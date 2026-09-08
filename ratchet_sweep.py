"""
ratchet_sweep.py — which (born stop, arm-to-breakeven) spacing actually
would have made the most money on real prices.

WHY (9/8, G: "figure out what ratchet spacing is most convenient.. what
stop to start with and when to jump to break even")
---------------------------------------------------------------------
ratchet_backtest.py answers "did the CURRENT rule (-10% born, arm +10%,
lock breakeven, +10% rungs) ever blow past its floor". This answers a
different question: holding that same SHAPE (born stop born_pct, arm at
arm_pct with a breakeven lock there, then a rung every arm_pct beyond it —
the one thing this file does NOT explore is decoupling rung size from arm
size, since G only asked about the stop and the breakeven jump), which
(born_pct, arm_pct) pair actually produces the best real dollars across
every contract-day in days/*.json.

EXCLUDES GIAN (9/8, his ask): his own hand trades aren't room calls, and
folding them into a "which spacing wins" sweep would tune the bot's exit
around trades it never would have followed in the first place.

HONEST LIMITS — read before trusting a number out of this
-----------------------------------------------------------
* ~110 contract-days across five weeks is a SMALL sample. A spacing that
  wins here by a few dollars is not proven better — it can easily be this
  particular five weeks' noise. Treat the ranking as a lean, not a verdict.
* Entry is always "bought at the ask closest to when the call came in" —
  the same assumption the backfill and ratchet_backtest already make, real
  fill or not.
* A contract-day whose price never reached ANY exit within its backfilled
  window is marked unresolved and scored at its last known price — not a
  final number. Reported per-config so you can see how much of the ranking
  rests on trades that hadn't actually finished.
* $ P&L assumes ONE contract (settings.json strategy.one_contract) at
  100x the premium, no fees.

Run: python ratchet_sweep.py
"""

import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import occ  # noqa: E402

TAPE_CSV = os.path.join(HERE, "databento_tape.csv")
OUT_CSV = os.path.join(HERE, "ratchet_sweep_results.csv")

EXCLUDE_WHO = {"gian"}   # his own hand trades — not room calls, not this study
CONTRACT_MULT = 100.0    # one option contract = 100 shares


def _nan(x):
    return x != x


def load_tape():
    tape = {}
    with open(TAPE_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                b, a = float(r["bid"]), float(r["ask"])
            except (TypeError, ValueError):
                continue
            if _nan(b) or _nan(a) or b <= 0 or a <= 0:
                continue
            tape.setdefault(r["occ"], []).append((float(r["ts"]), b, a))
    for k in tape:
        tape[k].sort()
    return tape


def load_trades(tape):
    """One entry per contract-day: entry price + every quote from entry on."""
    out = []
    for fn in sorted(glob.glob(os.path.join(HERE, "days", "*.json"))):
        day = os.path.basename(fn)[:-5]
        try:
            d = json.load(open(fn, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in d.get("table", []):
            if r.get("kind") != "option":
                continue
            who = str(r.get("who") or "").strip().lower()
            if who in EXCLUDE_WHO:
                continue
            sym, side = r.get("symbol"), r.get("side")
            strike, expiry = r.get("strike"), r.get("expiry")
            opened = r.get("opened")
            if not (sym and side and strike and expiry and opened):
                continue
            try:
                o = occ.build(sym, expiry, side, strike)
            except ValueError:
                continue
            rows = [x for x in tape.get(o, []) if x[0] >= opened - 5]
            if not rows:
                continue
            entry_row = min(rows, key=lambda x: abs(x[0] - opened))
            entry = entry_row[2]
            if entry <= 0 or _nan(entry):
                continue
            after = [x for x in rows if x[0] >= entry_row[0]]
            if not after:
                continue
            out.append({"day": day, "occ": o, "entry": entry, "quotes": after})
    return out


def locked_pct(gain_pct, arm_pct, step_pct):
    """Same shape as ratchet_tiers.ratchet_locked_pct: arm to lock BREAKEVEN,
    then step_pct more locked for every further step_pct of gain."""
    if gain_pct < arm_pct - 1e-9:
        return None
    k = int((gain_pct - arm_pct + 1e-9) // step_pct)
    return 0.0 + step_pct * k


def simulate_one(trade, born_pct, arm_pct):
    entry = trade["entry"]
    stop = entry * (1.0 - born_pct / 100.0)
    for _ts, bid, _ask in trade["quotes"]:
        gain = (bid - entry) / entry * 100.0
        lk = locked_pct(gain, arm_pct, arm_pct)      # rung tied to arm, his ask was just these two
        if lk is not None:
            new_stop = entry * (1.0 + lk / 100.0)
            stop = max(stop, new_stop)
        if bid <= stop:
            realized_pct = (stop - entry) / entry * 100.0
            return realized_pct, True
    last_bid = trade["quotes"][-1][1]
    realized_pct = (last_bid - entry) / entry * 100.0
    return realized_pct, False


def main():
    tape = load_tape()
    trades = load_trades(tape)
    print("simulating %d room-call contract-days (Gian excluded)" % len(trades))

    born_grid = [5.0, 7.5, 10.0, 12.5, 15.0, 17.5, 20.0]
    arm_grid = [5.0, 7.5, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0]

    rows_out = []
    for born in born_grid:
        for arm in arm_grid:
            total_dollars = 0.0
            wins = 0
            resolved = 0
            for t in trades:
                realized_pct, stopped = simulate_one(t, born, arm)
                total_dollars += (realized_pct / 100.0) * t["entry"] * CONTRACT_MULT
                if realized_pct > 0:
                    wins += 1
                if stopped:
                    resolved += 1
            n = len(trades)
            rows_out.append({
                "born_stop_pct": born, "arm_to_be_pct": arm,
                "total_pl_dollars": round(total_dollars, 2),
                "avg_pl_dollars": round(total_dollars / n, 2) if n else 0,
                "win_rate_pct": round(100.0 * wins / n, 1) if n else 0,
                "resolved_of": "%d/%d" % (resolved, n),
            })

    rows_out.sort(key=lambda r: -r["total_pl_dollars"])
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)

    current = next(r for r in rows_out if r["born_stop_pct"] == 10.0 and r["arm_to_be_pct"] == 10.0)
    print()
    print("current rule (born 10%%, arm 10%%): total $%.2f, win rate %.1f%%, rank #%d of %d"
          % (current["total_pl_dollars"], current["win_rate_pct"],
             rows_out.index(current) + 1, len(rows_out)))
    print()
    print("TOP 8 BY TOTAL $:")
    for r in rows_out[:8]:
        print("  -%.1f%% born / arm +%.1f%%  ->  $%8.2f total, %5.1f%% win rate, %s resolved"
              % (r["born_stop_pct"], r["arm_to_be_pct"], r["total_pl_dollars"],
                 r["win_rate_pct"], r["resolved_of"]))
    print()
    print("full grid -> %s" % os.path.basename(OUT_CSV))


if __name__ == "__main__":
    main()
