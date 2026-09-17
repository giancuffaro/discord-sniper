# BRIEF — week of Mon Sep 14 2026 to Sun Sep 20 2026. Newest day first; each day under its ===== header; a re-run replaces that day's block (reports.py).

===== Thu Sep 17 2026 =====

# SNIPER BRIEF — 2026-09-17

## Day
- Webull margin day P&L: +$227.1 net · +$233 gross on 65 broker legs (the gap is fees)
- Balance: NLV $1165.93 (+$227.12 vs 2026-09-16) · option BP $1165.93 · read 2026-09-17T18:18:50
- Webull futures: -$132.62 net · -$120 gross, $12.62 fees on 15 fills · NLV $256.64
- ALL ACCOUNTS, net of fees: +$94.48 (margin +$227.1, futures -$132.62)
- Bot: +$2 · 15 trades, 10 contracts  (1 with no P&L)
- Hand (G): +$232 · 16 trades, 51 contracts
- Ledger day total: +$234 (options only)

## Bot trades
```
time   channel             trader           tkr    contract         in    out        $  why exited
--------------------------------------------------------------------------------------------------
09:39  Aristotle           👑KingBeeAri🐝     SNDK   1800C 9/18        ?      ?       $0  unavailable  ⚠ journal ≠ broker
09:56  Whop Day Trades     Trademorewiser…  NVDA   217.5C 9/18    2.55   2.69     +$14  ratchet
10:03  OWLS all-alerts     MuggZone         MRNA   165C 9/18         ?      ?       $0  unavailable  ⚠ journal ≠ broker
10:12  Platinum ei-alerts  PT | ei trades   TSLA   382.5C 9/18    1.22   1.25      +$3  ratchet
10:14  Honeydrip daytrad…  Brett            SPY    760C 9/18         ?      ?       $0  unavailable  ⚠ journal ≠ broker
10:17  Aristotle           👑KingBeeAri🐝     INTC   111C 9/21      2.04   2.04      +$1  born stop
10:18  Aristotle           👑KingBeeAri🐝     INTC   111C 9/21      2.03      ?        ?  close
10:23  OWLS all-alerts     MuggZone         ORCL   160C 9/25         ?      ?       $0  unavailable  ⚠ journal ≠ broker
10:24  Vero 1              @vero-alerts     QQQ    716C 9/17         ?      ?       $0  unavailable  ⚠ journal ≠ broker
10:29  Vero 1              Vero             QQQ    716C 9/17         ?      ?       $0  unavailable  ⚠ journal ≠ broker
10:44  Mugzone Options     MuggZone         SMCI   41C 9/25       1.50   1.42      -$8  born stop
10:56  Vero 2              Vero             QQQ    715P 9/17      1.32   1.24      -$8  born stop
12:29  Demon day-trades    Demon × LKS      AAPL   340C 9/21      1.40   1.40       $0  BE stop
12:45  Brando Alerts       EliteOptions |…  DELL   600C 9/18      4.95   4.95       $0  BE stop
12:45  Brando Alerts       EliteOptions |…  DELL   600C SEPT 18   4.95   4.95       $0  BE stop
```
⚠ 6 rows: the journal says it exited, the broker record prices no exit.
entry slack (OFF, measured): 6 no-fills today; nothing beats today's rule: every slack level from 2% to 10% comes out behind it (-$13 to -$234), and the 95% band on 156 paired orders (-$2.58 .. -$0.49 per order) CLEARS zero

