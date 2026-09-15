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
| **A** LIVE flat 5/3/5 | 17 | -341 | -341 | 18% | -20.06 | 3m 04s | 7 | 7 | 2 | 1 |
| **B** 9/2 price tiers + anti-clip | 17 | -428 | -428 | 12% | -25.18 | 4m 19s | 14 | 0 | 1 | 2 |
| **C** 5/3/5 + born-stop floor | 17 | -341 | -341 | 18% | -20.06 | 3m 04s | 7 | 7 | 2 | 1 |
| **D** 9/2 tiers + anti-clip + floor | 17 | -405 | -405 | 18% | -23.82 | 4m 55s | 13 | 1 | 1 | 2 |

Webull charges $0 commission on options, so net = gross.

One row dominates those dollars: **09-11 NVDA260911C00220000, -188**. Its sweep has a hole of more than two minutes before the exit, so the price that broke its stop was never recorded and every variant marks it at whatever the tape showed next. Same subset, gap-damaged rows dropped:

| Variant | n (gap-clean) | Gross $ | Win % | Avg/trade | Born stop | First lock | Ratchet rung | Close |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **A** LIVE flat 5/3/5 | 15 | -160 | 13% | -10.67 | 7 | 6 | 1 | 1 |
| **B** 9/2 price tiers + anti-clip | 15 | -224 | 13% | -14.93 | 12 | 0 | 1 | 2 |
| **C** 5/3/5 + born-stop floor | 15 | -160 | 13% | -10.67 | 7 | 6 | 1 | 1 |
| **D** 9/2 tiers + anti-clip + floor | 15 | -201 | 20% | -13.40 | 11 | 1 | 1 | 2 |

## Paired comparison against A (same trades, same paths)

**All 17 scored trades**

| Variant | Mean difference / trade | 95% bootstrap band (4000 resamples) | Resamples above zero | Verdict |
|---|---:|---|---:|---|
| B vs A | -5.12 | -15.18 .. +3.18 | 12% | **cannot be decided at this sample** — the band spans zero |
| C vs A | +0.00 | +0.00 .. +0.00 | 0% | identical to A on **every** trade in this sample |
| D vs A | -3.76 | -14.06 .. +4.59 | 22% | **cannot be decided at this sample** — the band spans zero |

**Gap-clean subset (15)**

| Variant | Mean difference / trade | 95% bootstrap band (4000 resamples) | Resamples above zero | Verdict |
|---|---:|---|---:|---|
| B vs A | -4.27 | -15.73 .. +4.40 | 20% | **cannot be decided at this sample** — the band spans zero |
| C vs A | +0.00 | +0.00 .. +0.00 | 0% | identical to A on **every** trade in this sample |
| D vs A | -2.73 | -14.60 .. +6.07 | 32% | **cannot be decided at this sample** — the band spans zero |

The band is the 2.5th-97.5th percentile of the resampled MEAN difference. A band that contains zero means this sample cannot tell the two rules apart, whatever the totals say.

## Where the money actually was

This is the answer to "is it too tight": how far the bid got above the entry before the exit rule took it off, per trade, under A.

