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

const SEEN = new Set();
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

function handle(li) {
  if (!li.id || SEEN.has(li.id)) return;
  SEEN.add(li.id);
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
  const history = postedAt < STARTED - 5000;

  const text = textOf(li);
  if (!text) return;

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
  });
} catch (e) { /* orphaned copy after an update; the fresh one registers instead */ }

window.__SNIPER_STOP__ = function () {
  grabbing = false;
  if (observer) observer.disconnect();
  if (timer) clearInterval(timer);
  observer = null;
  watching = null;
};

// Discord is a single-page app: switching channels swaps the whole list out
// from under us, so re-check for it rather than attaching once and hoping.
attach();
timer = setInterval(function () {
  // After an update the old copy of this file is still running but is no longer
  // connected to anything — chrome.runtime.id goes undefined. Stand down rather
  // than sitting there looking busy.
  let alive = false;
  try { alive = !!(chrome.runtime && chrome.runtime.id); } catch (e) { alive = false; }
  if (!alive) { window.__SNIPER_STOP__(); return; }
  attach();
}, 1500);
})();
