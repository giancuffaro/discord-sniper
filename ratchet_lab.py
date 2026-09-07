"""ratchet_lab.py — WHICH RATCHET WOULD HAVE MADE THE MOST MONEY?

Run it:  python ratchet_lab.py            (every trade with saved bars)
         python ratchet_lab.py --min 40   (refuse to print unless n >= 40)

THE QUESTION, STATED PROPERLY
-----------------------------
G, 9/4: "read the options contract chart and see what is the best exit we
could have gotten... what ratchet would be the sweet spot so we can squeeze
every single trade. Even if we get stopped out, the ones that actually go, we
get the best percentage."

So: for each real trade, take what the contract ACTUALLY did after entry, and
ask which combination of

    opening stop  ·  arm level  ·  rung size

produces the most total profit across all of them — accepting stop-outs on
the losers so the winners can run.

Note it does NOT need the underlying's chart. The stop sits on the OPTION
price, so the option's own path decides every exit. The underlying would only
matter if we wanted rules keyed off the stock's behaviour, which is a
different question.

WHERE THE DATA COMES FROM
  bars/       1-minute option bars, saved by bars_capture.py after the close.
              Webull has no option history at all; Tradier serves it only
              while the contract is ALIVE, so the capture is what makes this
              possible. Miss a day and that day's 0DTEs are gone for good.
  trades.log  entry price, entry time, and the contract, per trade.

THE FIRST REAL RESULT (9/4/26, n=15) — kept so drift is visible
    YOURS   stop -10%  arm +10%  rung 10%    +1.4%/trade   13/15 stopped
    BEST    stop -25%  arm +10%  rung 15%    +8.4%/trade    9/15 stopped
  The finding was NOT about rung size — 5% vs 15% differed by 0.3%. It was
  the OPENING STOP. At -10% the trades were killed before the ratchet could
  ever arm. Arming at +10% was right; every later arm did worse.
  At n=15 that is a direction, not a decision.

HONESTY RULES BUILT IN
  * Bars are TRADE prints, not quotes. The real stop fires on the BID, so a
    replay is close, not exact.
  * Within one minute we cannot know if the high or the low came first, so
    the stop is checked against the LOW *before* the high may advance the
    ratchet. That is deliberately pessimistic.
  * A trade that never stops is exited at the last bar. That is what a
    ratchet-only rule really does, but it flatters the survivors.
  * Below --min trades it prints the table and REFUSES to name a winner.
"""
import argparse
import itertools
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BARS = os.path.join(HERE, "bars")
LOG = os.path.join(HERE, "trades.log")

ORDER_IN = re.compile(
    r'ORDER IN BUY\s+(\d+)\s+([A-Z]{1,6})\s+([\d.]+)([CP])\s+(\d{4}-\d\d-\d\d)')
FILLED = re.compile(r'FILLED\s+([A-Z]{1,6})\s+.*?filled\s+([\d.]+)\s+at\s+([\d.]+)')

STOPS = (10, 15, 20, 25, 30)
ARMS = (5, 10, 15, 20)
RUNGS = (5, 10, 15, 20)


