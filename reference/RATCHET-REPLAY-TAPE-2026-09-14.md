# Ratchet replay on real quotes — 2026-09-11 and 2026-09-14

G asked whether the live ratchet is too tight. This replays four exit rules over the SAME recorded bid/ask paths, one contract each, and reports the PAIRED difference against the live rule. It changes no setting and places no order.

Built by `reference/ratchet_replay_tape.py` from `alert_tape.csv` + `option_tape.csv` (quotes), `alert_meta.csv` + `master_alerts.csv` (alerts) and `master_ledger.csv` (real fills). Read that file's docstring for the full assumption list.

## The four rules

| Variant | Born stop | Arms at | First lock | Rung | Anti-clip |
|---|---|---|---|---|---|
| **A — LIVE** | -5% off entry | +3% | breakeven | +5% | off |
| **B — 9/2 tiers** | -5% off entry | +25 / +15 / +10% by premium (<$1 / $1-1.99 / $2+) | +10% / BE / +5% | +15 / +10 / +5% | on, k=0.40 |
| **C — A + floor** | max(-5%, 2x spread, 3 ticks) | +3% | breakeven | +5% | off |
| **D — B + floor** | max(-5%, 2x spread, 3 ticks) | as B | as B | as B | on, k=0.40 |

Both floors from `ratchet_tiers.py` run in every variant: a rung must clear 4 ticks (MIN_RUNG_TICKS) and a stop may never sit inside one full spread or 2 ticks of the bid (MIN_STOP_TICKS). Every variant also obeys the broker clamp — a resting SELL stop is capped one tick under the live bid, because Webull 417s one placed above it.

## Result

| Variant | n | Gross $ | Net $ (0 commission) | Win % | Avg/trade | Median hold | Born stop | First lock | Ratchet rung | Close |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **A** LIVE flat 5/3/5 | 14 | -244 | -244 | 21% | -17.43 | 3m 26s | 5 | 6 | 2 | 1 |
| **B** 9/2 price tiers + anti-clip | 14 | -365 | -365 | 7% | -26.07 | 4m 37s | 12 | 0 | 0 | 2 |
| **C** 5/3/5 + born-stop floor | 14 | -244 | -244 | 21% | -17.43 | 3m 26s | 5 | 6 | 2 | 1 |
| **D** 9/2 tiers + anti-clip + floor | 14 | -342 | -342 | 14% | -24.43 | 5m 52s | 11 | 1 | 0 | 2 |

Webull charges $0 commission on options, so net = gross.

## Paired comparison against A (same trades, same paths)

| Variant | Mean difference / trade | 95% bootstrap band (4000 resamples) | Resamples above zero | Verdict |
|---|---:|---|---:|---|
| B vs A | -8.64 | -20.14 .. -1.43 | 0% | real at this sample |
| C vs A | +0.00 | +0.00 .. +0.00 | 0% | **cannot be decided at this sample** — the band spans zero |
| D vs A | -7.00 | -19.00 .. +0.86 | 5% | **cannot be decided at this sample** — the band spans zero |

The band is the 2.5th-97.5th percentile of the resampled MEAN difference. A band that contains zero means this sample cannot tell the two rules apart, whatever the totals say.

## Named cases

- **QQQ260914C00708000** — Skyy's 0DTE that the caller rode to +423%. No replayable path: first quote 648s after the alert (> 180s)
- **MSFT260914C00505000** — the bot's fastest stop-out of the day. No replayable path: first quote 196s after the alert (> 180s)
- **QQQ 713 C 2026-09-14** (shabs, Skyy, 14:14) — 0.24 -> 0.22 in seconds
  - entry $0.24 (real fill), spread at entry $0.01, max bid $0.24 at 14:24:22, 357 quotes, first quote 54s after the alert.
  - A: born stop $0.21 (clamped to the bid) -> exit $0.21 at 14:27:26 (born stop), -3
  - B: born stop $0.21 (clamped to the bid) -> exit $0.21 at 14:27:26 (born stop), -3
  - C: born stop $0.21 (clamped to the bid) -> exit $0.21 at 14:27:26 (born stop), -3
  - D: born stop $0.21 (clamped to the bid) -> exit $0.21 at 14:27:26 (born stop), -3
  - REAL: bot filled $0.24, out $0.22 at 14:22:33, -2 (bot stop).
- **CRWD 245 C 9/18** (Mugzone Options, MuggZone, 10:13) — MuggZone's CRWD, trimmed five times by the caller
  - entry $2.50 (first ask), spread at entry $0.11, max bid $2.63 at 10:15:20, 60 quotes, first quote 5s after the alert.
  - A: born stop $2.38 (clamped to the bid) -> exit $2.45 at 10:16:21 (first lock), -5
  - B: born stop $2.38 (clamped to the bid) -> exit $2.36 at 10:16:52 (born stop), -14
  - C: born stop $2.28 -> exit $2.45 at 10:16:21 (first lock), -5
  - D: born stop $2.28 -> exit $2.59 at 10:33:40 (first lock), +9
