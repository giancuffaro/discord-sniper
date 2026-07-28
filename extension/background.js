/* background.js — parse, check the brakes, send the order.
 *
 * The browser deliberately holds no broker credentials. It sends a plain
 * description of the trade to a small program running on your own PC
 * (bridge.py), and that program is what talks to the broker. Anything with a
 * copy of your extension folder can read whatever is inside it; a browser is
 * not a safe place for account keys.
 */

importScripts("parser.js", "guards.js");

const BRIDGE_DEFAULT = "http://127.0.0.1:8787/order";
const LOG_MAX = 120;

async function cfg() {
  const { settings } = await chrome.storage.local.get("settings");
  return Object.assign({
    armed: false,
    stopped: false,
    capture: true,
    bridge_url: BRIDGE_DEFAULT,
    allowed_symbols: [],
    author_names: [],
    channel_ids: [],
    extra_veto_words: [],
    guards: {}
  }, settings || {});
}

async function addLog(entry) {
  const { log } = await chrome.storage.local.get("log");
  const l = log || [];
  l.unshift(Object.assign({ t: Date.now() }, entry));
  await chrome.storage.local.set({ log: l.slice(0, LOG_MAX) });
}

async function capture(text, author) {
  const { captured } = await chrome.storage.local.get("captured");
  const c = captured || [];
  c.push({ t: Date.now(), author, text });
  await chrome.storage.local.set({ captured: c.slice(-3000) });
}

async function badge() {
  const c = await cfg();
  const st = await guardState();
  if (c.stopped || !c.armed) {
    chrome.action.setBadgeText({ text: "OFF" });
    chrome.action.setBadgeBackgroundColor({ color: "#3f3f46" });
  } else if (sessionPhase(Object.assign({}, GUARD_DEFAULTS, c.guards || {})) !== "live"
             && Object.keys(st.positions || {}).length) {
    // On after the entry window purely to let an exit through. Worth its own
    // badge so you don't glance at it and think it's still hunting entries.
    chrome.action.setBadgeText({ text: "EXIT" });
    chrome.action.setBadgeBackgroundColor({ color: "#0369a1" });
  } else {
    chrome.action.setBadgeText({ text: String(st.count) });
    chrome.action.setBadgeBackgroundColor({ color: "#b45309" });
  }
}

async function sendOrder(sig, qty, c) {
  const order = {
    action: sig.action, symbol: sig.symbol, side: sig.side, qty,
    strike: sig.strike, expiry: sig.expiry, limit: sig.limit,
    // "exited SPY, and back in @ 2.84" is one message and two orders: sell the
    // contract, then buy the same one back. The bridge does both legs so the
    // gap between them is as small as it can be.
    reenter: !!sig.reenter, reenter_limit: sig.reenter_limit || null,
    // The percentage they posted with an exit ("all out @ 45%"). On a dry run
    // there is no real sale to read a price off, so this is the only honest way
    // to work out what the contract was worth when they called it: their
    // percentage, applied to their entry price. Without it a closed trade has
    // to say "sold at a price I never saw" and the pretend account can't move.
    pct: (sig.pct === 0 || sig.pct) ? sig.pct : null,
    source: "discord-extension", raw: sig.raw, ts: Date.now()
  };
  const t0 = performance.now();
  let r;
  try {
    r = await fetch(c.bridge_url || BRIDGE_DEFAULT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(order)
    });
  } catch (e) {
    return { ok: false, msg: "couldn't reach the bridge on your PC — did you " +
             "press 5 on START HERE? The trade did NOT go out." };
  }
  const ms = Math.round(performance.now() - t0);
  const body = (await r.text()).slice(0, 200);
  if (!r.ok) return { ok: false, msg: "the bridge refused it: HTTP " + r.status + " " + body };
  return { ok: true, msg: "sent in " + ms + " ms — " + (body || "accepted") };
}

/* What is the contract worth this second, and what is that to you. Read-only —
 * it sends no order and can move no money. Returns null whenever there's no
 * answer (bridge down, no keys, not in the trade), and the caller just says
 * less rather than guessing a number. */
async function markPosition(symbol, c) {
  try {
    const r = await fetch(bridgeBaseFrom(c.bridge_url) + "/mark", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol })
    });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}

/* ---- finding out what actually happened ------------------------------------
 *
 * Sending an order and owning contracts used to be the same event. They aren't
 * any more. Your entry goes in as a bid and sits there, and one of three things
 * happens: somebody sells to you, or nobody does and it gets pulled, or the
 * room posts their exit while it's still resting.
 *
 * The browser cannot see any of that — only the bridge talks to Webull. So the
 * position written down here when the order goes out is marked `pending`, and
 * this is what corrects it. The bridge is the authority on what you hold; this
 * side just does what it's told.
 *
 * Why it matters more than it sounds: if this stayed wrong, the next trim the
 * room posts would send a sell for contracts that were never bought, and the
 * 20% stop would be guarding a position that doesn't exist.
 */
