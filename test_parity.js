/* test_parity.js — prove the browser reads your room exactly like Python does.
 *
 * Two copies of the same logic in two languages is how a bot ends up buying in
 * the extension and not in the listener, on a Tuesday, for no visible reason.
 * This runs every line of samples.txt through the JS parser and compares it to
 * a JSON dump from the Python one.
 *
 *   python3 dump_parse.py > /tmp/py.json && node test_parity.js /tmp/py.json
 */
const fs = require("fs");
const path = require("path");
const { parseSignal } = require("./extension/parser.js");

const CFG = JSON.parse(fs.readFileSync(
  path.join(__dirname, "settings.example.json"), "utf8"));
const py = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));

// needs_position, needs_loaded, needs_add and caller are in here because that's
// how a symbol-less trim, a two-message entry and an average-in get resolved.
// If Python flags "work out which position they meant" and the extension
// doesn't, the browser silently drops an exit that the listener takes — which
// is the exact class of bug this file exists to catch. needs_add is the same
// hazard pointed the other way: miss it in one language and that side buys a
// second contract the other side never touched.
const FIELDS = ["fire", "action", "symbol", "side", "strike", "expiry",
                "limit", "pct", "qty", "reenter", "reenter_limit",
                "needs_position", "needs_loaded", "needs_add", "caller",
                // Futures and his-levels: one language reading "Short NQ @
                // 28660" as a trade while the other calls it chatter is the
                // exact disagreement this file exists to catch.
                "kind", "direction", "their_stop", "their_target", "usd"];
let bad = 0;

for (const row of py) {
  const js = parseSignal(row.raw, CFG);
  for (const f of FIELDS) {
    const a = row[f] === undefined ? null : row[f];
    const b = js[f] === undefined ? null : js[f];
    if (JSON.stringify(a) !== JSON.stringify(b)) {
      bad++;
      console.log("MISMATCH on " + f + ": python=" + JSON.stringify(a) +
                  " js=" + JSON.stringify(b) + "\n   " + row.raw.slice(0, 80));
    }
  }
}

if (bad) { console.log("\n" + bad + " field(s) disagree."); process.exit(1); }
console.log("Python and the extension read all " + py.length +
            " lines identically.");
