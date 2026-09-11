/* Historical Summit fills arrive after a separate LOADING message. The parser
 * may recognize the confirmation, but guards.resolveLoaded is the only code
 * allowed to attach and fire the stored contract. */
const P = require("./parser.js");

let failed = 0;
function confirm(label, text, price, named) {
  const s = P.parseSignal(text, {});
  const ok = s.action === "OPEN" && s.needs_loaded && !s.fire &&
    s.limit === price && (!named || s.named_symbol === named);
  console.log("  " + (ok ? "PASS" : "FAIL") + "  " + label +
    `  action=${s.action || "-"} loaded=${s.needs_loaded} price=${s.limit}`);
  if (!ok) failed++;
}
function silent(label, text) {
  const s = P.parseSignal(text, {});
  const ok = !s.action;
  console.log("  " + (ok ? "PASS" : "FAIL") + "  " + label);
  if (!ok) failed++;
}

console.log("CONFIRMED FILLS — recognized, held for the matching loaded contract:");
confirm("fill first", "Fill is 1.79 not using a lot of size here", 1.79);
confirm("OSI then price", "I took entry $NFLX NFLX260821C80 1.28", 1.28, "NFLX");
confirm("price then entry", "3.65 took entry", 3.65);
confirm("price fill entry", "1.56 fill took entry", 1.56);
{
  const s = P.parseSignal("$HOOD i took enry .HOOD260904C120 1.83 fill price", {});
  const ok = s.action === "OPEN" && s.symbol === "HOOD" && s.strike === 120 &&
    s.side === "CALLS" && s.limit === 1.83;
  console.log("  " + (ok ? "PASS" : "FAIL") +
    `  typo plus full OSI  ${s.symbol || "?"} ${s.strike || "?"} ${s.side || "?"} @${s.limit}`);
  if (!ok) failed++;
}

console.log("\nPROSPECTIVE/RESULT PROSE — never a fill:");
silent("watch trigger", "Watching TSLA above 353.5 for the 360 C 8/28");
silent("future add", "That 762.70 will be my add point once I fill");
silent("target reached", "here we are at premarket target, gg");

if (failed) process.exit(1);
console.log("\nall pass — historical fill shapes wait for a fresh loaded contract");
