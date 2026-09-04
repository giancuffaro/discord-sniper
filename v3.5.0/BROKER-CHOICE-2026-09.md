# Which broker? Webull vs Schwab vs Tradier — 9/3/26

Written after G asked: *"can you build so I can plug in a Schwab, or which is
better of both? think in the aspect of data rate and pricing as well."*

All figures researched 9/3/26 against current sources (linked at the bottom).
Nothing here is a recommendation to trade — it's a capability and cost
comparison for the machine.

---

## The scoreboard

| | **Webull** (today) | **Schwab** | **Tradier** |
|---|---|---|---|
| Options commission | **$0** | $0.65/contract | $0.35 (Pro) / $0.10 (Pro Plus) |
| Platform fee | $0 | $0 | $10/mo Pro, $35/mo Pro Plus |
| **Conditional orders on options** | **None.** OTO/OCO/OTOCO are stock-only | **Yes** — OTO, OCO, OTOCO + trigger source (STANDARD/BID/ASK/LAST/MARK) | **Yes** — oto, oco, otoco |
| **Option quote streaming** | **None.** HTTP only, 60 calls/min, 20 symbols per call | **Yes**, included | **Yes**, included, free with the account |
| Underlying (stock) streaming | Yes (MQTT) | Yes | Yes |
| Request rate | Per-endpoint; option snapshot 60/min | ~120/min overall | Not a published hard cap |
| **Unattended auth** | App key + secret, **stable** | ⚠️ **Refresh token dies every 7 days with no programmatic renewal** | Simple token |
| Order types on options | LIMIT, STOP_LOSS, STOP_LOSS_LIMIT. No MARKET | Full | Full |

## What it would actually cost him

He trades **1 contract per entry**. A round trip is 2 contract-sides.
At a realistic 5 round trips/day × 20 days = 200 contract-sides/month:

| | Monthly |
|---|---|
| Webull | **$0** |
| Tradier Pro Plus | $35 + (200 × $0.10) = **~$55** |
| Tradier Pro | $10 + (200 × $0.35) = **~$80** |
| Schwab | 200 × $0.65 = **~$130** |

Against an account running ~$500 of buying power, $55–130/month is a real
drag. This is the single biggest argument for staying on Webull.

## The two things a move would actually buy

1. **Streaming OPTION quotes — the bigger prize, and NOT what he asked about.**
   Today the entire ratchet runs off `quote_bus`, one batched HTTP call per
   second, because Webull has no option streaming at any price. Every stop
   move, every anti-clip decision, every watchdog trigger is working from a
   picture up to a second old. On Schwab or Tradier the ratchet becomes
   tick-accurate. That is worth more than the entry trigger.
2. **A real broker-side conditional entry.** "When SPY touches 761, submit
   the limit buy" would live at the broker instead of in our poll loop.
   Removes the last ~250ms of our own latency and survives the PC dying.

## Why NOT Schwab, specifically

The **7-day refresh token** is close to disqualifying for an unattended
money machine. Schwab's OAuth refresh token expires after 7 days and there
is no way to renew it programmatically — a human has to complete a browser
login. If the bot is running continuously it can keep rotating, but any
outage longer than a week (or a laptop reinstall, or a holiday) means the
machine is dead until G sits down and logs in through a browser. On top of
that it is the most expensive of the three per contract, and buys nothing
Tradier doesn't also provide.

## Recommendation

**If he moves at all, move to Tradier — not Schwab.** Cheaper per contract,
same conditional-order capability, option streaming included, and no
7-day auth cliff.

**But do not migrate.** Build a broker ADAPTER so brokers are pluggable and
run Tradier ALONGSIDE Webull: same signals, same ratchet, orders routed per
room. Prove the fills and the streaming on a small Tradier account for a
couple of weeks with real numbers in the journal, then decide with evidence
instead of a guess. If Tradier's fills are worse, or the commissions eat
more than the tighter ratchet saves, nothing has been lost.

The work is a `broker.py` interface with the ~12 methods `positions.py`
already calls (`positions`, `place_stop`, `replace_stop`, `cancel`, `sell`,
`ask_bid`, `ask_bid_many`, `stock_price`, `order_status`, `buying_power`,
`last_sell_fill`, `futures_positions`). `webull_options.py` becomes the
first implementation of it, `tradier.py` the second. Nothing above the
adapter — parser, guards, ratchet, watchdog, journal — changes at all.

## Sources
- Schwab pricing (options $0.65/contract): https://www.schwab.com/legal/schwab-pricing-guide-for-individual-investors
- Schwab API rate limits (~120/min): https://grokipedia.com/page/Schwab_Trader_API
- Schwab streaming: https://schwab-py.readthedocs.io/en/latest/streaming.html
- Schwab 7-day refresh token, no programmatic renewal: https://schwab-py.readthedocs.io/en/latest/auth.html and https://github.com/alexgolec/schwab-py/issues/100
- Schwab OTO/OCO/OTOCO + stopType: https://raw.githubusercontent.com/alexgolec/schwab-py/main/schwab/orders/common.py
- Tradier pricing ($10 Pro / $35 Pro Plus; $0.35 / $0.10 per index-option contract): https://tradier.com/individuals/pricing
- Tradier streaming + market data included: https://docs.tradier.com/docs/streaming-data and https://docs.tradier.com/docs/market-data
- Tradier oto/oco/otoco: https://docs.tradier.com/docs/trading.md
- Webull option order types / no OTOCO on options / no option streaming: see v3.5.0/OPTIONS-BROKER-REFERENCE.md sections A2–A3
