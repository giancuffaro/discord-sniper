"""The quote bus — one batched sweep for every open position, 9/2/26.

THE PROBLEM THIS REPLACES
-------------------------
Today every filled position starts its OWN watchdog thread, and every one of
those threads calls ask_bid() for its own contract on every tick. Six open
positions at a 5-second poll is 6 separate Webull calls every 5 seconds, and
those calls compete with entries, stop placements and the pullback hunter for
the same budget. Turning the poll down to 1 second would have made it SIX
calls a second.

Webull's documented limit is 300 requests per 60 seconds — 5 per second.
The old _pace() spacer slept 150ms between calls, which is 6.67 per second:
ALREADY OVER THE LIMIT. That is where the 8/9 wall of 429s came from, and it
is why polling faster made things worse instead of better.

WHAT THIS DOES INSTEAD
----------------------
1. ONE sweep asks for EVERY open contract in a single call
   (/market-data/options/snapshots/list takes a list of symbols).
   Six positions stop costing six calls and start costing one.
2. A real token bucket sized to the documented limit, with 5% held back.
   Nothing guesses at spacing any more; callers ask for budget and get it.
3. ORDERS OUTRANK QUOTES. A ratchet moving a stop, an entry, a panic exit —
   those take budget ahead of any quote sweep, always. A stop move never
   waits behind a price check again.
4. On a REAL 429 the sweep rate halves for 30 seconds, then walks back up.
   Reads back off. Orders never retry — a retried BUY is a double fill.

WHAT IT COSTS — HONESTLY
------------------------
This is NOT free. Today, 6 positions on a 5-second poll is 1.2 calls/sec.
A 300ms batched sweep is 3.3 calls/sec. That is MORE traffic, not less.

What changes is the shape of the cost:

  * Today  : cost grows with every position you hold. 15 positions at a
             1-second poll would be 15 calls/sec — three times over the limit.
  * Batched: cost is FLAT. One call per sweep whether you hold 2 or 20.

So the win is that freshness stops being something you pay for per position.
Quotes go from 5 seconds stale to ~300ms stale, and holding more positions
no longer makes the watchdog slower or pushes the account into 429s.
"""

import threading
import time

# Webull: 300 requests / 60 seconds. Keep 5% back so a burst of orders never
# pushes the account over and starts the 429 cascade.
LIMIT_REQUESTS = 300
LIMIT_WINDOW = 60.0
SAFETY = 0.95

# How often the sweeper WANTS to run. One batched call per sweep.
# 0.30s = 3.3 calls/sec against a 4.75/sec budget, which leaves ~1.4/sec for
# orders. Tested at 0.25s the bucket ran dry and an entry waited 0.44s behind
# quote sweeps — unacceptable when a fill is racing a room. 0.30s + the
# reserve below keeps order latency under ~50ms.
# CORRECTED 9/2 from Webull's published limits (v3.5.0/OPTIONS-BROKER-
# REFERENCE.md): limits are PER ENDPOINT, and the option snapshot endpoint
# is 60 requests / 60 s = ONE call per second, max 20 symbols each. A 0.30s
# sweep was 200 calls/min against a 60/min door — it would have 429'd
# itself within the first minute. 1.05s keeps a hair of slack.
SWEEP_TARGET = 1.05
SWEEP_FLOOR = 1.00          # never faster than the endpoint's 1/s
SWEEP_CEILING = 5.0         # what a fully backed-off bus falls back to

# Tokens the sweeper will NOT touch. Entries, exits and ratchet stop-moves
# draw from this cushion instantly instead of queueing behind price checks.
ORDER_RESERVE = 40.0

BACKOFF_SECONDS = 30.0      # how long a 429 keeps the rate halved
STALE_AFTER = 6.0           # a quote older than this is not a quote


class Budget:
    """Token bucket over the real documented limit, with a priority lane.

    take(1) blocks until there is room. Orders pass priority=True and are
    served first; quote sweeps yield to them.
    """

    def __init__(self, limit=LIMIT_REQUESTS, window=LIMIT_WINDOW,
                 safety=SAFETY):
        self.capacity = max(1.0, float(limit) * float(safety))
        self.window = float(window)
        self.rate = self.capacity / self.window        # tokens per second
        self._tokens = self.capacity
        self._last = time.time()
        self._lock = threading.Lock()
        self._priority_waiting = 0
        self.rejections = 0                            # real 429s seen

    def _refill(self):
        now = time.time()
        self._tokens = min(self.capacity,
                           self._tokens + (now - self._last) * self.rate)
        self._last = now

    def take(self, n=1, priority=False, timeout=10.0, reserve=0.0):
        """Spend n requests' worth of budget. True if granted.

        reserve is a floor a NON-priority caller will not dip below, so the
        quote sweeper can never drain the bucket that an entry or a ratchet
        stop-move needs a moment later. Priority callers ignore it.
        """
        deadline = time.time() + float(timeout)
        floor = 0.0 if priority else float(reserve)
        if priority:
            with self._lock:
                self._priority_waiting += 1
        try:
            while True:
                with self._lock:
                    self._refill()
                    # A quote sweep stands aside while an order is waiting.
                    clear = priority or self._priority_waiting == 0
                    need = n + floor
                    if clear and self._tokens >= need:
                        self._tokens -= n
                        return True
                    deficit = need - self._tokens if self._tokens < need else 0.0
                    wait = (deficit / self.rate) if deficit > 0 else 0.01
                if time.time() >= deadline:
                    return False
                time.sleep(min(max(wait, 0.005), 0.25))
        finally:
            if priority:
                with self._lock:
                    self._priority_waiting -= 1

    def available(self):
        with self._lock:
            self._refill()
            return self._tokens