async function syncFills() {
  const c = await cfg();
  const { fills_seq } = await chrome.storage.local.get("fills_seq");
  let data;
  try {
    const r = await fetch(bridgeBaseFrom(c.bridge_url) + "/fills?since=" +
                          (fills_seq || 0), { cache: "no-store" });
    if (!r.ok) return;
    data = await r.json();
  } catch (e) {
    return;      // bridge isn't up. Nothing to reconcile against; try later.
  }

  // The log lines first, so the popup reads in the order things happened.
  for (const e of (data.events || [])) {
    const loud = e.kind === "filled" || e.kind === "stopped" ||
                 e.kind === "nofill" || e.kind === "pulled";
    // The bridge's own sentence already begins with the symbol, and the popup
    // prints `what` in front of `why` — which is how "SPY SPY — filled 1 at
    // 2.78" happened. Take the duplicate off the front of the sentence rather
    // than dropping the heading, because the heading is what's in bold.
    const sym = String(e.symbol || "");
    const why = String(e.text || "").replace(
      new RegExp("^" + sym.replace(/[^A-Z0-9]/gi, "") + "\\s*(—|-)?\\s*", "i"), "");
    await addLog({ kind: e.kind === "filled" ? "fired" :
                         (e.kind === "stopped" ? "stopped" : "update"),
                   what: sym, why: why || e.text });
    if (e.kind === "filled" || e.kind === "stopped") {
      try {
        chrome.notifications.create({
          type: "basic", iconUrl: "icon128.png",
          title: (e.kind === "filled" ? "FILLED " : "STOPPED OUT ") + e.symbol,
          message: String(e.text).slice(0, 140)
        });
      } catch (err) { /* nicety */ }
    }
    if (loud) { /* already logged; the branch is here to keep the intent plain */ }
  }

  // Then the positions. Whatever the bridge says about a symbol wins — it is
  // the only side of this that has seen a fill.
  const st = await guardState();
  let changed = false;
  for (const [sym, p] of Object.entries(data.positions || {})) {
    const mine = st.positions[sym];
    if (p.state === "filled") {
      if (!mine) continue;              // reloaded mid-trade; leave it be
      const qty = Math.max(1, parseInt(p.qty || 1, 10) || 1);
      if (mine.pending || mine.qty !== qty) {
        mine.pending = false;
        mine.qty = qty;
        mine.fill = p.fill || null;     // what you actually paid, not their price
        mine.stop = p.stop || null;
        changed = true;
      }
    } else if (p.state === "working") {
      if (mine && !mine.pending) { mine.pending = true; changed = true; }
    } else {
      // nofill, stopped, closed, failed — you are out of it, or never were in.
      if (mine) { delete st.positions[sym]; changed = true; }
    }
  }
  if (changed) await saveGuardState(st);
  // The pretend account, straight from the bridge, so the popup can print a
  // balance instead of leaving you to work out from the log whether $4,000 was
  // ever doing anything. Null in live mode — there Webull is the only honest
  // answer and a second made-up number would be worse than none.
  await chrome.storage.local.set({ wallet: data.wallet || null,
                                   fills_seq: data.seq || 0 });
  badge();
}

/* Straight after an order goes out, check often for a minute or two — that's
 * the window where the fill either happens or doesn't. The half-minute alarm
 * keeps checking after that, and catches anything this missed if Chrome puts
 * the worker to sleep. */
function watchFills(times) {
  let n = times || 20;
  const tick = () => {
    syncFills().finally(() => { if (--n > 0) setTimeout(tick, 5000); });
  };
  setTimeout(tick, 3000);
}

/* ---- picking up its own changes -------------------------------------------
 *
 * Chrome will not notice on its own that you edited a file. An extension loaded
 * with "Load unpacked" is read off the disk once, and after that Chrome only
 * looks again if you press the reload arrow or restart the browser. There is no
 * setting for this — automatic updating is a Chrome Web Store feature, and this
 * is a private tool that is never going near the store.
 *
 * So it does it itself. The bridge is already running on the same PC as the
 * folder, so it hands out a fingerprint of that folder; this checks it every
 * half minute and, when it changes, calls chrome.runtime.reload() — which is
 * the reload arrow, pressed from the inside.
 *
 * Two things it will not do:
 *   - reload while an order is in flight
 *   - reload while the bot is ON
 * Reloading takes about a second, and for that second nothing is reading the
 * room. That's fine at 7am and not fine at 9:32, so while armed it just waits
 * and applies the update the moment you turn the bot OFF.
 */
