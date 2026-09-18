#!/usr/bin/env python3
"""futures_mirror_grid.py — every SPY / QQQ alert taken as MES / MNQ instead,
under a grid of stops and ratchets. Which alerts pay, which do not, and for
which callers.

G, 9/18: "suppose every SPY alert and every QQQ alert was entered in futures —
which would have been profitable and which not? Use various ratchet modes:
12.5 stop, 25 stop, 35 stop, 50 pt stop with rungs and all that."

Same alerts and bars as futures_mirror_daily.py (its alerts_for / bars_for /
run are reused, not copied): SPY call = long MES ($5/pt), SPY put = short
MES, QQQ call = long MNQ ($2/pt), QQQ put = short MNQ. Market entry on the
next 1-minute bar's open, one contract, $1.50 round turn, flat 15:59, stop
checked before target on every bar (conservative). Bars: Databento GLBX
8/3–9/12 plus Webull for 9/17 (Webull's futures bars only reach back one
session and G's keys are not subscribed to US_FUTURES data, so 9/15–9/16 have
no bars). MEASUREMENT ONLY. Output: reference/FUTURES-MIRROR-GRID.txt
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

import futures_mirror_daily as fm                           # noqa: E402

STOPS = (12.5, 25.0, 35.0, 50.0)
# name -> (arm_frac, step_frac, target_mult): arm = arm_frac x stop in profit
# moves the stop to breakeven, then every step_frac x stop locks another rung;
# target_mult x stop is a hard take-profit (None = none, the ratchet is the exit)
MODES = {
    "hard 1:2 bracket, no ratchet": (None, None, 2.0),
    "hard 1:1 bracket, no ratchet": (None, None, 1.0),
    "house ratchet (arm 2/3, rungs 4/15) + 2x target": (5 / 7.5, 2 / 7.5, 2.0),
    "house ratchet, NO target": (5 / 7.5, 2 / 7.5, None),
    "ratchet arm 1x, rungs 1/2, no target": (1.0, 0.5, None),
    "ratchet arm 1/2, rungs 1/4, no target": (0.5, 0.25, None),
}


def run(a, bars, stop_pts, arm_frac, step_frac, target_mult):
    root, _micro, ppt = fm.MAP[a["sym"]]
    b = bars[root]
    s = 1 if a["dirn"] == "L" else -1
    t0 = (a["ts"] + dt.timedelta(minutes=1)).replace(second=0, microsecond=0)
    day_end = a["ts"].replace(hour=fm.CLOSE.hour, minute=fm.CLOSE.minute, second=0, microsecond=0)
    w = b[(b.index >= t0) & (b.index <= day_end)]
    if w.empty:
        return None
    e = float(w.iloc[0]["open"])
    stop = e - s * stop_pts
    tgt = e + s * target_mult * stop_pts if target_mult else None
    arm = arm_frac * stop_pts if arm_frac else None
    step = step_frac * stop_pts if step_frac else None
    mfe = 0.0
    ex, why = None, None
    for i in range(len(w)):
        r = w.iloc[i]
        hi, lo = float(r["high"]), float(r["low"])
        fav = (hi - e) if s > 0 else (e - lo)
        if (lo <= stop) if s > 0 else (hi >= stop):
            ex = stop
            why = "STOP" if abs(stop - (e - s * stop_pts)) < 1e-9 else ("BE" if abs(stop - e) < 1e-9 else "RATCHET")
            break
        if tgt is not None and ((hi >= tgt) if s > 0 else (lo <= tgt)):
            ex, why = tgt, "TARGET"
            break
        mfe = max(mfe, fav)
        if arm is not None and mfe >= arm:
            k = math.floor((mfe - arm) / step)
            new = e + s * (k * step)
            if (s > 0 and new > stop) or (s < 0 and new < stop):
                stop = new
    if ex is None:
        ex, why = float(w.iloc[-1]["close"]), "CLOSE"
    pts = (ex - e) * s
    return {"pts": pts, "usd": pts * ppt - fm.RT_FEE, "why": why, "mfe": mfe}


def main():
    days = set()
    for r in fm._read_csv(fm.MASTER):
        if str(r.get("symbol") or "").upper() in fm.MAP and len(str(r.get("date") or "")) == 10:
            days.add(r["date"][:10])
    for r in fm._read_csv(fm.SHADOW):
        if str(r.get("sym") or "").upper() in fm.MAP and len(str(r.get("date") or "")) == 10:
            days.add(r["date"][:10])
    trades, no_bars = [], []
    for day in sorted(d for d in days if d >= fm.SINCE):
        bars, _src = fm.bars_for(day) if all(fm.cached_bars(r, day)[0] is not None for r in ("ES", "NQ")) else (None, "no cached bars")
        alerts = fm.alerts_for(day)
        if bars is None:
            no_bars.append((day, len(alerts)))
            continue
        for a in alerts:
            trades.append((a, bars))
    print("FUTURES MIRROR GRID — %d SPY/QQQ alerts on %d days with ES/NQ bars; %d alerts on %d days WITHOUT bars (%s)"
          % (len(trades), len({a["ts"].date() for a, _ in trades}), sum(n for _d, n in no_bars), len(no_bars),
             ", ".join("%s:%d" % x for x in no_bars)))
    print("SPY -> MES $5/pt, QQQ -> MNQ $2/pt, 1 contract, market entry next bar, $1.50 round turn, flat 15:59")
    results = {}
    for stop in STOPS:
        for mode, (af, sf, tm) in MODES.items():
            res = [(a, run(a, bars, stop, af, sf, tm)) for a, bars in trades]
            res = [(a, r) for a, r in res if r]
            results[(stop, mode)] = res
    print("\n%-50s" % "stop / mode" + "".join("%15s" % h for h in ("all $", "win%", "SPY/MES $", "QQQ/MNQ $")))
    for stop in STOPS:
        for mode in MODES:
            res = results[(stop, mode)]
            usd = [r["usd"] for _a, r in res]
            spy = sum(r["usd"] for a, r in res if a["sym"] == "SPY")
            qqq = sum(r["usd"] for a, r in res if a["sym"] == "QQQ")
            print("%-50s %14s %14s %14s %14s" % ("%g pt · %s" % (stop, mode), "%+.0f" % sum(usd),
                  "%d%%" % round(100 * sum(1 for u in usd if u > 0) / len(usd)), "%+.0f" % spy, "%+.0f" % qqq))
    best = max(results, key=lambda k: sum(r["usd"] for _a, r in results[k]))
    worst = min(results, key=lambda k: sum(r["usd"] for _a, r in results[k]))
    print("\nBEST cell: %g pt · %s = %+.0f   WORST: %g pt · %s = %+.0f"
          % (best[0], best[1], sum(r["usd"] for _a, r in results[best]),
             worst[0], worst[1], sum(r["usd"] for _a, r in results[worst])))
    print("\nHOW THEY END under the best cell: " + ", ".join(
        "%s %d" % kv for kv in sorted(defaultdict(int, {}).items())) if False else "")
    ends = defaultdict(int)
    for _a, r in results[best]:
        ends[r["why"]] += 1
    print("HOW THEY END under the best cell: " + ", ".join("%s %d" % kv for kv in sorted(ends.items(), key=lambda kv: -kv[1])))

    print("\nBY CALLER under the best cell (4+ alerts) — and under the live 25-pt house rule")
    house = results[(25.0, "house ratchet (arm 2/3, rungs 4/15) + 2x target")]
    by_best, by_house = defaultdict(list), defaultdict(list)
    for a, r in results[best]:
        by_best[(a["caller"] or a["room"] or "?")[:26]].append(r["usd"])
    for a, r in house:
        by_house[(a["caller"] or a["room"] or "?")[:26]].append(r["usd"])
    for name, vals in sorted(by_best.items(), key=lambda kv: -sum(kv[1])):
        if len(vals) >= 4:
            h = by_house.get(name, [])
            print("  %-26s %3d  best %+6.0f (win %2d%%)   house 25pt %+6.0f"
                  % (name, len(vals), sum(vals), round(100 * sum(1 for v in vals if v > 0) / len(vals)), sum(h)))
    print("\nBY TIME OF DAY under the best cell")
    for lo, hi, name in ((9.5, 10, "09:30-10:00"), (10, 11, "10:00-11:00"), (11, 14, "11:00-14:00"), (14, 16, "14:00-16:00")):
        vals = [r["usd"] for a, r in results[best] if lo <= a["ts"].hour + a["ts"].minute / 60 < hi]
        if vals:
            print("  %-12s %3d  %+6.0f  win %2d%%" % (name, len(vals), sum(vals), round(100 * sum(1 for v in vals if v > 0) / len(vals))))
    print("\nMFE (best move in the trade's favour, points) — median %.1f, 75th %.1f; reached 12.5 pts on %d%%, 25 on %d%%, 50 on %d%%"
          % (sorted(r["mfe"] for _a, r in house)[len(house) // 2], sorted(r["mfe"] for _a, r in house)[int(len(house) * .75)],
             round(100 * sum(1 for _a, r in house if r["mfe"] >= 12.5) / len(house)),
             round(100 * sum(1 for _a, r in house if r["mfe"] >= 25) / len(house)),
             round(100 * sum(1 for _a, r in house if r["mfe"] >= 50) / len(house))))


if __name__ == "__main__":
    main()
