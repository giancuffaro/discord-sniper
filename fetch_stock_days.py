#!/usr/bin/env python3
"""fetch_stock_days.py — pull the 1-minute stock bars for every symbol-day in
bars/stock_m1_wanted.txt into bars/stock_m1/ (trade_trend_label.day_bars does
the call and the cache; Webull stock history is free on the bridge keys, one
call a second). Run on the Hulk, off-hours. Reruns skip what is cached."""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import trade_trend_label as ttl

want = [l.split() for l in open(os.path.join(HERE, "bars", "stock_m1_wanted.txt")) if l.strip()]
done = fail = 0
t0 = time.time()
for sym, day in want:
    if os.path.exists(os.path.join(ttl.M1_DIR, "%s_%s.csv" % (sym, day))):
        continue
    bars, src = ttl.day_bars(sym, day, allow_fetch=True)
    done += 1
    if not bars:
        fail += 1
    if done % 50 == 0:
        print("%d fetched, %d empty, %.0fs" % (done, fail, time.time() - t0), flush=True)
print("DONE %d fetched, %d empty, %.0fs" % (done, fail, time.time() - t0), flush=True)
