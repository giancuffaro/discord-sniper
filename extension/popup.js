/* popup.js — the dashboard. Nothing here decides a trade; it only shows you
 * what happened and lets you change the settings the worker reads.
 *
 * There are two switches and they answer two different questions:
 *
 *   ON / OFF          is the bot working at all?      (lives in the browser)
 *   TEST / REAL       fake money or your money?       (lives on the bridge)
 *
 * Both have to be on before a dollar moves, which is what lets you leave it
 * running all day on TEST and watch what it would have done.
 *
 * There used to be a third button called STOP. It set a separate flag that did
 * exactly what OFF does — same door, second lock — so it's gone. OFF is the
 * stop button. It survives closing the popup, closing the tab and Chrome
 * putting the extension to sleep, because it's written to storage rather than
 * held in a variable.
 */

const $ = id => document.getElementById(id);

const DEFAULTS = {
  armed: true, stopped: false, capture: true,   // ON is the resting state
  bridge_url: "http://127.0.0.1:8787/order",
  channel_ids: [], follow_admins: [],
  // Futures fire like every other room now (per its TESTING/LIVE toggle). On
  // out of the box — set to false only if you ever want to park futures.
  futures_enabled: true,
  // The old filter knobs (trim modes, symbol lists, add limits, daily caps)
  // are deleted from the code — "no filters wanted. id like to follow
  // everything to the tee as they do." What's left is safety, not filtering.
  guards: { cooldown_seconds: 5, dedupe_seconds: 120,
            regular_hours_only: true, open_time: "09:30",
            close_time: "16:00", max_message_age_seconds: 20 }
};

const listToText = a => (a || []).join(", ");
const textToList = t => String(t || "").split(",")
  .map(s => s.trim()).filter(Boolean);

async function getSettings() {
  const { settings } = await chrome.storage.local.get("settings");
  const s = Object.assign({}, DEFAULTS, settings || {});
  s.guards = Object.assign({}, DEFAULTS.guards, (settings || {}).guards || {});
  // Old builds saved a conservative 15:45 close. Options actually trade to
  // 4:00 (and the cash indices to 4:15, handled in the guard), so lift the
  // stale value once so his end-of-day entries aren't refused.
  if (s.guards.close_time === "15:45") s.guards.close_time = "16:00";
  return s;
}

function ago(t) {
  const s = Math.round((Date.now() - t) / 1000);
  if (s < 60) return s + "s ago";
  if (s < 3600) return Math.round(s / 60) + "m ago";
  return Math.round(s / 3600) + "h ago";
}

/* Market time, not your PC's time. If you ever run this from a different time
 * zone, "since 09:41" should still mean 09:41 in New York. */
function clock(t) {
  return new Intl.DateTimeFormat("en-GB", { timeZone: "America/New_York",
    hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(t));
}

/* ---- the live / dry-run switch -------------------------------------------
 * This one lives on the bridge, not in the browser, because the bridge is the
 * only thing that can actually spend money. The popup just asks it what it is
 * and tells it to change. Flipping to live needs two clicks — one to ask, one
 * to mean it. Flipping back to dry run is instant, because the safe direction
 * should never make you confirm anything.
 */
let modeStatus = null;

function bridgeBase() {
  const url = $("bridge").value.trim() || DEFAULTS.bridge_url;
  return url.replace(/\/order\/?$/, "").replace(/\/$/, "");
}

async function askBridge(path, body) {
  const opt = body
    ? { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) }
    : { method: "GET" };
  const r = await fetch(bridgeBase() + path, opt);
  return r.json();
}

/* The master switch is retired. This paints one honest line about the
 * bridge: reachable or not, keys or not, real buying power when known. The
 * per-room toggles in Settings are the only thing that arms real money. */
function paintMode() {
  // Two dots, no essays: Bridge up or not, keys in or not. Green means
  // good. Buying power rides along when Webull will say it.
  const sub = $("modestate");
  const dot = ok => '<span style="color:' + (ok ? "#4ade80" : "#f87171") +
                    '">&#9679;</span> ';
  if (!modeStatus) {
    sub.innerHTML = dot(false) + "Bridge &nbsp; " + dot(false) + "Webull keys";
    return;
  }
  const bp = modeStatus.buying_power;
  const bpBit = (bp === null || bp === undefined)
    ? "" : " &nbsp;·&nbsp; $" + Math.round(bp).toLocaleString() + " margin BP";
  const fbp = modeStatus.futures_buying_power;
  const fbpBit = (fbp === null || fbp === undefined)
    ? "" : " &nbsp;·&nbsp; $" + Math.round(fbp).toLocaleString() + " futures BP";
  const fut = modeStatus.futures_account
    ? " &nbsp; " + dot(true) + "Futures acct" : "";
  sub.innerHTML = dot(true) + "Bridge &nbsp; " +
    dot(!!(modeStatus.has_keys && modeStatus.connected)) + "Webull keys" +
    fut + bpBit + fbpBit;
}


function paintProps() {
  const box = $("proplist");
  if (!box) return;
  const props = (modeStatus || {}).props || [];
  box.innerHTML = props.length ? props.map(pr =>
    '<div class="row" style="margin-bottom:4px">' +
    '<span class="grow" style="font-size:12px">' + pr.name +
    ' <span style="color:#7d8697">(' + pr.platform + ')</span></span>' +
    '<button data-prop="' + pr.name + '" data-op="toggle" class="' +
    (pr.enabled ? "live" : "safe") + '" style="width:88px">' +
    (pr.enabled ? "ARMED" : "off") + "</button>" +
    '<button data-prop="' + pr.name + '" data-op="remove" ' +
    'style="width:34px">✕</button></div>').join("") : "";
  box.querySelectorAll("button[data-prop]").forEach(btn => {
    btn.onclick = async () => {
      const op = btn.dataset.op;
      try {
        modeStatus = await askBridge("/props",
          op === "toggle" ? { toggle: btn.dataset.prop }
                          : { remove: btn.dataset.prop });
        $("propstate").textContent = modeStatus.message || "saved";
      } catch (e) {
        $("propstate").textContent = "couldn't reach the bridge";
      }
      paintProps();
    };
  });
}

/* Show the paste boxes only when they're needed. Keys already saved? Collapse
 * to a one-line summary with a Replace link — his ask: "only let paste keys if
 * they are needed, otherwise hide the entry key areas." */
function _toggleKeyGroup(entryId, savedId, saved, summaryHtml) {
  const entry = $(entryId), box = $(savedId);
  if (!entry || !box) return false;
  if (saved && !entry.dataset.forceOpen) {
    entry.style.display = "none";
    box.style.display = "";
    box.innerHTML = summaryHtml +
      ' &nbsp;<a href="#" data-openkeys="' + entryId + '" ' +
      'style="color:#60a5fa;text-decoration:none">Replace</a>';
    const a = box.querySelector("a[data-openkeys]");
    if (a) a.onclick = (e) => {
      e.preventDefault();
      entry.dataset.forceOpen = "1";
      entry.style.display = ""; box.style.display = "none";
    };
    return true;
  }
  entry.style.display = "";
  box.style.display = "none";
  return false;
}

function paintKeys() {
  const has = !!(modeStatus && modeStatus.has_keys);
  _okbox("keySaved", has, "Webull connected");
  _okbox("paperKeySaved", !!(modeStatus && modeStatus.paper_keys_in),
         "Webull paper keys saved");
  const el = $("keystate");
  if (!el) return;
  el.textContent = (!modeStatus || has) ? ""
    : "No key yet — tap the pencil on Webull to add it.";
}
function _okbox(id, ok, label) {
  const b = $(id);
  if (!b) return;
  if (ok) { b.style.display = "flex"; b.innerHTML = "<b>\u2713</b> " + label; }
  else b.style.display = "none";
}

let brokerPos = [];        // real Webull account positions, so the popup mirrors it
async function refreshMode() {
  try {
    modeStatus = await askBridge("/mode");
  } catch (e) {
    modeStatus = null;      // bridge isn't running, which is a normal state
  }
  try {
    const pr = await askBridge("/positions");
    brokerPos = (pr && pr.positions) || [];
  } catch (e) { brokerPos = []; }
  paintMode();
  paintKeys();
  paintProps();
  paintSim();
  paintStrat();
  paintFuturesBrokers();
  paintPaper();
  paintAi(modeStatus);
  paintStatus();
  paintBridgeDown();
}

/* The big red bridge-OFF banner. modeStatus is null only when the bridge didn't
 * answer at all — which is the one state where NOTHING can trade, so it gets the
 * loudest signal in the popup. */
function paintBridgeDown() {
  const el = $("bridgeDown");
  if (el) el.style.display = modeStatus ? "none" : "flex";
}
if ($("bridgeRetry")) $("bridgeRetry").onclick = async () => {
  const b = $("bridgeRetry");
  b.disabled = true; b.textContent = "…";
  await refreshMode();
  b.disabled = false; b.textContent = "Retry";
};
if ($("botOffOn")) $("botOffOn").onclick = async () => {
  const b = $("botOffOn");
  b.disabled = true; b.textContent = "…";
  try { await patch({ armed: true, stopped: false }); } catch (e) {}
  b.disabled = false; b.textContent = "Turn ON";
};

/* ---- where futures trade: Webull / NinjaTrader / Tradovate ----------------
 * Independent toggles, saved on the bridge. An alert fans out to every one
 * that's ON. Painted from the bridge's reported state so a reload is honest;
 * passwords are never sent back, only whether one is on file. */
