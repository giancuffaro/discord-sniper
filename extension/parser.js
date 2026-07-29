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
const RE_EMOJI = /[\u{1F000}-\u{1FAFF}\u{2190}-\u{27BF}\u{FE0F}\u{200D}]/gu;

// The $ before the strike is Brett's habit: "In NVDA $210C to July 29th".
// The lookbehind is load-bearing. Without it the symbol group happily matches
// the TAIL of a longer word — "Loading 205 calls" gave a ticker of ADING, which
// then failed the allowed-list check for reasons that had nothing to do with
// what the line said.
const RE_CONTRACT = /(?<![A-Za-z])\$?([A-Za-z]{1,5})\s+(?:(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d*dte)\s+)?\$?(\d{1,5}(?:\.\d{1,2})?)\s*(calls?|puts?|c|p)\b/gi;

// The same contract written back to front: "205 calls Friday expiration on
// NVDA". Requires the word "on" before the ticker — that's what keeps it from
// reading "10% on SPY" as a contract, and it's how they actually write it.
const RE_CONTRACT_REV = /(?<![A-Za-z\d.])\$?(\d{1,5}(?:\.\d{1,2})?)\s*(calls?|puts?)\b([^.!?]{0,40}?)\bon\s+\$?([A-Za-z]{1,5})\b/gi;

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
const RE_DTE_ANY = /\b(\d*dte)\b/i;
const RE_DATE_ANY = /\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b/;

const RE_PCT = /@\s*(\d{1,3}(?:\.\d+)?)\s*%/;
// A percentage anywhere at all. The second room writes trims as a bare number:
// "20%", "50% @here", "40% in spy now". No verb, no ticker, just the number.
const RE_PCT_ANY = /(\d{1,3}(?:\.\d+)?)\s*%/;
// "5-6% risk." and "risk was only 10%" are position sizing, not a gain. Same
// shape as a bare trim and the exact opposite meaning — read as a trim it sells
// you out of a trade on a sentence about how much they're willing to lose. Only
// consulted when the line has no exit verb in it, so "trimming SPY @ 45%, risk
// free now" is untouched.
const RE_PCT_RISK = /\d{1,3}(?:\.\d+)?\s*%\s*(?:of\s+)?(?:risk|stop|trail)\b|\b(?:risk|risking|risked|stop|trail)\b[^.!?]{0,20}?\d{1,3}(?:\.\d+)?\s*%/i;
// "My avg is $3.05" — posted a minute after the entry, as its own message.
const RE_AVG = /\bavg|\baverage\b/i;
const RE_LIMIT = /@\s*\$?(\d+(?:\.\d{1,4})?)(?![\d.]*\s*%)/;
const RE_QTY = /\b(\d{1,3})\s*(?:x|contracts?|lots?)\b/i;
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
const RE_FUT_ENTRY = /\b(short|long)\s+\$?([A-Za-z0-9]{1,4})\s*@\s*\$?(\d[\d,]*(?:\.\d{1,2})?)/i;
const RE_THEIR_STOP = /\bstop\s*(?:loss)?\s*[:=@]?\s*\$?(\d[\d,]*(?:\.\d{1,2})?)\b/i;
const RE_THEIR_TARGET = /\b(?:target|tp|pt)\s*[:=@]?\s*\$?(\d[\d,]*(?:\.\d{1,2})?)\b/i;
// "Target hit $1700 a contract - 2nd trim" / "$1,100 a contract on NQ short".
// His futures trims speak in dollars per contract, and on a dry run that
// number is the only honest exit price there is.
const RE_USD_CONTRACT = /\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(?:a|per|\/)\s*contract/i;

function num(s) { return parseFloat(String(s).replace(/,/g, "")); }

