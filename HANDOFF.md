# DISCORD SNIPER — THE HANDOFF
Read this first for current operating state. Session history and past findings
live in HANDOFF-LOG.md; they are evidence, not current instructions.
Last updated: 2026-09-13 — v3.8.29, Gemini-first contextual reader; index mirror stays OFF and activation is blocked until futures exits work.

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
- Caller research catalog: `python caller_ledger.py` refreshes ignored `local-reader-measure/caller-identity/callers.sqlite3`. `/callers` includes read-only SQL account sightings; popup v3.8.26 maps those by channel ID instead of legacy room labels. Historical win rates are unavailable until account/trade attribution is established. Existing confirmed Honey Drip controls remain; newly observed accounts do not create execution keys. No live dedup or eligibility changes. See `reference/CALLER-LEDGER.md`; historical identities and performance joins remain pending.
- G (giancuffaro230@gmail.com) — maintains this code himself (9/13), trades options + futures live,
  real money. Wants it CONDENSED. "Fix everything is default always" — bugs
  get fixed without asking, same day. "Fix errors every day after journaling."
- The machine: Chrome MV3 extension source v3.8.27 reads Discord in Profile 2 and Whop in Profile 6 (display name “Whop Profile”). `extension/rooms.txt` is the one room list. Typed, voice, and image alerts go to the Python bridge on 127.0.0.1:8787. Webull options use caller price or better, optional round-number pullback, a bracket stop born with the entry, and the flat 5/3/5 ratchet. Fill Announcer may be paused. The weekday autopilot watches health, syncs broker truth, journals after the close, and never places or cancels an order. Market Sniper on port 8000 shares the Webull account and API budget; positions this bot did not originate remain visible but untouched.
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
- ANTHROPIC STATUS: saved-key presence is separate from probe result. Billing, rate limits, authentication, access and connection failures have distinct labels; do not interpret every failed check as a missing key.
- KEY CHECK (9/13): OpenAI, Gemini and Perplexity probes passed; Anthropic billing blocked, DeepSeek removed. See sanitized local-reader-measure/provider-key-check.json.
- PROVIDER KEYS: Keys pane saves OpenAI, Gemini and Perplexity credentials under settings.json ai_provider_keys. Saved provider fields are hidden with an explicit Replace key option. OpenAI/Gemini connected to context observer; Perplexity stored inactive. DeepSeek credential and fields removed by user request; Anthropic retained billing-blocked. Status returns presence flags only; inputs are not included in browser draft persistence.
- DEPARTMENTS: enabled. Existing bridge audit loop calls health_tick every five minutes; extension maintenance publishes Discord/Whop lane heartbeat and reader issues. GPT-5.4 mini analyzes changed issues (12/day), Astra escalates multi-issue incidents (2/day), reviews selected reader disagreements (20/day), and analyzes existing daily reports after the 16:40 audit (1/day). Results are advisory files in department-reports, never executed as code/orders. Astra and Mini live probes passed; first Astra report for Friday 9/11 and Mini preflight generated. Context snapshots persist at most once/minute (up to one minute may be lost on abrupt exit).
- READER/UI: observer retains 50 prior messages within 72 hours; fresh-post admission remains 15 minutes and same-caller field borrowing remains five minutes. AI observer enabled: Gemini gemini-3.1-flash-lite primary, OpenAI gpt-5.4 fallback; same prompt, bounded requests and cooldowns; observation only. Needs You pane/buttons/polling removed. Caller controls appear under matching Channels; v3.8.27 shows verified account sightings by channel ID and an unavailable win rate until evidence supports one. Existing Honey Drip controls remain limited to their specific room IDs; newly observed accounts have no execution keys. Historical identity attribution is candidate-only unless the original source supports an account link. Grabber v3.8.22 re-resolves replaced message panes each step, tracks oldest-message progress instead of page height, allows 30 seconds for stalled loads, and clears failed runs; stale-ID recovery and queue advancement fixed; v3.8.23 restores the original one-year target (exceeds requested four months); the Optionality tab already had May 6 loaded and was correctly stopping at the shorter cutoff. Retains tabs and labels stalled history partial. v3.8.25 capture retains message_id, captured_at and observed revisions, dedupes by channel+ID, and exports structured .json beside readable .txt. Legacy ID-less rows remain explicit legacy-unknown; re-grab is needed to obtain IDs, not infer them. Browser full-history completeness remains unverified.
- AI MEASUREMENT: OpenAI retained scan COMPLETE: 12,162 successful; $28.37
  estimated API cost of $45 authorized. Results: local-reader-measure/
  openai-trial-2026-09-12/final-release-3.8.14/. No new paid scan needed.
  Contextual AI now uses Gemini with OpenAI fallback; legacy Anthropic one-message reader remains billing-blocked. Chrome
  remote history remains incomplete. Both Chrome lanes reported v3.8.27 on 9/13 after the Whop watchdog repair. G closed Platinum futures-alerts, NGD ngd-trades and Chika Alerts, then authorized a one-shot reopen; all three tabs were verified open. START HERE once Monday morning still opens enabled rooms; roomSchedule closes them after hours and does not reopen them automatically. Market-hours capture remains to verify.