function _fbBtn(id, on) {
  const b = $(id);
  if (!b) return;
  b.textContent = on ? "ON" : "off";
  b.className = "tgl " + (on ? "live" : "safe");
}

// The toggle ON/off intent lives in the BROWSER, so a status refresh (or the
// bridge being momentarily down) can never flip a switch the user just set.
// The bridge still ROUTES the orders, so every change is also pushed to it.
let _fbLocal = { webull: false, ninja: false, tradovate: false, topstep: false };
let _fbSeeded = false;
try {
  chrome.storage.local.get("fb_toggles", r => {
    if (r && r.fb_toggles) {
      _fbLocal = Object.assign(_fbLocal, r.fb_toggles);
      _fbSeeded = true;
      _fbPaintToggles();
    }
  });
} catch (e) {}

function _fbPaintToggles() {
  _fbBtn("fbWebull", _fbLocal.webull);
  _fbBtn("fbNinja", _fbLocal.ninja);
  _fbBtn("fbTradovate", _fbLocal.tradovate);
  _fbBtn("fbTopstep", _fbLocal.topstep);
}

function paintFuturesBrokers() {
  const fb = (modeStatus || {}).futures_brokers || {};
  const nt = fb.ninjatrader || {}, tv = fb.tradovate || {}, ts = fb.topstep || {};
  // Seed toggles from the bridge ONCE, only if the browser never stored an
  // intent of its own. After that the browser copy wins — a refresh can't turn
  // a switch off under the user.
  if (!_fbSeeded && modeStatus) {
    _fbLocal = { webull: !!fb.webull, ninja: !!nt.enabled,
                 tradovate: !!tv.enabled, topstep: !!ts.enabled };
    _fbSeeded = true;
    try { chrome.storage.local.set({ fb_toggles: _fbLocal }); } catch (e) {}
  }
  _fbPaintToggles();
  // Field values come from the bridge, but never stomp a field being typed in.
  if ($("ninjaAccount") && document.activeElement !== $("ninjaAccount"))
    $("ninjaAccount").value = nt.account || "";
  if ($("ninjaDir") && document.activeElement !== $("ninjaDir"))
    $("ninjaDir").value = nt.incoming_dir || "";
  if ($("tvUser") && document.activeElement !== $("tvUser"))
    $("tvUser").value = tv.username || "";
  if ($("tvDemo")) $("tvDemo").checked = !!tv.demo;
  if ($("tvPass") && tv.has_password && !$("tvPass").value)
    $("tvPass").placeholder = "•••••• (saved — leave blank to keep)";
  if ($("tsUser") && document.activeElement !== $("tsUser"))
    $("tsUser").value = ts.username || "";
  if ($("tsUrl") && document.activeElement !== $("tsUrl") && ts.base_url)
    $("tsUrl").value = ts.base_url;
  if ($("tsKey") && ts.has_password && !$("tsKey").value)
    $("tsKey").placeholder = "•••••• (saved — leave blank to keep)";
}

function _fbVal(id) { return ($(id) || {}).value || ""; }

async function saveFuturesBrokers() {
  const payload = {
    webull: _fbLocal.webull,
    ninjatrader: { enabled: _fbLocal.ninja,
                   account: _fbVal("ninjaAccount"),
                   incoming_dir: _fbVal("ninjaDir") },
    tradovate: { enabled: _fbLocal.tradovate,
                 username: _fbVal("tvUser"),
                 demo: !!($("tvDemo") || {}).checked },
    topstep: { enabled: _fbLocal.topstep,
               username: _fbVal("tsUser"),
               base_url: _fbVal("tsUrl") || "https://api.topstepx.com" }
  };
  const pw = _fbVal("tvPass"); if (pw) payload.tradovate.password = pw;
  const tk = _fbVal("tsKey");  if (tk) payload.topstep.api_key = tk;
  try {
    modeStatus = await askBridge("/config", { futures_brokers: payload });
    if ($("fbState")) $("fbState").textContent = "saved — futures route there now";
  } catch (e) {
    if ($("fbState")) $("fbState").textContent = "saved on this PC — it'll sync when the bridge is up";
  }
  paintFuturesBrokers();
}

function _wireFb(id, key, fieldsId) {
  const b = $(id);
  if (!b) return;
  b.onclick = async () => {
    _fbLocal[key] = !_fbLocal[key];
    _fbSeeded = true;
    _fbBtn(id, _fbLocal[key]);
    try { chrome.storage.local.set({ fb_toggles: _fbLocal }); } catch (e) {}
    await saveFuturesBrokers();   // persist to the bridge immediately
  };
}
_wireFb("fbWebull", "webull", null);
_wireFb("fbNinja", "ninja", "ninjaFields");
_wireFb("fbTradovate", "tradovate", "tradovateFields");
_wireFb("fbTopstep", "topstep", "topstepFields");
if ($("fbSave")) $("fbSave").onclick = saveFuturesBrokers;

/* ---- manual futures trigger — fire a buy/sell/close by hand ----------------
 * Sends a futures order through the SAME pipeline as a room alert, so it fans
 * out to whatever brokers are on under "Trade futures from". Tagged manual so
 * it fills at once and the hours guard can't block it. With a price it's a
 * labeled entry the parser reads as a limit; blank price = market. */
async function _fireManualFutures(text, label) {
  const st = $("mfState");
  if (st) st.textContent = "sending " + label + "…";
  try {
    await chrome.runtime.sendMessage({
      type: "MESSAGE", mid: "manualfut-" + Date.now(),
      text: text, full: text, author: "🎯 MANUAL",
      channelId: "829754942817828884", postedAt: Date.now(), test: true,
      history: false, reply: false,
      url: "https://discord.com/channels/manual/futures" });
    if (st) st.textContent = label + " sent — check the log and your broker.";
  } catch (e) {
    if (st) st.textContent = "couldn't send it — is the extension awake?";
  }
  setTimeout(render, 800);
}
function _mfEntry(dir) {
  const sym = (($("mfSym") || {}).value || "MNQ").trim().toUpperCase() || "MNQ";
  const price = (($("mfPrice") || {}).value || "").trim();
  // A price makes it a labeled entry the parser reads as a limit; blank = market.
  const text = price
    ? "Ticker: " + sym + " " + dir + " Entry: " + price
    : sym + " | " + dir + " HERE";
  return _fireManualFutures(text, sym + " " + dir + (price ? " @ " + price : " (market)"));
}
if ($("mfLong")) $("mfLong").onclick = () => _mfEntry("LONG");
if ($("mfShort")) $("mfShort").onclick = () => _mfEntry("SHORT");
if ($("mfClose")) $("mfClose").onclick = () => {
  const sym = (($("mfSym") || {}).value || "MNQ").trim().toUpperCase() || "MNQ";
  return _fireManualFutures("all out of " + sym, "close " + sym);
};

/* One-glance status bar — the whole setup on a single line, plus the one thing
 * to fix if anything's red. No more hunting through the panel. */
function _dot(ok) { return ok ? "✅" : "⛔"; }
async function paintStatus() {
  const bar = $("stBar"), fix = $("stFix");
  if (!bar) return;
  const st = modeStatus;
  const bridge = !!st;
  const paperKeys = !!(st && st.paper_keys_in);
  const paper = !!(st && st.paper);
  const ai = !!(st && st.ai_enabled);
  let voiceN = 0;
  try { const r = await chrome.runtime.sendMessage({ type: "VOICE_STATE" });
        voiceN = (r && r.listening || []).length; } catch (e) {}
  // The key being SAVED is what "set up" means — listening in a room is a
  // per-room action you take live, not part of setup. So the step is done the
  // moment the Deepgram key is in, same as the Webull/Claude keys.
  let dgKey = "";
  try { dgKey = (await chrome.storage.local.get("deepgram_key")).deepgram_key || ""; } catch (e) {}
  let v = "?"; try { v = (chrome.runtime.getManifest() || {}).version || "?"; } catch (e) {}
  const money = [];
  if (st && st.buying_power != null)
    money.push("$" + Math.round(st.buying_power).toLocaleString() + " margin");
  if (st && st.futures_buying_power != null)
    money.push("$" + Math.round(st.futures_buying_power).toLocaleString() + " futures");
  bar.textContent = [
    "Bridge " + _dot(bridge),
    "Webull " + ((st && (st.connected || paperKeys)) ? "✅" : (st && st.has_keys ? "⛔" : "—")),
    "Futures " + ((st && st.futures_account) ? "✅" : "—"),
    "AI " + (ai ? "✅" : "off"),
    "Voice " + (voiceN ? (voiceN + " 🎙") : (dgKey ? "✅" : "off"))
  ].join("  ·  ") + (money.length ? "   ·   " + money.join(" · ") : "");
  // A short "what to do next" checklist — only the steps not done yet, in
  // order. Empty when you're fully set up, so it disappears once you're ready.
  const steps = [];
  if (!bridge) steps.push("① Start the bridge — double-click 🎯 START HERE on your PC.");
  else {
    if (!paperKeys) steps.push("② Paper trading — add your Webull SANDBOX key in the Keys tab.");
    else if (!paper) steps.push("② Sandbox key saved but not connected — hit Update, or reconnect it.");
    if (!ai) steps.push("③ Smarter reads (optional) — add your Claude key in the Keys tab.");
    if (!dgKey) steps.push("④ Voice rooms (optional) — add your Deepgram key in the Keys tab.");
  }
  fix.innerHTML = steps.length
    ? "<b style='color:#e6edf6'>Set up:</b><br>" + steps.join("<br>")
    : "✅ All set — you're ready.";
  fix.style.color = steps.length ? "#fbbf24" : "#34d399";
}

