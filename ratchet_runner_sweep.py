"""ratchet_runner_sweep.py — "let winners run": arm to breakeven, then trail WIDE.

The tight ratchet cuts losers well but exits monsters early (SPXW ran +304%,
the live rule sold it at +5%). This tests a different shape on the same 80 fills:
    born  = catastrophic stop before it proves itself (% under entry)
    arm   = gain at which the stop jumps to BREAKEVEN (capital protected)
    wide  = after arming, trail this far BELOW THE PEAK (not tight rungs)
So a name that peaks +304% with wide=25 rides to ~+279% instead of +5%, while a
fader that only pokes +8% still comes out at breakeven.

Read-only. Reuses ratchet_sweep's tape + fills. Writes ratchet_runner_results.csv.
"""
import csv
import os
import re

from ratchet_sweep import load_tape, load_trades, CONTRACT_MULT

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ratchet_runner_results.csv")

BORN = 7.5
ARM = [3.0, 4.0, 5.0, 7.5]
WIDE = [10.0, 15.0, 20.0, 25.0, 30.0, 40.0]

_OCC = re.compile(r"^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")


def lab(o):
    m = _OCC.match(o)
    if not m:
        return o[:18]
    s, yy, mm, dd, cp, k = m.groups()
    return "%s %g%s %d/%d" % (s, int(k) / 1000.0, cp, int(mm), int(dd))


def sim_runner(trade, born, arm, wide):
    entry = trade["entry"]
    stop = entry * (1.0 - born / 100.0)
    peak = -1e9
    armed = False
    for _ts, bid, _ask in trade["quotes"]:
        g = (bid - entry) / entry * 100.0
        peak = max(peak, g)
        if g >= arm:
            armed = True
        if armed:
            wt = entry * (1.0 + (peak - wide) / 100.0)   # trail below peak
            stop = max(stop, entry, wt)                  # never below breakeven
        if bid <= stop:
            return (stop - entry) / entry * 100.0, True
    return (trade["quotes"][-1][1] - entry) / entry * 100.0, False


def score(trades, born, arm, wide):
    tot = 0.0
    wins = 0
    for t in trades:
        rp, _ = sim_runner(t, born, arm, wide)
        tot += (rp / 100.0) * t["entry"] * CONTRACT_MULT
        if rp > 0:
            wins += 1
    n = len(trades)
    return tot, (100.0 * wins / n if n else 0.0)


def main():
    tape = load_tape()
    trades = load_trades(tape)
    print("%d fills · runner shape: born %.1f%%, arm->BE, then trail WIDE below peak\n"
          % (len(trades), BORN))

    rows = []
    for a in ARM:
        for w in WIDE:
            tot, wr = score(trades, BORN, a, w)
            rows.append({"born": BORN, "arm": a, "wide": w,
                         "total": round(tot, 2), "win_pct": round(wr, 1)})
    rows.sort(key=lambda r: -r["total"])

    print("RUNNER TOP 12 (arm to BE / then trail wide below peak):")
    for r in rows[:12]:
        print("  arm +%4.1f%% / trail -%4.1f%% below peak  ->  $%8.2f   win %2.0f%%"
              % (r["arm"], r["wide"], r["total"], r["win_pct"]))

    best = rows[0]
    print("\nbaselines for comparison:")
    print("  tight fine 7.5/4/2 (best tight) ............ $  321")
    print("  tight live 7.5/5/5 (current) ............... $  152")
    print("  runner best (%.0f/BE/-%.0f) ................... $%8.2f"
          % (best["arm"], best["wide"], best["total"]))

    # show what the runner best captures on the biggest movers
    print("\nBIGGEST MOVERS — what the runner best (%.0f/BE/-%.0f) catches vs tight 4/2:"
          % (best["arm"], best["wide"]))
    import ratchet_sweep_fine as rf
    movers = []
    for t in trades:
        gains = [(b - t["entry"]) / t["entry"] * 100 for _s, b, _a in t["quotes"]]
        mfe = max(gains)
        tight, _ = rf.sim(t, 7.5, 4.0, 2.0)
        run, _ = sim_runner(t, BORN, best["arm"], best["wide"])
        movers.append((mfe, lab(t["occ"]), tight, run))
    movers.sort(reverse=True)
    print("  %-16s  peak    tight 4/2   runner" % "contract")
    for mfe, l, tg, rn in movers[:10]:
        print("  %-16s  %+5.0f%%   %+7.0f%%   %+7.0f%%" % (l, mfe, tg, rn))

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\nfull grid -> %s  (same 80-fill / 5-week sample — a lean, not a verdict)"
          % os.path.basename(OUT))


if __name__ == "__main__":
    main()
