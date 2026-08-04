# Futures reader — drill findings

> **STATUS Aug 3, evening:** P0 bugs 1–4 and P1 bugs 5–6 are FIXED in BOTH
> parsers (signals.py and extension/parser.js), locked into samples.txt, and
> test_parity holds them — all 364 lines read identically. Also landed: the
> stale-repost guard, bridge-failure auto-disarm, assumed-fill labeling in the
> day P&L, and bridge.log rotation. **The extension must be reloaded in Chrome
> (chrome://extensions → ↻) before the changes are live in the browser.**
> Still open: bugs 7–11 below (missed calls only, no wrong trades).
>
> **OPTIONS drill (same evening):** 60 adversarial lines. Fixed in both
> parsers via a post-parse guard wrapper (inner paths untouched): SELL calls
> no longer read as buys ("SPX 7565 C SELL" bought the call HE was selling),
> zero/absurd strike+premium bounds, dot-tickers ($BRK.B parsed as ticker B)
> refused, "was in"/"almost"/"tomorrow if" vetoes, WIN/GAIN/LOSS delisted as
> tickers. Expired-expiry check added at the BRIDGE (single choke point,
> dry + real): recent-past dates refuse, >60 days rolls to next year (LEAPs).
> Parity: all 376 lines identical. Known-open, documented not fixed:
> conditional break entries fire immediately (room convention, by design);
> "(edited)+old date" export artifact fires in drill only — live path
> dedupes by DOM identity; "Entry: 82.00" vs 0.82 typos pass the bounds
> (affordability check is the net on small accounts).

Two drills, 111 synthetic lines, run through `drill.py` and a session-level replay reusing
`signals.py` + `guards.py`. `execution.mode` stayed `dryrun` throughout; no repo file was modified.

Ordered by what they cost you, not by how hard they are to fix.

---

## P0 — would open a position that was never called

### 1. A count in a sentence is read as the price

| Message | Reads as |
|---|---|
| `I've been long NQ 3 times this week` | **OPEN NQ @ 3** |
| `short NQ 2 contracts here` | **OPEN NQ @ 2** |
| `long ES 4 lots` | **OPEN ES @ 4** |
| `went long MNQ 1 con only` | **OPEN MNQ @ 1** |
| `long CL 2 handles from here` | **OPEN CL @ 2** |
| `short NG 10 cents and I'm out` | **OPEN NG @ 10** |

`RE_FUT_ENTRY` takes the first number after the symbol as the price. It has no idea that
"3 times", "2 contracts", "4 lots" are counts.

Why this is the worst one: **a sell limit far below the market is marketable.** `short NQ 2
contracts here` places a sell at 2 while NQ trades near 28660 — that fills instantly at the
market, and you are short a contract nobody called. The long side is safer (a buy limit at 3
never fills) but still writes a phantom position into the book, which then blocks the real
entry with *"you're already in NQ"* and mis-routes every trim that follows.

**Fix:** reject when a unit word (`times`, `contract(s)`, `con(s)`, `lot(s)`, `handle(s)`,
`cent(s)`, `tick(s)`, `point(s)`) follows the number, and require the price to be within a
plausible band for the symbol.

### 2. Any sentence starting "Stopped" or "Stopping" closes your position

| Message | Reads as |
|---|---|
| `Stopped by the store, back in 20` | **CLOSE** |
| `Stopping for lunch, back at 1` | **CLOSE** |
| `stopped out of my personal trade, room trade still on` | **CLOSE** |

`RE_STOP_HIT` is start-anchored on `stopp(ed\|ing)` with nothing after it. The third one is
the sharpest: the message says explicitly that the room trade is still on, and the bot closes
the room trade.

**Fix:** require a trading object nearby — `stopped out`, `stop hit`, a symbol, a points/%
figure — and exclude a following preposition (`by`, `for`, `at the`).

### 3. No sanity bound on price at all

```
Long NQ @ 0          -> fire=True  limit=0.0
Long NQ @ 0.01       -> fire=True  limit=0.01
Long NQ @ 286600000  -> fire=True  limit=286600000.0
```

Nothing rejects a zero, a near-zero, or a nine-digit price. Combined with bug 1 this is how a
typo becomes a filled order.

**Fix:** per-symbol plausible range, refuse outside it. Refusing loudly is already the house
style in `webull_futures.py`; this should match.

### 4. Context that cancels the trade is ignored

| Message | Reads as |
|---|---|
| `Short NQ @ 28660 — actually cancel that, no fill` | **OPEN NQ @ 28660** |
| `Short NQ @ 28660 (paper account only, not my real one)` | **OPEN NQ @ 28660** |
| `Last week's long ES 7400 is still my best trade` | **OPEN ES @ 7400** |
| `My PnL: long NQ 28660 -> 28720 = +60` | **OPEN NQ @ 28660** |

The chatter guard already catches `do not`, `thinking`, `yesterday`, `recap`, `anyone` — and
those all worked correctly in the drill. These four slip through because the words aren't on
the list.

**Fix:** add `cancel`, `no fill`, `paper account`, `last week`, `pnl`, `->`, `p/l`.

---

## P1 — silently misses a real call

### 5. Three-decimal prices truncate to the integer

```
Long NG @ 3.412   -> OPEN NG @ 3.00
Long CL @ 66.405  -> OPEN CL @ 66
Long ZB @ 118.125 -> OPEN ZB @ 118
```

`RE_FUT_ENTRY` ends `(?:\.\d{1,2})?`. Natural gas, crude and treasuries all quote in 3+
decimals. The stop is then computed from a base up to 14% wrong.

**Fix:** `\.\d{1,3}` — or `\.\d+` and round per symbol tick.

### 6. `/NQ` does not parse, but `$NQ` does

```
Long /NQ @ 28660  -> NO MATCH
Long $NQ @ 28660  -> sym=NQ
Long NQ @ 28660   -> sym=NQ
```

The slash is the *more* common futures convention and it's the one that fails. Note
`/MES | LONG HERE` works — that's the separate Bullwinkle pattern, so the two paths disagree.

**Fix:** `[\$/]?` in place of `\$?`.

### 7. GOLD / SILVER / PLATINUM never resolve

`FUT_NICKNAMES` maps them but nothing on the entry path consults it, and the symbol group is
`[A-Za-z0-9]{1,4}` — SILVER (6) and PLATINUM (8) can't even be captured. GOLD is captured and
then dropped for not being in `FUT_SYMS`.

### 8. Only 15 symbols are supported

```
FUT_SYMS = CL ES GC M2K MCL MES MGC MNQ MYM NG NQ RTY SI SIL YM
```

Missing and silently ignored: **ZB ZN** (treasuries), **6E 6J** (FX), **HG** (copper),
**PL PA** (platinum/palladium), **ZC ZS** (grains), **MBT** (micro bitcoin).

### 9. Symbol-first phrasing is inconsistent

| Message | Result |
|---|---|
| `NQ short @ 28660 stop 28700` | fires |
| `NQ long 28660` | ignored |
| `es long 7455` | ignored |
| `si long 41.85` | ignored |
| `long si @ 41.85` | fires |

Symbol-first only works when an `@` is present. `RE_FUT_DIR_SYM` has the
`([A-Za-z0-9]{1,4})\s+(long|short)` branch, so this looks like the branch isn't reached from
the entry path.

### 10. Gerunds unsupported

`Shorting NQ @ 28660` and `Longing MNQ @ 28490` both ignored. `RE_FUT_ENTRY` matches only bare
`short|long`.

### 11. Others

- `Long NQ 28660 and long ES 7455` — only NQ is taken, ES silently dropped.
- `Target hit $1700 a contract` — ignored without a trim verb, though the code comment lists it
  as a supported format. `trim $800 a con` works.
- `flat NQ` — ignored. Common exit phrasing.
- `Long NQZ5 @ 28660` — explicit contract codes not recognised.
- `Long NQ Dec @ 28660` — fires, but the month is discarded; front-month is assumed.

---

## Worked correctly — don't regress these

Case-insensitivity (`LoNg nQ`), thousands separators (`28,660.75`), quarter-tick precision
(`.25`/`.75` survive), markdown wrappers (` ``` `, `>`, `**`), trailing `@everyone`, negative
prices refused, duplicate entry in one message taking only the first, and the whole chatter
guard set: `do not`, `thinking`, `yesterday`, `recap`, `anyone`, plus conditional phrasing
(`If NQ breaks 28700…`, `Looking to short NQ around…`) and `I'm long NQ from 28500`.

---

## Suggested order for tomorrow

1. Bug 2 — one regex, closes a live position on a lunch message
2. Bug 1 — unit-word rejection, the only one that opens an uncalled position
3. Bug 3 — price bounds, cheap insurance behind both of the above
4. Bug 5 — one character, `\d{1,2}` to `\d{1,3}`
5. Bug 6 — one character, `\$?` to `[\$/]?`

1–5 are small and independently testable. Re-run both drill files after each; every line above
is already a regression test.