const RE_LOADING = /\bloading\b/i;
const RE_ALLOUT = /\ball\s+out\b/i;
const RE_TRIM = /\btrim(?:ming|med|s)?\b/i;
const RE_BACKIN = /\bback\s+in\b/i;
const RE_ENTRY = /\b(?:in|entered|entering|filled|bto|bought|buying)\b/i;
const RE_EXIT = /\b(?:exited|exiting|closed|closing|stc|sold|selling|out)\b/i;
// "Filled 3.95 starters" — their entry arrives as TWO messages. The contract was
// named minutes earlier in a "Loading 205 calls Friday expiration on NVDA"
// notice, and this line carries nothing but the price. On its own it is not an
// order; resolveLoaded in guards.js pins it to that notice, or nothing is sent.
// Only a line that STARTS with the fill verb counts — "trimmed at 3.95" and
// "their avg was 3.95" are the same numbers meaning the opposite thing.
const RE_BARE_FILL = /^(?:just\s+|we\s+|i\s+|i've\s+|ive\s+|we've\s+)*(?:filled|fills|filling|fill|bought|bto|entered)\b[^\d%]{0,14}\$?(\d{1,3}\.\d{1,2})\b(?!\s*%)/i;
// "added to SPY @everyone new avg is 2.8" — they doubled up and their average
// moved. Whether that buys you a second contract is a setting, not a parser
// decision: resolveAdd in guards.js has the final word, because only the guards
// know whether you're even in it.
const RE_ADD = /\badd(?:ed|ing|s)?\s+(?:to|more)\b|\badding\b|\baverag(?:e|ed|ing)\s+(?:in|down|up)\b|\b(?:new|updated)\s+(?:avg|average)\b/i;
// The price out of "new avg is 2.8", "avg 3.05", "average: $2.90". Never a
// percentage — "avg gain 30%" is a result, not a price.
const RE_AVG_PRICE = /\b(?:avg|average)\w*\s*(?:is|of|at|around|near|:|=|@)?\s*\$?(\d{1,3}(?:\.\d{1,2})?)\b(?!\s*%)/i;

const VETO_WORDS = ["do not", "don't", "dont ", "watching", "watch", "eyeing",
  "looking at", "thinking", "maybe", "might", "if it", "if you", "waiting",
  "wait for", "heads up", "scanner", "idea", "consider", "recap", "example",
  "congrats", "missed", "sorry", "pissed", "sets the tone", "session",
  "overall", "read was", "look at that", "still holding", "use $", "as risk",
  "anyone", "lmk", "great job",
  // The victory-lap paragraph. It's full of percentages and prices and it is
  // not a call — none of these words ever appear in one.
  "yesterday", "tomorrow", "nice day", "conviction", "wish i"];

const NOT_TICKERS = new Set(["THE", "A", "AN", "IT", "ALL", "IN", "OUT", "AT",
  "ON", "MY", "IS", "AND", "OF", "TO", "BE", "OK", "DTE", "AM", "PM", "ET",
  "DO", "NOT", "BUY", "SELL", "IE", "ADMIN", "HERE", "EOD", "CPI", "FOMC",
  "PT", "SL", "TP", "AVG", "GO", "UP", "WE", "US", "NO",
  // The verbs themselves. "sold 205 calls on nvda" read SOLD as the ticker,
  // because a word directly in front of a strike looks exactly like a symbol.
  // None of these is ever a ticker he trades.
  "SOLD", "TRIM", "HOLD", "GOT", "ADD", "FULL", "TOOK", "LOAD", "FILL",
  "CALL", "CALLS", "PUT", "PUTS", "LONG", "SHORT", "SIZE", "RISK", "NEW",
  "JUST", "NOW", "OVER", "UNDER", "NEAR", "ABOVE"]);

function cleanText(raw) {
  let t = String(raw || "").trim().replace(RE_HDR, "");
  t = t.replace(RE_PING, " ").replace(RE_CALLER, " ").replace(RE_EMOJI, " ");
  // Numbered paste lines ("14. Loading 205 calls..."). The space after the dot
  // is required: without it "206.5 need to clear now" becomes "5 need to clear
  // now", and "747.5 calls on SPY" would turn into a strike of 5.
  t = t.replace(/^\s*\d{1,3}\.\s+/, "");
  return t.replace(/\s+/g, " ").trim();
}

