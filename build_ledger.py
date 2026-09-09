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
    "greeks_in", "greeks_out", "broker_confirmed", "export_confirmed", "store_pl",
    "source", "in_table", "in_wallet",
    "opened_from", "exit_from", "derived", "day_file", "raw", "why",
]

FILLED_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\t]*)\tFILLED\s+(\S+)\s+—\s+filled\s+([\d.]+)\s+at\s+([\d.]+)"
)
FUT_RE = re.compile(r"^(MES|MNQ|NQ|ES|MGC|GC|CL|MCL|RTY|M2K|YM|MYM)[FGHJKMNQUVXZ]?\d{0,2}$")


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


def _iso_epoch(s):
    """'2026-09-08T10:25:17-04:00' -> epoch float (None if unparseable)."""
    try:
        return datetime.fromisoformat(s).timestamp()
    except (TypeError, ValueError):
        return None


def _kind(r):
    """Infer kind when the store didn't record it (wallet rows never do)."""
    k = r.get("kind")
    if k:
        return k
    sym = str(r.get("symbol") or "").upper()
    if FUT_RE.match(sym):
        return "future"
    if r.get("strike") is not None or r.get("occ"):
        return "option"
    return ""


def _state(r):
    """Infer state for the two wallet rows that carry none."""
    s = r.get("state")
    if s:
        return s
    if r.get("exit") is not None or r.get("all_out"):
        return "closed"
    if r.get("fill") is not None or r.get("avg") is not None:
        return "filled"
    return ""


def _dedupe_key(r, date):
    """Same trade in two stores = same date, caller, contract, fill price.
    NO time in the key: wallet rows carry only "t" (the EXIT event), so a
    time bucket split every table/wallet twin (9/8: TSLA 372.5C and QQQ 717P
    each counted twice, -$40 against the broker). Two genuinely separate
    trades that collide here are told apart in load_days() by their entry
    times (both present, >2 min apart)."""
    price = _r2(r.get("fill")) or _r2(r.get("avg"))
    return (
        date,
        str(r.get("who") or "").strip().lower(),
        str(r.get("symbol") or "").upper(),
        _r2(r.get("strike")),
        str(r.get("side") or "").upper(),
        price,
    )


def _same_trade(a, b):
    """Twins unless BOTH know their entry time and those disagree by >2 min."""
    ta, tb = _f(a.get("opened")), _f(b.get("opened"))
    if ta is None or tb is None:
        return True
    return abs(ta - tb) <= 120


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
                bucket = merged.setdefault(k, [])
                for i, prev in enumerate(bucket):
                    if _same_trade(prev, r):
                        m = _merge(prev, r)
                        # the table zeroes qty after a close; wallet keeps it
                        if not _f(prev.get("qty")) and _f(r.get("qty")):
                            m["qty"] = r["qty"]
                        m["_in_table"] = prev["_in_table"] or r["_in_table"]
                        m["_in_wallet"] = prev["_in_wallet"] or r["_in_wallet"]
                        bucket[i] = m
                        break
                else:
                    bucket.append(r)
    # flatten: one dict per real trade, stable order
    flat = {}
    for k, bucket in merged.items():
        for i, r in enumerate(bucket):
            flat[k + (i,)] = r
    return flat


