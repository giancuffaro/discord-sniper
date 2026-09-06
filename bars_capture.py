"""bars_capture.py — save every traded contract's MINUTE BARS before they vanish.

Run it after the close:  python bars_capture.py
(or let the 4:45pm journal task call it — see WIRING at the bottom.)

WHY THIS EXISTS (9/4/26)
------------------------
G asked to pull the option charts for every trade and work out what the
ratchet should be. The obvious plan was to backfill from Tradier, which does
serve real 1-minute option bars. It failed, and the reason matters:

    111 trades recovered from the logs since 8/05
     24 still had intraday bars
     87 did not — and 84 of those were on contracts that had EXPIRED

**Tradier drops intraday history for expired options.** Not instantly — the
9/4 0DTEs were still there on 9/5, and captured — but every August expiry
was already gone. The window is days, not hours, and it is not documented,
so do not lean on it. Capture the same day and the question never comes up.

So this is not a backfill, it is a NIGHTLY CAPTURE. Run it the day of the
trade and the bars are ours forever, in bars/. Miss a day and that day's
0DTEs are unrecoverable.

WHY THIS BEATS option_tape.csv
------------------------------
The tape records ~1 quote/second, but ONLY while we hold the contract, and
only from the moment the stop is armed. These bars cover the WHOLE SESSION —
before the entry and after the exit — which is what answers "would a wider
stop have survived" and "how far did it run after we got out". Keep both:
the tape has real bid/ask, these have the full day.

HONEST LIMITS — say these out loud in any analysis built on this
  * These are TRADE prints, not quotes. There is no bid/ask. The ratchet
    fires on the BID, so a replay against bar lows is close but not exact.
  * A thin contract has holes. One deep-ITM SPY printed once in a day.
  * A minute bar's LOW says the price traded there, not that our stop would
    have filled there.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BARS = os.path.join(HERE, "bars")
LOG = os.path.join(HERE, "trades.log")

ORDER_IN = re.compile(
    r'ORDER IN BUY\s+(\d+)\s+([A-Z]{1,6})\s+([\d.]+)([CP])\s+(\d{4}-\d\d-\d\d)')


def occ(sym, expiry, cp, strike):
    return "%s%s%s%08d" % (sym, expiry.replace("-", "")[2:], cp,
                           int(round(float(strike) * 1000)))


def contracts_traded(day):
    """Every contract an ORDER went out on, on `day`. Reads the log, which is
    the one record that survives a restart and a git reset."""
    out = {}
    try:
        for line in open(LOG, encoding="utf-8", errors="replace"):
            if not line.startswith(day):
                continue
            m = ORDER_IN.search(line)
            if m:
                out[occ(m.group(2), m.group(5), m.group(4), m.group(3))] = True
    except OSError:
        pass
    return sorted(out)


def fetch(sym, day, token):
    """One contract's 1-minute bars for one session. Cached — a contract
    already on disk is never re-fetched, so this is safe to re-run."""
    os.makedirs(BARS, exist_ok=True)
    path = os.path.join(BARS, "%s_%s.json" % (sym, day))
    if os.path.exists(path):
        return None                       # already have it
    url = ("https://api.tradier.com/v1/markets/timesales?"
           + urllib.parse.urlencode({"symbol": sym, "interval": "1min",
                                     "start": day + " 09:30",
                                     "end": day + " 16:15"}))
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as fh:
        body = json.loads(fh.read().decode())
    rows = ((body.get("series") or {}) or {}).get("data") or []
    if isinstance(rows, dict):
        rows = [rows]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    time.sleep(0.25)                      # be a good citizen; no published cap
    return len(rows)


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y-%m-%d")
    try:
        cfg = json.load(open(os.path.join(HERE, "settings.json"),
                             encoding="utf-8"))
        token = ((cfg.get("execution") or {}).get("tradier")
                 or {}).get("access_token")
    except Exception as e:                              # noqa: BLE001
        print("could not read settings.json: %s" % e)
        return 1
    if not token:
        print("No Tradier token in settings. Run 'SETUP TRADIER.bat' first —")
        print("without it these bars are lost the moment the contract expires.")
        return 1

    syms = contracts_traded(day)
    if not syms:
        print("No contracts traded on %s — nothing to capture." % day)
        return 0

    print("Capturing %d contract(s) traded on %s" % (len(syms), day))
    got = have = fail = 0
    for s in syms:
        try:
            n = fetch(s, day, token)
            if n is None:
                have += 1
                print("   %-24s already saved" % s)
            else:
                got += 1
                print("   %-24s %d bar(s)%s" % (s, n, "" if n else
                      "   <- NONE: illiquid, or already expired"))
        except Exception as e:                          # noqa: BLE001
            fail += 1
            print("   %-24s FAILED %s" % (s, str(e)[:70]))
    print("\n  saved %d, already had %d, failed %d  ->  %s" % (got, have, fail, BARS))
    if fail:
        print("  Re-run to retry. Do it soon — Tradier drops intraday history")
        print("  for expired contracts within days, and it is not documented,")
        print("  so an expired 0DTE left for a week is simply gone.")
    return 0


# WIRING
#   Run it from the same scheduled task that builds the journal at 4:45pm,
#   after the journal step:
#       python bars_capture.py
#   Backfilling a missed day only works while the contracts are still alive:
#       python bars_capture.py 2026-09-03
if __name__ == "__main__":
    sys.exit(main())
