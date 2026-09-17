#!/usr/bin/env python3
"""caller_price_window_replay.py — the 9/17 rule, replayed, at several windows.

G, 9/17: "make more seconds scenarios to see if we would fill with more time,
up to 5 mins maybe, and run this new rule for previous alerts to see what would
have happened and what we would have skipped — losers or winners."

THE RULE (HANDOFF, PRICE): a round-number pullback that touches its level
crosses the ask ONLY when the ask is at or under the caller's price; over it,
the order rests AT the caller's price (tick-floored) for a working window and
dies unfilled. OLD = cross the ask whatever it is.

WHAT A FILL MEANS HERE. A resting bid is scored as filled only when the
recorded ASK comes down to it inside the window — the conservative reading; a
real bid can also be hit between quotes, so true fills are >= these. Exits are
reference/ratchet_replay_tape.simulate() under the LIVE ladder on the recorded
bid path, flat at 15:59. Only alerts with a caller price, a recorded option
path and (for round-number symbols) a touch inside the 10-minute wait are
scored; everything else is listed as unscored with the reason. Nothing is
interpolated. MEASUREMENT ONLY — places no order, changes no setting.
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import occ as occ_mod                                       # noqa: E402
import ratchet_replay_tape as rr                            # noqa: E402
from webull_options import tick_floor                       # noqa: E402

WINDOWS = (90, 120, 180, 300)


def all_days():
    days = set()
    with open(os.path.join(ROOT, "alert_meta.csv"), encoding="utf-8-sig",
              newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("stage") == "alert" and row.get("date"):
                days.add(row["date"])
    return tuple(sorted(days))


def add_shadow(paths):
    """Fold quote_shadow.csv (dxFeed symbols) into the Webull paths — denser."""
    grouped = defaultdict(dict)
    try:
        fh = open(os.path.join(ROOT, "quote_shadow.csv"), encoding="utf-8-sig",
                  newline="")
    except OSError:
        return paths
    with fh:
        for row in csv.DictReader(fh):
            ts, bid, ask = rr._f(row.get("ts")), rr._f(row.get("bid")), rr._f(row.get("ask"))
            if ts is None or not bid or not ask or ask < bid:
                continue
            day = rr._day_of(ts)
            if day not in rr.DAYS:
                continue
            try:
                contract = occ_mod.from_dx((row.get("symbol") or "").strip())
            except Exception:                               # noqa: BLE001
                continue
            grouped[(day, contract)].setdefault(int(ts), (ts, bid, ask))
    for key, rows in grouped.items():
        merged = {int(r[0]): r for r in paths.get(key, [])}
        for sec, r in rows.items():
            merged.setdefault(sec, r)
        paths[key] = [merged[s] for s in sorted(merged)]
    return paths


def logged_touches():
    """[(ts, root)] — every touch the LIVE watcher actually logged. The real
    thing beats the replayed one: the recorded underlying is one print per
    sweep and on 9/16 had no AAPL print before 9:45, so the replay found
    Brett's touch four minutes late at a 2.73 ask when the bot really touched
    at 9:41:10 into a 3.45 ask."""
    import datetime as dt
    import re
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


def run():
    rr.DAYS = all_days()
    touches = logged_touches()
    paths = add_shadow(rr.load_paths())
    unders = rr.load_underlying()
    out, unscored = [], []
    for a in rr.load_alerts():
        tag = "%s %s %s %s" % (a["day"], a["time"][:5], a["caller"] or a["room"], a["occ"])
        theirs = a.get("their_price")
        path = paths.get((a["day"], a["occ"]))
        if not theirs or theirs <= 0:
            unscored.append((tag, "no caller price")); continue
        if not path:
            unscored.append((tag, "no recorded quotes")); continue
        if a["root"] not in rr.MANAGED:
            unscored.append((tag, "instant-entry symbol — rule unchanged")); continue
        real = [t for t, root in touches
                if root == a["root"] and a["ts"] - 5 <= t <= a["ts"] + rr.PULLBACK_WINDOW_S + 30]
        if real:
            after = [r for r in path if r[0] >= real[0] - 2]
            basis, t0, ask0 = ("logged touch", after[0][0], after[0][2]) if after else ("logged touch, no quote", None, None)
        else:
            basis, t0, ask0 = rr.pullback_entry(a, unders.get((a["day"], a["root"]), []), path)
        if t0 is None:
            unscored.append((tag, basis)); continue
        if theirs > 2.5 * ask0 or theirs < 0.4 * ask0:
            unscored.append((tag, "caller price %.2f vs ask %.2f — not this contract" % (theirs, ask0))); continue
        flat = rr._flat_ts(a["day"])
        limit = float(tick_floor(round(theirs, 2), a["root"]))

        def result(ts, entry):
            walk = [r for r in path if r[0] >= ts]
            if not walk:
                return None
            sim = rr.simulate(walk, entry, a["root"], rr.TIERS_LIVE, False, False, flat)
            return round(sim["pl"], 2)

        row = {"tag": ("*" if real else " ") + tag, "theirs": theirs, "ask": ask0,
               "over": (ask0 / theirs - 1) * 100.0, "old": result(t0, ask0), "new": {}}
        for w in WINDOWS:
            if ask0 <= theirs + 1e-9:
                row["new"][w] = ("cross", row["old"], 0)
                continue
            hit = next((r for r in path if t0 <= r[0] <= t0 + w and r[2] <= limit + 1e-9), None)
            row["new"][w] = ("rest", result(hit[0], limit), hit[0] - t0) if hit else ("nofill", None, None)
        out.append(row)
    return out, unscored


def main():
    rows, unscored = run()
    print("CALLER-PRICE RULE REPLAY — days %s..%s — %d scored, %d unscored"
          % (rr.DAYS[0], rr.DAYS[-1], len(rows), len(unscored)))
    print("\n%-58s %6s %6s %6s %7s | %s" % ("alert", "caller", "ask", "over", "OLD $",
          "  ".join("%4ds" % w for w in WINDOWS)))
    for r in rows:
        cells = []
        for w in WINDOWS:
            kind, pl, lag = r["new"][w]
            cells.append("   --" if kind == "nofill" else "%+5.0f" % pl)
        print("%-58s %6.2f %6.2f %+5.0f%% %+7.0f | %s"
              % (r["tag"][:58], r["theirs"], r["ask"], r["over"], r["old"] or 0, "  ".join(cells)))
    print("\n* = touch time taken from the live watcher's own log line; others replayed from the recorded underlying")
    print("\nTOTALS")
    old = sum(r["old"] or 0 for r in rows)
    print("  OLD (cross the ask always): %d trades, %+.0f" % (len(rows), old))
    for w in WINDOWS:
        took = [r for r in rows if r["new"][w][0] != "nofill"]
        skipped = [r for r in rows if r["new"][w][0] == "nofill"]
        net = sum(r["new"][w][1] or 0 for r in took)
        sw = [r for r in skipped if (r["old"] or 0) > 0]
        sl = [r for r in skipped if (r["old"] or 0) <= 0]
        rested = [r for r in took if r["new"][w][0] == "rest"]
        print("  NEW %3ds: %2d trades (%d crossed, %d rested-and-filled) %+6.0f | skipped %d: "
              "%d winners worth %+.0f, %d losers worth %+.0f | vs OLD %+.0f"
              % (w, len(took), len(took) - len(rested), len(rested), net, len(skipped),
                 len(sw), sum(r["old"] for r in sw), len(sl), sum(r["old"] for r in sl), net - old))
    print("\nUNSCORED")
    why = defaultdict(int)
    for _tag, reason in unscored:
        why[reason.split(" $")[0].split(" — ")[0][:48]] += 1
    for reason, n in sorted(why.items(), key=lambda kv: -kv[1]):
        print("  %3d  %s" % (n, reason))


if __name__ == "__main__":
    main()
