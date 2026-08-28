"""test_phantom_exit.py — a quote is not a fill.

The 8/26-8/27 books were wrong by $419 in one day because finish() filled a
missing exit price with the watchdog's last seen BID. Every case below is a
real position from those two days, with the real numbers:

    QQQ 709C   bot booked +$290, the broker printed 2.56 ->   +$8
    TSLA 350P  bot booked  +$70, its bracket stop printed 4.70 -> -$45
    SLV 62.5C  bot booked   -$5, its GTC stop printed 2.31 ->   -$42
    CDE 22C    bot booked  -$10, its GTC stop printed 1.10 ->   -$25

The rule this locks in: when a position vanishes from the account, ask the
broker what it sold for. If the broker answers, settle on that. If it doesn't,
say nothing about money — never credit a quote.

    python3 test_phantom_exit.py
"""

import time

import positions

bad = 0


def ok(cond, label):
    global bad
    if not cond:
        bad += 1
        print("  - " + label)


def quiet(_line):
    pass


class GoneWB:
    """A broker holding nothing, that knows what the contract last sold for.

    `sold_at=None` is the broker that won't answer — the case where the bot
    has to stay quiet instead of guessing.
    """

    def __init__(self, sold_at=2.56, bid=3.97):
        self.sold_at = sold_at
        self.bid = bid
        self.asked = []

    def ask_bid(self, occ):
        return self.bid, self.bid, {}

    def positions(self):
        return []                      # the whole point: it's gone

    def cancel(self, oid):
        return True

    def place_stop(self, *a, **kw):
        return "999", 1.00

    def last_sell_fill(self, symbol, side, strike, expiry, since=None):
        self.asked.append((symbol, side, strike, expiry))
        return self.sold_at


def held(b, key, sym, side, strike, expiry, qty, fill, live=True):
    """Put a filled position in the book by hand, the way a restore would."""
    with b._lock:
        b._pos[key] = {
            "symbol": sym, "side": side, "strike": strike, "expiry": expiry,
            "state": positions.FILLED, "qty": qty, "fill": fill,
            "cost": fill * 100 * qty, "mult": 100, "direction": 1,
            "kind": "option", "live": live, "who": "Gian",
            "last_bid": None, "filled_at": time.time() - 600,
            "sent_at": time.time() - 600, "entries": [], "exits": [],
        }


# The account is NOT empty — it just doesn't hold our contract any more. An
# all-empty sweep is deliberately ignored upstream (empty and unreachable look
# identical from there), so a decoy live row is what makes the sweep count.
DECOY = {"symbol": "AAPL", "side": "CALLS", "strike": 250.0,
         "expiry": "2026-09-18", "qty": 1, "live": True, "kind": "option"}


def vanish(b, key, wb, stale_bid):
    """Three sweeps of an account that no longer holds it = the bot calls it
    gone.

    The stale bid is planted first, exactly as the watchdog would have left it,
    so the test proves the bid is IGNORED rather than merely absent.
    """
    with b._lock:
        b._pos[key]["last_bid"] = stale_bid
    for _ in range(3):
        b.reconcile_gone([dict(DECOY)])
    return b._pos.get(key) or {}


CASES = [
    # label,        qty, entry, real fill, stale bid, phantom, truth
    ("QQQ 709C",      2,  2.52,      2.56,      3.97,   290.0,    8.0),
    ("TSLA 350P",     1,  5.15,      4.70,      5.85,    70.0,  -45.0),
    ("SLV 62.5C",     1,  2.73,      2.31,      2.68,    -5.0,  -42.0),
    ("CDE 22C",       1,  1.35,      1.10,      1.25,   -10.0,  -25.0),
]