# ---------- load trades.log FILLED spine ----------
def load_broker_fills():
    """(date, SYMBOL, price) -> [ {qty, ts, used}, ... ]  — a QUEUE, because
    the same contract can fill twice at one price in a day and each FILLED
    line may confirm exactly one ledger row."""
    fills = {}
    if not os.path.exists(TRADES_LOG):
        return fills
    with open(TRADES_LOG, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = FILLED_RE.match(line)
            if not m:
                continue
            iso, sym, qty, price = m.group(1), m.group(2).upper(), m.group(3), m.group(4)
            key = (iso[:10], sym, round(float(price), 2))
            fills.setdefault(key, []).append(
                {"qty": _f(qty), "ts": _iso_epoch(iso), "used": False})
    return fills


def _take_fill(broker, key):
    """First unused FILLED line for this key, marked used. None if spent."""
    for b in broker.get(key, ()):
        if not b["used"]:
            b["used"] = True
            return b
    return None


# ---------- load Webull order-history exports (broker's OWN record) ----------
OCC_RE = re.compile(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$")


def _parse_occ(occ):
    m = OCC_RE.match(occ or "")
    if not m:
        return None
    sym, ymd, cp, strike8 = m.groups()
    return {"symbol": sym, "expiry": "20%s-%s-%s" % (ymd[:2], ymd[2:4], ymd[4:6]),
            "cp": cp, "strike": int(strike8) / 1000.0}


# master_broker.csv — THE broker-record family's one central file (9/9, G:
# "pull the real records from the broker to compare and then delete it at
# the end of the day so the folder is clean"). Every Webull order leg the
# account ever reported, all days, one row each. The autopilot writes the
# day's pull as Webull_Orders_<date>_auto.csv; absorb_exports() folds it in
# here and REMOVES the daily file the moment every leg is provably inside —
# so the folder holds one broker file, never a pile of dated ones.
BROKER = os.path.join(HERE, "master_broker.csv")
BAK_DIR = os.path.join(HERE, "backups")
EXPORT_GLOB = os.path.join(HERE, "Webull_Orders_*_auto.csv")
BROKER_COLS = ["date", "placed_time", "filled_time", "occ", "symbol", "side",
               "status", "filled", "total_qty", "price", "avg_price", "tif",
               "from_file"]
# an order in one of these states will never change again; anything else
# (WORKING, PENDING, PARTIAL…) is a snapshot that a later pull REPLACES.
FINAL_STATUS = ("FILLED", "CANCELLED", "CANCELED", "REJECTED", "EXPIRED", "FAILED")


def _order_key(leg):
    """Identity of one ORDER (not one snapshot of it): the export carries no
    order id, so placed-time + contract + side + size + limit is the key."""
    return (leg.get("placed_time") or "", leg.get("occ") or "",
            leg.get("side") or "", leg.get("total_qty") or "", leg.get("price") or "")


def _snap_key(leg):
    """What a later pull may change about the same order."""
    return (leg.get("status") or "", leg.get("filled_time") or "",
            leg.get("filled") or "", leg.get("avg_price") or "")


def _export_legs(path):
    """One daily Webull_Orders file → rows in master_broker shape.
    None if the file can't be read (leave it alone, try next time)."""
    legs = []
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for c in csv.DictReader(fh):
                occ = (c.get("Name OCC") or "").strip().upper()
                if not occ:
                    continue
                placed = (c.get("Placed Time") or "").strip()
                filled = (c.get("Filled Time") or "").strip()
                legs.append({
                    "date": (filled or placed)[:10],
                    "placed_time": placed, "filled_time": filled,
                    "occ": occ, "symbol": (c.get("Symbol") or "").strip().upper(),
                    "side": (c.get("Side") or "").strip().upper(),
                    "status": (c.get("Status") or "").strip().upper(),
                    "filled": (c.get("Filled") or "").strip(),
                    "total_qty": (c.get("Total Qty") or "").strip(),
                    "price": (c.get("Price") or "").strip(),
                    "avg_price": (c.get("Avg Price") or "").strip(),
                    "tif": (c.get("Time-in-Force") or "").strip(),
                    "from_file": os.path.basename(path),
                })
    except (OSError, csv.Error, UnicodeDecodeError):
        return None
    return legs


def _read_broker():
    rows = []
    if not os.path.exists(BROKER):
        return rows
    try:
        with open(BROKER, encoding="utf-8", newline="") as fh:
            rows = [dict(r) for r in csv.DictReader(fh)]
    except (OSError, csv.Error, UnicodeDecodeError):
        pass
    return rows


def _write_broker(rows):
    """Atomic; one dated .bak in backups/ (last 5 kept) because after the
    daily files are gone this file IS the only copy we hold."""
    _rotate_bak(BROKER)
    rows = sorted(rows, key=lambda r: (r.get("date") or "", r.get("placed_time") or "",
                                       r.get("filled_time") or "", r.get("occ") or ""))
    tmp = BROKER + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=BROKER_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in BROKER_COLS})
    os.replace(tmp, BROKER)


def _merge_leg(by_order, leg):
    """REPLACE, DON'T STACK: a later snapshot of the same order replaces a
    non-final one; an identical snapshot is a no-op; a genuinely different
    fill of an identical-looking order is appended. True if anything changed."""
    bucket = by_order.setdefault(_order_key(leg), [])
    sk = _snap_key(leg)
    for prev in bucket:
        if _snap_key(prev) == sk:
            return False
    for i, prev in enumerate(bucket):
        if (prev.get("status") or "") not in FINAL_STATUS:
            bucket[i] = leg
            return True
    bucket.append(leg)
    return True


