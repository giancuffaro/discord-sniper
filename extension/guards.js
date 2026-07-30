/* guards.js — the brakes, browser side. Mirrors guards.py.
 *
 * State lives in chrome.storage.local, not in a variable, because a Manifest V3
 * service worker gets shut down whenever Chrome feels like it. If the counters
 * and the position tracker lived in memory, your "6 trades a day" cap would
 * quietly reset every time the worker napped — and you'd find out on the worst
 * possible day.
 */

/* The old knobs — trim modes, add limits, daily caps, allowed lists — are
 * deleted, not defaulted. His rule: "no filters wanted. id like to follow
 * everything to the tee as they do." What's left is the safety that isn't a
 * filter: dedupe, cooldown, staleness, market hours, and the position book. */
const GUARD_DEFAULTS = {
  cooldown_seconds: 5,
  dedupe_seconds: 120,
  regular_hours_only: true,
  open_time: "09:30",
  // New trades are allowed right through to the closing bell. Exits are not
  // time-boxed at all — see guardCheck, which only applies this to OPEN.
  close_time: "16:00",
  max_message_age_seconds: 20
};

function etNow() {
  // Read the wall clock in New York without dragging in a date library.
  const f = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour12: false,
    weekday: "short", hour: "2-digit", minute: "2-digit"
  }).formatToParts(new Date());
  const g = t => f.find(p => p.type === t).value;
  return { wd: g("weekday"), h: (+g("hour")) % 24, m: +g("minute") };
}

function hm(s) {
  const [a, b] = String(s || "09:30").split(":");
  return (+a) * 60 + (+b);
}

function todayET() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" })
    .format(new Date());
}

/* One trade = one trader + one ticker. "brett|SPY" and "unraveler|SPY" are
 * different trades in the same name — that's the whole point. Mirrors
 * positions.key_of on the bridge, so the two sides' books line up key for key. */
function posKey(trader, symbol) {
  return ((String(trader || "?").trim().toLowerCase()) || "?") + "|" +
         String(symbol || "").toUpperCase();
}
function keySymbol(k) { return String(k || "").split("|").pop(); }
function keyWho(k) { return String(k || "").split("|")[0]; }

/* Positions written down before the trader went into the key were stored under
 * the bare ticker. Move them once, using the author that was already on them —
 * losing a live position over a bookkeeping change would be unforgivable. */
function migratePositions(pos) {
  const out = {};
  for (const [k, p] of Object.entries(pos || {})) {
    out[k.includes("|") ? k : posKey((p || {}).author, k)] = p;
  }
  return out;
}

async function guardState() {
  const { guardState: st } = await chrome.storage.local.get("guardState");
  const day = todayET();
  if (st && st.day === day) {
    st.recent = st.recent || {};
    st.positions = migratePositions(st.positions || {});
    st.loaded = st.loaded || {};
    return st;
  }
  // A new day resets the counter, but NOT the positions — an option you bought
  // yesterday is still sitting in your account this morning. Loading notices do
  // reset: yesterday's "getting ready on NVDA" means nothing this morning.
  return { day, count: 0, lastFire: 0, recent: {}, loaded: {},
           positions: migratePositions((st && st.positions) || {}) };
}

/* One line per traded ENTRY, for the whole day: trader + contract + posted
 * price. A scribe repost or a reply-quote is word-for-word the same call,
 * and "already in" only protects while you're holding — this is what stops
 * the echo re-buying AMD at top tick an hour after the trade closed. A real
 * re-entry always comes at a different posted price, so it passes. */
function echoKey(sig, who) {
  return [String(who || "").toLowerCase(), sig.symbol, sig.strike, sig.expiry,
          sig.side, sig.limit].join("|");
}

async function saveGuardState(s) {
  await chrome.storage.local.set({ guardState: s });
}

/* Where we are in the trading day. Used by the badge and by the auto-sleep, so
 * they can't disagree with what guardCheck would actually do. */
