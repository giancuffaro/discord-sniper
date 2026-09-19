#!/usr/bin/env python3
"""single_name_lab.py — the callers' single-name alerts (TSLA, NVDA, MU, PLTR,
...) tested for DIRECTIONAL skill on the STOCK's 1-minute bars (bars/stock_m1,
Webull). The option is not simulated — no year of option bars exists — so the
question here is narrower and cleaner: after a caller says "in NVDA 220c",
does NVDA go up? Sized as 10 shares (a micro stock future), thresholds in % of
price. Honest simulator (edge_lab.sim), in-sample / out-of-sample split,
random-direction control, the caller's own first exit post as one exit.
MEASUREMENT ONLY."""
from __future__ import annotations

import csv
import datetime as dt
import os
import random
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
import edge_lab as L                                       # noqa: E402

ET = L.ET
INDEX = ("SPY", "QQQ", "SPX", "SPXW", "IWM", "DIA")
SHARES = 10.0
M1 = os.path.join(ROOT, "bars", "stock_m1")


def alerts():
    rows = {}
    for path, tcol in ((os.path.join(ROOT, "grab_alerts.csv"), "time"), (os.path.join(ROOT, "recovered_alerts_chat.csv"), "time")):
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if path.endswith("recovered_alerts_chat.csv") and r.get("msg_type") != "entry":
                    continue
                sym = (r.get("symbol") or "").upper()
                side = (r.get("side") or "").upper()
                if sym in INDEX or not side.startswith(("C", "P")) or (r.get("date") or "") < "2025-09-18":
                    continue
                t = (r.get(tcol) or "")[:5]
                try:
                    hh, mm = int(t[:2]), int(t[3:5])
                except ValueError:
                    continue
                if not (9 * 60 + 30 <= hh * 60 + mm <= 15 * 60 + 30):
                    continue
                key = (sym, r["date"], hh * 60 + mm, side[0])
                if key in rows:
                    continue
                caller = (r.get("caller") or r.get("room") or "?")
                if caller.startswith("HoneyDrip"):
                    import re
                    m = re.search(r"@(Unraveller|Mike|Brett)", r.get("text") or r.get("source_message_verbatim") or "", re.I)
                    caller = "HD " + (m.group(1).title() if m else "?")
                rows[key] = dict(sym=sym, day=r["date"], mins=hh * 60 + mm, s=1 if side[0] == "C" else -1,
                                 caller=caller[:16], ts=dt.datetime.strptime(r["date"], "%Y-%m-%d").replace(hour=hh, minute=mm, tzinfo=ET))
    return list(rows.values())


_B = {}


