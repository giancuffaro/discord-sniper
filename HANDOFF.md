# HANDOFF — read this first in a new chat

If you're Claude and G has just pasted you this repo: this file is the context.
Read it, then read `README.md`, then `signals.py`. That's enough to be useful.

## What this is

G's personal reader for **somebody else's** Discord options signal room. Read
and fire, nothing else. It is deliberately separate from his other app,
MARKET SNIPER (`giancuffaro/market-sniper`) — no shared code, no shared folder,
no shared config. Keep it that way; he's said so more than once.

He is a **member, not an admin**, of that room. That's why the product is a
Chrome MV3 extension that reads the tab he already has open, not a Discord bot.
The bot path (`listener.py`, `execute.py`, `RUN.bat`) was deleted in the
consolidation pass — it needed an admin invite he can't get. It's in the git
history if that ever changes. `signals.py` and `guards.py` stayed: they're the
Python twins the parity tests check the extension against.

Channel ID: `829754942817828884`.

## The room's grammar (from his real transcript, in `samples.txt`)

| Line | Meaning |
|---|---|
| `loading AMD 7/31 480P` | get-ready only. **Never buys** — the room's own pinned rule |
| `in AMD 7/31 480P @ 3.4` | the only thing that opens a position |
| `In NVDA $210C to July 29th` | same thing, the second room's grammar. No fill price, so it warns |
| `in SPY 747C @ 3.00` | entry with **no date** — the bridge fills in this week's Friday |
| `trimming AMD @ 38%` | close. Default is out on the first trim, whatever the number |
| `Trimming @here` / `20%` / `50% @here` | a trim naming **no ticker** — resolved from the position book |
| `all out of AMD` | close. Names no contract — fill it in from the position |
| `added to SPY, new avg is 2.8` | deliberately does nothing. One contract, nothing to add to |
| `exited SPY, and back in @ 2.84` | **sell, then re-buy the SAME contract.** Not flat |
| `Loading 205 calls Friday expiration on NVDA` | loading, written back to front. Remembered per author — see below |
| `Filled 3.95 starters` | the **second half** of that entry. Buys the loaded contract at 3.95 |
| `5-6% risk.` / `205.7 risk @here` | position sizing. Same shape as a bare trim, opposite meaning — must not fire |
| `50% on SPY, great session` | chatter |
| `My avg is $3.05` / `Moving trail stop on spy to 736.5` | chatter |

`@ 38%` must never parse as a limit price of 38. There's a test for it.

`samples.txt` now holds **four** trading days, separated by `# ---` banner
comments. `replay.py` treats a banner as a day boundary and resets the daily
counter, the cooldown, the position book and the loading book — without that,
day two's entries get refused for hitting a limit day one used up.

## Architecture, and why

```
Discord tab -> extension (reads, parses, brakes) -> POST 127.0.0.1:8787 -> bridge.py -> Webull
```

The browser holds **zero credentials**. Keys live only in `settings.json` on his
PC (gitignored, chmod 600). Worst case someone owns the extension: one contract,
allow-listed symbol, market hours, daily cap. Bad afternoon, not a drained
account. Don't move credentials into the extension for convenience.

**The parser exists twice** — `signals.py` and `extension/parser.js` — because
one runs in Python and one in a service worker. They are kept in lockstep by
`test_parity.js`, not by discipline. **If you change one, change both and re-run
the parity test.** Same for `guards.py` / `extension/guards.js`.

## Webull

Options only. Futures refused three ways: auto-pick skips account ids ending in
a futures suffix (`3T0B`), an explicit account id is re-checked against the same
list, and more than one candidate is an error rather than a guess.

Needs the **$4.99/mo OPRA options data subscription** or every quote is a 403.

**There is no paper mode for options.** Live is real money, always.

Chase guard: if the live ask is >15% above the price the room quoted, skip. His
fill is not their fill.

## Before you change anything, run all four

```
python3 test_signals.py                                  # parser + brakes
python3 replay.py                                        # all four days, clock off
python3 dump_parse.py > /tmp/py.json && node test_parity.js /tmp/py.json
node test_resolve.js                                     # bare-trim resolution, JS side
```

Known-good tails, with `settings.example.json`'s `dry_run_buying_power` of 300
in play: `174 lines: 15 orders, 14 get-ready notices, 60 blocked by the brakes,
66 ignored as chatter.` and `Buying power: $300. 7 entries were skipped for
cost — the cheapest one you missed was $305.` With `--cash 0` it's 29 orders and
54 blocked. Then `Python and the extension read all 174 lines identically.` and
`The extension picks the same position Python does, and pins a bare fill price
to the same loading call.` If those move, something moved.

