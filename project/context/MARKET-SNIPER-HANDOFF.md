# HANDOFF — MARKET SNIPER work, written 9/4/26 (supersedes the 9/2 version)

**For a Claude session opened IN THE MARKET SNIPER FOLDER (127.0.0.1:8000).**

Read this whole file first. Then **read Market Sniper's own source before
changing anything.** This document knows Discord Sniper intimately and has
never seen a line of Market Sniper. Every effort estimate here is a guess
about a codebase I cannot see; treat them as such and re-estimate once you
can read it.

Copy code FROM `C:\Users\Hulk\Desktop\discord-sniper`. Never edit that folder
from a Market Sniper session, and never edit this folder from a Discord
Sniper session.

---

## Who you're working with

G (giancuffaro230@gmail.com). **Non-coder.** Trades options and futures live,
real money. Replies CONDENSED — short, direct, no fluff, no headers unless a
table genuinely helps. Active voice. Own mistakes plainly, then fix them.

Standing rules that apply here exactly as they do in Discord Sniper:

* **"Fix everything is default always."** Bugs get fixed without asking.
* **Real-money actions are HIS ALONE**: placing/cancelling orders, funding,
  unlocking accounts, questionnaires, accepting ToS, passwords, generating
  API keys. Never do them, however explicitly he asks. Set the form up and
  hand him the last click.
* **Never run git write commands from a sandbox.** AUTO PUSH sweeps every
  45s and holds the lock. On 9/4 even read-only `git log` hung for two
  minutes from a sandbox. Use file operations, not git.
* **Compile-check everything you touch.** Never break the build.
* `settings.json` is gitignored and holds every key — never commit it, never
  paste it back, never print its values.

---

## THE THREE MODIFICATIONS HE ASKED FOR (9/4)

In his priority order. Do them in this order too — 1 is the one that helps
both tools at once, and 3 depends on 1.

---

### MOD 1 — GET MARKET SNIPER'S QUOTES OFF WEBULL

**This is the biggest win available and it helps the bot as much as it helps
Market Sniper.**

Webull allows **300 requests / 60s PER APP KEY**. Three processes share one
key: the Discord Sniper bridge (8787), the Fill Announcer, and Market Sniper
(8000). They are not separate budgets. On 9/2 one process alone produced
76,991 rate-limit errors in a night and starved everyone. On 9/4 the bridge
log carried **1,052 throttle events**, and during the 09:48–09:52 burst the
bot's ratchet fell back to direct per-contract quotes because the shared bus
could not keep up.

Quotes are the bulk of the call volume. Move them and the pressure goes away.

**The split — this is the whole design:**

```
ORDERS, POSITIONS, BALANCES   ->  stay on WEBULL   (that is where the money is)
MARKET DATA (quotes, greeks)  ->  move to TASTYTRADE / TRADIER
```

Nothing about how Market Sniper *trades* changes. Only where it *looks*.

**Both accounts are live, funded and verified as of 9/4 18:10:**

| | tastytrade | Tradier |
|---|---|---|
| auth | OAuth: client_secret + refresh_token | single access token |
| funded | $250 | $500 |
| option quotes | **streams** over DXLink | REST + websocket |
| **greeks** | **streams live** (delta/gamma/theta/vega/IV) | ORATS via REST chains, cadence undocumented — MEASURE `greeks.updated_at` before trusting |
| stock quotes | REST 403s on this account | **works** (SPY 770.19 on 9/4) |
| rate cap | none published | none published |

So: **tastytrade for option quotes and greeks, Tradier for underlying
prices.** Webull has no option streaming at any price — that is the only
reason Discord Sniper polls a 1/sec batched sweep at all.

**What to copy:**

* `discord-sniper/dxlink.py` — **whole, unmodified.** A ~150-line RFC 6455
  WebSocket client on the **standard library only** (socket, ssl, struct,
  base64, hashlib). No pip install, deliberately. The last streaming SDK
  installed into a bridge Python broke its pins and `FIX SDK DEPS.bat` exists
  purely to undo that. This file cannot move a dependency.
