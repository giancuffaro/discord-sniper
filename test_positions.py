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
  - two traders hold the same ticker at once and stay two separate trades
  - a trim sells 3 of 5 and the stop keeps guarding the other 2
  - the unlimited test account refuses nothing and reports the most cash that
    was ever tied up at once — the "how much would I need" number
  - and the old running account still moves: money tied up while a bid rests,
    spent when it fills, handed back when nobody takes it

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
        self.qtys = {}        # order id -> how many that order asked for

    def ask_bid(self, occ):
        return self.ask, self.bid, {}

    def order_status(self, oid):
        self.calls.append(("status", oid))
        if self.fills:
            # You sat on the bid, so if it fills at all it fills at YOUR price
            # and for the size YOU asked — a 5-lot that came back as 1 would
            # break every trim downstream.
            return (positions.FILLED, self.qtys.get(str(oid), 1),
                    self.limits.get(str(oid), self.ask))
        return positions.WORKING, 0, None

    def cancel(self, oid):
        self.calls.append(("cancel", oid))
        return True

    def place_stop(self, symbol, side, strike, expiry, qty, fill_price,
                    stop_price=None):
        self.next_id += 1
        stop = (max(0.01, round(float(stop_price), 2)) if stop_price is not None
                else max(0.01, round(float(fill_price) * 0.80, 2)))
        self.calls.append(("stop", symbol, qty, stop))
        return str(self.next_id), stop

    def sell(self, symbol, side, strike, expiry, qty, ref_price=None,
             urgent=False):
        # Mirrors the real client: urgent stop-outs cross the bid, and every
        # sell is trackable so the fill-confirmation loop (8/21) can verify.
        self.calls.append(("sell", symbol, qty))
        self.next_id += 1
        oid = str(self.next_id)
        self.limits[oid] = self.bid
        self.qtys[oid] = qty
        return {"what": "SELL", "limit": self.bid, "order_id": oid}


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
        wb.qtys[str(oid)] = qty
    return {"order_id": oid, "occ": "SPY   250801C00745000", "limit": limit,
            "bid": limit, "ask": limit + 0.06, "qty": qty}


# Every trade is a trader plus a ticker now. Brett's SPY is "brett|SPY", and
# Unraveler can hold "unraveler|SPY" at the same time without either trade
# touching the other. That's the multi-trader test further down.
ORDER = {"symbol": "SPY", "side": "CALLS", "strike": 745, "expiry": "7/31",
         "limit": 2.80, "trader": "Brett"}
K = positions.key_of("Brett", "SPY")


def settle(b, key=K, seconds=3.0):
    """Wait for the watcher thread to reach a verdict."""
    end = time.time() + seconds
    while time.time() < end:
        if b.state_of(key) not in (positions.WORKING,):
            return
        time.sleep(0.05)


# --- it fills ---------------------------------------------------------------
wb = FakeWB(fills=True, ask=2.77, bid=2.77)
b = book(wb)
b.entry_sent(ORDER, ticket(wb))
ok(b.state_of(K) == positions.WORKING,
   "the moment the order goes out you do NOT own it, got %s" % b.state_of(K))
ok(not b.holding(K), "a resting bid must not count as holding")
settle(b)
ok(b.state_of(K) == positions.FILLED, "a fill should leave you holding it")
ok(b.qty_of(K) == 1, "one contract, got %s" % b.qty_of(K))
# the stop is armed right AFTER the state flips to FILLED, on the fill
# thread — give it a beat (9/2: the symbol-aware tick lookup made this
# race visible; the book's order of operations is unchanged)
_t0 = time.time()
while time.time() - _t0 < 2.0 and not any(c[0] == "stop" for c in wb.calls):
    time.sleep(0.02)
stops = [c for c in wb.calls if c[0] == "stop"]
ok(len(stops) == 1, "a fill should place exactly one resting stop, got %d" % len(stops))
# 20% off 2.77 is 2.216 — off YOUR fill, not off the 2.80 they posted —
# and SPY quotes in PENNIES at every price (Penny Program, 9/2 reference),
# so it rests at 2.22, not the nickel-rounded 2.20 a non-penny name gets.
# The book hands the broker the exact tick-rounded price it will hold.
ok(stops and abs(stops[0][3] - 2.22) < 0.005,
   "the stop goes 20%% under what you paid, at SPY's penny tick (2.22), got %s"
   % (stops[0][3] if stops else None))

