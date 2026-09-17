# ENTRY-SLACK — week of Mon Sep 14 2026 to Sun Sep 20 2026. Newest day first; each day under its ===== header; a re-run replaces that day's block (reports.py).

===== Thu Sep 17 2026 =====

# ENTRY SLACK — would crossing the ask have paid?

Measurement only. `execution.entry_slack_pct` is 0 and its activation is BLOCKED: the bot bids the caller's price or better and never chases. This file exists to tell G, every day, what that rule costs and what it saves.

VERDICT — 6 no-fills today; nothing beats today's rule: every slack level from 2% to 10% comes out behind it (-$13 to -$234), and the 95% band on 156 paired orders (-$2.58 .. -$0.49 per order) CLEARS zero

## The population

| | n | note |
|---|---:|---|
| option ORDER IN lines, all time | 222 | every option order the bot has ever sent |
| with a recorded outcome | 199 | a FILLED or NOFILL line after it; the rest were cancelled, edited or never resolved |
| never filled | 34 | the 90-second window expired with the bid unhit — the population this rule is about |
| filled | 165 | where the cost side lives |
| no-fills SCORED | **10** | a real recorded bid/ask within 90s of the order |
| no-fills QUARANTINED | 7 | the tape says the ask was already at or under our bid, so at slack 0 the model contradicts the broker. Counted nowhere |
| no-fills UNSCORED | 17 | no quote at read time. Not estimated, not extrapolated, not counted |
| fills SCORED | 146 of 165 | the cost is only charged where a real ask was recorded |

COVERAGE, said plainly: **10 of the 34 option no-fills can be scored**. 7 are quarantined and 17 have no quote at read time. The benefit side of this question rests on 10 trades; the cost side on 146. They are not measured to the same standard and the table below must be read that way.

`grep -c NOFILL trades.log` says 52. Five of those are POSTCHECK lines about a no-fill; 20 of the remaining 47 are FUTURES (16 MNQ, 4 MGC), which have no ask to cross on this rule. The option population is 34 of 222 ORDER INs (15%), not 52 of 204.

## Slack level → what it buys, what it costs

Exits are the LIVE ratchet, read from `ratchet_tiers.live_spacing()` and never typed in here: born stop -5%, arms at +3%, 5% rungs, the tick and spread floors, the broker's stop-under-the-bid clamp, sold at observed bids, flat at 15:59 ET. Money is per order (qty x 100).

| slack | no-fills rescued | gross from the rescues | fills that would cross | improvement given up | model net | **vs today** |
|---|---|---|---|---|---|---|
| 0% — today's rule | 0 of 10 | +$0 | 119 of 146 | -$386 | -$386 | **baseline** |
| 2% | 0 of 10 | +$0 | 128 of 146 | -$399 | -$399 | **-$13** |
| 3% | 0 of 10 | +$0 | 131 of 146 | -$426 | -$426 | **-$40** |
| 5% | 3 of 10 | +$27 | 140 of 146 | -$518 | -$491 | **-$105** |
| 7.5% | 7 of 10 | -$21 | 145 of 146 | -$632 | -$653 | **-$267** |
| 10% | 10 of 10 | +$17 | 146 of 146 | -$637 | -$620 | **-$234** |

**Read the last column, not the one before it.** The model prices a cross at the recorded ask, and our real fills came in BETTER than that ask — so the slack-0 column is already -$386 against the broker's own prices on 119 of 146 scored fills. That bias is the same at every slack level, so it cancels in the difference and poisons the absolute.

Across ALL 165 filled orders in the record — scored or not — resting at the caller's price filled **+$1313** better than the price we bid, about +$0.08 a contract. That is the thing crossing spends.

## Paired bootstrap against today's rule (same orders, both times)

| slack | n paired orders | mean diff / order | 95% band (4000 resamples) | resamples above zero | verdict |
|---|---|---|---|---|---|
| 2% | 156 | -$0.08 | -$0.15 .. -$0.03 | 0% | real at this sample — and it is on the **LOSS** side |
| 3% | 156 | -$0.26 | -$0.58 .. -$0.06 | 0% | real at this sample — and it is on the **LOSS** side |
| 5% | 156 | -$0.67 | -$1.28 .. -$0.10 | 1% | real at this sample — and it is on the **LOSS** side |
| 7.5% | 156 | -$1.71 | -$2.72 .. -$0.78 | 0% | real at this sample — and it is on the **LOSS** side |
| 10% | 156 | -$1.50 | -$2.58 .. -$0.49 | 0% | real at this sample — and it is on the **LOSS** side |

