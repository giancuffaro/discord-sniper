# DISCORD SNIPER — THE MAP
Written 2026-09-07. **Every fact below was read out of the source with an AST
parse, not recalled.** That matters: this file exists because a session kept
getting seams wrong from memory, and a map written from memory would have
repeated the mistake in a more authoritative font.

`HANDOFF.md` is the living memory — what the rules ARE and why.
**This file is the wiring diagram — what EXISTS and what talks to what.**
Where they disagree, the source wins and both get fixed.

---

## WHY THIS FILE EXISTS

One session made eight mistakes. Not one was a logic error — the math was
right every time. Every single one was at a **seam**:

| mistake | kind |
|---|---|
| called `client_from_settings()` | name that does not exist |
| called `balance()` | wrong name (it is `buying_power()`) |
| `WebullOptions(cfg["execution"]["webull"])` | wrong input — it wants the WHOLE config |
| called `occ_for()` | name that does not exist |
| read `QUOTES.get` as `(bid, ask)` | wrong output — it returns `(ask, bid, row)` |
| `return (False, msg)` from `do_POST` | wrong output — HTTP handlers return `self._reply(...)` |
| backed off on an exception | wrong failure mode — a 429 here returns `[]`, it never raises |
| sized a log window at "120 KB/minute" | invented constant |

**Seams are where this system hurts.** Sizes are not the problem
(26,463 lines of Python across 42 files, 8,995 lines of JS across 8). The
problem is that a wrong guess about an interface compiles cleanly, passes
tests, and fails at 9:31 with real money on it.

**So: before calling anything across a module boundary, look it up here or
in the source. Never from memory. Never from a plausible-sounding name.**

---

## THE CHAIN, END TO END

```
  26 Discord/Whop rooms
        |  Chrome MV3 extension  (extension/*.js, 8,995 lines)
        |    content.js   reads the DOM, stamps postedAt from <time datetime>
        |    background.js parses -> order JSON -> HTTP POST
        v
  bridge.py   127.0.0.1:8787      5,134 lines — the spine
        |    do_POST  validates, gates, refuses
        |    place()/_place_impl  builds and sends the order
        v
  positions.py  (Book)            3,983 lines — owns state and EXITS
        |    ratchet, stops, trims, adoption, reconciliation
        v
  webull_options.py (WebullOptions) 2,283 lines — the only thing that
        |                            actually talks to the broker
        v
  Webull OpenAPI       real orders, real money
```

**Feeds hanging off the spine:**

```
  quote_bus.py   OPTION quotes   POLLED 1/sec   (Webull has no option stream)
  stream_bus.py  stock prices    PUSHED via Webull MQTT
  dxlink.py      greeks + shadow quotes   PUSHED via tastytrade DXLink
  tradier.py     stock quotes, minute bars   REST
  props.py       futures: Topstep/ProjectX, NinjaTrader
```

---

## MODULE OWNERSHIP — one line each, and who imports whom

Dependency edges below are the REAL import graph.

| module | lines | owns |
|---|---|---|
| `bridge.py` | 5134 | HTTP door, order gates, orchestration, all the watchdog threads |
| `positions.py` | 3983 | the Book: position state, ratchet, stops, trims, P&L |
| `signals.py` | 2350 | the PYTHON MIRROR of the JS parser (parity-tested, not in the live path) |
| `webull_options.py` | 2283 | every Webull call. Nothing else may talk to the broker |
| `dxlink.py` | 712 | stdlib WebSocket + GreeksBus + shadow quote stream |
| `guards.py` | 608 | pre-trade refusals |
| `props.py` | 593 | futures brokers (Topstep/ProjectX, NinjaTrader) |
| `tastytrade.py` | 556 | tastytrade OAuth + REST |
| `announcer.py` | 532 | posts fills/milestones to G's Discord |
| `telemetry.py` | 509 | per-fill latency chain + entry math -> telemetry.csv |
| `webull_futures.py` | 446 | Webull futures leg |
| `tradier.py` | 404 | Tradier REST |
| `quote_bus.py` | 385 | the 1/sec option quote poller + rate Budget |
| `health.py` | 377 | connection health, measured |
| `pullback.py` | 351 | round-number pullback entry hunt |
| `greeks_math.py` | ~230 | delta/gamma/theta arithmetic. Pure, no I/O |
| `ratchet_tiers.py` | ~300 | the ladder. ONE copy of the rule |

