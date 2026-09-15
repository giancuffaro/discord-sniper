# Discord Sniper — Full Codebase Audit (2026-09-15)

Read-only static review, 128 files / ~51K lines, split across 3 passes:
- Group A: bridge.py, positions.py, broker/webull/tastytrade/tradier (execution engine)
- Group B: alert reader, quote handling, ratchet/stop-loss math
- Group C: ledger/journal, reporting, health/monitoring, infra/setup scripts

Nothing was executed, run, or modified. Cross-checked with pyflakes where relevant.

## Overall verdict
This codebase is unusually well-hardened for a solo-dev trading bot — most files carry
inline postmortems of past real bugs with the fixes already verified in place. No
hardcoded secrets, no unsafe eval/exec, no shell injection found anywhere. Core
money-math (ratchet stop/tier logic, options greeks, order sizing) all traced correct.

## Findings, by priority

### HIGH — bridge.py:714 NameError on paper_trading=true
`note(...)` is called at true module top-level (inside an `if` block that runs at import
time), but `def note()` isn't defined until line 1401 later in the same file. Confirmed
independently by pyflakes AST analysis and manual trace. Currently DORMANT because
`settings.json` has `webull.paper_trading: false` right now — but the instant that flag
flips to true, the entire bridge crashes on load: no server, no position book, no stop
protection on anything already open. This is exactly the failure mode the warning text
itself was trying to flag.
**Fix:** move the `def note(...)` definition above line 714, or move the top-level
`if (EXEC.get("webull")...` check into a function called after `note` is defined.

### HIGH — build_alerts.py:222 silent crash + swallowed error
`_alert_meta()` returns a 2-tuple (`{}, {}`) when `alert_meta.csv` is missing, but every
caller (e.g. `_apply_meta` line 281) unpacks 3 values → `ValueError`. Because
`ledger.py`'s `_ensure()` wraps the whole rebuild in a bare `except Exception: pass`,
this crash is 100% silent — `master_alerts.csv` goes stale/missing with zero error
anywhere, and that file feeds the daily brief's "what broke" + caller-scoring sections.
**Fix:** one-line — change line 222 to `return {}, {}, {}` to match the exception-path
return at line 248 and the unpack contract at 281. Also worth logging (not just passing)
the exception in `ledger.py:60-64` so a broken rebuild is discoverable next time.

### MEDIUM — alert_revision.py:187-196 no-message-id false "edit" detection
When a Discord alert has no message ID (voice/vision-read alerts, or any legacy path —
notably the AI-reader path, which structurally lacks a native message id), a second
real OPEN on the same symbol by the same trader within 5 minutes gets treated as a
"revision" of the first and the bridge cancels the first order — even if the trader
genuinely meant two separate positions (different strike, intentional add, etc). The
module's own docstring accepts this as a known tradeoff, but worth checking how often
the AI-reader path actually hits this branch in production.

### MEDIUM — market_hours.py holiday table can go stale with no warning
The docstring claims that past `HOLIDAYS_THROUGH` (currently only populated through
2027) the code "raises a holiday_table_stale flag" — but no such flag exists anywhere
in `status()`, `is_holiday()`, or `is_half_day()`. Once the calendar rolls past 2027
without anyone updating the table, the bot will silently treat every market holiday as
a normal trading day. Not urgent (18+ months out) but should go on a calendar reminder.

### MEDIUM — quote_bus.py Budget.take() has permanent debug overhead in the hot path
Every single quote tick AND every priority order/stop-move call runs a full
`import traceback` + `traceback.extract_stack()` + dict bookkeeping, wrapped in a bare
`except Exception: pass`. This is leftover diagnostic instrumentation, not gated behind
a debug flag, adding real latency to the exact code path that decides whether a stop
fires on time.

### MEDIUM — provider_key_check.py probably always fails for Perplexity
Uses `https://api.perplexity.ai/v1/sonar` with an OpenAI-shaped request body — doesn't
match Perplexity's actual `/chat/completions` endpoint. The key-health check likely
always reports Perplexity as broken/invalid regardless of whether the key actually
works — cosmetic (monitoring only) but worth fixing so it doesn't cry wolf.

### LOW / informational (no fix needed urgently)
- `journal_full.py:50-55` — uses naive local-clock time instead of explicit ET
  conversion like the rest of the reporting stack; only matters if run on a
  non-ET-timezone machine.
- `scoreboard.py:207-211` — a room lookup miss silently shows 0 trades instead of
  flagging "data couldn't be joined" — display-only, not a money bug.
- `ai_reader.py:550` — a number formatter can flip to scientific notation above 6 sig
  figs, causing a spurious (safe-direction) refusal on an unusually large price.
- `announcer.py:388-389` — futures fills are polled every 5th cycle vs every cycle for
  options — intentional pacing, just noted so it doesn't look like a missed alert.
- `webull_futures.protective_entries_ready()` returns `False` unconditionally, so all
  live futures opens are currently refused despite `futures_enabled: true` in settings —
  looks like an intentional fail-closed state pending reconciliation work, flagged to
  confirm it's not a forgotten switch.

## Not a bug — confirmed safe by design
`index_mirror.py` ships hard-disabled at two independent layers (function always
returns False AND gated behind a separate config flag) so it can't fire live orders
even under partial misconfiguration. `audit_reproductions.py` proves 20 previously-fixed
historical bugs stay fixed via live asserts against the current code.
