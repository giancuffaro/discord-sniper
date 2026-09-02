# HANDOFF — Option price history
### The one thing blocking every backtest, and how to fix it
**9/2/26. Standalone — nothing here depends on the v3.5.0 handoff.**

---

## THE PROBLEM, IN ONE LINE

**Webull's API will not give you historical option prices.** I tested it rather than trusting the docs:

```
get_stock_bars_single(symbol="SPY   260904C00762000", category="US_OPTION")
  -> UNSUPPORTED_CATEGORY: The category is not supported by this interface: US_OPTION
```

Their own tool description says it outright: *"US_OPTION type query is currently not supported."* Stocks, ETFs, futures, crypto, event contracts — all fine. Options — nothing.

Options are **real-time only** at Webull: the snapshot endpoint your bot already uses for bid/ask, and possibly the streaming feed (tomorrow's test settles that). The Webull *app* draws option charts; the API doesn't expose them.

**Why this matters:** it's why the ratchet backtest had to *model* option prices with Black-Scholes instead of knowing them. That model is the single weakest link in the whole analysis. Every conclusion about tiers, rungs and the anti-clip rule rests on my IV curve being roughly right.

---

## FIX 1 — RECORD YOUR OWN (free, starts tonight, already written)

The quote bus in v3.5.0 already quotes every open contract every 300ms. Recording those makes you your own data vendor.

**One line**, right after `QUOTES = QuoteBus(...)` in `bridge.py`:

```python
QUOTES.record_to("option_tape.csv")
```

It's already implemented in `quote_bus.py` — `record_to()` and `_tape()`. Writes `ts,occ,bid,ask`, appends, never re-read at runtime, and a failed write can never disturb trading.

**Size:** ~10 MB/day with 3 contracts open all session, ~34 MB/day with 10. Rotate monthly.

### Why this beats buying data, for your purpose

- It's **your universe** — exactly the contracts your rooms call, not a sample of everything.
- It captures **bid and ask at the moment the ratchet actually sees them**, which is the decision point that matters. A vendor gives you the market; this gives you what your bot was looking at.
- It costs nothing and needs no account.

**The catch:** it starts empty. You get a usable sample in weeks, not tonight. Which is why Fix 2 exists.

---

## FIX 2 — BUY A ONE-TIME BACKFILL (do NOT buy a subscription)

Here's the thing most people get wrong: **you don't need an ongoing data feed. You need one historical pull.** After that, your own tape covers you forever.

So price this as a one-off, not $80–99 every month indefinitely.

### What you actually need — and the requirement almost everyone misses

**Your stop watches the BID.** So trade prices are not enough. OHLC of *trades* will not tell you whether a stop was hit — you need **QUOTE data (bid/ask)**, at 1-minute or finer. Any source that only sells trade bars is useless for testing an exit rule.

### The options, checked

| Source | Historical options | Depth | Cost | Verdict |
|---|---|---|---|---|
| **Databento** | OPRA, pay-per-GB | full | **$125 free credit**, then per-GB | **Best fit — one-off, no subscription** |
| **ThetaData VALUE** | 1-min OHLC **+ quotes** | back to 2020-01-01 | ~$80/mo (2026 comparison) | Best value if you want a month's access |
| ThetaData FREE | EOD only | back to 2023-06 | free | Useless intraday |
| **Polygon** | tick-level | full | ~$79/mo options add-on | Fine, same idea as ThetaData |
| **Alpaca** | option bars | since Feb 2024 | free tier caps history at **the last 15 minutes**; $99/mo to remove | **Not free for this** — I nearly recommended it before checking |
| **IBKR** | option bars | **no expired contracts** | needs data pack | **Useless here.** Every 0DTE you'd study is expired |
| **Tradier** | end-of-day only | — | $10/mo data-only | No intraday, no good |
| **Schwab API** | **none** — "equities and ETFs" only | — | — | **Same wall as Webull** |
| **thinkorswim platform** | charts + OnDemand to 2009 | deep | free w/ account | Manual export only, trade prices not quotes — see below |

### thinkorswim — you were right, but it doesn't solve this

You said TOS has previous option chart data. **You're right, and it's the best free option-history tool out there.** But the split matters:

**The platform has it:**
- You can chart an option contract directly and right-click → **"Export chart data…"** to CSV (OHLCV).
- **OnDemand** replays any day tick-by-tick back to **7 December 2009** — options included. Nothing else free comes close.

**The Schwab API does not.** Straight from their docs:

> *"Schwab provides price history for equities and ETFs. It does not provide price history for options, futures, or any other instruments."*

Same wall as Webull. The only option endpoint is `get_option_chain()` — current chains, no history.

**So why it doesn't fix the backtest:**

1. **No way to get it out at scale.** Chart export is manual, one contract at a time. For 520 trades that's 520 right-clicks. Not a pipeline.
2. **It's trade prices, not quotes.** Options trade sporadically — a 1-minute OHLC on a quiet contract has gaps, and it still doesn't tell you the **bid**, which is what your stop watches. Same disqualifier as any trade-only source.
3. **Traders report quality issues** — closing-price snapshots and implausible spreads even on liquid tickers. Fine for eyeballing, not for deciding a rule.

**What it IS genuinely worth doing** (and this is a real use, not a consolation):

> **Spot-check my IV model.** Pull 5–10 option charts manually for contracts on 8/28, 8/31 and 9/01 — the days I backtested — and compare them to what my Black-Scholes model produced. That directly tests the weakest link in the entire ratchet analysis, costs an hour, and needs no purchase.

If my modelled premiums track the real ones, the anti-clip conclusion gets a lot more solid. If they don't, we found that out for free before you traded on it. A Schwab account costs nothing to open if you don't have one.

### What I'd do

**Databento.** Pay-as-you-go by the gigabyte, and **new accounts get $125 in free credits** (they expire after six months, one per team). You need maybe six months of quote data on the ~30 tickers your rooms actually trade — not the whole OPRA universe. Batch-download it once, and you're billed once even if you re-download for 30 days.

There's a decent chance that whole backfill lands inside the free credit. If it doesn't, one month of **ThetaData VALUE** (1-minute OHLC *and* quotes, back to 2020) gets you the same thing and you cancel after the pull.

Either way: **buy once, download, cancel.** Your tape recorder handles everything after that.

---

## WHAT THIS UNLOCKS

Right now every number in `ANTI-CLIP.txt` and `ALL-NAMES-CHECK.txt` carries the same asterisk: *real underlying bars, modelled option prices*. With real quote data, those become checkable instead of arguable:

- Is `SCALE_K = 0.40` right, or was that an artifact of my IV curve?
- Do the tier boundaries ($1 / $2) fall in the right places on real premiums?
- Is the tick floor doing anything useful, or is it noise?
- Does any of it survive a **fast tape** or an event day? My three test days were all quiet — SPY realized vol was 7.5%. That's the biggest untested hole in the whole analysis.

That last one matters most. Everything I've concluded comes from three calm days. A ratchet that works in chop can behave completely differently when things actually move.

---

## ORDER OF OPERATIONS

1. **Tonight:** add the one line, `QUOTES.record_to("option_tape.csv")`. Free, zero risk, starts accumulating immediately. Do this even if you never buy anything.
2. **Tomorrow:** run the streaming test. If Webull's stream carries options, your tape becomes tick-by-tick instead of 300ms samples — a much better record for free.
3. **Free, one hour, highest value per minute:** open thinkorswim, chart 5–10 option contracts from 8/28, 8/31 and 9/01, and compare them against my modelled premiums. That validates (or kills) the weakest assumption in the whole ratchet analysis without spending a cent. **Do this before you consider buying anything.**
4. **Only if step 3 says the model is roughly right and you still want more:** open a Databento account, spend the free credits on quote data for your top ~30 tickers over the last six months, pull it once.
5. **Then:** re-run the ratchet comparison against real prices. If the anti-clip rule holds up, you'll actually know. If it doesn't, better to find out from data than from a live account.

---

## ONE HONEST NOTE

None of this is urgent in the way tomorrow's Block A is. The tape recorder is one line and should go in regardless. The backfill is worth money only if you intend to actually re-run the analysis — if it's going to sit unused, skip it and let the recorder build the dataset for free.

I'd rather you spend nothing and wait three weeks than buy data you don't use.
