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
import sys

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


def sim(trade, born, arm, step, pause_sec=0.0, pause_cents=0.0):
    """Replay one trade's real tape under a stop rule.

    THE TWO PAUSES (9/10, G: "waiting 10 seconds before it could start the
    rung, or wait for it to move 25 or 50 cents in favour — some sort of
    pause to give the trade time to run"). Both gate ONLY the ratchet, never
    the born stop: the protective stop is live from the first tick either
    way, so a pause can never make a trade lose more than born allows. What
    it delays is the stop being RAISED — the thing that scratches a trade
    at breakeven before it has moved.
      pause_sec   — the ratchet stays asleep for N seconds after entry.
      pause_cents — the ratchet stays asleep until the bid is at least this
                    many dollars above entry. NOTE this is deliberately NOT
                    a percentage: it is flat money, so it bites hard on a
                    $0.34 contract (25c = +73%) and barely at all on a $5
                    one (25c = +5%). That asymmetry is the whole question.
    """
    entry = trade["entry"]
    stop = entry * (1.0 - born / 100.0)
    t0 = trade["quotes"][0][0]
    for _ts, bid, _ask in trade["quotes"]:
        awake = (_ts - t0 >= pause_sec) and (bid - entry >= pause_cents)
        if awake:
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


def pause_study(trades):
    """Does giving the trade room before the ratchet wakes up pay? (9/10)"""
    import statistics
    lb, la, ls = live_spacing()

    def score(pause_sec, pause_cents, spacing=None):
        b, a, st = spacing or (lb, la, ls)
        tot = 0.0
        wins = 0
        for t in trades:
            rp, _ = sim(t, b, a, st, pause_sec, pause_cents)
            tot += (rp / 100.0) * t["entry"] * CONTRACT_MULT
            if rp > 0:
                wins += 1
        return tot, 100.0 * wins / len(trades)

    base, base_wr = score(0, 0)
    print("PAUSE STUDY — live spacing %g/%g/%g, %d trades" % (lb, la, ls, len(trades)))
    print("baseline, no pause: $%+.2f  (win %.0f%%)\n" % (base, base_wr))

    print("A. TIME PAUSE — ratchet asleep for N seconds after entry")
    print("   %8s %10s %8s %10s" % ("seconds", "total $", "win%", "vs base"))
    for s in [0, 5, 10, 20, 30, 60, 120, 300, 600]:
        tot, wr = score(s, 0)
        print("   %8d %10.2f %7.0f%% %+10.2f" % (s, tot, wr, tot - base))

    print("\nB. MONEY PAUSE — ratchet asleep until the bid is +$X over entry")
    print("   %8s %10s %8s %10s" % ("dollars", "total $", "win%", "vs base"))
    for c in [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.35, 0.50, 0.75, 1.00]:
        tot, wr = score(0, c)
        print("   %8.2f %10.2f %7.0f%% %+10.2f" % (c, tot, wr, tot - base))

    print("\nC. BOTH — best time pause x best money pause")
    best = None
    for s in [0, 10, 30, 60, 120, 300]:
        row = []
        for c in [0.0, 0.10, 0.25, 0.50]:
            tot, _wr = score(s, c)
            row.append(tot)
            if best is None or tot > best[0]:
                best = (tot, s, c)
        print("   %4ds  " % s + "  ".join("%9.2f" % v for v in row))
    print("   (columns: +$0.00, +$0.10, +$0.25, +$0.50)")
    print("\n   BEST COMBO: %ds pause + $%.2f pause -> $%+.2f  (vs base $%+.2f, %+.2f)"
          % (best[1], best[2], best[0], base, best[0] - base))

    # IS IT REAL? paired bootstrap, same trades, against no pause.
    import random
    diffs = [(sim(t, lb, la, ls, best[1], best[2])[0] - sim(t, lb, la, ls)[0])
             / 100.0 * t["entry"] * CONTRACT_MULT for t in trades]
    rnd = random.Random(7)
    means = sorted(sum(rnd.choice(diffs) for _ in diffs) / len(diffs) for _ in range(2000))
    print("   per trade $%+.2f, 95%% band $%+.2f..$%+.2f -> %s"
          % (statistics.mean(diffs), means[50], means[1949],
             "REAL" if means[50] > 0 or means[1949] < 0 else "INSIDE THE NOISE"))