The band is the 2.5th-97.5th percentile of the resampled MEAN difference, the same method the 9/10 ratchet sweep used. A band containing zero means this sample cannot tell the rules apart, whatever the totals say.

One asymmetry matters more than the band: the 146 fills give the cost side a real sample, while the benefit side has 10 trades. So a band that clears zero here is evidence about the COST of crossing, not proof about its upside.

## Today's no-fills (2026-09-17)

| time | contract | our bid | market at read | status | what crossing would have done | note |
|---|---|---|---|---|---|---|
| 09:39 | SNDK260918C01800000 | $1.20 | 1.15 x 1.25 | scored | 5% at $1.25 -> +$20; 7.5% at $1.25 -> +$20; 10% at $1.25 -> +$20 |  |
| 10:03 | MRNA260918C00165000 | $1.72 | 1.78 x 1.85 | scored | 10% at $1.85 -> +$0 |  |
| 10:14 | SPY260918C00760000 | $2.25 | 2.41 x 2.42 | scored | 10% at $2.42 -> +$12 |  |
| 10:23 | ORCL260925C00160000 | $1.55 | 1.58 x 1.65 | scored | 7.5% at $1.65 -> -$9; 10% at $1.65 -> -$9 |  |
| 10:24 | QQQ260917C00716000 | $1.32 | 1.37 x 1.38 | scored | 5% at $1.38 -> +$7; 7.5% at $1.38 -> +$7; 10% at $1.38 -> +$7 |  |
| 10:29 | QQQ260917C00716000 | $1.32 | 1.39 x 1.40 | scored | 7.5% at $1.40 -> +$0; 10% at $1.40 -> +$0 |  |

## Why the rescues still lost

This is the part the complaint cannot see from the chart. Crossing pays the offer, and the born stop is then clamped one tick under the live BID (Webull 417s a resting stop at or above the bid), so a cross on a wide spread starts with a stop far tighter than -5%. It also moves the +3% arm out of reach: a contract bought 15c higher has to run 15c further before the ratchet locks anything.

| date | contract | our bid | crossed at | best bid after | peak gain | how it ended | exit | P&L |
|---|---|---|---|---|---|---|---|---|
| 2026-09-14 | CRWD260918C00245000 | $2.35 | $2.52 | $2.41 | -4.4% | born stop | $2.38 | -$14 |
| 2026-09-15 | CRWD260918C00240000 | $4.25 | $4.50 | $4.60 | +2.2% | born stop | $4.25 | -$25 |
| 2026-09-15 | CRWD260918C00250000 | $3.50 | $3.65 | $3.80 | +4.1% | first lock | $3.65 | +$0 |
| 2026-09-15 | HOOD260925C00120000 | $1.22 | $1.32 | $1.63 | +23.5% | ratchet rung | $1.58 | +$26 |
| 2026-09-17 | SNDK260918C01800000 | $1.20 | $1.25 | $1.60 | +28.0% | ratchet rung | $1.45 | +$20 |
| 2026-09-17 | MRNA260918C00165000 | $1.72 | $1.85 | $1.91 | +3.2% | first lock | $1.85 | +$0 |
| 2026-09-17 | SPY260918C00760000 | $2.25 | $2.42 | $2.64 | +9.1% | ratchet rung | $2.54 | +$12 |
| 2026-09-17 | ORCL260925C00160000 | $1.55 | $1.65 | $1.64 | -0.6% | born stop | $1.56 | -$9 |
| 2026-09-17 | QQQ260917C00716000 | $1.32 | $1.38 | $1.52 | +10.1% | ratchet rung | $1.45 | +$7 |
| 2026-09-17 | QQQ260917C00716000 | $1.32 | $1.40 | $1.45 | +3.6% | first lock | $1.40 | +$0 |

## Quarantined — the tape disagrees with the broker

These came back with a recorded ask at or UNDER the price we bid, so at slack 0 the model says they filled and the broker says they did not. That is a real disagreement — a different venue's offer, or (the August orders were qty 5) more size wanted than the offer held — and it means the row cannot answer this question. None of them is counted anywhere above, in either direction.

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

