# DISCORD SNIPER — THE HANDOFF
Read this first. It is the living memory of the project: what the machine is,
every rule it trades by, and how G works. Update it whenever a rule changes.
Last updated: 2026-09-01 (first automated journal day; breached-stop clamp
fix — see the daily rule section. Mashup attribution CONFIRMED working:
9/1 journal names The Market Bishop / Jpm Options. Bot 0-for-3 -$70 on ZT
mashup day one incl. the S swing's clamp bug; Gian +$94. FLR 57.5C swing
open. The 8/31 fixes all proved live 9/1: rearm fired 9:31, ghost-clear
and stop_below in the build since 00:10.)
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
- SPX->SPY, per channel (8/30, v3.4.8 — G: Ryan's alerts/Boka 3 trade SPX,
  "enter with SPY instead, pretty much the equivalent"): channels listed in
  settings.json spx_entry_channels fire index ENTRIES as the ETF — SPY,
  strike/10 rounded (6470 -> 647), caller's premium DROPPED (index premium
  is ~10x the ETF's; the bridge bids the SPY market). Verified: same call
  refuses everywhere else — the 8/15 index-entry off switch still rules.
- THE RATCHET v3 — TIERED (v3.5.0, G chose "live tomorrow" 9/2): -10%
  stop born WITH the order (combo bracket; rebased to the FILL if filled
  better; never at/above the fill). Then the rung plan comes from what he
  PAID (ratchet_tiers.py): UNDER $1 arms +25%, first lock +10%, rungs
  +15% (a $0.40 contract moves 2.5%/tick — finer rungs get scratched by
  the quote). $1-$1.99 arms +15%, first lock BREAKEVEN, rungs +10%. $2+
  arms +10%, first lock +5%, rungs +5% (a $2.50 fill at +30% rests at
  3.09, not 3.00). Two floors: a rung is worth 4+ ticks, and the stop
  never sits inside the bid/ask (ratchet_stop_price; last_ask stored on
  the watchdog pass). Shorts ratchet mirrored; futures route to a points
  ratchet (_futures_ratchet: one stop-width of profit = BE, each further
  = another rung) that only fires once a futures quote feed exists. The
  stop does the selling. NOT applied: B4 replace_stop (naked-window fix,
  needs new plumbing — weekend with Block C).
- SWINGS: expiry 14+ days out IS a swing (auto-tagged). Their stock-level
  stop runs it (underlying watcher); no level = wide -25%. Never the scalp stop.
- DEDUPE LADDER: extension in-flight contract lock -> bridge echo-lock (same
  contract OPEN within 20s refused, any path) -> per-trader "already in"
  book claim -> better-average exception: same trader, same contract, filled,
  new price >=1% under what was PAID -> one ADD (average-down), never more.
- RETRACTION: "not ready / revising / scratch that / cancel that / disregard
  / hold off / nevermind" pulls that trader's resting bids AND kills their
  armed pullback hunts. Exits/held positions untouched.
