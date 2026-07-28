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
const RE_HDR = /^[A-Za-z0-9_.\- ]{2,24}\s*\((scribe|admin|mod)\)\s*[—\-]+\s*\d{1,2}:\d{2}\s*(AM|PM)\s*/i;
const RE_EMOJI = /[\u{1F000}-\u{1FAFF}\u{2190}-\u{27BF}\u{FE0F}\u{200D}]/gu;

const RE_CONTRACT = /\$?([A-Za-z]{1,5})\s+(?:(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d*dte)\s+)?(\d{1,5}(?:\.\d{1,2})?)\s*(calls?|puts?|c|p)\b/gi;
const RE_PCT = /@\s*(\d{1,3}(?:\.\d+)?)\s*%/;
const RE_LIMIT = /@\s*\$?(\d+(?:\.\d{1,4})?)(?![\d.]*\s*%)/;
const RE_QTY = /\b(\d{1,3})\s*(?:x|contracts?|lots?)\b/i;
const RE_BARE = /\b([A-Z]{1,5})\b/g;

const RE_LOADING = /\bloading\b/i;
const RE_ALLOUT = /\ball\s+out\b/i;
const RE_TRIM = /\btrim(?:ming|med|s)?\b/i;
const RE_BACKIN = /\bback\s+in\b/i;
const RE_ENTRY = /\b(?:in|entered|entering|filled|bto|bought|buying)\b/i;
const RE_EXIT = /\b(?:exited|exiting|closed|closing|stc|sold|selling|out)\b/i;

const VETO_WORDS = ["do not", "don't", "dont ", "watching", "watch", "eyeing",
  "looking at", "thinking", "maybe", "might", "if it", "if you", "waiting",
  "wait for", "heads up", "scanner", "idea", "consider", "recap", "example",
  "congrats", "missed", "sorry", "pissed", "sets the tone", "session",
  "overall", "read was", "look at that", "still holding", "use $", "as risk",
  "anyone", "lmk", "great job"];

const NOT_TICKERS = new Set(["THE", "A", "AN", "IT", "ALL", "IN", "OUT", "AT",
  "ON", "MY", "IS", "AND", "OF", "TO", "BE", "OK", "DTE", "AM", "PM", "ET",
  "DO", "NOT", "BUY", "SELL", "IE", "ADMIN", "HERE", "EOD", "CPI", "FOMC",
  "PT", "SL", "TP", "AVG", "GO", "UP", "WE", "US", "NO"]);

function cleanText(raw) {
  let t = String(raw || "").trim().replace(RE_HDR, "");
  t = t.replace(RE_PING, " ").replace(RE_CALLER, " ").replace(RE_EMOJI, " ");
  t = t.replace(/^\s*\d{1,3}\.\s*/, "");
  return t.replace(/\s+/g, " ").trim();
}

function findContract(text) {
  RE_CONTRACT.lastIndex = 0;
  let m;
  while ((m = RE_CONTRACT.exec(text)) !== null) {
    const sym = m[1].toUpperCase();
    if (NOT_TICKERS.has(sym)) continue;
    const k = m[4].toLowerCase();
    return { symbol: sym, strike: parseFloat(m[3]),
             side: k.startsWith("c") ? "CALLS" : "PUTS",
             expiry: (m[2] || "").toUpperCase() || null };
  }
  return null;
}

function bareSymbol(text, allowed) {
  RE_BARE.lastIndex = 0;
  let m;
  while ((m = RE_BARE.exec(text)) !== null) {
    const s = m[1].toUpperCase();
    if (NOT_TICKERS.has(s)) continue;
    if (allowed.length && !allowed.includes(s)) continue;
    if (!allowed.length && s.length < 2) continue;
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
  return [s.action, s.symbol, s.side, s.strike, s.expiry, s.pct,
          s.reenter ? 1 : 0].join("|");
}

function parseSignal(text, cfg) {
  cfg = cfg || {};
  const allowed = (cfg.allowed_symbols || []).map(x => String(x).toUpperCase());
  const raw = String(text || "").trim();
  const s = { fire: false, why: "", action: null, symbol: null, side: null,
              strike: null, expiry: null, limit: null, pct: null, qty: null,
              caller: "", reenter: false, reenter_limit: null,
              warn: "", raw, clean: "", matched: "" };
  if (!raw) { s.why = "empty message"; return s; }

  const t = cleanText(raw);
  s.clean = t;
  const low = t.toLowerCase();

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

  // 4. TRIMMING — a partial. You hold one contract, so you can't trim; what you
  //    can choose is which of their trims you take your money on.
  if (RE_TRIM.test(low)) {
    s.symbol = bareSymbol(t, allowed);
    s.action = "TRIM"; s.matched = "trim";
    const m = RE_PCT.exec(t);
    if (m) s.pct = parseFloat(m[1]);
    if (!s.symbol) { s.why = "a trim, but I couldn't tell which ticker"; return s; }
    const mode = String(cfg.trim_action || "ignore").toLowerCase();
    if (mode === "close") {
      s.action = "CLOSE"; s.fire = true;
      s.why = "closing " + s.symbol + " on their first trim";
    } else if (mode === "at_pct") {
      const target = parseFloat(cfg.close_at_trim_pct != null ? cfg.close_at_trim_pct : 50);
      if (s.pct !== null && s.pct >= target) {
        s.action = "CLOSE"; s.fire = true;
        s.why = "closing " + s.symbol + " — they're trimming at " + s.pct +
                "%, your target is " + target + "%";
      } else {
        s.why = "trim on " + s.symbol + " at " + (s.pct === null ? "?" : s.pct) +
                "% — under your " + target + "% target, holding";
      }
    } else {
      s.why = "trim on " + s.symbol + (s.pct === null ? "" : " at " + s.pct + "%") +
              " — you're set to ignore trims and exit on \"all out\"";
    }
    return s;
  }

  // 5. IN — the entry. Needs a full contract; a bare "in" is not an order.
  if (RE_ENTRY.test(low)) {
    const c = findContract(t);
    if (!c) { s.why = "sounds like an entry but there's no full contract in it"; return s; }
    s.symbol = c.symbol; s.strike = c.strike; s.side = c.side; s.expiry = c.expiry;
    s.action = "OPEN"; s.matched = "entry";
    const m = RE_LIMIT.exec(t);
    if (m) s.limit = parseFloat(m[1]);
    const mq = RE_QTY.exec(t);
    if (mq) s.qty = parseInt(mq[1], 10);
    if (allowed.length && !allowed.includes(s.symbol)) {
      s.why = s.symbol + " isn't on your allowed-symbols list";
      return s;
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

  s.why = "nothing in it that means buy or sell";
  return s;
}

if (typeof module !== "undefined") {
  module.exports = { parseSignal, human, signalKey, cleanText };
}