# --- nobody takes it --------------------------------------------------------
wb = FakeWB(fills=False)
b = book(wb)
b.entry_sent(ORDER, ticket(wb))
settle(b)
ok(b.state_of(K) == positions.NOFILL,
   "an entry nobody took must end as nofill, got %s" % b.state_of(K))
ok(not b.holding(K), "a bid that never filled is not a position")
ok(b.qty_of(K) == 0, "and you hold none of it")
ok(any(c[0] == "cancel" for c in wb.calls),
   "the unfilled order has to be pulled, or it fills into their exit hours later")
ok(not any(c[0] == "stop" for c in wb.calls),
   "and nothing should be guarding a position you never had")

# --- their exit lands while your bid is still resting -----------------------
wb = FakeWB(fills=False)
b = book(wb, fill_seconds=30)
b.entry_sent(ORDER, ticket(wb))
held = b.cancel_entry(K, "they called the exit")
ok(held == 0, "pulling an unfilled entry leaves you holding nothing, got %s" % held)
ok(b.state_of(K) == positions.NOFILL, "and the book says so")
ok(any(c[0] == "cancel" for c in wb.calls), "the resting bid must actually be pulled")

# --- averaging in -----------------------------------------------------------
wb = FakeWB(fills=True, ask=2.00, bid=2.00)
b = book(wb)
b.entry_sent(ORDER, ticket(wb, limit=3.00))
settle(b)
first_stop_id = None
snap = b.snapshot()["positions"][K]
first_stop_id = snap["stop_order_id"]
ok(abs(snap["fill"] - 3.00) < 0.005, "first fill at 3.00, got %s" % snap["fill"])
# Second one is cheaper, which is the whole point of averaging in.
b.entry_sent(ORDER, ticket(wb, limit=2.00, oid="2"))
ok(b.state_of(K) == positions.WORKING,
   "an add is a resting bid too — it isn't yours until it fills")
ok(b.qty_of(K) == 1,
   "and while it rests you still hold only the one you already had, got %s"
   % b.qty_of(K))
settle(b)
snap = b.snapshot()["positions"][K]
ok(b.qty_of(K) == 2, "after the add fills you hold two, got %s" % b.qty_of(K))
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
ok(b.state_of(K) == positions.FILLED,
   "a failed add must not close the position you were already in, got %s"
   % b.state_of(K))
ok(b.qty_of(K) == 1, "you still hold the original one, got %s" % b.qty_of(K))

# --- the stop trips ---------------------------------------------------------
wb = FakeWB(fills=True, ask=3.00, bid=3.00)
b = book(wb, poll_seconds=0.2)
b.entry_sent(ORDER, ticket(wb, limit=3.00))
settle(b)
wb.bid = 2.30                        # 2.40 is the stop; this is through it
# The stop now CONFIRMS its fill with the broker before recording (8/21 —
# a sell that never filled used to be booked as a stop-out), so give it the
# few polling seconds that honesty costs.
end = time.time() + 15
while time.time() < end and b.state_of(K) == positions.FILLED:
    time.sleep(0.05)
ok(b.state_of(K) == positions.STOPPED,
   "the watchdog should have sold it, got %s" % b.state_of(K))
sells = [c for c in wb.calls if c[0] == "sell"]
ok(len(sells) == 1, "and sold it exactly once, got %d" % len(sells))
ok(not b.claim(K),
   "once it's stopped out, nothing else may claim it — that's the double-sell guard")

# --- one close, and only one ------------------------------------------------
wb = FakeWB(fills=True, ask=3.00, bid=3.00)
b = book(wb)
b.entry_sent(ORDER, ticket(wb, limit=3.00))
settle(b)
ok(b.claim(K), "their trim should be able to claim a position you hold")
ok(not b.claim(K), "and nothing else may claim it at the same time")
ok(any(c[0] == "cancel" for c in wb.calls),
   "claiming has to pull the resting stop first, or it sells after you already did")
b.release(K)
ok(b.claim(K), "a claim that came to nothing must hand the position back")
b.finish(K, positions.CLOSED, "sold on their call")
ok(b.qty_of(K) == 0 and not b.holding(K), "and after selling you're flat")

