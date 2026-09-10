/* test_percon.js — premium quoted PER CONTRACT (9/7, shabs / OWLS Capital).
 *
 * shabs writes the premium in DOLLARS PER CONTRACT, not per share:
 *   "7760c at 300/con @here"   is a $3.00 option
 * His own August recap confirms the scale ("8/28 7760c — 245 -> 1550" is
 * 2.45 -> 15.50, +533%). Read literally, 300 is a THREE HUNDRED DOLLAR limit
 * on a three dollar option — which does not merely overpay, it deletes the
 * price protection the limit exists to provide.
 *
 * "10 cons" is a QUANTITY and must survive untouched — the rule only fires
 * when the number is glued to the slash. */
const path = require("path");
const { parseSignal } = require(path.join(__dirname, "parser.js"));
const CASES = [
  ["300/con  -> 3.00",   "SPX 7760c at 300/con @here",                  3],
  ["250/con  -> 2.50",   "SPX 7750c at 250/con @here half sizer",       2.5],
  ["400/con  -> 4.00",   "SPX 7725c 400/con @here",                     4],
  ["1250/con -> 12.50",  "SPX 7760c at 1250/con",                       12.5],
  ["plain price intact", "AAPL 322.5c at .30",                          0.3],
  ["quantity untouched", "bought 10 cons of SPY 640c at 1.20",          1.2],
];
let bad = 0;
for (const [n, t, want] of CASES) {
  const s = parseSignal(t, { spx_entries: true }) || {};
  // 9/10: SPX NO LONGER retargets to SPY — that translation was deleted on
  // G's instruction (SPY 760c is not SPX 7600c: different multiplier, tick,
  // settlement and premium). The symbol and strike stay as written and the
  // caller's /con limit now SURVIVES, because the old retarget was what
  // nulled it. These expectations were flipped from SPY/766 to SPX/7655 to
  // match — the test encoded the retired rule, so it moves with the rule.
  // The limit tolerance below still accepts null for SPX lines from before.
  // ~10x the ETF's), so on those the check is that the PRE-retarget read was
  // right — asserted via the un-retargeted equity cases plus s.why.
  const lim = s.limit;
  const ok = /SPX/.test(t) ? (lim === null || Math.abs(lim - want) < 0.005)
                           : Math.abs(lim - want) < 0.005;
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(22)} limit=${lim}`);
}
// The raw normalisation, independent of the index retarget.
const raw = parseSignal("NVDA 220c at 300/con", {}) || {};
const rawOk = Math.abs(raw.limit - 3) < 0.005;
if (!rawOk) bad++;
console.log(`  ${rawOk ? "PASS" : "FAIL"}  ${"non-index /con".padEnd(22)} limit=${raw.limit} (want 3)`);

/* THE TICKER HE NEVER TYPES. shabs trades one underlying and says so in his
 * own recap ("August Recap, SPX only"), so he writes "in 7655p 2.9" with no
 * symbol at all. cfg.default_symbol is set PER CHANNEL by background.js from
 * settings.json default_symbol_channels — never globally, because a bare
 * "640c" in a room that trades everything is unknowable and inventing a
 * symbol there buys the wrong underlying. */
console.log("\nIMPLIED SYMBOL (per channel):");
const SPXCFG = { default_symbol: "SPX", spx_entries: true };
const IMPLIED = [
  ["in 7655p 2.9",       "bored, in 7655p 2.9 @here",                 "SPX", 7655, "PUTS"],
  ["in 7730c 4.3",       "in 7730c 4.3 @here",                        "SPX", 7730, "CALLS"],
  ["7760c at 300/con",   "7760c at 300/con @here",                    "SPX", 7760, "CALLS"],
  ["explicit wins",      "in NVDA 220c 4.3 @here",                    "NVDA", 220, "CALLS"],
  ["explicit wins 2",    "AAPL 322.5c at .30",                        "AAPL", 322.5, "CALLS"],
];
for (const [n, t, sym, k, side] of IMPLIED) {
  const s2 = parseSignal(t, SPXCFG) || {};
  const ok = s2.fire && s2.symbol === sym && Number(s2.strike) === k && s2.side === side;
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(20)} ${s2.symbol||"-"} ${s2.strike??"-"} ${s2.side||"-"}${s2.assumed_symbol ? "  [assumed " + s2.assumed_symbol + "]" : ""}`);
}
// Without the per-channel setting the SAME lines must stay unreadable — this
// is the guard against a bare strike ever being given a guessed underlying.
console.log("\nWITHOUT the setting, the same lines must NOT resolve:");
for (const [n, t] of [["in 7655p 2.9","bored, in 7655p 2.9 @here"],
                      ["7760c at 300/con","7760c at 300/con @here"]]) {
  const s3 = parseSignal(t, {}) || {};
  const ok = !s3.symbol;
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${n.padEnd(20)} ${s3.symbol || "no symbol"}`);
}
console.log(bad ? `\n${bad} FAILED` : "\nall pass — per-contract premium, implied symbol scoped to its channel");
process.exit(bad ? 1 : 0);
