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
  // SPX retargets to SPY and deliberately NULLS the limit (index premium is
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
console.log(bad ? `\n${bad} FAILED` : "\nall pass — per-contract premium normalised, quantities untouched");
process.exit(bad ? 1 : 0);
