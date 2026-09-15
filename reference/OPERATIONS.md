# OPERATIONS — mechanics

The mechanics behind the rules in HANDOFF.md, moved here 9/15 so HANDOFF stays a
rules core (under 30 KB). The rule is in HANDOFF; the HOW, the numbers and the
history-with-numbers are here. REPLACE, DON'T STACK applies: edit in place.

Restarts, POSTCHECK, the 16:40 audit, git/AUTO PUSH, the autopilot,
departments, the AI readers and keys, caller research, the second machine.
The report cache and STATUS.json are documented in reports.py / status_json.py and
ASK-MAP.md.

## Restarts and safety

- State photo on every event. On boot: expired options = dead paper;
  everything else UNVERIFIED until the broker confirms (then watchdog +
  stop arm); gone = closed "at a price I never saw". Mid-market code
  updates self-apply at the first safe window (no bids/hunts/closes in flight);
  a dispatch gate closes the final check-to-restart race;
  checkBuild reloads extension builds promptly. If Windows execv fails, the
  bridge exits only when its existing watchdog is confirmed running; START
  HERE also detects newer local Python files when Git reports no new revision. A copy with no explicit
  Discord/Whop lane only checks for its own build update and otherwise stays
  inert: it does not read rooms, manage tabs, or export stale data over a live
  lane. Resting stops at Webull guard every gap.
- POSTCHECK after every trade: book vs account, stop resting, quote bus
  fresh — logged as "POSTCHECK … PROBLEM" when they disagree.

## The daily audit and git (as they were written before reports.py, 9/15 — the
order is now broker_sync → replay → tests + gate → AUDIT block → reports.build for
every kind → brief → STATUS.json; outputs are weekly files, see reports.py)

