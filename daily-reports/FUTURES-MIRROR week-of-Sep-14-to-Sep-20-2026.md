# FUTURES-MIRROR — week of Mon Sep 14 2026 to Sun Sep 20 2026. Newest day first; each day under its ===== header; a re-run replaces that day's block (reports.py).

===== Fri Sep 18 2026 =====

# FUTURES MIRROR — 2026-09-18

SPY/QQQ room entries replayed as one-contract MES/MNQ two ways: market entry with a 25-pt stop / 50-pt target and the futures ratchet, and the LEVEL entry (MES: limit 2 before the 25, 12.5-pt 1:1 bracket; MNQ: limit 10 through the 25, 12.5 stop, BE at +5, rungs 2.5; 30-min wait).
The switch is OFF: this is a measurement, not a trade.

**Bars:** cache (ES_1m_2026-09-18.csv, NQ_1m_2026-09-18.csv)
**Alerts:** 7 (after RTH filter and 3-minute dedupe)

## The day

| time ET | sym | dir | micro | room | caller | entry | exit | why | pts | $ market | $ level |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10:09:00 | SPY | long | MES | Midas | Midas | 7690.00 | 7712.25 | CLOSE | +22.25 | +$111 | level never touched |
| 10:41:00 | SPY | long | MES | TTT Lotto | Shakira T | 7689.25 | 7712.25 | CLOSE | +23.00 | +$115 | level never touched |
| 10:54:00 | QQQ | long | MNQ | Shoof Alerts | Elite Options | 29764.00 | 29738.50 | STOP | -25.50 | -$51 | +$19 |
| 10:57:00 | SPX | long | MES | shabs | shabs | 7692.75 | 7712.25 | CLOSE | +19.50 | +$98 | level never touched |
| 12:01:00 | SPY | short | MES | OWLS jon-and-kian | jon & kian | 7682.75 | 7708.25 | STOP | -25.50 | -$128 | level never touched |
| 12:27:00 | SPY | short | MES | Midas | Midas | 7679.75 | 7705.25 | STOP | -25.50 | -$128 | level never touched |
| 12:55:00 | SPX | long | MES | TTT Lotto | rks_$$$$ | 7690.50 | 7712.25 | CLOSE | +21.75 | +$109 | level never touched |

$ level = the resting-limit entry (MES: limit 2 before the 25, 12.5-pt 1:1 bracket; MNQ: limit 10 through the 25, 12.5 stop, BE at +5, rungs 2.5; 30-min wait) with its own exits; "level never touched" = the alert was skipped, not lost.

## Totals

|  | trades | gross | net after $1.50 RT | win rate |
|---|---|---|---|---|
| Today (market) | 7 | +$126 | +$116 | 57% |
| Today (level) | 1 | +$19 | +$18 | 100% |
| **Since 2026-09-17 (market)** | 16 | **+$265** | +$241 | 62% |
| **Level, fills so far** | 5 | **+$58** | +$50 | 80% |

The level row counts from the day it was added to this file (9/18); the history behind it is reference/PULLBACK-LEVEL-ENTRY-TEST.txt. It goes to G for a real-money decision at 30 fills per micro.

## By room

| room | trades | gross | wins |
|---|---|---|---|
| OWLS jon-and-kian | 1 | -$128 | 0 |
| Shoof Alerts | 1 | -$51 | 0 |
| Midas | 2 | -$16 | 1 |
| shabs | 1 | +$98 | 1 |
| TTT Lotto | 2 | +$224 | 2 |

## By symbol and direction

| direction | trades | gross | wins |
|---|---|---|---|
| SPY short | 2 | -$255 | 0 |
| QQQ long | 1 | -$51 | 0 |
| SPX long | 2 | +$206 | 2 |
| SPY long | 2 | +$226 | 2 |

## How they ended

| exit | trades | gross |
|---|---|---|
| CLOSE | 4 | +$432 |
| STOP | 3 | -$306 |


### What this number is not

- No slippage and no spread: entries fill at the next bar's OPEN, exits at
  the exact stop/target price. A real market order does neither.
- 1-minute bars, so a bar that touched the stop AND the target is scored as
  a stop. Conservative, but it is a guess about which came first.
- Commission is an assumption: $1.50 round turn per contract, shown net.
- The mirror is OFF. This is hypothetical: the current live futures route
  records stop/target levels but does not enforce those exits at the broker.
  Activation is blocked until protective exits are operational and tested.
