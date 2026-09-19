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
SINCE_YEAR = "2025-09-18"          # the grabbed year; the daily mirror's own SINCE is the honest-sim era

# a number = the same points on ES and NQ; a dict = per root (G, 9/18: "MNQ 12.5, MES 7.5")
STOPS = ({"ES": 7.5, "NQ": 12.5}, 12.5, 25.0, 35.0, 50.0)


def _stop_for(stop, root):
    return stop[root] if isinstance(stop, dict) else stop


def _stop_name(stop):
    return "ES %g / NQ %g pt" % (stop["ES"], stop["NQ"]) if isinstance(stop, dict) else "%g pt" % stop
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
    # G, 9/18: "-12.5 stop, +12.5 stop to break even, +25 stop to +12.5, and so on"
    "G ladder: arm 1x, rungs 1x, no target": (1.0, 1.0, None),
}


def run(a, bars, stop_pts, arm_frac, step_frac, target_mult):
    """One alert under one stop/ratchet/target, through the ONE honest
    simulator (futures_ratchet_sweep.sim, fixes #1 and #2 of 9/19). The loop
    that used to live here credited the fill bar and ratcheted on the same bar
    it tested; its numbers (FUTURES-MIRROR-GRID.txt before 9/19) were void."""
    import futures_ratchet_sweep as rs
    root, _micro, ppt = fm.MAP[a["sym"]]
    stop_pts = _stop_for(stop_pts, root)
    b = bars[root]
    s = 1 if a["dirn"] == "L" else -1
    t0 = (a["ts"] + dt.timedelta(minutes=1)).replace(second=0, microsecond=0)
    day_end = a["ts"].replace(hour=fm.CLOSE.hour, minute=fm.CLOSE.minute, second=0, microsecond=0)
    w = b[(b.index >= t0) & (b.index <= day_end)]
    if w.empty:
        return None
    e = float(w.iloc[0]["open"])
    rows = list(zip(w["high"].astype(float), w["low"].astype(float), w["close"].astype(float)))
    usd = rs.sim(s, e, rows, ppt, stop_pts, arm_frac, step_frac or 1.0, target_mult)
    mfe = max([0.0] + [((h - e) if s > 0 else (e - l)) for h, l, _c in rows[1:]])
    why = "STOP" if usd < -0.5 * stop_pts * ppt else ("TARGET" if target_mult and usd > 0.9 * target_mult * stop_pts * ppt else "OTHER")
    return {"pts": usd / ppt, "usd": usd, "why": why, "mfe": mfe}


def main():
    days = set()
    for r in fm._read_csv(fm.MASTER):
        if str(r.get("symbol") or "").upper() in fm.MAP and len(str(r.get("date") or "")) == 10:
            days.add(r["date"][:10])
    for r in fm._read_csv(fm.SHADOW):
        if str(r.get("sym") or "").upper() in fm.MAP and len(str(r.get("date") or "")) == 10:
            days.add(r["date"][:10])
    trades, no_bars = [], []
    for day in sorted(d for d in days if d >= SINCE_YEAR):
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
            results[(STOPS.index(stop), mode)] = res
    print("\n%-50s" % "stop / mode" + "".join("%15s" % h for h in ("all $", "win%", "SPY/MES $", "QQQ/MNQ $")))
    for stop in STOPS:
        for mode in MODES:
            res = results[(STOPS.index(stop), mode)]
            usd = [r["usd"] for _a, r in res]
            spy = sum(r["usd"] for a, r in res if a["sym"] == "SPY")
            qqq = sum(r["usd"] for a, r in res if a["sym"] == "QQQ")
            print("%-50s %14s %14s %14s %14s" % ("%s · %s" % (_stop_name(stop), mode), "%+.0f" % sum(usd),
                  "%d%%" % round(100 * sum(1 for u in usd if u > 0) / len(usd)), "%+.0f" % spy, "%+.0f" % qqq))
    best = max(results, key=lambda k: sum(r["usd"] for _a, r in results[k]))
    worst = min(results, key=lambda k: sum(r["usd"] for _a, r in results[k]))
    print("\nBEST cell: %s · %s = %+.0f   WORST: %s · %s = %+.0f"
          % (_stop_name(STOPS[best[0]]), best[1], sum(r["usd"] for _a, r in results[best]),
             _stop_name(STOPS[worst[0]]), worst[1], sum(r["usd"] for _a, r in results[worst])))
    print("\nHOW THEY END under the best cell: " + ", ".join(
        "%s %d" % kv for kv in sorted(defaultdict(int, {}).items())) if False else "")
    ends = defaultdict(int)
    for _a, r in results[best]:
        ends[r["why"]] += 1
    print("HOW THEY END under the best cell: " + ", ".join("%s %d" % kv for kv in sorted(ends.items(), key=lambda kv: -kv[1])))

    print("\nBY CALLER under the best cell (4+ alerts) — and under the live 25-pt house rule")
    house = results[(STOPS.index(25.0), "house ratchet (arm 2/3, rungs 4/15) + 2x target")]
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
