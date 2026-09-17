#!/usr/bin/env python3
"""fade_test.py — "what if we took the alerts and did exactly the opposite?"

G, 9/17. Two different questions hide in that sentence, and they have
different answers:

  A. WERE THE CALLERS WRONG ABOUT DIRECTION? Measured on the STOCK, which has
     no spread, no decay and a full history: for every option alert, the
     stock's move 5/15/30/60 minutes later and to the close, signed the way
     the caller bet (calls = up). Negative = fading the direction would have
     been right.

  B. WOULD BUYING THE OPPOSITE OPTION HAVE MADE MONEY? The opposite of a long
     call that lost is a SHORT call, not a long put. A long put pays the same
     spread and the same time decay the long call did, so both sides of a flat
     tape lose. Measured where we can: for alerts whose mirrored contract
     (same expiry, call<->put, strike mirrored around the stock) has Webull
     1-minute option bars in option_bars.csv, entry at the bar's close at the
     alert, same live stop/ladder logic on bar lows/highs is NOT possible
     without quotes — so this part reports the raw contract move at +15/+30/
     +60 min for BOTH the caller's contract and its mirror, side by side.

MEASUREMENT ONLY. Stock bars: trade_trend_label.day_bars (1s files, else
Webull's free 1-minute history, cached).
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import trade_trend_label as ttl                             # noqa: E402

ET = ttl.ET
HORIZONS = (5, 15, 30, 60)


def alerts():
    seen, out = set(), []
    with open(os.path.join(ROOT, "master_alerts.csv"), encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            side = (row.get("side") or "").upper()
            sym = (row.get("symbol") or "").upper()
            if side not in ("CALLS", "PUTS") or not sym.isalpha():
                continue
            clock = (row.get("time") or "")[:8]
            if len(clock) == 5:
                clock += ":00"
            try:
                ts = dt.datetime.fromisoformat("%sT%s" % (row["date"], clock)).replace(tzinfo=ET).timestamp()
            except ValueError:
                continue
            key = (row["date"], sym, side, int(ts // 300))
            if key in seen:
                continue
            seen.add(key)
            out.append({"day": row["date"], "ts": ts, "sym": sym, "side": side,
                        "caller": (row.get("caller") or row.get("room") or "?")[:24],
                        "hour": int(clock[:2]) + int(clock[3:5]) / 60.0})
    return out


def tstat(vals):
    if len(vals) < 3:
        return 0.0
    sd = statistics.pstdev(vals)
    return 0.0 if not sd else statistics.mean(vals) / (sd / math.sqrt(len(vals)))


def main():
    fetch = "--no-fetch" not in sys.argv[1:]
    rows, skipped = [], 0
    for a in alerts():
        bars, _src = ttl.day_bars(a["sym"], a["day"], fetch)
        rth = [b for b in bars if 570 <= (dt.datetime.fromtimestamp(b[0], ET).hour * 60
                                          + dt.datetime.fromtimestamp(b[0], ET).minute) < 960]
        at = [b for b in rth if b[0] + 60 <= a["ts"]]
        if not at or a["ts"] - at[-1][0] > 300:
            skipped += 1
            continue
        px = at[-1][4]
        sign = 1.0 if a["side"] == "CALLS" else -1.0
        rec = dict(a)
        for h in HORIZONS:
            fut = [b for b in rth if a["ts"] + h * 60 - 90 <= b[0] <= a["ts"] + h * 60 + 30]
            rec[h] = sign * (fut[-1][4] / px - 1) * 1e4 if fut else None
        rec["close"] = sign * (rth[-1][4] / px - 1) * 1e4
        rows.append(rec)

    days = sorted({r["day"] for r in rows})
    print("FADE TEST — %d option alerts with stock bars (%d had none), %s .. %s, %d days"
          % (len(rows), skipped, days[0], days[-1], len(days)))
    print("\nA. THE STOCK'S MOVE IN THE CALLER'S DIRECTION, basis points (negative = the fade was right)")

    def table(label, part):
        line = "  %-26s %4d" % (label, len(part))
        for h in HORIZONS + ("close",):
            vals = [r[h] for r in part if r.get(h) is not None]
            if not vals:
                line += "%16s" % "-"
                continue
            byday = defaultdict(list)
            for r in part:
                if r.get(h) is not None:
                    byday[r["day"]].append(r[h])
            t = tstat([statistics.mean(v) for v in byday.values()])
            line += "%16s" % ("%+.0fbp %2.0f%% t%+.1f" % (statistics.mean(vals),
                              100.0 * sum(1 for v in vals if v > 0) / len(vals), t))
        print(line)

    print("  %-26s %4s" % ("", "n") + "".join("%16s" % ("+%s min" % h if h != "close" else "to close")
                                               for h in HORIZONS + ("close",)))
    table("ALL ALERTS", rows)
    table("calls", [r for r in rows if r["side"] == "CALLS"])
    table("puts", [r for r in rows if r["side"] == "PUTS"])
    for lo, hi, name in ((9.5, 10, "09:30-10:00"), (10, 11, "10:00-11:00"), (11, 14, "11:00-14:00"), (14, 16, "14:00-16:00")):
        table(name, [r for r in rows if lo <= r["hour"] < hi])
    print("  (each cell: mean move for the caller, %% of alerts that went his way, t-stat by day; |t| under 2 = coin flip)")

    print("\n  BY CALLER (10+ alerts), +30 min")
    by = defaultdict(list)
    for r in rows:
        by[r["caller"]].append(r)
    for caller, part in sorted(by.items(), key=lambda kv: -len(kv[1])):
        vals = [r[30] for r in part if r.get(30) is not None]
        if len(vals) >= 10:
            print("    %-24s %3d  %+6.0fbp  right %2.0f%%" % (caller, len(vals), statistics.mean(vals),
                  100.0 * sum(1 for v in vals if v > 0) / len(vals)))


if __name__ == "__main__":
    main()