let paperOn = false;
function paintPaper() {
  const s = modeStatus || {};
  paperOn = !!s.paper;
  const btn = $("paperbtn");
  if (!btn) return;
  btn.textContent = paperOn ? "ON" : "off";
  btn.className = "tgl " + (paperOn ? "live" : "safe");
  if ($("paperstate")) {
    $("paperstate").textContent = !s.paper_keys_in
      ? "This is your test engine. Paste your Webull SANDBOX key in the PAPER "
        + "boxes below — a separate key from your live one — and every test "
        + "trade fills in your $1M Webull paper books. Until then, the built-in "
        + "honest-fill sim stands in."
      : (s.paper_available
         ? "ON — every test trade fills in your $1M Webull paper account, scored per room."
         : (s.paper_warning
            || "Sandbox key saved but not connected yet — tap Update (or restart), "
               + "then it switches on by itself. In-house sim meanwhile."));
  }
}

let simRealistic = false;
let simLadder = false;
function paintSim() {
  const s = (modeStatus || {}).simulation || {};
  simRealistic = !!s.realistic_fills;
  const btn = $("simreal");
  if (btn) {
    btn.textContent = simRealistic ? "ON" : "off";
    btn.className = "tgl " + (simRealistic ? "live" : "safe");
  }
  if ($("simoffset") && document.activeElement !== $("simoffset"))
    $("simoffset").value = s.entry_offset_dollars || "";
  if ($("simbe") && document.activeElement !== $("simbe"))
    $("simbe").value = (s.auto_breakeven && s.auto_breakeven.enabled)
      ? (s.auto_breakeven.at_pct || 10) : "";
  simLadder = !!(s.auto_ladder && s.auto_ladder.enabled);
  const lb = $("simladder");
  if (lb) {
    lb.textContent = simLadder ? "ON" : "off";
    lb.className = "tgl " + (simLadder ? "live" : "safe");
  }
}

/* The keys go to the bridge and nowhere else. Nothing is written to
 * chrome.storage — the browser forgets them the moment they're sent, which is
 * the whole reason the bridge exists in the first place. */
$("paperbtn").onclick = async () => {
  paperOn = !paperOn;
  const btn = $("paperbtn");
  btn.textContent = paperOn ? "ON" : "off";
  btn.className = "tgl " + (paperOn ? "live" : "safe");
  try {
    modeStatus = await askBridge("/config", { paper_trading: paperOn });
  } catch (e) {
    $("paperstate").textContent = "couldn't reach the bridge — START HERE first";
  }
  paintPaper();
};

// The "Honest fills" toggle was a knob on the OLD in-house simulator, which is
// off now (Webull paper gives real fills). The button is gone from the UI;
// guard the handler so its absence can't throw at popup load.
if ($("simreal")) $("simreal").onclick = async () => {
  simRealistic = !simRealistic;
  paintSimQuick();
  await saveSim();
};
function paintSimQuick() {
  const btn = $("simreal");
  if (!btn) return;            // toggle removed from the UI
  btn.textContent = simRealistic ? "ON" : "off";
  btn.className = "tgl " + (simRealistic ? "live" : "safe");
}
$("simladder").onclick = async () => {
  simLadder = !simLadder;
  const b = $("simladder");
  b.textContent = simLadder ? "ON" : "off";
  b.className = "tgl " + (simLadder ? "live" : "safe");
  await saveSim();
};
async function saveSim() {
  const off = parseFloat($("simoffset").value);
  const be = parseFloat($("simbe").value);
  const sim = {
    realistic_fills: simRealistic,
    entry_offset_dollars: isNaN(off) ? 0 : off,
    auto_breakeven: { enabled: !isNaN(be) && be > 0,
                      at_pct: isNaN(be) ? 10 : be, sell_fraction: 0.10 },
    auto_ladder: { enabled: simLadder, keep_runners: 2,
                   rungs: [{ at: 10, sell: 1, stop_to: null },
                           { at: 20, sell: 1, stop_to: 0 },
                           { at: 30, sell: 1, stop_to: 10 }] }
  };
  try {
    modeStatus = await askBridge("/config", { simulation: sim });
    $("simstate").textContent = "saved — applies to the next trade";
  } catch (e) {
    $("simstate").textContent = "couldn't reach the bridge — START HERE first";
  }
  paintSim();
}
$("simsave").onclick = saveSim;

/* ---- one-click bracket strategy (LIVE-safe) -------------------------------
 * 1 contract on every entry, take profit at +15%, hard stop at -15%. It lives
 * in TWO places on purpose: the bridge (so orders actually get the +/-15%
 * bracket and the single-contract clamp) and the extension's settings (so the
 * worker sizes every entry to 1 before the order even leaves the browser).
 * Painted from the bridge's reported state so a reload always tells the truth.
 */
let bracketOn = false;
function paintStrat() {
  const s = (modeStatus || {}).strategy || {};
  bracketOn = !!s.enabled;
  const btn = $("bracketstrat");
  if (btn) {
    btn.textContent = bracketOn ? "ON" : "off";
    btn.className = "tgl " + (bracketOn ? "live" : "safe");
  }
}
if ($("bracketstrat")) $("bracketstrat").onclick = async () => {
  bracketOn = !bracketOn;
  const btn = $("bracketstrat");
  btn.textContent = bracketOn ? "ON" : "off";
  btn.className = "tgl " + (bracketOn ? "live" : "safe");
  const strat = { enabled: bracketOn, take_profit_pct: 20,
                  stop_loss_pct: 10, one_contract: true };
  // Extension settings first — this is what the worker reads to force qty=1.
  try {
    const { settings } = await chrome.storage.local.get("settings");
    const s = settings || {};
    s.strategy = strat;
    await chrome.storage.local.set({ settings: s });
  } catch (e) {}
  // Then the bridge, so live/paper orders get the actual +15%/-15% bracket.
  try {
    modeStatus = await askBridge("/config", { strategy: strat });
    if ($("bracketstate"))
      $("bracketstate").textContent = bracketOn
        ? "ON — every entry is 1 contract, +20% take-profit, −10% stop. Live and paper."
        : "Off — sizing and exits go back to the room's calls.";
  } catch (e) {
    if ($("bracketstate"))
      $("bracketstate").textContent = "Saved in the browser, but couldn't reach the bridge — START HERE first.";
  }
  paintStrat();
};

if ($("propadd")) $("propadd").onclick = async () => {
  const name = $("propname").value.trim();
  if (!name) { $("propstate").textContent = "give it a name first"; return; }
  try {
    modeStatus = await askBridge("/props", { add: {
      name, platform: $("propplatform").value,
      username: $("propuser").value.trim(),
      password: $("proppass").value,
      extra: $("propextra").value.trim() } });
    $("propstate").textContent = modeStatus.message || "saved";
    $("propname").value = ""; $("propuser").value = "";
    $("proppass").value = ""; $("propextra").value = "";
  } catch (e) {
    $("propstate").textContent = "couldn't reach the bridge — START HERE first";
  }
  paintProps();
};

$("savekeys").onclick = async () => {
  const key = $("wbkey").value.trim();
  const secret = $("wbsecret").value.trim();
  const el = $("keystate");
  if (!key || !secret) {
    // The recurring trap: keys pasted into the PAPER boxes below, but this
    // (LIVE) button pressed. Point them at the right button instead of the
    // baffling "both boxes are empty" when they clearly typed something.
    const pk = ($("wbpkey") || {}).value, ps = ($("wbpsecret") || {}).value;
    if ((pk && pk.trim()) || (ps && ps.trim())) {
      el.textContent = "Those are your SANDBOX keys — hit \"Save paper keys to " +
        "this PC\" just below, not this one. (This top button is for LIVE keys.)";
      return;
    }
    el.textContent = "Both boxes need something in them — the key and the secret.";
    return;
  }
  $("savekeys").textContent = "Saving and checking…";
  try {
    const r = await askBridge("/keys", { app_key: key, app_secret: secret });
    modeStatus = r;
    el.textContent = r.message || "saved";
    if (r.ok) {
      $("wbkey").value = ""; $("wbsecret").value = "";
      const ke = $("keyEntry"); if (ke) delete ke.dataset.forceOpen;
    }
    paintMode();
    paintKeys();     // collapse back to the saved summary
  } catch (e) {
    el.textContent = "Couldn't reach the bridge on your PC — double-click " +
      "START HERE first, then try again.";
  }
  $("savekeys").textContent = "Save keys to this PC";
};

$("savepaperkeys").onclick = async () => {
  const key = $("wbpkey").value.trim();
  const secret = $("wbpsecret").value.trim();
  const el = $("paperkeystate");
  if (!key || !secret) {
    el.textContent = "Both boxes need something — the sandbox key and secret.";
    return;
  }
  $("savepaperkeys").textContent = "Saving and checking…";
  try {
    const r = await askBridge("/keys",
      { paper_app_key: key, paper_app_secret: secret });
    modeStatus = r;
    el.textContent = r.message || "saved";
    if (r.ok) {
      $("wbpkey").value = ""; $("wbpsecret").value = "";
      const pe = $("paperKeyEntry"); if (pe) delete pe.dataset.forceOpen;
    }
    paintMode();
    paintPaper();
    paintKeys();     // collapse the paper key group back to its summary
  } catch (e) {
    el.textContent = "Couldn't reach the bridge on your PC — double-click " +
      "START HERE first, then try again.";
  }
  $("savepaperkeys").textContent = "Save paper keys to this PC";
};