- 156 scored orders cannot settle a trading rule. They can rule things out, and they can price a cost.
- The benefit side is 10 trades. Nothing here is a verdict on the upside of crossing; it is a verdict on what the record can see.
- The quote at read time is the nearest recorded print inside 90s, not a tick-by-tick book. A price that lived between two prints is invisible here.
- Most feeds carry no SIZE, so an ask with one contract behind it looks exactly like an ask with fifty. The August orders were qty 5, which is the likeliest reason for the quarantine above.
- The forward replay has no slippage, no queue and no partial fills: the entry pays the offer and the exit prints at the bid that broke the stop. Real life is worse.
- The anchor is the price the bot BID (the ORDER IN line) — the caller's price or better after the tick floor, not the caller's raw post.
- Coverage is stated, never inferred. An unscored order is absent from every total above, in both directions.

Built by `reference/entry_slack_replay.py` from `trades.log` (population) and `tape.py` (quotes: alert_tape, quote_shadow, option_tape, databento_tape, missed_tape, greeks_tape). The rule is `entry_slack.decide()`; the exits are `reference/ratchet_replay_tape.simulate()` on `ratchet_tiers.live_spacing()`. Per-order rows: `reference/ENTRY-SLACK-REPLAY.csv`.

===== Wed Sep 16 2026 =====

# ENTRY SLACK — would crossing the ask have paid?

Measurement only. `execution.entry_slack_pct` is 0 and its activation is BLOCKED: the bot bids the caller's price or better and never chases. This file exists to tell G, every day, what that rule costs and what it saves.

VERDICT — 0 no-fills today; nothing beats today's rule: every slack level from 2% to 10% comes out behind it (-$13 to -$266), and the 95% band on 140 paired orders (-$3.24 .. -$0.74 per order) CLEARS zero

## The population

| | n | note |
|---|---:|---|
| option ORDER IN lines, all time | 206 | every option order the bot has ever sent |
| with a recorded outcome | 183 | a FILLED or NOFILL line after it; the rest were cancelled, edited or never resolved |
| never filled | 28 | the 90-second window expired with the bid unhit — the population this rule is about |
| filled | 155 | where the cost side lives |
| no-fills SCORED | **4** | a real recorded bid/ask within 90s of the order |
| no-fills QUARANTINED | 7 | the tape says the ask was already at or under our bid, so at slack 0 the model contradicts the broker. Counted nowhere |
| no-fills UNSCORED | 17 | no quote at read time. Not estimated, not extrapolated, not counted |
| fills SCORED | 136 of 155 | the cost is only charged where a real ask was recorded |

COVERAGE, said plainly: **4 of the 28 option no-fills can be scored**. 7 are quarantined and 17 have no quote at read time. The benefit side of this question rests on 4 trades; the cost side on 136. They are not measured to the same standard and the table below must be read that way.

`grep -c NOFILL trades.log` says 52. Five of those are POSTCHECK lines about a no-fill; 20 of the remaining 47 are FUTURES (16 MNQ, 4 MGC), which have no ask to cross on this rule. The option population is 28 of 206 ORDER INs (14%), not 52 of 204.

## Slack level → what it buys, what it costs

Exits are the LIVE ratchet, read from `ratchet_tiers.live_spacing()` and never typed in here: born stop -10%, arms at +10%, 10% rungs, the tick and spread floors, the broker's stop-under-the-bid clamp, sold at observed bids, flat at 15:59 ET. Money is per order (qty x 100).

| slack | no-fills rescued | gross from the rescues | fills that would cross | improvement given up | model net | **vs today** |
|---|---|---|---|---|---|---|
| 0% — today's rule | 0 of 4 | +$0 | 113 of 136 | -$380 | -$380 | **baseline** |
| 2% | 0 of 4 | +$0 | 122 of 136 | -$393 | -$393 | **-$13** |
| 3% | 0 of 4 | +$0 | 125 of 136 | -$420 | -$420 | **-$40** |
| 5% | 1 of 4 | -$35 | 130 of 136 | -$472 | -$507 | **-$127** |
| 7.5% | 3 of 4 | -$80 | 135 of 136 | -$586 | -$666 | **-$286** |
| 10% | 4 of 4 | -$55 | 136 of 136 | -$591 | -$646 | **-$266** |

