#!/usr/bin/env python3
"""futures_bars_pull.py — ES / NQ 1-minute bars from Webull, free, into bars/.

The Databento equity/futures feed we bought ends 2026-09-12; the futures mirror
replay (futures_mirror_daily.py) needs bars for every day after that. Webull's
SDK serves them: futures_market_data.get_futures_history_bars(symbols,
category, timespan, count, start_time/end_time in epoch MILLISECONDS?) — this
file probes the signature once and writes what comes back in the SAME shape
the replay already reads (ts_event UTC, symbol, open, high, low, close,
volume), one file per contract-day: bars/<ROOT>_1m_<day>.csv. Read-only.
    python futures_bars_pull.py        (today's session; the daily audit runs it)
"""
import csv
import datetime as dt
import inspect
import os
import sys
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ET = ZoneInfo("America/New_York")
CONTRACTS = {"ES": "ESZ6", "NQ": "NQZ6"}


def main(first, last):
    """Webull's futures bars take no start/end — `count` back from NOW is all
    there is. 1,200 one-minute bars is one session (futures trade 23 hours),
    so this can only fill TODAY's file; run it every day after the close and
    the history accumulates. (Databento's GLBX feed, which filled 8/3-9/12,
    ends there.)"""
    sys.path.insert(0, HERE)
    import broker_sync
    client = broker_sync._client(broker_sync._settings())
    fn = client._data.futures_market_data.get_futures_history_bars
    for root, sym in CONTRACTS.items():
        try:
            res = fn(sym, "US_FUTURES", "M1", "1200")
            body = res.json() if getattr(res, "status_code", 200) == 200 else []
            rows = (body[0].get("result") if body and isinstance(body, list) else []) or []
        except Exception as ex:                                # noqa: BLE001
            print("ERROR %s: %s" % (root, str(ex)[:120]))
            continue
        by_day = {}
        for b in rows:
            t = dt.datetime.strptime(str(b["time"])[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
            local = t.astimezone(ET)
            if dt.time(9, 0) <= local.time() <= dt.time(16, 30):
                by_day.setdefault(local.date().isoformat(), []).append((t, b))
        for day, bars in sorted(by_day.items()):
            if len(bars) < 200:
                print("PARTIAL %s %s — %d bars, not written" % (root, day, len(bars)))
                continue
            out = os.path.join(HERE, "bars", "%s_1m_%s.csv" % (root, day))
            with open(out, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["ts_event", "symbol", "open", "high", "low", "close", "volume"])
                for t, b in sorted(bars, key=lambda x: x[0]):
                    w.writerow([t.isoformat(), "%s.c.0" % root, b["open"], b["high"], b["low"], b["close"], b["volume"]])
            print("WROTE %s (%d bars)" % (os.path.basename(out), len(bars)))


if __name__ == "__main__":
    main(None, None)
