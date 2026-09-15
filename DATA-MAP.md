# DATA-MAP.md — what is INSIDE every data file

`INDEX.md` says what each file **is**. This file says what is **in** it: the
columns, the line types, the counts, the date range, and the traps. Read it
before you grep, and before you conclude that something is not recorded.

Every number below was counted on **2026-09-11, 02:12 ET** (§9.1 and §14 on 2026-09-15). Counts in LIVE
files move; the shape does not.

---

## The 60-second version

| I need… | Open |
|---|---|
| What a caller actually posted | `DS Logs/signal-room-chat *.txt` (raw messages) + `trades.log` `AI READ` lines |
| What the bot decided and why | `DS Logs/*.txt` "WHAT THE BOT DID" block (`<sent>` `<skipped>` `<ignored>` `<failed>`) |
| The contract the bot resolved | `trades.log` `ORDER IN` lines (181, fully resolved, dated) |
| What actually filled | `master_broker.csv` (the broker's own record) |
| What a contract cost minute by minute | `databento_tape.csv` (49 days, 510 contracts), then `option_tape.csv` |
| What is true right now | Webull itself — `WHAT DO I HOLD.bat`. Never a log. |

**LIVE files change under you.** The bridge is running. These are being written
right now: `trades.log`, `bridge.log`, `deadman.log`, `webull_api.log`,
`telemetry.csv`, `shadow_ratchet.csv`, `state.json`, `days/<today>.json`,
and — during market hours — `option_tape.csv`,
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
| `FLATTEN` | 17 | `FLATTEN  FCX FAILED -> HTTP 417 …` | The popup's ✕ — G closing a position by hand. There is no automatic flatten (9/15). |
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

**ONE FILE PER WEEK PER LANE (9/15).** The name is the Monday..Sunday week of
the capture day, month abbreviated, no zero padding:

```
signal-room-chat week-of-Sep-14-to-Sep-20-2026 (discord).txt
signal-room-chat week-of-Sep-14-to-Sep-20-2026 (whop).txt
```

A week that straddles New Year carries both years — `week-of-Dec-29-2025-to-Jan-4-2026`.
Day boundary is Eastern. Inside the file each capture day is its own block
under its own header, in date order:

```
===== Mon Sep 14 2026 =====
```

**DELTA, NOT A RE-EXPORT.** The extension's export is cumulative — every pass
re-writes the whole retained backlog — so a day's block holds **only the lines
the earlier days of that same file do not already hold**. A re-export of the
same day REPLACES that day's block; a second header for one day can never
stack. Identity is the `message_id` when the capture carried one (the body
alongside it, so an edited message is never dropped), otherwise the whole line
— which already spells out timestamp, room and text. `ds_logs.py` owns all of
it; `bridge.py::_export_log` calls `ds_logs.merge_day` on write and
`extension/background.js` sends the day's delta with `day` and `lane`.

**A line lives in the week that first captured it.** `merge_day(..., held=)`
takes the earlier week files of the lane, so a Monday export never re-holds
last week's backlog (the bridge passes the previous week; the 9/15 merge
passed every earlier week).

**Every daily is merged (9/15).** The seven lane-tagged dailies (Sep 10/11/13/14
discord, Sep 11/13/14 whop, 33.0 MB) are in
`archive/signal-room-chat-dailies-pre-weekly-2026-09-15.zip` (3.0 MB); the 19
untagged dailies `signal-room-chat Aug-18-2026.txt` .. `Sep-10-2026.txt`
(30.1 MB, CRLF, Aug-18..Sep-9 = discord, Sep-10 = the **whop** lane's pre-tag
export — its rooms are all `#whop:` URLs) are in
`archive/signal-room-chat-dailies-legacy-untagged-2026-09-15.zip` (3.4 MB).
Both merges were asserted first: the set of distinct message lines and of
parser-gate keys is identical before and after (15,196 lines / 11,790 keys for
the second one). 40.6 MB in 25 files became 12.1 MB in 7 weekly files. Only
`signal-room-chat browser-history-*.txt` (a one-off grab) is not a week file.

**Where days come from now:** the `===== Mon Sep 14 2026 =====` headers, not
the file name. `ds_logs.days_covered(path)`, `ds_logs.all_days(root)` and
`ds_logs.files_for_day(root, day)` are the one place that is decided;
`replay_check.exports_for_day` and `audit_history` go through them (a
lane-tagged daily, should one ever appear again, is resolved by its name).

Each day block has the same blocks the daily file had:

**`=== CURRENT STATE ===`** — a photo of the machine at export time: version,
bridge/Webull status, buying power, the bracket settings, and **the full LIVE /
OFF / SHADOW room list for that day**. Kept verbatim, never deduped. This is
the only record of which rooms were on which day.

**`=== RAW MESSAGES THE READER SAW (n) ===`** — one line per message. `n` is
the count in THAT DAY'S BLOCK, not the running total:

```
2026-09-08 15:23:49  [Platinum Trading: 👑│nitro #911389167169191946 message_id=1414...]  Nitro Trades: <full message text>
```

**`=== LIVE PARSER INPUTS (n) ===`** — the same messages as the parser actually
received them (quotes and embeds resolved). A second VIEW of a RAW message, not
a duplicate of it: the two are deduped separately and never suppress each other.

**`=== WHAT THE BOT DID (n) ===`** — one line per decision:

```
2026-09-09 09:37:01  <sent>  OPEN GOOGL 345C 8/21 @ 3.40 x1 — Unraveller · Honey Drip … — sent in 3086 ms — waiting for GOOGL to touch $345
```

### Counts across the 7 weekly files (12.1 MB, 9/15 after the merge)

| | Count |
|---|---|
| Capture days covered | **23** (2026-08-18 → 2026-09-15) |
| RAW MESSAGES lines | **34,996** (4,313 are multi-line continuations) |
| Distinct messages (timestamp + room + full text) | **17,153** |
| Distinct room labels | 252 |
| Raw lines carrying a real `message_id` | **1,836** (everything else is `legacy-unknown`) |
| Voice-transcript lines (`[this room …]`) | **6,956** |
| LIVE PARSER INPUTS lines | **1,986** |
| "WHAT THE BOT DID" lines | **10,316** |

### The 8 bot-decision tags

