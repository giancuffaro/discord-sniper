/* test_resolve.js — the browser half of "which position did they mean?"
 *
 * A bare "Trimming @here" names no ticker. guards.py works it out from what
 * you're holding and who said it; extension/guards.js has to reach the exact
 * same answer, because that decision is what makes an exit fire or not. The
 * mirror of this file is the resolve block at the bottom of test_signals.py —
 * same three cases, same expected answers.
 *
 *   node test_resolve.js
 */
const fs = require("fs");
const path = require("path");

// guards.js is written for a service worker, so it expects chrome.* to exist.
// This is just enough of it to run: one key, in memory.
let store = {};
const chrome = {
  storage: { local: {
    async get(k) { return k in store ? { [k]: store[k] } : {}; },
    async set(o) { Object.assign(store, o); }
  } }
};

const src = fs.readFileSync(path.join(__dirname, "extension", "guards.js"), "utf8");
const load = new Function("chrome", "signalKey", "human",
  src + "\nreturn { resolveSymbol, guardRecord, guardState, " +
        "rememberLoading, resolveLoaded, resolveAdd, fillFromPosition, " +
        "clampQty };");
// guardRecord builds a dedupe key and resolveLoaded writes a readable line; the
// real versions of both live in parser.js and none of these cases depend on
// their exact shape.
const G = load(chrome,
               sig => [sig.action, sig.symbol].join("|"),
               sig => [sig.action, sig.symbol, sig.strike].join(" "));

let bad = 0;
function ok(cond, label) { if (!cond) { bad++; console.log("  - " + label); } }

