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

/* One message, one pass. The reader re-scans the DOM on every mutation sweep,
 * a room can be open in two tabs at once, and content.js's own SEEN set clears
 * at 3000 — so the SAME Discord message reaches the worker again and again.
 * Every re-read used to be logged (and re-evaluated) afresh, which is why the
 * log wrote everything two and three times. This remembers a message by its
 * stable id and drops the repeats. In-memory only: if the worker is evicted the
 * map resets, which is harmless — worst case one duplicate right after a
 * restart. Live path only; history/capture is untouched. */
const RECENT_MSGS = new Map();
const MSG_TTL_MS = 5 * 60 * 1000;
// One entry in flight per CONTRACT — see the AAPL 315C double-buy (8/18).
const OPEN_INFLIGHT = new Map();
// What the VOICE ears already bought — "SYM|side" and "SYM|side|strike" ->
// ts. The scribe types the same call seconds after it's spoken; within this
// window the typed copy is a repeat of a trade we're already in, keyed on
// the contract because the typed author (the scribe) never matches the
// voice room's label. 5 minutes, then the map forgets.
const VOICE_CTX = new Map();     // tabId -> rolling 25s of speech segments
const VOICE_STAGED = new Map();
// SPEAKER NAMING via the scribe (G's design, 8/29): when a voice's spoken
// call matches a typed "@Name" alert within 90s, that speaker IS that
// trader for the session. Voice trades then book under the real name, so
// every per-trader wall (dedupe, trims, no-override) applies to voices
// exactly like text.
const SPEAKER_NAMES = new Map();     // "tabId|spk" -> trader name
const VOICE_RECENT_CALLS = [];       // {t, vkey, symbol, strike, side}
(async () => { try {
  const st = (await chrome.storage.local.get("voice_speaker_names")).voice_speaker_names;
  if (st) for (const k of Object.keys(st)) SPEAKER_NAMES.set(k, st[k]);
} catch (e) {} })();
async function _saveSpeakerNames() {
  try {
    const o = {}; for (const [k, v] of SPEAKER_NAMES) o[k] = v;
    await chrome.storage.local.set({ voice_speaker_names: o });
  } catch (e) {}
}  // tabId -> {vs, t} — "loading X" staged,
                                 // fired only on "I'm in / my average is"
                                 // (G's teaching, 8/29: loading = get ready,
                                 // I'm in = executed). 4-minute shelf life.
const VOICE_TOOK = new Map();
const VOICE_TOOK_MS = 5 * 60 * 1000;
// The ears' QUIET GRACE (8/26): a Discord notification ping flips a tab
// audible for two seconds — on 8/25 that started and stopped the listener 42
// times and wrote down NOTHING all day, and a real speaker's normal pauses
// were cutting sessions mid-sentence. Starting stays instant (latency is the
// whole point); STOPPING now waits until the tab has been quiet for a full
// minute. A stray ping costs 60 seconds of cheap listening; a dropped
// first-word-of-a-call costs the entire edge.
const VOICE_QUIET = new Map();          // tabId -> pending stop timer
const VOICE_QUIET_GRACE_MS = 60 * 1000;
function voiceTookThis(sig) {
  const now = Date.now();
  for (const [k, t] of VOICE_TOOK) if (now - t > VOICE_TOOK_MS) VOICE_TOOK.delete(k);
  if (!sig || !sig.symbol) return false;
  const base = sig.symbol + "|" + (sig.side || "");
  return VOICE_TOOK.has(base) ||
         (sig.strike != null && VOICE_TOOK.has(base + "|" + sig.strike));
}
function seenMessage(msg) {
  // mid alone once swallowed embed hydrations: the re-read of a bot row
  // whose embed arrived late shares its mid with the blank first read.
  // Keying on mid + text LENGTH lets the fuller version through while a
  // same-length re-sweep stays deduped (embed-race fix, 8/30).
  const key = String(msg.mid
    ? msg.mid + "|" + String(msg.text || "").length
    : (msg.channelId + "|" + msg.postedAt + "|" + (msg.author || "") + "|" + msg.text));
  const now = Date.now();
  const prev = RECENT_MSGS.get(key);
  if (prev && (now - prev) < MSG_TTL_MS) return true;
  RECENT_MSGS.set(key, now);
  if (RECENT_MSGS.size > 5000) {
    const cut = now - MSG_TTL_MS;
    for (const [k, v] of RECENT_MSGS) if (v < cut) RECENT_MSGS.delete(k);
  }
  return false;
}

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
  // hash = the stable room id Whop keeps in EVERY url shape — the new
  // profile serves "/firststeptrading/exp_<hash>/app" with no slug at all
  // (8/23), so matching by slug alone lost every room's canonical id.
  { slug: "day-trades",        hash: "cvgzKYDmcUEDGh", id: "whop:day-trades",   name: "Whop Day Trades" },
  { slug: "futures-",          hash: "26GaLgZVMzB2PL", id: "whop:futures",      name: "Whop Futures" },
  { slug: "high-risk",         hash: "hpXJymtw0yMqzB", id: "whop:high-risk",    name: "Whop High Risk" },
  { slug: "fst-2-k-challenge", hash: "Yg9HGTPsXPhQ5D", id: "whop:2k-challenge", name: "Whop 2K Challenge" },
  { slug: "swing-trades",      hash: "6Q7acPPpFb6CyZ", id: "whop:swing",        name: "Whop Swing Trades" },
  { slug: "long-term",         hash: "sMzuBmyHSwKzFW", id: "whop:long-term",    name: "Whop Long Term" }
];
function whopRoomOf(channelId) {
  const p = String(channelId || "");
  if (!p.startsWith("whop:")) return null;
  return WHOP_ROOMS.find(r => p.includes(r.slug) || p.includes(r.hash)) || null;
}

/* Every room's plain name, for the per-room scoreboard he asked for. */
const ROOM_LABELS = {
  "829754942817828884": "Honeydrip daytrades",
  "987515353670221834": "Aristotle",
  "1144369893760831489": "Midas",
  "1433933203302776852": "Aristotle small",
  "642437862930907158": "RWGates",
  "769797179992571914": "Option Alerts",
  "880503518878892143": "Lotto Alerts",
  "769797819770732554": "Options Watchlist",
  "1137873895832174672": "Futures Alerts",
  "1135947475912495216": "MR.TOPHAT",
  "808127664022880297": "Spread Alerts",
  "769797593316065280": "Stock Alerts",
  "771902435680845845": "Member Alerts",
  "800526679046225961": "Trade Log",
  "whop:day-trades": "Whop Day Trades", "whop:futures": "Whop Futures",
  "whop:high-risk": "Whop High Risk", "whop:2k-challenge": "Whop 2K Challenge",
  "whop:swing": "Whop Swing Trades", "whop:long-term": "Whop Long Term",
  "829352738239414332": "ZT top-flow",
  "721821717328298066": "ZT scalps",
  "1174393224253681674": "ZT long-swings",
  "748266924122570882": "ZT uoa-swings",
  "1356793611420958732": "ZT opt-1",
  "1248264554886991893": "ZT opt-2",
  "694197721430491266": "ZT opt-4",
  "777750637613416479": "ZT opt-5",
  "1331631786068938813": "ZT opt-6",
  "1239624229583061052": "ZT opt-7",
  "1209181195406024744": "ZT opt-8",
  "1332090335005900800": "ZT opt-9",
  "874280313038192670": "Demon Alerts",
  "1389300087829827745": "ZT swing-1",
  "862419656382873650": "ZT swing-2",
  "1061980561293443152": "ZT swing-3",
  "1179200811650252850": "ZT swing-4",
  "918665915103584327": "ZT cc-1",
  "1255279667489931325": "ZT cc-2",
  "1294812275668160613": "ZT cc-3",
  "1121391020148543631": "ZT cc-4",
  "552885275676639243": "ZT forex",
  "1525120298075029554": "ZT fut-1",
  "1251181965252755517": "ZT fut-2",
  "1213977047479754783": "ZT fut-4",
  "1375454591755489341": "ZT fut-5",
  "1288291150083653652": "Boka 1",
  "1499190814482632825": "Boka 2",
  "1395159239164432515": "Boka 3",
  "1387459050505240597": "Boka 4",
  "1323708708374450247": "Vero 1",
  "760694103401955378": "Vero 2",
  "1095502893559316482": "Vero 3",
  "1527044644796366888": "Options Insider",
  "1471700027662405712": "ZT fut-6"
};

const RECORD_ONLY = new Set([
  // (empty — every Discord room is at least shadow-read now; Whop is still
  // gated separately by platform until its reader is precise)
]);

/* Nobody is in shadow — his call: "dont shadow, go ahead and put everyone
 * testing." Every graduated room fires PRETEND trades; not one real dollar
 * moves until he flips the REAL MONEY switch himself. The set stays here
 * for the next new room that needs a proving day. */
const SHADOW = new Set([
  // The new server (8/23) proves itself here first — his call: "learn the
  // parser and corpus before anything." Read for real, judged in the log
  // ("would have read this as…"), fires NOTHING until graduated out.
  "911389167169191946", "911390080285962290", "1086120203009658982",
  "1533885258724937739", "983807207625859143",
  "1537061197931618344",   // Rafita Trades 8/23 — proves itself first
]);

/* rooms.txt is the ONE list of channels that trade (his ask, 8/17) — the
 * extension used to keep its own hardcoded copy of "which rooms are baked
 * in", separate from the list of tabs START HERE.bat opens, and the two
 * drifted: a room pulled from the tab-opener kept trading anyway because it
 * was still sitting in this file's old array. Now both read the same
 * rooms.txt. Delete a line there and the room stops opening AND stops
 * trading, in one edit, guaranteed.
 *
 * Loaded once, cached — cfg() awaits this so channel_ids is never read
 * half-populated. An empty channel_ids would mean guardCheck's channel
 * filter skips itself and lets EVERY room through — the opposite of what a
 * missing rooms.txt should do — so a fetch failure logs it and channel_ids
 * stays empty on purpose (nothing trades) rather than defaulting open. */
let _roomsPromise = null;
function loadRoomsFile() {
  if (_roomsPromise) return _roomsPromise;
  _roomsPromise = (async () => {
    try {
      const r = await fetch(chrome.runtime.getURL("rooms.txt"));
      const text = await r.text();
      const ids = [];
      for (const line of text.split("\n")) {
        const t = line.trim();
        if (!t || t.startsWith("#")) continue;
        const id = t.split("|", 1)[0].trim();
        if (id) ids.push(id);
      }
      return ids;
    } catch (e) {
      try {
        await addLog({ kind: "failed", what: "ROOMS.TXT",
          why: "couldn't read extension/rooms.txt — no rooms are traded " +
               "until this is fixed. (" + String(e).slice(0, 120) + ")" });
      } catch (e2) {}
      return [];
    }
  })();
  return _roomsPromise;
}

