# DISCORD SNIPER — THE HANDOFF
Read this first for current operating state. Session history and past findings
live in HANDOFF-LOG.md; they are evidence, not current instructions.
Last updated: 2026-09-15 — cut to a RULES CORE: one line per rule, every mechanic moved verbatim to its reference doc (28,060 bytes before). The ceiling is now 14 KB, not 30.

## How to update this file (READ BEFORE EDITING — the old way broke things)
- This file is a STATE, not a story. Edit the rule that changed, in place.
  REPLACE, DON'T STACK: the new rule takes the old one's place — never
  leave the old one beside it with a "SUPERSEDED" note.
- ONE RULE, ONE LINE: `- NAME (G, date): the imperative. reference/DOC.md`. Numbers, thresholds, formats, procedures, examples, history and rationale are MECHANICS — they go in the reference doc, not here.
- Bump the one "Last updated:" line above. One line. Never prepend an essay.
- Session notes, findings, post-mortems, numbers-of-the-day go to
  HANDOFF-LOG.md under "SESSION NOTES", newest first, dated. That file may
  grow forever; this one may not. Hard ceiling: under 14 KB. If you are
  about to push it past that, you are writing history or mechanics, not a
  rule — move it (history → HANDOFF-LOG.md, how-it-works → reference/).
- RULES live here; MECHANICS (how a subsystem works, numbers, formats) live
  in one reference doc per subsystem, pointed to from the section below.
  G's own rule wording ("(G, date)", "RULE:") stays verbatim.
- Do not create handoff copies, dated handoffs, or upload snapshots. Daily
  performance belongs in `daily-reports/`; operating rules belong here.
- `HANDOFF-LOG.md` and the retired handoffs zipped in `archive/` are
  historical evidence, never current instructions.

## Where the mechanics live (one pointer per subsystem)
ASK-MAP.md (what to read for which question) · STATUS.json (the day's numbers,
what broke, verified checks) · reports/INDEX.json (report cache) ·
reference/ENTRIES.md (entry mechanics: pullback, strikes, expiry, guards,
dedupe, edits, futures, index mirror) · reference/RATCHET.md (ratchet, futures
ratchet, swings, close path, 0DTE) · reference/ROOMS-TABS.md (rooms.txt fields,
tabs, hours, relays, Whop, voice, popup) · reference/OPERATIONS.md (restarts,
POSTCHECK, the 16:40 audit, git, autopilot, announcer, departments, readers,
keys, second machine, caller research) · DATA-MAP.md (what is inside every
data file, the data families) · reference/OPTIONS-BROKER-REFERENCE.md (Webull
facts) · MARKET-HOURS.md (hours, holidays) · ARCHITECTURE.md (modules, seams)
· INDEX.md (what every file is).
Added 9/15: reference/OPERATIONS.md also holds the weekly-file and house file
rules · ARCHITECTURE.md the machine paragraph, accounts, coexistence, north
star · DATA-MAP.md the CONDENSE AND MERGE test · reference/EOD-BENCHMARK-SPEC.md
(report contract) · reference/PULLBACK-LEVELS.md · reference/CALLER-LEDGER.md ·
HANDOFF-LOG.md (history) · extension/rooms.txt · settings.json (keys,
gitignored) · master_ledger.csv / master_alerts.csv (truth) · days/ ·
daily-reports/ + daily-audits/ (one file per week per kind) · project/.

## Who and what
- G (giancuffaro230@gmail.com) — maintains this code himself (9/13), trades options + futures live,
  real money. Wants it CONDENSED. "Fix everything is default always" — bugs
  get fixed without asking, same day. "Fix errors every day after journaling."
- Real-money actions are HIS ALONE: placing/canceling orders, flipping rooms
  LIVE, unlocking accounts, funding, questionnaires, accepting ToS, passwords.