function sessionPhase(g) {
  const t = etNow();
  if (t.wd === "Sat" || t.wd === "Sun") return "shut";
  const mins = t.h * 60 + t.m;
  if (mins < hm(g.open_time)) return "early";
  if (mins > hm(g.close_time)) return "done";
  return "live";
}

/* Returns {allowed, reason}. Reasons are written for a human at 9:31am. */
async function guardCheck(sig, ctx, cfg) {
  const g = Object.assign({}, GUARD_DEFAULTS, cfg.guards || {});
  const now = Date.now();
  const st = await guardState();

  if (cfg.stopped || cfg.armed === false)
    return { allowed: false,
             reason: "the bot is switched OFF — turn it ON in the popup to trade" };

  const chans = (cfg.channel_ids || []).map(String).filter(Boolean);
  if (chans.length && !chans.includes(String(ctx.channelId)))
    return { allowed: false, reason: "that message wasn't in a channel you're listening to" };

  const names = (cfg.author_names || []).map(a => String(a).toLowerCase()).filter(Boolean);
  if (names.length && !names.includes(String(ctx.author || "").toLowerCase()))
    return { allowed: false, reason: ctx.author + " isn't on your trusted-poster list, so it was ignored" };

  const admins = (cfg.follow_admins || []).map(a => String(a).toLowerCase()).filter(Boolean);
  if (admins.length && sig.caller && !admins.includes(String(sig.caller).toLowerCase()))
    return { allowed: false, reason: "that was " + sig.caller + "'s call, and you're only following " + (cfg.follow_admins || []).join(", ") };

  const age = (now - (ctx.postedAt || now)) / 1000;
  if (g.max_message_age_seconds && age > g.max_message_age_seconds)
    return { allowed: false, reason: "that call is " + Math.round(age) + " seconds old — too stale to chase" };

  if (g.regular_hours_only && (sig.action === "OPEN" || sig.action === "ADD")) {
    const t = etNow();
    if (t.wd === "Sat" || t.wd === "Sun")
      return { allowed: false, reason: "it's the weekend — the market is shut" };
    const mins = t.h * 60 + t.m;
    if (mins < hm(g.open_time) || mins > hm(g.close_time))
      return { allowed: false, reason: "it's " + String(t.h).padStart(2, "0") + ":" +
        String(t.m).padStart(2, "0") + " ET — new trades are only allowed between " +
        g.open_time + " and " + g.close_time };
  }

  // What you're holding is checked before anything else, because "you're
  // already in AMD" tells you far more than "that looked like a repeat".
  // Checked per TRADER now: Brett being in SPY doesn't stop Unraveler's SPY
  // call — those are two different trades and both should run.
  const who = String(sig.caller || ctx.author || "").toLowerCase();
  // A position whose owner was never known blocks anyone's re-entry in that
  // name — better one missed trade than one doubled one.
  const already = st.positions[posKey(who, sig.symbol)] ||
    Object.keys(st.positions).some(k => keySymbol(k) === sig.symbol &&
                                        keyWho(k) === "?");
  if (sig.action === "OPEN" && already)
    return { allowed: false, reason: "you're already in " + sig.symbol +
      " from their earlier call — this one would double you up" };

  // The echo guard. Only with a posted price — re-entries with no price
  // (Aristotle's bare contracts) can't be told apart from each other, and
  // blocking those would block his real second run at a name.
  if (sig.action === "OPEN" && sig.limit !== null && sig.limit !== undefined) {
    st.echoes = st.echoes || {};
    if (st.echoes[echoKey(sig, who)])
      return { allowed: false, reason: "that exact call (same contract, same " +
        "price) already ran today — reads like a repost or a reply quote, " +
        "not a new trade" };
  }

  if ((sig.action === "CLOSE" || sig.action === "TRIM") &&
      !st.positions[posKey(who, sig.symbol)] &&
      !Object.keys(st.positions).some(k => keySymbol(k) === sig.symbol))
    // At most brokers a sell with nothing to sell isn't a no-op — it opens a
    // short. Never send it.
    return { allowed: false, reason: "you're not in " + sig.symbol +
      ", so there's nothing to " + (sig.action === "TRIM" ? "trim" : "close") +
      " — the order was not sent" };

  const last = st.recent[signalKey(sig)];
  if (last && (now - last) / 1000 < g.dedupe_seconds)
    return { allowed: false, reason: "already acted on that exact call " +
      Math.round((now - last) / 1000) + "s ago" };

  if (sig.action === "OPEN" || sig.action === "ADD") {
    if ((now - st.lastFire) / 1000 < g.cooldown_seconds)
      return { allowed: false, reason: "still in the " + g.cooldown_seconds +
        "s cooldown after the last fire" };
    // The daily trade cap is gone — he follows every call they make.
  }

  return { allowed: true, reason: "allowed" };
}

