#!/usr/bin/env python3
"""alert_quote_pull.py — OPRA quotes + 1-second stock bars for the alerts the
caller-price / trend replay could NOT score, so the sample stops being 39.

G, 9/17: "can we pull more data to backtest more samples please".

    python reference/alert_quote_pull.py            ESTIMATE ONLY — asks
                                                    Databento what it WOULD
                                                    cost (free), spends nothing
    python reference/alert_quote_pull.py --pull     spends the credit and pulls

SPENDING IS G'S CALL (HANDOFF: databento spends credit — never casually). The
default run cannot spend a cent: metadata.get_cost is a free call.

WHAT: every priced option OPEN in master_alerts.csv on a round-number symbol
whose contract has no recorded quote on its day. Window: 60s before the alert
to +45 minutes (the pullback wait, the entry, and the great majority of ratchet
exits) — NOT to the close, which is what makes a liquid 0DTE expensive. Quotes
are appended to databento_tape.csv (the ONE OPRA file, tape.py reads it),
downsampled to ~1/sec by databento_backfill.downsample. Stock: XNAS.ITCH
ohlcv-1s for each (symbol, day) with no bars/stock file, 09:30–16:00.
State: reference/alert_quote_pull_state.json — a pair asked once is never
billed twice, empty or not.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import caller_price_window_replay as replay                 # noqa: E402
import databento_backfill as bf                             # noqa: E402
import occ as occ_mod                                       # noqa: E402

STATE = os.path.join(HERE, "alert_quote_pull_state.json")
TAPE = os.path.join(ROOT, "databento_tape.csv")
AFTER_S = 45 * 60


def _state():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return set(tuple(x) for x in json.load(fh))
    except (OSError, ValueError):
        return set()


def _save(state):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(sorted(state), fh)
    os.replace(tmp, STATE)


def targets():
    al = replay.alerts()
    have = replay.option_paths({a["occ"] for a in al})
    done = _state()
    opts, stocks = {}, set()
    for a in al:
        if not replay.stock_path(a["root"], a["day"]) and ("stock", a["root"], a["day"]) not in done:
            stocks.add((a["root"], a["day"]))
        if (a["day"], a["occ"]) in have or ("opt", a["occ"], a["day"]) in done:
            continue
        parsed = occ_mod.parse(a["occ"])
        if not parsed:
            continue
        raw = occ_mod.to_tasty(parsed[0], parsed[1], parsed[2], parsed[3])
        key = (a["occ"], a["day"])
        t = opts.setdefault(key, {"occ": a["occ"], "raw": raw, "day": a["day"],
                                  "start": a["ts"] - 60, "end": a["ts"] + AFTER_S})
        t["start"], t["end"] = min(t["start"], a["ts"] - 60), max(t["end"], a["ts"] + AFTER_S)
    return list(opts.values()), sorted(stocks)


def main(pull):
    import datetime as dt
    import databento as db
    client = db.Historical(bf.load_key())
    opts, stocks = targets()
    print("option windows to price: %d   stock days to fetch: %d" % (len(opts), len(stocks)))
    total, state = 0.0, _state()
    by_day = defaultdict(list)
    for root, day in stocks:
        by_day[day].append(root)

    fh = wr = None
    if pull:
        fh = open(TAPE, "a", newline="", encoding="utf-8")
        wr = csv.writer(fh)
    for i, t in enumerate(opts, 1):
        args = dict(dataset="OPRA.PILLAR", schema="cmbp-1", stype_in="raw_symbol",
                    symbols=[t["raw"]], start=bf.iso(t["start"]), end=bf.iso(t["end"]))
        try:
            if not pull:
                total += float(client.metadata.get_cost(**args))
                continue
            rows = bf.downsample(client.timeseries.get_range(**args).to_df(),
                                 t["start"], t["end"])
        except Exception as e:                              # noqa: BLE001
            print("[%d/%d] ERROR %s %s: %s" % (i, len(opts), t["occ"], t["day"], str(e)[:90]))
            continue
        for ts, bid, ask in rows:
            wr.writerow(["%.3f" % ts, t["occ"], bid, ask])
        fh.flush()
        state.add(("opt", t["occ"], t["day"]))
        _save(state)
        print("[%d/%d] %-22s %s  %d rows" % (i, len(opts), t["occ"], t["day"], len(rows)))
    if fh:
        fh.close()
    print("OPTIONS %s: $%.2f" % ("cost estimate" if not pull else "done", total))

    stock_total = 0.0
    for day, roots in sorted(by_day.items()):
        d = dt.date.fromisoformat(day)
        s = dt.datetime(d.year, d.month, d.day, 9, 30, tzinfo=replay.ET)
        e = dt.datetime(d.year, d.month, d.day, 16, 0, tzinfo=replay.ET)
        args = dict(dataset="XNAS.ITCH", symbols=roots, schema="ohlcv-1s",
                    start=s.isoformat(), end=e.isoformat())
        try:
            if not pull:
                stock_total += float(client.metadata.get_cost(**args))
                continue
            df = client.timeseries.get_range(**args).to_df()
        except Exception as ex:                             # noqa: BLE001
            print("STOCK %s ERROR: %s" % (day, str(ex)[:90]))
            continue
        for root in roots:
            part = df[df["symbol"] == root] if "symbol" in df.columns else df
            path = os.path.join(ROOT, "bars", "stock", "%s_%s_1s.csv" % (root, day))
            if len(part):
                with open(path, "w", newline="", encoding="utf-8") as out:
                    w = csv.writer(out)
                    w.writerow(["ts", "o", "h", "l", "c"])
                    for ts, o, h, l, c in zip(part.index, part["open"], part["high"],
                                              part["low"], part["close"]):
                        w.writerow([int(ts.timestamp()), "%.4f" % o, "%.4f" % h,
                                    "%.4f" % l, "%.4f" % c])
            state.add(("stock", root, day))
        _save(state)
        print("STOCK %s  %s" % (day, ",".join(roots)))
    print("STOCK %s: $%.2f" % ("cost estimate" if not pull else "done", stock_total))
    if not pull:
        print("\nTOTAL ESTIMATE: $%.2f — nothing was spent. Re-run with --pull to buy it."
              % (total + stock_total))


if __name__ == "__main__":
    main("--pull" in sys.argv[1:])
