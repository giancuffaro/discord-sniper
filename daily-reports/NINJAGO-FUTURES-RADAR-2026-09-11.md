# Ninjago Futures Radar replay — 2026-09-11

## Method

Source alerts: `daily-audits/raw-2026-09-11-discord-log.json`, deduplicated by literal instrument, direction, entry, target, and stop. Price sources: retained one-minute continuous futures bars: `bars/NQ_1m_2026-08-03_2026-09-12.csv` and `bars/MGC_1m_2026-09-11.csv` (Databento GLBX.MDP3).

A trade is counted only when the stated entry is on that contract's tick grid and the price trades after the post. The stated target or stop determines the exit. If both occurred in one one-minute bar, the trade would be `unavailable`; none of the counted trades has that ambiguity. This is a market-data replay, not a broker fill: it excludes spread, slippage, and commissions.

## Result

| Posted ET | Signal | Entry | Target / stop | Result | Points | Gross, 1 MNQ |
|---|---|---:|---:|---|---:|---:|
| 11:13 | MNQ short | 29411.75 | 29381.75 / 29431.75 | Stop at 11:16 | -20 | -$40 |
| 11:18 | MNQ short | 29413.00 | 29383.00 / 29433.00 | Stop at 12:33 | -20 | -$40 |
| 14:06 | MNQ short | 29449.25 | 29419.25 / 29469.25 | Target at 14:20 | +30 | +$60 |

**Literal, valid, filled MNQ signals: 3. Win rate: 33.3%. Gross result: -10 points / -$20 per MNQ contract.**

## Not filled / not scored

| Posted ET | Signal | Why |
|---|---|---|
| 09:54 | MNQ short 29483.875 | The quoted entry is not a valid MNQ tick ($0.25 grid). Rounding it would change the caller's signal, so it is excluded. |
| 10:56 | MGC long 4422.60 | MGC bars are now retained. From 10:57 AM–4:00 PM ET, the highest print was 4383.80, so the stated entry never filled. |
| 11:16 | MNQ long 29377.50 | The entry did not trade again during regular hours after the alert. It first touched after 4:00 PM ET, so it is treated as unfilled rather than an overnight trade. |

The unfilled rows do not affect P&L. This scores only literal, time-aligned fills and does not grade the channel as a whole.
