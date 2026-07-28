"""test_positions.py — does it know the difference between an order and a fill?

Every other test in here is about reading the room correctly. This one is about
what happens after: your entry goes in as a bid and sits there, and one of three
things happens to it. Get that wrong and the damage is quiet — the browser
believes you're holding SPY, the room posts a trim, and you send a sell for
contracts nobody ever sold you.

So the cases are the awkward ones on purpose:

  - it fills, and the 20% stop lands off YOUR price, not off theirs
  - nobody takes it and it gets pulled, leaving you flat and knowing it
  - their exit lands while the bid is still resting
  - an add fills on top of a position, and the stop moves to the blend
  - an add doesn't fill, and the original position is untouched
  - the bid drops through the stop and exactly one thing sells
  - and the pretend account moves: money tied up while a bid rests, spent when
    it fills, handed back when nobody takes it, credited at what you sold for

    python3 test_positions.py
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


class FakeWB:
    """A broker that does what you tell it to.

    `fills` decides whether an entry ever gets taken; `bid` is what the watchdog
    sees. Everything it was asked to do is written down so the test can check
    that the resting stop was really cancelled before the sell went out — that
    one is invisible from the outside and expensive to get wrong.
    """

    def __init__(self, fills=True, bid=3.00, ask=3.00):
        self.fills = fills
        self.bid = bid
        self.ask = ask
        self.calls = []
        self.next_id = 100
        self.limits = {}      # order id -> the price that order was bid at

    def ask_bid(self, occ):
        return self.ask, self.bid, {}

    def order_status(self, oid):
        self.calls.append(("status", oid))
        if self.fills:
            # You sat on the bid, so if it fills at all it fills at YOUR price.
            # The fake used to answer with today's ask for every order, which
            # made two entries at different prices look like the same trade and
            # hid the whole point of the averaging check.
            return positions.FILLED, 1, self.limits.get(str(oid), self.ask)
        return positions.WORKING, 0, None

    def cancel(self, oid):
        self.calls.append(("cancel", oid))
        return True

    def place_stop(self, symbol, side, strike, expiry, qty, fill_price):
        self.next_id += 1
        stop = max(0.01, round(float(fill_price) * 0.80, 2))
        self.calls.append(("stop", symbol, qty, stop))
        return str(self.next_id), stop

    def sell(self, symbol, side, strike, expiry, qty):
        self.calls.append(("sell", symbol, qty))
        return {"what": "SELL", "limit": self.bid}


def book(wb, **kw):
    kw.setdefault("fill_seconds", 1.0)
    kw.setdefault("poll_seconds", 0.2)
    return positions.Book(wb, quiet, **kw)


def ticket(wb=None, limit=2.77, qty=1, oid="1"):
    """The receipt bridge.py hands the book after Webull accepts an order.

    Passing `wb` tells the fake broker what that order was bid at, so a later
    fill comes back at that price and not at whatever the last one paid.
    """
    if wb is not None:
        wb.limits[str(oid)] = limit
    return {"order_id": oid, "occ": "SPY   250801C00745000", "limit": limit,
            "bid": limit, "ask": limit + 0.06, "qty": qty}


ORDER = {"symbol": "SPY", "side": "CALLS", "strike": 745, "expiry": "7/31",
         "limit": 2.80}


def settle(b, sym="SPY", seconds=3.0):
    """Wait for the watcher thread to reach a verdict."""
    end = time.time() + seconds
    while time.time() < end:
        if b.state_of(sym) not in (positions.WORKING,):
            return
        time.sleep(0.05)


# --- it fills ---------------------------------------------------------------
wb = FakeWB(fills=True, ask=2.77, bid=2.77)
b = book(wb)
b.entry_sent(ORDER, ticket(wb))
ok(b.state_of("SPY") == positions.WORKING,
   "the moment the order goes out you do NOT own it, got %s" % b.state_of("SPY"))
ok(not b.holding("SPY"), "a resting bid must not count as holding")
settle(b)
ok(b.state_of("SPY") == positions.FILLED, "a fill should leave you holding it")
ok(b.qty_of("SPY") == 1, "one contract, got %s" % b.qty_of("SPY"))
stops = [c for c in wb.calls if c[0] == "stop"]
ok(len(stops) == 1, "a fill should place exactly one resting stop, got %d" % len(stops))
# 20% off 2.77 is 2.22 — off YOUR fill, not off the 2.80 they posted.
ok(stops and abs(stops[0][3] - 2.22) < 0.005,
   "the stop goes 20%% under what you paid (2.22), got %s"
   % (stops[0][3] if stops else None))

# --- nobody takes it --------------------------------------------------------
wb = FakeWB(fills=False)
b = book(wb)
b.entry_sent(ORDER, ticket(wb))
settle(b)
ok(b.state_of("SPY") == positions.NOFILL,
   "an entry nobody took must end as nofill, got %s" % b.state_of("SPY"))
ok(not b.holding("SPY"), "a bid that never filled is not a position")
ok(b.qty_of("SPY") == 0, "and you hold none of it")
ok(any(c[0] == "cancel" for c in wb.calls),
   "the unfilled order has to be pulled, or it fills into their exit hours later")
ok(not any(c[0] == "stop" for c in wb.calls),
   "and nothing should be guarding a position you never had")

# --- their exit lands while your bid is still resting -----------------------
wb = FakeWB(fills=False)
b = book(wb, fill_seconds=30)
b.entry_sent(ORDER, ticket(wb))
held = b.cancel_entry("SPY", "they called the exit")
ok(held == 0, "pulling an unfilled entry leaves you holding nothing, got %s" % held)
ok(b.state_of("SPY") == positions.NOFILL, "and the book says so")
ok(any(c[0] == "cancel" for c in wb.calls), "the resting bid must actually be pulled")

# --- averaging in -----------------------------------------------------------
wb = FakeWB(fills=True, ask=2.00, bid=2.00)
b = book(wb)
b.entry_sent(ORDER, ticket(wb, limit=3.00))
settle(b)
first_stop_id = None
snap = b.snapshot()["positions"]["SPY"]
first_stop_id = snap["stop_order_id"]
ok(abs(snap["fill"] - 3.00) < 0.005, "first fill at 3.00, got %s" % snap["fill"])
# Second one is cheaper, which is the whole point of averaging in.
b.entry_sent(ORDER, ticket(wb, limit=2.00, oid="2"))
ok(b.state_of("SPY") == positions.WORKING,
   "an add is a resting bid too — it isn't yours until it fills")
ok(b.qty_of("SPY") == 1,
   "and while it rests you still hold only the one you already had, got %s"
   % b.qty_of("SPY"))
settle(b)
snap = b.snapshot()["positions"]["SPY"]
ok(b.qty_of("SPY") == 2, "after the add fills you hold two, got %s" % b.qty_of("SPY"))
ok(abs(snap["fill"] - 2.50) < 0.005,
   "the blend of 3.00 and 2.00 is 2.50, got %s" % snap["fill"])
ok(abs(snap["stop"] - 2.00) < 0.005,
   "the stop moves to 20%% under the blend (2.00), got %s" % snap["stop"])
ok(any(c[0] == "cancel" and c[1] == first_stop_id for c in wb.calls),
   "the old resting stop must be cancelled first, or two of them sell you out twice")

# --- an add that never fills leaves the original alone ----------------------
wb = FakeWB(fills=True, ask=3.00, bid=3.00)
b = book(wb)
b.entry_sent(ORDER, ticket(wb, limit=3.00))
settle(b)
wb.fills = False                     # the add gets no taker
b.entry_sent(ORDER, ticket(wb, limit=2.00, oid="2"))
settle(b)
ok(b.state_of("SPY") == positions.FILLED,
   "a failed add must not close the position you were already in, got %s"
   % b.state_of("SPY"))
ok(b.qty_of("SPY") == 1, "you still hold the original one, got %s" % b.qty_of("SPY"))

# --- the stop trips ---------------------------------------------------------
wb = FakeWB(fills=True, ask=3.00, bid=3.00)
b = book(wb, poll_seconds=0.2)
b.entry_sent(ORDER, ticket(wb, limit=3.00))
settle(b)
wb.bid = 2.30                        # 2.40 is the stop; this is through it
end = time.time() + 3
while time.time() < end and b.state_of("SPY") == positions.FILLED:
    time.sleep(0.05)
ok(b.state_of("SPY") == positions.STOPPED,
   "the watchdog should have sold it, got %s" % b.state_of("SPY"))
sells = [c for c in wb.calls if c[0] == "sell"]
ok(len(sells) == 1, "and sold it exactly once, got %d" % len(sells))
ok(not b.claim("SPY"),
   "once it's stopped out, nothing else may claim it — that's the double-sell guard")

# --- one close, and only one ------------------------------------------------
wb = FakeWB(fills=True, ask=3.00, bid=3.00)
b = book(wb)
b.entry_sent(ORDER, ticket(wb, limit=3.00))
settle(b)
ok(b.claim("SPY"), "their trim should be able to claim a position you hold")
ok(not b.claim("SPY"), "and nothing else may claim it at the same time")
ok(any(c[0] == "cancel" for c in wb.calls),
   "claiming has to pull the resting stop first, or it sells after you already did")
b.release("SPY")
ok(b.claim("SPY"), "a claim that came to nothing must hand the position back")
b.finish("SPY", positions.CLOSED, "sold on their call")
ok(b.qty_of("SPY") == 0 and not b.holding("SPY"), "and after selling you're flat")

# --- events carry a number, not a sentence ----------------------------------
kinds = [e["kind"] for e in b.snapshot()["events"]]
ok("filled" in kinds and "closed" in kinds,
   "the browser needs both halves of the story, got %s" % kinds)
ok(all("qty" in e for e in b.snapshot()["events"]),
   "every event says how many you hold afterwards, as a number")

# --- the pretend account actually moves -------------------------------------
# The $4,000 used to be a number that got compared against and never changed.
# Four $280 entries in a row all passed the same check and the account was never
# reported anywhere, which is exactly why it looked like it wasn't doing
# anything. It wasn't.
wb = FakeWB(fills=True, ask=3.00, bid=3.00)
b = book(wb, wallet=4000)
ok(b.available() == 4000, "it starts with what you gave it, got %s" % b.available())
b.entry_sent(ORDER, ticket(wb, limit=3.00))
# A resting bid is money promised. Not holding it back is how four entries all
# fit inside the same balance.
ok(abs(b.available() - 3700) < 0.5,
   "a $300 bid has to tie up $300 while it rests, got %s" % b.available())
settle(b)
ok(abs(b.available() - 3700) < 0.5,
   "and when it fills the same $300 is spent, not spent twice, got %s"
   % b.available())
w = b.wallet()
ok(abs(w["open_cost"] - 300) < 0.5, "$300 in the trade, got %s" % w["open_cost"])
ok(abs(w["equity"] - 4000) < 0.5,
   "cash plus what you're holding is still $4,000, got %s" % w["equity"])
b.claim("SPY")
b.finish("SPY", positions.CLOSED, "sold on their call", price=4.35)
ok(abs(b.available() - 4135) < 0.5,
   "sold at 4.35, so $435 comes back and you're at $4,135, got %s" % b.available())
w = b.wallet()
ok(abs(w["realised"] - 135) < 0.5, "+$135 banked, got %s" % w["realised"])
ok(w["wins"] == 1 and w["losses"] == 0, "and it counts as a win")

# A bid nobody took must hand the money straight back, or a morning of misses
# quietly starves the account.
wb = FakeWB(fills=False)
b = book(wb, wallet=1000)
b.entry_sent(ORDER, ticket(wb, limit=4.80))
ok(abs(b.available() - 520) < 0.5,
   "while the bid rests, $480 is tied up, got %s" % b.available())
settle(b)
ok(abs(b.available() - 1000) < 0.5,
   "nobody sold to you, so all of it comes back, got %s" % b.available())
ok(b.wallet()["realised"] == 0, "and nothing was made or lost on a trade you never had")

# Live mode has no pretend account at all. Webull is the only honest answer and
# a second made-up number that disagrees with it is worse than none.
b = book(FakeWB(), wallet=None)
ok(b.available() is None and b.wallet() is None,
   "with no starting balance there is no pretend account to report")

if bad:
    print("\n%d check(s) failed." % bad)
    raise SystemExit(1)
print("An order is not a fill, a fill sets the stop off your own price, and "
      "only one thing is ever allowed to sell.")
