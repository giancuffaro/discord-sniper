#!/usr/bin/env python3
"""Compare caller-reported management with our ratchet from their entry.

This is deliberately separate from the execution-price replay.  A caller's
posted premium is treated as the hypothetical fill when present, even if the
recorded offer differed.  The ratchet then exits against the observed bid.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

import daily_policy_compare as policy
import caller_outcomes

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
    symbol = event.get("symbol") or event["label"].split()[-1]
    matched = [r for r in claims if r.get("symbol") == symbol
               and abs(_clock(day, r["entry_time"]) - event["ts"]) <= 3]
    if not matched:
        return "unavailable", "no paired caller exit"
    full = [r for r in matched if r.get("event") == "full exit"]
    row = full[-1] if full else matched[-1]
    scope = "full" if full else "partial"
    exit_px = policy._f(row.get("reported_exit"))
    stated_pct = policy._f(row.get("reported_pct"))
    per_contract = policy._f(row.get("profit_per_contract"))
    calc_pct = policy._f(row.get("calculated_pct"))
    if exit_px is not None:
        pct = calc_pct if calc_pct is not None else stated_pct
        return ("%s $%.2f%s" %
                (scope, exit_px, " (%+.1f%%)" % pct if pct is not None else ""),
                row.get("basis") or "caller-stated")
    if stated_pct is not None:
        return "%s %+.1f%%" % (scope, stated_pct), row.get("basis") or "caller-stated"
    if per_contract is not None:
        detail = (" (%+.1f%%)" % calc_pct if calc_pct is not None else "")
        return ("%s $%.0f/contract%s" % (scope, per_contract, detail),
                row.get("basis") or "caller-stated")
    return "%s exit posted; price unavailable" % scope, row.get("basis") or "caller-stated"


def _all_entries(day):
    parsed = caller_outcomes._messages(day)
    entries = caller_outcomes._enrich_entries(
        day, caller_outcomes._decision_entries(day), parsed)
    # caller_outcomes intentionally omits recovered futures because its
    # option-percent math does not apply to them. This all-alert inventory
    # still needs the recovered futures row so the denominator reconciles.
    try:
        recovered = json.load(open(os.path.join(
            HERE, "daily-audits", "recovered-%s.json" % day), encoding="utf-8"))
    except (OSError, ValueError):
        recovered = {"entries": []}
    for row in recovered.get("entries") or []:
        text = row.get("alert") or ""
        m = re.match(r"\s*(MNQ|MES|NQ|ES|MGC|GC)\b.*?@\s*([0-9.]+)",
                     text, flags=re.I)
        if not m:
            continue
        clock = (row.get("time") or "00:00") + ":00"
        entries.append({"symbol": m.group(1).upper(), "strike": None,
                        "side": None, "expiry": None,
                        "entry": float(m.group(2)), "time": clock,
                        "ts": _clock(day, clock), "caller": "",
                        "room": "recovered reader outage", "occ": "",
                        "contract_text": text, "origin": "recovered"})
    return sorted(entries, key=lambda e: e["ts"])


def _our_result(event, entry, replay):
    """Broker truth wins for a filled trade; otherwise use the simulation."""
    if event.get("actual") is not None:
        pl = event["actual"]
        pct = pl / (entry * 100.0) * 100.0 if entry else None
        return event.get("actual_exit"), pct, pl, "broker-confirmed actual"
    return (replay["exit"], replay["pct"], replay["pl"],
            "quote-path replay")


def build(day):
    quotes = policy._quotes(day)
    claims = _claims(day)
    all_entries = _all_entries(day)
    compared = []
    for event in policy._events(day):
        path = [r for r in quotes.get(event["occ"], []) if r[0] >= event["ts"]]
        if not path:
            continue
        caller_entry = event.get("caller_entry")
        event["symbol"] = event["label"].split()[-1]
        entry = event.get("fill") or caller_entry or path[0][2]
        if not entry:
            continue
        ratchet = policy._simulate(path, entry, event["occ"], True)
        caller, evidence = _caller_result(day, event, claims)
        basis = ("real fill = caller posted" if event.get("fill") is not None
                 and caller_entry is not None
                 and abs(event["fill"] - caller_entry) < 0.005 else
                 "real bot fill" if event.get("fill") is not None else
                 "caller posted" if caller_entry is not None else
                 "first recorded ask; caller price absent")
        shown_exit, shown_pct, shown_pl, ratchet_basis = _our_result(
            event, entry, ratchet)
        compared.append((event, entry, basis, caller, evidence, ratchet,
                         shown_exit, shown_pct, shown_pl, ratchet_basis))

    total = len(all_entries)
    lines = ["# Caller entry versus our ratchet — %s" % day, "",
             "The caller's posted premium is the hypothetical fill when available. Our 5/3/5 ratchet is replayed against the recorded Tastytrade bid path. Caller exits use their posted price/percentage, or the contemporaneous bid when they posted only the exit time.", "",
             "| Alert | Source | Hypothetical entry | Entry basis | Caller result | Caller evidence | Our ratchet exit | Our ratchet result |",
             "|---|---|---:|---|---|---|---:|---:|"]
    for (event, entry, basis, caller, evidence, _ratchet, shown_exit,
         shown_pct, shown_pl, ratchet_basis) in compared:
        lines.append("| %s | %s | $%.2f | %s | %s | %s | $%.2f | %+.1f%% / %+.0f (%s) |" % (
            event["label"], event["source"].replace("|", "\\|"), entry,
            basis, caller, evidence, shown_exit, shown_pct, shown_pl,
            ratchet_basis))

    lines += ["", "## Alerts awaiting an exact path", "",
              "These rows are still part of the comparison. Their caller evidence is retained; only our ratchet result waits for contract tape.", "",
              "| Alert | Trader / room | Original entry | Caller result | Ratchet status |",
              "|---|---|---:|---|---|"]
    scored = [(row[0]["symbol"], row[0]["ts"]) for row in compared]
    for entry in all_entries:
        if any(entry["symbol"] == sym and abs(entry["ts"] - ts) <= 3
               for sym, ts in scored):
            continue
        fake = {"symbol": entry["symbol"], "label": entry["symbol"],
                "ts": entry["ts"]}
        caller, _evidence = _caller_result(day, fake, claims)
        source = entry.get("caller") or entry.get("room") or "unknown"
        px = ("$%.2f" % entry["entry"]
              if entry.get("entry") is not None else "—")
        if not entry.get("side"):
            status = "futures path; options 5/3/5 does not apply"
        elif not entry.get("occ"):
            status = "expiry missing; exact contract unresolved"
        else:
            status = "exact bid/ask path unavailable"
        lines.append("| %s %s | %s | %s | %s | %s |" % (
            entry["time"][:5], entry["contract_text"].replace("|", "\\|"),
            source.replace("|", "\\|"), px, caller, status))
    ratchet_sum = sum(row[8] for row in compared)
    strict = [row for row in compared if row[0].get("caller_entry") is not None]
    strict_sum = sum(row[8] for row in strict)
    numeric_caller = sum(1 for row in compared
                         if "unavailable" not in row[3])
    lines += ["", "## Result", "",
              "- Comparable ratchet paths: **%d%s**." % (
                  len(compared), " of %d observed" % total if total is not None else ""),
              "- Our ratchet on the **%d paths with a caller-posted entry**: **%+.0f per one-contract replay**." % (len(strict), strict_sum),
              "- Including the one no-price alert at its first recorded ask: **%+.0f across all %d paths**." % (ratchet_sum, len(compared)),
              "- Numeric caller full-exit results on this subset: **%d of %d**; missing caller exit prices prevent an honest aggregate caller P&L." % (numeric_caller, len(compared)),
              "- Broker-confirmed results override quote-path simulations whenever the bot actually traded.",
              "- Every observed entry is listed: **%d scored + %d awaiting tape/futures handling = %d**." %
              (len(compared), len(all_entries) - len(compared), len(all_entries)),
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