async function cfg() {
  const { settings } = await chrome.storage.local.get("settings");
  const bakedRooms = await loadRoomsFile();
  const c = Object.assign({
    // No armed/stopped switch any more (8/17) — a room tab being open is the
    // only ON/OFF there is. See guards.js guardCheck() for why.
    capture: true,
    bridge_url: BRIDGE_DEFAULT,
    // ONE round-number switch for every channel (8/17) — Strategies tab.
    rn_pullback_all: false,
    author_names: [],
    channel_ids: [],   // merged with the graduated rooms below
    extra_veto_words: [],
    // Whole-server off switch, per channel id: { "<channelId>": true } means
    // that channel is deactivated — nothing read, nothing traded. The
    // Channels tab groups these by Discord/Whop server so one click can flip
    // every channel in a server, with a per-channel override to keep any one
    // of them on anyway.
    channel_disabled: {},
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
  // The rooms that trade come from rooms.txt now (8/17) — the same file
  // START HERE.bat reads to open tabs. Anything typed in the popup's channel
  // box is still honoured ON TOP of these, same as before.
  c.channel_ids = Array.from(new Set(
    [].concat((settings || {}).channel_ids || [], bakedRooms).map(String)));
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
  // three rooms; older ones fall off the back. Raised to 25k so a couple of
  // MONTHS of one room (grabbed with the auto-scroll history button) fits.
  c.push({ t: at || Date.now(), author, text, channel: String(channel || "") });
  await chrome.storage.local.set({ captured: c.slice(-50000) });
}

/* Save one room's captured messages straight to Downloads — called the moment a
 * grab finishes, so there's no button to press. Returns how many it wrote. */
async function downloadRoom(channelId, roomLabel) {
  let captured = [];
  try { captured = (await chrome.storage.local.get("captured")).captured || []; } catch (e) {}
  const rows = captured.filter(e => String(e.channel) === String(channelId))
                       .sort((a, b) => (a.t || 0) - (b.t || 0));
  if (!rows.length) return 0;
  const lines = rows.map(e => new Date(e.t).toISOString().slice(0, 16).replace("T", " ")
    + "  " + (e.author || "?") + ": " + e.text);
  const safe = String(roomLabel || channelId).replace(/[^a-z0-9]+/gi, "-").slice(0, 40) || "room";
  const stamp = new Date().toISOString().slice(0, 10);
  const url = "data:text/plain;charset=utf-8," + encodeURIComponent(lines.join("\n"));
  try {
    await chrome.downloads.download({ url, filename: safe + "-" + stamp + ".txt" });
  } catch (e) { return 0; }
  return rows.length;
}

/* ---- Grab queue ------------------------------------------------------------
 * Line rooms up and let the extension work through them ONE AT A TIME, hands
 * off. Press Ctrl+Shift+X on room A, then B, then C (or hit the popup button on
 * each): each gets added to the queue. The extension brings the first one to
 * the front (so Chrome doesn't freeze it), scrolls its whole history, saves the
 * file to Downloads, CLOSES that tab, then does the same for the next — until
 * the line is empty. Only one grabs at a time, always in front, so nothing
 * stalls in the background.
 *
 * The queue lives in storage (survives the service worker being put to sleep);
 * `pumping` is just an in-memory guard so two quick presses don't both start
 * the next one. */
let pumping = false;

async function getQueue() { return (await chrome.storage.local.get("grabQueue")).grabQueue || []; }
async function setQueue(q) { await chrome.storage.local.set({ grabQueue: q }); }
async function getRunning() { return (await chrome.storage.local.get("grabRunning")).grabRunning || null; }
async function setRunning(v) {
  if (v) await chrome.storage.local.set({ grabRunning: v });
  else await chrome.storage.local.remove("grabRunning");
}
// The REAL Discord/Whop names, as the reader saw them on the page. This is the
// source of truth for a room's label now — the hand-typed ROOM_LABELS above are
// only a fallback for a room you haven't opened yet this session. Loaded once
// on startup, updated whenever a tab reports a name, persisted so the popup and
// the logs keep the real name even after a restart.
let CHAN_NAMES = {};
(async () => {
  try { CHAN_NAMES = (await chrome.storage.local.get("chan_names")).chan_names || {}; }
  catch (e) { /* storage not ready; fills in as messages arrive */ }
})();
let _chanSaveTimer = null;
function noteChannelName(channelId, name) {
  const id = String(channelId || "");
  const nm = String(name || "").trim();
  if (!id || !nm || nm.length > 80) return;
  if (CHAN_NAMES[id] === nm) return;
  CHAN_NAMES[id] = nm;
  // Debounced write — a burst of messages shouldn't be a burst of disk writes.
  if (_chanSaveTimer) return;
  _chanSaveTimer = setTimeout(() => {
    _chanSaveTimer = null;
    try { chrome.storage.local.set({ chan_names: CHAN_NAMES }); } catch (e) {}
  }, 2000);
}
// Real captured name wins; the hand label is the fallback; then a bare id.
function roomName(channelId) {
  const id = String(channelId || "");
  return (id && (CHAN_NAMES[id] || ROOM_LABELS[id])) || "this room";
}

async function enqueueGrab(tab) {
  if (!tab || !/discord\.com\/channels\//.test(tab.url || "")) {
    await addLog({ kind: "update", why: "Grab ignored — that's not a Discord room tab. Open the room first." });
    return;
  }
  const cm = ((tab.url) || "").match(/channels\/[^/]+\/(\d+)/);
  const channelId = cm ? cm[1] : "";
  const running = await getRunning();
  const q = await getQueue();
  if ((running && running.tabId === tab.id) || q.some(x => x.tabId === tab.id)) {
    await addLog({ kind: "ignored", why: roomName(channelId) + " is already in line — no need to press it twice." });
    return;
  }
  q.push({ tabId: tab.id, channelId: channelId });
  await setQueue(q);
  await addLog({ kind: "update", why: "➕ queued " + roomName(channelId) + " (#" + q.length + " in line) — it'll grab, save, close, then move on." });
  pumpGrabQueue();
}

async function pumpGrabQueue() {
  if (pumping) return;
  if (await getRunning()) return;          // one already in progress
  pumping = true;
  try {
    const q = await getQueue();
    if (!q.length) return;
    const next = q[0];
    await setRunning(next);
    // Bring it to the front so Chrome keeps it awake, then start the scroll.
    try {
      const t = await chrome.tabs.get(next.tabId);
      try { await chrome.windows.update(t.windowId, { focused: true }); } catch (e) {}
      await chrome.tabs.update(next.tabId, { active: true });
      await new Promise(r => setTimeout(r, 400));   // let it paint before scrolling
      await chrome.tabs.sendMessage(next.tabId, { type: "GRAB_HISTORY" });
      await addLog({ kind: "update", why: "⏳ grabbing " + roomName(next.channelId) + " — brought it to the front. Leave it; it closes itself when done." });
    } catch (e) {
      // Tab was closed, or its reader isn't loaded — drop it and move on.
      await addLog({ kind: "ignored", why: "skipped " + roomName(next.channelId) + " — its tab was gone or not ready. Reopen it and re-queue." });
      await advanceQueue(next.tabId, false);
    }
  } finally {
    pumping = false;
  }
}

/* Called when a grab finishes (or its tab vanishes): drop the front item, close
 * its tab if asked, and kick off the next one. */
async function advanceQueue(tabId, closeTab) {
  const q = await getQueue();
  if (q.length && q[0].tabId === tabId) q.shift();
  else { const i = q.findIndex(x => x.tabId === tabId); if (i >= 0) q.splice(i, 1); }
  await setQueue(q);
  await setRunning(null);
  if (closeTab) { try { await chrome.tabs.remove(tabId); } catch (e) {} }
  pumpGrabQueue();
}

/* If you close a queued/running tab yourself, take it out of the line and,
 * if it was the one grabbing, SAVE whatever it caught so far, then move on to
 * the next. (Normal completion sets running=null before closing the tab, so
 * that path doesn't re-download here.) */
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const running = await getRunning();
  const q = await getQueue();
  const wasRunning = running && running.tabId === tabId;
  if (wasRunning) {
    const room = roomName(running.channelId);
    const n = await downloadRoom(running.channelId, room);
    await addLog({ kind: "update", why: "💾 " + room + " tab closed mid-grab — saved " +
      (n ? n + " messages caught so far to your Downloads." : "nothing (nothing captured yet).") });
  }
  if (wasRunning || q.some(x => x.tabId === tabId)) {
    await advanceQueue(tabId, false);
  }
});

/* Stop everything: halt the running grab, save what it caught, and empty the
 * queue so it doesn't advance. Leaves the tab open (a manual stop isn't a
 * finish). */
async function stopAllGrabs() {
  const running = await getRunning();
  if (running) {
    try { await chrome.tabs.sendMessage(running.tabId, { type: "STOP_GRAB" }); } catch (e) {}
    const room = roomName(running.channelId);
    const n = await downloadRoom(running.channelId, room);
    await addLog({ kind: "update", why: "⏹️ stopped " + room + " — saved " +
      (n ? n + " messages caught so far to your Downloads." : "nothing (nothing captured yet).") });
  }
  const left = (await getQueue()).length;
  await setQueue([]);
  await setRunning(null);
  if (left > 1) await addLog({ kind: "update", why: "cleared the rest of the queue (" + (left - 1) + " room" + (left - 1 === 1 ? "" : "s") + " removed)." });
}

/* Ctrl+Shift+X — queue whatever room tab is in front. */
try {
  chrome.commands.onCommand.addListener(async (cmd) => {
    if (cmd !== "grab-history") return;
    let tabs = [];
    try { tabs = await chrome.tabs.query({ active: true, currentWindow: true }); } catch (e) { return; }
    await enqueueGrab(tabs[0]);
  });
} catch (e) { /* commands API unavailable */ }

async function badge() {
  const c = await cfg();
  const st = await guardState();
  // No armed/stopped any more — the toolbar badge is now the LIVE bridge
  // indicator (his ask, 8/17), visible whether or not the popup is open.
  // checkBridgeHealth() keeps this fresh every 30s on the watch-build alarm.
  const { bridge_healthy } = await chrome.storage.local.get("bridge_healthy");
  if (bridge_healthy === false) {
    chrome.action.setBadgeText({ text: "NO BR" });
    chrome.action.setBadgeBackgroundColor({ color: "#dc2626" });
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
    be: !!sig.be,     // breakeven-stops flag (8/29)
    source: "discord-extension", raw: sig.raw, ts: Date.now(),
    // A stable id for THIS order across retries. If the bridge is mid-restart
    // when a call lands, the first POST is refused at the socket (nothing was
    // delivered) and we retry — the bridge dedupes on this id so a retry can
    // never place the same trade twice.
    coid: "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
    // Real money or pretend, decided by the ROOM's toggle, not a global.
    live: !!sig.live,
    // The call said SWING — rides to the book purely for display (8/17).
    swing: !!sig.swing,
    // "instant" (null) or "pullback" — the room's entry-mode toggle. A
    // pullback entry spends whatever the live flag above says, same as an
    // instant one (the old paper-force was lifted 8/17, his call).
    entry_mode: sig.entry_mode || null,
    // Which room called it — the per-room scoreboard keys off this.
    room: sig.room || null
  };
  const t0 = performance.now();
  const url = c.bridge_url || BRIDGE_DEFAULT;
  const payload = JSON.stringify(order);
  // A brief bridge restart (an update, or he double-clicks START HERE again)
  // used to lose the trade outright, and then every follow-up trim was refused
  // for a position that never opened. A THROWN fetch means the request never
  // reached the bridge — safe to retry. An HTTP status back means it DID reach
  // the bridge (working, just answering) — never retried. Up to 3 tries across
  // ~2s covers a normal restart without ever double-sending.
  let r, lastErr;
  for (let attempt = 0; attempt < 3; attempt++) {
    if (attempt > 0) await new Promise(res => setTimeout(res, 800));
    try {
      r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload
      });
      lastErr = null;
      break;                       // reached the bridge (ok or refusal) — stop
    } catch (e) { lastErr = e; }   // connection failure — nothing delivered, retry
  }
  if (lastErr) {
    // Honest about the unknown (8/25 UBER): a thrown fetch usually means
    // nothing was delivered — but a bridge that crashed MID-order placed the
    // trade and never answered. Don't promise "did NOT go out" when the
    // truthful answer is "check".
    return { ok: false, unreachable: true,
             msg: "couldn't reach the bridge on your PC (tried 3×) — did you " +
             "double-click START HERE? The trade almost certainly did not go " +
             "out, but if the bridge hung mid-order it MIGHT have — check the " +
             "popup's fills (or Webull) before re-sending it by hand." };
  }
  const ms = Math.round(performance.now() - t0);
  const body = (await r.text()).slice(0, 200);
  if (!r.ok) return { ok: false, msg: "the bridge refused it: HTTP " + r.status + " " + body };
  return { ok: true, msg: "sent in " + ms + " ms — " + (body || "accepted") };
}

/* Consecutive can't-reach-the-bridge failures. One is a hiccup. Three in a
 * row means the bridge is down and every call the rooms post is being read
 * and then lost — the Aug 3 dry run half-executed a whole session that way:
 * entries vanished, the book stayed flat, and later trims got refused for
 * positions that were never opened. A bot that can't deliver orders must
 * stop taking them. NOTE an HTTP refusal is the bridge WORKING — only a
 * connection failure counts as a strike. */
let bridgeStrikes = 0;
const BRIDGE_STRIKES_OUT = 3;

/* No more auto-disarm / re-arm (8/17): there's nothing left to arm or
 * disarm. When the bridge is unreachable, sendOrder's own 3-retry already
 * fails each order with a clear "couldn't reach the bridge" log line and
 * nothing fires — orders just start working again the instant the bridge
 * answers, with no switch to remember to flip back. This only tracks the
 * live connected/not-reachable flag for the badge and the popup's status
 * dot, and still says something loud after 3 in a row so a real outage
 * doesn't pass silently. */
async function checkBridgeHealth() {
  const c = await cfg();
  let healthy = false;
  try {
    const r = await fetch(bridgeBaseFrom(c.bridge_url) + "/build", { cache: "no-store" });
    healthy = r.ok;
  } catch (e) { healthy = false; }
  const { bridge_healthy: was } = await chrome.storage.local.get("bridge_healthy");
  await chrome.storage.local.set({ bridge_healthy: healthy, bridge_checked_at: Date.now() });
  if (healthy !== was) badge();
  return healthy;
}

