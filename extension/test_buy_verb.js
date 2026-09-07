/* test_buy_verb.js — the imperative "buy" + trailing-$ strike (9/7).
 *
 * RE_ENTRY listed bought/buying but NOT the bare "buy", so cranmer's entire
 * room read as silence. Worse, once "buy" was accepted, "buy AA sep 18 Calls
 * 52$" booked ticker SEP strike 18 — a real order in the wrong name, because
 * trailing-$ strikes were unreadable and month names were valid tickers.
 * All three are fixed; these cases hold the line in both directions. */
const path = require("path");
const { parseSignal } = require(path.join(__dirname, "parser.js"));
const eq = (s, sym, strike, side) =>
  s.fire && s.symbol === sym && String(s.strike) === String(strike) && s.side === side;

const CASES = [
  // [label, text, expectFire, symbol, strike, side]
  ["cranmer UPS, trailing $", "buy UPS 104$ calls Sep 18th for 1.75 (1.62 bid, 1.84 ask) @everyone", true, "UPS", 104, "CALLS"],
  ["cranmer BAC put",         "buy BAC sep 18th 61$ put for .83 and hedge @everyone",                  true, "BAC", 61,  "PUTS"],
  ["cranmer NVDA",            "buy NVDA Calls Sep 18 220 calls for 4.70 @everyone",                    true, "NVDA", 220, "CALLS"],
  ["cranmer U puts",          "buy U Puts sep 18 44$ puts for 2 (bid 1.90) @everyone",                 true, "U",   44,  "PUTS"],
  ["BTO still works",         "BTO PFE 1/15/27 30c @1.08 monthly IHS break",                           true, "PFE", 30,  "CALLS"],
];
const MUST_NOT_FIRE = [
  ["warning",        "LOADING= Get contracts ready, DO NOT BUY IN Specfied contracts SPY 640c 9/18"],
  ["negated",        "don't buy SPY 640c 9/18 here"],
  ["question",       "should you buy AAPL 220c 9/18 ?"],
  ["idiom",          "buy the dip on SPY 640c 9/18"],
  ["hypothetical",   "Or buy next week exp 11 3 6 10 6 5 2"],
  ["vertical",       "Msft Sep 9 497 put buy 490 put sell Total pay 2.20"],
  ["a trim is a trim","sell 2/3 UPS 105 calls sept 18th from 1.75 to 2.60 for 45-50% WIN!!"],
];
let bad = 0;
console.log("MUST FIRE, with the RIGHT contract:");
for (const [n, t, , sym, k, sd] of CASES) {
  const s = parseSignal(t, {}) || {};
  const ok = eq(s, sym, k, sd);
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(24)} ${s.fire ? s.symbol + " " + s.strike + s.side : "dead"}`);
}
console.log("\nMUST NOT FIRE:");
for (const [n, t] of MUST_NOT_FIRE) {
  const s = parseSignal(t, {}) || {};
  const ok = !s.fire;
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(24)} ${s.fire ? "FIRED " + s.symbol + " " + s.strike + s.side : "dead"}`);
}
/* KNOWN SAFE MISSES (unusual grammar, still unread — all are MISSED entries,
 * never wrong orders. Left documented rather than forced, because widening the
 * contract reader for these risks the SEP-style misparse we just killed):
 *   "buy DOCU Calls July 31st - 48$ calls for 1.52"   (dash before the strike)
 *   "buy QCOM $167.50 Sept 18th Calls for $5.05"      (decimal strike)
 *   "buy AI 12.50 .43 calls for Sept 18"              (strike then price, no $)
 *   "buy AA sep 18 Calls 52$"                         (strike after the side)
 *   "MCD Puts oct 16th exp, 245s"                     (madhatter, no verb) */
console.log(bad ? `\n${bad} FAILED` : "\nall pass — buy reads, negations refused, contracts correct");
process.exit(bad ? 1 : 0);
