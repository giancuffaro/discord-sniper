# ROOMS, TABS AND READERS — mechanics

The mechanics behind the rules in HANDOFF.md, moved here 9/15 so HANDOFF stays a
rules core (under 30 KB). The rule is in HANDOFF; the HOW, the numbers and the
history-with-numbers are here. REPLACE, DON'T STACK applies: edit in place.

Owner code: extension/rooms.txt (the one room list), extension/background.js (tabs,
reaper, whopSelfHeal, roomSchedule, probeOne, revokeCheck, RELAY UNWRAP), extension/
content.js, extension/popup.js, bridge.py (/rooms, /build, apply_room_rules).

## One switch per room — rooms.txt, the popup, who may open and close a tab

- ROOMS — ONE SWITCH PER ROOM (9/9 evening, G: "a list of all the rooms
  we've been to and the option to open the tab or not; if I selected to
  open it I obviously want it live"). The popup's Channels tab lists every
  room in extension/rooms.txt grouped as the file groups them, with its
  state: ON = tab open + read + trades LIVE; OFF = no tab, nothing read,
  nothing traded (the one-line reason sits above it in the file and shows
  dim in the popup); LAPSED = off because the sub ran out, probed daily.
  There is NO testing/paper state any more. The switch writes rooms.txt
  through the bridge (POST /rooms rewrites that one line in place), the
  extension re-reads the file and opens/closes the tab; the other Chrome
  profile sees the change within 30 s (pollRoomsFile) and follows for its
  own lane's rooms. START HERE opens only `on` rooms. CLOSING A TAB BY
  HAND IS NOT A BENCH — START HERE and a flip reopen every `on` room; the
  switch is the only bench. Benched rooms are never deleted from the file.
  WHOSE TABS THE REAPER MAY CLOSE (9/10). ONLY tabs the extension itself
  opened (`_OURS`). A tab a HUMAN opened is never closed, whatever URL it is
  on — it ate G's Discord Settings tab twice before this, and sparing the
  ACTIVE tab is no fix (his tab stops being active when he clicks away).
  WHO MAY OPEN A TAB (9/10, G: "get rid of auto opening tabs UNLESS it's
  the start sniper"). Exactly three things, and nothing else:
    1. START HERE.bat, through its one-shot open-rooms request
    2. the popup's Channels switch (his click)
    3. whopSelfHeal() — kept on his call so the Whop lane can revive its own
       4 tabs; its dedupe MUST read pendingUrl and query the whole origin, or
       a still-LOADING tab is missed and a heal pass turns 4 Whop tabs into 8
  roomSchedule() opens nothing; it only CLOSES at 4:30, which is what stops
  the overnight pings.
  probeOne() opens a lapsed room off-hours, then closes that tab seconds
  later in a finally — a door-knock, not an open.
  NO ACCESS = OUT OF SERVICE (9/10, G: "do not open the tab if we don't have
  access"). revokeCheck() reads the tab titles it already has; a room whose
  title says "No Access" is now written to rooms.txt as `lapsed` through the
  bridge and its tab closed, not merely warned about (RWGates warned for
  three weeks while opening a blank tab every morning). `lapsed` not `off`:
  the daily probe keeps knocking, so it un-lapses itself if the sub returns.
  6th field = the room's RULES (9/9 evening): comma flags `bare` (an entry
  with no verb counts, AND its tokens may arrive in any word order — see
  WORD ORDER below), `dotdate` (the expiry is written with a DOT — Maguro's
  "$slv 63c 10.16 2.35" is Oct 16 at $2.35; per-room because elsewhere that
  number IS the price), `pivot=NQ` (the room trades ONE future and writes only
  the last digits of the level — Chika's "short 195 pivot" is NQ 29,195; the
  BRIDGE expands it against a live quote, the browser never guesses a price),
  `readonly` (read the room and write down what we WOULD have done, send
  nothing — NOT the same as `off`, which reads nothing at all),
  `sym=SPX` (symbol to assume when the call names none).
  The `spx` flag was DELETED 9/10 on G's instruction — see NO SPX->SPY.
  The bridge DERIVES dot_date_channels / entry_no_verb_channels /
  default_symbol_channels from these (apply_room_rules, at boot and on
  every write) — settings.json no longer holds those lists. Rules count
  whatever the room's state (shabs/eli are off but relayed via OWLS).
  Set from the popup: the pills on each Channels row (SPY-proxy / bare /
  24h).

## Room hours, channels and controls

- ROOM HOURS: `on` rooms use tabs 9:15–16:30 ET on weekdays unless
  marked `always` (futures rooms). roomSchedule closes daytime tabs after
  hours; it does not reopen them at 9:15. START HERE once in the morning
  creates a one-shot, lane-aware open-rooms request (≤3 tabs per pass, 6 s
  apart). Whop alone self-heals missing tabs. A Discord tab closed by hand
  stays closed until the next START HERE or a room-switch change. The last
  browser tab is never closed.
- CHANNELS / CONTROLS: callers are shown within their verified room, win
  rate unavailable unless backed by evidence; no separate Callers / Needs You
  tab (G). Honey Drip caller switches keep their room keys; other observed
  accounts are identity rows only. GET/POST /callers and /rooms serve them.

## START HERE, relays, embeds, tab health, Whop, voice, silence

- rooms.txt = THE channel list (tabs + trading, one file). START HERE IS
  FULLY UNATTENDED (G, 9/9: "no input from me"): every run drops a one-shot
  open-rooms.request; the bridge serves its token on /build; each browser's
  extension then opens every rooms.txt room it lacks a tab for (its own
  lane, ≤3 per 30 s tick) until a pass opens none, then marks the token
  done. So a warm start (Chrome already open) fills in the missing rooms
  without closing Chrome; a cold start opens them all itself (~2.5 min
  paced flood; count tabs after, not during) and launches the announcer.
  Between runs NOTHING opens rooms — a tab he closes by hand stays closed.
  No prompts: git fails fast instead of asking for a credential
  (GIT_TERMINAL_PROMPT=0 / GCM_INTERACTIVE=never; a failed push keeps
  local work and skips the mirror), and every Chrome launch carries
  --hide-crash-restore-bubble so "Restore pages?" never waits on a click.
  The only inputs left are the ones no script may do: a Discord/Whop login
  if a profile is logged out, and Webull keys in the popup.
- Relay rooms (one bot account relaying many traders): ZTRADEZ was cut 9/9
  (no active ZT room). OWLS all-alerts (1449226651064991806, "OWLS Capital
  Clanker") is active — slug map shabs-sky-alerts→shabs, eli-alerts→eli,
  muggzone-options→MuggZone, giul-heatseeker→Giul, florida-man,
  common-stock, jon-and-kian, ab→AbTrades, tt, eva, neal. RELAY UNWRAP in
  background.js re-books under the real trader (footer "#slug" /
  possessive), so per-trader claims, dedupe and scoreboard hold; shabs + eli
  direct rooms retired 9/9 (covered by OWLS).
- EMBED RACE: bots post the call in an embed that hydrates after the row
  paints; content.js keys SEEN on id+length so the hydrated read re-emits.
- TAB HEALTH: content/Whop reinjection clears the old observer and heartbeat; background reinjects before any reload and logs every reload. Room opening is paced, memory shedding touches at most one inactive room per cycle, and active/voice tabs are protected. Extension maintenance jobs run in one ordered sweep; normal message delivery stays event-driven. Chrome uses Profile 2 for Discord and Profile 6 for Whop; `whop-profile.txt` pins the folder.
- WHOP: four `whop.com/<business>/exp_<id>/app/` tabs are read only from Profile 6. The extension is installed there. `whopSelfHeal()` and `_whop_loop.bat` restore missing Whop tabs/profile with bounded strikes; Discord tabs still reopen only from START HERE’s one-shot token. Felony’s Zoom uses the web client in that profile; one manual Sniper-icon click grants tab audio capture.
- VOICE: ears transcribe always (Deepgram, diarized S0/S1). Voice ENTRIES
  ON (9/2); voice EXITS irrelevant under entries-only. Two-stage: "loading
  X" = staged (4-min shelf, per speaker); fires on that speaker's "I'm in /
  filled / average is X". AUTO-JOIN clicks a LIVE badge's voice/stage
  channel (one join per 10 min). Glossary in ai_reader (pulls=puts,
  Qs=QQQ, one-d-t=1DTE …). Typed copy of a voice fire = echo, skipped 5 min.
- No timed quiet-room alarm (removed 9/15): the content-script heartbeat
  (3 missed beats ≈ 90s → reload), departments.health_tick() and deadman.py
  are the checks. Watchdog reloads stale/black-shell tabs.

## The page and the popup

- THE PAGE (v3.5.80, 9/9 evening, G: "make the popup an html page — it's
  super small now"): the SAME popup.html opened as a normal tab —
  chrome-extension://iaokjlndnmamhgmgkoldkhjehmdkginj/popup.html?page=1
  (the "⤢ page" button in the popup opens or focuses it; bookmarkable).
  No 800×600 cap; every tab is a card on a 3-column grid, same code and
  same 1-2 s bridge polling. One file, two sizes — never a second
  dashboard. IS_PAGE in popup.js
  guards the popup-only bits (window.close after a room jump).
- POPUP (v3.5.77, 9/9 evening): the rooms list paints FIRST in render()
  and any exception in the rest of the popup is written INTO the Channels
  pane ("popup error (…): …") — never a blank pane again. esc() is
  module-level, one copy. If G reports a broken popup again, the red
  line under the rooms is the diagnosis; ask for it. Claude-in-Chrome CANNOT
  read the popup (another extension's page; screenshots/JS/console all
  refused). Its id is the one in THE PAGE url above — Chrome hashes the
  folder path as UTF-16LE, so both profiles get the same one.
