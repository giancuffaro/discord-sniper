#!/usr/bin/env python3
"""pullback_level_entry_test.py — take the alert, but ENTER only on a pullback to
the nearest round level: ES every 25, NQ every 50 (and every 100).

G, 9/18: "imagine we took the alert and waited for the nearest round number
pull back — MES every 25 to enter, MNQ every 50 or 100."

Same alerts (bot + shadow + room-log entries) and bars as futures_ratchet_sweep.py.
Long alert: the level is the first multiple BELOW the price on the bar after
the alert (short: above). A resting limit at that level fills when a bar's low
(high) touches it, inside a WAIT window (5 / 15 / 30 min / rest of day); if
it never touches, the alert is skipped. Exits run from the fill: MES 1:1
bracket at 12.5 and 20; MNQ 1:1 at 12.5 and 25, the 10 / BE-at-5 / 2.5-rung
trail, and 25-stop 3x. Each line shows how many filled, the result, and the
same alerts entered INSTANTLY for comparison. MEASUREMENT ONLY.
Output: reference/PULLBACK-LEVEL-ENTRY-TEST.txt
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
import futures_mirror_daily as fm                          # noqa: E402
import futures_ratchet_sweep as rs                                 # noqa: E402

WAITS = (5, 15, 30, None)
EXITS = {
    "SPY": (("12.5 stop · 1:1", 12.5, None, 1.0, 1.0), ("20 stop · 1:1", 20.0, None, 1.0, 1.0)),
    "QQQ": (("12.5 stop · 1:1", 12.5, None, 1.0, 1.0), ("25 stop · 1:1", 25.0, None, 1.0, 1.0),
            ("10 stop · BE at 5 · 2.5 rungs", 10.0, 0.5, 0.25, None), ("25 stop · 3x target", 25.0, None, 1.0, 3.0)),
}
GRIDS = {"SPY": (25.0,), "QQQ": (50.0, 100.0)}


def level_below(price, s, grid):
    return math.floor(price / grid) * grid if s > 0 else math.ceil(price / grid) * grid


def pullback_fill(rows, e, s, grid, wait):
    lvl = level_below(e, s, grid)
    if lvl == e:                                   # already sitting on it: that is the fill
        return 0, lvl
    n = len(rows) if wait is None else min(len(rows), wait)
    for i in range(n):
        hi, lo, _c = rows[i]
        if (lo <= lvl) if s > 0 else (hi >= lvl):
            return i, lvl
    return None, lvl


def main():
    W = rs.windows()
    out = []
    p = out.append
    p("PULLBACK-TO-LEVEL ENTRY — %d SPY/MES and %d QQQ/MNQ alerts; limit at the nearest ES 25 / NQ 50 or 100 below (above for puts), filled on touch"
      % (sum(1 for a, *_ in W if a["sym"] == "SPY"), sum(1 for a, *_ in W if a["sym"] == "QQQ")))
    p("%-6s %-5s %-9s %-32s %6s %8s %6s %8s | %8s %6s" % ("sym", "grid", "wait", "exit", "filled", "pullbk $", "win%", "avg wait", "instant$", "win%"))
    p("                                                                                  (instant = same filled alerts entered at the alert bar instead)")
    for sym in ("SPY", "QQQ"):
        tr = [x for x in W if x[0]["sym"] == sym]
        for grid in GRIDS[sym]:
            for wait in WAITS:
                for name, st, ar, ru, tg in EXITS[sym]:
                    got, inst, waits = [], [], []
                    for a, ppt, rows, e in tr:
                        s = 1 if a["dirn"] == "L" else -1
                        i, lvl = pullback_fill(rows, e, s, grid, wait)
                        if i is None:
                            continue
                        rest = rows[i:]
                        got.append(rs.sim(s, lvl, rest, ppt, st, ar, ru, tg))
                        inst.append(rs.sim(s, e, rows, ppt, st, ar, ru, tg))
                        waits.append(i)
                    if not got:
                        p("%-6s %-5g %-9s %-32s %6d" % (sym, grid, "day" if wait is None else "%dm" % wait, name, 0))
                        continue
                    p("%-6s %-5g %-9s %-32s %6d %+8.0f %5.0f%% %7.0fm | %+8.0f %5.0f%%" % (
                        sym, grid, "day" if wait is None else "%dm" % wait, name, len(got), sum(got),
                        100 * sum(1 for v in got if v > 0) / len(got), sum(waits) / len(waits),
                        sum(inst), 100 * sum(1 for v in inst if v > 0) / len(inst)))
            p("")
    # the skipped: what did the instant entry make on alerts that never pulled back (day wait)?
    for sym in ("SPY", "QQQ"):
        tr = [x for x in W if x[0]["sym"] == sym]
        grid = GRIDS[sym][0]
        name, st, ar, ru, tg = EXITS[sym][0]
        never = [rs.sim(1 if a["dirn"] == "L" else -1, e, rows, ppt, st, ar, ru, tg)
                 for a, ppt, rows, e in tr if pullback_fill(rows, e, 1 if a["dirn"] == "L" else -1, grid, None)[0] is None]
        p("%s: %d alerts NEVER pulled back to a %g level all day; entered instantly under %s they made %+.0f (win %.0f%%)"
          % (sym, len(never), grid, name, sum(never), 100 * sum(1 for v in never if v > 0) / max(1, len(never))))
    txt = "\n".join(out)
    with open(os.path.join(HERE, "PULLBACK-LEVEL-ENTRY-TEST.txt"), "w", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
