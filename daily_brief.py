#!/usr/bin/env python3
"""The one-screen daily brief — what happened today, in the order G reads it.

Six sections, phone-sized, numbers not adjectives:

  1 Day           broker export state, balance, bot net vs his hand net
  2 Bot trades    one line per bot round trip, with why it exited
  3 Callers       who was right, who was wrong, who can't be scored
  4 What broke    the day's REFUSED / POSTCHECK / STOP-WARN / reader faults
  5 Pending       only the items waiting on G
  6 footer        the files this was built from

Everything is read from records already on disk — master_ledger.csv,
master_broker.csv, today's daily-reports/*, trades.log (dated) and the
extension lane reports.  Nothing is estimated: a missing exit price, a missing
export or a missing report renders as "unavailable", never as a number.

`--post` uploads the brief to G's own Discord ("Sniper HQ") as a FILE through
the Fill Announcer's existing webhook (settings.json -> announcer.webhook_url);
a Discord message caps at 2000 characters and the brief does not, so the file
is the message and the content line is the one-glance summary.  No webhook, or
a webhook that refuses, never fails the run: the file is already written.

Called by daily_audit.py last, after every report it reads has been written.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import sys
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS = os.path.join(HERE, "daily-reports")
UNAVAILABLE = "unavailable"

# A hand trade is one the bot did not originate.  `manual` is the ledger's own
# flag; the other two tests catch the rows the broker export donates, which
# carry no room and say so in `why` (HANDOFF: "in the Webull order export, in
# no store — a hand trade").  His own trades are never graded, never stop-
# managed and never counted as the bot's.
HAND_CALLERS = {"gian", "manual", "you", ""}


# ---------------------------------------------------------------- small tools
def _num(value):
    """A float, or None.  Blank, '-', 'n/a' and junk are all None, never 0.0."""
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    if not text or text in {"-", "—", "?", "n/a", "na", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _truthy(value):
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _money(value):
    if value is None:
        return UNAVAILABLE
    sign = "-" if value < -0.005 else "+" if value > 0.005 else ""
    return "%s$%s" % (sign, ("%.2f" % abs(value)).rstrip("0").rstrip("."))


def _pct(value):
    if value is None:
        return UNAVAILABLE
    return "%+.1f%%" % value


def _clip(text, width):
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[: width - 1] + "…"


def _read_csv(path):
    """Rows as dicts, or None when the file is not there / unreadable."""
    import csv
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    except (OSError, UnicodeError, csv.Error):
        return None


def _read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


# ------------------------------------------------------------ 1. the day rows
def _is_hand(row):
    if _truthy(row.get("manual")):
        return True
    if (row.get("caller") or "").strip().lower() in HAND_CALLERS:
        return True
    why = (row.get("why") or "").lower()
    return "a hand trade" in why


def split_day(ledger, day):
    rows = [r for r in (ledger or []) if (r.get("date") or "").strip() == day]
    bot = [r for r in rows if not _is_hand(r)]
    hand = [r for r in rows if _is_hand(r)]
    return bot, hand


def _net(rows):
    """Realized dollars, and how many rows had no number to add."""
    total, blind = 0.0, 0
    for row in rows:
        value = _num(row.get("pl"))
        if value is None:
            blind += 1
        else:
            total += value
    return (None if blind == len(rows) else total), blind


def _contracts(rows):
    return sum(int(_num(r.get("qty")) or 0) for r in rows)


# --------------------------------------------------------- 2. why it exited
def exit_words(row):
    """The ledger's exit provenance in words G uses.

    `bot stop` / a resting stop that fired is the bot's own stop; whether it
    was still the stop BORN with the order or one the ratchet had already
    walked up is decided by where the stop sat at the exit: at or above the
    fill means the ratchet had moved it, below means it was still the born
    stop.  Nothing else in the row can tell those two apart.
    """
    exit_by = (row.get("exit_by") or "").strip().lower()
    why = (row.get("why") or "").strip().lower()
    blob = exit_by + " | " + why

    if "edit-close" in blob:
        return "edit-close"
    if "edit-be" in blob:
        return "edit-BE"
    if "pullback" in blob:
        return "pullback stock exit"
    if ("you at webull" in exit_by or "manual close" in exit_by
            or "you closed it yourself" in why
            or "didn't send this sell" in why or "a hand trade" in why):
        return "closed by hand"
    if "room call" in exit_by or "sold on their call" in why:
        return "close"

    stopped = ("stop" in blob or (row.get("state") or "").lower() == "stopped")
    if stopped:
        stop_at = _num(row.get("stop_at_exit"))
        entry = _num(row.get("avg_in")) or _num(row.get("fill"))
        exit_at = _num(row.get("exit_avg"))
        moved = None
        if stop_at is not None and entry is not None:
            moved = stop_at >= entry
        elif exit_at is not None and entry is not None:
            moved = exit_at >= entry
        if moved is True:
            return "BE stop" if _near(row) else "ratchet"
        if moved is False:
            return "born stop"
        return "ratchet" if "bot stop" in exit_by else "born stop"
    if (row.get("state") or "").lower() in {"closed", "filled"}:
        return "close"
    return UNAVAILABLE


def _near(row):
    """A stop parked exactly at the fill is a breakeven stop, not a ratchet."""
    stop_at = _num(row.get("stop_at_exit"))
    entry = _num(row.get("avg_in")) or _num(row.get("fill"))
    if stop_at is None or entry is None or entry == 0:
        return False
    return abs(stop_at - entry) / entry <= 0.005


def journal_disagrees(row):
    """True when the journal asserts an exit the broker record does not price.

    The 9/14 TSLA 357.5C is the case this exists for: state `stopped`,
    `why` "the resting stop at Webull sold it first", and no exit price and no
    P&L anywhere — the book believes something the account never confirmed.
    """
    state = (row.get("state") or "").strip().lower()
    exited = state in {"closed", "stopped"} or _truthy(row.get("all_out"))
    if not exited:
        return False
    if _num(row.get("exit_avg")) is None or _num(row.get("pl")) is None:
        return True
    book = _num(row.get("store_pl"))
    real = _num(row.get("pl"))
    return book is not None and real is not None and abs(book - real) >= 1.0


def _contract(row):
    strike = _num(row.get("strike"))
    strike = ("%g" % strike) if strike is not None else "?"
    side = "C" if (row.get("side") or "").upper().startswith("C") else "P"
    expiry = (row.get("expiry") or "").strip()
    if len(expiry) == 10:
        expiry = "%d/%d" % (int(expiry[5:7]), int(expiry[8:10]))
    return "%s%s %s" % (strike, side, expiry or "?")


# --------------------------------------------------------------- the sections
def section_day(day, bot, hand, broker):
    dated = [r for r in (broker or []) if (r.get("date") or "").strip() == day]
    if broker is None:
        export = "master_broker.csv unreadable"
    elif dated:
        export = "%d broker order legs" % len(dated)
    else:
        seen = sorted({(r.get("date") or "").strip() for r in broker} - {""})
        export = "broker export missing" + (
            " (last %s)" % seen[-1] if seen else "")

    bot_net, bot_blind = _net(bot)
    hand_net, hand_blind = _net(hand)
    ledger_rows = bot + hand
    day_net, _ = _net(ledger_rows)

    def side(label, rows, net, blind):
        if not rows:
            return "- %s: none" % label
        tail = "" if not blind else "  (%d with no P&L)" % blind
        return "- %s: %s · %d trade%s, %d contract%s%s" % (
            label, _money(net), len(rows), "" if len(rows) == 1 else "s",
            _contracts(rows), "" if _contracts(rows) == 1 else "s", tail)

    lines = ["## Day",
             "- Webull margin day P&L: %s" % export,
             "- Balance: %s — no balance snapshot is kept on disk" % UNAVAILABLE,
             side("Bot", bot, bot_net, bot_blind),
             side("Hand (G)", hand, hand_net, hand_blind),
             "- Ledger day total: %s" % _money(day_net)]
    return "\n".join(lines), bot_net, hand_net


def section_bot_trades(bot):
    if not bot:
        return "## Bot trades\nNo bot trades on this date."
    fmt = "%-5s  %-18s  %-15s  %-5s  %-12s  %5s  %5s  %7s  %s"
    head = fmt % ("time", "channel", "trader", "tkr", "contract",
                  "in", "out", "$", "why exited")
    out = ["## Bot trades", "```", head, "-" * len(head)]
    flagged = 0
    for row in sorted(bot, key=lambda r: (r.get("opened") or "~")):
        entry = _num(row.get("avg_in")) or _num(row.get("fill"))
        exit_at = _num(row.get("exit_avg"))
        dollars = _num(row.get("pl"))
        why = exit_words(row)
        if journal_disagrees(row):
            why += "  ⚠ journal ≠ broker"
            flagged += 1
        out.append(fmt % ((row.get("opened") or "--:--")[:5],
                          _clip(row.get("room"), 18),
                          _clip(row.get("caller") or row.get("room"), 15),
                          _clip(row.get("symbol"), 5),
                          _clip(_contract(row), 12),
                          ("%.2f" % entry) if entry is not None else "?",
                          ("%.2f" % exit_at) if exit_at is not None else "?",
                          _money(dollars) if dollars is not None else "?",
                          why))
    out.append("```")
    if flagged:
        out.append("⚠ %d row%s: the journal says it exited, the broker record "
                   "prices no exit." % (flagged, "" if flagged == 1 else "s"))
    return "\n".join(out)


# ------------------------------------------------------------- 3. the callers
def _scored(row):
    """The caller's own posted result for this event, or None.

    A percentage they typed counts.  A price the report priced against the
    contemporaneous bid counts.  A stock price where a premium belongs, and an
    exit with no price at all, do not — those are never estimated.
    """
    basis = (row.get("basis") or "").lower()
    if "stock price" in basis:
        return None
    value = _num(row.get("calculated_pct"))
    if value is None:
        value = _num(row.get("reported_pct"))
    if value is None:
        return None
    if _num(row.get("entry")) is None:
        return None
    return value


def section_callers(day, bot):
    csv_path = os.path.join(REPORTS, "CALLER-OUTCOMES-%s.csv" % day)
    rows = _read_csv(csv_path)
    if rows is None:
        return "\n".join(["## Callers right / wrong",
                          "CALLER-OUTCOMES-%s.csv %s." % (day, UNAVAILABLE),
                          _ratchet_line(day) or ""]).rstrip()

    claims = {}
    for row in rows:
        basis = (row.get("basis") or "").lower()
        if "stock price" in basis:            # excluded from every total
            continue
        name = (row.get("caller") or "").strip() or _room_name(row.get("room"))
        key = (name or "?", (row.get("contract") or "?").strip())
        slot = claims.setdefault(key, {"pct": None, "when": "", "kind": ""})
        value = _scored(row)
        if value is not None and (row.get("event_time") or "") >= slot["when"]:
            slot.update(pct=value, when=row.get("event_time") or "",
                        kind="full" if "full" in (row.get("event") or "")
                             else "trim")

    right, wrong, unscored = [], [], []
    for (caller, contract), slot in sorted(claims.items(),
                                           key=lambda kv: kv[0][0].lower()):
        if slot["pct"] is None:
            unscored.append("%s %s" % (caller, contract.split(" @")[0]))
            continue
        line = "- %s %s %s (%s) — %s" % (
            caller, _clip(contract.split(" @")[0], 22), _pct(slot["pct"]),
            slot["kind"], _bot_took(caller, contract, bot))
        (right if slot["pct"] > 0 else wrong).append(line)

    out = ["## Callers right / wrong", "**Right**"]
    out += right or ["- none scored"]
    out.append("**Wrong**")
    out += wrong or ["- none scored"]
    seen = sorted(set(unscored), key=str.lower)
    out.append("unscored (no exit price — never estimated): %s"
               % (", ".join(seen) if seen else "none"))
    ratchet = _ratchet_line(day)
    if ratchet:
        out.append(ratchet)
    return "\n".join(out)


def _room_name(room):
    """The room's short half, for the rows the outcomes report leaves
    caller-less (a relay footer named the room, not the trader)."""
    return _clip((room or "").split(":")[-1].strip(), 24)


def _bot_took(caller, contract, bot):
    """Did the bot trade this caller's ticker, and what did it get?"""
    symbol = (contract.split() or [""])[0].upper()
    for row in bot:
        same_caller = (row.get("caller") or "").strip().lower() \
            in {caller.lower(), caller.lower().replace(" (mod)", "")}
        if same_caller and (row.get("symbol") or "").upper() == symbol:
            ours = _contract(row)
            got = _money(_num(row.get("pl")))
            if ours.split()[0] not in contract:
                return "bot took %s %s: %s" % (symbol, ours, got)
            return "bot took it: %s" % got
    return "bot: no"


