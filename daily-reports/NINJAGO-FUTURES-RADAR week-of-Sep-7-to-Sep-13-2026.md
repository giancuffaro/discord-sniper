# NINJAGO-FUTURES-RADAR — week of Mon Sep 7 2026 to Sun Sep 13 2026. Newest day first; each day under its ===== header; a re-run replaces that day's block (reports.py).

===== Fri Sep 11 2026 =====

# Ninjago Futures Radar caller-bracket replay — 2026-09-11

## What this measures

This is the caller's plan, not Discord Sniper's entry policy: each row assumes the caller was filled at the stated entry immediately when the alert was posted, then asks whether the stated target or stated stop was reached first. Price source: Databento GLBX.MDP3 continuous one-minute bars, cached in `bars/NQ_1m_2026-08-03_2026-09-12.csv` and `bars/MGC_1m_2026-09-11.csv`.

One-minute bars cannot order events inside the same minute. A bar that touched both target and stop would be `unavailable`; none of these did. The result is still conditional: it does not prove Ninjago's actual broker fill, size, slippage, or exit.

## Caller-stated outcomes

| Posted ET | Caller plan | First stated level reached after post | Conditional result |
|---|---|---|---|
| 09:54 | MNQ short 29483.875; TP 29453.875; SL 29503.875 | TP at 09:55 | Target |
| 10:56 | MGC long 4422.60; TP 4434.60; SL 4414.60 | Stop condition crossed in the 10:57 bar | Not verifiable: price had already gapped about 40 points below the claimed entry |
| 11:13 | MNQ short 29411.75; TP 29381.75; SL 29431.75 | SL at 11:16 | Stop |
| 11:16 | MNQ long 29377.50; TP 29407.50; SL 29357.50 | TP at 11:17 | Target |
| 11:18 | MNQ short 29413.00; TP 29383.00; SL 29433.00 | SL at 11:19 | Stop |
| 14:06 | MNQ short 29449.25; TP 29419.25; SL 29469.25 | TP at 14:20 | Target |

### Scoreable MNQ result

The five MNQ plans are **3 targets and 2 stops**. At the caller's stated entry/target/stop distances, that is **+50 points / +$100 per MNQ contract before fees**: three +30-point targets ($60 each) and two -20-point stops ($40 each).

The MGC row is deliberately outside that total. At 10:57 AM ET the MGC one-minute bar was 4382.0–4382.6, below even the caller's 4414.60 stop. A caller could not have been newly filled at 4422.60 at the stated time; treating the posted stop as a normal -8-point loss would invent a fill that the tape contradicts.

## The bot's separate 25-point rule

The live futures route keeps the caller's literal stop and target, but for **index-futures entries only** it snaps an entry to a 25-point level in the bot's favor. Thus the posted MNQ short `29483.875` would route as **29500**; a long at the same number would route as **29475**. That is Discord Sniper's route policy, not a claim about Ninjago's actual fill, and futures execution remains blocked until broker-confirmed protective exits exist.
