"""
ratchet_sweep.py — which (born stop, arm-to-breakeven) spacing actually
would have made the most money on real prices.

WHY (9/8, G: "figure out what ratchet spacing is most convenient.. what
stop to start with and when to jump to break even")
---------------------------------------------------------------------
ratchet_backtest.py answers "did the CURRENT rule (-7.5% born, arm +5%,
lock breakeven, +2% rungs) ever blow past its floor". This answers a
different question: holding that same SHAPE (born stop born_pct, arm at
arm_pct with a breakeven lock there, then a rung every arm_pct beyond it —
the one thing this file does NOT explore is decoupling rung size from arm
size, since G only asked about the stop and the breakeven jump), which
(born_pct, arm_pct) pair actually produces the best real dollars across
every contract-day in master_ledger.csv (via ledger.py).

EXCLUDES GIAN (9/8, his ask): his own hand trades aren't room calls, and
folding them into a "which spacing wins" sweep would tune the bot's exit
around trades it never would have followed in the first place.

ONLY REAL ENTRIES (9/8, found while sanity-checking this): state must be
closed/filled/stopped. A refused or never-filled call was never a position
this ratchet's spacing management — no stop, however spaced, saves a trade
that correctly never opened. Mixing those in dragged EVERY spacing in the
grid to a large loss and made the sweep answer a different question than
the one asked.

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
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ledger  # noqa: E402
import occ  # noqa: E402

# Prefer the despiked tape (clean_tape.py) when it exists — junk bid ticks
# fire phantom stops in every replay. Falls back to the raw backfill.
# 9/9: ONE registry decides which tape is canonical — tape.path("databento")
# is the despiked clean file when it exists. Same answer for every backtest.
import tape as _tape
TAPE_CSV = _tape.path("databento")
OUT_CSV = os.path.join(HERE, "ratchet_sweep_results.csv")

# 9/10 — "" and "?" join gian. An entry with no caller on it is not a room
# call: it is a hand trade or a position the bot adopted from the account.
# They were 707 of 822 rows and -$1,230 of the loss, swamping the 115 real
# room calls and making every spacing in the grid look hopeless.
EXCLUDE_WHO = {"gian", "", "?"}   # not room calls, not this study
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


REAL_ENTRY_STATES = {"closed", "filled", "stopped"}   # actually traded, not a
                                                       # refused/missed call —
                                                       # this study is about
                                                       # EXIT spacing, not
                                                       # whether the entry
                                                       # should have fired


def load_trades(tape):
    """One entry per REAL trade: the bot's own recorded fill (price + time,
    from entries[0] when present) + every quote from that fill onward.

    9/8: the first version of this used 'opened' + nearest tape quote as the
    entry, and included every call regardless of state — refused ones too.
    Both were wrong for this question. 'opened' can predate a pullback fill
    by minutes (TSLA 8/19: opened price ~3.00, real fill 2.94 a beat later —
    close, but entries[0] IS the real fill, no approximating needed when
    it's there). And folding in calls the bot correctly refused drags every
    spacing negative for a reason that has nothing to do with spacing — of
    course a stop can't save a trade that should never have been entered.
    """
    out = []
    # 9/9: reads master_ledger.csv via ledger.py — days/*.json table truncates.
    for day, day_rows in sorted(ledger.by_day().items()):
        for r in day_rows:
            if r.get("kind") != "option":
                continue
            if r.get("state") not in REAL_ENTRY_STATES:
                continue
            who = str(r.get("who") or "").strip().lower()
            if who in EXCLUDE_WHO:
                continue
            sym, side = r.get("symbol"), r.get("side")
            strike, expiry = r.get("strike"), r.get("expiry")
            if not (sym and side and strike and expiry):
                continue
            try:
                o = occ.build(sym, expiry, side, strike)
            except ValueError:
                continue

            entries = r.get("entries") or []
            if entries and entries[0].get("price") and entries[0].get("t"):
                entry = float(entries[0]["price"])
                entry_t = float(entries[0]["t"])
            else:
                entry = r.get("avg")
                entry_t = r.get("opened")
                if not (entry and entry_t):
                    continue
                entry = float(entry)

            after = [x for x in tape.get(o, []) if x[0] >= entry_t - 2]
            if not after or entry <= 0 or _nan(entry):
                continue
            out.append({"day": day, "occ": o, "entry": entry, "quotes": after,
                        "who": who or "?"})
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

    # 9/8, finalized after a first coarse pass (born to 20%, arm to 30%)
    # showed born>15% and arm>=15% strictly worsening with no exception —
    # every born-17.5/20 row and every arm-20/25/30 row ranked in the
    # bottom third, so this final grid drops that dead range and adds the
    # fine 1-6% arm resolution that first exposed the interior peak.
    born_grid = [5.0, 7.5, 10.0, 12.5, 15.0]
    arm_grid = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.5, 10.0, 12.5, 15.0]

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

    # 9/8: live default moved to born 7.5% / arm 5% after this exact sweep
    # found the old born 10%/arm 10% losing money (-$434, rank 30/50) — see
    # HANDOFF.md that date. Tracking the CURRENT live cell here, not the
    # retired one, so a future rerun always points at the right row.
    current = next(r for r in rows_out if r["born_stop_pct"] == 7.5 and r["arm_to_be_pct"] == 5.0)
    print()
    print("current rule (born 7.5%%, arm 5%%): total $%.2f, win rate %.1f%%, rank #%d of %d"
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

    if "--by-caller" in sys.argv:
        # 9/10 — the whole grid came back negative on the full tape (822
        # entries, every one of 50 spacings losing). When no stop wins, the
        # stop is not the lever; WHO is being followed is. Same simulation,
        # split by caller, current rule vs the grid's best.
        best = rows_out[0]
        per = {}
        for t in trades:
            cur = simulate_one(t, 7.5, 5.0)[0] / 100.0 * t["entry"] * CONTRACT_MULT
            bst = simulate_one(t, best["born_stop_pct"],
                               best["arm_to_be_pct"])[0] / 100.0 * t["entry"] * CONTRACT_MULT
            d = per.setdefault(t["who"], {"n": 0, "cur": 0.0, "best": 0.0, "win": 0})
            d["n"] += 1
            d["cur"] += cur
            d["best"] += bst
            if cur > 0:
                d["win"] += 1
        # IS THE WINNER REAL? 115 trades is small. Paired difference per
        # trade (best minus current on the SAME trade), bootstrapped 2000x.
        # If the 95% band straddles zero, the ranking is this sample's noise
        # and the live numbers should not move on it.
        import random
        diffs = [simulate_one(t, best["born_stop_pct"], best["arm_to_be_pct"])[0] / 100.0
                 * t["entry"] * CONTRACT_MULT
                 - simulate_one(t, 7.5, 5.0)[0] / 100.0 * t["entry"] * CONTRACT_MULT
                 for t in trades]
        rnd = random.Random(7)
        means = sorted(sum(rnd.choice(diffs) for _ in diffs) / len(diffs)
                       for _ in range(2000))
        lo, hi = means[50], means[1949]
        print()
        print("IS IT REAL? best-minus-current per trade: $%+.2f  95%% band $%+.2f..$%+.2f  -> %s"
              % (sum(diffs) / len(diffs), lo, hi,
                 "REAL" if lo > 0 or hi < 0 else "INSIDE THE NOISE"))

        print()
        print("BY CALLER — current rule (7.5/5) vs grid best (%.1f/%.1f)"
              % (best["born_stop_pct"], best["arm_to_be_pct"]))
        print("  %-22s %4s %10s %8s %10s %6s" % ("caller", "n", "current$", "$/trade", "best$", "win%"))
        for who, d in sorted(per.items(), key=lambda kv: kv[1]["cur"]):
            print("  %-22s %4d %10.2f %8.2f %10.2f %5.0f%%"
                  % (who[:22], d["n"], d["cur"], d["cur"] / d["n"],
                     d["best"], 100.0 * d["win"] / d["n"]))


if __name__ == "__main__":
    main()
