/* popup.js — the dashboard. Nothing here decides a trade; it only shows you
 * what happened and lets you change the settings the worker reads.
 *
 * ARMED vs SAFE is the switch you'll actually use. STOP is the one you'll be
 * glad exists: it survives closing the popup, closing the tab, and Chrome
 * putting the extension to sleep, because it's written to storage, not held
 * in a variable.
 */

const $ = id => document.getElementById(id);

const DEFAULTS = {
  armed: false, stopped: false, capture: true,
  bridge_url: "http://127.0.0.1:8787/order",
  channel_ids: [], follow_admins: [], allowed_symbols: [],
  trim_action: "ignore", close_at_trim_pct: 50,
  guards: { max_qty: 1, max_trades_per_day: 6, cooldown_seconds: 5,
            dedupe_seconds: 120, regular_hours_only: true,
            open_time: "09:30", close_time: "15:45",
            max_message_age_seconds: 20 }
};

const listToText = a => (a || []).join(", ");
const textToList = t => String(t || "").split(",")
  .map(s => s.trim()).filter(Boolean);

async function getSettings() {
  const { settings } = await chrome.storage.local.get("settings");
  const s = Object.assign({}, DEFAULTS, settings || {});
  s.guards = Object.assign({}, DEFAULTS.guards, (settings || {}).guards || {});
  return s;
}

function ago(t) {
  const s = Math.round((Date.now() - t) / 1000);
  if (s < 60) return s + "s ago";
  if (s < 3600) return Math.round(s / 60) + "m ago";
  return Math.round(s / 3600) + "h ago";
}

/* ---- the live / dry-run switch -------------------------------------------
 * This one lives on the bridge, not in the browser, because the bridge is the
 * only thing that can actually spend money. The popup just asks it what it is
 * and tells it to change. Flipping to live needs two clicks — one to ask, one
 * to mean it. Flipping back to dry run is instant, because the safe direction
 * should never make you confirm anything.
 */
let modeStatus = null;
let armLive = false;          // true when the button is waiting for click two
let armLiveTimer = null;

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

function paintMode() {
  const btn = $("mode"), sub = $("modestate");

  if (armLive) {
    btn.className = "grow confirm";
    btn.style.width = "100%";
    btn.textContent = "Click again to go LIVE";
    sub.textContent = "real money, no paper mode for options";
    return;
  }
  if (!modeStatus) {
    btn.className = "grow dry";
    btn.style.width = "100%";
    btn.textContent = "Bridge not running";
    sub.textContent = "start BRIDGE.bat on your PC and leave it open";
    return;
  }
  if (modeStatus.live) {
    btn.className = "grow live";
    btn.style.width = "100%";
    btn.textContent = "LIVE — click for DRY RUN";
    sub.textContent = modeStatus.connected
      ? ("real orders · Webull account " + (modeStatus.account || "?"))
      : ("LIVE but not connected: " + (modeStatus.error || "unknown"));
  } else {
    btn.className = "grow dry";
    btn.style.width = "100%";
    btn.textContent = "DRY RUN — click to go LIVE";
    sub.textContent = modeStatus.has_keys
      ? "orders are logged on your PC, nothing is sent"
      : "no Webull keys saved yet — run KEYS.bat first";
  }
}

async function refreshMode() {
  try {
    modeStatus = await askBridge("/mode");
  } catch (e) {
    modeStatus = null;      // bridge isn't running, which is a normal state
  }
  paintMode();
}

