#!/usr/bin/env python3
"""ratchet_sweep.py — hundreds of stop / arm / rung / target combinations on the
SPY->MES and QQQ->MNQ alert mirror, each instrument on its own.

G, 9/18: "take the best results from MNQ and MES and lay them out; run 100
different ratchet or other scenarios to see if we can increase our odds."

Same alerts, bars and entry as futures_mirror_grid.py (bot + shadow + room-log
entries the bot never parsed, since 9/18). Every combination of
  stop      5 / 7.5 / 10 / 12.5 / 15 / 20 / 25 / 35 pts
  arm       none / 0.5x / 0.75x / 1x / 1.5x the stop  (profit that moves the stop to breakeven)
  rung      0.25x / 0.5x / 1x the stop                (each further rung locks that much)
  target    none / 1x / 1.5x / 2x / 3x the stop       (hard take-profit)
= 8 x (1 + 4 x 3) x 5 = 520 combinations per instrument.
OVERFIT WARNING, printed with the result: with 64 SPY and 40 QQQ alerts the best
of 520 will look good by luck. So each combination is also scored on the FIRST
half of the days and the SECOND half separately; only a combination positive in
both halves is worth a second look. MEASUREMENT ONLY.
Output: reference/RATCHET-SWEEP.txt
"""
from __future__ import annotations

import datetime as dt
import itertools
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

STOPS = (5.0, 7.5, 10.0, 12.5, 15.0, 20.0, 25.0, 35.0)
ARMS = (None, 0.5, 0.75, 1.0, 1.5)
RUNGS = (0.25, 0.5, 1.0)
TARGETS = (None, 1.0, 1.5, 2.0, 3.0)


def windows():
    """[(alert, ppt, [(hi,lo,close)...], entry)] — bars pulled out of pandas once."""
    days = set()
    for src, col in ((fm.MASTER, "symbol"), (fm.SHADOW, "sym")):
        for r in fm._read_csv(src):
            if str(r.get(col) or "").upper() in fm.MAP and len(str(r.get("date") or "")) == 10:
                days.add(r["date"][:10])
    out = []
    for day in sorted(d for d in days if d >= fm.SINCE):
        if not all(fm.cached_bars(r, day)[0] is not None for r in ("ES", "NQ")):
            continue
        bars, _ = fm.bars_for(day)
        for a in fm.alerts_for(day):
            root, _m, ppt = fm.MAP[a["sym"]]
            b = bars[root]
            t0 = (a["ts"] + dt.timedelta(minutes=1)).replace(second=0, microsecond=0)
            day_end = a["ts"].replace(hour=fm.CLOSE.hour, minute=fm.CLOSE.minute, second=0, microsecond=0)
            w = b[(b.index >= t0) & (b.index <= day_end)]
            if w.empty:
                continue
            rows = list(zip(w["high"].astype(float), w["low"].astype(float), w["close"].astype(float)))
            out.append((a, ppt, rows, float(w.iloc[0]["open"])))
    return out


def sim(s, e, rows, ppt, stop_pts, arm_f, rung_f, tgt_m):
    stop0 = e - s * stop_pts
    st = stop0
    tgt = e + s * tgt_m * stop_pts if tgt_m else None
    arm = arm_f * stop_pts if arm_f else None
    rung = rung_f * stop_pts
    mfe = 0.0
    for hi, lo, cl in rows:
        if (lo <= st) if s > 0 else (hi >= st):
            return (st - e) * s * ppt - fm.RT_FEE
        if tgt is not None and ((hi >= tgt) if s > 0 else (lo <= tgt)):
            return (tgt - e) * s * ppt - fm.RT_FEE
        fav = (hi - e) if s > 0 else (e - lo)
        if fav > mfe:
            mfe = fav
            if arm is not None and mfe >= arm:
                new = e + s * (math.floor((mfe - arm) / rung) * rung)
                if (s > 0 and new > st) or (s < 0 and new < st):
                    st = new
    return (rows[-1][2] - e) * s * ppt - fm.RT_FEE


