/* parser_gate.js — RUN THIS BEFORE SHIPPING ANY PARSER CHANGE.
 *
 * G, 9/10: "we definitely do need a gate. That should be like the first thing
 * to measure."
 *
 * THE THREE WORDS, so they never get mixed up again:
 *   PARSER  the machine that reads a room message. Code. extension/parser.js.
 *   CORPUS  every real message we have ever captured. Data. "DS Logs".
 *           11,187 of them, from 20+ rooms, going back to August.
 *   GATE    this file. It runs the PARSER over the CORPUS and compares the
 *           result to the parser as it was before your change.
 *
 * WHY IT EXISTS. On 9/10 a change to read a ticker written AFTER the contract
 * looked perfect: every test passed, every one of the new room's formats read.
 * The gate said it also produced FOURTEEN new entries across the corpus and
 * THIRTEEN of them were English words turned into tickers:
 *     "revising $338,00 BREAK 4.65"     -> NEX 350 CALLS
 *     "buy DOCU Calls July 31st - 48"   -> FOR 48 CALLS
 *     "$776C cally spy TUESDAY"         -> CALLY 776 CALLS
 * NEX and FOR are REAL LISTED SYMBOLS. The allowlist downstream would have
 * waved both through and bought a contract nobody named. Unit tests cannot
 * find that, because you only write a test for a case you already thought of.
 * The corpus is full of cases nobody thought of.
 *
 * WHAT IT MEASURES
 *   GAINED     entries the new parser fires that the old one did not
 *   LOST       entries the old one fired that the new one does not
 *   JUNK       any fired symbol NOT on optionable.txt — the loudest signal
 *              here, because an invented ticker is the failure that costs
 *              real money silently
 *   EXPIRY     same trade, different date. A silent wrong-date fill is the
 *              worst class of bug this parser can have.
 *
 * IT DOES NOT PASS OR FAIL ON A COUNT. More entries is not better and fewer
 * is not worse — you have to LOOK at what changed. It exits non-zero only on
 * JUNK, which is never acceptable.
 *
 * USAGE
 *   node parser_gate.js                    compare against the last commit
 *   node parser_gate.js --base a79d568     compare against any commit
 *   node parser_gate.js --show 40          print more of the changed lines
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const HERE = __dirname;
const LOGS = path.join(HERE, "DS Logs");
const args = process.argv.slice(2);
const argOf = (k, d) => {
  const i = args.indexOf(k);
  return i >= 0 && args[i + 1] ? args[i + 1] : d;
};
const SHOW = parseInt(argOf("--show", "12"), 10);

// ---- the two parsers -------------------------------------------------------
const NEW = require(path.join(HERE, "extension", "parser.js"));
let BASE = argOf("--base", "HEAD");
const oldPath = path.join(os.tmpdir(),
  `parser_gate_base_${process.pid}_${Date.now()}.js`);
try {
  const source = execFileSync(
    "git", ["-C", HERE, "show", `${BASE}:extension/parser.js`],
    { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  fs.writeFileSync(oldPath, source, "utf8");
} catch (e) {
  console.error("could not read extension/parser.js at " + BASE + " — is it a"
    + " valid commit? (" + String(e.message).slice(0, 90) + ")");
  process.exit(2);
}
const OLD = require(oldPath);
process.on("exit", () => { try { fs.unlinkSync(oldPath); } catch (e) {} });

// ---- the allowlist, so JUNK can be named --------------------------------
const OPTIONABLE = new Set();
for (const line of fs.readFileSync(path.join(HERE, "extension", "optionable.txt"), "utf8").split("\n")) {
  const s = line.trim().toUpperCase();
  if (s && s[0] !== "#") OPTIONABLE.add(s);
}
// Compare code against code under the same production configuration. Giving
// this list to only one side made byte-identical parsers report differences.
if (typeof NEW.setOptionable === "function") NEW.setOptionable(OPTIONABLE);
if (typeof OLD.setOptionable === "function") OLD.setOptionable(OPTIONABLE);

// ---- the room rules, so each message is parsed the way its room is -------
const ROOMS = {};
for (const line of fs.readFileSync(path.join(HERE, "extension", "rooms.txt"), "utf8").split("\n")) {
  if (!line || line[0] === "#") continue;
  const p = line.split("|");
  if (p.length < 5) continue;
  const cfg = {};
  const rules = (p[5] || "");
  if (/\bbare\b/.test(rules)) cfg.entry_no_verb = true;
  if (/\bdotdate\b/.test(rules)) cfg.dot_date = true;
  if (/\breadonly\b/.test(rules)) cfg.read_only = true;
  const ms = /sym=([A-Z]+)/.exec(rules);
  if (ms) cfg.default_symbol = ms[1];
  const mp = /pivot=([A-Z]+)/.exec(rules);
  if (mp) cfg.pivot_root = mp[1];
  ROOMS[p[0]] = cfg;
}

// ---- the corpus ------------------------------------------------------------
const RE = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\[(.+?)#(\d+)\]\s+([\s\S]*)$/;
const seen = new Set();
const rows = [];
if (!fs.existsSync(LOGS)) {
  console.error('no "DS Logs" folder — nothing to gate against.');
  process.exit(2);
}
for (const f of fs.readdirSync(LOGS).filter(f => /^signal-room-chat.*\.txt$/.test(f))) {
  for (const line of fs.readFileSync(path.join(LOGS, f), "utf8").split("\n")) {
    const m = RE.exec(line);
    if (!m) continue;
    const key = m[1] + "|" + m[3] + "|" + m[4].slice(0, 120);
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({ ch: m[3], room: m[2].trim(), txt: m[4] });
  }
}

// ---- run both --------------------------------------------------------------
const gained = [], lost = [], junk = [], expiry = [];
let oldFire = 0, newFire = 0;
for (const r of rows) {
  const cfg = ROOMS[r.ch] || {};
  let a = null, b = null;
  try { a = OLD.parseSignal(r.txt, cfg); } catch (e) {}
  try { b = NEW.parseSignal(r.txt, cfg); } catch (e) {}
  const of_ = !!(a && a.fire && a.action === "OPEN");
  const nf = !!(b && b.fire && b.action === "OPEN");
  if (of_) oldFire++;
  if (nf) newFire++;
  const one = s => String(s || "").replace(/\s+/g, " ").slice(0, 96);
  if (nf && b.symbol && !OPTIONABLE.has(String(b.symbol).toUpperCase()))
    junk.push([b.symbol, b.strike, one(r.txt), r.room]);
  if (!of_ && nf) gained.push([b.symbol, b.strike, b.side, b.expiry, one(r.txt), r.room]);
  else if (of_ && !nf) lost.push([a.symbol, a.strike, one(r.txt), r.room]);
  else if (of_ && nf && String(a.expiry) !== String(b.expiry))
    expiry.push([b.symbol, b.strike, a.expiry + " -> " + b.expiry, one(r.txt)]);
}

// ---- report ----------------------------------------------------------------
const shortRoom = s => String(s).replace(/^.*?:\s*/, "").slice(0, 26);
console.log("=".repeat(76));
console.log("PARSER GATE — extension/parser.js  vs  " + BASE);
console.log("%d messages, %d rooms, %d on the allowlist",
            rows.length, Object.keys(ROOMS).length, OPTIONABLE.size);