def _ratchet_line(day):
    text = _read_text(os.path.join(REPORTS, "CALLER-VS-RATCHET-%s.md" % day))
    if text is None:
        return "ratchet replay: %s (CALLER-VS-RATCHET-%s.md missing)" % (
            UNAVAILABLE, day)
    match = re.search(r"Our ratchet on the \*\*(\d+) paths? with a caller-"
                      r"posted entry\*\*: \*\*([+\-−]?[\d,]+)", text)
    if not match:
        return None
    return "ratchet on those %s caller-priced paths: %s per 1-contract replay" \
        % (match.group(1), match.group(2).replace("−", "-"))


# ------------------------------------------------------------ 4. what broke
BROKE_TAGS = [
    ("REFUSED", lambda tag, body: tag == "REFUSED"),
    ("POSTCHECK PROBLEM", lambda tag, body: tag == "POSTCHECK"
     and "PROBLEM" in body),
    ("STOP-WARN", lambda tag, body: tag == "STOP-WARN"),
    ("EXPIRY", lambda tag, body: tag == "EXPIRY"),
    ("EDITED", lambda tag, body: tag == "EDITED"),
    ("MIRROR", lambda tag, body: tag == "MIRROR"),
    ("IMG READ", lambda tag, body: tag == "IMG"
     and re.search(r"couldn't read|HTTP \d|error", body, re.I) is not None),
    ("AI READ", lambda tag, body: tag == "AI READ"
     and re.search(r"HTTP \d|error|timeout|failed", body, re.I) is not None),
]


