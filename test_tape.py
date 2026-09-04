"""test_tape.py — the option tape must never have a hole where a real trade was.

WHY THIS FILE EXISTS (9/4/26)
-----------------------------
On 9/4 the bot traded NVDA 235C and INTC 94C, ratcheted the stop four times off
live bids, and took both out in profit. `option_tape.csv` recorded **not one
tick of either contract.** It did faithfully record 2,284 ticks of XLF — one of
G's own hand positions — every second, straight through the same window.

Two failures stacked, and both were silent:

  1. The bus was watching those contracts and the batched sweep kept coming
     back without them. A missing row wrote nothing and said nothing.
  2. The watchdog, finding nothing fresh on the bus, fell back to a direct
     ask_bid() — got a perfectly good quote, moved the stop on it, and threw
     the quote away instead of taping it.

Webull's API has NO historical option prices. option_tape.csv is the only
record that will ever exist of what our contracts printed, and it is the raw
material for every "should the stop have been wider" question G wants to ask.
A hole in it is a permanently unanswerable question.

WHAT THIS PROVES
  - With a totally blind sweep (fetch_many returns {}), a managed contract
    STILL gets taped, via the watchdog's direct-quote fallback.
  - The bus says so out loud, by contract name, instead of failing quietly.
  - `tape()` refuses a row with no prices in it (an empty quote is not data).

Run:  python3 test_tape.py
"""
import csv
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import quote_bus                                        # noqa: E402

FAILS = []


def ok(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("  FAIL  " + msg)


def _fixtures():
    """Reuse test_positions' fake broker and book so this file never drifts
    away from how the real book is actually built."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("tp", "test_positions.py")
    tp = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(tp)
    except SystemExit:                                  # its own __main__
        pass
    return tp


def test_blind_sweep_still_tapes():
    tp = _fixtures()
    said = []
    tape = tempfile.mktemp(suffix=".csv")

    # A bus whose batched sweep is BLIND — the exact 9/4 failure.
    bus = quote_bus.QuoteBus(lambda occs: {}, log=lambda *a: said.append(" ".join(str(x) for x in a)))
    bus.record_to(tape)
    bus._sweep_every = 0.05
    bus.start()
    try:
        wb = tp.FakeWB(fills=True, bid=3.00, ask=3.10)
        b = tp.book(wb)
        b.quotes = bus
        t = tp.ticket(wb, limit=2.77, qty=1, oid="1")
        b.entry_sent({"symbol": "NVDA", "side": "CALLS", "strike": 235.0,
                      "expiry": "2026-09-04", "qty": 1, "live": True,
                      "action": "OPEN"}, t)
        time.sleep(4.0)
    finally:
        bus.stop()

    occ = t["occ"]
    ok(occ in bus.watching(),
       "the armed contract is subscribed to the bus (got %s)" % bus.watching())

    rows = [r for r in csv.reader(open(tape)) if r and r[0] != "ts"]
    mine = [r for r in rows if r[1] == occ]
    ok(len(mine) >= 1,
       "a BLIND sweep still leaves ticks in the tape via the watchdog's "
       "direct fallback — got %d row(s) for %s" % (len(mine), occ))
    if mine:
        ok(float(mine[0][2]) == 3.00 and float(mine[0][3]) == 3.10,
           "the taped row carries the real bid/ask, got %s" % (mine[0][2:],))

    ok(any("BLIND" in s and occ in s for s in said),
       "the bus SAYS a watched contract is coming back empty, by name — "
       "said: %s" % (said or "nothing"))

    try:
        os.unlink(tape)
    except OSError:
        pass
    print("A blind sweep still tapes the trade, and the bus says it is blind.")


def test_tape_refuses_empty():
    tape = tempfile.mktemp(suffix=".csv")
    bus = quote_bus.QuoteBus(lambda occs: {})
    bus.record_to(tape)
    bus.tape("NVDA260904C00235000", None, None)
    rows = [r for r in csv.reader(open(tape)) if r and r[0] != "ts"]
    ok(not rows, "a quote with no bid AND no ask is not written (got %d)"
                 % len(rows))
    bus.tape("NVDA260904C00235000", 1.00, None)
    rows = [r for r in csv.reader(open(tape)) if r and r[0] != "ts"]
    ok(len(rows) == 1, "a bid-only quote IS written — a one-sided market is "
                       "still what printed (got %d)" % len(rows))
    try:
        os.unlink(tape)
    except OSError:
        pass
    print("An empty quote is not data; a one-sided quote is.")


if __name__ == "__main__":
    test_blind_sweep_still_tapes()
    test_tape_refuses_empty()
    print()
    if FAILS:
        print("FAILED %d check(s):" % len(FAILS))
        for f in FAILS:
            print("  - " + f)
        sys.exit(1)
    print("TAPE OK — every managed contract leaves a price record.")