- New-day alert coverage is limited to bridge shadow rows and master_alerts;
  a post missed before those stages is absent from this report.

===== Thu Sep 17 2026 =====

# FUTURES MIRROR — 2026-09-17

SPY/QQQ room entries replayed as one-contract MES/MNQ two ways: market entry with a 25-pt stop / 50-pt target and the futures ratchet, and the LEVEL entry (MES: limit 2 before the 25, 12.5-pt 1:1 bracket; MNQ: limit 10 through the 25, 12.5 stop, BE at +5, rungs 2.5; 30-min wait).
The switch is OFF: this is a measurement, not a trade.

**Bars:** cache (ES_1m_2026-09-17.csv, NQ_1m_2026-09-17.csv)
**Alerts:** 9 (after RTH filter and 3-minute dedupe)

## The day

| time ET | sym | dir | micro | room | caller | entry | exit | why | pts | $ market | $ level |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 09:36:00 | SPY | short | MES | Vero 1 | Vero | 7694.75 | 7707.50 | CLOSE | -12.75 | -$64 | level never touched |
| 09:40:00 | SPY | long | MES | Honeydrip daytrades | HoneyDrip (Scribe) | 7691.50 | 7707.50 | CLOSE | +16.00 | +$80 | level never touched |
| 09:42:51 | QQQ | long | MNQ | Demon day-trades | Demon × LKS | 29644.50 | 29650.67 | RATCHET | +6.17 | +$12 | level never touched |
| 09:52:00 | QQQ | long | MNQ | Vero 1 | @vero-alerts | 29670.75 | 29674.25 | RATCHET | +3.50 | +$7 | +$39 |
| 10:14:00 | SPY | long | MES | Honeydrip daytrades | Brett | 7692.25 | 7707.50 | CLOSE | +15.25 | +$76 | level never touched |
| 10:16:49 | QQQ | long | MNQ | Brando Alerts | EliteOptions | Brando | 29711.50 | 29722.00 | RATCHET | +10.50 | +$21 | level never touched |
| 10:23:00 | QQQ | long | MNQ | Vero 1 | @vero-alerts | 29718.25 | 29722.00 | RATCHET | +3.75 | +$8 | +$0 |
| 10:28:18 | QQQ | long | MNQ | Vero 1 | Vero | 29722.75 | 29722.25 | BE | -0.50 | -$1 | +$0 |
| 10:56:00 | QQQ | short | MNQ | Vero 2 | Vero | 29684.25 | 29684.75 | BE | -0.50 | -$1 | -$1 |

$ level = the resting-limit entry (MES: limit 2 before the 25, 12.5-pt 1:1 bracket; MNQ: limit 10 through the 25, 12.5 stop, BE at +5, rungs 2.5; 30-min wait) with its own exits; "level never touched" = the alert was skipped, not lost.

## Totals

|  | trades | gross | net after $1.50 RT | win rate |
|---|---|---|---|---|
| Today (market) | 9 | +$138 | +$125 | 67% |
| Today (level) | 4 | +$39 | +$33 | 75% |
| **Since 2026-09-17 (market)** | 9 | **+$138** | +$125 | 67% |
| **Level, fills so far** | 4 | **+$39** | +$33 | 75% |

The level row counts from the day it was added to this file (9/18); the history behind it is reference/PULLBACK-LEVEL-ENTRY-TEST.txt. It goes to G for a real-money decision at 30 fills per micro.

## By room

| room | trades | gross | wins |
|---|---|---|---|
| Vero 1 | 4 | -$50 | 2 |
| Vero 2 | 1 | -$1 | 0 |
| Demon day-trades | 1 | +$12 | 1 |
| Brando Alerts | 1 | +$21 | 1 |
| Honeydrip daytrades | 2 | +$156 | 2 |

## By symbol and direction

| direction | trades | gross | wins |
|---|---|---|---|
| SPY short | 1 | -$64 | 0 |
| QQQ short | 1 | -$1 | 0 |
| QQQ long | 5 | +$47 | 4 |
| SPY long | 2 | +$156 | 2 |

## How they ended

| exit | trades | gross |
|---|---|---|
| RATCHET | 4 | +$48 |
| CLOSE | 3 | +$92 |
| BE | 2 | -$2 |


### What this number is not

- No slippage and no spread: entries fill at the next bar's OPEN, exits at
  the exact stop/target price. A real market order does neither.
