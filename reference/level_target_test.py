#!/usr/bin/env python3
"""level_target_test.py — G's round-level exits on the SPY/QQQ-as-MES/MNQ mirror.

VOID (9/19): this file carries the pre-fix simulator loop (fill-bar credit, same-bar
ratchet). Its LEVEL-TARGET-TEST.txt is kept only as the record of the mistake; the
idea ("close at the round level") is retested honestly in reference/edge_lab.py.

G, 9/18: "targets: for MNQ the closest 100 level, for ES the levels ending in
25 — as soon as it hits 7725 it closes the trade. OR move the rung to 7720,
5 pts below, in case it continues."

Same 104 alerts / bars / entry as futures_mirror_grid.py. Under every variant
G's ladder runs (−stop, +1x → BE, +2x → +1x, ...). Variants:
  A  CLOSE at the first round level past entry (ES 25s, NQ 100s)
  B  at the level, stop = level − buffer (ES 5, NQ 20) and ride to the next
     level, where the stop moves to that level − buffer, and so on
Both are run with the level taken as the FIRST one past entry, and again
skipping any level closer than MIN_AWAY pts (ES 5 / NQ 20) — a level 2 pts
away is not a target. MEASUREMENT ONLY. Output: reference/LEVEL-TARGET-TEST.txt
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
import futures_mirror_grid as g                            # noqa: E402

GRID = {"ES": 25.0, "NQ": 100.0}
BUFFER = {"ES": 5.0, "NQ": 20.0}
MIN_AWAY = {"ES": 5.0, "NQ": 20.0}
STOPS = (12.5, {"ES": 7.5, "NQ": 12.5})


def next_level(price, s, grid, min_away):
    lvl = (math.floor(price / grid) + 1) * grid if s > 0 else (math.ceil(price / grid) - 1) * grid
    if abs(lvl - price) < min_away:
        lvl += s * grid
    return lvl


def run(a, bars, stop, variant, min_away):
    root, _m, ppt = fm.MAP[a["sym"]]
    stop_pts = g._stop_for(stop, root)
    b = bars[root]
    s = 1 if a["dirn"] == "L" else -1
    t0 = (a["ts"] + dt.timedelta(minutes=1)).replace(second=0, microsecond=0)
    day_end = a["ts"].replace(hour=fm.CLOSE.hour, minute=fm.CLOSE.minute, second=0, microsecond=0)
    w = b[(b.index >= t0) & (b.index <= day_end)]
    if w.empty:
        return None
    e = float(w.iloc[0]["open"])
    stop0 = e - s * stop_pts
    st = stop0
    lvl = next_level(e, s, GRID[root], min_away[root])
    mfe, ex, why, levels = 0.0, None, None, 0
    for i in range(len(w)):
        r = w.iloc[i]
        hi, lo = float(r["high"]), float(r["low"])
        if (lo <= st) if s > 0 else (hi >= st):
            ex = st
            why = "STOP" if st == stop0 else ("BE" if st == e else ("LEVEL-TRAIL" if levels else "RATCHET"))
            break
        if (hi >= lvl) if s > 0 else (lo <= lvl):
            if variant == "A":
                ex, why = lvl, "TARGET"
                break
            levels += 1
            new = lvl - s * BUFFER[root]
            if (s > 0 and new > st) or (s < 0 and new < st):
                st = new
            lvl += s * GRID[root]
        fav = (hi - e) if s > 0 else (e - lo)
        mfe = max(mfe, fav)
        if mfe >= stop_pts:                                   # G's ladder: arm 1x, rungs 1x
            k = math.floor((mfe - stop_pts) / stop_pts)
            new = e + s * (k * stop_pts)
            if (s > 0 and new > st) or (s < 0 and new < st):
                st = new
    if ex is None:
        ex, why = float(w.iloc[-1]["close"]), "CLOSE"
    pts = (ex - e) * s
    return {"pts": pts, "usd": pts * ppt - fm.RT_FEE, "why": why, "mfe": mfe, "levels": levels}


def main():
    days = set()
    for src, col in ((fm.MASTER, "symbol"), (fm.SHADOW, "sym")):
        for r in fm._read_csv(src):
            if str(r.get(col) or "").upper() in fm.MAP and len(str(r.get("date") or "")) == 10:
                days.add(r["date"][:10])
    trades = []
    for day in sorted(d for d in days if d >= fm.SINCE):
        if not all(fm.cached_bars(r, day)[0] is not None for r in ("ES", "NQ")):
            continue
        bars, _ = fm.bars_for(day)
        for a in fm.alerts_for(day):
            trades.append((a, bars))
    out = []
    p = out.append
    p("LEVEL TARGET TEST — %d SPY/QQQ alerts as MES/MNQ, G's ladder underneath every variant (arm 1x, rungs 1x)" % len(trades))
    p("levels: ES every 25, NQ every 100; B trails the stop %g (ES) / %g (NQ) under each level hit" % (BUFFER["ES"], BUFFER["NQ"]))
    p("baseline (ladder only, no level): 12.5 both = %+.0f" % sum(
        g.run(a, b, 12.5, 1.0, 1.0, None)["usd"] for a, b in trades if g.run(a, b, 12.5, 1.0, 1.0, None)))
    p("\n%-58s %8s %6s %8s %8s   ends" % ("stop · variant", "all $", "win%", "MES $", "MNQ $"))
    for stop in STOPS:
        for variant in ("A", "B"):
            for min_name, ma in (("first level, any distance", {"ES": 0, "NQ": 0}), ("skip levels < 5 ES / 20 NQ away", MIN_AWAY)):
                res = [(a, run(a, b, stop, variant, ma)) for a, b in trades]
                res = [(a, r) for a, r in res if r]
                usd = [r["usd"] for _a, r in res]
                ends = defaultdict(int)
                for _a, r in res:
                    ends[r["why"]] += 1
                p("%-58s %+8.0f %5d%% %+8.0f %+8.0f   %s" % (
                    "%s · %s · %s" % (g._stop_name(stop), "A close at level" if variant == "A" else "B trail under level", min_name),
                    sum(usd), round(100 * sum(1 for u in usd if u > 0) / len(usd)),
                    sum(r["usd"] for a, r in res if a["sym"] == "SPY"), sum(r["usd"] for a, r in res if a["sym"] == "QQQ"),
                    ", ".join("%s %d" % kv for kv in sorted(ends.items(), key=lambda kv: -kv[1]))))
    # per caller for the best
    best = None
    for stop in STOPS:
        for variant in ("A", "B"):
            for ma in ({"ES": 0, "NQ": 0}, MIN_AWAY):
                res = [(a, run(a, b, stop, variant, ma)) for a, b in trades]
                res = [(a, r) for a, r in res if r]
                tot = sum(r["usd"] for _a, r in res)
                if best is None or tot > best[0]:
                    best = (tot, stop, variant, ma, res)
    tot, stop, variant, ma, res = best
    p("\nBEST: %s · %s · min-away %s = %+.0f" % (g._stop_name(stop), variant, ma, tot))
    by = defaultdict(list)
    for a, r in res:
        by[(a["caller"] or a["room"] or "?")[:24]].append(r["usd"])
    for k, v in sorted(by.items(), key=lambda kv: -sum(kv[1])):
        if len(v) >= 3:
            p("  %-24s n=%2d %+6.0f win %2d%%" % (k, len(v), sum(v), round(100 * sum(1 for x in v if x > 0) / len(v))))
    byday = defaultdict(float)
    for a, r in res:
        byday[a["ts"].date()] += r["usd"]
    p("  positive days %d of %d" % (sum(1 for v in byday.values() if v > 0), len(byday)))
    txt = "\n".join(out)
    with open(os.path.join(HERE, "LEVEL-TARGET-TEST.txt"), "w", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
