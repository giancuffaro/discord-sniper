"""
guards.py — the things that stop a good parser from having a bad day.

A signal room can get hacked, spammed, or just have a guy who posts the same
call four times. None of that should cost you money. Every check here answers
one question in plain English: is this specific message allowed to spend
money right now?
"""

import os
import time
from datetime import datetime

# See eastern.py — Windows has no timezone database and the plain zoneinfo
# import kills this on a fresh PC.
from eastern import ET
KILL_FILE = "STOP"          # create a file called STOP next to the bot to halt it


def key_of(trader, symbol):
    """One trade = one trader + one ticker, same as positions.key_of and
    posKey in guards.js. "brett|SPY" and "unraveler|SPY" are two different
    trades in the same name — that's the point."""
    who = str(trader or "?").strip().lower() or "?"
    return "%s|%s" % (who, str(symbol or "").upper())


def _key_sym(k):
    return str(k).split("|")[-1]


def _key_who(k):
    return str(k).split("|")[0]


def _echo_key(sig, who):
    """Trader + contract + posted price. A scribe repost or a reply-quote is
    word-for-word the same call; a real re-entry comes at a new price."""
    return "|".join(str(x) for x in
                    (str(who).lower(), sig.symbol, sig.strike, sig.expiry,
                     sig.side, sig.limit))