**Read the last column, not the one before it.** The model prices a cross at the recorded ask, and our real fills came in BETTER than that ask — so the slack-0 column is already -$380 against the broker's own prices on 113 of 136 scored fills. That bias is the same at every slack level, so it cancels in the difference and poisons the absolute.

Across ALL 155 filled orders in the record — scored or not — resting at the caller's price filled **+$1292** better than the price we bid, about +$0.08 a contract. That is the thing crossing spends.

## Paired bootstrap against today's rule (same orders, both times)

| slack | n paired orders | mean diff / order | 95% band (4000 resamples) | resamples above zero | verdict |
|---|---|---|---|---|---|
| 2% | 140 | -$0.09 | -$0.16 .. -$0.03 | 0% | real at this sample — and it is on the **LOSS** side |
| 3% | 140 | -$0.29 | -$0.63 .. -$0.07 | 0% | real at this sample — and it is on the **LOSS** side |
| 5% | 140 | -$0.91 | -$1.71 .. -$0.31 | 0% | real at this sample — and it is on the **LOSS** side |
| 7.5% | 140 | -$2.04 | -$3.36 .. -$0.96 | 0% | real at this sample — and it is on the **LOSS** side |
| 10% | 140 | -$1.90 | -$3.24 .. -$0.74 | 0% | real at this sample — and it is on the **LOSS** side |

The band is the 2.5th-97.5th percentile of the resampled MEAN difference, the same method the 9/10 ratchet sweep used. A band containing zero means this sample cannot tell the rules apart, whatever the totals say.

One asymmetry matters more than the band: the 136 fills give the cost side a real sample, while the benefit side has 4 trades. So a band that clears zero here is evidence about the COST of crossing, not proof about its upside.

## Today's no-fills (2026-09-16)

None.

## Why the rescues still lost

This is the part the complaint cannot see from the chart. Crossing pays the offer, and the born stop is then clamped one tick under the live BID (Webull 417s a resting stop at or above the bid), so a cross on a wide spread starts with a stop far tighter than -10%. It also moves the +10% arm out of reach: a contract bought 15c higher has to run 15c further before the ratchet locks anything.

| date | contract | our bid | crossed at | best bid after | peak gain | how it ended | exit | P&L |
|---|---|---|---|---|---|---|---|---|
| 2026-09-14 | CRWD260918C00245000 | $2.35 | $2.52 | $2.82 | +11.9% | first lock | $2.52 | +$0 |
| 2026-09-15 | CRWD260918C00240000 | $4.25 | $4.50 | $4.60 | +2.2% | born stop | $4.05 | -$45 |
| 2026-09-15 | CRWD260918C00250000 | $3.50 | $3.65 | $3.80 | +4.1% | born stop | $3.30 | -$35 |
| 2026-09-15 | HOOD260925C00120000 | $1.22 | $1.32 | $1.75 | +32.6% | ratchet rung | $1.57 | +$25 |

## Quarantined — the tape disagrees with the broker

These came back with a recorded ask at or UNDER the price we bid, so at slack 0 the model says they filled and the broker says they did not. That is a real disagreement — a different venue's offer, or (the August orders were qty 5) more size wanted than the offer held — and it means the row cannot answer this question. None of them is counted anywhere above, in either direction.

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

- 140 scored orders cannot settle a trading rule. They can rule things out, and they can price a cost.
- The benefit side is 4 trades. Nothing here is a verdict on the upside of crossing; it is a verdict on what the record can see.
- The quote at read time is the nearest recorded print inside 90s, not a tick-by-tick book. A price that lived between two prints is invisible here.
- Most feeds carry no SIZE, so an ask with one contract behind it looks exactly like an ask with fifty. The August orders were qty 5, which is the likeliest reason for the quarantine above.
- The forward replay has no slippage, no queue and no partial fills: the entry pays the offer and the exit prints at the bid that broke the stop. Real life is worse.
- The anchor is the price the bot BID (the ORDER IN line) — the caller's price or better after the tick floor, not the caller's raw post.
- Coverage is stated, never inferred. An unscored order is absent from every total above, in both directions.

