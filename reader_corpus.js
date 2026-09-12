/* Export the exact retained live-message corpus used by parser_gate.js. */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const dir = path.join(__dirname, "DS Logs");
const RE = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\[(.+?)#(\d+)\]\s+([\s\S]*)$/;
const seen = new Set(), rows = [];
for (const file of fs.readdirSync(dir).filter(f =>
  /^signal-room-chat.*\.txt$/.test(f))) {
  for (const line of fs.readFileSync(path.join(dir, file), "utf8").split("\n")) {
    const m = RE.exec(line);
    if (!m) continue;
    let text = m[4];
    if (text.startsWith("<history> ")) continue;
    const colon = text.indexOf(": ");
    const author = colon >= 0 && colon < 60 ? text.slice(0, colon).trim() : "?";
    if (colon >= 0 && colon < 60) text = text.slice(colon + 2);
    text = text.replace(
      /^(?:.*?)?(?:\[\s*)?\d{1,2}:\d{2}\s*[AP]M(?:\s*\])?\s+[A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}\s*[AP]M\s+/i, "");
    const key = m[1] + "|" + m[3] + "|" + text.slice(0, 120);
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({ id: crypto.createHash("sha256").update(key).digest("hex").slice(0,20),
      seq: rows.length,
      at: m[1], room: m[2].trim(), channelId: m[3], author, text });
  }
}
process.stdout.write(JSON.stringify(rows));
