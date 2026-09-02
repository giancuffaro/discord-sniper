# METHODOLOGY — how the ratchet backtest actually works
### Everything I did, every assumption, and what I got wrong
**9/2/26.** So you can check the work instead of taking my word for it.

---

## THE SHORT VERSION

**Real market data:** SPY, QQQ and the Mag 7, 1-minute bars, 8/27–9/01, straight from Webull's API.

**Modelled:** the option prices themselves. Webull sells no option history (`UNSUPPORTED_CATEGORY`), so every premium in the backtest comes from Black-Scholes, not from a chart.

**That's the weak link.** Everything else is arithmetic on real prices. If the option model is wrong, the conclusions are wrong — which is why the `TOS-CHECKSHEET.txt` exists.

---

## 1. THETA — how time decay is handled

Not bolted on. It falls out of Black-Scholes automatically, because the option is repriced **every single minute** with a shorter time to expiry:

```
T = (days_to_expiry × 1440 + (960 − minute_of_day)) / (365 × 1440)
```

960 = 16:00 in minutes. So at 09:35 on a 0DTE contract, T is 385 minutes; at 15:30 it's 30 minutes. Black-Scholes value scales roughly with **√T**, which is exactly why decay accelerates into the close rather than running at a constant rate.

**What that produces**, ATM SPY 0DTE with the underlying frozen:

| Time | Premium | Note |
|---|---|---|
| 09:31 | $2.16 | |
| 11:00 | $1.54 | |
| 13:00 | $1.15 | |
| 15:45 | $0.64 | ~70% of the premium gone, SPY never moved |

And the consequence that matters for your stop:

| Entered | Flat tape to hit a −10% stop |
|---|---|
| 09:35 | 27 min |
| 12:00 | 41 min |
| 15:00 | 18 min |
| 15:30 | **7 min** |

Theta alone spends your stop. That's not a modelling artifact — it's the shape of √T decay, and it's why your "tape hasn't moved in 5–10 minutes, get out" instinct is correct.

## 2. DELTA AND GAMMA

Also automatic. The premium is recomputed from the **actual SPY price on that minute's bar**, so it moves a fraction of the underlying's move, and that fraction changes as price travels through the strike. No linear approximation anywhere.

## 3. IMPLIED VOLATILITY — the one real estimate

This is the part I invented, and the part to be suspicious of.

**Base level.** Each symbol's IV comes from **its own realized volatility**, measured from the same 1-minute bars:

| | Realized | × premium | = IV used |
|---|---|---|---|
| SPY | 7.5% | 1.55 | 12% |
| QQQ | 10.6% | 1.55 | 16% |
| AAPL | 22.2% | 1.30 | 29% |
| NVDA | 24.4% | 1.25 | 30% |
| META | 25.6% | 1.28 | 33% |
| TSLA | 37.8% | 1.20 | 45% |

The multiplier is the variance risk premium — IV normally trades above realized. Higher on indices, lower on single names, which matches how those markets behave.

**Intraday shape.** For 0DTE: elevated at the open, sagging midday, firming into the close as gamma takes over.

```
base × (1 − 0.28·sin(π·frac) + 0.30·frac³)      frac = 0 at 09:30, 1 at 16:00
```

For multi-day contracts, a mild 6% drift down across the session.

**Smile.** IV rises as the strike moves away from the money:

```
× (1 + 4.5 · |ln(S/K)|)     for 0DTE
× (1 + 1.6 · |ln(S/K)|)     for weeklies
```

**Calibration target:** a 09:30 ATM SPY 0DTE call priced near $2.10–2.20, which is where they really trade. It lands at $2.16.

**This is a model, not a measurement.** It's the single biggest thing standing between the backtest and reality.

## 4. SPREADS — and why they decide everything

Your stop watches the **bid**, so the spread is what actually triggers it.

```
width = max(floor, mid × liquidity) × (1 + widen × frac)
  floor       $0.01 SPY/QQQ, $0.02 single names
  liquidity   1.2% SPY/QQQ, 2.2% single names
  widen       0.9 for 0DTE, 0.25 for weeklies   (wider into the close)
  and never less than $0.02 once the premium drops under $0.30
capped at 10% of mid
```