- ACCOUNTS: `execution.mode=dryrun` does NOT disable per-room live Webull orders; verify buying power and positions AT THE BROKER before any claim; futures_brokers.webull, Topstep/Tradovate and NinjaTrader stay OFF.
- COEXISTENCE: Market Sniper (port 8000) is his own tool on the same account and rate budget — its positions are visible, NEVER stop-managed or sold; changing either app's ratchet spacing is a separate trading decision.
- PRODUCT NORTH STAR (G, 9/11): every day leaves a complete auditable alert funnel and append-only data to benchmark caller vs bot policy vs broker truth; never substitute a later high for a caller exit.
- AI READS ARE PROPOSALS: the parser and every guard judge them, AI confidence authorizes nothing; a model field that is "" or a range is NO CALL — not a crash, not an order; department output is advisory, never code or orders.
- CALLER IDENTITY IS CANDIDATE EVIDENCE: win rates unavailable until trade attribution exists; a newly observed account never gets an execution key; legacy ID-less rows stay unavailable — re-grab, never infer.
- Claude exports and project/context/ are historical reference only.

## Rules of the house (current, in force)

ENTRIES (mechanics: reference/ENTRIES.md)
- PRICE: the caller's price or better; pullback entries cross the ask at the touch; one contract per entry while the bracket is on.
- RN PULLBACK is global and ON and THE LEVEL STAYS $1 — SETTLED 9/9; don't re-open it on a feeling. reference/PULLBACK-LEVELS.md
- ROOMS — ONE SWITCH PER ROOM (G, 9/9): ON = tab open + read + trades LIVE; OFF = nothing; LAPSED = the sub ran out, probed daily. No testing/paper state. CLOSING A TAB BY HAND IS NOT A BENCH — the switch is the only bench, and benched rooms are never deleted.
- TABS (9/10): the reaper closes ONLY tabs the extension opened (`_OURS`), never a human's, whatever URL it is on; only START HERE's one-shot request, the popup's Channels switch and whopSelfHeal() may open one; a "No Access" title writes the room `lapsed` and closes its tab.
- ROOM RULES live in rooms.txt's 6th field, set from the popup pills — settings.json holds none; the `spx` flag was DELETED 9/10.
- ROOM HOURS: `on` rooms 9:15–16:30 ET on weekdays unless `always`; a hand-closed Discord tab stays closed until the next START HERE or switch change; the last browser tab is never closed.
- CHANNELS: callers are shown inside their verified room, win rate unavailable without evidence; no separate Callers / Needs You tab (G).
- STRIKES: never more than 1 strike OTM; deeper snaps to the first OTM rung; 3-ITM for SPY/QQQ/Mag7 0DTE; ADD buys the held strike.
- "ADDED <full contract>" you are not in = an OPEN entry. A bare "added to SPY" refuses.
- NO SPX→SPY (G, 9/10: "do not translate any SPX to SPY"). Index entries are HELD until execution.index_broker is set.
- WORD ORDER: ticker, strike and expiry in any order — SCOPED ON PURPOSE to `bare` rooms. TWO CONTRACTS IN ONE MESSAGE = TWO ORDERS (9/10): one each, own born stop, own ratchet, not a spread; same ticker only; call+put refuses the whole line.
- EXPIRY in ONE place: NDTE is N CALENDAR days rolling BACK over weekends/holidays, never past today; NO DATE = 0DTE (G, 9/10) and the LISTING is ASKED, never assumed; "FRIDAY WEEKLIES ONLY" is DEAD; clues win first.
- THE CONTRACT MUST EXIST (9/15) AND BE IN PRICE BAND (9/14): every entry asks the broker if it is listed — siblings listed → REFUSE, nothing listed → THROUGH with a LISTING line, fails open; on an INFERRED expiry an out-of-band ask is the wrong contract — take the listed expiry in band, else REFUSE.
- GUARDS: SPREAD and THIN refuse wide or illiquid entries; nothing older than 3 min fires; negations hard-veto; the DEDUPE LADDER ends at ONE average-down ADD under what was PAID, identity caller+symbol+strike+side+expiry everywhere.
- AN EDIT IS A REPLACEMENT, NOT A SECOND TRADE (9/14): it cancels the earlier hunt and its resting bid; two DIFFERENT message ids are two calls, never an edit.
- IF THE CORRECTED CONTRACT ALREADY FILLED (9/15, G: "if in profit keep the ratchet and set the stop to breakeven, if it's a losing trade, close it automatically"), judged on the CURRENT BID vs the fill. THE ONE EXCEPTION TO ENTRIES-ONLY, and not a room exit.
- RETRACTION ("not ready / scratch that / cancel / disregard / hold off / nevermind") pulls that trader's resting bids and armed hunts.
- FUTURES: micros only; their stop/target wins; a Webull futures OPEN refuses until an exact GTC STOP_LOSS is placed and verified after its fill. INDEX MIRROR (9/13) is OFF, blocked until a broker-confirmed futures protective exit exists. THE POCKET (pocket_scalps_only) is default OFF.
- REVIEWS (9/13): the optionality channel is ON by G's choice; no arbitrary premium range, no automatic factor-of-100 correction; missing units stay unresolved.

