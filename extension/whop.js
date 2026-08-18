/* whop.js — reads a Whop room you already have open. PRECISE reader now.
 *
 * Same rules as the Discord reader: it never logs in, never talks to Whop's
 * servers, never sends a request the page didn't already make. It reads what
 * is on your screen, because you're allowed to read the room you pay for.
 *
 * Rewritten 8/18 from a live DOM map of the FirstStepTrading rooms (the old
 * wide-net version captured 943 lines of storefront junk and zero alerts).
 * Real messages live in exactly two structures, and this reads ONLY those:
 *
 * TYPE A — "FEED" rooms (the alert rooms: Day Trades, Futures, Swing
 *   Trades, High Risk):
 *     post container:  div[id^="post_"] whose id ends "_container"
 *                      (id embeds a globally unique post id — the dedup key)
 *     body text:       descendant div[class*="post-body"]
 *     author:          first innerText line of the container
 *     NOTE: match the id with a prefix query + JS endsWith filter — the
 *     compound CSS [id$="_container"] form intermittently returned 0 while
 *     the page hydrates (seen in live testing).
 *
 * TYPE B — "CHAT" rooms (Trading Chat, Gains):
 *     row:     [class*="ChatMessageContainer"]
 *     header:  [class*="ChatMessageHeaderUsername"] → "Felony • 9:19 PM";
 *              consecutive messages from one author share a header, so the
 *              last seen author carries forward.
 *     body:    [class*="ChatMessageRichContent"]
 *     Class hashes change between Whop deploys — always [class*="..."] on
 *     the stable suffix, never a full class name.
 *
 * If the page is NEITHER type (storefront, still loading), emit NOTHING —
 * never fall back to scraping page text. That fallback was the whole bug.
 *
 * CRITICAL: real messages only render on the JOINED app URL —
 *   https://whop.com/joined/<business>/<room-slug>/app/
 * Anything else is the storefront. rooms.txt must use /joined/ + /app/.
 */