| Day | Time | Contract | Entry | Best bid | Peak gain | A took | Gave back |
|---|---|---|---:|---:|---:|---:|---:|
| 09-11 | 10:01 | NVDA260911C00220000 | $2.11 | $2.26 | +7.1% | -89.1% | 96.2 pts |
| 09-11 | 10:25 | TSLA260911P00362500 | $1.82 | $1.88 | +3.3% | -3.8% | 7.1 pts |
| 09-11 | 12:41 | CPS260918C00025000 | $0.65 | $0.70 | +7.7% | -7.7% | 15.4 pts |
| 09-14 | 10:13 | CRWD260918C00245000 | $2.50 | $2.63 | +5.2% | -2.0% | 7.2 pts |
| 09-14 | 10:21 | TSLA260918C00357500 | $7.40 | $7.25 | -2.0% | -4.7% | 2.7 pts |
| 09-14 | 10:22 | TSLA260918P00357500 | $6.50 | $7.10 | +9.2% | +4.6% | 4.6 pts |
| 09-14 | 10:23 | NVDA260916P00210000 | $2.40 | $2.53 | +5.4% | +0.0% | 5.4 pts |
| 09-14 | 10:36 | QQQ260914P00704000 | $1.13 | $1.17 | +3.5% | -0.9% | 4.4 pts |
| 09-14 | 10:41 | QQQ260914P00705000 | $1.41 | $1.43 | +1.4% | -5.0% | 6.4 pts |
| 09-14 | 10:42 | MU260916P00850000 | $2.10 | $1.32 | -37.1% | -44.3% | 7.1 pts |
| 09-14 | 11:12 | MSFT260914C00505000 | $0.65 | $0.65 | +0.0% | -4.6% | 4.6 pts |
| 09-14 | 11:24 | META260918C00670000 | $6.65 | $6.75 | +1.5% | -5.3% | 6.8 pts |
| 09-14 | 11:52 | TSLA260925P00340000 | $2.38 | $2.55 | +7.1% | -0.4% | 7.6 pts |
| 09-14 | 14:05 | META260918C00700000 | $2.61 | $2.85 | +9.2% | +2.7% | 6.5 pts |
| 09-14 | 14:14 | QQQ260914C00713000 | $0.24 | $0.24 | +0.0% | -12.5% | 12.5 pts |
| 09-14 | 14:20 | TSLA260914P00360000 | $0.38 | $0.37 | -2.6% | -7.9% | 5.3 pts |
| 09-14 | 15:12 | AFRM261016C00080000 | $2.11 | $2.19 | +3.8% | +3.8% | 0.0 pts |

- Trades whose bid ever reached the **+3% arm**: **10 of 17**.
- Trades that armed the ratchet and still came out at or below entry: **7**. That is the population the complaint is about.
- If the bid never reached +3%%, no arm/rung setting could have changed that trade; only the born stop could.

## Named cases

- **QQQ 708 C 2026-09-14** (shabs, Skyy, 11:21) — Skyy's 0DTE that the caller rode to +423%  **LATE START — not in any total.** The tape's first quote for this contract is 11 minutes after the call, so the entry below is a price from that later moment, not the one the alert offered.
  - entry $0.87 (first ask), spread at entry $0.02, max bid $1.44 at 11:32:38, 354 quotes, first quote 648s after the alert.
  - A: born stop $0.83 -> exit $1.30 at 11:32:43 (ratchet rung), +43
  - B: born stop $0.83 -> exit $1.28 at 11:33:32 (ratchet rung), +41
  - C: born stop $0.83 -> exit $1.30 at 11:32:43 (ratchet rung), +43
  - D: born stop $0.83 -> exit $1.28 at 11:33:32 (ratchet rung), +41
- **MSFT 505 C 2026-09-14** (OWLS all-alerts, MuggZone, 11:12) — the bot's fastest stop-out of the day
  - entry $0.65 (real fill), spread at entry $0.01, max bid $0.65 at 11:15:50, 935 quotes, first quote 196s after the alert.
  - A: born stop $0.62 (clamped to the bid) -> exit $0.62 at 11:15:59 (born stop), -3
  - B: born stop $0.62 (clamped to the bid) -> exit $0.62 at 11:15:59 (born stop), -3
  - C: born stop $0.62 (clamped to the bid) -> exit $0.62 at 11:15:59 (born stop), -3
  - D: born stop $0.62 (clamped to the bid) -> exit $0.62 at 11:15:59 (born stop), -3
  - REAL: bot filled $0.65, out $0.61 at 11:16:02, -4.
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

`!` marks a sweep hole longer than two minutes before the exit — that row's exit price is the next thing the tape saw, not the price that broke the stop.

### Scored

