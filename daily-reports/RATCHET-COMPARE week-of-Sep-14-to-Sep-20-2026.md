# RATCHET-COMPARE — week of Mon Sep 14 2026 to Sun Sep 20 2026. Newest day first; each day under its ===== header; a re-run replaces that day's block (reports.py).

===== Tue Sep 15 2026 =====

# Ratchet comparison — 2026-09-15

This replay isolates the exit rule. Both versions buy **one contract** at the first recorded ask (the actual fill for a filled bot trade) and use the same initial broker-compatible **-10% born stop**. The fixed version never moves that stop. The live version arms at **+10%** and then advances in **+10%** rungs, subject to tick and spread floors.

| Alert | Source | Entry | Fixed stop P&L | Ratchet P&L | Ratchet advantage |
|---|---|---:|---:|---:|---:|
| 09:41 TSLA | Platinum nitro | $1.72 | -17 | -17 | +0 |
| 09:42 AMD | Honeydrip daytrades | $5.25 | -55 | -55 | +0 |
| 09:46 META | Demon day-trades | $1.89 | -19 | -4 | +15 |
| 09:47 META | Demon day-trades | $1.88 | -18 | -3 | +15 |
| 09:50 TSLA | Platinum nitro | $1.48 | -14 | -14 | +0 |
| 09:53 TSLA | Platinum nitro | $1.19 | -20 | -20 | +0 |
| 09:57 SPY | Honeydrip daytrades | $3.00 | +38 | +145 | +107 |
| 10:01 AAPL | Honeydrip daytrades | $3.25 | -35 | +0 | +35 |
| 10:07 QQQ | Platinum nitro | $1.50 | +101 | +30 | -71 |
| 10:14 CRWD | Shoof Alerts | $4.55 | -50 | -50 | +0 |
| 10:14 CRWD | Shoof Alerts | $4.50 | -50 | -50 | +0 |
| 10:48 QQQ | Vero 1 | $1.42 | -12 | +40 | +52 |
| 10:51 TSLA | Honeydrip daytrades | $3.40 | -35 | -35 | +0 |
| 10:56 TSLA | Honeydrip daytrades | $3.25 | -37 | -37 | +0 |
| 11:03 QQQ | Demon day-trades | $0.68 | -8 | -8 | +0 |
| 11:03 QQQ | Demon day-trades | $0.61 | -6 | -6 | +0 |
| 11:32 AMD | Honeydrip daytrades | $5.50 | -50 | -50 | +0 |
| 11:33 AMD | Honeydrip daytrades | $5.45 | -55 | +0 | +55 |
| 12:25 MU | OWLS all-alerts | $3.95 | -35 | -35 | +0 |
| 12:25 MU | OWLS all-alerts | $3.70 | -40 | -40 | +0 |
| 12:50 CRWD | Shoof Alerts | $3.65 | -35 | -35 | +0 |
| 13:20 NVDA | OWLS all-alerts | $0.11 | -3 | -3 | +0 |
| 13:36 TSLA | Honeydrip daytrades | $3.90 | -40 | -40 | +0 |
| 13:36 TSLA | Honeydrip daytrades | $3.78 | -38 | -38 | +0 |
| 14:57 HOOD | AbTrades Alert Bot | $1.32 | +25 | +25 | +0 |
| 14:57 HOOD | AbTrades Alert Bot | $1.33 | +24 | +24 | +0 |
| 15:00 QQQ | ? | $1.37 | -12 | -12 | +0 |

## Result

- Price-replayable alerts: **27 of 68 observed**.
- Fixed born stop: **-496** total per one-contract replay.
- Live ratchet: **-288** total per one-contract replay.
- Ratchet advantage on the covered subset: **+208**.
- **41 alerts cannot be scored yet** because no exact-contract bid/ask path was recorded. This subset cannot establish the winner for the entire day.
- At least one value is marked at the end of its available tape and is not a final exit.
- HOOD is deliberately included because the question asks what happened if every alert were forced through. The live bot refused its 22% spread; bypassing that filter would have produced the replayed loss.

## Actual bot trade

- 09:47 META realized **-13**. The quote replay gives fixed **-18** versus ratchet **-3**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 09:53 TSLA realized **-8**. The quote replay gives fixed **-20** versus ratchet **-20**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:14 CRWD realized **+0**. The quote replay gives fixed **-50** versus ratchet **-50**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:56 TSLA realized **-20**. The quote replay gives fixed **-37** versus ratchet **-37**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 11:03 QQQ realized **-3**. The quote replay gives fixed **-6** versus ratchet **-6**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 11:33 AMD realized **-25**. The quote replay gives fixed **-55** versus ratchet **+0**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 12:25 MU realized **-20**. The quote replay gives fixed **-40** versus ratchet **-40**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 13:36 TSLA realized **-43**. The quote replay gives fixed **-38** versus ratchet **-38**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 14:57 HOOD realized **+0**. The quote replay gives fixed **+24** versus ratchet **+24**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 15:00 QQQ realized **-30**. The quote replay gives fixed **-12** versus ratchet **-12**; the real ratchet fill was better because the market sell completed above the trigger bid.

===== Mon Sep 14 2026 =====

# Ratchet comparison — 2026-09-14