| Tag | n | Example | Good for |
|---|---|---|---|
| `<skipped>` | 7,642 | `⚠ reader is running but its message watcher is detached — reloading that room` | Mostly plumbing. **This is why a room went quiet.** |
| `<update>` | 4,131 | `🎙 auto-listening to (2928) Discord / #🔔︱shoofs-trade-alerts` | Voice listening start/stop, room heartbeats. |
| `<ignored>` | 3,003 | `entries only — the ratchet owns the exit; Midas (Admin)'s exit on MARA noted, not traded` | **The full EXIT-IGNORED record** (trades.log has only 2). Also the "that's a REPLY quoting an older message" refusals. |
| `<sent>` | 1,062 | see above | Only a minority are orders — the rest are `ROOMS` / `ROOM HOURS` tab management. Filter on the text starting with `OPEN` or `(Swing) OPEN`. |
| `<failed>` | 373 | `OPEN RKLB 75C 10/16 @ 3.10 x5 — cranmer00 · ZTRADEZ … — the bridge refused it: HTTP 502 swing trades are paused` | Alert + room + caller + their price + the exact refusal. |
| `<stopped>` | 209 | `META · 👑KingBeeAri🐝 — bid hit 3.80, at or under your 3.80 stop. Selling 1.` | Stop-outs **with the caller attached** — trades.log's `STOPPED` has no caller. |
| `<voice>` | 206 | `🎙 (2788) Discord / #☀️｜daytrades-scalps : I'm already even gonna try to` | |
| `<fired>` | 149 | `META · 👑KingBeeAri🐝 — filled 1.0 at 4.11 · META @ 654.77 — cost $411` | Fills **with caller, room and the underlying price at fill**. |

### DS Logs traps

- **THE EXPORT IS STILL CUMULATIVE — the FILES no longer are.** Each pass hands
  the bridge the whole retained backlog; the week files keep each line once,
  across weeks. Still dedupe on `(timestamp, room, text)` before counting: a
  voice line can repeat under `this room` and under its named room.
- **THE JS CORPUS READERS MISS EVERY `message_id` LINE.** `parser_gate.js`,
  `reader_corpus.js` and `local-reader-measure/compare_keys.js` all match
  `\[(.+?)#(\d+)\]`, which cannot match the v3.8.32 tag
  `[Room #123 message_id=456]`. The 9/14 capture contributes **zero** rows to
  the gate corpus for that reason (11,385 messages gated, all from older
  lines). Python's `RE_MSG` in `replay_check.py` / `audit_history.py` /
  `scoreboard.py` already allows the tag. **This is a live gap, not a weekly-
  file effect — it predates 9/15 and is not fixed here**, because the 9/15
  restructure was proved by the gate count staying identical.
- **`[this room …]` is a placeholder, not a room.** 27,807 lines. Most carry a
  `#538…` id and are **Deepgram voice transcripts** of a Discord voice channel
  — the true channel name is inside the text (`🎙 (2579) Discord | #☀️｜daytrades-scalps | : Morning, guys.`).
  The rest are bare `this room` and are shadow duplicates of a named row with
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
  after the last `-`/`exp_` is the stable id. One post is re-read up to **410
  times** by the scraper.
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

## master_ledger.csv — one row per reconciled position
**Question:** what did we hold, what did it cost, what did it make?

57 columns as of 2026-09-13; full order and source fields are defined by
`build_ledger.COLUMNS`. `coid` is the client order ID shared with alert
telemetry when available, `entry_order_id` is the broker entry order ID in
new day snapshots, and `entry_qty` is the sum of retained entry legs. Older
rows leave IDs blank rather than inventing them. `qty` in old closed day
rows may be zero remaining; a unique exact OCC/entry size/price broker
round-trip within five minutes restores original size and broker exit/P&L.
`store_pl` preserves the book's old value for comparison.

The file is rebuilt, not appended. The 2026-09-13 corrected rebuild had
931 rows: 654 Webull-export-only, 227 days-json, 41 trades.log-only, and
9 broker-FIFO-rebuild. Forty-eight zero-remaining-quantity day rows were
reconciled to broker trips instead of appearing twice. The running bridge
must load the new code before future rebuilds use this rule.

`manual` means a **manual exit** in a day row; it does not establish that
G entered the trade. Conversely a Webull-export-only row has no book
provenance and cannot automatically be called a manual entry. For caller
performance require actual entry source, exact contract, and broker fill;
room/name fields alone are candidate evidence. `broker_confirmed` is a
trades.log fill; `export_confirmed` means a Webull order export matched.

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

---

# 4. The price tapes — what a contract actually cost

Webull's API returns **no historical option prices**. These files are the only
record we will ever have of what a contract was worth at a given minute.

| File | Columns | Rows | Contracts | Range | State |
|---|---|---|---|---|---|
| `databento_tape.csv` | `ts,occ,bid,ask` | 1,022,106 | **510** | 2026-06-12 → 2026-09-08, 49 trading days, 56 underlyings | backfilled, despiked in place |
| `option_tape.csv` | `ts,occ,bid,ask` | 161,482 | **31** | 2026-09-02 → 2026-09-10, **6 days only** | LIVE in market hours |
| `missed_tape.csv` | `ts,occ,bid,ask` | 46,394 | **3** | 2026-08-05, 08-11, 09-03 | frozen |
| `quote_shadow.csv` | `ts,symbol,bid,ask,mid,bid_size,ask_size` | 29,525 | 27 | 2026-09-08 → 2026-09-10 | LIVE (DXLink shadow) |
| `alert_tape.csv` | `ts,occ,bid,ask,und` | **2,333** | 3 | 2026-09-11 10:01 → 13:13 | LIVE all-alert snapshots |
| `alert_meta.csv` | `ts,stage,coid,date,time,room,caller,symbol,side,strike,expiry,occ,their_price,alert_at,seen_at,bid,ask,und,delta,iv` | **8** | 3 | 2026-09-11 10:01 → 12:41 | LIVE alert/quote metadata |
| `greeks_tape.csv` | `ts,symbol,price,iv,delta,gamma,theta,vega,rho` | 842 | — | 2026-09-04 → 2026-09-10 | LIVE |

### Tape traps

- **`option_tape.csv` is far smaller than it looks.** 161k rows, but only
  **31 distinct contracts across 6 days** — the fast bus tapes only contracts we
  actually hold, at ~1/sec, so two long holds (IREN 54k rows, XLF 52k rows)
  are 66% of the file. It is **not** a market tape.
- **`databento_tape.csv` is the real historical source** — 510 contracts,
  49 days. It is ONE file (9/15): `databento_backfill.py` / `option_tape_pull.py`
  append raw ticks, then `clean_tape.py` rewrites it in place — timestamps to
  the millisecond, rows grouped by contract, lone bid/ask spikes replaced by the
  local median (287 of 967,164 `(ts, occ)` keys). The `_clean` twin held the same
  ticks and is gone. It does **not** dedupe: ~54,940 rows repeat a `(ts, occ)`
  pair. Dedupe yourself.
- **`quote_shadow.csv` uses a different symbol format** — `.MSTR260911P132`
  (DXLink/tastytrade), not OCC `MSTR260911P00132000`. It will not join to the
  other tapes without conversion.