# --- events carry a number, not a sentence ----------------------------------
kinds = [e["kind"] for e in b.snapshot()["events"]]
ok("filled" in kinds and "closed" in kinds,
   "the browser needs both halves of the story, got %s" % kinds)
ok(all("qty" in e for e in b.snapshot()["events"]),
   "every event says how many you hold afterwards, as a number")

# --- two traders, same ticker, two separate trades --------------------------
# The day this was built for: Brett is in SPY, Unraveler gets into SPY too, and
# Brett's "all out" must sell Brett's contracts and leave Unraveler's alone.
wb = FakeWB(fills=True, ask=3.00, bid=3.00)
b = book(wb)
b.entry_sent(ORDER, ticket(wb, limit=3.00, qty=5))
U = positions.key_of("Unraveler", "SPY")
b.entry_sent(dict(ORDER, trader="Unraveler", strike=750, limit=2.00),
             ticket(wb, limit=2.00, qty=5, oid="2"))
settle(b, K)
settle(b, U)
ok(b.qty_of(K) == 5 and b.qty_of(U) == 5,
   "both trades filled and both are separate, got %s and %s"
   % (b.qty_of(K), b.qty_of(U)))
ok(b.open_count() == 2, "two open trades in the same ticker, got %s"
   % b.open_count())
ok(b.find_by_symbol("SPY") and len(b.find_by_symbol("SPY")) == 2,
   "the book can list both SPY trades")
b.claim(K)
b.finish(K, positions.CLOSED, "Brett's all out", price=3.50)
ok(b.qty_of(K) == 0 and b.qty_of(U) == 5,
   "Brett's exit must not touch Unraveler's trade, got %s and %s"
   % (b.qty_of(K), b.qty_of(U)))

# --- a trim sells 3 of 5 and the trade stays open ----------------------------
wb = FakeWB(fills=True, ask=3.00, bid=3.00)
b = book(wb, unlimited=True)
b.entry_sent(ORDER, ticket(wb, limit=3.00, qty=5))
settle(b)
ok(b.qty_of(K) == 5, "in with 5, got %s" % b.qty_of(K))
sold = b.trim(K, 3, 3.60, "their trim —")
ok(sold == 3, "a trim sells 3, got %s" % sold)
ok(b.qty_of(K) == 2 and b.state_of(K) == positions.FILLED,
   "and you still hold 2 with the trade open, got %s %s"
   % (b.qty_of(K), b.state_of(K)))
w = b.wallet()
ok(abs(w["realised"] - 180) < 0.5,
   "3 sold at 3.60 against a 3.00 fill is +$180 banked, got %s" % w["realised"])
ok(w["wins"] == 0 and w["losses"] == 0,
   "a trim is not a finished trade — nothing is counted yet")
ok(b.claim(K), "the stop can still claim what's left after a trim")
b.release(K)
sold = b.trim(K, 3, 3.90, "their next trim —")
ok(sold == 2, "selling 3 when you hold 2 sells the 2, got %s" % sold)
ok(b.state_of(K) == positions.CLOSED,
   "trims that walk the whole position out finish the trade, got %s"
   % b.state_of(K))
w = b.wallet()
ok(w["wins"] == 1, "and NOW it counts, once, as one trade")
ok(abs(w["realised"] - 360) < 0.5,
   "+$180 then 2 at 3.90 (+$180) is +$360, got %s" % w["realised"])
rows = b.table()
ok(len(rows) == 1 and rows[0]["all_out"] and len(rows[0]["exits"]) == 2,
   "the table shows one finished trade with both partial sales on it")

# --- the unlimited account refuses nothing and reports the peak --------------
wb = FakeWB(fills=True, ask=3.00, bid=3.00)
b = book(wb, unlimited=True)
ok(b.available() is None,
   "unlimited means no money gate anywhere, got %s" % b.available())
b.entry_sent(ORDER, ticket(wb, limit=3.00, qty=5))            # $1,500
settle(b)
b.entry_sent(dict(ORDER, trader="Mike"), ticket(wb, limit=4.00, qty=5,
                                                oid="2"))     # +$2,000
settle(b, positions.key_of("Mike", "SPY"))
w = b.wallet()
ok(w.get("unlimited") is True, "the wallet says it's unlimited")
ok(abs(w["peak"] - 3500) < 0.5,
   "$1,500 and $2,000 held at once peaks at $3,500 — that's the funding "
   "number, got %s" % w["peak"])
