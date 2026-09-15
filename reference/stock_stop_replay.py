#!/usr/bin/env python3
"""stock_stop_replay.py — manage the trade off the STOCK instead of the premium.

G's idea, in his words: "alert -> round-number pullback -> arm with a $0.25
stock stop; +$0.25 in favor -> stop to breakeven; then ratchet every +$0.15
from there" for SPY/QQQ, and a $1.00 stop on the Mag 7.

That is close to what `pullback.py` already does after a pullback entry — it
manages off the underlying with a fixed stop and a fixed TARGET (SPY/QQQ
0.25/0.50, Mag 7 1.00/2.50). His proposal keeps the stop and replaces the fixed
target with a stock-price ratchet. So the live rule is measured here too, as its
own column, and so is our premium 5/3/5 ratchet on the identical entries.

MEASUREMENT ONLY. This file places no orders and changes no setting.

WHAT RUNS
---------
Every variant is measured from L, the round-number level the stock actually
touched, in the trade's favour direction (up for a call, down for a put).

  S1   G's exact rule      SPY/QQQ stop 0.25, arm 0.25 -> L, rung 0.15
                           Mag 7   stop 1.00, arm 1.00, rung 0.60 (same ratio)
  S1b  S1 with the rounder Mag 7 rung 0.50 (SPY/QQQ identical to S1)
  S2   stop 0.35 (arm 0.35), Mag 7 1.50 — rungs unchanged
  S3   stop 0.45 (arm 0.45), Mag 7 2.00 — rungs unchanged
  P0   THE LIVE RULE: fixed stock stop and fixed stock target, no ratchet
       (`pullback.UNDERLYING_EXITS`, read from the live file)
  A    OUR PREMIUM 5/3/5, replayed on the option path by
       `ratchet_replay_tape.simulate` — one implementation, not a second copy
  H    HYBRID (suggested by Claude, NOT by G): S1's stock stop carries the
       initial risk, and the moment the PREMIUM is +3% the premium 5/3/5
       ratchet takes over at breakeven and owns the rest of the run. The idea
       is that a cheap contract's one-tick noise can't scratch a stock-level
       stop, while the premium ratchet still follows a runner.

CONSERVATIVE BY CONSTRUCTION
  * Stop before rung, on the same second: the adverse extreme of each 1-second
    bar is tested against the standing stop BEFORE the favourable extreme is
    allowed to raise it.
  * A stock rule fires on the stock clock; the option is then sold at the FIRST
    option BID at or after that second. The lag is recorded per trade and
    summarised, because a sweep-based option tape can only pay you late.
  * Entries cross the ask. No slippage, no queue, no partial fills.

HONEST LIMITS
  * Two different option tapes, never interleaved inside one contract-day:
    Databento OPRA (`databento_tape_clean.csv`, ~1 quote/second) for 8/11-9/8,
    and the Webull tapes (`alert_tape.csv` + `option_tape.csv`, 5-60s sweeps)
    for 9/11. The OPRA windows are SHORT — the backfill bought the minutes
    around each call, not the whole session — so most paths end long before
    15:59 and "close" means "the end of the tape", not a real exit.
  * 2026-09-14 CANNOT BE MEASURED. Every Databento equity dataset
    (XNAS.ITCH, XNAS.BASIC, EQUS.MINI/SUMMARY, DBEQ.BASIC, ARCX/XNYS.PILLAR,
    IEXG.TOPS) ends at 2026-09-14T04:00Z, so that session's per-second stock
    bars are not released yet. Re-running this script once they are will pick
    them up; the fetch is cached, so it will only pay for 9/14.
  * Small sample, one regime, and the stock ladder has never traded a dollar.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import occ as occ_symbol                                    # noqa: E402
import pullback                                             # noqa: E402
import pullback_levels                                      # noqa: E402
import ratchet_replay_tape as prem                          # noqa: E402

ET = prem.ET
SYMBOLS = ("SPY", "QQQ", "TSLA", "NVDA", "META", "AAPL", "MSFT", "AMZN",
           "GOOGL", "AMD")
FLAT_AT = "15:59:00"
MAX_ENTRY_LAG_S = 180.0
FILL_MATCH_WINDOW_S = 900.0
PULLBACK_WINDOW_S = 600.0       # settings.json pullback.timeout_seconds
BOOTSTRAP_N = 4000
PREMIUM_HANDOFF_PCT = 3.0       # H: the premium ratchet's own arm

# (stop, arm, rung) per band. SPY/QQQ first, Mag 7 second. The live stop
# distances come from pullback.UNDERLYING_EXITS so they can never drift from
# the file the bridge actually runs.
_ETF_STOP = pullback.UNDERLYING_EXITS["SPY"][0]             # 0.25
_MAG_STOP = pullback.UNDERLYING_EXITS["TSLA"][0]            # 1.00
STOCK_VARIANTS = (
    ("S1", "G's rule: stop/arm 0.25, rung 0.15 (Mag 7 1.00/0.60)",
     {"etf": (_ETF_STOP, _ETF_STOP, 0.15), "mag": (_MAG_STOP, _MAG_STOP, 0.60)}),
    ("S1b", "S1 with the rounder Mag 7 rung 0.50",
     {"etf": (_ETF_STOP, _ETF_STOP, 0.15), "mag": (_MAG_STOP, _MAG_STOP, 0.50)}),
    ("S2", "stop/arm 0.35 (Mag 7 1.50), rungs unchanged",
     {"etf": (0.35, 0.35, 0.15), "mag": (1.50, 1.50, 0.60)}),
    ("S3", "stop/arm 0.45 (Mag 7 2.00), rungs unchanged",
     {"etf": (0.45, 0.45, 0.15), "mag": (2.00, 2.00, 0.60)}),
)
ALL_VARIANTS = ("S1", "S1b", "S2", "S3", "P0", "A", "H")
VARIANT_LABEL = dict(
    [(c, l) for c, l, _p in STOCK_VARIANTS]
    + [("P0", "LIVE pullback stock exit: fixed stop + fixed target, no ratchet"),
       ("A", "OUR PREMIUM 5/3/5 ratchet on the same entry"),
       ("H", "HYBRID (Claude's suggestion): S1 stock stop, then premium 5/3/5 at +3%")])


def _f(v):
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _flat_ts(day):
    return dt.datetime.fromisoformat("%sT%s" % (day, FLAT_AT)).replace(
        tzinfo=ET).timestamp()


def _band(symbol):
    return "etf" if str(symbol).upper() in ("SPY", "QQQ", "IWM") else "mag"


# ------------------------------------------------------------------- inputs
def option_paths():
    """{(day, occ): (source, [(ts, bid, ask)])}.

    ONE source per contract-day, never interleaved: Databento OPRA first (it is
    real market data at ~1 quote/second), then the two Webull tapes, which are
    the same vendor at different cadences and so may be merged with each other.
    """
    out, webull = {}, defaultdict(dict)
    for name, source in (("databento_tape_clean.csv", "OPRA 1s"),
                         ("alert_tape.csv", "Webull sweep"),
                         ("option_tape.csv", "Webull sweep")):
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            continue
        grouped = defaultdict(dict)
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                ts, bid, ask = (_f(row.get("ts")), _f(row.get("bid")),
                                _f(row.get("ask")))
                contract = (row.get("occ") or "").strip()
                if (not contract or ts is None or not bid or not ask
                        or bid <= 0 or ask <= 0 or ask < bid):
                    continue
                day = dt.datetime.fromtimestamp(ts, ET).date().isoformat()
                grouped[(day, contract)].setdefault(int(ts), (ts, bid, ask))
        if source == "OPRA 1s":
            for key, rows in grouped.items():
                out[key] = (source, [rows[t] for t in sorted(rows)])
        else:
            for key, rows in grouped.items():
                webull[key].update({t: v for t, v in rows.items()
                                    if t not in webull[key]})
    for key, rows in webull.items():
        if key not in out:               # OPRA wins; never mix the two
            out[key] = ("Webull sweep", [rows[t] for t in sorted(rows)])
    return out


def stock_paths(days_symbols):
    """{(day, sym): [(ts, low, high, close)]} from the cached 1-second bars."""
    out = {}
    for day, sym in days_symbols:
        bars = pullback_levels.load_bars(sym, day)
        if bars:
            out[(day, sym)] = [(b[0], b[3], b[2], b[4]) for b in bars]
    return out


def alerts():
    """Every options OPEN alert on the ten symbols, from both alert records."""
    seen, out = set(), []
    meta = os.path.join(ROOT, "alert_meta.csv")
    if os.path.exists(meta):
        with open(meta, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("stage") != "alert":
                    continue
                sym = (row.get("symbol") or "").upper()
                contract, ts = (row.get("occ") or "").strip(), _f(row.get("ts"))
                if (sym not in SYMBOLS or not contract or ts is None
                        or (row.get("side") or "").upper() not in ("CALLS", "PUTS")):
                    continue
                key = (row["date"], contract, int(ts // 60))
                if key in seen:
                    continue
                seen.add(key)
                out.append({"day": row["date"], "time": row.get("time") or "",
                            "ts": ts, "occ": contract, "symbol": sym,
                            "side": row.get("side"), "strike": _f(row.get("strike")),
                            "expiry": row.get("expiry") or "",
                            "room": row.get("room") or "",
                            "caller": row.get("caller") or "",
                            "their_price": _f(row.get("their_price"))})
    with open(os.path.join(ROOT, "master_alerts.csv"), encoding="utf-8-sig",
              newline="") as fh:
        for row in csv.DictReader(fh):
            sym, side = (row.get("symbol") or "").upper(), (row.get("side") or "").upper()
            if sym not in SYMBOLS or side not in ("CALLS", "PUTS"):
                continue
            try:
                contract = occ_symbol.build(sym, row.get("expiry"), side,
                                            _f(row.get("strike")))
            except (ValueError, TypeError):
                continue
            clock = (row.get("time") or "")[:8]
            if len(clock) == 5:
                clock += ":00"
            try:
                ts = dt.datetime.fromisoformat("%sT%s" % (row["date"], clock)
                                               ).replace(tzinfo=ET).timestamp()
            except ValueError:
                continue
            key = (row["date"], contract, int(ts // 60))
            if key in seen:
                continue
            seen.add(key)
            out.append({"day": row["date"], "time": clock, "ts": ts,
                        "occ": contract, "symbol": sym, "side": side,
                        "strike": _f(row.get("strike")),
                        "expiry": row.get("expiry") or "",
                        "room": row.get("room") or "",
                        "caller": row.get("caller") or "",
                        "their_price": _f(row.get("their_price"))})
    return sorted(out, key=lambda a: (a["day"], a["ts"]))


# --------------------------------------------------------------- mechanics
def _bid_at_or_after(path, ts):
    """(bid, quote_ts, lag_seconds) for the first option quote at/after ts."""
    for qts, bid, _ask in path:
        if qts >= ts - 1e-9:
            return bid, qts, qts - ts
    return None, None, None


def _bid_before(path, ts):
    prev = None
    for qts, bid, _ask in path:
        if qts > ts + 1e-9:
            break
        prev = bid
    return prev


def stock_walk(bars, level, side, plan, entry, opt_path, flat, target=None):
    """Run one stock-level rule and return where it took the trade off.

    `plan` is (stop_distance, arm_distance, rung). `target` turns it into the
    LIVE fixed-target rule instead of a ratchet. Everything is measured from
    `level`, the round number the stock came back to.
    """
    stop_d, arm_d, rung = plan
    dirn = 1 if pullback.is_call(side) else -1
    stop = level - dirn * stop_d
    locked, rungs, best = None, 0, 0.0
    for ts, low, high, _close in bars:
        if ts > flat:
            break
        adverse, favour = (low, high) if dirn == 1 else (high, low)
        gain = dirn * (favour - level)
        best = max(best, gain)
        # STOP FIRST, on this same second.
        if (adverse - stop) * dirn <= 1e-9:
            why = "stop" if rungs == 0 else ("BE" if locked == 0 else "rung")
            return _settle(opt_path, ts, entry, why, best, stop, level)
        if target is not None and gain >= target - 1e-9:
            return _settle(opt_path, ts, entry, "target", best, stop, level)
        if target is None and rung > 0 and gain >= arm_d - 1e-9:
            k = int((gain - arm_d + 1e-9) // rung)
            want_locked = rung * k
            if locked is None or want_locked > locked + 1e-9:
                locked = want_locked
                stop = level + dirn * locked
                rungs += 1
    # "close" is the end of the tape, not a real exit: fire at the last option
    # quote so the lag is zero rather than the distance to the last stock bar.
    return _settle(opt_path, opt_path[-1][0], entry, "close", best, stop, level)


def _settle(opt_path, fire_ts, entry, why, best, stop, level):
    """Sell at the first option BID at or after the second the rule fired.

    When the option tape ends BEFORE the rule fires there is no such quote.
    That is a coverage hole, not a negative lag: the last bid is used, the lag
    is recorded as unknown, and the row is flagged so the lag statistics never
    average a number that does not exist.
    """
    bid, qts, lag = _bid_at_or_after(opt_path, fire_ts)
    tape_ended = bid is None
    if tape_ended:
        bid, qts, lag = opt_path[-1][1], opt_path[-1][0], None
    return {"why": why, "fire_ts": fire_ts, "ts": qts, "lag": lag, "exit": bid,
            "tape_ended_first": tape_ended,
            "pl": (bid - entry) * 100.0, "pct": (bid - entry) / entry * 100.0,
            "stock_best": best, "stop": stop, "level": level,
            "held_s": qts - opt_path[0][0],
            "bid_before_fire": _bid_before(opt_path, fire_ts)}


def hybrid_walk(bars, level, side, plan, entry, opt_path, root, flat):
    """S1's stock stop until the premium is +3%, then the premium 5/3/5 ratchet.

    Claude's suggestion, not G's. Before the handoff only the stock stop can
    end the trade; after it, `ratchet_replay_tape.simulate` owns the exit and
    starts from the breakeven rung the premium ladder has just earned.
    """
    handoff = None
    for qts, bid, _ask in opt_path:
        if qts > flat:
            break
        if (bid - entry) / entry * 100.0 >= PREMIUM_HANDOFF_PCT - 1e-9:
            handoff = qts
            break
    stop_d = plan[0]
    dirn = 1 if pullback.is_call(side) else -1
    stop = level - dirn * stop_d
    best = 0.0
    for ts, low, high, _close in bars:
        if ts > flat or (handoff is not None and ts > handoff):
            break
        adverse, favour = (low, high) if dirn == 1 else (high, low)
        best = max(best, dirn * (favour - level))
        if (adverse - stop) * dirn <= 1e-9:
            return _settle(opt_path, ts, entry, "stop", best, stop, level)
    if handoff is None:
        return _settle(opt_path, opt_path[-1][0], entry, "close", best, stop,
                       level)
    # HANDOFF. The premium is already at the ladder's +3% arm, so the ladder's
    # own answer is a BREAKEVEN stop — that, subject to the tick and spread
    # floors, is what the premium ratchet inherits. The stock stop is dropped.
    tail = [q for q in opt_path if q[0] >= handoff]
    prem_stop = prem.stop_price_for(entry, 0.0, tail[0][1], tail[0][2], None, root)
    if prem_stop is None:                       # the floors refuse breakeven
        prem_stop = max(0.01, round(entry * (1.0 - prem.BORN_PCT / 100.0), 2))
    rungs = 0
    for qts, bid, ask in tail:
        if bid <= prem_stop + 1e-9:
            why = "BE" if rungs == 0 else "rung"
            return _settle(opt_path, qts, entry, why, best, prem_stop, level)
        gain = (bid - entry) / entry * 100.0
        want, _k = prem.locked_for(gain, entry, prem.TIERS_LIVE, root, False)
        moved = prem.stop_price_for(entry, want, bid, ask, prem_stop, root)
        if moved is not None:
            prem_stop, rungs = moved, rungs + 1
    return _settle(opt_path, tail[-1][0], entry, "close", best, prem_stop, level)


# ------------------------------------------------------------------- build
def build():
    opt = option_paths()
    fills = {}
    with open(os.path.join(ROOT, "master_ledger.csv"), encoding="utf-8-sig",
              newline="") as fh:
        for row in csv.DictReader(fh):
            if (not row.get("occ")
                    or str(row.get("manual") or "").lower() in ("true", "1")):
                continue
            value = _f(row.get("avg_in"))
            if value and value > 0:
                fills[(row.get("date"), row["occ"])] = {
                    "fill": value, "opened_ts": _f(row.get("opened_ts")),
                    "pl": _f(row.get("pl")), "exit_avg": _f(row.get("exit_avg")),
                    "closed": row.get("closed") or ""}
    every = alerts()
    stocks = stock_paths({(a["day"], a["symbol"]) for a in every})
    trades, skipped = [], defaultdict(int)
    for alert in every:
        key = (alert["day"], alert["occ"])
        source_path = opt.get(key)
        bars = stocks.get((alert["day"], alert["symbol"]))
        if not source_path:
            skipped["no option quote path for this exact contract"] += 1
            continue
        if not bars:
            skipped["no cached 1-second stock bars for this symbol-day"] += 1
            continue
        source, path = source_path
        flat = _flat_ts(alert["day"])
        after = [q for q in path if q[0] >= alert["ts"] - 5.0 and q[0] <= flat]
        if not after:
            skipped["option path ends before the alert"] += 1
            continue
        # ---- entry 1: take the alert
        take_lag = after[0][0] - alert["ts"]
        fill = fills.get(key)
        if fill and fill.get("opened_ts") is not None and abs(
                fill["opened_ts"] - alert["ts"]) <= FILL_MATCH_WINDOW_S:
            take_entry, take_basis = fill["fill"], "real fill"
        else:
            fill = None
            take_entry, take_basis = after[0][2], "first ask"
        take_ok = take_lag <= MAX_ENTRY_LAG_S and take_entry and take_entry > 0
        # ---- entry 2: the live round-number pullback, on 1-second bars
        px0 = next((b[3] for b in bars if b[0] >= alert["ts"]), None)
        level = touch_ts = None
        why_pb = "no stock print at the alert"
        if px0 is not None:
            level = pullback.round_target(px0, alert["side"])
            deadline = alert["ts"] + PULLBACK_WINDOW_S
            why_pb = "never touched $%.0f in 10 min" % level
            for ts, low, high, _c in bars:
                if ts < alert["ts"] or ts > deadline:
                    continue
                reach = low if pullback.is_call(alert["side"]) else high
                if pullback.touched(reach, level, alert["side"]):
                    touch_ts, why_pb = ts, "touched $%.0f" % level
                    break
        pb_path = [q for q in path if touch_ts is not None and q[0] >= touch_ts
                   and q[0] <= flat]
        pb_entry = pb_basis = None
        pb_lag = None
        if touch_ts is not None and pb_path:
            pb_lag = pb_path[0][0] - touch_ts
            if (fill and fill.get("opened_ts") is not None
                    and abs(fill["opened_ts"] - touch_ts) <= 60.0):
                pb_entry, pb_basis = fill["fill"], "real fill at the touch"
            else:
                pb_entry, pb_basis = pb_path[0][2], "ask at the touch"
            if pb_lag > MAX_ENTRY_LAG_S:
                why_pb += " (option quote %.0fs late — excluded)" % pb_lag
                pb_entry = None
        elif touch_ts is not None:
            why_pb += " (no option quote after the touch)"
        row = {"alert": alert, "source": source, "path": after,
               "take_entry": take_entry if take_ok else None,
               "take_basis": take_basis, "take_lag": take_lag,
               "ledger": fill, "level": level, "touch_ts": touch_ts,
               "why_pb": why_pb, "pb_entry": pb_entry, "pb_basis": pb_basis,
               "pb_lag": pb_lag, "pb_path": pb_path, "runs": {},
               "peak_bid": max(q[1] for q in after),
               "flat": flat}
        if take_ok:
            row["runs_take_A"] = prem.simulate(
                after, take_entry, alert["symbol"], prem.TIERS_LIVE,
                False, False, flat)
        if pb_entry:
            walk = [b for b in bars if b[0] >= touch_ts and b[0] <= flat]
            band = _band(alert["symbol"])
            for code, _label, plans in STOCK_VARIANTS:
                row["runs"][code] = stock_walk(
                    walk, level, alert["side"], plans[band], pb_entry,
                    pb_path, flat)
            stop_d, target_d = pullback.exit_levels(alert["symbol"])
            row["runs"]["P0"] = stock_walk(
                walk, level, alert["side"], (stop_d, stop_d, 0.0), pb_entry,
                pb_path, flat, target=target_d)
            a_run = prem.simulate(pb_path, pb_entry, alert["symbol"],
                                  prem.TIERS_LIVE, False, False, flat)
            a_run["why"] = {"born stop": "stop", "first lock": "BE",
                            "ratchet rung": "rung"}.get(a_run["why"], a_run["why"])
            a_run["fire_ts"] = a_run["ts"]
            a_run["lag"] = 0.0          # A never leaves the option tape
            a_run["tape_ended_first"] = False
            a_run["level"] = level
            a_run["bid_before_fire"] = _bid_before(pb_path, a_run["ts"])
            row["runs"]["A"] = a_run
            row["runs"]["H"] = hybrid_walk(
                walk, level, alert["side"], plans_for_hybrid(band), pb_entry,
                pb_path, alert["symbol"], flat)
            row["stock_best"] = row["runs"]["S1"]["stock_best"]
        trades.append(row)
    return trades, skipped


def plans_for_hybrid(band):
    return dict(STOCK_VARIANTS[0][2])[band]


# ------------------------------------------------------------------ report
def summarise(trades, code):
    runs = [t["runs"][code] for t in trades if code in t["runs"]]
    pls = [r["pl"] for r in runs]
    why = defaultdict(int)
    for r in runs:
        why[r["why"]] += 1
    return {"n": len(runs), "gross": sum(pls),
            "win": 100.0 * sum(1 for p in pls if p > 0) / len(pls) if pls else 0.0,
            "avg": sum(pls) / len(pls) if pls else 0.0,
            "hold": prem.median([r["held_s"] for r in runs]) or 0.0,
            "why": dict(why)}


def write(trades, skipped, cost_note):
    scored = [t for t in trades if t["runs"]]
    out_md = os.path.join(HERE, "STOCK-STOP-REPLAY-2026-09-14.md")
    out_csv = os.path.join(HERE, "STOCK-STOP-REPLAY-2026-09-14.csv")
    days = sorted({t["alert"]["day"] for t in scored})
    L = ["# Managing off the STOCK instead of the premium — replay", "",
         "G's idea: \"alert -> round-number pullback -> arm with a $0.25 stock "
         "stop; +$0.25 in favor -> stop to breakeven; then ratchet every +$0.15 "
         "from there\", $1.00 on the Mag 7. This replays it against the live "
         "pullback stop+target rule and against our premium 5/3/5 ratchet, on "
         "the SAME pullback entries and the same real quotes. Nothing changed; "
         "no order was placed.", "",
         "Built by `reference/stock_stop_replay.py`. Stock leg: real 1-second "
         "Databento bars in `bars/stock/`. Option leg: Databento OPRA "
         "(`databento_tape_clean.csv`, ~1 quote/second) where it exists, else "
         "the Webull tapes. Entries and levels come from the live `pullback.py`.",
         "", cost_note, "",
         "## The rules", "",
         "| Variant | Stock stop | Arms at | Then | SPY/QQQ rung | Mag 7 rung |",
         "|---|---|---|---|---|---|"]
    for code, _label, plans in STOCK_VARIANTS:
        e, m = plans["etf"], plans["mag"]
        L.append("| **%s** | %.2f / %.2f | +%.2f / +%.2f | stop -> the level "
                 "(breakeven) | +%.2f | +%.2f |"
                 % (code, e[0], m[0], e[1], m[1], e[2], m[2]))
    L += ["| **P0** (live) | %.2f / %.2f | never | fixed target +%.2f / +%.2f, "
          "no ratchet | — | — |"
          % (pullback.UNDERLYING_EXITS["SPY"][0], pullback.UNDERLYING_EXITS["TSLA"][0],
             pullback.UNDERLYING_EXITS["SPY"][1], pullback.UNDERLYING_EXITS["TSLA"][1]),
          "| **A** (live premium) | -%.0f%% of the premium | +%.0f%% premium | "
          "stop -> breakeven | +%.0f%% premium | +%.0f%% premium |"
          % (prem.BORN_PCT, prem.TIERS_LIVE[-1][1][0], prem.TIERS_LIVE[-1][1][2],
             prem.TIERS_LIVE[-1][1][2]),
          "| **H** (Claude's) | %.2f / %.2f until the premium is +%.0f%% | then A |"
          " A's breakeven | +%.0f%% premium | +%.0f%% premium |"
          % (_ETF_STOP, _MAG_STOP, PREMIUM_HANDOFF_PCT,
             prem.TIERS_LIVE[-1][1][2], prem.TIERS_LIVE[-1][1][2]),
          "",
          "Every stop distance and every fixed target above is read from the "
          "live `pullback.UNDERLYING_EXITS`; the premium ladder is read from "
          "the live `ratchet_tiers.TIERS` and `settings.json`. Nothing is typed "
          "in twice.", "",
          "## Side by side — same pullback entries, same paths", "",
          "| Variant | n | Gross $ | Win % | Avg/trade | Median hold | stop | BE "
          "| rung | target | close |",
          "|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|"]
    stats = {c: summarise(scored, c) for c in ALL_VARIANTS}
    for code in ALL_VARIANTS:
        s = stats[code]
        L.append("| **%s** %s | %d | %+.0f | %.0f%% | %+.2f | %s | %d | %d | %d | %d | %d |"
                 % (code, VARIANT_LABEL[code], s["n"], s["gross"], s["win"],
                    s["avg"], prem._hold(s["hold"]), s["why"].get("stop", 0),
                    s["why"].get("BE", 0), s["why"].get("rung", 0),
                    s["why"].get("target", 0), s["why"].get("close", 0)))
    L += ["", "Webull charges $0 commission on options, so net = gross.", "",
          "## Paired bootstrap against A, %d resamples" % BOOTSTRAP_N, "",
          "| Variant | Mean difference / trade | 95% band | Resamples above zero "
          "| Can this sample decide? |", "|---|---:|---|---:|---|"]
    for code in ALL_VARIANTS:
        if code == "A":
            continue
        diffs = [t["runs"][code]["pl"] - t["runs"]["A"]["pl"] for t in scored]
        b = prem.bootstrap(diffs, n=BOOTSTRAP_N)
        if b is None:
            continue
        if all(abs(d) < 1e-9 for d in diffs):
            verdict = "identical to A on every trade"
        elif b["lo"] > 0 or b["hi"] < 0:
            verdict = "**yes — the band clears zero**"
        else:
            verdict = "no — the band spans zero"
        L.append("| %s vs A | %+.2f | %+.2f .. %+.2f | %.0f%% | %s |"
                 % (code, b["mean"], b["lo"], b["hi"],
                    100.0 * b["share_above_zero"], verdict))

    # ---- the entry question, kept separate
    both = [t for t in scored if t.get("runs_take_A")]
    take_sum = sum(t["runs_take_A"]["pl"] for t in both)
    pb_sum = sum(t["runs"]["A"]["pl"] for t in both)
    eb = prem.bootstrap([t["runs"]["A"]["pl"] - t["runs_take_A"]["pl"]
                         for t in both], n=BOOTSTRAP_N)
    never = sum(1 for t in trades if not t["runs"] and t["take_entry"])
    L += ["", "## The entry question, kept separate", "",
          "- Alerts where BOTH entries exist: **%d**. Same exit rule (A) on "
          "each: take-the-alert **%+.0f**, pullback **%+.0f**." % (len(both), take_sum, pb_sum),
          "- Paired mean difference (pullback minus take-it): **%s**, 95%% band "
          "**%s**, %s." % (
              ("%+.2f" % eb["mean"]) if eb else "n/a",
              ("%+.2f .. %+.2f" % (eb["lo"], eb["hi"])) if eb else "n/a",
              "the band spans zero so this sample cannot decide it"
              if eb and eb["lo"] < 0 < eb["hi"] else "the band clears zero"),
          "- Alerts the pullback SKIPPED that take-it would have entered: "
          "**%d**. A skipped trade is $0, not a loss." % never,
          "- The $1 level itself stays settled by the 9/9 study "
          "(`reference/PULLBACK-LEVELS.md`, 65 paired trades). This does not "
          "reopen it.", ""]

    # ---- the lag the option tape costs
    lags, costs, ended = [], [], 0
    for t in scored:
        for code in ALL_VARIANTS:
            r = t["runs"].get(code)
            if not r:
                continue
            if r.get("tape_ended_first"):
                ended += 1
                continue
            if r.get("lag") is None:
                continue
            lags.append(r["lag"])
            if r["lag"] > 1.0 and r.get("bid_before_fire") is not None:
                costs.append((r["exit"] - r["bid_before_fire"]) * 100.0)
    L += ["## What the option tape's lag costs", "",
          "A stock rule fires on the stock's clock; the option can only be sold "
          "at the next quote the tape holds.", "",
          "- Median lag from fire to the option quote used: **%.0fs**; mean "
          "**%.1fs**; worst **%.0fs**. (%d exits measured.)" % (
              prem.median(lags) or 0.0, sum(lags) / len(lags) if lags else 0.0,
              max(lags) if lags else 0.0, len(lags)),
          "- Exits where the lag was over a second: **%d**. On those the bid "
          "actually used differs from the last bid before the fire by "
          "**%s per contract** on average — that is what the gap costs."
          % (len(costs),
             ("%+.2f" % (sum(costs) / len(costs))) if costs
             else "nothing measurable; there were none"),
          "- Exits where the option tape simply ENDED before the rule fired: "
          "**%d**. Those have no lag to measure and are marked in the CSV "
          "(`tape_ended_first`); their exit is the last bid the tape holds." % ended,
          "- On the OPRA sample the tape is ~1 quote/second, so the lag is "
          "essentially zero. It is the Webull sweep days that pay.", ""]

    # ---- named cases
    L += ["## Named cases", ""]
    for contract, note in NAMED:
        hit = [t for t in trades if t["alert"]["occ"] == contract]
        if not hit:
            L.append("- **%s** — %s. **Not measurable here**: %s"
                     % (contract, note, _why_missing(contract)))
            continue
        t = hit[0]
        L.append("- **%s** (%s %s) — %s" % (contract, t["alert"]["day"],
                                            t["alert"]["time"][:5], note))
        if not t["runs"]:
            L.append("  - pullback: %s — no stock-managed trade to replay."
                     % t["why_pb"])
            continue
        L.append("  - touched $%.2f, entry $%.2f (%s), stock best +$%.2f in "
                 "favour, option max bid $%.2f."
                 % (t["level"], t["pb_entry"], t["pb_basis"],
                    t.get("stock_best") or 0.0, t["peak_bid"]))
        for code in ALL_VARIANTS:
            r = t["runs"][code]
            L.append("  - %-3s exit $%.2f (%s), %+.0f" % (code, r["exit"],
                                                          r["why"], r["pl"]))
    L.append("")

    # ---- per trade
    L += ["## Every replayed trade", "",
          "| Day | Time | Room | Contract | Touch level | Entry | Stock best | "
          "Option max bid | " + " | ".join("%s $" % c for c in ALL_VARIANTS) + " |",
          "|---|---|---|---|---:|---:|---:|---:|" + "---:|" * len(ALL_VARIANTS)]
    for t in sorted(scored, key=lambda r: (r["alert"]["day"], r["alert"]["ts"])):
        a = t["alert"]
        L.append("| %s | %s | %s | %s | $%.2f | $%.2f | +$%.2f | $%.2f | %s |"
                 % (a["day"][5:], a["time"][:5], prem._md(a["room"] or "?"),
                    a["occ"], t["level"], t["pb_entry"],
                    t.get("stock_best") or 0.0, t["peak_bid"],
                    " | ".join("%+.0f" % t["runs"][c]["pl"] for c in ALL_VARIANTS)))

    # ---- coverage
    L += ["", "## Coverage and caveats", "",
          "- Days measured: **%s**." % (", ".join(days) or "none"),
          "- Alerts on %s with an option path AND cached 1-second bars: **%d**. "
          "Of those, the pullback entered **%d**." % (
              "/".join(SYMBOLS), len(trades), len(scored)),
          "- Option quote source per contract-day: " + ", ".join(
              "%s %d" % (s, n) for s, n in sorted(
                  _count(t["source"] for t in scored).items())) + ".",
          "- Stock bars are 1-second Databento; the option tape is 1-second "
          "OPRA on the backfilled days and a 5-60s Webull sweep otherwise. A "
          "stop touched between two option quotes is invisible, so stop counts "
          "are a floor.",
          "- The OPRA backfill bought the minutes around each call, not whole "
          "sessions, so most paths end long before 15:59 and \"close\" means "
          "the end of the tape, not a real exit.",
          "- **2026-09-14 is missing and cannot be bought.** Every Databento "
          "equity dataset ends at 2026-09-14T04:00Z, so that session's "
          "per-second bars are not released yet. Re-run this script when they "
          "are; the cache means it will only pay for the new day.",
          "- No slippage, no queue, no partial fills; entries cross the ask.",
          "- The stock ladder has never traded a real dollar. This is a replay."]
    if skipped:
        L += ["", "### Alerts not replayed", "", "| Why | n |", "|---|---:|"]
        for why, n in sorted(skipped.items(), key=lambda kv: -kv[1]):
            L.append("| %s | %d |" % (why, n))

    with open(out_md + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L).rstrip() + "\n")
    os.replace(out_md + ".tmp", out_md)

    fields = (["day", "time", "room", "caller", "occ", "symbol", "side",
               "source", "touch_level", "pb_entry", "pb_entry_basis",
               "pb_option_lag_s", "take_entry", "take_entry_basis",
               "stock_best_favor", "option_max_bid", "take_A_pl"]
              + sum([["%s_exit" % c, "%s_pl" % c, "%s_why" % c, "%s_lag_s" % c,
                      "%s_tape_ended_first" % c] for c in ALL_VARIANTS], []))
    with open(out_csv + ".tmp", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fields)
        w.writeheader()
        for t in sorted(scored, key=lambda r: (r["alert"]["day"], r["alert"]["ts"])):
            a = t["alert"]
            rec = {"day": a["day"], "time": a["time"], "room": a["room"],
                   "caller": a["caller"], "occ": a["occ"], "symbol": a["symbol"],
                   "side": a["side"], "source": t["source"],
                   "touch_level": t["level"], "pb_entry": t["pb_entry"],
                   "pb_entry_basis": t["pb_basis"],
                   "pb_option_lag_s": round(t["pb_lag"], 1) if t["pb_lag"] is not None else "",
                   "take_entry": t["take_entry"],
                   "take_entry_basis": t["take_basis"],
                   "stock_best_favor": round(t.get("stock_best") or 0.0, 4),
                   "option_max_bid": t["peak_bid"],
                   "take_A_pl": (round(t["runs_take_A"]["pl"], 2)
                                 if t.get("runs_take_A") else "")}
            for c in ALL_VARIANTS:
                r = t["runs"][c]
                rec["%s_exit" % c] = r["exit"]
                rec["%s_pl" % c] = round(r["pl"], 2)
                rec["%s_why" % c] = r["why"]
                rec["%s_lag_s" % c] = ("" if r.get("lag") is None
                                       else round(r["lag"], 1))
                rec["%s_tape_ended_first" % c] = bool(r.get("tape_ended_first"))
            w.writerow(rec)
    os.replace(out_csv + ".tmp", out_csv)
    print(out_md)
    print(out_csv)
    return out_md, out_csv


def _count(values):
    out = defaultdict(int)
    for v in values:
        out[v] += 1
    return dict(out)


NAMED = (
    ("QQQ260914C00708000", "Skyy's 0DTE that the caller rode to +423%"),
    ("MSFT260914C00505000", "the bot's fastest stop-out of 9/14"),
    ("QQQ260914C00713000", "0.24 -> 0.22 in seconds"),
    ("CRWD260918C00245000", "MuggZone's CRWD"),
    ("QQQ260914P00705000", "Vero's QQQ 705P"),
    ("QQQ260914P00704000", "Demon's QQQ 704P"),
    ("TSLA260918C00357500", "Platinum ei-alerts TSLA 357.5C"),
    ("TSLA260918P00357500", "Platinum nitro TSLA 357.5P"),
)


def _why_missing(contract):
    parsed = occ_symbol.parse(contract)
    root = parsed[0] if parsed else "?"
    if root not in SYMBOLS:
        return ("%s is not one of the ten symbols this study covers (its stock "
                "leg was never bought)" % root)
    return ("it is a 2026-09-14 alert, and that session's per-second stock bars "
            "are still embargoed by Databento")


if __name__ == "__main__":
    _cost = ("Stock bars: Databento quoted **$0.1538** for the twenty "
             "symbol-days asked for (2026-09-11 and 2026-09-14). The 9/11 half "
             "($0.0732 quoted) delivered and is cached; the 9/14 half "
             "($0.0805 quoted) was refused with a 403 before any data was "
             "returned. Everything from 2026-08-11 to 2026-09-08 was already "
             "in `bars/stock/` from the 9/9 pullback study and cost nothing.")
    _trades, _skipped = build()
    write(_trades, _skipped, _cost)
