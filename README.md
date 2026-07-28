# DISCORD SNIPER

Read a signal room. Fire. That's the whole job.

This is its own thing. It does not import anything from MARKET SNIPER, it does
not share a folder with it, and it does not touch your Webull setup. You can
delete this folder tomorrow and the trading app won't notice.

---

## Two ways to read the room, and why the extension is the one you want

You told me this is **somebody else's signal room**. That's the whole problem,
and it has exactly two honest answers.

**The bot route** needs an admin of that server to invite your bot. Discord
enforces this and there is no way around it. If the channel happens to be an
*Announcement* channel you can Follow it into a server you own and read the
mirror — that works, and it costs a few hundred milliseconds of relay.

**The extension route** sidesteps the whole thing. You already have permission
to read that room — you're sitting in it. The extension reads the messages that
are already painted on your screen in a normal Discord tab. It never logs in,
never asks Discord for anything, and sends no request Discord wasn't already
expecting from your browser. Nobody's approval is needed, it works on any
channel type, and it's the same speed as your own eyes.

Both are in this folder. The extension is what you asked for and it's the one
I'd run.

> Note on the thing people find on YouTube: a "selfbot" that logs in with your
> own account token. It works and it's a straight ToS violation — accounts get
> banned for it, usually right when it's been running long enough to matter.
> It isn't here and it won't be.

---

## How it's wired

```
Discord tab  ->  extension (reads, decides, applies the brakes)
                       |  POST http://127.0.0.1:8787/order
                       v
                 bridge.py on your PC  ->  broker
```

The browser deliberately holds **no broker credentials**. Anything that can
read your extension folder can read everything in it, so account keys don't go
there. The extension only ever sends a plain description of a trade — "OPEN
AAPL 345C 7/31 x1 @ 3.40" — and `bridge.py` is what actually places it. Worst
case, someone who got into the extension can make it place a one-contract order
on a symbol you allow-listed, in market hours, up to your daily cap. Bad
afternoon, not a drained account.

---

## Install the extension (5 minutes)

1. Open `chrome://extensions` and turn on **Developer mode** (top right).
2. Click **Load unpacked** and pick the `extension` folder inside this one.
3. Pin the crosshair icon to your toolbar.
4. Start the bridge: double-click **BRIDGE.bat**. Leave that window open —
   close it and nothing can trade.
5. Open Discord **in Chrome** (not the desktop app) and go to the signal
   channel. Leave the tab open.
6. Click the extension icon → Settings. Your channel ID is already the default
   (`829754942817828884`). Set your symbols and your caps, hit Save.
7. Leave it on **SAFE** for a full session first. It reads everything and logs
   what it *would* have done, and sends nothing.

The badge on the icon tells you where you stand at a glance: `SAFE`, `STOP`, or
today's trade count in orange when it's armed.

**One thing to know:** it only reads messages that arrive *while the tab is
open*. When you open a channel, Discord paints the last hour of history into the
page — that's history, not calls, and it's ignored on purpose. Don't expect it
to react to something that was posted before you sat down.

---

## The three buttons

- **ARM / SAFE** — SAFE reads and logs, ARMED spends money. Nothing else.
- **STOP** — the panic button. Survives closing the popup, closing the tab, and
  Chrome putting the extension to sleep, because it's written to storage rather
  than held in a variable. `bridge.py` has its own version: drop an empty file
  called `STOP` in this folder and it refuses everything.
- **Export chat** — downloads every message the extension has seen. Send me that
  file and I'll tune the reader to your room's exact wording.

---

## How it reads your room

Built directly around your actual transcript, not generic options-room phrasing:

| They post | It does |
|---|---|
| `loading AMD 7/31 480P` | get-ready notice. **Never buys.** That's the room's own rule — their pinned message says DO NOT BUY IN on loading. |
| `in AMD 7/31 480P @ 3.4` | **buys.** This is the only thing that opens a position. |
| `trimming AMD @ 38%` | depends on your trim setting, below. |
| `all out of AMD` | **closes.** |
| `exited SPY, and back in @ 2.84` | closes you and warns you'll be flat — re-enter by hand if you want to follow. |
| `50% on SPY, 30% on AAPL, great session` | ignored. Chatter. |