/* A bare "Trimming @here", or a lone "20%", names no ticker. Everyone in the
 * room knows which position they mean; a broker does not.
 *
 * Two admins run that room and they are usually in different things, so the
 * first question is who said it — a trim from Brett means Brett's position. If
 * that's not enough and you only hold one thing, it's that one. If it's still
 * ambiguous, nothing is sent and you're told why: guessing which position to
 * close is how you end up flat on the wrong ticker and still holding the loser. */
async function resolveSymbol(sig, author) {
  if (sig.symbol || !sig.needs_position) return sig;
  const st = await guardState();
  const held = st.positions || {};
  const keys = Object.keys(held);
  if (!keys.length) {
    sig.why = "a trim with no ticker in it, and you're not in anything — nothing to close";
    return sig;
  }
  const who = String(sig.caller || author || "").toLowerCase();
  const pick = pickHeld(held, who);

  if (!pick) {
    const what = keys.slice().sort().map(k =>
      keySymbol(k) + " (" + keyWho(k) + "'s call)").join(", ");
    sig.why = "a trim with no ticker in it. You're in " + what + ", and this " +
      "came from " + (sig.caller || author || "somebody I couldn't name") +
      " — I can't tell which one they meant, so nothing was sent. Close it in " +
      "the Webull app if you want out.";
    return sig;
  }
  sig.symbol = keySymbol(pick);
  sig.fire = true;
  sig.why = (sig.action === "TRIM" ? "trimming " : "closing ") + sig.symbol +
            " — they didn't name it, but it's the position " +
            (sig.caller || author || "they") + " put you in";
  return sig;
}

/* Which of your open positions did this admin mean? Their own first, and the
 * only one open second — but never somebody else's. The positions are keyed
 * "trader|SYM" now, so "their own" is just a key prefix. Returns the KEY, or
 * null when it can't be sure — and being sure is the whole point. */
function pickHeld(held, who) {
  const keys = Object.keys(held || {});
  if (!keys.length) return null;
  const theirs = keys.filter(k => who && keyWho(k) === who);
  // Their own, and when they hold several, the NEWEST — Aristotle runs a
  // swing and a scalp at once, and his bare "12%" / "Out" is always about
  // the trade he just opened, not the swing from Tuesday.
  if (theirs.length >= 1) {
    theirs.sort((a, b) => ((held[b] || {}).ts || 0) - ((held[a] || {}).ts || 0));
    return theirs[0];
  }
  if (keys.length === 1) {
    const owner = keyWho(keys[0]);
    if (!who || owner === "?" || owner === who) return keys[0];
  }
  return null;
}

/* "added to SPY, new avg is 2.8" — they bought more of what they're already in.
 * Following them means a second contract at today's price, so this is the one
 * place in the file that spends money on purpose rather than because a call came
 * in. Four ways it says no: averaging is off, you're not in that trade, you've
 * already added as many times as you allowed, or it can't tell which position
 * they meant. Mirrors guards.resolve_add. */