* `discord-sniper/tastytrade.py` — `_session()` and `quote_token()` for auth.
* `discord-sniper/tradier.py` — if you want Tradier quotes too.
* Credentials already exist in `discord-sniper/settings.json` under
  `execution.tastytrade` and `execution.tradier`. **Market Sniper needs its
  own copy of those values** — ask G to paste them, or read them at runtime.
  Do not print them.

**Four traps already paid for on 9/4. Do not rediscover them:**

1. **The DXLink handshake is SEQUENTIAL.** Firing SETUP, AUTH,
   CHANNEL_REQUEST and FEED_SETUP back-to-back returns `AUTH step missing`
   forever *while the socket stays connected and looks healthy* — a silent
   no-data failure. Wait for each confirmation. See `_await()`.
2. **Check the token level.** An unfunded account gets `level: demo` on a URL
   ending `/delayed`. A funded one gets `level: api` on `/realtime`. Delayed
   greeks that read as live would move a stop off stale gamma.
   `live_level()` refuses them and says so out loud.
3. **OAuth access tokens last 15 MINUTES**, not 24 hours. Refresh on a 60s
   margin or you get a 401 in the middle of managing a position.
4. **Greeks publish on a SLOW cadence.** Measured 1–2 events per 20s on
   subscribe, and no `acceptAggregationPeriod` value changed it. Fine for
   entry/exit stamps; useless as a tick-by-tick delta feed. Subscribe
   `Quote` alongside `Greeks` if you need per-tick prices.

**Whatever you do NOT move, pace it.** Any remaining Webull call: ≥0.20s
between calls, back off 20s on a 429, and never poll orders/positions faster
than 2–5s. Copy `_pace()` from `discord-sniper/webull_options.py`.

---

### MOD 2 — PORT THE SAFETY FIXES

All proven in live trading in Discord Sniper. Safest first.

**2a. `stop_below()` — a stop can never rest AT the fill.** (~10 min)
Copy the function from `webull_options.py`. Rule: pct down, tick-rounded,
and if rounding lands at or above the reference, drop one full tick step.
Lesson: a 0.22 bid rounded its stop UP to the 0.20 fill and stopped out
seven seconds after filling. Use it everywhere a stop price is computed.

**2b. THE BRACKET STOP MUST BE CLAMPED UNDER THE LIVE BID.** (~20 min)
**This is the newest and most expensive lesson — 9/4 morning.** INTC 94C was
bought at the caller's 0.95 into a wide spread while the live bid was 0.83.
The bracket's stop leg was computed as a flat −10% of the fill = 0.86 —
*above* the bid — so it was **already triggered at birth and filled 308
milliseconds after the buy.** Guaranteed loss, no trade in between.

`place_stop()` had clamped stops under the live market since 9/1, but the
stop born WITH the entry never saw that clamp — and that is the leg resting
on nearly every trade. Before resting a born stop: read the bid, and if the
computed stop sits at or above it, rest one tick UNDER the bid instead. It
can only ever tighten the distance from the fill, never widen it.

**2c. Breached stop = SELL, never re-anchor.** (~10 min)
Webull rejects a sell-stop above the live market, so the code clamps one
tick under the bid. Keep that for the wide-spread case — but if the market
is more than 10% BELOW the intended stop, that stop is **breached**: refuse
to rest a lower one and let the watchdog sell. Lesson: an overnight gap
re-anchored a stop from 0.75 to 0.40 and rode it to −59%.

**2d. The ratchet ladder + anti-clip.** (~30 min)
Copy `ratchet_tiers.py` whole. **G's rule, in his own words, and it is the
rule — do not re-tier it:**

> "It was supposed to start all along from −10% and +10%. When it touched
> +10% the new stop becomes automatically 0%, and the next target is 20%.
> When 20% is touched the new stop is +10% and the new target is +30%. When
> +30% is touched the new stop is +20%, and so on and so forth."

