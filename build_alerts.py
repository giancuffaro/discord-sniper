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


def build():
    lk = _ledger_keys()
    rows = _taken(lk) + _declined()
    rows.sort(key=lambda r: (r["date"], r["time"] or "99:99:99", r["symbol"]))
    return rows


def _rotate_bak():
    if os.path.exists(OUT):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(OUT, f"{OUT}.bak-{stamp}")
    for old in sorted(glob.glob(f"{OUT}.bak-*"))[:-KEEP_BAKS]:
        try:
            os.remove(old)
        except OSError:
            pass


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
