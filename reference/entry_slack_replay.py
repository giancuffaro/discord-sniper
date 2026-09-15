#!/usr/bin/env python3
"""entry_slack_replay.py — what would crossing the ask have cost, and bought?

G, 9/15: "lets keep it as an option to backtest the alerts, maybe we have to
loosen up in that aspect."  This is that backtest, and it is the whole of it.
It places no order, changes no setting, and answers ONE question with the only
evidence that exists — the quotes we actually recorded:

    On the orders that never filled, would a slack of 0/2/3/5/7.5/10% have
    got us in, and what would the trade have been worth under the LIVE
    ratchet?  And on the orders that DID fill, how much of the better-than-
    posted price we currently earn would that same slack have given away?

THE HEADLINE NUMBER IS NET. Rescuing a runner is easy to admire and easy to
over-count; the cost side is invisible unless something adds it up, because it
is spread one nickel at a time across every fill that went right.

THE RULE IS NOT IN THIS FILE. entry_slack.decide() is the one implementation,
shared with the (blocked) live path, so the thing measured here and the thing
that would trade can never drift apart. The exits are not in this file either:
reference/ratchet_replay_tape.simulate() runs the position forward on the real
quote path under the live ladder, with the born stop, the tick floor, the
spread floor and the broker's stop-under-the-bid clamp, selling at observed
bids. ratchet_tiers.live_spacing() supplies the numbers, so the 9/15 move back
to 10/10/10 arrived here without anybody retyping it.

WHERE THE POPULATION COMES FROM
-------------------------------
trades.log ORDER IN / NOFILL / FILLED lines, paired by symbol and price inside
10 minutes. Two honest corrections to the number this study started from:

  * `grep -c NOFILL trades.log` says 52. Five of those are POSTCHECK lines
    about a no-fill, not no-fills. There are 47.
  * 20 of the 47 are FUTURES (16 MNQ, 4 MGC). A futures entry snaps to the
    25-point grid and has no ask to cross on this rule, so they are out.

So the population is **27 option no-fills out of 201 ORDER IN lines (13%)**,
not 52 of 204 (25%). Every table below counts the 27.

COVERAGE IS THE ANSWER, NOT A FOOTNOTE
--------------------------------------
An order is SCORED only when a tape recorded that exact contract's bid/ask
within QUOTE_TOL_S (90s, webull.entry_fill_seconds) of the order going in —
the bid's own resting window, so any quote inside it is one the bid faced. Everything else is
UNSCORED and stays out of every total. Nothing is interpolated, extrapolated,
or filled in from the nearest thing that happened to be lying around.

THE QUARANTINE, and it is most of them
--------------------------------------
Some no-fills come back with a recorded ask at or BELOW the price we bid. At
slack 0 the model then says "this fills", which contradicts the NOFILL the
broker actually wrote. That contradiction is real information, not noise:
Webull's book and the consolidated tape disagreed, or (on the August orders,
which were qty 5) the size at the offer was smaller than the order. Either
way the row cannot score the slack question — it disagrees with reality at
the baseline — so it is QUARANTINED, listed by name, and enters no total.

MEASUREMENT ONLY. Nothing here can place an order or change a setting.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import entry_slack                                          # noqa: E402
import occ as occ_symbol                                    # noqa: E402
import ratchet_tiers as rt                                  # noqa: E402
import reports                                              # noqa: E402
import tape                                                 # noqa: E402
from ratchet_replay_tape import bootstrap, gap_before, simulate  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                                           # noqa: BLE001
    ET = dt.timezone(dt.timedelta(hours=-4))

KIND = "entry-slack"
CUMULATIVE = os.path.join(HERE, "ENTRY-SLACK-REPLAY.csv")
TRADES_LOG = os.path.join(ROOT, "trades.log")

QUOTE_TOL_S = 90.0          # webull.entry_fill_seconds — the bid's own window
PAIR_WINDOW_S = 600.0       # an ORDER IN this long before its outcome line
FLAT_AT = "15:59:00"
GAP_ALARM_S = 120.0
CONTRACT_MULTIPLIER = 100.0
SLACKS = entry_slack.SLACK_LEVELS

ORDER_RE = re.compile(
    r"^(\S+)\tORDER IN (?:\[[A-Z]\] )?BUY ([\d.]+) ([A-Z.]+) "
    r"([\d.]+)([CP]) (\d{4}-\d{2}-\d{2}) @ ([\d.]+)")
NOFILL_RE = re.compile(
    r"^(\S+)\tNOFILL\s+([A-Z.]+) — no fill \(nobody sold at ([\d.]+) "
    r"within (\d+)s\)")
FILLED_RE = re.compile(
    r"^(\S+)\tFILLED\s+([A-Z.]+) — filled ([\d.]+) at ([\d.]+)")


# ------------------------------------------------------------------ the log
def _ts(iso):
    return dt.datetime.fromisoformat(iso).timestamp()


def read_log(path=TRADES_LOG):
    """(orders, nofills, fills) from trades.log. Options only — a futures
    ORDER IN has no strike/expiry and never matches ORDER_RE, which is how
    the 20 MNQ/MGC no-fills leave the population without a special case."""
    orders, nofills, fills = [], [], []
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return orders, nofills, fills
    with fh:
        for line in fh:
            hit = ORDER_RE.match(line)
            if hit:
                orders.append({
                    "iso": hit.group(1), "ts": _ts(hit.group(1)),
                    "qty": float(hit.group(2)), "symbol": hit.group(3),
                    "strike": float(hit.group(4)), "cp": hit.group(5),
                    "expiry": hit.group(6), "limit": float(hit.group(7))})
                continue
            hit = NOFILL_RE.match(line)
            if hit:
                nofills.append({"iso": hit.group(1), "ts": _ts(hit.group(1)),
                                "symbol": hit.group(2),
                                "price": float(hit.group(3)),
                                "window_s": int(hit.group(4))})
                continue
            hit = FILLED_RE.match(line)
            if hit:
                fills.append({"iso": hit.group(1), "ts": _ts(hit.group(1)),
                              "symbol": hit.group(2), "qty": float(hit.group(3)),
                              "fill": float(hit.group(4))})
    return orders, nofills, fills


def _pair(event, orders, match_price=True):
    """The ORDER IN this outcome line belongs to: same symbol, inside the
    pairing window, the LAST one before it. A no-fill also has to match on
    price, because the no-fill line quotes the resting bid back."""
    best = None
    for order in orders:
        if order["symbol"] != event["symbol"] or order["ts"] > event["ts"]:
            continue
        if event["ts"] - order["ts"] > PAIR_WINDOW_S:
            continue
        if match_price and abs(order["limit"] - event["price"]) > 1e-6:
            continue
        best = order
    return best


def _occ(order):
    try:
        return occ_symbol.build(order["symbol"], order["expiry"],
                                "CALLS" if order["cp"] == "C" else "PUTS",
                                order["strike"])
    except (ValueError, TypeError):
        return ""


def population():
    """(no_fills, filled, n_order_in) — every option order in the record,
    paired to its outcome line. An ORDER IN with neither a FILLED nor a
    NOFILL after it (cancelled, edited, pullback never touched) is counted in
    n_order_in and scored nowhere."""
    orders, nofills, fills = read_log()
    out_nf, out_f = [], []
    for event in nofills:
        order = _pair(event, orders)
        if order is None:
            continue                      # futures, or an ORDER IN we never wrote
        out_nf.append(dict(order, occ=_occ(order), outcome_ts=event["ts"],
                           window_s=event["window_s"], kind="nofill"))
    for event in fills:
        order = _pair(event, orders, match_price=False)
        if order is None:
            continue
        out_f.append(dict(order, occ=_occ(order), outcome_ts=event["ts"],
                          fill=event["fill"], qty=event["qty"] or order["qty"],
                          kind="fill"))
    return ([r for r in out_nf if r["occ"]], [r for r in out_f if r["occ"]],
            len(orders))


# ---------------------------------------------------------------- the quotes
def quote_paths(contracts):
    """{occ: [(ts, bid, ask)]} for every contract at once, through tape.py —
    the ONE registry (HANDOFF.md, PRICE TAPES). One streaming pass over every
    recorded feed; duplicate whole seconds keep the first row seen."""
    grouped = {}
    for row in tape.rows(occs=set(contracts)):
        if not row.bid or not row.ask or row.bid <= 0 or row.ask <= 0:
            continue
        if row.ask < row.bid:
            continue
        grouped.setdefault(row.occ, {}).setdefault(
            int(row.ts), (row.ts, row.bid, row.ask))
    return {occ: [bysec[t] for t in sorted(bysec)]
            for occ, bysec in grouped.items()}


def read_quote(path, when, tol=QUOTE_TOL_S):
    """(ts, bid, ask, gap) nearest to ``when`` inside ``tol``, or None. Never
    the last known value — a stale quote presented as a contemporaneous one is
    how a comparison turns into a lie (tape.py's own rule)."""
    best = None
    for row in path:
        gap = abs(row[0] - when)
        if best is None or gap < best[3]:
            best = (row[0], row[1], row[2], gap)
    if best is None or best[3] > tol:
        return None
    return best


def _flat_ts(ts):
    day = dt.datetime.fromtimestamp(ts, ET).date().isoformat()
    return dt.datetime.fromisoformat("%sT%s" % (day, FLAT_AT)).replace(
        tzinfo=ET).timestamp()


def _day_of(ts):
    return dt.datetime.fromtimestamp(ts, ET).date().isoformat()


# ---------------------------------------------------------------- the replay
def score_nofill(row, path):
    """One no-fill under every slack level. Money is per ORDER (qty x 100)."""
    quote = read_quote(path, row["ts"])
    row["quote"] = quote
    row["runs"] = {}
    if quote is None:
        row["status"] = "unscored"
        row["why"] = ("no recorded bid/ask within %ds of the order"
                      % int(QUOTE_TOL_S)) if path else \
                     "no tape ever quoted this contract"
        return row
    _qts, bid, ask, _gap = quote
    base = entry_slack.decide(row["limit"], bid, ask, 0.0, row["symbol"])
    if base.cross:
        # The tape says this was fillable at the price we bid, and the broker
        # says it was not. The baseline is already wrong, so the row cannot
        # score the question. Quarantined, named, never totalled.
        row["status"] = "quarantined"
        row["why"] = ("recorded ask %.2f was at or under our bid %.2f — the "
                      "tape and the broker's book disagree" % (ask, row["limit"]))
        return row
    row["status"] = "scored"
    row["why"] = ""
    flat = _flat_ts(row["ts"])
    walk = [r for r in path if r[0] >= quote[0] and r[0] <= flat]
    for slack in SLACKS:
        decision = entry_slack.decide(row["limit"], bid, ask, slack,
                                      row["symbol"])
        if not decision.cross:
            row["runs"][slack] = {"filled": False, "entry": None, "pl": 0.0,
                                  "why": "no fill (as it happened)"}
            continue
        if not walk:
            row["runs"][slack] = {"filled": True, "entry": decision.price,
                                  "pl": None,
                                  "why": "crossed, but no forward quote path"}
            continue
        run = simulate(walk, decision.price, row["symbol"], rt.TIERS,
                       False, False, flat)
        row["runs"][slack] = {
            "filled": True, "entry": decision.price,
            "pl": run["pl"] * row["qty"], "exit": run["exit"],
            "why": run["why"], "peak_bid": run["peak_bid"],
            "gap": gap_before(walk, run["ts"], GAP_ALARM_S),
            "held_s": run["held_s"]}
    return row


def score_fill(row, path):
    """One filled order: what we gained by resting, and what each slack would
    have handed back. Positive ``given_up`` = the slack costs money."""
    row["improvement"] = ((row["limit"] - row["fill"]) * CONTRACT_MULTIPLIER
                          * row["qty"])
    quote = read_quote(path, row["ts"])
    row["quote"] = quote
    row["runs"] = {}
    if quote is None:
        row["status"] = "unscored"
        row["why"] = ("no recorded bid/ask within %ds of the order"
                      % int(QUOTE_TOL_S)) if path else \
                     "no tape ever quoted this contract"
        return row
    _qts, bid, ask, _gap = quote
    row["status"] = "scored"
    row["why"] = ""
    for slack in SLACKS:
        decision = entry_slack.decide(row["limit"], bid, ask, slack,
                                      row["symbol"])
        if not decision.cross:
            row["runs"][slack] = {"crossed": False, "paid": row["fill"],
                                  "given_up": 0.0}
            continue
        given = (decision.price - row["fill"]) * CONTRACT_MULTIPLIER * row["qty"]
        row["runs"][slack] = {"crossed": True, "paid": decision.price,
                              "given_up": given}
    return row


def build():
    nofills, fills, n_orders = population()
    paths = quote_paths([r["occ"] for r in nofills + fills])
    for row in nofills:
        score_nofill(row, paths.get(row["occ"]) or [])
    for row in fills:
        score_fill(row, paths.get(row["occ"]) or [])
    return nofills, fills, n_orders


# ------------------------------------------------------------------- totals
def totals(nofills, fills):
    """Per slack: rescued count, gross from the rescues, improvement given up
    on the fills, and NET. Scored rows only, all of them paired."""
    scored_nf = [r for r in nofills if r["status"] == "scored"]
    scored_f = [r for r in fills if r["status"] == "scored"]
    out = {}
    for slack in SLACKS:
        rescued = [r for r in scored_nf
                   if r["runs"][slack]["filled"] and r["runs"][slack]["pl"] is not None]
        gross = sum(r["runs"][slack]["pl"] for r in rescued)
        given = sum(r["runs"][slack]["given_up"] for r in scored_f)
        out[slack] = {"rescued": len(rescued), "gross": gross,
                      "given_up": given, "net": gross - given,
                      "crossed_fills": sum(1 for r in scored_f
                                           if r["runs"][slack]["crossed"])}
    # SLACK 0 IS THE BASELINE, not zero dollars. The model prices a cross at
    # the recorded ask, and our real fills came in BETTER than that ask, so
    # the slack-0 column already shows a loss against the broker's own prices.
    # That bias is constant across the sweep, so the number that means
    # anything is the DIFFERENCE from slack 0 — it cancels.
    for slack in SLACKS:
        out[slack]["delta"] = out[slack]["net"] - out[0.0]["net"]
    return out, scored_nf, scored_f


def paired_diffs(scored_nf, scored_f, slack):
    """Per-ORDER difference against slack 0, over the same orders both times —
    the only comparison a bootstrap is allowed to resample."""
    diffs = []
    for row in scored_nf:
        base = row["runs"][0.0]["pl"] or 0.0
        now = row["runs"][slack]["pl"]
        diffs.append((now if now is not None else 0.0) - base)
    for row in scored_f:
        diffs.append(-(row["runs"][slack]["given_up"]
                       - row["runs"][0.0]["given_up"]))
    return diffs


# ------------------------------------------------------------------- report
def _money(value):
    if value is None:
        return "—"
    return "%s$%.0f" % ("-" if value < 0 else "+", abs(value))


def _cents(value):
    """Per-order and per-contract money, where a penny is the whole point."""
    if value is None:
        return "—"
    return "%s$%.2f" % ("-" if value < 0 else "+", abs(value))


def _pct(value):
    return "%g%%" % value


def _table(header, rows):
    out = ["| " + " | ".join(str(h) for h in header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return out


def best_slack(agg):
    """The slack level with the best difference against today's rule. Ties go
    to the SMALLER slack, so 0 (today) wins unless something really beats it."""
    return min(SLACKS, key=lambda s: (-agg[s]["delta"], s))


def verdict_line(day, nofills, agg, bands):
    today = [r for r in nofills if _day_of(r["ts"]) == day]
    best = best_slack(agg)
    if best == 0.0:
        return ("VERDICT — %d no-fill%s today; nothing beats today's rule: "
                "every slack level from %s to %s comes out behind it "
                "(%s to %s), and %s"
                % (len(today), "" if len(today) == 1 else "s",
                   _pct(SLACKS[1]), _pct(SLACKS[-1]),
                   _money(agg[SLACKS[1]]["delta"]),
                   _money(agg[SLACKS[-1]]["delta"]),
                   _band_words(bands.get(SLACKS[-1]))))
    return ("VERDICT — %d no-fill%s today; best slack %s is %s against "
            "today's rule, and %s"
            % (len(today), "" if len(today) == 1 else "s", _pct(best),
               _money(agg[best]["delta"]), _band_words(bands.get(best))))


def _band_words(band):
    if band is None:
        return "there is no paired sample to put an error bar on"
    if band["lo"] > 0 or band["hi"] < 0:
        return ("the 95%% band on %d paired orders (%s .. %s per order) "
                "CLEARS zero" % (band["n"], _cents(band["lo"]),
                                 _cents(band["hi"])))
    return ("the 95%% band on %d paired orders (%s .. %s per order) SPANS "
            "zero — undecidable at this n" % (band["n"], _cents(band["lo"]),
                                              _cents(band["hi"])))


def render(day, nofills, fills, n_orders):
    agg, scored_nf, scored_f = totals(nofills, fills)
    bands = {}
    for slack in SLACKS:
        if slack == 0.0:
            continue
        bands[slack] = bootstrap(paired_diffs(scored_nf, scored_f, slack))
    best = best_slack(agg)
    born, arm, step = rt.live_spacing()
    quarantined = [r for r in nofills if r["status"] == "quarantined"]
    unscored = [r for r in nofills if r["status"] == "unscored"]

    lines = ["# ENTRY SLACK — would crossing the ask have paid?", "",
             "Measurement only. `execution.entry_slack_pct` is 0 and its "
             "activation is BLOCKED: the bot bids the caller's price or better "
             "and never chases. This file exists to tell G, every day, what "
             "that rule costs and what it saves.", "",
             verdict_line(day, nofills, agg, bands), ""]

    lines += ["## The population", "",
              "| | n | note |", "|---|---:|---|",
              "| option ORDER IN lines, all time | %d | every option order the "
              "bot has ever sent |" % n_orders,
              "| with a recorded outcome | %d | a FILLED or NOFILL line after "
              "it; the rest were cancelled, edited or never resolved |"
              % len(nofills + fills),
              "| never filled | %d | the 90-second window expired with the bid "
              "unhit — the population this rule is about |" % len(nofills),
              "| filled | %d | where the cost side lives |" % len(fills),
              "| no-fills SCORED | **%d** | a real recorded bid/ask within %ds "
              "of the order |" % (len(scored_nf), int(QUOTE_TOL_S)),
              "| no-fills QUARANTINED | %d | the tape says the ask was already "
              "at or under our bid, so at slack 0 the model contradicts the "
              "broker. Counted nowhere |" % len(quarantined),
              "| no-fills UNSCORED | %d | no quote at read time. Not estimated, "
              "not extrapolated, not counted |" % len(unscored),
              "| fills SCORED | %d of %d | the cost is only charged where a "
              "real ask was recorded |" % (len(scored_f), len(fills)), "",
              "COVERAGE, said plainly: **%d of the %d option no-fills can be "
              "scored**. %d are quarantined and %d have no quote at read time. "
              "The benefit side of this question rests on %d trade%s; the cost "
              "side on %d. They are not measured to the same standard and the "
              "table below must be read that way."
              % (len(scored_nf), len(nofills), len(quarantined), len(unscored),
                 len(scored_nf), "" if len(scored_nf) == 1 else "s",
                 len(scored_f)), "",
              "`grep -c NOFILL trades.log` says 52. Five of those are POSTCHECK "
              "lines about a no-fill; 20 of the remaining 47 are FUTURES "
              "(16 MNQ, 4 MGC), which have no ask to cross on this rule. The "
              "option population is %d of %d ORDER INs (%.0f%%), not 52 of 204."
              % (len(nofills), n_orders, 100.0 * len(nofills) / max(1, n_orders)),
              ""]

    lines += ["## Slack level → what it buys, what it costs", "",
              "Exits are the LIVE ratchet, read from `ratchet_tiers."
              "live_spacing()` and never typed in here: born stop -%g%%, arms "
              "at +%g%%, %g%% rungs, the tick and spread floors, the broker's "
              "stop-under-the-bid clamp, sold at observed bids, flat at 15:59 "
              "ET. Money is per order (qty x 100)." % (born, arm, step), ""]
    lines += _table(["slack", "no-fills rescued", "gross from the rescues",
                     "fills that would cross", "improvement given up",
                     "model net", "**vs today**"],
                    [[_pct(s) + (" — today's rule" if s == 0 else ""),
                      "%d of %d" % (agg[s]["rescued"], len(scored_nf)),
                      _money(agg[s]["gross"]),
                      "%d of %d" % (agg[s]["crossed_fills"], len(scored_f)),
                      _money(-agg[s]["given_up"]),
                      _money(agg[s]["net"]),
                      "**%s**" % (_money(agg[s]["delta"]) if s else "baseline")]
                     for s in SLACKS])
    lines += ["", "**Read the last column, not the one before it.** The model "
              "prices a cross at the recorded ask, and our real fills came in "
              "BETTER than that ask — so the slack-0 column is already %s "
              "against the broker's own prices on %d of %d scored fills. That "
              "bias is the same at every slack level, so it cancels in the "
              "difference and poisons the absolute."
              % (_money(agg[0.0]["net"]), agg[0.0]["crossed_fills"],
                 len(scored_f)), ""]
    improvement = sum(r["improvement"] for r in fills)
    lines += ["Across ALL %d filled orders in the record — scored or not — "
              "resting at the caller's price filled **%s** better than the "
              "price we bid, about %s a contract. That is the thing crossing "
              "spends."
              % (len(fills), _money(improvement),
                 _cents(improvement / max(1, len(fills)) / CONTRACT_MULTIPLIER)),
              ""]

    lines += ["## Paired bootstrap against today's rule (same orders, both "
              "times)", ""]
    rows = []
    for slack in SLACKS:
        if slack == 0.0:
            continue
        band = bands.get(slack)
        if band is None:
            continue
        diffs = paired_diffs(scored_nf, scored_f, slack)
        if all(abs(d) < 1e-9 for d in diffs):
            call = "identical to today on **every** scored order"
        elif band["lo"] > 0 or band["hi"] < 0:
            call = ("real at this sample — and it is on the **%s** side"
                    % ("gain" if band["mean"] > 0 else "LOSS"))
        else:
            call = "**undecidable at this n** — the band spans zero"
        rows.append([_pct(slack), band["n"], _cents(band["mean"]),
                     "%s .. %s" % (_cents(band["lo"]), _cents(band["hi"])),
                     "%.0f%%" % (100.0 * band["share_above_zero"]), call])
    lines += _table(["slack", "n paired orders", "mean diff / order",
                     "95% band (4000 resamples)", "resamples above zero",
                     "verdict"], rows)
    lines += ["", "The band is the 2.5th-97.5th percentile of the resampled "
              "MEAN difference, the same method the 9/10 ratchet sweep used. A "
              "band containing zero means this sample cannot tell the rules "
              "apart, whatever the totals say.", "",
              "One asymmetry matters more than the band: the %d fills give the "
              "cost side a real sample, while the benefit side has %d trade%s. "
              "So a band that clears zero here is evidence about the COST of "
              "crossing, not proof about its upside."
              % (len(scored_f), len(scored_nf),
                 "" if len(scored_nf) == 1 else "s"), ""]

    today_rows = [r for r in nofills if _day_of(r["ts"]) == day]
    lines += ["## Today's no-fills (%s)" % day, ""]
    if not today_rows:
        lines += ["None.", ""]
    else:
        rows = []
        for row in sorted(today_rows, key=lambda r: r["ts"]):
            quote = row["quote"]
            cells = []
            for slack in SLACKS:
                run = (row.get("runs") or {}).get(slack) or {}
                if run.get("filled"):
                    cells.append("%s at $%.2f -> %s" % (
                        _pct(slack), run["entry"],
                        _money(run["pl"]) if run.get("pl") is not None else "?"))
            rows.append([row["iso"][11:16], row["occ"], "$%.2f" % row["limit"],
                         ("%.2f x %.2f" % (quote[1], quote[2])) if quote else "—",
                         row["status"],
                         "; ".join(cells) if cells else "no slack level crosses",
                         row["why"] or ""])
        lines += _table(["time", "contract", "our bid", "market at read",
                         "status", "what crossing would have done", "note"],
                        rows)
        lines += [""]

    rescued_any = [(r, s) for r in scored_nf for s in SLACKS
                   if r["runs"][s].get("filled")
                   and r["runs"][s].get("pl") is not None]
    if rescued_any:
        lines += ["## Why the rescues still lost", "",
                  "This is the part the complaint cannot see from the chart. "
                  "Crossing pays the offer, and the born stop is then clamped "
                  "one tick under the live BID (Webull 417s a resting stop at "
                  "or above the bid), so a cross on a wide spread starts with "
                  "a stop far tighter than -%g%%. It also moves the +%g%% arm "
                  "out of reach: a contract bought 15c higher has to run 15c "
                  "further before the ratchet locks anything."
                  % (born, arm), ""]
        seen = set()
        rows = []
        for row, slack in rescued_any:
            key = (row["occ"], row["iso"])
            if key in seen:
                continue
            seen.add(key)
            first = min(s for s in SLACKS if row["runs"][s].get("filled"))
            run = row["runs"][first]
            rows.append([_day_of(row["ts"]), row["occ"], "$%.2f" % row["limit"],
                         "$%.2f" % run["entry"], "$%.2f" % run["peak_bid"],
                         "%+.1f%%" % (100.0 * (run["peak_bid"] - run["entry"])
                                      / run["entry"]),
                         run["why"], "$%.2f" % run["exit"], _money(run["pl"])])
        lines += _table(["date", "contract", "our bid", "crossed at",
                         "best bid after", "peak gain", "how it ended",
                         "exit", "P&L"], rows)
        lines += [""]

    if quarantined:
        lines += ["## Quarantined — the tape disagrees with the broker", "",
                  "These came back with a recorded ask at or UNDER the price we "
                  "bid, so at slack 0 the model says they filled and the broker "
                  "says they did not. That is a real disagreement — a different "
                  "venue's offer, or (the August orders were qty 5) more size "
                  "wanted than the offer held — and it means the row cannot "
                  "answer this question. None of them is counted anywhere "
                  "above, in either direction.", ""]
        lines += _table(["date", "contract", "our bid", "recorded market", "qty"],
                        [[_day_of(r["ts"]), r["occ"], "$%.2f" % r["limit"],
                          "%.2f x %.2f" % (r["quote"][1], r["quote"][2]),
                          "%g" % r["qty"]]
                         for r in sorted(quarantined, key=lambda x: x["ts"])])
        lines += [""]

    if unscored:
        lines += ["## Unscored no-fills — never estimated", ""]
        lines += _table(["date", "contract", "our bid", "why"],
                        [[_day_of(r["ts"]), r["occ"], "$%.2f" % r["limit"],
                          r["why"]]
                         for r in sorted(unscored, key=lambda x: x["ts"])])
        lines += [""]

    lines += ["## Honest limits", "",
              "- %d scored orders cannot settle a trading rule. They can rule "
              "things out, and they can price a cost."
              % (len(scored_nf) + len(scored_f)),
              "- The benefit side is %d trade%s. Nothing here is a verdict on "
              "the upside of crossing; it is a verdict on what the record can "
              "see." % (len(scored_nf), "" if len(scored_nf) == 1 else "s"),
              "- The quote at read time is the nearest recorded print inside "
              "%ds, not a tick-by-tick book. A price that lived between two "
              "prints is invisible here." % int(QUOTE_TOL_S),
              "- Most feeds carry no SIZE, so an ask with one contract behind "
              "it looks exactly like an ask with fifty. The August orders were "
              "qty 5, which is the likeliest reason for the quarantine above.",
              "- The forward replay has no slippage, no queue and no partial "
              "fills: the entry pays the offer and the exit prints at the bid "
              "that broke the stop. Real life is worse.",
              "- The anchor is the price the bot BID (the ORDER IN line) — the "
              "caller's price or better after the tick floor, not the caller's "
              "raw post.",
              "- Coverage is stated, never inferred. An unscored order is "
              "absent from every total above, in both directions.", "",
              "Built by `reference/entry_slack_replay.py` from `trades.log` "
              "(population) and `tape.py` (quotes: alert_tape, quote_shadow, "
              "option_tape, databento_tape, missed_tape, greeks_tape). The rule "
              "is `entry_slack.decide()`; the exits are "
              "`reference/ratchet_replay_tape.simulate()` on "
              "`ratchet_tiers.live_spacing()`. Per-order rows: "
              "`reference/ENTRY-SLACK-REPLAY.csv`."]
    return "\n".join(lines).rstrip() + "\n", agg, bands


FIELDS = ["date", "time", "kind", "occ", "symbol", "qty", "our_bid",
          "actual_fill", "improvement", "status", "bid_at_read", "ask_at_read",
          "quote_gap_s", "why"] + \
    ["slack_%g_%s" % (s, k) for s in SLACKS for k in ("cross", "entry", "pl")]


def write_csv(nofills, fills):
    """One living file, rewritten from the log every run (it is derived, and
    re-derivable — APPEND DON'T PILE applies to records that cannot be
    rebuilt, which this is not)."""
    rows = []
    for row in sorted(nofills + fills, key=lambda r: r["ts"]):
        quote = row.get("quote")
        rec = {"date": _day_of(row["ts"]), "time": row["iso"][11:19],
               "kind": row["kind"], "occ": row["occ"], "symbol": row["symbol"],
               "qty": "%g" % row["qty"], "our_bid": "%.2f" % row["limit"],
               "actual_fill": ("%.2f" % row["fill"]) if row.get("fill") else "",
               "improvement": ("%.0f" % row["improvement"])
                              if row.get("improvement") is not None else "",
               "status": row["status"],
               "bid_at_read": ("%.2f" % quote[1]) if quote else "",
               "ask_at_read": ("%.2f" % quote[2]) if quote else "",
               "quote_gap_s": ("%.0f" % quote[3]) if quote else "",
               "why": row["why"]}
        for slack in SLACKS:
            run = (row.get("runs") or {}).get(slack) or {}
            if row["kind"] == "nofill":
                rec["slack_%g_cross" % slack] = run.get("filled", "")
                rec["slack_%g_entry" % slack] = run.get("entry") or ""
                rec["slack_%g_pl" % slack] = ("%.0f" % run["pl"]) \
                    if run.get("pl") is not None else ""
            else:
                rec["slack_%g_cross" % slack] = run.get("crossed", "")
                rec["slack_%g_entry" % slack] = run.get("paid") or ""
                rec["slack_%g_pl" % slack] = ("%.0f" % -run["given_up"]) \
                    if run.get("given_up") is not None else ""
        rows.append(rec)
    tmp = CUMULATIVE + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, CUMULATIVE)
    return CUMULATIVE


def main(day):
    nofills, fills, n_orders = build()
    text, agg, bands = render(day, nofills, fills, n_orders)
    path = reports.write_day(KIND, day, text)
    write_csv(nofills, fills)
    best = best_slack(agg)
    widest = bands.get(SLACKS[-1])
    print("ENTRY SLACK %s — %d option no-fills of %d orders, %d scored; best "
          "slack %g%% is %s vs today; %g%% band %s"
          % (day, len(nofills), n_orders,
             len([r for r in nofills if r["status"] == "scored"]), best,
             _money(agg[best]["delta"]), SLACKS[-1],
             ("%s..%s per order" % (_cents(widest["lo"]), _cents(widest["hi"])))
             if widest else "n/a"))
    print(path)
    print(CUMULATIVE)
    return 0


if __name__ == "__main__":
    import eastern
    raise SystemExit(main(eastern.day_arg()))
