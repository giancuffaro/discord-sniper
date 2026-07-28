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
  armed: false, stopped: false, capture: true,
  bridge_url: "http://127.0.0.1:8787/order",
  channel_ids: [], follow_admins: [], allowed_symbols: [],
  trim_action: "ignore", close_at_trim_pct: 50,
  // max_trades_per_day 0 means no daily limit — it follows every call they
  // make. average_in true means when they add to a trade you're already in and
  // post a new average, you buy another one, up to max_adds_per_position times.
  guards: { max_qty: 1, max_trades_per_day: 0, cooldown_seconds: 5,
            dedupe_seconds: 120, regular_hours_only: true,
            open_time: "09:30", close_time: "15:45",
            average_in: true, max_adds_per_position: 2,
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

  btn.style.width = "100%";

  if (armLive) {
    btn.className = "grow confirm big";
    btn.innerHTML = "CLICK AGAIN FOR REAL MONEY" +
                    "<small>this one really buys. options have no practice " +
                    "mode.</small>";
    sub.textContent = "or wait a few seconds and it forgets you asked";
    return;
  }
  if (!modeStatus) {
    btn.className = "grow dry big";
    btn.innerHTML = "CAN'T REACH YOUR PC<small>the bridge isn't running</small>";
    sub.textContent = "on your PC: open START HERE and press 5";
    return;
  }
  if (modeStatus.live) {
    btn.className = "grow live big";
    btn.innerHTML = "REAL MONEY<small>click to go back to test mode</small>";
    sub.textContent = modeStatus.connected
      ? ("orders go to your Webull account " + (modeStatus.account || "?"))
      : ("REAL MONEY but not connected: " + (modeStatus.error || "unknown"));
  } else {
    btn.className = "grow dry big";
    btn.innerHTML = "TEST MODE<small>click to switch to real money</small>";
    sub.textContent = modeStatus.has_keys
      ? "nothing is really bought — trades are written down on your PC"
      : "no Webull keys saved yet — START HERE, press 2";
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
      "there are no Webull keys saved yet — START HERE, press 2, then come back";
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
  const { guardState: gs, log, wallet } =
    await chrome.storage.local.get(["guardState", "log", "wallet"]);

  // The big word is what it IS right now. The small line is what a click does.
  // Getting those two the wrong way round is how somebody turns a bot on while
  // trying to turn it off.
  const arm = $("arm");
  if (s.armed) {
    arm.innerHTML = "ON<small>click to turn it off</small>";
    arm.className = "grow armed big";
  } else {
    arm.innerHTML = "OFF<small>click to turn it on</small>";
    arm.className = "grow safe big";
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
  const posAll = (gs && gs.positions) || {};
  const owned = held.filter(sym => !posAll[sym].pending);
  const waiting = held.filter(sym => posAll[sym].pending);
  const where = [];
  if (owned.length) where.push("holding " + owned.join(", "));
  if (waiting.length) where.push("bid in on " + waiting.join(", "));
  bits.push(where.length ? where.join(" · ") : "flat");
  $("state").textContent = bits.join(" · ");

  // What you're in right now, spelled out as a contract rather than a ticker.
  // The tracker already knows this — it has to, or it couldn't turn "all out of
  // AMD" into an order. This just puts it on screen.
  const pos = (gs && gs.positions) || {};
  if (!held.length) {
    $("holding").innerHTML = "<b>Flat.</b> Not in anything.";
  } else {
    const rows = held.map(sym => {
      const p = pos[sym] || {};
      const contract = [sym,
                        p.expiry || "",
                        (p.strike != null ? p.strike : "") +
                        (p.side === "PUTS" ? "P" : p.side === "CALLS" ? "C" : "")]
                       .filter(Boolean).join(" ");
      // How many you're holding matters now that it can average in. One is the
      // normal case and saying "x1" every time is noise, so it only shows up
      // once there's more than one.
      const n = parseInt(p.qty || 1, 10) || 1;
      if (p.pending) {
        // The order is out and nobody has taken it. You own nothing here yet,
        // and on the fast ones you never will — that's the trade-off of sitting
        // on the bid, and it should look different on screen.
        return '<span class="in wait">BID IN</span> <b>' + contract + "</b>" +
               (p.ts ? " — since " + clock(p.ts) : "") +
               " · nobody has sold to you yet";
      }
      return '<span class="in">IN</span> <b>' + contract + "</b>" +
             (n > 1 ? " <b>x" + n + "</b>" : "") +
             (p.ts ? " — since " + clock(p.ts) : "") +
             (p.fill ? " · paid " + Number(p.fill).toFixed(2) : "") +
             (p.stop ? " · stop " + Number(p.stop).toFixed(2) : "") +
             (n > 1 ? " (averaged in " + (p.adds || n - 1) + "x)" : "");
    });
    $("holding").innerHTML = rows.join("<br>");
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
    const day = wallet.equity - wallet.start;
    const rows = [];
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

  $("channels").value = listToText(s.channel_ids);
  $("admins").value = listToText(s.follow_admins);
  $("symbols").value = listToText(s.allowed_symbols);
  $("trim").value = s.trim_action;
  $("trimpct").value = s.close_at_trim_pct;
  $("maxqty").value = s.guards.max_qty;
  $("maxday").value = s.guards.max_trades_per_day;
  $("avgin").value = s.guards.average_in ? "1" : "0";
  $("maxadds").value = s.guards.max_adds_per_position;
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

$("save").onclick = () => patch({
  channel_ids: textToList($("channels").value),
  follow_admins: textToList($("admins").value),
  allowed_symbols: textToList($("symbols").value).map(x => x.toUpperCase()),
  trim_action: $("trim").value,
  close_at_trim_pct: parseFloat($("trimpct").value) || 50,
  bridge_url: $("bridge").value.trim() || DEFAULTS.bridge_url,
  guards: Object.assign({}, DEFAULTS.guards, {
    max_qty: parseInt($("maxqty").value, 10) || 1,
    // No "|| 0" fallback needed and none wanted: 0 is a real setting here, it
    // means no daily limit, and "|| 6" would have quietly overruled it.
    max_trades_per_day: Math.max(0, parseInt($("maxday").value, 10) || 0),
    average_in: $("avgin").value === "1",
    max_adds_per_position: Math.max(0, parseInt($("maxadds").value, 10) || 0)
  })
});

/* You can't select text out of this popup — it closes the moment you click
 * anywhere else, which is why a whole day's log once had to be sent as a
 * search URL. This puts it on the clipboard as plain text, oldest first so it
 * reads like a morning rather than backwards. */
$("copylog").onclick = async () => {
  const { log, wallet } = await chrome.storage.local.get(["log", "wallet"]);
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
  if (wallet) {
    lines.unshift("account $" + wallet.equity.toFixed(0) + " (started $" +
                  wallet.start.toFixed(0) + ", " + wallet.wins + " up / " +
                  wallet.losses + " down, banked $" +
                  wallet.realised.toFixed(0) + ")", "");
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
