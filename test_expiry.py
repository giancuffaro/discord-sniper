#!/usr/bin/env python3
"""test_expiry.py — every date shape the rooms actually write, read correctly.

    python3 test_expiry.py        (exit 0 = every format resolves)

WHY (9/11/26)
-------------
webull_options.expiry_to_date is the ONE place a date is decided, and it is
the most dangerous function in this folder: it does not fail loudly. A shape
it cannot read is refused upstream of the order, and the bridge then fills in
"this Friday" — so the bot buys a contract nobody called and nothing in the
log says it went wrong. trades.log has thirteen of those:

    "AUG 21" called  ->  AMZN 277.5C 2026-08-14 bought   (a week early)
    "AUG 28" called  ->  MRNA 110P  2026-08-21 bought
    "260814" called  ->  read as no date at all

Every case below is a real string out of trades.log or a room message, not an
invented one. If you add a format to the parser, add it here.
"""
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from webull_options import expiry_to_date                    # noqa: E402

FAILED = []
MON = dt.date(2026, 8, 3)        # a Monday, so every shape below is in future


def want(expiry, iso, today=MON):
    try:
        got = expiry_to_date(expiry, today=today)
    except Exception as e:                                   # noqa: BLE001
        got = "REFUSED: %s" % str(e)[:60]
    if got == iso:
        print("  OK    %-12r -> %s" % (expiry, got))
    else:
        print("  WRONG %-12r -> %s   (expected %s)" % (expiry, got, iso))
        FAILED.append(expiry)


def want_refused(expiry, today=MON):
    try:
        got = expiry_to_date(expiry, today=today)
    except Exception:                                        # noqa: BLE001
        print("  OK    %-12r -> refused, as it must be" % expiry)
        return
    print("  WRONG %-12r -> %s   (a guess; it should refuse)" % (expiry, got))
    FAILED.append(expiry)


def main():
    print("\nEXPIRY — every shape trades.log actually contains\n")
    # the bot's own ISO, which it used to hand itself and then refuse
    want("2026-08-07", "2026-08-07")
    want("2026-08-21", "2026-08-21")
    # slashes, with and without a year, zero-padded or not
    want("08/07/2026", "2026-08-07")
    want("8/7", "2026-08-07")
    want("08/05", "2026-08-05")
    want("9/18/26", "2026-09-18")
    # European day-first, which cost a META entry on 8/25
    want("26/8", "2026-08-26")
    # the month in the caller's own words, with and without an ordinal
    want("AUG 21", "2026-08-21")
    want("Aug 26", "2026-08-26")
    want("SEPT 14", "2026-09-14")
    want("Oct 16th", "2026-10-16")
    want("DEC 18", "2026-12-18")
    # YYMMDD, straight out of an OSI symbol (".SMCI260814C39.5")
    want("260814", "2026-08-14")
    want("260904", "2026-09-04")
    # the dotdate rooms' shape (Maguro: "$slv 63c 10.16 2.35")
    want("10.16", "2026-10-16")
    # N calendar days out, rolling BACK off a weekend, never past today
    want("0DTE", "2026-08-03")
    want("1DTE", "2026-08-04")
    want("5DTE", "2026-08-07")          # Saturday -> back to Friday
    want("6DTE", "2026-08-07")          # Sunday   -> back to Friday
    want("weekly", "2026-08-07")

    print("\n  and the ones that MUST still refuse — a guessed date is a\n"
          "  contract nobody called:\n")
    want_refused("next week")           # the bridge reads this from the text
    want_refused("swing")
    want_refused("2026-08-01")          # already in the past
    want_refused("2026-08-08")          # a Saturday: no such contract
    want_refused("13/40")               # not a date at all

    print()
    if FAILED:
        print("  %d FORMAT(S) WRONG. A date this reader cannot take is not a\n"
              "  skipped trade — the bridge fills in this Friday and buys the\n"
              "  wrong contract silently.\n" % len(FAILED))
        return 1
    print("  Every date shape in the log resolves, and every guess is refused.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
