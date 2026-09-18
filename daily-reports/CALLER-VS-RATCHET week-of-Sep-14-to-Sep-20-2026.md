# CALLER-VS-RATCHET — week of Mon Sep 14 2026 to Sun Sep 20 2026. Newest day first; each day under its ===== header; a re-run replaces that day's block (reports.py).

===== Fri Sep 18 2026 =====

# Caller entry versus our ratchet — 2026-09-18

The caller's posted premium is the hypothetical fill when available. Our 5/3/5 ratchet is replayed against the best available exact-contract bid path: historical OPRA when present, otherwise the live Tastytrade/Webull tapes. Caller exits use their posted price/percentage, or the contemporaneous bid when they posted only the exit time.

| Alert | Source | Hypothetical entry | Entry basis | Caller result | Caller evidence | Our ratchet exit | Our ratchet result |
|---|---|---:|---|---|---|---:|---:|
| 13:24 GOOGL | OWLS all-alerts | $4.00 | first recorded ask; caller price absent | unavailable | no paired caller exit | $4.00 | +0.0% / +0 (quote-path replay) |
| 13:47 FSLY | Brick Alerts | $1.75 | caller posted | partial +40.0% | caller-stated | $1.65 | -5.7% / -10 (quote-path replay) |
| 13:57 HOOD | MuggZone | $4.30 | caller posted | full $4.40 (+2.3%) | market bid at caller exit | $4.10 | -4.7% / -20 (quote-path replay) |
| 15:02 MU | Option Alerts | $4.20 | caller posted | unavailable | no paired caller exit | $4.00 | -4.8% / -20 (quote-path replay) |
| 15:20 TSLA | OWLS all-alerts | $0.45 | caller posted | full $0.34 (-24.4%) | caller-stated | $0.53 | +17.8% / +8 (quote-path replay) |
| 15:20 TSLA | OWLS all-alerts | $0.45 | caller posted | full $0.34 (-24.4%) | caller-stated | $0.53 | +17.8% / +8 (quote-path replay) |
| 15:49 GOOGL | OWLS all-alerts | $4.25 | caller posted | unavailable | no paired caller exit | $3.90 | -8.2% / -35 (quote-path replay) |

## Alerts awaiting an exact path

These rows are still part of the comparison. Their caller evidence is retained; only our ratchet result waits for contract tape.

| Alert | Trader / room | Original entry | Caller result | Ratchet status |
|---|---|---:|---|---|
| 12:57 MU 1000C | OWLS Capital: 🛎️｜all-alerts | — | partial $2.35 | expiry missing; exact contract unresolved |
| 13:43 P 115C 1/16 @ 3.30 | BRICK [I will never DM you]🧱 | $3.30 | unavailable | exact bid/ask path unavailable |

## Result

- Comparable ratchet paths: **7 of 9 observed**.
- Our ratchet on the **6 paths with a caller-posted entry**: **-69 per one-contract replay**.
- Including the no-price alerts at their first recorded ask: **-69 across 7 scorable paths**.
- Numeric caller full-exit results on this subset: **4 of 7**; missing caller exit prices prevent an honest aggregate caller P&L.
- Broker-confirmed results override quote-path simulations whenever the bot actually traded.
- Every observed entry is listed: **7 scored + 2 awaiting tape/futures handling = 9**.
- This assumes the caller's posted price filled. It measures trade management from their original entry, not whether that fill was executable for us.

===== Wed Sep 16 2026 =====

# Caller entry versus our ratchet — 2026-09-16

The caller's posted premium is the hypothetical fill when available. Our 5/3/5 ratchet is replayed against the best available exact-contract bid path: historical OPRA when present, otherwise the live Tastytrade/Webull tapes. Caller exits use their posted price/percentage, or the contemporaneous bid when they posted only the exit time.

