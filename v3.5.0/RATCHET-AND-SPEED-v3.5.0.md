# v3.5.0 — Tiered Ratchet + Fast Quotes + Direction Fix

**Written 9/2/26. Base version 3.4.11. Apply at the PC. Two stages: Stage 1 is small and safe, Stage 2 is the big speed win.**

---

## THE HEADLINE — you were already over the rate limit

Webull documents **300 requests per 60 seconds**. That is **5 calls per second**.

Your `_pace()` in `webull_options.py` sleeps **150ms** between calls. That is **6.67 calls per second**.

You have been running about **33% over Webull's published limit** every time the bot is busy. That is the 8/9 wall of 429s, and it is why the answer to "poll faster" was never just a smaller number — the bot was already asking for more than it was allowed.

So the fix is not "poll faster." It is:

1. Stop overshooting the limit (honest pacing).
2. Ask for **all your positions in one call** instead of one call each.
3. Spend the budget you free up on sweeping **every 300ms instead of every 5 seconds**.

Net result: quotes go from **5 seconds stale to 0.3 seconds stale** — about **16x fresher** — while staying *under* the documented limit instead of over it.

---

## STAGE 1 — Tiered ratchet (small, safe, do this first)

### What changes

One ratchet becomes three, picked off **what you actually paid** for the contract.

| You paid | Ratchet arms at | First lock | Each rung after | Worst giveback |
|---|---|---|---|---|
| **Under $1.00** | +25% | **+10%** | +15% | 15–30% |
| **$1.00 – $1.99** | +15% | **breakeven** | +10% | 10–20% |
| **$2.00 and up** | +10% | **+5%** | +5% | 5–10% |

### Why it is not just "5% everywhere"

You asked for tighter — 10/15/20/25/30. Tighter is right for **expensive** contracts and wrong for **cheap** ones, and here is the reason in one line:

> **A $0.40 contract moves in 1-cent ticks. One tick is 2.5%.**

A 5% ratchet on a 40-cent lotto is **two ticks**. The bid alone flickers that far without the market moving at all — you would get scratched out of every runner by the quote, not by the trade. That is why cheap contracts arm **later** (+25%) but lock **more per rung** (+15%).

Meanwhile a $4.00 contract at 5% is $0.20, which is several ticks of real distance. There, tight is free money — and that tier now locks **+5% profit at the very first rung**, better than the breakeven you get today.

### The old rule vs the new one, side by side

Contract bought at **$2.50**, runs to +30%:

| | Old (10/10) | New ($2.00+ tier) |
|---|---|---|
| +10% | stop → breakeven ($2.50) | stop → **+5%** ($2.61) |
| +20% | stop → +10% ($2.75) | stop → **+15%** ($2.85) |
| +30% | stop → +20% ($3.00) | stop → **+25%** ($3.09) |

You are locking **one full rung more** the whole way up on anything $2 and over.

Contract bought at **$0.50**, runs to +40%:

| | Old (15% arm, 10% steps) | New (under-$1 tier) |
|---|---|---|
| +15% | stop → breakeven ($0.50) ← **scratched by noise** | nothing yet |
| +25% | stop → +10% ($0.55) | stop → **+10%** ($0.55) |
| +40% | stop → +25% ($0.625) | stop → **+25%** ($0.625) |

Same locking, but it **stops handing your lottos back at breakeven** on a quote wiggle.

### Two safety floors that come with it

**1. The tick floor.** A rung must be worth at least **4 ticks**. A 5% rung on a $3.00 contract is $0.15, which is only 3 ticks (tick is a nickel above $3.00) — too tight, so the step automatically widens to 6.7%. This is handled for you; you will just see slightly wider rungs on nickel-tick contracts.

**2. The spread floor — this is the important one.** The new stop must sit at least **one full bid/ask spread** under the live bid. If the spread is $0.20 and the ratchet wants to put the stop $0.08 under the bid, that stop is living *inside the noise* and the quote will hit it. It gets pushed down to a real distance instead.

Neither floor ever moves a stop **down**. They only refuse to raise it somewhere unsafe — the trade keeps its old stop until it earns the room for a better one.

### Files

- **NEW FILE:** `ratchet_tiers.py` — drop it in the `discord-sniper` folder. Nothing else to do to it.

### Edit `positions.py`

**A.** At the top with the other imports, add:

```python
from ratchet_tiers import (ratchet_locked_pct as tier_locked_pct,
                           ratchet_stop_price, ratchet_plan)
```

**B.** Inside `auto_ratchet`, find these lines:

```python
            _arm = self.take_profit_pct if fill >= 1.0                 else max(self.take_profit_pct, 15.0)
            locked = ratchet_locked_pct(gain, self.stop_pct, _arm)
            if locked is None:
                return           # hasn't reached the first rung yet
```

and replace them with:

```python
            # TIERED (9/2/26): the rung plan comes from what he PAID, not
            # from one global pair of percentages. See ratchet_tiers.py.
            locked = tier_locked_pct(gain, fill)
            if locked is None:
                return           # hasn't reached the first rung yet
```

**C.** A little further down, find:

```python
            new_stop = round(fill * (1 + locked / 100.0), 2)
```

