# HANDOFF — v3.5.0
### Everything from the 9/2/26 session, in the order to apply it
**Base: 3.4.11.** Written for a morning session at the PC.

---

# READ THIS BEFORE YOU TOUCH ANYTHING

## 1. PUSH BEFORE YOU RESTART THE BRIDGE

`bridge.py` self-updates with `git reset --hard origin/main`. **That wipes any change on disk that hasn't reached GitHub.** It already destroyed a full day of work on 8/30 at 2:26 AM.

**Order, every single time:**

```
1. make the edits
2. run tests
3. SEND CHANGES TO GITHUB.bat        <- BEFORE the restart, not after
4. reload the extension in Chrome
5. RESTART BRIDGE.bat
```

If you restart before pushing, the reset eats your morning. If it happens anyway: `git reflog`, look for the `reset:` line, recover from the commit before it. Don't rebuild by hand.

## 2. DON'T DO ALL OF THIS BEFORE THE OPEN

I know you want everything live tomorrow. Some of it shouldn't be.

The work splits into three risk levels, and **BLOCK C is surgery on the code that watches your open positions.** Doing that in the hour before an open is how you lose a whole trading day. It is also the least urgent of the three, because the thing it fixes (quote speed) is costing you a little edge, while the things in BLOCK A are costing you whole trades.

| | What | Time | Do it |
|---|---|---|---|
| **A** | Chrome tabs, rate-limit fix, logging | ~25 min | **Tomorrow morning, before the open** |
| **B** | Tiered ratchet + direction fix | ~30 min | Tomorrow, ideally watch it on paper first |
| **C** | Quote bus + batched quotes | ~1–2 hrs | **Weekend. Not before an open.** |
| **D** | Two tests that need no code | ~10 min | Tonight (streaming) / any time (trailing) |

## 3. WHAT'S PROVEN AND WHAT ISN'T

You said this revamps the bot 100%. Some of it will. But **none of it is applied yet**, and I'd rather you walk in knowing which is which than find out at 9:31.

**Proven — I read your code and confirmed it:**
- Your `_pace()` runs at 6.67 requests/sec against Webull's documented 5/sec cap. You are over the limit. That's real.
- The ratchet cancels the old stop *before* placing the new one. That naked window exists.
- `autoDiscardable` is never set and `tab.discarded` is never checked. That hole is real.
- The bot uses two typed SDK calls and guesses the rest by method name.
- Futures never reach the ratchet — `arm_stop()` returns early for them.

**Tested here, but on my machine, not against Webull:**
- The tiered ratchet math and the futures points math (I ran the tables).
- The quote bus: 12 positions, 3.4 calls/sec, orders waiting 0ms.

