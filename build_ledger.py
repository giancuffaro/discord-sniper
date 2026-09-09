#!/usr/bin/env python3
"""
build_ledger.py — ONE central fill ledger from every source we have.

WHY THIS EXISTS (2026-09-09):
  Fills were scattered across three half-ledgers that disagree:
    days/*.json  "table"          — display rows; truncates/resets (dropped Aristotle 9/8)
    days/*.json  "wallet.trades"  — richest fields; clears on restart (only today survives)
    trades.log   FILLED lines     — immutable broker spine; no room/caller tag
  journal.csv is built from "table" only, so it inherits the truncation bug.

WHAT IT DOES:
  1. Unions table ∪ wallet.trades per day, MERGES duplicate rows field-by-field
     (prefers the non-empty value, so runup/drawdown/greeks survive).
  2. Cross-checks every row against trades.log FILLED (date, symbol, price)
     → broker_confirmed column. Broker fills with NO day-JSON row are added
     as their own rows (room="?", source="trades.log-only") so gaps are VISIBLE.
  3. Writes master_ledger.csv — deterministic full rebuild every run
     (no append = no double-count on restart). Prior file → timestamped .bak
     (last 5 kept).

SAFETY:
  Read-only over every source. Touches nothing on the live path.
  Only writes master_ledger.csv and its .bak files. Safe to run any time.

RUN:   python3 build_ledger.py            (rebuild + print summary)
       python3 build_ledger.py --quiet    (rebuild only)
"""
import csv
import glob
import json
import os
import re
import shutil
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DAYS_DIR = os.path.join(HERE, "days")
TRADES_LOG = os.path.join(HERE, "trades.log")
OUT = os.path.join(HERE, "master_ledger.csv")
KEEP_BAKS = 5

COLUMNS = [
    "date", "opened", "closed", "opened_ts", "closed_ts", "t",
    "room", "caller", "key",
    "symbol", "side", "direction", "strike", "expiry", "dte", "occ", "kind",
    "qty", "avg_in", "fill", "entries", "exits", "exit_avg", "pl", "pl_pct",
    "max_runup_pct", "max_drawdown_pct", "hi_pct", "lo_pct",
    "state", "exit_by", "all_out", "account", "manual", "swing",
    "their_avg", "their_stop", "their_target", "their_units", "stop_at_exit",
    "greeks_in", "greeks_out", "broker_confirmed", "source", "in_table", "in_wallet",
    "day_file", "raw", "why",
]

FILLED_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})T\S+\tFILLED\s+(\S+)\s+—\s+filled\s+([\d.]+)\s+at\s+([\d.]+)"
)


