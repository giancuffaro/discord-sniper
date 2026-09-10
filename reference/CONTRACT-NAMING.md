# HOW EVERY BROKER AND FEED NAMES A CONTRACT

G, 9/10: *"find out how the contracts are named in every single broker, and
that would help us out too to identify what contract there as well."*

He is right that this matters, and it matters more than it looks. A wrong
contract symbol is not a cosmetic bug. It buys something nobody named, or it
points the watchdog at a contract we do not hold — and it does that **silently**,
because a well-formed wrong symbol looks exactly like a well-formed right one.

**One rule: `occ.py` is the only translator.** Nothing else in this project may
build or reshape a contract symbol. Every format below either comes out of
`occ.py` or is documented here so it can be added to it. If you find yourself
writing `"C" if side == "CALL" else "P"` anywhere, stop — that exact line is
what `occ.side_letter()` exists to kill (anything not the literal string
`"CALL"` became a **PUT**, silently).

---

## OPTIONS

One contract — NVDA, 18 Sep 2026, 235 call — in every dialect:

| where | symbol | built by |
|---|---|---|
| **OCC** (the standard) | `NVDA260918C00235000` | `occ.build()` |
| **Webull** | `NVDA260918C00235000` | same — Webull takes plain OCC |
| **Tradier** | `NVDA260918C00235000` | same |
| **Databento / OPRA** | `NVDA 260918C00235000` | root padded, see below |
| **tastytrade** | `NVDA  260918C00235000` | `occ.to_tasty()` — **root padded to 6** |
| **dxfeed / DXLink** | `.NVDA260918C235` | `occ.to_dx()` |

### The OCC layout, field by field

```
NVDA 260918 C 00235000
│    │      │ └── strike × 1000, zero-padded to 8 digits
│    │      └──── C or P
│    └─────────── expiry, YYMMDD
└──────────────── root, NOT padded in plain OCC
```

* **strike × 1000, 8 digits.** A $4 strike is `00004000`, a $243.50 strike is
  `00243500`. Half strikes are why the multiplier is 1000 and not 100.
* **the root is where the dialects differ.** Plain OCC leaves it alone;
  tastytrade pads it to **6 characters with spaces** (`NVDA  `, `SPY   `), and
  OPRA/Databento pads similarly. The padding is easy to miss and produces a
  symbol that *looks* right and is rejected by the venue. That is exactly why
  `to_tasty()` lives in `occ.py` and not in `tastytrade.py`.

### dxfeed is the odd one out

```
.NVDA260918C235          leading DOT, plain strike, NO padding
.IWM260918P243.5         a half strike keeps its decimal
```

Never hand-build this. `occ.to_dx()` and `occ.from_dx()` round-trip it.

### Index roots carry a W

`SPX` is the monthly, **`SPXW` is the weekly** — and nearly every room call is
the weekly. Same for `RUT`/`RUTW`, `NDX`/`NDXP`. Getting this wrong finds a
real, tradeable, wrong contract. Verified builds:

```
SPXW260911P07650000      SPXW, 11 Sep 2026, 7650 put
SPY260911P00660000       SPY,  11 Sep 2026,  660 put
IWM260918P00243500       IWM,  18 Sep 2026,  243.5 put   (half strike)
ABAT260821C00004000      ABAT, 21 Aug 2026,    4 call    (penny name)
```

### What each venue will and will not do

| | historical prices | live quotes | greeks |
|---|---|---|---|
| Webull | **none** | yes (60/min per endpoint) | no |
| Tradier | stocks only (1-min ~3 wks, daily years) | yes | yes |
| tastytrade | none | yes (DXLink stream) | **yes, streamed** |
| Databento OPRA | **yes — the only source** | licence needed | no |

**This is the whole reason we ever pay Databento.** Everything above the last
row is free and already connected, so pull from a broker first, every time.
`option_tape.csv` is our own growing record and it shrinks that bill further.

---

## FUTURES

Same contract — E-mini Nasdaq, September 2026 — in every dialect:

| where | symbol | notes |
|---|---|---|
| **Webull** | `NQU6` | root + month letter + **1-digit** year |
| **CME / Databento** | `NQU6` or `NQZ6` | same shape |
| **ProjectX / Topstep** | `CON.F.US.ENQ.U25` | its own contract id — **must be looked up**, a plain symbol is refused |
| **NinjaTrader (OIF)** | `MNQ` / `NQ` | the plain root; NT resolves the front month itself |
| **the rooms** | `MNQ1`, `/MES`, `NQ` | whatever they feel like — see `FUT_SYMS` in parser.js |

### The month letter

```
F Jan   G Feb   H Mar   J Apr   K May   M Jun
N Jul   Q Aug   U Sep   V Oct   X Nov   Z Dec
```

Index futures are **quarterly**: only H, M, U, Z. `NQU6` = Sep 2026.

### Front month is a lookup, never a guess

`webull_futures.front_month()` asks the broker which contract is actually
tradable (`status` **OC** = open, **CO** = liquidate-only, **NT** = no-trade)
and takes the nearest expiry in the future. It falls back to the computed
quarterly code only if the SDK will not answer. Rolling happens mid-September
and mid-December; a hard-coded `NQU6` is a bug with a delivery date on it.

### Sizes and ticks that decide the money

| root | tick | $/point | $/tick |
|---|---|---|---|
| NQ | 0.25 | $20 | $5.00 |
| MNQ | 0.25 | $2 | $0.50 |
| ES | 0.25 | $50 | $12.50 |
| MES | 0.25 | $5 | $1.25 |

The micro is **1/10th** of the e-mini. Against a small futures account the
micro is the only sane instrument: a 38-point loss is **−$760 on NQ** and
**−$76 on MNQ**.

---

## OPTION TICK SIZES (they are not all a penny)

Getting this wrong gets the order rejected, not filled badly:

* **SPY / QQQ / IWM** — $0.01 always.
* **Penny Program names** — $0.01 under $3, $0.05 at $3 and above.
* **everything else** — $0.05 / $0.10.

---

## THE RULES THAT COME OUT OF ALL THIS

1. **`occ.py` builds every symbol.** No exceptions, no local copies. It once
   lived in seven places and they disagreed.
2. **`side_letter()` RAISES on anything it cannot read.** A refused build is a
   missed trade; a silent flip is the opposite trade.
3. **Front months are looked up, never computed** unless the broker refuses to
   answer.
4. **Broker data before paid data**, always. Only OPRA history has no free
   substitute.
5. **A symbol that parses is not a symbol that is right.** `optionable.txt`
   (6,387 roots from the broker's own universe) is checked in three places now
   — parser.js, background.js and bridge.py — because a well-formed wrong
   symbol is indistinguishable from a right one until the fill comes back.

Last verified 9/10/26 against live `occ.py` output and a live Webull futures
instrument query (`NQU6`, size 20, min tick 0.25, settles 2026-09-18).
