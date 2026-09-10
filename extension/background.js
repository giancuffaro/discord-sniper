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

/* SECOND MACHINE (9/9, G: "another account on a different computer for other
 * subs"). ONE bridge, ONE book: a second PC runs only Chrome + this extension
 * and talks to PC1's bridge over the LAN. Per-machine wiring lives in ONE
 * optional file next to rooms.txt — extension/bridge.txt, gitignored:
 *     http://192.168.1.10:8787|the-shared-secret
 * No file = today's behaviour (loopback, no token). With it, every call to the
 * bridge carries X-Sniper-Token; the bridge refuses off-loopback callers that
 * don't. Wrapping fetch here covers all eleven call sites at once. */
let BRIDGE_TOKEN = "";
let BRIDGE_ORIGIN = "";
const _rawFetch = self.fetch.bind(self);
self.fetch = function (input, init) {
  try {
    const u = typeof input === "string" ? input : String((input && input.url) || "");
    if (BRIDGE_TOKEN && BRIDGE_ORIGIN && u.startsWith(BRIDGE_ORIGIN)) {
      init = Object.assign({}, init || {});
      if (init.headers && typeof init.headers.append === "function") {
        init.headers = new Headers(init.headers);
        init.headers.set("X-Sniper-Token", BRIDGE_TOKEN);
      } else {
        init.headers = Object.assign({}, init.headers || {}, { "X-Sniper-Token": BRIDGE_TOKEN });
      }
    }
  } catch (e) {}
  return _rawFetch(input, init);
};