(function () {
"use strict";

if (typeof window.__SNIPER_WHOP_STOP__ === "function") {
  try { window.__SNIPER_WHOP_STOP__(); } catch (e) { /* old copy gone */ }
}

const SEEN = new Set();       // post ids / chat keys already sent
const STARTED = Date.now();
let timer = null;

function roomId() {
  // The path names the room well enough to keep two Whop rooms' lexicons
  // apart, and background.js's whopRoomOf() maps it to the canonical id.
  return "whop:" + location.pathname.replace(/\/+$/, "");
}

// The room's real name the way Whop shows it, for the popup's channel list.
function roomName() {
  try {
    let t = (document.title || "").split(" | ")[0].split(" - ")[0].trim();
    if (t && !/^whop$/i.test(t)) return t;
  } catch (e) {}
  try {
    const h = document.querySelector("h1, h2, [class*='title']");
    if (h && h.textContent.trim()) return h.textContent.trim().slice(0, 60);
  } catch (e) {}
  return "";
}

function clean(s) {
  return String(s || "").replace(/\s+/g, " ").trim();
}

function send(text, author, historyExtra) {
  chrome.runtime.sendMessage({
    type: "MESSAGE",
    platform: "whop",
    text: text,
    author: author || "?",
    channelId: roomId(),
    channelName: roomName(),
    postedAt: Date.now(),
    // The first 15 seconds after a (re)load are the page painting what
    // already happened — feed posts only carry relative ages ("9h"), so
    // everything in the first sweep is history: captured, studied, never
    // traded. After the grace, a newly appearing post is genuinely new.
    history: !!historyExtra || (Date.now() - STARTED) < 15000,
    url: location.href
  }).catch(() => { /* worker asleep; the next send wakes it */ });
}

/* ---- TYPE A: feed rooms (the alert rooms) ---- */
function readFeedPosts() {
  // Prefix query + endsWith filter on purpose — see header note.
  const containers = [];
  try {
    for (const e of document.querySelectorAll('div[id^="post_"]')) {
      if (e.id && e.id.endsWith("_container")) containers.push(e);
    }
  } catch (e) { return; }
  for (const c of containers) {
    const id = "p|" + c.id.slice(5, -10);   // strip "post_" and "_container"
    if (SEEN.has(id)) continue;
    let text = "";
    try {
      const body = c.querySelector('div[class*="post-body"]');
      text = body ? clean(body.innerText) : "";
    } catch (e) { text = ""; }
    if (!text) continue;
    let author = "?";
    try {
      const lines = String(c.innerText || "").split("\n")
        .map(s => s.trim()).filter(Boolean);
      author = lines[0] || "?";
    } catch (e) {}
    SEEN.add(id);
    if (SEEN.size > 6000) SEEN.clear();
    send(text, author, false);
  }
}

/* ---- TYPE B: chat rooms ---- */
let lastAuthor = "?";
function readChatMessages() {
  let rows;
  try { rows = document.querySelectorAll('[class*="ChatMessageContainer"]'); }
  catch (e) { return; }
  let lastTime = "";
  for (const r of rows) {
    try {
      const hdr = r.querySelector('[class*="ChatMessageHeaderUsername"]');
      if (hdr && hdr.parentElement) {
        // header renders as "Name\n•\n9:19 PM"
        const parts = String(hdr.parentElement.innerText || "").split("\n")
          .map(s => s.trim()).filter(s => s && s !== "•");
        lastAuthor = parts[0] || lastAuthor;
        lastTime = parts[1] || lastTime;
      }
      const body = r.querySelector('[class*="ChatMessageRichContent"]');
      const text = body ? clean(body.innerText) : "";
      if (!text) continue;
      // chat rows carry no DOM id — author + clock + text is the identity
      const key = "c|" + lastAuthor + "|" + lastTime + "|" + text.slice(0, 120);
      if (SEEN.has(key)) continue;
      SEEN.add(key);
      if (SEEN.size > 6000) SEEN.clear();
      send(text, lastAuthor, false);
    } catch (e) { /* one bad row never stops the sweep */ }
  }
}

function sweep() {
  // Room-type detection each pass (a SPA navigation can change it): feed
  // wins if any post container exists; chat if any chat row; NEITHER means
  // storefront or still loading — read nothing, on purpose.
  let isFeed = false;
  try {
    for (const e of document.querySelectorAll('div[id^="post_"]')) {
      if (e.id && e.id.endsWith("_container")) { isFeed = true; break; }
    }
  } catch (e) {}
  if (isFeed) { readFeedPosts(); return; }
  try {
    if (document.querySelector('[class*="ChatMessageContainer"]')) {
      readChatMessages();
    }
  } catch (e) {}
}

window.__SNIPER_WHOP_STOP__ = function () {
  if (timer) clearInterval(timer);
  timer = null;
};

// One loud line if this tab isn't on the joined app URL — the #1 cause of
// the storefront-junk captures. The tab still gets swept (harmlessly reads
// nothing), but the console says why nothing is arriving.
if (!/\/joined\/.+\/app\/?/.test(location.pathname)) {
  try {
    console.warn("[sniper] this is NOT a joined-room URL — messages only " +
                 "render at whop.com/joined/<biz>/<room>/app/. Fix rooms.txt.");
  } catch (e) {}
}

// A 2-second poll instead of a MutationObserver: the stable ids make
// re-reads free (dedup by id), a poll survives Whop's SPA re-renders that
// used to orphan the observer, and 2s is faster than a human reads.
sweep();
timer = setInterval(function () {
  let alive = false;
  try { alive = !!(chrome.runtime && chrome.runtime.id); } catch (e) { alive = false; }
  if (!alive) { window.__SNIPER_WHOP_STOP__(); return; }
  sweep();
}, 2000);
})();
