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
