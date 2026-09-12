# Discord Sniper — what every file in this folder is

Written 9/3/26 during the cleanup. If you're looking for *how the machine
works*, open `MAP.html`. This is the file directory.

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
| `test_positions.py`, `test_architecture.py`, `test_brokers.py`, `test_phantom_exit.py`, `test_tape.py`, `test_alert_tape.py`, `test_expiry.py`, `test_resolve.js`, `extension/test_*.js` | The suite. `test_expiry.py` holds every date shape the rooms actually write — a date this reader can't take is not a skipped trade, it's this Friday bought silently. |
| `samples.txt` | Parser samples (fed to `extension/parser.js` by the JS tests). |

## Records (written by the machine)

`master_broker.csv` (**the broker's own record** — every Webull order leg, all days; the
autopilot's daily `Webull_Orders_<date>_auto.csv` is absorbed into it and deleted) ·
`master_ledger.csv` (**THE fill truth** — every fill from every source, reconciled to the
broker; read it via `ledger.py`) · `master_alerts.csv` (every alert and what happened to
it; `ledger.alerts()`) · `backups/` (dated copies of the master files, last 5 each) ·
`trades.log` (dated, the raw story) · `bridge.log` (console echo)
· `days/*.json` (per-day book state — not for analysis) · `journal.csv` (legacy export) ·
`option_tape.csv` / `databento_tape_clean.csv` / `missed_tape.csv` (price tapes — `tape.py`
is the one reader) · `journal-*.xlsx` (built 4:45pm weekdays) · `DS Logs/` (extension
exports — every message the reader saw) · `corpus/` (room language samples)

## Documentation

`HANDOFF.md` — **the living memory. Read this first.** Every rule in force,
compact (<50 KB). · `HANDOFF-LOG.md` — the full history behind every rule
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
- `archive/` — 9/3 cleanup: 187MB of rotated logs, old broker exports, old
  journals and one-off docs. `archive/2026-09-09-cleanup/` — 9/9: dead
  scripts, superseded tools and executed docs (see its MANIFEST.txt for each
  item and why). Nothing in archive/ is used. **Safe to delete whenever you
  want the disk back.**