print("--- the broker answers: settle on the printed fill ---")
for label, qty, entry, real, stale, phantom, truth in CASES:
    wb = GoneWB(sold_at=real, bid=stale)
    b = positions.Book(wb, quiet)
    b.cash = 0.0
    K = positions.key_of("Gian", label.split()[0])
    held(b, K, label.split()[0], "CALLS", 709, "2026-08-26", qty, entry)
    p = vanish(b, K, wb, stale)
    exits = p.get("exits") or []
    got = round(float(exits[0]["pl"]), 2) if exits else None
    ok(exits and abs(exits[0]["price"] - real) < 0.005,
       "%s must settle at the broker's %.2f, got %s"
       % (label, real, exits[0]["price"] if exits else None))
    ok(got is not None and abs(got - truth) < 0.5,
       "%s P&L must be %+.0f, got %s" % (label, truth, got))
    ok(got is None or abs(got - phantom) > 0.5,
       "%s must NOT reproduce the old phantom %+.0f" % (label, phantom))
    ok(wb.asked, "%s should have ASKED the broker for the fill" % label)
    ok(p.get("state") == positions.CLOSED, "%s ends closed" % label)

print("--- the broker won't answer: stay silent, never credit the bid ---")
for label, qty, entry, real, stale, phantom, truth in CASES:
    wb = GoneWB(sold_at=None, bid=stale)
    b = positions.Book(wb, quiet)
    b.cash = 0.0
    K = positions.key_of("Gian", label.split()[0])
    held(b, K, label.split()[0], "CALLS", 709, "2026-08-26", qty, entry)
    p = vanish(b, K, wb, stale)
    exits = p.get("exits") or []
    ok(not exits,
       "%s: with no broker answer nothing may be booked, got %s"
       % (label, exits))
    ok(abs(float(b.realised or 0)) < 0.005,
       "%s: an unknown exit must not move realised P&L, got %s"
       % (label, b.realised))
    ok(p.get("state") == positions.CLOSED,
       "%s: the trade still ends closed — silent about money, not stuck" % label)

print("--- a known price still settles normally ---")
wb = GoneWB(sold_at=None, bid=9.99)
b = positions.Book(wb, quiet)
b.cash = 0.0
K = positions.key_of("Gian", "SPY")
held(b, K, "SPY", "CALLS", 768, "2026-08-27", 3, 1.35, live=False)
b.finish(K, positions.CLOSED, "sold on their call", price=2.19)
p = b._pos.get(K) or {}
ok(p.get("exits") and abs(p["exits"][0]["pl"] - 252.0) < 0.5,
   "an explicit exit price must still book normally (+252), got %s"
   % (p.get("exits") or None))

if bad:
    print("\n%d phantom-exit check(s) failed." % bad)
    raise SystemExit(1)
print("Phantom exits: a vanished position asks the broker what it really sold "
      "for and settles on THAT; when the broker can't say, the money stays "
      "silent instead of crediting a stale bid; an explicit fill still books.")


# --- warning storms: say it once a minute, count the rest -------------------
# 8 identical QQQ ratchet lines in 45 seconds is what made tonight's log
# unreadable. The warning must still arrive — it just must not repeat itself
# into noise. Fills and exits are never folded.
lines = []
b = positions.Book(GoneWB(), lines.append)
K = positions.key_of("Gian", "QQQ")
held(b, K, "QQQ", "CALLS", 709, "2026-08-26", 1, 2.52)
for i in range(8):
    b._event(K, "stop-warn",
             "QQQ — up %d%%, but the ratchet couldn't move the resting stop "
             "to 3.5%d" % (55 + i, i))
warns = [l for l in lines if "STOP-WARN" in l]
ok(len(warns) == 1,
   "8 near-identical stop-warns in a burst should log once, got %d" % len(warns))
for i in range(3):
    b._event(K, "stopped", "QQQ — stopped out at 2.40")
ok(len([l for l in lines if "STOPPED" in l]) == 3,
   "real outcomes are never folded — all 3 stop-outs must show")
b._event(K, "stop-warn", "QQQ — a different problem entirely")
ok(len([l for l in lines if "STOP-WARN" in l]) == 2,
   "a genuinely different warning still gets through immediately")

if bad:
    print("\n%d check(s) failed." % bad)
    raise SystemExit(1)
print("Warning storms: a repeated stop-warn logs once a minute with a count, "
      "a different warning still gets through, and real outcomes never fold.")
