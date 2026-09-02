# SDK Audit — what the bot could be using and isn't

**9/2/26. Against discord-sniper 3.4.11.** I downloaded all five Webull SDK packages and read every public method, then diffed that against what the bot actually calls.

---

## THE ONE-LINE SUMMARY

The bot uses **two** typed SDK calls: `get_account_list` and `place_order`.

Everything else — cancelling, order status, positions, futures — is done by **guessing method names at runtime**. It loops through every attribute on the SDK object, picks anything whose name contains "cancel" or "quote" or "position", and *calls it for real* to see if it works.

That single design choice is upstream of a surprising number of your worst days.

---

## WIN #1 — Push order events. This is the big one.

**Package:** `webull-python-sdk-trade-events-core` (published, not installed on your PC)
**Class:** `EventsClient(app_key, app_secret).do_subscribe([account_id])` with an `on_events_message` callback — a gRPC stream.

**Webull will tell you the instant an order fills.** You don't have to ask.

Right now the bot asks, repeatedly, and guesses when the answer is unclear. Look at what that has cost you:

| Your bug | What it really was |
|---|---|
| 8/10 phantom "META +$158 @7.88" that never happened | the bot's own guess, not a fill |
| AMD logged "failed" when it filled +$146 | poll missed it |
| fill-race fix: keep polling ~5s after a cancel | a workaround for not being told |
| "account-based live fill detection (order probe never sees live fills)" | the poll is blind on live |
| P&L "fiction" from desync | all of the above compounding |

Every one of those is the same root cause: **the bot is inferring fills instead of being told about them.** A push stream replaces the inference with fact. It doesn't cost rate-limit budget either — it's a stream, not requests.

This is the highest-value change available to you, by a distance. It is also the biggest, so it goes on its own branch and gets tested on paper first.

---

## WIN #2 — Stop guessing method names

Here's the actual code doing your cancels (`_try_calls`, webull_options.py:981):

```python
for m in dir(h):
    if not any(v in low for v in verbs):   # v is "cancel"
        continue
    try:
        res = fn(*args, **kw)              # <- a REAL HTTP request
```

It calls **every method whose name contains "cancel"** until one doesn't throw. Three separate harms:

**(a) It may have been cancelling with the wrong endpoint all along.**
The SDK has both `cancel_order` (stocks) and **`cancel_option`** (options). The hunt calls whichever comes first alphabetically and doesn't error. Now re-read your own 8/12 note:

> *"every cancel came back ORDER_NOT_FOUND, so the resting stop never died and then blocked every sell on that contract (8/12, all day: META, QQQ, NVDA, SPCX...)"*

You fixed that by switching which order-id you pass. That helped — but calling the **stock** cancel endpoint for an **option** order would produce exactly that symptom too. Worth checking before you trust the current fix.

**(b) Every failed guess is a real API call.** You're spending your 300-per-60-seconds budget on requests designed to fail. This feeds directly into the 429 problem from v3.5.0.

**(c) `order_status` with no id returns someone else's trade.** Your own comment documents it — a phantom MNQ "filled 3.0 at 1.41" that was actually a SPY position from four minutes earlier, which then armed a stop and sent a close for the wrong size. The typed `OrderDetailRequest.set_client_order_id()` structurally cannot do that.

**The replacements, all typed and documented:**

| Doing it by guessing | Use instead |
|---|---|
| `_try_calls(["order_v3"], ["cancel"], ...)` | `OrderOperationV2.cancel_option(...)` |
| `order_status()` hunt | `OrderOperationV2.query_order_detail(...)` |
| `positions()` hunt | `AccountV2.get_account_position(s)` |
| `_quote_fns` / `_stock_fns` hunts | `MarketData.get_snapshot(symbols, category)` |
| `_fut_rows` shape hunt | `TradeInstrument.get_tradeable_instruments` |

---

## WIN #3 — `replace_option` — the ratchet has a naked window right now

This is a safety bug, not just an efficiency one.

The ratchet currently does **cancel, then place**:

```python
if old_oid:
    wb.cancel(old_oid)                    # stop is now GONE
new_oid, placed = wb.place_stop(...)      # if THIS fails, you have no stop
```

Between those two lines the position has **no protection at all**. If the place fails — a 417 clamp refusal, a 429, a dropped connection — you are naked and the log tells you something reassuring but wrong:

> *"The old stop is still in place; the watchdog on this PC covers the gap."*

The old stop is **not** still in place. It was cancelled on the line above.

**`OrderOperationV2.replace_option(...)` modifies the resting order in place.** One call instead of two, atomic, and there is no moment where the stop doesn't exist. It also halves the ratchet's API cost, which matters more now that it fires on 5% rungs.

