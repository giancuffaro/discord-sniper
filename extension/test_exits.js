/* test_exits.js — "out" is also half an idiom (9/7).
 *
 * stormzyy's RECAP of a finished trade fired a real CLOSE MNQ off the bare
 * "out" inside "let it play out". Hunting it turned up a second live one in
 * the corpus: "I'm officially checked out for..." — a goodbye message — was
 * firing CLOSE with the symbol "NOTES". A phantom exit is worse than a missed
 * one: it flattens a live position on somebody's victory lap or their sign-off.
 * These lock both directions. "sold out" stays an exit on purpose. */
const path = require("path");
const { parseSignal } = require(path.join(__dirname, "parser.js"));
const NOT_EXITS = [
  ["stormzyy recap",  "Caught a clean MNQ long off the BOS + FVG setup and let it play out exactly how we wanted. Both targets hit for 45+ points on the move."],
  ["play out",        "let it play out exactly how we wanted MNQ"],
  ["works out",       "waiting to see how this works out on SPY"],
  ["checked out",     "Hey everyone I'm officially checked out for the rest of the week"],
  ["panned out",      "that MNQ setup never panned out"],
  ["figure out",      "trying to figure out what SPY does here"],
  ["ride it out",     "just going to ride out the chop on QQQ"],
  ["watch out",       "watch out for the MNQ reversal here"],
  ["out the gates",   "AAPL OUT THE GATES"],
];
const REAL_EXITS = [
  ["out of",          "out of NBIS"],
  ["bare out",        "Im out"],
  ["all out",         "all out"],
  ["fully out",       "fully out of MNQ here"],
  ["stopped out",     "stopped out of MNQ"],
  ["sold out",        "sold out of the SPY 640c"],
];
/* ---- CROSS-ROOM AUDIT, 9/7 ----------------------------------------------
 * Running every room's captured messages through the parser and looking for
 * lines that carry a real contract but produce NOTHING turned up two faults
 * that were older than the audit and cost real money:
 *
 * 1. AN EXPLICIT STC WAS BEING SILENCED BY CHATTER. The chatter veto had a
 *    carve-out for BUYS only, so Option Alerts' exits died on whatever the
 *    caller said next — "don't", "probably", "gonna", "watching". The bare
 *    line closed fine; one casual sentence and the exit vanished. A missed
 *    exit leaves the position open on our ratchet alone.
 * 2. THE WORD "partial" WAS NOT A TRIM ANYWHERE. \bpart\b does not match
 *    "partial", so "STC TSLA 350c @ .36 partial" read as a FULL EXIT — the
 *    caller sells a slice, the bot dumps everything. NINETEEN corpus lines
 *    were doing this.
 * ------------------------------------------------------------------------ */
const STC = [
  ["chatter: don't",   "STC SPY 8/31 770c @ 3.13 partial. Taking some in case we don't hold here", "TRIM"],
  ["chatter: probably","STC SPY 8/31 770c @ 2.50 stop hit on the rest, can probably get them cheaper", "CLOSE"],
  ["chatter: gonna",   "STC SPY 9/01 772c @ 2.15 alright I am not gonna hold through this today", "CLOSE"],
  ["chatter: watching","STC QQQ 9/08 720c @ 2.02 alright cutting in the green, will be watching", "CLOSE"],
  ["chatter: dont",    "STC QQQ 9/08 722c @ 1.28 I dont feel like swinging this.", "CLOSE"],
  ["partial, bare",    "STC SPY 8/31 770c @ 3.13 partial",                        "TRIM"],
  ["partial, TTT",     "STC TSLA 8/19 350c @ .36 partial",                        "TRIM"],
  ["partial, Elite",   "STC META 0dte 600c .94 partial make the free",            "TRIM"],
  ["taking some",      "STC GOOGL 9/11 345c @ 4.65 partial - pay yourself",       "TRIM"],
  ["all out wins",     "STC SPY 8/31 770c @ 3.13 all out",                        "CLOSE"],
  ["bare STC",         "STC SPY 8/31 770c @ 3.13",                                "CLOSE"],
];
let bad = 0;
console.log("EXPLICIT STC — an order, whatever the caller says next:");
for (const [n, t, want] of STC) {
  const s = parseSignal(t, {}) || {};
  const ok = s.action === want;
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(18)} ${(s.action||"NONE").padEnd(6)} want=${want}`);
}
console.log();
console.log("MUST NOT read as an exit:");
for (const [n, t] of NOT_EXITS) {
  const s = parseSignal(t, {}) || {};
  const ok = s.action !== "CLOSE" && s.action !== "TRIM";
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(16)} ${s.action || "-"}${s.fire ? "  FIRED " + s.symbol : ""}`);
}
console.log("\nMUST still read as an exit:");
for (const [n, t] of REAL_EXITS) {
  const s = parseSignal(t, {}) || {};
  const ok = s.action === "CLOSE" || s.action === "TRIM";
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(16)} ${s.action || "-"}`);
}
console.log(bad ? `\n${bad} FAILED` : "\nall pass — idioms are not exits, real exits still fire");
process.exit(bad ? 1 : 0);