def absorb_exports():
    """Fold every Webull_Orders_<date>_auto.csv into master_broker.csv, then
    delete each daily file whose legs are all provably in the master.
    Returns (legs_added, files_removed). Never raises."""
    added, removed = 0, 0
    try:
        paths = sorted(glob.glob(EXPORT_GLOB))
        if not paths:
            return 0, 0
        by_order = {}
        for r in _read_broker():
            by_order.setdefault(_order_key(r), []).append(r)
        pending = []
        for path in paths:
            legs = _export_legs(path)
            if legs is None:
                continue
            for leg in legs:
                if _merge_leg(by_order, leg):
                    added += 1
            pending.append((path, legs))
        if added:
            _write_broker([r for b in by_order.values() for r in b])
        have = set()
        for r in _read_broker():                   # re-read: trust only the disk
            have.add(_order_key(r) + _snap_key(r))
        for path, legs in pending:
            if all((_order_key(l) + _snap_key(l)) in have for l in legs):
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass                           # still open somewhere: next time
    except Exception:                               # noqa: BLE001
        pass
    return added, removed


def load_broker_exports():
    """master_broker.csv (after absorbing any daily export lying in the
    folder) → FIFO round-trips per contract:
    [{date, occ, symbol, cp, strike, qty, buy, buy_ts, sell, sell_ts, pl}].
    The broker's own order history is the truest record we hold. Legs are
    paired chronologically per OCC across days (BUY opens, SELL closes), so a
    swing sold the next morning meets its own lot; trip date = the buy's day."""
    absorb_exports()
    legs = []
    for c in _read_broker():
        if (c.get("status") or "").upper() != "FILLED":
            continue
        occ = (c.get("occ") or "").strip().upper()
        info = _parse_occ(occ)
        if not info:
            continue
        ts = c.get("filled_time") or c.get("placed_time") or ""
        try:
            ep = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            continue
        legs.append({"occ": occ, "side": (c.get("side") or "").upper(),
                     "qty": _f(c.get("filled")) or 0,
                     "px": _r2(c.get("avg_price")), "ts": ep,
                     "date": ts[:10], **info})
    legs.sort(key=lambda l: l["ts"])
    trips = []
    lots = {}                                       # occ -> open BUY lots (FIFO)
    for l in legs:
        if l["side"] == "BUY":
            lots.setdefault(l["occ"], []).append(dict(l))
            continue
        q = l["qty"]
        while q > 0 and lots.get(l["occ"]):
            lot = lots[l["occ"]][0]
            take = min(q, lot["qty"])
            trips.append({
                "date": lot["date"], "occ": l["occ"], "symbol": l["symbol"],
                "cp": l["cp"], "strike": l["strike"], "expiry": l["expiry"],
                "qty": take, "buy": lot["px"], "buy_ts": lot["ts"],
                "sell": l["px"], "sell_ts": l["ts"],
                "pl": round((l["px"] - lot["px"]) * take * 100.0, 2),
            })
            lot["qty"] -= take
            q -= take
            if lot["qty"] <= 0:
                lots[l["occ"]].pop(0)
    for occ, open_lots in lots.items():              # bought, never sold
        for lot in open_lots:
            if lot["qty"] > 0:
                trips.append({
                    "date": lot["date"], "occ": occ, "symbol": lot["symbol"],
                    "cp": lot["cp"], "strike": lot["strike"], "expiry": lot["expiry"],
                    "qty": lot["qty"], "buy": lot["px"], "buy_ts": lot["ts"],
                    "sell": None, "sell_ts": None, "pl": None,
                })
    return trips


def _side_letter(side):
    s = str(side or "").upper()
    return "C" if s.startswith("C") else ("P" if s.startswith("P") else "")


