# FUTURES MIRROR — 2026-09-11

SPY/QQQ room entries replayed as one-contract MES/MNQ, market entry, 25-pt stop / 50-pt target, futures ratchet.
The switch is OFF: this is a measurement, not a trade.

**Bars:** cache (ES_1m_2026-08-03_2026-09-12.csv, NQ_1m_2026-08-03_2026-09-12.csv)
**Alerts:** 2 (after RTH filter and 3-minute dedupe)

## The day

| time ET | sym | dir | micro | room | caller | entry | exit | why | pts | $ market | $ snap* |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 11:21:00 | SPY | short | MES |  |  | 7672.75 | 7659.00 | CLOSE | +13.75 | +$69 | +$80 |
| 15:40:00 | QQQ | long | MNQ |  |  | 29421.25 | 29396.25 | STOP | -25.00 | -$50 | +$0 |

\* the 25-pt-snap entry variant. **Selection-biased** — it only trades the alerts whose level happened to get touched inside ten minutes, which is a filter you cannot apply live. Shown for comparison, never as the headline.

## Totals

|  | trades | gross | net after $1.50 RT | win rate |
|---|---|---|---|---|
| Today (market) | 2 | +$19 | +$16 | 50% |
| Today (snap*) | 2 | +$80 | +$77 | 50% |
| **Since 2026-08-03 (market)** | 149 | **-$721** | -$944 | 43% |

The running total is the market column only — the snap column has no seeded history and is biased anyway.

## By room

| room | trades | gross | wins |
|---|---|---|---|
| — | 2 | +$19 | 1 |

## By symbol and direction

| direction | trades | gross | wins |
|---|---|---|---|
| QQQ long | 1 | -$50 | 0 |
| SPY short | 1 | +$69 | 1 |

## How they ended

| exit | trades | gross |
|---|---|---|
| CLOSE | 1 | +$69 |
| STOP | 1 | -$50 |


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
