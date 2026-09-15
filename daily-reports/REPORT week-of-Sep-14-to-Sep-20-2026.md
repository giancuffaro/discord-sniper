# REPORT — week of Mon Sep 14 2026 to Sun Sep 20 2026. Newest day first; each day under its ===== header; a re-run replaces that day's block (reports.py).

===== Tue Sep 15 2026 =====

# Daily Sniper Report — 2026-09-15

Generated 2026-09-15 16:41:35 Eastern Daylight Time.

## Coverage

- Rooms configured on: **35** Discord and **5** Whop.
- Rooms/channels with a live parser input today: **18**.
- Live parser inputs retained: **599** messages.
- Rooms with no message are quiet or unverified; the report does not call them healthy solely from silence.

## Alert flow

| Measure | Count |
|---|---:|
| Unique entry alerts observed (normal + recovered) | 68 |
| Entry alerts read and given a decision | 68 |
| Broker entry orders submitted | 10 |
| Read but not taken | 58 |
| Broker/risk refusals | 36 |
| Stale when first read | 0 |
| Duplicate or other skips | 22 |
| Recovered entry gaps | 0 |
| Recovered add gaps | 0 |
| Actual fills in master ledger | 11 |

## Actual results

- Bot trades: **11** — 1 win, 8 loss, 2 flat.
- Realized P&L: **-123.00**.
- Demon × LKS META 690.0C 2026-09-16: 1.88 → 1.75, **-13.00** (bot stop).
- Nitro Trades TSLA 370.0C 2026-09-16: 1.19 → 1.11, **-8.00** (bot stop).
- Elite Options | Shoof CRWD 240.0C 2026-09-18: ? → ?, **+0.00** (nofill).
- Mike TSLA 350.0P 2026-09-18: 3.25 → 3.05, **-20.00** (closed).
- Demon × LKS QQQ 703.0P 2026-09-15: 0.61 → 0.58, **-3.00** (closed).
- Unraveller AMD 490.0P 2026-09-18: 5.45 → 5.2, **-25.00** (closed).
- MuggZone MU 950.0C 2026-09-16: 3.7 → 3.5, **-20.00** (closed).
- Gian SPY 758.0P 2026-09-15: 1.0 → 1.13, **+39.00** (closed).
- Mike (Admin) TSLA 350.0P 2026-09-18: 3.78 → 3.35, **-43.00** (bot stop).
- AbTrades Alert Bot HOOD 120.0C 2026-09-25: ? → ?, **+0.00** (nofill).
- Gian QQQ 706.0P 2026-09-15: 1.37 → 1.27, **-30.00** (closed).

## Entry and exit comparison

- AMD: caller entry 5.3, bot fill 5.45 (2.8% difference); bot exit 5.2, P&L -25.0, verdict **NOISE CLIP**. stopped, then the bid was back above the entry by +10m. Only a 7.5%+ born stop survives this one; the 80-fill sweep still prefers 7.5 on average — count these clips; if they pile up on 0DTE ATM, that is the case for a wider 0DTE stop.
- META: caller entry 1.9, bot fill 1.88 (-1.1% difference); bot exit 1.75, P&L -13.0, verdict **NOISE CLIP**. stopped, then the bid was back above the entry by +30s. no stop in the 5-25%% grid survives this one; the 80-fill sweep still prefers 7.5 on average — count these clips; if they pile up on 0DTE ATM, that is the case for a wider 0DTE stop.
- MU: caller entry 3.7, bot fill 3.7 (0.0% difference); bot exit 3.5, P&L -20.0, verdict **GOOD STOP**. it kept falling to 3.00 after we left (-14% under the exit) — the stop saved money.
- QQQ: caller entry unavailable, bot fill 0.61 (n.a.% difference); bot exit 0.58, P&L -3.0, verdict **GOOD STOP**. it kept falling to 0.45 after we left (-22% under the exit) — the stop saved money.
- TSLA: caller entry 1.51, bot fill 1.19 (-21.2% difference); bot exit 1.11, P&L -8.0, verdict **NOISE CLIP**. stopped, then the bid was back above the entry by +1m. no stop in the 5-25%% grid survives this one; the 80-fill sweep still prefers 7.5 on average — count these clips; if they pile up on 0DTE ATM, that is the case for a wider 0DTE stop.
- TSLA: caller entry unavailable, bot fill 3.25 (n.a.% difference); bot exit 3.05, P&L -20.0, verdict **GOOD STOP**. it kept falling to 2.54 after we left (-17% under the exit) — the stop saved money.
- TSLA: caller entry 3.6, bot fill 3.78 (5.0% difference); bot exit 3.35, P&L -43.0, verdict **GOOD STOP**. it kept falling to 3.05 after we left (-9% under the exit) — the stop saved money.
- Exact caller-entry/caller-exit P&L is reported only when both messages and a contemporaneous contract quote exist. Missing exits remain **unavailable**; they are never estimated from a later high or a stale quote.
- Refused or missed alerts stay outcome-pending until a caller exit can be paired to the recorded contract tape; a later high alone is not labeled a win.
- A system-versus-caller verdict needs matched trades on both sides. 7 bot trades are displayed, but they are not enough evidence to call either method better.

