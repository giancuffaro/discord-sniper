#!/usr/bin/env python3
"""stock_futures_mirror_grid.py — every single-name option alert (TSLA, NVDA,
AAPL, ...) taken as ONE CME micro single-stock future instead (10 shares,
$10 per $1 of stock), under a grid of stops and ratchets.

G, 9/18: "to replay yes" — the futures_mirror_grid question, for the names
that have a micro stock future on CME.

BARS ARE THE STOCK'S 1-minute bars (bars/stock_m1, Webull, cached by
trade_trend_label.py), NOT the future's. Webull's futures bars for XTSLA /
XNVDA show single prints hours apart (open interest 260 / 758 on 9/17), so
there is no futures tape to replay and the stock is used as the proxy. A
proxy fill is not a real fill: at those volumes the spread and the wait,
not the stop, decide the trade. MEASUREMENT ONLY. Webull lists these
contracts as status NT (non-tradable) as of 9/18 — nothing here can be
traded there today.

Alerts: master_alerts.csv single-name CALLS = long, PUTS = short, RTH only,
same symbol+direction within 3 minutes is one alert. Market entry on the next
1-minute bar's open, flat on the 15:59 bar, stop checked before target on
every bar (conservative). Stops are a percent of the stock price because the
names range $60-$700. $1.50 round turn assumed.
Output: reference/STOCK-FUTURES-MIRROR-GRID.txt
"""
from __future__ import annotations

import csv
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

import trade_trend_label as ttl                            # noqa: E402

# CME micro single-stock futures listed at Webull (get_futures_products 9/18)
MICROS = {"TSLA": "XTSLA", "NVDA": "XNVDA", "AAPL": "XAAPL", "AMD": "XAMD0", "MSFT": "XMSFT",
          "META": "XMETA", "AMZN": "XAMZN", "GOOGL": "XGOOG", "GOOG": "XGOOG", "MU": "XMU00",
          "PLTR": "XPLTR", "NFLX": "XNFLX", "AVGO": "XAVGO", "SPCX": "XSPCX"}
SHARES = 10.0
RT_FEE = 1.50
STOPS_PCT = (0.25, 0.5, 1.0, 1.5)
MODES = {
    "hard 1:2 bracket, no ratchet": (None, None, 2.0),
    "hard 1:1 bracket, no ratchet": (None, None, 1.0),
    "house ratchet (arm 2/3, rungs 4/15) + 2x target": (5 / 7.5, 2 / 7.5, 2.0),
    "house ratchet, NO target": (5 / 7.5, 2 / 7.5, None),
    "ratchet arm 1x, rungs 1/2, no target": (1.0, 0.5, None),
    "ratchet arm 1/2, rungs 1/4, no target": (0.5, 0.25, None),
}
SINCE = "2026-08-03"
OPEN_MIN, LAST_MIN = 9 * 60 + 30, 15 * 60 + 30
CLOSE_MIN = 15 * 60 + 59
DEDUPE_S = 180
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                                          # noqa: BLE001
    ET = dt.timezone(dt.timedelta(hours=-4))


