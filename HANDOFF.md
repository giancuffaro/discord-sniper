# DISCORD SNIPER — THE HANDOFF
Read this first for current operating state. Session history and past findings
live in HANDOFF-LOG.md; they are evidence, not current instructions.
Last updated: 2026-09-15 — cut to a RULES CORE (was 28,060 bytes): one line per rule, mechanics moved verbatim to the reference docs. Ceiling is now 14 KB.

## How to update this file (READ BEFORE EDITING — the old way broke things)
- This file is a STATE, not a story. Edit the rule that changed, in place.
  REPLACE, DON'T STACK: the new rule takes the old one's place — never
  leave the old one beside it with a "SUPERSEDED" note.
- ONE RULE, ONE LINE. Numbers, formats, procedures, examples and rationale are MECHANICS — reference doc, not here.
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
9/15: OPERATIONS also holds the weekly-file + house rules and the watch-item
detail · ARCHITECTURE the machine, accounts, coexistence, north star · DATA-MAP
the CONDENSE test · also reference/EOD-BENCHMARK-SPEC.md, PULLBACK-LEVELS.md,
CALLER-LEDGER.md · HANDOFF-LOG.md (history) · extension/rooms.txt ·
settings.json (keys, gitignored) · master_ledger.csv / master_alerts.csv ·
days/ · daily-reports/ + daily-audits/ (one week file per kind).

## Who and what
- G (giancuffaro230@gmail.com) — maintains this code himself (9/13), trades options + futures live,
  real money. Wants it CONDENSED. "Fix everything is default always" — bugs
  get fixed without asking, same day. "Fix errors every day after journaling."
- Real-money actions are HIS ALONE: placing/canceling orders, flipping rooms
  LIVE, unlocking accounts, funding, questionnaires, accepting ToS, passwords.
- ACCOUNTS: `execution.mode=dryrun` does NOT disable per-room live orders; verify buying power and positions AT THE BROKER before any claim; futures_brokers.webull, Topstep/Tradovate, NinjaTrader stay OFF.
- COEXISTENCE: Market Sniper (port 8000) is his own tool on the same account and rate budget — its positions are visible, NEVER stop-managed or sold.
- NORTH STAR (G, 9/11): every day leaves a complete auditable alert funnel and append-only data to benchmark caller vs bot policy vs broker truth; a later high is never a caller exit.
- AI READS ARE PROPOSALS: parser and guards judge them, AI confidence authorizes nothing; "" or a range is NO CALL — not a crash, not an order; department output is advisory, never code or orders.
- CALLER IDENTITY IS CANDIDATE EVIDENCE: no win rate until trade attribution exists; a new account never gets an execution key; ID-less rows stay unavailable — re-grab, never infer.
- Claude exports and project/context/ are historical reference only.

## Rules of the house (current, in force)

ENTRIES · reference/ENTRIES.md
- PRICE: caller's price or better; pullbacks cross the ask; one contract per entry.
- RN PULLBACK is ON and global; THE LEVEL STAYS $1 (SETTLED 9/9) — never re-opened on a feeling.
- ONE SWITCH PER ROOM (G, 9/9): ON = tab + read + trades LIVE; OFF = nothing; LAPSED = sub ran out. No paper state. A TAB CLOSED BY HAND IS NOT A BENCH; benched rooms stay in the file.
- TABS (9/10): the reaper closes only `_OURS`, never a human's; only START HERE, the popup switch and whopSelfHeal() open one; "No Access" → `lapsed` + close; the last tab never closes.
- ROOM RULES = rooms.txt 6th field (popup pills), not settings.json; `spx` DELETED 9/10. HOURS 9:15–16:30 ET unless `always`; hand-closed tabs stay closed.
- CHANNELS: callers inside their verified room; win rate needs evidence; no Callers tab (G).
- STRIKES: max 1 OTM, deeper snaps to the first rung; 3-ITM for SPY/QQQ/Mag7 0DTE; ADD buys the held strike.
- "ADDED <full contract>" you are not in = an OPEN entry; a bare "added to SPY" refuses.
- NO SPX→SPY (G, 9/10: "do not translate any SPX to SPY"); index entries are HELD until execution.index_broker is set.
- WORD ORDER: any order, `bare` rooms only. TWO CONTRACTS = TWO ORDERS (9/10): one each, own stop and ratchet, same ticker; call+put refuses the line.
- EXPIRY, one place: NDTE = N CALENDAR days rolling BACK, never past today; NO DATE = 0DTE (G, 9/10), the LISTING ASKED never assumed; "FRIDAY WEEKLIES ONLY" is DEAD.
- CONTRACT MUST EXIST (9/15) AND BE IN PRICE BAND (9/14): siblings listed → REFUSE; nothing listed → THROUGH + LISTING line; fails open, a guard never a gate.
- GUARDS: SPREAD/THIN refuse wide or illiquid; nothing older than 3 min fires; negations hard-veto; DEDUPE ends at ONE average-down ADD under what was PAID.
- AN EDIT IS A REPLACEMENT, NOT A SECOND TRADE (9/14): it kills the earlier hunt and its bid; two DIFFERENT message ids are two calls. Identity = caller+symbol+strike+side+expiry.
- IF THE CORRECTED CONTRACT ALREADY FILLED (9/15, G: "if in profit keep the ratchet and set the stop to breakeven, if it's a losing trade, close it automatically"), on CURRENT BID vs fill. THE ONE EXCEPTION TO ENTRIES-ONLY, not a room exit.
- RETRACTION ("not ready / scratch that / cancel / disregard / hold off / nevermind") pulls that trader's bids and armed hunts.
- FUTURES: micros only; their stop/target wins; a Webull futures OPEN refuses until an exact GTC STOP_LOSS is verified after its fill. INDEX MIRROR (9/13) OFF until a broker-confirmed futures exit exists. THE POCKET default OFF.
- REVIEWS (9/13): optionality channel ON (G); no arbitrary premium range, no automatic factor-of-100 correction.