- `alert_tape.csv` / `alert_meta.csv` are the slow "what did the contracts we
  *didn't* buy cost" lane. They started fresh 2026-09-11 and now retain live
  snapshots/metadata; `tape.py` exposes them as source `alert`. Anything they
  held before the recreation is gone unless it is in `backups/` or `archive/`.
- Timestamps are **Unix epoch seconds, Eastern-facing**. Convert with a fixed
  −04:00 offset to match `trades.log`.
- `greeks_tape.csv` is tastytrade DXLink data, options **and** stock symbols
  mixed, and only exists from 9/4.

---

# 5. Per-trade and per-day records

## days/*.json — the book, one file per trading day
37 `YYYY-MM-DD.json`, no `.bak` (9/15: only `state.json` keeps a backup — nothing ever read a day file's). 2026-08-05 → today; today's file is LIVE.

Shape: `{"date", "mode", "table": [...], "wallet": {...}}`.
`mode` is `dryrun` or live. `wallet` = `cash, reserved, open_cost, open_worth,
realised, wins, losses, trades, unlimited, peak, day`.

Each `table` row has 31 fields: `key, who, symbol, side, strike, expiry, state,
kind, direction, their_stop, their_target, qty, avg, adds, entries, exits, pl,
their_avg, their_units, live, room, opened, closed, all_out, manual, raw,
pl_pct, exit_by, swing, hi_pct, lo_pct`.

**274 table rows across all days, covering 27 rooms.** INDEX.md says "not for
analysis" — that is about *state*, but the rows are still the **only place**
holding some fields per trade:
- **119 rows carry `raw`** — the caller's original message.
- **38 rows carry `their_stop`** (vs 25 in master_ledger).
- 1 row carries `their_target`. That field is effectively empty everywhere.

## postmortems/*.md — one verdict per exited trade
11 files, `YYYY-MM-DD_<OCC>.md` (a second trade in the same contract gets `-2`,
`-3`). Each holds: caller, room, our fill, round-number wait in seconds, exit,
P&L, hold time, MAE/MFE, and **the bid at +30s / +1m / +5m / +10m after we left,
plus the high and low in that window**. That "what happened after we sold" data
exists nowhere else. Started 2026-09-09.

## journal.csv and journal-*.xlsx
`journal.csv` — 274 rows, 2026-08-05 → 2026-09-10, 28 rooms, UTF-8 **BOM**.
Columns: `date, room, caller, symbol, side, direction, contract, qty, avg_in,
exits, P&L, P&L %, max run-up %, max drawdown %, opened, closed, status,
exit_by, account, signal`. Rebuilt, not appended. `exit_by` is blank on 148 of
274 rows.

`journal-2026-09-*.xlsx` (7 files, 9/1–9/10, sheets **Trades** + **By Trader**),
`journal-full-ALL.xlsx` (**All trades** + **Summary**),
`trader-scoreboard.xlsx` (**Scoreboard** + **Every trade**).
Older daily journals are in `archive/journals/` (9 files, 8/19–8/31).
The `.~lock.*.xlsx#` files mean a workbook is open in LibreOffice — ignore them.

---

# 6. Telemetry and diagnostics

| File | Answers | Rows / range | Notes |
|---|---|---|---|
| `telemetry.csv` | how many milliseconds from post → read → sent → filled | 3,654 rows, 2026-09-07 17:26 → 2026-09-11 02:05, **LIVE** | 39 columns. **Every greek column is zero** (`underlying, delta, gamma, theta, iv, stop_room_pts, stop_room_pct, theta_per_min, theta_break_min, gamma_read`), and `coid`/`room`/`posted_at`/`seen_at`/`read_ms`/`decide_ms`/`total_ms` are empty on 3,636 of 3,654. The `fill_ms`/`sent_at`/`their_price`/`our_fill`/`slip` columns are the usable part. |
| `shadow_ratchet.csv` | would a different ratchet have done better on the same fill | 2,047 rows, 2026-09-05 → 2026-09-11, **LIVE** | **NO HEADER ROW.** Columns are `t, entry_hhmm, held_min, occ, symbol, fill, real_pct, shadow_pct, shadow_exited, legs, peak_pct, dte, delta_in, iv_in`. **1,184 rows are a test contract (`SPY   250801C00745000`, note the padding) written by the test suite, and 837 have a blank OCC. Only ~26 rows are real trades.** |
| `health.csv` | are the Webull endpoints responding | 40 rows, 9/7 → 9/10 | `ts,market,endpoint,ok,trials,p50_ms,p90_ms,max_ms,err` |
| `rn_ledger.csv` | did the round-number pullback help | 33 rows, 9/9 → 9/10 | `caller_price` is empty on all 33. |
| `ratchet_backtest_results.json` | per-trade ratchet replay | 867 entries from 2026-06-12 | `day, occ, who, room, state, entry, realized_pct, stopped_out, peak_gain_pct`. `who` and `room` are usually blank. |
| `ratchet_sweep_results.csv` | 50 born-stop / arm combinations | 50 rows | `born_stop_pct, arm_to_be_pct, total_pl_dollars, avg_pl_dollars, win_rate_pct, resolved_of` |
| `ratchet_fine_results.csv` | 294 fine-grained combinations | 294 rows | `born, arm, step, total, win_pct, n` |
| `reproductions.json` / `js-reproductions.json` | which known bugs still reproduce | 20 / 2 entries, **LIVE** | `{name, reproduced, detail}` |
| `liquidity_cache.json` | today's open-interest / spread screen | `{day, map}`, 9/8 | One day only; stale. |
| `databento_backfill_state.json` | which contract-days are already downloaded | 111 `[occ, date]` pairs | The backfill's to-do list. |
| `px_day.json` | Topstep daily P&L points | 6 keys | Prop only. |
| `state.json` / `state.json.bak` | today's date + a small state blob | 2 keys, **LIVE** | |

---

# 7. Logs

| File | Lines | Range | State |
|---|---|---|---|
| `bridge.log` | 35,507 | from 2026-09-10 09:32 | **LIVE** — console echo of everything, far noisier than `trades.log` |
| `bridge.log.1` | 343,698 | 2026-08-27 → 2026-09-10 | frozen (27 MB) |
| `reads.log` | 593 | 2026-09-08 → 2026-09-10 | the **reader tape** — what the ears heard and the eyes saw. Format `ts  🎙/📸 room  speaker` then the parser's reading, then what was heard, pipe-separated. 574 voice, 19 screenshot. Read it with `python3 reads.py`. |
| `deadman.log` | 141 | from 2026-09-07 | **LIVE** — thread deaths |
| `webull_api.log` (hourly rotations `webull_api.log.<date>_<hh>` go to `archive/webull-api-logs/`, 28 there) | current | rolling | **LIVE.** SDK debug. **Contains the Webull app key in plaintext (`x-app-key`). Never paste this file anywhere.** |
| `webull_data_streaming_sdk.log` | 8,797 | to 2026-09-09 | streaming SDK errors; the SDK is not installed on purpose |
| `whop-loop.log` | 13 | 2026-09-10 | Whop Chrome restarts |
| `launcher-probe.log` | 26 | from 2026-08-31 | START HERE launches |

`bridge.log` uses `HH:MM  TYPE  message` (no date on most lines, a
`[Day MM/DD/YYYY HH:MM:SS.ss] starting bridge` banner on restart) and mangles
em-dashes to `?`. For anything you can get from `trades.log`, use `trades.log`.

---

# 8. Room and symbol configuration

| File | What is inside |
|---|---|
| `extension/rooms.txt` | **THE room list.** 74 rooms, one per line: `id\|url\|label\|group\|on\|off\|lapsed`. **31 on, 38 off, 5 lapsed** right now, plus comment lines carrying the one-line reason a room is off. Data, not code — editing it does not reload the extension. |
| `extension/optionable.txt` | 6,370 symbols the bot may trade, regenerated from tastytrade 2026-09-08. A ticker missing here is why an alert was skipped. |
| `chan_names.json` | 275 `channel id → "Server: #channel"` entries. **Last-write-wins**, so a renamed channel shows only its newest name, and several read `"… : No Access"` because the name was never learned. |
| `samples.txt` | 481 lines of parser samples, fed to `parser.js` by the JS tests. |
| `corpus/` | 5 files, `<channelid>-<date>.txt`, 1,976 lines total (nitro 1,322, futures-alerts 391, equity 185, ei-alerts 41, day-trades 37), 2024-12 → 2026-08. Room-language samples for the parser gate. |
| `reference/rooms-snapshot.txt` / `project/context/rooms-snapshot.txt` | frozen copies of rooms.txt for the Claude Project. |

---

# 9. Stock and futures bars

- `bars/stock/<SYM>_<YYYY-MM-DD>_1s.csv` — **112 files, 41 symbols, 1,315,559
  rows, 2026-08-04 → 2026-09-08.** Columns `ts,o,h,l,c` (epoch seconds, cents
  accurate, Databento). This is what `pullback_levels.py` replays.
- `bars/NQ_bars.csv` — 2,961 rows, `time,open,high,low,close,volume`, ISO
  timestamps in **+0000**, from 2026-08-24. Free Webull futures bars.
- `bars/ES_1m_<start>_<end>.csv` · `bars/NQ_1m_<start>_<end>.csv` · `bars/<root>_1m_<date>.csv`
  — index futures 1-minute OHLCV, `ts_event,symbol,open,high,low,close,volume`,
  **UTC**, Databento GLBX.MDP3 continuous front month (`ES.c.0`/`NQ.c.0`). The
  range files cover 2026-08-03 → 09-12; `futures_mirror_daily.py` reads these
  first and caches any day it has to buy as a single-date file (~1¢/day).
- `archive/2026-09-09-cleanup/bars/` holds an older capture — do not mix them.

## The index mirror (9/13)

| File | Columns | What it is |
|---|---|---|
| `futures_mirror_shadow.csv` | `ts_iso, date, time_et, sym, dirn, micro, room, caller, their_price, outcome` | **Append-only, gitignored, written live by the bridge** for EVERY SPY/QQQ option entry it sees — filled, refused, pullback-armed, TEST room — whether the mirror switch is on or off. The daily replay's input, so it never waits on a master_alerts rebuild. |
| `reference/FUTURES-MIRROR-REPLAY.csv` | `status, entry, exit, why, pts, usd, mfe, mae, bars, mode, ts, sym, dirn, room, caller, src, lvl, ref` | **The cumulative record**, one market-mode row per alert (the selection-biased snap variant stays in each day report only). Seeded with the 149 market rows of the 9/13 study; appended daily, deduped on `mode+ts+sym+dirn` so a re-run cannot inflate the running total. |
| `reference/FUTURES-MIRROR-REPLAY-2026-09-13.csv` | same | Frozen — the original 8/3–9/11 study (298 rows, both modes). The seed. Do not append to it. |
| `daily-reports/FUTURES-MIRROR week-of-….md` (that day's `===== Mon Sep 14 2026 =====` block) | — | One day's trades, day total, running total since 2026-08-03, win rate, by room, by sym×direction, exits, and what the number is not. |

`balance_daily.csv` (`broker_sync.py`, appended once per trading day at 16:40) — `date, nlv, day_pl, bp, read_at`. The ONLY place the account's net liquidation, Webull day P&L and option buying power are kept; nothing else on disk records a balance, and `health.csv` stores only whether the read succeeded. `day_pl` is Webull's own figure, NET of fees; `master_broker.csv` round trips are GROSS, so the two differ by the day's fees (9/14: -333.85 net vs -321 gross across 47 filled legs). One row per day — a re-run replaces that day's row, never stacks a second.

**TZ TRAP (9/15):** `build_ledger._hms()` renders epochs in the MACHINE's local timezone, and days-json `closed` values come from stored Eastern strings instead. Rebuild from anything but an Eastern shell and `opened` jumps +4h while `closed` jumps -4h. Always `TZ=America/New_York python3 build_ledger.py` off his PC. Caught the same day it happened and restored from `backups/`.

`daily-reports/BRIEF week-of-….md`, that day's block (`daily_brief.py`, written near the end of the 16:40 audit and posted to Sniper HQ as the file `BRIEF-<date>.md`) holds NO new data — it is a rendering of master_ledger + master_broker + that day's CALLER-OUTCOMES/CALLER-VS-RATCHET/FUTURES-MIRROR + dated `trades.log` lines + `department-reports/extension-*.json` + HANDOFF's Pending block. Two things in it exist nowhere else as a judgement: the exit-reason words (born stop / ratchet / BE stop, decided from `stop_at_exit` vs `avg_in` — at or above the fill means the ratchet moved it) and the `⚠ journal ≠ broker` flag (the row says it exited and the broker record prices no exit). Never quote a number from it that the source file does not also say.

---

# 9.1 Reports, the report cache and STATUS.json (9/15)

**One file per WEEK per kind** (same naming as DS Logs, `reports.py` owns it):
`daily-reports/REPORT week-of-Sep-14-to-Sep-20-2026.md`, `BRIEF week-of-….md`,
`CALLER-OUTCOMES week-of-….md`, `CALLER-VS-RATCHET week-of-….md`,
`RATCHET-COMPARE week-of-….md`, `FUTURES-MIRROR week-of-….md`,
`daily-audits/AUDIT week-of-….txt`, plus the hand-made kinds kept the same way
(`ALERT-LEDGER`, `NINJAGO-FUTURES-RADAR`, `ALERT-HISTORY`, `PARSER-HISTORY`).
Inside: a `===== Mon Sep 14 2026 =====` block per day, **newest day first**; a
re-run for a day replaces that day's block; the line before the first header is
a preamble that is rewritten every time. `python reports.py show <kind> <day>`
prints one day; `path` names the file. The 20 dated dailies that existed on 9/15
(18 md/txt + 2 csv) were folded in and deleted — 18 day blocks, 59 csv rows.

**The one csv:** `daily-reports/CALLER-OUTCOMES.csv` — `date` first, then
`entry_time, event_time, room, caller, symbol, contract, entry, event,
reported_exit, reported_pct, profit_per_contract, calculated_pct, implied_exit,
trim_size, basis, raw`. Replace-by-date: a re-run for a day drops that day's rows
and appends the new ones (rows stay sorted by date). Readers: `daily_brief`,
`caller_ratchet_compare`, `research_ledger`, `reference/caller_profile.py` —
all through `reports.csv_rows("caller-outcomes", day)` or the `date` column.

**Untouched in daily-audits/:** `latest.json` (the last audit's summary; its
report paths now name the weekly files), `review_queue.jsonl` (append-only
attention queue, one row per distinct issue shape per day), `.last-run`,
`PARSER-HISTORY-LATEST.txt` (AUTO PUSH overwrites it every push), and the frozen
9/11 recovery inputs `raw-2026-09-11-*.json` / `recovered-2026-09-11.json`
(read by `daily_report`, `caller_outcomes`, `caller_ratchet_compare` as
`recovered-<day>.json`; a day with no such file simply has no recovered gaps).

**`reports/INDEX.json`** — the report cache's memory: `{kind: {date: {fingerprint,
inputs: {input name: signature}, output, built_at}}}`. A signature is `size:mtime`
for a whole file (code, rooms.txt), a 16-hex sha256 of that DAY's lines/rows for
trades.log, the master csvs and the epoch-stamped tapes, of the day's DS Logs
block, or of another report's day block. `python reports.py status [day]` prints
one line per kind/day — CURRENT, STALE (and which inputs moved), MISSING, MANUAL.
`reports.py build <kind|all> <day>` skips a CURRENT one (`CURRENT <path>`).
The 16:40 audit builds every kind through it, so the index is always populated;
the undated kinds (`scoreboard` → SCOREBOARD.html, `alert-audit` →
ALERT-AUDIT.html) sit under the date key `all`.

**`STATUS.json`** (repo root, < 4 KB, written LAST by the audit; `python
status_json.py [day]` rebuilds it from disk) — `date`, `balance {nlv, day_pl, bp,
as_of}` (balance_daily.csv), `bot {trades, pl, wins, losses}` (master_ledger, the
brief's bot-trade definition), `rooms {discord|whop: {on, spoke, reads}}`
(rooms.txt + that day's DS Logs block), `audit {status, silent_drops,
possible_missed, coverage_warnings, failed_checks}`, `broke` (review queue, newest
5), `pending` (HANDOFF's Pending list), `bridge {up, buying_power, health}`
(health-latest.json + a 2 s loopback probe), `verified {tests {passed, failed,
at}, parser_gate {counts {messages, entries, actions, pass}, at},
broker_reconciled {match, at}, bridge_code_live {sha, bridge_py_mtime, at}}`,
`reports` (status lines). VERIFY ONCE: a `verified` entry stands while its
inputs are unchanged — do not re-run the suite, the gate or the reconciliation
for confidence. A hand rebuild with no fresh test output keeps the recorded one.

---

# 10. The 2026-09-11 recovery run (frozen artifacts)

These were produced by the history rebuild. They are snapshots, not live.

| File | Rows | What it is |
|---|---|---|
| `recovered_alerts_tradeslog.csv` | **425** | Alerts reconstructed from `trades.log`. 21 columns incl. `tier, confidence, how_recovered, corroborating_lines, source_line_number, source_line_text`. Tiers: 119 `F-airead`, 113 `E-order`, 53 `C-linked(E-order)`, 48 `A`, 44 `C-linked(F-airead)`, 26 `B`. Confidence: 271 high / 149 medium / 5 low. 2026-08-04 → 09-10. |
| `recovered_alerts_chat.csv` | **2,681** | Alerts reconstructed from the DS Logs exports. 22 columns incl. `their_stop, their_target, msg_type, links_to, confidence, clue, source_message_verbatim`. `msg_type`: 1,018 entry · 577 trim · 504 commentary · 477 exit · 105 add. Confidence: 979 high / 843 medium / 859 low. **Only 340 of the 2,681 were already in master_alerts.csv.** |
| `unrecoverable_alerts.csv` | 44 | Alerts from trades.log that could not be resolved — 27 because no expiry could be determined, the rest because the originating call is not in the log. |
| `unrecoverable_chat_messages.csv` | 179 | Chat messages that look like alerts but are not resolvable — **170 are "ticker and a bare number only"**. |
| `master_alerts_noise_to_purge.csv` | 60 | The non-alert rows sitting in master_alerts.csv. Not yet removed. |
| `alert_rebuild_2026-09-11.csv` | 29 | A tape-replay of rebuilt alerts. `status`: 16 OK, 7 "NO TAPE that day", 6 skipped for gaps. |
| `quotes_needed_backfill.txt` | 413 OCCs | Contracts with no price record, wanted from Databento. |
| `missing_contracts_for_backfill.txt` | 84 OCCs | The shorter, prioritised version. |

**Trap:** `recovered_alerts_chat.csv` is dominated by whichever export files were
biggest — 1,007 of its 2,681 rows come from one file
(`signal-room-chat Sep-10-2026 (discord).txt`). That is export duplication, not
a busy day. Dedupe before counting rooms.

---

# 11. Folders that are not live data

- **`archive/`** — 192 files, 2.6 MB (INDEX.md's "187 MB" is stale; the rotated
  logs are gone). `archive/broker-exports/` 10 daily Webull exports (8/21–9/03),
  `archive/journals/` 9 daily journals (8/19–8/31), `archive/one-off/` 13 items
  incl. `voice-transcript-week-Aug24-28.txt` and `voice-HARD-lines-for-G.txt`,
  `archive/2026-09-09-cleanup/` 157 retired scripts and docs with a
  `MANIFEST.txt`. Also three `paper-fills-2026-09-0*.csv` — **4 rows each and
  near-identical; they are not three days of data.** 9/15 additions:
  `signal-room-chat-dailies-legacy-untagged-2026-09-15.zip` (19 dailies),
  `local-reader-measure-experiments-2026-09-15.zip` (45 files, 95.8 MB → 7.2 MB:
  the openai-trial review/release/progress snapshots, the June all-channels
  run outputs, `grabber-audit/`, `rule-fixes/`, the pilot-v1 / haiku / sonnet
  run leftovers and three 9/13 probe files) and `webull-api-logs/` (the SDK's
  hourly rotations land here directly now). Nothing in `archive/` is read by
  the running machine.
- **`local-reader-measure/`** — 230 MB, all of it read or written by code:
  `caller-identity/` (`caller_ledger.py` writes, the bridge's /callers reads
  `callers.sqlite3`, 119 MB), `openai-trial-2026-09-12/` (`budget.sqlite3` is
  the $5 allowance ledger — never delete it — plus the trial's own corpus /
  ai-context / disagreements / summary files), `all-channels-2026-06-12/corpus.jsonl`
  (the trial's SOURCE), `corpus.jsonl` + `ai-context.jsonl` + `pilot-v1-disagreements.csv`
  (`reader_measure.py`), `live.jsonl` (`shadow_reader.py` appends every observer
  read, one file, each row carries `day` — replaced `live-<day>.jsonl`, 790 rows
  merged), `context-cache.json`, `provider-key-check.json`, `compare_keys.js` +
  its `js-keys.json`.
- **`department-reports/`** — one living pair per department (9/15):
  `reader_reviews.jsonl/.md` (23), `health.jsonl/.md` (6), `daily.jsonl/.md` (2),
  `incidents.jsonl/.md` (2); the `.jsonl` row carries the digest as `md`, the
  `.md` is newest first. `departments.record()` appends; the old
  `<role>-<day>-<fingerprint>.json/.md` pairs are gone. `runs.sqlite3` is the
  reservation ledger, `health-latest.json` / `extension-<lane>.json` are live.
- **`backups/`** — 28 dated copies, last 5–14 of each master file:
  14 `master_ledger.csv`, 8 `master_broker.csv`, 5 `master_alerts.csv`,
  1 `_whop_loop.bat`. Named `<file>.bak-YYYYMMDD-HHMMSS`. **Use these to see
  what a rebuilt master file looked like before the rebuild.**
- **Handoff history (consolidated 9/12)** — retired handoff documents are in
  `archive/retired-handoff-documents-2026-09-12.zip`, with source paths and SHA-256
  hashes. Historical evidence only. The bridge no longer generates daily
  handoffs; use `daily-reports/` and broker-reconciled master files for performance.
- **`reference/`** — 8 docs, the shelf. `OPTIONS-BROKER-REFERENCE.md` (59 KB)
  is the broker-fact file to read before any broker test.
- **`project/context/`** — Claude reference uploads, potentially stale. Handoff
  copies were removed 9/12; only root `HANDOFF.md` defines current operating
  state. `project/PROJECT-INSTRUCTIONS.md` points to the live files.
- **HTML artifacts** — `SCOREBOARD.html` (9/10, per-room scoreboard),
  `ALERT-AUDIT.html` (9/7, what we missed ever), `contracts.html` (9/9),
  `MAP.html` (9/2, how the machine works). Rebuild them rather than trusting
  the date on them.

---

# 12. If you are trying to answer X, read Y

| Question | Read | How |
|---|---|---|
| **Which rooms make money?** | `master_ledger.csv` | Use source-linked entry attribution and broker-confirmed fills. `manual` is a manual exit flag, not an entry-owner filter; export-only records need provenance before assigning a caller. Cross-check with the research SQL and SCOREBOARD.html. |
| **What did a contract cost at a given minute?** | `databento_tape.csv` first (510 contracts, 6/12–9/8), then `option_tape.csv` (31 contracts, 9/2–9/10), then `missed_tape.csv` (3 contracts). | Dedupe `(ts, occ)`. If the contract is in none of them, the price does not exist anywhere — see Known data gaps. |
| **What did a caller actually post?** | `DS Logs/signal-room-chat *.txt`, RAW MESSAGES block | Full text, untruncated. Dedupe on `(ts, room, text)`. If the room is a `#538…` voice room, the text is a speech transcript. |
| **…and if the exports don't cover that day?** | `trades.log` `AI READ` lines | 636 of them carry the message, truncated to 50 chars, plus the bot's full reading after the `->`. |
| **What did the bot do with an alert, and why?** | `DS Logs/*.txt` WHAT THE BOT DID block | `<sent>` = order out, `<failed>` = bridge refused it (reason included), `<skipped>` = the reader never got to it, `<ignored>` = read and deliberately not traded. |
| **…cross-checked against the bridge?** | `trades.log` | `WORKING` → `ORDER IN` → `FILLED` is the happy path. `REFUSED` / `ERROR` / `BLOCKED` / `NO-OTM` / `SWING-OFF` / `NOFILL` are the unhappy ones, each with its reason in the same line. |
| **What filled, and at what price?** | `master_broker.csv` (`status == FILLED`, use `avg_price`) | The broker's own record. `trades.log` `FILLED` lines agree but cover the bot only. |
| **What is open right now?** | **Webull.** Run `WHAT DO I HOLD.bat`. | Never a log file. Logs are past tense; the account is the present. `days/<today>.json` is the bot's belief, not the truth. |
| **What were the caller's own stop and target?** | `days/*.json` `table[].their_stop` (38 rows), then `master_ledger.csv` `their_stop` (25 rows), then `recovered_alerts_chat.csv` `their_stop`/`their_target`. | `their_target` is blank on 977 of 978 ledger rows. Treat targets as not recorded. |
| **Why was an alert refused?** | `master_alerts.csv` `outcome` + `reason` + `detail` | 136 buying power · 63 other refusal · 51 pullback never hit · 15 futures prop · 10 test room · 10 swings paused · 3 thin. Then `trades.log` `REFUSED`/`ERROR` for the exact broker text. |
| **Why did a room go quiet?** | `DS Logs/*.txt` `<skipped>` lines | 1,655 detached watcher, 1,080 tab navigated away, 347 audio blocked, 84 no Whop tab. Then `ALERT-AUDIT.html` / `audit_history.py`. |
| **Which rooms were switched on, on a given day?** | `DS Logs/signal-room-chat week-of-… (lane).txt`, that day's `===== Mon Sep 14 2026 =====` block, CURRENT STATE | The LIVE / OFF / SHADOW lists are stamped there, one per capture day. `extension/rooms.txt` only shows today. |
| **What happened after we sold?** | `postmortems/*.md` | Bid at +30s / +1m / +5m / +10m, plus high and low in that window. 11 trades only, 9/9 onward. |
| **How fast did we read and fire?** | `telemetry.csv` (`sent_at`, `fill_ms`, `slip_pct`) and the `sent in NNNN ms` text on `<sent>` lines. | Ignore every greek column in telemetry — all zero. |
| **Was the stop where I think it was?** | `trades.log` `STOP-SET` (362 lines) | Each line has the resting price and whether it was born with the order. |
| **Did this trade exist at all?** | `master_broker.csv` | If Webull has no row, it never happened, whatever the logs say. |
| **How did we do today / what broke / is it verified?** | `STATUS.json`, then ASK-MAP.md | Never a log first. |
| **Give me the report for a day** | `python reports.py status <day>` then `reports.py show <kind> <day>` | CURRENT = hand it over as is; STALE = `reports.py build`. |