## How he wants to be talked to

- Condensed. He reads on a phone.
- Never hand him a raw traceback. Every error becomes a sentence saying what's
  wrong and what to do about it. That rule is applied throughout the code and he
  notices when it isn't.
- He works on Windows and runs things by double-clicking `.bat` files.
- **Do not raise the GitHub token thing.** He said "forget the tokens brother,
  leave those alone, I'll have it in mind." Respect that.
- No selfbot, ever. Logging in with his own Discord token is a ToS violation and
  gets accounts banned. It's been refused; keep refusing it.

## State as of the last session

Done: parser, guards, extension (content/background/parser/guards/popup),
`bridge.py`, `webull_options.py`, `setup_keys.py`, the one menu `.bat`, README
with the full Chrome install walkthrough, and the corrected sell-and-re-buy
behaviour.

Open:
- He needs to create the empty **private** repo `discord-sniper` on github.com
  and run menu item 9, which walks him through it.
- He has never run it live. He's on `dryrun` + OFF and should stay there for a
  full session before anything is turned on.
- Untested against the live Webull API — the SDK field names are hunted for by
  name in `webull_options.py` because they drift. First live connect may need a
  fix there.

## Update — live/dry-run toggle

The popup now has a TEST MODE / REAL MONEY button below the ON/OFF one. It talks to
`GET|POST /mode` on the bridge; the bridge owns the mode because the bridge is
the only thing that can place an order. Going live is two clicks and writes
`execution.mode` into `settings.json`, then reconnects Webull and reports the
account. Going back to test mode is one click. It is a *separate* lock from the
ON/OFF switch — both must be on for anything to fire.

A fresh machine is menu 10 (pull) then 1 (install) then 2 (keys) then 3
(preflight). Keys are never in the repo, so every PC needs them typed once.

## Update — the extension updates itself

Chrome never re-reads an unpacked extension on its own. So: `bridge.py` serves
`GET /build` — a crc32 of name/size/mtime across `extension/` — and
`background.js` polls it on a 30-second alarm. Stamp changes → `chrome.runtime.reload()`.

Three things that are load-bearing and easy to break:

1. **`content.js` is wrapped in an IIFE.** Reload orphans the copy already in the
   Discord tab and Chrome will not re-inject, so `background.js` re-injects with
   `chrome.scripting`. A second injection into the same isolated world would
   throw "Identifier has already been declared" on any top-level `const` — the
   update would look fine and the tab would silently stop reading. The IIFE plus
   `window.__SNIPER_STOP__` handles the handoff. Don't unwrap it.
2. **Never reloads while the bot is ON or mid-order** (`inFlight`). It logs
   `kind:"update"`, notifies, and applies the next time he switches it off —
   `storage.onChanged` triggers the check immediately so it doesn't wait out the
   alarm.
3. Needs `alarms` + `scripting` permissions and **discord.com in
   `host_permissions`** — content-script `matches` do not grant the host access
   `executeScript` and `tabs.query({url})` require.

Menu item 10 does the git half: `fetch`, compare, `pull --ff-only`, optionally
looping every 2 min. Refuses to pull if the working tree is dirty.

## Update — the session window

`close_time` is **`16:00`** in `guards.js`, `guards.py` and
`settings.example.json` — he asked for it directly: *"change the trading time
from 9:25am to 4pm instead, let it roll."* (It was 12:00, and 15:45 before
that; don't put either back.) That window gates **OPEN only** — CLOSE is
deliberately allowed at any hour and must stay that way, or a 16:05 exit gets
refused and he's stuck in a position overnight.

`sessionSweep()` in `background.js` (same 30s alarm as the build check) switches
him OFF once entries are done **and** `guardState.positions` is empty. It must
not switch off while holding — it logs once per day instead and the badge shows
`EXIT`. `auto_safe_after_close: false` turns the whole thing off. (The setting
keeps its old name; renaming a stored key would silently reset it on his PC.)

The popup shows current positions as contracts above the settings block, read
straight from `guardState.positions`. No new state.

Browser: Chromium family only. Firefox would need `background.scripts` instead
of a service worker, and unpacked add-ons there are temporary (gone on restart),
so it's a downgrade. He's been told this; don't reopen it without a reason.

## Update — Windows timezone crash, and the morning alarm

His bridge died on startup with `ZoneInfoNotFoundError: 'No time zone found with
key America/New_York'`. Windows ships no tz database. **Never `from zoneinfo
import ZoneInfo` directly in this project** — import `ET` from `eastern.py`,
which uses the real database when present and falls back to a hand-written US
Eastern rule when not. The fallback overrides `fromutc()` and does the comparison
in UTC (wall-clock comparison is wrong for the November fold hour); verified
minute-by-minute against `ZoneInfo` over five years, zero clock-time mismatches.
`tzdata` is also now in requirements.txt.