## Callers right / wrong
**Right**
- @Owner Alerts TSLA 377.5C +48.0% (trim) — bot: no
- Brett SPY 760C 9/18 +13.0% (trim) — bot took it: $0
- Brett TSLA 372.5C 9/18 +70.0% (trim) — bot: no
- Brett SPY 760C 9/18 +6.7% (full) — bot took it: $0
- Mike AMZN 250C 9/18 +3053.2% (full) — bot: no
- MuggZone HOOD 110C 9/18 +50.0% (trim) — bot: no
- MuggZone SMCI 41C 9/25 +50.0% (trim) — bot took it: -$8
- Skyy QQQ 716C +50.0% (trim) — bot: no
- TB22 AAPL 340C 9/18 +108.3% (trim) — bot: no
- Trademorewiser (MOD) NVDA 217.5C +22.0% (trim) — bot took it: +$14
- Unraveller GOOGL 342.5C 9/18 +65.0% (trim) — bot: no
- Vero QQQ 715P 9/17 +51.5% (full) — bot took QQQ 716C 9/17: $0
**Wrong**
- @vero-alerts QQQ 716C 9/17 -14.4% (full) — bot took it: $0
- Mike TSLA 362.5P 9/18 -37.7% (full) — bot: no
- MuggZone MRNA 165C 9/18 -47.7% (full) — bot took it: $0
- MuggZone AMD 170C 9/18 -30.6% (trim) — bot: no
- Unraveller GOOGL 345C 9/18 -13.9% (full) — bot: no
- Unraveller GOOGL 345C 9/18 -39.2% (full) — bot: no
- Vero SPY 761P 9/17 -12.8% (full) — bot: no
unscored (no exit price — never estimated): shoof-alerts SNDK 1650C 9/18, Trademorewiser (MOD) MNQ, 👑KingBeeAri🐝 AMD 555C 9/18, 👑KingBeeAri🐝 INTC 111C 9/21, 👑KingBeeAri🐝 SNDK 1800C 9/18
ratchet replay: unavailable (no CALLER-VS-RATCHET block for 2026-09-17)

## What broke
- REFUSED 2 — OPEN QQQ — 716C 2026-09-17 asks 0.91 but the caller said 105.00; no listed expiry matches, not buying the wrong contract
- POSTCHECK PROBLEM 8 — FAILED INTC — PROBLEM: book holds INTC, the account doesn't
- STOP-WARN 12 — INTC — Webull wouldn't hold a resting stop (HTTP Status: 417, Code: OPENAPI_OPTION_LONG_POSITION_MUST_BE_CLOSE_THAN_SEL…
- EXPIRY 4 — QQQ 716C had no date — using 2026-09-17: today (2026-09-17) IS a listed expiration for QQQ, so 0DTE it is
- AI READ 9 — saved key check: verified (HTTP 200)
- MIRROR — bars unavailable, 9 alert(s) unscored: BentoClientError: 422 data_end_after_available_end

## Pending (G's action)
- Market Sniper: apply HANDOFF-RATCHET-2026-09-09.md (options 5→2 rung, futures decouple) — G's call who does i…
- NinjaTrader ATM "SNIPER": stop 100 ticks / target 200, qty 1 — create in NT8 (paused; NinjaTrader is off).
- NOTHING REOPENS A DISCORD ROOM TAB — only START HERE does (G, 9/8), and it starts the DISCORD BROWSER only wh…

built from master_ledger.csv, master_broker.csv, balance_daily.csv, master_futures.csv, trades.log, daily-reports/CALLER-OUTCOMES.csv, daily-reports/CALLER-VS-RATCHET week-of-Sep-14-to-Sep-20-2026.md, daily-reports/FUTURES-MIRROR week-of-Sep-14-to-Sep-20-2026.md, daily-reports/ENTRY-SLACK week-of-Sep-14-to-Sep-20-2026.md, department-reports/extension-*.json, HANDOFF.md · 2026-09-17 18:18 Eastern Daylight Time

===== Wed Sep 16 2026 =====

# SNIPER BRIEF — 2026-09-16

## Day
- Webull margin day P&L: +$34.59 net · +$43 gross on 49 broker legs (the gap is fees)
- Balance: NLV $938.81 (-$465.41 vs 2026-09-15) · option BP $938.81 · read 2026-09-16T22:59:40
- Webull futures: -$111.56 net · -$72.4 gross, $39.16 fees on 46 fills · NLV $389.26
- Money moved (transfer / deposit / withdrawal — NOT trading): margin -$500
- ALL ACCOUNTS, net of fees: -$76.97 (margin +$34.59, futures -$111.56)
- Bot: -$129 · 3 trades, 3 contracts
- Hand (G): +$172 · 22 trades, 106 contracts
- Ledger day total: +$43 (options only)

## Bot trades
```
time   channel             trader           tkr    contract         in    out        $  why exited
--------------------------------------------------------------------------------------------------
09:39  Honeydrip daytrad…  Unraveller       TSLA   355P 9/18      4.80   4.30     -$50  born stop
09:40  Honeydrip daytrad…  Mike             TSLA   350P 9/18      2.65   2.33     -$32  born stop
09:41  Honeydrip daytrad…  Brett            AAPL   335C 9/18      3.40   2.93     -$47  born stop
```
entry slack (OFF, measured): 0 no-fills today; nothing beats today's rule: every slack level from 2% to 10% comes out behind it (-$13 to -$266), and the 95% band on 140 paired orders (-$3.24 .. -$0.74 per order) CLEARS zero