- DAILY SNIPER REPORT: bridge.py runs `daily_audit.py` once per weekday at
  16:40 ET, after the 16:30 export/tab sweep. Order: `broker_sync.py` pulls
  the Webull export; the day's Discord and Whop inputs replay with each room's
  production grammar; `parser_gate.js` compares parser.js, rooms.txt and
  optionable.txt over every retained live message (AUTO PUSH runs that gate
  before any such rule ships and blocks invented symbols or expiry shifts);
  every JS/Python test runs; `daily-audits/AUDIT-<date>.txt` + `latest.json`
  are written; unresolved items are queued. Into `daily-reports/`: the Daily
  Sniper Report (coverage, decisions, skips, fills, P&L, postmortems),
  `RATCHET-COMPARE-<date>.md` (live 5/3/5 vs fixed -5% born stop over
  exact-contract quote paths, coverage stated, never extrapolated),
  `CALLER-OUTCOMES-<date>.md/.csv` (caller entry, every trim and full exit;
  caller P&L only when entry and exit pair with contemporaneous quotes;
  partials never become full results; a posted price within 2% of that
  minute's `und` is a STOCK quote -> entry "unavailable (stock price
  posted)", dollars out of every total), `CALLER-VS-RATCHET-<date>.md` (5/3/5
  from caller entry over `tape.py`). LAST: `daily_brief.py` posts the
  one-screen `BRIEF-<date>.md` to Sniper HQ through the webhook URL kept at
  `settings.json -> announcer.webhook_url` (the Fill Announcer is gone; the
  KEY stays and is the brief's only way out) — that post is how G gets the
  day; a failed brief never
  fails the audit. Rules: broker-confirmed actuals override any simulation;
  RAW capture is retained and LIVE PARSER rows overlay it; relay duplicates
  count once; expired pullback waits are skips, not orders; the 15-minute
  Codex guard was deleted at G's request — do not recreate it. Findings
  become tested fixtures. The date argument is validated (`eastern.day_arg`):
  a `--help` once became `AUDIT---help.txt` and four more like it.
- GIT: settings.json holds every key and is never committed. AUTO PUSH uses
  a live-owner PID lock, commits every 45 s and retries pushes; it never deletes
  Git locks or rebases. Runtime files remain local. After suspicious loss check
  `git reflog` for a "reset:" before rebuilding.

## build_ledger and time zones

- RUN build_ledger.py IN EASTERN. Its clocks come from the machine's local
  timezone, so a rebuild from a UTC shell rewrites `opened` four hours forward
  while `closed`, parsed from a stored string, moves the other way — one row,
  two clocks (9/15, caught and reverted from backups/). Off his PC:
  `TZ=America/New_York python3 build_ledger.py`.

## Autopilot, launchers, logs

- sniper-autopilot scheduled task: */30 ET — preflight ~9:30, sync watch
  in market hours, close-out ~16:30 (the old daily-journal-and-fix 16:45
  task is PAUSED, folded into Mode C). It never places/cancels orders or
  touches settings.json.

- Multi-account: extras mirror LIVE entries 1:1 with own books/stops.
- START HERE.bat saves+pushes before its reset; RESTART BRIDGE.bat
  pre-flights and warns. Logs: trades.log (the story), bridge.log (raw,
  20 MB, no rotation yet), webull_api.log, deadman.log.

## Readers, keys, departments, AI measurement

- PROVIDER KEYS: the Keys pane saves OpenAI, Gemini and Perplexity under settings.json ai_provider_keys; saved fields hide behind Replace key, status returns presence flags only. OpenAI/Gemini feed the observer AND both live readers; Perplexity stored inactive; DeepSeek removed (G); Anthropic kept but billing-blocked. Saved-key PRESENCE is not a probe RESULT: billing, rate-limit, auth, access and connection failures carry distinct labels.
- DEPARTMENTS: enabled. Bridge audit loop calls health_tick every five minutes; extension maintenance publishes Discord/Whop lane heartbeat and reader issues. GPT-5.4 mini analyzes changed issues (12/day); Astra escalates multi-issue incidents (2/day), reviews selected reader disagreements (20/day) and analyzes the daily reports after the 16:40 audit (1/day). Output is advisory, appended to department-reports/<role>.jsonl + .md (one living pair per department, newest first in the .md), never code or orders. Context snapshots persist at most once/minute.
- READER/UI: observer retains 50 prior messages within 72 hours; fresh-post admission 15 minutes, same-caller field borrowing five minutes. AI observer: Gemini gemini-3.1-flash-lite primary, OpenAI gpt-5.4 fallback; observation only. Caller controls appear under matching Channels with verified account sightings by channel ID; win rate shows unavailable until evidence supports one. Honey Drip controls stay limited to their room IDs; newly observed accounts have no execution keys; historical identity attribution is candidate-only. Grabber tracks oldest-message progress, allows 30s for a stalled load, targets one year back, labels stalled history partial. Capture retains message_id, captured_at and revisions, dedupes by channel+ID, exports .json beside .txt. Daily Sniper Reports add an Open in Chrome link only on one exact captured source match; the localhost handoff accepts only configured Discord guild/channel/message IDs and opens Chrome Profile 2 (no broker or Discord API capability). Legacy ID-less rows stay unavailable — re-grab, never infer. Full-history completeness unverified.
- WHO READS (9/14): BOTH live ai_reader lanes — the one-message reader
  (AI READ) and the screenshot reader (IMG READ) — use the observer's
  providers, keys and cooldown map: OpenAI gpt-5.4, then Gemini, then
  Anthropic LAST and skipped while billing-blocked
  (execution.ai_reader.billing_blocked; any credit refusal parks it 6h). One
  order setting, `context_observer.reader_provider_order`. Same prompts, the
  24h image cache, the log names who read it. Changing WHO reads
  changes nothing about what a read may DO — still a proposal the parser and
  every guard judge, AI confidence authorizes nothing. ai_reader.judge() is
  the ONE copy of "validate() can never raise": a model field that is "" or a
  range ("1.26-1.30") is NO CALL — not a crash, not an order (the 9/14
  numbers are in HANDOFF-LOG.md).
- AI MEASUREMENT: results in HANDOFF-LOG.md (9/14). Contextual AI = Gemini
  primary, OpenAI fallback. Market-hours capture still to verify.

## Caller research

- Caller research catalog: `python caller_ledger.py` refreshes the ignored
  local-reader-measure/caller-identity/callers.sqlite3; /callers maps read-only
  account sightings by channel ID. Win rates stay unavailable until trade
  attribution exists; a newly observed account never gets an execution key.
  See reference/CALLER-LEDGER.md.
- Caller behaviour (9/14): options first trim median 5.4 min at +17%; no posted
  option stop — revealed give-up −17%; bot out before their first trim on 15 of
  22 matched pairs. reference/CALLER-PROFILE-2026-09-14.md (rebuild:
  reference/caller_profile.py).

## Second machine (planned 9/9)

## SECOND MACHINE (planned 9/9 — G: "another account on a different computer
## for other subs"). Built default-off; nothing changes until PC2 exists.
- ONE bridge, ONE book, ONE rate budget: PC2 runs only Chrome + the extension
  and sends to THIS PC's bridge over the LAN (Discord's identify budget and
  Chrome's RAM are per account/machine). Never a second bridge on the same
  Webull account — two books break every dedupe and coexistence rule.
- Security is in the code: execution.bridge_listen + bridge_token; the bridge
  refuses to bind off loopback without a token, off-loopback callers must send
  X-Sniper-Token, CORS is limited to chrome-extension:// origins; the extension
  reads an optional gitignored extension/bridge.txt.
- BEFORE PC2 GOES LIVE — LANE TAGS: both PCs read the same rooms.txt, so today
  they would open and trade the same rooms. A 5th `|pc2` field per line plus a
  lane name per machine. Setup steps: HANDOFF-LOG.md under 2026-09-15.

## Weekly files and the house file rules (moved from HANDOFF.md 9/15, verbatim)

The rule lines stay in HANDOFF.md ("Rules of the house"); the naming, the
formats and the procedures are here.

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
- DATA-MAP.md is the index of what is INSIDE the data files — columns, log
  line types, row counts, traps, what each file can and cannot answer. Read
  it WITH INDEX.md at the start of every session. INDEX.md says what a file
  is; DATA-MAP.md says what is in it.
- Compile-check everything touched (python3 -m py_compile / node --check).
  Extension changes → bump extension/manifest.json so a reload is provable.
  Never install the streaming SDK family (webullsdkcore) into the bridge's
  Python. Sandbox trading is RETIRED — paper is LOCAL (SIM tickets).
- Discord API is NOT an option (user-token automation = permanent ban risk
  to the account + paid subs; official bots need the server owner).
  Reaffirmed 9/9. Browser reads only.

## Open watch items — the detail (moved from HANDOFF.md 9/15, verbatim)

One line per item stays in HANDOFF.md ("Watch items (open)"); the numbers,
the history and the open question are here. Close one here when G decides.

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

## Pending item 4 — the Chrome flags note (moved from HANDOFF.md 9/15, verbatim)

4. Close any old parked Whop tabs. (`--disable-gpu` rides every flagged
   Chrome launch since 9/10 — a GPU black tab reads NOTHING while looking
   open; flags bind only on a cold start.)

## How to update HANDOFF.md — the long form (moved from HANDOFF.md 9/15, verbatim)

HANDOFF.md keeps the short form at the top of the file; this is the original
wording of every clause, with the old 30 KB ceiling now replaced by 14 KB.

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

## The four long-form house rules (moved from HANDOFF.md 9/15, verbatim)

HANDOFF.md carries each rule's imperative in one line; G's full wording is here.

- REPLACE, DON'T STACK (G, 9/9). When something changes — a rule, a value,
  a function, a setting, a room line, a doc — the new version takes the old
  one's place. Never leave the old beside the new: not commented out, not
  "superseded", not "legacy/old/deprecated", not a dead branch kept "just
  in case". One thing, one truth. History lives in git and HANDOFF-LOG.md,
  never in the working file. A fallback that must stay is a deliberate
  design decision, written as one — not leftovers. Applies to code,
  settings.json, rooms.txt, every .md, and this file.
- REUSE, DON'T REBUILD (G, 9/15). A report whose inputs have not changed is handed over as it is — `reports.py status` decides, `reports/INDEX.json` is the memory. Rebuild only when it says stale. Never re-derive by reading logs what a report already states.
- ASK-MAP FIRST (G, 9/15). Every ask starts at ASK-MAP.md, then STATUS.json. Logs are read only when those two cannot answer. Checks recorded in STATUS.json.verified are trusted while their inputs are unchanged (VERIFY ONCE).
