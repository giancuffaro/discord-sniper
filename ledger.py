#!/usr/bin/env python3
"""
ledger.py — THE one way to read fills. Every analysis script imports this.

RULE (2026-09-09): master_ledger.csv is the fill truth. Nothing reads
days/*.json "table" or journal.csv for analysis anymore — those truncate
(table dropped 6 of 12 fills on 9/8) and journal.csv inherits it.

Rows come back keyed EXACTLY like the day-JSON table rows (who, room, avg,
exits, opened as epoch, live as bool …) so existing loops are a drop-in:

    from ledger import rows
    for date, r in rows(real_only=True):
        ...r["symbol"], r["who"], r["room"], r["pl"], r["exits"]...

Self-healing: if master_ledger.csv is missing it rebuilds it first.
Read-only over the ledger. Never touches the trading path.
"""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "master_ledger.csv")

REAL_STATES = ("filled", "closed", "stopped")
NOFILL_STATES = ("nofill", "failed")

_FLOAT = ("opened_ts", "closed_ts", "t", "strike", "qty", "avg_in", "fill",
          "exit_avg", "pl", "pl_pct", "max_runup_pct", "max_drawdown_pct",
          "hi_pct", "lo_pct", "their_avg", "their_stop", "their_target",
          "their_units", "stop_at_exit", "dte", "direction", "store_pl")
_JSON = ("entries", "exits", "greeks_in", "greeks_out")
_BOOL = ("all_out", "manual", "swing", "broker_confirmed", "export_confirmed",
         "in_table", "in_wallet", "derived")


def _f(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _b(v):
    return str(v).strip().lower() == "true"


def _j(v):
    if not v:
        return []
    try:
        return json.loads(v)
    except ValueError:
        return []


def _ensure():
    if not os.path.exists(LEDGER):
        try:
            import build_ledger
            build_ledger.refresh()
        except Exception:                               # noqa: BLE001
            pass


def _to_row(c):
    """CSV record -> day-JSON-shaped dict."""
    r = {}
    for k in _FLOAT:
        r[k] = _f(c.get(k))
    for k in _JSON:
        r[k] = _j(c.get(k))
    for k in _BOOL:
        r[k] = _b(c.get(k))
    # names the old table rows used
    r["date"] = c.get("date") or ""
    r["who"] = c.get("caller") or ""
    r["room"] = c.get("room") or "?"
    r["key"] = c.get("key") or ""
    r["symbol"] = c.get("symbol") or ""
    r["side"] = c.get("side") or ""
    r["expiry"] = c.get("expiry") or ""
    r["occ"] = c.get("occ") or ""
    r["kind"] = c.get("kind") or ""
    r["state"] = c.get("state") or ""
    r["exit_by"] = c.get("exit_by") or ""
    r["source"] = c.get("source") or ""
    r["raw"] = c.get("raw") or ""
    r["why"] = c.get("why") or ""
    r["day_file"] = c.get("day_file") or ""
    r["account"] = c.get("account") or ""
    r["live"] = r["account"] == "live"
    r["opened_from"] = c.get("opened_from") or ""
    r["exit_from"] = c.get("exit_from") or ""
    r["avg"] = r["avg_in"]
    # epoch, like the table rows. build_ledger already filled opened_ts from
    # the broker's FILLED stamp when the store lacked it — never from wallet
    # "t", which is the EXIT event. So no fallback here: None means unknown.
    r["opened"] = r["opened_ts"]
    r["closed"] = r["closed_ts"]
    r["opened_hms"] = c.get("opened") or ""
    r["closed_hms"] = c.get("closed") or ""
    if r["qty"] is not None and float(r["qty"]).is_integer():
        r["qty"] = int(r["qty"])
    if r["strike"] is not None and float(r["strike"]).is_integer():
        r["strike"] = int(r["strike"])       # "315C", not "315.0C"
    if r["direction"] is not None:
        r["direction"] = int(r["direction"])
    return r


def rows(real_only=False, nofill_only=False, since=None, until=None,
         room=None, who=None, symbol=None, account=None,
         include_broker_only=True):
    """Yield (date, row). Filters are optional and case-insensitive.
    since/until are 'YYYY-MM-DD' inclusive. account = 'live' | 'paper'."""
    _ensure()
    if not os.path.exists(LEDGER):
        return
    room_l = room.lower() if room else None
    who_l = who.lower() if who else None
    sym_u = symbol.upper() if symbol else None
    with open(LEDGER, encoding="utf-8", newline="") as fh:
        for c in csv.DictReader(fh):
            st = c.get("state") or ""
            if real_only and st not in REAL_STATES:
                continue
            if nofill_only and st not in NOFILL_STATES:
                continue
            d = c.get("date") or ""
            if since and d < since:
                continue
            if until and d > until:
                continue
            if not include_broker_only and c.get("source") == "trades.log-only":
                continue
            if room_l and (c.get("room") or "").lower() != room_l:
                continue
            if who_l and who_l not in (c.get("caller") or "").lower():
                continue
            if sym_u and (c.get("symbol") or "").upper() != sym_u:
                continue
            if account and (c.get("account") or "") != account:
                continue
            yield d, _to_row(c)


def load(**kw):
    """List form of rows()."""
    return list(rows(**kw))


def days():
    """Sorted distinct dates in the ledger."""
    return sorted({d for d, _ in rows()})


def by_day():
    """{date: [rows]} — for scripts that walked days/*.json one file at a time."""
    out = {}
    for d, r in rows():
        out.setdefault(d, []).append(r)
    return out


# ---------- alerts: master_alerts.csv (every alert and what happened) ----------
ALERTS = os.path.join(HERE, "master_alerts.csv")


def alerts(date=None, since=None, until=None, outcome=None, declined_only=False,
           filled_only=False, room=None, symbol=None):
    """Yield alert dicts from master_alerts.csv. outcome is one of
    'filled' | 'sent-no-fill' | a misses.py reason label. declined_only
    = everything that never reached the broker."""
    if not os.path.exists(ALERTS):
        try:
            import build_alerts
            build_alerts.refresh()
        except Exception:                               # noqa: BLE001
            pass
    if not os.path.exists(ALERTS):
        return
    room_l = room.lower() if room else None
    sym_u = symbol.upper() if symbol else None
    with open(ALERTS, encoding="utf-8", newline="") as fh:
        for c in csv.DictReader(fh):
            d = c.get("date") or ""
            if date and d != date:
                continue
            if since and d < since:
                continue
            if until and d > until:
                continue
            oc = c.get("outcome") or ""
            if outcome and oc != outcome:
                continue
            if declined_only and oc in ("filled", "sent-no-fill"):
                continue
            if filled_only and oc != "filled":
                continue
            if room_l and (c.get("room") or "").lower() != room_l:
                continue
            if sym_u and (c.get("symbol") or "").upper() != sym_u:
                continue
            c["in_ledger"] = _b(c.get("in_ledger"))
            for k in ("their_price", "our_fill", "slip_abs", "slip_pct", "strike",
                      "read_ms", "decide_ms", "fill_ms", "total_ms"):
                c[k] = _f(c.get(k))
            yield c


if __name__ == "__main__":
    from collections import Counter
    real = load(real_only=True)
    print(f"{LEDGER}: {len(real)} real fills over {len(days())} days")
    for rm, n in Counter(r["room"] for _, r in real).most_common(12):
        print(f"  {n:>4}  {rm}")
