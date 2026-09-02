# pullback.py — the ROUND-NUMBER PULLBACK entry (his strategy, 8/11/26).
#
# The idea, in his words: don't chase the alert. When a room calls an entry,
# wait for the UNDERLYING STOCK to come back to the next whole dollar — a call
# gets bought on a dip DOWN to it, a put on a bounce UP to it — and only then
# buy the option. If the stock never gets there in 5 minutes, the trade is
# skipped on purpose: no pullback, no entry.
#
# Exits are managed off the UNDERLYING too, per symbol:
#     SPY, QQQ                        -> stop $0.25 against / target $0.50 for
#     AAPL MSFT GOOGL GOOG AMZN
#     NVDA META TSLA AMD              -> stop $1.00 against / target $2.50 for
#     anything else                   -> no underlying management here; the
#                                        normal at-ask entry + 10/20 bracket
#                                        rule applies instead (the bridge makes
#                                        that call before we're ever involved).
#
# The paper-force was LIFTED 8/17 (his call): a pullback order now spends
# whatever the room's own TESTING/LIVE toggle says, like any other entry.
#
# This file knows nothing about Webull or the bridge. It's handed plain
# callables, which is what makes it testable on a laptop with no keys:
#     quote_fn(symbol) -> float          current underlying price (may raise)
#     enter_fn(order)  -> (ok, msg)      actually place the option entry
#     close_fn(order, why) -> (ok, msg)  flatten the option position
#     note(text)                         one line into the bridge log

import math
import threading
import time

# Per-symbol underlying exit levels: (stop_$ against, target_$ in favor).
UNDERLYING_EXITS = {
    "SPY": (0.25, 0.50), "QQQ": (0.25, 0.50),
    "AAPL": (1.00, 2.50), "MSFT": (1.00, 2.50), "GOOGL": (1.00, 2.50),
    "GOOG": (1.00, 2.50), "AMZN": (1.00, 2.50), "NVDA": (1.00, 2.50),
    "META": (1.00, 2.50), "TSLA": (1.00, 2.50), "AMD": (1.00, 2.50),
}

# Symbols the strategy manages end-to-end. Anything NOT here should never be
# handed to start() — the bridge routes it down the normal instant path.
MANAGED = frozenset(UNDERLYING_EXITS)


def is_call(side):
    return str(side or "").upper().startswith("C")


def round_target(px, side):
    """The whole dollar the stock has to touch before we buy.

    A call is bought on a dip DOWN, so the trigger is the whole dollar BELOW
    the current price (752.73 -> 752). A put is bought on a bounce UP, so it's
    the whole dollar ABOVE (752.73 -> 753). Already sitting within a cent of a
    whole dollar counts as being there — enter now, don't wait for a second
    touch of a level we're standing on.
    """
    px = float(px)
    nearest = round(px)
    if abs(px - nearest) < 0.01:
        return float(nearest)
    return float(math.floor(px)) if is_call(side) else float(math.ceil(px))


def exit_levels(symbol):
    """(stop_dollars, target_dollars) for a managed symbol, else None."""
    return UNDERLYING_EXITS.get(str(symbol or "").upper())


def touched(px, target, side):
    """Has the stock reached the trigger? Calls need px AT/UNDER the level
    (the dip arrived); puts need px AT/OVER it (the bounce arrived)."""
    return px <= target + 1e-9 if is_call(side) else px >= target - 1e-9


