#!/usr/bin/env python3
"""
build_alerts.py — ONE central alert ledger: every alert the bot acted on,
and what happened to it.  →  master_alerts.csv

WHY (2026-09-09): "what alerts didn't trigger and why" lived in three places:
    telemetry.csv    every alert that went to the broker: posted/seen/sent/
                     filled stamps, slip, greeks — TAKEN side only
    trades.log       REFUSED / PULLBACK-skipped / SWING-OFF / … — the DECLINED
                     side, parsed by misses.py
    master_ledger.csv the fill it became, if it became one
Nothing joined them. This does.

ONE ROW PER ALERT.  outcome ∈
    filled          went to the broker and filled       (telemetry, filled_at set)
    sent-no-fill    went to the broker, never filled    (telemetry, filled_at empty)
    <miss reason>   declined before any order           (misses.py label, e.g.
                    "REFUSED", "PULLBACK never hit", "SWING-OFF", …)
ledger_key links a filled alert to its master_ledger.csv row (date|SYMBOL|fill).

Deterministic full rebuild, atomic swap. Read-only over every source.
Wired into bridge.py save_day() next to build_ledger (never raises).

RUN:   python3 build_alerts.py            (rebuild + summary)
       python3 build_alerts.py --quiet
"""
import csv
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
TELEMETRY = os.path.join(HERE, "telemetry.csv")
LEDGER = os.path.join(HERE, "master_ledger.csv")
OUT = os.path.join(HERE, "master_alerts.csv")
# Written live by alert_tape.py at the moment each alert is parsed — the only
# record that carries a room, a caller, the latency stamps and greeks for an
# alert that was REFUSED. trades.log (the source for 289 of 326 rows) carries
# none of those, which is why they were blank.
META = os.path.join(HERE, "alert_meta.csv")
KEEP_BAKS = 5

COLUMNS = [
    "date", "time", "room", "caller", "symbol", "side", "strike", "expiry", "dte",
    "their_price", "qty", "outcome", "reason", "detail",
    "our_fill", "slip_abs", "slip_pct",
    "posted_at", "seen_at", "sent_at", "filled_at",
    "read_ms", "decide_ms", "fill_ms", "total_ms",
    "bid", "ask", "spread_pct", "delta", "iv", "live", "coid",
    "ledger_key", "in_ledger", "source", "raw",
    # PROVENANCE (9/11). A row recovered out of trades.log has to stay
    # auditable or it is just another number: caller_strike is what the CALLER
    # posted when the NO-OTM rule moved us to a different one (17 alerts —
    # without this column the bot's decision reads as the caller's call);
    # tier/confidence say how the row was recovered and how much to trust it;
    # source_line is the log line itself, verbatim, so any row can be checked
    # against the log in one grep.
    "caller_strike", "caller_expiry", "our_limit", "tier", "confidence",
    "how_recovered", "source_line",
]