async function loadBridgeFile() {
  let txt = "";
  try { txt = await (await _rawFetch(chrome.runtime.getURL("bridge.txt"))).text(); }
  catch (e) { return; }                       // no file = this PC, loopback
  const line = (txt.split("\n").map(s => s.trim()).find(s => s && !s.startsWith("#")) || "");
  if (!line) return;
  const [url, token] = line.split("|").map(s => (s || "").trim());
  if (!/^https?:\/\//.test(url)) return;
  BRIDGE_TOKEN = token || "";
  try { BRIDGE_ORIGIN = new URL(url).origin; } catch (e) { BRIDGE_ORIGIN = ""; }
  try {
    const { settings } = await chrome.storage.local.get("settings");
    const s = settings || {};
    const want = url.replace(/\/$/, "") + "/order";
    if (s.bridge_url !== want || s.bridge_token !== BRIDGE_TOKEN) {
      s.bridge_url = want;
      s.bridge_token = BRIDGE_TOKEN;
      await chrome.storage.local.set({ settings: s });
    }
  } catch (e) {}
}
loadBridgeFile();
// 400 was NOT a full day (9/2: the day's export started at 10:51 — every
// morning verdict was gone, so a 9:38 entry that never fired couldn't be
// audited). Today ran ~450 verdicts by the close; 2500 covers a loud day
// with room to spare, and the popup only renders the newest slice anyway.
const LOG_MAX = 2500;

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

/* RECORD_ONLY = rooms captured to the export file and NEVER traded: no parse,
 * no guards, no orders, whatever the settings say. Hard-coded so a wiped
 * settings box can't arm a room by accident. It is EMPTY today — Aristotle's
 * and Midas were the last two in it, and both graduated once the parser was
 * tuned on their wording; they trade live like every other Discord room.
 * Put an id back here only to re-park a room for capture-only. */
/* The Whop rooms that trade now: Day Trades, Futures, High Risk, 2K Challenge.
 * Matched by slug AND hash so the URL shape never matters. Swings are paused
 * since 9/4 and Whop Swing Trades was cut 9/7 — the swing/long-term rows below
 * stay only so an old URL still resolves to a name. Felony's rooms post bare
 * percentages as PROGRESS ("65% on NVDA"), not trims — the verb decides — so
 * every whop room parses with bare_pct_trims off. Unknown whop rooms stay
 * capture-only until they're named here. */
// shortName (lowercased) -> {url, id}. Filled by loadRoomsFile() so the
// popup can jump straight to a room's tab. See the FOCUS-ROOM handler.
const ROOM_TABS = {};
/* The LIVE room ids from rooms.txt, filled by loadRoomsFile(). rooms.txt is
 * the one list, so anything that needs "which rooms are actually running"
 * reads this — NOT Object.keys(ROOM_LABELS), which is a hand-typed name map
 * carrying every room ever wired, cut ones included (9/9: that mistake was
 * firing ~40 false "silent 40 min" alarms a day for rooms with no tab). */
const LIVE_ROOM_IDS = new Set();

// Rooms parked because the subscription lapsed. Filled by loadRoomsFile()
// from lines whose state is `lapsed`. They do not open and do not trade — but they are
// still known, so accessCheck() can test them and wake them by itself.
const SLEEPING = [];

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
 * testing." SHADOW is EMPTY, so no room is silenced here. And since 9/8 a
 * graduated room is LIVE by default (roomLive = _lv !== false): real money
 * moves unless he flips that room to TESTING in the popup. There is no master
 * REAL-money switch any more — it was retired; the per-room toggle is the only
 * arm. The set stays here for the next new room that needs a proving day. */
const SHADOW = new Set([
  // PROBATION: read for real, judged in the log ("would have read this
  // as…"), fires NOTHING. A new server proves itself here first.
  //
  // GRADUATED 9/2 (his call, after the corpus replay showed the cost):
  // 911389167169191946 Platinum-1 nitro, 911390080285962290 Platinum-2
  // futures-alerts, 1086120203009658982 Platinum-3 day-trades,
  // 1533885258724937739 Platinum-4 ei-alerts, 983807207625859143
  // Platinum equity-swings, 1537061197931618344 NGD ngd-trades.
  // Between them, 106 read-and-graded entries in 10 days never fired —
  // that, not a parser gap, was the "40 signals / 0 sent" on the
  // scoreboard. They now route like every other room: TEST unless the
  // popup has them LIVE. Add an id back here to re-benchmark a room.
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
/* BORN TESTING — RETIRED 9/8. The set is empty, so the generation sweep below
 * is a no-op. Kept (not deleted) so the gate code stays valid; see the note on
 * BORN_TESTING itself for what would have to happen to use it again.
 */
const BORN_TESTING_GEN = "2026-09-08b";
// TURNED OFF 9/8, G: "why were they ever testing? make everything live, let me
// choose if i turn them off with the tab." Born-testing was MY guardrail, not
// his rule — his rule (8/23) is that an OPEN TAB IS THE ON SWITCH and every
// room is LIVE unless he flips it to testing in the popup. This set is now
// EMPTY, so roomLive falls straight through to `_lv !== false` — live by
// default, his popup choice wins, closing the tab is how he turns one off.
// Left as an empty set (not deleted) so the gate code below stays valid; put
// an id back here AND bump BORN_TESTING_GEN only if he ever asks for it again.
const BORN_TESTING = new Set([]);

// ALL-LIVE one-shot (9/8, his call: "clear ALL test flags — make every
// currently-test room live at once"). Bump this string to sweep again.
const ALL_LIVE_GEN = "2026-09-09-alllive";   // 9/9: 7 rooms re-added — "make sure they are live"
async function applyBornTesting() {
  try {
    const { settings } = await chrome.storage.local.get("settings");
    const s = settings || {};
    const cl = s.channel_live || {};
    let cleared = 0;
    let touched = false;

    // (1) BORN_TESTING generation sweep — clears the listed reopened ids once.
    if (s.born_testing_gen !== BORN_TESTING_GEN) {
      for (const id of BORN_TESTING) {
        if (Object.prototype.hasOwnProperty.call(cl, id)) { delete cl[id]; cleared++; }
      }
      s.born_testing_gen = BORN_TESTING_GEN;
      touched = true;
    }

    // (2) ALL-LIVE sweep — deletes EVERY explicit channel_live=false so every
    // room falls through to live-by-default (roomLive = _lv !== false). One
    // shot per generation: after this, a room only goes back to TESTING when he
    // flips it in the popup, and that fresh false sticks because this sweep is
    // marked done and won't run again.
    if (s.all_live_gen !== ALL_LIVE_GEN) {
      for (const id of Object.keys(cl)) {
        if (cl[id] === false) { delete cl[id]; cleared++; }
      }
      s.all_live_gen = ALL_LIVE_GEN;
      touched = true;
    }

    if (!touched) return 0;
    s.channel_live = cl;
    await chrome.storage.local.set({ settings: s });
    if (cleared) {
      await addLog({ kind: "sent", what: "ALL LIVE",
        why: cleared + " room(s) were carrying a TEST flag. Cleared — every open "
           + "tab is now LIVE. Flip a room to TESTING in the popup any time and "
           + "it will stick." });
    }
    return cleared;
  } catch (e) { return 0; }
}

let _roomsPromise = null;

/* IS THAT A TICKER, OR A WORD FROM THE MESSAGE? (9/8)
 *
 * optionable.txt is THE list of symbols this bot may trade — 6,337 option
 * roots pulled from the broker's own universe by refresh_optionable.py, plus
 * futures and cash indexes. Read HERE and by bridge.py: one file, two readers,
 * no drift. Same rule as rooms.txt.
 *
 * The reader treats a capitalised word in front of a strike as a ticker, which
 * is right almost always and catastrophic occasionally:
 *     "...then can go with 773c."          -> OPEN WITH 773C, at market
 *     "| EXIT ALERT Ticker: NBIS Stopped"  -> CLOSE EXIT (the real one: NBIS)
 * Blocking words one at a time never converges — blocking VERY moved the
 * misread to GREEN, and "PROFITS FROM JUNE" produced ticker JUNE.
 *
 * FAILS OPEN. If the file is missing or short, everything is allowed and the
 * log says so once. bridge.py checks again anyway, so a browser that failed to
 * load a text file can never become a silent trading halt.
 */
let _symsPromise = null;
function loadOptionable() {
  if (_symsPromise) return _symsPromise;
  _symsPromise = (async () => {
    try {
      const r = await fetch(chrome.runtime.getURL("optionable.txt"));
      const txt = await r.text();
      const set = new Set();
      for (const line of txt.split("\n")) {
        const s = line.trim().toUpperCase();
        if (s && s[0] !== "#") set.add(s);
      }
      // Under a thousand means the file is truncated; an unusable list must
      // not become a blocklist for everything.
      if (set.size < 1000) {
        await addLog({ kind: "failed", what: "OPTIONABLE",
          why: "optionable.txt has only " + set.size + " symbols — too short to "
             + "trust, so the ticker check is OFF. Run refresh_optionable.py." });
        return null;
      }
      return set;
    } catch (e) {
      try {
        await addLog({ kind: "failed", what: "OPTIONABLE",
          why: "couldn't read optionable.txt (" + String(e).slice(0, 90) + ") — "
             + "the ticker check is OFF until it loads." });
      } catch (e2) {}
      return null;
    }
  })();
  return _symsPromise;
}
async function tradeableSymbol(sym) {
  if (!sym) return true;
  const set = await loadOptionable();
  if (!set) return true;                       // fail open
  return set.has(String(sym).trim().toUpperCase());
}
/* ACCESS PROBE (9/7) — knock on every sleeping room's door, once a day.
 *
 * His ask: park the rooms he can't read, and have the app notice by itself
 * when a subscription comes back so those rooms just start working again.
 *
 * HOW IT TELLS: open the room in a BACKGROUND tab, give Discord/Whop time
 * to render, then ask the content script how many message rows it can see.
 * A room you have access to renders rows. A room you don't renders none.
 * That is the same `rows` number the reader already reports every 30s in
 * _readerHealth(), so this adds no new way of being wrong.
 *
 * DELIBERATELY CONSERVATIVE:
 *  - one room per run, never a burst of tabs on his machine
 *  - only outside market hours; a probe tab during the open would compete
 *    with the rooms that are actually trading
 *  - it does NOT auto-uncomment rooms.txt. It TELLS him, loudly, and the
 *    popup offers the wake. Turning a room back on is a money decision:
 *    that room starts feeding real alerts again, and per the house rule
 *    those stay his. Waking is one click, not a surprise.
 *  - a sleeping room is NEVER traded while parked, even if the probe finds
 *    it readable — the probe closes its own tab straight after.
 */
const PROBE_EVERY_MS = 22 * 60 * 60 * 1000;      // ~daily, drifts off-peak
const PROBE_SETTLE_MS = 25000;                   // let the app actually paint

/* DISCORD ANSWERS THE QUESTION OUTRIGHT — use that, not a row count.
 *
 * Opening all five sleeping rooms by hand on 9/7 showed three DIFFERENT
 * shapes of "no", and only one of them is "zero rows":
 *
 *   RWGates          title "#alert-room | Summit Trading Strategies"  ACCESS
 *   Boka 2 and 3     title "No Access | BOKA Trading"                 REFUSED
 *   Boka 1           url REDIRECTED to #start-here                    REFUSED
 *   Options Insider  url redirected to /channels/@me                  NOT IN IT
 *
 * The title and the URL are both decisive and both arrive in seconds. A row
 * count is the weakest of the three: a real room that is simply quiet also
 * has few rows, and a slow render looks identical to a locked door.
 * Check the strong signals first and only fall back to counting.
 */
async function probeOne(room) {
  let tab = null;
  try {
    tab = await chrome.tabs.create({ url: room.url, active: false });
  } catch (e) { return null; }
  try {
    await new Promise(r => setTimeout(r, PROBE_SETTLE_MS));
    let info = null;
    try { info = await chrome.tabs.get(tab.id); } catch (e) {}
    const title = String((info && info.title) || "");
    const url = String((info && info.url) || "");

    // Discord said it in words.
    if (/no access/i.test(title)) return { ok: false, why: 'Discord says "No Access"' };
    // Bounced out of the channel entirely — the friends list, or another room.
    if (room.id && url && !url.includes(room.id)) {
      return { ok: false, why: url.includes("/channels/@me")
        ? "bounced to your friends list — you are not in that server"
        : "bounced to a different channel — no access to this one" };
    }
    // Still on the room, so ask how much of it rendered.
    let rows = 0;
    try {
      const res = await chrome.tabs.sendMessage(tab.id, { type: "HEALTH?" });
      rows = (res && res.rows) || 0;
    } catch (e) { rows = 0; }
    return rows > 0
      ? { ok: true, why: rows + " messages on screen", rows: rows }
      : { ok: false, why: "the room loaded but rendered nothing" };
  } finally {
    try { if (tab && tab.id) await chrome.tabs.remove(tab.id); } catch (e) {}
  }
}

/* REVOKED WHILE YOU WERE PAYING (9/7). The mirror image of the probe, and
 * the half that costs money: a room you are subscribed to quietly loses
 * access — the seller re-rolls permissions, a bot mis-fires, a renewal
 * fails — and the tab just sits there reading nothing. The bot cannot tell
 * that from a quiet morning.
 *
 * No tabs are opened here. The room tabs are ALREADY open, and Discord
 * writes the answer in the title: "No Access | BOKA Trading". Read the
 * titles we already have. Zero cost, and it fires the day it happens
 * instead of whenever someone next reads an export.
 */
async function revokeCheck() {
  try {
    await loadRoomsFile();
    const tabs = await chrome.tabs.query({ url: ["https://discord.com/*",
                                                 "https://*.discord.com/*"] });
    const { revoked_seen } = await chrome.storage.local.get("revoked_seen");
    const seen = revoked_seen || {};
    let changed = false;
    for (const t of tabs) {
      const title = String(t.title || "");
      if (!/no access/i.test(title)) continue;
      const url = String(t.url || "");
      const id = (url.match(/\/channels\/\d+\/(\d+)/) || [])[1];
      if (!id) continue;
      if (seen[id]) continue;                    // already told him once
      seen[id] = Date.now(); changed = true;
      const label = roomName(id) || id;
      await addLog({ kind: "failed", what: "ACCESS LOST",
        why: "🔒 " + label + " now says \"No Access\" — you are still opening " +
             "this room and it is reading NOTHING. If you pay for it, the " +
             "subscription or the seller's Discord role has gone. Check it, " +
             "then either fix it or switch the room OFF in the popup." });
      try {
        chrome.notifications.create({ type: "basic", iconUrl: "icon128.png",
          title: "🔒 " + label + " — access lost",
          message: "That room is open but reading nothing. Check the sub." });
      } catch (e) {}
    }
    if (changed) await chrome.storage.local.set({ revoked_seen: seen });
  } catch (e) { /* never break the reader */ }
}

async function accessCheck(force) {
  try {
    const { probe_at } = await chrome.storage.local.get("probe_at");
    const now = Date.now();
    if (!force && probe_at && now - probe_at < PROBE_EVERY_MS) return;
    // Market hours are for trading, not for probing.
    const et = new Date(new Date().toLocaleString("en-US",
                        { timeZone: "America/New_York" }));
    const mins = et.getHours() * 60 + et.getMinutes();
    const weekday = et.getDay() >= 1 && et.getDay() <= 5;
    if (!force && weekday && mins > 9 * 60 && mins < 16 * 60 + 30) return;

    await loadRoomsFile();
    if (!SLEEPING.length) return;
    const { probe_i } = await chrome.storage.local.get("probe_i");
    const i = ((probe_i || 0) % SLEEPING.length);
    const room = SLEEPING[i];
    await chrome.storage.local.set({ probe_at: now, probe_i: i + 1 });

    const v = await probeOne(room);
    if (!v) return;
    if (v.ok) {
      await addLog({ kind: "sent", what: "ACCESS BACK",
        why: "🔓 " + room.name + " is READABLE again — " + v.why + ". It was " +
             "parked because: " + room.why + ". Still asleep and still not " +
             "trading: switch it ON in the popup's Channels tab to wake it." });
      try {
        chrome.notifications.create({ type: "basic",
          iconUrl: "icon128.png", title: "🔓 " + room.name + " is back",
          message: v.why + ". Still parked — switch it on in the popup." });
      } catch (e) {}
    } else {
      await addLog({ kind: "ignored", what: "ACCESS CHECK",
        why: "🔒 " + room.name + " — " + v.why + ". Staying asleep." });
    }
  } catch (e) { /* a probe must never break the reader */ }
}

/* EVERY room rooms.txt knows, in file order, each {id, url, name, group,
 * state} with state on|off|lapsed. The popup's Channels tab is drawn from
 * this (one switch per room, 9/9 — G: "a list of all the rooms we've been
 * to and the option to open the tab or not; if I selected to open it I
 * obviously want it live"). */
const ALL_ROOMS = [];

function loadRoomsFile() {
  if (_roomsPromise) return _roomsPromise;
  _roomsPromise = (async () => {
    try {
      const r = await fetch(chrome.runtime.getURL("rooms.txt"), { cache: "no-store" });
      const text = await r.text();
      const ids = [];
      SLEEPING.length = 0;
      LIVE_ROOM_IDS.clear();
      ALL_ROOMS.length = 0;
      for (const k of Object.keys(ROOM_TABS)) delete ROOM_TABS[k];
      let lastComment = "";
      for (const line of text.split("\n")) {
        const t = line.trim();
        if (!t) { lastComment = ""; continue; }
        if (t.startsWith("#")) { lastComment = t.replace(/^#\s*/, ""); continue; }
        // rooms.txt is id|url|shortName|group|state (9/9). A line with no
        // 5th field is `on` — that is what every line was before the state
        // column existed, so an old file keeps meaning what it meant.
        const parts = t.split("|").map(s => s.trim());
        const id = parts[0];
        if (!id) continue;
        const state = (parts[4] || "on").toLowerCase();
        const name = parts[2] || id;
        const why = state === "on" ? "" : lastComment;
        lastComment = "";
        // 6th field (9/9): per-room rules — spx / bare / sym=XXX (see bridge read_rooms)
        const rules = (parts[5] || "").split(",").map(x => x.trim().toLowerCase()).filter(Boolean);
        ALL_ROOMS.push({ id: id, url: parts[1] || "", name: name,
                         group: parts[3] || "Other rooms", state: state, why: why, rules: rules });
        // rooms.txt wins over the hand-typed ROOM_LABELS map (9/9). That map
        // was missing 7 rooms that are live right now — Platinum nitro /
        // futures-alerts / day-trades / ei-alerts, Brando, Shoof, OWLS
        // all-alerts — so their trades rode to the bridge with sig.room set
        // to a bare channel id, landing in the ledger as an unnamed room.
        if (parts[2]) ROOM_LABELS[id] = parts[2];
        if (state === "lapsed") {
          // LAPSED (was "#SLEEP|" until 9/9): parked because the subscription
          // ran out. Not opened, not traded — but the access probe knocks on
          // its door once a day (accessCheck) and says when it is readable
          // again. Waking it is G's click on the popup switch.
          SLEEPING.push({ why: why || "subscription lapsed", id: id,
                          url: parts[1] || "", name: name });
          continue;
        }
        if (state !== "on") continue;              // off = benched, nothing
        ids.push(id); LIVE_ROOM_IDS.add(id);
        // JUMP TO THE ROOM (9/4, his ask: "I wanna see how the alert was
        // emitted but I can't find the tab because so many of them").
        // A position's `room` IS the shortName — so keep url+id per name and
        // the popup can send one click straight to the tab. `on` rooms only:
        // this map is also what openMissingRooms() opens.
        if (parts[2]) ROOM_TABS[parts[2].toLowerCase()] = { url: parts[1], id: id };
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

/* Re-read rooms.txt NOW (after a popup flip, or on the minute sweep so the
 * other Chrome profile sees a flip made in this one). Cheap: one local
 * fetch. Replaces the cached list wholesale — never merges. */
async function reloadRooms() {
  _roomsPromise = null;
  return loadRoomsFile();
}
/* ===== SELF-SERVE (test build 9/9) — room rules, needs-you, fix-it =====
 * Delete this block and the popup's Callers / Needs-you tabs to remove. */
async function setRoomRules(id, rules) {
  try {
    const { settings } = await chrome.storage.local.get("settings");
    const base = bridgeBaseFrom((settings || {}).bridge_url || BRIDGE_DEFAULT);
    const r = await fetch(base + "/rooms", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: String(id), rules: String(rules || "") }) });
    const j = await r.json();
    if (!j || j.ok === false) return { ok: false, why: (j && j.why) || "the bridge refused it" };
  } catch (e) {
    return { ok: false, why: "the bridge isn't reachable — nothing changed" };
  }
  await reloadRooms();
  await refreshBridgeChannels().catch(() => {});
  const room = ALL_ROOMS.find(x => x.id === String(id));
  await addLog({ kind: "sent", what: "ROOM RULES",
    why: ((room && room.name) || id) + " → " + ((room && room.rules.join(", ")) || "no special rules") });
  return { ok: true, why: "saved — the parser uses it on the next message" };
}

/* What is waiting on G, from the extension's side. Cheap, local, honest. */
async function needsFromExtension() {
  const items = [];
  try {
    await loadRoomsFile();
    let lane = "";
    try { lane = (await chrome.storage.local.get("profile_lane")).profile_lane || ""; } catch (e) {}
    const tabs = await chrome.tabs.query({ url: ["https://discord.com/*", "https://*.discord.com/*",
                                                 "https://whop.com/*"] });
    const now = Date.now();
    const et = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" }));
    const mins = et.getHours() * 60 + et.getMinutes();
    const marketOpen = et.getDay() >= 1 && et.getDay() <= 5 && mins >= 9 * 60 + 30 && mins < 16 * 60;
    for (const room of ALL_ROOMS) {
      if (room.state !== "on") continue;
      const isWhop = /^whop:/i.test(room.id) || /whop\.com/i.test(room.url);
      if (lane && (lane === "whop") !== isWhop) continue;
      if (!roomWantsTab(room)) continue;               // closed for the night on purpose
      const mine = await roomTabsFor(room);
      if (!mine.length) {
        items.push({ what: room.name + " is ON but has no tab in this browser", fix: "open_missing" });
        continue;
      }
      if (mine.some(t => /no access/i.test(String(t.title || "")))) {
        items.push({ what: room.name + " says \"No Access\" — the subscription or role is gone; switch it off (or to lapsed) in Channels", fix: null });
        continue;
      }
      const beat = READER_BEAT[room.id] || 0;
      if (marketOpen && now - beat > 3 * 60000) {
        items.push({ what: room.name + " tab is open but its reader hasn't beaten in " +
                           (beat ? Math.round((now - beat) / 60000) + " min" : "a while"), fix: "reload_readers" });
      }
    }
    const { build_waiting, build_stamp } = await chrome.storage.local.get(["build_waiting", "build_stamp"]);
    if (build_waiting && build_waiting !== build_stamp) {
      items.push({ what: "a new extension build is waiting for a safe window (market open or an order in flight)", fix: "reload_extension" });
    }
  } catch (e) {
    items.push({ what: "needs-you check hit an error: " + String(e).slice(0, 100), fix: null });
  }
  return items;
}

async function fixIt(what) {
  try {
    if (what === "open_missing") {
      const n = await openMissingRooms();
      return { ok: true, why: "opened " + (n || 0) + " room tab(s)" + (n >= 3 ? " — a few per pass, click again for more" : "") };
    }
    if (what === "reload_readers") {
      await loadRoomsFile();
      const now = Date.now();
      let n = 0;
      for (const room of ALL_ROOMS) {
        if (room.state !== "on") continue;
        if (now - (READER_BEAT[room.id] || 0) < 3 * 60000) continue;      // beating: leave it
        const tabs = await roomTabsFor(room);
        for (const t of tabs) {
          try { await chrome.tabs.reload(t.id); n++; RELOADED_AT[t.id] = now; } catch (e) {}
          await new Promise(res => setTimeout(res, 6000));                 // one gateway session per 5 s
        }
      }
      return { ok: true, why: "reloaded " + n + " dead reader tab(s)" };
    }
    if (what === "reload_extension") {
      await chrome.storage.local.set({ build_waiting: "" });
      setTimeout(() => chrome.runtime.reload(), 300);
      return { ok: true, why: "reloading the extension now" };
    }
  } catch (e) { return { ok: false, why: String(e).slice(0, 120) }; }
  return { ok: false, why: "unknown fix " + what };
}

/* ROOM HOURS (9/9 evening, G: "open the rooms at 9:15 and close them at
 * 4:30 PM since we can't follow any alert then — so we don't bomb Discord
 * with pings. Keep the futures channels always open"). An `on` room gets a
 * tab only inside the window, unless its rules carry `always` (the futures
 * rooms). Weekends and market holidays are outside the window. The Discord
 * gateway sees ~15 fewer sessions for 17 of every 24 hours. */
const ROOM_HOURS = { open: 9 * 60 + 15, close: 16 * 60 + 30 };     // ET
function roomWindowOpen() {
  try {
    const p = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York",
      hour12: false, weekday: "short", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit" }).formatToParts(new Date());
    const g = t => (p.find(x => x.type === t) || {}).value || "";
    if (["Sat", "Sun"].includes(g("weekday"))) return false;
    if (MARKET_HOLIDAYS.has(g("year") + "-" + g("month") + "-" + g("day"))) return false;
    const m = parseInt(g("hour"), 10) * 60 + parseInt(g("minute"), 10);
    return m >= ROOM_HOURS.open && m < ROOM_HOURS.close;
  } catch (e) { return true; }        // a clock bug must never close the rooms
}
function roomAlways(room) { return (room.rules || []).includes("always"); }
function roomWantsTab(room) { return room.state === "on" && (roomAlways(room) || roomWindowOpen()); }
/* Closing happens at the BOUNDARY (the moment the window shuts, and once at
 * startup if it is already shut) — not on every pass. So a room G opens by
 * hand at night to read stays open; it is only the 4:30 sweep that clears
 * the day's tabs. Opening happens on every pass inside the window (the
 * switch is the bench, a tab closed by hand during hours comes back). */
let _schedState = null;             // last seen window state; null = first pass
async function _keepWindowAlive(tab) {
  /* Never let a close take the window's LAST tab — that closes the window,
   * and with it this Chrome profile (no more extension, no futures rooms).
   * Put the dashboard page in its place. */
  try {
    const all = await chrome.tabs.query({ windowId: tab.windowId });
    if (all.length <= 1) {
      await chrome.tabs.create({ windowId: tab.windowId,
        url: chrome.runtime.getURL("popup.html?page=1"), active: true });
    }
  } catch (e) {}
}
async function roomSchedule() {
  try {
    await loadRoomsFile();
    let lane = "";
    try { lane = (await chrome.storage.local.get("profile_lane")).profile_lane || ""; } catch (e) {}
    const open = roomWindowOpen();
    const sweep = !open && (_schedState === null || _schedState === true);
    _schedState = open;
    let opened = 0, closed = 0;
    const now = Date.now();
    for (const room of ALL_ROOMS) {
      if (room.state !== "on") continue;
      const isWhop = /^whop:/i.test(room.id) || /whop\.com/i.test(room.url);
      if (lane && (lane === "whop") !== isWhop) continue;
      if (!lane) {                                    // lane not settled: the old soft rule
        const tabs0 = await chrome.tabs.query({ url: isWhop
          ? ["https://whop.com/joined/*", "https://whop.com/*/exp_*"]
          : ["https://discord.com/channels/*", "https://*.discord.com/channels/*"] });
        if (!tabs0.length) continue;                  // this surface isn't ours (yet)
      }
      const want = roomWantsTab(room);
      const tabs = await roomTabsFor(room);
      if (want && !tabs.length && room.url) {
        if (opened >= 3) continue;                    // a few per pass
        if (now - (ROOM_OPENED_AT[room.id] || 0) < 120000) continue;
        ROOM_OPENED_AT[room.id] = now;
        try { await chrome.tabs.create({ url: room.url, active: false }); opened++; } catch (e) {}
        await new Promise(res => setTimeout(res, 6000));   // one gateway session per 5 s
      } else if (!want && tabs.length && sweep) {
        for (const t of tabs) {
          await _keepWindowAlive(t);
          try { await chrome.tabs.remove(t.id); closed++; } catch (e) {}
        }
      }
    }
    if (opened) await addLog({ kind: "sent", what: "ROOM HOURS",
      why: "opened " + opened + " room tab(s) — the window is open (9:15-4:30 ET)" });
    if (closed) await addLog({ kind: "sent", what: "ROOM HOURS",
      why: "closed " + closed + " room tab(s) for the night — back at 9:15 ET; " +
           "rooms marked 24h stay open" });
  } catch (e) {}
}

/* THE OTHER PROFILE SEES THE FLIP (9/9). Both Chromes read the same
 * rooms.txt. A switch flipped in one profile's popup is written to the file
 * by the bridge; this poll (every 30 s, on the watch-build alarm) notices
 * the file changed and makes THIS profile's tabs follow for the rooms of
 * its own lane: newly-on rooms open, newly-off rooms close. Only ever on a
 * CHANGE of the file — never a continuous healer, so nothing reopens on its
 * own between edits. */
let _roomsStampSeen = "";
async function pollRoomsFile() {
  try {
    const r = await fetch(chrome.runtime.getURL("rooms.txt"), { cache: "no-store" });
    const text = await r.text();
    const stamp = text.length + ":" + [...text].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
    if (_roomsStampSeen && stamp !== _roomsStampSeen) {
      const before = new Set(LIVE_ROOM_IDS);
      await reloadRooms();
      let lane = "";
      try { lane = (await chrome.storage.local.get("profile_lane")).profile_lane || ""; } catch (e) {}
      let opened = 0, closed = 0;
      for (const room of ALL_ROOMS) {
        const isWhop = /^whop:/i.test(room.id) || /whop\.com/i.test(room.url);
        if (lane && (lane === "whop") !== isWhop) continue;   // the other browser's room
        const wasOn = before.has(room.id), isOn = room.state === "on";
        if (wasOn === isOn) continue;
        const tabs = await roomTabsFor(room);
        if (isOn && roomWantsTab(room) && !tabs.length && room.url) {
          if (Date.now() - (ROOM_OPENED_AT[room.id] || 0) < 120000) continue;
          ROOM_OPENED_AT[room.id] = Date.now();
          try { await chrome.tabs.create({ url: room.url, active: false }); opened++; } catch (e) {}
          await new Promise(res => setTimeout(res, 6000));   // one gateway session per 5 s
        } else if (!isOn) {
          for (const t of tabs) { await _keepWindowAlive(t); try { await chrome.tabs.remove(t.id); closed++; } catch (e) {} }
        }
      }
      await addLog({ kind: "sent", what: "ROOMS",
        why: "rooms.txt changed — " + LIVE_ROOM_IDS.size + " room(s) on now" +
             (opened ? ", opened " + opened : "") + (closed ? ", closed " + closed : "") });
    }
    _roomsStampSeen = stamp;
  } catch (e) {}
}

/* THE ONE SWITCH (9/9). Flip a room on/off: the bridge rewrites its line
 * in rooms.txt (the one list), this profile re-reads the file, and the tab
 * follows — ON opens it (in the profile that owns that surface), OFF closes
 * it and the room stops being read or traded. Returns {ok, why}. */
async function roomTabsFor(room) {
  const key = String(room.id || "").replace(/^whop:/, "");
  const idInUrl = (String(room.url || "").match(/\/channels\/\d+\/(\d+)/) || [])[1]
               || (String(room.url || "").match(/exp_[a-z0-9]+/i) || [])[0] || key;
  let tabs = [];
  try {
    tabs = await chrome.tabs.query({ url: ["https://discord.com/channels/*",
                                           "https://*.discord.com/channels/*",
                                           "https://whop.com/joined/*",
                                           "https://whop.com/*/exp_*"] });
  } catch (e) { return []; }
  return tabs.filter(t => String(t.url || "").includes(idInUrl));
}

async function setRoomState(id, on) {
  const state = on ? "on" : "off";
  let list = null;
  try {
    const { settings } = await chrome.storage.local.get("settings");
    const base = bridgeBaseFrom((settings || {}).bridge_url || BRIDGE_DEFAULT);
    const r = await fetch(base + "/rooms", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: String(id), state: state }) });
    list = await r.json();
    if (!list || list.ok === false) {
      return { ok: false, why: (list && list.why) || "the bridge refused the change" };
    }
  } catch (e) {
    return { ok: false, why: "the bridge isn't reachable — it writes rooms.txt, " +
                             "so nothing changed. Start it (START HERE) and flip again." };
  }
  // rooms.txt is written; rooms.txt inside the extension folder IS that file,
  // so a fresh read sees the new state straight away.
  await reloadRooms();
  refreshBridgeChannels().catch(() => {});
  const room = ALL_ROOMS.find(x => x.id === String(id));
  if (!room) return { ok: false, why: "room " + id + " isn't in rooms.txt after the write" };
  // a room that is on is LIVE — clear any old TESTING flag it may carry
  try {
    const { settings } = await chrome.storage.local.get("settings");
    const s = settings || {};
    const cl = s.channel_live || {};
    if (on && cl[room.id] === false) { delete cl[room.id]; s.channel_live = cl;
      await chrome.storage.local.set({ settings: s }); }
  } catch (e) {}
  const isWhop = /^whop:/i.test(room.id) || /whop\.com/i.test(room.url);
  let lane = "";
  try { lane = (await chrome.storage.local.get("profile_lane")).profile_lane || ""; } catch (e) {}
  const mine = !lane || (lane === "whop") === isWhop;
  if (!on) {
    const tabs = await roomTabsFor(room);
    for (const t of tabs) { await _keepWindowAlive(t); try { await chrome.tabs.remove(t.id); } catch (e) {} }
    await addLog({ kind: "sent", what: "ROOM OFF",
      why: room.name + " switched OFF — " + (tabs.length ? "closed its tab, " : "") +
           "not read, not traded, until you switch it back on." });
    return { ok: true, why: room.name + " is off" + (tabs.length ? " — tab closed" : "") +
                            (mine ? "" : " (its tab lives in the other browser; it closes there within a minute)") };
  }
  if (!mine) {
    await addLog({ kind: "sent", what: "ROOM ON",
      why: room.name + " switched ON — its tab belongs to the " + (isWhop ? "Whop" : "Discord") +
           " browser, which opens it within a minute (or run START HERE)." });
    return { ok: true, why: room.name + " is on — its tab opens in the " +
                            (isWhop ? "Whop" : "Discord") + " browser" };
  }
  const have = await roomTabsFor(room);
  if (!roomWantsTab(room)) {
    await addLog({ kind: "sent", what: "ROOM ON",
      why: room.name + " switched ON — outside room hours, its tab opens at 9:15 ET " +
           "(mark it 24h to keep it open round the clock)." });
    return { ok: true, why: room.name + " is on — its tab opens at 9:15 ET (24h rooms open now)" };
  }
  if (!have.length && room.url) {
    ROOM_OPENED_AT[room.id] = Date.now();
    try { await chrome.tabs.create({ url: room.url, active: false }); } catch (e) {}
  }
  await addLog({ kind: "sent", what: "ROOM ON",
    why: room.name + " switched ON — " + (have.length ? "tab already open, " : "tab opened, ") +
         "reading and trading LIVE." });
  return { ok: true, why: room.name + " is on — " + (have.length ? "already open" : "tab opened") };
}

// Per-channel lists the bridge owns (settings.json), cached from /mode so the
// parser's SPX->SPY retarget and implied-symbol fill see the same config the
// bridge does. Refreshed on the watch-build alarm and at startup.
let _BRIDGE_CHANNELS = {};
async function refreshBridgeChannels() {
  try {
    const { settings } = await chrome.storage.local.get("settings");
    const base = bridgeBaseFrom((settings || {}).bridge_url || BRIDGE_DEFAULT);
    const m = await (await fetch(base + "/mode", { cache: "no-store" })).json();
    if (m && typeof m === "object") {
      const next = {};
      if (Array.isArray(m.spx_entry_channels)) next.spx_entry_channels = m.spx_entry_channels.map(String);
      if (m.default_symbol_channels && typeof m.default_symbol_channels === "object") next.default_symbol_channels = m.default_symbol_channels;
      if (Array.isArray(m.entry_no_verb_channels)) next.entry_no_verb_channels = m.entry_no_verb_channels.map(String);
      _BRIDGE_CHANNELS = next;
    }
  } catch (e) { /* bridge down — keep the last good copy, never clear it */ }
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
  // PER-CHANNEL LISTS FROM THE BRIDGE (9/8). spx_entry_channels,
  // default_symbol_channels and entry_no_verb_channels live in settings.json
  // (the bridge's file) but drive the extension's parser. The extension never
  // read settings.json, so the two disagreed — SPX enabled on the bridge,
  // refused in the reader. The bridge now serves them on /mode and
  // refreshBridgeChannels() caches them here; settings.json is the one source.
  // A popup-set value in chrome.storage still wins if present (|| keeps it).
  if (_BRIDGE_CHANNELS.spx_entry_channels && !(settings || {}).spx_entry_channels)
    c.spx_entry_channels = _BRIDGE_CHANNELS.spx_entry_channels;
  if (_BRIDGE_CHANNELS.default_symbol_channels && !(settings || {}).default_symbol_channels)
    c.default_symbol_channels = _BRIDGE_CHANNELS.default_symbol_channels;
  if (_BRIDGE_CHANNELS.entry_no_verb_channels && !(settings || {}).entry_no_verb_channels)
    c.entry_no_verb_channels = _BRIDGE_CHANNELS.entry_no_verb_channels;
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
  pushChannelNames();          // housekeeping, debounced to 10 min
  // Debounced write — a burst of messages shouldn't be a burst of disk writes.
  if (_chanSaveTimer) return;
  _chanSaveTimer = setTimeout(() => {
    _chanSaveTimer = null;
    try { chrome.storage.local.set({ chan_names: CHAN_NAMES }); } catch (e) {}
  }, 2000);
}
// Real captured name wins; the hand label is the fallback; then a bare id.
/* TELL THE BRIDGE WHAT EACH CHANNEL IS REALLY CALLED (9/4).
 * The extension has always known this and never shared it, so rooms.txt kept
 * hand labels ("Platinum-1") that match nothing G sees in Discord. Debounced
 * hard — this is housekeeping, not a trading path, and it must never compete
 * with an order for the bridge's attention. Failure is silent on purpose:
 * a naming nicety must never surface as an error during a trade. */
let _namesSentAt = 0;
async function pushChannelNames() {
  try {
    if (Date.now() - _namesSentAt < 10 * 60 * 1000) return;   // 10 min
    if (!Object.keys(CHAN_NAMES).length) return;
    _namesSentAt = Date.now();
    const c = await cfg();     // 9/9: was hard-wired to loopback — a second PC's names never arrived
    await fetch(bridgeBaseFrom(c.bridge_url) + "/channames", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ names: CHAN_NAMES })
    });
  } catch (e) { /* bridge down, or busy. Try again in ten minutes. */ }
}

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

// postedAt (9/6): Discord's own <time datetime> on the message row — when the
// CALLER posted, not when we noticed. content.js has always read it; it just
// never reached the bridge. It is the start of the only latency chain that
// matters, and nothing in this field measures it. Voice and vision alerts
// have no such stamp and pass null on purpose: a blank is honest, a
// Date.now() there would silently record every voice call as instant.
async function sendOrder(sig, qty, c, author, postedAt) {
  // THE TICKER CHECK (9/8). Last stop before the bridge: if the broker lists
  // no options on it, the reader picked up a WORD, not a ticker. This is the
  // guard that stops "OPEN WITH 773C" (from "...then can go with 773c") and
  // "CLOSE EXIT" (from "| EXIT ALERT Ticker: NBIS", where the real ticker is
  // NBIS). Logged loudly rather than dropped, so a genuine ticker missing from
  // the list shows up as a line in the log instead of a silent no-trade.
  // bridge.py repeats this check; both fail open if the file won't load.
  if (sig && sig.symbol && !(await tradeableSymbol(sig.symbol))) {
    try {
      await addLog({ kind: "failed", what: "NOT-A-TICKER",
        why: sig.symbol + " isn't a tradeable symbol — the broker lists no "
           + "options on it, so that looks like a word from the message rather "
           + "than a ticker. Nothing was sent. (" + (author || "?") + ": "
           + String(sig.raw || "").slice(0, 80).replace(/\n/g, " ") + ")" });
    } catch (e) {}
    return { ok: false, why: "not a tradeable symbol: " + sig.symbol };
  }
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
    // is his stop and target run his trades, not our ratchet (born -7.5%,
    // arm +5% -> breakeven, then +2% rungs). usd is
    // "$1,100 a contract" off a trim, the only honest futures exit price a
    // dry run has.
    kind: sig.kind || "", direction: sig.direction || null,
    their_stop: (sig.their_stop === 0 || sig.their_stop) ? sig.their_stop : null,
    their_target: (sig.their_target === 0 || sig.their_target) ? sig.their_target : null,
    usd: (sig.usd === 0 || sig.usd) ? sig.usd : null,
    be: !!sig.be,     // breakeven-stops flag (8/29)
    source: "discord-extension", raw: sig.raw, ts: Date.now(),
    // THE LATENCY CHAIN (9/6). alert_at is the caller's post time from
    // Discord's own markup; seen_at is when this reader had it parsed. The
    // bridge stamps sent_at and filled_at. Splitting it three ways is the
    // point: a slow total that is all reader lag is an extension problem, a
    // slow total that is all fill time means our limit is priced too
    // politely. One number can't tell those apart, and they have opposite
    // fixes. Null when there is no post time (voice, vision) — never faked.
    alert_at: (postedAt ? postedAt / 1000 : null),
    seen_at: Date.now() / 1000,
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
 * ratchet stop (born -7.5%, arm +5% -> breakeven, +2% rungs) would be guarding
 * a position that doesn't exist.
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
            // Whose it is, per the bridge: the trader it inherited credit
            // from, or "Gian" for a hand trade. guards.pickHeld reads this
            // so a symbol-less "out" can never land on his own position
            // (9/2 14:54, SPY 767C 9/9 sold on a stranger's "I took my L").
            who: String(p.who || "?"),
            adopted: true };
          changed = true;
        }
        continue;
      }
      // A record that predates the `who` field (or whose owner the bridge
      // has since named): keep it current, the guard depends on it.
      if (mine.adopted && p.who && mine.who !== String(p.who)) {
        mine.who = String(p.who);
        changed = true;
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
let OPEN_ROOMS_PENDING = ""; // START HERE's open-rooms token not yet fully honoured

async function honourOpenRoomsRequest() {
  if (!OPEN_ROOMS_PENDING) return;
  const tok = OPEN_ROOMS_PENDING;
  let opened = 0;
  try { opened = (await openMissingRooms()) || 0; } catch (e) { opened = 0; }
  if (opened > 0) {
    await addLog({ kind: "sent", what: "ROOMS",
                   why: "START HERE asked — opened " + opened + " missing room(s); "
                        + "checking again in 30s" });
    return;                                  // keep going next tick
  }
  // a pass that opened nothing = every room is up. Done for this token.
  OPEN_ROOMS_PENDING = "";
  try { await chrome.storage.local.set({ open_rooms_done: tok }); } catch (e) {}
  await addLog({ kind: "sent", what: "ROOMS",
                 why: "START HERE's open-rooms request honoured — every room "
                      + "in rooms.txt has a tab in this browser" });
}

/* THE READER TAPE (9/8). Post one read to the bridge's reads.log. Voice calls
 * it for every finalized transcript line; the bridge writes its own vision
 * reads directly. Never awaited by the caller and never allowed to throw —
 * the tape is for G's eyes, and it must cost the ears and the eyes nothing. */
async function tapeRead(entry) {
  try {
    const c = await cfg();
    await fetch(bridgeBaseFrom(c.bridge_url) + "/reads", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ t: Date.now() }, entry || {})),
      cache: "no-store"
    });
  } catch (e) {}
}

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
    const j = await r.json();
    stamp = j.stamp;
    // ONE-SHOT ROOM OPEN (9/9, G: "no input from me"). START HERE writes
    // open-rooms.request; the bridge passes its token here. A token we
    // have not honoured yet becomes "pending": each 30s tick then opens up
    // to 3 missing rooms (openMissingRooms, lane-aware) until a pass opens
    // none, and only THEN is the token marked done. Nothing runs without a
    // fresh token — the always-on healer that reopened hand-closed tabs
    // stays gone.
    try {
      const tok = String(j.open_rooms || "");
      if (tok) {
        const { open_rooms_done } = await chrome.storage.local.get("open_rooms_done");
        if (tok !== open_rooms_done) OPEN_ROOMS_PENDING = tok;
      }
    } catch (e) {}
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
/* KEEP A READER IN EVERY ROOM TAB (9/8). reinject() runs once at come-up, but
 * a tab that was OPEN BEFORE the extension loaded never gets a content script
 * — Chrome only injects on navigation after install. That is exactly the Whop
 * second profile: the 4 tabs were open, then the extension was loaded, so
 * whop.js never attached and the bridge got nothing from Whop. This runs on
 * the 30s alarm and injects the right reader into any matching tab we have not
 * injected in the last 5 min. content.js/whop.js are idempotent (they stop the
 * old copy first), so a re-inject never double-reads. Bounded by INJECTED_AT
 * so a healthy tab isn't re-scripted every tick. */
