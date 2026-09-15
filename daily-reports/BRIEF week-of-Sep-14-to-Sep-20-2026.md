# BRIEF — week of Mon Sep 14 2026 to Sun Sep 20 2026. Newest day first; each day under its ===== header; a re-run replaces that day's block (reports.py).

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
