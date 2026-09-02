# The Chrome side — 26 tabs, and how rooms die quietly

**9/2/26, against 3.4.11.** I read `background.js`, `content.js` and the manifest.

You've already built a lot here: the paced flood, `oneTabPerChannel`, the 40-minute silence alarm, `memoryShed`, the embed-race fix, the tab-massacre fix. This isn't a rebuild. There is one specific hole, and it is a bad one.

---

## THE HOLE — Chrome discards tabs, and every watchdog you have believes the discarded tab is fine

`autoDiscardable` is never set anywhere in the extension. `tab.discarded` is never checked.

Chrome's **Memory Saver** discards background tabs when memory gets tight. With 26 Discord tabs open, that is not a maybe — that is the exact situation the feature exists for.

Here is why a discarded tab is the worst possible failure: **it looks completely healthy.**

| What checks it | What it sees |
|---|---|
| `chrome.tabs.query()` | the tab is there |
| its URL | normal `/channels/<id>/<id>` |
| `oneTabPerChannel` | counts it as the live tab for that room |
| the 40-min silence alarm | a room, no problem |
| you, glancing at Chrome | a tab with the right title |

**But there is no content script in it.** It reads nothing. Not one alert. Forever, until something reloads it.

And your own silence notification spells out the ambiguity you're stuck with today:

> *"Dead reader (F5 its tab) or the room's just asleep — worth a look either way."*

Forty minutes of market hours before you even get *that* much, and then it can't tell you which one it is.

---

## FIX 1 — Ask Chrome not to discard, and catch it when it does anyway

Two calls. `chrome.tabs.update(id, {autoDiscardable: false})` on every room tab, and a `tab.discarded` check that reloads immediately.

One thing that matters: **`autoDiscardable` must be re-applied, not set once.** Chrome resets it when a tab navigates, and Discord navigates constantly. That's why it goes on the 30-second `watch-build` alarm rather than at open time.

---

## FIX 2 — Make the reader prove it's alive, instead of inferring it from silence

A quiet room and a dead reader are indistinguishable right now. They don't have to be: **a room that is merely quiet still has a living content script in it, and a living script can say so.**

Every 30 seconds `content.js` now reports:

- that it's running at all
- how many message rows it can see
- whether Discord's message list was found
- **whether the MutationObserver is still attached** — a reader whose observer died is running and reading nothing, and today that is completely invisible
- whether the page was discarded

Three missed beats (95 seconds) and the background reloads that tab. **A 40-minute mystery becomes a 90-second self-heal**, and the log says which it was instead of guessing.

---

## FIX 3 — Frozen tabs lose messages

Chrome *freezes* background tabs to save power, separately from discarding. A frozen tab's timers stop and its MutationObserver queues nothing — mutations during the freeze are simply gone. On resume the DOM has moved on, and your 8-second re-sweep only catches what's still rendered.

The patch listens for the `resume` event, re-attaches the observer and forces a full re-read. `handle()` dedupes through `SEEN`, so re-reading costs nothing and missing a call costs a trade.

---

## FIX 4 — `memoryShed` is working against you

It reloads the oldest room every couple of hours to shed memory. But a reload is the **heaviest** thing you can do to a tab — it re-downloads the entire Discord app — and every reload is a window where that room reads nothing.

With the heartbeat in place, blind rotation is mostly wasted churn. Push `SHED_EVERY_MS` from 2 hours to 6 and let the heartbeat decide what actually needs reloading.

---

## THE REAL PROBLEM UNDER ALL OF THIS — 26 Discord tabs is a lot of memory

A Discord tab runs 150–400MB. Twenty-six of them is roughly **4 to 10 GB**.

That is very likely behind more than just discards. Chrome instability, the tab massacre being possible at all, and plausibly the 8/11 bridge crashes at 10:05 and 10:30 — system-wide memory pressure doesn't respect process boundaries. Everything above treats the symptom. These two treat the cause.

### The big one: follow announcement channels into Sniper HQ

You already own **Sniper HQ**. Discord has a built-in feature for exactly this: an **Announcement channel** in another server can be *followed* into a channel of yours, and its messages arrive in your server as webhook posts.

Every room you can follow collapses from a whole Discord tab into **one line in a channel you already watch.**

This is the same move that took you from 43 rooms to 26 with the ZTRADEZ mashup — except it's a native Discord feature instead of depending on someone else's relay bot, so nothing breaks when their bot goes down.

**What to do:** go through your 26 rooms and check which alert channels are Announcement channels (they show a "Follow" button at the top). Follow every one into a `#followed-alerts` channel in Sniper HQ. Then point the extension at that one channel and close those tabs.

Two things to know before you count on it:

- Not every server uses Announcement channels — plenty use plain text channels, which can't be followed. Those keep their tabs.
- Followed messages arrive as **webhook posts**, same shape as the ZTRADEZ relay embeds. Your relay-unwrap logic in `background.js` already handles exactly this pattern — it re-books relayed calls under the real trader name — so per-trader claims, dedupe and the scoreboard keep working. That code is the reason this is cheap for you and would be expensive for anyone else.

### The smaller one: the Whop API feed you already built

`startWhopFeed` and the bridge's `/whopfeed` already pull messages with no tab at all. That's the right shape. Every room moved onto an API path is a tab that stops existing.

### What I am not recommending

Reading Discord through its gateway WebSocket with your user token would delete every tab at once. It also violates Discord's terms and is the classic way accounts get banned. Your account is the thing all 26 room memberships hang off. Not worth it.

---

## ONE MORE, CHEAP — open live rooms first

The cold-start flood is 3 tabs per 10 seconds, ~2.5 minutes by design, in whatever order `rooms.txt` lists.

Order it **live rooms first, paper rooms last.** If Chrome chokes partway through, it chokes on the rooms that can't trade anyway. Costs nothing, and it means the first 30 seconds of the open are covered by the rooms that matter.

---

## APPLY ORDER

1. **Paste 1** into `content.js` (bottom) — the heartbeat.
2. **Paste 2** into `background.js` — discard fix + heartbeat watchdog.
3. **Paste 3** — the three one-line edits: add `keepRoomsLoaded()` to the `watch-build` alarm, add `if (t.discarded) continue;` to `oneTabPerChannel`, bump `SHED_EVERY_MS`.
4. Reload the extension, restart, watch the log for `⚠ Chrome had DISCARDED` lines. **If you see those, that was rooms going dark and you never knew.**
5. Separately, at your own pace: audit the 26 rooms for followable Announcement channels.

Step 4 is the one to watch tomorrow. It tells you whether this was theory or whether it's been costing you trades.
