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

The extension is what's in this folder now. The bot route was here too and has
been taken out — it can't run without an admin inviting it, so it was 300 lines
you were never going to use. It's still in the git history if that ever changes.

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

## There is one button

`🎯 START HERE.bat`. That's the only file you ever double-click, and it has no
menu any more — no numbers, nothing to pick. Every run does the whole morning
by itself, in order:

- installs anything missing (first run on a PC only)
- quietly pulls the latest build down from GitHub
- sets the 9:25 weekday alarm if it isn't set, working the timezone out itself
- starts the bridge, hidden
- opens your signal channel in Chrome

then tells you the one thing only you can do (the two switches in the popup)
and closes itself. Run it twice, nothing doubles — it notices what's already
done and leaves it alone. After the first run, the 9:25 alarm presses the
button for you, so most days you press nothing at all.

Your Webull keys don't go in at a console any more either. They go in through
the extension popup — Settings, two boxes, one save button. They're sent once
to the bridge on your own PC (127.0.0.1, never the internet), written into
`settings.json` with owner-only permissions, and the browser forgets them the
moment they're sent. The popup only ever shows the last four characters.

The rare stuff — stopping the bridge, reading its log, pushing to GitHub,
turning the alarm off — lives in `EXTRAS.bat`. Day to day you never open it.

The only thing START HERE can't do for you is Chrome — loading the extension is
a Chrome thing and Windows can't click through it. That's the next section, and
it's also once.

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
badge on it. That badge is your status at a glance: `OFF` in grey, or today's
trade count in orange when it's on.

**6. Run START HERE.** Back in `C:\discord-sniper`, double-click
**🎯 START HERE.bat**. It installs what the bridge needs, makes you a
`settings.json`, starts the bridge hidden, sets the morning alarm and opens
your channel — all by itself. If it complains about Python, install it from
python.org and **tick "Add Python to PATH"** on the first screen of the
installer — that box is the whole reason this ever fails. To shut the bridge
down later: `EXTRAS.bat`, option 1.

**7. Put your keys in.** In the extension popup, open Settings, paste your
Webull App Key and App Secret into the two boxes, hit save. The popup tells you
straight away whether they connected.

**8. Open Discord in Chrome.** The actual Chrome tab, not the Discord desktop
app — the extension can only see a real browser tab. Go to the signal channel
and leave it sitting there.

**9. Point it at the room.** Click the crosshair icon → **Settings**. Your
channel ID is already filled in (`829754942817828884`). Check your allowed
symbols and your caps. Hit **Save**.

**10. Now leave it alone for a session.** Leave the top button on **OFF**. It
reads every message and writes down what it *would* have done, and sends nothing
anywhere. Come back at the end of the day, open the popup, read the log. If what
it says lines up with what the room actually did, then we talk about turning it
on.

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
futures, and that's enforced rather than promised: a futures account is refused
outright, both by what Webull calls it and by an account id ending in a futures
suffix (`3T0B`).

Most people have more than one account — a margin one, a cash one, sometimes a
futures one — and nothing good comes of the bot guessing which. Saving keys
through the popup picks the options account automatically and refuses futures;
if you ever need to pick by hand, `EXTRAS.bat` option 9 prints the list:

```
  Which account should it trade?

    1) MARGIN   1234567890         <- saved now
    2) CASH     9876543210
    3) FUTURES  5555555555 3T0B    (futures — this bot will refuse to use it)

  Number [1]:
```

Pick the margin one. It's written into `settings.json` and the bridge uses that
exact account and no other — the picker and the bridge read the account list
through the same code, so they can't end up disagreeing about what's what.

**What you need from Webull first**

1. In the Webull app: **Menu → More → OpenAPI**. Create an App. Copy the
   **App Key** and **App Secret**.
2. Turn on the **options market data subscription** ($4.99/mo) for the API. Not
   optional — without it, every options quote comes back 403 and nothing can
   price an order. The bridge tells you this in plain English if it happens.