---

# 13. Known data gaps — do not go hunting for these

1. **Webull has no historical option prices via API.** There is no endpoint to
   ask "what was this contract worth on August 12". Our own tapes are the whole
   record, and the Databento backfill is the only way to add to it.
2. **Contracts with no tape have no price, ever.** `option_tape.csv` covers 31
   contracts over 6 days; `databento_tape.csv` covers 510 over 49 days;
   `missed_tape.csv` covers 3. Everything else alerted before or outside those
   is priceless in the literal sense. `quotes_needed_backfill.txt` lists 413
   such OCCs; `missing_contracts_for_backfill.txt` the 84 that matter most.
   They can only be recovered by paying Databento for them.
3. **`alert_tape.csv` and `alert_meta.csv` started from zero on 2026-09-11.**
   They now record the "what did the contracts we didn't buy cost" lane, but
   cannot recreate calls from before that start time.
4. **Voice rooms are speech-to-text and mostly unparseable by design.** The
   26,475 `[this room #538…]` lines are Deepgram transcripts — "Get an
   opportunity to add. Let's see." No ticker, no strike, no expiry. They are
   evidence of what was said, not a source of alerts.
5. **ZTRADEZ top-flow posts a ticker and a price with no contract.** 28 of its
   51 recovered entries have no expiry at all. Same for `guru-futures` (33) and
   `mr-top-hat` (11).