/* ---- AI reader — reading intelligence on the misses ---------------------- */
function paintAi(st) {
  const on = !!(st && st.ai_enabled);
  const el = $("aiState");
  if (el) { el.textContent = on ? "ON" : "off"; el.style.color = on ? "#34d399" : "#9aa"; }
}
$("saveaikey").onclick = async () => {
  const key = $("aiKey").value.trim();
  const el = $("aikeystate");
  if (!key) { el.textContent = "Paste your Claude API key first."; return; }
  $("saveaikey").textContent = "Turning on…";
  try {
    const r = await askBridge("/config", { ai_api_key: key, ai_enabled: true });
    modeStatus = r;
    el.textContent = r.ai_enabled ? "AI reading is ON — it'll read the misses." :
                     (r.message || "saved");
    if (r.ai_enabled) $("aiKey").value = "";
    paintAi(r);
  } catch (e) {
    el.textContent = "Couldn't reach the bridge — double-click START HERE first.";
  }
  $("saveaikey").textContent = "Turn on AI reading";
};
$("aioff").onclick = async () => {
  const el = $("aikeystate");
  try {
    const r = await askBridge("/config", { ai_enabled: false });
    modeStatus = r;
    el.textContent = "AI reading is off.";
    paintAi(r);
  } catch (e) {
    el.textContent = "Couldn't reach the bridge — double-click START HERE first.";
  }
};

/* Double-check entries — a browser-side toggle; the key stays on the bridge. */
async function paintVerify() {
  let on = false;
  try { on = !!(await chrome.storage.local.get("ai_verify")).ai_verify; } catch (e) {}
  const b = $("aiVerifyBtn");
  if (b) { b.textContent = on ? "on" : "off"; b.className = "tgl " + (on ? "live" : "safe"); }
}
if ($("aiVerifyBtn")) $("aiVerifyBtn").onclick = async () => {
  let on = false;
  try { on = !!(await chrome.storage.local.get("ai_verify")).ai_verify; } catch (e) {}
  try { await chrome.storage.local.set({ ai_verify: !on }); } catch (e) {}
  paintVerify();
};
paintVerify();

/* ---- Voice listener — Deepgram, per tab, several at once ------------------ */
function paintVoice(list) {
  list = list || [];
  const el = $("voiceState");
  if (el) { el.textContent = list.length ? (list.length + " listening") : "off";
            el.style.color = list.length ? "#34d399" : "#9aa"; }
  const box = $("voiceList");
  if (box) box.innerHTML = list.map(v =>
    "🎙 " + (v.label || v.id) + " — " + (v.state || "…")).join("<br>");
}
async function refreshVoice() {
  try { const r = await chrome.runtime.sendMessage({ type: "VOICE_STATE" });
        paintVoice(r && r.listening); }
  catch (e) { paintVoice([]); }
}
$("savedg").onclick = async () => {
  const key = $("dgKey").value.trim();
  const el = $("dgstate");
  if (!key) { el.textContent = "Paste your Deepgram key first."; return; }
  try { await chrome.storage.local.set({ deepgram_key: key });
        el.textContent = "Deepgram key saved to this PC."; $("dgKey").value = ""; }
  catch (e) { el.textContent = "couldn't save it"; }
};
$("listenTab").onclick = async () => {
  const el = $("dgstate");
  let tab;
  try { [tab] = await chrome.tabs.query({ active: true, currentWindow: true }); }
  catch (e) {}
  if (!tab) { el.textContent = "couldn't find the active tab"; return; }
  const label = ((tab.title || "").replace(/ \| Discord.*/, "").trim() || tab.url || "tab").slice(0, 40);
  el.textContent = "starting…";
  try {
    const r = await chrome.runtime.sendMessage({ type: "VOICE_START", tabId: tab.id, label });
    el.textContent = (r && r.ok) ? "listening — every word is being written down"
                                 : ("couldn't start: " + (r && r.why || "?"));
  } catch (e) { el.textContent = "couldn't reach the background worker"; }
  refreshVoice();
};
$("stopAllVoice").onclick = async () => {
  try { await chrome.runtime.sendMessage({ type: "VOICE_STOP_ALL" }); } catch (e) {}
  $("dgstate").textContent = "stopped all listening.";
  refreshVoice();
};
refreshVoice();


/* ---- the day as a table ---------------------------------------------------
 * One row per trade: who called it, the contract, what you paid, every
 * partial sale, and how it ended. This is the page you actually read at
 * lunchtime — the log is the diary, this is the scoreboard. */
const keySym = k => String(k || "").split("|").pop();
const keyWho = k => String(k || "").split("|")[0];

function contractStr(r) {
  return [r.symbol, r.expiry || "",
          (r.strike != null && r.strike !== "" ? r.strike : "") +
          (r.side === "PUTS" ? "P" : r.side === "CALLS" ? "C" : "")]
         .filter(Boolean).join(" ");
}

/* The rooms and their toggle rows. Every room starts (and stays) TESTING
 * until HE flips it — LIVE is a per-room decision on top of the big REAL
 * switch, never instead of it. */
