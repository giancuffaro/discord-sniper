#!/usr/bin/env python3
"""caller_price_window_replay.py — the 9/17 caller-price rule, replayed over
EVERY alert we own quotes for, at several resting windows, split by trend.

G, 9/17: "make more seconds scenarios to see if we would fill with more time,
up to 5 mins maybe, and run this new rule for previous alerts to see what would
have happened and what we would have skipped — losers or winners." Then:
"can we pull more data to backtest more samples … lots of alerts are counter
trend trades … can you tell price went from this price to this price so it
was an uptrend?"

THE RULE (HANDOFF, PRICE): a round-number pullback that touches its level
crosses the ask ONLY when the ask is at or under the caller's price; over it,
the order rests AT the caller's price (tick-floored) for a working window and
dies unfilled. OLD = cross the ask whatever it is.

POPULATION. master_alerts.csv, every date, option OPENs on the round-number
symbols with a caller price. Quotes: tape.py, every bid/ask source (Databento
OPRA Aug–Sep 8, Webull, tastytrade shadow, alert tape). Underlying: bars/stock
1-second files; where none exists, the live watcher's own logged touch, then
the alert tape's `und` prints. An alert is SCORED only with a touch inside the
10-minute wait and an option quote within 20s of it. Everything else is
counted by reason. Nothing is interpolated.

A resting bid is scored filled only when the recorded ASK comes down to it
inside the window (conservative). Exits: ratchet_replay_tape.simulate(), LIVE
ladder, recorded bids, flat 15:59.

TREND (own stock, 1-second bars only): the stock's % move over the 30 minutes
before the alert. UP > +0.15%, DOWN < -0.15%, else FLAT. A call in UP or a put
in DOWN is WITH the trend; the reverse is COUNTER. Also reported against the
move since the 9:30 open. MEASUREMENT ONLY.
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import occ as occ_mod                                       # noqa: E402
import ratchet_replay_tape as rr                            # noqa: E402
import tape                                                 # noqa: E402
import trend as trend_mod                                   # noqa: E402
from webull_options import tick_floor                       # noqa: E402

WINDOWS = (90, 120, 180, 300)
TREND_LOOKBACK_S = 1800
TREND_BAND_PCT = 0.15
QUOTE_NEAR_S = 20.0
ET = rr.ET


def alerts():
    seen, out = set(), []
    with open(os.path.join(ROOT, "master_alerts.csv"), encoding="utf-8-sig",
              newline="") as fh:
        for row in csv.DictReader(fh):
            side = (row.get("side") or "").upper()
            theirs = rr._f(row.get("their_price"))
            if side not in ("CALLS", "PUTS") or not theirs or theirs <= 0:
                continue
            sym = (row.get("symbol") or "").upper()
            if sym not in rr.MANAGED:
                continue
            try:
                contract = occ_mod.build(sym, row.get("expiry"), side,
                                         rr._f(row.get("strike")))
            except (ValueError, TypeError):
                continue
            clock = (row.get("time") or "")[:8]
            if len(clock) == 5:
                clock += ":00"
            try:
                ts = dt.datetime.fromisoformat("%sT%s" % (row["date"], clock)
                                               ).replace(tzinfo=ET).timestamp()
            except ValueError:
                continue
            key = (row["date"], contract, int(ts // 120))
            if key in seen:
                continue
            seen.add(key)
            out.append({"day": row["date"], "time": clock, "ts": ts, "occ": contract,
                        "root": sym, "side": side, "their_price": theirs,
                        "caller": row.get("caller") or row.get("room") or "",
                        "und_at_alert": None})
    return sorted(out, key=lambda a: a["ts"])


def option_paths(wanted):
    grouped = defaultdict(dict)
    for r in tape.rows(occs=wanted, sources=("webull", "tasty_quote", "databento",
                                             "missed", "alert")):
        if not r.bid or not r.ask or r.bid <= 0 or r.ask < r.bid:
            continue
        grouped[(rr._day_of(r.ts), r.occ)].setdefault(int(r.ts), (r.ts, r.bid, r.ask))
    return {k: [v[s] for s in sorted(v)] for k, v in grouped.items()}


_STOCK = {}


def stock_path(root, day):
    key = (root, day)
    if key not in _STOCK:
        rows = []
        try:
            with open(os.path.join(ROOT, "bars", "stock", "%s_%s_1s.csv" % (root, day)),
                      encoding="utf-8-sig", newline="") as fh:
                for r in csv.DictReader(fh):
                    ts, c = rr._f(r.get("ts")), rr._f(r.get("c"))
                    if ts and c:
                        rows.append((ts, c))
        except OSError:
            pass
        _STOCK[key] = rows
    return _STOCK[key]


def logged_touches():
    found = []
    pat = re.compile(r"^(\S+)\tPULLBACK (\w+): touched \$")
    try:
        fh = open(os.path.join(ROOT, "trades.log"), encoding="utf-8", errors="replace")
    except OSError:
        return found
    with fh:
        for line in fh:
            m = pat.match(line)
            if m:
                try:
                    found.append((dt.datetime.fromisoformat(m.group(1)).timestamp(), m.group(2)))
                except ValueError:
                    pass
    return found


def price_at(path, ts):
    if not path:
        return None
    i = bisect.bisect_right([p[0] for p in path], ts) - 1
    return path[i][1] if i >= 0 and ts - path[i][0] <= 120 else None


def trend(root, day, ts, side):
    path = stock_path(root, day)
    now, then = price_at(path, ts), price_at(path, ts - TREND_LOOKBACK_S)
    if not now or not then:
        return None, None, None
    move = (now / then - 1) * 100.0
    label = "UP" if move > TREND_BAND_PCT else "DOWN" if move < -TREND_BAND_PCT else "FLAT"
    is_call = side.startswith("C")
    with_trend = ("FLAT" if label == "FLAT" else
                  "WITH" if (label == "UP") == is_call else "COUNTER")
    open_px = path[0][1]
    day_move = (now / open_px - 1) * 100.0
    return with_trend, move, day_move


def structure(root, day, ts, side):
    """trend.py's swing read (higher highs + higher lows) at the alert."""
    path = stock_path(root, day)
    if not path:
        return None, None
    bars = trend_mod.minute_bars(path, ts)
    if len(bars) < 20:
        return None, None
    got = trend_mod.read(bars)
    return trend_mod.with_or_counter(got["label"], side), got["label"]