async function resolveAdd(sig, author, cfg) {
  if (!sig.needs_add) return sig;
  const who = String(sig.caller || author || "").toLowerCase();

  // The average_in switch, the add ceiling and the allowed-list check that
  // used to live here are deleted — "follow everything to the tee". The one
  // rule left is the one that isn't a preference: you can only add to a
  // trade you're actually in.
  const st = await guardState();
  const held = st.positions || {};
  if (!sig.symbol) {
    const k = pickHeld(held, who);
    if (k) sig.symbol = keySymbol(k);
  }
  if (!sig.symbol) {
    sig.why = "they added to a position and didn't name it, and I can't tell " +
              "which one they meant — nothing was sent";
    return sig;
  }
  const pos = findHeld(held, who, sig.symbol);
  if (!pos) {
    sig.why = "they added to their " + sig.symbol + ", but you're not in it — " +
              "there's nothing to average into";
    return sig;
  }
  const adds = parseInt(pos.adds || 0, 10) || 0;
  // The contract comes from what you're holding, never from the add message —
  // "added to SPY" doesn't say which strike, and buying a different one isn't
  // averaging, it's a second trade.
  sig.side = pos.side; sig.strike = pos.strike; sig.expiry = pos.expiry;
  sig.qty = 1;
  sig.fire = true;
  // 2.8 in "new avg is 2.8" is their BLENDED average across both contracts,
  // not what the second one cost. Their first fill was on one side of it and
  // the one they just bought was on the other, so it is not a price anything
  // can be bought at and it must never become the limit on this order. Kept
  // for the log line, dropped here.
  const theirAvg = sig.limit;
  sig.limit = null;
  sig.why = "averaging into " + sig.symbol + " — that's your " +
            (adds === 0 ? "first" : "next") + " add on it" +
            (theirAvg === null || theirAvg === undefined ? ""
             : ", their average across both is now " + Number(theirAvg).toFixed(2));
  return sig;
}

/* This trader's position in this ticker — their own key first, and failing
 * that the ONE open trade in the name, whoever's it is. Null when it's
 * ambiguous, because two trades in the same ticker is exactly when a guess
 * sells the wrong man's contracts. */
function findHeld(held, who, symbol) {
  const exact = (held || {})[posKey(who, symbol)];
  if (exact) return exact;
  const ks = Object.keys(held || {}).filter(k => keySymbol(k) === String(symbol || "").toUpperCase());
  return ks.length === 1 ? held[ks[0]] : null;
}
function findHeldKey(held, who, symbol) {
  if ((held || {})[posKey(who, symbol)]) return posKey(who, symbol);
  const ks = Object.keys(held || {}).filter(k => keySymbol(k) === String(symbol || "").toUpperCase());
  return ks.length === 1 ? ks[0] : null;
}

/* A LOADING notice never buys anything — that's the room's own rule. But it is
 * the only place the contract gets named when their entry comes in two
 * messages, so it gets kept until the price turns up. */
async function rememberLoading(sig, author) {
  if (sig.action !== "PREPARE" || !sig.symbol) return;
  const st = await guardState();
  st.loaded = st.loaded || {};
  st.loaded[String(sig.caller || author || "").toLowerCase()] = {
    symbol: sig.symbol, side: sig.side, strike: sig.strike,
    expiry: sig.expiry, ts: Date.now() };
  await saveGuardState(st);
}

/* "Filled 3.95 starters" is an order with the contract missing. It was in the
 * "Loading 205 calls Friday expiration on NVDA" the same admin posted a few
 * minutes before, so that's where it comes from.
 *
 * Same rule as everywhere else in this file: if it can't be worked out for
 * certain, nothing is sent and you're told why. A price with no contract behind
 * it is the single easiest way to buy the wrong thing. Mirrors
 * guards.resolve_loaded. */
