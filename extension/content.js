/* content.js — reads the Discord page you already have open.
 *
 * This is the whole reason the extension exists: it never logs in, never talks
 * to Discord's API, never sends a single request Discord didn't already expect
 * from your browser. It reads the messages that are already on your screen.
 * That's why it works in a room you don't own — you're allowed to read the room.
 *
 * Discord's CSS class names are scrambled and change without warning, so
 * nothing here matches on a class name alone. It matches on the structural
 * hooks Discord has kept stable for years: data-list-id on the message list,
 * and the id="chat-messages-..." / id="message-content-..." pattern.
 */

/* Everything below is inside a function on purpose. When the extension updates
 * itself it puts a fresh copy of this file into a page that already has one, and
 * a plain top-level `const` would blow up on the second copy with "already been
 * declared" — the update would look like it worked and the tab would quietly
 * stop reading. Wrapped like this, each copy gets its own scope, and the line
 * below shuts the old one down before the new one starts. */
(function () {
"use strict";

if (typeof window.__SNIPER_STOP__ === "function") {
  try { window.__SNIPER_STOP__(); } catch (e) { /* old copy already gone */ }
}

const SEEN = new Map();   // message id -> captured text LENGTH (embed-race fix)
const STARTED = Date.now();
let observer = null;
let watching = null;
let timer = null;

function channelId() {
  const m = location.pathname.match(/\/channels\/[^/]+\/(\d+)/);
  return m ? m[1] : "";
}

// The room's REAL name, the way Discord shows it, so the popup can label each
// channel with what it actually is instead of a hand-typed placeholder. Two
// honest sources: the channel header Discord paints at the top of the message
// pane, and the page title. Whichever gives a clean name wins; empty if the
// page hasn't painted yet (the next message will carry it).
function _cleanChannel(s) {
  // Only ever the channel, never the server. "#chan | Server", "chan - Server",
  // "(3) #chan" all collapse to just "chan".
  s = String(s || "").split(" | ")[0].split(" — ")[0];
  s = s.replace(/\s[-–]\s.*$/, "");           // "chan - Server" -> "chan"
  s = s.replace(/^\(\d+\)\s*/, "");           // drop unread count
  s = s.replace(/^[#﹟＃｜|\s]+/, "").trim();    // drop leading hash / divider
  return s;
}
function channelName() {
  // 1) The header title beside the # — Discord keeps a stable "title" hook here.
  try {
    const h = document.querySelector('[class*="title"] h1, section[aria-label] h1, h1[class*="title"]');
    if (h && h.textContent.trim()) {
      const c = _cleanChannel(h.textContent);
      if (c) return c;
    }
  } catch (e) {}
  // 2) The tab title: "(3) #signals | Server Name" -> "signals".
  try {
    const t = _cleanChannel(document.title || "");
    if (t && !/^discord$/i.test(t)) return t;
  } catch (e) {}
  return "";
}

function authorOf(li) {
  const own = li.querySelector('[id^="message-username-"] [class*="username"]')
           || li.querySelector('[class*="username"]');
  if (own && own.textContent.trim()) return own.textContent.trim();
  // Discord groups consecutive messages from one person and drops the name on
  // all but the first, so walk back up the list until a name turns up.
  let el = li.previousElementSibling, hops = 0;
  while (el && hops++ < 40) {
    const u = el.querySelector && el.querySelector('[class*="username"]');
    if (u && u.textContent.trim()) return u.textContent.trim();
    el = el.previousElementSibling;
  }
  return "unknown";
}

// A bot posts its call inside an embed — a colored box with an author line, a
// title, a description, name/value field pairs, and a footer. The ticker can
// live in ANY of those (Options Insider puts "CLOSED — CAT 950C" on the author
// line), so read them all. Missing one of these is how a whole call goes dark.
const EMBED_SEL = '[class*="embedAuthor"], [class*="embedTitle"], ' +
  '[class*="embedDescription"], [class*="embedFieldName"], ' +
  '[class*="embedFieldValue"], [class*="embedFooter"]';

function textOf(li) {
  const parts = [];
  const body = li.querySelector('[id^="message-content-"]');
  if (body) parts.push(body.textContent);
  li.querySelectorAll(EMBED_SEL).forEach(e => parts.push(e.textContent));
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

// For the history grabber we want EVERY line, no matter how the room formats
// it. If the structured read above comes back shorter than the whole row's
// visible text (an embed shape we didn't name), fall back to the full row so
// nothing is silently dropped from a tuning export.
function fullTextOf(li) {
  const t = textOf(li);
  let all = "";
  try { all = (li.innerText || "").replace(/\s+/g, " ").trim(); } catch (e) {}
  return all.length > t.length ? all : t;
}

// Some rooms post the whole call as a SCREENSHOT (his ask, 8/19). Collect the
// uploaded images on a message so the worker can have them read by vision when
// the text alone carries no call. ONLY real attachments — never emojis,
// avatars, reactions, or stickers, which are tiny decorative images.
function imagesOf(li) {
  const urls = [];
  try {
    li.querySelectorAll("img").forEach(im => {
      const src = im.currentSrc || im.src || im.getAttribute("src") || "";
      if (!src) return;
      // Discord serves uploaded pictures from these hosts under /attachments/
      // (cdn) or as proxied /external|/attachments (media). Keep the FULL url,
      // query and all — the cdn links are signed and won't fetch without it.
      if (!/(cdn|media)\.discordapp\.(net|com)\//.test(src)) return;
      if (/\/(emojis|avatars|icons|stickers|embed\/avatars)\//.test(src)) return;
      const cls = (im.className || "") + " " +
                  ((im.closest && im.closest('[class*="reaction"], [class*="emoji"], [class*="avatar"]')) ? "deco" : "");
      if (/emoji|avatar|reaction|sticker|deco/i.test(cls)) return;
      // skip obvious thumbnails/icons by rendered size when we can see it
      const w = im.naturalWidth || im.width || 0;
      if (w && w < 64) return;
      if (urls.indexOf(src) === -1) urls.push(src);
    });
  } catch (e) {}
  return urls.slice(0, 3);
}

function handle(li) {
  if (!li.id) return;
  // EMBED RACE FIX (8/30, G: "every bot puts the trade inside an embed" —
  // HD Greeter, ZTRADEZ BOT, Options Insider Alerts, Nitro Trades all send
  // an empty body with the call in the embed): Discord paints the message
  // row FIRST and hydrates the embed a beat later. The old code burned the
  // id into SEEN on first sight, so the blank pre-hydration version won and
  // the alert vanished without a log line. SEEN is now id -> captured text
  // LENGTH: a later, FULLER read of the same row (the embed arrived, via
  // the subtree observer or a re-sweep) re-emits; a same-length re-sweep
  // stays deduped. The worker's seenMessage mirrors this (mid + length).
  const text = textOf(li);
  const images = imagesOf(li);
  const prevLen = SEEN.get(li.id);
  if (prevLen !== undefined && text.length <= prevLen) return;  // nothing new
  if (!text && !images.length) return;  // blank shell, embed not hydrated —
                                        // leave UNRECORDED so the hydration
                                        // mutation still passes through
  SEEN.set(li.id, text.length);
  if (SEEN.size > 3000) SEEN.clear();

  const t = li.querySelector("time[datetime]");
  const postedAt = t ? Date.parse(t.getAttribute("datetime")) : Date.now();
  // When you open or scroll a channel, Discord paints old messages into the
  // DOM. Those are history, not calls — but history is exactly what tuning
  // the parser on a new room needs, and scrolling up is the one honest way to
  // get it (no API, no login, nothing Discord didn't already send this
  // browser). So it goes through MARKED, and the worker files it in the
  // capture and refuses to let it anywhere near the trading path. Scroll back
  // through a week of a room and you've exported its whole lexicon tonight
  // instead of collecting it live for days.
  // FRESH IS NOT HISTORY (9/2): when Chrome discards a room tab under
  // memory pressure and the heartbeat reloads it, STARTED resets and every
  // message on screen — including a call posted 30 seconds ago — was filed
  // as "history" and silently never traded. A message younger than 3
  // minutes is live no matter when this reader started; the worker's
  // stale-entry gate (3 min) still refuses anything older for OPEN/ADD.
  const history = postedAt < STARTED - 5000 &&
                  (Date.now() - postedAt) > 3 * 60 * 1000;

  // (text/images and the empty-check moved to the top of handle() — the
  // embed-race fix needs them before the dedupe decision. Image-only posts
  // still pass: vision reads them.)

  // A reply quotes an older message, and Discord renders the quoted line
  // inside the new one — which is how Mike replying to his own morning entry
  // re-bought AMD at top tick. Discord marks replies with a stable id
  // pattern, so they're flagged here and the worker refuses to trade them.
  const isReply = !!li.querySelector('[id^="message-reply-context"]');

  // When the extension reloads (an update landed), THIS orphaned copy's
  // sendMessage throws "Extension context invalidated" — synchronously, so a
  // .catch() alone doesn't stop the console error. Wrap it, and when it fires,
  // shut this dead copy down so it stops trying; the fresh copy the background
  // re-injects (and the tab auto-refresh) takes over the reading.
  try {
    chrome.runtime.sendMessage({
      type: "MESSAGE",
      mid: li.id,             // the Discord message id — stable identity so the
                              // worker can drop a re-read instead of logging it
                              // again (the reader re-scans on every sweep, and a
                              // room can be open in two tabs)
      text,
      full: fullTextOf(li),   // everything in the row — for the grabber's export
      images,                 // uploaded screenshots, for the vision reader
      author: authorOf(li),
      channelId: channelId(),
      channelName: channelName(),
      postedAt,
      history,
      reply: isReply,
      url: location.href
    }).catch(() => { /* worker asleep mid-send; the next one wakes it */ });
  } catch (e) {
    // Context gone — this copy is done. Stop the observer/timer quietly.
    try { if (typeof window.__SNIPER_STOP__ === "function") window.__SNIPER_STOP__(); }
    catch (e2) { /* already gone */ }
  }
}

function onMutations(records) {
  for (const r of records) {
    for (const n of r.addedNodes) {
      if (n.nodeType !== 1) continue;
      if (n.id && n.id.startsWith("chat-messages-")) handle(n);
      else if (n.querySelectorAll) {
        n.querySelectorAll('li[id^="chat-messages-"]').forEach(handle);
      }
    }
  }
}

function attach() {
  const list = document.querySelector('[data-list-id="chat-messages"]');
  if (!list) return;
  if (list === watching) return;
  if (observer) observer.disconnect();
  watching = list;
  observer = new MutationObserver(onMutations);
  observer.observe(list, { childList: true, subtree: true });
  chrome.runtime.sendMessage({ type: "ATTACHED", channelId: channelId(),
                               channelName: channelName() })
    .catch(() => {});
}

/* ---- History grabber -------------------------------------------------------
 * Scroll this room UP on its own, so the reader captures a couple of months of
 * its wording without you dragging the scrollbar for an hour. Everything it
 * sees this way is history (filed for tuning, never traded), same as if you'd
 * scrolled by hand. Stops at the date you set, or when the channel runs out.
 */
let grabbing = false;

function findScroller(el) {
  let n = el;
  while (n && n !== document.body) {
    const s = getComputedStyle(n);
    if ((s.overflowY === "auto" || s.overflowY === "scroll") &&
        n.scrollHeight > n.clientHeight + 40) return n;
    n = n.parentElement;
  }
  return document.querySelector('div[class*="scroller"]') || null;
}

function grabReport(obj) {
  try { chrome.runtime.sendMessage(Object.assign({ type: "GRAB_PROGRESS", channelId: channelId() }, obj)); }
  catch (e) {}
}

async function grabHistory(untilTs) {
  if (grabbing) return;
  // No date given -> go ONE YEAR back from the real date, right now.
  if (!untilTs) untilTs = Date.now() - 1 * 365 * 24 * 60 * 60 * 1000;
  const list = document.querySelector('[data-list-id="chat-messages"]');
  const scroller = list && findScroller(list);
  if (!scroller) { grabReport({ done: true, why: "couldn't find the message pane — open the room first" }); return; }
  grabbing = true;
  let stagnant = 0, lastH = -1, rounds = 0, parked = false, lastOldest = null;
  // GENTLE by design. Yanking straight to scrollTop=0 makes Discord fetch
  // batches faster than it can render them, which spikes CPU and crashes the
  // tab on a long pull. Instead we nudge up about one screenful at a time and
  // wait a beat, so Discord loads the next batch and settles before the next
  // nudge. Slower, but it survives a 3-year scroll.
  const WAIT = 750;                           // ms between nudges — twice as fast
                                              // as 1500; safe because we nudge
                                              // gently (a screen at a time), not
                                              // yank to the very top.
  grabReport({ started: true });
  while (grabbing && rounds < 20000) {
    rounds++;
    // Chrome slows hidden tabs to a crawl AND Discord stops loading older
    // messages when its tab isn't on screen. If we kept scrolling we'd see no
    // new height, wrongly decide we hit the top, and auto-download a partial
    // file. So while this tab is in the background we PARK: hold our place,
    // don't touch the stagnation counter, and wait for it to come back to the
    // front. The grab resumes exactly where it left off — nothing is lost.
    if (document.visibilityState !== "visible") {
      if (!parked) { grabReport({ parked: true, oldest: lastOldest }); parked = true; }
      await new Promise(r => setTimeout(r, 1000));
      rounds--;                              // a parked round doesn't count
      continue;
    }
    if (parked) { grabReport({ resumed: true }); parked = false; }
    // Nudge up ~80% of a screen rather than jumping to the very top.
    const step = Math.max(200, Math.floor(scroller.clientHeight * 0.8));
    scroller.scrollTop = Math.max(0, scroller.scrollTop - step);
    await new Promise(r => setTimeout(r, WAIT));
    // SWEEP every message currently on screen, don't wait for Discord's
    // "new message" event — during a fast scroll those events skip rows, which
    // is how whole embed calls went missing. handle() dedupes via SEEN, so
    // re-sweeping the same rows is cheap and nothing gets dropped.
    list.querySelectorAll('li[id^="chat-messages-"]').forEach(handle);
    const times = list.querySelectorAll('time[datetime]');
    const oldestEl = times[0];
    const oldest = oldestEl ? Date.parse(oldestEl.getAttribute("datetime")) : null;
    if (oldest) lastOldest = oldest;
    const h = scroller.scrollHeight;
    const atTop = scroller.scrollTop <= 4;   // pinned at the top of what's loaded
    if (rounds % 4 === 0 || (untilTs && oldest && oldest <= untilTs)) {
      grabReport({ oldest: oldest || null, rounds });
    }
    if (untilTs && oldest && oldest <= untilTs) { grabReport({ done: true, reached: "date", oldest }); break; }
    // Only call it "the top" when we're pinned at the top AND nothing new has
    // loaded for several waits. While we're still scrolling down through
    // already-loaded messages (not at top), that's not stagnation.
    if (atTop && h === lastH) { if (++stagnant >= 8) { grabReport({ done: true, reached: "top" }); break; } }
    else { stagnant = 0; }
    lastH = h;
  }
  grabbing = false;
  if (rounds >= 20000) grabReport({ done: true, reached: "limit" });
}

try {
  chrome.runtime.onMessage.addListener((msg, sender, reply) => {
    if (!msg) return;
    if (msg.type === "GRAB_HISTORY") { grabHistory(msg.untilTs || 0); reply && reply({ ok: true }); }
    else if (msg.type === "STOP_GRAB") { grabbing = false; reply && reply({ ok: true }); }
    else if (msg.type === "JOIN_VOICE") { joinLiveVoice().then(r => reply && reply(r)); return true; }
  });
} catch (e) { /* orphaned copy after an update; the fresh one registers instead */ }

window.__SNIPER_STOP__ = function () {
  grabbing = false;
  if (observer) observer.disconnect();
  if (timer) clearInterval(timer);
  observer = null;
  watching = null;
};

/* LIVE detection (his ask, 8/20): some rooms trade LIVE on voice/stage, and
 * the call is SPOKEN seconds before it's typed. When Discord paints a LIVE
 * badge anywhere in this server's channel list, tell the worker — it logs it
 * loudly, fires a desktop notification, and starts the voice listener the
 * moment this tab is playing the room's audio. Class hashes change between
 * Discord builds, so hunt by class fragment AND by literal badge text. */
let _lastLivePing = 0;
function liveScan() {
  const now = Date.now();
  if (now - _lastLivePing < 60000) return;    // one ping a minute is plenty
  let hit = "";
  try {
    const el = document.querySelector(
      '[class*="liveBadge" i], [class*="liveTag" i], [aria-label*="live" i][class*="badge" i]');
    if (el) hit = (el.getAttribute("aria-label") || el.textContent || "LIVE").trim().slice(0, 40);
    if (!hit) {
      // literal little "LIVE" pills in the sidebar
      for (const s of document.querySelectorAll("nav span, aside span")) {
        const t = (s.textContent || "").trim();
        if (t === "LIVE" || t === "Live") { hit = "LIVE badge"; break; }
      }
    }
  } catch (e) {}
  if (!hit) return;
  _lastLivePing = now;
  try {
    chrome.runtime.sendMessage({ type: "LIVE_DETECTED",
      channelId: channelId(), channelName: channelName(),
      where: hit, url: location.href }).catch(() => {});
  } catch (e) {}
}

/* AUTO-JOIN (9/2, G: "last time I knew it joined itself"). When a room
 * shows the LIVE badge, click into that voice/stage channel so the tab
 * starts playing audio — which is what makes the ears start. Same ethos
 * as everything else here: it clicks what you could click, in your own
 * browser, in a room you pay for. Best effort; the notification path
 * stays as the fallback. */
async function joinLiveVoice() {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const clickBtn = (rx) => {
    for (const b of document.querySelectorAll("button, [role='button']")) {
      const t = (b.textContent || b.getAttribute("aria-label") || "").trim();
      if (rx.test(t)) { b.click(); return t; }
    }
    return null;
  };
  try {
    // 1) already in a voice channel? Discord shows a "Disconnect" control.
    for (const b of document.querySelectorAll("button, [role='button']")) {
      const t = (b.getAttribute("aria-label") || b.textContent || "").trim();
      if (/^disconnect$/i.test(t)) return { ok: true, why: "already in voice" };
    }
    // 2) the live channel in the sidebar: the LIVE pill's nearest link/row
    let target = null;
    const badge = document.querySelector(
      '[class*="liveBadge" i], [class*="liveTag" i], [aria-label*="live" i][class*="badge" i]');
    if (badge) target = badge.closest("a, [role='link'], [role='button'], li");
    if (!target) {
      for (const sp of document.querySelectorAll("nav span, aside span")) {
        const t = (sp.textContent || "").trim();
        if (t === "LIVE" || t === "Live") { target = sp.closest("a, [role='link'], [role='button'], li"); break; }
      }
    }
    if (!target) return { ok: false, why: "no LIVE channel row found" };
    target.click();
    await sleep(1500);
    // 3) a stage/voice channel opens with a join prompt — press it
    let pressed = clickBtn(/^(join|join voice|join channel|join stage|join as audience|join the stage)$/i);
    await sleep(1500);
    if (!pressed) pressed = clickBtn(/^(join|join voice|join channel|join stage|join as audience)$/i);
    return { ok: true, why: pressed ? ("pressed " + pressed) : "clicked the live channel" };
  } catch (e) {
    return { ok: false, why: String(e && e.message || e).slice(0, 80) };
  }
}

// Belt-and-suspenders for the MutationObserver: re-read every message on
// screen on a timer, don't trust the "new message" event alone. Discord's
// observer can drop an event when the tab is backgrounded, throttled, or busy
// re-rendering — that's how Unraveller's "all out of TSLA" was never read and
// the position sat open (8/19). handle() dedupes via SEEN, so re-sweeping the
// same rows is free, and it only ever fires a message the observer skipped —
// and only while it's still fresh, since handle() files anything old as
// history and the bridge's staleness guard drops a stale chase anyway.
function liveSweep() {
  const list = document.querySelector('[data-list-id="chat-messages"]');
  if (!list) return;
  try { list.querySelectorAll('li[id^="chat-messages-"]').forEach(handle); }
  catch (e) { /* one bad row never stops the sweep */ }
}

// Discord is a single-page app: switching channels swaps the whole list out
// from under us, so re-check for it rather than attaching once and hoping.
attach();
liveSweep();
timer = setInterval(function () {
  // After an update the old copy of this file is still running but is no longer
  // connected to anything — chrome.runtime.id goes undefined. Stand down rather
  // than sitting there looking busy.
  let alive = false;
  try { alive = !!(chrome.runtime && chrome.runtime.id); } catch (e) { alive = false; }
  if (!alive) { window.__SNIPER_STOP__(); return; }
  attach();
  liveSweep();       // catch anything the live observer missed, every tick
  liveScan();        // and notice when the server goes LIVE on voice/stage
}, 1500);

/* HEARTBEAT (v3.5.0 A3.1, 9/2). A dead reader and a quiet room look
 * identical for 40 minutes today — the silence alert even says so. But a
 * merely-quiet room still has a living content script in it, and a living
 * script can say so. Every 30s: rows on screen, watcher attached, whether
 * Chrome discarded/hid us. Background reloads a room that stops answering. */
function _readerHealth() {
  const list = document.querySelector('[data-list-id="chat-messages"]');
  const rows = list
    ? list.querySelectorAll('li[id^="chat-messages-"]').length : 0;
  return {
    type: "READER_ALIVE",
    channelId: (location.pathname.match(/\/channels\/\d+\/(\d+)/) || [])[1]
               || null,
    rows: rows,
    listFound: !!list,
    observing: !!observer,          // false = watcher died, reads nothing
    wasDiscarded: !!document.wasDiscarded,
    hidden: document.hidden,
    at: Date.now()
  };
}
function _beat() {
  // "Extension context invalidated" throws synchronously on a reload —
  // never let a beat kill the reader.
  try { chrome.runtime.sendMessage(_readerHealth()).catch(() => {}); } catch (e) { }
}
setInterval(_beat, 30000);
_beat();

/* Chrome FREEZES background tabs. A frozen tab's MutationObserver queues
 * nothing, so mutations during the freeze are lost outright. On resume,
 * re-attach and force a full re-read — handle() dedupes via SEEN, so
 * re-reading is free and missing a call is not. */
document.addEventListener("resume", function () {
  try {
    const list = document.querySelector('[data-list-id="chat-messages"]');
    if (list) {
      if (observer) { try { observer.disconnect(); } catch (e) { } }
      observer = new MutationObserver(onMutations);
      observer.observe(list, { childList: true, subtree: true });
      list.querySelectorAll('li[id^="chat-messages-"]').forEach(handle);
    }
  } catch (e) { }
  _beat();
});
})();
