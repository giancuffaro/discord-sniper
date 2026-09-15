# ENTRIES — mechanics

The mechanics behind the rules in HANDOFF.md, moved here 9/15 so HANDOFF stays a
rules core (under 30 KB). The rule is in HANDOFF; the HOW, the numbers and the
history-with-numbers are here. REPLACE, DON'T STACK applies: edit in place.

Owner code: bridge.py (do_POST, _verify_listed), webull_options.py (expiry_to_date,
tick_round, stop_below), pullback.py, alert_revision.py, extension/parser.js.

## Reviews in force

OPTIONALITY REVIEW 9/13 (full findings in HANDOFF-LOG.md): the channel is ON
by G's choice. v3.8.24 blocks an OPEN whose premium is really a dollar-labelled
STOCK quote, and fixes the sell-option negation guard. Multi-contract
extraction, export duplication and conditional exit wording remain unresolved.

PREMIUM REVIEW: Department AI distinguishes per-share quotes, cents, per-contract
cost, position totals and profit. No arbitrary premium range and no automatic
factor-of-100 correction. Equivalent amounts with verified units are not bugs;
missing units remain unresolved pending original-source evidence.

## Round-number pullback — the $1 level

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

## Strikes, ADDs, SPX

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

## Word order and two-contract messages

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

## Expiry — one place

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
  · THE CONTRACT MUST EXIST (9/15, bridge._verify_listed,
    execution.verify_listed): EVERY entry asks the broker whether that exact
    contract is listed — one snapshot call for the one date, cached per
    contract per day; a second call only if the first is empty. Unlisted but
    siblings are -> REFUSE + BAD-CONTRACT line naming the room and the raw
    alert. NOTHING listed anywhere -> that is the feed, not the contract:
    goes THROUGH with a LISTING line. Fails open on no connection, an
    unreadable date, any exception — a guard, never a gate. Asked, not
    tabled: Mon/Wed expiries exist only on the nine Qualifying Securities
    (AAPL AMZN AVGO GOOGL META MSFT NVDA TSLA + IBIT) and that list is re-cut
    QUARTERLY on a $700B test. A GUESSED expiry also gets the price gate
    above; a date the caller TYPED is checked for existence only.

## Guards and dedupe

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

## Edits, corrected contracts, retractions

- AN EDIT IS A REPLACEMENT, NOT A SECOND TRADE (9/14). Discord keeps ONE
  message id when a caller EDITS a call, so an OPEN whose message id is
  already pending — or, with no id, the same trader's same ticker inside
  5 min on a different contract that reads as a fix — CANCELS the earlier
  pullback hunt and its
  resting bid, logs one line ("EDITED  TSLA — PT | ei trades changed 357.5C
  → 357.5P; the earlier pullback is cancelled, only the new one stands"),
  then arms the new one. Two DIFFERENT message ids are two calls, never an
  edit (TWO CONTRACTS still holds); an identical repost stays with the dedupe
  ladder. Born from PT's TSLA $357.5c edited to 357.5p: both sides armed and
  the stale CALL arm bought 357.5C at 7.40 ($740). alert_revision.py.
  NO message id (9/15, verbatim from HANDOFF): NO message id (voice/vision/legacy): same trader, same
  ticker, inside 5 min AND the text reads as a fix — a correction word (edit,
  meant, typo, "*", "not calls/puts") or ≥0.9 similar with the contract
  stripped. Otherwise it is a SIBLING trade and both arms stand (alert_revision.py).
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

## Futures entries, the index mirror, the pocket

- FUTURES: micros only (NQ→MNQ, ES→MES ...). Entry snaps to the 25-pt grid
  in his favour. Their stop/target wins; 25/50 fills the gaps. A MARKET entry
  (no price in the alert) gets that bracket off the FILL instead — positions.
  _arm_stop, but these are only recorded levels. Webull futures OPEN now refuses before broker lookup until an exact GTC STOP_LOSS is placed and verified after its fill, and stop/close reconciliation is tested. No futures quote-driven target/ratchet is operational.
- INDEX MIRROR (9/13) — **OFF, activation blocked** until a broker-confirmed futures protective exit exists. The shadow records SPY/QQQ option entries; `futures_mirror_daily.py` replays a hypothetical MES/MNQ market entry on ES/NQ 1-minute bars after the audit -> `daily-reports/FUTURES-MIRROR-<date>.md`, cumulative `reference/FUTURES-MIRROR-REPLAY.csv`. Its 25/50 stop/target/ratchet are simulated. Coverage = bridge shadow rows + `master_alerts.csv` only. Popup switch stays disabled until live exits are verified.
- THE POCKET (hidden on purpose): a :43-:51 scalp-entry clock gate behind
  settings pocket_scalps_only, default OFF. Decided from HIS fill data
  (ledger minute-of-hour), not the QQQ study.
- Positions record the underlying at fill (und_at_fill); FILLED lines,
  announcer posts and the journal carry it.

## Open watch item — pullback stock target vs the ratchet

- PULLBACK STOCK TARGET vs THE RATCHET (9/10, G's call): a pullback entry
  manages "off the stock" and CLOSES at a fixed stock target ($1 past the
  round number: META 645P out at 648.62). On 9/10 that took +$80 at 6.23
  while the ratchet's stop sat at 5.65 (+4% locked) and the contract ran
  to 8.50 inside 10 min (+$307). Doctrine says the ratchet is the ONLY
  exit; the stock TARGET is a second, earlier one. (a) delete the target,
  keep the pullback stock-STOP; (b) keep it. Nothing changes until G says.