class QuoteBus:
    """Every open contract's live bid/ask, refreshed by one batched sweep.

    fetch_many(occ_list) -> {occ: (ask, bid, row)} is supplied by the caller
    (webull_options.ask_bid_many). If the batched shape is unavailable the
    caller's fallback loops one at a time — the bus does not care which, it
    only pays for what it is told the call cost.
    """

    def __init__(self, fetch_many, budget=None, log=None):
        self._fetch_many = fetch_many
        self.budget = budget or Budget()
        self._log = log or (lambda *_a, **_k: None)
        self._quotes = {}                  # occ -> (ask, bid, row, ts)
        self._watch = set()
        self._lock = threading.Lock()
        self._sweep_every = SWEEP_TARGET
        self._backoff_until = 0.0
        self._stop = threading.Event()
        self._thread = None
        self.sweeps = 0
        self.last_sweep_ms = 0.0
        self._tape = None                  # path of option_tape.csv (record_to)

    # ---- option tape (9/2, HANDOFF-OPTION-DATA) -------------------------
    def record_to(self, path):
        """Append every swept quote to a CSV: ts,occ,bid,ask. Webull keeps
        no option tick history, so this is the only record of what our
        contracts printed. One line per contract per sweep (~1/s)."""
        self._tape = path
        try:
            import os
            if not os.path.exists(path):
                with open(path, "a", encoding="utf-8") as f:
                    f.write("ts,occ,bid,ask\n")
        except Exception:                                # noqa: BLE001
            self._tape = None

    def _tape_write(self, rows, now):
        if not self._tape or not rows:
            return
        try:
            with open(self._tape, "a", encoding="utf-8") as f:
                for occ, bid, ask in rows:
                    f.write("%.3f,%s,%s,%s\n" % (now, occ, bid, ask))
        except Exception:                                # noqa: BLE001
            pass

    # ---- what to watch -------------------------------------------------
    def watch(self, occ):
        if not occ:
            return
        with self._lock:
            self._watch.add(str(occ))

    def unwatch(self, occ):
        with self._lock:
            self._watch.discard(str(occ))
            self._quotes.pop(str(occ), None)

    def watching(self):
        with self._lock:
            return sorted(self._watch)

    # ---- reading -------------------------------------------------------
    def get(self, occ, max_age=STALE_AFTER):
        """(ask, bid, row) or (None, None, None) if there is no fresh quote.

        A stale quote is never returned as if it were live — the watchdog
        must not sell off a price from thirty seconds ago.
        """
        with self._lock:
            q = self._quotes.get(str(occ))
        if not q:
            return (None, None, None)
        ask, bid, row, ts = q
        if max_age and (time.time() - ts) > max_age:
            return (None, None, None)
        return (ask, bid, row)

    def age(self, occ):
        with self._lock:
            q = self._quotes.get(str(occ))
        return None if not q else (time.time() - q[3])

    # ---- the sweeper ---------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="quote-bus")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            started = time.time()
            try:
                self._sweep_once()
            except Exception as e:                       # noqa: BLE001
                # A sweep that dies must never take the bus down with it —
                # the resting stops at Webull are still guarding everything.
                self._log("quote-bus sweep error: %s" % str(e)[:120])
            took = time.time() - started
            self.last_sweep_ms = took * 1000.0
            gap = self._sweep_every - took
            if gap > 0:
                self._stop.wait(gap)

    def _sweep_once(self):
        with self._lock:
            occs = sorted(self._watch)
        if not occs:
            # Nothing open. Idle cheaply and give the whole budget back.
            self._stop.wait(0.5)
            return
        if not self.budget.take(1, priority=False, timeout=5.0,
                                reserve=ORDER_RESERVE):
            return                                       # budget starved
        try:
            got = self._fetch_many(occs) or {}
        except Exception as e:                           # noqa: BLE001
            if "429" in str(e) or "TOO_MANY" in str(e).upper():
                self._on_429()
            else:
                self._log("quote sweep failed: %s" % str(e)[:120])
            return
        now = time.time()
        tape_rows = []
        with self._lock:
            for occ, val in got.items():
                try:
                    ask, bid, row = val
                except Exception:                        # noqa: BLE001
                    continue
                self._quotes[str(occ)] = (ask, bid, row, now)
                tape_rows.append((str(occ), bid, ask))
        self.sweeps += 1
        self._tape_write(tape_rows, now)
        self._recover()

    def _on_429(self):
        self.budget.rejections += 1
        self._backoff_until = time.time() + BACKOFF_SECONDS
        self._sweep_every = min(SWEEP_CEILING, self._sweep_every * 2.0)
        self._log("rate limited — quote sweeps slowed to %.2fs for %ds"
                  % (self._sweep_every, int(BACKOFF_SECONDS)))

    def _recover(self):
        if time.time() < self._backoff_until:
            return
        if self._sweep_every > SWEEP_TARGET:
            self._sweep_every = max(SWEEP_TARGET, self._sweep_every * 0.8)

    # ---- for the popup -------------------------------------------------
    def status(self):
        return {
            "watching": len(self._watch),
            "sweep_every_s": round(self._sweep_every, 3),
            "last_sweep_ms": round(self.last_sweep_ms, 1),
            "sweeps": self.sweeps,
            "budget_left": round(self.budget.available(), 1),
            "rate_limited": self.budget.rejections,
        }
