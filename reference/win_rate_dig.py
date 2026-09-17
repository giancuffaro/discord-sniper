#!/usr/bin/env python3
"""win_rate_dig.py — WHY do round-number pullback entries win 12% of the time?

Same 102 scored alerts as caller_price_window_replay.py (it builds them), same
recorded quote paths, entry = cross the ask at the touch. Each question below
changes ONE thing and re-runs the identical trades. MEASUREMENT ONLY.
"""
from __future__ import annotations

import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import caller_price_window_replay as replay                 # noqa: E402
import ratchet_replay_tape as rr                            # noqa: E402


def sim(r, entry=None, born=None, tiers=None, anticlip=False, floored=False, delay=0.0):
    walk = [q for q in r["path"] if q[0] >= r["t0"] + delay]
    if not walk:
        return None
    keep = rr.BORN_PCT
    if born is not None:
        rr.BORN_PCT = born
    try:
        return rr.simulate(walk, entry if entry is not None else walk[0][2], r["a"]["root"],
                           tiers or rr.TIERS_LIVE, anticlip, floored, r["flat"])
    finally:
        rr.BORN_PCT = keep


def line(label, sims):
    sims = [s for s in sims if s]
    pls = [s["pl"] for s in sims]
    if not pls:
        return "  %-46s none" % label
    wins = sum(1 for p in pls if p > 2)
    scratch = sum(1 for p in pls if -2 <= p <= 2)
    return "  %-46s %3d trades %+7.0f  %+6.1f/trade  win %2d%%  scratch %2d%%  loss %2d%%" % (
        label, len(pls), sum(pls), sum(pls) / len(pls), round(100 * wins / len(pls)),
        round(100 * scratch / len(pls)), round(100 * (len(pls) - wins - scratch) / len(pls)))


def main():
    rows, _why, _n = replay.run()
    base = [sim(r) for r in rows]
    print("WIN-RATE DIG — %d pullback entries, ask at the touch, live ladder "
          "(born -%g%%, arm +%g%% -> breakeven, step %g%%)\n"
          % (len(rows), rr.BORN_PCT, rr.TIERS_LIVE[0][1][0], rr.TIERS_LIVE[0][1][2]))
    print(line("AS LIVE", base))

    print("\n1. HOW THEY END")
    for why in ("born stop", "first lock", "ratchet rung", "close"):
        part = [s for s in base if s and s["why"] == why]
        if part:
            held = statistics.median(s["held_s"] for s in part)
            print("  %-14s %3d (%2d%%)  %+7.0f   median hold %4.0fs"
                  % (why, len(part), round(100 * len(part) / len(base)),
                     sum(s["pl"] for s in part), held))

    print("\n2. WHAT CROSSING THE SPREAD COSTS AGAINST A STOP THAT WATCHES THE BID")
    spreads = [(r["ask"] - r["bid"]) / r["ask"] * 100.0 for r in rows if r["ask"] > 0]
    print("  spread at entry: median %.1f%% of the ask, 75th pct %.1f%%, max %.1f%%"
          % (statistics.median(spreads), sorted(spreads)[int(len(spreads) * .75)], max(spreads)))
    print("  -> the trade is BORN that far under water; the -10%% stop has only "
          "%.1f%% of real room on the median trade" % (10 - statistics.median(spreads)))
    clamped = sum(1 for s in base if s and s["clamped"])
    print("  born stop clamped under the bid by the broker rule on %d of %d" % (clamped, len(base)))

    print("\n3. DID THEY EVER WORK? best bid reached BEFORE the exit, vs the entry ask")
    mfe = [(s["peak_bid"] / r["ask"] - 1) * 100.0 for r, s in zip(rows, base) if s]
    for lvl in (0, 5, 10, 20, 30):
        print("  reached %+3d%% or better: %3d of %d (%d%%)"
              % (lvl, sum(1 for m in mfe if m >= lvl), len(mfe),
                 round(100 * sum(1 for m in mfe if m >= lvl) / len(mfe))))
    # after the stop: where did the contract go in the rest of its recorded window
    later = []
    for r, s in zip(rows, base):
        if s and s["why"] == "born stop":
            rest = [q[1] for q in r["path"] if s["ts"] < q[0] <= r["flat"]]
            if rest:
                later.append((max(rest) / r["ask"] - 1) * 100.0)
    if later:
        print("  AFTER a born stop, the same contract later traded above the ENTRY on %d of %d; "
              "+10%% or better on %d, +20%% on %d"
              % (sum(1 for x in later if x > 0), len(later),
                 sum(1 for x in later if x >= 10), sum(1 for x in later if x >= 20)))

    print("\n4. ONE CHANGE AT A TIME (same trades, same quotes)")
    for born in (15, 20, 30, 50):
        print(line("born stop -%d%% (ladder unchanged)" % born, [sim(r, born=born) for r in rows]))
    print(line("born stop floored to 2x spread / 3 ticks", [sim(r, floored=True) for r in rows]))
    print(line("9/2 price tiers + anti-clip, -10% born", [sim(r, tiers=rr.TIERS_9_2, anticlip=True) for r in rows]))
    print(line("9/2 tiers + anti-clip, born -20%", [sim(r, born=20, tiers=rr.TIERS_9_2, anticlip=True) for r in rows]))
    print(line("enter at the MID instead of the ask (if fillable)", [sim(r, entry=(r["ask"] + r["bid"]) / 2) for r in rows]))
    for d in (30, 60, 120):
        print(line("wait %ds after the touch, then cross" % d, [sim(r, delay=d) for r in rows]))

    print("\n5. NO STOP AT ALL — bid N minutes after entry (the raw quality of the entries)")
    for mins in (2, 5, 10, 20, 40):
        pls = []
        for r in rows:
            at = [q for q in r["path"] if r["t0"] + mins * 60 - 30 <= q[0] <= r["t0"] + mins * 60 + 30]
            if at:
                pls.append((at[0][1] - r["ask"]) * 100.0)
        if pls:
            print("  +%2d min: %3d priced  %+7.0f  %+6.1f/trade  above entry %d%%"
                  % (mins, len(pls), sum(pls), sum(pls) / len(pls),
                     round(100 * sum(1 for p in pls if p > 0) / len(pls))))

    print("\n6. BY PRICE OF THE CONTRACT (as live)")
    for lo, hi in ((0, 1), (1, 2), (2, 4), (4, 99)):
        part = [s for r, s in zip(rows, base) if s and lo <= r["ask"] < hi]
        print(line("ask $%g-%g" % (lo, hi), part))
    print("\n7. BY TIME OF DAY (as live)")
    for lo, hi, name in ((9.5, 10, "09:30-10:00"), (10, 11, "10:00-11:00"), (11, 14, "11:00-14:00"), (14, 16, "14:00-16:00")):
        part = [s for r, s in zip(rows, base) if s and lo <= int(r["a"]["time"][:2]) + int(r["a"]["time"][3:5]) / 60.0 < hi]
        print(line(name, part))
    print("\n8. 0DTE vs LATER EXPIRY (as live)")
    for name, test in (("0DTE", True), ("1+ DTE", False)):
        part = [s for r, s in zip(rows, base)
                if s and (r["a"]["occ"][len(r["a"]["root"]):len(r["a"]["root"]) + 6] == r["a"]["day"][2:].replace("-", "")) == test]
        print(line(name, part))


if __name__ == "__main__":
    main()
