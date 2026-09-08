# UPGRADES — what the rest of the world has that we don't
Researched 9/6/26. Three parallel sweeps: GitHub, execution engineering, trader forums.
Everything below was checked against **our actual source** before it was written down.

---

## FIRST: what we already have that the field does not

I checked before recommending. We are ahead of the open-source field on six things:

| | us | the field |
|---|---|---|
| Chrome MV3 DOM reader | yes | **nobody.** Every other project uses a Discord *selfbot* user token |
| Voice → order | yes | **zero** open-source projects parse voice |
| Vision / image alerts | yes | one abandoned `open_cv/` folder in a dead repo |
| Token bucket w/ priority lane + reserve floor | `quote_bus.py:78` | nobody |
| Underlying-referenced stop watch | `bridge.py:1757` | discussed, not implemented anywhere public |
| Spread gate (20% of price AND $0.20 abs) | `webull_options.py:449` | one repo has min-volume/min-delta |

**The selfbot point is the big one.** Every comparable project — including the commercial one — drives the Discord gateway with a user token, which is explicitly bannable under Discord's own policy. We read the DOM of a real logged-in client. That is structurally safer than the entire rest of the field, and it is why no prior art exists to copy from.

**CORRECTION (9/7): "nobody" was too strong — there is exactly one.**
`vnoctem/discord-web-reader` is our architecture to the letter: a Chrome
extension that reads Discord Web's DOM and posts to a local HTTP server. It is
also **0 stars, 1 fork, 4 commits, jQuery, abandoned** — a proof of concept, not
a project. The claim stands in spirit (no serious prior art) but the word
"nobody" was wrong and is now corrected.

**WHAT DISCORD ACTUALLY DETECTS (researched 9/7).** Their published detection
signals are all about what an account *sends*:
  * messages posted with NO preceding typing event
  * typing fired across several channels in 5-50ms where a human needs 300-500ms
  * channels iterated programmatically in ID order — a fingerprint
  * account-level flags: avatar, creation date, user flags
