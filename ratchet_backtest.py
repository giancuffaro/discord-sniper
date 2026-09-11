"""
ratchet_backtest.py — what the REAL ratchet would have done, on real prices.

WHY (9/8, G: "no contracts should've blown up, are you keeping in mind the
ratchet system?")
-------------------------------------------------------------------------
The first pass at this analysis reported the min/max price each missed call
reached in its window and called that "best case / worst case" — which
ignored that every entry gets a stop born under it (-10% at the time, -7.5%
since 9/8) and walks up from there. That made refused calls look like they
could have lost 50-90%, when the ratchet would have capped every one of them
at its born stop. Wrong methodology, not a data problem — the tape prices
were always real.

This is the honest version: for every contract in master_ledger.csv (via
ledger.py), simulate the ACTUAL rule (ratchet_tiers.py, the 9/9 settle — one
ladder for every premium: born -7.5%, arms at +5% gain, first lock breakeven,
then +2% a rung, anti-clip OFF per his 9/4 call) tick by tick against real
OPRA prices from the canonical databento tape (tape.path("databento") — the
despiked clean file when it exists), and report what really would have
happened.

WHAT "stopped_out": false MEANS
--------------------------------
The simulated stop never got touched inside the window we backfilled — not
"still open forever". A nofill/failed call only got a 30-minute window
(NOFILL_WINDOW_SECONDS in databento_backfill.py); a slow mover can outlast
that. Read realized_pct as "where it stood when our data runs out", not a
final number, whenever stopped_out is false.

Run: python ratchet_backtest.py
"""

import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ledger                 # noqa: E402
import occ                    # noqa: E402
import ratchet_tiers as rt    # noqa: E402

# 9/9: was hard-wired to the RAW tape while ratchet_sweep used the CLEAN one —
# two backtests, two tapes. tape.path("databento") is the one canonical file.
import tape as _tape
TAPE_CSV = _tape.path("databento")
OUT_JSON = os.path.join(HERE, "ratchet_backtest_results.json")

BORN_STOP_PCT = rt.live_spacing()[0]  # one reader for the live setting


def _nan(x):
    return x != x


def load_tape():
    tape = {}
    if not os.path.exists(TAPE_CSV):
        sys.exit("No databento tape — run databento_backfill.py (then clean_tape.py) first.")
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


def simulate(rows_after_entry, entry):
    """Walk real quotes forward with the actual ratchet rule. Returns
    (realized_pct, stopped_out, peak_gain_pct)."""
    stop = entry * (1.0 - BORN_STOP_PCT / 100.0)
    peak_gain = 0.0
    for _ts, bid, _ask in rows_after_entry:
        gain = (bid - entry) / entry * 100.0
        peak_gain = max(peak_gain, gain)
        locked = rt.ratchet_locked_pct(gain, entry)
        if locked is not None:
            new_stop = entry * (1.0 + locked / 100.0)
            stop = max(stop, new_stop)
        if bid <= stop:
            # F20 (9/11 audit): a resting stop is a MARKET order once it
            # triggers — it fills at whatever the bid actually is right
            # then, not at the nominal stop price. Crediting `stop` here
            # made every gap-through look like a clean stop-level exit
            # (a -50% gap under a -7.5% stop reported as -7.5%), which is
            # exactly the "worse than the born stop" gap risk main() is
            # trying to measure. Credit the real bid — it can only be
            # <= stop in this branch, so this never makes a fill look
            # BETTER than it was, only ever as bad as it really was.
            return (bid - entry) / entry * 100.0, True, peak_gain
    last_bid = rows_after_entry[-1][1] if rows_after_entry else entry
    return (last_bid - entry) / entry * 100.0, False, peak_gain


def main():
    tape = load_tape()
    out = []
    # 9/9: reads master_ledger.csv via ledger.py — days/*.json table truncates.
    for day, day_rows in sorted(ledger.by_day().items()):
        for r in day_rows:
            if r.get("kind") != "option":
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
            entry = entry_row[2]  # buy at the ask, same as a real entry
            if entry <= 0 or _nan(entry):
                continue
            after = [x for x in rows if x[0] >= entry_row[0]]
            if not after:
                continue
            realized, stopped, peak = simulate(after, entry)
            out.append({
                "day": day, "occ": o, "who": r.get("who"), "room": r.get("room"),
                "state": r.get("state"), "entry": round(entry, 2),
                "realized_pct": round(realized, 1), "stopped_out": stopped,
                "peak_gain_pct": round(peak, 1),
            })

    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), indent=1)

    worse_than_floor = [x for x in out if x["realized_pct"] < -BORN_STOP_PCT - 0.5]
    unresolved = [x for x in out if not x["stopped_out"]]
    print("simulated %d contract-days -> %s" % (len(out), OUT_JSON))
    print("worse than the %.0f%% born stop: %d (should be ~0 - only real gap "
          "risk, never the window/method)" % (BORN_STOP_PCT, len(worse_than_floor)))
    print("never touched the simulated stop within the window we have: %d "
          "(read as 'as of when data runs out', not final)" % len(unresolved))


if __name__ == "__main__":
    main()
