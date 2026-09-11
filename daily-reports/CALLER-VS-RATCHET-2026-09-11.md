# Caller entry versus our ratchet — 2026-09-11

The caller's posted premium is the hypothetical fill when available. Our 5/3/5 ratchet is replayed against the recorded Tastytrade bid path. Caller exits use their posted price/percentage, or the contemporaneous bid when they posted only the exit time.

| Alert | Source | Hypothetical entry | Entry basis | Caller result | Caller evidence | Our ratchet exit | Our ratchet result |
|---|---|---:|---|---|---|---:|---:|
| 10:01 NVDA | Platinum nitro | $2.15 | caller posted | full exit posted; price unavailable | caller exit; price unavailable | $2.04 | -5.1% / -11 (quote-path replay) |
| 10:25 TSLA | Platinum nitro | $1.79 | caller posted | full $1.24 (-30.7%) | market bid at caller exit | $1.79 | +0.0% / +0 (quote-path replay) |
| 10:37 NVDA | Platinum nitro | $0.97 | caller posted | full $0.98 (+1.0%) | market bid at caller exit | $0.84 | -13.4% / -13 (quote-path replay) |
| 12:01 HOOD | Honeydrip daytrades | $0.05 | first recorded ask; caller price absent | full -6.0% | caller-stated | $0.01 | -80.0% / -4 (quote-path replay) |
| 12:40 CPS | Demon day-trades | $0.65 | real fill = caller posted | unavailable | no paired caller exit | $0.70 | +7.7% / +5 (broker-confirmed actual) |

## Result

- Comparable ratchet paths: **5 of 34 observed**.
- Our ratchet on the **4 paths with a caller-posted entry**: **-19 per one-contract replay**.
- Including the one no-price alert at its first recorded ask: **-23 across all 5 paths**.
- Numeric caller full-exit results on this subset: **3 of 5**; missing caller exit prices prevent an honest aggregate caller P&L.
- Broker-confirmed results override quote-path simulations whenever the bot actually traded.
- This assumes the caller's posted price filled. It measures trade management from their original entry, not whether that fill was executable for us.