## Rules of the house (current, in force)
OPTIONALITY REVIEW 9/13: Channel is ON by user choice. v3.8.24 blocks OPEN when its chosen premium equals an explicitly dollar-ticker-labelled stock quote, and fixes the sell-option guard for the observed "this is option selling not traditional contract buying" negation. Three bad OPEN classifications removed in the distinct grabbed-text screen; 11,385-message gate unchanged (852 entries, 3,048 actions). Multi-contract extraction, export duplication and conditional exit wording remain unresolved; no claim that all findings are fixed.

PREMIUM REVIEW: Department AI distinguishes per-share quotes, cents, per-contract
cost, position totals and profit. No arbitrary premium range and no automatic
factor-of-100 correction. Equivalent amounts with verified units are not bugs;
missing units remain unresolved pending original-source evidence. User confirmed
Discord Chrome Profile 2 and Whop Chrome Profile 6 on 2026-09-13.

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
  Position identity is caller+symbol+strike+side+expiry in both extension
  and Python; sibling strikes/expiries remain separate. Client order IDs are
  reserved durably in request_journal.sqlite before broker dispatch.
- RETRACTION ("not ready / scratch that / cancel / disregard / hold off /
  nevermind") pulls that trader's resting bids and armed pullback hunts.
- FUTURES: micros only (NQ→MNQ, ES→MES ...). Entry snaps to the 25-pt grid
  in his favour. Their stop/target wins; 25/50 fills the gaps. A MARKET entry
  (no price in the alert) gets that bracket off the FILL instead — positions.
  _arm_stop, but these are recorded levels, not broker-enforced exits. No automatic futures stop/target or quote-driven ratchet is operational yet.
- INDEX MIRROR (9/13) — **OFF and activation blocked** until a broker-confirmed futures protective exit path exists. The shadow records SPY/QQQ option entries, and `futures_mirror_daily.py` replays a hypothetical MES/MNQ market entry on ES/NQ 1-minute bars after the daily audit. Reports land in `daily-reports/FUTURES-MIRROR-<date>.md`; the cumulative history is `reference/FUTURES-MIRROR-REPLAY.csv`. The original 149-alert 8/3–9/11 replay lost $721 gross (ZT mashup accounted for $703). The replay's 25/50 stop, target and ratchet are simulated, not current live futures exits. New-day coverage is only bridge shadow rows plus `master_alerts.csv`; posts missed upstream are absent. The popup switch stays disabled until live exits are built and verified.
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
- THE RATCHET (5/3/5 since 9/10, flat): born stop −5%; +3% moves the stop to breakeven; each further +5% locks another +5%. `ratchet_tiers.py` is the one implementation and `live_spacing()` is the one configuration reader. Stops respect tick/spread floors and never loosen. Anti-clip is off. The setting won the 115-trade OPRA replay ($504, rank 1/294; paired improvement +$3.01/trade, 95% band +$0.72..+$4.91). Re-run `ratchet_sweep_fine.py` as the sample grows.
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
- DAILY AUDIT / REPORT: bridge.py runs `daily_audit.py` once per weekday at
  16:40 ET, after the 16:30 export/tab sweep. It replays that day's exact
  Discord and Whop inputs with each room's production grammar. `parser_gate.js`
  also compares parser.js, rooms.txt and optionable.txt over every retained
  live message; AUTO PUSH runs that gate before any such rule ships and blocks
  invented symbols or expiry shifts. The audit runs every JS/Python test, writes `daily-audits/AUDIT-<date>.txt`
  plus `latest.json`, queues unresolved items, and writes the daily report:
  room coverage, decisions, skips, recovered gaps, fills, P&L and postmortems.
  Relay duplicates stay raw but count once. The 15-minute Codex guard was
  deleted at G's request; do not recreate it. Findings become tested fixtures. Caller-vs-system P&L is shown
  only when caller entry and exit can be paired with contemporaneous option
  quotes; missing exits remain unavailable rather than estimated. RAW capture
  is always retained and session-local LIVE PARSER rows overlay it; a browser
  restart can no longer truncate the day to its final session. Accepted
  pullback waits that expire are counted as skips, not broker orders. The same
  close run writes `daily-reports/RATCHET-COMPARE-<date>.md`, replaying every
  exact-contract quote path under the live 5/3/5 ratchet and a fixed -5% born
  stop. It reports coverage and never extrapolates uncovered alerts. Alert
  tape restores today's contracts from `alert_meta.csv` after bridge/code
  restarts, resolves shorthand expiries, and records distinct re-entries.
  `CALLER-OUTCOMES-<date>.md/.csv` separately preserves caller entry, every
  supported trim/full exit, exact or implied price and calculated percent;
  partial trims never become full-trade results and absent prices stay absent.
  `CALLER-VS-RATCHET-<date>.md` replays 5/3/5 from caller entry over `tape.py` and lists gaps/futures.
  Broker-confirmed actuals always override a quote-path simulation.
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
  PRICE-BLIND TWINS (9/11): a stop leg has no limit, so one pull may write
  its stop price in "Price" and another nothing; the merge treats a blank-
  price copy of the same placed-time/contract/side/size/snapshot as the SAME
  order (keeps the priced copy) and collapses any such twins already in the
  master on load. 9/10 had 7 (3 FILLED sells the FIFO could mis-pair).
  Webull_Orders_auto.csv "Price" = limit_price, else stop_price.
  Backups: backups/<file>.bak-<stamp> (last 5) — for master_broker,
  master_ledger and master_alerts; NO .bak files in the root anymore.
- BROKER TRUTH: `master_broker.csv` is paged across the full Webull order history; 100-row pages must continue with `last_client_order_id` until a short page. `build_ledger.py` computes P&L from broker fills, collapses carryovers by caller+contract+entry, and matches either end date for overnight trades. Do not quote P&L from book-priced rows when a broker row exists. Current historical split recorded 9/10: 705 completed round trips, −$4,228 total; G’s hand trading −$4,332; bot +$301 by the broad broker attribution.
- BOT ATTRIBUTION: a caller name is candidate evidence until the entry is linked to a source alert and the trade to broker fills. `manual` in the day row denotes a manual exit; it does not disqualify a bot-origin entry. Adopted/export-only rows need separate entry provenance; caller `?` is unknown. Keep the older 107-trade contract-matched study as a dated sample, not a current all-trade statistic. `option_tape_pull.py` records durable quote coverage before skipping downloads.
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
  X-Sniper-Token (constant-time compare). Loopback accepts the Chrome
  extension or local no-Origin utilities; ordinary web-page Origins are
  refused and CORS is limited to chrome-extension:// origins.
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

## Pending external setup and decisions
1. If continuing in Claude: replace its Project instructions with
   project/PROJECT-INSTRUCTIONS.md and remove its old uploaded handoffs.
   Local cleanup does not remove files already uploaded to Claude.
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
6. CHROME BEFORE 9:15 (9/11): START HERE ran at 09:49, so no room was read
   9:15–9:49 — QCOM 185C, NVDA 220C, MNQ short and DELL 560C were never seen.
   Rooms open themselves at 9:15 only if Chrome + the extension are already
   up; run START HERE (or schedule it) by 9:00 on trading days.
7. Chrome extension for Claude was NOT connected at the 16:35 close-out, so
   the /stream check (last_sweep_ms, budget_left) was skipped; re-sign-in
   the "Claude in Chrome" side panel if you want the autopilot to read it.
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
daily-reports/ (daily performance reports) · project/ (Claude reference setup).
