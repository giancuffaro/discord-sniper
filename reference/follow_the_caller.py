#!/usr/bin/env python3
"""follow_the_caller.py — why don't we get the callers' results?

G, 9/17: "why are these callers calling profits while we are pretty much
replicating their trades but aren't getting their results?"

For every caller entry that later got a trim or an exit call
(daily-reports/CALLER-OUTCOMES.csv), on OUR recorded quotes:
  * what the caller says he paid vs what a follower could actually buy at
    (the ask on the first quote after the alert reached us)
  * what the caller CLAIMED at his first trim vs what the follower really had
    at that same second (bid vs the follower's entry)
  * follower P&L, one contract, three ways:  A sell everything at his FIRST
    trim · B sell at his LAST call (full exit, else last trim) · C our live
    ladder.
MEASUREMENT ONLY. Entries that never got a follow-up call are not in the
outcomes file at all — counted separately from alert_meta as the silent ones.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import caller_price_window_replay as rp                     # noqa: E402
import occ as occ_mod                                       # noqa: E402
import ratchet_replay_tape as rr                            # noqa: E402
import win_rate_dig as dig                                  # noqa: E402

ET = rr.ET
PAT = re.compile(r"^(\w+)\s+([\d.]+)([CP])(?:\s+(\d{1,2})/(\d{1,2}))?")


def ts_of(day, clock):
    return dt.datetime.fromisoformat("%sT%s" % (day, clock)).replace(tzinfo=ET).timestamp()


def load():
    entries = defaultdict(list)
    with open(os.path.join(ROOT, "daily-reports", "CALLER-OUTCOMES.csv"),
              encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            m = PAT.match(r.get("contract") or "")
            if not m:
                continue
            sym, strike, cp, mo, dd = m.groups()
            expiry = "2026-%02d-%02d" % (int(mo), int(dd)) if mo else r["date"]
            try:
                contract = occ_mod.build(sym, expiry, cp, float(strike))
            except (ValueError, TypeError):
                continue
            key = (r["date"], r["entry_time"], contract)
            entries[key].append(r)
    return entries


def main():
    entries = load()
    paths = rp.option_paths({k[2] for k in entries})
    rows, no_tape = [], 0
    for (day, clock, contract), events in entries.items():
        path = paths.get((day, contract))
        t_alert = ts_of(day, clock)
        after = [q for q in (path or []) if q[0] >= t_alert - 2]
        if not after or after[0][0] - t_alert > 60:
            no_tape += 1
            continue
        ask0 = after[0][2]
        theirs = rr._f(events[0].get("entry"))
        if not theirs or theirs > 2.5 * ask0 or theirs < 0.4 * ask0:
            continue
        events.sort(key=lambda e: e["event_time"])

        def bid_at(clock2):
            t = ts_of(day, clock2)
            near = [q for q in path if t - 5 <= q[0] <= t + 45]
            return near[0][1] if near else None

        first = events[0]
        last = next((e for e in events if e["event"] == "full exit"), events[-1])
        b_first, b_last = bid_at(first["event_time"]), bid_at(last["event_time"])
        r = {"a": {"root": rr._root_of(contract), "day": day}, "path": path, "t0": after[0][0],
             "ask": ask0, "bid": after[0][1], "flat": rr._flat_ts(day)}
        ladder = dig.sim(r)
        claimed = rr._f(first.get("reported_pct"))
        peak = max(q[1] for q in path if q[0] >= after[0][0])
        rows.append({"day": day, "caller": first.get("caller") or first.get("room"), "contract": contract,
                     "theirs": theirs, "ask": ask0, "lag": (ask0 / theirs - 1) * 100,
                     "claimed": claimed,
                     "ours_at_trim": None if b_first is None else (b_first / ask0 - 1) * 100,
                     "A": None if b_first is None else (b_first - ask0) * 100,
                     "B": None if b_last is None else (b_last - ask0) * 100,
                     "C": ladder["pl"] if ladder else None, "C_why": ladder["why"] if ladder else "",
                     "C_held": ladder["held_s"] if ladder else 0,
                     "mins_to_trim": (ts_of(day, first["event_time"]) - t_alert) / 60.0,
                     "peak": (peak / ask0 - 1) * 100, "n_trims": sum(1 for e in events if e["event"] == "partial trim"),
                     "full": any(e["event"] == "full exit" for e in events)})

    n = len(rows)
    print("FOLLOW THE CALLER — %d caller entries with a follow-up call AND our quotes (%d had no tape), %s .. %s"
          % (n, no_tape, min(r["day"] for r in rows), max(r["day"] for r in rows)))

    def med(vals):
        vals = [v for v in vals if v is not None]
        return statistics.median(vals) if vals else float("nan")

    print("\n1. THE ENTRY GAP — his posted price vs the ask when the alert reached us")
    print("   median %+.1f%% · over his price on %d of %d · 10%%+ over on %d"
          % (med(r["lag"] for r in rows), sum(1 for r in rows if r["lag"] > 0), n,
             sum(1 for r in rows if r["lag"] >= 10)))

    both = [r for r in rows if r["claimed"] is not None and r["ours_at_trim"] is not None]
    print("\n2. HIS FIRST TRIM — what he CLAIMED vs what a follower HAD at that same moment (%d with both)" % len(both))
    print("   he claimed a median %+.0f%%; the follower was at a median %+.0f%% (selling at the bid, bought at the ask)"
          % (med(r["claimed"] for r in both), med(r["ours_at_trim"] for r in both)))
    print("   follower was GREEN at his first trim on %d of %d; first trim came a median %.1f min after the alert"
          % (sum(1 for r in both if r["ours_at_trim"] > 0), len(both), med(r["mins_to_trim"] for r in rows)))

    print("\n3. FOLLOWER P&L, 1 contract each")
    for key, label in (("A", "A  sell all at his FIRST trim"), ("B", "B  sell at his LAST call (full exit, else last trim)"),
                       ("C", "C  our live ladder")):
        vals = [r[key] for r in rows if r[key] is not None]
        print("   %-52s %3d trades %+7.0f  %+6.1f/trade  win %2d%%"
              % (label, len(vals), sum(vals), sum(vals) / len(vals), 100 * sum(1 for v in vals if v > 2) // len(vals)))
    same = [r for r in rows if r["A"] is not None and r["C"] is not None]
    print("   on the SAME %d trades: A %+.0f vs ladder %+.0f" % (len(same), sum(r["A"] for r in same), sum(r["C"] for r in same)))

    print("\n4. WHAT THE LADDER DID ON TRADES THE CALLER TRIMMED GREEN")
    green = [r for r in same if r["A"] > 2]
    print("   he was tradeable-green at his first trim on %d; our ladder on those: %+.0f (A made %+.0f)"
          % (len(green), sum(r["C"] for r in green), sum(r["A"] for r in green)))
    out_first = [r for r in green if r["C_held"] < r["mins_to_trim"] * 60]
    print("   the ladder was ALREADY OUT before his first trim on %d of %d — median hold %.0fs vs his trim at %.1f min"
          % (len(out_first), len(green), med(r["C_held"] for r in out_first), med(r["mins_to_trim"] for r in out_first)))
    by = defaultdict(int)
    for r in out_first:
        by[r["C_why"]] += 1
    print("   how it left: " + ", ".join("%s %d" % kv for kv in sorted(by.items(), key=lambda kv: -kv[1])))

    print("\n5. THE SHAPE OF HIS RESULTS — best bid after the alert, vs the follower's entry")
    for lvl in (10, 25, 50, 100):
        print("   reached +%d%%: %d of %d" % (lvl, sum(1 for r in rows if r["peak"] >= lvl), n))
    print("   entries that ever got a FULL EXIT call: %d of %d — the rest end on a trim and go quiet" % (sum(1 for r in rows if r["full"]), n))

    print("\n6. BY CALLER (4+), follower selling at his first trim vs our ladder")
    bc = defaultdict(list)
    for r in same:
        bc[(r["caller"] or "?")[:26]].append(r)
    for c, part in sorted(bc.items(), key=lambda kv: -len(kv[1])):
        if len(part) >= 4:
            print("   %-26s %2d   first-trim %+6.0f   ladder %+6.0f   median entry gap %+.0f%%"
                  % (c, len(part), sum(r["A"] for r in part), sum(r["C"] for r in part), med(r["lag"] for r in part)))


if __name__ == "__main__":
    main()
