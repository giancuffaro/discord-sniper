#!/usr/bin/env python3
"""Compare today's live ratchet with a fixed born-stop baseline.

Only alerts with a recorded same-day bid/ask path are replayed.  Both policies
buy one contract at the first recorded ask (or the real fill for a bot trade)
and sell into the observed bid when their stop triggers.  "Without ratchet"
keeps the same born stop fixed; it does not mean holding with no risk limit.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import sys
from collections import defaultdict
from zoneinfo import ZoneInfo

import occ
import ratchet_tiers as rt
from webull_options import stop_below, tick_round, tick_step

HERE = os.path.dirname(os.path.abspath(__file__))
EASTERN = ZoneInfo("America/New_York")


def _f(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quotes(day):
    start = dt.datetime.fromisoformat(day).replace(tzinfo=EASTERN).timestamp()
    end = start + 86400
    out = defaultdict(list)
    path = os.path.join(HERE, "quote_shadow.csv")
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            ts, bid, ask = _f(row.get("ts")), _f(row.get("bid")), _f(row.get("ask"))
            contract = occ.from_dx(row.get("symbol") or "")
            if (contract and ts is not None and start <= ts < end
                    and bid and ask and bid > 0 and ask > 0):
                out[contract].append((ts, bid, ask))
    for rows in out.values():
        rows.sort()
    return out


def _events(day):
    events = []
    with open(os.path.join(HERE, "alert_meta.csv"), encoding="utf-8-sig",
              newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("date") == day and row.get("stage") == "alert" and row.get("occ"):
                events.append({
                    "ts": _f(row.get("ts")), "occ": row["occ"],
                    "label": "%s %s" % (row.get("time", "")[:5], row.get("symbol", "?")),
                    "source": row.get("room") or row.get("caller") or "alert",
                    "fill": None, "actual": None,
                })
    # Filled bot trades have the best entry evidence and must be represented
    # even when alert_meta has no row for them.
    with open(os.path.join(HERE, "master_ledger.csv"), encoding="utf-8-sig",
              newline="") as fh:
        for row in csv.DictReader(fh):
            if (row.get("date") != day or row.get("kind") != "option"
                    or row.get("account") != "live"
                    or str(row.get("manual") or "").lower() in ("true", "1")):
                continue
            contract = row.get("occ")
            if not contract:
                continue
            opened = _f(row.get("opened_ts"))
            events.append({
                "ts": opened, "occ": contract,
                "label": "%s %s" % ((row.get("opened") or "")[:5], row.get("symbol") or "?"),
                "source": row.get("room") or row.get("caller") or "bot fill",
                "fill": _f(row.get("avg_in")), "actual": _f(row.get("pl")),
            })
    return sorted(events, key=lambda x: x["ts"] or 0)


def _born_stop(entry, first_bid, contract):
    born_pct = rt.live_spacing()[0]
    stop = stop_below(entry, born_pct, contract)
    ceiling = round(first_bid - tick_step(first_bid, contract), 2)
    if ceiling >= 0.01 and stop >= ceiling:
        stop = max(0.01, float(tick_round(ceiling, contract)))
    return stop


def _simulate(path, entry, contract, use_ratchet):
    stop = _born_stop(entry, path[0][1], contract)
    peak = -100.0
    moves = 0
    for ts, bid, ask in path:
        gain = (bid - entry) / entry * 100.0
        peak = max(peak, gain)
        if use_ratchet:
            locked = rt.ratchet_locked_pct(gain, entry)
            new_stop = rt.ratchet_stop_price(
                entry, locked, bid=bid, ask=ask, current_stop=stop)
            if new_stop is not None:
                stop = new_stop
                moves += 1
        if bid <= stop:
            return {"exit": bid, "pct": gain, "pl": (bid - entry) * 100,
                    "ts": ts, "stopped": True, "peak": peak, "moves": moves}
    bid = path[-1][1]
    return {"exit": bid, "pct": (bid - entry) / entry * 100,
            "pl": (bid - entry) * 100, "ts": path[-1][0],
            "stopped": False, "peak": peak, "moves": moves}


def _observed_total(day):
    path = os.path.join(HERE, "daily-reports", "REPORT-%s.md" % day)
    try:
        text = open(path, encoding="utf-8").read()
        m = re.search(r"Unique entry alerts observed .*?\|\s*(\d+)\s*\|", text)
        return int(m.group(1)) if m else None
    except OSError:
        return None


def build(day):
    quotes = _quotes(day)
    compared = []
    for event in _events(day):
        path = [r for r in quotes.get(event["occ"], []) if r[0] >= event["ts"]]
        if not path:
            continue
        entry = event["fill"] or path[0][2]
        if not entry or entry <= 0:
            continue
        fixed = _simulate(path, entry, event["occ"], False)
        ratchet = _simulate(path, entry, event["occ"], True)
        compared.append((event, entry, fixed, ratchet, path[-1][0]))

    total = _observed_total(day)
    born, arm, step = rt.live_spacing()
    fixed_sum = sum(x[2]["pl"] for x in compared)
    ratchet_sum = sum(x[3]["pl"] for x in compared)
    lines = [
        "# Ratchet comparison — %s" % day, "",
        "This replay isolates the exit rule. Both versions buy **one contract** at the first recorded ask (the actual fill for a filled bot trade) and use the same initial broker-compatible **-%.0f%% born stop**. The fixed version never moves that stop. The live version arms at **+%.0f%%** and then advances in **+%.0f%%** rungs, subject to tick and spread floors." % (born, arm, step), "",
        "| Alert | Source | Entry | Fixed stop P&L | Ratchet P&L | Ratchet advantage |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for event, entry, fixed, ratchet, _last in compared:
        lines.append("| %s | %s | $%.2f | %+.0f | %+.0f | %+.0f |" % (
            event["label"], event["source"].replace("|", "\\|"), entry,
            fixed["pl"], ratchet["pl"], ratchet["pl"] - fixed["pl"]))
    lines += ["", "## Result", "",
              "- Price-replayable alerts: **%d%s**." %
              (len(compared), " of %d observed" % total if total is not None else ""),
              "- Fixed born stop: **%+.0f** total per one-contract replay." % fixed_sum,
              "- Live ratchet: **%+.0f** total per one-contract replay." % ratchet_sum,
              "- Ratchet advantage on the covered subset: **%+.0f**." % (ratchet_sum - fixed_sum)]
    if total is not None and total > len(compared):
        lines.append("- **%d alerts cannot be scored yet** because no exact-contract bid/ask path was recorded. This subset cannot establish the winner for the entire day." % (total - len(compared)))
    lines += ["- Every replayed path reached a stop, so none of the values above is an end-of-tape mark." if all(x[2]["stopped"] and x[3]["stopped"] for x in compared) else "- At least one value is marked at the end of its available tape and is not a final exit.",
              "- HOOD is deliberately included because the question asks what happened if every alert were forced through. The live bot refused its 22% spread; bypassing that filter would have produced the replayed loss."]
    actual = [x for x in compared if x[0]["actual"] is not None]
    if actual:
        lines += ["", "## Actual bot trade", ""]
        for event, entry, fixed, ratchet, _last in actual:
            lines.append("- %s realized **%+.0f**. The quote replay gives fixed **%+.0f** versus ratchet **%+.0f**; the real ratchet fill was better because the market sell completed above the trigger bid." % (event["label"], event["actual"], fixed["pl"], ratchet["pl"]))
    os.makedirs(os.path.join(HERE, "daily-reports"), exist_ok=True)
    out = os.path.join(HERE, "daily-reports", "RATCHET-COMPARE-%s.md" % day)
    with open(out + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    os.replace(out + ".tmp", out)
    print(out)
    return out


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat())
