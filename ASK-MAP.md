# ASK-MAP — when G asks …, read THIS one file / run THIS one command

Rule (HANDOFF.md, ASK-MAP FIRST, G 9/15): every ask starts here, then
STATUS.json. Logs are read only when those two cannot answer. Checks recorded
in `STATUS.json.verified` are trusted while their inputs are unchanged
(VERIFY ONCE) — do not re-run tests, the gate or the broker reconciliation
for confidence. Reports whose inputs have not changed are handed over as they
are (`reports.py status` decides — REUSE, DON'T REBUILD).

Paths are relative to the repo root. `<day>` is `YYYY-MM-DD`; omitted = today
(Eastern). A weekly file holds one `===== Mon Sep 14 2026 =====` block per day,
newest first; `python reports.py show <kind> <day>` prints just that day.

| When G asks … | Read / run | Quote from it | Not this |
|---|---|---|---|
| How did we do today? | `STATUS.json` | `balance.day_pl` (margin, Webull's own, net) + `balance.fut_pl` (futures, net of `fut_fees`) = the day; `balance.flow` / `fut_flow` = money moved, NOT trading; `bot.trades` / `bot.pl` / `wins` / `losses`, `audit.status` | not trades.log, not the ledger by hand |
| …and the one-screen version | `python reports.py show brief <day>` | the whole block (Day / Bot trades / Callers / What broke / Pending) | never rebuild a CURRENT brief |
| How did we do this week? | `balance_daily.csv` (one row per day: `date,nlv,day_pl,bp,…,fut_nlv,fut_pl,fut_fees,flow,fut_flow`) + `daily-reports/BRIEF week-of-….md` | sum `day_pl` + `fut_pl` over the week's rows (never the NLV change — `flow` is transfers); per day, each BRIEF block's first line | not master_broker by hand |
| Which callers are worth following? / who goes silent? | `daily-reports/CALLER-SCORECARD.md` (rebuilt by the daily audit; by hand `python reference/caller_scorecard.py`) | per caller: alerts, silent %, FOLLOW HIM vs LADDER per alert — rows marked *(few)* are under 10 alerts and are NOT a ranking | measurement only — benching a room is G's call |
| Who's profitable? / scoreboard | `SCOREBOARD.html` (`python reports.py build scoreboard` if `status` says STALE) | the per-room table; money comes from master_ledger.csv only | not counts from DS Logs |
| Which callers were right / wrong on a day | `python reports.py show caller-outcomes <day>` or `daily-reports/CALLER-OUTCOMES.csv` rows with `date == <day>` | `event`, `reported_pct` / `calculated_pct`, `basis` | a later high is never a caller exit |
| Caller hold time / first trim / stop | `reference/CALLER-PROFILE-2026-09-14.md` | "first trim median 5.4 min at +17%", revealed give-up −17%, the per-caller table | rebuild only with `python reference/caller_profile.py` when new CALLER-OUTCOMES rows exist |
| Why didn't X fire? | `python reports.py show report <day>` → "Every recognized decision" table (Result / Reason / Source message) | the row for X: `Result` + `Reason`; the Open in Chrome link is the source | then only if absent: `master_alerts.csv` `outcome/reason/detail` for that date; last resort `trades.log` REFUSED/BLOCKED lines |
| Is the bridge up? Are rooms open? | `STATUS.json` → `bridge.up`, `bridge.health.lanes[*].fresh`, `rooms.<lane>.on / spoke / reads`; live: `http://127.0.0.1:8787/` and `department-reports/health-latest.json` | `up`, `fresh`, `issues`, `rooms_expected` | not Chrome screenshots, not bridge.log |
| What broke? | `STATUS.json` → `broke` (newest 5 review-queue items) and `audit.failed_checks`; then `python reports.py show brief <day>` → "What broke" | `silent_drops`, `possible_missed`, `failed_checks`, the brief's "- …" lines | read `daily-audits/AUDIT week-of-….txt` only for the replay detail |
| What's pending / waiting on me? | `STATUS.json` → `pending`; the full text is HANDOFF.md "## Pending external setup and decisions" | the numbered items | — |
| Caller-price rule / resting window / with-vs-counter trend replay | `reference/CALLER-PRICE-WINDOW-REPLAY.txt` (rebuild: `python reference/caller_price_window_replay.py`; rows in the .csv beside it) | the THE RULE block and the two TREND blocks, with their trade counts | measurement only; more quotes: `python reference/alert_quote_pull.py` prints the cost first and spends nothing without `--pull` |
| Why is the win rate so low? / what if the stop were wider? | `reference/WIN-RATE-DIG.txt` (rebuild: `python reference/win_rate_dig.py`) | section 4 (one change at a time), 5 (no stop at all), 7 (time of day) | measurement only |
| What was the trend when X alerted? | `alert_trend.csv` (`label`, `with_trend`, `legs`) — written live by the bridge; mechanics in `trend.py` | the row | nothing trades on it |
| Was a trade with or against the trend? / P&L by trend | `trade_trend.csv` (one row per ledger option trade: `label`, `with_trend`, `legs`) + `reference/TRADE-TREND.txt`; rebuild `python trade_trend_label.py` | the BOT and HAND blocks | lives BESIDE master_ledger.csv, never inside it |
| Did contract X ever print price Y? | `option_bars.csv` (Webull 1-min / 5-min option TRADE bars; refresh `python option_bars_pull.py` after the close) | the bar's high/low and its time | no bid/ask in it — fills and stops still come from the quote tapes |
| Does the trend label predict the next 5-60 min? / do turns happen at round hours or 5-0 prices? | `reference/TREND-PREDICT-TEST.txt` (rebuild `python reference/trend_predict_test.py`; `--no-fetch` uses the cache only) | PART 1 table, PART 2 lifts and z | measurement only |
| Futures fills / fees / P&L (a day or all time) | `master_futures.csv`; `python -c "import broker_sync;print(broker_sync.futures_day('<day>'))"` | `net`, `gross`, `fees`, `by_code`, and `open` / `unpriced` if not scorable | not the Webull connector by hand, not trades.log |
| Balance / buying power | `STATUS.json` → `balance` (nlv, day_pl, bp, as_of); live bp: `bridge.buying_power` | the numbers as printed | never estimate from fills |
| Ratchet replay (5/3/5 vs fixed stop; from the caller's entry) | `python reports.py show ratchet-compare <day>` / `show caller-vs-ratchet <day>` | the summary lines ("Our ratchet on the N paths…", coverage stated) | never extrapolate past the stated coverage |
| Why didn't we get filled? / should we loosen the entry? | `python reports.py show entry-slack <day>` | the `VERDICT —` line, then the COVERAGE sentence and the "vs today" column of the slack table | the switch is OFF and activation is BLOCKED — this is a measurement, and the absolute "model net" column is biased; read the difference |
| Single-name alerts (TSLA/NVDA/AAPL…) as micro stock futures | `reference/STOCK-FUTURES-MIRROR-GRID.txt` (rebuild `python reference/stock_futures_mirror_grid.py`) | 24-cell table, BY NAME, BY CALLER, BY TIME, MFE | stock 1-min bars stand in for the future; Webull lists these contracts NT (non-tradable) as of 9/18 — measurement only |
| Flip at the futures target and trade back the other way | `reference/REVERSE-AT-TARGET-TEST.txt` (rebuild `python reference/reverse_at_target_test.py`) | base vs reverse trades, winners/losers | measurement only — reverse is 50/50 |
| NinjaTrader ATM templates / indicator for the futures mirror | `ninjatrader/ATM-TEMPLATES.md` (rebuild `python ninjatrader/atm_templates.py`), `ninjatrader/SniperQuoteTape.cs` | the two templates in ticks, the install steps | numbers come from futures_mirror_daily.LEVEL |
| MNQ entry x exit sweep (grid, through/before, wait, time filter x stop/BE/rung/target) | `reference/MNQ-ENTRY-SWEEP.txt` (rebuild `python reference/mnq_entry_sweep.py`) | top by win%, top by $, knob averages | 10,416 rows on 61 alerts — read the knob averages, not the top row |
| A year of room history as alerts (from the grabs) | `grab_alerts.csv` (rebuild `python grab_to_alerts.py` after each new grab in DS Logs) | date, time ET, room, caller, symbol, side, strike, expiry, their_price | parsed by the production parser; the futures mirror and every reference replay read it |
| Per-caller edge on the index mirror (Brett / Mike / Vero / Unraveller / Owner Alerts …) | `reference/CALLER-EDGE.txt` (`python reference/caller_edge.py`) | per caller × instant/level × MNQ/MES × calls/puts: n, $, win%, IS/OOS, random control | honest sim; Honeydrip relabelled by the @name in the relay text; n under ~150 proves nothing |
| Does the next dollar hold after a break? (714 breaks -> 713 holds or goes to 712.50; up mirrored) | `reference/LEVEL-HOLD-TEST.txt` (`python reference/level_hold_test.py SPY QQQ`) | per symbol × direction × trend filter: breaks, % that reach the next $, HOLDS vs CONTINUES, straight / bounce-then-through / bounce-then-reclaim; half-dollar CONTROL rows | 1-min RTH bars in bars/stock_m1 (fetch_stock_days.py fills a year); whole dollars behave like half dollars |
| A room's history, raw (one grab) | `DS Logs/grab <channel_id> <room> <date>.txt` + `.json` twin | one line per message: UTC minute, message id, author, full text incl. embeds, ` [image]` when it carried an upload (urls only in the .json, ~1 day) | the scroll's own rows (v3.8.59), never the live capture store; 0 rows = no file; tests: test_grab_scroll.js, test_grab_rows.js |
| Does any idea have an edge on the futures mirror? (the honest bench) | `reference/edge_lab.py` (import it; the 9/19 runs are in HANDOFF-LOG 11:30) | per line: n, $, per fill, win%, dd, months+, IN-SAMPLE vs OUT-OF-SAMPLE, random-direction control | trust nothing that fails OOS or that its random control matches |
| Do the callers' single-name calls move the stock? | `reference/SINGLE-NAME-LAB.txt` (rebuild `python reference/single_name_lab.py`; bars via `fetch_stock_days.py`) | instant entry on stock bars, 10 shares, by exit / caller / symbol, with controls | 1,298 alerts: coin flip |
| Alert + wait for the ES 25 / NQ 50 pullback to ENTER (futures) | `reference/PULLBACK-LEVEL-ENTRY-TEST.txt` (rebuild `python reference/pullback_level_entry_test.py`) | fills, pullback $, win%, avg wait vs the same alerts instant | touch-fill; measurement only |
| Best stop / arm / rung / target per instrument (MES vs MNQ), 520 combos, both-halves check | `reference/FUTURES-RATCHET-SWEEP.txt` (rebuild `python reference/futures_ratchet_sweep.py`) | TOP 12, BOTTOM 3, BEST positive in both halves, knob averages | measurement only; n=110/61 — read the overfit line first |
| Round-level targets (ES 25s / NQ 100s) close-at-level vs trail-under | `reference/LEVEL-TARGET-TEST.txt` (rebuild `python reference/level_target_test.py`) | 8 lines + per caller for the best | measurement only |
| SPY/QQQ alerts as MES/MNQ under other stops / ratchets | `reference/FUTURES-MIRROR-GRID.txt` (rebuild `python reference/futures_mirror_grid.py`) | the 24-cell table, BY CALLER, BY TIME OF DAY, the MFE line | days without ES/NQ bars are named in the header; measurement only |
| Futures mirror (SPY/QQQ as MES/MNQ) | `python reports.py show futures-mirror <day>`; running total `reference/FUTURES-MIRROR-REPLAY.csv` | day total, running total since 2026-08-03, "bars: unavailable" if unscored | the switch is OFF — this is a measurement |
| Give me the report for `<day>` | `python reports.py status <day>` → if CURRENT: `python reports.py path report <day>` and hand that file (or `show`); if STALE: `python reports.py build report <day>` | the file itself | never rebuild a CURRENT one; never paste logs into a report |
| List bot trades (a day) | `python reports.py show brief <day>` → "Bot trades"; or `master_ledger.csv` rows with `date == <day>`, `account == live`, not `manual` | one line per round trip: contract, in → out, P&L, why it exited | not days/*.json, not journal.csv |
| List bot trades (all time) | `master_ledger.csv` via `ledger.py` | `date, caller, room, symbol, strike, side, expiry, avg_in, exit_avg, pl, exit_by` | not trades.log |
| Did trade X exist / what filled? | `master_broker.csv` (`status == FILLED`, `avg_price`) | the leg rows | if Webull has no row, it never happened |
| What is open RIGHT NOW? | `WHAT DO I HOLD.bat` (`now.py`) — Webull itself | positions + resting orders | never a log; logs are past tense |
| What did a caller actually post? | `DS Logs/signal-room-chat week-of-… (lane).txt`, that day's block, RAW MESSAGES | the line (`[Server: channel #id message_id=…]  text`) | — |
| Are the tests / gate / broker reconciliation green? | `STATUS.json` → `verified.tests`, `verified.parser_gate.counts` (messages / entries / actions), `verified.broker_reconciled.match`, `verified.bridge_code_live.sha` | the recorded numbers and their `at` | VERIFY ONCE: re-run only when a touched input changed (code, rooms.txt, the day's data) |
| Is a report current or stale, and why? | `python reports.py status [day]` | `CURRENT` / `STALE [changed: …]` | — |
| Why didn't a futures alert trade? | `webull_futures.protective_entries_reason(symbol)` — PER MICRO (same sentence in the refusal, `/mode` → `webull_futures_entry_by_symbol`, and the popup's futures line); mechanics in `reference/OPERATIONS.md` → "The futures entry gate" | the reason verbatim — that micro has no proof yet, a failed/missing step, or webull_futures.py changed since the proof | not the switch, not the subscription: the gate is that symbol's block of `futures_protection_proof.json`. MES proven is NOT MNQ proven, ES/NQ are judged on the micro they'd buy, and only G's own `--symbol <micro> --live` run writes a block |
| What rule applies to …? | HANDOFF.md (one line per rule) → the `reference/` doc it points to (the mechanics behind it) | the rule line, then the reference doc's detail | not HANDOFF-LOG.md (history, not instructions) |
| What is file X / what is in it? | INDEX.md (what it is) → DATA-MAP.md (what is inside) | the row | — |

Commands, all read-only and local:
`python reports.py status [day]` · `python reports.py show <kind> <day>` ·
`python reports.py path <kind> <day>` · `python reports.py build <kind|all> <day>`
(skips CURRENT) · `python status_json.py [day]` (rebuild STATUS.json from disk) ·
`python reports.py kinds` (the registry). Kinds: report, brief, caller-outcomes,
caller-vs-ratchet, ratchet-compare, futures-mirror, entry-slack, audit,
scoreboard, alert-audit (+ the hand-made alert-ledger, ninjago-futures-radar, alert-history,
parser-history).
