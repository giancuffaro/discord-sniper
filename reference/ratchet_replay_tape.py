#!/usr/bin/env python3
"""ratchet_replay_tape.py — is the live ratchet too tight? Ask the real quotes.

G, 9/14: "I think the ratchet is too tight."  This answers that with the only
evidence that exists — `alert_tape.csv`, the slow all-alert bid/ask sweep that
records EVERY alerted contract (not just the ones we bought), densified with
`option_tape.csv` (the ~1/sec fast bus, which only runs while a contract is
actually held).  Both feeds are Webull snapshots of the same contract, so
merging them is not vendor-mixing; OPRA/tastytrade tapes are deliberately NOT
touched here.

WHAT IT DOES
------------
For every options OPEN alert on the covered days it replays FOUR exit rules
over the SAME quote path, one contract, and reports the paired difference:

  A  LIVE 5/3/5      born stop -5% off entry; +3% gain arms the ratchet and
                     locks BREAKEVEN; every further +5% locks another +5%.
                     (born = settings.json strategy.stop_loss_pct = 5.0;
                      arm/lock/step = ratchet_tiers.TIERS = (3.0, 0.0, 5.0);
                      MIN_RUNG_TICKS=4 widens the rung, MIN_STOP_TICKS=2 and
                      the one-full-spread floor keep the stop out of the noise.)
  B  9/2 PRICE TIERS + ANTI-CLIP   under $1: arm +25 / first lock +10 / +15 a
                     rung.  $1.00-$1.99: arm +15 / BE / +10.  $2.00 and up:
                     arm +10 / +5 / +5.  Same two floors, plus the anti-clip
                     cap ANTI_CLIP_K = 0.40 — the stop may never sit closer
                     than 40% of the gain already made.
  C  A + BORN-STOP FLOOR   the initial stop distance is
                     max(5% of entry, 2 x the spread at entry, 3 ticks).
                     The rungs are A's, unchanged.
  D  B + that same born-stop floor.

Entry is the ask at the first tape quote after the alert, or the REAL fill
price when `master_ledger.csv` shows the bot filled that alert (the per-trade
table says which, per row, and a real-fill row starts its clock at the fill,
not at the alert — you cannot be stopped out of something you do not own yet).
Exit is always on the BID.  Flat at the last quote at or before 15:59 ET.

CONSERVATIVE BY CONSTRUCTION
  * The stop is checked BEFORE the ratchet on the same sweep, so a sweep that
    would have both hit the old stop and earned a higher one counts as a stop.
  * The born stop is clamped one tick under the live bid, exactly as
    webull_options does before it sends the bracket leg — a stop above the bid
    is already triggered and Webull 417s it.  On a wide spread this makes the
    real born stop TIGHTER than -5%, which is the whole complaint.
  * No slippage, no partial fills, no queue: the exit prints at the bid that
    broke the stop.  Real life is worse.

HONEST LIMITS — say these out loud with any number this prints
  * The sweep is every ~5s with positions open and ~30-60s otherwise. A stop
    that was touched between two sweeps is INVISIBLE here, so every variant's
    stop-outs are UNDERCOUNTED and every result is optimistic.
  * Entry crosses the ask. That is the live rule for a pullback touch, but a
    caller-price limit often fills better.
  * Tiny sample. See the bootstrap block before believing any ranking.
  * TICK NOTE: this replay uses webull_options.tick_step, which is symbol
    aware (SPY/QQQ/IWM $0.01 always; Penny Program $0.01 under $3 / $0.05 at
    or above; everything else $0.05 / $0.10).  LIVE ratchet_tiers.tick_size is
    symbol-BLIND ($0.01 under $3 / $0.05 above) inside ratchet_stop_price, so
    on a non-penny name the live rung floor and spread floor are computed on a
    finer grid than the exchange actually quotes.  All four variants here use
    the same symbol-aware rule, so the comparison is fair; the divergence from
    production is a separate finding.

MEASUREMENT ONLY. This file places no orders and changes no setting.
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import os
import random
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import occ as occ_symbol                                    # noqa: E402
import ratchet_tiers as rt                                  # noqa: E402
from webull_options import stop_below, tick_round, tick_step  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                                           # noqa: BLE001
    ET = dt.timezone(dt.timedelta(hours=-4))

DAYS = ("2026-09-11", "2026-09-14")
FLAT_AT = "15:59:00"            # flat here or at the last quote, whichever is first
MAX_ENTRY_LAG_S = 180.0         # a path that starts later than this is EXCLUDED
FILL_MATCH_WINDOW_S = 900.0     # ledger fill counts as this alert's fill inside it
BOOTSTRAP_N = 4000
GAP_ALARM_S = 120.0             # a hole bigger than this is reported per alert

# ---------------------------------------------------------------- the rules
BORN_PCT = rt.live_spacing()[0]                 # settings.json strategy.stop_loss_pct
TIERS_LIVE = rt.TIERS                           # ((None, (3.0, 0.0, 5.0)),)
# The 9/2 price-tiered ladder, quoted verbatim from ratchet_tiers.py's own
# docstring. It is retired in live; this is the only place it still runs.
TIERS_9_2 = ((1.00, (25.0, 10.0, 15.0)),
             (2.00, (15.0, 0.0, 10.0)),
             (None, (10.0, 5.0, 5.0)))
ANTI_CLIP_K = rt.ANTI_CLIP_K                    # 0.40
MIN_RUNG_TICKS = rt.MIN_RUNG_TICKS              # 4.0
MIN_STOP_TICKS = rt.MIN_STOP_TICKS              # 2.0

VARIANTS = (
    ("A", "LIVE flat 5/3/5", TIERS_LIVE, False, False),
    ("B", "9/2 price tiers + anti-clip", TIERS_9_2, True, False),
    ("C", "5/3/5 + born-stop floor", TIERS_LIVE, False, True),
    ("D", "9/2 tiers + anti-clip + floor", TIERS_9_2, True, True),
)


def _f(v):
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _root_of(contract):
    parsed = occ_symbol.parse(contract)
    return parsed[0] if parsed else ""


def _et(ts):
    return dt.datetime.fromtimestamp(float(ts), ET)


def _day_of(ts):
    return _et(ts).date().isoformat()


def _flat_ts(day):
    return dt.datetime.fromisoformat("%sT%s" % (day, FLAT_AT)).replace(
        tzinfo=ET).timestamp()


# ------------------------------------------------------------------- inputs
def load_paths():
    """{(day, occ): [(ts, bid, ask), ...]} from the two Webull tapes, merged.

    Both files are Webull option snapshots of the same contract; alert_tape is
    the slow all-alert sweep and option_tape the ~1/sec bus that only runs
    while a position is open. Same vendor, same quote, different cadence — so
    the merge densifies the path instead of inventing price jumps between
    feeds. Duplicate whole seconds keep the first row seen.
    """
    grouped = defaultdict(dict)
    for name, has_und in (("alert_tape.csv", True), ("option_tape.csv", False)):
        try:
            fh = open(os.path.join(ROOT, name), encoding="utf-8-sig", newline="")
        except OSError:
            continue
        with fh:
            for row in csv.DictReader(fh):
                ts, bid, ask = _f(row.get("ts")), _f(row.get("bid")), _f(row.get("ask"))
                contract = (row.get("occ") or "").strip()
                if not contract or ts is None or not bid or not ask:
                    continue
                if bid <= 0 or ask <= 0 or ask < bid:
                    continue
                day = _day_of(ts)
                if day not in DAYS:
                    continue
                grouped[(day, contract)].setdefault(int(ts), (ts, bid, ask))
    return {k: [v[t] for t in sorted(v)] for k, v in grouped.items()}


def load_underlying():
    """{(day, root): [(ts, price)]} — the only stock path we have for these
    days. It is the `und` column of alert_tape/alert_meta, i.e. one print per
    sweep (5s with positions open, 30-60s otherwise), NOT 1-second bars.
    bars/stock has no file for 2026-09-11 or 2026-09-14."""
    grouped = defaultdict(dict)
    for name, occ_col, und_col in (("alert_tape.csv", "occ", "und"),
                                   ("alert_meta.csv", "occ", "und")):
        try:
            fh = open(os.path.join(ROOT, name), encoding="utf-8-sig", newline="")
        except OSError:
            continue
        with fh:
            for row in csv.DictReader(fh):
                ts, und = _f(row.get("ts")), _f(row.get(und_col))
                root = _root_of(row.get(occ_col) or "")
                if ts is None or not und or und <= 0 or not root:
                    continue
                day = _day_of(ts)
                if day in DAYS:
                    grouped[(day, root)].setdefault(int(ts), (ts, und))
    return {k: [v[t] for t in sorted(v)] for k, v in grouped.items()}


def load_alerts():
    """Every options OPEN alert on the covered days, newest evidence first.

    alert_meta.csv `stage=alert` is the authoritative live record: it carries
    the exact OCC, the room, the caller, the caller's posted price and the
    underlying at the moment of the alert. master_alerts.csv (rebuilt daily,
    dateless expiries resolved) is folded in for anything alert_meta missed
    and for the outcome the policy engine reached.
    """
    seen, alerts = {}, []
    with open(os.path.join(ROOT, "alert_meta.csv"), encoding="utf-8-sig",
              newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("stage") != "alert" or row.get("date") not in DAYS:
                continue
            contract, ts = (row.get("occ") or "").strip(), _f(row.get("ts"))
            if not contract or ts is None:
                continue
            if (row.get("side") or "").upper() not in ("CALLS", "PUTS"):
                continue
            key = (row["date"], contract, int(ts // 60))
            if key in seen:            # the same post relayed twice
                continue
            seen[key] = True
            alerts.append({
                "day": row["date"], "time": row.get("time") or "",
                "ts": ts, "occ": contract, "root": _root_of(contract),
                "symbol": row.get("symbol") or "", "side": row.get("side") or "",
                "strike": _f(row.get("strike")), "expiry": row.get("expiry") or "",
                "room": row.get("room") or "", "caller": row.get("caller") or "",
                "their_price": _f(row.get("their_price")),
                "und_at_alert": _f(row.get("und")),
                "outcome": "", "source": "alert_meta",
            })
    by_contract = {(a["day"], a["occ"]): a for a in alerts}
    with open(os.path.join(ROOT, "master_alerts.csv"), encoding="utf-8-sig",
              newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("date") not in DAYS:
                continue
            side = (row.get("side") or "").upper()
            if side not in ("CALLS", "PUTS"):
                continue
            try:
                contract = occ_symbol.build(row.get("symbol"), row.get("expiry"),
                                            side, _f(row.get("strike")))
            except (ValueError, TypeError):
                continue
            hit = by_contract.get((row["date"], contract))
            if hit is not None:
                hit["outcome"] = hit["outcome"] or (row.get("outcome") or "")
                hit["room"] = hit["room"] or (row.get("room") or "")
                hit["caller"] = hit["caller"] or (row.get("caller") or "")
                if hit["their_price"] is None:
                    hit["their_price"] = _f(row.get("their_price"))
                continue
            clock = (row.get("time") or "")[:8]
            if len(clock) == 5:
                clock += ":00"
            try:
                ts = dt.datetime.fromisoformat("%sT%s" % (row["date"], clock)
                                               ).replace(tzinfo=ET).timestamp()
            except ValueError:
                continue
            entry = {
                "day": row["date"], "time": clock, "ts": ts, "occ": contract,
                "root": _root_of(contract), "symbol": row.get("symbol") or "",
                "side": side, "strike": _f(row.get("strike")),
                "expiry": row.get("expiry") or "", "room": row.get("room") or "",
                "caller": row.get("caller") or "",
                "their_price": _f(row.get("their_price")),
                "und_at_alert": None, "outcome": row.get("outcome") or "",
                "source": "master_alerts",
            }
            by_contract[(row["date"], contract)] = entry
            alerts.append(entry)
    return sorted(alerts, key=lambda a: (a["day"], a["ts"]))


def load_fills():
    """{(day, occ): {...}} — what the bot really paid, from the reconciled
    ledger. Hand trades (`manual`) and anything not in the live account are
    excluded: they are G's own, never this bot's entries."""
    out = {}
    with open(os.path.join(ROOT, "master_ledger.csv"), encoding="utf-8-sig",
              newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("date") not in DAYS or not row.get("occ"):
                continue
            if str(row.get("manual") or "").lower() in ("true", "1"):
                continue
            fill = _f(row.get("avg_in"))
            if not fill or fill <= 0:
                continue
            out[(row["date"], row["occ"])] = {
                "fill": fill, "opened_ts": _f(row.get("opened_ts")),
                "pl": _f(row.get("pl")), "exit_avg": _f(row.get("exit_avg")),
                "exit_by": row.get("exit_by") or "", "closed": row.get("closed") or "",
            }
    return out


# --------------------------------------------------------------- the ratchet
def plan_for(entry, tiers, root):
    """(arm, first_lock, step) for this premium under this ladder, with
    ratchet_tiers' FLOOR 1 applied: a rung must clear MIN_RUNG_TICKS ticks."""
    plan = tiers[-1][1]
    for ceiling, candidate in tiers:
        if ceiling is None or entry < ceiling:
            plan = candidate
            break
    arm, first, step = plan
    if entry > 0:
        min_step = (tick_step(entry, root) * MIN_RUNG_TICKS) / entry * 100.0
        if step < min_step:
            step = round(min_step, 2)
    return arm, first, step


