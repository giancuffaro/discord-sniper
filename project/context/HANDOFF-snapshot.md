# DISCORD SNIPER — THE HANDOFF
Read this first. It is the living memory of the project: what the machine is,
every rule it trades by, and how G works. Update it whenever a rule changes.
Last updated: 2026-09-03 18:05 (ran the missed-entry scan retroactively
across every day since the bot went live — 4 more historical RWGates
misses found, see bottom section). Prior: G: "can we add this kind of
scan for missed entrys after every signal? we need to be catching these"
— built a live,
real-time missed-entry watcher (extension) PLUS a batch version wired into
replay_check.py (autopilot). Extension 3.5.15 — RELOAD IT.)
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
- SUPERSEDED 9/3 — STANDING RULE: ENTRIES ONLY (G, 9/3): the bot follows
  room ENTRIES (and adds) ONLY now — the 8/30 "full exit fires as the
  emergency word" carve-out above is retired. Every room-side exit (trim,
  stop-move, "all out", "stopped out", "closed everything") is logged
  ("EXIT-IGNORED ... — entries only") and NEVER traded; the ratchet's own
  resting stop at Webull is the ONLY exit (plus the bridge's own pullback
  stock-stop / underlying hard-stop, which carry a "source"). A bot SELL
  that traces to a room trim/close is a BUG: check bridge.py do_POST's
  EXIT-IGNORED gate (order.get("source")), extension/background.js's
  TRIM/STOPMOVE/CLOSE gate before sig.fire, and settings.json
  execution.exit_policy != "full". Gate verified LIVE today (EXIT-IGNORED
  fired correctly on SPY at 12:42 and 13:48).
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

