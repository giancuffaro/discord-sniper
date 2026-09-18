# RATCHET-COMPARE — week of Mon Sep 14 2026 to Sun Sep 20 2026. Newest day first; each day under its ===== header; a re-run replaces that day's block (reports.py).

===== Fri Sep 18 2026 =====

# Ratchet comparison — 2026-09-18

This replay isolates the exit rule. Both versions buy **one contract** at the first recorded ask (the actual fill for a filled bot trade) and use the same initial broker-compatible **-5% born stop**. The fixed version never moves that stop. The live version arms at **+3%** and then advances in **+5%** rungs, subject to tick and spread floors.

| Alert | Source | Entry | Fixed stop P&L | Ratchet P&L | Ratchet advantage |
|---|---|---:|---:|---:|---:|
| 13:24 GOOGL | OWLS all-alerts | $4.00 | -60 | +0 | +60 |
| 13:47 FSLY | Brick Alerts | $1.80 | -10 | -10 | +0 |
| 13:57 HOOD | OWLS all-alerts | $4.40 | -20 | -20 | +0 |
| 15:02 MU | Option Alerts | $4.35 | -30 | -30 | +0 |
| 15:20 TSLA | OWLS all-alerts | $0.47 | -8 | +3 | +11 |
| 15:24 TSLA | OWLS all-alerts | $0.33 | -8 | -1 | +7 |
| 15:49 GOOGL | OWLS all-alerts | $4.30 | -40 | -40 | +0 |

## Result

- Price-replayable alerts: **7 of 9 observed**.
- Fixed born stop: **-176** total per one-contract replay.
- Live ratchet: **-98** total per one-contract replay.
- Ratchet advantage on the covered subset: **+78**.
- **2 alerts cannot be scored yet** because no exact-contract bid/ask path was recorded. This subset cannot establish the winner for the entire day.
- Every replayed path reached a stop, so none of the values above is an end-of-tape mark.
- HOOD is deliberately included because the question asks what happened if every alert were forced through. The live bot refused its 22% spread; bypassing that filter would have produced the replayed loss.

## Actual bot trade

- 15:24 TSLA realized **+5**. The quote replay gives fixed **-8** versus ratchet **-1**; the real ratchet fill was better because the market sell completed above the trigger bid.

===== Thu Sep 17 2026 =====

# Ratchet comparison — 2026-09-17

This replay isolates the exit rule. Both versions buy **one contract** at the first recorded ask (the actual fill for a filled bot trade) and use the same initial broker-compatible **-5% born stop**. The fixed version never moves that stop. The live version arms at **+3%** and then advances in **+5%** rungs, subject to tick and spread floors.