## Every recognized decision

| Time | Caller | Room | Alert | Result | Reason | Source message |
|---|---|---|---|---|---|---|
| 09:04:06 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29440.38 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:05:11 | already acted on that exact call 65s ago | unavailable | OPEN MNQ @ 29439.50 | skipped | skipped | unavailable |
| 09:06:07 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4329.10 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:08:04 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29447.13 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:10:06 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4327.15 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:10:48 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29458.00 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:14:34 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29419.88 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:15:51 | already acted on that exact call 78s ago | unavailable | OPEN MNQ @ 29433.50 | skipped | skipped | unavailable |
| 09:16:55 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29422.75 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:18:58 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29417.00 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:22:31 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4320.00 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:26:03 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29433.00 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:33:20 | Trademorewiser (MOD) | Whop Day Trades | OPEN MNQ @ 29395.00 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:36:04 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4326.90 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:41:33 | Nitro Trades | Platinum Trading: 👑│nitro | OPEN TSLA 370C @ 1.71 | failed | buying-power safety; no order | [Open in Chrome](http://127.0.0.1:8787/open-discord/911385966864896081/911389167169191946/1549414843029917849) |
| 09:42:28 | Unraveller | Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | OPEN AMD 490P 9/18 | sent | order sent | [Open in Chrome](http://127.0.0.1:8787/open-discord/525113944239767562/829754942817828884/1549415093584793752) |
| 09:46:57 | Demon × LKS | Low Key Stonks: 😈demon-day-trades | OPEN META 690C 9/16 @ 1.90 | sent | order sent | unavailable |
| 09:50:35 | Nitro Trades | Platinum Trading: 👑│nitro | OPEN TSLA 370C @ 1.51 | sent | order sent | unavailable |
| 09:57:26 | Brett | Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | OPEN SPY 759P 9/16 @ 2.80 | skipped | pullback expired; no order | [Open in Chrome](http://127.0.0.1:8787/open-discord/525113944239767562/829754942817828884/1549418841099210898) |
| 10:01:25 | Unraveller | Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | OPEN AAPL 330P 9/18 @ 3.20 | skipped | pullback expired; no order | [Open in Chrome](http://127.0.0.1:8787/open-discord/525113944239767562/829754942817828884/1549419864186294453) |
| 10:03:27 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29429.50 | failed | futures protective exit not operational; no order sent | unavailable |
| 10:05:01 | already acted on that exact call 94s ago | unavailable | OPEN MNQ @ 29400.75 | skipped | skipped | [Open in Chrome](http://127.0.0.1:8787/open-discord/911385966864896081/911390080285962290/1549420782780813354) |
| 10:07:08 | @Owner Alerts | Platinum Trading: 👑│nitro | OPEN QQQ 708P @ 1.42 | skipped | pullback expired; no order | unavailable |
| 10:08:03 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4328.70 | failed | futures protective exit not operational; no order sent | unavailable |
| 10:14:43 | Elite Options | unavailable | OPEN CRWD 240C 9/18 @ 4.25 | sent | order sent | unavailable |
| 10:48:00 | Vero | VeroTrade: ✅⏐1k-challenge | OPEN QQQ 706P 9/15 @ 1.47 | skipped | pullback expired; no order | unavailable |
| 10:51:55 | Mike | Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | OPEN TSLA 350P 9/18 @ 3.35 | sent | order sent | [Open in Chrome](http://127.0.0.1:8787/open-discord/525113944239767562/829754942817828884/1549432558964576267) |
| 11:03:03 | Demon × LKS | Low Key Stonks: 😈demon-day-trades | OPEN QQQ 703P 9/15 @ 0.70 | skipped | pullback expired; no order | unavailable |
| 11:07:28 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4321.20 | failed | futures protective exit not operational; no order sent | unavailable |
| 11:09:01 | ⚠ double-check disagrees | unavailable | OPEN FOR 260C 9/25 @ 1.87 | skipped | skipped | unavailable |
| 11:14:06 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29258.50 | failed | futures protective exit not operational; no order sent | unavailable |
| 11:32:59 | Unraveller | Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | OPEN AMD 490P 9/18 @ 5.30 | sent | order sent | [Open in Chrome](http://127.0.0.1:8787/open-discord/525113944239767562/829754942817828884/1549442903141519471) |
| 12:25:26 | MuggZone | OWLS Capital: 🛎️｜all-alerts | OPEN MU 950C 1DTE @ 3.70 | sent | order sent | unavailable |
| 12:50:36 | @Elite | ELITE OPTIONS: shoof-alerts | OPEN CRWD 250C 9/18 @ 3.50 | sent | order sent | unavailable |
| 13:20:58 | Eva | OWLS Capital: 🛎️｜all-alerts | OPEN NVDA 220C | skipped | pullback expired; no order | unavailable |
| 13:36:13 | Mike (Admin) | Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | OPEN TSLA 350P @ 3.60 | sent | order sent | [Open in Chrome](http://127.0.0.1:8787/open-discord/525113944239767562/829754942817828884/1549473910586609787) |
| 14:11:03 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29274.50 | failed | futures protective exit not operational; no order sent | unavailable |
| 14:14:11 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29275.25 | failed | futures protective exit not operational; no order sent | unavailable |
| 14:15:29 | already acted on that exact call 78s ago | unavailable | OPEN MNQ @ 29281.50 | skipped | skipped | unavailable |
| 14:16:43 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29273.50 | failed | futures protective exit not operational; no order sent | unavailable |
| 14:17:40 | already acted on that exact call 58s ago | unavailable | OPEN MNQ @ 29267.75 | skipped | skipped | unavailable |
| 14:19:03 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29271.25 | failed | futures protective exit not operational; no order sent | unavailable |
| 14:20:00 | already acted on that exact call 57s ago | unavailable | OPEN MNQ @ 29270.25 | skipped | skipped | unavailable |
| 14:22:20 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29275.75 | failed | futures protective exit not operational; no order sent | unavailable |
| 14:30:03 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29279.00 | failed | futures protective exit not operational; no order sent | unavailable |
| 14:32:29 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29274.13 | failed | futures protective exit not operational; no order sent | unavailable |
| 14:33:26 | already acted on that exact call 57s ago | unavailable | OPEN MNQ @ 29261.75 | skipped | skipped | unavailable |
| 14:35:29 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29262.50 | failed | futures protective exit not operational; no order sent | unavailable |
| 14:40:35 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29262.75 | failed | futures protective exit not operational; no order sent | unavailable |
| 14:46:04 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29249.25 | failed | futures protective exit not operational; no order sent | unavailable |
| 14:47:01 | already acted on that exact call 57s ago | unavailable | OPEN MNQ @ 29245.50 | skipped | skipped | unavailable |
| 14:48:01 | already acted on that exact call 117s ago | unavailable | OPEN MNQ @ 29245.13 | skipped | skipped | unavailable |
| 14:49:04 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29245.38 | failed | futures protective exit not operational; no order sent | unavailable |
| 14:50:02 | already acted on that exact call 58s ago | unavailable | OPEN MNQ @ 29240.13 | skipped | skipped | unavailable |
| 14:57:44 | AbTrades Alert Bot | OWLS Capital: 🌟｜ab | OPEN HOOD 120C 9/25 @ 1.22 | sent | order sent | [Open in Chrome](http://127.0.0.1:8787/open-discord/718624848812834903/1235366372385493074/1549494403767336972) |
| 15:13:03 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29243.50 | failed | futures protective exit not operational; no order sent | unavailable |
| 15:14:00 | already acted on that exact call 57s ago | unavailable | OPEN MNQ @ 29244.63 | skipped | skipped | unavailable |
| 15:15:02 | already acted on that exact call 119s ago | unavailable | OPEN MNQ @ 29247.00 | skipped | skipped | unavailable |
| 15:16:06 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29242.25 | failed | futures protective exit not operational; no order sent | unavailable |
| 15:19:08 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29246.38 | failed | futures protective exit not operational; no order sent | unavailable |
| 15:32:02 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29235.88 | failed | futures protective exit not operational; no order sent | unavailable |
| 15:33:01 | already acted on that exact call 59s ago | unavailable | OPEN MNQ @ 29239.25 | skipped | skipped | unavailable |
| 15:35:37 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29233.25 | failed | futures protective exit not operational; no order sent | unavailable |
| 15:36:33 | already acted on that exact call 57s ago | unavailable | OPEN MNQ @ 29230.88 | skipped | skipped | unavailable |
| 15:38:37 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29231.13 | failed | futures protective exit not operational; no order sent | unavailable |
| 15:40:35 | already acted on that exact call 118s ago | unavailable | OPEN MNQ @ 29222.00 | skipped | skipped | unavailable |
| 15:41:48 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29231.25 | failed | futures protective exit not operational; no order sent | unavailable |
| 15:44:04 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29248.00 | failed | futures protective exit not operational; no order sent | unavailable |

## Room activity

| Room/channel | Parser inputs |
|---|---:|
| NGD: ngd-trades | 123 |
| Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | 94 |
| OWLS Capital: 🛎️｜all-alerts | 78 |
| Platinum Trading: 🟣│futures-alerts | 60 |
| Honey Drip Network 🍯💰📈: 👑｜aristotle-trades | 54 |
| OWLS Capital: 🌟｜shabs-sky-alerts | 46 |
| Honey Drip Network 🍯💰📈: 🇳🇬｜midas-small-account-challenge | 34 |
| OWLS Capital: 🌟｜eli-alerts | 22 |
| OWLS Capital: 🌟｜muggzone-options | 20 |
| OWLS Capital: 🌟｜ab | 18 |
| Platinum Trading: 👑│nitro | 12 |
| OWLS Capital: 🌟｜jon-and-kian | 12 |
| ELITE OPTIONS: shoof-alerts | 10 |
| Low Key Stonks: 😈demon-day-trades | 6 |
| Platinum Trading: 🟣│ei-alerts | 4 |
| VeroTrade: ✅⏐1k-challenge | 2 |
| Platinum Trading: 🟣│equity | 2 |
| Honey Drip Network 🍯💰📈: 🐝｜aristotle-small-acct-challenge | 2 |

## Detailed benchmarks

- [Caller entry, trim, and exit evidence](CALLER-OUTCOMES%20week-of-Sep-14-to-Sep-20-2026.md)
- [Caller original entry versus our ratchet](CALLER-VS-RATCHET%20week-of-Sep-14-to-Sep-20-2026.md)
- [Fixed stop versus live ratchet replay](RATCHET-COMPARE%20week-of-Sep-14-to-Sep-20-2026.md)

===== Mon Sep 14 2026 =====

# Daily Sniper Report — 2026-09-14

Generated 2026-09-15 01:50:52 EDT.

## Coverage

- Rooms configured on: **35** Discord and **5** Whop.
- Rooms/channels with a live parser input today: **20**.
- Live parser inputs retained: **740** messages.
- Rooms with no message are quiet or unverified; the report does not call them healthy solely from silence.

## Alert flow

| Measure | Count |
|---|---:|
| Unique entry alerts observed (normal + recovered) | 53 |
| Entry alerts read and given a decision | 53 |
| Broker entry orders submitted | 6 |
| Read but not taken | 47 |
| Broker/risk refusals | 32 |
| Stale when first read | 0 |
| Duplicate or other skips | 15 |
| Recovered entry gaps | 0 |
| Recovered add gaps | 0 |
| Actual fills in master ledger | 11 |

## Actual results

- Bot trades: **11** — 2 win, 8 loss, 1 flat.
- Realized P&L: **-55.00**.
- Gian SPY 761.0C 2026-09-14: 0.72 → 0.9, **+36.00** (closed).
- Trademorewiser (MOD) NVDA 210.0P 2026-09-16: 2.4 → 2.38, **-2.00** (closed).
- PT | ei trades TSLA 357.5C 2026-09-18: 7.4 → 7.06, **-34.00** (closed).
- Demon × LKS QQQ 704.0P 2026-09-14: 1.13 → 1.13, **+0.00** (closed).
- MuggZone MU 850.0P 2026-09-16: 2.1 → 2.05, **-5.00** (pullback stop).
- Vero QQQ 705.0P 2026-09-14: 1.41 → 1.39, **-2.00** (closed).
- MuggZone MSFT 505.0C 2026-09-14: 0.65 → 0.61, **-4.00** (closed).
- Unraveller META 670.0C 2026-09-18: 6.65 → 6.2, **-45.00** (closed).
- MuggZone TSLA 340.0P 2026-09-25: 2.38 → 2.34, **-4.00** (pullback stop).
- 👑KingBeeAri🐝 META 700.0C 2026-09-18: 2.61 → 2.68, **+7.00** (bot stop).
- Skyy QQQ 713.0C 2026-09-14: 0.24 → 0.22, **-2.00** (bot stop).

## Entry and exit comparison

- META: caller entry unavailable, bot fill 6.65 (n.a.% difference); bot exit 6.2, P&L -45.0, verdict **NOISE CLIP**. stopped, then the bid was back above the entry by +5m. Only a 7.5%+ born stop survives this one; the 80-fill sweep still prefers 7.5 on average — count these clips; if they pile up on 0DTE ATM, that is the case for a wider 0DTE stop.
- META: caller entry unavailable, bot fill 2.61 (n.a.% difference); bot exit 2.68, P&L 7.0, verdict **GOOD EXIT**. took what was there; nothing to change.
- MSFT: caller entry 0.85, bot fill 0.65 (-23.5% difference); bot exit 0.61, P&L -4.0, verdict **NOISE CLIP**. stopped, then the bid was back above the entry by +30s. Only a 15%+ born stop survives this one; the 80-fill sweep still prefers 7.5 on average — count these clips; if they pile up on 0DTE ATM, that is the case for a wider 0DTE stop.
- MU: caller entry 2.1, bot fill 2.1 (0.0% difference); bot exit 2.05, P&L -5.0, verdict **NOISE CLIP**. stopped, then the bid was back above the entry by +10m. Only a 20%+ born stop survives this one; the 80-fill sweep still prefers 7.5 on average — count these clips; if they pile up on 0DTE ATM, that is the case for a wider 0DTE stop.
- QQQ: caller entry 0.4, bot fill 0.24 (-40.0% difference); bot exit 0.22, P&L -2.0, verdict **NOISE CLIP**. stopped, then the bid was back above the entry by +10m. Only a 25%+ born stop survives this one; the 80-fill sweep still prefers 7.5 on average — count these clips; if they pile up on 0DTE ATM, that is the case for a wider 0DTE stop.
- QQQ: caller entry unavailable, bot fill 1.13 (n.a.% difference); bot exit 1.13, P&L 0.0, verdict **GOOD EXIT**. took what was there; nothing to change.
- QQQ: caller entry unavailable, bot fill 1.41 (n.a.% difference); bot exit 1.39, P&L -2.0, verdict **LOSS, FLAT AFTER**. no recovery and no further drop on tape in 10 min — a dead call.
- TSLA: caller entry 2.4, bot fill 2.38 (-0.8% difference); bot exit 2.34, P&L -4.0, verdict **NOISE CLIP**. stopped, then the bid was back above the entry by +5m. Only a 5%+ born stop survives this one; the 80-fill sweep still prefers 7.5 on average — count these clips; if they pile up on 0DTE ATM, that is the case for a wider 0DTE stop.
- Exact caller-entry/caller-exit P&L is reported only when both messages and a contemporaneous contract quote exist. Missing exits remain **unavailable**; they are never estimated from a later high or a stale quote.
- Refused or missed alerts stay outcome-pending until a caller exit can be paired to the recorded contract tape; a later high alone is not labeled a win.
- A system-versus-caller verdict needs matched trades on both sides. 8 bot trades are displayed, but they are not enough evidence to call either method better.

## Every recognized decision

| Time | Caller | Room | Alert | Result | Reason | Source message |
|---|---|---|---|---|---|---|
| 09:16:24 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 28883.50 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:18:25 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 28895.63 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:22:27 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 28919.88 | failed | futures protective exit not operational; no order sent | unavailable |
| 09:24:03 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4312.80 | failed | futures protective exit not operational; no order sent | unavailable |
| 10:07:59 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4308.10 | failed | futures protective exit not operational; no order sent | unavailable |
| 10:10:02 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4308.60 | failed | futures protective exit not operational; no order sent | unavailable |
| 10:11:45 | EliteOptions \| Brando | unavailable | OPEN QQQ 710C 9/16 @ 3.45 | skipped | stale when received (78s old; 20s Discord limit) | unavailable |
| 10:13:15 | MuggZone | OWLS Capital: 🌟｜muggzone-options | OPEN CRWD 245C 9/18 @ 2.35 | sent | order sent | [Open in Chrome](http://127.0.0.1:8787/open-discord/718624848812834903/1503509270526951575/1549069806593118231) |
| 10:18:44 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29049.75 | failed | futures protective exit not operational; no order sent | unavailable |
| 10:21:21 | PT | unavailable | OPEN TSLA 357.5C @ 1.42 | skipped | pullback expired; no order | unavailable |
| 10:22:17 | @Owner Alerts | Platinum Trading: 👑│nitro | OPEN TSLA 357.5P @ 1.61 | skipped | pullback expired; no order | unavailable |
| 10:23:00 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29023.00 | failed | futures protective exit not operational; no order sent | unavailable |
| 10:23:15 | Trademorewiser (MOD) | Whop Day Trades | OPEN NVDA 210P 9/16 @ 2.40 | sent | order sent | unavailable |
| 10:28:16 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 28998.25 | failed | futures protective exit not operational; no order sent | unavailable |
| 10:30:54 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4310.80 | failed | futures protective exit not operational; no order sent | unavailable |
| 10:30:58 | Vero | VeroTrade: ✅⏐vero-trades | OPEN QQQ 714P 9/10 @ 1.15 | failed | contract expiry already passed; no order | unavailable |
| 10:31:16 | Trademorewiser (MOD) | Whop Day Trades | OPEN MNQ @ 29000.00 | failed | futures protective exit not operational; no order sent | unavailable |
| 10:31:27 | Vero | unavailable | OPEN SPY 759P 9/10 @ 1.15 | skipped | stale when received (29s old; 20s Discord limit) | [Open in Chrome](http://127.0.0.1:8787/open-discord/725117609275555851/760694103401955378/1549064921701154947) |
| 10:36:45 | Demon × LKS | Low Key Stonks: 😈demon-day-trades | OPEN QQQ 704P 9/14 @ 1.00 | skipped | pullback expired; no order | [Open in Chrome](http://127.0.0.1:8787/open-discord/722872384800948227/1169216956746969088/1549066369360994305) |
| 10:36:45 | @Futures Alerts | Platinum Trading: 🟣│futures-alerts | OPEN MNQ @ 28977.50 | failed | futures protective exit not operational; no order sent | [Open in Chrome](http://127.0.0.1:8787/open-discord/911385966864896081/911390080285962290/1549066374674911277) |
| 10:41:16 | Vero | VeroTrade: ✅⏐vero-trades | OPEN QQQ 705P 9/14 @ 1.55 | skipped | pullback expired; no order | unavailable |
| 10:42:14 | MuggZone | OWLS Capital: 🌟｜muggzone-options | OPEN MU 850P 9/16 @ 2.10 | sent | order sent | unavailable |
| 10:54:01 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4314.90 | failed | futures protective exit not operational; no order sent | unavailable |
| 11:04:03 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MGC @ 4313.20 | failed | futures protective exit not operational; no order sent | unavailable |
| 11:05:41 | Trademorewiser (MOD) | Whop Day Trades | OPEN MNQ @ 29995.00 | failed | futures protective exit not operational; no order sent | unavailable |
| 11:07:40 | Eva | OWLS Capital: 🛎️｜all-alerts | OPEN DRAM 58C 9/18 | failed | spread too wide | unavailable |
| 11:12:31 | MuggZone | OWLS Capital: 🛎️｜all-alerts | OPEN MSFT 505C @ 0.85 | sent | order sent | unavailable |
| 11:13:01 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 28997.50 | failed | futures protective exit not operational; no order sent | unavailable |
| 11:21:01 | Skyy | OWLS Capital: 🌟｜shabs-sky-alerts | OPEN QQQ 708C @ 0.75 | skipped | pullback expired; no order | unavailable |
| 11:24:18 | Unraveller | Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | OPEN META 670C 9/18 @ 6.50 | sent | order sent | [Open in Chrome](http://127.0.0.1:8787/open-discord/525113944239767562/829754942817828884/1549078339820716036) |
| 11:28:00 | Midas (Admin) | Honey Drip Network 🍯💰📈: 🇳🇬｜midas-small-account-challenge | OPEN SPY 760P 9/14 @ 760.40 | failed | buying-power safety; no order | unavailable |
| 11:52:50 | MuggZone | OWLS Capital: 🌟｜muggzone-options | OPEN TSLA 340P 9/25 @ 2.40 | skipped | pullback expired; no order | [Open in Chrome](http://127.0.0.1:8787/open-discord/718624848812834903/1503509270526951575/1549085512818495580) |
| 12:13:22 | Demon × LKS | Low Key Stonks: 😈demon-day-trades | OPEN WMT 110C 9/18 @ 0.96 | failed | swing paused | [Open in Chrome](http://127.0.0.1:8787/open-discord/722872384800948227/1169216956746969088/1549090686010134580) |
| 12:24:35 | Trademorewiser (MOD) | Whop Day Trades | OPEN MNQ @ 29220.00 | failed | futures protective exit not operational; no order sent | unavailable |
| 12:26:44 | TT | OWLS Capital: 🛎️｜all-alerts | OPEN GOOGL 360C 10/16 @ 7.20 | failed | swing paused | unavailable |
| 12:39:24 | duccimama | Low Key Stonks: 🧿ducci-alerts | OPEN MCL @ 102.00 | failed | futures protective exit not operational; no order sent | [Open in Chrome](http://127.0.0.1:8787/open-discord/722872384800948227/1316182395652669510/1549097236439240816) |
| 12:46:27 | AbTrades | OWLS Capital: 🛎️｜all-alerts | OPEN AMZN 300C 11/20 @ 3.97 | failed | swing paused | unavailable |
| 13:18:01 | Midas (Admin) | Honey Drip Network 🍯💰📈: 🇳🇬｜midas-small-account-challenge | OPEN SPY 762P 0DTE @ 1.25 | skipped | pullback expired; no order | [Open in Chrome](http://127.0.0.1:8787/open-discord/525113944239767562/1144369893760831489/1549106954289418264) |
| 13:41:30 | MuggZone | OWLS Capital: 🛎️｜all-alerts | OPEN AMZN 260C 9/18 @ 1.80 | skipped | pullback expired; no order | unavailable |
| 13:53:51 | EliteOptions | unavailable | OPEN QQQ 715C 9/17 @ 4.04 | skipped | pullback expired; no order | unavailable |
| 14:05:00 | 👑KingBeeAri🐝 | Honey Drip Network 🍯💰📈: 👑｜aristotle-trades | OPEN META 700C 9/18 | sent | order sent | [Open in Chrome](http://127.0.0.1:8787/open-discord/525113944239767562/987515353670221834/1549118779953258509) |
| 14:14:16 | Skyy | OWLS Capital: 🌟｜shabs-sky-alerts | OPEN QQQ 713C @ 0.40 | skipped | pullback expired; no order | [Open in Chrome](http://127.0.0.1:8787/open-discord/718624848812834903/1513300726141419550/1549121091048443945) |
| 14:20:25 | MuggZone | OWLS Capital: 🌟｜muggzone-options | OPEN TSLA 360P 0DTE | skipped | pullback expired; no order | [Open in Chrome](http://127.0.0.1:8787/open-discord/718624848812834903/1503509270526951575/1549122640915206258) |
| 14:43:12 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29269.00 | failed | futures protective exit not operational; no order sent | unavailable |
| 14:56:04 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29265.88 | failed | futures protective exit not operational; no order sent | unavailable |
| 15:12:43 | AbTrades | OWLS Capital: 🛎️｜all-alerts | OPEN AFRM 80C 10/16 @ 2.02 | failed | swing paused | unavailable |
| 15:13:25 | AbTrades Alert Bot | unavailable | OPEN AFRM 80C 9/14 @ 2.02 | skipped | stale when received (48s old; 20s Discord limit) | [Open in Chrome](http://127.0.0.1:8787/open-discord/718624848812834903/1235366372385493074/1549135802846548030) |
| 15:25:09 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29223.25 | failed | futures protective exit not operational; no order sent | unavailable |
| 15:41:02 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29222.00 | failed | futures protective exit not operational; no order sent | unavailable |
| 15:47:03 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29218.13 | failed | futures protective exit not operational; no order sent | unavailable |
| 15:51:37 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29181.13 | failed | futures protective exit not operational; no order sent | unavailable |
| 15:55:00 | Ninjago Futures Radar | NGD: ngd-trades | OPEN MNQ @ 29199.63 | failed | futures protective exit not operational; no order sent | unavailable |
| 16:02:07 | MuggZone | unavailable | OPEN TSLA 340P 9/25 @ 3.05 | skipped | options entry window closed; no order | unavailable |

## Room activity

| Room/channel | Parser inputs |
|---|---:|
| Honey Drip Network 🍯💰📈: 👑｜aristotle-trades | 174 |
| Honey Drip Network 🍯💰📈: 🇳🇬｜midas-small-account-challenge | 104 |
| OWLS Capital: 🌟｜shabs-sky-alerts | 104 |
| OWLS Capital: 🛎️｜all-alerts | 68 |
| NGD: ngd-trades | 60 |
| Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps | 50 |
| Platinum Trading: 🟣│futures-alerts | 46 |
| OWLS Capital: 🌟｜muggzone-options | 46 |
| OWLS Capital: 🌟｜ab | 20 |
| Platinum Trading: 👑│nitro | 10 |
| ELITE OPTIONS: brando-alerts | 8 |
| Platinum Trading: 🟣│ei-alerts | 8 |
| Platinum Trading: 🟣│equity | 8 |
| Low Key Stonks: ⚖chika-alerts | 8 |
| Low Key Stonks: 😈demon-day-trades | 6 |
| OWLS Capital: 🌟｜jon-and-kian | 6 |
| Low Key Stonks: 🔋nando-alerts | 4 |
| Low Key Stonks: 🧿ducci-alerts | 4 |
| TradingTheTrend: 🎰lotto-alerts | 4 |
| VeroTrade: ✅⏐vero-trades | 2 |

## Detailed benchmarks

- [Caller entry, trim, and exit evidence](CALLER-OUTCOMES%20week-of-Sep-14-to-Sep-20-2026.md)
- [Caller original entry versus our ratchet](CALLER-VS-RATCHET%20week-of-Sep-14-to-Sep-20-2026.md)
- [Fixed stop versus live ratchet replay](RATCHET-COMPARE%20week-of-Sep-14-to-Sep-20-2026.md)