| Day | Time | Room | Caller | Contract | Entry basis | Entry | A exit / $ | B exit / $ | C exit / $ | D exit / $ | Max bid | Max bid at |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 09-11 | 10:01 | Platinum nitro | @Owner Alerts | NVDA 220C 2026-09-11 | first ask `!` | $2.11 | $0.23 / -188 | $0.23 / -188 | $0.23 / -188 | $0.23 / -188 | $2.26 | 10:03:30 |
| 09-11 | 10:25 | Platinum nitro | Nitro Trades | TSLA 362.5P 2026-09-11 | first ask | $1.82 | $1.75 / -7 | $1.73 / -9 | $1.75 / -7 | $1.73 / -9 | $1.88 | 10:25:53 |
| 09-11 | 12:41 | Demon day-trades | Demon × LKS | CPS 25C 2026-09-18 | real fill | $0.65 | $0.60 / -5 | $0.60 / -5 | $0.60 / -5 | $0.60 / -5 | $0.70 | 12:41:08 |
| 09-14 | 10:13 | Mugzone Options | MuggZone | CRWD 245C 9/18 | first ask | $2.50 | $2.45 / -5 | $2.36 / -14 | $2.45 / -5 | $2.59 / +9 | $2.63 | 10:15:20 |
| 09-14 | 10:21 | Platinum ei-alerts | PT \| ei trades | TSLA 357.5C 2026-09-18 | real fill | $7.40 | $7.05 / -35 | $7.05 / -35 | $7.05 / -35 | $7.05 / -35 | $7.25 | 10:24:27 |
| 09-14 | 10:22 | Platinum nitro | @Owner Alerts | TSLA 357.5P 2026-09-18 | first ask | $6.50 | $6.80 / +30 | $6.10 / -40 | $6.80 / +30 | $6.10 / -40 | $7.10 | 10:27:05 |
| 09-14 | 10:23 | Whop Day Trades | Trademorewiser (MOD) | NVDA 210P 9/16 | real fill | $2.40 | $2.40 / +0 | $2.28 / -12 | $2.40 / +0 | $2.28 / -12 | $2.53 | 10:26:42 |
| 09-14 | 10:36 | Demon day-trades | Demon × LKS | QQQ 704P 9/14 | real fill | $1.13 | $1.12 / -1 | $1.07 / -6 | $1.12 / -1 | $1.07 / -6 | $1.17 | 10:37:34 |
| 09-14 | 10:41 | Vero 2 | Vero | QQQ 705P 9/14 | real fill | $1.41 | $1.34 / -7 | $1.34 / -7 | $1.34 / -7 | $1.34 / -7 | $1.43 | 10:42:35 |
| 09-14 | 10:42 | Mugzone Options | MuggZone | MU 850P 9/16 | real fill | $2.10 | $1.17 / -93 | $1.17 / -93 | $1.17 / -93 | $1.17 / -93 | $1.32 | 11:32:11 |
| 09-14 | 11:12 | OWLS all-alerts | MuggZone | MSFT 505C 2026-09-14 | real fill | $0.65 | $0.62 / -3 | $0.62 / -3 | $0.62 / -3 | $0.62 / -3 | $0.65 | 11:15:50 |
| 09-14 | 11:24 | Honeydrip daytrades | Unraveller | META 670C 9/18 | real fill | $6.65 | $6.30 / -35 | $6.30 / -35 | $6.30 / -35 | $6.30 / -35 | $6.75 | 11:27:07 |
| 09-14 | 11:52 | Mugzone Options | MuggZone | TSLA 340P 9/25 | real fill | $2.38 | $2.37 / -1 | $2.71 / +33 | $2.37 / -1 | $2.71 / +33 | $2.55 | 12:14:45 |
| 09-14 | 14:05 | Aristotle | 👑KingBeeAri🐝 | META 700C 9/18 | real fill `!` | $2.61 | $2.68 / +7 | $2.45 / -16 | $2.68 / +7 | $2.45 / -16 | $2.85 | 14:08:27 |
| 09-14 | 14:14 | shabs | Skyy | QQQ 713C 2026-09-14 | real fill | $0.24 | $0.21 / -3 | $0.21 / -3 | $0.21 / -3 | $0.21 / -3 | $0.24 | 14:24:22 |
| 09-14 | 14:20 | Mugzone Options | MuggZone | TSLA 360P 0DTE | first ask | $0.38 | $0.35 / -3 | $0.35 / -3 | $0.35 / -3 | $0.35 / -3 | $0.37 | 14:21:16 |
| 09-14 | 15:12 | OWLS all-alerts | AbTrades | AFRM 80C 10/16 | first ask | $2.11 | $2.19 / +8 | $2.19 / +8 | $2.19 / +8 | $2.19 / +8 | $2.19 | 15:57:07 |