EXITS — THE DOCTRINE: THEIR TRIGGER → OUR ENTRY → THE RATCHET'S EXIT (mechanics: reference/RATCHET.md)
- ENTRIES ONLY (G, 9/3): the bot follows room ENTRIES (and adds) only. EVERY room-side exit — trim, stop-move, "all out", "stopped out", "closed everything" — is logged "EXIT-IGNORED … entries only" and NEVER traded. The ratchet's resting stop at Webull is the ONLY exit. A bot SELL that traces to a room's exit call is a BUG.
- THE RATCHET (5/3/5 since 9/10, flat): born stop −5%; +3% moves the stop to breakeven; each further +5% locks another +5%. ratchet_tiers.py is the one implementation. Stops never loosen. Anti-clip is off.
- FUTURES RATCHET (9/9) is derived from the trade's own risk, never a fixed number.
- SWINGS: 14+ DTE = swing (auto-tagged); their stock-level stop runs it, no level = wide −25% re-armed every morning at 9:31. Scalps excluded on purpose.
- CLOSE path: every bot sell waits for FILLED — an ACCEPTED sell is never booked as filled; a CLOSE for a contract the book does not hold is REFUSED, never sent.
- 0DTE: ETF options trade to 16:15; auto-exercise at $0.01 ITM — flatten before the close.

RESTARTS / SAFETY / THE HOUSE RULES (mechanics: reference/OPERATIONS.md)
- BOOT: state photo on every event; everything UNVERIFIED until the broker confirms; expired options = dead paper; code updates self-apply at the first safe window; resting stops at Webull guard every gap. POSTCHECK after every trade logs "POSTCHECK … PROBLEM" when book, stop and quote bus disagree.
- RULE: weekly signal-room-chat logs (replaces daily) (G, 9/15). ds_logs.py owns naming, blocks and de-dupe; never hand-edit a week file.
- WEEKLY REPORTS (9/15): every report kind is ONE file per week per kind, newest day first, a re-run replacing that day's block. reports.py owns naming and the cache; writers call it, never mint a dated file.
- APPEND, DON'T PILE (G, 9/15). New data goes INTO the one living file for its kind — never a new dated file beside it; rotated logs and finished experiments land zipped in `archive/`.
- REUSE, DON'T REBUILD (G, 9/15). A report whose inputs have not changed is handed over as it is — `reports.py status` decides, `reports/INDEX.json` is the memory. Rebuild only when it says stale. Never re-derive by reading logs what a report already states.
- ASK-MAP FIRST (G, 9/15). Every ask starts at ASK-MAP.md, then STATUS.json. Logs are read only when those two cannot answer. Checks recorded in STATUS.json.verified are trusted while their inputs are unchanged (VERIFY ONCE).
- DAILY SNIPER REPORT: daily_audit.py runs once per weekday at 16:40 ET. Broker-confirmed actuals override any simulation; RAW capture is kept and LIVE PARSER rows overlay it; relay duplicates count once; expired pullback waits are skips; the 15-minute Codex guard was deleted at G's request — do not recreate it.
- GIT: settings.json holds every key and is never committed. AUTO PUSH owns commits (every 45 s); never run git write commands from a sandbox. After suspicious loss check `git reflog` for a "reset:" before rebuilding.
- REPLACE, DON'T STACK (G, 9/9). When something changes — a rule, a value,
  a function, a setting, a room line, a doc — the new version takes the old
  one's place. Never leave the old beside the new: not commented out, not
  "superseded", not "legacy/old/deprecated", not a dead branch kept "just
  in case". One thing, one truth. History lives in git and HANDOFF-LOG.md,
  never in the working file. A fallback that must stay is a deliberate
  design decision, written as one — not leftovers. Applies to code,
  settings.json, rooms.txt, every .md, and this file.
