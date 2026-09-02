/* =====================================================================
 * v3.5.0 CHROME PATCH — stop losing rooms silently
 * =====================================================================
 *
 * Three pastes. content.js first, then two into background.js.
 * Nothing here changes how a signal is read or traded — this is only
 * about knowing, within 30 seconds, that a reader has stopped reading.
 * ===================================================================== */


/* =====================================================================
 * PASTE 1 of 3  ->  content.js, at the BOTTOM of the file
 * ---------------------------------------------------------------------
 * THE HEARTBEAT.
 *
 * Today a dead reader and a quiet room look identical for 40 minutes.
 * The silence alarm even says so out loud: "dead reader or sleeping room."
 * That ambiguity is the whole problem, and it is unnecessary — a room
 * that is merely quiet still has a living content script in it, and a
 * living content script can say so.
 *
 * So every 30 seconds this reports that it is alive AND what it can see.
 * The background script stops guessing from silence and starts knowing.
 * ===================================================================== */

function _readerHealth() {
  const list = document.querySelector('[data-list-id="chat-messages"]');
  const rows = list
    ? list.querySelectorAll('li[id^="chat-messages-"]').length : 0;
  return {
    type: "READER_ALIVE",
    channelId: (location.pathname.match(/\/channels\/\d+\/(\d+)/) || [])[1]
               || null,
    rows: rows,                       // 0 while a room is genuinely empty
    listFound: !!list,                // false = Discord's DOM moved, or the
                                      //         page never finished loading
    observing: !!observer,            // false = the MutationObserver died
    wasDiscarded: !!document.wasDiscarded,
    hidden: document.hidden,
    at: Date.now()
  };
}

function _beat() {
  // "Extension context invalidated" throws synchronously on a reload — the
  // same trap handled at line ~182. Never let a beat kill the reader.
  try { chrome.runtime.sendMessage(_readerHealth()); } catch (e) { }
}
setInterval(_beat, 30000);
_beat();

/* PAGE LIFECYCLE — Chrome FREEZES background tabs to save power. A frozen
 * tab's timers stop and its MutationObserver queues nothing, so mutations
 * that happen while frozen are simply lost. On resume the DOM has moved on
 * and the 8-second re-sweep only sees what is still rendered.
 *
 * So on resume: re-attach the observer and force a full re-read. handle()
 * dedupes through SEEN, so re-reading is free and missing a call is not. */
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
document.addEventListener("freeze", function () {
  try { chrome.runtime.sendMessage({ type: "READER_FROZEN",
                                     channelId: (location.pathname
                                       .match(/\/channels\/\d+\/(\d+)/) || [])[1],
                                     at: Date.now() }); } catch (e) { }
});


/* =====================================================================
 * PASTE 2 of 3  ->  background.js, anywhere near oneTabPerChannel()
 * ---------------------------------------------------------------------
 * THE DISCARD FIX. This is the important one.
 *
 * Chrome's Memory Saver DISCARDS background tabs when memory gets tight.
 * With 26 Discord tabs open, that is not a maybe.
 *
 * A discarded tab is the worst possible failure because it looks fine:
 *   - it STILL appears in chrome.tabs.query()
 *   - it STILL reports its normal /channels/<id>/<id> URL
 *   - oneTabPerChannel counts it as the live tab for that room
 *   - the silence check sees a room, not a problem
 * ...but there is NO content script in it. It reads nothing. Forever.
 *
 * Every watchdog in this extension believes a discarded room is healthy.
 * Two small things fix it: ask Chrome not to discard these tabs, and
 * check the flag Chrome sets when it does it anyway.
 * ===================================================================== */

const READER_BEAT = {};        // channelId -> last heartbeat ts
const READER_TAB = {};         // channelId -> tabId
const BEAT_DEAD_MS = 95000;    // 3 missed beats. Reload, don't wonder.
const REVIVED_AT = {};         // tabId -> last revive, so we don't loop