```
bridge          -> ai_reader, broker, dxlink, eastern, positions, props,
                   pullback, quote_bus, stream_bus, telemetry,
                   webull_futures, webull_options
positions       -> ratchet_tiers, telemetry, webull_options
broker          -> tastytrade, tradier, webull_options
telemetry       -> greeks_math
health          -> broker, webull_options
caller_report   -> telemetry
webull_futures  -> bridge, positions          <-- SEE THE WARNING BELOW
```

### ⚠️ ONE CIRCULAR DEPENDENCY, FOUND WHILE MAPPING

`bridge` imports `webull_futures`, and `webull_futures` imports **both**
`bridge` and `positions`. That cycle is real and it is in the source today.
It works because the imports are late/inside functions, but it means import
order can matter and a careless move at the top of either file can break
startup. **Do not "tidy" either import without testing a cold start.**
Not fixed here — this file is a map, and unwinding a cycle in the order path
is not a documentation change.

---

## CONSOLIDATED 9/7 — three jobs the app was doing in many places

**`occ.py` — what a contract is called.** Was SEVEN implementations
(`webull_options.occ_symbol`, `bridge._occ_build`, `positions._occ_for`,
`bars_capture.occ`, `dxlink.occ_to_dx`, `quote_shadow.dx_to_occ`, plus an
eighth written inline in `bridge.py` on 9/6). All now delegate to `occ.py`;
**zero hand-rolled `strike*1000` constructions remain outside it.** Output
is byte-identical on every shape (parity-tested).

It also removes a live landmine. `occ_symbol` decided the side with
`cp = "C" if option_type == "CALL" else "P"` — so `"CALLS"`, `"call"`,
`"c"`, `None` all silently became **PUTS**, and five call sites each
repeated `"CALL" if side.startswith("C") else "PUT"` to stay clear of it.
`occ.side_letter()` accepts every real spelling and **raises** on anything
else. A refused build is a missed trade; a silent flip is the opposite trade.

**A second landmine found the same way, one day later (9/8).** `_ymd()`
stripped every `-`/`/` and then just counted digits, always assuming what
was left was `YYYYMMDD`. `2026-08-14` and zero-padded `08/28/2026` both
collapse to 8 digits that way, and only the first one is actually in that
order — `08/28/2026` silently became expiry `282026` (YY=28 MM=20 DD=26), a
well-formed WRONG date with no error anywhere. `11/20/26` hit the same bug
the other direction (6 digits, read as-is instead of M/D/YY). Found
backfilling `days/*.json` through Databento, which refused the resulting
garbage symbol outright — a broker that accepted it instead would have
bought whatever contract that nonsense date happened to resolve to. Fixed
by reading the year from WHICH piece is 4 (or 2) digits and where it sits,
before the separators that carried that information are thrown away.

**`tape.py` — one reader for everything recorded.** The price files record the
same contracts at the same moments in several schemas and two symbol formats
(`option_tape.csv` and `databento_tape.csv` key on OCC, the other two on
dxfeed). Every tool had to know all three original ones and join by hand —
`quote_shadow.py` did it with `bisect`. `tape.rows()` / `tape.at()` /
`tape.contracts()` do it once, in OCC form. The READ side only: the writers
still own their own files, because Webull keeps no historical option prices
and the live-recorded tapes cannot be regenerated. `databento_tape.csv` is
the one exception that CAN be regenerated — it's a backfill from OPRA via
`databento_backfill.py` (9/8), covering calls the live feeds never saw
(refused, missed, never filled), re-runnable and idempotent. The live
`alert_tape.csv` all-alert recorder is registered as source `alert`, so its
refused/missed-contract snapshots use the same reader and can support
caller-exit comparisons.