- CONDENSE AND MERGE (G, 9/11). Sibling data belongs in ONE file: merge the duplicate into the existing home and delete the copy, but only when the merge cannot break a reader (the test: DATA-MAP.md). Records that can never be re-derived — the price tapes, telemetry, days/ — are APPENDED to, never rewritten. When in doubt leave it and write the reason in DATA-MAP.md.
- READ DATA-MAP.md WITH INDEX.md at the start of every session: INDEX.md says what a file IS, DATA-MAP.md what is IN it. RUN build_ledger.py IN EASTERN.
- COMPILE-CHECK everything touched (python3 -m py_compile / node --check); extension changes bump extension/manifest.json; never install the streaming SDK family (webullsdkcore) into the bridge's Python; sandbox trading is RETIRED — paper is LOCAL (SIM tickets).
- DISCORD API IS NOT AN OPTION (reaffirmed 9/9): user-token automation risks a permanent ban on the account and the paid subs; official bots need the server owner. Browser reads only.

ROOMS / TABS / READERS (mechanics: reference/ROOMS-TABS.md)
- rooms.txt = THE channel list (tabs + trading, one file). START HERE IS FULLY UNATTENDED (G, 9/9); between runs NOTHING opens rooms. The only inputs no script may do: a Discord/Whop login, and Webull keys in the popup.
- Relays: OWLS all-alerts is active and RELAY UNWRAP re-books under the real trader; ZTRADEZ, shabs and eli direct rooms were retired 9/9.
- TAB HEALTH: never close a human-owned tab; active/voice tabs are protected; Chrome uses Profile 2 for Discord and Profile 6 for Whop.
- VOICE: ears transcribe always (Deepgram); voice ENTRIES ON (9/2), voice EXITS irrelevant under entries-only; a typed copy of a voice fire is an echo. Any room quiet 40 min in market hours raises the silence alarm.

FILL ANNOUNCER (announcer.py, read-only; mechanics: reference/OPERATIONS.md)
- Posts every fill, milestone, stop-out and the scoreboard to G's Discord webhooks; NEITHER channel ever goes into rooms.txt.
- PAUSED since 9/2 (announcer.stop = "stop"). Its board is computed FROM THE LEDGER (9/9); its order hunt is paced — the 9/2 429 storm must never come back.