This replay isolates the exit rule. Both versions buy **one contract** at the first recorded ask (the actual fill for a filled bot trade) and use the same initial broker-compatible **-5% born stop**. The fixed version never moves that stop. The live version arms at **+3%** and then advances in **+5%** rungs, subject to tick and spread floors.

| Alert | Source | Entry | Fixed stop P&L | Ratchet P&L | Ratchet advantage |
|---|---|---:|---:|---:|---:|
| 09:58 SPY | ? | $0.72 | -3 | +0 | +3 |
| 10:13 CRWD | Mugzone Options | $2.52 | -17 | -2 | +15 |
| 10:21 TSLA | Platinum ei-alerts | $7.80 | -40 | -40 | +0 |
| 10:22 TSLA | Platinum nitro | $6.55 | -35 | +30 | +65 |
| 10:23 NVDA | Whop Day Trades | $2.39 | -14 | -1 | +13 |
| 10:23 NVDA | Whop Day Trades | $2.40 | -12 | +0 | +12 |
| 10:24 TSLA | Platinum ei-alerts | $7.40 | -40 | -40 | +0 |
| 10:36 QQQ | Demon day-trades | $1.10 | -5 | +0 | +5 |
| 10:36 QQQ | Demon day-trades | $1.13 | -8 | +0 | +8 |
| 10:41 QQQ | Vero 2 | $1.61 | -7 | -1 | +6 |
| 10:42 MU | Mugzone Options | $2.26 | -16 | -16 | +0 |
| 10:42 MU | Mugzone Options | $2.10 | -10 | -10 | +0 |
| 10:42 QQQ | Vero 2 | $1.41 | -7 | -7 | +0 |
| 11:07 DRAM | OWLS all-alerts | $0.57 | -17 | -1 | +16 |
| 11:12 MSFT | OWLS all-alerts | $0.93 | -12 | +0 | +12 |
| 11:15 MSFT | OWLS all-alerts | $0.65 | -15 | +2 | +17 |
| 11:21 QQQ | shabs | $0.72 | -7 | +0 | +7 |
| 11:24 META | Honeydrip daytrades | $6.80 | -35 | -35 | +0 |
| 11:25 META | Honeydrip daytrades | $6.65 | -35 | -35 | +0 |
| 11:28 SPY | Midas | $1.10 | -6 | -6 | +0 |
| 11:52 TSLA | Mugzone Options | $2.46 | -12 | -12 | +0 |
| 12:02 TSLA | Mugzone Options | $2.38 | +67 | -1 | -68 |
| 12:13 WMT | Demon day-trades | $0.97 | -7 | +0 | +7 |
| 12:26 GOOGL | OWLS all-alerts | $7.30 | +110 | +0 | -110 |
| 12:46 AMZN | OWLS all-alerts | $3.60 | -20 | +20 | +40 |
| 13:18 SPY | Midas | $0.73 | -10 | +4 | +14 |
| 13:41 AMZN | OWLS all-alerts | $1.90 | -12 | -12 | +0 |
| 13:53 QQQ | Brando Alerts | $4.04 | -26 | -26 | +0 |
| 13:53 QQQ | Brando Alerts | $4.03 | -25 | -25 | +0 |
| 14:05 META | Aristotle | $2.64 | -14 | -2 | +12 |
| 14:05 META | Aristotle | $2.61 | -11 | +7 | +18 |
| 14:14 QQQ | shabs | $0.41 | -6 | +2 | +8 |
| 14:20 TSLA | Mugzone Options | $0.37 | -7 | +0 | +7 |
| 14:22 QQQ | shabs | $0.24 | -9 | +0 | +9 |
| 15:12 AFRM | OWLS all-alerts | $2.10 | +5 | +5 | +0 |

## Result

- Price-replayable alerts: **35 of 53 observed**.
- Fixed born stop: **-318** total per one-contract replay.
- Live ratchet: **-202** total per one-contract replay.
- Ratchet advantage on the covered subset: **+116**.
- **18 alerts cannot be scored yet** because no exact-contract bid/ask path was recorded. This subset cannot establish the winner for the entire day.
- At least one value is marked at the end of its available tape and is not a final exit.
- HOOD is deliberately included because the question asks what happened if every alert were forced through. The live bot refused its 22% spread; bypassing that filter would have produced the replayed loss.

## Actual bot trade

- 09:58 SPY realized **+36**. The quote replay gives fixed **-3** versus ratchet **+0**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:23 NVDA realized **-2**. The quote replay gives fixed **-12** versus ratchet **+0**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:24 TSLA realized **-34**. The quote replay gives fixed **-40** versus ratchet **-40**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:36 QQQ realized **+0**. The quote replay gives fixed **-8** versus ratchet **+0**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:42 MU realized **-5**. The quote replay gives fixed **-10** versus ratchet **-10**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:42 QQQ realized **-2**. The quote replay gives fixed **-7** versus ratchet **-7**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 11:15 MSFT realized **-4**. The quote replay gives fixed **-15** versus ratchet **+2**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 11:25 META realized **-45**. The quote replay gives fixed **-35** versus ratchet **-35**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 12:02 TSLA realized **-4**. The quote replay gives fixed **+67** versus ratchet **-1**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 14:05 META realized **+7**. The quote replay gives fixed **-11** versus ratchet **+7**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 14:22 QQQ realized **-2**. The quote replay gives fixed **-9** versus ratchet **+0**; the real ratchet fill was better because the market sell completed above the trigger bid.