and replace it with:

```python
            # Spread floor: a stop inside the bid/ask gets hit by the quote,
            # not by the trade. ratchet_stop_price returns None when the move
            # isn't safe or isn't an improvement — then we spend no API call.
            _ask = p.get("last_ask")
            new_stop = ratchet_stop_price(fill, locked, bid=bid, ask=_ask,
                                          current_stop=p.get("stop"))
            if new_stop is None:
                return
```

**That is all of Stage 1.** Run your tests, push, restart. It is a contained change — if you hate it, the old lines go back.

---

## STAGE 2 — Fast quotes (the real speed win)

### What changes

Right now **every open position runs its own thread making its own quote call.** Six positions on a 5-second poll is six calls every five seconds, and those calls fight your entries, your stop placements and the pullback hunter for the same limited budget.

The new way: **one sweep asks for every open contract in a single call**, 300ms apart.

|  | Today | After |
|---|---|---|
| Quote freshness | 5 seconds | **0.3 seconds** |
| Cost with 6 positions | 1.2 calls/sec | 3.3 calls/sec |
| Cost with 20 positions | 4 calls/sec (**over limit at 1s poll**) | **still 3.3 calls/sec** |
| Order waits behind quotes | yes | **no — orders jump the queue** |

The key thing: cost stops growing with position count. That is what makes going fast possible at all.

### Honest note on cost

This is **not** free — at 6 positions it is *more* total traffic than today, not less. What it buys you is that freshness no longer costs you per position, and holding 15 positions no longer pushes you into 429s.

### Files

- **NEW FILE:** `quote_bus.py` — drop it in.
- **PASTE:** the contents of `_patch_ask_bid_many.py` into `webull_options.py`, right after the existing `ask_bid()` method (same indentation — it is a method on the same class).

### Edit `webull_options.py`

Find in `_pace()`:

```python
        wait = 0.15 - (now - getattr(self, "_last_call", 0.0))
```

Change to:

```python
        # 0.20 = Webull's documented 300 requests / 60 seconds = 5 per second.
        # The old 0.15 was 6.67/sec — over the limit, which is where the 8/9
        # wall of 429s came from.
        wait = 0.20 - (now - getattr(self, "_last_call", 0.0))
```

### Edit `bridge.py`

Where the Webull client is built, attach the shared budget and start the bus:

```python
from quote_bus import Budget, QuoteBus

BUDGET = Budget()                      # 300 req / 60s, 5% held back
WB.budget = BUDGET                     # every Webull call now draws from it
QUOTES = QuoteBus(WB.ask_bid_many, budget=BUDGET, log=print)
QUOTES.start()
BOOK.quotes = QUOTES                   # the book reads prices from here
```

And in `settings.json`, under `execution.webull`:

```json
"fill_poll_seconds": 0.3
```

### Edit `positions.py` — the watchdog

In `_watchdog`, register the contract with the bus and read from it instead of calling Webull directly:

```python
            # was: _ask, bid, _row = wb.ask_bid(occ)
            _bus = getattr(self, "quotes", None)
            if _bus is not None:
                _bus.watch(occ)
                _ask, bid, _row = _bus.get(occ)
                if bid is None:
                    continue        # no FRESH quote is not a reason to sell
            else:
                _ask, bid, _row = wb.ask_bid(occ)
```

Also store the ask so the ratchet's spread floor has something to work with — right next to where `last_bid` is saved:

```python
                        q["last_ask"] = float(_ask) if _ask else None
```

And drop the poll floor so 0.3 is actually honoured. Find:

```python
        self.poll_seconds = max(1.0, float(poll_seconds))
```

Change to:

```python
        self.poll_seconds = max(0.2, float(poll_seconds))
```

Finally, call `self.quotes.unwatch(occ)` wherever a position is closed, so the bus stops paying for dead contracts.

---

## VERIFY AFTER RESTART

1. `bridge.log` shows no `429` / `TOO_MANY_REQUESTS` for a full session.
2. `curl 127.0.0.1:8787/rooms` still answers (bridge is alive).
3. On the first winner over its arm level, the log line reads **"ratchet moved your stop"** with a price matching its tier — a $2+ contract should lock **+5%**, not breakeven.
4. If you see **"batched option quotes not available on this SDK"** in the log, the batch shape was refused and it fell back to one call per contract. Tell me and I will fix the shape — do NOT leave `fill_poll_seconds` at 0.3 in that state.

---

## STAGE 3 — The direction fix (shorts + futures)

### First, the thing I got half right last time

I told you the `dirn != 1` line was what stopped futures ratcheting. That line **is** wrong and it is fixed below — but removing it alone changes nothing, and you should know that before you go looking for a result that will not appear.

**Futures never reach the ratchet in the first place.** Two hard walls, both upstream of it:

1. `arm_stop()` in `positions.py` returns early for `kind == "future"` — it writes the caller's stop onto the record and stops. No resting stop is placed, and no watchdog thread is started.
2. Futures positions have **no OCC symbol and no quote feed**. The watchdog polls `ask_bid(occ)`; with no `occ` there is nothing to poll. The code says so plainly at line ~1798: *"until the futures data subscription exists, no quote feed for a watchdog to poll."*

