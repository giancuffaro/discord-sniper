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


def newest_export():
    fs = sorted(glob.glob(os.path.join(HERE, "DS Logs", "signal-room-chat*.txt")),
                key=os.path.getmtime)
    return fs[-1] if fs else None


def load(fn):
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
                if m and m.group(1) == DAY:
                    d, t, room, cid, text = m.groups()
                    msgs[(t, cid, text[:100])] = (t, room, cid, text)
            elif sec == "d":
                m = RE_DID.match(ln)
                if m and m.group(1) == DAY:
                    dids.append(m.groups()[1:])
    return list(msgs.values()), dids


def bridge_lines():
    out = []
    try:
        with open(os.path.join(HERE, "bridge.log"), encoding="utf-8", errors="replace") as f:
            for ln in f:
                if re.match(r"^\d{2}:\d{2}:\d{2}  ", ln):
                    out.append(ln.rstrip("\n"))
    except OSError:
        pass
    return out


def strip_header(text):
    # "Author: " prefix the export adds, then the parser's own cleaners
    return text.split(": ", 1)[1] if ": " in text[:60] else text


def near(t1, t2, secs):
    def s(x):
        h, m, sec = x.split(":")
        return int(h) * 3600 + int(m) * 60 + int(sec)
    return abs(s(t1) - s(t2)) <= secs


RE_PRICE = re.compile(r"\b\d{1,4}\.\d{1,2}\b")


def find_missed_entries(keep, parsed):
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
    shelf = {}                                    # trader -> (sym, strike, side, t)
    flags = []
    for t, room, author, text, sig in rows:
        act = sig.get("action") if sig else None
        if act == "PREPARE" and sig.get("symbol"):
            shelf[author] = (sig.get("symbol"), sig.get("strike"), sig.get("side"), t)
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
    fn = newest_export()
    if not fn:
        print("no DS Logs export found")
        return
    msgs, dids = load(fn)
    blog = bridge_lines()
    per = defaultdict(lambda: {"msgs": 0, "actionable": 0, "judged": 0, "silent": []})
    keep = [(t, room, cid, text) for (t, room, cid, text) in msgs
            if not any(room.startswith(x) for x in SKIP_ROOMS) and not text.startswith("🎙")]
    parsed = jsparse.parse_many([strip_header(x[3]) for x in keep])
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

    print("REPLAY CHECK for %s — export: %s" % (DAY, os.path.basename(fn)))
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

    missed = find_missed_entries(keep, parsed)
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