# ---------- build rows ----------
def build():
    day_rows = load_days()
    broker = load_broker_fills()
    trips = load_broker_exports()
    trip_used = [False] * len(trips)
    out = []

    def _find_trip(date, sym, strike, cp, fill):
        """First unused export round-trip for this contract at this fill."""
        for i, t in enumerate(trips):
            if trip_used[i] or t["date"] != date or t["symbol"] != sym:
                continue
            if strike is not None and abs(t["strike"] - strike) > 0.001:
                continue
            if cp and t["cp"] != cp:
                continue
            if fill is not None and t["buy"] is not None and abs(t["buy"] - fill) > 0.011:
                continue
            trip_used[i] = True
            return t
        return None

    # One FILLED line confirms ONE row. Rows the book already knew filled go
    # first, so a nofill/failed twin can never steal the real trade's line
    # and get promoted on someone else's fill.
    _REAL = ("filled", "closed", "stopped")
    ordered = sorted(day_rows.values(),
                     key=lambda r: 0 if (r.get("state") or "") in _REAL else 1)
    for r in ordered:
        date = r["_day"]
        sym = str(r.get("symbol") or "").upper()
        fill = _r2(r.get("fill")) or _r2(r.get("avg"))
        bkey = (date, sym, fill) if fill is not None else None
        bhit = _take_fill(broker, bkey) if bkey else None
        confirmed = bhit is not None

        # --- normalize the thin wallet rows (they never carry these) ---
        # entry time: the store's "opened", else the BROKER's FILLED stamp.
        # NOT wallet "t" — that is the last event (the exit), not the entry.
        opened_ts = _f(r.get("opened"))
        opened_from = "store"
        if opened_ts is None and bhit and bhit.get("ts"):
            opened_ts = bhit["ts"]
            opened_from = "trades.log"
        closed_ts = _f(r.get("closed"))
        if closed_ts is None and r.get("exit") is not None:
            closed_ts = _f(r.get("t"))          # wallet: t = exit event
        qty = r.get("qty")
        avg = _r2(r.get("avg"))
        if avg is None:
            avg = fill                          # fill IS the entry price
        entries = r.get("entries")
        derived = False
        if not entries and fill is not None and qty:
            entries = [{"t": opened_ts, "qty": qty, "price": fill}]
            derived = True
        exits = r.get("exits")
        if not exits and r.get("exit") is not None and qty:
            exits = [{"t": closed_ts, "qty": qty, "price": _r2(r.get("exit")),
                      "pl": _r2(r.get("pl"))}]
            derived = True
        # --- the broker's own export: confirm, and fill a missing exit ---
        trip = _find_trip(date, sym, _r2(r.get("strike")), _side_letter(r.get("side")), fill)
        export_confirmed = trip is not None
        exit_from = "store"
        store_pl = _r2(r.get("pl"))
        if trip:
            if opened_ts is None and trip.get("buy_ts"):
                opened_ts, opened_from = trip["buy_ts"], "webull-export"
            if trip.get("sell") is not None:
                # THE BROKER'S OWN RECORD WINS over the book's belief. On 9/8
                # the store said bot -92 / hand +10; the export said +77 —
                # and +77 is what Webull's history shows. The store's number
                # is kept in store_pl so the disagreement stays visible.
                exits = [{"t": trip["sell_ts"], "qty": trip["qty"],
                          "price": trip["sell"], "pl": trip["pl"]}]
                closed_ts = trip["sell_ts"]
                exit_from = "webull-export"
                derived = True
                r["pl"] = trip["pl"]
                r["exit"] = trip["sell"]         # lets _state() say "closed"
                r["pl_pct"] = None               # recomputed below from fill
            if not r.get("occ"):
                r["occ"] = trip["occ"]
        hi = r.get("hi_pct") if r.get("hi_pct") is not None else r.get("max_runup_pct")
        lo = r.get("lo_pct") if r.get("lo_pct") is not None else r.get("max_drawdown_pct")
        runup = r.get("max_runup_pct") if r.get("max_runup_pct") is not None else r.get("hi_pct")
        ddown = r.get("max_drawdown_pct") if r.get("max_drawdown_pct") is not None else r.get("lo_pct")
        pl = _r2(r.get("pl"))
        pl_pct = _r2(r.get("pl_pct"))
        if pl_pct is None and pl is not None and fill and qty:
            try:
                mult = 1.0 if _kind(r) == "future" else 100.0
                pl_pct = round(pl / (fill * float(qty) * mult) * 100.0, 2)
            except (TypeError, ValueError, ZeroDivisionError):
                pl_pct = None

        out.append({
            "date": date,
            "opened": _hms(opened_ts),
            "closed": _hms(closed_ts),
            "opened_ts": opened_ts if opened_ts is not None else "",
            "closed_ts": closed_ts if closed_ts is not None else "",
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
            "kind": _kind(r),
            "qty": qty if qty is not None else "",
            "avg_in": avg if avg is not None else "",
            "fill": fill if fill is not None else "",
            "entries": _json(entries),
            "exits": _json(exits),
            "exit_avg": _exit_avg(exits) if exits else "",
            "pl": pl if pl is not None else "",
            "pl_pct": pl_pct if pl_pct is not None else "",
            "max_runup_pct": _r2(runup) if runup is not None else "",
            "max_drawdown_pct": _r2(ddown) if ddown is not None else "",
            "hi_pct": _r2(hi) if hi is not None else "",
            "lo_pct": _r2(lo) if lo is not None else "",
            # the broker saw it fill → it filled, whatever the book believed.
            # 9/8: IWM 295P and SPY 767P were filed as "failed" by the book
            # while Webull's history shows both filled AND closed (-6, -1).
            "state": ("closed" if (trip and trip.get("sell") is not None)
                      else "filled" if (export_confirmed or confirmed)
                      and _state(r) in ("failed", "nofill", "")
                      else _state(r)),
            "exit_by": r.get("exit_by") or "",
            "all_out": r.get("all_out") if r.get("all_out") is not None else "",
            # the export IS the real account: a fill found there is live no
            # matter what the store thought (9/8: IWM 295P and SPY 767P were
            # filed as paper by the book, yet sit in Webull's own history)
            "account": "live" if (r.get("live") or export_confirmed) else "paper",
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
            "export_confirmed": export_confirmed,
            "store_pl": store_pl if store_pl is not None else "",
            "source": r.get("source") or "days-json",
            "in_table": r["_in_table"],
            "in_wallet": r["_in_wallet"],
            "opened_from": opened_from,
            "exit_from": exit_from,
            "derived": derived,
            "day_file": r["_file"],
            "raw": (r.get("raw") or "").replace("\n", " ").strip(),
            "why": (r.get("why") or "").replace("\n", " ").strip(),
        })

    # broker fills with NO day-JSON row → visible gap rows (every FILLED line
    # nothing above consumed)
    for (date, sym, price), queue in broker.items():
      for b in queue:
        if b["used"]:
            continue
        qty, ts = b.get("qty"), b.get("ts")
        out.append({c: "" for c in COLUMNS} | {
            "date": date, "room": "?", "symbol": sym, "fill": price,
            "avg_in": price, "qty": qty if qty is not None else "",
            "opened": _hms(ts), "opened_ts": ts if ts is not None else "",
            "kind": "future" if FUT_RE.match(sym) else "option",
            "entries": _json([{"t": ts, "qty": qty, "price": price}]) if qty else "",
            "state": "filled",
            # the FILLED line does not say which book — do NOT let a
            # consumer's "" -> paper fallback mislabel a broker fill
            "account": "unknown", "manual": "", "swing": "",
            "broker_confirmed": True, "export_confirmed": False,
            "source": "trades.log-only",
            "in_table": False, "in_wallet": False,
            "opened_from": "trades.log", "exit_from": "", "derived": True,
            "why": "broker FILLED with no day-JSON row (room unknown)",
        })

    # export round-trips no store ever saw → the account's own record wins.
    # These are almost all G's hand scalps (Market Sniper) — visible, his,
    # never the bot's. account=live is a fact here: the export IS the account.
    for i, t in enumerate(trips):
        if trip_used[i]:
            continue
        exits = ([{"t": t["sell_ts"], "qty": t["qty"], "price": t["sell"], "pl": t["pl"]}]
                 if t.get("sell") is not None else [])
        out.append({c: "" for c in COLUMNS} | {
            "date": t["date"], "room": "?", "caller": "",
            "symbol": t["symbol"], "side": "CALLS" if t["cp"] == "C" else "PUTS",
            "strike": t["strike"], "expiry": t["expiry"], "occ": t["occ"],
            "kind": "option", "qty": t["qty"],
            "avg_in": t["buy"], "fill": t["buy"],
            "opened": _hms(t["buy_ts"]), "opened_ts": t["buy_ts"],
            "closed": _hms(t["sell_ts"]) if t.get("sell_ts") else "",
            "closed_ts": t["sell_ts"] if t.get("sell_ts") else "",
            "entries": _json([{"t": t["buy_ts"], "qty": t["qty"], "price": t["buy"]}]),
            "exits": _json(exits), "exit_avg": t["sell"] if t.get("sell") is not None else "",
            "pl": t["pl"] if t.get("pl") is not None else "",
            "pl_pct": (round(t["pl"] / (t["buy"] * t["qty"] * 100.0) * 100.0, 2)
                       if t.get("pl") is not None and t["buy"] else ""),
            "state": "closed" if t.get("sell") is not None else "filled",
            "all_out": t.get("sell") is not None,
            "account": "live", "manual": True, "swing": "",
            "broker_confirmed": False, "export_confirmed": True,
            "source": "webull-export-only",
            "in_table": False, "in_wallet": False,
            "opened_from": "webull-export", "exit_from": "webull-export",
            "derived": True,
            "why": "in the Webull order export, in no store — a hand trade",
        })

    out.sort(key=lambda x: (x["date"], x["opened"] or "99:99:99", x["symbol"]))
    return out, broker