6. **Platinum Trading `👑│nitro` never writes an expiry.** All **149** of its
   recovered entries lack one. There is no rule that recovers it — a nitro
   alert without an expiry is unresolvable, not merely unresolved.
7. **476 of the 1,018 recovered chat entries have no resolvable OCC** for the
   same family of reasons ("NEXT WEEK", no expiry, two tickers in one message).
   `unrecoverable_alerts.csv` (44) and `unrecoverable_chat_messages.csv` (179)
   are the itemised list. 170 of the 179 are "ticker and a bare number only".
8. **`delta` and `iv` do not exist in `master_alerts.csv`** (0 on all 331 rows)
   or in `telemetry.csv` (0 on all 3,654). The only real greeks are the 842 rows
   of `greeks_tape.csv`, from 2026-09-04 onward, and the `greeks_in`/`greeks_out`
   fields on 13–17 ledger rows.
9. **`their_target` is not recorded.** 977 of 978 ledger rows blank, 1 of 274
   day-file rows populated. Caller targets have to be read out of the raw
   message text.
10. **Room attribution is missing on most fills.** Only 177 of 978 ledger rows
    and 0 `ORDER IN` lines carry a room. Anything older than the `days-json`
    era (pre 2026-08-05) has no room at all.
11. **There are no DS Logs exports before 2026-08-18.** Messages from earlier
    dates do appear inside those files (back to 2019), but they are pinned posts
    and rules the reader scrolled past, not a real backfill of alerts.
