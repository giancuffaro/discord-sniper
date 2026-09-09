"""missed_dollarize.py — what did waiting for the round-number pullback COST?

The round-number rule skips an entry when the underlying never pulls back to the
round number. Those skips are recorded as 'nofill' rows in days/*.json (they
carry the caller's price in their_avg, the contract, and a time window) — and
their OPRA prices were already backfilled. So we can answer directly: if we had
just taken the CALLER'S price on every skipped call and run the same 7.5/4/2
ratchet, what would it have made or lost? That dollar figure is the other half
of the RN ledger (entry_compare.py measured the fills it caught).

Read-only. Uses the clean tape + nofill rows.
"""
import glob
import json
import os

import occ
import ratchet_sweep as rs
from ratchet_sweep_fine import sim

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    tape = rs.load_tape()
    # merge in the WIDE-window pull for skipped contracts (scoped_missed_pull.py):
    # it has the real alert->end-of-day path the short backfill window lacked.
    import csv
    mp = os.path.join(HERE, "missed_tape.csv")
    if os.path.exists(mp):
        add = {}
        for row in csv.DictReader(open(mp, encoding="utf-8")):
            try:
                add.setdefault(row["occ"], []).append(
                    (float(row["ts"]), float(row["bid"]), float(row["ask"])))
            except (TypeError, ValueError, KeyError):
                continue
        for k, v in add.items():
            v.sort()
            tape[k] = v          # wide window replaces the 90-second one
    rows = []
    for fn in sorted(glob.glob(os.path.join(HERE, "days", "*.json"))):
        try:
            d = json.load(open(fn, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        for r in d.get("table", []):
            if r.get("kind") != "option" or r.get("state") != "nofill":
                continue
            if str(r.get("who") or "").strip().lower() in rs.EXCLUDE_WHO:
                continue
            sym, side = r.get("symbol"), r.get("side")
            strike, expiry = r.get("strike"), r.get("expiry")
            their, opened = r.get("their_avg"), r.get("opened")
            if not (sym and side and strike and expiry and their and opened):
                continue
            try:
                o = occ.build(sym, expiry, side, strike)
            except ValueError:
                continue
            q = [x for x in tape.get(o, []) if x[0] >= float(opened) - 2]
            rows.append({"occ": o, "their": float(their), "q": q,
                         "who": r.get("who") or "?"})

    covered = [r for r in rows if r["q"] and r["their"] > 0]
    print("skipped (nofill) calls: %d   with backfilled prices: %d\n"
          % (len(rows), len(covered)))
    if not covered:
        print("  none had usable price paths.")
        return

    tot = 0.0
    wins = 0
    det = []
    for r in covered:
        rp, _ = sim({"entry": r["their"], "quotes": r["q"]}, 7.5, 4.0, 2.0)
        dollars = rp / 100.0 * r["their"] * rs.CONTRACT_MULT
        tot += dollars
        if dollars > 0:
            wins += 1
        det.append((dollars, r["occ"], r["their"], rp, r["who"]))

    det.sort(reverse=True)
    print("if we'd taken the CALLER'S price on every skipped call (7.5/4/2 ratchet):")
    print("  total: $%.2f   win %d/%d   avg $%.2f/call\n"
          % (tot, wins, len(covered), tot / len(covered)))
    print("  %-17s in$    result   $P&L   caller" % "contract")
    for dollars, o, e, rp, who in det:
        print("  %-17s %5.2f  %+5.0f%%  %+6.0f   %s" % (o[:17], e, rp, dollars, who))

    print("\nread: POSITIVE total = the RN rule LEFT money on the table by waiting;")
    print("NEGATIVE = waiting SAVED you (those calls would have lost). Compare to")
    print("entry_compare.py's +$ edge on the fills the RN rule DID catch.")


if __name__ == "__main__":
    main()