const INJECTED_AT = {};       // tabId -> last inject time
async function ensureReaders() {
  let tabs = [];
  try {
    tabs = await chrome.tabs.query({ url: ["https://discord.com/channels/*",
      "https://*.discord.com/channels/*", "https://whop.com/*", "https://*.whop.com/*"] });
  } catch (e) { return; }
  const now = Date.now();
  for (const t of tabs) {
    if (t.discarded || t.status === "loading") continue;
    if (now - (INJECTED_AT[t.id] || 0) < 300000) continue;   // did this one recently
    // 9/9: a tab whose reader is HEARTBEATING doesn't need a new copy.
    // Re-injecting healthy tabs every 5 min was what manufactured the
    // zombie beaters (one per inject). Inject only when nothing is beating.
    let beating = false;
    for (const cid in READER_TAB) {
      if (READER_TAB[cid] === t.id && now - (READER_BEAT[cid] || 0) < 60000) { beating = true; break; }
    }
    if (beating) { INJECTED_AT[t.id] = now; continue; }
    const isWhop = /(^|\.)whop\.com/.test(String(t.url || ""));
    try {
      await chrome.scripting.executeScript({ target: { tabId: t.id },
        files: [isWhop ? "whop.js" : "content.js"] });
      INJECTED_AT[t.id] = now;
    } catch (e) { /* closed / mid-nav — next tick */ }
  }
}

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