# ---------- helpers ----------
def _f(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _hms(epoch):
    if not epoch:
        return ""
    try:
        return datetime.fromtimestamp(float(epoch)).strftime("%H:%M:%S")
    except (TypeError, ValueError, OSError):
        return ""


def _r2(v):
    v = _f(v)
    return None if v is None else round(v, 2)


def _json(v):
    return "" if v in (None, "", [], {}) else json.dumps(v, separators=(",", ":"))


def _exit_avg(exits):
    if not isinstance(exits, list) or not exits:
        return None
    tot_q = sum(_f(e.get("qty")) or 0 for e in exits)
    if tot_q <= 0:
        return None
    return round(sum((_f(e.get("qty")) or 0) * (_f(e.get("price")) or 0) for e in exits) / tot_q, 2)


def _merge(a, b):
    """Field-wise merge: keep a's value unless empty, then take b's."""
    out = dict(a)
    for k, v in b.items():
        if out.get(k) in (None, "", [], {}) and v not in (None, "", [], {}):
            out[k] = v
    return out


def _dedupe_key(r, date):
    price = _r2(r.get("fill")) or _r2(r.get("avg"))
    opened = r.get("opened") or r.get("t")
    opened_min = int(float(opened) // 60) if opened else None   # minute bucket
    return (
        date,
        str(r.get("who") or "").strip().lower(),
        str(r.get("symbol") or "").upper(),
        _r2(r.get("strike")),
        str(r.get("side") or "").upper(),
        price,
        opened_min,
    )


# ---------- load day-JSON (table ∪ wallet.trades) ----------
def load_days():
    merged = {}          # dedupe_key -> merged row dict (+ _in_table/_in_wallet/_day)
    for path in sorted(glob.glob(os.path.join(DAYS_DIR, "*.json"))):
        if path.endswith(".bak"):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        date = d.get("date") or os.path.basename(path)[:10]
        table = d.get("table") or []
        wallet = ((d.get("wallet") or {}).get("trades")) or []
        for src_name, rows in (("table", table), ("wallet", wallet)):
            for r in rows:
                if not isinstance(r, dict) or not r.get("symbol"):
                    continue
                k = _dedupe_key(r, date)
                r = dict(r)
                r["_in_table"] = src_name == "table"
                r["_in_wallet"] = src_name == "wallet"
                r["_day"] = date
                r["_file"] = os.path.basename(path)
                if k in merged:
                    prev = merged[k]
                    m = _merge(prev, r)
                    m["_in_table"] = prev["_in_table"] or r["_in_table"]
                    m["_in_wallet"] = prev["_in_wallet"] or r["_in_wallet"]
                    merged[k] = m
                else:
                    merged[k] = r
    return merged


# ---------- load trades.log FILLED spine ----------
def load_broker_fills():
    fills = {}   # (date, SYMBOL, price) -> qty  (first seen)
    if not os.path.exists(TRADES_LOG):
        return fills
    with open(TRADES_LOG, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = FILLED_RE.match(line)
            if not m:
                continue
            date, sym, qty, price = m.group(1), m.group(2).upper(), m.group(3), m.group(4)
            key = (date, sym, round(float(price), 2))
            fills.setdefault(key, _f(qty))
    return fills


# ---------- build rows ----------
def build():
    day_rows = load_days()
    broker = load_broker_fills()
    matched_broker = set()
    out = []

    for r in day_rows.values():
        date = r["_day"]
        sym = str(r.get("symbol") or "").upper()
        fill = _r2(r.get("fill")) or _r2(r.get("avg"))
        bkey = (date, sym, fill) if fill is not None else None
        confirmed = bkey in broker if bkey else False
        if confirmed:
            matched_broker.add(bkey)
        exits = r.get("exits")
        out.append({
            "date": date,
            "opened": _hms(r.get("opened") or r.get("t")),
            "closed": _hms(r.get("closed")),
            "opened_ts": _f(r.get("opened")) or "",
            "closed_ts": _f(r.get("closed")) or "",
            "t": _f(r.get("t")) or "",
            "room": (r.get("room") or "?").strip() or "?",
            "caller": (r.get("who") or "").strip(),
            "key": r.get("key") or "",
            "symbol": sym,
            "side": (r.get("side") or "").upper(),
            "direction": r.get("direction") if r.get("direction") is not None else "",
            "strike": _r2(r.get("strike")) if r.get("strike") is not None else "",
            "expiry": r.get("expiry") or "",
            "dte": r.get("dte") if r.get("dte") is not None else "",
            "occ": r.get("occ") or "",
            "kind": r.get("kind") or "",
            "qty": r.get("qty") if r.get("qty") is not None else "",
            "avg_in": _r2(r.get("avg")) if r.get("avg") is not None else "",
            "fill": fill if fill is not None else "",
            "entries": _json(r.get("entries")),
            "exits": _json(exits),
            "exit_avg": _exit_avg(exits) if exits else "",
            "pl": _r2(r.get("pl")) if r.get("pl") is not None else "",
            "pl_pct": _r2(r.get("pl_pct")) if r.get("pl_pct") is not None else "",
            "max_runup_pct": _r2(r.get("max_runup_pct")) if r.get("max_runup_pct") is not None else "",
            "max_drawdown_pct": _r2(r.get("max_drawdown_pct")) if r.get("max_drawdown_pct") is not None else "",
            "hi_pct": _r2(r.get("hi_pct")) if r.get("hi_pct") is not None else "",
            "lo_pct": _r2(r.get("lo_pct")) if r.get("lo_pct") is not None else "",
            "state": r.get("state") or "",
            "exit_by": r.get("exit_by") or "",
            "all_out": r.get("all_out") if r.get("all_out") is not None else "",
            "account": "live" if r.get("live") else "paper",
            "manual": bool(r.get("manual")),
            "swing": bool(r.get("swing")),
            "their_avg": _r2(r.get("their_avg")) if r.get("their_avg") is not None else "",
            "their_stop": _r2(r.get("their_stop")) if r.get("their_stop") is not None else "",
            "their_target": _r2(r.get("their_target")) if r.get("their_target") is not None else "",
            "their_units": r.get("their_units") if r.get("their_units") is not None else "",
            "stop_at_exit": _r2(r.get("stop_at_exit")) if r.get("stop_at_exit") is not None else "",
            "greeks_in": _json(r.get("greeks_in")),
            "greeks_out": _json(r.get("greeks_out")),
            "broker_confirmed": confirmed,
            "source": r.get("source") or "days-json",
            "in_table": r["_in_table"],
            "in_wallet": r["_in_wallet"],
            "day_file": r["_file"],
            "raw": (r.get("raw") or "").replace("\n", " ").strip(),
            "why": (r.get("why") or "").replace("\n", " ").strip(),
        })

    # broker fills with NO day-JSON row → visible gap rows
    for (date, sym, price), qty in broker.items():
        if (date, sym, price) in matched_broker:
            continue
        out.append({c: "" for c in COLUMNS} | {
            "date": date, "room": "?", "symbol": sym, "fill": price,
            "qty": qty if qty is not None else "", "state": "filled",
            "account": "", "manual": "", "swing": "",
            "broker_confirmed": True, "source": "trades.log-only",
            "in_table": False, "in_wallet": False,
            "why": "broker FILLED with no day-JSON row (room unknown)",
        })

    out.sort(key=lambda x: (x["date"], x["opened"] or "99:99:99", x["symbol"]))
    return out, broker


# ---------- write ----------
def _rotate_bak():
    if os.path.exists(OUT):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(OUT, f"{OUT}.bak-{stamp}")
    baks = sorted(glob.glob(f"{OUT}.bak-*"))
    for old in baks[:-KEEP_BAKS]:
        try:
            os.remove(old)
        except OSError:
            pass


def write(rows, bak=True):
    """bak=True (CLI) keeps a timestamped copy of the prior ledger.
    bak=False (bridge, on every event) skips it — no .bak churn all day."""
    if bak:
        _rotate_bak()
    tmp = OUT + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    os.replace(tmp, OUT)      # atomic swap — never a half-written ledger


def summary(rows, broker):
    from collections import Counter
    real = [r for r in rows if r["state"] in ("filled", "closed", "stopped")]
    nofill = [r for r in rows if r["state"] in ("nofill", "failed")]
    gaps = [r for r in rows if r["source"] == "trades.log-only"]
    conf = sum(1 for r in real if r["broker_confirmed"])
    untag = sum(1 for r in real if r["room"] == "?")
    print(f"master_ledger.csv  →  {len(rows)} rows")
    print(f"  real fills (filled/closed/stopped): {len(real)}")
    print(f"  no-fill / failed attempts:          {len(nofill)}")
    print(f"  broker-confirmed fills:             {conf}/{len(real)}")
    print(f"  broker fills with no room row:      {len(gaps)}  (source=trades.log-only)")
    print(f"  real fills untagged room '?':       {untag}")
    print()
    print("  REAL FILLS PER ROOM:")
    for rm, n in Counter(r["room"] for r in real).most_common():
        print(f"   {n:>4}  {rm}")


def refresh():
    """One-call rebuild for the bridge's save_day(). Never raises."""
    try:
        rows, _ = build()
        write(rows, bak=False)
    except Exception:                                   # noqa: BLE001
        pass        # the ledger must never take down the trading path


if __name__ == "__main__":
    rows, broker = build()
    write(rows)
    if "--quiet" not in sys.argv:
        summary(rows, broker)