def locked_for(gain_pct, entry, tiers, root, anticlip):
    """(locked_pct, rung_index) or (None, None) before the ladder arms.

    Mirrors ratchet_tiers.ratchet_locked_pct exactly, and applies the 9/2
    anti-clip cap on top when this variant uses it.
    """
    arm, first, step = plan_for(entry, tiers, root)
    if step <= 0 or gain_pct is None or gain_pct < arm - 1e-9:
        return None, None
    k = int((gain_pct - arm + 1e-9) // step)
    locked = first + step * k
    if anticlip:
        locked = min(locked, round((1.0 - ANTI_CLIP_K) * gain_pct, 2))
    return locked, k


def stop_price_for(entry, locked_pct, bid, ask, current_stop, root):
    """Mirror of ratchet_tiers.ratchet_stop_price for a long, with the
    symbol-aware tick (see the module docstring's TICK NOTE). None when the
    move is unsafe or is not an improvement."""
    if locked_pct is None or not entry or entry <= 0:
        return None
    want = entry * (1.0 + locked_pct / 100.0)
    tick = tick_step(want, root)
    if bid and bid > 0:
        spread = (ask - bid) if (ask and ask > bid) else 0.0
        ceiling = bid - max(spread, tick * MIN_STOP_TICKS)
        if want > ceiling:
            want = ceiling
    want = round(max(0.01, want), 2)
    if current_stop is not None and want <= float(current_stop) + 1e-9:
        return None
    return want


def born_stop_for(entry, first_bid, first_ask, root, floored):
    """Where the bracket's stop leg is born.

    Unfloored: webull_options.stop_below(entry, 5%) — production's own call.
    Floored (variants C/D): the distance is widened to
    max(5% of entry, 2 x the entry spread, 3 ticks) first.

    Then the BROKER CLAMP both paths must obey: a SELL stop at or above the
    live bid is already triggered and Webull rejects it (417), so the real
    resting stop is capped one tick under the bid. That clamp only ever
    TIGHTENS the stop, and on a wide spread it is what actually sets it.
    """
    step = tick_step(entry, root)
    if floored:
        spread = max(0.0, (first_ask or 0.0) - (first_bid or 0.0))
        distance = max(entry * BORN_PCT / 100.0, 2.0 * spread, 3.0 * step)
        stop = max(0.01, float(tick_round(entry - distance, root)))
        if stop >= entry - 1e-9:
            stop = max(0.01, round(entry - step, 2))
    else:
        stop = stop_below(entry, BORN_PCT, root)
    clamped = False
    if first_bid and first_bid > 0:
        ceiling = round(first_bid - tick_step(first_bid, root), 2)
        if ceiling >= 0.01 and stop >= ceiling:
            stop = max(0.01, float(tick_round(ceiling, root)))
            clamped = True
    return stop, clamped


def simulate(path, entry, root, tiers, anticlip, floored, flat_ts):
    """One contract, one exit rule, one real quote path. Stop before ratchet."""
    walk = [r for r in path if r[0] <= flat_ts] or path[:1]
    stop, clamped = born_stop_for(entry, walk[0][1], walk[0][2], root, floored)
    born = stop
    locked_now, rung_now, moves = None, None, 0
    peak_bid, peak_ts = walk[0][1], walk[0][0]
    for ts, bid, ask in walk:
        if bid > peak_bid:
            peak_bid, peak_ts = bid, ts
        if bid <= stop + 1e-9:                  # STOP FIRST — conservative
            if moves == 0:
                why = "born stop"
            elif rung_now == 0:
                why = "first lock"
            else:
                why = "ratchet rung"
            return {"exit": bid, "ts": ts, "why": why, "stop": stop,
                    "born": born, "clamped": clamped, "moves": moves,
                    "locked": locked_now, "peak_bid": peak_bid,
                    "peak_ts": peak_ts, "held_s": ts - walk[0][0],
                    "pl": (bid - entry) * 100.0,
                    "pct": (bid - entry) / entry * 100.0}
        gain = (bid - entry) / entry * 100.0
        locked, rung = locked_for(gain, entry, tiers, root, anticlip)
        moved = stop_price_for(entry, locked, bid, ask, stop, root)
        if moved is not None:
            stop, locked_now, rung_now = moved, locked, rung
            moves += 1
    ts, bid, _ask = walk[-1]
    return {"exit": bid, "ts": ts, "why": "close", "stop": stop, "born": born,
            "clamped": clamped, "moves": moves, "locked": locked_now,
            "peak_bid": peak_bid, "peak_ts": peak_ts,
            "held_s": ts - walk[0][0], "pl": (bid - entry) * 100.0,
            "pct": (bid - entry) / entry * 100.0}


# ------------------------------------------------------------------ pullback
MANAGED = ("SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA",
           "META", "TSLA", "AMD")
PULLBACK_WINDOW_S = 600.0       # settings.json pullback.timeout_seconds


def round_target(px, side):
    """pullback.round_target: a call waits for the dollar BELOW, a put for the
    dollar ABOVE, and already being within a cent of one counts as there."""
    nearest = round(px)
    if abs(px - nearest) < 0.01:
        return float(nearest)
    return (float(math.floor(px)) if str(side).upper().startswith("C")
            else float(math.ceil(px)))


def touched(px, target, side):
    return (px <= target + 1e-9 if str(side).upper().startswith("C")
            else px >= target - 1e-9)


def pullback_entry(alert, und_path, path):
    """(basis, ts, ask) for the live round-number wait, or (reason, None, None).

    Only the symbols pullback.MANAGED covers are deferred to the watcher; the
    bridge routes everything else straight down the instant path.
    """
    root = alert["root"]
    if root not in MANAGED:
        return "not a round-number symbol (instant entry)", None, None
    stock = [(ts, px) for ts, px in und_path if ts >= alert["ts"] - 60.0]
    at_alert = alert.get("und_at_alert")
    if at_alert is None:
        near = [p for p in stock if p[0] <= alert["ts"] + 60.0]
        at_alert = near[0][1] if near else None
    if at_alert is None:
        return "no underlying print at the alert", None, None
    target = round_target(at_alert, alert["side"])
    deadline = alert["ts"] + PULLBACK_WINDOW_S
    for ts, px in stock:
        if ts < alert["ts"] or ts > deadline:
            continue
        if touched(px, target, alert["side"]):
            after = [r for r in path if r[0] >= ts]
            if not after:
                return "touched $%.0f but no option quote there" % target, None, None
            return ("touched $%.0f" % target), after[0][0], after[0][2]
    return "never touched $%.0f in 10 min" % target, None, None


# ----------------------------------------------------------------- bootstrap
def bootstrap(diffs, n=BOOTSTRAP_N, seed=20260914):
    """Paired resample of the per-trade differences. Returns mean, the 2.5/97.5
    band and the share of resamples above zero. With a handful of trades this
    band is wide on purpose — that is the answer, not a defect."""
    if not diffs:
        return None
    rng = random.Random(seed)
    k = len(diffs)
    means = sorted(sum(rng.choice(diffs) for _ in range(k)) / k for _ in range(n))
    return {
        "mean": sum(diffs) / k,
        "lo": means[int(0.025 * n)],
        "hi": means[min(n - 1, int(0.975 * n))],
        "share_above_zero": sum(1 for m in means if m > 0) / float(n),
        "n": k,
    }


def gap_before(walk, until_ts, limit=GAP_ALARM_S):
    """Did the sweep go dark for longer than `limit` at any point up to
    `until_ts`? If it did, the price that ended this trade was never recorded
    and the exit below is only the next thing the tape happened to see."""
    return any(walk[i + 1][0] - walk[i][0] > limit and walk[i][0] <= until_ts
               for i in range(len(walk) - 1))


def median(values):
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0


# --------------------------------------------------------------------- build
def build():
    paths, unders, alerts, fills = (load_paths(), load_underlying(),
                                    load_alerts(), load_fills())
    trades, excluded = [], []
    for alert in alerts:
        key = (alert["day"], alert["occ"])
        path = paths.get(key) or []
        after = [r for r in path if r[0] >= alert["ts"] - 5.0]
        if not after:
            excluded.append((alert, "no quote path for this exact contract"))
            continue
        lag = after[0][0] - alert["ts"]
        fill = fills.get(key)
        if fill and fill.get("opened_ts") is not None and abs(
                fill["opened_ts"] - alert["ts"]) <= FILL_MATCH_WINDOW_S:
            # A real fill IS the entry evidence — an exact price and an exact
            # time from the broker. The 3-minute tape gate exists to stop us
            # inventing an entry from a stale quote, so it does not apply here.
            entry, basis, late = fill["fill"], "real fill", False
            sim_from = max(alert["ts"], fill["opened_ts"])
        else:
            fill = None
            entry, basis = after[0][2], "first ask"
            sim_from = after[0][0]
            late = lag > MAX_ENTRY_LAG_S
        walk = [r for r in after if r[0] >= sim_from] or after[:1]
        if not entry or entry <= 0:
            excluded.append((alert, "no usable entry price"))
            continue
        # The gate that actually matters: how long after we would have OWNED
        # it does the tape start quoting? A real fill with a 50-minute hole
        # before its first quote is no more scoreable than a late alert.
        if walk[0][0] - sim_from > MAX_ENTRY_LAG_S:
            late = True
        flat = _flat_ts(alert["day"])
        walk = [r for r in walk if r[0] <= flat] or walk[:1]
        gaps = [walk[i + 1][0] - walk[i][0] for i in range(len(walk) - 1)]
        row = {
            "alert": alert, "entry": entry, "basis": basis, "path": walk,
            "late": late, "lag": lag, "n_quotes": len(walk),
            "median_gap": median(gaps) or 0.0,
            "big_gaps": sum(1 for g in gaps if g > GAP_ALARM_S),
            "max_gap": max(gaps) if gaps else 0.0,
            "last_ts": walk[-1][0],
            "reaches_close": walk[-1][0] >= flat - 60.0,
            "spread_at_entry": walk[0][2] - walk[0][1],
            "ledger": fill,
            "runs": {},
        }
        for code, _label, tiers, anticlip, floored in VARIANTS:
            row["runs"][code] = simulate(walk, entry, alert["root"], tiers,
                                         anticlip, floored, flat)
        # A hole in the sweep before the exit means the stop was probably hit
        # inside it and we never saw the price that did it. Those rows keep
        # their place in the table but are quarantined out of the clean total.
        row["gap_before_exit"] = gap_before(
            walk, max(row["runs"][c]["ts"] for c in row["runs"]))
        pb_why, pb_ts, pb_ask = pullback_entry(
            alert, unders.get((alert["day"], alert["root"])) or [], walk)
        row["pullback_why"] = pb_why
        row["pullback_ts"] = pb_ts
        row["pullback_entry"] = pb_ask
        if pb_ask:
            pb_path = [r for r in walk if r[0] >= pb_ts]
            run = simulate(pb_path, pb_ask, alert["root"], TIERS_LIVE,
                           False, False, flat)
            row["pullback_run"] = run
            row["pullback_gap"] = gap_before(pb_path, run["ts"])
        else:
            row["pullback_run"] = None
            row["pullback_gap"] = False
        trades.append(row)
    return trades, excluded


# -------------------------------------------------------------------- report
def summarise(trades, code):
    runs = [t["runs"][code] for t in trades]
    pls = [r["pl"] for r in runs]
    wins = [p for p in pls if p > 0]
    why = defaultdict(int)
    for r in runs:
        why[r["why"]] += 1
    return {
        "n": len(runs), "gross": sum(pls),
        "win_pct": (100.0 * len(wins) / len(runs)) if runs else 0.0,
        "avg": (sum(pls) / len(runs)) if runs else 0.0,
        "median_hold": median([r["held_s"] for r in runs]) or 0.0,
        "why": dict(why),
    }


def hhmm(ts):
    return _et(ts).strftime("%H:%M:%S")


def write(trades, excluded):
    out_md = os.path.join(HERE, "RATCHET-REPLAY-TAPE-2026-09-14.md")
    out_csv = os.path.join(HERE, "RATCHET-REPLAY-TAPE-2026-09-14.csv")
    # SCORED is the honest sample: the tape quoted the contract within 3
    # minutes of the alert, or the bot really filled it. LATE rows are
    # replayed and shown, but their entry is a quote from minutes after the
    # call, so they answer a different question and never enter a total.
    scored = [t for t in trades if not t["late"]]
    late = [t for t in trades if t["late"]]
    clean = [t for t in scored if not t["gap_before_exit"]]
    stats = {code: summarise(scored, code) for code, _l, _t, _a, _f in VARIANTS}
    clean_stats = {code: summarise(clean, code) for code, _l, _t, _a, _f in VARIANTS}

    L = ["# Ratchet replay on real quotes — 2026-09-11 and 2026-09-14", "",
         "G asked whether the live ratchet is too tight. This replays four exit "
         "rules over the SAME recorded bid/ask paths, one contract each, and "
         "reports the PAIRED difference against the live rule. It changes no "
         "setting and places no order.", "",
         "Built by `reference/ratchet_replay_tape.py` from `alert_tape.csv` + "
         "`option_tape.csv` (quotes), `alert_meta.csv` + `master_alerts.csv` "
         "(alerts) and `master_ledger.csv` (real fills). Read that file's "
         "docstring for the full assumption list.", "",
         "## The four rules", "",
         "| Variant | Born stop | Arms at | First lock | Rung | Anti-clip |",
         "|---|---|---|---|---|---|",
         "| **A — LIVE** | -%.0f%% off entry | +%.0f%% | breakeven | +%.0f%% | off |"
         % (BORN_PCT, TIERS_LIVE[-1][1][0], TIERS_LIVE[-1][1][2]),
         "| **B — 9/2 tiers** | -%.0f%% off entry | +25 / +15 / +10%% by premium "
         "(<$1 / $1-1.99 / $2+) | +10%% / BE / +5%% | +15 / +10 / +5%% | on, k=%.2f |"
         % (BORN_PCT, ANTI_CLIP_K),
         "| **C — A + floor** | max(-%.0f%%, 2x spread, 3 ticks) | +%.0f%% | "
         "breakeven | +%.0f%% | off |"
         % (BORN_PCT, TIERS_LIVE[-1][1][0], TIERS_LIVE[-1][1][2]),
         "| **D — B + floor** | max(-%.0f%%, 2x spread, 3 ticks) | as B | as B | "
         "as B | on, k=%.2f |" % (BORN_PCT, ANTI_CLIP_K), "",
         "Both floors from `ratchet_tiers.py` run in every variant: a rung must "
         "clear %d ticks (MIN_RUNG_TICKS) and a stop may never sit inside one "
         "full spread or %d ticks of the bid (MIN_STOP_TICKS). Every variant "
         "also obeys the broker clamp — a resting SELL stop is capped one tick "
         "under the live bid, because Webull 417s one placed above it."
         % (int(MIN_RUNG_TICKS), int(MIN_STOP_TICKS)), "",
         "## Result", "",
         "| Variant | n | Gross $ | Net $ (0 commission) | Win % | Avg/trade | "
         "Median hold | Born stop | First lock | Ratchet rung | Close |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for code, label, _t, _a, _f in VARIANTS:
        s = stats[code]
        L.append("| **%s** %s | %d | %+.0f | %+.0f | %.0f%% | %+.2f | %s | %d | %d | %d | %d |"
                 % (code, label, s["n"], s["gross"], s["gross"], s["win_pct"],
                    s["avg"], _hold(s["median_hold"]),
                    s["why"].get("born stop", 0), s["why"].get("first lock", 0),
                    s["why"].get("ratchet rung", 0), s["why"].get("close", 0)))
    L += ["", "Webull charges $0 commission on options, so net = gross.", "",
          "One row dominates those dollars: **%s**. Its sweep has a hole of "
          "more than two minutes before the exit, so the price that broke its "
          "stop was never recorded and every variant marks it at whatever the "
          "tape showed next. Same subset, gap-damaged rows dropped:" % _worst(scored),
          "",
          "| Variant | n (gap-clean) | Gross $ | Win % | Avg/trade | Born stop | "
          "First lock | Ratchet rung | Close |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for code, label, _t, _a, _f in VARIANTS:
        s = clean_stats[code]
        L.append("| **%s** %s | %d | %+.0f | %.0f%% | %+.2f | %d | %d | %d | %d |"
                 % (code, label, s["n"], s["gross"], s["win_pct"], s["avg"],
                    s["why"].get("born stop", 0), s["why"].get("first lock", 0),
                    s["why"].get("ratchet rung", 0), s["why"].get("close", 0)))
    L += ["", "## Paired comparison against A (same trades, same paths)", ""]
    for label, sample in (("All %d scored trades" % len(scored), scored),
                          ("Gap-clean subset (%d)" % len(clean), clean)):
        L += ["**%s**" % label, ""]
        L += ["| Variant | Mean difference / trade | 95%% bootstrap band (%d resamples) | "
              "Resamples above zero | Verdict |" % BOOTSTRAP_N,
              "|---|---:|---|---:|---|"]
        for code, _lab, _t, _a, _f in VARIANTS:
            if code == "A":
                continue
            diffs = [t["runs"][code]["pl"] - t["runs"]["A"]["pl"] for t in sample]
            b = bootstrap(diffs)
            if b is None:
                continue
            if all(abs(d) < 1e-9 for d in diffs):
                verdict = "identical to A on **every** trade in this sample"
            elif b["lo"] > 0 or b["hi"] < 0:
                verdict = "real at this sample"
            else:
                verdict = ("**cannot be decided at this sample** — the band "
                           "spans zero")
            L.append("| %s vs A | %+.2f | %+.2f .. %+.2f | %.0f%% | %s |"
                     % (code, b["mean"], b["lo"], b["hi"],
                        100.0 * b["share_above_zero"], verdict))
        L.append("")
    L += ["The band is the 2.5th-97.5th percentile of the resampled MEAN "
          "difference. A band that contains zero means this sample cannot tell "
          "the two rules apart, whatever the totals say.", "",
          "## Where the money actually was", "",
          "This is the answer to \"is it too tight\": how far the bid got above "
          "the entry before the exit rule took it off, per trade, under A.", "",
          "| Day | Time | Contract | Entry | Best bid | Peak gain | A took | Gave back |",
          "|---|---|---|---:|---:|---:|---:|---:|"]
    gave_back = 0
    for t in sorted(scored, key=lambda r: (r["alert"]["day"], r["alert"]["ts"])):
        a, r = t["alert"], t["runs"]["A"]
        peak_pct = (r["peak_bid"] - t["entry"]) / t["entry"] * 100.0
        if peak_pct >= 3.0 and r["pct"] <= 0.0:
            gave_back += 1
        L.append("| %s | %s | %s | $%.2f | $%.2f | %+.1f%% | %+.1f%% | %.1f pts |"
                 % (a["day"][5:], a["time"][:5], a["occ"], t["entry"],
                    r["peak_bid"], peak_pct, r["pct"], peak_pct - r["pct"]))
    armed = sum(1 for t in scored
                if (t["runs"]["A"]["peak_bid"] - t["entry"]) / t["entry"] * 100.0 >= 3.0)
    L += ["", "- Trades whose bid ever reached the **+3%% arm**: **%d of %d**."
          % (armed, len(scored)),
          "- Trades that armed the ratchet and still came out at or below "
          "entry: **%d**. That is the population the complaint is about." % gave_back,
          "- If the bid never reached +3%, no arm/rung setting could have "
          "changed that trade; only the born stop could.", ""]

    L += ["## Named cases", ""]
    for occ_want, note in NAMED:
        hit = [t for t in trades if t["alert"]["occ"] == occ_want]
        if not hit:
            L.append("- **%s** — %s. No replayable path: %s" % (
                occ_want, note, _why_excluded(occ_want, excluded)))
            continue
        t = hit[0]
        a = t["alert"]
        L.append("- **%s %s %s %s** (%s, %s, %s) — %s%s" % (
            a["symbol"], _strike(a), a["side"][0], a["expiry"],
            a["room"] or "?", a["caller"] or "?", a["time"][:5], note,
            "  **LATE START — not in any total.** The tape's first quote for "
            "this contract is %.0f minutes after the call, so the entry below "
            "is a price from that later moment, not the one the alert offered."
            % (t["lag"] / 60.0) if t["late"] else ""))
        L.append("  - entry $%.2f (%s), spread at entry $%.2f, max bid $%.2f at %s, "
                 "%d quotes, first quote %.0fs after the alert.%s"
                 % (t["entry"], t["basis"], t["spread_at_entry"],
                    t["runs"]["A"]["peak_bid"], hhmm(t["runs"]["A"]["peak_ts"]),
                    t["n_quotes"], t["lag"],
                    "  Sweep hole > 2 min before the exit: the price that broke "
                    "the stop was never recorded." if t["gap_before_exit"] else ""))
        for code, _label, _tt, _aa, _ff in VARIANTS:
            r = t["runs"][code]
            L.append("  - %s: born stop $%.2f%s -> exit $%.2f at %s (%s), %+.0f"
                     % (code, r["born"], " (clamped to the bid)" if r["clamped"] else "",
                        r["exit"], hhmm(r["ts"]), r["why"], r["pl"]))
        if t["ledger"]:
            led = t["ledger"]
            L.append("  - REAL: bot filled $%.2f, out $%s at %s, %s%s."
                     % (led["fill"],
                        ("%.2f" % led["exit_avg"]) if led["exit_avg"] else "?",
                        led["closed"] or "?",
                        ("%+.0f" % led["pl"]) if led["pl"] is not None else "?",
                        (" (%s)" % led["exit_by"]) if led["exit_by"] else ""))
    L.append("")

    L += ["## Every replayed alert", "",
          "`!` marks a sweep hole longer than two minutes before the exit — "
          "that row's exit price is the next thing the tape saw, not the price "
          "that broke the stop.", ""]
    for heading, sample in (("### Scored", scored),
                            ("### Late start — shown, never totalled", late)):
        if not sample:
            continue
        L += [heading, "",
              "| Day | Time | Room | Caller | Contract | Entry basis | Entry | "
              "A exit / $ | B exit / $ | C exit / $ | D exit / $ | Max bid | Max bid at |",
              "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
        for t in sorted(sample, key=lambda r: (r["alert"]["day"], r["alert"]["ts"])):
            a = t["alert"]
            cells = ["$%.2f / %+.0f" % (t["runs"][c]["exit"], t["runs"][c]["pl"])
                     for c in ("A", "B", "C", "D")]
            L.append("| %s | %s | %s | %s | %s %s%s %s | %s%s | $%.2f | %s | $%.2f | %s |"
                     % (a["day"][5:], a["time"][:5], _md(a["room"]), _md(a["caller"]),
                        a["symbol"], _strike(a), a["side"][0], a["expiry"],
                        t["basis"], " `!`" if t["gap_before_exit"] else "",
                        t["entry"], " | ".join(cells),
                        t["runs"]["A"]["peak_bid"], hhmm(t["runs"]["A"]["peak_ts"])))
        L.append("")

    L += ["## Tape coverage, per alert", "",
          "Sweep granularity is the biggest caveat in this file. A stop touched "
          "between two sweeps is invisible, so every stop-out count below is a "
          "FLOOR and every P&L an over-estimate.", "",
          "| Day | Time | Contract | First quote after alert | Quotes | "
          "Median sweep | Largest gap | Gaps > 2 min | Last quote | Reaches 15:59? |",
          "|---|---|---|---:|---:|---:|---:|---:|---|---|"]
    for t in sorted(trades, key=lambda r: (r["alert"]["day"], r["alert"]["ts"])):
        a = t["alert"]
        L.append("| %s | %s | %s | %.0fs | %d | %.0fs | %.0fs | %d | %s | %s |"
                 % (a["day"][5:], a["time"][:5], a["occ"], t["lag"], t["n_quotes"],
                    t["median_gap"], t["max_gap"], t["big_gaps"],
                    hhmm(t["last_ts"]), "yes" if t["reaches_close"] else "**no**"))
    L += ["", "- Replayed and scored: **%d**. Replayed but late-start (never "
          "totalled): **%d**. Excluded outright: **%d**."
          % (len(scored), len(late), len(excluded)),
          "- Scored rows with a sweep hole > 2 min before the exit: **%d**. "
          "Gap-clean scored rows: **%d**."
          % (len(scored) - len(clean), len(clean)),
          "- Paths that reach 15:59 ET: **%d of %d**. The rest are marked at the "
          "last quote the tape holds, which is not a real exit."
          % (sum(1 for t in trades if t["reaches_close"]), len(trades)),
          "- No slippage, no queue, no partial fills. The entry crosses the ask "
          "and the exit prints at the bid that broke the stop. Real life is worse.",
          "- %d scored trades over two sessions is not a sample that can settle "
          "a trading rule. It can only rule things out." % len(scored),
          "- Midas's SPY 760P posted \"@ 760.40\" — that is SPY's price, not the "
          "premium. This replay never used it (no bot fill, so the entry is the "
          "first recorded ask, $1.17). The daily caller reports did use it, "
          "which is fixed separately."]
    if excluded:
        L += ["", "### Excluded alerts", "",
              "| Day | Time | Contract | Why |", "|---|---|---|---|"]
        for a, why in excluded:
            L.append("| %s | %s | %s | %s |"
                     % (a["day"][5:], a["time"][:5], a["occ"], why))

    # ------------------------------------------------------------- entries
    L += ["", "## The OTHER question: the entry", "",
          "Same alerts, same variant-A exit rule. \"Take it\" crosses the ask at "
          "the first quote after the alert. \"Pullback\" is the live rule: for "
          "the symbols `pullback.MANAGED` covers, wait up to 10 minutes for the "
          "stock to touch the next whole dollar (a dip for a call, a bounce for "
          "a put) and cross the ask there; never touched = never entered.", "",
          "**Coverage warning, and it is severe.** `bars/stock` holds no "
          "1-second file for 2026-09-11 or 2026-09-14, so the only underlying "
          "path available is the `und` column of the alert sweep — one print "
          "every 5 to 60 seconds. A dollar level tagged between two prints is "
          "invisible, so this UNDERSTATES how often the pullback would have "
          "filled. Re-run it if per-second bars for these days ever arrive.", "",
          "| Day | Time | Contract | Take-it entry | Take-it $ (A) | Pullback | "
          "Pullback entry | Pullback $ (A) |",
          "|---|---|---|---:|---:|---|---:|---:|"]
    take_n = take_sum = pb_n = pb_sum = 0
    for t in sorted(scored, key=lambda r: (r["alert"]["day"], r["alert"]["ts"])):
        a = t["alert"]
        take_n += 1
        take_sum += t["runs"]["A"]["pl"]
        pr = t["pullback_run"]
        if pr:
            pb_n += 1
            pb_sum += pr["pl"]
        L.append("| %s | %s | %s | $%.2f | %+.0f%s | %s | %s | %s%s |"
                 % (a["day"][5:], a["time"][:5], a["occ"], t["entry"],
                    t["runs"]["A"]["pl"], " `!`" if t["gap_before_exit"] else "",
                    t["pullback_why"],
                    ("$%.2f" % t["pullback_entry"]) if t["pullback_entry"] else "—",
                    ("%+.0f" % pr["pl"]) if pr else "—",
                    " `!`" if t["pullback_gap"] else ""))
    managed = [t for t in scored if t["alert"]["root"] in MANAGED]
    m_take = sum(t["runs"]["A"]["pl"] for t in managed)
    m_pb = sum(t["pullback_run"]["pl"] for t in managed if t["pullback_run"])
    paired = [t for t in managed if t["pullback_run"]
              and not t["gap_before_exit"] and not t["pullback_gap"]]
    p_take = sum(t["runs"]["A"]["pl"] for t in paired)
    p_pb = sum(t["pullback_run"]["pl"] for t in paired)
    pb_boot = bootstrap([t["pullback_run"]["pl"] - t["runs"]["A"]["pl"]
                         for t in paired])
    L += ["", "`!` again marks a sweep hole before that exit.", "",
          "- Take-it fills: **%d**, **%+.0f** under variant A." % (take_n, take_sum),
          "- Pullback fills: **%d**, **%+.0f** under variant A." % (pb_n, pb_sum),
          "- On the **%d round-number-eligible alerts only**: take-it **%+.0f**, "
          "pullback **%+.0f** — and the pullback simply did not enter %d of them."
          % (len(managed), m_take, m_pb, len(managed) - pb_n),
          "- **The only honest paired comparison** is the %d alerts where BOTH "
          "rules entered and neither exit fell in a sweep hole: take-it "
          "**%+.0f**, pullback **%+.0f**, mean difference **%s/trade**, "
          "95%% band **%s**. %s"
          % (len(paired), p_take, p_pb,
             ("%+.2f" % pb_boot["mean"]) if pb_boot else "n/a",
             ("%+.2f .. %+.2f" % (pb_boot["lo"], pb_boot["hi"])) if pb_boot else "n/a",
             "Nothing in this sample separates them." if pb_boot
             and pb_boot["lo"] < 0 < pb_boot["hi"] else
             "The band clears zero — but on %d trades, read it as a hint."
             % len(paired) if pb_boot else ""),
          "- For contrast, the 9/9 study that SETTLED the $1 level "
          "(`reference/PULLBACK-LEVELS.md`) used 65 paired trades on real "
          "1-second stock bars. This is not that. It does not overturn it.",
          "- A skipped entry is $0, not a loss. Whether that is good depends on "
          "the trades it skips, which is the point of the table above.",
          "- **Skyy's QQQ 708C is the case in point and it is not in this table**: "
          "its tape path starts 10.8 minutes after the call, so neither entry "
          "rule can be scored on it. What is recorded is that the contract was "
          "$0.75 at the call and the caller posted out at $3.92 (+423%) at "
          "13:14 — a move the $1 pullback wait would have had to be standing in "
          "front of, and QQQ's next round number below 706.95 is 706."]

    with open(out_md + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L).rstrip() + "\n")
    os.replace(out_md + ".tmp", out_md)

    fields = ["day", "time", "room", "caller", "occ", "symbol", "side", "strike",
              "expiry", "their_price", "entry", "entry_basis", "scored",
              "gap_before_exit", "spread_at_entry",
              "first_quote_lag_s", "quotes", "median_gap_s", "max_gap_s",
              "gaps_over_2min", "last_quote", "reaches_close", "peak_bid",
              "peak_bid_at", "pullback_why", "pullback_entry", "pullback_pl_A"]
    for code, _l, _t, _a, _f in VARIANTS:
        fields += ["%s_exit" % code, "%s_pl" % code, "%s_why" % code,
                   "%s_born_stop" % code, "%s_stop_moves" % code,
                   "%s_held_s" % code]
    with open(out_csv + ".tmp", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fields)
        w.writeheader()
        for t in sorted(trades, key=lambda r: (r["alert"]["day"], r["alert"]["ts"])):
            a = t["alert"]
            rec = {"day": a["day"], "time": a["time"], "room": a["room"],
                   "caller": a["caller"], "occ": a["occ"], "symbol": a["symbol"],
                   "side": a["side"], "strike": a["strike"], "expiry": a["expiry"],
                   "their_price": a["their_price"], "entry": round(t["entry"], 4),
                   "entry_basis": t["basis"], "scored": not t["late"],
                   "gap_before_exit": t["gap_before_exit"],
                   "spread_at_entry": round(t["spread_at_entry"], 4),
                   "first_quote_lag_s": round(t["lag"], 1),
                   "quotes": t["n_quotes"], "median_gap_s": round(t["median_gap"], 1),
                   "max_gap_s": round(t["max_gap"], 1),
                   "gaps_over_2min": t["big_gaps"], "last_quote": hhmm(t["last_ts"]),
                   "reaches_close": t["reaches_close"],
                   "peak_bid": t["runs"]["A"]["peak_bid"],
                   "peak_bid_at": hhmm(t["runs"]["A"]["peak_ts"]),
                   "pullback_why": t["pullback_why"],
                   "pullback_entry": t["pullback_entry"],
                   "pullback_pl_A": (round(t["pullback_run"]["pl"], 2)
                                     if t["pullback_run"] else "")}
            for code, _l, _t2, _a2, _f2 in VARIANTS:
                r = t["runs"][code]
                rec["%s_exit" % code] = r["exit"]
                rec["%s_pl" % code] = round(r["pl"], 2)
                rec["%s_why" % code] = r["why"]
                rec["%s_born_stop" % code] = r["born"]
                rec["%s_stop_moves" % code] = r["moves"]
                rec["%s_held_s" % code] = round(r["held_s"], 1)
            w.writerow(rec)
    os.replace(out_csv + ".tmp", out_csv)
    print(out_md)
    print(out_csv)
    return out_md, out_csv


NAMED = (
    ("QQQ260914C00708000", "Skyy's 0DTE that the caller rode to +423%"),
    ("MSFT260914C00505000", "the bot's fastest stop-out of the day"),
    ("QQQ260914C00713000", "0.24 -> 0.22 in seconds"),
    ("CRWD260918C00245000", "MuggZone's CRWD, trimmed five times by the caller"),
    ("QQQ260914P00705000", "Vero's QQQ 705P"),
    ("QQQ260914P00704000", "Demon's QQQ 704P"),
)


def _worst(trades):
    """The single row carrying the most dollars under A — the one a reader
    must know about before trusting the total."""
    if not trades:
        return "none"
    t = max(trades, key=lambda r: abs(r["runs"]["A"]["pl"]))
    return "%s %s, %+.0f" % (t["alert"]["day"][5:], t["alert"]["occ"],
                             t["runs"]["A"]["pl"])


def _why_excluded(contract, excluded):
    for a, why in excluded:
        if a["occ"] == contract:
            return why
    return "the alert is not in alert_meta/master_alerts for these days"


def _strike(a):
    k = a.get("strike")
    if k is None:
        return "?"
    return "%g" % k


def _md(text):
    return str(text or "?").replace("|", "\\|")


def _hold(seconds):
    seconds = int(seconds or 0)
    if seconds < 90:
        return "%ds" % seconds
    return "%dm %02ds" % (seconds // 60, seconds % 60)


if __name__ == "__main__":
    _trades, _excluded = build()
    write(_trades, _excluded)
