"""ratchet_lab.py — replay REAL trades against DIFFERENT ratchet rules.

Run it:  python ratchet_lab.py            (all recorded trades)
         python ratchet_lab.py --days 10  (last 10 days only)

WHY THIS EXISTS (9/4/26)
------------------------
G asked what the ratchet should follow. The tempting way to answer that is to
look at the day's P&L and reason from it. That is how you get fooled.

This morning NVDA stopped out at +$11 while the caller who called it rode the
same contract to +$70. Stare at that one trade and the obvious conclusion is
"the rungs are too tight". But the opposite trade — where a tight rung saved a
winner from round-tripping — happens just as often and nobody remembers it,
because nothing dramatic occurs when a stop does its job.

One trade is an anecdote. A day is a small pile of anecdotes. The only honest
way to ask "should the rung be 10% or 15%" is to take the SAME trades, on the
SAME tick paths, and replay them under different rules. Then you are comparing
rules instead of comparing memories.

WHAT IT NEEDS
  option_tape.csv          the tick path of each contract  (fixed 9/4 — before
                           that it had no ticks for traded contracts at all)
  days/*.json              closed trades with fill/exit/occ/times (from 9/4)
Both started recording properly on 9/4, so until several weeks have passed
this will say "not enough data" and it is meant to. That message is the
feature; a confident answer off four trades is the bug.

HOW IT REPLAYS
  It imports ratchet_tiers and drives the REAL production functions, with the
  TIERS table swapped per variant. So the simulation cannot drift away from
  what the bot actually does — if the ratchet changes, this changes with it.
  The stop is tested against the BID, because that is what the watchdog reads.

WHAT IT DELIBERATELY DOES NOT DO
  It does not pick a winner. It prints the distributions and the sample size
  and leaves the judgement to G. It also never writes to settings.json or
  touches a live position — it is a read-only thought experiment.
"""
import argparse
import csv
import glob
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ratchet_tiers as RT                              # noqa: E402

# (arm %, first lock %, rung %) — his current rule first.
VARIANTS = [
    ("HIS RULE  arm+10 lockBE rung10", (10.0, 0.0, 10.0), True),
    ("wider     arm+10 lockBE rung15", (10.0, 0.0, 15.0), True),
    ("wider     arm+15 lockBE rung15", (15.0, 0.0, 15.0), True),
    ("widest    arm+20 lockBE rung20", (20.0, 0.0, 20.0), True),
    ("tighter   arm+10 lock+5  rung5", (10.0, 5.0, 5.0), True),
    ("HIS RULE + anti-clip on 0DTE  ", (10.0, 0.0, 10.0), False),
    ("no ratchet at all (-10% stop) ", None, True),
]


def load_trades(days=None):
    """Closed trades that carry what a replay needs."""
    out = []
    for f in sorted(glob.glob(os.path.join(HERE, "days", "*.json")))[-(days or 9999):]:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:                               # noqa: BLE001
            continue
        for t in (d.get("wallet") or {}).get("trades") or []:
            if t.get("occ") and t.get("fill") and t.get("t"):
                out.append(t)
    return out


def load_tape():
    """occ -> [(ts, bid), ...] sorted. The only option price history we own."""
    tape = defaultdict(list)
    p = os.path.join(HERE, "option_tape.csv")
    if not os.path.exists(p):
        return tape
    with open(p, encoding="utf-8") as f:
        for r in csv.reader(f):
            if len(r) < 4 or r[0] == "ts":
                continue
            try:
                tape[r[1]].append((float(r[0]), float(r[2])))
            except (TypeError, ValueError):
                continue
    for k in tape:
        tape[k].sort()
    return tape


def replay(trade, path, plan, anticlip_on_0dte):
    """Walk the tick path under one rule. Returns the exit price it produces.

    Mirrors the live logic: arm a -10% stop at the fill, walk it up with
    ratchet_locked_pct/ratchet_stop_price, and exit the moment the bid trades
    at or below the stop. If it never stops, the trade exits where it really
    exited — we are testing the STOP, not inventing a different thesis.
    """
    fill = float(trade["fill"])
    stop = round(fill * 0.90, 2)                        # the -10% it starts on
    locked = None
    dte = trade.get("dte")

    if plan is None:                                    # no ratchet at all
        for _ts, bid in path:
            if bid <= stop:
                return stop, "stopped"
        return float(trade.get("exit") or fill), "held to the real exit"

    saved = RT.TIERS
    RT.TIERS = ((None, plan),)
    try:
        for _ts, bid in path:
            if bid <= stop:
                return stop, "stopped"
            gain = (bid - fill) / fill * 100.0
            lk = RT.ratchet_locked_pct(gain, fill)
            if lk is None:
                continue
            use_clip = (dte is None or dte >= 2) if anticlip_on_0dte else True
            if use_clip:
                lk = RT.anti_clip(lk, gain)
            if locked is not None and lk <= locked:
                continue
            new = RT.ratchet_stop_price(fill, lk, bid=bid, current_stop=stop)
            if new:
                stop, locked = new, lk
    finally:
        RT.TIERS = saved
    return float(trade.get("exit") or fill), "held to the real exit"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None)
    a = ap.parse_args()

    trades, tape = load_trades(a.days), load_tape()
    print("=" * 72)
    print("  RATCHET LAB — same trades, same ticks, different rules")
    print("=" * 72)
    print("  closed trades on record : %d" % len(trades))

    usable = []
    for t in trades:
        path = tape.get(t["occ"]) or []
        # only the window this trade was actually open for
        t0 = float(t.get("opened_t") or 0) or (float(t["t"]) - 6 * 3600)
        seg = [(ts, b) for ts, b in path if t0 <= ts <= float(t["t"])]
        if len(seg) >= 5:
            usable.append((t, seg))
    print("  with a usable tick path : %d" % len(usable))

    if len(usable) < 20:
        print("""
  NOT ENOUGH DATA — and that is the honest answer, not a failure.

  option_tape.csv and the trade record both only started capturing properly
  on 9/4/26. Until there are a few dozen trades with real tick paths, any
  ranking below is noise: one lucky runner can reorder the whole table.

  Let it collect. Re-run this in a few weeks.
""")
        if not usable:
            return 0
        print("  (showing what there is, clearly marked as INSUFFICIENT)\n")

    rows = []
    for name, plan, clip0 in VARIANTS:
        tot = wins = 0
        for t, seg in usable:
            px, _why = replay(t, seg, plan, clip0)
            pl = (px - float(t["fill"])) * 100 * int(t.get("qty") or 1)
            tot += pl
            wins += 1 if pl >= 0 else 0
        rows.append((name, tot, wins, len(usable)))

    real = sum(float(t.get("pl") or 0) for t, _ in usable)
    print("  %-34s %10s  %8s" % ("RULE", "P&L", "win rate"))
    print("  " + "-" * 56)
    for name, tot, wins, n in rows:
        print("  %-34s %+10.0f  %5.0f%% (%d/%d)"
              % (name, tot, 100.0 * wins / max(n, 1), wins, n))
    print("  " + "-" * 56)
    print("  %-34s %+10.0f   <- what actually happened" % ("ACTUAL", real))
    print("""
  Read this as a comparison, not a recommendation. A rule that wins here by
  a few dollars over %d trades has not proven anything. Look for a rule that
  wins CONSISTENTLY and by a margin that survives dropping the best trade.
""" % len(usable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