def _tag_of(body):
    head = body.split("  ")[0].strip() if "  " in body else body.split(" ")[0]
    return head.strip()


def section_broke(day):
    """trades.log is dated, so the day's faults are read from it, not from
    bridge.log — bridge.log has no dates and carries raw broker payloads."""
    found = {label: [] for label, _ in BROKE_TAGS}
    path = os.path.join(HERE, "trades.log")
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.startswith(day):
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 2:
                    continue
                body = parts[1]
                tag = _tag_of(body)
                for label, test in BROKE_TAGS:
                    if test(tag, body):
                        found[label].append(body)
                        break
    except OSError:
        return "## What broke\ntrades.log %s." % UNAVAILABLE

    lines = []
    for label, _ in BROKE_TAGS:
        hits = found[label]
        if hits:
            lines.append("- %s %d — %s" % (label, len(hits),
                                           _clip(_strip_label(label, hits[0]),
                                                 120)))
    mirror = _mirror_fault(day)
    if mirror:
        lines.append(mirror)
    lines += _lane_faults()
    if not lines:
        return "## What broke\nnothing broke"
    return "\n".join(["## What broke"] + lines)


def _strip_label(label, body):
    """Drop the log tag from the front so the line reads as the fault itself.
    POSTCHECK keeps its subject ("FILLED TSLA — PROBLEM: …") — that is the
    useful half."""
    for prefix in (label, label.split()[0], _tag_of(body)):
        if body.upper().startswith(prefix.upper()):
            return body[len(prefix):].strip(" :-")
    return body.strip()


