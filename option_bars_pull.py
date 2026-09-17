#!/usr/bin/env python3
"""option_bars_pull.py — Webull's own 1-minute OPTION bars, for every contract
a room ever alerted or the account ever held. Free, read-only.

G, 9/17: "get as much options history bars from webull plz".

Found 9/17: the SDK's option_market_data.get_option_history_bars(occ,
"US_OPTION", timespan, count) answers — expired contracts included — with up
to 1,200 bars counted BACK FROM THE CONTRACT'S LAST PRINT. There is no start
date, so depth is bought with the timespan:
    M1  x 1200 = the last ~3 sessions of the contract's life
    M5  x 1200 = the last ~15 sessions
Both are pulled. They are TRADE bars (open/high/low/close/volume): no bid, no
ask. Stops watch the bid, so the quote tapes stay the truth for fills and
exits; these answer "did it ever print X, and when".

WHAT: every option contract in master_alerts.csv and master_ledger.csv.
WHERE: option_bars.csv — ts,occ,span,open,high,low,close,volume — ONE file,
one row per (occ, span, ts); a re-run adds only bars it does not have.
WEBULL FORGETS. A contract that expired more than about a week ago answers
417 INVALID_SYMBOL (9/17: everything expiring 9/9 and earlier was gone, 9/14
still answered). So this is a DAILY job, not a one-time backfill: the 16:40
audit runs it with `--recent 6`, which asks only for contracts alerted or
traded in the last 6 days and adds the bars it does not have. A day missed is
a day of history lost for good.

PACING: one request per second, never while the option market is open unless
--now is passed (the bridge's stops share this app key).
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "option_bars.csv")
HEAD = ["ts", "occ", "span", "open", "high", "low", "close", "volume"]
SPANS = ("M1", "M5")
PACE_S = 1.0


def contracts(recent_days=None):
    import occ
    found = {}
    for name in ("master_alerts.csv", "master_ledger.csv"):
        try:
            fh = open(os.path.join(HERE, name), encoding="utf-8-sig", newline="")
        except OSError:
            continue
        with fh:
            for row in csv.DictReader(fh):
                symbol = row.get("occ") or ""
                if not occ.is_occ(symbol):
                    try:
                        symbol = occ.build(row.get("symbol"), row.get("expiry"),
                                           row.get("side"), row.get("strike"))
                    except (ValueError, TypeError):
                        continue
                day = (row.get("date") or "")[:10]
                found[symbol] = max(found.get(symbol, ""), day)
    # newest first: the contracts Webull is most likely to still serve
    ranked = sorted(found.items(), key=lambda kv: kv[1], reverse=True)
    if recent_days:
        floor = (dt.date.today() - dt.timedelta(days=recent_days)).isoformat()
        ranked = [kv for kv in ranked if kv[1] >= floor]
    return [c for c, _d in ranked]


def have():
    seen = set()
    try:
        with open(OUT, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                seen.add((row["occ"], row["span"], row["ts"]))
    except OSError:
        pass
    return seen


def _market_open():
    try:
        from market_hours import is_open
        return bool(is_open("option"))
    except Exception:                                       # noqa: BLE001
        return False


def main(force_now):
    if not force_now:
        try:
            from market_hours import is_open
            if is_open("option"):
                print("the option market is open — not competing with the stops. "
                      "Run after the close, or pass --now.")
                return 1
        except Exception:                                   # noqa: BLE001
            pass
    import broker_sync
    client = broker_sync._client(broker_sync._settings())
    fetch = client._data.option_market_data.get_option_history_bars
    recent = None
    if "--recent" in sys.argv:
        try:
            recent = int(sys.argv[sys.argv.index("--recent") + 1])
        except (IndexError, ValueError):
            recent = 6
    todo, seen = contracts(recent), have()
    # A daily run REFRESHES recent contracts (today's bars are new); the big
    # backfill skips any contract-span it already holds.
    done_pairs = set() if recent else {(o, s) for o, s, _t in seen}
    fresh = not os.path.exists(OUT)
    got = empty = errors = added = 0
    with open(OUT, "a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if fresh:
            writer.writerow(HEAD)
        for i, contract in enumerate(todo, 1):
            for span in SPANS:
                if (contract, span) in done_pairs and "--refresh" not in sys.argv:
                    continue
                time.sleep(PACE_S)
                if not force_now and _market_open():
                    print("the option market opened — stopping at %d/%d; run again "
                          "after the close, it resumes where it stopped" % (i, len(todo)))
                    return 0
                try:
                    res = fetch(contract, "US_OPTION", span, "1200")
                    if getattr(res, "status_code", 200) == 429:
                        print("throttled — sleeping 30s")
                        time.sleep(30)
                        res = fetch(contract, "US_OPTION", span, "1200")
                    body = res.json() if getattr(res, "status_code", 200) == 200 else []
                except Exception as e:                      # noqa: BLE001
                    errors += 1
                    print("[%d/%d] ERROR %s %s: %s" % (i, len(todo), contract, span, str(e)[:80]))
                    continue
                rows = (body[0].get("result") if body and isinstance(body, list)
                        and isinstance(body[0], dict) else None) or []
                if not rows:
                    empty += 1
                    continue
                n = 0
                for bar in rows:
                    try:
                        ts = dt.datetime.strptime(str(bar["time"])[:19], "%Y-%m-%dT%H:%M:%S") \
                            .replace(tzinfo=dt.timezone.utc).timestamp()
                    except (KeyError, ValueError):
                        continue
                    key = (contract, span, "%d" % ts)
                    if key in seen:
                        continue
                    seen.add(key)
                    writer.writerow(["%d" % ts, contract, span, bar.get("open"), bar.get("high"),
                                     bar.get("low"), bar.get("close"), bar.get("volume")])
                    n += 1
                fh.flush()
                got += 1
                added += n
            if i % 25 == 0:
                print("[%d/%d] %d answered, %d empty, %d errors, %d bars" % (i, len(todo), got, empty, errors, added))
    print("DONE %d contracts: %d answered, %d empty, %d errors, %d new bars -> option_bars.csv"
          % (len(todo), got, empty, errors, added))
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--now" in sys.argv[1:]))
