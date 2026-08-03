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
const LOG_MAX = 400;   // a full trading day, not just the last hour

/* Rooms that are being RECORDED, never traded. Aristotle's and Midas post the
 * same kind of calls but with messier wording, and the parser hasn't been
 * tuned on their sentences yet — a half-understood call is worse than none.
 * Every message from these channels goes into the capture file (that's the
 * point — Export chat hands over their lexicon for tuning) and absolutely
 * nothing else happens: no parse, no guards, no orders, whatever the settings
 * say. Hard-coded on purpose so a wiped settings box can't accidentally arm
 * them. When a room graduates, its line comes out of this set. */
/* The Whop rooms that trade now — HIS word: "i want everything running at
 * full speed.. every channel, options and futures, equities and swings."
 * Matched by slug so the URL hash never matters. Felony's rooms post bare
 * percentages as PROGRESS ("65% on NVDA"), not trims — the verb decides —
 * so every whop room parses with bare_pct_trims off. Unknown whop rooms
 * stay capture-only until they're named here. */
const WHOP_ROOMS = [
  { slug: "day-trades",         id: "whop:day-trades",   name: "Whop Day Trades" },
  { slug: "futures-",           id: "whop:futures",      name: "Whop Futures" },
  { slug: "high-risk",          id: "whop:high-risk",    name: "Whop High Risk" },
  { slug: "fst-2-k-challenge",  id: "whop:2k-challenge", name: "Whop 2K Challenge" },
  { slug: "swing-trades",       id: "whop:swing",        name: "Whop Swing Trades" },
  { slug: "long-term",          id: "whop:long-term",    name: "Whop Long Term" }
];
function whopRoomOf(channelId) {
  const p = String(channelId || "");
  if (!p.startsWith("whop:")) return null;
  return WHOP_ROOMS.find(r => p.includes(r.slug)) || null;
}

/* Every room's plain name, for the per-room scoreboard he asked for. */
const ROOM_LABELS = {
  "829754942817828884": "Main room",
  "987515353670221834": "Aristotle",
  "1144369893760831489": "Midas",
  "1433933203302776852": "Aristotle small",
  "whop:day-trades": "Whop Day Trades", "whop:futures": "Whop Futures",
  "whop:high-risk": "Whop High Risk", "whop:2k-challenge": "Whop 2K Challenge",
  "whop:swing": "Whop Swing Trades", "whop:long-term": "Whop Long Term",
  "829352738239414332": "ZT top-flow",
  "721821717328298066": "ZT scalps",
  "1504469469844738158": "ZT uoa-data",
  "1174393224253681674": "ZT long-swings",
  "748266924122570882": "ZT uoa-swings",
  "1343408561803362374": "ZT 5k-challenge",
  "1151897689185861632": "ZT strategy-testing",
  "1356793611420958732": "ZT opt-1",
  "1248264554886991893": "ZT opt-2",
  "1470409110288601282": "ZT opt-3",
  "694197721430491266": "ZT opt-4",
  "777750637613416479": "ZT opt-5",
  "1331631786068938813": "ZT opt-6",
  "1239624229583061052": "ZT opt-7",
  "1209181195406024744": "ZT opt-8",
  "1332090335005900800": "ZT opt-9",
  "874280313038192670": "ZT opt-10",
  "1389300087829827745": "ZT swing-1",
  "862419656382873650": "ZT swing-2",
  "1061980561293443152": "ZT swing-3",
  "1179200811650252850": "ZT swing-4",
  "918665915103584327": "ZT cc-1",
  "1255279667489931325": "ZT cc-2",
  "1294812275668160613": "ZT cc-3",
  "1121391020148543631": "ZT cc-4",
  "1239561137914122240": "ZT cc-5",
  "552885275676639243": "ZT forex",
  "1525120298075029554": "ZT fut-1",
  "1251181965252755517": "ZT fut-2",
  "1472793065646325904": "ZT fut-3",
  "1213977047479754783": "ZT fut-4",
  "1375454591755489341": "ZT fut-5",
  "1288291150083653652": "Boka 1",
  "1499190814482632825": "Boka 2",
  "1395159239164432515": "Boka 3",
  "1387459050505240597": "Boka 4",
  "1323708708374450247": "Vero 1",
  "760694103401955378": "Vero 2",
  "1095502893559316482": "Vero 3"
};

