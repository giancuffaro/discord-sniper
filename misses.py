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
collect_misses() is imported by journal_full.py so both agree on what a miss is.
"""
import os
import re
import sys
import datetime as _dt
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "trades.log")

# Lines that are NOT entry-misses, even if a keyword matches: the futures
# position-poll heartbeat, exit-sell failures, and book/broker bookkeeping.
# (Tag-anchored so we don't accidentally eat a real entry refusal whose text
# happens to end "...you're not in it".)
SKIP = re.compile(r"^(FUT-POS|PHANTOM|POSTCHECK|ADOPT|DEADMAN|RESTORED|"
                  r"STOP-SET|STOP-WARN|WORKING|FILLED|CODE)\b|"
                  r"stop (tried|failed) to sell| exit — |exit failed", re.I)

# First match wins — specific reasons before catch-alls.
CATS = [
    ("THIN / no open interest", re.compile(r"too thin to trade", re.I)),
    ("PULLBACK never hit",      re.compile(r"never touched .*skipped", re.I)),
    ("BUYING POWER too small",  re.compile(r"costs \$.*to spend|buying power is insuffic", re.I)),
    ("SWINGS paused",           re.compile(r"swing trades are PAUSED", re.I)),
    ("TEST room — not sent",    re.compile(r"test room, nothing sent|is a TEST room", re.I)),
    ("FUTURES prop refused",    re.compile(r"PROP-NO|ProjectX refused", re.I)),
    ("NOT optionable",          re.compile(r"not optionable|isn.t optionable|not on the optionable", re.I)),
    ("SPREAD too wide",         re.compile(r"too wide to trade|spread[^.]*too wide", re.I)),
    ("NO buying connection",    re.compile(r"no Webull (paper|live) connection|sandbox unreachable", re.I)),
    ("OTHER refusal",           re.compile(r"\bREFUSED\b", re.I)),
]

# Uppercase words that are NOT tickers (tags, verbs, chatter).
STOP = {"OPEN", "SHORT", "LONG", "REFUSED", "PULLBACK", "SWING", "OFF", "TEST",
        "PROP", "NO", "THE", "AND", "YOU", "BTO", "STC", "DTE", "HTTP", "EXIT",
        "IN", "ENTRY", "TRADE", "ALERT", "EVERY", "BANG", "TP", "SL", "RN",
        "US", "PC", "ID", "OK", "MOD", "FST", "WEBULL", "TOPSTEP", "PROJECTX",
        "ONLY", "MASTER", "DAY", "EOD", "NFP", "YT", "AI", "READ", "AD",
        "SAME", "WITH", "VERY", "GTR", "OPENAPI", "REVERSE", "OPTION",
        "CLOSE", "ADD", "SOLD", "ERROR", "ACCT", "OCO", "PM", "AM", "HALF",
        "ROLL", "LOTTO", "CALL", "CALLS", "PUT", "PUTS", "OVER", "GOING",
        "FAST", "SMA", "POS", "OIF"}

_THIN_N = re.compile(r"only (\d+) contracts", re.I)
_NEVER = re.compile(r"never touched \$?([\d.]+)", re.I)
_MONEY_NEED = re.compile(r"costs \$([\d,]+).*?\$([\d,]+) to spend", re.I)
_PROP_MSG = re.compile(r'errorMessage":"([^"]+)"')


def _sym(msg):
    # Whole all-caps words of 2-6 letters. \b..\b means "REFUSED"(7)/"PULLBACK"(8)
    # etc. never match at all; the shorter tag words are caught by STOP.
    #
    # STOP IS A BLACKLIST AND A BLACKLIST NEVER CONVERGES (9/11): "SOLD but
    # could NOT get back in: that one costs $312..." made the symbol NOT, and
    # the next one would be some other word. extension/optionable.txt is the
    # list of things the broker lists options on and it is the answer — the
    # same rail parser.js, ai_reader and bridge.py already stand on; this
    # reader was the last one without it. symbols.resolve also un-glues the
    # ANSI "m" that welded itself to Namrood's tickers (MXLU -> XLU), so the
    # alert record names the ticker the room actually called. Fails open: no
    # list, no opinion, and the blacklist still stands underneath.
    for tok in re.findall(r"\b[A-Z]{2,6}\b", msg):
        if tok in STOP:
            continue
        try:
            import symbols as _symbols
            got = _symbols.resolve(tok)
        except ImportError:
            got = tok
        if got:
            return got
    return "?"


def _detail(label, msg):
    if label.startswith("THIN"):
        n = _THIN_N.search(msg)
        return "%s (%s traded)" % (_sym(msg), n.group(1) if n else "?")
    if label.startswith("PULLBACK"):
        n = _NEVER.search(msg)
        return "%s ($%s)" % (_sym(msg), n.group(1) if n else "?")
    if label.startswith("BUYING"):
        m = _MONEY_NEED.search(msg)
        return ("%s (needs $%s, had $%s)" % (_sym(msg), m.group(1), m.group(2))) \
            if m else _sym(msg)
    if label.startswith("FUTURES"):
        m = _PROP_MSG.search(msg)
        return "%s — %s" % (_sym(msg), m.group(1)[:40]) if m else _sym(msg)
    return _sym(msg)


def collect_misses(date=None, all_days=False):
    """Every DISTINCT miss as a dict: date, time, reason, symbol, detail, raw.
    date=None + all_days=False means today."""
    if date is None and not all_days:
        date = _dt.date.today().isoformat()
    rows = []
    seen = set()
    if not os.path.exists(LOG):
        return rows
    with open(LOG, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            parts = ln.split("\t", 1)
            if len(parts) != 2:
                continue
            ts, msg = parts
            d = ts[:10]
            if not all_days and d != date:
                continue
            hhmm = ts[11:16] if len(ts) >= 16 else ts
            if SKIP.search(msg):
                continue
            for label, pat in CATS:
                if pat.search(msg):
                    det = _detail(label, msg)
                    key = (d, label, det)
                    if key in seen:
                        break
                    seen.add(key)
                    rows.append({"date": d, "time": hhmm, "reason": label,
                                 "symbol": _sym(msg), "detail": det, "raw": msg})
                    break
    return rows


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

    rows = collect_misses(date=None if show_all else date, all_days=show_all)
    buckets = OrderedDict((c[0], []) for c in CATS)
    for r in rows:
        buckets[r["reason"]].append((r["time"], r["detail"]))

    scope = "ALL DAYS" if show_all else date
    print("\nMISSES — %s  (alerts the reader saw that did NOT trade, and why)\n"
          % scope)
    if not rows:
        print("  none logged — every alert that came in either traded or "
              "wasn't a tradeable call.\n")
        return
    for label, items in buckets.items():
        if not items:
            continue
        dets = ", ".join(d for _, d in items)
        print("  %-24s (%d): %s" % (label, len(items), dets))
    print("\n  total distinct misses: %d\n" % len(rows))


if __name__ == "__main__":
    main(sys.argv[1:])
