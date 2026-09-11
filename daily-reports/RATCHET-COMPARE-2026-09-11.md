# Ratchet comparison — 2026-09-11

This replay isolates the exit rule. Both versions buy **one contract** at the first recorded ask (the actual fill for a filled bot trade) and use the same initial broker-compatible **-5% born stop**. The fixed version never moves that stop. The live version arms at **+3%** and then advances in **+5%** rungs, subject to tick and spread floors.

| Alert | Source | Entry | Fixed stop P&L | Ratchet P&L | Ratchet advantage |
|---|---|---:|---:|---:|---:|
| 10:01 NVDA | Platinum nitro | $2.11 | -11 | -11 | +0 |
| 10:25 TSLA | Platinum nitro | $1.82 | -8 | -3 | +5 |
| 10:37 NVDA | Platinum nitro | $0.90 | -6 | +0 | +6 |
| 12:01 HOOD | Honeydrip daytrades | $0.05 | -4 | -4 | +0 |
| 12:40 CPS | Demon day-trades | $0.65 | -10 | +0 | +10 |

## Result

- Price-replayable alerts: **5 of 34 observed**.
- Fixed born stop: **-39** total per one-contract replay.
- Live ratchet: **-18** total per one-contract replay.
- Ratchet advantage on the covered subset: **+21**.
- **29 alerts cannot be scored yet** because no exact-contract bid/ask path was recorded. This subset cannot establish the winner for the entire day.
- Every replayed path reached a stop, so none of the values above is an end-of-tape mark.
- HOOD is deliberately included because the question asks what happened if every alert were forced through. The live bot refused its 22% spread; bypassing that filter would have produced the replayed loss.

## Actual bot trade

- 12:40 CPS realized **+5**. The quote replay gives fixed **-10** versus ratchet **+0**; the real ratchet fill was better because the market sell completed above the trigger bid.