/* "to July 29th" -> "7/29". Only used when the contract itself didn't carry an
 * expiry, so it can never override one they actually wrote. */
function expiryAnywhere(text) {
  let m = RE_MONTH_DAY.exec(text);
  if (m) return MONTHS[m[1].toLowerCase().slice(0, 3)] + "/" + parseInt(m[2], 10);
  m = RE_DTE_ANY.exec(text);
  if (m) return m[1].toUpperCase();
  m = RE_DATE_ANY.exec(text);
  if (m) return parseInt(m[1], 10) + "/" + parseInt(m[2], 10) + (m[3] ? "/" + m[3] : "");
  return null;
}

function findContract(text) {
  RE_CONTRACT.lastIndex = 0;
  let m;
  while ((m = RE_CONTRACT.exec(text)) !== null) {
    const sym = m[1].toUpperCase();
    if (NOT_TICKERS.has(sym)) continue;
    const k = m[4].toLowerCase();
    let expiry = (m[2] || "").toUpperCase() || null;
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
    if (FUT_SYMS.has(s) && raw === s) return s;
    if (allowed.length) {
      if (!allowed.includes(s)) continue;
    } else {
      if (raw !== s || s.length < 2) continue;
    }
    return s;
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

function parseSignal(text, cfg) {
  cfg = cfg || {};
  const allowed = (cfg.allowed_symbols || []).map(x => String(x).toUpperCase());
  const raw = String(text || "").trim();
  const s = { fire: false, why: "", action: null, symbol: null, side: null,
              strike: null, expiry: null, limit: null, pct: null, qty: null,
              caller: "", reenter: false, reenter_limit: null,
              needs_position: false, needs_loaded: false, needs_add: false,
              // Futures and his-levels support. kind is "future" on a futures
              // call and "" otherwise; direction is LONG/SHORT; their_stop and
              // their_target are the levels HE posted; usd is "$1,100 a
              // contract" off a trim, the only honest futures exit price a
              // dry run has.
              kind: "", direction: null, their_stop: null, their_target: null,
              usd: null,
              warn: "", raw, clean: "", matched: "" };
  if (!raw) { s.why = "empty message"; return s; }

  const t = cleanText(raw);
  s.clean = t;
  const low = t.toLowerCase();

  // Who said it. Two shapes: the scribe relaying somebody ("@Brett (Admin)
  // ..."), and the admin posting straight into the room ("Brett (Admin) —
  // 10:20 AM ..."). The relay wins when both are there.
  const mh = RE_HDR.exec(raw);
  if (mh) s.caller = mh[1].trim();
  const mc = RE_CALLER.exec(raw);
  if (mc) s.caller = mc[1];

  if (t.includes("?")) { s.why = "it's a question, not a call"; return s; }

  const veto = VETO_WORDS.concat(cfg.extra_veto_words || []);
  for (const w of veto) {
    if (low.includes(String(w).toLowerCase())) {
      s.why = 'chatter, not an order (it contains "' + String(w).trim() + '")';
      return s;
    }
  }

  // 1. LOADING — get ready. Never buys; that is the room's own instruction.
  if (RE_LOADING.test(low)) {
    const c = findContract(t);
    s.action = "PREPARE"; s.matched = "loading";
    if (c) { s.symbol = c.symbol; s.strike = c.strike; s.side = c.side; s.expiry = c.expiry; }
    s.why = "they're getting ready on " + (s.symbol || "something") +
            " — LOADING never buys, that's the room's own rule";
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

  // 3b. ADDED TO — they doubled up and posted their new average.
  //     A second buy on a trade you're already in. The parser stops short of
  //     firing it, because the three things that decide it are all state: is
  //     averaging switched on, are you actually in that position, and how many
  //     times have you added already. resolveAdd in guards.js.
  if (RE_ADD.test(low)) {
    const c = findContract(t);
    s.symbol = c ? c.symbol : bareSymbol(t, allowed);
    if (c) { s.strike = c.strike; s.side = c.side; s.expiry = c.expiry; }
    s.action = "ADD"; s.matched = "added to their position";
    s.needs_add = true;
    const m = RE_LIMIT.exec(t) || RE_AVG_PRICE.exec(t);
    if (m) s.limit = parseFloat(m[1]);
    const mq = RE_QTY.exec(t);
    if (mq) s.qty = parseInt(mq[1], 10);
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
  if (mf && FUT_SYMS.has(mf[2].toUpperCase())) {
    s.symbol = mf[2].toUpperCase();
    s.kind = "future";
    s.direction = mf[1].toUpperCase();
    s.limit = num(mf[3]);
    s.action = "OPEN"; s.matched = "futures entry";
    const rest = t.slice((mf.index || 0) + mf[0].length);
    const ms = RE_THEIR_STOP.exec(rest);
    if (ms) s.their_stop = num(ms[1]);
    const mt = RE_THEIR_TARGET.exec(rest);
    if (mt) s.their_target = num(mt[1]);
    s.fire = true;
    s.why = "futures entry: " + s.direction + " " + s.symbol + " @ " +
            s.limit + (s.their_stop !== null ? ", their stop " + s.their_stop : "") +
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
  const pctM = RE_PCT.exec(t) || RE_PCT_ANY.exec(t);
  if (pctM && !RE_TRIM.test(low) && RE_PCT_RISK.test(t)) {
    s.why = "that percentage is their risk, not a gain — nothing to act on";
    return s;
  }
  // "Full sold nvda close to 25%" — the word FULL turns a percentage line
  // into a complete exit. Without this, the trim rule below would swallow it
  // and sell 3 of 5 on a call that means "I'm out".
  if (/\bfull(?:y)?\b/i.test(low) && RE_EXIT.test(low) && pctM && !findContract(t)) {
    s.symbol = bareSymbol(t, allowed);
    s.action = "CLOSE"; s.matched = "full exit";
    s.pct = parseFloat(pctM[1]);
    if (!s.symbol) {
      s.needs_position = true;
      s.why = "a full exit with no ticker in it — working out which position they meant";
      return s;
    }
    s.fire = true;
    s.why = "full exit on " + s.symbol;
    return s;
  }
  if (RE_TRIM.test(low) || (pctM && !findContract(t))) {
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
    s.why = "trim on " + s.symbol +
            (s.pct === null ? "" : " at " + s.pct + "%") +
            " — following their trim";
    return s;
  }

  // 5. IN — the entry. Needs a full contract; a bare "in" is not an order.
  if (RE_ENTRY.test(low)) {
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
      s.why = "sounds like an entry but there's no full contract in it";
      return s;
    }
    s.symbol = c.symbol; s.strike = c.strike; s.side = c.side; s.expiry = c.expiry;
    s.action = "OPEN"; s.matched = "entry";
    const m = RE_LIMIT.exec(t);
    if (m) s.limit = parseFloat(m[1]);
    const mq = RE_QTY.exec(t);
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

  // 6. A plain exit word with something identifiable behind it.
  if (RE_EXIT.test(low)) {
    const c = findContract(t);
    s.symbol = c ? c.symbol : bareSymbol(t, allowed);
    if (c) { s.strike = c.strike; s.side = c.side; s.expiry = c.expiry; }
    if (!s.symbol) { s.why = "sounds like an exit but I couldn't tell which ticker"; return s; }
    s.action = "CLOSE"; s.matched = "exit"; s.fire = true;
    s.why = "exit on " + s.symbol;
    return s;
  }

  // 7. "My avg is $3.05" — the fill price, posted a minute after the entry as
  //    its own message. Nothing to do with it: the order is long gone by then
  //    by then. Named here only so
  //    the log says something useful instead of "nothing in it".
  if (RE_AVG.test(low)) {
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
