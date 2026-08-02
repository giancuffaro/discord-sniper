/* whop.js — reads a Whop room you already have open. Recording only, for now.
 *
 * Same rules as the Discord reader: it never logs in, never talks to Whop's
 * servers, never sends a request the page didn't already make. It reads what
 * is on your screen, because you're allowed to read the room you pay for.
 *
 * The honest difference: Discord's page structure is known and stable, and
 * this bot has 174 tested sample lines of that room's grammar. Whop has
 * neither yet. So this file is deliberately a WIDE NET — it captures anything
 * that looks like chat and lets the export show what the room really looks
 * like. Once that export exists, this gets rewritten as a precise reader the
 * same way the Discord one was, and only then does trading come into it.
 * The worker enforces that: everything tagged platform:"whop" is filed in
 * the capture and never reaches the parser.
 *
 * Whop is built with utility CSS (hashed/tailwind classes), so unlike
 * Discord there are no stable ids to hook. The heuristics below aim for
 * "leaf block of readable text inside a scrolling feed", which is what a
 * chat message is on every chat site ever built.
 */
(function () {
"use strict";

if (typeof window.__SNIPER_WHOP_STOP__ === "function") {
  try { window.__SNIPER_WHOP_STOP__(); } catch (e) { /* old copy gone */ }
}

const SEEN = new Set();       // fingerprints of what's already been sent
const STARTED = Date.now();
let observer = null;
let timer = null;

function roomId() {
  // The path names the room well enough to keep two Whop rooms' lexicons
  // apart in the export, which is all it's for.
  return "whop:" + location.pathname.replace(/\/+$/, "");
}

function clean(s) {
  return String(s || "").replace(/\s+/g, " ").trim();
}

/* The first capture day taught us what the storefront looks like — tracking
 * pixels, "Pay Get access", sign-in prompts. None of it is chat and none of
 * it belongs in the lexicon file. */
const JUNK = [/facebook\.com\/tr/i, /^<img\b/i, /^pay get access/i,
              /^join for free/i, /terms of service/i, /^support chat$/i,
              /^partners(new)?$/i, /^enter your email/i,
              /consistent profitability\.?$/i, /tradingview chart access/i];
function isJunk(t) { return JUNK.some(re => re.test(t)); }

/* A message's own moment, if the page put one anywhere nearby. Chat apps
 * almost universally use <time datetime="..."> for this. When there isn't
 * one, "now" is the only honest guess. */
function stampOf(el) {
  const t = el.querySelector && (el.querySelector("time[datetime]") ||
                                 (el.closest && el.closest("time[datetime]")));
  if (t) {
    const v = Date.parse(t.getAttribute("datetime"));
    if (!isNaN(v)) return v;
  }
  return Date.now();
}

/* Leaf blocks: elements whose text is readable and which don't just wrap
 * other blocks saying the same thing. Walking these instead of whole added
 * subtrees stops one mutation exporting as five nested copies. */
function leafBlocks(root, out) {
  if (!root || root.nodeType !== 1) return out;
  const tag = root.tagName;
  if (tag === "SCRIPT" || tag === "STYLE" || tag === "SVG" ||
      tag === "BUTTON" || tag === "INPUT" || tag === "TEXTAREA") return out;
  const kids = Array.from(root.children || []);
  const substantial = kids.filter(k => clean(k.innerText).length >= 8);
  if (substantial.length >= 2) {
    for (const k of kids) leafBlocks(k, out);
    return out;
  }
  const t = clean(root.innerText);
  // Too short is UI chrome ("Send", "Reply", "2h"); too long is a whole
  // feed painted in one go — recurse into that instead of swallowing it.
  if (t.length >= 8 && t.length <= 600) out.push(root);
  else if (t.length > 600) for (const k of kids) leafBlocks(k, out);
  return out;
}

function fingerprint(text, at) {
  // Text plus the minute it belongs to. Chat repaints the same nodes a lot;
  // the same sentence in the same minute is the same message.
  return text.slice(0, 120) + "|" + Math.floor(at / 60000);
}

/* "Felony@felonytrades·1d" — Whop paints the author as its own little block
 * right before the message. Remember the last one seen and hand it to the
 * next message, exactly how a human reads the feed. */
let lastAuthor = "?";
const RE_AUTHOR = /^(.{1,24}?)\s*(?:\(MOD\))?\s*@[a-z0-9_.]+\s*[·•]/i;

function handle(el) {
  for (const block of leafBlocks(el, [])) {
    let text = clean(block.innerText);
    if (isJunk(text)) continue;
    const ma = RE_AUTHOR.exec(text);
    if (ma) {
      lastAuthor = ma[1].trim() || "?";
      // The author line sometimes carries the message right behind it.
      text = clean(text.replace(RE_AUTHOR, "").replace(/^\S*\s*/, ""));
      if (text.length < 8) continue;
    }
    const at = stampOf(block);
    const fp = fingerprint(text, at);
    if (SEEN.has(fp)) continue;
    SEEN.add(fp);
    if (SEEN.size > 6000) SEEN.clear();
    chrome.runtime.sendMessage({
      type: "MESSAGE",
      platform: "whop",
      text,
      author: lastAuthor,
      channelId: roomId(),
      postedAt: at,
      // The first 15 seconds after a (re)load are the page painting what
      // already happened. Whop doesn't always stamp messages with a time,
      // so without this grace an old entry could look brand new on every
      // reload and BUY. History is captured, studied, never traded.
      history: at < STARTED - 5000 || (Date.now() - STARTED) < 15000,
      url: location.href
    }).catch(() => { /* worker asleep; the next send wakes it */ });
  }
}

function onMutations(records) {
  for (const r of records) {
    for (const n of r.addedNodes) {
      if (n.nodeType === 1) handle(n);
    }
  }
}

function attach() {
  if (observer) return;
  observer = new MutationObserver(onMutations);
  observer.observe(document.body, { childList: true, subtree: true });
}

window.__SNIPER_WHOP_STOP__ = function () {
  if (observer) observer.disconnect();
  if (timer) clearInterval(timer);
  observer = null;
};

attach();
timer = setInterval(function () {
  let alive = false;
  try { alive = !!(chrome.runtime && chrome.runtime.id); } catch (e) { alive = false; }
  if (!alive) { window.__SNIPER_WHOP_STOP__(); return; }
  attach();
}, 2000);
})();
