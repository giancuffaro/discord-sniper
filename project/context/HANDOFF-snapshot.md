# DISCORD SNIPER — THE HANDOFF
Read this first. It is the living memory: what the machine is, every rule in
force, how G works. It holds ONLY what is true right now. The full history —
every session's notes, every bug's story — lives in HANDOFF-LOG.md.
Last updated: 2026-09-09 (later still) — cut from 240 KB / 3,034 lines to this;
rules folded in from tonight: ONE central file per data family (ledger /
alerts / tapes / holidays / announcer board), ratchet 7.5/5/2 flat, futures
ratchet decoupled, Whop API path deleted, OWLS all-alerts wired, shabs/eli
retired, all rooms live. Rooms cut 27→12 on tagged master_ledger.csv numbers,
then 12→8 dropping all 4 remaining ZTRADEZ rooms (sub lapses in 1 day), then
G re-added 11 (all 4 Whop, Aristotle small, TTT Lotto, all 3 Platinum shadow,
Brando, Shoof) to land at 19 — his target was 15-20 tabs total. rooms.txt's
old per-room essays moved to HANDOFF-LOG.md.

## How to update this file (READ BEFORE EDITING — the old way broke things)
- This file is a STATE, not a story. Edit the rule that changed, in place.
  If a rule is superseded, REPLACE it — never leave the old one with a
  "SUPERSEDED" note stacked on top.
- Bump the one "Last updated:" line above. One line. Never prepend an essay.
- Session notes, findings, post-mortems, numbers-of-the-day go to
  HANDOFF-LOG.md under "SESSION NOTES", newest first, dated. That file may
  grow forever; this one may not. Hard ceiling: 50 KB. If you are about to
  push it past that, you are writing history, not state — move it.
- The bridge's own daily handoffs/HANDOFF-<date>.md is a thin status photo.
- Then sync the Project: copy this file over project/context/HANDOFF-snapshot.md
  (fixed name — a re-upload replaces) and END THE REPLY with
  "📌 Update the Project: re-upload project/context/HANDOFF-snapshot.md".
  The live file here ALWAYS wins over the Project copy.

## Who and what
- G (giancuffaro230@gmail.com) — non-coder, trades options + futures live,
  real money. Wants it CONDENSED. "Fix everything is default always" — bugs
  get fixed without asking, same day. "Fix errors every day after journaling."
- REAL-MONEY ACTIONS ARE HIS ALONE: placing/canceling orders, flipping rooms
  live, restarting the bridge/announcer, unlocking accounts, funding,
  questionnaires, ToS, passwords, keys. Never do them; ask with a short
  multiple-choice, recommended option first.
- The machine: Chrome MV3 extension (Profile 2; v3.5.67) reads 19 rooms —
  15 Discord + 4 Whop (Whop tabs are in the separate "Sniper Whop" profile,
  Browser 2 — not part of the Profile 2 / Discord-logoff tab count), 0
  ZTRADEZ (whole server cut 9/9, sub lapsing) (extension/rooms.txt is THE
  list; editing it changes the build stamp → extension reloads itself) —
  typed alerts, voice
  (Deepgram, diarized), images (vision) → Python bridge (bridge.py,
  127.0.0.1:8787) places real Webull option orders. Futures: micros via
  NinjaTrader OIF files (Webull futures account $0 by choice; Topstep not
  executing; Tradovate removed 9/x). Whop reads happen in the "Sniper Whop"
  Chrome profile (Browser 2); the Whop API path is DELETED (walled + it was
  dropping tab reads).
- Accounts (Webull, one app key): MARGIN ENIQGUV4 (~$706), CASH MOI680
  ($0.55), FUTURES R8IEC ($0.55). Rate budget is SHARED with Market Sniper.
- SEPARATE tool: Market Sniper (his own build, 127.0.0.1:8000) trades HIS
  manual scalps on the SAME Webull account. Coexistence rule: positions the
  bot didn't originate are HIS — visible, never stop-managed, never sold,
  never blocking a room call in the same symbol (Book.is_hand_trade, every
  exit door). Market Sniper is on the OLD ratchet (10/10) — port the 9/9
  handoff: C:\Users\Hulk\Desktop\Market Sniper\HANDOFF-RATCHET-2026-09-09.md.