# ---------- write ----------
def _rotate_bak(path=OUT):
    """Dated copy of `path` into backups/ (last KEEP_BAKS kept) — the folder
    root stays clean (9/9). Never raises: a backup must not block a write."""
    try:
        if not os.path.exists(path):
            return
        os.makedirs(BAK_DIR, exist_ok=True)
        base = os.path.basename(path)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, os.path.join(BAK_DIR, f"{base}.bak-{stamp}"))
        for old in sorted(glob.glob(os.path.join(BAK_DIR, f"{base}.bak-*")))[:-KEEP_BAKS]:
            try:
                os.remove(old)
            except OSError:
                pass
    except OSError:
        pass


def write(rows, bak=True):
    """bak=True (CLI) keeps a timestamped copy of the prior ledger.
    bak=False (bridge, on every event) skips it — no .bak churn all day."""
    if bak:
        _rotate_bak(OUT)
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
    hand = [r for r in rows if r["source"] == "webull-export-only"]
    conf = sum(1 for r in real if r["broker_confirmed"])
    xconf = sum(1 for r in real if r.get("export_confirmed"))
    xexit = sum(1 for r in real if r.get("exit_from") == "webull-export")
    untag = sum(1 for r in real if r["room"] == "?")
    print(f"master_ledger.csv  →  {len(rows)} rows")
    print(f"  real fills (filled/closed/stopped): {len(real)}")
    print(f"  no-fill / failed attempts:          {len(nofill)}")
    print(f"  trades.log-confirmed fills:         {conf}/{len(real)}")
    print(f"  Webull-export-confirmed fills:      {xconf}/{len(real)}")
    print(f"  exits filled in FROM the export:    {xexit}")
    print(f"  broker fills with no room row:      {len(gaps)}  (source=trades.log-only)")
    print(f"  hand trades only in the export:     {len(hand)}  (source=webull-export-only)")
    print(f"  real fills untagged room '?':       {untag}")
    # RECONCILIATION — the ledger must equal the broker's own history on
    # every day we hold an export. If a day drifts, something upstream lied.
    trips = load_broker_exports()
    days_x = sorted({t["date"] for t in trips})
    legs = _read_broker()
    print(f"  master_broker.csv: {len(legs)} order legs over "
          f"{len({l.get('date') for l in legs})} days "
          f"({sum(1 for l in legs if l.get('status') == 'FILLED')} filled); "
          f"daily Webull_Orders files left in folder: "
          f"{len(glob.glob(EXPORT_GLOB))}")
    if days_x:
        print()
        print("  RECONCILIATION vs Webull order export (live, real fills):")
        for day in days_x:
            ex = sum(t["pl"] for t in trips if t["date"] == day and t["pl"] is not None)
            lg = sum(_f(r["pl"]) or 0 for r in real
                     if r["date"] == day and r["account"] == "live" and r["pl"] != "")
            ok = abs(ex - lg) < 0.01
            print(f"   {day}  export {ex:+9.2f}   ledger {lg:+9.2f}   "
                  f"{'MATCH' if ok else 'DRIFT %+.2f  <-- INVESTIGATE' % (lg - ex)}")
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
