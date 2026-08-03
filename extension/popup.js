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
    ? "" : " &nbsp;·&nbsp; $" + Math.round(bp).toLocaleString() + " buying power";
  const fut = modeStatus.futures_account
    ? " &nbsp; " + dot(true) + "Futures acct" : "";
  sub.innerHTML = dot(true) + "Bridge &nbsp; " +
    dot(!!(modeStatus.has_keys && modeStatus.connected)) + "Webull keys" +
    fut + bpBit;
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
  paintProps();
}

/* The keys go to the bridge and nowhere else. Nothing is written to
 * chrome.storage — the browser forgets them the moment they're sent, which is
 * the whole reason the bridge exists in the first place. */
$("propadd").onclick = async () => {
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
const ROOM_NAMES = { "829754942817828884": "Main room",
                     "987515353670221834": "Aristotle",
                     "1144369893760831489": "Midas",
                     "1433933203302776852": "Aristotle small acct",
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
                     "1387459050505240597": "Boka 4" };

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
      return '<div class="trow"><b>' + n + "</b>" +
        '<span class="sub">' + today + ever + "</span></div>";
    }).join("");
}

function renderRoomToggles(channelLive) {
  const box = $("roomtoggles");
  if (!box) return;
  box.innerHTML = Object.keys(ROOM_NAMES).map(id => {
    const live = !!(channelLive || {})[id];
    // ONE button, one click, flips and saves instantly. No dropdown, no
    // confirm, no Save step — his word. Red is reserved for real money.
    return '<div class="row" style="margin-bottom:4px">' +
           '<span class="grow" style="font-size:12px">' + ROOM_NAMES[id] +
           '</span><button data-room="' + id + '" class="' +
           (live ? "live" : "safe") + '" style="width:110px">' +
           (live ? "LIVE" : "testing") + "</button></div>";
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
      renderRoomToggles(s.channel_live);
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
    $("holding").innerHTML = "No active trades";
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
  renderRoomStats(wallet, day_table);

  renderRoomToggles(s.channel_live || {});
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

$("export").onclick = async () => {
  const { captured } = await chrome.storage.local.get("captured");
  // Which room each line came from. Three rooms export into one file, and the
  // tag is what keeps their three dialects apart when the parser gets tuned.
  const ROOMS = { "829754942817828884": "main",
                  "987515353670221834": "aristotle",
                  "1144369893760831489": "midas",
                  "1433933203302776852": "aristotle-small" };
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
loadScoreboard();
