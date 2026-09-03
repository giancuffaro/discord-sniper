/* parse_batch.js — run the PRODUCTION parser (parser.js, the one the extension
 * actually trades with) over many lines at once, from Python or the shell.
 *
 *   node extension/parse_batch.js < lines.txt      (one message per line)
 *   node extension/parse_batch.js --json < arr.json (JSON array of strings)
 *
 * Prints a JSON array, one object per input line: {action, symbol, strike,
 * side, expiry, limit, why, matched, fire, kind, direction}. Used by
 * replay_check.py and scoreboard.py so the audit tools can never disagree with
 * the bot again (9/2: the Python mirror lagged parser.js and called a room
 * silent that the bot was reading fine).
 */
const fs = require("fs");
const path = require("path");
const { parseSignal } = require(path.join(__dirname, "parser.js"));

let cfg = {};
try {
  cfg = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "settings.example.json"), "utf8"));
} catch (e) { cfg = {}; }

const raw = fs.readFileSync(0, "utf8");
const lines = process.argv.includes("--json")
  ? JSON.parse(raw || "[]")
  : raw.split("\n").filter(l => l.length);

const out = lines.map(t => {
  try {
    const s = parseSignal(String(t), cfg) || {};
    return { action: s.action || null, symbol: s.symbol || null, strike: s.strike ?? null,
             side: s.side || null, expiry: s.expiry || null, limit: s.limit ?? null,
             why: s.why || "", matched: s.matched || "", fire: !!s.fire,
             kind: s.kind || "", direction: s.direction || null };
  } catch (e) {
    return { action: null, why: "ERR " + String(e).slice(0, 80) };
  }
});
process.stdout.write(JSON.stringify(out));
