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
# v3.5.0 (9/2, G: "live tomorrow"): tiered ratchet off what he PAID
from ratchet_tiers import (ratchet_locked_pct as tier_locked_pct,
                           ratchet_stop_price, ratchet_plan, anti_clip)


def _tick_step(px, sym=None):
    """Legal increment — symbol-aware since 9/2 (SPY/QQQ/IWM = $0.01 always;
    Penny Program names $0.01 under $3 / $0.05 above; else $0.05 / $0.10).
    Borrows webull_options' table when importable; falls back to the always-
    legal coarse grid so the book never NEEDS the broker module (test stubs)."""
    try:
        from webull_options import tick_step as _ts
        return _ts(px, sym)
    except Exception:                                   # noqa: BLE001
        return 0.05 if float(px) < 3.0 else 0.10


def _tick_round(px, sym=None):
    """Snap an option price to the exchange's legal increment (see
    _tick_step). Same snap webull_options.tick_round applies on the way to
    the broker, so the book, the log and the resting order agree."""
    try:
        p = float(px)
    except (TypeError, ValueError):
        return px
    if p <= 0:
        return _tick_step(0.01, sym)
    step = _tick_step(p, sym)
    snapped = round(round(p / step) * step, 2)
    return snapped if snapped > 0 else step



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