Morning automation lives in the menu (below). `_run_hidden.vbs` launches
`python bridge.py` with window style 0, appending to `bridge.log`; not for
double-clicking. `check_keys.py` is the ordered preflight — stops at the first
real failure, prints only the last 4 chars of the key, ends on a live options
quote to surface a missing OPRA subscription before market open, places no
orders.

## Update — one .bat, numbered menu

He asked for this directly: *"too many things I have to press... just make it in
one, step one, step two."* Fifteen `.bat` files collapsed into
**`🎯 START HERE.bat`**, a menu of 1-10. Everything else was deleted.

- The 9:25 alarm re-runs **this same file** with an argument:
  `schtasks ... /tr "\"%~f0\" morning"`. `%~f0` rather than the literal name,
  because the name contains an emoji and a mis-decoded code page would give
  Task Scheduler a path that doesn't exist — silently, at 9:25.
- `:dostart` is a `call`ed subroutine so menu item 5 and the alarm's `morning`
  path can't drift apart.
- **Don't write `^|` inside a double-quoted PowerShell `-Command`.** cmd doesn't
  treat `^` as an escape inside quotes, so PowerShell receives a literal `^|`,
  fails to parse, exits non-zero, and the bridge-readiness probe reports "did
  NOT come up" even when it did. Use `$null = ...` instead of `| Out-Null`.
- Item 9 folds in the old FIRST PUSH and FIX THE PUSH flows: no repo → the
  github.com/new walkthrough; push rejected → offers the `merge -s ours` join.
- Item 4 is idempotent — if the task already exists it offers to cancel instead
  of stacking another.
- Keep it ASCII inside. Parens in `echo` lines inside `( )` blocks must be
  `^(` `^)`.

Note: this sandbox is blocked from authenticated pushes to GitHub. The loop is
zip -> he unzips over his folder -> he runs menu item 9. Don't promise him
direct pushes; it's been tried and refused at the environment level.

## Update — the eight asks, and two more trading days

Everything below came from him directly. Each one is a constraint now, not a
preference — putting any of it back the way it was is a regression.

**The account picker.** Menu 2 lists every account on the key with its type and
makes him choose; it does not auto-pick. He wants the **margin** account, and
some people on this SDK have cash and futures accounts sitting next to it. The
futures refusal is unchanged and still belt-and-braces: id suffix *and*
`account_type`.

**`getpass` is banned in this project.** The App Secret is long and he pastes
it; `getpass.getpass` silently swallows a paste on his console, so he typed
nothing and got a confusing failure. Plain `input()` and echo it back masked.
If you ever want to hide a secret on screen again — don't.

**The live switch is popup-only.** *"dont ask this on console, i want this to be
togglable from the extension setting instead, not from cmd."* Nothing in
`🎯 START HERE.bat` or `setup_keys.py` may ask whether to go live. LIVE lives on
`POST /mode`, ON/OFF lives in the extension, and both are required.

**Chrome opens itself on the right channel.** Server `525113944239767562`,
channel `829754942817828884`, hardcoded into the start path. Never prompt for
the URL again — he answered that question once and said so.

**Out on the first trim.** `trim_action` defaults to `close`: *"I want the first
trim to be the only exit, just exit at the first trim."* He knows it leaves
runners on the table; the trim table in the README shows him the numbers. He
trades one contract, so every exit is all-or-nothing. `ignore` and `at_pct` are
still in `settings.json` if he changes his mind.

**Chase limit = skip, never chase.** Confirmed in his words: *"skip the trade if
it has run already."*

### Bare trims — `resolve_symbol` / `resolveSymbol`

The second room writes exits as `Trimming @here`, `20%`, `50% @here`. No ticker.
The parser cannot finish those — it never sees positions — so it marks
`needs_position: true, action: "CLOSE", fire: false` and the **guards layer**
fills in the ticker. Callers are `extension/background.js` (between
`parseSignal` and the `!sig.fire` return) and `replay.py`. Order:

1. The single position **that same author** opened. Every OPEN is tagged with
   its caller for exactly this.
2. The only open position — but **only if it isn't demonstrably somebody
   else's.** This clause is a real safety fix, not a nicety: without it, an
   Unraveller trim closes Brett's NVDA, a trade he was never in. Tested in both
   languages.
3. Refuse, with a sentence naming every held position and who called it.

