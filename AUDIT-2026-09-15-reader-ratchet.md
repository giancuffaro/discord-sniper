# Read-only static audit — Discord alert reader, quote handling, ratchet math
Scope: 27 files (ai_reader.py, alert_tape.py, alert_revision.py, reader_measure.py,
reader_history.py, shadow_reader.py, quote_bus.py, quote_shadow.py, stream_bus.py,
observer_providers.py, parser_gate.js, reader_parse.js, reader_corpus.js, jsparse.py,
ratchet_tiers.py, ratchet_backtest.py, ratchet_sweep.py, ratchet_sweep_fine.py,
pullback.py, pullback_levels.py, chart_contracts.py, greeks_math.py,
entry_attribution.py, entry_compare.py, missed_dollarize.py,
caller_ratchet_compare.py, ai_scalps_backtest.py, openai_reader_trial.py)

No files were executed, imported, or invoked. Static read-only review only.

**Overall read:** this is an unusually well-hardened codebase. Most files carry
extensive in-line postmortems of *past* real bugs (each stamped with a date and
what broke), and the fixes for those are in place and look correct on inspection.
The live-money core — `ratchet_tiers.py`'s arm/lock/step math, `pullback.py`'s
round-number entry/exit direction logic, and `ai_reader.py`'s literal-match
anti-hallucination guard — all checked out sign-correct and off-by-one-correct
on manual trace. Most of the 27 files (ratchet_backtest/sweep/sweep_fine,
chart_contracts, entry_attribution, entry_compare, missed_dollarize,
caller_ratchet_compare, ai_scalps_backtest, pullback_levels, reader_measure,
reader_history, openai_reader_trial, jsparse, the three .js corpus/gate tools)
are offline research/backtest/reporting scripts that write local files or
stdout and never call the order path — bugs there could mislead a spacing
decision a human later approves, but cannot directly move real money. Findings
below reflect that risk tier.

## ai_reader.py
- [SEVERITY: low] ai_reader.py:550 — `_num_in_text` formats numbers with `"%g" % float(n)`, which switches to scientific notation (`1.5e+06`) above 6 significant digits; a legitimate strike/price of unusual magnitude would then fail the literal-text match and the call would be refused even though it is real. — Fails safe (spurious refusal, not a bad trade), but worth switching to a format that never goes scientific (e.g. strip trailing zeros from `%.10f`) so an odd-shaped real alert isn't silently dropped.

## alert_revision.py
- [SEVERITY: medium] alert_revision.py:187-196 — the no-message-id fallback (voice/vision reads, or any legacy source) treats *any* second OPEN on the same symbol by the same trader within 5 minutes as a revision of the first and hands it to the caller as "superseded," which the bridge then cancels — but a trader legitimately posting two separate contracts on the same underlying within the window (e.g., a second, intentional add or a different-strike scalp) would have the first one incorrectly cancelled, not just the TSLA-edit case this file was built to catch. The module's own docstring calls out this ambiguity as an accepted tradeoff when no message_id exists, but it's worth confirming how often the AI-reader/vision path (which doesn't have a Discord message id inherently) is the one hitting this branch in production, since that's exactly the path most likely to lack a message_id.

## quote_bus.py
- [SEVERITY: medium] quote_bus.py:112-121 — `Budget.take()` (called on *every* quote sweep tick and every priority order/stop-move — this is literally the function every real-money order and every ratchet stop-move passes through to get budget) does a full `import traceback` + `traceback.extract_stack(limit=4)` + dict bookkeeping on every single call, wrapped only in a bare `except Exception: pass`. This is diagnostic instrumentation ("WHO-SPENDS tell") left permanently live in the hot path rather than gated behind a debug flag. It adds real per-call latency to the exact code path guarding order/stop-move budget priority, and an unbounded-looking `callers` dict is never pruned (low risk in practice since call-stack signatures are few and stable, but still unbounded by construction). — Gate the stack-introspection block behind a debug flag/env var so production order/stop-move calls don't pay the cost of `traceback.extract_stack` on every token request.

## ratchet_tiers.py
- clean — arm/lock/step math, the tick-size floor, the spread floor, and the long/short sign mirroring in `ratchet_stop_price` and `futures_stop_price` all traced correctly by hand; "never loosen" comparisons are correctly inverted between long (`want <= cur`) and short (`want >= cur`).

## pullback.py
- clean — `round_target`/`touched`/`_manage_exit` direction logic (call = dip down / floor, put = bounce up / ceil) is internally consistent and matches its own passing self-tests; dedupe key and phantom-exit cancellation matching look sound.

## greeks_math.py
- clean — the gamma-corrected premium math and the sign check in `underlying_for_premium` (refusing a wrong-direction root) are correct on manual trace.

## symbols.py, alert_tape.py, quote_shadow.py, stream_bus.py, observer_providers.py, shadow_reader.py, jsparse.py, reader_history.py, parser_gate.js, reader_parse.js, reader_corpus.js
- clean — no logic bugs found. All broad `except Exception` blocks in these files fail toward "do nothing / refuse the trade" rather than silently proceeding with bad data, which is the correct default for a money-moving system.

## ratchet_backtest.py, ratchet_sweep.py, ratchet_sweep_fine.py, chart_contracts.py, entry_attribution.py, entry_compare.py, missed_dollarize.py, caller_ratchet_compare.py, ai_scalps_backtest.py, pullback_levels.py, reader_measure.py, openai_reader_trial.py
- clean of real bugs — offline research/backtest/report generators only (write local CSV/JSON/HTML/Markdown, never call an order endpoint; several explicitly assert this in their own docstrings). Minor unused-variable-only findings (e.g. reader_measure.py:355 `pa`/`aa`/`raw_action` assigned but unused, chart_contracts.py:72 `smap` unused) are style nits per the audit brief and are omitted.

## No secrets, no eval/exec, no shell injection
Searched all 27 files for hardcoded API keys/tokens (`sk-...` patterns), `eval(`, and `os.system`/`subprocess(..., shell=True)`. None found. `openai_reader_trial.py` takes its API key via a masked, memory-only GUI field and explicitly documents it is never imported by the live order path.

## Biggest risk found
Nothing here rises to "will misfire a real trade" — the ratchet math and the pullback direction logic, which are the two places a sign error would directly cost money, both check out correct on manual trace. The most consequential finding is the `quote_bus.py` `Budget.take()` stack-introspection overhead sitting permanently in the exact hot path used by every stop-move and order, since latency there is the one thing the module's own design notes call out as the difference between a stop firing on time and one that doesn't; it's a performance/hygiene issue today, not a logic bug, but it's the one item worth fixing rather than filing away.