**Putting the keys in**

Menu, number **2**. It asks for the key, the secret, which account, and your
your keys. It writes them to `settings.json` with locked-down permissions.
That file is gitignored — it never gets committed, and an update never
overwrites it.

**The secret is typed in plain sight, and that's deliberate.** It used to be
hidden as you typed, which sounds safer until you meet the actual problem:
Windows blocks paste into a hidden prompt, so a 60-character secret had to be
typed by hand, and a typo doesn't announce itself — it comes back later as a
login failure you can't explain. Now you paste it (right-click in the black
window) and read it back. Close the window when you're done.

**Nothing in there asks whether to go live.** That switch is one click in the
extension popup, where you can see which way it's set instead of trying to
remember what you answered in a terminal three days ago.

**The chase limit is gone.** It used to skip an entry when the ask had run
too far past the room's price. Deleted on his word — "no filters wanted. id
like to follow everything to the tee as they do." The entry still sits on
the bid, which is what protects the price actually paid.

> **There is no paper mode for options.** Not in this bot, not at Webull, not
> anywhere. Stocks have one; options don't. The instant you switch mode to
> `webull` and hit ARM, every fill is real money. That's why the default is
> `dryrun` and why arming is a separate deliberate act.

---

## How your order actually goes in — sitting on the bid

Webull takes no market orders on options. Every buy is a limit, and this one is
a limit **at the bid** — you're not paying the offer, you're posting a price and
waiting for a seller to come down to you.

That's the cheapest way in, and it has one consequence that shapes everything
else in here:

> **Sending an order and owning the contract are two different events, and the
> second one often doesn't happen.**

The room calls SPY 745C and the screen says bid 2.77 / ask 2.83. You bid 2.77.
If somebody sells at 2.77 you're in six cents cheaper than the man who crossed
the spread. If the call runs the second it's posted, nobody is selling at 2.77
any more and you get nothing — and the ones that run are exactly the ones you'll
miss. That's the trade-off, and it's a real one. If it costs you too many good
calls, the setting to change is `entry_price` in `settings.json`: `"bid"` today,
`"ask"` pays the offer plus a 2% buffer and fills nearly every time.

**Your bid gets 90 seconds**, then it's pulled. Not because 90 is a magic
number — because an order left resting all day fills at 3:55pm into a trade they
called at 9:40 and were out of by 10:05. You'd be buying their exit. Menu **11**
changes it.

**The 20% stop goes on the moment you fill**, measured off *what you paid*, not
off the price they posted. Fill at 2.77 → stop at 2.22. It's held two ways, and
only one of them is ever allowed to sell:

- a real stop order resting at Webull, so it still works with your PC shut
- a watchdog inside the bridge window watching the bid, so it still works when
  Webull refuses the stop, or when a contract gaps straight through the trigger

Their trim is still your take-profit. Nothing changed there — first trim and
you're out, same as before.

> **20% on options premium is tight.** It's a normal amount of movement on a
> slow morning. Expect it to take you out of trades that would have come back.
> Menu **11** widens it whenever you want.

**What you'll see on the screen.** The popup now tells you which of the two
things has happened:

- **BID IN**, amber — the order is out, nobody has sold to you yet
- **FILLED**, green — you own it, at this price, with the stop at that price
- **NOFILL** — nobody came down, the bid was pulled, you're flat on it
- **STOPPED OUT**, orange — it hit the stop and it's gone

Green means you own it, amber means you don't yet. That's the whole colour rule.
A missed fill is now an ordinary line in the log, not a sign something broke.

The awkward case is covered too: if they post their trim while your bid is
*still sitting there*, the bid gets pulled and nothing is sold, because there was
nothing to sell. The log says exactly that.

---

**One thing to know:** it only reads messages that arrive *while the tab is
open*. When you open a channel, Discord paints the last hour of history into the
page — that's history, not calls, and it's ignored on purpose. Don't expect it
to react to something that was posted before you sat down.

