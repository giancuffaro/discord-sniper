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
let bad = 0;
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
