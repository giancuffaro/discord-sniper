"""alert_tape.py — a real price record for EVERY alerted contract, 9/11/26.

THE PROBLEM
-----------
In six weeks the rooms called 326 contracts and the bot bought 37 of them.
The single biggest reason it stood down was BUYING POWER too small (136 of
them). Every one of those 289 refusals was thrown away the moment it was
refused, so the question "would that call have worked?" can only be answered
with a MODEL of what the contract probably did — never with what it actually
printed. Webull keeps no option tick history, so a price not recorded on the
day is gone for good.

This records them. Every parsed alert — filled, refused for money, paper,
pullback that never triggered, refused for any reason at all — gets its OCC
symbol registered here, and this keeps writing that contract's real bid/ask
to `alert_tape.csv` until the contract expires.

WHAT IT MUST NEVER DO
---------------------
Delay real money. Webull's door is 300 requests / 60 seconds overall, and the
option-snapshot endpoint specifically is 60 requests / 60 seconds, 20 symbols
per call. The quote bus's fast sweep for OPEN POSITIONS already runs at 1.05s
(≈57 of those 60 calls a minute) and orders draw from a reserve nothing else
may touch. So this lane:

  * is SLOW — one batched call every 30 seconds while the fast bus has open
    positions to watch, which is 2 calls a minute on top of the fast bus's 57.
    57 + 2 = 59 against a door of 60.
  * speeds up ONLY when the fast bus is idle — no open positions means the
    fast bus is spending nothing, so this may take one call every 5 seconds
    (12 a minute, still a fifth of the door).
  * never dips into the order reserve, and keeps an EXTRA cushion above it,
    so an entry or a ratchet stop-move is never behind a data sweep.
  * backs off for five full minutes on a 429 instead of thirty seconds. Data
    collection is the first thing that should get out of the way.
  * refuses to run at all if the batched shape is not working. Falling back
    to one call per contract would be 20 calls where this budgets for 1, and
    THAT is how the door gets blown.

WHAT IT WRITES
--------------
alert_tape.csv   ts,occ,bid,ask,und     — the same shape as option_tape.csv
                 plus the underlying's price at that sweep, so direction can
                 later be told apart from theta decay. option_tape.csv is not
                 touched and open positions keep taping there exactly as now.

alert_meta.csv   one row per alert at the moment it is logged: room, caller,
                 the caller's price, the latency stamps, and delta/iv if the
                 greeks feed has them. build_alerts.py joins this in, which
                 is what finally puts a room, a caller and greeks on a
                 REFUSED alert — they were blank on all 289 of them because
                 the only record of a refusal is a line of trades.log.
"""

import csv
import os
import threading
import time

# One batched snapshot call per tick. Never more — see the module docstring.
BATCH = 20

# Seconds between calls while the fast bus HAS open positions to watch.
# 60 / 30 = 2 calls a minute on top of the fast bus's ~57. Door is 60.
BUSY_EVERY = 30.0
# Seconds between calls while the fast bus is idle (it spends nothing then).
IDLE_EVERY = 5.0

# On a 429 this lane goes away for five minutes. The fast bus halves for 30
# seconds; a data lane should yield much harder than a lane guarding money.
COOLDOWN_429 = 300.0

# Budget floor this lane will not dip below, ON TOP OF the quote bus's own
# ORDER_RESERVE. Orders draw from the reserve; this keeps a second cushion
# above it so even a burst of quote sweeps plus this can't crowd an entry.
EXTRA_RESERVE = 60.0

# A hard ceiling on how many contracts are tracked at once, so a runaway room
# cannot turn this into a full-chain subscription. Oldest registered goes
# first. 400 contracts at 20 per call is 20 calls = one full refresh every
# 10 minutes in the busy cadence, which is plenty for scoring a call.
MAX_TRACKED = 400

# How many alerted contracts may be handed to the GREEKS feed. That feed is a
# websocket, not a request — it costs nothing against Webull's door — but it
# is still a live subscription per contract and it writes a line of
# greeks_tape.csv per tick. Sixty is well past a busy morning's alerts and
# keeps the file and the socket the size they are today. Price recording is
# NOT capped by this; only the greeks are.
GREEKS_MAX = 60

TAPE_HEADER = "ts,occ,bid,ask,und\n"
META_HEADER = ("ts,stage,coid,date,time,room,caller,symbol,side,strike,"
               "expiry,occ,their_price,alert_at,seen_at,bid,ask,und,"
               "delta,iv\n")


