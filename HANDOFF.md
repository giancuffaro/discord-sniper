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

## Update — futures, built and parked behind THE switch

His ask: *"start working on that so the only thing i hqve to do later is just
flip a switch"*. Done. The switch is `execution.futures_enabled` in
settings.json + `futures_enabled` in the extension settings — the popup's
"Futures calls (NQ / ES)" select sets BOTH (POST /config keeps the bridge
side in step). Off by default, and off means: his futures calls are parsed,
priced and logged, and nothing fires in either mode.

What's live behind it:
- **Parser** (both languages, parity at 183 lines): "Short NQ @ 28660 Stop
  29700 Target 28550" → OPEN, kind=future, direction, THEIR stop/target
  captured. Futures trims speak dollars ("$1,100 a contract") → sig.usd.
  Options entries also capture their Target/Stop levels now (recorded only).
- **Book**: kind/mult/direction on every position. Futures P/L = points ×
  multiplier × direction (FUT_MULT table in bridge.py — NQ $20, ES $50...).
  No premium out, nothing reserved, peak untouched. Their stop sits on the
  record; no watchdog (no quote feed yet), exits fire on their calls.
- **Dry run**: sized 3 contracts, trims sell 1 (his trim/2nd trim/runner
  pattern). Exit price back-solved from his $-per-contract. Smoke-tested on
  his real NQ day: +$1,100 / +$1,700 / +$2,200 = +$5,000, exits landing
  exactly on his posted levels.
- **Live**: webull_futures.py — front-month resolution + order placement via
  the _try_calls probing idiom, ONE contract hard-pinned, refuses loudly when
  endpoints don't answer. Cannot be exercised until the data subscription
  exists: THE FIRST LIVE FUTURES ORDER IS A SUPERVISED EVENT. Expect to tune
  endpoint names against the real SDK that day.

