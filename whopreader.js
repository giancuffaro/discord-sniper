// ============================================================================
// whop-reader.js — precise Whop message reader (replaces the wide-net whop.js)
// Mapped live from whop.com on 2026-08-18 (FirstStepTrading rooms).
//
// WHY THE OLD READER CAUGHT JUNK
// The old reader scraped broad page text, so it captured the storefront
// sidebar, marketing blurbs, reviews, and pricing. Real messages live in two
// distinct, stable DOM structures depending on room type. Read ONLY those.
//
// ALSO CRITICAL — the room URL must be the *joined* app URL:
//   https://whop.com/joined/<business>/<room-slug>/app/
// e.g. https://whop.com/joined/firststeptrading/day-trades-cvgzKYDmcUEDGh/app/
// Any other URL (store page, product page) renders the marketing content the
// old reader was capturing. Verify every line in rooms.txt has /joined/ + /app/.
//
// ROOM TYPE A — "FEED" rooms (the alert rooms: Day Trades, Trading Floor,
//   Futures, Swing Trades, High Risk, Long Term, Daily Watchlist)
//   Post container:  div[id^="post_"][id$="_container"]
//     - id embeds a globally unique post id: post_<ID>_container  → perfect
//       dedup key, no text hashing needed.
//   Body text:       descendant div[class*="post-body"]   (class "group/post-body")
//   Author line:     container innerText lines are:
//                    [ displayName, @handle, "·", relativeAge, ...body ]
//   Timestamps:      only relative ("9h", "2d") — stamp Date.now() at first sight.
//
// ROOM TYPE B — "CHAT" rooms (Trading Chat, Gains, Testimonials)
//   Row:             [class*="ChatMessageContainer"]
//   Header:          [class*="ChatMessageHeaderUsername"] → "Felony • 9:19 PM"
//                    NOTE: consecutive messages from the same author are
//                    GROUPED — later rows have no header. Carry the last seen
//                    author forward.
//   Body:            [class*="ChatMessageRichContent"]
//   Class name hashes (ArOy2a_ etc.) change between deploys — always match the
//   stable suffix with [class*="..."], never the full class.
//
// Both structures live in the top-level document (no iframe piercing needed).
// ============================================================================

(function () {
  'use strict';

  const seen = new Set(); // post ids / chat keys already emitted

  // ---------- TYPE A: feed rooms ----------
  function readFeedPosts() {
    const out = [];
    // NOTE: use prefix query + JS filter, not [id$="_container"] — the compound
    // CSS attribute selector intermittently returned 0 during page hydration
    // in live testing; this form was reliable.
    const containers = [...document.querySelectorAll('div[id^="post_"]')]
      .filter(e => e.id.endsWith('_container'));
    for (const c of containers) {
      const id = c.id.slice(5, -10); // strip "post_" and "_container"
      if (seen.has(id)) continue;

      const bodyEl = c.querySelector('div[class*="post-body"]');
      const text = bodyEl ? bodyEl.innerText.trim() : '';
      if (!text) continue;

      // header lines: displayName, @handle, "·", age
      const lines = c.innerText.split('\n').map(s => s.trim()).filter(Boolean);
      const author = lines[0] || '';
      const handle = (lines.find(l => l.startsWith('@')) || '').slice(1);

      seen.add(id);
      out.push({
        source: 'whop',
        kind: 'feed',
        id,
        author,
        handle,
        text,
        capturedAt: Date.now(),
      });
    }
    return out;
  }

  // ---------- TYPE B: chat rooms ----------
  function readChatMessages() {
    const out = [];
    const rows = document.querySelectorAll('[class*="ChatMessageContainer"]');
    let lastAuthor = '';
    let lastTime = '';
    for (const r of rows) {
      const hdr = r.querySelector('[class*="ChatMessageHeaderUsername"]');
      if (hdr) {
        // header text renders as "Name\n•\n9:19 PM"
        const parts = hdr.parentElement.innerText.split('\n').map(s => s.trim()).filter(s => s && s !== '•');
        lastAuthor = parts[0] || lastAuthor;
        lastTime = parts[1] || lastTime;
      }
      const bodyEl = r.querySelector('[class*="ChatMessageRichContent"]');
      const text = bodyEl ? bodyEl.innerText.trim() : '';
      if (!text) continue;

      // chat rows have no DOM id → dedup on author+time+text hash
      const key = 'c|' + lastAuthor + '|' + lastTime + '|' + text.slice(0, 120);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({
        source: 'whop',
        kind: 'chat',
        id: key,
        author: lastAuthor,
        handle: '',
        text,
        timeText: lastTime,
        capturedAt: Date.now(),
      });
    }
    return out;
  }

  // ---------- room-type detection ----------
  function detectRoomType() {
    if ([...document.querySelectorAll('div[id^="post_"]')].some(e => e.id.endsWith('_container'))) return 'feed';
    if (document.querySelector('[class*="ChatMessageContainer"]')) return 'chat';
    return null; // page not a message room (or still loading) — emit NOTHING
  }

  // ---------- main poll ----------
  // Replaces whatever broad text-scrape the old whop.js did. If the page is
  // not a recognized room type, return [] — never fall back to page text.
  function readWhopMessages() {
    const type = detectRoomType();
    if (type === 'feed') return readFeedPosts();
    if (type === 'chat') return readChatMessages();
    return [];
  }

  // Guard: warn loudly (once) if this tab is not on a /joined/.../app/ URL —
  // that is the #1 cause of the storefront-junk captures.
  if (!/\/joined\/.+\/app\/?/.test(location.pathname)) {
    console.warn('[whop-reader] Not a joined-room app URL — this page will only show storefront content. Fix rooms.txt to use https://whop.com/joined/<biz>/<room>/app/');
  }

  // Export for the extension's existing wiring (adjust to your bridge):
  window.__whopReader = { readWhopMessages, detectRoomType };

  // Example polling loop (wire into your existing capture pipeline):
  // setInterval(() => {
  //   for (const msg of readWhopMessages()) sendToBridge(msg);
  // }, 2000);
})();