def expiry_ymd(occ):
    """The YYMMDD out of an OCC symbol, or None.

    OCC is ROOT + YYMMDD + C/P + 8-digit strike, so the date is always the
    six characters ending fifteen from the right. Read positionally rather
    than by regex because the root is variable length and may contain digits
    (BRK.B, 1COV) — counting from the RIGHT is the only safe end.
    """
    s = str(occ or "")
    if len(s) < 15:
        return None
    body = s[-15:-9]
    return body if body.isdigit() else None


def _today_ymd(now=None):
    return time.strftime("%y%m%d", time.localtime(now or time.time()))


def _csv(v):
    """One CSV cell that can never break the row."""
    if v is None:
        return ""
    s = str(v)
    if any(c in s for c in (",", '"', "\n", "\r")):
        return '"%s"' % s.replace('"', '""')
    return s


class AlertRecorder:
    """The slow lane: real bid/ask for alerted contracts we did not buy.

    fetch_many(occ_list) -> {occ: (ask, bid, row)} — the same callable the
    quote bus uses (webull_options.ask_bid_many). It is only ever handed
    BATCH symbols or fewer, so one tick is one HTTP call.
    """

    def __init__(self, fetch_many, budget, quotes=None, und_price=None,
                 greeks=None, healthy=None, is_open=None, log=None,
                 order_reserve=0.0):
        self._fetch_many = fetch_many
        self.budget = budget
        self._quotes = quotes            # the FAST bus — read only, for its
                                         # cached quotes and its idle state
        self._und_price = und_price      # StockStream.price: free, pushed
        self._greeks = greeks            # dxlink.GreeksBus, or None
        self._healthy = healthy          # () -> False means stand down
        self._is_open = is_open          # () -> is the option market open
        self._log = log or (lambda *_a, **_k: None)
        self._order_reserve = float(order_reserve or 0.0)

        self._occs = []                  # rotation order, oldest first
        self._seen = set()
        self._lock = threading.Lock()
        self._cursor = 0
        self._tape = None
        self._meta = None
        self._hdr = {}                   # path -> its header line
        self._stop = threading.Event()
        self._thread = None
        self._cool_until = 0.0
        self._batch = 1                  # proven-shape ramp: see _sweep_once
        self._quoted = set()             # OCCs whose stage=quote row is written
        self._greeked = set()            # OCCs handed to the greeks websocket
        self._called = {}                # occ -> what the CALL said, kept so
                                         # the later `quote` row joins to the
                                         # same alert on the same key
        self.sweeps = 0
        self.rows = 0
        self.registered = 0
        self.refused_full = 0
        self.off = ""                    # why this lane is not running

    # ---- files ---------------------------------------------------------
    def record_to(self, tape_path, meta_path=None):
        self._tape = self._ensure(tape_path, TAPE_HEADER)
        if meta_path:
            self._meta = self._ensure(meta_path, META_HEADER)

    def restore_today(self):
        """Restore today's tracked contracts after a bridge/code restart."""
        if not self._meta or not os.path.exists(self._meta):
            return 0
        today = time.strftime("%Y-%m-%d", time.localtime())
        restored = 0
        try:
            with open(self._meta, encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    contract = str(row.get("occ") or "").strip().upper()
                    if row.get("date") != today or not contract:
                        continue
                    with self._lock:
                        if contract in self._seen or len(self._occs) >= MAX_TRACKED:
                            continue
                        self._seen.add(contract)
                        self._occs.append(contract)
                        restored += 1
                    self._called[contract] = {
                        "symbol": row.get("symbol"), "side": row.get("side"),
                        "strike": row.get("strike"), "expiry": row.get("expiry"),
                        "coid": row.get("coid"), "room": row.get("room"),
                        "trader": row.get("caller"),
                    }
                    try:
                        if self._greeks is not None and len(self._greeked) < GREEKS_MAX:
                            self._greeked.add(contract)
                            self._greeks.watch(contract)
                    except Exception:                       # noqa: BLE001
                        pass
        except (OSError, ValueError):
            return restored
        return restored

    def _ensure(self, path, header):
        try:
            self._hdr[path] = header
            if not os.path.exists(path):
                with open(path, "a", encoding="utf-8") as f:
                    f.write(header)
            return path
        except Exception:                               # noqa: BLE001
            return None

    def _append(self, path, line):
        if not path:
            return
        try:
            # THE HEADER COMES BACK IF THE FILE WENT AWAY (9/11). record_to
            # writes the header once at startup, so a tape that is moved,
            # rotated or backed up mid-session would be recreated by the
            # next append as a file of bare numbers with no column names —
            # readable by nothing, and not obviously broken until someone
            # tries to use a day of it. Cheap to check, so check.
            head = "" if os.path.exists(path) else self._hdr.get(path, "")
            with open(path, "a", encoding="utf-8") as f:
                f.write(head + line)
        except Exception:                               # noqa: BLE001
            pass

    # ---- registering an alert ------------------------------------------
    def register(self, occ, order=None):
        """Track this contract, and log the alert's own row. Idempotent.

        Called on EVERY parsed alert, before anything knows whether it will
        fill. Never raises: a recorder fault must not change what the bridge
        does with an order.
        """
        try:
            occ = str(occ or "").strip().upper()
            if not occ:
                return False
            ymd = expiry_ymd(occ)
            if ymd and ymd < _today_ymd():
                return False                            # already expired
            fresh = False
            with self._lock:
                if occ not in self._seen:
                    self._prune_locked()
                    if len(self._occs) >= MAX_TRACKED:
                        self.refused_full += 1
                        if self.refused_full == 1:
                            self._log("alert tape is full at %d contracts — "
                                      "new alerts are not being taped until "
                                      "some expire" % MAX_TRACKED)
                        return False
                    self._seen.add(occ)
                    self._occs.append(occ)
                    self.registered += 1
                    fresh = True
            # Start the underlying streaming (MQTT push — costs no request,
            # and StockStream subscribes on the first ask).
            try:
                if self._und_price is not None and order:
                    self._und_price(str(order.get("symbol") or "").upper())
            except Exception:                           # noqa: BLE001
                pass
            # Greeks, if the feed is up: a websocket subscription, not a
            # request. Gives delta/iv on refused alerts, which is exactly
            # what master_alerts.csv has never had.
            try:
                if self._greeks is not None and len(self._greeked) < GREEKS_MAX:
                    self._greeked.add(occ)
                    self._greeks.watch(occ)
            except Exception:                           # noqa: BLE001
                pass
            # One metadata row per alert, even when the contract is already
            # tracked. Re-entries need their own timestamp and caller price.
            o = order or {}
            self._called[occ] = {
                "symbol": str(o.get("symbol") or "").upper(),
                "side": o.get("side"), "strike": o.get("strike"),
                "expiry": o.get("expiry"), "coid": o.get("coid"),
                "room": o.get("room") or o.get("room_label"),
                "trader": o.get("trader") or o.get("who")}
            self._write_meta("alert", occ, order)
            return fresh
        except Exception:                               # noqa: BLE001
            return False

    def _prune_locked(self):
        """Drop contracts that have expired. Lock held by caller."""
        today = _today_ymd()
        keep = []
        for o in self._occs:
            ymd = expiry_ymd(o)
            if ymd and ymd < today:
                self._seen.discard(o)
                self._quoted.discard(o)
                self._called.pop(o, None)
                # F21 (9/11 audit): an expired contract used to keep its
                # greeks websocket slot forever — _greeked only ever grew,
                # so GREEKS_MAX filled up with dead contracts and every
                # alert after that ran with no delta/iv, silently, with
                # nothing in the log to say why. Release the slot AND
                # actually unsubscribe, the same moment everything else
                # about this contract is dropped.
                if o in self._greeked:
                    self._greeked.discard(o)
                    if self._greeks is not None:
                        try:
                            self._greeks.unwatch(o)
                        except Exception:                   # noqa: BLE001
                            pass
                continue
            keep.append(o)
        self._occs = keep
        if self._cursor >= len(self._occs):
            self._cursor = 0

    # ---- the alert's own row -------------------------------------------
    def _free_quote(self, occ):
        """bid/ask from the FAST bus's cache only — never a new request."""
        try:
            if self._quotes is None:
                return (None, None)
            ask, bid, _row = self._quotes.get(occ)
            return (bid, ask)
        except Exception:                               # noqa: BLE001
            return (None, None)

    def _free_greeks(self, occ):
        try:
            if self._greeks is None:
                return (None, None)
            g = self._greeks.get(occ) or {}
            iv = g.get("volatility", g.get("iv"))
            return (g.get("delta"), iv)
        except Exception:                               # noqa: BLE001
            return (None, None)

    def _free_und(self, symbol):
        try:
            if self._und_price is None or not symbol:
                return None
            return self._und_price(str(symbol).upper())
        except Exception:                               # noqa: BLE001
            return None

    def _write_meta(self, stage, occ, order=None, bid=None, ask=None,
                    und=None, delta=None, iv=None):
        if not self._meta:
            return
        o = order or {}
        now = time.time()
        if stage == "alert":
            bid, ask = self._free_quote(occ)
            delta, iv = self._free_greeks(occ)
            und = self._free_und(o.get("symbol"))
        lt = time.localtime(now)
        self._append(self._meta, ",".join(_csv(x) for x in (
            round(now, 3), stage, o.get("coid"),
            time.strftime("%Y-%m-%d", lt), time.strftime("%H:%M:%S", lt),
            o.get("room") or o.get("room_label"),
            o.get("trader") or o.get("who"),
            str(o.get("symbol") or "").upper(), o.get("side"),
            o.get("strike"), o.get("expiry"), occ,
            o.get("limit") if o.get("limit") is not None else o.get("their_price"),
            o.get("alert_at"), o.get("seen_at"),
            bid, ask, und, delta, iv)) + "\n")

    # ---- the slow sweeper ----------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="alert-tape")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _fast_bus_idle(self):
        try:
            return not (self._quotes and self._quotes.watching())
        except Exception:                               # noqa: BLE001
            return False

    def _interval(self):
        return IDLE_EVERY if self._fast_bus_idle() else BUSY_EVERY

    def _run(self):
        while not self._stop.is_set():
            wait = self._interval()
            try:
                wait = self._tick()
            except Exception as e:                      # noqa: BLE001
                self._log("alert tape sweep error: %s" % str(e)[:120])
            self._stop.wait(max(0.5, wait))

    def _tick(self):
        """One batched call at most. Returns how long to wait next."""
        if self.off:
            return 60.0
        now = time.time()
        if now < self._cool_until:
            return min(30.0, self._cool_until - now)
        # A lane that cannot batch would cost 20 calls where it budgets for
        # 1. It does not get to run at all.
        if self._healthy is not None and not self._healthy():
            self.off = ("batched option quotes are not working on this SDK — "
                        "alert taping is OFF rather than spend 20 calls where "
                        "it budgeted for 1")
            self._log(self.off)
            return 60.0
        if self._is_open is not None:
            try:
                if not self._is_open():
                    return 60.0                          # closed: spend nothing
            except Exception:                            # noqa: BLE001
                pass
        with self._lock:
            self._prune_locked()
            n = len(self._occs)
            if not n:
                return 5.0
            size = min(self._batch, BATCH, n)
            if self._cursor >= n:
                self._cursor = 0
            batch = self._occs[self._cursor:self._cursor + size]
            self._cursor += size
        # Non-priority, and it keeps a cushion ABOVE the order reserve so a
        # stop-move never queues behind a data sweep.
        if not self.budget.take(1, priority=False, timeout=3.0,
                                reserve=self._order_reserve + EXTRA_RESERVE):
            return self._interval()
        try:
            got = self._fetch_many(batch) or {}
        except Exception as e:                          # noqa: BLE001
            if "429" in str(e) or "TOO_MANY" in str(e).upper():
                self._cool_until = time.time() + COOLDOWN_429
                self._log("alert tape rate limited — standing down for %d "
                          "minutes so orders and open positions keep the door"
                          % int(COOLDOWN_429 / 60))
            else:
                self._log("alert tape sweep failed: %s" % str(e)[:120])
            return self._interval()
        self.sweeps += 1
        if got and self._batch < BATCH:
            # The batched shape answered. Only now is a full 20-symbol call
            # known to cost one request instead of twenty.
            self._batch = BATCH
        rows = []
        for occ, val in got.items():
            try:
                ask, bid, _row = val
            except Exception:                           # noqa: BLE001
                continue
            occ = str(occ)
            und = self._free_und(_underlying_of(occ))
            rows.append("%.3f,%s,%s,%s,%s\n" % (
                time.time(), occ,
                "" if bid is None else bid,
                "" if ask is None else ask,
                "" if und is None else und))
            if occ not in self._quoted:
                self._quoted.add(occ)
                d, iv = self._free_greeks(occ)
                # The call's OWN strike/side/expiry, not a guess from the
                # symbol — build_alerts joins on those, so a quote row that
                # dropped them would file real prices under a row nobody
                # could match back to the alert.
                self._write_meta("quote", occ,
                                 self._called.get(occ)
                                 or {"symbol": _underlying_of(occ)},
                                 bid=bid, ask=ask, und=und, delta=d, iv=iv)
        if rows:
            self.rows += len(rows)
            self._append(self._tape, "".join(rows))
        return self._interval()

    # ---- for the popup --------------------------------------------------
    def status(self):
        with self._lock:
            n = len(self._occs)
        return {
            "tracking": n,
            "registered": self.registered,
            "sweeps": self.sweeps,
            "rows": self.rows,
            "every_s": self._interval(),
            "batch": self._batch,
            "cooling_s": max(0, round(self._cool_until - time.time())),
            "off": self.off,
        }


def _underlying_of(occ):
    """SPY260902C00767000 -> SPY. The root is everything before the date."""
    s = str(occ or "")
    if len(s) < 15:
        return ""
    return s[:-15]