const RECORD_ONLY = new Set([
  // (empty — every Discord room is at least shadow-read now; Whop is still
  // gated separately by platform until its reader is precise)
]);

/* Nobody is in shadow — his call: "dont shadow, go ahead and put everyone
 * testing." Every graduated room fires PRETEND trades; not one real dollar
 * moves until he flips the REAL MONEY switch himself. The set stays here
 * for the next new room that needs a proving day. */
const SHADOW = new Set([]);

async function cfg() {
  const { settings } = await chrome.storage.local.get("settings");
  const c = Object.assign({
    armed: true,       // ON is the resting state — see ensureArmed()
    stopped: false,
    capture: true,
    bridge_url: BRIDGE_DEFAULT,
    author_names: [],
    channel_ids: [],   // merged with the graduated rooms below
    extra_veto_words: [],
    guards: {}
  }, settings || {});
  // NOTHING is blocked by ticker any more — the refusal checks are deleted.
  // This list survives only as VOCABULARY: it helps the parser recognise a
  // ticker typed in lowercase ("40% in spy now"), which lets it follow MORE,
  // never less. His old saved list merges with the built-ins.
  const VOCAB = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "AMD", "NVDA", "NFLX",
                 "TSLA", "META", "MSFT", "AMZN", "GOOGL", "GOOG", "PLTR",
                 "COIN", "HOOD", "SMCI", "AVGO", "MU", "INTC", "BABA", "UBER",
                 "SNOW", "CRM", "ORCL", "BAC", "XOM"];
  c.allowed_symbols = Array.from(new Set(
    [].concat((settings || {}).allowed_symbols || [], VOCAB)
      .map(x => String(x).toUpperCase())));
  // The rooms that trade are baked in, so graduating one never depends on a
  // settings box being right: the main room and Aristotle's. Anything typed
  // in the popup's channel box is honoured ON TOP of these.
  c.channel_ids = Array.from(new Set(
    [].concat((settings || {}).channel_ids || [],
              ["829754942817828884",     // main room
               "987515353670221834",     // Aristotle — testing, his word
               "1144369893760831489",    // Midas — testing, his word
               "1433933203302776852",    // Aristotle's small-account challenge
               // Felony's Whop rooms — canonical ids, matched by slug below
               "whop:day-trades", "whop:futures", "whop:high-risk",
               "whop:2k-challenge", "whop:swing", "whop:long-term",
               // z trades (ZTRADEZ) — the free-trial week, all testing
               "829352738239414332", "721821717328298066", "1504469469844738158", "1174393224253681674", "748266924122570882", "1343408561803362374", "1151897689185861632",
               // z trades batch two — his links, his groupings
               "1356793611420958732",
               "1248264554886991893",
               "1470409110288601282",
               "694197721430491266",
               "777750637613416479",
               "1331631786068938813",
               "1239624229583061052",
               "1209181195406024744",
               "1332090335005900800",
               "874280313038192670",
               "1389300087829827745",
               "862419656382873650",
               "1061980561293443152",
               "1179200811650252850",
               "918665915103584327",
               "1255279667489931325",
               "1294812275668160613",
               "1121391020148543631",
               "1239561137914122240",
               "552885275676639243",
               "1525120298075029554",
               "1251181965252755517",
               "1472793065646325904",
               "1213977047479754783",
               "1375454591755489341",
               // boka trading — new server
               "1288291150083653652", "1499190814482632825", "1395159239164432515", "1387459050505240597",
               // VERO — new server
               "1323708708374450247", "760694103401955378", "1095502893559316482"])
      .map(String)));
  return c;
}

