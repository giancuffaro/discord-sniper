# Caller profile - how the callers actually trade (2026-09-14)

Question, in G's words: *"what is the callers' average trade hold time, because we need to kind of match that to get similar results - I'm even happy getting to the first trim. What's their normal stop also?"*

Built by `reference/caller_profile.py`. Measurement only - reads CSVs, writes this file and its `.csv` twin, changes nothing live. Re-runnable.

## What this is measured on

| | |
|---|---|
| source | `recovered_alerts_chat.csv` |
| rows after de-duplicating the overlapping exports | 2535 (dropped 146 duplicates) |
| window + confidence filter | 2026-08-03 .. 2026-09-10, high+medium only |
| entries in scope | **695** (530 option, 161 futures, 4 equity) |
| management posts linked to one of those entries | **459** |
| entries with at least one linked management post | **194** |

**The linking caveat, stated up front.** 491 management messages in the whole file carry no `links_to` at all - they name a ticker and a percent and nothing else, so they can never be tied to an entry. A further 37 linked messages point at an entry that is outside this window or below medium confidence, 5 are ambiguous (two entries share the timestamp), and 0 timestamp *before* their entry. All of those are excluded. **Every hold-time number below is therefore measured on the callers who write a linkable management post - the tidy ones. It is not a sample of all calls.**

---

## 1. Hold time

### Overall

**Options** - 530 entries (high+medium confidence, 2026-08-03 .. 2026-09-10)

| measure | value |
|---|---|
| entry -> first trim (min) | 7.5  (p25 1.5 / p75 30.7, n=117) |
| entry -> full exit (min) | 22.7  (p25 9.6 / p75 199.6, n=112) |
| entries with NO management post at all (silent) | 352 of 530 = 66.4% |
| entries with no posted exit of any kind | 418 of 530 = 78.9% |

**Futures** - 161 entries (high+medium confidence, 2026-08-03 .. 2026-09-10)

| measure | value |
|---|---|
| entry -> first trim (min) | 2866.5  (p25 1.5 / p75 5731.5, n=2) |
| entry -> full exit (min) | 15.0  (p25 8.8 / p75 19.6, n=12) |
| entries with NO management post at all (silent) | 147 of 161 = 91.3% |
| entries with no posted exit of any kind | 149 of 161 = 92.5% |

Read the silent line carefully: an entry with no posted exit is not a loss and not a win. It is **unavailable**. A later high in the tape is not a caller exit.

---

## 2. The first trim

| measure | value |
|---|---|
| entries that got a first trim | 119 of 695 |
| minutes from entry to it | 7.5  (p25 1.5 / p75 30.7, n=119) |
| percent it is posted at | 15.0%  (p25 10.0% / p75 26.1%, n=85) |
| where that percent came from | stated 60, unavailable 34, caller-price 23, caller-price-points 1, measured 1 |
| first trim is the only positive event (no better exit recorded) | 107 of 119 |

Stated trim size, where the caller gives one: 1/2 x15, 1/4 x3.

---

## 3. Their stop

### (a) Posted stops

| measure | value |
|---|---|
| entries carrying a posted stop | 156 of 695 = 22.4% |
| option stops quoted as a premium, distance below entry | unavailable (n=0) |
| option "stops" that are an UNDERLYING level, not a premium | 0 - excluded |
| futures stops, points from entry | 20.0  (p25 8.0 / p75 25.0, n=156) |

Of the futures stops, **84 come from one automated signal poster** that prints a fixed `TP:/SL:` on every message. That is a machine's parameter, not a human's risk decision - read it separately.

### (b) Revealed stops - where a loss exit was actually posted

| measure | value |
|---|---|
| entries with a posted losing exit and a readable percent | 27 |
| the loss at that exit | -17.0%  (p25 -31.0% / p75 -9.3%, n=27) |

### (c) "SL to b/e"

| measure | value |
|---|---|
| entries where a management post moves the stop to breakeven | 24 of 695 |
| minutes after entry that happens | 1063.5  (p25 865.4 / p75 1423.2, n=24) |

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

---

