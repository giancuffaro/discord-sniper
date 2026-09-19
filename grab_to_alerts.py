#!/usr/bin/env python3
"""grab_to_alerts.py — every ROOM HISTORY GRAB in DS Logs, read by the
PRODUCTION parser (extension/parse_batch.js), into grab_alerts.csv: one row
per ENTRY the bot would have fired, with the caller's own price. The futures
mirror and the reference replays read this beside recovered_alerts_chat.csv.

G, 9/19: a year of Vero / Midas / ... history to replay under the level shape.
Grab timestamps are UTC to the minute (reader_history.GRAB_ROW); written here
in ET. Nothing here trades; it is a record."""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reader_history                                   # noqa: E402

ET = ZoneInfo("America/New_York")
OUT = os.path.join(HERE, "grab_alerts.csv")
HEAD = ["date", "time", "channel_id", "room", "caller", "symbol", "side", "strike",
        "expiry", "their_price", "action", "kind", "source_file", "line", "text"]


def grabs():
    rooms, _ = reader_history.room_list(HERE)
    for f in sorted(os.listdir(os.path.join(HERE, "DS Logs"))):
        if not (f.startswith("grab ") and f.endswith(".txt")):
            continue
        data = open(os.path.join(HERE, "DS Logs", f), encoding="utf-8", errors="replace").read()
        cid = re.search(r"^channel_id: (.+)$", data, re.M)
        if not cid:
            continue
        cid = cid[1].strip()
        room = rooms.get(cid, {}).get("room") or (re.search(r"^room: (.*)$", data, re.M) or [None, cid])[1]
        pending = None
        for n, line in enumerate(data.splitlines(), 1):
            m = reader_history.GRAB_ROW.match(line)
            if m:
                if pending:
                    yield f, cid, room, pending
                pending = [m[1], m[2], n]
            elif pending:
                pending[1] += "\n" + line
        if pending:
            yield f, cid, room, pending


def main():
    msgs = list(grabs())
    texts = []
    for f, cid, room, (stamp, body, n) in msgs:
        body = re.sub(r"^\[message_id=[^\]]+\]\s*", "", body)
        author, text = reader_history.split_author(body)
        text = re.sub(r"\s+", " ", reader_history.DOM_PREFIX.sub("", text)).strip()
        texts.append((f, cid, room, stamp, n, author, text))
    res = subprocess.run(["node", os.path.join(HERE, "extension", "parse_batch.js"), "--json"],
                         input=json.dumps([t[-1] for t in texts]), capture_output=True, text=True, encoding="utf-8")
    parsed = json.loads(res.stdout)
    seen = set()
    rows = []
    for (f, cid, room, stamp, n, author, text), p in zip(texts, parsed):
        if not p or p.get("action") != "OPEN" or not p.get("symbol"):
            continue
        when = dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc).astimezone(ET)
        key = (cid, when.strftime("%Y-%m-%d %H:%M"), p["symbol"], p.get("side"), p.get("strike"))
        if key in seen:
            continue
        seen.add(key)
        rows.append([when.strftime("%Y-%m-%d"), when.strftime("%H:%M:%S"), cid, room, author, p["symbol"],
                     p.get("side") or "", p.get("strike") or "", p.get("expiry") or "", p.get("limit") or "",
                     p.get("action"), p.get("kind") or "option", f, n, text[:200]])
    rows.sort()
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEAD)
        w.writerows(rows)
    by = {}
    for r in rows:
        by[r[3]] = by.get(r[3], 0) + 1
    print("%d messages -> %d entries -> %s" % (len(texts), len(rows), OUT))
    for k, v in sorted(by.items(), key=lambda kv: -kv[1]):
        print("  %-30s %d" % (k, v))
    idx = [r for r in rows if r[5] in ("SPY", "QQQ", "SPX", "SPXW")]
    print("index entries:", len(idx), "from", idx[0][0] if idx else "-", "to", idx[-1][0] if idx else "-")


if __name__ == "__main__":
    main()