| Alert | Source | Hypothetical entry | Entry basis | Caller result | Caller evidence | Our ratchet exit | Our ratchet result |
|---|---|---:|---|---|---|---:|---:|
| 09:34 GOOGL | Honeydrip daytrades | $9.00 | caller posted | unavailable | no paired caller exit | $2.87 | -68.1% / -613 (quote-path replay) |
| 09:38 TSLA | Honeydrip daytrades | $4.96 | caller posted | unavailable | no paired caller exit | $4.50 | -9.3% / -46 (quote-path replay) |
| 09:39 TSLA | Honeydrip daytrades | $3.00 | caller posted | full exit posted; price unavailable | caller exit; price unavailable | $2.70 | -10.0% / -30 (quote-path replay) |
| 09:40 AAPL | Honeydrip daytrades | $3.17 | caller posted | full $2.33 (-26.5%) | market bid at caller exit | $3.15 | -0.6% / -2 (quote-path replay) |
| 09:46 QQQ | Demon day-trades | $1.00 | caller posted | unavailable | no paired caller exit | $1.00 | +0.0% / +0 (quote-path replay) |
| 10:09 AAPL | Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | $2.70 | caller posted | unavailable | no paired caller exit | $2.45 | -9.3% / -25 (quote-path replay) |
| 10:10 AAPL | Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | $10.00 | caller posted | unavailable | no paired caller exit | $2.60 | -74.0% / -740 (quote-path replay) |
| 10:15 NVDA | TTT Lotto | $0.23 | caller posted | unavailable | no paired caller exit | $0.27 | +17.4% / +4 (quote-path replay) |
| 15:33 SPY | OWLS all-alerts | $2.66 | caller posted | partial +25.0% | caller-stated | $3.51 | +32.0% / +85 (quote-path replay) |
| 15:50 SPY | AbTrades Alert Bot | $3.34 | first recorded ask; caller price absent | unavailable | no paired caller exit | $3.51 | +5.1% / +17 (quote-path replay) |
| 15:52 SMH | OWLS all-alerts | $0.72 | caller posted | unavailable | no paired caller exit | $0.78 | +8.3% / +6 (quote-path replay) |

## Alerts awaiting an exact path

These rows are still part of the comparison. Their caller evidence is retained; only our ratchet result waits for contract tape.