def sim_runner(trade, born, arm, step, trigger, mode, width):
    """The ratchet, but it LOOSENS once a trade has proved it is moving.

    9/10, G: "some sort of pause to give the trade time to run". The pause
    study said no — pausing the ratchet doesn't help a trade run, it just
    exits it lower. This is the mechanically correct version of the same
    instinct: don't loosen on every trade from the start, loosen only on the
    ones already up `trigger` percent.
      mode "rung"  — above the trigger the rung widens from `step` to `width`
      mode "trail" — above the trigger the stop stops laddering and simply
                     trails `width` percent under the HIGHEST bid seen
    Below the trigger, both behave exactly like the live ladder.
    """
    entry = trade["entry"]
    stop = entry * (1.0 - born / 100.0)
    peak = entry
    for _ts, bid, _ask in trade["quotes"]:
        if bid > peak:
            peak = bid
        gain = (bid - entry) / entry * 100.0
        if gain >= trigger:
            if mode == "trail":
                stop = max(stop, peak * (1.0 - width / 100.0))
            else:
                lk = locked_pct(gain, arm, width)
                if lk is not None:
                    stop = max(stop, entry * (1.0 + lk / 100.0))
        else:
            lk = locked_pct(gain, arm, step)
            if lk is not None:
                stop = max(stop, entry * (1.0 + lk / 100.0))
        if bid <= stop:
            return (stop - entry) / entry * 100.0, True
    return (trade["quotes"][-1][1] - entry) / entry * 100.0, False


def runner_study(trades):
    """Does letting a PROVEN mover run pay? (9/10, the pause study's sequel)"""
    import random
    import statistics
    lb, la, ls = live_spacing()

    def tot(fn):
        s = 0.0
        w = 0
        for t in trades:
            rp = fn(t)[0]
            s += (rp / 100.0) * t["entry"] * CONTRACT_MULT
            if rp > 0:
                w += 1
        return s, 100.0 * w / len(trades)

    base, base_wr = tot(lambda t: sim(t, lb, la, ls))
    print("RUNNER STUDY — live ladder %g/%g/%g, %d trades" % (lb, la, ls, len(trades)))
    print("baseline: $%+.2f (win %.0f%%)\n" % (base, base_wr))

    rows = []
    print("A. WIDER RUNG above the trigger")
    print("   %8s %8s %10s %8s %9s" % ("trigger", "rung", "total $", "win%", "vs base"))
    for trig in [10, 15, 20, 30, 50]:
        for wid in [7.5, 10, 15, 20]:
            s, wr = tot(lambda t, a=trig, b=wid: sim_runner(t, lb, la, ls, a, "rung", b))
            rows.append((s, trig, "rung", wid, wr))
            print("   %8d %8.1f %10.2f %7.0f%% %+9.2f" % (trig, wid, s, wr, s - base))

    print("\nB. TRAIL under the PEAK above the trigger")
    print("   %8s %8s %10s %8s %9s" % ("trigger", "trail%", "total $", "win%", "vs base"))
    for trig in [10, 15, 20, 30, 50]:
        for wid in [5, 8, 10, 15, 20, 25]:
            s, wr = tot(lambda t, a=trig, b=wid: sim_runner(t, lb, la, ls, a, "trail", b))
            rows.append((s, trig, "trail", wid, wr))
            print("   %8d %8.1f %10.2f %7.0f%% %+9.2f" % (trig, wid, s, wr, s - base))

    rows.sort(reverse=True)
    s, trig, mode, wid, wr = rows[0]
    print("\nBEST: %s, trigger +%g%%, width %g%% -> $%+.2f (vs $%+.2f, %+.2f)"
          % (mode, trig, wid, s, base, s - base))
    diffs = [(sim_runner(t, lb, la, ls, trig, mode, wid)[0] - sim(t, lb, la, ls)[0])
             / 100.0 * t["entry"] * CONTRACT_MULT for t in trades]
    rnd = random.Random(7)
    means = sorted(sum(rnd.choice(diffs) for _ in diffs) / len(diffs) for _ in range(2000))
    print("  per trade $%+.2f, 95%% band $%+.2f..$%+.2f -> %s"
          % (statistics.mean(diffs), means[50], means[1949],
             "REAL" if means[50] > 0 or means[1949] < 0 else "INSIDE THE NOISE"))
    hit = sum(1 for t in trades
              if max((b - t["entry"]) / t["entry"] * 100.0 for _, b, _ in t["quotes"]) >= trig)
    print("  only %d of %d trades ever reach the +%g%% trigger — the rest are unchanged."
          % (hit, len(trades), trig))


def main():
    tape = load_tape()
    trades = load_trades(tape)
    if "--pause" in sys.argv:
        pause_study(trades)
        return
    if "--runner" in sys.argv:
        runner_study(trades)
        return
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
