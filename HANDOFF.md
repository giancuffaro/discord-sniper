# DISCORD SNIPER — THE HANDOFF
Read this first. It is the living memory of the project: what the machine is,
every rule it trades by, and how G works. Update it whenever a rule changes.
Last updated: 2026-08-30 (announcer v3: futures leg + scoreboard channel, seeded from journals).
No secrets live here — keys and account ids stay in settings.json (gitignored).

## Who and what
- G (giancuffaro230@gmail.com) — non-coder, trades options + futures live.
  Direct, wants things CONDENSED. "Fix everything is default always" — bugs
  get fixed without asking. Real-money actions (placing/canceling orders,
  unlocking accounts, funding, questionnaires) are HIS alone, always.
- The machine: Chrome MV3 extension (reads Discord + Whop rooms in Profile 2,
  v3.3.2) + Python bridge (bridge.py on 127.0.0.1:8787) firing real orders at
  Webull (options), Webull futures, NinjaTrader (OIF files), Topstep/ProjectX.
- SEPARATE tool: "Market Sniper" (his own build, 127.0.0.1:8000) trades HIS
  manual scalps on the SAME Webull account. Coexistence rule: positions the
  bot didn't originate are HIS — visible, never stop-managed, never sold,
  never blocking a room call in the same symbol.

## Rules of the house (current, in force)
- ENTRIES: bid the caller's price or better; pullback entries cross the ask
  at the touch. RN pullback is global and ON by default (waits for the next
  round number, 10-min window). All rooms LIVE by default; toggling off is
  G's only bench. One contract per entry while the bracket strategy is on.
- STRIKES: never more than 1 strike OTM. Deeper OTM snaps to the first OTM
  rung (quote-verified; falls back to ATM/ITM walk). ADD buys the held strike.
- FUTURES: micros only, always (NQ->MNQ, ES->MES, ...). Entry snaps to the
  25-pt grid in his favour. Their stop/target wins; 25/50 fills the gaps.
- SPREAD GUARD (entries only): refuse if spread > 20% of mid, or > max($0.20,
  10% of mid).
- THE RATCHET v2 (strategy 10/10): -10% stop born WITH the order (combo
  bracket; rebased to the FILL if filled better). At +10% stop jumps to
  BREAKEVEN; every further +10% locks another +10%, no ceiling. Contracts
  under $1.00 arm at +15% instead (0DTE noise). The stop does the selling.
- SWINGS: expiry 14+ days out IS a swing (auto-tagged). Their stock-level
  stop runs it (underlying watcher); no level = wide -25%. Never the scalp stop.
- DEDUPE LADDER: extension in-flight contract lock -> bridge echo-lock (same
  contract OPEN within 20s refused, any path) -> per-trader "already in"
  book claim -> better-average exception: same trader, same contract, filled,
  new price >=1% under what was PAID -> one ADD (average-down), never more.
- RETRACTION: "not ready / revising / scratch that / cancel that / disregard
  / hold off / nevermind" pulls that trader's resting bids AND kills their
  armed pullback hunts. Exits/held positions untouched.
