#!/usr/bin/env python3
"""Pull the day's broker truth from Webull, once, after the close.

WHY THIS FILE EXISTS (9/15). HANDOFF said "the autopilot pulls the account's
order history every Mode B run and writes it to Webull_Orders_auto.csv". No
code did that. `build_ledger.absorb_exports()` only folds a file that something
ELSE must have written, and the only thing that ever wrote it was a Claude
session using the Webull connector by hand — `now.py` says so out loud: "no
order_history() on the adapter — ask Claude to pull it from the Webull
connector". The last hand pull was 2026-09-11, so from 9/12 on every day's
report read "broker export missing" and every hand trade was invisible. 9/14
alone was 60 order legs, 47 filled, −$321 the books never saw.

WHAT IT IS. A ONE-SHOT, READ-ONLY, AFTER-CLOSE step of the daily audit:

  1 order history for the day (paged) -> Webull_Orders_auto.csv, OVERWRITTEN
    (G, 9/10: "have one that overwrites" — no deletes, no dated piles)
  2 the account balance -> one appended row in balance_daily.csv
  3 THE FUTURES ACCOUNT (G, 9/16: "add futures from now on") — its filled
    legs -> master_futures.csv (one row per order id, fees included), and its
    net liquidation, day result and fees onto the SAME balance_daily.csv row.
    9/16 was 46 futures fills, -$72 gross and $39 of fees that no report saw,
    and a $500 margin->futures transfer the brief printed as a -$465 day.
    `flow` / `fut_flow` are what moved in or out of each account that was NOT
    trading: (net liquidation change) - (the day's net result).
  4 build_ledger, which absorbs the export into master_broker.csv and
    reconciles it against master_ledger.csv to the cent

NOT A SECOND CLIENT AND NOT A POLL LOOP. It builds ONE WebullOptions the way
health.py already does, uses it for two reads, and exits. It runs once a day,
after the close, when the bridge's quote bus is idle — a handful of hits
against the 2-per-2s door, not a loop competing with the stops. It never places, cancels
or modifies an order, and never touches settings.json.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.path.join(HERE, "Webull_Orders_auto.csv")
BALANCES = os.path.join(HERE, "balance_daily.csv")

EXPORT_HEAD = ["Name OCC", "Symbol", "Side", "Status", "Filled", "Total Qty",
               "Price", "Avg Price", "Time-in-Force", "Placed Time",
               "Filled Time"]
FUTURES = os.path.join(HERE, "master_futures.csv")
HISTORY_DOOR_S = 2.5        # Webull: order history is 2 requests per 2 seconds
BALANCE_HEAD = ["date", "nlv", "day_pl", "bp", "read_at",
                "fut_nlv", "fut_pl", "fut_fees", "flow", "fut_flow"]
FUT_HEAD = ["date", "filled_time", "symbol", "code", "side", "qty", "price",
            "fees", "order_id"]

# Dollars per index point, per contract — Webull's own instrument list
# (`size`), read 2026-09-16. The E-nanos (NNQ/NES/N2K/NDOW) began trading
# 2026-08-24. JOURNAL ARITHMETIC ONLY: this table prices fills that already
# happened. What the bridge may TRADE is webull_futures.FUT_SPECS and its
# proof gate, which this file never touches. A code missing here is reported
# as unpriced — never guessed.
FUT_POINT_VALUE = {"ES": 50.0, "MES": 5.0, "NES": 0.5,
                   "NQ": 20.0, "MNQ": 2.0, "NNQ": 0.2,
                   "RTY": 50.0, "M2K": 5.0, "N2K": 0.5,
                   "YM": 5.0, "MYM": 0.5, "NDOW": 0.05}


def _settings():
    with open(os.path.join(HERE, "settings.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _client(settings):
    """The one adapter, connected. health.py's pattern, and its warning: give
    WebullOptions the WHOLE settings dict (it digs out execution.webull
    itself), and connect() FIRST or account_id is still blank."""
    from webull_options import WebullOptions
    client = WebullOptions(settings)
    if not client.connect():
        raise IOError("connect() returned no account id")
    return client


def _et_stamp(value):
    """Webull stamps UTC ('2026-09-14T14:36:56.809Z'); the export build_ledger
    already absorbs is Eastern wall-clock, and its `date` column is cut from
    it. Getting this wrong moves a 16:05 fill onto the next day."""
    if not value:
        return ""
    text = str(value)
    try:
        moment = dt.datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return text[:19].replace("T", " ")
    try:
        import eastern
        return moment.replace(tzinfo=dt.timezone.utc).astimezone(
            eastern.ZONE if hasattr(eastern, "ZONE")
            else dt.timezone(dt.timedelta(hours=-4))
        ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:                                   # noqa: BLE001
        return (moment - dt.timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")


def _occ(order):
    """The leg's OCC symbol via occ.py — the ONE builder — or "" when the row
    does not name a contract. occ.build raises on an unreadable side instead
    of defaulting to a put; an unreadable row is dropped, never guessed."""
    import occ
    legs = order.get("legs") or []
    leg = legs[0] if legs else {}
    try:
        return occ.build(
            leg.get("symbol") or order.get("symbol"),
            str(leg.get("option_expire_date")
                or order.get("option_expire_date") or "")[:10],
            leg.get("option_type") or order.get("option_type"),
            leg.get("strike_price") or leg.get("option_exercise_price"))
    except (ValueError, TypeError):
        return ""


def export_rows(orders):
    """Raw SDK order dicts -> the export shape master_broker.csv absorbs.
    `Price` is the limit, else the stop (HANDOFF: a stop leg has no limit)."""
    rows = []
    for order in orders:
        if str(order.get("instrument_type") or "OPTION") != "OPTION":
            continue
        occ = _occ(order)
        if not occ:
            continue
        rows.append([occ, order.get("symbol") or "", order.get("side") or "",
                     order.get("status") or "",
                     order.get("filled_quantity") or "0",
                     order.get("total_quantity") or "0",
                     order.get("limit_price") or order.get("stop_price") or "",
                     order.get("filled_price") or "",
                     order.get("time_in_force") or "",
                     _et_stamp(order.get("place_time_at")),
                     _et_stamp(order.get("filled_time_at"))])
    rows.sort(key=lambda r: r[9])
    return rows


def write_export(rows, path=None):
    path = path or EXPORT
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(EXPORT_HEAD)
        writer.writerows(rows)
    os.replace(tmp, path)
    return len(rows)


def _fut_code(symbol):
    """'MNQZ6' -> 'MNQ': the product code is the symbol less its month letter
    and year digit(s)."""
    text = str(symbol or "").upper().strip()
    while text and text[-1].isdigit():
        text = text[:-1]
    return text[:-1] if len(text) > 1 else text


def futures_rows(orders):
    """Raw SDK order dicts -> one master_futures.csv row per FILLED futures
    leg. Fees are Webull's own per-order `fees[].actual_value`, summed."""
    rows = []
    for order in orders:
        if str(order.get("instrument_type") or "").upper() != "FUTURES":
            continue
        if str(order.get("status") or "").upper() != "FILLED":
            continue
        stamp = _et_stamp(order.get("filled_time_at")
                          or order.get("place_time_at"))
        symbol = str(order.get("symbol") or "").upper()
        fees = 0.0
        for fee in (order.get("fees") or []):
            try:
                fees += float(fee.get("actual_value") or 0)
            except (TypeError, ValueError, AttributeError):
                pass
        rows.append([stamp[:10], stamp, symbol, _fut_code(symbol),
                     str(order.get("side") or "").upper(),
                     order.get("filled_quantity") or "0",
                     order.get("filled_price") or "",
                     "%.2f" % fees,
                     order.get("order_id") or order.get("client_order_id")
                     or ""])
    rows.sort(key=lambda r: r[1])
    return rows