---

## The test account, the trade table, and what a trim is now

**Test mode has no money limit, on purpose.** Every call the room makes goes
through, at a fixed size — an entry is **5 contracts**, an add is **5 more**, a
trim **sells 3**, and "all out" sells whatever's left. Nothing is ever refused
for being too expensive. Instead the bridge keeps the one number a cap could
never give you: the **most cash that was tied up at any one moment** of the
day, resting bids included. That's what the popup means by "most tied up at
once", and it is the honest answer to *how much money would I need to follow
this room for real*. Run a week of test days and the biggest of those numbers
is your funding requirement.

**Several traders at once.** A trade is a *trader plus a ticker* now. If Brett
calls SPY and Unraveler calls SPY five minutes later, those are two positions —
different contracts, different averages, different stops — and they never touch
each other. Brett's "all out" sells Brett's contracts and leaves Unraveler's
exactly where they were. Every line in the log and every row in the table says
whose trade it is.

**Trims sell now (in test).** "Trimming here" from an admin sells 3 of your 5
and keeps the trade open, with the stop still guarding what's left. The sale is
priced off the live bid when there's a quote, and off their percentage on their
own average when there isn't — and the log says which. A trade only counts as a
win or a loss once the last contract is gone. In **real-money mode trims still
don't sell anything** — that stays switched off until you say otherwise.

**The reverse math on adds.** When they add and post their new average, the
average itself is not a price anyone can trade at — it's a blend. But it hides
the real number: if they were in at 2.88 and the add moved them to 2.55, the
contract they just bought cost 2.55×2 − 2.88 = **2.22**. The bridge does that
arithmetic the moment the message lands and puts the bid in at the answer,
because that's where the contract actually just traded. Each further add solves
off the updated average, automatically.

**The trade table.** The popup has a *Trades* box: one row per trade — the
contract, who called it, what you paid, every partial sale as it happens, and
whether it's live, bid in, or all out, with the running dollars on the row.
It's the scoreboard; the log underneath stays the diary.

**Previous days.** The bridge writes the whole table to a dated file on your PC
as the day happens (`days/2026-07-29.json` and so on), one per trading day.
The dropdown on the Trades box loads any of them, so "how did Tuesday actually
go" is two clicks, and the files are plain JSON for backtesting.

**Both buying powers.** Under the mode button: your real Webull margin buying
power, read live from the broker, shown in both modes. The test side shows the
peak-needed figure instead of a made-up balance.

**Copying the log.** There's a *Copy log* button under the log box. A Chrome
popup closes the moment you click anywhere else, so you can't select text out of
it — the button puts the whole thing on your clipboard as plain text, oldest
first, with the day summary at the top. If Chrome blocks the clipboard it
saves it as a file instead.

---

## Setting it up on a different computer

Everything except your keys is in GitHub, so a new PC is the same menu:

Get the folder onto it (unzip, or clone), double-click **🎯 START HERE.bat**,
then **10** to pull the latest code down, **1** to install, **2** for your keys,
**3** to prove they work. Then load the `extension` folder into Chrome at
`chrome://extensions`, which is the one step no batch file can do for you.

Your keys are deliberately **not** in GitHub, so every machine needs them typed
once. That's the price of them not being in a public-ish place, and it's worth
paying.

---

## The two switches

There are two, they are not the same thing, and both have to be on before a
single dollar moves. Each one answers a different question:

- **ON / OFF** — *is the bot working at all?* OFF reads the room and writes down
  what it would have done. ON means it acts. This is your stop button: it's
  written to storage rather than held in a variable, so it survives closing the
  popup, closing the tab, and Chrome putting the extension to sleep. `bridge.py`
  has its own version of the same thing — drop an empty file called `STOP` in
  this folder and it refuses everything.

