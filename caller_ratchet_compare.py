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
    tracked = policy._events(day)
    for source_entry in all_entries:
        if not source_entry.get("side") or not source_entry.get("occ"):
            continue
        matches = [event for event in tracked
                   if event["occ"] == source_entry["occ"]
                   and abs(event["ts"] - source_entry["ts"]) <= 3]
        if matches:
            event = min(matches, key=lambda e: abs(e["ts"] - source_entry["ts"]))
        else:
            event = {"ts": source_entry["ts"], "occ": source_entry["occ"],
                     "label": "%s %s" % (source_entry["time"][:5],
                                           source_entry["symbol"]),
                     "source": source_entry.get("caller") or
                               source_entry.get("room") or "alert",
                     "fill": None, "actual": None, "actual_exit": None,
                     "caller_entry": source_entry.get("entry")}
        path = [r for r in quotes.get(event["occ"], []) if r[0] >= event["ts"]]
        if not path:
            continue
        caller_entry = event.get("caller_entry")
        event["symbol"] = event["label"].split()[-1]
        # A posted "price" that matches the underlying is the stock quote, not
        # the premium (9/14 Midas SPY 760P @ 760.40 -> a -$75,936 replay row
        # that owned the day's total). The live OPEN path has refused this
        # since v3.8.24; this is the same rule, measured against the recorded
        # `und` instead of the caller's wording. The row stays and keeps its
        # caller evidence; only its dollars are withheld.
        stock_price = (caller_entry is not None
                       and event.get("fill") is None
                       and caller_outcomes.is_posted_stock_price(
                           day, event["symbol"], caller_entry, event["ts"],
                           ask=path[0][2]))
        if stock_price:
            event["caller_entry_raw"] = caller_entry
            caller_entry = None
            event["caller_entry"] = None
        entry = event.get("fill") or caller_entry or path[0][2]
        if not entry:
            continue
        ratchet = policy._simulate(path, entry, event["occ"], True)
        caller, evidence = _caller_result(day, event, claims)
        basis = (caller_outcomes.STOCK_PRICE_BASIS if stock_price else
                 "real fill = caller posted" if event.get("fill") is not None
                 and caller_entry is not None
                 and abs(event["fill"] - caller_entry) < 0.005 else
                 "real bot fill" if event.get("fill") is not None else
                 "caller posted" if caller_entry is not None else
                 "first recorded ask; caller price absent")
        shown_exit, shown_pct, shown_pl, ratchet_basis = _our_result(
            event, entry, ratchet)
        compared.append((event, entry, basis, caller, evidence, ratchet,
                         shown_exit, shown_pct, shown_pl, ratchet_basis,
                         stock_price))

    total = len(all_entries)
    lines = ["# Caller entry versus our ratchet — %s" % day, "",
             "The caller's posted premium is the hypothetical fill when available. Our 5/3/5 ratchet is replayed against the best available exact-contract bid path: historical OPRA when present, otherwise the live Tastytrade/Webull tapes. Caller exits use their posted price/percentage, or the contemporaneous bid when they posted only the exit time.", "",
             "| Alert | Source | Hypothetical entry | Entry basis | Caller result | Caller evidence | Our ratchet exit | Our ratchet result |",
             "|---|---|---:|---|---|---|---:|---:|"]
    for (event, entry, basis, caller, evidence, _ratchet, shown_exit,
         shown_pct, shown_pl, ratchet_basis, stock_price) in compared:
        result = ("— (excluded from the total)" if stock_price else
                  "%+.1f%% / %+.0f (%s)" % (shown_pct, shown_pl, ratchet_basis))
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            event["label"], event["source"].replace("|", "\\|"),
            "—" if stock_price else "$%.2f" % entry,
            basis, caller, evidence,
            "—" if stock_price else "$%.2f" % shown_exit, result))

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
    # A row whose posted "price" was the underlying carries no honest dollars,
    # so it is kept in the table and left out of every total.
    stock_rows = [row for row in compared if row[10]]
    scorable = [row for row in compared if not row[10]]
    ratchet_sum = sum(row[8] for row in scorable)
    strict = [row for row in scorable if row[0].get("caller_entry") is not None]
    strict_sum = sum(row[8] for row in strict)
    numeric_caller = sum(1 for row in scorable
                         if "unavailable" not in row[3])
    lines += ["", "## Result", "",
              "- Comparable ratchet paths: **%d%s**." % (
                  len(compared), " of %d observed" % total if total is not None else ""),
              "- Our ratchet on the **%d paths with a caller-posted entry**: **%+.0f per one-contract replay**." % (len(strict), strict_sum),
              "- Including the no-price alerts at their first recorded ask: **%+.0f across %d scorable paths**." % (ratchet_sum, len(scorable)),
              "- Numeric caller full-exit results on this subset: **%d of %d**; missing caller exit prices prevent an honest aggregate caller P&L." % (numeric_caller, len(scorable)),]
    if stock_rows:
        lines.append(
            "- **%d row%s excluded from every dollar total** because the caller "
            "posted the STOCK price where the premium belongs (%s). The row "
            "stays visible; its P&L would be nonsense. Same rule the live OPEN "
            "path has refused since v3.8.24."
            % (len(stock_rows), "s" if len(stock_rows) != 1 else "",
               ", ".join("%s @ %.2f" % (row[0]["label"],
                                        row[0].get("caller_entry_raw") or 0.0)
                         if row[0].get("caller_entry_raw") else row[0]["label"]
                         for row in stock_rows)))
    lines += [
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