def merge_futures(rows, path=None):
    """Fold the pulled legs into master_futures.csv. ONE ROW PER ORDER ID: a
    re-run replaces a leg it already has, never stacks a second copy."""
    path = path or FUTURES
    have = {}
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            for old in list(csv.reader(fh))[1:]:
                if old and len(old) == len(FUT_HEAD):
                    have[old[-1] or "|".join(old)] = old
    except OSError:
        pass
    for row in rows:
        have[row[-1] or "|".join(row)] = row
    out = sorted(have.values(), key=lambda r: r[1])
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(FUT_HEAD)
        writer.writerows(out)
    os.replace(tmp, path)
    return len(out)


def futures_day(day, path=None):
    """The day's futures result from master_futures.csv.

    gross = cash from round trips that CLOSED FLAT that day, per product.
    A product still open at the end of the day (or carried in) cannot be
    scored from one day's fills, and a product with no point value here
    cannot be priced — both are NAMED in `open` / `unpriced`, and `gross` /
    `net` come back None rather than a number that leaves them out."""
    path = path or FUTURES
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            rows = [r for r in csv.DictReader(fh)
                    if (r.get("date") or "") == day]
    except OSError:
        rows = []
    if not rows:
        return None
    per, fees, contracts = {}, 0.0, 0.0
    for r in rows:
        try:
            qty, price = float(r["qty"] or 0), float(r["price"] or 0)
            fees += float(r.get("fees") or 0)
        except (TypeError, ValueError):
            continue
        sign = 1.0 if (r.get("side") or "").startswith("S") else -1.0
        slot = per.setdefault(r.get("code") or "", {"pos": 0.0, "pts": 0.0,
                                                    "fills": 0})
        slot["pos"] -= sign * qty
        slot["pts"] += sign * qty * price
        slot["fills"] += 1
        contracts += qty
    gross, open_, unpriced, by_code = 0.0, [], [], {}
    for code, slot in sorted(per.items()):
        value = FUT_POINT_VALUE.get(code)
        if abs(slot["pos"]) > 1e-9:
            open_.append(code)
        elif value is None:
            unpriced.append(code)
        else:
            by_code[code] = round(slot["pts"] * value, 2)
            gross += by_code[code]
    whole = not open_ and not unpriced
    return {"fills": len(rows), "contracts": contracts,
            "gross": round(gross, 2) if whole else None,
            "fees": round(fees, 2),
            "net": round(gross - fees, 2) if whole else None,
            "by_code": by_code, "open": open_, "unpriced": unpriced}