(async () => {
  const CFG = { guards: {} };
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" })
    .format(new Date());

  // Brett opens NVDA, then trims without naming it.
  store = {};
  await G.guardRecord({ action: "OPEN", symbol: "NVDA", side: "CALLS",
                        strike: 210, expiry: "7/29", caller: "Brett" },
                      CFG, "Brett");
  let s = await G.resolveSymbol({ needs_position: true, symbol: null,
                                  caller: "Brett", fire: false }, "Brett");
  ok(s.fire && s.symbol === "NVDA",
     "Brett's bare trim should close Brett's NVDA, got " + s.symbol + " (" + s.why + ")");

  // Somebody else trims and the only thing open is Brett's. Must refuse —
  // closing it would exit a trade that admin never put you in.
  s = await G.resolveSymbol({ needs_position: true, symbol: null,
                              caller: "Unraveller", fire: false }, "Unraveller");
  ok(!s.fire && !s.symbol,
     "a trim from an admin whose trade you're not in must not close somebody " +
     "else's position, got " + s.symbol);

  // Nothing open at all.
  store = { guardState: { day: today, count: 0, lastFire: 0, recent: {}, positions: {} } };
  s = await G.resolveSymbol({ needs_position: true, symbol: null,
                              caller: "Brett", fire: false }, "Brett");
  ok(!s.fire && /not in anything/.test(s.why),
     "a bare trim with nothing open should say so, got " + s.why);

  // Two positions, neither of them theirs.
  store = { guardState: { day: today, count: 0, lastFire: 0, recent: {}, positions: {
    NVDA: { author: "Brett" }, SPY: { author: "Unraveller" } } } };
  s = await G.resolveSymbol({ needs_position: true, symbol: null,
                              caller: "Mike", fire: false }, "Mike");
  ok(!s.fire && /can't tell/.test(s.why),
     "two positions and an unrelated admin should refuse, got " + s.why);

  // --- the entry that arrives as two messages ------------------------------
  // "Loading 205 calls Friday expiration on NVDA" names the contract and buys
  // nothing; "Filled 3.95 starters" is the order and names nothing. Same cases
  // as the matching block in test_signals.py.
  const LCFG = { guards: {}, allowed_symbols: ["SPY", "NVDA", "AMZN"] };
  const loading = { action: "PREPARE", symbol: "NVDA", side: "CALLS",
                    strike: 205, expiry: "WEEKLY", caller: "Unraveller" };
  const fill = () => ({ action: "OPEN", needs_loaded: true, symbol: null,
                        side: null, strike: null, expiry: null, limit: 3.95,
                        fire: false, caller: "Unraveller" });

  store = {};
  await G.rememberLoading(loading, "Unraveller");
  s = await G.resolveLoaded(fill(), "Unraveller", LCFG);
  ok(s.fire && s.symbol === "NVDA" && s.strike === 205 && s.side === "CALLS" &&
     s.expiry === "WEEKLY",
     "the fill should take the contract from the loading call, got " +
     s.symbol + " (" + s.why + ")");

  // Used up — a second bare price is them averaging in, and you only ever hold
  // the one contract.
  s = await G.resolveLoaded(fill(), "Unraveller", LCFG);
  ok(!s.fire, "a second bare fill must not re-open the same trade: " + s.why);

  // Nobody loaded anything. This is the case that would otherwise buy blind.
  store = {};
  s = await G.resolveLoaded(fill(), "Brett", LCFG);
  ok(!s.fire && /can't find the LOADING call/.test(s.why),
     "a fill price with no loading call must not fire: " + s.why);

  // They loaded before lunch and posted a price at the close. Not the same
  // trade, so nothing is sent.
  store = {};
  await G.rememberLoading(loading, "Unraveller");
  store.guardState.loaded["unraveller"].ts -= 7200 * 1000;
  s = await G.resolveLoaded(fill(), "Unraveller", LCFG);
  ok(!s.fire && /too long ago/.test(s.why),
     "a fill two hours after the loading call must not fire: " + s.why);

  // "Loading does not mean enter" names no contract, so there is nothing to
  // pin a later price to.
  store = {};
  await G.rememberLoading({ action: "PREPARE", symbol: null, caller: "Unraveller" },
                          "Unraveller");
  s = await G.resolveLoaded(fill(), "Unraveller", LCFG);
  ok(!s.fire, "a loading line with no contract must not become a trade: " + s.why);

  // --- averaging in --------------------------------------------------------
  // Same four refusals as guards.py: switched off, not in it, already added
  // your limit of times, or it can't tell which position they meant.
  const AVOFF = { guards: { average_in: false }, allowed_symbols: ["SPY"] };
  const AVON = { guards: { average_in: true, max_adds_per_position: 2 },
                 allowed_symbols: ["SPY"] };
  const add = () => ({ action: "ADD", needs_add: true, symbol: "SPY",
                       side: null, strike: null, expiry: null, limit: 2.8,
                       qty: null, fire: false, caller: "Brett" });
  const opened = { action: "OPEN", symbol: "SPY", side: "CALLS", strike: 745,
                   expiry: "7/31", qty: 1, caller: "Brett" };

  store = {};
  await G.guardRecord(opened, AVOFF, "Brett");
  s = await G.resolveAdd(add(), "Brett", AVOFF);
  ok(!s.fire && /switched off/.test(s.why),
     "with averaging off an add must send nothing: " + s.why);

  store = {};
  await G.guardRecord(opened, AVON, "Brett");
  s = await G.resolveAdd(add(), "Brett", AVON);
  ok(s.fire, "averaging in should fire: " + s.why);
  // The contract comes from what you hold, never from their message.
  ok(s.strike === 745 && s.side === "CALLS" && s.expiry === "7/31",
     "an add must buy the contract you're holding, got " + s.strike + " " +
     s.side + " " + s.expiry);
  // 2.8 is their blended average across both contracts, not the price of the
  // one they just bought, so it must not survive as this order's limit.
  ok(s.limit === null,
     "their blended average must not become the limit, got " + s.limit);
  await G.guardRecord(s, AVON, "Brett");
  let st = await G.guardState();
  // Positions are keyed "trader|SYM" now — Brett's SPY, not just SPY.
  ok(st.positions["brett|SPY"].qty === 2 && st.positions["brett|SPY"].adds === 1,
     "after one add you hold two contracts, got " + JSON.stringify(st.positions["brett|SPY"]));

  s = await G.resolveAdd(add(), "Brett", AVON);
  ok(s.fire, "the second add is within the limit of 2: " + s.why);
  await G.guardRecord(s, AVON, "Brett");
  s = await G.resolveAdd(add(), "Brett", AVON);
  ok(!s.fire && /your limit/.test(s.why), "a third add must be refused: " + s.why);

  // And the exit sells all three. Selling one would leave you holding two while
  // the log says you're flat.
  const exit = { action: "CLOSE", symbol: "SPY", qty: 1, caller: "Brett" };
  await G.fillFromPosition(exit, "Brett");
  ok(exit.qty === 3, "an exit must sell everything you averaged into, got " + exit.qty);
  ok(G.clampQty(exit.qty, AVON, "CLOSE") === 3,
     "max_qty caps what you buy, never what you sell, got " +
     G.clampQty(exit.qty, AVON, "CLOSE"));
  ok(G.clampQty(5, AVON, "OPEN") === 1, "an entry is still capped at max_qty");

  // Adding to something you're not in has nothing to average into.
  store = {};
  s = await G.resolveAdd(add(), "Brett", AVON);
  ok(!s.fire && /not in it/.test(s.why),
     "an add on a trade you don't hold must send nothing: " + s.why);

  // Unnamed add, two of their own positions open — it must not guess.
  store = { guardState: { day: today, count: 0, lastFire: 0, recent: {}, loaded: {},
    positions: { SPY: { author: "brett", qty: 1, adds: 0 },
                 NVDA: { author: "brett", qty: 1, adds: 0 } } } };
  const vague = add(); vague.symbol = null;
  s = await G.resolveAdd(vague, "Brett", AVON);
  ok(!s.fire, "an unnamed add with two of their positions open must not guess: " + s.why);

  if (bad) { console.log("\n" + bad + " check(s) failed."); process.exit(1); }
  console.log("The extension picks the same position Python does, pins a "
              + "bare fill price to the same loading call, and averages in on "
              + "the same terms.");
})();