`test_resolve.js` is the JS-side test and loads `extension/guards.js` as text
with a stubbed `chrome.storage.local`. `needs_position` and `caller` are in the
parity `FIELDS` list — if Python flags a trim for resolution and the extension
doesn't, the browser silently drops an exit Python takes.

### The weekly-expiry fallback

`in SPY 747C @ 3.00` has a strike and no date, and would have been refused
outright. Their pinned rules say contracts are weekly unless they spell out
0DTE or a date, so the date isn't missing — it's implied. `weekly_expiry()` in
`webull_options.py` returns this week's Friday, and **backs up to Thursday when
that Friday is a holiday** (July 4th week, Christmas week) rather than rolling
to the next week, because that's when the contracts actually expire. Wired in
at `bridge.py`, not the parser, so there's exactly one copy of the calendar and
no clock in the parity test. Only ever applied to an OPEN that already named a
strike; a close still fills its contract from the tracked position, never a
guess. `execution.assume_weekly_expiry: false` turns it off.

### `added to`

`added to SPY @everyone new avg is 2.8` is a deliberate no-op with an
explanatory `why`. With `max_qty: 1`, treating it as an entry buys a second
contract past his own cap. Rule 3b in both parsers.

### Veto words

The victory-lap paragraph (*"I took the same setup yesterday at 204 and 206..."*)
is full of percentages and was reaching the trim branch. Five words that never
appear in a real call now veto it: `yesterday`, `tomorrow`, `nice day`,
`conviction`, `wish i`. Add to both copies or the parity test fails.

## Update — buying power, and the 7/21 day

### The money check

His words: *"if their average is two point eight, that means that's two hundred
and eighty dollars, and I don't have two hundred and eighty dollars on the
account... if the buying power is not enough, just automatically skip the
trade."* One contract is 100 shares, so their quoted price is his cost times a
hundred. On a $300 account this refuses more trades than the parser does.

`affordability(limit, qty, have, buffer)` is a plain module-level function in
`webull_options.py`, deliberately not a method, because **three** callers have
to produce the identical sentence:

1. `Broker.afford_check()` inside `buy()`, live.
2. `bridge.place()`'s dry-run branch, against `execution.dry_run_buying_power`.
3. `replay.py`, against `--cash` or the same setting.

There is no worse way to learn what this does than to have dry run say one thing
and live say another.

Live, `Broker.buying_power()` hunts the balance endpoint by name the same way
the quote method does (Webull has renamed it more than once), caches for 8
seconds so a burst of five messages isn't five balance calls, and returns
`None` when it can't read it. **`None` means don't block.** A balance endpoint
that changed shape overnight must not quietly stop him trading — Webull will
still reject an order he can't afford; this check exists to catch it earlier and
say so in English, not to be the only thing standing in the way.

The live check runs *after* the marketable limit is computed, not at parse time:
their quoted 2.80 and the live ask are different numbers, and it's the live one
he'd be paying. `webull.keep_cash_buffer` is dollars to never touch; 0 spends
everything.

### The two-message entry

7/21 is the day the entry arrived in two halves:

```
Loading 205 calls Friday expiration on NVDA     <- contract, no price
Loading does not mean enter
... six lines of chat ...
Filled 3.95 starters @here                      <- price, no contract
```

Parser side: a line that *starts* with a fill verb, carries a bare decimal, and
has no contract and no symbol in it gets `action="OPEN"`, `fire=False`,
`needs_loaded=True`, `limit=<price>` (`RE_BARE_FILL`). It is not an order yet.

Guards side: `remember_loading()` stores each PREPARE that named a full contract
against its author; `resolve_loaded()` pins the fill to it. It requires the same
author, a full contract (symbol + strike + side), the allowed-symbols list, and
a 30-minute window (`guards.loading_window_seconds`). Anything short of that and
nothing is sent, with a sentence saying which. The entry is popped once used — a
second bare price is them averaging in, which he can't do on one contract.

Deliberately the same shape as `resolve_symbol` for bare trims: the parser never
sees state, so anything needing state is resolved at the guards layer, in both
languages, with a `needs_*` flag in the parity `FIELDS` list carrying it across.
Callers: `background.js` (right after `parseSignal`, before the `!sig.fire`
return) and `replay.py`.

### Two parser bugs the 7/21 scan surfaced

- `5-6% risk.` parsed as a bare trim and would have **sold him out of a
  position** on a sentence about position sizing. `RE_PCT_RISK` vetoes it, and
  is only consulted when the line has no trim verb, so `trimming SPY @ 45%, risk
  free now` is untouched.
- `clean_text` stripped a leading `\d{1,3}\.` to handle his numbered pastes, and
  turned `206.5 need to clear now` into `5 need to clear now`. A space after the
  dot is now required — otherwise `747.5 calls on SPY` becomes a strike of 5.

