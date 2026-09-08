/* test_plan_entry.js — verbless calls that carry a RISK PLAN (9/7).
 *
 * A room G brought over writes calls with no entry verb at all: the contract,
 * the fill price, then SL / TP. Every one read as silence. A bare contract on
 * its own IS ambiguous (that's a watchlist row), but nobody writes a stop-loss
 * or a take-profit ladder about a trade they haven't taken — the plan is the
 * verb. Two contract-shape fixes came with it:
 *   - the expiry may sit on EITHER SIDE of the strike ("TSLA 357.5 0 DTE CALLS")
 *   - the expiry may lead the whole thing ("9/2 TSLA 355 PUTS 1.57")
 *
 * MEASURED, NOT GUESSED: broader triggers were tested against the corpus and
 * rejected. "lotto" matched 13 lines, all of them "$150p on watch" watchlist
 * rows. An @everyone/@here ping matched 140, mostly "loading GOOGL 8/21 345C"
 * — the PREPARE state, where firing would buy before the caller does. Both
 * would have bought things nobody bought. Hence the narrow SL/TP signature. */
const path = require("path");
const { parseSignal } = require(path.join(__dirname, "parser.js"));
const FIRE = [
  ["SL + TP, 0 DTE spaced", "TSLA 357.5 0 DTE CALLS 1.30 SL .80 TP 1.60 / 1.95 / 2.6 @everyone", "TSLA", 357.5, "CALLS", "0DTE"],
  ["SL + TP, dated",        "SNOW 9/4 385 C 2.60 SL 1.9 TP 3.20 / 3.8 / 5.1 (runners) @everyone", "SNOW", 385, "CALLS", "9/4"],
  ["TP only, date first",   "9/2 TSLA 355 PUTS 1.57 TP 2.0 /2.45 / 3.0 @here",                    "TSLA", 355, "PUTS",  "9/2"],
  ["0DTE before strike",    "TSLA 0DTE 357.5 CALLS 1.30 SL .80 TP 1.60",                          "TSLA", 357.5, "CALLS", "0DTE"],
];
const NEVER = [
  // watchlist rows — these carry a contract and the word lotto, never a plan
  ["on watch + lotto",  "@Owner Alerts Comment SPY $654p on watch again for a quick scalp, LOTTO as always"],
  ["on watch, sized",   "@Owner Alerts Comment PLTR $180p on watch, this one will be quarter sized not lotto"],
  // the PREPARE state — the caller has not filled yet
  ["loading",           "@Unraveller (Admin) loading GOOGL 8/21 345C @here"],
  ["loading w/ price",  "@Unraveller (Admin) loading GOOGL 8/21 345C @ 2.95 @everyone"],
  // talk ABOUT a finished trade — "TP hit" is not a fresh plan
  ["TP hit (no verb)",  "TSLA 355 PUTS TP 2.0 hit"],
  ["TP hit + up %",     "TSLA 355 PUTS TP 2.0 hit, up 40% on these"],
  // no side word at all: call or put is unknowable and must never be guessed
  ["no side word",      "SPY 0dte 775 .25 TP .45 / .55 / .75 leave runners @everyone"],
  // a reference to an earlier contract, not a new one
  ["same 1dte puts",    "Entry this time is at $3.13 on those same 1dte puts. Use my level as stop."],
];
let bad = 0;
console.log("MUST FIRE (plan = verb):");
for (const [n, t, sym, k, side, exp] of FIRE) {
  const s = parseSignal(t, {}) || {};
  const ok = s.fire && s.symbol === sym && Number(s.strike) === k && s.side === side && s.expiry === exp;
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(22)} ${s.symbol||"-"} ${s.strike??"-"} ${s.side||"-"} exp=${s.expiry||"-"}`);
}
// "must not fire" here means MUST NOT OPEN A POSITION. A line that is a
// genuine exit is allowed to close one — that is the whole point of the
// exit path — so the assertion is specifically about entries.
console.log("\nMUST NOT OPEN A POSITION:");
for (const [n, t] of NEVER) {
  const s = parseSignal(t, {}) || {};
  const ok = s.action !== "OPEN";
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(22)} ${s.action ? s.action + " " + (s.symbol||"") : "dead"}`);
}
console.log(bad ? `\n${bad} FAILED` : "\nall pass — the plan reads; watchlists, loading and recaps never open");
process.exit(bad ? 1 : 0);
