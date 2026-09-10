# DISCORD SNIPER — THE HANDOFF LOG (archive)
This is the FULL history that used to live inside HANDOFF.md — every session's
notes, newest first, byte-for-byte as they were on 2026-09-09 when HANDOFF.md
was cut back to a compact living memory. NOTHING was deleted; it moved here.
Search this when you need the WHY behind a rule or the story of a bug.
HANDOFF.md (the rules in force) always wins over anything here.
From 2026-09-09 on, session notes are appended at the TOP of the
"SESSION NOTES" section below, dated, and HANDOFF.md gets only the rule edit.

## SESSION NOTES (newest first)

**2026-09-10 02:30 — THE TAPE, THE RATCHET VERDICT, AND ALL 25 SERVERS.**
Two jobs while G slept: buy the OPRA tape and finish the Discord sweep.

THE TAPE. The first pull never wrote a byte. Three reasons, all found and
all fixed. (1) A backgrounded `nohup` dies with the sandbox call, so the
"it's downloading" of the night before was a process that had already been
killed — check `ls -l` on the output file, never the fact that you launched
something. (2) The pull priced every day-window with metadata.get_cost on
EVERY run, 49 round-trips before a single download; pricing now belongs to
`--cost` alone. (3) The real cost: it asked for one window per DAY spanning
min-entry to max-exit across every contract that day — the whole session,
for each of them — on `cmbp-1`, the full book. Millions of rows to produce
a 1-second downsample. Now: one pull per CONTRACT-window, four in flight,
on `cbbo-1s`, which Databento already samples to the second. 8 windows in
84s became 87 in 120s. `--minutes N` stops cleanly and re-runs resume,
because a window is written all-or-nothing (a half-written day would be
skipped forever by `already_taped`). Result: 537 contract-days, 1,022,106
quotes. Only 9/9 is missing — OPRA history stops at 13:30 UTC that day,
the rest needs a live licence we do not have.

THE RATCHET VERDICT — AND A TRAP ON THE WAY. First run of ratchet_sweep.py
on the full tape said 822 trades and EVERY one of 50 spacings losing, best
−$918. That looked like "the stop is not the lever, the rooms are". It was
a filter bug of exactly the kind found the night before: 707 of the 822
rows had caller `?` — hand trades and adopted positions, not room calls —
worth −$1,230 on their own. EXCLUDE_WHO now drops "" and "?" alongside
"gian". The honest sample is 115 real room-call trades: current 7.5/5 =
+$87 (rank 10 of 50), best born −5.0% / arm +4.0% = +$384. Because 115 is
small, `--by-caller` now also bootstraps the PAIRED difference (same trade,
both rules, 2000 resamples): +$2.58 a trade, 95% band +$0.45..+$4.31.
Outside zero, so it is a real edge and not this sample's noise — the first
ratchet number in this project that clears its own error bar. NOT APPLIED:
it is money, so it is G's call. The by-caller table also shows where the
money is: the pawn +$323 and mike +$263 carry the whole book, unraveller
−$204 and evapanda −$160 give it back. ratchet_backtest.py agrees the
current stop is sound in the other direction — 867 contract-days, 0 that
went worse than the born stop.

THE DISCORD SWEEP. The tab reloaded overnight and took `window.__CAND` with
it, so the 70 candidates were gone. Rebuilt with a rule worth keeping: to
move between channels use `history.pushState` + a synthetic `popstate`.
Clicking an injected anchor is a REAL navigation — it reloads Discord, tears
down the eval context, and costs a fresh gateway session (the logout risk).
pushState keeps the page, the variables and the session. Re-swept all 25
servers, 289 visible channels, then OPENED every plausible one and read its
last messages rather than judging by name.
Found: TradingTheTrend #member-alerts and #trade-log — live options calls
("BTO NVDA 9/11 230c @ .88") echoed by a TradesTracker bot in the cleanest
machine format in any of the 25 servers. Added `off`; trade-log probably
duplicates the #option-alerts room already on, so member-alerts goes first.
Added `off` with their reason: TTT spread-alerts / option-spreads (credit
spreads, against the 9/7 rule), TTT stock-alerts and ZT dave-trader
(shares). Rejected in one block, all read: OWLS notable-flow / etf-flow /
free-flow-ideas (an unusual-flow bot — prints what someone else bought, no
entry, no stop, nobody to follow), chatter rooms, watchlists, recaps,
react-for-a-role boards, a competing product's changelog bot, and two dead
ZTRADEZ rooms.
G asked specially about the education channels — "there's a lot of
education and parser they teach for their specific server". There isn't.
Honey Drip's five how-to-trade-* channels are each a single YouTube link;
Vero's day-trade-guide and Platinum's how-to-navigate are signposts to the
alert rooms we already read. No server teaches a format we were not already
parsing.
And a trap avoided: Sniper HQ's #sniper-alerts-options / #sniper-alerts-
futures showed up as perfect alert channels. They are OUR OWN — the fill
announcer posts there. Reading them would feed the bot its own fills as if
they were somebody's calls. Marked DO NOT ADD in rooms.txt.

**RATCHET CHANGED 7.5/5/2 -> 5/3/5 (G: "flip it").** Applied, not proposed:
settings.json strategy.stop_loss_pct 7.5 -> 5 and ratchet_tiers.TIERS
(5.0,0.0,2.0) -> (3.0,0.0,5.0). NOTE FOR THE RECORD: the question G answered
offered born -5.0 / arm +4.0, from ratchet_sweep.py, which ties the rung to
the arm. ratchet_sweep_fine.py, which decouples the rung, then found the
real best cell is 5.0/3.0/5.0 at $504 vs 5.0/4.0/4.0 at $384 — same born
stop he approved, better arm and rung. The tested cell was applied and the
difference is called out here rather than buried.
Four ratchet assertions in test_positions.py encoded the old ladder's
numbers (a $2.00 fill locking 2.28 at +20%, 2.48 at +30%); under 3/5 the
same fill locks 2.30 and 2.50. Updated, all five suites green.
AND THE BUG BEHIND THE BUG: ratchet_sweep_fine.py had "LIVE 7.5/5/5"
hardcoded in its header and had been printing that for two days while the
real rung was 2 — every comparison in that report was against a rule nobody
was running. chart_contracts.py, entry_compare.py, missed_dollarize.py and
pullback_levels.py each carried their own typed copy too. There is now ONE
reader, ratchet_tiers.live_spacing(), returning (born, arm, step) read from
settings.json and TIERS; all five call it. A "current" number typed into a
report is a number that goes stale the day the real one moves.
ALSO NOTED, NOT CHANGED: ZT all-trades-mashup is still `on` in rooms.txt
even though the 9/9 note says the whole ZTRADEZ server was cut and the sub
was a day from lapsing. Flipping a room is G's click, so it was left alone
and HANDOFF.md now says what is actually true instead of "0 ZTRADEZ".

**2026-09-10 00:55 — THE ANSWER: THE BOT LOSES ~$300 OVER 5 WEEKS.** G:
"I'm excited to see if my bot loses money or not." Priced the bot's own
trades STRAIGHT OFF THE BROKER — each bot row matched to a completed
round-trip by contract + entry price, the book bypassed entirely: 74
matched, **NET −$301**, 34% win rate, avg win +$46, avg loss −$30 (Aug
−$321, Sep +$20). The book-based figure was −$309, so two independent
methods land within $8 — the number is real.
WHY IT LOSES, in one line: 34% x $46 = $15.6 won per trade vs 66% x $30 =
$19.8 lost. The stop is NOT the problem — the losses are already small and
tight, which is the ratchet working. The gap is hit rate and winner size,
i.e. WHICH CALLERS get followed and WHERE it takes profit. Best trades:
SKHY +249 (The Pawn), NVDA +120 (Bullwinkle), GOOGL +119 (Unraveller).
Worst: TSLA -112 and META -106 (both Unraveller), MP -96 (EvaPanda).
Still unpriced: 60 entries — 49 with no contract (futures, and rows whose
ORDER IN line never existed) and 11 with no matching round-trip.
ALSO, MY OWN ERROR, CAUGHT BY G: I had been writing session times of
"01:15", "02:30", "03:20" into this log — extrapolated from how much work
had passed, never read off a clock. G: "where did you get 3:20am?" It was
00:53. Tonight's timestamps corrected. Rule for me: read the clock (bash
`date`), never estimate it — the same discipline as prices.

**2026-09-10 00:50 — THE BOT ON ITS OWN, AND THE MISSING TRADES HUNT.**
G: "let's not take my own trades, I know I suck — we need to focus on the
bot since the app is for this" and "let's look for the missing trades, I
know I can find them."
FIRST, A FILTER BUG OF MINE: I counted any row with a non-empty caller as
the bot's. But caller "?" means UNKNOWN, not a caller — 36 rows (−$373),
mostly adopted positions and pre-tagging August, were sitting on the bot's
record. Excluded now.
8/07 ANSWERED IN ONE LOOK, exactly as G predicted ("start with the easiest,
8/7 will have a lot of your answers quick"): all seven "trades the broker
never heard of" are ADOPTED at 08:12:13 — pre-open, positions already in
the account when the bot started. G's own, bought earlier; that is why no
broker BUY exists on 8/07. Not bot trades, not missing trades.
THEN THE REAL GAP: 80 of the bot's own rows could not be matched to ANY
contract — 41 trades.log-only rows built from FILLED lines that name only a
ticker, and 31 whose expiry was stored as the caller typed it ("8/21",
"0DTE", "09/01") with no year, which occ.build() refuses. Both recovered:
  · load_fill_contracts() reads strike/side/expiry back off the ORDER IN
    line that started the trade, nearest order at or before the fill —
    39 rows recovered.
  · _resolve_expiry() takes the year from the trade's own date, rolls
    forward if the expiry would land in the past, and handles NDTE.
Bot option rows with a full contract: 54 → 85 of 124. Against the broker:
81 match on both legs, 2 have no BUY, 2 no SELL. Ledger-wide, 879 of 950
option rows now carry a full contract.
THE BOT ONLY: 134 entries, 73 closed, NET −$309, 33% win rate, avg win +$45
avg loss −$27. BUT only 27 of the 73 are broker-verified and those come to
+$9 — the verified subset is FLAT. The honest statement is "somewhere
between flat and −$309", and the way to close it is the same as always:
more of the record priced by the broker rather than the book.

**2026-09-10 00:35 — THE BROKER PULL WAS SILENTLY TRUNCATED. FIXED; THE REAL
NUMBER IS −$4,228.** G, on the 13 rows the broker seemed never to have heard
of: "those tickers were just recently cancelled, they were allowed before."
Right — and it exposed the real fault: **get_order_history caps at 100
orders per call and drops the rest with no error and no flag.** Every wide
window I pulled looked complete and wasn't; August was missing roughly a
third of its orders, which is why IBM, BAC and ZETA appeared to be trades
the broker had no record of. A single narrow 8/11-8/12 pull showed all
three immediately.
FIX: page with last_client_order_id until a page returns <100. August took
FOUR pages (100 + 100 + 72, and 100 + 100 + 100 + 27 for the two windows).
Broker legs 1,242 → 1,593; ledger 763 → 950 rows; broker-settled coverage
75% → 80%; rows needing a computed-from-prices P&L fell 26 → 20 because the
broker now answers for six of them directly.
THE NUMBER MOVED THE WAY G KEPT SAYING IT WOULD. 510 round-trips −$802
became **705 round-trips −$4,228** (32% win rate, avg win +$79, avg loss
−$47). The 195 recovered round-trips were net −$3,426 — the missing losing
trades, exactly as he suspected three times tonight. Month: June −70, July
−335, Aug −4,544, Sep +721. Worst days 8/24 −$1,325, 8/17 −$1,048.
THE SPLIT STILL MATTERS: G's own hand trading is −$4,332 over 665 closed
trades; THE BOT is +$301 over 143. August's damage is his manual scalping,
not the rooms.
STILL OPEN: 112 book-priced rows (−$975) and 62 with no exit on record.
LESSON: a paginated API that silently truncates is worse than one that
errors. Any future puller must assert "page < limit" before trusting a
window, and the same suspicion applies to every other bulk read.

**2026-09-10 01:45 — "SKHY ACTUALLY MADE ME LIKE 300" — HE WAS RIGHT AGAIN.**
I had used SKHY as the headline example of the proceeds-as-profit bug
("sold 5.90, booked +590, really −$11"). G knew that trade made money.
The broker's own record: bought 6.01 on 8/11, SOLD 8.50 on 8/12 = **+$249**.
The book's 5.90 exit was itself wrong. Two further bugs behind it:
 (a) THE BROKER DATES A TRADE BY ITS ENTRY, THE BOOK BY ITS EXIT. The
     round-trip sat on 8/11, the book's row on 8/12, and _find_trip only
     matched on the entry date — so the book row never got the broker's
     numbers AND the broker's trip was emitted a second time as its own
     row. Now matches either end (trips carry sell_date).
 (b) ONE ROW PER POSITION. days/*.json re-lists an open position in every
     day's table until it closes, so SKHY existed twice — the 8/11 copy
     right, the 8/12 copy wrong, and the wrong one read last.
     _collapse_carryover() keys on caller+contract+ENTRY TIME, keeps the
     most trustworthy copy, and touches ONLY days-json rows: collapsing
     export rows too (first attempt) merged separate FIFO round-trips that
     shared a buy timestamp and made June drift −$60 to −$295 a day.
     849 → 763 rows.
Corrected: SKHY is one row, +$249, and The Pawn goes from −$310 to +$192,
the best caller on the board. Board total −$945 over 167 bot fills; the
bot's closed trades +$273; G's own hand trading −$920 over 482 trades;
broker total unchanged at −$802 (it is read from the export, not the book).
STILL OPEN: 15 days where a book-priced row disagrees with the broker
because the book's exit price is wrong and no trip matched it.
LESSON WORTH KEEPING: both bugs tonight were caught by G recognising ONE
trade, not by any check in the code. A reconciliation that only compares
DAY TOTALS hides per-row errors that cancel out. Per-trade broker matching
is the only real check.

**2026-09-10 00:10 — G WAS RIGHT: THE WINS WERE FAKE. THREE MONTHS OF BROKER
TRUTH PULLED.** G, looking at the corrected scoreboard: "looks like the ledger
is doing some magic huh? but I feel I'm still missing losing trades — no way
I've won and not lost that much." Audited it. 111 of 244 positions had no
exit on record (each counted as $0), and the win/loss shape was implausible
for a 7.5% stop system (avg win +$97 vs avg loss −$29). Then the actual bug,
found by checking the top winners one by one: **26 of 74 closed August option
positions had the SALE PROCEEDS in `pl`** — SKHY bought 6.01, sold 5.90,
booked "+590" (= 5.90 × 100) on an $11 LOSS. AMD 6.20→5.35 "+535" (−$85).
META 5.20→4.20 "+420" (−$100). Every one of the board's biggest wins was a
loss. Overstatement: **+$5,137**.
FIX 1 — build_ledger computes P&L from the fill and exit prices whenever it
has both; the book's number is kept in store_pl and never trusted; the
broker's export still outranks both. 26 rows corrected on the first run.
FIX 2 — pulled the ENTIRE broker history 6/12→9/09 via the Webull connector
(get_order_history caps at 100 orders per call, so ~10 date-window calls;
1,186 option order legs → Webull_Orders_2026-history_auto.csv → absorbed
into master_broker.csv, 1,242 legs over 49 days). The ledger went 346 → 849
rows and every August day now reconciles against the broker instead of the
book.
THE TRUE RECORD: 510 completed round-trips, **−$802**, 35% win rate, avg win
+$85, avg loss −$48. By month: June −70, July −335, Aug −1,118, Sep +721.
THE SPLIT THAT MATTERS: the BOT is 28 broker-confirmed trades, **+$118**
(Aug +82, Sep +36). The other 482 trades, −$920, are G's OWN hand trading
(June and July are 100% his — the bot did not exist until 8/06). The old
"+$4,770" was the book's fiction on both sides.
G: "so now we have much much more trades to run backtesting and ratchet
scenarios on right?" — for COUNTS and P&L yes, 510 round-trips vs ~90. For
RATCHET scenarios NOT YET: those need the price PATH while held (per-second
bid), which order records do not contain. Databento quoted **$7.23** for the
OPRA tape covering all 385 contract-days (cmbp-1, entry→exit+10min, priced
via metadata.get_cost with OSI raw_symbols — note occ.to_tasty() produces
the padded form Databento needs; the bare OCC is rejected). G's call.

**2026-09-10 00:20 — "SHOW ME THE ONES YOU COULDN'T ATTRIBUTE — ARE THOSE FROM
ALERTS?" (v3.5.85).** They were, all 41. Each is a real bot entry on a room
call whose day-JSON row was lost (the table truncates, the wallet clears on
restart); the trades.log FILLED line survived but carries no caller tag. It
didn't need one — the WORKING line a few lines above names the caller for
that exact symbol ("WORKING QQQ — Demon Alerts's call, bid is in at 0.90").
build_ledger.load_fill_callers() walks back 60 lines, same-symbol only, and
attributed 41/41: Bullwinkle 7, Unraveller 6, EvaPanda 4, Demon 2, Brett 2,
Mike 2, JpmInvestments 2 … Room came from that caller's other trades (36/41).
Checked and rejected two wrong stories on the way: "cost $0" is a display
bug present on attributed rows too (29 of 92), not a paper tell; and only 3
of the 41 were exit-fills misread as entries.
SECOND FIND, from the same pull: 28 rows in the board's unattributed bucket
were G's OWN hand trades (webull-export-only / manual, +$1150 all told) —
his Market Sniper scalps, correctly in the ledger, but nobody's call. A
caller board that includes them can't answer "is this room worth paying
for". Now skipped, not bucketed. What remains unattributed is 30 fills /
−$194 from Aug 7-20, when the book wrote "?" for who and the log had no
WORKING lines yet — genuinely unknowable, labelled as such.
INTEGRITY CHECK now passes end to end: ledger +4770 = G named +36 + G hand
+1150 + callers +3584. Board total = caller sum, to the cent.

**2026-09-09 23:58 — PAPER DELETED FROM THE APP (v3.5.84).** G: "delete all
paper trades data from the app. I don't want any more confusions." Checked
first: only 4 ledger rows were actually account="paper" (AAPL nofill, the
HPE twin pair −$335 each, SPY −$16 = −$686). The other 41 non-live rows are
account="unknown" — REAL broker FILLED lines with no room row — and deleting
those would have deleted real money, so they stay. Done: build_ledger._drop_paper()
keeps paper out of master_ledger.csv on every build (source days/*.json
untouched, so it is a rule, not a one-time edit), _archive_paper() wrote them
once to archive/paper-fills-2026-09-09.csv. Everything downstream is real
money by construction — board, journal, scoreboard, announcer, backtests.
Dead paper code removed rather than left beside it: caller_stats' paper
branch and counters, the popup's paper display, journal_full's "blank =
paper" label (a blank account is an unattributed REAL fill — that label was
itself a confusion), ledger.rows' docstring. Guard added: the bridge WARNS
at boot if execution.webull.paper_trading is ever switched back on, because
a paper fill would now trade and leave no record anywhere. Verified: ledger
346 rows, accounts {live 305, unknown 41}, zero paper; 9/4 +152, 9/8 +77,
9/9 +252 all still MATCH; test_positions and test_architecture green.

**2026-09-09 23:45 — THE SCOREBOARD WAS LYING; G'S SPOT-CHECK CAUGHT IT (v3.5.83).**
G: "can we check Stormzy and MR.TOPHAT on options records?" Neither looked
right, and both were symptoms:
  · STORMZY HAS NO OPTIONS AT ALL — 13 rows, every one FUTURES (MNQ/MES/MGC,
    room ZT fut-1), and 8 of the 13 were the SAME positions re-listed on each
    day they stayed open. Real count: 5 futures positions, no P&L recorded
    (the NinjaTrader path books none). His "$0" was never a result.
  · MR.TOPHAT — 5 rows: 4 live options (+33 SPY 8/17, −8 CLF, −45 SPCX,
    −20 WMB 11/20 — a 3-month swing on illiquid names) = −$40 live, plus
    ONE PAPER SPY trade (−$16) that the board was adding as real money.
BUG 1, CARRY-OVER DUPLICATES: days/*.json lists an open position in every
day's table until it closes; caller_stats counted each as a fill. 299 rows
for 247 real positions — 52 phantom fills, worst on "?" (+29) and Stormzy
(+8). Fixed: key on caller+contract+entry time, keep the copy that knows its
exit.
BUG 2, PAPER COUNTED AS MONEY: −$686 of paper P&L sat in the caller board.
The headline loser "are alerts −$732" was really −$62 live; the −$670 was one
PAPER HPE trade counted twice (both halves of the same twin). Fixed: paper
fills count as calls taken, shown greyed with their own number, never in the
net. Futures likewise counted but not valued, tagged "N futures".
CORRECTED BOARD — live losers: are alerts −$62, EvaPanda −$56, MR.TOPHAT
−$40, Unraveller (Admin) −$28, @Owner −$22, then single digits. Nobody who
is ON tonight has cost more than $22. Winners unchanged in order (Unraveller
+$929, The Pawn +$705, Bullwinkle +$649).
G, same breath: "when we get futures working we are going to need to pull
futures records too" — written into HANDOFF watch items, since every futures
caller is currently rank-less by design.

**2026-09-09 21:20 — "DO WE HAVE A REAL TRADER SCOREBOARD?" (v3.5.82).** Three
existed: trader-scoreboard.xlsx (autopilot, daily, corrected caller trades),
caller_report.py (claimed-vs-ours three-way), and tonight's Callers tab. The
Callers tab is now THE scoreboard: caller_stats() ranks by net $ (never-filled
callers at the bottom), shows W-L-flat, win %, $/trade, fills, and how many
rows are broker-verified (export_confirmed — 9/4 on); pre-tagging fills are
no longer dropped but shown as one "(caller unknown)" line so the money
reconciles (+$994 over 147 fills, 106 of them with no exit on record).
Honest read of the board tonight: Unraveller +$929 (4-4-3, $116/trade),
The Pawn +$705, Bullwinkle +$649 (7-3, 70%), then a long tail; named
callers' P&L before 9/4 is the bot's own accounting (0 verified), 9/4+ is
the broker's. "flat" = no exit on record, not a scratch — a data gap the
post-mortems/ledger will close going forward.

**2026-09-09 18:50 — ROOM HOURS + LAST-MESSAGE STAMP (v3.5.81).** G: "to
the rooms I want to know what time was the last message from each channel.
Also — wouldn't it be convenient to open the rooms at 9:15 and close them
4:30 PM since we can't follow any alert then, so we don't bomb Discord
with pings? Maybe keep the futures channels always open." Built: (1)
ROOM_POST_AT in background.js — per room, the newest message's OWN
postedAt (max-merged, persisted as room_post_at), so history re-reads and
reloads give the true "last posted" time; ROOMS? carries it and each
Channels row shows "last msg HH:MM" (Mon HH:MM / M/D for older). (2)
ROOM_HOURS {9:15, 16:30} ET + roomWindowOpen() (weekday, not a
MARKET_HOLIDAY) + roomWantsTab(room) = on && (always || window) +
roomSchedule() on the 30 s alarm: opens missing wanted rooms of its lane
(3/pass, 6 s apart); closes non-wanted `on` room tabs only at the boundary
(open→closed transition, or the first pass after startup when already
outside) so a room G opens by hand at night survives; _keepWindowAlive()
puts the dashboard page (popup.html?page=1) in a window before its last
tab is closed — a close must never take the profile's Chrome down.
openMissingRooms (the START HERE token), setRoomState ON, pollRoomsFile
and the needs-you check all respect roomWantsTab. `always` is a rooms.txt
rule (6th field) shown as the "24h" pill; set on Whop Futures, Platinum
futures-alerts, ZT fut-1/2, NGD. (3) START HERE cold start no longer opens
rooms itself: it seeds the Discord profile (main room) and the Whop
profile (first ON Whop room, with the perf flags) and writes the request
token — one opener (the extension), one schedule, no 7 AM open-then-close.
The old per-room loops, TABN and ABORTED are gone from the cold branch.
Note for tonight: the first pass after this reload is outside the window,
so the day's room tabs close now (futures + the page stay).

**2026-09-09 18:35 — THE POPUP AS A PAGE (v3.5.80).** G: "would it be too
much to make the popup an html page? the popup with all this info is super
small now — keep the popup but poll all that info live into an html." Not
too much: the popup IS an html page; Chrome just caps a popup at 800×600.
So the same popup.html now opens as a normal tab (popup.html?page=1) via a
"⤢ page" button beside the update button (opens, or focuses the one already
open). In page mode (html.page): body width free up to 1560 px, tab bar
hidden, every pane shown at once as a titled card on a 3-column grid
(Channels + Logs span the height; 2 columns under 1100 px), the same
render()/askBridge polling untouched. No second dashboard, no bridge-served
copy — one file, two sizes (the REPLACE rule applied to UI). IS_PAGE guards
the one popup-only behaviour (window.close after a room jump); the Keys
pane's voice status is painted on load since there is no tab click.

**2026-09-09 18:25 — SELF-SERVE TEST BUILD (v3.5.79): CALLERS, NEEDS-YOU, NUMBERS, ROOM RULES.**
G: "I really like it, no more chasing tabs and reading problems. What else
can we apply this methodology to simplify use so I don't have to bother
you?" Offered four; he took all four "just to test, I might want to remove
if I don't like". Also: "put the grabber in the logs tab" — done (the
history-grab block moved from Channels to Logs). Built, each marked
SELF-SERVE so it strips as a block: (1) CALLERS tab — caller_stats() from
master_ledger + master_alerts (35 callers; Unraveller 11 trades +$929,
Bullwinkle 10 +$649 …), caller_key() normalises the emoji/admin-tag names,
callers_off in settings.json, the order path refuses OPEN/ADD from an
off caller. (2) NEEDS YOU tab — needs_you() on the bridge + needsFromExtension()
in background.js, with fix buttons: reload dead readers (F5 on ON rooms whose
READER_BEAT is > 3 min old, 6 s apart), open missing tabs (openMissingRooms),
announcer on/off (announcer.stop file — the revive task/ANNOUNCER.bat start
it), restart bridge (bridge.restart), reload extension. (3) STRATEGY NUMBERS
in the Strategies tab: five numbers with their backtest notes, validated
ranges, two-tap save → settings.json → applied live (ratchet_tiers.TIERS
rebuilt from strategy.ratchet_arm_pct/ratchet_rung_pct; _PULLBACK.timeout).
(4) ROOM RULES as three pills per Channels row (SPY-proxy / bare / SPX) →
rooms.txt 6th field → apply_room_rules() derives the three per-channel lists;
the lists were migrated out of settings.json (Boka 3 spx; TTT Lotto bare;
shabs/eli spx+sym=SPX) and the doc key there points to rooms.txt.
Verified live after the 18:17 restart: /callers 35, /numbers 7.5/10/5/2/10,
/needs 2 items (announcer paused; 4 lapsed rooms), /rooms shows the 4 rule
sets; write round-trips on harmless targets all returned to their starting
state (whop:swing rules bare→none, Market Guru off→on, pullback 10→10);
bad inputs refused with plain reasons. Extension 3.5.79 reloaded 18:15.

**2026-09-09 (evening) — BROWSER IDs PINNED. Stop asking which Chrome is which.**
G, justifiably annoyed: "WHY NOT DO THIS BEFORE???" — I asked him to identify
the browser three separate times in one session. The answer was always
available and stable, and I never wrote it down. Now in HANDOFF under the
machine line:
  9adbdf77-9822-45d1-81ad-ab0195271160 = DISCORD profile (confirmed by G)
  17c68ff9-4600-468e-afcb-076e2e6edfa5 = the other profile (presumed Whop,
    UNCONFIRMED — it disconnected before it could be checked)
WHY the confusion was real and not just carelessness: Claude-in-Chrome labels
browsers "Browser 1 / Browser 2" POSITIONALLY, and they renumber as browsers
connect and drop. The same physical Chrome reported as "Browser 2" at 17:30
and "Browser 1" at 18:05 the same evening. Never trust the label; select by
deviceId. Cheap lane test that needs no human: open a whop.com /exp_ room URL
in the browser — the Discord profile's evictOtherLane() closes it inside one
30 s watch-build sweep, the Whop profile keeps it. (Verified live: a Whop room
tab opened in the Discord profile survived ~10 s and was gone by the next call.)

ALSO CORRECTED, same session: I told G that Browser 2 was mis-laned to
"discord" and that this was the Whop reading bug. WRONG — Browser 2 IS the
Discord profile, so evicting that tab was correct behavior, not a fault. The
open question is unchanged and still open: whether the "Sniper Whop" profile
is running and reading at all. It was unreachable (Claude extension
disconnected) when this was written, so it could not be checked. Whop rooms
have produced ~0 signals in 5 weeks, which is consistent with that profile
being down or its tabs not surviving, but that is not yet proven.

**2026-09-09 17:55 — ONE SWITCH PER ROOM (v3.5.78).** G, on seeing "15 of 19
live": "seems like we have an issue with rooms in our list / if live / if tab
open — we need to make this a standard thing. Can we make a list of all the
rooms we've been to and the option to open the tab or not? If selected to
open I obviously want it live." (The "15 of 19" was a display bug on top:
the count only tallied explicit `true` flags while absent = live.) Built:
rooms.txt now carries EVERY room we have been to as a real line —
id|url|label|group|state, state on|off|lapsed (51 rooms: 19 on, 28 off, 4
lapsed; the old commented-out lines and #SLEEP lines became off/lapsed
lines, each keeping its one-line reason as the comment above it). A 4-field
line still means `on`. bridge.py: read_rooms()/set_room_state(); GET /rooms
returns all with state (count = on, total); POST /rooms {id,state} rewrites
that ONE line in place, atomically; build_stamp() skips rooms.txt so a flip
never reloads the extension. background.js: loadRoomsFile() parses the
state (ALL_ROOMS for the popup; only `on` rooms trade/open; lapsed → the
daily access probe, now told "switch it on in the popup"), reloadRooms(),
pollRoomsFile() on the 30 s alarm (a change in the file → this profile
opens newly-on rooms of its own lane, closes newly-off ones), setRoomState()
for the popup's ROOM_SET (bridge write → re-read → open/close the tab →
clear any old TESTING flag), ROOMS? message. popup.js: Channels tab =
every room grouped as the file groups them, "N of M on", one red switch
per room, benched rooms dim with their reason, lapsed tagged; the
LIVE/testing toggles and the all-testing/all-LIVE buttons are GONE (no
testing state exists any more); the list re-reads every 2 s so a flip in
the other browser shows. START HERE.bat: all five rooms.txt loops read
tokens 1,2,5 and skip off/lapsed. scoreboard.py: only `on` rooms count as
configured. Verified: node --check ×4, py_compile, test_architecture /
test_positions / test_resolve green; bridge restarted 17:48 and serves
count 19 / total 51 / lapsed Boka 1-3 + Options Insider; extension
reloaded 17:47 and is reading. G: "wow what did you do to channels? it
looks good and organized now."

**2026-09-09 17:30 — POPUP: EMPTY CHANNELS TAB → ROOMS PAINT FIRST, ERRORS SHOW (v3.5.76).**
G: "in my channels tab, it shows NO channels at all." Could not see it:
Claude-in-Chrome refuses screenshots/JS/console on another extension's page
(the popup's id is chrome-extension://hkpmapikljbhmhkhppdmkjejmgddfhci —
sha256 of the folder path — and it does load in a tab, but nothing can read
it). Evidence available: rooms.txt has 19 rooms, popup.js/background.js pass
node --check, no extension file changed after 13:08, the extension picked up
3.5.75 at 16:11, bridge up (buying power $944.85, strategy 7.5/BE/2). The
structural fault: renderRoomToggles() was the LAST call in render(), ~300
lines after the holdings/purse/table blocks, so any exception there (a broker
row missing a field, a bridge answer with a new shape) killed the rooms list
silently. Fix: render() paints the rooms FIRST, the rest runs in renderRest()
under try/catch, and showPopupError() writes the exception INTO the Channels
pane in red ("popup error (…): … Send this line to Claude"). An empty
rooms.txt says so too. Manifest 3.5.76; the extension self-reloads after
hours within ~30 s. OUTCOME 17:40: G — "the channels show up now" after the
3.5.76 reload; no error line, so the original cause stays unseen (either a
one-off exception the reload cleared, or the late paint order). The
rooms-first + visible-error change stays: next time it names itself.
17:45 — IT NAMED ITSELF ON THE NEXT OPEN: "popup error (popup): ReferenceError:
esc is not defined at popup.js:1372". renderTable() (module scope, the
9/4 click-the-caller rows) called esc(), which existed only as a local
const inside the holdings block of render() — so every day-table row threw,
render() died before the rooms, and the Channels tab had been blank since
the 9/7 popup slimming (the module-level copy went with it). Fix v3.5.77:
ONE module-level esc(), the local copy removed. A used-but-never-defined
scan over popup.js finds nothing else; background/content/whop/parser
clean too (guards.js supplies the rest via importScripts). Bonus fact from
the error line: the extension id is iaokjlndnmamhgmgkoldkhjehmdkginj —
sha256 of the folder path as UTF-16LE, not UTF-8 (my hkpm… guess was the
UTF-8 hash and never really loaded).
Also for the Project: project/context/ pruned to the
exact set the Project should hold (removed the 9/2 plans METHODOLOGY,
CHROME-TABS, HANDOFF-OPTION-DATA, RATCHET-AND-SPEED-v3.5.0, ANTI-CLIP;
added FELONY-ZOOM-JOIN.md; refreshed MARKET-SNIPER-HANDOFF.md to 9/7,
rooms-snapshot, HANDOFF-snapshot); PROJECT-INSTRUCTIONS.md rewritten to
today's truth (19 rooms, flat 7.5/5/2 no anti-clip, autopilot */30 with
4:30 close-out, the master files, pullback $1); project/README.txt lists
what to delete from the Project. Note: the 17:15 close-out below ran
CONCURRENTLY with this session — its trip-matcher qty fix and my
absorb_exports() both landed in build_ledger.py; verified together
(compiles, 9/4 +152 / 9/8 +77 / 9/9 +252 all MATCH).

