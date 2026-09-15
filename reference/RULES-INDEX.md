# RULES-INDEX — every HANDOFF rule and the code that enforces it

Built 2026-09-15 by walking all 191 rules in HANDOFF.md (68 bullets) against the
code. Buckets: **ENFORCED** (a named code path does it), **UNBACKED** (the rule
asserted behaviour nothing implements — those lines were rewritten in HANDOFF the
same day), **DECISION-ONLY** (a choice not to build something, or an instruction to
G or to a session — no code expected), **DRIFTED** (code exists but does something
different: wrong threshold, wrong scope, disabled by a flag, unreachable).

Counts: **116 ENFORCED · 2 UNBACKED · 67 DECISION-ONLY · 6 DRIFTED** of 191.

Line numbers are as of 2026-09-15 after that day's dead-code deletions. A rule
whose evidence line has moved is still findable by the symbol named beside it —
the symbol is the claim, the number is only a shortcut.

The six DRIFTED rows are open decisions for G: fix the rule or fix the code.
Nothing in this file changes behaviour; it is a map.

| # | HANDOFF line | Rule | Bucket | Enforcing code / why not |
|---|---|---|---|---|
| 1 | 7 | A STATE, not a story: edit the rule that changed IN PLACE. REPLACE, DON'T STACK — the new rule takes the old one's place, never sits beside it | DECISION-ONLY | how to keep this file |
| 2 | 9 | ONE RULE, ONE LINE. Numbers, formats, procedures and rationale are MECHANICS: one reference doc per subsystem | DECISION-ONLY | how to keep this file |
| 3 | 9 | G's own wording stays verbatim | DECISION-ONLY | how to keep this file |
| 4 | 11 | Bump the one "Last updated:" line | DECISION-ONLY | how to keep this file |
| 5 | 11 | never prepend an essay | DECISION-ONLY | how to keep this file |
| 6 | 11 | Session notes, findings and post-mortems go to HANDOFF-LOG.md ("SESSION NOTES", newest first, dated) — that file grows forever, this one may not | DECISION-ONLY | how to keep this file |
| 7 | 14 | HARD CEILING: UNDER 14 KB. Past it you are writing history or mechanics: move it (history → HANDOFF-LOG.md, how-it-works → reference/) | DECISION-ONLY | how to keep this file |
| 8 | 16 | No handoff copies, dated handoffs or upload snapshots | DECISION-ONLY | how to keep this file |
| 9 | 16 | daily performance lives in `daily-reports/`. HANDOFF-LOG.md and the handoffs zipped in `archive/` are historical evidence, never current instructions | DECISION-ONLY | how to keep this file |
| 10 | 30 | G (giancuffaro230@gmail.com) maintains this code himself (9/13), trades options + futures live, real money, wants it CONDENSED. "Fix everything is default always" — bugs get fixed without asking, same day | DECISION-ONLY | instruction to the session |
| 11 | 30 | "Fix errors every day after journaling." | DECISION-ONLY | instruction to the session |
| 12 | 31 | Real-money actions are HIS ALONE: placing/canceling orders, flipping rooms LIVE, unlocking accounts, funding, questionnaires, accepting ToS, passwords | DECISION-ONLY | human-only actions — no code may do them |
| 13 | 32 | ACCOUNTS: `execution.mode=dryrun` does NOT disable per-room live orders | ENFORCED | bridge.py:4522 `_status` returns mode "per-room"; the per-order `live` flag from rooms.txt, not execution.mode, decides a real order (bridge.py:3392 live_order) |
| 14 | 32 | check buying power and positions AT THE BROKER before any claim | DECISION-ONLY | instruction to the session |
| 15 | 32 | futures_brokers.webull, Topstep/Tradovate and NinjaTrader stay OFF | DRIFTED | settings futures_brokers.webull = true AND bridge.py:273 futures_on() returns True unconditionally; bridge.py:3408 use_webull -> webull_futures.execute. Topstep/NT/Tradovate ARE off. |
| 16 | 33 | COEXISTENCE: Market Sniper (port 8000) shares the account and the rate budget — its positions are visible, NEVER stop-managed or sold | ENFORCED | positions.py:1251 adopt(): never arms the watchdog, skips cash-settled index names and anything over adopt_max_qty=3 |
| 17 | 34 | NORTH STAR (G, 9/11): every day leaves a complete auditable alert funnel and append-only data to benchmark caller vs bot vs broker truth | DECISION-ONLY | the north star, not a mechanism |
| 18 | 34 | a later high is never a caller exit | ENFORCED | reference/caller_profile.py:24 and :677; daily_report.py:355 |
| 19 | 35 | AI READS ARE PROPOSALS: parser and guards judge them, AI confidence authorizes nothing | ENFORCED | ai_reader.py:262 — every AI read goes back through parser + guards |
| 20 | 35 | "" or a range is NO CALL — not a crash, not an order | ENFORCED | ai_reader returns no action on an empty/range price; bridge refuses without a strike (bridge.py:5872 "that wasn't a readable order") |
| 21 | 35 | department output is advisory | ENFORCED | departments.py:1-2 and SYSTEM prompt — reviews are read-only, nothing is executed |
| 22 | 36 | CALLER IDENTITY IS CANDIDATE EVIDENCE: no win rate until attribution exists, a new account never gets an execution key, ID-less rows stay unavailable — re-grab, never infer | ENFORCED | trade_identity.py + caller_ledger.py; bridge.py:3238 caller switch keyed on a named caller |
| 23 | 37 | Claude exports and project/context/ are reference only | DECISION-ONLY | reference-only material |
| 24 | 42 | PRICE: caller's price or better | ENFORCED | pullback.py:81; bridge limit = the caller's price |
| 25 | 42 | pullbacks cross the ask | ENFORCED | webull_options.py:2308 marketable buffer — a pullback entry pays the ask |
| 26 | 42 | one contract per entry | ENFORCED | bridge.py:3573 qty = 1 when strategy.enabled (settings: true) |
| 27 | 42 | RN PULLBACK is ON and global | ENFORCED | extension/background.js:1081 rn_pullback_all default on, global |
| 28 | 42 | THE LEVEL STAYS $1 (SETTLED 9/9), never re-opened on a feeling | ENFORCED | pullback.py:51 round_target() rounds to the whole dollar |
| 29 | 43 | ONE SWITCH PER ROOM (G, 9/9): ON = tab + read + trades LIVE | ENFORCED | bridge.py:327 read_rooms state on/off/lapsed; the room's own live flag arms real orders |
| 30 | 43 | OFF = nothing | ENFORCED | bridge.py:3343 a non-live room with paper off is REFUSED, never faked |
| 31 | 43 | LAPSED = sub ran out | ENFORCED | bridge.py:321 ROOM_STATES; bridge.py:735 lapsed rooms are reported, never traded |
| 32 | 43 | No paper state | ENFORCED | settings execution.webull.paper_trading=false and the in-house sim is deleted (bridge.py:3343) |
| 33 | 43 | A TAB CLOSED BY HAND IS NOT A BENCH | ENFORCED | extension/background.js:833 roomSchedule closes only; nothing reopens a hand-closed tab |
| 34 | 43 | benched rooms stay | ENFORCED | extension/background.js:684 state!=="on" -> no tab, the line stays in rooms.txt |
| 35 | 44 | TABS (9/10): the reaper closes only `_OURS`, never a human's | ENFORCED | extension/background.js:2617 _OURS; the reaper may only close a tab it opened |
| 36 | 44 | only START HERE, the popup switch and whopSelfHeal() open one | ENFORCED | extension/background.js:884 "NOTHING ABOVE OPENS A TAB ANY MORE" — honourOpenRoomsRequest, setRoomState, whopSelfHeal, probeOne |
| 37 | 44 | "No Access" → `lapsed` + close | ENFORCED | extension/background.js:457 No Access -> lapsed + close |
| 38 | 44 | the last tab stays | ENFORCED | extension/background.js:_keepWindowAlive — a close never takes the window's last tab |
| 39 | 45 | ROOM RULES = rooms.txt 6th field (popup pills), not settings.json | ENFORCED | bridge.py:327 read_rooms 6th field; settings.json holds no room rules |
| 40 | 45 | `spx` DELETED 9/10. HOURS 9:15–16:30 ET unless `always` | ENFORCED | no room carries spx and the flag is gone from bridge/popup (9/15); ROOM_HOURS 9:15-16:30 at extension/background.js:814, `always` exempt |
| 41 | 45 | hand-closed tabs stay closed | ENFORCED | extension/background.js:833 — closing happens only at the 4:30 boundary |
| 42 | 45 | CHANNELS: callers inside their verified room, win rate needs evidence, no Callers tab (G) | ENFORCED | extension/popup.js renderRoomCallers() paints callers INSIDE each room row; there is no Callers tab |
| 43 | 46 | STRIKES: max 1 OTM, deeper snaps to the first rung | DRIFTED | bridge.py:1887 _no_otm_translate exists but returns at :1911 unless execution.translate_strikes is true — that key is NOT in settings.json, so the caller's strike is bought however deep OTM |
| 44 | 46 | 3-ITM for SPY/QQQ/Mag7 0DTE | UNBACKED | REWRITTEN 9/15 — nothing anywhere implements a 3-ITM rule; bridge.py:1880 records that the 8/19 "3 strikes ITM" rule was replaced on 8/20. Clause deleted from HANDOFF. |
| 45 | 46 | ADD buys the held strike | DRIFTED | the only code that rewrites an ADD to the held strike is bridge.py:1921, inside the disabled _no_otm_translate |
| 46 | 47 | "ADDED <full contract>" you are not in = an OPEN entry | ENFORCED | extension/parser.js:2632 ADD on a named contract |
| 47 | 47 | a bare "added to SPY" refuses | ENFORCED | extension/parser.js:306 — a bare "added to SPY" carries no contract and never becomes an order |
| 48 | 47 | NO SPX→SPY (G, 9/10: "do not translate any SPX to SPY") | ENFORCED | extension/parser.js:1288-1322 — the SPX->SPY retarget is deleted, not disabled |
| 49 | 47 | index entries are HELD until execution.index_broker is set | ENFORCED | extension/parser.js:1318 — held unless cfg.index_broker names a broker |
| 50 | 48 | WORD ORDER: any order, `bare` rooms only | ENFORCED | bridge.py:452 entry_no_verb_channels from the rooms.txt `bare` flag |
| 51 | 48 | TWO CONTRACTS = TWO ORDERS (9/10): one each, own stop and ratchet, same ticker | ENFORCED | extension/parser.js:817 extraStrikes — same ticker/side/expiry, one order each |
| 52 | 48 | call+put refuses the line | DRIFTED | extension/parser.js:811 — a call+put pair is "left alone": the PUT is not added as a sibling, but the CALL still fires. The rule says the line is refused; nothing refuses it. |
| 53 | 49 | EXPIRY, one place: NDTE = N CALENDAR days rolling BACK, never past today | ENFORCED | build_ledger.py:147 + the parser's NDTE reader |
| 54 | 49 | NO DATE = 0DTE (G, 9/10), the LISTING ASKED never assumed, clues win first | ENFORCED | bridge.py:4044 _dateless_expiry asks the listing; today wins when listed |
| 55 | 49 | "FRIDAY WEEKLIES ONLY" is DEAD | ENFORCED | bridge.py:4050 and :5983 record the Friday-weeklies assumption as retired |
| 56 | 50 | CONTRACT MUST EXIST (9/15) AND BE IN PRICE BAND (9/14): siblings listed → REFUSE | ENFORCED | bridge.py:4154 _verify_listed -> BAD-CONTRACT |
| 57 | 50 | nothing listed → THROUGH + LISTING line | ENFORCED | bridge.py:4233 LISTING line when nothing answers |
| 58 | 50 | fails open, a guard never a gate | ENFORCED | bridge.py:4216 "letting it through" — fails open |
| 59 | 51 | GUARDS: SPREAD/THIN refuse wide or illiquid | ENFORCED | webull_options.py:2337 spread guard; liquidity.py:137 check() volume floor |
| 60 | 51 | nothing older than 3 min fires | DRIFTED | extension/guards.js:22 max_message_age_seconds = 20 (Discord) and :160 a 90s window for Whop. Nothing uses 3 minutes. |
| 61 | 51 | negations hard-veto | ENFORCED | extension/parser.js negation veto before any action is set |
| 62 | 51 | DEDUPE ends at ONE average-down ADD under what was PAID | ENFORCED | bridge.py:2818 dedupe on coid; the average-down ADD is capped at one under what was paid |
| 63 | 51 | identity = caller+symbol+strike+side+expiry | ENFORCED | bridge.py tkey() = caller+symbol+strike+side+expiry |
| 64 | 52 | AN EDIT IS A REPLACEMENT, NOT A SECOND TRADE (9/14): it kills the earlier hunt and its bid | ENFORCED | alert_revision.py:150 reads_as_edit + bridge.py:2617 kills the earlier hunt and bid |
| 65 | 52 | two DIFFERENT message ids are two calls | ENFORCED | alert_revision.py:104 message_id — two ids are two calls |
| 66 | 53 | IF THE CORRECTED CONTRACT ALREADY FILLED (9/15, G: "if in profit keep the ratchet and set the stop to breakeven, if it's a losing trade, close it automatically"), on CURRENT BID vs fill | ENFORCED | bridge.py:2617-2670 — on CURRENT BID vs fill: green keeps the ratchet and moves the stop to breakeven, red closes |
| 67 | 53 | THE ONE EXCEPTION TO ENTRIES-ONLY, not a room exit | ENFORCED | same path; it is the only bot sell that is not the ratchet |
| 68 | 54 | RETRACTION ("not ready / scratch that / cancel / disregard / hold off / nevermind") pulls that trader's bids and armed hunts | ENFORCED | extension/parser.js:1716 RETRACT regex; bridge.py:3068 pulls the bids; positions.py:679; pullback.py:150 kills armed hunts. (Bare "cancel" alone is not a trigger — the regex needs "cancel that".) |
| 69 | 55 | FUTURES: micros only | ENFORCED | webull_futures.py sizes at one micro and refuses rather than guessing |
| 70 | 55 | their stop/target wins | ENFORCED | bridge.py futures path uses their stop/target |
| 71 | 55 | a Webull futures OPEN refuses until an exact GTC STOP_LOSS is verified after its fill | ENFORCED | webull_futures.py:484 submit-then-prove the exact working STOP_LOSS/GTC; bridge.py:4557 protective_entries_ready |
| 72 | 55 | INDEX MIRROR (9/13) OFF until a broker-confirmed futures exit exists | ENFORCED | settings execution.index_mirror.enabled = false; index_mirror.py keeps the shadow record either way |
| 73 | 55 | THE POCKET default OFF | ENFORCED | bridge.py:3114 pocket_scalps_only — the key is absent from settings.json, so it is off |
| 74 | 58 | NO DAILY LOSS STOP (G, 9/14: "No | DECISION-ONLY | a standing decision not to build one |
| 75 | 58 | We are not gonna do a daily daily stop limit | DECISION-ONLY | same rule, G's words |
| 76 | 58 | We're not.") | DECISION-ONLY | same rule, G's words |
| 77 | 58 | Never propose one, never wire one | DECISION-ONLY | never propose one — an instruction to the session |
| 78 | 58 | The per-trade born stop is the only cap | ENFORCED | ratchet_tiers.py born stop from settings strategy.stop_loss_pct = 5 |
| 79 | 59 | ENTRIES ONLY (G, 9/3): the bot follows room ENTRIES (and adds) only | ENFORCED | bridge.py:5899 EXIT-IGNORED |
| 80 | 59 | EVERY room-side exit — trim, stop-move, "all out", "stopped out", "closed everything" — is logged "EXIT-IGNORED … entries only" and NEVER traded | ENFORCED | bridge.py:5891 gates TRIM/CLOSE/STOPMOVE from any room poster; extension/parser.js:1579 the same gate upstream |
| 81 | 59 | The ratchet's resting stop at Webull is the ONLY exit | ENFORCED | positions.py:2454 _arm_stop rests the stop at the broker |
| 82 | 59 | A bot SELL tracing to a room's exit call is a BUG | DECISION-ONLY | a statement about what a bug looks like |
| 83 | 60 | THE RATCHET (5/3/5 since 9/10, flat): born −5%, +3% → breakeven, each +5% locks +5% | ENFORCED | ratchet_tiers.py:91 TIERS = (3.0 arm, 0.0 first lock, 5.0 step); settings strategy.stop_loss_pct = 5 |
| 84 | 60 | ratchet_tiers.py is the one implementation | ENFORCED | ratchet_tiers.py is imported by positions.py:50 and by every replay |
| 85 | 60 | stops never loosen | ENFORCED | ratchet_tiers.py:158 ratchet_stop_price returns None when the move is not an improvement |
| 86 | 60 | anti-clip off | ENFORCED | bridge.py:1050 BOOK.anticlip = strategy.anticlip, absent from settings.json -> False |
| 87 | 61 | FUTURES RATCHET (9/9) comes from the trade's own risk, never a fixed number | ENFORCED | ratchet_tiers.py:260 futures_stop_points derives from the trade's own risk |
| 88 | 61 | SWINGS (14+ DTE, auto-tagged): their stock stop runs it | ENFORCED | positions.py:706 and :1876 — a swing with their_stop runs on it |
| 89 | 61 | no level = wide −25% re-armed at 9:31 | ENFORCED | positions.py:2541 _pct = 25.0 for a swing with no level; bridge.py:6640 re-arm at minute 571 (9:31) |
| 90 | 61 | scalps excluded | ENFORCED | positions.py:1777 docstring — swings only, scalps never live past a close |
| 91 | 62 | CLOSE: every bot sell waits for FILLED | ENFORCED | positions.py:3046 _sell_confirmed |
| 92 | 62 | a CLOSE the book does not hold is REFUSED, never sent | ENFORCED | bridge.py:2046 plan_exit refuses a CLOSE the book does not hold |
| 93 | 63 | NO PRE-CLOSE FLATTEN (G, 9/15, told the risk and chose it): the bot does NOT close 0DTE before the bell | DECISION-ONLY | a decision NOT to build the flatten (G, 9/15, told the risk) |
| 94 | 63 | A 0DTE left $0.01 ITM auto-exercises into 100 shares | DECISION-ONLY | a broker fact |
| 95 | 63 | that is HIS risk to run, HIS to close by hand | DECISION-ONLY | his risk to run |
| 96 | 63 | Never re-add an auto-flatten | DECISION-ONLY | an instruction to the session |
| 97 | 63 | ETFs trade to 16:15 | ENFORCED | market_hours.py OPTIONS_CLOSE_LATE = 16:15 |
| 98 | 66 | BOOT: all UNVERIFIED until the broker confirms | ENFORCED | bridge.py boot marks the book UNVERIFIED until the broker answers |
| 99 | 66 | expired options = dead paper | ENFORCED | positions.py:1159 purge_expired, called at bridge.py:6660 |
| 100 | 66 | updates apply at the first safe window | ENFORCED | bridge.py:6582 safe-window restart (weekday 09:20-16:15, nothing in flight, checked twice 20s apart) |
| 101 | 66 | POSTCHECK logs a PROBLEM when book, stop and quote bus disagree | ENFORCED | bridge.py:6772 POSTCHECK |
| 102 | 67 | RULE: weekly signal-room-chat logs (replaces daily) (G, 9/15). ds_logs.py owns naming, blocks and de-dupe | ENFORCED | ds_logs.py:80 weekly_name + :249 merge_day + :191 _dedupe_block |
| 103 | 67 | never hand-edit a week file | DECISION-ONLY | an instruction to the session |
| 104 | 68 | WEEKLY REPORTS (9/15): ONE file per week per kind, newest day first | ENFORCED | reports.py:203 path() -> one weekly file per kind, newest day first |
| 105 | 68 | reports.py owns it, writers never mint a dated file | ENFORCED | reports.py:216 write_day is the only writer |
| 106 | 69 | APPEND, DON'T PILE (G, 9/15) | ENFORCED | reports.py + ds_logs.py + departments.py:20 STEMS — one living file per kind |
| 107 | 69 | New data goes INTO the one living file for its kind, never a new dated file beside it | ENFORCED | same |
| 108 | 69 | rotated logs and finished experiments zip to `archive/` | DECISION-ONLY | zipping to archive/ is a human action |
| 109 | 70 | REUSE, DON'T REBUILD (G, 9/15) | ENFORCED | reports.py:407 check() decides CURRENT vs STALE |
| 110 | 70 | A report whose inputs have not changed is handed over as it is (`reports.py status` decides, `reports/INDEX.json` is the memory) | ENFORCED | reports.py:385 load_index / reports/INDEX.json |
| 111 | 70 | Never re-derive from logs what a report already states | DECISION-ONLY | an instruction to the session |
| 112 | 71 | ASK-MAP FIRST (G, 9/15) | DECISION-ONLY | an instruction to the session |
| 113 | 71 | Every ask starts at ASK-MAP.md, then STATUS.json | DECISION-ONLY | an instruction to the session |
| 114 | 71 | logs only when those two cannot answer | DECISION-ONLY | an instruction to the session |
| 115 | 71 | STATUS.json.verified is trusted while its inputs are unchanged (VERIFY ONCE) | ENFORCED | status_json.py writes the `verified` block with its inputs |
| 116 | 72 | THE 16:40 AUDIT: broker actuals override any simulation | ENFORCED | build_ledger.py — broker rows override the book |
| 117 | 72 | RAW capture is kept, LIVE PARSER rows overlay it | ENFORCED | build_alerts.py reads trades.log RAW and overlays LIVE PARSER rows |
| 118 | 72 | relay duplicates count once | ENFORCED | build_alerts.py:699 duplicate-guard classification |
| 119 | 72 | expired pullback waits are skips | ENFORCED | build_alerts.py:445 RE_PB_SKIP — an expired pullback wait is a skip |
| 120 | 72 | never recreate the 15-minute Codex guard | DECISION-ONLY | an instruction to the session |
| 121 | 73 | GIT: settings.json holds every key and is never committed | ENFORCED | .gitignore carries settings.json |
| 122 | 73 | AUTO PUSH owns commits | ENFORCED | AUTO PUSH.bat is the only committer |
| 123 | 73 | never run git write commands from a sandbox | DECISION-ONLY | an instruction to the session |
| 124 | 74 | REPLACE, DON'T STACK (G, 9/9) | DECISION-ONLY | house rule |
| 125 | 74 | When anything changes — a rule, a value, a function, a setting, a room line, a doc — the new version takes the old one's place | DECISION-ONLY | house rule |
| 126 | 74 | never left beside it, not commented out, not "superseded", not "legacy", not a dead branch "just in case" | DECISION-ONLY | house rule |
| 127 | 74 | One thing, one truth | DECISION-ONLY | house rule |
| 128 | 74 | history lives in git and HANDOFF-LOG.md | DECISION-ONLY | house rule |
| 129 | 74 | A fallback that stays is a deliberate design decision | DECISION-ONLY | house rule |
| 130 | 75 | CONDENSE AND MERGE (G, 9/11) | DECISION-ONLY | house rule |
| 131 | 75 | Sibling data belongs in ONE file: merge the duplicate into the existing home and delete the copy, but only when it cannot break a reader (test: DATA-MAP.md) | DECISION-ONLY | house rule |
| 132 | 75 | Records that cannot be re-derived — tapes, telemetry, days/ — are APPENDED to, never rewritten | DECISION-ONLY | house rule — tapes/telemetry/days are appended to |
| 133 | 76 | READ DATA-MAP.md WITH INDEX.md every session (INDEX = what a file IS, DATA-MAP = what is IN it) | DECISION-ONLY | an instruction to the session |
| 134 | 76 | RUN build_ledger.py IN EASTERN. COMPILE-CHECK everything touched | DECISION-ONLY | an instruction to the session |
| 135 | 76 | bump extension/manifest.json on extension changes | DECISION-ONLY | an instruction to the session |
| 136 | 76 | never install webullsdkcore into the bridge's Python | DECISION-ONLY | an instruction to the session |
| 137 | 76 | sandbox is RETIRED, paper is LOCAL (SIM) | UNBACKED | REWRITTEN 9/15 — there is no local sim: it was deleted and bridge.py:3343 REFUSES a non-live order instead of faking one, with execution.webull.paper_trading = false. HANDOFF now says so. |
| 138 | 77 | DISCORD API IS NOT AN OPTION (9/9): user-token automation risks a permanent ban on the account and the subs | DECISION-ONLY | a decision not to use the Discord API |
| 139 | 77 | official bots need the owner | DECISION-ONLY | same |
| 140 | 77 | Browser reads only | DECISION-ONLY | same |
| 141 | 78 | FILL ANNOUNCER REMOVED (G, 9/15): reinstall when the bot is profitable | ENFORCED | no announcer module anywhere in the repo (grep: only the CLEANUP bat and daily_brief's webhook read) |
| 142 | 78 | The daily BRIEF still posts to Sniper HQ through the announcer webhook URL in settings.json — that key stays | ENFORCED | daily_brief.py:700 posts the BRIEF through settings announcer.webhook_url |
| 143 | 81 | rooms.txt = THE channel list (tabs + trading, one file) | ENFORCED | extension/rooms.txt is the one list; bridge.py:327 reads it |
| 144 | 81 | START HERE IS FULLY UNATTENDED (G, 9/9) | ENFORCED | START HERE.bat runs unattended; extension/background.js honourOpenRoomsRequest |
| 145 | 81 | between runs NOTHING opens rooms | ENFORCED | extension/background.js:884 — the three openers only |
| 146 | 81 | the only manual inputs are a Discord/Whop login and Webull keys | DECISION-ONLY | the two manual inputs are human actions |
| 147 | 82 | Relays: OWLS all-alerts active, RELAY UNWRAP re-books under the real trader | ENFORCED | extension/background.js:4063 RELAY UNWRAP re-books under the real trader |
| 148 | 82 | ZTRADEZ, shabs, eli retired 9/9. Never close a human tab | ENFORCED | rooms.txt carries the retired rooms as off; the reaper only closes _OURS |
| 149 | 82 | Profile 2 = Discord, Profile 6 = Whop | ENFORCED | whop-profile.txt / chrome-profile.txt pin the folders; extension/background.js lane assignment |
| 150 | 83 | VOICE: ears always transcribe (Deepgram) | ENFORCED | extension/offscreen.js:61 Deepgram, always on |
| 151 | 83 | voice ENTRIES ON (9/2), exits irrelevant | ENFORCED | extension/background.js voice entries fire, exits are ignored under entries-only |
| 152 | 83 | a typed copy of a voice fire is an echo | ENFORCED | extension/background.js echo suppression on a typed copy of a voice fire |
| 153 | 86 | BROKER RECORD → master_broker.csv | ENFORCED | master_broker.csv written by broker_sync.py:19 |
| 154 | 86 | the Webull export is ONE file OVERWRITTEN every run, never dated piles | ENFORCED | broker_sync.py OVERWRITES Webull_Orders_auto.csv every run |
| 155 | 86 | one balance row a day in balance_daily.csv | ENFORCED | broker_sync.py:18 one balance row a day in balance_daily.csv |
| 156 | 87 | FILLS → master_ledger.csv | ENFORCED | build_ledger.py -> master_ledger.csv; ledger.py is the reader |
| 157 | 87 | the broker's exit/P&L/state/account WIN over the book, a DRIFT line means something upstream lied, and nothing reads days/*.json or journal.csv for analysis | DRIFTED | the broker-wins half is enforced (build_ledger.py:1155 DRIFT). The "nothing reads journal.csv" half is not: bridge.py:1661 still WRITES journal.csv and caller_report.py:66 still READS it for analysis. |
| 158 | 88 | ALERTS → master_alerts.csv | ENFORCED | build_alerts.py -> master_alerts.csv |
| 159 | 88 | RN LEDGER → rn_ledger.csv (append-only) | ENFORCED | pullback.py:83 appends to rn_ledger.csv |
| 160 | 88 | HOLIDAYS/HOURS → market_hours.py owns the table — UPDATE EVERY YEAR. POST-MORTEMS → master_postmortems.csv + postmortems/ | ENFORCED | market_hours.py owns FULL_CLOSE/HALF_DAY; holiday_table_flag() warns before the table expires |
| 161 | 88 | his own hand trades are never graded | ENFORCED | postmortem.py:452 skips rows whose owner is his own hand |
| 162 | 89 | PRICE TAPES → tape.py is the ONE registry | ENFORCED | tape.py is the one registry |
| 163 | 89 | Webull has NO historical option prices | DECISION-ONLY | a broker fact |
| 164 | 89 | databento_backfill.py spends credit — never run its main() casually | DECISION-ONLY | an instruction to the session |
| 165 | 90 | NO PAPER, ANYWHERE (9/9, G: "delete all paper trades data from the app, I don't want any more confusions"): account="paper" rows stay OUT of master_ledger.csv, account="unknown" is NOT paper | ENFORCED | build_ledger.py:848 keeps account="paper" rows out |
| 166 | 91 | BOT ATTRIBUTION: a caller name is candidate evidence until the entry links to an alert and the trade to broker fills | ENFORCED | trade_identity.py + entry_attribution.py |
| 167 | 91 | never quote P&L from a book-priced row when a broker row exists | ENFORCED | build_ledger.py — a broker row beats a book price |
| 168 | 94 | NO MARKET ORDERS ON OPTIONS | ENFORCED | webull_options.py:623 — no market orders on options |
| 169 | 94 | combos = MASTER(LIMIT) + STOP_LOSS on SINGLE only | ENFORCED | webull_options.py combo = MASTER(LIMIT) + STOP_LOSS on SINGLE |
| 170 | 94 | Option SELL orders are DAY-only → every resting stop dies at the close | ENFORCED | option sells are DAY-only, which is why positions.py:1777 rearm_overnight_stops exists |
| 171 | 95 | Rate limits are PER ENDPOINT per app key, shared with Market Sniper | ENFORCED | webull_options.py rate rules are per endpoint |
| 172 | 95 | 429 = throttle, 417 = business rejection | ENFORCED | webull_options.py:1277 throttled=stop on 429; 417 is a business rejection |
| 173 | 95 | No option streaming | DECISION-ONLY | a broker fact |
| 174 | 95 | fills ARE pushed | DECISION-ONLY | a broker fact |
| 175 | 96 | Ticks are symbol-aware | ENFORCED | webull_options.py:373 + ratchet_tiers.py:99 tick_size |
| 176 | 96 | never invent one | DECISION-ONLY | an instruction to the session |
| 177 | 97 | sniper-autopilot (*/30 ET) never places or cancels orders, never touches settings.json | DECISION-ONLY | an instruction to the sniper-autopilot agent, not a code path |
| 178 | 98 | THE PAGE is the SAME popup.html opened as a tab — never a second dashboard | ENFORCED | extension/popup.js:1 PAGE MODE, extension/background.js:843 popup.html?page=1 |
| 179 | 98 | Claude-in-Chrome CANNOT read it | DECISION-ONLY | a fact about Claude-in-Chrome |
| 180 | 98 | the red line under the rooms is the diagnosis — ask for it | DECISION-ONLY | an instruction to the session |
| 181 | 99 | Multi-account: extras mirror LIVE entries 1:1, own books/stops | ENFORCED | bridge.py webull_extra_accounts mirror LIVE entries with their own books/stops |
| 182 | 99 | SECOND MACHINE (planned 9/9, default-off until PC2 exists): ONE bridge, ONE book, ONE rate budget — never a second bridge on the same Webull account | DECISION-ONLY | a decision, default-off until PC2 exists |
| 183 | 102 | In Claude: use project/PROJECT-INSTRUCTIONS.md as the Project instructions | DECISION-ONLY | pending external setup |
| 184 | 102 | remove the old uploaded handoffs (local cleanup does not touch uploads) | DECISION-ONLY | pending external setup |
| 185 | 103 | Market Sniper: apply HANDOFF-RATCHET-2026-09-09.md (options 5→2 rung, futures decouple) — G's call whether Claude does it or he does | DECISION-ONLY | pending external setup |
| 186 | 104 | NinjaTrader ATM template "SNIPER": stop 100 ticks / target 200 (=25/50 MNQ pts), qty 1 — create in NT8, type SNIPER in the popup | DECISION-ONLY | pending external setup |
| 187 | 105 | Close any old parked Whop tabs (Chrome flags note: reference/OPERATIONS.md) | DECISION-ONLY | pending external setup |
| 188 | 106 | CHROME BEFORE 9:15: rooms open at 9:15 only if Chrome + the extension are already up | DECISION-ONLY | pending external setup |
| 189 | 106 | Run START HERE, or schedule it, by 9:00 on trading days | DECISION-ONLY | pending external setup |
| 190 | 109 | G'S CALL, nothing changes until he says: PULLBACK STOCK TARGET vs THE RATCHET (9/10) — a pullback entry also closes at a fixed stock target, a second exit beside the ratchet. (a) delete it (b) keep it | DECISION-ONLY | an open decision for G |
| 191 | 112 | Also open: futures fills → the ledger · telemetry has no room/caller · the Deepgram key may be one char short · the first overnight swing stop is unconfirmed · a room's NAMED exit misses adopted positions · bridge.log has no rotation · multi-account "L" orphans · Topstep/Webull futures off | DECISION-ONLY | the open watch list |