## 9/3 11:45 — SYNC WATCH (autopilot): TWO BUGS FROM THE 10:53 BUILD, BOTH FIXED
**BUG 1 — order_status answered "unknown" for EVERY order since the 10:56 restart.** The 11:00 fix said "`_try_calls` now takes `_avoid=[...]`" — but `_try_calls` never consumed it. `_avoid=` went into every SDK method as a kwarg → TypeError → skipped → body None → "unknown". Cost today: **SPY 771P 9/4 (ZTRADEZ, 11:10:51)** — the bid FILLED at 2.02 within 1s (broker: 250995d2…, FILLED 15:10:53Z). The pullback stock-stop fired 11:12:05, `cancel_entry` got ORDER_CAN_NOT_BE_CANCEL, probed 4× → "unknown" → logged PULLED "you own nothing here". The born-with stop then sold the real contract at **1.87** (5ec4d5aa…, FILLED 15:13:36Z). **Real trade: −$15, NOT in days/2026-09-03.json (state nofill, qty 0) — the close-out journal must add it (exit trigger = ratchet stop).** Same bug: C 139P fill was only found at the 90s deadline via positions() (95s lag), and POSTCHECK's "C stop 3b88fc80 is 'unknown'" was a false alarm — the stop is SUBMITTED at 1.24 at Webull. Fix: `_try_calls` pops `_avoid` and skips methods whose name contains any of those words (unit-checked: returns filled/1.0/2.02 with get_order_history skipped). Also `_watch_fill` now probes on the client that owns the order (`wb=self._wbfor(p)`) like the deadline path does.
**BUG 2 — the bridge's ENTRIES-ONLY backstop was dead.** The gate was `and not order.get("source")` — but the extension stamps `source:"discord-extension"` on EVERY order, so no room exit was ever gated at the bridge. 11:00:43 "CLOSE NVDA" walked past it and only stopped at BLOCKED "no strike/expiry". Now only the bridge's own sources ("pullback", "under-stop") are exempt. That CLOSE also reached the bridge at all → the extension in Chrome is still pre-3.5.12 — **G must reload it (chrome://extensions).**
Tests: py_compile clean; test_positions 0 fails; test_signals the 4 known Brett-trim fails; test_resolve OK. Bridge restarts itself at the next safe window (C 139P held with its stop — kept and RESTORED).

## 9/3 15:25 — SPY + C post-mortem (G: "C lost a lot… I closed SPY manually")
Broker truth, all three of today's bot trades:
- **SPY 772C 0DTE (the one he closed): +$33, and THE RATCHET WAS WORKING.** Filled 1.23 at 13:36:40 (stop born at 1.11). 13:51:56 up 18% → stop to 1.23 (breakeven). 13:52:36 up 25% → stop to 1.35 (+10% locked). He sold at market 1.56 at 13:56:08 — better than the 1.35 stop, so closing by hand cost nothing. Note: the broker shows those ratchet stops at 1.23 and **1.42**, the log printed 1.35 — the log prints the plan price, not the tick-rounded one actually placed. Cosmetic, logged for the journal.
- **C 139P 9/4: −$52 (−31%), and OUR OWN STOP closed it, not him.** Filled 1.66 at 11:34:56 with a −25% stop at 1.24 born with it. Stop FILLED 15:12:13 at **1.14** (STOP_LOSS = market on trigger, so 10¢ of slippage below the 1.24 trigger). The ratchet never armed because C never reached +15% (1.91). The book said "gone from your account — you closed it yourself, at a price I never saw" — **wrong, and now fixed** (below). Open question for G: C 139P expiring 9/4 was classed a SWING and got the wide −25% stop; a scalp stop (−10% = 1.49) would have cut the loss roughly in half. Worth deciding whether 1-2 DTE should ever be a swing.
- **SPY 771P 9/4: −$15, and this is the serious one.** 11:10:51 the bid went in at 2.10; **Webull FILLED it at 2.02 at 11:10:53**. At 11:12:12 the pullback's stock-stop fired, cancel_entry ran, the order probe said not-filled and the book announced "your bid never filled… you're flat on it." The position then existed at the broker, outside the book, for four hours — nothing watching it, no ratchet. The only thing guarding it was the stop leg born with the order, which fired at 15:13:36 at 1.87.
### Fixed (all three live at 15:22)
1. **cancel_entry now asks the ACCOUNT before saying "you own nothing."** The 8/26 confirm-the-pull loop only re-probed the ORDER; an order probe can be throttled or hit a renamed endpoint, the positions list can't. If the account holds it, the book takes it back and manages it.
2. **reconcile_gone checks OUR OWN stop first.** If `stop_order_id` is FILLED at the broker the trade is recorded as STOPPED at the real fill price — "your resting stop fired at Webull and filled at 1.14 — that's what closed it, not you" — instead of blaming him and losing the price.
3. **POSTCHECK now watches pulls and hunts ORPHANS** — a contract the ACCOUNT holds that the book thinks is closed. That is exactly the SPY 771P shape and it would have shouted within ~9 seconds instead of four hours.

## 9/3 15:45 — "the ratchet is supposed to be armed from the start" — what actually happened on C
Two different things were both being called "the ratchet":
- **The protective stop IS armed from the start.** C had a resting stop at Webull from the moment it filled (born with the order, 11:34:35). That never failed.
- **The ratchet is the thing that MOVES that stop up**, and it only has something to lock once the trade is green. For a $1–2 contract the tier arms at **+15%**. C's bid, tracked in 12,189 tape quotes from 11:47 to 15:22, topped out at **1.74 = +4.8%** off the 1.66 fill. It never had a gain to protect, so it correctly never moved.
**The real bug was the stop DISTANCE, and it is fixed.** ZTRADEZ Manager's call was labelled a swing, so C got the swing's wide **−25%** stop (1.24) — on a contract that expired the NEXT DAY. The 8/25 auto-swing rule promotes 14+ DTE to swing but nothing ever demoted a near-dated "swing". Now: **expiry ≤ 2 days = scalp, whatever the room called it** ("SCALP C — they called it a swing but it expires in 1 day… keeping the tight scalp stop"), and any caller stock-level is dropped with it. On C that would have been a −10% stop at 1.49 instead of 1.24 — roughly −$21 instead of −$52.
Live at 15:43. Open decision for G: the tier ARM thresholds (<$1 arms +25%, $1–2 arms +15%, ≥$2 arms +10%) are unchanged — that's a strategy choice, not a bug.

## 9/3 15:55 — RATCHET LADDER RESTORED TO G'S RULE (his words, 9/3)
"It was supposed to start all along from -10% and +10%. When it touched +10% the new stop becomes automatically 0%, and the next target is 20%. When 20% is touched the new stop is +10% and the new target is +30%. When +30% is touched the new stop is +20%, and so on and so forth."
The 9/2 price tiers are RETIRED. `ratchet_tiers.TIERS` is now a single rule for every premium: **arm +10%, first lock 0% (breakeven), +10% a rung.** Verified: +10%→BE, +20%→+10%, +30%→+20%, +40%→+30%, +50%→+40%. The two safety floors stay (a rung must clear 4 ticks; the stop is never placed inside the spread) and they log when they move one of his numbers. test_positions updated to his ladder.
**ONE CONFLICT HE NEEDS TO SETTLE:** ANTI-CLIP (approved 9/2 off the 520-trade study) says the stop may never sit closer than 40% of the gain, so it CAPS his ladder above +20%: at +30% his rule says lock +20%, anti-clip allows +18%; at +50% his rule says +40%, anti-clip allows +30%; at +100% his rule says +90%, anti-clip allows +60%. Below +30% the two agree exactly. Anti-clip currently WINS. Asked; awaiting his answer.

## 9/3 16:25 — ANTI-CLIP SPLIT BY EXPIRY (his rule: "my rule on 0 and 1dte and anticlip on later expirations")
- **0DTE and 1DTE: his ladder, uncapped.** +10%→BE, +20%→+10%, +30%→+20%, +40%→+30%, +100%→+90%. A same-day contract has no tomorrow; theta eats whatever isn't locked, so the gain gets taken.
- **2+ days out: anti-clip applies** — the stop never sits closer than 40% of the gain (so +30%→+18%, +50%→+30%, +100%→+60%). Runners keep room to breathe (the 9/2 520-trade study).
- Unknown/unparseable expiry → anti-clip applies (safe default).
- When anti-clip moves one of his numbers it now SAYS so: "anti-clip held the stop at +18% instead of +20% (never closer than 40% of a +30% gain; 9 days out)".
- test_positions: existing +30% case (far expiry) still expects 2.36; NEW case proves a same-day expiry locks the full 2.40. Suite green.

## 9/3 16:35 — DAILY CLOSE-OUT (automated)
Broker truth, 5 bot closes + 1 Gian scalp: **bot day -$51.55 corrected** (was
booking $0/wrong on 3 of the 5 before today's earlier fixes), **Gian +$207.62**
(QQQ 710P x4, clean). Combined realized +$156.07 + XLF's +$3.95 unrealized
day-mark = **+$160.02**, matches Webull's own day P&L to the penny — FIFO
math checks out. journal-2026-09-03.xlsx built (house format); trader-
scoreboard.xlsx appended (ZTRADEZ BOT now 13 trades/-$136.55/AVOID,
👑KingBeeAri🐝 now 2 trades/-$71.12/WATCH); Webull_Orders_2026-09-03_auto.csv
written. Open overnight: XLF 58C 10/16 x1 @1.58, GTC stop 1.06/1.18 resting
at Webull (SUBMITTED), mark +$10.50, watchdog on. replay_check.py: **0 silent
drops**. scoreboard.py 10: 67 rooms heard from, 2 silent configured.
test_positions/test_signals(4 known Brett fails)/test_resolve/py_compile/
node --check: all green, no regressions, **no new code fixes needed today**
(every bug the journal exposed was already fixed earlier in today's own
sync-watch runs — see below).

**What the journal caught (all pre-date today's own fixes, none are new bugs):**
1. **WMT 108C 9/25 — ROOM EXIT-BUG, already fixed.** 👑KingBeeAri🐝's trim
   at 10:35 actually sold a real contract (the bridge's entries-only gate
   was dead until the 11:45 fix today). Also a ledger echo: journaled at
   the entry price 2.17 (+$0) instead of the broker's real fill 2.21
   (+$3.88 corrected). Gate confirmed working now — EXIT-IGNORED fired
   clean on SPY at 12:42 and 13:48, no repeat.
2. **C 139P 9/4 — already fixed.** Misattributed as a hand-close ("you
   closed it yourself... price I never saw") by the reconcile_gone bug,
   fixed today 15:22. Real cause: the bot's own -25% swing stop (1-day
   expiry mistagged swing instead of scalp, also fixed today 15:43) firing
   with 10c slippage to 1.14. Corrected: -$52.12.
3. **SPY 771P 9/4 — already fixed, but the historical record was never
   trued up.** cancel_entry declared this bid dead when the broker had
   already filled it 2s earlier; the born-with stop caught it blind 4h
   later at 1.87. days/2026-09-03.json still shows nofill/qty 0 and no
   TRUED UP line ever posted for it — added to the journal from broker
   order history by hand. Corrected: -$15.12.
4. SPY 772C 0DTE and IREN 40C — clean hand-closes by Gian (Market Sniper,
   "6a99..." client-id family), ledger just needed the real broker price:
   +$32.88 and -$21.07.

**Watch items (no code touched, flagging for the next session):**
- **IBIT 47C NOFILL (15:59) drew 104 broker 429s** in its 90s fill-watch —
  5 positions (WMT/C/SPY/XLF/IBIT-watch) were being polled concurrently
  and stacked past the shared per-endpoint budget. POSTCHECK itself called
  it "ok, with notes" (no missed fill, no wrong price) — not fixed today
  since it caused no harm and a rushed rate-limit change with nobody
  watching felt riskier than the 429s themselves. Worth tuning if
  concurrent-position count keeps climbing.
- **16:11 the extension auto-updated and reloaded** (cascading "reader
  detached, reloading" 16:11-16:12); the popup export captured seconds
  later (16:12:53) mid-reload shows "LIVE rooms: none (all testing)" —
  almost certainly a stale snapshot (real fills happened continuously all
  day including the 15:55 XLF entry, and bridge /mode + /rooms checked
  live via Claude-in-Chrome at 16:5x show the bridge connected and XLF's
  stop resting real at Webull). G should glance at the popup before
  tomorrow's open to confirm rooms are still LIVE.
- RWGates: zero captures today (was alive 9/2 with 28). Options Insider:
  still silent, deathwatch continues (cancel-by 9/11 unless it posts).
- Chrome: no DISCARDED/out-of-memory lines today. Clean.
- /stream (checked live via Claude-in-Chrome, 16:5x): connected true,
  last_sweep_ms 151.9, budget_left 284.5, budget_takes 888 ≈ 2×sweeps —
  healthy.
- Announcer: still paused (G, 8/31 14:55) — skipped per standing
  instruction, not re-enabled.

## 9/3 17:16 — RWGates wasn't silent: a real entry was silently dropped, fixed
G asked directly why his RWGates/Summit Trading Strategies ($189/mo) looked
quiet. It wasn't — checked the live room via Claude-in-Chrome and found two
real TradeLikeGates entries this morning that never made it into trades.log:
- **9:32 HOOD 260904C120 @1.83 — correctly read, correctly REFUSED** (buying
  power was $113, needed $251). Not a bug.
- **9:40-9:44 NVDA 260904C230 @1.37 — silently dropped, no REFUSED line, no
  trace at all.** He posted "Loaded $NVDA .NVDA260904C230" (PREPARE, parsed
  fine), then a few minutes later "$NVDA I took entry 1.37 fill" with NO
  contract repeated in that second message. Ran to +100% per his own 9:55
  recap; the account was never in it.

**ROOT CAUSE, found and fixed:** the two-message entry ("Loading X" then a
bare fill) is a known, handled shape — but only when the fill line itself
STARTS with a fill verb (filled/bought/bto/entered — RE_BARE_FILL) or starts
with "in" (RE_BARE_IN). RWGates' actual phrasing puts the ticker first and
"fill" at the END ("$NVDA I took entry 1.37 fill"), which is not in the verb
list and doesn't start the line — it fell through every branch to "sounds
like an entry but there's no full contract in it" and was dropped with zero
trace, not even a why-not log line.

**FIX (extension/parser.js + signals.py, mirrored; both compile-checked,
parity-checked against samples.txt, test_signals.py green + 3 new cases):**
new RE_TOOK_ENTRY_FILL branch — `\btook\s+entr(?:y|ies)\b...fill\b` — anywhere
in the message (not anchored to the start), sets needs_loaded + pins
named_symbol so resolveLoaded can't pair it with a different ticker's most
recent load (same safety rail as the existing "loose in" branch). Verified:
the exact NVDA text now resolves through the existing loading-shelf mechanism
(rememberLoading/resolveLoaded in guards.js — a 4-hour per-trader shelf that
already existed and already worked for RE_BARE_FILL/RE_BARE_IN, just never
saw this shape). test_signals.py: same 4 pre-existing Brett-trim failures,
0 new. test_parity.js: same 5 pre-existing gaps, 0 new. Extension 3.5.13 —
**RELOAD IT** (chrome://extensions) for this to take effect live; signals.py
is Python-tooling-only (bridge.py never imports it), no bridge restart needed.

**Not investigated further today:** whether other rooms use this same
"$TICKER I took entry $PRICE fill" shape (RWGates is the only one confirmed
so far) — worth a corpus check next time replay_check runs across more days.

## 9/3 17:31 — FULL 26-ROOM AUDIT (G: "double check every single room, I need all rooms firing correctly")

**IMPORTANT LIMITATION FOUND FIRST:** replay_check.py's "0 silent drops" this
morning was blind to all of this. Its whole method is "the parser assigned
an action (OPEN/ADD/CLOSE) but nothing downstream acted on it" — it has NO
way to catch a message the parser doesn't even recognize as actionable at
all (`action: null`), which is exactly the shape of every bug below. Built a
one-off heuristic instead for today (every raw message today, run through
jsparse, action=null AND contains an entry word + a price) — 731 raw
messages -> 11 suspects -> 3 real bugs, rest were false positives (analysis/
"WATCHING" chatter that happens to mention a price) or already-known-working
(RWGates' HOOD, resolved by the AI-vision fallback). This blind spot in
replay_check.py itself is unresolved — worth a proper fix (some kind of
per-room "expected signal rate" baseline) next time there's room to build it.

**3 bugs found and FIXED today** (all the same root shape — a fill
confirmation with no strike, where the strike was named in an earlier
LOADING message; all now pin `named_symbol` so they can only resolve against
that SAME trader's SAME ticker, never a different one they also loaded):
1. RWGates "$TICKER I took entry $PRICE fill" (NVDA 230C, see above).
2. Unraveller/Honeydrip "$TICKER avg $PRICE" ("Meta avg 5.7" — the RE_AVG
   branch used to always say "nothing to do with it," now checks the
   loading shelf first when a ticker is named).
3. Unraveller/Honeydrip "Filled $PRICE ... on $TICKER" ("Filled 2.26 starter
   size on AAPL" — RE_BARE_FILL used to disable ITSELF the moment a ticker
   appeared in the message, on the theory a named ticker meant something
   else was going on; it fell through to the stateless AI-vision fallback,
   which guessed a nonsense "AAPL EQUITY @ 2.26" — AAPL doesn't trade near
   $2 — instead of resolving the AAPL 330P Unraveller had loaded 3 min
   before). This is the same class as #1 and #2, found by the audit sweep.
All 3: extension/parser.js + signals.py mirrored, 6 new test_signals.py
cases (2 per bug: parse-level + end-to-end resolve-through-the-shelf), 2 new
samples.txt lines, parity-checked (same 5 pre-existing gaps, 0 new),
test_signals/test_positions/test_resolve all green (same 4 known Brett-trim
fails, 0 new). Extension 3.5.14 — **RELOAD IT**.

**1 bug found, NOT fixed — flagged for G's call:** Mike (Honeydrip
daytrades) replied to his own "Loading AMD 9/4 445 Puts" with "Filled
starters at 4.60" (9:41am) — background.js's reply-quote guard
(`if (msg.reply) { ... }`, added specifically to stop a past incident where
"Mike replying to his own morning entry" made the bot re-buy AMD at top
tick off the quoted old text) treats EVERY reply as pure quoted noise and
refuses it outright, never even trying needs_loaded resolution. That guard
is doing its job in general — but it can't currently tell "a reply that
quotes an unrelated OLD trade" (must suppress) from "a reply that IS the
fresh fill confirmation for the SAME loading call it's replying to" (should
resolve), because content.js flattens the quoted text and the new reply
text into one string with no boundary. Fixing this needs content.js to
capture reply-quoted text separately from the new body — a bigger,
higher-risk change than the 3 above (this exact guard exists BECAUSE a bad
fix here once caused a real wrong re-buy), so it's flagged rather than
rushed. Likely low financial cost today specifically (buying power was
$65-$113 most of the morning — probably would have been refused anyway,
same as the other AMD/GOOGL/TSLA misses), but worth fixing properly when
there's room to test it against the original incident.

**Every other room checked against today's baseline and explained, not
bugs:** Whop Futures / Whop High Risk / NGD ngd-trades / all futures rooms —
zero activity or not, doesn't matter, every futures broker is OFF (a
switch, not a parser problem). Options Insider — 0 today, known deathwatch
(last real post 8/12, cancel-by 9/11). Vero 2 — 0 today, posts ~weekly, last
9/1, within normal cadence. Boka 2 — 0 today, known low-frequency/equity-
swings room. Platinum-3 (day-trades) — 0 today, ~1 msg/10 days historically,
normal. Whop Swing Trades — 0 today, Felony hasn't posted there since 8/27
(known). RWGates' own HOOD entry (9:32am, 1.83) — correctly read via the
AI-vision fallback and correctly REFUSED for buying power ($113 vs $251),
not a bug.

## 9/3 17:42 — MISSED-ENTRY WATCHER, live + batch (G: "we need to be catching these")
Two additions, both READ-ONLY (log/notify only — never place, never touch
sig.action, sig.fire, or any order):

1. **Live, in the extension (background.js, right where a fully-unmatched
   message currently logs NOTHING at all — "logging pure chatter would bury
   the useful lines" was the old reasoning).** Now: if THIS trader has an
   unconsumed LOADING call on the shelf (guards.js's own
   remember_loading/resolve_loaded state — the exact mechanism all 3 of
   today's bugs slipped past) within the loading window (default 4h) AND
   this unmatched message carries a price-shaped number, it fires a Chrome
   desktop notification ("⚠ POSSIBLE MISSED ENTRY — TICKER STRIKE") plus a
   log line, same pattern as the existing 40-min silence alarm. Deliberately
   narrow — needs an ARMED shelf, not just any price+word — so it can't
   turn into log spam; pure chatter with no open loading call stays silent
   exactly as before. Nothing is ever bought off this — it's a tap on the
   shoulder to go look, same as G asked for.
2. **Batch, in replay_check.py (`find_missed_entries`), wired into the same
   run the daily close-out (step 4) already calls.** Separate from the
   existing silent-drop check (which only fires when the parser ALREADY
   assigned an action — structurally blind to a full parser miss, which is
   what all 3 of today's bugs were). This one replays the day chronologically
   per trader, arms/clears the same shelf concept in Python, and flags any
   action=null message that lands while a trader's shelf is still armed and
   carries a price. New output section: "POSSIBLE MISSED ENTRIES". Tested
   against today's real data — correctly reproduces the fixed RWGates
   pattern (now shows as a regular SILENT since the parser fix makes it
   actionable again) and flags one true heuristic false-positive (RWGates'
   HOOD entry, already handled fine via the AI-vision fallback, which this
   Python-only replay can't see) — expected: it's a diagnostic net for a
   human glance, not a claim every flag is a real miss.
Both compile-checked (py_compile + node --check), full test suite still the
same 4 known Brett-trim fails, 0 new. Extension 3.5.15 — **RELOAD IT**.

## 9/3 18:05 — HISTORICAL missed-entry catch-up (all days since bot went live)
G: "did you run it already or can you run it now for today and every past
day since the bot has been alive to catch up?"

First fixed a real bug in replay_check.py itself: `newest_export()` always
loaded the single most-recently-modified DS Logs file no matter what DAY
was requested — running it for a past date would silently load TODAY's
file, find no matching date string, and report a false "0 results" for
every historical day. Added `export_for_day(day)` (resolves the actual
`DS Logs/signal-room-chat <Mon>-<DD>-<YYYY>.txt` for the requested day,
filename first, content-scan fallback) and wired it into `main()`. Compile
clean. This is a diagnostic-tool fix only, not the trading path.

Ran `find_missed_entries` for every day we have a DS Logs export for —
Aug 18, 19, 20, 21, 23, 24, 25, 26, 27, 28, 31, Sep 1, 2, 3 (2026) — the
full range since the bot's chat capture started.

**Result — the RWGates "took entry / avg / fill" pattern (fixed today as
RE_TOOK_ENTRY_FILL) was ALSO silently missed on 4 earlier days, not just
today:**
- 8/19 09:35 — META 535P, "Fill is 1.79 not using a lot of size here"
- 8/20 09:38 — NFLX 80C, "I took entry $NFLX NFLX260821C80 1.28"
- 8/21 09:59 — HOOD 102C, "3.65 took entry"
- 8/26 09:35 — MSFT 495C, "1.56 fill took entry"
- 8/25 09:37 — flagged but symbol mismatch (shelf had MRNA loaded, message
  named META) — likely two different unconfirmed calls, not one clean miss;
  didn't count it as a clean instance.

Two more flags were heuristic noise, not real misses (confirmed by
reading the message body): 8/25 10:28 KingBeeAri TSLA — a "watching above
353.5" note, not a fill; 9/2 09:50 Midas SPY — "will be my add point once
I fill," a forward-looking plan, not a fill. Every other day: 0 flags.

These are historical — the bug is fixed going forward (extension 3.5.15),
and nothing can be done about entries the bot missed on 8/19–8/26; this is
reported for the record, not actioned. No trades were placed as part of
this check — read-only replay against saved logs only.

## 9/3 17:10 — FULL HISTORY ALERT AUDIT (G: "find alert fails since the beginning of time, why some rooms were silent")
New tool **audit_history.py** → **ALERT-AUDIT.html**: replays EVERY export (8/18–9/3) through the production parser and sorts each room into TRADED / MISSED (parser read an action, nothing happened) / BLIND (parser read nothing while a loading shelf was armed and a price was present) / NO CALLS / SILENT, then groups every miss BY SHAPE so a fix covers a class.
### The honest caveat, in the tool's own output
Until 9/2 the extension kept only the last **400 verdicts per day** (LOG_MAX). Every export 8/19–8/31 shows exactly 400 while capturing 748–8,367 messages — **the morning of every one of those days is gone**. So a historical "MISSED" can mean never-judged OR record-trimmed; they are indistinguishable now. Cap is 2500 since 9/3, so from here MISSED means missed. BLIND is trustworthy on every day (it is the parser's verdict on the text, not a logging artifact).
### Two REAL bugs the sweep found, both fixed this pass (extension 3.5.16)
1. **DANGEROUS false positive — watchlist rows read as live BUYS.** TradingTheTrend posts a levels row every morning: `QQQ 726c > 725.00 715p < 716.00 MU 1000c > 980.00`. The parser read `OPEN QQQ 726C @ 725.00` — paying the TRIGGER LEVEL as the premium, ~600x the real price. Only buying power stopped it from ever firing. Two guards now, ahead of every entry rule in both parsers: a `>`/`<` between a contract and a number is a trigger level, not a price; and 3+ distinct contracts in one message is a list, not an order. Seen on 9 separate days.
2. **RWGates missed AGAIN, a second shape.** 8/25: `Took entry $META META260826C570 Fill: 5.15` — price AFTER the word fill, with a colon and an OSI contract in between. The 9/3 fix only matched `<price> fill`. RE_TOOK_ENTRY_FILL now takes both orders.
### What the shapes say (why rooms looked quiet)
Labelled template 95 · unclassified 81 · futures phrasing 38 · date-first contract 13 · Server Tag junk 11 · bot footer 4 · ticker-first fill 3 · avg-price 3. Everything except "unclassified" is a grammar already fixed in the last two days — the volume is the measure of what those fixes recovered, not a live backlog.
### Still open (his call, not rushed)
- Mike/Honeydrip reply-to-own-message fills swallowed by the reply-quote guard (deliberate, from a past bad-rebuy).
- "Fill is 1.79 not using a lot of size here" (RWGates 8/19) and `Fully out @here 103%` — no ticker, needs the loading shelf; not yet wired for those two phrasings.
- 3 tests added (2 watchlist, 1 took-entry-fill:). Suite: same 4 pre-existing failures, parity unchanged, resolve green.

## 9/3 19:10 — FOLDER CLEANUP (G: "cleanup without breaking anything — can reorganizing improve the app?")
**Answer to the question: yes, but not by moving code.** The Python modules import each other flat (`import positions`) and the .bat files use plain names — putting code in subfolders breaks every import and every launcher, on a live money system, for zero gain. Nothing in the engine moved. What the cleanup DID surface were three real improvements.
### Moved (recoverable, nothing deleted)
`archive/logs` 187MB of rotated logs (bridge.log.1/.2 75MB, announcer.log.1 45MB, webull_api rotations 32MB, webull_api-announcer 20MB) · `archive/broker-exports` 10 Webull CSVs · `archive/journals` 9 old journals (last 3 kept in place) · `archive/one-off` pitches, voice transcripts, scoreboard backups, 0-byte test files. Live logs (`bridge.log`, `webull_api.log`, `trades.log`, `announcer.log`) untouched. `archive/` added to .gitignore; git saw **0 tracked deletions** — everything moved was already ignored. **G can delete `archive/` any time to reclaim the 187MB.**
### Improvement 1 — the log sweeper only knew one log family
`_connect_extras` swept `webull_trade_sdk.log.*` older than 2 days and nothing else, which is how 187MB accumulated unwatched. Now it sweeps every rotated family (bridge / announcer / webull_api / streaming SDK) and, new, rolls any LIVE log past 40MB to `.old` once rather than letting it grow forever. `*.log.old` gitignored.
### Improvement 2 — the audit tools were matching across DAYS (real correctness bug)
`replay_check.py` and `audit_history.py` read `bridge.log`, whose lines carry **HH:MM:SS and no date** — so an 8/19 call could be "confirmed" by a 9/3 log line at the same clock time. `trades.log` is the same stream written by `note()` with a full ISO timestamp, going back to 8/01. Both tools now read trades.log, day-scoped. Every historical answer is honest for the first time.
**That fix immediately paid for itself**: it surfaced a brand-new miss the same minute — RWGates 9/3 09:35, `@here $HOOD i took enry .HOOD260904C120 1.83 fill price`. He typo'd "entry" as "enry". Deliberately NOT fuzzy-matched: a widened regex was tried, started eating the OSI code's own digits (META...C570 became a limit of 570) and broke a test, so it was reverted. **A mistyped verb gets surfaced by the POSSIBLE MISSED ENTRY net for a human, never guessed into a real-money order.** The regex does now accept `Fill: <price>` and the common transpositions after a correctly-spelled "took".
### Improvement 3 — dead menu entries in EXTRAS.bat
`tune.py` and `drill.py` were deleted long ago; the menu still called them and threw a raw Python error. Both entries now check first and point at the tools that replaced them (replay_check / audit_history / scoreboard).
### New: INDEX.md
Every file in the folder, what it's for, what must never move, and the one line that matters: **archive/ is safe to delete.**
### Verified after all of it
All 16 modules import · every file referenced by every .bat is present · test_positions 0 failures · test_signals 4 pre-existing · test_parity 5 pre-existing · test_resolve green · bridge restarted 19:06 and re-confirmed the open XLF position with its stop still resting at 1.18.

## 9/3 19:40 — HUNT #2: the ratchet could FAIL SILENTLY and the log lied about it
Method: audited all 113 filled trades on record for the one shape that should be impossible — **went green past +10% but still closed red.** Two hits; one is a real bug that cost real money.
### TSLA 350P, 8/26 — peaked +16%, closed −$45
Filled 5.15, bracket stop born at 4.60. The ratchet then tried **three times** to move the stop to breakeven (5.15) — at +13%, +16%, +14% — and Webull refused all three with `DAY_BUYING_POWER_INSUFFICIENT`. The trade died at the original 4.60.
**The bug isn't the refusal — it's what happened after.** That failure branch logs *"the old stop is still in place; the watchdog on this PC covers the gap."* **It did not.** The watchdog reads `p["stop"]`, and `p["stop"]` was only ever written on SUCCESS. After a refusal the local guard was still watching the OLD, lower level, so a winner that the ratchet had already decided to protect at breakeven was left guarded at −11%. Every "ratchet couldn't move the resting stop" line in the whole history (21 of them) had this hole behind it.
### Fixed
`auto_ratchet`'s failure path now records the level it WANTED as `soft_stop`; the watchdog guards `max(stop, soft_stop)`; a successfully placed resting stop clears it. So a refused ratchet move still protects the trade locally instead of only claiming to.
New test reproduces it exactly: FakeWB gains `refuse_stop_moves`, accepts the bracket stop, then refuses every move — asserts the soft stop is recorded at 2.20 and sits above the stale resting stop. Suite green (test_positions 0 failures, others at their pre-existing counts).
### The other hit, not a bug
NFLX 8/20 peaked +10.0% — exactly the arm threshold, so the ratchet had nothing to lock yet. Left alone.

## 9/3 20:00 — "why not a conditional order at the round number?" (G)
**Because Webull's API doesn't offer one for options.** Checked against v3.5.0/OPTIONS-BROKER-REFERENCE.md, sourced to developer.webull.com:
- Options accept only `LIMIT`, `STOP_LOSS`, `STOP_LOSS_LIMIT`. No MARKET, no trailing.
- `OTO`, `OCO`, `OTOCO` are **stock-only** — option orders do not support them even on a SINGLE strategy.
- Nothing in the API triggers an order off a DIFFERENT instrument. There is no "buy SPY 645C when SPY *stock* touches 761."
- The nearest thing, a BUY `STOP_LOSS_LIMIT` on the option, triggers on the OPTION's own price and only on the way UP — backwards for a pullback, where we want to buy after the stock dips and the call gets cheaper. It would suit a breakout entry, not this.
So the polling hunt isn't a shortcut around a broker feature; it IS the trigger, and the only thing that matters is how fast it sees the touch.
**Improvement shipped instead:** the hunt's entry poll was a flat 1.0s from when every price was an HTTP call. Since 9/2 the underlying comes from the MQTT push, so a poll is a dict lookup costing zero rate budget. The hunt now watches at **0.25s while the stream has that symbol fresh** and falls straight back to 1.0s if the stream drops (`Pullback(streamed_fn=..., entry_poll_streamed=0.25)`, `_pullback_streamed` in bridge.py, both tunable in settings under `pullback`). **4x less lag between the touch and the bid going in, for free.**
