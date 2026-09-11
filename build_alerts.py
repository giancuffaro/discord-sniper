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
import glob
import os
import shutil
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
    rows, seen = [], set()
    if not os.path.exists(TELEMETRY):
        return rows
    with open(TELEMETRY, encoding="utf-8-sig", newline="", errors="replace") as fh:
        for c in csv.DictReader(fh):
            coid = (c.get("coid") or "").strip()
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
            })
    return rows


def _declined():
    """misses.py → one row per distinct decline, with its reason."""
    try:
        from misses import collect_misses
    except ImportError:
        return []
    rows = []
    for m in collect_misses(all_days=True):
        raw = m.get("raw") or ""
        caller = ""
        import re
        cm = re.search(r"\(([^()]{1,40})'s call\)", raw)
        if cm:
            caller = cm.group(1)
        pm = re.search(r"@\s*\$?([\d.]+)", raw)
        cm2 = re.search(r"\b(\d+(?:\.\d+)?)([CP])\s+(\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{4}-\d{2}-\d{2}|\dDTE)", raw)
        rows.append({c: "" for c in COLUMNS} | {
            "date": m.get("date") or "", "time": m.get("time") or "",
            "caller": caller, "symbol": (m.get("symbol") or "").upper(),
            "side": ("CALLS" if cm2 and cm2.group(2) == "C" else "PUTS" if cm2 else ""),
            "strike": cm2.group(1) if cm2 else "", "expiry": cm2.group(3) if cm2 else "",
            "their_price": pm.group(1) if pm else "",
            "outcome": m.get("reason") or "declined",
            "reason": m.get("reason") or "", "detail": m.get("detail") or "",
            "in_ledger": False, "source": "trades.log", "raw": raw[:300],
        })
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
            if not (r.get(col) or "").strip() and m.get(col):
                r[col] = m[col]
                got = True
        if not (r.get("posted_at") or "").strip() and m.get("alert_at"):
            r["posted_at"] = m["alert_at"]
            got = True
        if not (r.get("seen_at") or "").strip() and m.get("seen_at"):
            r["seen_at"] = m["seen_at"]
            got = True
        # read_ms is alert->seen: the only leg of the latency chain a
        # REFUSED alert has, because it was never sent and never filled.
        if not (r.get("read_ms") or "").strip():
            a, b = _f(m.get("alert_at")), _f(m.get("seen_at"))
            if a and b and b >= a:
                r["read_ms"] = int(round((b - a) * 1000))
                got = True
        if not (r.get("spread_pct") or "").strip():
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


def build():
    lk = _ledger_keys()
    rows = _taken(lk) + _declined()
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
    # Live alert metadata FIRST, so the ledger/caller backfills below only
    # have to guess at what was genuinely never recorded.
    _m = _apply_meta(rows)
    if _m:
        sys.stderr.write("build_alerts: alert_meta filled %d row(s)\n" % _m)
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


if __name__ == "__main__":
    rows = build()
    write(rows)
    if "--quiet" not in sys.argv:
        summary(rows)
