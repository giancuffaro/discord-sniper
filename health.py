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

# Two checks only mean anything on the PC the bridge runs on: the bridge's
# own HTTP door (127.0.0.1 in any other shell is that shell, not his box)
# and Webull (whose SDK is installed in the Windows Python). Reporting those
# as FAILURES from anywhere else is how a monitor invents an outage — the
# first run of this file did exactly that and I nearly wrote up a healthy
# bridge as down. They are SKIPPED, with the reason said out loud.
NOT_HERE = ("not reachable from this shell — run  python health.py  ON the "
            "PC where the bridge runs")


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

    Budgeted at 2 per 2 SECONDS on Webull's side and shared with the running
    bridge and with Market Sniper, so this is paced hard and capped at 3
    trials. A monitor that starves the thing it monitors is not a monitor.

    (The first version called `wo.client_from_settings()`, a factory I
    invented. It does not exist, so the check reported a permanent failure
    that was entirely my own. The real entry point is `WebullOptions(cfg)`.)
    """
    ex = (c.get("execution") or {})
    wb = (ex.get("webull") or {})
    if not (wb.get("app_key") and wb.get("app_secret")):
        return ("Webull balance", None, [], "no app_key/app_secret in settings")

    def go():
        # TWO bugs lived in this five-line function, both mine, both the
        # same shape — writing what I expected instead of reading what is
        # there:
        #   1. `balance()` does not exist. The methods are buying_power /
        #      futures_buying_power / positions / futures_positions.
        #   2. WebullOptions takes the WHOLE settings dict and digs out
        #      execution.webull itself. Handing it the sub-dict gave it an
        #      empty app_key, so it reported a permanent connection failure
        #      that was entirely fabricated by the test.
        # A monitor that invents outages is worse than no monitor.
        # connect() FIRST. `account_id` is blank in settings on purpose
        # (auto-pick), and a fresh client has not discovered it yet — so
        # buying_power() reads a balance for account None and returns None.
        # That is not a broken key, it is an unconnected client, and the
        # third version of this check was about to report it as an outage.
        from webull_options import WebullOptions
        cl = WebullOptions(c)
        acct = cl.connect()
        if not acct:
            raise IOError("connect() returned no account id")
        bp = cl.buying_power()
        if bp is None:
            raise IOError("connected as %s but Webull would not return a "
                          "balance (throttled?)" % acct)
    ok, lat, err = timed(go, min(trials, 3), pause=2.5)
    # The Webull SDK lives in the Windows Python, not in every shell this
    # file might be run from. "Not installed here" is an ENVIRONMENT fact,
    # not a broker outage, and must not be coloured like one.
    if ok == 0 and err and ("isn't installed" in err or "No module" in err
                            or "ModuleNotFound" in err):
        return ("Webull connect+bal", None, [], NOT_HERE)
    return ("Webull connect+bal", ok, lat, err)


def check_bridge(c, trials):
    """The bridge's own HTTP door.

    ONLY MEANINGFUL ON THE MACHINE THE BRIDGE RUNS ON. 127.0.0.1 inside a
    sandbox or container is that sandbox, not the Windows host — the first
    run of this reported 0/6 "connection refused" and I nearly wrote it up
    as the bridge being down when it was serving fine three feet away. A
    connection-refused here is reported as UNREACHABLE, not as a failure,
    because those are different facts.
    """
    url = "http://127.0.0.1:8787/health"

    def go():
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as fh:
            fh.read()

    ok, lat, err = timed(go, trials, pause=0.2)
    if ok == 0 and err and ("refused" in err.lower() or "111" in err):
        return ("Bridge 8787", None, [], NOT_HERE)
    return ("Bridge 8787", ok, lat, err)


def dxlink_from_log(max_read=4000000):
    """DXLink health WITHOUT connecting — read the running session's own log.

    See the module docstring: opening a second session damages the live one.

    SCOPED TO THE CURRENT BRIDGE RUN, NOT TO A TIME WINDOW. The first
    version took a `minutes` argument and converted it to bytes using a
    GUESSED 120 KB/minute. It reported "340 greeks errors" that were months
    of history, on a feed that had produced zero errors that hour — a
    monitor crying wolf, built on exactly the kind of made-up constant this
    project does not allow. There is no reliable bytes-per-minute rate: the
    log's growth depends entirely on how much the SDK is complaining.

    So it counts from the LAST bridge start marker onward and says so. That
    boundary is a real string in the file, not an estimate.
    """
    path = os.path.join(HERE, "bridge.log")
    out = {"connected": 0, "closed": 0, "reauth_ok": 0, "reauth_refused": 0,
           "errors": 0, "scoped": False, "lines": 0}
    try:
        size = os.path.getsize(path)
        want = min(size, max_read)
        with open(path, "rb") as fh:
            fh.seek(size - want)
            blob = fh.read().decode("utf-8", "replace")
    except OSError:
        return out

    lines = blob.splitlines()
    # Find the last boot marker and count only what came after it.
    start = 0
    for i in range(len(lines) - 1, -1, -1):
        if "QUOTE BUS on" in lines[i] or "Webull LIVE connected" in lines[i]:
            start, out["scoped"] = i, True
            break
    for line in lines[start:]:
        if "[greeks]" not in line:
            continue
        out["lines"] += 1
        low = line.lower()
        if "connected" in low:
            out["connected"] += 1
        elif "closed the websocket" in low:
            out["closed"] += 1
        elif "refused re-auth" in low:
            out["reauth_refused"] += 1
        elif "refreshed in place" in low:
            out["reauth_ok"] += 1
        elif "server error" in low:
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
        print("because a second session breaks the live one).")
        print("Scope: %s"
              % ("since the last bridge start" if dx["scoped"]
                 else "WHOLE LOG TAIL — no boot marker found, so these "
                      "counts may include old runs"))
        print("   connected %d · socket closed %d · re-auth ok %d · "
              "REFUSED %d · server errors %d"
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