12. **No weekend or holiday files.** Gaps at 8/22, 8/29–8/30, 9/5, 9/7 are
    weekends, not missing data.
13. **`git log` hangs in this repo.** Do not use git history as a data source,
    and never run a git write command — AUTO PUSH sweeps every 45 s on its own.

---

---

# 14. The data families — one central file per family (moved from HANDOFF.md 9/15)

THE APP READS ONLY THESE. The rule lines stay in HANDOFF.md (DATA section); the
mechanics are here, verbatim.

- BROKER RECORD → master_broker.csv (one row per Webull order leg, every
  day). `broker_sync.py` — FIRST step of the 16:40 audit, one read-only client,
  no loop — pulls the order history (paged on `last_client_order_id` until a
  short page) into ONE fixed file, Webull_Orders_auto.csv, OVERWRITING it every
  run (G, 9/10: "have one that overwrites" — no deletes, ever), and records one
  balance row per day in `balance_daily.csv` (date, nlv, day_pl, bp, read_at) —
  the brief's only balance source (automated 9/15 — nothing pulled it
  before). build_ledger's absorb_exports() (runs inside every ledger refresh) folds
  it into master_broker.csv and leaves it in place. Never write dated
  Webull_Orders_<date> files — the folder holds the master plus that one
  scratch file (G, 9/9: never dated piles).
  Merge is REPLACE-DON'T-STACK per order (placed-time+contract+side+size+
  limit): a later pull replaces a WORKING snapshot, never duplicates it.
  PRICE-BLIND TWINS (9/11): a stop leg has no limit, so one pull may write
  its stop price in "Price" and another nothing; the merge treats a blank-
  price copy of the same placed-time/contract/side/size/snapshot as the SAME
  order (keeps the priced copy) and collapses such twins already in the
  master on load.
  Webull_Orders_auto.csv "Price" = limit_price, else stop_price.
  Backups: backups/<file>.bak-<stamp> (last 5) — for master_broker,
  master_ledger and master_alerts; NO .bak files in the root anymore.