def day_bars(sym, day):
    k = (sym, day)
    if k not in _B:
        p = os.path.join(M1, "%s_%s.csv" % (sym, day))
        if not os.path.exists(p):
            _B[k] = None
        else:
            rows = []
            with open(p, encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    t = dt.datetime.fromtimestamp(float(r["ts"]), ET)
                    rows.append((t.hour * 60 + t.minute, float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"])))
            rows.sort()
            _B[k] = rows if len(rows) >= 100 else None
    return _B[k]


def after(a):
    b = day_bars(a["sym"], a["day"])
    if not b:
        return None, None
    idx = [i for i, r in enumerate(b) if r[0] > a["mins"] and r[0] <= 15 * 60 + 59]
    if not idx:
        return None, None
    i0 = idx[0]
    rows = [(r[2], r[3], r[4]) for r in b[i0:] if r[0] <= 15 * 60 + 59]
    return rows, b[i0][1]


def exits():
    ex = defaultdict(list)
    with open(os.path.join(ROOT, "grab_exits.csv"), encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            ex[(r["symbol"].upper(), r["date"])].append(int(r["time"][:2]) * 60 + int(r["time"][3:5]))
    for k in ex:
        ex[k].sort()
    return ex


def sim_pct(s, e, rows, stop_pct, arm_pct=None, rung_pct=None, tgt_pct=None, time_stop=None):
    """edge_lab.sim in percent-of-entry units; $ for SHARES shares."""
    L.SLIP_TICKS = 0
    ppt = SHARES
    slip = 0.0005 * e * ppt                # 5 bps a side against us, both sides
    v = L.sim(s, e, rows, ppt, stop=e * stop_pct / 100, arm=(e * arm_pct / 100) if arm_pct else None,
              rung=(e * rung_pct / 100) if rung_pct else None, tgt=(e * tgt_pct / 100) if tgt_pct else None, time_stop=time_stop)
    return v - 2 * slip


def run(al, label, exit=None, entry="instant", stop_pct=1.0, tgt_pct=1.0, **kw):
    kw = dict(kw, stop_pct=stop_pct, tgt_pct=tgt_pct)
    EX = exits() if exit == "caller" else None
    pairs, ctl = [], []
    rnd = random.Random(3)
    for a in al:
        rows, e = after(a)
        if rows is None:
            continue
        s = a["s"]
        if entry == "pb":                                   # wait for a 0.5% pullback, 30 min
            i, fill = L.fill_pullback_pts(rows, e, s, e * 0.005, 30)
            if i is None:
                continue
            rows, e = rows[i:], fill
        if exit == "caller":
            m = next((mm for mm in EX.get((a["sym"], a["day"]), []) if mm > a["mins"]), None)
            n = None
            if m is not None:
                b = day_bars(a["sym"], a["day"]); i0 = next(i for i, r in enumerate(b) if r[0] > a["mins"])
                n = next((k for k, r in enumerate(b[i0:]) if r[0] >= m), None)
            v = sim_pct(s, e, rows, time_stop=n, **kw)
            c = sim_pct(rnd.choice((1, -1)), e, rows, time_stop=n, **kw)
        else:
            v = sim_pct(s, e, rows, **kw)
            c = sim_pct(rnd.choice((1, -1)), e, rows, **kw)
        pairs.append((a, v)); ctl.append((a, c))
    print(L.line(label, pairs, ctl))
    return pairs


if __name__ == "__main__":
    al = alerts()
    have = [a for a in al if day_bars(a["sym"], a["day"])]
    print("single-name alerts %d, with stock bars %d, days %d, callers %s" % (len(al), len(have), len({a["day"] for a in have}),
          sorted(defaultdict(int, {a["caller"]: 1 for a in have}))[:12]))
    print("\nINSTANT at the alert, 10 shares, 5 bps slip each side")
    run(have, "1% stop, 1:1 target")
    run(have, "1% stop, 1:2 target", stop_pct=1.0, tgt_pct=2.0)
    run(have, "0.5% stop, 1:1", stop_pct=0.5, tgt_pct=0.5)
    run(have, "1% stop, trail BE .4 / rungs .2", stop_pct=1.0, arm_pct=0.4, rung_pct=0.2)
    run(have, "2% stop, hold to close", stop_pct=2.0)
    run(have, "1% stop, 30-min time stop", stop_pct=1.0, time_stop=30)
    run(have, "1% stop, 60-min time stop", stop_pct=1.0, time_stop=60)
    run(have, "1% stop, out at caller's first exit post (else close)", exit="caller", stop_pct=1.0)
    run(have, "2% stop, out at caller's first exit post", exit="caller", stop_pct=2.0)
    print("\nCALLS vs PUTS (1% stop, 1:1)")
    run([a for a in have if a["s"] > 0], "calls"); run([a for a in have if a["s"] < 0], "puts")
    print("\nBY CALLER (1% stop, 1:1), 20+ alerts")
    by = defaultdict(list)
    for a in have:
        by[a["caller"]].append(a)
    for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
        if len(v) >= 20:
            run(v, k)
    print("\nBY SYMBOL (1% stop, 1:1), 25+ alerts")
    by = defaultdict(list)
    for a in have:
        by[a["sym"]].append(a)
    for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
        if len(v) >= 25:
            run(v, k)