## Update — averaging in, no daily limit, and the button rename

Asked for at 2am the morning of a dry run: *"I want you to not have a limit on
the trades per day, and I want you to pretend that I have a four thousand dollar
buying power. And I do want to average in for the trades... I want everything to
be as natural as possible."*

**Averaging in** is a third instance of the existing pattern, not a special
case. The parser emits `action="ADD"`, `needs_add=True`, `fire=False` and stops
— exactly like `needs_position` (bare trim) and `needs_loaded` (bare fill
price). `guards.resolve_add` / `resolveAdd` is the only thing that can set
`fire`, because all three questions it has to answer are state: is averaging on,
are you in that trade, and how many times have you added already. `needs_add` is
on the `FIELDS` list in `test_parity.js`, so the two languages can't drift.

Four refusals, all deliberate: averaging off, not in the trade, per-position add
cap reached, or it can't tell which position they meant. The contract always
comes from `open_pos[sym]`, never from the add message — "added to SPY" names no
strike, and buying a different strike isn't averaging.

**The one that would ruin a day:** `RE_ADD` requires an add verb ("added to",
"adding", "averaging in/down/up", "new avg"). A bare "my avg is 3.05" — which
that room posts after nearly every entry — still falls through to rule 7 and
buys nothing. If you ever widen `RE_ADD` to catch bare averages, every position
doubles itself the moment it opens. There's a test pinning this.

Averaging forces contract counting through the whole stack, and each of these
was a real latent hazard fixed at the same time:

- `open_pos[sym]` now carries `qty` and `adds`; `guardRecord` mirrors it.
- `fill_from_position` sets exit qty from the position, so "all out" sells all
  of them. In `background.js` that meant moving `fillFromPosition` **above** the
  `clampQty` call — it used to run after, so a position-derived qty was computed
  and then thrown away.
- `clamp_qty` / `clampQty` take an action. `max_qty: 1` would otherwise have
  clamped a 3-contract *sell* down to 1 and left him holding two.
- `bridge.py` gained `HARD_MAX_SELL_QTY = 10` beside `HARD_MAX_QTY = 2`, for the
  same reason.

**No daily limit:** `max_trades_per_day: 0` means no limit, in both languages
and in the popup. Written as 0 rather than a big number so the log can say "no
daily limit" and mean it. Note `parseInt(x) || 6` in the popup save handler
would have silently overruled 0 — it's `Math.max(0, parseInt(x) || 0)` now.

**Dry-run buying power is 4000** in `settings.example.json`. His own
`settings.json` is gitignored and never ships in the zip, hence
`settings_quick.py` + menu **11**, which sets buying power, trades a day,
contracts per trade and averaging without him opening JSON. It reminds him the
extension keeps its own copy of the trade rules, because it does — the popup is
what actually decides.

**The button rename** came straight from him, with a screenshot: *"i dont
understand what armed means, safe means... isnt go live and armed the same
thing??? i think both buttons do almost the same thing, and theres a stop button
? pressing the regular button wouldnt stop it ?"*

He was right about the third button. `stopped` and `armed === false` hit the
same branch in `guardCheck` — one door, two locks — so **the STOP button is
gone**. The `stopped` key still exists in storage and is still honoured by
`guardCheck` and `background.js`, but nothing sets it true any more, and turning
the bot ON always writes `stopped: false` so an installation left stopped can't
strand itself with no button on screen. Don't re-add it.

The vocabulary now, everywhere including the log lines and the `.bat`:

| was | is |
| --- | --- |
| ARMED / SAFE | ON / OFF |
| LIVE / DRY RUN | REAL MONEY / TEST MODE |
| STOP | (removed — OFF is the stop button) |

Both switches render as one big word (what it IS) over a small grey line (what a
click DOES). Getting those the wrong way round is how somebody turns a bot on
while trying to turn it off. The badge is `OFF`, `EXIT`, or today's count.

Storage keys were deliberately **not** renamed — `armed`, `stopped`,
`auto_safe_after_close` all keep their old names. Renaming a key in
`chrome.storage.local` resets it to the default on his PC without telling him,
and the default for `armed` is false, which he'd discover at 9:31.

---

## Update — buy at the bid, and the order/fill split

His words: *"Webull doesn't allow market orders, so you're gonna have to go
ahead and buy the bid every time they trigger their entry... and go ahead and do
a twenty percent stop loss, just the twenty percent stop loss for now. And
whatever their trim is, as a take profit."*