// The real Discord/Whop names the reader captured on the page (channelId ->
// name), loaded from storage each time the popup renders. These WIN over the
// hand-typed ROOM_NAMES below — those are only a fallback for a room that
// hasn't been opened in a tab yet, so its real name hasn't been seen.
let CAP_NAMES = {};
async function loadCapNames() {
  try { CAP_NAMES = (await chrome.storage.local.get("chan_names")).chan_names || {}; }
  catch (e) { CAP_NAMES = {}; }
}
// Just the channel, never the server. Discord/Whop names arrive as
// "#channel | Server Name" or "channel - Server - Discord"; keep only the part
// before the first separator, drop a leading "(3)" unread count and any "#".
function _channelOnly(name) {
  let s = String(name || "");
  s = s.split(" | ")[0].split(" — ")[0];
  s = s.replace(/\s[-–]\s.*$/, "");          // "channel - Server" -> "channel"
  s = s.replace(/^\(\d+\)\s*/, "");          // drop unread count
  s = s.replace(/^[#﹟＃｜|\s]+/, "").trim();   // drop leading hash / divider
  return s || String(name || "").trim();
}
function chanLabel(id) {
  const k = String(id || "");
  return _channelOnly(CAP_NAMES[k] || ROOM_NAMES[k] || k || "this room");
}
const ROOM_NAMES = { "829754942817828884": "Honeydrip daytrades",
                     "987515353670221834": "Aristotle",
                     "1144369893760831489": "Midas",
                     "1433933203302776852": "Aristotle small acct",
                     "642437862930907158": "RWGates",
                     "769797179992571914": "Option Alerts",
                     "880503518878892143": "Lotto Alerts",
                     "769797819770732554": "Options Watchlist",
                     "1137873895832174672": "Futures Alerts",
                     "whop:day-trades": "Whop Day Trades",
                     "whop:futures": "Whop Futures",
                     "whop:high-risk": "Whop High Risk",
                     "whop:2k-challenge": "Whop 2K Challenge",
                     "whop:swing": "Whop Swing Trades",
                     "whop:long-term": "Whop Long Term",
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
                     "874280313038192670": "Demon Alerts",
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
                     "1471700027662405712": "ZT fut-6" };

/* The per-room scoreboard he asked for: "trade information, won, lost,
 * profits, from each individual channel just to have good data to see where
 * everything comes from." Built from the day's finished trades (which carry
 * their room now) plus what's still open. */
function renderRoomStats(wallet, dayTable) {
  const el = $("roomstats");
  if (!el) return;
  const rows = {};
  for (const tr of ((wallet || {}).trades || [])) {
    const r = tr.room || "(before room tags)";
    const s = rows[r] = rows[r] || { w: 0, l: 0, pl: 0, open: 0 };
    if ((tr.pl || 0) >= 0) s.w += 1; else s.l += 1;
    s.pl += tr.pl || 0;
  }
  for (const r of (dayTable || [])) {
    if (!r.all_out) {
      const s = rows[r.room || "(before room tags)"] =
        rows[r.room || "(before room tags)"] || { w: 0, l: 0, pl: 0, open: 0 };
      s.open += 1;
    }
  }
  // Rooms with any history join the board even if quiet today — that's
  // the whole point of "stay with the best performers".
  for (const n of Object.keys(scoreAll || {})) {
    rows[n] = rows[n] || { w: 0, l: 0, pl: 0, open: 0 };
  }
  const names = Object.keys(rows);
  if (!names.length) { el.style.display = "none"; return; }
  el.style.display = "";
  const money = n => (n < 0 ? "-$" : "+$") + Math.abs(Math.round(n));
  const rank = n => (scoreAll && scoreAll[n]) ? scoreAll[n].pl : rows[n].pl;
  el.innerHTML = "<div class=\"tablehead\"><b>By room — today &amp; all time</b></div>" +
    names.sort((a, b) => rank(b) - rank(a)).map(n => {
      const s = rows[n];
      const a = (scoreAll || {})[n];
      const today = s.w + s.l + s.open
        ? "today " + s.w + "-" + s.l + " " + money(s.pl) +
          (s.open ? " · " + s.open + " open" : "")
        : "quiet today";
      const ever = a
        ? " &nbsp;·&nbsp; all time " + a.w + "-" + a.l + " " + money(a.pl) +
          " (" + a.days + "d)"
        : "";
      return '<div class="trow"><b>' + chanLabel(n) + "</b>" +
        '<span class="sub">' + today + ever + "</span></div>";
    }).join("");
}

function renderRoomToggles(channelLive, channelPull) {
  const box = $("roomtoggles");
  if (!box) return;
  box.innerHTML = Object.keys(ROOM_NAMES).map(id => {
    const live = !!(channelLive || {})[id];
    const pull = !!(channelPull || {})[id];
    // ONE button, one click, flips and saves instantly. No dropdown, no
    // confirm, no Save step — his word. Red is reserved for real money.
    // Second toggle (8/11/26): entry mode. "instant" buys the alert at the
    // ask; "RN wait" hands it to the bridge's round-number pullback watcher
    // (paper-only there until proven).
    return '<div class="row" style="margin-bottom:4px">' +
           '<span class="grow" style="font-size:12px">' + chanLabel(id) +
           '</span>' +
           '<button data-pull="' + id + '" title="Entry mode: instant = buy the ' +
           'alert at the ask. RN wait = wait for the stock to touch the next ' +
           'whole dollar first (paper only until proven)." ' +
           'style="font-size:10px;margin-right:6px;padding:1px 7px;border-radius:9px;' +
           'cursor:pointer;border:1px solid ' + (pull ? "#60a5fa" : "#3a4254") +
           ';background:' + (pull ? "#1d3a5f" : "transparent") +
           ';color:' + (pull ? "#93c5fd" : "#7d8697") + '">' +
           (pull ? "RN wait" : "instant") + '</button>' +
           '<span style="font-size:11px;letter-spacing:.04em;width:52px;' +
           'text-align:right;color:' + (live ? "#f87171" : "#7d8697") + '">' +
           (live ? "LIVE" : "testing") + '</span>' +
           '<button data-room="' + id + '" class="tgl money ' +
           (live ? "live" : "safe") + '"></button></div>';
  }).join("");
  box.querySelectorAll("button[data-room]").forEach(btn => {
    btn.onclick = async () => {
      const { settings } = await chrome.storage.local.get("settings");
      const s = settings || {};
      s.channel_live = s.channel_live || {};
      const id = btn.dataset.room;
      if (s.channel_live[id]) delete s.channel_live[id];
      else s.channel_live[id] = true;
      await chrome.storage.local.set({ settings: s });
      renderRoomToggles(s.channel_live, s.channel_pullback);
    };
  });
  box.querySelectorAll("button[data-pull]").forEach(btn => {
    btn.onclick = async () => {
      const { settings } = await chrome.storage.local.get("settings");
      const s = settings || {};
      s.channel_pullback = s.channel_pullback || {};
      const id = btn.dataset.pull;
      if (s.channel_pullback[id]) delete s.channel_pullback[id];
      else s.channel_pullback[id] = true;
      await chrome.storage.local.set({ settings: s });
      renderRoomToggles(s.channel_live, s.channel_pullback);
    };
  });
}


function renderTable(rows, el) {
  if (!rows || !rows.length) {
    el.innerHTML = "";   // no trades = nothing to say
    return;
  }
  const money = n => (n < 0 ? "-$" : "+$") + Math.abs(Math.round(n));
  el.innerHTML = rows.map(r => {
    const state = r.all_out
      ? (r.state === "stopped" ? "STOPPED OUT"
         : r.state === "nofill" ? "NO FILL"
         : r.state === "failed" ? "CHECK WEBULL" : "ALL OUT")
      : (r.state === "working" ? "BID IN" : "LIVE · holding " + r.qty);
    const cls = r.all_out
      ? (r.state === "nofill" ? "flat" : (r.pl >= 0 ? "up" : "down"))
      : "livepos";
    // Every fill and every sale carries its New York time, so a row reads
    // "in 09:33 5 @ 4.50 · out 09:43 3 @ 4.15" and he can line it up
    // against the room's messages minute by minute.
    const ins = (r.entries || [])
      .map(e => (e.t ? clock(e.t * 1000) + " " : "") +
                e.qty + " @ " + Number(e.price).toFixed(2)).join(" + ");
    const outs = (r.exits || [])
      .map(e => (e.t ? clock(e.t * 1000) + " " : "") +
                e.qty + " @ " + Number(e.price).toFixed(2)).join(", ");
    const bits = [];
    if (ins) bits.push("in " + ins);
    if (outs) bits.push("out " + outs);
    if (r.all_out && r.state !== "nofill") bits.push(money(r.pl));
    else if ((r.exits || []).length) bits.push(money(r.pl) + " so far");
    const dirTag = r.kind === "future"
      ? (r.direction < 0 ? "SHORT " : "LONG ") : "";
    return '<div class="trow"><b>' + dirTag + contractStr(r) + "</b> · " +
           (r.who || "?") + ' · <span class="tag ' + cls + '">' + state +
           "</span><span class=\"sub\">" +
           (bits.join(" · ") || "nothing has happened yet") + "</span></div>";
  }).join("");
}

/* Previous days live on the bridge as one file per date. Picking one swaps
 * the table to that day and stops the live refresh overwriting it; "today"
 * hands it back to the live feed. */
let viewingDay = "";        // "" = today, live
let viewedRows = null;

function etToday() {
  const p = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York",
    year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  return p;   // 2026-08-01
}

let scoreAll = null;      // all-time per-room record, from the bridge

async function loadScoreboard() {
  try { scoreAll = (await askBridge("/scoreboard")).rooms || null; }
  catch (e) { scoreAll = null; }
}

async function loadDays() {
  // The first entry is today — shown as the actual date, his ask.
  const first = $("dayspick").options[0];
  if (first) first.textContent = etToday();

  try {
    const r = await askBridge("/days");
    const sel = $("dayspick");
    const have = new Set(Array.from(sel.options).map(o => o.value));
    for (const d of (r.days || []).slice().reverse()) {
      if (have.has(d)) continue;
      const o = document.createElement("option");
      o.value = d; o.textContent = d;
      sel.appendChild(o);
    }
  } catch (e) { /* bridge down; the picker just stays at "today" */ }
}

async function render() {
  const s = await getSettings();
  await loadCapNames();     // real room names the reader has seen, freshest first
  const { guardState: gs, log, wallet, day_table } =
    await chrome.storage.local.get(["guardState", "log", "wallet",
                                    "day_table"]);

  // The big word is what it IS right now. His call: drop the "click to turn it
  // off/on" sub-line — the button state speaks for itself.
  const arm = $("arm");
  if (s.armed) {
    arm.innerHTML = "ON";
    arm.className = "grow armed big";
  } else {
    arm.innerHTML = "OFF";
    arm.className = "grow safe big";
  }
  // The loud OFF banner — same red treatment as the bridge being down, because
  // an OFF bot is the other state where nothing trades. If it went OFF by itself
  // (auto-disarm after the bridge vanished), say so, since he didn't do it.
  const offEl = $("botOff");
  if (offEl) {
    offEl.style.display = s.armed ? "none" : "flex";
    if (!s.armed && $("botOffWhy")) {
      const autoOff = (log || []).some(e => String(e.what || "").includes("AUTO-DISARMED") &&
                                            (Date.now() - (e.t || 0)) < 90 * 60 * 1000);
      $("botOffWhy").textContent = autoOff
        ? "It auto-disarmed after the bridge went missing. Bring the bridge back, then turn it ON."
        : "Tap the big OFF button below to turn it back ON.";
    }
  }

  const held = Object.keys((gs && gs.positions) || {});
  const cap = parseInt(s.guards.max_trades_per_day, 10) || 0;
  const done = (gs && gs.count) || 0;
  const bits = [];
  bits.push(s.armed ? "following their calls" : "watching only, not trading");
  // 0 means you took the limit off on purpose, so say that rather than counting
  // down from a number that doesn't exist.
  bits.push(cap > 0 ? done + " of " + cap + " trades used today"
                    : done + (done === 1 ? " trade" : " trades") +
                      " today, no limit set");
  // "holding" and "bid in" are not the same thing any more. An entry rests on
  // the bid, so a symbol can be on this list with nobody having sold to you
  // yet — saying "holding SPY" then would be a lie you'd act on.
  // Positions are keyed "trader|SYM" now — two admins can be in the same
  // ticker and they are two different trades. On screen that reads as
  // "SPY (brett)".
  const posAll = (gs && gs.positions) || {};
  const showKey = k => keySym(k) +
    (keyWho(k) && keyWho(k) !== "?" ? " (" + keyWho(k) + ")" : "");
  const owned = held.filter(k => !posAll[k].pending);
  const waiting = held.filter(k => posAll[k].pending);
  const where = [];
  if (owned.length) where.push("holding " + owned.map(showKey).join(", "));
  if (waiting.length) where.push("bid in on " + waiting.map(showKey).join(", "));
  bits.push(where.length ? where.join(" · ") : "flat");
  $("state").textContent = bits.join(" · ");

  // What you're in right now, spelled out as a contract rather than a ticker.
  // The tracker already knows this — it has to, or it couldn't turn "all out of
  // AMD" into an order. This just puts it on screen.
  const pos = (gs && gs.positions) || {};
  const bpos = Array.isArray(brokerPos) ? brokerPos : [];
  // What Webull ACTUALLY holds wins — the popup mirrors the broker. A resting
  // bid the browser recorded but Webull hasn't shown as filled yet is drawn too,
  // as long as its symbol isn't already a real Webull position.
  const bsyms = new Set(bpos.map(b => String(b.symbol || "").toUpperCase()));
  const pendKeys = held.filter(k => (pos[k] || {}).pending &&
                                    !bsyms.has(keySym(k).toUpperCase()));
  if (!bpos.length && !pendKeys.length) {
    $("holding").innerHTML = "No active trades";
  } else {
    const rows = [];
    // 1) REAL Webull positions — live price and P&L, straight from the broker.
    for (const b of bpos) {
      const sym = String(b.symbol || "").toUpperCase();
      const contract = [sym, b.expiry || "",
        (b.strike != null ? b.strike : "") +
        (b.side === "PUTS" ? "P" : b.side === "CALLS" ? "C" : "")]
        .filter(Boolean).join(" ");
      const n = parseInt(b.qty || 1, 10) || 1;
      const paid = (b.fill != null) ? " · paid " + Number(b.fill).toFixed(2) : "";
      const now = (b.last != null) ? " · now " + Number(b.last).toFixed(2) : "";
      let plTxt = "";
      if (b.pl != null) {
        const up = b.pl >= 0;
        plTxt = ' <span style="color:' + (up ? "#4ade80" : "#f87171") + '">' +
          (up ? "+$" : "-$") + Math.abs(b.pl).toFixed(0) +
          (b.pl_pct != null ? " (" + (b.pl_pct >= 0 ? "+" : "") +
             b.pl_pct.toFixed(0) + "%)" : "") + "</span>";
      }
      const x = '<button class="posx" data-flat="' + encodeURIComponent(sym) +
                '" data-flatlive="' + (b.live ? "1" : "0") +
                '" title="Close this at Webull now">✕</button>';
      // LIVE (real money) vs PAPER (sandbox) — so a sandbox MSFT is never
      // mistaken for a real one. b.live comes tagged from the bridge.
      const tag = b.live
        ? '<span style="color:#f87171;font-size:10px;font-weight:700">LIVE</span> '
        : '<span style="color:#7d8697;font-size:10px;font-weight:700">PAPER</span> ';
      rows.push('<div class="posrow"><span class="grow">' + tag +
        '<span class="in">IN</span> <b>' +
        contract + '</b> <b>x' + n + "</b>" + paid + now + plTxt +
        "</span>" + x + "</div>");
    }
    // 2) Resting bids Webull hasn't confirmed filled yet.
    for (const k of pendKeys) {
      const p = pos[k] || {};
      const contract = [keySym(k), p.expiry || "",
        (p.strike != null ? p.strike : "") +
        (p.side === "PUTS" ? "P" : p.side === "CALLS" ? "C" : "")]
        .filter(Boolean).join(" ");
      const x = '<button class="posx" data-close="' + encodeURIComponent(k) +
                '" title="Cancel this">✕</button>';
      rows.push('<div class="posrow"><span class="grow"><span class="in wait">BID IN</span> <b>' +
        contract + "</b>" + (keyWho(k) !== "?" ? " · " + keyWho(k) + "'s call" : "") +
        (p.ts ? " — since " + clock(p.ts) : "") +
        " · nobody has sold to you yet</span>" + x + "</div>");
    }
    $("holding").innerHTML = rows.join("");
    // ✕ on a REAL Webull position closes it straight at the broker (/flatten),
    // so it works even for a position the book lost track of on a restart.
    $("holding").querySelectorAll("button[data-flat]").forEach(btn => {
      btn.onclick = async () => {
        btn.disabled = true; btn.textContent = "…";
        const sym = decodeURIComponent(btn.dataset.flat);
        const live = btn.dataset.flatlive === "1";
        try { await askBridge("/flatten", { symbol: sym, live: live }); } catch (e) {}
        setTimeout(render, 1000);
      };
    });
    // ✕ on a resting bid cancels it through the normal path.
    $("holding").querySelectorAll("button[data-close]").forEach(btn => {
      btn.onclick = async () => {
        const k = decodeURIComponent(btn.dataset.close);
        btn.disabled = true; btn.textContent = "…";
        const sym = keySym(k), who = keyWho(k);
        const room = (pos[k] && pos[k].channelId) || "829754942817828884";
        try {
          await chrome.runtime.sendMessage({
            type: "MESSAGE", mid: "manualclose-" + Date.now(),
            text: "all out of " + sym, full: "all out of " + sym,
            author: who && who !== "?" ? who : "🎯 MANUAL",
            channelId: room, postedAt: Date.now(), test: true,
            history: false, reply: false,
            url: "https://discord.com/channels/manual/close" });
        } catch (e) {}
        setTimeout(render, 800);
      };
    });
  }

  // The pretend account. It only exists on a dry run — in live mode Webull
  // knows what you've got, and printing a second number here that disagrees
  // with your real balance would be worse than printing nothing.
  //
  // Money leaves when a bid fills, comes back at whatever it sold for, and
  // what's left is what the next entry has to fit inside. Without this on
  // screen there was no way to tell whether the starting balance was doing
  // anything at all, and it wasn't.
  const purse = $("purse");
  if (!wallet) {
    purse.style.display = "none";
  } else {
    purse.style.display = "";
    const money = n => (n < 0 ? "-$" : "$") + Math.abs(n).toFixed(0);
    const rows = [];
    if (wallet.unlimited) {
      // The test account has no ceiling on purpose. The two numbers that
      // matter instead: what the day made, and the most cash that was ever
      // tied up at once — which is what funding this for real would take.
      const day = wallet.day != null ? wallet.day : wallet.realised;
      rows.push('<b>TEST · no limits</b> · <span class="' +
                (day >= 0 ? "up" : "down") + '">' +
                (day >= 0 ? "+" : "") + money(day) + " today</span>");
      rows.push('<span class="sub">most tied up at once: <b>' +
                money(wallet.peak) + "</b> — that's roughly what this day " +
                "would need for real</span>");
      const bits = [];
      if (wallet.reserved) bits.push(money(wallet.reserved) + " out in bids");
      if (wallet.open_cost) {
        bits.push(money(wallet.open_cost) + " in open trades" +
                  (wallet.open_worth != null
                   ? " (worth " + money(wallet.open_worth) + " now)" : ""));
      }
      if (bits.length) {
        rows.push('<span class="sub">' + bits.join(" · ") + "</span>");
      }
    } else {
      const day = wallet.equity - wallet.start;
      rows.push('<b>' + money(wallet.equity) + "</b> account · " +
                '<span class="' + (day >= 0 ? "up" : "down") + '">' +
                (day >= 0 ? "+" : "") + money(day) + " today</span>" +
                " · started " + money(wallet.start));
      const bits = [money(wallet.cash) + " cash"];
      if (wallet.reserved) bits.push(money(wallet.reserved) + " tied up in bids");
      if (wallet.open_cost) {
        bits.push(money(wallet.open_cost) + " in open trades" +
                  (wallet.open_worth != null
                   ? " (worth " + money(wallet.open_worth) + " now)" : ""));
      }
      rows.push('<span class="sub">' + bits.join(" · ") + "</span>");
    }
    const done = wallet.wins + wallet.losses;
    if (done) {
      rows.push('<span class="sub">' + done +
                (done === 1 ? " trade closed" : " trades closed") + " · " +
                wallet.wins + " up, " + wallet.losses + " down · " +
                (wallet.realised >= 0 ? "+" : "") + money(wallet.realised) +
                " banked</span>");
    }
    purse.innerHTML = rows.join("<br>");
  }

  // The scoreboard: today's table live from the bridge, or a previous day
  // loaded off the shelf. A loaded day stays put — the 2-second refresh only
  // repaints when you're on "today".
  if (viewingDay) {
    renderTable(viewedRows || [], $("daytable"));
  } else {
    renderTable(day_table || [], $("daytable"));
  }
  renderRoomStats(wallet, day_table);

  renderRoomToggles(s.channel_live || {}, s.channel_pullback || {});
  $("bridge").value = s.bridge_url;

  const box = $("log");
  box.innerHTML = "";
  const entries = (log || []).slice(0, 40);
  if (!entries.length) {
    box.innerHTML = '<div class="note">Nothing yet. Open the signal channel in a ' +
                    'Discord tab and leave it open — only messages that arrive ' +
                    'while the tab is open are read.</div>';
    return;
  }
  for (const e of entries) {
    const d = document.createElement("div");
    d.className = "e " + e.kind;
    // "SENT" and "FILLED" are two different lines on purpose. Your entry goes
    // in as a bid, so the order going out and somebody actually selling to you
    // are separate events, sometimes minutes apart and sometimes only one of
    // them happens at all.
    // "BID IN" is only ever true of an entry. A sell doesn't rest on the bid
    // waiting for somebody to come to it, so labelling an exit that way made
    // finished trades read like open ones — the log said "BID IN · CLOSE SPY
    // (+45%)" on a trade that was over.
    const isExit = e.action === "CLOSE" ||
                   /^CLOSE\b/.test(String(e.what || ""));
    const head = { sent: isExit ? "SOLD" : "BID IN",
                   fired: "FILLED", failed: "FAILED",
                   skipped: "SKIPPED", stopped: "STOPPED OUT",
                   ignored: "not a trade", update: "UPDATED" }[e.kind] || e.kind;
    d.innerHTML = "<b>" + head + (e.what ? " · " + e.what : "") + "</b>" +
                  "<span>" + (e.why || "") + "</span>" +
                  '<span style="display:block">' + ago(e.t) + " · " +
                  (e.author || "") + ": " +
                  String(e.text || "").slice(0, 90) + "</span>";
    // Click any line to copy the WHOLE thing — the head, the reason, and the
    // FULL untruncated message. Drag-selecting inside a popup is unreliable (it
    // can close on you) and the row only shows the first 90 chars anyway, so
    // "things don't copy" was really "I can't get the full line out." One click
    // now does it. The whole-log button still lives up top for everything.
    const full = head + (e.what ? " · " + e.what : "") +
                 (e.why ? "  |  " + e.why : "") +
                 "  |  " + (e.author || "") +
                 (e.text ? ": " + e.text : "");
    d.title = "click to copy this line";
    d.style.cursor = "copy";
    d.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(full);
      } catch (_) {
        // Clipboard API blocked in some popup states — fall back to a hidden
        // textarea + execCommand so the copy still lands.
        const ta = document.createElement("textarea");
        ta.value = full; ta.style.position = "fixed"; ta.style.opacity = "0";
        document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); } catch (__) {}
        ta.remove();
      }
      const b = d.querySelector("b");
      if (b) { const keep = b.textContent; b.textContent = "✓ copied";
               setTimeout(() => { b.textContent = keep; }, 1200); }
    });
    box.appendChild(d);
  }
}