async function addLog(entry) {
  const { log } = await chrome.storage.local.get("log");
  const l = log || [];
  l.unshift(Object.assign({ t: Date.now() }, entry));
  await chrome.storage.local.set({ log: l.slice(0, LOG_MAX) });
}

async function capture(text, author, channel, at) {
  const { captured } = await chrome.storage.local.get("captured");
  const c = captured || [];
  // Discord repaints its message nodes and the first capture day came out
  // double-spaced — every line twice. Same author, same words, same minute,
  // in the last few entries = the same message.
  const t0 = at || Date.now();
  if (c.slice(-8).some(e => e.text === text && e.author === author &&
                            Math.abs((e.t || 0) - t0) < 60000)) return;
  // The channel rides along so a capture day across three rooms exports as
  // three distinguishable lexicons — tuning Midas's grammar on Aristotle's
  // sentences would be worse than not tuning at all. The timestamp is the
  // message's own, not the moment it was scraped — scrolled-in history
  // should read as the day it happened. 8000 lines is a couple of weeks of
  // three rooms; older ones fall off the back.
  c.push({ t: at || Date.now(), author, text, channel: String(channel || "") });
  await chrome.storage.local.set({ captured: c.slice(-8000) });
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

async function sendOrder(sig, qty, c, author) {
  const order = {
    action: sig.action, symbol: sig.symbol, side: sig.side, qty,
    strike: sig.strike, expiry: sig.expiry, limit: sig.limit,
    // Who called it. This is half the identity of the trade now — Brett's SPY
    // and Unraveler's SPY are two different positions, and every order has to
    // say whose it is or the bridge can't tell them apart.
    trader: sig.caller || author || "?",
    // Their new blended average, when this is an add. The bridge does the
    // reverse math on it — new_avg*(n+1) - old_avg*n — to recover what the
    // add actually cost, and bids that.
    avg: (sig.avg === 0 || sig.avg) ? sig.avg : null,
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
    // Futures: what it is, which way, and THEIR levels — the plan of record
    // is his stop and target run his trades, not the flat 20%. usd is
    // "$1,100 a contract" off a trim, the only honest futures exit price a
    // dry run has.
    kind: sig.kind || "", direction: sig.direction || null,
    their_stop: (sig.their_stop === 0 || sig.their_stop) ? sig.their_stop : null,
    their_target: (sig.their_target === 0 || sig.their_target) ? sig.their_target : null,
    usd: (sig.usd === 0 || sig.usd) ? sig.usd : null,
    source: "discord-extension", raw: sig.raw, ts: Date.now(),
    // Real money or pretend, decided by the ROOM's toggle, not a global.
    live: !!sig.live,
    // Which room called it — the per-room scoreboard keys off this.
    room: sig.room || null
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
             "double-click START HERE? The trade did NOT go out." };
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
async function markPosition(symbol, trader, c) {
  try {
    const r = await fetch(bridgeBaseFrom(c.bridge_url) + "/mark", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, trader })
    });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}

/* Which mode the bridge is actually in. TEST and REAL follow different rules
 * on this side — test plays the room's full pattern (5 in, add 5, trim 3),
 * real stays on the conservative settings — so the answer has to come from
 * the one program that knows. /fills keeps it fresh; this is the cold start. */