async function bridgeStrike(res) {
  if (res.ok) { bridgeStrikes = 0; return; }
  if (!res.unreachable) return;
  bridgeStrikes++;
  if (bridgeStrikes < BRIDGE_STRIKES_OUT) return;
  bridgeStrikes = 0;
  await chrome.storage.local.set({ bridge_healthy: false, bridge_checked_at: Date.now() });
  await addLog({
    kind: "failed", what: "BRIDGE UNREACHABLE",
    why: "the bridge couldn't be reached " + BRIDGE_STRIKES_OUT + " times " +
         "in a row — those calls were read but nothing was sent. Start the " +
         "bridge (🎯 START HERE.bat). Nothing needs re-arming — trading " +
         "resumes on its own the moment the bridge answers again.",
    text: "", author: ""
  });
  badge();
  try {
    chrome.notifications.create({
      type: "basic", iconUrl: "icon128.png",
      title: "BRIDGE UNREACHABLE",
      message: "3 orders in a row couldn't reach the bridge on your PC. " +
               "Start it back up — nothing else to do, it'll pick back up on its own."
    });
  } catch (e) { /* notifications are a nicety, never a blocker */ }
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
      if (!mine) {
        // A position the bridge ADOPTED from the real Webull account — one the
        // bot never placed, or lost track of on a restart. Add it so the popup
        // shows it AND a room's "all out" can actually flatten it. Only true
        // broker-adopted positions are added here; a bare mid-reload with no
        // adopt flag still says "leave it be".
        if (p.adopted) {
          st.positions[sym] = {
            side: p.side, strike: p.strike, expiry: p.expiry,
            ts: Date.now(), author: keyWho(sym) || "?",
            qty: Math.max(1, parseInt(p.qty || 1, 10) || 1), adds: 0,
            pending: false, live: !!p.live, kind: p.kind || "",
            channelId: "", fill: p.fill || null, stop: p.stop || null,
            adopted: true };
          changed = true;
        }
        continue;
      }
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
  // The other direction (8/11): a guard record the BRIDGE doesn't know AT
  // ALL. Yesterday's MSFT/META survived a bridge restart inside extension
  // storage, and this morning's fresh calls got refused as "already in it —
  // would double you up" — a real missed entry. The bridge's book is the
  // truth: if it's answering and holds no trace of a record (same key OR same
  // symbol under any owner, adopted "?" included), and the record is older
  // than 10 minutes (grace for an in-flight send), it's a leftover — drop it
  // so today's call can fire.
  const knownKeys = new Set(Object.keys(data.positions || {}));
  const knownSyms = new Set([...knownKeys].map(keySymbol));
  const staleCut = Date.now() - 10 * 60 * 1000;
  for (const k of Object.keys(st.positions)) {
    const p = st.positions[k] || {};
    if ((p.ts || 0) >= staleCut) continue;
    if (knownKeys.has(k) || knownSyms.has(keySymbol(k))) continue;
    delete st.positions[k];
    changed = true;
    await addLog({ kind: "update", what: keySymbol(k),
                   why: "cleared a leftover record from a previous session — " +
                        "the bridge holds no such trade, and it was blocking " +
                        "fresh entries as a double-up." });
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

/* A cheap gate so the AI reader only ever sees plausible calls, not chatter —
 * it needs a ticker-ish token, a number, and a trading verb all present. Keeps
 * the model (and the round-trip) off the thousands of lines that aren't trades. */
function looksTradeLike(t) {
  if (!t || t.length > 400) return false;
  if (!/\d/.test(t)) return false;
  if (!/(^|[^A-Za-z])\$?[A-Za-z]{1,5}([^A-Za-z]|$)/.test(t)) return false;
  return /\b(in|out|sold|sell|selling|buy|bought|bto|stc|trim(?:med|ming)?|clos(?:e|ed|ing)|long|short|calls?|puts?|add(?:ed|ing)?|stopped|filled|entry|exit|took|target|tp|sl)\b/i.test(t);
}

/* Ask the bridge (which holds your Claude key) to READ one missed message into
 * a clean call. Returns the canonical string, or null if the AI is off, can't
 * read it, or anything at all goes wrong — a miss stays a miss, never a crash. */
async function aiRead(text, c) {
  try {
    const r = await fetch(bridgeBaseFrom(c.bridge_url) + "/read", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    if (!r.ok) return null;
    const j = await r.json();
    if (!(j && j.ok && j.canonical)) return null;
    return { canonical: j.canonical,
             confidence: Number(j.confidence || (j.read && j.read.confidence) || 0) };
  } catch (e) { return null; }
}

/* SCREENSHOT reading (his ask, 8/19): a room posts the call as a picture. The
 * uploaded image URLs go to the bridge, which has Claude read them into a clean
 * call the SAME way text is read — then it runs back through this parser and
 * every guard. Returns {canonical, confidence, seen} or null. */
async function aiReadImage(images, text, c) {
  try {
    const r = await fetch(bridgeBaseFrom(c.bridge_url) + "/readimage", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ images: images || [], text: text || "" })
    });
    if (!r.ok) return null;
    const j = await r.json();
    if (!(j && j.ok && j.canonical)) return null;
    return { canonical: j.canonical, seen: j.seen_text || "",
             confidence: Number(j.confidence || (j.read && j.read.confidence) || 0) };
  } catch (e) { return null; }
}

/* Micro vs full-size index futures are the SAME underlying to us — we always
 * fire the micro (MNQ) no matter which name the room types (NQ). So the
 * double-check must NOT treat "nq" (AI read NQ) vs "MNQ" (regex read) as a
 * disagreement — that false mismatch held every one of Trademorewiser's NQ
 * calls for review, 8/18 and 8/19. Each pair below is one instrument in two
 * sizes; anything not in a pair is compared as a plain ticker. */
const FUT_SIBLINGS = [
  ["NQ", "MNQ"], ["ES", "MES"], ["YM", "MYM"],
  ["RTY", "M2K"], ["CL", "MCL"], ["GC", "MGC"]
];
function sameUnderlying(a, b) {
  a = String(a || "").toUpperCase().trim();
  b = String(b || "").toUpperCase().trim();
  if (a === b) return true;
  for (const [x, y] of FUT_SIBLINGS) {
    if ((a === x || a === y) && (b === x || b === y)) return true;
  }
  return false;
}

/* SMARTER READS — the double-check. Ask the AI to read the SAME message
 * independently and see if it agrees with the regex on the things that pick the
 * contract: ticker, strike, side. Returns {agree, ai} — or null when the AI is
 * off or couldn't read, in which case we DON'T block (the regex read stands, as
 * it does today). Only an ACTIVE disagreement holds the trade. */
async function aiVerify(text, sig, c) {
  try {
    const r = await fetch(bridgeBaseFrom(c.bridge_url) + "/read", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    if (!r.ok) return null;
    const j = await r.json();
    if (!j || j.off || !j.ok || !j.read) return null;   // no opinion -> don't block
    const a = j.read;
    const tOk = !a.ticker || sameUnderlying(a.ticker, sig.symbol);
    const kOk = a.strike == null || sig.strike == null || Number(a.strike) === Number(sig.strike);
    const sOk = !a.side || !sig.side || String(a.side).toUpperCase() === String(sig.side).toUpperCase();
    return { agree: tOk && kOk && sOk, ai: a };
  } catch (e) { return null; }
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

// Market holidays (NYSE closed all day) — same list as the bridge's own
// HOLIDAYS in webull_options.py, kept in sync by hand since this side has no
// import from Python. Add a year here when you add one there.
const MARKET_HOLIDAYS = new Set([
  "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
  "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
  "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
  "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
]);

/* No signals fire Friday 5pm ET through Sunday 7pm ET — the weekend, plain
 * and simple — or on a market holiday. His ask (8/15): the auto-export
 * shouldn't bother writing a file for a stretch where nothing happened. This
 * only gates the AUTOMATIC 30-minute export; the manual buttons (Copy log,
 * Save log now, Export chat) still work any time you press them yourself —
 * if you explicitly want a file, you get one. */
function inExportBlackout() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour12: false,
    weekday: "short", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit"
  }).formatToParts(new Date());
  const g = {};
  for (const p of parts) g[p.type] = p.value;
  const ymd = g.year + "-" + g.month + "-" + g.day;
  if (MARKET_HOLIDAYS.has(ymd)) return true;
  const mins = parseInt(g.hour, 10) * 60 + parseInt(g.minute, 10);
  const FRI_1700 = 17 * 60, SUN_1900 = 19 * 60;
  if (g.weekday === "Fri" && mins >= FRI_1700) return true;
  if (g.weekday === "Sat") return true;
  if (g.weekday === "Sun" && mins < SUN_1900) return true;
  return false;
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

  // Used to wait for the manual OFF switch — deleted 8/17 because that's
  // exactly what left the bot silently dead for 90 minutes on 8/17: it
  // waited for OFF, something turned it OFF once, and nothing ever turned
  // it back ON. Wait for the market to be closed instead — a real state
  // that always ends on its own, with nothing to remember to flip.
  if (inFlight > 0 || marketOpenNow()) {
    const { build_waiting } = await chrome.storage.local.get("build_waiting");
    if (build_waiting !== stamp) {
      await chrome.storage.local.set({ build_waiting: stamp });
      // (the "UPDATED — a new version is on this PC" banner lived here.
      // Deleted 8/11 — his call: he restarts with RESTART BRIDGE.bat, the
      // banner was noise. The build_waiting bookkeeping above still runs.)
    }
    return;
  }

  // Mark that this restart is from a code update, so on the way back up the
  // Discord/Whop tabs get a clean auto-refresh (not just a re-inject) — that's
  // what clears the orphaned "context invalidated" copy for good.
  await chrome.storage.local.set({ build_stamp: stamp, build_waiting: "",
                                   just_updated: stamp });
  await addLog({ kind: "update", why: "picked up a new version by itself and reloaded" });
  chrome.runtime.reload();
}

/* Reloading orphans the copy of content.js already sitting in your Discord tab
 * — Chrome does not put a fresh one back on its own, and it will not inject one
 * until that tab navigates. Since you're not going to reload Discord every time,
 * put it back here. */