### Late start — shown, never totalled

| Day | Time | Room | Caller | Contract | Entry basis | Entry | A exit / $ | B exit / $ | C exit / $ | D exit / $ | Max bid | Max bid at |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 09-11 | 10:37 | Platinum nitro | @Owner Alerts | NVDA 220C 2026-09-11 | first ask | $0.24 | $0.21 / -3 | $0.21 / -3 | $0.21 / -3 | $0.21 / -3 | $0.23 | 12:41:33 |
| 09-11 | 12:01 | Honeydrip daytrades | Brett (Admin) | HOOD 118C 2026-09-11 | first ask | $0.02 | $0.01 / -1 | $0.01 / -1 | $0.01 / -1 | $0.01 / -1 | $0.01 | 12:41:33 |
| 09-14 | 11:07 | OWLS all-alerts | Eva | DRAM 58C 9/18 | first ask `!` | $0.54 | $0.63 / +9 | $0.63 / +9 | $0.63 / +9 | $0.63 / +9 | $0.63 | 14:23:50 |
| 09-14 | 11:21 | shabs | Skyy | QQQ 708C 2026-09-14 | first ask | $0.87 | $1.30 / +43 | $1.28 / +41 | $1.30 / +43 | $1.28 / +41 | $1.44 | 11:32:38 |
| 09-14 | 11:28 | Midas | Midas (Admin) | SPY 760P 9/14 | first ask | $1.17 | $0.88 / -29 | $0.88 / -29 | $0.88 / -29 | $0.88 / -29 | $1.16 | 11:31:49 |
| 09-14 | 12:13 | Demon day-trades | Demon × LKS | WMT 110C 9/18 | first ask | $0.98 | $0.96 / -2 | $0.96 / -2 | $0.96 / -2 | $0.96 / -2 | $0.99 | 14:28:56 |
| 09-14 | 12:26 | OWLS all-alerts | TT | GOOGL 360C 10/16 | first ask | $7.80 | $7.35 / -45 | $7.35 / -45 | $7.55 / -25 | $7.55 / -25 | $7.40 | 14:23:50 |
| 09-14 | 12:46 | OWLS all-alerts | AbTrades | AMZN 300C 11/20 | first ask | $3.90 | $3.75 / -15 | $3.75 / -15 | $3.75 / -15 | $3.75 / -15 | $3.80 | 14:23:50 |
| 09-14 | 13:18 | Midas | Midas (Admin) | SPY 762P 0DTE | first ask | $0.50 | $0.47 / -3 | $0.47 / -3 | $0.47 / -3 | $0.47 / -3 | $0.49 | 14:23:50 |
| 09-14 | 13:41 | OWLS all-alerts | MuggZone | AMZN 260C 9/18 | first ask | $1.70 | $1.61 / -9 | $1.61 / -9 | $1.61 / -9 | $1.61 / -9 | $1.64 | 14:23:50 |
| 09-14 | 13:53 | Brando Alerts | EliteOptions \| Brando | QQQ 715C 9/17 | first ask | $3.67 | $3.67 / +0 | $3.67 / +0 | $3.67 / +0 | $3.67 / +0 | $3.70 | 14:26:54 |

## Tape coverage, per alert

Sweep granularity is the biggest caveat in this file. A stop touched between two sweeps is invisible, so every stop-out count below is a FLOOR and every P&L an over-estimate.