b.claim(K)
b.finish(K, positions.CLOSED, "all out", price=3.20)
w = b.wallet()
ok(abs(w["peak"] - 3500) < 0.5,
   "selling later must not shrink the peak — it's a high-water mark, got %s"
   % w["peak"])

# --- the old running account still works ------------------------------------
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
b.claim(K)
b.finish(K, positions.CLOSED, "sold on their call", price=4.35)
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
print("An order is not a fill, two traders in one ticker are two trades, a "
      "trim sells 3 and keeps the stop on the rest, and only one thing is "
      "ever allowed to sell.")

# --- futures: points times multiplier, shorts profit downwards ---------------
# Felony's day: Short NQ @ 28660, 3 contracts. NQ is $20 a point. A trim at
# his "$1,100 a contract" means the market fell 55 points to 28605.
FUT = {"symbol": "NQ", "side": None, "strike": None, "expiry": None,
       "limit": 28660.0, "trader": "Felony", "kind": "future", "mult": 20,
       "direction": "SHORT", "their_stop": 29700.0, "their_target": 28550.0}
FK = positions.key_of("Felony", "NQ")
b = book(FakeWB(fills=True), unlimited=True)
b.entry_sent(FUT, {"order_id": None, "occ": None, "limit": 28660.0,
                   "bid": None, "ask": None, "qty": 3})
settle(b, FK)
ok(b.qty_of(FK) == 3, "in with 3 futures contracts, got %s" % b.qty_of(FK))
w = b.wallet()
ok(w["peak"] == 0 and w["open_cost"] == 0,
   "futures pay no premium, so nothing is tied up: peak %s cost %s"
   % (w["peak"], w["open_cost"]))
snap = b.snapshot()["positions"][FK]
ok(snap["stop"] == 29700.0, "the stop on record is THEIR level, got %s" % snap["stop"])
sold = b.trim(FK, 1, 28605.0, "their trim —")
ok(sold == 1, "futures trim sells one, got %s" % sold)
w = b.wallet()
ok(abs(w["realised"] - 1100) < 0.5,
   "55 points x $20 on a short is +$1,100, got %s" % w["realised"])
b.claim(FK)
b.finish(FK, positions.CLOSED, "all out", price=28575.0)
w = b.wallet()
ok(abs(w["realised"] - (1100 + 2 * 85 * 20)) < 0.5,
   "2 left at 85 points x $20 is +$3,400 more, total +$4,500, got %s"
   % w["realised"])
ok(w["wins"] == 1, "one finished futures trade, one win")

# A LONG loses when the price falls — direction has to flip the sign.
b = book(FakeWB(fills=True), unlimited=True)
b.entry_sent(dict(FUT, direction="LONG", limit=7500.0, symbol="ES", mult=50),
             {"order_id": None, "occ": None, "limit": 7500.0,
              "bid": None, "ask": None, "qty": 1})
EK = positions.key_of("Felony", "ES")
settle(b, EK)
b.claim(EK)
b.finish(EK, positions.CLOSED, "stopped", price=7480.0)
ok(abs(b.wallet()["realised"] - (-1000)) < 0.5,
   "long ES down 20 points x $50 is -$1,000, got %s" % b.wallet()["realised"])
ok(b.wallet()["losses"] == 1, "and it counts as a loss")

# The futures block above ran after the first verdict, so check again.
if bad:
    print("\n%d futures check(s) failed." % bad)
    raise SystemExit(1)
print("Futures: points times multiplier, shorts profit downwards, their stop "
      "on the record, no premium tied up.")


# --- a finished trade must survive a re-entry on the same key ---------------
# Day one, live: Unraveller stopped out of TSLA at 09:33 and was back in
# eleven minutes later. The new entry took the "unraveller|TSLA" slot in the
# working book before sweep() (which waits half an hour) ever filed the old
# one — the loss kept its money in the wallet but vanished from the table,
# which is why the popup showed a day of wins and none of the morning losses.
# This pins the fix: the finished trade goes to the archive the moment the
# key is reused.
wb = FakeWB(fills=True, ask=4.50, bid=4.50)
b = book(wb, unlimited=True)
TS = {"symbol": "TSLA", "side": "PUTS", "strike": 305, "expiry": "7/31",
      "limit": 4.50, "trader": "Unraveller"}
