# DISCORD SNIPER — THE HANDOFF
Read this first. It is the living memory of the project: what the machine is,
every rule it trades by, and how G works. Update it whenever a rule changes.
Last updated: 2026-09-02 evening (daily journal-and-fix run #2 — see
"9/2 EVENING" at the bottom. Bot -$62 on 3 closes, Gian +$114 on 9 hand
trades, account +$52 gross / +$45.71 net. Six bridge fixes + extension
3.5.7 (RELOAD IT): pulled stops go back when an exit is abandoned, a
CLOSE never sells what the book doesn't hold, "price I never saw" now
trues itself up from the broker, bare "out" can't touch his hand trades,
symbol-aware ticks at the order choke point, exits sell the HELD strike,
mashup calls attributed from the relay FOOTER, heartbeat reloads back off.
RULE: his hand trades are UNTOUCHABLE by any room's exit/trim/stop-move
(G, 9/2: "they shouldn't") — the 8/18 "closeable on the room's call" adopt
rule is retired. IREN 40C 9/18 swing carries overnight, GTC stop 1.85
confirmed SUBMITTED at Webull 17:45.)
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
  never blocking a room call in the same symbol. ENFORCED 9/2 evening at
  every exit door (Book.is_hand_trade — see "HAND TRADES ARE UNTOUCHABLE").

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
- AUTO-JOIN (v3.5.2, 9/2, G: "last time I knew it joined itself" — it never had; he'd been in voice already): on a LIVE badge the extension now CLICKS into that voice/stage channel (content.js joinLiveVoice: live row -> Join/Join Stage button), waits 5s for audio, then the ears start. One auto-join per 10 min across all tabs (one voice connection per Discord account). Fallback = the old notification.
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
  -> DONE 9/2 evening: they did (IREN/IWM/SPY 762P all "ZTRADEZ BOT").
  Truth from the raw capture: every relayed message ENDS with its source
  channel — "... #◽︱♟market-bishop • 3:57 PM". v3.5.6 reads that footer
  (slug -> The Market Bishop / MR.TOPHAT / Jpm Options / King Maker ...;
  an unknown slug books under the slug itself). Verify 9/3: the journal
  names the trader on every mashup call without hand work.

## Watch items (9/2 midday — status as of the evening run)
- EXIT-WHILE-WORKING — FIXED (evening): plan_exit stands an armed pullback
  hunt down on the room's exit (the 11:13 NVDA shape) and, new rule, a
  CLOSE for a contract the book does not hold is REFUSED, never sent — the
  "worst case is a 417" comment was wrong the day he started scalping
  SPY/QQQ in size in the same account (a sell of 1 against his 12-lot is
  a loss, not a message). Adopted positions are on the book, so a room's
  NAMED exit still reaches them (policy question below).
- QUOTE BUS BATCH: fixed 14:20 (Response object vs .json()); the 17:12
  restart shows no "batched option quotes not available" line. Closed.
- GTC OPTION STOPS ARE ACCEPTED: closed by the 14:35 "check before redoing"
  rule — 17:12 restart logged "overnight stop still resting at Webull at
  1.85 — kept" on IREN. Confirm 9/3 pre-open that Webull still shows it
  SUBMITTED/working after the night (first real overnight broker stop).
- MARKET SNIPER SOLD BOT POSITIONS: FLR (10:56:35 @1.55) and SPY 766C
  (11:48:00 @1.87) closed by MARKET orders with 6a98… client ids — G's
  hand (Market Sniper/app), not the bot. Still open: was FLR a deliberate
  flatten? (-$9 on a swing that was +5% the night before.)

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

## 9/2 PM — STREAM BUS: "stream all data from the best source we can"

What streams now, per data type (the honest ceiling for each):
- **Fills** → Webull gRPC push (`TradeEventsClient`). Announcer already wakes on it; bridge still polls fills at `fill_poll_seconds` (1s) — good enough, push wiring for the bridge is a next step.
- **Underlying stock/ETF prices** → Webull MQTT (`stream_bus.py`, `StockStream`). Attached to every client as `wb.stream`; `stock_price()` answers from the push when <3s old, else the old HTTP path. Bridge pre-watches SPY/QQQ/IWM + Mag7; anything else auto-subscribes on first ask. One connection (limit 5/key), fresh session id on every reconnect, daemon thread, all try/except — cannot block trading.
- **Option quotes** → no stream exists at Webull (MQTT = stocks/ETFs/futures/crypto only). The 1/s batched quote bus stays the ceiling. `option_tape.csv` now actually records every sweep (`QuoteBus.record_to`) — earlier note said it did; it hadn't landed.

Verify after RESTART BRIDGE: `curl 127.0.0.1:8787/stream` → `connected: true`, `msgs` climbing, `fresh: {SPY: ...}`. Bridge log line "STREAM on". If you see `[stream] dropped (403...)` the app key lacks the OpenAPI market-data subscription (developer.webull.com → Subscribe Advanced Quotes) — HTTP prices keep working meanwhile. If "SDK has no DataStreamingClient" the bridge Python needs `paho-mqtt` (FIX SDK DEPS.bat pins it).

## 9/2 PM — popup P&L lag (G: "huge delay in pnl at the popup")
Cause: /positions served Webull's positions endpoint (cached 8s, broker mark lags) and the popup asked every 4s → 10–15s stale. Fix: /positions now overlays the quote bus bid (1/s) for options and the MQTT push for stocks onto every row (`live_quote: true`); broker numbers only when nothing fresh. Popup refresh 4s→2s. Extension 3.5.3 — reload it in chrome://extensions.

## 9/2 14:20 — THE quote-bus bug ("pulling data but not fast")
Symptom: sweeps every 1.9s instead of 1.05s, budget bucket pinned at the 40-token reserve, positions endpoint 429s. Diagnosed with `/stream` (new `budget_takes`/`budget_callers` tell): 9 budget takes per sweep, all from ask_bid_many.
Root cause: ask_bid_many passed the SDK's requests **Response object** to `_parse_batch` instead of `.json()` → every shape looked empty → the hunt walked all 8 shapes on every method every sweep, then fell back to per-contract calls ("batched option quotes not available" was printed every restart — it was never the SDK). Fixed: `.json()` + status check + TypeError skip. Result: sweep 124ms, 1 call per sweep, budget full.
Also: `_try_calls` winner cache (positions/orders hunting cost 2-4 HTTP calls per poll into a 2-per-2s endpoint → 429 wall at 14:0x); `ask_bid` remembers its winning method+shape; `_parse_batch` matches a symbol from any string value in the row.
Verify any time: http://127.0.0.1:8787/stream → `last_sweep_ms` ~100-200, `budget_takes` ≈ 2×`sweeps`, `budget_left` ~280.
Note: every bridge restart cancels+re-places the resting stop on restored positions (3 times today). Not stacking, but each is a brief naked moment — restart only when it matters.

## 9/2 14:25 — restart keeps the resting stop (G's ask)
reconcile_gone: on the first broker confirmation of a RESTORED position, `order_status(stop_order_id)`; if "working" the stop is kept and only the watchdog starts ("stop still resting at Webull at X — kept as is"). Anything else → `_arm_stop` as before. Proven 14:25:37 on SPY (stop 3.14 kept). Ratchet moves unchanged (cancel+replace only when the price must move).

## 9/2 14:35 — RULE: check before redoing (G: "do that to everything")
Principle: before any cancel/re-place/re-hunt, ask the broker/SDK whether the thing is already there. New helper `Book._stop_still_resting(p)` (order_status(stop_order_id) == "working"). Used by: restore-after-restart (14:25) and now `rearm_overnight_stops` at 9:31 — a GTC stop that survived the close is kept, not cancelled and re-placed (closes the 9/2 "GTC stops accepted" watch item). Already following the rule: ratchet replace-first (B4), quote/positions/orders winner caches, bus-before-direct-quote in the watchdog, stream-before-HTTP for stock prices. Still legitimately "redo": stop moves (price must change), averaging-in (size changes), fill-time arming (nothing exists yet).
Applies at the next restart (code watcher: safe window or the close).

## 9/2 14:36 — P&L faster than the 1/s option door (tick interpolation)
Webull option snapshot = 60/min per key, no option streaming. Answer: the bus stamps every swept row with the underlying's streamed price (`_und_at_sweep`, `_und_sym`; QuoteBus `und_price` hook = STREAM.price). `/positions` walks the last real bid forward on SPY's tick stream: `bid + delta·ΔS + ½·gamma·ΔS²` (delta/gamma from the snapshot row). Popup shows "≈3.31" for an estimate, plain number for a real quote; popup refresh 1s; `und_now` in the row. Stops/ratchet/watchdog use REAL quotes only — the estimate is display-only. A second app key would double the door to 2/s (his to create). Extension 3.5.4.

## 9/2 14:50 — market-open sweep (G: "check any other mistakes")
- **Announcer was OFF 13:27→14:24** (a non-empty announcer.stop after its 13:26 boot; only STOP ANNOUNCER.bat writes one). The 14:07 SPY fill never posted. Nobody could see it. Fix: bridge `/mode` now reports `announcer_alive`/`announcer_age` (heartbeat .announcer.alive < 120s) and the popup's bridge line says "· announcer on" or red "✕ ANNOUNCER OFF — run ANNOUNCER.bat". Extension 3.5.5. Rule: never write announcer.stop to restart it — use announcer.restart.
- AAPL alert AI-read twice 2s apart (14:43). Harmless today (buying power), and the `_place_impl` ECHO guard already refuses the same contract OPEN within 20s — I briefly added a second dedup, found the existing one, removed mine. Watch: why the same alert reached the reader twice (embed re-render vs. two rooms) — needs the extension log.
- `_expiry_age` strptime("%m/%d") without a year: Python 3.15 will break it; year now pinned explicitly.
- Positions endpoint still 429s ~4 per 10 min (broker_positions + futures_positions + probes). Low impact (cached row served); noted.
- Announcer adopt-at-boot 429 item: resolved (14:25 boot adopted 1 position first try).

## 9/2 14:55 — ANNOUNCER PAUSED (G: "put the announcer off for a while, get this app working 100% first")
announcer.stop = "stop" (revive task and START HERE step 4.5 both honour it). Bridge reports `announcer_stopped`; popup shows grey "announcer off (paused)" instead of the red warning. To bring it back: ANNOUNCER.bat (clears the stop file). Focus now: the sniper itself.

## 9/2 15:10 — in-position sweep #2
- **BUG: restart armed a stop on HIS OWN adopted trade.** 14:07 SPY 767C x1 adopted as "your own — no auto-stop" (8/18 rule); the 14:11 restart's restore path armed a 3.14 stop anyway; 14:54 a room's exit call sold it at 3.24. Fixed: restore path now honours `adopted` + no stop id → confirm and stay hands-off. OPEN QUESTION for G: adopted hand trades are still "closeable on the room's call" by design — keep that, or make his own trades fully untouchable?
- Combo entry tried the STOP_LOSS_LIMIT leg first — refused by Webull every time since 8/20 — then STOP_LOSS. One wasted order call per entry while racing a room. STOP_LOSS first now.
- IWM 294C 0DTE @0.18 (ZT bot, 15:05): bid worked 90s, no seller, pulled clean. QQQ 710C x4 = his, left alone (> bot size). Tape follows QQQ 710C for the popup.
- Throttles since 14:55: positions ×4, order detail/history/open ×3 each, place ×1 (the LIMIT leg). "Invalid account or insufficient permissions" ×2 — likely the futures account id on an options endpoint; watch.

## 9/2 15:12 — TODO (G, "later"): MANAGE button for hand positions
His QQQ 710C x4 (hand-bought, +17%) got no ratchet: adopt() leaves anything above bot size alone, and adopted trades never get a watchdog. Build: popup "MANAGE" on a broker row → bridge adopts it into the book with ratchet ON (stop_below at the current tier, resting stop + watchdog, exits only by ratchet/emergency). Real-money: placing that first stop needs his click. Also pending his answer: hand trades closeable on a room's exit call, or untouchable.

## 9/2 EVENING — daily journal-and-fix run #2 (16:55-17:40, automated)
Journal: journal-2026-09-02.xlsx (house format + the "Underlying at fill"
column, fees ACTUAL from the API's per-order fee arrays = $6.29, not an
estimate). Broker truth: bot -$62 on 3 closes (FLR -9 hand-closed, AMZN -22
clean stop, SPY 766C -31 hand-closed after the naked-exit bug); Gian +$114
gross on 9 hand trades (QQQ 706P x7 +126 and SPY 767C x20 +120 carried it,
the other seven -$132, one of them the bot's own sale of his SPY 767C 9/9 at
3.22 = -27). Account +$52 gross / +$45.71 net; Webull's own day figure
+$31.97 (marks FLR from 9/1's close). Open overnight: IREN 40C 9/18 x1 @2.45
(The Market Bishop via the mashup; their 42C -> our 40C by NO-OTM), GTC
stop-limit 1.85/1.65 resting at Webull (order O7G6OBKV9K5G2I5AN7HT2PMO6B),
mark -$6.50, plus the bridge watchdog. Buying power ~$113.

What the journal exposed -> FIXED the same evening (bridge restarted itself
onto the build at 17:12, IREN's stop kept, tests green: test_positions,
test_resolve; py_compile + node --check on every touched file):
1. NAKED AFTER A REFUSED EXIT (11:43 SPY 766C, five minutes with no stop):
   claim() pulls the resting stop before any sell; every refusal path then
   called release(), which only cleared the flag. release() now re-arms a
   stop that claim() itself pulled (remembered as pulled_stop) — TEST-room
   refusal, Refused, exception, all of them. rearm_stop_after_failed_exit
   also refuses to invent a stop for an adopted trade that never had one.
   The watchdog's own stop-out loop passes rearm=False (it re-claims next
   tick). _pullback_close's live flag was already carried through by the
   14:56 build.
2. "PRICE I NEVER SAW" = A 429, NOT A MISSING FILL (FLR, SPY 766C today;
   S, SPY, SPY yesterday — six $0 bookings in two days, every one of them
   a TOO_MANY_REQUESTS on /trade/order/history, 2 per 2s, shared with the
   announcer's poll). _broker_exit_price now tries twice 2.2s apart; if
   still empty the trade is booked and a background _true_up_exit keeps
   asking (6s apart, up to 3 min), then writes the real print onto the
   record — event "TRUED UP: the broker printed X for that exit" — exits/
   trade_pl/closed_why, matched by key AND sent_at so the next trade in the
   same ticker can never take it. Day file and state photo follow.
3. NOT ON THE BOOK = NOT THE BOT'S TO SELL: plan_exit's "st is None ->
   send the sell anyway" is gone (see the watch item). The 11:13 NVDA 417
   class is extinct; so is the hand-size hole.
4. SELL WHAT IS HELD: a room's exit naming the strike THEY called ("out
   IREN 42C") while the bot holds the NO-OTM-translated one (40C) now sells
   the held contract (the book resolved the exit to their position; the
   record's strike/expiry/side win). Used to 417 four times and leave the
   real position standing with its stop pulled.
5. SYMBOL-AWARE TICKS AT THE CHOKE POINT (webull_options._order rounded to
   the nearest NICKEL with no symbol): IWM 0.18 bid went out at 0.20 (+11%
   over the caller on a penny name), AMZN 2.41 at 2.40, the 2.11 stop at
   2.10, the 2.17 born-stop at 2.15 — while every log line printed the
   number it meant. Now: buy() FLOORS a resting bid (their price or
   better survives rounding), CEILS the pullback's ask-cross (stays
   marketable), sell() floors (one tick more marketable), _order rounds
   symbol-aware as the legal backstop. tick_floor/tick_ceil added.
6. AI READER: a "premium" at/above the strike is the stock level, not the
   option ("adding at 224.70" on a 225C read as @224.7) — dropped, the
   bridge bids the market.
Extension 3.5.6 (RELOAD in chrome://extensions — G's hands):
7. A SYMBOL-LESS "OUT" CAN NEVER LAND ON HIS HAND TRADE: guards.pickHeld
   treated "the only position, owner ?" as anyone's. 14:54 a caller's "I
   took my $126 L" (no ticker, the caller's loss) matched G's adopted SPY
   767C 9/9 and SOLD it at 3.22 (-$27). Adopted records now carry the
   bridge's `who` (trader name or "Gian"); an adopted record owned by "?"
   or Gian is never the answer to a bare exit, in pickHeld or the
   loaded-symbol fallback. A bot trade re-adopted after a restart keeps its
   trader and still matches its own caller.
8. MASHUP ATTRIBUTION FROM THE FOOTER (see the 8/31 note above) — the
   possessive-title hunt never matched the live relay format.
9. HEARTBEAT RELOAD LOOP: one room tab was reloaded 174 times 13:25-17:11
   (every ~80s) because its beat never returned — the record was stale
   (the tab had moved to another page) and the watchdog kept punishing it.
   Now: a tab whose URL no longer names the channel drops the record (no
   reload); genuine dead readers back off 1m/2m/4m/8m/15m with the attempt
   count in the log line.
ALSO: test_signals.py has 4 failing checks that PREDATE tonight (Brett's
"Out of 80%"/"Tapped 40%" TRIM reads and two "Stops moved to $208.30"
STOPMOVE resolutions) — expectations written 8/15, before the 8/30 exit
policy; not a regression, needs a look when the parser is next touched.

HAND TRADES ARE UNTOUCHABLE — RULE (G, 9/2 evening: "how do they manage
to close them? they shouldn't"). HOW they could: adoption. Anything in the
account the bot didn't place, up to 3 lots, was pulled onto the book as
"?|SYM" (owner unknown) so a room's exit could re-find the bot's OWN trade
after a restart (the 8/18 rule, written before the state photo existed).
find_key then handed ANY trader's "out SPY" to "the only SPY on the book,
unattributed" — his. Closed at every door: Book.is_hand_trade() = adopted
with no inherited trader (who "Gian"); find_by_symbol(rooms=True) leaves
those out of every room-side lookup (find_key, the bare-exit resolver);
plan_exit / TRIM / STOPMOVE refuse them outright ("that's YOUR own trade
— rooms can't close or trim it"); the extension (3.5.7) refuses before
the round trip. Still HIS in the popup, still no stop, still counted in
the journal under Gian. A bot trade re-found after a restart carries its
trader's name (credit inherited) and stays closeable by that room — that
is what adoption is for now. The 8/18 "closeable on the room's call" rule
is RETIRED. The MANAGE button (15:12 TODO) stays the only way to hand one
of his positions to the ratchet, and it needs his click.

ANNOUNCER (paused by G at 14:55, announcer.stop="stop"): before the pause
it posted only the 11:35 SPY 766C ENTRY today — it was down 11:17-11:35
(stop-file restarts) and missed the AMZN round trip, and the 14:25 boot
never posted the 14:54 SPY 767C sale before signing off at 14:56 despite
"push: subscribed". When it comes back (ANNOUNCER.bat): verify an EXIT
post, and cut its 2s history poll to a 30s safety net while push is up —
that poll shares the 2-per-2s history budget the bridge's exit lookups
(fix #2) need.
DEATHWATCH: Options Insider ($199+tax) — last message 8/12 (TSM 430C
swing); 21 days silent on 9/2, tab open, silence alarms firing daily.
Cancel call at day 30 = 9/11 unless it posts. RWGates (TradeLikeGates,
STS alert-room): alive, 28 captures today, NBIS 215C called 9:44.
CHROME: no "out of memory", no "DISCARDED" lines today; memory shed and
the discard pin are holding. START HERE's fresh-start closes stale Whop
tabs on next launch.

## 9/2 18:40 — ROOM SCOREBOARD (scoreboard.py → SCOREBOARD.html, artifact "discord-sniper-room-scoreboard")
Built from DS Logs exports (every message the reader saw + bot verdicts) and days/*.json. Re-run any time: `python scoreboard.py 10`. Findings: Honeydrip daytrades is the loudest real room (107 signals/10d, 17 bot sends, 4 filled, −$15); ZT mashup 61 signals, 8 filled. Whop rooms ARE read now (Day Trades 53, High Risk 41, Futures 35 signals) but send 0 — Felony calls NQ futures and every futures broker is OFF. "NGD: ngd-trades" (Ninjago Futures Radar bot, MGC) shows 86 signals and is NOT in rooms.txt. 6 configured rooms silent 10 days. Trader board from the trade table.

## 9/2 19:20 — WHY ROOMS ARE SILENT / UNLISTED (G's ask) — findings + fixes
- **BUG FIXED — Discord "Server Tag" junk broke the parser.** Discord's 2026 badge leaks into captured text ("Vero [PAID], Server Tag: PAID PAID SPY 763C 9/2 1.22 2 CONTRACTS…"). Vero's SPY 763C call at 10:18 today parsed as "nothing that means buy or sell" — no verdict, no order. RE_STAG strip added to parser.js cleanText + signals.py clean_text (both sides of the call, with role word + dash-timestamp). Extension 3.5.8 — reload. test_signals: same 4 pre-existing failures before/after (Brett trims), none new.
- **Options Insider (server 719580371997556737): "NO TEXT CHANNELS — you don't have access."** Membership/role lapsed. Nothing to read until he rejoins. Remove from rooms.txt or renew.
- **RWGates / Summit alert-room:** posts are commentary ("$META entries called out in the LIVE trading", "$AAPL next ?") — his real calls are in the live voice room. Text room will always look silent.
- **Platinum equity, Boka 2 (equity-alerts):** SHARES swings ("added $AXTX shares for a swing") — the bot trades options/futures only. Not silent, just not ours. Boka 2 last post 8/24.
- **Vero 2 (vero-trades):** Vero posts ~weekly (8/21, 9/1). Reader fine.
- **Whop Swing:** Felony last posted 8/27. Whop 2K Challenge: image-only posts, one re-sent every ~6 min → 36 vision calls today. Bridge `/readimage` now hashes images+caption and answers repeats from a 24h cache.
- **Whop Day/High Risk/Futures:** read fine (53/41/35 signals) — Felony's NQ futures calls; all futures brokers OFF → nothing fires (a switch).
- **"Rafita Trades" 1537061197931618344 is actually NGD #ngd-trades (Ninjago Futures Radar bot, MGC).** Relabelled in rooms.txt. Futures → also gated by the OFF brokers.
- Unlisted-but-signaling = the old individual ZT rooms (last 8/28, covered by the mashup) and Sniper HQ (our own announcer server — must never be traded). Fine.

## 9/2 20:00 — "why aren't we finding bugs like these when I tell you to run everything?"
Honest answer: "run everything" tested plumbing (bridge, bus, stream, unit tests with canned phrases). It never replayed the day's REAL room messages against what the bot decided. Now it does:
- **replay_check.py** — every captured message today → signals.parse → cross-checked with extension verdicts + bridge.log; lists SILENT DROPS per room. Wired into the 16:45 daily task (step 4) and into any "run everything" from now on. RULE: a silent drop in a LIVE room is a bug until proven otherwise.
- **Corrections to my 19:20 findings:** RWGates IS read and traded — his `.NBIS260904C215` dot notation parses (PREPARE on "loaded", OPEN on "took entry … Fill: 1.80", ADD on "adding"); 9:44 NBIS was AI-read, strike-translated to 205C and REFUSED for buying power ($511 vs $157). My scoreboard regex missed the dot notation — the scoreboard was wrong, not the bot. Options Insider stays configured (G may rejoin).
- **Extension log cap 400 → 2500**: the 400 cap meant today's export had NO verdicts before 10:51, so morning misses (e.g. Nitro "Entry Contract: TSLA $350p Price: $1.59" 9:38 — parses OPEN, no bridge line, no verdict) can't be audited. Tomorrow they can.
- **Fresh ≠ history (content.js)**: a discarded/reloaded room tab filed every on-screen message as history, including calls seconds old. Now a message < 3 min old is live regardless of reader start; the stale gate still refuses older OPEN/ADD.
- **OFF rooms are loud**: a room switched OFF in the popup now logs once/hour when a real call is dropped, and the export's CURRENT STATE lists OFF rooms and SHADOW rooms.
- ZT mashup readings today: ORCL 147C (refused $), AMD (refused $), TSLA 360C lotto (pullback hunt), SPY (refused $), IWM 294C (bid 90s, no fill), SPX 7665C (ignored — SPX→SPY not enabled for the mashup channel), IREN 42C (sent → 40C held), SLV 60C (refused $ at 15:59). ZT is read.
- Cosmetic: bridge answers a buying-power refusal with HTTP 502 → extension logs `<failed>` instead of `<skipped>`. Fix later.
Extension 3.5.9 — reload.

## 9/2 20:40 — Blue Collar template + voice audit + the self-learning loop
- **BUG FIXED — Platinum Blue Collar's template never parsed.** "Challenge Account LONG SETUP Ticker: SPY Contract: 764 C Entry Zone: .50 Risk: 20% Stop TP1: 20% TP2: 763.93" hit the "that percentage is their risk" bail before the contract was read; also ".50" (leading-dot premium) never parsed as 0.50. Both parsers: labelled template → "BTO SPY 764 C @ 0.50" (only when BOTH Ticker: and Contract: labels are present — ZT's "Entering Option" and Nitro's "Entry Contract:" keep their own rules); risk bail only when the line names NO contract; leading-dot premium → 0.xx. Test cases added to test_signals.py (Blue Collar ×2, Server Tag, risk-only). Suite: same 4 pre-existing failures. Extension 3.5.10.
- 9/1 11:05 Blue Collar SPY 764C: no AI READ in bridge.log and the 9/1 export's verdicts were wiped by the 400 cap → cannot say whether the AI reader was consulted. Cap now 2500.
- **Voice today:** 238 transcript lines, all from Honeydrip's live room 10:55–11:25 (Unraveller commentary: "first break of EMAs on SPY", "if you shorted SPY use 765.8 as risk"). Zero spoken entries with a full contract → nothing to fire; parser's bare-% "trims" on speech are harmless (exit policy ignores trims). Listener cycles on/off with the audio (quiet 60s → stop). It also auto-listened to OUR #sniper-alerts-options tab (notification pings) — now skipped.
- **Self-learning loop (G: "everything should learn from mistakes")** — what's real vs. planned, see reply.

## 9/2 21:30 — COLLECTIVE CORPUS PASS (G: "exchange parsers room to room, fill the parser blanks")
There is ONE parser for every room (extension/parser.js; signals.py mirrors it for tests/tools). Per-room settings are only behaviour flags (SPX→SPY channels, Whop bare-% trims, exit policy) — grammar learned in one room applies everywhere. What was missing was a collective CORPUS to test it against; now:
- **jsparse.py + extension/parse_batch.js**: audit tools (replay_check, scoreboard) run the PRODUCTION parser via node, never the Python mirror (which lagged — it called "Open SPY 09/01 764P @.95" nothing while the bot read it fine).
- **13 days × every room replayed** (1,228 contract-naming messages). Blanks 547 → 365; the rest are updates/watchlists/recaps by design. Formats added to BOTH parsers, with tests in test_signals.py and samples.txt (parity):
  • Clutch date-first entries "0DTE GOOGL 345C .84", "8/28 SLV 60C 1.68 swing", "Swing: 9/04 SMR 10C .54"
  • ei.trades "Contract: QQQ $711 p Price: $1.68" (no "Entry" label)
  • TLM "Aapl Aug 26 315 call at 1.75" (bare priced contract, no verb)
  • Aristotle "I'm in 80 C 9/18s for uber" (ticker after the contract, "for")
  • Felony "Short NQ @ 29530 Stop 29570 Target 29450 <essay with 'if you'>" (order head kept, commentary dropped)
  • NGD radar "MGC SHORT (1m) @ 4496.35 | TP:… SL:… | Prob:…" (rewritten to the futures grammar; "probability" veto no longer kills it)
  • Mr. Top Hat "MNQ 24674 long quick scalp", "MES quick short here 7697"
  • Bot footers stripped before veto words fire: "Do not take this as financial advice" (vetoed EVERY Market Guru call), "None of this is financial advice" (Clutch), "For Educational/Informational Purposes Only", "© 2021-2026 Horizon Analytics", "How I Trade…", "@Namrood - Live…"
  • Discord row junk stripped: "NAME APP — 9:44 AM Wednesday, September 2, 2026 at 9:44 AM Forwarded", "[ 9:38 AM ] …", "Yesterday at", "N Add Reaction", "(edited)", ":green_alert:" shortcodes — these also made "loading GOOGL…" lines look like ENTRIES in the export replay (LOADING never buys; now PREPARE)
  • **SAFETY FIX — partial sells are TRIMS**: "sold 1/2 UPS", "sell 2/3 UPS 105 calls", "sold some… holding the rest" read as a FULL exit → would have flattened a position the trader only trimmed. Now TRIM with pct. "sold the rest/all" stays CLOSE.
  • "closed AAPL for +20%", "QQQ OUT @ 150% PROFIT", "sold NVDA at +35%" read as 20%/150%/35% TRIMS (ignored by exit policy) → now full CLOSE ("they posted the gain, not a trim size").
- Suite: test_signals same 4 pre-existing failures (Brett trims); parity 5 pre-existing field gaps; test_resolve green. Extension 3.5.11 — reload.
- replay_check now flags only OPEN/ADD/CLOSE silence (PREPARE/trims are silent by design). NGD's 86 radar signals/day are OPENs that go nowhere because every futures broker is OFF — a switch, noted.

## 9/2 22:00 — "one collective parser?" — it already IS one; the per-room stuff is PERMISSIONS
There is exactly ONE grammar: extension/parser.js (signals.py mirrors it for tests/tools only). No room has its own parser and never did — a format learned in one room works in all 26. Nothing to merge or delete.
What IS per-room is routing/permission, not reading:
1. `channel_live` — LIVE (real money) vs TEST. HIS switch.
2. `channel_disabled` — room OFF (drops everything; now logs once/hour when a real call is dropped).
3. `SHADOW` (hardcoded in background.js) — read + graded, FIRES NOTHING. Probation.
4. `spx_entry_channels` — only Boka 3 may fire SPX as SPY.
5. `bare_pct_trims=false` for Whop — a bare "20%" there is a progress update, not a trim.
Those 5 should stay: they're money controls, not parsing.
**THE REAL FINDING — the SHADOW list is what's costing signals.** 6 rooms on probation since 8/23: Platinum-1 (nitro), Platinum-2 (futures-alerts), Platinum-3 (day-trades), Platinum-4 (ei-alerts), Platinum equity-swings, NGD ngd-trades. **106 entries in the last 10 days were read, graded, and never fired** (NGD 89, nitro 11, futures-alerts 4, ei-alerts 1, day-trades 1). This — not a parser gap — is why the scoreboard showed nitro "40 signals / 0 sent" and NGD "86 signals / 0 judged".
Correction to the 9/1 Blue Collar SPY 764C mystery: Platinum day-trades is a SHADOW room, so it could never have fired anyway. The parser bug was real and is fixed, but the room is on probation.
Also note: Platinum day-trades appears in BOTH channel_live and SHADOW — shadow wins (returns first). Graduating it would make it fire LIVE. G's call.

## 9/2 22:10 — SHADOW LIST CLEARED (his call) — and all 6 are flipped LIVE
Removed all 6 ids from SHADOW in background.js; the mechanism stays (add an id back to re-benchmark a room). Extension 3.5.12 — reload.
**IMPORTANT:** the extension's own export (CURRENT STATE, the truth — extension config lives in chrome.storage.local, NOT settings.json) lists every one of these as a LIVE room: Platinum nitro, Platinum futures-alerts, Platinum day-trades, Platinum ei-alerts, Platinum equity, NGD ngd-trades. SHADOW was the only thing stopping them. From the next reload they place REAL orders. Realistic exposure: nitro ~1 entry/day; day-trades/ei-alerts ~1 per 10 days; futures-alerts + NGD are futures and every futures broker is OFF, so they still fire nothing; Platinum equity posts SHARES (bot trades options/futures only). Buying power ($100-160 free) refuses most of it anyway.
G should flip any of these to TEST in the popup if he wants them papered first.

## 9/3 11:00 — IWM never opened + POSTCHECK after every trade (G's ask)
**IWM answer:** nothing closed it — it never opened. 10:48:36 ORDER IN BUY 1 IWM 294C 9/4 @1.24 (stop 1.12 born with it) → WORKING → 10:50:08 NOFILL, nobody sold at 1.24 in 90s. Broker truth confirms: client_order_id a1cbf9e0…, status CANCELLED, filled_quantity 0; the stop leg cancelled with it. He is NOT in IWM.
**BUG FIXED — trims were journaled at the BID, not the broker's fill.** WMT 108C 9/25: bought 2.17 at 10:14, their trim sold it at 10:35 — the broker filled **2.21**, the book wrote **2.17**, so a +$4 trade journaled as +$0. `trim()` used `p["last_bid"]`. Now it asks `last_sell_fill()` after the sell lands and uses the real price (same lesson as the 8/27 phantom exit), and says so in the log when they differ.
**BUG FIXED — fill-poll wasted a doomed call every poll.** `order_status` hunts methods containing "get_order", which also matched `get_order_OPEN(account_id, page_size)` — so every poll sent our order id as page_size and logged "invalid page_size, value: <order id>" 417 (32 times in the log). `_try_calls` now takes `_avoid=[...]`; order_status avoids open/history/list/batch.
**NEW — POSTCHECK.** A thread watches the book for terminal events (filled, closed, stopped, nofill, trimmed, failed) and 6s later checks, in one log line: quote-bus sweep time + rate-limit backoffs, price stream connected, EVERY held position has a stop that is actually "working" at Webull, book vs broker parity (ghosts), bot-recorded exit vs the broker's real fill (the WMT check, flags a P&L gap ≥ $0.02/contract), and broker error count since the last trade. Output: "POSTCHECK FILLED WMT — all good: stop resting at Webull, quote bus fresh, stream up, book matches the account", or "— PROBLEM: …". Adopted (his own) and futures positions are skipped for the stop check by design.