Shown the concrete case — SPY 745C, bid 2.77 / ask 2.83 — and warned in writing
that on the fast calls a resting bid gets nothing and those are the ones that
run, he picked **"2.77 — sit on the bid"** anyway. On the stop he picked
**"Both"**: a real stop order at Webull *and* a watchdog in the bridge. No fixed
take-profit; their trim is the exit, unchanged.

**Why this was not a one-line price change.** Sitting on the bid means most
entries don't fill. The extension used to write the position down the moment it
sent the order, so it would have believed it held contracts nobody sold it —
and then the next trim would have sold phantom contracts and the 20% stop would
have been guarding an empty chair. So:

> **`positions.Book` in the bridge is now the authority on ownership.** The
> browser writes `pending: true` and finds out what happened by asking.

- `positions.py` — states `WORKING / FILLED / NOFILL / STOPPED / CLOSED /
  FAILED`. `HOLDING = (FILLED,)`. It polls the order, arms the stop off the
  actual fill, runs the bid watchdog, and hands out `claim()` so exactly one of
  (resting stop, watchdog, their trim) can ever sell. Every event carries a
  numeric `qty` — how many you hold *afterwards* — on purpose, so the browser
  never has to read ownership out of an English sentence.
- `GET /fills?since=N` is the reconcile endpoint. `background.js` `syncFills()`
  polls it on the alarm and for 100 seconds after any send (`watchFills`),
  flipping `pending` off, correcting `qty`, and deleting positions that ended.
- `plan_exit()` in `bridge.py` runs before every CLOSE: if the entry is still
  resting it pulls the bid and reports "you're flat on it"; if you're not in it,
  nothing is sent; and the sell is sized off `BOOK.qty_of()`, not off what the
  browser asked for.
- `build_book()` refuses to rebuild while `open_count()` is non-zero. Flipping
  live↔dry-run would otherwise orphan the watchdog that is the only thing
  holding the stop on a live position.
- The log says **ORDER IN**, never "bought". The popup says **BID IN** in amber
  and **FILLED** in green. Green means owned; that rule is load-bearing.

**Dry-run honesty.** With keys saved the bridge connects read-only and prices
against real quotes, so a test day genuinely shows which bids a seller would
have come down to. With no broker at all it assumes every bid filled and appends
"(assumed — no keys saved...)" to the line. That is the only place the dry run
flatters itself and it is marked every single time.

**New settings**, all under `execution.webull`: `entry_price: "bid"`,
`entry_fill_seconds: 90`, `stop_loss_pct: 20`, `fill_poll_seconds: 5`. The last
two are on menu **11**. The stop and the fill deadline live on the bridge side
because the browser never sees a fill price, so it couldn't enforce either.

**`test_positions.py`** covers the awkward cases: an order is not a fill; the
stop lands 20% under *your* price and not theirs; a no-fill gets cancelled and
places no stop; their exit landing on a resting bid; an add blending to 2.50 and
moving the stop, with the old stop cancelled first; a failed add leaving the
original position alone; and the watchdog selling exactly once. The fake broker
fills at the order's own limit — an earlier version answered with the current
ask for every order, which made two entries at different prices look identical
and hid the averaging bug it was there to catch.

---

## Update — the $4,000 became an account, and trims get priced

He looked at a real dry-run day and said: *"i thought we were going to pretend
that i had 4000 and we were going to follow each signal to the tee."* He was
right, and then he put his finger on the deeper thing: *"when they say trim,
pretty much you have to check the contract price at that exact time to see about
what price did they exit, thats how we would be able to see really how much
money was made or lost."*

That's the whole design of this change. Their percentage describes their trade.
Only a quote describes yours.

**The ledger.** `dry_run_buying_power` was a static affordability gate — the
same $4,000 compared against every entry, never debited, never reported. It's
now a running balance inside `positions.Book`: `_reserve` when a bid goes out,
debit on fill at the real paid price, `_unreserve` on a no-fill or a pulled bid,
credit on exit, and `available() = cash - reserved`. `wallet()` renders it for
the popup and rides along in `snapshot()`. `wallet=None` in live mode — Webull
is the only honest authority there.

