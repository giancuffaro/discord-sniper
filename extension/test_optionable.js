/* test_optionable.js — the ticker allowlist (9/8).
 *
 * optionable.txt is THE list of symbols this bot may trade: 6,337 option roots
 * pulled from the broker's own universe, plus futures and cash indexes. Read by
 * background.js AND bridge.py — one file, two readers, no drift.
 *
 * It exists because the reader treats a capitalised word in front of a strike
 * as a ticker, which is right almost always and catastrophic occasionally:
 *     "...has to hold ... then can go with 773c."  -> OPEN WITH 773C at market
 *     "| EXIT ALERT Ticker: NBIS Stopped out"      -> CLOSE EXIT (real: NBIS)
 * Blocking words one at a time never converges: blocking VERY moved the misread
 * on to GREEN, and the month list held only abbreviations so "PROFITS FROM
 * JUNE" produced ticker JUNE.
 *
 * Verified against every symbol our alerts have ever produced: the 33 it blocks
 * are all words or delisted small caps. ZERO real alerts are affected. */
const fs = require("fs"), path = require("path");
const txt = fs.readFileSync(path.join(__dirname, "optionable.txt"), "utf8");
const SET = new Set(txt.split("\n").map(s => s.trim().toUpperCase())
                       .filter(s => s && s[0] !== "#"));

const MUST_TRADE = [
  // the rooms' bread and butter
  "SPY","QQQ","IWM","NVDA","TSLA","AAPL","MSFT","META","AMZN","GOOGL","GOOG",
  "PLTR","AMD","MU","SNDK","HOOD","NBIS","ARM","AVGO","SMCI","COIN","MSTR",
  "UBER","DELL","CRWV","RDDT","SMH","XLF","PFE","WMT","IWM","DKNG","OKLO",
  // SMH is slang in NOT_TICKERS but a real ETF — it must be tradeable here
  "SMH",
  // futures roots and cash indexes
  "MNQ","MES","MGC","NQ","ES","SPX","SPXW","XSP","NDX","VIX",
];
const MUST_REFUSE = [
  // every one of these was produced as a "symbol" by the live parser
  "WITH","EXIT","VERY","GREEN","WHAT","FROM","ONLY","JUNE","NOTES","TESLA",
  "FVG","BREAK","YES","BABY","BANG","DAY","EVERY","FEEL","FILLS","FIRST",
  "FREE","HAD","IF","LIVE","ONE","REST","VIDEO","BTW","CORE","FEED",
];
let bad = 0;
console.log("list size: " + SET.size);
console.log("\nMUST BE TRADEABLE:");
for (const s of MUST_TRADE) {
  const ok = SET.has(s);
  if (!ok) { bad++; console.log(`  FAIL  ${s} is MISSING from the list — a real ticker would be blocked`); }
}
if (!bad) console.log(`  PASS  all ${MUST_TRADE.length} real symbols present`);
console.log("\nMUST BE REFUSED (all were real parser misreads):");
const leaked = MUST_REFUSE.filter(s => SET.has(s));
if (leaked.length) { bad += leaked.length; leaked.forEach(s => console.log(`  FAIL  ${s} is on the list`)); }
else console.log(`  PASS  all ${MUST_REFUSE.length} word-symbols refused`);
console.log("\nSANITY:");
const sane = SET.size > 5000 && SET.size < 20000;
if (!sane) bad++;
console.log(`  ${sane ? "PASS" : "FAIL"}  list size is plausible (${SET.size})`);
console.log(bad ? `\n${bad} FAILED` : "\nall pass — real tickers trade, words never do");
process.exit(bad ? 1 : 0);