- BROKER TRUTH: `master_broker.csv` is paged across the full Webull order history; 100-row pages must continue with `last_client_order_id` until a short page. `build_ledger.py` computes P&L from broker fills, collapses carryovers by caller+contract+entry, and matches either end date for overnight trades. Do not quote P&L from book-priced rows when a broker row exists.
- BOT ATTRIBUTION: a caller name is candidate evidence until the entry is linked to a source alert and the trade to broker fills. `manual` in the day row denotes a manual exit; it does not disqualify a bot-origin entry. Adopted/export-only rows need separate entry provenance; caller `?` is unknown. The 107-trade contract-matched study is a dated sample, not a current statistic. `option_tape_pull.py` records quote coverage before skipping downloads.
- NO PAPER, ANYWHERE (9/9, G: "delete all paper trades data from the app, I
  don't want any more confusions"). build_ledger keeps account="paper" rows
  OUT of master_ledger.csv, so the board, journal, scoreboard and
  every backtest are real money only. account="unknown" is NOT paper —
  41 real broker fills with no room row; they stay. execution.webull
  .paper_trading is false and the bridge now WARNS at boot if it is ever
  switched on, because a paper fill would leave no record at all.
- FILLS → master_ledger.csv (built by build_ledger.py, read via ledger.py).
  Sources in trust order: master_broker.csv (the account's own history,
  FIFO-paired per OCC ACROSS days so a swing meets its own lot; trip date =
  the buy's day) > trades.log FILLED > days/wallet.trades > days/table.
  RULES: the broker's exit/P&L/state/account WIN
  over the book's belief (store_pl keeps the book's number); a fill the
  broker saw is `filled` even if the book said `failed`; export-confirmed ⇒
  live; entry time = opened, else the broker's FILLED stamp, NEVER wallet
  `t` (that's the exit); one FILLED line confirms one row; table/wallet
  twins dedupe on date+caller+contract+fill (no time bucket). Gaps are
  rows, not silence (source=trades.log-only / webull-export-only).
  Match a closed position's ORIGINAL size only to one exact OCC, price and
  near-time (five-minute) broker trip; never relax a nonzero size mismatch.
  Day records carry entry_qty, the first broker entry_order_id and client coid.
  A manual exit is exit provenance, not proof of manual entry. Research SQL
  joins alert and trade only on an explicit shared coid or legacy event key.
  RECONCILIATION prints every run: on any day with an export, ledger(live,
  real) must equal the export to the cent (9/4 +152.00 ✓, 9/8 +77.00 ✓ —
  the book had 9/8 at −$82). A DRIFT line = something upstream lied.
  NOTHING reads days/*.json "table" or journal.csv for analysis anymore
  (table truncates — 9/8 it kept 6 of 12 fills; journal.csv inherits it).
  journal.csv is a legacy export the bridge still writes.
- ALERTS → master_alerts.csv (build_alerts.py; ledger.alerts()): every
  alert and its fate — taken side from telemetry.csv (posted/seen/sent/
  filled, slip, greeks), declined side from trades.log via misses.py
  (BUYING POWER / THIN / PULLBACK never hit / SWINGS paused / TEST room /
  FUTURES prop …), filled ones linked to their ledger row. Thin spot:
  telemetry rows carry no room/caller (bridge doesn't populate them).
- PRICE TAPES → tape.py is the ONE registry. Six sources: webull,
  tasty_greeks, tasty_quote, databento (`databento_tape.csv`, despiked IN
  PLACE by clean_tape.py after every backfill — the `_clean` twin is gone
  9/15), missed, and alert. `alert` is `alert_tape.csv`, the slow all-alert lane used for
  refused/missed-call outcomes and caller-exit comparisons; it was wired
  into the registry 9/11 after its writer existed but the common reader did
  not know about it.
  NOT bars/ — that and bars_capture.py were archived 9/9 and tape.py never
  registered them. tape.path(
  "databento") = the despiked clean file when it exists — every backtest
  replays the same prices. Webull has NO historical option prices; the
  tapes are our own record. Databento key (settings execution.databento)
  works from the sandbox; databento_backfill.py spends credit — never run
  its main() casually.
- HOLIDAYS / HOURS → market_hours.py owns the table (through 2027, UPDATE EVERY
  YEAR). holiday_table_flag() says "expiring" in the last 60 days and "stale"
  past it; STATUS.json "broke" and the brief's "What broke" both show it.
  Bump HOLIDAYS_THROUGH; webull_options.HOLIDAYS derives from it. MARKET-HOURS.md is the human copy. Options 9:30-16:00
  (SPY/QQQ/IWM + index to 16:15); futures Sun 18:00 → Fri 17:00 with the
  17:00-18:00 daily halt.
- POST-MORTEMS → master_postmortems.csv + postmortems/<date>_<occ>.md
  (postmortem.py; a SECOND round-trip on the same contract the same day is
  <date>_<occ>-2.md, named by the trade's rank among that day's graded trades
  on the OCC; the csv row is keyed date+occ+fill+exit. G 9/9: "analyze every
  single trade after exiting … be attentive to these"). One verdict per exited bot trade — NOISE CLIP /
  ARM CLIP / GOOD STOP / LEFT MONEY / GAVE BACK / GOOD EXIT — with the call vs our fill,
  the RN wait, the ride (MAE/MFE), the bid at +30s/+1m/+5m/+10m after the
  exit, the widest born stop that would have survived, and every machine
  fault line in the window. The bridge's POSTCHECK loop schedules it 10.5
  min after each close/stop; quote_bus keeps taping an exited contract for
  10 min (LINGER_S) so the after-exit half exists. The autopilot reads new
  ones every 30 min (faults = bugs to fix same day) and tallies them at the
  close (the 0DTE stop question is decided from that tally, by G). His own
  hand trades (Gian / manual) are never graded.
- RN LEDGER → rn_ledger.csv (pullback.log_ledger, append-only): every
  armed/filled/missed/cancelled round-number hunt — the forward tracker
  for "is my RN rule beating their entry" (so far: RN fill vs caller
  price on the same contracts ≈ +$123 edge on 11 → 34 trades; misses
  cost ≈ −$38 on the 2 priced).
- Both central files rebuild inside bridge.py save_day() (never-raise
  guards, ~110 ms, atomic swap) and on demand: python3 build_ledger.py /
  build_alerts.py (keeps 5 .baks, prints summary + reconciliation).
- ANALYSIS TOOLS (all read-only, all on the ledger): caller_report.py,
  scoreboard.py (→ SCOREBOARD.html), journal_full.py (taken+missed xlsx),
  misses.py, errors.py, entry_compare.py, missed_dollarize.py,
  ratchet_sweep*.py, ratchet_backtest.py, chart_contracts.py, telemetry.py.

## CONDENSE AND MERGE — the test (moved from HANDOFF.md 9/15, verbatim)

The rule stays in HANDOFF.md; the procedure is here.

- CONDENSE AND MERGE (G, 9/11). Sibling data belongs in ONE file. Whenever a
  file, a log line type, a column or a folder duplicates something we already
  keep, merge it into the existing home and delete the copy — but only when
  the merge cannot break a reader. The test, in order: (1) name every piece of
  code that opens it (grep the repo, both halves); (2) if anything reads it,
  either repoint that reader in the same change or leave the file alone; (3)
  run the tests AND `node parser_gate.js`; (4) never merge two files whose
  rows mean different things just because the columns line up. Records that
  can never be re-derived — the price tapes, telemetry, days/ — are APPENDED
  to, never rewritten. One-off evidence CSVs from an analysis run get folded
  into the script that regenerates them and then archived, not left in root.
  This is REPLACE-DON'T-STACK applied to data instead of code. When in doubt
  leave it and write the reason in DATA-MAP.md.

## Rules for whoever edits this file

Same house rule as everywhere else: **replace, don't stack.** When a count
changes, edit the number in place and change the date at the top. When a file
is deleted, delete its row. History goes to `HANDOFF-LOG.md`, never here.