**Not verified — do not build on these until tested:**
- Whether Webull streaming carries options (that's the test in BLOCK D).
- Whether option orders accept trailing-stop fields.
- Whether Chrome is *actually* discarding your tabs. The log will tell you tomorrow.

---

# BLOCK A — do this first (~25 min, safe, pre-market)

Nothing here touches trading logic. All three are contained.

## A1 — The rate-limit fix (2 minutes, do it first)

**`webull_options.py`**, in `_pace()` (~line 584). Find:

```python
        wait = 0.15 - (now - getattr(self, "_last_call", 0.0))
```

Replace with:

```python
        # 0.20 = Webull's documented 300 requests / 60 seconds = 5 per second.
        # The old 0.15 was 6.67/sec — OVER the published limit, which is where
        # the 8/9 wall of 429s came from. Slower here means fewer refusals.
        wait = 0.20 - (now - getattr(self, "_last_call", 0.0))
```

That's the whole change. You have been running about 33% over Webull's cap.

## A2 — Turn on the SDK's real logging (1 minute)

**`webull_options.py`**, right after `api = ApiClient(key, secret, REGION)` (~line 435):

```python
        # Full request/response logging, built into the SDK. This is what
        # answers the ai_reader 404 and the bridge crashes instead of us
        # reading tea leaves in bridge.log.
        try:
            api.set_file_logger("webull_api.log")
        except Exception:                               # noqa: BLE001
            pass
```

## A3 — The Chrome tab fixes (~20 min)

**This is the highest-value item in Block A.** Chrome's Memory Saver discards background tabs, and a discarded Discord tab still shows up in `chrome.tabs.query()` with a normal URL — so `oneTabPerChannel`, the 40-minute silence alarm and everything else believe it's healthy while it reads **nothing**.

### A3.1 — Paste into `content.js`, at the very bottom

```js
/* HEARTBEAT (9/2/26). A dead reader and a quiet room look identical for 40
 * minutes today — the silence alert even says so. But a merely-quiet room
 * still has a living content script in it, and a living script can say so. */
function _readerHealth() {
  const list = document.querySelector('[data-list-id="chat-messages"]');
  const rows = list
    ? list.querySelectorAll('li[id^="chat-messages-"]').length : 0;
  return {
    type: "READER_ALIVE",
    channelId: (location.pathname.match(/\/channels\/\d+\/(\d+)/) || [])[1]
               || null,
    rows: rows,
    listFound: !!list,
    observing: !!observer,          // false = watcher died, reads nothing
    wasDiscarded: !!document.wasDiscarded,
    hidden: document.hidden,
    at: Date.now()
  };
}
function _beat() {
  // "Extension context invalidated" throws synchronously on a reload —
  // same trap as line ~182. Never let a beat kill the reader.
  try { chrome.runtime.sendMessage(_readerHealth()); } catch (e) { }
}
setInterval(_beat, 30000);
_beat();

/* Chrome FREEZES background tabs. A frozen tab's MutationObserver queues
 * nothing, so mutations during the freeze are lost outright. On resume,
 * re-attach and force a full re-read — handle() dedupes via SEEN, so
 * re-reading is free and missing a call is not. */
document.addEventListener("resume", function () {
  try {
    const list = document.querySelector('[data-list-id="chat-messages"]');
    if (list) {
      if (observer) { try { observer.disconnect(); } catch (e) { } }
      observer = new MutationObserver(onMutations);
      observer.observe(list, { childList: true, subtree: true });
      list.querySelectorAll('li[id^="chat-messages-"]').forEach(handle);
    }
  } catch (e) { }
  _beat();
});
```

### A3.2 — Paste into `background.js`, near `oneTabPerChannel()`

```js
/* DISCARD FIX + HEARTBEAT WATCHDOG (9/2/26).
 * A discarded tab still appears in tabs.query() with a normal URL, so every
 * watchdog here believed it was healthy. It has no content script in it. */
const READER_BEAT = {};        // channelId -> last heartbeat ts
const READER_TAB = {};         // channelId -> tabId
const BEAT_DEAD_MS = 95000;    // 3 missed beats. Reload, don't wonder.
const REVIVED_AT = {};         // tabId -> last revive, so we don't loop

chrome.runtime.onMessage.addListener((m, sender) => {
  if (!m) return;
  if (m.type === "READER_ALIVE") {
    if (m.channelId) {
      READER_BEAT[m.channelId] = m.at || Date.now();
      if (sender && sender.tab) READER_TAB[m.channelId] = sender.tab.id;
    }
    if (m.listFound && !m.observing) {
      addLog({ kind: "skipped", author: ROOM_LABELS[m.channelId] || m.channelId,
               text: "",
               why: "⚠ reader is running but its message watcher is detached — "
                    + "reloading that room" });
      const tid = READER_TAB[m.channelId];
      if (tid) { try { chrome.tabs.reload(tid); } catch (e) { } }
    }
  }
});

/* autoDiscardable must be RE-APPLIED, not set once: Chrome resets it when a
 * tab navigates, and Discord navigates constantly. Hence the alarm. */
async function keepRoomsLoaded() {
  let tabs;
  try {
    tabs = await chrome.tabs.query({ url: ["https://discord.com/channels/*",
                                           "https://*.discord.com/channels/*"] });
  } catch (e) { return; }

  const now = Date.now();
  for (const t of tabs) {
    try { await chrome.tabs.update(t.id, { autoDiscardable: false }); }
    catch (e) { /* older Chrome, or the tab just closed */ }

    if (t.discarded) {
      if (now - (REVIVED_AT[t.id] || 0) < 60000) continue;
      REVIVED_AT[t.id] = now;
      const label = (t.url.match(/\/channels\/\d+\/(\d+)/) || [])[1];
      await addLog({ kind: "skipped",
                     author: ROOM_LABELS[label] || label || "room", text: "",
                     why: "⚠ Chrome had DISCARDED this room's tab to save "
                          + "memory — it was reading nothing. Reloaded." });
      try { await chrome.tabs.reload(t.id); } catch (e) { }
    }
  }

  for (const cid of Object.keys(ROOM_LABELS)) {
    const last = READER_BEAT[cid];
    if (!last) continue;
    if (now - last < BEAT_DEAD_MS) continue;
    const tid = READER_TAB[cid];
    if (!tid) continue;
    if (now - (REVIVED_AT[tid] || 0) < 60000) continue;
    REVIVED_AT[tid] = now;
    await addLog({ kind: "skipped", author: ROOM_LABELS[cid] || cid, text: "",
                   why: "⚠ this room's reader stopped answering ("
                        + Math.round((now - last) / 1000) + "s). Reloading it "
                        + "now instead of waiting 40 minutes to notice." });
    try { await chrome.tabs.reload(tid); } catch (e) { }
  }
}
```

### A3.3 — Three one-line edits in `background.js`

**(a)** Find the `watch-build` alarm line (~1339) and add the new call:

```js
  if (a.name === "watch-build") { checkBuild(); syncFills(); oneTabPerChannel(); checkBridgeHealth(); memoryShed(); keepRoomsLoaded(); }
```

**(b)** Inside `oneTabPerChannel()`, in the candidate filter next to the 8/30 "loading tabs are never candidates" rule, add:

```js
      if (t.discarded) continue;      // a discarded tab reads nothing
```

**(c)** `SHED_EVERY_MS` — 2 hours to 6. A reload re-downloads the whole Discord app and blanks that room while it happens; with the heartbeat running, blind rotation is churn.

```js
const SHED_EVERY_MS = 6 * 60 * 60 * 1000;
```

### A3.4 — Bump the manifest version

`extension/manifest.json`: `"version": "3.5.0"`

---

# BLOCK B — the ratchet (~30 min)

## B1 — Drop in `ratchet_tiers.py`

Copy it into the `discord-sniper` folder. Nothing to configure.

**What it does — three tiers off what you PAID:**

| You paid | Arms at | First lock | Each rung |
|---|---|---|---|
| **Under $1.00** | +25% | **+10%** | +15% |
| **$1.00 – $1.99** | +15% | breakeven | +10% |
| **$2.00 and up** | +10% | **+5%** | +5% |

You asked for 10-15-20-25-30. That's right for expensive contracts and wrong for cheap ones: **a $0.40 contract moves in 1-cent ticks, so one tick is 2.5%.** A 5% ratchet there is two ticks — the bid flickers that far with the market standing still, and you'd get scratched out of every runner by the quote.

So cheap contracts arm later but lock more per rung. And your current sub-$1 setting (+15% arm → breakeven) is actively bad: it hands lottos back on noise. On $2+ you get exactly what you wanted — a $2.50 fill at +30% now rests its stop at **$3.09** instead of $3.00, one full rung better the whole way up.

Two floors come with it: a rung must be worth **4+ ticks**, and the stop can never sit **inside the bid/ask spread**.

## B2 — `positions.py` — three edits

**(a)** With the other imports at the top:

```python
from ratchet_tiers import (ratchet_locked_pct as tier_locked_pct,
                           ratchet_stop_price, ratchet_plan)
```

**(b)** In `auto_ratchet`, find:

```python
            _arm = self.take_profit_pct if fill >= 1.0                 else max(self.take_profit_pct, 15.0)
            locked = ratchet_locked_pct(gain, self.stop_pct, _arm)
            if locked is None:
                return           # hasn't reached the first rung yet
```

Replace with:

```python
            # TIERED (9/2/26): the rung plan comes from what he PAID, not from
            # one global pair of percentages. See ratchet_tiers.py.
            locked = tier_locked_pct(gain, fill)
            if locked is None:
                return           # hasn't reached the first rung yet
```

**(c)** Find:

```python
            new_stop = round(fill * (1 + locked / 100.0), 2)
```

Replace with:

```python
            # Spread floor: a stop inside the bid/ask gets hit by the quote,
            # not by the trade. Returns None when the move isn't safe or isn't
            # an improvement — then we spend no API call on it.
            _ask = p.get("last_ask")
            new_stop = ratchet_stop_price(fill, locked, bid=bid, ask=_ask,
                                          current_stop=p.get("stop"),
                                          direction=dirn)
            if new_stop is None:
                return
```

**(d)** Store the ask so the spread floor has something to work with. Next to where `last_bid` is saved in the watchdog:

```python
                        q["last_ask"] = float(_ask) if _ask else None
```

## B3 — The direction fix

**A correction first:** I told you the `dirn != 1` line was what stopped futures ratcheting. That line *is* wrong and it's fixed below — but **removing it alone changes nothing**, and I don't want you hunting for a result that won't appear.

Futures never reach the ratchet at all. `arm_stop()` returns early for `kind == "future"` — no resting stop, no watchdog thread — and futures have no OCC symbol, so there's no quote to poll. Your own code says it at ~line 1798.

So: the math is right now; **actual futures ratcheting still needs a futures quote feed.** Webull does publish a futures snapshot endpoint, so it's buildable — but it's a separate project, not tomorrow.

In `auto_ratchet`, find:

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
            # ratchet_stop_price handles both sides. Futures go through the
            # points path, not this percentage one.
            if p.get("kind") == "future":
                return self._futures_ratchet(key, bid)
```

Then add this method next to `auto_ratchet`:

```python
    def _futures_ratchet(self, key, price):
        """Points-based ratchet for futures — percent is meaningless when MNQ
        trades at 24,000 ("10%" would be 2,400 points). Uses the number the
        trade already has: its own stop width. One stop-width of profit locks
        breakeven, every further one locks another.

        Needs a futures quote feed to fire. Without one `price` never arrives
        and this is simply never called."""
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

MNQ on the house 25-pt stop: +25 locks BE, +50 locks +25, +75 locks +50. MES on your 10-pt stop: +10 locks BE, +20 locks +10. A caller who posts a 12-point stop gets 12-point rungs — "theirs first, mine as fallback", unchanged.

## B4 — Fix the naked stop window

**This is a safety bug, and it's small.** The ratchet currently does cancel-then-place:

```python
if old_oid:
    wb.cancel(old_oid)                    # stop is now GONE
new_oid, placed = wb.place_stop(...)      # if THIS fails, you are naked
```

Between those lines the position has no protection. If the place fails — a 417 clamp refusal, a 429, a dropped connection — you're naked and the log tells you something false:

> *"The old stop is still in place; the watchdog on this PC covers the gap."*

It is **not** still in place. It was cancelled on the line above.

`OrderOperationV2.replace_option(...)` modifies the resting order in place — one call, atomic, no gap, and half the API cost. **Try replace first, fall back to the old path if the SDK refuses**, so a bad replace can never cost you a stop:

```python
        try:
            new_oid = placed = None
            # REPLACE first (9/2/26): modifies the resting stop in place, so
            # there is never a moment with no stop. The old cancel-then-place
            # left a real naked window and lied about it in the log.
            if old_oid:
                try:
                    holder = getattr(wb.trade, "order_v3", None) \
                        or getattr(wb.trade, "order", None)
                    rep = getattr(holder, "replace_option", None)
                    if rep is not None:
                        new_oid, placed = wb.replace_stop(old_oid, sym, side,
                                                          strike, expiry, qty,
                                                          fill,
                                                          stop_price=new_stop)
                except Exception:                       # noqa: BLE001
                    new_oid = placed = None             # fall through
            if placed is None:
                if old_oid:
                    try:
                        wb.cancel(old_oid)
                    except Exception:                   # noqa: BLE001
                        pass
                new_oid, placed = wb.place_stop(sym, side, strike, expiry, qty,
                                                fill, stop_price=new_stop)
```

`replace_stop` needs writing in `webull_options.py` alongside `place_stop` — same order body, sent through `replace_option` with the existing `client_order_id`. **If you'd rather not write it tomorrow, skip B4 entirely** — it's the one item here that needs new plumbing rather than an edit.

## B5 — Run the tests, then push

```
python test_positions.py
node test_parity.js
node test_resolve.js
```

Expect the same 4 pre-existing signal failures and nothing new. Then **SEND CHANGES TO GITHUB.bat**, reload the extension, **RESTART BRIDGE.bat**.

---

# BLOCK C — the speed work (WEEKEND, not before an open)

This rewires the code that watches your open positions. Do it when nothing is live.

## What it fixes

Every open position runs its own thread making its own quote call. Six positions on a 5-second poll is six calls every five seconds, competing with entries and stop placements for the same budget. Turning the poll to 1 second would have made it six calls a *second* — past the cap you're already over.

Batched: **one call covers every position**, sweeping every 300ms.

|  | Today | After |
|---|---|---|
| Quote freshness | 5 seconds | **0.3 seconds** |
| 6 positions | 1.2 calls/sec | 3.3 calls/sec |
| 20 positions | 4/sec, **over limit at 1s poll** | **still 3.3/sec** |
| Orders waiting behind quotes | yes | **no — 0ms in testing** |

Honest: at 6 positions that's *more* traffic, not less. What changes is that cost stops growing with position count — which is the only thing that makes speed possible at all.

## The steps

1. Drop in **`quote_bus.py`**.
2. Paste **`_patch_ask_bid_many.py`** into `webull_options.py`, right after `ask_bid()` (same indentation — it's a method on the same class).
3. In `bridge.py`, where the Webull client is built:

```python
from quote_bus import Budget, QuoteBus

BUDGET = Budget()                      # 300 req / 60s, 5% held back
WB.budget = BUDGET                     # every Webull call draws from it
QUOTES = QuoteBus(WB.ask_bid_many, budget=BUDGET, log=print)
QUOTES.start()
BOOK.quotes = QUOTES
```

4. In `positions.py` `_watchdog`, read from the bus:

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

5. Drop the poll floor:

```python
        self.poll_seconds = max(0.2, float(poll_seconds))
```

6. `settings.json` → `execution.webull.fill_poll_seconds: 0.3`
7. Call `self.quotes.unwatch(occ)` wherever a position closes.

**If the log says "batched option quotes not available on this SDK"** — the batch shape was refused and it fell back to one call per contract. Tell me, and **do not leave `fill_poll_seconds` at 0.3 in that state.**

---

# BLOCK D — two tests, no code (do these first, they're free)

## D1 — Does Webull streaming carry options? (run tonight)

Double-click **`TEST STREAMING.bat`**.

**The market being closed is fine.** No prices will arrive and that is not a failure — the test judges on whether Webull **accepts the subscription**, which it answers at 3am Sunday exactly like noon Tuesday.

```
subscribe ACCEPTED  ->  options ARE carried. Green light.
subscribe REFUSED   ->  options are NOT carried.
no prices arriving  ->  means nothing while closed. Ignore it.
```

It resolves a real contract over HTTP first (a made-up strike would look identical to "not supported") and subscribes to plain SPY as a control (a broken setup would too).

**If this comes back green, it's bigger than all of Block C** — no rate limit, no 429s ever, prices pushed the instant they change. Re-run it during market hours to confirm delivery.

## D2 — Do options accept trailing stops? (5 min, one paper contract)

`PlaceOrderRequest` has `set_trailing_type()` and `set_trailing_stop_step()`. If **options** accept them, the ratchet could live at the broker — trailing with your PC off, the bridge closed, the power out.

I could not confirm options support: those setters are on the *stock* order path. The options path takes a free-form dict, so the fields may pass through or may be **silently ignored**, which is the dangerous outcome.

Send one paper contract with the fields set, then **look in the Webull app** and confirm the resting order really is a trailing stop. Don't trust the API's 200.

---

# WHAT NOT TO DO TOMORROW

- **Don't do Block C before the open.** It's the position watchdog.
- **Don't restart the bridge before pushing.** See rule 1.
- **Don't build on D1 or D2 until they come back green.**
- **Don't promote any room from paper to live** in the same session you change the ratchet. One variable at a time or you won't know what did what.

---

# VERIFY, END OF DAY TOMORROW

1. `bridge.log` — **zero** `429` / `TOO_MANY_REQUESTS` for the session. (A1 alone should do this.)
2. Extension log — any `⚠ Chrome had DISCARDED` lines? **If yes, that was rooms going dark and you never knew.** That single line justifies the whole Chrome block.
3. Any `⚠ reader stopped answering` lines? Same story, caught in 90 seconds instead of 40 minutes.
4. First winner past its arm level: the log should read **"ratchet moved your stop"** at its tier — a $2+ contract locks **+5%**, not breakeven.
5. `webull_api.log` exists and has real request/response bodies in it.

---

# STILL OPEN AFTER ALL THIS

- **Push order fills** (`webull-python-sdk-trade-events-core`). Webull will *tell* you the instant an order fills instead of you polling and guessing. This is the fix for the phantom META +$158, the AMD logged "failed" that filled +$146, the post-cancel poll, and the P&L fiction — all one bug wearing different clothes. Biggest reliability win left. Own branch, paper first.
- **`cancel_option` vs `cancel_order`.** The name-hunt calls whichever matches first. Calling the *stock* cancel on an *option* order produces exactly your 8/12 symptom — ORDER_NOT_FOUND all day, stops that never die, every sell blocked. The order-id fix helped; worth confirming which endpoint actually gets hit.
- **~700 lines of method-name guessing** (~26% of `webull_options.py`) replaceable by typed SDK calls. Retire endpoint by endpoint, fallback kept.
- **Futures quote feed + futures resting stops** — the real unlock for B3.
- **Follow announcement channels into Sniper HQ.** Each followable room collapses from a whole Discord tab into one line in a channel you already watch. Native Discord feature, and your ZTRADEZ relay-unwrap code already handles that exact message shape. Best structural fix for the 4–10GB of tabs.
- `preview_option`, `get_trade_calendar`, contract validation before ordering.

---

## FILES IN THIS DROP

| File | Goes where |
|---|---|
| `ratchet_tiers.py` | drop into `discord-sniper/` |
| `quote_bus.py` | drop into `discord-sniper/` (Block C) |
| `TEST_MQTT_OPTIONS.py` + `TEST STREAMING.bat` | drop in, double-click the .bat |
| `_patch_ask_bid_many.py` | paste into `webull_options.py` (Block C) |
| `_patch_chrome_tabs.js` | the Block A3 pastes, with fuller comments |
| `SDK-AUDIT.md` | background reading, not needed to apply |
| `CHROME-TABS.md` | background reading, not needed to apply |

**This doc is self-contained.** Every edit you need tomorrow is written out above — the other files are the code to drop in plus the reasoning behind it.