**Atomic state writes.** `save_state`, the extra-account books and
`save_day` used `open(path, "w")`, which truncates first. A crash mid-write
left a torn `state.json`, and `load_state` swallowed the parse error and
returned — booting an EMPTY book while real positions sat at the broker with
no stop management. A kill-mid-write drill measured it: **29 of 40 kills
produced a corrupt file.** Now `.tmp` + `fsync` + `os.replace`, one `.bak`
kept, and `load_state` shouts and tries the backup. Same drill after: 0/40.

**Still pending: `signals.py`.** 2,350 lines of Python that mirror the real
JS parser and are imported by nothing in the live order path — only
`jsparse` (as a fallback), `dump_parse` and its own test. Deleting it is
**gated on confirming Node.js is installed on the trading PC**, because
`scoreboard`, `replay_check` and `audit_history` parse through `jsparse` and
would otherwise go dark. `jsparse` now prints a loud warning and sets
`USED_MIRROR` whenever it falls back; `health.py` reports whether node is
present.

---

## THE SEAMS — exact signatures, copied from the source

These are the interfaces that got me. Look here first.

### `webull_options.WebullOptions` — the ONLY broker path

**Constructor takes the WHOLE settings dict.** It digs out
`cfg["execution"]["webull"]` itself. Handing it the sub-dict yields an empty
`app_key` and a silent, fabricated "connection failure".

```python
cl = WebullOptions(settings)     # RIGHT
cl = WebullOptions(settings["execution"]["webull"])   # WRONG, looks fine
acct = cl.connect()              # MUST be called first — account_id is
                                 # blank in settings (auto-pick). Without
                                 # it, buying_power() reads account None
                                 # and returns None.
```

Public methods, verbatim:

```
connect()                     ask_bid(occ)        ask_bid_many(occs)
stock_price(symbol)           buying_power()      futures_buying_power()
afford_check(limit, qty)      order_status(order_id)
last_sell_fill(symbol, side, strike, expiry, since=None)
open_orders(symbol=None)      cancel(order_id)
positions()                   futures_positions()  flatten(symbol)
place_stop(symbol, side, strike, expiry, qty, fill_price, stop_price=None)
replace_stop(old_oid, symbol, side, strike, expiry, qty, fill_price, stop_price)
buy(symbol, side, strike, expiry, qty, their_price=None, price_mode=None,
    bracket_stop_pct=None)
sell(symbol, side, strike, expiry, qty, ref_price=None, urgent=False)
entry_limit(bid, ask)
```

There is **no** `balance()`. There is **no** `client_from_settings()`.

**FAILURE MODE THAT COST ME A WHOLE FIX:** a 429 does **not** raise.
`_try_calls` catches the throttle and returns `(None, why)`, so
`futures_positions()` hands back `[]` — indistinguishable from "flat". Any
retry/backoff built around `except` will never fire. **Detect throttling by
the EMPTY RESULT, not by an exception.**

### `quote_bus.QuoteBus` — option quotes, polled

```python
QUOTES.get(occ, max_age=STALE_AFTER)   # -> (ask, bid, row)
                                       #     ASK FIRST. Not (bid, ask).
QUOTES.watch(occ) / unwatch(occ) / watching() / age(occ) / status()
QUOTES.record_to(path) / tape(occ, bid, ask, now=None)
```

Getting that tuple order backwards inverts every mid computed from it, and
nothing crashes.

### `quote_bus.Budget` — the shared rate limiter

```python
take(n=1, priority=False, timeout=10.0, reserve=0.0)
```

**`priority=True` is never passed by any caller.** What actually protects
orders is `ORDER_RESERVE = 40.0`: the quote sweep will not drain the last 40
tokens, and orders bypass the Budget entirely via `_pace()` (a 200 ms
spacer). Do not describe this as a "priority lane" — it is a reserve floor.

### `dxlink.GreeksBus` — greeks, and the shadow quote stream

```python
get(occ, max_age=30.0)     # -> greeks dict or None
quote(occ, max_age=30.0)   # -> (bid, ask)  SHADOW ONLY, zero call sites
watch/unwatch/start/stop/status/quote_tape_to(path)
```