- **QQQ 705 P 9/14** (Vero 2, Vero, 10:41) — Vero's QQQ 705P
  - entry $1.41 (real fill), spread at entry $0.01, max bid $1.43 at 10:42:35, 1253 quotes, first quote 75s after the alert.
  - A: born stop $1.34 -> exit $1.34 at 10:42:47 (born stop), -7
  - B: born stop $1.34 -> exit $1.34 at 10:42:47 (born stop), -7
  - C: born stop $1.34 -> exit $1.34 at 10:42:47 (born stop), -7
  - D: born stop $1.34 -> exit $1.34 at 10:42:47 (born stop), -7
  - REAL: bot filled $1.41, out $1.39 at 11:15:59, -2.
- **QQQ 704 P 9/14** (Demon day-trades, Demon × LKS, 10:36) — Demon's QQQ 704P
  - entry $1.13 (real fill), spread at entry $0.01, max bid $1.17 at 10:37:34, 487 quotes, first quote 17s after the alert.
  - A: born stop $1.07 -> exit $1.12 at 10:37:41 (first lock), -1
  - B: born stop $1.07 -> exit $1.07 at 10:37:59 (born stop), -6
  - C: born stop $1.07 -> exit $1.12 at 10:37:41 (first lock), -1
  - D: born stop $1.07 -> exit $1.07 at 10:37:59 (born stop), -6
  - REAL: bot filled $1.13, out $1.13 at 10:37:44, +0.

## Every replayed alert

| Day | Time | Room | Caller | Contract | Entry basis | Entry | A exit / $ | B exit / $ | C exit / $ | D exit / $ | Max bid | Max bid at |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 09-11 | 10:01 | Platinum nitro | @Owner Alerts | NVDA 220C 2026-09-11 | first ask | $2.11 | $0.23 / -188 | $0.23 / -188 | $0.23 / -188 | $0.23 / -188 | $2.26 | 10:03:30 |
| 09-11 | 10:25 | Platinum nitro | Nitro Trades | TSLA 362.5P 2026-09-11 | first ask | $1.82 | $1.75 / -7 | $1.73 / -9 | $1.75 / -7 | $1.73 / -9 | $1.88 | 10:25:53 |
| 09-11 | 12:41 | Demon day-trades | Demon × LKS | CPS 25C 2026-09-18 | real fill | $0.65 | $0.60 / -5 | $0.60 / -5 | $0.60 / -5 | $0.60 / -5 | $0.70 | 12:41:08 |
| 09-14 | 10:13 | Mugzone Options | MuggZone | CRWD 245C 9/18 | first ask | $2.50 | $2.45 / -5 | $2.36 / -14 | $2.45 / -5 | $2.59 / +9 | $2.63 | 10:15:20 |
| 09-14 | 10:21 | Platinum ei-alerts | PT \| ei trades | TSLA 357.5C 2026-09-18 | real fill | $7.40 | $7.05 / -35 | $7.05 / -35 | $7.05 / -35 | $7.05 / -35 | $7.25 | 10:24:27 |
| 09-14 | 10:22 | Platinum nitro | @Owner Alerts | TSLA 357.5P 2026-09-18 | first ask | $6.50 | $6.80 / +30 | $6.10 / -40 | $6.80 / +30 | $6.10 / -40 | $7.10 | 10:27:05 |
| 09-14 | 10:23 | Whop Day Trades | Trademorewiser (MOD) | NVDA 210P 9/16 | real fill | $2.40 | $2.40 / +0 | $2.28 / -12 | $2.40 / +0 | $2.28 / -12 | $2.53 | 10:26:42 |
| 09-14 | 10:36 | Demon day-trades | Demon × LKS | QQQ 704P 9/14 | real fill | $1.13 | $1.12 / -1 | $1.07 / -6 | $1.12 / -1 | $1.07 / -6 | $1.17 | 10:37:34 |
| 09-14 | 10:41 | Vero 2 | Vero | QQQ 705P 9/14 | real fill | $1.41 | $1.34 / -7 | $1.34 / -7 | $1.34 / -7 | $1.34 / -7 | $1.43 | 10:42:35 |
| 09-14 | 11:24 | Honeydrip daytrades | Unraveller | META 670C 9/18 | real fill | $6.65 | $6.30 / -35 | $6.30 / -35 | $6.30 / -35 | $6.30 / -35 | $6.75 | 11:27:07 |
| 09-14 | 14:05 | Aristotle | 👑KingBeeAri🐝 | META 700C 9/18 | real fill | $2.61 | $2.68 / +7 | $2.45 / -16 | $2.68 / +7 | $2.45 / -16 | $2.85 | 14:08:27 |
| 09-14 | 14:14 | shabs | Skyy | QQQ 713C 2026-09-14 | real fill | $0.24 | $0.21 / -3 | $0.21 / -3 | $0.21 / -3 | $0.21 / -3 | $0.24 | 14:24:22 |
| 09-14 | 14:20 | Mugzone Options | MuggZone | TSLA 360P 0DTE | first ask | $0.38 | $0.35 / -3 | $0.35 / -3 | $0.35 / -3 | $0.35 / -3 | $0.37 | 14:21:16 |
| 09-14 | 15:12 | OWLS all-alerts | AbTrades | AFRM 80C 10/16 | first ask | $2.11 | $2.19 / +8 | $2.19 / +8 | $2.19 / +8 | $2.19 / +8 | $2.19 | 15:57:07 |

