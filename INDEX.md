# Discord Sniper — what every file in this folder is

Written 9/3/26 during the cleanup. If you're looking for *how the machine
works*, open `MAP.html`. This is the file directory. If you're looking for
*the answer to a question G asks*, open `ASK-MAP.md`.

**Nothing here moves.** The Python modules import each other flat
(`import positions`), and the .bat files use plain names — putting the code
in subfolders would break every import and every launcher. Only dead weight
was archived.

---

## Double-click these

| File | What it does |
|---|---|
| `🎯 START HERE.bat` | The one button, fully unattended. Pulls latest code, starts the bridge, AUTO PUSH and the announcer; seeds each Chrome profile with one tab and hands the rooms to the extension (one-shot request) — which opens only the rooms whose hours are open (9:15–4:30 ET; `always` rooms any time). No prompts. |
| `RESTART BRIDGE.bat` | Restart onto new code by hand. (The bridge also restarts itself on a safe window, or instantly on a non-empty `bridge.restart` file.) |
| `ANNOUNCER.bat` / `STOP ANNOUNCER.bat` | Fill announcer on / off. **Currently paused on purpose.** |
| `WHAT DO I HOLD.bat` | **"What is true RIGHT NOW."** Positions and resting orders straight from Webull, then the bot's book, then the feeds — and it says plainly that when the book and the account disagree, the account wins. Read-only. |
| `EXTRAS.bat` | Stop the bridge, tail its log, check the keys, list what the reader missed today. |
| `FIX SDK DEPS.bat` | Repairs the bridge's Python packages if the Webull SDK pins break. |
| `MAKE DESKTOP ICON.bat` | Desktop / taskbar shortcut for START HERE. |
| `SETUP TRADIER.bat` | Connects Tradier read-only. Fund the account BEFORE generating the key — Tradier revokes API access on unfunded accounts and you would have to make it twice. |
| `SETUP TASTYTRADE.bat` | Connects tastytrade read-only. OAuth: you make a client secret + refresh token in your browser, paste them here. Your password is never asked for. Places no orders, does not switch the bot off Webull. |

Emergency brake: create a file named `STOP` (or `STOP.txt`). The bridge stays
down until you delete it.

## The engine (never move these)

| File | Role |
|---|---|
| `bridge.py` | The HTTP server on 127.0.0.1:8787 the extension talks to. Orders, endpoints, restarts, POSTCHECK. |
| `positions.py` | The Book — what filled, stops, watchdog, ratchet, adopt/reconcile with the broker. |
| `webull_options.py` | Every Webull call: orders, stops, quotes, positions. Rate-limit rules live here. |
| `ratchet_tiers.py` | The stop ladder: born −7.5%, +5% → breakeven, then +2% locked per +2% (flat, no cheap tier). Futures: arm at ⅔ of the stop distance, rung every ~27%. Anti-clip on 2+ DTE only. |
| `quote_bus.py` | One batched option-quote call per second for every open contract → `option_tape.csv`. |
| `alert_tape.py` | The SLOW second lane: real bid/ask for every contract the rooms called, including the ones we never bought → `alert_tape.csv` (+ `alert_meta.csv`, the room/caller/greeks of each alert). One batched call every 30s, 5s when nothing is open. Always yields to orders and to the fast bus. |
| `stream_bus.py` | Live stock/ETF prices pushed over Webull MQTT. |
| `pullback.py` | The round-number pullback hunter. |
| `ai_reader.py` | Hands a messy message to Claude, gets a clean call back. |
| `announcer.py` | Posts fills / milestones / scoreboard to Discord. |
| `webull_futures.py`, `props.py`, `eastern.py` | Futures accounts, prop accounts, market clock. |
| `index_mirror.py` | The SPY/QQQ → MES/MNQ mirror: one switch (`execution.index_mirror.enabled`, **OFF**) that replaces a SPY/QQQ option entry with a one-contract micro-futures order, plus the always-on shadow record. Measured, not believed — `futures_mirror_daily.py`. |
| `broker.py` | The broker CONTRACT — 16 methods + capability flags. `get_broker(cfg)` picks one; **defaults to Webull**, so untouched settings behave exactly as before. |
| `tradier.py` · `tastytrade.py` | Second and third brokers. **Neither has touched a live server yet** — run their `verify()` the day a key exists. |
| `extension/` | The Chrome extension. `parser.js` is **the** parser — one grammar for every room. `rooms.txt` is the one room list: EVERY room we've been to, `id\|url\|label\|group\|on/off/lapsed`; the popup's switch rewrites it through the bridge (POST /rooms). |

