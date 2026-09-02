"""ROOM SCOREBOARD (9/2/26, G: "who has and hasn't signaled, make me a scoreboard").

Reads what's already on disk — no network, no broker:
  * DS Logs/signal-room-chat *.txt   — the extension's self-learning exports:
        every message the reader saw ([Server: channel #id]) and every verdict
        (<sent>/<skipped>/<ignored>) with the room on it
  * days/*.json                      — the bridge's trade table (who, room, P&L,
        exit_by, hi/lo %)
  * extension/rooms.txt              — the configured rooms (so a room that never
        said a word still shows up, as SILENT)

Writes SCOREBOARD.html next to this file. Run:  python scoreboard.py [days]
(default: last 10 calendar days). Safe to run any time; nothing is modified.
"""
import glob
import html
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DAYS_BACK = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 10
SINCE = date.today() - timedelta(days=DAYS_BACK)

RE_MSG = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})  \[(.*?) #(\d+)\]  (.*)$")
RE_DID = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})  <(\w+)>  (.*)$")
# a message that names a contract: "SPY 645C", "$57 calls", "255P 9/4", "NVDA 225 call"
RE_CONTRACT = re.compile(r"\b[A-Z]{1,5}\b[^\n]{0,40}?\$?\d{1,5}(?:\.\d+)?\s*(?:[CP]\b|calls?\b|puts?\b)", re.I)
RE_ENTRY = re.compile(r"\b(bto|buy|bought|entry|entering|in\b|added|adding|long|lotto|scalp|swing)\b", re.I)
RE_EXIT = re.compile(r"\b(all out|out of|sold|sell|close[d]?|trim|trimm|stc|exit|took profit|stopped)\b", re.I)


