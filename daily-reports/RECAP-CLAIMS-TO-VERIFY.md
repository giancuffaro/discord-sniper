# Room recap claims G asked me to verify (newest first)

## Optionality Pro daily recap — 2026-09-15 (pasted by G 9/17, "that's for you to verify later")
Claimed: 22 trades, 16 winners / 6 losers, 72.73% win rate, +1,356.83% total, +67.84% avg per call.
Their own rule: "For Swift, only trades that gained more than 25% are classified as green and included in the stats."

SWIFT: SPY 9/15 762C 1.02→3.07 +200.98% · AMD 9/16 515C 3.30→6.65 +101.52% · SKHY 9/18 180C 3.05→5.48 +79.51% · SPY 9/15 758P 0.63→2.30 +268.00% · SPY 9/15 757P 0.46→1.65 +262.64% · SKHY 9/18 185C 1.67→3.20 +92.19% · QQQ 9/15 710C 0.96→1.21 +25.39% · INTC 9/18 100C 2.11→3.15 +49.29% · DELL 9/18 625C 1.46→1.90 +30.58% · MUU 9/18 30C 0.65→0.90 +38.46% · SPX 9/15 7575P 0.46→1.35 marked −100%
WAXUI: SPY 0DTE 760P 1.30→3.10 +138.46%
DEMON: META 9/16 690C 1.90→3.64 +91.50% · QQQ 0DTE 703P 0.70→0 −100% · SPX 0DTE 7560P 0.80→0 −100%
BISHOP: INTC 9/16 101C 1.20→0.96 −20%
ROWDY: SPY 757P @0.38 +321% · SPY 9/21 750P +64%
SHYAMAL: SPX 0DTE 7605C 2.50→0 −100%
NAMROOD: SPCX 9/18 148C 2.63→2.98 +13.31% (marked red, "not significant enough")
FUTURES (MITRO): 2 wins 0 losses, +58 pts avg

TO CHECK against our own tapes / DS Logs: was each entry price actually posted at that price and time; is the exit the PEAK or a posted exit; what a follower entering at the first quote we saw would have made.
VERIFIED 9/17 with Webull's own 1-minute option bars (SDK get_option_history_bars — works on expired contracts): DEMON META 9/16 690C printed a high of 3.70 at 10:04 ET on 9/15. Their 1.90 -> 3.64 is REAL. My first look said "our tape's best bid that day was 2.09" — that was our quote tape going quiet on the contract after the bot's own position closed, not the market; I was wrong to read it as the day's high. DEMON QQQ 703P: 0.67/0.68 at 11:03, never above 0.69, went to ~0 — matches their -100%. The rest of the recap is NOT yet checked; the same bars call can check every line (entry price printed at the posted time? exit = the peak or a posted exit?).