async function patch(changes) {
  const s = await getSettings();
  await chrome.storage.local.set({ settings: Object.assign(s, changes) });
  chrome.runtime.sendMessage({ type: "ATTACHED" }).catch(() => {});
  render();
}

$("arm").onclick = async () => {
  const s = await getSettings();
  // stopped:false always. The old STOP button is gone, but an installation that
  // was left stopped would otherwise sit there refusing everything with no
  // button on screen to clear it. Turning it ON clears it.
  await patch({ armed: !s.armed, stopped: false });
};

if ($("save")) $("save").onclick = async () => {
  // The switch lives in TWO places on purpose: the extension (gates whether
  // a futures call fires at all) and the bridge's settings.json (second lock
  // on real orders). Saving sets both so they can't drift apart — and both
  // are told the allowed list is empty for good: "no filters wanted."
  try { await askBridge("/config", {
                                     allowed_symbols: [] }); }
  catch (e) { /* bridge down — the extension-side gate still holds */ }
  return patch({
    // channels are baked into the worker; callers are never filtered
    channel_ids: [], follow_admins: [],
    bridge_url: $("bridge").value.trim() || DEFAULTS.bridge_url,
    guards: DEFAULTS.guards
  });
};

/* You can't select text out of this popup — it closes the moment you click
 * anywhere else, which is why a whole day's log once had to be sent as a
 * search URL. This puts it on the clipboard as plain text, oldest first so it
 * reads like a morning rather than backwards. */
