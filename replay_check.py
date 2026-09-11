"""REPLAY CHECK (9/2/26, G: "why aren't we finding bugs like these when I tell
you to run everything?").

"Run everything" used to test the plumbing — bridge, bus, stream, unit tests
with canned phrases. It never replayed the day's REAL room messages. This does:

  1. every message the reader captured today (DS Logs export, RAW section)
  2. through the PRODUCTION parser (extension/parser.js via node)
  3. anything the parser reads as an ACTION is looked up in
       - the extension's verdicts (<sent>/<skipped>/<ignored>, same export)
       - bridge.log (ORDER IN / refused / AI READ lines with the ticker)
  4. an actionable message with NO verdict and NO bridge line is a SILENT DROP
     — the exact shape of the RWGates and Vero misses on 9/2.

Run:  python replay_check.py [YYYY-MM-DD]     (default: today)
Prints per-room counts and every silent drop with the raw text. Read-only.
"""
import glob
import os
import re
import sys
from collections import defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jsparse  # noqa: E402  (the PRODUCTION parser via node; Python mirror only as fallback)

DAY = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
RE_MSG = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})  \[(.*?) #(\S+?)\]  (.*)$")
RE_DID = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})  <(\w+)>  (.*)$")
SKIP_ROOMS = ("Sniper HQ", "this room")           # our own output / voice


def room_rules():
    """rooms.txt is production's source of per-room parser grammar."""
    out = {}
    try:
        with open(os.path.join(HERE, "extension", "rooms.txt"), encoding="utf-8") as f:
            for line in f:
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                p = [x.strip() for x in line.split("|")]
                if len(p) >= 6:
                    out[p[0]] = [x.strip().lower() for x in p[5].split(",") if x.strip()]
    except OSError:
        pass
    return out


ROOM_RULES = room_rules()


def parser_cfg(channel_id, text):
    c = {}
    for rule in ROOM_RULES.get(str(channel_id), []):
        if rule == "bare":
            c["entry_no_verb"] = True
        elif rule == "dotdate":
            c["dot_date"] = True
        elif rule == "readonly":
            c["read_only"] = True
        elif rule.startswith("pivot="):
            c["pivot_root"] = rule.split("=", 1)[1].upper()
        elif rule.startswith("sym="):
            c["default_symbol"] = rule.split("=", 1)[1].upper()
    # OWLS all-alerts carries several callers. Production applies their known
    # grammar after unwrapping the relay; mirror those narrow rules here.
    if str(channel_id) == "1449226651064991806":
        low = text.lower()
        if "muggzone-options" in low or "muggzone message" in low:
            c["entry_no_verb"] = True
        if "shabs-sky-alerts" in low or "eli-alerts" in low:
            c["default_symbol"] = "SPX"
    return c


def newest_export():
    """9/10: exports are now "<day> (discord).txt" / "<day> (whop).txt" — both
    profiles used to write ONE name and clobber each other's whole day. The
    glob already matches both; taking the newest mtime is still right for
    "what just happened", and export_for_day below reads EVERY lane for a day."""
    fs = sorted(glob.glob(os.path.join(HERE, "DS Logs", "signal-room-chat*.txt")),
                key=os.path.getmtime)
    return fs[-1] if fs else None


def export_for_day(day):
    """9/3, G: run this for every past day. newest_export() always returns
    the single most-recently-modified file no matter what DAY was asked
    for — fine for "today" but silently wrong for anything historical
    (it would filter the newest file for a date string that isn't in it
    and report zero results). Resolve DAY to the actual export file:
    first by filename ("signal-room-chat Aug-18-2026.txt" -> 2026-08-18),
    falling back to scanning file contents for that date if the name
    doesn't decode cleanly.
    """
    fs = sorted(glob.glob(os.path.join(HERE, "DS Logs", "signal-room-chat*.txt")))
    for f in fs:
        m = re.search(r"signal-room-chat (\w+-\d+-\d+)(?: \([a-z]+\))?\.txt$", os.path.basename(f))
        if not m:
            continue
        try:
            from datetime import datetime
            d = datetime.strptime(m.group(1), "%b-%d-%Y").date().isoformat()
        except ValueError:
            continue
        if d == day:
            return f
    for f in fs:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    if ln.startswith(day + " "):
                        return f
        except OSError:
            continue
    return None


def exports_for_day(day):
    """Every lane export for ``day`` (Discord and Whop), newest per lane.

    The split-profile exporter writes ``(discord)`` and ``(whop)`` files.
    ``export_for_day`` predates that split and returns on the first filename,
    which silently excluded the other lane from the daily miss audit.
    """
    fs = sorted(glob.glob(os.path.join(HERE, "DS Logs",
                                       "signal-room-chat*.txt")))
    matched = []
    for f in fs:
        m = re.search(
            r"signal-room-chat (\w+-\d+-\d+)(?: \(([a-z]+)\))?\.txt$",
            os.path.basename(f))
        if not m:
            continue
        try:
            from datetime import datetime
            file_day = datetime.strptime(m.group(1), "%b-%d-%Y").date().isoformat()
        except ValueError:
            continue
        if file_day == day:
            matched.append(f)
    if matched:
        # If a legacy unsuffixed file and split-lane files coexist, the split
        # files are the authoritative independent snapshots.
        split = [f for f in matched if re.search(r" \((discord|whop)\)\.txt$", f)]
        return split or matched
    found = []
    for f in fs:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                if any(ln.startswith(day + " ") for ln in fh):
                    found.append(f)
        except OSError:
            continue
    return found


