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
| 11:28 SPY | Midas | $760.40 | caller posted | partial +50.0% | caller-stated | $1.04 | -99.9% / -75936 (quote-path replay) |
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
| 10:11 QQQ 710C 9/16 @ 3.45 | ELITE OPTIONS: brando-alerts | $3.45 | partial exit posted; price unavailable | exact bid/ask path unavailable |
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
- Our ratchet on the **21 paths with a caller-posted entry**: **-74960 per one-contract replay**.
- Including the one no-price alert at its first recorded ask: **-74965 across all 25 paths**.
- Numeric caller full-exit results on this subset: **8 of 25**; missing caller exit prices prevent an honest aggregate caller P&L.
- Broker-confirmed results override quote-path simulations whenever the bot actually traded.
- Every observed entry is listed: **25 scored + 28 awaiting tape/futures handling = 53**.
- This assumes the caller's posted price filled. It measures trade management from their original entry, not whether that fill was executable for us.
