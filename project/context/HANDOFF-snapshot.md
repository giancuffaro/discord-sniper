# DISCORD SNIPER — THE HANDOFF
Read this first. It is the living memory: what the machine is, every rule in
force, how G works. It holds ONLY what is true right now. The full history —
every session's notes, every bug's story — lives in HANDOFF-LOG.md.
Last updated: 2026-09-09 (evening) — v3.5.79: SELF-SERVE test build (Callers tab, Needs-you tab + fix buttons, Strategy numbers, room-rule pills; grabber moved to Logs); ONE SWITCH PER ROOM — rooms.txt
now lists all 51 rooms with on|off|lapsed, the popup's Channels tab shows every
one grouped with a single switch (on = tab + read + LIVE; no testing state),
the bridge writes the flip (POST /rooms), START HERE opens only `on` rooms;
popup paints the rooms FIRST and shows any popup error in the Channels pane —
which caught the real bug: esc() undefined in renderTable, blank Channels since 9/7, fixed;
build_ledger.py's trip-matcher now checks qty, not just price (a stale store
snapshot could grab the wrong-size export trip — found on today's QQQ 716C,
also caught 2 older cases on 9/4; zero change to any day's reconciled total);
ARM CLIP added as a post-mortem verdict (alongside NOISE CLIP). Earlier today:
master_broker.csv (daily Webull pulls absorbed + deleted); pullback level
settled at $1 on real bars; post-mortem on every exit; one central file per data
family (ledger / alerts / tapes / holidays / announcer board); ratchet 7.5/5/2
flat, futures ratchet decoupled; Whop API path deleted; the tab-reload storm
found (662 reloads/day, zombie heartbeat) and fixed; rooms settled at 19
(15 Discord + 4 Whop, all live, 0 ZTRADEZ — counted from rooms.txt 9/9 11:20,
replacing an earlier "26" that no longer matched the file); START HERE fully
unattended (one-shot open-rooms request, no git/Chrome prompts);
REPLACE-DON'T-STACK rule; folder cleanup to archive/; POSTCHECK stale-snapshot
false alarm fixed. Story of each in HANDOFF-LOG.md.

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
- The machine: Chrome MV3 extension (Profile 2; v3.5.79) reads 19 rooms —
  15 Discord + 4 Whop (Whop tabs are in the separate "Sniper Whop" profile.
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
  Not part of the Profile 2 tab count), 0 ZTRADEZ (whole server
  cut 9/9, sub lapsing — incl. Demon Alerts and MR.TOPHAT, same guild). G
  brought every non-ZT room back 9/9 once the reload storm was fixed (the
  "silent" verdicts were measured during the storm, so they re-measure on
  clean ledger data from here). extension/rooms.txt is THE list of EVERY
  room we have been to (51: 19 on, 28 off, 4 lapsed), one line each with a
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
  6th field = the room's RULES (9/9 evening): comma flags `spx` (index
  calls trade as SPY, strike/10, premium dropped), `bare` (an entry with
  no verb counts), `sym=SPX` (symbol to assume when the call names none).
  The bridge DERIVES spx_entry_channels / entry_no_verb_channels /
  default_symbol_channels from these (apply_room_rules, at boot and on
  every write) — settings.json no longer holds those lists. Rules count
  whatever the room's state (shabs/eli are off but relayed via OWLS).
  Set from the popup: the three pills on each Channels row.
- SELF-SERVE PANELS — TEST BUILD (9/9 evening, G: "what else can we apply
  this methodology to so I don't have to bother you?" — "make them just to
  test, I might want to remove"). Four panels, each one bridge endpoint
  pair + one popup block, marked "SELF-SERVE" in bridge.py / popup.js /
  popup.html / background.js so removal is deleting the marked blocks:
  · CALLERS tab — every trader ever followed (ledger + alerts; key =
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
  cancel+place and says so. Anti-clip is OFF ENTIRELY (verified 9/9:
  Book.anticlip=False, no strategy.anticlip key) — turn it on with
  strategy.anticlip=true and it caps locked ≤60% of gain, at 2+ DTE only.
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
- REPLACE, DON'T STACK (G, 9/9). When something changes — a rule, a value,
  a function, a setting, a room line, a doc — the new version takes the old
  one's place. Never leave the old beside the new: not commented out, not
  "superseded", not "legacy/old/deprecated", not a dead branch kept "just
  in case". One thing, one truth. History lives in git and HANDOFF-LOG.md,
  never in the working file. A fallback that must stay is a deliberate
  design decision, written as one — not leftovers. Applies to code,
  settings.json, rooms.txt, every .md, and this file.
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
  tab read since the morning). Felony posts QQQ/SPY contracts when he trades
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
  and writes the day as Webull_Orders_<date>_auto.csv; build_ledger's
  absorb_exports() (runs inside every ledger refresh) folds it into
  master_broker.csv and DELETES the daily file once every leg is provably
  inside — the folder keeps ONE broker file, never dated piles (G, 9/9).
  Merge is REPLACE-DON'T-STACK per order (placed-time+contract+side+size+
  limit): a later pull replaces a WORKING snapshot, never duplicates it.
  Backups: backups/<file>.bak-<stamp> (last 5) — for master_broker,
  master_ledger and master_alerts; NO .bak files in the root anymore.
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
  (postmortem.py; G 9/9: "analyze every single trade after exiting … be
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

## Operational truths
- sniper-autopilot scheduled task: */30 ET — preflight ~9:30, sync watch
  in market hours, close-out ~16:30 (the old daily-journal-and-fix 16:45
  task is PAUSED, folded into Mode C). It never places/cancels orders or
  touches settings.json.
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
1. OWLS all-alerts (shabs + eli's coverage) has had NO TAB since it was added
   to rooms.txt at 02:08 — dark all session (confirmed again at today's
   close-out, still in the "silent configured" list, zero reads in bridge.log
   ever). Only a START HERE run (or hand-opening the room tab) fixes it — the
   silence-alarm code fix shipped, but nothing opens a tab for a room added
   outside START HERE. Costly while dark: shabs alone ran +$15,898 in August.
2. Restart the announcer when he wants it back (it posts the ledger board).
3. Market Sniper: apply HANDOFF-RATCHET-2026-09-09.md (options 5→2 rung,
   futures decouple).
4. NinjaTrader ATM template "SNIPER": stop 100 ticks / target 200 (=25/50
   MNQ pts), qty 1 — create in NT8, type SNIPER in the popup.
5. Chrome: hardware acceleration OFF. Close any old parked Whop tabs.

## Watch items (open)
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
MARKET-HOURS.md · reference/ (broker reference, anti-clip study, ratchet
notes) · extension/rooms.txt · settings.json (keys, gitignored) ·
master_ledger.csv / master_alerts.csv (truth) · days/ (per-day state) ·
handoffs/ (bridge's daily photos) · project/ (Claude Project files).
