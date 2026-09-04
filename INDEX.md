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
| `🎯 START HERE.bat` | The one button. Pulls latest code, closes Chrome, reopens all 26 rooms, starts the bridge keep-alive, AUTO PUSH, and the announcer. |
| `RESTART BRIDGE.bat` | Restart onto new code by hand. (The bridge also restarts itself on a safe window, or instantly on a non-empty `bridge.restart` file.) |
| `ANNOUNCER.bat` / `STOP ANNOUNCER.bat` | Fill announcer on / off. **Currently paused on purpose.** |
| `EXTRAS.bat` | Keys, log tail, odd jobs. |
| `FIX SDK DEPS.bat` | Repairs the bridge's Python packages if the Webull SDK pins break. |
| `MAKE DESKTOP ICON.bat` | Desktop / taskbar shortcut for START HERE. |
| `SETUP TRADIER.bat` | Connects Tradier read-only. Fund the account BEFORE generating the key — Tradier revokes API access on unfunded accounts and you would have to make it twice. |
| `SETUP TASTYTRADE.bat` | Connects tastytrade read-only. OAuth: you make a client secret + refresh token in your browser, paste them here. Your password is never asked for. Places no orders, does not switch the bot off Webull. |
| `SEND CHANGES TO GITHUB.bat` | Manual push. (AUTO PUSH already sweeps every 45s.) |

Emergency brake: create a file named `STOP` (or `STOP.txt`). The bridge stays
down until you delete it.

## The engine (never move these)

| File | Role |
|---|---|
| `bridge.py` | The HTTP server on 127.0.0.1:8787 the extension talks to. Orders, endpoints, restarts, POSTCHECK. |
| `positions.py` | The Book — what filled, stops, watchdog, ratchet, adopt/reconcile with the broker. |
| `webull_options.py` | Every Webull call: orders, stops, quotes, positions. Rate-limit rules live here. |
| `ratchet_tiers.py` | The stop ladder. −10% start; +10%→BE, +20%→+10%, +30%→+20%. Anti-clip on 2+ DTE only. |
| `quote_bus.py` | One batched option-quote call per second for every open contract → `option_tape.csv`. |
| `stream_bus.py` | Live stock/ETF prices pushed over Webull MQTT. |
| `pullback.py` | The round-number pullback hunter. |
| `signals.py` | Python mirror of the parser — used by tests and audit tools, not by trading. |
| `guards.py` | Position resolution: which trade did they mean. |
| `ai_reader.py` | Hands a messy message to Claude, gets a clean call back. |
| `announcer.py` | Posts fills / milestones / scoreboard to Discord. |
| `webull_futures.py`, `props.py`, `eastern.py` | Futures accounts, prop accounts, market clock. |
| `broker.py` | The broker CONTRACT — 16 methods + capability flags. `get_broker(cfg)` picks one; **defaults to Webull**, so untouched settings behave exactly as before. |
| `tradier.py` · `tastytrade.py` | Second and third brokers. **Neither has touched a live server yet** — run their `verify()` the day a key exists. |
| `extension/` | The Chrome extension. `parser.js` is **the** parser — one grammar for all 26 rooms. `rooms.txt` is the one room list. |

## Checking and auditing (read-only, safe any time)

| File | Answers |
|---|---|
| `replay_check.py` | "What did we miss TODAY?" Replays the day's real messages, flags silent drops and possible missed entries. |
| `audit_history.py` | "What have we missed EVER, and why was a room quiet?" → `ALERT-AUDIT.html` |
| `scoreboard.py` | Per-room signal/trade scoreboard → `SCOREBOARD.html` |
| `jsparse.py` + `extension/parse_batch.js` | Let the Python tools call the REAL parser, so an audit can never disagree with the bot. |
| `test_brokers.py` | Runs the Tradier/tastytrade adapters against a FAKE local server — proves the parsing with no credentials needed. |
| `test_tape.py` | "Did this trade leave a price record?" Proves a managed contract still gets taped when the batched sweep is completely blind, and that the bus says so out loud. |
| `test_positions.py`, `test_signals.py`, `test_resolve.js`, `test_parity.js` | The suite. Parity proves the JS and Python parsers agree. |
| `dump_parse.py` + `samples.txt` | Feeds test_parity. |

## Records (written by the machine)

`trades.log` (dated, the real record) · `bridge.log` (console echo, no dates) ·
`days/*.json` (per-day book) · `option_tape.csv` (our only option tick history) ·
`journal-*.xlsx` (built 4:45pm weekdays) · `DS Logs/` (extension exports — every
message the reader saw) · `corpus/` (room language samples)

## Documentation

`HANDOFF.md` — **the living memory. Read this first.** Every rule in force and
why. · `MAP.html` — how the machine works · `INDEX.md` — this file ·
`README.md` — original setup notes · `v3.5.0/` — broker reference, methodology,
TOS checksheet, **BROKER-TOP4-2026-09.md** (which broker and why) · `project/` — the Claude Project snapshot · `handoffs/` — older
handoffs

## Never touch

- `settings.json` — every API key and webhook. Gitignored. Never commit it,
  never paste its contents anywhere.
- `archive/` — 9/3 cleanup: 187MB of rotated logs, old broker exports, old
  journals and one-off docs. Nothing here is used. **Safe to delete whenever
  you want the disk back.**