TK = positions.key_of("Unraveller", "TSLA")
b.entry_sent(TS, ticket(wb, limit=4.50, qty=5, oid="t1"))
settle(b, TK)
b.claim(TK)
b.finish(TK, positions.CLOSED, "stopped out", price=4.15)
b.entry_sent(dict(TS, limit=3.20), ticket(wb, limit=3.20, qty=5, oid="t2"))
settle(b, TK)
rows = [r for r in b.table() if r["symbol"] == "TSLA"]
ok(len(rows) == 2, "re-entering TSLA must not eat the finished trade — "
   "table has %d TSLA row(s), wanted 2" % len(rows))
done = [r for r in rows if r["all_out"]]
ok(len(done) == 1 and abs(done[0]["pl"] - (-175.0)) < 0.5,
   "and the finished row still says what it lost, got %s"
   % [r.get("pl") for r in done])

# --- midnight resets the scoreboard, not the holdings -----------------------
before_open = b.open_count()
b.new_day()
w = b.wallet()
ok(w["wins"] == 0 and w["losses"] == 0 and abs(w["realised"]) < 0.01,
   "a new day starts at zero, got %s up / %s down, realised %s"
   % (w["wins"], w["losses"], w["realised"]))
ok(all(not r["all_out"] for r in b.table()),
   "yesterday's finished trades are off today's table")
ok(b.open_count() == before_open,
   "but what you're holding carries over: %s -> %s"
   % (before_open, b.open_count()))

# --- reset_paper_daily clears the paper book, never a live hold -------------
b.reset_paper_daily = True
b._pos["papertrader|AAPL"] = {"state": positions.FILLED, "live": False,
                              "paper": True, "closing": False, "symbol": "AAPL"}
b._pos["livetrader|SPY"] = {"state": positions.FILLED, "live": True,
                            "paper": False, "closing": False, "symbol": "SPY"}
b.new_day()
left = sorted(b._pos)
ok("livetrader|SPY" in left and "papertrader|AAPL" not in left,
   "midnight clears paper AAPL but keeps live SPY, left with %s" % left)

if bad:
    print("\n%d day-book check(s) failed." % bad)
    raise SystemExit(1)
print("A re-entry archives the finished trade instead of eating it, and "
      "midnight resets the scoreboard without touching what you hold.")


# --- a bid with no price must die at the deadline, not wait forever ---------
# Day two live: "TAKE 742C" went out with no posted price and no real quote.
# float(None) crashed the fill watcher, and the crash path forgot to change
# the state — so the popup said "waiting for a seller" from 11:15 to the
# close. Both halves are pinned here: no price -> the deadline pulls it, and
# a watcher that dies -> the bid is declared dead, never left WORKING.
wb = FakeWB(fills=True, ask=2.77, bid=2.77)
b = book(wb, unlimited=True, simulated=True)   # dry run WITH quotes, like live
NP = dict(ORDER, trader="Midas")
NK = positions.key_of("Midas", "SPY")
b.entry_sent(NP, {"order_id": None, "occ": "SPY   250801C00745000",
                  "limit": None, "bid": None, "ask": None, "qty": 5})
settle(b, NK)
ok(b.state_of(NK) in (positions.NOFILL, positions.FAILED),
   "a priceless bid must be pulled at the deadline, got %s" % b.state_of(NK))
ok(not b.holding(NK), "and you must not be counted as holding it")

# No quote feed AND no price: dead on arrival, honestly.
b2 = book(None, unlimited=True)
b2.entry_sent(NP, {"order_id": None, "occ": None, "limit": None,
                   "bid": None, "ask": None, "qty": 5})
settle(b2, NK)
ok(b2.state_of(NK) in (positions.NOFILL, positions.FAILED),
   "no quote and no price is dead on arrival, got %s" % b2.state_of(NK))
ok(not b2.holding(NK), "and holds nothing")

if bad:
    print("\n%d dead-bid check(s) failed." % bad)
    raise SystemExit(1)
print("A bid with no price dies at the deadline; a crashed watcher declares "
      "the bid dead instead of leaving it waiting forever.")


