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
  // THE futures switch. Off = his NQ/ES calls are read and logged, nothing
  // fires. Deliberately off out of the box.
  futures_enabled: false,
  // The old filter knobs (trim modes, symbol lists, add limits, daily caps)
  // are deleted from the code — "no filters wanted. id like to follow
  // everything to the tee as they do." What's left is safety, not filtering.
  guards: { cooldown_seconds: 5, dedupe_seconds: 120,
            regular_hours_only: true, open_time: "09:30",
            close_time: "15:45", max_message_age_seconds: 20 }
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
    sub.textContent = "on your PC: double-click START HERE, then look again";
    return;
  }
  // The real account's buying power, whenever the bridge can read it. Shown
  // in BOTH modes — knowing what the margin account could do is half of how
  // you judge whether the test day's "would need $X" figure is realistic.
  const bp = modeStatus.buying_power;
  const bpBit = (bp === null || bp === undefined)
    ? "" : " · $" + Math.round(bp).toLocaleString() + " real buying power";
  if (modeStatus.live) {
    btn.className = "grow live big";
    btn.innerHTML = "REAL MONEY<small>click to go back to test mode</small>";
    sub.textContent = (modeStatus.connected
      ? ("orders go to your Webull account " + (modeStatus.account || "?"))
      : ("REAL MONEY but not connected: " + (modeStatus.error || "unknown")))
      + bpBit;
  } else {
    btn.className = "grow dry big";
    btn.innerHTML = "TEST MODE<small>click to switch to real money</small>";
    sub.textContent = (modeStatus.has_keys
      ? "nothing is really bought — trades are written down on your PC"
      : "no Webull keys saved yet — scroll down to Settings and paste them in") + bpBit;
  }
}

function paintKeys() {
  const el = $("keystate");
  if (!el) return;
  if (!modeStatus) {
    el.textContent = "Can't check your keys — the bridge isn't running.";
  } else if (modeStatus.has_keys) {
    el.textContent = "Keys are in (…" + (modeStatus.key_tail || "????") + ")" +
      (modeStatus.connected ? " and connected to Webull."
                            : ", but not connected" +
                              (modeStatus.error ? ": " + modeStatus.error : "."));
  } else {
    el.textContent = "No keys saved yet. Get them from the Webull developer " +
      "page, paste both boxes, hit save. They stay on your PC, never in Chrome.";
  }
}

async function refreshMode() {
  try {
    modeStatus = await askBridge("/mode");
  } catch (e) {
    modeStatus = null;      // bridge isn't running, which is a normal state
  }
  paintMode();
  paintKeys();
}

/* The keys go to the bridge and nowhere else. Nothing is written to
 * chrome.storage — the browser forgets them the moment they're sent, which is
 * the whole reason the bridge exists in the first place. */
$("savekeys").onclick = async () => {
  const key = $("wbkey").value.trim();
  const secret = $("wbsecret").value.trim();
  const el = $("keystate");
  if (!key || !secret) {
    el.textContent = "Both boxes need something in them — the key and the secret.";
    return;
  }
  $("savekeys").textContent = "Saving and checking…";
  try {
    const r = await askBridge("/keys", { app_key: key, app_secret: secret });
    modeStatus = r;
    el.textContent = r.message || "saved";
    if (r.ok) { $("wbkey").value = ""; $("wbsecret").value = ""; }
    paintMode();
  } catch (e) {
    el.textContent = "Couldn't reach the bridge on your PC — double-click " +
      "START HERE first, then try again.";
  }
  $("savekeys").textContent = "Save keys to this PC";
};

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
      "no Webull keys saved yet — paste them into Settings below, then come back";
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

function renderTable(rows, el) {
  if (!rows || !rows.length) {
    el.innerHTML = '<div class="note">No trades on this day.</div>';
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
    const ins = (r.entries || [])
      .map(e => e.qty + " @ " + Number(e.price).toFixed(2)).join(" + ");
    const outs = (r.exits || [])
      .map(e => e.qty + " @ " + Number(e.price).toFixed(2)).join(", ");
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

async function loadDays() {
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
  const { guardState: gs, log, wallet, day_table } =
    await chrome.storage.local.get(["guardState", "log", "wallet",
                                    "day_table"]);

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
  if (!held.length) {
    $("holding").innerHTML = "<b>Flat.</b> Not in anything.";
  } else {
    const rows = held.map(k => {
      const p = pos[k] || {};
      const who = keyWho(k) !== "?" ? " · " + keyWho(k) + "'s call" : "";
      const contract = [keySym(k),
                        p.expiry || "",
                        (p.strike != null ? p.strike : "") +
                        (p.side === "PUTS" ? "P" : p.side === "CALLS" ? "C" : "")]
                       .filter(Boolean).join(" ");
      const n = parseInt(p.qty || 1, 10) || 1;
      if (p.pending) {
        // The order is out and nobody has taken it. You own nothing here yet,
        // and on the fast ones you never will — that's the trade-off of sitting
        // on the bid, and it should look different on screen.
        return '<span class="in wait">BID IN</span> <b>' + contract + "</b>" +
               who + (p.ts ? " — since " + clock(p.ts) : "") +
               " · nobody has sold to you yet";
      }
      return '<span class="in">IN</span> <b>' + contract + "</b>" +
             " <b>x" + n + "</b>" + who +
             (p.ts ? " — since " + clock(p.ts) : "") +
             (p.fill ? " · paid " + Number(p.fill).toFixed(2) : "") +
             (p.stop ? " · stop " + Number(p.stop).toFixed(2) : "");
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

  $("channels").value = listToText(s.channel_ids);
  $("admins").value = listToText(s.follow_admins);
  $("futures").value = s.futures_enabled ? "1" : "0";
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

$("save").onclick = async () => {
  const fut = $("futures").value === "1";
  // The switch lives in TWO places on purpose: the extension (gates whether
  // a futures call fires at all) and the bridge's settings.json (second lock
  // on real orders). Saving sets both so they can't drift apart — and both
  // are told the allowed list is empty for good: "no filters wanted."
  try { await askBridge("/config", { futures_enabled: fut,
                                     allowed_symbols: [] }); }
  catch (e) { /* bridge down — the extension-side gate still holds */ }
  return patch({
    futures_enabled: fut,
    channel_ids: textToList($("channels").value),
    follow_admins: textToList($("admins").value),
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
    const ins = (r.entries || []).map(e => e.qty + "@" + Number(e.price).toFixed(2)).join(" +");
    const outs = (r.exits || []).map(e => e.qty + "@" + Number(e.price).toFixed(2)).join(", ");
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

$("export").onclick = async () => {
  const { captured } = await chrome.storage.local.get("captured");
  // Which room each line came from. Three rooms export into one file, and the
  // tag is what keeps their three dialects apart when the parser gets tuned.
  const ROOMS = { "829754942817828884": "main",
                  "987515353670221834": "aristotle",
                  "1144369893760831489": "midas" };
  // Whop rooms tag themselves "whop:/their/path" — shown as-is, so two
  // different Whop rooms stay two different lexicons in the file.
  // Sorted by when the message was POSTED, not when it was scraped —
  // scrolling up paints newest-first, and a file in paint order would read
  // like a week played backwards.
  const rows = (captured || []).slice().sort((a, b) => a.t - b.t).map(c =>
    new Date(c.t).toLocaleString() +
    "  [" + (ROOMS[c.channel] || c.channel || "?") + "]" +
    "  " + (c.author || "?") + ": " + c.text);
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
