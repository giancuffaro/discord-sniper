"""clean_tape.py — despike the backfilled option tape so backtests stop
firing on junk bid prints.

databento_tape.csv holds ~1-second bid/ask for every backfilled contract. It has
isolated bad ticks — a bid that flickers to a fraction of its neighbours for one
print, then recovers (the "-96% low" seen in the mover analysis). Those aren't
tradeable levels; they falsely trigger stops in every ratchet replay. This walks
each contract's series and replaces any bid/ask that deviates hard from its LOCAL
median (a real move persists across ticks and moves the median with it; a bad
tick is a lone spike). Rewrites databento_tape.csv IN PLACE (9/15: one file,
not a raw/clean twin) — timestamps rounded to the millisecond, rows grouped
by contract in time order. databento_backfill.py and option_tape_pull.py run
this after every append, so the file is always the despiked one.

    python3 clean_tape.py
"""
import csv
import os
import statistics as st
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TAPE = os.path.join(HERE, "databento_tape.csv")

WIN = 2          # look ±2 ticks for the local median (5-point window)
LO = 0.4         # bid below 40% of local median = bad drop
HI = 2.5         # bid above 250% of local median = bad spike


def despike(vals):
    """Return (cleaned list, number replaced). Replaces lone spikes with the
    local median; leaves genuine (persistent) moves alone."""
    n = len(vals)
    out = list(vals)
    fixed = 0
    for i in range(n):
        lo = max(0, i - WIN)
        hi = min(n, i + WIN + 1)
        win = [vals[j] for j in range(lo, hi) if j != i]
        if len(win) < 2:
            continue
        med = st.median(win)
        if med <= 0:
            continue
        if vals[i] < LO * med or vals[i] > HI * med:
            out[i] = med
            fixed += 1
    return out, fixed


def main():
    rows = defaultdict(list)   # occ -> [(ts, bid, ask, raw_line_index)]
    order = []
    with open(TAPE, encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            try:
                ts = float(r["ts"])
                b = float(r["bid"])
                a = float(r["ask"])
            except (TypeError, ValueError, KeyError):
                continue
            rows[r["occ"]].append([ts, b, a])

    total = 0
    fixed_bid = 0
    fixed_ask = 0
    contracts = 0
    for occ, series in rows.items():
        series.sort(key=lambda x: x[0])
        bids = [x[1] for x in series]
        asks = [x[2] for x in series]
        cb, fb = despike(bids)
        ca, fa = despike(asks)
        for k in range(len(series)):
            series[k][1] = round(cb[k], 4)
            series[k][2] = round(ca[k], 4)
        total += len(series)
        fixed_bid += fb
        fixed_ask += fa
        contracts += 1

    tmp = "%s.%d.tmp" % (TAPE, os.getpid())
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts", "occ", "bid", "ask"])
        for occ, series in rows.items():
            for ts, b, a in series:
                w.writerow(["%.3f" % ts, occ, b, a])
    os.replace(tmp, TAPE)

    print("cleaned %d contracts, %d ticks" % (contracts, total))
    print("  bad BID ticks replaced: %d  (%.3f%%)"
          % (fixed_bid, 100.0 * fixed_bid / total if total else 0))
    print("  bad ASK ticks replaced: %d  (%.3f%%)"
          % (fixed_ask, 100.0 * fixed_ask / total if total else 0))
    print("rewrote %s in place" % os.path.basename(TAPE))


if __name__ == "__main__":
    main()
