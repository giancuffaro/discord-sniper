/* parser.js — the same brain as signals.py, in the browser.
 *
 * These two files must agree. test_parity.js runs every line of samples.txt
 * through both and fails if they ever read one differently, so if you edit one
 * and forget the other, you'll be told rather than finding out live.
 *
 * The room's grammar, which is what this is built around:
 *   loading AMD 7/31 480P          -> GET READY. The room's own rule: DO NOT BUY.
 *   in AMD 7/31 480P @ 3.4         -> the entry. The only thing that buys.
 *   trimming AMD @ 38%             -> a partial.
 *   all out of AMD                 -> full exit.
 *   exited SPY, and back in @ 2.84 -> out and straight back in.
 */

const RE_CALLER = /@\s*([A-Za-z0-9_.\-]{2,24})\s*\((admin|mod|analyst|scribe)\)/i;
const RE_PING = /@(everyone|here)\b/gi;
const RE_HDR = /^([A-Za-z0-9_.\- ]{2,24})\s*\((scribe|admin|mod)\)\s*[—\-]+\s*\d{1,2}:\d{2}\s*(AM|PM)\s*/i;
// SERVER TAG junk (9/2, found on Vero's SPY 763C that parsed as nothing):
// Discord's 2026 "Server Tag" badge leaks into the captured text as
// "Vero [PAID], Server Tag: PAID PAID Owner — 10:18 AM Wednesday, September
// 2, 2026 at 10:18 AM" — before, after, or on both sides of the call. Strip
// every copy: name + [TAG], the "Server Tag: X X" echo, an optional role
// word, and the dash-timestamp that follows. Mirrors signals.py.
const RE_STAG = /(?:[A-Za-z0-9_.$|&' \-]{1,40}?\s*\[[^\]]{1,16}\],?\s*)?Server Tag:\s*\S{1,16}(?:\s+\S{1,16})?(?:\s+(?:Owner|Admin|Founder|CEO|Mod|Moderator|Analyst|Trader))?(?:\s*[—\-]+\s*(?:\d{1,2}\/\d{1,2}\/\d{2,4},?\s*)?\d{1,2}:\d{2}\s*[AP]M(?:\s+[A-Za-z]+day,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}\s*[AP]M)?)?/gi;
const RE_EMOJI = /[\u{1F000}-\u{1FAFF}\u{2190}-\u{27BF}\u{FE0F}\u{200D}]/gu;

// The $ before the strike is Brett's habit: "In NVDA $210C to July 29th".
// The lookbehind is load-bearing. Without it the symbol group happily matches
// the TAIL of a longer word — "Loading 205 calls" gave a ticker of ADING, which
// then failed the allowed-list check for reasons that had nothing to do with
// what the line said.
// The expiry between symbol and strike can be a date, a DTE, or — the Whop
// room's habit — a month name: "Entered nvda July 20th 205c". Without the
// month alternative, "July" got read as the SYMBOL: entry came out TH 205C.
// (8/30: month-name dates may carry a YEAR — Vero writes "MSTR SEP 18 2026
// $150 CALLS" — so the date alternative accepts an optional ", 2026" tail.)
const RE_CONTRACT = /(?<![A-Za-z])\$?([A-Za-z]{1,5})\s+(?:(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d*dte|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)\s+)?\$?(\d{1,5}(?:\.\d{1,2})?)\s*(calls?|puts?|c|p)\b/gi;

// The same contract written back to front: "205 calls Friday expiration on
// NVDA". Requires the word "on" before the ticker — that's what keeps it from
// reading "10% on SPY" as a contract, and it's how they actually write it.
const RE_CONTRACT_REV = /(?<![A-Za-z\d.])\$?(\d{1,5}(?:\.\d{1,2})?)\s*(calls?|puts?|c|p)\b([^.!?]{0,40}?)\b(?:on|for)\s+\$?([A-Za-z]{1,5})\b/gi;

// TradeLikeGates ($STS / RWGates) posts in ThinkorSwim dotted form:
// ".HOOD260702C118" = HOOD, 2026-07-02, Call, strike 118. Unambiguous, so first.
const RE_CONTRACT_OSI = /\.([A-Za-z]{1,6})(\d{2})(\d{2})(\d{2})([CP])(\d{1,6}(?:\.\d{1,2})?)/i;

// "Friday expiration" is not a missing date — it's the same weekly the room's
// pinned rules already default to, said out loud. Kept as the token WEEKLY so
// the log can say "this Friday" and so turning assume_weekly_expiry off doesn't
// also refuse the calls where they actually told you.
const RE_FRI_EXP = /\bfri(?:day)?\s*exp\w*/i;

// Expiries that trail the contract instead of leading it — "to July 29th".
// Only consulted when the contract itself didn't carry one.
const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
                 jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
const RE_MONTH_DAY = /\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b/i;
const RE_DTE_ANY = /\b(\d*dte)s?\b/i;
const RE_DATE_ANY = /\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b/;

const RE_PCT = /@\s*(-?\d{1,3}(?:\.\d+)?)\s*%/;
// A percentage anywhere at all. The second room writes trims as a bare number:
// "20%", "50% @here", "40% in spy now". No verb, no ticker, just the number.
const RE_PCT_ANY = /(-?\d{1,3}(?:\.\d+)?)\s*%/;
// "5-6% risk." and "risk was only 10%" are position sizing, not a gain. Same
// shape as a bare trim and the exact opposite meaning — read as a trim it sells
// you out of a trade on a sentence about how much they're willing to lose. Only
// consulted when the line has no exit verb in it, so "trimming SPY @ 45%, risk
// free now" is untouched.
const RE_PCT_RISK = /\d{1,3}(?:\.\d+)?\s*%\s*(?:of\s+)?(?:risk|stop|trail)\b|\b(?:risk|risking|risked|stop|trail|lose|losing|lost|drawdown)\b[^.!?]{0,25}?\d{1,3}(?:\.\d+)?\s*%/i;
// "My avg is $3.05" — posted a minute after the entry, as its own message.
const RE_AVG = /\bavg|\baverage\b/i;
const RE_LIMIT = /@\s*\$?(\d+(?:\.\d{1,4})?)(?![\d.]*\s*%)/;
// "(2 CONS)" and "Entered (4) SLV 55C" — the 2K challenge posts HIS size
// with every entry, in parentheses. Captured for the record and for the
// day per-room LIVE wants to mirror his sizing.
const RE_QTY = /\b(\d{1,3})\s*(?:x|con(?:tract)?s?|lots?)\b/i;
const RE_QTY_PAREN = /\((\d{1,3})\)\s*(?=[A-Za-z$])/;
// Case-insensitive on purpose — the second room types "on spy", not "on SPY".
// Lowercase only counts when there's an allowed list; see bareSymbol.
const RE_BARE = /\b([A-Za-z]{1,5})\b/g;

/* ---- futures ---------------------------------------------------------------
 * Felony's grammar, from his real posts: "Short NQ @ 28660  Stop 29700
 * Target 28550". A futures call names no strike and no expiry — the symbol,
 * the direction and the price ARE the contract. The stop and target are his
 * own numbers in index points, and they're captured because the plan is to
 * use HIS levels instead of the flat 20% rule when his room trades. */
const FUT_SYMS = new Set(["NQ", "MNQ", "ES", "MES", "YM", "MYM", "RTY", "M2K",
                          "CL", "MCL", "GC", "MGC", "SI", "SIL", "NG"]);
/* A futures token the rooms wrote with a trailing digit -> its ROOT.
 * Same shape of bug as positions._fut_mult_for: the set is keyed by ROOT
 * ("MNQ") while a room writes the contract with a number stuck on the end.
 * Horizon posts "BTO MNQ1 29115"; "MNQ1" is in no set, so the entry branch
 * fell through to the no-price branch and the call died with NO log line at
 * all — a silent drop, twice (8/18 22:42, 8/25 21:38).
 * EXACT MATCH FIRST, so nothing that already works can change. Only an
 * unknown token gets its trailing digits stripped and retried. Returns the
 * root or null; the caller's price-band check still has the final say.
 * Mirrors signals._fut_root — test_parity holds the two together. */
function futRoot(raw) {
  const s = String(raw || "").toUpperCase();
  if (FUT_SYMS.has(s)) return s;
  const t = s.replace(/\d+$/, "");
  return (t && t !== s && FUT_SYMS.has(t)) ? t : null;
}
// The @ is optional now — his Day Trades channel writes "Short nq 28240.50"
// with nothing between the symbol and the price. "SL 28302" is Whop
// shorthand for the same stop ("SL at be" carries no number and stays
// unmatched), and "$800 a con" is "a contract" with the end bitten off.
// [\$/]? because the rooms write /NQ as often as $NQ; \.\d{1,3} because NG
// quotes "3.412" and two decimals truncated it to 3; the lookahead refuses
// a count posing as a price ("short NQ 2 contracts here" is a size).
// Mirrors signals.py exactly — test_parity holds the two together.
const RE_FUT_ENTRY = /\b(short|long)\s+[\$/]?([A-Za-z0-9]{1,4})\s*(?:@|at\b)?\s*\$?(\d[\d,]*(?:\.\d{1,3})?)\b(?!\s*(?:times?|contracts?|cons?|lots?|handles?|cents?|ticks?|points?|pts?|mins?|minutes?)\b)/i;
// A number outside these bands isn't a price, whatever the sentence says.
// Wide on purpose — they catch counts, zeros and fat fingers, not judge the
// market. A "short NQ @ 2" limit is BELOW the market and fills instantly,
// so the sell side is where a phantom price becomes a real position.
const FUT_PRICE_BAND = {
  NQ: [5000, 60000], MNQ: [5000, 60000],
  ES: [1500, 20000], MES: [1500, 20000],
  YM: [10000, 100000], MYM: [10000, 100000],
  RTY: [800, 10000], M2K: [800, 10000],
  CL: [10, 300], MCL: [10, 300],
  GC: [1000, 20000], MGC: [1000, 20000],
  SI: [10, 300], SIL: [10, 300],
  NG: [0.5, 30]
};
function futPriceOk(sym, px) {
  const b = FUT_PRICE_BAND[sym] || [0.1, 1e6];
  return px >= b[0] && px <= b[1];
}
// "St0p" with a zero is a real High Risk channel typo; "Target 1: 7600"
// numbers its targets — the label only counts when a colon follows.
const RE_THEIR_STOP = /\b(?:st[o0]p(?:\s*loss)?|sl)\s*[:=@]?\s*\$?(\d[\d,]*(?:\.\d{1,2})?)\b/i;
const RE_THEIR_TARGET = /\b(?:target|tp|pt)\s*(?:\d\s*[:=]\s*)?\$?(\d[\d,]*(?:\.\d{1,2})?)\b/i;
// "Target hit $1700 a contract - 2nd trim" / "$1,100 a contract on NQ short"
// / "$800 a con". His futures trims speak in dollars per contract, and on a
// dry run that number is the only honest exit price there is.
const RE_USD_CONTRACT = /\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(?:a|per|\/)\s*con(?:tract)?s?\b/i;
// His Futures-channel entry variants: "Long NQ - AVG 24015", "Long NQ -
// 23865 AVG", "Entered NQ short 23477 average", "Short RTY AVG - 2398.4".
// Direction + symbol either way round, price arriving as an average.
// Wandering shape first — "Re-entered long here @ 23480 on NQ" — or the
// alternation stops at "long here" and never reaches the symbol.
const RE_FUT_DIR_SYM = /\b(long|short)\b[^\n.]{0,24}?\bon\s+\$?([A-Za-z0-9]{1,4})\b|\b(long|short)\s+\$?([A-Za-z0-9]{1,4})\b|\b([A-Za-z0-9]{1,4})\s+(long|short)\b/gi;
const RE_FUT_AVG = /\b(?:avg|average)\s*[-:]?\s*\$?(\d[\d,]*(?:\.\d{1,2})?)\b|\b(\d[\d,]*(?:\.\d{1,2})?)\s+(?:avg|average)\b/i;
// The room says "gold"/"silver" as often as GC/SI.
const FUT_NICKNAMES = { GOLD: "GC", SILVER: "SI", PLATINUM: "PL" };
// "Stopped" alone at the start of a message, "Eh stopped", "Stop got hit",
// "BE stop hit", "Trailing stop hit on RTY" — their stop fired, said seven
// ways. Start-anchored so "if we get stopped" inside an entry's rationale
// never reads as an exit. An everyday preposition after the word kills the
// read: "Stopped by the store" and "Stopping for lunch" are errands, and
// each closed a live position in the Aug 3 drill. Mirrors signals.py.
const RE_STOP_HIT = /^(?:eh\s+|welp\s+)?stopp(?:ed|ing)\b(?!\s+(?:by|for|to|into|off|at\s+the)\b)|\b(?:be\s+|trailing\s+)?stop\s+(?:got\s+|was\s+)?hit\b/i;
// "stopped out of my personal trade, room trade still on" — HIS other
// account, not the call the room followed.
const RE_NOT_ROOM_TRADE = /\bpersonal\b|\broom\s+trade\s+still\b|\bnot\s+the\s+room\b/i;
// "Felony posted Jul 30, 2026 ..." — a date stamp INSIDE the body is an old
// post rendered on screen that the scraper picked up, never a live message.
// On Aug 3 one of these bought an expired contract. Mirrors signals.py.
const RE_STALE_STAMP = /\bposted\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b|·\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b|·\s*\d+\s*[dhw]\b/i;
// Boilerplate footer some rooms staple to a call — cut from the first marker to
// the end so its words (idea, p/l, disclaimer) can't veto the order. Mirrors
// RE_FOOTER in signals.py.
const RE_FOOTER = /\s*(?:how i trade\b|trade\s+idea'?s?\s+disclaimer|\bp\/?l\s*[:=]|\bdisclaimer\b|for\s+information(?:al)?\s+purposes\s+only|not\s+financial\s+advice|educational\s+only|©)[\s\S]*$/i;
// "Taking paper cut" / "Locking in a 8 point loss" — an early exit by hand.
// Verb-led on purpose: "those paper cuts we took yesterday" is a war story,
// "Taking papercut" is a sale.
// "Took an L" / "take the L" / "big L on this" — trader slang for a loss, i.e.
// they closed it red. Verb- or size-anchored so "cool", "LOL", a stray "l"
// never fire. Bullwinkle's "we took an L" on COIN went unread before this.
const RE_PAPERCUT = /\btak(?:e|ing)\s+(?:a\s+|this\s+|the\s+)?paper\s*cut|\btak(?:e|ing)\s+be\b|\btaking\s+the\s+loss\b|\block(?:ing)?\s+in\s+an?\s+\d+\s+point\s+loss\b|\b(?:took|tak(?:e|ing))\s+(?:a\s+|an\s+|the\s+|this\s+|that\s+)?l\b|\bthat'?s\s+(?:a\s+|an\s+|the\s+)?l\b|\b(?:big|small|tough|rough|another)\s+l\b|\bl\s+on\s+(?:this|that|the)\b/i;

function num(s) { return parseFloat(String(s).replace(/,/g, "")); }

/* ---- Aristotle's grammar, from his real corpus -----------------------------
 * PREP names the contract, then "In @here" is the trigger — HIS fill already
 * happened, the price arrives as its own message afterwards. So a bare "In"
 * fires on the last PREP, at the market. "Out" / "Fully out" close the same
 * way: no ticker, resolved by whose position it is. "QQQ 668 0 day puts
 * @here lightly" is a whole entry in five words. */
const RE_BARE_IN = /^(?:i'?m\s+|i\s+|we\s+)?in\b(?:\s+(?:here|everyone|starters?|lightly|light|small|super\s+light|very\s+light|these|again|now))*\s*(?:@?\s*\$?(\d{1,3}(?:\.\d{1,2})?))?\s*[.!]?$/i;
const RE_BARE_OUT = /^(?:i'?m\s+)?(?:fully\s+|all\s+)?out\b(?:\s+(?:of\s+)?half)?[\s!.]{0,4}$/i;
// Midas's "In @here my add level will be 744.30" / "In 0days at 1.97" — an
// IN at the start, not leading into prose, with a trading cue somewhere in
// the line. The blocklist is what keeps "In no rush to lose money today"
// from buying anything.
const RE_LOOSE_IN = /^(?:i'?m\s+|i\s+|we\s+)?in\b(?!\s+(?:no|not|the|a|an|this|that|it|order|fact|case|between|rush|and|but|on|to|for|honeydrip)\b)/i;
const RE_IN_CUE = /\d+\.\d{1,2}|\bstarters?\b|\bcons?\b|\b[01]\s*d(?:ays?|tes?)\b|\blightly\b|\bfill\b|\badd\s+level\b/i;
const RE_IN_PRICE = /(?:\bat|@)\s*\$?(\d{1,2}\.\d{1,2})\b/i;
// "All positions closed" / "Out of all trades" — everything this trader
// holds goes, whatever the tickers are.
// Midas confirms his entry three ways after a Loaded: a bare "Filled
// @here", a bare price with the word fill/avg ("1.97 fill", "Avg 1.61"),
// or "Taking more cons". All of them mean HE IS IN — fire on his last PREP.
// Midas's two-step entry (missed 8/11): "Loaded $PLTR 175p 8/14" then
// "4.10 entry @here" / "Full sized 3.80 avg" — price-only lines that pin to
// the loaded contract. Mirrors signals.RE_FILL_CONF exactly.
const RE_FILL_CONF = /^(?:filled)\b(?:\s+(?:light\s+size|lightly|starters?))*[\s.!]*$|^(?:full\s+siz(?:e|ed)\s+)?\$?(\d{1,2}\.\d{1,2})\s+(?:is\s+my\s+)?(?:final\s+)?(?:fill|avg|entry)\b[\s.!]*(?:@\w+[\s.!]*)?$|^avg\s+\$?(\d{1,2}\.\d{1,2})\b[\s.!]*$|^tak(?:e|ing)\s+(?:first|more|some)?\s*(?:size|cons?)\b/i;
const RE_CLOSE_ALL = /\ball\s+positions?\s+(?:are\s+)?closed\b|\bclos(?:ed|ing)\s+all\s+positions?\b|\bout\s+of\s+all\s+trades\b|\bsold\s+everything\b/i;
const RE_HALF = /\b(?:out\s+of|sold)\s+half\b/i;
// "Stopped out of half my position" / "Stopping out of 2nd entry" — their
// stop fired. Half or a numbered entry = partial; otherwise the trade's done.
// "Stopped out" is the main room. The Whop Day Trades room drops the "out":
// "Stopped on nq", "Stopped at be", "Stopped be on nq", "Stopped 20 point
// loss". All of them mean their stop fired.
const RE_STOPPED_OUT = /\bstopp?(?:ed|ing)\s+(?:out\b|on\s+\w|at\s+be\b|be\b|\d+\s+point)/i;
const RE_PARTIAL = /\bhalf\b|\b(?:2nd|second|1st|first)\s+entry\b|\bpart\b|\bsome\b/i;
// Entry-line filler that isn't information: sizing talk and hype words.
const RE_FILLER = /\b(?:lightly|light|super|very|small|starters?|lottos?|lotto|these|some|size|zero|for|high|risk|deg[ea]n|accts?|account|starter)\b|[()!,]|\.(?!\d)/gi;

// "loading" is the main room; "PREP AAPL 350 C 7/31" is Aristotle's word for
// the same thing, and Midas says "Loaded ... cons" — all of them mean GET
// READY, none of them buys.
const RE_LOADING = /\b(?:load(?:ing|ed)?|prep(?:ping|ped)?)\b/i;
const RE_ALLOUT = /\ball\s+out\b/i;
// 8/24: King Maker's "up +35%! taking some profits" slipped past this and the
// generic entry pattern BOUGHT the victory lap (spread guard saved it). Any
// "taking/took (some) profits" is an update on a ride, never a fresh entry.
const RE_TRIM = /\btrim(?:ming|med|s)?\b|\btook\s+some\s+off\b|\b(?:taking|took|booking|booked)\s+(?:some\s+)?profits?\b/i;
const RE_BACKIN = /\bback\s+in\b/i;
// "swinging" is an ENTRY verb here (his rule, 8/12: open today, close
// tomorrow) — mirrors signals.py RE_ENTRY. Present-progressive only, so
// "swing trade idea" / "that was a good swing" stay chatter.
const RE_ENTRY = /\b(?:in|entered|entering|filled|bto|bought|buying|grabbed)\b|\b(?:took|take|taking)\s+(?:some|a|entry|entries)\b|\bswinging\b(?!\s+(?:trade|idea|setup|watch))/i;
const RE_EXIT = /\b(?:exited|exiting|closed|closing|stc|sold|selling|out|cutting)\b/i;
// "Filled 3.95 starters" — their entry arrives as TWO messages. The contract was
// named minutes earlier in a "Loading 205 calls Friday expiration on NVDA"
// notice, and this line carries nothing but the price. On its own it is not an
// order; resolveLoaded in guards.js pins it to that notice, or nothing is sent.
// Only a line that STARTS with the fill verb counts — "trimmed at 3.95" and
// "their avg was 3.95" are the same numbers meaning the opposite thing.
const RE_BARE_FILL = /^(?:just\s+|we\s+|i\s+|i've\s+|ive\s+|we've\s+)*(?:filled|fills|filling|fill|bought|bto|entered)\b[^\d%]{0,14}\$?(\d{1,3}\.\d{1,2})\b(?!\s*%)/i;
// "$NVDA I took entry 1.37 fill" (RWGates shape, 9/3) — same two-message
// entry as RE_BARE_FILL above, but the ticker leads the line and "fill"
// trails the price instead of a fill verb leading it, so RE_BARE_FILL (which
// requires the message to START with filled/bought/bto/entered) never
// matches. "took entry" is not anchored to the front on purpose — the
// ticker or an "@here" can sit in front of it.
const RE_TOOK_ENTRY_FILL = /\btook\s+entr(?:y|ies)\b[^\d%]{0,20}\$?(\d{1,3}(?:\.\d{1,2})?)\s*fill\b/i;
// "added to SPY @everyone new avg is 2.8" — they doubled up and their average
// moved. Whether that buys you a second contract is a setting, not a parser
// decision: resolveAdd in guards.js has the final word, because only the guards
// know whether you're even in it.
// "added $ONDS 10c 7/17" — past-tense add straight onto a contract. "adding"
// alone matched but "added <contract>" slipped through and read as nothing (a
// missed entry).
const RE_ADD = /\badd(?:ed|ing|s)?\s+(?:to|more|into)\b|\badding\b|\badd(?:ed|ing)?\s+\$?[A-Za-z]{1,5}\s+\$?\d{1,4}(?:\.\d{1,2})?\s*(?:calls?|puts?|[cp])\b|\baverag(?:e|ed|ing)\s+(?:in|down|up)\b|\b(?:new|updated)\s+(?:avg|average)\b/i;
// The price out of "new avg is 2.8", "avg 3.05", "average: $2.90". Never a
// percentage — "avg gain 30%" is a result, not a price.
const RE_AVG_PRICE = /\b(?:avg|average)\w*\s*(?:is|of|at|around|near|:|=|@)?\s*\$?(\d{1,3}(?:\.\d{1,2})?)\b(?!\s*%)/i;
// The premium on an add, in priority order and NEVER off a stock level.
// "adding $LMND 65c ... off strong support @ $52" read $52 (the share price)
// as the premium. A real premium is "filled 10.00", "avg 8.70", or a bare
// "@ 1.2" — small, usually a decimal, never "$<whole number>".
const RE_FILL_PRICE = /\b(?:filled|fill|fills|filling|bought)\s+\$?(\d{1,3}(?:\.\d{1,2})?)\b(?!\s*%)/i;
function addPremium(t) {
  let m = RE_FILL_PRICE.exec(t);
  if (m) return parseFloat(m[1]);
  m = RE_AVG_PRICE.exec(t);
  if (m) return parseFloat(m[1]);
  const re = /@\s*(\$?)(\d+(?:\.\d{1,4})?)(?![\d.]*\s*%)/g;
  let mm;
  while ((mm = re.exec(t)) !== null) {
    const dollar = mm[1], numStr = mm[2], val = parseFloat(numStr);
    if (dollar && numStr.indexOf(".") === -1) continue; // "@ $52" is a share price
    if (val >= 100) continue;                            // no option trades at 100+
    return val;
  }
  return null;
}

const VETO_WORDS = ["do not", "don't", "dont ", "watching", "watch", "eyeing",
  // "Probably only got 10% out of that" is a P&L musing that read as a 10%
  // TRIM. "hold runners for breakeven" is coaching, not a sale — both are
  // advice/recap, never firm orders.
  "probably", "hold runners", "take trims",
  // "we have been SPOT on ... getting stopped out" read SPOT as a ticker and
  // fired CLOSE. "on watch" is a Nitro/are-alerts watchlist note, never a buy.
  "spot on", "on watch",
  "looking at", "thinking", "maybe", "might", "if it", "if you", "waiting",
  "wait for", "heads up", "scanner", "idea", "consider", "recap", "example",
  "entry / exit", "entry/exit",
  "congrats", "missed", "sorry", "pissed", "sets the tone", "session",
  "overall", "read was", "look at that", "still holding", "use $", "as risk",
  "anyone", "lmk", "great job",
  // The victory-lap paragraph. It's full of percentages and prices and it is
  // not a call — none of these words ever appear in one.
  "yesterday", "nice day", "conviction", "wish i",
  // "71.7% chance of no cut" on FOMC day — a percentage that is about the
  // Fed, not about a trade. Nearly parsed as a trim.
  "chance of", "probability", "odds of", "supposed to",
  // Midas planning out loud, day one live: "Not adding to this position"
  // would have BOUGHT five more if we'd been holding his trade — RE_ADD saw
  // "adding" and never looked left for the "Not". And "Some trim targets
  // are 737.70 and lower" is a map of where he MIGHT sell, not a sale.
  "not adding", "won't add", "wont add", "no adds", "trim target",
  // "I'm going to take 742c starters and add full size at 741.60" — Midas
  // narrating a PLAN. Day two the reader bought the verb: OPEN TAKE 742C.
  // Announced intent is not an entry; his entry is the fill that follows.
  "going to", "gonna",
  // "Short NQ @ 28660 — actually cancel that, no fill" fired the order and
  // ignored the retraction. The retraction wins. Same for "(paper account
  // only)", P&L lines and "Last week's long ES 7400" — a war story with a
  // parseable entry inside it. Mirrors signals.py.
  "cancel", "no fill", "never filled", "paper account", "last week",
  "pnl", "p&l", "p/l",
  // Aug 3 options drill: war stories and future-intent plans. NOT "earlier"
  // or "if we" alone — both live inside real calls. Mirrors signals.py.
  "was in", "almost", "tomorrow if",
  // 8/24: bullwinkle posted "SNDK $1500 C 41.00 I AM NOT GETTING IN THIS TOO
  // EXPINSIVE FOR ME" — a pass, not a call. The reader saw the strike and
  // tried to BUY it; only low cash refused it. A trader saying no is a no.
  "not getting in", "not taking", "not entering", "not buying",
  "too expensive", "too expinsive", "sitting this", "i'll pass", "ill pass",
  // 8/25: "AAPL OUT THE GATES" — hype for a rip at the open, and OUT read as
  // a full exit. Would have SOLD a held AAPL on a cheer.
  "out the gate"];

const NOT_TICKERS = new Set(["THE", "A", "AN", "IT", "ALL", "IN", "OUT", "AT",
  // "I got in SOME 400 C" — "some" is a word, not a ticker (8/10).
  // "SL HIT" — the stop got hit; HIT is a verb, not a ticker (8/11).
  "SOME", "HIT",
  "ON", "MY", "IS", "AND", "OF", "TO", "BE", "OK", "DTE", "AM", "PM", "ET",
  "DO", "NOT", "BUY", "SELL", "IE", "ADMIN", "HERE", "EOD", "CPI", "FOMC",
  "PT", "SL", "TP", "AVG", "GO", "UP", "WE", "US", "NO",
  // A5 - timezone tokens + option-strategy shorthand that read as tickers on
  // tickerless exits ("... 10:17 AM EDT" grabbed EDT). Blacklisted so a
  // symbol-less exit resolves from the open position instead.
  "EDT", "EST", "PST", "PDT", "CT", "MT", "UTC", "IV", "CSP", "CC", "CCS",
  "PCS", "STO", "BTO", "STC",
  // The verbs themselves. "sold 205 calls on nvda" read SOLD as the ticker,
  // because a word directly in front of a strike looks exactly like a symbol.
  // None of these is ever a ticker he trades.
  "SOLD", "TRIM", "HOLD", "GOT", "ADD", "FULL", "TOOK", "LOAD", "FILL",
  "CALL", "CALLS", "PUT", "PUTS", "LONG", "SHORT", "SIZE", "RISK", "NEW",
  "JUST", "NOW", "OVER", "UNDER", "NEAR", "ABOVE",
  // Day two live: "going to take 742c" bought TAKE, and "Keep 305 puts
  // loaded" once read KEEP as the ticker. Verbs in front of a strike.
  "TAKE", "KEEP",
  // Trader shorthand that looks exactly like a ticker once uppercase counts.
  "OPEX", "ORB", "HOD", "LOD", "EMA", "VWAP", "ATH", "RSI", "FIB", "PREP",
  "OK", "LOL", "SMH", "LFG", "BE", "PDT",
  // "WIN!!" in a victory lap read as ticker WIN. Mirrors signals.py.
  "WIN", "GAIN", "LOSS",
  // Whop role badges + repost boilerplate. "Trademorewiser (MOD) posted ...
  // Full sold NQ" read the (MOD) moderator badge as ticker MOD and MISSED the
  // NQ exit. MOD is the room's scribe, never a ticker. Mirrors signals.py.
  "MOD", "VIP", "POSTED", "FINAL", "CON", "CONS", "PDH", "PDL", "FTGH",
  "LH", "HH",
  // The Discord bot badge. "stockguy007 APP — ... Stopping out" and "Nitro
  // Trades APP — ... Closed SPY" read APP as ticker APP and fired CLOSE APP.
  "APP", "COMMENT", "ENTRY", "PRICE", "SWING",
  // Bullwinkle exit/management lingo that fired phantom CLOSEs on the word by
  // OUT ("OUT ALL BUT 1", "OUT HALF", "Bullwinkle EDU — ... OUT", "WILL STOP
  // OUT", "letting it RIDE", "NO MORE AFTER THIS"). None are the ticker.
  "BUT", "HALF", "MORE", "EDU", "TOO", "LAST", "WILL", "FORM", "LIGHT",
  "STARTER", "PENDING", "PICKED", "MARKETING", "LOTTO", "IDEA", "WATCH",
  "OPTION", "OPTIONS", "TRADE", "ALERT", "SETUP", "AFTER", "STOP", "RIDE",
  "TA", "WIL", "SIDELINES", "STRONG", "SMALL", "NEXT", "THIS", "THAT",
  // "OUT FOLKS" (Bullwinkle sign-off) -> phantom CLOSE FOLKS. Sign-off words,
  // never tickers; the real position is resolved from what's held.
  "LETTING", "FOLKS", "GUYS", "EVERYONE", "EVERYBODY", "TODAY", "HERE",
  "NOW", "DONE", "OFF"]);

// DISCORD ROW JUNK (9/2 corpus): when the reader hands over the whole row
// (grouped messages, forwards, re-renders) the call arrives wrapped in
// "ZTRADEZ BOT APP — 9:44 AM Wednesday, September 2, 2026 at 9:44 AM
// Forwarded @everyone …", "[ 9:38 AM ] Wednesday, … at 9:38 AM …",
// "Yesterday at 11:22 AM", trailing "2 Add Reaction". None of it is the call.
const RE_ROWHDR = /^\s*[^\n—]{1,70}?\s+—\s+(?:Yesterday at |Today at |\d{1,2}\/\d{1,2}\/\d{2,4},\s*)?\d{1,2}:\d{2}\s*[AP]M(?:\s+[A-Za-z]+day,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}\s*[AP]M)?\s*/i;
const RE_ROWTIME = /\[\s*\d{1,2}:\d{2}\s*[AP]M\s*\]\s*(?:[A-Za-z]+day,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}\s*[AP]M)?\s*/gi;
const RE_ROWMISC = /\b(?:Yesterday|Today) at \d{1,2}:\d{2}\s*[AP]M\b|\bForwarded\b|\b\d{0,3}\s*Add Reaction\b|\(edited\)/gi;

function cleanText(raw) {
  let t = String(raw || "").trim().replace(RE_STAG, " ").replace(RE_HDR, "");
  t = t.replace(RE_ROWHDR, "").replace(RE_ROWTIME, " ").replace(RE_ROWMISC, " ");
  t = t.replace(/:[a-z0-9_]{2,32}:/gi, " ");      // ":green_alert:" shortcodes (9/2)
  // ANSI color codes in Namrood's alerts ("[1;37;44mMETA") glued their
  // trailing "m" onto the ticker — META became MMETA (live, 8/17-18).
  // Strip them, with or without the ESC byte. Mirrors signals.py.
  t = t.replace(/\x1b?\[[0-9;]{1,16}m/g, " ");
  t = t.replace(RE_PING, " ").replace(RE_CALLER, " ").replace(RE_EMOJI, " ");
  // Numbered paste lines ("14. Loading 205 calls..."). The space after the dot
  // is required: without it "206.5 need to clear now" becomes "5 need to clear
  // now", and "747.5 calls on SPY" would turn into a strike of 5.
  t = t.replace(/^\s*\d{1,3}\.\s+/, "");
  // A1 - normalize smart quotes so a quoted premium ("2.21") parses.
  t = t.replace(/[“”]/g, '"').replace(/[‘’]/g, "'");
  // LABELLED TEMPLATE (9/2, Platinum Blue Collar: "LONG SETUP Ticker: SPY
  // Contract: 764 C Entry Zone: .50 Risk: 20% Stop TP1: 20% TP2: 763.93").
  // Rewrite the labels into the grammar every other room already speaks:
  // "BTO SPY 764 C @ 0.50". Risk/TP percentages go — they tripped the
  // "that's their risk" bail before the contract was ever looked at.
  // Only the Blue Collar shape (both labels) — ZT's "Entering Option: …
  // Entry: 0.82" and Nitro's "Entry Contract: TSLA $390p Price:" have
  // their own rules and must not be rewritten.
  if (/\bticker\s*:/i.test(t) && /\bcontract\s*:/i.test(t)) {
    t = t.replace(/\b(?:long|short)\s+setup\b/gi, "BTO")
         .replace(/\bticker\s*:\s*/gi, " ")
         .replace(/\bcontract\s*:\s*/gi, " ")
         .replace(/\bentry(?:\s*zone)?\s*:\s*/gi, " @ ")
         .replace(/\b(?:risk|tp\d?|target\d?|stop)\s*:\s*\$?\d+(?:\.\d+)?\s*%?/gi, " ")
         .replace(/\b(?:risk|tp\d?)\s*:/gi, " ");
    if (!/\b(bto|buy|in|entry|long)\b/i.test(t)) t = "BTO " + t;
  }
  // ".50" is a premium of 0.50 (9/2) — a leading-dot price never parsed.
  t = t.replace(/(^|[\s@$])\.(\d{1,2})\b/g, "$10.$2");
  // COLLECTIVE CORPUS (9/2 evening, 13 days of every room replayed): the
  // bot footers that ride on every alert carry veto words ("Do not take
  // this as financial advice" vetoed EVERY Market Guru call on "do not";
  // "None of this is financial advice" on Clutch; King Maker's "For
  // Educational Purposes Only"; the ZT relay's "© 2021-2026, Horizon
  // Analytics"). Cut the text at the first footer marker.
  t = t.replace(/\s*(?:IG:\s*\S+\s*\|?\s*)?None of this is financial advice[\s\S]*$/i, " ")
       .replace(/\s*Do not take this as financial advice[\s\S]*$/i, " ")
       .replace(/\s*@\S*\s*-\s*For Educational Purposes Only[\s\S]*$/i, " ")
       .replace(/\s*For (?:Educational|Informational) Purposes Only[\s\S]*$/i, " ")
       .replace(/\s*©\s*20\d\d[\s\S]*$/, " ")
       .replace(/\s*How I Trade\b[\s\S]*$/i, " ")
       .replace(/\s*@Namrood\s*-\s*Live[\s\S]*$/i, " ")
       .replace(/\s*Solely for informational purpose[\s\S]*$/i, " ");
  // NGD futures radar: "MGC SHORT (1m) @ 4496.35 | TP:4484.35 SL:4504.35 |
  // Prob:88% | R:R:1.5 NEW POTENTIAL SIGNAL ... probability ..." — the
  // call is the head; the summary after it carries the veto word.
  const radar = /^\s*(?:@\S+\s+)?([A-Z]{1,4})\s+(LONG|SHORT)\s*\(\d+m\)\s*@\s*(\d[\d,.]*)\s*\|\s*TP:\s*(\d[\d,.]*)\s*SL:\s*(\d[\d,.]*)/i.exec(t);
  if (radar) t = radar[2].toUpperCase() + " " + radar[1].toUpperCase() + " @ " + radar[3] +
                 " Stop " + radar[5] + " Target " + radar[4];
  // Felony / Whop: "Short NQ @ 29530 Stop 29570 Target 29450 Very high risk
  // here... if we break..." — a clean futures order followed by commentary
  // full of soft words. Keep the order, drop the essay.
  const fhead = /^\s*(?:@\S+\s+)?(long|short)\s+\$?\/?([A-Za-z0-9]{1,4})\s*(?:@|at)?\s*\$?(\d[\d,]*(?:\.\d{1,3})?)\s+(?:stop|sl)\s*(?:@|at|:)?\s*\$?(\d[\d,]*(?:\.\d{1,3})?)(?:\s+(?:target|tp)\s*(?:\d\s*:)?\s*(?:@|at|:)?\s*\$?(\d[\d,]*(?:\.\d{1,3})?))?/i.exec(t);
  // Only rewrite when the order is followed by prose (the essay case);
  // a clean multi-target line ("Target 1: 7600 Target 2: 7650") already
  // parses and must keep every target.
  if (fhead && FUT_SYMS.has(fhead[2].toUpperCase()) && /[a-z]{4,}\s+[a-z]{3,}\s+[a-z]{3,}/i.test(t.slice(fhead[0].length)))
    t = fhead[1] + " " + fhead[2].toUpperCase() + " @ " + fhead[3] + " Stop " + fhead[4] +
        (fhead[5] ? " Target " + fhead[5] : "");
  // Mr. Top Hat: "MNQ 24674 long quick scalp" / "MES quick short here 7697"
  // — the same order in two word orders the futures grammar never saw.
  t = t.replace(/\b(NQ|MNQ|ES|MES|YM|MYM|RTY|M2K|GC|MGC|CL|MCL|SI|NG)\s+(\d{3,6}(?:\.\d+)?)\s+(long|short)\b/gi, "$3 $1 @ $2")
       .replace(/\b(NQ|MNQ|ES|MES|YM|MYM|RTY|M2K|GC|MGC|CL|MCL|SI|NG)\s+(?:quick\s+)?(long|short)\s+(?:here\s+)?@?\s*(\d{3,6}(?:\.\d+)?)\b/gi, "$2 $1 @ $3");
  return t.replace(/\s+/g, " ").trim();
}

// A1 - after a contract is found, scan the whole message for the premium when
// it isn't written "@ 1.23": a bare "3.20", a quoted "2.21", or a range
// "13.25-13.40" (low end). Skips the strike, %-figures and anything >= 100.
function loosePremium(text, strike) {
  const mr = /(\d{1,3}(?:\.\d{1,2})?)\s*[-–]\s*(\d{1,3}(?:\.\d{1,2})?)(?!\s*%)/.exec(text);
  if (mr) {
    const lo = parseFloat(mr[1]);
    if (lo > 0 && lo < 100 && lo !== strike) return lo;
  }
  const reP = /\b(\d{1,3}\.\d{1,2})\b(?!\s*%)/g;
  let mp;
  while ((mp = reP.exec(text)) !== null) {
    const v = parseFloat(mp[1]);
    if (v === strike || v <= 0 || v >= 100) continue;
    return v;
  }
  return null;
}
// A1 - quantity-first entries ("2 cons QQQ 721 C 8/7 2.21") carry no verb; the
// leading count is the entry cue. Stripped as size, it never blocks the read.
const RE_QTY_LEAD = /^\s*\d{1,3}\s*(?:cons?|contracts?|lots?)\b/i;

/* "to July 29th" -> "7/29". Only used when the contract itself didn't carry an
 * expiry, so it can never override one they actually wrote. */
const RE_DAYS_ANY = /\b(\d{1,2})\s*days?\b/i;
// "tomorrow exp" is Midas's and Aristotle's way of writing 1DTE, and
// "today exp" is 0DTE said out loud.
const RE_TMRW_EXP = /\btomorrow\s+exp\w*/i;
const RE_TODAY_EXP = /\btoday\s+exp\w*|\bexpiring\s+today\b/i;
function expiryAnywhere(text) {
  if (RE_TMRW_EXP.test(text)) return "1DTE";
  if (RE_TODAY_EXP.test(text)) return "0DTE";
  let m = RE_MONTH_DAY.exec(text);
  if (m) return MONTHS[m[1].toLowerCase().slice(0, 3)] + "/" + parseInt(m[2], 10);
  m = RE_DTE_ANY.exec(text);
  if (m) return m[1].toUpperCase();
  // Aristotle writes "0 day" where the main room writes 0DTE. Same thing.
  m = RE_DAYS_ANY.exec(text);
  if (m) return parseInt(m[1], 10) + "DTE";
  m = RE_DATE_ANY.exec(text);
  if (m) return parseInt(m[1], 10) + "/" + parseInt(m[2], 10) + (m[3] ? "/" + m[3] : "");
  return null;
}

function findContract(text) {
  const osi = RE_CONTRACT_OSI.exec(text);
  if (osi && !NOT_TICKERS.has(osi[1].toUpperCase())) {
    return { symbol: osi[1].toUpperCase(), strike: parseFloat(osi[6]),
             side: osi[5].toLowerCase() === "c" ? "CALLS" : "PUTS",
             expiry: parseInt(osi[3], 10) + "/" + parseInt(osi[4], 10) + "/" + osi[2] };
  }
  RE_CONTRACT.lastIndex = 0;
  let m;
  while ((m = RE_CONTRACT.exec(text)) !== null) {
    const sym = m[1].toUpperCase();
    if (NOT_TICKERS.has(sym)) continue;
    const k = m[4].toLowerCase();
    let expiry = (m[2] || "").toUpperCase() || null;
    if (expiry && /^[A-Z]/.test(expiry) && !expiry.endsWith("DTE")) {
      const md = RE_MONTH_DAY.exec(expiry.toLowerCase());
      if (md) expiry = MONTHS[md[1]] + "/" + parseInt(md[2], 10);
    }
    if (!expiry) expiry = expiryAnywhere(text.slice(RE_CONTRACT.lastIndex));
    return { symbol: sym, strike: parseFloat(m[3]),
             side: k.startsWith("c") ? "CALLS" : "PUTS",
             expiry };
  }

  // Written back to front. Tried second so a normally-written contract in the
  // same line always wins.
  RE_CONTRACT_REV.lastIndex = 0;
  while ((m = RE_CONTRACT_REV.exec(text)) !== null) {
    const sym = m[4].toUpperCase();
    if (NOT_TICKERS.has(sym)) continue;
    const mid = m[3] || "";
    return { symbol: sym, strike: parseFloat(m[1]),
             side: m[2].toLowerCase().startsWith("c") ? "CALLS" : "PUTS",
             expiry: RE_FRI_EXP.test(mid) ? "WEEKLY" : expiryAnywhere(mid) };
  }

  // "QQQ 668 0 day puts" — the expiry sits BETWEEN strike and kind, which
  // neither shape above allows. Aristotle's habit.
  const md = /(?<![A-Za-z])\$?([A-Za-z]{1,5})\s+\$?(\d{1,5}(?:\.\d{1,2})?)\s+(\d{1,2})\s*days?\s+(calls?|puts?)\b/i.exec(text);
  if (md && !NOT_TICKERS.has(md[1].toUpperCase())) {
    return { symbol: md[1].toUpperCase(), strike: parseFloat(md[2]),
             side: md[4].toLowerCase().startsWith("c") ? "CALLS" : "PUTS",
             expiry: parseInt(md[3], 10) + "DTE" };
  }
  return null;
}

/* Lowercase ("30% on spy") only counts when there's an allowed-symbols list to
 * check it against. With no list there is nothing to check a lowercase word
 * against, and every third word in a sentence starts looking like a ticker. */
function bareSymbol(text, allowed) {
  RE_BARE.lastIndex = 0;
  let m;
  while ((m = RE_BARE.exec(text)) !== null) {
    const raw = m[1];
    const s = raw.toUpperCase();
    if (NOT_TICKERS.has(s)) continue;
    // A futures symbol written in capitals is recognisable on its own —
    // "on NQ short - Trimmed" has to resolve whether or not NQ is on the
    // options allowed-list, because that list is about options.
    // ...in ANY case — the Whop room types "Stopped on nq" all day, and
    // futures symbols aren't English words, so lowercase is safe here.
    if (FUT_SYMS.has(s)) return s;
    if (FUT_NICKNAMES[s]) return FUT_NICKNAMES[s];
    // Written in CAPITALS = a ticker, whoever's list it is or isn't on —
    // "Fully out of NBIS" has to resolve without NBIS being pre-listed.
    // The vocabulary list only unlocks lowercase ("40% in spy now").
    if (raw === s && s.length >= 2) return s;
    if (allowed.length && allowed.includes(s)) return s;
    continue;
  }
  return null;
}

function human(s) {
  if (!s.action) return "no trade";
  const bits = [s.action, s.symbol || "?"];
  if (s.strike) bits.push(String(s.strike) + (s.side === "CALLS" ? "C" : "P"));
  if (s.expiry) bits.push(s.expiry);
  if (s.limit) bits.push("@ " + s.limit.toFixed(2));
  if (s.pct !== null && s.pct !== undefined) bits.push("(+" + s.pct + "%)");
  return bits.join(" ");
}

// reenter belongs in the identity. "exited SPY, and back in" and a later plain
// "all out of SPY" are both CLOSE SPY on the same contract, but they're two
// different calls minutes apart — without this the real exit is thrown away as
// a duplicate of the re-entry and you ride the position into the close.
// Symbol stays at index 1: guardRecord's purge splits on "|" and reads it.
function signalKey(s) {
  // The caller is on the end now. Brett and Unraveler posting the same call
  // minutes apart are two trades, not a duplicate — without the name, the
  // second man's "all out of SPY" dies in the dedupe window of the first's.
  return [s.action, s.symbol, s.side, s.strike, s.expiry, s.pct,
          s.reenter ? 1 : 0,
          String(s.caller || "").toLowerCase()].join("|");
}

/* The reader, wrapped in the last set of no-matter-what checks. The inner
 * function stays exactly the battle-tested paths; this wrapper only gets to
 * turn a would-be OPEN into a loud refusal, never to create one. Mirrors
 * signals.py word for word — test_parity holds the two together. */
// Cash-settled index options can't trade on Webull, but their ETF proxy is the
// same directional bet at 1/10 the strike (SPX 7770 ≈ SPY 777). Retarget them so
// the room's SPX call becomes a tradeable SPY one. Mirrors signals.py.
const INDEX_ETF = { SPX: ["SPY", 10], SPXW: ["SPY", 10], XSP: ["SPY", 1],
                    RUT: ["IWM", 10], RUTW: ["IWM", 10] };
function indexToEtf(s, cfg) {
  if (!s || !s.symbol) return;
  const m = INDEX_ETF[String(s.symbol).toUpperCase()];
  if (!m) return;
  const hasAction = s.action === "OPEN" || s.action === "ADD" ||
                    s.action === "TRIM" || s.action === "CLOSE";
  const isOpt = s.side === "CALLS" || s.side === "PUTS" || s.strike !== null;
  if (!hasAction && !isOpt) return;
  // Fresh index entries are switched OFF (8/15, his word — mirrors
  // signals.py SPX_ENTRIES_ENABLED = False). This gate was missing here
  // while Python had it, so the extension would have bought SPY on an SPX
  // call Python refused — caught by test_parity on 8/17. Refuse loudly,
  // leave symbol/strike exactly as parsed; exits/trims still retarget below
  // so an old position can always be closed.
  if ((s.action === "OPEN" || s.action === "ADD") &&
      !(cfg && cfg.spx_entries)) {
    // Per-channel override (8/30, G: Ryan's alerts trade SPX — "make me
    // enter with SPY instead, pretty much the equivalent"): background.js
    // sets cfg.spx_entries = true when the message came from a channel in
    // settings.json spx_entry_channels. Everywhere else the 8/15 off
    // switch still holds.
    const was0 = String(s.symbol).toUpperCase();
    s.fire = false;
    s.why = was0 + " is a cash-index option - following it as an ETF is " +
            "turned off for now, so nothing was sent";
    return;
  }
  const etf = m[0], ratio = m[1];
  if (s.strike !== null && s.strike !== undefined) {
    const k = parseFloat(s.strike);
    if (!isNaN(k)) s.strike = Math.round(k / ratio);   // 7770 -> 777
  }
  const was = String(s.symbol).toUpperCase();
  s.symbol = etf;
  s.limit = null;                 // index premium ≠ ETF premium; bid the ETF market
  s.why = was + " isn't tradeable on Webull — following it as " + etf +
          (s.strike != null ? " " + s.strike : "") +
          (s.side === "CALLS" ? "C" : s.side === "PUTS" ? "P" : "") + " instead";
}

/* Refuse a futures entry whose LEVELS contradict the word. Mirrors
 * signals.py _direction_sanity. 8/12: "MNQ Shorts ... Entry 29868.25
 * Sl: 29848.25 TP 1 : 29889.25" — stop below, target above, i.e. a LONG's
 * shape. He'd mistyped "Shorts" and fixed it later, but the bot would have
 * sold the trade the room was buying. Words vs numbers disagree = one is a
 * typo and there's no telling which, so nothing goes out. */
function directionSanity(s) {
  if (s.action !== "OPEN" || !s.fire || s.kind !== "future") return;
  const d = String(s.direction || "").toUpperCase();
  if (!d) return;
  const short = d.startsWith("S");
  const entry = Number(s.limit);
  if (!isFinite(entry)) return;
  const bad = [];
  [["stop", s.their_stop, short], ["target", s.their_target, !short]]
    .forEach(([label, lvl, wantAbove]) => {
      if (lvl === null || lvl === undefined) return;
      const v = Number(lvl);
      if (!isFinite(v) || Math.abs(v - entry) < 1e-9) return;
      if ((v > entry) !== wantAbove) {
        bad.push(label + " " + v + " is " + (v < entry ? "below" : "above") +
                 " the " + entry + " entry");
      }
    });
  if (bad.length) {
    s.fire = false;
    s.why = "they wrote " + (short ? "SHORT" : "LONG") + " but the levels say " +
            "the opposite (" + bad.join("; ") + "). One of the two is a typo " +
            "and I can't tell which, so nothing was sent — check the room and " +
            "fire it by hand if it's real.";
  }
}

function parseSignal(text, cfg) {
  const s = parseSignalInner(text, cfg);
  indexToEtf(s, cfg);
  directionSanity(s);
  if (s.action !== "OPEN" || s.kind === "future") return s;
  const low = (s.clean || "").toLowerCase();
  const isOption = s.side === "CALLS" || s.side === "PUTS" || s.strike !== null;
  // A PROGRESS UPDATE wearing an entry's clothes (8/18): "KO ... @$0.62,
  // up more than 90%!, my order filled little earlier, will look to close
  // the remaining" — parses like a fresh call, but it's a victory lap
  // about a trade ALREADY made. A real entry never brags about its own
  // gain in the same breath. Mirrors signals.py.
  if (s.action === "OPEN" && (
      /\bup\s+(?:more\s+than\s+)?\d{1,4}\s*%/.test(low)
      || /\bfilled\s+(?:a\s+)?(?:little\s+|bit\s+)?earlier/.test(low)
      || /\bwill\s+look\s+to\s+close/.test(low)
      || /\bclos(?:e|ed|ing)\s+the\s+remaining/.test(low))) {
    s.fire = false; s.action = null;
    s.why = "that's a progress update on an EARLIER call (it brags about " +
            "the gain / mentions closing the rest) — not a fresh entry, so " +
            "nothing was sent";
    return s;
  }
  // UNDERLYING hard stop on an options entry (his INTC alert, 8/18):
  // "stop loss under 97 hard stop" = INTC THE STOCK under $97, not the
  // premium. Rides in their_stop; the bridge's stock watcher closes the
  // option when the stock crosses it. Mirrors signals.py.
  if (isOption && (s.their_stop === null || s.their_stop === undefined)) {
    const mu = /\b(?:hard\s+)?(?:st[o0]p(?:\s*loss)?|sl)\s*:?\s+(?:is\s+)?(?:under|below|above|over)\s+\$?(\d[\d,]*(?:\.\d+)?)\b/.exec(low);
    if (mu) s.their_stop = parseFloat(mu[1].replace(/,/g, ""));
  }
  if (isOption && /\b(sell|selling|sold|sto)\b/.test(low)
      && !/\b(bto|buy|buying|bought)\b/.test(low)) {
    s.fire = false; s.action = null;
    s.why = "they're SELLING that option — this bot only ever buys, so " +
            "nothing was sent";
    return s;
  }
  if (isOption && s.strike !== null && Number(s.strike) <= 0) {
    s.fire = false; s.action = null;
    s.why = "a strike of 0 isn't a contract — refused, not guessed";
    return s;
  }
  if (isOption && s.limit !== null
      && (Number(s.limit) <= 0 || Number(s.limit) >= 1000)) {
    s.fire = false; s.action = null;
    s.why = Number(s.limit) + " isn't a plausible option premium — refused, " +
            "not guessed";
    return s;
  }
  if (/\$[A-Za-z]{1,5}\.[A-Za-z]\b/.test(s.raw || "")) {
    s.fire = false; s.action = null;
    s.why = "a dot-class ticker (BRK.B style) — the reader mangles these " +
            "into the wrong symbol, so nothing was sent";
    return s;
  }
  return s;
}

function parseSignalInner(text, cfg) {
  cfg = cfg || {};
  const allowed = (cfg.allowed_symbols || []).map(x => String(x).toUpperCase());
  const raw = String(text || "").trim();
  const s = { fire: false, why: "", action: null, symbol: null, side: null,
              strike: null, expiry: null, limit: null, pct: null, qty: null,
              caller: "", reenter: false, reenter_limit: null, named_symbol: null,
              needs_position: false, needs_loaded: false, needs_add: false,
              // Futures and his-levels support. kind is "future" on a futures
              // call and "" otherwise; direction is LONG/SHORT; their_stop and
              // their_target are the levels HE posted; usd is "$1,100 a
              // contract" off a trim, the only honest futures exit price a
              // dry run has.
              kind: "", direction: null, their_stop: null, their_target: null,
              usd: null,
              // "All positions closed" — close everything this trader holds.
              all: false,
              warn: "", raw, clean: "", matched: "" };
  if (!raw) { s.why = "empty message"; return s; }

  let t = cleanText(raw);
  // Strip the boilerplate FOOTER some rooms staple to a call (a disclaimer or a
  // running P/L line) so its words can't veto the order in front. Mirrors
  // signals.py — Market Bishop's "idea" and Namrood's "P/L:" were killing real
  // trims. Cuts from a known marker to the end only.
  t = (t.replace(RE_FOOTER, "").trim()) || t;
  // A2 - forwarded/relayed embed: "X (MOD) posted <Channel> - <Cat> Entered
  //      ...". Unwrap to the trading verb and re-parse; drop lotto/yolo noise.
  {
    const rel = t.match(/\bposted\b\s+.+?\s+[-–]\s+.+?\s+((?:entered|in|bto|open(?:ed|ing)?|taking|buying|bought|trimming|trimmed|closed|sold|out)\b[\s\S]*)$/i);
    if (rel) t = rel[1].replace(/\b(?:lotto|yolo)\b/gi, " ").replace(/\s+/g, " ").trim();
  }
  s.clean = t;
  const low = t.toLowerCase();
  // HARD VETO — a trader saying NO outranks every pattern below, including
  // the trader-specific formats that return before the normal veto list is
  // consulted. 8/24: bullwinkle's "SNDK $1500 C 41.00 I AM NOT GETTING IN
  // THIS TOO EXPINSIVE" matched his own entry format and tried to BUY the
  // pass; only low cash refused it. Mirrors signals.py.
  for (const hv of ["not getting in", "not taking", "not entering",
                    "not buying", "too expensive", "too expinsive",
                    "sitting this", "i'll pass", "ill pass"]) {
    if (low.includes(hv)) {
      s.why = "the trader passed on it (\"" + hv + "\") — not a call";
      return s;
    }
  }
  // RETRACTION (8/26, bullwinkle's "NOT READY YET REVISING" 60s after a
  // TSLA call the bot had already bid on): a trader pulling a call back is
  // an ORDER — cancel my in-flight entry and any armed pullback of theirs.
  // Only fires when the message is a bare retraction (no fresh contract in
  // it); a revision WITH a new contract parses as its own new call below.
  if (/\b(?:not\s+ready(?:\s+yet)?|revising|scratch\s+that|cancel\s+that|disregard(?:\s+that)?|hold\s+off|nevermind|never\s*mind)\b/i.test(low)
      && !/\d{1,5}(?:\.\d+)?\s*[CcPp]\b/.test(t)) {
    s.action = "RETRACT";
    s.fire = true;
    const rt = /\b([A-Z]{2,5})\b/.exec(t.toUpperCase());
    if (rt && !NOT_TICKERS.has(rt[1])) s.symbol = rt[1];
    s.why = "the trader pulled the call back — cancelling anything of " +
            "theirs still in flight";
    return s;
  }
  // BE STOPS (8/29, G): "you can use breakeven stops" = move the stop to
  // the ENTRY price. Zero loss allowed from here. Ticker optional.
  if (/\b(break\s*-?even|b\/?e)\s+stops?\b|\bstops?\s+(?:to|at)\s+break\s*-?even\b/i.test(low)) {
    s.action = "STOPMOVE";
    s.be = true;
    s.fire = true;
    const _rebe = /\b([A-Z]{1,5})\b/g; let _mbe;
    const _upbe = t.toUpperCase();
    while ((_mbe = _rebe.exec(_upbe)) !== null) {
      if (!NOT_TICKERS.has(_mbe[1]) && !/^(FIRST|GUYS|CAN|USE|OKAY|STOPS|MOVE|BREAK|EVEN|B\/E|BE)$/.test(_mbe[1])) { s.symbol = _mbe[1]; break; }
    }
    s.why = "their call: breakeven stops — stop moves to the entry";
    return s;
  }
  // STOPMOVE (8/29, G): "lowering my stop loss on Tesla, 351 new stop
  // loss" — the number is the UNDERLYING price, the action is moving
  // their stop. Never an entry, never an exit, never a strike.
  {
    const sm = /\b(?:new stop(?:\s*loss)?(?:\s+is)?|(?:lower|rais|mov|adjust)(?:ing|ed)?\s+(?:my\s+)?stop(?:\s*loss)?(?:\s+(?:to|at))?)\b/i.test(low)
      && /\b(\d{2,5}(?:\.\d+)?)\b/.test(t);
    if (sm && !/\b(call|put)s?\b/i.test(low)) {
      const _scan = t.toUpperCase().replace(/\bSTOP\b|\bLOSS\b|\bNEW\b/g, " ");
      let tkSym = null, _m2;
      const _re2 = /\b([A-Z]{1,5})\b/g;
      while ((_m2 = _re2.exec(_scan)) !== null) {
        if (!NOT_TICKERS.has(_m2[1]) && !/^(MOVIN|GUYS|LOWER|RAIS|MY)$/.test(_m2[1])) { tkSym = _m2[1]; break; }
      }
      const lv = /\b(\d{2,5}(?:\.\d+)?)\b/.exec(t);
      if (lv) {
        s.action = "STOPMOVE";
        s.their_stop = parseFloat(lv[1]);
        if (tkSym) s.symbol = tkSym;
        s.fire = true;
        s.why = "their stop moved to " + s.their_stop + " on the stock";
        return s;
      }
    }
  }
  // Swing wording anywhere on the line tags the signal (harmless on
  // non-entries — only entries ever store or show it). Mirrors signals.py.
  s.swing = /\bswing(?:ing|s)?\b/.test(low);

  // Before every format reader on purpose: on Aug 3 a "Felony posted
  // Jul 30" scrape bought an expired NVDA contract because the entry
  // grammar got to it first. Mirrors signals.py.
  if (RE_STALE_STAMP.test(t)) {
    s.why = "carries its own date stamp — a rendered old post the scraper " +
            "picked up, not a live call";
    return s;
  }

  // Credit/debit spreads and iron condors are MULTI-LEG — a buy-only bot can't
  // follow them, and he dropped credit spreads on purpose. "Put Credit Spread
  // (PCS) ... SPX PCS 7720/7710 ... Target: 30%+" used to read as TRIM PCS.
  // Vetoed here, before any format reader, so no spread reaches the book.
  if (/\bcredit\s+spread\b|\bdebit\s+spread\b|\biron\s+condor\b|\bput\s+credit\b|\bcall\s+credit\b|\b(?:pcs|ccs|csp)\b/.test(low)) {
    s.why = "a credit/debit spread or cash-secured put (a selling strategy) — " +
            "the buy-only bot doesn't trade these";
    return s;
  }

  // Promo / recruitment spam ("50% OFF A FUNDED PORT ... USING CODE ..."): it
  // carries a percent and "OFF" so it read as TRIM OFF. An ad, not a call.
  if (/\d{1,3}\s*%\s*off\b|\busing\s+code\b|\bfunded\s+(?:port|account|trader)\b|\bprop\s+firm\s+funding\b|\bsign\s*up\b/.test(low)) {
    s.why = "promotional / recruitment message, not a trade call";
    return s;
  }

  // Who said it. Two shapes: the scribe relaying somebody ("@Brett (Admin)
  // ..."), and the admin posting straight into the room ("Brett (Admin) —
  // 10:20 AM ..."). The relay wins when both are there.
  const mh = RE_HDR.exec(raw);
  if (mh) s.caller = mh[1].trim();
  const mc = RE_CALLER.exec(raw);
  if (mc) s.caller = mc[1];

  // ---- Market Guru™ Alerts labeled futures format:
  //        Ticker: `MNQ SHORT SMALL RISKY TRADE`  Entry: 28590  Stoploss: 28620
  //      symbol is a micro future, extra words are noise, entry/stop are index
  //      points. Management arrives as bare point counts ("14 points trim",
  //      "102 points exit target hit"); the point number is their P&L, the
  //      trim/exit word acts, a lone "309 points omg" does nothing.
  const mg = /ticker:\s*`?\s*([A-Za-z]{2,4})\b([^`\n]*)/i.exec(t);
  if (mg && FUT_SYMS.has(mg[1].toUpperCase())
        && /\bentry:\s*[\d]/i.test(t)) {
    s.symbol = mg[1].toUpperCase();
    s.kind = "future";
    s.direction = /short/i.test(mg[2]) ? "SHORT" : "LONG";
    const me = /\bentry:\s*([\d][\d.,]*)/i.exec(t);
    if (me) s.limit = num(me[1]);
    const ms = /\bstop\s*loss:?\s*([\d][\d.,]*)/i.exec(t);
    if (ms) s.their_stop = num(ms[1]);
    s.action = "OPEN"; s.matched = "market-guru futures entry"; s.fire = true;
    if (s.limit == null || isNaN(s.limit))
      s.warn = "no entry price posted — it pays the market.";
    s.why = "entry: " + s.direction + " " + s.symbol + " @ "
            + (s.limit ? s.limit : "mkt");
    return s;
  }

  // Market Guru management by running point count. "exit"/"target hit" closes,
  // a trim word trims; both resolve against what you hold. A bare "N points"
  // (no verb) falls through and ends as a non-order.
  const mgp = /^\s*[-+]?\d+(?:\.\d+)?\s*points?\b([\s\S]*)$/i.exec(low);
  if (mgp && low.indexOf("$") === -1 && !/\ba con(?:tract)?\b/i.test(low)) {
    // bare point call only — "$800 a con" is Felony's dollar exit, handled below.
    const rest = mgp[1];
    if (/\bexit\b|target\s*hit/i.test(rest)) {
      s.action = "CLOSE"; s.matched = "market-guru points exit";
      s.needs_position = true;
      s.why = "their exit on the points call — close what it belongs to";
      return s;
    }
    if (RE_TRIM.test(rest)) {
      s.action = "TRIM"; s.matched = "market-guru points trim";
      s.needs_position = true;
      s.why = "their trim on the points call — sell some of it";
      return s;
    }
  }

  // ---- "Open / Update / Closed" alert-bot format (JPM Options and the like):
  //      "Open  SPY 08/03 753C @.92" enters; "Update ... (+40%)" is a running
  //      P&L post and must NEVER read as a trim; "Closed"/"Close" exits. Gated
  //      on a readable contract so a stray "close the door" does nothing.
  // A short lead-in before the label is allowed: are-alerts writes "For my
  // small fries : OPEN $HPE $30 call 5/15 @ 0.50 (swing)".
  const jm = /^(?:[^:\n]{1,40}:\s+)?(open|update|closed|close)\b\s*([\s\S]*)$/i.exec(t);
  if (jm && findContract((jm[2] || "").trim())) {
    const label = jm[1].toLowerCase();
    const rest = (jm[2] || "").trim();
    if (label === "update") {
      s.why = "an Update — a running P&L post, not an order";
      return s;
    }
    const c = findContract(rest);
    s.symbol = c.symbol; s.strike = c.strike; s.side = c.side; s.expiry = c.expiry;
    const mp = /@\s*\$?([0-9]*\.?[0-9]+)/.exec(rest);
    s.limit = mp ? parseFloat(mp[1]) : null;
    if (label === "open") {
      s.action = "OPEN"; s.matched = "open-label entry"; s.fire = true;
      if (s.limit === null || isNaN(s.limit))
        s.warn = "no price on the entry — it pays the market.";
      s.why = "entry: " + human(s);
    } else {
      s.action = "CLOSE"; s.matched = "close-label exit";
      s.why = "full exit on " + s.symbol;
    }
    return s;
  }

  // ---- Bullwinkle (ZTRADEZ) format: "AMD | $550 C 12.72", "QQQ $707 P 8.75",
  //      "/MES | LONG HERE". CC/CSP are SELLING strategies, never a buy — the
  //      single-letter [CP] word boundary refuses to read them.
  const bwf = /^\/?([A-Za-z]{2,4})\s*\|\s*(long|short)\s+here\b/i.exec(t);
  if (bwf && FUT_SYMS.has(bwf[1].toUpperCase())) {
    s.symbol = bwf[1].toUpperCase(); s.kind = "future";
    s.direction = bwf[2].toUpperCase();
    s.action = "OPEN"; s.matched = "bullwinkle futures entry"; s.fire = true;
    s.warn = "no price on the entry — it pays the market.";
    s.why = "entry: " + s.direction + " " + s.symbol;
    return s;
  }
  // Clutch (9/2): a date, "0DTE" or "Swing:" may lead the same shape —
  // "8/28 SLV 60C 1.68 swing", "0DTE GOOGL 345C .84", "Swing: 9/04 SMR 10C .54".
  const bwPre = /^(?:(?:swing(?:ing)?|lotto|scalp|day\s*trade)\s*:?\s+)?(?:(\d{1,2}\/\d{1,2}(?:\/\d{2,4})?|\d*dte)\s+)?/i.exec(t);
  const bwT = bwPre && bwPre[0] ? t.slice(bwPre[0].length) : t;
  const bwLeadExp = bwPre && bwPre[1] ? bwPre[1] : null;
  const bw = /^([A-Za-z]{1,5})\s*(\|)?\s*(\$)?(\d{1,5}(?:\.\d+)?)\s*([CcPp])\b([\s\S]*)$/.exec(bwT);
  // 8/25: "AAPL 315 C 2.13" with no pipe and no $ is still his entry shape —
  // accept it when a plain decimal premium follows (a bare % never counts).
  if (bw && (bw[2] || bw[3] || /(?<![\d$.])\d+\.\d{1,2}(?!\s*%)/.test(bw[6] || ""))
      && !NOT_TICKERS.has(bw[1].toUpperCase())) {
    const rest = bw[6];
    s.symbol = bw[1].toUpperCase();
    s.strike = parseFloat(bw[4]);
    s.side = bw[5].toUpperCase() === "C" ? "CALLS" : "PUTS";
    const md = /\b(\d{1,2}\/\d{1,2})\b/.exec(rest);
    if (md) s.expiry = md[1];
    else if (bwLeadExp) s.expiry = /dte/i.test(bwLeadExp) ? bwLeadExp.toUpperCase() : bwLeadExp;
    const mp = /(?<![\d$])(\d+\.\d{1,2})\b/.exec(rest);
    s.limit = mp ? parseFloat(mp[1]) : null;
    s.action = "OPEN"; s.matched = "bullwinkle entry"; s.fire = true;
    if (s.limit === null || isNaN(s.limit))
      s.warn = "no premium I could read — it pays the market.";
    s.why = "entry: " + human(s);
    return s;
  }

  // ---- The Market Bishop / "The Pawn": "I'm Entering Option: NOW 97 C 7/24
  //      Entry: 0.82". The label makes the ticker unambiguous (NOW = ServiceNow).
  const pw = /^(?:@\w+\s+)?i'?m\s+entering\s+option:?\s*([\s\S]*)$/i.exec(t);
  if (pw) {
    const mc = /^\s*([A-Za-z]{1,5})\s+\$?(\d{1,5}(?:\.\d+)?)\s*([CcPp])\b([\s\S]*)$/.exec(pw[1]);
    if (mc) {
      s.symbol = mc[1].toUpperCase();
      s.strike = parseFloat(mc[2]);
      s.side = mc[3].toUpperCase() === "C" ? "CALLS" : "PUTS";
      const md = /\b(\d{1,2}\/\d{1,2})\b/.exec(mc[4]);
      if (md) s.expiry = md[1];
      const me = /entry:?\s*\$?([0-9]*\.?[0-9]+)/i.exec(pw[1]);
      s.limit = me ? parseFloat(me[1]) : null;
      s.action = "OPEN"; s.matched = "market-bishop entry"; s.fire = true;
      if (s.limit === null || isNaN(s.limit))
        s.warn = "no entry price posted — it pays the market.";
      s.why = "entry: " + human(s);
      return s;
    }
  }

  // ---- TLM (9/2): "Aapl Aug 26 315 call at 1.75 Target 2.10" — a full
  //      contract and a price, no verb at all. Short, verb-less, priced =
  //      an entry; anything with a sell/trim/update word stays out of here.
  {
    const bare = findContract(t);
    const atp = /\b(?:at|@)\s*\$?(\d{1,3}(?:\.\d{1,2})?)\b(?!\s*%)/i.exec(t);
    if (bare && atp && t.length <= 110 &&
        !/\b(sold|sell|selling|out|close|closed|closing|trim|trimm|stop|stops|update|watch|watching|target hit|hedge|spread|avg|average|now)\b/i.test(t) &&
        !NOT_TICKERS.has(bare.symbol)) {
      const px = parseFloat(atp[1]);
      if (px > 0 && px !== bare.strike) {
        s.symbol = bare.symbol; s.strike = bare.strike; s.side = bare.side;
        s.expiry = bare.expiry || null; s.limit = px;
        s.action = "OPEN"; s.matched = "bare priced entry"; s.fire = true;
        s.why = "entry: " + human(s);
        return s;
      }
    }
  }

  // ---- Nitro Trades: "Entry Contract: TSLA $390p Price: $1.75 Comments:none".
  //      Fully labeled — the "Entry Contract:" / "Price:" tags make it
  //      unambiguous. "Comment ... on watch" is a watch (vetoed above).
  // ei.trades (9/2) drops the word "Entry": "Contract: QQQ $711 p Price: $1.68".
  const ntr = /\b(?:entry\s+)?contract:?\s*\$?([A-Za-z]{1,5})\s+\$?(\d{1,5}(?:\.\d{1,2})?)\s*([CcPp])\b(?:[\s\S]*?\bprice:?\s*\$?(\d+(?:\.\d{1,2})?))?/i.exec(t);
  if (ntr && !NOT_TICKERS.has(ntr[1].toUpperCase())) {
    s.symbol = ntr[1].toUpperCase();
    s.strike = parseFloat(ntr[2]);
    s.side = ntr[3].toUpperCase() === "C" ? "CALLS" : "PUTS";
    if (ntr[4]) s.limit = parseFloat(ntr[4]);
    s.action = "OPEN"; s.matched = "nitro entry"; s.fire = true;
    if (s.limit === null || isNaN(s.limit))
      s.warn = "no entry price posted — it pays the market.";
    s.why = "entry: " + human(s);
    return s;
  }

  // ---- stockguy007: "USO Calls Jul 18th exp 74" / "SPY Puts Aug 6th exp 630s"
  //      / "ROKU Calls May 15th 120s". Ticker, spelled-out side, month+day
  //      expiry, then the strike (often a trailing "s"). No premium.
  const sgm = /(?<![A-Za-z])\$?([A-Za-z]{1,5})\s+(calls?|puts?)\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th|dn)?\s+(?:exp\.?\s+)?\$?(\d{1,4})s?\b/i.exec(t);
  if (sgm && !NOT_TICKERS.has(sgm[1].toUpperCase())) {
    const MO = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7,
                 aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
    s.symbol = sgm[1].toUpperCase();
    s.side = sgm[2].toLowerCase().startsWith("call") ? "CALLS" : "PUTS";
    s.expiry = MO[sgm[3].toLowerCase()] + "/" + parseInt(sgm[4], 10);
    s.strike = parseFloat(sgm[5]);
    s.action = "OPEN"; s.matched = "stockguy entry"; s.fire = true;
    s.warn = "no premium posted — it pays the market.";
    s.why = "entry: " + human(s);
    return s;
  }

  // ---- Namrood-Trades: "Buy To Open MSFT 400C 1DTE $2.6" / "Lotto Trade —
  //      RISKY TSLA 402.5C 7/17/2026 $3.35". The label is the buy.
  if (/\bbuy\s+to\s+open\b|\blotto\s+trade\b/i.test(low)) {
    const c = findContract(t);
    if (c && !NOT_TICKERS.has(c.symbol)) {
      s.symbol = c.symbol; s.strike = c.strike; s.side = c.side; s.expiry = c.expiry;
      const mps = t.match(/\$\s*(\d+(?:\.\d{1,2})?)\b(?!\s*%)/g);
      if (mps) {
        const last = parseFloat(mps[mps.length - 1].replace(/[^\d.]/g, ""));
        if (last !== s.strike) s.limit = last;
      }
      s.action = "OPEN"; s.matched = "namrood entry"; s.fire = true;
      if (s.limit === null || isNaN(s.limit)) s.warn = "no entry price I could read — it pays the market.";
      s.why = "entry: " + human(s);
      return s;
    }
  }

  // ---- Adex Swing: "Entering $MA 535C 6/18 @4.5" / "Entering: $LOW 230C 8/21
  //      @3.30". The big "Options Analysis ·" table is not an entry.
  if (/\bentering\b/i.test(low) && !/\boptions?\s+analysis\b/i.test(low)) {
    const c = findContract(t);
    if (c && !NOT_TICKERS.has(c.symbol)) {
      s.symbol = c.symbol; s.strike = c.strike; s.side = c.side; s.expiry = c.expiry;
      const mp = /@\s*\$?(\d+(?:\.\d{1,2})?)\b(?!\s*%)/.exec(t);
      if (mp) s.limit = parseFloat(mp[1]);
      s.action = "OPEN"; s.matched = "adex entry"; s.fire = true;
      if (s.limit === null || isNaN(s.limit)) s.warn = "no entry price posted — it pays the market.";
      s.why = "entry: " + human(s);
      return s;
    }
  }

  // ---- King Maker Bot: "TWLO 11/21 $140 Calls @$1.49 SL: ...". A % gain or
  //      "trimming/booking/took" makes it an update, not an entry.
  const km = /^(?:@everyone\s+)?([A-Za-z]{1,5})\s+(\d{1,2}[/.]\d{1,2}(?:[/.]\d{2,4})?)\s+\$(\d{1,5}(?:\.\d{1,2})?)\s+(calls?|puts?)\s+@\s*\$?(\d+(?:\.\d{1,2})?)/i.exec(t);
  if (km && !NOT_TICKERS.has(km[1].toUpperCase()) && !RE_PCT_ANY.test(t)
      && !/\b(trimming|booking|took|book|profits?)\b/i.test(low)) {
    const p = km[2].match(/\d+/g);
    s.symbol = km[1].toUpperCase();
    s.expiry = parseInt(p[0], 10) + "/" + parseInt(p[1], 10);
    s.strike = parseFloat(km[3]);
    s.side = km[4].toLowerCase().startsWith("call") ? "CALLS" : "PUTS";
    s.limit = parseFloat(km[5]);
    s.action = "OPEN"; s.matched = "kingmaker entry"; s.fire = true;
    s.why = "entry: " + human(s);
    return s;
  }

  // ---- KuMo Bot: "Weekly CAVA 07/17/26 $100 Call @$1.50-$1.60 PT1:...".
  //      Single-leg only — a Debit/Credit Spread is two legs, skipped.
  const kumo = /\b(?:weekly|monthly)\s+([A-Za-z]{1,5})\s+(\d{1,2}\/\d{1,2}(?:\/\d{2,4})?)\s+\$(\d{1,5}(?:\.\d{1,2})?)\s+(calls?|puts?)\s+@\s*\$?(\d+(?:\.\d{1,2})?)/i.exec(t);
  if (kumo && !NOT_TICKERS.has(kumo[1].toUpperCase()) && !/\bspread\b/i.test(low) && !RE_PCT_ANY.test(t)) {
    const p = kumo[2].match(/\d+/g);
    s.symbol = kumo[1].toUpperCase();
    s.expiry = parseInt(p[0], 10) + "/" + parseInt(p[1], 10);
    s.strike = parseFloat(kumo[3]);
    s.side = kumo[4].toLowerCase().startsWith("call") ? "CALLS" : "PUTS";
    s.limit = parseFloat(kumo[5]);
    s.action = "OPEN"; s.matched = "kumo entry"; s.fire = true;
    s.why = "entry: " + human(s);
    return s;
  }

  // ---- Stormzy (futures): "TRADE ENTRY - MNQ Shorts - 1/4 Size Position
  //      Entry: 28163.75 Sl: 28194.50".
  const sz = /\btrade\s+entry\b[^\n]{0,40}?\b(MNQ|NQ|MES|ES|MYM|YM|M2K|RTY|MCL|CL|MGC|GC)\b[^\n]{0,20}?\b(short|long)s?\b[^\n]{0,40}?\bentry:?\s*\$?(\d[\d,]*(?:\.\d{1,2})?)/i.exec(t);
  if (sz) {
    const px = num(sz[3]);
    if (futPriceOk(sz[1].toUpperCase(), px)) {
      s.symbol = sz[1].toUpperCase(); s.kind = "future";
      s.direction = sz[2].toUpperCase(); s.limit = px;
      const ms = RE_THEIR_STOP.exec(t);
      if (ms) s.their_stop = num(ms[1]);
      s.action = "OPEN"; s.matched = "stormzy futures entry"; s.fire = true;
      s.why = "entry: " + s.direction + " " + s.symbol;
      return s;
    }
  }

  // ---- Vero: "QQQ 708C 7/21 1.03 2 CONTRACTS". The "N CONTRACTS/CONS" tail is
  //      the fingerprint.
  const vr = /^([A-Za-z]{1,5})\s+(\d{1,5})\s*([CcPp])\s+(\d{1,2}\/\d{1,2})\s+(\d+\.\d{1,2})\s+\d+\s*(?:contracts?|cons?)\b/i.exec(t);
  if (vr && !NOT_TICKERS.has(vr[1].toUpperCase())) {
    s.symbol = vr[1].toUpperCase();
    s.strike = parseFloat(vr[2]);
    s.side = vr[3].toUpperCase() === "C" ? "CALLS" : "PUTS";
    s.expiry = vr[4];
    s.limit = parseFloat(vr[5]);
    s.action = "OPEN"; s.matched = "vero entry"; s.fire = true;
    s.why = "entry: " + human(s);
    return s;
  }

  // ---- MR.TOPHAT lotto: "lotto yolo SPX 7460C 0dte @0.25". Anchored lead +
  //      @-price + real contract, refused if it carries a percentage (recap).
  if (/^(?:@\w+\s+)?(?:lotto|yolo)\b/i.test(low) && t.indexOf("@") !== -1
        && !RE_PCT_ANY.test(t)) {
    const c = findContract(t);
    if (c) {
      s.symbol = c.symbol; s.strike = c.strike; s.side = c.side; s.expiry = c.expiry;
      const mp = /@\s*\$?([0-9]*\.?[0-9]+)/.exec(t);
      s.limit = mp ? parseFloat(mp[1]) : null;
      s.action = "OPEN"; s.matched = "lotto entry"; s.fire = true;
      s.why = "entry: " + human(s);
      return s;
    }
  }

  // ---- labeled alert-bot format (Sir Goldman [BOKA]): ENTRY / TRIM /
  //      EXIT / COMMENT keyword is the truth; COMMENT never trades.
  const ml = /^(?:@\w+\s+)?(ENTRY|TRIM|EXIT|COMMENT)\b\s*([\s\S]*)$/i.exec(t);
  if (ml) {
    const label = ml[1].toUpperCase();
    const rest = (ml[2] || "").trim();
    if (label === "COMMENT") {
      s.why = "a COMMENT from the alert bot — never an order";
      return s;
    }
    if (label === "ENTRY") {
      const md = /\b(long|short)s?\b[^\n.]{0,20}?\b([A-Za-z]{2,4})\b/i.exec(rest);
      if (md && FUT_SYMS.has(md[2].toUpperCase())) {
        s.symbol = md[2].toUpperCase(); s.kind = "future";
        s.direction = md[1].toUpperCase();
        const mp = RE_LIMIT.exec(rest);
        s.limit = mp ? parseFloat(mp[1]) : null;
        s.action = "OPEN"; s.matched = "alert-bot futures entry"; s.fire = true;
        if (s.limit === null) s.warn = "no price on the entry — it pays the market.";
        s.why = "entry: " + s.direction + " " + s.symbol;
        return s;
      }
      const cL = findContract(rest);
      if (cL) {
        s.symbol = cL.symbol; s.strike = cL.strike; s.side = cL.side;
        s.expiry = cL.expiry;
        const mp = RE_LIMIT.exec(rest);
        s.limit = mp ? parseFloat(mp[1]) : null;
        s.action = "OPEN"; s.matched = "alert-bot entry"; s.fire = true;
        s.why = "entry: " + human(s);
        return s;
      }
      s.why = "an ENTRY label with no contract I could read";
      return s;
    }
    s.symbol = bareSymbol(rest, allowed);
    s.action = label === "TRIM" ? "TRIM" : "CLOSE";
    s.matched = "alert-bot " + label.toLowerCase();
    const mp = /\b(\d{1,3}(?:\.\d{1,2})?)\s*[!]/.exec(rest);
    if (mp) s.limit = parseFloat(mp[1]);
    const mpc = RE_PCT_ANY.exec(rest);
    if (mpc) s.pct = parseFloat(mpc[1]);
    if (!s.symbol) {
      s.needs_position = true;
      s.why = "their " + label.toLowerCase() + " with no ticker — working " +
              "out which position they meant";
      return s;
    }
    s.fire = s.action === "CLOSE";
    s.why = (s.action === "CLOSE" ? "full exit on " : "trim on ") + s.symbol;
    return s;
  }

  if (t.includes("?")) { s.why = "it's a question, not a call"; return s; }

  // An explicit buy-to-open with a real contract is an ORDER, not chatter — a
  // stray soft word in a risk note ("BTO $MSFT 400c @0.43 cheapie, watch
  // sizing") must not be vetoed by "watch". Hard "don't/do not" still fire, and
  // the sell-guard downstream still catches a genuine SELL. Mirrors signals.py.
  const _explicitBuy = /\b(?:bto|bought)\b/i.test(low) && !!findContract(t);
  const veto = VETO_WORDS.concat(cfg.extra_veto_words || []);
  for (const w of veto) {
    if (low.includes(String(w).toLowerCase()) && !RE_PAPERCUT.test(low)) {
      const wl = String(w).toLowerCase();
      if (_explicitBuy && wl !== "do not" && wl !== "don't" && wl !== "dont ") continue;
      s.why = 'chatter, not an order (it contains "' + String(w).trim() + '")';
      return s;
    }
  }

  // 0. The recap line. "Way to close the day: AAPL 25% / SPY 63% / JNJ -33%"
  //    — three or more percentages in one message is a scoreboard, not a
  //    call, and reading it as a trim would sell on a summary.
  if ((t.match(/-?\d{1,3}(?:\.\d+)?\s*%/g) || []).length >= 3) {
    s.why = "three or more percentages in one line — that's a recap, not a call";
    return s;
  }

  // "Or from 15% profit" — Midas describing the level he'd trim FROM. The
  // "from" in front of the percentage is the tell: it's a condition for
  // later, not something he just did. Read as a trim it would have sold.
  if (/\bfrom\s+\d{1,3}(?:\.\d+)?\s*%/.test(low)) {
    s.why = "a percentage with \"from\" in front of it is a level they're " +
            "planning around, not a sale";
    return s;
  }

  // "I'm about 80% sure market falls" — a percentage about his CONFIDENCE,
  // not his position. Day two it fired TRIM (+80%).
  if (/\d{1,3}(?:\.\d+)?\s*%\s*sure\b/.test(low)) {
    s.why = "that percentage is how sure they are, not a sale";
    return s;
  }

  // The Whop room narrates its RESTING orders: "Sell order at 29630", "Buy
  // order sitting at 28934", "First trim order at 28550", "First trim at
  // 29563". Orders they PLACED, not fills — acting on one sells at a level
  // the market hasn't reached. ("First trim 37%" has no "at <level>", so a
  // real first trim still reads as a trim.)
  if (/\b(?:buy|sell|trim)\s+order\b|\border\s+(?:at|sitting|set)\b|\bfirst\s+(?:trim|sell)\s+(?:order\s+)?(?:set\s+)?at\s+\$?\d+(?!\s*%)/.test(low)) {
    s.why = "that's a resting order they've placed, not a fill — nothing has happened yet";
    return s;
  }

  // ---- z trades' posted format (their own server-map rules) ---------------
  //   GREEN circle = BOUGHT   RED = SOLD   WHITE = update   scissors = trim
  //   "ON THE BREAK OF $451.50" = conditional; his "in @ 1.06" is the fill.
  //   Circles live in the RAW text — the cleaner strips emoji.
  const zg = raw.includes("\u{1F7E2}");
  const zr = raw.includes("\u{1F534}");
  const zw = raw.includes("\u26AA");
  const zs = raw.includes("\u2702");
  if (zw && !zg && !zr) {
    s.why = "their price update (white circle) — not an order";
    return s;
  }
  if (zg || zr || (zs && !RE_TRIM.test(low))) {
    // "GOOGL - $172.5 C" — the dash hides the contract; drop it.
    const tZ = t.replace(/\s-\s/g, " ");
    const cZ = findContract(tZ);
    let pxZ = null;
    const reDec = /\b(\d{1,4}\.\d{1,4})\b/g;
    let md0;
    while ((md0 = reDec.exec(tZ)) !== null) {
      const v = parseFloat(md0[1]);
      if (cZ && Math.abs(v - cZ.strike) < 0.001) continue;
      pxZ = v;
      break;
    }
    if (zg) {
      const brk = /on\s+the\s+break\s+of\s+\$?(\d[\d.,]*)/.exec(low);
      if (cZ && brk) {
        s.symbol = cZ.symbol; s.strike = cZ.strike; s.side = cZ.side;
        s.expiry = cZ.expiry;
        s.action = "PREPARE"; s.matched = "z-format conditional";
        s.why = "they'll buy when " + s.symbol + " breaks " + brk[1] +
                " — waiting for their fill, exactly like a LOADING";
        return s;
      }
      if (cZ) {
        s.symbol = cZ.symbol; s.strike = cZ.strike; s.side = cZ.side;
        s.expiry = cZ.expiry;
        s.action = "OPEN"; s.matched = "z-format entry";
        const mL = RE_LIMIT.exec(t);
        s.limit = mL ? parseFloat(mL[1]) : pxZ;
        if (s.limit === null) s.warn = "no price on the green circle — it pays the market.";
        s.fire = true;
        s.why = "entry: " + human(s);
        return s;
      }
      if (pxZ !== null) {
        s.action = "OPEN"; s.matched = "z-format fill";
        s.needs_loaded = true;
        s.limit = pxZ;
        s.symbol = bareSymbol(t, allowed);
        s.why = "their fill on the break-of call — looking for the conditional it belongs to";
        return s;
      }
      s.why = "a green circle with no contract and no price — nothing to follow";
      return s;
    }
    s.symbol = bareSymbol(t, allowed);
    const partial = zs || /\bout\s+half\b|\bout\s+\d\/\d\b|\ball\s+but\b|\bone\s+left\b|\btrim/.test(low);
    s.action = partial ? "TRIM" : "CLOSE";
    s.matched = "z-format exit";
    if (pxZ !== null) s.limit = pxZ;
    if (!s.symbol) {
      s.needs_position = true;
      s.why = "they sold (" + (zr ? "red" : "scissors") + " circle) with no " +
              "ticker — working out which position they meant";
      return s;
    }
    s.fire = s.action === "CLOSE";
    s.why = (s.action === "CLOSE" ? "full exit on " : "their trim on ") +
            s.symbol + (pxZ === null ? "" : " at " + pxZ);
    return s;
  }

  // 1. LOADING — get ready. Never buys; that is the room's own instruction.
  // A4 - exit/trim/all-out wins over LOADING. "all out of AMD ... keep same
  //      cons loaded" must close, not read as a no-op PREPARE on the word
  //      "loaded". Fall through so the exit branches below catch it.
  if (RE_LOADING.test(low) && !RE_ALLOUT.test(low) && !RE_CLOSE_ALL.test(low)
      && !RE_TRIM.test(low) && !RE_STOPPED_OUT.test(low) && !RE_EXIT.test(low)) {
    const c = findContract(t);
    s.action = "PREPARE"; s.matched = "loading";
    if (c) { s.symbol = c.symbol; s.strike = c.strike; s.side = c.side; s.expiry = c.expiry; }
    s.why = "they're getting ready on " + (s.symbol || "something") +
            " — LOADING never buys, that's the room's own rule";
    return s;
  }

  // 1b. "All positions closed" / "Out of all trades" — everything this
  //     trader holds goes. No ticker to resolve: the worker walks their
  //     whole book and closes each one.
  if (RE_CLOSE_ALL.test(low)) {
    s.action = "CLOSE"; s.all = true; s.matched = "close everything";
    s.why = "they closed everything — selling every trade of theirs still open";
    return s;
  }

  // 2. ALL OUT — checked before trim, because "all out" wins.
  if (RE_ALLOUT.test(low)) {
    const c = findContract(t);
    s.symbol = c ? c.symbol : bareSymbol(t, allowed);
    if (c) { s.strike = c.strike; s.side = c.side; s.expiry = c.expiry; }
    s.action = "CLOSE"; s.matched = "all out";
    if (s.symbol && FUT_SYMS.has(s.symbol)) s.kind = "future";
    const mu0 = RE_USD_CONTRACT.exec(t);
    if (mu0) s.usd = num(mu0[1]);
    const m = RE_PCT.exec(t);
    if (m) s.pct = parseFloat(m[1]);
    if (!s.symbol) { s.why = "they called an exit but I couldn't tell which ticker"; return s; }
    s.fire = true;
    s.why = "full exit on " + s.symbol;
    return s;
  }

  // 2b. "Out" / "Fully out" — Aristotle's exit is two words with no ticker.
  //     Resolved by whose position it is, exactly like a bare trim. The
  //     anchored regex is what keeps "Damn it actually worked out" from
  //     reading as an exit — a bare out IS the whole message, or it's chatter.
  if (RE_STOPPED_OUT.test(low) || RE_STOP_HIT.test(t) || RE_PAPERCUT.test(low)) {
    if (RE_NOT_ROOM_TRADE.test(low)) {
      // "stopped out of my personal trade, room trade still on" — his OTHER
      // account. The room's position is explicitly alive; closing it here
      // is the exact wrong read. Mirrors signals.py.
      s.why = "their stop fired on a personal trade, not the room's — the " +
              "room trade is still on";
      return s;
    }
    s.symbol = bareSymbol(t, allowed);
    s.action = RE_PARTIAL.test(low) ? "TRIM" : "CLOSE";
    s.matched = "stopped out";
    if (!s.symbol) {
      s.needs_position = true;
      s.why = "their stop fired — working out which position they meant";
      return s;
    }
    s.fire = s.action === "CLOSE";
    s.why = (s.action === "CLOSE" ? "stopped out of " : "partial stop on ") +
            s.symbol;
    return s;
  }

  if (RE_BARE_OUT.test(t)) {
    s.action = RE_HALF.test(t) ? "TRIM" : "CLOSE";
    s.needs_position = true;
    s.matched = "bare exit";
    s.why = "an exit with no ticker in it — working out which position they meant";
    return s;
  }

  // 3. EXITED ... AND BACK IN — one line, two trades. They sold and immediately
  //    re-bought THE SAME contract at a new price. The line doesn't name the
  //    contract because everyone in the room already knows which one, so the
  //    re-entry is filled in from the position you're holding.
  if (RE_BACKIN.test(low) && RE_EXIT.test(low)) {
    const c = findContract(t);
    s.symbol = c ? c.symbol : bareSymbol(t, allowed);
    if (c) { s.strike = c.strike; s.side = c.side; s.expiry = c.expiry; }
    s.action = "CLOSE"; s.matched = "exit and re-entry";
    const m = RE_LIMIT.exec(t);
    if (m) s.limit = parseFloat(m[1]);
    if (!s.symbol) { s.why = "they exited and re-entered but I couldn't tell which ticker"; return s; }
    s.fire = true;
    s.reenter = true;
    s.reenter_limit = s.limit;
    s.warn = "two orders off one line: it sells, then buys the same contract " +
             "straight back.";
    s.why = "out and back into " + s.symbol +
            (s.limit === null ? "" : " @ " + s.limit.toFixed(2)) +
            " — same contract, sold and re-bought";
    return s;
  }

  // 2c. Midas's fill confirmations — "Filled @here", "1.97 fill",
  //     "Avg 1.61", "Taking more cons at 748.50". He is IN (or adding);
  //     fires on his last Loaded, and a second one on the same PREP goes
  //     down the averaging path like any other add.
  // A3 - "SAME ONES" / "same cons": re-enter the caller's last posted
  //      contract. If the contract is on the line ("AMD | SAME ONES 500 C
  //      13.25-13.40") parse it and mark a re-entry - the spelled-out
  //      strike/side stops "ONES" being read as the ticker. Full state (prior
  //      expiry / anti-double-up) is the guards' call; never a silent drop -
  //      it logs a decision and holds for resolution rather than blindly buying.
  if (/\bsame\s+(?:ones?|cons?|contracts?)\b/i.test(low)) {
    const tS = t.replace(/\bsame\s+(?:ones?|cons?|contracts?)\b/gi, " ")
                 .replace(/\|/g, " ").replace(/\s+/g, " ").trim();
    const lpS = loosePremium(tS, null);
    // Strip price decimals/ranges before reading the contract so a range like
    // "13.25-13.40" can't be misread as an expiry (25/13).
    const tC = tS.replace(/\d{1,3}\.\d{1,2}\s*[-–]\s*\d{1,3}\.\d{1,2}/g, " ")
                 .replace(/\b\d{1,3}\.\d{1,2}\b/g, " ").replace(/\s+/g, " ").trim();
    const cS = findContract(tC);
    s.reenter = true; s.matched = "same-ones re-entry"; s.needs_position = true;
    if (cS) {
      s.symbol = cS.symbol; s.strike = cS.strike; s.side = cS.side; s.expiry = cS.expiry;
      s.action = "OPEN";
      if (lpS !== null) { s.limit = lpS; s.reenter_limit = lpS; }
      s.why = "re-entry of " + human(s) + " - same contract they just called; " +
              "holding to confirm against your open position before it fires";
    } else {
      s.why = 'a "same ones" re-entry with no contract on the line - ' +
              "resolving it from their last call";
    }
    return s;
  }

  const mfc = RE_FILL_CONF.exec(t);
  if (mfc) {
    s.action = "OPEN"; s.matched = "fill confirmation on a loaded contract";
    s.needs_loaded = true;
    const p0 = mfc[1] || mfc[2];
    if (p0) s.limit = parseFloat(p0);
    else {
      const mp0 = RE_IN_PRICE.exec(t);
      if (mp0) s.limit = parseFloat(mp0[1]);
    }
    s.why = "their fill confirmation — looking for the PREP it belongs to";
    return s;
  }

  // 3a-equity. "Entered BULL equity @ 7.24" / "Grabbed NFLX equity @ 74.8"
  // / "Snagging starters on PYPL equity @ 41.03 AVG" — plain shares, Swing
  // Trades and Long Term style. The word "equity" next to the ticker IS the
  // instrument; price from @ or their average.
  const meq = /(?<![A-Za-z])\$?([A-Za-z]{1,5})\s+(?:equity|shares|stock)\b/i.exec(t);
  if (meq && !NOT_TICKERS.has(meq[1].toUpperCase())) {
    if (/\b(?:entered|entering|grabbed|grabbing|snagg?(?:ed|ing)|bought|buying|added|adding|in)\b/i.test(low)) {
      s.symbol = meq[1].toUpperCase();
      s.kind = "equity";
      s.action = "OPEN"; s.matched = "equity entry";
      const mL = RE_LIMIT.exec(t);
      const maE = RE_FUT_AVG.exec(t);
      if (mL) s.limit = parseFloat(mL[1]);
      else if (maE) s.limit = num(maE[1] || maE[2]);
      const msE = RE_THEIR_STOP.exec(t);
      if (msE) s.their_stop = num(msE[1]);
      const mtE = RE_THEIR_TARGET.exec(t);
      if (mtE) s.their_target = num(mtE[1]);
      if (s.limit === null) {
        s.why = "an equity entry with no price anywhere — nothing to follow";
        return s;
      }
      s.fire = true;
      s.why = "equity entry: some shares of " + s.symbol + " @ " + s.limit;
      return s;
    }
  }

  // 3a2. "1.26 new avg" on its own — that's their bookkeeping after an add
  //      that was already signalled, not a second add. Reading it as one
  //      would buy five more contracts per arithmetic update.
  if (/^\$?\d+(?:\.\d+)?\s*(?:is\s+)?(?:my\s+)?new\s+avg\.?$/i.test(t)) {
    s.matched = "their new average";
    s.why = "their running average after an add they already called — nothing to do";
    return s;
  }

  // 3b. ADDED TO — they doubled up and posted their new average.
  //     A second buy on a trade you're already in. The parser stops short of
  //     firing it, because the three things that decide it are all state: is
  //     averaging switched on, are you actually in that position, and how many
  //     times have you added already. resolveAdd in guards.js.
  if (RE_ADD.test(low)) {
    const c = findContract(t);
    s.symbol = c ? c.symbol : bareSymbol(t, allowed);
    if (c) { s.strike = c.strike; s.side = c.side; s.expiry = c.expiry; }
    const p = addPremium(t);
    if (p !== null) s.limit = p;
    const mq = RE_QTY.exec(t);
    if (mq) s.qty = parseInt(mq[1], 10);
    // JonnyOptions [BOKA]: "adding $WULF 17c 4/17" = OPEN, not average up.
    // A per-channel flag; a bare "adding more" (no contract) still averages.
    if (cfg && cfg.adding_is_entry && c) {
      s.action = "OPEN"; s.matched = "entry (their \"adding\" = enter)";
      s.fire = true;
      s.why = "entry: " + human(s);
      return s;
    }
    s.action = "ADD"; s.matched = "added to their position";
    s.needs_add = true;
    s.why = "they added to their " + (s.symbol || "position") + " and their " +
            "average moved — checking whether you can follow them in";
    return s;
  }

  // 3c. FUTURES — "Short NQ @ 28660  Stop 29700  Target 28550".
  //     No strike, no expiry: the symbol, the direction and the price are the
  //     whole contract. His stop and target ride along as THEIR levels — the
  //     plan of record is to run his numbers, not the flat 20%, when this
  //     grammar goes live. Which side of the switch that happens on is not
  //     the parser's decision; it reads, the guards and the bridge decide.
  const mf = RE_FUT_ENTRY.exec(t);
  let futDir = null, futSym = null, futPx = null, futEnd = 0;
  const mfRoot = mf ? futRoot(mf[2]) : null;
  if (mfRoot) {
    const px0 = num(mf[3]);
    if (!futPriceOk(mfRoot, px0)) {
      // "Long NQ @ 0", "Long NQ @ 286600000", or a count the unit-word
      // lookahead didn't know. Refused loudly, never guessed — a short at
      // a nonsense-low price is a marketable order. Mirrors signals.py.
      s.why = "looks like a futures entry but " + px0 + " isn't a plausible " +
              mfRoot + " price — refused, not guessed";
      return s;
    }
    futDir = mf[1].toUpperCase(); futSym = mfRoot;
    futPx = px0; futEnd = (mf.index || 0) + mf[0].length;
  } else {
    // "Long NQ - AVG 24015" / "Entered NQ short 23477 average" — no inline
    // price, direction and symbol either way round, the price arriving as
    // an average. Requires the average or his stop plus an entry verb, so
    // "comfortable being long NQ" chatter stays chatter.
    // TWO safety guards, from the High Risk channel's own lines. His trim
    // updates read "...$1,000 a contract on NQ short - Trimmed / Stop now
    // 28130 ... post in gains" — a direction, a symbol, a stop with digits
    // and even the word "in". Without these it would have BOUGHT. 1) any
    // trim word kills the entry read; 2) an entry leads with its call, so
    // the direction+symbol must sit in the first 40 characters.
    let md = null;
    if (!RE_TRIM.test(low)) {
      RE_FUT_DIR_SYM.lastIndex = 0;
      let cand;
      while ((cand = RE_FUT_DIR_SYM.exec(t)) !== null) {
        if (cand.index > 40) break;
        const cS = (cand[2] || cand[4] || cand[5] || "").toUpperCase();
        if (FUT_SYMS.has(cS)) { md = cand; break; }
      }
    }
    if (md) {
      const d0 = (md[1] || md[3] || md[6] || "").toUpperCase();
      const s0 = (md[2] || md[4] || md[5] || "").toUpperCase();
      if (d0 && FUT_SYMS.has(s0)) {
        const maF = RE_FUT_AVG.exec(t);
        const mlF = RE_LIMIT.exec(t);
        if (maF || mlF) {
          const px1 = maF ? num(maF[1] || maF[2]) : parseFloat(mlF[1]);
          if (!futPriceOk(s0, px1)) {
            s.why = "looks like a futures entry but " + px1 + " isn't a " +
                    "plausible " + s0 + " price — refused, not guessed";
            return s;
          }
          futDir = d0; futSym = s0;
          futPx = px1;
          futEnd = (md.index || 0) + md[0].length;
        } else if (RE_THEIR_STOP.test(t) && RE_ENTRY.test(low)) {
          futDir = d0; futSym = s0; futEnd = (md.index || 0) + md[0].length;
        }
      }
    }
  }
  if (futSym) {
    s.symbol = futSym;
    s.kind = "future";
    s.direction = futDir;
    s.limit = futPx;
    s.action = "OPEN"; s.matched = "futures entry";
    const rest = t.slice(futEnd);
    const ms = RE_THEIR_STOP.exec(rest);
    if (ms) s.their_stop = num(ms[1]);
    const mt = RE_THEIR_TARGET.exec(rest);
    if (mt) s.their_target = num(mt[1]);
    s.fire = true;
    if (s.limit === null) {
      s.warn = "they posted no price on this one — it pays the market.";
    }
    s.why = "futures entry: " + s.direction + " " + s.symbol + " @ " +
            (s.limit === null ? "market" : s.limit) +
            (s.their_stop !== null ? ", their stop " + s.their_stop : "") +
            (s.their_target !== null ? ", their target " + s.their_target : "");
    return s;
  }

  // 4. TRIMMING — a partial.
  //
  //    Two grammars. One room writes the word: "trimming SPY @ 38%". The other
  //    just posts the number: "20%", "50% @here", "40% in spy now". A bare
  //    percentage with no contract in the line is a trim — nobody opens a
  //    position by posting "34%". The no-contract test is what stops a real
  //    entry from being swallowed here.
  // "closed AAPL for +20%" / "sold NVDA at +35%" is a FULL exit reporting its
  // gain — not a 20% trim (9/2 corpus). A trim word anywhere keeps it a trim.
  {
    const fx = /\b(closed|sold|out of|exited|stopped out of)\s+(?:my\s+)?\$?([A-Za-z]{1,5})\b[^%\n]{0,30}?\b(?:for|at|up)\s+[+-]?\d{1,4}(?:\.\d+)?\s*%/i.exec(t)
      || /\b\$?([A-Za-z]{1,5})\s+(out|closed|sold|exited)\s*(?:@|at|for|up)\s*[+-]?\d{1,4}(?:\.\d+)?\s*%/i.exec(t) && (() => {
           const m = /\b\$?([A-Za-z]{1,5})\s+(out|closed|sold|exited)\s*(?:@|at|for|up)\s*[+-]?\d{1,4}(?:\.\d+)?\s*%/i.exec(t);
           return [m[0], m[2], m[1]]; })();
    if (fx && !RE_TRIM.test(low) && !RE_PARTIAL.test(low) && !NOT_TICKERS.has(fx[2].toUpperCase())) {
      const c = findContract(t);
      s.symbol = c ? c.symbol : fx[2].toUpperCase();
      if (c) { s.strike = c.strike; s.side = c.side; s.expiry = c.expiry; }
      s.action = "CLOSE"; s.matched = "exit with gain"; s.fire = true;
      s.why = "full exit on " + s.symbol + " (they posted the gain, not a trim size)";
      return s;
    }
  }
  const pctM = RE_PCT.exec(t) || RE_PCT_ANY.exec(t);
  // ...unless the line also NAMES A CONTRACT — then it's an entry that
  // happens to state its risk (Blue Collar's template, 9/2), not a risk note.
  const _hasContract = new RegExp(RE_CONTRACT.source, "i").test(t) || RE_CONTRACT_OSI.test(t);
  if (pctM && !RE_TRIM.test(low) && RE_PCT_RISK.test(t) && !_hasContract) {
    s.why = "that percentage is their risk, not a gain — nothing to act on";
    return s;
  }
  // "Full sold nvda close to 25%" — the word FULL turns a percentage line
  // into a complete exit. Without this, the trim rule below would swallow it
  // and sell 3 of 5 on a call that means "I'm out".
  // "Full sold $3400 a contract" / "Full sold nq 500 points" — the Whop
  // room's full exits often carry dollars or points instead of a percent.
  // FULL + an exit verb is the call; the numbers just say how it went.
  if (/\bfull(?:y)?\b/i.test(low) && RE_EXIT.test(low) && !findContract(t)) {
    s.symbol = bareSymbol(t, allowed);
    s.action = "CLOSE"; s.matched = "full exit";
    if (pctM) s.pct = parseFloat(pctM[1]);
    const muF = RE_USD_CONTRACT.exec(t);
    if (muF) s.usd = num(muF[1]);
    if (!s.symbol) {
      s.needs_position = true;
      s.why = "a full exit with no ticker in it — working out which position they meant";
      return s;
    }
    s.fire = true;
    s.why = "full exit on " + s.symbol;
    return s;
  }
  const barePctOk = cfg && cfg.bare_pct_trims === false ? false : true;
  // A BARE percentage with no "trim" verb and no ticker is only a trim when the
  // line is terse — "37%", "50% here". A recap like "3 10-12% trades today lol,
  // green is green" carries a percentage but is an end-of-day summary; acting on
  // it would trim a live position on a reflection. A percentage RANGE ("10-12%")
  // or a long sentence is the tell. A percentage WITH a ticker stays a real trim.
  let barePct = !!pctM && !findContract(t) && barePctOk;
  if (barePct && !RE_TRIM.test(low) && !bareSymbol(t, allowed)) {
    const isRange = /\d{1,3}\s*[-–]\s*\d{1,3}\s*%/.test(t);
    if (isRange || t.split(/\s+/).length > 6) barePct = false;
  }
  if (RE_TRIM.test(low) || barePct) {
    s.symbol = bareSymbol(t, allowed);
    s.action = "TRIM"; s.matched = "trim";
    if (pctM) s.pct = parseFloat(pctM[1]);
    // Futures trims speak in dollars, not percent: "$1,100 a contract on NQ
    // short - Trimmed". The dollars are the exit price a dry run settles at.
    if (s.symbol && FUT_SYMS.has(s.symbol)) s.kind = "future";
    const mu = RE_USD_CONTRACT.exec(t);
    if (mu) s.usd = num(mu[1]);

    // There used to be a trim_action setting here (ignore / close / close
    // above a %). Deleted on his word — "no filters wanted. id like to
    // follow everything to the tee as they do." A trim is a trim: the
    // follow-them logic downstream sells its share and keeps the rest.
    if (!s.symbol) {
      // Held back rather than dropped. resolveSymbol in guards.js works out
      // which position they meant from what you're holding and who said it;
      // if it can't, nothing is sent.
      s.needs_position = true;
      s.why = "a trim with no ticker in it — working out which position they meant";
      return s;
    }
    // "Out of JNJ -33%" — OUT OF a named ticker is a full exit that happens
    // to carry a percentage, not a partial. "out of half" stays a trim.
    if (/^(?:i'?m\s+)?(?:fully\s+)?out\s+of\b/i.test(t) && !RE_HALF.test(t)) {
      s.action = "CLOSE"; s.fire = true;
      s.why = "full exit on " + s.symbol +
              (s.pct === null ? "" : " at " + s.pct + "%");
      return s;
    }
    s.why = "trim on " + s.symbol +
            (s.pct === null ? "" : " at " + s.pct + "%") +
            " — following their trim";
    return s;
  }

  // 5. IN — the entry. Needs a full contract; a bare "in" is not an order.
  // But a strong exit word (out/closed/sold) with only a weak bare "in" is an
  // EXIT with commentary, not a buy: "QQQ OUT 2.10 In one runner on MNQ futures"
  // is Vero closing QQQ; the stray "In" used to hijack it and drop the exit.
  const _strongEntry = /\b(?:entered|entering|filled|bto|bought|buying|grabbed)\b/i.test(low);
  const _exitWithWeakIn = RE_EXIT.test(low) && !_strongEntry;
  // A1 - "taking" is an entry verb ("Also taking $AAPL 315c ... 3.20") but not
  //      "taking profits/off" (a trim, handled above); a quantity-first line
  //      has no verb at all - the leading count is the cue.
  const _takingEntry = /\btaking\b/i.test(low)
      && !/\btaking\s+(?:profits?|gains?|some|off|half|the\s+l)\b/i.test(low)
      && !!findContract(t);
  if ((RE_ENTRY.test(low) || _takingEntry || RE_QTY_LEAD.test(t)) && !_exitWithWeakIn) {
    const c = findContract(t);
    if (!c) {
      // The two-message entry: "Loading 205 calls Friday expiration on NVDA",
      // then a minute later "Filled 3.95 starters". This second line really is
      // the order — the contract is just in the message before it. Held back
      // rather than dropped, the same way a bare trim is.
      const mf = RE_BARE_FILL.exec(t);
      if (mf && !bareSymbol(t, allowed)) {
        s.action = "OPEN"; s.matched = "fill on a loaded contract";
        s.needs_loaded = true;
        s.limit = parseFloat(mf[1]);
        const mq0 = RE_QTY.exec(t);
        if (mq0) s.qty = parseInt(mq0[1], 10);
        s.why = "a fill price with no contract in it — looking for the LOADING call it belongs to";
        return s;
      }
      // Aristotle's trigger: "In @here starters" — the whole message. His
      // fill already happened; the contract was in his PREP a minute ago,
      // and the price (if any) trails on the end ("I'm in @1.31"). Fires on
      // the last thing this admin loaded, at the market when no price came.
      const mi = RE_BARE_IN.exec(t);
      if (mi) {
        s.action = "OPEN"; s.matched = "bare in on a loaded contract";
        s.needs_loaded = true;
        s.limit = mi[1] ? parseFloat(mi[1]) : null;
        s.why = "a bare \"in\" — looking for the PREP it belongs to";
        return s;
      }
      // Midas's shape: "In @here my add level will be 744.30" / "In 0days at
      // 1.97". Starts with IN, not prose, and carries a trading cue. The
      // price is only believed when it's premium-sized — 744.30 is a level
      // on the chart, not a thing you pay for a contract.
      if (RE_LOOSE_IN.test(t) && RE_IN_CUE.test(t)) {
        s.action = "OPEN"; s.matched = "loose in on a loaded contract";
        s.needs_loaded = true;
        // If they named a ticker ("In meta 6.10 avg"), pin it so resolveLoaded
        // won't pair it with a different ticker's load.
        s.named_symbol = bareSymbol(t, allowed);
        const mp = RE_IN_PRICE.exec(t);
        let lim = mp ? parseFloat(mp[1]) : null;
        if (lim === null) {
          const md0 = /\b(\d{1,2}\.\d{1,2})\b/.exec(t);
          if (md0 && parseFloat(md0[1]) < 100) lim = parseFloat(md0[1]);
        }
        s.limit = lim;
        s.why = "an \"in\" with detail around it — looking for the PREP it belongs to";
        return s;
      }
      // "$NVDA I took entry 1.37 fill" — RWGates' shape (9/3): the contract
      // was named in an earlier LOADING call, this message only confirms the
      // fill. "took entry" already reads as an entry verb above, but nothing
      // caught it here because it doesn't start the message and isn't in
      // RE_BARE_FILL's fill-verb list — it fell through to "no contract" and
      // was silently dropped (RWGates NVDA 230C 9/4 @1.37, 9/3, never sent).
      const mte = RE_TOOK_ENTRY_FILL.exec(t);
      if (mte) {
        s.action = "OPEN"; s.matched = "took-entry fill on a loaded contract";
        s.needs_loaded = true;
        s.limit = parseFloat(mte[1]);
        // If they named a ticker ("$NVDA I took entry..."), pin it so
        // resolveLoaded won't pair it with a different ticker's load.
        s.named_symbol = bareSymbol(t, allowed);
        s.why = "a fill confirmation (\"took entry ... fill\") with no contract " +
                "in it — looking for the LOADING call it belongs to";
        return s;
      }
      s.why = "sounds like an entry but there's no full contract in it";
      return s;
    }
    s.symbol = c.symbol; s.strike = c.strike; s.side = c.side; s.expiry = c.expiry;
    s.action = "OPEN"; s.matched = "entry";
    const m = RE_LIMIT.exec(t);
    if (m) s.limit = parseFloat(m[1]);
    else {
      // The Whop room posts the fill on the next line of the SAME message:
      // "Entered nvda July 20th 205c / Avg 2.25". Their average is the
      // price they paid — that's the limit.
      const ma = RE_AVG_PRICE.exec(t);
      if (ma) s.limit = parseFloat(ma[1]);
    }
    // A1 - price written anywhere, not just after "@".
    if (s.limit === null) {
      const lp = loosePremium(t, s.strike);
      if (lp !== null) s.limit = lp;
    }
    const mq = RE_QTY.exec(t) || RE_QTY_PAREN.exec(t);
    if (mq) s.qty = parseInt(mq[1], 10);
    // "Entered AMD 520C 7/20 @ 1.75  Target 524  Stop 505" — HIS levels, on
    // the underlying. Written down for the day his numbers replace the flat
    // 20% rule; nothing acts on them yet.
    const msO = RE_THEIR_STOP.exec(t);
    if (msO && num(msO[1]) !== s.strike) s.their_stop = num(msO[1]);
    const mtO = RE_THEIR_TARGET.exec(t);
    if (mtO && num(mtO[1]) !== s.strike) s.their_target = num(mtO[1]);
    // (The allowed-symbols refusal that used to sit here is gone — every
    // ticker trades. "no filters wanted.")
    if (s.limit === null) {
      // No price in the message. Worth saying out loud rather than
      // discovering on the fill.
      s.warn = "they didn't post a fill price on this one — nothing to " +
               "compare your fill against.";
    }
    s.fire = true;
    s.why = "entry: " + human(s);
    return s;
  }

  // 5b. "QQQ 668 0 day puts @here lightly" — a whole entry in five words,
  //     no verb, no price. Only counts when stripping the contract and the
  //     sizing filler leaves NOTHING — "NVDA 205C looks juicy" leaves "looks
  //     juicy" and stays chatter.
  {
    const c5 = findContract(t);
    if (c5) {
      const leftover = t
        .replace(/(?<![A-Za-z])\$?[A-Za-z]{1,5}\s+\$?\d{1,5}(?:\.\d{1,2})?\s*(?:\d{1,2}\s*days?\s*)?(?:calls?|puts?|c|p)\b/i, " ")
        .replace(/\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b|\b\d*dte\b|\b\d{1,2}\s*days?\b/gi, " ")
        .replace(RE_FILLER, " ")
        .replace(/\s+/g, " ").trim();
      const lonePrice = /^\$?(\d{1,2}(?:\.\d{1,2})?)$/.exec(leftover);
      if (!leftover || (lonePrice && parseFloat(lonePrice[1]) < 100)) {
        s.symbol = c5.symbol; s.strike = c5.strike; s.side = c5.side;
        s.expiry = c5.expiry;
        s.action = "OPEN"; s.matched = "bare contract entry";
        s.fire = true;
        if (lonePrice) s.limit = parseFloat(lonePrice[1]);
        else s.warn = "no price posted — it pays the market.";
        s.why = "entry: " + human(s) + " — the contract IS the whole message";
        return s;
      }
    }
  }

  // 6. A plain exit word with something identifiable behind it.
  //    PARTIAL SELLS ARE TRIMS (9/2 corpus): "sold 1/2 UPS here", "sell 2/3
  //    UPS 105 calls", "sold some", "sold most", "sold a third" read as a
  //    FULL exit — the bot would have flattened a position the trader only
  //    trimmed. A fraction/partial word next to the sell word is a trim.
  const partSell = /\b(?:sold|sell|selling|closed|closing|out|exited|took)\s+(?:out\s+)?(?:of\s+)?(?:(\d)\s*\/\s*(\d)|half|a\s+third|a\s+quarter|some|most|part(?:ial)?|a\s+few|another\s+\d\/\d)\b/i.exec(t);
  const fullSell = /\b(?:sold|sell|selling|closed|closing|out|exited)\s+(?:out\s+)?(?:of\s+)?(?:the\s+)?(?:rest|remaining|remainder|all|everything|last|final)\b/i.test(t);
  if (RE_EXIT.test(low) || partSell) {
    const c = findContract(t);
    s.symbol = c ? c.symbol : bareSymbol(t, allowed);
    if (c) { s.strike = c.strike; s.side = c.side; s.expiry = c.expiry; }
    if (!s.symbol) { s.why = "sounds like an exit but I couldn't tell which ticker"; return s; }
    const part = fullSell ? null : partSell;
    if (part) {
      s.action = "TRIM"; s.matched = "partial sell"; s.fire = false;
      if (part[1] && part[2] && parseInt(part[2], 10) > 0)
        s.pct = Math.round(100 * parseInt(part[1], 10) / parseInt(part[2], 10));
      else if (/half/i.test(part[0])) s.pct = 50;
      else if (/third/i.test(part[0])) s.pct = 33;
      else if (/quarter/i.test(part[0])) s.pct = 25;
      s.why = "partial sell on " + s.symbol + " — a trim, not the exit";
      return s;
    }
    s.action = "CLOSE"; s.matched = "exit"; s.fire = true;
    s.why = "exit on " + s.symbol;
    return s;
  }

  // 7. "My avg is $3.05" — the fill price, posted a minute after the entry as
  //    its own message. USUALLY nothing to do with it: the order already
  //    fired off a full contract+price message and this is a redundant echo.
  //    But (9/3, Unraveller/META) when the ONLY thing that came before is a
  //    LOADING notice — no full-contract message ever fired — this line IS
  //    the fill confirmation ("Loading meta 610 puts weeklies" then, 12
  //    minutes later, "Meta avg 5.7 @here"), same shape as "Filled 3.95
  //    starters" above. A named ticker is required before this tries the
  //    loading shelf — a bare "my avg is $3.05" with no ticker stays exactly
  //    as informational as before (too ambiguous which position it means).
  if (RE_AVG.test(low)) {
    const symAvg = bareSymbol(t, allowed);
    const mAvg = RE_AVG_PRICE.exec(t);
    if (symAvg && mAvg) {
      s.action = "OPEN"; s.matched = "average fill on a loaded contract";
      s.needs_loaded = true;
      s.named_symbol = symAvg;
      s.limit = parseFloat(mAvg[1]);
      s.why = "their average (\"" + symAvg + " avg " + mAvg[1] + "\") with no " +
              "contract in it — looking for the LOADING call it belongs to, " +
              "otherwise this is just their fill price on a trade already open";
      return s;
    }
    s.matched = "their fill price";
    s.why = "that's their average fill on a trade they already called — " +
            "nothing to do with it";
    return s;
  }

  s.why = "nothing in it that means buy or sell";
  return s;
}

if (typeof module !== "undefined") {
  module.exports = { parseSignal, human, signalKey, cleanText };
}
