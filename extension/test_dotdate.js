/* test_dotdate.js — THE EXPIRY WRITTEN WITH A DOT (9/10, Maguro Alerts in
 * Low Key Stonks).
 *
 * His whole grammar is  $TICKER STRIKEc MM.DD PRICE  — in either order:
 *     "$uber 80c 09.18 1.46"      "$mrvl 10.16 250c 11.5"
 *     "$amzn 270c 11.20 10.2"     "$intc 100c 10.16 4"
 * Eighteen messages, eight with a contract, and the shape never varies.
 *
 * WHY IT IS A PER-ROOM RULE AND NOT A GLOBAL ONE
 * In every other room "MU 8/28 965c 1.26" carries a $1.26 PRICE — and 1.26
 * reads just as well as January 26th. Nothing in the text can tell those
 * apart, so the ROOM says which language it speaks: rooms.txt rule `dotdate`.
 * The second half of this file is the proof that the rule stays in its room.
 *
 * WHAT IT COST TO GET RIGHT: written with /g the rule ate the PRICE as a
 * second date — "$tlt 83c 10.16 1.01 cheap calls" turned 1.01 into 1/01 and
 * the entry would have gone out at the market with no price at all. He writes
 * one date per alert, next to the contract, so only the first match converts.
 */
const path = require("path");
const P = require(path.join(__dirname, "parser.js"));
const MAG = { entry_no_verb: true, dot_date: true };
const PLAIN = { entry_no_verb: true };
let bad = 0;
function show(got, want, msg) {
  const ok = got === want;
  if (!ok) bad++;
  console.log("  " + (ok ? "PASS  " : "FAIL  ") + got.padEnd(26) +
              (ok ? msg.slice(0, 34) : "(wanted " + want + ")  " + msg));
}
function read(m, cfg) {
  const s = P.parseSignal(m, cfg);
  if (!s || !s.action) return "silent";
  return [s.action, s.symbol, s.strike, s.expiry || "NO-DATE",
          s.limit == null ? "mkt" : s.limit].join(" ");
}

console.log("MAGURO — every alert in his room, verbatim:");
[["$uber 80c 09.18 1.46 possible retest of range", "OPEN UBER 80 9/18 1.46"],
 ["$tlt 83c 10.16 1.01 cheap calls",               "OPEN TLT 83 10/16 1.01"],
 ["$tmus 195c 10.16 3.65",                         "OPEN TMUS 195 10/16 3.65"],
 ["$tlt 84c 09.18 0.42 roll the dice boys",        "OPEN TLT 84 9/18 0.42"],
 ["$intc 100c 10.16 4",                            "OPEN INTC 100 10/16 4"],
 ["$slv 63c 10.16 2.35",                           "OPEN SLV 63 10/16 2.35"],
 ["$mrvl 10.16 250c 11.5 lookin for this gapper fill", "OPEN MRVL 250 10/16 11.5"],
 ["$amzn 270c 11.20 10.2",                         "OPEN AMZN 270 11/20 10.2"]
].forEach(([m, w]) => show(read(m, MAG), w, m));

console.log("\nHis running P&L must never open anything:");
["$uber 70%", "$intc 140%", "$slv 166% we long and hold",
 "$tlt -50% will reenter close to fomc",
 "$intc gmorning to all the nonbelievers"].forEach(m => {
  const s = P.parseSignal(m, MAG);
  const ok = s.action !== "OPEN";
  if (!ok) bad++;
  console.log("  " + (ok ? "PASS  " : "FAIL  ") + String(s.action || "silent").padEnd(8) + m.slice(0, 40));
});

console.log("\nTHE RULE STAYS IN ITS ROOM — same lines, no `dotdate`:");
// 10.16 goes back to being an ordinary number, which is what it is everywhere
// else. The entry still reads; it just has no date of its own and the bridge
// fills one in, which is the pre-existing behaviour for a dateless call.
show(read("MU 8/28 965c 1.26", PLAIN),  "OPEN MU 965 8/28 1.26",  "price stays a price");
show(read("SPY 760c at 3.40", PLAIN),   "OPEN SPY 760 NO-DATE 3.4", "untouched");
show(read("MU 1020 9/11 CALLS @ 2.2 SL 1.45 TP 2.6 / 3.3", {}),
     "OPEN MU 1020 9/11 2.2", "mugzone untouched");
// And inside a dotdate room an ordinary slash date still wins.
show(read("$tlt 83c 10/16 1.01", MAG),  "OPEN TLT 83 10/16 1.01", "slash date still reads");

console.log(bad ? "\n" + bad + " FAILED" :
  "\nall pass — dot dates read in Maguro's room and nowhere else");
process.exit(bad ? 1 : 0);
