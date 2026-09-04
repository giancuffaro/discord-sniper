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
  // No armed/stopped any more (8/17) — a room tab open is the only switch.
  capture: true,
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
  // Topstep's green box (his ask, 8/17) — and it tells the TRUTH: the
  // bridge logs in with the saved key, so "connected" means TopstepX
  // said yes, "saved" alone means it hasn't answered yet.
  const _ts = ((modeStatus || {}).futures_brokers || {}).topstep || {};
  _okbox("topstepKeySaved", !!_ts.keys_in,
         _ts.verified === true ? "Topstep connected (" + (_ts.username || "") + ")"
       : _ts.verified === false ? "Topstep key saved — but REFUSED, recheck it"
       : "Topstep key saved");
  const el = $("keystate");
  if (!el) return;
  el.textContent = (!modeStatus || has) ? ""
    : "No key yet — tap the pencil on Webull to add it.";
}

/* More Webull accounts (8/18): one row per account — green when the bridge
 * actually logged in to it, honest words when it didn't. The ✖ removes it
 * (its saved keys go with it). */
function _monthNow() {
  const d = new Date();
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");
}
function _monthEndWords() {
  const d = new Date();
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0);
  return last.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
const _exOpen = {};   // name -> fetched account choices, survives repaints
function paintExtras() {
  const list = $("extraList");
  if (!list) return;
  const xs = (((modeStatus || {}).futures_brokers || {}).webull_extras) || [];
  list.innerHTML = "";
  const resend = (mut) => xs.map(o => {
    const e = { name: o.name, enabled: o.enabled !== false,
                paid_month: o.paid_month || "" };
    return (mut && mut(e)) || e;
  });
  xs.forEach(x => {
    const row = document.createElement("div");
    row.className = "row";
    row.style.marginTop = "4px";
    const ok = !!x.connected;
    // Subscription words (his model, 8/20): flipping ON pays the account
    // through the END of this month; the new month expires it by itself.
    const active = !!x.active;
    const expired = (x.enabled !== false) && x.paid_month &&
                    x.paid_month !== (x.month_now || _monthNow());
    const bp = (x.buying_power === null || x.buying_power === undefined)
      ? "" : " · $" + Math.round(x.buying_power).toLocaleString() + " BP";
    const word = (!x.keys_in ? "no keys saved"
      : !ok ? ("saved — " + (x.why || "couldn't log in (check trades.log)"))
      : active ? "connected · active through " + _monthEndWords()
      : expired ? "connected · subscription EXPIRED — flip ON to renew"
      : "connected · OFF — not taking entries") + (ok ? bp : "");
    const span = document.createElement("span");
    span.className = "grow";
    span.style.cssText = "font-size:12px;white-space:normal;color:" +
      (active ? "#4ade80" : expired ? "#f87171" : "#fbbf24");
    span.textContent = (active ? "✓ " : "") + (x.name || "?") + " — " + word;
    row.appendChild(span);
    // Several accounts on one login: one BUTTON per candidate, labeled with
    // its buying power — click the one to trade from and it's pinned (8/21).
    if (!ok && Array.isArray(x.choices) && x.choices.length) {
      const wrap = document.createElement("div");
      wrap.style.cssText = "width:100%;margin-top:4px;display:flex;gap:6px;flex-wrap:wrap";
      x.choices.forEach(ch => {
        const b = document.createElement("button");
        b.textContent = ch.bp != null
          ? "use $" + Math.round(ch.bp).toLocaleString() + " acct"
          : (ch.err ? "…" + ch.id.slice(-6) + " (error)" : "…" + ch.id.slice(-6));
        b.title = ch.id + (ch.err ? " — " + ch.err : "");
        b.disabled = !!ch.err;
        b.onclick = async () => {
          b.textContent = "connecting…";
          const out = resend(e => {
            if (e.name === x.name) {
              e.account_id = ch.id;
              e.enabled = true;               // picking it = arming it
              e.paid_month = _monthNow();     // active for this month
            }
          });
          try {
            modeStatus = await askBridge("/config",
                                         { webull_extra_accounts: out });
            paintExtras();
          } catch (e2) {
            $("exState").textContent = "Couldn't reach the bridge.";
          }
        };
        wrap.appendChild(b);
      });
      row.appendChild(wrap);
      row.style.flexWrap = "wrap";
    }
    // ✏️ — switch WHICH of the login's accounts trades, any time (8/21).
    const ed = document.createElement("button");
    ed.className = "edit";
    ed.textContent = "✏️";
    ed.title = "Switch which of this login's accounts trades";
    // The fetched list lives in _exOpen so the popup's 4-second repaint
    // can't wipe it off the screen mid-read (8/21). ✏️ again closes it.
    ed.textContent = _exOpen[x.name] ? "▲" : "✏️";
    ed.onclick = async () => {
      if (_exOpen[x.name]) { delete _exOpen[x.name]; paintExtras(); return; }
      ed.textContent = "…";
      try {
        const j = await askBridge("/exchoices?name=" + encodeURIComponent(x.name));
        if (!(j && j.ok && j.choices && j.choices.length)) {
          ed.textContent = "✏️";
          $("exState").textContent = (j && j.why) || "couldn't list the accounts";
          return;
        }
        _exOpen[x.name] = j.choices;
        paintExtras();
      } catch (e) {
        ed.textContent = "✏️";
        $("exState").textContent = "Couldn't reach the bridge.";
      }
    };
    row.appendChild(ed);
    if (_exOpen[x.name]) {
      const wrap = document.createElement("div");
      wrap.className = "exChoices";
      wrap.style.cssText = "width:100%;margin-top:4px";
      _exOpen[x.name].forEach(ch => {
        const b = document.createElement("button");
        b.style.cssText = "display:block;width:100%;text-align:left;" +
          "margin-top:4px;font-size:12px;padding:6px 8px;white-space:normal";
        b.textContent = (ch.current ? "✓ USING — " : "") +
          (ch.bp != null ? "$" + Math.round(ch.bp).toLocaleString() + " BP"
                         : "BP unknown") +
          " · " + (ch.kind || "?") + " · " + ch.id;
        b.disabled = !!ch.current;
        b.onclick = async () => {
          b.textContent = "switching…";
          const out = resend(e => { if (e.name === x.name) e.account_id = ch.id; });
          try {
            modeStatus = await askBridge("/config", { webull_extra_accounts: out });
            delete _exOpen[x.name];
            paintExtras();
          } catch (e2) { $("exState").textContent = "Couldn't reach the bridge."; }
        };
        wrap.appendChild(b);
      });
      row.appendChild(wrap);
      row.style.flexWrap = "wrap";
    }
    const daysLeft = (() => {
      const d = new Date();
      return new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate() - d.getDate() + 1;
    })();
    const tgl = document.createElement("button");
    tgl.className = "tgl " + (active ? "live" : "safe");
    tgl.textContent = active ? "on" : "off";
    tgl.title = active
      ? (daysLeft + " day" + (daysLeft === 1 ? "" : "s") + " left — active through " +
         _monthEndWords() + ". Click to turn OFF (open positions still managed).")
      : ("OFF — click to activate through " + _monthEndWords() + " (" + daysLeft +
         " day" + (daysLeft === 1 ? "" : "s") + ").");
    tgl.onclick = async () => {
      const goingOn = !active;
      const out = resend(e => {
        if (e.name === x.name) {
          e.enabled = goingOn;
          if (goingOn) e.paid_month = _monthNow();   // renew for THIS month
        }
      });
      try {
        modeStatus = await askBridge("/config",
                                     { webull_extra_accounts: out });
        paintExtras();
      } catch (e2) {
        $("exState").textContent = "Couldn't reach the bridge.";
      }
    };
    row.appendChild(tgl);
    const del = document.createElement("button");
    del.textContent = "✖";
    del.title = "Remove this account";
    del.style.maxWidth = "34px";
    del.onclick = async () => {
      if (!confirm("Remove " + (x.name || "this account") +
                   "? It stops firing immediately.")) return;
      const keep = resend().filter(o => o.name !== x.name);
      try {
        modeStatus = await askBridge("/config",
                                     { webull_extra_accounts: keep });
        paintExtras();
      } catch (e) {
        $("exState").textContent = "Couldn't reach the bridge.";
      }
    };
    row.appendChild(del);
    list.appendChild(row);
  });
}