## Tape coverage, per alert

Sweep granularity is the biggest caveat in this file. A stop touched between two sweeps is invisible, so every stop-out count below is a FLOOR and every P&L an over-estimate.

| Day | Time | Contract | First quote after alert | Quotes | Median sweep | Largest gap | Gaps > 2 min | Last quote | Reaches 15:59? |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| 09-11 | 10:01 | NVDA260911C00220000 | 1s | 295 | 5s | 9429s | 1 | 13:13:44 | **no** |
| 09-11 | 10:25 | TSLA260911P00362500 | 1s | 1773 | 5s | 31s | 0 | 13:13:44 | **no** |
| 09-11 | 12:41 | CPS260918C00025000 | 2s | 591 | 1s | 2s | 0 | 12:51:29 | **no** |
| 09-14 | 10:13 | CRWD260918C00245000 | 5s | 60 | 31s | 9778s | 5 | 14:32:00 | **no** |
| 09-14 | 10:21 | TSLA260918C00357500 | 8s | 1098 | 1s | 8455s | 2 | 14:32:00 | **no** |
| 09-14 | 10:22 | TSLA260918P00357500 | 13s | 430 | 5s | 8455s | 2 | 14:32:00 | **no** |
| 09-14 | 10:23 | NVDA260916P00210000 | 7s | 1127 | 1s | 8455s | 2 | 14:32:00 | **no** |
| 09-14 | 10:36 | QQQ260914P00704000 | 17s | 487 | 5s | 8455s | 2 | 14:32:00 | **no** |
| 09-14 | 10:41 | QQQ260914P00705000 | 75s | 1253 | 1s | 8455s | 2 | 14:32:00 | **no** |
| 09-14 | 11:24 | META260918C00670000 | 84s | 682 | 5s | 8455s | 1 | 14:32:00 | **no** |
| 09-14 | 14:05 | META260918C00700000 | 11s | 378 | 1s | 316s | 2 | 14:32:00 | **no** |
| 09-14 | 14:14 | QQQ260914C00713000 | 54s | 357 | 1s | 62s | 0 | 15:59:10 | yes |
| 09-14 | 14:20 | TSLA260914P00360000 | 51s | 97 | 61s | 62s | 0 | 15:59:10 | yes |
| 09-14 | 15:12 | AFRM261016C00080000 | 34s | 46 | 61s | 62s | 0 | 15:59:10 | yes |

- Replayed: **14**. Excluded: **28**.
- Paths that reach 15:59 ET: **3 of 14**. The rest are marked at the last quote the tape holds, which is not a real exit.

### Excluded alerts

