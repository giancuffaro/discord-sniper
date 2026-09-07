"""health.py — is every connection actually reliable? Measured, not assumed.

    python health.py                 one pass
    python health.py --trials 20     20 trials per endpoint, with percentiles
    python health.py --watch 30      re-run every 30 minutes, append to a log

WHY (9/7/26)
------------
G's rule: nothing assumed, nothing guessed — real data, polled or pulled.
"Are the connections reliable?" had never been measured here. It was
answered from log impressions, which is how I ended up telling him the
greeks socket was flapping when it had dropped twice in its life, and how I
called Friday's closing quotes "live market data" on a day the market was
shut.

So this asks each endpoint, repeatedly, and reports what came back: success
rate, median latency, worst latency. Percentiles rather than a single ping,
because a feed that answers in 80ms nine times and 9 seconds once is not a
reliable feed, and one ping cannot tell you that.

THE ONE THING IT MUST NEVER DO
------------------------------
**It does not open a tastytrade DXLink session.** tastytrade caps concurrent
sessions per account. On 9/7 a probe that opened a second one forced three
`refused RE-AUTH` errors and three reconnects on the LIVE greeks feed during
market hours. Discord Sniper holds that session; Market Sniper held another.
A test that damages the thing it measures is worse than no test.

DXLink health is therefore read from `bridge.log` — the running session's own
words — rather than by connecting. That is the honest way to observe a
single-owner resource.

MARKET-CLOSED HONESTY
---------------------
It asks Tradier's clock FIRST and prints the answer, because every quote
number below means something different when the market is shut. A closed
market returns the previous session's last quote, which looks exactly like
live data and is not. Nothing here should ever be read as "live" without
that line saying so.
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "health.csv")


def cfg():
    try:
        return json.load(open(os.path.join(HERE, "settings.json"),
                              encoding="utf-8"))
    except OSError:
        return {}


def _pct(v, p):
    if not v:
        return None
    v = sorted(v)
    i = min(len(v) - 1, max(0, int(round((p / 100.0) * (len(v) - 1)))))
    return v[i]


def timed(fn, trials, pause=0.35):
    """Run fn() `trials` times. Returns (ok_count, [latencies_ms], last_err).
    A failure is recorded, never retried into looking like a success."""
    lat, ok, err = [], 0, None
    for i in range(trials):
        if i:
            time.sleep(pause)
        t0 = time.time()
        try:
            fn()
            lat.append((time.time() - t0) * 1000.0)
            ok += 1
        except Exception as e:                              # noqa: BLE001
            err = str(e)[:110]
    return ok, lat, err


def http_json(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as fh:
        return json.loads(fh.read().decode())


# ---------------------------------------------------------------- checks
def check_tradier(c, trials):
    tok = ((c.get("execution") or {}).get("tradier") or {}).get("access_token")
    if not tok:
        return ("Tradier REST", None, [], "no token in settings")
    h = {"Authorization": "Bearer " + tok, "Accept": "application/json"}

    def go():
        d = http_json("https://api.tradier.com/v1/markets/quotes?"
                      + urllib.parse.urlencode({"symbols": "SPY"}), h)
        q = ((d.get("quotes") or {}).get("quote") or {})
        if not q.get("symbol"):
            raise IOError("no quote in response")
    return ("Tradier REST",) + timed(go, trials)


def check_tasty_oauth(c, trials):
    """The 15-minute token exchange. This is the one that broke on 9/6 with
    'client secret mismatch' and silently killed greeks — worth watching."""
    tt = (c.get("execution") or {}).get("tastytrade") or {}
    if not (tt.get("client_secret") and tt.get("refresh_token")):
        return ("tastytrade OAuth", None, [], "no credentials in settings")

    def go():
        import broker as bk
        b = bk.get_broker(c, "tastytrade")
        d = b.quote_token() or {}
        if not d.get("token"):
            raise IOError("no quote token returned")
        if str(d.get("level") or "").lower() in ("demo", ""):
            raise IOError("token level=%s (delayed/unfunded)" % d.get("level"))
    return ("tastytrade OAuth",) + timed(go, trials, pause=1.0)


def check_webull(c, trials):
    """Balance read — the cheapest honest proof the trading key still works.
    Budgeted at 2 per 2s, so this paces itself and uses few trials."""
    def go():
        import webull_options as wo
        cl = wo.client_from_settings(c) if hasattr(wo, "client_from_settings") \
            else None
        if cl is None:
            raise IOError("no client factory in webull_options")
        b = cl.balance()
        if b is None:
            raise IOError("balance returned nothing")
    return ("Webull balance",) + timed(go, min(trials, 4), pause=1.2)


def check_bridge(c, trials):
    url = "http://127.0.0.1:8787/health"

    def go():
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as fh:
            fh.read()
    return ("Bridge 8787",) + timed(go, trials, pause=0.2)


def dxlink_from_log(minutes=60):
    """DXLink health WITHOUT connecting — read the running session's own log.

    See the module docstring: opening a second session damages the live one.
    This counts what the real session reported in the last `minutes`.
    """
    path = os.path.join(HERE, "bridge.log")
    out = {"connected": 0, "closed": 0, "reauth_ok": 0, "reauth_refused": 0,
           "errors": 0, "read_bytes": 0}
    try:
        size = os.path.getsize(path)
        # ~120 KB per minute of log at the observed rate; cap the read.
        want = min(size, max(400000, minutes * 120000))
        with open(path, "rb") as fh:
            fh.seek(size - want)
            blob = fh.read().decode("utf-8", "replace")
        out["read_bytes"] = want
    except OSError:
        return out
    for line in blob.splitlines():
        if "[greeks]" not in line:
            continue
        low = line.lower()
        if "connected" in low:
            out["connected"] += 1
        elif "closed the websocket" in low:
            out["closed"] += 1
        elif "refused re-auth" in low:
            out["reauth_refused"] += 1
        elif "refreshed in place" in low:
            out["reauth_ok"] += 1
        elif "error" in low:
            out["errors"] += 1
    return out


def market_state(c):
    tok = ((c.get("execution") or {}).get("tradier") or {}).get("access_token")
    if not tok:
        return None
    try:
        d = http_json("https://api.tradier.com/v1/markets/clock",
                      {"Authorization": "Bearer " + tok,
                       "Accept": "application/json"})
        return (d.get("clock") or {})
    except Exception:                                       # noqa: BLE001
        return None


def run_once(trials, quiet=False):
    c = cfg()
    clock = market_state(c)
    rows = []

    if not quiet:
        print("=" * 66)
        if clock:
            print("MARKET: %s — %s   (%s)"
                  % (str(clock.get("state", "?")).upper(),
                     clock.get("description", ""), clock.get("date", "")))
            if str(clock.get("state")) != "open":
                print("        Quotes below are the PREVIOUS session's last")
                print("        print. They are not live and must not be read")
                print("        as live. Latency numbers are still valid.")
        else:
            print("MARKET: unknown — could not reach Tradier's clock")
        print("=" * 66)
        print("%-20s %7s %9s %9s %9s  %s"
              % ("ENDPOINT", "OK", "p50 ms", "p90 ms", "worst", "note"))
        print("-" * 66)

    for fn in (check_bridge, check_tradier, check_tasty_oauth, check_webull):
        try:
            name, ok, lat, err = fn(c, trials)
        except Exception as e:                              # noqa: BLE001
            name, ok, lat, err = (getattr(fn, "__name__", "?"), None, [],
                                  str(e)[:110])
        n = len(lat) + (0 if ok is None else 0)
        total = (ok or 0) + (0 if ok is None else 0)
        rows.append((name, ok, lat, err))
        if quiet:
            continue
        if ok is None:
            print("%-20s %7s %9s %9s %9s  %s"
                  % (name, "SKIP", "-", "-", "-", err or ""))
            continue
        tried = max(len(lat), ok) if ok else trials
        print("%-20s %6d/%-2d %9s %9s %9s  %s"
              % (name, ok, tried if tried else trials,
                 "%.0f" % _pct(lat, 50) if lat else "-",
                 "%.0f" % _pct(lat, 90) if lat else "-",
                 "%.0f" % max(lat) if lat else "-",
                 "" if ok and not err else (err or "")))

    dx = dxlink_from_log()
    if not quiet:
        print("-" * 66)
        print("DXLink greeks (read from bridge.log — NEVER connected to,")
        print("because a second session breaks the live one):")
        print("   connected %d · socket closed %d · re-auth ok %d · "
              "REFUSED %d · errors %d"
              % (dx["connected"], dx["closed"], dx["reauth_ok"],
                 dx["reauth_refused"], dx["errors"]))
        if dx["reauth_refused"]:
            print("   ^ REFUSED means another app or a probe is holding a")
            print("     tastytrade session. Two apps is the cap. Find it.")
        print("=" * 66)

    # append a machine-readable row for trend watching
    try:
        new = not os.path.exists(LOG)
        with open(LOG, "a", encoding="utf-8", newline="") as fh:
            import csv as _csv
            w = _csv.writer(fh)
            if new:
                w.writerow(["ts", "market", "endpoint", "ok", "trials",
                            "p50_ms", "p90_ms", "max_ms", "err"])
            st = (clock or {}).get("state", "?")
            for name, ok, lat, err in rows:
                w.writerow([round(time.time(), 3), st, name,
                            "" if ok is None else ok,
                            trials, "%.1f" % _pct(lat, 50) if lat else "",
                            "%.1f" % _pct(lat, 90) if lat else "",
                            "%.1f" % max(lat) if lat else "", err or ""])
    except OSError:
        pass
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=6)
    ap.add_argument("--watch", type=int, default=0,
                    help="repeat every N minutes")
    a = ap.parse_args()
    run_once(a.trials)
    while a.watch:
        time.sleep(a.watch * 60)
        print()
        run_once(a.trials)
    return 0


if __name__ == "__main__":
    sys.exit(main())
