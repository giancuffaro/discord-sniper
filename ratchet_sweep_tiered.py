"""ratchet_sweep_tiered.py — does spacing by CONTRACT PRICE beat one flat ladder?

ratchet_sweep.py swept a SINGLE (born, arm) applied to every trade and picked
7.5/5 as best overall. But +5% on a $0.30 contract is barely a tick — G's
point: cheap contracts need a looser stop or they get shaken out on noise.
This buckets the SAME real fills by entry price and finds the best (born, arm)
WITHIN each bucket, then compares a per-price tiered ladder to the flat 7.5/5.

Honest limits: same ~80-fill, 5-week sample as the flat sweep; the "best per
bucket" is picked IN-SAMPLE (optimistic — it can overfit a small bucket), so
treat a bucket with few trades as a hint, not a rule. Read-only; writes
ratchet_tiered_results.csv.
"""
import csv
import os

from ratchet_sweep import load_tape, load_trades, simulate_one, CONTRACT_MULT

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ratchet_tiered_results.csv")

BUCKETS = [
    ("cheap  <$1.00", lambda p: p < 1.0),
    ("mid    $1-1.99", lambda p: 1.0 <= p < 2.0),
    ("exp    >=$2.00", lambda p: p >= 2.0),
]

BORN = [5.0, 7.5, 10.0, 12.5, 15.0, 20.0, 25.0]
ARM = [3.0, 5.0, 7.5, 10.0, 12.5, 15.0, 20.0, 25.0]


def score(trades, born, arm):
    tot = 0.0
    wins = 0
    res = 0
    for t in trades:
        rp, st = simulate_one(t, born, arm)
        tot += (rp / 100.0) * t["entry"] * CONTRACT_MULT
        if rp > 0:
            wins += 1
        if st:
            res += 1
    n = len(trades)
    return tot, (100.0 * wins / n if n else 0.0), res, n


def main():
    tape = load_tape()
    trades = load_trades(tape)
    print("total room-call trades: %d\n" % len(trades))

    rows = []
    flat_total = 0.0
    tiered_total = 0.0
    print("%-15s  n   flat 7.5/5        best in bucket           best $   flat $"
          % "bucket")
    print("-" * 82)
    for name, pred in BUCKETS:
        tb = [t for t in trades if pred(t["entry"])]
        ft, fw, fr, fn = score(tb, 7.5, 5.0)
        flat_total += ft
        best = None
        for b in BORN:
            for a in ARM:
                tot, wr, res, n = score(tb, b, a)
                rows.append({"bucket": name, "born": b, "arm": a,
                             "total": round(tot, 2), "win_pct": round(wr, 1),
                             "n": n})
                if best is None or tot > best["total"]:
                    best = {"born": b, "arm": a, "total": tot, "win": wr}
        if tb:
            tiered_total += best["total"]
        print("%-15s %3d   $%8.2f (%3.0f%%)   -%4.1f%% born / +%4.1f%% arm   $%8.2f  %+8.2f"
              % (name, len(tb), ft, fw,
                 (best["born"] if tb else 0), (best["arm"] if tb else 0),
                 (best["total"] if tb else 0.0),
                 ((best["total"] - ft) if tb else 0.0)))

    print("-" * 82)
    print("FLAT 7.5/5 everywhere (the live rule):   $%8.2f" % flat_total)
    print("TIERED best-per-bucket (in-sample):      $%8.2f" % tiered_total)
    print("gap the flat ladder leaves on the table: $%8.2f" % (tiered_total - flat_total))
    print("\n(the tiered number is optimistic — best cell picked in-sample per"
          "\n bucket. The honest read is the per-bucket 'best arm': if cheap"
          "\n wants a much wider arm than +5%, that is the real signal.)")

    rows.sort(key=lambda r: (r["bucket"], -r["total"]))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\nfull per-bucket grid -> %s" % os.path.basename(OUT))


if __name__ == "__main__":
    main()