| Day | Time | Contract | Why |
|---|---|---|---|
| 09-11 | 10:00 | MU260911C00990000 | no quote path for this exact contract |
| 09-11 | 10:05 | HIMS260918C00029000 | no quote path for this exact contract |
| 09-11 | 10:12 | TSLA260916P00360000 | no quote path for this exact contract |
| 09-11 | 10:23 | AAPL260911C00335000 | no quote path for this exact contract |
| 09-11 | 10:37 | NVDA260911C00220000 | first quote 7432s after the alert (> 180s) |
| 09-11 | 10:39 | AMZN260914C00255000 | no quote path for this exact contract |
| 09-11 | 10:50 | HOOD260918C00118000 | no quote path for this exact contract |
| 09-11 | 11:21 | SPY260911P00766000 | no quote path for this exact contract |
| 09-11 | 11:28 | MU260911C00980000 | no quote path for this exact contract |
| 09-11 | 12:01 | HOOD260911C00118000 | first quote 2385s after the alert (> 180s) |
| 09-11 | 13:10 | ORCL260918C00165000 | no quote path for this exact contract |
| 09-11 | 14:06 | SHOP261120C00150000 | no quote path for this exact contract |
| 09-11 | 15:22 | IBM260918C00250000 | no quote path for this exact contract |
| 09-11 | 15:32 | HAL261016C00038000 | no quote path for this exact contract |
| 09-11 | 15:40 | QQQ260911C00716000 | no quote path for this exact contract |
| 09-11 | 15:53 | SPY260918C00772000 | no quote path for this exact contract |
| 09-14 | 10:42 | MU260916P00850000 | first quote 2978s after the alert (> 180s) |
| 09-14 | 11:07 | DRAM260918C00058000 | first quote 1450s after the alert (> 180s) |
| 09-14 | 11:12 | MSFT260914C00505000 | first quote 196s after the alert (> 180s) |
| 09-14 | 11:21 | QQQ260914C00708000 | first quote 648s after the alert (> 180s) |
| 09-14 | 11:28 | SPY260914P00760000 | first quote 229s after the alert (> 180s) |
| 09-14 | 11:52 | TSLA260925P00340000 | first quote 608s after the alert (> 180s) |
| 09-14 | 12:13 | WMT260918C00110000 | first quote 7827s after the alert (> 180s) |
| 09-14 | 12:26 | GOOGL261016C00360000 | first quote 7025s after the alert (> 180s) |
| 09-14 | 12:46 | AMZN261120C00300000 | first quote 5842s after the alert (> 180s) |
| 09-14 | 13:18 | SPY260914P00762000 | first quote 3949s after the alert (> 180s) |
| 09-14 | 13:41 | AMZN260918C00260000 | first quote 2539s after the alert (> 180s) |
| 09-14 | 13:53 | QQQ260917C00715000 | first quote 1799s after the alert (> 180s) |

## The OTHER question: the entry

Same alerts, same variant-A exit rule. "Take it" crosses the ask at the first quote after the alert. "Pullback" is the live rule: for the symbols `pullback.MANAGED` covers, wait up to 10 minutes for the stock to touch the next whole dollar (a dip for a call, a bounce for a put) and cross the ask there; never touched = never entered.

**Coverage warning, and it is severe.** `bars/stock` holds no 1-second file for 2026-09-11 or 2026-09-14, so the only underlying path available is the `und` column of the alert sweep — one print every 5 to 60 seconds. A dollar level tagged between two prints is invisible, so this UNDERSTATES how often the pullback would have filled. Re-run it if per-second bars for these days ever arrive.

| Day | Time | Contract | Take-it entry | Take-it $ (A) | Pullback | Pullback entry | Pullback $ (A) |
|---|---|---|---:|---:|---|---:|---:|
| 09-11 | 10:01 | NVDA260911C00220000 | $2.11 | -188 | never touched $221 in 10 min | — | — |
| 09-11 | 10:25 | TSLA260911P00362500 | $1.82 | -7 | touched $364 | $1.41 | -13 |
| 09-11 | 12:41 | CPS260918C00025000 | $0.65 | -5 | not a round-number symbol (instant entry) | — | — |
| 09-14 | 10:13 | CRWD260918C00245000 | $2.50 | -5 | not a round-number symbol (instant entry) | — | — |
| 09-14 | 10:21 | TSLA260918C00357500 | $7.40 | -35 | touched $358 | $7.35 | -35 |
| 09-14 | 10:22 | TSLA260918P00357500 | $6.50 | +30 | never touched $359 in 10 min | — | — |
| 09-14 | 10:23 | NVDA260916P00210000 | $2.40 | +0 | never touched $211 in 10 min | — | — |
| 09-14 | 10:36 | QQQ260914P00704000 | $1.13 | -1 | touched $705 | $1.01 | -76 |
| 09-14 | 10:41 | QQQ260914P00705000 | $1.41 | -7 | touched $705 | $1.39 | +14 |
| 09-14 | 11:24 | META260918C00670000 | $6.65 | -35 | never touched $656 in 10 min | — | — |
| 09-14 | 14:05 | META260918C00700000 | $2.61 | +7 | touched $667 | $2.64 | -19 |
| 09-14 | 14:14 | QQQ260914C00713000 | $0.24 | -3 | touched $712 | $0.23 | -1 |
| 09-14 | 14:20 | TSLA260914P00360000 | $0.38 | -3 | never touched $362 in 10 min | — | — |
| 09-14 | 15:12 | AFRM261016C00080000 | $2.11 | +8 | not a round-number symbol (instant entry) | — | — |

- Take-it fills: **14**, **-244** under variant A.
- Pullback fills: **6**, **-130** under variant A.
- On the **11 round-number-eligible alerts only**: take-it **-242**, pullback **-130** — and the pullback simply did not enter 5 of them.
- A skipped entry is $0, not a loss. Whether that is good depends on the trades it skips, which is the point of the table above.