# --- his trim ladder: run our own exit on their entry -----------------------
# +10% trim, same stop. +20% trim, stop to breakeven. +30% trim, stop to +10%.
# Never sell below the 2 runners he wants left for the rooms' un-called moves.
# The rung fires on the live bid; the stop rides up with it whether or not
# there was room left to sell.
wb = FakeWB(fills=True, ask=4.00, bid=4.00)
b = book(wb)
LADORD = {"symbol": "SPY", "side": "CALLS", "strike": 745, "expiry": "7/31",
          "limit": 4.00, "trader": "Ladder"}
LK = positions.key_of("Ladder", "SPY")
b.ladder_on = True
b.ladder_keep = 2
wb.limits["9"] = 4.00
wb.qtys["9"] = 4
b.entry_sent(LADORD, {"order_id": "9", "occ": "SPY   250801C00745000",
                      "limit": 4.00, "bid": 4.00, "ask": 4.06, "qty": 4})
settle(b, LK)
ok(b.state_of(LK) == positions.FILLED and b.qty_of(LK) == 4,
   "start the ladder holding 4 at 4.00, got %s x%s"
   % (b.state_of(LK), b.qty_of(LK)))

def snap_stop(key):
    return b.snapshot()["positions"][key].get("stop")

# +10% -> bid 4.40. Sell one (4->3), stop unchanged (still ~3.20 = 20% under).
b.auto_ladder(LK, 4.40)
ok(b.qty_of(LK) == 3, "+10%% trims one, holds 3, got %s" % b.qty_of(LK))
ok(abs((snap_stop(LK) or 0) - 3.20) < 0.02,
   "+10%% leaves the stop where it was (3.20), got %s" % snap_stop(LK))

# +20% -> bid 4.80. Sell one (3->2), stop to breakeven (fill = 4.00).
b.auto_ladder(LK, 4.80)
ok(b.qty_of(LK) == 2, "+20%% trims to the 2 runners, got %s" % b.qty_of(LK))
ok(abs((snap_stop(LK) or 0) - 4.00) < 0.02,
   "+20%% moves the stop to breakeven (4.00), got %s" % snap_stop(LK))

# +30% -> bid 5.20. No room to sell (2 runners are protected), but the stop
# still ratchets to +10% = 4.40.
b.auto_ladder(LK, 5.20)
ok(b.qty_of(LK) == 2, "+30%% keeps the 2 runners, got %s" % b.qty_of(LK))
ok(abs((snap_stop(LK) or 0) - 4.40) < 0.02,
   "+30%% locks the stop at +10%% (4.40), got %s" % snap_stop(LK))

# Higher still — nothing new fires, the runners ride.
b.auto_ladder(LK, 6.00)
ok(b.qty_of(LK) == 2, "past +30%% the runners are left alone, got %s" % b.qty_of(LK))

# Off by default: a fresh book with the ladder off never trims itself.
wb2 = FakeWB(fills=True, ask=4.00, bid=4.00)
b3 = book(wb2)
ok(b3.ladder_on is False, "the ladder ships OFF")
wb2.limits["7"] = 4.00
wb2.qtys["7"] = 4
b3.entry_sent(dict(LADORD, trader="NoLad"),
              {"order_id": "7", "occ": "SPY   250801C00745000",
               "limit": 4.00, "bid": 4.00, "ask": 4.06, "qty": 4})
NL = positions.key_of("NoLad", "SPY")
settle(b3, NL)
b3.auto_ladder(NL, 6.00)
ok(b3.qty_of(NL) == 4, "ladder off means it never trims for you, got %s"
   % b3.qty_of(NL))

if bad:
    print("\n%d ladder check(s) failed." % bad)
    raise SystemExit(1)
print("Trim ladder: +10% trims and holds the stop, +20% goes to breakeven, "
      "+30% locks +10%, the 2 runners are never sold, and it's off unless "
      "you flip it on.")