- The Claude Project (claude.ai): project/PROJECT-INSTRUCTIONS.md is its
  Instructions; project/context/ holds its uploads (HANDOFF-snapshot.md,
  rooms-snapshot.txt, OPTIONS-BROKER-REFERENCE.md ...).

## Rules of the house (current, in force)
ENTRIES
- Bid the caller's price or better; pullback entries cross the ask at the
  touch. RN (round-number) pullback is global and ON (waits for the next
  round number, 10-min window; a never-touched RN = skipped, logged
  "PULLBACK never hit"). One contract per entry while the bracket is on.
- All rooms LIVE by default (ALL_LIVE_GEN migration 9/8 cleared every test
  flag). Toggling a room off is G's only bench.
- STRIKES: never more than 1 strike OTM; deeper snaps to the first OTM rung
  (quote-verified). 3-ITM translation for SPY/QQQ/Mag7 0DTE. ADD buys the
  held strike.
- "ADDED <full contract>" you are not in = an OPEN entry. A bare "added to
  SPY" refuses.
- SPX→SPY per channel (settings spx_entry_channels): index entries fire as
  the ETF, strike/10, caller's premium dropped. OWLS relay: shabs/eli calls
  get default_symbol SPX + spx_entries (9/9).
- SPREAD GUARD (entries only): refuse if spread > 20% of mid or > max($0.20,
  10% of mid). THIN guard: < 250 contracts last session = refused.