- THE MASHUP SWAP (8/30, v3.4.6 — G: "eliminate six and have only one"):
  ZT all-trades-mashup (1334236429655740457, ZTRADEZ BOT) relays every ZT
  trader as embeds titled "<Name>'s ...". Wired IN; the five journal-proven
  bleeders wired OUT (commented in rooms.txt, reversible): MR.TOPHAT -156,
  Market Bishop/opt-7 -87, Demon -65, EvaPanda/opt-5 -55, are-alerts/opt-2
  -42. RELAY UNWRAP in background.js re-books relayed calls under the real
  trader name (regex on the leading possessive), so per-trader claims +
  dedupe + scoreboard hold, and a direct-room copy can't double-fire.
  KingBeeAri posts inside Honeydrip's Aristotle rooms — not separately
  cuttable. THEN G took it to the logical end ("if Demon's in the mashup
  there's no point having Demon's channel — eliminate their respective
  channels"): ALL 19 individual ZT rooms are now commented out; ZTRADEZ =
  the mashup alone. Rooms 43 -> 25. VERIFY MONDAY: the mashup capture
  lists every relayed trader (unwrapped names) — any ZT trader who does
  NOT appear gets their direct room uncommented. If the mashup ever goes
  quiet in market hours, the 40-min silence alarm barks. MIDAS re-added
  8/30 (G: "we only need entries, since we have the ratchet" — his exits
  were the old reason he got benched). Rooms = 26. ALSO 8/30: day-first expiries ("26/8") accepted
  in webull_options (cost a TLG META entry 8/25), and Vero's month-name+
  year format ("MSTR SEP 18 2026 $150 CALLS") parses (was "no full
  contract"). RWGates VERDICT corrected: he DOES fire when he posts full
  contracts (NFLX 8/19+8/20); his misses were thin buying power + the
  date bug + contract-less narration (correctly skipped).
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
- EXITS — RATCHET + EMERGENCY OUT (G's policy, 8/30: "we're taking
  everybody's entry, but we are letting the ratchet do its thing"): the
  ratchet owns ALL profit-taking and stop management. Callers' TRIMS and
  STOP-MOVES are logged ("noted, not traded") and never fire — this
  includes swing stop-level tightenings (the level posted WITH the entry
  still applies; later moves don't). A caller's FULL exit ("all out",
  "stopped out") still fires as the emergency word — urgent sells cross
  the bid, fill-confirmed (phantom-exit family), bare exits ("OUT NVDA")
  resolve to the held contract via the book. Pulled bids are confirmed
  dead — if the cancel lost the race, the exit sells the fill immediately.
  settings.json exit_policy:"full" = the one-line way back.
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
- VOICE ENTRIES switched ON by G 9/2 pre-open (data collection: measure the live voice-vs-scribe lead; a voice fire is real money only in a LIVE room).
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
- WHOP API READER (8/30, v3.4.9 — built DARK, awaiting G's key): Whop has
  an official API (docs.whop.com/developer/guides/chat) — messages.list by
  the SAME exp_ ids in rooms.txt. bridge.py polls every whop room server-
  side (1.5s, endpoint-hunted, Bearer key) into a /whopfeed queue; the
  extension's OFFSCREEN page (the only MV3 place a 2s timer survives)
  polls it and forwards items as normal whop MESSAGEs (mid "whopapi|...").
  When active, tab-sourced whop reads are DROPPED (api is the one source;
  tabs stay as backup/health view). ACTIVATION: G creates an app at
  whop.com dashboard -> Developer, pastes key into settings.json as
  "whop": {"api_key": "..."}, restarts bridge. TESTED 8/30 with G's real
  Account API key (in settings.json): the key AUTHENTICATES (endpoints
  resolve, Day Trades correctly identified as a forum-type experience)
  but member-side reads are WALLED — chat 403, forum "You do not have
  access to read these posts". Account keys see your own business only.
  "active" on /whopfeed = delivered-in-last-5-min (never just key-exists),
  so tabs NEVER stand down for a dead feed; poller backs off to 60s probes
  while walled. PLAN B (the unlock): Felony installs G's Whop app with
  chat:read — the moment any community grants access, the reader lights
  up on its own, no code changes. Tabs carry the job until then.
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
  NEVER-POSTED BUG (FOUND+FIXED 9/1): the announcer's homemade order hunt
  guessed SDK verbs that don't exist — announcer-seen.json sat [] for three
  days while the account did nine round trips; only "online" banners ever
  reached Discord. _recent_orders now uses the proven last_sell_fill
  pattern (holders order_v3/order/trade/account_v2, verb substring
  "history", dates BY KEYWORD). Also: an EMPTY announcer.stop is inert now
  (the sandbox can truncate but not delete); STOP ANNOUNCER writes "stop"
  into it. First live narration expected 9/2.
  RUNS IN BACKGROUND (8/30): ANNOUNCER.bat double-clicked once = starts
  hidden (output -> announcer.log), installs a Startup-folder entry
  (every logon) + "Fill Announcer revive" schtask (every 30 min).
  Keep-alive: _announcer_hidden.vbs -> _announcer_loop.bat (10s crash
  respawn). Single-instance via .announcer.alive heartbeat (15s beats,
  90s stand-down, cleared on exit). Off switch: STOP ANNOUNCER.bat
  (drops announcer.stop — stays off through reboots until ANNOUNCER.bat
  runs again and deletes it).

- SANDBOX FULLY RETIRED (8/29, G: "deactivate every single thing that has
  to do with paper trading" [meaning: sandbox contact]): the paper client
  now connects with LIVE keys to the LIVE endpoint — real quotes, real
  account list (margin picked like live, futures kept apart) — and the
  paper flag alone keeps orders LOCAL (SIM tickets) and balance offline
  (None, never a network call — was 211 sandbox 404s in one quiet
  Saturday). The old "sandbox 401 -> quietly flip to live" fallback is
  DELETED: it would have turned one flaky boot request into real orders
  from testing rooms. paper_app_key/secret in settings = dead config.
  TESTING mode itself is unchanged and still the default for every room.

- CHROME OUT OF MEMORY (9/1): CAUSE = our own --process-per-site flag
  packed every Discord tab into ONE renderer; Discord web bloats 0.5-2 GB
  per tab after hours; that single process hit Chrome's per-process V8
  ceiling. FIX: flag removed from START HERE (one renderer per tab — more
  total RAM, no single-process wall) + MEMORY SHED in background.js
  (v3.4.11): every 30s tick reloads at most ONE Discord room tab whose
  last reload is 2h+ old — never the active tab, never a voice tab, never
  9:28-9:40. Reloads are safe (content re-attaches; on-screen history is
  never traded). Discord API is NOT an option for reading others' servers:
  user-token automation = ToS ban risk; official bots need the server
  owner to add them (same "install my app" pattern as Whop).
- UNDERLYING AT FILL (9/1, G's ask): positions record und_at_fill; the
  FILLED log line carries "· SYM @ price"; the announcer ENTRY post shows
  "(SYM @ price)"; the journal has an "Underlying at fill" column.

- v3.5.0 PACKAGE (9/2, from a parallel session; docs in v3.5.0/):
  APPLIED = Block A: _pace 0.15->0.20 (was 33% over Webull's 5/s cap),
  SDK file logger (webull_api.log), and the TAB-DISCARD fix — Chrome's
  Memory Saver discards background tabs that still look healthy to every
  watchdog; now every room tab is pinned autoDiscardable=false each tick,
  content.js heartbeats every 30s, and a room silent 3 beats (~90s) or
  detached is reloaded (log line "⚠ Chrome had DISCARDED..." / "reader
  stopped answering"). Memory-shed cadence 2h->4h. Extension 3.5.0.
  THEN G said "do everything now" (9/2 ~01:20) — ALL APPLIED, bridge
  restarted clean 01:26 with "QUOTE BUS on": Block B tiers (see RATCHET
  v3) + ANTI-CLIP (locked <= 60% of gain, v3.5.0/ANTI-CLIP.txt: 520-trade
  study, +$6,433 vs +$2,872, nine of nine names better); B4 replace_stop
  (webull_options.replace_stop via the SDK's replace verb, existing
  client_order_id; ratchet tries REPLACE first, falls back to cancel+
  place and now tells the truth — "NO broker stop is resting" — and
  clears stop_order_id so the next pass re-arms); Block C quote bus
  (bridge: Budget shared by all clients + QuoteBus on WB.ask_bid_many;
  positions._watchdog reads the bus, falls back to a DIRECT quote at most
  every 2s when the bus has nothing fresh — a dead bus can never blind a
  stop; unwatch in the watchdog's finally; poll floor 0.2;
  fill_poll_seconds 0.3). SWING STOPS through every path: _arm_stop uses
  25% for a swing with no level (restore/re-arm used to hand swings the
  -10% scalp stop — FLR 01:00 "1.50 -9%" -> now 1.25 -24%). Breach check
  now applies to explicit (ratchet/swing) stops too.
  BLOCK D: PARKED — the streaming SDK family (webullsdkcore) and the
  bridge's (webull) pin incompatible protobuf/paho/cachetools/jmespath;
  installing the test into the bridge's Python BROKE its pins (FIX SDK
  DEPS.bat restored them, G ran it 01:10). TEST STREAMING.bat now only
  runs inside a side-by-side Python 3.12 venv (.venv-stream) and refuses
  otherwise. From the sandbox the MQTT port is blocked — inconclusive.
  ANNOUNCER 429 STORM (9/2 01:30): the rewritten _recent_orders re-ran the
  full SDK verb hunt every 1s on two accounts = 76,991 TOO_MANY_REQUESTS
  in one night on the SHARED app key — the bridge's 429s were this
  process. Fixed: hunt ONCE per account, remember the bound method, pace
  0.20s, futures every 5th poll, 20s back-off on 429, poll 2s. tests:
  test_positions + test_resolve pass.

- OPTION TAPE (9/2, v3.5.0/HANDOFF-OPTION-DATA.md): Webull's API has NO
  historical option prices (US_OPTION unsupported) — every ratchet
  backtest so far ran on MODELLED (Black-Scholes) premiums, the weakest
  link in the anti-clip analysis. The quote bus now RECORDS every quote it
  sees to option_tape.csv (ts,occ,bid,ask, ~300ms; gitignored; rotate
  monthly). In ~3 weeks the tiers/anti-clip can be re-checked on real
  bids from exactly the contracts the rooms call. Free next step G can do
  any time: chart 5-10 contracts from 8/28-9/01 in thinkorswim and
  compare to the modelled premiums. Buy-once backfill (Databento free
  credit / ThetaData one month) ONLY if the model checks out and he'll
  actually re-run the analysis.

- BROKER FACTS (9/2 research, ~150 sources: v3.5.0/OPTIONS-BROKER-
  REFERENCE.md — READ IT before any broker test). Corrections applied:
  (1) Webull has NO option streaming (MQTT = stocks/ETFs/futures/crypto
  only) — TEST STREAMING is answered, no Python 3.12 needed. (2) Rate
  limits are PER ENDPOINT: option snapshot 60/min (20 symbols/call),
  Order Detail / Open Orders / Positions / Balance 2 per 2s — the quote
  bus now sweeps at 1.05s (was 0.30 = would have 429'd), ask_bid_many
  chunks at 20, fill_poll_seconds 1.0. (3) TICKS: SPY/QQQ/IWM = $0.01 at
  every price; Penny Program names $0.01 <$3 / $0.05 >=$3; others $0.05/
  $0.10 — tick_round/stop_below/_tick_round are symbol-aware (PENNY_ALWAYS
  + PENNY_PROGRAM sets in webull_options; unknown = coarse, always legal).
  (4) Option SELL orders are DAY-only at Webull (confirmed) — the 9:31
  re-arm is the right design. (5) No MARKET orders for options; combos =
  MASTER(LIMIT)+STOP_LOSS on SINGLE only; OTO/OCO are stock-only — our
  bracket shape is correct. (6) Replace needs the ORIGINAL client_order_id
  AND legs[].id for options — replace_stop lacks leg ids, so it falls back
  to cancel+place (safe); storing leg ids at entry would make replace
  work. (7) Webull PUSHES order fills over gRPC (TradeEventsClient, same
  SDK) — that is announcer v4: no polling, no rate budget. (8) ETF options
  (SPY/QQQ/IWM/DIA...) trade to 16:15; the restart safe-window already
  honours 16:15. (9) Webull retail lists SPX/XSP index options; whether
  the OpenAPI takes them is UNVERIFIED — our SPX->SPY translation stays.

- "ADDED" IS AN ENTRY (9/2 retest, v3.5.1): Boka's/RWGates' "added $DRAM
  $57 calls 9/18" only parsed on Saturday because the message also said
  "buying". Now RE_ADD (both parsers) accepts "57 calls"/"$57 puts", and
  resolveAdd/resolve_add turn an "added <full contract>" you are NOT in
  into an OPEN entry. A bare "added to SPY" with no contract still refuses.

- START HERE = FRESH START (G, 9/2): a click now CLOSES Chrome (5s
  countdown, Ctrl+C aborts) and reopens every room, replacing the 8/10
  "never touch open tabs" rule. It also launches the Fill Announcer
  (step 4.5, single-instance, honours a non-empty announcer.stop). The
  logon Startup entry waits 60s before launching the announcer (the
  instant fire threw "Can not find script file").

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

## The daily rule (G, 8/31): "fix errors every day after journaling."
A scheduled task (daily-journal-and-fix, weekdays 16:45 ET, runs in the
desktop app) builds the journal from broker truth and then FIXES what it
exposes, same day. All four of 8/31's finds were fixed within the hour:
- GHOST STOP — FIXED: reconcile_gone refused verdicts on an empty account
  ("flat and unreachable look identical"). broker_positions now flags a
  SUCCESSFUL live read, and trust_empty_live lets a flat account clear
  ghosts. (The adopted SPY he'd sold haunted the book 3h and 417-stormed.)
- CHEAP STOP ROUNDING — FIXED: new stop_below() everywhere a stop is
  computed — pct down, tick-rounded, and NEVER at/above the reference
  (drops a full step if rounding lands there). 0.20 fill -> 0.15 stop,
  was 0.20 = the 7-second IWM stop-out.
- SWING OVERNIGHT — FIXED: Webull sell-leg stops are DAY-only, so
  Book.rearm_overnight_stops() (bridge calls it weekdays at 9:31) re-arms
  every open SWING's resting stop each morning. Scalps excluded on purpose.
- MASHUP ATTRIBUTION — WIDENED (v3.4.10, needs extension reload): the
  relay unwrap now also hunts the first 140 chars for "<Name>'s
  ideas/alerts/trades/plays/calls/entries". If tomorrow's calls STILL book
  as ZTRADEZ BOT, pull one raw captured mashup message and fix from truth.

## Watch items
- Deepgram key may be one char short (39) — watch for voice auth errors.
- Bridge log rotation: SDK logs purge at boot, 2-day keep.
- Chrome: hardware acceleration OFF recommended (GPU black-tab disease).
- His L account: verify no orphan positions after mirror exits.

## The Claude Project (G's claude.ai project, set up 9/2)
project/PROJECT-INSTRUCTIONS.md is its Instructions; project/context/ holds
its Context uploads. RULE: whenever this HANDOFF changes materially (a rule
added/changed, a system built or retired), copy it over
project/context/HANDOFF-snapshot.md (fixed name, so a re-upload replaces),
refresh rooms-snapshot.txt if rooms changed, and END THE REPLY with:
"📌 Update the Project: re-upload project/context/HANDOFF-snapshot.md".
The daily journal task does the copy automatically at 16:45; sessions do it
by hand. The live HANDOFF.md always wins over the Project copy.

## How to update this file
At the end of any session that changed a rule, add/edit the rule above,
bump the "Last updated" line, and let AUTO PUSH sweep it. The bridge's own
daily handoffs/HANDOFF-<date>.md is a thin status snapshot only — this file
is the memory.
