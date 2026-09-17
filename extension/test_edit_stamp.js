/* An EDITED Discord row carries "(edited)Wednesday, September 16, 2026 at
 * 10:10 AM" glued to the call. Until 9/16 that datestamp was read as part of
 * the call: its "10" became the price, its "September 3" became the expiry,
 * and an edited "loading" line fired as an OPEN. The stamp is never the call. */
const P = require("./parser.js");
let failed = 0;
function check(label, text, want) {
  const s = P.parseSignal(text, {});
  const got = { action: s.action || null, limit: s.limit == null ? null : s.limit,
                expiry: s.expiry || null };
  const ok = Object.keys(want).every(k => String(got[k]) === String(want[k]));
  console.log("  " + (ok ? "PASS" : "FAIL") + "  " + label + "  " + JSON.stringify(got));
  if (!ok) failed++;
}
const STAMP = " @everyone (edited)Wednesday, September 16, 2026 at 10:10 AM";
check("the price is the caller's, not the clock's",
  "@Brett (Admin) in AAPL 9/18 335C @ 2.67" + STAMP, { action: "OPEN", limit: 2.67 });
check("an edited LOADING still never buys",
  "@Unraveller (Admin) loading TSLA 9/11 365C @here (edited) Thursday, September 10, 2026 at 9:41 AM",
  { action: "PREPARE" });
check("the expiry is the one he typed, not the day he edited",
  "In aapl 325 puts starter size 9/11 exp. Avg 5.53 @here (edited) Thursday, September 3, 2026 at 9:40 AM",
  { action: "OPEN", limit: 5.53 });
{
  const s = P.parseSignal("In aapl 325 puts starter size 9/11 exp. Avg 5.53 @here (edited) Thursday, September 3, 2026 at 9:40 AM", {});
  const ok = /9\/11|09-11/.test(String(s.expiry));
  console.log("  " + (ok ? "PASS" : "FAIL") + "  expiry reads 9/11  " + s.expiry);
  if (!ok) failed++;
}
console.log(failed ? "\nFAILED (" + failed + ")" : "\ntest_edit_stamp: all good.");
process.exit(failed ? 1 : 0);