def run():
    al = alerts()
    paths = option_paths({a["occ"] for a in al})
    touches = logged_touches()
    und_tape = None
    out, why = [], defaultdict(int)
    for a in al:
        path = paths.get((a["day"], a["occ"]))
        if not path:
            why["no recorded option quotes"] += 1
            continue
        real = [t for t, root in touches
                if root == a["root"] and a["ts"] - 5 <= t <= a["ts"] + rr.PULLBACK_WINDOW_S + 30]
        t_touch = real[0] if real else None
        if t_touch is None:
            stock = stock_path(a["root"], a["day"])
            if stock:
                basis, t_touch, _ = rr.pullback_entry(a, stock, [(t, 0, 0) for t, _p in stock])
            else:
                if und_tape is None:
                    rr.DAYS = tuple(sorted({x["day"] for x in al}))
                    und_tape = rr.load_underlying()
                basis, t_touch, _ = rr.pullback_entry(
                    a, und_tape.get((a["day"], a["root"]), []),
                    [(t, 0, 0) for t, _p in und_tape.get((a["day"], a["root"]), [])])
            if t_touch is None:
                why["never touched" if basis.startswith("never") else
                    "no underlying data" if "no underlying" in basis else basis[:40]] += 1
                continue
        after = [r for r in path if r[0] >= t_touch - 2]
        if not after or after[0][0] - t_touch > QUOTE_NEAR_S:
            why["no option quote within 20s of the touch"] += 1
            continue
        t0, ask0 = after[0][0], after[0][2]
        theirs = a["their_price"]
        if theirs > 2.5 * ask0 or theirs < 0.4 * ask0:
            why["caller price is not this contract's price"] += 1
            continue
        flat = rr._flat_ts(a["day"])
        limit = float(tick_floor(round(theirs, 2), a["root"]))

        def result(ts, entry):
            walk = [r for r in path if r[0] >= ts]
            if not walk:
                return None
            return round(rr.simulate(walk, entry, a["root"], rr.TIERS_LIVE, False,
                                     False, flat)["pl"], 2)

        tr, move30, moveday = trend(a["root"], a["day"], a["ts"], a["side"])
        st, st_label = structure(a["root"], a["day"], a["ts"], a["side"])
        row = {"a": a, "ask": ask0, "bid": after[0][1], "t0": t0, "path": path,
               "flat": flat, "struct": st, "struct_label": st_label, "over": (ask0 / theirs - 1) * 100.0,
               "old": result(t0, ask0) or 0.0, "new": {}, "trend": tr,
               "move30": move30, "moveday": moveday, "logged": bool(real)}
        for w in WINDOWS:
            if ask0 <= theirs + 1e-9:
                row["new"][w] = ("cross", row["old"])
                continue
            hit = next((r for r in path if t0 <= r[0] <= t0 + w and r[2] <= limit + 1e-9), None)
            row["new"][w] = ("rest", result(hit[0], limit) or 0.0) if hit else ("nofill", None)
        out.append(row)
    return out, why, len(al)