- TAB MASSACRE (FIXED 8/30, v3.4.5 — G: "43 rooms but fewer open"):
  oneTabPerChannel (the dupe-closer, on the watch-build alarm) treated
  still-loading tabs as duplicates — during START HERE's paced flood,
  uncommitted tabs all report the same blank//channels/@me path and got
  closed as one. Now: loading tabs are never candidates, and only paths
  that NAME a room (/channels/<id>/<id>, /exp_<id>, /joined/) can dedupe.
  Note the flood itself takes ~2.5 min by design (3 tabs per 10s so
  Chrome doesn't choke) — count tabs after, not during.
- EMBED RACE (FIXED 8/30, v3.4.4 — G: "every bot puts the trade inside an
  embed"): HD Greeter, ZTRADEZ BOT, Options Insider Alerts, Nitro Trades
  all post an empty body with the call in a Discord embed, which hydrates
  a beat AFTER the row paints. The old id-burn dedupe locked in the blank
  first read — alerts vanished silently. Now content.js SEEN maps id ->
  captured text length (blank shells stay unrecorded; a fuller re-read
  re-emits) and the worker's seenMessage keys mid+length to let the
  hydrated version through. Same-length re-sweeps stay deduped; a double
  EMIT of the same signal is caught by the normal dedupe ladder.
- GIT SAFETY (learned the HARD way 8/30 ~2:26 AM): START HERE's mirror
  step ran git reset --hard origin/main while a day of work sat in LOCAL
  commits that never reached GitHub — the reset destroyed the working
  tree back to 8/28 and deleted staged-new files. RECOVERED fully from
  the pre-reset auto-push commit (348ac20) via the reflog. Rule: the
  reflog holds ~90 days of orphaned commits — after ANY suspicious file
  loss, check `git reflog` for a "reset:" line before rebuilding by hand.
  Bridge /rooms endpoint exists (curl 127.0.0.1:8787/rooms = the parsed
  live room list).
- STALE-ENTRY GATE: entries older than 3 minutes (re-scan, slow tab) never
  fire. Exits pass at any age. Negations ("NOT GETTING IN", "too expensive")
  hard-veto everything; "out the gate(s)" is hype, never an exit.
- EXITS: urgent sells cross the bid; fill-confirmed (phantom-exit family).
  Bare exits ("OUT NVDA") resolve to the held contract via the book. Pulled
  bids are confirmed dead — if the cancel lost the race, the exit sells the
  fill immediately.
- RESTARTS: state photo on every event. On boot: expired options = dead
  paper, dropped, zero credit; everything else is UNVERIFIED until the
  broker confirms it (then watchdog+stop arm); gone = closed at "a price I
  never saw", never a stale quote. Mid-market code updates self-apply at the
  first safe window (no bids/hunts in flight); RESTART BRIDGE.bat pre-flights
  and warns. Resting stops at Webull guard every gap.
- THE DOCTRINE (G, 8/30): voice is the TRIGGER, the RN pullback is the
  ENTRY, the ratchet is the EXIT. Voice leads the scribe by median 19s on
  entries — that head start arms the pullback hunt earlier, catching
  round-number touches the typed timing would miss. Voice EXITS are
  optional garnish (the ratchet already owns TP+SL); voice ENTRIES are
  the point. Hard-lines file (voice-HARD-lines-for-G.txt) holds the ~75
  utterances still untranslated — G translates, rules get encoded.
- VOICE (v3.4.2, built with G 8/29-30): ZOOM works — Felony goes live via
  Zoom; the Zoom WEB client (app.zoom.us/wc/... "Join from browser") is a
  Chrome tab, so tabCapture grabs it like Discord voice. Auto-listen now
  triggers on audible zoom.us tabs too; the Zoom desktop APP is invisible
  to the ears — always join in the browser. Ears transcribe always, with Deepgram
  DIARIZATION (speaker tags S0/S1... in captures). TWO popup switches, both
  default OFF: Voice EXITS (spoken outs/trims fire — the proven 6-249s
  edge) and Voice ENTRIES (the STITCHER joins 25s of speech per speaker;
  needs strike + 85% read). TWO-STAGE PROTOCOL: "loading X" = STAGED (4-min
  shelf, per speaker); fires only on that same speaker's "I'm in / got
  filled / my average is X" (spoken average becomes the bid). "I'll let
  you know when I get filled" = pending, never fires. SPEAKER NAMING: a
  typed scribe alert matching a voice call within 90s names that speaker
  (persisted); named voices book under the trader's real name so all
  per-trader walls apply. GLOSSARY (in ai_reader): pulls=puts, as-p-y=SPY,
  Qs=QQQ, one-d-t=1DTE, cons=contracts, number-words=digits, bare number
  is never a strike, average=fill price, "settle for green"=exit, never
  marry ticker+strike across an intervening ticker. Typed copy of a voice
  fire is skipped as echo for 5 min.
- WHOP (SOLVED 8/30 — "we never got anything from Whop"): Whop's 2026
  redesign KILLED /joined/ URLs — they redirect to /townhall/ (or mangle
  the room id), a lobby page with neither structure, so tabs parked on old
  links read NOTHING forever. Zero whop signals in every log confirmed it
  was literal. The reader itself is FINE — verified live 8/30 on the new
  pages: feed selectors (post_*_container) matched 10-14 posts in Trading
  Floor/Day Trades, chat selectors (ChatMessageContainer...) matched 50
  rows in Trading Chat, author/age/body all parse. Rooms now live at
  whop.com/<business>/exp_<id>/app/ — rooms.txt REPLACED with the new URLs
  (same hashes, so whopRoomOf() maps unchanged); START HERE opens the right
  tabs on next launch. G should close any old parked Whop tabs. BONUS: Felony's pinned rule — he now posts QQQ/SPY CONTRACTS
  whenever he trades NQ/ES (Trading Chat) = directly parseable options
  calls. v3.4.3: whop.js warns on non-exp_ URLs; tab-dedupe covers the
  new shape. Watchdog reloads stale tabs (market hours) and black-shell
  pages (any hour, via the 1-min health pulse). Silence alarm: any room
  quiet 40 min during market hours -> desktop notification.
- THE POCKET (hidden from UI on purpose): scalp-entry clock gate :43-:51
  exists behind settings flag pocket_scalps_only (default off). Journals
  stamp each trade's minute-of-hour; decision comes from HIS fill data,
  not the QQQ study (2yr: :45-:51 has +27% dollar-follow-through).

- FILL ANNOUNCER v3 (8/30): announcer.py + ANNOUNCER.bat — watches BOTH
  Webull accounts (margin + futures; futures wired even while it holds $0,
  per G) read-only, posts every fill within ~1s ("ENTRY TSLA 345P 8/28 @
  4.24 x1"), +10/+20/+30... milestones off live quotes, ⛔ STOPPED OUT on
  red exits. SCOREBOARD: per-symbol realized $ (options x100; futures via
  FUT_MULT — MNQ $2/pt, MES $5, ...) accumulates in announcer-scoreboard
  .json (gitignored, SEEDED from journals 8/19-8/28: grand -$1,635; QQQ
  -846 worst, NVDA +125 best). After every close it posts "🏆 SYM +$ today
  (+$ all-time) | Day | Leaders"; full board posts at boot. CHANNELS (8/30,
  G): options fills -> announcer.webhook_url, futures fills -> announcer.
  futures_webhook_url (set, routed by source account), scoreboard ->
  announcer.scoreboard_webhook_url (NOT set yet — falls back to options
  channel until G makes that channel). RULE:
  NEITHER channel ever goes into rooms.txt (the sniper would chase its
  own tail). Same script is the template for any trader G recruits.
  RUNS IN BACKGROUND (8/30): ANNOUNCER.bat double-clicked once = starts
  hidden (output -> announcer.log), installs a Startup-folder entry
  (every logon) + "Fill Announcer revive" schtask (every 30 min).
  Keep-alive: _announcer_hidden.vbs -> _announcer_loop.bat (10s crash
  respawn). Single-instance via .announcer.alive heartbeat (15s beats,
  90s stand-down, cleared on exit). Off switch: STOP ANNOUNCER.bat
  (drops announcer.stop — stays off through reboots until ANNOUNCER.bat
  runs again and deletes it).

## Operational truths
- settings.json: ALL keys, gitignored, never pushed. Never run git write ops
  from the sandbox (locks can't be unlinked); AUTO PUSH.bat is a resident
  45s push-on-change loop; START HERE.bat saves+pushes before its reset.
- Journals: journal-YYYY-MM-DD.xlsx built from broker fills (connector)
  FIFO-matched vs trades.log; includes entry minute-of-hour. Scoreboard:
  Felony = Trademorewiser (one identity). Whop = Felony only.
- sniper-autopilot scheduled task: */30 ET — preflight ~9:30, sync watch
  market hours, close-out ~16:30. Never places/cancels orders, never touches
  settings.json.
- Multi-account: extras (e.g. "L") mirror LIVE entries 1:1 with own books/
  stops, gated by subscription (paid_month). Exits always mirror.

## Standing chores (G's side, updated 8/27 evening)
1. RESOLVED (8/28 night): the 417 STRATEGY_NOT_MATCH "rejections" were
   the Webull SANDBOX refusing options (all 8/28 payloads were paper —
   rooms had been flipped to testing during the 8/26 scare). His real
   account was never blocked; nothing to update at the broker. FIX
   SHIPPED: paper is LOCAL now — testing orders never touch the sandbox
   (SIM tickets, assumed fills, live-feed quotes), so that rejection
   class is extinct. WATCH: one genuine LIVE 417 on 8/26 9:50:03 (TSLA
   exit, mid rapid-retry) remains unexplained — eyeball the first live
   option order after rooms flip back to REAL. NOTE: rooms are still
   set to TESTING from 8/26 — G must flip them back live when ready.
2. NEW (8/28): Topstep refused brackets — "You must enable Auto OCO
   Brackets" — a toggle in his Topstep/ProjectX account settings.
3. Bridge went silent Fri 16:38 (likely exited). Verify it's up before
   CME reopens Sunday 6 PM ET.
4. Webull futures account: $0 BY CHOICE (his call 8/27) — NT + Topstep carry
   futures; Webull-futures refusals are clean and intentional.
5. NinjaTrader ATM template: decided 8/27 — name SNIPER, stop 100 ticks /
   target 200 ticks (= 25/50 pts on MNQ), qty 1. G creates it in NT8 and
   types SNIPER into the popup's NinjaTrader field.
6. Topstep XFA: locked/paused — unlock in TopstepX Risk Settings (-$680
   pre-existing on it).

## Subscriptions (audited 8/28 from Whop billing + G)
Whop, card ****4000, ~17.5% tax on top of sticker:
  Insiders Pro (Options Insider) $199 | STS Full Access (RWGates — Summit
  Trading Strategies IS RWGates, same person) $189 | Felony/FirstStep $100 |
  Boka $99.99 | Platinum $99 | "VIP discord access" $65 (server still
  unidentified — logo "WiningTheTrde"?) | ZTRADEZ $65 | Vero $49.
Stripe: Honeydrip/Aristotle $125. Free: Rafita.
TOTAL rooms: ~$991/mo sticker, ~$1,140/mo with tax (~$13.7k/yr). Discord
itself bills $0 — no card on file there.

Infrastructure (G confirmed 8/28):
  ProjectX/Topstep API $29 | NinjaTrader data $12 | Deepgram ~$5 usage |
  Webull options data ~$3 + futures data ~$2.50 | TradingView $0 (no sub).
  = ~$51.50/mo confirmed.
Still login-walled, G to check: Anthropic API usage (console.anthropic.com
  -> Billing — the AI reader burns this all day) and Topstep eval fees
  (dashboard.topstep.com -> Billing — EXPRESS + XFA likely bill monthly).
Variable: Webull passes exchange/regulatory fees per options contract
  (~$0.10-0.60/contract) — at bot volume ~$20-40/mo. Not a subscription
  but real burn.
GRAND TOTAL: rooms ~$1,140 + infra ~$52 + fees ~$30 = ~$1,220/mo before
AI usage and Topstep evals. The operation must clear ~$60+/trading day
to break even on costs.
Next audit: cost vs scoreboard P&L per room; identify the $65 mystery sub.

## Watch items
- Deepgram key may be one char short (39) — watch for voice auth errors.
- Bridge log rotation: SDK logs purge at boot, 2-day keep.
- Chrome: hardware acceleration OFF recommended (GPU black-tab disease).
- His L account: verify no orphan positions after mirror exits.

## How to update this file
At the end of any session that changed a rule, add/edit the rule above,
bump the "Last updated" line, and let AUTO PUSH sweep it. The bridge's own
daily handoffs/HANDOFF-<date>.md is a thin status snapshot only — this file
is the memory.
