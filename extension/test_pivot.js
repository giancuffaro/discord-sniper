/* test_pivot.js — THE PIVOT ROOMS (9/10, Chika Alerts in Low Key Stonks).
 *
 * She trades ONE instrument — the NASDAQ — and never names it, never writes
 * the thousands, and often writes no verb the ordinary reader knows:
 *     "short 195 pivot"   =  NQ at 29,195, short
 * G walked me through it: "she only trades the NASDAQ... that means
 * automatically where the NASDAQ is, for example 29,000, so it would be
 * 29,195." The bot then waits for the next 25 against the trade — 195 -> 200,
 * 230 -> 250, 203 -> 225 — which is exactly what webull_futures._round_entry
 * already does (ceil to 25 short, floor long), so no new maths was needed.
 *
 * THE EXPANSION IS NOT DONE IN THE PARSER. The browser has no quote, and a
 * reader that guessed the thousands would be inventing a price. The parser
 * hands back the digits she wrote; the bridge, which can price NQ, turns them
 * into a level.
 *
 * WHICH NUMBER IS THE ENTRY is the whole difficulty. Her lines carry up to
 * four: the pivot, her stop, her invalidation, and a trim size. Every case
 * below is verbatim from her room.
 *
 * READ-ONLY. G's call on this room, and the reason is in the numbers: her
 * last 170 messages are 64 entries and 94 exits with 5 flips. Her edge is in
 * the trims, and ENTRIES ONLY throws all of them away. So she is READ, written
 * down, and not traded until there is a record worth judging.
 */
const path = require("path");
const { parseSignal } = require(path.join(__dirname, "parser.js"));
const ROOM = { pivot_root: "NQ", read_only: true };
const ARMED = { pivot_root: "NQ" };
let bad = 0;
function show(label, got, want) {
  const ok = got === want;
  if (!ok) bad++;
  console.log("  " + (ok ? "PASS  " : "FAIL  ") + label.padEnd(30) + got +
              (ok ? "" : "   (wanted " + want + ")"));
}
function read(m, cfg) {
  const s = parseSignal(m, cfg || ROOM);
  if (!s || !s.action) return "silent";
  return [s.action, s.direction || "-", s.pivot == null ? "-" : s.pivot,
          s.their_stop == null ? "-" : "sl" + s.their_stop,
          s.fire ? "FIRE" : "held"].join(" ");
}

console.log("HER ENTRIES — side, level, and her stop:");
show("plain",           read("short 195 pivot"),            "OPEN SHORT 195 - held");
show("no 'pivot' word",  read("got a short 230"),            "OPEN SHORT 230 - held");
show("re-entry",        read("reshorting 163 pivot, tight"), "OPEN SHORT 163 - held");
show("her typo 'olong'", read("trying a olong 150 pivot"),   "OPEN LONG 150 - held");
show("number first",    read("565 short tight"),             "OPEN SHORT 565 - held");
show("trailing s",      read("starter short 340s, stop nhod"), "OPEN SHORT 340 - held");
show("four digits",     read("relonging 4665 pivot"),        "OPEN LONG 4665 - held");
show("level then side", read("450 pivot short, stop 470"),   "OPEN SHORT 450 sl470 held");

console.log("\nTHE OTHER NUMBERS ARE NOT THE ENTRY:");
// Her invalidation. "null if 160" is where the idea dies, not where she buys.
show("null-if ignored",  read("am short nascock, 153 pivot null if 160"),
                         "OPEN SHORT 153 - held");
// Her stop, which is captured separately — and per the futures bracket HERS
// wins over our default 25 points.
show("stop is a stop",   read("readding short 168 , stop still 175"),
                         "OPEN SHORT 168 sl175 held");
show("stop + fill note",  read("light long, 488 pivot, stop 480 494 fill"),
                         "OPEN LONG 488 sl480 held");
// "30pt stop" is a distance, not a level.
show("points not level",  read("starter long 280s 30pt stop"),
                         "OPEN LONG 280 - held");
// Two numbers, one tagged. The tag wins.
show("tagged wins",      read("addin long 450, 443 pivot bit dicey"),
                         "OPEN LONG 443 - held");
// No level at all — she is adding to something already on. Nothing to enter at.
show("no level given",   read("added long"),                  "silent");
show("no level, has stop", read("added short, hard stop 165"), "silent");

console.log("\nHER EXITS — recorded, NEVER acted on (ENTRIES ONLY):");
show("trim",            read("+25 trim"),                     "TRIM - - - held");
show("safety trim",     read("safety trim +15"),              "TRIM - - - held");
show("flat",            read("flat"),                         "CLOSE - - - held");
show("out",             read("im out"),                       "CLOSE - - - held");
show("stop move",       read("moving risk t 158"),            "TRIM - - - held");
show("runner stop",     read("runner SL shift 271"),          "TRIM - - - held");
show("trailing",        read("trailing stops moved to 335"),  "TRIM - - - held");

console.log("\nREAD-ONLY IS THE HOLD — armed, the same line would fire:");
show("armed fires",     read("short 195 pivot", ARMED),       "OPEN SHORT 195 - FIRE");
show("armed exit still held", read("+25 trim", ARMED),        "TRIM - - - held");

console.log("\nSCOPED — outside a pivot room none of this is an order:");
show("no pivot rule",   read("short 195 pivot", {}),          "silent");
show("no pivot rule 2", read("565 short tight", {}),          "silent");
show("no pivot rule 3", read("reshorting 163 pivot, tight", {}), "silent");

console.log(bad ? "\n" + bad + " FAILED" :
  "\nall pass — her side and level read, her stop kept, her exits ignored, " +
  "and nothing fires outside a pivot room");
process.exit(bad ? 1 : 0);