| Alert | Source | Entry | Fixed stop P&L | Ratchet P&L | Ratchet advantage |
|---|---|---:|---:|---:|---:|
| 09:33 GOOGL | Honeydrip daytrades | $4.65 | -55 | -55 | +0 |
| 09:36 SPY | Vero 1 | $1.40 | -9 | -9 | +0 |
| 09:39 GOOGL | Honeydrip daytrades | $4.35 | -35 | -35 | +0 |
| 09:39 SNDK | Aristotle | $1.20 | -20 | +30 | +50 |
| 09:39 SNDK | Aristotle | $1.25 | -10 | +25 | +35 |
| 09:40 SPY | Honeydrip daytrades | $2.51 | -11 | -4 | +7 |
| 09:40 TSLA | Honeydrip daytrades | $3.30 | -20 | -20 | +0 |
| 09:42 QQQ | Demon day-trades | $0.90 | -12 | -1 | +11 |
| 09:56 NVDA | Whop Day Trades | $2.53 | +45 | -2 | -47 |
| 09:56 NVDA | Whop Day Trades | $2.55 | +43 | -4 | -47 |
| 09:56 AMD | Aristotle | $2.28 | -19 | -19 | +0 |
| 09:58 GOOGL | Honeydrip daytrades | $4.60 | -55 | -55 | +0 |
| 10:02 TSLA | Platinum nitro | $1.96 | -11 | -4 | +7 |
| 10:03 MRNA | OWLS all-alerts | $1.85 | -10 | +0 | +10 |
| 10:03 MRNA | OWLS all-alerts | $1.85 | -10 | +0 | +10 |
| 10:05 TSLA | Honeydrip daytrades | $3.75 | -15 | -15 | +0 |
| 10:09 TSLA | Platinum ei-alerts | $1.41 | -12 | +18 | +30 |
| 10:12 TSLA | Platinum ei-alerts | $1.22 | -11 | +2 | +13 |
| 10:14 SPY | Honeydrip daytrades | $2.40 | -10 | +0 | +10 |
| 10:14 SPY | Honeydrip daytrades | $2.41 | -11 | -1 | +10 |
| 10:16 QQQ | Brando Alerts | $2.95 | -15 | -1 | +14 |
| 10:16 QQQ | Brando Alerts | $2.95 | -15 | -1 | +14 |
| 10:17 INTC | Aristotle small | $1.98 | +24 | +10 | -14 |
| 10:17 INTC | Aristotle | $2.04 | +18 | +0 | -18 |
| 10:19 AMZN | Honeydrip daytrades | $2.27 | +123 | +21 | -102 |
| 10:19 INTC | Aristotle | $2.06 | -14 | +9 | +23 |
| 10:23 ORCL | OWLS all-alerts | $1.65 | -10 | +0 | +10 |
| 10:23 ORCL | OWLS all-alerts | $1.65 | -10 | +0 | +10 |
| 10:23 QQQ | Vero 1 | $1.45 | -5 | -5 | +0 |
| 10:24 QQQ | Vero 1 | $1.39 | -12 | +7 | +19 |
| 10:25 AMZN | OWLS all-alerts | $3.25 | -25 | -25 | +0 |
| 10:26 ORCL | OWLS all-alerts | $1.28 | -18 | -18 | +0 |
| 10:28 QQQ | Vero 1 | $1.66 | -8 | -8 | +0 |
| 10:29 QQQ | Vero 1 | $1.40 | -5 | +0 | +5 |
| 10:44 SMCI | Mugzone Options | $1.55 | +22 | +12 | -10 |
| 10:44 SMCI | Mugzone Options | $1.50 | +27 | +14 | -13 |
| 10:56 QQQ | Vero 2 | $1.37 | -7 | -7 | +0 |
| 10:56 QQQ | Vero 2 | $1.32 | -7 | -7 | +0 |
| 12:05 AAPL | TTT Lotto | $0.62 | -7 | +0 | +7 |
| 12:18 INGM | Demon day-trades | $0.65 | -35 | -35 | +0 |
| 12:22 AMD | OWLS all-alerts | $382.65 | -940 | -940 | +0 |
| 12:23 AAPL | Demon day-trades | $1.48 | -8 | +0 | +8 |
| 12:29 AAPL | Demon day-trades | $1.40 | -5 | +0 | +5 |
| 12:45 DELL | Brando Alerts | $5.25 | -30 | -30 | +0 |
| 12:45 DELL | Brando Alerts | $4.95 | -25 | +0 | +25 |
| 12:45 DELL | Brando Alerts | $5.15 | -40 | -40 | +0 |
| 12:45 DELL | Brando Alerts | $4.95 | -25 | +0 | +25 |
| 15:41 HOOD | OWLS all-alerts | $1.00 | +45 | +10 | -35 |
| 15:54 LRCX | Option Alerts | $2.86 | -28 | -28 | +0 |

## Result

- Price-replayable alerts: **49 of 40 observed**.
- Fixed born stop: **-1283** total per one-contract replay.
- Live ratchet: **-1211** total per one-contract replay.
- Ratchet advantage on the covered subset: **+72**.
- At least one value is marked at the end of its available tape and is not a final exit.
- HOOD is deliberately included because the question asks what happened if every alert were forced through. The live bot refused its 22% spread; bypassing that filter would have produced the replayed loss.

## Actual bot trade