- STALE-ENTRY GATE: entries older than 3 min never fire. Negations ("NOT
  getting in", "too expensive") hard-veto; "out the gate" is hype.
- DEDUPE LADDER: extension in-flight lock → bridge echo-lock (same contract
  OPEN within 20 s refused) → per-trader "already in" claim → one
  average-down ADD if the same trader re-posts ≥1% under what was PAID.
- RETRACTION ("not ready / scratch that / cancel / disregard / hold off /
  nevermind") pulls that trader's resting bids and armed pullback hunts.
- FUTURES: micros only (NQ→MNQ, ES→MES ...). Entry snaps to the 25-pt grid
  in his favour. Their stop/target wins; 25/50 fills the gaps.
- THE POCKET (hidden from the UI on purpose): a :43-:51 scalp-entry clock
  gate exists behind settings flag pocket_scalps_only, default OFF. The
  decision comes from HIS fill data (ledger minute-of-hour), not the QQQ study.
- Positions record the underlying at fill (und_at_fill); FILLED log lines,
  announcer posts and the journal all carry it.

EXITS — THE DOCTRINE: THEIR TRIGGER → OUR ENTRY → THE RATCHET'S EXIT
- ENTRIES ONLY (G, 9/3; verified live 9/8): the bot follows room ENTRIES
  (and adds) only. EVERY room-side exit — trim, stop-move, "all out",
  "stopped out", "closed everything" — is logged "EXIT-IGNORED … entries
  only" and NEVER traded. The ratchet's resting stop at Webull is the ONLY
  exit (plus the bridge's own pullback stock-stop / underlying hard-stop).
  A bot SELL that traces to a room call is a BUG: check bridge.py do_POST's
  EXIT-IGNORED gate, background.js's TRIM/STOPMOVE/CLOSE gate, and that
  settings execution.exit_policy is absent (default entries_only; "full" is
  the one-line way back).
- THE RATCHET (settled 9/9, flat, no cheap tier): born stop −7.5%
  (strategy.stop_loss_pct) placed WITH the order as a combo bracket, rebased
  to the FILL if filled better, never at/above the fill, never inside the
  bid/ask. Arm at +5% → stop to BREAKEVEN; then every further +2% locks
  another +2% (ratchet_tiers.py TIERS = (None,(5.0,0.0,2.0))). A rung must
  clear 4 ticks (MIN_RUNG_TICKS). Ratchet tries REPLACE, falls back to
  cancel+place and says so. Anti-clip (locked ≤60% of gain) only at 2+ DTE.
  WHY 7.5/5/2: 294-combo sweep on 80 real fills (ratchet_sweep_fine.py) —
  the small rung is the lever ($152 → $281 on the sample); cheap (<$1)
  loses under every spacing, so no cheap tier. Lean, not verdict.
- FUTURES RATCHET (9/9): derived from the trade's own risk — arm at
  ⅔ of the stop distance in profit → BE, then a rung every ~27% of it
  (FUT_ARM_FRACTION = 5/7.5, FUT_STEP_FRACTION = 2/7.5). 30-pt NQ stop →
  30/20/8. Anchor: QQQ↔NQ ≈ 41 pts per $1.
- SWINGS: 14+ DTE = swing (auto-tagged). Their stock-level stop runs it; no
  level = wide −25%. Option SELL orders are DAY-only at Webull, so
  Book.rearm_overnight_stops re-arms every open swing at 9:31. Scalps
  excluded on purpose.
- CLOSE path (9/9 phantom-exit fix): every bot sell waits for FILLED
  (_sell_confirmed) — an ACCEPTED sell is never booked as filled; a
  never-filled sell releases the key and logs EXIT-RETRY.
- A CLOSE for a contract the book does not hold is REFUSED, never sent
  (his 12-lot scalps live in the same account).
- 0DTE: ETF options trade to 16:15; auto-exercise at $0.01 ITM — flatten
  before the close.

RESTARTS / SAFETY
- State photo on every event. On boot: expired options = dead paper;
  everything else UNVERIFIED until the broker confirms (then watchdog +
  stop arm); gone = closed "at a price I never saw". Mid-market code
  updates self-apply at the first safe window (no bids/hunts in flight);
  checkBuild defers an extension reload while market is open with
  positions in flight. Resting stops at Webull guard every gap.
- POSTCHECK after every trade: book vs account, stop resting, quote bus
  fresh — logged as "POSTCHECK … PROBLEM" when they disagree.
- GIT: settings.json holds every key, gitignored, never committed, never
  pasted back. Never run git write commands from a sandbox (locks). AUTO
  PUSH sweeps commits every 45 s. After ANY suspicious file loss check
  `git reflog` for a "reset:" line before rebuilding by hand.
- Compile-check everything touched (python3 -m py_compile / node --check).
  Extension changes → bump extension/manifest.json so a reload is provable.
  Never install the streaming SDK family (webullsdkcore) into the bridge's
  Python. Sandbox trading is RETIRED — paper is LOCAL (SIM tickets).
- Discord API is NOT an option (user-token automation = permanent ban risk
  to the account + paid subs; official bots need the server owner).
  Reaffirmed 9/9. Browser reads only.

ROOMS / TABS / READERS
- rooms.txt = THE channel list (tabs + trading, one file). Closing a tab
  STICKS — openMissingRooms was removed from the watch-build alarm (9/9).
  START HERE = fresh start: closes Chrome, reopens every room (~2.5 min
  paced flood; count tabs after, not during), launches the announcer.
- Relay rooms (one bot account relaying many traders): ZT all-trades-mashup
  (1334236429655740457, ZTRADEZ BOT) COVERED ALL 19 ZT direct rooms, but the
  whole ZTRADEZ server was cut 9/9 (subscription lapsing in 1 day) — no
  active ZT room remains. OWLS all-alerts (1449226651064991806, "OWLS
  Capital Clanker", 9/9 — slug map shabs-sky-alerts→shabs, eli-alerts→eli,
  muggzone-options→MuggZone, giul-heatseeker→Giul, florida-man,
  common-stock, jon-and-kian, ab→AbTrades, tt, eva, neal) is still active.
  RELAY UNWRAP in background.js re-books under the real trader (footer
  "#slug" / possessive), so per-trader claims, dedupe and scoreboard hold.
  shabs + eli direct rooms retired 9/9 (covered by OWLS all-alerts).
- EMBED RACE: bots post the call in an embed that hydrates after the row
  paints; content.js keys SEEN on id+length so the hydrated read re-emits.
- TAB RELOADS (root cause FOUND 9/9, v3.5.68 — G: "it's something in
  code, I know it"): the DS Logs export showed 662 "watcher is detached —
  reloading that room" reloads in ~29 h at a median gap of EXACTLY 60 s
  (the handler's own throttle). Cause: a re-injected content.js stopped the
  old copy's observer but NOT its heartbeat interval, so the dead copy kept
  reporting "observing:false" every 30 s and the background reloaded the
  tab; ensureReaders() re-injected every tab every 5 min, so every room
  grew a zombie and reloaded ~once a minute all evening. THAT reload storm
  — hundreds of page loads an hour — is what made Discord log the profile
  out (the 603 "tab now shows a different page" drops), not the tab count.
  FIXED: content.js/whop.js clear their beat/pulse on __SNIPER_STOP__ and
  carry a `stopped` flag; background re-INJECTS on a detached report and
  reloads only on a repeat within 5 min; ensureReaders injects only into a
  tab that is not heartbeating; memory shed and both Whop reloads now LOG
  a line (they were silent); Whop's no-message backstop 5 → 30 min.
  RULE: a page reload is the LAST resort — re-attach first, and every
  reload path must write a log line, so a storm can never be invisible.
  MEMORY: memory shed reloads ≤1 room tab per tick, 4 h cadence (never
  active/voice tab, never 9:28-9:40); tabs pinned autoDiscardable=false;
  a room silent 90 s is reloaded with 1/2/4/8/15-min back-off.
  --process-per-site is OFF (one renderer per tab). Chrome hardware
  acceleration OFF.
  ROOM CUTS: any cut is G's call on TAGGED ledger numbers only — the 9/9
  "7 dead rooms" list was WITHDRAWN (it was built on a broken count;
  Aristotle had a live AMD 515C that day). 154 fills still carry room "?".
- WHOP: rooms live at whop.com/<business>/exp_<id>/app/ (the old /joined/
  URLs redirect to a lobby and read nothing). Tabs are the ONLY Whop source
  (API reader deleted 9/9 — its dead "api mode" gate had been dropping every
  tab read since the morning). Felony posts QQQ/SPY contracts when he trades
  NQ/ES. Felony goes live on ZOOM mornings — join the WEB client
  (app.zoom.us/wc/…) in a Chrome tab so tabCapture hears it; the desktop app
  is invisible. Scheduled task opens + captures 9:15-9:20 weekdays.
- VOICE: ears transcribe always (Deepgram, diarized S0/S1). Voice ENTRIES
  ON (9/2); voice EXITS irrelevant under entries-only. Two-stage: "loading
  X" = staged (4-min shelf, per speaker); fires on that speaker's "I'm in /
  filled / average is X". AUTO-JOIN clicks a LIVE badge's voice/stage
  channel (one join per 10 min). Glossary in ai_reader (pulls=puts,
  Qs=QQQ, one-d-t=1DTE …). Typed copy of a voice fire = echo, skipped 5 min.
- Silence alarm: any room quiet 40 min in market hours → desktop
  notification. Watchdog reloads stale/black-shell tabs.

FILL ANNOUNCER (announcer.py, read-only)
- Posts every fill, +10/+20/… milestones, ⛔ stop-outs to G's Discord:
  options → announcer.webhook_url, futures → futures_webhook_url,
  scoreboard → scoreboard_webhook_url (falls back to options). NEITHER
  channel ever goes into rooms.txt. Single-instance (.announcer.alive);
  off switch = announcer.stop containing "stop" (STOP ANNOUNCER.bat);
  "Fill Announcer revive" schtask every 30 min; announcer.restart = reload.
- STATUS: PAUSED since 9/2 (announcer.stop = "stop", G: "get this app
  working 100% first"). Its board is now computed FROM THE LEDGER (9/9) —
  the old running tally missed every close it wasn't awake for.
- Its order hunt is paced (0.20 s, once per account) — the 9/2 429 storm
  (77k TOO_MANY_REQUESTS on the shared key) must never come back.

## DATA — one central file per family (9/9). THE APP READS ONLY THESE.
- FILLS → master_ledger.csv (built by build_ledger.py, read via ledger.py).
  Sources in trust order: Webull_Orders_<date>_auto.csv exports (the
  account's own history, FIFO-paired per OCC) > trades.log FILLED > days/
  wallet.trades > days/table. RULES: the export's exit/P&L/state/account WIN
  over the book's belief (store_pl keeps the book's number); a fill the
  broker saw is `filled` even if the book said `failed`; export-confirmed ⇒
  live; entry time = opened, else the broker's FILLED stamp, NEVER wallet
  `t` (that's the exit); one FILLED line confirms one row; table/wallet
  twins dedupe on date+caller+contract+fill (no time bucket). Gaps are
  rows, not silence (source=trades.log-only / webull-export-only).
  RECONCILIATION prints every run: on any day with an export, ledger(live,
  real) must equal the export to the cent (9/4 +152.00 ✓, 9/8 +77.00 ✓ —
  the book had 9/8 at −$82). A DRIFT line = something upstream lied.
  NOTHING reads days/*.json "table" or journal.csv for analysis anymore
  (table truncates — 9/8 it kept 6 of 12 fills; journal.csv inherits it).
  journal.csv is a legacy export the bridge still writes.
- ALERTS → master_alerts.csv (build_alerts.py; ledger.alerts()): every
  alert and its fate — taken side from telemetry.csv (posted/seen/sent/
  filled, slip, greeks), declined side from trades.log via misses.py
  (BUYING POWER / THIN / PULLBACK never hit / SWINGS paused / TEST room /
  FUTURES prop …), filled ones linked to their ledger row. Thin spot:
  telemetry rows carry no room/caller (bridge doesn't populate them).
- PRICE TAPES → tape.py is the ONE registry (webull option_tape, tasty
  greeks/quote, databento raw + CLEAN, missed_tape, bars/). tape.path(
  "databento") = the despiked clean file when it exists — every backtest
  replays the same prices. Webull has NO historical option prices; the
  tapes are our own record. Databento key (settings execution.databento)
  works from the sandbox; databento_backfill.py spends credit — never run
  its main() casually.
- HOLIDAYS / HOURS → market_hours.py owns the table (through 2027 —
  UPDATE EVERY YEAR, bump HOLIDAYS_THROUGH); webull_options.HOLIDAYS
  derives from it. MARKET-HOURS.md is the human copy. Options 9:30-16:00
  (SPY/QQQ/IWM + index to 16:15); futures Sun 18:00 → Fri 17:00 with the
  17:00-18:00 daily halt.
- RN LEDGER → rn_ledger.csv (pullback.log_ledger, append-only): every
  armed/filled/missed/cancelled round-number hunt — the forward tracker
  for "is my RN rule beating their entry" (so far: RN fill vs caller
  price on the same contracts ≈ +$123 edge on 11 → 34 trades; misses
  cost ≈ −$38 on the 2 priced).
- Both central files rebuild inside bridge.py save_day() (never-raise
  guards, ~110 ms, atomic swap) and on demand: python3 build_ledger.py /
  build_alerts.py (keeps 5 .baks, prints summary + reconciliation).
- ANALYSIS TOOLS (all read-only, all on the ledger): caller_report.py,
  scoreboard.py (→ SCOREBOARD.html), journal_full.py (taken+missed xlsx),
  misses.py, errors.py, entry_compare.py, missed_dollarize.py,
  ratchet_sweep*.py, ratchet_backtest.py, chart_contracts.py, telemetry.py.

## Broker facts (Webull OpenAPI — v3.5.0/OPTIONS-BROKER-REFERENCE.md first)
- Limits PER ENDPOINT per app key: option snapshot 60/min (20 symbols/
  call); Order Detail / Positions / Balance 2 per 2 s. 429 = throttle;
  417 = business rejection (DAY_BUYING_POWER_INSUFFICIENT,
  NOT_SUPPORT_REVERSE_OPTION, STOP_PRICE_MUST_BE_LESS_THAN_MARKET).
- No option streaming; fills ARE pushed (gRPC TradeEventsClient). No
  MARKET orders on options. Combos = MASTER(LIMIT) + STOP_LOSS on SINGLE
  only. Replace needs original client_order_id + legs[].id.
- Ticks: SPY/QQQ/IWM $0.01 always; Penny Program $0.01 <$3 / $0.05 ≥$3;
  else $0.05/$0.10 (tick_round/stop_below are symbol-aware).
- Quote bus sweeps at 1.05 s, 20 symbols per call, fill poll 1.0 s;
  positions' watchdog reads the bus, direct quote at most every 2 s.

## Operational truths
- sniper-autopilot scheduled task: */30 ET — preflight ~9:30, sync watch
  in market hours, close-out ~16:30. daily-journal-and-fix: weekdays 16:45
  builds the journal from broker truth, copies HANDOFF-snapshot, and fixes
  what it exposes. Neither places/cancels orders or touches settings.json.
- Multi-account: extras mirror LIVE entries 1:1 with own books/stops.
- START HERE.bat saves+pushes before its reset; RESTART BRIDGE.bat
  pre-flights and warns. Logs: trades.log (the story), bridge.log (raw,
  20 MB, no rotation yet), webull_api.log, announcer.log, deadman.log.

## Pending — G's side (real-money / restart actions only he takes)
1. RESTART THE BRIDGE to apply tonight: ratchet 7.5/5/2, futures ratchet,
   RN ledger hook, Whop fix, OWLS all-alerts, shabs/eli retirement, ledger +
   alerts hooks, phantom-exit CLOSE fix. (The bridge auto-booted 02:55 and
   already ran the ledger hook once — but the running code must be his.)
2. Restart the announcer when he wants it back (it posts the ledger board).
3. Market Sniper: apply HANDOFF-RATCHET-2026-09-09.md (options 5→2 rung,
   futures decouple).
4. NinjaTrader ATM template "SNIPER": stop 100 ticks / target 200 (=25/50
   MNQ pts), qty 1 — create in NT8, type SNIPER in the popup.
5. Chrome: hardware acceleration OFF. Close any old parked Whop tabs.

## Watch items (open)
- Discord logoff under tab load — 9/9: 27 rooms cut to 8 (ledger-dead rooms,
  then the whole ZTRADEZ server on its sub lapsing), then G re-added 11 to
  land at 19 (15 Discord + 4 Whop; Whop is a separate Chrome profile so it
  doesn't count toward the Discord logoff risk — effectively 15 Discord
  tabs vs. 23 before). Watch whether logoffs actually stop at this count;
  if not, the next lever is moving rooms across more Chrome profiles, not
  further cuts.
- 154 ledger fills with room "?" (pre-tagging August + recovered rows).
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

## Subscriptions (audited 8/28)
Whop (~17.5% tax on top): Insiders Pro $199 | STS/RWGates $189 | Felony $100
| Boka $99.99 | Platinum $99 | "VIP discord access" $65 (unidentified) |
ZTRADEZ $65 (LAPSING ~9/10 — G's call to let it go; all 4 remaining ZT rooms
cut 9/9 ahead of it) | Vero $49. Stripe: Honeydrip/Aristotle $125. Free: Rafita.
≈ $1,140/mo rooms + ~$52 infra (ProjectX $29, NT data $12, Deepgram ~$5,
Webull data ~$5.50) + ~$30 exchange fees ≈ $1,220/mo before AI usage.
Break-even ≈ $60+/trading day. Next audit: cost vs ledger P&L per room.

## Where everything lives
HANDOFF-LOG.md (all history) · INDEX.md (folder map) · ARCHITECTURE.md ·
MARKET-HOURS.md · v3.5.0/ (broker reference, anti-clip study, ratchet
notes) · extension/rooms.txt · settings.json (keys, gitignored) ·
master_ledger.csv / master_alerts.csv (truth) · days/ (per-day state) ·
handoffs/ (bridge's daily photos) · project/ (Claude Project files).
