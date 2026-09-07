/* test_spreads.js — the named-leg vertical guard (9/7).
 * TLM writes spreads as two legs and never says "spread". That fired a NAKED
 * long put with real money. These cases lock the fix in both directions:
 * multi-leg must be refused, ordinary single-leg calls must still fire. */
const path = require("path");
const { parseSignal } = require(path.join(__dirname, "parser.js"));
const cfg = {};
const MUST_REFUSE = [
  ["TLM real, 9/4",      "Open @everyone Msft Sep 9 497 put buy 490 put sell Total pay 2.20 Target 2.60 SL 1.90"],
  ["TLM close, 9/4",     "Close @everyone Msft Sep 9 497 put buy 490 put sell Total close 2.15 to 2.20"],
  ["legs, calls",        "AAPL Sep 18 200 call buy 210 call sell for 2.10 debit"],
  ["legs, reversed",     "SPY 500 put sell 505 put buy total 1.40"],
  ["buy/sell phrasing",  "buy the 497 put and sell the 490 put for 2.20 total"],
  ["kumo real",          "CAKE 09/18/26 $120/$125 Call Debit Spread @$0.50"],
];
const MUST_STILL_FIRE = [
  ["cranmer real",       "buy NVDA Calls Sep 18 220 calls for 4.70 @everyone"],
  ["entry + sell target","buy NVDA 220 calls Sep 18 at 4.70, sell at 6.00"],
  ["evapanda real",      "MU 1100C 9/18 @ 5.50 6.55 (19.09%)"],
  ["plain BTO",          "BTO AAPL 120c 11/06 @1.5"],
  ["same strike restate","buy SPY 640 calls 9/8 for 1.20, will sell 640 calls into strength"],
];
let bad = 0;
console.log("MUST REFUSE (multi-leg):");
for (const [name, t] of MUST_REFUSE) {
  const s = parseSignal(t, cfg) || {};
  const ok = !s.fire;
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${name.padEnd(20)} fire=${!!s.fire}${s.fire ? "  -> " + s.action + " " + s.symbol + " " + s.strike + s.side : ""}`);
}
console.log("\nMUST STILL FIRE (single-leg):");
for (const [name, t] of MUST_STILL_FIRE) {
  const s = parseSignal(t, cfg) || {};
  const ok = !!s.fire;
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${name.padEnd(20)} fire=${!!s.fire}  ${s.why ? s.why.slice(0, 60) : ""}`);
}
console.log(bad ? `\n${bad} FAILED` : "\nall pass — spread refused, ordinary calls untouched");
process.exit(bad ? 1 : 0);
