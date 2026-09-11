# DISCORD SNIPER — THE HANDOFF
Read this first. It is the living memory: what the machine is, every rule in
force, how G works. It holds ONLY what is true right now. The full history —
every session's notes, every bug's story — lives in HANDOFF-LOG.md.
Last updated: 2026-09-11 (06:40) — ext 3.8.2. SECURITY: 18 rotated webull_api.log.* files carrying the live x-app-key were TRACKED and pushed to the PUBLIC repo (*.log never matched their dated names); moved to archive/, .gitignore patched — THE KEY IS STILL IN GIT HISTORY AND MUST BE ROTATED AT WEBULL (G's action, Pending). New rules: CONDENSE AND MERGE; DATA-MAP.md read with INDEX.md every session. Alert recovery: build_alerts.py now mines ORDER IN (184) + AI READ (2,222) + per-contract REFUSED + pullback arms (direction match mandatory); 60 noise rows purged and gated; real alert count 331 -> 505, room coverage 156 -> 312, caller 89 -> 259. Expiry reader was silently buying the WRONG expiry when it could not parse a date — 13 real trades hit, now fixed + test_expiry.py. ai_reader.py had NO optionable.txt allowlist (ticker 'WITH') and was matching raw text through a Discord colour escape (MXLU/MMETA/MSPCX). test_positions.py was appending 3,896 fixture rows to production telemetry.csv — now telemetry-test.csv. alert_tape.csv/alert_meta.csv are LIVE but still EMPTY (recorder armed 9/11, collects at the open). WHOP ROOMS — REAL ROOT CAUSE 9/11, and my first two answers were WRONG (both corrected here, not stacked): THE WHOP PROFILE HAS NO EXTENSION. Discord Sniper is installed in folders `Default` and `Profile 2` ONLY — verified in each profile's Secure Preferences, which names the unpacked path C:\Users\Hulk\Desktop\discord-sniper\extension. The launcher opened 4 Whop tabs in a window with no reader in it, so they read nothing. That is the month Day Trades caught 1 alert, and why ZERO "(whop)" export files have ever been written against 2 "(discord)". A script cannot install an extension — START HERE now checks and prints a loud banner instead of pretending it worked. G's one-time step: open that Chrome window, chrome://extensions, Developer mode, Load unpacked -> extension folder, and log into whop.com in it. SECOND FACT, also wrong before: Chrome's profile FOLDERS here are Default='Your Chrome', 'Profile 2'='Discord Profile', 'Profile 6'='Whop Profile', 'Sniper Whop'='Person 1'. The launcher's default --profile-directory="Sniper Whop" is a REAL folder but it is the junk 'Person 1' profile, not the Whop one. whop-profile.txt now pins `Profile 6`. :resolve_profile also fixed: an exact FOLDER name now wins over the display-name lookup (it used to find nothing for "Sniper Whop" and pass it through). My earlier claim that Chrome was silently falling back to Default was wrong — it was opening a real but empty profile. ext 3.8.4; all 20 tests + parser_gate PASS.

## How to update this file (READ BEFORE EDITING — the old way broke things)
- This file is a STATE, not a story. Edit the rule that changed, in place.
  REPLACE, DON'T STACK: the new rule takes the old one's place — never
  leave the old one beside it with a "SUPERSEDED" note. (Same rule as for
  code, under RESTARTS / SAFETY.)
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
- The machine: Chrome MV3 extension (Profile 2; v3.5.95) reads 22 rooms —
  18 Discord + 4 Whop (Whop tabs are in the separate "Sniper Whop" profile.
  NEVER ASK WHICH BROWSER IS WHICH AGAIN — Claude-in-Chrome's "Browser 1 /
  Browser 2" labels are POSITIONAL and renumber as browsers connect and drop
  (the same physical Chrome was "Browser 2" at 17:30 on 9/9 and "Browser 1"
  at 18:05). The deviceId is stable; use it, and select_browser by ID:
      9adbdf77-9822-45d1-81ad-ab0195271160  = DISCORD profile (Profile 2)
      17c68ff9-4600-468e-afcb-076e2e6edfa5  = the OTHER profile (presumed
        "Sniper Whop"; unconfirmed — it disconnected 9/9 evening before it
        could be checked, so verify once it is back and correct this line)
  Confirm a lane the cheap way rather than by asking: open a whop.com room
  URL in it — the Discord profile's evictOtherLane() kills any whop.com
  /exp_ tab within one 30 s watch-build sweep, the Whop profile keeps it.
  Not part of the Profile 2 tab count). ZTRADEZ: the whole server was cut
  9/9 (sub lapsing — incl. Demon Alerts and MR.TOPHAT, same guild) but the
  ZT all-trades-mashup line is STILL `on` in rooms.txt, counted 9/10 02:22.
  Either the cut missed it or it was left deliberately; flipping a room is
  G's click, so it stays on until he says. The sub was "1 day" from 9/9, so
  it is dead or dying either way. G
  brought every non-ZT room back 9/9 once the reload storm was fixed (the
  "silent" verdicts were measured during the storm, so they re-measure on
  clean ledger data from here). extension/rooms.txt is THE list of EVERY
  room we have been to (57: 19 on, 33 off, 5 lapsed), one line each with a
  5th field on|off|lapsed — see ROOMS below. rooms.txt is data, not code:
  editing it does NOT reload the extension (build stamp skips it); the
  extension re-reads it within 30 s —
  typed alerts, voice
  (Deepgram, diarized), images (vision) → Python bridge (bridge.py,
  127.0.0.1:8787) places real Webull option orders. Futures: micros via
  NinjaTrader OIF files (Webull futures account $0 by choice; Topstep not
  executing; Tradovate removed 9/x). Whop reads happen in the "Sniper Whop"
  Chrome profile; the Whop API path is DELETED (walled + it was dropping tab
  reads).
- Accounts (Webull, one app key), read live 9/10 16:45 (close-out): MARGIN
  ENIQGUV4 $0.83, flat (day P&L −$671 net of fees: the BOT was +$46 on 7
  one-lot trades, G's 21 hand round-trips −$706 — HANDOFF-LOG 9/10), CASH MOI680 ($0.55), FUTURES R8IEC
  $211.95 funded but flat and `futures_brokers.webull` is still false so
  the bot will not touch it. At $0.83 of option buying power the bot
  CANNOT ENTER ANYTHING — the median bot entry costs $167; AAPL/MU/AMD
  calls were refused for money on 9/10 afternoon. G said 9/10 he is
  depositing and leaving the account to the bot alone.
  Rate budget is SHARED with Market Sniper.
- SEPARATE tool: Market Sniper (his own build, 127.0.0.1:8000) trades HIS
  manual scalps on the SAME Webull account. Coexistence rule: positions the
  bot didn't originate are HIS — visible, never stop-managed, never sold,
  never blocking a room call in the same symbol (Book.is_hand_trade, every
  exit door). Market Sniper's ratchet_tiers.py is (5.0, 0.0, 2.0), i.e. the
  spacing this bot ran until 9/10 — so the two tools now manage stops
  DIFFERENTLY on the SAME account. Port 5/3/5 across, or switch it off:
  G's call, still open 9/10.
- The Claude Project (claude.ai): project/PROJECT-INSTRUCTIONS.md is its
  Instructions; project/context/ holds its uploads (HANDOFF-snapshot.md,
  rooms-snapshot.txt, OPTIONS-BROKER-REFERENCE.md ...).

## Rules of the house (current, in force)
ENTRIES
- Bid the caller's price or better; pullback entries cross the ask at the
  touch. RN (round-number) pullback is global and ON (waits for the next
  round number, 10-min window; a never-touched RN = skipped, logged
  "PULLBACK never hit"). One contract per entry while the bracket is on.
  THE LEVEL STAYS $1 — SETTLED 9/9 on 106 beta-name alerts (META/AMD/AAPL/
  NVDA/TSLA/MSFT/AMZN/GOOGL, 8/4–9/8) replayed on real 1-second stock bars
  (pullback_levels.py → reference/PULLBACK-LEVELS.md): the $1 wait beats
  taking the alert by +$8/contract (paired, 65 trades, 2.6× its noise);
  $2 / $2.50 / $5 / $10 add nothing over $1 on the same trades (+0.4, +1.7,
  +6.1 — all inside noise) while skipping 40–75% of the trades; a 15-min
  wait changes nothing vs 10. And the "they bounce off 2.50s and 5s" idea
  is false in this sample: $5 lines held 31%, $2.50 36%, a random x.25 line
  38%. Don't re-open on a feeling — re-run the script when the sample doubles.
- ROOMS — ONE SWITCH PER ROOM (9/9 evening, G: "a list of all the rooms
  we've been to and the option to open the tab or not; if I selected to
  open it I obviously want it live"). The popup's Channels tab lists every
  room in extension/rooms.txt grouped as the file groups them, with its
  state: ON = tab open + read + trades LIVE; OFF = no tab, nothing read,
  nothing traded (the one-line reason sits above it in the file and shows
  dim in the popup); LAPSED = off because the sub ran out, probed daily.
  There is NO testing/paper state any more. The switch writes rooms.txt
  through the bridge (POST /rooms rewrites that one line in place), the
  extension re-reads the file and opens/closes the tab; the other Chrome
  profile sees the change within 30 s (pollRoomsFile) and follows for its
  own lane's rooms. START HERE opens only `on` rooms. CLOSING A TAB BY
  HAND IS NOT A BENCH — START HERE and a flip reopen every `on` room; the
  switch is the only bench. Benched rooms are never deleted from the file.
  WHOSE TABS THE REAPER MAY CLOSE (9/10). ONLY tabs the extension itself
  opened (`_OURS`). A tab a HUMAN opened is never closed, whatever URL it is
  on. Written the other way round first — "close any discord.com tab that is
  not an `on` room" — and within the hour it had eaten the Discord Settings
  tab G asked Claude to work in, twice, mid-edit. Sparing the ACTIVE tab is
  not enough: the moment he clicks away, or a tool drives another window, his
  tab stops being active. If you ever widen this again, that is the failure
  you are re-inviting.
  WHO MAY OPEN A TAB (9/10, G: "get rid of auto opening tabs UNLESS it's
  the start sniper"). Exactly three things, and nothing else:
    1. START HERE.bat, through its one-shot open-rooms request
    2. the popup's Channels switch (his click)
    3. whopSelfHeal() — kept on his call so the Whop lane can revive its own
       4 tabs; its dedupe now reads pendingUrl and queries the whole origin,
       because the old query missed a still-LOADING tab and that is how a
       heal pass turned 4 Whop tabs into 8
  roomSchedule() no longer opens anything — it used to open every `on` room
  at 9:15. It still CLOSES at 4:30, which is what stops the overnight pings.
  probeOne() opens a lapsed room off-hours to see if access came back and
  closes that tab seconds later in a finally — a door-knock, not an open.
  NO ACCESS = OUT OF SERVICE (9/10, G: "do not open the tab if we don't have
  access"). revokeCheck() reads the tab titles it already has; a room whose
  title says "No Access" is now written to rooms.txt as `lapsed` through the
  bridge and its tab closed, instead of only logging a warning. RWGates
  proved the warning alone was useless — it fired for three weeks while the
  room kept opening a blank tab every morning. `lapsed` not `off` on purpose:
  the daily probe keeps knocking, so it un-lapses itself if the sub returns.
  6th field = the room's RULES (9/9 evening): comma flags `bare` (an entry
  with no verb counts, AND its tokens may arrive in any word order — see
  WORD ORDER below), `dotdate` (the expiry is written with a DOT — Maguro's
  "$slv 63c 10.16 2.35" is Oct 16 at $2.35; per-room because elsewhere that
  number IS the price), `pivot=NQ` (the room trades ONE future and writes only
  the last digits of the level — Chika's "short 195 pivot" is NQ 29,195; the
  BRIDGE expands it against a live quote, the browser never guesses a price),
  `readonly` (read the room and write down what we WOULD have done, send
  nothing — NOT the same as `off`, which reads nothing at all),
  `sym=SPX` (symbol to assume when the call names none).
  The `spx` flag was DELETED 9/10 on G's instruction — see NO SPX->SPY.
  The bridge DERIVES dot_date_channels / entry_no_verb_channels /
  default_symbol_channels from these (apply_room_rules, at boot and on
  every write) — settings.json no longer holds those lists. Rules count
  whatever the room's state (shabs/eli are off but relayed via OWLS).
  Set from the popup: the pills on each Channels row (SPY-proxy / bare /
  SPX / 24h).
- ROOM HOURS (9/9 evening, G: "open the rooms at 9:15 and close them at
  4:30 PM — we can't follow any alert then, don't bomb Discord with pings;
  keep the futures channels always open"). An `on` room has a tab only
  9:15–4:30 PM ET on weekdays (no market holidays) UNLESS its rules carry
  `always` (the futures rooms: Platinum futures-alerts, Whop Futures; ZT
  fut-1/2 and NGD carry it too for when they're on). background.js
  ROOM_HOURS + roomSchedule() on the 30 s alarm: inside the window it opens
  any missing `on` room of its lane (3 per pass, 6 s apart); at the 4:30
  boundary (and once at startup if already outside) it closes the day's
  room tabs; a room opened by hand at night is left alone until the next
  4:30. Never closes a window's last tab — the dashboard page takes its
  place. START HERE now only SEEDS each browser (main Discord room, first
  ON Whop room) and hands the rest to the extension via the request token,
  cold or warm — so a 7 AM start opens the futures rooms and the rest come
  up at 9:15 by themselves. Switching a room ON at night says "its tab
  opens at 9:15". Each Channels row shows "last msg HH:MM" — the newest
  message that room POSTED (its own timestamp, survives reloads).
- SELF-SERVE PANELS — TEST BUILD (9/9 evening, G: "what else can we apply
  this methodology to so I don't have to bother you?" — "make them just to
  test, I might want to remove"). Four panels, each one bridge endpoint
  pair + one popup block, marked "SELF-SERVE" in bridge.py / popup.js /
  popup.html / background.js so removal is deleting the marked blocks:
  · CALLERS tab — THE TRADER SCOREBOARD. Ranked by net $, and the board's
    total RECONCILES: ledger +4770 = G's named +36 + G's hand trades +1150
    + callers +3584. Rules learned 9/9-9/10 from G's spot-checks:
    (a) ONE ROW PER POSITION — days/*.json re-lists an open position every
    day until it closes, so a 3-day hold read as 3 fills (299 rows for 247
    positions; Stormzy's 5 futures positions read as 13). Keyed on
    caller+contract+entry time, richest copy wins. (b) PAPER IS NOT MONEY —
    counted as a call taken, shown greyed, never in the net ("are alerts"
    read −$732 when the real number was −$62 live; the rest was one paper
    HPE trade). (c) FUTURES fills are counted, not valued — the NinjaTrader
    path records no P&L, so a futures caller shows "$0 · N futures", never
    a fake zero. (d) A FILL WITH NO BOOK ROW IS STILL SOMEBODY'S CALL —
    build_ledger.load_fill_callers() reads the caller back from the WORKING
    line above each trades.log FILLED ("WORKING QQQ — Demon Alerts's call"),
    same symbol, 60 lines of reach. That attributed all 41 rows that used to
    sit at room "?" with no name. (e) G'S OWN HAND TRADES ARE NOT A CALLER'S
    RECORD — export-only/manual rows are skipped, not bucketed (+$1150 of
    his Market Sniper scalps was inflating the board). What is left in the
    bucket is 30 fills / −$194 from Aug 7-20, before the book recorded a
    caller at all; the log has no WORKING lines that far back, so it stays.
    WHEN FUTURES EXECUTION WORKS, PULL ITS RECORDS THE SAME WAY
    THE OPTIONS ONES ARE PULLED (broker export → master_broker.csv →
    ledger), or the board keeps lying about the futures callers.
    Every trader ever followed (ledger + alerts; key =
    lowercase alphanumerics of the name), record inline, one switch. OFF =
    settings.json callers_off gets the key; the bridge refuses that
    trader's OPEN/ADD at the door ("switched OFF in the popup's Callers
    tab"); exits never gated; the room keeps reading. GET/POST /callers.
  · NEEDS YOU tab — what's waiting on G: bridge side (STOP file, announcer
    paused, Webull not connected, buying power < $150, lapsed rooms, queued
    restart) + extension side (ON room with no tab in this lane, "No
    Access" title, reader silent > 3 min in market hours, extension update
    waiting). Buttons = the old .bat files / F5: reload dead readers,
    open missing tabs, announcer on/off (announcer.stop), restart bridge
    (bridge.restart), reload extension. GET /needs, POST /fix, messages
    NEEDS? / FIX.
  · STRATEGY NUMBERS (Strategies tab, bottom) — born stop %, take-profit %
    (hard-close mode only), ratchet arm %, ratchet rung %, round-number
    wait minutes; each with its backtest note; ranges enforced (stop 2-30,
    arm 1-30, rung 0.5-20, wait 1-30); two taps to save; written to
    settings.json (strategy.ratchet_arm_pct / ratchet_rung_pct are NEW
    keys, applied to ratchet_tiers.TIERS live; pullback.timeout_seconds
    applied to the live Pullback). GET/POST /numbers. Changing them is
    G's call by house rule — the panel is him making it.
  · ROOM RULES — the pills above.
  None of these places, cancels or sizes an order by itself.
- STRIKES: never more than 1 strike OTM; deeper snaps to the first OTM rung
  (quote-verified). 3-ITM translation for SPY/QQQ/Mag7 0DTE. ADD buys the
  held strike.
- "ADDED <full contract>" you are not in = an OPEN entry. A bare "added to
  SPY" refuses.
- NO SPX→SPY. DELETED 9/10, G: "do not translate any SPX to SPY. Delete any
  sort of translation between SPX and SPY." SPX/SPXW/XSP/RUT/NDX/VIX entries
  are HELD with a plain reason until execution.index_broker is set
  (tastytrade or tradier, a separate funded account). SPY 760c is not SPX
  7600c — different multiplier, tick and settlement. OWLS relay still gives
  shabs/eli default_symbol SPX so the CONTRACT is read right; it just does
  not go to Webull. Exits on an SPX position are unaffected (there are none).
- WORD ORDER (9/10, G: "it doesn't matter the order of the expiration or the
  price or the ticker. It's not relevant. It could be in any order"). In a
  `bare` room the reader strips THIS contract's own three tokens — ticker,
  strike+side, date — wherever each sits, and fires if nothing is left over:
  "8/24 $255P $AMZN", "2DTE $765C SPY CALLS", "$255P $AMZN" all read.
  SCOPED ON PURPOSE: unscoped it fired "TSLA 9/4 360P .72" in every room,
  which is a real entry in some rooms and a chart caption in others.
  test_word_order.js + test_bare_entry.js hold both sides.
- TWO CONTRACTS IN ONE MESSAGE = TWO ORDERS (9/10, G: "when you have
  multistrikes, just buy both of them. Buy two contracts, one of each").
  ONE contract each, separate positions with their own born stop and their
  own ratchet — not a spread. Two shapes:
    "$NVDA $225C/ and $230C NEXT FRI"            two strikes, one expiry
    "$APLD 10/16 30c 2.75 ... $APLD 9/18 30c .9" two expiries, own prices
  The second leg goes only after leg one is ACCEPTED. Guards: same ticker
  only (two DIFFERENT tickers on a line is a levels row / watchlist — take
  the first, leave the rest); a bare strike with another ticker written in
  front of it is that ticker's, not a sibling; call+put is a strangle and
  the whole line refuses rather than trading one leg; max 3 extras.
- EXPIRY, in one place (webull_options.expiry_to_date):
  · NDTE is N CALENDAR days out. If N lands on a weekend or holiday it rolls
    BACK to the previous trading day (G, 9/10: "there is no 3DTE if in three
    days is a Saturday — it would just end in 2DTE"). Never past today.
  · NO DATE = 0DTE (G, 9/10) on every root that HAS a same-day listing —
    DAILY_EXPIRY_ROOTS (SPY/QQQ/IWM + SPX/SPXW/XSP/NDX/NDXP/RUT/RUTW). On a
    single stock there is no such contract; that Friday is the only listing
    there is, and it is used. Clues in the message win first: "NEXT WEEK" and
    "NEXT FRI" -> next week's Friday, a shouted MONTH -> that monthly.
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
- THE RATCHET (5/3/5 since G's 9/10 "flip it", flat, no cheap tier): born stop −5%
  (strategy.stop_loss_pct) placed WITH the order as a combo bracket, rebased
  to the FILL if filled better, never at/above the fill, never inside the
  bid/ask. Arm at +3% → stop to BREAKEVEN; then every further +5% locks
  another +5% (ratchet_tiers.py TIERS = (None,(3.0,0.0,5.0))). A rung must
  clear 4 ticks (MIN_RUNG_TICKS). Ratchet tries REPLACE, falls back to
  cancel+place and says so. Anti-clip is OFF ENTIRELY (verified 9/9:
  Book.anticlip=False, no strategy.anticlip key) — turn it on with
  strategy.anticlip=true and it caps locked ≤60% of gain, at 2+ DTE only.
  WHY 5/3/5 — CHANGED 9/10 ON G'S CALL, and it is the first ratchet number
  here that clears its own error bar. The OPRA tape was bought (537
  contract-days, 1.02M per-second quotes), so ratchet_sweep_fine.py re-swept
  its 294 combos on REAL price paths, on 115 trades not 80 — the sweep was
  also scoring 707 rows whose caller was "?" (G's hand trades and adopted
  positions) as room calls; EXCLUDE_WHO now drops "" and "?" with "gian".
      old 7.5/5/2   $158   rank #82 of 294
      NEW 5.0/3/5   $504   rank #1
  Paired bootstrap, same trades, 2000 resamples: +$3.01 a trade, 95% band
  +$0.72..+$4.91 — outside zero, so an edge, not the luckiest of 294 cells.
  Win rate FALLS 35% → 25% while dollars rise: more small scratches, far
  fewer big losers. The 9/9 "small rungs win" finding was an artifact of
  backfilled minute data that never showed the intraday retraces a 2% rung
  keeps stopping into. Cheap (<$1) still loses under every spacing, so no
  cheap tier. Re-run `python3 ratchet_sweep_fine.py` as trades accumulate.
  ONE READER FOR "WHAT IS LIVE" (9/10): ratchet_tiers.live_spacing()
  returns (born, arm, step) read from settings.json + TIERS. Every backtest
  and report now calls it — ratchet_sweep_fine, chart_contracts,
  entry_compare, missed_dollarize, pullback_levels. They used to TYPE the
  live numbers into their own headers and had been comparing against
  7.5/5/5, a rule nobody was running, for two days.
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
  is; DATA-MAP.md says what is in it. A session that skipped DATA-MAP.md on
  9/11 concluded only 16 of 331 alerts were recoverable and missed 425.
- Compile-check everything touched (python3 -m py_compile / node --check).
  Extension changes → bump extension/manifest.json so a reload is provable.
  Never install the streaming SDK family (webullsdkcore) into the bridge's
  Python. Sandbox trading is RETIRED — paper is LOCAL (SIM tickets).
- Discord API is NOT an option (user-token automation = permanent ban risk
  to the account + paid subs; official bots need the server owner).
  Reaffirmed 9/9. Browser reads only.

ROOMS / TABS / READERS
- rooms.txt = THE channel list (tabs + trading, one file). START HERE IS
  FULLY UNATTENDED (G, 9/9: "no input from me"): every run drops a one-shot
  open-rooms.request; the bridge serves its token on /build; each browser's
  extension then opens every rooms.txt room it lacks a tab for (its own
  lane, ≤3 per 30 s tick) until a pass opens none, then marks the token
  done. So a warm start (Chrome already open) fills in the missing rooms
  without closing Chrome; a cold start opens them all itself (~2.5 min
  paced flood; count tabs after, not during) and launches the announcer.
  Between runs NOTHING opens rooms — a tab he closes by hand stays closed.
  No prompts: git fails fast instead of asking for a credential
  (GIT_TERMINAL_PROMPT=0 / GCM_INTERACTIVE=never; a failed push keeps
  local work and skips the mirror), and every Chrome launch carries
  --hide-crash-restore-bubble so "Restore pages?" never waits on a click.
  The only inputs left are the ones no script may do: a Discord/Whop login
  if a profile is logged out, and Webull keys in the popup.
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
  DISCORD'S OWN LIMITS FOR A USER ACCOUNT (docs.discord.food, 9/9): ONE
  gateway session start per 5 s (max_concurrency 1; more = Invalid Session),
  max 50 ACTIVE sessions — a reloaded tab's old session lingers minutes, so
  a reload storm stacks ghosts past the cap — and "suspicious sessions may
  be flagged … account locked, requiring a password reset." There is NO
  identify-per-day budget for user accounts (that is bots only). So: START
  HERE opens ONE tab per 6 s, the one-shot opener sleeps 6 s between opens,
  and an INSTANT logout after a good login means a lock — his email from
  Discord + password reset clears it, not code.
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
  tab read since the morning; the official API stays WALLED for member reads
  until Felony installs G's Whop app with chat:read — unlocks itself, no code
  change, if that ever happens). FOUND 9/10: tabs being the only source also
  meant Day Trades caught exactly 1 alert in the whole month since 8/13 —
  openMissingRooms() only fills a missing tab on START HERE's one-shot token
  (9/8, so a DISCORD tab he closes by hand stays closed, his rule), and
  nothing ever noticed if the whole "Sniper Whop" Chrome profile wasn't even
  running. FIXED 9/10, two parts, Discord's 9/8 behavior untouched: (1)
  whopSelfHeal() in background.js calls openMissingRooms() every watch-build
  tick, but ONLY in the whop lane — he doesn't hand-close Whop tabs, they die
  from crashes/memory/eviction, so self-healing them doesn't fight his rule.
  (2) _whop_loop.bat + _whop_hidden.vbs (same pattern as the bridge's own
  _run_hidden.vbs) watch whether the Sniper Whop Chrome window is running at
  all and relaunch it if not; installed by START HERE.bat as a Startup entry
  + 30-min revive task, same durability model as the Fill Announcer. Felony posts QQQ/SPY contracts when he trades
  NQ/ES. Felony goes live on ZOOM mornings (~9:15, event on FST's "Zoom
  Links & Events" page; recurring meeting 89312529658 on us02web) — join the
  WEB client `us02web.zoom.us/wc/join/<id>` in the WHOP Chrome profile so
  tabCapture hears it; the desktop app is invisible. Exact recipe:
  reference/FELONY-ZOOM-JOIN.md. Scheduled task felony-live-whop-check does
  it at 9:12 weekdays (first proven live 9/9). EARS RULE: tab audio needs
  ONE Sniper-icon click on that tab (Chrome's tabCapture grant); a scripted
  join logs the refusal and retries on front/click (v3.5.74). Never join a
  second time if reads.log already shows 🎙 lines — it bumps the first.
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
- BROKER RECORD → master_broker.csv (one row per Webull order leg, every
  day). The autopilot pulls the account's order history every Mode B run
  and writes it to ONE fixed file, Webull_Orders_auto.csv, OVERWRITING it
  every run (G, 9/10: "have one that overwrites" — no deletes, ever);
  build_ledger's absorb_exports() (runs inside every ledger refresh) folds
  it into master_broker.csv and leaves it in place. Never write dated
  Webull_Orders_<date> files — the folder holds the master plus that one
  scratch file (G, 9/9: never dated piles).
  Merge is REPLACE-DON'T-STACK per order (placed-time+contract+side+size+
  limit): a later pull replaces a WORKING snapshot, never duplicates it.
  Backups: backups/<file>.bak-<stamp> (last 5) — for master_broker,
  master_ledger and master_alerts; NO .bak files in the root anymore.
- THE RECORD IS THE BROKER'S, THREE MONTHS DEEP (9/10, G: "I feel I'm still
  missing losing trades — no way I've won and not lost that much"). He was
  right, and the cause was an accounting bug: 26 of 74 closed August option
  positions had the SALE PROCEEDS written into `pl` (sold at 5.90 → "+590"
  on a trade that lost $11). It overstated the record by +$5,137 and made
  26 losses the board's biggest wins. Two fixes: build_ledger now COMPUTES
  P&L from the fill and exit prices (the book's claim is kept in store_pl,
  the broker's export still outranks both), and the whole broker history
  6/12→9/09 was pulled from Webull (1,186 orders, MCP get_order_history in
  ≤100-order windows → Webull_Orders_2026-history_auto.csv → absorbed).
  THE PULL MUST BE PAGED OR IT LIES QUIETLY (9/10). get_order_history caps
  at 100 orders per call and returns the newest first — a wide window drops
  the REST WITHOUT SAYING SO. The first sweep looked complete and was
  missing a third of August; that is why IBM/BAC/ZETA looked like trades
  the broker had never heard of (G: "those tickers were allowed before" —
  he was right, they were real). RULE: after every window, if it returned
  exactly 100 orders there IS another page — re-request with
  last_client_order_id = the last combo's client_order_id and keep going
  until a page returns fewer than 100. August took 4 pages.
  THE REAL NUMBERS, from the properly paged broker record: 705 completed
  round-trips, −$4,228 all in; 32% win rate, avg win +$79, avg loss −$47.
  Split: G's OWN hand trading −$4,332 over 665 closed trades; THE BOT is
  +$301 over 143. By month: June −70, July −335 (both 100% G, the bot did
  not exist until 8/06), Aug −4,544, Sep +721. Worst days 8/24 −1,325 and
  8/17 −1,048. Do not quote a P&L from anything but broker-priced rows.
  COVERAGE TODAY: 728 of 905 real fills (80%) are broker-settled.
- THE BOT ON ITS OWN (9/10, G: "let's not take my own trades, the app is
  for this"). A BOT trade = a row with a REAL caller — caller "?" means
  unknown, NOT a caller, and treating it as one put 36 of G's/adopted rows
  on the bot's record (−$373 of them) — AND not manual/adopted AND not
  export-only. By that rule: 134 entries, 73 closed, NET −$309, 33% win
  rate. Of those 73, only 27 are broker-verified (+$9); the other 46 are
  book-priced (−$318). THEN PRICED STRAIGHT OFF THE BROKER instead (each
  bot row matched to a completed round-trip by contract + entry price, the
  book bypassed entirely): 74 matched, NET −$301, 34% win rate, avg win
  +$46, avg loss −$30, Aug −321, Sep +20. TWO INDEPENDENT METHODS AGREE
  (−$309 from the book, −$301 from the broker), so it is real: THE BOT
  LOSES ABOUT $300 OVER 5 WEEKS, roughly −$4 a trade. Why, in one line:
  34% × $46 = $15.6 won per trade against 66% × $30 = $19.8 lost. The stop
  is NOT the problem — the losses are already small, which is the ratchet
  doing its job. The gap is hit rate and winner size: WHICH CALLERS get
  followed and WHERE it takes profit. Best: SKHY +249 (The Pawn), NVDA
  +120 (Bullwinkle), GOOGL +119 (Unraveller). Worst: TSLA −112 and META
  −106 (both Unraveller), MP −96 (EvaPanda). THEN THE LAST CONTRACTS WERE RECOVERED
  (the gap rows had strike/side/expiry read back but the symbol was never
  assembled — the build ran in the day-row loop while those rows are made
  later; one-line ordering fix). 124 of 134 bot rows now carry a contract;
  the last 10 are futures, which have none by nature. Broker-matched bot
  trades 74 -> 107: NET -$545, -$5.1 a trade, 34% win rate.
  DID THEY FOLLOW THE ROUND NUMBER? Each entry tagged by whether a
  "PULLBACK ...: touched $N - buying now" line sits within 4 min of it:
      big name, WAITED for the round number   37 trades   +$25   +0.7/trade  39% win
      big name, entered INSTANTLY             30 trades  -$301  -10.0/trade  37% win
      everything else (no pullback available) 40 trades  -$269   -6.7/trade  26% win
  Like-for-like (same symbol class, only the wait differs) waiting is
  +$10.7 a trade better - but that is 1.1x its own noise on 37 vs 30
  trades: SUGGESTIVE, NOT PROVEN. It agrees in direction with the 9/9
  one-second-bar study (+$8/contract), which is a reason to KEEP the $1
  rule, not to widen it. The louder, cleaner line: the 40 trades in names
  too small to qualify for a pullback (INTC, SPCX, WMT, RIOT, ZETA, SKHY,
  LYFT, SMCI) lose -$6.7 a trade at a 26% hit rate - a FILTER question,
  and where the bot's money actually goes.
  RATCHET SCENARIOS: UNBLOCKED 9/10. The OPRA tape was bought and now holds
  537 contract-days / 1.02M per-second quotes (databento_tape.csv, despiked
  into databento_tape_clean.csv). option_tape_pull.py buys cbbo-1s, one
  pull per contract-window, four at a time, `--minutes N` to stop and
  resume; the full-book cmbp-1 schema it used first was ~100x the rows for
  the same answer. Only 9/9 itself is missing — OPRA history stops at
  13:30 UTC that day and the rest needs a live licence. Verdict is in THE
  RATCHET above.
  8/07's seven "missing" trades were ADOPTED at 08:12:13 pre-open — G's own
  positions from before, never bot trades, and no broker BUY exists that
  day because they were bought earlier.
  TWO RECOVERIES that made the bot's rows checkable at all:
  load_fill_contracts() reads the contract back off the ORDER IN line for
  trades.log-only rows (39 recovered — they had no strike/side/expiry, so
  they could never be matched to anything), and _resolve_expiry() gives a
  short expiry its year from the trade's own date ("8/21" on a trade dated
  8/17 → 2026-08-21; NDTE → date+N). Bot option rows with a full contract:
  85 of 124, of which 81 match the broker on both legs, 2 have no BUY, 2 no
  SELL. Ledger option rows with a full contract: 879 of 950.
  TWO MORE BUGS THE SAME NIGHT, both found by G spot-checking one trade
  ("SKHY actually made me like 300"): (a) THE BROKER DATES A TRADE BY ITS
  ENTRY, THE BOOK BY ITS EXIT — SKHY was bought 8/11 and sold 8/12, so an
  entry-date-only trip match failed and the book's row kept its own WRONG
  exit (5.90 vs the broker's real 8.50: −$11 booked instead of +$249).
  _find_trip now matches either end of the round-trip. (b) ONE ROW PER
  POSITION — days/*.json re-lists an open position every day until it
  closes, so SKHY existed twice and the wrong copy was the one read last.
  _collapse_carryover() keys on caller+contract+ENTRY TIME and keeps the
  most trustworthy copy (broker-confirmed > knows its exit > earliest); it
  only touches days-json rows, because the export's FIFO round-trips and
  the log's FILLED lines are already one row per event. 849 → 763 rows.
  STILL OPEN: 15 days where a book-priced row disagrees with the broker
  (the book's exit price is wrong and no trip matched). The broker total is
  unaffected — it is read straight from the export.
- NO PAPER, ANYWHERE (9/9, G: "delete all paper trades data from the app, I
  don't want any more confusions"). build_ledger keeps account="paper" rows
  OUT of master_ledger.csv, so the board, journal, scoreboard, announcer and
  every backtest are real money only. The 4 rows that existed were archived
  once to archive/paper-fills-2026-09-09.csv (−$686, all August; the twin
  HPE pair alone made the Callers board read "are alerts −$732" instead of
  −$62) and days/*.json still holds them. account="unknown" is NOT paper —
  41 real broker fills with no room row; they stay. execution.webull
  .paper_trading is false and the bridge now WARNS at boot if it is ever
  switched on, because a paper fill would leave no record at all.
- FILLS → master_ledger.csv (built by build_ledger.py, read via ledger.py).
  Sources in trust order: master_broker.csv (the account's own history,
  FIFO-paired per OCC ACROSS days so a swing meets its own lot; trip date =
  the buy's day) > trades.log FILLED > days/wallet.trades > days/table.
  RULES: the broker's exit/P&L/state/account WIN
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
- PRICE TAPES → tape.py is the ONE registry. Six sources, verified 9/9:
  webull, tasty_greeks, tasty_quote, databento, databento_clean, missed.
  NOT bars/ — that and bars_capture.py were archived 9/9 and tape.py never
  registered them. (test_architecture.py asserted an exact set of four and
  had gone stale; it now requires the four core sources and checks every
  registered source resolves to a path.) tape.path(
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
- POST-MORTEMS → master_postmortems.csv + postmortems/<date>_<occ>.md
  (postmortem.py; a SECOND round-trip on the same contract the same day is
  <date>_<occ>-2.md — named by the trade's rank among that day's graded
  trades on the OCC (9/10, after SPY 758C ×2 overwrote itself twice); the
  csv row is keyed date+occ+fill+exit; G 9/9: "analyze every single trade after exiting … be
  attentive to these"). One verdict per exited bot trade — NOISE CLIP /
  ARM CLIP / GOOD STOP / LEFT MONEY / GAVE BACK / GOOD EXIT — with the call vs our fill,
  the RN wait, the ride (MAE/MFE), the bid at +30s/+1m/+5m/+10m after the
  exit, the widest born stop that would have survived, and every machine
  fault line in the window. The bridge's POSTCHECK loop schedules it 10.5
  min after each close/stop; quote_bus keeps taping an exited contract for
  10 min (LINGER_S) so the after-exit half exists. The autopilot reads new
  ones every 30 min (faults = bugs to fix same day) and tallies them at the
  close (the 0DTE stop question is decided from that tally, by G). His own
  hand trades (Gian / manual) are never graded.
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

## Broker facts (Webull OpenAPI — reference/OPTIONS-BROKER-REFERENCE.md first)
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
- FUTURES-ACCOUNT POSITIONS POLL (bridge _FUT_POS_BACKOFF): after 3 empty
  reads it backs off — capped at 60 s while futures_brokers.webull is on,
  300 s while it is off (9/10: the 60 s cap alone was 187 of the day's 256
  429s, all on a flat futures account; the only futures there could be G's
  own, never managed). Any non-empty read resets it. Exponent clamped
  (2**(fails-3) overflowed float after ~17 h flat).

## Operational truths
- sniper-autopilot scheduled task: */30 ET — preflight ~9:30, sync watch
  in market hours, close-out ~16:30 (the old daily-journal-and-fix 16:45
  task is PAUSED, folded into Mode C). It never places/cancels orders or
  touches settings.json.
- THE PAGE (v3.5.80, 9/9 evening, G: "make the popup an html page — it's
  super small now"): the SAME popup.html opened as a normal tab —
  chrome-extension://iaokjlndnmamhgmgkoldkhjehmdkginj/popup.html?page=1
  (the "⤢ page" button in the popup opens or focuses it; bookmarkable).
  No 800×600 cap; every tab becomes a card on a 3-column grid (Channels and
  Logs span the height); same code, same 1-2 s polling of the same bridge.
  One file, two sizes — never a second dashboard. IS_PAGE in popup.js
  guards the popup-only bits (window.close after a room jump).
- POPUP (v3.5.77, 9/9 evening): the rooms list paints FIRST in render()
  and any exception in the rest of the popup is written INTO the Channels
  pane ("popup error (…): …") — never a blank pane again. It caught its
  first one the same evening: `esc is not defined` at renderTable — the
  HTML-escaper lived only as a local inside the holdings block while the
  module-level renderTable() called it, so ANY day-table row killed render()
  before the rooms drew (blank Channels tab since the 9/7 slimming). esc()
  is module-level now, one copy. If G reports a broken popup again, the red
  line under the rooms is the diagnosis; ask for it. Claude-in-Chrome CANNOT
  read the popup (another extension's page; screenshots/JS/console all
  refused). Extension id: chrome-extension://iaokjlndnmamhgmgkoldkhjehmdkginj
  (Chrome hashes the folder path as UTF-16LE; same id in both profiles).
- Multi-account: extras mirror LIVE entries 1:1 with own books/stops.
- START HERE.bat saves+pushes before its reset; RESTART BRIDGE.bat
  pre-flights and warns. Logs: trades.log (the story), bridge.log (raw,
  20 MB, no rotation yet), webull_api.log, announcer.log, deadman.log.

## SECOND MACHINE (planned 9/9 — G: "another account on a different computer
## for other subs"). Built default-off; nothing changes until PC2 exists.
- WHY: Discord's identify budget and Chrome's RAM are per account / per
  machine. A second Discord account on a second PC doubles both.
- ARCHITECTURE: ONE bridge, ONE book, ONE rate budget — PC2 runs only Chrome
  + the extension and sends to THIS PC's bridge over the LAN. Never a second
  bridge on the same Webull account (two books break every dedupe and
  coexistence rule).
- SECURITY (in the code now): settings execution.bridge_listen (default
  127.0.0.1) + execution.bridge_token (default ""). The bridge refuses to
  bind off loopback without a token. Off-loopback callers must send
  X-Sniper-Token (constant-time compare); loopback callers are untouched.
  Extension: an optional, gitignored extension/bridge.txt —
  `http://<PC1-LAN-IP>:8787|<secret>` — makes every bridge call carry the
  token (fetch is wrapped once; the popup's askBridge adds it too).
- PC2 SETUP, when it exists: (1) this PC: put a long random string in
  bridge_token, bridge_listen "0.0.0.0", allow TCP 8787 in Windows firewall
  for the LAN only, restart the bridge; (2) PC2: clone the repo, create
  extension/bridge.txt with PC1's LAN IP + the same secret, add
  `"http://<PC1-LAN-IP>/*"` to extension/manifest.json host_permissions,
  Load Unpacked in a Chrome profile logged into the NEW Discord account;
  (3) Whop: re-link the moved subs to the new Discord account so the paid
  roles land there.
- NOT BUILT YET — LANE TAGS: both PCs read the same rooms.txt, so today they
  would open and trade the same rooms. Next build: a 5th field per line
  (`|pc2`) + a lane name per machine; each extension opens/trades only its
  own lane, START HERE's cold-start loop honours it too. Relay rooms both
  accounts can see stay protected by the bridge's 20 s echo-lock. Do this
  BEFORE PC2 goes live.

## Pending — G's side (real-money / restart actions only he takes)
1. The Claude Project: paste project/PROJECT-INSTRUCTIONS.md into the
   Instructions box; re-upload project/context/HANDOFF-snapshot.md and
   rooms-snapshot.txt; delete the six 9/2 files listed in project/README.txt.
2. Market Sniper: apply HANDOFF-RATCHET-2026-09-09.md (options 5→2 rung,
   futures decouple) — G's call whether Claude does it or he does.
3. NinjaTrader ATM template "SNIPER": stop 100 ticks / target 200 (=25/50
   MNQ pts), qty 1 — create in NT8, type SNIPER in the popup.
4. Close any old parked Whop tabs. (Chrome hardware acceleration: DONE 9/10
   — `--disable-gpu` is now on every flagged Chrome launch in START HERE.bat
   and _whop_loop.bat, so it applies itself on the next full restart and no
   longer depends on the Settings checkbox. Reason it matters is CORRECTNESS,
   not speed: GPU black-tab disease paints a room black, and a black tab
   reads NOTHING while looking open. Flags only bind on a cold start — if
   that profile's Chrome is already running, the launch reuses the existing
   process and ignores them.)
5. Announcer: paused since 9/2 — the Needs-you tab has the on/off button.
(OWLS all-alerts "no tab" — RESOLVED by ROOM HOURS: the extension opens
every `on` room at 9:15 by itself; verify OWLS reads on 9/10.)
(daily-journal-and-fix — DELETED 9/9 evening; Mode C did its first clean
close-out today.)

## Watch items (open)
- PULLBACK STOCK TARGET vs THE RATCHET (9/10, G's call): a pullback entry
  manages "off the stock" and CLOSES at a fixed stock target ($1 past the
  round number: META 645P out at 648.62). On 9/10 that took +$80 at 6.23
  while the ratchet's stop sat at 5.65 (+4% locked) and the contract ran
  to 8.50 inside 10 min (+$307). Doctrine says the ratchet is the ONLY
  exit; the stock TARGET is a second, earlier one. (a) delete the target,
  keep the pullback stock-STOP; (b) keep it. Nothing changes until G says.
- The 9/10 META row in master_ledger.csv reads exit_by "room call" from
  the old "sold on their call" wording (fixed 9/10 16:33) — it was the
  pullback target, NOT a room exit. Not an ENTRIES ONLY breach.
- **7-ROOM RE-ENABLE (04:14) — RESOLVED, rooms.txt back at 19 by 04:36.**
  Something briefly uncommented 7 cut rooms (Options Watchlist, Vero 1,
  Vero 3, Platinum equity, NGD ngd-trades, shabs, eli), taking the file to 26;
  it (or G) reverted to 19 (15 Discord + 4 Whop) 22 minutes later, confirmed
  unchanged since (rooms.txt mtime 04:36, still 19 lines at today's
  close-out). shabs + eli stay retired in favor of OWLS all-alerts — see the
  Pending item above, since that relay has had no tab all day.
- Discord logoff under tab load — 9/9: 27 rooms cut to 8 (ledger-dead rooms,
  then the whole ZTRADEZ server on its sub lapsing), G re-added 11 to land at
  19 (the 04:14 blip above never stuck). Watch whether logoffs stay clear at
  this count; if not, the next lever is moving rooms across more Chrome
  profiles, not further cuts.
- 141 ledger fills still at room "?" — but only 30 have no CALLER now
  (Aug 7-20, before the book recorded one). Room "?" on the rest is
  cosmetic: the caller is known, the room name was never written.
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
MARKET-HOURS.md · reference/ (broker reference, anti-clip study, ratchet
notes) · extension/rooms.txt · settings.json (keys, gitignored) ·
master_ledger.csv / master_alerts.csv (truth) · days/ (per-day state) ·
handoffs/ (bridge's daily photos) · project/ (Claude Project files).