def load_rooms():
    rooms = {}
    p = os.path.join(HERE, "extension", "rooms.txt")
    try:
        with open(p, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                parts = ln.split("|")
                if len(parts) >= 4:
                    rooms[parts[0]] = {"label": parts[2], "group": parts[3], "url": parts[1]}
    except OSError:
        pass
    return rooms


def load_exports():
    """Every message + verdict across all exports, de-duplicated."""
    msgs, dids = {}, {}
    for fn in sorted(glob.glob(os.path.join(HERE, "DS Logs", "signal-room-chat*.txt"))):
        section = None
        try:
            with open(fn, encoding="utf-8", errors="replace") as f:
                for ln in f:
                    ln = ln.rstrip("\n")
                    if ln.startswith("=== RAW MESSAGES"):
                        section = "msg"
                        continue
                    if ln.startswith("=== WHAT THE BOT DID"):
                        section = "did"
                        continue
                    if section == "msg":
                        m = RE_MSG.match(ln)
                        if m:
                            d, t, room, cid, text = m.groups()
                            msgs[(d, t, cid, text[:160])] = (d, t, room, cid, text)
                    elif section == "did":
                        m = RE_DID.match(ln)
                        if m:
                            d, t, kind, text = m.groups()
                            dids[(d, t, kind, text[:160])] = (d, t, kind, text)
        except OSError:
            continue
    return list(msgs.values()), list(dids.values())


def load_trades():
    rows = []
    for fn in sorted(glob.glob(os.path.join(HERE, "days", "*.json"))):
        day = os.path.basename(fn)[:-5]
        try:
            d = json.load(open(fn, encoding="utf-8"))
        except Exception:                               # noqa: BLE001
            continue
        for r in (d.get("table") or []):
            if isinstance(r, dict):
                r = dict(r)
                r["_day"] = day
                rows.append(r)
    return rows


def main():
    rooms = load_rooms()
    msgs, dids = load_exports()
    trades = load_trades()

    # ---- per-room message stats -------------------------------------------
    R = defaultdict(lambda: {"msgs": 0, "signals": 0, "entries": 0, "exits": 0,
                             "last": "", "last_text": "", "days": set(), "authors": defaultdict(int),
                             "sent": 0, "skipped": 0, "ignored": 0, "label": "", "cid": ""})
    for d, t, room, cid, text in msgs:
        if d < SINCE.isoformat():
            continue
        r = R[cid]
        r["label"] = room
        r["cid"] = cid
        r["msgs"] += 1
        r["days"].add(d)
        author = text.split(":", 1)[0][:40] if ":" in text else "?"
        if RE_CONTRACT.search(text):
            r["signals"] += 1
            r["authors"][author] += 1
            if RE_ENTRY.search(text):
                r["entries"] += 1
            if RE_EXIT.search(text):
                r["exits"] += 1
            stamp = "%s %s" % (d, t[:5])
            if stamp > r["last"]:
                r["last"] = stamp
                r["last_text"] = text[:140]

    # verdicts carry "· Server: channel" — match by channel label
    label_to_cid = {v["label"]: k for k, v in R.items()}
    for d, t, kind, text in dids:
        if d < SINCE.isoformat():
            continue
        hit = None
        for lab, cid in label_to_cid.items():
            chan = lab.split(":", 1)[-1].strip()
            if chan and chan in text:
                hit = cid
                break
        if hit is None:
            continue
        if kind == "sent":
            R[hit]["sent"] += 1
        elif kind == "skipped":
            R[hit]["skipped"] += 1
        elif kind == "ignored":
            R[hit]["ignored"] += 1

    # ---- per-room / per-trader trade stats ---------------------------------
    T = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "pl": 0.0,
                             "best": None, "worst": None, "hi": [], "who": defaultdict(int)})
    for r in trades:
        if (r.get("_day") or "") < SINCE.isoformat():
            continue
        if not r.get("entries"):
            continue                         # never filled — not a trade
        room = str(r.get("room") or "?")
        key = room if room in rooms else room
        t = T[key]
        t["trades"] += 1
        pl = float(r.get("pl") or 0.0)
        t["pl"] += pl
        if pl > 0:
            t["wins"] += 1
        elif pl < 0:
            t["losses"] += 1
        t["best"] = pl if t["best"] is None else max(t["best"], pl)
        t["worst"] = pl if t["worst"] is None else min(t["worst"], pl)
        if r.get("hi_pct") is not None:
            t["hi"].append(float(r["hi_pct"]))
        t["who"][str(r.get("who") or "?")] += 1

    # ---- rows ---------------------------------------------------------------
    rows = []
    seen_cids = set()
    for cid, r in R.items():
        seen_cids.add(cid)
        cfg = rooms.get(cid)
        tr = T.get(cid) or T.get((cfg or {}).get("label", "\x00")) or {}
        rows.append({
            "room": r["label"], "cid": cid, "configured": bool(cfg),
            "group": (cfg or {}).get("group", "(not in rooms.txt)"),
            "msgs": r["msgs"], "signals": r["signals"], "entries": r["entries"], "exits": r["exits"],
            "days": len(r["days"]), "last": r["last"], "last_text": r["last_text"],
            "top": ", ".join("%s (%d)" % (a, n) for a, n in sorted(r["authors"].items(), key=lambda x: -x[1])[:3]),
            "sent": r["sent"], "skipped": r["skipped"], "ignored": r["ignored"],
            "trades": tr.get("trades", 0), "wins": tr.get("wins", 0), "losses": tr.get("losses", 0),
            "pl": tr.get("pl", 0.0),
            "hi": (sum(tr["hi"]) / len(tr["hi"])) if tr.get("hi") else None,
        })
    for cid, cfg in rooms.items():
        if cid in seen_cids:
            continue
        rows.append({"room": cfg["label"], "cid": cid, "configured": True, "group": cfg["group"],
                     "msgs": 0, "signals": 0, "entries": 0, "exits": 0, "days": 0, "last": "",
                     "last_text": "", "top": "", "sent": 0, "skipped": 0, "ignored": 0,
                     "trades": 0, "wins": 0, "losses": 0, "pl": 0.0, "hi": None})
    # trade rows whose room label isn't a channel id (older days used labels)
    for key, tr in T.items():
        if key in R or key in rooms:
            continue
        rows.append({"room": key, "cid": "", "configured": False, "group": "(trade table only)",
                     "msgs": 0, "signals": 0, "entries": 0, "exits": 0, "days": 0, "last": "",
                     "last_text": "", "top": ", ".join("%s (%d)" % kv for kv in sorted(tr["who"].items(), key=lambda x: -x[1])[:3]),
                     "sent": 0, "skipped": 0, "ignored": 0,
                     "trades": tr["trades"], "wins": tr["wins"], "losses": tr["losses"], "pl": tr["pl"],
                     "hi": (sum(tr["hi"]) / len(tr["hi"])) if tr["hi"] else None})

    rows.sort(key=lambda x: (-x["signals"], -x["msgs"], x["room"]))

    # ---- trader board (from the trade table) --------------------------------
    W = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "pl": 0.0, "rooms": set(), "last": ""})
    for r in trades:
        if (r.get("_day") or "") < SINCE.isoformat() or not r.get("entries"):
            continue
        w = W[str(r.get("who") or "?")]
        w["trades"] += 1
        pl = float(r.get("pl") or 0.0)
        w["pl"] += pl
        w["wins"] += 1 if pl > 0 else 0
        w["losses"] += 1 if pl < 0 else 0
        w["rooms"].add(rooms.get(str(r.get("room")), {}).get("label", str(r.get("room"))))
        w["last"] = max(w["last"], r.get("_day") or "")
    traders = sorted(W.items(), key=lambda kv: -kv[1]["pl"])

    # ---- html ---------------------------------------------------------------
    def money(v):
        return ("+" if v > 0 else "") + "$%.0f" % v if v else "$0"

    def cls(v):
        return "pos" if v > 0 else "neg" if v < 0 else ""

    body = []
    body.append("<h1>Room scoreboard</h1>")
    body.append("<div class=sub>Last %d days (since %s) · %d rooms heard from · %d configured · built %s</div>"
                % (DAYS_BACK, SINCE.isoformat(), len(R), len(rooms), time.strftime("%Y-%m-%d %H:%M")))
    n_silent = sum(1 for x in rows if x["configured"] and x["signals"] == 0)
    body.append("<div class=kpis>"
                "<div><b>%d</b><small>rooms with real signals</small></div>"
                "<div><b>%d</b><small>configured rooms SILENT (no contract named)</small></div>"
                "<div><b>%d</b><small>bot orders sent</small></div>"
                "<div><b class='%s'>%s</b><small>bot P&amp;L, filled trades</small></div>"
                "</div>" % (sum(1 for x in rows if x["signals"] > 0), n_silent,
                            sum(x["sent"] for x in rows),
                            cls(sum(x["pl"] for x in rows)), money(sum(x["pl"] for x in rows))))
    body.append("<table><thead><tr>"
                "<th>Room</th><th>Group</th><th>Msgs</th><th>Signals</th><th>Entries</th><th>Exits</th>"
                "<th>Days</th><th>Last signal</th><th>Who signals</th>"
                "<th>Sent</th><th>Skipped</th><th>Ignored</th>"
                "<th>Trades</th><th>W/L</th><th>P&amp;L</th><th>Avg peak</th></tr></thead><tbody>")
    for x in rows:
        state = ("silent" if x["configured"] and x["signals"] == 0 else "")
        body.append("<tr class='%s'><td><b>%s</b>%s<div class=small>%s</div></td><td>%s</td>"
                    "<td>%d</td><td><b>%d</b></td><td>%d</td><td>%d</td><td>%d</td>"
                    "<td>%s</td><td class=small>%s</td>"
                    "<td>%d</td><td>%d</td><td>%d</td>"
                    "<td>%d</td><td>%d / %d</td><td class='%s'>%s</td><td>%s</td></tr>"
                    % (state, html.escape(x["room"]),
                       "" if x["configured"] else " <span class=tag>not in rooms.txt</span>",
                       html.escape(x["last_text"]), html.escape(x["group"]),
                       x["msgs"], x["signals"], x["entries"], x["exits"], x["days"],
                       x["last"] or "<span class=tag>never</span>", html.escape(x["top"]),
                       x["sent"], x["skipped"], x["ignored"],
                       x["trades"], x["wins"], x["losses"], cls(x["pl"]), money(x["pl"]),
                       ("%+.0f%%" % x["hi"]) if x["hi"] is not None else "—"))
    body.append("</tbody></table>")

    body.append("<h2>By trader (bot's filled trades)</h2>")
    body.append("<table><thead><tr><th>Trader</th><th>Trades</th><th>W/L</th><th>P&amp;L</th><th>Rooms</th><th>Last</th></tr></thead><tbody>")
    for who, w in traders:
        body.append("<tr><td><b>%s</b></td><td>%d</td><td>%d / %d</td><td class='%s'>%s</td><td class=small>%s</td><td>%s</td></tr>"
                    % (html.escape(who), w["trades"], w["wins"], w["losses"], cls(w["pl"]), money(w["pl"]),
                       html.escape(", ".join(sorted(w["rooms"]))), w["last"]))
    body.append("</tbody></table>")
    body.append("<div class=foot>Signals = messages naming a contract (ticker + strike + C/P). Entries/Exits = signals with buy / sell words. "
                "Sent/Skipped/Ignored = the bot's own verdicts for that room. Trades/P&amp;L = the bridge's trade table (filled only). "
                "Re-run: <code>python scoreboard.py 10</code>.</div>")

    page = """<!DOCTYPE html><html lang=en><head><meta charset=utf-8><title>Room scoreboard</title><style>
:root{color-scheme:light}body{margin:0;padding:24px 28px 60px;font:13.5px/1.4 -apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:#1b1f27;background:#f7f8fb}
h1{margin:0 0 4px;font-size:22px}h2{font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:#5b6472;margin:30px 0 10px}
.sub{color:#5b6472;margin-bottom:14px}.kpis{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.kpis div{background:#fff;border:1px solid #d9dee7;border-radius:10px;padding:10px 16px;min-width:150px}.kpis b{font-size:22px;display:block}.kpis small{color:#5b6472}
table{border-collapse:collapse;width:100%;background:#fff;border:1px solid #d9dee7;border-radius:10px;overflow:hidden}
th,td{padding:7px 9px;border-bottom:1px solid #e6e9ef;text-align:left;vertical-align:top}th{background:#eef1f6;font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;color:#5b6472;position:sticky;top:0}
tr:last-child td{border-bottom:0}tr.silent td{background:#fff7f7;color:#7a7f8a}
.small{font-size:11.5px;color:#5b6472;max-width:420px}.tag{font-size:10.5px;background:#fde8e8;color:#b91c1c;padding:1px 6px;border-radius:8px}
.pos{color:#15803d;font-weight:700}.neg{color:#b91c1c;font-weight:700}.foot{color:#5b6472;font-size:12px;margin-top:16px}code{background:#eef1f6;padding:1px 5px;border-radius:4px}
</style></head><body>__BODY__</body></html>""".replace("__BODY__", "\n".join(body))
    out = os.path.join(HERE, "SCOREBOARD.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)

    # console summary
    print("rooms heard from: %d   configured: %d   silent configured: %d" % (len(R), len(rooms), n_silent))
    for x in rows[:40]:
        print("%-58s sig %3d  ent %3d  ex %3d  sent %2d  trades %2d  P&L %s  last %s"
              % (x["room"][:58], x["signals"], x["entries"], x["exits"], x["sent"], x["trades"], money(x["pl"]), x["last"] or "never"))
    print("wrote", out)


if __name__ == "__main__":
    main()