# --- two-connection routing: live -> real account, everything else -> paper --
# The money-safety invariant. With both clients up, the book must manage a live
# position on the live client and a paper/test one on the paper client — and
# NOTHING that isn't explicitly live may ever resolve to the live client.
LIVEWB = FakeWB()
PAPERWB = FakeWB()
rb = book(PAPERWB)                     # default/primary broker = paper
rb.broker_resolver = lambda p: LIVEWB if p.get("live") else PAPERWB
ok(rb._wbfor({"live": True}) is LIVEWB, "a live position routes to the live client")
ok(rb._wbfor({"live": False}) is PAPERWB, "a test position routes to paper")
ok(rb._wbfor({}) is PAPERWB, "an unmarked position never touches the live client")
ok(rb._wbfor({"paper": True}) is PAPERWB, "a paper position routes to paper")
ok(rb._wbfor({"live": 0, "paper": 1}) is PAPERWB, "paper-not-live stays on paper")
# No resolver set -> the single default broker, exactly as before two-connection.
rb.broker_resolver = None
ok(rb._wbfor({"live": True}) is PAPERWB, "no resolver -> the one default broker")
# A resolver that throws must never crash a sell/stop — it falls back to default.
rb.broker_resolver = lambda p: (_ for _ in ()).throw(RuntimeError("boom"))
ok(rb._wbfor({"live": True}) is PAPERWB, "a broken resolver falls back to default, never crashes")

if bad:
    print("\n%d routing check(s) failed." % bad)
    raise SystemExit(1)
print("Two-connection routing: live positions go to the real account, "
      "everything else to paper, an unmarked position never reaches live, and "
      "a broken resolver falls back safely.")


# --- live-exit: a live position is managed for REAL even in a simulated book --
# The book can be simulated as a whole (dry run / paper test) yet hold ONE live
# position that must get a real resting stop and a real stop-sell, while paper
# and test positions stay simulated. _sim(p) keys on the same live flag the
# broker router uses, so client and management can never disagree.
sb = book(FakeWB(), simulated=True)
ok(sb._sim({"live": True}) is False, "a live position is never simulated")
ok(sb._sim({"paper": True}) is False,
   "a paper position is NOT simulated — paper is the Webull sandbox, a real "
   "broker, so its fills/stops/exits are placed there")
ok(sb._sim({}) is True, "an unmarked (pure dry-run) position follows the sim flag")

# A LIVE entry, in a simulated book, fills and gets a REAL resting stop.
LWB = FakeWB(fills=True, ask=2.00, bid=2.00)
lb = book(LWB, simulated=True)
lb.broker_resolver = lambda p: LWB
LWB.limits["9"] = 2.00; LWB.qtys["9"] = 1
ltk = ticket(LWB, limit=2.00, oid="9"); ltk["live"] = True
lb.entry_sent(dict(ORDER, trader="LiveGuy"), ltk)
LKEY = positions.key_of("LiveGuy", "SPY")
settle(lb, LKEY)
ok(lb.state_of(LKEY) == positions.FILLED, "the live entry fills, got %s" % lb.state_of(LKEY))
ok(any(c[0] == "stop" for c in LWB.calls),
   "a LIVE position gets a REAL resting stop even in a simulated book")

# A PAPER entry, same simulated book, fills AND gets a real resting stop — paper
# is the sandbox now, a real broker, so it's managed there just like live (only
# the account differs). No in-house sim for paper any more.
PWB = FakeWB(fills=True, ask=2.00, bid=2.00)
pb = book(PWB, simulated=True)
pb.broker_resolver = lambda p: PWB
PWB.limits["8"] = 2.00; PWB.qtys["8"] = 1
ptk = ticket(PWB, limit=2.00, oid="8"); ptk["paper"] = True
pb.entry_sent(dict(ORDER, trader="PaperGuy"), ptk)
PKEY = positions.key_of("PaperGuy", "SPY")
settle(pb, PKEY)
ok(pb.state_of(PKEY) == positions.FILLED, "the paper entry fills, got %s" % pb.state_of(PKEY))
ok(any(c[0] == "stop" for c in PWB.calls),
   "a PAPER position gets a REAL resting stop on the sandbox — broker-managed")

if bad:
    print("\n%d live-exit check(s) failed." % bad)
    raise SystemExit(1)
print("Live-exit: live AND paper positions both get real resting stops and real "
      "management on their own accounts; only a pure dry-run book simulates.")


# --- the ratchet (8/15, re-tuned 8/25): ---------------------------------------
# starts at -stop_pct like any other stop; once gain reaches take_profit_pct
# the stop arms EARLY at BREAKEVEN (lock 0 — the trade can't go red any more),
# and every further stop_pct of gain locks another stop_pct. Never sells
# outright on the way up, never loosens once it's locked. (The old first rung
# jumped straight to +stop_pct and left a +15%% winner free to ride back red.)
ok(positions.ratchet_locked_pct(19.9, 10, 20) is None,
   "below the first rung, nothing is locked yet")