class Guards:
    def __init__(self, cfg, here="."):
        g = cfg.get("guards", {})
        self.channels = set(str(c) for c in cfg.get("channel_ids", []))
        self.authors = set(str(a) for a in cfg.get("author_ids", []))
        self.author_names = set(str(a).lower() for a in cfg.get("author_names", []))
        # The old knobs — max_qty, daily caps, average_in switches, add
        # ceilings, allowed-list refusals — are deleted, not defaulted. His
        # rule: "no filters wanted. id like to follow everything to the tee
        # as they do." What's left is safety, not preference.
        self.cooldown_s = float(g.get("cooldown_seconds", 5))
        self.dedupe_s = float(g.get("dedupe_seconds", 120))
        self.session_only = bool(g.get("regular_hours_only", True))
        self.open_hm = tuple(int(x) for x in g.get("open_time", "09:30").split(":"))
        # Entries only. Exits are never time-boxed — see check(), which only
        # applies this to OPEN. 16:00 is the closing bell, so this is now "any
        # call they make during the session", not "mornings only".
        self.close_hm = tuple(int(x) for x in g.get("close_time", "16:00").split(":"))
        self.max_age_s = float(g.get("max_message_age_seconds", 20))
        self.kill_path = os.path.join(here, KILL_FILE)

        self._last_fire = 0.0
        self._recent = {}       # signal key -> timestamp
        self._day = None
        self._count = 0
        # What the bot believes you're holding, keyed "trader|SYM" — Brett's
        # SPY and Unraveler's SPY are two different trades and both can be
        # open at once. The same admin calling the same ticker twice is still
        # caught, because that lands on the same key.
        self.open_pos = {}      # "trader|SYM" -> {side, strike, expiry, ts}
        # The last LOADING notice each admin posted. Their entry is two messages
        # — the contract, then the price — and this is what holds the first one
        # until the second one turns up. Per author, because both admins load
        # different things within minutes of each other.
        self.loaded = {}        # author (lowercased) -> {symbol, side, ...}
        # A3 - each caller's last contract per symbol, kept even after the
        # position closes, so a "same ones" re-entry can copy the expiry.
        self.last_call = {}     # "trader|SYM" -> {side, strike, expiry, limit, ts}
        # Four hours — Midas rests his bid at his price and waits; the old
        # 30-minute window threw away his "Filled at 1.46" 97 minutes after
        # the Loaded call, which was his only real trade of day one.
        self.loaded_window_s = float(g.get("loading_window_seconds", 14400))
        # A3 - auto-follow "same ones" re-entries once the contract resolves.
        # Never doubles up on a contract already held. False = log only.
        self.follow_reentries = bool(g.get("follow_reentries", True))
        # Checked again at resolve time: the LOADING rule doesn't check the
        # allowed list, so without this a two-message entry would be the one way
        # round it.
        self.allowed = set(str(a).upper() for a in cfg.get("allowed_symbols", []))

    # -- helpers --------------------------------------------------------------
    def _roll_day(self):
        today = datetime.now(ET).date()
        if self._day != today:
            self._day, self._count = today, 0


    def killed(self):
        return os.path.exists(self.kill_path) or os.path.exists(self.kill_path + ".txt")

    # -- the gate -------------------------------------------------------------
    def check(self, sig, channel_id, author_id, author_name, msg_epoch=None):
        """Returns (allowed: bool, reason: str). The reason is written to be
        read by a human at 9:31 in the morning, not by a developer."""
        self._roll_day()
        now = time.time()

        if self.killed():
            return False, ("the STOP file is there, so the bot is parked. "
                           "Delete it to start firing again.")

        if self.channels and str(channel_id) not in self.channels:
            return False, "that message wasn't in a channel you're listening to"

        if self.authors and str(author_id) not in self.authors:
            return False, ("%s isn't on your trusted-poster list, so it was ignored"
                           % author_name)
        if (not self.authors) and self.author_names and \
                str(author_name).lower() not in self.author_names:
            return False, ("%s isn't on your trusted-poster list, so it was ignored"
                           % author_name)

        if msg_epoch and self.max_age_s and (now - msg_epoch) > self.max_age_s:
            return False, ("that call is %.0f seconds old — too stale to chase"
                           % (now - msg_epoch))

        if self.session_only and sig.action in ("OPEN", "ADD") \
                and getattr(sig, "kind", None) != "future":
            # Futures trade nearly 24h (Sun 6PM ET - Fri 5PM ET, daily 5-6PM
            # break) — the mirror of guards.js applies the futures calendar
            # there; here futures simply skip the equities window.
            t = datetime.now(ET)
            if t.weekday() > 4:
                return False, "it's the weekend — the market is shut"
            mins = t.hour * 60 + t.minute
            o = self.open_hm[0] * 60 + self.open_hm[1]
            # Equity & ETF options close 4:00 ET; cash-index options (SPX, NDX,
            # RUT, XSP, VIX) trade to 4:15 ET, so those get the later bell.
            LATE = {"SPX", "SPXW", "XSP", "NDX", "NDXP", "RUT", "RUTW",
                    "VIX", "VIXW", "MRUT", "XND"}
            ch, cm = self.close_hm
            if str(getattr(sig, "symbol", "") or "").upper() in LATE:
                ch, cm = 16, 15
            c = ch * 60 + cm
            if not (o <= mins <= c):
                return False, ("it's %s ET — new option trades are only allowed "
                               "between %02d:%02d and %02d:%02d"
                               % (t.strftime("%H:%M"), self.open_hm[0],
                                  self.open_hm[1], ch, cm))

        # dedupe: the same call posted twice in a couple of minutes is one trade
        # What you're holding is checked before anything else, because "you're
        # already in AMD" tells you far more than "that looked like a repeat".
        # Per TRADER now: Brett being in SPY doesn't block Unraveler's SPY call.
        who = str(getattr(sig, "caller", "") or author_name or "").lower()

        # Double-up is per-CONTRACT, not per-ticker: holding QQQ 720P must NOT
        # block a fresh QQQ 717P call. Only the exact strike+expiry+side you
        # already hold counts as a double-up. Equity/futures carry no strike,
        # so for them the name IS the whole contract and the ticker match stays.
        def _same_ct(p):
            if sig.strike is None:
                return True
            try:
                return (str(p.get("side")) == str(sig.side)
                        and float(p.get("strike") or -1) == float(sig.strike)
                        and str(p.get("expiry") or "") == str(sig.expiry or ""))
            except Exception:  # noqa: BLE001
                return False
        _keyed = self.open_pos.get(key_of(who, sig.symbol))
        already = (_keyed if (_keyed and _same_ct(_keyed)) else next(
            # A position whose owner was never known blocks anyone's re-entry
            # in that same contract — better one missed trade than a doubled one.
            (p for k, p in self.open_pos.items()
             if _key_sym(k) == sig.symbol and _key_who(k) == "?"
             and _same_ct(p)), None))
        if sig.action == "OPEN" and already:
            return False, ("you're already in %s from their earlier call — "
                           "this one would double you up" % sig.symbol)

        # The echo guard: the same exact entry only runs once a day. Only
        # with a posted price — bare re-entries can't be told apart.
        if sig.action == "OPEN" and sig.limit is not None and                 _echo_key(sig, who) in getattr(self, "echoes", {}):
            return False, ("that exact call (same contract, same price) "
                           "already ran today — reads like a repost or a "
                           "reply quote, not a new trade")

        if sig.action in ("CLOSE", "TRIM") and \
                not self.open_pos.get(key_of(who, sig.symbol)) and \
                not any(_key_sym(k) == sig.symbol for k in self.open_pos):
            # This one matters more than it looks. At most brokers a sell with
            # nothing to sell isn't a no-op — it opens a short. Never send it.
            return False, ("you're not in %s, so there's nothing to %s — "
                           "the order was not sent"
                           % (sig.symbol,
                              "trim" if sig.action == "TRIM" else "close"))

        key = sig.key()
        last = self._recent.get(key)
        if last and (now - last) < self.dedupe_s:
            return False, ("already acted on that exact call %.0fs ago"
                           % (now - last))

        if sig.action in ("OPEN", "ADD"):
            if (now - self._last_fire) < self.cooldown_s:
                return False, ("still in the %.0fs cooldown after the last fire"
                               % self.cooldown_s)
            # The daily trade cap is gone — he follows every call they make.

        return True, "allowed"

    def resolve_symbol(self, sig, author_name=""):
        """A bare "Trimming @here", or a lone "20%", names no ticker. Everyone
        in the room knows which position they mean; a broker does not.

        Two admins run that room and they are usually in different things, so
        the first question is who said it — a trim from Brett means Brett's
        position. If that's not enough and you only hold one thing, it's that
        one. If it's still ambiguous, nothing is sent and you're told why,
        because guessing which position to close is how you end up flat on the
        wrong ticker and still holding the loser."""
        if sig.symbol or not getattr(sig, "needs_position", False):
            return sig

        who = str(getattr(sig, "caller", "") or author_name or "").lower()
        held = self.open_pos
        if not held:
            sig.why = ("a trim with no ticker in it, and you're not in "
                       "anything — nothing to close")
            return sig

        pick = self._pick_held(who)

        # Second try (8/11/26): the trim came from an admin who LOADED a
        # contract earlier — "Midas: Loaded $Spy 773p ... Midas: 11%". His
        # positions all read owner "?" after a pickup, so the name match
        # fails, but his own loading call says exactly which ticker he
        # trades. One unambiguous match only, never a guess between two.
        if not pick:
            ld = (self.loaded.get(who) or {}) if isinstance(
                getattr(self, "loaded", None), dict) else {}
            ld_sym = str(ld.get("symbol") or "").upper()
            if ld_sym:
                cands = [k for k in held if _key_sym(k) == ld_sym]
                if len(cands) == 1:
                    pick = cands[0]

        if not pick:
            what = ", ".join("%s (%s's call)" % (_key_sym(k), _key_who(k))
                             for k in sorted(held))
            sig.why = ("a trim with no ticker in it. You're in %s, and this came "
                       "from %s — I can't tell which one they meant, so nothing "
                       "was sent. Close it in the Webull app if you want out."
                       % (what, getattr(sig, "caller", "") or author_name
                          or "somebody I couldn't name"))
            return sig

        sig.symbol = _key_sym(pick)
        sig.fire = True
        sig.why = ("closing %s on their first trim — they didn't name it, but "
                   "it's the position %s put you in"
                   % (sig.symbol,
                      getattr(sig, "caller", "") or author_name or "they"))
        return sig

    def resolve_reenter(self, sig, author_name=""):
        """A3 mirror of resolveReenter: complete a "same ones" re-entry from
        the caller's held or last-called contract and fire it, unless
        follow_reentries is off or you already hold that exact contract."""
        if not getattr(sig, "reenter", False) or sig.action != "OPEN":
            return sig
        sym = str(sig.symbol or "").upper()
        if not self.follow_reentries:
            sig.fire = False
            sig.needs_position = False
            sig.why = ('a re-entry ("same ones") - follow_reentries is off, '
                       "nothing sent")
            return sig
        who = str(getattr(sig, "caller", "") or author_name or "").lower()
        ref = self.open_pos.get(key_of(who, sym)) or self.last_call.get(key_of(who, sym))
        if not ref and sym:
            cand = [k for k in list(self.open_pos) + list(self.last_call)
                    if _key_sym(k) == sym]
            cand.sort(key=lambda k: (self.open_pos.get(k)
                                     or self.last_call.get(k) or {}).get("ts", 0),
                      reverse=True)
            if cand:
                ref = self.open_pos.get(cand[0]) or self.last_call.get(cand[0])
        if ref:
            if sig.side is None:
                sig.side = ref.get("side")
            if sig.strike is None:
                sig.strike = ref.get("strike")
            if not sig.expiry:
                sig.expiry = ref.get("expiry")
            if getattr(sig, "limit", None) is None and ref.get("limit") is not None:
                sig.limit = ref.get("limit")
        sig.needs_position = False
        if not sig.symbol or sig.strike is None or not sig.side or not sig.expiry:
            sig.fire = False
            sig.why = ('a "same ones" re-entry I could not complete - no earlier '
                       "%s call on record to copy the contract from" % sym)
            return sig
        cur = self.open_pos.get(key_of(who, sym))
        if cur and str(cur.get("side")) == str(sig.side) \
                and float(cur.get("strike") or -1) == float(sig.strike) \
                and str(cur.get("expiry") or "") == str(sig.expiry or ""):
            sig.fire = False
            sig.why = ('a "same ones" re-entry but you are already in %s %s%s '
                       "- not doubling up"
                       % (sym, sig.strike, "C" if sig.side == "CALLS" else "P"))
            return sig
        sig.fire = True
        sig.why = ("re-entry: %s %s%s%s%s - same contract they last called"
                   % (sym, sig.strike, "C" if sig.side == "CALLS" else "P",
                      " " + sig.expiry if sig.expiry else "",
                      "" if getattr(sig, "limit", None) is None
                      else " @ %s" % sig.limit))
        return sig

    def _pick_held(self, who):
        """Which of your open positions did this admin mean? Their own first,
        and the only one open second — but never somebody else's. The keys are
        "trader|SYM", so "their own" is a prefix. Returns the KEY, or None
        when it can't be sure — and being sure is the whole point."""
        held = self.open_pos
        if not held:
            return None
        theirs = [k for k in held if who and _key_who(k) == who]
        # Their own, and when they hold several, the NEWEST — Aristotle runs
        # a swing and a scalp at once, and his bare "12%" / "Out" is always
        # about the trade he just opened, not the swing from Tuesday.
        if theirs:
            theirs.sort(key=lambda k: held[k].get("ts", 0), reverse=True)
            return theirs[0]
        if len(held) == 1:
            only = next(iter(held))
            owner = _key_who(only)
            if not who or owner == "?" or owner == who:
                return only
        return None

    def _find_held(self, who, symbol):
        """This trader's position in this ticker — their own key first, then
        the ONE open trade in the name whoever's it is. None when ambiguous:
        two trades in the same ticker is exactly when a guess sells the wrong
        man's contracts."""
        exact = self.open_pos.get(key_of(who, symbol))
        if exact is not None:
            return exact
        ks = [k for k in self.open_pos
              if _key_sym(k) == str(symbol or "").upper()]
        return self.open_pos[ks[0]] if len(ks) == 1 else None

    def resolve_add(self, sig, author_name=""):
        """"added to SPY, new avg is 2.8" — they bought more of what they're
        already in. Following them means a second contract at today's price, so
        this is the one place in the file that spends money on purpose rather
        than because a call came in.

        Four ways it says no: averaging is switched off, you're not in that
        trade, you've already added as many times as you allowed, or it can't
        tell which position they meant.
        """
        if not getattr(sig, "needs_add", False):
            return sig
        who = str(getattr(sig, "caller", "") or author_name or "").lower()

        # The average_in switch, the add ceiling and the allowed-list check
        # are deleted — "follow everything to the tee". The one rule left is
        # the one that isn't a preference: you can only add to a trade you're
        # actually in.
        if not sig.symbol:
            k = self._pick_held(who)
            if k:
                sig.symbol = _key_sym(k)
        if not sig.symbol:
            sig.why = ("they added to a position and didn't name it, and I "
                       "can't tell which one they meant — nothing was sent")
            return sig

        pos = self._find_held(who, sig.symbol)
        if not pos:
            # BOKA/RWGates dialect (9/2): "added $DRAM $57 calls 9/18" is an
            # ENTRY announcement when you're not in it (full contract only;
            # a bare "added to SPY" still refuses — no strike named).
            if (getattr(sig, "strike", None) is not None
                    and getattr(sig, "side", None)
                    and getattr(sig, "expiry", None)):
                sig.action = "OPEN"
                sig.needs_add = False
                sig.qty = 1
                sig.fire = True
                sig.why = ("entry: OPEN %s %s%s %s (their \"added\" is an "
                           "entry — you're not in it)"
                           % (sig.symbol, sig.strike,
                              "C" if str(sig.side).startswith("C") else "P",
                              sig.expiry))
                return sig
            sig.why = ("they added to their %s, but you're not in it — there's "
                       "nothing to average into" % sig.symbol)
            return sig
        adds = int(pos.get("adds", 0))
        # The contract comes from what you're holding, never from the add
        # message — "added to SPY" doesn't say which strike, and buying a
        # different one isn't averaging, it's a second trade.
        sig.side = pos.get("side")
        sig.strike = pos.get("strike")
        sig.expiry = pos.get("expiry")
        sig.qty = 1
        sig.fire = True
        # 2.8 in "new avg is 2.8" is their BLENDED average across both
        # contracts, not what the second one cost. Their first fill was on one
        # side of it and the one they just bought was on the other, so it is
        # not a price anything can be bought at and it must never become the
        # limit on this order. It's kept for the log line and dropped here.
        their_avg = sig.limit
        sig.limit = None
        sig.why = ("averaging into %s — that's your %s add on it%s"
                   % (sig.symbol, "first" if adds == 0 else "next",
                      "" if their_avg is None
                      else ", their average across both is now %.2f" % their_avg))
        return sig

    def remember_loading(self, sig, author_name=""):
        """A LOADING notice never buys anything — that's the room's own rule.
        But it is the only place the contract gets named when their entry comes
        in two messages, so it gets kept here until the price turns up."""
        if getattr(sig, "action", None) != "PREPARE" or not sig.symbol:
            return
        who = str(getattr(sig, "caller", "") or author_name or "").lower()
        self.loaded[who] = {"symbol": sig.symbol, "side": sig.side,
                            "strike": sig.strike, "expiry": sig.expiry,
                            "ts": time.time()}

    def resolve_loaded(self, sig, author_name=""):
        """"Filled 3.95 starters" is an order with the contract missing. It was
        in the "Loading 205 calls Friday expiration on NVDA" the same admin
        posted a few minutes before, so that's where it comes from.

        Same rule as everywhere else in this file: if it can't be worked out for
        certain, nothing is sent and you're told why in a sentence. A price with
        no contract behind it is the single easiest way to buy the wrong thing.
        """
        if sig.symbol or not getattr(sig, "needs_loaded", False):
            return sig
        who = str(getattr(sig, "caller", "") or author_name or "").lower()
        cand = self.loaded.get(who)
        if cand is None and len(self.loaded) == 1:
            # Nobody else has loaded anything, so there's only one call it could
            # possibly be. Still refused below if it's stale or incomplete.
            only_who, only = next(iter(self.loaded.items()))
            if not who or not only_who:
                cand = only
        if not cand:
            sig.why = ("they posted a fill price on its own and I can't find the "
                       "LOADING call that goes with it — nothing was sent")
            return sig
        age = time.time() - cand["ts"]
        if self.loaded_window_s and age > self.loaded_window_s:
            sig.why = ("they posted a fill price on its own, but the last LOADING "
                       "call was %.0f minutes ago — too long ago to assume it's "
                       "the same trade, so nothing was sent" % (age / 60.0))
            return sig
        if not (cand.get("symbol") and cand.get("strike") and cand.get("side")):
            sig.why = ("they posted a fill price on its own, and the LOADING call "
                       "before it didn't name a full contract either — nothing "
                       "was sent")
            return sig
        named = getattr(sig, "named_symbol", None)
        if named and str(named).upper() != str(cand["symbol"]).upper():
            # "In meta 6.10 avg" while their last load was TSLA. They named a
            # ticker; it disagrees with the load. Buying the load here buys the
            # WRONG ticker — the Aug 4 TSLA-for-META bug. Refuse.
            sig.why = ("they said %s but the last LOADING I have for them is %s — "
                       "I won't buy a different ticker than the one they named, so "
                       "nothing was sent" % (str(named).upper(), cand["symbol"]))
            return sig
        if cand.get("used"):
            # A second price on the same loading call is them averaging into the
            # trade they already put you in — "Filled 4.20 more" after "Filled
            # 3.95 starters". Sent down the averaging path, which refuses it
            # outright unless you switched averaging on.
            sig.action, sig.needs_add = "ADD", True
            sig.symbol = cand["symbol"]
            return self.resolve_add(sig, author_name)
        cand["used"] = 1
        sig.symbol, sig.side = cand["symbol"], cand["side"]
        sig.strike, sig.expiry = cand["strike"], cand.get("expiry")
        sig.fire = True
        sig.why = ("entry: %s — they posted the price on its own, and that's the "
                   "contract %s loaded"
                   % (sig.human(), getattr(sig, "caller", "") or author_name
                      or "they"))
        return sig

    def fill_from_position(self, sig, author_name=""):
        """"all out of AMD" never says which contract, and neither does "exited
        and back in" — everyone in the room already knows which one. A broker
        doesn't, so the missing pieces come from what you're actually holding."""
        who = str(getattr(sig, "caller", "") or author_name or "").lower()
        p = self._find_held(who, sig.symbol)
        if not p:
            return sig
        if sig.strike is None:
            sig.strike = p.get("strike")
        if sig.side is None:
            sig.side = p.get("side")
        if sig.expiry is None:
            sig.expiry = p.get("expiry")
        # If you averaged in, you hold more than one contract, and "all out"
        # means all of them. Selling the one the parser assumed would leave you
        # holding the rest without knowing it.
        if sig.action == "CLOSE":
            sig.qty = max(1, int(p.get("qty", 1)))
        return sig

    def record(self, sig, author_name=""):
        """Call this the moment an order actually goes out."""
        now = time.time()
        who = str(getattr(sig, "caller", "") or author_name or "")
        # Anything older about this ticker is history now. Without this, the
        # room getting out of SPY and straight back in ten seconds later would
        # look like a duplicate call and you'd sit out the rest of the move.
        # Buying twice is stopped by the position tracker instead, which is the
        # right tool for it.
        if sig.symbol:
            self._recent = {k: v for k, v in self._recent.items()
                            if k[1] != sig.symbol}
        self._recent[sig.key()] = now
        pk = key_of(who, sig.symbol)
        if sig.action == "OPEN":
            if sig.limit is not None:
                if not hasattr(self, "echoes"):
                    self.echoes = {}
                self.echoes[_echo_key(sig, who)] = now
            # The author is in the KEY now, so a later symbol-less trim from
            # the same admin pins to the position they actually opened — and
            # two admins can be in the same ticker without colliding.
            # "pending" means the order has gone out and nobody has sold to you
            # yet. Entries rest on the bid, so that is the normal state for a
            # while and sometimes the only one it ever reaches. Only the bridge
            # can clear it, because only the bridge sees the fill.
            self.open_pos[pk] = {"side": sig.side, "strike": sig.strike,
                                 "expiry": sig.expiry, "ts": now,
                                 "author": who, "qty": int(sig.qty or 1),
                                 "adds": 0, "pending": True}
            self.last_call[pk] = {"side": sig.side, "strike": sig.strike,
                                  "expiry": sig.expiry,
                                  "limit": getattr(sig, "limit", None), "ts": now}
            if len(self.last_call) > 60:
                old = sorted(self.last_call,
                             key=lambda kk: self.last_call[kk].get("ts", 0))
                for d in old[:len(self.last_call) - 60]:
                    self.last_call.pop(d, None)
        elif sig.action == "ADD":
            # More contracts of the same thing. The count is what an exit
            # sells, and the add count is what stops it happening all day.
            p = self._find_held(who, sig.symbol)
            if p is not None:
                p["qty"] = int(p.get("qty", 1)) + int(sig.qty or 1)
                p["adds"] = int(p.get("adds", 0)) + 1
                p["ts"] = now
                p["pending"] = True     # the extra contracts aren't yours yet
        elif sig.action == "TRIM":
            # Sold some, kept the rest. The bridge's count is the truth; this
            # subtraction just keeps the local picture roughly honest.
            p = self._find_held(who, sig.symbol)
            if p is not None:
                p["qty"] = max(1, int(p.get("qty", 1)) - int(sig.qty or 1))
        elif sig.action == "CLOSE":
            ks = [k for k in self.open_pos if _key_sym(k) == sig.symbol]
            gone = pk if pk in self.open_pos else (ks[0] if len(ks) == 1 else pk)
            held = self.open_pos.pop(gone, None)
            if getattr(sig, "reenter", False):
                # Sold and bought straight back into the same contract. The
                # tracker has to know you're still in it, or the room's next
                # "all out" gets refused for having nothing to sell.
                base = held or {}
                self.open_pos[gone] = {
                    "side": sig.side or base.get("side"),
                    "strike": sig.strike if sig.strike is not None
                              else base.get("strike"),
                    "expiry": sig.expiry or base.get("expiry"), "ts": now,
                    "author": who or base.get("author", ""),
                    # Straight back in on the same size you just sold — as a
                    # bid, so pending until the bridge says it filled.
                    "qty": int(base.get("qty", 1) or 1), "adds": 0,
                    "pending": True}
        # keep the dedupe table from growing all day
        if len(self._recent) > 400:
            cut = now - max(self.dedupe_s, 300)
            self._recent = {k: v for k, v in self._recent.items() if v > cut}
        if sig.action in ("OPEN", "ADD"):
            self._last_fire = now
            self._roll_day()
            self._count += 1

    def clamp_qty(self, wanted, action="OPEN"):
        """Real-money buys are pinned to ONE contract — a sizing safety, not
        a filter, until he raises it on purpose. Sells are never capped down:
        an exit has to sell everything you hold or you're quietly still in."""
        if str(action).upper() in ("CLOSE", "TRIM"):
            return max(1, int(wanted or 1))
        return 1
