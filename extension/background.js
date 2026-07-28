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
const LOG_MAX = 120;

async function cfg() {
  const { settings } = await chrome.storage.local.get("settings");
  return Object.assign({
    armed: false,
    stopped: false,
    capture: true,
    bridge_url: BRIDGE_DEFAULT,
    allowed_symbols: [],
    author_names: [],
    channel_ids: [],
    extra_veto_words: [],
    guards: {}
  }, settings || {});
}

async function addLog(entry) {
  const { log } = await chrome.storage.local.get("log");
  const l = log || [];
  l.unshift(Object.assign({ t: Date.now() }, entry));
  await chrome.storage.local.set({ log: l.slice(0, LOG_MAX) });
}

async function capture(text, author) {
  const { captured } = await chrome.storage.local.get("captured");
  const c = captured || [];
  c.push({ t: Date.now(), author, text });
  await chrome.storage.local.set({ captured: c.slice(-3000) });
}

async function badge() {
  const c = await cfg();
  const st = await guardState();
  if (c.stopped) {
    chrome.action.setBadgeText({ text: "STOP" });
    chrome.action.setBadgeBackgroundColor({ color: "#b91c1c" });
  } else if (!c.armed) {
    chrome.action.setBadgeText({ text: "SAFE" });
    chrome.action.setBadgeBackgroundColor({ color: "#3f3f46" });
  } else {
    chrome.action.setBadgeText({ text: String(st.count) });
    chrome.action.setBadgeBackgroundColor({ color: "#b45309" });
  }
}

async function sendOrder(sig, qty, c) {
  const order = {
    action: sig.action, symbol: sig.symbol, side: sig.side, qty,
    strike: sig.strike, expiry: sig.expiry, limit: sig.limit,
    // "exited SPY, and back in @ 2.84" is one message and two orders: sell the
    // contract, then buy the same one back. The bridge does both legs so the
    // gap between them is as small as it can be.
    reenter: !!sig.reenter, reenter_limit: sig.reenter_limit || null,
    source: "discord-extension", raw: sig.raw, ts: Date.now()
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
    return { ok: false, msg: "couldn't reach the bridge on your PC — is BRIDGE.bat " +
             "running? The trade did NOT go out." };
  }
  const ms = Math.round(performance.now() - t0);
  const body = (await r.text()).slice(0, 200);
  if (!r.ok) return { ok: false, msg: "the bridge refused it: HTTP " + r.status + " " + body };
  return { ok: true, msg: "sent in " + ms + " ms — " + (body || "accepted") };
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.type === "ATTACHED") { badge(); reply({ ok: true }); return; }
  if (msg.type !== "MESSAGE") { reply({ ok: false }); return true; }

  (async () => {
    const c = await cfg();
    if (c.capture) capture(msg.text, msg.author);

    const sig = parseSignal(msg.text, c);
    if (!sig.fire) {
      // Only worth showing the ones that looked like a trade and then failed a
      // check. Logging pure chatter would bury the useful lines.
      if (sig.action) await addLog({ kind: "ignored", why: sig.why, text: msg.text,
                                     author: msg.author });
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

    const qty = clampQty(sig.qty || 1, c);
    // The room says "all out of AMD" — no strike, no expiry, because everyone
    // there knows which contract. A broker doesn't, so fill it in from the
    // position before this leaves the browser.
    if (sig.action === "CLOSE") await fillFromPosition(sig);
    // Recorded before the order goes out, so a crash mid-send can't double-fire.
    await guardRecord(sig, c);
    const res = await sendOrder(sig, qty, c);
    await addLog({ kind: res.ok ? "fired" : "failed", what: human(sig) + " x" + qty,
                   why: res.msg, text: msg.text, author: msg.author });
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

chrome.runtime.onInstalled.addListener(badge);
chrome.runtime.onStartup.addListener(badge);
badge();