def alerts():
    rows = []
    with open(os.path.join(ROOT, "master_alerts.csv"), encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            sym = (r.get("symbol") or "").upper()
            side = (r.get("side") or "").upper()
            day = (r.get("date") or "")[:10]
            if sym not in MICROS or not side.startswith(("C", "P")) or len(day) != 10 or day < SINCE:
                continue
            t = (r.get("time") or "")[:5]
            try:
                hh, mm = int(t[:2]), int(t[3:5])
            except ValueError:
                continue
            m = hh * 60 + mm
            if not OPEN_MIN <= m <= LAST_MIN:
                continue
            ts = dt.datetime.combine(dt.date.fromisoformat(day), dt.time(hh, mm), ET)
            rows.append(dict(ts=ts, day=day, sym=sym, dirn="L" if side.startswith("C") else "S",
                             room=r.get("room") or "", caller=r.get("caller") or ""))
    rows.sort(key=lambda r: (r["ts"], r["sym"]))
    keep, last = [], {}
    for r in rows:
        k = (r["sym"], r["dirn"])
        if k in last and (r["ts"] - last[k]).total_seconds() < DEDUPE_S:
            continue
        last[k] = r["ts"]
        keep.append(r)
    return keep


def run(a, bars, stop_pct, arm_frac, step_frac, target_mult):
    s = 1 if a["dirn"] == "L" else -1
    t0 = (a["ts"] + dt.timedelta(minutes=1)).timestamp()
    t_end = a["ts"].replace(hour=15, minute=59).timestamp()
    w = [b for b in bars if t0 <= b[0] <= t_end]
    if not w:
        return None
    e = w[0][1]
    stop_pts = e * stop_pct / 100.0
    stop0 = e - s * stop_pts
    stop = stop0
    tgt = e + s * target_mult * stop_pts if target_mult else None
    arm = arm_frac * stop_pts if arm_frac else None
    step = step_frac * stop_pts if step_frac else None
    mfe, ex, why = 0.0, None, None
    for _ts, _o, hi, lo, _c in w:
        fav = (hi - e) if s > 0 else (e - lo)
        if (lo <= stop) if s > 0 else (hi >= stop):
            ex = stop
            why = "STOP" if abs(stop - stop0) < 1e-9 else ("BE" if abs(stop - e) < 1e-9 else "RATCHET")
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
        ex, why = w[-1][4], "CLOSE"
    pts = (ex - e) * s
    return {"pts": pts, "pct": 100 * pts / e, "usd": pts * SHARES - RT_FEE, "why": why, "mfe_pct": 100 * mfe / e}


def main():
    al = alerts()
    trades, no_bars = [], defaultdict(int)
    cache = {}
    for a in al:
        key = (a["sym"], a["day"])
        if key not in cache:
            cache[key] = ttl.day_bars(a["sym"], a["day"], allow_fetch=True)[0]
        if not cache[key]:
            no_bars[key] += 1
            continue
        trades.append((a, cache[key]))
    out = []
    p = out.append
    p("STOCK FUTURES MIRROR GRID — %d single-name alerts on %d days with stock 1-min bars; %d alerts without bars (%s)"
      % (len(trades), len({a["day"] for a, _ in trades}), sum(no_bars.values()),
         ", ".join("%s %s:%d" % (k[0], k[1], n) for k, n in sorted(no_bars.items())) or "none"))
    p("ONE micro stock future = 10 shares ($10 per $1). BARS ARE THE STOCK'S (proxy) — the futures themselves print a few lots an hour "
      "and are status NT (non-tradable) at Webull on 9/18. Market entry next bar, $1.50 round turn, flat 15:59. Stops in % of the stock price.")
    syms = defaultdict(int)
    for a, _ in trades:
        syms[a["sym"]] += 1
    p("names: " + ", ".join("%s %d" % kv for kv in sorted(syms.items(), key=lambda kv: -kv[1])))
    results = {}
    for stop in STOPS_PCT:
        for mode, (af, sf, tm) in MODES.items():
            res = [(a, run(a, b, stop, af, sf, tm)) for a, b in trades]
            results[(stop, mode)] = [(a, r) for a, r in res if r]
    p("\n%-52s %10s %6s %10s %10s" % ("stop / mode", "all $", "win%", "longs $", "shorts $"))
    for stop in STOPS_PCT:
        for mode in MODES:
            res = results[(stop, mode)]
            usd = [r["usd"] for _a, r in res]
            lg = sum(r["usd"] for a, r in res if a["dirn"] == "L")
            sh = sum(r["usd"] for a, r in res if a["dirn"] == "S")
            p("%-52s %+10.0f %5d%% %+10.0f %+10.0f" % ("%g%% · %s" % (stop, mode), sum(usd),
              round(100 * sum(1 for u in usd if u > 0) / len(usd)), lg, sh))
    best = max(results, key=lambda k: sum(r["usd"] for _a, r in results[k]))
    worst = min(results, key=lambda k: sum(r["usd"] for _a, r in results[k]))
    p("\nBEST cell: %g%% · %s = %+.0f   WORST: %g%% · %s = %+.0f"
      % (best[0], best[1], sum(r["usd"] for _a, r in results[best]), worst[0], worst[1], sum(r["usd"] for _a, r in results[worst])))
    ends = defaultdict(int)
    for _a, r in results[best]:
        ends[r["why"]] += 1
    p("HOW THEY END under the best cell: " + ", ".join("%s %d" % kv for kv in sorted(ends.items(), key=lambda kv: -kv[1])))
    house = results[(0.5, "house ratchet, NO target")]
    p("\nBY NAME under the best cell — and under 0.5% house ratchet, no target")
    by_b, by_h = defaultdict(list), defaultdict(list)
    for a, r in results[best]:
        by_b[a["sym"]].append(r["usd"])
    for a, r in house:
        by_h[a["sym"]].append(r["usd"])
    for name, vals in sorted(by_b.items(), key=lambda kv: -sum(kv[1])):
        p("  %-6s %3d  best %+7.0f (win %2d%%)   house %+7.0f" % (name, len(vals), sum(vals),
          round(100 * sum(1 for v in vals if v > 0) / len(vals)), sum(by_h.get(name, []))))
    p("\nBY CALLER under the best cell (4+ alerts)")
    by_c, by_ch = defaultdict(list), defaultdict(list)
    for a, r in results[best]:
        by_c[(a["caller"] or a["room"] or "?")[:26]].append(r["usd"])
    for a, r in house:
        by_ch[(a["caller"] or a["room"] or "?")[:26]].append(r["usd"])
    for name, vals in sorted(by_c.items(), key=lambda kv: -sum(kv[1])):
        if len(vals) >= 4:
            p("  %-26s %3d  best %+7.0f (win %2d%%)   house %+7.0f" % (name, len(vals), sum(vals),
              round(100 * sum(1 for v in vals if v > 0) / len(vals)), sum(by_ch.get(name, []))))
    p("\nBY TIME OF DAY under the best cell")
    for lo, hi, name in ((9.5, 10, "09:30-10:00"), (10, 11, "10:00-11:00"), (11, 14, "11:00-14:00"), (14, 16, "14:00-16:00")):
        vals = [r["usd"] for a, r in results[best] if lo <= a["ts"].hour + a["ts"].minute / 60 < hi]
        if vals:
            p("  %-12s %3d  %+7.0f  win %2d%%" % (name, len(vals), sum(vals), round(100 * sum(1 for v in vals if v > 0) / len(vals))))
    m = sorted(r["mfe_pct"] for _a, r in house)
    p("\nMFE (best move in favour, %% of stock) — median %.2f%%, 75th %.2f%%; reached 0.5%% on %d%%, 1%% on %d%%, 2%% on %d%%"
      % (m[len(m) // 2], m[int(len(m) * .75)], round(100 * sum(1 for x in m if x >= 0.5) / len(m)),
         round(100 * sum(1 for x in m if x >= 1) / len(m)), round(100 * sum(1 for x in m if x >= 2) / len(m))))
    txt = "\n".join(out)
    with open(os.path.join(HERE, "STOCK-FUTURES-MIRROR-GRID.txt"), "w", encoding="utf-8") as fh:
        fh.write("Run %s ET\n%s\n" % (dt.datetime.now(ET).strftime("%Y-%m-%d %H:%M"), txt))
    print(txt)


if __name__ == "__main__":
    main()