Built by `reference/entry_slack_replay.py` from `trades.log` (population) and `tape.py` (quotes: alert_tape, quote_shadow, option_tape, databento_tape, missed_tape, greeks_tape). The rule is `entry_slack.decide()`; the exits are `reference/ratchet_replay_tape.simulate()` on `ratchet_tiers.live_spacing()`. Per-order rows: `reference/ENTRY-SLACK-REPLAY.csv`.

===== Tue Sep 15 2026 =====

# ENTRY SLACK — would crossing the ask have paid?

Measurement only. `execution.entry_slack_pct` is 0 and its activation is BLOCKED: the bot bids the caller's price or better and never chases. This file exists to tell G, every day, what that rule costs and what it saves.

VERDICT — 3 no-fills today; nothing beats today's rule: every slack level from 2% to 10% comes out behind it (-$13 to -$266), and the 95% band on 137 paired orders (-$3.37 .. -$0.77 per order) CLEARS zero

## The population

| | n | note |
|---|---:|---|
| option ORDER IN lines, all time | 203 | every option order the bot has ever sent |
| with a recorded outcome | 180 | a FILLED or NOFILL line after it; the rest were cancelled, edited or never resolved |
| never filled | 28 | the 90-second window expired with the bid unhit — the population this rule is about |
| filled | 152 | where the cost side lives |
| no-fills SCORED | **4** | a real recorded bid/ask within 90s of the order |
| no-fills QUARANTINED | 7 | the tape says the ask was already at or under our bid, so at slack 0 the model contradicts the broker. Counted nowhere |
| no-fills UNSCORED | 17 | no quote at read time. Not estimated, not extrapolated, not counted |
| fills SCORED | 133 of 152 | the cost is only charged where a real ask was recorded |

COVERAGE, said plainly: **4 of the 28 option no-fills can be scored**. 7 are quarantined and 17 have no quote at read time. The benefit side of this question rests on 4 trades; the cost side on 133. They are not measured to the same standard and the table below must be read that way.

`grep -c NOFILL trades.log` says 52. Five of those are POSTCHECK lines about a no-fill; 20 of the remaining 47 are FUTURES (16 MNQ, 4 MGC), which have no ask to cross on this rule. The option population is 28 of 203 ORDER INs (14%), not 52 of 204.

## Slack level → what it buys, what it costs

Exits are the LIVE ratchet, read from `ratchet_tiers.live_spacing()` and never typed in here: born stop -10%, arms at +10%, 10% rungs, the tick and spread floors, the broker's stop-under-the-bid clamp, sold at observed bids, flat at 15:59 ET. Money is per order (qty x 100).

| slack | no-fills rescued | gross from the rescues | fills that would cross | improvement given up | model net | **vs today** |
|---|---|---|---|---|---|---|
| 0% — today's rule | 0 of 4 | +$0 | 110 of 133 | -$374 | -$374 | **baseline** |
| 2% | 0 of 4 | +$0 | 119 of 133 | -$387 | -$387 | **-$13** |
| 3% | 0 of 4 | +$0 | 122 of 133 | -$414 | -$414 | **-$40** |
| 5% | 1 of 4 | -$35 | 127 of 133 | -$466 | -$501 | **-$127** |
| 7.5% | 3 of 4 | -$80 | 132 of 133 | -$580 | -$660 | **-$286** |
| 10% | 4 of 4 | -$55 | 133 of 133 | -$585 | -$640 | **-$266** |

**Read the last column, not the one before it.** The model prices a cross at the recorded ask, and our real fills came in BETTER than that ask — so the slack-0 column is already -$374 against the broker's own prices on 110 of 133 scored fills. That bias is the same at every slack level, so it cancels in the difference and poisons the absolute.

Across ALL 152 filled orders in the record — scored or not — resting at the caller's price filled **+$1247** better than the price we bid, about +$0.08 a contract. That is the thing crossing spends.

## Paired bootstrap against today's rule (same orders, both times)