let inFlight = 0;          // orders currently being sent; worker-lifetime only

function bridgeBaseFrom(url) {
  return (url || BRIDGE_DEFAULT).replace(/\/order\/?$/, "").replace(/\/$/, "");
}

async function checkBuild() {
  const c = await cfg();
  let stamp;
  try {
    const r = await fetch(bridgeBaseFrom(c.bridge_url) + "/build", { cache: "no-store" });
    if (!r.ok) return;
    stamp = (await r.json()).stamp;
  } catch (e) {
    return;    // bridge not running. Nothing to say — it'll be there next time.
  }
  if (!stamp) return;

  const { build_stamp } = await chrome.storage.local.get("build_stamp");
  if (!build_stamp) {                       // first run: remember where we are
    await chrome.storage.local.set({ build_stamp: stamp });
    return;
  }
  if (stamp === build_stamp) return;

  if (c.armed || inFlight > 0) {
    const { build_waiting } = await chrome.storage.local.get("build_waiting");
    if (build_waiting !== stamp) {
      await chrome.storage.local.set({ build_waiting: stamp });
      await addLog({ kind: "update", why: "a new version is on this PC. It'll " +
                     "load itself the moment you turn the bot OFF — not while " +
                     "you're armed." });
      try {
        chrome.notifications.create({
          type: "basic", iconUrl: "icon128.png",
          title: "Update ready",
          message: "New version waiting. It'll apply when you disarm."
        });
      } catch (e) { /* nicety */ }
    }
    return;
  }

  await chrome.storage.local.set({ build_stamp: stamp, build_waiting: "" });
  await addLog({ kind: "update", why: "picked up a new version by itself and reloaded" });
  chrome.runtime.reload();
}

/* Reloading orphans the copy of content.js already sitting in your Discord tab
 * — Chrome does not put a fresh one back on its own, and it will not inject one
 * until that tab navigates. Since you're not going to reload Discord every time,
 * put it back here. */
async function reinject() {
  let tabs;
  try {
    tabs = await chrome.tabs.query({ url: ["https://discord.com/channels/*",
                                           "https://*.discord.com/channels/*"] });
  } catch (e) { return; }
  for (const t of tabs) {
    try {
      await chrome.scripting.executeScript({ target: { tabId: t.id }, files: ["content.js"] });
    } catch (e) { /* tab closed or mid-navigation; the next attach picks it up */ }
  }
}

/* ---- going to sleep when the session is over ------------------------------
 *
 * The room calls entries in the morning and stops around midday. Leaving this
 * Left ON all afternoon and overnight, every stray line in that channel is
 * still being read by something that can spend money, for eleven hours, for no
 * reason. So once entries are done for the day it switches itself OFF.
 *
 * With one exception, and it matters: it will not disarm while you're still
 * holding something. If the room calls the exit at 12:40 and this had already
 * shut itself off at 12:00, that exit doesn't fire and you're sitting in a
 * position nobody is watching. So while you're holding, it stays armed and
 * says so — exits are allowed at any hour, only entries are time-boxed.
 */
async function sessionSweep() {
  const c = await cfg();
  if (!c.armed) return;
  const g = Object.assign({}, GUARD_DEFAULTS, c.guards || {});
  if (g.auto_safe_after_close === false) return;

  const phase = sessionPhase(g);
  if (phase !== "done" && phase !== "shut") return;

  const st = await guardState();
  const held = Object.keys(st.positions || {});
  if (held.length) {
    const { holdNotice } = await chrome.storage.local.get("holdNotice");
    if (holdNotice !== st.day) {
      await chrome.storage.local.set({ holdNotice: st.day });
      await addLog({ kind: "update", why: "entries are done for the day, but " +
                     "you're still in " + held.join(", ") + " — staying ON so " +
                     "their exit can still fire. It'll switch OFF once you're flat." });
    }
    badge();
    return;
  }

  const settings = Object.assign({}, c, { armed: false });
  await chrome.storage.local.set({ settings });
  await addLog({ kind: "update", why: "entries are done for the day and you're " +
                 "flat, so it switched itself OFF. Nothing fires until you " +
                 "arm it again tomorrow." });
  try {
    chrome.notifications.create({
      type: "basic", iconUrl: "icon128.png",
      title: "Switched itself OFF",
      message: "Session's over and you're flat. Disarmed itself."
    });
  } catch (e) { /* nicety */ }
  badge();
}