def _line(label, rows, key=lambda r: r["old"]):
    n = len(rows)
    if not n:
        return "  %-34s  none" % label
    pls = [key(r) for r in rows]
    wins = sum(1 for p in pls if p > 0)
    return "  %-34s %3d trades  %+7.0f  (%+.1f/trade, %d%% win)" % (
        label, n, sum(pls), sum(pls) / n, round(100.0 * wins / n))


def main():
    rows, why, n_alerts = run()
    days = sorted({r["a"]["day"] for r in rows})
    print("CALLER-PRICE RULE + TREND REPLAY — %d priced round-number alerts, %d scored, "
          "%s .. %s (%d days)" % (n_alerts, len(rows), days[0], days[-1], len(days)))
    over = [r for r in rows if r["over"] > 0]
    print("\nAT THE TOUCH: ask at/under the caller's price on %d of %d (rule changes nothing); "
          "over it on %d (median %+.0f%%)" % (len(rows) - len(over), len(rows), len(over),
          sorted(r["over"] for r in over)[len(over) // 2] if over else 0))
    print("\nTHE RULE")
    print(_line("OLD — always cross the ask", rows))
    old = sum(r["old"] for r in rows)
    for w in WINDOWS:
        took = [r for r in rows if r["new"][w][0] != "nofill"]
        skip = [r for r in rows if r["new"][w][0] == "nofill"]
        net = sum(r["new"][w][1] for r in took)
        sw = [r for r in skip if r["old"] > 0]
        sl = [r for r in skip if r["old"] <= 0]
        rest = [r for r in took if r["new"][w][0] == "rest"]
        print("  NEW %3ds  %3d trades  %+7.0f  vs OLD %+6.0f | rested+filled %d worth %+.0f | "
              "skipped %d: %d winners %+.0f, %d losers %+.0f"
              % (w, len(took), net, net - old, len(rest), sum(r["new"][w][1] for r in rest),
                 len(skip), len(sw), sum(r["old"] for r in sw), len(sl), sum(r["old"] for r in sl)))
    hard = [r for r in rows if r["over"] <= 0]
    print(_line("HARD SKIP when ask > caller", hard))

    print("\nTREND — the stock's own move in the 30 min before the alert (OLD-rule P&L)")
    lab = [r for r in rows if r["trend"]]
    for name in ("WITH", "COUNTER", "FLAT"):
        print(_line("%s trend" % name, [r for r in lab if r["trend"] == name]))
    print("  (no 1-second stock file for the other %d)" % (len(rows) - len(lab)))
    print("\nTREND — SWING STRUCTURE at the alert (trend.py: higher highs + higher lows = UP)")
    sl = [r for r in rows if r["struct"]]
    for name in ("WITH", "COUNTER", "CHOP"):
        print(_line("%s structure" % name, [r for r in sl if r["struct"] == name]))
    print("\nTREND — against the move since the 9:30 open")
    for name, test in (("WITH the day", lambda r: (r["moveday"] > 0) == r["a"]["side"].startswith("C")),
                       ("AGAINST the day", lambda r: (r["moveday"] > 0) != r["a"]["side"].startswith("C"))):
        print(_line(name, [r for r in lab if abs(r["moveday"]) > TREND_BAND_PCT and test(r)]))

    print("\nBY CALLER (OLD rule, 4+ trades)")
    by = defaultdict(list)
    for r in lab:
        by[r["a"]["caller"][:22]].append(r)
    for c, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        if len(rs) >= 4:
            cn = [r for r in rs if r["trend"] == "COUNTER"]
            print("  %-22s %3d trades %+6.0f | counter-trend %d of them, worth %+.0f"
                  % (c, len(rs), sum(r["old"] for r in rs), len(cn), sum(r["old"] for r in cn)))

    print("\nNOT SCORED")
    for reason, n in sorted(why.items(), key=lambda kv: -kv[1]):
        print("  %3d  %s" % (n, reason))
    with open(os.path.join(HERE, "CALLER-PRICE-WINDOW-REPLAY.csv"), "w",
              encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["date", "time", "caller", "occ", "caller_price", "ask_at_touch",
                     "over_pct", "old_pl"] + ["new_%ds" % w for w in WINDOWS]
                    + ["structure", "trend30", "move30_pct", "move_since_open_pct", "touch_from_log"])
        for r in rows:
            a = r["a"]
            wr.writerow([a["day"], a["time"], a["caller"], a["occ"], a["their_price"], r["ask"],
                         "%.1f" % r["over"], r["old"]]
                        + ["" if r["new"][w][0] == "nofill" else r["new"][w][1] for w in WINDOWS]
                        + [r["struct"] or "", r["trend"] or "", "" if r["move30"] is None else "%.2f" % r["move30"],
                           "" if r["moveday"] is None else "%.2f" % r["moveday"], int(r["logged"])])


if __name__ == "__main__":
    main()
