# ALERT-LEDGER — week of Mon Sep 14 2026 to Sun Sep 20 2026. Newest day first; each day under its ===== header; a re-run replaces that day's block (reports.py).

===== Mon Sep 14 2026 =====

# Alert Ledger — 2026-09-14

Every recognized entry alert from configured ON rooms. A `sent` row means the bridge accepted an order request; it does not by itself prove a broker fill.

## Summary

| Status / reason | Count |
|---|---:|
| futures protective exit not operational; no order sent | 25 |
| pullback expired; no order | 11 |
| order sent | 6 |
| swing paused | 4 |
| stale when received (78s old; 20s Discord limit) | 1 |
| contract expiry already passed; no order | 1 |
| stale when received (29s old; 20s Discord limit) | 1 |
| spread too wide | 1 |
| buying-power safety; no order | 1 |
| stale when received (48s old; 20s Discord limit) | 1 |
| options entry window closed; no order | 1 |

## Every alert

| Time ET | Caller | Room | Alert | Result | Why |
|---|---|---|---|---|---|
| 09:16:24 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 28883.50 | failed | futures protective exit not operational; no order sent |
| 09:18:25 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 28895.63 | failed | futures protective exit not operational; no order sent |
| 09:22:27 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 28919.88 | failed | futures protective exit not operational; no order sent |
| 09:24:03 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4312.80 | failed | futures protective exit not operational; no order sent |
| 10:07:59 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4308.10 | failed | futures protective exit not operational; no order sent |
| 10:10:02 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4308.60 | failed | futures protective exit not operational; no order sent |
| 10:11:45 | EliteOptions \| Brando | unavailable | OPEN QQQ 710C 9/16 @ 3.45 | skipped | stale when received (78s old; 20s Discord limit) |
| 10:13:15 | MuggZone | OWLS Capital: 🌟｜muggzone-options | OPEN CRWD 245C 9/18 @ 2.35 | sent | order sent |
| 10:18:44 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29049.75 | failed | futures protective exit not operational; no order sent |
| 10:21:21 | PT | unavailable | OPEN TSLA 357.5C @ 1.42 | skipped | pullback expired; no order |
| 10:22:17 | @Owner Alerts | Platinum Trading: 👑│nitro | OPEN TSLA 357.5P @ 1.61 | skipped | pullback expired; no order |
| 10:23:00 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29023.00 | failed | futures protective exit not operational; no order sent |
| 10:23:15 | Trademorewiser (MOD) | Whop Day Trades | OPEN NVDA 210P 9/16 @ 2.40 | sent | order sent |
| 10:28:16 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 28998.25 | failed | futures protective exit not operational; no order sent |
| 10:30:54 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4310.80 | failed | futures protective exit not operational; no order sent |
| 10:30:58 | Vero | VeroTrade: ✅⏐vero-trades | OPEN QQQ 714P 9/10 @ 1.15 | failed | contract expiry already passed; no order |
| 10:31:16 | Trademorewiser (MOD) | Whop Day Trades | OPEN MNQ @ 29000.00 | failed | futures protective exit not operational; no order sent |
| 10:31:27 | Vero | unavailable | OPEN SPY 759P 9/10 @ 1.15 | skipped | stale when received (29s old; 20s Discord limit) |
| 10:36:45 | Demon × LKS | Low Key Stonks: 😈demon-day-trades | OPEN QQQ 704P 9/14 @ 1.00 | skipped | pullback expired; no order |
| 10:36:45 | @Futures Alerts | Platinum Trading: 🟣│futures-alerts | OPEN MNQ @ 28977.50 | failed | futures protective exit not operational; no order sent |
| 10:41:16 | Vero | VeroTrade: ✅⏐vero-trades | OPEN QQQ 705P 9/14 @ 1.55 | skipped | pullback expired; no order |
| 10:42:14 | MuggZone | OWLS Capital: 🌟｜muggzone-options | OPEN MU 850P 9/16 @ 2.10 | sent | order sent |
| 10:54:01 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4314.90 | failed | futures protective exit not operational; no order sent |
| 11:04:03 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4313.20 | failed | futures protective exit not operational; no order sent |
| 11:05:41 | Trademorewiser (MOD) | Whop Day Trades | OPEN MNQ @ 29995.00 | failed | futures protective exit not operational; no order sent |
| 11:07:40 | Eva | OWLS Capital: 🛎️｜all-alerts | OPEN DRAM 58C 9/18 | failed | spread too wide |
| 11:12:31 | MuggZone | OWLS Capital: 🛎️｜all-alerts | OPEN MSFT 505C @ 0.85 | sent | order sent |
| 11:13:01 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 28997.50 | failed | futures protective exit not operational; no order sent |
| 11:21:01 | Skyy | OWLS Capital: 🌟｜shabs-sky-alerts | OPEN QQQ 708C @ 0.75 | skipped | pullback expired; no order |
| 11:24:18 | Unraveller | Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | OPEN META 670C 9/18 @ 6.50 | sent | order sent |
| 11:28:00 | Midas (Admin) | Honey Drip Network 🍯💰📈: 🇳🇬｜midas-small-account-challenge | OPEN SPY 760P 9/14 @ 760.40 | failed | buying-power safety; no order |
| 11:52:50 | MuggZone | OWLS Capital: 🌟｜muggzone-options | OPEN TSLA 340P 9/25 @ 2.40 | skipped | pullback expired; no order |
| 12:13:22 | Demon × LKS | Low Key Stonks: 😈demon-day-trades | OPEN WMT 110C 9/18 @ 0.96 | failed | swing paused |
| 12:24:35 | Trademorewiser (MOD) | Whop Day Trades | OPEN MNQ @ 29220.00 | failed | futures protective exit not operational; no order sent |
| 12:26:44 | TT | OWLS Capital: 🛎️｜all-alerts | OPEN GOOGL 360C 10/16 @ 7.20 | failed | swing paused |
| 12:39:24 | duccimama | Low Key Stonks: 🧿ducci-alerts | OPEN MCL @ 102.00 | failed | futures protective exit not operational; no order sent |
| 12:46:27 | AbTrades | OWLS Capital: 🛎️｜all-alerts | OPEN AMZN 300C 11/20 @ 3.97 | failed | swing paused |
| 13:18:01 | Midas (Admin) | Honey Drip Network 🍯💰📈: 🇳🇬｜midas-small-account-challenge | OPEN SPY 762P 0DTE @ 1.25 | skipped | pullback expired; no order |
| 13:41:30 | MuggZone | OWLS Capital: 🛎️｜all-alerts | OPEN AMZN 260C 9/18 @ 1.80 | skipped | pullback expired; no order |
| 13:53:51 | EliteOptions | unavailable | OPEN QQQ 715C 9/17 @ 4.04 | skipped | pullback expired; no order |
| 14:05:00 | 👑KingBeeAri🐝 | Honey Drip Network 🍯💰📈: 👑｜aristotle-trades | OPEN META 700C 9/18 | sent | order sent |
| 14:14:16 | Skyy | OWLS Capital: 🌟｜shabs-sky-alerts | OPEN QQQ 713C @ 0.40 | skipped | pullback expired; no order |
| 14:20:25 | MuggZone | OWLS Capital: 🌟｜muggzone-options | OPEN TSLA 360P 0DTE | skipped | pullback expired; no order |
| 14:43:12 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29269.00 | failed | futures protective exit not operational; no order sent |
| 14:56:04 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29265.88 | failed | futures protective exit not operational; no order sent |
| 15:12:43 | AbTrades | OWLS Capital: 🛎️｜all-alerts | OPEN AFRM 80C 10/16 @ 2.02 | failed | swing paused |
| 15:13:25 | AbTrades Alert Bot | unavailable | OPEN AFRM 80C 9/14 @ 2.02 | skipped | stale when received (48s old; 20s Discord limit) |
| 15:25:09 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29223.25 | failed | futures protective exit not operational; no order sent |
| 15:41:02 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29222.00 | failed | futures protective exit not operational; no order sent |
| 15:47:03 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29218.13 | failed | futures protective exit not operational; no order sent |
| 15:51:37 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29181.13 | failed | futures protective exit not operational; no order sent |
| 15:55:00 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29199.63 | failed | futures protective exit not operational; no order sent |
| 16:02:07 | MuggZone | unavailable | OPEN TSLA 340P 9/25 @ 3.05 | skipped | options entry window closed; no order |

## Notes

- Futures alerts were read and recorded, but no futures entry was sent because the broker-confirmed protective-exit lifecycle is not yet operational.
- `pullback expired` means the configured entry wait did not touch its level within the ten-minute window.
- `stale` means the alert arrived after the live-entry age limit.
