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
| How did we do today? | `STATUS.json` | `balance.day_pl` (Webull's own, net), `bot.trades` / `bot.pl` / `wins` / `losses`, `audit.status` | not trades.log, not the ledger by hand |
| …and the one-screen version | `python reports.py show brief <day>` | the whole block (Day / Bot trades / Callers / What broke / Pending) | never rebuild a CURRENT brief |
| How did we do this week? | `balance_daily.csv` (one row per day: `date,nlv,day_pl,bp`) + `daily-reports/BRIEF week-of-….md` | sum `day_pl` over the week's rows; per day, each BRIEF block's first line | not master_broker by hand |
| Who's profitable? / scoreboard | `SCOREBOARD.html` (`python reports.py build scoreboard` if `status` says STALE) | the per-room table; money comes from master_ledger.csv only | not counts from DS Logs |
| Which callers were right / wrong on a day | `python reports.py show caller-outcomes <day>` or `daily-reports/CALLER-OUTCOMES.csv` rows with `date == <day>` | `event`, `reported_pct` / `calculated_pct`, `basis` | a later high is never a caller exit |
| Caller hold time / first trim / stop | `reference/CALLER-PROFILE-2026-09-14.md` | "first trim median 5.4 min at +17%", revealed give-up −17%, the per-caller table | rebuild only with `python reference/caller_profile.py` when new CALLER-OUTCOMES rows exist |
| Why didn't X fire? | `python reports.py show report <day>` → "Every recognized decision" table (Result / Reason / Source message) | the row for X: `Result` + `Reason`; the Open in Chrome link is the source | then only if absent: `master_alerts.csv` `outcome/reason/detail` for that date; last resort `trades.log` REFUSED/BLOCKED lines |
| Is the bridge up? Are rooms open? | `STATUS.json` → `bridge.up`, `bridge.health.lanes[*].fresh`, `rooms.<lane>.on / spoke / reads`; live: `http://127.0.0.1:8787/` and `department-reports/health-latest.json` | `up`, `fresh`, `issues`, `rooms_expected` | not Chrome screenshots, not bridge.log |
| What broke? | `STATUS.json` → `broke` (newest 5 review-queue items) and `audit.failed_checks`; then `python reports.py show brief <day>` → "What broke" | `silent_drops`, `possible_missed`, `failed_checks`, the brief's "- …" lines | read `daily-audits/AUDIT week-of-….txt` only for the replay detail |
| What's pending / waiting on me? | `STATUS.json` → `pending`; the full text is HANDOFF.md "## Pending external setup and decisions" | the numbered items | — |
| Balance / buying power | `STATUS.json` → `balance` (nlv, day_pl, bp, as_of); live bp: `bridge.buying_power` | the numbers as printed | never estimate from fills |
| Ratchet replay (5/3/5 vs fixed stop; from the caller's entry) | `python reports.py show ratchet-compare <day>` / `show caller-vs-ratchet <day>` | the summary lines ("Our ratchet on the N paths…", coverage stated) | never extrapolate past the stated coverage |
| Why didn't we get filled? / should we loosen the entry? | `python reports.py show entry-slack <day>` | the `VERDICT —` line, then the COVERAGE sentence and the "vs today" column of the slack table | the switch is OFF and activation is BLOCKED — this is a measurement, and the absolute "model net" column is biased; read the difference |
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