Verified against our own code: the extension makes **ZERO** requests to
Discord. The only network destination anywhere in extension/*.js is
`http://127.0.0.1:8787`. It sends no messages, fires no typing, uses no user
token, and never touches the gateway. Every listed signal is emitted by
sending; we send nothing, so we emit none of them.

**THE ONE EXCEPTION, AND IT IS REAL:** `content.js joinLiveVoice()` clicks the
LIVE badge and presses "Join" to enter a voice channel. That is the only place
the extension ACTS AS THE USER rather than reading, and unlike reading it
produces a genuine server-side event — a voice state update, at machine speed,
the instant a badge appears. If any part of this system ever draws attention,
it is that one. The clean fix is not to disguise it but to stop automating it:
make the LIVE join a notification G taps. Reading, parsing and execution are
completely unaffected, because none of them talk to Discord at all.
See also: client modifications (BetterDiscord et al.) are separately banned for
injecting into Discord's client bundle. We do not do that either — a content
script observing rendered DOM is not a patched client.

**There is exactly ONE serious open-source competitor:** `AdoNunes/DiscordAlertsTrader` (79 stars, alive, last push 2026-01-17). Everything else is a dead 2022 TD-Ameritrade toy, a forex Telegram copier solving an easier problem, or a closed-source binary with a marketing README.

⚠️ **The GitHub `trade-copier` topic is star-farmed.** `DelegateStar/Ninja-Trader-2026` has 456 stars on **4 commits and 14 KB of code**. `DaggerConsole/metatrader-4-boost`: 260 stars, **zero forks**. These are malware droppers or affiliate funnels. Do not clone anything from that topic.

---

## THE GAPS — verified against our code, ranked

### 1. We never measure alert-timestamp → fill. (grep: zero hits)
`bridge.py`, `positions.py`, `signals.py` contain no latency instrumentation of any kind.

**Nobody in the field measures this either** — I checked the competitor's source specifically. It is genuine white space, and it is the number that tells you which of 26 rooms is worth keeping. Two timestamps and a subtraction:

```
alert_seen_at  (extension already stamps it)
order_sent_at
fill_at
```

Log `fill_at - alert_seen_at` per caller per room. Then log the contract mid at +1s/+5s/+30s/+60s after the alert. **That decay curve has never been published by anyone.** It answers, with our own data, whether chasing or waiting is right *per caller* — instead of us arguing about it.

### 2. No caller scorecard, no auto-bench. (`scoreboard.py` has no per-caller scoring)
`scoreboard.py` loads rooms, exports and trades — and stops. There is no expectancy, no win rate, no grouping by caller.

The competitor has the whole offline half and it is worth copying wholesale:
- **Three P&L columns side by side:** the caller's *claimed* price, the *actual* market price at his alert timestamp, and what *our exit rules* got. That three-way split proves whether a caller's posted numbers are real AND whether our ratchet beats his exits.
- `groupby('Trader')` → PnL$, mean PnL%, wins, trade count.

**Nobody has closed the loop to automatic demotion.** Sample-size discipline from the stats literature: 20 trades at 65% is p > 0.2 — noise. ~100 trades minimum to act on. Profit factor above ~4.0 should be read as a red flag for cherry-picking, not as excellence.

### 3. Position sizing is fixed contracts, not fixed dollar risk.
The forex copiers all derive size from stop distance: `size = risk_budget / stop_distance`. Every trade risks the same dollars no matter how wide the caller's stop is.

Ours: `size = risk_budget / (entry_premium × ratchet_stop_%)`.

**The data behind it:** Option Alpha, 230,000 0DTE trades — bucketing by dollar risk showed **no relationship between amount risked and outcome**. Sizing up did not improve odds. Kelly on lottery-shaped long 0DTE (5–10x payoff, <10% hit rate) outputs **under 1% of capital**; practitioners run 0.25–0.5× Kelly, i.e. fixed 1–2% risk.

### 4. Cross-room dedupe only covers OPEN/ADD, and only by open position.
`bridge.py:1852` — "Only OPEN/ADD are deduped." That catches three callers posting the same trade, but it can't distinguish a genuine average-down from a duplicate.

Field practice: hash `(action, symbol, strike, expiry)` and suppress inside a **5–10 second window**. The window is the entire design decision.

### 5. No `data_integrity` flag on journal rows.
From a dead-but-well-built OMS: when the broker errors on a known order ID, don't hang — assume filled and tag the row `"Assumed"` vs `"Reliable"`. Every downstream P&L row carries the flag, so a backtest can exclude trades whose fill was never actually confirmed. **Cheap column, makes our numbers honest.**

### 6. No stale-order killer.
Any unfilled entry older than N seconds gets cancelled automatically. Prevents a stale limit filling into a move that is already over. Same repo: `MAX_QUEUE_LENGTH` + a `KillQueueOrder` task.

---

## EXECUTION TECHNIQUES WORTH IMPLEMENTING

### The gamma correction — our stops are set too tight, every trade

The delta-gamma-theta expansion: `dC ≈ Δ·dS + ½·Γ·(dS)² + Θ·dt`

For a **long** option the gamma term **always adds**. So `stop = entry − Δ × distance` predicts a bigger premium loss than actually occurs, and sets the stop too low.

Worked example — SPY 640, 0DTE 640C at $2.10, Δ=0.52, Γ=0.11, stop 1.20 points lower:

| | |
|---|---|
| linear | 2.10 − 0.624 = **$1.476** |
| gamma-corrected | 2.10 − 0.624 + 0.5(0.11)(1.44) = **$1.555** |

**8¢ too tight — nearly three ticks of unnecessary give-up on every single trade.** On a 3-point move the gap is 50¢.

And gamma is not constant through the day: ATM 0DTE gamma runs **2–5× a 7DTE contract in the morning and 10×+ near the close**. A stop distance computed at 10:00 is wrong by a factor of 2–5 at 15:30. **Recompute the greeks-based stop on a schedule, not once at entry.**

### The trigger-source problem — why we get wicked out

A sell-stop on an option is triggered by the **ASK** (tastytrade) or by `ask ≤ stop OR last ≤ stop` (Fidelity). A market maker widening his quote — pulling the bid with **zero trades and zero underlying movement** — satisfies the trigger.

The professional position, from a 15-year Chicago options broker: stop orders on options are market orders in disguise, and the desk saw stops set at $3 fill at **$0.05** on the open and trade back to $1.00 minutes later.

**The architecture that follows:**
- **Underlying price = the trigger.** Cheap, deep, penny-tight, and not charged against our 60/min option-snapshot budget.
- **Option premium = a disaster floor only**, set far below, catching IV crush and nothing else.
- **The resting broker STOP_LOSS leg = a crash hedge, set WIDE.** It exists for when our process dies. This inverts the hobbyist design that puts the tight stop at the broker and gets wicked out.
- **Never fire on a single quote.** Require the condition on two consecutive polls.
- **Stale-quote guard:** reject any snapshot older than 2× the poll interval; reject any quote where `bid ≥ ask` (locked/crossed = corrupt); reject any where `spread/mid` is more than 2× that contract's own trailing median.

We already have `_underlying_stop_watch`. This makes it the primary rather than a helper.

### Walk-limit, properly parameterized

Schwab's Walk Limit is exactly five parameters: start, end, price increment, time increment — and at the end price it **stops walking and rests**. Their worked examples: +$0.01 every 5s, or +$0.02 every 4s.

Their own caveat is the important half: walk limits "aren't ideal... for options that are moving in one direction or another rapidly." That is our exact case. So:

```
ENTRY (patient, capped):        EXIT (aggressive):
  start = mid                     start = bid
  cap   = ask                     step  = 1 tick DOWN
  step  = 1 tick                  dwell = 1s
  dwell = 3s (5s if wide)         floor = bid_at_trigger
  re-anchor to a FRESH mid                − max(3 ticks, 0.25 × spread)
  ABORT after 20s or if the
  underlying moved against us
```

The **abort clause** is what hobbyist bots omit. An entry unfilled after 20s on a 0DTE is telling you the move left; chasing converts a missed trade into a bad trade. The exit **floor** is what stops a liquidity vacuum turning our stop into an unbounded market order.

Skip the modify entirely when the new price equals the old one — that saves a rate-limit token per rung.

### Request coalescing (singleflight)

Three processes wanting the same contract's snapshot inside one second must resolve to **one** API call. Shared `{contract_id: (ts, quote, in_flight)}` map with a ~900ms TTL.

**Open question worth 10 minutes:** does Webull's option snapshot endpoint accept a symbol *list*? Our reference says 20 symbols/call. If we're not batching, that is the single biggest quota win available to us.

### The binding constraint nobody states plainly

Option snapshot at 60/min is **1 per second**. With N open positions, our per-position stop granularity is **N seconds**. Order-detail/positions at 2 per 2s is also 1/sec, so a full reconcile of N positions takes N seconds.

**Design consequence: never place a stop whose correctness depends on sub-N-second reaction.** Ratchet rungs must be spaced wider than worst-case quote staleness. This is a hard limit, not a tuning parameter.

### Startup order — the double-submit bug

```
1. Load journal. Every non-terminal row = UNKNOWN.
2. Fetch broker positions + open orders. BROKER IS TRUTH.
3. Three-way diff:
   broker position, no local state  -> ORPHAN. Adopt and arm a stop NOW.
   local state, no broker position  -> resolve via order history, close row.
   broker open order, no local      -> adopt or cancel.
4. ONLY THEN enable new-order submission.
```
The classic double-submit is a bot that starts trading at t=0 while its reconcile is still in flight at t=3s.

**Unverified and worth checking:** whether Webull's Open API accepts a client-supplied order ID. If not, we need a local fingerprint — `sha256(account|contract|side|qty|intent|minute_bucket)` fsync'd **before** the HTTP call, and on restart any pending older than 30s gets resolved by *querying order history*, never by re-submitting blind.

### 0DTE close-of-day

- Spreads that are $0.05 at the open **widen to $0.50+ by 3 PM**. A SPY put quoted $0.22/$0.24 at 1DTE can sit at **$0.02/$0.05** on expiration day — a spread of 150% of mid, past every filter we have. **A liquidity gate that blocks our exit is a bug.** Widen the gate as the day progresses.
- Three independent sources converge on **flat by 3:30 PM ET** for 0DTE; the last 30 minutes is the worst risk-adjusted period of the day.
- OCC auto-exercises at **$0.01 ITM**. A SPY 0DTE call left open $0.02 ITM becomes **100 × $640 = $64,000** of unfunded stock over a weekend. That single event dwarfs every execution improvement in this document. **"Flat by 15:45" needs its own watchdog timer, independent of the trading logic.**
- Pin risk: avoid the highest-OI cluster strike in the final hour. Price oscillating around a magnet strike is the maximally hostile environment for a tight stop.

### Backtest honesty — what our replays are getting wrong

Our `ratchet_lab.py` replays bar lows. Three corrections:

1. **Fill the stop at the BID at the NEXT observation after trigger — never AT the stop price.** With 1-minute data the exit is often *past* the stop: price 9.99, stop 10.00, next print 10.25. The uncapped number is the honest one.
2. **The replay must respect our real poll cadence.** If live we can only see a contract every N seconds, the backtest may only see it every N seconds. **This one change usually costs more than slippage does.**
3. **Model no-fills.** If the exit ladder's floor stays above the bid for the whole window, the trade does *not* exit — carry it. A backtest with a 100% limit-fill rate is fiction.

Also: entry fills at the **ask**, exit at the **bid**. Mid-price replays are optimistic by roughly the full spread.

### The stacking trap — the finding that should govern all of the above

SPY 0DTE opening-range breakout, real 1-minute option bars, 303 trades, Feb 2024–Mar 2026: −50% stop / +100% target / 3:30pm time stop returned **$13,792**. Every individually-optimal tweak — tighter 40% stop, bigger breakout buffer, 2pm time stop — made the combined system **worse: $5,710**.

A separate futures study found the same shape: the **fixed** exit had the highest total return; an immediate tight trailing stop had the best in-sample Sharpe and was rejected as parameter-fragile.

**Two independent studies agree that the simple exit beat the optimized one.** That is the argument for implementing these one at a time, measured, not as a batch.

---

## SOURCES

Competitor: [AdoNunes/DiscordAlertsTrader](https://github.com/AdoNunes/DiscordAlertsTrader) ·
[TreyThomas93/python-trading-bot-with-thinkorswim](https://github.com/TreyThomas93/python-trading-bot-with-thinkorswim) ·
[mogden16/TradierTDA_Trader](https://github.com/mogden16/TradierTDA_Trader) ·
[ogunjobiFX/MT4-MT5-Forex-Signal-Copier](https://github.com/ogunjobiFX/MT4-MT5-Forex-Signal-Copier-Telegram-Bot) ·
[DiscordTrader/BotifyTrades](https://github.com/DiscordTrader/BotifyTrades) (README only, no source)

Execution: [Schwab Walk Limit](https://www.schwab.com/learn/story/how-to-use-walk-limit-orders-options-trading) ·
[projectfinance — never use stops on options](https://www.projectfinance.com/stop-loss-calls-and-puts/) ·
[Fidelity order-type FAQ](https://www.fidelity.com/trading/faqs-order-types) ·
[Cboe RG18-009 bid-ask differentials](https://cdn.cboe.com/resources/regulation/circulars/regulatory/RG18-009.pdf) ·
[MIAX Penny Program](https://www.miaxglobal.com/markets/us-options/all-options-exchanges/penny-program) ·
[OIC exercise FAQ](https://www.optionseducation.org/referencelibrary/faq/options-exercise) ·
[SpotGamma 0DTE](https://spotgamma.com/0dte-options-strategy/) ·
[FlashAlpha gamma/pin risk](https://flashalpha.com/articles/spxw-0dte-guide-same-day-sp500-options-gamma-pin-risk) ·
[Option Alpha 0DTE decay](https://optionalpha.com/blog/0dte-options-time-decay)

Data: [Options Cafe SPY 0DTE ORB backtest](https://options.cafe/blog/0dte-opening-range-breakout-strategy-spy-backtested-results/) ·
[CrackingMarkets exits/slippage](https://www.crackingmarkets.com/intraday-breakout-details-that-matter-exits-slippage-and-0dte-options/) ·
[Option Alpha 230k trades](https://optionalpha.com/blog/0dte-options-strategy-performance) ·
[Option Omega backtest FAQ](https://docs.optionomega.com/backtesting-faq)

Risk: [Discord self-bot policy](https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots) ·
[SEC v. Constantinescu (Atlas Trading)](https://www.sec.gov/newsroom/press-releases/2022-221) ·
[SEC Rule 15c3-5 FAQ](https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions/divisionsmarketregfaq-0)

**Could not verify:** Reddit and X are unreachable from my tooling — no direct citations from either.
Webull client-order-id support, Webull snapshot batching, and Webull's auto-exercise threshold vs OCC's
$0.01 are all unchecked and all change the design.
