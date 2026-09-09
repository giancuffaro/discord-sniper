# MARKET HOURS — what can trade, and when (all times ET)

Recorded 2026-09-08. Why it matters: an alert that lands outside its product's
session cannot fill. Options die at the afternoon bell; futures run almost around
the clock. The Felony NQ long @ 29580 that came in ~9:25 PM on 9/8 was a valid,
tradeable FUTURES entry (futures were open) — it was missed only because the Whop
feed wasn't reaching the bridge, not because of the hour.

## US EQUITY / ETF OPTIONS
- **Regular session: 9:30 AM – 4:00 PM ET**, Mon–Fri, minus holidays.
- **SPY, QQQ, IWM options: close 4:15 PM ET** (the extra 15 min — matches our
  existing rule "ETF options trade to 16:15"). Most other single-name equity
  options stop at 4:00 PM.
- **No overnight for options.** After 4:15 PM ET nothing options-side can fill.
- 0DTE reminder (unchanged): auto-exercises at $0.01 ITM — flatten before close.
- Half-days (day after Thanksgiving, Christmas Eve, etc.): **1:00 PM ET** close
  (index/ETF options 1:15 PM).

## CASH-SETTLED INDEX OPTIONS (SPX, NDX, RUT, VIX)
- **9:30 AM – 4:15 PM ET.** (SPX also has a separate overnight/global session on
  some venues, but we do not trade that.)

## FUTURES — CME Globex (equity index ES/NQ/MES/MNQ; metals GC/MGC/SI)
- **Sunday 6:00 PM ET → Friday 5:00 PM ET**, i.e. nearly 24 hours a day.
- **Daily maintenance halt 5:00 PM – 6:00 PM ET** (the one gap each weekday).
- So a futures alert on a weekday evening (like the 9:25 PM NQ long) IS in
  session and tradeable — this is where the after-hours edge is, and why the
  Whop futures rooms (FirstStepTrading Futures, Felony's NQ/ES/MGC calls) matter
  even when options are long closed.
- Topstep/prop rules still apply on top of these hours (Combine consistency lock).

## PRACTICAL RULE FOR THE BOT
- Between ~4:15 PM and next 9:30 AM ET: **only futures can fill.** Any options
  alert read in that window will not execute — expected, not a bug.
- Futures window closes Fri 5:00 PM ET and reopens Sun 6:00 PM ET; the daily
  5–6 PM ET halt is the only weekday gap.

## SOURCES
- CME Globex hours: https://www.cmegroup.com/trading-hours.html ; E-mini Nasdaq
  (NQ) specs: https://ninjatrader.com/futures/futures-contracts/equity-index/e-mini-nasdaq/
- Options hours (Nasdaq): https://www.nasdaqtrader.com/Trader.aspx?id=optionshours
