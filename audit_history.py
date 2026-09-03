"""AUDIT HISTORY (9/3/26, G: "find alert fails since the beginning of time,
why some rooms were silent").

replay_check.py answers "what did we miss TODAY". This answers "what have we
missed EVER, and why was each room quiet" across every export the extension
has written (8/18 -> now). Read-only; nothing here trades.

For every day it runs the PRODUCTION parser (extension/parser.js, via
jsparse) over every captured message and sorts each room into one of:

  TRADED      the bot judged it (verdict in the export, or a bridge.log line)
  MISSED      the parser read an OPEN/ADD/CLOSE and NOTHING happened
  BLIND       the parser read NOTHING but a loading shelf was armed and the
              message carried a price — the RWGates "took entry ... fill"
              shape, invisible to the action-based check
  NO CALLS    the room spoke, but never said anything tradable
  SILENT      the room said nothing at all that day

Then it groups the misses by SHAPE so a fix covers a class, not one line.

Run:  python audit_history.py            (writes ALERT-AUDIT.html + console)
      python audit_history.py --quiet    (console summary only)
"""
import glob
import html
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jsparse                                          # noqa: E402

RE_MSG = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})  \[(.*?) #(\S+?)\]  (.*)$")
RE_DID = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})  <(\w+)>  (.*)$")
RE_PRICE = re.compile(r"\b\d{1,4}\.\d{1,2}\b")
SKIP = ("Sniper HQ", "this room")


def day_of(path):
    m = re.search(r"signal-room-chat (\w+-\d+-\d+)\.txt$", os.path.basename(path))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%b-%d-%Y").date().isoformat()
    except ValueError:
        return None


