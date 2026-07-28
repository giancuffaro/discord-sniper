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

const SEEN = new Set();
const STARTED = Date.now();
let observer = null;
let watching = null;

function channelId() {
  const m = location.pathname.match(/\/channels\/[^/]+\/(\d+)/);
  return m ? m[1] : "";
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

function textOf(li) {
  const parts = [];
  const body = li.querySelector('[id^="message-content-"]');
  if (body) parts.push(body.textContent);
  // some rooms post their calls inside embeds rather than as plain text
  li.querySelectorAll('[class*="embedTitle"], [class*="embedDescription"], [class*="embedFieldValue"]')
    .forEach(e => parts.push(e.textContent));
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

function handle(li) {
  if (!li.id || SEEN.has(li.id)) return;
  SEEN.add(li.id);
  if (SEEN.size > 3000) SEEN.clear();

  const t = li.querySelector("time[datetime]");
  const postedAt = t ? Date.parse(t.getAttribute("datetime")) : Date.now();
  // When you open or scroll a channel, Discord paints old messages into the
  // DOM. Those are history, not calls. Anything from before this tab started
  // watching is ignored outright.
  if (postedAt < STARTED - 5000) return;

  const text = textOf(li);
  if (!text) return;

  chrome.runtime.sendMessage({
    type: "MESSAGE",
    text,
    author: authorOf(li),
    channelId: channelId(),
    postedAt,
    url: location.href
  }).catch(() => { /* worker asleep mid-send; the next one wakes it */ });
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
  chrome.runtime.sendMessage({ type: "ATTACHED", channelId: channelId() })
    .catch(() => {});
}

// Discord is a single-page app: switching channels swaps the whole list out
// from under us, so re-check for it rather than attaching once and hoping.
attach();
setInterval(attach, 1500);
