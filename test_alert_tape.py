"""test_alert_tape.py — every alerted contract gets a real price record, and
data collection never gets in front of money. 9/11/26.

WHY THIS FILE EXISTS
--------------------
In six weeks the rooms called 326 contracts. The bot bought 37. The other 289
were refused — 136 of them purely because the buying power was too small — and
every one of them was thrown away the instant it was refused. Webull keeps no
option tick history, so "would that call have worked?" was permanently
unanswerable with real prices.

alert_tape.py records them. The danger in doing that is obvious: hundreds of
extra contracts against a door of 60 option-snapshot calls a minute, on the
same connection that has to place an entry inside a second. So most of what
this file proves is about restraint, not about recording.

WHAT THIS PROVES
  - Every alert is registered once, expired contracts never are, and each
    registration leaves a row naming the room, the caller and their price.
  - ONE tick is at most ONE call of at most 20 symbols — never a per-contract
    fallback, which is the shape that blows the door.
  - The arithmetic holds: fast bus (~57 calls/min) + this lane (2/min) stays
    under the 60/min option-snapshot limit.
  - A budget drained to the reserve STOPS this lane and still serves an order
    instantly. Real money is never behind data collection.
  - A 429 stands this lane down for minutes, not seconds.
  - If batched quotes are not working, the lane refuses to run at all.
  - alert_tape.csv carries ts,occ,bid,ask,und and option_tape.csv is untouched.

Run:  python3 test_alert_tape.py
"""
import csv
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import alert_tape                                       # noqa: E402
import quote_bus                                        # noqa: E402

FAILS = []


