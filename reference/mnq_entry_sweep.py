#!/usr/bin/env python3
"""mnq_entry_sweep.py — MNQ: every entry variant x exit variant, scored on win%
AND dollars, with the both-halves check.

G, 9/18: "figure out MNQ's best scenario ... run multiple scenarios of
entries or pullbacks, or mess with the round hour times, give it a little
more wiggle room or not ... get me to at least 75%."

Alerts: every QQQ entry (bot + shadow + room logs), NQ 1-min bars, as in
pullback_level_entry_test.py. ENTRY knobs: grid 25 / 50 / 100; buffer before
the level 0 / 5 / 10 (or -5 = 5 THROUGH it, more wiggle); wait 5 / 15 / 30 /
60 min / all day; time-of-day filter: all / skip 09:30-10:00 / skip the first
5 minutes after every round hour / only 10:00-14:00. EXIT knobs: stop 7.5 /
10 / 12.5 / 15; BE trigger 0.5x / 0.75x the stop; rung 0.25x / 0.5x; target
none / 1x / 2x. A row needs 20+ fills to be listed. MEASUREMENT ONLY.
Output: reference/MNQ-ENTRY-SWEEP.txt
"""
from __future__ import annotations

import itertools
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
import futures_ratchet_sweep as rs                          # noqa: E402
import pullback_level_entry_test as pt                     # noqa: E402

GRIDS = (25.0, 50.0, 100.0)
BUFS = (-5.0, 0.0, 5.0, 10.0)
WAITS = (5, 15, 30, 60, None)
TOD = {
    "all": lambda a: True,
    "skip 09:30-10:00": lambda a: not (a["ts"].hour == 9),
    "skip :00-:05 after each hour": lambda a: a["ts"].minute >= 5,
    "10:00-14:00 only": lambda a: 10 <= a["ts"].hour < 14,
}
STOPS = (7.5, 10.0, 12.5, 15.0)
ARMS = (0.5, 0.75)
RUNGS = (0.25, 0.5)
TARGETS = (None, 1.0, 2.0)
MIN_FILLS = 20


def main():
    W = [x for x in rs.windows() if x[0]["grp"] == "QQQ"]
    days = sorted({a["ts"].date() for a, *_ in W})
    mid = days[len(days) // 2]
    out = []
    p = out.append
    p("MNQ ENTRY x EXIT SWEEP — %d QQQ alerts, %d days (split at %s); rows need %d+ fills" % (len(W), len(days), mid, MIN_FILLS))
    rows = []
    entries = list(itertools.product(GRIDS, BUFS, WAITS, TOD.keys()))
    exits = [(st, ar, ru, tg) for st in STOPS for ar in ARMS for ru in RUNGS for tg in TARGETS]
    # fills are independent of the exit: compute once per entry
    for grid, buf, wait, tod in entries:
        fills = []
        for a, ppt, rows_, e in W:
            if not TOD[tod](a):
                continue
            s = 1 if a["dirn"] == "L" else -1
            i, fill = pt.pullback_fill(rows_, e, s, grid, wait, buf)
            if i is None:
                continue
            fills.append((a, s, fill, rows_[i:], ppt))
        if len(fills) < MIN_FILLS:
            continue
        for st, ar, ru, tg in exits:
            vals = [(a, rs.sim(s, fill, rest, ppt, st, ar, ru, tg)) for a, s, fill, rest, ppt in fills]
            tot = sum(v for _a, v in vals)
            h1 = sum(v for a, v in vals if a["ts"].date() < mid)
            win = 100 * sum(1 for _a, v in vals if v > 0) / len(vals)
            rows.append((win, tot, h1, tot - h1, len(vals), grid, buf, wait, tod, st, ar, ru, tg))
    p("%d entry variants with %d+ fills x %d exits = %d rows" % (len({r[5:9] for r in rows}), MIN_FILLS, len(exits), len(rows)))

    def line(r):
        win, tot, h1, h2, n, grid, buf, wait, tod, st, ar, ru, tg = r
        return ("%3.0f%%  %+6.0f  (%+5.0f/%+5.0f)  n=%2d  grid %3g  buf %+3g  wait %-4s  %-28s  stop %4g BE %.2gx rung %.2gx tgt %s"
                % (win, tot, h1, h2, n, grid, buf, "day" if wait is None else "%dm" % wait, tod, st, ar, ru, "none" if tg is None else "%gx" % tg))
    both = [r for r in rows if r[2] > 0 and r[3] > 0]
    p("\nTOP 15 by WIN%% (both halves positive, %d+ fills):" % MIN_FILLS)
    for r in sorted(both, key=lambda r: (-r[0], -r[1]))[:15]:
        p("  " + line(r))
    p("\nTOP 15 by DOLLARS (both halves positive):")
    for r in sorted(both, key=lambda r: -r[1])[:15]:
        p("  " + line(r))
    p("\nBEST BALANCE — win%% >= 75 and the most dollars:")
    for r in sorted([r for r in both if r[0] >= 75], key=lambda r: -r[1])[:10]:
        p("  " + line(r))
    p("\nWHAT EACH KNOB DOES (average win%% / average $ across every row it appears in):")
    for name, idx, keys in (("grid", 5, GRIDS), ("buffer", 6, BUFS), ("wait", 7, WAITS), ("time filter", 8, list(TOD)),
                            ("stop", 9, STOPS), ("BE trigger", 10, ARMS), ("rung", 11, RUNGS), ("target", 12, TARGETS)):
        parts = []
        for k in keys:
            sel = [r for r in rows if r[idx] == k]
            if sel:
                parts.append("%s: %.0f%% / %+.0f (%d rows)" % ("none" if k is None else k, sum(r[0] for r in sel) / len(sel), sum(r[1] for r in sel) / len(sel), len(sel)))
        p("  %-12s " % name + " | ".join(parts))
    txt = "\n".join(out)
    with open(os.path.join(HERE, "MNQ-ENTRY-SWEEP.txt"), "w", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