Known wart: replay.py treats futures prices as premium (a "skipped, cost
$748500" line) — replay is options-math only for now.

## Update — the filters are deleted, not hidden

His words: "no stop making different rules, just change the existing ones. or
just remove that box all together because i dont want to block anything...
no filters wanted. id like to follow everything to the tee as they do." And:
"delete what i dont want from the coding so its less for you to read."

Gone from the CODE, not defaulted: trim_action/close_at_trim_pct (a trim
always parses as TRIM; the follow-them logic sells its share), average_in and
max_adds_per_position (adds always follow; only "you're not in it" refuses),
max_trades_per_day (every call counts), max_qty (live buys are pinned to ONE
contract in clampQty/clamp_qty as a sizing safety — raise on purpose, not by
knob), and every allowed-symbols REFUSAL (bridge, parser entry check,
resolve_add, resolve_loaded). The bridge's ALLOWED set is deleted entirely.

allowed_symbols survives ONLY as vocabulary — it helps the parser read a
lowercase ticker ("40% in spy now"); nothing is ever refused off it. The
extension merges his old saved list with a built-in VOCAB list in cfg().

New parser rule that fell out of this: "Full sold nvda close to 25%" — FULL +
an exit verb + a bare % = complete exit, not a trim. Without it the trim rule
would sell 3 of 5 on a call that means "I'm out".

The popup lost the whole filter block; what's left is: on/off, test/real,
channels, callers, futures switch, keys, bridge url, save/export/copy.
Still deliberate: live-mode trims refuse to sell real contracts (test mode
sells 3); that flips when he says so, not by a setting.

## Update — the chase limit is deleted too

His quote of the setup_keys prompt, then "remove this". Gone from
webull_options.buy() (the Refused branch), setup_keys.py (the question),
settings.example.json (the key), and the parser's no-price warning was
reworded since there's no chase limit to reference. If the room is in it,
he's in it, whatever the ask has done since — the bid-sitting entry style is
still what protects the price actually paid.

## Update — ON is the resting state

His words: "i want the bot to be on 24/7 as soon as you execute it, beucase
you can only trade during market hours anyway. but if i want it to go live
with an account with money then yes have to activate it for now."

Done: armed defaults true everywhere; ensureArmed() in background.js arms
once per install (marker `armed_once`) so the OFF button still sticks when
pressed on purpose. sessionSweep (the after-close auto-disarm) is DELETED —
the market-hours guard already refuses entries outside 09:30–16:00 ET and
weekends, and exits were never time-boxed. auto_safe_after_close is gone from
defaults and settings.example. TEST/REAL stays exactly as it was: manual,
two-click confirm to go live — that's the activation he means.

## Update — first capture day read, quick fixes shipped

His first Export chat (7/29, all four rooms) taught us:
- Main room grammar: confirmed working (the GOOGL triple).
- Aristotle: "PREP AAPL 350 C 7/31" = loading; entries are bare contracts
  with NO price ("QQQ 668 0 day puts @here lightly"); exits "Fully out" /
  "Take profits leave runners". Needs an entry rule (bare contract + no
  verb = OPEN at the ask) and "N day" as an expiry shape — build after one
  more capture day. Room stays RECORD_ONLY.
- Midas: prose + underlying levels ("Loaded 342.5c cons", "added off
  342.30", "If 341.85 doesn't hold exiting longs"), ticker implied from
  earlier messages. Hardest room; needs context-carry. Stays RECORD_ONLY.
- Whop: capture caught only the storefront — the chat feed lives in an
  embedded frame. Fixed: whop.js now runs all_frames:true, plus a junk
  filter built from the storefront lines. He needs a logged-in tab and a
  re-export.
Fixes shipped: capture dedupe (every Discord line was doubled — same
author+text within 60s of the last few entries is skipped), RE_LOADING now
also matches loaded/prep/prepping/prepped (all GET READY, never buy), and
new veto words "chance of"/"probability"/"odds of" — Brett's "71.7% chance
of no cut" was one step from reading as a trim. Samples at 189, parity green.

## Update — Aristotle's grammar built from his full corpus; room moved to SHADOW

He sent two weeks of KingBeeAri's chat and confirmed the reading: "@here"
means HE IS ALREADY IN — fire immediately, his separately-posted price is
the benchmark, not a limit. New grammar, in both parsers (parity at 208):
- PREP = loading (already in). Bare "In @here [starters/lightly...]" fires
  on that admin's last PREP via needs_loaded, at the market; a trailing
  "@1.31" becomes the limit. RE_BARE_IN is ANCHORED — the bare in is the
  whole message or it's chatter.
- "QQQ 668 0 day puts @here lightly" = bare-contract entry: fires only when
  stripping contract + sizing filler (RE_FILLER) leaves NOTHING. "N day"
  parses as NDTE, including between strike and kind (RE_CONTRACT_DTE).
- "Out" / "Fully out" (anchored, RE_BARE_OUT) = exit resolved by trader;
  "out of half" = TRIM. "Out of JNJ -33%" = full exit WITH pct (percents can
  be negative now). "Cutting" is an exit verb. took some/take a/grabbed are
  entry verbs.
- Recap guard: >=3 percentages in one line = scoreboard, not a call.
  New vetoes: "supposed to". New NOT_TICKERS: OPEX ORB HOD LOD EMA VWAP ATH
  RSI FIB PREP LOL SMH LFG PDT.
- UPPERCASE tickers always resolve now (NBIS, JNJ); the vocabulary list only
  unlocks lowercase.
- pickHeld/_pick_held: several positions from the same trader -> the NEWEST
  wins. His bare "12%"/"Out"/"Added a lil" is always the active scalp, never
  the swing from Tuesday. Tests updated to this rule.
Aristotle is out of RECORD_ONLY into SHADOW (background.js): parsed for
real, logged as "would have read this as: ...", never trades. One clean
shadow day = graduation. Midas stays RECORD_ONLY (prose + underlying
levels, ticker implied from earlier messages — needs context-carry).
Known gaps, deliberate: "Prep SPY 744 C tomorrow exp" dies on the
"tomorrow" veto (PREP-only loss); two-ticker trim lines ("15% CRWV / 40%
JNJ") only act the first; his percent-stream (93/107/132/146%) would trim
on each until the position runs out.

## Update — Aristotle LIVE in test; Midas grammar built, room in SHADOW

His words: "actually dont put him in shadow mode, go ahead and test him out,
im not going to go live until next week anyway... ill double check tomorrow
everything and mention if i see anything weird." So: Aristotle's channel now
TRADES in test mode. Trading channels are baked into cfg() (main +
Aristotle) and merged with whatever's in the popup box, so graduation never
depends on a settings box. Midas moved into the SHADOW set — parsed for
real, "would have read this as..." in the log, nothing fires.

Midas grammar (from a month of his room, parity at 228):
- "Loaded $SPY 744c [0dtes]" = PREPARE; "0dtes"/"1dtes" plural parses; "In
  $SPY 749p tomorrow exp" — "tomorrow" is OFF the veto list and "tomorrow
  exp" = 1DTE (the recap guard covers the victory laps that veto protected).
- Loose IN: "In @here my add level will be 744.30" / "In at 1.34" / "In
  754c cons" — starts with in, NOT prose (blocklist: no/not/the/rush/...,
  word-bounded — "at" once died on the "a"), carries a cue (decimal,
  starters, cons, 0days, fill, add level). Premium-sized decimals (<100)
  become the limit; 744.30 is a chart level and is ignored.
- "Small Accts, $KO 85c 7/17 starter 1.38" — bare-contract entry now accepts
  a lone leftover price (<100) as the limit; the filler class no longer eats
  the dot out of "1.38".
- "All positions closed" / "out of all trades" / "sold everything" — new
  sig.all: background walks every position of that trader and closes each
  (respects OFF). "Took some off" = trim. "1.26 new avg" alone = their
  bookkeeping, NOT a second add (was worth 5 phantom contracts per update).
  "won't lose more than 15%" — lose/losing/lost/drawdown joined the
  risk-percent guard.
Still known-thin for Midas: his corpus is entry-rich and exit-poor; asked
him for July 16-29 and for losing days (stop-outs). His add levels are
underlying prices — we don't act on them (no underlying feed), we buy once
at signal.

## Update — everyone testing; Midas fill-confirmations learned

His words: "dont shadow, go ahead and put everyone testing. not sure what
you meant by 'real test money' hope its only test mode for everyone." It is:
test mode = the pretend account, nothing reaches Webull until HE flips REAL
MONEY (two-click). SHADOW set is now empty; main + Aristotle + Midas all
fire pretend trades; all three channels baked into cfg().channel_ids.

Second Midas batch (Jul 17-27) added: RE_FILL_CONF — "1.97 fill @here",
"Filled @here", "Avg 1.61", "Taking more/first size|cons" all mean HE IS IN
and fire on his last Loaded (a second confirmation on the same PREP walks
the averaging path). "today exp"/"expiring today" = 0DTE. RE_STOPPED_OUT —
"Stopped out of half my position" = TRIM, plain "stopped out" = CLOSE,
resolved by trader when no ticker. Parity at 241 lines.

He can supply corpus going back much further if needed. Still thin: Midas
losing days. Whop re-export still pending (needs logged-in tab since the
all_frames fix).

## Update — first live test day graded; the reply bug, fixed two ways

Day one of all-rooms testing: +$196, 7 up / 6 down, peak $7,040. His copied
log only reached back to 10:25 (LOG_MAX was 120) — the visible five trades
netted +$723, so the morning he couldn't see netted -$527, which matches the
"day so far -$687" line at 10:38 exactly. Fixes: LOG_MAX is 400, and Copy
log now leads with "THE DAY, TRADE BY TRADE" — every trade from the day
table with entries, exits and WIN/LOSS/STILL OPEN verdicts — so analysis
never depends on log reach again.

HE found the day's real bug (screenshot): Mike REPLIED to his own morning
AMD entry; the scribe relay line inside the reply re-read as a fresh entry
and the bot bought AMD 470P again at 4.15 and then 6.10 (top tick, after
the real trade closed +56%). Two independent fixes:
1. content.js flags Discord replies ([id^="message-reply-context"]) and the
   worker refuses to trade them (still captured, logged as "a REPLY quoting
   an older message").
2. The echo guard (guards.js + guards.py, tested): same trader + same
   contract + same POSTED PRICE only enters once per day (st.echoes /
   self.echoes). Genuine re-entries always carry a new price (GOOGL 4.45 →
   3.50 → 3.20 all passed). Entries with no posted price are exempt —
   Aristotle's bare re-entries can't be told apart.
Also of note from the day, not a bug: the 3-of-5 trim ladder sells out
before the room's big runners (last SPY sold +30%, Brett rode to +65%).
That's the fixed-pattern trade-off, on record for when he wants to revisit
sizing.

## Update — day one autopsy answered; trims now sell 1; popup text copyable

His four questions after day one, answered and shipped (v1.13.1):

WITHOUT Mike's reply error: AMD#2 (bought 4.15 off the reply, sold +$80)
comes out of the ledger — realized goes +$196 → about +$116, record 6 up /
6 down. AMD#3 (5 @ 6.10 top tick, $3,050) would never have existed; that's
the STILL OPEN position dragging the day. The $7,040 peak is UNCHANGED —
computed to the dollar as SPY $2,715 + AMD#1 $1,675 + META $2,650 held
simultaneously ~10:31, which is BEFORE either echo buy. The peak was
legitimate money-in-use.

TRIM LADDER: on his word ("maybe in every 'trim' we can sell 1 contract
instead of 3") DRY_TRIM_QTY and DRY_FUT_TRIM_QTY are 1, and the test-mode
trim override in background.js sends qty 1. Entries/adds stay 5. So a
5-contract trade now survives four trims instead of one and rides runners
closer to the caller's full exit — the day-one evidence was the last SPY
selling +30% while Brett rode +65%.

POPUP COPY/PASTE: body { user-select: text } (buttons excluded) — every
number, log line and table row in the popup can be selected and copied.
The popup only closes when you click OUTSIDE it, so dragging a selection
inside is safe.

WHERE THE REST OF THE LOG LIVES (told to him): trades.log in the
discord-sniper folder is the full play-by-play (Notepad opens it);
days\YYYY-MM-DD.json is the structured per-trade table the bridge rewrites
on every event; the popup Trades table shows today live and the dropdown
loads any saved day; Copy log now leads with the full-day trade table.

## Update — he found the day file; two real bugs fell out of it

He uploaded days/2026-07-30.json and asked where the losing trades were.
They weren't in the table — and that was a BUG, not a display choice:

1. RE-ENTRY ATE THE FINISHED TRADE. Positions live under trader|SYM.
   sweep() only files finished trades to the archive after 30 minutes, but
   Unraveller re-entered TSLA ~11 minutes after stopping out — entry_sent()
   overwrote the finished position before sweep ever saw it. The wallet kept
   the money (its own closed_trades list), so P/L was right, but the trade
   row vanished. All five morning losses and both closed AMD trades were
   eaten this way. Fix: entry_sent() archives a DONE position before taking
   the key. Regression test in test_positions.py.

2. MIDNIGHT NEVER HAPPENED. The bridge runs 24/7 now, and nothing reset the
   scoreboard: Wednesday's GOOGL +$165 and QQQ +$108 were still on
   Thursday's count. "+$196, 7 up / 6 down" was really TWO days. Thursday
   7/30 alone: -$77, 5 up / 6 down (and stripping Mike's echo AMD +$80,
   -$157, 4 up / 6 down). Fix: Book.new_day() (clears archive + day
   scoreboard, keeps open positions, re-marks peak) called by bridge
   roll_day() from save_day() and the /fills poll. Yesterday's file is
   already complete on disk when the roll happens.
   NOTE: peak $7,040 stands — all three legs were Thursday ~10:26-10:49.

Also on his ask: every entry and exit in the popup table and Copy log now
carries its New York time ("in 09:33 5 @ 4.50") so he can line rows up
against the room minute by minute. The day files always stored these
timestamps; now they're shown.

The 13-trade money list in wallet.trades was complete all along — that plus
trades.log is the full record; only the table rows went missing. v1.13.2.

## Update — day one graded for the NEW rooms (he pasted the Copy log)

He asked what worked and what didn't, Aristotle and Midas only.

ARISTOTLE: not one line in the whole log (10:25-12:53). Either the tab
wasn't open/logged in, or he posted nothing in that window. Export chat
will settle it — waiting on him.

MIDAS: the tab WAS recording, and his lines exposed three things, all
fixed in v1.13.3:
1. MISSED HIS ONLY REAL TRADE. He posted Loaded before 10:20 (before log
   reach) and "Filled at 1.46" at 11:56 — 97 minutes of resting his bid,
   his style. The 30-minute loading window refused it; he later posted
   "Trimmed at 17%". FIX: loading window default 1800s → 14400s (4h) in
   guards.js + guards.py; the stale-fill tests in test_signals.py and
   test_resolve.js now assert 2h fires and 5h+ refuses.
2. "Not adding to this position" PARSED AS AN ADD (RE_ADD saw "adding",
   never looked left). Only stayed safe because we held no Midas position.
   FIX: negation vetoes "not adding" / "won't add" / "wont add" /
   "no adds" in VETO_WORDS, both parsers.
3. His planning chatter — "Some trim targets are 737.70 and lower",
   "Or from 15% profit" — was refused only because bare trims need a
   resolvable position; holding his trade, the second one would have SOLD.
   FIX: "trim target" veto + a from-N% rule (a percentage with "from" in
   front is a level, not a sale), both parsers. Corpus now 244 lines,
   parity green.

Also noted in his log, not new: every message appears twice (two BID IN /
SKIPPED "already acted 0s ago" pairs) — the dupe guard held every time, no
double trades; likely the same channel open in two tabs at once. Told him
to keep one tab per channel. The reply-echo AMD entries at 10:45/11:01
fired in this log because he was still on the pre-fix build.

## Update — the drill (practice tool) and the tab doubling explained

The doubling mystery is solved and it wasn't Discord: he clicked START
HERE by hand AND the 9:25 alarm ran it again — every channel open in two
tabs, every message read twice. The dupe guard held every time. Fix that
makes it impossible anyway: background.js oneTabPerChannel() on the 30s
alarm — same channel in two tabs, the extra closes itself (active tab
survives, else the oldest). v1.13.4.

"What can we do to practice more on the wording? midas is kind of hard" —
built drill.py + EXTRAS option 10. The flow: scroll far back in a channel
(history is captured, never traded) → popup "Export chat" → EXTRAS 10 (or
python drill.py signal-room-chat.txt midas) → drill-report.txt opens in
Notepad with every line's verdict from the SAME reader that trades:
WOULD FIRE / WOULD SELL (if holding) / noted (Loaded) / ignored + why.
Bare fills pair with the caller's last Loaded inside the report; bare
trims say they'd resolve to the newest open position. Honest limits
stated in the file: no positions and no timing guards in a replay —
wording practice, not a backtest.

Drill implementation note: the export writes "Author: text" but live the
reader gets text with author separate — drill.py splits the same way,
otherwise a bare "Filled at 1.46" stops being recognisable behind the
author prefix. (Both parsers behave identically on prefixed lines, so
this is an export-format thing, not a live-parity thing.)

Waiting on him: more Midas days (especially losing days) via Export chat.

## Update — no more zips: GitHub pull is the update path now (v1.13.5)

He asked to stop the unzip-over-the-folder routine. The machinery mostly
existed (bridge /build fingerprint + extension self-reload + EXTRAS pull);
three gaps closed:

1. The self-reload waited for the bot to be OFF — but ON is 24/7 now, so
   updates waited forever. checkBuild now reloads whenever the SESSION
   isn't on (marketOpenNow(): Mon-Fri 09:15-16:10 ET is the hold window;
   in-flight orders always hold). Log/notification wording updated.
2. EXTRAS 7 refused to pull over local changes and pointed at option 6 —
   which would have -X-ours'd his STALE zip contents over the repo. Now 7
   fetches, and if the tree is dirty (zip residue) offers a one-question
   "make this folder exactly match GitHub" = git reset --hard origin/main.
   Keys/days/trades.log are gitignored so untouched. First run of 7 will
   hit exactly this path — that's the transition off zips.
3. A pull leaves the RUNNING bridge on old code, and a mid-day bridge
   restart wipes the in-memory day (save_day would rewrite today's file
   from an empty book — pre-existing hazard, still parked). So 7 now ends
   by OFFERING a bridge restart (stop + _run_hidden.vbs) with a plain
   warning to say N mid-session.

The flow he was told: I push → he runs EXTRAS 7 (→ Y) → extension updates
itself after the close, bridge restarts on his Y or next START HERE. The
v1.13.5 zip is the LAST zip — it carries the new EXTRAS 7.

Bat-editing gotcha (cost one retry): EXTRAS.bat is CRLF; read it with
newline="" (keep \r\n literal) before splitting on \r\n, or the splice
appends a duplicate :pull block at the end instead of replacing (batch
goto jumps to the FIRST label — old behavior silently wins).

## Update — EXTRAS 7 restarts the bridge without asking

On his word ("I'm not gonna update this during market hours... make it
restart automatically"): the Restart-the-bridge-now? question is gone from
option 7 — pull ends by stopping any running bridge and relaunching it
hidden, automatically. The mid-session caveat lives on as a comment in the
bat and in the wording that updates belong in the evening.

## Update — updates are fully automatic now; the dead files are gone (v1.13.6)

"i also dont want to hit extra, so just make that automatic aswell" — so
START HERE's step [2/5] no longer politely skips when the tree is dirty:
it fetches and `git reset --hard origin/main` every run. The folder
MIRRORS GitHub. If HEAD moved, UPDATED=1 and step [4/5] stops the running
bridge and relaunches it onto the new code (it already restarts the
extension via the /build fingerprint). So the whole update path is now:
I push → his 9:25 alarm (or any double-click of START HERE) does the rest.
EXTRAS 7 still exists for a mid-day manual pull; the automatic path is the
morning run. Consequence, deliberate: any local edits on his PC are wiped
daily — he doesn't edit code, and keys/days/logs are gitignored.

"clean all the files that are trash now" — deleted from the repo:
settings_quick.py (every number it tuned — buying power caps, trades/day,
max_qty, averaging switches — is a deleted filter; the file only wrote
dead keys) plus its EXTRAS option 5 (menu now has a deliberate gap at 5 —
renumbering would break "Do 6 first" references and his muscle memory).
dry_run_buying_power removed from settings.example.json (unlimited book).
README updated. And START HERE's update step quietly `del`s the pre-git
leftovers if they're still on his disk: BRIDGE.bat KEYS.bat RUN.bat
SETUP.bat TEST.bat execute.py listener.py webull_trade_sdk.log
settings_quick.py and the five old emoji bats (matched as "* UPDATE.bat"
etc. — cmd can't type emoji, wildcards can). .gitignore grew
drill-report.txt and signal-room-chat.txt so the drill's working files
never look like "changes".

Closing text of START HERE finally caught up with reality: it said "the
bot is OFF until you turn it ON", which hasn't been true since ON-24/7.
Now: ON and reading, TEST until HE flips it, OFF is the emergency brake.

## Update — fourth room: Aristotle's small-account challenge (v1.13.7)

Channel 1433933203302776852, "its aristotles but its a small account
challenge". Wired the same as the others: baked into channel_ids
(testing, like everyone — nothing real until HE flips it), fourth tab in
START HERE (same server id), exports tagged "aristotle-small", drill
prompt mentions it. Same grammar the reader already knows from his main
room.

Known edge, told to him: positions are keyed trader|SYMBOL, so if
Aristotle runs the SAME ticker in both his rooms at once, the bot sees
one trade — a bare trim from either room resolves to his newest position.
Refine only if it actually happens.

First update delivered WITHOUT a zip — it rides down on his next START
HERE (or EXTRAS 7).

## Update — day two graded: the reader bought a verb (v1.13.8)

He pasted day two's Copy log ("see if you find anything weird"). +$330,
2 up 1 down, and the 1-per-trim ladder proved itself: AMD rode all five
of Unraveller's trims to +58% (+$405 vs day one's early exits).

The bad one: Midas posted "741.60 is new line in the sand. I'm going to
take 742c starters and add full size at 741.60..." and the reader fired
OPEN **TAKE** 742C — bought the verb. (Died quietly as a nofill: TAKE
quotes don't exist. Still wrong.) Eight minutes later "I'm about 80% sure
market falls" fired TRIM +80%. Fixes, both parsers, samples 247, all
green: TAKE and KEEP into NOT_TICKERS; "going to"/"gonna" veto (announced
intent is not an entry — his entry is the fill that follows); a %-sure
veto (confidence is not a sale).

The doubled log line ("sold 1 at 7.35... still holding 2" twice at 09:37)
was the after-order fast poll and the 30s alarm running syncFills
concurrently — same fills_seq cursor read twice, same events logged
twice. fillsBusy flag now makes them take turns. No money was ever
doubled; it was log-only.

Noted, no code change: "couldn't reach the bridge" at 09:55 and 10:51 —
transient, bridge answered fine at 09:36/09:58/10:00. It cost the
KingBeeAri MSFT entry (his 46% winner). If it repeats, EXTRAS 2 (bridge
log) around those minutes is the diagnostic. Bridge refusals reply HTTP
502 by design — reads scary in the log but the sentence after it is the
bridge's own explanation. Also fine, by design: AMD call posted @4.65,
we filled @6.50 — no chase limit exists on his instruction; live bid is
what the market cost at that second. Mike's NVDA nofill (bid 2.53, ran
away) is the same coin's other face.

Challenge room works: KingBeeAri captured, his MSFT entry parsed
correctly, his bare "In @here"/"Trim @here"/"25%" shapes resolve exactly
like Aristotle's. First full day where every room ran the new plumbing..

## Update — why TAKE 742C sat in BID IN all day, and past a bridge reload

He asked, then reloaded the bridge and it was STILL pending. Three layers,
all fixed (v1.13.9):

1. The entry existed at all — the reader bought the verb "take". Fixed
   last turn (NOT_TICKERS + going-to veto).
2. The bid never died. TAKE has no quote and Midas posted no price, so
   the ticket's limit was None. In _probe/_became_filled the float(None)
   crashed the fill watcher, and the crash handler logged "lost track"
   but LEFT THE STATE AS WORKING — a bid in "waiting for a seller"
   forever. Now: _probe treats no-price as unfillable (simulated: let the
   90s deadline pull it; no-quote-and-no-price: dead on arrival), and the
   watcher's except path marks the position FAILED + unreserves — a
   crashed watcher declares the bid dead, never leaves it WORKING.
   Regression tests in test_positions (needed simulated=True — the plain
   book() helper defaults to the broker path, which FakeWB happily fills).
3. It survived his bridge reload because the popup's holding box reads
   the EXTENSION's own position record (guardState in chrome.storage),
   which a bridge restart doesn't touch — and the restarted bridge never
   sends a "nofill" event for a position it no longer remembers. Now
   syncFills purges any pending position older than 15 minutes (bridge
   pulls real bids at 90s, so a 15-minute "pending" can only be a ghost),
   with a log line saying so.

His words, the standing rule: "there should[n't] be any positions trying
to get in, much less carrying over to the next day."
## The Whop chapter opens — FirstStepTrading (Felony), the channel map

Discord chapter closed on his word ("lets put a period there"). He
subscribed to Felony's Whop: https://whop.com/joined/firststeptrading/
He'll subscribe to Webull's CME futures data (free per the Webull/CME
partner page) and was told the futures switch in the popup is the only
thing left to flip after that. NinjaTrader question answered: Webull is
the friendly path (everything's built against it); NT would be a second
bridge — revisit only if real-size futures costs matter someday.

His survey of the workspace — the six channels that post real entries
and exits, with their sample grammar:
- Day Trades: "Short nq 28240.50 / SL 28302", "Trimmed $800 a contract /
  SL at be" — futures shorthand.
- Futures: "Long NQ @ 29925 / Stop 29875 / Target 30,100", "40 points
  $800 a con on NQ long - Trimmed".
- Swing Trades: "Entered VXX 25C 8/28 @ 1.3" + stops/targets, "Entered
  BULL equity @ 7.24" — OPTIONS + EQUITY, multi-day.
- High Risk: "Long NQ @ 28490 / Stop 28450 / Target 28600", "Stopped 20
  point loss", "$1,000 a contract on NQ short - Trimmed".
- Long Term: "Grabbed NFLX equity @ 74.8", "Snagging starters on PYPL
  equity @ 41.03 AVG" — EQUITY, adds/holds.
- FST x 2K Challenge: "Entered (4) SLV 55C 8/21 @ 1.61 / Stop is today's
  low / Target 60" — options with HIS qty and text stops.
Not signals: Trading Floor (levels/plans), Daily Watchlist, and the
info/chat channels. "Read First" holds their definitions of Loading/
Filled/Trimming — worth capturing verbatim when he exports.

Already taught from the survey quotes (v1.13.10, samples 249, parity
green): futures entries without the @ ("Short nq 28240.50"), SL as stop
shorthand (numberless "SL at be" stays unmatched), "$800 a con".

Still ahead, in rough order:
1. His scrollback + Export chat from the six channels (whop.js all_frames
   capture is shipped but untested against the real logged-in room) —
   that pins Whop's DOM shape and channel paths ("whop:/..." tags).
2. Per-channel wiring: Day Trades / Futures / High Risk are the futures
   pipeline (built, behind futures_enabled). 2K Challenge is options —
   closest to today's pipeline, plus his "(4)" qty and text stops.
3. Swing Trades / Long Term need TWO new things before any of it trades,
   even in test: EQUITY orders (new kind: shares, mult 1, no expiry) and
   the parked multi-day-hold machinery (disk-persisted book, catch-up on
   reopen). Do not let a "Grabbed NFLX equity" line near the options
   path meanwhile — "equity" lines currently have no grammar, and if one
   ever parses by accident the NOT_TICKERS/veto approach is the tool.

## Update — Day Trades taught from his full-channel paste; per-room LIVE toggles (v1.13.11)

He pasted the entire Day Trades channel (June 1 - now, Felony + the mod
Trademorewiser who posts the mechanical lines) and asked to "start with
this one". Also: shorter replies from now on — the chat is clogging.

Grammar taught, both parsers, samples 270, parity green, all suites pass:
- bare "Load nvda 205p" = PREPARE (RE_LOADING now matches load/loading/loaded)
- "Stopped on nq" / "at be" / "be on nq" / "20 point loss" = their stop
  fired = CLOSE (RE_STOPPED_OUT extended)
- "Full sold $3400 a contract" / "nq 500 points $10,000 a contract" /
  "200 points" = CLOSE carrying usd (full-exit rule no longer demands a
  percentage)
- "Trailed out nq" = CLOSE; futures symbols now resolve in ANY case
  ("nq", "es" lowercase — they aren't English words, safe where stock
  tickers wouldn't be)
- RESTING-ORDER NARRATION NEVER TRADES: "Sell order at 29630", "Buy order
  sitting at 28934", "First trim (order) at 28550" — new veto; "First
  trim 37%" (no "at level") still trims
- "Entered nvda July 20th 205c / Avg 2.25 / Sl 203" — month-name expiry
  inside the contract (was reading "July" as ticker TH!), and Avg on the
  next line becomes the limit when no @ price
- "Made small add into nvda" = ADD ("into")
- Verified ignored: bare "$1000 a contract", "70 points...", "Up 210
  points...", "Sl moved to...", bare "75%"-style updates (in THIS room
  bare percents are progress, not trims — the verb decides; note: when
  Whop rooms are wired for real, Aristotle-style bare-percent-trims vs
  this room's bare-percent-updates will need per-room profiles)

PER-ROOM TEST/LIVE TOGGLES, his design: popup Settings now lists every
room with testing/LIVE selects (ROOM_NAMES in popup.js), stored as
settings.channel_live. Enforcement in background: master TEST = everything
pretends as always; master REAL = rooms not flipped LIVE are logged and
never reach the bridge. Default: everything testing. When he's near the
REAL flip, consider the dual-book so testing rooms keep paper-scoring in
live mode (not built yet, on record).

Webull data sub ($220/mo he remembers): NOT findable publicly. Webull's
API docs say OpenAPI futures data requires a paid subscription whose
"subscription module is under active development and will be released
soon"; in-app CME L1/L2 is free via the CME partner page. Told him to
claim the free in-app CME data and ask Webull support about the API-side
package (that's the one our bridge actually consumes).

Equity + multi-day holds: HIS word — build them eventually, but Swing
Trades and Long Term channels are ON HOLD, not trading yet.

SANDBOX NOTE for future turns: this cloud workspace rolled back twice,
silently losing local commits/files that were already pushed. GitHub is
the truth — at the start of any turn after a gap, fetch and compare
before editing, and re-seat local work on top of origin/main.

## v1.14.0 — THE MASTER SWITCH IS RETIRED; the Futures channel is taught

His words: "remove the main big switch since i want every room to act
individually. its either testing or they are live.. just like that. as
soon as app starts everyone is testing obviously."

Architecture now: execution is PER ORDER. The extension sets order.live
from the room's own toggle; the bridge routes each order (live -> Webull
path, else dry book). MODE is forced to dryrun at boot (an old
settings.json saying webull can't arm anything); webhook mode survives as
the only global. POST /mode answers politely that it's retired. The Book
holds live and test positions side by side: p["live"] decides whether the
fill watcher probes Webull order_status or the quote feed, and the pretend
wallet/scoreboard NEVER counts live positions (Webull is the ledger for
real money). _row exports "live" for the popup. Live trims still refuse
(hold-until-all-out stands). Live tickets are marked live by the bridge;
webull_futures orders inherit via order["live"].

Extension: big TEST/REAL button deleted from the popup — a one-line bridge
status replaces it (keys, connection, buying power). Room toggles are THE
control: flipping one to LIVE pops a plain-words confirm; Save applies.
allRoomsTesting() clears channel_live on browser start/install — LIVE is
per room, per session, never survives a Chrome restart.

Futures channel taught (samples 283, parity green): AVG-style entries
("Long NQ - AVG 24015", "Entered NQ short 23477 average", "Short RTY AVG -
2398.4"), priceless-but-real calls ("Short NQ - Light" + Stop/Target =
market entry with a warning), seven ways of saying stopped ("Stopped" at
message start, "Eh stopped", "Stop got hit", "BE stop hit", "Trailing stop
hit on RTY"), papercuts sell ("Taking papercut" — verb-led, exempted from
the don't-veto; "paper cuts we took yesterday" stays a war story),
gold/silver/platinum map to GC/SI/PL. Sandbox data endpoint he supplied,
for when quotes matter: https://api.sandbox.webull.com/openapi/market-data/futures/tick
(docs: developer.webull.com/apis/docs/reference/futures-tick) — noted for
webull_futures/quote work once his CME data is live.

NOT done, deliberate: live-mode paper-scoring dual wallet beyond what the
Book now does (test rooms score in the dry wallet even while other rooms
are live — that IS the dual book, done); per-room grammar profiles (bare
percents: Aristotle trims vs Felony-room updates) still pending Whop
wiring; Whop platform gate still record-only.

## v1.14.1 — High Risk + 2K challenge taught; one near-disaster caught in review

High Risk channel (link: whop.com/joined/firststeptrading/high-risk-...):
same grammar as Day Trades/Futures plus quirks, all pinned: "St0p 28225"
(zero for o), "Target 1: 7600 / Target 2:" (label only skipped when a
colon follows — "Target 28250" can't lose its 2), "Taking BE (on NQ)" =
close at breakeven (joined RE_PAPERCUT).

THE NEAR-DISASTER, caught while testing, never shipped broken: his trim
updates ("$1,000 a contract on NQ short - Trimmed / Stop now 28130 ...
post in gains") contain a direction, a FUT symbol, a digit stop and the
word "in" — everything the v1.14.0 AVG-entry fallback wanted. It would
have BOUGHT on a trim. Guards now: any trim word kills the entry read,
and the direction+symbol must sit within the first 40 chars (entries lead
with their call; buried "on NQ short" doesn't). RE_FUT_DIR_SYM iterates
candidates (leftmost "long here" no longer shadows "on NQ") with the
wandering shape ("Re-entered long here @ 23480 on NQ") first, and the
fallback also accepts an inline @price (Re-Entered NQ short @ 29555).

2K challenge (whop.com/firststeptrading/fst-2-k-challenge-...): his OWN
posted signal format ("Entered (3) ABC 25C @ 1.23 for 6/19"). Qty in
parens captured (RE_QTY_PAREN), "2 CONS" counts as contracts, "Stopped on
VXX -15%" closes. His per-entry size is recorded — the day a room goes
LIVE with his sizing, sig.qty is already there (test mode stays 5/1).

Samples 295, parity green, all suites green. Known deferred: bare-percent
updates ("65% on NVDA $100 per con") would TRIM under Aristotle's rule —
per-room grammar profiles are REQUIRED before any Whop room leaves
record-only. Two-contract entries ("SPY 742P and QQQ 696P" one message)
still act the first only.

## v1.15.0 — full speed: every channel, options, futures 24h, equity, swings

His word: "i want everything running at full speed.. every channel,
options and futures, equities and swings." All test money; per-room LIVE
still per-session and confirmed by hand.

- FUTURES TRADE 24H now: guards.js applies the real futures calendar to
  kind=future entries (Sun 6PM ET open, Fri 5PM close, daily 5-6PM break);
  equities keep the 9:30-16:00 window. guards.py mirror: futures skip the
  equities window.
- EQUITY: parser reads "Entered BULL equity @ 7.24" / "Grabbed NFLX equity
  @ 74.8" / "Snagging starters on PYPL equity @ 41.03 AVG" -> OPEN
  kind=equity (mult 1). Bridge test-sizes in DOLLARS: DRY_EQ_USD=1000 ->
  qty=round(1000/px). positions.py money math is mult-aware now (the old
  hardcoded x100 would have priced $1k of NFLX as $100k).
- SWINGS SURVIVE RESTARTS: Book.export_state/restore_state + bridge
  state.json (written with every day file, loaded at boot). FILLED
  positions always come back with stops re-armed; archive + scoreboard
  come back same-day only. Also fixes the old mid-day-restart-wipes-the-
  morning hazard. state.json gitignored.
- WHOP ROOMS TRADE (test): background whop gate now graduates known slugs
  -> canonical ids (whop:day-trades, whop:futures, whop:high-risk,
  whop:2k-challenge, whop:swing, whop:long-term), baked into channel_ids,
  in ROOM_NAMES toggles. Felony-room grammar profile: bare_pct_trims=false
  (bare "65%" is progress there, never a trim — the verb decides; parser
  cfg flag, both brains). whop.js learned author lines
  ("Felony@felonytrades·1d" blocks -> lastAuthor). Unknown whop rooms stay
  capture-only. CAVEAT, said plainly: the whop DOM reader is still the
  wide-net heuristic and untested against the live logged-in page — the
  Export chat file remains wanted to pin it down. Swing/Long Term slugs
  are guessed ("swing-trades"/"long-term") until he sends those links.
- PER-ROOM SCOREBOARD: orders carry room labels; Book positions +
  closed_trades keep them; popup "By room — today" box: up/down, net $,
  still-open per room.
- HIS WEBULL CME DATA IS LIVE — confirmed from this session via the Webull
  MCP: NQU6/ESU6 snapshots with bid/ask returned (Friday close data).
  Futures switch in the popup is what remains for him to flip.