if ($("exAdd")) $("exAdd").onclick = async () => {
  const name = ($("exName").value || "").trim();
  const key = ($("exKey").value || "").trim();
  const sec = ($("exSecret").value || "").trim();
  const st = $("exState");
  if (!name) { st.textContent = "Give the account a name first."; return; }
  if (!key || !sec) {
    st.textContent = "Both the App Key and App Secret are needed.";
    return;
  }
  // Send the whole list back: existing rows by name only (the bridge keeps
  // their stored secrets), plus the new one with its keys.
  const xs = (((modeStatus || {}).futures_brokers || {}).webull_extras) || [];
  const out = xs.filter(o => o.name !== name)
    .map(o => ({ name: o.name, enabled: o.enabled !== false,
                 paid_month: o.paid_month || "" }));
  // a freshly added account starts ACTIVE for the current month
  out.push({ name: name, app_key: key, app_secret: sec, enabled: true,
             paid_month: _monthNow(),
             account_id: (($("exAcctId") || {}).value || "").trim() });
  $("exAdd").textContent = "Saving and connecting…";
  try {
    modeStatus = await askBridge("/config", { webull_extra_accounts: out });
    $("exName").value = ""; $("exKey").value = ""; $("exSecret").value = "";
    if ($("exAcctId")) $("exAcctId").value = "";
    clearDrafts(["exName", "exKey", "exSecret", "exAcctId"]);
    st.textContent = "";
    paintExtras();
  } catch (e) {
    st.textContent = "Couldn't reach the bridge on your PC — double-click " +
      "START HERE first, then try again.";
  }
  $("exAdd").textContent = "Add this account";
};
function _okbox(id, ok, label) {
  const b = $(id);
  if (!b) return;
  if (ok) { b.style.display = "flex"; b.innerHTML = "<b>\u2713</b> " + label; }
  else b.style.display = "none";
}

