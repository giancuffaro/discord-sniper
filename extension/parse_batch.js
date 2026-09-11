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
const PARSER = require(path.join(__dirname, "parser.js"));
const { parseSignal } = PARSER;

/* THE ALLOWLIST, SAME AS PRODUCTION (9/11). background.js hands
 * optionable.txt to the parser at startup, so the bot never mints a ticker out
 * of an English word. This file did not, so every Python tool that reads
 * through it — replay_check, audit_history, scoreboard, jsparse — was running a
 * parser one guard weaker than the one that trades, and reported entries the
 * bot would have refused ("OPEN WITH 773C"). The whole point of this file is
 * that an audit can never disagree with the bot. Fails open exactly as
 * production does: setOptionable ignores a list under 1,000 names. */
try {
  const set = new Set();
  for (const line of fs.readFileSync(path.join(__dirname, "optionable.txt"), "utf8").split("\n")) {
    const s = line.trim().toUpperCase();
    if (s && s[0] !== "#") set.add(s);
  }
  if (typeof PARSER.setOptionable === "function") PARSER.setOptionable(set);
} catch (e) { /* missing list = no gate, never a silent halt */ }

let cfg = {};
try {
  cfg = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "settings.example.json"), "utf8"));
} catch (e) { cfg = {}; }

const raw = fs.readFileSync(0, "utf8");
const lines = process.argv.includes("--json")
  ? JSON.parse(raw || "[]")
  : raw.split("\n").filter(l => l.length);

const out = lines.map(item => {
  try {
    // Audit callers may supply the effective per-room flags. Plain strings
    // remain the public/default format used by scoreboard and older tools.
    const text = item && typeof item === "object" ? item.text : item;
    const roomCfg = item && typeof item === "object" && item.cfg
      ? Object.assign({}, cfg, item.cfg) : cfg;
    const s = parseSignal(String(text || ""), roomCfg) || {};
    return { action: s.action || null, symbol: s.symbol || null, strike: s.strike ?? null,
             side: s.side || null, expiry: s.expiry || null, limit: s.limit ?? null,
             why: s.why || "", matched: s.matched || "", fire: !!s.fire,
             kind: s.kind || "", direction: s.direction || null };
  } catch (e) {
    return { action: null, why: "ERR " + String(e).slice(0, 80) };
  }
});
process.stdout.write(JSON.stringify(out));