## 5. The match question - was the bot still in when the caller trimmed?

Join: same date, same symbol, same strike, same side, our entry within 5 minutes of theirs, against `master_ledger.csv`.

| measure | value |
|---|---|
| caller entries the ledger also shows a position in | **70** |
| of those, rows with book provenance (not Webull-export-only) | 49 |
| pairs where the caller ALSO posted a first trim (the answerable set) | **24** |
| bot still in when the caller trimmed | **7 of 24** |
| bot already out before the caller's first trim | **17 of 24** |

| our hold time on matched trades (min) | 2.7  (p25 1.3 / p75 5.1, n=60) |
|---|---|
| our exit % on matched trades | -5.5%  (p25 -11.0% / p75 6.7%, n=49) |
| the caller's first-trim clock on the same trades (min) | 8.1  (p25 3.2 / p75 38.0, n=29) |
| the caller's first-trim % on the same trades | 23.1%  (p25 8.0% / p75 34.1%, n=14) |

Side by side, every answerable pair:

| date | contract | caller | their 1st trim | their % | our hold | our % | still in? |
|---|---|---|---:|---:|---:|---:|---|
| 2026-08-18 | QQQ 718.0P | Vero | 5.3 min | unavailable | 2.1 min | -2.5% | NO - out first |
| 2026-08-19 | GOOGL 345.0C | Unraveller | 1.1 min | 18.0% | 2.6 min | -6.2% | yes |
| 2026-08-19 | MRNA 110.0P | MRNA | 0.2 min | unavailable | 1.9 min | 0.0% | yes |
| 2026-08-19 | MSFT 480.0C | Unraveller | 26.8 min | 30.0% | 4.7 min | 0.0% | NO - out first |
| 2026-08-19 | QQQ 716.0P | Vero | 8.0 min | unavailable | 0.4 min | unavailable | NO - out first |
| 2026-08-19 | QQQ 716.0P | Vero | 8.0 min | unavailable | 3.0 min | -14.3% | NO - out first |
| 2026-08-19 | QQQ 716.0P | Vero | 8.0 min | unavailable | 0.7 min | -5.0% | NO - out first |
| 2026-08-19 | QQQ 716.0P | Vero | 8.0 min | unavailable | 3.8 min | 114.9% | NO - out first |
| 2026-08-20 | INTC 90.0P | The Pawn (The Mark | 3.2 min | 22.2% | 3.5 min | 20.3% | yes |
| 2026-08-20 | QQQ 710.0P | Vero | 22.6 min | unavailable | 0.4 min | unavailable | NO - out first |
| 2026-08-20 | QQQ 710.0P | Vero | 22.6 min | unavailable | 3.1 min | 23.6% | NO - out first |
| 2026-08-24 | SNAP 6.0C | The Pawn (The Mark | 1328.0 min | 30.0% | 1.5 min | unavailable | NO - out first |
| 2026-08-25 | MSFT 485.0P | Unraveller | 0.5 min | 8.0% | 1.6 min | 6.7% | yes |
| 2026-08-25 | MSFT 485.0P | Unraveller | 0.5 min | 8.0% | 1.6 min | unavailable | yes |
| 2026-09-01 | FLR 57.5C | ZTRADEZ BOT | 2517.3 min | 34.1% | -301.5 min | -5.5% | NO - out first |
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

`daily-reports/CALLER-OUTCOMES-*.csv` pairs claim events by hand for two days. Small, but every row has both timestamps.

| measure | value |
|---|---|
| claim events paired across the two days | 59 |
| distinct positions whose FIRST trim is timed | 23 |
| entry -> first trim (min) | 13.3  (p25 5.7 / p75 18.8, n=23) |
| first-trim % | 30.0%  (p25 15.0% / p75 70.0%, n=19) |
| full exits recorded | 12 |
| entry -> full exit (min) | 13.2  (p25 5.1 / p75 29.6, n=12) |

Basis on those rows: 37 caller-stated, 5 market-bid-at-exit (measured), 15 unavailable.

---

## 7. Per-caller profile (min 5 linked entries), ranked by matchable

| caller | n entries / linked | median min to 1st trim | typical 1st-trim % | posts a stop | typical stop % of premium | silent | median exit % | matchable |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Brett | 33 / 16 | 4.1 (n=14) | 10.0% (n=14) | 0% | unavailable (n=0) | 52% | 60.0% (n=5) | 46.1 |
| Mike | 37 / 16 | 2.8 (n=12) | 10.0% (n=12) | 0% | unavailable (n=0) | 57% | 21.5% (n=6) | 42.8 |
| 👑KingBeeAri🐝 | 23 / 14 | 20.1 (n=7) | 28.0% (n=5) | 0% | unavailable (n=0) | 39% | unavailable (n=0) | 42.2 |
| Unraveller | 96 / 40 | 0.8 (n=29) | 13.0% (n=23) | 0% | unavailable (n=0) | 58% | -9.3% (n=11) | 39.4 |
| TradingTheTrend | 14 / 7 | 581.3 (n=6) | 16.8% (n=5) | 0% | unavailable (n=0) | 50% | -1.2% (n=4) | 38.5 |
| The Pawn (The Market Bis | 23 / 11 | 1228.9 (n=6) | 29.4% (n=6) | 0% | unavailable (n=0) | 52% | -19.5% (n=6) | 38.0 |
| ZTRADEZ BOT | 36 / 11 | 536.1 (n=6) | 28.6% (n=6) | 0% | unavailable (n=0) | 69% | -33.0% (n=4) | 33.6 |
| TradeLikeGates | 22 / 8 | 5.5 (n=1) | 20.0% (n=1) | 0% | unavailable (n=0) | 64% | 20.0% (n=4) | 30.1 |
| @Futures Alerts | 9 / 5 | unavailable (n=0) | unavailable (n=0) | 89% | unavailable (n=0) | 44% | unavailable (n=0) | -1.0 |
| Vero | 22 / 13 | 8.0 (n=13) | unavailable (n=0) | 0% | unavailable (n=0) | 41% | unavailable (n=0) | -1.0 |

## 8. Per-room

| room | entries | linked | median min to 1st trim | median 1st-trim % | median min to exit | silent |
|---|---:|---:|---:|---:|---:|---:|
| Honey Drip Network 🍯💰📈: ☀️｜daytrades-scalps  | 169 | 73 | 2.0 | 10.0% | 11.4 | 57% |
| ZTRADEZ (OPTIONS & STOCKS): ◽︱all-trades-mas | 48 | 11 | 536.1 | 28.6% | 1054.2 | 77% |
| ZTRADEZ (OPTIONS & STOCKS): ◽︱♟market-bishop | 23 | 11 | 1228.9 | 29.4% | 548.2 | 52% |
| Summit Trading Strategies: 📌｜alert-room #642 | 22 | 8 | 5.5 | 20.0% | 13.4 | 64% |
| Honey Drip Network 🍯💰📈: 👑｜aristotle-trades # | 20 | 13 | 20.1 | 28.0% | 51.0 | 35% |
| Platinum Trading: 🟣│futures-alerts #91139008 | 17 | 7 | unavailable | unavailable | 14.9 | 59% |
| TradingTheTrend: 🚨option-alerts🚨 #7697971799 | 17 | 10 | 84.0 | 18.3% | 1303.1 | 41% |
| VeroTrade: ✅⏐1k-challenge #13237087083744502 | 11 | 7 | 5.3 | unavailable | unavailable | 36% |
| VeroTrade: ✅⏐vero-trades #760694103401955378 | 8 | 6 | 21.0 | unavailable | unavailable | 25% |

## 9. What this cannot say

- It cannot give a caller's win rate or net result. Most entries never get a posted exit, and an unposted exit is unavailable, not a number.
- The hold times describe **callers who post management messages the recovery could link**. Rooms that post an entry and go quiet are in the silent column, not in the medians.
- `their_target` is not recorded anywhere in this repo, so no target study is possible.
- Percentages labelled `stated` are the caller's own claim. They are not broker truth and they are not the bid we could have hit.

