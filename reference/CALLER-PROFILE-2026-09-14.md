# Caller profile - how the callers actually trade (2026-09-14)

G's question: *"what is the callers' average trade hold time, because we need to kind of match that to get similar results - I'm even happy getting to the first trim. What's their normal stop also?"*

Built by `reference/caller_profile.py`. Measurement only - reads CSVs, writes this file and its `.csv` twin, changes nothing live. Re-runnable.

## The three numbers

| | |
|---|---|
| **options: entry -> first trim** | **5.4  (p25 1.1 / p75 18.9, n=100)** |
| **options: the percent that trim is posted at** | **17.4%  (p25 10.0% / p75 28.7%, n=96)** |
| **options: their stop, revealed by posted losing exits** | **-17.0%  (p25 -31.0% / p75 -9.3%, n=27)** |

They almost never post a premium stop on an option: 26 of 530 option entries in scope mention a stop at all, and only 2 of those quote a stop as a premium.

---

## What this is measured on

| | |
|---|---|
| source | `recovered_alerts_chat.csv` |
| rows after de-duplicating the overlapping exports | 2535 (dropped 146 duplicates) |
| window + confidence filter | 2026-08-03 .. 2026-09-10, high+medium only |
| entries in scope | **695** (530 option, 161 futures, 4 equity) |
| management posts linked to one of those entries | **459** |
| entries with at least one linked management post | **194** |
| entry premium known | 459 posted by the caller + 24 recovered from the message text |

**The linking caveat, up front.** 491 management messages in the whole file carry no `links_to` at all - they name a ticker and a percent and nothing else, so they can never be tied to an entry. A further 37 point at an entry outside this window or below medium confidence, 5 are ambiguous (two entries share a timestamp), 0 timestamp before their entry. All excluded. **Every hold-time number below is measured on callers who write a linkable management post - the tidy ones. It is not a sample of all calls.**

---

## 1. Hold time

**Options** - 530 entries

| measure | value |
|---|---|
| entry -> first trim, SAME DAY (min) | 5.4  (p25 1.1 / p75 18.9, n=100) |
| entry -> first trim, next day or later (hours) | 23.7  (p25 18.8 / p75 43.0, n=17) |
| entry -> full exit, SAME DAY (min) | 13.8  (p25 6.4 / p75 34.5, n=86) |
| entry -> full exit, next day or later (hours) | 23.2  (p25 18.2 / p75 24.7, n=26) |
| entries with NO management post at all (silent) | 352 of 530 = 66.4% |
| entries with no posted exit of any kind | 418 of 530 = 78.9% |

**Futures** - 161 entries

| measure | value |
|---|---|
| entry -> first trim, SAME DAY (min) | 1.5  (p25 1.5 / p75 1.5, n=1) |
| entry -> first trim, next day or later (hours) | 95.5  (p25 95.5 / p75 95.5, n=1) |
| entry -> full exit, SAME DAY (min) | 14.9  (p25 3.5 / p75 19.6, n=11) |
| entry -> full exit, next day or later (hours) | 14.4  (p25 14.4 / p75 14.4, n=1) |
| entries with NO management post at all (silent) | 147 of 161 = 91.3% |
| entries with no posted exit of any kind | 149 of 161 = 92.5% |

Same-day and multi-day are split on purpose: one swing trim four days later would otherwise drag the median into the thousands of minutes.

Read the silent line carefully: an entry with no posted exit is not a loss and not a win. It is **unavailable**. A later high is not a caller exit.

---

## 2. The first trim

| measure | value |
|---|---|
| entries that got a first trim | 119 of 695 |
| of those, same day | 101 |
| minutes to it, same-day only | 5.3  (p25 1.1 / p75 18.9, n=101) |
| percent it is posted at | 16.8%  (p25 10.0% / p75 28.7%, n=97) |
| where that percent came from | stated 60, caller-price 35, unavailable 22, caller-price-points 1, measured 1 |
| first trim is the only positive event (nothing better posted later) | 65 of 119 |
| ... of which no later percent was posted at all (unavailable, not zero) | 48 |

