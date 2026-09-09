"""today_entry_compare.py — pullback entry vs "got in with them" entry, today.

WHY (9/8, G: "we read them.. waited for the pull back.. what would of been
the original entry point if we didnt pull back for it? and what would of
their trade got if we would of gotten in with them instead of the pull
back")
-----------------------------------------------------------------------
Every one of today's 6 real room calls IS pullback-managed (bridge.py's
per-room "pullback" entry mode) — the hunt arms on the ALERT, watches the
UNDERLYING STOCK for a touch of the next round dollar, then buys at the ask.
The 'opened' timestamp in days/*.json is the TOUCH (order-fire) moment, not
the alert — so a naive read of days/*.json understates the wait by 8-346
seconds. The real alert time comes from bridge.log's "AI READ" line.

HONEST LIMIT — why "immediate entry" uses their_avg, not our own tick
-----------------------------------------------------------------------
Checked first: does our own tape (option_tape.csv / tastytrade, via tape.py)
have a real recorded quote AT the alert moment? No — on every one of these
six, the earliest tick our own system ever recorded for the contract is
3-5 seconds before the TOUCH, not the alert (the pullback hunt watches the
stock, not the option, while it waits — nothing polls the option's own
bid/ask until the moment it's about to buy). Databento can't fill the gap
either — its free tier is embargoed within 24h of today (see HANDOFF 9/8).
So there is no real recorded option price at alert-time to fall back on.
Best available stand-in: their_avg, the caller's own posted price, which is
timestamped at essentially the same moment as the alert — this literally IS
"getting in with them." Not a guess dressed as data — the actual number
they called it at.

WHAT THIS DOES NOT CLAIM
-----------------------------------------------------------------------
The "immediate" leg's stop/ratchet walk uses OUR real recorded ticks from
the moment they start (a few seconds pre-touch) onward — same real prices
the actual trade lived through. Between alert and touch there's a real gap
with zero data on either leg; the sim can't see inside it, so a wick in that
window (either direction) isn't reflected in the -10% floor check. Read as
"same shape as ratchet_backtest.py, same honest-limits disclosure."

Run: python today_entry_compare.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ledger                 # noqa: E402
import occ                    # noqa: E402
import ratchet_tiers as rt    # noqa: E402
import tape                   # noqa: E402

DAY = "2026-09-08"

# (label, symbol, expiry, side, strike, alert_unix_t, their_avg, who, room)
# alert_unix_t read off bridge.log's "AI READ" line for each call (the
# 'opened' field in days/*.json is the pullback TOUCH, not this).
TRADES = [
    ("AMD 510C 9/11 (Mike #1)",  "AMD", "2026-09-11", "CALLS", 510,
     1788874491.3, 6.00, "Mike", "Honeydrip daytrades"),
    ("AMD 510C 9/11 (Mike #2)",  "AMD", "2026-09-11", "CALLS", 510,
     1788875455.1, 5.60, "Mike", "Honeydrip daytrades"),
    ("QQQ 717P 9/8 (Owner #1)",  "QQQ", "2026-09-08", "PUTS", 717,
     1788875594.1, 1.78, "@Owner Alerts", "911389167169191946"),
    ("QQQ 717P 9/8 (Owner #2)",  "QQQ", "2026-09-08", "PUTS", 717,
     1788876116.8, 1.72, "@Owner Alerts", "911389167169191946"),
    ("TSLA 372.5C 9/11 (Owner)", "TSLA", "2026-09-11", "CALLS", 372.5,
     1788876414.7, 1.50, "@Owner Alerts", "911389167169191946"),
    ("QQQ 716P 9/8 (Vero)",      "QQQ", "2026-09-08", "PUTS", 716,
     1788876600.5, 1.35, "Vero", "Vero 1"),
]

BORN_STOP_PCT = 10.0   # today's live default — settings.json strategy.stop_loss_pct


def _nan(x):
    return x != x


def simulate(rows_after_entry, entry):
    """Copy of ratchet_backtest.simulate — the real live rule (born -10%,
    ratchet_tiers ladder), tick by tick. Returns (realized_pct, stopped_out,
    last_ts_used)."""
    stop = entry * (1.0 - BORN_STOP_PCT / 100.0)
    last_ts = None
    for ts, bid, _ask in rows_after_entry:
        last_ts = ts
        gain = (bid - entry) / entry * 100.0
        locked = rt.ratchet_locked_pct(gain, entry)
        if locked is not None:
            new_stop = entry * (1.0 + locked / 100.0)
            stop = max(stop, new_stop)
        if bid <= stop:
            return (stop - entry) / entry * 100.0, True, ts
    if rows_after_entry:
        last_bid = rows_after_entry[-1][1]
        return (last_bid - entry) / entry * 100.0, False, last_ts
    return 0.0, False, None


def load_real_fills():
    # 9/9: reads master_ledger.csv via ledger.py — days/*.json table truncates.
    out = {}
    for r in ledger.by_day().get(DAY, []):
        if r.get("kind") != "option":
            continue
        who = str(r.get("who") or "").strip().lower()
        if who == "gian":
            continue
        entries = r.get("entries") or []
        if not entries:
            continue
        key = (r.get("symbol"), r.get("side"), r.get("strike"), round(entries[0]["t"], 0))
        out[key] = r
    return out


def main():
    real = load_real_fills()
    print("%-28s %8s %8s %8s | %-22s | %-22s" % (
        "trade", "wait(s)", "their$", "our$", "IMMEDIATE (their_avg)", "PULLBACK (our real fill)"))
    print("-" * 130)

    tot_immediate = 0.0
    tot_pullback = 0.0

    for label, sym, exp, side, strike, alert_t, their_avg, who, room in TRADES:
        o = occ.build(sym, exp, side, strike)
        rows = sorted(tape.rows(occ=o), key=lambda r: r.ts)
        today_rows = [(r.ts, r.bid, r.ask) for r in rows if r.ts >= 1788850000
                      and r.bid and r.ask and not _nan(r.bid) and not _nan(r.ask)
                      and r.bid > 0 and r.ask > 0]

        # find this specific alert's matching real row (by nearest entries[0].t)
        real_row = None
        best_dt = None
        for (rsym, rside, rstrike, rt_), rr in real.items():
            if rsym != sym or rside != side or float(rstrike) != float(strike):
                continue
            dt = abs(rr["entries"][0]["t"] - alert_t)
            if dt < 600 and (best_dt is None or dt < best_dt):
                best_dt, real_row = dt, rr
        if real_row is None:
            print("%-28s  -- no matching real fill found, skipped --" % label)
            continue

        touch_t = real_row["entries"][0]["t"]
        our_fill = real_row["entries"][0]["price"]
        wait_s = round(touch_t - alert_t, 1)

        # PULLBACK leg: real entry, real ticks from the real fill onward.
        pull_quotes = [q for q in today_rows if q[0] >= touch_t - 1]
        pull_pct, pull_stopped, _ = simulate(pull_quotes, our_fill)
        pull_dollars = pull_pct / 100.0 * our_fill * 100.0

        # IMMEDIATE leg: entry = their posted price at alert time, then the
        # same real ticks (all we have — the gap before touch is unrecorded
        # on both legs, see module docstring).
        imm_quotes = [q for q in today_rows if q[0] >= alert_t - 1]
        imm_pct, imm_stopped, _ = simulate(imm_quotes, their_avg)
        imm_dollars = imm_pct / 100.0 * their_avg * 100.0

        tot_immediate += imm_dollars
        tot_pullback += pull_dollars

        flag = "  <-- their posted price looks off, see notes" if label.startswith("TSLA") else ""
        print("%-28s %8.1f %8.2f %8.2f | %+6.1f%% (%s%+.0f$)%s | %+6.1f%% (%s%+.0f$)" % (
            label, wait_s, their_avg, our_fill,
            imm_pct, "stopped " if imm_stopped else "open as of data end ", imm_dollars, flag,
            pull_pct, "stopped " if pull_stopped else "open as of data end ", pull_dollars))

    print("-" * 130)
    print("TOTALS (1 contract each, %d trades): immediate/with-them $%.2f   vs   pullback (real) $%.2f   ->  pullback %s by $%.2f"
          % (len(TRADES), tot_immediate, tot_pullback,
             "won" if tot_pullback > tot_immediate else "lost",
             abs(tot_pullback - tot_immediate)))


if __name__ == "__main__":
    main()
