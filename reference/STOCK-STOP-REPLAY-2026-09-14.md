# Managing off the STOCK instead of the premium — replay

G's idea: "alert -> round-number pullback -> arm with a $0.25 stock stop; +$0.25 in favor -> stop to breakeven; then ratchet every +$0.15 from there", $1.00 on the Mag 7. This replays it against the live pullback stop+target rule and against our premium 5/3/5 ratchet, on the SAME pullback entries and the same real quotes. Nothing changed; no order was placed.

Built by `reference/stock_stop_replay.py`. Stock leg: real 1-second Databento bars in `bars/stock/`. Option leg: Databento OPRA (`databento_tape_clean.csv`, ~1 quote/second) where it exists, else the Webull tapes. Entries and levels come from the live `pullback.py`.

Stock bars: Databento quoted **$0.1538** for the twenty symbol-days asked for (2026-09-11 and 2026-09-14). The 9/11 half ($0.0732 quoted) delivered and is cached; the 9/14 half ($0.0805 quoted) was refused with a 403 before any data was returned. Everything from 2026-08-11 to 2026-09-08 was already in `bars/stock/` from the 9/9 pullback study and cost nothing.

## The rules

| Variant | Stock stop | Arms at | Then | SPY/QQQ rung | Mag 7 rung |
|---|---|---|---|---|---|
| **S1** | 0.25 / 1.00 | +0.25 / +1.00 | stop -> the level (breakeven) | +0.15 | +0.60 |
| **S1b** | 0.25 / 1.00 | +0.25 / +1.00 | stop -> the level (breakeven) | +0.15 | +0.50 |
| **S2** | 0.35 / 1.50 | +0.35 / +1.50 | stop -> the level (breakeven) | +0.15 | +0.60 |
| **S3** | 0.45 / 2.00 | +0.45 / +2.00 | stop -> the level (breakeven) | +0.15 | +0.60 |
| **P0** (live) | 0.25 / 1.00 | never | fixed target +0.50 / +2.50, no ratchet | — | — |
| **A** (live premium) | -5% of the premium | +3% premium | stop -> breakeven | +5% premium | +5% premium |
| **H** (Claude's) | 0.25 / 1.00 until the premium is +3% | then A | A's breakeven | +5% premium | +5% premium |

Every stop distance and every fixed target above is read from the live `pullback.UNDERLYING_EXITS`; the premium ladder is read from the live `ratchet_tiers.TIERS` and `settings.json`. Nothing is typed in twice.

## Side by side — same pullback entries, same paths

| Variant | n | Gross $ | Win % | Avg/trade | Median hold | stop | BE | rung | target | close |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **S1** G's rule: stop/arm 0.25, rung 0.15 (Mag 7 1.00/0.60) | 45 | -299 | 24% | -6.64 | 3m 33s | 24 | 9 | 11 | 0 | 1 |
| **S1b** S1 with the rounder Mag 7 rung 0.50 | 45 | -287 | 24% | -6.38 | 3m 33s | 24 | 7 | 13 | 0 | 1 |
| **S2** stop/arm 0.35 (Mag 7 1.50), rungs unchanged | 45 | -512 | 24% | -11.38 | 4m 12s | 25 | 6 | 11 | 0 | 3 |
| **S3** stop/arm 0.45 (Mag 7 2.00), rungs unchanged | 45 | -458 | 24% | -10.18 | 6m 31s | 24 | 4 | 12 | 0 | 5 |
| **P0** LIVE pullback stock exit: fixed stop + fixed target, no ratchet | 45 | -379 | 24% | -8.42 | 3m 33s | 31 | 0 | 0 | 13 | 1 |
| **A** OUR PREMIUM 5/3/5 ratchet on the same entry | 45 | -594 | 11% | -13.20 | 22s | 30 | 9 | 5 | 0 | 1 |
| **H** HYBRID (Claude's suggestion): S1 stock stop, then premium 5/3/5 at +3% | 45 | -483 | 20% | -10.73 | 1m 44s | 21 | 14 | 9 | 0 | 1 |

Webull charges $0 commission on options, so net = gross.

## Paired bootstrap against A, 4000 resamples

| Variant | Mean difference / trade | 95% band | Resamples above zero | Can this sample decide? |
|---|---:|---|---:|---|
| S1 vs A | +6.56 | -3.13 .. +18.93 | 89% | no — the band spans zero |
| S1b vs A | +6.82 | -3.09 .. +19.27 | 89% | no — the band spans zero |
| S2 vs A | +1.82 | -9.07 .. +13.82 | 61% | no — the band spans zero |
| S3 vs A | +3.02 | -10.07 .. +17.89 | 66% | no — the band spans zero |
| P0 vs A | +4.78 | -5.38 .. +15.89 | 81% | no — the band spans zero |
| H vs A | +2.47 | -4.40 .. +10.40 | 73% | no — the band spans zero |

## The entry question, kept separate

- Alerts where BOTH entries exist: **40**. Same exit rule (A) on each: take-the-alert **-643**, pullback **-587**.
- Paired mean difference (pullback minus take-it): **+1.40**, 95% band **-3.82 .. +7.20**, the band spans zero so this sample cannot decide it.
- Alerts the pullback SKIPPED that take-it would have entered: **22**. A skipped trade is $0, not a loss.
- The $1 level itself stays settled by the 9/9 study (`reference/PULLBACK-LEVELS.md`, 65 paired trades). This does not reopen it.

## What the option tape's lag costs

A stock rule fires on the stock's clock; the option can only be sold at the next quote the tape holds.

- Median lag from fire to the option quote used: **0s**; mean **7.2s**; worst **124s**. (244 exits measured.)
- Exits where the lag was over a second: **5**. On those the bid actually used differs from the last bid before the fire by **-7.00 per contract** on average — that is what the gap costs.
- Exits where the option tape simply ENDED before the rule fired: **71**. Those have no lag to measure and are marked in the CSV (`tape_ended_first`); their exit is the last bid the tape holds.
- On the OPRA sample the tape is ~1 quote/second, so the lag is essentially zero. It is the Webull sweep days that pay.

## Named cases

- **QQQ260914C00708000** — Skyy's 0DTE that the caller rode to +423%. **Not measurable here**: it is a 2026-09-14 alert, and that session's per-second stock bars are still embargoed by Databento
- **MSFT260914C00505000** — the bot's fastest stop-out of 9/14. **Not measurable here**: it is a 2026-09-14 alert, and that session's per-second stock bars are still embargoed by Databento
- **QQQ260914C00713000** — 0.24 -> 0.22 in seconds. **Not measurable here**: it is a 2026-09-14 alert, and that session's per-second stock bars are still embargoed by Databento
- **CRWD260918C00245000** — MuggZone's CRWD. **Not measurable here**: CRWD is not one of the ten symbols this study covers (its stock leg was never bought)
- **QQQ260914P00705000** — Vero's QQQ 705P. **Not measurable here**: it is a 2026-09-14 alert, and that session's per-second stock bars are still embargoed by Databento
- **QQQ260914P00704000** — Demon's QQQ 704P. **Not measurable here**: it is a 2026-09-14 alert, and that session's per-second stock bars are still embargoed by Databento
- **TSLA260918C00357500** — Platinum ei-alerts TSLA 357.5C. **Not measurable here**: it is a 2026-09-14 alert, and that session's per-second stock bars are still embargoed by Databento
- **TSLA260918P00357500** — Platinum nitro TSLA 357.5P. **Not measurable here**: it is a 2026-09-14 alert, and that session's per-second stock bars are still embargoed by Databento

## Every replayed trade

| Day | Time | Room | Contract | Touch level | Entry | Stock best | Option max bid | S1 $ | S1b $ | S2 $ | S3 $ | P0 $ | A $ | H $ |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 08-12 | 09:41 | ZT scalps | META260814C00610000 | $596.00 | $2.94 | +$0.17 | $3.05 | -40 | -40 | -54 | -71 | -40 | -32 | -40 |
| 08-12 | 09:47 | Honeydrip daytrades | NVDA260814C00220000 | $222.00 | $3.95 | +$2.04 | $5.15 | +65 | +55 | +65 | +65 | +65 | +35 | +35 |
| 08-12 | 09:53 | ZT scalps | AMZN260814P00270000 | $271.00 | $2.34 | +$2.07 | $3.25 | +86 | +86 | +86 | +86 | +86 | +12 | +12 |
| 08-12 | 09:58 | ZT scalps | AMZN260814C00277500 | $270.00 | $0.59 | +$0.05 | $0.70 | -8 | -8 | -8 | -8 | -8 | -5 | -8 |
| 08-13 | 09:55 | Demon Alerts | TSLA260814C00340000 | $332.00 | $1.05 | +$1.57 | $1.24 | -12 | +0 | -12 | -14 | -14 | -11 | +5 |
| 08-13 | 10:03 | ZT scalps | AMD260814C00505000 | $495.00 | $3.47 | +$0.37 | $3.25 | -47 | -47 | -66 | -51 | -47 | -37 | -47 |
| 08-14 | 09:40 | Honeydrip daytrades | AMD260819C00507500 | $489.00 | $5.80 | +$1.50 | $9.90 | -15 | -15 | -15 | +115 | -55 | -30 | -55 |
| 08-14 | 09:46 | Honeydrip daytrades | AAPL260819C00307500 | $306.00 | $2.45 | +$0.35 | $2.88 | -15 | -15 | -15 | -15 | -15 | -14 | -15 |
| 08-17 | 09:31 | Honeydrip daytrades | META260821C00595000 | $584.00 | $4.50 | +$0.02 | $4.35 | -15 | -15 | -15 | -15 | -15 | -25 | -15 |
| 08-17 | 09:50 | Honeydrip daytrades | AMD260821C00535000 | $514.00 | $6.40 | +$1.31 | $6.30 | -30 | -30 | -50 | -65 | -40 | -40 | -40 |
| 08-18 | 09:30 | Whop Day Trades | SPY260819C00775000 | $768.00 | $0.29 | +$0.46 | $0.39 | -5 | -5 | -5 | -5 | -2 | -5 | -1 |
| 08-18 | 09:44 | ZT scalps | NVDA260821C00227500 | $220.00 | $0.71 | +$0.80 | $0.83 | -12 | -12 | -12 | -12 | -12 | -4 | -12 |
| 08-18 | 10:14 | Whop Day Trades | SPY260825P00760000 | $768.00 | $1.87 | +$0.17 | $1.86 | -9 | -9 | -12 | -15 | -9 | -9 | -9 |
| 08-18 | 11:06 | Whop Day Trades | SPY260818C00769000 | $768.00 | $0.59 | +$0.10 | $0.61 | -7 | -7 | -10 | -17 | -7 | +0 | +0 |
| 08-18 | 11:59 | Option Alerts | TSLA260819C00350000 | $339.00 | $0.62 | +$0.52 | $0.67 | -12 | -12 | -18 | -18 | -12 | -3 | -1 |
| 08-18 | 12:04 | Option Alerts | TSLA260819C00350000 | $339.00 | $0.62 | +$0.52 | $0.67 | -12 | -12 | -18 | -18 | -12 | -3 | -1 |
| 08-18 | 15:48 | Option Alerts | TSLA260918P00300000 | $337.00 | $3.21 | +$0.43 | $3.20 | -1 | -1 | -1 | -1 | -1 | -1 | -1 |
| 08-19 | 09:38 | Honeydrip daytrades | GOOGL260821C00345000 | $343.00 | $2.72 | +$0.33 | $2.73 | -49 | -49 | -65 | -83 | -49 | -27 | -49 |
| 08-19 | 09:40 | ZT opt-1 | AAPL260918C00330000 | $312.00 | $2.83 | +$5.81 | $4.05 | +112 | +112 | +112 | +112 | +52 | -14 | +67 |
| 08-19 | 09:41 | Vero 2 | QQQ260819P00716000 | $718.00 | $1.32 | +$0.01 | $4.01 | -1 | -1 | -1 | -1 | -1 | -7 | -1 |
| 08-19 | 09:50 | Honeydrip daytrades | MSFT260821C00480000 | $481.00 | $5.20 | +$1.32 | $5.95 | -45 | -45 | +30 | +30 | +65 | -40 | -5 |
| 08-19 | 10:00 | Honeydrip daytrades | GOOGL260821C00342500 | $342.00 | $3.30 | +$3.00 | $4.70 | +90 | +105 | +50 | +70 | +120 | +0 | +0 |
| 08-19 | 10:21 | ZT top-flow | TSLA260821C00360000 | $339.00 | $0.48 | +$4.43 | $0.56 | +8 | +8 | +8 | +8 | +8 | +0 | +0 |
| 08-19 | 10:33 | ZT top-flow | TSLA260821P00340000 | $342.00 | $3.98 | +$0.72 | $4.20 | -43 | -43 | -58 | -78 | -43 | -18 | -3 |
| 08-19 | 10:45 | ZT top-flow | TSLA260821P00345000 | $347.00 | $4.10 | +$1.22 | $4.65 | +25 | +25 | -45 | -15 | -25 | +0 | +0 |
| 08-19 | 11:21 | ZT top-flow | TSLA260821C00352500 | $347.00 | $3.05 | +$1.15 | $3.15 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| 08-20 | 10:17 | ? | AAPL260821P00315000 | $317.00 | $1.44 | +$1.00 | $1.67 | +4 | +4 | +4 | +4 | +4 | +13 | +13 |
| 08-24 | 09:44 | ZT scalps | NVDA260828C00207500 | $210.00 | $7.80 | +$0.23 | $7.80 | -65 | -65 | -60 | -60 | -65 | -55 | -65 |
| 08-24 | 09:46 | Honeydrip daytrades | MSFT260828P00487500 | $485.00 | $7.85 | +$1.09 | $7.70 | -55 | -55 | -130 | -155 | -105 | -65 | -105 |
| 08-24 | 10:59 | Demon Alerts | TSLA260824C00357500 | $358.00 | $2.17 | +$0.70 | $2.45 | -57 | -57 | -61 | -61 | -57 | -11 | +10 |
| 08-24 | 11:40 | Demon Alerts | TSLA260828P00357500 | $357.00 | $7.00 | +$0.27 | $7.25 | -55 | -55 | +15 | +15 | -55 | -35 | -55 |
| 08-24 | 12:04 | MR.TOPHAT | SPY260831C00765000 | $765.00 | $4.98 | +$0.00 | $5.23 | -2 | -2 | -2 | -9 | -2 | +0 | -2 |
| 08-25 | 09:39 | Honeydrip daytrades | MSFT260828P00485000 | $488.00 | $4.70 | +$0.56 | $4.60 | -80 | -80 | -80 | -80 | -80 | -90 | -80 |
| 08-25 | 11:38 | Honeydrip daytrades | TSLA260828P00352500 | $353.00 | $5.85 | +$1.65 | $6.50 | +10 | +5 | +0 | +0 | +0 | +25 | +25 |
| 08-26 | 09:47 | ZT top-flow | TSLA260828P00350000 | $351.00 | $5.15 | +$4.48 | $7.20 | +130 | +130 | +100 | +100 | +90 | -25 | +100 |
| 09-01 | 12:13 | ZT all-trades-mashup | SPY260901C00764000 | $763.00 | $0.42 | +$0.03 | $0.73 | -3 | -3 | -6 | -8 | -3 | -2 | -3 |
| 09-01 | 12:17 | ZT all-trades-mashup | SPY260901C00764000 | $763.00 | $0.42 | +$0.03 | $0.56 | -3 | -3 | -6 | -8 | -3 | -2 | -3 |
| 09-02 | 11:43 | Midas | SPY260903C00766000 | $765.00 | $1.73 | +$0.59 | $2.12 | +13 | +13 | +15 | +15 | +21 | +0 | +0 |
| 09-08 | 09:36 | Honeydrip daytrades | AMD260911C00510000 | $493.00 | $5.70 | +$0.73 | $6.80 | -50 | -50 | -50 | -50 | -50 | -30 | -50 |
| 09-08 | 09:54 | Platinum nitro | QQQ260908P00717000 | $717.00 | $1.64 | +$0.19 | $2.33 | -13 | -13 | -17 | -21 | -13 | -1 | -1 |
| 09-08 | 10:03 | Platinum nitro | QQQ260908P00717000 | $717.00 | $1.57 | +$0.51 | $2.33 | +5 | +5 | +5 | -5 | +22 | -1 | -1 |
| 09-08 | 10:07 | Platinum nitro | TSLA260911C00372500 | $362.00 | $3.25 | +$0.62 | $3.30 | -47 | -47 | -60 | -48 | -47 | -15 | -47 |
| 09-08 | 10:15 | Vero 1 | QQQ260908P00716000 | $717.00 | $1.11 | +$0.54 | $1.28 | -1 | -1 | -1 | -9 | +11 | -11 | -1 |
| 09-08 | 10:35 | Vero 1 | SPY260908P00767000 | $767.00 | $0.98 | +$0.36 | $1.14 | -2 | -2 | -2 | +0 | +0 | +2 | +2 |
| 09-11 | 10:25 | Platinum nitro | TSLA260911P00362500 | $364.00 | $1.41 | +$0.05 | $1.88 | -36 | -36 | -47 | -62 | -36 | -13 | -36 |

## Coverage and caveats

- Days measured: **2026-08-12, 2026-08-13, 2026-08-14, 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-20, 2026-08-24, 2026-08-25, 2026-08-26, 2026-09-01, 2026-09-02, 2026-09-08, 2026-09-11**.
- Alerts on SPY/QQQ/TSLA/NVDA/META/AAPL/MSFT/AMZN/GOOGL/AMD with an option path AND cached 1-second bars: **76**. Of those, the pullback entered **45**.
- Option quote source per contract-day: OPRA 1s 44, Webull sweep 1.
- Stock bars are 1-second Databento; the option tape is 1-second OPRA on the backfilled days and a 5-60s Webull sweep otherwise. A stop touched between two option quotes is invisible, so stop counts are a floor.
- The OPRA backfill bought the minutes around each call, not whole sessions, so most paths end long before 15:59 and "close" means the end of the tape, not a real exit.
- **2026-09-14 is missing and cannot be bought.** Every Databento equity dataset ends at 2026-09-14T04:00Z, so that session's per-second bars are not released yet. Re-run this script when they are; the cache means it will only pay for the new day.
- No slippage, no queue, no partial fills; entries cross the ask.
- The stock ladder has never traded a real dollar. This is a replay.

### Alerts not replayed

| Why | n |
|---|---:|
| no option quote path for this exact contract | 176 |
| no cached 1-second stock bars for this symbol-day | 46 |
| option path ends before the alert | 3 |
