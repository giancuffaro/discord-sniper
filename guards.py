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
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
KILL_FILE = "STOP"          # create a file called STOP next to the bot to halt it


class Guards:
    def __init__(self, cfg, here="."):
        g = cfg.get("guards", {})
        self.channels = set(str(c) for c in cfg.get("channel_ids", []))
        self.authors = set(str(a) for a in cfg.get("author_ids", []))
        self.author_names = set(str(a).lower() for a in cfg.get("author_names", []))
        self.max_qty = int(g.get("max_qty", 1))
        self.max_trades_per_day = int(g.get("max_trades_per_day", 10))
        self.cooldown_s = float(g.get("cooldown_seconds", 5))
        self.dedupe_s = float(g.get("dedupe_seconds", 120))
        self.session_only = bool(g.get("regular_hours_only", True))
        self.open_hm = tuple(int(x) for x in g.get("open_time", "09:30").split(":"))
        self.close_hm = tuple(int(x) for x in g.get("close_time", "15:45").split(":"))
        self.max_age_s = float(g.get("max_message_age_seconds", 20))
        self.kill_path = os.path.join(here, KILL_FILE)

        self._last_fire = 0.0
        self._recent = {}       # signal key -> timestamp
        self._day = None
        self._count = 0
        # What the bot believes you're holding. Two admins calling the same
        # trade five minutes apart is the normal case in a signal room, and
        # without this you'd buy it twice.
        self.open_pos = {}      # symbol -> {side, strike, expiry, ts}

    # -- helpers --------------------------------------------------------------
    def _roll_day(self):
        today = datetime.now(ET).date()
        if self._day != today:
            self._day, self._count = today, 0

    def trades_left(self):
        self._roll_day()
        return max(0, self.max_trades_per_day - self._count)

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

        if self.session_only and sig.action == "OPEN":
            t = datetime.now(ET)
            if t.weekday() > 4:
                return False, "it's the weekend — the market is shut"
            mins = t.hour * 60 + t.minute
            o = self.open_hm[0] * 60 + self.open_hm[1]
            c = self.close_hm[0] * 60 + self.close_hm[1]
            if not (o <= mins <= c):
                return False, ("it's %s ET — new trades are only allowed between "
                               "%02d:%02d and %02d:%02d"
                               % (t.strftime("%H:%M"), *self.open_hm, *self.close_hm))

        # dedupe: the same call posted twice in a couple of minutes is one trade
        # What you're holding is checked before anything else, because "you're
        # already in AMD" tells you far more than "that looked like a repeat".
        if sig.action == "OPEN" and self.open_pos.get(sig.symbol):
            return False, ("you're already in %s from their earlier call — "
                           "this one would double you up" % sig.symbol)

        if sig.action == "CLOSE" and sig.symbol not in self.open_pos:
            # This one matters more than it looks. At most brokers a sell with
            # nothing to sell isn't a no-op — it opens a short. Never send it.
            return False, ("you're not in %s, so there's nothing to close — "
                           "the order was not sent" % sig.symbol)

        key = sig.key()
        last = self._recent.get(key)
        if last and (now - last) < self.dedupe_s:
            return False, ("already acted on that exact call %.0fs ago"
                           % (now - last))

        if sig.action == "OPEN":
            if (now - self._last_fire) < self.cooldown_s:
                return False, ("still in the %.0fs cooldown after the last fire"
                               % self.cooldown_s)
            if self._count >= self.max_trades_per_day:
                return False, ("you've hit your limit of %d trades for today"
                               % self.max_trades_per_day)

        return True, "allowed"

    def fill_from_position(self, sig):
        """"all out of AMD" never says which contract, and neither does "exited
        and back in" — everyone in the room already knows which one. A broker
        doesn't, so the missing pieces come from what you're actually holding."""
        p = self.open_pos.get(sig.symbol)
        if not p:
            return sig
        if sig.strike is None:
            sig.strike = p.get("strike")
        if sig.side is None:
            sig.side = p.get("side")
        if sig.expiry is None:
            sig.expiry = p.get("expiry")
        return sig

    def record(self, sig):
        """Call this the moment an order actually goes out."""
        now = time.time()
        # Anything older about this ticker is history now. Without this, the
        # room getting out of SPY and straight back in ten seconds later would
        # look like a duplicate call and you'd sit out the rest of the move.
        # Buying twice is stopped by the position tracker instead, which is the
        # right tool for it.
        if sig.symbol:
            self._recent = {k: v for k, v in self._recent.items()
                            if k[1] != sig.symbol}
        self._recent[sig.key()] = now
        if sig.action == "OPEN":
            self.open_pos[sig.symbol] = {"side": sig.side, "strike": sig.strike,
                                         "expiry": sig.expiry, "ts": now}
        elif sig.action == "CLOSE":
            held = self.open_pos.pop(sig.symbol, None)
            if getattr(sig, "reenter", False):
                # Sold and bought straight back into the same contract. The
                # tracker has to know you're still in it, or the room's next
                # "all out" gets refused for having nothing to sell.
                base = held or {}
                self.open_pos[sig.symbol] = {
                    "side": sig.side or base.get("side"),
                    "strike": sig.strike if sig.strike is not None
                              else base.get("strike"),
                    "expiry": sig.expiry or base.get("expiry"), "ts": now}
        # keep the dedupe table from growing all day
        if len(self._recent) > 400:
            cut = now - max(self.dedupe_s, 300)
            self._recent = {k: v for k, v in self._recent.items() if v > cut}
        if sig.action == "OPEN":
            self._last_fire = now
            self._roll_day()
            self._count += 1

    def clamp_qty(self, wanted):
        return max(1, min(int(wanted or 1), self.max_qty))
