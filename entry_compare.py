"""entry_compare.py — is the ROUND-NUMBER entry actually beating the caller's price?

For every real option fill we have two entry prices: the caller's stated entry
(their_avg) and what the bot actually filled (its RN-pullback / "caller's price
or better" logic). This replays the SAME contract's quote path from each price
through the same ratchet — the LIVE spacing, read from ratchet_tiers (never
typed here) — and compares the dollars, plus the
raw fill-price distribution.

Honest limits: (1) it only sees trades the bot ACTUALLY FILLED — the winners the
RN rule missed by waiting for a pullback that never came are NOT here (those are
in misses.py, PULLBACK-never-hit); the RN rule's true value = better fills here
MINUS those missed winners. (2) The caller entered a beat earlier than the bot;
replaying their price over the bot's quote window is an approximation of the
price effect, not a perfect twin. Read-only.
"""
import os

from ratchet_tiers import live_spacing

import ledger
import occ
import ratchet_sweep as rs
from ratchet_sweep_fine import sim

HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    tape = rs.load_tape()
    out = []
    # 9/9: reads master_ledger.csv via ledger.py — days/*.json table truncates.
    for _date, day_rows in sorted(ledger.by_day().items()):
        for r in day_rows:
            if r.get("kind") != "option":
                continue
            if r.get("state") not in rs.REAL_ENTRY_STATES:
                continue
            if str(r.get("who") or "").strip().lower() in rs.EXCLUDE_WHO:
                continue
            sym, side = r.get("symbol"), r.get("side")
            strike, expiry = r.get("strike"), r.get("expiry")
            their = r.get("their_avg")
            ent = (r.get("entries") or [{}])[0]
            botp, bott = ent.get("price"), ent.get("t")
            if not (sym and side and strike and expiry and their and botp and bott):
                continue
            try:
                o = occ.build(sym, expiry, side, strike)
            except ValueError:
                continue
            q = [x for x in tape.get(o, []) if x[0] >= float(bott) - 2]
            if not q or float(their) <= 0 or float(botp) <= 0:
                continue
            out.append({"occ": o, "their": float(their), "bot": float(botp),
                        "quotes": q})
    return out


def main():
    rows = load()
    n = len(rows)
    print("comparing %d filled option trades (bot RN fill vs caller's price)\n" % n)

    better = same = worse = 0
    diffs = []
    bot_tot = their_tot = 0.0
    bot_win = their_win = 0
    for t in rows:
        d = (t["bot"] - t["their"]) / t["their"] * 100.0
        diffs.append(d)
        if t["bot"] < t["their"] - 1e-9:
            better += 1          # bot paid LESS than the caller = better entry
        elif t["bot"] > t["their"] + 1e-9:
            worse += 1
        else:
            same += 1
        rb, _ = sim({"entry": t["bot"], "quotes": t["quotes"]}, *live_spacing())
        rt, _ = sim({"entry": t["their"], "quotes": t["quotes"]}, *live_spacing())
        bot_tot += (rb / 100.0) * t["bot"] * rs.CONTRACT_MULT
        their_tot += (rt / 100.0) * t["their"] * rs.CONTRACT_MULT
        if rb > 0:
            bot_win += 1
        if rt > 0:
            their_win += 1

    avg = sum(diffs) / n if n else 0
    print("FILL PRICE vs the caller:")
    print("  better (paid less): %3d   same: %3d   worse (paid more): %3d"
          % (better, same, worse))
    print("  average fill vs caller: %+.2f%%  (negative = you got in cheaper)\n"
          % avg)
    print("SAME contracts, %g/%g/%g spacing — the LIVE ladder, read from "
          "ratchet_tiers, entered at each price:" % live_spacing())
    print("  your RN fill .......... $%8.2f   (win %.0f%%)"
          % (bot_tot, 100.0 * bot_win / n))
    print("  the caller's price .... $%8.2f   (win %.0f%%)"
          % (their_tot, 100.0 * their_win / n))
    print("  edge from the RN entry: $%8.2f" % (bot_tot - their_tot))
    print("\n(does NOT count winners the RN pullback MISSED by waiting — see"
          "\n misses.py PULLBACK-never-hit. Full value = this edge MINUS those.)")


if __name__ == "__main__":
    main()
