#!/usr/bin/env python3
"""Build a conservative caller entry/exit claim ledger from daily messages.

Caller claims stay separate from broker truth and policy simulations. A stated
percentage is useful evidence, but a partial trim is not promoted to a complete
trade result. When a caller posts an exact exit price, the percentage is
calculated from their stated entry. When they post only a percentage, the
corresponding option price is explicitly labelled implied.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

import daily_report
import jsparse
import occ as occ_symbol
import replay_check

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "daily-reports")
ET = ZoneInfo("America/New_York")


def _f(value):
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _clock(day, hhmmss):
    return dt.datetime.fromisoformat("%sT%s" % (day, hhmmss)).replace(
        tzinfo=ET).timestamp()


def _entry_contract(text, day):
    m = re.search(r"\b([A-Z][A-Z0-9.]*)\s+(\d+(?:\.\d+)?)([CP])\b", text)
    if not m:
        p = re.search(r"@\s*\$?([0-9]+(?:\.[0-9]+)?)", text or "")
        return {"symbol": text.split(None, 1)[0].upper() if text else "",
                "strike": None, "side": None, "expiry": None,
                "entry": _f(p.group(1)) if p else None}
    expiry = None
    d = re.search(r"\b(0DTE|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b", text,
                  flags=re.I)
    if d:
        token = d.group(1).upper()
        if token == "0DTE":
            expiry = day
        else:
            parts = [int(x) for x in token.split("/")]
            year = parts[2] if len(parts) == 3 else int(day[:4])
            if year < 100:
                year += 2000
            expiry = "%04d-%02d-%02d" % (year, parts[0], parts[1])
    p = re.search(r"@\s*\$?([0-9]+(?:\.[0-9]+)?)", text)
    return {"symbol": m.group(1), "strike": _f(m.group(2)),
            "side": "CALLS" if m.group(3) == "C" else "PUTS",
            "expiry": expiry, "entry": _f(p.group(1)) if p else None}


def _decision_entries(day):
    _messages, decisions = daily_report._decision_rows(day)
    decisions = daily_report._finalize_deferred(day, decisions)
    out = []
    for row in decisions:
        if row["action"] != "OPEN":
            continue
        contract = _entry_contract(row["contract"], day)
        source = re.search(r"—\s+(.+?)\s+·\s+(.+?)\s+—", row["text"])
        out.append({**contract, "time": row["time"],
                    "ts": _clock(day, row["time"]),
                    "caller": source.group(1) if source else "",
                    "room": source.group(2) if source else "",
                    "contract_text": row["contract"], "origin": "decision"})
    # Forensic entries did not receive a normal decision, but they are still
    # caller events and can have later trims/exits worth preserving.
    try:
        recovered = json.load(open(os.path.join(
            HERE, "daily-audits", "recovered-%s.json" % day), encoding="utf-8"))
    except (OSError, ValueError):
        recovered = {"entries": []}
    for row in recovered.get("entries") or []:
        contract = _entry_contract(row.get("alert") or "", day)
        if contract.get("symbol") in ("", "MNQ", "MGC"):
            continue
        clock = (row.get("time") or "00:00") + ":00"
        out.append({**contract, "time": clock, "ts": _clock(day, clock),
                    "caller": "", "room": "",
                    "contract_text": row.get("alert") or "?",
                    "origin": "recovered"})
    return out


def _messages(day):
    replay_check.DAY = day
    rows = {}
    for fn in replay_check.exports_for_day(day):
        messages, _dids = replay_check.load(fn)
        for msg in messages:
            rows[(msg[0], msg[2], msg[3][:160])] = msg
    messages = sorted(rows.values(), key=lambda x: x[0])
    cleaned = [replay_check.strip_header(m[3]) for m in messages]
    configs = [replay_check.parser_cfg(m[2], cleaned[i])
               for i, m in enumerate(messages)]
    parsed = jsparse.parse_many(cleaned, configs)
    return list(zip(messages, cleaned, parsed))


def _enrich_entries(day, entries, parsed_messages):
    # alert_meta has the exact OCC identity for the contracts captured live.
    meta = []
    try:
        with open(os.path.join(HERE, "alert_meta.csv"), encoding="utf-8-sig",
                  newline="") as fh:
            meta = [r for r in csv.DictReader(fh)
                    if r.get("date") == day and r.get("stage") == "alert"]
    except OSError:
        pass
    for entry in entries:
        near = [r for r in meta if r.get("symbol") == entry["symbol"]
                and abs((_f(r.get("ts")) or 0) - entry["ts"]) <= 120]
        if near:
            row = min(near, key=lambda r: abs((_f(r.get("ts")) or 0) - entry["ts"]))
            entry["occ"] = row.get("occ")
            entry["expiry"] = entry["expiry"] or row.get("expiry")
            entry["entry"] = entry["entry"] or _f(row.get("their_price"))
            entry["room"] = entry["room"] or row.get("room") or ""
            entry["caller"] = entry["caller"] or row.get("caller") or ""
        else:
            entry["occ"] = ""
        # Fill missing attribution from the closest raw OPEN in the same symbol.
        candidates = [(m, p) for m, _text, p in parsed_messages
                      if p.get("action") == "OPEN"
                      and p.get("symbol") == entry["symbol"]
                      and abs(_clock(day, m[0]) - entry["ts"]) <= 120]
        if candidates:
            m, p = min(candidates,
                       key=lambda x: abs(_clock(day, x[0][0]) - entry["ts"]))
            entry["room"] = entry["room"] or m[1]
            entry["entry"] = entry["entry"] or _f(p.get("limit"))
        if entry.get("origin") == "recovered" and not candidates:
            # Some forensic entries are visible contract cards that the
            # parser deliberately did not promote. Their ticker/strike text
            # can still establish attribution without inventing an order.
            token = str(int(entry["strike"]) if entry.get("strike") is not None
                        and float(entry["strike"]).is_integer()
                        else entry.get("strike") or "")
            raw_near = [m for m, text, _p in parsed_messages
                        if abs(_clock(day, m[0]) - entry["ts"]) <= 120
                        and re.search(r"\b%s\b" % re.escape(entry["symbol"]),
                                      text, flags=re.I)
                        and (not token or token in text)]
            if raw_near:
                entry["room"] = min(
                    raw_near,
                    key=lambda m: abs(_clock(day, m[0]) - entry["ts"]))[1]
        if not entry.get("room"):
            # Contextual fills such as Midas's "1.46 on starters" carry no
            # symbol. The nearest raw row at the recovered timestamp still
            # establishes the room without inventing a contract.
            contextual = [(m, p) for m, _text, p in parsed_messages
                          if abs(_clock(day, m[0]) - entry["ts"]) <= 45
                          and "fill confirmation" in (p.get("matched") or "")]
            nearby = [m for m, _p in contextual]
            if not nearby:
                nearby = [m for m, _text, p in parsed_messages
                          if abs(_clock(day, m[0]) - entry["ts"]) <= 45
                          and p.get("kind") != "future"]
            if nearby:
                entry["room"] = min(
                    nearby, key=lambda m: abs(_clock(day, m[0]) - entry["ts"]))[1]
        if not entry.get("occ") and all(entry.get(k) for k in
                                            ("symbol", "expiry", "side", "strike")):
            try:
                entry["occ"] = occ_symbol.build(entry["symbol"], entry["expiry"],
                                                 entry["side"], entry["strike"])
            except ValueError:
                pass
        # Repair the one unsafe whole-cent form using its source wording. The
        # live parser now handles this prospectively; this branch corrects a
        # decision that was already durably logged as @300.00 before the fix.
        if (entry.get("entry") and entry["entry"] >= 100
                and entry.get("strike") is not None):
            cents_posts = [text for m, text, _p in parsed_messages
                           if abs(_clock(day, m[0]) - entry["ts"]) <= 120
                           and re.search(
                               r"\b%s\s+%s\s*[cp]\b\s+at\s+(\d{2,5})"
                               r"(?=\s+for\s+you\s+rich\s+folks\b)" % (
                                   re.escape(entry["symbol"]),
                                   re.escape(str(int(entry["strike"])))),
                               text, flags=re.I)]
            if cents_posts:
                match = re.search(r"\bat\s+(\d{2,5})\s+for\s+you\s+rich",
                                  cents_posts[0], flags=re.I)
                if match:
                    entry["entry"] = int(match.group(1)) / 100.0
                    entry["contract_text"] = re.sub(
                        r"@\s*[0-9]+(?:\.[0-9]+)?",
                        "@ %.2f" % entry["entry"],
                        entry["contract_text"])
    return entries


def _quote_paths(day):
    paths = {}
    path = os.path.join(HERE, "quote_shadow.csv")
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    ts = float(row["ts"]); bid = float(row["bid"])
                    contract = occ_symbol.from_dx(row.get("symbol") or "")
                except (TypeError, ValueError):
                    continue
                if (contract and bid > 0
                        and dt.datetime.fromtimestamp(ts, ET).date().isoformat() == day):
                    paths.setdefault(contract, []).append((ts, bid))
    except OSError:
        pass
    return paths


def _claim_values(text, action):
    # Work on the visible post after repeated accessible-card headers.
    price = None
    for pattern in (
        r"\bSTC\b[^\n]*?@\s*\$?((?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+))",
        r"@\s*\$?((?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+))\s+from\s+\$?[0-9]",
        r"\bout(?:\s+on\s+(?:most|all))?[^\n]{0,30}?\s((?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+))\b",
    ):
        m = re.search(pattern, text, flags=re.I)
        if m:
            price = _f(m.group(1))
            break
    pcts = [_f(x) for x in re.findall(r"(?<![\w.])([+-]?\d+(?:\.\d+)?)\s*%", text)]
    pct = pcts[-1] if pcts else None
    per_contract = None
    m = re.search(r"\b([0-9]+(?:\.\d+)?)\s*/\s*con(?:tract)?\b", text,
                  flags=re.I)
    if m:
        per_contract = _f(m.group(1))
    partial = action == "TRIM" or bool(re.search(
        r"\b(partial|trim|runner|1/\d|half|most)\b", text, flags=re.I))
    return price, pct, per_contract, partial


def build(day):
    parsed_messages = _messages(day)
    entries = _enrich_entries(day, _decision_entries(day), parsed_messages)
    quote_paths = _quote_paths(day)
    claims = []
    for message, cleaned, parsed in parsed_messages:
        action = parsed.get("action")
        if action not in ("TRIM", "CLOSE"):
            continue
        price, pct, per_contract, partial = _claim_values(cleaned, action)
        symbol = parsed.get("symbol")
        ts = _clock(day, message[0])
        candidates = [e for e in entries if e["ts"] < ts
                      and (not symbol or e["symbol"] == symbol)]
        same_room = [e for e in candidates
                     if e.get("room") and (e["room"] in message[1]
                                           or message[1] in e["room"])]
        if same_room:
            candidates = same_room
        elif not symbol or len({e.get("room") for e in candidates}) > 1:
            # A symbol-less percentage or two callers in the same ticker is
            # not enough identity. Better an explicit gap than a false claim.
            continue
        if not candidates:
            continue
        entry = max(candidates, key=lambda e: e["ts"])
        if symbol and entry["symbol"] != symbol:
            continue
        basis = "caller-stated"
        if price is None and pct is None and per_contract is None:
            # A timestamped full exit plus a contemporaneous executable bid
            # is calculable even when the caller omitted the price.
            if action != "CLOSE":
                continue
            path = quote_paths.get(entry.get("occ")) or []
            if path:
                nearest = min(path, key=lambda r: abs(r[0] - ts))
                if abs(nearest[0] - ts) <= 5:
                    price = nearest[1]
                    basis = "market bid at caller exit"
                else:
                    basis = "caller exit; price unavailable"
            else:
                basis = "caller exit; price unavailable"
        entry_px = entry.get("entry")
        calc_pct = ((price - entry_px) / entry_px * 100.0
                    if price is not None and entry_px else None)
        implied = (entry_px * (1.0 + pct / 100.0)
                   if price is None and pct is not None and entry_px else None)
        if (price is None and pct is None and per_contract is not None
                and entry_px):
            # Listed equity/index options use the standard 100 multiplier.
            # "$500/con" therefore adds $5.00 to the quoted premium.
            implied = entry_px + per_contract / 100.0
            calc_pct = per_contract / entry_px
        claims.append({
            "entry_time": entry["time"], "event_time": message[0],
            "room": entry.get("room") or message[1],
            "caller": entry.get("caller") or "", "symbol": entry["symbol"],
            "contract": entry["contract_text"], "entry": entry_px,
            "event": "partial trim" if partial else "full exit",
            "reported_exit": price, "reported_pct": pct,
            "profit_per_contract": per_contract,
            "calculated_pct": calc_pct, "implied_exit": implied,
            "basis": basis,
            "raw": message[3],
        })

    # A direct post and its aggregator relay often land one second apart (and
    # can straddle a fixed time bucket). Deduplicate on the claim identity and
    # a rolling 60-second distance instead.
    unique = []
    for row in sorted(claims, key=lambda r: r["event_time"]):
        identity = (row["entry_time"], row["symbol"], row["reported_exit"],
                    row["reported_pct"], row["profit_per_contract"],
                    row["event"])
        duplicate = any(
            identity == (old["entry_time"], old["symbol"],
                         old["reported_exit"], old["reported_pct"],
                         old["profit_per_contract"], old["event"])
            and abs(_clock(day, row["event_time"])
                    - _clock(day, old["event_time"])) <= 60
            for old in unique[-12:])
        if not duplicate:
            unique.append(row)
    claims = unique

    os.makedirs(OUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUT_DIR, "CALLER-OUTCOMES-%s.csv" % day)
    fields = ["entry_time", "event_time", "room", "caller", "symbol",
              "contract", "entry", "event", "reported_exit", "reported_pct",
              "profit_per_contract", "calculated_pct", "implied_exit", "raw"]
    fields.insert(-1, "basis")
    with open(csv_path + ".tmp", "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fields)
        writer.writeheader(); writer.writerows(claims)
    os.replace(csv_path + ".tmp", csv_path)

    md_path = os.path.join(OUT_DIR, "CALLER-OUTCOMES-%s.md" % day)
    lines = ["# Caller outcome evidence — %s" % day, "",
             "Caller claims are separate from broker results and ratchet simulations. Partial trims remain partial; percentages imply a price only when the caller's entry is known.", "",
             "| Entry | Event | Trader / room | Contract | Caller entry | Caller event | Exit/claim | Calculated | Evidence |",
             "|---|---|---|---|---:|---|---:|---:|---|"]
    for r in claims:
        claim = ("$%.2f" % r["reported_exit"] if r["reported_exit"] is not None
                 else ("%+.1f%%" % r["reported_pct"] if r["reported_pct"] is not None
                       else ("$%.0f/contract" % r["profit_per_contract"]
                             if r["profit_per_contract"] is not None
                             else "price unavailable")))
        calc = ("%+.1f%%" % r["calculated_pct"] if r["calculated_pct"] is not None
                else ("implied $%.2f" % r["implied_exit"]
                      if r["implied_exit"] is not None else "unavailable"))
        source = (r["caller"] or r["room"].split(": ")[-1] or "unknown")
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["entry_time"], r["event_time"], source.replace("|", "\\|"),
            r["contract"].replace("|", "\\|"),
            "$%.2f" % r["entry"] if r["entry"] is not None else "—",
            r["event"], claim, calc, r["basis"]))
    full = [r for r in claims if r["event"] == "full exit"]
    calculable_full = [r for r in full if r["calculated_pct"] is not None
                       or r["reported_pct"] is not None]
    lines += ["", "- Claim events paired: **%d**." % len(claims),
              "- Full exits recorded: **%d**; calculable: **%d**; price/percent unavailable: **%d**." %
              (len(full), len(calculable_full), len(full) - len(calculable_full)),
              "- Quantity-weighted caller P&L stays unavailable when trim size or the final runner exit is missing."]
    with open(md_path + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    os.replace(md_path + ".tmp", md_path)
    print(md_path)
    return md_path


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat())