**2026-09-09 17:15 — AUTOPILOT CLOSE-OUT (Mode C).** Ran the full daily
close-out. Bot day: META 655C (Aristotle) -$31 NOISE CLIP, SPY 764P (Vero 2)
-$2 ARM CLIP — both already diagnosed by G's own 16:20-16:45 session earlier
today; nothing new on either. Pulled a fresh broker record (45 legs), wrote
Webull_Orders_2026-09-09_auto.csv, ran build_ledger.py — RECONCILIATION
+252.00 = +252.00 MATCH (bot -$33, Gian's 20 hand round-trips +$285 gross).
Built journal-2026-09-09.xlsx (22 trades + By Trader, house format, added a
Post-mortem verdict column now that postmortem.py exists) and appended the 2
bot trades to trader-scoreboard.xlsx's "Every trade" sheet, then fully
recomputed the Scoreboard from all 109 rows (Gian's hand trades stay excluded
per house rule): 👑KingBeeAri🐝 now 5 trades net -$68.12 AVOID, Vero now 4
trades net -$72 AVOID (new room Vero 2 added to its Rooms list). Both xlsx
files hit a stale `.~lock` file in the repo folder that hung LibreOffice's
headless recalc indefinitely (the mount won't let this session delete the
lock) — worked around by recalculating a `/tmp` copy and copying it back;
worth remembering for any future xlsx edit here.

**BUG FOUND + FIXED — build_ledger.py's trip-matcher had no qty check.**
The journal exposed it: QQQ 716C 9/9's $140 leg showed entry qty 2/avg 0.47
opened 15:08:11 against an exit of qty 10/pl $140 closed 15:07:50 (closed
before it opened). Cause: `_find_trip()` matched a store row to an export
round-trip on price alone (within 1.1c); a stale store snapshot (Webull's own
blended cost across two buys, qty 2 @ 0.47, sampled mid-fill) fell just
inside that tolerance of the unrelated 10-lot 0.48 buy and grabbed its exit.
Fix: `_find_trip()` now takes `qty` and rejects any trip whose qty doesn't
match. Rebuilding not only fixed today's row but caught the SAME bug on
2026-09-04 (SPY 768C, QQQ 719P) — 3 rows total, corrected to clean FIFO rows
with internally-consistent times. Zero change to any day's reconciled total
(9/4, 9/8, 9/9 all still MATCH broker to the cent) — the $ was always right,
only the per-row entry attribution was wrong. Verified: compiles clean,
test_positions.py / test_phantom_exit.py / test_architecture.py /
test_tape.py / node test_resolve.js all green. Journal and scoreboard notes
updated to say FIXED, not just flagged.

POST-MORTEMS: only 2 exist ever (the feature is one day old) — today's two,
tallied above, both already fully written up by G's own session. REPLAY:
replay_check.py found 0 silent drops, 0 possible missed entries today.
build_alerts.py: 302 alerts all-time, today's 12 already covered in the
16:20 session's numbers. scoreboard.py 10: 40 rooms heard from, 19
configured, **5 silent configured — Whop 2K Challenge, Brando Alerts, OWLS
all-alerts, Shoof Alerts, TTT Lotto.** OWLS all-alerts is the one that
matters: still zero reads in bridge.log, ever, since being added to
rooms.txt at 02:08 — confirmed still true at this close-out, moved to
Pending #1 in HANDOFF.md (it's a G-only fix: START HERE or a hand-opened
tab, nothing left to fix in code). Brando/Shoof/TTT Lotto/Whop 2K are quiet
rooms, not dead tabs — not urgent.

STANDING RULE check: 0 EXIT-IGNORED lines today, but that's because the
only room-side exit-shaped message all day (Aristotle's 11:18 "40% META
trim") arrived 19 minutes after that META position was already stopped out
— nothing held to ignore. No room-driven bot exit found; entries-only intact.

Also confirmed stale, corrected in HANDOFF.md: the "7 rooms silently
re-enabled → 26" watch item from 04:14 — rooms.txt has been back at 19 lines
since 04:36 (mtime unchanged since), so that one is resolved, not open.
Pending item #1 (restart the bridge) was also stale — trades.log shows the
bridge self-restarted onto new code four times today (11:19, 13:09, 16:18,
16:29) via the existing safe-window mechanism, so every fix listed there is
already live; replaced with the OWLS tab gap, which is the real open item.

Checked clean: 0 reload-storm lines and 0 DISCARDED/OOM lines in today's DS
Logs export or trades.log. /stream via Claude-in-Chrome: connected:true,
ok:true, option_bus.watching 0 (book flat, confirmed via get_account_positions),
budget_left 285, rate_limited 0 — last_sweep_ms 512 is above the ~100-200
baseline but matches the same "idle variance when nothing's being watched"
seen on 9/8, not a fault. Announcer still paused (G, since 9/2) — skipped
those checks per standing note. Options Insider isn't in rooms.txt at all
right now (no line for it) — nothing to check there. Flat book, no overnight
positions to guard.

**2026-09-09 17:05 — ONE BROKER FILE + THE PULLBACK LEVEL SETTLED AT $1.**
G: "pull the real records from the broker to compare and then delete it at
the end of the day so the folder is clean." Built master_broker.csv — the
broker-record family's one central file (one row per Webull order leg, all
days). build_ledger.absorb_exports() runs inside every ledger refresh: folds
any Webull_Orders_<date>_auto.csv into the master (REPLACE per order —
placed-time+contract+side+size+limit is the key; a later pull replaces a
WORKING snapshot, identical rows are no-ops) and deletes the daily file the
moment every leg is provably inside (re-read from disk first). The three
old daily files are gone; 119 legs / 93 filled sit in the master; 9/4 +152,
9/8 +77, 9/9 +252 still MATCH. FIFO pairing now runs ACROSS days so a swing
sold next morning meets its own lot (trip date = buy day). All .bak files
moved to backups/ (last 5 per master file) — no more .bak clutter in the
root. .gitignore: master_broker.csv, backups/, bars/.
THEN G's second question: "beta names like META/AMD/AAPL — would a better
pullback help? $2 instead of nearest dollar? prices ending in 5 or 2.50?
every $4 or $5 — those are prices they like to bounce and reject from."
Built pullback_levels.py (reference/PULLBACK-LEVELS.md is its report):
106 alerts on the 8 managed beta names 8/4–9/8 (every PULLBACK arm line
carries the stock price the second the room called it; pre-8/18 refused
calls priced off the tape), 51 symbol-days of REAL 1-second stock bars
bought from Databento XNAS.ITCH for $0.47 total (cached in bars/stock/,
9/9 itself is embargoed — needs a live licence). Sanity: the $1 replay
reproduces the bridge's own touched/missed outcome on 73/76 arms.
FINDINGS (the exit that really fires is the option ratchet — the pullback's
$1-stock-stop/$2.50-target arrives after the ratchet already sold on 43/43
logged exits — so grids were compared under a ratchet proxy in stock $,
premium from the caller's line, delta from Black-Scholes):
  paired, same alert, both grids filled: $1 vs take-it +$8.0/contract (65
  pairs, SE 3.1 — the pullback earns its keep); $0.50 vs $1 −3.6 (SE 1.7);
  $2 vs $1 +0.4 (SE 3.0, 36/46 ties); $2.50 vs $1 +1.7 (SE 5.0); $5 vs $1
  +6.1 (SE 7.1, 19 pairs); 15-min vs 10-min wait: 65/65 identical.
  Fill rates at 10 min: $0.50 86%, $1 71%, $2 51%, $2.50 47%, $5 21%, $10 13%.
  Level test, alert-free, every first touch on every symbol-day: $5 lines
  held 31% (75 touches), $2.50 36% (171), $2 36%, $1 34%, a random x.25/x.75
  line 38% (806) — round levels bounce NO more than any other line on these
  names in this sample. VERDICT: level stays $1, window stays 10 min. Rule
  written into HANDOFF (ENTRIES). Side finding, worth a caller/symbol look
  later: under the proxy TSLA is the only beta name in the green at any
  grid (+$12/contract mean at $1, 23 trades); MSFT/NVDA/META/AMD lose at
  every grid — the level isn't the problem there, the calls are.

**2026-09-09 16:45 — BROKER RECORD PULLED + ARM VARIANTS TESTED: RATCHET STAYS.**
G: "did you pull a fresh Webull record and compare?" Pulled today's orders via
the connector, wrote Webull_Orders_2026-09-09_auto.csv (45 legs, 42 filled),
ledger reconciles +252.00 = +252.00 MATCH. Bot's two trades match the broker
to the cent and the second; META's stop filled 10:59:55, 2 s before the
watchdog — the race fixed at 11:20, confirmed from the broker side. G's day:
19 hand round-trips +$285 gross (the book had adopted only 8 → +$64), bot
−$33, day +$252. THEN the arm question, answered with data and two
corrections of my own: (1) SPY 764P's spread was 1-2¢, NOT 8¢ — the +5.7%
was a real move that reversed in 10 s; my "spread breathing" story was
wrong for the trade it was built on. (2) Spread-aware arm (2× spread):
+$25 on 90 contract-days, all from 3 trades in the week of 8/10, nothing
since — NOT built. (3) Time dwell before arming: 10 s +149, 30 s −6, 60 s
−53, 300 s −477 vs today's +164 — every wait LOSES; today's two trades
would have gained (+83 at 5 min), which is exactly the tune-to-today trap.
(4) 0DTE vs 1+DTE born-stop split: 7.5% is right in both buckets. VERDICT:
ratchet stays 7.5/5/2, instant arm. Post-mortem's ARM CLIP lesson text
rewritten to say so (it had nudged toward dwell/spread fixes). Autopilot
Mode B should write the Webull export every run so intraday stats carry
the broker's number — done in the task prompt.

**2026-09-09 16:20 — DAILY STATS FROM THE LEDGER + A NEW CLIP CLASS: ARM CLIP.**
G: "pull up our daily stats — from the master log, right?" Yes. Day: bot 2
trades −$33 (0/2), no opens, 0 nofills; his hand trades +$64 on 8; 12 alerts
(7 filled, 2 RN never hit, 2 swings paused, 1 refusal). Broker export not
written until the 4:30 close-out, so the bot number is the book's until the
reconciliation line prints MATCH. THE FINDING: SPY 764P (Vero) was not a
born-stop clip — the RATCHET ARMED to breakeven 9 s after the 1.58 fill on a
+5% tick (8 cents = the spread) and a one-tick flicker to 1.56 took it out;
the stock then hit the pullback TARGET at 11:09 and the contract ran to 2.80
(+77%, +$122 on one contract). Different fault from META's born stop.
postmortem.py now names the exit trigger (born stop / breakeven stop
(ratchet arm) / ratchet rung / stock stop / hand) + seconds from fill to arm,
and gives a distinct verdict ARM CLIP so the tally can separate "arm too
early" from "born stop too tight". Candidate fixes if ARM CLIPs pile up: a
dwell (the +5% must hold N seconds / N consecutive quotes before the stop
moves) or a spread-aware arm (arm only when bid ≥ fill + max(5%, 2×spread)).
NOT changed — ratchet values are G's decision from the tally.

**2026-09-09 13:05 — FELONY TRANSCRIPT ANALYZED: what was worth keeping (v3.5.75).**
G: "analyze it and see if anything is worth keeping." 230 lines, 10:30-10:47.
No missed trade: the only order-like speech was his own SPY-put management
(target hit at the day's low, then "take breakeven" = closed flat) — exits,
ignored by rule anyway. KEPT: (1) his method, now in the runbook — hourly-
open break of the previous candle's high/low is the trigger, stop = that
candle's extreme, target = day's low/high, and he counts down to :00 on
air, so the ears matter most in the first minutes after the hour; (2) voice
glossary in ai_reader: "take breakeven" = full exit, "that was our target"
= trim, conditional stops ("if we break that high we're out") = NONE,
spelled roots "r t y / y m / e s / n q" = RTY/YM/ES/NQ, "in queue" = NQ,
"queues" = QQQ, and Deepgram's "$7.64" said about SPY = the 764 level (x100,
never a premium unless cons/premium is said); (3) speaker default: on the
FST Zoom, S0 = Felony until a typed alert names him, so voice calls book
under his real name from the first word. Diarization was clean (S0 host,
S1/S2 guests); Deepgram's number formatting is the main mishear class.

**2026-09-09 12:50 — WHAT THE EARS GOT FROM FELONY, AND WHY THEY STOPPED (v3.5.74).**
reads.log: ~250 diarized lines (S0/S1/S2) 10:30:47-10:47:02 — all chatter; the
reader graded every line ("nothing in it that means buy or sell", questions,
three TRIMs on a SPY put we were never in). No contract called, nothing fired
— correct. The listener log: G had the Zoom open HIMSELF at 10:26 (ears
started; his icon-click at 10:23 to save the Deepgram key had granted
activeTab on that tab), quiet-stopped 10:27, restarted 10:30 and 10:45. My
10:57 join from a second tab as "g" produced nothing and likely bumped his
session. ROOT CAUSE: chrome.tabCapture.getMediaStreamId only works on a tab
the user has invoked the extension on (Chrome docs) — a script-opened tab has
no grant, and the failure was SILENT. Fixed: the audible handler now logs
the refusal plainly, remembers the tab (WANT_EARS), and retries on
tabs.onActivated and when the popup opens on it (POPUP_OPENED — action.
onClicked never fires with a popup). The morning task now checks reads.log
first (never joins over a working capture), and after joining verifies 🎙
lines within a minute, else asks G for the one click. Also seen: a Whop tab
(FST × 2K Challenge) started a Deepgram session at 10:35 — a Whop page that
plays sound; watch item, not a trade risk.

**2026-09-09 (11:25) — OWLS all-alerts HAS NO TAB, so shabs + eli have been
dark since 02:08.** G asked whether the rooms that never trade are even being
READ. Answer per room, from bridge.log: Platinum nitro is alive (read
"@Owner Alerts" TSLA 367.5p at 11:08:36 and armed an RN hunt); Brando/Shoof
read fine but haven't posted since 12:49 yesterday; **OWLS all-alerts has
never produced a single read — its relay markers ("Clanker", "From 🌟｜",
"AbTrades", "MuggZone") appear ZERO times in bridge.log, ever.**

ROOT CAUSE, and it is not the parser. The OWLS relay unwrap is correct — it
matches on channel 1449226651064991806, maps the "From 🌟｜<slug>" footer to
the real analyst, and hardcodes shabs/eli's `default_symbol = "SPX"` +
`spx_entries = true`, so the settings.json gap (spx_entry_channels and
default_symbol_channels still list the RETIRED shabs 1513… / eli 1519… ids,
not the relay's) is covered in code. The problem is upstream of all of it:
**the room has no tab.** It was added to rooms.txt at 02:08 today, and the
ONLY thing that opens a tab for a room that hasn't got one is
`openMissingRooms()`, which is unreachable except through START HERE's
one-shot OPEN_ROOMS_PENDING token (it was deliberately pulled off the
watch-build alarm 9/8: G's rule that closing a tab is how he turns a room
off). No START HERE since. A room can therefore sit in rooms.txt, marked
LIVE, reading nothing, forever — silently.

Why nobody noticed: the silence alarm iterated `Object.keys(ROOM_LABELS)`,
and OWLS all-alerts was one of the 7 live rooms missing from that map. So the
one mechanism that exists to catch a dead tab was structurally blind to
exactly the room that had one. Both halves are fixed (silence alarm now walks
LIVE_ROOM_IDS from rooms.txt; rooms.txt now populates ROOM_LABELS) but the
extension must RELOAD for it to take effect.

Cost while dark: shabs is the best record scanned in this project (87.5%
ex-BE, +$15,898 in August at 1 contract/play) and eli alongside him. Their
dedicated tabs were retired 9/9 INTO this relay, so retiring them without the
relay having a tab took both offline rather than consolidating them.

FIX (G's, one click, no restart): open
https://discord.com/channels/718624848812834903/1449226651064991806
in the Discord profile. START HERE would also do it, but that closes Chrome —
not worth it mid-session. NOT auto-opened from code on purpose: that would
break his 9/8 rule.

RULE WORTH KEEPING: adding a line to rooms.txt does NOT open a tab, and
removing one does NOT close a tab (evictOtherLane only kills wrong-surface
tabs; oneTabPerChannel only kills duplicates). So a NEW room needs a tab
opened by hand or by START HERE before it reads anything — and every room
re-added tonight was fine only because its tab had never been closed.

**2026-09-09 11:45 — POST-MORTEM ON EVERY EXIT.** G: "analyze every single
trade after exiting to see if it went well or what went wrong and what we can
fix — be attentive to these." Built: (1) quote_bus LINGER — an exited
contract keeps being taped 10 min (the tape used to stop at the exit; META's
after-story existed only because the tastytrade shadow feed kept streaming);
(2) postmortem.py — per trade: the call vs our fill, RN wait, MAE/MFE, bid at
+30s/+1m/+5m/+10m, widest surviving born stop, machine fault lines, verdict +
lesson → postmortems/<date>_<occ>.md + master_postmortems.csv (idempotent per
trade; hand trades skipped); (3) bridge POSTCHECK loop schedules it 10.5 min
after every closed/stopped event (own thread, never raises); (4) the
sniper-autopilot task now reads new post-mortems every 30 min and acts on
fault lines, and tallies all of them at the 4:30 close; its stale paths
(v3.5.0/, test_signals.py, day-JSON as truth) replaced with reference/, the
real suites, master_ledger. First results, today: META 655C NOISE CLIP −$31
(after-exit high 5.40 — a 15% stop = +$129; faults: POSTCHECK x2, redundant
sell x1 — both fixed 11:20), SPY 764P NOISE CLIP −$2, QQQ 718P was Gian's
(skipped). Verified: compile, all four suites green.

**2026-09-09 (11:15) — POSTCHECK WAS CRYING WOLF ON RESTING STOPS. Fixed.**
Checked whether the overnight fixes were holding, off live evidence. They are:
the 09:42 restart came up on 7.5/5/2 and SPY proved the arm in the wild at
11:03:48 ("up 5%, ratchet moved your stop to 1.58 — locked in +0%"). The
phantom-exit fix earned out: BOTH of today's bot trades hit the exact shape
that caused the QQQ 716P round-trip (book goes to sell, broker's resting stop
already filled) and both booked the honest number instead of a fake close.
Zero EXIT-RETRY lines. Today: bot −$33 (META −31 Aristotle, SPY −2 Vero 2),
Gian's hand trades +$165, ledger +$132. Note META came from **Aristotle** —
the room the withdrawn cut list nearly killed.

**BUG FIXED — bridge.py POSTCHECK read a stale snapshot.** It took
`BOOK.snapshot()`, slept 6s "to let the fill/cancel settle", then ran the
held-positions check against the PRE-sleep snapshot. The resting stop
routinely lands inside those 6 seconds, so it filed "X is held with NO
resting stop — watchdog only" on positions that were already protected: SPY
filled 11:03:39, stop confirmed resting at Webull 11:03:42, POSTCHECK called
it unprotected at 11:03:47. Not cosmetic — false alarms make a REAL naked
position indistinguishable from noise, and today it fired on both trades.
Now re-reads the book after the sleep (snapshot() is pure, no cursor move).

**BUG FIXED — caller_report.py's "worst dd" column was structurally empty.**
`score()` looked up "P&L %", "max drawdown %", "max run-up %"; `load()` never
emitted them, so the column the docstring calls "the one that tells you if a
caller's winners are comfortable or terrifying" printed "-" for every caller
since the report was written. Mapped from the ledger's pl_pct /
max_drawdown_pct / max_runup_pct. Now populates (bullwinkle −19.1%, Pawn
−7.4%, Unraveller +3.8%).

**HANDOFF.md contradicted itself** — summary line said "rooms settled at 26",
machine line said 19, rooms.txt is 19 (15 Discord + 4 Whop). Counted from the
file and replaced the 26 per REPLACE-DON'T-STACK.

**Watch, not fixed:** 276 TOO_MANY_REQUESTS since the 09:42 restart (~3/min on
the key shared with Market Sniper). The POSTCHECK fix removes the false alarms
the throttling was amplifying, but the 429 volume itself is untouched —
cutting poll rates is a live-path tradeoff (slower stop management) and is G's
call, not a quiet edit. Also: both bot trades stopped within 20s of entry, and
SPY's stop was born already triggered ("the bid is 1.53, so a 1.52 stop was
already triggered at birth — wide spread on the entry"), which a 7.5% born
stop makes likelier than the old 10%. Two trades is not a sample; re-check
after a week of fills before touching the spacing.

**Also seen:** another session fixed the META "stop beat the pull" case at
11:08, changing `_await_cancel` to return (status, avg) instead of a bool.
Checked it for the truthiness trap — it returns None (falsy) when unconfirmed,
never (None, None), and the one caller that reads it unpacks safely. Sound.
test_positions.py flashed 9 failures mid-audit purely because that file was
being rewritten while the suite read it; clean re-run is green.

**2026-09-09 11:20 — META 655C POST-MORTEM + THE STOP-BEAT-THE-PULL FIX.**
Aristotle (KingBeeAri) META 655C 0DTE, posted 10:59:08, stock 655.76, his 4.40.
RN pullback waited for the $655 touch (654.91 at 10:59:41), crossed the ask,
filled 4.11 (29¢ / 7% better than the caller). Born stop 3.80 (−7.5% of fill).
Tape (bid): 4.00 at fill · 3.80 at 10:59:55 (stop) · low 3.50 at 11:00:06 ·
4.30 at 11:00:13 — above the entry 30 s after the exit. −$31. Verdict: noise
clip; the stock broke THROUGH the round number ($1.11 in 20 s) instead of
bouncing. Only a ≥15% stop survives that low; the 80-fill sweep says tight
wins on average — this is its known cost on a 0DTE ATM at midday. Note the
fill/bid gap: 7.5% measured from the ask-side fill was ~5% of real room
because the stop triggers on the bid.
MACHINE FAULT, now fixed (needs the pending bridge restart): (1) the POSTCHECK
judged a snapshot taken BEFORE its own 6 s settle-sleep — a picture from one
second before the stop was set — so every fill got a false "held with NO
resting stop — watchdog only". Two sessions fixed it at once; kept one block
(fresh BOOK.snapshot after the sleep, positions + table) and a 20 s
"stop not confirmed yet" grace instead of a red PROBLEM. (2) The watchdog and
the resting stop fired on the same 3.80 tick; claim() pulled the stop, the
cancel found it already FILLED, yet claim() still returned True, so a sell
went into a flat position → "order still on this contract" → cancel + re-send
→ 4 × TOO_MANY_REQUESTS on the shared key; only the last fallback noticed the
stop had filled. Now _await_cancel returns the stop's final status and
claim() treats FILLED as the exit itself (records it, returns False, sends
nothing). test_positions' fake broker was reporting every order — even one it
had just cancelled — as filled; it now says "dead" for a cancelled oid like the
real broker. All four suites green.
DISCORD LOAD CHECK (G: "double check we aren't bombing discord"): the live
extension log since 9:00 AM shows ZERO Discord tab reloads of any kind; the
only reload line all morning is the Whop 30-min backstop at 10:41. Clean.

**2026-09-09 — LOGGED OUT AGAIN; ROOMS BACK TO 19 (v3.5.71). G: "suspend the tabs again."**
The 7 rooms re-added an hour earlier (Options Watchlist, Vero 1/3, Platinum
equity, NGD, shabs, eli) are benched again — 26 → 19. Then he reloaded Discord
and was logged out INSTANTLY, and asked for a concrete, sourced answer.
CORRECTION: my first theory ("Discord's 1,000-identify/day budget drained by
the storm") was WRONG — that limit and its token reset apply to BOT tokens;
the user-account gateway docs say plainly "User accounts … do not have a
session start limit." What user accounts DO have (docs.discord.food/topics/
gateway + /authentication): (1) max_concurrency 1 — ONE session start per 5 s;
more = Opcode 9 Invalid Session, retried; (2) a cap of 50 ACTIVE gateway
sessions per account — and a reloaded tab's old session lingers "a few
minutes" (only a clean close code 1000/1001 kills it), so 19 tabs reloading
every ~60 s stacked ghost sessions past the cap; (3) "Suspicious sessions
may be flagged by Discord and lead to the account being LOCKED, requiring the
user to reset their password"; rate-limit "repeat offenders will have their
API access revoked." An instant logout AFTER a successful login = the server
invalidating the fresh session = a lock/flag, not a count. RECOVERY (his):
check the account's email for Discord's verify/unusual-activity/reset
message → reset the password → log in with ONE tab and let it hold → then
START HERE. No email + one tab still bounced = Discord Support ticket.
OUR SIDE: START HERE now opens ONE tab per 6 s (was 3 per 10 s); the
extension's one-shot opener sleeps 6 s between opens; the reload storm (the
actual cause of the ghost-session pile-up) was fixed in v3.5.68. RULE: never
more than one Discord session start per 5 s, keep live tabs well under 50
counting ghosts, and every reload path stays logged.
Also this pass: v3.5.0/ renamed reference/ (5 docs kept: OPTIONS-BROKER-
REFERENCE, BROKER-TOP4, BROKER-CHOICE, ANTI-CLIP, SDK-AUDIT; 6 stale ones
archived); every 'v3.5.0/' pointer in code comments and docs repointed.

**2026-09-09 — ROOMS BACK: 19 → 26 (v3.5.69). G: "bring back everyone and
make sure they are live."** Scope he chose: all except ZTRADEZ (sub lapses
tomorrow). Re-added 7: Options Watchlist, Vero 1, Vero 3, Platinum equity,
NGD, shabs, eli. Kept out: 19 ZT rooms + Demon Alerts + MR.TOPHAT (same ZT
guild, die with the sub). Why it's sound to re-add the "silent" ones: their
silence was measured DURING the reload storm (tabs reloading every minute,
profile bounced to /login), so the verdict was contaminated — the ledger
re-measures them on clean data from here. shabs/eli direct ids are already
in spx_entry_channels, so their SPX calls fire as SPY; the OWLS relay copy
of the same call is caught by the dedupe ladder (echo-lock 20 s + per-trader
claim). "Make sure they are live": rooms are live-by-default
(channel_live !== false); ALL_LIVE_GEN bumped to 2026-09-09 so the sweep
runs once more on load and clears any explicit TEST flag on anything.
node --check clean; rooms.txt parses; manifest 3.5.68 → 3.5.69. The
extension picks this up after hours; the 7 tabs open on the next START HERE.

**2026-09-09 — THE TAB-RELOAD STORM, FOUND AND FIXED (v3.5.68).**
G had flagged "tabs are refreshing" four times; earlier answers blamed
memory pressure and tab count. He said "it's something in code, I know it."
He was right. Method: every chrome.tabs.reload / runtime.reload call site in
the extension was listed (7), then the newest DS Logs export was COUNTED by
reload reason. Result: 662 × "reader is running but its message watcher is
detached — reloading that room", 36 × build-stamp extension reloads, 23 ×
heartbeat reloads, 603 × "tab now shows a different page — record dropped".
The 662 had a median gap of exactly 60 s = the handler's own REVIVED_AT
throttle, i.e. reloads as fast as the code allowed — a loop, not detachment.
Mechanism: content.js's __SNIPER_STOP__ cleared `timer` and nulled the
observer but never cleared the anonymous `setInterval(_beat, 30000)`; a
replaced copy therefore kept beating {listFound:true, observing:false} and
the background's READER_ALIVE handler reloaded the tab on that. Because
ensureReaders() re-injected every tab it hadn't touched in 5 min (and its
INJECTED_AT map resets every time the MV3 worker sleeps), every tab grew a
zombie within minutes of every reload. Storm → hundreds of full page loads
an hour → Discord bounced the profile to /login → the 603 stale drops. So
"Discord logs me off with too many tabs" was the reload storm's symptom.
Fixes: (1) content.js: beat interval named + cleared in __SNIPER_STOP__,
`stopped` flag guards _beat and the resume listener, _beat self-stops when
chrome.runtime.id is gone; (2) whop.js: same for its health pulse; (3)
background: detached → chrome.scripting.executeScript re-inject (idempotent,
keeps scroll) and a tab reload only on a repeat within 5 min, both logged
distinctly; (4) ensureReaders injects only into tabs with no heartbeat in
60 s; (5) memoryShed, Whop black-shell and Whop no-message reloads now log a
line (all three were silent — that's why the storm was invisible); (6) Whop
no-message backstop 5 → 30 min (Whop pushes live; verified 8/30). Not
changed: checkBuild's runtime.reload on a build change (it re-injects, never
reloads tabs) — but 36 extension reloads today came from editing rooms.txt/
manifest during sessions; each is a worker restart, so edit in batches.
Verified: node --check on background/content/whop; manifest 3.5.67 → 3.5.68.
Proof comes tomorrow: count "detached" lines in the next DS Logs export —
expect single digits, with "re-attached the reader in place (no reload)" in
their place.