Fix this one even if you do nothing else on this list.

---

## WIN #4 — `preview_option` — check before you send

`OrderOperationV2.preview_option(...)` validates an order without placing it. Buying power, price steps, whether the stop is legal against the live market — all answered without an order going out.

Today the bot learns these by getting refused. The whole stop-clamping dance exists because Webull 417s a stop that sits above the market, and you found that out the hard way. Preview turns "place it and see" into "ask first, then place."

Best use: the ratchet's stop move, and any entry where buying power is tight.

---

## WIN #5 — A real market calendar

`TradeCalendar.get_trade_calendar(market, start, end)`.

The bot works out market hours from the clock. That's wrong on holidays and half-days — the 1pm close on the day after Thanksgiving, for one. Consequences today: the 40-minute silence alarm barks on a holiday, and the boot logic decides what counts as an expired option using a guess about what day it is.

Small change, removes a whole category of "why did it do that at 1:15."

---

## WIN #6 — Validate the contract before ordering

`TradeInstrument.get_trade_security_detail(symbol, market, strike, expiry, ...)` confirms a contract exists and is tradeable.

This is your parser's safety net. Recent failures in this family:

- day-first expiries (`"26/8"`) — cost a TLG META entry on 8/25
- Vero's `"MSTR SEP 18 2026 $150 CALLS"` — read as "no full contract"
- strikes deeper than one rung OTM needing a quote-verified walk

Every one of those currently surfaces as a rejected order or a silent skip. A validation call turns them into a clean "that contract doesn't exist, here's the nearest one that does" **before** anything is sent — and the strike-walk logic gets simpler because it can ask instead of probe.

---

## WIN #7 — Turn on the SDK's own logging

`ApiClient.set_file_logger(path)` — full request/response logging, built in, one line.

You have two open mysteries that this answers directly: the `ai_reader.py` HTTP 404, and the 10:05 + 10:30 bridge crashes on 8/11 that cost XOM and GM. Right now you're reading tea leaves in `bridge.log`. Turn this on and stop guessing.

---

## WIN #8 — Native trailing stops — WORTH TESTING, NOT ASSUMING

`PlaceOrderRequest` has `set_trailing_type()` and `set_trailing_stop_step()`.

If Webull accepts these on **options**, the ratchet could live at the broker instead of on your PC. It would keep trailing with the bridge closed, the laptop asleep, the power out.

**But I could not confirm options support.** Those setters are on the *stock* order path (`add_stock_order_params`). The options path takes a free-form `new_orders` dict, so the fields might pass through — or might be silently ignored, which is the dangerous outcome.

Do not build on this until it's tested on one paper contract and the resting order is confirmed in the Webull app as a trailing stop. If it works, it's a bigger deal than everything above it on this list.

---

## WHAT CAN BE DELETED

Line counts from your actual files:

| Code | Lines | Replaced by |
|---|---|---|
| `webull_options.py` plumbing (`_quote_fns`, `ask_bid`, `_stock_fns`, `stock_price`, `_send_combo`, `_send`, `_try_calls`, `order_status`, `cancel`, `positions`, `futures_positions`) | **468** | typed SDK requests |
| `webull_futures.py` (`_try`, `_fut_rows`, `front_month`, `_place`, `_order_id_of`) | **231** | same |

**~700 lines of guesswork, about 26% of `webull_options.py`,** doing what a dozen documented calls do — and doing it by making failing HTTP requests against your rate limit.

That's not a rewrite you do in one sitting. Do it endpoint by endpoint, each one behind the existing fallback so a swap that misbehaves drops back to the hunt.

### The other duplication — parser.js ↔ signals.py

You maintain two parsers that must agree, with 381 parity tests holding them together. The extension could POST raw message text to the bridge and let Python do all the parsing, deleting the JS half entirely.

**I'd leave it.** The JS side does in-flight contract locking and dedupe *before* the network hop, and that speed is the point of the whole thing. The parity tests are doing their job. This is duplication you chose for a reason — the reason still holds.

---

## THE ORDER I'D DO THESE IN

1. **`replace_option` for the ratchet** — small, fixes a real naked-stop window. Today.
2. **`cancel_option`** — check whether the option cancel was ever hitting the right endpoint.
3. **SDK file logging** — one line, and it makes everything after this easier to debug.
4. **Push order events** — the big one. Own branch, paper first.
5. **`preview_option`** on stop moves and tight-buying-power entries.
6. **Trade calendar** + **contract validation** — cheap, kills two nuisance categories.
7. **Trailing stop test** — one paper contract, confirm in the app.
8. **Retire the hunts**, one endpoint at a time, fallback kept.

Items 1–3 are an evening. Item 4 is a project, and it's the one that stops the bot inventing fills.