/* OPEN THE ONES THAT AREN'T THERE (9/8, G: "check which are open and open
 * the ones that are missing"). oneTabPerChannel() is the CLOSE half — it kills
 * duplicates. This is the OPEN half — it opens any LIVE room from rooms.txt
 * that has no tab at all.
 *
 * NOT a background healer any more (9/8): this was pulled out of the watch-build
 * sweep because it reopened tabs G had deliberately closed, and closing a tab is
 * how he turns a room off. It now runs ONLY when START HERE asks for it
 * (honourOpenRoomsRequest), so the tab set converges on rooms.txt on request,
 * not continuously. Which is why the Brando/Shoof tabs being shut one morning
 * cost the 10:44 QQQ call — nothing reopens a room he closed.
 *
 * Careful, because opening tabs costs money-adjacent attention and RAM:
 *  - `on` rooms only. off / lapsed rooms are never opened.
 *  - Discord AND Whop, by their real URL shapes.
 *  - Throttled: at most a few per pass, opened in the background, so a cold
 *    start does not slam a whole lane at once — rooms.txt is 26 rooms today,
 *    22 Discord + 4 Whop, and each profile opens only its own (the launcher's
 *    own 3-at-a-time flood
 *    still handles the true cold start; this is the steady-state healer).
 *  - Never opens a room it opened in the last 2 minutes — a tab that is still
 *    loading has no matchable path yet, and without this guard the next pass
 *    would open it again. */