EXITS — THE DOCTRINE: THEIR TRIGGER → OUR ENTRY → THE RATCHET'S EXIT · reference/RATCHET.md
- ENTRIES ONLY (G, 9/3): the bot follows room ENTRIES (and adds) only. EVERY room-side exit — trim, stop-move, "all out", "stopped out", "closed everything" — is logged "EXIT-IGNORED … entries only" and NEVER traded. The ratchet's resting stop at Webull is the ONLY exit. A bot SELL tracing to a room's exit call is a BUG.
- THE RATCHET (5/3/5 since 9/10, flat): born −5%, +3% → breakeven, each +5% locks +5%; ratchet_tiers.py is the one implementation; stops never loosen; anti-clip off.
- FUTURES RATCHET (9/9) comes from the trade's own risk, never a fixed number.
- SWINGS (14+ DTE, auto-tagged): their stock stop runs it; no level = wide −25% re-armed at 9:31; scalps excluded.
- CLOSE: every bot sell waits for FILLED; a CLOSE the book does not hold is REFUSED, never sent. 0DTE: ETFs trade to 16:15, auto-exercise at $0.01 ITM — flatten before the close.

RESTARTS / SAFETY / HOUSE RULES · reference/OPERATIONS.md
- BOOT: state photo per event; all UNVERIFIED until the broker confirms; expired options = dead paper; updates apply at the first safe window. POSTCHECK logs a PROBLEM when book, stop and quote bus disagree.
- RULE: weekly signal-room-chat logs (replaces daily) (G, 9/15). ds_logs.py owns naming, blocks and de-dupe; never hand-edit a week file.
- WEEKLY REPORTS (9/15): ONE file per week per kind, newest day first; reports.py owns it, writers never mint a dated file.
- APPEND, DON'T PILE (G, 9/15). New data goes INTO the one living file for its kind — never a new dated file beside it; rotated logs and finished experiments zip to `archive/`.
- REUSE, DON'T REBUILD (G, 9/15). A report whose inputs have not changed is handed over as it is — `reports.py status` decides, `reports/INDEX.json` is the memory. Rebuild only when it says stale. Never re-derive by reading logs what a report already states.
- ASK-MAP FIRST (G, 9/15). Every ask starts at ASK-MAP.md, then STATUS.json. Logs are read only when those two cannot answer. Checks recorded in STATUS.json.verified are trusted while their inputs are unchanged (VERIFY ONCE).
- THE 16:40 AUDIT: broker actuals override any simulation; RAW capture is kept and LIVE PARSER rows overlay it; relay duplicates count once; expired pullback waits are skips; never recreate the deleted 15-minute Codex guard.
- GIT: settings.json holds every key and is never committed; AUTO PUSH owns commits; never run git write commands from a sandbox.
- REPLACE, DON'T STACK (G, 9/9). When something changes — a rule, a value,
  a function, a setting, a room line, a doc — the new version takes the old
  one's place. Never leave the old beside the new: not commented out, not
  "superseded", not "legacy/old/deprecated", not a dead branch kept "just
  in case". One thing, one truth. History lives in git and HANDOFF-LOG.md,
  never in the working file. A fallback that must stay is a deliberate
  design decision, written as one — not leftovers. Applies to code,
  settings.json, rooms.txt, every .md, and this file.
- CONDENSE AND MERGE (G, 9/11). Sibling data belongs in ONE file: merge the duplicate into the existing home and delete the copy, but only when the merge cannot break a reader (the test: DATA-MAP.md). Records that can never be re-derived — price tapes, telemetry, days/ — are APPENDED to, never rewritten. In doubt, leave it and write why in DATA-MAP.md.
- READ DATA-MAP.md WITH INDEX.md every session: INDEX says what a file IS, DATA-MAP what is IN it. RUN build_ledger.py IN EASTERN.
- COMPILE-CHECK everything touched; bump extension/manifest.json on extension changes; never install webullsdkcore into the bridge's Python; sandbox is RETIRED, paper is LOCAL (SIM).
- DISCORD API IS NOT AN OPTION (9/9): user-token automation risks a permanent ban on the account and the subs; official bots need the owner. Browser reads only.

