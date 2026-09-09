# HOW TO GET INTO FELONY'S MORNING ZOOM (so the ears can hear him)
Proven 2026-09-09 10:55 ET, live, first try. The scheduled task
`felony-live-whop-check` (9:12 AM ET weekdays) does exactly this; this page
is the human copy so anyone can do it by hand in two minutes.

## Why the browser, not the Zoom app
The extension transcribes with Deepgram by capturing a Chrome TAB's audio
(tabCapture). The Zoom desktop app is invisible to it. So the meeting must be
open as the Zoom WEB client — `us02web.zoom.us/wc/join/<id>` — in a Chrome tab.
Any zoom.us tab that is playing audio is picked up automatically; nothing to
switch on.

## Which Chrome
The "Sniper Whop" profile. Tell-tale: a whop.com tab SURVIVES there. In the
Discord profile the sniper extension closes any Whop tab within seconds
(lane guard) — if your tab vanishes, you're in the wrong browser.
(Claude-in-Chrome on 9/9: "Browser 1" = Whop, "Browser 2" = Discord.)

## The fast path (his meeting is recurring)
1. Open a tab: `https://us02web.zoom.us/wc/join/89312529658`
2. "Enter Meeting Info" — name is remembered as "g". Click **Join**.
3. You're in when the tab title is "Live Trading × FST" and the banner says
   "You are viewing Felony Trades's screen".
If Zoom says the ID is invalid or the meeting hasn't started, use the slow
path — and if the ID has changed, write the new one here and in the task.

## The slow path (find today's link)
1. `https://whop.com/firststeptrading/exp_d8xHKjPXPlW9Lk/app/` — FST's
   "Zoom Links & Events" page. A live session shows **Live!** and a card
   "Live Trading W/ First Step Trading · 9:15 AM · Zoom (Online)".
2. Click the card. Scroll the right pane down to **Meet at Zoom — We are
   live! Join meeting**. (It's inside an iframe — you have to click it, a
   script can't read the link.)
3. "Join meeting" opens a new tab `us02web.zoom.us/j/<MEETING_ID>#success`
   that wants the desktop app. Don't. Take the ID from the URL and go to
   `https://us02web.zoom.us/wc/join/<MEETING_ID>` instead — the web client.
4. Name "g" → **Join**. Passcode, if ever asked, is on the event page.

## FIRST — is a Zoom tab already up with working ears?
Check `reads.log` for "🎙 Live Trading × FST" lines in the last 3 minutes. If
yes, DON'T join again. Learned 9/9: a second join as the same name bumps the
first session — G's own tab had the ears working from 10:30, the second join
at 10:57 killed it, and the second tab never captured anything.

## The ears need ONE grant per tab (Chrome's rule, not ours)
Tab-audio capture (tabCapture) only works on a tab the user has invoked the
extension on — clicked the Sniper icon with that tab in front, or the tab is
in front with that grant. G's 10:26 tab worked because he'd clicked the icon
on it (saving the Deepgram key) three minutes earlier. A tab opened by a
script has no grant: since v3.5.74 the extension LOGS "Chrome won't let the
ears take it yet — bring that tab to the FRONT or click the Sniper icon on it
once" and retries the moment either happens. So after joining: confirm
reads.log is filling within a minute; if not, ONE click on the Sniper icon
with the Zoom tab in front starts it. That click is the only thing that can't
be automated.

## Once in
- Audio is connected automatically (bottom bar shows only "audio setting").
  If you ever see a **Join Audio** button, click it.
- Never turn on camera or mic. Never click anything else in Zoom.
- Leave the tab open all session. Close it after he ends (~11:15 AM).

## His pattern
- Posts the event on the FST Zoom Links & Events page; live ~9:15 AM ET,
  scheduled 9:15–11:15. Occasionally YouTube instead — the Livestreaming
  page `https://whop.com/firststeptrading/exp_LfnIHe3fltMP2K/app/`; an
  audible YouTube tab is captured the same way.
- Recurring meeting ID as of 2026-09-09: **89312529658** (us02web).

## How Felony trades (from the 9/9 live — worth knowing before his calls)
- HOURLY OPEN is his trigger. His words: "New hourly: we open, break the
  previous candle's high and hold — that's the long. We open, dump, break
  that candle's low — back into lows." He counts down to the top of the
  hour on air ("twenty minutes till", "fourteen minutes"). Expect his
  entries in the first minutes after :00 — that is when the ears matter.
- STOP = the previous candle's extreme, not a %. "If we break that
  candle's high, we're out of here." "Use a stop above that same high."
- TARGET = the day's low/high. "That was our target — 762.50, low of day."
  He trims there; "take breakeven" means he closed flat.
- He talks in index LEVELS (764, 762.50) and futures roots (NQ/ES/YM/RTY),
  and reads relative strength out loud ("NQ rejecting, ES popping") — that
  is commentary, not an order. A real call names a contract or "I'm in".
- Guests: S1/S2 are other traders on the call; S0 (host) is Felony — the
  extension books S0's calls under his name from the first word (v3.5.75).