console.log("=".repeat(76));
console.log("  entries fired BEFORE : %d", oldFire);
console.log("  entries fired NOW    : %d   (%s%d)", newFire,
            newFire - oldFire >= 0 ? "+" : "", newFire - oldFire);
console.log("  gained: %d   lost: %d   expiry changed: %d",
            gained.length, lost.length, expiry.length);
console.log("  JUNK TICKERS: %d %s", junk.length,
            junk.length ? "  <-- THIS IS THE ONE THAT MATTERS" : "");

const dump = (title, list, fmt) => {
  if (!list.length) return;
  console.log("\n--- " + title + " (" + list.length + ") ---");
  for (const r of list.slice(0, SHOW)) console.log("  " + fmt(r));
  if (list.length > SHOW) console.log("  ... " + (list.length - SHOW) + " more (--show N)");
};
dump("JUNK — fired a symbol that is NOT a tradeable ticker", junk,
     r => (r[0] + "").padEnd(7) + String(r[1]).padEnd(7) + "| " + r[2]);
dump("GAINED — new entries", gained,
     r => (r[0] + "").padEnd(7) + String(r[1]).padEnd(6) + (r[2] || "").slice(0, 4).padEnd(5)
        + (r[3] || "no-date").padEnd(8) + shortRoom(r[5]).padEnd(27) + "| " + r[4]);
dump("LOST — entries that no longer fire", lost,
     r => (r[0] + "").padEnd(7) + String(r[1]).padEnd(6) + shortRoom(r[3]).padEnd(27) + "| " + r[2]);
dump("EXPIRY CHANGED — same trade, different date", expiry,
     r => (r[0] + "").padEnd(7) + String(r[1]).padEnd(6) + r[2].padEnd(22) + "| " + r[3]);

console.log("\n" + "=".repeat(76));
if (junk.length) {
  console.log("FAIL — %d invented tickers. A well-formed wrong symbol looks",
              junk.length);
  console.log("exactly like a right one and buys a contract nobody named.");
  process.exit(1);
}
console.log("PASS — no invented tickers.");
console.log("Now READ the gained and lost lists above. A count is not a verdict:");
console.log("more entries is not better, fewer is not worse. Ask of each line,");
console.log("'is that a real call a room actually made?'");
process.exit(0);
