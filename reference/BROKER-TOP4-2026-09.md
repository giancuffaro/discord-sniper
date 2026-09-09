# Top 4 brokers for the sniper — deep research, 9/3/26

G asked: *"is there any other broker? do deep research about this and make a
list of top 4."* Researched 9/3/26; every claim links to its source at the
bottom. Ranked for **this machine's** needs, not for a general trader.

## What actually matters here (in order)

1. **Conditional / bracket orders ON OPTIONS.** The stop must be born with the
   entry — no naked moment. Webull can do this (MASTER+STOP_LOSS) but cannot
   trigger anything off the UNDERLYING's price.
2. **Streaming OPTION quotes.** The whole ratchet runs on `quote_bus`'s 1/s
   batched HTTP poll because Webull has no option stream at any price. This
   is the single biggest upgrade available and it is invisible until you see
   the stop moving on ticks instead of on a one-second photo.
3. **Cost at HIS size** — 1 contract per entry, ~200 contract-sides/month.
4. **Unattended auth.** The machine runs alone. Anything needing a weekly
   human browser login is a liability, not a feature.
5. **Python API maturity** — a real SDK, not a screen-scrape.

---

## 1. Tradier — the recommendation

| | |
|---|---|
| Options commission | **$0.35/contract** (Pro, $10/mo) · **$0.10/contract** (Pro Plus, $35/mo) |
| Cost at his size | **~$55–80/mo** |
| Conditional orders on options | **Yes** — `oto`, `oco`, `otoco` |
| Option streaming | **Yes, included free** with the brokerage account |
| Auth | Simple bearer token — no weekly re-login |
| API | Mature REST, well documented, options-first |

**Why it wins:** it is the only one that gives all three of conditional
option orders, free option streaming, and a token that survives being left
alone — at a price that doesn't eat the account. Tradier is built API-first
for exactly this kind of use.

**Watch:** it is a smaller broker than Schwab/IBKR; fill quality on thin
contracts is the thing to prove in the two-week side-by-side, not assume.

## 2. tastytrade — the strong second

| | |
|---|---|
| Options commission | **$1.00/contract to OPEN, $0 to CLOSE**, capped $10/leg |
| Cost at his size | ~$100/mo (100 round trips — you only pay the open) |
| Conditional orders on options | Not confirmed in the docs — **must verify before committing** |
| Option streaming | **Yes — dxfeed websocket, and it streams GREEKS as well as quotes** |
| Auth | Session token |
| API | Official public API + a good typed Python SDK |

**Why it's interesting:** streaming **greeks** would let the ratchet reason
about delta and theta directly instead of inferring from price — a genuinely
better machine, not just a faster one. Closing trades free also suits a bot
that exits everything it opens.

**Why it's second:** the conditional-order question is unresolved in their
public docs, and that's the feature that started this. Verify first.

## 3. Interactive Brokers — cheapest at volume, heaviest to run

| | |
|---|---|
| Options commission | **$0.15–$0.65/contract** tiered by volume; fixed plan $0.65 |
| Cost at his size | ~$60–130/mo (he'd be at the expensive end — tiers reward volume) |
| Conditional orders | **Yes**, extensive — IBKR simulates order types the exchange lacks |
| Option streaming | Yes, but **100 concurrent market-data lines** by default, and OPRA option data is a **paid add-on** |
| Auth | TWS/Gateway must stay running, or Web API OAuth — the most operationally fragile of the four |
| API | Powerful, mature, and the least pleasant to work with |

**Verdict:** the best economics if his size grows a lot, and the worst
day-to-day operational fit right now. Revisit if volume 5×'s.

## 4. Schwab — capable, but the auth disqualifies it

| | |
|---|---|
| Options commission | **$0.65/contract**, no base |
| Cost at his size | **~$130/mo** — the most expensive of the four |
| Conditional orders on options | **Yes** — OTO, OCO, OTOCO, plus a selectable stop trigger (STANDARD/BID/ASK/LAST/MARK) |
| Option streaming | Yes, included |
| Auth | ⚠️ **Refresh token expires every 7 days with NO programmatic renewal** |
| API | Good docs, solid `schwab-py` community SDK, ~120 req/min |

**Verdict:** technically excellent and the trigger-source control is the
nicest of the four — but a money machine that dies after any week-long gap
and needs a human at a browser to come back is the wrong shape for this.
Most expensive, too.

---

## Ruled out, and why (so nobody re-litigates them)

- **Alpaca** — commission-free options, which sounds perfect, but **no
  bracket or OTO orders on options at all** (the stop can't be born with the
  entry), and real-time OPRA option data is a **$99/mo** plan. Fails on the
  exact two things that matter most here.
- **Robinhood** — no official/supported trading API.
- **E*TRADE / Public / Lime** — either no real options API, or no
  conditional option orders worth the migration.
- **Webull (staying)** — $0 commissions and stable auth, but no option
  streaming at any price and no conditional orders on options. It is the
  cheapest and the blindest.

## The call

**Build the adapter. Run Tradier alongside Webull. Verify tastytrade's
conditional orders in parallel** — if they exist, tastytrade's streaming
greeks make it a serious contender on capability even at a higher cost.

Do not migrate anything until the journal has two weeks of both brokers'
real fills side by side.

## Sources
- Tradier pricing: https://tradier.com/individuals/pricing
- Tradier streaming / market data: https://docs.tradier.com/docs/streaming-data · https://docs.tradier.com/docs/market-data
- Tradier oto/oco/otoco: https://docs.tradier.com/docs/trading.md
- tastytrade developer portal / API overview: https://developer.tastytrade.com/ · https://developer.tastytrade.com/api-overview/
- tastytrade streaming (dxfeed, quotes + greeks): https://developer.tastytrade.com/streaming-market-data/ · https://tastyworks-api.readthedocs.io/en/latest/data-streamer.html
- tastytrade Python SDK: https://github.com/tastyware/tastytrade
- IBKR options commissions: https://www.interactivebrokers.com/en/pricing/commissions-options.php
- IBKR market data pricing / lines: https://www.interactivebrokers.com/en/pricing/market-data-pricing.php
- IBKR conditional orders: https://www.interactivebrokers.com.au/en/trading/orders/conditional.php
- Schwab pricing: https://www.schwab.com/legal/schwab-pricing-guide-for-individual-investors
- Schwab 7-day refresh token: https://schwab-py.readthedocs.io/en/latest/auth.html · https://github.com/alexgolec/schwab-py/issues/100
- Schwab streaming: https://schwab-py.readthedocs.io/en/latest/streaming.html
- Alpaca options order-type limits + OPRA data pricing: https://docs.alpaca.markets/us/docs/options-trading · https://docs.alpaca.markets/docs/real-time-option-data · https://alpaca.markets/data
