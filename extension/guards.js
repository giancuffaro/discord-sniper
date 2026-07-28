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
  max_trades_per_day: 6,
  cooldown_seconds: 5,
  dedupe_seconds: 120,
  regular_hours_only: true,
  open_time: "09:30",
  close_time: "15:45",
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

async function guardState() {
  const { guardState: st } = await chrome.storage.local.get("guardState");
  const day = todayET();
  if (st && st.day === day) {
    st.recent = st.recent || {};
    st.positions = st.positions || {};
    return st;
  }
  // A new day resets the counter, but NOT the positions — an option you bought
  // yesterday is still sitting in your account this morning.
  return { day, count: 0, lastFire: 0, recent: {},
           positions: (st && st.positions) || {} };
}

async function saveGuardState(s) {
  await chrome.storage.local.set({ guardState: s });
}

/* Returns {allowed, reason}. Reasons are written for a human at 9:31am. */
async function guardCheck(sig, ctx, cfg) {
  const g = Object.assign({}, GUARD_DEFAULTS, cfg.guards || {});
  const now = Date.now();
  const st = await guardState();

  if (cfg.stopped)
    return { allowed: false, reason: "you hit STOP, so nothing fires until you clear it" };
  if (cfg.armed === false)
    return { allowed: false, reason: "the extension is on SAFE — flip it to ARMED to trade" };

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

  if (g.regular_hours_only && sig.action === "OPEN") {
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

  if (sig.action === "OPEN") {
    if ((now - st.lastFire) / 1000 < g.cooldown_seconds)
      return { allowed: false, reason: "still in the " + g.cooldown_seconds +
        "s cooldown after the last fire" };
    if (st.count >= g.max_trades_per_day)
      return { allowed: false, reason: "you've hit your limit of " +
        g.max_trades_per_day + " trades for today" };
  }

  return { allowed: true, reason: "allowed" };
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
  return sig;
}

async function guardRecord(sig, cfg) {
  const g = Object.assign({}, GUARD_DEFAULTS, cfg.guards || {});
  const now = Date.now();
  const st = await guardState();

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
    st.positions[sig.symbol] = { side: sig.side, strike: sig.strike,
                                 expiry: sig.expiry, ts: now };
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
        expiry: sig.expiry || held.expiry, ts: now };
    }
  }
  await saveGuardState(st);
  return st;
}

function clampQty(wanted, cfg) {
  const g = Object.assign({}, GUARD_DEFAULTS, cfg.guards || {});
  return Math.max(1, Math.min(parseInt(wanted || 1, 10) || 1, g.max_qty));
}
