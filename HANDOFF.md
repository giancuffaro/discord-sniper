# DISCORD SNIPER — THE HANDOFF
Read this first for current operating state. Session history and past findings
live in HANDOFF-LOG.md; they are evidence, not current instructions.
Last updated: 2026-09-15 — no-message-id edit needs a correction word or ≥0.9 text match (alert_revision.py); holiday_table_flag() surfaced in STATUS.json + the brief; Perplexity probe URL fixed; two comment essays cut to one line. Prior: REUSE, DON'T REBUILD; ASK-MAP FIRST.

## How to update this file (READ BEFORE EDITING — the old way broke things)
- This file is a STATE, not a story. Edit the rule that changed, in place.
  REPLACE, DON'T STACK: the new rule takes the old one's place — never
  leave the old one beside it with a "SUPERSEDED" note.
- Bump the one "Last updated:" line above. One line. Never prepend an essay.
- Session notes, findings, post-mortems, numbers-of-the-day go to
  HANDOFF-LOG.md under "SESSION NOTES", newest first, dated. That file may
  grow forever; this one may not. Hard ceiling: under 30 KB. If you are
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

## Who and what
- G (giancuffaro230@gmail.com) — maintains this code himself (9/13), trades options + futures live,
  real money. Wants it CONDENSED. "Fix everything is default always" — bugs
  get fixed without asking, same day. "Fix errors every day after journaling."
- The machine: Chrome MV3 extension source v3.8.33 reads Discord in Profile 2 and Whop in Profile 6 (display name “Whop Profile”). Typed, voice, and image alerts go to the Python bridge on 127.0.0.1:8787. Webull options use caller price or better, optional round-number pullback, a bracket stop born with the entry, and the flat 5/3/5 ratchet. Fill Announcer may be paused. The weekday autopilot audits and journals after close. Market Sniper shares Webull; this bot never manages its positions.
- Accounts: `execution.mode=dryrun` does not disable per-room live Webull
  orders. Verify current buying power and positions at the broker before
  making claims. Webull options share one API budget with Market Sniper;
  `futures_brokers.webull` and Topstep/Tradovate remain off. NinjaTrader
  execution was paused 9/13; its configured account remains untouched.
- Market Sniper on port 8000 is G's separate tool on the same account. Its
  positions are visible but never stop-managed or sold by Discord Sniper;
  Book.is_hand_trade enforces that boundary. The two apps' ratchet spacing
  differs; changing either is a separate trading-policy decision.
- Real-money actions are HIS ALONE: placing/canceling orders, flipping rooms
  LIVE, unlocking accounts, funding, questionnaires, accepting ToS, passwords.
- Claude exports and project/context/ are historical reference only.
- PRODUCT NORTH STAR (G, 9/11): every day must leave a complete, auditable
  alert funnel and enough append-only price/event data to benchmark the
  caller's documented trade, the versioned bot policy on the same alert, and
  the broker-confirmed actual result. Daily reports are the readable snapshot;
  the growing dataset is what earns parser/strategy improvements. Exact caller
  results require real entry+exit evidence; never substitute a later high.
  Full contract: reference/EOD-BENCHMARK-SPEC.md.
- AI reads are PROPOSALS: whatever reads a message (observer, AI READ, IMG
  READ — provider order in reference/OPERATIONS.md), the parser and every
  guard judge it and AI confidence authorizes nothing. A model field that is
  "" or a range ("1.26-1.30") is NO CALL — not a crash, not an order
  (ai_reader.judge() is the one copy of "validate() can never raise").
  Department output is advisory, never code or orders. Anthropic is skipped
  while billing-blocked; DeepSeek removed (G).
- Caller identity is candidate evidence: win rates stay unavailable until
  trade attribution exists; a newly observed account never gets an execution
  key; legacy ID-less rows stay unavailable — re-grab, never infer. Caller
  behaviour numbers (9/14): reference/CALLER-PROFILE-2026-09-14.md.

## Rules of the house (current, in force)
OPTIONALITY REVIEW 9/13: the channel is ON by G's choice (findings in
HANDOFF-LOG.md). PREMIUM REVIEW: no arbitrary premium range and no automatic
factor-of-100 correction; missing units stay unresolved pending source evidence.

