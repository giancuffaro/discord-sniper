#!/usr/bin/env python3
"""trade_trend_label.py — the trend at the moment of EVERY trade in the ledger.

G, 9/17: "can you go and label all trades' trend status at the moment, in the
master ledger … where all our trades data is".

master_ledger.csv is REBUILT from broker truth every run, so the label does not
go inside it (it would be wiped); it goes BESIDE it, one row per ledger row:

    trade_trend.csv   date,opened,symbol,side,occ,manual,qty,pl,label,
                      with_trend,reversal,legs,bars,source

LABEL = trend.py's swing structure (higher highs + higher lows = UP, mirror =
DOWN, else CHOP; EARLY = under 15 minutes of tape) read off that day's
1-minute bars of the STOCK, using only bars that had CLOSED before the entry —
no lookahead. Bars: bars/stock 1-second files where we own them, else Webull's
own 1-minute history (market_data.get_history_bar by date — free), cached in
bars/stock_m1/ so a symbol-day is asked for once. Options only; futures rows
are skipped. MEASUREMENT ONLY.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import trend                                                # noqa: E402

LEDGER = os.path.join(HERE, "master_ledger.csv")
OUT = os.path.join(HERE, "trade_trend.csv")
M1_DIR = os.path.join(HERE, "bars", "stock_m1")
HEAD = ["date", "opened", "symbol", "side", "occ", "manual", "caller", "qty", "pl",
        "label", "with_trend", "reversal", "legs", "bars", "source"]
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                                           # noqa: BLE001
    ET = dt.timezone(dt.timedelta(hours=-4))

_CLIENT = []


def _client():
    if not _CLIENT:
        import broker_sync
        _CLIENT.append(broker_sync._client(broker_sync._settings()))
    return _CLIENT[0]


def day_bars(symbol, day, allow_fetch=True):
    """([(ts,o,h,l,c)] oldest first, source)."""
    one_s = os.path.join(HERE, "bars", "stock", "%s_%s_1s.csv" % (symbol, day))
    if os.path.exists(one_s):
        with open(one_s, encoding="utf-8-sig", newline="") as fh:
            ticks = [(float(r["ts"]), float(r["c"])) for r in csv.DictReader(fh)]
        if ticks:
            return trend.minute_bars(ticks, ticks[-1][0], minutes=24 * 60), "1s file"
    cached = os.path.join(M1_DIR, "%s_%s.csv" % (symbol, day))
    if os.path.exists(cached):
        with open(cached, encoding="utf-8", newline="") as fh:
            return [(float(r["ts"]), float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]))
                    for r in csv.DictReader(fh)], "webull m1"
    if not allow_fetch:
        return [], "none"
    d = dt.date.fromisoformat(day)
    start = dt.datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET)
    end = dt.datetime(d.year, d.month, d.day, 16, 0, tzinfo=ET)
    time.sleep(1.0)
    try:
        res = _client()._data.market_data.get_history_bar(
            symbol, "US_STOCK", "M1", "1200",
            start_time=int(start.timestamp() * 1000), end_time=int(end.timestamp() * 1000))
        body = res.json() if getattr(res, "status_code", 200) == 200 else []
    except Exception as e:                                  # noqa: BLE001
        print("  bars %s %s: %s" % (symbol, day, str(e)[:80]))
        body = []
    bars = []
    for row in (body if isinstance(body, list) else []):
        try:
            ts = dt.datetime.strptime(str(row["time"])[:19], "%Y-%m-%dT%H:%M:%S") \
                .replace(tzinfo=dt.timezone.utc).timestamp()
            bars.append((ts, float(row["open"]), float(row["high"]), float(row["low"]),
                         float(row["close"])))
        except (KeyError, ValueError, TypeError):
            continue
    bars.sort()
    os.makedirs(M1_DIR, exist_ok=True)
    with open(cached, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ts", "o", "h", "l", "c"])
        w.writerows(bars)          # an empty file is remembered too: asked once
    return bars, "webull m1"


def build(allow_fetch=True):
    with open(LEDGER, encoding="utf-8-sig", newline="") as fh:
        ledger = [r for r in csv.DictReader(fh) if r.get("kind") == "option"
                  and r.get("opened_ts") and r.get("symbol")]
    out = []
    for r in ledger:
        ts = float(r["opened_ts"])
        bars, source = day_bars(r["symbol"].upper(), r["date"], allow_fetch)
        before = [b for b in bars if b[0] + 60 <= ts][-trend.LOOKBACK_BARS:]
        got = trend.read(before)
        label = got["label"] if len(before) >= 15 else ("EARLY" if bars else "NO BARS")
        out.append([r["date"], r.get("opened") or "", r["symbol"].upper(), r.get("side") or "",
                    r.get("occ") or "", r.get("manual") or "", r.get("caller") or "",
                    r.get("qty") or "", r.get("pl") or "", label,
                    trend.with_or_counter(label, r.get("side")), got["reversal"],
                    got["legs"], len(before), source])
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEAD)
        w.writerows(out)
    os.replace(tmp, OUT)
    return out


def summary(rows):
    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    lines = ["TRADE TREND — %d option trades labelled (trend.py swing structure at the entry)" % len(rows)]
    for who, test in (("BOT", lambda r: str(r[5]).lower() not in ("true", "1")),
                      ("HAND (G)", lambda r: str(r[5]).lower() in ("true", "1"))):
        part = [r for r in rows if test(r) and num(r[8]) is not None]
        lines.append("\n%s — %d trades with a P&L, %+.0f" % (who, len(part), sum(num(r[8]) for r in part)))
        groups = defaultdict(list)
        for r in part:
            groups[r[10]].append(num(r[8]))
        for name in ("WITH", "COUNTER", "CHOP", "EARLY", "NO BARS"):
            pls = groups.get(name)
            if pls:
                wins = sum(1 for p in pls if p > 0)
                lines.append("  %-8s %4d trades  %+8.0f  %+7.1f/trade  win %2d%%"
                             % (name, len(pls), sum(pls), sum(pls) / len(pls), round(100 * wins / len(pls))))
        lines.append("  by the tape's own label (whatever he traded):")
        tape = defaultdict(list)
        for r in part:
            tape[(r[9], "CALLS" if str(r[3]).upper().startswith("C") else "PUTS")].append(num(r[8]))
        for key in sorted(tape):
            pls = tape[key]
            lines.append("    %-5s %-5s %4d trades  %+8.0f  %+7.1f/trade  win %2d%%"
                         % (key[0], key[1], len(pls), sum(pls), sum(pls) / len(pls),
                            round(100 * sum(1 for p in pls if p > 0) / len(pls))))
    return "\n".join(lines)


if __name__ == "__main__":
    data = build(allow_fetch="--no-fetch" not in sys.argv[1:])
    text = summary(data)
    with open(os.path.join(HERE, "reference", "TRADE-TREND.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)