One ladder for every premium. The 9/2 price tiers are retired. Wire it as:

```python
locked = ratchet_locked_pct(gain_pct, fill)
if dte is None or dte >= 2:                 # anti-clip: 2+ DTE ONLY
    locked = anti_clip(locked, gain_pct)    # never closer than 40% of gain
new_stop = ratchet_stop_price(fill, locked, bid=bid, ask=ask,
                              current_stop=stop, direction=+1)   # None = don't move
```

**Anti-clip is OFF on 0/1DTE** (his rule: "my rule on 0 and 1dte and anticlip
on later expirations"). A 0DTE has no tomorrow — theta eats whatever it does
not lock. Two safety floors live inside: a rung must clear 4 ticks, and the
stop never sits inside the bid/ask spread. Never loosen a stop.

Evidence it works: on 9/4 two NVDA 235C 0DTE entries ratcheted 0.95→1.11 and
0.93→1.10 and **both stopped out in profit, +$20 combined.**

**2e. Atomic stop replace — no naked window.** (~20 min)
Copy `replace_stop` from `webull_options.py`. Moving a stop by cancel-then-
place leaves a window with no protection, and the cancel is async — placing
the new stop while the old one still rests is every "ratchet couldn't move
the resting stop" 417. Try REPLACE first; only fall back to cancel+place,
and **wait for the cancel to land.**

**2f. Option SELL orders are DAY-only at Webull.** Every resting stop dies at
the close. Anything held overnight needs its stop re-armed the next morning
at 9:31. Discord Sniper does this in `rearm_overnight_stops()`.

---

### MOD 3 — GREEKS AND TRADE RECORDING

Depends on MOD 1 (the greeks come from the same DXLink connection).

**3a. Greeks on his manual scalps.** Once `dxlink.py` is in, subscribe each
open contract and stamp `greeks_in` at entry and `greeks_out` at exit. In
Discord Sniper this is done by subscribing the moment the stop is armed —
first greeks arrive in **0.06s**, so even a 20-second scalp gets them.
**Stamp entry greeks within the first 60s only.** After that they are not
entry greeks and calling them so would be a lie in the record.

**3b. Record the SHAPE of every trade, not just its ends.** This is what G
actually wants the data for — he asked for "more weeks data off of trades"
so the ratchet can be tuned on evidence instead of anecdote. Per closed
trade, store: `fill`, `exit`, `pl`, **`max_runup_pct`**, **`max_drawdown_pct`**,
`occ`, `side`, `strike`, `expiry`, `dte`, `swing`, `stop_at_exit`, `why`,
`state`, `live`, `greeks_in`, `greeks_out`.

Max drawdown is the one that matters most: **how far did a WINNER go against
me before it worked.** Entry, exit and P&L can never answer that, and it is
the only honest basis for any "give trades more room" rule.

**Two bugs Discord Sniper hit doing exactly this — both cost a full day of
data before they were caught:**

* The record sat inside `if not p_live`, so **only pretend trades were ever
  written down.** 26 day files held 2 rows between them while the log showed
  125 fills.
* Then, after fixing that, the record was still inside
  `... and price is not None` — so **every exit where the fill price is not
  known yet recorded nothing at all.** That is every hand close ("sold, but
  at a price I never saw"), which for Market Sniper is *most exits*. The day
  book ended 9/4 with zero trades while the journal counted eleven.

**A close must ALWAYS leave a row.** Write it with `exit`/`pl` NULL and a
`pending_price` flag when the price is unknown, and fill them in later from
the broker's order list. **Null is honest. Zero is a lie. Missing is worse.**

**3c. Also unfixed in Discord Sniper, so don't copy the bug:**
`restore_state` pops `hi_pct`/`lo_pct` on restart, so a position held across
a restart loses its run-up/drawdown history. Persist those.

---

## THE COEXISTENCE CONTRACT — DO NOT BREAK THIS

Both tools trade the **same Webull margin account** (`ENIQGUV4LUTT3JSAA9NKLDDU19`)
with the **same app key**.

* Positions Market Sniper did not originate are the BOT's. Leave them alone.
* Positions the bot did not originate are G's. Discord Sniper marks them
  visible, never stop-manages them, never sells them — and its adopt rule
  leaves anything larger than 3 contracts entirely alone, because a room's
  "all out of SPY" must never sell his 30-lot.
* On 9/4 this worked correctly: `ADOPT left SPY x5 alone — bigger than
  anything the bot trades, so it's YOURS. Rooms can't touch it.`
* **Historic failure to avoid:** Market Sniper has sold bot positions before
  (FLR and SPY 766C, logged in `discord-sniper/HANDOFF.md`). Whatever
  Market Sniper closes, it must be sure it opened.

---

## THE SOURCE-OF-TRUTH RULE

Learned expensively on 9/4, applies to any session in any of these folders:

```
positions -> ask the ACCOUNT
prices    -> ask the ORDER HISTORY
reasoning -> read the logs
...and NEVER substitute one for another.
```

Claude told G he was holding a 5-lot SPY position. He wasn't — it had closed
an hour earlier. The claim came from a log line that was TRUE when written
and FALSE when read. **A log is a narrative in the past tense; it is not a
statement of state.** Then, compounding it, Claude saw two earlier adoptions
of 2 and 3 lots, decided 2+3=5, and accused working code of inventing the
position. The order history showed a real, separate 5-lot trade. **The code
was right. A tidy theory beat a ten-second check.**

Discord Sniper now has `now.py` / `WHAT DO I HOLD.bat` for this. Market
Sniper should get the same: broker first, book second, log never.

---

## FACTS TO RESPECT (Webull, from v3.5.0/OPTIONS-BROKER-REFERENCE.md)

* Limits are **per endpoint, per app key**: option snapshot 60/min (20
  symbols per call); Order Detail / Positions / Balance 2 per 2s.
* **429 = throttle. 417 = business rejection.** Different problems.
* **No option streaming on Webull at any price.** Fills ARE pushed (gRPC
  TradeEventsClient).
* **No MARKET orders on options.** Combos = MASTER(LIMIT) + STOP_LOSS on
  SINGLE only. OTO/OCO/OTOCO are stock-only.
* Ticks: SPY/QQQ/IWM $0.01 always; Penny Program names $0.01 <$3 / $0.05 ≥$3;
  else $0.05/$0.10.
* ETF options trade to 16:15. 0DTE auto-exercises at $0.01 ITM — flatten
  before the close.
* **Webull's API has NO historical option prices.** Anything not recorded as
  it happens is gone forever. That is why the tape matters.

---

## STILL UNPROVEN — do not trust these until tested

* **Tradier OTOCO** (`place_conditional_entry`) — the conditional "buy when
  the underlying touches X" order, and the main reason to want Tradier.
  **UNVERIFIED.** Prove it in Tradier's sandbox before it ever sees real
  money: a conditional order that silently does nothing, or fires twice, is
  the worst possible thing to discover live.
* **Tradier option quotes** — needs a live OCC symbol to exercise.
* **tastytrade REST market data** — 403s on this account even though the
  DXLink stream works fine. Use the stream, not the REST endpoint.

---

## WHERE THINGS ARE

`C:\Users\Hulk\Desktop\discord-sniper\` — copy from here:
`dxlink.py` (stdlib WebSocket + greeks bus) · `tastytrade.py` · `tradier.py` ·
`broker.py` (the 16-method contract + capability flags) · `ratchet_tiers.py` ·
`webull_options.py` (`stop_below`, `place_stop`, `replace_stop`, `_pace`,
`tick_round`) · `positions.py` (the Book, watchdog, adopt/reconcile) ·
`now.py` · `HANDOFF.md` (**the living memory — read it for anything not
covered here**).
