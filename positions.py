"""
positions.py — the difference between "an order went out" and "you own it".

Until now those two were the same thing, and they could be: the entry crossed
the spread and filled in under a second, so writing the position down the
instant the order was sent was never wrong in practice.

Sitting on the bid breaks that. A resting bid is an offer, not a purchase. It
fills when a seller comes down to you, which on a call that runs straight from
the message is *never*. So there are now three things that can happen to an
entry, and only one of them means you're in:

    working   the bid is sitting there, nothing has happened yet
    filled    a seller took it, you own contracts, at a price this file knows
    nofill    the deadline passed, the order was pulled, you own nothing

Everything downstream depends on getting that right. If the browser thinks
you're holding SPY and you aren't, the next trim they post sends a sell for
contracts that don't exist, and the 20% stop is guarding an empty chair.

This file also holds the stop. Two of them, actually, because one can fail:

    the resting stop   a real STOP order sitting at Webull, off your fill
                       price. Works with your PC off, Chrome closed, this
                       program dead.
    the watchdog       a thread here checking the bid every few seconds.
                       Works when Webull won't take the resting stop, or when
                       the contract gaps straight through it.

Both can sell. Only one is allowed to. `claim()` is how that's decided, and
every path that closes a position goes through it — the watchdog, the resting
stop, and the room's own trim. Whoever gets there first wins and the others
find the door shut.

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


class Book:
    """Every entry this program has sent today, and what became of it.

    Thread-safe because three different things write to it: the HTTP handler
    when an order goes out, the fill watcher when it fills or doesn't, and the
    watchdog when the stop trips.
    """

    def __init__(self, wb, note, stop_pct=20.0, fill_seconds=90.0,
                 poll_seconds=5.0, simulated=False, wallet=None):
        self.wb = wb                    # the broker, or None in a dry run
        self.note = note                # bridge.note — writes to trades.log
        self.stop_pct = float(stop_pct)
        self.fill_seconds = float(fill_seconds)
        self.poll_seconds = max(1.0, float(poll_seconds))
        self.simulated = simulated
        self._lock = threading.RLock()
        self._pos = {}                  # symbol -> dict
        self._events = []               # things the extension hasn't seen yet
        self._seq = 0

        # The pretend account. Dry run only — with real money Webull is the
        # authority on what you've got and making up a second number that
        # disagrees with it would be worse than having none.
        #
        # It is a running balance, not a limit that gets checked. Cash leaves
        # when a bid actually fills, comes back at what you sold for, and what
        # is left is what the next entry has to fit inside. A static "can you
        # afford $280 out of $4,000" answers yes four times in a row and lets
        # you hold more than the account could ever have paid for.
        self.start_cash = None if wallet in (None, "", 0) else float(wallet)
        self.cash = self.start_cash
        self.reserved = 0.0             # bids that are out but haven't filled
        self.realised = 0.0             # profit and loss on trades that are over
        self.wins = 0
        self.losses = 0
        self.closed_trades = []         # [{symbol, qty, fill, exit, pl}]

    # -- writing things down --------------------------------------------------
    def _event(self, symbol, kind, text, qty=None):
        """`qty` is how many contracts you hold AFTER this happened.

        It's carried as a number on purpose. The browser has to decide whether
        you're still in the trade, and having it read that out of an English
        sentence would be one bad rewording away from selling something you
        don't own.
        """
        with self._lock:
            if qty is None:
                p = self._pos.get(symbol)
                qty = int(p.get("qty") or 0) if p else 0
            self._seq += 1
            self._events.append({"id": self._seq, "t": time.time(),
                                 "symbol": symbol, "kind": kind, "text": text,
                                 "qty": int(qty)})
            # A day of events is plenty and this lives in memory.
            if len(self._events) > 400:
                self._events = self._events[-400:]
        self.note("%-8s %s" % (kind.upper(), text))

    # -- the pretend account --------------------------------------------------
    @staticmethod
    def _dollars(price, qty):
        """One options contract is 100 shares. $2.80 is $280, and forgetting
        that by a factor of a hundred is the classic way to model an account
        that could afford everything."""
        return float(price or 0) * 100 * int(qty or 0)

    def available(self):
        """Spendable cash: what's left, minus the bids already out there.

        A resting bid is money you've promised. Not counting it lets four
        entries in a row each pass a check against the same $4,000."""
        with self._lock:
            if self.cash is None:
                return None
            return max(0.0, self.cash - self.reserved)

    def _reserve(self, sym, amount):
        with self._lock:
            if self.cash is None:
                return
            self.reserved += float(amount)
            p = self._pos.get(sym)
            if p:
                p["reserved"] = float(amount)

    def _unreserve(self, sym):
        with self._lock:
            if self.cash is None:
                return
            p = self._pos.get(sym)
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
            return {
                "start": round(self.start_cash, 2),
                "cash": round(self.cash, 2),
                "reserved": round(self.reserved, 2),
                "open_cost": round(open_cost, 2),
                "open_worth": round(worth, 2) if priced and open_cost else None,
                "realised": round(self.realised, 2),
                "equity": round(self.cash + (worth if priced else open_cost), 2),
                "wins": self.wins,
                "losses": self.losses,
                "trades": list(self.closed_trades[-40:]),
            }

    def snapshot(self, since=0):
        """What the extension asks for. `since` is the last event id it saw."""
        with self._lock:
            return {
                "positions": {k: dict(v, occ=None) for k, v in self._pos.items()},
                "events": [e for e in self._events if e["id"] > int(since or 0)],
                "wallet": self.wallet(),
                "seq": self._seq,
            }

    def holding(self, symbol):
        with self._lock:
            p = self._pos.get(str(symbol).upper())
            return bool(p and p.get("state") in HOLDING)

    def state_of(self, symbol):
        with self._lock:
            p = self._pos.get(str(symbol).upper())
            return p.get("state") if p else None

    def open_count(self):
        """Positions that are still live — held, or with a bid still resting."""
        with self._lock:
            return sum(1 for p in self._pos.values()
                       if p.get("state") in (WORKING, FILLED))

    def info(self, symbol):
        """A copy of what's known about a position, for callers that need a
        number off it — their posted entry price, the last bid seen — without
        reaching into the book and holding the lock while they think."""
        with self._lock:
            p = self._pos.get(str(symbol).upper())
            return dict(p) if p else None

    def qty_of(self, symbol):
        """How many contracts you actually own. Not how many were ordered —
        an exit priced off the wrong one of those two is how you end up
        selling short."""
        with self._lock:
            p = self._pos.get(str(symbol).upper())
            return int(p.get("qty") or 0) if p else 0

    # -- an entry goes out ----------------------------------------------------
    def entry_sent(self, order, ticket):
        """Called the moment Webull accepts the buy. Starts the watcher that
        decides whether this ever becomes a real position."""
        sym = str(order.get("symbol", "")).upper()
        with self._lock:
            prev = self._pos.get(sym) or {}
            # Averaging in: a second entry on something already held. Keep the
            # first fill price; the watcher adds to the quantity when it fills.
            adding = prev.get("state") == FILLED
            self._pos[sym] = {
                "symbol": sym,
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
                "their_price": order.get("limit"),
                "cost": float(prev.get("cost") or 0) if adding else 0.0,
                "last_bid": prev.get("last_bid") if adding else None,
                "reserved": 0.0,
                "sent_at": time.time(),
                "closing": False,
            }
        # Money out of the door the moment the bid is out, not when it fills.
        # It isn't spent yet, but it is promised, and it can't be promised twice.
        self._reserve(sym, self._dollars(ticket.get("limit"),
                                         ticket.get("qty") or 1))
        self._event(sym, "working",
                    "%s — bid is in at %.2f, waiting for a seller (%.0fs)"
                    % (sym, float(ticket.get("limit") or 0), self.fill_seconds))
        t = threading.Thread(target=self._watch_fill, args=(sym,), daemon=True)
        t.start()

    # -- did it fill? ---------------------------------------------------------
    def _watch_fill(self, sym):
        """Polls until the order fills or the deadline runs out.

        The deadline is the important half. An entry left resting all day can
        fill at 3:55pm into a trade the room called at 9:40 and was out of by
        10:05 — you'd be buying their exit. So it gets pulled."""
        deadline = time.time() + self.fill_seconds
        try:
            while time.time() < deadline:
                time.sleep(min(2.0, self.poll_seconds))
                with self._lock:
                    p = self._pos.get(sym)
                    if not p or p["state"] != WORKING:
                        return              # somebody else resolved it
                    oid, occ, limit = p["order_id"], p["occ"], p["limit"]
                    want = p["want_qty"]

                state, filled_qty, avg = self._probe(oid, occ, limit)
                if state == FILLED:
                    self._became_filled(sym, filled_qty or want, avg or limit)
                    return
                if state == "dead":
                    self._became_nofill(sym, "Webull cancelled or rejected it")
                    return
        except Exception as e:                          # noqa: BLE001
            self._event(sym, "failed",
                        "%s — lost track of the entry: %s. Check the Webull app."
                        % (sym, str(e)[:120]))
            with self._lock:
                if sym in self._pos:
                    self._pos[sym]["state"] = FAILED
            return

        # Deadline. Pull it — but check one last time, because it can fill in
        # the second between the last poll and the cancel going out.
        with self._lock:
            p = self._pos.get(sym)
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
            self._became_filled(sym, filled_qty or want, avg or limit)
        else:
            self._became_nofill(
                sym, "nobody sold at %.2f within %.0fs"
                     % (float(limit or 0), self.fill_seconds))

    def _probe(self, oid, occ, limit):
        """(state, filled_qty, avg_price) — from the broker for real, or from
        the live quote in a dry run."""
        if self.wb is None:
            # No broker at all. Nothing can be checked, so a dry run treats the
            # entry as filled at the price it would have bid, and the log says
            # so. This is the one place the dry run flatters itself, and it's
            # marked every time it happens.
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

    def _became_filled(self, sym, qty, price):
        with self._lock:
            p = self._pos.get(sym)
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
            side, strike, expiry = p["side"], p["strike"], p["expiry"]
        # Promised money becomes spent money. The debit is what you actually
        # paid, which is not always what you bid — a seller can come down
        # further than your price.
        paid = self._dollars(price, qty or 1)
        self._unreserve(sym)
        with self._lock:
            if self.cash is not None:
                self.cash -= paid
                p = self._pos.get(sym)
                if p:
                    p["cost"] = float(p.get("cost") or 0) + paid
        # With no broker at all there is nothing to ask, so the dry run assumed
        # this filled. Said out loud every single time, because an assumed fill
        # is the one number in the log that is not evidence of anything.
        assumed = ("" if self.wb is not None else
                   "  (assumed — no keys saved, so nothing checked whether "
                   "anyone would actually have sold to you)")
        left = self.available()
        money = ("" if left is None else
                 " — cost $%.0f, $%.0f left to trade with" % (paid, left))
        self._event(sym, "filled",
                    "%s — filled %s at %.2f%s%s%s" % (sym, qty, float(price),
                                                      "" if first else
                                                      " (now holding %d)" % total,
                                                      money, assumed))
        self._arm_stop(sym, side, strike, expiry, total, blended)

    def _became_nofill(self, sym, why):
        with self._lock:
            p = self._pos.get(sym)
            if not p or p["state"] != WORKING:
                return
        # Nothing was bought, so the money that was promised comes straight
        # back. Leaving it tied up would slowly starve the account of trades
        # over a morning of missed fills — which, sitting on the bid, is most
        # of them.
        self._unreserve(sym)
        with self._lock:
            p = self._pos.get(sym)
            if not p:
                return
            # Averaging in that never filled leaves the ORIGINAL position alone.
            # Only the new contracts failed to arrive.
            if p["qty"] > 0:
                p["state"] = FILLED
                self._event(sym, "nofill",
                            "%s — the add didn't fill (%s). You still hold %d."
                            % (sym, why, p["qty"]))
                return
            p["state"] = NOFILL
        self._event(sym, "nofill",
                    "%s — no fill (%s). You are NOT in this one." % (sym, why))

    # -- the stop -------------------------------------------------------------
    def _arm_stop(self, sym, side, strike, expiry, qty, fill):
        """Both halves of it. The resting order first, because that's the one
        that survives this program dying; the watchdog second, because that's
        the one that works when Webull won't take the resting order."""
        stop_price = max(0.01, round(float(fill) * (1 - self.stop_pct / 100), 2))
        oid = None
        if self.wb is not None and not self.simulated:
            with self._lock:
                p = self._pos.get(sym)
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
                self._event(sym, "stop-set",
                            "%s — stop resting at Webull at %.2f (-%.0f%% from "
                            "%.2f)" % (sym, stop_price, self.stop_pct, fill))
            except Exception as e:                      # noqa: BLE001
                # Not fatal, and it must not read as if you're unprotected —
                # the watchdog below is still running.
                self._event(sym, "stop-warn",
                            "%s — Webull wouldn't hold a resting stop (%s). The "
                            "watchdog on this PC is still on it, so keep this "
                            "program running." % (sym, str(e)[:90]))
        with self._lock:
            p = self._pos.get(sym)
            if p:
                p["stop"] = stop_price
                p["stop_order_id"] = oid
                if not p.get("watching"):
                    p["watching"] = True
                    threading.Thread(target=self._watchdog, args=(sym,),
                                     daemon=True).start()
        if self.simulated:
            self._event(sym, "stop-set",
                        "%s — pretend stop at %.2f (-%.0f%% from %.2f)"
                        % (sym, stop_price, self.stop_pct, fill))

    def _watchdog(self, sym):
        """Checks the bid. If it's at or under the stop, sells.

        This is the half that works when the resting stop was refused, and the
        half that catches a contract gapping straight through the trigger."""
        while True:
            time.sleep(self.poll_seconds)
            with self._lock:
                p = self._pos.get(sym)
                if not p or p["state"] != FILLED or p.get("closing"):
                    return
                occ, stop, qty = p["occ"], p["stop"], p["qty"]
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
                    q = self._pos.get(sym)
                    if q:
                        q["last_bid"] = float(bid)
            if bid is None or float(bid) > float(stop):
                continue
            if not self.claim(sym):
                return          # the resting stop or their trim got there first
            self._event(sym, "stopped",
                        "%s — bid hit %.2f, at or under your %.2f stop. Selling "
                        "%d." % (sym, float(bid), float(stop), qty))
            if self.simulated:
                self.finish(sym, STOPPED, "pretend stop-out at %.2f" % float(bid),
                            price=float(bid))
                return
            try:
                self.wb.sell(sym, side, strike, expiry, qty)
                self.finish(sym, STOPPED, "stopped out at %.2f" % float(bid),
                            price=float(bid))
            except Exception as e:                      # noqa: BLE001
                self._event(sym, "failed",
                            "%s — the stop tried to sell and couldn't: %s. Go "
                            "close it in the Webull app." % (sym, str(e)[:110]))
                self.finish(sym, FAILED, "stop failed to sell")
            return

    # -- one close, and only one ----------------------------------------------
    def claim(self, symbol):
        """Take ownership of closing this position. Returns False if something
        else already has it — that's the whole double-sell guard.

        Also pulls the resting stop, because selling on their trim while a stop
        order is still sitting at Webull is how you end up short a contract you
        never meant to sell."""
        sym = str(symbol).upper()
        with self._lock:
            p = self._pos.get(sym)
            if not p or p["state"] != FILLED or p.get("closing"):
                return False
            p["closing"] = True
            oid = p.get("stop_order_id")
            p["stop_order_id"] = None
        if oid and self.wb is not None and not self.simulated:
            try:
                self.wb.cancel(oid)
                self._event(sym, "stop-pulled",
                            "%s — pulled the resting stop before selling" % sym)
            except Exception:                           # noqa: BLE001
                self._event(sym, "stop-warn",
                            "%s — couldn't pull the resting stop. If it's still "
                            "in Webull after this sells, cancel it by hand."
                            % sym)
        return True

    def cancel_entry(self, symbol, why="pulled"):
        """Take a resting bid back off the book.

        This is the case sitting on the bid creates and crossing the spread
        never did: the room posts their trim while your entry is still sitting
        there unfilled. Leaving it would fill you into a trade they have
        already left. Returns how many contracts you still hold afterwards —
        zero if that bid was the whole position, and the count you were already
        holding if it was only an add on top of it.
        """
        sym = str(symbol).upper()
        with self._lock:
            p = self._pos.get(sym)
            if not p or p["state"] != WORKING:
                return self.qty_of(sym)
            oid = p["order_id"]
            held = int(p.get("qty") or 0)
            # An add that gets pulled leaves the original position exactly where
            # it was. Only the new contracts are gone.
            p["state"] = FILLED if held > 0 else NOFILL
        if oid and self.wb is not None and not self.simulated:
            try:
                self.wb.cancel(oid)
            except Exception:                           # noqa: BLE001
                self._event(sym, "stop-warn",
                            "%s — couldn't pull the resting bid. If it's still "
                            "in Webull, cancel it there by hand." % sym)
        self._event(sym, "pulled",
                    "%s — %s. The bid is off the book%s"
                    % (sym, why, "; you own nothing here." if not held
                       else "; you still hold %d." % held))
        return held

    def release(self, symbol):
        """The close didn't happen after all. Put it back."""
        with self._lock:
            p = self._pos.get(str(symbol).upper())
            if p:
                p["closing"] = False

    def finish(self, symbol, state, why, price=None):
        """The position is over. `price` is what you sold each contract for.

        Give it a price whenever one is known and the pretend account can tell
        you what the trade actually made. Leave it out and the money side goes
        quiet rather than guessing — a made-up exit price would turn the one
        number he's checking into fiction.
        """
        sym = str(symbol).upper()
        with self._lock:
            p = self._pos.get(sym)
            if not p:
                return
            qty = int(p.get("qty") or 0)
            cost = float(p.get("cost") or 0)
            entry = p.get("fill")
            if price is None:
                # No price was passed, but the watchdog has been keeping the
                # last bid it saw, and the bid is what you'd sell into.
                price = p.get("last_bid")
            p.update(state=state, closing=False, qty=0, closed_at=time.time())

        money = ""
        if self.cash is not None and qty and price is not None:
            got = self._dollars(price, qty)
            pl = got - cost
            with self._lock:
                self.cash += got
                self.realised += pl
                if pl >= 0:
                    self.wins += 1
                else:
                    self.losses += 1
                self.closed_trades.append(
                    {"symbol": sym, "qty": qty, "fill": entry,
                     "exit": round(float(price), 2), "pl": round(pl, 2),
                     "t": time.time()})
                pot = self.cash
            money = (" · %s$%.0f on the trade · account $%.0f"
                     % ("+" if pl >= 0 else "-", abs(pl), pot))
        elif self.cash is not None and qty:
            # Held contracts sold at a price nobody told us. The cash can't be
            # credited without inventing a number, so it says so instead of
            # quietly leaving the account short.
            money = " · sold, but at a price I never saw — account left as it was"
        self._event(sym, state, "%s — %s%s" % (sym, why, money))

    def sweep(self, older_than=1800):
        """Forget finished positions so the book doesn't grow all day."""
        now = time.time()
        with self._lock:
            for k in list(self._pos):
                p = self._pos[k]
                if p.get("state") in DONE and \
                        now - p.get("closed_at", p.get("sent_at", now)) > older_than:
                    self._pos.pop(k, None)