**Only carries contracts we HOLD** — `watch()` is driven by open positions.
No position, no data. An empty `quote_shadow.csv` is not a fault.

**HARD RULE: never open a second DXLink session.** tastytrade caps
concurrent sessions per account. On 9/7 a probe opened one and forced three
`refused RE-AUTH` errors on the live feed. Market Sniper held the other.
Read DXLink health from `bridge.log`, never by connecting.

### `bridge.do_POST` — the HTTP door

Refusals return **`self._reply(code, message)`**, not a tuple. A bare
`return (False, msg)` leaves the extension with no HTTP response, which
looks exactly like a dead bridge and triggers a retry.

### `positions.Book` — 38 public methods

Too many to list; read the source. The ones that decide money:
`entry_sent`, `trim`, `claim`, `release`, `finish`, `adopt`,
`reconcile_gone`, `auto_ratchet`, `auto_ladder`, `auto_breakeven`,
`rearm_overnight_stops`, `force_drop`.

---

## DATA FILES — who writes, who reads

| file | written by | read by | replaceable? |
|---|---|---|---|
| `option_tape.csv` | bridge | quote_shadow | **NO — irreplaceable** |
| `greeks_tape.csv` | bridge | — | **NO** |
| `quote_shadow.csv` | bridge (dxlink) | quote_shadow | **NO** |
| `telemetry.csv` | telemetry | caller_report | **NO** |
| `alert_decay.csv` | telemetry | — | **NO** |
| `shadow_ratchet.csv` | positions | — | **NO** |
| `trades.log` | bridge | audit_history, bars_capture, ratchet_lab, replay_check, thetadata_probe | **NO** |
| `journal.csv` | bridge | caller_report | rebuildable from broker |
| `settings.json` | bridge + all setup_* | everything | **NO — holds every key** |
| `state.json` | bridge | bridge | yes |
| `health.csv` | health | — | yes |
| `rooms.txt` | bridge, rename_rooms | scoreboard | yes |

**Webull keeps NO historical option prices.** Anything not recorded live is
gone forever. That is why the tapes are marked irreplaceable and why they
are gitignored rather than committed (committing logs put 68 MB in `.git`).

---

## THE 21 ENTRY POINTS

Live: `bridge.py` · `announcer.py`
Setup: `setup_keys` · `setup_tastytrade` · `setup_tradier` · `check_keys`
Look at results: `caller_report` · `scoreboard` · `now` · `health` ·
`quote_shadow` · `telemetry`
Research/replay: `ratchet_lab` · `bars_capture` · `audit_history` ·
`replay_check` · `thetadata_probe`
Maintenance: `rename_rooms` · `dump_parse`
Tests: `test_*`

---

## THE RULES THIS MAP ENCODES

1. **Only `webull_options.py` talks to Webull.** No exceptions.
2. **`positions.py` owns exits.** The ratchet lives in `ratchet_tiers.py`,
   one copy, and Market Sniper must match it.
3. **A 429 returns empty, it does not raise.** Detect on the result.
4. **`QUOTES.get` is (ask, bid, row).**
5. **`WebullOptions` takes the whole config, and needs `connect()` first.**
6. **HTTP handlers reply with `self._reply`.**
7. **One tastytrade DXLink session, ever. Discord Sniper owns it.**
8. **Nothing assumed, nothing guessed** — real data, polled or pulled. Test
   data is for proving plumbing, and must be labelled as such
   (`telemetry.integrity_of` -> BROKER / ASSUMED / PAPER / BLIND / UNKNOWN).
9. **Never run git write commands from a sandbox.** AUTO PUSH holds the lock.
10. **Compile-check everything touched. Bump `extension/manifest.json` on
    any extension change.**

## HOW TO KEEP THIS FILE HONEST

Prose goes stale silently — that is the known weakness of a map. The import
graph, the module sizes, the public signatures and the data-file table were
all machine-extracted and can be re-extracted the same way in a minute. When
something here contradicts the source, **the source wins**: fix the code if
the code is wrong, fix this file if this file is wrong, and never leave both.
