# HANDOFF — read this first in a new chat

If you're Claude and G has just pasted you this repo: this file is the context.
Read it, then read `README.md`, then `signals.py`. That's enough to be useful.

## What this is

G's personal reader for **somebody else's** Discord options signal room. Read
and fire, nothing else. It is deliberately separate from his other app,
MARKET SNIPER (`giancuffaro/market-sniper`) — no shared code, no shared folder,
no shared config. Keep it that way; he's said so more than once.

He is a **member, not an admin**, of that room. That's why the real product is a
Chrome MV3 extension that reads the tab he already has open, not a Discord bot.
The bot path still exists in this folder and is kept working, but it needs an
admin to invite it, so it's the backup.

Channel ID: `829754942817828884`.

## The room's grammar (from his real transcript, in `samples.txt`)

| Line | Meaning |
|---|---|
| `loading AMD 7/31 480P` | get-ready only. **Never buys** — the room's own pinned rule |
| `in AMD 7/31 480P @ 3.4` | the only thing that opens a position |
| `trimming AMD @ 38%` | depends on `trim_action`; default is ignore |
| `all out of AMD` | close. Names no contract — fill it in from the position |
| `exited SPY, and back in @ 2.84` | **sell, then re-buy the SAME contract.** Not flat |
| `50% on SPY, great session` | chatter |

`@ 38%` must never parse as a limit price of 38. There's a test for it.

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

## Before you change anything, run all three

```
python3 test_signals.py                                  # parser + brakes
python3 replay.py                                        # his whole session, clock off
python3 dump_parse.py > /tmp/py.json && node test_parity.js /tmp/py.json
```

Known-good replay output ends with: `Still open at the end: NFLX`. If that line
changes, something moved.

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
`bridge.py`, `webull_options.py`, `setup_keys.py`, all the `.bat` files, README
with the full Chrome install walkthrough, and the corrected sell-and-re-buy
behaviour wired through both the extension path and the bot path.

Open:
- He needs to create the empty **private** repo `discord-sniper` on github.com
  and run `📤 FIRST PUSH TO GITHUB.bat`.
- He has never run it live. He's on `dryrun` + SAFE and should stay there for a
  full session before anything is armed.
- Untested against the live Webull API — the SDK field names are hunted for by
  name in `webull_options.py` because they drift. First live connect may need a
  fix there.

## Update — live/dry-run toggle

The popup now has a LIVE / DRY RUN button above the settings. It talks to
`GET|POST /mode` on the bridge; the bridge owns the mode because the bridge is
the only thing that can place an order. Going live is two clicks and writes
`execution.mode` into `settings.json`, then reconnects Webull and reports the
account. Going back to dry run is one click. It is a *separate* lock from ARM —
both must be on for anything to fire.

`📥 SET UP ON THIS PC.bat` handles a fresh machine: checks git and Python, pulls
from GitHub, installs deps, then tells him to run KEYS.bat and load the
extension. Keys are never in the repo, so every PC needs them typed once.

Note: this sandbox is blocked from authenticated pushes to GitHub. The loop is
zip -> he unzips over his folder -> he runs `⬆️ PUSH CHANGES.bat`. Don't promise
him direct pushes; it's been tried and refused at the environment level.