- 09:39 SNDK realized **+0**. The quote replay gives fixed **-10** versus ratchet **+25**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 09:56 NVDA realized **+14**. The quote replay gives fixed **+43** versus ratchet **-4**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:03 MRNA realized **+0**. The quote replay gives fixed **-10** versus ratchet **+0**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:12 TSLA realized **+3**. The quote replay gives fixed **-11** versus ratchet **+2**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:14 SPY realized **+0**. The quote replay gives fixed **-11** versus ratchet **-1**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:17 INTC realized **+1**. The quote replay gives fixed **+18** versus ratchet **+0**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:23 ORCL realized **+0**. The quote replay gives fixed **-10** versus ratchet **+0**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:24 QQQ realized **+0**. The quote replay gives fixed **-12** versus ratchet **+7**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:29 QQQ realized **+0**. The quote replay gives fixed **-5** versus ratchet **+0**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:44 SMCI realized **-8**. The quote replay gives fixed **+27** versus ratchet **+14**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 10:56 QQQ realized **-8**. The quote replay gives fixed **-7** versus ratchet **-7**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 12:29 AAPL realized **+0**. The quote replay gives fixed **-5** versus ratchet **+0**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 12:45 DELL realized **+0**. The quote replay gives fixed **-25** versus ratchet **+0**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 12:45 DELL realized **+0**. The quote replay gives fixed **-25** versus ratchet **+0**; the real ratchet fill was better because the market sell completed above the trigger bid.

===== Wed Sep 16 2026 =====

# Ratchet comparison — 2026-09-16

This replay isolates the exit rule. Both versions buy **one contract** at the first recorded ask (the actual fill for a filled bot trade) and use the same initial broker-compatible **-10% born stop**. The fixed version never moves that stop. The live version arms at **+10%** and then advances in **+10%** rungs, subject to tick and spread floors.

| Alert | Source | Entry | Fixed stop P&L | Ratchet P&L | Ratchet advantage |
|---|---|---:|---:|---:|---:|
| 09:34 GOOGL | Honeydrip daytrades | $3.25 | -38 | -38 | +0 |
| 09:38 TSLA | Honeydrip daytrades | $4.95 | -45 | -45 | +0 |
| 09:39 TSLA | Honeydrip daytrades | $2.91 | -31 | -31 | +0 |
| 09:39 TSLA | Honeydrip daytrades | $4.80 | -50 | -50 | +0 |
| 09:40 TSLA | Honeydrip daytrades | $2.65 | -25 | -25 | +0 |
| 09:40 AAPL | Honeydrip daytrades | $3.45 | -35 | -35 | +0 |
| 09:41 AAPL | Honeydrip daytrades | $3.40 | -30 | -30 | +0 |
| 09:41 TSLA | Honeydrip daytrades | $2.64 | -24 | -24 | +0 |
| 09:46 QQQ | Demon day-trades | $1.11 | -11 | -11 | +0 |
| 10:15 NVDA | TTT Lotto | $0.24 | -4 | +4 | +8 |
| 15:33 SPY | OWLS all-alerts | $2.91 | +60 | +60 | +0 |
| 15:50 SPY | AbTrades Alert Bot | $3.34 | +17 | +17 | +0 |
| 15:52 SMH | OWLS all-alerts | $0.80 | -2 | -2 | +0 |

## Result

- Price-replayable alerts: **13 of 66 observed**.
- Fixed born stop: **-218** total per one-contract replay.
- Live ratchet: **-210** total per one-contract replay.
- Ratchet advantage on the covered subset: **+8**.
- **53 alerts cannot be scored yet** because no exact-contract bid/ask path was recorded. This subset cannot establish the winner for the entire day.
- At least one value is marked at the end of its available tape and is not a final exit.
- HOOD is deliberately included because the question asks what happened if every alert were forced through. The live bot refused its 22% spread; bypassing that filter would have produced the replayed loss.

## Actual bot trade

- 09:39 TSLA realized **-50**. The quote replay gives fixed **-50** versus ratchet **-50**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 09:40 TSLA realized **-32**. The quote replay gives fixed **-25** versus ratchet **-25**; the real ratchet fill was better because the market sell completed above the trigger bid.
- 09:41 AAPL realized **-47**. The quote replay gives fixed **-30** versus ratchet **-30**; the real ratchet fill was better because the market sell completed above the trigger bid.

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