async function reinject() {
  // On EVERY come-up — a normal browser open OR a code update — put a fresh
  // content.js back into the tabs WITHOUT reloading the page. His rule: he
  // doesn't want every room's tab refreshing under him every time a version
  // lands, least of all going into a live session. It's safe to skip the
  // reload because content.js is idempotent: the first thing a fresh copy does
  // is call the old copy's __SNIPER_STOP__() (content.js line ~23), which kills
  // the previous observer/timer before the new one starts — so there's no
  // double-reading and no orphaned "context invalidated" copy left running.
  // You keep your scroll position in every room, and reading never stops.
  try { await chrome.storage.local.set({ just_updated: "" }); } catch (e) {}

  const urls = ["https://discord.com/channels/*", "https://*.discord.com/channels/*",
                "https://whop.com/*", "https://*.whop.com/*"];
  let tabs = [];
  try { tabs = await chrome.tabs.query({ url: urls }); } catch (e) { return; }

  for (const t of tabs) {
    const isWhop = /(^|\.)whop\.com/.test(String(t.url || ""));
    try {
      await chrome.scripting.executeScript({ target: { tabId: t.id },
        files: [isWhop ? "whop.js" : "content.js"] });
    } catch (e) { /* tab closed or mid-navigation; the next attach picks it up */ }
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
 * 8/17: taken one step further — the manual ON/OFF switch itself is gone.
 * A room tab being open in the browser is the only switch there ever was in
 * practice (content.js only reads while it's open); the toggle was a SECOND,
 * independent switch that could be left OFF and forgotten, which is exactly
 * what cost 90 minutes on 8/17. There's nothing left to arm on install.
 *
 * What stays manual, on his word too: TEST vs REAL. Being ON only ever spends
 * pretend money until he flips the mode himself ("if i want it to go live
 * with an account with money then yes have to activate it").
 */

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
                                           // 2026 redesign: rooms live at
                                           // /<biz>/exp_<id>/app — /joined/
                                           // is dead but kept for stragglers.
                                           "https://whop.com/joined/*",
                                           "https://whop.com/*/exp_*"] });
  } catch (e) { return; }
  const byChannel = {};
  for (const t of tabs) {
    let path;
    try { path = new URL(t.url).pathname; } catch (e) { continue; }
    // Whop drops the trailing slash once the page loads, so "/app/" (still
    // loading) and "/app" (loaded) counted as two different rooms and BOTH
    // survived — "5 open, 5 loading" (8/23). Normalize before matching.
    path = path.replace(/\/+$/, "").toLowerCase();
    // ONLY a path that NAMES a room can be a duplicate (8/30 — "why do
    // fewer rooms open than rooms.txt?"): during the morning flood, tabs
    // that hadn't committed yet all reported the same blank/interstitial
    // path (/channels/@me, /login, "") and this closer executed the lot
    // as "duplicates". A still-loading tab is never a duplicate.
    if (t.status === "loading") continue;
    if (t.discarded) continue;      // a discarded tab reads nothing (v3.5.0)
    if (!(/\/channels\/\d+\/\d+/.test(path) ||
          /\/exp_[a-z0-9]+/.test(path) || /\/joined\//.test(path))) continue;
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
const WHOP_PULSE = {};     // tabId -> { t, ok, badSince } from the health pulse

async function whopWatchdog() {
  let tabs;
  try {
    // ALL whop tabs (8/25): Profile 2's rooms live at
    // whop.com/<community>/exp_<hash>/app — the old "/joined/*" filter
    // matched none of them, so the auto-reload guarded empty air and a
    // dead (black) tab stayed dead all day. Filter to app views here.
    tabs = await chrome.tabs.query({ url: ["https://whop.com/*"] });
    tabs = tabs.filter(t => /\/app(\/|$)|\/joined\//.test(t.url || ""));
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
    // BROKEN-PAGE reload, any hour (8/25): the pulse says the page is
    // running but painting nothing — a black shell. Two bad minutes in a
    // row earns a reload; a healthy quiet page is left alone.
    const hp = WHOP_PULSE[t.id];
    if (hp && !hp.ok && hp.badSince && now - hp.badSince > 2 * 60 * 1000) {
      WHOP_PULSE[t.id] = { t: now, ok: false, badSince: 0 };  // reset clock
      whopTabSeen[t.id] = now;
      try { await chrome.tabs.reload(t.id); } catch (e) { /* tab gone */ }
      continue;
    }
    // NO-MESSAGE reload, MARKET HOURS ONLY (8/25): out of hours a quiet
    // room is just a quiet room — the old any-hour version reloaded every
    // whop tab all evening, which read as "loading and black again".
    if (!_marketOpenNow()) continue;
    if (!whopTabSeen[t.id]) { whopTabSeen[t.id] = now; continue; }
    if (now - whopTabSeen[t.id] > 5 * 60 * 1000) {
      whopTabSeen[t.id] = now;
      try { await chrome.tabs.reload(t.id); } catch (e) { /* tab gone */ }
    }
  }
}

/* ROOM SILENCE ALARM (his ask, 8/25: "alert me if a channel is not putting
 * out alerts"). Every 5 minutes during market hours, any watched room that
 * hasn't produced a single message in 40 minutes gets a desktop
 * notification and an amber log line — that's either a dead reader (F5 the
 * tab) or a room that's gone quiet; both are worth knowing about. One alert
 * per quiet spell, again at the 2-hour mark if it's still dead. Also barks
 * if NO whop tab is open at all. The map persists across service-worker
 * naps so an idle restart can't fake a full board of silence. */
const ROOM_MSG_AT = {};          // channelId -> last message ts
const ROOM_ALERTED = {};         // channelId -> last-msg ts we alerted on
let _pulseBoot = Date.now();
(async () => { try {
  const st = (await chrome.storage.local.get("room_msg_at")).room_msg_at;
  if (st) for (const k of Object.keys(st)) ROOM_MSG_AT[k] = st[k];
} catch (e) {} })();

function _marketOpenNow() {
  try {
    const p = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York",
      hour12: false, weekday: "short", hour: "2-digit", minute: "2-digit"
    }).formatToParts(new Date());
    const g = t => (p.find(x => x.type === t) || {}).value || "";
    if (["Sat", "Sun"].includes(g("weekday"))) return false;
    const m = parseInt(g("hour"), 10) * 60 + parseInt(g("minute"), 10);
    return m >= 9 * 60 + 30 && m < 16 * 60;
  } catch (e) { return false; }
}

async function roomSilenceCheck() {
  try { await chrome.storage.local.set({ room_msg_at: ROOM_MSG_AT }); } catch (e) {}
  if (!_marketOpenNow()) return;
  const now = Date.now();
  const QUIET = 40 * 60 * 1000;
  for (const id of Object.keys(ROOM_LABELS)) {
    const last = ROOM_MSG_AT[id] || _pulseBoot;
    const quiet = now - last;
    if (quiet < QUIET) continue;
    const already = ROOM_ALERTED[id];
    // once per spell, and once more if it crosses two hours
    if (already === last && quiet < 120 * 60 * 1000) continue;
    if (already === "2h:" + last) continue;
    ROOM_ALERTED[id] = quiet >= 120 * 60 * 1000 ? "2h:" + last : last;
    const mins = Math.round(quiet / 60000);
    const label = ROOM_LABELS[id] || id;
    try {
      chrome.notifications.create("quiet-" + id, {
        type: "basic", iconUrl: "icon128.png",
        title: "🔇 " + label + " — silent " + mins + " min",
        message: "Not one message during market hours. Dead reader (F5 its " +
                 "tab) or the room's just asleep — worth a look either way."
      });
    } catch (e) {}
    await addLog({ kind: "skipped",
                   why: "🔇 " + label + " has been silent " + mins + " min " +
                        "during market hours — dead reader or sleeping room. " +
                        "Check its tab.", text: "", author: label });
  }
  // No whop tab open at all — nothing can be read, say so plainly.
  try {
    let wt = await chrome.tabs.query({ url: ["https://whop.com/*"] });
    wt = wt.filter(t => /\/app(\/|$)|\/joined\//.test(t.url || ""));
    if (!wt.length && WHOP_ROOMS.length &&
        (now - (ROOM_ALERTED["_nowhop"] || 0)) > 30 * 60 * 1000) {
      ROOM_ALERTED["_nowhop"] = now;
      chrome.notifications.create("no-whop", {
        type: "basic", iconUrl: "icon128.png",
        title: "🔇 No Whop tab is open",
        message: "Every Whop room is unwatched right now — open the rooms " +
                 "(START HERE does it) or Felony trades without you." });
      await addLog({ kind: "skipped",
                     why: "🔇 no Whop tab open — every Whop room is unwatched",
                     text: "", author: "whop" });
    }
  } catch (e) {}
}

chrome.alarms.create("room-silence", { periodInMinutes: 5 });
chrome.alarms.create("whop-watchdog", { periodInMinutes: 1 });
chrome.alarms.create("watch-build", { periodInMinutes: 0.5 });
// The self-learning pipe: every 30 minutes, drop the whole day — every raw
// message the reader saw AND what the bot did with each — into a fixed file in
// Downloads/discord-sniper-logs/. Point Google Drive at that folder and it
// syncs up on its own; the scheduled reader picks it up, sees what the parser
// missed, tunes it, and pushes. One file per day, overwritten each pass, so it
// stays current without piling up.
// Fire the export at :05 and :35 past the hour, so there's always a fresh file
// five minutes before the top-of-hour :40 log check (and once mid-hour). Anchor
// to the next :05/:35 so it stays on the clock even across worker restarts.
// Every 4 minutes now, his call — the daily file is overwritten each pass
// (same filename, conflictAction:"overwrite"), so it stays current for a close
// remote read without piling up. Kicks off a minute after startup, then every 4.
// The interval is a SETTING now (popup -> Save chat section), not a constant:
// the worker restarts all day, and a constant here stomped any change straight
// back — "it'll just go back over and over", his words, 8/11. Stored value
// wins; 30 is the default he asked for.
const EXPORT_EVERY_MIN_DEFAULT = 30;
async function armAutoExport() {
  let mins = EXPORT_EVERY_MIN_DEFAULT;
  try {
    const { export_every_min } = await chrome.storage.local.get("export_every_min");
    const v = parseFloat(export_every_min);
    if (v >= 1 && v <= 240) mins = v;
  } catch (e) { /* default stands */ }
  chrome.alarms.create("auto-export", { when: Date.now() + 60000, periodInMinutes: mins });
}
armAutoExport();
chrome.storage.onChanged.addListener((ch, area) => {
  if (area === "local" && ch.export_every_min) armAutoExport();
});
chrome.alarms.onAlarm.addListener(a => {
  if (a.name === "watch-build") { checkBuild(); syncFills(); oneTabPerChannel(); checkBridgeHealth(); memoryShed(); keepRoomsLoaded(); }
  if (a.name === "whop-watchdog") whopWatchdog();
  if (a.name === "room-silence") roomSilenceCheck();
  if (a.name === "auto-export") autoExportForLearning();
});

/* Build one plain-text file of the day — raw captures + activity — and save it
 * to Downloads/discord-sniper-logs/, overwriting the same-day file each pass.
 * A service worker has no Blob URLs, so it goes out as a data: URL. */
async function autoExportForLearning() {
  // Weekend/holiday quiet: no signals fire then, so no point writing a file
  // for it (his ask, 8/15). Manual buttons (Copy log / Save log now / Export
  // chat) still work any time — this only skips the unattended 30-min pass.
  if (inExportBlackout()) return;
  let captured = [], log = [];
  try { captured = (await chrome.storage.local.get("captured")).captured || []; } catch (e) {}
  try { log = (await chrome.storage.local.get("log")).log || []; } catch (e) {}
  if (!captured.length && !log.length) return;
  const stamp = t => { try { return new Intl.DateTimeFormat("en-CA",
    { timeZone: "America/New_York", year: "numeric", month: "2-digit",
      day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
      hour12: false }).format(new Date(t)).replace(",", ""); } catch (e) { return ""; } };
  const day = (stamp(Date.now()).slice(0, 10) || "today");
  // The filename he wants: "signal-room-chat Aug-6-2026.txt". One file per ET
  // day — the same day overwrites itself (conflictAction below), a new day is a
  // new file, so no day's log ever clobbers another's.
  const fileDay = (() => {
    try {
      const parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York",
        month: "short", day: "numeric", year: "numeric" }).formatToParts(new Date());
      const g = t => (parts.find(p => p.type === t) || {}).value || "";
      return g("month") + "-" + g("day") + "-" + g("year");   // Aug-6-2026
    } catch (e) { return day; }
  })();
  const caps = captured.slice().sort((a, b) => a.t - b.t).map(c =>
    // The channel ID rides along in the tag now. The display name alone can't
    // be matched back to the watch list (internal labels like "ZT opt-7" vs
    // Discord's "♟market-bishop"), so a dead-room cleanup was guesswork.
    // With the id here it's exact.
    stamp(c.t) + "  [" + (roomName(c.channel) || "?") +
    (c.channel ? " #" + c.channel : "") + "]  " +
    (c.author || "?") + ": " + String(c.text || "").replace(/\s+/g, " ").trim());
  const acts = log.slice().reverse().map(e =>
    stamp(e.t) + "  <" + (e.kind || "?") + ">  " +
    (e.what ? e.what + " — " : "") + String(e.why || "").replace(/\s+/g, " ").trim() +
    (e.text ? "  |  " + (e.author || "") + ": " + String(e.text).replace(/\s+/g, " ").trim() : ""));

  // The whole popup state, so a remote read of this file sees exactly what's on
  // and off without reaching the PC: connections, keys, toggles, LIVE rooms, and
  // every active position on both accounts. This is what makes "poll what's on
  // the popup" possible from the log alone.
  let state = "";
  try {
    const c = await cfg();
    const base = bridgeBaseFrom(c.bridge_url);
    let mode = null, posData = null, dg = "";
    try { mode = await (await fetch(base + "/mode", { cache: "no-store" })).json(); } catch (e) {}
    try { posData = await (await fetch(base + "/positions", { cache: "no-store" })).json(); } catch (e) {}
    try { dg = (await chrome.storage.local.get("deepgram_key")).deepgram_key || ""; } catch (e) {}
    let ver = "?"; try { ver = (chrome.runtime.getManifest() || {}).version || "?"; } catch (e) {}
    const fb = (mode && mode.futures_brokers) || {};
    const strat = (mode && mode.strategy) || {};
    const liveRooms = Object.keys((c.channel_live) || {})
      .map(id => roomName(id) || id);
    const posLines = ((posData && posData.positions) || []).map(p => {
      const contract = [String(p.symbol || "").toUpperCase(), p.expiry || "",
        (p.strike != null ? p.strike : "") +
        (p.side === "PUTS" ? "P" : p.side === "CALLS" ? "C" : "")]
        .filter(Boolean).join(" ");
      const plp = (p.pl != null) ? " " + (p.pl >= 0 ? "+$" : "-$") + Math.abs(p.pl).toFixed(0) +
        (p.pl_pct != null ? " (" + (p.pl_pct >= 0 ? "+" : "") + p.pl_pct.toFixed(0) + "%)" : "") : "";
      return "    [" + (p.live ? "LIVE " : "PAPER") + "] " + contract + " x" + (p.qty || 1) +
        (p.fill != null ? " paid " + Number(p.fill).toFixed(2) : "") +
        (p.last != null ? " now " + Number(p.last).toFixed(2) : "") + plp;
    });
    const onoff = b => b ? "ON" : "off";
    state =
      "=== CURRENT STATE (as of " + stamp(Date.now()) + " ET) ===\n" +
      "  version:        v" + ver + "\n" +
      // No armed/stopped any more — reading is just whether a room tab is
      // open (8/17). "bridge" below is the one thing that gates trading.
      "  bridge:         " + (mode ? "connected" : "NOT REACHABLE") + "\n" +
      "  webull:         " + (mode ? ("live keys " + onoff(mode.has_keys && mode.connected) +
        ", paper " + (mode.paper ? "ON" : "off") +
        ", paper keys " + onoff(mode.paper_keys_in)) : "unknown") + "\n" +
      "  margin BP:      " + (mode && mode.buying_power != null ? "$" + Math.round(mode.buying_power).toLocaleString() : "—") + "\n" +
      "  futures BP:     " + (mode && mode.futures_buying_power != null ? "$" + Math.round(mode.futures_buying_power).toLocaleString() : "—") + "\n" +
      "  futures from:   webull " + onoff(fb.webull) +
        ", topstep " + onoff((fb.topstep || {}).enabled) +
        ", ninjatrader " + onoff((fb.ninjatrader || {}).enabled) +
        ", tradovate " + onoff((fb.tradovate || {}).enabled) + "\n" +
      "  bracket strat:  " + onoff(strat.enabled) +
        (strat.enabled ? " (+" + (strat.take_profit_pct || 20) + "% / -" + (strat.stop_loss_pct || 10) + "%, 1 contract)" : "") + "\n" +
      "  AI reader:      " + onoff(mode && mode.ai_enabled) + "\n" +
      "  voice key:      " + onoff(dg) + "\n" +
      "  LIVE rooms:     " + (liveRooms.length ? liveRooms.join(", ") : "none (all testing)") + "\n" +
      "  RN-pullback:    " + (c.rn_pullback_all ? "ON — all channels wait for the round number" : "off (all instant)") + "\n" +
      "  open positions (" + ((posData && posData.positions) || []).length + "):\n" +
      (posLines.length ? posLines.join("\n") : "    (none)") + "\n\n";
  } catch (e) { state = ""; }

  const text =
    "Discord Sniper — self-learning export (" + day + ", refreshed " + stamp(Date.now()) + " ET)\n\n" +
    state +
    "=== RAW MESSAGES THE READER SAW (" + caps.length + ") ===\n" + caps.join("\n") +
    "\n\n=== WHAT THE BOT DID (" + acts.length + ") ===\n" + acts.join("\n") + "\n";
  // Through the BRIDGE now, into <folder>\DS Logs (his ask, 8/18: "logs
  // download here"). Chrome's download API can't write outside Downloads
  // and kept minting "(1)(2)(3)" duplicates instead of overwriting — the
  // bridge writes the real file properly, same name all day. Chrome
  // download stays as the fallback for a bridge-down moment.
  const fname = "signal-room-chat " + fileDay + ".txt";
  try {
    const c2 = await cfg();
    const r = await fetch(bridgeBaseFrom(c2.bridge_url) + "/exportlog", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: fname, text: text })
    });
    if (r.ok) {
      try { await chrome.storage.local.set({ last_export: Date.now() }); } catch (e) {}
      return;
    }
  } catch (e) { /* bridge down — fall through to the old Downloads path */ }
  const url = "data:text/plain;charset=utf-8," + encodeURIComponent(text);
  try {
    await chrome.downloads.download({
      url, filename: fname, conflictAction: "overwrite", saveAs: false
    });
    try { await chrome.storage.local.set({ last_export: Date.now() }); } catch (e) {}
  } catch (e) { /* downloads busy or blocked — next pass tries again */ }
}