$("copylog").onclick = async () => {
  const { log, wallet, day_table } =
    await chrome.storage.local.get(["log", "wallet", "day_table"]);
  const head = { sent: "BID IN", fired: "FILLED", failed: "FAILED",
                 skipped: "SKIPPED", stopped: "STOPPED OUT",
                 ignored: "not a trade", update: "UPDATED" };
  const lines = (log || []).slice().reverse().map(e => {
    const isExit = e.action === "CLOSE" || /^CLOSE\b/.test(String(e.what || ""));
    const h = (e.kind === "sent" && isExit) ? "SOLD" : (head[e.kind] || e.kind);
    return [clock(e.t), h + (e.what ? " · " + e.what : ""),
            e.why || "", e.text ? (e.author || "?") + ": " + e.text : ""]
           .filter(Boolean).join("  |  ");
  });
  if (wallet && wallet.unlimited) {
    lines.unshift("test day " + (wallet.realised >= 0 ? "+" : "-") + "$" +
                  Math.abs(wallet.realised).toFixed(0) + " (" + wallet.wins +
                  " up / " + wallet.losses + " down, most tied up at once $" +
                  (wallet.peak || 0).toFixed(0) + ")", "");
  } else if (wallet) {
    lines.unshift("account $" + wallet.equity.toFixed(0) + " (started $" +
                  wallet.start.toFixed(0) + ", " + wallet.wins + " up / " +
                  wallet.losses + " down, banked $" +
                  wallet.realised.toFixed(0) + ")", "");
  }
  // The trade list up top — every trade of the day with its verdict, so the
  // analysis never depends on how far back the log happens to reach.
  const rows = (day_table || []).map(r => {
    const ins = (r.entries || []).map(e => (e.t ? clock(e.t * 1000) + " " : "") +
      e.qty + "@" + Number(e.price).toFixed(2)).join(" + ");
    const outs = (r.exits || []).map(e => (e.t ? clock(e.t * 1000) + " " : "") +
      e.qty + "@" + Number(e.price).toFixed(2)).join(", ");
    const verdict = r.all_out
      ? (r.state === "nofill" ? "NO FILL"
         : (r.pl >= 0 ? "WIN +$" + Math.round(r.pl) : "LOSS -$" + Math.abs(Math.round(r.pl))))
      : "STILL OPEN (" + r.qty + " held)";
    return [r.opened ? clock(r.opened * 1000) : "?",
            (r.who || "?") + " " + contractStr(r),
            ins ? "in " + ins : "no fill",
            outs ? "out " + outs : "", verdict].filter(Boolean).join("  |  ");
  });
  if (rows.length) {
    lines.unshift("");
    lines.unshift.apply(lines, ["THE DAY, TRADE BY TRADE:"].concat(rows, [""]));
  }
  const text = lines.join("\n") || "nothing logged yet";
  const btn = $("copylog");
  try {
    await navigator.clipboard.writeText(text);
    btn.textContent = "Copied — paste it anywhere";
  } catch (e) {
    // Clipboard blocked. Rather than fail quietly, hand it over as a file,
    // which is the same thing one step further away.
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    chrome.downloads.download({ url, filename: "sniper-log.txt", saveAs: true })
      .catch(() => chrome.tabs.create({ url }));
    btn.textContent = "Saved it as a file instead";
  }
  setTimeout(() => { btn.textContent = "Copy log"; }, 2500);
};

$("savelognow").onclick = async () => {
  const btn = $("savelognow");
  btn.disabled = true; btn.textContent = "💾 Saving…";
  try {
    await chrome.runtime.sendMessage({ type: "EXPORT_NOW" });
    btn.textContent = "💾 Saved — tell Claude to check";
  } catch (e) {
    btn.textContent = "💾 Save failed — is the bot on?";
  }
  setTimeout(() => { btn.disabled = false;
    btn.textContent = "💾 Save log now (for Claude)"; }, 2500);
};

/* Live countdown to the next auto-save. Now every 4 minutes — reckoned from the
 * last save (last_export), so it stays honest without knowing the worker's exact
 * alarm tick. Also shows when it last saved. */
const EXPORT_EVERY_MS = 4 * 60 * 1000;
async function tickExportTimer() {
  const el = $("exportTimer");
  if (!el) return;
  let last = 0;
  try { last = (await chrome.storage.local.get("last_export")).last_export || 0; } catch (e) {}
  let ms = last ? (last + EXPORT_EVERY_MS - Date.now()) : 0;
  if (ms < 0) ms = 0;
  const mm = Math.floor(ms / 60000);
  const ss = Math.floor((ms % 60000) / 1000);
  const lastBit = last ? " · last saved " + ago(last) : "";
  el.textContent = "Next auto-save in " + mm + ":" +
    String(ss).padStart(2, "0") + lastBit;
}
setInterval(tickExportTimer, 1000);
tickExportTimer();

