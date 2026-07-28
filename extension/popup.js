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