def ok(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("  FAIL  " + msg)


def _occ(sym, strike, cp, days):
    """Through occ.build, never hand-rolled — test_architecture enforces that
    there is exactly one OCC builder in this repo, and a test fixture that
    quietly grew a second one is how the two drift apart."""
    from occ import build
    ymd = time.strftime("%y%m%d", time.localtime(time.time() + days * 86400))
    return build(sym, ymd, cp, strike)


def _future_occ(sym="SPY", strike=767, cp="C", days=7):
    return _occ(sym, strike, cp, days)


def _past_occ(sym="SPY", strike=700, cp="C", days=7):
    return _occ(sym, strike, cp, -days)


def _rec(fetch, **kw):
    r = alert_tape.AlertRecorder(fetch, kw.pop("budget", quote_bus.Budget()),
                                 **kw)
    tape = tempfile.mktemp(suffix=".csv")
    meta = tempfile.mktemp(suffix=".csv")
    r.record_to(tape, meta)
    return r, tape, meta


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
def test_every_alert_is_registered_once():
    r, tape, meta = _rec(lambda occs: {})
    occ = _future_occ()
    order = {"symbol": "SPY", "side": "CALLS", "strike": 767, "expiry": "2026-09-18",
             "room": "Elite Options", "trader": "Brett", "limit": 1.22,
             "coid": "c1", "alert_at": 1000.0, "seen_at": 1000.4}
    ok(r.register(occ, order) is True, "a fresh alert registers")
    ok(r.register(occ, order) is False, "the same alert does not register twice")
    ok(r.status()["tracking"] == 1,
       "one contract tracked, not two (got %d)" % r.status()["tracking"])

    rows = _rows(meta)
    ok(len(rows) == 1, "one alert row per alert (got %d)" % len(rows))
    if rows:
        m = rows[0]
        ok(m["room"] == "Elite Options", "the alert row keeps the ROOM — it was "
                                         "blank on all 289 refused alerts")
        ok(m["caller"] == "Brett", "the alert row keeps the CALLER")
        ok(m["their_price"] == "1.22", "the alert row keeps the price they called")
        ok(m["alert_at"] == "1000.0" and m["seen_at"] == "1000.4",
           "the latency stamps ride along, so a refused alert can be timed too")
        ok(m["occ"] == occ, "the alert row names the contract")
    print("Every alert is logged once, with its room, its caller, their price "
          "and the latency stamps — filled or refused.")


def test_expired_is_never_tracked():
    r, tape, meta = _rec(lambda occs: {})
    ok(r.register(_past_occ(), {"symbol": "SPY"}) is False,
       "a contract that already expired is never taped")
    ok(r.status()["tracking"] == 0, "and it is not tracked")

    # one that expires between registering and the next sweep is dropped
    r2, _t2, _m2 = _rec(lambda occs: {})
    r2._seen.add("OLD"); r2._occs.append(_past_occ())
    r2._prune_locked()
    ok(r2.status()["tracking"] == 0, "an expired contract is pruned off the "
                                     "rotation instead of being asked for forever")
    print("Expired contracts are never asked for — a dead contract has no quote "
          "and asking for one is a wasted call.")


def test_one_tick_is_one_small_call():
    calls = []

    def fetch(occs):
        calls.append(list(occs))
        return {o: (1.05, 1.00, {}) for o in occs}

    r, tape, meta = _rec(fetch, healthy=lambda: True, is_open=lambda: True)
    for i in range(120):
        r.register(_future_occ(strike=700 + i), {"symbol": "SPY"})
    ok(r.status()["tracking"] == 120, "120 alerted contracts are tracked")

    r._tick()                       # first tick proves the batched shape
    ok(len(calls) == 1, "one tick, one call (got %d)" % len(calls))
    ok(len(calls[0]) == 1, "the FIRST call asks for ONE contract — until the "
                           "batched shape has answered, a 20-symbol call could "
                           "secretly be 20 calls (got %d)" % len(calls[0]))
    r._tick()
    ok(len(calls) == 2, "second tick, second call")
    ok(len(calls[1]) == alert_tape.BATCH,
       "once batching is proven it asks for the full 20 (got %d)" % len(calls[1]))
    for c in calls:
        ok(len(c) <= 20, "no call ever asks for more than Webull's 20-symbol "
                         "maximum (got %d)" % len(c))
    print("One tick is one batched call of at most 20 symbols, and it will not "
          "ask for 20 until 20 is known to cost one request.")


def test_the_rate_arithmetic():
    # The fast bus for OPEN POSITIONS: 60/1.05 = 57.1 calls a minute.
    fast = 60.0 / quote_bus.SWEEP_TARGET
    slow_busy = 60.0 / alert_tape.BUSY_EVERY
    slow_idle = 60.0 / alert_tape.IDLE_EVERY
    ok(fast + slow_busy < 60.0,
       "fast bus %.1f/min + alert lane %.1f/min = %.1f must stay under the "
       "option-snapshot door of 60/min" % (fast, slow_busy, fast + slow_busy))
    ok(slow_idle < 60.0,
       "with no open positions the fast bus spends nothing, so the alert "
       "lane's %.0f/min is the whole cost" % slow_idle)
    ok(alert_tape.BUSY_EVERY > alert_tape.IDLE_EVERY,
       "the lane is SLOWER while positions are open, not faster")

    r, tape, meta = _rec(lambda occs: {}, quotes=None)
    ok(r._interval() == alert_tape.IDLE_EVERY,
       "no fast bus at all counts as idle")

    class _BusyBus:
        def watching(self):
            return ["SPY260918C00767000"]

        def get(self, occ, **kw):
            return (None, None, None)

    r2, _t, _m = _rec(lambda occs: {}, quotes=_BusyBus())
    ok(r2._interval() == alert_tape.BUSY_EVERY,
       "one open position and the alert lane drops to the slow cadence")
    print("Cadence: %.0fs between calls while positions are open (%.0f/min on "
          "top of the fast bus's %.0f/min, door is 60), %.0fs when the bus is "
          "idle." % (alert_tape.BUSY_EVERY, slow_busy, fast,
                     alert_tape.IDLE_EVERY))


def test_orders_always_win():
    calls = []
    b = quote_bus.Budget()

    def fetch(occs):
        calls.append(list(occs))
        return {}

    r, tape, meta = _rec(fetch, budget=b, healthy=lambda: True,
                         is_open=lambda: True,
                         order_reserve=quote_bus.ORDER_RESERVE)
    r.register(_future_occ(), {"symbol": "SPY"})

    # Drain the bucket down to a little above the order reserve.
    b._tokens = quote_bus.ORDER_RESERVE + 5.0
    r._tick()
    ok(not calls, "with the budget down near the reserve the alert lane does "
                  "NOT spend (it made %d call(s))" % len(calls))

    t0 = time.time()
    got = b.take(1, priority=True, timeout=1.0)
    ok(got and (time.time() - t0) < 0.05,
       "and an ORDER still gets its token instantly (%.3fs)" % (time.time() - t0))

    b._tokens = b.capacity
    r._tick()
    ok(len(calls) == 1, "with a full bucket the alert lane sweeps normally")
    print("The alert lane keeps a cushion ABOVE the order reserve: it stops "
          "spending long before an entry or a stop-move could ever queue.")


def test_429_stands_down_for_minutes():
    def fetch(occs):
        raise RuntimeError("429 TOO_MANY_REQUESTS")

    r, tape, meta = _rec(fetch, healthy=lambda: True, is_open=lambda: True)
    r.register(_future_occ(), {"symbol": "SPY"})
    r._tick()
    left = r.status()["cooling_s"]
    ok(left > quote_bus.BACKOFF_SECONDS,
       "a 429 stands the DATA lane down far longer (%ds) than the fast bus's "
       "%ds — the lane guarding money yields last" % (left, quote_bus.BACKOFF_SECONDS))
    calls = []
    r._fetch_many = lambda occs: calls.append(occs)
    r._tick()
    ok(not calls, "and it really does stop asking while it is cooling off")
    print("A 429 stands the alert lane down for %d minutes; the fast bus only "
          "halves for %ds." % (alert_tape.COOLDOWN_429 / 60,
                               quote_bus.BACKOFF_SECONDS))


def test_no_batch_means_no_lane():
    calls = []
    r, tape, meta = _rec(lambda occs: calls.append(occs),
                         healthy=lambda: False, is_open=lambda: True)
    r.register(_future_occ(), {"symbol": "SPY"})
    r._tick()
    ok(not calls, "with batching broken the lane makes no calls at all")
    ok(r.status()["off"], "and it says why: %s" % (r.status()["off"] or "(nothing)"))
    print("If batched quotes stop working the lane turns itself OFF and says "
          "so — a per-contract fallback is 20 calls where it budgeted for 1.")


def test_closed_market_costs_nothing():
    calls = []
    r, tape, meta = _rec(lambda occs: calls.append(occs) or {},
                         healthy=lambda: True, is_open=lambda: False)
    r.register(_future_occ(), {"symbol": "SPY"})
    r._tick()
    ok(not calls, "the market is closed: no calls, no budget spent")
    print("Closed market, nothing spent.")


def test_the_file_shape():
    r, tape, meta = _rec(lambda occs: {o: (1.05, 1.00, {}) for o in occs},
                         healthy=lambda: True, is_open=lambda: True,
                         und_price=lambda s: 767.42)
    occ = _future_occ()
    r.register(occ, {"symbol": "SPY"})
    r._tick()
    rows = _rows(tape)
    ok(len(rows) == 1, "the sweep wrote a row (got %d)" % len(rows))
    if rows:
        t = rows[0]
        ok(list(t.keys()) == ["ts", "occ", "bid", "ask", "und"],
           "alert_tape.csv is option_tape.csv's shape plus the underlying "
           "(got %s)" % list(t.keys()))
        ok(t["occ"] == occ and t["bid"] == "1.0" and t["ask"] == "1.05",
           "with the REAL bid and ask, not a model of them")
        ok(t["und"] == "767.42", "and the underlying at that moment, so "
                                 "direction can be told from theta later")
    ok(alert_tape.expiry_ymd("SPY260902C00767000") == "260902",
       "the expiry is read off the RIGHT end of the OCC — roots contain "
       "digits and are not a fixed width")
    ok(alert_tape._underlying_of("SPY260902C00767000") == "SPY",
       "and so is the underlying")
    print("alert_tape.csv: ts,occ,bid,ask,und — real prices, with the stock "
          "beside them.")


def test_option_tape_is_not_disturbed():
    src = open(os.path.join(HERE, "quote_bus.py"), encoding="utf-8").read()
    ok("alert_tape" not in src,
       "quote_bus.py does not know this module exists — the fast lane that "
       "guards open positions is untouched by it")
    ok(alert_tape.TAPE_HEADER.startswith("ts,occ,bid,ask"),
       "and the new tape starts with option_tape.csv's own columns, so every "
       "reader of one can read the other")
    print("option_tape.csv and the fast lane that writes it are untouched.")


def test_a_refused_alert_reaches_master_alerts():
    """The whole point, end to end: an alert that was REFUSED still ends up
    with a room, a caller, a real bid/ask, greeks and a read latency on its
    master_alerts.csv row \u2014 all five were blank on all 289 refused rows,
    because trades.log (their only record) carries none of them."""
    import build_alerts as ba

    r, tape, meta = _rec(lambda occs: {o: (1.30, 1.20, {}) for o in occs},
                         healthy=lambda: True, is_open=lambda: True,
                         und_price=lambda s: 767.42)
    occ = _future_occ(strike=767.5)
    order = {"symbol": "SPY", "side": "CALLS", "strike": 767.5,
             "expiry": "2026-09-18", "room": "Elite Options",
             "trader": "Brett", "limit": 1.22, "coid": "c9",
             "alert_at": 2000.000, "seen_at": 2000.350}
    r.register(occ, order)
    r._tick()                                   # the first REAL quote lands

    today = time.strftime("%Y-%m-%d")
    row = {c: "" for c in ba.COLUMNS}
    row.update({"date": today, "time": "10:31:02", "symbol": "SPY",
                "side": "CALLS", "strike": "767.5",
                "outcome": "BUYING POWER too small",
                "source": "trades.log"})

    old_meta = ba.META
    ba.META = meta
    try:
        touched = ba._apply_meta([row])
    finally:
        ba.META = old_meta

    ok(touched == 1, "the refused alert's row was filled in")
    ok(row["room"] == "Elite Options", "it has a ROOM now (was blank on 170 "
                                       "of 326 rows)")
    ok(row["caller"] == "Brett", "it has a CALLER now (was blank on 237)")
    ok(row["bid"] == "1.2" and row["ask"] == "1.3",
       "and the REAL bid/ask the contract actually printed, not a model "
       "(got %r/%r)" % (row["bid"], row["ask"]))
    ok(row["their_price"] == "1.22", "beside the price the caller claimed \u2014 "
                                     "which is the whole comparison")
    ok(row["read_ms"] == 350, "and how long the reader took to see it (%r)"
                              % row["read_ms"])
    ok(row["spread_pct"] not in ("", None),
       "spread_pct comes free once bid and ask are real")
    ok(row["outcome"] == "BUYING POWER too small",
       "and none of this changed WHAT HAPPENED to the alert")

    # nothing is ever overwritten
    row2 = dict(row, room="Somewhere Else", bid="9.99")
    ba.META = meta
    try:
        ba._apply_meta([row2])
    finally:
        ba.META = old_meta
    ok(row2["room"] == "Somewhere Else" and row2["bid"] == "9.99",
       "a column that already had an answer is never overwritten")
    print("A refused alert now carries its room, its caller, a real bid/ask, "
          "and the reader latency \u2014 all of which were blank on every one of "
          "the 289 refusals.")


if __name__ == "__main__":
    test_every_alert_is_registered_once()
    test_expired_is_never_tracked()
    test_one_tick_is_one_small_call()
    test_the_rate_arithmetic()
    test_orders_always_win()
    test_429_stands_down_for_minutes()
    test_no_batch_means_no_lane()
    test_closed_market_costs_nothing()
    test_the_file_shape()
    test_option_tape_is_not_disturbed()
    test_a_refused_alert_reaches_master_alerts()
    print()
    if FAILS:
        print("FAILED %d check(s):" % len(FAILS))
        for f in FAILS:
            print("  - " + f)
        sys.exit(1)
    print("ALERT TAPE OK — every alerted contract gets real prices, and "
          "nothing about it can get in front of an order.")
