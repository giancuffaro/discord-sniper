# BRIEF — week of Mon Sep 14 2026 to Sun Sep 20 2026. Newest day first; each day under its ===== header; a re-run replaces that day's block (reports.py).

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
