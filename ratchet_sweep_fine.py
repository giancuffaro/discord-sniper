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
    live = next((r for r in allrows if r["born"] == 7.5 and r["arm"] == 5.0
                 and r["step"] == 5.0), None)
    if live:
        print("LIVE 7.5/5/5:  $%.2f  (win %.0f%%)  — rank #%d of %d\n"
              % (live["total"], live["win_pct"],
                 allrows.index(live) + 1, len(allrows)))
    print("GLOBAL TOP 12 (born / arm / step):")
    for r in allrows[:12]:
        print("  -%4.1f%% / +%4.1f%% / +%4.1f%%   ->  $%8.2f   win %2.0f%%"
              % (r["born"], r["arm"], r["step"], r["total"], r["win_pct"]))

    print("\nBEST INSIDE EACH PRICE BUCKET:")
    for name, pred in BUCKETS:
        tb = [t for t in trades if pred(t["entry"])]
        rows = sweep(tb)
        b = rows[0] if rows else None
        flat = next((r for r in rows if r["born"] == 7.5 and r["arm"] == 5.0
                     and r["step"] == 5.0), None)
        if b:
            print("  %-10s n=%2d   best -%4.1f/+%4.1f/+%4.1f = $%8.2f (win %2.0f%%)"
                  "   vs live 7.5/5/5 = $%8.2f"
                  % (name, b["n"], b["born"], b["arm"], b["step"], b["total"],
                     b["win_pct"], flat["total"] if flat else 0.0))

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(allrows[0].keys()))
        w.writeheader()
        w.writerows(allrows)
    print("\nfull %d-row grid -> %s" % (len(allrows), os.path.basename(OUT)))
    print("(same 80-fill / 5-week sample — a lean, not a verdict.)")


if __name__ == "__main__":
    main()
