/* test_owls_jonkian.js — OWLS #jon-and-kian, read live 9/10 off G's link.
 *
 * Two callers, one alert bot ("OWLS Capital Clanker"), and every post is
 * labelled OPEN: / CLOSE: / Update:. The room reads with NO rules — but
 * reading it exposed THREE real defects, and this file is what keeps them
 * dead:
 *
 *  1. THE DATE GLUED TO "exp".  "FRVO 25C 3/19exp 4.05 premium"
 *     Every date pattern ends on a word boundary and "9exp" is not one, so
 *     the expiry came back NULL and the order fell through to the bridge's
 *     default date. Silent, and it buys a REAL contract with the WRONG
 *     expiry — "PURR 15C 1/15exp" would have been bought as this Friday,
 *     four months early. Worst class of bug this parser can have.
 *
 *  2. NO "@" IN FRONT OF THE PRICE.  "70C 10/16 Exp. at 3.60" / "4.05 premium"
 *     The OPEN-label branch only looked for "@", so it bid the MARKET on
 *     every entry in this room while the price sat in plain sight.
 *
 *  3. THE LABEL READ AS THE TICKER.  "CLOSE: sold 6/10 RKLB at 4.15"
 *     resolved to ticker CLOSE. Harmless to the account (exits are ignored,
 *     and the optionable list refuses the word) but it poisons attribution.
 */
const path = require("path");
const { parseSignal } = require(path.join(__dirname, "parser.js"));
let bad = 0;
function show(label, got, want) {
  const ok = got === want;
  if (!ok) bad++;
  console.log("  " + (ok ? "PASS  " : "FAIL  ") + label.padEnd(20) + got +
              (ok ? "" : "   (wanted " + want + ")"));
}
function read(msg) {
  const s = parseSignal(msg, {});                 // NO room rules on purpose
  if (!s || !s.action) return "silent";
  return s.action + " " + (s.symbol || "?") + " " +
         (s.strike == null ? "" : s.strike + (s.side ? s.side[0] : "") + " ") +
         (s.expiry || "no-date") + " @" + (s.limit == null ? "market" : s.limit);
}

console.log("ENTRIES — contract, expiry AND price:");
show("jon, at-price",  read("OPEN: RKLB 70C 10/16 Exp. at 3.60"),
                       "OPEN RKLB 70C 10/16 @3.6");
show("kian, exp glued", read("OPEN: bit of a chase here but FRVO 25C 3/19exp 4.05 premium"),
                       "OPEN FRVO 25C 3/19 @4.05");
show("kian, LEAP",     read("OPEN: PURR 15C 1/15exp 2.15 premium, liking the 8D bounce."),
                       "OPEN PURR 15C 1/15 @2.15");
// He posted no price on this one and said "filled at .10" a minute later.
// No price is honest here — it must not invent one.
show("no price at all", read("OPEN: NU 16C 9/11exp size for 0 lotto, im bored"),
                       "OPEN NU 16C 9/11 @market");
// Single-letter ticker, four-digit year.
show("jon, plain line", read("T 29C 01/15/2027 Exp. At 0.50 @everyone"),
                       "OPEN T 29C 01/15 @0.5");

console.log("\nEXITS — ignored by doctrine, but the TICKER must still be right:");
show("label not ticker", read("CLOSE: sold 6/10 RKLB at 4.15"), "CLOSE RKLB no-date @market");
show("label not ticker 2", read("CLOSE: Sold another NTR at 4.95"), "CLOSE NTR no-date @market");

console.log("\nNEVER AN ORDER:");
show("running P&L",   read("Update: RKLK up to 3.97 from Jons Swings!"), "silent");
show("fill echo",     read("Update: filled at .10"),                     "silent");
show("victory lap",   read("22% on commons, feels good coming back to owls with a banger"), "silent");
// They trade shares too. This machine trades options and futures, not stock.
show("commons",       read("OPEN: 1000% lotto CHGG commonst at .83"),    "silent");

console.log("\nTHE OTHER ROOMS' OPEN-LABEL FORMAT IS UNTOUCHED:");
show("JPM style",     read("Open  SPY 08/03 753C @.92"), "OPEN SPY 753C 08/03 @0.92");

console.log(bad ? "\n" + bad + " FAILED" :
  "\nall pass — glued dates read, prices without @ read, labels are not tickers");
process.exit(bad ? 1 : 0);
