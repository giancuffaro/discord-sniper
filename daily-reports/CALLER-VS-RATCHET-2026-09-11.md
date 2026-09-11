# Caller entry versus our ratchet — 2026-09-11

The caller's posted premium is the hypothetical fill when available. Our 5/3/5 ratchet is replayed against the recorded Tastytrade bid path. Caller exits use their posted price/percentage, or the contemporaneous bid when they posted only the exit time.

| Alert | Source | Hypothetical entry | Entry basis | Caller result | Caller evidence | Our ratchet exit | Our ratchet result |
|---|---|---:|---|---|---|---:|---:|
| 10:01 NVDA | Platinum nitro | $2.15 | caller posted | full exit posted; price unavailable | caller exit; price unavailable | $2.04 | -5.1% / -11 (quote-path replay) |
| 10:25 TSLA | Platinum nitro | $1.79 | caller posted | full $1.24 (-30.7%) | market bid at caller exit | $1.79 | +0.0% / +0 (quote-path replay) |
| 10:37 NVDA | Platinum nitro | $0.97 | caller posted | full $0.98 (+1.0%) | market bid at caller exit | $0.84 | -13.4% / -13 (quote-path replay) |
| 12:01 HOOD | Honeydrip daytrades | $0.05 | first recorded ask; caller price absent | full -6.0% | caller-stated | $0.01 | -80.0% / -4 (quote-path replay) |
| 12:40 CPS | Demon day-trades | $0.65 | real fill = caller posted | unavailable | no paired caller exit | $0.70 | +7.7% / +5 (broker-confirmed actual) |

## Alerts awaiting an exact path

These rows are still part of the comparison. Their caller evidence is retained; only our ratchet result waits for contract tape.

| Alert | Trader / room | Original entry | Caller result | Ratchet status |
|---|---|---:|---|---|
| 09:39 QCOM 185C @ 0.97 | OWLS Capital: 🛎️｜all-alerts | $0.97 | unavailable | expiry missing; exact contract unresolved |
| 09:42 NVDA 220C 9/16 @ 3.06 | Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | $3.06 | full exit posted; price unavailable | exact bid/ask path unavailable |
| 09:42 DELL 560C @ 1.05 | OWLS Capital: 🌟｜muggzone-options | $1.05 | partial +185.0% | expiry missing; exact contract unresolved |
| 09:42 MNQ short @ 29462.375 | recovered reader outage | $29462.38 | unavailable | futures path; options 5/3/5 does not apply |
| 09:50 HPE 62C 0DTE | OWLS Capital: 🌟｜muggzone-options | — | partial +92.0% | exact bid/ask path unavailable |
| 09:54 MNQ @ 29483.88 | Ninjago Futures Radar | $29483.88 | unavailable | futures path; options 5/3/5 does not apply |
| 10:00 MU 990C 0DTE @ 2.86 | MuggZone | $2.86 | partial $2.40 (-16.1%) | exact bid/ask path unavailable |
| 10:05 HIMS 29C 9/18 | MuggZone | $0.42 | unavailable | exact bid/ask path unavailable |
| 10:12 TSLA 360P 9/16 @ 5.15 | Unraveller | $5.15 | full exit posted; price unavailable | exact bid/ask path unavailable |
| 10:23 AAPL 335C 9/11 @ 0.65 | Demon × LKS | $0.65 | partial $1.05 (+61.5%) | exact bid/ask path unavailable |
| 10:35 SPX 7700C @ 1.05 | OWLS Capital: 🌟｜shabs-sky-alerts | $1.05 | partial $500/contract (+476.2%) | expiry missing; exact contract unresolved |
| 10:38 MGC @ 4422.60 | Ninjago Futures Radar | $4422.60 | unavailable | futures path; options 5/3/5 does not apply |
| 10:39 AMZN 255C 9/14 @ 2.05 | Mike | $2.05 | full exit posted; price unavailable | exact bid/ask path unavailable |
| 10:48 MNQ @ 29340.00 | @Futures Alerts | $29340.00 | unavailable | futures path; options 5/3/5 does not apply |
| 10:50 HOOD 118C 9/18 @ 2.50 | Brett | $2.50 | partial +10.0% | exact bid/ask path unavailable |
| 10:54 AAPL 335C 0DTE @ 1.46 | Honey Drip Network 🍯💰📈: 🇳🇬｜midas-small-account-challenge | $1.46 | partial +22.0% | exact bid/ask path unavailable |
| 11:13 MU 980C 0DTE @ 3.00 | Honey Drip Network 🍯💰📈: 👑｜aristotle-trades | $3.00 | partial +40.0% | exact bid/ask path unavailable |
| 11:13 MNQ @ 29411.75 | NGD: ngd-trades | $29411.75 | unavailable | futures path; options 5/3/5 does not apply |
| 11:16 MNQ @ 29377.50 | NGD: ngd-trades | $29377.50 | unavailable | futures path; options 5/3/5 does not apply |
| 11:18 MNQ @ 29413.00 | NGD: ngd-trades | $29413.00 | unavailable | futures path; options 5/3/5 does not apply |
| 11:21 SPY 766P 0DTE @ 1.29 | Midas (Admin) | $1.29 | unavailable | exact bid/ask path unavailable |
| 13:10 ORCL 165C 9/18 @ 1.30 | MuggZone | $1.30 | unavailable | exact bid/ask path unavailable |
| 13:27 RKLB 70C 9/25 @ 1.39 | OWLS Capital: 🌟｜muggzone-options | $1.39 | unavailable | exact bid/ask path unavailable |
| 14:06 MNQ @ 29449.25 | Ninjago Futures Radar | $29449.25 | unavailable | futures path; options 5/3/5 does not apply |
| 14:06 SHOP 150C 11/20 @ 6.80 | BRICK [I will never DM you]🧱 | $6.80 | unavailable | exact bid/ask path unavailable |
| 15:22 IBM 250C 9/18 @ 1.70 | Demon × LKS | $1.70 | partial $2.20 (+29.4%) | exact bid/ask path unavailable |
| 15:32 HAL 38C 10/16 @ 0.77 | sloth  legooman NR100 | $0.77 | unavailable | exact bid/ask path unavailable |
| 15:40 QQQ 716C 9/11 @ 0.15 | TradingTheTrend | $0.15 | partial $0.24 (+60.0%) | exact bid/ask path unavailable |
| 15:53 SPY 772C 9/18 @ 1.73 | TradingTheTrend | $1.73 | unavailable | exact bid/ask path unavailable |

## Result

- Comparable ratchet paths: **5 of 34 observed**.
- Our ratchet on the **4 paths with a caller-posted entry**: **-19 per one-contract replay**.
- Including the one no-price alert at its first recorded ask: **-23 across all 5 paths**.
- Numeric caller full-exit results on this subset: **3 of 5**; missing caller exit prices prevent an honest aggregate caller P&L.
- Broker-confirmed results override quote-path simulations whenever the bot actually traded.
- Every observed entry is listed: **5 scored + 29 awaiting tape/futures handling = 34**.
- This assumes the caller's posted price filled. It measures trade management from their original entry, not whether that fill was executable for us.