async function resolveLoaded(sig, author, cfg) {
  if (sig.symbol || !sig.needs_loaded) return sig;
  cfg = cfg || {};
  const st = await guardState();
  const loaded = st.loaded || {};
  const who = String(sig.caller || author || "").toLowerCase();
  const keys = Object.keys(loaded);
  let key = Object.prototype.hasOwnProperty.call(loaded, who) ? who : null;
  // Nobody else has loaded anything, so there's only one call it could possibly
  // be. Still refused below if it's stale or incomplete.
  if (key === null && keys.length === 1 && (!who || !keys[0])) key = keys[0];
  const cand = key === null ? null : loaded[key];
  if (!cand) {
    sig.why = "they posted a fill price on its own and I can't find the LOADING " +
              "call that goes with it — nothing was sent";
    return sig;
  }
  const win = parseFloat((cfg.guards || {}).loading_window_seconds);
  const windowS = isNaN(win) ? 1800 : win;
  const age = (Date.now() - cand.ts) / 1000;
  if (windowS && age > windowS) {
    sig.why = "they posted a fill price on its own, but the last LOADING call " +
              "was " + Math.round(age / 60) + " minutes ago — too long ago to " +
              "assume it's the same trade, so nothing was sent";
    return sig;
  }
  if (!cand.symbol || cand.strike === null || cand.strike === undefined || !cand.side) {
    sig.why = "they posted a fill price on its own, and the LOADING call before " +
              "it didn't name a full contract either — nothing was sent";
    return sig;
  }
  if (cand.used) {
    // A second price on the same loading call is them averaging into the trade
    // they already put you in — "Filled 4.20 more" after "Filled 3.95
    // starters". Sent down the averaging path, which refuses it outright unless
    // you switched averaging on.
    sig.action = "ADD"; sig.needs_add = true; sig.symbol = cand.symbol;
    return await resolveAdd(sig, author, cfg);
  }
  sig.symbol = cand.symbol; sig.side = cand.side;
  sig.strike = cand.strike; sig.expiry = cand.expiry;
  st.loaded[key].used = 1;
  await saveGuardState(st);
  sig.fire = true;
  sig.why = "entry: " + human(sig) + " — they posted the price on its own, and " +
            "that's the contract " + (sig.caller || author || "they") + " loaded";
  return sig;
}

/* "all out of AMD" never says which contract, and neither does "exited and
 * back in" — the room already knows which one. A broker doesn't, so the
 * missing pieces come from what you're actually holding. */
async function fillFromPosition(sig, author) {
  const st = await guardState();
  const who = String(sig.caller || author || "").toLowerCase();
  const p = findHeld(st.positions, who, sig.symbol);
  if (!p) return sig;
  if (sig.strike === null || sig.strike === undefined) sig.strike = p.strike;
  if (!sig.side) sig.side = p.side;
  if (!sig.expiry) sig.expiry = p.expiry;
  // If you averaged in, you hold more than one contract, and "all out" means
  // all of them. Selling the one the parser assumed would leave you holding the
  // rest without knowing it.
  if (sig.action === "CLOSE") sig.qty = Math.max(1, parseInt(p.qty || 1, 10) || 1);
  return sig;
}