chrome.runtime.onMessage.addListener((m, sender) => {
  if (!m) return;
  if (m.type === "READER_ALIVE") {
    if (m.channelId) {
      READER_BEAT[m.channelId] = m.at || Date.now();
      if (sender && sender.tab) READER_TAB[m.channelId] = sender.tab.id;
    }
    // A living reader whose observer died is a reader that reads nothing.
    // Say it loudly — this used to be invisible.
    if (m.listFound && !m.observing) {
      addLog({ kind: "skipped", author: ROOM_LABELS[m.channelId] || m.channelId,
               text: "",
               why: "⚠ reader is running but its message watcher is detached — "
                    + "reloading that room" });
      const tid = READER_TAB[m.channelId];
      if (tid) { try { chrome.tabs.reload(tid); } catch (e) { } }
    }
  }
});

/* Ask Chrome to keep every room tab loaded, and rescue any it already
 * dropped. Runs on the 30-second watch-build alarm.
 *
 * autoDiscardable has to be RE-APPLIED: Chrome resets it when a tab
 * navigates, and Discord navigates constantly. Setting it once at open
 * time is not enough, which is why this lives on the alarm. */
async function keepRoomsLoaded() {
  let tabs;
  try {
    tabs = await chrome.tabs.query({ url: ["https://discord.com/channels/*",
                                           "https://*.discord.com/channels/*"] });
  } catch (e) { return; }

  const now = Date.now();
  for (const t of tabs) {
    try { await chrome.tabs.update(t.id, { autoDiscardable: false }); }
    catch (e) { /* older Chrome, or the tab just closed */ }

    // Chrome discarded it anyway (memory pressure wins over the request).
    // A reload is the only way back, and it is safe: content.js is
    // idempotent, and SEEN starts clean so nothing double-fires.
    if (t.discarded) {
      if (now - (REVIVED_AT[t.id] || 0) < 60000) continue;
      REVIVED_AT[t.id] = now;
      const label = (t.url.match(/\/channels\/\d+\/(\d+)/) || [])[1];
      await addLog({ kind: "skipped",
                     author: ROOM_LABELS[label] || label || "room", text: "",
                     why: "⚠ Chrome had DISCARDED this room's tab to save "
                          + "memory — it was reading nothing. Reloaded." });
      try { await chrome.tabs.reload(t.id); } catch (e) { }
    }
  }

  // Now the heartbeat check: a room whose reader has gone quiet on the
  // WIRE (not in the chat) is broken, whatever its tab looks like.
  for (const cid of Object.keys(ROOM_LABELS)) {
    const last = READER_BEAT[cid];
    if (!last) continue;                       // never beat = never attached
    if (now - last < BEAT_DEAD_MS) continue;
    const tid = READER_TAB[cid];
    if (!tid) continue;
    if (now - (REVIVED_AT[tid] || 0) < 60000) continue;
    REVIVED_AT[tid] = now;
    await addLog({ kind: "skipped", author: ROOM_LABELS[cid] || cid, text: "",
                   why: "⚠ this room's reader stopped answering ("
                        + Math.round((now - last) / 1000) + "s). Reloading it "
                        + "now instead of waiting 40 minutes to notice." });
    try { await chrome.tabs.reload(tid); } catch (e) { }
  }
}


/* =====================================================================
 * PASTE 3 of 3  ->  background.js
 * ---------------------------------------------------------------------
 * Wire it into the alarm, and calm memoryShed down.
 * ===================================================================== */

/* FIND the watch-build line and ADD keepRoomsLoaded():
 *
 *   if (a.name === "watch-build") { checkBuild(); syncFills();
 *     oneTabPerChannel(); checkBridgeHealth(); memoryShed();
 *     keepRoomsLoaded(); }                      // <-- add this
 */

/* AND — inside oneTabPerChannel(), a discarded tab must never be kept as
 * the winner over a live one. Add this to the candidate filter, next to
 * the existing "loading tabs are never candidates" rule from 8/30:
 *
 *   if (t.discarded) continue;      // a discarded tab reads nothing
 */

/* FINALLY — memoryShed reloads the oldest room on a timer to shed memory.
 * With the two fixes above, blind rotation is mostly wasted work: a
 * reload is the heaviest thing you can do to a tab (it re-downloads the
 * whole Discord app) and every reload is a window where that room reads
 * nothing at all.
 *
 * Change SHED_EVERY_MS from 2 hours to 6, and let the heartbeat decide
 * what actually needs reloading. Rotate on a clock only as a backstop:
 *
 *   const SHED_EVERY_MS = 6 * 60 * 60 * 1000;
 */