ok(positions.ratchet_locked_pct(20.0, 10, 20) == 0,
   "right at +20%%, the stop goes to BREAKEVEN (locks +0%%)")
ok(positions.ratchet_locked_pct(25.0, 10, 20) == 0,
   "between rungs (+25%%) still at the last rung crossed — breakeven")
ok(positions.ratchet_locked_pct(30.0, 10, 20) == 10,
   "at +30%%, locked climbs to +10%%")
ok(positions.ratchet_locked_pct(30.0, 10, 20) == 10,
   "at +30%%, locked climbs to +10%% (same answer asked twice — no drift)")
ok(positions.ratchet_locked_pct(95.0, 10, 20) == 70,
   "no ceiling: a +95%% runner locks +70%% (rungs 20,30,...,90)")
ok(positions.ratchet_locked_pct(15.0, 20, 20) is None,
   "a broken bracket (take-profit <= stop) never ratchets, refuses instead")

RWB = FakeWB(fills=True, ask=2.00, bid=2.00)
rb = book(RWB)
rb.ratchet_on = True
rb.take_profit_pct = 20.0
rb.stop_pct = 10.0
RWB.limits["9"] = 2.00; RWB.qtys["9"] = 1
rtk = ticket(RWB, limit=2.00, oid="9")
rb.entry_sent(dict(ORDER, trader="RatchetGuy"), rtk)
RKEY = positions.key_of("RatchetGuy", "SPY")
settle(rb, RKEY)
ok(rb.state_of(RKEY) == positions.FILLED, "ratchet test entry fills")
# fill was 2.00 (RWB always fills at its own ask/bid). +20% is 2.40.
rb.auto_ratchet(RKEY, 2.39)
ok(rb.state_of(RKEY) == positions.FILLED,
   "below the first rung (+19.5%%), the position is untouched and still open")
stops_before = [c for c in RWB.calls if c[0] == "stop"]
rb.auto_ratchet(RKEY, 2.40)          # exactly +20%
ok(rb.state_of(RKEY) == positions.FILLED,
   "hitting +20%% does NOT close the position — the ratchet moves the stop, "
   "it never sells outright")
stops_after = [c for c in RWB.calls if c[0] == "stop"]
ok(len(stops_after) == len(stops_before) + 1,
   "the ratchet cancels the old resting stop and places exactly one new one")
new_stop = stops_after[-1][3]
# v3.5.0 TIERS (9/2): a $2+ fill arms at +10% with a +5% first lock and 5%
# rungs, so +20% = +15% locked = a 2.30 stop (the old 10/10 rule said BE).
# ANTI-CLIP (9/2): the $2+ tier would lock +15% at +20%, but the stop may
# never sit closer than 40% of the gain -> locked = 60% of 20 = +12% -> 2.24.
ok(abs(new_stop - 2.24) < 0.005,
   "at +20%% a $2.00 fill locks +12%% (tier +15%%, anti-clip caps at 60%% of gain) — 2.24, got %s" % new_stop)
ok(any(c[0] == "cancel" for c in RWB.calls),
   "the old stop order gets cancelled before the new one goes in")
# Price keeps climbing to +30% — the stop should walk up again, to +10%.
rb.auto_ratchet(RKEY, 2.60)
stops_30 = [c for c in RWB.calls if c[0] == "stop"]
ok(len(stops_30) == len(stops_after) + 1,
   "a further rung places another new stop")
ok(abs(stops_30[-1][3] - 2.36) < 0.005,
   "at +30%% anti-clip caps the lock at +18%% (60%% of 30) — a 2.36 stop, got %s" % stops_30[-1][3])
# Price dips back to +21% (still above the +20 rung, below the +30 rung) — the
# already-locked +20% stop must NOT be loosened back down to +10%.
rb.auto_ratchet(RKEY, 2.42)
stops_dip = [c for c in RWB.calls if c[0] == "stop"]
ok(len(stops_dip) == len(stops_30),
   "a dip that's still above the last-hit rung places no new (and no "
   "looser) stop")

if bad:
    print("\n%d ratchet check(s) failed." % bad)
    raise SystemExit(1)
print("Ratchet: below +20%% the position is untouched; +20%% walks the stop to "
      "BREAKEVEN instead of closing; +30%% locks +10%%; a dip that's still "
      "above the last rung never loosens the stop back down.")
