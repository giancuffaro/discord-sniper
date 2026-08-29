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
 * CRITICAL: real messages only render on the room app URL — since Whop's
 * 2026 redesign that is:
 *   https://whop.com/<business>/exp_<id>/app/
 * (/joined/ links are DEAD — they redirect to Townhall, which renders
 * neither structure. That redirect is why Whop produced zero signals for
 * months.) rooms.txt must use the exp_ form.
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

// Screenshots posted in a Whop room (his ask, 8/19) — real uploaded images
// only, never tiny avatars/emojis. Whop serves uploads from its own CDN and
// from imgix/cloudfront; keep the full signed url so the reader can fetch it.
function imagesIn(el) {
  const urls = [];
  try {
    el.querySelectorAll("img").forEach(im => {
      const src = im.currentSrc || im.src || im.getAttribute("src") || "";
      if (!src || /^data:/.test(src)) return;
      if (/(avatar|emoji|icon|reaction|sticker|profile)/i.test(
            src + " " + (im.className || ""))) return;
      const w = im.naturalWidth || im.width || 0;
      if (w && w < 64) return;
      if (urls.indexOf(src) === -1) urls.push(src);
    });
  } catch (e) {}
  return urls.slice(0, 3);
}

/* The post's own age, read from its header lines: "34s", "1m", "9h", "2d",
 * "Jul 23". Stamping Date.now() on everything is how a JULY 23rd VXX post
 * traded as fresh on AUGUST 18th — the reader must report the REAL time and
 * let guardCheck's staleness rule ("too stale to chase") do the refusing,
 * loudly, in the log. No age found = assume fresh; the 20s guard still rules. */
function ageToTs(lines) {
  const RE_REL = /^·?\s*(just now|now|(\d+)\s*([smhd]))$/i;
  const RE_MON = /^·?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})$/i;
  for (const l of (lines || []).slice(0, 6)) {
    let m = RE_REL.exec(l);
    if (m) {
      if (!m[2]) return Date.now();
      const mult = { s: 1e3, m: 6e4, h: 36e5, d: 864e5 }[m[3].toLowerCase()];
      return Date.now() - parseInt(m[2], 10) * (mult || 6e4);
    }
    m = RE_MON.exec(l);
    if (m) {
      const mon = ["jan", "feb", "mar", "apr", "may", "jun",
                   "jul", "aug", "sep", "oct", "nov", "dec"]
                  .indexOf(m[1].toLowerCase());
      const d = new Date();
      d.setMonth(mon, parseInt(m[2], 10));
      d.setHours(12, 0, 0, 0);
      if (d.getTime() > Date.now()) d.setFullYear(d.getFullYear() - 1);
      return d.getTime();
    }
  }
  return Date.now();
}

function send(text, author, at, images) {
  const ts = at || Date.now();
  chrome.runtime.sendMessage({
    type: "MESSAGE",
    platform: "whop",
    text: text,
    images: images || [],
    author: author || "?",
    channelId: roomId(),
    channelName: roomName(),
    postedAt: ts,
    // History = the post's own age says it's old, OR the first 15 seconds
    // after a (re)load (the page painting what already happened). History
    // is captured, studied, never traded.
    history: ts < STARTED - 5000 || (Date.now() - STARTED) < 15000,
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
    const images = imagesIn(c);
    // Text OR a screenshot is enough now — an image-only alert used to be
    // dropped here and never reached the reader.
    if (!text && !images.length) continue;
    let author = "?";
    let at = Date.now();
    try {
      const lines = String(c.innerText || "").split("\n")
        .map(s => s.trim()).filter(Boolean);
      author = lines[0] || "?";
      at = ageToTs(lines);          // the post's REAL age (the VXX lesson)
    } catch (e) {}
    SEEN.add(id);
    if (SEEN.size > 6000) SEEN.clear();
    send(text, author, at, images);
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
      send(text, lastAuthor, Date.now());   // live chat = present tense
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

// One loud line if this tab isn't on a room URL — the #1 cause of the
// zero-alerts months. Whop's 2026 redesign KILLED /joined/ links: they now
// redirect to /townhall/ (or mangle the room id), a page with neither post
// nor chat structures, so a tab parked on an old link reads nothing forever.
// Rooms now live at whop.com/<business>/exp_<id>/app/ (verified live 8/30:
// both the feed selectors and the chat selectors still match perfectly on
// the new pages — the reader was never blind, the tabs were just parked on
// a lobby). The tab still gets swept (harmlessly reads nothing), but the
// console says why nothing is arriving.
if (!/\/exp_[A-Za-z0-9]+\/app\/?/.test(location.pathname)) {
  try {
    console.warn("[sniper] this is NOT a room URL — messages only render at " +
                 "whop.com/<business>/exp_<id>/app/. Old /joined/ links are " +
                 "dead (they redirect to Townhall). Re-open the room from " +
                 "the community sidebar and pin THAT tab.");
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

// HEALTH PULSE (8/25): once a minute, tell the worker whether this page
// actually RENDERED — a black/stuck Whop shell runs scripts but paints no
// text. The watchdog reloads on "running but blank", never on "quiet room",
// so an evening with no messages stops looking like a dead tab.
setInterval(function () {
  try {
    if (!(chrome.runtime && chrome.runtime.id)) return;
    const txt = (document.body && document.body.innerText) || "";
    chrome.runtime.sendMessage({
      type: "WHOP_PULSE",
      ok: txt.replace(/\s+/g, "").length > 120,
      href: location.href
    }, function () { void chrome.runtime.lastError; });
  } catch (e) {}
}, 60 * 1000);
})();