- 1-minute bars, so a bar that touched the stop AND the target is scored as
  a stop. Conservative, but it is a guess about which came first.
- Commission is an assumption: $1.50 round turn per contract, shown net.
- The mirror is OFF. This is hypothetical: the current live futures route
  records stop/target levels but does not enforce those exits at the broker.
  Activation is blocked until protective exits are operational and tested.
- New-day alert coverage is limited to bridge shadow rows and master_alerts;
  a post missed before those stages is absent from this report.

===== Wed Sep 16 2026 =====

# FUTURES MIRROR — 2026-09-16

SPY/QQQ room entries replayed as one-contract MES/MNQ, market entry, 25-pt stop / 50-pt target, futures ratchet.
The switch is OFF: this is a measurement, not a trade.

**bars: unavailable** — BentoClientError: 422 data_end_after_available_end
The dataset GLBX.MDP3 has data available up to '2026-09-16 20:20:00+00:00'. The `end` in the query ('2026-09-17 00:00:00+00:00') is after the available range. Try requ

3 SPY/QQQ alert(s) were found for this date and are NOT scored. Nothing is guessed and nothing is written to the cumulative file; re-run once bars are available.


### What this number is not

- No slippage and no spread: entries fill at the next bar's OPEN, exits at
  the exact stop/target price. A real market order does neither.
- 1-minute bars, so a bar that touched the stop AND the target is scored as
  a stop. Conservative, but it is a guess about which came first.
- Commission is an assumption: $1.50 round turn per contract, shown net.
- The mirror is OFF. This is hypothetical: the current live futures route
  records stop/target levels but does not enforce those exits at the broker.
  Activation is blocked until protective exits are operational and tested.
- New-day alert coverage is limited to bridge shadow rows and master_alerts;
  a post missed before those stages is absent from this report.

===== Tue Sep 15 2026 =====

# FUTURES MIRROR — 2026-09-15

SPY/QQQ room entries replayed as one-contract MES/MNQ, market entry, 25-pt stop / 50-pt target, futures ratchet.
The switch is OFF: this is a measurement, not a trade.

**bars: unavailable** — BentoClientError: 422 data_end_after_available_end
The dataset GLBX.MDP3 has data available up to '2026-09-15 20:20:00+00:00'. The `end` in the query ('2026-09-16 00:00:00+00:00') is after the available range. Try requ

4 SPY/QQQ alert(s) were found for this date and are NOT scored. Nothing is guessed and nothing is written to the cumulative file; re-run once bars are available.


### What this number is not

- No slippage and no spread: entries fill at the next bar's OPEN, exits at
  the exact stop/target price. A real market order does neither.
- 1-minute bars, so a bar that touched the stop AND the target is scored as
  a stop. Conservative, but it is a guess about which came first.
- Commission is an assumption: $1.50 round turn per contract, shown net.
- The mirror is OFF. This is hypothetical: the current live futures route
  records stop/target levels but does not enforce those exits at the broker.
  Activation is blocked until protective exits are operational and tested.
- New-day alert coverage is limited to bridge shadow rows and master_alerts;
  a post missed before those stages is absent from this report.

===== Mon Sep 14 2026 =====

# FUTURES MIRROR — 2026-09-14

SPY/QQQ room entries replayed as one-contract MES/MNQ, market entry, 25-pt stop / 50-pt target, futures ratchet.
The switch is OFF: this is a measurement, not a trade.

**bars: unavailable** — BentoClientError: 422 dataset_unavailable_range
Part or all of your request for dataset 'GLBX.MDP3' requires a subscription and/or license to access. Try again with an end time before 2026-09-14T21:51:58.705042000Z.
do

8 SPY/QQQ alert(s) were found for this date and are NOT scored. Nothing is guessed and nothing is written to the cumulative file; re-run once bars are available.


### What this number is not

- No slippage and no spread: entries fill at the next bar's OPEN, exits at
  the exact stop/target price. A real market order does neither.
- 1-minute bars, so a bar that touched the stop AND the target is scored as
  a stop. Conservative, but it is a guess about which came first.
- Commission is an assumption: $1.50 round turn per contract, shown net.
- The mirror is OFF. This is hypothetical: the current live futures route
  records stop/target levels but does not enforce those exits at the broker.
  Activation is blocked until protective exits are operational and tested.
- New-day alert coverage is limited to bridge shadow rows and master_alerts;
  a post missed before those stages is absent from this report.