$("mode").onclick = async () => {
  if (modeStatus && modeStatus.live) {         // safe direction — just do it
    armLive = false;
    try { modeStatus = await askBridge("/mode", { live: false }); }
    catch (e) { modeStatus = null; }
    return paintMode();
  }
  if (!modeStatus) return refreshMode();
  if (!modeStatus.has_keys) {
    $("modestate").textContent =
      "there are no Webull keys saved yet — run KEYS.bat, then come back";
    return;
  }
  if (!armLive) {                              // first click: ask, don't act
    armLive = true;
    paintMode();
    clearTimeout(armLiveTimer);
    armLiveTimer = setTimeout(() => { armLive = false; paintMode(); }, 6000);
    return;
  }
  armLive = false;
  clearTimeout(armLiveTimer);
  try {
    const r = await askBridge("/mode", { live: true });
    modeStatus = r;
    paintMode();
    if (r.message) $("modestate").textContent = r.message;
  } catch (e) {
    modeStatus = null;
    paintMode();
  }
};

async function render() {
  const s = await getSettings();
  const { guardState: gs, log } = await chrome.storage.local.get(["guardState", "log"]);

  const arm = $("arm");
  if (s.armed) {
    arm.textContent = "ARMED — click to go SAFE";
    arm.className = "grow armed";
  } else {
    arm.textContent = "SAFE — click to ARM";
    arm.className = "grow safe";
  }

  const held = Object.keys((gs && gs.positions) || {});
  const bits = [];
  bits.push(s.stopped ? "STOPPED — nothing will fire until you clear it"
                      : (s.armed ? "watching" : "reading only, not trading"));
  bits.push(((gs && gs.count) || 0) + " of " + s.guards.max_trades_per_day +
            " trades used today");
  bits.push(held.length ? "holding " + held.join(", ") : "flat");
  $("state").textContent = bits.join(" · ");

  $("stop").textContent = s.stopped ? "CLEAR STOP" : "STOP";

  $("channels").value = listToText(s.channel_ids);
  $("admins").value = listToText(s.follow_admins);
  $("symbols").value = listToText(s.allowed_symbols);
  $("trim").value = s.trim_action;
  $("trimpct").value = s.close_at_trim_pct;
  $("maxqty").value = s.guards.max_qty;
  $("maxday").value = s.guards.max_trades_per_day;
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
    const head = { fired: "FIRED", failed: "FAILED", skipped: "SKIPPED",
                   ignored: "not a trade" }[e.kind] || e.kind;
    d.innerHTML = "<b>" + head + (e.what ? " · " + e.what : "") + "</b>" +
                  "<span>" + (e.why || "") + "</span>" +
                  '<span style="display:block">' + ago(e.t) + " · " +
                  (e.author || "") + ": " +
                  String(e.text || "").slice(0, 90) + "</span>";
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
  // Arming while STOPped would be a lie — clear the stop as part of arming, so
  // the button always means what it says.
  await patch({ armed: !s.armed, stopped: s.armed ? s.stopped : false });
};

$("stop").onclick = async () => {
  const s = await getSettings();
  await patch({ stopped: !s.stopped, armed: false });
};

$("save").onclick = () => patch({
  channel_ids: textToList($("channels").value),
  follow_admins: textToList($("admins").value),
  allowed_symbols: textToList($("symbols").value).map(x => x.toUpperCase()),
  trim_action: $("trim").value,
  close_at_trim_pct: parseFloat($("trimpct").value) || 50,
  bridge_url: $("bridge").value.trim() || DEFAULTS.bridge_url,
  guards: Object.assign({}, DEFAULTS.guards, {
    max_qty: parseInt($("maxqty").value, 10) || 1,
    max_trades_per_day: parseInt($("maxday").value, 10) || 6
  })
});

$("export").onclick = async () => {
  const { captured } = await chrome.storage.local.get("captured");
  const rows = (captured || []).map(c =>
    new Date(c.t).toLocaleTimeString() + "  " + (c.author || "?") + ": " + c.text);
  const blob = new Blob([rows.join("\n") || "nothing captured yet"],
                        { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  await chrome.downloads.download({ url, filename: "signal-room-chat.txt",
                                    saveAs: true })
    .catch(() => {
      // downloads permission missing or blocked — open it in a tab instead so
      // you can still copy it out.
      chrome.tabs.create({ url });
    });
};

render();
setInterval(render, 2000);
refreshMode();
setInterval(refreshMode, 4000);