## 5. ENTRIES — matched to how your bot actually behaves

- **Direction** from the previous 5 minutes of the underlying — a momentum call, like a room makes. **Past bars only, no lookahead anywhere.**
- **Strike** ATM or exactly one rung OTM, using the real increment ($1 SPY, $2.50 NVDA, $5 TSLA). Your "never more than 1 strike OTM" rule.
- **Fill crosses the ask.** Your standing rule since 8/11.
- Contracts under $0.15 skipped — no room would call them.
- 14 entry times per day × 2 strikes × 9 symbols × 3 days = **520 trades**.

## 6. MANAGEMENT — identical for both rules

The stop watches the bid, minute by minute. Nothing else closes the position. Anything still open at 15:55 is marked out at the bid. Both rules see the **exact same** price series, so the comparison is apples to apples even where the price model is imperfect.

---

## WHAT I GOT WRONG — AND FIXED

**The flaw:** I priced every single-name contract as **2 days to expiry on every day**. That was just wrong:

| Day | Weekday | Real DTE to the Friday |
|---|---|---|
| 8/28 | Friday | **0** |
| 8/31 | Monday | **4** |
| 9/01 | Tuesday | **3** |

**Fixed and re-ran.** The conclusion held, and got less suspiciously clean:

| | Fixed 2 DTE (wrong) | Real per-day DTE |
|---|---|---|
| OLD | +2,436 | +849 |
| NEW | +6,433 | +4,704 |
| t | 2.93 | **2.42** |
| bootstrap | 100% | **100%** |
| better / worse | 95 / 69 | 100 / 72 |
| symbols improved | 9 of 9 | **6 of 9** |

Note how much the **absolute** totals moved — the model is genuinely sensitive to expiry assumptions. But the **relative** answer survived, because both rules see identical prices. That's the one structural protection this whole exercise has.

The corrected version is what to believe.

---

## WHAT IS *NOT* MODELLED

Honest list of everything absent:

- **Real bid/ask quotes.** Modelled, not measured. The big one.
- **Volatility surface dynamics** — no IV crush on events, no vol spikes on moves. IV follows a smooth curve; reality doesn't.
- **Liquidity and fill quality.** Every stop is assumed to fill at its trigger. Real stop-limits slip or don't fill.
- **Commissions.** $0 at Webull for stock/ETF options, so nearly right for you — but index options are $0.50/contract.
- **Assignment, early exercise, dividends.**
- **Sub-minute movement.** 1-minute bars. Your bot polls every 300ms, so real intraday spikes could trigger stops my model never sees. **This probably understates how often tight stops get hit** — a bias against the tiered rules, so the conclusion is conservative in that direction.
- **Your actual rooms.** Entries are my momentum proxy. This tests the **exit rule**, not your alerts.

## THE BIGGEST HOLE

**All three days were quiet.** SPY realized volatility was 7.5% — a calm tape. Nothing here has met a fast market, a Fed day, or an event gap.

A ratchet that behaves well in chop can behave very differently when things move. Of everything on this page, that's what I'd least want you to forget.

---

## HOW TO CHECK ME — 20 MINUTES, FREE

`TOS-CHECKSHEET.txt` lists six real contracts with dates, times, and what my model says each was worth. Chart them in thinkorswim and fill in the blanks.

**If you only check one number:** the SPY 0DTE ATM call at 09:35 on 9/01 — my model says **bid 1.10 / ask 1.12**. That single figure tells you whether my opening IV is sane, and opening IV drives everything downstream.

Within ~15% and the backtest stands up. Wildly off and I'll rebuild the IV term before you trust a word of it.

---

## THE FILES

| File | What it is |
|---|---|
| `opt_model.py` | Black-Scholes, IV term, spread model |
| `multi.py` | all nine symbols, per-symbol IV, expiries |
| `variants.py` | tier variants, the grid that came back non-monotonic |
| `twospeed.py` | anti-clip candidates, leave-one-out validation |
| `replay_real.py` | the SPY-only first pass |
| `TOS-CHECKSHEET.txt` | the check sheet above |

All runnable. `python multi.py` reproduces the table.