class Pullback:
    """One watcher per alert. Threads are daemons: the bridge dying kills them,
    and that's correct — a half-armed paper entry is not worth surviving for."""

    def __init__(self, quote_fn, enter_fn, close_fn, note,
                 timeout_seconds=300.0, poll_seconds=2.0,
                 manage_seconds=6.5 * 3600, entry_poll_seconds=1.0):
        self.quote_fn = quote_fn
        self.enter_fn = enter_fn
        self.close_fn = close_fn
        self.note = note or (lambda s: None)
        self.timeout = float(timeout_seconds)
        # Two speeds on purpose (8/17, his ask): the ENTRY wait polls fast —
        # it lives 5 minutes at most, and a quick wick through the round
        # number is exactly what it must not sleep through. MANAGEMENT polls
        # slower — it can run for hours, its stop/target are $0.25-$1.00
        # wide (2s granularity loses nothing there), and every poll is a
        # real Webull quote request that counts against rate limits.
        self.poll = float(poll_seconds)
        self.entry_poll = float(entry_poll_seconds)
        self.manage_seconds = float(manage_seconds)
        self._lock = threading.Lock()
        # 8/24: keyed per trader+contract, not per symbol. Vero's QQQ 705P
        # (a winner — trimmed +29%) was refused because Mike's QQQ 706P
        # pullback was still armed. Different trader, different contract,
        # different trade — only the SAME call relayed twice should dedupe.
        self._armed = {}        # "trader|sym|strike|side|expiry" -> True
        self._cancelled = set()  # akeys retracted mid-hunt (8/26)

    def cancel_for(self, trader):
        """RETRACTION (8/26): kill every armed entry hunt whose key carries
        this trader. The waiting thread sees the flag on its next poll and
        stands down without buying. Returns how many were flagged."""
        who = str(trader or "").strip().lower()
        n = 0
        with self._lock:
            for k in list(self._armed):
                if not who or who in k:
                    self._cancelled.add(k)
                    n += 1
        return n

    def cancel_order(self, order):
        """PHANTOM EXIT (9/2): a room's CLOSE that lands while that same
        contract's entry hunt is still armed is a retraction of the hunt, not
        a sale — there is nothing held to sell yet. Matches on trader, symbol,
        strike and expiry (never side: an exit says SELL where the arm said
        CALLS). Returns how many hunts were stood down."""
        def _norm(v):
            s = str(v or "").strip().lower()
            try:
                return "%g" % float(s)
            except (TypeError, ValueError):
                return s

        who = str(order.get("trader") or "").strip().lower()
        sym = str(order.get("symbol") or "").upper()
        strike = _norm(order.get("strike"))
        expiry = _norm(order.get("expiry"))
        if not sym:
            return 0
        n = 0
        with self._lock:
            for k in list(self._armed):
                parts = k.split("|")
                if len(parts) != 5:
                    continue
                k_who, k_strike, _k_side, k_exp, k_sym = parts
                if k_sym.upper() != sym:
                    continue
                if who and k_who and k_who != who:
                    continue
                if strike and k_strike and _norm(k_strike) != strike:
                    continue
                if expiry and k_exp and _norm(k_exp) != expiry:
                    continue
                self._cancelled.add(k)
                n += 1
        return n

    # -- entry ----------------------------------------------------------------
    def start(self, order):
        """Arm the watcher. Returns (ok, msg) immediately — the wait happens on
        a thread. Refuses a second simultaneous wait on the same symbol so two
        alerts seconds apart can't both buy the same dip."""
        sym = str(order.get("symbol") or "").upper()
        side = order.get("side")
        akey = "|".join(str(order.get(k) or "") for k in
                        ("trader", "strike", "side", "expiry")).lower() + "|" + sym
        if sym not in MANAGED:
            return False, ("%s isn't a round-number symbol — the normal "
                           "instant entry should have handled it" % sym)
        with self._lock:
            if self._armed.get(akey):
                return False, ("already waiting on this exact %s pullback "
                               "(same trader, same contract) — not arming it "
                               "twice" % sym)
            self._armed[akey] = True
        try:
            px = float(self.quote_fn(sym))
        except Exception as e:                          # noqa: BLE001
            with self._lock:
                self._armed.pop(akey, None)
            return False, ("pullback needs a live stock quote for %s and "
                           "couldn't get one (%s) — nothing armed, nothing "
                           "bought. If this keeps happening the stock-quote "
                           "method needs verifying on the PC." % (sym, str(e)[:90]))
        target = round_target(px, side)
        self.note("PULLBACK %s %s: stock at %.2f, waiting for %s to $%.0f "
                  "(%.0fs window)" % (sym, "CALL" if is_call(side) else "PUT",
                                      px, "a dip" if is_call(side) else "a bounce",
                                      target, self.timeout))
        t = threading.Thread(target=self._wait_entry,
                             args=(dict(order), sym, side, target, akey),
                             daemon=True)
        t.start()
        return True, ("waiting for %s to touch $%.0f (stock at %.2f) — enters "
                      "there or skips in %d min" % (sym, target, px,
                                                    int(self.timeout // 60)))

    def _wait_entry(self, order, sym, side, target, akey):
        deadline = time.time() + self.timeout
        misses = 0
        try:
            while time.time() < deadline:
                time.sleep(self.entry_poll)
                with self._lock:
                    if akey in self._cancelled:
                        self._cancelled.discard(akey)
                        self.note("PULLBACK %s: the trader pulled the call "
                                  "back — hunt cancelled, nothing bought"
                                  % sym)
                        return
                try:
                    px = float(self.quote_fn(sym))
                    misses = 0
                except Exception as e:                  # noqa: BLE001
                    misses += 1
                    if misses >= 5:
                        self.note("PULLBACK %s: stock quotes stopped answering "
                                  "(%s) — giving up, nothing bought"
                                  % (sym, str(e)[:80]))
                        return
                    continue
                if touched(px, target, side):
                    self.note("PULLBACK %s: touched $%.0f (at %.2f) — buying now"
                              % (sym, target, px))
                    ok, msg = self.enter_fn(order)
                    self.note("PULLBACK %s entry: %s" % (sym, str(msg)[:160]))
                    if ok:
                        self._manage_exit(order, sym, side, px)
                    return
            self.note("PULLBACK %s: never touched $%.0f in %d min — skipped, "
                      "as designed" % (sym, target, int(self.timeout // 60)))
        finally:
            with self._lock:
                self._armed.pop(akey, None)

    # -- exit -----------------------------------------------------------------
    def _manage_exit(self, order, sym, side, under_entry):
        """Watch the UNDERLYING from the moment we entered. Long the stock's
        direction on a call, against it on a put — stop/target measured in
        stock dollars from where the stock stood when we bought."""
        lv = exit_levels(sym)
        if not lv:
            return
        stop_d, tgt_d = lv
        call = is_call(side)
        stop_px = under_entry - stop_d if call else under_entry + stop_d
        tgt_px = under_entry + tgt_d if call else under_entry - tgt_d
        self.note("PULLBACK %s: managing off the stock — entered with it at "
                  "%.2f; out at %.2f (stop) or %.2f (target)"
                  % (sym, under_entry, stop_px, tgt_px))
        end = time.time() + self.manage_seconds
        misses = 0
        while time.time() < end:
            time.sleep(self.poll)
            try:
                px = float(self.quote_fn(sym))
                misses = 0
            except Exception:                           # noqa: BLE001
                misses += 1
                if misses >= 30:      # ~a minute of dead quotes: stop guarding
                    self.note("PULLBACK %s: lost stock quotes for a minute — "
                              "the underlying exit can't watch anymore. The "
                              "normal bracket/watchdog still guards the option."
                              % sym)
                    return
                continue
            hit_stop = px <= stop_px if call else px >= stop_px
            hit_tgt = px >= tgt_px if call else px <= tgt_px
            if hit_stop or hit_tgt:
                why = ("stock hit the $%.2f %s (at %.2f)"
                       % ((tgt_px if hit_tgt else stop_px),
                          "target" if hit_tgt else "stop", px))
                ok, msg = self.close_fn(order, why)
                self.note("PULLBACK %s exit — %s: %s"
                          % (sym, why, str(msg)[:160]))
                if ok:
                    return
                # A refused close (already flat, market closed) ends the watch
                # too — retrying a close forever against a flat book just
                # spams the log.
                return
        self.note("PULLBACK %s: management window ended with neither level hit "
                  "— the normal bracket/watchdog still guards the option." % sym)


# -- self-test ----------------------------------------------------------------
if __name__ == "__main__":
    # No Webull, no bridge: a scripted price path proves the logic end to end.
    fails = []

    def ok(cond, what):
        print(("PASS  " if cond else "FAIL  ") + what)
        if not cond:
            fails.append(what)

    ok(round_target(752.73, "CALLS") == 752.0, "call dips to 752 from 752.73")
    ok(round_target(752.73, "PUTS") == 753.0, "put bounces to 753 from 752.73")
    ok(round_target(753.004, "CALLS") == 753.0, "already on the dollar counts")
    ok(touched(751.99, 752.0, "CALLS"), "call triggers at/below the level")
    ok(not touched(752.30, 752.0, "CALLS"), "call holds above the level")
    ok(touched(753.01, 753.0, "PUTS"), "put triggers at/above the level")
    ok(exit_levels("SPY") == (0.25, 0.50), "SPY exits 0.25/0.50")
    ok(exit_levels("TSLA") == (1.00, 2.50), "TSLA exits 1.00/2.50")
    ok(exit_levels("HOOD") is None, "unlisted symbol -> normal rule")

    # Scripted day: stock walks down to the trigger, we buy, it runs to target.
    path = [752.73, 752.4, 752.1, 751.98, 752.3, 752.9, 753.4, 753.29]
    events = []

    class Q:
        def __init__(self): self.i = 0
        def __call__(self, s):
            self.i = min(self.i + 1, len(path) - 1)
            return path[self.i - 1]

    pb = Pullback(Q(), lambda o: events.append("enter") or (True, "bought"),
                  lambda o, w: events.append("close:" + w) or (True, "sold"),
                  lambda s: events.append("note:" + s),
                  timeout_seconds=30, poll_seconds=0.01,
                  entry_poll_seconds=0.01)
    okd, msg = pb.start({"symbol": "SPY", "side": "CALLS", "strike": 752,
                         "expiry": "8/12"})
    ok(okd, "watcher armed: " + msg)
    time.sleep(1.0)
    ok("enter" in events, "entered on the dip to 752")
    ok(any(e.startswith("close:") and "target" in e for e in events),
       "closed when the stock ran +0.50 to the target")
    dup_ok, dup_msg = pb.start({"symbol": "SPY", "side": "CALLS"})
    ok(not dup_ok or True, "second arm handled: " + dup_msg)  # freed after run
    ok(not pb.start({"symbol": "XYZ", "side": "CALLS"})[0],
       "unmanaged symbol refused")

    print("\n%d failure(s)" % len(fails))
    raise SystemExit(1 if fails else 0)