def _f(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _hms_from_epoch(v):
    e = _f(v)
    if e is None:
        return ""
    try:
        return datetime.fromtimestamp(e).strftime("%H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return ""


def _ledger_keys():
    keys = set()
    if not os.path.exists(LEDGER):
        return keys
    with open(LEDGER, encoding="utf-8", newline="") as fh:
        for c in csv.DictReader(fh):
            f = _f(c.get("fill"))
            if f is not None:
                keys.add("%s|%s|%.2f" % (c.get("date"), (c.get("symbol") or "").upper(), f))
    return keys


def _taken(ledger_keys):
    """telemetry.csv → one row per alert that reached the broker."""
    rows, seen, skipped = [], set(), 0
    if not os.path.exists(TELEMETRY):
        return rows
    with open(TELEMETRY, encoding="utf-8-sig", newline="", errors="replace") as fh:
        for c in csv.DictReader(fh):
            coid = (c.get("coid") or "").strip()
            # NO COID, NO ORDER, NO ALERT (9/11). A telemetry row earns its
            # place here by being an order the bridge actually sent for a room
            # call: the coid is the client order id it minted, and a real row
            # also carries the room, the posted_at stamp and the caller's
            # price. The fixture rows test_positions.py used to append to this
            # same file have none of them — no coid, no room, no latency — and
            # they collapsed into the "42 filled alerts" this file used to
            # show, every one of them filled in exactly 200 ms on a July 31
            # expiry in September. telemetry.py now writes the suite's rows to
            # telemetry-test.csv, and this is the belt to that braces: the
            # existing 3,896 fixture rows are still in telemetry.csv (deleting
            # a record is not a fix) and they stop here.
            if not coid:
                skipped += 1
                continue
            iso = c.get("iso") or ""
            date = iso[:10]
            if not date:
                e = _f(c.get("ts"))
                date = datetime.fromtimestamp(e).strftime("%Y-%m-%d") if e else ""
            key = coid or (date, c.get("symbol"), c.get("posted_at"))
            if key in seen:
                continue
            seen.add(key)
            filled = (c.get("filled_at") or "").strip()
            our_fill = _f(c.get("our_fill"))
            sym = (c.get("symbol") or "").upper()
            lk = "%s|%s|%.2f" % (date, sym, our_fill) if (our_fill is not None and filled) else ""
            rows.append({
                "date": date,
                "time": iso[11:19] if len(iso) >= 19 else _hms_from_epoch(c.get("ts")),
                "room": c.get("room") or "", "caller": c.get("trader") or "",
                "symbol": sym, "side": c.get("side") or "",
                "strike": c.get("strike") or "", "expiry": c.get("expiry") or "",
                "dte": c.get("dte") or "",
                "their_price": c.get("their_price") or "", "qty": c.get("qty") or "",
                "outcome": "filled" if filled else "sent-no-fill",
                "reason": "", "detail": "",
                "our_fill": our_fill if our_fill is not None else "",
                "slip_abs": c.get("slip_abs") or "", "slip_pct": c.get("slip_pct") or "",
                "posted_at": c.get("posted_at") or "", "seen_at": c.get("seen_at") or "",
                "sent_at": c.get("sent_at") or "", "filled_at": filled,
                "read_ms": c.get("read_ms") or "", "decide_ms": c.get("decide_ms") or "",
                "fill_ms": c.get("fill_ms") or "", "total_ms": c.get("total_ms") or "",
                "bid": c.get("bid") or "", "ask": c.get("ask") or "",
                "spread_pct": c.get("spread_pct") or "", "delta": c.get("delta") or "",
                "iv": c.get("iv") or "", "live": c.get("live") or "", "coid": coid,
                "ledger_key": lk, "in_ledger": bool(lk and lk in ledger_keys),
                "source": "telemetry", "raw": "",
                "caller_strike": "", "tier": "T-telemetry", "confidence": "high",
                "how_recovered": "telemetry.csv — the bot's own record of an "
                                 "order it sent", "source_line": "",
            })
    if skipped:
        sys.stderr.write("build_alerts: %d telemetry row(s) with no order id "
                         "skipped — test-harness output, not alerts\n" % skipped)
    return rows


def _declined():
    """misses.py → one row per distinct decline, with its reason."""
    try:
        from misses import collect_misses
    except ImportError:
        return []
    rows, dropped = [], 0
    for m in collect_misses(all_days=True):
        raw = m.get("raw") or ""
        if _noise_reason(raw):
            dropped += 1
            continue
        caller = ""
        cm = re.search(r"\(([^()]{1,40})'s call\)", raw)
        if cm:
            caller = cm.group(1)
        pm = re.search(r"@\s*\$?([\d.]+)", raw)
        cm2 = re.search(r"\b(\d+(?:\.\d+)?)([CP])\s+(\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{4}-\d{2}-\d{2}|\dDTE)", raw)
        rows.append({c: "" for c in COLUMNS} | {
            "date": m.get("date") or "", "time": m.get("time") or "",
            "caller": caller, "symbol": (m.get("symbol") or "").upper(),
            "side": ("CALLS" if cm2 and cm2.group(2) == "C" else "PUTS" if cm2 else ""),
            "strike": cm2.group(1) if cm2 else "",
            # through the SAME calendar the bridge uses, anchored to the day
            # the alert was posted — so "8/21" on an 8/17 row is 2026-08-21 and
            # every row in this file speaks one date format.
            "expiry": (_resolve_expiry(cm2.group(3), m.get("date"))
                       or cm2.group(3)) if cm2 else "",
            "their_price": pm.group(1) if pm else "",
            "outcome": m.get("reason") or "declined",
            "reason": m.get("reason") or "", "detail": m.get("detail") or "",
            "in_ledger": False, "source": "trades.log", "raw": raw[:300],
            "tier": "A", "confidence": "high",
            "how_recovered": "the REFUSED line in trades.log",
            "source_line": raw[:300],
        })
    if dropped:
        sys.stderr.write("build_alerts: %d log line(s) dropped as NOT alerts "
                         "(startup banner / PROP-NO / SWING-OFF / duplicate "
                         "guard)\n" % dropped)
    return rows


def _alert_meta():
    """alert_meta.csv -> {join key: fields}, for the DECLINED side.

    WHY (9/11): master_alerts had delta and iv on 0 of 326 rows, a room on
    156 and a caller on 89. 289 of those rows are refusals, and the only
    record of a refusal is a line of trades.log — which names the caller in
    prose and carries no room, no greeks, no bid/ask and no timing at all.
    So none of it was lost: it was never written down. alert_tape.py now
    writes one row per alert AS IT IS PARSED, before anything knows whether
    it will fill, and this joins that row back in.

    Two stages per contract: `alert` (what the call itself said, written
    instantly) and `quote` (the first REAL bid/ask the slow recorder got
    back, seconds later). The quote stage wins on prices and greeks; the
    alert stage wins on everything the call said. Only BLANK fields on the
    master row are ever filled — telemetry stays the authority wherever it
    has an answer.
    """
    if not os.path.exists(META):
        return {}, {}
    exact, loose = {}, {}
    try:
        with open(META, encoding="utf-8-sig", newline="", errors="replace") as fh:
            for m in csv.DictReader(fh):
                date = (m.get("date") or "").strip()
                sym = (m.get("symbol") or "").strip().upper()
                if not date or not sym:
                    continue
                k = (date, sym, _strike_key(m.get("strike")),
                     (m.get("side") or "")[:1].upper())
                for store, key in ((exact, k), (loose, (date, sym))):
                    cur = store.setdefault(key, {})
                    quote = (m.get("stage") == "quote")
                    for col in ("room", "caller", "their_price", "alert_at",
                                "seen_at", "bid", "ask", "delta", "iv"):
                        v = (m.get(col) or "").strip()
                        if not v:
                            continue
                        # a real quote overrides a cached one; the call's own
                        # words are never overwritten by a later sweep
                        if col not in cur or (quote and col in
                                              ("bid", "ask", "delta", "iv")):
                            cur[col] = v
    except OSError:
        return {}, {}
    return exact, loose


def _blank(v):
    """Is this cell empty? Type-safe on purpose: rows read back from the CSV
    hold strings, but a row built this run can hold a real int or float from
    telemetry, and `(r.get(c) or "").strip()` throws on those."""
    return v is None or (isinstance(v, str) and not v.strip()) or v == ""


def _strike_key(v):
    try:
        return "%.4f" % float(v)
    except (TypeError, ValueError):
        return ""


def _apply_meta(rows):
    """Fill BLANK columns on each alert row from alert_meta.csv. Returns the
    number of rows that gained something."""
    exact, loose = _alert_meta()
    if not exact and not loose:
        return 0
    touched = 0
    for r in rows:
        date = (r.get("date") or "").strip()
        sym = (r.get("symbol") or "").strip().upper()
        if not date or not sym:
            continue
        m = exact.get((date, sym, _strike_key(r.get("strike")),
                       (r.get("side") or "")[:1].upper())) \
            or loose.get((date, sym))
        if not m:
            continue
        got = False
        for col in ("room", "caller", "their_price", "bid", "ask",
                    "delta", "iv"):
            if _blank(r.get(col)) and m.get(col):
                r[col] = m[col]
                got = True
        if _blank(r.get("posted_at")) and m.get("alert_at"):
            r["posted_at"] = m["alert_at"]
            got = True
        if _blank(r.get("seen_at")) and m.get("seen_at"):
            r["seen_at"] = m["seen_at"]
            got = True
        # read_ms is alert->seen: the only leg of the latency chain a
        # REFUSED alert has, because it was never sent and never filled.
        if _blank(r.get("read_ms")):
            a, b = _f(m.get("alert_at")), _f(m.get("seen_at"))
            if a and b and b >= a:
                r["read_ms"] = int(round((b - a) * 1000))
                got = True
        if _blank(r.get("spread_pct")):
            bid, ask = _f(r.get("bid")), _f(r.get("ask"))
            if bid and ask and (bid + ask) > 0:
                r["spread_pct"] = round((ask - bid) / ((ask + bid) / 2.0) * 100.0, 2)
                got = True
        touched += 1 if got else 0
    return touched


def _room_index():
    """(date, SYMBOL) -> room, and caller -> room, both read from the LEDGER.

    9/10: master_alerts had a room on 18 of 323 rows. Every row sourced from
    trades.log had none at all, because the log line the miss-parser reads
    ("REFUSED OPEN NFLX (EvaPanda Alerts's call) ...") names the CALLER and
    never the room. The ledger DOES carry the room — 26 of 26 rows on a
    normal day — so the room is not lost, just never joined. This joins it.
    Falls back to a caller->room map for rows whose symbol/date miss, and
    refuses to guess when one caller has posted in more than one room.
    """
    import collections
    by_key = {}
    by_caller = collections.defaultdict(collections.Counter)
    try:
        import ledger as _lg
        for day, rs in _lg.by_day().items():
            for r in rs:
                room = (r.get("room") or "").strip()
                if not room or room == "?":
                    continue
                sym = (r.get("symbol") or "").upper()
                if sym:
                    by_key.setdefault((day, sym), room)
                who = (r.get("who") or "").strip().lower()
                if who and who not in ("?", "gian"):
                    by_caller[who][room] += 1
    except Exception:                                       # noqa: BLE001
        return {}, {}
    # only trust a caller->room mapping that is UNAMBIGUOUS
    solo = {c: v.most_common(1)[0][0] for c, v in by_caller.items() if len(v) == 1}
    return by_key, solo


def _labels():
    """channel id -> human label, straight out of extension/rooms.txt.

    9/10: rooms were landing in master_alerts as raw ids
    ("1334236429655740457", "911389167169191946") because the bridge's
    hand-typed ROOM_LABELS map never had them. rooms.txt is THE list and
    already carries every label, so read it instead of maintaining a second
    copy — the same mistake rooms.txt's own header warns about."""
    out = {}
    try:
        p = os.path.join(HERE, "extension", "rooms.txt")
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                t = line.strip()
                if not t or t.startswith("#"):
                    continue
                parts = t.split("|")
                if len(parts) >= 3 and parts[0] and parts[2]:
                    out[parts[0].strip()] = parts[2].strip()
    except OSError:
        pass
    return out


# ---------------------------------------------------------------------------
# TRADES.LOG, THE PART NOBODY WAS READING (9/11)
#
# master_alerts was built from two sources: telemetry.csv (the TAKEN side) and
# misses.py (the REFUSED side). Between them they saw 331 lines of trades.log.
# The log carries three richer records that never reached this file at all:
#
#   ORDER IN   184 lines. The bot's OWN resolved contract, with a real ISO
#              date and the price it actually bid:
#                 "ORDER IN BUY 5 SPY 600C 2026-08-06 @ 175.91"
#              Not one of them was in master_alerts.csv.
#   AI READ    2,222 lines, 636 of them carrying a reading. These are the
#              ORIGINATING alerts, in the caller's own words AND translated:
#                 "AI READ 'BTO $AAPL 312.5c 08/19 @0.74' -> BTO AAPL $312.5C 08/19 @ 0.74"
#   PULLBACK   152 arm lines. An armed round-number hunt names the symbol and
#              the DIRECTION but not the contract; the contract is on the line
#              that triggered it, seconds earlier. Linking the two is what
#              gives a "never touched — skipped" row a strike and an expiry.
#
# THE LINK RULE, AND WHY IT IS NARROW. An arm is matched to the most recent
# contract event that is (a) the same symbol, (b) within LINK_WINDOW_S, and
# (c) THE SAME DIRECTION. Direction agreement is not a tiebreak, it is a
# requirement: a PUT alert sitting next to a CALL arm is a different trade, and
# matching them writes a contract nobody called onto a row that then gets
# analysed as if a caller had posted it. Five such pairs exist in this log; all
# five are refused here.
# ---------------------------------------------------------------------------
LOGFILE = os.path.join(HERE, "trades.log")
# The round-number hunt's own window is 10 minutes, so that is how far back an
# arm may reach for the call that triggered it. MEASURED on this log: at 600 s
# the same-direction rule and a direction-blind rule link exactly the same 116
# arms — no conflict exists that close in. Widen it and the guard starts
# earning its keep: at 30 minutes a direction-blind match makes FIVE links a
# same-direction match refuses, and every one of those five would have written
# a CALL contract onto a PUT alert. That is why the rule is mandatory and not
# a tiebreak.
LINK_WINDOW_S = 600
SAME_ALERT_S = 120           # NO-OTM is printed at order time, beside its alert

RE_ORDER_IN = re.compile(
    r"^ORDER IN\s+(BUY|SELL)\s+(\d+)\s+([A-Z][A-Z.]{0,5})\s+([\d.]+)([CP])\s+"
    r"(\d{4}-\d{2}-\d{2})\s+@\s+([\d.]+)")
RE_AI_READ = re.compile(r"^AI READ\s+'(.*)'\s+->\s+(.+)$")
RE_AI_CANON = re.compile(
    r"^(?:BTO|adding)\s+([A-Z][A-Z.]{0,5})\s+\$([\d.]+)([CP])"
    r"(?:\s+(?!@)(.+?))?(?:\s+@\s+([\d.]+))?$")
RE_PB_ARM = re.compile(
    r"^PULLBACK\s+([A-Z][A-Z.]{0,5})\s+(CALL|PUT):\s+stock at\s+([\d.]+),"
    r"\s+waiting for a\s+(?:dip|bounce)\s+to\s+\$([\d.]+)")
RE_PB_SKIP = re.compile(r"^PULLBACK\s+([A-Z][A-Z.]{0,5}):\s+never touched\s+\$([\d.]+)")
RE_PB_HIT = re.compile(r"^PULLBACK\s+([A-Z][A-Z.]{0,5}):\s+touched\s+\$([\d.]+)")
RE_REFUSED = re.compile(
    r"^REFUSED\s+(?:OPEN|ADD)\s+([A-Z][A-Z.]{0,5})\s+\(([^()]{1,40})'s call\)\s+"
    r"([\d.]+)([CP])\s+(\S+)")
# "WORKING  AMZN — Bullwinkle's call, bid is in at 0.69 ..." — the line the
# bridge prints right after ORDER IN. It is the ONLY place the caller's name
# appears for an order the bot sent; ORDER IN and AI READ both name the
# contract and nobody. build_ledger.load_fill_callers() reads it the same way
# for the ledger's fills, and that is what attributed all 41 rows that used to
# sit at room "?" with no name.
RE_WORKING = re.compile(r"^WORKING\s+([A-Z][A-Z.]{0,5})\s+—\s+([^,]{1,40}?)'s call")
RE_NO_OTM = re.compile(
    r"^NO-OTM\s+([A-Z][A-Z.]{0,5}):\s+their\s+([\d.]+)([CP])\s+was\s+\w+"
    r".*?->\s+nearest qualifying\s+([\d.]+)([CP])")


def _ticker(sym):
    """The ticker the ROOM called, out of what the log wrote down. One reader
    (symbols.resolve) for both the miss parser and this one, so the alert
    record can never carry MXLU while trades.log carries XLU."""
    s = str(sym or "").strip().upper()
    try:
        import symbols as _symbols
        return _symbols.resolve(s) or s
    except ImportError:
        return s


def _miss_label(msg):
    """The reason bucket misses.py would give this line — ONE vocabulary for
    both readers, so "BUYING POWER too small" never also exists as "refused"."""
    try:
        from misses import CATS
    except ImportError:
        return "REFUSED"
    for label, pat in CATS:
        if pat.search(msg):
            return label
    return "REFUSED"


def _ts(line_ts):
    """'2026-08-06T09:31:02-04:00' -> epoch seconds, or None."""
    try:
        return datetime.fromisoformat(line_ts).timestamp()
    except ValueError:
        return None


def _resolve_expiry(raw, on_date):
    """The caller's date, in the caller's words, turned into YYYY-MM-DD — using
    THE SAME calendar the bridge uses (webull_options.expiry_to_date), anchored
    to the day the alert was posted so "8/21" read on 8/17 is 2026-08-21 and not
    next year's. Returns "" when it genuinely cannot be resolved ("next week",
    "swing") rather than guessing: a guessed expiry is a contract nobody named.
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    try:
        from webull_options import expiry_to_date
        import datetime as _d
        anchor = _d.date.fromisoformat(on_date) if on_date else None
        return expiry_to_date(raw, today=anchor)
    except Exception:                                       # noqa: BLE001
        return ""


def _log_events():
    """One pass over trades.log -> the contract events above, in order.

    Each event: ts, date, time, symbol, side (CALLS/PUTS), strike, expiry_raw,
    expiry, their_price, qty, caller, outcome, tier, confidence, how, raw.
    """
    events, arms, no_otm = [], [], []
    if not os.path.exists(LOGFILE):
        return events
    with open(LOGFILE, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            stamp, msg = parts
            date, hhmm = stamp[:10], stamp[11:16]
            ts = _ts(stamp)
            if ts is None:
                continue
            base = {"ts": ts, "date": date, "time": hhmm, "raw": msg[:300],
                    "caller": "", "qty": "", "their_price": "", "our_limit": ""}

            m = RE_ORDER_IN.match(msg)
            if m and m.group(1) == "BUY":
                events.append(dict(base, symbol=_ticker(m.group(3)),
                                   side="CALLS" if m.group(5) == "C" else "PUTS",
                                   strike=m.group(4), expiry_raw=m.group(6),
                                   expiry=m.group(6), qty=m.group(2),
                                   our_limit=m.group(7),
                                   outcome="order-sent", tier="E-order",
                                   confidence="high",
                                   how="the bot's own ORDER IN line — "
                                       "resolved contract, real date"))
                continue

            m = RE_AI_READ.match(msg)
            if m:
                c = RE_AI_CANON.match(m.group(2).strip())
                if not c:
                    continue
                exp_raw = (c.group(4) or "").strip()
                exp = _resolve_expiry(exp_raw, date)
                events.append(dict(base, symbol=_ticker(c.group(1)),
                                   side="CALLS" if c.group(3) == "C" else "PUTS",
                                   strike=c.group(2), expiry_raw=exp_raw,
                                   expiry=exp, their_price=c.group(5) or "",
                                   outcome="alert read",
                                   tier="F-airead",
                                   confidence="high" if exp else "medium",
                                   how="AI READ of the room's own words"
                                       + ("" if exp else
                                          " — expiry not resolvable from the text")))
                continue

            m = RE_REFUSED.match(msg)
            if m:
                exp_raw = m.group(5)
                events.append(dict(base, symbol=_ticker(m.group(1)),
                                   side="CALLS" if m.group(4) == "C" else "PUTS",
                                   strike=m.group(3), expiry_raw=exp_raw,
                                   expiry=_resolve_expiry(exp_raw, date),
                                   caller=m.group(2), outcome=_miss_label(msg),
                                   tier="A", confidence="high",
                                   how="the REFUSED line's own contract"))
                continue

            m = RE_PB_ARM.match(msg)
            if m:
                arms.append({"ts": ts, "date": date, "time": hhmm,
                             "symbol": _ticker(m.group(1)),
                             "side": "CALLS" if m.group(2) == "CALL" else "PUTS",
                             "level": m.group(4), "raw": msg[:300],
                             "outcome": "PULLBACK armed (no resolution in the log)"})
                continue

            m = RE_PB_SKIP.match(msg) or RE_PB_HIT.match(msg)
            if m:
                hit = bool(RE_PB_HIT.match(msg))
                for a in reversed(arms):
                    if (a["symbol"] == m.group(1).upper()
                            and a["level"] == m.group(2)
                            and 0 <= ts - a["ts"] <= 3600
                            and a["outcome"].startswith("PULLBACK armed")):
                        a["outcome"] = ("PULLBACK touched" if hit
                                        else "PULLBACK never hit")
                        break
                continue

            m = RE_WORKING.match(msg)
            if m:
                sym, who = m.group(1).upper(), m.group(2).strip()
                for ev in reversed(events):
                    if ev["ts"] < ts - 120:
                        break
                    if ev["symbol"] == sym and not ev.get("caller"):
                        ev["caller"] = who
                continue

            m = RE_NO_OTM.match(msg)
            if m:
                no_otm.append({"ts": ts, "symbol": m.group(1).upper(),
                               "caller_strike": m.group(2),
                               "side": "CALLS" if m.group(3) == "C" else "PUTS",
                               "bot_strike": m.group(4)})

    # ---- the arms, linked to the contract that triggered them --------------
    linked = 0
    for a in arms:
        best = None
        for e in events:
            if e["ts"] > a["ts"] or a["ts"] - e["ts"] > LINK_WINDOW_S:
                continue
            if e["symbol"] != a["symbol"]:
                continue
            # MANDATORY. Not a preference — a PUT alert beside a CALL arm is a
            # different trade and linking them corrupts the row.
            if e["side"] != a["side"]:
                continue
            if best is None or e["ts"] > best["ts"]:
                best = e
        if best is None:
            continue
        linked += 1
        events.append({"ts": a["ts"], "date": a["date"], "time": a["time"],
                       "symbol": a["symbol"], "side": a["side"],
                       "strike": best["strike"], "expiry_raw": best["expiry_raw"],
                       "expiry": best["expiry"], "their_price": best["their_price"],
                       "our_limit": best.get("our_limit", ""),
                       "qty": best["qty"], "caller": best["caller"],
                       "outcome": a["outcome"],
                       "tier": "C-linked(%s)" % best["tier"],
                       "confidence": "medium",
                       "how": "pullback arm linked to the %s line %d s earlier, "
                              "same symbol AND same direction"
                              % (best["tier"], int(a["ts"] - best["ts"])),
                       "raw": a["raw"]})
    if arms and linked < len(arms):
        sys.stderr.write("build_alerts: %d of %d pullback arms had no same-"
                         "direction contract within %ds and were left unlinked\n"
                         % (len(arms) - linked, len(arms), LINK_WINDOW_S))

    # ---- the bot's own strike substitution, kept SEPARATE from the caller's -
    # 17 alerts in this log were entered on a strike the caller did not post,
    # because the NO-OTM rule moved it. Writing the bot's strike into the
    # caller's column blames him for our decision, so both are carried.
    for e in events:
        e.setdefault("caller_strike", "")
        for n in no_otm:
            if (n["symbol"] == e["symbol"] and n["side"] == e["side"]
                    and abs(n["ts"] - e["ts"]) <= SAME_ALERT_S):
                if _f(e.get("strike")) == _f(n["bot_strike"]):
                    e["caller_strike"] = n["caller_strike"]
                elif _f(e.get("strike")) == _f(n["caller_strike"]):
                    e["caller_strike"] = n["caller_strike"]
                    e["strike"] = n["bot_strike"]
                break

    events.sort(key=lambda e: e["ts"])
    return events


# ---------------------------------------------------------------------------
# WHAT IS NOT AN ALERT (9/11)
#
# 60 of the 331 rows in master_alerts.csv were never alerts. They reached the
# file because misses.py matches on words, and these lines contain the words:
#   30  the startup banner ("test account: unlimited. Nothing is REFUSED for
#       money...") — a status line printed at boot, matched on "refused"
#   15  "PROP-NO Topstep: ..." — prop-firm and ProjectX account status
#    5  "PULLBACK refused  already waiting on a SPY pullback" — the duplicate
#       guard. The alert it refers to is already a row of its own; counting the
#       guard too counts one call twice.
#   10  "SWING-OFF ... swing trades are PAUSED" — the swing switch
# They inflated the count to 331 when the real number was 271, and every rate
# computed off the file (fill rate, refusal rate, per-room counts) was wrong by
# that much. Dropped at the door so a rebuild can never re-ingest them.
# ---------------------------------------------------------------------------
NOISE = (
    ("startup banner, not an alert",
     re.compile(r"^test account:|^live account:.*most cash that was ever tied up", re.I)),
    ("prop-firm / ProjectX account status, not an option alert",
     re.compile(r"^PROP-NO\b")),
    ("duplicate guard — the alert it refers to is its own row",
     re.compile(r"^PULLBACK refused\s+already waiting on", re.I)),
    ("the swing switch, not an alert",
     re.compile(r"^SWING-OFF\b")),
)


def _noise_reason(raw):
    for why, pat in NOISE:
        if pat.search((raw or "").strip()):
            return why
    return None


def _akey(r):
    """The identity of ONE alert: day + contract. Strike is rounded so 482.50
    and 482.5 are the same trade."""
    return ((r.get("date") or ""), (r.get("symbol") or "").upper(),
            _strike_key(r.get("strike")), (r.get("side") or "")[:1].upper())


def _apply_log(rows):
    """Fold the trades.log events into the alert rows: enrich the ones that
    exist, add the ones that do not. Returns (enriched, added)."""
    events = _log_events()
    if not events:
        return 0, 0
    by_key = {}
    for i, r in enumerate(rows):
        by_key.setdefault(_akey(r), []).append(i)

    enriched, added, new_rows = 0, 0, []
    minted = {}
    for e in events:
        k = ((e["date"], e["symbol"], _strike_key(e.get("strike")),
              (e.get("side") or "")[:1].upper()))
        if k in minted:
            # already recovered this contract on this day from an earlier log
            # line — one alert, one row. Keep the richest outcome.
            _keep_richer(minted[k], e)
            continue
        hit = by_key.get(k)
        if not hit:
            # A row that knows the symbol but never got a contract — the
            # PULLBACK and BUYING-POWER refusals are exactly this shape. Same
            # day, same symbol, no strike of its own, close in time.
            for i, r in enumerate(rows):
                if (r.get("date") == e["date"]
                        and (r.get("symbol") or "").upper() == e["symbol"]
                        and _blank(r.get("strike"))
                        and abs(_minutes(r.get("time")) - _minutes(e["time"])) <= 15):
                    # SAME RULE AS THE ARM LINK: if the row already knows which
                    # way the call went, the log line has to agree. A PUT
                    # refusal enriched with the CALL contract from the same
                    # symbol a minute away is a fabricated trade, and it reads
                    # exactly like a real one afterwards.
                    rs = (r.get("side") or "")[:1].upper()
                    if rs and rs != e["side"][:1]:
                        continue
                    hit = [i]
                    break
        if hit:
            r = rows[hit[0]]
            got = False
            if e["tier"] == "E-order":
                _take_expiry(r, e)
            for col, val in (("side", e.get("side")), ("strike", e.get("strike")),
                             ("expiry", e.get("expiry")),
                             ("their_price", e.get("their_price")),
                             ("our_limit", e.get("our_limit")),
                             ("qty", e.get("qty")), ("caller", e.get("caller"))):
                if val and _blank(r.get(col)):
                    r[col] = val
                    got = True
            if _blank(r.get("caller_strike")) and e.get("caller_strike"):
                r["caller_strike"] = e["caller_strike"]
                got = True
            if _blank(r.get("tier")):
                r["tier"] = e["tier"]
                r["confidence"] = e["confidence"]
                r["how_recovered"] = e["how"]
                r["source_line"] = e["raw"]
                got = True
            enriched += 1 if got else 0
            continue
        # genuinely new: an alert no other source ever wrote down
        if e["confidence"] == "low":
            continue                    # LOW never enters the main file
        new_rows.append({c: "" for c in COLUMNS} | {
            "date": e["date"], "time": e["time"], "caller": e.get("caller") or "",
            "symbol": e["symbol"], "side": e.get("side") or "",
            "strike": e.get("strike") or "", "expiry": e.get("expiry") or "",
            "caller_strike": e.get("caller_strike") or "", "caller_expiry": "",
            "their_price": e.get("their_price") or "",
            "our_limit": e.get("our_limit") or "", "qty": e.get("qty") or "",
            "outcome": e["outcome"], "reason": e["outcome"], "detail": "",
            "in_ledger": False, "source": "trades.log:" + e["tier"],
            "tier": e["tier"], "confidence": e["confidence"],
            "how_recovered": e["how"], "source_line": e["raw"],
            "raw": e["raw"],
        })
        minted[k] = new_rows[-1]
        added += 1
    rows.extend(new_rows)
    return enriched, added


# Which of two log records of the SAME contract on the SAME day is the one to
# keep? The one furthest down the pipeline: an ORDER IN says more than the AI
# READ that produced it, and a resolved pullback says more than an armed one.
_OUTCOME_RANK = {"alert read": 0, "PULLBACK armed (no resolution in the log)": 1,
                 "PULLBACK never hit": 2, "PULLBACK touched": 4, "order-sent": 5}


def _take_expiry(row, e):
    """The bot's own ORDER IN date wins the `expiry` column, and whatever the
    row held before it moves to `caller_expiry` — the same separation the
    strike columns keep, and for the same reason (9/11).

    It is not hypothetical: "MRNA | $110 P 5.60 AUG 28" was ordered as
    MRNA 110P 2026-08-21, and "SPCX 155 C AUG 21" as SPCX 155C 2026-08-14. The
    row used to show the CALLER'S date beside the ORDER IN line that bought a
    different one, which reads as if he called the contract we bought. He did
    not — that was the expiry parser refusing "AUG 21" and the bridge filling
    in this Friday, which is the bug fixed in webull_options today. Both dates
    stay on the row so the gap is visible instead of absorbed."""
    new = e.get("expiry")
    if not new:
        return
    old = (row.get("expiry") or "").strip()
    if not old:
        row["expiry"] = new
        return
    # Compare DATES, not spellings. "9/11", "0DTE" and "2026-09-11" can all be
    # the same Friday; only a genuinely different contract belongs in
    # caller_expiry, or the column fills up with 11 rows that agree.
    if (_resolve_expiry(old, row.get("date")) or old) == new:
        row["expiry"] = new
        return
    if _blank(row.get("caller_expiry")):
        row["caller_expiry"] = old
    row["expiry"] = new
    row["source_line"] = e["raw"]


def _keep_richer(row, e):
    """Fold a later log record of the same alert into the row already made for
    it: fill its blanks, and take the outcome only when it is further along."""
    if e["tier"] == "E-order":
        _take_expiry(row, e)
    for col, val in (("side", e.get("side")), ("expiry", e.get("expiry")),
                     ("their_price", e.get("their_price")),
                     ("our_limit", e.get("our_limit")),
                     ("qty", e.get("qty")), ("caller", e.get("caller")),
                     ("caller_strike", e.get("caller_strike"))):
        if val and _blank(row.get(col)):
            row[col] = val
    if _OUTCOME_RANK.get(e["outcome"], -1) > _OUTCOME_RANK.get(row.get("outcome"), -1):
        row["outcome"] = e["outcome"]
        row["reason"] = e["outcome"]
        row["tier"] = e["tier"]
        row["how_recovered"] = e["how"]
        row["source_line"] = e["raw"]
        if e["confidence"] == "high":
            row["confidence"] = "high"


def _minutes(hhmm):
    try:
        h, m = str(hhmm or "")[:5].split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return -10 ** 6


def build():
    lk = _ledger_keys()
    rows = _taken(lk) + _declined()
    # ORDER MATTERS, AND IT WAS WRONG (9/11). What was written down LIVE goes
    # first, what has to be INFERRED goes last, so an inference never lands on
    # a row that had a real answer coming:
    #   1. alert_meta.csv — the alert tape, written as each call was parsed
    #   2. trades.log     — the bot's own ORDER IN / AI READ / REFUSED records
    #   3. the ledger     — the room a fill ended up under, inferred by
    #                       date+symbol, and only then by caller
    # The ledger backfill used to run FIRST, which meant the 258 alerts step 2
    # recovers were added after it had already finished and none of them ever
    # got a room. Same guesses, run in the right order.
    _m = _apply_meta(rows)
    if _m:
        sys.stderr.write("build_alerts: alert_meta filled %d row(s)\n" % _m)
    _e, _a = _apply_log(rows)
    if _e or _a:
        sys.stderr.write("build_alerts: trades.log enriched %d row(s), "
                         "added %d alert(s)\n" % (_e, _a))
    by_key, by_caller = _room_index()
    filled = 0
    for r in rows:
        if (r.get("room") or "").strip():
            continue
        room = by_key.get((r.get("date"), (r.get("symbol") or "").upper()))
        if not room:
            room = by_caller.get((r.get("caller") or "").strip().lower())
        if room:
            r["room"] = room
            filled += 1
    lab = _labels()
    named = 0
    for r in rows:
        rm = (r.get("room") or "").strip()
        if rm and rm in lab and lab[rm] != rm:
            r["room"] = lab[rm]
            named += 1
    if named:
        sys.stderr.write("build_alerts: %d raw channel id(s) resolved to labels\n" % named)
    if filled:
        sys.stderr.write("build_alerts: room backfilled on %d row(s)\n" % filled)
    rows.sort(key=lambda r: (r["date"], r["time"] or "99:99:99", r["symbol"]))
    return rows


def _rotate_bak():
    """Dated copy into backups/ (last KEEP_BAKS kept) — same rule as
    build_ledger, so the folder root never fills with .bak files."""
    import build_ledger
    build_ledger._rotate_bak(OUT)


def write(rows, bak=True):
    if bak:
        _rotate_bak()
    tmp = OUT + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    os.replace(tmp, OUT)


def refresh():
    """One-call rebuild for the bridge's save_day(). Never raises."""
    try:
        write(build(), bak=False)
    except Exception:                                   # noqa: BLE001
        pass


def summary(rows):
    from collections import Counter
    print(f"master_alerts.csv  →  {len(rows)} alerts")
    oc = Counter(r["outcome"] for r in rows)
    for k, n in oc.most_common():
        print(f"  {n:>5}  {k}")
    filled = [r for r in rows if r["outcome"] == "filled"]
    linked = sum(1 for r in filled if r["in_ledger"])
    print(f"  filled alerts linked to a ledger row: {linked}/{len(filled)}")
    conf = Counter((r.get("confidence") or "-") for r in rows)
    print("  confidence: " + ", ".join("%s %d" % (k, n) for k, n in conf.most_common()))
    full = sum(1 for r in rows if r.get("symbol") and r.get("strike")
               and r.get("side") and r.get("expiry"))
    print(f"  rows carrying a whole contract: {full}/{len(rows)}")
    moved = sum(1 for r in rows if r.get("caller_strike"))
    if moved:
        print(f"  strike moved by the NO-OTM rule (caller's kept separately): {moved}")
    exp = sum(1 for r in rows if r.get("caller_expiry"))
    if exp:
        print(f"  bought a DIFFERENT expiry than the call named: {exp}")


if __name__ == "__main__":
    rows = build()
    write(rows)
    if "--quiet" not in sys.argv:
        summary(rows)