def main():
    W = windows()
    out = []
    p = out.append
    combos = [(st, None, 1.0, tg) for st in STOPS for tg in TARGETS] + \
             [(st, ar, ru, tg) for st in STOPS for ar in ARMS if ar for ru in RUNGS for tg in TARGETS]
    p("RATCHET SWEEP — %d combinations per instrument on %d SPY/MES and %d QQQ/MNQ alerts (%s..%s)"
      % (len(combos), sum(1 for a, *_ in W if a["sym"] == "SPY"), sum(1 for a, *_ in W if a["sym"] == "QQQ"),
         min(a["ts"].date() for a, *_ in W), max(a["ts"].date() for a, *_ in W)))
    p("OVERFIT WARNING: the best of %d on this few trades is mostly luck. Trust only what is positive in BOTH halves of the days." % len(combos))
    for sym, label in (("SPY", "MES ($5/pt)"), ("QQQ", "MNQ ($2/pt)")):
        tr = [(a, ppt, rows, e) for a, ppt, rows, e in W if a["sym"] == sym]
        days = sorted({a["ts"].date() for a, *_ in tr})
        mid = days[len(days) // 2]
        scored = []
        for st, ar, ru, tg in combos:
            vals = [(a, sim(1 if a["dirn"] == "L" else -1, e, rows, ppt, st, ar, ru, tg)) for a, ppt, rows, e in tr]
            tot = sum(v for _a, v in vals)
            h1 = sum(v for a, v in vals if a["ts"].date() < mid)
            h2 = tot - h1
            win = 100 * sum(1 for _a, v in vals if v > 0) / len(vals)
            scored.append((tot, h1, h2, win, st, ar, ru, tg))
        scored.sort(key=lambda x: -x[0])
        pos = sum(1 for x in scored if x[0] > 0)
        both = [x for x in scored if x[1] > 0 and x[2] > 0]
        p("\n== %s -> %s — %d alerts, %d days; %d of %d combos positive; %d positive in BOTH halves (split at %s)"
          % (sym, label, len(tr), len(days), pos, len(scored), len(both), mid))
        p("%-8s %-8s %-8s %-8s %8s %8s %8s %6s" % ("stop", "arm", "rung", "target", "total $", "1st half", "2nd half", "win%"))

        def line(x):
            tot, h1, h2, win, st, ar, ru, tg = x
            return "%-8g %-8s %-8s %-8s %+8.0f %+8.0f %+8.0f %5.0f%%" % (
                st, "none" if ar is None else "%gx" % ar, "-" if ar is None else "%gx" % ru,
                "none" if tg is None else "%gx" % tg, tot, h1, h2, win)
        p("TOP 12 by total:")
        for x in scored[:12]:
            p("  " + line(x))
        p("BOTTOM 3:")
        for x in scored[-3:]:
            p("  " + line(x))
        p("BEST that is positive in BOTH halves (top 8):")
        for x in sorted(both, key=lambda x: -min(x[1], x[2]))[:8]:
            p("  " + line(x))
        # what matters: average total by each knob
        for name, idx, keys in (("stop", 4, STOPS), ("arm", 5, ARMS), ("rung", 6, RUNGS), ("target", 7, TARGETS)):
            avg = {k: [x[0] for x in scored if x[idx] == k] for k in keys}
            p("  avg total by %-6s " % name + "  ".join("%s:%+.0f" % ("none" if k is None else "%g" % k, sum(v) / len(v)) for k, v in avg.items() if v))
    txt = "\n".join(out)
    with open(os.path.join(HERE, "RATCHET-SWEEP.txt"), "w", encoding="utf-8") as fh:
        fh.write("Run %s\n%s\n" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M"), txt))
    print(txt)


if __name__ == "__main__":
    main()
