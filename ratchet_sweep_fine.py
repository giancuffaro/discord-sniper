"""ratchet_sweep_fine.py — a wider, finer ratchet sweep, with the RUNG decoupled.

ratchet_sweep.py tied the rung size to the arm (step == arm) and used a coarse
grid. This sweeps three independent knobs on the same 80 real fills:
    born  = where the stop starts (% under entry)
    arm   = gain at which the stop jumps to breakeven
    step  = how much MORE it locks for every further `step` of gain
and reports the best globally and inside each price bucket.

Read-only. Reuses ratchet_sweep's tape + fills + contract multiplier.
Writes ratchet_fine_results.csv (full grid).
"""
import csv
import os

from ratchet_sweep import load_tape, load_trades, CONTRACT_MULT
from ratchet_tiers import live_spacing

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ratchet_fine_results.csv")

BORN = [5.0, 6.0, 7.5, 9.0, 10.0, 12.5, 15.0]
ARM = [2.0, 3.0, 4.0, 5.0, 6.0, 7.5, 10.0]
STEP = [2.0, 3.0, 4.0, 5.0, 7.5, 10.0]

BUCKETS = [
    ("cheap <$1", lambda p: p < 1.0),
    ("mid $1-2", lambda p: 1.0 <= p < 2.0),
    ("exp >=$2", lambda p: p >= 2.0),
]


def locked_pct(gain, arm, step):
    if gain < arm - 1e-9:
        return None
    k = int((gain - arm + 1e-9) // step)
    return 0.0 + step * k


def sim(trade, born, arm, step):
    entry = trade["entry"]
    stop = entry * (1.0 - born / 100.0)
    for _ts, bid, _ask in trade["quotes"]:
        gain = (bid - entry) / entry * 100.0
        lk = locked_pct(gain, arm, step)
        if lk is not None:
            stop = max(stop, entry * (1.0 + lk / 100.0))
        if bid <= stop:
            return (stop - entry) / entry * 100.0, True
    last = trade["quotes"][-1][1]
    return (last - entry) / entry * 100.0, False


def score(trades, born, arm, step):
    tot = 0.0
    wins = 0
    for t in trades:
        rp, _ = sim(t, born, arm, step)
        tot += (rp / 100.0) * t["entry"] * CONTRACT_MULT
        if rp > 0:
            wins += 1
    n = len(trades)
    return tot, (100.0 * wins / n if n else 0.0), n


def sweep(trades):
    out = []
    for b in BORN:
        for a in ARM:
            for s in STEP:
                tot, wr, n = score(trades, b, a, s)
                out.append({"born": b, "arm": a, "step": s,
                            "total": round(tot, 2), "win_pct": round(wr, 1),
                            "n": n})
    out.sort(key=lambda r: -r["total"])
    return out


def main():
    tape = load_tape()
    trades = load_trades(tape)
    print("%d fills · grid %d combos (born %d × arm %d × step %d)\n"
          % (len(trades), len(BORN) * len(ARM) * len(STEP),
             len(BORN), len(ARM), len(STEP)))

    allrows = sweep(trades)
    # 9/10: LIVE is READ from the live files, never typed here. This line
    # said 7.5/5/5 for two days while the real rung was 2 — a hardcoded
    # "current" number drifts the moment the real one moves, and then every
    # comparison in this report is against a rule nobody is running.
    lb, la, ls = live_spacing()
    live = next((r for r in allrows if r["born"] == lb and r["arm"] == la
                 and r["step"] == ls), None)
    if live:
        print("LIVE %g/%g/%g:  $%.2f  (win %.0f%%)  — rank #%d of %d\n"
              % (lb, la, ls, live["total"], live["win_pct"],
                 allrows.index(live) + 1, len(allrows)))
    else:
        print("LIVE %g/%g/%g is not on this grid.\n" % (lb, la, ls))
    print("GLOBAL TOP 12 (born / arm / step):")
    for r in allrows[:12]:
        print("  -%4.1f%% / +%4.1f%% / +%4.1f%%   ->  $%8.2f   win %2.0f%%"
              % (r["born"], r["arm"], r["step"], r["total"], r["win_pct"]))

    print("\nBEST INSIDE EACH PRICE BUCKET:")
    for name, pred in BUCKETS:
        tb = [t for t in trades if pred(t["entry"])]
        rows = sweep(tb)
        b = rows[0] if rows else None
        flat = next((r for r in rows if r["born"] == lb and r["arm"] == la
                     and r["step"] == ls), None)
        if b:
            print("  %-10s n=%2d   best -%4.1f/+%4.1f/+%4.1f = $%8.2f (win %2.0f%%)"
                  "   vs live %g/%g/%g = $%8.2f"
                  % (name, b["n"], b["born"], b["arm"], b["step"], b["total"],
                     b["win_pct"], lb, la, ls, flat["total"] if flat else 0.0))

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(allrows[0].keys()))
        w.writeheader()
        w.writerows(allrows)
    print("\nfull %d-row grid -> %s" % (len(allrows), os.path.basename(OUT)))

    # DOES THE WINNER CLEAR ITS OWN ERROR BAR? Paired difference per trade
    # (grid best minus live on the SAME trade), bootstrapped 2000x. A grid
    # this wide will always produce a top row; this is what says whether
    # the top row is an edge or the luckiest cell in 294 tries.
    import random
    top = allrows[0]
    diffs = [(sim(t, top["born"], top["arm"], top["step"])[0]
              - sim(t, lb, la, ls)[0]) / 100.0 * t["entry"] * CONTRACT_MULT
             for t in trades]
    rnd = random.Random(7)
    means = sorted(sum(rnd.choice(diffs) for _ in diffs) / len(diffs)
                   for _ in range(2000))
    print("best -%g/+%g/+%g minus live: $%+.2f a trade, 95%% band $%+.2f..$%+.2f -> %s"
          % (top["born"], top["arm"], top["step"], sum(diffs) / len(diffs),
             means[50], means[1949],
             "REAL" if means[50] > 0 or means[1949] < 0 else "INSIDE THE NOISE"))
    print("(%d fills, ~13 weeks of real OPRA tape — a lean, not a verdict.)" % len(trades))


if __name__ == "__main__":
    main()
