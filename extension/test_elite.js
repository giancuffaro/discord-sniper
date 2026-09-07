/* test_elite.js — ELITE OPTIONS (Brando + Shoof), wired 9/7 after G bought Pro.
 *
 * Two callers, two grammars, both pipe-delimited:
 *   Brando: "@Elite BOUGHT | QQQ SEPT 2 717C $2.99 LOTTO"   month name, $price
 *   Shoof:  "@Elite ALERT BOUGHT | SPY 9/4 767C at 2.00"    numeric date, at-price
 * Exits are the dangerous half. BOTH put the size at the END, after the price:
 *   "(1/2)" "(1/4)" "(1/8)" "1/4 position" "3/4 position"
 * Those read as FULL EXITS before the trailing-partial fix, which would have
 * closed the whole position on a caller's quarter-trim. "ALL OUT" is the only
 * thing that may fire an exit — both callers write it literally. */
const path = require("path");
const { parseSignal } = require(path.join(__dirname, "parser.js"));
const C = [
  // --- Brando: entries
  ["brando entry",      "@Elite BOUGHT | QQQ SEPT 2 717C $2.99 LOTTO, just trading small for now", "OPEN", "QQQ", 717],
  ["brando roll",       "@Elite BOUGHT | QQQ SEPT 4 715C $3.27 roll w profits from 710C",          "OPEN", "QQQ", 715],
  ["brando dbl verb",   "@Elite BOUGHT | BOUGHT** | META AUG 28 580C $5.50 LOTTO",                 "OPEN", "META", 580],
  // --- Brando: exits
  ["brando 1/2",        "@Elite SOLD | QQQ SEPT 4 710C $5.00 1/2 POSITION, MOVED ITM SOLD SOME",   "TRIM", "QQQ", 710],
  ["brando 1/4 lower",  "@Elite SOLD | QQQ SEPT 4 710C $5.40 1/4 position, selling into strength", "TRIM", "QQQ", 710],
  ["brando 1/3",        "@Elite SOLD | MU AUG 14 1000C $5.50 1/3 POSITION, HOLDING 1/3 LEFT",      "TRIM", "MU", 1000],
  ["brando 3/4",        "@Elite SOLD | SNDK AUG 28 1550C $4.50 3/4 position",                      "TRIM", "SNDK", 1550],
  ["brando all out",    "@Elite SOLD | QQQ SEPT 4 710C $6.00 all out",                             "CLOSE","QQQ", 710],
  ["brando dbl space",  "@Elite SOLD |  QQQ AUG 28 715C $5.00 ALL OUT",                            "CLOSE","QQQ", 715],
  ["brando no-$ price", "@Elite SOLD | TSLA SEPT 4 380C 7.10 1/4 POSITION",                        "TRIM", "TSLA", 380],
  // --- Shoof
  ["shoof entry",       "@Elite ALERT BOUGHT | SPY 9/4 767C at 2.00",                              "OPEN", "SPY", 767],
  ["shoof lottos",      "@Elite ALERT BOUGHT | PLTR 9/4 190C at 2.43 LOTTOS",                      "OPEN", "PLTR", 190],
  ["shoof (1/2)",       "@Elite ALERT SOLD | SPY 9/4 767C at 2.60 (1/2)",                          "TRIM", "SPY", 767],
  ["shoof (1/8)",       "@Elite ALERT SOLD | SPY 8/14 775C at 3.00 (1/8)",                         "TRIM", "SPY", 775],
  ["shoof @ price",     "@Elite ALERT SOLD | NBIS 9/11 230C @ 7.60 (1/4)",                         "TRIM", "NBIS", 230],
  ["shoof (ALL OUT)",   "@Elite ALERT SOLD | ARM 9/18 300C at 2.15 (ALL OUT) - I'll revisit",      "CLOSE","ARM", 300],
  ["shoof $ + all out", "@Elite ALERT SOLD | HOOD 9/4 115C at $8.65 (ALL OUT)",                    "CLOSE","HOOD", 115],
  // SMH is slang in NOT_TICKERS; Shoof trades the ETF. Only with a contract.
  ["shoof SMH entry",   "@Elite ALERT BOUGHT | SMH 8/21 580C at 27.00",                            "OPEN", "SMH", 580],
  ["shoof SMH trim",    "@Elite ALERT SOLD | SMH 8/21 580C at 27.00 (1/4)",                        "TRIM", "SMH", 580],
];
const NEVER = [
  ["smh as slang",   "smh this market is brutal today"],
  ["smh + a ticker", "smh I cant believe SPY dropped 5 points"],
  // Brando posts share buys in the same channel. This bot trades options only.
  ["shares buy",     "@Elite BOUGHT | SNDK 500 SHARES AT $1444.50"],
  ["shares sell",    "@Elite SOLD | SNDK 250 SHARES AT $1550.50"],
];
let bad = 0;
for (const [n, t, act, sym, k] of C) {
  const s = parseSignal(t, {}) || {};
  const ok = s.action === act && s.symbol === sym && Number(s.strike) === k;
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(18)} ${(s.action||"-").padEnd(6)} ${s.symbol||"-"} ${s.strike??"-"}`);
}
console.log("\nMUST NEVER FIRE AN OPTION ORDER:");
for (const [n, t] of NEVER) {
  const s = parseSignal(t, {}) || {};
  const ok = s.action !== "OPEN" && s.action !== "CLOSE";
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(18)} ${s.action || "-"}`);
}
console.log(bad ? `\n${bad} FAILED` : "\nall pass — both Elite callers read clean, trims stay trims");
process.exit(bad ? 1 : 0);
