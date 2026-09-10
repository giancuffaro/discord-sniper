/* test_word_order.js — THE TOKENS CAN ARRIVE IN ANY ORDER (9/10).
 *
 * G, walking me through TheArchitech's room: "it doesn't matter the order of
 * the expiration or the price or the ticker. It's not relevant. It could be in
 * any order." Three of his four formats put the ticker LAST and every one of
 * them died as "nothing in it that means buy or sell", while the same content
 * written the ordinary way parsed perfectly. A pure word-order gap.
 *
 * WHAT THIS FILE HOLDS DOWN
 *   1. the any-order reader works, in rooms flagged `bare`
 *   2. it is SCOPED — the first cut of it fired "TSLA 9/4 360P .72" in every
 *      room on earth, because the three tokens strip out separately and leave
 *      nothing behind. test_bare_entry.js caught it. This file keeps the scope
 *      honest from the other side.
 *   3. two strikes in one call become TWO orders (G: "when you have
 *      multistrikes, just buy both of them. Buy two contracts, one of each.")
 *   4. the two rooms added the same day still read with NO rules at all
 */
const path = require("path");
const { parseSignal } = require(path.join(__dirname, "parser.js"));
const BARE = { entry_no_verb: true };
const SPXROOM = { entry_no_verb: true, default_symbol: "SPX" };
let bad = 0;

function show(label, got, want) {
  const ok = got === want;
  if (!ok) bad++;
  console.log("  " + (ok ? "PASS  " : "FAIL  ") + label.padEnd(24) + got +
              (ok ? "" : "   (wanted " + want + ")"));
}
function read(msg, cfg) {
  const s = parseSignal(msg, cfg || {});
  if (!s || !s.action) return "silent";
  let out = s.action + " " + (s.symbol || "?") + " " + (s.strike == null ? "?" : s.strike) +
            (s.side ? s.side[0] : "") + (s.expiry ? " " + s.expiry : "");
  if (s.also && s.also.length)
    out += " +" + s.also.map(a => a.strike + (a.expiry ? "@" + a.expiry : "")).join("/");
  if (!s.fire) out += " [held]";
  return out;
}

console.log("ANY ORDER, in a `bare` room:");
show("ticker last, dated",   read("8/24 $255P $AMZN", BARE),        "OPEN AMZN 255P 8/24");
show("ticker last, no date", read("$255P $AMZN", BARE),             "OPEN AMZN 255P");
show("date first, DTE",      read("2DTE $765C SPY CALLS", BARE),    "OPEN SPY 765C 2DTE");
show("ticker first",         read("$AAOI 9/25 $130C SWING small", BARE), "OPEN AAOI 130C 9/25");
show("strike only + DTE",    read("7730C 0DTE", SPXROOM),           "OPEN SPX 7730C 0DTE [held]");

console.log("\nTWO STRIKES = TWO ORDERS:");
show("bare, next fri",  read("$NVDA $225C/ and $230C NEXT FRI Starters", BARE), "OPEN NVDA 225C +230");
show("with a verb",     read("bought NVDA 225c and 230c", {}),      "OPEN NVDA 225C +230");
// A call and a put together is a STRANGLE, a different trade. It is not
// paired — and it is not half-traded either: the put is left standing in the
// leftover, so the whole line refuses. Buying only the call would be picking
// one leg of somebody's two-sided trade, which is not the trade he called.
show("call + put refuses", read("$NVDA $225C and $230P", BARE),     "silent");
// Mugzone's take-profit ladder is three numbers in a row and must never be
// read as three more contracts to buy.
show("TP ladder ignored",
  read("MU 1020 9/11 CALLS @ 2.2 SL 1.45 TP 2.6 / 3.3 / 4.4", {}), "OPEN MU 1020C 9/11");

// AbTrades posts two whole contracts, same ticker, DIFFERENT expiry and
// price, in one message. Shape 1 cannot see it (the strike is identical) and
// the old reader traded only the first — half of what he called.
show("two expiries",
  read("$APLD 10/16 30c 2.75 1/4th size $APLD 9/18 30c .9 Lotto size", BARE),
  "OPEN APLD 30C 10/16 +30@9/18");
// Two DIFFERENT tickers on one line is a levels row or a watchlist, never a
// pair of orders.
show("two tickers never pair",
  read("$AMZN 11/20 300c 4.8 $GOOGL 11/20 370c 8.3", BARE),
  "OPEN AMZN 300C 11/20");

/* THE NEAR-DISASTER (9/10). The first cut of the ticker-after-the-contract
 * reader was replayed against 11,187 real room messages: it produced 14 new
 * entries and THIRTEEN were ordinary words turned into tickers. NEX and FOR
 * are REAL LISTED SYMBOLS, so the optionable list would have waved them
 * through and bought a contract nobody named. Every line below is verbatim
 * from the logs. They must never read, even in a `bare` room. */
console.log("\nWORDS ARE NOT TICKERS (verbatim from the logs):");
show("BREAK 4.65",   read("revising $338,00 BREAK 4.65", BARE),                    "silent");
show("July 31st - 48", read("buy DOCU Calls July 31st - 48", BARE),                "OPEN DOCU");
show("cally spy",    read("$776C cally spy TUESDAY", BARE),                        "silent");
show("levels prose", read("772.35 - 772.40 has to hold for a push to 773c", BARE), "silent");
show("out breakeven", read("NVDA OUT BREAKEVEN NO LOSS but 220c", BARE),           "silent");

console.log("\nSCOPED — the same lines must stay SILENT with no room rule:");
show("ticker last",     read("8/24 $255P $AMZN", {}),               "silent");
show("date between",    read("TSLA 9/4 360P .72", {}),              "silent");
show("chatter",         read("NVDA 205C looks juicy", BARE),        "silent");
show("levels row",      read("QQQ 726c > 725.00 715p < 716.00 MU 1000c > 980.00", BARE), "silent");

console.log("\nNO RULES NEEDED — Mugzone and FloridaMan read as written:");
show("mugzone",   read("MU 1020 9/11 CALLS @ 2.2 SL 1.45 TP 2.6 / 3.3 / 4.4 @everyone", {}),
                  "OPEN MU 1020C 9/11");
show("mugzone #2", read("1. SPCX 9/11 155 calls 1.95 SL 1.45 tp 2.45 / 2.85 / 3.5", {}),
                  "OPEN SPCX 155C 9/11");
show("floridaman", read("@Florida man alerts Lotto Entered $GLD 416C 0DTE @ $0.53/ea", {}),
                  "OPEN GLD 416C 0DTE");
show("floridaman #2", read("1. $ABAT 4C 8/21 @ $0.05/ea", BARE),    "OPEN ABAT 4C 8/21");

console.log(bad ? "\n" + bad + " FAILED" :
  "\nall pass — any word order in named rooms, two strikes become two orders, " +
  "scoping holds");
process.exit(bad ? 1 : 0);
