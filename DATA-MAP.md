# DATA-MAP.md — what is INSIDE every data file

`INDEX.md` says what each file **is**. This file says what is **in** it: the
columns, the line types, the counts, the date range, and the traps. Read it
before you grep, and before you conclude that something is not recorded.

Every number below was counted on **2026-09-11, 02:12 ET**. Counts in LIVE
files move; the shape does not.

---

## The 60-second version

| I need… | Open |
|---|---|
| What a caller actually posted | `DS Logs/signal-room-chat *.txt` (raw messages) + `trades.log` `AI READ` lines |
| What the bot decided and why | `DS Logs/*.txt` "WHAT THE BOT DID" block (`<sent>` `<skipped>` `<ignored>` `<failed>`) |
| The contract the bot resolved | `trades.log` `ORDER IN` lines (181, fully resolved, dated) |
| What actually filled | `master_broker.csv` (the broker's own record) |
| What a contract cost minute by minute | `databento_tape_clean.csv` (49 days, 510 contracts), then `option_tape.csv` |
| What is true right now | Webull itself — `WHAT DO I HOLD.bat`. Never a log. |

**LIVE files change under you.** The bridge is running. These are being written
right now: `trades.log`, `bridge.log`, `deadman.log`, `webull_api.log`,
`telemetry.csv`, `shadow_ratchet.csv`, `state.json`, `days/<today>.json`,
`handoffs/HANDOFF-<today>.md`, and — during market hours — `option_tape.csv`,
`alert_tape.csv`, `alert_meta.csv`, `quote_shadow.csv`, `greeks_tape.csv`.
`master_ledger.csv`, `master_alerts.csv` and `journal.csv` are **rebuilt from
scratch** by `build_ledger.py`, not appended — a row can vanish between two
reads. Copy a file to your own scratch folder before a long analysis.

---

# 1. trades.log — THE most under-read file in the repo

**Question it answers:** what did the bot see, decide, send, fill and exit,
minute by minute, in plain English.

**Shape:** `<ISO timestamp with -04:00 offset>` TAB `<message>`. The first word
of the message is the line type. One line per event, no wrapping.

**9,853 lines · 2026-08-01 → 2026-09-11 · LIVE (appended continuously) · never rotated.**

**63 distinct line types.** Full list, with counts and a real example:

### The two that rebuild history

| Type | n | Example | Good for |
|---|---|---|---|
| `AI READ` | 2,222 | `AI READ  '@Mike (Admin) in NVDA 8/14 220C @ 4.0 @everyone'  ->  BTO NVDA $220C 8/14 @ 4` | **636 of these carry the original Discord message and the bot's reading of it.** The single best source for "what did the caller actually say". |
| `ORDER IN` | 181 | `ORDER IN BUY 5 SPY 600C 2026-08-06 @ 175.91` / `ORDER IN [L] BUY 1 NVDA 207.5C 2026-08-28 @ 7.97  [stop 7.17 born with it]` | **Every order the bot sent, with a fully resolved contract and a real date.** 177 plain, 4 with a `[L]` (live) marker and the stop price. |

`AI READ` breaks down as: **636** quoted-message reads (`'…'  ->  BTO …`),
**1,385** `no call` lines (1,077 "the reader saw no call", 139 HTTP 404, 88 HTTP
401, the rest named-symbol rejects), **191** "key verified", **7** "reader ON".
The 636 span 442 in August and 194 in September.

> **Trap:** the quoted message is **truncated to 50 characters** — 453 of the
> 636 hit the cap. The `-> BTO …` half after the arrow is the bot's *complete*
> reading, so read the right-hand side for the contract and the left-hand side
> only for attribution. Neither half carries the room name; link a read to its
> room through the `WORKING` / `REFUSED` / `ERROR` / `TEST` line that follows,
> which does carry `(<caller>'s call)`.

### Entry path

| Type | n | Example | Good for |
|---|---|---|---|
| `PULLBACK` | 709 | `PULLBACK AAPL CALL: stock at 309.24, waiting for a dip to $309 (300s window)` | The round-number wait. 144 "touched", 91 "waiting for a dip", 69 "refused up front", 62 window notices, 54 "managing off the stock". |
| `WORKING` | 203 | `WORKING  AAPL — Bullwinkle's call, bid is in at 1.13 for 5, waiting for a seller (90s)` | **Carries the caller's name and the bid price.** The link between an `AI READ` and an `ORDER IN`. |
| `REFUSED` | 110 | `REFUSED  OPEN NFLX (EvaPanda Alerts's call) 75C 08/07/2026 x5 @ 0.61  ->  couldn't get a quote …` | Why an alert never became an order. Carries room-caller, contract, size, their price. |
| `ERROR` | 45 | `ERROR    OPEN AAOI (EvaPanda Alerts's call) 170C 08/07/2026 x5 @ 2.38  ->  HTTP 417 …` | Broker rejections, with the Webull error code. |
| `NOFILL` | 44 | `NOFILL   AAPL — no fill (nobody sold at 1.13 within 90s). You are NOT in this one.` | Bids that expired. |
| `NO-OTM` | 72 | `NO-OTM   NVDA: their 225C was OTM (stock 217.93) -> nearest qualifying 217.5C` | Where our strike differs from the caller's, and why. |
| `BLOCKED` | 15 | `BLOCKED  OPEN SPY 772 — expiry 08/02 already passed (expired 3 day(s) ago)` | Dead-expiry rejects. |
| `SWING-OFF` | 11 | `SWING-OFF INTC refused — swing trades are PAUSED (9/18 is 14 days out …)` | Alerts lost to the swing switch. |
| `TEST` | 11 | `TEST     OPEN NVDA (?'s call) 225C 2026-08-14 x1  ->  test room, nothing sent` | Rooms that were on test. Nothing was traded. |
| `ITM-3` | 6 | `ITM-3    SPY — no quoted strike found near 771.40, so the caller's strike stands` | Strike-snap decisions. |
| `IMG READ` | 153 | `IMG READ  [screenshot]  ->  TRIM SPY   (saw: 'SPY 08/19 771P @.96 (+35%)')` | Every vision read. Same `saw:` truncation habit as `AI READ`. |
| `VOICE` | 7 | `VOICE    Deepgram key saved on this PC` | Key status only — **not** the transcripts. Transcripts are in `DS Logs/` and `reads.log`. |

### Fill and exit path

| Type | n | Example | Good for |
|---|---|---|---|
| `FILLED` | 143 | `FILLED   HPE — filled 5 at 3.02 — cost $1510` | Entry price and dollar cost. |
| `SOLD` | 32 | `SOLD     SELL 1 META 595C 2026-08-21 @ 4.40` | Exit legs with a price. |
| `STOP-SET` | 362 | `STOP-SET SPY — stop was born WITH the order and is resting at Webull at 0.14` | Every stop placement and every ratchet move. |
| `STOP-WARN` | 318 | `STOP-WARN FCX — Webull wouldn't hold a resting stop (HTTP 417 …)` | Stops the broker refused — the watchdog carried these. |
| `STOP-PULLED` | 89 | `STOP-PULLED HPE — pulled the resting stop before selling` | |
| `STOPPED` | 272 | `STOPPED  HPE — bid hit 2.35, at or under your 2.42 stop. Selling 5.` | The stop trigger and the bid that caused it. |
| `FAILED` | 278 | `FAILED   HPE — the stop tried to sell and couldn't: HTTP 417 …` | Exits that did not go through. **A `FAILED` is not a loss — it means nothing happened.** |
| `UPDATE` | 204 | `UPDATE   NVDA — up 20%, hitting your +20% take-profit. Closing all 1.` | Take-profit and ratchet narration. |
| `CLOSED` | 169 | `CLOSED   FCX — gone from your Webull account — you closed it yourself` | Includes positions G closed by hand. |
| `TRIMMED` | 15 | `TRIMMED  AAPL — their trim — sold 1 at 1.82 (+$15 on those)` | |
| `EXIT` | 39 | `EXIT     your bid on SPY never filled, so there was nothing to sell.` | |
| `EXIT-IGNORED` | 2 | `EXIT-IGNORED CLOSE SPY — entries only: the ratchet owns the exit (ZTRADEZ BOT said: OUT)` | Room-side exits we deliberately did not trade. **Only 2 lines — the bulk of these live in `DS Logs/` as `<ignored>` (2,461).** |
| `PULLED` | 12 | `PULLED   SPY — their exit landed before your bid filled.` | |
| `UNDER-STOP` | 2 | `UNDER-STOP SPCX: watching the STOCK — the option closes if SPCX prints at/under 135.00` | The caller's own hard stop, on the stock. |
| `PHANTOM` | 8 | `PHANTOM  NVDA — the book recorded 'closed' but the broker STILL holds it` | Book-vs-broker disagreements. |
| `POSTCHECK` | 81 | `POSTCHECK FILLED C — PROBLEM: C stop 3b88fc80 is 'unknown' at Webull` | Post-order verification. |
| `FLATTEN` | 17 | `FLATTEN  FCX FAILED -> HTTP 417 …` | End-of-day flattens. |
| `BRACKET` | 2 | `BRACKET  SNAP — Webull wouldn't take the linked group (HTTP 417 …)` | |

### Position book

| Type | n | Example |
|---|---|---|
| `ADOPTED` | 480 | `ADOPTED  FCX x1 picked up from your Webull account — the bot can see it and exit it` |
| `ADOPT` | 109 | `ADOPT    left QQQ x5 alone — bigger than anything the bot trades, so it's YOURS.` |
| `RESTORED` | 143 | `RESTORED 7 position(s) from the last run — swings survive a restart now` |
| `PURGED` | 15 | `PURGED   MNQU6 — an adopted futures row over a day old that the broker can't confirm.` |
| `DROPPED` | 3 | `DROPPED  SPY was recorded as a futures position but isn't a futures contract` |
| `SWING` | 35 | `SWING    XPEV — wide -25% stop (swing, no level given)` |
| `keeping` | 1 | `keeping the position book — 2 still open, so the stop on it stays where it is` |
| `reverse` | 1 | `reverse math: their average moved to 3.17 across 2 fills, so the add went off at ~5.91` |

### Futures and prop

| Type | n | Example |
|---|---|---|
| `FUTURES` | 152 | `FUTURES  ERROR OPEN MNQ (Stormzy's call) x3 @ 29785.25 -> couldn't work out which MNQ contract is front month` |
| `FUT-POS` | 147 | `FUT-POS  Webull has returned no futures position 3 times running — asking every 10s` |
| `TOPSTEP` | 199 | `TOPSTEP  key VERIFIED — connected for giancuffaro230` |
| `PROP` | 56 | `PROP     NinjaTrader <- SELL MGC x1 (NinjaTrader OIF DS7c9483e177)` |
| `PROP-NO` | 29 | `PROP-NO  Topstep: MGC is switched off for Topstep — his call. Nothing was sent.` |

### Machine state — noise for trade analysis, gold for "why was it quiet"

| Type | n | What it is |
|---|---|---|
| `CODE` | 728 | Code changed on disk; a restart is pending. |
| `Webull` | 480 | Connection banners (multi-account ambiguity, not connected). |
| `test` | 244 | "test account: unlimited" startup banner. |
| `paper` | 226 | Paper-mode banners. |
| `STRATEGY` | 218 | `STRATEGY forced ON at bridge start: 1 contract, +20% take-profit, -10% stop` — **the settings in force at that moment.** |
| `GREEKS` | 179 | DXLink greeks lane on/off. |
| `DEADMAN` | 130 | Thread watchdog armed. |
| `QUOTE` | 96 | Quote bus on/off. |
| `STREAM` | 85 | MQTT stock stream on/off. |
| `no` | 85 | `no date in that call, so using this week's Friday (2026-08-07)` — **expiry inference decisions.** |
| `ACCT` | 68 | Account selection. |
| `ROOMS` | 53 | `ROOMS    learned 102 channel name(s) from the extension` |
| `LOGS` | 26 | Log rotation sweeps. |
| `SELF-UPDATE` | 14 | `SELF-UPDATE pulled 3ca1211..713115a — restarting the bridge` |
| `ALERT` | 9 | Alert-tape lane on/off. |
| `KEYS` | 5 | Key changes. |
| `CALLERS` | 2 | `CALLERS  marketgurualerts -> OFF (popup switch)` |
| `PAPER` | 1 | Paper mode on. |

### trades.log traps

- **Line types are padded to 8 characters**, so match on `\tKEYWORD` not on the
  keyword alone. `ADOPT` is a different type from `ADOPTED`; `STOP-SET`,
  `STOP-WARN` and `STOP-PULLED` all start `STOP-`.
- **No room name on `ORDER IN`, `FILLED`, `STOPPED` or `SOLD`.** The room and
  caller appear on `WORKING`, `REFUSED`, `ERROR`, `TEST` and `FUTURES`. To
  attribute a fill to a room, walk backwards to the nearest such line.
- **August 1–3 is bench noise**, not trading: banners, key setup, account
  ambiguity. The first `ORDER IN` is 2026-08-05.
- A `STOPPED` line does **not** prove a sale happened. Look for the matching
  `SOLD`/`FILLED`, or a `FAILED` right after it.
- The file is never rotated and never truncated. Nothing has been lost.

---

# 2. DS Logs/ — the extension's exports

**Question they answer:** every message the reader saw in every room, and what
the bot did with each one.

21 `signal-room-chat <Month-D>-2026.txt` files, 8 KB to 6.5 MB each,
2026-08-18 → 2026-09-11 (weekdays only; 2026-09-11 is the newest). Frozen once
written — a new file is written each night, the old ones are never edited.

Each file has three blocks:

**`=== CURRENT STATE ===`** — a photo of the machine at export time: version,
bridge/Webull status, buying power, the bracket settings, and **the full LIVE /
OFF / SHADOW room list for that day**. This is the only record of which rooms
were on which day.

**`=== RAW MESSAGES THE READER SAW (n) ===`** — one line per message:

```
2026-09-08 15:23:49  [Platinum Trading: 👑│nitro #911389167169191946]  Nitro Trades: <full message text>
```

**`=== WHAT THE BOT DID (n) ===`** — one line per decision:

```
2026-09-09 09:37:01  <sent>  OPEN GOOGL 345C 8/21 @ 3.40 x1 — Unraveller · Honey Drip … — sent in 3086 ms — waiting for GOOGL to touch $345
```

### Counts across all 21 files

| | Count |
|---|---|
| Raw message lines | **145,982** |
| Distinct messages (timestamp + room + full text) | **14,713** |
| Distinct messages ignoring the room label | **14,102** |
| Distinct room labels | 275 (242 distinct Discord channel IDs) |
| Voice-transcript lines (`[this room #538…]`) | **26,739** |
| "WHAT THE BOT DID" lines | **15,796** |

### The 8 bot-decision tags

| Tag | n | Example | Good for |
|---|---|---|---|
| `<skipped>` | 7,334 | `⚠ reader is running but its message watcher is detached — reloading that room` | Mostly plumbing. 1,655 detached-watcher, 1,080 "tab shows a different page", 347 audio-blocked, 84 "no Whop tab open". **This is why a room went quiet.** |
| `<update>` | 4,238 | `🎙 auto-listening to (2928) Discord | #🔔︱shoofs-trade-alerts` | Voice listening start/stop, room heartbeats. |
| `<ignored>` | 2,461 | `entries only — the ratchet owns the exit; Midas (Admin)'s exit on MARA noted, not traded` | **The full EXIT-IGNORED record** (trades.log has only 2). Also 1,220 "that's a REPLY quoting an older message". |
| `<sent>` | 963 | see above | **Only 345 are orders** (197 distinct). The other 618 are `ROOMS` / `ROOM HOURS` tab management. Filter on the text starting with `OPEN` or `(Swing) OPEN`. |
| `<failed>` | 296 | `OPEN RKLB 75C 10/16 @ 3.10 x5 — cranmer00 · ZTRADEZ … — the bridge refused it: HTTP 502 swing trades are paused` | Alert + room + caller + their price + the exact refusal. |
| `<voice>` | 206 | `🎙 (2788) Discord | #☀️｜daytrades-scalps | : I'm already even gonna try to` | |
| `<stopped>` | 171 | `META · 👑KingBeeAri🐝 — bid hit 3.80, at or under your 3.80 stop. Selling 1.` | Stop-outs **with the caller attached** — trades.log's `STOPPED` has no caller. |
| `<fired>` | 127 | `META · 👑KingBeeAri🐝 — filled 1.0 at 4.11 · META @ 654.77 — cost $411` | Fills **with caller, room and the underlying price at fill**. |

### DS Logs traps

- **THE EXPORTS ARE CUMULATIVE.** Each night's file re-exports the whole
  backlog the extension still holds, so the same message appears in many files.
  **145,982 raw lines dedupe to 14,713 distinct messages** — an 90% duplication
  rate. One message repeats up to **571 times**. Always dedupe on
  `(timestamp, room, text)` before counting anything.
- `signal-room-chat Sep-10-2026 (discord).txt` and
  `signal-room-chat Sep-11-2026 (discord).txt` are **byte-identical** (6,541,137
  bytes each). Counting both double-counts a day.
- **`[this room …]` is a placeholder, not a room.** 26,739 lines. 26,475 carry a
  `#538…` id and are **Deepgram voice transcripts** of a Discord voice channel —
  the true channel name is inside the text (`🎙 (2579) Discord | #☀️｜daytrades-scalps | : Morning, guys.`).
  264 more are bare `this room` and are shadow duplicates of a named row with
  the same timestamp.
- **Six Discord channel IDs appear under two names**, because the name was
  learned later: `1095502893559316482` = swing-trades / vero-swings ·
  `1326233105454993439` = daily-futures-levels / daily-key-levels ·
  `1395159239164432515`, `1499190814482632825`, `1288291150083653652`
  (BOKA "No Access" / real name) · `1334236429655740457` (ZTRADEZ "No Access" /
  all-trades-mashup). **Join on the channel ID, never on the label.**
- **Whop rooms appear under two URL forms for the same room**:
  `Day Trades #whop:/joined/firststeptrading/day-trades-cvgzKYDmcUEDGh/app`
  and `Day Trades #whop:/firststeptrading/exp_cvgzKYDmcUEDGh/app`. The suffix
  after the last `-`/`exp_` is the stable id. Whop lines: 8,758 raw → **1,920
  distinct**, one post re-read up to **410 times** by the scraper.
- The message text has Discord chrome baked in: the author name repeats, the
  server tag, the timestamp in three formats, reaction counts, and trailing
  `Add Reaction`. Strip before parsing.
- Message timestamps go back to **2019-06** — those are pinned rules and welcome
  posts the reader scrolled past, not alerts. Real volume starts 2025-08.
- Non-chat files live in this folder too: `Webull_Orders_Records_Options.csv`
  (a manual broker export), `roster.html`, three PDFs (statements/notices), and
  `recovery-codes.txt`. **`recovery-codes.txt` is a secret — never read it out,
  never paste it, never commit it.**

---

# 3. The master CSVs — the reconciled record

## master_broker.csv — the broker's own truth
**Question:** what orders did Webull actually accept, and what filled?

`date, placed_time, filled_time, occ, symbol, side, status, filled, total_qty, price, avg_price, tif, from_file`

**1,668 rows · 2026-06-12 → 2026-09-10 (51 trading days) · rebuilt from broker exports.**
1,444 FILLED / 224 CANCELLED · 759 BUY / 909 SELL · no blank OCC · no exact duplicate rows.

- **Traps:** it is assembled from overlapping exports — 923 rows came from one
  `2026-history` pull, 551 from an `2026-08-full` pull, the rest from daily
  `Webull_Orders_<date>_auto.csv` files. **38 rows share the same
  occ + placed_time + side + qty** — some are genuine repeats, some may be
  double-absorbed. `price` is blank on market-ish rows; use `avg_price`.
- It covers **the whole account**, bot and hand trades alike. It cannot tell you
  which room a trade came from.
- `Webull_Orders_auto.csv` in the repo root (111 rows) is the **not-yet-absorbed**
  daily export. Older ones are in `archive/broker-exports/` (10 files).

## master_ledger.csv — one row per trade, reconciled
**Question:** what did we hold, what did it cost, what did it make?

54 columns: `date, opened, closed, opened_ts, closed_ts, t, room, caller, key,
symbol, side, direction, strike, expiry, dte, occ, kind, qty, avg_in, fill,
entries, exits, exit_avg, pl, pl_pct, max_runup_pct, max_drawdown_pct, hi_pct,
lo_pct, state, exit_by, all_out, account, manual, swing, their_avg, their_stop,
their_target, their_units, stop_at_exit, greeks_in, greeks_out,
broker_confirmed, export_confirmed, store_pl, source, in_table, in_wallet,
opened_f` (+ trailing fields).

**978 rows · 2026-06-12 → 2026-09-10 (52 days) · REBUILT by `build_ledger.py`, not appended.**

- **The biggest trap in the repo: 755 of the 978 rows are `manual=True`** —
  G's own hand trades on the same account, not the bot's. Only **182** are
  `manual=False`. **Only 177 rows have a room at all.** Any "which room makes
  money" answer that does not filter `manual=False` is wrong.
- `source`: 702 `webull-export-only` · 226 `days-json` · 41 `trades.log-only` ·
  9 `broker-FIFO-rebuild`. Only the `days-json` rows carry room/caller.
- `broker_confirmed` is True on **140 of 978**. Everything else is inferred.
- Mostly-empty columns: `t` (943/978), `dte` (976/978 zero), `max_runup_pct`
  and `max_drawdown_pct` (~922/978), `hi_pct`/`lo_pct`, `their_stop` (953 blank),
  `their_target` (**977 of 978 blank — effectively unusable**),
  `stop_at_exit` (959), `greeks_in`/`greeks_out` (~962), `raw` (881).
- 2 exact duplicate rows.
- `state`: 807 closed · 97 filled · 32 nofill · 29 stopped · 13 failed.
- Read it through `ledger.py`, not by hand.

## master_alerts.csv — every alert and what happened to it
**Question:** which alerts did we see, and why did each one trade or not?

36 columns: `date, time, room, caller, symbol, side, strike, expiry, dte,
their_price, qty, outcome, reason, detail, our_fill, slip_abs, slip_pct,
posted_at, seen_at, sent_at, filled_at, read_ms, decide_ms, fill_ms, total_ms,
bid, ask, spread_pct, delta, iv, live, coid, ledger_key, in_ledger, source, raw`

**331 rows · 2026-08-01 → 2026-09-11 · 23 rooms · REBUILT, not appended.**

`outcome`: 136 BUYING POWER too small · 63 OTHER refusal · 51 PULLBACK never hit ·
42 filled · 15 FUTURES prop refused · 10 TEST room · 10 SWINGS paused ·
3 THIN / no open interest · 1 NO buying connection.
`source`: 289 `trades.log` · 42 `telemetry`. `in_ledger` is True on only 18.

- **Trap — 60 of the 331 rows are not alerts.** They are startup banners
  (30), Topstep/ProjectX prop status (15), swing-switch settings (10) and
  duplicate-guard notices (5). They are itemised in
  `master_alerts_noise_to_purge.csv` **and they are still present in
  master_alerts.csv** — the purge has not been applied. **Real alert count: 271.**
- **Trap — `delta` and `iv` are zero on all 331 rows.** Not "mostly": all of them.
  So is `dte`. Do not build a greeks study on this file.
- Also near-empty: `slip_abs`/`slip_pct` (309/331), `posted_at`, `seen_at`,
  `read_ms`, `decide_ms`, `total_ms` (313/331), `bid`/`ask`/`spread_pct`
  (299/331), `live` (309/331), `coid` (313/331).
- `raw` holds the source line, so it is the fastest way to cross-check a row
  against `trades.log`.

## master_postmortems.csv — one verdict per exited trade
28 columns from `date, occ, symbol, who, room, fill, exit, pl, pl_pct, held_s`
through `mae_pct, mfe_pct, after_30s, after_1m, after_5m, after_10m, after_low,
after_high, survive_pct, exit_trigger, arm_after_s, faults, verdict, lesson, file`.

**9 rows · 2026-09-09 → 2026-09-10.** The long-form versions are in
`postmortems/*.md` — **11 files, so two post-mortems have no CSV row.**
Auto-written after every exit; only started 9/9, so it covers almost nothing.