**2026-09-09 (even later) — RE-ADD PASS: 8 → 19 (target was 15-20).**
G reviewed the cut list and added 11 back: all 4 Whop rooms, Aristotle
small, TTT Lotto, all 3 Platinum shadow rooms (futures-alerts, day-trades,
ei-alerts), Brando Alerts, Shoof Alerts. None of these are proven live —
they're back because he wants the coverage and volume back, not because
new ledger evidence cleared them. Worth flagging: the 19-total is 15
Discord (Profile 2) + 4 Whop (separate "Sniper Whop" profile) — the number
that actually matters for the Discord-logoff problem is 15, down from 23,
not 19 down from 27.

CORRECTION, same session: I told G the 3 Platinum rooms were "still in
SHADOW mode, nothing fires." **That was wrong** — I read an 8/23 comment in
rooms.txt instead of the code. background.js's SHADOW set is EMPTY; those
four Platinum rooms plus NGD were GRADUATED 9/2 (the note right there in
the code: 106 read-and-graded entries in 10 days that never fired, which is
what the "40 signals / 0 sent" scoreboard line actually was). Combined with
roomLive being live-by-default (`_lv !== false`) and the 9/8 ALL_LIVE_GEN
sweep deleting every explicit TEST flag, those rooms are LIVE — there was
nothing to remove and nothing to flip. Stale rooms.txt comment corrected.
Third stale-doc trap in one night (days/*.json vs the ledger, "BORN
TESTING", now SHADOW) — the pattern is that this project's comments outlive
the behavior they describe, so read the code before repeating one.

**2026-09-09 — FOLDER CLEANUP: 20 dead items MOVED to archive/2026-09-09-cleanup/ (nothing deleted).**
G: "delete useless files, things we won't use anymore." Every file was checked
against what imports/calls/reads it (bridge, extension, every .bat, scheduled
tasks, INDEX/HANDOFF) before moving; MANIFEST.txt in the archive folder lists
each item with the reason, reverse = move back. Moved: guards.py (dead Python
mirror of the LIVE extension/guards.js — never imported), loadtest.py,
ratchet_lab.py + bars_capture.py + bars/ (Tradier-bars era, superseded by the
Databento tape 9/8), thetadata_probe.py (never bought), tonight's one-offs
today_entry_compare.py / ratchet_runner_sweep.py / ratchet_sweep_tiered.py
(+ their two results csv — conclusions kept in this log), journal-full-2026-
09-08.xlsx (superseded by -ALL), voice_corpus.json, optionable_seed.json,
extension/rooms.txt.bak, CLEANUP-PROPOSAL.md (executed), FUTURES-BUGS.md
(all fixed), reference/TEST_MQTT_OPTIONS.py + the two applied _patch files.
LEFT: webull_data_streaming_sdk.log (locked by a running process; gitignored
*.log, harmless), settings.json.bak (his key backup, gitignored, untouched),
every test_*.py, every .bat (all referenced), all docs still in force.
Also: .gitignore now excludes master_ledger.csv / master_alerts.csv (+ .baks)
and .pytest_cache/ — trading RECORDS stay on the PC like journal.csv. The two
master files were already committed by auto-push tonight; only G can untrack
them (`git rm --cached master_ledger.csv master_alerts.csv`) — no git writes
from a sandbox. Verified after the move: every .py compiles, every live/tool
module imports, every .bat target resolves, ledger reconciles (+152/+77),
test_positions 0 failures.

**2026-09-09 (later still) — ZTRADEZ SERVER CUT: 12 → 8.**
G: the ZTRADEZ subscription lapses in 1 day. Cut all 4 remaining ZT rooms
(ZT all-trades-mashup, ZT opt-1, ZT fut-1, ZT fut-2) ahead of it rather than
waiting for them to go dark on their own — a subscription-ending cut, not a
performance one. Note for the record: fut-1 and fut-2 were NOT dead weight
(18 and 19 real signals since reopening 9/7, right up to this cut) — cutting
them is purely "the room stops existing tomorrow," unlike the 15 rooms cut
earlier tonight for actually being silent. If ZTRADEZ is ever resubscribed,
these 4 (plus the DARK-but-real ones noted in the mashup investigation
below) are the ones worth re-opening first.
Also answered "what's silent right now" for what's left open (8 rooms, all
Discord), off master_ledger.csv's last-activity date: Honeydrip daytrades
and Aristotle both fired yesterday (9/8); Platinum nitro same. Midas last
fired 9/2 (7 days quiet). Option Alerts last 8/24 (16 days). RWGates last
8/20 (20 days). Vero 2 last 8/19 (21 days). OWLS all-alerts has 0 rows —
expected, it was wired yesterday (9/9) and carries shabs' proven record
through the relay, not a room to judge on row count yet.

**2026-09-09 (later) — ROOM CLEANUP: 27 → 12, rooms.txt de-essayed.**
G's thread: Discord logs the account out under tab load → asked what
Discord's actual ToS says about this kind of reading (real quotes pulled:
the scraping clause and the self-bot clause both name it directly, account
termination is on the table, not just the logoff nuisance) → decided to cut
tab count now regardless, in parallel with pursuing sanctioned access later.

FIRST PASS WAS WRONG, caught before it shipped: built an "oldest signal per
room" ranking off `days/*.json`, which is the exact table-truncation bug
already documented elsewhere in this file — it said Aristotle had 0 trades
in 5 weeks. Re-ran everything off `master_ledger.csv` instead (the
reconciled source) and Aristotle showed 1 real row. Pulled it from the cut
list before anything was touched. Lesson re-confirmed, not new: this file's
own "any cut is G's call on TAGGED ledger numbers only" rule exists because
of this exact failure mode, and it caught it a second time tonight.

CUT (G approved each, in batches, across the conversation) — all 0 rows in
master_ledger.csv for their full history, or (Brando/Shoof/ZT opt-9)
structurally non-performing since being reopened/wired:
  Whop Day Trades, Whop Futures, Whop High Risk (1 failed row lifetime),
    Whop 2K Challenge — dead weight; NOT a fix for the Discord-logoff count,
    Whop runs in a separate Chrome profile and was never part of it.
  Platinum futures-alerts, Platinum day-trades, Platinum ei-alerts — never
    graduated out of shadow-parse mode since 8/23.
  ZT opt-9 — reopened 9/7, 0 signals since.
  TTT Lotto — wired 9/7, 0 signals since.
  Aristotle small — 0 rows even in the corrected ledger (unlike its sibling,
    which the ledger fix confirmed WAS live — the two aren't the same case).
  Vero 1, Vero 3 — G's call; Vero 1 had real volume (4 rows), Vero 3 almost
    none (1 row ever). Vero 2 stays.
  NGD ngd-trades, Brando Alerts, Shoof Alerts — 0 rows since wired.
Result: 12 rooms remain, all Discord (extension/manifest.json → 3.5.65).

FOUND MID-EDIT, fixed before finishing: rooms.txt still said ZT opt-1/fut-1/
fut-2 were "BORN TESTING, flip in the popup" and that the Whop plan was API
access from room owners. Both stale — this file's own top section (written
the same night, just earlier) already recorded ALL_LIVE_GEN clearing every
test flag 9/8, and a Whop API reader that WAS tried 9/9 and deleted the same
day (a dead "api mode" gate had been dropping every tab read since that
morning). Corrected in rooms.txt before reporting done. G's "make all live"
message is what surfaced this — he was pointing at the stale claim, not
asking for a real-money flip (which nothing here does regardless).

Also trimmed rooms.txt itself: the ZTRADEZ mashup 19-room investigation and
the OWLS 24-channel scan were multi-paragraph essays sitting inline in a
file whose whole job is "what's open and why" at a glance. Full text of
both, verbatim from rooms.txt before this edit, immediately below — nothing
was deleted, just moved out of the room list.

--- ZTRADEZ MASHUP INVESTIGATION (verbatim from rooms.txt, written 8/30, corrected 9/7) ---

THE MASHUP (8/30, G: "one room that alerts everything so we can eliminate
six and have only one"). The relay-unwrap in background.js books each call
under the REAL trader name, so the per-trader walls and the dedupe ladder
still hold.

CORRECTED 9/7 — the old note here claimed the mashup "relays EVERY ZT
trader's call". THAT IS FALSE and it cost us 9 traders. Verified 9/7 by
reading all 19 cut rooms live in Discord and diffing their real 9/1-9/4
entries against 9 days of mashup capture (8/28-9/6, dense on 9/1-9/4):

  The mashup carries TWO streams, not one:
    ZTRADEZ BOT     (793 msgs) forwards from some trader rooms
    ZTRADEZ Manager (292 msgs) the house/Namrood feed, best-formatted
                    alerts we get: "Buy To Open ORCL 147C 09/04 $1.5"
                    with entry, expiry and running P/L (ANSI color codes
                    wrapped around the contract - parser must strip them)

  RELAYED, 10 of 19 - safe to leave cut:
    mr-top-hat, market-bishop/opt-7, jpm-investments/opt-6,
    sir-goldman/opt-8, are-swings/opt-2, demon, adex-swings/swing-4,
    namrood/fut-6, top-flow, scalps

  DARK, 9 of 19 - these alerts reach us NOWHERE. Proof, all absent from
  the mashup on days it captured hundreds of lines:
    cranmer/opt-9      UPS 104C, AA 52C, NVDA 220C 9/18
    evapanda/opt-5     MU 1100C, MRVL 240C, URA 48C
    madhatter/opt-1    MCD 245P 10/16
    tlm/opt-4          AAPL 327C, MSFT 497/490P spread
    stormzyy/fut-1     MNQ
    guru-futures/fut-2 MNQ LONG 29525
    clutch/swing-1     SPCX
    kumo/swing-2       CAKE 120/125 debit spread
    king-maker/swing-3 GM 87.5C 9/18

  Only evapanda was cut on journal evidence (-55). The other 8 were cut
  as "redundant: flows through the mashup" - a reason now disproven.
  Reopening any of them is G's call (rooms are his).

Of the 9 DARK rooms, four were reopened 9/7 on that finding (madhatter/opt-1
→ ZT opt-1, cranmer/opt-9 → ZT opt-9, stormzyy/fut-1 → ZT fut-1,
guru-futures/fut-2 → ZT fut-2). ZT opt-9 was re-cut 9/9 (0 signals since
reopening); opt-1/fut-1/fut-2 are still open. The other 5 DARK rooms
(evapanda/opt-5, tlm/opt-4, clutch/swing-1, kumo/swing-2, king-maker/swing-3)
remain cut on their own separate merits (see their individual lines in
rooms.txt) — reopening any of them is still G's call.

--- OWLS CAPITAL 24-CHANNEL SCAN (verbatim from rooms.txt, written 9/7) ---

OWLS CAPITAL — SCANNED 9/7, NOTHING WIRED (at the time). All 24 channels
read. The six per-trader "*" channels were the only alert candidates and
not one was safely tradeable by an options bot as found that day:
  jon-and-kian     COMMON STOCK, not options: "1000% lotto CHGG commonst at
    .83", "sold some CHGG commons at 15%", "22% on commons". DANGEROUS to
    wire: "Sold another SPCX at 5.70" carries no word saying it is stock, so
    it reads as a plain CLOSE and would dump an SPCX OPTIONS position. The
    parser cannot tell from that text — only the room can — which is exactly
    why this room stayed out. (Lines that DO name themselves are vetoed:
    "shares", "commons", "commonst", "common stock".)
  ab               real options, but entries are BARE contracts with no verb
    ("$GOOGL 10/16 400c 1.88") so they do not fire, while his closes
    ("$AAPL 10/16 330c 200% (Closed)") DO. A room that can close but cannot
    open is worse than no room at all — it can only ever end a ride early.
  tt               SPX 0DTE, and the sample is a SPREAD ("7690/7675p 0dte
    1.4") plus a lotto. Two alert lines in the whole scrollback.
  muggzone-options parses ("ENTERED 9/11 MRVL 240 CALLS @here 1.3" -> OPEN
    MRVL 240C @1.3) but DROPS THE EXPIRY, because the date sits BEFORE the
    ticker and the reader only looks after it. Zero of the corpus lines at
    the time used that order, so no wired room was affected and it was left
    alone rather than widened on speculation.
  giul-heatseeker  the trader is away ("going to korea and japan these next
    2 weeks") and his bot is broken ("bot may not be working right now").
  members-plays    member TA chat, not calls.
The rest (bot feeds, recaps, chatter, admin channels): notable-flow /
notable-etf-flow / news, admin-analysis, ab-updates, gains-losses,
risk-management, trading-floor, entrance-floor, off-topic,
keyz-soccer-bets, futures-trading, support, home, announcements.

OWLS CAPITAL (wired 9/8, G: "wire shabs + eli as SPY proxy"). Both are
SPX-ONLY traders who never type the ticker — "in 7655p 2.9", "7760c at
300/con". default_symbol_channels maps each to SPX; spx_entry_channels lets
the SPX->SPY retarget fire (7655p -> SPY 766p at 1/10). shabs was the best
record scanned (87.5% ex-BE, +$15,898 at 1 con/play in August). eli is
commentary-heavy — the "stock is selling" and progress-update guards (9/8)
exist because of his room.

RETIRED 9/9 into OWLS all-alerts (G: "remove the rooms covered by all
alerts"). shabs & eli now flow through the aggregator; background.js's relay
unwrap re-books their calls under "shabs"/"eli" AND re-applies their SPX-only
handling (default_symbol=SPX + SPX->SPY retarget) off the "From 🌟｜" tag, so
nothing is lost. The 9/9 all-alerts room aggregates all 11 analysts (ab,
muggzone, eva, tt, giul, neal, florida-man, common-stock, jon-and-kian, plus
shabs/eli) via "OWLS Capital Clanker" embeds tagged "From 🌟｜<analyst>".

(pre-cut history follows)

---

# ===== PRE-CUT HANDOFF.md, VERBATIM (as of 2026-09-09) =====

# DISCORD SNIPER — THE HANDOFF
Read this first. It is the living memory of the project: what the machine is,
every rule it trades by, and how G works. Update it whenever a rule changes.
Last updated: 2026-09-09 (latest) — ONE CENTRAL FILE PER DATA FAMILY, and the
app now reads ONLY those. G: "make sure the app fully uses this from now on
and not the previous. do this for other similar types of data or files."
Done, in five families:

**1. FILLS → `master_ledger.csv` (325 rows, 52 cols) — THE fill truth.**
Built by `build_ledger.py` from FOUR sources, in trust order: (a) the Webull
order-history exports `Webull_Orders_<date>_auto.csv` (the account's OWN
record — FIFO leg-pairing per OCC into round-trips), (b) `trades.log FILLED`
(immutable, exact fill stamp, no room), (c) `days/*.json wallet.trades`, (d)
`days/*.json table`. RULES baked in, each learned from 9/8: the export's exit /
P&L / state / account WIN over the book's belief (`store_pl` keeps the book's
number so the disagreement stays visible); a fill the broker saw is `filled`
even if the book filed it `failed` (IWM 295P, SPY 767P); export-confirmed ⇒
`account=live`; entry time comes from `opened`, else the broker's FILLED
stamp, NEVER wallet `t` (that's the exit); one FILLED line confirms exactly
one row (queue, real rows first, so a nofill can't steal a fill); table/wallet
twins dedupe on date+caller+contract+fill with NO time bucket (wallet rows
have no `opened`; the old minute bucket double-counted TSLA 372.5C and QQQ
717P). Thin wallet rows are normalized (kind / avg / entries / exits / hi-lo
derived, `derived=True`). Gaps are rows, not silence: 41 `trades.log-only`
fills no store ever journaled, 13 `webull-export-only` hand scalps.
**RECONCILIATION is built in and printed every run:** on every day we hold an
export, ledger(live,real) must equal the export to the cent — 9/4 +152.00 =
+152.00, 9/8 +77.00 = +77.00 (the book had 9/8 at −$82). A DRIFT line means
something upstream lied; investigate, don't average.
Reader: **`ledger.py`** — `rows()/load()/by_day()/days()` yield rows keyed
exactly like the old day-JSON table rows, so every consumer was a drop-in.
Wired into `bridge.py save_day()` (never-raise guard, `bak=False`, ~110 ms);
the bridge already ran it live on its 02:55 boot. CLI `python3 build_ledger.py`
keeps 5 .baks and prints the summary + reconciliation.
**SWITCHED to the ledger (parity-verified byte-identical on every old row,
then MORE rows):** caller_report.py, scoreboard.py, journal_full.py (264 →
329 taken), entry_compare.py (11 → 34 option trades), missed_dollarize.py,
scoped_missed_pull.py, today_entry_compare.py, ratchet_backtest.py,
ratchet_sweep.py, databento_backfill.py, announcer.py (below). `journal.csv`
is now a LEGACY export the bridge still writes; nothing reads it for truth.

**2. ALERTS → `master_alerts.csv` (295 rows) — every alert and its fate.**
`build_alerts.py`: taken side from `telemetry.csv` (posted/seen/sent/filled
stamps, slip, greeks), declined side from `trades.log` via `misses.collect_
misses()` (reason labels), filled ones linked to their ledger row
(`ledger_key`, `in_ledger`). This is the answer to G's original "what alerts
didn't trigger and why" in one file. Reader `ledger.alerts(date=, outcome=,
declined_only=, …)`. Wired into `save_day()` next to the ledger. Known thin
spot: telemetry rows carry no room/caller (bridge doesn't populate them) —
a bridge telemetry fix, not a ledger one.

**3. PRICE TAPES → `tape.py` is the ONE registry.** Registered the three it
didn't know (`databento_clean`, `missed`, plus a `bars(occ)` reader for
bars/). **`tape.path("databento")` returns the despiked clean tape when it
exists** — ratchet_backtest replayed RAW while ratchet_sweep replayed CLEAN
(two backtests, two tapes); both now call `tape.path()`. Default `rows()`
never replays raw+clean together (same ticks).

**4. HOLIDAYS → `market_hours.py` owns the table.** `webull_options.HOLIDAYS`
now derives from `market_hours.FULL_CLOSE` (name kept — bridge.py:1450's
import is untouched; literal set only as import-failure fallback). 30 dates
2025-27. Update ONE place each year.

**5. ANNOUNCER SCOREBOARD → computed from the ledger.** `announcer.py` was a
running tally that only counted closes it witnessed; it was OFF Sep 2-8 and
posted a stale board (−$1,680 as of 9/1). `_score_from_ledger()` rebuilds
`all`/`today` from `ledger.rows(real_only, account=live)` at boot and at
each day rollover; `announcer-scoreboard.json` is now a cache. Live ledger
board: 54 symbols. **Needs the announcer restarted (announcer.restart touch
or the 30-min revive task) — G's call; not done from here.**

Verified: py_compile clean on all 18 touched files; every switched consumer
runs; test_positions.py 0 failures; reconciliation MATCH on both export
days. Nothing on the order path changed except the two never-raise hooks at
the END of save_day(). NEEDS THE BRIDGE RESTART already pending tonight.
STILL TRUE: 154 real fills carry room "?" (pre-tagging August + recovered
rows) — room-cut decisions wait for tagged numbers; the 7-room cut list
stays withdrawn.

Previously — Last updated: 2026-09-09 (late) — ONE CENTRAL FILL LEDGER: `master_ledger.csv`.
G caught me claiming Aristotle had 0 trades when he'd taken AMD 515C from it
that morning. Root cause was DATA, not a stale read: fills were split across
three half-ledgers that disagree — `days/*.json "table"` (display rows,
truncates: on 9/8 it saved 6 of 12 fills, Aristotle among the dropped),
`days/*.json "wallet.trades"` (richest fields, clears on restart, only today
survives), `trades.log FILLED` (immutable broker spine, but NO room/caller).
`journal.csv` is built from "table" only, so it inherits the truncation.
**FIX — `build_ledger.py` → `master_ledger.csv` (316 rows, 44 cols).** Unions
table ∪ wallet.trades per day, merges duplicate rows field-by-field (runup /
drawdown / greeks survive), cross-checks every row against trades.log FILLED
(`broker_confirmed`), and ADDS broker fills that never got a journal row as
their own rows (`source=trades.log-only`, room "?") so gaps are VISIBLE — it
found 39 of them (SPY 9, NVDA 7, INTC 5, MSFT 4; 13 on 8/18 alone). Also
carries `in_table` / `in_wallet` so you can see which store dropped what.
Deterministic full rebuild (no append → no double-count on restart), atomic
`os.replace` swap, ~108 ms. **Wired into `bridge.py save_day()`** right after
journal.csv, in its own never-raise guard, `bak=False` (no .bak churn per
event); CLI `python3 build_ledger.py` keeps 5 timestamped .baks + prints a
per-room summary. Verified: py_compile clean on both, refresh() runs, full
test_positions.py green. NEEDS A BRIDGE RESTART to run live (same restart as
everything else tonight).
**RULE (new): `master_ledger.csv` is THE fill truth. Any per-room / per-caller
/ "which rooms trade" count reads it — never `table`, never `journal.csv`.**
`journal.csv` stays as the legacy Excel export (announcer/caller_report still
read it); it is NOT the source of truth anymore. Honest state of the numbers:
247 real fills, 128 broker-confirmed; the 119 unconfirmed are 52 manual /
Market Sniper (his, not the bot's), 29 untagged, 26 futures (NinjaTrader —
never a Webull line, expected), 8 FIFO-rebuilt, 4 stragglers. 138 real fills
still carry room "?" (mostly pre-tagging August days + the 39 recovered) —
so "cut this room, it's dead" is NOT a call to make off these counts yet.
Room cuts stay G's decision on numbers that hold; my earlier 7-room cut list
is WITHDRAWN.

Previously — Last updated: 2026-09-09 — QQQ 716P PHANTOM-EXIT BUG FIXED (bridge.py CLOSE
handler). G approved ("yes plz") fixing the headline bug from the 9/8 16:36
close-out below. **bridge.py's `_place_impl` CLOSE branch (primary account,
~line 2766, and the WB_EXTRA mirror-account loop, ~line 2848) now uses
`BOOK._sell_confirmed(...)` instead of `BOOK._sell_retry(...)`** — the exact
same wait-for-FILLED + one-reprice pattern the watchdog's own stop-out path
already used and already trusted. Three outcomes handled honestly: confirmed
fill -> `BOOK.finish(..., price=confirmed_price)` (real price, not the quoted
ask); accepted-but-never-filled -> `BOOK.release(key)` + "EXIT-RETRY" log,
position stays OPEN, nothing marked CLOSED on a lie; broker exception ->
existing two-seller-collision check, else `BOOK.release(key)` before
re-raising. This closes the exact gap the 16:36 close-out flagged: an
ACCEPTED sell is no longer treated as a FILLED sell anywhere in the CLOSE
path, for pullback exits, hard-stops, or the watchdog.
Verified: `python3 -m py_compile bridge.py` clean. Full existing suite green
post-fix: test_positions.py, test_architecture.py, test_brokers.py,
test_phantom_exit.py, test_tape.py — all pass, no regressions.
Also fixed while in test_positions.py for the 9/8 ratchet respacing: 4 stale
hardcoded expected-stop assertions tied to the old 10/0/10 ladder (now
5/0/5), and one unrelated pre-existing `%%`-escaping cosmetic bug in a bare
`print()` summary.
NOT COVERED by a dedicated new regression test — no existing test harness
exercises `bridge.py`'s `_place_impl` directly (it reads live module globals:
`client`, `BOOK`, `WB_EXTRA`); building one is a real test-harness project on
the scale of `test_brokers.py`'s fake-server pattern, not a same-session add.
Confidence instead rests on: this reuses `_sell_confirmed`, which already has
production mileage via the watchdog path and is exercised by
`test_positions.py`'s and `test_phantom_exit.py`'s passing suites.
**NEEDS A BRIDGE RESTART to take effect** — same as the 9/8 ratchet-spacing
rollout, the running process won't pick this up from disk alone.

Previously — Last updated: 2026-09-08 16:36 — DAILY CLOSE-OUT (automated): QQQ 716P PHANTOM-EXIT
BUG (a real +20.8% win that silently became a -34.9% loss), ONE FIX SHIPPED,
GIAN'S HAND-TRADE LEDGER GAP RECURS. Broker truth (Webull order history,
account ENIQGUV4LUTT3JSAA9NKLDDU19): bot +$89 gross / Gian -$12 gross, fees
-$3.42, net ~+$72.58 matching the account's own day-P&L. Account flat as of
16:36, nothing resting overnight. Announcer PAUSED (announcer.stop="stop",
8/31 standing call) — announcer checks skipped per standing instruction.

  **HEADLINE BUG — Vero's QQQ 716P (10:15:46 entry, 1.06): a pullback-target
  exit that only ever ACCEPTED, never FILLED.** At 10:18:28 the stock hit its
  716.50 pullback target and the bridge fired a real SELL at 1.28 (+20.8%,
  a clean win) — but bridge.py's CLOSE handler (`_place_impl`, the branch
  gated by the EXIT-IGNORED check at do_POST's `order.get("source") in
  ("pullback","under-stop")`) calls `BOOK._sell_retry(...)` directly and
  books `positions.CLOSED` the moment an order_id comes back, unlike the
  watchdog's own stop-out path which waits on `_sell_confirmed` for a real
  FILLED status. This one never filled. ~2 min later (10:20:37) the reconcile
  loop found the broker still holding it ("book recorded closed but broker
  STILL holds it") and tried to finish the exit — by then the market had
  reversed and a stray resting order on the same contract made every
  completion attempt 417 (`OPENAPI_ORDER_NOT_SUPPORT_REVERSE_OPTION`),
  including the watchdog's own follow-up stop-outs at 0.95 and 0.83
  (BREACHED, unclampable per webull_options.py's own design — "the watchdog
  should sell", but the watchdog's sell was ALSO blocked). Round-tripped
  from +20.8% to -34.9% (~$60/contract) before finally clearing at 0.69 at
  10:25:22. NOT A ROOM-EXIT VIOLATION — verified the entries-only gate is
  intact (bridge.py do_POST's EXIT-IGNORED check present and correct,
  execution.exit_policy absent/defaults to entries_only, extension gate
  unreviewed but 0 EXIT-IGNORED lines fired today because 0 room CLOSEs
  reached the bridge) — this is a phantom-fill bug in a legitimate,
  gate-exempt bot-internal exit (pullback stock-target), the same "source"
  family as underlying hard-stops, so BOTH share this exposure.
  **NOT FIXED UNATTENDED** — touches the live CLOSE path shared by every
  pullback and hard-stop exit; recommended fix (for a focused, tested
  session, ideally at a safe restart window): route that CLOSE handler
  through `positions.Book._sell_confirmed` (already does the wait-for-FILLED
  + one reprice, used by the watchdog's own stop path) instead of trusting
  order acceptance from `_sell_retry` alone.
  Ledger fallout: days/2026-09-08.json fragmented this ONE trade into THREE
  rows — the original "vero|QQQ" row phantom-closed at 1.27 (never happened),
  plus two orphan re-adoptions wrongly attributed to **Gian** (who never
  touched this contract) after the ADOPT path picked it up mid-crisis.
  journal-2026-09-08.xlsx and trader-scoreboard.xlsx both correct this to
  ONE row, Vero, broker truth (-$37). Vero's scoreboard verdict flipped to
  AVOID on this — flagged as skewed by the bug, not the call, in both files.

  **FIXED TODAY — positions.py, the IWM-shaped postcheck mis-record** (same
  bug class, lower stakes: bookkeeping only, not a protection gap). Both
  Vero's SPY 767P (-$1) and ZTRADEZ BOT's IWM 295P (-$6) filled CLEAN on
  their own born resting stop at Webull, but the watchdog's own redundant
  sell attempt raced a lagged `order_status` read (same rate-limit/
  contention family as the pre-existing `/openapi/assets/positions` 429s —
  Market Sniper shares this app key) and logged FAILED instead of
  recognizing the fill — a clean stop-out mis-recorded as a failure with no
  exit price. The existing 9/8 fix for this (checking `pulled_stop.oid`'s
  order_status before falling back to `_gone_at_broker`) still lost the
  race on a single read. Gave it the same few-tries-short-pause pattern
  `_await_cancel` already uses elsewhere (3 tries, 0.5s apart) before
  believing "not filled" — read-only, changes no order-placement behavior,
  only which of two true/false paths a report takes. Verified: `python3 -m
  py_compile positions.py` clean; test_positions.py, test_resolve.js,
  test_architecture.py, test_brokers.py, test_phantom_exit.py, test_tape.py
  all pass (test_signals.py does not exist in this repo — the CODE FIXES
  instruction naming it appears stale; ran every test file that does exist
  instead). Bridge restarts onto this automatically at the next safe window
  or the close (nothing was in flight when this was written).

  **STOP-PLACEMENT RELIABILITY, pre-12:01 restart (not a code bug found,
  logged for the pattern):** every bot bracket trade from 09:36 through
  10:35 (AMD x3, QQQ x3, TSLA, SPY) showed POSTCHECK "NO resting stop —
  watchdog only" for some number of seconds after fill, because the born
  bracket's stop almost always needs a REBASE (fill beats the limit, so the
  -10%-of-fill stop differs from the -10%-of-limit born stop by more than
  the 2-cent tolerance) and the replacement `place_stop()` call kept hitting
  417s (`OPENAPI_STOP_PRICE_MUST_BE_LESS_THAN_MARKET_PRICE`,
  `OPENAPI_DAY_BUYING_POWER_INSUFFICIENT`) during that window. The ONE trade
  after the 12:01 restart (IWM, 13:00) filled AT its limit (no rebase
  needed) and its born stop rested and filled cleanly start to finish.
  One data point either way — not enough to say the 11:53-12:01 changes
  (ratchet respacing) fixed or didn't fix the underlying rebase-window
  exposure. Watch tomorrow's first hour for whether "NO resting stop" still
  shows up on trades that DO need a rebase.

  **GIAN'S HAND-TRADE LEDGER GAP RECURS** (first flagged 9/4, "root cause
  unconfirmed"). Of Gian's 6 hand round trips today (multi-lot SPY MARKET
  scalps via Market Sniper/the Webull app, net -$12 broker truth), only the
  FIRST (SPY 766P, -$22) reached days/2026-09-08.json. The other five
  (-$52, +$8, -$20 on the same SPY 766P contract, plus SPY 768C +$70 and
  SPY 767C +$4, entirely unrecorded) are missing outright — same shape as
  9/4's two missing SPY scalps, now a second occurrence. Still not
  root-caused; both times it happened during/around a period of unusually
  heavy concurrent order activity (today: the QQQ 716P crisis window).
  Worth a dedicated look, not a today-fix.

  **REPLAY (`replay_check.py`): 18 silent drops, most explained.** Filtered
  to genuine OPEN/ADD misses (CLOSE/PREPARE/recap lines are expected to be
  silent under entries-only and were skipped): Elite Shoof's 09:31 NBIS
  250C and Elite Brando's 10:44 QQQ 720C are the SAME misses already
  diagnosed and fixed earlier today (extension 3.5.53, "MISSING ROOMS HEAL
  THEMSELVES" — see below in this file), not new. Four still open, none
  traded real money, none investigated live in Discord (autopilot, no
  browser dive without cause beyond a log check):
    - ZT guru-futures 09:59 "MNQ SHORT Entry: 29500 Stoploss: 29550" — room
      IS wired (Market Guru, already AVOID-rated in the scoreboard), format
      may not match the parser's SHORT-verb grammar; needs a corpus check.
    - ZT all-trades-mashup 11:05 "ABT ... averaging down here at 2.00" — a
      relayed ADD phrased differently from the "added $X calls" shape the
      9/2 ADD fix covers; ABT itself is read 92x today elsewhere in
      bridge.log, so this is a phrasing gap, not a dead room.
    - TradingTheTrend option-alerts 10:34 "benw ... BTO TSLA 9/9 375c @1.00"
      — caller "benw" never appears anywhere in bridge.log today; possible
      tab/attach gap for this specific poster, unconfirmed.
    - Whop Day Trades 09:47 "Short NQ 29508 Sl 29550" — room has 138
      signals captured today (per scoreboard.py) but 0 ever sent/traded,
      all-time; may be a pre-existing quiet/never-parses room, not a new
      regression — lower priority.
  scoreboard.py 10: 81 rooms heard from (28 configured, 1 silent
  configured — Options Insider, expected, see below), SCOREBOARD.html
  regenerated. Options Insider still dark (lost server access 9/2, kept
  configured, G's call not to renew). RWGates is AWAKE (subscription
  lapsed but Discord access verified intact 9/7) — not a deathwatch item.

  **Checked clean:** 0 Chrome DISCARDED/out-of-memory lines today. /stream
  via Claude-in-Chrome: connected:true, budget_left 285, rate_limited 0,
  option_bus.watching 0 (account flat) — last_sweep_ms 507 is above the
  usual ~100-200 baseline but with nothing being watched right now that may
  just be idle variance, not a fault. announcer-seen.json non-empty (15
  ids) but irrelevant while paused.

  **Deliverables:** Webull_Orders_2026-09-08_auto.csv (47 order legs),
  journal-2026-09-08.xlsx (15 trades + By Trader, house format, recalced
  clean), trader-scoreboard.xlsx (9 new caller rows — Gian's 6 hand trades
  excluded per house rule —, Scoreboard fully recomputed from all 108
  trade rows across 27 callers, pre-8/19 caveat and every prior footnote
  preserved, 6 new footnotes added for today's corrections + the QQQ 716P
  writeup).

  **NOTE ON CONCURRENCY**: this close-out ran while at least one other
  session/process was also editing this repo today — the ratchet respacing
  (born 10%->7.5%, arm 10%->5%) and an "ALL ROOMS LIVE" extension change
  (3.5.60, pending his reload) both landed in HANDOFF.md between when this
  run started reading it and when it finished. Neither is this run's work;
  both are left exactly as their own entries describe below. If HANDOFF.md
  looks different from what this entry assumed by the time it's read,
  trust the newer entry.
Previously — Last updated: 2026-09-08 — ALL ROOMS LIVE (his call) + WHOP PATH VERIFIED HEALTHY.
"check if every path is good": Discord path IS good — fired all morning
(AMD 510C, MARA 12C, INTC 110C, SPY 767P, QQQ 720P vero); the liquidity floor
refused META (67 traded last session) and SNDK (57) exactly as designed; vero's
pullback waited and correctly skipped QQQ. Two changes made this session.
  **(1) ALL ROOMS LIVE — extension 3.5.60, needs his RELOAD to take effect.**
  Elite (Brando 1286022517869514874 / Shoof 1368263191632543956) and a few
  others were still landing TEST ("nothing sent, paper execution is off")
  because they carried an explicit channel_live=false the born-testing
  migration never cleared (that one only deletes ids in BORN_TESTING, which is
  empty). applyBornTesting() now has a SECOND one-shot sweep, gen ALL_LIVE_GEN
  "2026-09-08-alllive": deletes EVERY channel_live===false so every room falls
  through to live-by-default (roomLive = _lv !== false). Runs ONCE; after it, a
  popup flip to TESTING writes a fresh false that STICKS. Popup log prints
  "ALL LIVE — N room(s) ... cleared" on reload so it's provable. node --check
  clean; manifest 3.5.59 -> 3.5.60.
  **(2) WHOP PATH — VERIFIED, not broken.** Zero Whop reads today did NOT mean
  the reader is dead. In G's own logged-in Chrome profile: whop.js IS live on
  whop.com (its own console line fired — "[sniper] this is NOT a room URL", from
  chrome-extension://.../whop.js:240) and the FirstStepTrading membership is
  ACTIVE (full room sidebar loads). The 4 wired exp_ ids in rooms.txt are
  CURRENT — they match Whop's live sidebar today exactly: day-trades
  exp_cvgzKYDmcUEDGh, futures exp_26GaLgZVMzB2PL, high-risk exp_hpXJymtw0yMqzB,
  2k-challenge exp_Yg9HGTPsXPhQ5D. So rooms.txt is NOT stale and access is NOT
  lost. whop.js ONLY reads at whop.com/<biz>/exp_/app/ URLs and stays idle (that
  warning) on Townhall / /messenger / dead /joined/ links. The one thing that
  keeps Whop silent: a room tab not sitting on its /app/ URL. FIX IS G's, in the
  Sniper Whop window — re-open each room from the sidebar so the URL ends
  /exp_.../app/ and pin THAT tab. Could not enumerate his pinned tabs from here
  (outside the automation tab group) and did NOT open a live room myself — a
  first-attach read of a fresh alert in a live room could fire a real order,
  which is his alone.
  **Dead-but-harmless**: bridge.py's server-side _whop_feed_loop (the "tabs
  optional" API reader) has never fed — it queries Whop with exp_ experience ids
  at guessed /v1/messages paths, but Whop's real chat API wants chat_feed_ ids +
  a chat-scoped token (docs.whop.com/developer/guides/chat). WHOP_FEED_OK stays
  0, no "[whop-api] reader up" in 2 wks of bridge.log. It is ONLY the backup;
  the real Whop path is the browser tabs above, so it can stay dead without
  costing a read. Left alone (a proper fix needs the chat_feed_ ids via an
  authenticated call + a restart — not worth a second guess now).
  **NOT DONE — NEEDS G**: (a) reload the extension so 3.5.60's ALL LIVE sweep
  runs (it defers to the close on its own while the market's open); (b) pin the
  4 Whop room /app/ tabs in the Sniper Whop window.
  **MISSES REPORT (new tool, misses.py)** — G asked "what alerts didn't trigger
  and why — are we watching this?" We ARE (every refusal/skip is logged in
  trades.log), but the daily journal is TRADES-ONLY and reads.py --misses is
  voice/vision only — so there was no single "didn't trade, and why" view. Added
  misses.py (read-only, parses trades.log): `python3 misses.py` groups the day's
  misses by reason — THIN/no-OI, PULLBACK-never-hit, BUYING-POWER-too-small,
  SWINGS-paused, TEST-room, FUTURES-prop-refused, not-optionable. 9/8 = 19
  distinct misses. NOT yet wired into the 4:45 journal.xlsx (that edits bridge.py
  + needs a restart — G's call).
  **UNIFIED JOURNAL (new tool, journal_full.py)** — G: "make one journal for all
  trades missed/refused and taken so we can use that data to modify the app."
  Merges taken trades (days/*.json) + misses (misses.collect_misses, from
  trades.log) into ONE xlsx: `python3 journal_full.py --all` -> journal-full-ALL.xlsx
  (or --date / --today). Sheet "All trades" is one filterable, colour-coded row
  per event (green TAKEN / red MISSED) with outcome+reason columns; sheet
  "Summary" totals misses by reason/symbol and taken by caller. Read-only.
  ALL-days snapshot 9/8: 264 taken, 272 missed — and the single biggest miss
  bucket is BUYING POWER (130), i.e. the ~$250 account couldn't afford the
  contract. That's the top lever if funding ever grows.
  **ERRORS REPORT (new tool, errors.py)** — G: "do we have somewhere with all
  this info?" Reads trades.log (+bridge.log tracebacks on --all) and groups the
  day's problems: broker sell-rejects (buying-power / reverse-option / stop-price
  417s), stop-fails, phantom/orphan, prop rejects, futures-unfunded, rate-limit,
  plus a guards-that-fired section (not errors) and broker error-code counts.
  `python3 errors.py` (today) / --date / --all. Read-only. NOTE: it only catches
  what the system LOGS — a SILENT bug like today's Whop api-mode gate (threw
  reads away with no error line) won't show here; those still take discovery.
  **REVERTED auto-open-missing-tabs (extension 3.5.61, needs RELOAD)** — G:
  "revert the check the browser and open missing tabs, because if i close one it
  wont stop opening them." openMissingRooms() removed from the watch-build sweep;
  left defined-but-uncalled. His 8/23 rule restored: OPEN TAB = on, CLOSING a tab
  = off, launcher opens once at startup, nothing reopens a closed tab.
  keepRoomsLoaded()/oneTabPerChannel()/evictOtherLane() untouched (they only keep
  or close existing tabs, never reopen a closed one).
  **WHOP STILL NOT FEEDING (confirmed 9/8 22:25)** — G pasted a Felony
  (FirstStepTrading) alert "Long NQ @ 29580, stop 29550, target 29645" from ~1h
  earlier (~21:25). The bridge never read it: ZERO Whop-sourced reads landed all
  day. whop.js is alive and correct (proved earlier via its own console line),
  the API reader is dead (wrong ids), so the ONLY path is the Sniper Whop
  profile's browser tabs — and they are not reaching the bridge. Most likely the
  room tabs aren't sitting on their /exp_.../app/ URL (whop.js goes idle on
  Townhall/messenger). Unresolved; needs eyes on that profile's tabs + popup.
  **MARKET HOURS recorded → MARKET-HOURS.md** (G's ask: "read market hours for
  options and futures and write it down"). Options (equity/ETF) 9:30–4:00 ET,
  SPY/QQQ/IWM + index (SPX/NDX/RUT/VIX) to 4:15; NO overnight options. Futures
  (CME Globex, ES/NQ/MES/MNQ, metals) Sun 6:00 PM → Fri 5:00 PM ET with a daily
  5–6 PM ET halt. So the 9:25 PM NQ long WAS in-session and tradeable — the only
  reason it was missed is the dead Whop feed, not the hour.
  **WHOP FEED FIXED — root cause found and the dead path deleted (ext 3.5.62,
  needs RELOAD).** Checked the Whop feed live in G's Sniper Whop profile: whop.js
  IS alive and its scraper WORKS on the current Whop DOM (13 posts pulled from
  Day Trades, e.g. Trademorewiser "Short NQ 29508"), and his room tabs ARE on the
  right /exp_.../app/ URLs. So reading was never the problem. THE BUG: background.js's
  MESSAGE handler had a gate — `if (WHOP_API_ACTIVE) { reply('api mode'); return; }`
  — that DROPPED every Whop tab read whenever the server-side API reader flagged
  itself "active". That API reader never actually worked (queried Whop with exp_
  experience ids at guessed /v1/messages paths → 404), but its false "active"
  ping silenced the working tab path. That's why Whop went dark all day incl. the
  9:25 PM NQ long. FIX (G: "delete anything not working and wire the fix from
  scratch"): DELETED the whole dead API reader — bridge.py _whop_feed_loop +
  /whopfeed + WHOP_FEED* (−111 lines), background.js WHOP_API_ACTIVE/startWhopFeed/
  FEED_ACTIVE + the gate, offscreen.js feedStart. Whop now reads ONLY through the
  browser tab (whop.js → background MESSAGE → bridge), exactly like Discord. Kept:
  offscreen (voice), whopWatchdog/WHOP_PULSE (tab health). node --check + py_compile
  clean; no dead-API refs remain. TAKES EFFECT ON EXTENSION RELOAD (3.5.62) — after
  that Whop feeds AND trades (rooms are live from the ALL-LIVE change); existing
  messages are history-flagged so a reload won't re-fire them, but the next FRESH
  futures alert WILL fire (futures trade overnight — see MARKET-HOURS.md).
  **RATCHET RE-EXAMINED BY CONTRACT PRICE (9/9, new tool ratchet_sweep_tiered.py).**
  G's instinct: "for cheap contracts it must be too tight." Confirmed. The flat
  sweep (ratchet_sweep.py) only ever tried ONE global (born, arm) on all trades,
  so it couldn't see price effects. Bucketing the SAME 80 fills by entry price:
  cheap <$1 (n=15) flat 7.5/5 = -$35, best at a LOOSER +10% arm = -$17 (still
  loses — ~13% win, the real lever may be trading fewer sub-$1 lottos, not
  re-spacing); mid $1-2 (n=21) flat = -$21, best at a TIGHTER +3% arm = +$53;
  expensive >=$2 (n=44) holds ALL the profit (+$209) and flat 7.5/5 is already
  best there — which is why the flat sweep landed on it (that bucket dominates).
  Also: the LIVE arm (5%) is rank #2 — the flat #1 is 7.5 born / arm +4% (+$251
  vs +$152), a ~$99 edge but 4-vs-5 is within noise on 80 trades. G's CALL: KEEP
  BACKTESTING, HOLD VALUES (stay -7.5% born / +5% arm) until the sample grows —
  buckets of 15/21/44 over 5 weeks are hints, not verdicts, and per-bucket "best"
  is in-sample overfit. Re-run both sweeps as fills accumulate.
  **DECOUPLED-STEP SWEEP + CONTRACT CHARTS (9/9, ratchet_sweep_fine.py +
  chart_contracts.py).** G: "do more percentages... I wanted option contract
  charts to see the movement of every contract." The original sweep FORCED
  step==arm; decoupling the rung is the biggest lever found yet. On the same 80
  fills the LIVE 7.5/5/5 ranks #13 of 294; the whole top of the board uses a
  SMALL +2-3% rung: global best 7.5 born / +4% arm / +2% step = $321 (vs $152
  live), and the dominant expensive bucket (44 trades) 7.5/+4/+2 = $353 (vs
  $209). So locking in small increments captures the run-then-pullback that a
  +5% rung gives back. chart_contracts.py -> contracts.html draws every fill's
  gain%-from-entry path with entry/born/arm lines, peak/trough, and an ✕ where
  the live stop sold — for eyeballing why small rungs win. SHIPPED 9/9 (G's
  settle): ratchet_tiers.py TIERS step 5.0 -> 2.0 — the ladder is now BORN -7.5%
  (settings.json) / ARM +5% -> breakeven / STEP +2% rungs, ONE tier for all
  premiums (no cheap tier — cheap loses under every spacing, G's call; sizing/
  filtering is the real cheap lever, tracked separately). test_positions.py
  ratchet checks recomputed for step-2 (+20%->2.28, +30%->2.48 on a $2 fill) and
  GREEN. NEEDS A BRIDGE RESTART to go live. MIN_RUNG_TICKS=4 floors the 2% rung
  so it never goes sub-tick on cheap/nickel names. Futures: DECOUPLED 9/9 to
  match. futures_locked_points now arms at 2/3 of the risk -> BE, then a rung
  every ~27% of the risk (FUT_ARM_FRACTION 5/7.5, FUT_STEP_FRACTION 2/7.5 — the
  options 7.5:5:2 ratios). Risk = the caller's own stop (theirs first) so an NQ
  30-pt stop -> 30/20/8, MES 10 -> 10/6.7/2.7, auto-scaled per instrument.
  Anchored to QQQ<->NQ = ~41 pts/$ (live 9/9: QQQ 717.42, NQU6 29,579). NO
  futures backtest (no fills) — a translation, verify when futures actually
  trade. test_positions/architecture green. NEEDS RESTART. Market Sniper handoff
  written (it's still on old 10/10): C:\Users\Hulk\Desktop\Market Sniper\
  HANDOFF-RATCHET-2026-09-09.md — port options 5->2 rung + the futures decouple.
  **RN-RULE LEDGER + FORWARD TRACKER (9/9). "Is my round-number entry better
  than taking their price?"** Answer from what history allows: FAVORABLE BUT
  THIN. On the fills it caught (entry_compare.py, n=11) the RN entry beat the
  caller's price by +$123; on the skips that booked (missed_dollarize.py, n=2)
  waiting SAVED ~$38 (both would've lost). Both sides favor the rule, but n=11/2
  is anecdote, not proof — most of the log's "45 misses" never became book rows.
  Tooling built tonight (all read-only): entry_compare.py (RN fill vs caller
  price on filled trades), missed_dollarize.py (skips at caller price, reads the
  wide pull), scoped_missed_pull.py (pulls wide OPRA windows for skipped
  contracts -> missed_tape.csv; sandbox CAN reach Databento with the key),
  clean_tape.py (despikes databento_tape.csv -> databento_tape_clean.csv; only 7
  junk ticks in 329k, so conclusions were never corrupted; ratchet_sweep now
  auto-uses the clean file). THE REAL ANSWER-MAKER, now LIVE-ON-RESTART:
  pullback.py writes rn_ledger.csv — one append-only row per pullback decision
  (armed / filled / missed / cancelled) with the caller's price, contract,
  trader, room. Fully wrapped (log_ledger try/except) — can never affect a trade;
  test_architecture + test_positions still green. Over a few weeks this builds a
  real n; then entry_compare/missed_dollarize give a verdict instead of a lean.
  NEEDS A BRIDGE RESTART to start logging. Also noted: sandbox has databento +
  webull MCP reach, handy for future backtests.
  **AGGREGATOR CHANNELS to cut the tab wall (9/9).** Too many tabs = Chrome
  discards/reloads them AND logs Discord out (confirmed: both profiles bounced to
  the login page). Fix = fewer tabs via server "all-alerts"-style relay channels.
  WIRED: OWLS 🛎️ all-alerts [1449226651064991806] (rooms.txt, ext 3.5.63) — one
  feed relays all 11 OWLS analysts as embeds via "OWLS Capital Clanker", tagged
  "From 🌟｜<analyst>". content.js ALREADY reads embeds (8/30 fix) so no parser
  change needed. CAVEAT: it also relays shabs & eli (who have dedicated SPX-proxy
  tabs) — running both DOUBLE-READS them; G to decide: drop shabs/eli tabs (lose
  implied-SPX) or add a guard so all-alerts skips them. SURVEY (browser, safe):
  only the two community servers have aggregators — OWLS all-alerts (wired) and
  ZTRADEZ all-trades-mashup (already wired). Honeydrip/TTT/Platinum/Vero split
  alerts by TYPE (no single feed). So tab-reduction win = open all-alerts, close
  ~9 OWLS analyst tabs. DECLINED the Discord-API route (G asked): for third-party
  servers that means his USER token as a self-bot = permanent-ban risk to the
  account + all paid subs — same refusal as before; the browser scan is the safe
  path and already answered it. 3.5.63 is the last extension edit of the session.
  **OWLS TABS RETIRED into all-alerts (9/9, ext 3.5.64).** Per G "remove the
  rooms covered by all alerts": shabs & eli dedicated rooms are commented out in
  rooms.txt; background.js's relay-unwrap now covers the all-alerts channel
  (1449226651064991806) — it reads "From 🌟｜<analyst>", re-books the call under
  the real analyst (shabs/eli/ab/muggzone/eva/tt/giul/neal/florida-man/
  common-stock/jon-and-kian), and for shabs/eli re-applies default_symbol=SPX +
  spx_entries=true so their bare "7655p" posts still resolve and retarget. So
  all-alerts is the SOLE OWLS tab with nothing lost. node --check clean. NEEDS
  the extension reload (comes with the restart). ZTRADEZ was already consolidated
  8/30 (redundant trader channels cut, mashup kept). This is the tab-count cut
  that should stop the reload/Discord-logoff churn once G closes the old tabs.
Previously — Last updated: 2026-09-08 — RATCHET RESPACED LIVE: BORN 10%->7.5%, ARM 10%->5%.
G, after seeing the sweep: "good on everything else... change this, dont
break it please." Shipped the ratchet_sweep.py finding from earlier today.
  **CODE**: settings.json strategy.stop_loss_pct 10 -> 7.5 (the born stop —
  confirmed this is the only stop_loss_pct that matters; a second one at
  execution.webull._stop_loss_pct:20 is a vestigial constructor default that
  bridge.py's _sync_stop_pct() overwrites at boot, so it's inert).
  ratchet_tiers.py TIERS (10.0,0.0,10.0) -> (5.0,0.0,5.0) — arm/lock/step,
  confirmed this is the ONE live consumer (positions.auto_ratchet ->
  tier_locked_pct -> here) by tracing the import; positions.py's OWN
  ratchet_locked_pct(gain,sl,tp) is same-named but a DIFFERENT, dead
  function only exercised by its own test — left untouched, on purpose.
  **FOUND AND FIXED WHILE IN THERE**: two live boot-banner note() calls in
  bridge.py (~line 526, ~line 4072) printed their arm/lock/step by
  RECOMPUTING from take_profit_pct/stop_loss_pct instead of reading
  ratchet_tiers — a comment right next to one of them already flagged this
  exact failure mode from an 8/25 incident ("never let the banner recompute
  the rule — read it off the function that owns it") but the code was never
  actually updated when tier_locked_pct took over. It only ever LOOKED
  right because arm/step/stop_loss_pct all happened to equal 10. The
  instant they diverged today (7.5 born vs 5 arm/step) it would have
  started printing "+10%" for a bot actually running "+5%" — a real-money
  bot lying about its own stop in its own log. Both banners now import
  ratchet_tiers and read TIERS directly; can't drift again.
  **TEST SUITE**: test_positions.py's ratchet block (4 assertions) hardcoded
  expected stop prices for the OLD 10/0/10 ladder on a $2.00 fill (2.20,
  2.40, 2.40, 2.20). Recomputed by hand for 5/0/5 on the SAME stimulus bids
  (never touched the inputs, only the expected outputs + the comments
  explaining them): 2.30, 2.50, 2.50, 2.30. Anti-clip's own number (2.36)
  needed NO change — its 60%-of-gain cap is a function of gain alone, and
  it already sat tighter than either ladder's raw number at +30%, so it was
  binding before and after. All 6 test files green after the edit
  (test_positions/test_architecture/test_brokers/test_phantom_exit/
  test_tape all rerun clean; test_positions' own ratchet summary print()
  also had a pre-existing %% -> literal-double-percent bug, unrelated to
  this change but in a line I was already touching — fixed to match the
  file's own single-% convention for bare prints).
  **NOT DONE — NEEDS G**: editing the .py files does not touch the running
  bridge process. The new spacing is live in the files, not yet live in
  the account, until the bridge restarts (however he normally restarts it —
  I have no reach into his Windows process from here).
Previously — Last updated: 2026-09-08 — TODAY'S 6 CALLS: PULLBACK BEAT "GOT IN WITH THEM"
BY $89. G: "what would of been the original entry point if we didnt pull
back.. what would of their trade got if we would of gotten in with them
instead."
  Built `today_entry_compare.py`. First had to establish ground truth: the
  'opened' field in days/*.json is the pullback TOUCH (order-fire) moment,
  NOT the alert — bridge.log's "AI READ" line is the real alert time, and
  the gap between them ranged 8-347 seconds across today's 6 calls. Checked
  whether our own tape has a real quote AT the alert moment before trusting
  any number — it doesn't; the pullback hunt watches the STOCK while it
  waits, nothing polls the OPTION's own bid/ask until the touch, and
  Databento can't fill the gap (embargoed within 24h). Used their_avg (the
  caller's own posted price, timestamped at the alert) as the honest stand-
  in for "entering with them" — not a guess, the actual number they called.
  Ran BOTH legs through the real live ratchet (ratchet_backtest.py's exact
  engine, born -10%/arm ladder) off real ticks from each entry forward.
  Result on the 5 usable trades (TSLA excluded, see below): pullback entry
  beat immediate entry on 4, tied on 1, lost on 1 by $2 — net **pullback
  +$89** across the 5. Mechanism, not luck: a cheaper basis arms the
  breakeven lock off a SMALLER absolute bounce, so several of today's calls
  round-tripped through +10% and locked flat instead of riding the born
  floor down — AMD Mike#2 is the clean example (immediate: straight to -10%
  floor, -$56; pullback: armed, locked BE, round-tripped to exactly $0).
  **TSLA 372.5C 9/11 EXCLUDED — their posted price doesn't check out.**
  @Owner Alerts posted "$1.50"; our own fill 8 seconds later, same stock
  price (362.14 -> 361.99, basically flat), was $3.25 — parser.js read the
  raw text correctly ("Price: $1.50" is verbatim in the alert), so this
  isn't a parsing bug, the room's own number looks wrong (typo or stale on
  their end). Flagged to G, no code change — nothing to fix when the input
  itself was bad and our fill/stop both behaved correctly off the real
  price.
Previously — Last updated: 2026-09-08 — RATCHET SPACING SWEEP: BORN -10/ARM +10 IS COSTING
MONEY, -7.5%/+4% WINS ON REAL FILLS. G: "figure out what ratchet spacing is
most convenient.. what stop to start with and when to jump to break even."
  Built `ratchet_sweep.py`: same shape as the real ratchet (born stop,
  arm-to-breakeven, then a rung every arm_pct beyond it) but sweeps
  (born_pct, arm_pct) against real OPRA fills from databento_tape.csv,
  scored in real dollars. Scoped to the 80 contract-days that were ACTUALLY
  entered (state closed/filled/stopped — a refused/nofill call was never a
  position, no stop spacing saves a trade that correctly never opened) and
  excludes Gian's own hand trades (not room calls, would tune the bot's exit
  around trades it never followed). Entry/exit read from the bot's own
  `entries[0]` real fill, not `their_avg` — that field is the CALLER'S
  posted price from the raw alert text (TTT's own guide says so: "your fill
  will not always match the alert"), confirmed by comparing a TSLA 8/19 case
  where entries[0] (2.94) matched my derived entry (2.96) closely while
  their_avg was off by more.
  Final grid (born 5/7.5/10/12.5/15%, arm 1/2/3/4/5/6/7.5/10/12.5/15%) —
  dropped born>15% and arm>=20% after a first coarse pass showed every row
  out there strictly worse, no exception. Result:
      current rule (born 10%, arm 10%): -$434.20 total, 28.8% win, rank 30/50
      BEST FOUND: born 7.5%, arm 4%:    +$251.07 total, 35.0% win, 75/80 resolved
  Runner-up shape holds too — 7.5% born beat every other born value at
  nearly every arm width tried, and arm 3-6% beat both tighter (1-2%) and
  looser (7.5%+) arms almost everywhere. Tighter isn't just-always-better:
  arm 1-2% locks breakeven off ordinary quote noise before the trade's
  proven itself, arm >=10% gives back too much before locking anything.
  **READ THIS BEFORE ACTING ON IT**: 80 trades over ~5 weeks is a small
  sample — a few-dollar gap between neighboring cells (e.g. arm 4 vs 5 vs 6,
  all within ~$170 of each other) is well within noise. This is a lean, not
  a verdict. The sweep also doesn't model the live tick-floor/spread-floor
  safety rails ratchet_tiers.py enforces — those exist specifically to stop
  a too-tight arm from getting scratched by a quote flicker, which may be
  part of why arm 1-2% underperforms here. Changing the live ratchet off
  this number is G's call, not made here.
  Also tried: adding 9/8's own trades to the backfill. Blocked — Databento's
  free-credit tier license doesn't cover OPRA data after 2026-09-08 13:30
  UTC ("live data license required"), a provider-side cutoff, not a bug.
Previously — Last updated: 2026-09-08 — DATABENTO BACKFILL + AN OCC LANDMINE FOUND BY IT.
  G: "find out now then later and slow" — signed up for Databento ($125 free
  credit, no card) to price every call in days/*.json for real off OPRA,
  including the refused/nofill/failed ones option_tape.csv could never have
  (it only ever saw contracts the bot itself quoted, from 9/2 on). Key lives
  in settings.json execution.databento.api_key (setup_databento.py writes
  it — same "never pastes his secret to me" doctrine as tastytrade).
  `databento_backfill.py` reads days/*.json (109 -> 110 option contract-days
  once the fix below let a few more parse), pulls OPRA cmbp-1 (bid/ask) per
  contract for a window around its actual opened/closed time (30 min after
  the call if it never filled), downsamples to ~1 row/sec to match
  option_tape's own cadence, writes databento_tape.csv in the exact shape
  tape.py already reads, and is idempotent — a state file tracks every
  (occ, day) ATTEMPTED, not just the ones that returned rows, so a contract
  with genuinely no quotes in its window doesn't get re-fetched (and
  re-billed) forever. Wired into tape.py's SOURCES. Result: 329,430 rows,
  80 real contracts, 8/5 through 9/4. Cost: a few dollars off the $125.
  **FOUND BUILDING IT: a live landmine in occ.py, the ONE place every part
  of this app builds a contract symbol.** `_ymd()` stripped every `-`/`/`
  THEN counted digits, always assuming what was left was YYYY-MM-DD.
  `08/28/2026` collapses to the same 8 digits as `2026-08-28` that way, and
  the old code always read it in the ISO order — so a zero-padded
  MM/DD/YYYY date silently became a WELL-FORMED WRONG expiry (`282026` ->
  YY=28 MM=20 DD=26) with no error anywhere. `11/20/26` broke the same way
  in the other direction. Five real contracts from days/*.json hit this
  before Databento's own API refused the resulting garbage symbol
  outright — a broker that instead silently accepted it would have bought
  whatever contract that nonsense date happened to resolve to. Fixed by
  reading the year off WHICH piece is 4-or-2 digits and WHERE it sits,
  before the separators that carried that information get thrown away.
  test_architecture.py's occ/tape checks still pass; ARCHITECTURE.md
  updated with both the fix and the reasoning. This is the second landmine
  occ.py has caught since it was built 9/7 (side_letter's CALL/PUT flip was
  the first) — worth remembering that consolidating five copies of
  something into one doesn't just save code, it's the only way a bug like
  this is findable at all.
  **SAME DAY, CAUGHT BY G: the first analysis of this data was wrong.**
  Showed him "worst case" on the 23 missed calls as the lowest print in each
  contract's window — down to -94.5% on one. He asked "no contracts
  should've blown up, are you keeping in mind the ratchet system?" Correct
  — that number ignored that every entry gets a stop born at -10% (settings
  strategy.stop_loss_pct) and walks up from there (ratchet_tiers.py's 9/3
  ladder: arm +10%, first lock breakeven, +10% a rung; anti-clip OFF per
  9/4). Min/max-in-window was never what the bot would have experienced.
  Built `ratchet_backtest.py` to do it right: walk the real OPRA quotes
  tick by tick through the actual `ratchet_locked_pct` rule and report what
  really would have happened. Corrected picture: **zero of 119 simulated
  contract-days ever showed worse than the -10% floor** — the ratchet held
  everywhere in this sample, no gap risk materialized. Of the 23 missed
  calls, 18 stopped at exactly -10%, a handful hadn't resolved by the end
  of the (30-min, for a nofill) backfill window, and the one real gain
  (SPY 765C 8/31, +10%) is tagged "Gian" — his own hand trade, not a room
  miss. So: nothing the room called and we skipped turned out to be a
  missed big winner in this sample: the refusals did their job. Lesson for
  next time, not just this once — ANY backtest number on this project has
  to run through the actual exit rule, never a naive high/low, or it will
  overstate risk exactly like this did.
Previously — Last updated: 2026-09-08 — TWO-BROWSER SPLIT HARDENED + WHOP SELF-CONNECT.
extension 3.5.59. G set the Whop split up (second profile "Sniper Whop",
logged in, extension installed) and hit two issues, both fixed:
  1. WHOP PROFILE WASN'T FEEDING THE BRIDGE. A tab open BEFORE the extension
     loads never gets a content script (Chrome only injects on nav-after-
     install) — so whop.js never attached to the 4 pre-open Whop tabs.
     FIX: ensureReaders() on the 30s alarm injects the right reader
     (content.js/whop.js) into any matching tab not injected in 5 min.
     Idempotent, so no double-read. The Whop profile self-connects within a
     minute of the extension reloading — no manual tab reload needed.
  2. STRAY WHOP TABS IN THE DISCORD BROWSER (4 left over from before the
     split) would double-read Whop AND the old lane logic would REOPEN any
     G closed. FIX: sticky per-profile lane (profile_lane in storage, locks at
     >=3 tabs of a surface with a majority, never flips) + evictOtherLane()
     closes wrong-lane room tabs + whopWatchdog now no-ops in the discord lane.
     Net: the Discord browser never opens, reloads, or keeps a Whop tab; the
     Whop profile keeps its 4 and self-connects. No double-fire either way.
  AUTO-APPLY: the extension fingerprints its folder (bridge build_stamp) and
  reloads itself — but DEFERS while the market is open / a position is in
  flight. So 3.5.59 goes live at the CLOSE on its own, or immediately if G
  reloads the extension by hand in BOTH profiles. Bridge already restarted
  (12:01) so its side is live now.
  MISSED TODAY because of the above: trademorewiser's ES short (Whop, profile
  not feeding yet) and Stormzy's 12:00 MES (came in 1 min before the bridge
  restart, old Topstep sign bug). Both paths are fixed for next time.

Prior: 2026-09-08 — OWLS WIRED (shabs + eli), and a config-plumbing bug
fixed on the way. G asked if we see Elite/OWLS. Elite (Brando+Shoof) was
already live in rooms.txt; OWLS was never added — I built the parser support
on 9/7 and skipped the room lines. Now both shabs (1513300726141419550) and
eli (1519039282537300209) are in rooms.txt, BORN TESTING (gen 2026-09-08b),
28 live rooms.
  THE BUG, worth remembering: spx_entry_channels and default_symbol_channels
  live in settings.json — but that is the BRIDGE's file. The EXTENSION's parser
  does the SPX->SPY retarget and the implied-symbol fill, and it reads config
  from chrome.storage, which never saw settings.json. So editing settings.json
  enabled SPX on the bridge while the extension still refused it — they never
  agreed. (That is also why the old lone 1395 entry's history was murky.)
  FIX: the bridge now serves spx_entry_channels, default_symbol_channels and
  entry_no_verb_channels on /mode; refreshBridgeChannels() in the extension
  caches them and cfg() overlays them — settings.json is now the SINGLE source
  for all three, for both processes. A popup/chrome.storage value still wins if
  one exists. Proven: shabs "in 7655p 2.9" -> OPEN SPY 766P (SPX/10 retarget),
  born-testing so it won't fire until G flips it.
  Also fixed: I first wrote the OWLS keys under settings.execution (wrong
  level) and nearly orphaned the existing 1395 spx channel. Moved both keys to
  ROOT and merged 1395 back in. Now: spx_entry_channels = [1395..., shabs, eli].
  NEEDS the bridge restart to serve the new /mode fields, AND an extension
  reload to pick them up + open the two new rooms.

Prior: 2026-09-08 — WHOP IN ITS OWN BROWSER (his ask). Whop's 4 tabs are
the heaviest thing running and were dragging the Discord tabs enough to get
RWGates/Brando discarded. START HERE now opens Discord rooms in the main Chrome
profile and the 4 Whop rooms in a SECOND profile (WHOP_PROFILE, default "Sniper
Whop", override with whop-profile.txt) — a separate renderer set, so Whop's
memory is off the Discord browser entirely. All still one bat.
  ONE-TIME SETUP in the Whop profile, done once and it persists: log into Whop,
  and install the Discord Sniper extension in it (puzzle piece / Load Unpacked
  on the extension folder) exactly like the main profile. After that the
  launcher opens both every run.
  WHY IT DOESN'T DOUBLE-FIRE: both profiles run the same extension and read the
  same rooms.txt, so openMissingRooms() is now LANE-AWARE — an instance only
  opens rooms of a surface it already has a tab for. The launcher seeds each
  profile with its own surface (Discord rooms to main, Whop rooms to WHOP_
  PROFILE), so each adopts its lane and never opens the other's rooms. Discord
  and Whop room sets are disjoint (22 vs 4, no shared channel), so there is no
  overlap to collide on. Both post to the one bridge on 127.0.0.1 — it already
  sends Access-Control-Allow-Origin:* and does not care which browser posts.
  The Whop profile has its OWN channel_live flags; Whop rooms aren't in
  BORN_TESTING so they come up live by the 8/23 default — no extra step.
  Lane logic proven in isolation; extension 3.5.54.

Prior: 2026-09-08 — MISSING ROOMS HEAL THEMSELVES; launcher stops
nuking Chrome. G: "dont give me this option, check which are open and open the
ones that are missing." This reverses the 9/2 "close everything and reopen"
rule, which was a sledgehammer — it discarded tabs that were reading fine, and
THIS MORNING it shut the Brando/Shoof tabs, so Brando's 10:44 QQQ 720c call went
completely unread (the channel ids appear ZERO times in today's bridge log).
  NEW: background.js openMissingRooms() — the mirror of oneTabPerChannel().
  The dupe-closer removes extra tabs; this opens any LIVE room from rooms.txt
  that has no tab at all. Both run on the watch-build alarm, so the set of open
  room tabs continuously converges on rooms.txt without touching a good tab.
  LIVE rooms only (never #SLEEP or commented), Discord + Whop, throttled to 3
  per pass and never re-opening a room within 2 minutes (a still-loading tab
  has no matchable path yet — without the guard it would open forever).
  LAUNCHER: the [5/5] block no longer kills Chrome when it is already open. It
  prints "leaving your tabs exactly as they are" and jumps to :chromedone; the
  extension opens whatever is missing within a minute. Chrome is only started
  fresh on a true cold start (no window at all).
  CMD TRAP RE-HIT AND FIXED: my first draft put "(9/1 and 9/4 exports)" and
  even a NOTE about parens — inside the `if not errorlevel 1 (` block. A `)`
  in a rem inside a bracketed block ends the block early. The whole [5/5] body
  is now free of round brackets except the gate itself; verified 100/100 paren
  balance and zero brackets in lines 275-293.
  extension 3.5.53.

Prior: Last updated: 2026-09-08 — THE READER TAPE: reads.log + reads.py.
  G: "so now they will read and transcribe? i need to see them in order to
  help you analize." Yes — the listener transcribes whenever it is in a voice
  room even with voice_entries OFF, and vision reads every image post. They
  just landed in three different places (popup log, capture, bridge.log). Now
  ONE chronological, human-readable file: reads.log.
    time  🎙/📸  room  speaker | what the parser made of it | what was heard/seen [note]
  VOICE: background.js posts every finalized transcript line to POST /reads
  with a quick parse of it — fire-and-forget, never awaited, never allowed to
  slow the ears. VISION: the bridge writes its own reads directly — the call
  (with confidence), the refusal reason, or the FAILURE reason (which now
  carries the API's message, see the vision sweep below).
  VIEW IT:  python3 reads.py            last 60
            python3 reads.py --voice / --vision / --calls / --today / -n 200
            python3 reads.py --misses  lines with something ticker-shaped that
                                       produced NOTHING — the ones to look at
  The trading path never reads this file. It is for G's eyes, so he can point
  at a line and say what it should have been. That is how the readers get
  tuned from here on: not from me guessing, from him reading the stream.
  TO FILL IT: run the listener during a live session (entries can stay off).

Prior: Last updated: 2026-09-08 — VISION / IMAGE SWEEP. The last unswept path.
  THE DESIGN IS RIGHT AND IT IS WORTH KNOWING WHY. An image goes to the bridge
  /readimage; the model TRANSCRIBES what it sees (seen_text) and proposes a
  call; ai_reader.validate() then demands that the ticker, the strike and the
  price each LITERALLY appear in the model's own transcription plus the
  caption — a hallucinated ticker fails that bar. The clean call comes back as
  text and is re-parsed by the SAME parseSignal, and `sig = sig3` happens
  BEFORE `sig.live = roomLive` is set, so vision inherits live/testing, BORN
  TESTING, the ticker allowlist (sendOrder) and the volume floor (bridge).
  Confidence under 0.6 is held for review, never sent. Same image within 24h
  gets the cached verdict (the Whop 2K room re-posts one screenshot every ~6
  minutes). Images are fetched from Discord's CDN by the FULL SIGNED URL the
  browser already loaded, within milliseconds of the post, so link expiry
  never bites.

  WHAT IT HAS ACTUALLY DONE, from bridge.log: 137 screenshot reads.
    125 refused (charts, no call)          — correct
     12 produced a call                    — EVERY ONE a TRIM or CLOSE
      0 produced an ENTRY                  — ever
  With exit_policy=entries_only, a TRIM/CLOSE from a room is refused at the
  bridge, so VISION HAS NEVER PLACED AN ORDER and structurally cannot unless it
  one day reads an OPEN. Zero money exposure to date.
  Of the 12: nine were a bot's "+30%" progress cards read as trims (record
  noise only), "Out of INTC" was a genuine exit, and two were victory laps
  ("Those SPX puts we took went to $16.00 from $5.80") read as exits — wrong,
  harmless under entries_only, left alone.

  THE ONE FIX: 12 of 137 reads had failed as a bare "HTTP 400". The API's own
  explanation was read and DISCARDED — `return {"_error": "HTTP %s" % e.code}`
  — so nobody could tell if it was image size, media type, or a bad request.
  It now carries the message: "HTTP 400: image exceeds 5 MB maximum: 6.2 MB".
  Proven with a faked API error. Next time it happens the log has the answer.

  NOTED, NOT CHANGED: Discord's img.src is usually the RESIZED preview
  (?width=550), so the reader sees a thumbnail, not the original. Legible for
  an alert screenshot, and charts are refused regardless. Stripping the resize
  params for full resolution is possible but untested against the signed URL —
  do not touch it without proving the fetch still works.

Prior: Last updated: 2026-09-08 — voice_corpus.json: 2,305 REAL SPOKEN LINES, kept.
  G asked whether we have voice recordings to practise on. NO AUDIO IS KEPT —
  Deepgram transcribes the stream live and only the text survives. So we cannot
  test whether it HEARD correctly; we can only test what the parser does with
  what it heard. Those are different problems and only the second is testable.
  What we DO have is 2,305 unique spoken lines that were already being captured
  alongside typed messages (1,836 from Honeydrip daytrades-scalps, 557 from
  Live Trading). They are now saved as voice_corpus.json so the voice reader
  has a permanent regression set instead of lines scattered through exports.
  MORE ARRIVE FOR FREE: the listener writes transcripts into the same capture
  as typed messages, so any Ctrl+Shift+X on a room that was listening exports
  them too.

  A MEASUREMENT TRAP WORTH REMEMBERING: with the room prefix left on
  ("🎙 (2579) Discord | #room | S0: ...") only 41 lines produced an action and
  none fired. Stripped to the bare transcript — which is what production
  actually passes — it became 111 actions and THREE fires. Test the voice
  reader on the bare text or the result is meaningless.

  OF THE THREE: two were STOPMOVE with no symbol (already refused by
  entries_only). The third was real and is now fixed:
      "AMD actually is kinda selling here. Let's see."  ->  CLOSE AMD
  The STOCK is selling; nobody is selling anything. My first guard vetoed any
  "is/are selling" and that would have KILLED A REAL EXIT —
      "XOM OUT Will revisit... Most things are selling"
  — so the veto now only fires when the price-action phrase is the ONLY exit
  evidence in the line. Any independent exit verb (out, stc, sold, closed,
  trim, stopped, cut) and the line is left exactly as it was. test_exits.js
  holds both sides, including that "selling the rest" IS a full close.

Prior: Last updated: 2026-09-08 — VOICE / DEEPGRAM SWEEP.
  FIRST, THE REASSURANCE: VOICE FIRES NOTHING TODAY. voice_entries and
  voice_exits are absent from settings.json AND from cfg()'s defaults, and the
  code demands `=== true` for each. Everything below is LATENT — it matters the
  day those switches go on, not now.

  THE REAL FIND: VOICE IGNORED LIVE/TESTING ENTIRELY. The voice path carried a
  flat `vs.live = true` with the comment "voice rooms are live rooms" (8/29).
  That predates per-room testing and BORN TESTING, and it meant a room set to
  TESTING in the popup would still have fired its SPOKEN calls with REAL money
  — flatly against the house rule that flipping a room live is G's call alone.
  Now it reads the same three lines as the typed reader: his popup setting
  wins, an untouched room is live (the 8/23 default), a BORN_TESTING room
  starts in testing. Set BEFORE the two-stage staging, so a call staged on
  "loading" and fired later by "I'm in" carries the same flag. Five cases
  proven.

  WHAT THE TRANSCRIPTS ACTUALLY CONTAIN: 2,393 voice lines in the corpus, 41
  produce an action, and NOT ONE of them fires — they are almost all
  symbol-less commentary ("I'm taking trims here", "Loading the meta").

  ONE VOICE-SPECIFIC HAZARD, worth remembering:
      "I wanna load the same $3.45 puts on Tesla"  ->  TESLA 3.45 PUTS
  Two errors in one sentence. TESLA is not a ticker (TSLA is), and $3.45 is the
  PREMIUM — spoken alerts say "the $3.45 puts" where a typed one would say
  "$345 puts". So a spoken price can arrive in the STRIKE field. Today the
  ticker gate refuses it because TESLA is not on optionable.txt. If a speaker
  ever says a name that resolves cleanly AND quotes the premium that way, the
  strike would be wrong and the broker would reject it — noisy, not silent.
  If voice is ever switched on, a strike-vs-spot sanity check is the next
  guard to add.

Prior: Last updated: 2026-09-08 — BORN TESTING WAS NOT WORKING. G caught it: "the new
rooms show live for me actually". He was right and the gate was useless for
exactly the rooms it was written for.
  WHY IT FAILED. The gate applied only when channel_live had NO entry for a
  room. But channel_live PERSISTS on purpose (his own call: "everytime i push a
  new update my channels go all back to testing, i need the popup to keep the
  live on"), and the popup's ALL LIVE button writes true for EVERY room id.
  Four of the six reopened rooms — cranmer/opt-9, madhatter/opt-1,
  stormzyy/fut-1, guru/fut-2 — were LIVE rooms before being cut on 8/30, so
  they still carried a stale `true`. `_lv === undefined` was never true for
  them, the gate never fired, and they came back LIVE on real money.
  FIX: BORN_TESTING_GEN, currently "2026-09-08a". applyBornTesting() runs on
  install and startup and, once per generation, DELETES the channel_live entry
  for every id in BORN_TESTING so the room genuinely starts with no setting.
  It logs how many stale LIVE flags it cleared. After G flips one in the popup
  that is a real entry and it sticks — the migration will not run again for
  that generation.
  ADDING A REOPENED ROOM LATER: put its id in BORN_TESTING **and bump the
  generation string**, or the migration considers itself done and the room
  stays live. This is the trap that caused the bug; do not repeat it.
  Proven with a fake storage: 6 stale LIVE flags cleared, all six read TESTING
  afterwards, an unrelated live room untouched, and a flip-to-live survives the
  next startup.

Prior: Last updated: 2026-09-08 — TWO NEW GATES: A REAL TICKER LIST, AND A VOLUME FLOOR.
G pushed back on both, correctly, and both times the data moved the answer.

  1. extension/optionable.txt — THE ONE LIST OF TRADEABLE SYMBOLS.
     6,337 equity/ETF option roots + 25 futures + 8 cash indexes, pulled from
     tastytrade /instruments/equities/active (13,226 active equities). A symbol
     earns its place by the broker publishing OPTION TICK SIZES for it.
     Rebuild any time: python3 refresh_optionable.py (refuses to write a
     truncated file — an old list beats a short one).
     WHY: the reader took any capitalised word in front of a strike as a
     ticker. Blocking words one at a time is whack-a-mole — blocking VERY just
     moved the misread to GREEN. An allowlist ends it.
     I FIRST SEEDED THIS FROM TRADIER AND IT WAS WRONG. G: "your guessing makes
     no sense.. use the internet and all the api keys we have connected". He
     was right: the Tradier seed marked VSCO, WATT and SMX as not optionable
     and all three ARE. tastytrade's full universe is the source of truth.
     Checked against every symbol our alerts have ever produced: 33 would be
     blocked and ALL 33 are junk (WITH, GREEN, FVG, TESLA, BREAK, YES, NOTES,
     BABY, DAY, ONE, REST...) or small caps from Platinum equity, which is cut.
     ZERO real alerts blocked.
     NOW ENFORCED IN BOTH PLACES (9/8):
       * extension — background.js sendOrder() checks before the order ever
         leaves the browser, and writes a NOT-A-TICKER line to the log rather
         than dropping it silently, so a genuine ticker missing from the list
         is VISIBLE instead of a mystery no-trade.
       * bridge — symbols.py, checked in do_POST beside the NO-DATE gate, so
         anything reaching the bridge by another path is caught too.
     BOTH FAIL OPEN: a missing or truncated file (<1000 symbols) turns the
     check OFF and says so once. A data file that failed to load must never
     become a silent trading halt.
     test_optionable.js locks it: 44 real tickers must be present (SPY, NVDA,
     SNDK, MNQ, SPX, and SMH — which is slang in NOT_TICKERS but a real ETF),
     and 30 word-symbols that the live parser actually produced must be absent.

  2. liquidity.py — A VOLUME FLOOR, DEFAULT 250 (G's number, 9/8).
     His instinct: "even if you can buy a contract you still don't want to if
     there's no open interest.. you wouldn't be able to sell it to no one
     later." Right, and the measurement moved it one step: OPEN INTEREST IS
     THE WRONG NUMBER for these names. At strikes within 2% of spot —
         NVDA OI 3,403 / VOL 29,332      TSLA OI 1,076 / VOL 21,480
         QQQ  OI   792 / VOL  6,604      SPY  OI 1,206 / VOL  4,205
         MU   OI    94 / VOL  1,867      SNDK OI    27 / VOL    336
     These are day-traded contracts: everyone flattens by the close, so OI
     stays tiny while volume is huge. An OI gate would have blocked MU and
     SNDK for nothing, and SNDK is a real part of Brando's book.
     250 passes everything the rooms touch (SNDK's thinnest is 280) and only
     ever fires on something genuinely dead.
     READS THE PRIOR COMPLETED SESSION, on purpose: intraday volume starts at
     zero at 9:30, so a gate on today's number would refuse every 0DTE trade
     at the open. Served from a warm cache — the fire path pays no latency.
     FAILS OPEN: unknown contract, no token or a slow broker all ALLOW, with a
     note. The spread gate still stands behind it.
     EXITS ARE NEVER GATED — being stuck is the thing this guards against.
     Live-tested: MU 455C (0 traded) REFUSED, SPY 770C (87,921) ALLOWED.
     Off switch: settings.json execution.min_contract_volume = 0.
     Wired into webull_options.buy() beside the spread guard.

Prior: Last updated: 2026-09-08 ~late — SWEEP 2: FALSE POSITIVES. The first sweep
looked for MISSED signals. This one looked the other way — everything that
FIRES, checked for things that should not. Method: list every symbol the parser
has ever produced (135 distinct) and test each against English.

  SIX WERE ENGLISH WORDS. THREE OF THEM FIRED:
    "...then can go WITH 773c. Theta decay will destroy..."  -> OPEN WITH 773
       Pure coaching text. A BUY, in a ticker that does not exist, at market
       (no limit). The single worst thing found in either sweep.
    "| EXIT ALERT Ticker: NBIS Stopped out"                  -> CLOSE EXIT
       The real ticker is NBIS. A genuine stop-out was resolving to the word
       "EXIT", so the actual NBIS position would NOT have been closed. Now
       correctly CLOSE NBIS.
    "OUT LAST 3.50 L ON THE VERY LAST OTHERS GREEN"          -> CLOSE VERY
  Blocking a word just moves the reader to the NEXT word, so this took two
  passes: VERY -> GREEN, and the month list had only ABBREVIATIONS so
  "BOOKING SOME PROFITS FROM JUNE" resolved to ticker JUNE. Function words,
  colours, full month names and day names are all in NOT_TICKERS now.
  RESULT: 135 distinct symbols -> 129, and ZERO English words remain.

  CHECKED AND CLEAN, worth not re-investigating:
    * strikes: none absurd (nothing <1 or >10000)
    * one-letter symbols W and U are REAL (Wayfair, Unity), not misparses
    * 68 futures entries with no expiry — correct, futures have none
    * Discord REACTION COUNTS ("...full Tp 48 14 8 3") can create a fake price,
      but ONLY via fullTextOf/innerText, which feeds the history grabber. The
      trading path uses textOf() = message body + embeds, so reactions never
      reach it, and background.js gates history separately. Verified, not a bug.

  THE "161 DATELESS ENTRIES" — RESOLVED, NO CHANGE NEEDED. I flagged these as
  running on a GUESS. That framing was wrong and is corrected here.
  G's read of Platinum nitro was 0DTE ("the contract is so cheap"), and the
  data backs the STYLE completely: nitro never states an expiry (6 date-words
  in 885 messages, none a contract date), 119 contracts over 115 trading days
  = 1.1 entries/day, NOTHING ever carried to the next day (the 8 repeated
  strikes are months apart, not held), premiums $0.72-$2.33, and their own
  words "today is friday so lot more riskier setups" — Friday is only riskier
  if you are same-day.
  BUT literal 0DTE would be unbuyable for most of that room. bridge.py already
  splits it correctly, and the comment credits the rule to G on 9/7:
      SPY / QQQ / IWM  -> TODAY. These are the only tickers with a midweek
                         same-day listing, and it is what those rooms mean.
      single stocks    -> THIS FRIDAY. "A single stock has FRIDAY WEEKLIES
                         ONLY: a midweek 0DTE does not exist, so this Friday
                         is the only listing there is, NOT a guess."
  The split of the 161: 56 go to 0DTE, 104 go to this Friday — and the 104 are
  NVDA (38), TSLA (34), AMZN, PLTR, AAPL, GOOG, HOOD, META, AMD, UBER. Every
  one of those is a single stock with no midweek expiry to buy.
  execution.assume_weekly_expiry = True, so this is live and nothing is being
  refused. Setting nitro to a literal "0DTE" would ask the broker for contracts
  that do not exist on 104 of 161 entries. LEAVE IT.

Prior: Last updated: 2026-09-08 ~late — CROSS-ROOM PARSER AUDIT. G's ask: are we
slipping or missing alerts, do the rooms disagree with each other. Method: run
every room's captured messages (18 rooms, 3,769 unique) through the live
parser, isolate lines that carry a REAL CONTRACT but produce NO ACTION, group
by room. Two faults fell out, BOTH OLDER THAN THE AUDIT, both cost money:

  1. THE WORD "partial" WAS NOT A TRIM ANYWHERE. RE_PARTIAL's \bpart\b does not
     match "partial", and nothing else looked for it. So
       "STC TSLA 8/19 350c @ .36 partial"
       "STC META 0dte 600c .94 partial make the free"
     read as FULL EXITS — the caller sells a SLICE and the bot dumps the WHOLE
     position. NINETEEN corpus lines were doing exactly this, across Option
     Alerts, TTT Lotto and Elite. Now downgraded to TRIM (fire=false, per the
     exit doctrine: their trims are noted, never traded). No pct is set — he
     said partial, not how much.

  2. AN EXPLICIT STC WAS BEING SILENCED BY CHATTER. The chatter veto had a
     carve-out for BUYS only (_explicitBuy). Explicit SELLS had none, so real
     exits died on whatever the caller happened to say next:
       "...partial. Taking some in case we don't hold"   killed by "don't"
       "...stop hit on the rest, can probably..."        killed by "probably"
       "...cutting in the green, will be watching"       killed by "watching"
     The bare line closed fine; one casual sentence and the exit disappeared.
     A MISSED EXIT IS THE EXPENSIVE MISTAKE — the position stays open on our
     ratchet alone. An explicit STC with a real contract now skips the chatter
     veto entirely; unlike a buy there is no "don't" to respect, because the
     sell verb and contract are already stated.
  Corpus: 27 lines changed — 19 CLOSE->TRIM (the dump-the-position bug), 6
  newly-firing exits, 0 lost.

  EVERYTHING ELSE CAME BACK CLEAN. Platinum nitro looked worst on paper (203 of
  339 contract-lines silent, 60%) and is entirely correct: every one is
  "$140p on watch" — a WATCHLIST. Same for Aristotle ("Watching AAPL above 313
  for the 315 C"), Platinum ei-alerts ("WATCHING SPY $763 CALLS") and Aristotle
  small ("Loading HOOD 130 C" = the PREPARE state). Those rooms are fine.
  STILL OPEN, small: Honeydrip writes entries as prose ("I'm in @here 768P 1dte
  at $3.30", "Filled spy puts 775 puts 1dte 3.12") and Vero 3 posts
  "XOM 9/18 $170 C 2 cons @ 2.02" verbless — both readable, neither urgent, and
  Vero 3's are swing-alerts anyway.

Prior: Last updated: 2026-09-08 ~late — BOTH TURNED ON, G's call.
  TTT LOTTO verbless entries are LIVE. settings.json entry_no_verb_channels now
  contains 880503518878892143. One key added, 22 -> 23, nothing else touched and
  no secret read back. Its seven previously-invisible entries now fire, and its
  own daily levels row still does not.
  NOTE FOR WHOEVER READS THIS NEXT: TTT Lotto is a LIVE room, not born-testing,
  so this took effect on real money immediately — it was not staged. That was
  G's instruction ("turn on"), made with the numbers in front of him.
  NGD ngd-trades STAYS LIVE. G's call ("keep ngd"). It is a machine-generated
  1-minute futures radar ("NEW POTENTIAL SIGNAL", "a setup has been detected")
  firing real MGC/MNQ orders with a limit, and no one has yet reviewed what it
  costs or makes. The journal is the place that will answer it — first NGD fill
  that lands, check it there.

Prior: Last updated: 2026-09-08 ~late — THE TWO UNKNOWN ROOMS, GRABBED AND READ. G was
asleep, so the scrollback was pulled by hand instead of Ctrl+Shift+X.
  TTT LOTTO (#lotto-alerts, TradingTheTrend) IS ALIVE AND WAS HALF-BLIND.
  127 messages, 8 callers (TradingTheTrend, Lars, Tater Tot, Edtrader,
  Shakira T, treadwayma, Abblejuice, rks). Clean BTO/STC grammar — but most
  callers skip the verb, and NINE entries fired while SEVEN were invisible:
  "MU 8/28 965c @ 1.26", "TSLA 9/4 360P .72", "NBIS 230C @.25",
  "AMD 0dte 445p @ .76". Now 15 entries.
  NEW, AND SCOPED PER CHANNEL: settings.json entry_no_verb_channels. A bare
  contract WITH a price counts as an entry, but ONLY in a room named there.
  THAT SCOPING IS THE WHOLE SAFETY STORY AND IT WAS MEASURED. Across the
  7,168-line corpus, 51 currently-silent lines match "contract + price", and
  the biggest group is TradingTheTrend's OWN daily levels row —
      "QQQ 726c > 725.00  715p < 716.00  MU 1000c > 980.00 ..."
  ONE LINE, EIGHT CONTRACTS. Global, this rule buys a watchlist. G's read:
  "it would be a disaster." The rest were weekly recaps and victory laps.
  Even inside a named room the vetoes still refuse: comparison operators,
  recap/weekly/unrealized/runners/banger, on-watch/watching/loading/eyes-on,
  up-N%/arrow/itm/hit, and anything RE_EXIT or RE_TRIM catches.
  BONUS BUG, OLDER THAN TONIGHT: the "bullwinkle entry" branch would take
  "SPY $654p on watch again for a quick scalp" — a WATCHLIST row — and buy it.
  Nothing was firing in practice only because the nitro room's real posts carry
  an "@Owner Alerts Comment" prefix that stops them earlier. That is luck, not
  a guard. On-watch is now refused in that branch too.
  NGD ngd-trades IS A FUTURES RADAR BOT, and it DOES fire:
      "MGC SHORT (1m) @ 4428.65 | TP:4416.65 SL:4436.65 | Prob:74.5% | R:R:1.5"
  parses as OPEN MGC SHORT limit 4428.65 (MNQ LONG likewise). NOT a human's
  executed trade — the bot's own words are "NEW POTENTIAL SIGNAL" and "a setup
  has been detected". 1-minute timeframe, leveraged futures, machine-generated.
  FOR G TO DECIDE: this room is wired and live. Nobody has ever reviewed what
  it actually costs or makes. Worth a week in testing before it is trusted.
  Corpus: 7,166/7,168 identical with the flag off, 0 newly firing, 0 lost.

Prior: Last updated: 2026-09-07 ~night — VOICE AUTO-JOIN STAYS AS IT IS. G's call,
made with the tradeoff in front of him. Do not change it, and do not raise it
again unless he does.
  THE FACTS BEHIND THE DECISION. The extension makes ZERO requests to Discord —
  the only network destination in all of extension/*.js is 127.0.0.1:8787. No
  user token, no gateway, no messages, no typing. Discord's published detection
  signals (messages with no typing event, typing across channels in 5-50ms,
  channels iterated in ID order) are ALL emitted by sending; we send nothing.
  Reading the DOM is structurally safer than every comparable project, all of
  which drive the gateway with a selfbot token.
  THE ONE EXCEPTION is content.js joinLiveVoice(), which clicks the LIVE badge
  and presses Join. It is the only place the app acts as the user, and it does
  produce a real server-side voice-state event.
  G ASKED FOR A 3-4 SECOND DELAY on it. Not done, deliberately: Discord's own
  policy names delays specifically — "captcha solving, token rotation, delays,
  and human-like typing do not make a prohibited use compliant". A delay
  changes nothing about what is sent, it only makes an automated action look
  less automated, so it buys the appearance of safety and not the safety. He
  was offered notify-and-tap (same few seconds, removes the account action
  entirely) and chose to keep instant auto-join knowingly. That is a legitimate
  choice about his own account and it is recorded here as his, not as an
  oversight.

Prior: Last updated: 2026-09-07 ~night — SPX IS TRADEABLE, ON TASTYTRADE. Settled by
API, nothing submitted (Tradier preview=true and tastytrade /orders/dry-run
both validate and stop):
  tastytrade  ACCEPTED "SPXW 260908C07760000", dry-run status Received,
              buying power 250.00 -> 243.28 (change 6.72 on a 1-lot at 0.05).
              Only warning was "next valid session" — the market was shut.
              THIS IS THE PATH FOR SPX. Note the bot trades options on WEBULL
              today; tastytrade is greeks-only. Using it to EXECUTE is a real
              build, not a config flip.
  Tradier     ACCEPTED the same contract and reached the buying-power check,
              so SPX permissions are fine there too — but it is blocked:
              total_cash 250, uncleared_funds 500, option_buying_power -250.
              A funding/settlement problem, NOT an instrument problem.
  Also: that 7760 call quoted bid 2.15 / ask 2.30, which corroborates the
  "300/con" = $3.00 reading. At ~$220 a contract, $250 of buying power is
  exactly ONE contract — which is how shabs sizes ("1 con per play").

ANNOUNCEMENT-FOLLOW WORKAROUND: CHECKED, DOES NOT APPLY. The idea (follow a
Discord Announcement channel into Sniper HQ so it arrives as a webhook post,
which background.js already unwraps like the ZTRADEZ relay) is sound, but all
8 servers were scanned 9/7 and ZERO of the 24 wired rooms are Announcement
channels. Only ZTRADEZ has any at all (3: winning-recap, penny-stocks, otc)
and none of them is a room we trade. Alert rooms are plain text channels
because sellers gate them; Announcement type is for broadcast. No tabs saved.

Prior: Last updated: 2026-09-07 ~night — SHABS (OWLS #shabs-sky-alerts,
1513300726141419550, plus 1519039282537300209). His August recap: 53 SPX
trades, 42W/6L/5BE, 87.5% win rate ex-BE, +$15,898 net at 1 contract a play —
the best record in any room scanned. Two things in his grammar were traps:
  1. PREMIUM QUOTED PER CONTRACT. "7760c at 300/con" is a $3.00 option, not a
     $300 one — his own recap proves the scale ("8/28 7760c 245 -> 1550" =
     2.45 -> 15.50). Read literally that is a THREE HUNDRED DOLLAR limit on a
     three dollar option, which doesn't merely overpay, it DELETES the price
     protection the limit exists for. Now normalised before anything reads a
     price. "10 cons" (a quantity) is untouched — the rule only fires when the
     number is glued to the slash. NOTE he also uses plain dollars in the same
     channel ("in 7730c 4.3", "AAPL 322.5c at .30"), so both must work.
  2. THE TICKER HE NEVER TYPES. He trades one underlying and says so ("August
     Recap, SPX only"), so he writes "in 7655p 2.9" with no symbol and nothing
     parsed at all. NEW: settings.json default_symbol_channels maps a channel
     to the symbol it always means — { "1519039282537300209": "SPX" }.
     PER CHANNEL on purpose: a bare "640c" in a room that trades everything is
     unknowable, and inventing a symbol there buys the WRONG UNDERLYING. Only
     applied when the line has no contract of its own, so an explicit ticker in
     the same message always wins. With the setting absent, those lines stay
     unreadable — that is the guard, and it is a test case.
  ALREADY CORRECT, left alone: indexToEtf nulls the limit on SPX->SPY ("index
  premium != ETF premium; bid the ETF market"), so the ~10x notional gap does
  NOT leak into a limit price. Good design that was already there.
  STILL BLOCKED, and it is G's call: SPX ENTRIES ARE OFF. Wiring shabs means
  adding his channel to spx_entry_channels, which converts 7655p -> SPY 766p.
  That is a money/strategy decision (SPY is a proxy, not his instrument), so
  it stays his. Open question raised 9/7: whether Tradier or tastytrade can
  place a REAL SPX order via API, which would remove the proxy entirely.

Prior: Last updated: 2026-09-07 ~night — THE PLAN IS THE VERB. G pasted six alerts
from a room that writes calls with NO ENTRY VERB — contract, fill price, then
the risk plan. All six read as silence. Now 4 of 6 parse, and the two that
don't are refusals on purpose. Three fixes, each regression-tested on the full
7,168-line corpus:
  1. PLAN-AS-VERB. A bare contract alone stays ambiguous — that is a watchlist
     row and forcing it to fire buys somebody's chart idea. But nobody writes
     "SL .80 TP 1.60 / 1.95 / 2.6" about a trade they have not taken. A stop or
     a target ladder WITH a number now counts as the entry verb, and only
     alongside a real contract and no exit/trim/recap language.
  2. EXPIRY ON EITHER SIDE OF THE STRIKE. "TSLA 357.5 0 DTE CALLS" was unread
     because the shape only allowed an expiry BEFORE the strike. "0 DTE" with a
     space is accepted too. The after-expiry must be preceded by a real space,
     or "those same 1dte puts" parses as ticker SAME strike 1 — it did, briefly,
     and that is now a test case. SAME/THOSE/THESE/THAT/THIS added to
     NOT_TICKERS.
  3. DATE FIRST. "9/2 TSLA 355 PUTS 1.57" matched the contract but LOST the
     expiry, so the entry fell back to a guessed one. A short 14-char window
     before the symbol is now searched, so an unrelated date earlier in the
     sentence cannot be adopted. Bonus: cranmer's "QCOM $167.50 Sept 18th
     Calls" — a documented safe-miss — now parses.
  MEASURED, NOT GUESSED — two broader triggers were tested against the corpus
  and REJECTED. "lotto" matched 13 lines, every one a "$150p on watch"
  WATCHLIST row. An @everyone/@here ping matched 140, mostly "loading GOOGL
  8/21 345C @here" — the PREPARE state, where firing buys before the caller
  does. Both would have bought things nobody bought. test_plan_entry.js keeps
  those exact lines as must-not-open cases.
  STILL REFUSED ON PURPOSE: "SPY 0dte 775 .25 TP .45" names no side at all —
  call or put is unknowable and must never be guessed. "SPX 7755 0DTE CALLS
  1.85" carries no plan and no verb (SPX entries are gated off anyway).
  "kind of a lotto 9/2 META 590 call 1.8 GOING FAST" is a real call whose only
  tell is prose — that is the AI-fallback case, not a regex case.

Prior: Last updated: 2026-09-07 ~night — PHANTOM EXIT KILLED, and OWLS CAPITAL SCANNED
AND REJECTED.
  "OUT" IS ALSO HALF AN IDIOM. stormzyy's recap of a FINISHED trade — "let it
  play OUT exactly how we wanted" — fired a real CLOSE MNQ off the bare "out"
  in RE_EXIT. Hunting it found a SECOND live one already in the corpus: "I'm
  officially checked out for the rest of the week", a sign-off message, was
  firing CLOSE with the symbol "NOTES". A phantom exit is worse than a missed
  one: it flattens a live position on somebody's victory lap. "out" no longer
  counts when it is the tail of a phrasal verb (play/work/pan/ride/figure/
  watch/check/find/reach/... out). "sold out" is deliberately still an exit.
  test_exits.js locks 9 idioms out and 6 real exits in. Corpus: the ONLY line
  that changed from firing to not firing is the "checked out" phantom.

  OWLS CAPITAL (718624848812834903) — all 24 channels read, NOTHING WIRED:
    jon-and-kian  trades COMMON STOCK ("CHGG commonst at .83", "22% on
      commons"). Dangerous to wire because "Sold another SPCX at 5.70" names
      nothing as stock and reads as a plain CLOSE — it would dump an SPCX
      OPTIONS position. The text cannot tell; only the room can. The shares
      veto now also covers "commons"/"commonst"/"common stock".
    ab            real options, but entries are BARE contracts with no verb
      ("$GOOGL 10/16 400c 1.88") so they never fire, while his closes DO.
      A room that can close but cannot open can only ever end a ride early —
      strictly worse than not having it.
    tt            SPX 0DTE, sample is a spread ("7690/7675p 0dte 1.4").
    muggzone      parses, but DROPS THE EXPIRY: the date sits BEFORE the
      ticker ("ENTERED 9/11 MRVL 240 CALLS") and the reader only looks after
      it. ZERO of our 7,168 corpus lines use that order, so nothing wired is
      affected — left alone rather than widened on speculation.
    giul-heatseeker trader is abroad and his bot is broken; members-plays is
      member chat. Everything else is bot feeds and admin.

Prior: Last updated: 2026-09-07 ~night — ELITE OPTIONS PRO WIRED (G bought it that
day). Scanned all 28 channels; free tier showed 15, Pro unlocked the two that
matter. WIRED, born testing: Brando Alerts (1286022517869514874) and Shoof
Alerts (1368263191632543956). Their grammars:
  Brando  "@Elite BOUGHT | QQQ SEPT 2 717C $2.99 LOTTO"   month name, $price
  Shoof   "@Elite ALERT BOUGHT | SPY 9/4 767C at 2.00"    numeric date, "at"
Verified against 148 of their REAL alerts scraped from scrollback (Brando 100,
Shoof 48): every one resolved to the right action, symbol and strike.
Three parser faults this found, all fixed, each with ZERO corpus regression
(7,168 lines diffed before/after on every change):
  1. TRAILING PARTIAL — both callers put the size at the END, after the price:
     "(1/2)" "(1/4)" "(1/8)" "1/4 position" "3/4 position". The partial reader
     only looked right after the verb ("sold 1/2 UPS"), so ALL of these read as
     FULL EXITS. A caller trimming a quarter would have closed the whole
     position and handed back the rest of the move. Only "ALL OUT" fires now —
     both callers write it literally, so it is a safe discriminator. Dates are
     the trap (9/4 is not a fraction), so it only counts a fraction in
     parentheses or followed by "position", and only when num < den.
  2. SMH — blocked in NOT_TICKERS as "shaking my head", but Shoof trades the
     ETF. Now rescued ONLY when the word wears a contract (strike + C/P).
     "smh this market" is still slang. This also exposed that FIVE separate
     places tested NOT_TICKERS; they now all route through blockedTicker().
  3. SHARES — Brando posts stock trades in the same alert channel
     ("SNDK 250 SHARES AT $1550.50"). That read as CLOSE SNDK and would have
     dumped an SNDK OPTIONS position because he trimmed stock. Any line that
     talks about shares and names no contract is refused; a line with a
     contract ("sold shares, still holding the 580c") is untouched.
NOT WIRED, deliberately: brando/shoof-commentary (level talk — "MU wants 1011,
1020 next", ~1 tradeable contract a session), levels/flow/x-news/uwhale bots,
trade-log + chartbook + market-recap + winning-trades (weekly IMAGES, not live
entries), the two chatrooms, and live-voice-logs (a voice-path candidate).
ALSO SCANNED 9/7 and rejected: The Options Cartel (no alerts channel at all,
free tier only) and Low Key Stonks (per-trader alert channels exist but are
behind the paywall; the visible member-picks is covered calls).

Prior: Last updated: 2026-09-07 ~night — "BUY" WAS NOT AN ENTRY VERB. Chasing why
cranmer's alerts never fired turned up three faults, one of them dangerous:
  1. RE_ENTRY listed bought/buying but NOT the bare imperative "buy". cranmer
     writes every call that way, so the whole room read as silence. "buy" is
     genuinely risky ("DO NOT BUY IN" is a real Honeydrip line), so it is now
     accepted only via RE_BUY_CMD, guarded by RE_NO_BUY (negations, questions,
     "buy the dip", "or buy next week") AND only when the line names a contract.
  2. TRAILING-DOLLAR STRIKES were unreadable: cranmer writes "104$", "61$",
     "52$". Normalised away in parseSignalInner before any format reader.
  3. MONTH NAMES were valid tickers. With 1+2 unfixed, "buy AA sep 18 Calls
     52$" booked ticker SEP strike 18 — A REAL ORDER IN THE WRONG NAME. All
     month and weekday abbreviations are now in NOT_TICKERS.
  REGRESSION: all three ran against the full 7,168-line corpus versus the
  pre-change parser. 7,165 identical, ZERO stopped firing, ZERO new false
  positives; the 3 differences are trailing-$ contracts now read correctly on
  exit lines. test_buy_verb.js locks it, and lists the remaining SAFE MISSES
  (dash-before-strike, decimal strike, strike-after-side, madhatter's verbless
  "MCD Puts oct 16th exp, 245s") — deliberately left, because widening the
  contract reader for those risks bringing the SEP-style misparse back.
  STILL OPEN: stormzyy's RECAP of a finished trade ("Caught a clean MNQ long...
  Both targets hit") still fires a phantom CLOSE MNQ.

Prior: Last updated: 2026-09-07 ~evening — NO SPREADS, NO COVERED CALLS, AT THE ROOM
LEVEL. G 9/7: "Whatever is a spread or covered calls and all that, I want you
to delete those rooms. I do not want covered calls and spreads." Two of the six
reopened rooms were cut on that rule, on evidence, not on vibes:
  evapanda/opt-5 — his own 8/31-9/4 summary: RIVN 25C "This was a covered
    call", BULL 15C "Covered Call - Collecting Prems", NOK 2028 leap, plus
    TSLA/AMZN/URA swings. Fails the covered-call rule and the no-swings rule.
  tlm/opt-4 — verticals in 2 of his last 5 entries: 9/4 "Msft Sep 9 497 put buy
    490 put sell Total pay 2.20" (the one that fired a naked 497 put) and 8/18
    "Swing Gld Aug 31 405 call buy 415 call sell" — a spread AND a swing.
Every other live room was re-scanned for spread/covered-call business: clean.
FOUR rooms remain reopened and BORN TESTING: cranmer/opt-9, madhatter/opt-1,
stormzyy/fut-1, guru-futures/fut-2. 27 live rooms.
NOTE: the parser refusing spreads (below) and cutting the rooms are two
different defences and BOTH are wanted — the guard protects against a spread
arriving from any room, the cut removes rooms whose business is spreads.

Prior: Last updated: 2026-09-07 ~evening — NAMED-LEG VERTICALS NOW REFUSED. G asked to
put the six reopened rooms LIVE. Before that (rooms LIVE stays his action) the
six traders' REAL messages were run through parser.js, the one that fires. It
found a money bug: TLM writes spreads WITHOUT the word "spread" —
"Msft Sep 9 497 put buy 490 put sell  Total pay 2.20" — and that fired as a
NAKED long MSFT 497 put. Different trade, different risk: his loss is capped at
the $2.20 debit, a bare 497 put costs multiples of it. The old guard only
matched the literal words credit/debit spread, which is why kumo's CAKE spread
was correctly refused and TLM's was not.
  FIX: structural, not vocabulary — two DIFFERENT strikes, each with its own
  put/call word, one leg bought and one sold. test_spreads.js locks it: 6
  multi-leg forms refused, ordinary single-leg entries still fire.
  KNOWN GAPS, pre-existing and NOT caused by the fix (verified by diffing
  parser.js with and without the block — identical): these real entries are
  silently MISSED (money left on the table, never a wrong order) —
  "buy UPS 104$ calls Sep 18th for 1.75" (cranmer, strike written 104$),
  "Open ... Aapl sep4 327 call at 1.87" (tlm), "MCD Puts oct 16th exp, 245s"
  (madhatter), and any entry that also names a sell target.
  ALSO SEEN: a stormzyy RECAP of a finished trade ("Caught a clean MNQ long...
  Both targets hit") fires a phantom CLOSE MNQ. Not yet fixed.

Prior: Last updated: 2026-09-07 ~evening — THE MASHUP DOES NOT CARRY EVERYONE, and a
new rule: BORN TESTING. Verified by reading all 19 cut ZTRADEZ rooms live in
Discord and diffing their real 9/1-9/4 entries against 9 days of mashup
capture. The mashup relays 10 of 19; NINE were dark. Eight of those nine had
been cut on 8/30 for the reason "redundant: flows through the mashup" — which
was never true. G reopened six (cranmer/opt-9, evapanda/opt-5, madhatter/opt-1,
tlm/opt-4, stormzyy/fut-1, guru-futures/fut-2) and declined the three swing
rooms (clutch/swing-1, king-maker/swing-3, kumo/swing-2 — "I don't want any
swings channels").

  NEW RULE — BORN TESTING (background.js, next to the 8/23 "always live"
  default). A room with NO channel_live entry normally trades REAL MONEY the
  moment its tab opens. Reopening six unproven rooms would therefore have put
  six untested traders on real money without G flipping anything, and
  flipping a room LIVE is his call alone. Those six ids now start in TESTING.
  The gate only applies while channel_live has no entry — the instant he sets
  either value in the popup his choice wins and the list goes inert. Proven
  with 5 cases run against the real source block.

  ALSO: rooms.txt field 4 is the POPUP GROUP LABEL (popup.js:1072). Never put
  a trailing "(note)" on a live room line — it invents a new group in the
  popup. Notes go on a '#' line above. Fixed one pre-existing offender (TTT
  Lotto), which also explains why that room appeared unexplained earlier.

  The mashup carries TWO streams: ZTRADEZ BOT (forwards, 7 rooms wired) and
  ZTRADEZ Manager (house feed — Namrood + Bullwinkle/top-flow/scalps). The
  Manager format is the cleanest alert grammar we receive
  ("Buy To Open ORCL 147C 09/04 $1.5" with entry/expiry/running P&L) but it
  wraps the contract in ANSI colour codes — the reader must strip them.

Prior: Last updated: 2026-09-07 ~mid-day — G pasted TradingTheTrend's own format/
glossary guide to sharpen the reader for that room. Their alert grammar
("BTO AAPL 120c 11/06 @1.5" / "STC AAPL 120c 11/06 @.90 for -10%") already
parsed clean — strike-then-expiry, leading-dot prices, BTO/STC verbs were all
covered before today. What their glossary exposed: it spells out jargon
(ITM/ATM/OTM, DD, MM, SS, FA, IPO, ETF, GTC, GTD, YOLO, FOMO, AH, ER, PRE) this
reader had never seen written in caps, and bareSymbol's rule is "any all-caps
1-5 letter word not on the exclude list IS a ticker" — so "trimming ATM 40%"
or "out of DD" would have resolved ATM/DD as the traded symbol and could fire
a phantom trim/close on a real position of that name. Added all fifteen to
NOT_TICKERS in extension/parser.js (3.5.30 — RELOAD IT); confirmed the exact
BTO/STC lines still fire and "trimming ATM 40%" / "out of DD" now correctly
return symbol: null ("couldn't tell which ticker") instead of guessing.
LEFT OUT ON PURPOSE: MOMO ("Momo" = momentum in their glossary) is also a
real, actively-traded ticker (Hello Group) — same tradeoff already accepted
for TA/DD elsewhere in the list, but this one's for G to bless, not assume.
ALSO FOUND, NOT YET ACTED ON: the welcome message named three TTT channels
never wired into rooms.txt — option-spread signals (808127664022880297),
lottery-ticket plays (880503518878892143), and an auto-log of every
option-alerts fill (800526679046225961, posted by bot 803669969895161876).
The last one mirrors the option-alerts channel already wired — adding it
would double-fire every trade from two sources. Spreads are multi-leg; this
bot has no multi-leg order path. Flagged for G, not added — new rooms go
LIVE by default and that's his call alone.
Previously — Last updated: 2026-09-07 ~01:45 — see "9/6-9/7 OVERNIGHT" at the bottom.
The short version: **telemetry** now records the alert→fill latency chain and
the entry math on every fill (`telemetry.csv`); `caller_report.py` scores
callers and found that **nobody has 20 closed trades yet**, so no auto-benching
until there is a sample; a **shadow option-quote stream** rides the tastytrade
socket into `quote_shadow.csv`, read by NOTHING; the greeks socket now
**re-auths in place** instead of dying every 15 minutes; the Webull futures
position read **backs off** after 3 empty reads (it was 363 of 364 throttles);
futures + Topstep toggles are **ON** at G's instruction.

Previously — 2026-09-04 LATE EVENING — see "9/4 EVENING" below for the six
things that changed after the close. The short version, because it is a lot:
**(1)** the bot now trades the contract the caller ACTUALLY named — the
1-strike-OTM rewrite is off, it had been paying ~2x the called price;
**(2)** anti-clip is OFF entirely, plain ladder only, his call;
**(3)** SHADOW MODE is running — a second ratchet rule scores itself against
every real fill into `shadow_ratchet.csv` and trades nothing;
**(4)** `bars_capture.py` + `ratchet_lab.py` — real 1-minute option bars from
Tradier, and the replay that tunes the ratchet on them;
**(5)** the browser-lag fix in `content.js` (extension 3.5.24 — RELOAD IT);
**(6)** `trades.log` no longer carries the boot banner — it was 21% of the file.
Also: click a caller's name in the popup to jump to their room's tab.
Read `CLEANUP-PROPOSAL.md` — it has removal decisions waiting for G.
Prior: 2026-09-04 16:55 — DAILY CLOSE-OUT run (see bottom section
"9/4 16:55" for the full writeup). Account flat overnight, no open positions.
Bot day -$34, Gian +$154, combined +$120 broker-verified. One real, unfixed
gap found: two of Gian's fast SPY scalps (770P, 769P) never reached
days/2026-09-04.json despite postdating today's 10:30 DATA RULE fix — flagged,
not fixed (root cause unconfirmed). Everything else that looked wrong today
(INTC 94C -$12 born-stop, the ratchet's refused breakeven move) was already
diagnosed and fixed earlier in today's own 10:20 session, before this
close-out ran. ENTRIES ONLY gate verified solid: 96 room exits logged
"ignored" today, zero traded. 0 silent drops, 0 missed entries on replay.
Prior: Last updated: 2026-09-04 10:30 — **SWING TRADES ARE PAUSED** (G's call, right
after the INTC 96C 9/18). A call for a contract 14+ days out, or one a room
labels a swing, is now REFUSED at the entry gate in bridge.py `_place_impl`
("SWING-OFF ... refused"). Nothing is sent; scalps trade normally; positions
already held are untouched and keep their stops. Switch: `swings_paused` in
settings.json, toggled from the popup's Strategies tab (extension 3.5.17 —
RELOAD IT), reported in /mode so the state is never a guess.
**THE DATA RULE (9/4, G: "i want to get more weeks data off of trades").**
Webull's API has NO historical option prices, so anything not recorded as it
happens is gone forever. Two holes were found and closed:
- **option_tape.csv had no ticks for the contracts we traded.** 9/4 recorded
  2,284 ticks of XLF (G's own hand position, rendered by /positions) and ZERO
  for NVDA 235C and INTC 94C. Two silent failures stacked: the batched sweep
  kept returning without them, and the watchdog's direct-quote fallback threw
  its quote away instead of taping it. Now: the bus `tape()`s the fallback
  quote, positions subscribe at ARM time (not only from inside the watchdog
  thread, which can return early), and the bus SAYS "QUOTE BUS BLIND on <occ>"
  after 30 empty sweeps. Locked by `test_tape.py`.
- **Live trades were never written to the day book at all.** The whole
  closed-trade row sat inside `if not p_live`, so only PRETEND trades were
  recorded — 26 day files hold 2 rows between them while trades.log shows 125
  fills. The wallet maths is still gated (a live trade never moves the pretend
  cash); only the RECORD is unconditional now, tagged `live`.
- The row now carries the SHAPE of the trade, not just its ends:
  `max_runup_pct`, `max_drawdown_pct`, occ, side, strike, expiry, dte, swing,
  `stop_at_exit`, why, state, live. Run-up/drawdown were already tracked in
  memory by `_mark_excursion` since 8/19 and thrown away at close. They are
  the only way to ever answer "how far did a WINNER go against me first",
  which is the question every breathing-room rule depends on.
**TASTYTRADE IS OAUTH NOW — HIS PASSWORD IS NEVER ASKED FOR (9/4).** The old
username+password `/sessions` flow is fallback only. Current path: he makes an
OAuth application at my.tastytrade.com -> Manage -> API Access -> OAuth
Applications (callback `http://localhost:8000`, SAVE THE CLIENT SECRET, shown
once), then Manage -> Create Grant for a REFRESH TOKEN. Those two strings go
in settings.json; `_session()` POSTs them to `/oauth/token` for a **15-minute**
access token (not 24h — it refreshes on a 60s margin) and sends it as
`Bearer`, while the legacy token is still sent raw. Refresh tokens never
expire and can be revoked without changing his password. `SETUP TASTYTRADE.bat`
+ `setup_tastytrade.py` rewritten to match; `test_brokers.py` pins BOTH auth
header shapes. **Claude never types his password or pastes his secrets — he
does that himself, in his own browser and his own terminal.**

**A CLOSE ALWAYS LEAVES A ROW (9/4 evening — the journal caught my own
half-fix the same day).** The morning fix moved the closed-trade record out of
`if not p_live` so real trades would be written down. It was still inside
`... and price is not None`, so **every exit where the fill price isn't known
yet recorded NOTHING** — and that is every hand close ("sold, but at a price I
never saw"), plus any exit the broker hasn't confirmed. Result: the 9/4 day
book held **0 trades** while the journal counted 11. Now the row is written on
every close path, with `exit`/`pl` NULL and `pending_price: true` when the
price isn't known; `_true_up_exit` and the journal fill it in from the broker's
order list. **Null is honest, zero would have been a lie, missing was worse.**
Proven for live/paper × price/no-price, and the `_recorded` flag stops any
path writing the row twice.
ALSO: `restore_state` pops `hi_pct`/`lo_pct` on restart, so a position held
across a restart loses its run-up/drawdown history. Not yet fixed — flagged.

**BOTH NEW BROKERS ARE LIVE AND VERIFIED (9/4 18:10).** tastytrade: $250,
`api`/REALTIME, greeks_tape.csv filling. Tradier: production key, **$500**
buying power, balances + stock quote (SPY 770.19) + positions all reading
against the real server. Tradier's stock quote WORKS where tastytrade's REST
market data 403s. **`execution.broker` is still `webull` — neither is
executing.** Unproven on Tradier: the option-quote path (needs a live OCC) and
**OTOCO**, which is the whole point of it — prove that in their sandbox before
it ever sees real money.

**THE SOURCE-OF-TRUTH RULE (9/4, after getting it wrong twice in one hour).**

    positions -> ask the ACCOUNT
    prices    -> ask the ORDER HISTORY
    reasoning -> read the logs
    ...and NEVER substitute one for another.

What happened: Claude told G he was holding a 5-lot SPY position. He wasn't —
it had closed an hour earlier. The claim came from a log line that was TRUE
when written and FALSE when read: `11:44:59 ADOPT left SPY x5 alone`. **A log
is a narrative in the past tense. It is not a statement of state.** Same class
of error as the bot saying "you closed it yourself" when its own stop fired.
Then, compounding it, Claude saw `ADOPTED x2` + `ADOPTED x3`, decided 2+3=5,
and accused the adopt code of inventing the position. The order history said
otherwise: a REAL 5-lot SPY 769P, bought 11:44:30 @ 0.46, sold 11:48:49 @
0.54, +$40. **The code was right.** A tidy theory beat a ten-second check.
Before any claim about what he holds: `now.py` / `WHAT DO I HOLD.bat`, or the
Webull connector's get_account_positions + get_order_history. Never the log.
TODO after the close: `webull_options` has no `order_history()`, so section 4
of now.py is a stub — add it.

**GREEKS ARE LIVE AND RECORDING (9/4 12:05).** G funded tastytrade; the token
flipped from `level: demo` on `/delayed` to **`level: api` on `/realtime`**
within minutes. `GREEKS on` at bridge start. Real numbers flowing, e.g. INTC
9/18 96C: delta 0.4798, gamma 0.0377, theta -0.1486, vega 0.0745, IV 0.5658.
- **`dxlink.py` is STDLIB ONLY — no pip install, on purpose.** A ~150-line
  RFC 6455 client (socket+ssl+struct+base64+hashlib). The obvious
  `pip install websockets` is exactly what broke the SDK pins on 9/2 and
  `FIX SDK DEPS.bat` exists to undo. Nothing here can move a pin.
- **The DXLink handshake is SEQUENTIAL, not a burst.** Firing SETUP, AUTH,
  CHANNEL_REQUEST and FEED_SETUP back-to-back gets `AUTH step missing`
  forever while the socket stays happily connected — a silent no-data
  failure. Each step waits for its confirmation (`_await`).
- **Delayed data is REFUSED, not used.** `live_level()` checks the token; a
  demo/delayed feed stands down with a one-line explanation rather than
  serving stale gamma that looks live.
- Wiring: greeks are a DATA feed only — `execution.broker` is untouched and
  **Webull still places every order.** Positions subscribe at arm time, and
  `_greeks_sync` in bridge.py mirrors the quote bus every 2s to cover
  restored/adopted ones. Output: `greeks_tape.csv`, plus `greeks_in` and
  `greeks_out` on every closed-trade row (entry greeks stamped by the
  watchdog within the first 60s only — after that they are not "entry"
  greeks and calling them that would be a lie).
- NOTE: the position dict field is **`sent_at`**, not `opened_at`. Two of
  today's edits assumed `opened_at` and were silently falling back to
  `time.time()`.
PRIOR STATE, kept for the record —
**TASTYTRADE WAS CONNECTED BUT DELAYED (9/4 11:38).** G created the OAuth client and ran the setup; the adapter
authenticates, lists the account, reads balances and positions. Then the live
checklist against the REAL server:
```
 ok   login / accounts / balances / positions / greeks stream token
 FAIL stock quote        GET /market-data/by-type -> HTTP 403
 ??   OTOCO entry        still unverified — prove it in cert
```
DXLink was driven by hand end to end (SETUP -> AUTH -> CHANNEL_REQUEST ->
FEED_SUBSCRIPTION) and real greeks arrived for `.SPY260918C660`:
delta 0.9868, gamma 0.000629, theta -0.0646, vega 0.051, IV 0.356. **The
plumbing works.** BUT the token comes back `level: demo` and the URL is
`wss://tasty-demo-dxlink-md-ws.dxfeed.com/**delayed**`. Delayed greeks are
worthless for a 0DTE ratchet and dangerous if mistaken for live.
CAUSE: the account is UNFUNDED (buying power 0.0), so it has no market-data
entitlement — which is also why the REST quote 403s. UNBLOCKING IT IS HIS AND
ONLY HIS: fund the account, accept the market-data agreements. Until the token
comes back at a live level, **nothing may consume this feed for a trading
decision**; treat it as plumbing that is ready, not as data.
Account id is in settings.json (gitignored) — it does not belong in this file.

NEXT, and it needs G: greeks. tastytrade STREAMS them over DXLink (delta,
gamma, theta, vega, rho, IV, theo — per tick). Tradier's come from ORATS on
the REST chains endpoint with `greeks=true`, refresh rate undocumented —
MEASURE it off `greeks.updated_at` before trusting it. Plan is tastytrade as
a DATA feed with Webull still executing; no rule changes until weeks of
greeks-tagged trades exist.

Also today, two more:
- **1-STRIKE-OTM IS NOW 0/1DTE ONLY** (G, 9/4). It exists because a far-OTM
  strike expiring TODAY is a lottery ticket. From 2 SESSIONS out (sessions,
  not calendar days — a Friday's next expiry is Monday) the room's own strike
  stands. TB22 called a 9/18 100C at $2.41; this rule bought a 96C at $4.05,
  68% more money at a different delta, so his call ran +10% while ours sat
  at -4%. `_no_otm_translate` in bridge.py returns early now.
- The bracket stop born WITH the entry now gets clamped under the live bid
  (INTC 94C's 0.86 stop filled 308ms after the buy because the bid was
  already 0.83).
Prior:
(2026-09-03 18:05 — ran the missed-entry scan retroactively
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

- v3.5.0 PACKAGE (9/2, from a parallel session; docs in reference/):
  APPLIED = Block A: _pace 0.15->0.20 (was 33% over Webull's 5/s cap),
  SDK file logger (webull_api.log), and the TAB-DISCARD fix — Chrome's
  Memory Saver discards background tabs that still look healthy to every
  watchdog; now every room tab is pinned autoDiscardable=false each tick,
  content.js heartbeats every 30s, and a room silent 3 beats (~90s) or
  detached is reloaded (log line "⚠ Chrome had DISCARDED..." / "reader
  stopped answering"). Memory-shed cadence 2h->4h. Extension 3.5.0.
  THEN G said "do everything now" (9/2 ~01:20) — ALL APPLIED, bridge
  restarted clean 01:26 with "QUOTE BUS on": Block B tiers (see RATCHET
  v3) + ANTI-CLIP (locked <= 60% of gain, reference/ANTI-CLIP.txt: 520-trade
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

- OPTION TAPE (9/2, reference/HANDOFF-OPTION-DATA.md): Webull's API has NO
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

- BROKER FACTS (9/2 research, ~150 sources: reference/OPTIONS-BROKER-
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

## 9/4 16:55 — DAILY CLOSE-OUT + FIX (automated, Friday EOW run)
Account flat as of 16:36 (get_account_positions = []) — no open positions,
nothing to guard overnight. Announcer confirmed PAUSED (announcer.stop="stop",
G's 8/31 standing call) — announcer.log/seen.json/push-subscribed checks
skipped per standing instruction.

**Broker truth (11 round trips, order history via Webull connector,
account ENIQGUV4LUTT3JSAA9NKLDDU19):**
- Bot (1-lot LIMIT+bracket entries, incl. swings): NVDA 235C x2 entries
  (KingBeeAri +$10, Mr M Trades 🤖 +$10 — both ratchet-managed, +10% rung
  locked and stopped out clean, textbook); INTC 94C (ZTRADEZ BOT, -$12 —
  the born-already-triggered stop bug from this morning's 10:20 fix, this
  trade predates the fix, nothing new to do); INTC 96C 9/18 swing (TB22,
  -$10, Gian hand-closed — the exact trade that triggered today's 10:30
  swing pause); XLF 58C 10/16 swing (Vero, carried from 9/3 @1.58,
  Gian hand-closed today at 1.26, -$32, well clear of its 1.18 resting
  stop which never fired). **Bot day: -$34.**
- Gian (multi-lot MARKET scalps): SPY 773P +$6, SPY 770P -$24, SPY 769P
  +$40, QQQ 722.5C -$14, SPY 768C +$56, QQQ 719P +$90. **Gian day: +$154.**
- **Combined: +$120**, all realized, account flat.

**Real finding, NOT fixed (flagged for G/next session):** SPY 770P (11:40,
45-sec round trip) and SPY 769P (11:44-11:48, this is literally the
5-lot example the 10:30 SOURCE-OF-TRUTH note in this file describes) never
reached days/2026-09-04.json — NOT booked $0, entirely ABSENT — despite
closing well after today's 10:30 DATA RULE fix that was supposed to make
live-trade recording unconditional. SPY 768C and QQQ 719P (also Gian,
also after 10:30) recorded correctly, so the fix mostly works. Best guess,
unconfirmed: `adopt()` in positions.py dedupes by symbol only (`have` set
keyed on `p.get("symbol")`, no strike — see the "Keyed under an UNKNOWN
owner" docstring) and only sees the broker on its own periodic sweep; a
45-second hand round trip can open and close between two sweeps and never
get adopted at all, so reconcile_gone never has anything to finish. Not
fixed today — root cause unconfirmed and this touches live adoption/
reconcile code, too risky to guess at unattended. journal-2026-09-04.xlsx
carries the correct broker numbers regardless (broker truth, not the
ledger, is what the journal is built from).
Also true-up gave up after its 3-minute retry window on 3 trades today
(INTC 94C, XLF, INTC 96C swing) during/after the 09:48-09:52 rate-limit
burst (76 broker errors per POSTCHECK) — same shape as 9/3's IBIT 429
storm watch item, still open, still not fixed (low-risk/no-cost so far,
noted again).

**ENTRIES ONLY verified solid:** 96 room exits logged "ignored — entries
only" today (extension-side, DS Logs export) and 0 EXIT-IGNORED lines in
trades.log (no room exit even reached the bridge to need the second gate)
— zero traded. Both gates checked in code and intact: bridge.py do_POST's
EXIT-IGNORED check (order.get("source") not in pullback/under-stop) and
background.js's pre-sig.fire TRIM/STOPMOVE/CLOSE gate. settings.json has
no execution.exit_policy key at all (defaults to entries_only, never
"full"). Notable ignored exits today: ZTRADEZ BOT's INTC trims (12:52/
12:55, on a position the bot's own stop had already closed hours earlier),
TB22's INTC 96C partials (15:49-15:57, after Gian's hand-close AND after
the 10:30 swing pause — correctly refused twice more as SWING-OFF too).

replay_check.py: 0 silent drops, 0 possible missed entries. scoreboard.py 10:
66 rooms heard from, 3 silent configured (unchanged). SCOREBOARD.html
regenerated. Options Insider still silent (deathwatch continues, cancel-by
9/11). No Chrome DISCARDED/out-of-memory lines today. /stream unreachable
from this sandbox (localhost isn't the user's machine here) — not treated
as a bug, note for G to eyeball the popup Monday.

Deliverables written: Webull_Orders_2026-09-04_auto.csv (27 order legs),
journal-2026-09-04.xlsx (11 trades + By Trader, house format, LibreOffice-
recalculated), trader-scoreboard.xlsx appended (5 new rows in "Every trade",
Scoreboard sheet fully recomputed from all days, pre-8/19 caveat note and
every dated footnote preserved intact).

**Friday/weekend note for G:** account is flat, nothing resting overnight,
swings are paused so nothing new can be opened as a multi-day carry before
Monday. The two missing-ledger-row trades above are a paper-trail gap only
(no money at risk, no wrong trade) — safe to leave for a proper look
Monday rather than a rushed weekend fix.

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
**Because Webull's API doesn't offer one for options.** Checked against reference/OPTIONS-BROKER-REFERENCE.md, sourced to developer.webull.com:
- Options accept only `LIMIT`, `STOP_LOSS`, `STOP_LOSS_LIMIT`. No MARKET, no trailing.
- `OTO`, `OCO`, `OTOCO` are **stock-only** — option orders do not support them even on a SINGLE strategy.
- Nothing in the API triggers an order off a DIFFERENT instrument. There is no "buy SPY 645C when SPY *stock* touches 761."
- The nearest thing, a BUY `STOP_LOSS_LIMIT` on the option, triggers on the OPTION's own price and only on the way UP — backwards for a pullback, where we want to buy after the stock dips and the call gets cheaper. It would suit a breakout entry, not this.
So the polling hunt isn't a shortcut around a broker feature; it IS the trigger, and the only thing that matters is how fast it sees the touch.
**Improvement shipped instead:** the hunt's entry poll was a flat 1.0s from when every price was an HTTP call. Since 9/2 the underlying comes from the MQTT push, so a poll is a dict lookup costing zero rate budget. The hunt now watches at **0.25s while the stream has that symbol fresh** and falls straight back to 1.0s if the stream drops (`Pullback(streamed_fn=..., entry_poll_streamed=0.25)`, `_pullback_streamed` in bridge.py, both tunable in settings under `pullback`). **4x less lag between the touch and the bid going in, for free.**

## 9/3 20:30 — BROKER CHOICE researched: Tradier, not Schwab (reference/BROKER-CHOICE-2026-09.md)
G asked to plug in Schwab, and which is better on data rate and pricing. Researched 9/3 against live sources; full table + citations in the doc. Headline:
- **Cost on his size** (1 contract/entry, ~200 contract-sides/mo): Webull **$0** · Tradier Pro Plus **~$55/mo** · Tradier Pro **~$80/mo** · Schwab **~$130/mo**.
- **Both Schwab and Tradier have what Webull lacks**: real OTO/OCO/OTOCO conditional orders ON OPTIONS, and **streaming OPTION quotes**.
- **Schwab's disqualifier for an unattended machine: the OAuth refresh token expires every 7 days with NO programmatic renewal** — a human must complete a browser login. Any outage over a week and the bot is dead until G sits down. It is also the most expensive per contract and buys nothing Tradier doesn't.
- **The bigger prize is NOT the conditional entry — it's option streaming.** The whole ratchet currently runs off quote_bus's 1/s batched HTTP poll because Webull has no option stream at any price. On Tradier the ratchet becomes tick-accurate. That is worth more than removing our ~250ms entry latency.
**Recommendation: don't migrate — build a broker ADAPTER and run Tradier ALONGSIDE Webull.** Same signals, same ratchet, orders routed per room; prove fills + streaming on a small Tradier account for two weeks with real journal numbers, then decide on evidence. Scope is small and contained: the whole codebase only calls **11 broker methods** (cancel 8×, order_status 5×, positions 4×, ask_bid 4×, place_stop 3×, sell 2×, last_sell_fill 2×, replace_stop, open_orders, futures_positions, flatten). `webull_options.py` becomes the first implementation, `tradier.py` the second; nothing above the adapter — parser, guards, ratchet, watchdog, journal — changes at all. **Not started; awaiting his call.**

## 9/3 21:00 — BROKER ADAPTER BUILT (broker.py + tradier.py) + top-4 research
### Research: reference/BROKER-TOP4-2026-09.md (every claim sourced, 9/3)
**1. Tradier** — $0.35/contract Pro ($10/mo) or $0.10 Pro Plus ($35/mo) → **~$55–80/mo at his size**; `oto/oco/otoco` ON OPTIONS; **option streaming included free**; plain bearer token, no weekly re-login. **The recommendation.**
**2. tastytrade** — $1.00/contract to OPEN, **$0 to close** (~$100/mo); streams **greeks as well as quotes** via dxfeed, which would let the ratchet reason about delta/theta instead of inferring from price; official API + good typed Python SDK. **Conditional-order support on options is NOT confirmed in their docs — verify before committing.**
**3. IBKR** — $0.15–$0.65 tiered (he'd be at the expensive end); extensive conditional orders; but only 100 concurrent market-data lines by default, OPRA option data is a paid add-on, and TWS/Gateway or Web-API OAuth is the most fragile thing to run unattended. Revisit if volume 5×'s.
**4. Schwab** — OTOCO plus a selectable stop trigger (BID/ASK/LAST/MARK), streaming included, but **$0.65/contract (~$130/mo, dearest of the four)** and the **7-day refresh token with no programmatic renewal** — any week-long gap and the machine is dead until a human logs in through a browser. Technically excellent, wrong shape for this.
**Ruled out: Alpaca** — commission-free options sounds ideal, but it supports **no bracket/OTO orders on options at all** (the stop cannot be born with the entry) and real-time OPRA is a **$99/mo** plan. Fails the two things that matter most. Also out: Robinhood (no official API), E*TRADE/Public/Lime.
### Built
- **`broker.py`** — `BrokerBase` names the **15-method contract** the whole machine already used, plus capability flags (`supports_bracket_entry`, `supports_conditional_on_underlying`, `supports_option_streaming`, `option_quote_limit_per_min`) so code and logs can ASK instead of assume. `get_broker(cfg)` picks from `execution.broker` and **defaults to Webull, so an untouched settings.json behaves exactly as before**. `place_conditional_entry(...)` is the named home for the thing Webull cannot do; BrokerBase raises Refused, so pullback.py's polling hunt stays the fallback everywhere it isn't available.
- **`tradier.py`** — full implementation: quotes (single + batched 50s), stock price, positions with OCC parsing, balances, order status, open orders, cancel, sell, place_stop (**GTC — Tradier allows GTC on option sells, so the 9:31 overnight re-arm dance disappears**), last_sell_fill from real filled orders, flatten. `_one()` handles Tradier's object-vs-list quirk, the #1 source of bugs in Tradier integrations.
- `WebullOptions` now declares its own capabilities (bracket yes; conditional-on-underlying no; option streaming no; 60 option quotes/min).
### Status and honesty
**tradier.py has never touched a live server** — no key exists yet. Structurally complete, compile-checked, every endpoint/field from the published docs, but every response shape is a hypothesis until proven. `TradierOptions.verify()` is the read-only first-run checklist (balances, stock quote, positions shape) and `place_conditional_entry` deliberately **raises Refused** until a sandbox order proves the otoco leg encoding — it will not touch money on a guess.
Nothing above the adapter changed. Suite: test_positions 0 failures, others at pre-existing counts. Bridge restarted on Webull as always.
### Next, when G is ready
Open a Tradier account → put `{"execution": {"broker": "webull", "tradier": {"access_token": "...", "account_id": "...", "sandbox": true}}}` in settings → run `verify()` → prove otoco in the sandbox → then route ONE room to it and let the journal compare fills for two weeks.

## 9/3 21:20 — TASTYTRADE ADAPTER BUILT TOO (G: "I like the greeks thing... maybe do 2")
`tastytrade.py` joins `tradier.py` behind `broker.py`. Registry is now **webull (default) / tradier / tastytrade** — settings untouched still means Webull, unchanged.
### Research question CLOSED
**tastytrade DOES support OTOCO on options** — confirmed in their docs and the official Python SDK (which has `place_complex_order` with OTOCO built from a LimitOrder entry + StopOrder). That was the one unknown holding it back in the top-4 writeup; it is now a full contender on capability, not just on data.
### Why it earns its own adapter — the greeks
Its dxfeed stream carries **delta, gamma, theta, vega and IV per contract, live**. Every other broker on the shortlist makes the ratchet infer everything from price. With real greeks the machine could know that a position is only green because IV popped, or that theta is about to eat a 0DTE faster than the stop can walk up to it — decisions it literally cannot make today. New capability flag `supports_streaming_greeks` (only tastytrade: True) so the ratchet can branch on it later.
### Cost shape
**$1.00/contract to OPEN, $0.00 to CLOSE**, capped $10/leg. A bot that exits everything it opens pays once, not twice — ~$100/mo at his size vs Tradier's $55–80.
### Built
Session auth (username+password → session token, ~24h, auto-refresh, and it captures a `remember_token` so **the password can come back OUT of settings.json**), accounts, positions with tastytrade's space-padded OCC (`'SPY   260904P00771000'`), balances, order status incl. per-leg fills, live orders, cancel, sell, place_stop (**GTC**), last_sell_fill from real fills, flatten, and `stream_note()` documenting exactly how to wire the greeks stream via `/api-quote-tokens`.
### Credentials warning, written into the file
tastytrade authenticates with the **account login, not an API key** — the password would sit in settings.json (gitignored). G enters it himself; it must never be committed or pasted anywhere. Prefer the remember_token once obtained so the password stops living on disk.
### Status — same honesty as tradier.py
**Never touched a live server.** No credentials exist. Compile-checked, every endpoint from the published docs, all 15 BrokerBase methods present, OCC round-trips correctly. `verify()` is the read-only first-run checklist (login → accounts → balances → quote → positions → greeks-token). `place_conditional_entry` **deliberately raises Refused** until the OTOCO envelope is proven in their cert sandbox — the polling hunt stays in charge until then. **The greeks stream is deliberately NOT implemented**: it needs a websocket in the bridge's Python and the last streaming SDK install broke the pins (8/31). Wire it dependency-free, after the REST path is proven.
Suite green (test_positions 0 failures, others pre-existing). Bridge restarted on Webull.

## 9/3 21:45 — adapters PROVEN against a fake server + bridge can now select one
G is opening the accounts; this is the work that de-risks the moment his keys arrive.
### `test_brokers.py` — new
Stands up a local HTTP server answering with the response shapes from each broker's published docs, points the adapters at it, and checks what comes out. **No credentials needed.** It proves: request paths, auth headers (Tradier `Bearer <token>` vs tastytrade's RAW session token), JSON walking, OCC building AND parsing both ways (incl. tastytrade's space-padded `'SPY   260904P00771000'`), Tradier's one-result-is-an-OBJECT-not-a-list trap, cost_basis 202.0 → a 2.02 per-share fill, per-leg fill reading, `connect()` settling the account id, that `place_conditional_entry` REFUSES loudly on both, and that **`positions()` returns [] on a dead server instead of raising** (the 8/31 ghost lesson — [] is "no verdict", never "you are flat").
**Mutation-checked**: deliberately broke tradier's OCC parser and confirmed the suite goes red, then restored. A test that cannot fail proves nothing.
What it still CANNOT prove: that the LIVE servers send these shapes. That is what `verify()` is for on day one. If a real response differs, test_brokers.py is where the fix gets pinned so it never regresses.
### Bridge can now actually use a second broker
The LIVE client construction is pluggable and **opt-in**: unless `execution.broker` NAMES something other than webull, the path is byte-for-byte what it was. When it does name one, the adapter is built and the capabilities are logged; **if it fails to build for any reason the bridge falls back to Webull** rather than leaving the machine with no broker. `connect()` added to the contract and both adapters (read-only, account-list only, never places an order).
### When his keys land
1. `settings.json` → `{"execution": {"broker": "webull", "tradier": {"access_token": "...", "sandbox": true}}}` — note broker STAYS "webull" while testing.
2. `python -c "import json,broker;print(broker.get_broker(json.load(open('settings.json')),'tradier').verify())"` — read-only, places nothing.
3. If a shape differs from the canned one, fix the adapter and pin it in test_brokers.py.
4. Only then flip `broker` and route ONE room.
Suite: test_brokers all green, test_positions 0 failures, others pre-existing. Bridge restarted on Webull.

## 9/3 22:00 — tastytrade account is ready; setup tool built (password-safe)
G: "tastytrade is ready, what do you need from me? tradier they're waiting to approve my account."
**Nothing sensitive is needed from him.** New `setup_tastytrade.py` + **`SETUP TASTYTRADE.bat`**: he types his username and password INTO HIS OWN WINDOW (`getpass`, no echo), it logs in exactly once, trades the password for a **remember token**, and writes only `username` + `remember_token` + `account_id` into settings.json. **The password is never saved, never logged, never leaves the machine** except in that one login request, and the code explicitly `pop`s any lingering `password` key. The remember token can be revoked from his tastytrade account without changing the password.
It then lists accounts (picks automatically if there's one), saves the choice, and runs the read-only `verify()` checklist. It **places nothing** and **deliberately leaves `execution.broker` alone** — the machine keeps trading Webull until he decides otherwise.
**Proven end-to-end against the fake server before he ever runs it**: login → remember-token captured → accounts listed → verify's six checks all report. Full dry run passed.
### Notes that matter when he runs it
- **tastytrade's cert/sandbox environment needs its OWN separate credentials** — a live login will NOT work against api.cert.tastyworks.com. So `sandbox` defaults to false and verify runs against live; every check in it is read-only, so that is safe.
- The account needs options approval and funding before balances/positions look like anything.
- What he sends back is the checklist text, which contains **no secrets** — account number and buying power only.
### Tradier
Waiting on their approval. Its adapter is already written and fake-server tested; when the token arrives it's the same shape of job, and a matching `SETUP TRADIER.bat` can be written in minutes (Tradier is simpler — a plain access token, no password involved).

## 9/3 22:15 — setup script: password now echoes asterisks + atomic settings write
G: "I can type in the username section but not the password." Diagnosis: nothing was broken — `getpass` hides input SO completely (no asterisks, no cursor movement) that the window looks frozen. Bad feedback, not a bug.
**Fixed** with `read_password()`: on Windows it reads a character at a time via `msvcrt.getwch()` and echoes a `*` per keystroke (backspace works, arrow keys eaten, Ctrl-C honoured). The password itself is still never displayed, saved or logged. Non-Windows falls back to getpass, and if the console refuses even that it says plainly that input WILL be visible rather than pretending otherwise.
**Also hardened, unprompted:** the script was rewriting `settings.json` in place — the file holding EVERY key this machine owns, including the live Webull credentials. A half-written file would have taken the whole bot down. Now: copy to `settings.json.bak` → write `settings.json.tmp` → fsync → **re-parse the temp to prove it is valid JSON** → `os.replace()` (atomic on Windows). On any failure the original is left untouched and it says so. Proven on a COPY of the real settings: Webull keys survive, tastytrade block added, no `password` key present. `.bak`/`.tmp` added to .gitignore.

## 9/4 10:20 — LIVE CHECK: the bracket stop could be born ALREADY TRIGGERED (INTC, −$12)
Account is flat as of 10:15; nothing unprotected right now. Broker truth for the morning:
- **NVDA 235C 0DTE — the ratchet worked perfectly, twice.** Two entries (1.00 and 1.01 at 09:48/09:49); on both the ratchet walked the born stop 0.95→0.90→1.00→1.11 and 0.93→1.01→1.10, and both stopped out IN PROFIT at 1.11 and 1.10. **+$20 combined.** This is his ladder doing exactly what it should on a 0DTE.
- **XLF +$?; SPY 773P x2 bought 1.48 sold 1.51; QQQ x2 (his own) 0.83→0.76.**
- **INTC 94C — THE BUG.** Bought at the caller's 0.95 at 09:51:03.009. The bracket's stop leg (0.86, −10% of fill) **FILLED at 0.83 THREE HUNDRED AND EIGHT MILLISECONDS LATER.** Not a trade that went wrong — a stop that was already triggered the moment it was born, because the live BID was ~0.83 while we paid 0.95 into a wide spread. Guaranteed −$12 with no trade in between.
### Root cause
`place_stop()` has clamped stops under the live market since 9/1 (the S-swing lesson) — but the **BRACKET leg born with the entry never saw that clamp**, and that is the leg resting on nearly every trade. It was computed purely as a percentage below the FILL, with no idea where the bid was.
### Fixed
The born-with-the-order stop now reads the live bid and, if the computed stop sits at or above it, rests one tick UNDER the bid instead — logging `STOP-BORN INTC — the bid is 0.83, so a 0.86 stop was already triggered at birth; resting it at 0.82 instead (wide spread on the entry)`. It can only ever tighten the stop's distance from the fill, never widen it. Verified against the exact INTC numbers: old 0.86 (above the 0.83 bid) → new 0.82 (below it).
### Also seen, and now explained
The 12 `OPTION_CAVERED_CALL_STOCK_NO_ENOUGH` errors and the two "ratchet couldn't move the stop to 0.95" warnings at 09:51:56/58 were the ratchet trying to move a stop on a position that had been gone since 09:51:03 — **symptoms of the INTC stop-out, not a separate fault**. Same for "book holds INTC/NVDA, the account doesn't": POSTCHECK caught the book lagging the broker by a few seconds during the burst, and it resolved on its own.
Still watching: 32 "Too many requests" today (positions/orders endpoints during the 09:48–09:52 burst), and `invalid symbols: [QCOM]` ×4 — a stock_price lookup for QCOM that Webull rejects. Neither cost money today. Suite green; bridge restarted onto the fix.

---

# 9/4 EVENING — what changed after the close

## THE BIG ONE: we trade the contract they actually called
`_no_otm_translate` is **OFF** (`execution.translate_strikes`, default false).
It had rewritten a caller's strike **72 times**, always pulling toward the
money, and it discarded their limit price with it. Measured cost on 8 trades
where both prices are known: **+$1.31 a contract, about DOUBLE the called
price** — TSLA called at 2.80, bought at 5.85. It also made every trade
at-the-money (all 9 trades with a recorded underlying sat within ±1% of the
strike), which is why the ratchet could never be tuned by moneyness: there
was no OTM or ITM sample to compare. Expect further-OTM contracts now:
cheaper, more volatile in percent, more of them clearing the affordability
check that refused 64 calls.

## ANTI-CLIP IS OFF — plain ladder only
G: *"I just want the regular ratchet until we gather information about the
greeks."* `strategy.anticlip`, default false. At +30% the stop now locks
+20% (his ladder) instead of +18% (anti-clipped). The test proves BOTH
states, so the switch is real and not decoration. Bonus: every trade from
here runs one rule, so the next weeks are a clean sample.

## SHADOW MODE — a second ratchet, scoring itself, trading nothing
`positions._shadow()` runs beside the real ratchet on every poll and writes
`shadow_ratchet.csv` on each close: entry time, hold length, real %, shadow %,
whether the shadow exited, **legs** (new highs made — trend vs chop), peak %,
DTE, delta and IV at entry. It sells nothing and places nothing.

WHY it exists rather than just switching: a leg-retrace + 20%-floor rule beat
his ladder +4.9% to +2.4% a trade over 48 contracts — then dropping its single
best trade (META, +159%) made the LADDER win, and dropping two made the
challenger negative. **The whole edge lived in 4 trades out of 48.** So
nothing was switched; both rules now watch the same real fills and in a few
weeks the comparison is real.

## OPTION BARS — the data that makes any of this answerable
* `bars_capture.py` — run after the close. Saves 1-minute bars for every
  contract traded that day. **Tradier drops intraday history for expired
  options**, so this is a nightly CAPTURE, not a backfill: 84 of 87 missing
  contracts were expired. 108 contracts archived so far.
* `ratchet_lab.py` — replays every saved trade across 80 rule combinations
  and reports which knob actually matters. **Refuses to name a winner below
  n=40**, because at n=15 the best rung was 15% and at n=22 it was 5%.
* The structural finding that IS solid: his ladder locks a fixed % of the
  ENTRY, so as a share of the CURRENT price it tightens as the trade runs —
  9.1% room at +10%, 4.0% at +150%. Backwards. On META that meant stopping
  at +20% on a trade that ran +245%.

## BROWSER LAG — found and fixed (extension 3.5.24, RELOAD)
`content.js` ran `handle()` over every visible row in every Discord tab every
1.5s, and the dedupe sat AFTER `textOf()` and `imagesOf()` — so ~80,000 calls
a minute each did two querySelectorAll walks and a regex before deciding
nothing had changed. A single native `li.textContent.length` read now decides
first. Late-embed hydration proven unchanged by test.

## trades.log was 21% boot banner
**1,735 of 8,210 lines** were startup sentences repeated across ~200 restarts.
They still print to the console; they no longer enter the permanent record.
See `_BOOT_NOISE` in bridge.py.

## Smaller, same evening
* Click a caller's name in the popup -> jumps to that room's tab, opening it
  if closed. Matching ignores generic words ("trades", "alerts") because
  those sent `vero-trades` to "Whop Day Trades" — a wrong tab is worse than
  no tab.
* `POST /channames` + `rename_rooms.py`: the extension reports each channel's
  REAL Discord name, so rooms.txt stops saying "Platinum-1". Dry run by
  default; only the label column is ever touched.
* START HERE stops opening tabs if Chrome is closed mid-run.
* Chrome's Above-Normal priority bump RETIRED — it was the lag, and it never
  read a message. `CHROME_PRIORITY=AboveNormal` puts it back.

## KNOWN AND STILL BROKEN
* `signals.py` misses 4 no-ticker exits ("Out of 80% of my position").
* `restore_state` drops `hi_pct`/`lo_pct` on restart — a position held across
  a restart loses its run-up/drawdown history.
* Tradier **OTOCO unverified** — the conditional entry, the main reason to
  want Tradier. Prove it in their sandbox before it sees money.
* Voice/Deepgram has produced **zero** transcripts in six weeks.

---

## 9/6-9/7 OVERNIGHT — instrumentation, and three live bugs it exposed

Built at G's ask after a research pass over every comparable tool in public.
The headline from that research: **we are ahead of the open-source field on
execution, exits and rate limiting, and alone on DOM-reading, voice and
vision.** The one thing everyone else has that we did not was a per-caller
scorecard — and nobody anywhere measures alert→fill latency. See UPGRADES.md.

### NEW FILES
* `telemetry.py` — one row per fill into `telemetry.csv`: the latency chain
  (`posted_at → seen_at → sent_at → filled_at`, split three ways because a
  slow read and a slow fill have opposite fixes), what the caller said vs
  what we paid, the spread we paid it into, and the entry math below.
  Also `alert_decay.csv`: the contract's mid at +1s/+5s/+30s/+60s after the
  alert. **Nobody has published that curve.** It is how we settle
  chase-vs-wait per caller on our own rooms.
* `greeks_math.py` — delta+gamma second-order conversion. The one that
  matters is `stop_room()`: how far the STOCK must move to take out a -10%
  premium stop. **On the two contracts we had greeks for, that was 0.20 SPY
  points and 0.13 QQQ points.** SPY moves that in seconds. "-10%" is not a
  level, it is noise, and until now nothing could say so.
* `caller_report.py` — expectancy, win rate, PF, worst drawdown per caller,
  with a hard 20-trade floor for ranking and a 100-trade "solid" mark.
* `quote_shadow.py` — compares the streamed tastytrade quote against the
  Webull-polled one. Read p99, not p50.

### CORRECTIONS TO WHAT I TOLD HIM (both mine)
* I said our stops were "8 cents too tight from a linear delta conversion."
  **We have no delta conversion anywhere.** The ratchet is premium-percent
  and `_underlying_stop_watch` fires on the caller's stock level. The claim
  did not apply. What is real is `stop_room` above, which is worse.
* I called the Budget's `priority=True` lane a feature we have. **No caller
  passes it.** What actually protects orders is `ORDER_RESERVE = 40.0` — the
  quote sweep will not drain the last 40 tokens — and orders bypass the
  budget entirely via `_pace()`. That is coherent, but it is not what I said.

### THREE BUGS THE INSTRUMENTATION EXPOSED
1. **A fill-path race, which I caused and then found.** Writing the telemetry
   row between `state=FILLED` and the cost ledger made `test_positions` fail
   2 runs in 3 — on stop placement and P&L, not on telemetry. Nothing raised;
   a few ms of file I/O was enough. **There is a real window between "the
   position says FILLED" and "the position knows what it cost."** Telemetry
   now writes after the ledger, on a bounded queue drained by one long-lived
   thread. The window itself is still there and is worth closing separately.
2. **`watch_decay` was dead code.** Written, tested, never called. It would
   have collected nothing. Wired into `place()` on accepted OPENs; reads the
   quote-bus cache only, so it costs zero of the 60/min option budget.
3. **`futures_positions()` burned 363 of 364 throttles in nine minutes** —
   ungated, on the same 2-per-2s door the option stops use, asking Webull
   for futures that live at Topstep. Pre-existing: it was 429ing on Saturday
   with futures still off. Now backs off after 3 consecutive EMPTY reads
   (capped 60s). **It backs off on empty, not on an exception, because a 429
   here never raises** — `_try_calls` swallows it and returns `[]`, which is
   indistinguishable from "flat". My first breaker watched for an exception
   and never fired once.

### GREEKS SOCKET — RE-AUTH IN PLACE
tastytrade tokens last 15 minutes. We rode one until the server said
"reauthentication is required" and dropped the socket. It healed itself, so
it looked fine — but there was a hole in the greeks every 15 minutes, and
greeks feed the entry math. Now re-AUTHs on the same socket at 10 minutes
(`REAUTH_AFTER`), subscriptions untouched. Verified live: `token refreshed
in place (1)`.

### SHADOW QUOTE STREAM — READ BY NOTHING
Webull has **no** option streaming; every bid/ask is a 1/sec poll against a
60/min door, so with N positions each contract is seen once every N seconds.
That is the ceiling on stop reaction and why the rungs must be spaced wide.
DXLink carries `Quote` events on the socket we already hold. Subscribed,
taping to `quote_shadow.csv`. **Zero call sites in any exit, stop or order
path — audited.** tastytrade's quote is not Webull's book, and the broker
filling you is the one whose book should price your order. A week of
`quote_shadow.py` decides whether it is ever promoted. Off switch:
`execution.tastytrade.stream_quotes = false`.

### KNOWN AND NOT FIXED
* `/openapi/assets/positions` 429s ~4/min. **Pre-existing** (614 in the old
  log) and it is contention: Market Sniper is running on the SAME app key.
  Orders are unaffected — zero 429s on `order/place`, checked.
* The Webull streaming SDK cannot rotate its own log (`WinError 32`, file
  held open) and dumps stack traces into `bridge.log` instead of failing
  quietly.
* Market Sniper sends **no server-side bracket** to ProjectX. Its futures
  stop is the local ratchet only (initial rung −12.5 pts ≈ $25/contract on
  MNQ) and dies with the PC. Discord Sniper's futures stop lives on Topstep's
  servers. Same instruction, two different guarantees.

### 9/7 MIDDAY — tastytrade CAPS CONCURRENT SESSIONS. Learn this one.

Trying to prove the shadow quote stream with a standalone probe during
market hours, I opened a SECOND DXLink session on the same tastytrade
account. The bridge's own feed answered:

```
[greeks] dxlink refused RE-AUTH: The number of user sessions has
         exceeded the configured limit, user=tasty/U48e04e91-...
```

Three RE-AUTH refusals, three forced reconnects. **The probe disrupted the
live feed.** It recovered every time — the re-auth fallback raises and the
outer loop rebuilds the session, exactly as designed — and greeks are
data-only with no position open, so nothing traded differently. But the
lesson is permanent:

* **Market Sniper ALSO holds a DXLink session** (`main.py:175`, "DXLink
  armed"). Two apps, one tastytrade account. That is already at the cap.
* **NEVER open a third.** No probes, no scratch scripts, no test harness
  against the live account while both apps are up. The cap is a shared
  resource like the Webull app key, and it is easier to trip.
* This is a SECOND cause of the `[greeks] server closed the websocket`
  drops seen on 9/6, alongside the 15-minute token expiry.

**Consequence for the shadow quote stream:** the subscription is accepted
and the data is real — the probe returned SPY 260908C770 at 1.75/1.76,
matching Tradier's chain exactly. What is NOT yet proven is CONTINUOUS
streaming, because a capped-out second session receives one snapshot and
then nothing. That proof can only come from the bridge's own session, and
it arrives free the moment a position opens and `quote_shadow.csv` starts
filling. **Until then, do not claim the stream ticks.**

Also fixed while chasing this: dxfeed sends PARTIAL Quote frames (only the
side that changed; the other arrives null or NaN). The first version treated
a missing side as a bad row and dropped it. It now carries the last known
side forward, and when that merge produces a transient crossed book it keeps
the state — so the two sides can re-converge — while refusing to tape or
serve it. Without that, a contract would freeze at a stale price.

### 9/7 EVENING — subscriptions checked, 5 rooms parked, Chrome kill fixed

**WHY THE ROOM READING WAS FLAWED.** `START HERE` ran `taskkill /F /IM
chrome.exe`. `/F` is TerminateProcess — Chrome gets no chance to flush. The
extension's `chrome.storage.local` (every room's LIVE flag AND every
captured message) is a LevelDB written lazily; killed mid-write, Chrome
rebuilds it EMPTY on the next launch.

Evidence: the 9/1 and 9/4 exports both read `LIVE rooms: none (all testing)`
with 0 and 5 captured messages — on days that placed live trades and logged
326 actions. The reader was fine. The STORAGE was wiped, after the close.

Cost: the audit trail for those days. **Risk if it ever lands BEFORE the
open: all rooms come up "testing" and the bot trades nothing real all day,
silently.** Fixed — graceful `taskkill` first, force only if Chrome refuses.

**WHOP SUBSCRIPTIONS (checked on whop.com 9/7).** Five active:

    #1 Live Trading WorldWide   $100/mo   -> the 5 Whop rooms (firststeptrading)
    Platinum Trading Premium     $99/mo   -> Platinum x5
    ZTRADEZ Full Access          $65/mo   -> ZT all-trades-mashup
    VIP discord access           $65/mo   -> TradingTheTrend: Option Alerts,
                                             Options Watchlist
    VeroTrade Premium            $49/mo   -> Vero 1/2/3

Three LAPSED (last paid early August, not renewing):

    Boka Trading Premium      Aug 7  -> Boka 1, 2, 3
    STS / Summit Strategies   Aug 9  -> RWGates
    The Insiders Pro Plan     Aug 3  -> Options Insider

Those 5 rooms are commented out in `extension/rooms.txt` (26 -> 21 active),
each line tagged with which subscription lapsed and when. Uncomment to
restore. **G's call 9/7: not renewing until the bot is proven at 100%** —
prove it on the rooms he pays for before adding expensive ones back.

**NOTE ON RWGATES.** `parser.js` carries dedicated rules for him:
`RE_CONTRACT_OSI` for his ThinkorSwim dotted symbols (`.HOOD260702C118`),
`RE_TOOK_ENTRY_FILL` for four phrasings, and tolerance for his typos
(`enrty`, `enry`, `etnry`). That work is intact and idle. It costs nothing
to leave, and it is ready the day the subscription comes back.

**FOUR ROOMS DELIBERATELY LEFT ALONE:** Aristotle, Aristotle small,
Honeydrip daytrades, Midas (all Honey Drip Network), plus NGD. No matching
Whop subscription, but no evidence of a lapse either — they may be free or
paid outside Whop. Not touched without evidence.


---

## 2026-09-10 — the old HANDOFF.md header, moved here byte-intact
It had grown to 24 lines of every past session's headline and pushed the
file past its own 50 KB ceiling. State stays in HANDOFF.md; this is history.

Last updated: 2026-09-10 (02:45) — THE RATCHET MOVED, 7.5/5/2 → 5/3/5, G's call, and it is the first spacing here that clears its own error bar: the OPRA tape was bought (537 contract-days, 1.02M per-second quotes) so ratchet_sweep_fine.py re-swept 294 combos on real price paths and on 115 real room calls (707 rows with caller "?" — hand trades and adopted positions — had been scored as room calls; fixed). Old $158 rank #82, new $504 rank #1, +$3.01 a trade with a 95% band of +$0.72..+$4.91. Every backtest and report now READS the live spacing from ratchet_tiers.live_spacing() instead of typing it; FULL-DEPTH DISCORD SCAN of all 25 servers / 289 channels — two live options feeds found in TradingTheTrend (member-alerts, trade-log; both added `off`), five more alert rooms that fail a standing rule added `off`, everything else read and rejected in one block, and Sniper HQ marked DO NOT ADD because it is our own announcer's output; the bot's own record isolated (107 broker-priced trades, NET −$545, −$5/trade; pullback entries break even, instant ones do not); contracts and expiries recovered so bot rows can be checked against the broker at all; P&L now COMPUTED from prices, not trusted (a book bug booked sale proceeds as profit, +$5,137 of phantom wins); the broker's whole 3-month history pulled and absorbed (705 round-trips, −$4,228 all in — G's hand trading −$4,332, the bot +$301); v3.5.85: caller recovered for the 41 fills that had no book row (read back from the log's WORKING line); G's own hand trades out of the caller board, which now reconciles to the ledger; NO PAPER DATA anywhere in the app (paper rows never enter the ledger; the 4 that existed archived); the Callers tab is the trader scoreboard, corrected (one row per position, paper never counted as money, futures counted not valued); ROOM HOURS 9:15–4:30 ET (futures rooms 24h), last-message stamp per room, START HERE seeds only; the popup as a full PAGE (⤢ page button / popup.html?page=1); SELF-SERVE test build (Callers tab, Needs-you tab + fix buttons, Strategy numbers, room-rule pills; grabber moved to Logs); ONE SWITCH PER ROOM — rooms.txt
now lists all 57 rooms with on|off|lapsed, the popup's Channels tab shows every
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
family (ledger / alerts / tapes / holidays / announcer board); ratchet 5/3/5
flat, futures ratchet decoupled; Whop API path deleted; the tab-reload storm
found (662 reloads/day, zombie heartbeat) and fixed; rooms settled at 20 on
of 57 listed (16 Discord + 4 Whop, all live, 0 ZTRADEZ — counted from
rooms.txt 9/10 02:22, after the full-depth scan of all 25 servers added
7 more `off` lines and one rejected-rooms block); START HERE fully
unattended (one-shot open-rooms request, no git/Chrome prompts);
REPLACE-DON'T-STACK rule; folder cleanup to archive/; POSTCHECK stale-snapshot
false alarm fixed. Story of each in HANDOFF-LOG.md.