def ratchet_locked_pct(gain_pct, stop_loss_pct, take_profit_pct):
    """His rule (8/15): the trade runs the normal -stop_loss_pct/+take_profit_pct
    bracket to start, but once it reaches +take_profit_pct the stop WALKS UP
    instead of closing the position — locked at +stop_loss_pct profit first,
    then another +stop_loss_pct locked in for every further step of gain, where
    a step is (take_profit_pct - stop_loss_pct). 10%/20%: gain 20 -> lock +10,
    gain 30 -> lock +20, gain 40 -> lock +30, and so on with no ceiling — once a
    trade reaches the first rung it can never come back red.

    Returns the locked-in profit percentage (a positive number, the new stop
    is that far ABOVE entry), or None while gain hasn't reached take_profit_pct
    yet (the original bracket is still what's guarding it) or if the bracket
    is set up wrong (step <= 0 — take-profit at or below the stop makes no
    sense to ratchet, so this refuses rather than guess).

    A tiny epsilon absorbs float noise on the boundary: (2.40 - 2.00) / 2.00
    * 100 comes out 19.999999999999996 in real floating point, not a clean
    20.0, and a bid landing EXACTLY on the take-profit price must still ratchet
    — the alternative is silently skipping the very moment this exists for."""
    # 8/25, his change: the ratchet arms EARLY. At +take_profit_pct the stop
    # goes to BREAKEVEN (lock 0 — can't go red), and every further
    # stop_loss_pct of gain locks another stop_loss_pct: 10/10 -> +10% locks
    # BE, +20% locks +10, +30% locks +20, no ceiling. The old first rung
    # (+20% -> +10) skipped straight past breakeven and left a +15% winner
    # free to ride back to -10%.
    step = stop_loss_pct
    if step <= 0 or gain_pct is None or gain_pct < take_profit_pct - 1e-9:
        return None
    k = int((gain_pct - take_profit_pct + 1e-9) // step)
    return step * k


class Book:
    """Every entry this program has sent today, and what became of it.

    Thread-safe because three different things write to it: the HTTP handler
    when an order goes out, the fill watcher when it fills or doesn't, and the
    watchdog when the stop trips.
    """

    def _wait_label(self):
        """How long a resting bid gets, in plain words for the popup: '3 min'
        past two minutes, otherwise the raw seconds."""
        s = self.fill_seconds
        if s >= 120 and s % 60 == 0:
            return "%d min" % (s / 60)
        if s >= 120:
            return "%.1f min" % (s / 60)
        return "%.0fs" % s

    def __init__(self, wb, note, stop_pct=20.0, fill_seconds=180.0,
                 poll_seconds=5.0, simulated=False, wallet=None,
                 unlimited=False):
        self.wb = wb                    # the DEFAULT broker, or None in a dry run
        # Two-connection routing. When the bridge holds both a paper client and
        # a live client, it sets this to a function that, given a position dict,
        # returns the broker that owns it — the live account for a live
        # position, the paper account for a paper one. Left None (the common
        # case) every position uses self.wb, exactly as before.
        self.broker_resolver = None
        self.note = note                # bridge.note — writes to trades.log
        self.stop_pct = float(stop_pct)
        self.fill_seconds = float(fill_seconds)
        # v3.5.0: floor dropped 1.0 -> 0.2 — the quote bus makes a fast
        # watchdog cheap (one batched call feeds every position).
        self.poll_seconds = max(0.2, float(poll_seconds))
        self.simulated = simulated
        self._lock = threading.RLock()
        self._pos = {}                  # key ("trader|SYM") -> dict
        self._archive = []              # finished trades, kept for the table
        self._events = []               # things the extension hasn't seen yet
        self._seq = 0
        self.save_day = None            # bridge sets this; writes the day file
        self.reset_paper_daily = False  # bridge sets from settings; clear paper at NY midnight

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
        # The slice of realised that rests on ASSUMED fills — entries taken
        # with no broker connected, where nothing ever checked that a seller
        # existed at that price. Tracked separately so the day total can say
        # out loud how much of itself is assumption rather than evidence.
        self.realised_assumed = 0.0
        self.wins = 0
        self.losses = 0
        self.closed_trades = []         # [{key, who, symbol, qty, fill, exit, pl}]
        # Honest-fill + his two tactics. All inert until the bridge sets them
        # from settings, so the existing scoreboard doesn't shift underfoot.
        self.realistic = False          # subtract real fees per contract
        self.fee_option = 0.0
        self.fee_future = 0.0
        self.auto_be_on = False         # sell a slice at +N%, stop to breakeven
        self.auto_be_pct = 10.0
        self.auto_be_frac = 0.10
        # His one-click bracket: close the WHOLE position at +take_profit_pct.
        # Works on LIVE and paper (a real sell), unlike the sim-only tactics
        # above. The stop side of the bracket is the resting stop (stop_pct),
        # so setting both to 15 gives a tight +15% / -15% exit on one contract.
        # Contracts the BROKER keeps refusing to sell (an order still resting
        # on them that isn't ours to see). Keyed by contract, not by position
        # key, because the position gets rebuilt on every adoption pass and a
        # flag on it would be forgotten every 20 seconds.
        self.broker_blocked = set()
        # His replacement for the hard take-profit close (8/15): once a winner
        # reaches +take_profit_pct the stop walks up instead of the position
        # closing outright. See auto_ratchet() and ratchet_locked_pct(). Off
        # by default like every other tactic here — the bridge switches it on
        # from settings.
        self.ratchet_on = False
        # ...and how many times each contract has been refused. Same reason:
        # a counter on the position is wiped by the next adoption pass, so it
        # would never reach three and the loop would run all day.
        self.sell_fail_counts = {}
        self.take_profit_on = False
        self.take_profit_pct = 20.0
        # HIS trim ladder — run our own exit on their entry, because the
        # rooms don't always call their trims. Each rung: sell some at +at_pct
        # and (optionally) drag the stop to entry*(1+stop_to_pct/100). Keep a
        # couple of runners. His rule: +10% same stop, +20% breakeven,
        # +30% stop to +10%.
        self.ladder_on = False
        self.ladder_keep = 2            # never sell below this many runners
        self.ladder_rungs = [
            {"at": 10.0, "sell": 1, "stop_to": None},   # same stop
            {"at": 20.0, "sell": 1, "stop_to": 0.0},    # breakeven
            {"at": 30.0, "sell": 1, "stop_to": 10.0},   # lock +10%
        ]

    # -- writing things down --------------------------------------------------
    def _event(self, key, kind, text, qty=None):
        """`qty` is how many contracts you hold AFTER this happened.

        It's carried as a number on purpose. The browser has to decide whether
        you're still in the trade, and having it read that out of an English
        sentence would be one bad rewording away from selling something you
        don't own.
        """
        # WARNING STORMS (8/27): stop-warn fires from the watchdog loop, so a
        # condition that doesn't clear repeats every few seconds forever —
        # tonight it was 8 identical QQQ ratchet lines in 45 seconds, and on
        # 8/26 the TSLA 417 warned 4 times in 20. Same trade, same complaint,
        # nothing new to act on: say it once a minute and count the rest. The
        # repeat still comes (this is a real problem and must not go silent),
        # it just stops burying the lines he actually needs to see. Only
        # stop-warn is folded; fills, stops, exits and errors are never
        # touched.
        folded = 0
        if kind == "stop-warn":
            import re as _re
            sig = (key, _re.sub(r"[\d.]+", "#", str(text)))
            now = time.time()
            with self._lock:
                seen = getattr(self, "_warn_seen", None)
                if seen is None:
                    seen = self._warn_seen = {}
                last, n = seen.get(sig, (0.0, 0))
                if now - last < 60.0:
                    seen[sig] = (last, n + 1)
                    return                      # same gripe, still fresh
                seen[sig] = (now, 0)
                folded = n
            if folded:
                text = ("%s  (+%d more like this in the last minute)"
                        % (text, folded))
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

    def _greeks_now(self, p):
        """Live greeks for a position, trimmed to what is worth keeping, or
        None. Never raises and never blocks — the greeks feed is a nice-to-
        have that must never be able to delay an exit."""
        try:
            bus = getattr(self, "greeks", None)
            if bus is None or not p:
                return None
            g = bus.get(p.get("occ"))
            if not g:
                return None
            out = {}
            for k in ("delta", "gamma", "theta", "vega", "volatility",
                      "price"):
                v = g.get(k)
                if v is not None:
                    out["iv" if k == "volatility" else k] = round(float(v), 6)
            return out or None
        except Exception:                               # noqa: BLE001
            return None

    def _mark_excursion(self, key, bid):
        """The furthest a position ever ran green and the furthest it ever went
        red, as a % from the entry fill (his ask, 8/19: 'the lowest the
        position was, -8%, and the highest'). Marked to the same live bid the
        stop and ratchet watch, every poll. direction flips it for a short so a
        futures short shows +% when price falls. Stored on the position, so it
        rides into the day file and the journal when the trade closes."""
        with self._lock:
            p = self._pos.get(key)
            if not p:
                return
            try:
                base = float(p.get("fill"))
            except (TypeError, ValueError):
                return
            if not base:
                return
            d = int(p.get("direction") or 1)
            pct = d * (float(bid) - base) / base * 100.0
            hi, lo = p.get("hi_pct"), p.get("lo_pct")
            if hi is None or pct > hi:
                p["hi_pct"] = pct
            if lo is None or pct < lo:
                p["lo_pct"] = pct

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
            "live": bool(p.get("live")),
            "room": p.get("room"),
            "opened": p.get("sent_at"),
            "closed": p.get("closed_at"),
            "all_out": p.get("state") in DONE,
            "manual": bool(p.get("manual_close")),
            # The alert word for word, win/loss as a PERCENT, and WHAT pulled
            # the exit trigger — his asks (8/17) for the journal that shows
            # which traders and rooms are worth following.
            "raw": p.get("raw"),
            "pl_pct": (round(100.0 * float(p.get("trade_pl") or 0)
                              / float(p.get("cost")), 1)
                       if p.get("cost") else None),
            "exit_by": self._exit_by(p),
            "swing": bool(p.get("swing")),
            # How far the trade ever ran green / red from entry (his ask, 8/19).
            "hi_pct": (round(float(p["hi_pct"]), 1)
                       if p.get("hi_pct") is not None else None),
            "lo_pct": (round(float(p["lo_pct"]), 1)
                       if p.get("lo_pct") is not None else None),
        }

    @staticmethod
    def _exit_by(p):
        st = p.get("state")
        if st not in DONE or st == NOFILL:
            return ""
        why = str(p.get("closed_why") or "")
        if p.get("manual_close"):
            return ("you at Webull (or your resting stop filled)"
                    if p.get("stop_order_id") else "you at Webull")
        if "take-profit" in why:
            return "bot take-profit"
        if st == STOPPED:
            return "bot stop"
        if st == FAILED:
            return "failed"
        return "room call"

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

    def cancel_working_for(self, trader):
        """RETRACTION (8/26): the trader said 'not ready / revising' — pull
        every resting bid of theirs off the book and the broker. Returns the
        symbols pulled."""
        who = str(trader or "").strip().lower()
        pulled = []
        with self._lock:
            keys = [k for k, p in self._pos.items()
                    if p.get("state") == WORKING
                    and (not who or who in str(p.get("who") or k).lower())]
        for k in keys:
            try:
                self.cancel_entry(k, "the trader pulled the call back")
                pulled.append(k.split("|")[-1])
            except Exception:                           # noqa: BLE001
                pass
        return pulled

    def stop_to_breakeven(self, key):
        """BE STOPS (G, 8/29: "you can use breakeven stops, guys") — the
        resting premium stop moves to the ENTRY fill: from here the trade
        can scratch but never lose. Rides the existing cancel+replace in
        _arm_stop by feeding it the price whose -stop_pct lands exactly on
        the fill. Swings on a stock-level stop are left to that watcher."""
        with self._lock:
            p = self._pos.get(key)
            if not p or p.get("state") != FILLED:
                return False
            if p.get("swing") and p.get("their_stop"):
                return False
            f = float(p.get("fill") or 0)
            side, strike = p.get("side"), p.get("strike")
            expiry, qty = p.get("expiry"), int(p.get("qty") or 1)
        if not f:
            return False
        adj = f / (1 - self.stop_pct / 100.0)
        try:
            self._arm_stop(key, side, strike, expiry, qty, adj)
        except Exception:                               # noqa: BLE001
            return False
        return True

    def set_their_stop(self, key, level):
        """STOPMOVE (8/29): the trader spoke a new stock-level stop; the
        running underlying watcher reads this field every pass."""
        with self._lock:
            p = self._pos.get(key)
            if p is not None:
                p["their_stop"] = float(level)
                return True
        return False

    def restart_exposure(self):
        """What a restart would interrupt, for the pre-restart check (8/26):
        held positions are SAFE (their stops rest at the broker and the book
        restores), but a WORKING bid loses its 90s puller and an armed
        pullback hunt dies silently. Names included so the warning can say
        exactly what's at stake."""
        with self._lock:
            held = [p.get("symbol") for p in self._pos.values()
                    if p.get("state") == FILLED]
            working = [p.get("symbol") for p in self._pos.values()
                       if p.get("state") == WORKING]
        return held, working

    def info(self, key):
        """A copy of what's known about a position, for callers that need a
        number off it — their posted entry price, the last bid seen — without
        reaching into the book and holding the lock while they think."""
        with self._lock:
            p = self._pos.get(key)
            return dict(p) if p else None

    @staticmethod
    def is_hand_trade(p):
        """HIS OWN position (9/2, G: "how do they manage to close them? they
        shouldn't"): adopted off the account with no bot record to inherit
        credit from — the book names it "Gian". Visible in the popup, never
        stop-managed, and now never resolvable by any room's exit or trim.
        A bot trade re-found after a restart carries its trader's name and
        is not this."""
        if not p or not p.get("adopted"):
            return False
        who = str(p.get("who") or "").strip().lower()
        return who in ("", "?", "gian")

    def find_by_symbol(self, symbol, rooms=False):
        """Keys of every live trade in this ticker, any trader. For the one
        caller that has a symbol but no name — and if this returns more than
        one key, the right answer is to ask, not to pick.
        rooms=True is the view a ROOM's call gets: his own hand trades are
        left out, so "out SPY" can never land on them."""
        sym = str(symbol or "").upper()
        with self._lock:
            return [k for k, p in self._pos.items()
                    if p.get("symbol") == sym
                    and p.get("state") in (WORKING, FILLED)
                    and not (rooms and self.is_hand_trade(p))]

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
            # Per-room live now. A position knows whether it is real money —
            # the fill watcher probes Webull for live ones and the quote feed
            # for test ones, and the pretend wallet only ever counts the
            # pretend positions.
            is_live = bool(ticket.get("live") or order.get("live"))
            # Paper = Webull's simulated fill (probe the broker for the real
            # price) BUT still counts in the per-room scoreboard, because it's
            # pretend money by definition. So it is NOT "live" for the wallet.
            is_paper = bool(ticket.get("paper") or order.get("paper"))
            # A finished trade can still be sitting under this key — sweep()
            # only files it away after half an hour, and Unraveller re-entered
            # TSLA eleven minutes after stopping out. This overwrite used to
            # eat the finished row whole: the money survived (the wallet keeps
            # its own list) but the trade vanished from the table. That is why
            # day one's table showed the wins and none of the morning losses.
            # Now the finished trade is archived before the new one takes the
            # key.
            if prev and not adding and prev.get("state") in DONE:
                self._archive.append(prev)
            self._pos[key] = {
                "key": key,
                "live": is_live,
                "paper": is_paper,
                "room": order.get("room") or prev.get("room"),
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
                # A blind entry (no quote, no posted price) was priced at a
                # ceiling, not a real market price — so it must NOT be assumed
                # filled at that ceiling; it waits for the broker's real fill.
                "blind": bool(ticket.get("blind")),
                # The Discord/Whop message this trade came from, word for
                # word — his ask (8/17): a per-trade journal that tells him
                # which traders and which rooms are actually worth
                # following. Kept on adds too (first entry's wording).
                "raw": order.get("raw") if not adding else prev.get("raw"),
                # The call said SWING — overnight hold. Display only (8/17).
                "swing": (prev.get("swing") if adding
                          else bool(order.get("swing"))),
                # Born-with-the-order stop (8/19): the entry went out as a
                # linked group with its stop leg attached broker-side. On the
                # fill, _arm_stop ADOPTS this resting leg instead of placing a
                # second one. An ADD replaces the bracket (new avg = new stop),
                # so only a fresh entry keeps it.
                "bracket_stop_id": (None if adding
                                    else (str(ticket.get("stop_child"))
                                          if ticket.get("stop_child") else None)),
                "bracket_stop": (None if adding else ticket.get("stop_born")),
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
                    "seller (%s)"
                    % (sym, who, float(ticket.get("limit") or 0),
                       int(ticket.get("qty") or 1), self._wait_label()))
        t = threading.Thread(target=self._watch_fill, args=(key,), daemon=True)
        t.start()

    def _occ_for(self, b):
        """OCC symbol for a broker row, via the builder the bridge installs.
        None when the parts are missing — the watchdog then simply can't watch
        it, same as before, but says so instead of silently going blind."""
        fn = getattr(self, "occ_builder", None)
        if fn is None or b.get("kind") == "future":
            return None
        try:
            if b.get("symbol") and b.get("side") and b.get("strike") is not None and b.get("expiry"):
                return fn(b["symbol"], b["side"], b["strike"], b["expiry"])
        except Exception:                               # noqa: BLE001
            pass
        return None

    def _fut_mult_for(self, sym):
        """Points-to-dollars for a futures symbol.

        The broker reports the CONTRACT CODE ("MNQU6" = MNQ, Sep 2026) while the
        multiplier table is keyed by ROOT ("MNQ"). Looking the code up directly
        missed every time and silently fell back to 1.0, which understates an
        MNQ move by 2x and an NQ move by 20x. So: exact match first, then strip
        the trailing month letter + year digit(s) and match the root."""
        table = getattr(self, "fut_mult", None) or {}
        s = str(sym or "").upper()
        if s in table:
            return float(table[s])
        # Strip a trailing month letter + year digits without needing re:
        # "MNQU6" -> "MNQ", "ESZ26" -> "ES".
        t = s
        while t and t[-1].isdigit():
            t = t[:-1]
        if t and t != s and t[-1] in "FGHJKMNQUVXZ" and t[:-1] in table:
            return float(table[t[:-1]])
        # Longest known root that this code starts with (MNQU6 -> MNQ, not NQ).
        for root in sorted(table, key=len, reverse=True):
            if s.startswith(root):
                return float(table[root])
        return 1.0

    def drop_corrupt(self, note=None):
        """Throw out book rows that can't be real, and say so.

        The 8/12 case: futures_positions() briefly mislabelled OPTION rows as
        futures when the SDK ignored the futures account id, leaving "SPY" as a
        futures contract with no strike, no expiry and an option premium for a
        price. Nothing could shift it — reconcile_gone skips futures, flatten()
        refuses them, so ✕ did nothing. A futures symbol is a root plus a month
        letter and year ("MESU6"); anything else claiming to be a future is
        wreckage from that bug and gets dropped. Returns how many went."""
        def _is_code(sym):
            """A legitimate futures symbol is EITHER a contract code ("MNQU6")
            or a known root ("MNQ").

            Both shapes are real and both are used: the bot books its own
            orders under the root it read from the alert, while adoption from
            the broker uses the dated code. Checking only for the code shape
            deleted the bot's own MNQ short 15 seconds after it filled
            (8/12 11:45) — this function is a wrecking ball if it's wrong, so
            it errs towards keeping anything it recognises."""
            t = str(sym or "").upper()
            if t in (getattr(self, "fut_mult", None) or {}):
                return True             # a known root - MNQ, MES, MGC, CL...
            digits = 0
            while t and t[-1].isdigit():
                t = t[:-1]
                digits += 1
            if not (1 <= digits <= 2 and len(t) >= 2
                    and t[-1] in "FGHJKMNQUVXZ"):
                return False
            # "MNQU6" -> root "MNQ" must itself be recognisable, so a random
            # option ticker that happens to end in a letter+digit is not
            # mistaken for a contract.
            root = t[:-1]
            table = getattr(self, "fut_mult", None) or {}
            return (not table) or root in table or t in table
        bad = []
        with self._lock:
            for k, p in list(self._pos.items()):
                if p.get("kind") != "future":
                    continue
                sym = str(p.get("symbol") or "").upper()
                if _is_code(sym):
                    continue
                bad.append((k, sym))
        for k, sym in bad:
            with self._lock:
                p = self._pos.pop(k, None)
                if p is not None:
                    p.update(state=CLOSED, qty=0, closing=False,
                             watching=False, closed_at=time.time())
                    self._archive.append(p)
            if note:
                note("DROPPED  %s was recorded as a futures position but isn't "
                     "a futures contract (a bug on 8/12 mislabelled it). "
                     "Removed from the book; nothing was sent to the broker."
                     % sym)
        return len(bad)

    def purge_stale_futures(self, note=None, older_than=86400.0):
        """Drop adopted FUTURES rows more than a day old (his MESU6/MNQU6
        question, 8/17). These are his own hand trades the bot picked up;
        the futures account often can't be polled (unfunded / no data sub),
        so the gone-from-account sweep never gets a verdict and the row
        haunts 'holding ...' forever. A day-old adopted future the broker
        can't confirm is a ghost: archive it, touch no broker."""
        cut = time.time() - float(older_than)
        gone = 0
        with self._lock:
            items = list(self._pos.items())
        for key, p in items:
            # Any day-old futures row, adopted or not (8/18: the restored
            # MESU6 ghost dodged the adopted-only check and got trims and
            # stops booked against a position no broker holds). A REAL
            # futures position a day old would be re-confirmed by its
            # broker; these can't be, which is the whole point.
            if p.get("kind") != "future":
                continue
            if p.get("state") not in (WORKING, FILLED):
                continue
            if float(p.get("sent_at") or 0) >= cut:
                continue
            with self._lock:
                q = self._pos.pop(key, None)
                if q is not None:
                    q.update(state=CLOSED, qty=0, closing=False,
                             watching=False, manual_close=True,
                             closed_why="stale adopted future purged at "
                                        "startup — over a day old and the "
                                        "broker can't confirm it",
                             closed_at=time.time())
                    self._archive.append(q)
                    gone += 1
            if note:
                note("PURGED   %s — an adopted futures row over a day old "
                     "that the broker can't confirm. It was your own hand "
                     "trade; the book stops showing it as held."
                     % p.get("symbol"))
        return gone

    def purge_expired(self, note=None):
        """Drop FILLED option positions whose expiry is already in the past.
        They can't be sold (Webull refuses), they scare the ambiguity check,
        and they sit in the popup looking like money. No broker orders — the
        market already settled them; this only makes the book say so."""
        pe = getattr(self, "expiry_parser", None)
        if pe is None:
            return 0
        import datetime as _dt
        today = _dt.date.today()
        gone = 0
        with self._lock:
            items = list(self._pos.items())
        for key, p in items:
            if p.get("state") != FILLED or p.get("kind") == "future":
                continue
            exp = p.get("expiry")
            if not exp:
                continue
            try:
                if pe(exp) >= today:
                    continue
            except Exception:                           # noqa: BLE001
                continue
            with self._lock:
                q = self._pos.get(key)
                if not q or q.get("state") != FILLED:
                    continue
                q["state"] = CLOSED
                q["qty"] = 0
                q["closing"] = False
                q["closed_at"] = time.time()
            gone += 1
            self._event(key, "closed",
                        "%s — expired %s, already settled by the market. "
                        "Cleared from the book." % (p.get("symbol"), exp))
        if gone and note:
            note("PURGED   %d expired position(s) out of the book" % gone)
        return gone

    def _inherit_credit(self, sym, strike, expiry):
        """Who called this contract, if anyone did.

        An adopted position is created with who="?" because the broker doesn't
        know about Discord. But the SAME contract is very often one the bot
        itself entered minutes earlier on someone's call and then re-adopted
        (a failed stop-sell, a restart). Rebuilding it as "?" threw the caller
        and room away, so "Active trades" stopped saying whose alert it was —
        exactly what he noticed on 8/12. Look for the most recent record of
        this contract that HAS a caller and carry it forward."""
        def _root(v):
            """MNQU6 -> MNQ, so the broker's contract code and the root the
            alert used are recognised as the same instrument. Without this a
            futures trade loses its caller the instant it's adopted: the bot
            books Stormzy's call as "MNQ" and Webull reports "MNQU6"."""
            t = str(v or "").upper()
            table = getattr(self, "fut_mult", None) or {}
            if t in table:
                return t
            d = 0
            while t and t[-1].isdigit():
                t = t[:-1]
                d += 1
            if 1 <= d <= 2 and t and t[-1] in "FGHJKMNQUVXZ":
                r = t[:-1]
                if not table or r in table:
                    return r
            return str(v or "").upper()

        want = _root(sym)
        best = None
        with self._lock:
            pool = list(self._pos.values()) + list(self._archive)
        for q in pool:
            if _root(q.get("symbol")) != want:
                continue
            who = q.get("who")
            if not who or who == "?":
                continue
            try:
                if (strike is not None and q.get("strike") is not None
                        and abs(float(q["strike"]) - float(strike)) > 0.001):
                    continue
            except (TypeError, ValueError):
                continue
            if expiry and q.get("expiry") and str(q["expiry"]) != str(expiry):
                continue
            t = float(q.get("sent_at") or 0)
            if best is None or t > best[0]:
                best = (t, who, q.get("room"))
        return (best[1], best[2]) if best else (None, None)

    def adopt(self, broker_rows, note=None):
        """Take the account's REAL open positions (read from the broker) into the
        book as FILLED, live positions the bot can SEE and EXIT — even ones it
        never placed, or ones it lost track of across a restart. This is what lets
        a room's 'all out of SPY' actually flatten a SPY you're holding after a
        bridge restart wiped the in-memory book.

        Keyed under an UNKNOWN owner ('?') on purpose: a close from any admin
        ('all out of SPY') matches by symbol, and it never collides with a live
        trade the bot is itself running under a named owner. Skips anything the
        book already tracks so it can't double a position. Deliberately does NOT
        start the stop/take-profit watchdog — an adopted position is the room's
        (or the user's) to manage; the bot only makes it visible and closeable,
        it doesn't impose its own stop on a trade it didn't open. Returns the
        number newly adopted."""
        rows = broker_rows or []
        added = 0
        with self._lock:
            have = set()
            for p in self._pos.values():
                if p.get("state") in (WORKING, FILLED):
                    have.add(str(p.get("symbol") or "").upper())
        for b in rows:
            sym = str(b.get("symbol") or "").upper()
            if not sym or sym in have:
                continue
            qty = int(b.get("qty") or 0)
            if qty <= 0:
                continue
            # JUST-CLOSED GUARD (8/17): Webull's position feed lags a beat
            # behind a sell. On 8/17 a META sold on the room's call at 09:33:27
            # was still in the feed one second later, got re-adopted, armed a
            # fresh stop, and that stop then failed 417 ("nothing to sell")
            # again and again until the breaker gave up. If we closed this exact
            # symbol seconds ago, that IS the lag — leave it until the feed
            # catches up instead of re-adopting a ghost.
            _cool = float(getattr(self, "readopt_cooldown", 120) or 0)
            if _cool > 0:
                _cut = time.time() - _cool
                _recent = False
                with self._lock:
                    # BOTH places a finished trade can live: the archive, AND
                    # still under its key in _pos (sweep only files it away
                    # later). Checking only the archive is how VXX looped on
                    # 8/18: stopped out -> still in _pos as STOPPED -> feed
                    # lag re-showed it -> re-adopted -> stopped again, every
                    # 20 seconds. A symbol closed in the last 2 minutes is
                    # NOT re-adopted, wherever its record sits.
                    for _q in list(self._pos.values()) + list(self._archive):
                        if str(_q.get("symbol") or "").upper() != sym:
                            continue
                        if float(_q.get("closed_at") or 0) >= _cut:
                            _recent = True
                            break
                if _recent:
                    continue
            is_fut = b.get("kind") == "future"
            # PHANTOM-EXIT COMPLETION (8/21, his ask: "can't the bot put an
            # order in and not leave it open?"): the book recorded a stop or
            # close MINUTES ago, but the broker still holds the contract —
            # the exit's sell never really filled (CLF today; MP and TSLA
            # before the fill-confirmation fix existed). The decision to be
            # OUT was already made by a stop or a room call; finish it —
            # urgent, fill-confirmed — instead of re-adopting an unmanaged
            # orphan. Manual closes are exempt: those are HIS trades.
            phantom = None
            if not is_fut and qty <= int(getattr(self, "adopt_max_qty", 3) or 3):
                _pcut = time.time() - 900.0
                with self._lock:
                    for _q in list(self._pos.values()) + list(self._archive):
                        if str(_q.get("symbol") or "").upper() != sym:
                            continue
                        if _q.get("state") not in (STOPPED, CLOSED):
                            continue
                        if _q.get("manual_close"):
                            continue
                        if float(_q.get("closed_at") or 0) < _pcut:
                            continue
                        try:
                            if (b.get("strike") is not None
                                    and _q.get("strike") is not None
                                    and abs(float(b["strike"])
                                            - float(_q["strike"])) > 0.001):
                                continue
                        except (TypeError, ValueError):
                            continue
                        phantom = dict(_q)
                        break
            if phantom:
                wb = self._wbfor(phantom)
                if wb is not None:
                    _occ = phantom.get("occ") or self._occ_for(b)
                    _ref = phantom.get("last_bid") or phantom.get("stop") \
                        or fill
                    if note:
                        note("PHANTOM  %s — the book recorded '%s' but the "
                             "broker STILL holds it; that exit never filled. "
                             "Finishing it now (urgent, fill-confirmed)."
                             % (sym, phantom.get("state")))
                    try:
                        _okp, _pxp = self._sell_confirmed(
                            wb, phantom.get("key") or key_of("?", sym), _occ,
                            sym, phantom.get("side") or b.get("side"),
                            phantom.get("strike") if phantom.get("strike")
                            is not None else b.get("strike"),
                            phantom.get("expiry") or b.get("expiry"),
                            qty, float(_ref) if _ref else None)
                    except Exception as _pe:            # noqa: BLE001
                        _okp, _pxp = False, None
                        if note:
                            note("PHANTOM  %s — completing the exit FAILED "
                                 "(%s); adopting it back so it stays visible "
                                 "and watched." % (sym, str(_pe)[:80]))
                    if _okp:
                        # Refresh the close stamp to NOW (8/25): the recent-
                        # close guard above dates from the WRONG recorded
                        # close, so Webull's reporting lag after this real
                        # fill could still re-adopt a ghost (NVDA, 9:54).
                        try:
                            phantom["closed_at"] = time.time()
                        except Exception:               # noqa: BLE001
                            pass
                        if note:
                            note("PHANTOM  %s — exit COMPLETED at %.2f. The "
                                 "earlier recorded price was wrong; the "
                                 "daily reconcile trues up the P&L."
                                 % (sym, float(_pxp)))
                        continue        # really out now — nothing to adopt
                    # else fall through: adopt normally, the watchdog re-arms
            # Cash-settled index options (SPXW, XSP, NDX...) can't be SOLD
            # through this account's API — Webull refuses every sell
            # (INDEX_NAKED 8/17, MARGIN_TO_CASH 8/18, live both days), so an
            # adopted one is a position the bot can see but never exit:
            # endless stop-warn spam and phantom loss records. His index
            # trades are HIS — left alone entirely.
            if not is_fut and sym in ("SPX", "SPXW", "XSP", "NDX", "NDXP",
                                      "RUT", "RUTW", "VIX", "VIXW", "MRUT",
                                      "XND"):
                seen = getattr(self, "_adopt_skips", None)
                if seen is None:
                    seen = self._adopt_skips = set()
                if sym not in seen:
                    seen.add(sym)
                    if note:
                        note("ADOPT    left %s alone — a cash-settled index "
                             "option this account's API can't sell. It's "
                             "yours to manage at Webull." % sym)
                continue
            # HIS OWN hand trades share this account: 5-30 lot scalps next to
            # the bot's 1-2 lot calls. Adopting a 30-lot means a room's "all
            # out of SPY" can sell HIS position out from under him — so
            # anything bigger than the bot would ever trade is left alone.
            maxq = int(getattr(self, "adopt_max_qty", 3) or 0)
            if maxq and not is_fut and qty > maxq:
                seen = getattr(self, "_adopt_skips", None)
                if seen is None:
                    seen = self._adopt_skips = set()
                if sym not in seen:
                    seen.add(sym)
                    if note:
                        note("ADOPT    left %s x%d alone — bigger than anything "
                             "the bot trades, so it's YOURS. Rooms can't touch "
                             "it." % (sym, qty))
                continue
            # A contract that already EXPIRED is dead weight: it can't be sold
            # (Webull refuses past expiries) and it bloats the "which one did
            # they mean" list until every tickerless trim goes ambiguous.
            pe = getattr(self, "expiry_parser", None)
            if pe and not is_fut and b.get("expiry"):
                try:
                    import datetime as _dt
                    if pe(b["expiry"]) < _dt.date.today():
                        seen = getattr(self, "_adopt_skips", None)
                        if seen is None:
                            seen = self._adopt_skips = set()
                        if sym not in seen:
                            seen.add(sym)
                            if note:
                                note("ADOPT    left %s alone — that expiry is "
                                     "already in the past" % sym)
                        continue
                except Exception:                       # noqa: BLE001
                    pass
            fill = b.get("fill")
            try:
                fill = float(fill) if fill not in (None, "") else None
            except (TypeError, ValueError):
                fill = None
            key = key_of("?", sym)
            # WHICH account the row came from decides everything downstream:
            # a sandbox leftover adopted as "live" routes its trims/closes to
            # the REAL account, which doesn't hold it — Webull reads the sell
            # as opening a covered call and 417s (the whole morning of 8/11).
            row_live = bool(b.get("live"))
            # If the bot was in this exact contract on someone's call, keep the
            # credit — otherwise every re-adoption erases whose alert it was.
            _who, _room = self._inherit_credit(sym, b.get("strike"),
                                               b.get("expiry"))
            with self._lock:
                if self._pos.get(key, {}).get("state") in (WORKING, FILLED):
                    continue
                self._pos[key] = {
                    "key": key, "live": row_live, "paper": not row_live,
                    "room": _room,
                    # No bot record to inherit credit from = a trade GIAN put
                    # on himself (his ask, 8/20: "are my trades the adopted?
                    # put gian if so"). The KEY stays "?|SYM" on purpose — any
                    # admin's "all out" still matches it by symbol — only the
                    # journal's name changes.
                    "who": _who or "Gian", "symbol": sym,
                    "kind": b.get("kind") or "option",
                    # A futures contract is points x ITS OWN multiplier (MNQ 2,
                    # NQ 20, ES 50). Hardcoding 1.0 made every adopted futures
                    # P&L and stop wrong by that factor. The bridge installs the
                    # table; 1.0 only if it never did.
                    "mult": (self._fut_mult_for(sym) if is_fut else 100.0),
                    # And a SHORT is direction -1. Hardcoding long meant a short
                    # future showed a losing trade as winning and put the stop on
                    # the wrong side of the market.
                    "direction": int(b.get("direction") or 1) if is_fut else 1,
                    "their_stop": None, "their_target": None,
                    "state": FILLED, "order_id": None,
                    # The occ is the watchdog's eyes: without it the TP/trim
                    # price poll dies instantly (NVDA 8/11 hit +20% and nothing
                    # fired). Build it from the row when the parts are there.
                    "occ": self._occ_for(b),
                    "side": b.get("side"), "strike": b.get("strike"),
                    "expiry": b.get("expiry"),
                    "want_qty": qty, "qty": qty, "adds": 0,
                    "limit": fill, "fill": fill, "stop": None,
                    "stop_order_id": None, "their_price": fill,
                    "their_avg": fill, "their_units": 1,
                    "cost": (fill or 0) * 100 * qty if not is_fut else 0.0,
                    "entries": [], "exits": [], "trade_pl": 0.0,
                    "last_bid": None, "reserved": 0.0, "sent_at": time.time(),
                    "closing": False, "watching": False, "blind": False,
                    "adopted": True,
                }
            have.add(sym)
            added += 1
            self._event(key, "adopted",
                        "%s x%d picked up from your Webull %s account — %s"
                        % (sym, qty, "LIVE" if row_live else "paper",
                           ("the bot can see it and exit it on the room's "
                            "call" if _who else
                            "YOUR trade: visible in the popup, no stop, and "
                            "no room can close or trim it")))
            if note:
                note("ADOPTED  %s x%d from Webull %s (fill %s)"
                     % (sym, qty, "LIVE" if row_live else "paper", fill))
            # The old rule bracketed ANY adopted 1-2 lot with a known cost —
            # which put stops on HIS OWN hand trades too ("why did my own
            # qqq position have a stop loss?", 8/18). The bracket now arms
            # ONLY when the book remembers the bot itself touching this
            # exact contract in the last hour (an entry that slipped through
            # as a no-fill — the naked-GOOGL case it was built for). A
            # contract the bot never traded is HIS: visible, closeable on
            # the room's call, never auto-stopped.
            _bot_recent = False
            if fill and qty <= 2 and not is_fut:
                _cut_h = time.time() - 3600.0
                with self._lock:
                    for _r in list(self._pos.values()) + list(self._archive):
                        if _r.get("adopted"):
                            continue    # only the bot's own placed orders count
                        if str(_r.get("symbol") or "").upper() != sym:
                            continue
                        if float(_r.get("sent_at") or 0) < _cut_h:
                            continue
                        try:
                            if (_r.get("strike") is not None
                                    and b.get("strike") is not None
                                    and abs(float(_r["strike"])
                                            - float(b["strike"])) > 0.001):
                                continue
                        except (TypeError, ValueError):
                            pass
                        _bot_recent = True
                        break
            if _bot_recent:
                try:
                    self._arm_stop(key, b.get("side"), b.get("strike"),
                                   b.get("expiry"), qty, float(fill))
                except Exception:                       # noqa: BLE001
                    pass
            elif fill and qty <= 2 and not is_fut and note:
                note("ADOPT    %s x%d looks like YOUR own trade (the bot "
                     "never touched that contract) — no auto-stop put on it."
                     % (sym, qty))
        return added

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
                    _wb = self._wbfor(p)

                # ask the broker that OWNS the order (9/3): a live bid is
                # checked on the live client, same as the deadline path below
                state, filled_qty, avg = self._probe(
                    oid, occ, limit, live=p.get("live"),
                    paper=p.get("paper"), blind=p.get("blind"), wb=_wb)
                if state == FILLED:
                    self._became_filled(key, filled_qty or want, avg or limit)
                    return
                if state == "dead":
                    self._became_nofill(key, "Webull cancelled or rejected it, "
                                        "or there was never a price to bid "
                                        "with")
                    return
        except Exception as e:                          # noqa: BLE001
            # The watcher died. Whatever went wrong, a bid may not sit in
            # "waiting for a seller" forever — that's how a garbage entry
            # (TAKE 742C, no price, no quote) stayed BID IN from 11:15 to
            # the close. The bid is declared dead; Webull is the referee if
            # this was ever real.
            with self._lock:
                p = self._pos.get(key)
                if p is not None and p["state"] == WORKING:
                    p["state"] = FAILED
                    p["closed_at"] = time.time()
            self._unreserve(key)
            self._event(key, "failed",
                        "%s — lost track of the entry: %s. The bid is treated "
                        "as DEAD — check the Webull app before trusting this "
                        "line." % (key.split("|")[-1], str(e)[:120]))
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
            wb = self._wbfor(p)
        if wb is not None and oid:
            try:
                wb.cancel(oid)
            except Exception:                           # noqa: BLE001
                pass
        with self._lock:
            p_l = self._pos.get(key) or {}
        state, filled_qty, avg = self._probe(
            oid, occ, limit, live=p_l.get("live"),
            paper=p_l.get("paper"), blind=p_l.get("blind"), wb=wb)
        # On a LIVE Webull order a fill can land in the same instant the cancel
        # goes out, and Webull can take a few seconds to REPORT it. The old code
        # probed ONCE and, if that single probe hadn't caught up, declared "no
        # fill" on a contract you now actually hold -- which then got adopted
        # later with NO bracket. So on live, keep polling for a few more seconds
        # before concluding nobody sold. Any partial/full fill routes through
        # _became_filled, which arms the +TP/-stop bracket and keeps the
        # room-owner link so trims still match. Sim/paper is untouched (no such
        # report-lag), which also keeps the deadline tests' timing intact.
        if (bool(p_l.get("live"))
                and not (state == FILLED or (filled_qty or 0) > 0)
                and state != "dead"):
            for _settle in range(5):                 # ~5s live grace
                time.sleep(1.0)
                with self._lock:
                    p_c = self._pos.get(key)
                    if not p_c or p_c["state"] != WORKING:
                        return                       # resolved elsewhere meanwhile
                    p_c = dict(p_c)
                try:
                    state, filled_qty, avg = self._probe(
                        oid, occ, limit, live=p_c.get("live"),
                        paper=p_c.get("paper"), blind=p_c.get("blind"), wb=wb)
                except Exception:                    # noqa: BLE001
                    break
                if state == FILLED or (filled_qty or 0) > 0 or state == "dead":
                    break
        # Last resort on LIVE (8/11, NVDA): the order-status probe misses
        # real fills entirely — every live entry was ending "no fill" and only
        # coming back via adoption, blind. Before declaring nobody sold, ask
        # the ACCOUNT: if it now holds this very contract, that IS the fill.
        if (bool(p_l.get("live")) and wb is not None
                and not (state == FILLED or (filled_qty or 0) > 0)):
            try:
                with self._lock:
                    p_h = dict(self._pos.get(key) or {})
                for row in (wb.positions() or []):
                    if str(row.get("symbol") or "").upper() != str(p_h.get("symbol") or "").upper():
                        continue
                    if p_h.get("strike") is not None and row.get("strike") is not None and abs(float(row["strike"]) - float(p_h["strike"])) > 0.001:
                        continue
                    got = int(row.get("qty") or 0)
                    px = row.get("fill")
                    if got > 0:
                        self._became_filled(key, min(got, want),
                                            float(px) if px else (limit or 0))
                        return
            except Exception:                           # noqa: BLE001
                pass
        if state == FILLED or (filled_qty or 0) > 0:
            self._became_filled(key, filled_qty or want, avg or limit)
        else:
            self._became_nofill(
                key, "nobody sold at %.2f within %s"
                     % (float(limit or 0), self._wait_label()))

    def _wbfor(self, p):
        """The broker that OWNS this position. With two connections up, a live
        position is managed on the live account and a paper one on the paper
        account — you can't cancel a live order id on the paper client or vice
        versa. Safe by construction: the resolver only ever returns the live
        client for a position explicitly flagged live; anything else stays on
        paper/sim. No resolver set -> the single default broker, as before."""
        r = self.broker_resolver
        if r is not None:
            try:
                return r(p or {})
            except Exception:                           # noqa: BLE001
                return self.wb
        return self.wb

    def _sim(self, p):
        """Is THIS position managed in simulation? A LIVE position is never
        simulated — real resting stop and real stop-sell on the real account.
        A PAPER position is ALSO never simulated now: paper is Webull's sandbox,
        a real broker, so its stops/trims/closes are placed there too (options
        AND futures), not modelled in-house. Only a position with no broker at
        all (pure dry run, no keys) follows the book's simulated flag. Keyed on
        the same p["live"]/p["paper"] the broker router uses, so the client and
        the sim-flag can never disagree."""
        if p and (p.get("live") or p.get("paper")):
            return False
        return self.simulated

    def _probe(self, oid, occ, limit, live=False, wb=None, paper=False,
               blind=False):
        """(state, filled_qty, avg_price) — from the broker for real money,
        or from the live quote for a test position. `wb` is the broker that owns
        this position; falls back to the default when the caller didn't route."""
        if wb is None:
            wb = self.wb
        if paper and not live and not blind:
            # PAPER fills the moment it's placed. The entry crosses the ask (a
            # real, marketable quote), so in the real world it fills instantly —
            # "we are still biding in" is the exact miss he can't have. Don't sit
            # waiting on the sandbox's fill engine to match a resting order:
            # assume the fill at the marketable price we sent, so trims and exits
            # act on a real position. A price of None can't be filled — dead.
            # Blind entries are excluded above (their limit is a ceiling, not a
            # market price) and fall through to the real broker check.
            if limit is None:
                return "dead", 0, None
            return FILLED, None, limit
        if live:
            # Real money: Webull is the only honest answer.
            if wb is None:
                return WORKING, 0, None
            return wb.order_status(oid)
        if wb is None or not occ:
            # No broker, or no quotable contract — futures have no OCC symbol
            # and no quote feed yet. Nothing can be checked, so a dry run
            # treats the entry as filled at the price it would have bid, and
            # the log says so. This is the one place the dry run flatters
            # itself, and it's marked every time it happens.
            if limit is None:
                # ...but with no bid price EITHER, there is nothing to
                # pretend a fill at. Dead on arrival, honestly.
                return "dead", 0, None
            return FILLED, None, limit
        if self.simulated:
            # Keys are present and quotes are real, so a dry run can answer the
            # actual question: did anyone offer to sell at your bid? If the ask
            # comes down to your price, somebody would have.
            if limit is None:
                # A bid with no price can't be matched against any ask. Let
                # the deadline pull it rather than crash the watcher — this
                # exact float(None) is what wedged TAKE 742C in BID IN.
                return WORKING, 0, None
            try:
                ask, bid, _ = wb.ask_bid(occ)
            except Exception:                           # noqa: BLE001
                return WORKING, 0, None
            if ask and float(ask) <= float(limit) + 0.0001:
                return FILLED, None, limit
            return WORKING, 0, None
        return wb.order_status(oid)


    def _stop_still_resting(self, p):
        """CHECK BEFORE REDOING (9/2, G: "do that to everything"): is the
        stop this position remembers still WORKING at Webull? True means
        leave it alone. Anything else — gone, unknown, sim — means the
        caller should arm. One read instead of a cancel + a place."""
        try:
            sid = p.get("stop_order_id")
            if not sid or self._sim(p):
                return False
            wb = self._wbfor(p)
            if wb is None:
                return False
            st, _fq, _ = wb.order_status(sid)
            return st == "working"
        except Exception:                               # noqa: BLE001
            return False

    def rearm_overnight_stops(self):
        """Webull only takes DAY stops on option sell legs, so every resting
        stop dies at the close and an overnight hold wakes up NAKED at the
        broker (8/31: the S 22.5C swing's 0.70 stop was cancelled at the
        bell). The bridge calls this once per day just after the open: any
        FILLED, still-open SWING whose stop wasn't placed today gets the
        same _arm_stop it got at entry — resting order first, watchdog
        second. Swings only, on purpose: scalps never live past a close."""
        import datetime as _dt
        today = _dt.date.today().isoformat()
        with self._lock:
            keys = [k for k, p in self._pos.items()
                    if p.get("state") == FILLED and int(p.get("qty") or 0) > 0
                    and p.get("kind") != "future" and not p.get("closing")
                    and p.get("swing") and p.get("stop_day") != today]
        n = 0
        for k in keys:
            with self._lock:
                p = dict(self._pos.get(k) or {})
            if not p:
                continue
            if self._stop_still_resting(p):
                # A stop that survived the close (GTC standalone sells are
                # accepted, 9/2) is not re-placed — checked, kept, logged.
                with self._lock:
                    q = self._pos.get(k)
                    if q is not None:
                        q["stop_day"] = today
                self._event(k, "update",
                            "%s — overnight stop still resting at Webull at %.2f "
                            "— kept" % (k.split("|")[-1], float(p.get("stop") or 0)))
                continue
            try:
                self._arm_stop(k, p.get("side"), p.get("strike"),
                               p.get("expiry"), int(p.get("qty") or 1),
                               float(p.get("fill") or 0) or None)
                with self._lock:
                    q = self._pos.get(k)
                    if q is not None:
                        q["stop_day"] = today
                n += 1
            except Exception:                           # noqa: BLE001
                pass
        return n

    def reconcile_gone(self, broker_rows, note=None, trust_empty_live=False):
        """The inverse of adopt(): the book says you're in it, the ACCOUNT
        says you're not — he sold it himself in the Webull app. After 3
        sweeps in a row missing (~60s) the trade is marked done instead of
        the watchdog guarding a ghost all day. One flaky poll can't fake it,
        and an account bucket that came back empty is skipped entirely,
        because empty and unreachable look identical from here.
        Returns how many trades were marked closed."""
        buckets = {True: [], False: []}
        for b in (broker_rows or []):
            if b.get("kind") == "future":
                continue
            buckets[bool(b.get("live"))].append(b)

        def _exp(e):
            fn = getattr(self, "expiry_parser", None)
            if fn is not None:
                try:
                    return str(fn(e))
                except Exception:                       # noqa: BLE001
                    return None
            return str(e)

        def _held(b, p_):
            if str(b.get("symbol") or "").upper() != str(p_.get("symbol") or "").upper():
                return False
            try:
                if p_.get("strike") is not None and b.get("strike") is not None \
                        and abs(float(b["strike"]) - float(p_["strike"])) > 0.001:
                    return False
            except Exception:                           # noqa: BLE001
                return False
            bs = str(b.get("side") or "").upper()
            ps = str(p_.get("side") or "").upper()
            if bs and ps and bs[0] != ps[0]:
                return False
            be, pe = _exp(b.get("expiry")), _exp(p_.get("expiry"))
            if be is None or pe is None:
                # an expiry that won't parse -> call it held. Never close a
                # trade over a date-format misunderstanding.
                return True
            return be == pe

        closed = 0
        with self._lock:
            keys = list(self._pos.keys())
        for key in keys:
            with self._lock:
                p_ = dict(self._pos.get(key) or {})
            if not p_ or p_.get("state") != FILLED or int(p_.get("qty") or 0) <= 0:
                continue
            if p_.get("kind") == "future" or p_.get("closing"):
                continue
            acct = buckets[bool(p_.get("live"))]
            if not acct:
                # Empty bucket: no verdict — UNLESS the caller vouches the
                # live read succeeded and simply found the account flat.
                # A flat account is the strongest "you're not in it" there is
                # (8/31 ghost-SPY lesson: he was flat for 3 hours and the
                # ghost was untouchable the whole time).
                if not (p_.get("live") and trust_empty_live):
                    continue
            if any(_held(b, p_) for b in acct):
                _arm_now = False
                with self._lock:
                    q = self._pos.get(key)
                    if q is not None:
                        q["gone_misses"] = 0
                        if q.get("unverified"):
                            q["unverified"] = False
                            _arm_now = True
                if _arm_now and p_.get("adopted") and not p_.get("stop_order_id"):
                    # HIS OWN TRADE (8/18 rule): adopted, never auto-stopped.
                    # A restart used to forget that and arm a -10% stop on
                    # it anyway (9/2 14:11: his hand-bought SPY 767C got a
                    # 3.14 stop it never asked for). Confirm, stay hands-off.
                    self._event(key, "update",
                                "%s — the broker confirms your own trade; no "
                                "auto-stop, as before" % p_.get("symbol"))
                    continue
                if _arm_now:
                    # KEEP THE RESTING STOP (9/2, G: "leave the stop and
                    # just check if it's still there"). A restart used to
                    # cancel the stop Webull was already holding and place
                    # it again — two order calls and a naked moment for
                    # nothing. Now: ask Webull about the saved stop id; if
                    # it is still WORKING, keep it and just start the
                    # watchdog. Only a stop that's gone (filled, cancelled,
                    # expired at the close) gets re-armed.
                    _kept = False
                    if self._stop_still_resting(p_):
                        if True:
                            _kept = True
                            with self._lock:
                                q = self._pos.get(key)
                                if q is not None and not q.get("watching"):
                                    q["watching"] = True
                                    threading.Thread(target=self._watchdog,
                                                     args=(key,),
                                                     daemon=True).start()
                            self._event(key, "update",
                                        "%s — the broker confirms the restored "
                                        "position; stop still resting at Webull "
                                        "at %.2f — kept as is, watchdog on"
                                        % (p_.get("symbol"),
                                           float(p_.get("stop") or 0)))
                    if not _kept:
                        self._event(key, "update",
                                    "%s — the broker confirms the restored "
                                    "position; watchdog and stop armed"
                                    % p_.get("symbol"))
                        try:
                            self._arm_stop(key, p_.get("side"), p_.get("strike"),
                                           p_.get("expiry"),
                                           int(p_.get("qty") or 1),
                                           float(p_.get("fill") or 0) or None)
                        except Exception:               # noqa: BLE001
                            pass
                continue
            misses = 0
            with self._lock:
                q = self._pos.get(key)
                if q is None:
                    continue
                q["gone_misses"] = int(q.get("gone_misses") or 0) + 1
                misses = q["gone_misses"]
                if misses >= 3:
                    q["manual_close"] = True
            if misses >= 3:
                # ASK BEFORE ASSUMING (8/27). The position is gone and the bot
                # never sent the sell, so it has no order id — but the account
                # still has the fill on it. Look the real price up and settle
                # on THAT. Whatever closed it (a resting bracket stop, a GTC
                # stop from an earlier session, him tapping Close) printed a
                # price, and that price is the trade's truth. None means the
                # lookup failed, and finish() then says so out loud instead of
                # crediting a quote.
                # OUR OWN STOP FIRST (9/3, the C 139P case): the resting
                # stop that was born with the entry FILLED at 1.14 and the
                # book announced "you closed it yourself, at a price I never
                # saw". The bot's own stop is the most likely closer and it
                # has an order id — ask THAT before blaming him.
                px = None
                _kind = CLOSED
                _sid = p_.get("stop_order_id")
                if _sid and not self._sim(p_):
                    try:
                        _wbx = self._wbfor(p_)
                        _sst, _sq, _spx = _wbx.order_status(_sid) if _wbx else ("unknown", 0, None)
                        if _sst == FILLED or _sst == "filled":
                            _kind = STOPPED
                            px = float(_spx) if _spx else None
                    except Exception:                   # noqa: BLE001
                        pass
                if px is None:
                    px = self._broker_exit_price(p_, tries=2)
                if _kind == STOPPED:
                    why = ("your resting stop fired at Webull%s — that's what "
                           "closed it, not you"
                           % ((" and filled at %.2f" % px) if px is not None else ""))
                elif px is not None:
                    why = ("closed at your broker for %.2f — the bot didn't "
                           "send this sell, so it read the fill back off the "
                           "account" % px)
                else:
                    why = ("gone from your Webull account — you closed it "
                           "yourself, so the trade is marked done")
                self.finish(key, _kind, why, price=px)
                closed += 1
                if px is None and p_.get("live"):
                    # TRUE-UP (9/2 journal): the lookup above answered None
                    # SIX times in two days — every one a 429 on the order-
                    # history door (2 per 2s, shared with the announcer's
                    # poll), never a missing fill. Each booked $0 and the
                    # journal had to correct it by hand (FLR -9, SPY -31
                    # today; S -50, SPY -12, SPY -8 yesterday). Keep asking
                    # in the background and write the real price onto the
                    # record when it comes.
                    try:
                        threading.Thread(target=self._true_up_exit,
                                         args=(key, p_), daemon=True).start()
                    except Exception:                   # noqa: BLE001
                        pass
        return closed

    def _broker_exit_price(self, p_, tries=1, pause=2.2):
        """The real sale price for a position that vanished, or None.

        Wrapped tight on purpose: this runs inside the reconcile sweep, and a
        broker hiccup here must never stop the sweep from finishing the trade.
        Silence (None) is a safe answer — finish() handles it honestly.
        `tries` > 1 re-asks after `pause` seconds: the order-history endpoint
        is budgeted 2 per 2s and a single 429 was the whole reason this came
        back empty (9/2 11:49:01, SPY 766C — the fill was sitting right there)."""
        if not p_.get("live"):
            return None
        for i in range(max(1, int(tries))):
            if i:
                time.sleep(pause)
            try:
                wb = self._wbfor(p_)
                if wb is None or not hasattr(wb, "last_sell_fill"):
                    return None
                px = wb.last_sell_fill(p_.get("symbol"), p_.get("side"),
                                       p_.get("strike"), p_.get("expiry"),
                                       since=p_.get("filled_at")
                                       or p_.get("sent_at"))
                if px:
                    return float(px)
            except Exception:                               # noqa: BLE001
                pass
        return None

    def _true_up_exit(self, key, p_, tries=30, pause=6.0):
        """Background: keep asking the broker for the sell that closed a
        vanished position, and settle the record on the real print once it
        answers. Up to ~3 minutes, six seconds apart (well under the
        history endpoint's budget). Never raises; the day file is rewritten
        by the event it posts."""
        for _ in range(int(tries)):
            time.sleep(pause)
            px = self._broker_exit_price(p_, tries=1)
            if px is None:
                continue
            pl = self._apply_exit_price(key, p_, px)
            if pl is None:
                return              # already settled by somebody else
            self._event(key, "update",
                        "%s — TRUED UP: the broker printed %.2f for that exit "
                        "(read back off the account after the rate limit "
                        "cleared) · %s$%.0f on the trade"
                        % (p_.get("symbol"), px, "+" if pl >= 0 else "-",
                           abs(pl)))
            return
        self._event(key, "update",
                    "%s — no sell fill found on the account for that exit "
                    "after %d minutes; the journal will true it up from the "
                    "broker's order list" % (p_.get("symbol"),
                                              int(tries * pause / 60)))

    def _apply_exit_price(self, key, p_, px):
        """Write a broker-confirmed exit price onto a CLOSED record that was
        booked without one. Returns the trade P&L, or None if the record is
        gone or already carries a priced exit (never double-settles)."""
        qty = int(p_.get("qty") or 0)
        if qty <= 0 or p_.get("kind") == "future":
            return None
        mult = float(p_.get("mult") or 100)
        cost = float(p_.get("cost") or 0)
        got = float(px) * mult * qty
        pl = got - cost
        # The record is THIS trade (same key AND same sent_at — the key alone
        # is reused by the next call in the same ticker), wherever it sits:
        # still under its key in _pos, or already swept into the archive.
        sent = float(p_.get("sent_at") or 0)

        def _same(r):
            return (r is not None and r.get("state") in DONE
                    and abs(float(r.get("sent_at") or 0) - sent) < 1e-6)
        with self._lock:
            rec = self._pos.get(key)
            if not _same(rec):
                rec = None
                for a in reversed(self._archive):
                    if a.get("key") == key and _same(a):
                        rec = a
                        break
            if rec is None:
                return None
            if any(float(x.get("price") or 0) > 0
                   for x in (rec.get("exits") or [])):
                return None
            rec.setdefault("exits", []).append(
                {"t": time.time(), "qty": qty, "price": round(float(px), 4),
                 "pl": round(pl, 2), "trued_up": True})
            rec["trade_pl"] = round(float(rec.get("trade_pl") or 0) + pl, 2)
            rec["cost"] = 0.0
            rec["exit_px"] = round(float(px), 4)
            rec["closed_why"] = (str(rec.get("closed_why") or "")
                                 + " · trued up: sold at %.2f" % float(px))
        return pl

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
            is_live = bool(p0 and p0.get("live"))
            m0 = float((p0 or {}).get("mult") or 100)
        # mult-aware: an option is 100 shares, a share is one share. The old
        # hardcoded x100 would have priced $1,000 of NFLX stock as $100,000.
        paid = 0.0 if is_fut else float(price) * m0 * int(qty or 1)
        self._unreserve(key)
        with self._lock:
            # The position's OWN cost ledger records what was paid no matter
            # which account paid it — it is the basis every P&L and % is
            # computed from. (8/18: live fills skipped this, so a live
            # trade's "P&L" printed as its sale PROCEEDS — AAPL's real +$19
            # showed as +$209, and a Vero LOSS showed as +$132.) Only the
            # PRETEND WALLET below stays live-blind, exactly as designed:
            # real money never touches the pretend cash.
            p = self._pos.get(key)
            if p and not is_fut:
                p["cost"] = float(p.get("cost") or 0) + paid
            if self.cash is not None and not is_fut and not is_live:
                self.cash -= paid
        self._mark_peak()
        # With no broker at all there is nothing to ask, so the dry run assumed
        # this filled. Said out loud every single time, because an assumed fill
        # is the one number in the log that is not evidence of anything.
        # The flag rides on the position so the day total can keep assumed
        # money separate from checked money all the way to the close.
        if self.wb is None:
            with self._lock:
                _pa = self._pos.get(key)
                if _pa is not None:
                    _pa["assumed"] = True
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
        # UNDERLYING AT FILL (9/1, G: "what price of the underlying are these
        # entries filling at?"): read the stock right now, keep it on the
        # position, and print it in the FILLED line so the journal and the
        # announcer can carry it. Best effort — a quote hiccup never blocks.
        und_s = ""
        if not is_fut:
            try:
                _wbu = self._wbfor(p0) if p0 else None
                _u = _wbu.stock_price(sym) if _wbu is not None else None
                if _u:
                    with self._lock:
                        _pu = self._pos.get(key)
                        if _pu is not None:
                            _pu["und_at_fill"] = round(float(_u), 2)
                    und_s = " · %s @ %.2f" % (sym, float(_u))
            except Exception:                           # noqa: BLE001
                und_s = ""
        self._event(key, "filled",
                    "%s — filled %s at %.2f%s%s%s%s" % (sym, qty, float(price),
                                                        "" if first else
                                                        " (now holding %d)" % total,
                                                        und_s, money, assumed))
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
    def rearm_stop_after_failed_exit(self, key):
        """A failed CLOSE/TRIM leaves the position ALIVE but its resting
        stop PULLED (the exit pulls the stop before selling) — SPY 769C sat
        0DTE with watchdog-only cover after the 8/18 collision. If the
        position survived the failure, the broker-side stop goes straight
        back in, at the SAME level it was guarding — a ratcheted stop must
        never fall back to -10%-from-fill."""
        with self._lock:
            p = self._pos.get(key)
            if (not p or p.get("state") != FILLED or p.get("closing")
                    or p.get("kind") == "future" or self._sim(p)):
                return
            if p.get("stop_order_id"):
                return                  # still resting — nothing to do
            stop = p.get("stop")
            # HIS OWN TRADE (8/18 rule, re-learned 9/2 14:11): an adopted
            # position that never carried a stop must not be handed one by
            # a failed exit — that is how his hand-bought SPY 767C got a
            # 3.14 stop it never asked for. No stop before = no stop after.
            if p.get("adopted") and not stop:
                return
            fill = p.get("fill")
            side = p.get("side")
            strike = p.get("strike")
            expiry = p.get("expiry")
            qty = int(p.get("qty") or 0)
        if qty <= 0:
            return
        base = fill
        try:
            if stop and self.stop_pct:
                # a synthetic fill so "-stop_pct% of fill" recreates the
                # CURRENT stop level exactly, ratchet progress included
                base = float(stop) / (1.0 - self.stop_pct / 100.0)
        except Exception:                               # noqa: BLE001
            base = fill
        if not base:
            return
        try:
            self._arm_stop(key, side, strike, expiry, qty, float(base))
            self._event(key, "stop-set",
                        "%s — the exit failed but you still hold it, so the "
                        "resting stop went straight back in."
                        % key.split("|")[-1])
        except Exception:                               # noqa: BLE001
            pass

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
        # A position Webull keeps refusing to sell must not be re-armed on
        # every adoption pass — that was the 8/12 loop (fail, adopt, arm,
        # fail...). It stays in the book and visible; it just stops pretending
        # a stop is going to work until he clears it at the broker.
        with self._lock:
            _p = self._pos.get(key) or {}
            if _p.get("no_auto_stop") or (str(_p.get("symbol") or "").upper(), _p.get("strike"), str(_p.get("expiry") or "")) in self.broker_blocked:
                return
        # SWING with THEIR stock level (8/24): no premium stop at all — the
        # bridge's underlying watcher guards it at their level; a resting
        # premium stop here is the scalp-stop that killed the HOOD swing in
        # 3 minutes. A born bracket leg, if one slipped through, is
        # cancelled so it can't sell the swing on noise.
        _wb0 = _bid0 = None
        with self._lock:
            _sp = self._pos.get(key)
            _is_swing_lvl = bool(_sp and _sp.get("swing")
                                 and _sp.get("their_stop")
                                 and _sp.get("kind") != "future")
            if _is_swing_lvl:
                _wb0 = self._wbfor(_sp)
                _bid0 = _sp.get("bracket_stop_id")
                _sp["bracket_stop_id"] = None
                _sp["stop"] = None
                self._event(key, "stop-set",
                            "%s — SWING: no premium stop; their stock level "
                            "%g is the guard (watched on this PC)"
                            % (sym, float(_sp["their_stop"])))
        if _is_swing_lvl:
            if _bid0 and _wb0 is not None:
                try:
                    _wb0.cancel(_bid0)
                except Exception:                       # noqa: BLE001
                    pass
            return
        # Tick-rounded to the exchange step (0.05 under $3, 0.10 above), the
        # same snap webull_options applies on the way out — so the number in
        # the book, the log, and the REBASE comparison below is the number
        # that actually rests at the broker. Before this, SLV showed 2.46
        # while the broker held 2.45, and CDE's rebase line promised 1.22
        # while 1.20 went out.
        # stop strictly BELOW the fill (8/31 IWM: nearest-rounding put the
        # stop AT the 0.20 fill -> stopped in 7 seconds). Same rule as
        # webull_options.stop_below, inlined to keep this module standalone.
        # SWING-AWARE (9/2): a swing with no caller level runs the WIDE
        # -25% stop (the house rule) — the restore/re-arm path used to
        # hand it the -10% scalp stop (FLR 9/2 01:00: "stop at 1.50, -9%
        # from 1.64" on an 18-DTE swing = the HOOD lesson all over again).
        with self._lock:
            _ps = self._pos.get(key) or {}
            _pct = (25.0 if (_ps.get("swing") and not _ps.get("their_stop"))
                    else self.stop_pct)
        stop_price = max(0.01, float(_tick_round(
            float(fill) * (1 - _pct / 100), sym)))
        if stop_price >= float(fill) - 1e-9:
            _stp = _tick_step(float(fill), sym)
            stop_price = max(0.01, round(float(fill) - _stp, 2))
        oid = None
        with self._lock:
            p = self._pos.get(key)
            wb = self._wbfor(p)
            old = p.get("stop_order_id") if p else None
            # Born-with-the-order stop (8/19): the entry went out as a linked
            # group and its stop leg is ALREADY resting at Webull. Adopt that
            # leg — placing a second stop here would be the very two-resting-
            # sells problem the group exists to end. The ratchet still moves
            # it later (cancel+replace path, unchanged).
            born = p.get("bracket_stop_id") if p else None
            if born and not old:
                _bs = float(p.get("bracket_stop") or stop_price)
                # REBASE (8/24, the HOOD lesson): the bracket leg was priced
                # off the ORDER (7.86 -> stop 7.07) but the fill came better
                # (7.50) — a 6% stop wearing 10% clothes. When the born stop
                # sits tighter than the fill deserves, cancel it (below, via
                # the normal path) and place a fresh one off the FILL.
                if _bs > stop_price + 0.02:
                    old = str(born)
                    p["bracket_stop_id"] = None
                    # Print the TRUE percent of the tick-rounded price, not
                    # the setting — on a nickel-step contract "-10%" can
                    # really be -11% (CDE 8/25: 1.35 fill, 1.20 stop).
                    _pa = ((1 - stop_price / float(fill)) * 100
                           if float(fill or 0) > 0 else self.stop_pct)
                    self._event(key, "stop-set",
                                "%s — filled better than the bid the bracket "
                                "was priced off; moving the stop from %.2f "
                                "to %.2f (-%.0f%% of the FILL)"
                                % (sym, _bs, stop_price, _pa))
                else:
                    p["stop"] = _bs
                    p["stop_order_id"] = str(born)
                    p["bracket_stop_id"] = None
                    if not p.get("watching"):
                        p["watching"] = True
                        threading.Thread(target=self._watchdog, args=(key,),
                                         daemon=True).start()
                    self._event(key, "stop-set",
                                "%s — stop was born WITH the order and is resting "
                                "at Webull at %.2f (one group, no naked moment)"
                                % (sym, float(p["stop"])))
                    return
        if wb is not None and not self._sim(p):
            # Averaging in moves the stop, so the old one has to go first or
            # you end up with two resting sells and get flattened twice.
            # And WAIT for the cancel to land (8/18): cancels are async, and
            # placing the new stop while the old one still rests is every
            # "ratchet couldn't move the resting stop" 417 of the day —
            # AAPL's +30% lock failed eight times in a row over this race
            # and gave back ~$19 of locked profit.
            if old:
                try:
                    wb.cancel(old)
                except Exception:                       # noqa: BLE001
                    pass
                try:
                    self._await_cancel(wb, old)
                except Exception:                       # noqa: BLE001
                    pass
            try:
                try:
                    oid, stop_price = wb.place_stop(sym, side, strike, expiry,
                                                    qty, fill,
                                                    stop_price=stop_price)
                except Exception as e0:                 # noqa: BLE001
                    # "can't hold a resting stop" is nearly always an older
                    # order still sitting on the contract. Clear it and try
                    # once more before giving up and going watchdog-only.
                    up0 = str(e0).upper()
                    if ("MUST_BE_CLOSE_THAN_SELL_SHORT" in up0
                            or "CAVERED_CALL_STOCK_NO_ENOUGH" in up0
                            or "REVERSE" in up0
                            or "EXCESS OF CURRENT HOLDING" in up0):
                        if self._clear_orphans(wb, key, sym, strike):
                            oid, stop_price = wb.place_stop(sym, side, strike,
                                                            expiry, qty, fill,
                                                            stop_price=stop_price)
                        else:
                            raise
                    else:
                        raise
                _pa = ((1 - stop_price / float(fill)) * 100
                       if float(fill or 0) > 0 else self.stop_pct)
                self._event(key, "stop-set",
                            "%s — stop resting at Webull at %.2f (-%.0f%% from "
                            "%.2f)" % (sym, stop_price, _pa, fill))
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
        # SUBSCRIBE AT ARM TIME, not only from inside the watchdog loop
        # (9/4). The watchdog is one thread that can return early — no occ,
        # no stop, a broker that won't resolve — and when it does, the
        # contract is never handed to the quote bus and nothing is ever
        # taped for it. Subscribing here means the tape starts the moment
        # the position is armed, independent of that thread's health.
        try:
            _b = getattr(self, "quotes", None)
            _o = (self._pos.get(key) or {}).get("occ")
            if _b is not None and _o:
                _b.watch(_o)
            # Same line, same moment, for greeks. The bridge ALSO mirrors the
            # quote bus into the greeks feed every 2s, which covers restored
            # and adopted positions — but a new fill should not wait up to
            # two seconds to start streaming, and this must not depend on
            # that thread being alive.
            _gb = getattr(self, "greeks", None)
            if _gb is not None and _o:
                _gb.watch(_o)
        except Exception:                               # noqa: BLE001
            pass
        # Stamp the ENTRY greeks once, here, because this runs seconds after
        # the fill. Delta/IV at entry is half of every question worth asking
        # later — a -$50 trade at 0.15 delta and a -$50 trade at 0.60 delta
        # are not the same mistake.
        try:
            with self._lock:
                _pg = self._pos.get(key)
                if _pg is not None and not _pg.get("greeks_in"):
                    _g = self._greeks_now(_pg)
                    if _g:
                        _pg["greeks_in"] = _g
        except Exception:                               # noqa: BLE001
            pass
        if self._sim(p):
            _pa = ((1 - stop_price / float(fill)) * 100
                   if float(fill or 0) > 0 else self.stop_pct)
            self._event(key, "stop-set",
                        "%s — pretend stop at %.2f (-%.0f%% from %.2f)"
                        % (sym, stop_price, _pa, fill))

    def _watchdog(self, key):
        """Checks the bid. If it's at or under the stop, sells what's left.

        This is the half that works when the resting stop was refused, and the
        half that catches a contract gapping straight through the trigger.
        After a trim it guards the remainder — 2 contracts still get a stop."""
        _occ_watched = None
        _bus = getattr(self, "quotes", None)
        _last_direct = 0.0
        try:
          while True:
            time.sleep(self.poll_seconds)
            with self._lock:
                p = self._pos.get(key)
                if not p or p["state"] != FILLED or p.get("closing"):
                    return
                occ, stop, qty = p["occ"], p["stop"], p["qty"]
                sym = p["symbol"]
                side, strike, expiry = p["side"], p["strike"], p["expiry"]
                wb = self._wbfor(p)
            if wb is None or not occ or not stop:
                return
            try:
                # v3.5.0 BLOCK C: read from the shared quote bus when there
                # is one (one batched call feeds every position, ~300ms
                # fresh). SAFETY: if the bus has no fresh quote for this
                # contract, fall back to a direct quote at most every 2s —
                # a dead bus can never make a stop blind.
                if _bus is not None:
                    if _occ_watched != occ:
                        _bus.watch(occ)
                        _occ_watched = occ
                    _ask, bid, _row = _bus.get(occ)
                    if bid is None and time.time() - _last_direct >= 2.0:
                        _last_direct = time.time()
                        _ask, bid, _row = wb.ask_bid(occ)
                        # TAPE THE FALLBACK (9/4). When the bus has nothing
                        # fresh, this direct quote is the ONLY price anyone
                        # will ever see for this contract — and until today
                        # it was thrown away, which is why 9/4 has no NVDA
                        # ticks at all despite the ratchet moving four times
                        # off these very quotes. Record it.
                        try:
                            _bus.tape(occ, bid, _ask)
                        except Exception:               # noqa: BLE001
                            pass
                else:
                    _ask, bid, _row = wb.ask_bid(occ)
            except Exception:                           # noqa: BLE001
                continue        # a missed quote is not a reason to sell
            if bid is not None:
                # Kept so the account can be marked to market, and so a close
                # that arrives without a price still has a real number to use.
                with self._lock:
                    q = self._pos.get(key)
                    if q:
                        q["last_bid"] = float(bid)
                        try:
                            q["last_ask"] = float(_ask) if _ask else None
                        except (TypeError, ValueError):
                            q["last_ask"] = None
                # High-water / low-water mark of the trade, same live bid.
                self._mark_excursion(key, float(bid))
                # His rule runs here, on the same live bid the stop watches.
                # Take-profit first: if the position is up +N% it closes ALL of
                # it and we're done — nothing else to manage. Then the sim-only
                # secure/ladder tactics for a paper trade that's still open.
                if self.auto_take_profit(key, float(bid)):
                    return
                self.auto_ratchet(key, float(bid))
                self.auto_breakeven(key, float(bid))
                self.auto_ladder(key, float(bid))
                with self._lock:
                    q2 = self._pos.get(key)
                    if not q2 or q2.get("state") != FILLED:
                        return
                    stop = q2.get("stop")
                    # The ratchet may have been REFUSED by the broker; the
                    # level it wanted is still the level that protects this
                    # trade, so the watchdog enforces the higher of the two.
                    _soft = q2.get("soft_stop")
                    if _soft is not None:
                        stop = _soft if stop is None else max(float(stop), float(_soft))
            if bid is None or stop is None or float(bid) > float(stop):
                continue
            if not self.claim(key):
                return          # the resting stop or their trim got there first
            self._event(key, "stopped",
                        "%s — bid hit %.2f, at or under your %.2f stop. Selling "
                        "%d." % (sym, float(bid), float(stop), qty))
            if self._sim(p):
                self.finish(key, STOPPED, "pretend stop-out at %.2f" % float(bid),
                            price=float(bid))
                return
            try:
                _okf, _px = self._sell_confirmed(wb, key, occ, sym, side,
                                                 strike, expiry, qty,
                                                 float(bid))
                if _okf:
                    self.finish(key, STOPPED,
                                "stopped out at %.2f" % float(_px),
                                price=float(_px))
                    return
                # Accepted but NEVER filled, twice — the truth is you're
                # still holding. Hand the claim back and keep watching;
                # pretending it sold is how CLF/MP went wrong. No re-arm:
                # the next tick claims again and would pull it right back.
                self.release(key, rearm=False)
                self._event(key, "stop-warn",
                            "%s — the stop's sell was accepted but never "
                            "FILLED (tried twice, repriced once). Still "
                            "HOLDING; the watchdog keeps trying." % sym)
                continue
            except Exception as e:                      # noqa: BLE001
                # FIRST: is there anything left to sell? (8/18) The resting
                # stop at Webull often fills a beat before the watchdog
                # fires, and every "failure" after that is the watchdog
                # racing a sale that already happened. If the broker shows
                # nothing left, the trade is DONE — say so once, quietly,
                # and stand down instead of counting phantom failures.
                if self._gone_at_broker(wb, sym, side, strike):
                    self._event(key, "stopped",
                                "%s — the resting stop at Webull had already "
                                "sold it; the watchdog stands down. Trade "
                                "closed." % sym)
                    self.finish(key, STOPPED,
                                "the resting stop at Webull sold it first")
                    return
                # Count it. The same rejection every 20s all morning (8/12:
                # LYFT 15 times, META 8) is noise that hides the one thing he
                # has to do, and re-adoption keeps feeding the loop. After
                # three, say it once, plainly, and stop re-arming this one.
                with self._lock:
                    q = self._pos.get(key) or {}
                    _ct = (str(q.get("symbol") or "").upper(), q.get("strike"),
                           str(q.get("expiry") or ""))
                    n = int(self.sell_fail_counts.get(_ct) or 0) + 1
                    self.sell_fail_counts[_ct] = n
                    q["sell_fails"] = n
                if n >= 3:
                    self._event(key, "failed",
                                "%s — the stop has tried to sell %d times and "
                                "Webull keeps refusing (%s). I've stopped "
                                "retrying it. Close this one in the Webull app, "
                                "and cancel any leftover order on it there."
                                % (sym, n, str(e)[:70]))
                    with self._lock:
                        q = self._pos.get(key)
                        if q is not None:
                            q["no_auto_stop"] = True
                            self.broker_blocked.add((str(q.get("symbol") or "").upper(), q.get("strike"), str(q.get("expiry") or "")))
                else:
                    self._event(key, "failed",
                                "%s — the stop tried to sell and couldn't: %s. "
                                "Retrying." % (sym, str(e)[:110]))
                self.finish(key, FAILED, "stop failed to sell")
            return
        finally:
            # the bus stops fetching a contract nobody watches any more
            if _bus is not None and _occ_watched:
                try:
                    _bus.unwatch(_occ_watched)
                except Exception:                   # noqa: BLE001
                    pass


    def _gone_at_broker(self, wb, sym, side, strike):
        """Does the broker still show this contract at all? The 8/18 morning
        in one question: MSFT/NVDA/VXX 'stop FAILED to sell' walls were the
        watchdog racing its own RESTING stop — the stop had already sold at
        Webull, so every follow-up sell 417'd against a position that wasn't
        there. A False positive here is dangerous (we'd stop guarding a real
        position), so ANY doubt — no client, query error — counts as still
        held and the failure keeps being treated as real."""
        if wb is None:
            return False
        try:
            side_word = ("CALLS" if str(side or "").upper().startswith("C")
                         else "PUTS")
            held = wb.positions() or []
            # positions() NEVER raises — on a throttle/timeout/bad body it
            # hands back an EMPTY LIST, which is indistinguishable from "the
            # account is flat". The except-guard below can therefore never
            # see that failure, and an empty list used to fall through to
            # "gone" and book a close that never filled: SPCX 139C 9/4
            # (8/25, 13:42:51) was recorded CLOSED at the MARK (-$10) while
            # the broker still held it — the 13:57 adoption sweep found it
            # sitting there. Empty is DOUBT, and doubt means still held.
            if not held:
                return False
            for p in held:
                if str(p.get("symbol") or "").upper() != str(sym or "").upper():
                    continue
                if p.get("side") and p.get("side") != side_word:
                    continue
                try:
                    if (p.get("strike") is not None and strike is not None
                            and abs(float(p["strike"]) - float(strike)) > 0.001):
                        continue
                except (TypeError, ValueError):
                    pass
                if int(p.get("qty") or 0) > 0:
                    return False    # still holding — the failure is real
            return True             # nothing left — something already sold it
        except Exception:                               # noqa: BLE001
            return False            # can't tell -> assume held, keep trying

    @staticmethod
    def _sell_blocked(msg):
        """Webull says 'something is in the way of this sell' in several voices —
        all mean a resting order still has the contract committed, all cured the
        same way (let go of it and ask again)."""
        msg = str(msg).upper()
        return ("MUST_BE_CLOSE_THAN_SELL_SHORT" in msg
                or "EXCESS OF CURRENT HOLDING" in msg
                or "CHECK YOUR OPEN ORDERS" in msg
                # "...it will reverse an existing position. You may need to ...
                # cancel an open order" (ORDER_NOT_SUPPORT_REVERSE_OPTION)
                or "REVERSE_OPTION" in msg
                or "REVERSE AN EXISTING POSITION" in msg
                # Webull reads a blocked long sale as opening a covered call and
                # complains about shares it never needed.
                or "CAVERED_CALL_STOCK_NO_ENOUGH" in msg
                or "COVERED_CALL_STOCK_NO_ENOUGH" in msg
                or "INSUFFICIENT NUMBER OF UNDERLYING" in msg)

    def _sell_confirmed(self, wb, key, occ, sym, side, strike, expiry, qty,
                        ref):
        """Sell URGENTLY (crossing the bid) and report True only when the
        broker says FILLED. The 8/21 CLF stop (and MP, and TSLA before it):
        a stop's sell was ACCEPTED, recorded as a fill, and never actually
        filled — the book said flat while the broker said holding, and the
        orphaned order 417-blocked every later exit. Acceptance is not a
        fill. This waits for the real fill, re-prices ONCE at the fresh bid
        if it has to, and tells the truth when it can't get out."""
        for _attempt in (0, 1):
            r = self._sell_retry(wb, key, sym, side, strike, expiry, qty,
                                 ref_price=ref, urgent=True)
            oid = r.get("order_id")
            px_fallback = r.get("limit") or ref
            if not oid:
                return True, px_fallback        # untrackable — old behavior
            deadline = time.time() + 25
            while time.time() < deadline:
                time.sleep(3)
                try:
                    state, fq, avg = wb.order_status(oid)
                except Exception:               # noqa: BLE001
                    continue
                s = str(state or "").lower()
                if s.startswith("fill") or (fq and int(fq) >= int(qty)):
                    return True, (avg or px_fallback)
                if s in ("dead", "cancelled", "canceled", "rejected",
                         "failed", "expired"):
                    break                       # go again at the fresh bid
            try:
                wb.cancel(oid)
            except Exception:                   # noqa: BLE001
                pass
            self._await_cancel(wb, oid)
            try:
                _a, _b, _ = wb.ask_bid(occ)
                if _b and float(_b) > 0:
                    ref = float(_b)             # round 2 prices off NOW
            except Exception:                   # noqa: BLE001
                pass
        return False, None

    def _sell_retry(self, wb, key, sym, side, strike, expiry, qty, **kw):
        """Sell, and if Webull refuses because something is still resting
        against the contract, clear it and try AGAIN — up to a few rounds.

        A single cancel-and-resend used to be enough on paper, but Webull's
        order-check system lags a cancel by a second or two, so the re-sent sell
        can race the cancel and hit the SAME REVERSE_OPTION block — then it gave
        up (8/19: TSLA 340P bled to -24% with an orphan stop-limit blocking every
        stop-out). So the recovery now LOOPS: pull our stop, pull every resting
        sell on the contract, wait a beat longer each round, and try the sell
        again — a few times before it's allowed to fail."""
        try:
            return wb.sell(sym, side, strike, expiry, qty, **kw)
        except Exception as e:                          # noqa: BLE001
            if not self._sell_blocked(e):
                raise
        last = None
        for attempt in range(4):
            with self._lock:
                p = self._pos.get(key) or {}
                oid = p.get("stop_order_id")
            if oid:
                try:
                    wb.cancel(oid)
                except Exception:                       # noqa: BLE001
                    pass
                self._await_cancel(wb, oid)
                with self._lock:
                    q = self._pos.get(key)
                    if q is not None:
                        q["stop_order_id"] = None
            # ALSO clear anything else of ours resting on this contract — an
            # orphan from an earlier run (or a stop-out that recorded closed but
            # never filled) blocks every following sell. Ask the broker what's
            # still working on this symbol and pull it, awaiting each cancel.
            pulled = self._clear_orphans(wb, key, sym, strike)
            if not oid and not pulled:
                time.sleep(1.0 + attempt)   # nothing to pull — settle, longer each round
            if attempt == 0:
                self._event(key, "update",
                            "%s — Webull said an order was still on this contract; "
                            "cleared it and re-sent the sell" % sym)
            try:
                return wb.sell(sym, side, strike, expiry, qty, **kw)
            except Exception as e2:                     # noqa: BLE001
                if not self._sell_blocked(e2):
                    raise
                last = e2                               # still blocked — loop and clear again
                time.sleep(0.5 + 0.5 * attempt)
        # Exhausted every round and it's still blocked — let the caller log a
        # real failure (and re-arm the stop / stand the watchdog back up).
        raise last if last is not None else RuntimeError("sell blocked")

    def _clear_orphans(self, wb, key, sym, strike=None):
        """Cancel every WORKING order the broker still has on this contract.

        Returns how many were pulled. Silent and safe when the SDK has no
        open-orders endpoint (returns []) — the caller falls back to waiting.
        Only ever cancels SELL-side orders on the exact contract, so a resting
        BUY entry somewhere else in the account is never touched."""
        if wb is None or not hasattr(wb, "open_orders"):
            return 0
        try:
            rows = wb.open_orders(sym) or []
        except Exception:                               # noqa: BLE001
            return 0
        pulled = 0
        for r in rows:
            try:
                if strike is not None and r.get("strike") is not None:
                    if abs(float(r["strike"]) - float(strike)) > 0.001:
                        continue
                act = str(r.get("action") or "").upper()
                if act and not act.startswith("S"):
                    continue        # never pull a buy
                oid = r.get("order_id")
                if not oid:
                    continue
                wb.cancel(oid)
                self._await_cancel(wb, oid)
                pulled += 1
            except Exception:                           # noqa: BLE001
                continue
        if pulled:
            self._event(key, "update",
                        "%s — pulled %d stale order(s) Webull still had resting "
                        "on this contract" % (sym, pulled))
        return pulled

    def _fee(self, p, qty):
        """Round-trip trading fees, per contract, for the honest sim — applied
        once at exit so a full open-and-close pays its fees exactly once."""
        n = int(qty or 0)
        if p.get("kind") == "future":
            return self.fee_future * n
        if p.get("kind") == "equity":
            return 0.0
        return self.fee_option * n

    def auto_take_profit(self, key, bid):
        """His one-click bracket, run by the watchdog on the live bid: the moment
        a position is up take_profit_pct, close ALL of it. Unlike breakeven/ladder
        this fires on LIVE too, with a real sell, because it's a real exit — the
        whole point is to bank +15% and be flat. Returns True if it closed."""
        if not self.take_profit_on or bid is None:
            return False
        with self._lock:
            p = self._pos.get(key)
            if not p or p.get("state") != FILLED or p.get("closing"):
                return False
            fill = float(p.get("fill") or 0)
            held = int(p.get("qty") or 0)
            dirn = int(p.get("direction") or 1)
            if not fill or held <= 0:
                return False
            gain = (float(bid) - fill) * dirn / fill * 100.0
            if gain < self.take_profit_pct:
                return False
            sym, side = p["symbol"], p.get("side")
            strike, expiry = p.get("strike"), p.get("expiry")
            wb = self._wbfor(p)
        if not self.claim(key):
            return False        # their exit or the stop got there first
        self._event(key, "update",
                    "%s — up %.0f%%, hitting your +%.0f%% take-profit. Closing "
                    "all %d." % (sym, gain, self.take_profit_pct, held))
        if self._sim(p):
            self.finish(key, CLOSED,
                        "take-profit at %.2f (+%.0f%%)" % (float(bid), gain),
                        price=float(bid))
            return True
        try:
            self._sell_retry(wb, key, sym, side, strike, expiry, held,
                             ref_price=float(bid))
            self.finish(key, CLOSED,
                        "take-profit sold at %.2f (+%.0f%%)" % (float(bid), gain),
                        price=float(bid))
        except Exception as e:                              # noqa: BLE001
            # FIRST: anything left to sell? (8/18) — same race as the stop:
            # a resting order can fill a beat ahead of the watchdog, and
            # every "failure" after that is against a position that's gone.
            if self._gone_at_broker(wb, sym, side, strike):
                self._event(key, "update",
                            "%s — already sold at Webull before the "
                            "take-profit got there (a resting order beat "
                            "it). Trade closed." % sym)
                self.finish(key, CLOSED,
                            "a resting order at Webull sold it first "
                            "(+%.0f%% at the time)" % gain,
                            price=float(bid))
                return True
            # Same breaker as the stop: three refusals on one contract and we
            # stop re-arming it, instead of re-adopting and re-failing every
            # 20s while a +30% winner sits there (8/12 QQQ).
            with self._lock:
                q = self._pos.get(key) or {}
                _ct = (str(q.get("symbol") or "").upper(), q.get("strike"),
                       str(q.get("expiry") or ""))
                n = int(self.sell_fail_counts.get(_ct) or 0) + 1
                self.sell_fail_counts[_ct] = n
            if n >= 3:
                with self._lock:
                    self.broker_blocked.add(_ct)
                    q2 = self._pos.get(key)
                    if q2 is not None:
                        q2["no_auto_stop"] = True
                self._event(key, "failed",
                            "%s — the take-profit has tried %d times and Webull "
                            "keeps refusing (%s). I've stopped retrying. SELL "
                            "THIS ONE IN THE WEBULL APP — it's up %.0f%% — and "
                            "cancel any leftover order on it."
                            % (sym, n, str(e)[:60], gain))
            else:
                self._event(key, "failed",
                            "%s — take-profit tried to sell and couldn't: %s. "
                            "Retrying." % (sym, str(e)[:110]))
            self.finish(key, FAILED, "take-profit failed to sell")
        return True

    def _futures_ratchet(self, key, price):
        """Points-based ratchet for futures (v3.5.0) — percent is meaningless
        when MNQ trades at 24,000. Uses the trade's own stop width: one
        stop-width of profit locks breakeven, every further one locks
        another. Needs a futures quote feed to fire; without one `price`
        never arrives and this is simply never called."""
        from ratchet_tiers import (futures_stop_points, futures_locked_points,
                                   futures_stop_price)
        if price is None:
            return
        with self._lock:
            p = self._pos.get(key)
            if not p or p.get("state") != FILLED or p.get("closing"):
                return
            entry = float(p.get("fill") or 0)
            dirn = int(p.get("direction") or 1)
            sym = p.get("symbol")
            if not entry:
                return
            gain_pts = (float(price) - entry) * dirn
            rung = futures_stop_points(sym, p.get("their_stop"), entry)
            locked = futures_locked_points(gain_pts, rung)
            new_stop = futures_stop_price(entry, locked, dirn, p.get("stop"))
            if new_stop is None:
                return
            p["stop"] = new_stop
            p["ratchet_locked_pts"] = locked
        self._event(key, "stop-set",
                    "%s — up %.0f pts, ratchet moved the stop to %g "
                    "(locked +%g pts, %g-pt rungs)"
                    % (sym, gain_pts, new_stop, locked, rung))

    def auto_ratchet(self, key, bid):
        """His replacement for the hard take-profit close (8/15): once a
        position reaches +take_profit_pct it no longer gets sold outright —
        instead the STOP walks up to lock in +stop_loss_pct, and every further
        step of gain (another take_profit_pct - stop_loss_pct) walks the stop
        up another notch, so a winner can run forever and can never come back
        red once it's locked. Uses the same resting-stop-at-Webull +
        watchdog-checks-the-bid pair every other stop uses — this only ever
        decides a new price for that same mechanism, never a new one. Runs
        AFTER auto_take_profit in the watchdog and only if that left the
        position open (take_profit_on stays a separate, still-available hard
        exit for anyone who wants the old all-or-nothing behaviour instead).
        """
        if not self.ratchet_on or bid is None:
            return
        with self._lock:
            p = self._pos.get(key)
            if not p or p.get("state") != FILLED or p.get("closing"):
                return
            fill = float(p.get("fill") or 0)
            dirn = int(p.get("direction") or 1)
            if not fill:
                return
            gain = (float(bid) - fill) * dirn / fill * 100.0
            # CHEAP-CONTRACT arm (his call, 8/25): a sub-$1.00 premium
            # breathes +/-10-15% on pure noise, so its ratchet arms at +15%
            # instead of +10% — otherwise the first wiggle scratches every
            # 0DTE lotto at breakeven and the runners leave without him.
            # Rungs after arming are unchanged.
            # TIERED (v3.5.0, 9/2): the rung plan comes from what he PAID,
            # not one global pair. <$1: arm +25%, lock +10%, 15% rungs (a
            # $0.40 contract moves 2.5% a tick — 5% rungs get scratched by
            # the quote). $1-2: arm +15%, BE, 10% rungs. $2+: arm +10%,
            # lock +5%, 5% rungs. See ratchet_tiers.py.
            locked = tier_locked_pct(gain, fill)
            if locked is None:
                return           # hasn't reached the first rung yet
            # ANTI-CLIP, BUT NOT ON 0/1DTE (9/3, his rule in one line:
            # "my rule on 0 and 1dte and anticlip on later expirations").
            # A 0DTE has no tomorrow — theta eats whatever it doesn't lock,
            # so his ladder takes the gain: +10% -> BE, +20% -> +10%,
            # +30% -> +20%. From 2 days out the trade has room to breathe
            # and anti-clip's 60%-of-gain cap keeps a runner from being
            # strangled by a rung (the 9/2 study).
            _dte = None
            try:
                import datetime as _dtx
                _ex = p.get("expiry")
                if _ex:
                    _exd = str(_ex)
                    if len(_exd) == 10 and _exd[4] == "-":
                        _dte = (_dtx.date.fromisoformat(_exd) - _dtx.date.today()).days
                    else:
                        from webull_options import expiry_to_date as _e2dx
                        _dte = (_dtx.date.fromisoformat(str(_e2dx(_exd)))
                                - _dtx.date.today()).days
            except Exception:                           # noqa: BLE001
                _dte = None
            if _dte is None or _dte >= 2:
                _before = locked
                locked = anti_clip(locked, gain)
                if _before != locked:
                    self._event(key, "update",
                                "%s — anti-clip held the stop at +%.0f%% instead "
                                "of +%.0f%% (never closer than 40%% of a +%.0f%% "
                                "gain; %s days out)"
                                % (p.get("symbol"), locked, _before, gain,
                                   _dte if _dte is not None else "?"))
            already = p.get("ratchet_locked_pct")
            if already is not None and locked <= float(already):
                return           # never loosen a stop that's already this high
            # v3.5.0: shorts ratchet too — a short's stop lives ABOVE the
            # entry and walks DOWN as the trade profits; ratchet_stop_price
            # handles both sides. Futures go through the points path.
            if p.get("kind") == "future":
                return self._futures_ratchet(key, bid)
            # Spread floor: a stop inside the bid/ask gets hit by the quote,
            # not by the trade. None = not safe or not an improvement -> no
            # API call spent on it.
            _ask = p.get("last_ask")
            new_stop = ratchet_stop_price(fill, locked, bid=bid, ask=_ask,
                                          current_stop=p.get("stop"),
                                          direction=dirn)
            if new_stop is None:
                return
            sym, side = p["symbol"], p.get("side")
            strike, expiry = p.get("strike"), p.get("expiry")
            qty = int(p.get("qty") or 0)
            old_oid = p.get("stop_order_id")
            wb = self._wbfor(p)
            if qty <= 0:
                return
        if self._sim(p):
            with self._lock:
                q = self._pos.get(key)
                if q is not None:
                    q["stop"] = new_stop
                    q["ratchet_locked_pct"] = locked
            self._event(key, "stop-set",
                        "%s — up %.0f%%, ratchet moves the pretend stop to "
                        "%.2f (locked +%.0f%%)" % (sym, gain, new_stop, locked))
            return
        if wb is None:
            return
        _cancelled_old = False
        try:
            new_oid = placed = None
            # v3.5.0 B4 — REPLACE first: modifies the resting stop in place,
            # so there is never a moment with no stop. The old cancel-then-
            # place left a real naked window and lied about it in the log.
            if old_oid and hasattr(wb, "replace_stop"):
                try:
                    new_oid, placed = wb.replace_stop(old_oid, sym, side,
                                                      strike, expiry, qty,
                                                      fill, stop_price=new_stop)
                except Exception:                       # noqa: BLE001
                    new_oid = placed = None             # fall through
            if placed is None:
                if old_oid:
                    try:
                        wb.cancel(old_oid)
                        _cancelled_old = True
                    except Exception:                   # noqa: BLE001
                        pass
                new_oid, placed = wb.place_stop(sym, side, strike, expiry, qty,
                                                fill, stop_price=new_stop)
        except Exception as e:                          # noqa: BLE001
            # Tell the truth about what is resting (the old log line claimed
            # the old stop was "still in place" even after cancelling it).
            self._event(key, "stop-warn",
                        "%s — up %.0f%%, but the ratchet couldn't move the "
                        "resting stop to %.2f (%s). %s"
                        % (sym, gain, new_stop, str(e)[:90],
                           ("NO broker stop is resting right now — the "
                            "watchdog on this PC is the only guard; retrying "
                            "next pass." if _cancelled_old else
                            "The old stop is still in place; the watchdog "
                            "on this PC covers the gap.")))
            # SOFT STOP (9/3, the TSLA 8/26 post-mortem): this branch has
            # always claimed "the watchdog on this PC covers the gap" — and
            # it did not. The watchdog reads p["stop"], and p["stop"] was
            # only ever updated on SUCCESS, so after a refusal the local
            # guard was still watching the OLD, lower level. TSLA 350P
            # peaked +16%, the ratchet tried three times to move the stop to
            # breakeven (5.15) and Webull refused all three on
            # DAY_BUYING_POWER_INSUFFICIENT, and the trade still died at the
            # original 4.60 for -$45. Record the level we WANTED; the
            # watchdog now enforces it locally even with no resting order.
            with self._lock:
                q = self._pos.get(key)
                if q is not None:
                    if _cancelled_old:
                        q["stop_order_id"] = None       # so the next pass re-arms
                    _prev = q.get("soft_stop")
                    if _prev is None or float(new_stop) > float(_prev):
                        q["soft_stop"] = float(new_stop)
            return
        with self._lock:
            q = self._pos.get(key)
            if q is not None:
                q["stop"] = placed
                q["stop_order_id"] = new_oid
                q["ratchet_locked_pct"] = locked
                q.pop("soft_stop", None)   # a real resting stop supersedes it
        self._event(key, "stop-set",
                    "%s — up %.0f%%, ratchet moved your stop to %.2f — locked "
                    "in +%.0f%%, can't go red from here" % (sym, gain, placed,
                                                            locked))

    def auto_breakeven(self, key, bid):
        """His secure-the-trade rule, run by the watchdog: once a live position
        is up auto_be_pct, sell auto_be_frac of it and drag the stop to the
        entry price so the runner can't turn into a loss. Once per position."""
        if not self.auto_be_on or bid is None:
            return
        with self._lock:
            p = self._pos.get(key)
            if not p or p.get("state") != FILLED or p.get("be_done"):
                return
            # Test-money tactic only. On a LIVE position this would shrink the
            # ledger without actually selling a real contract, so the book and
            # the account would drift apart. Live follows the room's real calls
            # and the real resting stop, nothing self-invented.
            if p.get("live"):
                return
            fill = float(p.get("fill") or 0)
            held = int(p.get("qty") or 0)
            mult = float(p.get("mult") or 100)
            dirn = int(p.get("direction") or 1)
            if not fill or held <= 0:
                return
            gain = (float(bid) - fill) * dirn / fill * 100.0
            if gain < self.auto_be_pct:
                return
            n = max(1, int(round(held * self.auto_be_frac)))
            n = min(n, held - 1) if held > 1 else 0     # keep a runner if you can
            p["be_done"] = True
            p["stop"] = fill                            # breakeven — can't lose
        if n > 0:
            self.trim(key, n, float(bid),
                      "auto: +%.0f%% so securing profit" % self.auto_be_pct)
        self._event(key, "update",
                    "%s — up %.0f%%, took %d off and moved the stop to "
                    "breakeven. This trade can't lose now."
                    % (key.split("|")[-1], self.auto_be_pct, n))

    def auto_ladder(self, key, bid):
        """His exit ladder, run by the watchdog on the live bid. For each rung
        not yet hit, once the position is up that %, sell the rung's size
        (never below ladder_keep runners) and, if the rung says so, drag the
        stop to entry*(1+stop_to/100). His plan: +10% same stop, +20%
        breakeven, +30% lock +10%. Their own trims/exits still fire on top —
        this is the safety net for the ones they don't call."""
        if not self.ladder_on or bid is None or not self.ladder_rungs:
            return
        actions = []
        with self._lock:
            p = self._pos.get(key)
            if not p or p.get("state") != FILLED:
                return
            # Test-money tactic only — see auto_breakeven. A LIVE position must
            # not be trimmed by a ledger-only routine; it would desync from the
            # real account. Live rides the room's calls and the real stop.
            if p.get("live"):
                return
            fill = float(p.get("fill") or 0)
            dirn = int(p.get("direction") or 1)
            if not fill:
                return
            gain = (float(bid) - fill) * dirn / fill * 100.0
            done = p.setdefault("ladder_hit", [])
            for rung in sorted(self.ladder_rungs, key=lambda r: float(r["at"])):
                at = float(rung["at"])
                if at in done or gain + 1e-9 < at:   # epsilon: 19.999% == 20%
                    continue
                held = int(p.get("qty") or 0)
                room = held - int(self.ladder_keep)     # sellable above runners
                want = min(int(rung.get("sell", 1)), room) if room > 0 else 0
                done.append(at)
                if rung.get("stop_to") is not None:
                    p["stop"] = round(fill * (1 + float(rung["stop_to"]) / 100.0), 4)
                    actions.append((at, want, float(rung["stop_to"])))
                else:
                    actions.append((at, want, None))
        # sell + narrate outside the lock (trim takes the lock itself)
        for at, want, stop_to in actions:
            if want > 0:
                self.trim(key, want, float(bid),
                          "auto ladder: +%.0f%% —" % at)
            if stop_to is not None:
                where = ("breakeven" if stop_to == 0
                         else "+%.0f%%" % stop_to)
                self._event(key, "update",
                            "%s — ladder hit +%.0f%%, stop moved to %s"
                            % (key.split("|")[-1], at, where))

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
            sym0 = p["symbol"]
            side0, strike0, expiry0 = p["side"], p["strike"], p["expiry"]
            fut0 = p.get("kind") == "future"
            real0 = not self._sim(p)
            wb0 = self._wbfor(p)
        # ANTI-PHANTOM (8/11/26). On 8/10 the book "sold" META at 7.88 for a
        # +$158 trim that never existed at Webull — the trim was pure book
        # arithmetic, no broker order behind it. A trim on a REAL position
        # (live or sandbox) must now BE a real sale: the sell goes to the
        # broker FIRST, and only a sell the broker accepted gets written into
        # the book. Refused/unreachable -> nothing recorded, said out loud.
        # Futures keep their own execution path; the dry-run sim is untouched.
        if real0 and not fut0 and wb0 is not None:
            try:
                try:
                    self._sell_retry(wb0, key, sym0, side0, strike0, expiry0, n,
                                     ref_price=price)
                except TypeError:
                    self._sell_retry(wb0, key, sym0, side0, strike0, expiry0, n)
                # BROKER PRICE, NOT THE BID (9/3, WMT): the trim was written
                # down at p["last_bid"] — WMT sold at the broker for 2.21 and
                # the book recorded 2.17, so a +$4 trade journaled as +$0.
                # Same lesson as the 8/27 phantom exit: ask what it ACTUALLY
                # sold for. Only overwrite on a sane answer; the bid stands
                # if the broker can't say.
                try:
                    _real = wb0.last_sell_fill(sym0, side0, strike0, expiry0,
                                               since=time.time() - 120)
                    if _real and float(_real) > 0 and abs(float(_real) - price) < max(0.5, price * 0.5):
                        if abs(float(_real) - price) >= 0.005:
                            self._event(key, "update",
                                        "%s — the broker filled that trim at %.2f, "
                                        "not the %.2f bid I quoted; using the real "
                                        "fill" % (sym0, float(_real), price))
                        price = float(_real)
                except Exception:                       # noqa: BLE001
                    pass
            except Exception as e:                      # noqa: BLE001
                # A trim can collide with a stop exactly like a close can
                # (his pick #6, 8/18). If the broker shows nothing left, the
                # stop won the race and sold EVERYTHING — record the trade
                # done instead of warning as if the trim just vanished.
                if self._gone_at_broker(wb0, sym0, side0, strike0):
                    self._event(key, "stopped",
                                "%s — their trim collided with the stop and "
                                "the stop won; everything sold. Trade closed."
                                % sym0)
                    self.finish(key, STOPPED,
                                "the resting stop sold it as their trim "
                                "arrived", price=price)
                    return 0
                self._event(key, "stop-warn",
                            "%s — their trim did NOT sell at the broker (%s). "
                            "Nothing recorded — the book still shows what you "
                            "really hold." % (sym0, str(e)[:120]))
                # The failed trim pulled the resting stop on the way in —
                # put it straight back if the position survived (8/18).
                try:
                    self.rearm_stop_after_failed_exit(key)
                except Exception:                       # noqa: BLE001
                    pass
                return 0
        with self._lock:
            p = self._pos.get(key)
            if not p or p["state"] != FILLED:
                return 0
            held = int(p.get("qty") or 0)
            n = min(n, held)
            if n <= 0:
                return 0
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
            # Real fees: a contract costs something to trade, both ends.
            fee = self._fee(p, n) if self.realistic else 0.0
            got -= fee
            pl -= fee
            if self.cash is not None and not p.get("live"):
                self.cash += got
                self.realised += pl
                if p.get("assumed"):
                    self.realised_assumed += pl
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
            p.pop("pulled_stop", None)
            sym = p["symbol"]
            oid = p.get("stop_order_id")
            p["stop_order_id"] = None
            wb = self._wbfor(p)
        if oid and wb is not None and not self._sim(p):
            try:
                wb.cancel(oid)
                # A cancel is a REQUEST, not an event. Webull keeps the
                # contract committed to the dying order for a moment, and a
                # sell sent into that window comes back "you can not place an
                # order in excess of current holding quantity" — which is
                # exactly what killed the 8/12 META and LYFT stops, one second
                # after the pull. So wait for the broker to actually let go.
                self._await_cancel(wb, oid)
                # Remembered so release() can put it BACK if the sell never
                # goes out (9/2: SPY 766C sat naked five minutes after a
                # pull-then-refuse).
                with self._lock:
                    p2 = self._pos.get(key)
                    if p2 is not None:
                        p2["pulled_stop"] = {"oid": oid, "stop": p2.get("stop")}
                self._event(key, "stop-pulled",
                            "%s — pulled the resting stop before selling" % sym)
            except Exception:                           # noqa: BLE001
                self._event(key, "stop-warn",
                            "%s — couldn't pull the resting stop. If it's still "
                            "in Webull after this sells, cancel it by hand."
                            % sym)
        return True

    def _await_cancel(self, wb, oid, tries=6, pause=0.5):
        """Block until the broker says that order is really gone (dead/filled),
        up to ~3s. Returns True if confirmed. Never raises — an unconfirmed
        cancel still lets the sell try; the retry below is the backstop."""
        if wb is None or not oid or not hasattr(wb, "order_status"):
            return False
        for _ in range(int(tries)):
            try:
                st, _fq, _avg = wb.order_status(oid)
            except Exception:                           # noqa: BLE001
                return False
            if st in ("dead", "filled"):
                return True
            time.sleep(pause)
        return False

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
            wb = self._wbfor(p)
        self._unreserve(key)
        if oid and wb is not None and not self._sim(p):
            try:
                wb.cancel(oid)
            except Exception:                           # noqa: BLE001
                self._event(key, "stop-warn",
                            "%s — couldn't pull the resting bid. If it's still "
                            "in Webull, cancel it there by hand." % sym)
            # CONFIRM the pull (8/26, the SPY 766P race): a cancel is a
            # REQUEST — Webull can fill the bid before it lands. The old
            # fire-and-forget left a real position marked NOFILL; the
            # trader's exit (the very reason for this pull) then found
            # "nothing to sell" and the orphan sat until adoption, two
            # minutes after the room had left. Poll briefly: if the bid
            # actually FILLED, mark it held so the exit that pulled us
            # sells it right now.
            try:
                for _ in range(4):
                    time.sleep(1.5)
                    _st, _fq, _px = self._probe(oid, p.get("occ"),
                                                p.get("limit"),
                                                live=bool(p.get("live")),
                                                wb=wb,
                                                paper=bool(p.get("paper")))
                    if _st == FILLED and (_fq is None or _fq):
                        with self._lock:
                            p2 = self._pos.get(key)
                            if p2 is not None:
                                p2["state"] = FILLED
                                p2["qty"] = int(_fq or p2.get("qty") or 1)
                                if _px:
                                    p2["fill"] = float(_px)
                                p2.pop("closed_at", None)
                        held = int(_fq or 1)
                        self._event(key, "update",
                                    "%s — the cancel LOST the race: the bid "
                                    "filled at %s before the pull landed. "
                                    "You hold %d — selling it on their exit "
                                    "now." % (sym, _px if _px else "?", held))
                        break
                    if _st in ("dead", NOFILL) or _st == "cancelled":
                        break
            except Exception:                           # noqa: BLE001
                pass
            # THE ACCOUNT IS THE LAST WORD (9/3, SPY 771P): the probe said
            # not-filled and the bid was declared dead — but Webull had
            # filled it at 2.02 seventy-nine seconds EARLIER. The position
            # then sat outside the book for four hours, guarded only by the
            # bracket stop that was born with the order. An order probe can
            # lie (throttled, renamed endpoint, unknown); the positions list
            # cannot. Ask it before saying "you own nothing".
            if not held and wb is not None and not self._sim(p):
                try:
                    for _r in (wb.positions() or []):
                        if str(_r.get("symbol") or "").upper() != sym.upper():
                            continue
                        if _r.get("strike") is not None and p.get("strike") is not None \
                                and abs(float(_r["strike"]) - float(p["strike"])) > 0.001:
                            continue
                        _rs = str(_r.get("side") or "").upper()
                        if _rs and p.get("side") and _rs != str(p["side"]).upper():
                            continue
                        _q = abs(int(float(_r.get("qty") or 0)))
                        if _q <= 0:
                            continue
                        with self._lock:
                            p3 = self._pos.get(key)
                            if p3 is not None:
                                p3["state"] = FILLED
                                p3["qty"] = _q
                                if _r.get("fill"):
                                    p3["fill"] = float(_r["fill"])
                                p3.pop("closed_at", None)
                        held = _q
                        self._event(key, "update",
                                    "%s — the order probe said no fill, but the "
                                    "ACCOUNT holds %d at %s. You DO own it; "
                                    "managing it now." % (sym, _q, _r.get("fill") or "?"))
                        break
                except Exception:                       # noqa: BLE001
                    pass
        self._event(key, "pulled",
                    "%s — %s. The bid is off the book%s"
                    % (sym, why, "; you own nothing here." if not held
                       else "; you still hold %d." % held))
        return held

    def release(self, key, rearm=True):
        """The close didn't happen after all. Put it back — the claim AND the
        resting stop claim() pulled on the way in (rearm=False for the one
        caller that is about to claim again on its very next tick: the
        watchdog's own stop-out loop, where a re-placed stop would only be
        pulled a second later).

        9/2 11:43, SPY 766C 9/3: the pullback's stock-stop claimed the
        position (stop pulled at Webull), the sell was then refused as a
        TEST-room order, and every refusal path called release() — which
        only cleared the flag. The contract sat with NO stop anywhere for five
        minutes until he sold it by hand at 1.87. A pulled stop goes back
        the moment the exit is abandoned, whatever the reason. Only a stop
        claim() itself pulled is re-armed: an adopted hand trade that never
        had one still gets none."""
        pulled = None
        with self._lock:
            p = self._pos.get(key)
            if p:
                p["closing"] = False
                pulled = p.pop("pulled_stop", None)
        if pulled and rearm:
            try:
                self.rearm_stop_after_failed_exit(key)
            except Exception:                           # noqa: BLE001
                pass

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
                # NEVER GUESS THE EXIT (8/27). This used to fall back to the
                # watchdog's last seen bid. A bid is what somebody MIGHT pay;
                # it is not an execution, and one line of it invented every
                # phantom in the 8/26-8/27 books:
                #   QQQ 709C  booked +$290, really +$8  (bid 3.97 vs fill 2.56)
                #   TSLA 350P booked  +$70, really -$45 (its bracket stop had
                #                                        already filled @4.70)
                #   SLV       booked   -$5, really -$42
                #   CDE       booked  -$10, really -$25
                #   QQQ 712P  booked  -$66, really -$29
                # The only honest exit price is one the broker printed. Callers
                # that know the fill pass it in; reconcile_gone now ASKS the
                # broker for it (see _broker_exit_price). When nobody knows,
                # price stays None and the money goes silent below — "sold, but
                # at a price I never saw" — which is the truth and is also what
                # this function's docstring has always promised.
                pass
            # The sentence that ended the trade, kept on the record — the
            # journal's "exit_by" column reads it (with state and the manual
            # flag) to say WHAT pulled the trigger (8/17).
            p.update(state=state, closing=False, qty=0, closed_at=time.time(),
                     closed_why=str(why or ""))
            p.pop("pulled_stop", None)      # the exit happened; nothing to put back

        money = ""
        if settle and self.cash is not None and qty and price is not None:
            if fut:
                # Points times multiplier times direction. No premium came
                # back because none went out.
                pl = (float(price) - float(entry or price)) * mult * qty * dirn
                got = pl
            else:
                got = float(price) * mult * qty
                pl = got - cost
            with self._lock:
                p_live = bool((self._pos.get(key) or {}).get("live"))
                if not p_live:
                    self.cash += got
                    self.realised += pl
                    if (self._pos.get(key) or {}).get("assumed"):
                        self.realised_assumed += pl
                p = self._pos.get(key)
                if p is not None:
                    p.setdefault("exits", []).append(
                        {"t": time.time(), "qty": qty,
                         "price": round(float(price), 4), "pl": round(pl, 2)})
                    p["trade_pl"] = float(p.get("trade_pl") or 0) + pl
                    p["cost"] = 0.0
                total = float((p or {}).get("trade_pl") or pl)
                if not p_live:
                    if total >= 0:
                        self.wins += 1
                    else:
                        self.losses += 1
                if True:
                    # RECORD THE LIVE ONES TOO (9/4). Everything below used
                    # to sit inside `if not p_live`, so the ONLY trades ever
                    # written to the day book were the pretend ones — the
                    # real-money trades, the entire point of the exercise,
                    # left no structured record at all. 26 day files hold
                    # exactly 2 rows between them while trades.log shows 125
                    # fills. The wallet maths stays gated above, because a
                    # live trade must never move the pretend cash; only the
                    # RECORD is unconditional now, tagged with which it was.
                    # THE SHAPE OF THE TRADE, not just its ends (9/4, G:
                    # "i want to get more weeks data off of trades").
                    # _mark_excursion has tracked hi_pct/lo_pct on every
                    # poll since 8/19 — and this row, the only one that
                    # survives the day, threw both away. Without them there
                    # is no way to ever ask the one question that matters
                    # for breathing room: how far did a WINNER go against
                    # me first? Entry, exit and P&L cannot answer that.
                    # Also kept: the contract, its DTE, and how it ended,
                    # so a stop-out can be told from a called exit later.
                    _pp = p or {}
                    _dte_c = None
                    try:
                        import datetime as _dtc
                        _ex_c = str(_pp.get("expiry") or "")[:10]
                        if len(_ex_c) == 10:
                            _dte_c = (_dtc.date.fromisoformat(_ex_c)
                                      - _dtc.date.fromtimestamp(
                                          _pp.get("opened_at") or time.time())
                                      ).days
                    except Exception:                   # noqa: BLE001
                        _dte_c = None
                    self.closed_trades.append(
                        {"key": key, "who": who, "symbol": sym, "qty": qty,
                         "fill": entry, "exit": round(float(price), 2),
                         "room": _pp.get("room"),
                         "pl": round(total, 2), "t": time.time(),
                         # how far it ran green / red, in % of the entry
                         "max_runup_pct": (round(float(_pp["hi_pct"]), 2)
                                           if _pp.get("hi_pct") is not None
                                           else None),
                         "max_drawdown_pct": (round(float(_pp["lo_pct"]), 2)
                                              if _pp.get("lo_pct") is not None
                                              else None),
                         "occ": _pp.get("occ"),
                         "side": _pp.get("side"),
                         "strike": _pp.get("strike"),
                         "expiry": _pp.get("expiry"),
                         "dte": _dte_c,
                         "swing": bool(_pp.get("swing")),
                         "stop_at_exit": _pp.get("stop"),
                         "why": why,
                         "state": state,
                         "live": p_live,
                         # GREEKS AT BOTH ENDS (9/4). Entry greeks are
                         # stamped when the stop is armed; these are the
                         # exit ones. Delta says how much of the move we
                         # actually captured, and IV at entry vs exit says
                         # whether a loss was direction or just vol coming
                         # out — which a P&L number alone can never tell.
                         "greeks_in": _pp.get("greeks_in"),
                         "greeks_out": self._greeks_now(_pp)})
                pot = self.cash
            day = ""
            if self.unlimited:
                day = ("day so far %s$%.0f"
                       % ("+" if self.realised >= 0 else "-",
                          abs(self.realised)))
                # Honesty tax: how much of that number was never checked
                # against a real seller. If the whole day is assumed, the
                # whole day is a hypothesis, and the log should say so.
                if abs(self.realised_assumed) >= 0.5:
                    day += (" (of which %s$%.0f rests on assumed fills)"
                            % ("+" if self.realised_assumed >= 0 else "-",
                               abs(self.realised_assumed)))
            money = (" · %s$%.0f on the trade · %s"
                     % ("+" if pl >= 0 else "-", abs(pl),
                        day if self.unlimited
                        else "account $%.0f" % pot))
        elif not settle:
            # trim() already banked the money chunk by chunk; just count it.
            with self._lock:
                p = self._pos.get(key)
                total = float((p or {}).get("trade_pl") or 0)
                if p is not None and p.get("live"):
                    pass          # Webull keeps the score on real money
                else:
                    if total >= 0:
                        self.wins += 1
                    else:
                        self.losses += 1
                    self.closed_trades.append(
                        {"key": key, "who": who, "symbol": sym, "qty": qty,
                         "fill": entry, "exit": None, "pl": round(total, 2),
                         "room": (p or {}).get("room"), "t": time.time()})
            money = (" · %s$%.0f on the whole trade"
                     % ("+" if total >= 0 else "-", abs(total)))
        elif self.cash is not None and qty:
            # Held contracts sold at a price nobody told us. The cash can't be
            # credited without inventing a number, so it says so instead of
            # quietly leaving the account short.
            money = " · sold, but at a price I never saw — account left as it was"
        self._event(key, state, "%s — %s%s" % (sym, why, money))

    def force_drop(self, symbol, why="removed from the popup", live=None):
        """Take a symbol out of the book, no questions asked.

        This is the ✕ button's backstop. The normal close path goes through
        claim(), which refuses when a position is already marked `closing` —
        and a position left mid-exit by a failed sell stays that way forever,
        so ✕ did nothing at all (8/12: a mislabelled SPY and a futures MESU6
        that no amount of clicking would clear). Nothing is sent to the broker
        here; this only makes the book agree with reality. Returns how many
        entries it dropped."""
        sym = str(symbol or "").upper()
        gone = 0
        with self._lock:
            for k in list(self._pos.keys()):
                p = self._pos.get(k) or {}
                if str(p.get("symbol") or "").upper() != sym:
                    continue
                # ✕ on a LIVE row must not also delete the paper one of the
                # same ticker, and vice versa.
                if live is not None and bool(p.get("live")) != bool(live):
                    continue
                p["closing"] = False
                p["watching"] = False
                p["qty"] = 0
                p["state"] = CLOSED
                p["closed_at"] = time.time()
                p["stop_order_id"] = None
                self._archive.append(self._pos.pop(k))
                gone += 1
        if gone:
            self._event("?|" + sym, "closed", "%s — %s" % (sym, why), qty=0)
        return gone

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

    # -- surviving a restart ---------------------------------------------------
    # Swing trades hold for DAYS now, and a bridge that forgets everything on
    # restart can't hold anything overnight. The bridge writes this alongside
    # every day file and reads it back at boot: FILLED positions always come
    # back (a swing is still yours tomorrow); the day's archive and scoreboard
    # come back only if it's still the same trading day.
    def export_state(self):
        with self._lock:
            keep = {}
            for k, p in self._pos.items():
                if p.get("state") == FILLED:
                    q = {kk: vv for kk, vv in p.items()
                         if isinstance(vv, (str, int, float, bool, list,
                                            dict, type(None)))}
                    keep[k] = q
            return {"pos": keep,
                    "archive": [dict(a) for a in self._archive],
                    "wallet": {"cash": self.cash, "realised": self.realised,
                               "realised_assumed": self.realised_assumed,
                               "wins": self.wins, "losses": self.losses,
                               "peak": self.peak,
                               "trades": list(self.closed_trades)}}

    def restore_state(self, data, same_day):
        if not isinstance(data, dict):
            return 0
        # An older/empty state.json can have "pos" as a list, not a dict.
        # Anything that isn't a proper {key: position} map is ignored rather
        # than crashing the whole bridge on boot.
        pos = data.get("pos")
        if not isinstance(pos, dict):
            pos = {}
        n = 0
        # DEAD PAPER GATE (8/27): a restored OPTION whose expiry passed while
        # the bridge was off is settled history, not a position. Restoring it
        # live armed a watchdog on a STALE quote — "up 58%" on Wednesday's
        # 0DTE, ratchet spam against a contract Webull rightly refused to
        # touch, and a phantom +$290 credited off the dead quote. Expired =
        # not restored, said plainly, zero credit (the market already ruled).
        pe = getattr(self, "expiry_parser", None)
        import datetime as _dt
        _today = _dt.date.today()

        def _dead(pp):
            if pp.get("kind") == "future":
                return False
            exp = pp.get("expiry")
            if not exp or pe is None:
                return False
            try:
                return pe(exp) < _today
            except Exception:                           # noqa: BLE001
                return False
        with self._lock:
            for k, p in pos.items():
                if not isinstance(p, dict):
                    continue
                if k in self._pos:
                    continue
                p = dict(p)
                if _dead(p):
                    self.note("EXPIRED  %s %s%s %s — expired while the "
                              "bridge was off; settled by the market, not "
                              "restored, nothing credited."
                              % (p.get("symbol"), p.get("strike"),
                                 str(p.get("side") or "")[:1],
                                 p.get("expiry")))
                    continue
                p["state"] = FILLED
                p["closing"] = False
                # VERIFY-BEFORE-TRUST (8/27): a restored position arms no
                # watchdog and no ratchet until the first broker sweep
                # confirms Webull actually still holds it. The photo is for
                # remembering; the broker is for truth. Its resting stop at
                # Webull guards the ~20s gap, as always.
                p["unverified"] = True
                # and forget the photo's last quote — if this position turns
                # out to be gone, the close must say "a price I never saw",
                # never credit stale numbers (tonight's phantom +$290).
                for _stale in ("last_bid", "bid", "hi_pct", "lo_pct"):
                    p.pop(_stale, None)
                self._pos[k] = p
                n += 1
            if same_day:
                self._archive = list(data.get("archive") or [])
                w = data.get("wallet") or {}
                self.cash = float(w.get("cash") or 0.0)
                self.realised = float(w.get("realised") or 0.0)
                self.realised_assumed = float(w.get("realised_assumed") or 0.0)
                self.wins = int(w.get("wins") or 0)
                self.losses = int(w.get("losses") or 0)
                self.peak = float(w.get("peak") or 0.0)
                self.closed_trades = list(w.get("trades") or [])
        # Stops re-arm outside the lock: each restored hold gets its
        # watchdog back, exactly as if it had just filled.
        # Watchdogs wait for the broker's word now (8/27) — see
        # reconcile_gone: the first sweep that finds the position still held
        # clears "unverified" and arms the stop then. Nothing armed here.
        if n:
            self.note("RESTORED %d position(s) from the last run — swings "
                      "survive a restart now" % n)
        return n

    def new_day(self):
        """Midnight in New York. Yesterday's file is already complete on disk
        — the bridge rewrote it on every event — so what resets here is the
        scoreboard: the finished-trade shelf, the day's P/L, the win/loss
        record, the peak. Without this, Wednesday's GOOGL and QQQ wins were
        still being counted on Thursday and '+$196' was really two days.
        Open positions carry over untouched — a trade held overnight is still
        a trade — and whatever they cost re-marks the peak from zero."""
        purged = 0
        with self._lock:
            self._archive = []
            self.realised = 0.0
            self.realised_assumed = 0.0
            self.wins = 0
            self.losses = 0
            self.closed_trades = []
            self.peak = 0.0
            # Clear the paper book so the popup starts each day clean. A LIVE
            # (real-money) hold is NEVER touched - only paper/sim positions are
            # dropped, and each one's watchdog stands down when its key vanishes.
            if self.reset_paper_daily:
                for k in list(self._pos):
                    if not self._pos[k].get("live"):
                        self._pos[k]["closing"] = True
                        self._pos.pop(k, None)
                        purged += 1
        self._mark_peak()
        if purged:
            self.note("NEW DAY  cleared %d paper position(s) for a clean slate "
                      "- live positions untouched" % purged)
