"""loadtest.py — can it handle 10 trades arriving at the same instant?

    python loadtest.py            10 simultaneous
    python loadtest.py 22         match your record day (Aug 11)

G's question, 9/7: "10 simultaneously... could it handle it?"

NOTHING REAL HAPPENS HERE. No bridge, no Webull, no orders, no money. It
drives `positions.Book` — the real position engine, the real ratchet, the
real watchdog threads — against the same fake broker the test suite uses.
It deliberately does NOT post to the live bridge on 8787: futures are armed
right now, and a load test that can place an order is not a test.

WHAT IT ACTUALLY MEASURES
  * do all N entries get accepted, filled and stopped, with none lost
  * how many threads that costs, and whether any DIE (deadman is armed)
  * how long the engine takes to react when all N move at once
  * whether the ratchet lands on the right rung for every one of them
    independently, or whether they interfere with each other

WHAT IT CANNOT TELL YOU
  * real Webull latency or throttling. The fake broker answers instantly, so
    this measures OUR engine, not the round trip. The quote budget is the
    real-world limit and it is documented in quote_bus.py: batched at 20
    contracts per call, so 10 costs exactly what 2 costs.
  * real fills, real spreads, real slippage.
"""
import sys
import threading
import time

import deadman
import positions

QUIET = lambda *a, **k: None                              # noqa: E731


class FakeWB:
    """Same shape as the test suite's broker. Answers instantly and records
    everything, so nothing here can touch a real account."""

    def __init__(self, bid=3.00, ask=3.00):
        self.bid, self.ask = bid, ask
        self.calls, self.limits, self.qtys = [], {}, {}
        self.next_id = 1000
        self._lock = threading.Lock()

    def ask_bid(self, occ):
        return self.ask, self.bid, {}

    def order_status(self, oid):
        return (positions.FILLED, self.qtys.get(str(oid), 1),
                self.limits.get(str(oid), self.ask))

    def cancel(self, oid):
        with self._lock:
            self.calls.append(("cancel", oid))
        return True

    def place_stop(self, symbol, side, strike, expiry, qty, fill_price,
                   stop_price=None):
        with self._lock:
            self.next_id += 1
            oid = str(self.next_id)
            stop = (max(0.01, round(float(stop_price), 2))
                    if stop_price is not None
                    else max(0.01, round(float(fill_price) * 0.90, 2)))
            self.calls.append(("stop", symbol, qty, stop))
        return oid, stop

    def sell(self, symbol, side, strike, expiry, qty, ref_price=None,
             urgent=False):
        with self._lock:
            self.next_id += 1
            oid = str(self.next_id)
            self.limits[oid] = self.bid
            self.qtys[oid] = qty
            self.calls.append(("sell", symbol, qty))
        return {"what": "SELL", "limit": self.bid, "order_id": oid}


TICKERS = ["SPY", "QQQ", "NVDA", "AAPL", "META", "AMD", "TSLA", "AMZN",
           "GOOGL", "NFLX", "MSFT", "IWM", "SMCI", "COIN", "MU", "AVGO",
           "CRM", "UBER", "PLTR", "SOFI", "RIVN", "INTC", "BAC", "F"]


def main(n=10):
    deadman.arm(note=QUIET)
    wb = FakeWB()
    book = positions.Book(wb, QUIET, fill_seconds=1.0, poll_seconds=0.2)

    base_threads = len(threading.enumerate())
    print("=" * 66)
    print("  LOAD TEST — %d trades arriving AT THE SAME INSTANT" % n)
    print("  (fake broker, no bridge, no orders, no money)")
    print("=" * 66)
    print("  threads before: %d\n" % base_threads)

    keys, t0 = [], time.time()

    def fire(i):
        sym = TICKERS[i % len(TICKERS)]
        trader = "Caller%d" % (i % 5)
        order = {"symbol": sym, "side": "CALLS", "strike": 100 + i,
                 "expiry": "9/11", "limit": 2.00, "trader": trader}
        oid = str(500 + i)
        wb.limits[oid] = 2.00
        wb.qtys[oid] = 1
        tk = {"order_id": oid, "occ": "X", "limit": 2.00, "bid": 2.00,
              "ask": 2.06, "qty": 1}
        book.entry_sent(order, tk)
        keys.append(positions.key_of(trader, sym))

    # ALL AT ONCE — every entry handed to the book from its own thread in the
    # same instant, which is the case he asked about and the one most likely
    # to expose a lock held too long.
    threads = [threading.Thread(target=fire, args=(i,), name="fire-%d" % i)
               for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("  all %d handed over in %.0f ms" % (n, (time.time() - t0) * 1000))

    # Wait for every one to reach a fill.
    end, filled = time.time() + 20, 0
    while time.time() < end:
        filled = sum(1 for k in keys if book.state_of(k) == positions.FILLED)
        if filled >= n:
            break
        time.sleep(0.05)
    t_fill = time.time() - t0
    peak = len(threading.enumerate())
    print("  all %d FILLED in %.2f s" % (filled, t_fill))
    print("  threads at peak: %d  (+%d for %d trades)"
          % (peak, peak - base_threads, n))

    # Now move the market on ALL of them at once and see the ratchet react.
    t1 = time.time()
    wb.bid = wb.ask = 2.40                     # +20% on every position
    end = time.time() + 25
    moved = 0
    while time.time() < end:
        moved = sum(1 for k in keys
                    if (book.info(k) or {}).get("stop") not in (None, 0))
        if moved >= filled:
            break
        time.sleep(0.05)
    print("  +20%% on all %d -> %d stops armed in %.2f s"
          % (n, moved, time.time() - t1))

    stops = sorted({round(float((book.info(k) or {}).get("stop") or 0), 2)
                    for k in keys})
    print("  distinct stop prices: %s" % stops)
    print("     (all equal = every trade ratcheted the same and independently)")

    d = deadman.report()
    print("\n  THREADS THAT DIED: %s" % (list(d["dead"]) or "none"))
    print("  stalled heartbeats: %s" % (d["stalled"] or "none"))

    lost = [k for k in keys if book.state_of(k) is None]
    print("  positions lost/never created: %d" % len(lost))

    ok = (filled == n and moved == n and not d["dead"] and not lost
          and len(stops) == 1)
    print("\n  %s" % ("PASS — %d simultaneous trades handled, none lost, "
                      "none died, all ratcheted alike." % n if ok
                      else "PROBLEM — read the numbers above."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 10))