| Day | Time | Contract | First quote after alert | Quotes | Median sweep | Largest gap | Gaps > 2 min | Last quote | Reaches 15:59? |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| 09-11 | 10:01 | NVDA260911C00220000 | 1s | 295 | 5s | 9429s | 1 | 13:13:44 | **no** |
| 09-11 | 10:25 | TSLA260911P00362500 | 1s | 1773 | 5s | 31s | 0 | 13:13:44 | **no** |
| 09-11 | 10:37 | NVDA260911C00220000 | 7432s | 265 | 5s | 31s | 0 | 13:13:44 | **no** |
| 09-11 | 12:01 | HOOD260911C00118000 | 2385s | 265 | 5s | 31s | 0 | 13:13:44 | **no** |
| 09-11 | 12:41 | CPS260918C00025000 | 2s | 591 | 1s | 2s | 0 | 12:51:29 | **no** |
| 09-14 | 10:13 | CRWD260918C00245000 | 5s | 60 | 31s | 9778s | 5 | 14:32:00 | **no** |
| 09-14 | 10:21 | TSLA260918C00357500 | 8s | 1098 | 1s | 8455s | 2 | 14:32:00 | **no** |
| 09-14 | 10:22 | TSLA260918P00357500 | 13s | 430 | 5s | 8455s | 2 | 14:32:00 | **no** |
| 09-14 | 10:23 | NVDA260916P00210000 | 7s | 1127 | 1s | 8455s | 2 | 14:32:00 | **no** |
| 09-14 | 10:36 | QQQ260914P00704000 | 17s | 487 | 5s | 8455s | 2 | 14:32:00 | **no** |
| 09-14 | 10:41 | QQQ260914P00705000 | 75s | 1253 | 1s | 8455s | 2 | 14:32:00 | **no** |
| 09-14 | 10:42 | MU260916P00850000 | 2978s | 354 | 5s | 8455s | 1 | 14:32:00 | **no** |
| 09-14 | 11:07 | DRAM260918C00058000 | 1450s | 354 | 5s | 8455s | 1 | 14:32:00 | **no** |
| 09-14 | 11:12 | MSFT260914C00505000 | 196s | 935 | 1s | 8455s | 2 | 14:32:00 | **no** |
| 09-14 | 11:21 | QQQ260914C00708000 | 648s | 354 | 5s | 8455s | 1 | 14:32:00 | **no** |
| 09-14 | 11:24 | META260918C00670000 | 84s | 682 | 5s | 8455s | 1 | 14:32:00 | **no** |
| 09-14 | 11:28 | SPY260914P00760000 | 229s | 353 | 5s | 8455s | 1 | 14:32:00 | **no** |
| 09-14 | 11:52 | TSLA260925P00340000 | 608s | 30486 | 1s | 61s | 0 | 21:05:22 | yes |
| 09-14 | 12:13 | WMT260918C00110000 | 7827s | 9 | 61s | 62s | 0 | 14:32:00 | **no** |
| 09-14 | 12:26 | GOOGL261016C00360000 | 7025s | 9 | 61s | 62s | 0 | 14:32:00 | **no** |
| 09-14 | 12:46 | AMZN261120C00300000 | 5842s | 9 | 61s | 62s | 0 | 14:32:00 | **no** |
| 09-14 | 13:18 | SPY260914P00762000 | 3949s | 9 | 61s | 62s | 0 | 14:32:00 | **no** |
| 09-14 | 13:41 | AMZN260918C00260000 | 2539s | 9 | 61s | 62s | 0 | 14:32:00 | **no** |
| 09-14 | 13:53 | QQQ260917C00715000 | 1799s | 9 | 61s | 62s | 0 | 14:32:00 | **no** |
| 09-14 | 14:05 | META260918C00700000 | 11s | 378 | 1s | 316s | 2 | 14:32:00 | **no** |
| 09-14 | 14:14 | QQQ260914C00713000 | 54s | 357 | 1s | 62s | 0 | 15:59:10 | yes |
| 09-14 | 14:20 | TSLA260914P00360000 | 51s | 97 | 61s | 62s | 0 | 15:59:10 | yes |
| 09-14 | 15:12 | AFRM261016C00080000 | 34s | 46 | 61s | 62s | 0 | 15:59:10 | yes |