/* ===== VOICE LISTENER =======================================================
 * Listen to a Discord voice room and write every word down FAST, and turn any
 * spoken call into the same clean format as a typed one. Several rooms at once:
 * Discord allows one voice channel per account, so you open each in its own tab
 * (a second account / profile) and start listening on each — they run in
 * parallel, tagged by tab. The audio work lives in offscreen.js; this side just
 * starts/stops it and files what comes back. It never trades — it writes down.
 */
const LISTENING = new Map();   // tabId -> { label, state }

async function ensureOffscreen() {
  try { if (chrome.offscreen.hasDocument && await chrome.offscreen.hasDocument()) return; }
  catch (e) { /* fall through and try to create */ }
  try {
    await chrome.offscreen.createDocument({
      url: "offscreen.html",
      reasons: ["USER_MEDIA"],
      justification: "Transcribe a Discord voice channel you chose to listen to."
    });
  } catch (e) { /* already exists, or a race — fine */ }
}

async function dgKey() {
  try {
    let k = (await chrome.storage.local.get("deepgram_key")).deepgram_key || "";
    if (k) return k;
    // Not in the browser (fresh install / wiped profile) — its permanent
    // home is the PC. Ask the bridge and restore ourselves (8/20).
    const c = await cfg();
    const r = await fetch(bridgeBaseFrom(c.bridge_url) + "/dgkey");
    if (r.ok) {
      const j = await r.json();
      k = (j && j.key) || "";
      if (k) await chrome.storage.local.set({ deepgram_key: k });
    }
    return k;
  } catch (e) { return ""; }
}
async function dgModel() {
  // nova-3 (8/26): noticeably better on fast multi-speaker room audio, and it
  // takes keyterm prompting — the ticker names are exactly the words nova-2
  // kept mangling ("SLV" -> "silver"). A key without nova-3 access falls back
  // to nova-2 by itself in offscreen.js. Saving deepgram_model in storage
  // still overrides this default, same as before.
  try { return (await chrome.storage.local.get("deepgram_model")).deepgram_model || "nova-3"; }
  catch (e) { return "nova-3"; }
}
async function saveListening() {
  const arr = Array.from(LISTENING.entries()).map(([id, v]) => ({ id, ...v }));
  try { await chrome.storage.local.set({ listening: arr }); } catch (e) {}
  badge();
}

async function startListening(tabId, label) {
  const key = await dgKey();
  if (!key) return { ok: false, why: "paste your Deepgram key in the popup first" };
  await ensureOffscreen();
  let streamId;
  try { streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tabId }); }
  catch (e) { return { ok: false, why: "couldn't grab that tab's audio — click the extension while the Discord tab is focused: " + (e && e.message || e) }; }
  LISTENING.set(tabId, { label: label || ("tab " + tabId), state: "starting" });
  await saveListening();
  // Keyterm prompting (nova-3): hand Deepgram the room's own ticker
  // vocabulary so "SLV" comes back as SLV and not "silver". Short symbols
  // first — those are the ones speech mangles. Spelling help only; nothing
  // is filtered by this list, exactly like the parser's vocabulary.
  const _c = await cfg();
  const keyterms = Array.from(new Set([].concat(_c.allowed_symbols || [])
      .map(s => String(s).toUpperCase().trim())
      .filter(s => /^[A-Z.]{1,6}$/.test(s))))
    .sort((a, b) => a.length - b.length).slice(0, 50);
  chrome.runtime.sendMessage({ target: "offscreen", type: "START_LISTEN",
    id: tabId, label: label || ("tab " + tabId), streamId, dgKey: key,
    model: await dgModel(), keyterms });
  return { ok: true };
}
async function stopListening(tabId) {
  chrome.runtime.sendMessage({ target: "offscreen", type: "STOP_LISTEN", id: tabId });
  LISTENING.delete(tabId);
  await saveListening();
  return { ok: true };
}
async function stopAllListening() {
  chrome.runtime.sendMessage({ target: "offscreen", type: "STOP_ALL" });
  LISTENING.clear();
  await saveListening();
}

async function handleOffscreen(msg) {
  if (msg.type === "LISTEN_NOTE") {
    // Informational only (e.g. nova-3 fell back to nova-2) — the session is
    // still alive, so this must NOT touch the LISTENING map.
    await addLog({ kind: "update",
                   why: "🎙 " + (msg.label || "voice") + ": " + msg.why, text: "" });
    return;
  }
  if (msg.type === "LISTEN_STATE") {
    if (msg.state === "stopped") LISTENING.delete(msg.id);
    else { const cur = LISTENING.get(msg.id); if (cur) cur.state = msg.state; }
    await saveListening();
    return;
  }
  if (msg.type === "LISTEN_ERROR") {
    await addLog({ kind: "ignored", why: "voice (" + (msg.label || "") + "): " + msg.why,
                   text: "" });
    LISTENING.delete(msg.id); await saveListening();
    return;
  }
  if (msg.type === "TRANSCRIPT") {
    if (!msg.isFinal) return;              // write down only finalized segments
    const label = msg.label || ("tab " + msg.id);
    // 1) write EVERYTHING down, fast — but only to the CAPTURE (the corpus
    //    file used for tuning). His call, 8/24: "if its a trash message,
    //    there is no need to fill the log" — the popup log gets a line only
    //    when the words turn out to be an actual call (below).
    capture(msg.text, "🎙 " + label +
            (msg.speaker != null ? " S" + msg.speaker : ""),
            String(msg.id), Date.now());
    // 2) turn a spoken call into the SAME clean format as a typed one, so it's
    //    easy to read and execute. The AI reader gives one uniform shape; the
    //    regex is the free fast path when it already reads it.
    // THE STITCHER (8/29, his find in the transcripts): the trader says
    // "Loading the meta"... breath... "Five sixty calls." Each segment
    // alone is unreadable; the last 25 seconds together are a complete
    // call. Every room keeps a rolling window and the reader sees the
    // window, not the fragment.
    const _now = Date.now();
    // PER-SPEAKER (8/29): each voice in the room gets its own context
    // window and its own staged contract — trader A's "I'm in" can never
    // fire trader B's load. Speaker index comes from Deepgram diarization;
    // null (old sessions) falls back to one shared lane.
    const _vkey = msg.id + "|" + (msg.speaker == null ? "x" : msg.speaker);
    const _buf = (VOICE_CTX.get(_vkey) || []).filter(b => _now - b.t < 25000);
    _buf.push({ t: _now, x: msg.text });
    VOICE_CTX.set(_vkey, _buf);
    const stitched = _buf.map(b => b.x).join(" ");
    // "Now I'm in, guys" — the execution word for a previously STAGED load.
    const CONFIRM = /\b(i'?m in|i am in|got filled|just (?:got )?filled|my average(?: is)?|average is|avg(?:\.| is)|(?:got|took|grabbed|in with) (?:some )?starters?|starters? (?:in|on|here))\b/i;
    const _st = VOICE_STAGED.get(_vkey);
    if (_st && Date.now() - _st.t < 4 * 60 * 1000 && CONFIRM.test(msg.text)) {
      VOICE_STAGED.delete(_vkey);
      const c2 = await cfg();
      if (c2.voice_entries === true) {
        const vs2 = _st.vs;
        const mavg = /(?:average(?: is)?|avg(?:\.| is)?)[^0-9]{0,10}(\d+(?:\.\d+)?)/i.exec(msg.text);
        if (mavg) vs2.limit = parseFloat(mavg[1]);
        await addLog({ kind: "update",
          why: "🎙 \"I'm in\" — firing the staged " + vs2.symbol + " " +
               (vs2.strike || "") + (String(vs2.side||"")[0]||"") +
               (vs2.limit ? " @ " + vs2.limit : ""),
          text: msg.text, author: _st.label || "voice" });
        const r2 = await sendOrder(vs2, vs2.qty || 1, c2, _st.label || "voice");
        await addLog({ kind: r2 && r2.ok ? "sent" : "failed",
          what: "🎙 " + vs2.action + " " + vs2.symbol + " — voice confirm",
          why: (r2 && r2.msg) || "", text: msg.text, author: _st.label || "voice" });
        if (r2 && r2.ok) {
          const nowv = Date.now();
          VOICE_TOOK.set(vs2.symbol + "|" + (vs2.side || ""), nowv);
          if (vs2.strike != null)
            VOICE_TOOK.set(vs2.symbol + "|" + (vs2.side || "") + "|" + vs2.strike, nowv);
        }
      } else {
        await addLog({ kind: "update",
          why: "🎙 \"I'm in\" heard for the staged " + _st.vs.symbol +
               " — Voice ENTRIES is OFF, so noted only",
          text: msg.text, author: _st.label || "voice" });
      }
      return;
    }
    if (!looksTradeLike(msg.text) && !looksTradeLike(stitched)) return;
    const c = await cfg();
    let canon = null, conf = 0, regexHit = false;
    let sig = parseSignal(msg.text, c);
    if (sig.action && sig.symbol) { canon = msg.text.trim(); regexHit = true; }
    if (!canon) {
      sig = parseSignal(stitched, c);
      if (sig.action && sig.symbol) { canon = stitched.trim(); regexHit = true; }
    }
    if (!canon) { const rd = await aiRead(stitched, c); if (rd) { canon = rd.canonical; conf = rd.confidence; } }
    if (!canon) return;
    VOICE_CTX.set(_vkey, []);   // a read call consumes its window
    const pct = conf ? " (" + Math.round(conf * 100) + "%)" : "";
    await addLog({ kind: "update", why: "🎙 VOICE CALL (" + label + ") → " + canon + pct,
                   text: msg.text, author: label });
    // VOICE FIRES (his call, 8/24): the spoken call beats the scribe's typed
    // copy by seconds — that's the whole edge. High-confidence only: the
    // regex reading the words directly counts as confident; an AI read needs
    // 85%+. A misheard strike is the risk, so every normal guard downstream
    // (spread, NO-OTM, cash, stop-at-birth) still applies, and entries need
    // a strike (or a futures root) — "buying some calls" is not an order.
    // TWO SWITCHES now (his call, 8/29): voice ENTRIES and voice EXITS
    // arm separately, both OFF by default. Exits are the proven edge
    // (spoken 6-249s before the scribe, and complete as spoken); entries
    // need the stitcher plus a strike and are the riskier flip.
    const vs = regexHit ? sig : parseSignal(canon, c);
    if (!vs.action || !vs.symbol || vs.fire === false) return;
    // remembered for scribe-matching even in ears-only mode — naming
    // learns while the switches are still off
    VOICE_RECENT_CALLS.push({ t: Date.now(), vkey: _vkey,
                              symbol: vs.symbol, strike: vs.strike,
                              side: vs.side });
    while (VOICE_RECENT_CALLS.length > 40) VOICE_RECENT_CALLS.shift();
    const _learned = SPEAKER_NAMES.get(_vkey.split("|").slice(0,2).join("|")) ||
                     SPEAKER_NAMES.get(_vkey);
    if (_learned) { vs.caller = _learned; label = _learned + " 🎙"; }
    const _isEntry = vs.action === "OPEN" || vs.action === "ADD";
    if (_isEntry && c.voice_entries !== true) return;
    if (!_isEntry && c.voice_exits !== true) return;
    // Dress the order BEFORE staging or firing — a staged entry confirmed
    // by "I'm in" must carry the SAME live flag and the SAME round-number
    // pullback as a direct one (8/29 fix: it used to fire naked-paper).
    vs.live = true;                        // voice rooms are live rooms
    vs.entry_mode = (vs.action === "OPEN" && c.rn_pullback_all !== false)
      ? "pullback" : null;
    vs.caller = vs.caller || label;
    vs.room = "🎙 " + label;
    // TWO-STAGE PROTOCOL (G, 8/29): "loading" means GET READY, not buy.
    // Stage the contract; the buy fires on "I'm in / my average is".
    if (_isEntry && /\bload(?:ing|ed)?\b/i.test(stitched) && !CONFIRM.test(stitched)) {
      VOICE_STAGED.set(_vkey, { vs, t: Date.now(), label: label + (msg.speaker != null ? " · S" + msg.speaker : "") });
      await addLog({ kind: "update",
        why: "🎙 STAGED " + vs.symbol + " " + (vs.strike || "") +
             (String(vs.side||"")[0]||"") + " — they said \"loading\"; " +
             "waiting for \"I'm in\" (4 min shelf)",
        text: canon, author: label });
      return;
    }
    if (!regexHit && conf < 0.85) {
      await addLog({ kind: "skipped", why: "🎙 heard a call but only " +
                     Math.round(conf * 100) + "% sure of the words — not firing " +
                     "real money on a maybe (typed copy will fire normally)",
                     text: canon, author: label });
      return;
    }
    if ((vs.action === "OPEN" || vs.action === "ADD") &&
        vs.strike == null && vs.kind !== "future") return;
    const vres = await sendOrder(vs, vs.qty || 1, c, label);
    await addLog({ kind: vres && vres.ok ? "sent" : "failed",
                   what: "🎙 " + vs.action + " " + vs.symbol + " — voice, " + label,
                   why: (vres && vres.msg) || "", text: canon, author: label });
    if (vres && vres.ok && (vs.action === "OPEN" || vs.action === "ADD")) {
      const now = Date.now();
      VOICE_TOOK.set(vs.symbol + "|" + (vs.side || ""), now);
      if (vs.strike != null)
        VOICE_TOOK.set(vs.symbol + "|" + (vs.side || "") + "|" + vs.strike, now);
    }
  }
}

// A settings change is a sign he's here — check for a pending update a
// little sooner than the 30s alarm would (checkBuild now waits for the
// market to be closed, not for any manual switch — see checkBuild()).
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.settings) checkBuild();
});

