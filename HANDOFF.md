# DISCORD SNIPER — THE HANDOFF
Read this first for current operating state. Session history and past findings
live in HANDOFF-LOG.md; they are evidence, not current instructions.
Last updated: 2026-09-15 — room-chat exports are ONE FILE PER WEEK PER LANE (G's rule, v3.8.33 + ds_logs.py); the 16:40 audit starts with the broker export and ends by posting the one-screen BRIEF to Sniper HQ; PROVIDER KEYS / DEPARTMENTS / READER-UI / DAILY REPORT bullets condensed to state (history in HANDOFF-LOG.md).

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
- Do not create handoff copies, dated handoffs, or upload snapshots. Daily
  performance belongs in `daily-reports/`; operating rules belong here.
- `HANDOFF-LOG.md` is historical evidence, never current instructions. Retired
  handoffs are preserved in `archive/retired-handoff-documents-2026-09-12.zip`
  for explicit historical investigation only; do not apply their rules/code.

## Who and what
- Caller research catalog: `python caller_ledger.py` refreshes the ignored
  local-reader-measure/caller-identity/callers.sqlite3; /callers maps read-only
  account sightings by channel ID. Win rates stay unavailable until trade
  attribution exists, and a newly observed account never gets an execution key.
  See reference/CALLER-LEDGER.md; the 9/13 detail is in HANDOFF-LOG.md.
- Caller behaviour (9/14): options first trim median 5.4 min at +17%; no posted
  option stop — revealed give-up −17%; bot out before their first trim on 15 of
  22 matched pairs. reference/CALLER-PROFILE-2026-09-14.md (rebuild:
  reference/caller_profile.py).
- G (giancuffaro230@gmail.com) — maintains this code himself (9/13), trades options + futures live,
  real money. Wants it CONDENSED. "Fix everything is default always" — bugs
  get fixed without asking, same day. "Fix errors every day after journaling."
- The machine: Chrome MV3 extension source v3.8.31 reads Discord in Profile 2 and Whop in Profile 6 (display name “Whop Profile”). Typed, voice, and image alerts go to the Python bridge on 127.0.0.1:8787. Webull options use caller price or better, optional round-number pullback, a bracket stop born with the entry, and the flat 5/3/5 ratchet. Fill Announcer may be paused. The weekday autopilot audits and journals after close. Market Sniper shares Webull; this bot never manages its positions.
- Accounts: `execution.mode=dryrun` does not disable per-room live Webull
  orders. Verify current buying power and positions at the broker before
  making claims. Webull options share one API budget with Market Sniper;
  `futures_brokers.webull` and Topstep/Tradovate remain off. NinjaTrader
  execution was paused 9/13; its configured account remains untouched.
- Market Sniper on port 8000 is G's separate tool on the same account. Its
  positions are visible but never stop-managed or sold by Discord Sniper;
  Book.is_hand_trade enforces that boundary. The two apps' ratchet spacing
  differs; changing either is a separate trading-policy decision.
- Claude exports and project/context/ are historical reference only.
- PRODUCT NORTH STAR (G, 9/11): every day must leave a complete, auditable
  alert funnel and enough append-only price/event data to benchmark the
  caller's documented trade, the versioned bot policy on the same alert, and
  the broker-confirmed actual result. Daily reports are the readable snapshot;
  the growing dataset is what earns parser/strategy improvements. Exact caller
  results require real entry+exit evidence; never substitute a later high.
  Full contract: reference/EOD-BENCHMARK-SPEC.md.
- PROVIDER KEYS: the Keys pane saves OpenAI, Gemini and Perplexity under settings.json ai_provider_keys; saved fields hide behind an explicit Replace key, status returns presence flags only. OpenAI/Gemini feed the observer AND both live readers; Perplexity stored inactive; DeepSeek removed (G); Anthropic kept but billing-blocked. Saved-key PRESENCE is not a probe RESULT: billing, rate-limit, auth, access and connection failures carry distinct labels.
- DEPARTMENTS: enabled. Bridge audit loop calls health_tick every five minutes; extension maintenance publishes Discord/Whop lane heartbeat and reader issues. GPT-5.4 mini analyzes changed issues (12/day); Astra escalates multi-issue incidents (2/day), reviews selected reader disagreements (20/day) and analyzes the daily reports after the 16:40 audit (1/day). Output is advisory files in department-reports, never code or orders. Context snapshots persist at most once/minute.
- READER/UI: observer retains 50 prior messages within 72 hours; fresh-post admission 15 minutes, same-caller field borrowing five minutes. AI observer: Gemini gemini-3.1-flash-lite primary, OpenAI gpt-5.4 fallback; observation only. Caller controls appear under matching Channels with verified account sightings by channel ID; win rate shows unavailable until evidence supports one. Honey Drip controls stay limited to their room IDs; newly observed accounts have no execution keys; historical identity attribution is candidate-only. Grabber tracks oldest-message progress, allows 30s for a stalled load, targets one year back, labels stalled history partial. Capture retains message_id, captured_at and revisions, dedupes by channel+ID, exports .json beside .txt. Daily Sniper Reports add an Open in Chrome link only on one exact captured source match; the localhost handoff accepts only configured Discord guild/channel/message IDs and opens Chrome Profile 2 (no broker or Discord API capability). Legacy ID-less rows stay unavailable — re-grab, never infer. Full-history completeness unverified.
- WHO READS (9/14): BOTH live ai_reader lanes — the one-message reader
  (AI READ) and the screenshot reader (IMG READ) — use the observer's
  providers, keys and cooldown map: OpenAI gpt-5.4, then Gemini, then
  Anthropic LAST and skipped while billing-blocked
  (execution.ai_reader.billing_blocked; any credit refusal parks it 6h). One
  order setting, `context_observer.reader_provider_order`. Same prompts, the
  24h image cache, the log names who read it. Changing WHO reads
  changes nothing about what a read may DO — still a proposal the parser and
  every guard judge, AI confidence authorizes nothing. On 9/14 alone the old
  hard-coded Anthropic call cost 242 "AI READ no call - ai: HTTP 400" and
  every 📸 read. ai_reader.judge() is the ONE copy of "validate() can never
  raise": a model field that is "" or a range ("1.26-1.30") is NO CALL — not
  a crash, not an order. 249 of the 12,162 retained OpenAI reads do that, and
  neither live lane had a guard on it.
- AI MEASUREMENT: full scan results and the Chrome-lane history are in
  HANDOFF-LOG.md (9/14). Contextual AI = Gemini primary, OpenAI fallback.
  START HERE opens enabled rooms Monday morning; roomSchedule closes them after hours
  and does not reopen them. Market-hours capture still to verify.

## Rules of the house (current, in force)
OPTIONALITY REVIEW 9/13 (full findings in HANDOFF-LOG.md): the channel is ON
by G's choice. v3.8.24 blocks an OPEN whose premium is really a dollar-labelled
STOCK quote, and fixes the sell-option negation guard. Multi-contract
extraction, export duplication and conditional exit wording remain unresolved.

PREMIUM REVIEW: Department AI distinguishes per-share quotes, cents, per-contract
cost, position totals and profit. No arbitrary premium range and no automatic
factor-of-100 correction. Equivalent amounts with verified units are not bugs;
missing units remain unresolved pending original-source evidence.

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
  on. Written the other way round first, it ate the Discord Settings tab G
  was working in, twice, mid-edit — and sparing the ACTIVE tab is no fix,
  since his tab stops being active the moment he clicks away. Widen this
  again and that is the failure you are re-inviting.
  WHO MAY OPEN A TAB (9/10, G: "get rid of auto opening tabs UNLESS it's
  the start sniper"). Exactly three things, and nothing else:
    1. START HERE.bat, through its one-shot open-rooms request
    2. the popup's Channels switch (his click)
    3. whopSelfHeal() — kept on his call so the Whop lane can revive its own
       4 tabs; its dedupe MUST read pendingUrl and query the whole origin, or
       a still-LOADING tab is missed and a heal pass turns 4 Whop tabs into 8
  roomSchedule() no longer opens anything — it used to open every `on` room
  at 9:15. It still CLOSES at 4:30, which is what stops the overnight pings.
  probeOne() opens a lapsed room off-hours, then closes that tab seconds
  later in a finally — a door-knock, not an open.
  NO ACCESS = OUT OF SERVICE (9/10, G: "do not open the tab if we don't have
  access"). revokeCheck() reads the tab titles it already has; a room whose
  title says "No Access" is now written to rooms.txt as `lapsed` through the
  bridge and its tab closed, not merely warned about (RWGates warned for
  three weeks while opening a blank tab every morning). `lapsed` not `off`:
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
  24h).
- ROOM HOURS: `on` rooms use tabs 9:15–16:30 ET on weekdays unless
  marked `always` (futures rooms). roomSchedule closes daytime tabs after
  hours; it does not reopen them at 9:15. START HERE once in the morning
  creates a one-shot, lane-aware open-rooms request, up to three tabs per
  pass with six-second spacing. Whop alone self-heals missing tabs. Closing
  a Discord tab by hand leaves it closed until the next START HERE request
  or a room-switch change. The last browser tab is protected from closure.
- CHANNELS / CONTROLS: Callers are shown within their verified room, with
  win rate unavailable unless backed by evidence. The separate Callers and
  Needs You tabs/buttons were removed at G's request. Existing Honey Drip
  caller switches retain their specific room keys; other observed accounts
  are identity rows only. Strategy Numbers and Room Rules remain in the UI.
  GET/POST /callers and /rooms still provide their existing bridge functions.
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
  · NO DATE = 0DTE (G, 9/10), and the LISTING is ASKED, never assumed
    (9/14). One batched snapshot call names today, the rest of this week and
    both Fridays; only contracts Webull really lists answer. Today wins if
    today is listed, else the nearest listed date. One call per dateless
    alert, cached per contract per day. DAILY_EXPIRY_ROOTS is now ONLY the
    fallback for when that lookup can't answer, and the log says it fell
    back. The old "a single stock has FRIDAY WEEKLIES ONLY" rule is DEAD: it
    bought TSLA 357.5C 9/18 at $7.40 on a $1.42 0DTE call, and the NVDA 210P
    9/16 two minutes later proves mega-caps list Mon/Wed/Fri. Clues still win
    first: "NEXT WEEK"/"NEXT FRI" -> next week's Friday, shouted MONTH -> that
    monthly.
  · CALLER-PRICE GATE (9/14, execution.price_sanity = 0.4x–2.5x): on an
    expiry the bridge INFERRED, if the resolved contract's ask falls outside
    that band around the price the caller posted, it is the wrong contract —
    take the listed expiry that IS in band, else REFUSE the entry and say so.
    No posted price = the gate is inert.
- SPREAD GUARD (entries only): refuse if spread > 20% of mid or > max($0.20,
  10% of mid). THIN guard: < 250 contracts last session = refused.
- STALE-ENTRY GATE: entries older than 3 min never fire. Negations ("NOT
  getting in", "too expensive") hard-veto; "out the gate" is hype.
- DEDUPE LADDER: extension in-flight lock → bridge echo-lock (same contract
  OPEN within 20 s refused) → per-trader "already in" claim → one
  average-down ADD if the same trader re-posts ≥1% under what was PAID.
  Position identity is caller+symbol+strike+side+expiry in both extension
  and Python; sibling strikes/expiries remain separate. Client order IDs are
  reserved durably in request_journal.sqlite before broker dispatch.
- AN EDIT IS A REPLACEMENT, NOT A SECOND TRADE (9/14). Discord keeps ONE
  message id when a caller EDITS a call, so an OPEN whose message id is
  already pending — or, with no id, the same trader's same ticker inside
  5 min on a different contract — CANCELS the earlier pullback hunt and its
  resting bid, logs one line ("EDITED  TSLA — PT | ei trades changed 357.5C
  → 357.5P; the earlier pullback is cancelled, only the new one stands"),
  then arms the new one. Two DIFFERENT message ids are two calls, never an
  edit (TWO CONTRACTS still holds); an identical repost stays with the dedupe
  ladder. Born from PT's TSLA $357.5c edited to 357.5p: both sides armed and
  the stale CALL arm bought 357.5C at 7.40 ($740). alert_revision.py.
- IF THE CORRECTED CONTRACT ALREADY FILLED (9/15, G: "if in profit keep the
  ratchet and set the stop to breakeven, if it's a losing trade, close it
  automatically"). Judged on the CURRENT BID vs the fill, read free from the
  quote bus cache as the edit lands. bid >= fill -> the stop goes to
  BREAKEVEN by the existing stop_to_breakeven path and the ratchet keeps
  running. bid < fill -> CLOSED down the existing exit path, the same
  _place_impl CLOSE the pullback stock exit uses, so claim() pulls the resting
  stop and waits for the broker first; there is no second sell routine.
  No bid, a non-option, or a stop that will not move = LOGGED ONLY,
  never a guess. Journal exit_by "edit-close"; a BE stop that later
  fires reads "edit-BE".
  THE ONE EXCEPTION TO ENTRIES-ONLY, and not a room exit: the caller changed
  the CONTRACT, so what we hold is OUR misread of their call, not a trade
  they asked us out of. Their trims, stop-moves and "all out" stay
  EXIT-IGNORED. A price-only edit never reaches it (same contract = no
  revision), nor does a different message id.
- RETRACTION ("not ready / scratch that / cancel / disregard / hold off /
  nevermind") pulls that trader's resting bids and armed pullback hunts.
- FUTURES: micros only (NQ→MNQ, ES→MES ...). Entry snaps to the 25-pt grid
  in his favour. Their stop/target wins; 25/50 fills the gaps. A MARKET entry
  (no price in the alert) gets that bracket off the FILL instead — positions.
  _arm_stop, but these are only recorded levels. Webull futures OPEN now refuses before broker lookup until an exact GTC STOP_LOSS is placed and verified after its fill, and stop/close reconciliation is tested. No futures quote-driven target/ratchet is operational.
- INDEX MIRROR (9/13) — **OFF and activation blocked** until a broker-confirmed futures protective exit path exists. The shadow records SPY/QQQ option entries, and `futures_mirror_daily.py` replays a hypothetical MES/MNQ market entry on ES/NQ 1-minute bars after the daily audit. Reports land in `daily-reports/FUTURES-MIRROR-<date>.md`; the cumulative history is `reference/FUTURES-MIRROR-REPLAY.csv`. The replay's 25/50 stop, target and ratchet are simulated, not current live futures exits. New-day coverage is only bridge shadow rows plus `master_alerts.csv`; posts missed upstream are absent. The popup switch stays disabled until live exits are verified.
- THE POCKET (hidden on purpose): a :43-:51 scalp-entry clock gate behind
  settings pocket_scalps_only, default OFF. Decided from HIS fill data
  (ledger minute-of-hour), not the QQQ study.
- Positions record the underlying at fill (und_at_fill); FILLED log lines,
  announcer posts and the journal all carry it.

EXITS — THE DOCTRINE: THEIR TRIGGER → OUR ENTRY → THE RATCHET'S EXIT
- ENTRIES ONLY (G, 9/3; verified live 9/8): the bot follows room ENTRIES
  (and adds) only. EVERY room-side exit — trim, stop-move, "all out",
  "stopped out", "closed everything" — is logged "EXIT-IGNORED … entries
  only" and NEVER traded. The ratchet's resting stop at Webull is the ONLY
  exit (plus the bridge's own pullback stock-stop / underlying hard-stop).
  ONE EXCEPTION, and it is not a room exit: an EDIT that changes the CONTRACT
  we already bought (see ENTRIES). A bot SELL that traces to a room's own exit
  call is still a BUG: check bridge.py do_POST's
  EXIT-IGNORED gate, background.js's TRIM/STOPMOVE/CLOSE gate, and that
  settings execution.exit_policy is absent (default entries_only; "full" is
  the one-line way back).
- THE RATCHET (5/3/5 since 9/10, flat): born stop −5%; +3% moves the stop to breakeven; each further +5% locks another +5%. `ratchet_tiers.py` is the one implementation and `live_spacing()` is the one configuration reader. Stops respect tick/spread floors and never loosen. Anti-clip is off. It won the 115-trade OPRA sweep, and three later replays failed to beat it outside their error bars — price tiers, a born-stop floor, G's stock ladder (numbers in HANDOFF-LOG.md). Re-run `ratchet_sweep_fine.py`, `reference/ratchet_replay_tape.py` and `reference/stock_stop_replay.py` as the sample grows; the BORN stop, not the rungs, is what ends these trades.
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
  never-filled sell releases the key and logs EXIT-RETRY. Late/partial fills
  found during cancel reduce the remaining quantity before any retry.
- A CLOSE for a contract the book does not hold is REFUSED, never sent
  (his 12-lot scalps live in the same account).
- 0DTE: ETF options trade to 16:15; auto-exercise at $0.01 ITM — flatten
  before the close.

RESTARTS / SAFETY
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
- RULE: weekly signal-room-chat logs (replaces daily) (G, 9/15).
  Naming: `signal-room-chat week-of-<Mon>-to-<Sun>-<year> (discord).txt` and
  `(whop).txt` — e.g. `signal-room-chat week-of-Sep-14-to-Sep-20-2026 (discord).txt`.
  Week = Mon–Sun. One-time merge: for each existing week, concatenate that
  week's daily `signal-room-chat <date> (...)` files in date order into the new
  weekly file, each day under a `===== Mon Sep 14 2026 =====` header. Delete
  the daily files after merge — REPLACE, not stack. Going forward: each day's
  capture appends under a new day-header inside the current week's file
  instead of creating a new daily file. New week → new file, auto-started.
  (Merge done 9/15: the seven lane-tagged dailies are zipped in `archive/`;
  `ds_logs.py` owns naming, day blocks and de-dupe — readers ask it which days
  a file covers. A re-export replaces that day's block. Never hand-edit one.)
- DAILY SNIPER REPORT: bridge.py runs `daily_audit.py` once per weekday at
  16:40 ET, after the 16:30 export/tab sweep. Order: `broker_sync.py` pulls
  the Webull export first; the day's exact Discord and Whop inputs replay with
  each room's production grammar; `parser_gate.js` compares parser.js,
  rooms.txt and optionable.txt over every retained live message (AUTO PUSH
  runs that gate before any such rule ships and blocks invented symbols or
  expiry shifts); every JS/Python test runs; `daily-audits/AUDIT-<date>.txt`
  + `latest.json` are written; unresolved items are queued. Reports written
  to `daily-reports/`: the Daily Sniper Report (coverage, decisions, skips,
  fills, P&L, postmortems), `RATCHET-COMPARE-<date>.md` (live 5/3/5 vs fixed
  -5% born stop over exact-contract quote paths, coverage stated, never
  extrapolated), `CALLER-OUTCOMES-<date>.md/.csv` (caller entry, every trim
  and full exit with price/percent/size; caller P&L only when entry and exit
  pair with contemporaneous quotes; partials never become full results; a
  posted price within 2% of that minute's `und` is a STOCK quote -> entry
  "unavailable (stock price posted)", dollars out of every total),
  `CALLER-VS-RATCHET-<date>.md` (5/3/5 from caller entry over `tape.py`).
  LAST step is `daily_brief.py`: the one-screen brief (day · bot trades ·
  callers right/wrong · what broke · pending) -> `BRIEF-<date>.md`, POSTED TO
  SNIPER HQ through the Fill Announcer's options webhook. That post is how G
  gets the day; a failed brief never fails the audit. Rules: broker-confirmed
  actuals override any simulation; RAW capture is always retained and LIVE
  PARSER rows overlay it; relay duplicates count once; expired pullback waits
  are skips, not orders; the 15-minute Codex guard was deleted at G's request
  — do not recreate it. Findings become tested fixtures.
- GIT: settings.json holds every key and is never committed. AUTO PUSH uses
  a live-owner PID lock, commits every 45 s and retries pushes; it never deletes
  Git locks or rebases. Runtime files remain local. After suspicious loss check
  `git reflog` for a "reset:" before rebuilding.
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
  is; DATA-MAP.md says what is in it.
- RUN build_ledger.py IN EASTERN. Its clocks come from the machine's local
  timezone, so a rebuild from a UTC shell rewrites `opened` four hours forward
  while `closed`, parsed from a stored string, moves the other way — one row,
  two clocks (9/15, caught and reverted from backups/). Off his PC:
  `TZ=America/New_York python3 build_ledger.py`.
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
- TAB HEALTH: content/Whop reinjection clears the old observer and heartbeat; background reinjects before any reload and logs every reload. Room opening is paced, memory shedding touches at most one inactive room per cycle, and active/voice tabs are protected. Extension maintenance jobs run in one ordered sweep; normal message delivery stays event-driven. Chrome uses Profile 2 for Discord and Profile 6 for Whop; `whop-profile.txt` pins the folder.
- WHOP: four `whop.com/<business>/exp_<id>/app/` tabs are read only from Profile 6. The extension is installed there. `whopSelfHeal()` and `_whop_loop.bat` restore missing Whop tabs/profile with bounded strikes; Discord tabs still reopen only from START HERE’s one-shot token. Felony’s Zoom uses the web client in that profile; one manual Sniper-icon click grants tab audio capture.
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
  working 100% first"). Its board is computed FROM THE LEDGER (9/9).
- Its order hunt is paced (0.20 s, once per account) — the 9/2 429 storm
  (77k TOO_MANY_REQUESTS on the shared key) must never come back.

## DATA — one central file per family (9/9). THE APP READS ONLY THESE.
- BROKER RECORD → master_broker.csv (one row per Webull order leg, every
  day). `broker_sync.py` — FIRST step of the 16:40 audit, one read-only client,
  no loop — pulls the order history (paged on `last_client_order_id` until a
  short page) into ONE fixed file, Webull_Orders_auto.csv, OVERWRITING it every
  run (G, 9/10: "have one that overwrites" — no deletes, ever), and records one
  balance row per day in `balance_daily.csv` (date, nlv, day_pl, bp, read_at) —
  the brief's only balance source. NOTHING PULLED THIS UNTIL 9/15 (a session
  did it by hand; last pull 9/11), so 9/12-9/14 all read "broker export
  missing" and 9/14's 60 legs / -$321 were invisible;
  build_ledger's absorb_exports() (runs inside every ledger refresh) folds
  it into master_broker.csv and leaves it in place. Never write dated
  Webull_Orders_<date> files — the folder holds the master plus that one
  scratch file (G, 9/9: never dated piles).
  Merge is REPLACE-DON'T-STACK per order (placed-time+contract+side+size+
  limit): a later pull replaces a WORKING snapshot, never duplicates it.
  PRICE-BLIND TWINS (9/11): a stop leg has no limit, so one pull may write
  its stop price in "Price" and another nothing; the merge treats a blank-
  price copy of the same placed-time/contract/side/size/snapshot as the SAME
  order (keeps the priced copy) and collapses any such twins already in the
  master on load. 9/10 had 7 (3 FILLED sells the FIFO could mis-pair).
  Webull_Orders_auto.csv "Price" = limit_price, else stop_price.
  Backups: backups/<file>.bak-<stamp> (last 5) — for master_broker,
  master_ledger and master_alerts; NO .bak files in the root anymore.
- BROKER TRUTH: `master_broker.csv` is paged across the full Webull order history; 100-row pages must continue with `last_client_order_id` until a short page. `build_ledger.py` computes P&L from broker fills, collapses carryovers by caller+contract+entry, and matches either end date for overnight trades. Do not quote P&L from book-priced rows when a broker row exists.
- BOT ATTRIBUTION: a caller name is candidate evidence until the entry is linked to a source alert and the trade to broker fills. `manual` in the day row denotes a manual exit; it does not disqualify a bot-origin entry. Adopted/export-only rows need separate entry provenance; caller `?` is unknown. Keep the older 107-trade contract-matched study as a dated sample, not a current all-trade statistic. `option_tape_pull.py` records durable quote coverage before skipping downloads.
- NO PAPER, ANYWHERE (9/9, G: "delete all paper trades data from the app, I
  don't want any more confusions"). build_ledger keeps account="paper" rows
  OUT of master_ledger.csv, so the board, journal, scoreboard, announcer and
  every backtest are real money only. account="unknown" is NOT paper —
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
  A closed position's qty can be zero remaining even when its entry legs
  show the original size. Match that original size only to one exact OCC,
  price and near-time (five-minute) broker trip; never relax a nonzero size
  mismatch. Broker-confirmed exit and P/L replace the book's assertion while
  store_pl retains it. New day records include entry_qty, the first broker
  entry_order_id and client coid; the rebuilt ledger carries these fields.
  A manual exit is exit provenance, not proof of manual entry. Research SQL
  joins alert and trade only on an explicit shared coid or legacy event key.
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
- PRICE TAPES → tape.py is the ONE registry. Seven sources:
  webull, tasty_greeks, tasty_quote, databento, databento_clean, missed,
  and alert. `alert` is `alert_tape.csv`, the slow all-alert lane used for
  refused/missed-call outcomes and caller-exit comparisons; it was wired
  into the registry 9/11 after its writer existed but the common reader did
  not know about it.
  NOT bars/ — that and bars_capture.py were archived 9/9 and tape.py never
  registered them. tape.path(
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
  <date>_<occ>-2.md, named by the trade's rank among that day's graded trades
  on the OCC; the csv row is keyed date+occ+fill+exit. G 9/9: "analyze every
  single trade after exiting … be attentive to these"). One verdict per exited bot trade — NOISE CLIP /
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
  No 800×600 cap; every tab is a card on a 3-column grid, same code and
  same 1-2 s bridge polling. One file, two sizes — never a second
  dashboard. IS_PAGE in popup.js
  guards the popup-only bits (window.close after a room jump).
- POPUP (v3.5.77, 9/9 evening): the rooms list paints FIRST in render()
  and any exception in the rest of the popup is written INTO the Channels
  pane ("popup error (…): …") — never a blank pane again. esc() is
  module-level, one copy. If G reports a broken popup again, the red
  line under the rooms is the diagnosis; ask for it. Claude-in-Chrome CANNOT
  read the popup (another extension's page; screenshots/JS/console all
  refused). Its id is the one in THE PAGE url above — Chrome hashes the
  folder path as UTF-16LE, so both profiles get the same one.
- Multi-account: extras mirror LIVE entries 1:1 with own books/stops.
- START HERE.bat saves+pushes before its reset; RESTART BRIDGE.bat
  pre-flights and warns. Logs: trades.log (the story), bridge.log (raw,
  20 MB, no rotation yet), webull_api.log, announcer.log, deadman.log.

## SECOND MACHINE (planned 9/9 — G: "another account on a different computer
## for other subs"). Built default-off; nothing changes until PC2 exists.
- WHY: Discord's identify budget and Chrome's RAM are per account / per
  machine. ONE bridge, ONE book, ONE rate budget — PC2 runs only Chrome + the
  extension and sends to THIS PC's bridge over the LAN. Never a second bridge
  on the same Webull account (two books break every dedupe and coexistence
  rule).
- SECURITY IS ALREADY IN THE CODE: execution.bridge_listen + bridge_token; the
  bridge refuses to bind off loopback without a token and off-loopback callers
  must send X-Sniper-Token; CORS is limited to chrome-extension:// origins. The
  extension reads an optional gitignored extension/bridge.txt.
- BEFORE PC2 GOES LIVE — LANE TAGS: both PCs read the same rooms.txt, so today
  they would open and trade the same rooms. A 5th `|pc2` field per line plus a
  lane name per machine. Setup steps: HANDOFF-LOG.md under 2026-09-15.

## Pending external setup and decisions
1. In Claude: use project/PROJECT-INSTRUCTIONS.md as the Project
   instructions and remove the old uploaded handoffs (local cleanup does not
   remove what was already uploaded).
2. Market Sniper: apply HANDOFF-RATCHET-2026-09-09.md (options 5→2 rung,
   futures decouple) — G's call whether Claude does it or he does.
3. NinjaTrader ATM template "SNIPER": stop 100 ticks / target 200 (=25/50
   MNQ pts), qty 1 — create in NT8, type SNIPER in the popup.
4. Close any old parked Whop tabs. (Chrome hardware acceleration: DONE 9/10
   — `--disable-gpu` rides every flagged Chrome launch. CORRECTNESS, not
   speed: a GPU black tab reads NOTHING while looking open. Flags bind only
   on a cold start, so a Chrome already running ignores them.)
5. Announcer: paused since 9/2 — the Needs-you tab has the on/off button.
6. CHROME BEFORE 9:15: rooms open at 9:15 only if Chrome + the extension
   are already up. Run START
   HERE, or schedule it, by 9:00 on trading days.

## Watch items (open)
- PULLBACK STOCK TARGET vs THE RATCHET (9/10, G's call): a pullback entry
  manages "off the stock" and CLOSES at a fixed stock target ($1 past the
  round number: META 645P out at 648.62). On 9/10 that took +$80 at 6.23
  while the ratchet's stop sat at 5.65 (+4% locked) and the contract ran
  to 8.50 inside 10 min (+$307). Doctrine says the ratchet is the ONLY
  exit; the stock TARGET is a second, earlier one. (a) delete the target,
  keep the pullback stock-STOP; (b) keep it. Nothing changes until G says.
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

## Subscriptions
≈ $1,140/mo rooms + ~$52 infra + ~$30 exchange fees ≈ $1,220/mo before AI
usage. Break-even ≈ $60+/trading day. Next audit: cost vs ledger P&L per room.

## Where everything lives
HANDOFF-LOG.md (all history) · INDEX.md (folder map) · ARCHITECTURE.md ·
MARKET-HOURS.md · reference/ (broker reference, anti-clip study, ratchet
notes) · extension/rooms.txt · settings.json (keys, gitignored) ·
master_ledger.csv / master_alerts.csv (truth) · days/ (per-day state) ·
daily-reports/ (daily performance reports) · project/ (Claude reference setup).