- **TEST MODE / REAL MONEY** — *fake money or your money?* This one lives on the
  bridge, not in the browser, because the bridge is the only thing that can
  actually place an order. Switching to real money takes two clicks — one to
  ask, one to mean it — and it's written to `settings.json`, so restarting the
  bridge doesn't quietly put you somewhere you didn't expect. Switching back to
  test mode is one click and instant, because the safe direction should never
  make you confirm anything. If your keys aren't saved yet it says so instead of
  pretending.

That split is the whole point: ON + TEST MODE is a full day of watching the room
and placing pretend trades, which is exactly how you find out whether you trust
it. Turning one on never turns the other on.

The colours are worth one line. Green means it's running, grey means it's
asleep, and red is kept for one thing only — the button that spends your money.
If there's nothing red on that screen, nothing on it can cost you anything.

There used to be a third button called STOP, sitting next to ON/OFF. It set a
separate flag that did precisely what OFF does — the same door with a second
lock on it — so it's gone. Turning it off *is* stopping it.

**Export chat**, down in Settings, downloads every message the extension has
seen. Send me that file and I'll tune the reader to your room's exact wording.

Under those buttons is a box showing **what you're in right now**, as an actual
contract — `IN SPY 7/28 745P — since 09:41` — and it says **Flat** when you're
not in anything. That isn't new bookkeeping; the position tracker already had to
know this, or it couldn't turn "all out of SPY" into an order. It's just on
screen now. The log underneath is the history: every entry, every exit, every
call it refused and the reason why. Your Webull app is still the source of truth
for fills and P/L — this box tells you what the *extension* thinks it's in, which
is the number that matters when you're wondering why it did or didn't fire.

---

## The trading day

- **New trades are allowed from 09:30 right through to 16:00 ET**, the closing
  bell. Both times are in settings. It used to cut off at midday on the theory
  that the room is done by then; it isn't always, and a good afternoon call
  being refused by a clock is a worse trade than no trade. So it runs the whole
  session now.
- **Exits are never time-boxed at all.** If they call the exit at 16:30, it
  fires. Being stuck in a position because of a clock would be a much worse bug
  than being late to an entry.
- **It switches itself OFF when the session's over** — but only once you're
  **flat**. If you're still holding something at 16:00 it stays ON, tells you
  why, and shows a blue **EXIT** badge meaning "not hunting entries any more,
  just waiting to get you out". Once that position closes, it switches itself
  off.

So the normal day is: it starts itself at 9:25, you turn it on, and you find it
OFF again in the evening. Nothing is left on overnight.

Chrome will still put the extension to sleep between messages — that's normal
for MV3 and it wakes on the next one. All the counters live in storage, not in
memory, precisely so that nap can't reset anything.

---

## Starting it in the morning without doing anything

Menu, number **4**, once. From then on, every weekday at 9:25am this PC starts
the bridge and opens your signal channel in Chrome by itself. Come back to **4**
any time and it offers to cancel it.

