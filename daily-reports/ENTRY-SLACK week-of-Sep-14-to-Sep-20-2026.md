# ENTRY-SLACK — week of Mon Sep 14 2026 to Sun Sep 20 2026. Newest day first; each day under its ===== header; a re-run replaces that day's block (reports.py).

===== Tue Sep 15 2026 =====

# ENTRY SLACK — would crossing the ask have paid?

Measurement only. `execution.entry_slack_pct` is 0 and its activation is BLOCKED: the bot bids the caller's price or better and never chases. This file exists to tell G, every day, what that rule costs and what it saves.

VERDICT — 2 no-fills today; best slack 0% nets -$367 all-time on 0 scored orders; 95% band n/a SPANS zero — undecidable

## The population

| | n | note |
|---|---:|---|
| Option ORDER IN lines | 178 | the orders this rule could ever have changed |
| never filled | 27 | the 90-second window expired with the bid unhit |
| filled | 151 | every one of these is where the cost side lives |
| no-fills SCORED | 3 | a real recorded bid/ask within 90s of the order |
| no-fills QUARANTINED | 7 | the tape says the ask was already at or under our bid — it disagrees with the broker, so it cannot score this |
| no-fills UNSCORED | 17 | no quote at read time. Not estimated, not extrapolated, not counted |
| fills SCORED | 132 of 151 | the cost side is only charged where a real ask was recorded |

`grep -c NOFILL trades.log` says 52. Five are POSTCHECK lines about a no-fill; 20 of the remaining 47 are FUTURES (16 MNQ, 4 MGC), which have no ask to cross on this rule. The option population is 27.

## Slack level → what it buys, what it costs

Exits are the LIVE ratchet read from `ratchet_tiers.live_spacing()`: born stop -10%, arms at +10%, 10% rungs, sold at observed bids, flat at 15:59 ET. Money is per order (qty x 100).