`@ 38%` is never mistaken for a limit price of 38. There's a regression test for
that specific one because it's the mistake that would hurt most.

### The trim decision — this is the one real judgement call

You trade one contract, so you can't trim. What you *can* choose is which of
their trims you take your money on. Your own session says a lot:

| They trimmed at | It ran to |
|---|---|
| AMD +38% | +118% |
| SPY +10% | +110% |
| AAPL +9% | +30% |

Exiting on their first trim would have cut every one of those short. So the
default is **hold until "all out"**. The other two modes are there if you
disagree: exit on first trim, or exit at/above a % you pick.

---

## The brakes

Every one of these exists because it's a way an automated signal bot actually
loses money:

- **Max contracts** — one, until you trust it. The parser reading `10x` off a
  message doesn't override it, and `bridge.py` caps it a second time.
- **Max trades/day** — a room having a wild day, or a compromised account
  spamming, can't drain the account.
- **Position tracker** — two admins calling the same trade five minutes apart is
  normal in a signal room. Without this you'd buy it twice. It also refuses to
  sell something you're not in, because at most brokers that isn't a no-op — it
  opens a short.
- **Dedupe** — the same call posted twice is one trade. Cleared per-symbol on a
  real fill, so a genuine re-entry after an exit still goes through.
- **Cooldown** — nothing fires back-to-back inside the window.
- **Message age** — a twenty-minute-old entry is not a trade you want to chase.
- **Market hours** — no *new* positions outside 09:30–15:45 ET. Closes are always
  allowed, because being stuck in something is worse.
- **Allowed symbols** — it can only trade tickers you listed. Enforced twice,
  once in the browser and again in the bridge.
- **Trusted callers** — leave blank for anyone, or name the admins you follow.

---

## What's in the folder

**Extension** (`extension/`)
- `manifest.json` — Chrome MV3 manifest.
- `content.js` — reads the open Discord tab. The only part that touches Discord.
- `parser.js` — decides what a line means.
- `guards.js` — the brakes. State lives in `chrome.storage.local`, not memory,
  because Chrome shuts a sleeping service worker down whenever it likes.
- `background.js` — ties them together and posts to the bridge.
- `popup.html` / `popup.js` — the dashboard.

**On your PC**
- `bridge.py` + `BRIDGE.bat` — receives orders, holds the credentials, places
  the trade. Listens on 127.0.0.1 only, so nothing outside this machine can
  reach it.
- `settings.example.json` — copy to `settings.json` and fill in.

**The bot route, if you ever want it**
- `listener.py`, `signals.py`, `guards.py`, `execute.py` — same logic, running
  as a real Discord bot. `RUN.bat` starts it.

**Checks**
- `test_signals.py` — the parser and the brakes, against real lines from your
  room. `TEST.bat` runs it.
- `replay.py` — runs your whole session through in order with the clock off, so
  you can see every order it would have placed. Try `python replay.py --trim close`
  to see the other setting.
- `test_parity.js` — proves the browser and Python read all 55 of your lines
  identically. Two copies of the same logic in two languages is how a bot ends
  up buying in one and not the other on a Tuesday for no visible reason.
  `python dump_parse.py > py.json && node test_parity.js py.json`

---

## Keeping it up to date

Same as MARKET SNIPER. Double-click **🔄 UPDATE.bat** and it pulls whatever I've
pushed. If the extension files changed, open `chrome://extensions` and hit the
reload arrow on Discord Sniper so Chrome picks it up.

`settings.json` is gitignored, so your keys never leave your PC and an update
never overwrites them.

---

## Still to decide

**Which broker this fires into.** You said it must not be linked to MARKET
SNIPER, so `bridge.py` is on `dryrun` and there's a clearly marked spot where
the real backend goes. Tell me the broker and I'll write it.