def _prior(existing, day, column):
    """The last value recorded in `column` BEFORE `day`, or None."""
    index = BALANCE_HEAD.index(column)
    for old in sorted((r for r in existing if r and r[0] < day),
                      key=lambda r: r[0], reverse=True):
        if len(old) > index and old[index] != "":
            try:
                return float(old[index])
            except ValueError:
                return None
    return None


def record_balance(day, snapshot, path=None, futures=None):
    """Append one row per trading day. Append-only, and a re-run replaces that
    day's row rather than stacking a second one — one day, one balance.

    `futures` = {"nlv", "pl", "fees"} for the futures account, any of them
    None. `flow` / `fut_flow` = (net liquidation change since the last
    recorded day) - (that day's net result): a transfer, deposit or
    withdrawal. Blank when any of the three numbers is missing."""
    path = path or BALANCES
    snapshot, futures = snapshot or {}, futures or {}
    if not snapshot and futures.get("nlv") is None:
        return None
    existing, seen = [], False
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            existing = [r for r in csv.reader(fh)][1:]
    except OSError:
        pass
    width = len(BALANCE_HEAD)
    existing = [(r + [""] * width)[:width] for r in existing if r]

    def cell(value):
        return "" if value is None else "%.2f" % value

    def flow(now, column, result):
        before = _prior(existing, day, column)
        if now is None or before is None or result is None:
            return None
        return round(now - before - result, 2)

    row = [day, cell(snapshot.get("nlv")), cell(snapshot.get("day_pl")),
           cell(snapshot.get("bp")),
           dt.datetime.now().astimezone().isoformat(timespec="seconds"),
           cell(futures.get("nlv")), cell(futures.get("pl")),
           cell(futures.get("fees")),
           cell(flow(snapshot.get("nlv"), "nlv", snapshot.get("day_pl"))),
           cell(flow(futures.get("nlv"), "fut_nlv", futures.get("pl")))]
    out = []
    for old in existing:
        if old and old[0] == day:
            out.append(row)
            seen = True
        else:
            out.append(old)
    if not seen:
        out.append(row)
    out.sort(key=lambda r: r[0] if r else "")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(BALANCE_HEAD)
        writer.writerows(out)
    os.replace(tmp, path)
    return row


def latest_balance(day=None, path=None):
    """The most recent recorded balance (optionally for one exact day), as a
    dict, or None. This is what the brief falls back to when it is run by
    hand with no bridge and no broker."""
    path = path or BALANCES
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return None
    if day:
        rows = [r for r in rows if (r.get("date") or "") == day]
    if not rows:
        return None
    row = rows[-1]

    def num(key):
        try:
            return float(row.get(key) or "")
        except (TypeError, ValueError):
            return None
    return {"date": row.get("date") or "", "nlv": num("nlv"),
            "day_pl": num("day_pl"), "bp": num("bp"),
            "read_at": row.get("read_at") or "",
            "fut_nlv": num("fut_nlv"), "fut_pl": num("fut_pl"),
            "fut_fees": num("fut_fees"), "flow": num("flow"),
            "fut_flow": num("fut_flow")}