def _mirror_fault(day):
    text = _read_text(os.path.join(REPORTS, "FUTURES-MIRROR-%s.md" % day))
    if text is None:
        return None
    match = re.search(r"\*\*bars: unavailable\*\*\s*—\s*(.+)", text)
    if not match:
        return None
    scored = re.search(r"(\d+) SPY/QQQ alert", text)
    return "- MIRROR — bars unavailable, %s alert(s) unscored: %s" % (
        scored.group(1) if scored else "?", _clip(match.group(1), 90))


def _lane_faults():
    lines = []
    for path in sorted(glob.glob(os.path.join(HERE, "department-reports",
                                              "extension-*.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                report = json.load(fh)
        except (OSError, ValueError):
            continue
        issues = [i for i in (report.get("issues") or []) if i]
        if issues:
            lines.append("- LANE %s %d — %s" % (report.get("lane", "?"),
                                                len(issues),
                                                _clip("; ".join(issues), 120)))
    return lines


# --------------------------------------------------------------- 5. pending
def section_pending():
    text = _read_text(os.path.join(HERE, "HANDOFF.md"))
    if text is None:
        return "## Pending (G's action)\nHANDOFF.md %s." % UNAVAILABLE
    block = re.search(r"^## Pending[^\n]*\n(.*?)(?=^## |\Z)", text,
                      re.S | re.M)
    if not block:
        return "## Pending (G's action)\nno Pending section in HANDOFF.md."
    items, current = [], ""
    for line in block.group(1).splitlines():
        if re.match(r"^\s*\d+\.\s", line):
            if current:
                items.append(current)
            current = re.sub(r"^\s*\d+\.\s*", "", line)
        elif current and line.strip():
            current += " " + line.strip()
    if current:
        items.append(current)

    out = []
    for item in items:
        item = re.sub(r"\((?:[^()]*\bDONE\b[^()]*)\)", "", item)
        item = " ".join(item.split())
        if not item or item.lower().startswith("done"):
            continue
        out.append("- " + _clip(item, 110))
        if len(out) == 6:
            break
    if not out:
        return "## Pending (G's action)\nnothing waiting on you."
    return "\n".join(["## Pending (G's action)"] + out)


# ----------------------------------------------------------------- assembly
def build(day):
    ledger = _read_csv(os.path.join(HERE, "master_ledger.csv"))
    broker = _read_csv(os.path.join(HERE, "master_broker.csv"))
    bot, hand = split_day(ledger, day)

    day_block, bot_net, hand_net = section_day(day, bot, hand, broker)
    broke = section_broke(day)
    blocks = [day_block, section_bot_trades(bot), section_callers(day, bot),
              broke, section_pending()]

    sources = ["master_ledger.csv", "master_broker.csv", "trades.log",
               "daily-reports/CALLER-OUTCOMES-%s.csv" % day,
               "daily-reports/CALLER-VS-RATCHET-%s.md" % day,
               "daily-reports/FUTURES-MIRROR-%s.md" % day,
               "department-reports/extension-*.json", "HANDOFF.md"]
    stamp = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    footer = "built from %s · %s" % (", ".join(sources), stamp)

    faults = len([line for line in broke.splitlines()
                  if line.startswith("- ")])
    summary = ("%s — day %s · bot %d trade%s %s · hand %d trade%s %s · "
               "%d thing%s broke"
               % (_short(day), _day_headline(day, broker),
                  len(bot), "" if len(bot) == 1 else "s", _money(bot_net),
                  len(hand), "" if len(hand) == 1 else "s", _money(hand_net),
                  faults, "" if faults == 1 else "s"))

    text = "\n\n".join(["# SNIPER BRIEF — %s" % day] + blocks + [footer]) + "\n"
    return text, summary


def _day_headline(day, broker):
    dated = [r for r in (broker or []) if (r.get("date") or "").strip() == day]
    return "%d broker legs" % len(dated) if dated else "broker export missing"


def _short(day):
    try:
        parsed = dt.date.fromisoformat(day)
        return "%d/%d" % (parsed.month, parsed.day)
    except ValueError:
        return day


# ------------------------------------------------------------------- Discord
def _webhook():
    """The Fill Announcer's existing options webhook. Never logged, never
    printed, never copied anywhere else."""
    try:
        with open(os.path.join(HERE, "settings.json"), encoding="utf-8") as fh:
            config = json.load(fh)
    except (OSError, ValueError):
        return ""
    url = ((config.get("announcer") or {}).get("webhook_url") or "").strip()
    return url if url.startswith("https://discord.com/api/webhooks/") else ""


def post(day, text, summary, opener=urllib.request.urlopen):
    """Upload the brief as BRIEF-<date>.md. Returns the HTTP status, or None
    when there is no webhook to post to. Never raises."""
    url = _webhook()
    if not url:
        return None
    boundary = "----sniper" + uuid.uuid4().hex
    payload = json.dumps({"content": summary[:1900],
                          "username": "Fill Announcer"})
    parts = [
        ("--%s\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
         "Content-Type: application/json\r\n\r\n%s\r\n" % (boundary, payload)
         ).encode("utf-8"),
        ("--%s\r\nContent-Disposition: form-data; name=\"files[0]\"; "
         "filename=\"BRIEF-%s.md\"\r\nContent-Type: text/markdown\r\n\r\n"
         % (boundary, day)).encode("utf-8"),
        text.encode("utf-8"),
        ("\r\n--%s--\r\n" % boundary).encode("utf-8"),
    ]
    request = urllib.request.Request(
        url, data=b"".join(parts),
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary,
                 "User-Agent": "Mozilla/5.0 (SniperBrief/1.0)"})
    try:
        with opener(request, timeout=20) as response:
            return getattr(response, "status", None) or response.getcode()
    except Exception as error:                              # noqa: BLE001
        return getattr(error, "code", None) or str(error)[:80]


def main(day=None, do_post=False):
    day = day or dt.date.today().isoformat()
    text, summary = build(day)
    os.makedirs(REPORTS, exist_ok=True)
    path = os.path.join(REPORTS, "BRIEF-%s.md" % day)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)
    print(text)
    print(path)
    if do_post:
        status = post(day, text, summary)
        if status is None:
            print("BRIEF not posted — no announcer webhook in settings.json; "
                  "the file is written.")
        else:
            print("BRIEF posted to Sniper HQ — HTTP %s" % status)
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--post"]
    raise SystemExit(main(args[0] if args else None, "--post" in sys.argv[1:]))