The bridge runs **hidden** — no black window on your screen. Everything it would
have printed goes into `bridge.log` instead, so if it ever fails to start there's
still a record of why (that's number **7**). Because there's no window to close,
number **6** is how you shut it down.

Number **5** is the same morning routine on demand — press it whenever you sit
down. Safe to press twice; it checks whether a bridge is already running and
leaves it alone if so, and it doesn't just launch and hope, it waits and confirms
the bridge is actually answering before it says it's up.

The first time it runs it'll ask for your channel's web address — open Discord in
Chrome, click into the signal channel, copy what's in the address bar, paste it
in. It saves it and never asks again.

The alarm **arms nothing and goes live on nothing.** It starts the machinery,
that's all. ARM and LIVE stay off until you press them. And the PC has to be
awake — a sleeping laptop doesn't run alarms, so if it sleeps overnight just
press **5** when you sit down.

---

## If the bridge won't start

**`ZoneInfoNotFoundError: No time zone found with key America/New_York`** — this
one bit you already. Python asks Windows for the world's timezone rules and
Windows doesn't ship them. Everything here runs on New York time, so it couldn't
start at all.

It's fixed two ways now, deliberately belt-and-braces, because this is the one
clock the whole thing depends on. `tzdata` is in requirements.txt, so START
HERE's first run installs the proper database. And `eastern.py` has the US Eastern rule written
out by hand as a fallback, so even on a PC where that install was never done, it
starts anyway. The fallback was checked minute-by-minute against the real
database across five years — including both daylight-saving switchovers — and
gives an identical clock at every point.

Run START HERE once on this PC and it'll pick up `tzdata` properly.

---

## Checking it'll actually work

Menu, number **3**. It goes through everything that has to be right before a trade
can go out, in order, and stops at the first real problem instead of burying it:
the clock, `settings.json`, whether your key and secret are saved, which mode
you're in, the SDK, whether Webull recognises the key, which account it picked,
that the account **isn't** your futures account, and then it asks for a real
options price — which is the one that catches people out, because the key can be
perfect and every quote still comes back refused if the $4.99/mo options data
subscription isn't active on the API. It finishes by printing your limits back
at you.

It places no orders and it can't. The most it does is ask for a price. Your key
is never printed — just the last four characters, enough to recognise it.

---

## Which browser

**Chrome, or Edge.** Edge, Brave, Opera and Vivaldi are all Chromium underneath —
same folder, same "Load unpacked", same everything, just `edge://extensions`
instead of `chrome://extensions`. The self-reload works there too.

**Firefox would need a rewrite, and it'd be worse.** Firefox doesn't run MV3
background service workers the way Chrome does, so `background.js` would have to
be restructured. And unpacked add-ons load there as *temporary* — they're gone
every time you restart the browser, so you'd be reinstalling this every single
morning. There's no version of that which beats what you have.

---

## How it reads your room

Built directly around your actual transcript, not generic options-room phrasing:

| They post | It does |
|---|---|
| `loading AMD 7/31 480P` | get-ready notice. **Never buys.** That's the room's own rule — their pinned message says DO NOT BUY IN on loading. |
| `in AMD 7/31 480P @ 3.4` | **buys.** This is the only thing that opens a position. |
| `trimming AMD @ 38%` | **closes.** First trim is your exit — see below. |
| `all out of AMD` | **closes.** |
| `exited SPY, and back in @ 2.84` | **two orders off one line.** Sells the contract, then buys the *same* contract straight back at the new price. You end up still holding it. |
| `In NVDA $210C to July 29th. Stop below $206.` | **buys.** The other room's grammar: `$` in front of the strike, expiry written out in words at the end. |
| `20%` / `Trimming @here` / `50% @here` | **closes** — a percentage with no contract in the line is a trim. Which position it means is worked out below. |
| `Loading 205 calls Friday expiration on NVDA` | get-ready notice, written back to front. Still never buys — but it's remembered, because of the next line. |
| `Filled 3.95 starters` | **buys** the contract from that loading call, at 3.95. Same admin, within half an hour, or nothing is sent. |
| `5-6% risk.` / `205.7 risk @here` | ignored. That's how much they're willing to lose, not a gain. Read as a trim it would sell you out of the trade. |
| `My avg is $3.05` | ignored. That's their fill, posted after the fact. |
| `Moving trail stop on spy to 736.5 now` | ignored. Talk about the trade is not the trade. |
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
| NVDA +12% | +125% |
| SPY +27% | +50% |

Exiting on their first trim would have cut every one of those short — and you
asked for it anyway, which is a defensible call. You trade one contract, so
every exit is all-or-nothing; taking a certain +10% beats watching a +38% round
trip back to zero because you were in a meeting. **The default is now: get out
on their first trim, whatever number it is.** No second guess, no target to
hit, no holding runners you can't actually hold.

The other two modes are still there in `settings.json` under `trim_action` if
you change your mind: `ignore` holds until they say "all out", and `at_pct`
waits for a trim at or above a percentage you pick.

### When they trim without saying what

The second room writes trims as a bare number — `Trimming @here`, `20%`,
`50% @here`, `Out of 80% of my position`. No ticker anywhere. Everyone in the
channel knows which trade they mean; a broker doesn't.

So the ticker gets worked out from what you're actually holding, in this order:

1. **The position that admin opened.** A bare trim from Brett closes Brett's
   trade. Every position is tagged with who called it, exactly for this.
2. **The only thing you're in**, if there's just one and it isn't somebody
   else's — if Brett put you in NVDA and *Unraveller* trims, that's about a
   trade you were never in, and taking it would close the wrong thing.
3. **Nothing.** If it's still ambiguous, no order is sent and the log names what
   you're holding and who each one came from, so you can close it yourself in
   the Webull app.

Guessing which position to close is how you end up flat on the winner and still
holding the loser, so it doesn't guess.

### When the entry arrives as two messages

Some days they split it. First the contract:

> **Loading 205 calls Friday expiration on NVDA**
> Loading does not mean enter

then six lines of chat, then the actual order:

> **Filled 3.95 starters**

Neither half is a trade on its own. The loading line is explicitly not one —
that's the room's own rule and it's obeyed — and the fill line names no ticker,
no strike and no side, just a price. Put together they're one entry, so that's
how they're read: the loading call is remembered against the admin who posted
it, and the next bare fill price from that admin buys **that** contract at
**that** price.

It has to be the same admin, and it has to be within half an hour. If neither
lines up, nothing is sent and the log says which — a price with no contract
behind it is the easiest possible way to buy something nobody called. A second
bare price from the same admin — "Filled 4.20 more" after "Filled 3.95 starters"
— is them averaging in, so it goes down the averaging path below rather than
opening the same trade twice.

### It checks you can afford it

One options contract is **100 shares**. When they say their average is 2.80,
that is **$280** out of your account, not $2.80. On a small account that decides
more trades than the parser does.

So before any entry goes out, the cost is checked against what you actually
have. If it doesn't fit, the trade is skipped on purpose and the log says
`that one costs $395 and you've got $300 to spend. Skipped on purpose — no
order was sent and you're not in it.` No order is placed, and you're not left
wondering whether you're in it.

Live, it asks Webull for the real number before every entry. In dry run there's
no broker to ask, so it uses `dry_run_buying_power` in `settings.json` — set it
to whatever is actually in the account and the dry run starts telling you the
truth about your week. Same sentence either way, on purpose.

Two knobs, both in `settings.json`:

- `execution.dry_run_buying_power` — no longer consulted on a dry run: test
  mode is unlimited on purpose and reports the peak-needed figure instead
  (see "The test account" section above). The knob is kept for `replay.py --cash`.
- `execution.webull.keep_cash_buffer` — dollars to never touch when live. `50`
  means an entry is skipped once it would leave you under $50.

Run `python replay.py --cash 300` to see it against your own transcripts. On
the four days in `samples.txt` a $300 account takes 16 of the 30 orders and has
to pass on 7 entries, the cheapest of which was $305. The same four days at
$4,000 take every single one.

---

### When they add to what they're already in

> **added to SPY @everyone new avg is 2.8**

They bought more, and their average moved. Whether you follow them in is a
setting, because it's a second contract of real money on a trade you're already
holding: `guards.average_in`, or **When they add to a trade** in the popup
settings. Off, it's written in the log and nothing is sent. On, it buys one
more.

Four things will stop it, and all four are on purpose:

- averaging is switched off;
- **you're not in that trade** — there's nothing to average into, and opening it
  fresh off an add message isn't the same trade they're talking about;
- you've already added `max_adds_per_position` times on it;
- it can't tell which position they meant. An unnamed "adding more" when that
  admin has two positions open gets nothing, same as an unnamed trim.

The contract always comes from **what you're holding**, never from the add
message. "added to SPY" doesn't say which strike, and buying a different strike
isn't averaging — it's a second trade wearing the wrong name.

The one that matters most is what it *doesn't* count as an add. The room posts
"my avg is 3.05" straight after almost every entry. There's no add verb in it,
so it stays a non-order. If that read as an add, every position would double
itself the moment it opened.

Once you're holding more than one, the popup says `IN SPY 7/31 745C x2`, and an
exit sells **all** of them. Selling one would leave you still in the trade while
the log says you're flat — so the contract cap applies to buying only, in the
extension, in `guards.py` and again in `bridge.py`.

---

## The brakes

Every one of these exists because it's a way an automated signal bot actually
loses money:

- **Contracts per trade** — one, until you trust it. The parser reading `10x`
  off a message doesn't override it, and `bridge.py` caps it a second time. It
  caps what you *buy* only: an exit is always allowed to sell everything you're
  holding, or averaging in would leave you quietly still in the trade.
- **Trades a day** — a room having a wild day, or a compromised account
  spamming, can't drain the account. Set it to **0** and there's no limit,
  which is a deliberate choice and not an accident: on a small account the
  buying-power check is the real limit anyway.
- **Max adds per position** — the ceiling on averaging in. Two means you can end
  up holding three of something and no more. This is what stops a $280 trade
  turning into $1,120 while you're not looking.
- **Position tracker** — two admins calling the same trade five minutes apart is
  normal in a signal room. Without this you'd buy it twice. It also refuses to
  sell something you're not in, because at most brokers that isn't a no-op — it
  opens a short.
- **Dedupe** — the same call posted twice is one trade. Cleared per-symbol on a
  real fill, so a genuine re-entry after an exit still goes through.
- **Cooldown** — nothing fires back-to-back inside the window.
- **Message age** — a twenty-minute-old entry is not a trade you want to chase.
- **Market hours** — no *new* positions outside 09:30–16:00 ET. Closes are always
  allowed at any hour, because being stuck in something is worse.
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
- `🎯 START HERE.bat` — the only file you double-click. No menu — it does the
  whole morning by itself.
- `EXTRAS.bat` — the rare stuff: stop the bridge, read its log, GitHub push and
  pull, alarm off, console keys.
- `_run_hidden.vbs` — one line, launches the bridge with no window. START HERE
  runs it for you; don't double-click it yourself.
- `bridge.py` — receives orders, holds the credentials, places
  the trade. Listens on 127.0.0.1 only, so nothing outside this machine can
  reach it.
- `positions.py` — the book of what actually filled. Since your entry sits on
  the bid, "an order went out" and "you own it" are different events, and this
  is the only file that knows which one has happened. It also arms the stop,
  watches the bid, and makes sure exactly one thing is ever allowed to sell a
  position — the resting stop, the watchdog, or their trim, never two of them.
- `webull_options.py` — the Webull backend. Builds the OCC contract symbol,
  checks the live ask against your chase limit, prices a marketable limit, and
  refuses futures accounts. Every error it can hit is translated into a sentence
  that tells you what to fix.
- `setup_keys.py` — puts your API keys in without you ever opening a JSON file
  and getting a comma wrong at 9:29. The popup's key boxes use the same file.
- `check_keys.py` — the preflight. EXTRAS.bat option 3.
- `settings_quick.py` — the numbers that change a day: pretend buying power,
  trades a day, contracts per trade, averaging in, the stop loss %, and how long
  your bid may sit there. EXTRAS.bat option 5. Press Enter on any question and it
  leaves that one alone.
- `eastern.py` — New York time, with the rule written out by hand so Windows
  not shipping a timezone database can't stop the bridge.
- `signals.py` / `guards.py` — the Python twins of `parser.js` / `guards.js`.
  Not run day to day; they're what the tests test.
- `settings.example.json` — copy to `settings.json` and fill in. START HERE
  does this for you.

**Checks**
- `test_signals.py` — the parser and the brakes, against real lines from your
  room.
- `test_positions.py` — the one that checks a resting bid never gets mistaken
  for a position: an order isn't a fill, a fill puts the stop 20% under *your*
  price, an entry nobody takes ends as NOFILL with the order pulled, an add that
  fills moves the stop to the blend, and when the stop trips exactly one thing
  sells. `python test_positions.py`
- `replay.py` — runs your whole session through in order with the clock off, so
  you can see every order it would have placed. Try `python replay.py --trim close`
  to see the other setting, or `python replay.py --cash 300` to see which entries
  your account couldn't have paid for.
- `test_parity.js` — proves the browser and Python read all 174 of your lines
  identically. Two copies of the same logic in two languages is how a bot ends
  up buying in one and not the other on a Tuesday for no visible reason.
  `python dump_parse.py > py.json && node test_parity.js py.json`
- `test_resolve.js` — the same check for the three things the parser can't
  finish on its own: a trim with no ticker, a fill price with no contract, and
  an add on a position it can't see. All three get finished at the guards layer,
  so they need their own test. This one proves the
  browser picks the same position Python does — including refusing when the trim
  came from an admin who didn't open it — and pins a bare "Filled 3.95" to the
  same loading call.
  `node test_resolve.js`

---

## Keeping it up to date

**It updates itself now.** You don't press anything.

Chrome, left alone, would never notice you changed a file. An extension loaded
with "Load unpacked" gets read off your disk once, and after that Chrome only
looks again if you hit the reload arrow or restart the browser. There's no
setting for that — real auto-update is a Chrome Web Store feature, and this tool
is never going near the store. So it does it itself:

- **bridge.py** watches the `extension` folder and hands out a fingerprint of it.
- **The extension** asks for that fingerprint every 30 seconds. When it changes,
  it reloads itself — which is the reload arrow, pressed from the inside — and
  puts a fresh reader back into your Discord tab without you touching it.
- START HERE quietly pulls anything new down from GitHub on every run;
  EXTRAS.bat option 7 does it by hand. Say **Y** to the
  "keep watching?" question and it stays open checking every 2 minutes.

Run all three and the loop closes: change a file on github.com from your phone
in bed, and about two minutes later your PC is running it. You'll see a blue
**UPDATED** line in the popup log when it happens.

Two things it deliberately won't do:

- **It won't reload while the bot is ON.** Reloading takes about a second, and
  for that second nothing is reading the room. Fine at 7am, not fine at 9:32.
  While it's on it holds the update, tells you it's waiting, and applies it the
  moment you turn the bot off.
- **It won't pull over the top of unpushed work.** If it finds edits on this PC
  that aren't on GitHub, it stops and tells you to push first (EXTRAS.bat option 6).

The bridge has to be running for any of this — it's the part that can see the
disk. If it's off, nothing updates and nothing breaks; it catches up when the
bridge comes back.

`settings.json` is gitignored, so your keys never leave your PC and an update
never overwrites them.

---

## Going live, when you're ready

In order, and not before you've done the one above it:

1. A full session with the bot **ON** and the bridge in **TEST MODE**. Read the
   log at the end.
2. `python replay.py` on a fresh export of your room, so you can see every
   order it would have placed against what actually happened.
3. Open the extension popup and switch the bottom button to **REAL MONEY**.
   That button is the only place real money gets turned on — nothing on the
   black console screen ever asks you, so you can't switch it by accident while
   setting something else up. Then EXTRAS.bat option 2 to read what the bridge said: you
   want `mode: webull` and `Webull: connected, options account ...`.
4. Turn the bot **OFF** while you check that. The two switches are separate and
   both have to be on before a single order goes out — so confirm the bridge
   connects and picks the right account before the bot is on.
5. Turn it **ON**, with contracts per trade at 1, trades a day at 2 or 3, and
   averaging in switched off, on a quiet day you can watch.

Keep the STOP button in reach: in the popup, or an empty file called `STOP` in
this folder, which the bridge checks on every single order.