## DATA — one central file per family (9/9). THE APP READS ONLY THESE.
(what is inside each: DATA-MAP.md)
- BROKER RECORD → master_broker.csv; the Webull export is ONE fixed file OVERWRITTEN every run — never dated Webull_Orders_<date> piles (G, 9/9, 9/10); one balance row per day in balance_daily.csv.
- FILLS → master_ledger.csv. The broker's exit/P&L/state/account WIN over the book's belief; a DRIFT line in RECONCILIATION means something upstream lied; NOTHING reads days/*.json "table" or journal.csv for analysis.
- ALERTS → master_alerts.csv. RN LEDGER → rn_ledger.csv (append-only).
- PRICE TAPES → tape.py is the ONE registry; Webull has NO historical option prices, the tapes are our own record; databento_backfill.py spends credit — never run its main() casually.
- HOLIDAYS / HOURS → market_hours.py owns the table — UPDATE EVERY YEAR.
- POST-MORTEMS → master_postmortems.csv + postmortems/; his own hand trades are never graded.
- NO PAPER, ANYWHERE (9/9, G: "delete all paper trades data from the app, I don't want any more confusions"): account="paper" rows stay OUT of master_ledger.csv, account="unknown" is NOT paper, and the bridge WARNS at boot if paper_trading is switched on.
- BOT ATTRIBUTION: a caller name is candidate evidence until the entry links to a source alert and the trade to broker fills; never quote P&L from book-priced rows when a broker row exists.

## Broker facts — the RULES only (all of them: reference/OPTIONS-BROKER-REFERENCE.md, read it before any broker test)
- NO MARKET ORDERS ON OPTIONS; combos = MASTER(LIMIT) + STOP_LOSS on SINGLE only.
- Option SELL orders are DAY-only → every resting stop dies at the close.
- Rate limits are PER ENDPOINT per app key and shared with Market Sniper; 429 = throttle, 417 = business rejection. No option streaming; fills ARE pushed.
- Ticks are symbol-aware (SPY/QQQ/IWM, Penny Program, the rest) — never invent one.

## Operational truths (mechanics: reference/OPERATIONS.md, reference/ROOMS-TABS.md)
- sniper-autopilot (*/30 ET) never places or cancels orders and never touches settings.json.
- THE PAGE is the SAME popup.html opened as a normal tab — one file, two sizes, never a second dashboard. Claude-in-Chrome CANNOT read the popup; the red line under the rooms is the diagnosis — ask for it.
- Multi-account: extras mirror LIVE entries 1:1 with own books/stops.
- SECOND MACHINE (planned 9/9, default-off until PC2 exists): ONE bridge, ONE book, ONE rate budget — never a second bridge on the same Webull account.

## Pending external setup and decisions
1. In Claude: use project/PROJECT-INSTRUCTIONS.md as the Project
   instructions and remove the old uploaded handoffs (local cleanup does not
   remove what was already uploaded).
2. Market Sniper: apply HANDOFF-RATCHET-2026-09-09.md (options 5→2 rung,
   futures decouple) — G's call whether Claude does it or he does.
3. NinjaTrader ATM template "SNIPER": stop 100 ticks / target 200 (=25/50
   MNQ pts), qty 1 — create in NT8, type SNIPER in the popup.
4. Close any old parked Whop tabs. (`--disable-gpu` rides every flagged
   Chrome launch since 9/10 — a GPU black tab reads NOTHING while looking
   open; flags bind only on a cold start.)
5. Announcer: paused since 9/2 — the Needs-you tab has the on/off button.
6. CHROME BEFORE 9:15: rooms open at 9:15 only if Chrome + the extension
   are already up. Run START HERE, or schedule it, by 9:00 on trading days.

## Watch items (open)
- PULLBACK STOCK TARGET vs THE RATCHET (9/10, G's call): a pullback entry
  CLOSES at a fixed stock target ($1 past the round number) — a second,
  earlier exit beside the ratchet (9/10: +$80 taken, +$307 left). (a) delete
  the target, keep the pullback stock-STOP; (b) keep it. Nothing changes
  until G says.
- FUTURES RECORDS (G, 9/9): the moment futures execution works, its fills
  need pulling into the ledger the way options fills are (a broker export
  into master_broker.csv). Until then every futures caller — Stormzy 5
  positions, Market Guru 7, Namrood-BOT — sits on the scoreboard with a
  count and no money, which is honest but useless for ranking them.
- Telemetry rows lack room/caller → master_alerts taken-side is anonymous.
- Deepgram key may be one char short (39) — watch for voice auth errors.
- First live overnight broker stop on a swing: confirm it survives the night.
- Market Sniper closed bot positions by MARKET order on 9/2 (FLR, SPY 766C)
  — policy question still open: should a room's NAMED exit reach adopted
  positions? (Under entries-only today: no.)
- bridge.log has no rotation (20 MB).
- Multi-account "L": verify no orphan positions after mirror exits.
- Topstep: not executing futures (see HANDOFF-LOG.md for the findings);
  Webull futures $0 by choice — futures refusals there are intentional.

## Subscriptions
≈ $1,140/mo rooms + ~$52 infra + ~$30 exchange fees ≈ $1,220/mo before AI
usage. Break-even ≈ $60+/trading day. Next audit: cost vs ledger P&L per room.
