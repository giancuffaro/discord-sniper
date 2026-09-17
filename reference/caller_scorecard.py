#!/usr/bin/env python3
"""caller_scorecard.py — per caller: does he TALK, and does following him pay?

G, 9/17: "yea do that". Two facts came out of follow_the_caller.py: 41% of
alerts never get another word (the losers nobody announces), and on the ones
that do, selling at the caller's own first trim beat our ladder by a mile. Both
are properties of the CALLER, so this ranks callers on them, over every day we
have quotes for (alert_meta.csv + the quote tapes), rebuilt by the daily audit:

  alerts      taped option entries, instant buy at the ask, 1 contract
  silent      never got a trim / exit / stop call afterwards
  gap         median ask-vs-his-posted-price when the alert reached us
  FOLLOW HIM  exit at the bid on his FIRST follow-up call; a -20% disaster
              stop; otherwise flat at the last quote. Applied to ALL his
              alerts, silent ones included — that is the honest version.
  LADDER      the live ladder on the same alerts (ratchet_replay_tape).

UNDER 10 ALERTS IS NOT A RANKING, it is a list; those rows are marked.
MEASUREMENT ONLY — nothing here can bench, follow or trade anything.
Output: daily-reports/CALLER-SCORECARD.md (ONE file, overwritten).
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import follow_the_caller as ftc                             # noqa: E402
import ladder_grid_test as lg                               # noqa: E402
import ratchet_replay_tape as rr                            # noqa: E402
import win_rate_dig as dig                                  # noqa: E402

OUT = os.path.join(ROOT, "daily-reports", "CALLER-SCORECARD.md")
DISASTER_STOP_PCT = 20.0
MIN_N = 10


def days():
    found = set()
    with open(os.path.join(ROOT, "alert_meta.csv"), encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("stage") == "alert" and r.get("date"):
                found.add(r["date"])
    return sorted(found)


def first_calls():
    first = {}
    for (day, _clock, contract), events in ftc.load().items():
        t1 = min(ftc.ts_of(day, e["event_time"]) for e in events)
        first[(day, contract)] = min(first.get((day, contract), 1e18), t1)
    return first


def follow(row, t_call):
    entry = row["ask"]
    walk = [q for q in row["path"] if row["t0"] <= q[0] <= row["flat"]]
    for ts, bid, _ask in walk:
        if bid <= entry * (1 - DISASTER_STOP_PCT / 100.0):
            return (bid - entry) * 100.0
        if t_call and ts >= t_call:
            return (bid - entry) * 100.0
    return (walk[-1][1] - entry) * 100.0 if walk else 0.0


ALIASES = {"abtrades alert bot": "AbTrades", "elite": "EliteOptions | Brando",
           "vero-alerts": "Vero"}


def who(alert):
    """One person, one row: "Brett (Admin)", "@Brett" and "Brett" are Brett."""
    import re
    name = (alert.get("caller") or "").strip()
    if not name or name == "?":
        return "(room) " + (alert.get("room") or "?")[:28]
    name = re.sub(r"\s*\((?:admin|mod)\)\s*", "", name, flags=re.I).lstrip("@").strip()
    return ALIASES.get(name.lower(), name)


def build():
    all_days = days()
    rr.DAYS = tuple(all_days)
    first = first_calls()
    rows = []
    for day in all_days:
        alerts = lg.day_alerts(day)
        # day_alerts keeps `caller`; carry the room for unnamed ones
        rooms = {}
        with open(os.path.join(ROOT, "alert_meta.csv"), encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("date") == day and r.get("stage") == "alert":
                    rooms[(r.get("occ"), (r.get("time") or "")[:4])] = r.get("room") or ""
        for a in alerts:
            a["room"] = rooms.get((a["occ"], a["time"][:4]), "")
        rows += lg.rows_for(alerts)
    by = defaultdict(list)
    for r in rows:
        a = r["a"]
        t_call = first.get((a["day"], a["occ"]))
        ladder = dig.sim(r)
        gap = (r["ask"] / a["their_price"] - 1) * 100.0 if a.get("their_price") else None
        if gap is not None and not (-60 < gap < 150):
            gap = None
        by[who(a)].append({"silent": t_call is None, "follow": follow(r, t_call),
                           "ladder": ladder["pl"] if ladder else 0.0, "gap": gap, "day": a["day"]})
    return all_days, rows, by


def render(all_days, rows, by):
    stamp = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    total = [x for v in by.values() for x in v]
    lines = ["# CALLER SCORECARD — %s .. %s (%d days, %d taped alerts)" % (all_days[0], all_days[-1], len(all_days), len(rows)),
             "",
             "Instant buy at the ask, 1 contract, our own recorded quotes. **FOLLOW HIM** = out at the bid on his first "
             "follow-up call, a -%d%% disaster stop, else flat at the last quote — on ALL his alerts, silent ones included. "
             "**LADDER** = the live ladder (%s) on the same alerts. Under %d alerts is a list, not a ranking. Measurement only."
             % (DISASTER_STOP_PCT, "/".join("%g" % x for x in (rr.BORN_PCT,) + tuple(rr.TIERS_LIVE[0][1][i] for i in (0, 2))), MIN_N),
             "",
             "ALL CALLERS: %d alerts · silent %d%% · follow him %+.0f · ladder %+.0f"
             % (len(total), round(100 * sum(1 for x in total if x["silent"]) / max(1, len(total))),
                sum(x["follow"] for x in total), sum(x["ladder"] for x in total)),
             "",
             "| caller | alerts | days | silent | entry gap | FOLLOW HIM | per alert | LADDER | per alert | better |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    ranked = sorted(by.items(), key=lambda kv: (len(kv[1]) < MIN_N, -sum(x["follow"] for x in kv[1]) / len(kv[1])))
    for name, part in ranked:
        n = len(part)
        gaps = [x["gap"] for x in part if x["gap"] is not None]
        f, l = sum(x["follow"] for x in part), sum(x["ladder"] for x in part)
        lines.append("| %s%s | %d | %d | %d%% | %s | %+.0f | %+.1f | %+.0f | %+.1f | %s |"
                     % (name.replace("|", "/")[:30], "" if n >= MIN_N else " *(few)*", n,
                        len({x["day"] for x in part}),
                        round(100 * sum(1 for x in part if x["silent"]) / n),
                        ("%+.0f%%" % statistics.median(gaps)) if gaps else "—",
                        f, f / n, l, l / n, "follow" if f > l else "ladder"))
    lines += ["", "built from alert_meta.csv, daily-reports/CALLER-OUTCOMES.csv and the quote tapes · %s" % stamp, ""]
    return "\n".join(lines)


def main():
    all_days, rows, by = build()
    text = render(all_days, rows, by)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, OUT)
    print(text)


if __name__ == "__main__":
    main()