const ROOM_OPENED_AT = {};        // channelId -> last time we opened it

/* WHICH BROWSER AM I? (9/8). Two profiles run this same extension — one for
 * Discord, one for the 4 Whop rooms. Each needs to know its lane so it opens
 * (and keeps) only its own rooms and EVICTS the other's. The signal is what is
 * already open: the profile the launcher seeded with Discord rooms has ~22
 * Discord tabs, the Whop profile has 4 Whop tabs. Once a profile has clearly
 * more of one surface it LOCKS to that lane in storage and never flips — so a
 * stray tab (e.g. the 4 leftover Whop tabs in the Discord browser from before
 * the split) can't drag it the wrong way. Locks at >=3 of a surface and a
 * clear majority; until then returns "" and the caller uses the soft rule. */
async function stickyLane(haveDiscord, haveWhop) {
  try {
    const { profile_lane } = await chrome.storage.local.get("profile_lane");
    if (profile_lane === "discord" || profile_lane === "whop") return profile_lane;
    const tabs = await chrome.tabs.query({ url: ["https://discord.com/channels/*",
      "https://*.discord.com/channels/*", "https://whop.com/joined/*",
      "https://whop.com/*/exp_*"] });
    let d = 0, w = 0;
    for (const t of tabs) {
      const u = String(t.url || "");
      if (/discord\.com\/channels\/\d+\/\d+/.test(u)) d++;
      else if (/whop\.com/.test(u)) w++;
    }
    let lane = "";
    if (d >= 3 && d > w) lane = "discord";
    else if (w >= 3 && w > d) lane = "whop";
    if (lane) await chrome.storage.local.set({ profile_lane: lane });
    return lane;
  } catch (e) { return ""; }
}

/* EVICT THE OTHER LANE'S TABS (9/8). Once a profile is locked to a lane, close
 * any open ROOM tab of the OTHER surface. This is what removes the 4 Whop tabs
 * that were left in the Discord browser from before the split — and it stops
 * the far worse problem they cause: the Discord profile's extension READING
 * those Whop tabs too, so every Whop alert fires from BOTH browsers. Only ever
 * closes tabs whose URL is a real room of the wrong surface; never a random
 * tab, never anything if the lane isn't locked. */
async function evictOtherLane() {
  try {
    const { profile_lane } = await chrome.storage.local.get("profile_lane");
    if (profile_lane !== "discord" && profile_lane !== "whop") return;
    const wantWhopGone = (profile_lane === "discord");
    const tabs = await chrome.tabs.query({ url: wantWhopGone
      ? ["https://whop.com/joined/*", "https://whop.com/*/exp_*"]
      : ["https://discord.com/channels/*", "https://*.discord.com/channels/*"] });
    let closed = 0;
    for (const t of tabs) {
      const u = String(t.url || "");
      const isRoom = wantWhopGone
        ? /whop\.com\/(?:joined\/|[^/]+\/exp_)/.test(u)
        : /discord\.com\/channels\/\d+\/\d+/.test(u);
      if (!isRoom) continue;
      try { await chrome.tabs.remove(t.id); closed++; } catch (e) {}
    }
    if (closed) await addLog({ kind: "sent", what: "ROOMS",
      why: "closed " + closed + " " + (wantWhopGone ? "Whop" : "Discord")
         + " tab(s) that don't belong in this browser — they live in the other "
         + "profile now, and reading them here would double-fire." });
  } catch (e) {}
}