## Callers right / wrong
**Right**
- AbTrades SPY 760C 9/25 +25.0% (trim) — bot: no
- Skyy QQQ 713C +15.0% (trim) — bot: no
- ☀️｜daytrades-scalps META 665P 9/18 +15.0% (trim) — bot: no
- ☀️｜daytrades-scalps MSFT 495P 9/18 +20.0% (trim) — bot: no
- 🇳🇬｜midas-small-account-… SPY 761C 9/16 +80.0% (full) — bot: no
**Wrong**
- Brett AAPL 335C 9/18 -26.5% (full) — bot took it: -$47
- Mike TSLA 350P 9/18 -22.0% (full) — bot took it: -$32
unscored (no exit price — never estimated): none
ratchet on those 10 caller-priced paths: -1361 per 1-contract replay

## What broke
- REFUSED 3 — OPEN GOOGL (Unraveller's call) 347.5C 9/18 x1 @ 9.00 -> GOOGL260918C00347500 is too thin to trade: only 66 contracts tr…
- POSTCHECK PROBLEM 1 — FILLED TSLA — PROBLEM: book holds QQQ, the account doesn't
- EXPIRY 2 — QQQ 713C had no date — using 2026-09-16: today (2026-09-16) IS a listed expiration for QQQ, so 0DTE it is
- AI READ 8 — saved key check: verified (HTTP 200)
- MIRROR — bars unavailable, 3 alert(s) unscored: BentoClientError: 422 data_end_after_available_end
- LANE discord 1 — Chika Alerts is ON but has no tab in this browser

## Pending (G's action)
- Market Sniper: apply HANDOFF-RATCHET-2026-09-09.md (options 5→2 rung, futures decouple) — G's call who does i…
- NinjaTrader ATM "SNIPER": stop 100 ticks / target 200, qty 1 — create in NT8 (paused; NinjaTrader is off).
- NOTHING REOPENS A DISCORD ROOM TAB — only START HERE does (G, 9/8), and it starts the DISCORD BROWSER only wh…

built from master_ledger.csv, master_broker.csv, balance_daily.csv, master_futures.csv, trades.log, daily-reports/CALLER-OUTCOMES.csv, daily-reports/CALLER-VS-RATCHET week-of-Sep-14-to-Sep-20-2026.md, daily-reports/FUTURES-MIRROR week-of-Sep-14-to-Sep-20-2026.md, daily-reports/ENTRY-SLACK week-of-Sep-14-to-Sep-20-2026.md, department-reports/extension-*.json, HANDOFF.md · 2026-09-16 23:00 Eastern Daylight Time

===== Tue Sep 15 2026 =====

# SNIPER BRIEF — 2026-09-15

## Day
- Webull margin day P&L: +$197 on 64 broker legs (gross of fees)
- Balance: NLV $1404.22 (+$124.36 vs 2026-09-14) · read 2026-09-15T16:40:34
- Bot: -$132 · 9 trades, 7 contracts
- Hand (G): +$278 · 19 trades, 102 contracts
- Ledger day total: +$146

## Bot trades
```
time   channel             trader           tkr    contract         in    out        $  why exited
--------------------------------------------------------------------------------------------------
09:47  Demon day-trades    Demon × LKS      META   690C 9/16      1.88   1.75     -$13  born stop
09:53  Platinum nitro      Nitro Trades     TSLA   370C 9/16      1.19   1.11      -$8  born stop
10:14  Shoof Alerts        Elite Options …  CRWD   240C 9/18         ?      ?       $0  unavailable  ⚠ journal ≠ broker
10:56  Honeydrip daytrad…  Mike             TSLA   350P 9/18      3.25   3.05     -$20  born stop
11:03  Demon day-trades    Demon × LKS      QQQ    703P 9/15      0.61   0.58      -$3  born stop
11:33  Honeydrip daytrad…  Unraveller       AMD    490P 9/18      5.45   5.20     -$25  born stop
12:25  OWLS all-alerts     MuggZone         MU     950C 9/16      3.70   3.50     -$20  born stop
13:36  Honeydrip daytrad…  Mike (Admin)     TSLA   350P 9/18      3.78   3.35     -$43  born stop
14:57  AbTrades Alert Bot  AbTrades Alert…  HOOD   120C 9/25         ?      ?       $0  unavailable  ⚠ journal ≠ broker
```
⚠ 2 rows: the journal says it exited, the broker record prices no exit.
entry slack (OFF, measured): 3 no-fills today; nothing beats today's rule: every slack level from 2% to 10% comes out behind it (-$13 to -$266), and the 95% band on 137 paired orders (-$3.37 .. -$0.77 per order) CLEARS zero

## Callers right / wrong
**Right**
- @Owner Alerts QQQ 708P +200.0% (trim) — bot: no
- AbTrades Alert Bot HOOD 120C 9/25 +35.0% (trim) — bot took it: $0
- Brett SPY 759P 9/16 +53.6% (full) — bot: no
- Elite Options | Shoof CRWD 240C 9/18 +56.5% (full) — bot took it: $0
- Unraveller AAPL 330P 9/18 +13.0% (trim) — bot: no
**Wrong**
- Mike TSLA 350P 9/18 -10.7% (full) — bot took it: -$20
- Nitro Trades TSLA 370C -18.1% (full) — bot took it: -$8
- Unraveller AMD 490P 9/18 +0.0% (full) — bot took it: -$25
- Vero QQQ 706P 9/15 -2.7% (full) — bot: no
unscored (no exit price — never estimated): Mike (Admin) TSLA 350P, Trademorewiser (MOD) MNQ, Unraveller AMD 490P 9/18
ratchet replay: unavailable (no CALLER-VS-RATCHET block for 2026-09-15)

## What broke
- REFUSED 1 — OPEN AMD (Unraveller's call) 490P 9/18 x1 -> that one costs $535 and you've got $163 to spend. Skipped on purpose — no …
- POSTCHECK PROBLEM 1 — FILLED TSLA — PROBLEM: book holds SPY, the account doesn't
- EXPIRY 20 — TSLA 357.5C 2026-09-18 asks 7.40 against the caller's 1.42 — 2026-09-15 asks 1.45, which is the trade they posted. Swit…
- AI READ 23 — saved key check: verified (HTTP 200)
- MIRROR — bars unavailable, 4 alert(s) unscored: BentoClientError: 422 data_end_after_available_end

## Pending (G's action)
- In Claude: PROJECT-INSTRUCTIONS.md as the Project instructions; delete the old uploaded handoffs (local clean…
- Market Sniper: apply HANDOFF-RATCHET-2026-09-09.md (options 5→2 rung, futures decouple) — G's call who does i…
- NinjaTrader ATM "SNIPER": stop 100 ticks / target 200, qty 1 — create in NT8 (paused; NinjaTrader is off).
- Close any old parked Whop tabs (Chrome flags note: reference/OPERATIONS.md).
- CHROME BEFORE 9:15: rooms open at 9:15 only if Chrome + the extension are already up. Run START HERE, or sche…

built from master_ledger.csv, master_broker.csv, balance_daily.csv, trades.log, daily-reports/CALLER-OUTCOMES.csv, daily-reports/CALLER-VS-RATCHET week-of-Sep-14-to-Sep-20-2026.md, daily-reports/FUTURES-MIRROR week-of-Sep-14-to-Sep-20-2026.md, daily-reports/ENTRY-SLACK week-of-Sep-14-to-Sep-20-2026.md, department-reports/extension-*.json, HANDOFF.md · 2026-09-15 16:42 Eastern Daylight Time

===== Mon Sep 14 2026 =====

# SNIPER BRIEF — 2026-09-14

## Day
- Webull margin day P&L: -$333.85 net · -$321 gross on 60 broker legs (the gap is fees)
- Balance: NLV $1279.86 · option BP $1279.86 · read 2026-09-14T23:25:00
- Bot: -$91 · 10 trades, 10 contracts
- Hand (G): -$230 · 15 trades, 142 contracts
- Ledger day total: -$321

## Bot trades
```
time   channel             trader           tkr    contract         in    out        $  why exited
--------------------------------------------------------------------------------------------------
10:23  Whop Day Trades     Trademorewiser…  NVDA   210P 9/16      2.40   2.38      -$2  BE stop
10:24  Platinum ei-alerts  PT | ei trades   TSLA   357.5C 9/18    7.40   7.06     -$34  born stop
10:36  Demon day-trades    Demon × LKS      QQQ    704P 9/14      1.13   1.13       $0  BE stop
10:42  Mugzone Options     MuggZone         MU     850P 9/16      2.10   2.05      -$5  pullback stock exit
10:42  Vero 2              Vero             QQQ    705P 9/14      1.41   1.39      -$2  closed by hand
11:15  OWLS all-alerts     MuggZone         MSFT   505C 9/14      0.65   0.61      -$4  born stop
11:25  Honeydrip daytrad…  Unraveller       META   670C 9/18      6.65   6.20     -$45  born stop
12:02  Mugzone Options     MuggZone         TSLA   340P 9/25      2.38   2.34      -$4  pullback stock exit
14:05  Aristotle           👑KingBeeAri🐝     META   700C 9/18      2.61   2.68      +$7  ratchet
14:22  shabs               Skyy             QQQ    713C 9/14      0.24   0.22      -$2  born stop
```

## Callers right / wrong
**Right**
- @Owner Alerts TSLA 357.5P +36.0% (trim) — bot: no
- brando-alerts QQQ 710C 9/16 +59.4% (trim) — bot: no
- MuggZone CRWD 245C 9/18 +100.0% (trim) — bot: no
- MuggZone MSFT 505C +100.0% (trim) — bot took it: -$4
- Skyy QQQ 708C +422.7% (full) — bot took QQQ 713C 9/14: -$2
- TT GOOGL 360C 10/16 +26.0% (trim) — bot: no
- Unraveller META 670C 9/18 +6.5% (trim) — bot took it: -$45
**Wrong**
- Trademorewiser (MOD) NVDA 210P 9/16 -37.5% (full) — bot took it: -$2
unscored (no exit price — never estimated): @Futures Alerts MNQ, MuggZone MU 850P 9/16, MuggZone TSLA 360P 0DTE, Trademorewiser (MOD) MNQ, 👑KingBeeAri🐝 META 700C 9/18
ratchet on those 20 caller-priced paths: +976 per 1-contract replay

## What broke
- REFUSED 1 — OPEN DRAM (Eva's call) 58C 9/18 x1 -> the spread on DRAM260918C00058000 is 0.44/0.57 — 26% of the price (20% cap). A fi…
- POSTCHECK PROBLEM 7 — FILLED TSLA — PROBLEM: TSLA is held with NO resting stop — watchdog only
- STOP-WARN 5 — ei trades — Webull wouldn't hold a resting stop (bad option root ' ei trades'). The watchdog on this PC is still on it,…
- EXPIRY 3 — MSFT 505C had no date — using 2026-09-14: today (2026-09-14) IS a listed expiration for MSFT, so 0DTE it is
- IMG READ 3 — couldn't read the image (HTTP 400: Your credit balance is too low to access the Anthropic API. Please go to Plans & Bil…
- AI READ 245 — no call — ai: HTTP 400
- MIRROR — bars unavailable, 8 alert(s) unscored: BentoClientError: 422 dataset_unavailable_range

## Pending (G's action)
- In Claude: use project/PROJECT-INSTRUCTIONS.md as the Project instructions and remove the old uploaded handof…
- Market Sniper: apply HANDOFF-RATCHET-2026-09-09.md (options 5→2 rung, futures decouple) — G's call whether Cl…
- NinjaTrader ATM template "SNIPER": stop 100 ticks / target 200 (=25/50 MNQ pts), qty 1 — create in NT8, type …
- Close any old parked Whop tabs. (`--disable-gpu` rides every flagged Chrome launch since 9/10 — a GPU black t…
- Announcer: paused since 9/2 — the Needs-you tab has the on/off button.
- CHROME BEFORE 9:15: rooms open at 9:15 only if Chrome + the extension are already up. Run START HERE, or sche…

built from master_ledger.csv, master_broker.csv, balance_daily.csv, trades.log, daily-reports/CALLER-OUTCOMES.csv, daily-reports/CALLER-VS-RATCHET week-of-Sep-14-to-Sep-20-2026.md, daily-reports/FUTURES-MIRROR week-of-Sep-14-to-Sep-20-2026.md, department-reports/extension-*.json, HANDOFF.md · 2026-09-15 01:52 EDT
