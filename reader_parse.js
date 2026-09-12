/* Read-only corpus parser: same room flags and allowlist as parser_gate.js. */
const fs = require("fs");
const path = require("path");
const parser = require("./extension/parser.js");

const symbols = new Set(fs.readFileSync(path.join(__dirname,
  "extension/optionable.txt"), "utf8").split("\n")
  .map(x => x.trim().toUpperCase()).filter(x => x && x[0] !== "#"));
if (typeof parser.setOptionable === "function") parser.setOptionable(symbols);

const rooms = {};
for (const line of fs.readFileSync(path.join(__dirname,
  "extension/rooms.txt"), "utf8").split("\n")) {
  if (!line || line[0] === "#") continue;
  const p = line.split("|");
  if (p.length < 5) continue;
  const rules = p[5] || "";
  const cfg = {};
  if (/\bbare\b/.test(rules)) cfg.entry_no_verb = true;
  if (/\bdotdate\b/.test(rules)) cfg.dot_date = true;
  if (/\breadonly\b/.test(rules)) cfg.read_only = true;
  const sym = /sym=([A-Z]+)/.exec(rules);
  if (sym) cfg.default_symbol = sym[1];
  const pivot = /pivot=([A-Z]+)/.exec(rules);
  if (pivot) cfg.pivot_root = pivot[1];
  rooms[p[0]] = cfg;
}

const input = JSON.parse(fs.readFileSync(0, "utf8") || "[]");
const output = input.map(r => {
  const cfg = Object.assign({}, rooms[String(r.channelId)] || {});
  const text = String(r.text || "");
  const low = text.toLowerCase();
  if (String(r.channelId) === "1449226651064991806") {
    if (low.includes("muggzone-options") || low.includes("muggzone message"))
      cfg.entry_no_verb = true;
    if (low.includes("shabs-sky-alerts") || low.includes("eli-alerts"))
      cfg.default_symbol = "SPX";
  }
  try {
    const s = parser.parseSignal(text, cfg) || {};
    return { action: s.action || null, symbol: s.symbol || null,
      strike: s.strike ?? null, side: s.side || null,
      expiry: s.expiry || null, limit: s.limit ?? null,
      fire: !!s.fire, why: s.why || "" };
  } catch (e) { return { action: null, error: String(e).slice(0, 100) }; }
});
process.stdout.write(JSON.stringify(output));