ROOMS / TABS / READERS · reference/ROOMS-TABS.md
- rooms.txt = THE channel list (tabs + trading, one file). START HERE IS FULLY UNATTENDED (G, 9/9); between runs NOTHING opens rooms; the only manual inputs are a Discord/Whop login and Webull keys.
- Relays: OWLS all-alerts active, RELAY UNWRAP re-books under the real trader; ZTRADEZ, shabs, eli retired 9/9. Never close a human tab; Profile 2 = Discord, Profile 6 = Whop.
- VOICE: ears always transcribe (Deepgram); voice ENTRIES ON (9/2), exits irrelevant; a typed copy of a voice fire is an echo. A room quiet 40 min in hours raises the silence alarm.

FILL ANNOUNCER (announcer.py, read-only) · reference/OPERATIONS.md
- Posts every fill, milestone, stop-out and the scoreboard to G's webhooks; NEITHER channel goes into rooms.txt.
- PAUSED since 9/2; board computed FROM THE LEDGER (9/9); order hunt paced — the 9/2 429 storm must never come back.

## DATA — one central file per family (9/9). THE APP READS ONLY THESE.
(what is inside each: DATA-MAP.md)
- BROKER RECORD → master_broker.csv; the Webull export is ONE file OVERWRITTEN every run, never dated piles; one balance row a day in balance_daily.csv.
- FILLS → master_ledger.csv. The broker's exit/P&L/state/account WIN over the book; a DRIFT line means something upstream lied; nothing reads days/*.json or journal.csv for analysis.
- ALERTS → master_alerts.csv. RN LEDGER → rn_ledger.csv (append-only). HOLIDAYS / HOURS → market_hours.py owns the table — UPDATE EVERY YEAR.
- PRICE TAPES → tape.py is the ONE registry; Webull has NO historical option prices; databento_backfill.py spends credit — never run its main() casually.
- POST-MORTEMS → master_postmortems.csv + postmortems/; his own hand trades are never graded.
- NO PAPER, ANYWHERE (9/9, G: "delete all paper trades data from the app, I don't want any more confusions"): account="paper" rows stay OUT of master_ledger.csv, account="unknown" is NOT paper.
- BOT ATTRIBUTION: a caller name is candidate evidence until the entry links to an alert and the trade to broker fills; never quote P&L from a book-priced row when a broker row exists.

## Broker facts — RULES only · reference/OPTIONS-BROKER-REFERENCE.md before any broker test
- NO MARKET ORDERS ON OPTIONS; combos = MASTER(LIMIT) + STOP_LOSS on SINGLE only.
- Option SELL orders are DAY-only → every resting stop dies at the close.
- Rate limits are PER ENDPOINT per app key, shared with Market Sniper; 429 = throttle, 417 = business rejection. No option streaming; fills ARE pushed.
- Ticks are symbol-aware — never invent one.

## Operational truths · reference/OPERATIONS.md, reference/ROOMS-TABS.md
- sniper-autopilot (*/30 ET) never places or cancels orders and never touches settings.json.
- THE PAGE is the SAME popup.html opened as a tab — never a second dashboard. Claude-in-Chrome CANNOT read the popup; the red line under the rooms is the diagnosis — ask for it.
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
4. Close any old parked Whop tabs (the Chrome flags note: reference/OPERATIONS.md).
5. Announcer: paused since 9/2 — the Needs-you tab has the on/off button.
6. CHROME BEFORE 9:15: rooms open at 9:15 only if Chrome + the extension
   are already up. Run START HERE, or schedule it, by 9:00 on trading days.

## Watch items (open) — the detail is in reference/OPERATIONS.md
- PULLBACK STOCK TARGET vs THE RATCHET (9/10): a pullback entry also closes at a fixed stock target, a second exit beside the ratchet. (a) delete it (b) keep it — G decides.
- FUTURES RECORDS (G, 9/9): the moment futures execution works its fills must be pulled into the ledger; until then futures callers rank by count, not money.
- Telemetry rows lack room/caller → the master_alerts taken side is anonymous.
- Deepgram key may be one char short (39) — watch for voice auth errors.
- First live overnight broker stop on a swing: confirm it survives the night.
- Should a room's NAMED exit reach adopted positions? Under entries-only today: no.
- bridge.log has no rotation (20 MB).
- Multi-account 'L': verify no orphan positions after mirror exits.
- Topstep is not executing futures; Webull futures $0 by choice — refusals there are intentional.

## Subscriptions
≈ $1,140/mo rooms + ~$52 infra + ~$30 exchange fees ≈ $1,220/mo before AI
usage. Break-even ≈ $60+/trading day. Next audit: cost vs ledger P&L per room.