| Alert | Trader / room | Original entry | Caller result | Ratchet status |
|---|---|---:|---|---|
| 09:18 MGC @ 4396.60 | Ninjago Futures Radar | $4396.60 | unavailable | futures path; options 5/3/5 does not apply |
| 09:19 MGC @ 4397.10 | NGD: ngd-trades | $4397.10 | unavailable | futures path; options 5/3/5 does not apply |
| 09:22 MGC @ 4395.10 | Ninjago Futures Radar | $4395.10 | unavailable | futures path; options 5/3/5 does not apply |
| 09:27 MNQ @ 29418.00 | Ninjago Futures Radar | $29418.00 | unavailable | futures path; options 5/3/5 does not apply |
| 09:28 MGC @ 4398.95 | Ninjago Futures Radar | $4398.95 | unavailable | futures path; options 5/3/5 does not apply |
| 09:29 MNQ @ 29414.13 | NGD: ngd-trades | $29414.13 | unavailable | futures path; options 5/3/5 does not apply |
| 09:45 META 665P 9/18 @ 5.25 | Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | $5.25 | full exit posted; price unavailable | exact bid/ask path unavailable |
| 09:55 QQQ 713C 9/18 @ 3.66 | EliteOptions \| Brando | $3.66 | unavailable | exact bid/ask path unavailable |
| 10:04 MNQ @ 29449.13 | Ninjago Futures Radar | $29449.13 | unavailable | futures path; options 5/3/5 does not apply |
| 10:05 MNQ @ 29448.50 | NGD: ngd-trades | $29448.50 | unavailable | futures path; options 5/3/5 does not apply |
| 10:06 MNQ @ 29450.88 | Ninjago Futures Radar | $29450.88 | unavailable | futures path; options 5/3/5 does not apply |
| 10:06 MSFT 495P 9/18 @ 5.22 | Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | $5.22 | partial +20.0% | exact bid/ask path unavailable |
| 10:08 MNQ @ 29450.38 | NGD: ngd-trades | $29450.38 | unavailable | futures path; options 5/3/5 does not apply |
| 10:08 QQQ 713C @ 112.00 | Skyy | $112.00 | partial +15.0% | expiry missing; exact contract unresolved |
| 10:09 MNQ @ 29468.88 | Ninjago Futures Radar | $29468.88 | unavailable | futures path; options 5/3/5 does not apply |
| 10:12 MGC @ 4381.05 | Ninjago Futures Radar | $4381.05 | unavailable | futures path; options 5/3/5 does not apply |
| 10:12 MNQ @ 29445.88 | Ninjago Futures Radar | $29445.88 | unavailable | futures path; options 5/3/5 does not apply |
| 10:14 MNQ @ 29436.88 | NGD: ngd-trades | $29436.88 | unavailable | futures path; options 5/3/5 does not apply |
| 14:09 SPY 761C 9/16 @ 2.00 | Honey Drip Network 🍯💰📈: 🇳🇬｜midas-small-account-challenge | $2.00 | full $160/contract (+80.0%) | exact bid/ask path unavailable |
| 14:10 MNQ @ 29508.00 | Ninjago Futures Radar | $29508.00 | unavailable | futures path; options 5/3/5 does not apply |
| 14:16 MNQ @ 29491.13 | Ninjago Futures Radar | $29491.13 | unavailable | futures path; options 5/3/5 does not apply |
| 14:22 MNQ @ 29491.50 | Ninjago Futures Radar | $29491.50 | unavailable | futures path; options 5/3/5 does not apply |
| 14:27 MNQ @ 29453.13 | Ninjago Futures Radar | $29453.13 | unavailable | futures path; options 5/3/5 does not apply |
| 14:28 MNQ @ 29426.50 | NGD: ngd-trades | $29426.50 | unavailable | futures path; options 5/3/5 does not apply |
| 14:29 MNQ @ 29433.13 | NGD: ngd-trades | $29433.13 | unavailable | futures path; options 5/3/5 does not apply |
| 14:30 MNQ @ 29494.88 | Ninjago Futures Radar | $29494.88 | unavailable | futures path; options 5/3/5 does not apply |
| 14:32 MNQ @ 29488.63 | Ninjago Futures Radar | $29488.63 | unavailable | futures path; options 5/3/5 does not apply |
| 14:33 MNQ @ 29402.38 | NGD: ngd-trades | $29402.38 | unavailable | futures path; options 5/3/5 does not apply |
| 14:35 MNQ @ 29401.50 | Ninjago Futures Radar | $29401.50 | unavailable | futures path; options 5/3/5 does not apply |
| 14:36 MNQ @ 29358.13 | NGD: ngd-trades | $29358.13 | unavailable | futures path; options 5/3/5 does not apply |
| 14:37 MNQ @ 29360.75 | Ninjago Futures Radar | $29360.75 | unavailable | futures path; options 5/3/5 does not apply |
| 14:41 MNQ @ 29430.00 | Ninjago Futures Radar | $29430.00 | unavailable | futures path; options 5/3/5 does not apply |
| 14:42 MNQ @ 29431.38 | NGD: ngd-trades | $29431.38 | unavailable | futures path; options 5/3/5 does not apply |
| 14:45 MNQ @ 29454.75 | Ninjago Futures Radar | $29454.75 | unavailable | futures path; options 5/3/5 does not apply |
| 14:46 MNQ @ 29433.75 | NGD: ngd-trades | $29433.75 | unavailable | futures path; options 5/3/5 does not apply |
| 14:48 MNQ @ 29413.25 | Ninjago Futures Radar | $29413.25 | unavailable | futures path; options 5/3/5 does not apply |
| 14:49 MNQ @ 29417.63 | NGD: ngd-trades | $29417.63 | unavailable | futures path; options 5/3/5 does not apply |
| 14:50 MNQ @ 29421.50 | NGD: ngd-trades | $29421.50 | unavailable | futures path; options 5/3/5 does not apply |
| 15:03 MNQ @ 29299.75 | Ninjago Futures Radar | $29299.75 | unavailable | futures path; options 5/3/5 does not apply |
| 15:04 MNQ @ 29289.25 | NGD: ngd-trades | $29289.25 | unavailable | futures path; options 5/3/5 does not apply |
| 15:07 MNQ @ 29375.75 | Ninjago Futures Radar | $29375.75 | unavailable | futures path; options 5/3/5 does not apply |
| 15:08 MNQ @ 29251.13 | NGD: ngd-trades | $29251.13 | unavailable | futures path; options 5/3/5 does not apply |
| 15:09 MNQ @ 29218.63 | NGD: ngd-trades | $29218.63 | unavailable | futures path; options 5/3/5 does not apply |
| 15:10 MNQ @ 29217.63 | Ninjago Futures Radar | $29217.63 | unavailable | futures path; options 5/3/5 does not apply |
| 15:11 MNQ @ 29221.38 | NGD: ngd-trades | $29221.38 | unavailable | futures path; options 5/3/5 does not apply |
| 15:12 MNQ @ 29216.50 | NGD: ngd-trades | $29216.50 | unavailable | futures path; options 5/3/5 does not apply |
| 15:13 MNQ @ 29172.00 | Ninjago Futures Radar | $29172.00 | unavailable | futures path; options 5/3/5 does not apply |
| 15:14 MNQ @ 29162.88 | NGD: ngd-trades | $29162.88 | unavailable | futures path; options 5/3/5 does not apply |
| 15:18 MNQ @ 29192.63 | Ninjago Futures Radar | $29192.63 | unavailable | futures path; options 5/3/5 does not apply |
| 15:20 MNQ @ 29178.25 | Ninjago Futures Radar | $29178.25 | unavailable | futures path; options 5/3/5 does not apply |
| 15:26 MNQ @ 29077.00 | Ninjago Futures Radar | $29077.00 | unavailable | futures path; options 5/3/5 does not apply |
| 15:27 MNQ @ 29077.13 | NGD: ngd-trades | $29077.13 | unavailable | futures path; options 5/3/5 does not apply |
| 15:29 MNQ @ 29175.50 | Ninjago Futures Radar | $29175.50 | unavailable | futures path; options 5/3/5 does not apply |
| 15:31 MNQ @ 29137.25 | Ninjago Futures Radar | $29137.25 | unavailable | futures path; options 5/3/5 does not apply |
| 15:50 MNQ @ 29341.00 | Ninjago Futures Radar | $29341.00 | unavailable | futures path; options 5/3/5 does not apply |

