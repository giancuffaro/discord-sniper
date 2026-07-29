"""
positions.py — the difference between "an order went out" and "you own it".

Until now those two were the same thing, and they could be: the entry crossed
the spread and filled in under a second, so writing the position down the
instant the order was sent was never wrong in practice.

Sitting on the bid breaks that. A resting bid is an offer, not a purchase. It
fills when a seller comes down to you, which on a fast one is *never*. So there
are three things that can happen to an entry, and only one of them means you're
in:

    working   the bid is sitting there, nothing has happened yet
    filled    a seller took it, you own contracts, at a price this file knows
    nofill    the deadline passed, the order was pulled, you own nothing

Everything downstream depends on getting that right. If the browser thinks
you're holding SPY and you aren't, the next trim they post sends a sell for
contracts that don't exist, and the 20% stop is guarding an empty chair.

THE BOOK IS KEYED BY TRADER, NOT BY TICKER. This is new and it matters: Brett
and Unraveler can both be in SPY at the same time, on different contracts, and
they are two different trades. "all out" from Brett closes Brett's SPY and
touches nothing else. A book keyed by ticker alone would have blended them into
one position and sold the wrong man's trade — which is exactly what it used to
do the day both of them were in the same name.

This file also holds the stop. Two of them, actually, because one can fail:

    the resting stop   a real STOP order sitting at Webull, off your fill
                       price. Works with your PC off, Chrome closed, this
                       program dead.
    the watchdog       a thread here checking the bid every few seconds.
                       Works when Webull won't take the resting stop, or when
                       the contract gaps straight through it.

Both can sell. Only one is allowed to. `claim()` is how that's decided, and
every path that fully closes a position goes through it. A trim doesn't claim —
selling 3 of 5 leaves a position behind, and the stop has to keep guarding it.

Nothing in here talks to the browser. bridge.py exposes a snapshot over GET
/fills and the extension reconciles against it.
"""

import threading
import time


# The states a position can be in, and what each one means for whether the
# extension should believe you're holding something.
WORKING = "working"     # bid is resting. You do NOT own it yet.
FILLED = "filled"       # you own it.
NOFILL = "nofill"       # never filled, order pulled. You do NOT own it.
STOPPED = "stopped"     # the 20% stop sold it.
CLOSED = "closed"       # their trim sold it, or you did.
FAILED = "failed"       # something broke. Assume nothing; go look at Webull.

# States where you are actually holding contracts.
HOLDING = (FILLED,)
# States that are over and can be swept out of the book.
DONE = (NOFILL, STOPPED, CLOSED, FAILED)


def key_of(trader, symbol):
    """One trade = one trader + one ticker. "brett|SPY" and "unraveler|SPY"
    are different trades in the same name, which is the whole point."""
    who = str(trader or "?").strip().lower() or "?"
    return "%s|%s" % (who, str(symbol or "").upper())