async function openMissingRooms() {
  let rooms;
  try { rooms = await loadRoomsFile(); } catch (e) { return; }
  // every `on` room that wants a tab RIGHT NOW (9/9: outside 9:15-4:30 ET
  // only the rooms marked `always` — the futures ones — get opened)
  const want = [];
  try {
    for (const r of ALL_ROOMS) {
      if (r && r.id && r.url && roomWantsTab(r)) want.push({ id: String(r.id), url: r.url });
    }
  } catch (e) { return; }
  if (!want.length) return;
  let tabs;
  try {
    tabs = await chrome.tabs.query({ url: ["https://discord.com/channels/*",
                                           "https://*.discord.com/channels/*",
                                           "https://whop.com/joined/*",
                                           "https://whop.com/*/exp_*"] });
  } catch (e) { return; }
  const openIds = new Set();
  let haveDiscord = false, haveWhop = false;
  for (const t of tabs) {
    const u = String(t.url || "");
    if (/discord\.com\/channels\/\d+\/\d+/.test(u)) haveDiscord = true;
    if (/whop\.com\/.*exp_/.test(u) || /whop\.com\/joined\//.test(u)) haveWhop = true;
    const m = u.match(/\/channels\/\d+\/(\d+)/) || u.match(/exp_([a-z0-9]+)/i);
    if (m) openIds.add(m[1]);
    const e2 = u.match(/exp_[a-z0-9]+/i);
    if (e2) openIds.add(e2[0]);
  }
  // TWO-BROWSER SPLIT (9/8, G runs Discord in one Chrome and the Whop rooms in
  // a separate one to keep Whop's weight off everything else). BOTH browsers
  // run this same extension and read the same rooms.txt, so without a lane
  // rule each would try to open the OTHER browser's rooms — the Whop window
  // would open 22 Discord tabs and vice versa. The rule: an instance only ever
  // opens rooms of a surface it ALREADY has a tab for. The launcher seeds each
  // browser with its own surface, so each adopts its lane and never crosses.
  // A browser with neither surface yet (nothing opened) opens nothing here and
  // waits — the launcher's cold-start does the first open.
  const now = Date.now();
  let opened = 0;
  for (const r of want) {
    const isWhop = /^whop:/i.test(r.id) || /whop\.com/i.test(r.url);
    const lane = await stickyLane(haveDiscord, haveWhop);
    if (lane === "discord" && isWhop) continue;   // Whop is the other browser's job
    if (lane === "whop" && !isWhop) continue;     // Discord is the other browser's job
    if (!lane) {                                   // lane not settled yet — old rule
      if (isWhop && !haveWhop) continue;
      if (!isWhop && !haveDiscord) continue;
    }
    const key = r.id.replace(/^whop:/, "");
    const idInUrl = (r.url.match(/\/channels\/\d+\/(\d+)/) || [])[1]
                 || (r.url.match(/exp_[a-z0-9]+/i) || [])[0];
    if (idInUrl && (openIds.has(idInUrl) || openIds.has(key))) continue;   // already up
    if (now - (ROOM_OPENED_AT[r.id] || 0) < 120000) continue;             // opened just now
    ROOM_OPENED_AT[r.id] = now;
    try {
      await chrome.tabs.create({ url: r.url, active: false });
      opened++;
    } catch (e) { /* ignore */ }
    if (opened >= 3) break;     // a few per pass; the caller comes round again
    // 9/9: Discord lets a USER account start ONE gateway session per 5 s
    // (max_concurrency 1) and caps live sessions at 50. Space the opens.
    await new Promise(res => setTimeout(res, 6000));
  }
  return opened;                // 9/9: the one-shot request needs the count
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
  // NOT IN THE DISCORD BROWSER (9/8, G: "remove the whop from the autoreload
  // list" / "stop opening whop websites on the original browser"). Whop lives
  // in its own profile now. In the profile locked to the Discord lane, this
  // watchdog must never reload or keep a Whop tab alive — that is what kept
  // resurrecting the strays. It only runs in the Whop-lane profile (or before
  // a lane has locked, where evictOtherLane hasn't cleared anything yet).
  try {
    const { profile_lane } = await chrome.storage.local.get("profile_lane");
    if (profile_lane === "discord") return;
  } catch (e) {}
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
      await addLog({ kind: "skipped", author: "whop", text: "",
                     why: "⚠ Whop tab painted nothing for 2 min (black shell) — reloading it" });
      try { await chrome.tabs.reload(t.id); } catch (e) { /* tab gone */ }
      continue;
    }
    // NO-MESSAGE reload, MARKET HOURS ONLY (8/25): out of hours a quiet
    // room is just a quiet room — the old any-hour version reloaded every
    // whop tab all evening, which read as "loading and black again".
    // 9/9: 5 min -> 30 min. Whop DOES push live (verified 8/30 on the new
    // pages; alerts arrive without a reload), so the 5-min hedge was ~75
    // silent reloads per tab per day for nothing. Kept as a 30-min
    // backstop and LOGGED, so it can never be an invisible storm again.
    if (!_marketOpenNow()) continue;
    if (!whopTabSeen[t.id]) { whopTabSeen[t.id] = now; continue; }
    if (now - whopTabSeen[t.id] > 30 * 60 * 1000) {
      whopTabSeen[t.id] = now;
      await addLog({ kind: "skipped", author: "whop", text: "",
                     why: "Whop tab quiet 30 min in market hours — routine backstop reload" });
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
const OFF_SAID = {};        // "off|<cid>" -> last time we said the room is OFF
const ROOM_MSG_AT = {};          // channelId -> last time the reader handed us a row
// channelId -> the newest message's OWN timestamp (postedAt), max-merged —
// "when did this room last post", survives reloads and history re-reads
// (9/9, G: "I want to know what time was the last message from each channel")
const ROOM_POST_AT = {};
const ROOM_ALERTED = {};         // channelId -> last-msg ts we alerted on
let _pulseBoot = Date.now();
(async () => { try {
  const got = await chrome.storage.local.get(["room_msg_at", "room_post_at"]);
  const st = got.room_msg_at;
  if (st) for (const k of Object.keys(st)) ROOM_MSG_AT[k] = st[k];
  const pt = got.room_post_at;
  if (pt) for (const k of Object.keys(pt)) ROOM_POST_AT[k] = Math.max(ROOM_POST_AT[k] || 0, pt[k]);
} catch (e) {} })();
function notePost(cid, postedAt) {
  const t = Number(postedAt) || 0;
  if (!cid || !t || t > Date.now() + 60000) return;
  if (t > (ROOM_POST_AT[cid] || 0)) ROOM_POST_AT[cid] = t;
}

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
  try { await chrome.storage.local.set({ room_msg_at: ROOM_MSG_AT, room_post_at: ROOM_POST_AT }); } catch (e) {}
  if (!_marketOpenNow()) return;
  const now = Date.now();
  const QUIET = 40 * 60 * 1000;
  // LIVE rooms only (9/9). This used to walk Object.keys(ROOM_LABELS) — the
  // hand-typed name map, which carries every room ever wired: all the cut ZT
  // rooms, the asleep Boka ones, Vero 1/3, Options Watchlist, TTT ids that
  // were never in rooms.txt. None of them have a tab, so every one of them
  // tripped "silent 40 min" every session — roughly 40 false alarms a day,
  // which is how a real dead reader gets lost in the noise.
  try { await loadRoomsFile(); } catch (e) {}
  const _watch = LIVE_ROOM_IDS.size ? LIVE_ROOM_IDS : Object.keys(ROOM_LABELS);
  for (const id of _watch) {
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
// ACCESS PROBE (9/7): every 30 min it CONSIDERS probing; accessCheck()
// itself enforces once-a-day, one room, and never during market hours.
chrome.alarms.create("access-check", { periodInMinutes: 30 });
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
/* WHOP LANE SELF-HEAL (9/10 — Day Trades caught exactly 1 alert in the month
 * since 8/13). openMissingRooms() only runs on the one-shot START HERE token
 * (9/8, G: "if i close one it wont stop opening them" — an open tab is the on
 * switch for DISCORD, closing one is how he turns a room off, and that rule
 * stays exactly as it was). But he doesn't hand-manage the Whop profile the
 * same way — those tabs die from crashes, memory pressure, or the eviction/
 * dedupe logic, never from him closing one on purpose. So in the whop lane
 * only, this calls openMissingRooms() every watch-build tick regardless of
 * the token; openMissingRooms already skips Discord rooms when the lane is
 * "whop" (the isWhop/lane check inside it), so Discord's 9/8 behavior is
 * completely untouched. Paired with _whop_loop.bat, which relaunches the
 * whole Sniper Whop Chrome window if it isn't even running. */
async function whopSelfHeal() {
  try {
    const { profile_lane } = await chrome.storage.local.get("profile_lane");
    if (profile_lane !== "whop") return;
  } catch (e) { return; }
  try { await openMissingRooms(); } catch (e) {}
}

chrome.alarms.onAlarm.addListener(a => {
  // openMissingRooms() REMOVED from this sweep 9/8 (G: "revert the check the
  // browser and open missing tabs, because if i close one it wont stop opening
  // them"). His 8/23 rule stands: an OPEN TAB is the on switch, and CLOSING a
  // tab is how he turns a room off. The launcher (START HERE) opens the tabs
  // once at startup; after that nothing reopens a tab he closed. Function left
  // defined-but-uncalled below in case it's ever wanted back.
  // whopSelfHeal() ADDED BACK 9/10, whop lane only — see its own comment.
  if (a.name === "watch-build") { checkBuild(); pollRoomsFile(); roomSchedule(); syncFills(); ensureReaders(); oneTabPerChannel(); evictOtherLane(); refreshBridgeChannels(); checkBridgeHealth(); memoryShed(); keepRoomsLoaded(); honourOpenRoomsRequest(); whopSelfHeal(); }
  if (a.name === "whop-watchdog") whopWatchdog();
  if (a.name === "room-silence") roomSilenceCheck();
  if (a.name === "access-check") { accessCheck(false); revokeCheck(); }
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
    // 9/9 FIX — this listed the KEYS of channel_live, which was wrong twice
    // over: a room flipped to TESTING has a key (value false) and was printed
    // as LIVE, and after the ALL_LIVE_GEN sweep deleted every key the map is
    // usually EMPTY, so this export told him "none (all testing)" while all
    // 19 rooms were spending real money. This is the file he reads remotely
    // to see what's armed, so it has to say the true thing.
    try { await loadRoomsFile(); } catch (e) {}
    const _cl = c.channel_live || {};
    const liveRooms = Array.from(LIVE_ROOM_IDS)
      .filter(id => _cl[id] !== false)
      .map(id => roomName(id) || id);
    // OFF rooms in the export (9/2, the RWGates mystery: a LIVE room whose
    // calls were captured all day and never judged — the popup's per-room
    // OFF switch drops messages silently, and nothing anywhere said so).
    const offRooms = Object.keys((c.channel_disabled) || {})
      .filter(id => c.channel_disabled[id]).map(id => roomName(id) || id);
    const shadowRooms = Array.from(SHADOW || []).map(id => roomName(id) || id);
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
      "  LIVE rooms:     " + (liveRooms.length ? liveRooms.join(", ") : "none — every room is flipped to TESTING") + "\n" +
      "  OFF rooms:      " + (offRooms.length ? offRooms.join(", ") : "none") + "\n" +
      "  SHADOW rooms:   " + (shadowRooms.length ? shadowRooms.join(", ") : "none") + "\n" +
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
    // THE READER TAPE (9/8, G: "i need to see them in order to help you
    // analize"). Every finalized line the ears heard, with what the parser
    // made of it, goes to the bridge's reads.log — one chronological file
    // for voice AND vision, so he can read the stream and point at the
    // misreads. Fire-and-forget; a slow bridge must never delay the ears.
    try {
      const _quick = parseSignal(msg.text, {}) || {};
      tapeRead({ kind: "voice", room: label,
                 speaker: (msg.speaker != null ? "S" + msg.speaker : ""),
                 heard: msg.text,
                 action: _quick.action || "", symbol: _quick.symbol || "",
                 strike: _quick.strike, side: _quick.side || "",
                 why: _quick.why || "" });
    } catch (e) {}
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
    let _learned = SPEAKER_NAMES.get(_vkey.split("|").slice(0,2).join("|")) ||
                   SPEAKER_NAMES.get(_vkey);
    // HOST DEFAULT (9/9, from the first captured FST live): on Felony's own
    // Zoom ("Live Trading × FST") speaker S0 is the host — Felony — the
    // whole session; S1/S2 are guests. Until a typed scribe alert names a
    // speaker, book the host's calls under his real name so the per-trader
    // walls (claims, dedupe, scoreboard) apply from the first word.
    if (!_learned && /FST|First ?Step|Live Trading/i.test(String(label || "")) &&
        String(msg.speaker) === "0") {
      _learned = "Felony";
    }
    if (_learned) { vs.caller = _learned; label = _learned + " 🎙"; }
    const _isEntry = vs.action === "OPEN" || vs.action === "ADD";
    if (_isEntry && c.voice_entries !== true) return;
    if (!_isEntry && c.voice_exits !== true) return;
    // Dress the order BEFORE staging or firing — a staged entry confirmed
    // by "I'm in" must carry the SAME live flag and the SAME round-number
    // pullback as a direct one (8/29 fix: it used to fire naked-paper).
    // LIVE/TESTING, THE SAME WAY THE TYPED PATH DECIDES IT (9/8).
    // This used to be a flat `vs.live = true` — "voice rooms are live rooms"
    // (8/29). That predates per-room testing and BORN TESTING, and it meant a
    // room set to TESTING in the popup still fired its VOICE calls with REAL
    // money, which contradicts the house rule that flipping a room live is
    // G's call alone. Latent rather than live so far only because
    // voice_entries/voice_exits are both off — but the day he turns voice on
    // it would have gone straight to the account.
    // Same three lines as the typed reader: his popup setting wins, a room
    // he has never touched is live (his 8/23 default), and a reopened room in
    // BORN_TESTING starts in testing until he says otherwise.
    {
      const _vid = String(msg.id || "");
      const _vlv = (c.channel_live || {})[_vid];
      vs.live = (_vlv === undefined && BORN_TESTING.has(_vid))
                ? false
                : (_vlv !== false);
    }
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

/* EARS RETRY (9/9). Tabs whose audio Chrome refused to hand over (no
 * activeTab grant yet). The first time such a tab is brought to the front,
 * or the Sniper icon is clicked while it is up, try once more. */
const WANT_EARS = new Map();          // tabId -> label

async function retryEars(tabId, how) {
  const label = WANT_EARS.get(tabId);
  if (!label || LISTENING.has(tabId)) return;
  let tab = null;
  try { tab = await chrome.tabs.get(tabId); } catch (e) { WANT_EARS.delete(tabId); return; }
  if (!tab || !tab.audible) return;            // quiet now — the audible event will re-ask
  const r = await startListening(tabId, label);
  if (r && r.ok) {
    WANT_EARS.delete(tabId);
    const v = LISTENING.get(tabId); if (v) v.auto = true;
    await saveListening();
    await addLog({ kind: "update", text: "",
      why: "🎙 auto-listening to " + label + " — took the audio once the tab was "
         + how + ". Every spoken call gets written down and read." });
  }
}
chrome.tabs.onActivated.addListener(({ tabId }) => { retryEars(tabId, "in front").catch(() => {}); });
// (the icon has a popup, so action.onClicked never fires — the popup sends POPUP_OPENED instead)

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
        // Our own server's notification pings are not a trader talking
        // (9/2: "auto-listening to #sniper-alerts-options" — a Deepgram
        // session on the announcer channel). Text channels that merely
        // beep are skipped; only voice/live rooms get ears.
        if (/sniper-alerts|sniper hq/i.test(tab.title || "")) return;
        const label = (tab.title || "voice").replace(/ \| Discord.*/i, "").slice(0, 40);
        const r = await startListening(tabId, label);
        if (r && r.ok) {
          WANT_EARS.delete(tabId);
          const v = LISTENING.get(tabId); if (v) v.auto = true;
          await saveListening();
          await addLog({ kind: "update",
            why: "🎙 auto-listening to " + label + " — the tab started playing "
               + "voice audio. Every spoken call gets written down and read.",
            text: "" });
        } else {
          // 9/9: Chrome only lets tabCapture take a tab the user has invoked
          // the extension on (icon click / front tab with that grant). A Zoom
          // tab opened by the morning task never has it, and this failure
          // used to be SILENT — Felony's 10:57 join produced nothing and
          // nobody knew. Say so, and remember the tab: the first time it is
          // brought to the front or the icon is clicked on it, try again.
          WANT_EARS.set(tabId, label);
          await addLog({ kind: "skipped", author: label, text: "",
            why: "🎙 " + label + " is playing audio but Chrome won't let the ears "
               + "take it yet — bring that tab to the FRONT or click the Sniper "
               + "icon on it once; the ears start by themselves the moment you do."
               + (r && r.why ? " (" + String(r.why).slice(0, 80) + ")" : "") });
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
  if (msg.type === "POPUP_OPENED") { if (msg.tabId) retryEars(msg.tabId, "clicked on").catch(() => {}); reply({ ok: true }); return; }
  // THE ONE SWITCH (9/9): the popup asks for every room + flips one.
  if (msg.type === "ROOMS?") {
    loadRoomsFile().then(() => reply({ ok: true, window_open: roomWindowOpen(), hours: ROOM_HOURS,
      rooms: ALL_ROOMS.map(r => Object.assign({}, r, { last_post: ROOM_POST_AT[r.id] || 0,
                                                       last_read: ROOM_MSG_AT[r.id] || 0 })) }))
      .catch(() => reply({ ok: false, rooms: [] }));
    return true;
  }
  if (msg.type === "ROOM_SET") { setRoomState(msg.id, !!msg.on).then(reply).catch(e => reply({ ok: false, why: String(e).slice(0, 160) })); return true; }
  if (msg.type === "ROOM_RULES") { setRoomRules(msg.id, msg.rules).then(reply).catch(e => reply({ ok: false, why: String(e).slice(0, 160) })); return true; }
  if (msg.type === "NEEDS?") { needsFromExtension().then(items => reply({ ok: true, items })).catch(() => reply({ ok: false, items: [] })); return true; }
  if (msg.type === "FIX") { fixIt(msg.do).then(reply).catch(e => reply({ ok: false, why: String(e).slice(0, 160) })); return true; }
  if (msg.type === "ATTACHED") { noteChannelName(msg.channelId, msg.channelName); badge(); reply({ ok: true }); return; }

  /* FOCUS ROOM (9/4) — click a caller's name in the popup and land on the
   * tab their alert came from. His ask: "I wanna see how the alert was
   * emitted but I can't find the tab because so many of them."
   *
   * Match order, most reliable first:
   *   1. rooms.txt shortName -> its exact URL, then find that open tab
   *   2. the channel id inside any open Discord URL
   *   3. a captured channel NAME (CHAN_NAMES) matching what was clicked
   * It DOES open the tab when the room is closed (9/4, his call — the reader
   * only reads open tabs, so landing on a dead room is useless). rooms.txt is
   * 26 rooms today, so at worst this restores one of those, never a stranger. */
  if (msg && msg.type === "FOCUS_ROOM") {
    (async () => {
      try {
        await loadRoomsFile();                       // fills ROOM_TABS
        /* EXACT ID WINS (9/7). The Rooms list in the popup is drawn FROM
         * the channel ids, so when the click comes from there it can say
         * exactly which room it means and none of the word-matching below
         * has to run. Everything else — a trade row, a caller name — still
         * arrives as text and still goes through the scoring. Use the sure
         * thing when you have it. */
        const wantId = String(msg.id || "").trim();
        if (wantId) {
          const byId = Object.values(ROOM_TABS).find(v => v.id === wantId)
                    || { url: "", id: wantId };
          const tabsNow = await chrome.tabs.query({});
          const t0 = tabsNow.find(t => (t.url || "").includes(wantId));
          if (t0) {
            await chrome.tabs.update(t0.id, { active: true });
            try { await chrome.windows.update(t0.windowId, { focused: true }); }
            catch (e) {}
            return reply({ ok: true });
          }
          if (byId.url) {
            await chrome.tabs.create({ url: byId.url, active: true });
            return reply({ ok: true });
          }
          return reply({ ok: false, why: "that room has no tab open" });
        }
        const want = String(msg.room || "").trim().toLowerCase();
        if (!want) return reply({ ok: false, why: "no room on that trade" });
        /* The name on a trade is whatever Discord SHOWED ("◽︱all-trades-
         * mashup"); rooms.txt uses a hand label ("ZT all-trades-mashup").
         * They rarely match as strings, so compare on WORDS with the emoji,
         * separators and short filler stripped. "all-trades-mashup" is the
         * part both forms share, and that is what identifies the room. */
        const norm = (s) => String(s || "").toLowerCase()
          .replace(/[^a-z0-9]+/g, " ").trim();
        const words = (s) => norm(s).split(" ").filter(w => w.length > 2);
        const wantW = words(want);

        /* CHAN_NAMES FIRST — it is the name Discord actually shows, keyed by
         * channel id, so it is an EXACT identification. rooms.txt labels are
         * hand-written and often generic ("Platinum-1", "Vero 2", "Boka 3"),
         * which share no words with "👑│nitro" and can never be matched by
         * text. Resolve the id here, then get the URL from rooms.txt BY ID. */
        let hit = null, chanId = "";
        {
          // Same generic-word trap as the rooms.txt path below: "trades" and
          // "alerts" are in half the channel names, so a first-match-wins
          // loop lands on the wrong room. Score on RARE words and take the
          // best, not the first. (PROJECT-STATUS's rule: sweep the class.)
          const cf = {};
          for (const id of Object.keys(CHAN_NAMES)) {
            for (const w of new Set(words(CHAN_NAMES[id]))) cf[w] = (cf[w] || 0) + 1;
          }
          let best = 0;
          for (const id of Object.keys(CHAN_NAMES)) {
            const nm = norm(CHAN_NAMES[id]);
            if (!nm) continue;
            if (nm === norm(want)) { chanId = id; best = 99; break; }
            const shared = words(CHAN_NAMES[id]).filter(
              w => wantW.includes(w) && (cf[w] || 0) <= 2).length;
            if (shared > best) { best = shared; chanId = id; }
          }
          if (!best) chanId = "";
        }
        if (chanId) {
          const byId = Object.values(ROOM_TABS).find(v => v.id === chanId);
          hit = byId || { url: "", id: chanId };
        }
        if (!hit) hit = ROOM_TABS[want] || null;
        if (!hit) {
          /* IGNORE WORDS THAT IDENTIFY NOTHING. "trades", "alerts",
           * "options" appear in half the labels, so matching on them sent
           * "vero-trades" to "Whop Day Trades" and "ryans-alerts" to
           * "Option Alerts". A word only counts if it appears in at most
           * two room labels — the rare word is the one that names a room.
           * A wrong tab is worse than no tab. */
          const freq = {};
          for (const k of Object.keys(ROOM_TABS)) {
            for (const w of new Set(words(k))) freq[w] = (freq[w] || 0) + 1;
          }
          let best = 0;
          for (const k of Object.keys(ROOM_TABS)) {
            const shared = words(k).filter(
              w => wantW.includes(w) && (freq[w] || 0) <= 2).length;
            if (shared > best) { best = shared; hit = ROOM_TABS[k]; }
          }
          if (!best) hit = null;
        }
        const tabs = await chrome.tabs.query({});
        let tab = null;
        if (hit) {
          tab = tabs.find(t => (t.url || "") === hit.url)
             || tabs.find(t => hit.id && (t.url || "").includes(hit.id));
        }
        if (!tab && hit && hit.id) {
          tab = tabs.find(t => (t.url || "").includes(hit.id));
        }
        if (!tab) {
          /* OPEN IT (9/4, his call). His point: the reader only reads OPEN
           * tabs, so if a trade exists the room WAS open — it has since been
           * closed, or this is an older trade. Either way he wants to see it:
           * "have it open one more. That's okay, I'll close it later."
           * Only ever opens a URL that came from rooms.txt. */
          if (!hit || !hit.url) {
            return reply({ ok: false,
              why: "that room isn't in rooms.txt, so there's no link to open" });
          }
          const made = await chrome.tabs.create({ url: hit.url, active: true });
          try { await chrome.windows.update(made.windowId, { focused: true }); } catch (e) {}
          return reply({ ok: true, opened: true });
        }
        await chrome.tabs.update(tab.id, { active: true });
        try { await chrome.windows.update(tab.windowId, { focused: true }); } catch (e) {}
        reply({ ok: true });
      } catch (e) {
        reply({ ok: false, why: String(e).slice(0, 120) });
      }
    })();
    return true;                                     // async reply
  }
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
      // The Whop browser TAB is the ONE and ONLY source of Whop reads. The old
      // server-side API reader was DELETED 9/8 — it queried Whop with the
      // experience ids at guessed /v1/messages paths (404, never once fed), and
      // while it falsely reported itself "active" it silently DROPPED every tab
      // read right here. That is exactly why Whop went dark all day. The gate is
      // gone; tab reads now flow straight through to the same parser + bridge
      // path as Discord. Verified against the live Whop DOM (13 posts scraped
      // from Day Trades) on 9/8.
    }
    // Deactivated (his ask, 8/15): a whole Discord/Whop SERVER can be turned
    // off from the Channels tab in one click, with the option to keep any
    // one of its channels on anyway. Checked before capture too — an OFF
    // channel is off, full stop, not just "don't trade it".
    {
      const _cid = String(
        (String(msg.platform || "") === "whop" && whopRoomOf(msg.channelId))
          ? whopRoomOf(msg.channelId).id : msg.channelId || "");
      if ((c.channel_disabled || {})[_cid]) {
        // Say it ONCE an hour per room, and only for something that reads
        // as a real call — so a switched-off room with live alerts shows
        // up in the log instead of vanishing (RWGates, 9/2).
        try {
          const _k = "off|" + _cid;
          const _now = Date.now();
          if (!msg.history && (_now - (OFF_SAID[_k] || 0)) > 3600 * 1000) {
            const _sv = parseSignal(msg.text, c);
            if (_sv && _sv.action) {
              OFF_SAID[_k] = _now;
              await addLog({ kind: "ignored",
                             what: "room OFF · " + (roomName(_cid) || _cid),
                             why: "this room is switched OFF in the popup, so its calls " +
                                  "are dropped — flip it on if you want it traded",
                             text: msg.text, author: msg.author });
            }
          }
        } catch (e) {}
        reply({ ok: true }); return;
      }
    }
    // Grabber export stores the FULL row text (embeds and all); trading still
    // reads the clean msg.text below.
    if (c.capture) capture(msg.full || msg.text, msg.author, msg.channelId, msg.postedAt);
    ROOM_MSG_AT[String(msg.channelId || "")] = Date.now();
    notePost(String(msg.channelId || ""), msg.postedAt);

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
                   ROOM_MSG_AT[String(wroom.id)] = Date.now();
                   notePost(String(wroom.id), msg.postedAt); }
      c.bare_pct_trims = false;
    }

    // SPX->SPY entries, per channel (8/30, G: Ryan's alerts trade SPX —
    // "enter with SPY instead, pretty much the equivalent"). The parser's
    // index-to-ETF retarget (strike/10, premium dropped, bid the SPY
    // market) already handles the math; this flag just unlocks ENTRIES
    // for channels listed in settings.json spx_entry_channels.
    c.spx_entries = ((c.spx_entry_channels || [])
      .map(String).includes(String(msg.channelId || "")));

    // THE TICKER HE NEVER TYPES (9/7, shabs / OWLS). A caller who trades ONE
    // underlying stops naming it: "in 7655p 2.9", "7760c at 300/con". Those
    // are complete calls except for the symbol, so nothing parsed at all.
    // settings.json default_symbol_channels maps a channel id to the symbol
    // that room ALWAYS means: { "1519039282537300209": "SPX" }.
    // PER CHANNEL on purpose — a bare "640c" in a room that trades everything
    // is unknowable, and inventing a symbol there buys the wrong underlying.
    // The parser only applies it when the line has no real contract of its
    // own, so an explicitly named ticker in the same message always wins.
    {
      const _ds = (c.default_symbol_channels || {})[String(msg.channelId || "")];
      if (_ds) c.default_symbol = String(_ds).toUpperCase();
      else delete c.default_symbol;
      // BARE CONTRACT + PRICE = AN ENTRY, in rooms whose callers skip the verb
      // (9/7, TTT Lotto: "MU 8/28 965c @ 1.26"). PER CHANNEL and measured — see
      // parser.js: globally this rule would fire on TradingTheTrend's own daily
      // levels row, one line carrying eight contracts.
      c.entry_no_verb = ((c.entry_no_verb_channels || [])
        .map(String).includes(String(msg.channelId || "")));
    }

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
      // THE FOOTER IS THE TRUTH (9/2 evening, from the raw captures): every
      // relayed message ENDS with its source channel — "... #◽︱♟market-bishop
      // • 3:57 PM", "... #◽︱🎩mr-top-hat • 3:05 PM", "... #◽︱jpm-investments
      // • 9:44 AM". The possessive hunt above only ever matched an embed
      // TITLE ("Bishop's Ideas"); the live relay format has none, so all
      // 9/2 mashup calls (IREN, IWM, SPY 762P) booked as "ZTRADEZ BOT" and
      // the journal had to name them by hand. Map the slug to the trader
      // the scoreboard already knows; an unknown slug still beats "the bot".
      if (!_rm) {
        const _ft = _t.match(/#\s*[^\w#]*([a-z0-9][a-z0-9\-]{1,40})\s*•\s*\d{1,2}:\d{2}\s*[AP]M\s*$/i)
          || _t.match(/#\s*[^\w#]*([a-z0-9][a-z0-9\-]{1,40})\s*•\s*\d{1,2}:\d{2}\s*[AP]M/i);
        if (_ft) {
          const _slug = _ft[1].toLowerCase();
          const _NAMES = {
            "market-bishop": "The Market Bishop", "mr-top-hat": "MR.TOPHAT",
            "jpm-investments": "Jpm Options", "king-maker": "King Maker",
            "adex-swings": "Adex", "sir-goldman": "Sir Goldman",
            "are-swings": "are-alerts", "are-alerts": "are-alerts",
            "guru-futures": "Market Guru", "cranmer": "Cranmer",
            "madhatter-trades": "MadHatter", "clutchinvestments": "Clutch",
            "namrood-options": "Namrood", "demon": "Demon", "eva-panda": "EvaPanda",
            "evapanda": "EvaPanda", "kumo": "KuMo", "stormzy": "Stormzy",
            "nitro-trades": "Nitro Trades", "stockguy007": "stockguy007",
            "bullwinkle": "Bullwinkle", "top-flow": "Top Flow", "scalps": "ZT scalps",
          };
          msg.author = _NAMES[_slug] || _slug;
          msg.relay_source = _slug;
        }
      }
    }

    // OWLS all-alerts (9/9): the "OWLS Capital Clanker" bot relays every OWLS
    // analyst into ONE channel, each embed prefixed "From 🌟｜<analyst>". Same
    // idea as the ZT mashup above — pull the REAL analyst so claims/dedupe/
    // scoreboard work, and carry shabs & eli's SPX-only handling (they never
    // type the ticker; their per-channel default_symbol/SPX-retarget can't ride
    // a mixed feed). This is what lets their dedicated tabs retire into this one.
    if (String(msg.channelId || "") === "1449226651064991806") {
      const _om = String(msg.text || "").match(/from\s*[^\w]*([a-z0-9][a-z0-9\-]{1,30})/i);
      if (_om) {
        const _slug = _om[1].toLowerCase();
        const _OWLS = {
          "shabs-sky-alerts": "shabs", "shabs": "shabs",
          "eli-alerts": "eli", "eli": "eli",
          "muggzone-options": "MuggZone", "giul-heatseeker": "Giul",
          "florida-man": "Florida Man", "common-stock": "Common Stock",
          "jon-and-kian": "Jon and Kian", "ab": "AbTrades", "tt": "TT",
          "eva": "Eva", "neal": "Neal",
        };
        msg.author = _OWLS[_slug] || _slug;
        msg.relay_source = _slug;
        if (msg.author === "shabs" || msg.author === "eli") {
          c.default_symbol = "SPX";     // their bare "7655p" -> SPX 7655p
          c.spx_entries = true;         // then the SPX->SPY retarget fires
        }
      }
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
    // order. Nothing resets on a Chrome restart — LIVE persists (his 9/8 ask:
    // "i need the popup to keep the live on"), and a room with no setting at
    // all is live by default.
    // EXIT POLICY — ENTRIES ONLY (9/3, his word: "we only follow entries
    // and let our ratchet do its thing. Remove anything we have on trims
    // and close"). Every caller-side exit — TRIM, STOPMOVE and the full
    // CLOSE ("all out", "stopped out", "closed everything") — is written
    // down and NEVER traded. The ratchet's stop at the broker is the only
    // exit. The 8/30 gate only looked at sig.fire, and the parser hands a
    // trim over with fire=false (the block below used to light it), so a
    // trim slid straight past it: 9/3 10:35, Ari trimmed WMT 108C and the
    // bot's 1-lot sold out while he stayed in. The gate now keys off the
    // ACTION alone, before anything can set fire. settings.json
    // exit_policy:"full" is still the one-line way back to obeying exits.
    {
      const _xp = String(c.exit_policy || "entries_only");
      if (_xp !== "full" &&
          (sig.action === "TRIM" || sig.action === "STOPMOVE" ||
           sig.action === "CLOSE")) {
        const _what = sig.action === "TRIM" ? "trim"
                    : sig.action === "STOPMOVE" ? "stop move" : "exit";
        // Their exit is still information: what was YOUR contract worth at
        // that moment? Best effort, never blocks the ignore.
        let _mark = "";
        try {
          if (sig.symbol) {
            const m = await markPosition(sig.symbol, sig.caller || msg.author, c);
            if (m && m.ok && m.pct != null) {
              _mark = "  —  yours is at " + Number(m.bid).toFixed(2) + ", " +
                      (m.pct >= 0 ? "+" : "") + m.pct + "% on the " +
                      Number(m.fill).toFixed(2) + " you paid";
            }
          }
        } catch (e) {}
        await addLog({ kind: "ignored",
          why: "entries only — the ratchet owns the exit; " +
               (sig.caller || msg.author || "?") + "'s " + _what +
               (sig.symbol ? " on " + sig.symbol : "") +
               " noted, not traded" + _mark,
          text: String(msg.text || "").slice(0, 140), author: msg.author });
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
    // the reverse. SHADOW is empty today, so nothing is silenced that way.
    const _lv = (c.channel_live || {})[String(msg.channelId || "")];
    // BORN TESTING — see BORN_TESTING at module scope. The gate only applies
    // while channel_live has NO entry for the room; the startup migration
    // clears any stale entry once so that is actually true. After G flips it
    // in the popup his choice is a real entry and wins from then on.
    const roomLive = (_lv === undefined
                      && BORN_TESTING.has(String(msg.channelId || "")))
                     ? false
                     : (_lv !== false);
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
        try { r1 = await sendOrder(one, one.qty || 1, c, msg.author, msg.postedAt); }
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
      } else {
        // POSSIBLE MISSED ENTRY (G, 9/3: "we need to be catching these" —
        // after finding 3 real entries silently dropped in one day, all
        // with the SAME shape: a trader has an unconsumed LOADING call on
        // the shelf, then confirms the fill in a phrasing the parser didn't
        // recognize AT ALL, so nothing gets logged, not even "ignored").
        // Deliberately narrow so it can't turn into log spam: only fires
        // when BOTH are true — (1) this trader has a loading call that
        // never got used, (2) THIS message carries a price-shaped number.
        // Pure chatter with no price stays silent, same as before.
        try {
          const _who = String(sig.caller || msg.author || "").toLowerCase();
          const _st = await guardState();
          const _cand = (_st.loaded || {})[_who];
          const _hasPrice = /\b\d{1,4}\.\d{1,2}\b/.test(String(msg.text || ""));
          const _winS = parseFloat((c.guards || {}).loading_window_seconds);
          const _windowS = isNaN(_winS) ? 14400 : _winS;
          const _age = _cand ? (Date.now() - _cand.ts) / 1000 : Infinity;
          if (_cand && !_cand.used && _hasPrice && _age <= _windowS) {
            const _ageMin = Math.round(_age / 60);
            const _what = _cand.symbol +
              (_cand.strike != null ? " " + _cand.strike +
               (_cand.side === "PUTS" ? "P" : "C") : "");
            const _msg2 = (sig.caller || msg.author || "?") +
              " has a LOADING call on " + _what + " (" + _ageMin +
              " min ago, never confirmed) and just posted a price with no " +
              "match — nothing was sent. Check by hand: " +
              String(msg.text || "").slice(0, 140);
            try {
              chrome.notifications.create({
                type: "basic", iconUrl: "icon128.png",
                title: "⚠ POSSIBLE MISSED ENTRY — " + _what,
                message: _msg2
              });
            } catch (e2) {}
            await addLog({ kind: "skipped", why: "⚠ POSSIBLE MISSED ENTRY — " + _msg2,
                           text: msg.text, author: msg.author });
          }
        } catch (e) {}
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
      res = await sendOrder(sig, qty, c, msg.author, msg.postedAt);
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
  // room only leaves LIVE when he flips it himself, or via the STOP file, which
  // still halts everything instantly. (The old master OFF switch is retired —
  // per-room toggles are the only arm.) Kept as a named function
  // so the install/startup hooks don't need touching.
  return;
}

chrome.runtime.onInstalled.addListener(() => { scrubOldBanners(); allRoomsTesting(); applyBornTesting(); refreshBridgeChannels(); badge(); reinject(); });
chrome.runtime.onStartup.addListener(() => { scrubOldBanners(); allRoomsTesting(); applyBornTesting(); refreshBridgeChannels(); badge(); reinject(); });

/* MEMORY SHED (9/1, G: "sometimes I come back and Chrome has run out of
 * memory"). Discord web leaks: a room tab that starts at ~150 MB sits at
 * 0.5-2 GB after a few hours, and 22 of them is how the browser dies. A
 * reload resets a tab to fresh — and it is SAFE here: the content script
 * re-attaches, everything already on screen comes back flagged history
 * (never traded), and the stale-entry gate covers the rest. So: every
 * 30s tick, reload at most ONE Discord room tab whose last reload is
 * SHED_EVERY_MS (4h) old — never the tab you're looking at, never a tab
 * playing voice, and never in the opening window (9:28-9:40). One tab per
 * tick means a full cycle of today's 22 Discord rooms takes ~11 minutes and
 * no two rooms are ever blind at once. Whop tabs have their own watchdog. */
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
    // 9/9: say so. This reload was silent, which is how a reload storm
    // stayed invisible until the DS Logs export was counted.
    const lbl = (String(oldest.url || "").match(/\/channels\/\d+\/(\d+)/) || [])[1];
    await addLog({ kind: "skipped", author: ROOM_LABELS[lbl] || lbl || "room", text: "",
                   why: "memory shed — routine 4h reload of this room (RAM), not a fault" });
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
const REVIVE_TRIES = {};       // channelId -> reloads in a row with no beat back
const DETACHED_STRIKE = {};    // tabId -> last "detached" handled (re-inject first, reload on repeat)

chrome.runtime.onMessage.addListener((m, sender) => {
  if (!m || m.type !== "READER_ALIVE") return;
  if (m.channelId) {
    READER_BEAT[m.channelId] = m.at || Date.now();
    REVIVE_TRIES[m.channelId] = 0;          // it answered — the slate is clean
    if (sender && sender.tab) READER_TAB[m.channelId] = sender.tab.id;
  }
  if (m.listFound && !m.observing) {
    // 9/9 — THE 662-RELOAD BUG. This used to reload the tab on the first
    // "detached" beat. The beats were coming from ZOMBIE copies of
    // content.js (replaced by a re-inject, observer nulled, heartbeat never
    // cleared), so every room reloaded ~once a minute all evening and
    // Discord logged the profile out. content.js is fixed to go silent when
    // replaced; on THIS side a detached watcher now gets the cheap remedy
    // first — a fresh content.js inject, which re-attaches the observer in
    // place (idempotent, keeps scroll, nothing on screen is traded). A tab
    // is reloaded only if the SAME room reports detached AGAIN within 5 min
    // of that inject. A page reload is the last resort, not the first.
    const tid = READER_TAB[m.channelId];
    const now = Date.now();
    if (tid && now - (REVIVED_AT[tid] || 0) > 60000) {
      REVIVED_AT[tid] = now;
      const strikes = (DETACHED_STRIKE[tid] && now - DETACHED_STRIKE[tid] < 300000) ? 2 : 1;
      DETACHED_STRIKE[tid] = now;
      if (strikes === 1) {
        addLog({ kind: "skipped", author: ROOM_LABELS[m.channelId] || m.channelId,
                 text: "",
                 why: "watcher detached — re-attached the reader in place (no reload)" });
        chrome.scripting.executeScript({ target: { tabId: tid }, files: ["content.js"] })
          .catch(() => {});
      } else {
        DETACHED_STRIKE[tid] = 0;
        addLog({ kind: "skipped", author: ROOM_LABELS[m.channelId] || m.channelId,
                 text: "",
                 why: "⚠ watcher detached AGAIN after a re-attach — reloading that room" });
        try { chrome.tabs.reload(tid); } catch (e) { }
      }
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
    // BACK OFF, DON'T LOOP (9/2 evening): one room was reloaded 174 times
    // between 13:25 and 17:11 — every ~80s all afternoon — because its
    // heartbeat never came back. A reload that didn't help once won't
    // help every minute; it only keeps a tab that may be reading fine for
    // ANOTHER room in a permanent reload cycle. 1m, 2m, 4m, 8m, then 15m.
    const tries = REVIVE_TRIES[cid] || 0;
    const wait = Math.min(15 * 60000, 60000 * Math.pow(2, tries));
    if (now - (REVIVED_AT[tid] || 0) < wait) continue;
    // still open? a closed tab just stops beating — nothing to revive
    let alive = null;
    try { alive = await chrome.tabs.get(tid); } catch (e) { alive = null; }
    if (!alive) { delete READER_BEAT[cid]; delete READER_TAB[cid];
                  delete REVIVE_TRIES[cid]; continue; }
    // STALE RECORD: the tab has since moved to a different page (a click,
    // a redirect, a room swap) — its content script now beats under the
    // NEW channel id and this old id can never answer again. Reloading it
    // would only punish whatever it is reading now. Drop the record.
    if (!String(alive.url || "").includes("/" + cid)) {
      delete READER_BEAT[cid]; delete READER_TAB[cid]; delete REVIVE_TRIES[cid];
      await addLog({ kind: "skipped", author: ROOM_LABELS[cid] || cid, text: "",
                     why: "that room's tab now shows a different page, so its "
                          + "old heartbeat record was stale — dropped, no "
                          + "reload. If the room should be open, START HERE "
                          + "opens it." });
      continue;
    }
    REVIVED_AT[tid] = now;
    REVIVE_TRIES[cid] = tries + 1;
    const nextWait = Math.min(15 * 60000, 60000 * Math.pow(2, tries + 1));
    await addLog({ kind: "skipped", author: ROOM_LABELS[cid] || cid, text: "",
                   why: "⚠ this room's reader stopped answering ("
                        + Math.round((now - last) / 1000) + "s). Reloading it "
                        + "now instead of waiting 40 minutes to notice."
                        + (tries ? " (attempt " + (tries + 1) + " — next in "
                                   + Math.round(nextWait / 60000) + " min; if "
                                   + "it never answers, open that room by hand)"
                                 : "") });
    try { await chrome.tabs.reload(tid); } catch (e) { }
  }
}

/* WHOP API FEED — DELETED 9/8. It never worked: it queried Whop with the
 * experience ids at guessed /v1/messages paths that 404, so it never fed, and
 * its false "active" ping silently killed the working browser-tab reads in the
 * MESSAGE handler above. Whop now reads ONLY through the tab (whop.js), exactly
 * like Discord. The offscreen page is kept for VOICE (Deepgram) only. */
badge();
reinject();
checkBuild();
checkBridgeHealth();