## Result

- Comparable ratchet paths: **11 of 66 observed**.
- Our ratchet on the **10 paths with a caller-posted entry**: **-1361 per one-contract replay**.
- Including the no-price alerts at their first recorded ask: **-1344 across 11 scorable paths**.
- Numeric caller full-exit results on this subset: **2 of 11**; missing caller exit prices prevent an honest aggregate caller P&L.
- Broker-confirmed results override quote-path simulations whenever the bot actually traded.
- Every observed entry is listed: **11 scored + 55 awaiting tape/futures handling = 66**.
- This assumes the caller's posted price filled. It measures trade management from their original entry, not whether that fill was executable for us.

===== Mon Sep 14 2026 =====

# Caller entry versus our ratchet — 2026-09-14

The caller's posted premium is the hypothetical fill when available. Our 5/3/5 ratchet is replayed against the best available exact-contract bid path: historical OPRA when present, otherwise the live Tastytrade/Webull tapes. Caller exits use their posted price/percentage, or the contemporaneous bid when they posted only the exit time.

| Alert | Source | Hypothetical entry | Entry basis | Caller result | Caller evidence | Our ratchet exit | Our ratchet result |
|---|---|---:|---|---|---|---:|---:|
| 10:13 CRWD | MuggZone | $2.35 | caller posted | partial +100.0% | caller-stated | $2.40 | +2.1% / +5 (quote-path replay) |
| 10:21 TSLA | Platinum ei-alerts | $1.42 | caller posted | unavailable | no paired caller exit | $7.50 | +428.2% / +608 (quote-path replay) |
| 10:22 TSLA | Platinum nitro | $1.61 | caller posted | partial +36.0% | caller-stated | $6.40 | +297.5% / +479 (quote-path replay) |
| 10:23 NVDA | Whop Day Trades | $2.40 | real bot fill | full $1.50 (-37.5%) | market bid at caller exit | $2.38 | -0.8% / -2 (broker-confirmed actual) |
| 10:36 QQQ | Demon day-trades | $1.00 | caller posted | unavailable | no paired caller exit | $1.10 | +10.0% / +10 (quote-path replay) |
| 10:41 QQQ | Vero 2 | $1.55 | caller posted | unavailable | no paired caller exit | $1.62 | +4.5% / +7 (quote-path replay) |
| 10:42 MU | Mugzone Options | $2.10 | real fill = caller posted | partial exit posted; price unavailable | caller trim; price unavailable | $2.05 | -2.4% / -5 (broker-confirmed actual) |
| 11:07 DRAM | OWLS all-alerts | $0.57 | first recorded ask; caller price absent | unavailable | no paired caller exit | $0.56 | -1.8% / -1 (quote-path replay) |
| 11:12 MSFT | OWLS all-alerts | $0.85 | caller posted | partial exit posted; price unavailable | caller trim; price unavailable | $0.93 | +9.4% / +8 (quote-path replay) |
| 11:21 QQQ | shabs | $0.75 | caller posted | full $3.92 (+422.7%) | market bid at caller exit | $0.65 | -13.3% / -10 (quote-path replay) |
| 11:24 META | Honeydrip daytrades | $6.50 | caller posted | full exit posted; price unavailable | caller exit; price unavailable | $6.45 | -0.8% / -5 (quote-path replay) |
| 11:28 SPY | Midas | — | unavailable (stock price posted) | partial +50.0% | caller posted a stock price, not a premium — entry unavailable | — | — (excluded from the total) |
| 11:52 TSLA | Mugzone Options | $2.40 | caller posted | unavailable | no paired caller exit | $2.40 | +0.0% / +0 (quote-path replay) |
| 12:13 WMT | Demon day-trades | $0.96 | caller posted | unavailable | no paired caller exit | $0.96 | +0.0% / +0 (quote-path replay) |
| 12:26 GOOGL | OWLS all-alerts | $7.20 | caller posted | partial +26.0% | caller-stated | $7.20 | +0.0% / +0 (quote-path replay) |
| 12:46 AMZN | OWLS all-alerts | $3.97 | caller posted | unavailable | no paired caller exit | $3.40 | -14.4% / -57 (quote-path replay) |
| 13:18 SPY | Midas | $1.25 | caller posted | unavailable | no paired caller exit | $0.63 | -49.6% / -62 (quote-path replay) |
| 13:41 AMZN | OWLS all-alerts | $1.80 | caller posted | unavailable | no paired caller exit | $1.78 | -1.1% / -2 (quote-path replay) |
| 13:53 QQQ | Brando Alerts | $4.04 | caller posted | unavailable | no paired caller exit | $3.78 | -6.4% / -26 (quote-path replay) |
| 14:05 META | Aristotle | $2.64 | first recorded ask; caller price absent | partial +43.0% | caller-stated | $2.62 | -0.8% / -2 (quote-path replay) |
| 14:14 QQQ | shabs | $0.40 | caller posted | unavailable | no paired caller exit | $0.40 | +0.0% / +0 (quote-path replay) |
| 14:20 TSLA | Mugzone Options | $0.37 | first recorded ask; caller price absent | partial +145.0% | caller-stated | $0.37 | +0.0% / +0 (quote-path replay) |
| 15:12 AFRM | OWLS all-alerts | $2.02 | caller posted | unavailable | no paired caller exit | $2.15 | +6.4% / +13 (quote-path replay) |
| 15:13 AFRM | AbTrades | $2.02 | caller posted | unavailable | no paired caller exit | $2.15 | +6.4% / +13 (quote-path replay) |
| 16:02 TSLA | OWLS Capital: 🛎️｜all-alerts | $3.05 | caller posted | unavailable | no paired caller exit | $3.05 | +0.0% / +0 (quote-path replay) |

