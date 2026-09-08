"""misses.py — WHAT DIDN'T TRADE, AND WHY.

The daily journal (journal.csv / journal-<date>.xlsx) is TRADES ONLY: one row
per position that actually entered the book. A "miss" — an alert the reader
saw but the bridge did NOT trade — never becomes a book row, so it never shows
up in the journal. Those reasons ARE logged, minute by minute, in trades.log
(REFUSED / PULLBACK / SWING-OFF / TEST / PROP-NO ...). This reads trades.log
back and groups every miss by reason.

    python3 misses.py                today (default)
    python3 misses.py --today        today only
    python3 misses.py --date 2026-09-08
    python3 misses.py --all          every day in the log

Read-only. Touches nothing in the trading path — it only reads trades.log.
"""
import os
import re
import sys
import datetime as _dt

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "trades.log")

# Each miss category: (label, matcher on the message text). Order matters —
# the first match wins, so put the specific ones before the catch-alls.
CATS = [
    ("THIN / no open interest", re.compile(r"too thin to trade", re.I)),
    ("PULLBACK never hit",      re.compile(r"never touched .* skipped", re.I)),
    ("BUYING POWER too small",  re.compile(r"costs \$.*to spend|buying power is insuffic", re.I)),
    ("SWINGS paused",           re.compile(r"swing trades are PAUSED", re.I)),
    ("TEST room — not sent",    re.compile(r"test room, nothing sent|is a TEST room", re.I)),
    ("FUTURES prop refused",    re.compile(r"Topstep|ProjectX|PROP-NO", re.I)),
    ("NOT optionable",          re.compile(r"not optionable|isn.t optionable|not on the optionable", re.I)),
    ("SPREAD too wide",         re.compile(r"spread .*too wide|too wide to trade", re.I)),
    ("NO buying connection",    re.compile(r"no Webull (paper|live) connection|sandbox unreachable", re.I)),
    ("OTHER refusal",           re.compile(r"\bREFUSED\b|nothing was sent|Nothing was sent", re.I)),
]

# Pull a ticker-ish symbol out of the message so the summary reads cleanly.
_SYM = re.compile(r"\b(?:OPEN|SHORT|LONG)?\s*([A-Z]{1,6})\s*"
                  r"(?:\d|entry|:|—|-|call|put|C\d|P\d| is | \(|260|261)")
_MONEY_NEED = re.compile(r"costs \$([\d,]+).*?\$([\d,]+) to spend", re.I)
_THIN_N = re.compile(r"only (\d+) contracts", re.I)
_NEVER = re.compile(r"never touched \$?([\d.]+)", re.I)


def _sym(msg):
    # strip the leading TAG word(s) so the symbol regex sees the payload
    m = re.match(r"^[A-Z][A-Z\- ]{2,12}?\s{2,}(.*)$", msg)
    payload = m.group(1) if m else msg
    for pat in (re.compile(r"\bOPEN\s+([A-Z]{1,6})\b"),
                re.compile(r"\b([A-Z]{2,6})\s+(?:entry|\d|—|:|call|put)", re.I),
                re.compile(r"\b([A-Z]{2,6})\b")):
        g = pat.search(payload)
        if g:
            s = g.group(1).upper()
            if s not in ("OPEN", "SHORT", "LONG", "THE", "AND", "YOU", "BTO",
                         "STC", "DTE", "HTTP", "TEST"):
                return s
    return "?"


def _detail(label, msg):
    s = _sym(msg)
    if label.startswith("THIN"):
        n = _THIN_N.search(msg)
        return "%s (%s traded)" % (s, n.group(1) if n else "?")
    if label.startswith("PULLBACK"):
        n = _NEVER.search(msg)
        return "%s ($%s)" % (s, n.group(1) if n else "?")
    if label.startswith("BUYING"):
        m = _MONEY_NEED.search(msg)
        return ("%s (needs $%s, had $%s)" % (s, m.group(1), m.group(2))) if m else s
    return s


def main(argv):
    date = _dt.date.today().isoformat()
    show_all = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--today":
            date = _dt.date.today().isoformat()
        elif a == "--all":
            show_all = True
        elif a == "--date" and i + 1 < len(argv):
            date = argv[i + 1]
            i += 1
        i += 1

    if not os.path.exists(LOG):
        print("no trades.log yet.")
        return

    # bucket: label -> list of (hhmm, detail)
    from collections import OrderedDict
    buckets = OrderedDict((c[0], []) for c in CATS)
    seen = set()   # (label, detail, hhmm) — collapse the double-logs

    with open(LOG, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not show_all and not ln.startswith(date):
                continue
            parts = ln.split("\t", 1)
            if len(parts) != 2:
                continue
            ts, msg = parts
            hhmm = ts[11:16] if len(ts) >= 16 else ts
            for label, pat in CATS:
                if pat.search(msg):
                    det = _detail(label, msg)
                    key = (label, det, hhmm)
                    if key in seen:
                        break
                    seen.add(key)
                    buckets[label].append((hhmm, det))
                    break

    total = sum(len(v) for v in buckets.values())
    scope = "ALL DAYS" if show_all else date
    print("\nMISSES — %s  (alerts the reader saw that did NOT trade, and why)\n"
          % scope)
    if not total:
        print("  none logged — every alert that came in either traded or "
              "wasn't a tradeable call.\n")
        return
    for label, rows in buckets.items():
        if not rows:
            continue
        dets = ", ".join(d for _, d in rows)
        print("  %-26s (%d): %s" % (label, len(rows), dets))
    print("\n  total misses: %d\n" % total)


if __name__ == "__main__":
    main(sys.argv[1:])