## Checking and auditing (read-only, safe any time)

| File | Answers |
|---|---|
| `now.py` | Behind WHAT DO I HOLD.bat. Exists because a log line was read as current state (9/4 SPY x5) — logs are past tense, the account is the present. |
| `replay_check.py` | "What did we miss TODAY?" Replays the day's real messages, flags silent drops and possible missed entries. |
| `audit_history.py` | "What have we missed EVER, and why was a room quiet?" → `ALERT-AUDIT.html` |
| `scoreboard.py` | Per-room signal/trade scoreboard → `SCOREBOARD.html` |
| `pullback_levels.py` | "Should the beta names wait for $1, $2, $2.50 or $5?" Replays every logged alert on real 1-second stock bars (Databento, cents; cached in `bars/stock/`) → `reference/PULLBACK-LEVELS.md`. Verdict 9/9: $1 stays. |
| `reference/EOD-BENCHMARK-SPEC.md` | The product contract for daily coverage, alert lifecycle reconciliation, caller-vs-bot counterfactuals, honest backtests, and evidence-gated learning. |
| `postmortem.py` | One verdict per exited trade (call → ride → after we left → the stop → the machine) → `postmortems/*.md` + `master_postmortems.csv`. Auto-runs after every exit. |
| `jsparse.py` + `extension/parse_batch.js` | Let the Python tools call the REAL parser, so an audit can never disagree with the bot. |
| `test_brokers.py` | Runs the Tradier/tastytrade adapters against a FAKE local server — proves the parsing with no credentials needed. |
| `test_tape.py` | "Did this trade leave a price record?" Proves a managed contract still gets taped when the batched sweep is completely blind, and that the bus says so out loud. |
| `broker_sync.py` | **The broker pull that never existed.** First step of the 16:40 audit: one read-only WebullOptions, the day's order history (paged) → `Webull_Orders_auto.csv` OVERWRITTEN, one balance read → `balance_daily.csv`, then `build_ledger`. Until 9/15 nothing pulled it — a Claude session did it by hand, last on 9/11, so 9/12–9/14 reported "broker export missing". |
| `daily_brief.py` | **The one screen G reads.** Near the end of the 16:40 audit: day / bot trades / callers right-wrong / what broke / pending, built only from records already on disk → that day's block in `daily-reports/BRIEF week-of-….md`, posted to Sniper HQ as a file through the Fill Announcer webhook. `python daily_brief.py [YYYY-MM-DD]` re-renders it without posting; `--post` posts. |
| `reports.py` | **The report registry and the REUSE-DON'T-REBUILD cache** (9/15). Every report kind, its builder script, its inputs and its weekly file; `python reports.py status [day]` says CURRENT or STALE and why, `build <kind|all> <day>` skips a CURRENT one, `show <kind> <day>` prints one day's block, `path` names the file. Memory: `reports/INDEX.json`. Writers call `reports.write_day` / `write_csv_rows`; readers `day_text` / `csv_rows`. |
| `status_json.py` | Writes `STATUS.json` (root, < 4 KB) as the audit's LAST step: balance, bot trades, rooms per lane, what broke, pending, bridge health, and the `verified` block (tests, parser_gate, broker reconciliation, bridge code). `python status_json.py [day]` rebuilds it from disk. Read it before any log — ASK-MAP.md. |
| `futures_mirror_daily.py` | Every evening (called by `daily_audit.py` through `reports.py` after the audit): replays the day's SPY/QQQ entries as MES/MNQ on real ES/NQ 1-min bars (bars/ cache, else Databento) → that day's block in `daily-reports/FUTURES-MIRROR week-of-….md` + cumulative `reference/FUTURES-MIRROR-REPLAY.csv`. 9/13 baseline: −$721 over 149 alerts. |
| `test_positions.py`, `test_architecture.py`, `test_brokers.py`, `test_phantom_exit.py`, `test_tape.py`, `test_alert_tape.py`, `test_expiry.py`, `test_index_mirror.py`, `test_resolve.js`, `extension/test_*.js` | The suite. `test_expiry.py` holds every date shape the rooms actually write — a date this reader can't take is not a skipped trade, it's this Friday bought silently. |
| `samples.txt` | Parser samples (fed to `extension/parser.js` by the JS tests). |