class Book:
    """Every entry this program has sent today, and what became of it.

    Thread-safe because three different things write to it: the HTTP handler
    when an order goes out, the fill watcher when it fills or doesn't, and the
    watchdog when the stop trips.
    """

    def __init__(self, wb, note, stop_pct=20.0, fill_seconds=90.0,
                 poll_seconds=5.0, simulated=False, wallet=None,
                 unlimited=False):
        self.wb = wb                    # the broker, or None in a dry run
        self.note = note                # bridge.note — writes to trades.log
        self.stop_pct = float(stop_pct)
        self.fill_seconds = float(fill_seconds)
        self.poll_seconds = max(1.0, float(poll_seconds))
        self.simulated = simulated
        self._lock = threading.RLock()
        self._pos = {}                  # key ("trader|SYM") -> dict
        self._archive = []              # finished trades, kept for the table
        self._events = []               # things the extension hasn't seen yet
        self._seq = 0
        self.save_day = None            # bridge sets this; writes the day file

        # The account, and there are now two kinds of pretend one.
        #
        # unlimited: nothing is ever refused for money. Instead the book keeps
        # the HIGH-WATER MARK — the most cash that was tied up at any one
        # moment — because that is the actual answer to "how much would I need
        # to fund this". A cap answers "what fits in $4,000"; the mark answers
        # "what does the room's day cost to follow".
        #
        # a starting balance (wallet=N): the old running account. Kept because
        # the tests exercise it and because it's the right tool once he settles
        # on a real number.
        self.unlimited = bool(unlimited)
        if self.unlimited:
            self.start_cash = 0.0
            self.cash = 0.0             # net cash flow; goes negative in trades
        else:
            self.start_cash = None if wallet in (None, "", 0) else float(wallet)
            self.cash = self.start_cash
        self.reserved = 0.0             # bids that are out but haven't filled
        self.peak = 0.0                 # most money committed at once
        self.realised = 0.0             # profit and loss on trades that are over
        self.wins = 0
        self.losses = 0
        self.closed_trades = []         # [{key, who, symbol, qty, fill, exit, pl}]

    # -- writing things down --------------------------------------------------
    def _event(self, key, kind, text, qty=None):
        """`qty` is how many contracts you hold AFTER this happened.

        It's carried as a number on purpose. The browser has to decide whether
        you're still in the trade, and having it read that out of an English
        sentence would be one bad rewording away from selling something you
        don't own.
        """
        with self._lock:
            p = self._pos.get(key) or {}
            if qty is None:
                qty = int(p.get("qty") or 0)
            self._seq += 1
            self._events.append({"id": self._seq, "t": time.time(),
                                 "key": key, "symbol": p.get("symbol")
                                 or key.split("|")[-1],
                                 "who": p.get("who") or key.split("|")[0],
                                 "kind": kind, "text": text, "qty": int(qty)})
            # A day of events is plenty and this lives in memory.
            if len(self._events) > 400:
                self._events = self._events[-400:]
        self.note("%-8s %s" % (kind.upper(), text))
        # The day file on disk, rewritten after anything worth writing down.
        # This is what "look at how we did last Tuesday" reads later, so it is
        # kept current rather than written once at some end-of-day moment that
        # a crashed bridge never reaches.
        if self.save_day is not None:
            try:
                self.save_day()
            except Exception:                           # noqa: BLE001
                pass        # a full disk must not take down the trading path

    # -- the pretend account --------------------------------------------------
    @staticmethod
    def _dollars(price, qty):
        """One options contract is 100 shares. $2.80 is $280, and forgetting
        that by a factor of a hundred is the classic way to model an account
        that could afford everything."""
        return float(price or 0) * 100 * int(qty or 0)

    def _mark_peak(self):
        """The most money this day has had committed at once. Bids that are
        out count — that money is promised even before it's spent."""
        with self._lock:
            open_cost = sum(float(p.get("cost") or 0)
                            for p in self._pos.values()
                            if p.get("state") == FILLED)
            now = self.reserved + open_cost
            if now > self.peak:
                self.peak = now

    def available(self):
        """Spendable cash: what's left, minus the bids already out there.

        None means "don't gate on money" — either there's no account at all
        (live mode; Webull is the authority) or the account is unlimited on
        purpose and the peak tracker is doing the measuring instead."""
        with self._lock:
            if self.unlimited or self.cash is None:
                return None
            return max(0.0, self.cash - self.reserved)

    def _reserve(self, key, amount):
        with self._lock:
            if self.cash is None:
                return
            self.reserved += float(amount)
            p = self._pos.get(key)
            if p:
                p["reserved"] = float(amount)
        self._mark_peak()

    def _unreserve(self, key):
        with self._lock:
            if self.cash is None:
                return
            p = self._pos.get(key)
            held = float((p or {}).get("reserved") or 0)
            self.reserved = max(0.0, self.reserved - held)
            if p:
                p["reserved"] = 0.0

    def wallet(self):
        """The account as a number the popup can print. None in live mode,
        where Webull is the only honest answer."""
        with self._lock:
            if self.cash is None:
                return None
            open_cost = sum(float(p.get("cost") or 0) for p in self._pos.values()
                            if p.get("state") == FILLED)
            # Worth now, if there's a quote. Selling means hitting the bid, so
            # that's the price used — not the ask, which you'd never get.
            worth, priced = 0.0, True
            for p in self._pos.values():
                if p.get("state") != FILLED:
                    continue
                b = p.get("last_bid")
                if b is None:
                    priced = False
                    continue
                worth += self._dollars(b, p.get("qty"))
            out = {
                "cash": round(self.cash, 2),
                "reserved": round(self.reserved, 2),
                "open_cost": round(open_cost, 2),
                "open_worth": round(worth, 2) if priced and open_cost else None,
                "realised": round(self.realised, 2),
                "wins": self.wins,
                "losses": self.losses,
                "trades": list(self.closed_trades[-40:]),
            }
            if self.unlimited:
                # No balance to run down, so the useful numbers are what the
                # day made and what it would have cost to be there for it.
                out["unlimited"] = True
                out["peak"] = round(self.peak, 2)
                out["day"] = round(self.realised
                                   + (worth - open_cost if priced else 0.0), 2)
            else:
                out["start"] = round(self.start_cash, 2)
                out["equity"] = round(self.cash
                                      + (worth if priced else open_cost), 2)
            return out

    # -- the day as a table ---------------------------------------------------
    def _row(self, p):
        return {
            "key": p.get("key"),
            "who": p.get("who") or "?",
            "symbol": p.get("symbol"),
            "side": p.get("side"),
            "strike": p.get("strike"),
            "expiry": p.get("expiry"),
            "state": p.get("state"),
            "kind": p.get("kind") or "option",
            "direction": int(p.get("direction") or 1),
            "their_stop": p.get("their_stop"),
            "their_target": p.get("their_target"),
            "qty": int(p.get("qty") or 0),
            "avg": p.get("fill"),
            "adds": int(p.get("adds") or 0),
            "entries": list(p.get("entries") or []),
            "exits": list(p.get("exits") or []),
            "pl": round(float(p.get("trade_pl") or 0), 2),
            "their_avg": p.get("their_avg"),
            "their_units": p.get("their_units"),
            "opened": p.get("sent_at"),
            "closed": p.get("closed_at"),
            "all_out": p.get("state") in DONE,
        }

    def table(self):
        """Every trade of the day, open and finished, one row each — who
        called it, what you paid, every partial sale, and how it ended. This
        is what the popup's table and the day files are made of."""
        with self._lock:
            rows = [self._row(p) for p in self._pos.values()] + \
                   [self._row(p) for p in self._archive]
        rows.sort(key=lambda r: r.get("opened") or 0)
        return rows

    def snapshot(self, since=0):
        """What the extension asks for. `since` is the last event id it saw."""
        with self._lock:
            return {
                "positions": {k: dict(v, occ=None) for k, v in self._pos.items()},
                "events": [e for e in self._events if e["id"] > int(since or 0)],
                "wallet": self.wallet(),
                "table": self.table(),
                "seq": self._seq,
            }

    def holding(self, key):
        with self._lock:
            p = self._pos.get(key)
            return bool(p and p.get("state") in HOLDING)

    def state_of(self, key):
        with self._lock:
            p = self._pos.get(key)
            return p.get("state") if p else None

    def open_count(self):
        """Positions that are still live — held, or with a bid still resting."""
        with self._lock:
            return sum(1 for p in self._pos.values()
                       if p.get("state") in (WORKING, FILLED))

    def info(self, key):
        """A copy of what's known about a position, for callers that need a
        number off it — their posted entry price, the last bid seen — without
        reaching into the book and holding the lock while they think."""
        with self._lock:
            p = self._pos.get(key)
            return dict(p) if p else None

    def find_by_symbol(self, symbol):
        """Keys of every live trade in this ticker, any trader. For the one
        caller that has a symbol but no name — and if this returns more than
        one key, the right answer is to ask, not to pick."""
        sym = str(symbol or "").upper()
        with self._lock:
            return [k for k, p in self._pos.items()
                    if p.get("symbol") == sym
                    and p.get("state") in (WORKING, FILLED)]

    def qty_of(self, key):
        """How many contracts you actually own. Not how many were ordered —
        an exit priced off the wrong one of those two is how you end up
        selling short."""
        with self._lock:
            p = self._pos.get(key)
            return int(p.get("qty") or 0) if p else 0

    def their_add(self, key, new_avg):
        """They bought more and posted the new blended average. Written down so
        the NEXT add has the right starting point for the reverse math."""
        with self._lock:
            p = self._pos.get(key)
            if not p:
                return
            if new_avg:
                p["their_avg"] = float(new_avg)
            p["their_units"] = int(p.get("their_units") or 1) + 1

    # -- an entry goes out ----------------------------------------------------
    def entry_sent(self, order, ticket):
        """Called the moment Webull accepts the buy. Starts the watcher that
        decides whether this ever becomes a real position."""
        sym = str(order.get("symbol", "")).upper()
        key = key_of(order.get("trader"), sym)
        who = str(order.get("trader") or "?").strip() or "?"
        with self._lock:
            prev = self._pos.get(key) or {}
            # Averaging in: a second entry on something already held. Keep the
            # first fill price; the watcher adds to the quantity when it fills.
            adding = prev.get("state") == FILLED
            self._pos[key] = {
                "key": key,
                "who": who if not adding else (prev.get("who") or who),
                "symbol": sym,
                # Futures support. An options contract is 100 shares; NQ is
                # $20 a point, ES $50 — the multiplier is what turns a price
                # move into dollars, and getting it wrong is a 5x lie. A
                # short's profit runs the other way, so direction is -1 for
                # short, +1 for long, and every P/L line multiplies by it.
                "kind": order.get("kind") or "option",
                "mult": float(order.get("mult") or 100),
                "direction": -1 if str(order.get("direction") or ""
                                       ).upper() == "SHORT" else 1,
                # THEIR levels, when they posted them. The plan of record for
                # Felony's room: his stop and target run the trade, not the
                # flat 20%.
                "their_stop": (prev.get("their_stop") if adding
                               else order.get("their_stop")),
                "their_target": (prev.get("their_target") if adding
                                 else order.get("their_target")),
                "state": WORKING,
                "order_id": ticket.get("order_id"),
                "occ": ticket.get("occ"),
                "side": order.get("side"),
                "strike": order.get("strike"),
                "expiry": order.get("expiry"),
                "want_qty": int(ticket.get("qty") or 1),
                "qty": int(prev.get("qty", 0)) if adding else 0,
                "adds": int(prev.get("adds", 0)) + (1 if adding else 0),
                "limit": ticket.get("limit"),
                "bid_at_send": ticket.get("bid"),
                "ask_at_send": ticket.get("ask"),
                "fill": prev.get("fill") if adding else None,
                "stop": prev.get("stop") if adding else None,
                "stop_order_id": prev.get("stop_order_id") if adding else None,
                "their_price": (prev.get("their_price") if adding
                                else order.get("limit")),
                # Their side of the trade, for the reverse math on adds. Starts
                # at their posted entry and one unit; their_add() moves it.
                "their_avg": (prev.get("their_avg") if adding
                              else order.get("limit")),
                "their_units": prev.get("their_units", 1) if adding else 1,
                "cost": float(prev.get("cost") or 0) if adding else 0.0,
                "entries": list(prev.get("entries") or []) if adding else [],
                "exits": list(prev.get("exits") or []) if adding else [],
                "trade_pl": float(prev.get("trade_pl") or 0) if adding else 0.0,
                "last_bid": prev.get("last_bid") if adding else None,
                "reserved": 0.0,
                "sent_at": (prev.get("sent_at") if adding else time.time()),
                "closing": False,
                "watching": prev.get("watching", False),
            }
        # Money out of the door the moment the bid is out, not when it fills.
        # It isn't spent yet, but it is promised, and it can't be promised
        # twice. Futures reserve nothing here — there's no premium paid up
        # front, margin is the broker's ledger, and pretending premium math
        # applies would poison the peak-needed number.
        if (order.get("kind") or "option") != "future":
            self._reserve(key, self._dollars(ticket.get("limit"),
                                             ticket.get("qty") or 1))
        self._event(key, "working",
                    "%s — %s's call, bid is in at %.2f for %d, waiting for a "
                    "seller (%.0fs)"
                    % (sym, who, float(ticket.get("limit") or 0),
                       int(ticket.get("qty") or 1), self.fill_seconds))
        t = threading.Thread(target=self._watch_fill, args=(key,), daemon=True)
        t.start()

    # -- did it fill? ---------------------------------------------------------
    def _watch_fill(self, key):
        """Polls until the order fills or the deadline runs out.

        The deadline is the important half. An entry left resting all day can
        fill at 3:55pm into a trade the room called at 9:40 and was out of by
        10:05 — you'd be buying their exit. So it gets pulled."""
        deadline = time.time() + self.fill_seconds
        try:
            while time.time() < deadline:
                time.sleep(min(2.0, self.poll_seconds))
                with self._lock:
                    p = self._pos.get(key)
                    if not p or p["state"] != WORKING:
                        return              # somebody else resolved it
                    oid, occ, limit = p["order_id"], p["occ"], p["limit"]
                    want = p["want_qty"]

                state, filled_qty, avg = self._probe(oid, occ, limit)
                if state == FILLED:
                    self._became_filled(key, filled_qty or want, avg or limit)
                    return
                if state == "dead":
                    self._became_nofill(key, "Webull cancelled or rejected it")
                    return
        except Exception as e:                          # noqa: BLE001
            self._event(key, "failed",
                        "%s — lost track of the entry: %s. Check the Webull app."
                        % (key.split("|")[-1], str(e)[:120]))
            with self._lock:
                if key in self._pos:
                    self._pos[key]["state"] = FAILED
            return

        # Deadline. Pull it — but check one last time, because it can fill in
        # the second between the last poll and the cancel going out.
        with self._lock:
            p = self._pos.get(key)
            if not p or p["state"] != WORKING:
                return
            oid, occ, limit, want = (p["order_id"], p["occ"], p["limit"],
                                     p["want_qty"])
        if self.wb is not None and oid:
            try:
                self.wb.cancel(oid)
            except Exception:                           # noqa: BLE001
                pass
        state, filled_qty, avg = self._probe(oid, occ, limit)
        if state == FILLED or (filled_qty or 0) > 0:
            self._became_filled(key, filled_qty or want, avg or limit)
        else:
            self._became_nofill(
                key, "nobody sold at %.2f within %.0fs"
                     % (float(limit or 0), self.fill_seconds))

    def _probe(self, oid, occ, limit):
        """(state, filled_qty, avg_price) — from the broker for real, or from
        the live quote in a dry run."""
        if self.wb is None or not occ:
            # No broker, or no quotable contract — futures have no OCC symbol
            # and no quote feed yet. Nothing can be checked, so a dry run
            # treats the entry as filled at the price it would have bid, and
            # the log says so. This is the one place the dry run flatters
            # itself, and it's marked every time it happens.
            return FILLED, None, limit
        if self.simulated:
            # Keys are present and quotes are real, so a dry run can answer the
            # actual question: did anyone offer to sell at your bid? If the ask
            # comes down to your price, somebody would have.
            try:
                ask, bid, _ = self.wb.ask_bid(occ)
            except Exception:                           # noqa: BLE001
                return WORKING, 0, None
            if ask and float(ask) <= float(limit) + 0.0001:
                return FILLED, None, limit
            return WORKING, 0, None
        return self.wb.order_status(oid)

    def _became_filled(self, key, qty, price):
        with self._lock:
            p = self._pos.get(key)
            if not p or p["state"] not in (WORKING,):
                return
            first = p["qty"] == 0
            # Averaging in: the stop has to move to the blended price, or the
            # second contract is protected at the first one's level.
            total = p["qty"] + int(qty or 1)
            if first or not p.get("fill"):
                blended = float(price)
            else:
                blended = ((p["fill"] * p["qty"] + float(price) * int(qty or 1))
                           / max(1, total))
            p.update(state=FILLED, qty=total, fill=round(blended, 4),
                     filled_at=time.time())
            p.setdefault("entries", []).append(
                {"t": time.time(), "qty": int(qty or 1),
                 "price": round(float(price), 4)})
            sym = p["symbol"]
            side, strike, expiry = p["side"], p["strike"], p["expiry"]
        # Promised money becomes spent money. The debit is what you actually
        # paid, which is not always what you bid — a seller can come down
        # further than your price. Futures pay no premium; their money story
        # is all in the exit.
        with self._lock:
            p0 = self._pos.get(key)
            is_fut = bool(p0 and p0.get("kind") == "future")
        paid = 0.0 if is_fut else self._dollars(price, qty or 1)
        self._unreserve(key)
        with self._lock:
            if self.cash is not None and not is_fut:
                self.cash -= paid
                p = self._pos.get(key)
                if p:
                    p["cost"] = float(p.get("cost") or 0) + paid
        self._mark_peak()
        # With no broker at all there is nothing to ask, so the dry run assumed
        # this filled. Said out loud every single time, because an assumed fill
        # is the one number in the log that is not evidence of anything.
        assumed = ("" if self.wb is not None else
                   "  (assumed — no keys saved, so nothing checked whether "
                   "anyone would actually have sold to you)")
        left = self.available()
        money = ("" if left is None else
                 " — cost $%.0f, $%.0f left to trade with" % (paid, left))
        if left is None and self.unlimited:
            money = " — cost $%.0f" % paid
        if is_fut:
            money = " — futures: no premium out, the money moves at the exit"
        self._event(key, "filled",
                    "%s — filled %s at %.2f%s%s%s" % (sym, qty, float(price),
                                                      "" if first else
                                                      " (now holding %d)" % total,
                                                      money, assumed))
        self._arm_stop(key, side, strike, expiry, total, blended)

    def _became_nofill(self, key, why):
        with self._lock:
            p = self._pos.get(key)
            if not p or p["state"] != WORKING:
                return
            sym = p["symbol"]
        # Nothing was bought, so the money that was promised comes straight
        # back. Leaving it tied up would slowly starve the account of trades
        # over a morning of missed fills — which, sitting on the bid, is most
        # of them.
        self._unreserve(key)
        with self._lock:
            p = self._pos.get(key)
            if not p:
                return
            # Averaging in that never filled leaves the ORIGINAL position alone.
            # Only the new contracts failed to arrive.
            if p["qty"] > 0:
                p["state"] = FILLED
                self._event(key, "nofill",
                            "%s — the add didn't fill (%s). You still hold %d."
                            % (sym, why, p["qty"]))
                return
            p["state"] = NOFILL
            p["closed_at"] = time.time()
        self._event(key, "nofill",
                    "%s — no fill (%s). You are NOT in this one." % (sym, why))

    # -- the stop -------------------------------------------------------------
    def _arm_stop(self, key, side, strike, expiry, qty, fill):
        """Both halves of it. The resting order first, because that's the one
        that survives this program dying; the watchdog second, because that's
        the one that works when Webull won't take the resting order."""
        sym = key.split("|")[-1]
        with self._lock:
            pf = self._pos.get(key)
            if pf and pf.get("kind") == "future":
                # A futures trade runs on THEIR stop, written on the record.
                # There's no options-style resting stop to place and, until
                # the futures data subscription exists, no quote feed for a
                # watchdog to poll — so the book says plainly what's guarding
                # it: his level, acted on when the room says so.
                pf["stop"] = pf.get("their_stop")
                self._event(key, "stop-set",
                            "%s — running their stop%s; exits fire on their "
                            "calls" % (sym,
                                       "" if not pf.get("their_stop")
                                       else " at %g" % float(pf["their_stop"])))
                return
        stop_price = max(0.01, round(float(fill) * (1 - self.stop_pct / 100), 2))
        oid = None
        if self.wb is not None and not self.simulated:
            with self._lock:
                p = self._pos.get(key)
                old = p.get("stop_order_id") if p else None
            # Averaging in moves the stop, so the old one has to go first or
            # you end up with two resting sells and get flattened twice.
            if old:
                try:
                    self.wb.cancel(old)
                except Exception:                       # noqa: BLE001
                    pass
            try:
                oid, stop_price = self.wb.place_stop(sym, side, strike, expiry,
                                                     qty, fill)
                self._event(key, "stop-set",
                            "%s — stop resting at Webull at %.2f (-%.0f%% from "
                            "%.2f)" % (sym, stop_price, self.stop_pct, fill))
            except Exception as e:                      # noqa: BLE001
                # Not fatal, and it must not read as if you're unprotected —
                # the watchdog below is still running.
                self._event(key, "stop-warn",
                            "%s — Webull wouldn't hold a resting stop (%s). The "
                            "watchdog on this PC is still on it, so keep this "
                            "program running." % (sym, str(e)[:90]))
        with self._lock:
            p = self._pos.get(key)
            if p:
                p["stop"] = stop_price
                p["stop_order_id"] = oid
                if not p.get("watching"):
                    p["watching"] = True
                    threading.Thread(target=self._watchdog, args=(key,),
                                     daemon=True).start()
        if self.simulated:
            self._event(key, "stop-set",
                        "%s — pretend stop at %.2f (-%.0f%% from %.2f)"
                        % (sym, stop_price, self.stop_pct, fill))

    def _watchdog(self, key):
        """Checks the bid. If it's at or under the stop, sells what's left.

        This is the half that works when the resting stop was refused, and the
        half that catches a contract gapping straight through the trigger.
        After a trim it guards the remainder — 2 contracts still get a stop."""
        while True:
            time.sleep(self.poll_seconds)
            with self._lock:
                p = self._pos.get(key)
                if not p or p["state"] != FILLED or p.get("closing"):
                    return
                occ, stop, qty = p["occ"], p["stop"], p["qty"]
                sym = p["symbol"]
                side, strike, expiry = p["side"], p["strike"], p["expiry"]
            if self.wb is None or not occ or not stop:
                return
            try:
                _ask, bid, _row = self.wb.ask_bid(occ)
            except Exception:                           # noqa: BLE001
                continue        # a missed quote is not a reason to sell
            if bid is not None:
                # Kept so the account can be marked to market, and so a close
                # that arrives without a price still has a real number to use.
                with self._lock:
                    q = self._pos.get(key)
                    if q:
                        q["last_bid"] = float(bid)
            if bid is None or float(bid) > float(stop):
                continue
            if not self.claim(key):
                return          # the resting stop or their trim got there first
            self._event(key, "stopped",
                        "%s — bid hit %.2f, at or under your %.2f stop. Selling "
                        "%d." % (sym, float(bid), float(stop), qty))
            if self.simulated:
                self.finish(key, STOPPED, "pretend stop-out at %.2f" % float(bid),
                            price=float(bid))
                return
            try:
                self.wb.sell(sym, side, strike, expiry, qty)
                self.finish(key, STOPPED, "stopped out at %.2f" % float(bid),
                            price=float(bid))
            except Exception as e:                      # noqa: BLE001
                self._event(key, "failed",
                            "%s — the stop tried to sell and couldn't: %s. Go "
                            "close it in the Webull app." % (sym, str(e)[:110]))
                self.finish(key, FAILED, "stop failed to sell")
            return

    # -- selling part of it ---------------------------------------------------
    def trim(self, key, qty, price, why):
        """Sell some contracts and keep the rest. Returns how many were sold.

        This is what a trim IS now: they say "trimming", you sell 3 of your 5
        and stay in the trade with a stop still on the other 2. It does not go
        through claim() — claiming is for closes, and a trimmed position still
        needs the watchdog guarding what's left.

        Refuses (returns 0) without a price rather than settling at a made-up
        one. A partial sale at a fictional price would quietly poison the one
        number the whole day is being run to find out.
        """
        with self._lock:
            p = self._pos.get(key)
            if not p or p["state"] != FILLED or p.get("closing"):
                return 0
            held = int(p.get("qty") or 0)
            n = min(max(0, int(qty or 0)), held)
            if n <= 0:
                return 0
            if price is None:
                price = p.get("last_bid")
            if price is None:
                self._event(key, "stop-warn",
                            "%s — they trimmed, but there's no price to sell at "
                            "(no quote and no percentage). Still holding %d."
                            % (p["symbol"], held))
                return 0
            price = float(price)
            fill = float(p.get("fill") or price)
            # Futures: dollars = points moved x the contract multiplier, and
            # a short profits on the way DOWN — direction flips the sign.
            # Options keep the old premium arithmetic.
            mult = float(p.get("mult") or 100)
            dirn = int(p.get("direction") or 1)
            fut = p.get("kind") == "future"
            chunk_cost = 0.0 if fut else fill * mult * n
            pl = (price - fill) * mult * n * dirn
            got = pl if fut else price * mult * n
            p["qty"] = held - n
            p["cost"] = max(0.0, float(p.get("cost") or 0) - chunk_cost)
            p.setdefault("exits", []).append(
                {"t": time.time(), "qty": n, "price": round(price, 4),
                 "pl": round(pl, 2)})
            p["trade_pl"] = float(p.get("trade_pl") or 0) + pl
            if self.cash is not None:
                self.cash += got
                self.realised += pl
            left = p["qty"]
            sym = p["symbol"]
        self._event(key, "trimmed",
                    "%s — %s sold %d at %.2f (%s$%.0f on those), still holding "
                    "%d%s" % (sym, why, n, price, "+" if pl >= 0 else "-",
                              abs(pl), left,
                              "" if left else " — that trim was the lot"))
        if left == 0:
            # Their trims walked the whole position out the door. That's a
            # finished trade, and it should say so rather than sit at qty 0.
            self.finish(key, CLOSED, "their trims sold the last of it",
                        price=None, settle=False)
        return n

    # -- one close, and only one ----------------------------------------------
    def claim(self, key):
        """Take ownership of closing this position. Returns False if something
        else already has it — that's the whole double-sell guard.

        Also pulls the resting stop, because selling on their call while a stop
        order is still sitting at Webull is how you end up short a contract you
        never meant to sell."""
        with self._lock:
            p = self._pos.get(key)
            if not p or p["state"] != FILLED or p.get("closing"):
                return False
            p["closing"] = True
            sym = p["symbol"]
            oid = p.get("stop_order_id")
            p["stop_order_id"] = None
        if oid and self.wb is not None and not self.simulated:
            try:
                self.wb.cancel(oid)
                self._event(key, "stop-pulled",
                            "%s — pulled the resting stop before selling" % sym)
            except Exception:                           # noqa: BLE001
                self._event(key, "stop-warn",
                            "%s — couldn't pull the resting stop. If it's still "
                            "in Webull after this sells, cancel it by hand."
                            % sym)
        return True

    def cancel_entry(self, key, why="pulled"):
        """Take a resting bid back off the book.

        This is the case sitting on the bid creates and crossing the spread
        never did: the room posts their trim while your entry is still sitting
        there unfilled. Leaving it would fill you into a trade they have
        already left. Returns how many contracts you still hold afterwards —
        zero if that bid was the whole position, and the count you were already
        holding if it was only an add on top of it.
        """
        with self._lock:
            p = self._pos.get(key)
            if not p or p["state"] != WORKING:
                return self.qty_of(key)
            oid = p["order_id"]
            sym = p["symbol"]
            held = int(p.get("qty") or 0)
            # An add that gets pulled leaves the original position exactly where
            # it was. Only the new contracts are gone.
            p["state"] = FILLED if held > 0 else NOFILL
            if not held:
                p["closed_at"] = time.time()
        self._unreserve(key)
        if oid and self.wb is not None and not self.simulated:
            try:
                self.wb.cancel(oid)
            except Exception:                           # noqa: BLE001
                self._event(key, "stop-warn",
                            "%s — couldn't pull the resting bid. If it's still "
                            "in Webull, cancel it there by hand." % sym)
        self._event(key, "pulled",
                    "%s — %s. The bid is off the book%s"
                    % (sym, why, "; you own nothing here." if not held
                       else "; you still hold %d." % held))
        return held

    def release(self, key):
        """The close didn't happen after all. Put it back."""
        with self._lock:
            p = self._pos.get(key)
            if p:
                p["closing"] = False

    def finish(self, key, state, why, price=None, settle=True):
        """The position is over. `price` is what you sold each contract for.

        Give it a price whenever one is known and the pretend account can tell
        you what the trade actually made. Leave it out and the money side goes
        quiet rather than guessing — a made-up exit price would turn the one
        number he's checking into fiction.

        `settle=False` is for the caller that has already moved the money
        (trim() selling the last contracts) and only needs the trade marked
        finished and counted.
        """
        with self._lock:
            p = self._pos.get(key)
            if not p:
                return
            qty = int(p.get("qty") or 0)
            cost = float(p.get("cost") or 0)
            entry = p.get("fill")
            mult = float(p.get("mult") or 100)
            dirn = int(p.get("direction") or 1)
            fut = p.get("kind") == "future"
            sym = p.get("symbol") or key.split("|")[-1]
            who = p.get("who") or key.split("|")[0]
            if price is None:
                # No price was passed, but the watchdog has been keeping the
                # last bid it saw, and the bid is what you'd sell into.
                price = p.get("last_bid")
            p.update(state=state, closing=False, qty=0, closed_at=time.time())

        money = ""
        if settle and self.cash is not None and qty and price is not None:
            if fut:
                # Points times multiplier times direction. No premium came
                # back because none went out.
                pl = (float(price) - float(entry or price)) * mult * qty * dirn
                got = pl
            else:
                got = self._dollars(price, qty)
                pl = got - cost
            with self._lock:
                self.cash += got
                self.realised += pl
                p = self._pos.get(key)
                if p is not None:
                    p.setdefault("exits", []).append(
                        {"t": time.time(), "qty": qty,
                         "price": round(float(price), 4), "pl": round(pl, 2)})
                    p["trade_pl"] = float(p.get("trade_pl") or 0) + pl
                    p["cost"] = 0.0
                total = float((p or {}).get("trade_pl") or pl)
                if total >= 0:
                    self.wins += 1
                else:
                    self.losses += 1
                self.closed_trades.append(
                    {"key": key, "who": who, "symbol": sym, "qty": qty,
                     "fill": entry, "exit": round(float(price), 2),
                     "pl": round(total, 2), "t": time.time()})
                pot = self.cash
            money = (" · %s$%.0f on the trade · %s"
                     % ("+" if pl >= 0 else "-", abs(pl),
                        ("day so far %s$%.0f"
                         % ("+" if self.realised >= 0 else "-",
                            abs(self.realised))) if self.unlimited
                        else "account $%.0f" % pot))
        elif not settle:
            # trim() already banked the money chunk by chunk; just count it.
            with self._lock:
                p = self._pos.get(key)
                total = float((p or {}).get("trade_pl") or 0)
                if total >= 0:
                    self.wins += 1
                else:
                    self.losses += 1
                self.closed_trades.append(
                    {"key": key, "who": who, "symbol": sym, "qty": qty,
                     "fill": entry, "exit": None, "pl": round(total, 2),
                     "t": time.time()})
            money = (" · %s$%.0f on the whole trade"
                     % ("+" if total >= 0 else "-", abs(total)))
        elif self.cash is not None and qty:
            # Held contracts sold at a price nobody told us. The cash can't be
            # credited without inventing a number, so it says so instead of
            # quietly leaving the account short.
            money = " · sold, but at a price I never saw — account left as it was"
        self._event(key, state, "%s — %s%s" % (sym, why, money))

    def sweep(self, older_than=1800):
        """Move finished positions out of the working book so it doesn't grow
        all day. They stay in the archive — the table still shows the whole
        day, finished trades included; that's what it's FOR."""
        now = time.time()
        with self._lock:
            for k in list(self._pos):
                p = self._pos[k]
                if p.get("state") in DONE and \
                        now - p.get("closed_at", p.get("sent_at", now)) > older_than:
                    self._archive.append(self._pos.pop(k))
            if len(self._archive) > 200:
                self._archive = self._archive[-200:]