Stated trim size where the caller gives one: 1/2 x15, 1/4 x3. Most trims state no size at all.

Where the first trim lands: <10% 15, 10-19% 41, 20-34% 25, 35-59% 10, 60%+ 6 (n=97).

---

## 3. Their stop

### (a) Posted stops

| measure | value |
|---|---|
| FUTURES entries carrying a posted stop | 156 of 161 |
| futures stop distance, points from entry | 20.0  (p25 8.0 / p75 25.0, n=156) |
| OPTION entries with a stop in the recovered `their_stop` field | **0 of 530** |
| OPTION entries whose message mentions a stop at all | 26 of 530 = 4.9% |
| ... stated as an UNDERLYING level ("SL: under 55") | 13 |
| ... stated as "no stop loss" / "SL: None" | 6 |
| ... stated as a PREMIUM stop | 2 |
| premium-stop distance below entry | 25.6%  (p25 25.6% / p75 25.6%, n=2) |

**Read the futures stop with care:** 84 of those 156 come from one automated signal poster that prints a fixed `TP:/SL:` on every message. That is a machine's parameter, not a human's risk decision.

### (b) Revealed stops - where a losing exit was actually posted

| measure | value |
|---|---|
| option entries with a posted losing exit and a readable percent | 27 |
| the loss at that exit | -17.0%  (p25 -31.0% / p75 -9.3%, n=27) |
| the deepest quartile (p25) | -31.0% |

This is the only honest read on "their normal stop" for options: not a resting order, a habit. When a caller gives up on an option he is typically already down -17%.

### (c) "SL to b/e"

| measure | value |
|---|---|
| entries where a management post moves the stop to breakeven | 6 of 695 |
| minutes after entry, same-day cases | 11.0  (p25 1.1 / p75 44.9, n=3) |
| cases that happened on a later day | 3 |

---

## 4. Runner vs trim

| measure | value |
|---|---|
| entries with 2+ management posts and a first trim | 91 |
| of those, both first-trim % and final-exit % readable | 22 |
| median first-trim % | 18.9% |
| median final-exit % | 12.7% |
| runner adds more than +25 pts beyond the first trim | 7 of 22 |
| runner ends BELOW the first trim (gives back) | 11 of 22 |

n=22 is a small sample and it is the *only* set where both ends are readable. Treat the split as a direction, not a result.

---

## 5. The match question - was the bot still in when the caller trimmed?

Join: same date, same symbol, same strike, same side, our entry within 5 minutes of theirs, against `master_ledger.csv`. A ledger row whose close timestamps before its open is dropped as unusable.

| measure | value |
|---|---|
| caller entries the ledger also shows a position in | **70** |
| of those, rows with book provenance (not Webull-export-only) | 49 |
| pairs where the caller ALSO posted a first trim (the answerable set) | **23** (17 distinct caller entries) |
| **bot still in when the caller trimmed** | **7 of 23** |
| **bot already out before the caller's first trim** | **16 of 23** |

| measure | value |
|---|---|
| our hold time on matched trades (min) | 3.0  (p25 1.5 / p75 5.2, n=57) |
| our exit % on matched trades | -5.5%  (p25 -11.0% / p75 6.7%, n=49) |
| the caller's first-trim clock on the same trades (min) | 8.1  (p25 3.2 / p75 38.0, n=29) |
| the caller's first-trim % on the same trades | 24.6%  (p25 18.0% / p75 47.4%, n=21) |

Every answerable pair. Where one caller entry matched several of our positions in the same contract, each of our positions is its own row.

