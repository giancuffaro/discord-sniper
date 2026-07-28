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

## Installing it in your browser — the long version

Do this once. It takes about ten minutes and nothing here can spend money until
the very last step, which you don't do today.

**1. Get the folder onto your PC.** Unzip `discord-sniper.zip` somewhere you'll
find again — `C:\discord-sniper` is fine. Not Downloads, not the Desktop; you're
going to point Chrome at this folder permanently and if you move it later the
extension breaks.

**2. Open the extensions page.** In Chrome, type `chrome://extensions` in the
address bar and press Enter. You can't get there from a normal link — Chrome
blocks that on purpose.

**3. Turn on Developer mode.** Top-right corner, a toggle. Flick it on. Three
new buttons appear at the top left: *Load unpacked*, *Pack extension*, *Update*.

> "Developer mode" sounds like something you shouldn't touch. All it means is
> "let me install an extension that didn't come from the Chrome Web Store."
> That's what this is. Chrome will pop up a "Disable developer mode extensions?"
> warning every so often — click the X, not Disable.

**4. Click Load unpacked.** A folder picker opens. Go into `C:\discord-sniper`
and select the **`extension`** folder — the one *inside* it, not the outer one.
Click Select Folder.

You should now see a **Discord Sniper** card with a crosshair icon. If you see a
red *Errors* button instead, click it, screenshot it and send it to me.

**5. Pin it.** Click the puzzle-piece icon in Chrome's toolbar, find Discord
Sniper, click the pin. The icon now sits next to your address bar with a little
badge on it. That badge is your status at a glance: `SAFE`, `STOP`, or today's
trade count in orange when it's armed.

**6. Install the Python side.** Back in `C:\discord-sniper`, double-click
**SETUP.bat**. It installs what the bridge needs and makes you a `settings.json`.
If it complains about Python, install it from python.org and **tick "Add Python
to PATH"** on the first screen of the installer — that box is the whole reason
this ever fails.

**7. Start the bridge.** Double-click **BRIDGE.bat**. A black window opens and
says `listening on http://127.0.0.1:8787` and `mode: dryrun`. **Leave it open.**
Close that window and the extension can read the room but can't trade. It has to
be running whenever you want to trade — starting it is part of your morning, the
same as opening the chart.

**8. Open Discord in Chrome.** The actual Chrome tab, not the Discord desktop
app — the extension can only see a real browser tab. Go to the signal channel
and leave it sitting there.

**9. Point it at the room.** Click the crosshair icon → **Settings**. Your
channel ID is already filled in (`829754942817828884`). Check your allowed
symbols and your caps. Hit **Save**.

**10. Now leave it alone for a session.** SAFE mode. It reads every message and
writes down what it *would* have done, and sends nothing anywhere. Come back at
the end of the day, open the popup, read the log. If what it says lines up with
what the room actually did, then we talk about arming it.

### Two things that will confuse you if I don't say them now

**It only sees messages that arrive while the tab is open.** When you open a
channel, Discord repaints the last hour of history onto the page. That's history,
not calls — it's ignored on purpose. Don't sit down at 10:15 and expect it to
react to the 9:47 entry.

**Chrome puts extensions to sleep.** That's normal and it's handled — every bit
of state lives in storage, not in memory, so it wakes up knowing what it's
holding and how many trades it's done. But it means the popup log is the truth,
not your memory of what you saw earlier.

---

## Firing into Webull — options only

The bridge talks to Webull's official API. Options only. It will not touch
futures, and that's enforced rather than promised: the account it picks has to
be an options account, an account id ending in a futures suffix (`3T0B`) is
refused outright, and if you have more than one candidate account it stops and
asks rather than guessing.

**What you need from Webull first**

1. In the Webull app: **Menu → More → OpenAPI**. Create an App. Copy the
   **App Key** and **App Secret**.
2. Turn on the **options market data subscription** ($4.99/mo) for the API. Not
   optional — without it, every options quote comes back 403 and nothing can
   price an order. The bridge tells you this in plain English if it happens.

**Putting the keys in**

Double-click **KEYS.bat**. It asks for the key, the secret (which doesn't show
on screen as you type), an optional account id, and your chase limit. It writes
them to `settings.json` with locked-down permissions. That file is gitignored —
it never gets committed, and an update never overwrites it.

The last question is *"Turn live Webull trading on now?"* and the default is
**no**. Say no. Say no for at least a week.

**The chase limit** is the one setting worth understanding. The room posts
`in SPY 7/28 745P @ 2.76`. By the time you see it, the ask might be 2.80, or it
might be 3.40. Their fill is not your fill. If the ask is more than **15%** above
the price they quoted, the bridge skips the trade instead of buying the top. It
says so in the log. That's not a bug and it will happen — a skipped trade is the
cheapest trade there is.

> **There is no paper mode for options.** Not in this bot, not at Webull, not
> anywhere. Stocks have one; options don't. The instant you switch mode to
> `webull` and hit ARM, every fill is real money. That's why the default is
> `dryrun` and why arming is a separate deliberate act.

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
| `exited SPY, and back in @ 2.84` | **two orders off one line.** Sells the contract, then buys the *same* contract straight back at the new price. You end up still holding it. |
| `50% on SPY, 30% on AAPL, great session` | ignored. Chatter. |

`@ 38%` is never mistaken for a limit price of 38. There's a regression test for
that specific one because it's the mistake that would hurt most.

### The two lines that don't name a contract

`all out of AMD` and `exited SPY, and back in @ 2.84` never say which strike or
which expiry, because everyone in that room already knows. A broker doesn't. So
before either one leaves the browser, the missing pieces are filled in from the
position you're actually holding — and if that somehow comes up empty, the bridge
refuses to send anything rather than guess at a contract nobody called.

The re-entry runs both legs inside `bridge.py`, back to back, so the gap between
selling and buying back is as small as it can be. If the sell fills and the
re-buy gets refused — say the ask ran past your chase limit in between — it tells
you exactly that, in those words, and says **"You are FLAT on SPY."** You should
never have to work out which half went through.

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
- `webull_options.py` — the Webull backend. Builds the OCC contract symbol,
  checks the live ask against your chase limit, prices a marketable limit, and
  refuses futures accounts. Every error it can hit is translated into a sentence
  that tells you what to fix.
- `setup_keys.py` + `KEYS.bat` — puts your API keys in without you ever opening
  a JSON file and getting a comma wrong at 9:29.
- `settings.example.json` — copy to `settings.json` and fill in. `SETUP.bat`
  does this for you.

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

## Going live, when you're ready

In order, and not before you've done the one above it:

1. A full session on **SAFE**, bridge in `dryrun`. Read the log at the end.
2. `python replay.py` on a fresh export of your room, so you can see every
   order it would have placed against what actually happened.
3. `KEYS.bat`, answer **yes** to live. Restart `BRIDGE.bat` — it should say
   `mode: webull` and `Webull: connected, options account ...`.
4. Still SAFE in the browser. Confirm the bridge connects and picks the right
   account before you arm anything.
5. ARM it, with `max_qty` at 1 and `max_trades_per_day` at 2 or 3, on a quiet
   day you can watch.

Keep the STOP button in reach: in the popup, or an empty file called `STOP` in
this folder, which the bridge checks on every single order.
