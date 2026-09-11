#!/usr/bin/env python3
"""Compare caller-reported management with our ratchet from their entry.

This is deliberately separate from the execution-price replay.  A caller's
posted premium is treated as the hypothetical fill when present, even if the
recorded offer differed.  The ratchet then exits against the observed bid.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

import daily_policy_compare as policy

HERE = os.path.dirname(os.path.abspath(__file__))
ET = ZoneInfo("America/New_York")


def _clock(day, value):
    return dt.datetime.fromisoformat("%sT%s" % (day, value)).replace(
        tzinfo=ET).timestamp()


def _claims(day):
    path = os.path.join(HERE, "daily-reports",
                        "CALLER-OUTCOMES-%s.csv" % day)
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _caller_result(day, event, claims):
    matched = [r for r in claims if r.get("symbol") == event["label"].split()[-1]
               and abs(_clock(day, r["entry_time"]) - event["ts"]) <= 3]
    if not matched:
        return "unavailable", "no paired caller exit"
    full = [r for r in matched if r.get("event") == "full exit"]
    row = full[-1] if full else matched[-1]
    scope = "full" if full else "partial"
    exit_px = policy._f(row.get("reported_exit"))
    stated_pct = policy._f(row.get("reported_pct"))
    calc_pct = policy._f(row.get("calculated_pct"))
    if exit_px is not None:
        pct = calc_pct if calc_pct is not None else stated_pct
        return ("%s $%.2f%s" %
                (scope, exit_px, " (%+.1f%%)" % pct if pct is not None else ""),
                row.get("basis") or "caller-stated")
    if stated_pct is not None:
        return "%s %+.1f%%" % (scope, stated_pct), row.get("basis") or "caller-stated"
    return "%s exit posted; price unavailable" % scope, row.get("basis") or "caller-stated"


def build(day):
    quotes = policy._quotes(day)
    claims = _claims(day)
    compared = []
    for event in policy._events(day):
        path = [r for r in quotes.get(event["occ"], []) if r[0] >= event["ts"]]
        if not path:
            continue
        caller_entry = event.get("caller_entry")
        entry = event.get("fill") or caller_entry or path[0][2]
        if not entry:
            continue
        ratchet = policy._simulate(path, entry, event["occ"], True)
        caller, evidence = _caller_result(day, event, claims)
        basis = ("real bot fill" if event.get("fill") is not None else
                 "caller posted" if caller_entry is not None else
                 "first recorded ask; caller price absent")
        compared.append((event, entry, basis, caller, evidence, ratchet))

    total = policy._observed_total(day)
    lines = ["# Caller entry versus our ratchet — %s" % day, "",
             "The caller's posted premium is the hypothetical fill when available. Our 5/3/5 ratchet is replayed against the recorded Tastytrade bid path. Caller exits use their posted price/percentage, or the contemporaneous bid when they posted only the exit time.", "",
             "| Alert | Source | Hypothetical entry | Entry basis | Caller result | Caller evidence | Our ratchet exit | Our ratchet result |",
             "|---|---|---:|---|---|---|---:|---:|"]
    for event, entry, basis, caller, evidence, ratchet in compared:
        lines.append("| %s | %s | $%.2f | %s | %s | %s | $%.2f | %+.1f%% / %+.0f |" % (
            event["label"], event["source"].replace("|", "\\|"), entry,
            basis, caller, evidence, ratchet["exit"], ratchet["pct"], ratchet["pl"]))
    ratchet_sum = sum(row[-1]["pl"] for row in compared)
    numeric_caller = sum(1 for row in compared
                         if "unavailable" not in row[3])
    lines += ["", "## Result", "",
              "- Comparable ratchet paths: **%d%s**." % (
                  len(compared), " of %d observed" % total if total is not None else ""),
              "- Our ratchet from caller-posted/available entry prices: **%+.0f per one-contract replay**." % ratchet_sum,
              "- Numeric caller full-exit results on this subset: **%d of %d**; missing caller exit prices prevent an honest aggregate caller P&L." % (numeric_caller, len(compared)),
              "- This assumes the caller's posted price filled. It measures trade management from their original entry, not whether that fill was executable for us."]
    out = os.path.join(HERE, "daily-reports",
                       "CALLER-VS-RATCHET-%s.md" % day)
    with open(out + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    os.replace(out + ".tmp", out)
    print(out)
    return out


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat())