- Replayed and scored: **17**. Replayed but late-start (never totalled): **11**. Excluded outright: **14**.
- Scored rows with a sweep hole > 2 min before the exit: **2**. Gap-clean scored rows: **15**.
- Paths that reach 15:59 ET: **4 of 28**. The rest are marked at the last quote the tape holds, which is not a real exit.
- No slippage, no queue, no partial fills. The entry crosses the ask and the exit prints at the bid that broke the stop. Real life is worse.
- 17 scored trades over two sessions is not a sample that can settle a trading rule. It can only rule things out.

### Excluded alerts

| Day | Time | Contract | Why |
|---|---|---|---|
| 09-11 | 10:00 | MU260911C00990000 | no quote path for this exact contract |
| 09-11 | 10:05 | HIMS260918C00029000 | no quote path for this exact contract |
| 09-11 | 10:12 | TSLA260916P00360000 | no quote path for this exact contract |
| 09-11 | 10:23 | AAPL260911C00335000 | no quote path for this exact contract |
| 09-11 | 10:39 | AMZN260914C00255000 | no quote path for this exact contract |
| 09-11 | 10:50 | HOOD260918C00118000 | no quote path for this exact contract |
| 09-11 | 11:21 | SPY260911P00766000 | no quote path for this exact contract |
| 09-11 | 11:28 | MU260911C00980000 | no quote path for this exact contract |
| 09-11 | 13:10 | ORCL260918C00165000 | no quote path for this exact contract |
| 09-11 | 14:06 | SHOP261120C00150000 | no quote path for this exact contract |
| 09-11 | 15:22 | IBM260918C00250000 | no quote path for this exact contract |
| 09-11 | 15:32 | HAL261016C00038000 | no quote path for this exact contract |
| 09-11 | 15:40 | QQQ260911C00716000 | no quote path for this exact contract |
| 09-11 | 15:53 | SPY260918C00772000 | no quote path for this exact contract |

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
| 09-14 | 10:42 | MU260916P00850000 | $2.10 | -93 | not a round-number symbol (instant entry) | — | — |
| 09-14 | 11:12 | MSFT260914C00505000 | $0.65 | -3 | never touched $503 in 10 min | — | — |
| 09-14 | 11:24 | META260918C00670000 | $6.65 | -35 | never touched $656 in 10 min | — | — |
| 09-14 | 11:52 | TSLA260925P00340000 | $2.38 | -1 | touched $364 | $2.39 | +0 |
| 09-14 | 14:05 | META260918C00700000 | $2.61 | +7 | touched $667 | $2.64 | -19 |
| 09-14 | 14:14 | QQQ260914C00713000 | $0.24 | -3 | touched $712 | $0.23 | -1 |
| 09-14 | 14:20 | TSLA260914P00360000 | $0.38 | -3 | never touched $362 in 10 min | — | — |
| 09-14 | 15:12 | AFRM261016C00080000 | $2.11 | +8 | not a round-number symbol (instant entry) | — | — |

- Take-it fills: **17**, **-341** under variant A.
- Pullback fills: **7**, **-130** under variant A.
- On the **13 round-number-eligible alerts only**: take-it **-246**, pullback **-130** — and the pullback simply did not enter 6 of them.
- A skipped entry is $0, not a loss. Whether that is good depends on the trades it skips, which is the point of the table above.
- **Skyy's QQQ 708C is the case in point and it is not in this table**: its tape path starts 10.8 minutes after the call, so neither entry rule can be scored on it. What is recorded is that the contract was $0.75 at the call and the caller posted out at $3.92 (+423%) at 13:14 — a move the $1 pullback wait would have had to be standing in front of, and QQQ's next round number below 706.95 is 706.