async function bridgeMode(c) {
  const { bridge_mode } = await chrome.storage.local.get("bridge_mode");
  if (bridge_mode) return bridge_mode;
  try {
    const r = await fetch(bridgeBaseFrom(c.bridge_url) + "/mode",
                          { cache: "no-store" });
    if (r.ok) {
      const j = await r.json();
      if (j.mode) {
        await chrome.storage.local.set({ bridge_mode: j.mode });
        return j.mode;
      }
    }
  } catch (e) { /* bridge down; fall through */ }
  // No bridge to ask means no order can send anyway. Defaulting to test keeps
  // every rule on the cautious-for-real-money side: the test pattern only
  // ever fires pretend trades.
  return "dryrun";
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
let fillsBusy = false;   // two pollers, one cursor — see below

async function syncFills() {
  // The 30-second alarm and the after-an-order fast poll can land on top of
  // each other. Both would read the same `fills_seq`, fetch the same events,
  // and write the same log line twice — which is exactly how "sold 1 at
  // 7.35, still holding 2" appeared twice on day two. One at a time.
  if (fillsBusy) return;
  fillsBusy = true;
  try {
    await syncFillsInner();
  } finally {
    fillsBusy = false;
  }
}

async function syncFillsInner() {
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
                   // Whose trade it is rides on the heading now — with two
                   // admins in the same ticker, "SPY — filled" alone doesn't
                   // say which trade just moved.
                   what: sym + (e.who && e.who !== "?" ? " · " + e.who : ""),
                   why: why || e.text });
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
  // A bid that's been "pending" for 15 minutes is not pending — it's a ghost.
  // The bridge pulls every unfilled bid at the 3-minute deadline, so the only
  // ways to get here are a bridge that restarted (and forgot the position
  // before it could say "nofill") or a watcher that died mid-trade. Either way
  // the TAKE 742C lesson applies: nothing may sit in "waiting for a seller"
  // across hours, let alone into the next day.
  const ghostCut = Date.now() - 15 * 60 * 1000;
  for (const k of Object.keys(st.positions)) {
    const p = st.positions[k] || {};
    if (p.pending && (p.ts || 0) < ghostCut) {
      delete st.positions[k];
      changed = true;
      await addLog({ kind: "update", what: keySymbol(k),
                     why: "that bid sat unfilled far past the deadline — " +
                          "a stale leftover, not a live order. Cleared. If " +
                          "you ever see this in REAL mode, glance at Webull's " +
                          "open orders once." });
    }
  }
  if (changed) await saveGuardState(st);
  // The test account and the day's trade table, straight from the bridge, so
  // the popup can draw the whole day instead of leaving you to reconstruct it
  // from log lines. wallet is null in live mode — there Webull is the only
  // honest answer and a second made-up number would be worse than none.
  await chrome.storage.local.set({ wallet: data.wallet || null,
                                   day_table: data.table || [],
                                   bridge_mode: data.mode || null,
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

/* Is New York trading right now? Used only to decide when a reload is safe.
 * The bot is ON 24/7 by design, so "waits until you turn it OFF" would mean
 * updates wait forever — instead they land the moment the session isn't on.
 * A few minutes of margin either side so an update never blinks the reader
 * right at the bell. */
function marketOpenNow() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour12: false,
    weekday: "short", hour: "2-digit", minute: "2-digit"
  }).formatToParts(new Date());
  const g = {};
  for (const p of parts) g[p.type] = p.value;
  if (g.weekday === "Sat" || g.weekday === "Sun") return false;
  const mins = parseInt(g.hour, 10) * 60 + parseInt(g.minute, 10);
  return mins >= 9 * 60 + 15 && mins <= 16 * 60 + 10;
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

  if (inFlight > 0 || (c.armed && marketOpenNow())) {
    const { build_waiting } = await chrome.storage.local.get("build_waiting");
    if (build_waiting !== stamp) {
      await chrome.storage.local.set({ build_waiting: stamp });
      await addLog({ kind: "update", why: "a new version is on this PC. It'll " +
                     "load itself as soon as the market session is over (or " +
                     "the moment you turn the bot OFF) — never mid-session." });
      try {
        chrome.notifications.create({
          type: "basic", iconUrl: "icon128.png",
          title: "Update ready",
          message: "New version waiting. It applies itself after the close."
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
  // The Whop reader gets put back the same way, into any Whop tab that's open.
  try {
    tabs = await chrome.tabs.query({ url: ["https://whop.com/*",
                                           "https://*.whop.com/*"] });
  } catch (e) { return; }
  for (const t of tabs) {
    try {
      await chrome.scripting.executeScript({ target: { tabId: t.id }, files: ["whop.js"] });
    } catch (e) { /* same story */ }
  }
}

/* ---- always on -------------------------------------------------------------
 *
 * The bot used to switch itself OFF after the session and wait to be armed
 * each morning. Deleted, on his word: "i want the bot to be on 24/7 as soon
 * as you execute it, beucase you can only trade during market hours anyway."
 * He's right — the market-hours guard already refuses entries outside the
 * session and weekends, and exits were never time-boxed. Being ON around the
 * clock costs nothing and misses nothing.
 *
 * What stays manual, on his word too: TEST vs REAL. Being ON only ever spends
 * pretend money until he flips the mode himself ("if i want it to go live
 * with an account with money then yes have to activate it").
 *
 * ensureArmed runs once per install: it arms the bot and leaves a marker so
 * the OFF button still works — pressing OFF is a choice, and choices stick.
 */
async function ensureArmed() {
  const { settings, armed_once } = await chrome.storage.local.get(
    ["settings", "armed_once"]);
  if (armed_once) return;
  await chrome.storage.local.set({
    settings: Object.assign({}, settings || {}, { armed: true, stopped: false }),
    armed_once: true
  });
  badge();
}

/* One tab per channel. Day one he clicked START HERE by hand and the 9:25
 * alarm ran it again — every channel open twice, every message read twice.
 * The double-trade guard caught all of them, but the log read double and it
 * only takes one missed catch. So: the same channel in two tabs, and the
 * extra one closes itself. The tab being looked at survives; otherwise the
 * oldest does. */
async function oneTabPerChannel() {
  let tabs;
  try {
    tabs = await chrome.tabs.query({ url: ["https://discord.com/channels/*",
                                           "https://*.discord.com/channels/*",
                                           // Whop rooms dedupe the same way —
                                           // the morning alarm reopens them.
                                           "https://whop.com/joined/*"] });
  } catch (e) { return; }
  const byChannel = {};
  for (const t of tabs) {
    let path;
    try { path = new URL(t.url).pathname; } catch (e) { continue; }
    (byChannel[path] = byChannel[path] || []).push(t);
  }
  for (const path of Object.keys(byChannel)) {
    const dupes = byChannel[path];
    if (dupes.length < 2) continue;
    dupes.sort((a, b) => ((b.active ? 1 : 0) - (a.active ? 1 : 0)) || (a.id - b.id));
    for (const extra of dupes.slice(1)) {
      try { await chrome.tabs.remove(extra.id); } catch (e) { /* already gone */ }
    }
  }
}

/* Does Whop push new messages into an open tab like Discord does, or only
 * show them on refresh? Unknown until Monday proves it — so it's made not
 * to matter. Any Whop tab that hasn't produced a single captured message
 * in 5 minutes gets quietly reloaded: if Whop pushes live, this almost
 * never fires; if it doesn't, the reader is never more than ~5 minutes
 * behind, and the 15-second history grace in whop.js means a reload can
 * never trade the old messages it repaints. */
const whopTabSeen = {};    // tabId -> last time a message arrived from it

async function whopWatchdog() {
  let tabs;
  try {
    tabs = await chrome.tabs.query({ url: ["https://whop.com/joined/*"] });
  } catch (e) { return; }
  const now = Date.now();
  for (const t of tabs) {
    // Whop rooms are a POSTS FEED: each entry ("Long nq 28470") is a post,
    // and the running updates are its comments. If the tab drills INTO a
    // single post (URL gains "/posts/post_..."), the reader sees that post's
    // comments but goes BLIND to new entry posts in the feed — which is why
    // Felony's entries were missed while his "now 130 points" comments came
    // through. So: any whop tab sitting on a /posts/ view gets snapped back
    // to its feed, where new entries actually appear.
    const url = t.url || "";
    if (url.includes("/posts/")) {
      const feed = url.split("/posts/")[0];   // .../day-trades-.../app
      whopTabSeen[t.id] = now;
      try { await chrome.tabs.update(t.id, { url: feed }); } catch (e) { /* gone */ }
      continue;
    }
    if (!whopTabSeen[t.id]) { whopTabSeen[t.id] = now; continue; }
    if (now - whopTabSeen[t.id] > 5 * 60 * 1000) {
      whopTabSeen[t.id] = now;
      try { await chrome.tabs.reload(t.id); } catch (e) { /* tab gone */ }
    }
  }
}

chrome.alarms.create("whop-watchdog", { periodInMinutes: 1 });
chrome.alarms.create("watch-build", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(a => {
  if (a.name === "watch-build") { checkBuild(); syncFills(); oneTabPerChannel(); }
  if (a.name === "whop-watchdog") whopWatchdog();
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
    if (sender && sender.tab && String(msg.platform || "") === "whop") {
      whopTabSeen[sender.tab.id] = Date.now();   // this tab is alive
    }
    if (c.capture) capture(msg.text, msg.author, msg.channelId, msg.postedAt);

    // Whop stops here too, and harder: the Whop reader is a wide net that
    // hasn't been taught the room's shape yet, so EVERYTHING it sends is
    // capture material and none of it may touch the parser. When the Whop
    // room's export has been studied and its reader made precise, this gate
    // is where trading would be switched on — deliberately one line, in one
    // place.
    if (String(msg.platform || "") === "whop") {
      const wroom = whopRoomOf(msg.channelId);
      if (!wroom) {
        reply({ ok: true });   // unknown whop room: captured, nothing more
        return;
      }
      // A graduated Felony room. Canonical id so toggles/guards don't care
      // about URL hashes, and his grammar profile: bare percents are
      // progress updates here, never trims — the verb decides.
      msg.channelId = wroom.id;
      c.bare_pct_trims = false;
    }

    // A reply is a quote of something older — the words are a repeat, not a
    // fresh call. Captured for the record, never traded. This is the fix for
    // Mike replying to his own morning entry and the bot re-buying AMD at
    // top tick off the quoted line.
    if (msg.reply) {
      const rv = parseSignal(msg.text, c);
      if (rv.action && rv.fire !== false || rv.action === "OPEN") {
        await addLog({ kind: "ignored",
                       why: "that's a REPLY quoting an older message — not a " +
                            "fresh call, so nothing was sent",
                       text: msg.text, author: msg.author });
      }
      reply({ ok: true });
      return;
    }

    // Scrolled-in history stops here: filed in the capture with its ORIGINAL
    // timestamp, and never parsed. An old call acted on today is how you buy
    // somebody's exit from last Tuesday — reading the past is for tuning,
    // never for trading.
    if (msg.history) {
      reply({ ok: true });
      return;
    }

    // Shadow rooms get read for real — parsed with the same brain as the
    // main room — and the log shows the verdict, but nothing ever fires.
    // This is the graduation exam: a day of "would have" lines to hold up
    // against what Aristotle actually did.
    if (SHADOW.has(String(msg.channelId || ""))) {
      const sv = parseSignal(msg.text, c);
      if (sv.action) {
        await addLog({ kind: "ignored",
                       what: "shadow · " + (sv.caller || msg.author || "?"),
                       why: "would have read this as: " +
                            (sv.fire ? human(sv)
                             : (sv.action + " — " + sv.why)),
                       text: msg.text, author: msg.author });
      }
      reply({ ok: true });
      return;
    }

    // Record-only rooms stop right here, captured and nothing more. The
    // return is BEFORE the parser on purpose — these rooms' wording hasn't
    // been learned yet, and the one thing worse than missing their call is
    // half-reading it and firing the wrong thing.
    if (RECORD_ONLY.has(String(msg.channelId || ""))) {
      reply({ ok: true });
      return;
    }

    let sig = parseSignal(msg.text, c);
    // Their new blended average, off the raw parse, BEFORE the resolvers get
    // to it — resolveAdd deliberately strips the average out of the limit
    // field (it isn't a tradeable price), but the bridge's reverse math needs
    // the number itself.
    const postedAvg = (sig.action === "ADD") ? sig.limit : null;
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

    /* ---- test mode plays the room's full pattern ------------------------
     * On the bridge's dry run the rules are his, fixed on purpose so every
     * day is comparable: an entry is 5 contracts, an add is 5 more, a trim
     * sells 3, "all out" sells the rest. Money never blocks anything — the
     * bridge's unlimited book keeps score of what it would have taken. None
     * of this touches real mode, which stays on the conservative settings. */
    // THE MASTER SWITCH IS RETIRED — his word: "remove the main big switch
    // since i want every room to act individually. its either testing or
    // they are live.. just like that." Each room's own toggle decides, per
    // order. Every room resets to TESTING when Chrome starts.
    // MICROS, always — his word: "when felony mentiones NQ and ES, we are
    // going to shoot the diminutive of the underlying.. meaning MNQ because
    // my buying power wont be the same. same for any other future." The
    // translation happens HERE, before guards and the book, so the whole
    // trade lives under the micro: his later "Stopped on nq" translates the
    // same way and lands on the same position.
    const MICRO_OF = { NQ: "MNQ", ES: "MES", YM: "MYM", RTY: "M2K",
                       GC: "MGC", CL: "MCL", SI: "SIL" };
    if (sig.kind === "future" && sig.symbol && MICRO_OF[sig.symbol]) {
      sig.symbol = MICRO_OF[sig.symbol];
    }

    // Boka rooms (JonnyOptions) post bare percentages as PROGRESS, like
    // Felony's — the verb decides, not the number.
    const BOKA_IDS = new Set(["1288291150083653652","1499190814482632825",
                              "1395159239164432515","1387459050505240597"]);
    if (BOKA_IDS.has(String(msg.channelId || ""))) {
      c.bare_pct_trims = false;
      c.adding_is_entry = true;   // Jonny's "adding" opens a position
    }

    const roomLive = !!((c.channel_live || {})[String(msg.channelId || "")]);
    sig.live = roomLive;
    sig.room = ROOM_LABELS[String(msg.channelId || "")] ||
               String(msg.channelId || "");
    const testing = !roomLive;
    if (testing && sig.action === "TRIM" && !sig.fire) {
      if (!sig.symbol) {
        sig.needs_position = true;
        sig = await resolveSymbol(sig, msg.author);
      } else {
        sig.fire = true;
      }
      if (sig.fire) {
        sig.action = "TRIM";
        sig.qty = 1;    // one per trim — keeps runners on for the big move
        sig.why = "their trim — selling 1, holding the rest" +
                  (sig.pct != null ? " (they're up " + sig.pct + "%)" : "");
      }
    }
    if (testing && sig.action === "ADD") {
      const stAdd = await guardState();
      const whoAdd = String(sig.caller || msg.author || "").toLowerCase();
      if (!sig.symbol) {
        const pk = pickHeld(stAdd.positions, whoAdd);
        if (pk) sig.symbol = keySymbol(pk);
      }
      const posAdd = sig.symbol
        ? findHeld(stAdd.positions, whoAdd, sig.symbol) : null;
      if (posAdd) {
        sig.side = posAdd.side; sig.strike = posAdd.strike;
        sig.expiry = posAdd.expiry;
        sig.avg = postedAvg;      // the bridge back-solves the real add price
        sig.limit = null;         // their average is not a price you can pay
        sig.qty = 5;
        sig.fire = true;
        sig.why = "their add — test mode buys 5 more" +
                  (postedAvg ? ", and their new average " +
                   Number(postedAvg).toFixed(2) + " tells the bridge what the " +
                   "add really cost" : "");
      } else if (!sig.fire) {
        sig.why = "they added to " + (sig.symbol || "a position") +
                  " but you're not in it — nothing to add onto";
      }
    }

    // "All positions closed" — walk everything this trader holds and close
    // each one as its own order. Respect the OFF switch like everything else.
    if (sig.all && sig.action === "CLOSE") {
      if (c.stopped || c.armed === false) { reply({ ok: true }); return; }
      const stAll = await guardState();
      const whoAll = String(sig.caller || msg.author || "").toLowerCase();
      const mine = Object.keys(stAll.positions || {})
        .filter(k => keyWho(k) === whoAll);
      if (!mine.length) {
        await addLog({ kind: "ignored",
                       why: "they closed everything, but you're not in any of " +
                            "their trades — nothing to sell",
                       text: msg.text, author: msg.author });
        reply({ ok: true });
        return;
      }
      for (const k of mine) {
        const one = Object.assign({}, sig, {
          all: false, symbol: keySymbol(k), fire: true, needs_position: false });
        await fillFromPosition(one, msg.author);
        await guardRecord(one, c, msg.author);
        inFlight++;
        let r1;
        try { r1 = await sendOrder(one, one.qty || 1, c, msg.author); }
        finally { inFlight--; }
        if (r1.ok) watchFills();
        await addLog({ kind: r1.ok ? "sent" : "failed",
                       what: human(one) + " x" + (one.qty || 1), action: "CLOSE",
                       why: r1.msg, text: msg.text, author: msg.author });
      }
      badge();
      reply({ ok: true });
      return;
    }

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
          const m = await markPosition(sig.symbol, sig.caller || msg.author, c);
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

    // THE futures switch. Until it's on, his NQ/ES calls are read, priced and
    // logged — and nothing fires, in either mode. Flipping it in Settings is
    // the one thing left to do when the data subscription is live.
    if (sig.fire && sig.kind === "future" && !c.futures_enabled) {
      await addLog({ kind: "skipped", what: human(sig),
                     why: "futures switch is off — read and logged, nothing " +
                          "sent. Flip it in Settings when you're ready.",
                     text: msg.text, author: msg.author });
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
    if (sig.action === "CLOSE") await fillFromPosition(sig, msg.author);
    // Test mode's sizes are the pattern, not the settings: 5 on the way in,
    // 3 out on a trim, the rest on "all out". Real mode keeps the caps.
    const qty = testing && (sig.action === "OPEN" || sig.action === "ADD")
      ? (sig.kind === "future" ? 3 : (sig.qty || 5))
      : clampQty(sig.qty || 1, c, sig.action);
    // Recorded before the order goes out, so a crash mid-send can't double-fire.
    await guardRecord(sig, c, msg.author);
    inFlight++;
    let res;
    try {
      res = await sendOrder(sig, qty, c, msg.author);
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

async function scrubOldBanners() {
  // The "ON by default now..." banner used to be written into the log at
  // install. He's asked for it gone — including the copies already stored.
  const { log } = await chrome.storage.local.get("log");
  if (!log) return;
  const keep = log.filter(e => !String(e.why || "").startsWith("ON by default now"));
  if (keep.length !== log.length) await chrome.storage.local.set({ log: keep });
}

async function allRoomsTesting() {
  // "as soon as app starts everyone is testing obviously" — LIVE is a
  // decision he makes fresh, per room, per session. Nothing stays armed
  // for real money across a browser restart.
  const { settings } = await chrome.storage.local.get("settings");
  if (settings && settings.channel_live &&
      Object.keys(settings.channel_live).length) {
    settings.channel_live = {};
    await chrome.storage.local.set({ settings });
    await addLog({ kind: "update",
                   why: "Chrome restarted — every room is back to TESTING. " +
                        "LIVE is flipped per room, per session, in Settings." });
  }
}

chrome.runtime.onInstalled.addListener(() => { scrubOldBanners(); allRoomsTesting(); ensureArmed(); badge(); reinject(); });
chrome.runtime.onStartup.addListener(() => { scrubOldBanners(); allRoomsTesting(); ensureArmed(); badge(); reinject(); });
ensureArmed();
badge();
reinject();
checkBuild();