## Alerts awaiting an exact path

These rows are still part of the comparison. Their caller evidence is retained; only our ratchet result waits for contract tape.

| Alert | Trader / room | Original entry | Caller result | Ratchet status |
|---|---|---:|---|---|
| 09:16 MNQ @ 28883.50 | Ninjago Futures Radar | $28883.50 | unavailable | futures path; options 5/3/5 does not apply |
| 09:18 MNQ @ 28895.63 | Ninjago Futures Radar | $28895.63 | unavailable | futures path; options 5/3/5 does not apply |
| 09:22 MNQ @ 28919.88 | Ninjago Futures Radar | $28919.88 | unavailable | futures path; options 5/3/5 does not apply |
| 09:24 MGC @ 4312.80 | Ninjago Futures Radar | $4312.80 | unavailable | futures path; options 5/3/5 does not apply |
| 10:07 MGC @ 4308.10 | Ninjago Futures Radar | $4308.10 | unavailable | futures path; options 5/3/5 does not apply |
| 10:10 MGC @ 4308.60 | Ninjago Futures Radar | $4308.60 | unavailable | futures path; options 5/3/5 does not apply |
| 10:11 QQQ 710C 9/16 @ 3.45 | ELITE OPTIONS: brando-alerts | $3.45 | partial $5.50 (+59.4%) | exact bid/ask path unavailable |
| 10:18 MNQ @ 29049.75 | Ninjago Futures Radar | $29049.75 | unavailable | futures path; options 5/3/5 does not apply |
| 10:23 MNQ @ 29023.00 | Ninjago Futures Radar | $29023.00 | unavailable | futures path; options 5/3/5 does not apply |
| 10:28 MNQ @ 28998.25 | Ninjago Futures Radar | $28998.25 | unavailable | futures path; options 5/3/5 does not apply |
| 10:30 MGC @ 4310.80 | Ninjago Futures Radar | $4310.80 | unavailable | futures path; options 5/3/5 does not apply |
| 10:30 QQQ 714P 9/10 @ 1.15 | Vero | $1.15 | unavailable | exact bid/ask path unavailable |
| 10:31 MNQ @ 29000.00 | Trademorewiser (MOD) | $29000.00 | partial exit posted; price unavailable | futures path; options 5/3/5 does not apply |
| 10:31 SPY 759P 9/10 @ 1.15 | VeroTrade: ✅⏐vero-trades | $1.15 | unavailable | exact bid/ask path unavailable |
| 10:36 MNQ @ 28977.50 | @Futures Alerts | $28977.50 | full exit posted; price unavailable | futures path; options 5/3/5 does not apply |
| 10:54 MGC @ 4314.90 | Ninjago Futures Radar | $4314.90 | unavailable | futures path; options 5/3/5 does not apply |
| 11:04 MGC @ 4313.20 | Ninjago Futures Radar | $4313.20 | unavailable | futures path; options 5/3/5 does not apply |
| 11:05 MNQ @ 29995.00 | Trademorewiser (MOD) | $29995.00 | unavailable | futures path; options 5/3/5 does not apply |
| 11:13 MNQ @ 28997.50 | Ninjago Futures Radar | $28997.50 | unavailable | futures path; options 5/3/5 does not apply |
| 12:24 MNQ @ 29220.00 | Trademorewiser (MOD) | $29220.00 | unavailable | futures path; options 5/3/5 does not apply |
| 12:39 MCL @ 102.00 | duccimama | $102.00 | unavailable | futures path; options 5/3/5 does not apply |
| 14:43 MNQ @ 29269.00 | Ninjago Futures Radar | $29269.00 | unavailable | futures path; options 5/3/5 does not apply |
| 14:56 MNQ @ 29265.88 | Ninjago Futures Radar | $29265.88 | unavailable | futures path; options 5/3/5 does not apply |
| 15:25 MNQ @ 29223.25 | Ninjago Futures Radar | $29223.25 | unavailable | futures path; options 5/3/5 does not apply |
| 15:41 MNQ @ 29222.00 | Ninjago Futures Radar | $29222.00 | unavailable | futures path; options 5/3/5 does not apply |
| 15:47 MNQ @ 29218.13 | Ninjago Futures Radar | $29218.13 | unavailable | futures path; options 5/3/5 does not apply |
| 15:51 MNQ @ 29181.13 | Ninjago Futures Radar | $29181.13 | unavailable | futures path; options 5/3/5 does not apply |
| 15:55 MNQ @ 29199.63 | Ninjago Futures Radar | $29199.63 | unavailable | futures path; options 5/3/5 does not apply |

## Result

- Comparable ratchet paths: **25 of 53 observed**.
- Our ratchet on the **20 paths with a caller-posted entry**: **+976 per one-contract replay**.
- Including the no-price alerts at their first recorded ask: **+971 across 24 scorable paths**.
- Numeric caller full-exit results on this subset: **7 of 24**; missing caller exit prices prevent an honest aggregate caller P&L.
- **1 row excluded from every dollar total** because the caller posted the STOCK price where the premium belongs (11:28 SPY @ 760.40). The row stays visible; its P&L would be nonsense. Same rule the live OPEN path has refused since v3.8.24.
- Broker-confirmed results override quote-path simulations whenever the bot actually traded.
- Every observed entry is listed: **25 scored + 28 awaiting tape/futures handling = 53**.
- This assumes the caller's posted price filled. It measures trade management from their original entry, not whether that fill was executable for us.
