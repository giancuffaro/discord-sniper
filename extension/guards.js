/* guards.js — the brakes, browser side. Mirrors guards.py.
 *
 * State lives in chrome.storage.local, not in a variable, because a Manifest V3
 * service worker gets shut down whenever Chrome feels like it. If the counters
 * and the position tracker lived in memory, your "6 trades a day" cap would
 * quietly reset every time the worker napped — and you'd find out on the worst
 * possible day.
 */

const GUARD_DEFAULTS = {
  max_qty: 1,
  // 0 or less means no daily limit at all.
  max_trades_per_day: 6,
  // Follow them when they add to a position and post a new average. Off means
  // the add is logged and nothing is sent.
  average_in: false,
  // A ceiling on that, because adding three more times on the way down is how a
  // $400 trade quietly becomes a $1,600 one.
  max_adds_per_position: 2,
  cooldown_seconds: 5,
  dedupe_seconds: 120,
  regular_hours_only: true,
  open_time: "09:30",
  // New trades are allowed right through to the closing bell. Exits are not
  // time-boxed at all — see guardCheck, which only applies this to OPEN.
  close_time: "16:00",
  max_message_age_seconds: 20,
  // Once entries are done for the day, switch OFF on its own — but only
  // once you're flat. See sessionSweep() in background.js.
  auto_safe_after_close: true
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

async function guardState() {
  const { guardState: st } = await chrome.storage.local.get("guardState");
  const day = todayET();
  if (st && st.day === day) {
    st.recent = st.recent || {};
    st.positions = st.positions || {};
    st.loaded = st.loaded || {};
    return st;
  }
  // A new day resets the counter, but NOT the positions — an option you bought
  // yesterday is still sitting in your account this morning. Loading notices do
  // reset: yesterday's "getting ready on NVDA" means nothing this morning.
  return { day, count: 0, lastFire: 0, recent: {}, loaded: {},
           positions: (st && st.positions) || {} };
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
  if (sig.action === "OPEN" && st.positions[sig.symbol])
    return { allowed: false, reason: "you're already in " + sig.symbol +
      " from their earlier call — this one would double you up" };

  if (sig.action === "CLOSE" && !st.positions[sig.symbol])
    // At most brokers a sell with nothing to sell isn't a no-op — it opens a
    // short. Never send it.
    return { allowed: false, reason: "you're not in " + sig.symbol +
      ", so there's nothing to close — the order was not sent" };

  const last = st.recent[signalKey(sig)];
  if (last && (now - last) / 1000 < g.dedupe_seconds)
    return { allowed: false, reason: "already acted on that exact call " +
      Math.round((now - last) / 1000) + "s ago" };

  if (sig.action === "OPEN" || sig.action === "ADD") {
    if ((now - st.lastFire) / 1000 < g.cooldown_seconds)
      return { allowed: false, reason: "still in the " + g.cooldown_seconds +
        "s cooldown after the last fire" };
    // 0 means you took the daily limit off on purpose.
    if (g.max_trades_per_day > 0 && st.count >= g.max_trades_per_day)
      return { allowed: false, reason: "you've hit your limit of " +
        g.max_trades_per_day + " trades for today" };
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
  const names = Object.keys(held);
  if (!names.length) {
    sig.why = "a trim with no ticker in it, and you're not in anything — nothing to close";
    return sig;
  }
  const who = String(sig.caller || author || "").toLowerCase();
  const theirs = names.filter(n =>
    who && String(held[n].author || "").toLowerCase() === who);

  let pick = null;
  if (theirs.length === 1) pick = theirs[0];
  else if (!theirs.length && names.length === 1) {
    // Only one thing open, so it's tempting to just take it. But if that
    // position was opened by a different admin, a trim from this one is about
    // something you never got into — closing the other guy's trade on it is
    // exactly the mistake this whole function exists to avoid.
    const only = names[0];
    const owner = String(held[only].author || "").toLowerCase();
    if (!who || !owner || owner === who) pick = only;
  }

  if (!pick) {
    const what = names.slice().sort().map(n =>
      n + (held[n].author ? " (" + held[n].author + "'s call)" : "")).join(", ");
    sig.why = "a trim with no ticker in it. You're in " + what + ", and this " +
      "came from " + (sig.caller || author || "somebody I couldn't name") +
      " — I can't tell which one they meant, so nothing was sent. Close it in " +
      "the Webull app if you want out.";
    return sig;
  }
  sig.symbol = pick;
  sig.fire = true;
  sig.why = "closing " + pick + " on their first trim — they didn't name it, " +
            "but it's the position " + (sig.caller || author || "they") + " put you in";
  return sig;
}

/* Which of your open positions did this admin mean? Their own first, and the
 * only one open second — but never somebody else's. Null when it can't be sure,
 * and being sure is the whole point. Mirrors guards._pick_held. */
function pickHeld(held, who) {
  const names = Object.keys(held || {});
  if (!names.length) return null;
  const theirs = names.filter(n =>
    who && String(held[n].author || "").toLowerCase() === who);
  if (theirs.length === 1) return theirs[0];
  if (!theirs.length && names.length === 1) {
    const only = names[0];
    const owner = String(held[only].author || "").toLowerCase();
    if (!who || !owner || owner === who) return only;
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
  const g = Object.assign({}, GUARD_DEFAULTS, (cfg || {}).guards || {});
  const who = String(sig.caller || author || "").toLowerCase();

  if (!g.average_in) {
    sig.why = "they added to their " + (sig.symbol || "position") + " and their " +
              "average moved — averaging in is switched off, so nothing was " +
              "sent. You're still in it.";
    return sig;
  }

  const st = await guardState();
  const held = st.positions || {};
  if (!sig.symbol) sig.symbol = pickHeld(held, who);
  if (!sig.symbol) {
    sig.why = "they added to a position and didn't name it, and I can't tell " +
              "which one they meant — nothing was sent";
    return sig;
  }
  const pos = held[sig.symbol];
  if (!pos) {
    sig.why = "they added to their " + sig.symbol + ", but you're not in it — " +
              "there's nothing to average into";
    return sig;
  }
  const allowed = ((cfg || {}).allowed_symbols || []).map(x => String(x).toUpperCase());
  if (allowed.length && !allowed.includes(sig.symbol)) {
    sig.why = sig.symbol + " isn't on your allowed-symbols list";
    return sig;
  }
  const adds = parseInt(pos.adds || 0, 10) || 0;
  if (g.max_adds_per_position >= 0 && adds >= g.max_adds_per_position) {
    sig.why = "they added to " + sig.symbol + " again, but you've already " +
              "averaged in " + adds + (adds === 1 ? " time" : " times") +
              " on it — that's your limit, so nothing was sent";
    return sig;
  }
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
  const allowed = (cfg.allowed_symbols || []).map(x => String(x).toUpperCase());
  if (allowed.length && !allowed.includes(cand.symbol)) {
    sig.why = cand.symbol + " isn't on your allowed-symbols list";
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
async function fillFromPosition(sig) {
  const st = await guardState();
  const p = st.positions[sig.symbol];
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

  if (sig.action === "OPEN") {
    // The author is kept so a later symbol-less trim from the same admin can
    // be pinned to the position they actually opened.
    // pending: the order has gone out, nobody has sold to you yet. Your entry
    // sits on the bid, so this is the normal state for a while and sometimes
    // the only state it ever reaches. The bridge is what decides it filled;
    // syncFills in background.js clears this when it says so.
    st.positions[sig.symbol] = { side: sig.side, strike: sig.strike,
                                 expiry: sig.expiry, ts: now, author: who,
                                 qty: parseInt(sig.qty || 1, 10) || 1, adds: 0,
                                 pending: true };
    st.lastFire = now;
    st.count += 1;
  } else if (sig.action === "ADD") {
    // One more contract of the same thing. The count is what an exit sells, and
    // the add count is what stops this happening all day.
    const p = st.positions[sig.symbol];
    if (p) {
      p.qty = (parseInt(p.qty || 1, 10) || 1) + (parseInt(sig.qty || 1, 10) || 1);
      p.adds = (parseInt(p.adds || 0, 10) || 0) + 1;
      p.ts = now;
      // The add is a resting bid like any other entry, so the extra contract
      // isn't yours yet either. The bridge corrects this count when it fills,
      // or when it doesn't.
      p.pending = true;
    }
    st.lastFire = now;
    st.count += 1;
  } else if (sig.action === "CLOSE") {
    const held = st.positions[sig.symbol] || {};
    delete st.positions[sig.symbol];
    if (sig.reenter) {
      // Sold and bought straight back into the same contract. The tracker has
      // to know you're still in it, or the room's next "all out" gets refused
      // for having nothing to sell.
      st.positions[sig.symbol] = {
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

/* max_qty caps what you BUY. An exit has to be allowed to sell everything
 * you're holding — capping that at one contract after you've averaged in would
 * leave you quietly still in the trade. */
function clampQty(wanted, cfg, action) {
  const g = Object.assign({}, GUARD_DEFAULTS, cfg.guards || {});
  const n = Math.max(1, parseInt(wanted || 1, 10) || 1);
  if (String(action || "").toUpperCase() === "CLOSE") return n;
  return Math.min(n, g.max_qty);
}