Careful with the affordability gate in `bridge.py`: `available()` returning
`0.0` (depleted) and `dry_run_buying_power` being `0` (means *don't check*) are
different states and must stay different. The fallback coerces the config `0` to
`None`, then checks `if wallet is not None`.

**Pricing an exit.** `exit_price()` asks the broker for a live quote at the
moment the exit lands — the bid, since selling means hitting the bid. Falls back
to the watchdog's `last_bid`, then to `their_price * (1 + pct/100)` using the new
`pct` field on the order payload, then gives up and says so. `finish()` takes a
`price` and does the money; with no price it explicitly refuses to guess.

**Pricing a trim.** New read-only `POST /mark` on the bridge: give it a symbol,
get back the live bid, your fill, your percentage and your dollars. The
extension calls it whenever it ignores a trim on something you hold, so a log
full of their numbers becomes a log with yours in it. It sends no order and can
move no money.

**Two display bugs from his log.** A CLOSE logs with `kind: "sent"` and so
rendered as "BID IN" — a finished trade reading like an open one. Log records now
carry `action`, and the popup says SOLD for an exit. And fill lines read "SPY SPY
— filled 1 at 2.78" because the popup prints `what` in front of `why` while the
bridge's sentence already starts with the symbol; `syncFills` now strips the
duplicate off the front of the sentence rather than dropping the heading.

**Copy log.** He pasted a whole day's log as a Google search URL because a Chrome
popup can't be selected from — it closes on any outside click. There's a button
now.

Not changed, deliberately: trims are still ignored, exit is still on "all out".
He chose that against the alternative and it was worth about 4x on his log days.

## Update — v1.4.0: many traders, real trims, no limits on test

His words, from the night before he wanted it running:

> pretty much i need it to run without any limits on test mode, pretend we
> have unlimited buying power ( i know i said ) but i need to know how much
> money it needs approximately.

> so i want it to be able to enter multiple trades at once, example if brett
> enter a trade and unravler enter another one i want all to execute correctly
> and not get confused with one another..

> if an entry has been made and the avg is 2.88 and then an another add makes
> a new average ending up in 2.55 then do reverse math which would be the
> second contracts cost 2.22. does that make any sense ?

> on test mode just default and assume 5 contracts have been bought. if theres
> an add, assume 5 more. on trims.. assume they sold 3 so sell 3, another
> trim, sell 3 more, all out would be the rest.

**The book is keyed by trader now.** `positions.key_of(trader, symbol)` →
`"brett|SPY"`. Brett and Unraveler can both be in SPY on different contracts
and they are two different trades: separate fills, separate stops, separate
averages, separate exits. Same key shape on the extension side (`posKey` in
guards.js) and in guards.py, so all three books line up key for key. Every
order now carries `trader` — it's half the identity of the trade.

**Unlimited test account.** The dry-run book takes `unlimited=True`: nothing
is ever refused for money, and instead it keeps `peak` — the high-water mark
of cash committed at once (resting bids count). That's the answer to "how much
money does it need approximately". The popup prints it as "most tied up at
once". The old `$N` running account still exists and still passes its tests;
`dry_run_buying_power` in settings.json is simply not consulted on a dry run
any more.

**Test-mode sizing is the pattern, fixed on purpose:** entry = 5, add = 5,
trim sells 3, all out sells the rest (constants at the top of bridge.py).
Trims EXECUTE on a dry run now — `Book.trim()` sells the chunk, banks the P/L
per chunk, leaves the stop guarding the remainder, and a trade only counts as
a win or a loss once it's fully out. In LIVE mode trims still refuse to sell —
he hasn't said trims may touch real money, so they don't.

**The reverse math** (`implied_add_price` in bridge.py): they held n fills
averaging a, posted new average v after an add, so the add went off at
v·(n+1) − a·n. His example is the docstring: 2.88 then 2.55 → 2.22. That
number is a market fact — where the contract just traded — so it becomes the
bid on the add order, in both modes. `their_avg`/`their_units` live on the
position and `Book.their_add()` rolls them forward, so a second add solves off
the right base. If the arithmetic comes out ≤ $0.02 it's distrusted and the
order falls back to a live quote.

**The trade table.** `Book.table()` — one row per trade: who, contract, your
average, every entry, every partial exit with its P/L, state, all-out flag.
Rides on `/fills` for the popup (a "Trades" box with per-row state tags), and
is written to `days/YYYY-MM-DD.json` on every event (`save_day` in bridge.py —
rewritten as it happens, so a crash at 11am still leaves the morning on disk).
`GET /days` lists the shelf, `GET /day?date=...` serves one; the popup has a
dropdown that loads any previous day. `days/` is gitignored — it's his trading
record, not code.

**Buying power, both kinds.** `/mode` now carries `buying_power` — the real
margin account's number via `WB.buying_power()`, cached ~30s in the bridge on
top of the SDK's own cache — and the popup shows it under the mode button in
both modes. The test side shows the peak-needed figure instead of a made-up
balance.

**Dedupe got a name on it.** `signalKey`/`Sig.key()` end with the caller now,
because Brett's "all out of SPY" and Unraveler's "all out of SPY" minutes
apart are two different trades, not a duplicate. Symbol stays at index 1 —
the record purge reads it there.

**The bridge tells the extension the mode** (on `/fills` and `/mode`), and the
extension caches it as `bridge_mode`. That's what gates the test pattern; with
no bridge reachable it defaults to the test rules, which can't spend anything
anyway.

Watch out for, next session: `HARD_MAX_QTY` is still 2 in live mode and
`max_qty` in the popup still caps live buys at 1 — the 5-lot pattern is
test-only until he says otherwise. And `migratePositions` in guards.js moves
any pre-v1.4 bare-symbol position under its author's key on first read.

## Update — no more menu, keys through the popup

His ask: *"can you make the start here stuff all automatic ? i dont want to
type any numbers at all... if i have to enter the api keys in the extension to
work thats better. i like to lean more to the UI side."*

**START HERE has no menu now.** Double-click = the whole morning: first-run
pip install (detected by `import webull` failing), settings.json from the
example, a quiet best-effort `git pull --ff-only` (skipped if dirty/offline),
the 9:25 weekday alarm set idempotently — 9:25 ET converted to the PC's local
clock in PowerShell so nobody does timezone arithmetic at a prompt — the
bridge started hidden and probed until it answers, Chrome opened on the
channel, then a has_keys probe of `/mode` decides whether to tell him to paste
keys. Window closes itself. The `morning` argument still exists and the old
scheduled task still points at this same file.

**Keys go in through the popup.** New `POST /keys` on the bridge: writes
app_key/app_secret into settings.json (created from the example on a bare PC),
chmod 600, reloads, reconnects quietly, answers with the connect result. The
browser stores NOTHING — the two password inputs are wiped on success, and the
only thing that ever comes back is `key_tail` (last 4) on `/mode`. The
security shape is unchanged: credentials at rest live in settings.json on the
PC, never in Chrome. `setup_keys.py` still exists (EXTRAS option 9) and is
still the way to pick between multiple accounts by hand; the popup path picks
the options account automatically.

**EXTRAS.bat** holds everything that used to be a menu number: stop bridge,
bridge log, check_keys, tune, settings_quick, GitHub push/pull (with the
merge-ours recovery kept intact), alarm off, console keys. All "press N"
wording in the Python/JS/README was updated to match.

Watch out for: the alarm creation needs admin on some PCs — START HERE says so
in one line and carries on, since double-clicking does the same job.

## For later — two more rooms, same server

He gave these to keep on record, not to build yet ("we can polish everything
later but its pretty much the same dinamic.. only that these 2 channels dont
have clean wording"):

- Aristotle's room — channel 987515353670221834
- Midas room — channel 1144369893760831489

Same dynamic as the main room, messier wording — so before either goes live in
the watch list, run a capture day: tab open on the channel, Export chat from
the popup, and tune the parser on the real lines (samples.txt + test_parity
grow to cover them). Multi-trader keying already handles the people; it's the
grammar that needs the work. Also parked deliberately, his words: LEAPs and
multi-day swing rooms ("ok we can talk about leaps an swing later") — those
need the catch-up-on-reopen read, disk-persisted bridge positions, and
per-channel stop rules before they're safe.

## Update — the Whop recorder

He has a trader on whop.com. Same tab-reading approach, shipped RECORD-ONLY:
`extension/whop.js` is a deliberately wide net (leaf-text-block heuristic,
fingerprint dedupe, <time datetime> stamps, history flag on old stamps)
because Whop's DOM is unknown here and hashed-class/tailwind, so there's
nothing stable to hook yet. Every message it sends carries platform:"whop"
and the worker gates on that BEFORE the parser — one line, one place, where
trading would eventually be switched on after the room's export has been
studied and the reader made precise. Capture tags Whop rooms as
"whop:/path", so several Whop rooms stay separate lexicons in the export.
Next step is entirely material-driven: he opens the Whop room, scrolls back,
Exports chat, and the reader + parser get built on real sentences.

## Heads up from him — Felony's room (Whop, "High Risk")

Screenshots reviewed. Felony (@felonytrades) posts clean grammar: "Entered
AMD 520C 7/20 @ 1.75, Target 524, Stop 505". Decisions from him, verbatim
intent: "we can use his tps and stops of course" — so when this room
graduates, HIS posted stop/target replace the flat 20% stop for his trades.
Also: "i will at some point very soon include futures. i know i have to
subscribe to webull special data for this but as soon as i see money coming
in thats okay" — futures (NQ/ES shorts) are PARKED until then; note the
current code deliberately refuses futures accounts (suffix 3T0B), so futures
support is a real project, not a flag. His room also does two contracts in
one message (SPY 742P and QQQ 696P) and swings overnight — needs the
multi-day upgrades (catch-up read, disk-persisted book) before live.
