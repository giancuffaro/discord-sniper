#!/usr/bin/env python3
"""One readable daily operating and performance report.

Combines the reader export, extension decisions, master alert ledger, master
trade ledger and post-mortems. Counts are deduplicated by contract/action so a
direct-room post and its relay remain one alert.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import subprocess
from collections import Counter, defaultdict

import replay_check

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "daily-reports")


def _read_csv(name, day):
    try:
        with open(os.path.join(HERE, name), encoding="utf-8-sig", newline="") as fh:
            return [r for r in csv.DictReader(fh) if r.get("date") == day]
    except OSError:
        return []


def _on_rooms():
    discord = whop = 0
    try:
        with open(os.path.join(HERE, "extension", "rooms.txt"), encoding="utf-8") as fh:
            for line in fh:
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                p = [x.strip() for x in line.split("|")]
                if len(p) >= 5 and p[4].lower() == "on":
                    if "whop.com" in p[1]:
                        whop += 1
                    else:
                        discord += 1
    except OSError:
        pass
    return discord, whop


def _active_channel_ids():
    """Stable IDs/paths for rooms the extension is meant to operate."""
    out = set()
    try:
        with open(os.path.join(HERE, "extension", "rooms.txt"), encoding="utf-8") as fh:
            for line in fh:
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                p = [x.strip() for x in line.split("|")]
                if len(p) < 5 or p[4].lower() != "on":
                    continue
                out.add(p[0])
                if "whop.com/" in p[1]:
                    path = re.sub(r"^https?://whop\.com", "whop:", p[1])
                    out.add(path.rstrip("/"))
    except OSError:
        pass
    return out


def _discord_room_urls():
    """Map a watched Discord channel ID to its canonical Discord URL."""
    out = {}
    try:
        with open(os.path.join(HERE, "extension", "rooms.txt"), encoding="utf-8") as fh:
            for line in fh:
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                p = [x.strip() for x in line.split("|")]
                if len(p) >= 2 and re.match(r"^https://discord\.com/channels/\d+/\d+$", p[1]):
                    out[p[0]] = p[1]
    except OSError:
        pass
    return out


def _source_message_url(channel_id, message_id):
    """Return a Discord deep link only for a retained, verified source ID."""
    message_id = str(message_id or "")
    # Discord's DOM labels a row ``chat-messages-<channel>-<message>``.  The
    # final snowflake is the URL's message ID; accepting that exact wrapper is
    # safe and keeps captured DOM IDs useful without guessing from text.
    wrapped = re.fullmatch(r"chat-messages-\d+-(\d+)", message_id)
    if wrapped:
        message_id = wrapped.group(1)
    base = _discord_room_urls().get(str(channel_id or ""))
    if not base or not re.fullmatch(r"\d+", message_id):
        return ""
    guild, channel = re.fullmatch(r"https://discord\.com/channels/(\d+)/(\d+)", base).groups()
    # Clicking this route opens the post in Discord's Chrome Profile 2. A
    # normal Markdown URL remains inside Codex's integrated browser.
    return "http://127.0.0.1:8787/open-discord/%s/%s/%s" % (guild, channel, message_id)


def _source_body(text):
    """The exact captured message copied into an extension verdict, if any."""
    if " | " not in str(text or ""):
        return ""
    return re.sub(r"\s+", " ", str(text).rsplit(" | ", 1)[1]).strip()


def _clock_seconds(clock):
    h, m, s = (int(v) for v in clock.split(":"))
    return h * 3600 + m * 60 + s


def _corrected_non_alert(text):
    low = text.lower()
    return (bool(re.search(r"\bsick\b.*\d+(?:\.\d+)?\s*/\s*con.*\bon\b", low))
            or bool(re.search(r"\bleft\s+(?:a|one|\d+)\s+runner", low))
            or bool(re.search(r"\d+(?:\.\d+)?\s*[kmb]\s+on\s+flow", low)))


def _reportable_channel(channel_id, active_channels=None):
    """Keep personal Whop pages and direct messages out of an ops report.

    They are retained in raw capture for evidence, but neither represents a
    monitored room nor belongs in reader coverage.  Showing a participant's
    handle as a room made the report look like an unknown caller was watched.
    """
    channel_id = str(channel_id or "").lower()
    if channel_id == "whop:/messages" or channel_id.startswith("whop:/@"):
        return False
    return active_channels is None or channel_id in active_channels


def _decision_rows(day):
    rank = {"ignored": 0, "skipped": 1, "failed": 2, "sent": 3}
    rows = {}
    messages = {}
    active_channels = _active_channel_ids()
    for fn in replay_check.exports_for_day(day):
        lane_msgs, dids = replay_check.load(fn)
        for message in lane_msgs:
            t, room, cid, text = message
            if not _reportable_channel(cid, active_channels):
                continue
            key = (t, cid, text[:100])
            prior = messages.get(key)
            # A legacy capture and an ID-bearing re-capture can describe the
            # same displayed row.  Never let the legacy copy overwrite the
            # source ID needed for an auditable Discord link.
            if prior and getattr(prior, "message_id", "") and not getattr(message, "message_id", ""):
                continue
            messages[key] = message
        for t, kind, text in dids:
            if kind not in rank:
                continue
            # Swing decisions carry a display tag before OPEN. They are still
            # entry alerts and must count in the funnel (IBM 9/11).
            m = re.match(r"^(?:\([^)]*\)\s*)?(OPEN|ADD)\s+(.+?)(?:\s+x\d+(?:\.\d+)?)?\s+—", text)
            if not m:
                continue
            if _corrected_non_alert(text):
                continue
            contract = re.sub(r"\s+x\d+(?:\.\d+)?$", "", m.group(2)).strip()
            key = (m.group(1), contract)
            row = {"time": t, "action": m.group(1), "contract": contract,
                   "kind": kind, "text": text}
            if key not in rows or rank[kind] > rank[rows[key]["kind"]]:
                rows[key] = row
    # Verdict rows preserve the original ``author: message`` after `` | ``.
    # Match that literal evidence back to one captured source row.  A link is
    # emitted only for an exact message match; repeated text is resolved by
    # nearest timestamp and a tie stays unavailable rather than guessing.
    for row in rows.values():
        source = _source_body(row["text"])
        if not source:
            row["source_url"] = ""
            continue
        candidates = [m for m in messages.values()
                      if getattr(m, "message_id", "")
                      and re.sub(r"\s+", " ", m[3]).strip() == source]
        if not candidates:
            row["source_url"] = ""
            continue
        candidates.sort(key=lambda m: abs(_clock_seconds(m[0]) - _clock_seconds(row["time"])))
        nearest = candidates[0]
        if (len(candidates) > 1 and
                abs(_clock_seconds(candidates[1][0]) - _clock_seconds(row["time"])) ==
                abs(_clock_seconds(nearest[0]) - _clock_seconds(row["time"]))):
            row["source_url"] = ""
        else:
            row["source_url"] = _source_message_url(nearest[2], nearest.message_id)
    return list(messages.values()), sorted(rows.values(), key=lambda r: r["time"])


def _reason(row):
    low = row["text"].lower()
    if row["kind"] == "sent":
        return "order sent"
    if "protective stop is not operational" in low:
        return "futures protective exit not operational; no order sent"
    if "new option trades are only allowed" in low:
        return "options entry window closed; no order"
    if "pullback trigger expired" in low:
        return "pullback expired; no order"
    if "too stale" in low:
        age = re.search(r"that call is\s+(\d+)\s+seconds old", low)
        return ("stale when received (%ss old; 20s Discord limit)" % age.group(1)
                if age else "stale when read")
    if "costs $" in low or "buying power" in low:
        return "buying-power safety; no order"
    if "expiry" in low and "expired" in low:
        return "contract expiry already passed; no order"
    if "too thin" in low:
        return "liquidity floor"
    if "spread" in low:
        return "spread too wide"
    if "swing trades are paused" in low:
        return "swing paused"
    if "topstep" in low or "futures broker" in low:
        return "futures unavailable"
    if "same contract" in low or "another relay" in low:
        return "duplicate/repost"
    return row["kind"]


def _caller_room(row):
    """Extract the display attribution preserved in the bridge decision line."""
    first = str(row.get("text") or "").split(" | ", 1)[0]
    parts = first.split(" — ")
    if len(parts) < 2:
        return "unavailable", "unavailable"
    source = parts[1].strip()
    # A stale refusal leads with its age, then preserves the original author
    # after ``|``.  Prefer that author over the guard message.
    if source.lower().startswith(("that call is", "it's ")):
        original = str(row.get("text") or "").split(" | ", 1)
        if len(original) == 2:
            author = original[1].split(":", 1)[0].strip()
            return author or "unavailable", "unavailable"
    if " · " not in source:
        return source or "unavailable", "unavailable"
    caller, room = source.split(" · ", 1)
    return caller.strip() or "unavailable", room.strip() or "unavailable"


def _recovered(day):
    path = os.path.join(HERE, "daily-audits", "recovered-%s.json" % day)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"entries": [], "adds": [], "note": ""}


def _finalize_deferred(day, decisions):
    """Turn accepted pullback waits into their final same-day outcome.

    The extension calls a request ``sent`` once the bridge accepts it.  A
    pullback request can then wait without submitting a broker order and
    expire ten minutes later.  Counting that as an order inflated the daily
    taken count (QQQ on 9/11).  trades.log is the durable final authority.
    """
    expired = set()
    try:
        with open(os.path.join(HERE, "trades.log"), encoding="utf-8",
                  errors="replace") as fh:
            for line in fh:
                if not line.startswith(day):
                    continue
                m = re.search(r"PULLBACK\s+([A-Z][A-Z0-9.]*): never touched", line)
                if m:
                    expired.add(m.group(1))
    except OSError:
        pass
    for row in decisions:
        symbol = row["contract"].split(None, 1)[0].upper()
        if row["kind"] == "sent" and symbol in expired:
            row["kind"] = "skipped"
            row["text"] += " — pullback trigger expired without a broker order"
    return decisions


def build(day):
    os.makedirs(OUT_DIR, exist_ok=True)
    messages, decisions = _decision_rows(day)
    decisions = _finalize_deferred(day, decisions)
    ledger = [r for r in _read_csv("master_ledger.csv", day)
              if (r.get("account") == "live"
                  and str(r.get("manual") or "").lower() not in ("true", "1"))]
    post = _read_csv("master_postmortems.csv", day)
    recovered = _recovered(day)
    d_rooms, w_rooms = _on_rooms()
    speaking = Counter(r[1] for r in messages)

    sent = [r for r in decisions if r["kind"] == "sent"]
    refused = [r for r in decisions if r["kind"] == "failed"]
    stale = [r for r in decisions if r["kind"] == "skipped"
             and _reason(r) == "stale when read"]
    other_skips = [r for r in decisions if r["kind"] in ("skipped", "ignored")
                   and _reason(r) != "stale when read"]
    wins = [r for r in ledger if float(r.get("pl") or 0) > 0]
    losses = [r for r in ledger if float(r.get("pl") or 0) < 0]
    flats = [r for r in ledger if float(r.get("pl") or 0) == 0]
    pnl = sum(float(r.get("pl") or 0) for r in ledger)
    recovered_entries = recovered.get("entries") or []
    recovered_adds = recovered.get("adds") or []
    decided_entries = [r for r in decisions if r["action"] == "OPEN"]
    observed_entries = len(decided_entries) + len(recovered_entries)
    not_taken_after_review = len([r for r in decided_entries
                                  if r["kind"] != "sent"])

    lines = ["# Daily Sniper Report — %s" % day, "",
             "Generated %s." % dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"), "",
             "## Coverage", "",
             "- Rooms configured on: **%d** Discord and **%d** Whop." % (d_rooms, w_rooms),
             "- Rooms/channels with a live parser input today: **%d**." % len(speaking),
             "- Live parser inputs retained: **%d** messages." % len(messages),
             "- Rooms with no message are quiet or unverified; the report does not call them healthy solely from silence.", "",
             "## Alert flow", "",
             "| Measure | Count |", "|---|---:|",
             "| Unique entry alerts observed (normal + recovered) | %d |" % observed_entries,
             "| Entry alerts read and given a decision | %d |" % len(decided_entries),
             "| Broker entry orders submitted | %d |" % len(sent),
             "| Read but not taken | %d |" % not_taken_after_review,
             "| Broker/risk refusals | %d |" % len(refused),
             "| Stale when first read | %d |" % len(stale),
             "| Duplicate or other skips | %d |" % len(other_skips),
             "| Recovered entry gaps | %d |" % len(recovered_entries),
             "| Recovered add gaps | %d |" % len(recovered_adds),
             "| Actual fills in master ledger | %d |" % len(ledger), "",
             "## Actual results", "",
             "- Bot trades: **%d** — %d win, %d loss, %d flat." %
             (len(ledger), len(wins), len(losses), len(flats)),
             "- Realized P&L: **%+.2f**." % pnl]
    for r in ledger:
        lines.append("- %s %s%s %s: %s → %s, **%+.2f** (%s)." % (
            r.get("caller") or "?", r.get("symbol") or "?",
            (" " + r.get("strike", "") + (r.get("side") or "")[:1])
            if r.get("strike") else "", r.get("expiry") or "",
            r.get("avg_in") or "?", r.get("exit_avg") or "?",
            float(r.get("pl") or 0), r.get("exit_by") or r.get("state") or ""))

    lines += ["", "## Entry and exit comparison", ""]
    if post:
        for r in post:
            lines.append("- %s: caller entry %s, bot fill %s (%s%% difference); "
                         "bot exit %s, P&L %s, verdict **%s**. %s" % (
                r.get("symbol") or "?", r.get("their_price") or "unavailable",
                r.get("fill") or "?", r.get("fill_vs_theirs_pct") or "n.a.",
                r.get("exit") or "?", r.get("pl") or "?",
                r.get("verdict") or "unavailable", r.get("lesson") or ""))
    else:
        lines.append("- No filled trade has enough tape for a comparison yet.")
    lines.append("- Exact caller-entry/caller-exit P&L is reported only when both messages and a contemporaneous contract quote exist. Missing exits remain **unavailable**; they are never estimated from a later high or a stale quote.")
    lines.append("- Refused or missed alerts stay outcome-pending until a caller exit can be paired to the recorded contract tape; a later high alone is not labeled a win.")
    if post:
        lines.append("- A system-versus-caller verdict needs matched trades on both sides. %d bot trade%s displayed, but %s not enough evidence to call either method better." %
                     (len(post), " is" if len(post) == 1 else "s are",
                      "it is" if len(post) == 1 else "they are"))
    else:
        lines.append("- No matched trade is available for a system-versus-caller verdict.")

    lines += ["", "## Every recognized decision", "",
              "| Time | Caller | Room | Alert | Result | Reason | Source message |",
              "|---|---|---|---|---|---|---|"]
    for r in decisions:
        caller, room = _caller_room(r)
        source = "[Open in Chrome](%s)" % r["source_url"] if r.get("source_url") else "unavailable"
        lines.append("| %s | %s | %s | %s %s | %s | %s | %s |" %
                     (r["time"], caller.replace("|", "\\|"), room.replace("|", "\\|"),
                      r["action"], r["contract"], r["kind"], _reason(r), source))
    if recovered_entries or recovered_adds:
        lines += ["", "## Recovered gaps", ""]
        for r in recovered_entries + recovered_adds:
            lines.append("- %s %s — %s (%s)." %
                         (r.get("time", "?"), r.get("alert", "?"),
                          r.get("why", "no normal verdict"),
                          r.get("class", "review")))
        if recovered.get("note"):
            lines.append("- " + recovered["note"])

    lines += ["", "## Room activity", "",
              "| Room/channel | Parser inputs |", "|---|---:|"]
    for room, count in speaking.most_common():
        lines.append("| %s | %d |" % (room.replace("|", "\\|"), count))

    lines += ["", "## Detailed benchmarks", "",
              "- [Caller entry, trim, and exit evidence](CALLER-OUTCOMES-%s.md)" % day,
              "- [Caller original entry versus our ratchet](CALLER-VS-RATCHET-%s.md)" % day,
              "- [Fixed stop versus live ratchet replay](RATCHET-COMPARE-%s.md)" % day]

    out = os.path.join(OUT_DIR, "REPORT-%s.md" % day)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    os.replace(tmp, out)
    print(out)
    return out


if __name__ == "__main__":
    import eastern
    build(eastern.day_arg())