chrome.alarms.create("watch-build", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(a => {
  if (a.name === "watch-build") { checkBuild(); sessionSweep(); syncFills(); }
});

// Going from ON back to OFF is the moment a held-back update can land, so
// don't make it wait out the rest of the half minute.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.settings) checkBuild();
});

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.type === "ATTACHED") { badge(); reply({ ok: true }); return; }
  if (msg.type !== "MESSAGE") { reply({ ok: false }); return true; }

  (async () => {
    const c = await cfg();
    if (c.capture) capture(msg.text, msg.author);

    let sig = parseSignal(msg.text, c);
    // "Trimming @here" with no ticker. The parser can't finish that on its own
    // — only the position tracker knows what you're holding and who put you in
    // it — so the ticker gets filled in here, before anything decides to fire.
    if (sig.needs_position) sig = await resolveSymbol(sig, msg.author);
    // A LOADING notice buys nothing, but it names the contract their next
    // message is only going to give a price for. Remembered here so that
    // "Filled 3.95 starters" a minute later has something to attach to.
    if (sig.action === "PREPARE") await rememberLoading(sig, msg.author);
    if (sig.needs_loaded) sig = await resolveLoaded(sig, msg.author, c);
    // "added to SPY, new avg 2.8" — a second contract on something you're
    // already in, but only if you switched averaging on and only up to your own
    // limit. resolveLoaded can hand one of these over too, so it comes after.
    if (sig.needs_add) sig = await resolveAdd(sig, msg.author, c);
    if (!sig.fire) {
      // Only worth showing the ones that looked like a trade and then failed a
      // check. Logging pure chatter would bury the useful lines.
      if (sig.action) {
        // A trim you're ignoring is still information. They're saying the trade
        // is up 23% — on THEIR entry. You got in at a different price, so the
        // only way to know what that moment was actually worth to you is to
        // look at the contract price right then. That's what this asks for, and
        // it's the difference between a log full of their percentages and a log
        // that tells you what your own trade was doing.
        let mark = "";
        if (sig.action === "TRIM" && sig.symbol) {
          const m = await markPosition(sig.symbol, c);
          if (m && m.ok && m.pct != null) {
            mark = "  —  yours is at " + Number(m.bid).toFixed(2) +
                   " right now, " + (m.pct >= 0 ? "+" : "") + m.pct + "% on the " +
                   Number(m.fill).toFixed(2) + " you paid (" +
                   (m.pl >= 0 ? "+$" : "-$") + Math.abs(Math.round(m.pl)) + ")";
          }
        }
        await addLog({ kind: "ignored", why: (sig.why || "") + mark,
                       text: msg.text, author: msg.author });
      }
      reply({ ok: true });
      return;
    }

    const chk = await guardCheck(sig, msg, c);
    if (!chk.allowed) {
      await addLog({ kind: "skipped", why: chk.reason, what: human(sig),
                     text: msg.text, author: msg.author });
      reply({ ok: true });
      return;
    }

    // The room says "all out of AMD" — no strike, no expiry, because everyone
    // there knows which contract. A broker doesn't, so fill it in from the
    // position before this leaves the browser. This also sets the quantity on
    // an exit, which is why it has to happen before the line below.
    if (sig.action === "CLOSE") await fillFromPosition(sig);
    const qty = clampQty(sig.qty || 1, c, sig.action);
    // Recorded before the order goes out, so a crash mid-send can't double-fire.
    await guardRecord(sig, c, msg.author);
    inFlight++;
    let res;
    try {
      res = await sendOrder(sig, qty, c);
    } finally {
      inFlight--;     // must drop even if that threw, or updates stall forever
    }
    // An entry is now an offer, not a purchase. Watch for what became of it —
    // this is what turns "bid is in" into "filled" or "nobody sold to you".
    if (res.ok) watchFills();
    await addLog({ kind: res.ok ? "sent" : "failed", what: human(sig) + " x" + qty,
                   // What kind of order it was. "BID IN" is only true of an
                   // entry — a sell doesn't sit on the bid waiting for a buyer,
                   // and calling an exit "BID IN" made closed trades read like
                   // open ones. The popup picks its heading off this.
                   action: sig.action,
                   // sig.warn is the "they posted no fill price" note. It belongs
                   // on the line that actually spent money, not buried elsewhere.
                   why: res.msg + (sig.warn ? "  —  " + sig.warn : ""),
                   text: msg.text, author: msg.author });
    badge();
    try {
      chrome.notifications.create({
        type: "basic", iconUrl: "icon128.png",
        title: (res.ok ? "FIRED " : "FAILED ") + human(sig),
        message: res.msg.slice(0, 140)
      });
    } catch (e) { /* notifications are a nicety, never a blocker */ }
    reply({ ok: true });
  })();

  return true;   // keep the message channel open for the async reply
});

chrome.runtime.onInstalled.addListener(() => { badge(); reinject(); });
chrome.runtime.onStartup.addListener(() => { badge(); reinject(); });
badge();
reinject();
checkBuild();