| slack | no-fills rescued | gross from rescues | fills that would cross | improvement given up | NET |
|---|---|---|---|---|---|
| 0% (today's rule) | 0 of 3 | +$0 | 109 of 132 | -$367 | **-$367** |
| 2% | 0 of 3 | +$0 | 118 of 132 | -$380 | **-$380** |
| 3% | 0 of 3 | +$0 | 121 of 132 | -$407 | **-$407** |
| 5% | 1 of 3 | -$35 | 126 of 132 | -$459 | **-$494** |
| 7.5% | 3 of 3 | -$80 | 131 of 132 | -$573 | **-$653** |
| 10% | 3 of 3 | -$80 | 132 of 132 | -$578 | **-$658** |

Across ALL 151 filled orders in the record — scored or not — resting at the caller's price earned **+$1235** better than the price we bid. That is the thing crossing spends.

## Paired bootstrap against slack 0 (same orders, both times)

| slack | n | mean diff / order | 95% band (4000 resamples) | resamples above zero | verdict |
|---|---|---|---|---|---|
| 2% | 135 | -$0 | -$0 .. -$0 | 0% | real at this sample |
| 3% | 135 | -$0 | -$1 .. -$0 | 0% | real at this sample |
| 5% | 135 | -$1 | -$2 .. -$0 | 0% | real at this sample |
| 7.5% | 135 | -$2 | -$3 .. -$1 | 0% | real at this sample |
| 10% | 135 | -$2 | -$3 .. -$1 | 0% | real at this sample |

The band is the 2.5th-97.5th percentile of the resampled MEAN difference. A band containing zero means this sample cannot tell the rules apart, whatever the totals say — and with 135 scored orders it mostly will.

## Today's no-fills (2026-09-15)

| time | contract | our bid | market at read | status | would cross at | note |
|---|---|---|---|---|---|---|
| 10:14 | CRWD260918C00240000 | $4.25 | 4.40 x 4.50 | scored | 7.5%, 10% |  |
| 12:50 | CRWD260918C00250000 | $3.50 | 3.55 x 3.65 | scored | 5%, 7.5%, 10% |  |

## Quarantined — the tape disagrees with the broker

These rows came back with a recorded ask at or UNDER the price we bid, so at slack 0 the model says they filled and the broker says they did not. That is a real disagreement (a different venue's offer, or — on the August orders, which were qty 5 — more size at the offer than the tape shows), and it means the row cannot answer this question. None of them is counted anywhere above.

| date | contract | our bid | recorded market | qty |
|---|---|---|---|---|
| 2026-08-05 | AAPL260807C00315000 | $1.13 | 1.09 x 1.10 | 5 |
| 2026-08-11 | GOOGL260814C00360000 | $2.10 | 2.00 x 2.03 | 1 |
| 2026-08-11 | IBM260814C00240000 | $3.32 | 3.05 x 3.20 | 1 |
| 2026-08-11 | BAC260821C00064000 | $0.88 | 0.84 x 0.85 | 1 |
| 2026-08-11 | NVDA260814C00220000 | $2.91 | 2.73 x 2.76 | 1 |
| 2026-08-12 | AMZN260814P00270000 | $2.56 | 2.45 x 2.48 | 1 |
| 2026-08-12 | QQQ260814P00720000 | $1.93 | 1.89 x 1.91 | 1 |

## Unscored no-fills — never estimated

| date | contract | our bid | why |
|---|---|---|---|
| 2026-08-05 | MSFT260807P00480000 | $2.15 | no tape ever quoted this contract |
| 2026-08-05 | SPCX260807P00090000 | $0.30 | no tape ever quoted this contract |
| 2026-08-14 | SPY260817C00775000 | $3.14 | no tape ever quoted this contract |
| 2026-08-17 | INTC260828C00115000 | $1.77 | no recorded bid/ask within 90s of the order |
| 2026-08-18 | PLTR260821C00172500 | $3.35 | no tape ever quoted this contract |
| 2026-08-18 | QQQ260818P00718000 | $1.22 | no recorded bid/ask within 90s of the order |
| 2026-08-18 | INTC260819P00097000 | $1.51 | no recorded bid/ask within 90s of the order |
| 2026-08-18 | SPY260819P00769000 | $2.40 | no recorded bid/ask within 90s of the order |
| 2026-08-18 | GLD260831C00405000 | $2.45 | no tape ever quoted this contract |
| 2026-08-19 | SOFI260828C00018000 | $0.51 | no recorded bid/ask within 90s of the order |
| 2026-08-19 | JPM260828C00385000 | $0.17 | no tape ever quoted this contract |
| 2026-08-20 | M260918C00025000 | $0.55 | no recorded bid/ask within 90s of the order |
| 2026-08-24 | SNAP261016C00006000 | $0.31 | no tape ever quoted this contract |
| 2026-09-02 | IWM260902C00294000 | $0.18 | no tape ever quoted this contract |
| 2026-09-03 | IWM260904C00294000 | $1.24 | no tape ever quoted this contract |
| 2026-09-03 | IBIT260918C00047000 | $1.34 | no tape ever quoted this contract |
| 2026-09-10 | SPCX260911C00155000 | $1.95 | no tape ever quoted this contract |

## Honest limits

- 135 scored orders cannot settle a trading rule. They can rule things out.
- The quote at read time is the nearest recorded print inside 90s, not a tick-by-tick book. A price that existed between two prints is invisible here.
- The tapes carry no SIZE on most feeds, so an ask with one contract behind it looks exactly like an ask with fifty. The August orders were qty 5.
- The forward replay has no slippage, no queue and no partial fills: the entry pays the offer and the exit prints at the bid that broke the stop. Real life is worse.
- The anchor is the price the bot BID (the ORDER IN line), which is the caller's price or better after the tick floor — not the caller's raw post.
- Coverage is stated, never inferred. An unscored order is absent from every total above, in both directions.

Built by `reference/entry_slack_replay.py` from `trades.log` (population) and `tape.py` (quotes: alert_tape, quote_shadow, option_tape, databento_tape, missed_tape, greeks_tape). The rule is `entry_slack.decide()`; the exits are `reference/ratchet_replay_tape.simulate()` on `ratchet_tiers.live_spacing()`.