| slack | n paired orders | mean diff / order | 95% band (4000 resamples) | resamples above zero | verdict |
|---|---|---|---|---|---|
| 2% | 137 | -$0.09 | -$0.17 .. -$0.04 | 0% | real at this sample — and it is on the **LOSS** side |
| 3% | 137 | -$0.29 | -$0.64 .. -$0.07 | 0% | real at this sample — and it is on the **LOSS** side |
| 5% | 137 | -$0.93 | -$1.72 .. -$0.33 | 0% | real at this sample — and it is on the **LOSS** side |
| 7.5% | 137 | -$2.09 | -$3.45 .. -$1.01 | 0% | real at this sample — and it is on the **LOSS** side |
| 10% | 137 | -$1.94 | -$3.37 .. -$0.77 | 0% | real at this sample — and it is on the **LOSS** side |

The band is the 2.5th-97.5th percentile of the resampled MEAN difference, the same method the 9/10 ratchet sweep used. A band containing zero means this sample cannot tell the rules apart, whatever the totals say.

One asymmetry matters more than the band: the 133 fills give the cost side a real sample, while the benefit side has 4 trades. So a band that clears zero here is evidence about the COST of crossing, not proof about its upside.

## Today's no-fills (2026-09-15)

| time | contract | our bid | market at read | status | what crossing would have done | note |
|---|---|---|---|---|---|---|
| 10:14 | CRWD260918C00240000 | $4.25 | 4.40 x 4.50 | scored | 7.5% at $4.50 -> -$45; 10% at $4.50 -> -$45 |  |
| 12:50 | CRWD260918C00250000 | $3.50 | 3.55 x 3.65 | scored | 5% at $3.65 -> -$35; 7.5% at $3.65 -> -$35; 10% at $3.65 -> -$35 |  |
| 14:57 | HOOD260925C00120000 | $1.22 | 1.28 x 1.32 | scored | 10% at $1.32 -> +$25 |  |

## Why the rescues still lost

This is the part the complaint cannot see from the chart. Crossing pays the offer, and the born stop is then clamped one tick under the live BID (Webull 417s a resting stop at or above the bid), so a cross on a wide spread starts with a stop far tighter than -10%. It also moves the +10% arm out of reach: a contract bought 15c higher has to run 15c further before the ratchet locks anything.

| date | contract | our bid | crossed at | best bid after | peak gain | how it ended | exit | P&L |
|---|---|---|---|---|---|---|---|---|
| 2026-09-14 | CRWD260918C00245000 | $2.35 | $2.52 | $2.82 | +11.9% | first lock | $2.52 | +$0 |
| 2026-09-15 | CRWD260918C00240000 | $4.25 | $4.50 | $4.60 | +2.2% | born stop | $4.05 | -$45 |
| 2026-09-15 | CRWD260918C00250000 | $3.50 | $3.65 | $3.80 | +4.1% | born stop | $3.30 | -$35 |
| 2026-09-15 | HOOD260925C00120000 | $1.22 | $1.32 | $1.75 | +32.6% | ratchet rung | $1.57 | +$25 |

## Quarantined — the tape disagrees with the broker

These came back with a recorded ask at or UNDER the price we bid, so at slack 0 the model says they filled and the broker says they did not. That is a real disagreement — a different venue's offer, or (the August orders were qty 5) more size wanted than the offer held — and it means the row cannot answer this question. None of them is counted anywhere above, in either direction.

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

- 137 scored orders cannot settle a trading rule. They can rule things out, and they can price a cost.
- The benefit side is 4 trades. Nothing here is a verdict on the upside of crossing; it is a verdict on what the record can see.
- The quote at read time is the nearest recorded print inside 90s, not a tick-by-tick book. A price that lived between two prints is invisible here.
- Most feeds carry no SIZE, so an ask with one contract behind it looks exactly like an ask with fifty. The August orders were qty 5, which is the likeliest reason for the quarantine above.
- The forward replay has no slippage, no queue and no partial fills: the entry pays the offer and the exit prints at the bid that broke the stop. Real life is worse.
- The anchor is the price the bot BID (the ORDER IN line) — the caller's price or better after the tick floor, not the caller's raw post.
- Coverage is stated, never inferred. An unscored order is absent from every total above, in both directions.

Built by `reference/entry_slack_replay.py` from `trades.log` (population) and `tape.py` (quotes: alert_tape, quote_shadow, option_tape, databento_tape, missed_tape, greeks_tape). The rule is `entry_slack.decide()`; the exits are `reference/ratchet_replay_tape.simulate()` on `ratchet_tiers.live_spacing()`. Per-order rows: `reference/ENTRY-SLACK-REPLAY.csv`.
