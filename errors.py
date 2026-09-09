"""errors.py — the day's ERRORS & BUGS in one place.

Everything is already in trades.log (minute-by-minute) and bridge.log
(tracebacks), but scattered. This reads them back and groups every problem by
kind, so "what broke today" is one command instead of ten greps.

    python3 errors.py                today (default)
    python3 errors.py --date 2026-09-08
    python3 errors.py --all          every day in the log

Read-only. Reads trades.log + bridge.log; writes nothing, trades nothing.
Companion to misses.py (alerts that didn't trade) and journal_full.py.
"""
import os
import re
import sys
import datetime as _dt
from collections import OrderedDict, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TLOG = os.path.join(HERE, "trades.log")
BLOG = os.path.join(HERE, "bridge.log")

# category -> matcher. First match wins; specific before general.
CATS = [
    ("BROKER rejected a SELL (buying power)",
        re.compile(r"DAY_BUYING_POWER_INSUFFICIENT", re.I)),
    ("BROKER rejected a SELL (already closed / reverse)",
        re.compile(r"NOT_SUPPORT_REVERSE_OPTION", re.I)),
    ("BROKER wouldn't hold a resting stop",
        re.compile(r"STOP_PRICE_MUST_BE_LESS_THAN_MARKET|STOP-WARN", re.I)),
    ("STOP failed to sell",
        re.compile(r"stop (tried to sell and couldn't|failed to sell)", re.I)),
    ("PHANTOM exit (book closed, broker still held)",
        re.compile(r"^PHANTOM|book recorded 'closed' but the broker", re.I)),
    ("ORPHAN (account holds what the book thinks is closed)",
        re.compile(r"orphan|the book thinks is closed", re.I)),
    ("FUTURES prop rejected (Topstep/ProjectX)",
        re.compile(r"PROP-NO|ProjectX refused", re.I)),
    ("FUTURES: Webull account has no position (unfunded)",
        re.compile(r"^FUT-POS|no futures position", re.I)),
    ("RATE-LIMIT throttle (429)",
        re.compile(r"\b429\b|TOO_MANY_REQUESTS|throttle", re.I)),
    ("BRIDGE unreachable / thread died",
        re.compile(r"BRIDGE UNREACHABLE|a thread that dies|deadman", re.I)),
    ("OTHER broker error (417)",
        re.compile(r"HTTP Status: 417|OPENAPI_", re.I)),
]

# Refusals that are the guards WORKING — not errors. Shown separately.
GUARDS = [
    ("Too thin / no open interest", re.compile(r"too thin to trade", re.I)),
    ("Swings paused",               re.compile(r"swing trades are PAUSED", re.I)),
    ("Buying power too small (skipped up front)",
        re.compile(r"costs \$.*to spend", re.I)),
    ("Test room — nothing sent",    re.compile(r"test room, nothing sent", re.I)),
]

_CODE = re.compile(r"OPENAPI_[A-Z_]+")
_ADOPT = re.compile(r"^ADOPT", re.I)


def _rows(path, date, all_days):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            parts = ln.split("\t", 1)
            if len(parts) == 2:
                ts, msg = parts
                d = ts[:10]
                hhmm = ts[11:16] if len(ts) >= 16 else ""
            else:
                # bridge.log: no tab; only used for tracebacks/429 scan
                ts = ""
                d = ""
                hhmm = ""
                msg = ln
            if not all_days and date and d and d != date:
                continue
            yield d, hhmm, msg


def _scan(date=None, all_days=False):
    if date is None and not all_days:
        date = _dt.date.today().isoformat()
    err = OrderedDict((c[0], []) for c in CATS)
    guard = OrderedDict((g[0], 0) for g in GUARDS)
    codes = defaultdict(int)
    adopts = 0
    seen = set()
    for d, hhmm, msg in _rows(TLOG, date, all_days):
        m = _CODE.search(msg)
        if m:
            codes[m.group(0)] += 1
        if _ADOPT.search(msg):
            adopts += 1
        placed = False
        for label, pat in CATS:
            if pat.search(msg):
                err[label].append((hhmm, msg))
                placed = True
                break
        if placed:
            continue
        for label, pat in GUARDS:
            if pat.search(msg):
                guard[label] += 1
                break
    # tracebacks from bridge.log (today only, cheap heuristic)
    tb = 0
    for d, hhmm, msg in _rows(BLOG, date, all_days):
        if msg.strip().startswith("Traceback (most recent call last)"):
            tb += 1
    return err, guard, codes, adopts, tb


def main(argv):
    date = _dt.date.today().isoformat()
    all_days = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--all":
            all_days = True
            date = None
        elif a == "--date" and i + 1 < len(argv):
            date = argv[i + 1]
            i += 1
        i += 1

    err, guard, codes, adopts, tb = _scan(date, all_days)
    scope = "ALL DAYS" if all_days else date
    print("\nERRORS & BUGS — %s\n" % scope)

    total = sum(len(v) for v in err.values())
    if not total and not tb:
        print("  clean — no broker errors, prop rejects, phantoms or "
              "tracebacks logged.\n")
    for label, items in err.items():
        if not items:
            continue
        print("  %-48s %d" % (label, len(items)))
        # show the first distinct message as a sample
        for hhmm, msg in items[:1]:
            print("        e.g. %s  %s" % (hhmm, msg[:96]))
    if tb:
        print("  %-48s %d   (see bridge.log)" % ("PYTHON tracebacks", tb))

    if codes:
        print("\n  broker error codes seen:")
        for c, n in sorted(codes.items(), key=lambda x: -x[1]):
            print("    %-46s %d" % (c, n))
    if adopts:
        print("\n  reconciliations (your manual trades adopted): %d" % adopts)

    shown = [(l, n) for l, n in guard.items() if n]
    if shown:
        print("\n  guards that fired (working as designed, NOT errors):")
        for l, n in shown:
            print("    %-46s %d" % (l, n))
    print()


if __name__ == "__main__":
    main(sys.argv[1:])