So the direction fix is **necessary but not sufficient**. It makes the math right for when a short does arrive. Futures ratcheting also needs a futures quote feed — and the good news is that Webull **does** publish a futures snapshot endpoint, so it is buildable the same way the options one was.

### Why futures use points, not percent

A percentage is meaningless on a future. MNQ trades near 24,000 — "10%" is **2,400 points**. That is not a stop, it is a different trade.

Your futures book is already written in points: entries snap to the 25-point grid, the default bracket is 25 risk / 50 reward, MES gets its own 10-point stop. So the futures ratchet uses the number the trade already has — **its own stop width** — as both the arm and the rung:

> **One stop-width of profit locks breakeven. Every further stop-width locks another.**

| | Arms at | Then |
|---|---|---|
| **MNQ / NQ** (25-pt stop) | +25 → breakeven | +50 → +25, +75 → +50 … |
| **MES / ES** (your 10-pt stop) | +10 → breakeven | +20 → +10, +30 → +20 … |
| **Caller posted their own stop** | that distance | same, in their size |

Tested: MNQ long from 24000 → stop 24000 at +25, 24025 at +50, 24050 at +75. MES short from 5025 → stop 5025 at +10, 5015 at +20, 5005 at +30. A caller's 12-point stop makes 12-point rungs automatically — your "theirs first, mine as fallback" rule, unchanged.

### Edit `positions.py` — remove the skip

Find this in `auto_ratchet`:

```python
            # Only long positions ratchet for now — every call site that arms
            # this bracket is a long options buy; a short/futures ratchet
            # would need the mirrored math and isn't part of what he asked for.
            if dirn != 1:
                return
```

Replace with:

```python
            # 9/2/26: shorts ratchet too. A short's stop lives ABOVE the entry
            # and walks DOWN as the trade profits — the exact mirror — and
            # ratchet_stop_price handles both sides. Futures come through the
            # points path below, not this percentage one.
            if p.get("kind") == "future":
                return self._futures_ratchet(key, bid)
```

And pass direction into the stop price (replacing the Stage 1 version of this line):

```python
            new_stop = ratchet_stop_price(fill, locked, bid=bid, ask=_ask,
                                          current_stop=p.get("stop"),
                                          direction=dirn)
```

### Add the futures ratchet method

New method on the same class, next to `auto_ratchet`:

```python
    def _futures_ratchet(self, key, price):
        """Points-based ratchet for futures. See ratchet_tiers.py for why
        percent is meaningless here. Needs a futures quote feed to fire —
        without one, `price` never arrives and this is simply never called."""
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
```

**Note:** this only moves the stop on the *record* for now. Actually resting it at the broker needs the futures stop-order path, which is the same build as the futures quote feed.

---

## THE STREAMING TEST (run this tonight — market closed is fine)

**`TEST_MQTT_OPTIONS.py`** + **`TEST STREAMING.bat`** — double-click the .bat.

This answers the one question that makes all the polling work above obsolete: **does Webull push option prices instead of making you ask?** If yes, there is no 300/minute cap and no 429s, ever.

### Why a closed market does not break it

Nothing trades when the market is shut, so **no prices will arrive — that is expected and it is not a failure.** The test does not judge on prices arriving. It judges on whether Webull **accepts the subscription**, which is a control message it answers at 3am Sunday exactly like noon Tuesday.

```
subscribe ACCEPTED  ->  options ARE carried. Green light.
subscribe REFUSED   ->  options are NOT carried.
no prices arriving  ->  means NOTHING while closed. Ignore it.
```

### The two traps it avoids

**1. A wrong contract looks identical to "not supported."** So it does not guess a strike — it reads SPY's live price, picks the ATM strike on the next Friday, and confirms the contract is real over plain HTTP *before* subscribing to it.

**2. A broken setup looks identical to "not supported."** So it also subscribes to plain SPY stock as a control:

| Option | Stock | Means |
|---|---|---|
| ACCEPTED | ACCEPTED | **Options are carried. Build it.** |
| REFUSED | ACCEPTED | Streaming works, options specifically are not. Stay on batched polling. |
| REFUSED | REFUSED | Your streaming entitlement is the problem — says nothing about options either way. |

I checked the real SDK, so the calls match what is actually installed: `DefaultQuotesClient`, `Category.US_OPTION`, `SubscribeType.QUOTE/SNAPSHOT`, and the verdict hangs off `on_subscribe_success`, which fires only on a 200 from Webull.

**`Category.US_OPTION` exists in Webull's own market-data SDK** — that is a good sign, but it is not proof of entitlement on your keys. That is what the test settles.

If it comes back green, run it once more during market hours to confirm prices actually flow. Acceptance is proven closed; delivery is the one thing a shut market cannot show you.

---

## STILL OPEN

- **Futures quote feed + futures resting stops** — the real unlock for futures ratcheting. Webull publishes a futures snapshot endpoint, so it is buildable.
- If streaming comes back green, Stage 2's polling work becomes a fallback rather than the main path. Worth doing anyway — it is the safety net for when the stream drops.
