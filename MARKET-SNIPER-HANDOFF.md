# HANDOFF — porting the Discord Sniper upgrades into MARKET SNIPER
Written 9/2/26 for a Claude session opened IN THE MARKET SNIPER FOLDER.
Read this whole file first. Then read Market Sniper's own code before
changing anything — this doc knows Discord Sniper; it has never seen
Market Sniper's source.

## Who / what
- G (giancuffaro230@gmail.com), non-coder. Replies CONDENSED. "Fix
  everything is default always." Real-money actions are HIS alone.
- MARKET SNIPER = G's own tool, 127.0.0.1:8000, his MANUAL scalps (he
  clicks, it fires). DISCORD SNIPER = the room-copying bot, 127.0.0.1:8787,
  folder C:\Users\Hulk\Desktop\discord-sniper. BOTH trade the SAME Webull
  margin account (ENIQGUV4LUTT3JSAA9NKLDDU19) with the SAME app key.
- The source of every upgrade below is in the discord-sniper folder. Copy
  from there; never edit that folder from a Market Sniper session.

## THE ONE RULE THAT MATTERS MOST: one app key = one rate budget
Webull allows 300 requests / 60 s PER APP KEY. Three processes share it:
the bridge (8787), the Fill Announcer, and Market Sniper. On 9/2 one
process (the announcer) alone produced 76,991 rate-limit errors in a night
and everyone else's calls 429'd with it. Market Sniper MUST:
1. Pace every Webull call at >= 0.20 s (the bridge's `_pace()`), and
2. Back off 20 s the moment it sees a 429, and
3. Never poll anything faster than it needs (quotes: use the batched call
   below; orders/positions: 2-5 s, not 1 s).
If Market Sniper polls quotes per-symbol every second, it will starve the
bot's stops. That is the failure to avoid above all others.

## What to port, in order (safest first)

### 1. `stop_below()` — a stop can never rest AT the fill (10 min)
Copy from discord-sniper/webull_options.py (function `stop_below`).
Rule: pct down, tick-rounded, and if rounding lands at/above the reference
price, drop one full tick step. Lesson: a 0.22 bid rounded its stop UP to
the 0.20 fill and stopped out 7 seconds after filling. Use it everywhere a
stop price is computed.

### 2. Breached stop = SELL, never re-anchor (10 min)
In whatever places a resting stop (see `place_stop` in webull_options.py):
Webull rejects a sell-stop above the live market, so code "clamps" the
stop one tick under the bid. Keep the clamp for the wide-spread-at-entry
case, but if the market is more than 10% BELOW the intended stop, that stop
is BREACHED — refuse to rest a lower one and let the watchdog sell. Lesson:
an overnight gap re-anchored a stop from 0.75 to 0.40 and rode it to -59%.

### 3. The tiered ratchet + ANTI-CLIP (30 min)
Copy `ratchet_tiers.py` whole. Wire it where Market Sniper walks stops up:
  locked = ratchet_locked_pct(gain_pct, fill)      # tier rungs by price paid
  locked = anti_clip(locked, gain_pct)             # never closer than 40% of gain
  new_stop = ratchet_stop_price(fill, locked, bid=bid, ask=ask,
                                current_stop=stop, direction=+1)  # None = don't move
Tiers: <$1 arms +25% / lock +10% / rungs 15%; $1-2 arms +15% / BE / 10%;
$2+ arms +10% / lock +5% / 5%. Never loosen. Two floors inside: a rung is
worth 4+ ticks and the stop never sits inside the bid/ask. Study behind
anti-clip is in discord-sniper/v3.5.0/ANTI-CLIP.txt (+$6,433 vs +$2,872).
If Market Sniper's ratchet is G's manual choice per trade, wire it as an
option, default ON, and let him flip it.

### 4. Atomic stop replace — no naked window (20 min)
Copy `replace_stop` from webull_options.py. When moving a stop: try REPLACE
(same client_order_id, one call) first; only on failure fall back to
cancel-then-place. If the cancel succeeded and the place failed, LOG THE
TRUTH ("no broker stop resting") and re-arm on the next pass. The old
pattern lied about the old stop still being there.

### 5. Batched quotes + the budget (45 min, do it on a closed market)
Copy `quote_bus.py` whole and the `ask_bid_many` / `_pace_batch` /
`_parse_batch` methods (discord-sniper/v3.5.0/_patch_ask_bid_many.py).
Wire: `BUDGET = Budget(); client.budget = BUDGET; bus = QuoteBus(
client.ask_bid_many, budget=BUDGET); bus.start()`. Watch/unwatch each
open contract; read `bus.get(occ)`; if the bus has nothing fresh, take a
DIRECT quote at most every 2 s (never let a dead bus blind a stop). One
call then covers every open position every ~300 ms. If the log says
"batched option quotes not available on this SDK", keep polls at 5 s.

### 6. Overnight swings: re-arm stops after the open (15 min)
Webull only takes DAY stops on option sell legs — every resting stop dies
at the close. Any position held overnight wakes up NAKED. Copy the pattern
in positions.py `rearm_overnight_stops()` (called weekdays at 9:31): every
open position whose stop wasn't placed today gets its stop re-armed. Swings
get the WIDE stop (-25% or the caller's level), never the scalp stop.

### 7. Flat account = a verdict (10 min)
If Market Sniper reconciles its book against broker positions: an EMPTY but
SUCCESSFUL positions read means "flat" and must clear ghosts. Treating
empty as "no answer" left a sold position haunting the book for 3 hours and
its stop 417-storming a contract that no longer existed.

### 8. Underlying at fill (5 min)
On every fill, read the stock price and store it with the trade. G asked
for it; it goes in the journal and the Discord post.

### 9. Fill Announcer (optional, 15 min)
discord-sniper/announcer.py already narrates the WHOLE account — including
Market Sniper's fills — to G's Discord (options + futures channels,
milestones, stop-outs, scoreboard). Do NOT run a second announcer from
Market Sniper: two would double-post and double the API load. If Market
Sniper wants its own posts, POST TO THE SAME WEBHOOKS from settings.json
(gitignored) and tag lines "[MS]".

## Coexistence rules (both tools on one account)
- Discord Sniper ADOPTS any position it didn't originate as "his" —
  visible, never stop-managed, never sold by a room call. Market Sniper's
  positions therefore show up in the bot's book with no bot stop. Keep it
  that way: Market Sniper manages its own stops; the bot manages its own.
- Never let both tools rest a stop on the SAME contract. If G scalps a
  contract the bot is also in, the second resting sell is how you get
  flattened twice (the 8/18 "two resting sells" lesson).
- The bot's `adopt_max_qty` (settings.json, default 3) is the line: any
  position bigger than 3 contracts is assumed to be G's manual trade.

## Things NOT to do
- Do NOT install `webull-python-sdk-*` (the streaming/MQTT family) into the
  same Python as `webull-openapi-python-sdk`. They pin incompatible
  protobuf/paho/cachetools/jmespath. It broke the bridge's imports on 9/2
  (discord-sniper/FIX SDK DEPS.bat repairs it). Streaming lives only in a
  side-by-side Python 3.12 venv.
- Do NOT `git reset --hard` anything without `git merge-base --is-ancestor
  HEAD origin/main` passing first (the 8/30 lost-day lesson).
- Do NOT touch the position watchdog during market hours. Batched quotes
  and stop logic = closed market only, tests first.
- Do NOT touch discord-sniper/settings.json from Market Sniper. Read keys
  from Market Sniper's own config.

## Verify after porting
1. Zero `429` / `TOO_MANY_REQUESTS` in BOTH tools' logs for a full session.
2. A stop is never logged at the fill price.
3. First winner past its arm level moves its stop at the tier, and a big
   runner's stop trails at 60% of the gain (anti-clip line in the log).
4. Overnight hold: stop re-armed at 9:31 with the wide %.
5. The Fill Announcer posts Market Sniper's fills to Discord too.

## Where the source lives (copy, don't link)
discord-sniper/webull_options.py  (stop_below, place_stop clamp+breach,
                                    replace_stop, ask_bid_many, _pace)
discord-sniper/positions.py       (rearm_overnight_stops, reconcile_gone
                                    trust_empty_live, _watchdog bus read,
                                    auto_ratchet with tiers + anti-clip)
discord-sniper/ratchet_tiers.py   (whole file)
discord-sniper/quote_bus.py       (whole file)
discord-sniper/v3.5.0/            (the study docs, ANTI-CLIP.txt, patches)
discord-sniper/HANDOFF.md         (the bot's own living memory — every rule)
