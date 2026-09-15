# RATCHET-COMPARE — week of Mon Sep 14 2026 to Sun Sep 20 2026. Newest day first; each day under its ===== header; a re-run replaces that day's block (reports.py).

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
