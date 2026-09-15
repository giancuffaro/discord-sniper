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
  3 build_ledger, which absorbs the export into master_broker.csv and
    reconciles it against master_ledger.csv to the cent

NOT A SECOND CLIENT AND NOT A POLL LOOP. It builds ONE WebullOptions the way
health.py already does, uses it for two reads, and exits. It runs once a day,
after the close, when the bridge's quote bus is idle — two hits against the
2-per-2s door, not a loop competing with the stops. It never places, cancels
or modifies an order, and never touches settings.json.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.path.join(HERE, "Webull_Orders_auto.csv")
BALANCES = os.path.join(HERE, "balance_daily.csv")

EXPORT_HEAD = ["Name OCC", "Symbol", "Side", "Status", "Filled", "Total Qty",
               "Price", "Avg Price", "Time-in-Force", "Placed Time",
               "Filled Time"]
BALANCE_HEAD = ["date", "nlv", "day_pl", "bp", "read_at"]


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
    legs = order.get("legs") or []
    leg = legs[0] if legs else {}
    symbol = str(leg.get("symbol") or order.get("symbol") or "").upper()
    expiry = str(leg.get("option_expire_date")
                 or order.get("option_expire_date") or "")[:10]
    if not symbol or len(expiry) != 10:
        return ""
    kind = "C" if str(leg.get("option_type")
                      or order.get("option_type") or "").upper() \
        .startswith("C") else "P"
    try:
        strike = int(round(float(leg.get("strike_price")
                                 or leg.get("option_exercise_price")) * 1000))
    except (TypeError, ValueError):
        return ""
    return "%s%s%s%08d" % (symbol, expiry[2:4] + expiry[5:7] + expiry[8:10],
                           kind, strike)


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


def record_balance(day, snapshot, path=None):
    """Append one row per trading day. Append-only, and a re-run replaces that
    day's row rather than stacking a second one — one day, one balance."""
    path = path or BALANCES
    if not snapshot:
        return None
    existing, seen = [], False
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            existing = [r for r in csv.reader(fh)][1:]
    except OSError:
        pass
    row = [day,
           "" if snapshot.get("nlv") is None else "%.2f" % snapshot["nlv"],
           "" if snapshot.get("day_pl") is None else "%.2f" % snapshot["day_pl"],
           "" if snapshot.get("bp") is None else "%.2f" % snapshot["bp"],
           dt.datetime.now().astimezone().isoformat(timespec="seconds")]
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
        except ValueError:
            return None
    return {"date": row.get("date") or "", "nlv": num("nlv"),
            "day_pl": num("day_pl"), "bp": num("bp"),
            "read_at": row.get("read_at") or ""}


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
    row = record_balance(day, snapshot)
    if row:
        print("BROKER SYNC balance — nlv %s  day P&L %s  option BP %s"
              % (row[1] or "?", row[2] or "?", row[3] or "?"))
    else:
        print("BROKER SYNC balance — Webull would not say; nothing recorded")

    import build_ledger
    rows, _broker = build_ledger.build()
    build_ledger.write(rows)
    print("BROKER SYNC ledger rebuilt — %d rows" % len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
