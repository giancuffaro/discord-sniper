#!/usr/bin/env python3
"""trend_predict_test.py — does trend.py's label PREDICT anything?

G, 9/17: "yes do the test, and do 5 15 30 45 and 1 hour after … I also think
sometimes a new trend direction starts at round-number hours and more often at
round-number prices ending in 5 or 0, and combined."

PART 1 — PREDICTION. Every 5 minutes from 09:45 to 15:00, on every symbol-day,
read the label from bars that had already CLOSED, then look at the stock 5 /
15 / 30 / 45 / 60 minutes later. For UP the forward move should be positive,
for DOWN negative; "with-label move" = the forward move signed that way, in
basis points (1 bp = 0.01%). Baseline = the same forward move with no label.
Also split by the label's AGE (minutes since it last changed) — a fresh trend
and a mature one are different bets. Significance is by DAY, not by sample:
samples 5 minutes apart on one day are the same tape, so each day contributes
ONE number (its mean) and t = mean / (sd / sqrt(days)).

PART 2 — WHERE TURNS HAPPEN. Swing pivots (trend.swings) on the whole day, at
the normal reversal size and at 2x (bigger turns). For each pivot: minutes
from the nearest top of the hour / half hour, and distance from the nearest
price ending in 5 or 0 (a multiple of $5) and the nearest whole dollar. The
comparison is never "uniform": it is EVERY one-minute bar's own extreme on the
same days, so a stock that simply spends time near $760 does not count as
evidence.

Data: trade_trend_label.day_bars — our 1-second files where they exist, else
Webull's free 1-minute history by date, cached. MEASUREMENT ONLY.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import trade_trend_label as ttl                             # noqa: E402
import trend                                                # noqa: E402

SYMBOLS = ("SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "META", "AMZN", "AMD", "GOOGL")
LAST_DAY = dt.date(2026, 9, 16)
N_DAYS = 60
HORIZONS = (5, 15, 30, 45, 60)
ET = ttl.ET


def trading_days():
    days, d = [], LAST_DAY
    while len(days) < N_DAYS:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= dt.timedelta(days=1)
    return days


def minute_of_day(ts):
    t = dt.datetime.fromtimestamp(ts, ET)
    return t.hour * 60 + t.minute


def tstat(values):
    if len(values) < 3:
        return 0.0
    sd = statistics.pstdev(values)
    return 0.0 if sd == 0 else statistics.mean(values) / (sd / math.sqrt(len(values)))


def part1(days_bars):
    # cell -> horizon -> day -> [signed bp]
    cells = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    counts = defaultdict(int)
    for (sym, day), bars in days_bars.items():
        rth = [b for b in bars if 570 <= minute_of_day(b[0]) < 960]
        if len(rth) < 300:
            continue
        idx = {minute_of_day(b[0]): i for i, b in enumerate(rth)}
        last_label, since = None, None
        for m in range(585, 901, 5):                       # 09:45 .. 15:00
            if m - 1 not in idx:
                continue
            i = idx[m - 1]                                  # last CLOSED bar
            label = trend.read(rth[:i + 1])["label"]
            if label != last_label:
                last_label, since = label, m
            age = m - since
            px = rth[i][4]
            counts[label] += 1
            for h in HORIZONS:
                j = idx.get(m - 1 + h)
                if j is None:
                    continue
                fwd = (rth[j][4] / px - 1) * 1e4
                cells["ALL (no label)"][h][(sym, day)].append(fwd)
                if label in ("UP", "DOWN"):
                    signed = fwd if label == "UP" else -fwd
                    cells[label][h][(sym, day)].append(signed)
                    cells["UP+DOWN"][h][(sym, day)].append(signed)
                    bucket = "fresh <15m" if age < 15 else "15-45m" if age < 45 else "mature 45m+"
                    cells["  age " + bucket][h][(sym, day)].append(signed)
                else:
                    cells["CHOP (abs move)"][h][(sym, day)].append(abs(fwd))
    return cells, counts


def part2(days_bars):
    out = {}
    for mult in (1.0, 2.0):
        by_hour = {"turn": defaultdict(int), "bar": defaultdict(int)}
        piv_clock, base_clock = defaultdict(int), defaultdict(int)
        near = {"piv": defaultdict(int), "base": defaultdict(int)}
        n_piv = n_base = both_p = both_b = 0
        for (sym, day), bars in days_bars.items():
            rth = [b for b in bars if 570 <= minute_of_day(b[0]) < 960]
            if len(rth) < 300:
                continue
            rev = trend.reversal_size(rth) * mult
            band = max(0.10, rth[0][4] * 0.0002)            # 2 bp of price, min 10c
            # The session's first minutes are excluded on BOTH sides: a zigzag's
            # first pivot is nearly always the opening extreme, which would
            # "prove" that turns cluster at :30 when it is only the 9:30 bell.
            pivots = [p for p in trend.swings(rth, rev)
                      if p[2] in ("H", "L") and minute_of_day(p[0]) >= 580]
            rth = [b for b in rth if minute_of_day(b[0]) >= 580]
            for p_ts, _pp, _k in pivots:
                by_hour["turn"][minute_of_day(p_ts) // 30] += 1
            for b in rth:
                by_hour["bar"][minute_of_day(b[0]) // 30] += 2

            def flags(ts, price):
                mod = minute_of_day(ts) % 60
                hour = min(mod, 60 - mod) <= 2
                half = abs(mod - 30) <= 2
                five = abs(price - round(price / 5.0) * 5.0) <= band
                one = abs(price - round(price)) <= band
                return hour, half, five, one

            for ts, price, _k in pivots:
                hour, half, five, one = flags(ts, price)
                n_piv += 1
                piv_clock["hour"] += hour
                piv_clock["half"] += half
                near["piv"]["five"] += five
                near["piv"]["one"] += one
                both_p += (hour and five)
            for b in rth:
                for price in (b[2], b[3]):
                    hour, half, five, one = flags(b[0], price)
                    n_base += 1
                    base_clock["hour"] += hour
                    base_clock["half"] += half
                    near["base"]["five"] += five
                    near["base"]["one"] += one
                    both_b += (hour and five)
        out[mult] = (n_piv, n_base, piv_clock, base_clock, near, both_p, both_b, by_hour)
    return out


def main():
    days_bars = {}
    for day in trading_days():
        for sym in SYMBOLS:
            bars, _src = ttl.day_bars(sym, day, "--no-fetch" not in sys.argv[1:])
            if bars:
                days_bars[(sym, day)] = bars
    used = sorted({d for _s, d in days_bars})
    print("TREND PREDICTION TEST — %d symbol-days, %d sessions %s .. %s, %d symbols"
          % (len(days_bars), len(used), used[0], used[-1], len(SYMBOLS)))

    cells, counts = part1(days_bars)
    total = sum(counts.values())
    print("\nlabels read: " + "  ".join("%s %d (%d%%)" % (k, v, round(100 * v / total))
                                       for k, v in sorted(counts.items())))
    print("\nPART 1 — forward move WITH the label, basis points (1bp = 0.01%%; SPY $760 -> 1bp = 7.6c)")
    print("  %-18s" % "" + "".join("%18s" % ("+%d min" % h) for h in HORIZONS))
    for name in ("ALL (no label)", "UP", "DOWN", "UP+DOWN", "  age fresh <15m", "  age 15-45m",
                 "  age mature 45m+", "CHOP (abs move)"):
        row = "  %-18s" % name
        for h in HORIZONS:
            per_day = [statistics.mean(v) for v in cells[name][h].values() if v]
            flat = [x for v in cells[name][h].values() for x in v]
            if not flat:
                row += "%18s" % "-"
                continue
            hit = 100.0 * sum(1 for x in flat if x > 0) / len(flat)
            row += "%18s" % ("%+.1fbp %2.0f%% t%+.1f" % (statistics.mean(flat), hit, tstat(per_day)))
        print(row)
    print("  (each cell: mean move, %% of samples that went the label's way, t-stat across symbol-days; |t| under 2 = noise)")

    print("\nPART 2 — where swing turns happen, vs where every 1-minute extreme happens")
    for mult, (n_piv, n_base, pc, bc, near, both_p, both_b, by_hour) in part2(days_bars).items():
        print("\n  reversal x%g — %d turns" % (mult, n_piv))
        for label, p, b in (("within 2 min of the top of the hour", pc["hour"], bc["hour"]),
                            ("within 2 min of the half hour", pc["half"], bc["half"]),
                            ("at a price ending in 5 or 0 (multiple of $5)", near["piv"]["five"], near["base"]["five"]),
                            ("at a whole dollar", near["piv"]["one"], near["base"]["one"]),
                            ("BOTH top of the hour AND a 5/0 price", both_p, both_b)):
            fp, fb = 100.0 * p / n_piv, 100.0 * b / n_base
            # binomial z against the baseline rate
            se = math.sqrt(fb / 100 * (1 - fb / 100) / n_piv) * 100 if n_piv else 0
            z = (fp - fb) / se if se else 0.0
            print("    %-48s turns %5.1f%%   all bars %5.1f%%   lift x%.2f   z %+.1f"
                  % (label, fp, fb, (fp / fb) if fb else 0, z))
        tt, tb = sum(by_hour["turn"].values()), sum(by_hour["bar"].values())
        print("    turns per half-hour slot vs that slot's share of the tape (x1.00 = no more turns than time spent):")
        print("      " + "  ".join("%02d:%02d x%.2f" % (k // 2, (k % 2) * 30,
                                   (by_hour["turn"][k] / tt) / (by_hour["bar"][k] / tb))
                                   for k in sorted(by_hour["bar"]) if by_hour["bar"][k]))
    print("  (z over ~3 = real; the 10:00 hour carries scheduled data releases, so 'top of the hour' is partly the calendar)")


if __name__ == "__main__":
    main()