def load(fn):
    msgs, parser_msgs, dids = {}, {}, []
    sec = None
    with open(fn, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if ln.startswith("=== RAW MESSAGES"):
                sec = "m"
                continue
            if ln.startswith("=== LIVE PARSER INPUTS"):
                sec = "p"
                continue
            if ln.startswith("=== WHAT THE BOT DID"):
                sec = "d"
                continue
            if sec in ("m", "p"):
                m = RE_MSG.match(ln)
                if m and m.group(1) == DAY:
                    d, t, room, cid, text = m.groups()
                    # A scroll/backfill is useful parser corpus, but it never
                    # entered the live path and cannot be a silent live drop.
                    if text.startswith("<history> "):
                        continue
                    target = parser_msgs if sec == "p" else msgs
                    target[(t, cid, text[:100])] = (t, room, cid, text)
            elif sec == "d":
                m = RE_DID.match(ln)
                if m and m.group(1) == DAY:
                    dids.append(m.groups()[1:])
    return list((parser_msgs or msgs).values()), dids


def bridge_lines(day=None):
    """9/3 CLEANUP FINDING — read trades.log, not bridge.log.

    bridge.log is stdout: its lines carry HH:MM:SS and NO DATE, so matching
    a 9:41 message against a 9:41 log line matched ACROSS DAYS — an 8/19
    call could be "confirmed" by a 9/3 log line at the same clock time.
    trades.log is the same stream written by note() with a full ISO
    timestamp, and it goes back to 8/01. Same information, dated, and it
    makes every historical answer honest. Returns "HH:MM:SS  text" lines
    for `day` so callers keep their existing shape.
    """
    out = []
    try:
        with open(os.path.join(HERE, "trades.log"), encoding="utf-8",
                  errors="replace") as f:
            for ln in f:
                if len(ln) < 20 or ln[4] != "-" or "\t" not in ln:
                    continue
                if day and not ln.startswith(day):
                    continue
                out.append("%s  %s" % (ln[11:19], ln.split("\t", 1)[1].rstrip("\n")))
    except OSError:
        pass
    return out

def strip_header(text):
    # "Author: " prefix the export adds, then the parser's own cleaners
    text = text.split(": ", 1)[1] if ": " in text[:60] else text
    # Discord's accessible row repeats its visible timestamp before the post.
    # The activity log stores the clean post ("Filled"), so remove the display
    # header before both parsing and verdict matching.
    return re.sub(
        r"^(?:.*?)?(?:\[\s*)?\d{1,2}:\d{2}\s*[AP]M(?:\s*\])?\s+"
        r"[A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}\s+at\s+"
        r"\d{1,2}:\d{2}\s*[AP]M\s+", "", text)


def near(t1, t2, secs):
    def s(x):
        h, m, sec = x.split(":")
        return int(h) * 3600 + int(m) * 60 + int(sec)
    return abs(s(t1) - s(t2)) <= secs


RE_PRICE = re.compile(r"\b\d{1,4}\.\d{1,2}\b")


def find_missed_entries(keep, parsed, dids=None, blog=None):
    """Second pass, separate from the action-based silent-drop check above
    (which is structurally blind to this — 9/3, G: "we need to be catching
    these" after 3 real entries this exact shape were missed in one day).
    That check only fires when the parser ALREADY assigned an action; this
    one catches the case where it assigned NOTHING at all.

    Simulates the extension's own per-trader LOADING shelf (guards.js
    remember_loading/resolve_loaded) chronologically across the day: a
    PREPARE arms the shelf for that trader; any recognized action after it
    clears the shelf (they're done confirming); a message that parses to NO
    action at all while the shelf is still armed AND the message carries a
    price is flagged — the same shape as RWGates' NVDA and both Unraveller
    misses on 9/3. Heuristic and deliberately narrow (needs an armed shelf,
    not just any price+word combo) — a diagnostic net, not a trading
    decision; nothing here is ever acted on.
    """
    rows = []
    for (t, room, cid, text), sig in zip(keep, parsed):
        author = text.split(": ", 1)[0] if ": " in text[:60] else "?"
        rows.append((t, room, author.strip().lower(), text, sig))
    rows.sort(key=lambda r: r[0])
    dids, blog = dids or [], blog or []
    shelf = {}                                    # trader -> (sym, strike, side, t)
    flags = []
    for t, room, author, text, sig in rows:
        act = sig.get("action") if sig else None
        if act == "PREPARE" and sig.get("symbol"):
            shelf[author] = (sig.get("symbol"), sig.get("strike"), sig.get("side"), t)
            continue
        # A price-only confirmation is actionable only after guards.js joins
        # it to the caller's PREPARE shelf. A parser replay that stops at
        # needs_loaded would otherwise count the old heuristic "POSSIBLE
        # MISSED" warning as a verdict and hide the fact that no OPEN was ever
        # produced. Require a concrete OPEN/bridge record for the loaded symbol.
        if act == "OPEN" and sig.get("needs_loaded"):
            cand = shelf.get(author)
            if not cand:
                continue
            concrete = any(near(vt, t, 180) and ("OPEN " + cand[0]) in vtext
                           for vt, _kind, vtext in dids)
            if not concrete:
                concrete = any(near(bl[:8], t, 180) and
                               re.search(r"\b(?:OPEN|ORDER IN)\s+%s\b" %
                                         re.escape(cand[0]), bl)
                               for bl in blog)
            if not concrete:
                body = strip_header(text)
                flags.append((t, room, author, cand[0], cand[1], cand[2],
                              body[:150]))
            shelf.pop(author, None)
            continue
        if act:
            shelf.pop(author, None)               # confirmed some other way, or moved on
            continue
        cand = shelf.get(author)
        if not cand:
            continue
        body = strip_header(text)
        if not RE_PRICE.search(body):
            continue
        flags.append((t, room, author, cand[0], cand[1], cand[2], body[:150]))
        del shelf[author]                          # one flag per loading call
    return flags


def main():
    fns = exports_for_day(DAY)
    if not fns:
        newest = newest_export()
        fns = [newest] if newest else []
    if not fns:
        print("no DS Logs export found")
        return
    msg_map, dids, empty_exports = {}, [], []
    for fn in fns:
        lane_msgs, lane_dids = load(fn)
        if not lane_msgs:
            empty_exports.append(os.path.basename(fn))
        for row in lane_msgs:
            msg_map[(row[0], row[2], row[3][:100])] = row
        dids.extend(lane_dids)
    msgs = list(msg_map.values())
    blog = bridge_lines(DAY)
    per = defaultdict(lambda: {"msgs": 0, "actionable": 0, "judged": 0, "silent": []})
    keep = [(t, room, cid, text) for (t, room, cid, text) in msgs
            if not any(room.startswith(x) for x in SKIP_ROOMS) and not text.startswith("🎙")]
    bodies = [strip_header(x[3]) for x in keep]
    parsed = jsparse.parse_many(
        bodies, [parser_cfg(x[2], body) for x, body in zip(keep, bodies)])
    for (t, room, cid, text), sig in zip(keep, parsed):
        p = per[room]
        p["msgs"] += 1
        body = strip_header(text)
        if not sig or not sig.get("action"):
            continue
        p["actionable"] += 1
        # Only the calls that MUST produce a record: entries, adds, full
        # exits. PREPARE (loading) and trims are ignored by design (exit
        # policy = ratchet), so their silence is expected, not a drop.
        if sig.get("action") not in ("OPEN", "ADD", "CLOSE"):
            continue
        sym = str(sig.get("symbol") or "").upper()
        # any verdict within 3 min naming the ticker or quoting the text?
        judged = False
        for vt, kind, vtext in dids:
            if near(vt, t, 180) and ((sym and sym in vtext) or body[:40] in vtext):
                judged = True
                break
        if not judged:
            for bl in blog:
                bt = bl[:8]
                if near(bt, t, 180) and sym and re.search(r"\b%s\b" % re.escape(sym), bl):
                    judged = True
                    break
        if judged:
            p["judged"] += 1
        else:
            p["silent"].append((t, sig.get("action"), sym, body[:150]))

    print("REPLAY CHECK for %s — exports: %s" %
          (DAY, ", ".join(os.path.basename(f) for f in fns)))
    for fn in empty_exports:
        print("COVERAGE WARNING: %s contains no live parser inputs for %s; "
              "a zero-miss result does not audit that lane." % (fn, DAY))
    total_silent = 0
    for room, p in sorted(per.items(), key=lambda kv: -len(kv[1]["silent"])):
        if not p["actionable"]:
            continue
        total_silent += len(p["silent"])
        print("\n%s — %d msgs, %d actionable, %d judged, %d SILENT"
              % (room, p["msgs"], p["actionable"], p["judged"], len(p["silent"])))
        for t, act, sym, body in p["silent"][:8]:
            print("   %s  %-7s %-5s %s" % (t, act, sym, body))
    print("\nTOTAL silent drops: %d  (actionable per the parser, no verdict, no bridge line)" % total_silent)

    missed = find_missed_entries(keep, parsed, dids, blog)
    if missed:
        print("\nPOSSIBLE MISSED ENTRIES (heuristic — parser found NO action at "
              "all, but the trader had an unconfirmed LOADING call and this "
              "message carries a price):")
        for t, room, author, sym, strike, side, body in missed:
            what = sym + (" " + str(strike) + ("P" if side == "PUTS" else "C")
                          if strike is not None else "")
            print("   %s  %-20s %-15s %s — %s" % (t, room[:20], author, what, body))
    print("POSSIBLE MISSED ENTRIES: %d" % len(missed))


if __name__ == "__main__":
    main()