def load(fn, day):
    msgs, dids = {}, []
    sec = None
    with open(fn, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if ln.startswith("=== RAW MESSAGES"):
                sec = "m"
                continue
            if ln.startswith("=== WHAT THE BOT DID"):
                sec = "d"
                continue
            if sec == "m":
                m = RE_MSG.match(ln)
                if m and m.group(1) == day:
                    _d, t, room, cid, text = m.groups()
                    msgs[(t, cid, text[:100])] = (t, room, cid, text)
            elif sec == "d":
                m = RE_DID.match(ln)
                if m and m.group(1) == day:
                    dids.append(m.groups()[1:])
    return list(msgs.values()), dids


def bridge_lines():
    out = []
    try:
        with open(os.path.join(HERE, "bridge.log"), encoding="utf-8",
                  errors="replace") as f:
            for ln in f:
                if re.match(r"^\d{2}:\d{2}:\d{2}  ", ln):
                    out.append(ln.rstrip("\n"))
    except OSError:
        pass
    return out


def strip_header(text):
    return text.split(": ", 1)[1] if ": " in text[:60] else text


def near(a, b, secs):
    def s(x):
        h, m, sec = x.split(":")
        return int(h) * 3600 + int(m) * 60 + int(sec)
    return abs(s(a) - s(b)) <= secs


def shape_of(body):
    """Group a miss by the GRAMMAR that beat the parser, not by its words."""
    b = body.lower()
    if re.search(r"took\s+entry.*\bfill", b):
        return "ticker-first fill: \"$X I took entry 1.37 fill\""
    if re.search(r"\bfilled\b.*\bon\s+\$?[a-z]{1,5}\b", b):
        return "\"Filled <price> ... on $TICKER\""
    if re.search(r"\bavg\b\s*\$?\d", b):
        return "\"avg $PRICE\" (price-only average-in)"
    if re.search(r"^\s*\$?\d{1,3}\.\d{1,2}\s*$", b):
        return "bare price on its own line"
    if re.search(r"\bentry\b.*:", b):
        return "labelled template (Ticker:/Contract:/Entry:)"
    if re.search(r"\bserver tag\b", b):
        return "Discord Server Tag junk around the call"
    if re.search(r"\b(do not|none of this|educational|informational)\b", b):
        return "bot footer swallowed the call (veto words)"
    if re.search(r"\b\d{1,2}/\d{1,2}\b.*\b\d{1,5}\s*[cp]\b", b):
        return "date-first contract (\"8/28 SLV 60C 1.68\")"
    if re.search(r"\b(mnq|mes|nq|es|mgc|gc|cl|rty|ym)\b", b):
        return "futures phrasing"
    return "other / unclassified"


def main():
    files = sorted(glob.glob(os.path.join(HERE, "DS Logs", "signal-room-chat*.txt")))
    days = [(day_of(f), f) for f in files]
    days = [(d, f) for d, f in days if d]
    days.sort()
    blog = bridge_lines()

    rooms = defaultdict(lambda: {"days_spoke": set(), "msgs": 0, "traded": 0,
                                 "missed": [], "blind": [], "calls": 0})
    shapes = defaultdict(list)
    per_day = []

    for day, fn in days:
        msgs, dids = load(fn, day)
        keep = [m for m in msgs
                if not any(m[1].startswith(x) for x in SKIP)
                and not m[3].startswith("\U0001f399")]
        if not keep:
            per_day.append((day, 0, 0, 0))
            continue
        parsed = jsparse.parse_many([strip_header(k[3]) for k in keep])

        rows = []
        for (t, room, cid, text), sig in zip(keep, parsed):
            author = (text.split(": ", 1)[0] if ": " in text[:60] else "?").strip().lower()
            rows.append((t, room, author, text, sig or {}))
        rows.sort(key=lambda r: r[0])

        d_missed = d_blind = d_traded = 0
        shelf = {}
        for t, room, author, text, sig in rows:
            R = rooms[room]
            R["days_spoke"].add(day)
            R["msgs"] += 1
            body = strip_header(text)
            act = sig.get("action")

            # --- BLIND pass: shelf armed, no action, price present
            if act == "PREPARE" and sig.get("symbol"):
                shelf[author] = (sig.get("symbol"), sig.get("strike"), sig.get("side"))
            elif act:
                shelf.pop(author, None)
            else:
                cand = shelf.get(author)
                if cand and RE_PRICE.search(body):
                    R["blind"].append((day, t, cand[0], body[:160]))
                    shapes[shape_of(body)].append((day, room, body[:120]))
                    d_blind += 1
                    shelf.pop(author, None)

            if not act:
                continue
            R["calls"] += 1
            if act not in ("OPEN", "ADD", "CLOSE"):
                continue
            sym = str(sig.get("symbol") or "").upper()
            judged = False
            for vt, kind, vtext in dids:
                if near(vt, t, 180) and ((sym and sym in vtext) or body[:40] in vtext):
                    judged = True
                    break
            if not judged:
                for bl in blog:
                    if near(bl[:8], t, 180) and sym and \
                            re.search(r"\b%s\b" % re.escape(sym), bl):
                        judged = True
                        break
            if judged:
                R["traded"] += 1
                d_traded += 1
            else:
                R["missed"].append((day, t, act, sym, body[:160]))
                shapes[shape_of(body)].append((day, room, body[:120]))
                d_missed += 1
        per_day.append((day, d_traded, d_missed, d_blind))

    # ---- console ----------------------------------------------------------
    print("ALERT AUDIT — every export since the bot went live (%s .. %s)"
          % (days[0][0], days[-1][0]))
    print("\nPER DAY   traded / missed(action) / blind(no action)")
    for day, tr, ms, bl in per_day:
        print("  %s   %4d  %4d  %4d%s" % (day, tr, ms, bl,
                                          "   <-- nothing captured" if tr + ms + bl == 0 else ""))
    tot_m = sum(len(v["missed"]) for v in rooms.values())
    tot_b = sum(len(v["blind"]) for v in rooms.values())
    print("\nTOTAL  missed(action) %d   blind(no action) %d" % (tot_m, tot_b))
    print("\n  READ THIS BEFORE TRUSTING 'MISSED': until 9/2 the extension kept only")
    print("  the last 400 verdicts of a day (LOG_MAX). Every export from 8/19-8/31")
    print("  shows exactly 400 while capturing 700-8,400 messages, so the MORNING")
    print("  verdicts of every one of those days are simply gone. A 'missed' on")
    print("  those days can mean the bot never judged it OR the record was trimmed")
    print("  — the two are indistinguishable now. The cap is 2500 since 9/3, so")
    print("  from here on 'missed' means missed. BLIND is trustworthy on every day:")
    print("  it is the parser's own verdict on the text, not a logging artifact.")

    print("\nBY ROOM  (days spoken / msgs / tradable calls / traded / missed / blind)")
    for room, v in sorted(rooms.items(),
                          key=lambda kv: -(len(kv[1]["missed"]) + len(kv[1]["blind"]))):
        print("  %-52s %2dd %5d %5d %5d %4d %4d"
              % (room[:52], len(v["days_spoke"]), v["msgs"], v["calls"],
                 v["traded"], len(v["missed"]), len(v["blind"])))

    print("\nBY SHAPE  (what beat the parser — fix the shape, not the line)")
    for sh, hits in sorted(shapes.items(), key=lambda kv: -len(kv[1])):
        print("\n  [%d] %s" % (len(hits), sh))
        seen = set()
        for day, room, body in hits:
            k = re.sub(r"\d", "#", body[:40])
            if k in seen:
                continue
            seen.add(k)
            print("      %s %-34s %s" % (day[5:], room[:34], body[:96]))
            if len(seen) >= 4:
                break

    # ---- html -------------------------------------------------------------
    if "--quiet" not in sys.argv:
        H = ["<!DOCTYPE html><html lang=en><head><meta charset=utf-8>",
             "<title>Alert audit</title><style>",
             ":root{color-scheme:light}body{margin:0;padding:24px 28px 60px;",
             "font:13.5px/1.45 -apple-system,'Segoe UI',Roboto,Arial,sans-serif;",
             "color:#1b1f27;background:#f7f8fb}h1{margin:0 0 4px;font-size:22px}",
             "h2{font-size:15px;text-transform:uppercase;letter-spacing:.06em;",
             "color:#5b6472;margin:28px 0 10px}table{border-collapse:collapse;",
             "width:100%;background:#fff;border:1px solid #d9dee7;border-radius:10px;",
             "overflow:hidden}th,td{padding:7px 10px;border-bottom:1px solid #e6e9ef;",
             "text-align:left;vertical-align:top}th{background:#eef1f6;font-size:11.5px;",
             "text-transform:uppercase;color:#5b6472}tr:last-child td{border-bottom:0}",
             ".n{color:#b91c1c;font-weight:700}.g{color:#15803d;font-weight:700}",
             ".s{font-size:11.5px;color:#5b6472}code{background:#eef1f6;padding:1px 5px;",
             "border-radius:4px}</style></head><body>"]
        H.append("<h1>Alert audit — since the bot went live</h1>")
        H.append("<div class=s>%s .. %s &middot; parsed with the production parser "
                 "(extension/parser.js) &middot; built %s</div>"
                 % (days[0][0], days[-1][0],
                    datetime.now().strftime("%Y-%m-%d %H:%M")))
        H.append("<h2>By shape — what beat the parser</h2><table><tr><th>Hits</th>"
                 "<th>Shape</th><th>Examples</th></tr>")
        for sh, hits in sorted(shapes.items(), key=lambda kv: -len(kv[1])):
            ex, seen = [], set()
            for day, room, body in hits:
                k = re.sub(r"\d", "#", body[:40])
                if k in seen:
                    continue
                seen.add(k)
                ex.append("%s &middot; %s<br><span class=s>%s</span>"
                          % (day[5:], html.escape(room[:38]), html.escape(body[:110])))
                if len(ex) >= 3:
                    break
            H.append("<tr><td class=n>%d</td><td><b>%s</b></td><td class=s>%s</td></tr>"
                     % (len(hits), html.escape(sh), "<br>".join(ex)))
        H.append("</table>")
        H.append("<h2>By room</h2><table><tr><th>Room</th><th>Days</th><th>Msgs</th>"
                 "<th>Tradable calls</th><th>Traded</th><th>Missed</th><th>Blind</th></tr>")
        for room, v in sorted(rooms.items(),
                              key=lambda kv: -(len(kv[1]["missed"]) + len(kv[1]["blind"]))):
            H.append("<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td>"
                     "<td class=g>%d</td><td class=n>%d</td><td class=n>%d</td></tr>"
                     % (html.escape(room), len(v["days_spoke"]), v["msgs"],
                        v["calls"], v["traded"], len(v["missed"]), len(v["blind"])))
        H.append("</table>")
        H.append("<h2>Per day</h2><table><tr><th>Day</th><th>Traded</th>"
                 "<th>Missed</th><th>Blind</th></tr>")
        for day, tr, ms, bl in per_day:
            H.append("<tr><td>%s</td><td class=g>%d</td><td class=n>%d</td>"
                     "<td class=n>%d</td></tr>" % (day, tr, ms, bl))
        H.append("</table><div class=s style='margin-top:14px'>MISSED = the parser "
                 "read an OPEN/ADD/CLOSE and no verdict or bridge line followed. "
                 "BLIND = the parser read nothing while that trader had a loading "
                 "call armed and the message carried a price. Re-run: "
                 "<code>python audit_history.py</code>.</div></body></html>")
        out = os.path.join(HERE, "ALERT-AUDIT.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(H))
        print("\nwrote", out)


if __name__ == "__main__":
    main()