def trades_with_bars():
    """Every entry we can both identify AND replay."""
    pend, out = {}, []
    try:
        fh = open(LOG, encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in fh:
        m = ORDER_IN.search(line)
        if m:
            pend[m.group(2)] = {"symbol": m.group(2), "strike": float(m.group(3)),
                                "cp": m.group(4), "expiry": m.group(5)}
            continue
        m = FILLED.search(line)
        if m and m.group(1) in pend:
            t = pend.pop(m.group(1))
            t["fill"] = float(m.group(3))
            t["day"], t["hhmm"] = line[:10], line[11:16]
            from occ import build as _occ_build
            t["occ"] = _occ_build(t["symbol"], t["expiry"], t["cp"], t["strike"])
            p = os.path.join(BARS, "%s_%s.json" % (t["occ"], t["day"]))
            if not os.path.exists(p):
                continue
            try:
                bars = json.load(open(p, encoding="utf-8"))
            except Exception:                            # noqa: BLE001
                continue
            bars = [b for b in bars if b.get("time", "")[11:16] >= t["hhmm"]]
            if len(bars) >= 3 and t["fill"] > 0:
                t["bars"] = bars
                out.append(t)
    return out


def replay(t, open_stop, arm, rung):
    """Walk the minutes. Returns (percent result, why it ended)."""
    f = t["fill"]
    stop = f * (1 - open_stop / 100.0)
    locked = None
    for b in t["bars"]:
        # PESSIMISTIC ON PURPOSE: the stop is tested first, because we cannot
        # know whether the low or the high came first inside the minute.
        if b["low"] <= stop:
            return (stop - f) / f * 100.0, "stopped"
        gain = (b["high"] - f) / f * 100.0
        if gain >= arm:
            lk = rung * int((gain - arm) // rung)   # first rung = breakeven
            if locked is None or lk > locked:
                locked = lk
                stop = max(stop, f * (1 + lk / 100.0))
    return (t["bars"][-1]["close"] - f) / f * 100.0, "held"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=40,
                    help="refuse to name a winner below this many trades")
    a = ap.parse_args()

    rows = trades_with_bars()
    print("=" * 70)
    print("  RATCHET LAB — real trades, real minute bars")
    print("=" * 70)
    print("  trades replayable: %d" % len(rows))
    if not rows:
        print("\n  No saved bars yet. Run 'python bars_capture.py' after the")
        print("  close — and do it the SAME DAY: Tradier drops intraday")
        print("  history for expired contracts, so a 0DTE left a week is gone.")
        return 0

    res = []
    for op, arm, rung in itertools.product(STOPS, ARMS, RUNGS):
        tot = st = 0
        for t in rows:
            pct, why = replay(t, op, arm, rung)
            tot += pct
            st += (why == "stopped")
        res.append((tot / len(rows), op, arm, rung, st))
    res.sort(reverse=True)

    print("\n  %-36s %11s %9s" % ("rule", "avg/trade", "stopped"))
    for avg, op, arm, rung, st in res[:8]:
        print("  stop -%2d%%   arm +%2d%%   rung %2d%%        %+7.1f%%   %2d/%d"
              % (op, arm, rung, avg, st, len(rows)))
    print("   ...")
    for avg, op, arm, rung, st in res[-2:]:
        print("  stop -%2d%%   arm +%2d%%   rung %2d%%        %+7.1f%%   %2d/%d"
              % (op, arm, rung, avg, st, len(rows)))

    cur = [x for x in res if x[1:4] == (10, 10, 10)]
    if cur:
        avg, op, arm, rung, st = cur[0]
        print("\n  YOURS      stop -10%%   arm +10%%   rung 10%%   %+7.1f%%   %2d/%d"
              % (avg, st, len(rows)))

    # WHICH KNOB ACTUALLY MATTERS. On 9/4 the answer was the opening stop,
    # not the rung — worth re-checking every run rather than assuming.
    print("\n  which setting moves the result:")
    for name, idx, vals in (("opening stop", 1, STOPS), ("arm", 2, ARMS),
                            ("rung", 3, RUNGS)):
        best = {}
        for r in res:
            best[r[idx]] = max(best.get(r[idx], -99), r[0])
        spread = max(best.values()) - min(best.values())
        detail = "  ".join("%d%%:%+.1f" % (v, best[v]) for v in vals)
        print("    %-13s spread %5.1f pts   %s" % (name, spread, detail))

    if len(rows) < a.min:
        print("""
  n=%d — TOO FEW TO ACT ON, and that is the honest answer.
  One outlier reorders this whole table. Treat the ranking as a direction
  to watch, not a setting to change. Keep running bars_capture.py after
  every close; at ~6 trades a day this reaches n=%d in about %d sessions.
""" % (len(rows), a.min, max(1, (a.min - len(rows)) // 6 + 1)))
    else:
        print("""
  n=%d. Before changing anything, drop the single best trade and re-run:
  if the winner changes, the winner was one lucky trade.
""" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