ENTRIES (mechanics: reference/ENTRIES.md)
- Bid the caller's price or better; pullback entries cross the ask at the
  touch. RN (round-number) pullback is global and ON. One contract per entry
  while the bracket is on. THE LEVEL STAYS $1 — SETTLED 9/9 on 106 beta-name
  alerts replayed on real 1-second bars (reference/PULLBACK-LEVELS.md). Don't
  re-open on a feeling — re-run the script when the sample doubles.
- ROOMS — ONE SWITCH PER ROOM (9/9 evening, G: "a list of all the rooms
  we've been to and the option to open the tab or not; if I selected to
  open it I obviously want it live"). ON = tab open + read + trades LIVE;
  OFF = no tab, nothing read, nothing traded; LAPSED = off because the sub
  ran out, probed daily. There is NO testing/paper state any more. CLOSING A
  TAB BY HAND IS NOT A BENCH — the switch is the only bench. Benched rooms
  are never deleted from the file.
  WHOSE TABS THE REAPER MAY CLOSE (9/10). ONLY tabs the extension itself
  opened (`_OURS`). A tab a HUMAN opened is never closed, whatever URL it is
  on.
  WHO MAY OPEN A TAB (9/10, G: "get rid of auto opening tabs UNLESS it's
  the start sniper"). Exactly three things, and nothing else: START HERE.bat's
  one-shot request, the popup's Channels switch (his click), whopSelfHeal().
  NO ACCESS = OUT OF SERVICE (9/10, G: "do not open the tab if we don't have
  access"): a "No Access" title writes the room `lapsed` and closes its tab.
  Room RULES (6th field: bare, dotdate, pivot=NQ, readonly, sym=SPX) are set
  from the popup pills; the bridge derives its lists from them, settings.json
  no longer holds those lists. The `spx` flag was DELETED 9/10 (NO SPX->SPY).
- ROOM HOURS: `on` rooms use tabs 9:15–16:30 ET on weekdays unless marked
  `always` (futures rooms). A Discord tab closed by hand stays closed until
  the next START HERE or a room-switch change. The last browser tab is never
  closed.
- CHANNELS / CONTROLS: callers are shown within their verified room, win
  rate unavailable unless backed by evidence; no separate Callers / Needs You
  tab (G). Honey Drip caller switches keep their room keys.
- STRIKES: never more than 1 strike OTM; deeper snaps to the first OTM rung
  (quote-verified). 3-ITM translation for SPY/QQQ/Mag7 0DTE. ADD buys the
  held strike.
- "ADDED <full contract>" you are not in = an OPEN entry. A bare "added to
  SPY" refuses.
- NO SPX→SPY. DELETED 9/10, G: "do not translate any SPX to SPY. Delete any
  sort of translation between SPX and SPY." SPX/SPXW/XSP/RUT/NDX/VIX entries
  are HELD with a plain reason until execution.index_broker is set
  (tastytrade or tradier, a separate funded account).
- WORD ORDER (9/10, G: "it doesn't matter the order of the expiration or the
  price or the ticker. It's not relevant. It could be in any order"). In a
  `bare` room the reader strips the contract's own three tokens wherever each
  sits and fires if nothing is left over. SCOPED ON PURPOSE to `bare` rooms.
- TWO CONTRACTS IN ONE MESSAGE = TWO ORDERS (9/10, G: "when you have
  multistrikes, just buy both of them. Buy two contracts, one of each").
  ONE contract each, own born stop, own ratchet — not a spread. Same ticker
  only; call+put is a strangle and the whole line refuses; max 3 extras.
- EXPIRY (webull_options.expiry_to_date, one place):
  · NDTE is N CALENDAR days out, rolling BACK over weekends/holidays (G,
    9/10: "there is no 3DTE if in three days is a Saturday — it would just
    end in 2DTE"). Never past today.
  · NO DATE = 0DTE (G, 9/10), and the LISTING is ASKED, never assumed (9/14):
    today wins if listed, else the nearest listed date. The old "FRIDAY
    WEEKLIES ONLY" rule is DEAD. Clues still win first ("NEXT WEEK"/"NEXT FRI",
    a shouted MONTH).
  · CALLER-PRICE GATE (9/14, execution.price_sanity = 0.4x–2.5x) on an
    INFERRED expiry: an ask outside the band = wrong contract — take the
    listed expiry that IS in band, else REFUSE. No posted price = inert.
  · THE CONTRACT MUST EXIST (9/15, bridge._verify_listed): EVERY entry asks
    the broker whether that exact contract is listed. Unlisted but siblings
    are -> REFUSE + BAD-CONTRACT line. NOTHING listed anywhere = the feed, not
    the contract: goes THROUGH with a LISTING line. Fails open — a guard,
    never a gate.
- SPREAD GUARD (entries only): refuse if spread > 20% of mid or > max($0.20,
  10% of mid). THIN guard: < 250 contracts last session = refused.
- STALE-ENTRY GATE: entries older than 3 min never fire. Negations ("NOT
  getting in", "too expensive") hard-veto; "out the gate" is hype.
- DEDUPE LADDER: extension in-flight lock → bridge echo-lock (20 s) →
  per-trader "already in" claim → one average-down ADD ≥1% under what was
  PAID. Position identity is caller+symbol+strike+side+expiry everywhere.
- AN EDIT IS A REPLACEMENT, NOT A SECOND TRADE (9/14): an OPEN whose message
  id is already pending on a different contract CANCELS the earlier hunt and
  its resting bid, then arms the new one. Two DIFFERENT message ids are two
  calls, never an edit. NO message id (voice/vision/legacy): same trader, same
  ticker, inside 5 min AND the text reads as a fix — a correction word (edit,
  meant, typo, "*", "not calls/puts") or ≥0.9 similar with the contract
  stripped. Otherwise it is a SIBLING trade and both arms stand (alert_revision.py).
- IF THE CORRECTED CONTRACT ALREADY FILLED (9/15, G: "if in profit keep the
  ratchet and set the stop to breakeven, if it's a losing trade, close it
  automatically"). Judged on the CURRENT BID vs the fill: bid >= fill -> stop
  to BREAKEVEN, ratchet keeps running; bid < fill -> CLOSED down the existing
  exit path. No bid, a non-option, or a stop that will not move = LOGGED ONLY.
  THE ONE EXCEPTION TO ENTRIES-ONLY, and not a room exit: the caller changed
  the CONTRACT, so what we hold is OUR misread. Their trims, stop-moves and
  "all out" stay EXIT-IGNORED.
- RETRACTION ("not ready / scratch that / cancel / disregard / hold off /
  nevermind") pulls that trader's resting bids and armed pullback hunts.
- FUTURES: micros only (NQ→MNQ, ES→MES ...). Their stop/target wins; 25/50
  fills the gaps. Webull futures OPEN refuses until an exact GTC STOP_LOSS is
  placed and verified after its fill. No futures quote-driven target/ratchet
  is operational.
- INDEX MIRROR (9/13) — **OFF, activation blocked** until a broker-confirmed
  futures protective exit exists. The shadow records; `futures_mirror_daily.py`
  measures. Popup switch stays disabled until live exits are verified.
- THE POCKET (hidden on purpose): settings pocket_scalps_only, default OFF.

EXITS — THE DOCTRINE: THEIR TRIGGER → OUR ENTRY → THE RATCHET'S EXIT
(mechanics: reference/RATCHET.md)
- ENTRIES ONLY (G, 9/3; verified live 9/8): the bot follows room ENTRIES
  (and adds) only. EVERY room-side exit — trim, stop-move, "all out",
  "stopped out", "closed everything" — is logged "EXIT-IGNORED … entries
  only" and NEVER traded. The ratchet's resting stop at Webull is the ONLY
  exit (plus the bridge's own pullback stock-stop / underlying hard-stop).
  ONE EXCEPTION, and it is not a room exit: an EDIT that changes the CONTRACT
  we already bought (see ENTRIES). A bot SELL that traces to a room's own exit
  call is still a BUG: check bridge.py do_POST's EXIT-IGNORED gate,
  background.js's TRIM/STOPMOVE/CLOSE gate, and that settings
  execution.exit_policy is absent (default entries_only; "full" is the
  one-line way back).
- THE RATCHET (5/3/5 since 9/10, flat): born stop −5%; +3% moves the stop to
  breakeven; each further +5% locks another +5%. `ratchet_tiers.py` is the one
  implementation. Stops never loosen. Anti-clip is off. Won the 115-trade
  sweep; re-run the replays as the sample grows (reference/RATCHET.md).
- FUTURES RATCHET (9/9): derived from the trade's own risk — arm at ⅔ of the
  stop distance → BE, then a rung every ~27% of it.
- SWINGS: 14+ DTE = swing (auto-tagged). Their stock-level stop runs it; no
  level = wide −25%, re-armed every morning at 9:31 (option SELL orders are
  DAY-only at Webull). Scalps excluded on purpose.
- CLOSE path: every bot sell waits for FILLED — an ACCEPTED sell is never
  booked as filled. A CLOSE for a contract the book does not hold is REFUSED,
  never sent (his 12-lot scalps live in the same account).
- 0DTE: ETF options trade to 16:15; auto-exercise at $0.01 ITM — flatten
  before the close.

RESTARTS / SAFETY (mechanics: reference/OPERATIONS.md)
- State photo on every event; on boot everything is UNVERIFIED until the
  broker confirms; expired options = dead paper. Mid-market code updates
  self-apply at the first safe window. Resting stops at Webull guard every gap.
- POSTCHECK after every trade: book vs account, stop resting, quote bus
  fresh — logged as "POSTCHECK … PROBLEM" when they disagree.
- RULE: weekly signal-room-chat logs (replaces daily) (G, 9/15).
  `signal-room-chat week-of-<Mon>-to-<Sun>-<year> (discord|whop).txt`, week =
  Mon–Sun, each capture day under a `===== Mon Sep 14 2026 =====` header in
  date order, holding only lines no earlier day — or earlier week — already
  holds. A re-export replaces that day's block. New week → new file, by
  itself. `ds_logs.py` owns naming, blocks and de-dupe; readers ask it which
  days a file covers. Every daily (26 of them) is merged and zipped in
  `archive/`. Never hand-edit a week file.
- WEEKLY REPORTS (9/15): every report kind is ONE file per week per kind,
  same naming — `daily-reports/REPORT week-of-Sep-14-to-Sep-20-2026.md`,
  `daily-audits/AUDIT week-of-….txt` — a `===== Mon Sep 14 2026 =====` block
  per day, NEWEST DAY FIRST, a re-run replaces that day's block; the one csv
  kind is `daily-reports/CALLER-OUTCOMES.csv` with a `date` column.
  `reports.py` owns naming, blocks and the cache; writers call it, never
  mint a dated file. `daily-audits/latest.json` stays as is.
- APPEND, DON'T PILE (G, 9/15). New data goes INTO the one living file for
  its kind — the week file, the jsonl, the master csv, the archive folder —
  never a new dated file beside it. A writer that would create
  `<name>-<date>` must instead append a dated block/row to `<name>`. Rotated
  logs land in `archive/`. Finished experiments are zipped in `archive/`, not
  left as folders. Dated piles found later get merged the same way (see
  CONDENSE AND MERGE).
- REUSE, DON'T REBUILD (G, 9/15). A report whose inputs have not changed is handed over as it is — `reports.py status` decides, `reports/INDEX.json` is the memory. Rebuild only when it says stale. Never re-derive by reading logs what a report already states.
- ASK-MAP FIRST (G, 9/15). Every ask starts at ASK-MAP.md, then STATUS.json. Logs are read only when those two cannot answer. Checks recorded in STATUS.json.verified are trusted while their inputs are unchanged (VERIFY ONCE).
- DAILY SNIPER REPORT: bridge.py runs `daily_audit.py` once per weekday at
  16:40 ET. Order: broker_sync → replay → JS/Python tests + parser_gate →
  AUDIT block + latest.json → every report through `reports.build` → the
  BRIEF posted to Sniper HQ through the Fill Announcer's options webhook (how
  G gets the day; a failed brief never fails the audit) → STATUS.json LAST.
  Rules: broker-confirmed actuals override any simulation; RAW capture is
  retained and LIVE PARSER rows overlay it; relay duplicates count once;
  expired pullback waits are skips, not orders; the 15-minute Codex guard was
  deleted at G's request — do not recreate it. Findings become tested
  fixtures. The date argument is validated (`eastern.day_arg`).
- GIT: settings.json holds every key and is never committed. AUTO PUSH owns
  commits (every 45 s); never run git write commands from a sandbox. After
  suspicious loss check `git reflog` for a "reset:" before rebuilding.
- REPLACE, DON'T STACK (G, 9/9). When something changes — a rule, a value,
  a function, a setting, a room line, a doc — the new version takes the old
  one's place. Never leave the old beside the new: not commented out, not
  "superseded", not "legacy/old/deprecated", not a dead branch kept "just
  in case". One thing, one truth. History lives in git and HANDOFF-LOG.md,
  never in the working file. A fallback that must stay is a deliberate
  design decision, written as one — not leftovers. Applies to code,
  settings.json, rooms.txt, every .md, and this file.
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
- DATA-MAP.md is the index of what is INSIDE the data files — columns, log
  line types, row counts, traps, what each file can and cannot answer. Read
  it WITH INDEX.md at the start of every session. INDEX.md says what a file
  is; DATA-MAP.md says what is in it.
- RUN build_ledger.py IN EASTERN. Off his PC:
  `TZ=America/New_York python3 build_ledger.py` (9/15: a UTC shell wrote
  `opened` +4h and `closed` −4h on one row; caught and reverted).
- Compile-check everything touched (python3 -m py_compile / node --check).
  Extension changes → bump extension/manifest.json so a reload is provable.
  Never install the streaming SDK family (webullsdkcore) into the bridge's
  Python. Sandbox trading is RETIRED — paper is LOCAL (SIM tickets).
- Discord API is NOT an option (user-token automation = permanent ban risk
  to the account + paid subs; official bots need the server owner).
  Reaffirmed 9/9. Browser reads only.

ROOMS / TABS / READERS (mechanics: reference/ROOMS-TABS.md)
- rooms.txt = THE channel list (tabs + trading, one file). START HERE IS
  FULLY UNATTENDED (G, 9/9: "no input from me"). Between runs NOTHING opens
  rooms — a tab he closes by hand stays closed. The only inputs left are the
  ones no script may do: a Discord/Whop login if a profile is logged out, and
  Webull keys in the popup.
- Relay rooms: ZTRADEZ cut 9/9; OWLS all-alerts is active and RELAY UNWRAP
  re-books under the real trader; shabs + eli direct rooms retired 9/9.
- TAB HEALTH: never close a human-owned tab; active/voice tabs are protected;
  Chrome uses Profile 2 for Discord and Profile 6 for Whop.
- VOICE: ears transcribe always (Deepgram). Voice ENTRIES ON (9/2); voice
  EXITS irrelevant under entries-only. Typed copy of a voice fire = echo.
- Silence alarm: any room quiet 40 min in market hours → desktop
  notification.

FILL ANNOUNCER (announcer.py, read-only; mechanics: reference/OPERATIONS.md)
- Posts every fill, milestones, stop-outs and the scoreboard to G's Discord
  webhooks. NEITHER channel ever goes into rooms.txt.
- STATUS: PAUSED since 9/2 (announcer.stop = "stop", G: "get this app
  working 100% first"). Its board is computed FROM THE LEDGER (9/9). Its
  order hunt is paced — the 9/2 429 storm must never come back.

## DATA — one central file per family (9/9). THE APP READS ONLY THESE.
(what is inside each: DATA-MAP.md)
- BROKER RECORD → master_broker.csv. `broker_sync.py` — FIRST step of the
  16:40 audit — pulls the order history into ONE fixed file,
  Webull_Orders_auto.csv, OVERWRITING it every run (G, 9/10: "have one that
  overwrites" — no deletes, ever), and one balance row per day in
  `balance_daily.csv`. Never write dated Webull_Orders_<date> files (G, 9/9:
  never dated piles). Merge is REPLACE-DON'T-STACK per order.
- BROKER TRUTH: `master_broker.csv` is the account's own history. Do not
  quote P&L from book-priced rows when a broker row exists.
- BOT ATTRIBUTION: a caller name is candidate evidence until the entry is
  linked to a source alert and the trade to broker fills. `manual` denotes a
  manual exit; it does not disqualify a bot-origin entry.
- NO PAPER, ANYWHERE (9/9, G: "delete all paper trades data from the app, I
  don't want any more confusions"). account="paper" rows stay OUT of
  master_ledger.csv; account="unknown" is NOT paper. The bridge WARNS at boot
  if paper_trading is ever switched on.
- FILLS → master_ledger.csv (build_ledger.py, read via ledger.py). The
  broker's exit/P&L/state/account WIN over the book's belief. RECONCILIATION
  prints every run; a DRIFT line = something upstream lied. NOTHING reads
  days/*.json "table" or journal.csv for analysis anymore.
- ALERTS → master_alerts.csv (build_alerts.py; ledger.alerts()).
- PRICE TAPES → tape.py is the ONE registry (webull, tasty_greeks,
  tasty_quote, databento, missed, alert). Webull has NO historical option
  prices; the tapes are our own record. databento_backfill.py spends credit —
  never run its main() casually.
- HOLIDAYS / HOURS → market_hours.py owns the table (through 2027, UPDATE EVERY
  YEAR). holiday_table_flag() says "expiring" in the last 60 days and "stale"
  past it; STATUS.json "broke" and the brief's "What broke" both show it.
- POST-MORTEMS → master_postmortems.csv + postmortems/ (G 9/9: "analyze every
  single trade after exiting … be attentive to these"). His own hand trades
  are never graded.
- RN LEDGER → rn_ledger.csv (append-only).

## Broker facts (Webull OpenAPI — reference/OPTIONS-BROKER-REFERENCE.md first)
- Limits PER ENDPOINT per app key: option snapshot 60/min (20 symbols/
  call); Order Detail / Positions / Balance 2 per 2 s. 429 = throttle;
  417 = business rejection.
- No option streaming; fills ARE pushed. No MARKET orders on options.
  Combos = MASTER(LIMIT) + STOP_LOSS on SINGLE only. Option SELL orders are
  DAY-only → every resting stop dies at the close.
- Ticks: SPY/QQQ/IWM $0.01 always; Penny Program $0.01 <$3 / $0.05 ≥$3;
  else $0.05/$0.10.

## Operational truths (mechanics: reference/OPERATIONS.md)
- sniper-autopilot scheduled task: */30 ET. It never places/cancels orders or
  touches settings.json.
- THE PAGE (9/9, G: "make the popup an html page — it's super small now"):
  the SAME popup.html opened as a normal tab. One file, two sizes — never a
  second dashboard. Claude-in-Chrome CANNOT read the popup; if G reports a
  broken popup, the red line under the rooms is the diagnosis — ask for it.
- Multi-account: extras mirror LIVE entries 1:1 with own books/stops.

## SECOND MACHINE (planned 9/9 — G: "another account on a different computer
## for other subs"). Built default-off; nothing changes until PC2 exists.
- ONE bridge, ONE book, ONE rate budget: PC2 runs only Chrome + the extension
  and sends to THIS PC's bridge over the LAN. Never a second bridge on the
  same Webull account. Setup steps: reference/OPERATIONS.md.

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

## Where everything lives
ASK-MAP.md (ask → file) · STATUS.json · HANDOFF-LOG.md (all history) ·
INDEX.md (folder map) · DATA-MAP.md · ARCHITECTURE.md · MARKET-HOURS.md ·
reference/ (subsystem mechanics, broker reference, studies) ·
extension/rooms.txt · settings.json (keys, gitignored) · master_ledger.csv /
master_alerts.csv (truth) · days/ (per-day state) · daily-reports/ and
daily-audits/ (one file per week per kind) · reports/INDEX.json ·
project/ (Claude reference setup).