let brokerPos = [];        // real Webull account positions, so the popup mirrors it
// The BRIDGE's book, keyed "caller|TICKER". This is the only place the caller
// survives: the extension deletes its own guardState entry the moment a bid
// fills, so a filled position has no caller on this side at all — which is
// why the credit line stayed blank no matter what was fixed around it.
let bookPos = {};
async function refreshMode() {
  try {
    modeStatus = await askBridge("/mode");
  } catch (e) {
    modeStatus = null;      // bridge isn't running, which is a normal state
  }
  _bridgeLastCheck = Date.now();
  try {
    const pr = await askBridge("/positions");
    brokerPos = (pr && pr.positions) || [];
  } catch (e) { brokerPos = []; }
  try {
    const fr = await askBridge("/fills?since=0");
    bookPos = (fr && fr.positions) || {};
  } catch (e) { /* keep the last book we saw */ }
  paintMode();
  paintKeys();
  paintProps();
  paintSim();
  paintStrat();
  paintFuturesBrokers();
  paintExtras();
  paintPaper();
  paintAi(modeStatus);
  paintStatus();
  paintBridgeDown();
  paintBridgeLive();
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

/* LIVE bridge status dot (8/17, his ask): "something on the popup that shows
 * if the bridge is connected, live." refreshMode() re-fetches modeStatus
 * every 4s while this popup is open — this paints it, plus how long ago the
 * last check was, so it visibly ticks instead of sitting static. Green =
 * connected, red = not reachable, grey = first check still running. */
let _bridgeLastCheck = 0;
function paintBridgeLive() {
  const dot = $("bridgeDot"), txt = $("bridgeLiveText");
  if (!dot || !txt) return;
  const ok = !!modeStatus;
  dot.style.background = _bridgeLastCheck ? (ok ? "#4ade80" : "#dc2626") : "#52525b";
  // Just the verdict, no clock (his ask, 8/17: "i dont need to know how
  // many seconds passed"). refreshMode refreshes this every 4s regardless.
  // Announcer rides on the same line (9/2): it was silently stopped for an
  // hour and a real fill never posted. Red text when its heartbeat is stale.
  // Deliberately off (STOP ANNOUNCER / G's call 9/2) is grey, not red —
  // red is only for "should be running and isn't".
  const annOff = ok && modeStatus.announcer_stopped;
  const annOk = ok && (modeStatus.announcer_alive || annOff);
  const annTxt = !ok ? "" : annOff ? " · announcer off (paused)"
    : modeStatus.announcer_alive ? " · announcer on"
    : " · ✕ ANNOUNCER OFF — run ANNOUNCER.bat";
  txt.textContent = !_bridgeLastCheck ? "checking bridge…"
    : ok ? "✓ Bridge connected" + annTxt : "✕ Bridge NOT reachable — run 🎯 START HERE";
  txt.style.color = _bridgeLastCheck && (!ok || !annOk) ? "#fca5a5" : "#9aa3b5";
}

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
let _fbLocal = { webull: true, ninja: false, tradovate: false, topstep: false };  // Webull futures ON always (8/13)
let _fbSeeded = false;
try {
  chrome.storage.local.get("fb_toggles", r => {
    if (r && r.fb_toggles) {
      _fbLocal = Object.assign(_fbLocal, r.fb_toggles);
      _fbLocal.webull = true;   // Webull futures stays ON always (8/13)
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
    _fbLocal = { webull: true, ninja: !!nt.enabled,   // Webull ON always (8/13)
                 tradovate: !!tv.enabled, topstep: !!ts.enabled };
    _fbSeeded = true;
    try { chrome.storage.local.set({ fb_toggles: _fbLocal }); } catch (e) {}
  }
  _fbPaintToggles();
  // Field values come from the bridge — but ONLY into EMPTY boxes. The old
  // rule ("don't stomp a field being typed in") had a race his email fell
  // into (8/17): type the new username, click Save — the click blurs the
  // field, the 4-second repaint puts the OLD value back, and Save reads
  // that. "the numbers and @gmail.com get deleted." Never overwrite a box
  // that has anything in it; a wrong value is cleared by selecting it and
  // deleting, same as any form.
  if ($("ninjaAccount") && !$("ninjaAccount").value)
    $("ninjaAccount").value = nt.account || "";
  if ($("ninjaDir") && !$("ninjaDir").value)
    $("ninjaDir").value = nt.incoming_dir || "";
  if ($("ninjaAtm") && !$("ninjaAtm").value)
    $("ninjaAtm").value = nt.atm_template || "";
  if ($("tvUser") && !$("tvUser").value)
    $("tvUser").value = tv.username || "";
  if ($("tvDemo")) $("tvDemo").checked = !!tv.demo;
  if ($("tvPass") && tv.has_password && !$("tvPass").value)
    $("tvPass").placeholder = "•••••• (saved — leave blank to keep)";
  if ($("tsUser") && !$("tsUser").value)
    $("tsUser").value = ts.username || "";
  if ($("tsUrl") && !$("tsUrl").value && ts.base_url)
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
                   incoming_dir: _fbVal("ninjaDir"),
                   atm_template: _fbVal("ninjaAtm") },
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
    clearDrafts(["tsUser", "tsKey", "tsUrl", "tvUser", "tvPass",
                 "ninjaAccount", "ninjaDir", "ninjaAtm"]);
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
  // Buying-power display removed from this line (his ask, 8/15) - he doesn't
  // want it always visible. buying_power/futures_buying_power still ride in
  // modeStatus for anything else that needs them, just not painted here.
  bar.textContent = [
    "Bridge " + _dot(bridge),
    "Webull " + ((st && (st.connected || paperKeys)) ? "✅" : (st && st.has_keys ? "⛔" : "—")),
    "Futures " + ((st && st.futures_account) ? "✅" : "—"),
    "AI " + (ai ? "✅" : "off"),
    "Voice " + (voiceN ? (voiceN + " 🎙") : (dgKey ? "✅" : "off"))
  ].join("  ·  ");
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
    : "";
  fix.style.color = steps.length ? "#fbbf24" : "#34d399";
}

/* SWINGS PAUSED (9/4). A gate that silently refuses trades has to be visible,
 * so the button reads its truth from the bridge's /mode every paint — never
 * from a local guess that could drift out of step with what the bridge is
 * actually doing. */
let swingPause = false;
function paintSwingPause() {
  const btn = $("swingpause");
  if (!btn) return;
  swingPause = !!(modeStatus && modeStatus.swings_paused);
  btn.textContent = swingPause ? "PAUSED" : "off";
  btn.className = "tgl " + (swingPause ? "live" : "safe");
}
if ($("swingpause")) {
  $("swingpause").onclick = async () => {
    const want = !swingPause;
    try {
      modeStatus = await askBridge("/config", { swings_paused: want });
    } catch (e) {
      if ($("swingpausestate")) {
        $("swingpausestate").textContent =
          "couldn't reach the bridge — START HERE first";
      }
      return;
    }
    paintSwingPause();
  };
}

let paperOn = false;
function paintPaper() {
  paintSwingPause();
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

/* The "Paper-only tactics" panel (bid-under, auto-secure, auto-trim ladder)
 * is DELETED from the UI (his call, 8/17: "i dont think we need this") —
 * they were knobs on the old in-house paper simulator. paintSim stays as a
 * guarded no-op so nothing else needs touching; the bridge-side simulation
 * config is untouched and simply never set. */
function paintSim() {}

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

// (the sim-tactics handlers — honest-fills, ladder, bid-under, auto-secure,
// save — left with the panel, 8/17)

/* ---- one-click bracket strategy (LIVE-safe) -------------------------------
 * 1 contract on every entry, take profit at +15%, hard stop at -15%. It lives
 * in TWO places on purpose: the bridge (so orders actually get the +/-15%
 * bracket and the single-contract clamp) and the extension's settings (so the
 * worker sizes every entry to 1 before the order even leaves the browser).
 * Painted from the bridge's reported state so a reload always tells the truth.
 */
let bracketOn = false;
// "ratchet" (default, 8/15): the stop walks up in +stop_loss_pct steps once
// gain reaches take_profit_pct, never sells outright. "hardclose": the old
// behaviour, sells everything the instant gain hits take_profit_pct.
let bracketExit = "ratchet";
function paintStrat() {
  const s = (modeStatus || {}).strategy || {};
  bracketOn = !!s.enabled;
  bracketExit = s.take_profit_hard_close ? "hardclose" : "ratchet";
  const btn = $("bracketstrat");
  if (btn) {
    btn.textContent = bracketOn ? "ON" : "off";
    btn.className = "tgl " + (bracketOn ? "live" : "safe");
  }
  const sel = $("bracketexit");
  if (sel) sel.value = bracketExit;
  const exitNote = $("bracketexitstate");
  if (exitNote) {
    exitNote.innerHTML = bracketExit === "hardclose"
      ? "<b>Close whole position</b>: sells everything the instant it's up " +
        "+20% and you're flat. The old behaviour, from before 8/15."
      : "<b>Ratchet</b>: the stop stops sitting at -10% and starts walking UP " +
        "instead — locked at +10% first, then another +10% for every further " +
        "+10% of gain (up 20 locks +10, up 30 locks +20, up 40 locks +30…), " +
        "no ceiling. Never sells outright, never comes back red once it's " +
        "locked.";
  }
}
async function _saveBracket() {
  const btn = $("bracketstrat");
  if (btn) {
    btn.textContent = bracketOn ? "ON" : "off";
    btn.className = "tgl " + (bracketOn ? "live" : "safe");
  }
  const hardClose = bracketExit === "hardclose";
  const strat = { enabled: bracketOn, take_profit_pct: 20,
                  stop_loss_pct: 10, one_contract: true,
                  ratchet_enabled: !hardClose,
                  take_profit_hard_close: hardClose };
  // Extension settings first — this is what the worker reads to force qty=1.
  try {
    const { settings } = await chrome.storage.local.get("settings");
    const s = settings || {};
    s.strategy = strat;
    await chrome.storage.local.set({ settings: s });
  } catch (e) {}
  // Then the bridge, so live/paper orders get the actual bracket.
  try {
    modeStatus = await askBridge("/config", { strategy: strat });
    if ($("bracketstate"))
      $("bracketstate").textContent = bracketOn
        ? (hardClose
           ? "ON — every entry is 1 contract, +20% take-profit, −10% stop. Live and paper."
           : "ON — every entry is 1 contract, −10% stop to start, ratcheting up past +20%. Live and paper.")
        : "Off — sizing and exits go back to the room's calls.";
  } catch (e) {
    if ($("bracketstate"))
      $("bracketstate").textContent = "Saved in the browser, but couldn't reach the bridge — START HERE first.";
  }
  paintStrat();
}
if ($("bracketstrat")) $("bracketstrat").onclick = async () => {
  bracketOn = !bracketOn;
  await _saveBracket();
};
if ($("bracketexit")) $("bracketexit").onchange = async () => {
  bracketExit = $("bracketexit").value;
  await _saveBracket();
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
      clearDrafts(["wbkey", "wbsecret"]);
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
      clearDrafts(["wbpkey", "wbpsecret"]);
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

/* ---- AI reader — ALWAYS ON when keyed (his call, 8/17) -------------------
 * "make it always on, i need every trade to go through AI reading." No off
 * button any more — the only states are "on" (a working key is saved) and
 * "needs a key". The bridge ignores the old enabled flag to match. */
function paintAi(st) {
  const on = !!(st && st.ai_enabled);
  const el = $("aiState");
  if (el) {
    el.textContent = on ? "always ON" : "needs a key";
    el.style.color = on ? "#34d399" : "#fbbf24";
  }
}
if ($("saveaikey")) $("saveaikey").onclick = async () => {
  const key = $("aiKey").value.trim();
  const el = $("aikeystate");
  if (!key) { el.textContent = "Paste your Claude API key first (starts sk-ant-)."; return; }
  $("saveaikey").textContent = "Saving…";
  try {
    const r = await askBridge("/config", { ai_api_key: key, ai_enabled: true });
    modeStatus = r;
    el.textContent = r.ai_enabled ? "AI reading is ON — every call goes through it." :
                     (r.message || "saved");
    if (r.ai_enabled) { $("aiKey").value = ""; clearDrafts(["aiKey"]); }
    paintAi(r);
  } catch (e) {
    el.textContent = "Couldn't reach the bridge — double-click START HERE first.";
  }
  $("saveaikey").textContent = "Save AI key";
};
if ($("aioff")) $("aioff").style.display = "none";   // no off switch — always on

/* Round-number pullback — ONE toggle for every channel (his ask, 8/17),
 * browser-side like the double-check below. background.js reads
 * rn_pullback_all and stamps entry_mode on every entry it fires. */
if ($("rnAll")) $("rnAll").onclick = async () => {
  const s = await getSettings();
  await patch({ rn_pullback_all: s.rn_pullback_all === false });
};

/* Voice firing, split in two (8/29): EXITS (the proven, protective edge)
 * and ENTRIES (the stitcher). Both OFF by default, both real-money red. */
if ($("voiceExits")) $("voiceExits").onclick = async () => {
  const s = await getSettings();
  await patch({ voice_exits: !(s.voice_exits === true) });
};
if ($("voiceEntries")) $("voiceEntries").onclick = async () => {
  const s = await getSettings();
  await patch({ voice_entries: !(s.voice_entries === true) });
};

/* Double-check entries — a browser-side toggle; the key stays on the bridge. */
async function paintVerify() {
  let on = true;   // ON by default now (8/13); still toggleable off
  try { on = ((await chrome.storage.local.get("ai_verify")).ai_verify !== false); } catch (e) {}
  const b = $("aiVerifyBtn");
  if (b) { b.textContent = on ? "on" : "off"; b.className = "tgl " + (on ? "live" : "safe"); }
}
if ($("aiVerifyBtn")) $("aiVerifyBtn").onclick = async () => {
  let on = true;   // ON by default now (8/13); still toggleable off
  try { on = ((await chrome.storage.local.get("ai_verify")).ai_verify !== false); } catch (e) {}
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
        el.textContent = "Deepgram key saved — the ears are always on now.";
        $("dgKey").value = "";
        clearDrafts(["dgKey"]); }
  catch (e) { el.textContent = "couldn't save it"; }
  // Its permanent home is the PC (settings.json) — survives a browser
  // reinstall; the extension restores itself from the bridge on boot.
  try { await askBridge("/config", { deepgram_key: key }); } catch (e) {}
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
/* ROOM_NAMES and SERVER_GROUPS both come from extension/rooms.txt now
 * (8/17) — the SAME file background.js loads its trading list from, and
 * the same file START HERE.bat reads to open tabs. One file, three
 * consumers, so a room removed from it is gone from all three at once
 * instead of needing three separate edits that could drift apart (which is
 * exactly how a channel kept trading after it stopped being opened as a
 * tab). Both start empty and are populated once by loadRoomsForPopup()
 * before the first render — see the call at the bottom of this file. */
let ROOM_NAMES = {};
let SERVER_GROUPS = [];
let _roomsLoaded = false;
async function loadRoomsForPopup() {
  try {
    const r = await fetch(chrome.runtime.getURL("rooms.txt"));
    const text = await r.text();
    const names = {};
    const groups = [];              // preserves file order, one entry per group
    const groupIndex = {};
    for (const line of text.split("\n")) {
      const t = line.trim();
      if (!t || t.startsWith("#")) continue;
      const parts = t.split("|");
      const id = (parts[0] || "").trim();
      const label = (parts[2] || id).trim();
      const group = (parts[3] || "Other rooms").trim();
      if (!id) continue;
      names[id] = label;
      if (!(group in groupIndex)) {
        groupIndex[group] = groups.length;
        groups.push({ name: group, ids: [] });
      }
      groups[groupIndex[group]].ids.push(id);
    }
    ROOM_NAMES = names;
    SERVER_GROUPS = groups;
  } catch (e) {
    // Leave both empty rather than guess — an empty Channels tab with a
    // clear "couldn't load rooms.txt" is honest; a stale hardcoded list
    // silently trading rooms that were supposedly removed is not.
    if ($("roomtoggles"))
      $("roomtoggles").innerHTML =
        '<div class="note">Couldn\'t load extension/rooms.txt — nothing shows here until this is fixed.</div>';
  }
  _roomsLoaded = true;
}
// Any channel that's opened but doesn't fall in a named group above (a room
// added later, or one of the many "added on request" ids in background.js's
// channel_ids list) still needs a home so it isn't invisible in the Servers
// list. Everything not claimed by a group goes in one catch-all row.
function serverGroupsFor(allIds) {
  const claimed = new Set(SERVER_GROUPS.flatMap(g => g.ids));
  const leftover = allIds.filter(id => !claimed.has(id));
  const groups = SERVER_GROUPS.map(g => ({ name: g.name,
                                          ids: g.ids.filter(id => allIds.includes(id)) }))
                              .filter(g => g.ids.length);
  if (leftover.length) groups.push({ name: "Other rooms", ids: leftover });
  return groups;
}

let _expandedServer = null;   // which group's channel list is open, if any
function renderServerToggles(channelDisabled) {
  const box = $("servertoggles");
  if (!box) return;
  const cd = channelDisabled || {};
  const groups = serverGroupsFor(Object.keys(ROOM_NAMES));
  box.innerHTML = groups.map((g, gi) => {
    const offCount = g.ids.filter(id => cd[id]).length;
    const allOff = offCount === g.ids.length;
    const someOff = offCount > 0 && !allOff;
    const expanded = _expandedServer === gi;
    const rows = expanded ? g.ids.map(id => {
      const on = !cd[id];
      return '<div class="row" style="margin:2px 0 2px 14px">' +
             '<span class="grow" style="font-size:11px;color:#9aa3b5">' +
             chanLabel(id) + '</span>' +
             '<button data-servchan="' + id + '" style="font-size:10px;' +
             'padding:1px 8px;border-radius:9px;cursor:pointer;border:1px solid ' +
             (on ? "#3a4254" : "#7f1d1d") + ';background:' +
             (on ? "transparent" : "#2a1720") + ';color:' +
             (on ? "#7d8697" : "#f87171") + '">' + (on ? "on" : "off") +
             '</button></div>';
    }).join("") : "";
    return '<div class="row" style="margin-bottom:2px">' +
           '<span class="grow" data-servexpand="' + gi + '" style="font-size:12px;' +
           'cursor:pointer">' + (expanded ? "▾ " : "▸ ") + g.name +
           (someOff ? ' <span style="color:#fbbf24;font-size:10px">(' + offCount +
            '/' + g.ids.length + ' off)</span>' : "") + '</span>' +
           '<button data-servtoggle="' + gi + '" style="font-size:10px;padding:1px 10px;' +
           'border-radius:9px;cursor:pointer;border:1px solid ' +
           (allOff ? "#7f1d1d" : "#3a4254") + ';background:' +
           (allOff ? "#2a1720" : "transparent") + ';color:' +
           (allOff ? "#f87171" : "#7d8697") + '">' +
           (allOff ? "OFF" : (someOff ? "partial" : "on")) + '</button></div>' +
           rows;
  }).join("");

  box.querySelectorAll("[data-servexpand]").forEach(el => {
    el.onclick = () => {
      const gi = parseInt(el.dataset.servexpand, 10);
      _expandedServer = (_expandedServer === gi) ? null : gi;
      renderServerToggles(cd);
    };
  });
  box.querySelectorAll("button[data-servtoggle]").forEach(btn => {
    btn.onclick = async () => {
      const gi = parseInt(btn.dataset.servtoggle, 10);
      const g = groups[gi];
      const { settings } = await chrome.storage.local.get("settings");
      const s = settings || {};
      s.channel_disabled = s.channel_disabled || {};
      const offCount = g.ids.filter(id => s.channel_disabled[id]).length;
      const turnOff = offCount < g.ids.length;   // any on -> turn ALL off; all off -> turn ALL on
      g.ids.forEach(id => {
        if (turnOff) s.channel_disabled[id] = true;
        else delete s.channel_disabled[id];
      });
      await chrome.storage.local.set({ settings: s });
      renderServerToggles(s.channel_disabled);
    };
  });
  box.querySelectorAll("button[data-servchan]").forEach(btn => {
    btn.onclick = async () => {
      const id = btn.dataset.servchan;
      const { settings } = await chrome.storage.local.get("settings");
      const s = settings || {};
      s.channel_disabled = s.channel_disabled || {};
      if (s.channel_disabled[id]) delete s.channel_disabled[id];
      else s.channel_disabled[id] = true;
      await chrome.storage.local.set({ settings: s });
      renderServerToggles(s.channel_disabled);
    };
  });
}

/* The per-room scoreboard he asked for: "trade information, won, lost,
 * profits, from each individual channel just to have good data to see where
 * everything comes from." Built from the day's finished trades (which carry
 * their room now) plus what's still open. */
function renderRoomStats(wallet, dayTable) {
  const el = $("roomstats");
  if (!el) return;
  el.style.display = "none"; return;   // "By room" board removed on his ask (8/13)
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

let _allLiveArm = 0;            // two-tap arm for "all LIVE" (real money)
function renderRoomToggles(channelLive, channelPull, channelDisabled) {
  const box = $("roomtoggles");
  if (!box) return;
  const cd = channelDisabled || {};
  // Rooms turned off up in Servers stay VISIBLE here (his ask, 8/17: "i
  // only want them to toggle off, not disappear") — shown dimmed with an
  // "off" tag instead of vanishing from the list. Their LIVE/pull controls
  // are hidden while off, since a room that isn't read can't trade anyway.
  const ids = Object.keys(ROOM_NAMES);
  const liveCount = ids.filter(id => !cd[id] && !!(channelLive || {})[id]).length;
  // Master row (his ask, 8/13): flip every room at once instead of clicking
  // ~60 toggles. "all testing" is always safe and instant. "all LIVE" arms
  // REAL money on every room, so it takes two taps — one to arm, one to fire,
  // the same care as the main live switch.
  const master =
    '<div class="row" style="margin-bottom:8px;padding-bottom:6px;' +
    'border-bottom:1px solid #2a303c">' +
    '<span class="grow" style="font-size:12px;font-weight:600">All rooms ' +
    '<span style="color:#7d8697;font-weight:400">(' + liveCount + '/' + ids.length +
    ' live)</span></span>' +
    '<button id="allTesting" style="font-size:10px;margin-right:6px;padding:1px 8px;' +
    'border-radius:9px;cursor:pointer;border:1px solid #3a4254;background:transparent;' +
    'color:#7d8697">all testing</button>' +
    '<button id="allLive" style="font-size:10px;padding:1px 8px;border-radius:9px;' +
    'cursor:pointer;border:1px solid #f87171;background:transparent;color:#f87171">' +
    'all LIVE</button></div>';
  box.innerHTML = master + ids.map(id => {
    // absent = LIVE now (8/23, his call: rooms come up live; only an
    // explicit false means testing)
    const live = (channelLive || {})[id] !== false;
    const pull = !!(channelPull || {})[id];
    // Server-switched-off rooms: visible but dimmed with a plain "off" tag
    // (his ask, 8/17) — no controls to misclick while the room isn't read.
    if (cd[id]) {
      return '<div class="row" style="margin-bottom:4px;opacity:.45">' +
             '<span class="grow" style="font-size:12px">' + chanLabel(id) +
             '</span><span style="font-size:10px;color:#7d8697">' +
             'off — server switch</span></div>';
    }
    // ONE button, one click, flips and saves instantly. No dropdown, no
    // confirm, no Save step — his word. Red is reserved for real money.
    // (The per-room "instant/RN wait" pill lived here 8/11-8/17. Replaced by
    // ONE global Round-number toggle in the Strategies tab — his ask.)
    return '<div class="row" style="margin-bottom:4px">' +
           '<span class="grow" style="font-size:12px">' + chanLabel(id) +
           '</span>' +
           '<span style="font-size:11px;letter-spacing:.04em;width:52px;' +
           'text-align:right;color:' + (live ? "#f87171" : "#7d8697") + '">' +
           (live ? "LIVE" : "testing") + '</span>' +
           '<button data-room="' + id + '" class="tgl money ' +
           (live ? "live" : "safe") + '"></button></div>';
  }).join("");
  // "all testing" — every room back to paper. Always safe, no confirm.
  const allOff = box.querySelector("#allTesting");
  if (allOff) allOff.onclick = async () => {
    _allLiveArm = 0;
    const { settings } = await chrome.storage.local.get("settings");
    const s = settings || {};
    s.channel_live = {};
    ids.forEach(id => { s.channel_live[id] = false; });
    await chrome.storage.local.set({ settings: s });
    renderRoomToggles(s.channel_live, s.channel_pullback, s.channel_disabled);
  };
  // "all LIVE" — real money on every room. Two taps: arm, then fire.
  const allOn = box.querySelector("#allLive");
  if (allOn) allOn.onclick = async () => {
    const now = Date.now();
    if (now - _allLiveArm > 4000) {         // first tap: arm for 4s
      _allLiveArm = now;
      allOn.textContent = "tap again to confirm";
      allOn.style.background = "#f87171";
      allOn.style.color = "#0b0d12";
      setTimeout(() => {                     // disarm + relabel if he waits
        if (Date.now() - _allLiveArm >= 4000) {
          _allLiveArm = 0;
          if (allOn.isConnected) {
            allOn.textContent = "all LIVE";
            allOn.style.background = "transparent";
            allOn.style.color = "#f87171";
          }
        }
      }, 4100);
      return;
    }
    _allLiveArm = 0;                         // second tap: apply
    const { settings } = await chrome.storage.local.get("settings");
    const s = settings || {};
    s.channel_live = s.channel_live || {};
    ids.forEach(id => { s.channel_live[id] = true; });
    await chrome.storage.local.set({ settings: s });
    renderRoomToggles(s.channel_live, s.channel_pullback, s.channel_disabled);
  };
  box.querySelectorAll("button[data-room]").forEach(btn => {
    btn.onclick = async () => {
      const { settings } = await chrome.storage.local.get("settings");
      const s = settings || {};
      s.channel_live = s.channel_live || {};
      const id = btn.dataset.room;
      s.channel_live[id] = (s.channel_live[id] === false);
      await chrome.storage.local.set({ settings: s });
      renderRoomToggles(s.channel_live, s.channel_pullback, s.channel_disabled);
    };
  });
  // (the per-room RN-pill click handler is gone with the pill — the ONE
  // Round-number toggle lives in Strategies now, 8/17)
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

  // No more ON/OFF button or its banner (8/17) — a room tab being open is the
  // only switch now. See paintBridgeLive() for the live connected/not-reachable
  // dot that replaces it.
  paintBridgeLive();

  // The ONE Round-number toggle (Strategies tab) — painted every pass.
  const vxBtn = $("voiceExits");
  if (vxBtn) {
    const vxOn = s.voice_exits === true;    // comes up OFF (8/29)
    vxBtn.textContent = vxOn ? "ON" : "off";
    vxBtn.className = "tgl money " + (vxOn ? "live" : "safe");
  }
  const veBtn = $("voiceEntries");
  if (veBtn) {
    const veOn = s.voice_entries === true;  // comes up OFF (8/29)
    veBtn.textContent = veOn ? "ON" : "off";
    veBtn.className = "tgl money " + (veOn ? "live" : "safe");
  }
  const rnBtn = $("rnAll");
  if (rnBtn) {
    const rnOn = s.rn_pullback_all !== false;   // comes up ON (8/23)
    rnBtn.textContent = rnOn ? "ON" : "off";
    rnBtn.className = "tgl " + (rnOn ? "live" : "safe");
  }

  const held = Object.keys((gs && gs.positions) || {});
  const cap = parseInt(s.guards.max_trades_per_day, 10) || 0;
  const done = (gs && gs.count) || 0;
  const bits = [];
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
    /* Who called it, and from which room. The broker row knows the contract
     * but nothing about WHY you're in it — that lives in the book (keyed
     * "caller|TICKER"). Match on symbol+strike+expiry and carry the caller
     * and room onto the line, so an open position always answers "whose
     * alert was this?" without digging through the log. An adopted position
     * has no caller (nobody's alert opened it) and stays blank rather than
     * guessing. */
    // Room and caller names come from Discord, so they never go into HTML raw.
    const esc = (v) => String(v).replace(/[&<>"']/g, ch => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
    // "MNQU6" and "MNQ" are the same instrument: the alert names the root, the
    // broker reports the dated contract. Without folding them together a
    // futures trade shows no caller at all, which is exactly what he saw.
    const futRoot = (v) => {
      let t = String(v || "").toUpperCase();
      let d = 0;
      while (t && /[0-9]$/.test(t)) { t = t.slice(0, -1); d++; }
      if (d >= 1 && d <= 2 && t && "FGHJKMNQUVXZ".includes(t.slice(-1))) {
        return t.slice(0, -1);
      }
      return String(v || "").toUpperCase();
    };
    // The call said SWING (his ask, 8/17): purple "(Swing)" in front of the
    // trade, so an overnight hold never reads like a day trade. Same
    // book-then-extension matching as creditFor below.
    const swingFor = (b) => {
      if (b.swing) return true;
      const sym = futRoot(b.symbol);
      const sources = [bookPos || {}, pos || {}];
      for (const src of sources)
      for (const k of Object.keys(src)) {
        const p = src[k] || {};
        if (futRoot(p.symbol || keySym(k)) !== sym) continue;
        if (b.strike != null && p.strike != null &&
            Math.abs(Number(p.strike) - Number(b.strike)) > 0.001) continue;
        if (b.side && p.side && String(b.side)[0] !== String(p.side)[0]) continue;
        if (p.swing) return true;
      }
      return false;
    };
    const swingTag = (b) => swingFor(b)
      ? '<span style="color:#c084fc;font-size:10px;font-weight:700">(SWING)</span> '
      : "";
    const creditFor = (b) => {
      const sym = futRoot(b.symbol);
      // Bridge book first (it keeps who/room for the life of the trade), then
      // the extension's own pending entries as a fallback.
      const sources = [bookPos || {}, pos || {}];
      for (const src of sources)
      for (const k of Object.keys(src)) {
        const p = src[k] || {};
        // The extension's own store has no `symbol` field at all — the ticker
        // lives in the key ("tlm|QQQ"). Reading p.symbol alone matched nothing,
        // which is the other half of why this line never appeared.
        if (futRoot(p.symbol || keySym(k)) !== sym) continue;
        if (b.strike != null && p.strike != null &&
            Math.abs(Number(p.strike) - Number(b.strike)) > 0.001) continue;
        if (b.side && p.side && String(b.side)[0] !== String(p.side)[0]) continue;
        // The popup reads the EXTENSION's own position store, which names
        // these fields differently from the bridge's book: `author` and
        // `channelId`, not `who` and `room`. Reading only the bridge's names
        // meant the credit line was always empty — the data was there the
        // whole time under another name. Take whichever exists, and fall back
        // to the trader encoded in the key ("tlm|QQQ").
        const who = (() => {
          const a = p.who && p.who !== "?" ? p.who
                  : (p.author && p.author !== "?" ? p.author : "");
          if (a) return a;
          const fromKey = keyWho(k);
          return fromKey && fromKey !== "?" ? fromKey : "";
        })();
        const room = p.room || (p.channelId ? chanLabel(p.channelId) : "");
        if (!who && !room) continue;
        return (who ? esc(who) : "") + (who && room ? " · " : "") +
               (room ? esc(room) : "");
      }
      return "";
    };
    // Its own line under the trade, his call 8/12: "put their name either
    // under or on top - I just need to SEE it". An inline tail was getting
    // lost at the end of a long row.
    const creditLine = (b) => {
      const c = creditFor(b);
      return c ? '<div class="poscredit">\u21b3 ' + c + "</div>" : "";
    };
    // 1) REAL Webull positions — live price and P&L, straight from the broker.
    for (const b of bpos) {
      const sym = String(b.symbol || "").toUpperCase();
      const contract = [sym, b.expiry || "",
        (b.strike != null ? b.strike : "") +
        (b.side === "PUTS" ? "P" : b.side === "CALLS" ? "C" : "")]
        .filter(Boolean).join(" ");
      const n = parseInt(b.qty || 1, 10) || 1;
      const paid = (b.fill != null) ? " · paid " + Number(b.fill).toFixed(2) : "";
      // "≈" = walked forward from the last 1/s quote on the underlying's tick
      // stream (delta/gamma); a plain number is the real quote (9/2).
      const now = (b.last != null) ? " · now " + (b.est ? "\u2248" : "") + Number(b.last).toFixed(2) : "";
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
      // Futures carry no strike or expiry, so the contract renders as just the
      // code (MNQU6). What they DO carry is a direction, and a short shown as a
      // long is a lie about which way you're leaning — so it's spelled out.
      const dir = (b.kind === "future")
        ? (Number(b.direction) < 0
            ? '<span style="color:#f87171;font-size:10px;font-weight:700">SHORT</span> '
            : '<span style="color:#4ade80;font-size:10px;font-weight:700">LONG</span> ')
        : "";
      const _cr = creditFor(b);
      // Hover as well as the line under it — his call 8/12. A title works even
      // if the extra line is ever clipped by the panel's scroll box.
      const _tip = _cr ? ' title="' + _cr.replace(/"/g, "&quot;") + '"' : "";
      rows.push('<div class="posrow"' + _tip + '><span class="grow">' + swingTag(b) + tag + dir +
        '<span class="in">IN</span> <b>' +
        contract + '</b> <b>x' + n + "</b>" + paid + now + plTxt +
        "</span>" + x + "</div>" +
        (_cr ? '<div class="poscredit">\u21b3 ' + _cr + "</div>" : ""));
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
      rows.push('<div class="posrow"><span class="grow">' +
        (p.swing ? '<span style="color:#c084fc;font-size:10px;font-weight:700">(SWING)</span> ' : "") +
        '<span class="in wait">BID IN</span> <b>' +
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
    purse.style.display = "none";   // TEST summary hidden on his ask (8/13)
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

  renderServerToggles(s.channel_disabled || {});
  renderRoomToggles(s.channel_live || {}, s.channel_pullback || {}, s.channel_disabled || {});
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
const EXPORT_EVERY_MIN_DEFAULT = 30;
async function exportEveryMs() {
  try {
    const { export_every_min } = await chrome.storage.local.get("export_every_min");
    const v = parseFloat(export_every_min);
    if (v >= 1 && v <= 240) return v * 60 * 1000;
  } catch (e) { /* default stands */ }
  return EXPORT_EVERY_MIN_DEFAULT * 60 * 1000;
}
async function tickExportTimer() {
  const el = $("exportTimer");
  if (!el) return;
  let last = 0;
  try { last = (await chrome.storage.local.get("last_export")).last_export || 0; } catch (e) {}
  let ms = last ? (last + (await exportEveryMs()) - Date.now()) : 0;
  if (ms < 0) ms = 0;
  const mm = Math.floor(ms / 60000);
  const ss = Math.floor((ms % 60000) / 1000);
  const lastBit = last ? " · last saved " + ago(last) : "";
  el.textContent = "Next auto-save in " + mm + ":" +
    String(ss).padStart(2, "0") + lastBit;
}
setInterval(tickExportTimer, 1000);
tickExportTimer();

/* The auto-save interval box: shows the remembered value, saves on change.
 * The background worker re-arms its alarm the moment this is stored. */
(async () => {
  const inp = $("exportEvery");
  if (!inp) return;
  try {
    const { export_every_min } = await chrome.storage.local.get("export_every_min");
    inp.value = export_every_min || EXPORT_EVERY_MIN_DEFAULT;
  } catch (e) { inp.value = EXPORT_EVERY_MIN_DEFAULT; }
  inp.onchange = async () => {
    let v = parseFloat(inp.value);
    if (!(v >= 1)) v = EXPORT_EVERY_MIN_DEFAULT;
    if (v > 240) v = 240;
    inp.value = v;
    await chrome.storage.local.set({ export_every_min: v });
  };
})();

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

/* DRAFT MEMORY for the key fields (his ask, 8/20): Chrome kills this popup the
 * moment another window takes focus, and everything typed-but-not-saved died
 * with it — paste the App Key, click over to grab the Secret, come back to an
 * empty box. Every keystroke in these fields now saves to the extension's
 * local storage and is restored when the popup reopens. A successful save
 * CLEARS its fields' drafts, so secrets don't linger once they've reached
 * settings.json on the PC. */
const DRAFT_IDS = ["wbkey", "wbsecret", "wbpkey", "wbpsecret",
                   "tsUser", "tsKey", "tsUrl", "tvUser", "tvPass",
                   "ninjaAccount", "ninjaDir", "ninjaAtm",
                   "exName", "exKey", "exSecret", "exAcctId", "aiKey", "dgKey"];
function wireDrafts() {
  try {
    chrome.storage.local.get("field_drafts", d => {
      const drafts = (d && d.field_drafts) || {};
      for (const id of DRAFT_IDS) {
        const el = $(id);
        if (!el) continue;
        if (!el.value && drafts[id]) el.value = drafts[id];
        el.addEventListener("input", () => {
          chrome.storage.local.get("field_drafts", dd => {
            const cur = (dd && dd.field_drafts) || {};
            if (el.value) cur[id] = el.value;
            else delete cur[id];
            chrome.storage.local.set({ field_drafts: cur });
          });
        });
      }
    });
  } catch (e) { /* storage unavailable — typing just isn't remembered */ }
}
function clearDrafts(ids) {
  try {
    chrome.storage.local.get("field_drafts", dd => {
      const cur = (dd && dd.field_drafts) || {};
      for (const id of ids) delete cur[id];
      chrome.storage.local.set({ field_drafts: cur });
    });
  } catch (e) {}
}
wireDrafts();

// rooms.txt loads once before the first paint so the Channels/Servers tabs
// never flash empty — every render() after this one just reuses it.
loadRoomsForPopup().then(render);
setInterval(render, 2000);
refreshMode();
setInterval(refreshMode, 1000);
loadDays();
loadScoreboard();
