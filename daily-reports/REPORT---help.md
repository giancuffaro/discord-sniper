# Daily Sniper Report — --help

Generated 2026-09-14 22:28:54 Eastern Daylight Time.

## Coverage

- Rooms configured on: **34** Discord and **4** Whop.
- Rooms/channels with a live parser input today: **0**.
- Live parser inputs retained: **0** messages.
- Rooms with no message are quiet or unverified; the report does not call them healthy solely from silence.

## Alert flow

| Measure | Count |
|---|---:|
| Unique entry alerts observed (normal + recovered) | 0 |
| Entry alerts read and given a decision | 0 |
| Broker entry orders submitted | 0 |
| Read but not taken | 0 |
| Broker/risk refusals | 0 |
| Stale when first read | 0 |
| Duplicate or other skips | 0 |
| Recovered entry gaps | 0 |
| Recovered add gaps | 0 |
| Actual fills in master ledger | 0 |

## Actual results

- Bot trades: **0** — 0 win, 0 loss, 0 flat.
- Realized P&L: **+0.00**.

## Entry and exit comparison

- No filled trade has enough tape for a comparison yet.
- Exact caller-entry/caller-exit P&L is reported only when both messages and a contemporaneous contract quote exist. Missing exits remain **unavailable**; they are never estimated from a later high or a stale quote.
- Refused or missed alerts stay outcome-pending until a caller exit can be paired to the recorded contract tape; a later high alone is not labeled a win.
- No matched trade is available for a system-versus-caller verdict.

## Every recognized decision

| Time | Caller | Room | Alert | Result | Reason | Source message |
|---|---|---|---|---|---|---|

## Room activity

| Room/channel | Parser inputs |
|---|---:|

## Detailed benchmarks

- [Caller entry, trim, and exit evidence](CALLER-OUTCOMES---help.md)
- [Caller original entry versus our ratchet](CALLER-VS-RATCHET---help.md)
- [Fixed stop versus live ratchet replay](RATCHET-COMPARE---help.md)
