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
  max_message_age_seconds: 20,
  // A3 - auto-follow "same ones" re-entries once the contract resolves. Safe:
  // it never doubles up on a contract you already hold. false = log only.
  follow_reentries: true
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
  // Old saved settings pinned a conservative 15:45 options close; options
  // really trade to 4:00 (indices to 4:15, handled below). Lift the stale value
  // so end-of-day entries aren't refused. One line, the single trading gate.
  if (g.close_time === "15:45") g.close_time = "16:00";
  const now = Date.now();
  const st = await guardState();

  // No manual ON/OFF any more (his ask, 8/17): a room tab being open in the
  // browser IS the switch — content.js only reads while that tab exists, and
  // the old toggle was a second, independent switch that could be left OFF
  // by accident (8/17: a self-update reload waited for it to be OFF, then
  // nothing ever turned it back ON — 90 minutes of every room silently
  // skipped). One less state to get stuck in.
  const chans = (cfg.channel_ids || []).map(String).filter(Boolean);
  if (chans.length && !chans.includes(String(ctx.channelId)))
    return { allowed: false, reason: "that message wasn't in a channel you're listening to" };

  const names = (cfg.author_names || []).map(a => String(a).toLowerCase()).filter(Boolean);
  if (names.length && !names.includes(String(ctx.author || "").toLowerCase()))
    return { allowed: false, reason: ctx.author + " isn't on your trusted-poster list, so it was ignored" };

  const admins = (cfg.follow_admins || []).map(a => String(a).toLowerCase()).filter(Boolean);
  if (admins.length && sig.caller && !admins.includes(String(sig.caller).toLowerCase()))
    return { allowed: false, reason: "that was " + sig.caller + "'s call, and you're only following " + (cfg.follow_admins || []).join(", ") };

  // Whop's feed delivers with 30-60s of built-in lag (poll cycle + post
  // rendering), so the 20s Discord rule was refusing EVERY Whop entry as
  // stale — including the first real futures call after Topstep went live
  // ("Short Nq 29640", 41s old, 8/18). Whop gets a lag-aware 90s window;
  // Discord keeps the tight one.
  const _maxAge = (String(ctx.platform || "") === "whop" ? 90
                   : g.max_message_age_seconds);
  const age = (now - (ctx.postedAt || now)) / 1000;
  if (_maxAge && age > _maxAge)
    return { allowed: false, reason: "that call is " + Math.round(age) + " seconds old — too stale to chase" };

  // A manual test trade is allowed to run any time — it's how he proves the
  // pipeline end to end, and blocking it at 10PM makes the button useless. It
  // routes to paper only, so the worst case out of hours is Webull not filling.
  const isTest = !!(sig.test || ctx.test ||
                    /^🧪/.test(String(sig.caller || ctx.author || "")));
  if (!isTest && g.regular_hours_only && (sig.action === "OPEN" || sig.action === "ADD")) {
    const t = etNow();
    const mins = t.h * 60 + t.m;
    if (sig.kind === "future") {
      // Futures trade nearly 24 hours — Felony shorts NQ at 10PM on a
      // Sunday, and that's a real entry. The futures week: opens Sunday
      // 6PM ET, closes Friday 5PM ET, with a 5-6PM ET maintenance break
      // every day. Only those gaps refuse an entry.
      const shut =
        (t.wd === "Sat") ||
        (t.wd === "Sun" && mins < 18 * 60) ||
        (t.wd === "Fri" && mins >= 17 * 60) ||
        (mins >= 17 * 60 && mins < 18 * 60);
      if (shut)
        return { allowed: false, reason: "the futures market itself is shut " +
          "right now (daily 5-6PM ET break, or the weekend gap Fri 5PM to " +
          "Sun 6PM) — the order would just be rejected" };
    } else {
      if (t.wd === "Sat" || t.wd === "Sun")
        return { allowed: false, reason: "it's the weekend — the market is shut" };
      // Equity & ETF options (SPY, QQQ, TSLA, NVDA...) close at 4:00 ET. The
      // cash-settled broad indices (SPX, NDX, RUT, XSP, VIX) trade to 4:15 ET,
      // so those get the later bell. Open is the same 9:30 for all.
      const LATE = /^(SPX|SPXW|XSP|NDX|NDXP|RUT|RUTW|VIX|VIXW|MRUT|XND)$/;
      const closeStr = LATE.test(String(sig.symbol || "").toUpperCase())
        ? "16:15" : g.close_time;
      if (mins < hm(g.open_time) || mins > hm(closeStr))
        return { allowed: false, reason: "it's " + String(t.h).padStart(2, "0") + ":" +
          String(t.m).padStart(2, "0") + " ET — new option trades are only allowed between " +
          g.open_time + " and " + closeStr };
    }
  }

  // What you're holding is checked before anything else, because "you're
  // already in AMD" tells you far more than "that looked like a repeat".
  // Checked per TRADER now: Brett being in SPY doesn't stop Unraveler's SPY
  // call — those are two different trades and both should run.
  const who = String(sig.caller || ctx.author || "").toLowerCase();
  // COEXISTENCE (8/26): an ownerless position is G's OWN trade — his
  // Market Sniper tool works the same account. His QQQ scalp must not
  // block a room's QQQ call; they're two different trades by design.
  // Only the SAME TRADER already being in the name blocks a re-entry.
  const already = st.positions[posKey(who, sig.symbol)];
  if (sig.action === "OPEN" && already) {
    // BETTER-AVERAGE ADD (8/26, his call: "we can double if the avg is
    // better"). Same trader, same CONTRACT, position actually filled, and
    // the new call's price at least 1% under what you PAID — then this is
    // an average-down, not a double: it converts to an ADD for one more
    // contract (the book blends the average and walks the stop to it).
    // One better-average add per position — twice is martingale, not
    // averaging. Note: if the first entry was strike-translated, the paid
    // price belongs to the translated contract and this compare is
    // conservative; a mismatch just leaves a resting bid that never fills.
    const heldPos = st.positions[posKey(who, sig.symbol)];
    const samePaper = heldPos && heldPos.strike === sig.strike &&
      String(heldPos.expiry || "") === String(sig.expiry || "") &&
      heldPos.side === sig.side;
    const paid = heldPos && heldPos.fill != null ? Number(heldPos.fill) : null;
    if (samePaper && !heldPos.pending && paid && sig.limit != null &&
        Number(sig.limit) < paid * 0.99 && (heldPos.adds || 0) < 1) {
      sig.action = "ADD";
      return { allowed: true, reason: "already in " + sig.symbol + " at " +
        paid + ", but their re-fire at " + sig.limit + " IMPROVES the " +
        "average — buying one more as an ADD" };
    }
    return { allowed: false, reason: "you're already in " + sig.symbol +
      " from their earlier call — this one would double you up" +
      (samePaper && paid ? " (and " + sig.limit + " doesn't beat your " +
       paid + " average)" : "") };
  }

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

  if (sig.action === "CLOSE" || sig.action === "TRIM") {
    // Micro/full futures siblings are ONE position (8/21: the room's "ALL
    // OUT ES" died right here because the book holds it as MES — the same
    // NQ/MNQ lesson, on the exit side). If we hold the sibling, the exit is
    // for it: rewrite the symbol so everything downstream matches.
    const _sibs = { ES: "MES", MES: "ES", NQ: "MNQ", MNQ: "NQ",
                    YM: "MYM", MYM: "YM", RTY: "M2K", M2K: "RTY",
                    CL: "MCL", MCL: "CL", GC: "MGC", MGC: "GC" };
    const _sib = _sibs[sig.symbol];
    if (_sib && !st.positions[posKey(who, sig.symbol)] &&
        !Object.keys(st.positions).some(k => keySymbol(k) === sig.symbol) &&
        Object.keys(st.positions).some(k => keySymbol(k) === _sib)) {
      sig.symbol = _sib;
    }
    if (!st.positions[posKey(who, sig.symbol)] &&
        !Object.keys(st.positions).some(k => keySymbol(k) === sig.symbol))
      // At most brokers a sell with nothing to sell isn't a no-op — it opens
      // a short. Never send it.
      return { allowed: false, reason: "you're not in " + sig.symbol +
        ", so there's nothing to " + (sig.action === "TRIM" ? "trim" : "close") +
        " — the order was not sent" };
  }

  const last = st.recent[signalKey(sig)];
  if (last && (now - last) / 1000 < g.dedupe_seconds)
    return { allowed: false, reason: "already acted on that exact call " +
      Math.round((now - last) / 1000) + "s ago" };

  // No time cooldown, on his word: "don't have cool downs. Just have a
  // verification, and if it's exactly the same thing, just skip it." A blunt
  // timer dropped a real NVDA call because a QQQ order fired 3s earlier — the
  // exact miss he can't afford in a fast room. The only thing that stops a
  // fire now is that it's genuinely a REPEAT of one already acted on: the echo
  // guard above (same contract + same price, all day) and the exact-call
  // dedupe above (identical signal). Different calls always go through.

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
  let pick = pickHeld(held, who);

  // Second try (8/11/26): the trim came from an admin who LOADED a contract
  // earlier — "Midas: Loaded $Spy 773p ... Midas: 11%". His positions all
  // read owner "?" after a pickup, so the name match fails, but his own
  // loading call says exactly which ticker he trades. One unambiguous match
  // only, never a guess between two. Mirrors guards.resolve_symbol.
  if (!pick) {
    const ld = (st.loaded || {})[who] || {};
    const ldSym = String(ld.symbol || "").toUpperCase();
    if (ldSym) {
      // Same trader (or an unattributed pickup) only — a loaded ticker must
      // never resolve onto ANOTHER trader's position (8/19: KingBeeAri had
      // loaded AAPL, so his bare "10%" grabbed stockguy007's AAPL swing).
      const cands = keys.filter(k => keySymbol(k) === ldSym &&
        (keyWho(k) === who || keyWho(k) === "?") &&
        // ...but never G's own hand trade (9/2): an adopted record with
        // no trader on it, or Gian's name, is his — the loading call
        // proves the trader named the ticker, not that the position is
        // theirs. Same rule as pickHeld.
        !((held[k] || {}).adopted &&
          ["?", "gian", ""].includes(String((held[k] || {}).who || "?").toLowerCase())));
      if (cands.length === 1) pick = cands[0];
    }
  }

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
  // Who a record belongs to: the key's owner, or — for a bridge-adopted
  // "?|SYM" record — the name the bridge put on it (the trader whose call
  // the bot was in when it lost track, or "Gian" for a hand trade).
  const ownerOf = (k) => {
    const kw = keyWho(k);
    if (kw && kw !== "?") return kw;
    const p = held[k] || {};
    return String(p.who || "?").toLowerCase();
  };
  const theirs = keys.filter(k => who && ownerOf(k) === who);
  // Their own, and when they hold several, the NEWEST — Aristotle runs a
  // swing and a scalp at once, and his bare "12%" / "Out" is always about
  // the trade he just opened, not the swing from Tuesday.
  if (theirs.length >= 1) {
    theirs.sort((a, b) => ((held[b] || {}).ts || 0) - ((held[a] || {}).ts || 0));
    return theirs[0];
  }
  if (keys.length === 1) {
    const k = keys[0];
    const owner = ownerOf(k);
    const p = held[k] || {};
    // A HAND TRADE IS NEVER "THE ONLY POSITION" (9/2 14:54): the only
    // record was G's own SPY 767C 9/9, adopted "?" from the account, and a
    // caller's symbol-less "I took my $126 L" was matched to it and SOLD it
    // (-$27) — a loss the caller took, not him. An adopted record with no
    // trader on it (or Gian's name) belongs to nobody in the room; a bare
    // exit can't name it. Named ones (a bot trade re-adopted after a
    // restart) still match their own trader above.
    if (p.adopted && (owner === "?" || owner === "gian")) return null;
    if (!who || owner === "?" || owner === who) return k;
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
    // BOKA/RWGates dialect (9/2): "added $DRAM $57 calls 9/18" is how
    // Jonny ANNOUNCES an entry — "added" is his buy verb. A full contract
    // (strike + side + expiry) you are NOT in is an entry, not an average-
    // in. A bare "added to SPY" with no contract still refuses: nothing
    // says which strike.
    if (sig.strike != null && sig.side && sig.expiry) {
      sig.action = "OPEN";
      sig.needs_add = false;
      sig.qty = 1;
      sig.fire = true;
      sig.why = "entry: OPEN " + sig.symbol + " " + sig.strike +
                (String(sig.side).startsWith("C") ? "C" : "P") + " " + sig.expiry +
                " (their \"added\" is an entry — you're not in it)";
      return sig;
    }
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
  // Four hours, not thirty minutes. Midas rests his bid at his price and
  // waits: day one live he posted Loaded before 10:20 and "Filled at 1.46"
  // at 11:56, and the 30-minute window threw away his only real trade of
  // the day (he trimmed it +17% an hour later). The Loaded call names the
  // full contract, so a late fill is still unambiguous; four hours spans a
  // morning of waiting without reaching back into yesterday.
  const windowS = isNaN(win) ? 14400 : win;
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
  if (sig.named_symbol && String(sig.named_symbol).toUpperCase() !== String(cand.symbol).toUpperCase()) {
    // "In meta 6.10 avg" while their last load was TSLA — they named a ticker
    // that disagrees with the load. Buying the load buys the WRONG ticker (the
    // Aug 4 TSLA-for-META bug). Refuse.
    sig.why = "they said " + String(sig.named_symbol).toUpperCase() + " but the " +
              "last LOADING I have for them is " + cand.symbol + " — I won't buy " +
              "a different ticker than the one they named, so nothing was sent";
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

/* A3 - "SAME ONES" re-entry. The parser flags reenter and usually the
 * spelled-out strike/side, but the line rarely carries the expiry. Fill it
 * from what this caller holds, or last called, in that symbol, then fire the
 * re-buy - but only once the contract fully resolves AND you are not already
 * in it (that would be a double-up). Otherwise hold with a plain reason; never
 * a silent drop. Off when follow_reentries is false. */
async function resolveReenter(sig, author, cfg) {
  if (!sig.reenter || sig.action !== "OPEN") return sig;
  const g = Object.assign({}, GUARD_DEFAULTS, (cfg && cfg.guards) || {});
  const sym = String(sig.symbol || "").toUpperCase();
  if (g.follow_reentries === false) {
    sig.fire = false; sig.needs_position = false;
    sig.why = 'a re-entry ("same ones") - follow_reentries is off, nothing sent';
    return sig;
  }
  const st = await guardState();
  const who = String(sig.caller || author || "").toLowerCase();
  const last = st.lastCall || {};
  let ref = st.positions[posKey(who, sym)] || last[posKey(who, sym)] || null;
  if (!ref && sym) {
    const cand = Object.keys(st.positions).concat(Object.keys(last))
      .filter(x => keySymbol(x) === sym);
    cand.sort((a, b) => (((st.positions[b] || last[b] || {}).ts) || 0) -
                        (((st.positions[a] || last[a] || {}).ts) || 0));
    if (cand.length) ref = st.positions[cand[0]] || last[cand[0]];
  }
  if (ref) {
    if (sig.side == null) sig.side = ref.side;
    if (sig.strike == null) sig.strike = ref.strike;
    if (!sig.expiry) sig.expiry = ref.expiry;
    if (sig.limit == null && ref.limit != null) sig.limit = ref.limit;
  }
  sig.needs_position = false;
  if (!sig.symbol || sig.strike == null || !sig.side || !sig.expiry) {
    sig.fire = false;
    sig.why = 'a "same ones" re-entry I could not complete - no earlier ' + sym +
              " call on record to copy the contract from";
    return sig;
  }
  const cur = st.positions[posKey(who, sym)];
  if (cur && String(cur.side) === String(sig.side) &&
      Number(cur.strike) === Number(sig.strike) &&
      String(cur.expiry || "") === String(sig.expiry || "")) {
    sig.fire = false;
    sig.why = 'a "same ones" re-entry but you are already in ' + sym + " " +
              sig.strike + (sig.side === "CALLS" ? "C" : "P") + " - not doubling up";
    return sig;
  }
  sig.fire = true;
  sig.why = "re-entry: " + sym + " " + sig.strike +
            (sig.side === "CALLS" ? "C" : "P") +
            (sig.expiry ? " " + sig.expiry : "") +
            (sig.limit == null ? "" : " @ " + sig.limit) +
            " - same contract they last called";
  return sig;
}

async function guardRecord(sig, cfg, author, isTest) {
  const g = Object.assign({}, GUARD_DEFAULTS, cfg.guards || {});
  const now = Date.now();
  const st = await guardState();
  // A test or manual trade is assumed filled the instant it goes out — his
  // rule: don't leave it sitting on the bid waiting for a seller that a dry run
  // will never produce. So its position is written down as owned, not pending.
  const assumeFilled = !!(isTest || sig.test ||
                          /^(🧪|🎯)/.test(String(sig.caller || author || "")));
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
                        // The room this was opened in, and whether that room is
                        // LIVE — so a one-click ✕ closes it in the SAME mode it
                        // was opened. Closing a live position with a paper order
                        // would leave the real one open; this prevents that.
                        channelId: sig.channelId || "",
                        live: !!sig.live, kind: sig.kind || "",
                        swing: !!sig.swing,   // display only (8/17)
                        pending: !assumeFilled };
    // A3 - remember this caller's contract so a later "same ones" re-entry can
    // copy the expiry even after the position is closed. Bounded to 60 entries.
    st.lastCall = st.lastCall || {};
    st.lastCall[k] = { side: sig.side, strike: sig.strike, expiry: sig.expiry,
                       limit: (sig.limit == null ? null : sig.limit), ts: now };
    { const lk = Object.keys(st.lastCall);
      if (lk.length > 60) { lk.sort((a, b) => (st.lastCall[a].ts || 0) - (st.lastCall[b].ts || 0));
        for (const d of lk.slice(0, lk.length - 60)) delete st.lastCall[d]; } }
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
      // or when it doesn't — unless it's a test/manual, assumed filled at once.
      p.pending = !assumeFilled;
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

/* The undo for guardRecord, run when an entry the bridge was asked to place
 * comes back FAILED (refused, unreachable, no buying power, wrong account).
 * The position was written down BEFORE the order went out so a mid-send crash
 * couldn't double-fire — but if the order definitively did NOT go out, that
 * write is a PHANTOM: it makes the bot think you're holding something you
 * never bought, which then blocks the next real entry ("already in AMD, would
 * double you up") and makes trims chase a position that isn't there. This is
 * exactly what wedged AMD/MNQ after their orders were rejected. So a failed
 * OPEN is deleted, and a failed ADD gives its contracts back. Only touches a
 * still-PENDING write — never a position the bridge already confirmed filled. */
async function guardUnrecord(sig, author) {
  if (!sig || (sig.action !== "OPEN" && sig.action !== "ADD")) return;
  const st = await guardState();
  const who = String(sig.caller || author || "").toLowerCase() || "?";
  const pk = findHeldKey(st.positions, who, sig.symbol) ||
             posKey(who, sig.symbol);
  const p = st.positions[pk];
  if (!p) return;
  // Never unwind a fill the bridge already confirmed — only the resting/assumed
  // write this same message just made.
  if (p.pending === false && sig.action === "OPEN" &&
      !(sig.test || /^(🧪|🎯)/.test(who))) {
    // A confirmed live fill — leave it. (A failed CLOSE later is the way out.)
  }
  if (sig.action === "OPEN") {
    delete st.positions[pk];
  } else {   // ADD — hand the contracts back, undo the add count
    const back = parseInt(sig.qty || 1, 10) || 1;
    p.qty = Math.max(0, (parseInt(p.qty || 1, 10) || 1) - back);
    p.adds = Math.max(0, (parseInt(p.adds || 0, 10) || 0) - 1);
    if (p.qty <= 0) delete st.positions[pk];
  }
  if (st.count > 0) st.count -= 1;   // the failed order shouldn't count against the day
  await saveGuardState(st);
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