| date | contract | caller | their 1st trim | their % | our hold | our % | still in? |
|---|---|---|---:|---:|---:|---:|---|
| 2026-08-18 | QQQ 718.0P | Vero | 5.3 min | 24.6% | 2.1 min | -2.5% | NO - out first |
| 2026-08-19 | GOOGL 345.0C | Unraveller | 1.1 min | 18.0% | 2.6 min | -6.2% | yes |
| 2026-08-19 | MRNA 110.0P | MRNA | 0.2 min | unavailable | 1.9 min | 0.0% | yes |
| 2026-08-19 | MSFT 480.0C | Unraveller | 26.8 min | 30.0% | 4.7 min | 0.0% | NO - out first |
| 2026-08-19 | QQQ 716.0P | Vero | 8.0 min | 91.5% | 0.4 min | unavailable | NO - out first |
| 2026-08-19 | QQQ 716.0P | Vero | 8.0 min | 91.5% | 3.0 min | -14.3% | NO - out first |
| 2026-08-19 | QQQ 716.0P | Vero | 8.0 min | 91.5% | 0.7 min | -5.0% | NO - out first |
| 2026-08-19 | QQQ 716.0P | Vero | 8.0 min | 91.5% | 3.8 min | 114.9% | NO - out first |
| 2026-08-20 | INTC 90.0P | The Pawn (The Mark | 3.2 min | 22.2% | 3.5 min | 20.3% | yes |
| 2026-08-20 | QQQ 710.0P | Vero | 22.6 min | 18.0% | 0.4 min | unavailable | NO - out first |
| 2026-08-20 | QQQ 710.0P | Vero | 22.6 min | 18.0% | 3.1 min | 23.6% | NO - out first |
| 2026-08-24 | SNAP 6.0C | The Pawn (The Mark | 1328.0 min | 30.0% | 1.5 min | unavailable | NO - out first |
| 2026-08-25 | MSFT 485.0P | Unraveller | 0.5 min | 8.0% | 1.6 min | 6.7% | yes |
| 2026-08-25 | MSFT 485.0P | Unraveller | 0.5 min | 8.0% | 1.6 min | unavailable | yes |
| 2026-09-03 | WMT 108.0C | 👑KingBeeAri🐝 | 38.0 min | unavailable | 21.4 min | 1.8% | NO - out first |
| 2026-09-04 | INTC 94.0C | ZTRADEZ BOT | 8.1 min | 47.4% | 0.0 min | -12.6% | NO - out first |
| 2026-09-04 | NVDA 235.0C | 👑KingBeeAri🐝 | 41.5 min | unavailable | 2.7 min | 11.0% | NO - out first |
| 2026-09-04 | NVDA 235.0C | 👑KingBeeAri🐝 | 41.5 min | unavailable | 2.3 min | 8.9% | NO - out first |
| 2026-09-08 | AMD 510.0C | Mike | 1.1 min | 10.0% | 0.4 min | 10.0% | yes |
| 2026-09-08 | AMD 510.0C | Mike | 7.2 min | 0.0% | 3.9 min | 14.2% | NO - out first |
| 2026-09-09 | META 655.0C | 👑KingBeeAri🐝 | 20.1 min | 40.0% | 0.2 min | -7.5% | NO - out first |
| 2026-09-10 | META 645.0P | Unraveller | 0.4 min | 24.0% | 0.3 min | 14.7% | yes |
| 2026-09-10 | META 675.0C | @Updates | 85.8 min | unavailable | 0.1 min | -9.0% | NO - out first |

---

## 6. The two fully-paired days (9/11 and 9/14)

`daily-reports/CALLER-OUTCOMES-*.csv` pairs claim events by hand for two days. Small, but every row carries both timestamps - so it is the cleanest check on the big sample above.

| measure | value |
|---|---|
| claim events paired across the two days | 59 |
| distinct positions whose FIRST trim is timed | 23 |
| entry -> first trim (min) | 13.3  (p25 5.7 / p75 18.8, n=23) |
| first-trim % | 30.0%  (p25 15.0% / p75 70.0%, n=19) |
| full exits recorded | 12 |
| entry -> full exit (min) | 13.2  (p25 5.1 / p75 29.6, n=12) |

Basis on those rows: 37 caller-stated, 5 market-bid-at-caller-exit (measured), 15 unavailable.

---

## 7. Per-caller profile (min 5 linked entries), ranked by matchable

`matchable` rewards a first trim that exists, lands the same day at least a minute after entry, sits between +8%% and +80%%, and is not buried under a high silent rate. It is a ranking, not a score with units.

| caller | n entries / linked | median min to 1st trim (same day) | typical 1st-trim % | posts a stop | typical stop | silent | median exit % | matchable |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Vero | 22 / 13 | 7.8 (n=12) | 29.5% (n=12) | 0% | unavailable (n=0) | 41% | unavailable (n=0) | 46.8 |
| Brett | 33 / 16 | 4.1 (n=14) | 10.0% (n=14) | 0% | unavailable (n=0) | 52% | 60.0% (n=5) | 46.1 |
| Mike | 37 / 16 | 2.8 (n=12) | 10.0% (n=12) | 0% | unavailable (n=0) | 57% | 21.5% (n=6) | 42.8 |
| 👑KingBeeAri🐝 | 23 / 14 | 20.1 (n=7) | 28.0% (n=5) | 4% | unavailable (n=0) | 39% | unavailable (n=0) | 42.2 |
| Unraveller | 96 / 40 | 0.8 (n=29) | 13.0% (n=23) | 0% | unavailable (n=0) | 58% | -9.3% (n=11) | 39.4 |
| TradingTheTrend | 14 / 7 | 67.6 (n=3) | 16.8% (n=5) | 14% | unavailable (n=0) | 50% | -1.2% (n=4) | 35.5 |
| The Pawn (The Market Bis | 23 / 11 | 3.2 (n=1) | 29.4% (n=6) | 0% | unavailable (n=0) | 52% | -19.5% (n=6) | 33.0 |
| ZTRADEZ BOT | 36 / 11 | 8.1 (n=3) | 28.6% (n=6) | 0% | unavailable (n=0) | 69% | -33.0% (n=4) | 30.6 |
| TradeLikeGates | 22 / 8 | 5.5 (n=1) | 20.0% (n=1) | 0% | unavailable (n=0) | 64% | 20.0% (n=4) | 30.1 |
| @Futures Alerts | 9 / 5 | unavailable (n=0) | unavailable (n=0) | 89% | 22.5pts (n=8) | 44% | unavailable (n=0) | -1.0 |

## 8. Per-room

| room | entries | linked | median min to 1st trim (same day) | median 1st-trim % | median min to exit (same day) | silent |
|---|---:|---:|---:|---:|---:|---:|
| Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps #8 | 169 | 73 | 2.0 | 10.0% | 11.4 | 57% |
| ZTRADEZ (OPTIONS & STOCKS): ◽︱all-trades-mashu | 48 | 11 | 8.1 | 28.6% | 11.0 | 77% |
| ZTRADEZ (OPTIONS & STOCKS): ◽︱♟market-bishop # | 23 | 11 | 3.2 | 29.4% | 5.7 | 52% |
| Summit Trading Strategies: 📌｜alert-room #64243 | 22 | 8 | 5.5 | 20.0% | 12.1 | 64% |
| Honey Drip Network 🍯💰📈: 👑｜aristotle-trades #98 | 20 | 13 | 20.1 | 28.0% | 23.4 | 35% |
| Platinum Trading: 🟣│futures-alerts #9113900802 | 17 | 7 | unavailable | unavailable | 13.5 | 59% |
| TradingTheTrend: 🚨option-alerts🚨 #769797179992 | 17 | 10 | 46.4 | 18.3% | 132.1 | 41% |
| VeroTrade: ✅⏐1k-challenge #1323708708374450247 | 11 | 7 | 5.1 | 30.7% | unavailable | 36% |
| VeroTrade: ✅⏐vero-trades #760694103401955378 | 8 | 6 | 21.0 | 29.5% | unavailable | 25% |

## 9. What this cannot say

- **No caller win rate, no caller net result.** Most entries never get a posted exit, and an unposted exit is unavailable, not a number. Nothing here is a scoreboard.
- The hold times describe **callers who post linkable management messages**. Rooms that post an entry and go quiet sit in the silent column, not in the medians.
- `their_target` is not recorded anywhere in this repo, so no target study exists.
- Percentages labelled `stated` are the caller's own claim on their own fill. They are not broker truth and they are not the bid we could have hit.
- The match section joins on contract and clock only - `master_ledger.csv` carries a room on a minority of rows, so a match is evidence we held the same contract at the same minute, not proof the room caused our order.