/* LIVE rooms (his ask, 8/20): a trader SAYS the call seconds before typing
 * it. The reader in the tab spots Discord's LIVE badge; this side logs it,
 * throws a desktop notification, and tries to start the ears right away.
 * Chrome only hands over a tab's audio after the extension has been clicked
 * on that tab once — so when the grab is refused, the notification says
 * exactly that: click the sniper icon on that tab once, and from then on
 * this room auto-listens every time it goes live. */
const LIVE_SEEN = new Map();     // channelId -> last ping ts
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg && msg.type === "WHOP_PULSE" && sender.tab) {
    const prev = WHOP_PULSE[sender.tab.id] || {};
    WHOP_PULSE[sender.tab.id] = { t: Date.now(), ok: !!msg.ok,
      badSince: msg.ok ? 0 : (prev.badSince || Date.now()) };
    return;
  }
  if (!msg || msg.type !== "LIVE_DETECTED") return;
  (async () => {
    const cid = String(msg.channelId || "");
    const last = LIVE_SEEN.get(cid) || 0;
    if (Date.now() - last < 10 * 60 * 1000) return;   // one alert per 10 min
    LIVE_SEEN.set(cid, Date.now());
    const room = msg.channelName || cid;
    await addLog({ kind: "update",
      why: "🔴 " + room + " is LIVE on voice — they may be calling trades "
           + "out loud before typing them.", text: "" });
    const tabId = sender && sender.tab && sender.tab.id;
    let started = false;
    if (tabId != null && !LISTENING.has(tabId)) {
      // AUTO-JOIN (9/2): click into the live channel first so the tab has
      // audio to capture; give Discord a few seconds to connect. The
      // audible-tab listener may beat us to it — LISTENING check covers it.
      // ONE join per 10 min across ALL tabs: several tabs of the same server
      // each see the LIVE badge, and Discord allows one voice connection per
      // account — a second join from another tab would yank the first.
      const _now = Date.now();
      const _recentJoin = (globalThis.VOICE_JOIN_AT || 0);
      if (_now - _recentJoin < 10 * 60 * 1000) {
        await addLog({ kind: "update",
          why: "🔴 " + room + " — another room was joined <10 min ago; not switching voice", text: "" });
      } else try {
        globalThis.VOICE_JOIN_AT = _now;
        const j = await chrome.tabs.sendMessage(tabId, { type: "JOIN_VOICE" });
        await addLog({ kind: "update",
          why: "🔴 " + room + " — auto-join: " + ((j && j.why) || "no answer"),
          text: "" });
        await new Promise(res => setTimeout(res, 5000));
      } catch (e) { /* tab busy or reloading — fall through to the old path */ }
      if (LISTENING.has(tabId)) { started = true; }
      const r = started ? { ok: true } : await startListening(tabId, room);
      started = !!(r && r.ok);
      if (!started && r) {
        await addLog({ kind: "ignored",
          why: "🔴 couldn't auto-grab " + room + "'s audio (" + r.why + "). "
             + "Join the voice in that tab and click the sniper icon on it "
             + "once — after that it auto-listens every time.", text: "" });
      }
    }
    try {
      chrome.notifications.create("live-" + cid, {
        type: "basic", iconUrl: "icon128.png",
        title: room + " is LIVE",
        message: started
          ? "Listening — every spoken call is being written down."
          : "Join the voice in its tab, then click the Sniper icon on that tab once to start the ears."
      });
    } catch (e) {}
  })();
});

/* The moment a Discord tab starts PLAYING audio (he joined the voice), start
 * transcribing it — and when it goes quiet again, stop. Auto only touches
 * sessions it started itself, so a hand-started listen is never cut off. */
chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (!info || !("audible" in info)) return;
  (async () => {
    try {
      // Discord voice OR a Zoom web-client meeting (Felony goes live on
      // Zoom — the /wc/ browser version is a tab like any other, 8/30).
      if (!tab || !/https:\/\/([^/]*\.)?(discord\.com|zoom\.us)\//.test(tab.url || "")) return;
      const c = await cfg();
      if (c.auto_listen_live === false) return;      // on unless he turns it off
      if (info.audible === true) {
        // Sound again — cancel any pending "quiet" stop and keep the session.
        const t = VOICE_QUIET.get(tabId);
        if (t) { clearTimeout(t); VOICE_QUIET.delete(tabId); }
        if (LISTENING.has(tabId)) return;   // the grace held; nothing to start
        if (!(await dgKey())) return;               // no Deepgram key = no ears
        const label = (tab.title || "voice").replace(/ \| Discord.*/i, "").slice(0, 40);
        const r = await startListening(tabId, label);
        if (r && r.ok) {
          const v = LISTENING.get(tabId); if (v) v.auto = true;
          await saveListening();
          await addLog({ kind: "update",
            why: "🎙 auto-listening to " + label + " — the tab started playing "
               + "voice audio. Every spoken call gets written down and read.",
            text: "" });
        }
      } else if (info.audible === false) {
        const v = LISTENING.get(tabId);
        if (!(v && v.auto)) return;         // hand-started sessions are never cut
        if (VOICE_QUIET.has(tabId)) return; // grace already counting down
        VOICE_QUIET.set(tabId, setTimeout(async () => {
          VOICE_QUIET.delete(tabId);
          try {
            const cur = LISTENING.get(tabId);
            if (!(cur && cur.auto)) return;
            let audibleNow = false;
            try { audibleNow = !!(await chrome.tabs.get(tabId)).audible; }
            catch (e) { /* tab gone — fall through and stop */ }
            if (audibleNow) return;         // it came back — the ears stay on
            await stopListening(tabId);
            await addLog({ kind: "update",
              why: "🎙 " + (cur.label || "voice") + " has been quiet a full "
                 + "minute — stopped listening.", text: "" });
          } catch (e) {}
        }, VOICE_QUIET_GRACE_MS));
      }
    } catch (e) {}
  })();
});

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.type === "ATTACHED") { noteChannelName(msg.channelId, msg.channelName); badge(); reply({ ok: true }); return; }
  // ---- VOICE LISTENER control + transcripts ----
  if (msg && msg.from === "offscreen") { handleOffscreen(msg); reply({ ok: true }); return; }
  if (msg && msg.type === "EXPORT_NOW") { autoExportForLearning().then(() => reply({ ok: true })).catch(() => reply({ ok: false })); return true; }
  if (msg && msg.type === "VOICE_START") { startListening(msg.tabId, msg.label).then(reply); return true; }
  if (msg && msg.type === "VOICE_STOP") { stopListening(msg.tabId).then(reply); return true; }
  if (msg && msg.type === "VOICE_STOP_ALL") { stopAllListening().then(() => reply({ ok: true })); return true; }
  if (msg && msg.type === "VOICE_STATE") {
    reply({ ok: true, listening: Array.from(LISTENING.entries()).map(([id, v]) => ({ id, ...v })) });
    return true;
  }
  // ---- Grab queue: popup asks to stop everything and save partials ----
  if (msg && msg.type === "STOP_ALL_GRABS") {
    stopAllGrabs().then(() => reply({ ok: true }));
    return true;
  }
  // ---- Grab queue: popup asks to add the active room to the line ----
  if (msg && msg.type === "ENQUEUE_GRAB") {
    (async () => {
      let tab = null;
      if (msg.tabId != null) { try { tab = await chrome.tabs.get(msg.tabId); } catch (e) {} }
      if (!tab) { const ts = await chrome.tabs.query({ active: true, currentWindow: true }); tab = ts[0]; }
      await enqueueGrab(tab);
    })();
    reply({ ok: true });
    return true;
  }
  // ---- History grabber progress (from content.js auto-scroll) ----
  if (msg && msg.type === "GRAB_PROGRESS") {
    (async () => {
      const room = ROOM_LABELS[String(msg.channelId || "")] || String(msg.channelId || "");
      if (msg.started) await addLog({ kind: "update", why: "⏳ grabbing " + room + "'s history — scrolling it up, sit tight" });
      else if (msg.done) {
        const how = msg.why ? msg.why
          : (msg.reached === "date" ? "reached 1 year back" :
             msg.reached === "top" ? "reached the top of the channel" :
             msg.reached === "limit" ? "hit the safety limit" : "stopped");
        // Auto-download THIS room's messages the instant it's done — no button.
        const n = await downloadRoom(msg.channelId, room);
        await addLog({ kind: "update", why: "✅ done grabbing " + room + " — " + how +
          (n ? ". Downloaded " + n + " messages to your Downloads." : ". Nothing captured.") });
        // If this room was in the queue, close its tab and start the next one.
        const running = await getRunning();
        if (running && String(running.channelId) === String(msg.channelId)) {
          const left = (await getQueue()).length - 1;
          await addLog({ kind: "update", why: left > 0
            ? "🗂️ closing " + room + " — " + left + " room" + (left === 1 ? "" : "s") + " still in line."
            : "🗂️ closing " + room + " — that was the last one in line. All done." });
          await advanceQueue(running.tabId, true);
        }
      } else if (msg.parked) {
        await addLog({ kind: "ignored", why: "⏸️ " + room + " paused — it's in a background tab. Click back onto that tab to keep grabbing (it held its place" +
          (msg.oldest ? ", at " + new Date(msg.oldest).toLocaleDateString() : "") + ")." });
      } else if (msg.resumed) {
        await addLog({ kind: "update", why: "▶️ " + room + " back in front — grabbing again." });
      } else if (msg.oldest) {
        await addLog({ kind: "ignored", why: "…grabbing " + room + " — back to " + new Date(msg.oldest).toLocaleDateString() });
      }
    })();
    reply({ ok: true });
    return true;
  }
  if (msg.type !== "MESSAGE") { reply({ ok: false }); return true; }

  (async () => {
    const c = await cfg();
    noteChannelName(msg.channelId, msg.channelName);   // learn the room's real name
    if (sender && sender.tab && String(msg.platform || "") === "whop") {
      whopTabSeen[sender.tab.id] = Date.now();   // this tab is alive
      // WHOP API MODE (8/30): when the bridge's server-side reader is
      // active, it is the ONE source of whop messages — tab reads are
      // dropped here so the same alert can't arrive twice with two
      // different identities (tab reads carry no mid; the dedupe can't
      // catch that pair). Tabs stay useful as the health/backup view.
      if (WHOP_API_ACTIVE) { reply({ ok: true, why: "api mode" }); return; }
    }
    // Deactivated (his ask, 8/15): a whole Discord/Whop SERVER can be turned
    // off from the Channels tab in one click, with the option to keep any
    // one of its channels on anyway. Checked before capture too — an OFF
    // channel is off, full stop, not just "don't trade it".
    {
      const _cid = String(
        (String(msg.platform || "") === "whop" && whopRoomOf(msg.channelId))
          ? whopRoomOf(msg.channelId).id : msg.channelId || "");
      if ((c.channel_disabled || {})[_cid]) { reply({ ok: true }); return; }
    }
    // Grabber export stores the FULL row text (embeds and all); trading still
    // reads the clean msg.text below.
    if (c.capture) capture(msg.full || msg.text, msg.author, msg.channelId, msg.postedAt);
    ROOM_MSG_AT[String(msg.channelId || "")] = Date.now();

    // Drop a message we've already handled. Capture ran first (above), so the
    // grabber's export still sees every row; this only stops the LIVE path —
    // parse, guards, logging, firing — from running twice on one message.
    // History is exempt: it returns below without logging or trading anyway,
    // and re-reads of it while scrolling are expected.
    if (!msg.history && seenMessage(msg)) { reply({ ok: true }); return; }

    // Every channel trades now — his call: "no channels should be capture
    // only, every channel should be trade." A Whop room used to stop here as
    // capture-only until its reader was tuned; that's why Felony's room read
    // messages but never took a trade. Now a named Whop room uses its canonical
    // id and an UNNAMED one still parses and fires with the default profile.
    // Bare percentages are progress updates in every Whop room (the verb
    // decides), so that profile applies whether or not the room is named.
    if (String(msg.platform || "") === "whop") {
      const wroom = whopRoomOf(msg.channelId);
      if (wroom) { msg.channelId = wroom.id;   // canonical id when we know it
                   ROOM_MSG_AT[String(wroom.id)] = Date.now(); }
      c.bare_pct_trims = false;
    }

    // SPX->SPY entries, per channel (8/30, G: Ryan's alerts trade SPX —
    // "enter with SPY instead, pretty much the equivalent"). The parser's
    // index-to-ETF retarget (strike/10, premium dropped, bid the SPY
    // market) already handles the math; this flag just unlocks ENTRIES
    // for channels listed in settings.json spx_entry_channels.
    c.spx_entries = ((c.spx_entry_channels || [])
      .map(String).includes(String(msg.channelId || "")));

    // RELAY UNWRAP (8/30, G: "one room that alerts everything"): the ZT
    // all-trades-mashup (and HD Greeter) post as ONE bot account relaying
    // every trader, with the real name leading the embed title — "Bishop's
    // Ideas". Re-book the call under the REAL trader so per-trader claims,
    // the dedupe ladder, and the scoreboard keep working; without this every
    // relayed trader shares one book, and a copy arriving in a direct room
    // would double-fire (different "trader" = no claim match).
    if (/^(ztradez\s*bot|hd\s*greeter)/i.test(String(msg.author || ""))) {
      const _t = String(msg.text || "");
      // Try the leading possessive first ("Bishop's Ideas ..."), then hunt
      // the first 140 chars for a possessive+keyword anywhere — 8/31 live
      // showed the mashup's captured text starts with the call body, so the
      // trader name sits deeper in the embed than the audit's sample.
      const _rm = _t.match(/^\s*(?:the\s+)?([A-Za-z][\w .\-]{1,24}?)[’']s\b/) ||
        _t.slice(0, 140).match(
          /\b([A-Z][\w .\-]{1,24}?)[’']s\s+(?:ideas|alerts|trades|plays|calls|entries)\b/i);
      if (_rm) msg.author = _rm[1].trim();
    }

    // VERO posts every call as a reply on his own alert bot, so the reply
    // gate below was killing ALL of them (his 717C entry read as "a reply,
    // nothing sent"). His format is fixed and self-contained — a full
    // TICKER STRIKE C/P EXPIRY PRICE, or a clean OUT/ALL OUT — so in a Vero
    // room a complete call is trusted and the dedupe (same call once) is what
    // guards a true repeat, not the reply flag.
    const VERO_IDS = new Set(["1323708708374450247", "760694103401955378",
                              "1095502893559316482"]);
    const _veroRoom = VERO_IDS.has(String(msg.channelId || ""));
    // A reply is a quote of something older — the words are a repeat, not a
    // fresh call. Captured for the record, never traded. This is the fix for
    // Mike replying to his own morning entry and the bot re-buying AMD at
    // top tick off the quoted line.
    if (msg.reply) {
      const rv = parseSignal(msg.text, c);
      // Vero exception: a complete call (entry with a strike, or a clear
      // exit/trim) from a Vero room is real even as a reply — let it through.
      const _veroReal = _veroRoom && rv.action &&
        ((rv.action === "OPEN" && rv.symbol && rv.strike != null) ||
         (rv.action !== "OPEN" && rv.symbol));
      if (!_veroReal) {
        if (rv.action && rv.fire !== false || rv.action === "OPEN") {
          await addLog({ kind: "ignored",
                         why: "that's a REPLY quoting an older message — not a " +
                              "fresh call, so nothing was sent",
                         text: msg.text, author: msg.author });
        }
        reply({ ok: true });
        return;
      }
    }

    // Scrolled-in history stops here: filed in the capture with its ORIGINAL
    // timestamp, and never parsed. An old call acted on today is how you buy
    // somebody's exit from last Tuesday — reading the past is for tuning,
    // never for trading.
    if (msg.history) {
      reply({ ok: true });
      return;
    }

    // STALE-ENTRY gate (8/24). The MSFT 480P lesson: the call came at 9:34,
    // was rightly skipped (already in MSFT), and 8 minutes later — after the
    // first trade closed and a bridge restart — the re-scan re-read the SAME
    // message (its 5-min dedupe had expired) and bought it. By then the
    // trader had already stopped out. A scalp entry older than 3 minutes is
    // an artifact of a re-scan or a slow tab, never a fresh call — refused
    // here for OPEN/ADD only. Exits and trims still pass at any age: late
    // is better than never when it's about getting OUT.
    {
      const _pa = Number(msg.postedAt);
      if (isFinite(_pa) && _pa > 946684800000 &&
          Date.now() - _pa > 3 * 60 * 1000) {
        const _st = parseSignal(msg.text, c);
        if (_st && (_st.action === "OPEN" || _st.action === "ADD")) {
          await addLog({ kind: "ignored",
                         what: "stale · " + (_st.caller || msg.author || "?"),
                         why: "that call is " + Math.round((Date.now() - _pa) / 60000) +
                              " minutes old (a re-scan or slow tab brought it back) — " +
                              "entries don't fire late, so nothing was sent",
                         text: msg.text, author: msg.author });
          reply({ ok: true });
          return;
        }
      }
    }

    // Shadow rooms get read for real — parsed with the same brain as the
    // main room — and the log shows the verdict, but nothing ever fires.
    // This is the graduation exam: a day of "would have" lines to hold up
    // against what Aristotle actually did.
    if (SHADOW.has(String(msg.channelId || ""))) {
      let sv = parseSignal(msg.text, c);
      // Shadow grading gets the SAME brain as live rooms (8/23): when the
      // regex shrugs, the AI reader takes a look — otherwise a messy format
      // grades as silence instead of "would have traded X".
      if (!sv.action && !msg.history && !msg.reply && looksTradeLike(msg.text)) {
        const rd = await aiRead(msg.text, c);
        if (rd && rd.canonical) {
          const sv2 = parseSignal(rd.canonical, c);
          if (sv2.action) sv = sv2;
        }
      }
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

    // AI READER — reading intelligence, nothing else. ONLY when the regex gave
    // up (no action) and the line looks like it might be a call. The message is
    // handed to the bridge, which holds the key and asks Claude to read it into
    // a CLEAN call; that clean call is then run back through THIS same parser,
    // so every guard (dedupe, position resolve, live/test routing) still
    // applies. A hallucinated ticker was already refused bridge-side. Off (and
    // free) unless you've saved a Claude API key.
    if (!sig.action && !msg.history && !msg.reply && looksTradeLike(msg.text)) {
      const rd = await aiRead(msg.text, c);
      if (rd && rd.canonical) {
        const sig2 = parseSignal(rd.canonical, c);
        if (sig2.action) {
          const conf = rd.confidence;
          const pct = conf ? " (" + Math.round(conf * 100) + "%)" : "";
          // Confidence gate: a shaky read is written down for you to eyeball,
          // never auto-fired. Only a confident read becomes a live signal.
          if (conf && conf < 0.6) {
            await addLog({ kind: "skipped",
              why: "AI read this as “" + rd.canonical + "” but wasn't sure" + pct +
                   " — held for review, nothing sent. Fire it by hand if it's right.",
              text: msg.text, author: msg.author });
          } else {
            await addLog({ kind: "update",
                           why: "AI read this as “" + rd.canonical + "”" + pct,
                           text: msg.text, author: msg.author });
            sig = sig2;
          }
        }
      }
    }

    // SCREENSHOT reading (his ask, 8/19): still no call from the text, but the
    // post carries an uploaded image — some rooms post the whole call as a
    // picture. Send the image(s) to the bridge's vision reader; a confident
    // read becomes a live signal and runs the identical guards below. Skipped
    // on history and replies, same as the text path. Only fires when the
    // message actually had an image, so ordinary text posts cost nothing.
    if (!sig.action && !msg.history && !msg.reply &&
        Array.isArray(msg.images) && msg.images.length) {
      const ri = await aiReadImage(msg.images, msg.text, c);
      if (ri && ri.canonical) {
        const sig3 = parseSignal(ri.canonical, c);
        if (sig3.action) {
          const conf = ri.confidence;
          const pct = conf ? " (" + Math.round(conf * 100) + "%)" : "";
          const sawBit = ri.seen ? " — saw “" + ri.seen.slice(0, 80) + "”" : "";
          if (conf && conf < 0.6) {
            await addLog({ kind: "skipped",
              why: "📸 read a screenshot as “" + ri.canonical + "” but wasn't sure" +
                   pct + sawBit + " — held for review, nothing sent. Fire it by " +
                   "hand if it's right.",
              text: msg.text || "(image)", author: msg.author });
          } else {
            await addLog({ kind: "update",
              why: "📸 read a screenshot as “" + ri.canonical + "”" + pct + sawBit,
              text: msg.text || "(image)", author: msg.author });
            sig = sig3;
          }
        }
      }
    }
    // Their new blended average, off the raw parse, BEFORE the resolvers get
    // to it — resolveAdd deliberately strips the average out of the limit
    // field (it isn't a tradeable price), but the bridge's reverse math needs
    // the number itself.
    const postedAvg = (sig.action === "ADD") ? sig.limit : null;
    // "Trimming @here" with no ticker. The parser can't finish that on its own
    // — only the position tracker knows what you're holding and who put you in
    // it — so the ticker gets filled in here, before anything decides to fire.
    if (sig.needs_position) sig = await resolveSymbol(sig, msg.author);
    // A3 - "same ones" re-entry: complete the contract from memory and fire it
    // (never doubling up on something you already hold).
    if (sig.reenter) sig = await resolveReenter(sig, msg.author, c);
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
    // EXIT POLICY (8/30, his word: "we're taking everybody's entry, but we
    // are letting the ratchet do its thing" — chose RATCHET + EMERGENCY
    // OUT): callers' TRIMS and STOP-MOVES are recorded, never traded — the
    // ratchet owns profit-taking and stop management. A caller's FULL exit
    // ("all out", "stopped out") still fires: their emergency word can beat
    // a trailing stop on real news. settings.json exit_policy:"full" is the
    // one-line way back to the old obey-everything behavior.
    {
      const _xp = String(c.exit_policy || "ratchet_emergency");
      if (_xp !== "full" && sig.fire &&
          (sig.action === "TRIM" || sig.action === "STOPMOVE")) {
        await addLog({ kind: "ignored",
          why: "exit policy: the ratchet owns " +
               (sig.action === "TRIM" ? "trims" : "stop moves") + " — " +
               (sig.caller || msg.author || "?") + "'s call noted, not traded",
          text: String(msg.text || "").slice(0, 140) });
        reply({ ok: true });
        return;
      }
    }
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
    } else if (sig.symbol && MICRO_OF[sig.symbol] &&
               (sig.action === "TRIM" || sig.action === "CLOSE") &&
               (sig.strike === null || sig.strike === undefined)) {
      // A bare futures EXIT ("TRIM ES", "out of NQ") arrives with no kind tag —
      // the reader marks entries, not one-word exits — so it skipped the micro
      // translation above and went looking for an "ES" position while the book
      // holds MES. The exit guard then refused it as "you're not in ES" and it
      // never reached the bridge: 8/21, Stormzy's two ES trims died that way on
      // a live MES long. Same class of bug bridge.py already fixed on its own
      // exit gate ("a known futures root with no strike IS a future").
      // Deliberately narrow: only on an exit, only when you are actually
      // holding the micro and NOT the plain root, so an equity ticker that
      // happens to share a futures root (CL, SI) can never be translated.
      const _stMic = await guardState();
      const _heldMic = (_stMic && _stMic.positions) || {};
      const _plain = String(sig.symbol).toUpperCase();
      const _micro = MICRO_OF[_plain];
      const _hasSym = (s) =>
        Object.keys(_heldMic).some(k => keySymbol(k) === s);
      if (!_hasSym(_plain) && _hasSym(_micro)) {
        sig.symbol = _micro;
        sig.kind = "future";
      }
    }

    // Boka rooms (JonnyOptions) post bare percentages as PROGRESS, like
    // Felony's — the verb decides, not the number.
    const BOKA_IDS = new Set(["1288291150083653652","1499190814482632825",
                              "1395159239164432515","1387459050505240597"]);
    if (BOKA_IDS.has(String(msg.channelId || ""))) {
      c.bare_pct_trims = false;
      c.adding_is_entry = true;   // Jonny's "adding" opens a position
    }

    // ALWAYS LIVE (his call, 8/23: "channels always toggled all live as soon
    // as I open everything"). Every room is REAL MONEY unless he explicitly
    // flips it to testing in the popup (stored false) — the old default was
    // the reverse. Shadow rooms still fire nothing at all.
    const _lv = (c.channel_live || {})[String(msg.channelId || "")];
    const roomLive = _lv !== false;
    sig.live = roomLive;
    // The voice ears already took this one (8/24): the spoken call fired
    // seconds ago; this typed line is the scribe's copy of it. Entries only —
    // exits and trims always pass, doubled exits are idempotent and a missed
    // exit is the expensive mistake.
    // SPEAKER LEARNING (8/29): this typed alert may be the scribe's copy of
    // something a voice just said — if symbol (and strike, when both have
    // one) match a voice call from the last 90s, that speaker now has this
    // trader's name.
    if (sig.symbol && (sig.caller || msg.author)) {
      const _nm = String(sig.caller || msg.author).replace(/^@/, "").trim();
      const _cut = Date.now() - 90000;
      for (const rc of VOICE_RECENT_CALLS) {
        if (rc.t < _cut || rc.symbol !== sig.symbol) continue;
        if (rc.strike != null && sig.strike != null &&
            Number(rc.strike) !== Number(sig.strike)) continue;
        const spkKey = rc.vkey;   // tabId|speaker
        if (_nm && SPEAKER_NAMES.get(spkKey) !== _nm) {
          SPEAKER_NAMES.set(spkKey, _nm);
          _saveSpeakerNames();
          const _spk = spkKey.split("|")[1];
          await addLog({ kind: "update",
            why: (_spk !== "x"
              ? "🎙 speaker S" + _spk + " identified as " + _nm +
                " (scribe confirmed the same call)"
              : "🎙 the room's voice identified as " + _nm +
                " (scribe confirmed)"),
            text: msg.text, author: _nm });
        }
      }
    }
    if ((sig.action === "OPEN" || sig.action === "ADD") && voiceTookThis(sig)) {
      await addLog({ kind: "skipped",
                     what: sig.action + " " + sig.symbol + " — typed copy",
                     why: "🎙 the voice ears already fired this call seconds ago — " +
                          "the typed version is the scribe catching up, not a new trade",
                     text: msg.text, author: msg.author });
      reply({ ok: true });
      return;
    }
    // Round-number pullback is ONE global switch (his ask, 8/17), and since
    // 8/23 it COMES UP ON — only an explicit off in Strategies turns it off.
    sig.entry_mode = (c.rn_pullback_all !== false) ? "pullback" : null;
    sig.channelId = String(msg.channelId || "");
    sig.room = ROOM_LABELS[String(msg.channelId || "")] ||
               String(msg.channelId || "");
    const testing = !roomLive;
    // Follow their trims to the tee — in LIVE rooms too, not just testing. His
    // call: "they trimmed 10% and it didn't trigger on my broker; I want the
    // trim to fire." A room's trim IS the take-profit, so when they sell some,
    // the bot sells some at the broker (one contract, runners stay on).
    if (sig.action === "TRIM" && !sig.fire) {
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
    // Adds follow to the tee in LIVE rooms too, not just testing — same reason
    // trims do. When they add to a position you're in, the bot adds too.
    if (sig.action === "ADD") {
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
        // Test buys 5 more; live adds 1 (the bracket clamps to 1 anyway).
        sig.qty = testing ? 5 : 1;
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
    // each one as its own order.
    if (sig.all && sig.action === "CLOSE") {
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
        await guardRecord(one, c, msg.author, msg.test);
        inFlight++;
        let r1;
        try { r1 = await sendOrder(one, one.qty || 1, c, msg.author); }
        finally { inFlight--; }
        await bridgeStrike(r1);
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

    // Futures fire like every other room now — read, priced, and sent per the
    // room's own TESTING/LIVE toggle, same as options. (The old separate
    // futures switch is retired on both sides: "everything should be either
    // testing or live." CME data is live.) Left as a one-line guard only so an
    // explicit futures_enabled:false still parks them if you ever want that.
    if (sig.fire && sig.kind === "future" && c.futures_enabled === false) {
      await addLog({ kind: "skipped", what: human(sig),
                     why: "futures switch is explicitly off — read and logged, " +
                          "nothing sent. Turn it back on in Settings.",
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

    // SMARTER READS — optional double-check on ENTRIES. If it's on, the AI reads
    // the message independently and must agree with what the regex pulled out
    // (ticker/strike/side); a disagreement is HELD FOR REVIEW, not bought. Catches
    // the wrong-ticker/strike class (meta->TSLA) even when the regex was sure.
    if (sig.action === "OPEN" || sig.action === "ADD") {
      let verifyOn = true;   // ON by default now, his standing rule (8/13)
      try { verifyOn = ((await chrome.storage.local.get("ai_verify")).ai_verify !== false); } catch (e) {}
      if (verifyOn && sig.symbol) {
        const v = await aiVerify(msg.text, sig, c);
        if (v && !v.agree) {
          await addLog({ kind: "skipped",
            why: "⚠ double-check disagrees — I read " + sig.symbol + " " +
                 (sig.strike || "") + ", the AI read " + (v.ai.ticker || "?") + " " +
                 (v.ai.strike || "") + ". Held for review — nothing sent. Fire it by " +
                 "hand in Webull if the room really meant it.",
            what: human(sig), text: msg.text, author: msg.author });
          reply({ ok: true });
          return;
        }
      }
    }

    // The room says "all out of AMD" — no strike, no expiry, because everyone
    // there knows which contract. A broker doesn't, so fill it in from the
    // position before this leaves the browser. This also sets the quantity on
    // an exit, which is why it has to happen before the line below.
    if (sig.action === "CLOSE") await fillFromPosition(sig, msg.author);
    // One-click bracket strategy overrides sizing on the way in: always exactly
    // 1 contract, no matter what the alert called for. Trims/closes still size
    // off the open position so a full exit stays possible.
    const stratOn = c && c.strategy && c.strategy.enabled;
    // Test mode's sizes are the pattern, not the settings: 5 on the way in,
    // 3 out on a trim, the rest on "all out". Real mode keeps the caps.
    const qty = (stratOn && (sig.action === "OPEN" || sig.action === "ADD"))
      ? 1
      : (testing && (sig.action === "OPEN" || sig.action === "ADD")
        ? (sig.kind === "future" ? 3 : (sig.qty || 5))
        : clampQty(sig.qty || 1, c, sig.action));
    // IN-FLIGHT CONTRACT LOCK (8/18, the AAPL 315C double-buy): the scribe's
    // relay and the admin's own post land ~1s apart, and both passed the
    // guards before either had recorded a position — two real buys at 1.10
    // and 1.11. While an OPEN for a contract is mid-flight (and 15s after),
    // a second OPEN for the SAME contract is the echo, whatever its price.
    if (sig.action === "OPEN") {
      const _ck = [String(sig.symbol || "").toUpperCase(), sig.side,
                   sig.strike, sig.expiry].join("|");
      const _prev = OPEN_INFLIGHT.get(_ck);
      if (_prev && (Date.now() - _prev) < 15000) {
        await addLog({ kind: "skipped",
          why: "that exact contract's entry is already in flight from " +
               "another relay of the same call — not buying it twice",
          what: human(sig), text: msg.text, author: msg.author });
        reply({ ok: true });
        return;
      }
      OPEN_INFLIGHT.set(_ck, Date.now());
      if (OPEN_INFLIGHT.size > 200) OPEN_INFLIGHT.clear();
    }
    // Recorded before the order goes out, so a crash mid-send can't double-fire.
    await guardRecord(sig, c, msg.author, msg.test);
    inFlight++;
    let res;
    try {
      res = await sendOrder(sig, qty, c, msg.author);
    } finally {
      inFlight--;     // must drop even if that threw, or updates stall forever
    }
    await bridgeStrike(res);
    // A failed entry never went out — so undo the position we wrote down before
    // sending, or it becomes a PHANTOM that blocks the next real entry ("already
    // in AMD") and makes trims chase something that isn't there. This is what
    // wedged AMD/MNQ after Webull refused those orders. Only OPEN/ADD, only on a
    // genuine failure (a resting "bid is in" is res.ok and stays).
    if (!res.ok && (sig.action === "OPEN" || sig.action === "ADD")) {
      await guardUnrecord(sig, msg.author);
    }
    // An entry is now an offer, not a purchase. Watch for what became of it —
    // this is what turns "bid is in" into "filled" or "nobody sold to you".
    if (res.ok) watchFills();
    // WHO called it and WHICH ROOM, right on the line (his ask, 8/11).
    const _cid = String(msg.channelId || "");
    const _room = CHAN_NAMES[_cid] || ROOM_LABELS[_cid] || sig.room || "";
    const _from = (sig.caller || msg.author || "?") + (_room ? " · " + _room : "");
    await addLog({ kind: res.ok ? "sent" : "failed",
                   // "(Swing)" rides the front of the line when the call said
                   // so (his ask, 8/17) — overnight hold, not a day trade.
                   what: (sig.swing ? "(Swing) " : "") + human(sig) + " x" + qty + " — " + _from,
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
        message: (_from + " — " + res.msg).slice(0, 140)
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
  // His call, reversed: LIVE now STAYS live across updates and restarts —
  // "everytime i push a new update my channels go all back to testing, i need
  // the popup to keep the live on." So this no longer wipes channel_live. A
  // room only leaves LIVE when he flips it himself, or via the STOP file /
  // master OFF, which still halt everything instantly. Kept as a named function
  // so the install/startup hooks don't need touching.
  return;
}

chrome.runtime.onInstalled.addListener(() => { scrubOldBanners(); allRoomsTesting(); badge(); reinject(); startWhopFeed(); });
chrome.runtime.onStartup.addListener(() => { scrubOldBanners(); allRoomsTesting(); badge(); reinject(); startWhopFeed(); });

/* MEMORY SHED (9/1, G: "sometimes I come back and Chrome has run out of
 * memory"). Discord web leaks: a room tab that starts at ~150 MB sits at
 * 0.5-2 GB after a few hours, and 26 of them is how the browser dies. A
 * reload resets a tab to fresh — and it is SAFE here: the content script
 * re-attaches, everything already on screen comes back flagged history
 * (never traded), and the stale-entry gate covers the rest. So: every
 * 30s tick, reload at most ONE Discord room tab whose last reload is 2h+
 * old — never the tab you're looking at, never a tab playing voice, and
 * never in the opening window (9:28-9:40). One tab per tick means a full
 * cycle of 26 rooms takes 13 minutes and no two rooms are ever blind at
 * once. Whop tabs have their own watchdog. */
const RELOADED_AT = {};                  // tabId -> last reload ts
const SHED_EVERY_MS = 4 * 60 * 60 * 1000;   // 4h (v3.5.0: heartbeat catches
                                            // dead readers in 90s, so the blind
                                            // rotation only fights RAM bloat)
async function memoryShed() {
  try {
    const now = new Date();
    const hm = now.getHours() * 60 + now.getMinutes();
    if (hm >= 9 * 60 + 28 && hm <= 9 * 60 + 40) return;   // the open is sacred
    const tabs = await chrome.tabs.query({ url: ["https://discord.com/channels/*",
                                                 "https://*.discord.com/channels/*"] });
    const t0 = Date.now();
    let oldest = null;
    for (const t of tabs) {
      if (!(t.id in RELOADED_AT)) RELOADED_AT[t.id] = t0;   // fresh tab = clock starts now
      if (t.active || t.audible || LISTENING.has(t.id)) continue;
      if (t0 - RELOADED_AT[t.id] < SHED_EVERY_MS) continue;
      if (!oldest || RELOADED_AT[t.id] < RELOADED_AT[oldest.id]) oldest = t;
    }
    if (!oldest) return;
    RELOADED_AT[oldest.id] = t0;
    await chrome.tabs.reload(oldest.id);
  } catch (e) { /* a closed tab mid-query — next tick */ }
}

/* DISCARD FIX + HEARTBEAT WATCHDOG (v3.5.0 A3.2, 9/2).
 * Chrome's Memory Saver DISCARDS background tabs. A discarded tab still
 * appears in tabs.query() with a normal URL, so every watchdog here
 * believed it was healthy — it has NO content script in it and reads
 * nothing. Two answers: (1) pin autoDiscardable=false on every room tab,
 * re-applied every tick because Chrome resets it whenever Discord
 * navigates; (2) content.js now heartbeats every 30s — a room that stops
 * answering for 3 beats gets reloaded in ~90s instead of the 40-minute
 * silence alarm wondering. */
const READER_BEAT = {};        // channelId -> last heartbeat ts
const READER_TAB = {};         // channelId -> tabId
const BEAT_DEAD_MS = 95000;    // 3 missed beats. Reload, don't wonder.
const REVIVED_AT = {};         // tabId -> last revive, so we don't loop

chrome.runtime.onMessage.addListener((m, sender) => {
  if (!m || m.type !== "READER_ALIVE") return;
  if (m.channelId) {
    READER_BEAT[m.channelId] = m.at || Date.now();
    if (sender && sender.tab) READER_TAB[m.channelId] = sender.tab.id;
  }
  if (m.listFound && !m.observing) {
    const tid = READER_TAB[m.channelId];
    if (tid && Date.now() - (REVIVED_AT[tid] || 0) > 60000) {
      REVIVED_AT[tid] = Date.now();
      addLog({ kind: "skipped", author: ROOM_LABELS[m.channelId] || m.channelId,
               text: "",
               why: "⚠ reader is running but its message watcher is detached — "
                    + "reloading that room" });
      try { chrome.tabs.reload(tid); } catch (e) { }
    }
  }
});

async function keepRoomsLoaded() {
  let tabs;
  try {
    tabs = await chrome.tabs.query({ url: ["https://discord.com/channels/*",
                                           "https://*.discord.com/channels/*"] });
  } catch (e) { return; }
  const now = Date.now();
  for (const t of tabs) {
    try { await chrome.tabs.update(t.id, { autoDiscardable: false }); }
    catch (e) { /* older Chrome, or the tab just closed */ }
    if (t.discarded) {
      if (now - (REVIVED_AT[t.id] || 0) < 60000) continue;
      REVIVED_AT[t.id] = now;
      const label = (String(t.url || "").match(/\/channels\/\d+\/(\d+)/) || [])[1];
      await addLog({ kind: "skipped",
                     author: ROOM_LABELS[label] || label || "room", text: "",
                     why: "⚠ Chrome had DISCARDED this room's tab to save "
                          + "memory — it was reading nothing. Reloaded." });
      RELOADED_AT[t.id] = now;        // counts as this tab's shed too
      try { await chrome.tabs.reload(t.id); } catch (e) { }
    }
  }
  // Rooms that once beat and went quiet — every room that ever reported,
  // not just the hand-labelled ones.
  for (const cid of Object.keys(READER_BEAT)) {
    const last = READER_BEAT[cid];
    if (now - last < BEAT_DEAD_MS) continue;
    const tid = READER_TAB[cid];
    if (!tid) continue;
    if (now - (REVIVED_AT[tid] || 0) < 60000) continue;
    // still open? a closed tab just stops beating — nothing to revive
    let alive = null;
    try { alive = await chrome.tabs.get(tid); } catch (e) { alive = null; }
    if (!alive) { delete READER_BEAT[cid]; delete READER_TAB[cid]; continue; }
    REVIVED_AT[tid] = now;
    await addLog({ kind: "skipped", author: ROOM_LABELS[cid] || cid, text: "",
                   why: "⚠ this room's reader stopped answering ("
                        + Math.round((now - last) / 1000) + "s). Reloading it "
                        + "now instead of waiting 40 minutes to notice." });
    try { await chrome.tabs.reload(tid); } catch (e) { }
  }
}

/* WHOP API FEED bootstrap (8/30): the offscreen page runs the 2s poll of
 * the bridge's /whopfeed (a service worker can't hold a timer that fast).
 * FEED_ACTIVE pings from offscreen tell the MESSAGE handler whether tab
 * reads should stand down. Dark until settings.json whop.api_key exists. */
let WHOP_API_ACTIVE = false;
chrome.runtime.onMessage.addListener((m) => {
  if (m && m.type === "FEED_ACTIVE") WHOP_API_ACTIVE = !!m.active;
});
async function startWhopFeed() {
  try {
    await ensureOffscreen();
    const c = await cfg();
    chrome.runtime.sendMessage({ target: "offscreen", type: "FEED_START",
                                 base: bridgeBaseFrom(c.bridge_url) });
  } catch (e) { /* offscreen races are harmless — voice will ensure it too */ }
}
startWhopFeed();
badge();
reinject();
checkBuild();
checkBridgeHealth();