## Records (written by the machine)

`master_broker.csv` (**the broker's own record** — every Webull order leg, all days; the
autopilot's daily `Webull_Orders_<date>_auto.csv` is absorbed into it and deleted) ·
`master_ledger.csv` (**THE fill truth** — every fill from every source, reconciled to the
broker; read it via `ledger.py`) · `master_alerts.csv` (every alert and what happened to
it; `ledger.alerts()`) · `backups/` (dated copies of the master files, last 5 each) ·
`trades.log` (dated, the raw story) · `bridge.log` (console echo)
· `days/*.json` (per-day book state — not for analysis) · `journal.csv` (legacy export) ·
`option_tape.csv` / `databento_tape.csv` / `missed_tape.csv` (price tapes — `tape.py`
is the one reader; the databento tape is despiked in place by `clean_tape.py`) · `journal-*.xlsx` (built 4:45pm weekdays) · `DS Logs/` (extension exports — every
message the reader saw; ONE FILE PER WEEK PER LANE, `signal-room-chat week-of-Sep-14-to-Sep-20-2026 (discord).txt`, each capture day under a
`===== Mon Sep 14 2026 =====` header holding only that day's new lines — `ds_logs.py` owns the
naming, the day blocks and the de-dupe; every daily was merged 9/15 and zipped in `archive/`) ·
`daily-reports/` and `daily-audits/` (**one file per WEEK per kind**, `REPORT week-of-Sep-14-to-Sep-20-2026.md`, `AUDIT week-of-….txt`, a `===== Mon Sep 14 2026 =====` block per day newest first, `reports.py` owns them; the one csv is `daily-reports/CALLER-OUTCOMES.csv` with a `date` column; `daily-audits/latest.json` is the last audit's summary) · `reports/INDEX.json` (the report cache's memory) · `STATUS.json` (the day in < 4 KB) ·
`department-reports/` (one `<role>.jsonl` + `.md` per department, appended) · `local-reader-measure/`
(reader measurement corpora, `live.jsonl`, caller identity; finished experiments are zipped in `archive/`) · `corpus/` (room language samples) · `futures_mirror_shadow.csv` (one row per SPY/QQQ
entry the bridge saw, written switch-on or switch-off; the index mirror's input)

## Documentation

`ASK-MAP.md` — **when G asks X, read THIS file / run THIS command.** Start here. ·
`HANDOFF.md` — **the living memory. Read this second.** Every rule in force,
compact (<30 KB); the mechanics live in one `reference/` doc per subsystem
(ENTRIES, RATCHET, ROOMS-TABS, OPERATIONS) plus DATA-MAP and the broker
reference. · `HANDOFF-LOG.md` — the full history behind every rule
(every session's notes, newest first; grows forever, HANDOFF.md may not) ·
`MAP.html` — how the machine works · `INDEX.md` — this file ·
`README.md` — original setup notes · `reference/` — the shelf: **OPTIONS-BROKER-REFERENCE.md** (broker facts — read
before any broker test), **BROKER-TOP4 / BROKER-CHOICE** (which broker and why), ANTI-CLIP
study, SDK-AUDIT (what we could use and don't), **FELONY-ZOOM-JOIN.md** (how to get
into Felony's morning Zoom so the ears hear it) · `project/` — Claude reference setup,
with instructions pointing to the live files. Daily performance lives in `daily-reports/`.
Retired handoffs are preserved as historical evidence in
`archive/retired-handoff-documents-2026-09-12.zip`; their rules must not be applied.

## Never touch

- `settings.json` — every API key and webhook. Gitignored. Never commit it,
  never paste its contents anywhere.
- `archive/` — where retired things go: rotated SDK logs
  (`archive/webull-api-logs/`, written there directly), zipped dailies and
  finished experiments (the 9/15 zips), old broker exports, journals and
  one-off docs; `archive/2026-09-09-cleanup/` — dead scripts, superseded tools
  and executed docs (see its MANIFEST.txt). Nothing in archive/ is used.
  **Safe to delete whenever you want the disk back.**
