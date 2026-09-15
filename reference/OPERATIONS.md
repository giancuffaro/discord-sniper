# OPERATIONS — mechanics

The mechanics behind the rules in HANDOFF.md, moved here 9/15 so HANDOFF stays a
rules core (under 30 KB). The rule is in HANDOFF; the HOW, the numbers and the
history-with-numbers are here. REPLACE, DON'T STACK applies: edit in place.

Restarts, POSTCHECK, the 16:40 audit, git/AUTO PUSH, the autopilot, the Fill
Announcer, departments, the AI readers and keys, caller research, the second machine.
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
  one-screen `BRIEF-<date>.md` to Sniper HQ through the Fill Announcer's
  options webhook — that post is how G gets the day; a failed brief never
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

## Fill Announcer

FILL ANNOUNCER (announcer.py, read-only)
- Posts every fill, +10/+20/… milestones, ⛔ stop-outs to G's Discord:
  options → announcer.webhook_url, futures → futures_webhook_url,
  scoreboard → scoreboard_webhook_url (falls back to options). NEITHER
  channel ever goes into rooms.txt. Single-instance (.announcer.alive);
  off switch = announcer.stop containing "stop" (STOP ANNOUNCER.bat);
  "Fill Announcer revive" schtask every 30 min; announcer.restart = reload.
- STATUS: PAUSED since 9/2 (announcer.stop = "stop", G: "get this app
  working 100% first"). Its board is computed FROM THE LEDGER (9/9). Its
  order hunt is paced (0.20 s, once per account) — the 9/2 429 storm must
  never come back.

## Autopilot, launchers, logs

- sniper-autopilot scheduled task: */30 ET — preflight ~9:30, sync watch
  in market hours, close-out ~16:30 (the old daily-journal-and-fix 16:45
  task is PAUSED, folded into Mode C). It never places/cancels orders or
  touches settings.json.

- Multi-account: extras mirror LIVE entries 1:1 with own books/stops.
- START HERE.bat saves+pushes before its reset; RESTART BRIDGE.bat
  pre-flights and warns. Logs: trades.log (the story), bridge.log (raw,
  20 MB, no rotation yet), webull_api.log, announcer.log, deadman.log.

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