$("export").onclick = async () => {
  const { captured } = await chrome.storage.local.get("captured");
  // Which room each line came from. Three rooms export into one file, and the
  // tag is what keeps their three dialects apart when the parser gets tuned.
  const ROOMS = { "829754942817828884": "main",
                  "987515353670221834": "aristotle",
                  "1144369893760831489": "midas",
                  "642437862930907158": "rwgates",
                  "769797179992571914": "option alerts",
                  "880503518878892143": "lotto alerts",
                  "769797819770732554": "options watchlist",
                  "1137873895832174672": "futures alerts",
                  "1433933203302776852": "aristotle-small" };
  // Whop rooms tag themselves "whop:/their/path" — shown as-is, so two
  // different Whop rooms stay two different lexicons in the file.
  // Sorted by when the message was POSTED, not when it was scraped —
  // scrolling up paints newest-first, and a file in paint order would read
  // like a week played backwards.
  // Only export the window the user picked in the dropdown.
  const sel = ($("exportRange") || {}).value || "60";
  let cutoff = 0;
  if (sel === "today") { const d = new Date(); d.setHours(0,0,0,0); cutoff = d.getTime(); }
  else { const mins = parseFloat(sel); if (mins > 0) cutoff = Date.now() - mins*60*1000; }
  const picked = (captured || []).filter(c => !cutoff || c.t >= cutoff);
  const rows = picked.slice().sort((a, b) => a.t - b.t).map(c =>
    new Date(c.t).toLocaleString() +
    "  [" + (ROOMS[c.channel] || c.channel || "?") + "]" +
    "  " + (c.author || "?") + ": " + c.text);
  const blob = new Blob([rows.join("\n") || "nothing captured yet"],
                        { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const tag = sel === "today" ? "today"
    : (parseFloat(sel) >= 60 ? "last" + (parseFloat(sel)/60) + "h" : "last" + sel + "m");
  await chrome.downloads.download({ url, filename: "signal-room-chat-" + tag + ".txt",
                                    saveAs: true })
    .catch(() => {
      // downloads permission missing or blocked — open it in a tab instead so
      // you can still copy it out.
      chrome.tabs.create({ url });
    });
};

/* The test-trade button. Fires a real entry, a trim, then a full exit — as
 * three synthetic messages pushed through the EXACT path a typed Discord call
 * takes: the same MESSAGE handler, the same parser, the same guards, the same
 * position book, the same bridge and paper broker. Nothing is special-cased, so
 * what you see is what a real room would get. It routes to PAPER only (no "live"
 * flag, a test room id), so it can never touch real money. */
function nextTradingDay() {
  // m/d for the next weekday (Mon–Fri). Options need a real trading day, and a
  // weekend expiry doesn't exist — roll to Monday.
  const d = new Date();
  do { d.setDate(d.getDate() + 1); } while (d.getDay() === 0 || d.getDay() === 6);
  return (d.getMonth() + 1) + "/" + d.getDate();
}
$("testtrade").onclick = async () => {
  const btn = $("testtrade");
  const type = (($("testtype") || {}).value || "C");
  const isFut = (type === "LONG" || type === "SHORT");
  // Futures use a futures symbol (MNQ, MES, ES, NQ...) and no strike/expiry.
  // If the box still has the options default "SPY", stand in a real micro so
  // the test actually parses as a future.
  let tk = ((($("testticker") || {}).value || "").trim()).toUpperCase();
  if (isFut && (!tk || tk === "SPY")) tk = "MNQ";
  if (!tk) tk = "SPY";
  const strike = ((($("teststrike") || {}).value || "800").trim() || "800");
  const cp = (type === "P") ? "P" : "C";
  const exp = ((($("testexp") || {}).value || "").trim()) || nextTradingDay();
  // A PAPER room id that's always in the listened list, so the channel gate
  // never blocks the test. The parser reads a future from the text itself
  // ("MNQ | LONG HERE"), so the room doesn't need to be a "futures" room.
  // postedAt = now so it's never history; a fresh mid each run for re-tests.
  const room = "829754942817828884";
  const base = Date.now();
  // Futures speak the room's own syntax: "MNQ | LONG HERE" is the entry the
  // parser reads as a futures OPEN with a direction; trims/closes are the same
  // shape as options. Options keep the "in TICKER EXP STRIKEC" entry.
  const steps = isFut ? [
    { text: tk + " | " + type + " HERE",  label: "① entry" },
    { text: "trimming " + tk + " @ 25%",  label: "② trim"  },
    { text: "all out of " + tk,           label: "③ exit"  }
  ] : [
    { text: "in " + tk + " " + exp + " " + strike + cp, label: "① entry" },
    { text: "trimming " + tk + " @ 25%",                 label: "② trim"  },
    { text: "all out of " + tk,                          label: "③ exit"  }
  ];
  const fire = (text, i) => chrome.runtime.sendMessage({
    type: "MESSAGE", mid: "test-" + base + "-" + i, text, full: text,
    author: "🧪 TEST", channelId: room, postedAt: Date.now(), test: true,
    history: false, reply: false, url: "https://discord.com/channels/test/" + room
  }).catch(() => {});

  // Entry now; trim after the entry has had time to fill on the sandbox; exit
  // after the trim. The gaps let the fill-watcher actually see a fill, so the
  // trim and exit act on a real position instead of a resting bid.
  btn.disabled = true; btn.textContent = "① entry sent…";
  fire(steps[0].text, 0);
  setTimeout(() => { btn.textContent = "② trim sent…"; fire(steps[1].text, 1); }, 9000);
  setTimeout(() => { btn.textContent = "③ exit sent…"; fire(steps[2].text, 2); }, 18000);
  setTimeout(() => {
    btn.disabled = false;
    btn.textContent = "🧪 Run test trade (entry → trim → exit)";
    render();
  }, 22000);
};

/* Update the app from the popup — pulls the newest build and restarts the
 * bridge on the PC, so START HERE is never needed just for an update. The
 * bridge goes away for a few seconds while it re-execs onto the new code, so
 * this waits, then re-checks that it came back up. */
$("updateapp").onclick = async () => {
  const btn = $("updateapp");
  const el = $("updatestate");
  btn.disabled = true;
  btn.textContent = "⏳";
  try {
    const r = await askBridge("/update", { go: true });
    el.textContent = r.message || (r.ok ? "updating…" : "couldn't update");
    if (r.ok && /restart/i.test(r.message || "")) {
      btn.textContent = "⏳";
      // Give the bridge time to re-exec, then confirm it's answering again.
      let back = false;
      for (let i = 0; i < 15 && !back; i++) {
        await new Promise(res => setTimeout(res, 1500));
        try {
          const m = await askBridge("/mode");
          if (m && (m.connected !== undefined || m.mode)) { back = true; }
        } catch (e) { /* still down, keep waiting */ }
      }
      if (back) {
        el.textContent = "Updated — the bridge is back up on the new version.";
        try { chrome.runtime.reload(); } catch (e) { /* extension refresh */ }
      } else {
        el.textContent = "Updated the files, but the bridge hasn't answered " +
          "yet. Give it a moment; if it stays quiet, double-click START HERE " +
          "once.";
      }
    }
  } catch (e) {
    el.textContent = "Couldn't reach the bridge on your PC — double-click " +
      "START HERE first, then try again.";
  }
  btn.disabled = false;
  btn.textContent = "🔄";
};

/* Show the version right on the panel so you never have to go hunting for it.
 * Reads the loaded extension's own manifest — after an update reloads the
 * extension, reopening the popup shows the new number. */
function showVersion() {
  try {
    const v = (chrome.runtime.getManifest() || {}).version || "?";
    const el = $("appVersion");
    if (el) el.textContent = "v" + v;
    const btn = $("updateapp");
    if (btn) btn.title = "Update to the latest version (on v" + v + ")";
  } catch (e) { /* not in an extension context */ }
}
showVersion();

/* Descriptions on hover — the gray help text under each control is hidden by
 * default and only appears when you hover the control (or the text itself), so
 * the panel reads clean. Status lines (the ones with an id, like fbState) keep
 * showing — those report live state, not help. */
(function descriptionsOnHover() {
  document.querySelectorAll(".note").forEach(n => {
    if (n.id) return;                         // status lines stay visible
    const trigger = n.previousElementSibling; // the label/row it explains
    if (!trigger) return;
    n.style.display = "none";
    const show = () => { n.style.display = "block"; };
    const hide = () => { n.style.display = "none"; };
    trigger.addEventListener("mouseenter", show);
    trigger.addEventListener("mouseleave", hide);
    n.addEventListener("mouseenter", show);
    n.addEventListener("mouseleave", hide);
  });
})();

/* Tabs — browse the panel by page. Every section kept its own id and handler;
 * switching a tab only changes which page is visible. */
/* Pencil buttons: each opens/closes the credential box for its broker, so the
 * ON switch only arms and the fields stay hidden until you want to edit. */
(function wireEditButtons() {
  document.querySelectorAll("button.edit[data-edit]").forEach(b => {
    b.onclick = () => {
      const t = $(b.dataset.edit);
      if (!t) return;
      const open = t.style.display && t.style.display !== "none";
      t.style.display = open ? "none" : "block";
    };
  });
})();

(function setupTabs() {
  const btns = document.querySelectorAll('#tabbar .tabbtn');
  btns.forEach(b => b.addEventListener('click', () => {
    const t = b.dataset.tab;
    btns.forEach(x => x.classList.toggle('on', x === b));
    document.querySelectorAll('.tabpane').forEach(p =>
      p.classList.toggle('on', p.dataset.tab === t));
    if (t === 'keys') { try { refreshVoice(); } catch (e) {} }
  }));
})();

/* ---- History grabber + per-room export ----------------------------------- */
async function activeTab() {
  try { const [t] = await chrome.tabs.query({ active: true, currentWindow: true }); return t; }
  catch (e) { return null; }
}
function channelOf(tab) {
  const m = ((tab && tab.url) || "").match(/channels\/[^/]+\/(\d+)/);
  return m ? m[1] : "";
}
// Grab ADDS this room to the queue. The background works the line one room at a
// time — brings each to the front, scrolls its history, saves to Downloads,
// closes the tab, next. Queue several with the button or Ctrl+Shift+X and walk
// away. Each goes 1 year back.
$("grabHistory").onclick = async () => {
  const el = $("grabState");
  const tab = await activeTab();
  if (!tab || !/discord\.com\/channels\//.test(tab.url || "")) {
    el.textContent = "Open the Discord room's tab first, then hit Grab."; return;
  }
  el.textContent = "added to the queue — the extension will bring it to the front, grab it, save it, close the tab, and move to the next. Watch the Logs tab.";
  try { await chrome.runtime.sendMessage({ type: "ENQUEUE_GRAB", tabId: tab.id }); }
  catch (e) { el.textContent = "couldn't reach the extension — reopen the popup and try again."; }
};
// Stop the run early: halt the current grab, save whatever it caught, and clear
// the rest of the queue.
$("grabStop").onclick = async () => {
  const el = $("grabState");
  try {
    await chrome.runtime.sendMessage({ type: "STOP_ALL_GRABS" });
    el.textContent = "stopping — saving whatever's been caught so far, and clearing the queue. Check your Downloads and the Logs tab.";
  } catch (e) {
    el.textContent = "couldn't reach the extension — reopen the popup and try again.";
  }
};

/* The previous-days picker. "today" is the live feed; a date is a file the
 * bridge saved, frozen until you pick something else. */
$("dayspick").onchange = async () => {
  const v = $("dayspick").value;
  if (!v) { viewingDay = ""; viewedRows = null; return render(); }
  try {
    const r = await askBridge("/day?date=" + v);
    viewingDay = v;
    viewedRows = r.table || [];
  } catch (e) {
    viewingDay = "";
    viewedRows = null;
  }
  render();
};

render();
setInterval(render, 2000);
refreshMode();
setInterval(refreshMode, 4000);
loadDays();
loadScoreboard();