async function guardRecord(sig, cfg, author) {
  const g = Object.assign({}, GUARD_DEFAULTS, cfg.guards || {});
  const now = Date.now();
  const st = await guardState();
  const who = String(sig.caller || author || "");

  // Anything older about this ticker is history now. Without this, the room
  // getting out of SPY and straight back in would look like a duplicate call
  // and you'd sit out the rest of the move. Double-buying is stopped by the
  // position tracker instead, which is the right tool for it.
  for (const k of Object.keys(st.recent)) {
    if (k.split("|")[1] === sig.symbol) delete st.recent[k];
  }
  st.recent[signalKey(sig)] = now;
  const cut = now - Math.max(g.dedupe_seconds, 300) * 1000;
  for (const k of Object.keys(st.recent)) if (st.recent[k] < cut) delete st.recent[k];

  const k = posKey(who, sig.symbol);
  if (sig.action === "OPEN") {
    // Written down for the echo guard: this exact call has now run today.
    if (sig.limit !== null && sig.limit !== undefined) {
      st.echoes = st.echoes || {};
      st.echoes[echoKey(sig, who)] = now;
    }
    // The author is in the KEY now, so a later symbol-less trim from the same
    // admin pins to the position they actually opened — and two admins can be
    // in the same ticker without stepping on each other's bookkeeping.
    // pending: the order has gone out, nobody has sold to you yet. Your entry
    // sits on the bid, so this is the normal state for a while and sometimes
    // the only state it ever reaches. The bridge is what decides it filled;
    // syncFills in background.js clears this when it says so.
    st.positions[k] = { side: sig.side, strike: sig.strike,
                        expiry: sig.expiry, ts: now, author: who,
                        qty: parseInt(sig.qty || 1, 10) || 1, adds: 0,
                        pending: true };
    st.lastFire = now;
    st.count += 1;
  } else if (sig.action === "ADD") {
    // More contracts of the same thing. The count is what an exit sells, and
    // the add count is what stops this happening all day.
    const pk = findHeldKey(st.positions, who, sig.symbol);
    const p = pk ? st.positions[pk] : null;
    if (p) {
      p.qty = (parseInt(p.qty || 1, 10) || 1) + (parseInt(sig.qty || 1, 10) || 1);
      p.adds = (parseInt(p.adds || 0, 10) || 0) + 1;
      p.ts = now;
      // The add is a resting bid like any other entry, so the extra contracts
      // aren't yours yet either. The bridge corrects this count when it fills,
      // or when it doesn't.
      p.pending = true;
    }
    st.lastFire = now;
    st.count += 1;
  } else if (sig.action === "TRIM") {
    // Sold some, kept the rest. The bridge knows the exact count afterwards
    // and syncFills writes it back; the subtraction here just keeps the popup
    // honest in the seconds in between.
    const pk = findHeldKey(st.positions, who, sig.symbol);
    const p = pk ? st.positions[pk] : null;
    if (p) p.qty = Math.max(0, (parseInt(p.qty || 1, 10) || 1) -
                               (parseInt(sig.qty || 1, 10) || 1)) || p.qty;
  } else if (sig.action === "CLOSE") {
    const pk = findHeldKey(st.positions, who, sig.symbol) || k;
    const held = st.positions[pk] || {};
    delete st.positions[pk];
    if (sig.reenter) {
      // Sold and bought straight back into the same contract. The tracker has
      // to know you're still in it, or the room's next "all out" gets refused
      // for having nothing to sell.
      st.positions[pk] = {
        side: sig.side || held.side,
        strike: (sig.strike === null || sig.strike === undefined)
                ? held.strike : sig.strike,
        expiry: sig.expiry || held.expiry, ts: now,
        author: who || held.author || "",
        // Straight back in on the same size you just sold — as a bid, so it's
        // pending until the bridge says somebody sold to you.
        qty: parseInt(held.qty || 1, 10) || 1, adds: 0, pending: true };
    }
  }
  await saveGuardState(st);
  return st;
}

/* Real-money buys are pinned to ONE contract — that's a sizing safety, not a
 * filter, and it stays until he raises it on purpose. Sells are never capped
 * down: an exit has to be allowed to sell everything you're holding, or
 * you're quietly still in the trade. Test mode never calls this. */
function clampQty(wanted, cfg, action) {
  const n = Math.max(1, parseInt(wanted || 1, 10) || 1);
  const a = String(action || "").toUpperCase();
  if (a === "CLOSE" || a === "TRIM") return n;
  return 1;
}
