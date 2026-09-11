/* test_bare_entry.js — bare contract + price, PER ROOM (9/7, TTT Lotto).
 *
 * That room's callers mostly skip the verb ("MU 8/28 965c @ 1.26"). Nine of its
 * entries fired and SEVEN were invisible. But this rule is OFF unless
 * settings.json entry_no_verb_channels names the channel, and that scoping was
 * MEASURED, not assumed: across the 7,168-line corpus, 51 currently-silent
 * lines match "contract + price", and the largest group is TradingTheTrend's
 * own daily LEVELS row —
 *     "QQQ 726c > 725.00  715p < 716.00  MU 1000c > 980.00 ..."
 * one line carrying eight contracts. Turned on globally, this rule buys a
 * watchlist. The rest were weekly recaps and victory laps.
 *
 * So the flag is half the safety and the vetoes below are the other half:
 * even INSIDE a named room, comparison operators, recap words, watch/loading
 * words and progress words still refuse. */
const path = require("path");
const { parseSignal } = require(path.join(__dirname, "parser.js"));
const ON = { entry_no_verb: true };
const FIRE = [
  ["verbless, @ price",  "MU 8/28 965c @ 1.26 yolo time, 0 or hero", "MU", 965, "CALLS"],
  ["verbless, bare",     "TSLA 9/4 360P .72",                        "TSLA", 360, "PUTS"],
  ["verbless, prose",    "Guys Friday lottos - NBIS 230C @.25",      "NBIS", 230, "CALLS"],
  ["verbless, 0dte",     "AMD 0dte 445p @ .76 grabbing a cheap lotto","AMD", 445, "PUTS"],
  ["BTO still fires",    "BTO SPY 8/17 776c @ .23 risky lotto",       "SPY", 776, "CALLS"],
  ["OWLS clls typo",     "RKLB 9/25 $70 clls 1.39 @everyone",          "RKLB", 70, "CALLS"],
];
const NEVER = [
  // THE ONE THAT MATTERS: eight contracts on one line, comparison operators
  ["levels row",     "QQQ 726c > 725.00 715p < 716.00 MU 1000c > 980.00 SNDK 1750c > 1731.00"],
  ["levels row 2",   "SPY 774c > 773.00 765p < 767.00 TSLA 325p < 330.00 CRWV 98p < 100.00"],
  ["weekly recap",   "8/10 - 8/14 Weekly Recap $QQQ 750C 23% Unrealized: $HD, $LEN"],
  ["victory lap",    "Update DINO 08/21/26 $90 Call @$5.45, runners up more than +560%!"],
  ["progress",       "0.93 on NVDA 220C +48% banger"],
  ["watchlist",      "Have my eyes on these $HPE $60c 11/20, most likely an earnings position"],
  ["on watch",       "SPY $654p on watch again for a quick scalp"],
  ["loading",        "loading GOOGL 8/21 345C @ 2.95"],
  ["credit spread",  "AAPL 307.5/305 PCS 8/28 .33"],
  ["a trim",         "STC META 0dte 600c .94 partial make the free"],
  ["shabs price recap", "Sick 320/con on MU 980c, meh but p is p @here"],
  ["flow observation", "ONON 29C 9/25 ~ 1M on flow; Need to see if it can close above the 21 ema (27.40)"],
];
let bad = 0;
console.log("MUST FIRE in a named room:");
for (const [n, t, sym, k, side] of FIRE) {
  const s = parseSignal(t, ON) || {};
  const ok = s.action === "OPEN" && s.symbol === sym && Number(s.strike) === k && s.side === side;
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(20)} ${s.symbol||"-"} ${s.strike??"-"} ${s.side||"-"} @${s.limit??"-"}`);
}
console.log("\nMUST NOT OPEN, even with the flag ON:");
for (const [n, t] of NEVER) {
  const s = parseSignal(t, ON) || {};
  const ok = s.action !== "OPEN";
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(20)} ${s.action || "-"}${s.action === "OPEN" ? " " + s.symbol + " " + s.strike : ""}`);
}
console.log("\nWITH THE FLAG OFF, the verbless ones must stay silent:");
for (const [n, t] of FIRE.slice(0, 4)) {
  const s = parseSignal(t, {}) || {};
  const ok = s.action !== "OPEN";
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(20)} ${s.action || "silent"}`);
}
console.log(bad ? `\n${bad} FAILED` : "\nall pass — verbless entries read in named rooms only, levels rows never");
process.exit(bad ? 1 : 0);