def main(day=None):
    day = day or dt.date.today().isoformat()
    settings = _settings()
    client = _client(settings)

    # A day either side: Webull rejects single-day ranges, and a stop placed
    # yesterday that filled today has to fall inside the window.
    start = (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()
    end = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
    orders = client.order_history(start, end)
    legs = write_export(export_rows(orders))
    print("BROKER SYNC %s — %d order leg(s) -> %s"
          % (day, legs, os.path.basename(EXPORT)))

    snapshot = client.account_snapshot()

    futures = None
    fut_id = getattr(client, "futures_account_id", None)
    if fut_id and fut_id != getattr(client, "account_id", None):
        # THE ORDER-HISTORY DOOR IS 2 PER 2 SECONDS and the margin pull has
        # just used it (three pages on a 200-leg day). Asked straight after,
        # the futures pull is throttled and comes back EMPTY — which on 9/17
        # the journal printed as "no fills" on a day with 15 fills and -$132.62.
        # Wait the door out, and ask once more if it still says nothing.
        time.sleep(HISTORY_DOOR_S)
        fut_orders = client.order_history(start, end, account_id=fut_id)
        if not fut_orders:
            time.sleep(2 * HISTORY_DOOR_S)
            fut_orders = client.order_history(start, end, account_id=fut_id)
        kept = merge_futures(futures_rows(fut_orders))
        fut_day = futures_day(day) or {}
        fut_snap = client.account_snapshot(account_id=fut_id) or {}
        # No fills that day is a result of 0.00 — but ONLY when the balance
        # agrees. A futures balance that moved with no fills on file is an
        # unknown result (a missed pull, or money moved), never a 0.00.
        flat = not fut_day
        moved = None
        if flat and fut_snap.get("nlv") is not None:
            try:
                with open(BALANCES, encoding="utf-8", newline="") as fh:
                    before = _prior([(r + [""] * len(BALANCE_HEAD))[:len(BALANCE_HEAD)]
                                     for r in list(csv.reader(fh))[1:] if r],
                                    day, "fut_nlv")
            except OSError:
                before = None
            if before is not None and abs(fut_snap["nlv"] - before) >= 1.0:
                moved = fut_snap["nlv"] - before
                print("BROKER SYNC futures — NO FILLS ON FILE but the futures "
                      "balance moved %+.2f: result recorded as UNKNOWN, not 0.00 "
                      "(a throttled history pull, or money moved)" % moved)
        unknown = flat and moved is not None
        futures = {"nlv": fut_snap.get("nlv"),
                   "pl": None if unknown else 0.0 if flat else fut_day.get("net"),
                   "fees": None if unknown else 0.0 if flat else fut_day.get("fees")}
        print("BROKER SYNC futures — %d fill(s) that day, net %s, fees %s, "
              "nlv %s%s%s  (%d legs in %s)"
              % (fut_day.get("fills", 0),
                 "?" if futures["pl"] is None else "%.2f" % futures["pl"],
                 "?" if futures["fees"] is None else "%.2f" % futures["fees"],
                 "?" if futures["nlv"] is None else "%.2f" % futures["nlv"],
                 "  STILL OPEN: %s" % ",".join(fut_day["open"])
                 if fut_day.get("open") else "",
                 "  NO POINT VALUE: %s" % ",".join(fut_day["unpriced"])
                 if fut_day.get("unpriced") else "",
                 kept, os.path.basename(FUTURES)))

    row = record_balance(day, snapshot, futures=futures)
    if row:
        print("BROKER SYNC balance — nlv %s  day P&L %s  option BP %s  "
              "flow %s  futures flow %s"
              % (row[1] or "?", row[2] or "?", row[3] or "?",
                 row[8] or "?", row[9] or "?"))
    else:
        print("BROKER SYNC balance — Webull would not say; nothing recorded")

    import build_ledger
    rows, _broker = build_ledger.build()
    build_ledger.write(rows)
    print("BROKER SYNC ledger rebuilt — %d rows" % len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
