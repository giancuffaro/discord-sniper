# Read-only static audit — ledger/journal, reporting, health/monitoring, infra scripts

Scope: 60 files (ledger/journal bookkeeping, daily reporting, health/monitoring,
misc infra/setup scripts) in `C:\Users\Hulk\Desktop\discord-sniper\`. No files
were executed or modified; this is Read-tool-only static review.

---

### build_alerts.py
- [SEVERITY: high] build_alerts.py:222 — `_alert_meta()` returns a 2-tuple (`return {}, {}`) on the "no alert_meta.csv" path, but every call site (`_apply_meta` line 281: `exact, contract_unique, symbol_unique = _alert_meta()`) unpacks 3 values, so a missing `alert_meta.csv` raises `ValueError: not enough values to unpack` inside `build()` — and because `ledger.py`'s `alerts()`/`_ensure()` call `build_alerts.refresh()` inside a bare `except Exception: pass`, this failure is silently swallowed, leaving `master_alerts.csv` stale or absent with zero visible error anywhere. — Fix: change line 222 to `return {}, {}, {}` to match the exception-path return at line 248 and the unpack contract at 281.
- [SEVERITY: low] build_alerts.py:248 — the `except OSError: return {}, {}, {}` path (correct 3-tuple) is inconsistent with the "file doesn't exist" 2-tuple return one screen above it — one of the two return shapes is simply wrong and it's the file-not-found one, which is the common/likely case (not just an I/O error), making it the more probable trigger. — Fix: same as above; make both early-return paths match the 3-tuple contract.

### build_ledger.py
- clean — the historical bugs documented in the file's own comments (F19 expiry-omitted dedupe key, the qty-blind trip matcher, the sale-proceeds-as-P&L bug) are already fixed in the code present; verified `_dedupe_key` includes expiry (line 203) and `_find_trip` has the qty guard.

### ledger.py
- [SEVERITY: low] ledger.py:60-64 — `_ensure()` catches `Exception` around `build_ledger.refresh()` with a bare `except Exception: pass`; combined with the `build_alerts.py` bug above, any exception raised while rebuilding the ledger is invisible to every downstream caller (scoreboard, caller_report, journal_full, etc.) — they all just see an empty or stale CSV with no diagnostic. — Fix: log the exception (even just to stderr) instead of silently passing, so a broken rebuild is at least discoverable.

### caller_ledger.py
- clean.

### caller_report.py
- clean — `MIN_N`/`GOOD_N` sample-size gating and the caller name-canonicalization logic are sound; no math errors found.

### caller_outcomes.py
- clean — extensively guarded against unit-mismatch (stock-price-vs-premium) and duplicate-claim bugs; the regexes are narrow and documented with real false-positive cases they were built to avoid.

### journal_full.py
- [SEVERITY: low] journal_full.py:50-55 — `_hhmm()` uses naive `datetime.fromtimestamp(t)` (local system time) while the rest of the reporting stack (`eastern.py`, `daily_report.py`, `postmortem.py`) is careful to convert to `America/New_York` explicitly. If this script is ever run on a machine whose local timezone differs from ET (or during a DST transition mismatch on a misconfigured host), every `time`/`opened`/`closed` column in the exported journal.xlsx will be silently off by the UTC-offset difference, with no warning. — Fix: route through `eastern.now()`-style conversion, or at minimum note in the docstring that this assumes the host clock is ET (as `telemetry.py`'s `minutes_to_close()` does explicitly).

### daily_report.py
- clean — reads are all defensive (`OSError`/`ValueError` caught locally), and the message/decision-matching windowing (180s near-match) is consistent with other report files.

### daily_brief.py
- clean — every numeric formatter (`_num`, `_money`, `_pct`) is careful to return `None`/"unavailable" rather than defaulting to 0, avoiding the classic "missing data silently becomes a loss" bug class this codebase is otherwise vigilant about.

### daily_audit.py
- clean — orchestration only; every sub-step wrapped so one failing report can't take down the whole audit pipeline. `broker_step`/each `_run()` swallow subprocess errors into the summary object rather than raising, by design.

### daily_policy_compare.py
- clean.

### scoreboard.py
- [SEVERITY: low] scoreboard.py:207-211 — `T` room-stats lookup: `tr = T.get(cid) or T.get((cfg or {}).get("label", "\x00")) or {}`. If a room's trades are keyed under its *label* in `T` (built from `master_ledger.csv`'s `room` field, which can be either an id or an already-resolved label depending on source) but the room in `R` is keyed by channel id, and BOTH lookups miss, `tr` silently becomes `{}` and that room's real P&L/trade count is dropped from its row without any indicator that data was lost (as opposed to the room genuinely having 0 trades). This is a display-only script (not the ledger itself) so the risk is a misleading scoreboard rather than a money bug, but it's the same "unattributed data vanishes with no evidence-of-loss marker" pattern flagged elsewhere. — Fix: track and print a count of trades that couldn't be joined to a room row, similar to how `misses.py`/`build_alerts.py` report unmatched/dropped rows.

### postmortem.py
- clean — the CSV race between concurrent postmortem writers is explicitly closed with `_CSV_LOCK` around the full read-modify-write cycle (documented as fixing bug F11); verified the lock scope actually covers both the read and the write.

### research_ledger.py
- clean.

### research_report.py
- clean — pure read/render, no live-data risk.

### health.py
- clean — deliberately never opens a second tastytrade DXLink session (would break the live one); Webull check paced correctly; `check_local_processes`/`dxlink_from_log` degrade to "unknown" rather than false-positive failures.

### deadman.py
- clean — this is explicitly the module designed to STOP silent exception-swallowing elsewhere in the codebase (installs `threading.excepthook`, `sys.excepthook`, `sys.unraisablehook`). No bare `except: pass` in the file; every internal failure path (`_say()`) itself degrades through three channels rather than one.

### errors.py
- clean — pure log-grep/report tool, no state mutation.

### market_hours.py
- clean — DST logic in `fromutc()` is deliberately computed in UTC instants (not wall-clock) specifically to sidestep the November fall-back ambiguous-hour bug class; the reasoning in the docstring is correct and matches the implementation. Holiday table is hardcoded through 2027 only — this is flagged in-file (`HOLIDAYS_THROUGH`) but the code does NOT actually check `HOLIDAYS_THROUGH` against the current year anywhere in `is_holiday()`/`is_half_day()` despite the docstring claiming it "raises the holiday_table_stale flag." See finding below.
- [SEVERITY: medium] market_hours.py:66-77 — the module docstring claims "If the running year is past HOLIDAYS_THROUGH the code treats every weekday as a normal session and status() raises the 'holiday_table_stale' flag," but `status()` (lines 172-179) contains no such flag, and `is_holiday()`/`is_half_day()` simply do `FULL_CLOSE.get(d.year, set())` with no staleness check at all — so once the calendar rolls past 2027 with no one having updated the table, the bot will silently treat every market holiday (Jan 1, Thanksgiving, Christmas, etc.) as a normal trading day with no warning anywhere, which is exactly the "attempt a trade on a day the market is shut" failure mode the file's own docstring says must not happen. — Fix: either implement the documented `holiday_table_stale` flag in `status()`, or update the docstring to stop promising a safeguard that isn't there.

### eastern.py
- clean — the hand-rolled `_USEastern` DST fallback is correct per its own stated reasoning (checked against the real US rule since 2007); `fromutc()` correctly sidesteps wall-clock ambiguity by computing in UTC-instant space.

### symbols.py
- clean — fail-open behavior (unknown ticker list → allow everything) is intentional and documented, not a bug.

### occ.py
- clean — this file is explicitly the fix for a prior class of bug (silent CALL/PUT default-to-PUT); `side_letter()` raises rather than guessing, exactly as documented. `_ymd()`'s position-based year disambiguation for expiry strings is correct.

### now.py
- clean — read-only diagnostic, degrades gracefully everywhere.

### trade_identity.py
- clean.

### context_reader.py
- clean — shadow/measurement-only path, explicitly never feeds the live order path (confirmed via `assess()`/`safety_flags()` which only flag, never act).

### departments.py
- clean.

### telemetry.py
- clean — extensively guarded against perturbing the trading path (single writer thread, bounded queue, drop-on-full rather than block); `_ms()` correctly returns blank (not 0) for negative/missing deltas, avoiding the "missing data silently becomes fast" bug class.

### index_mirror.py
- clean — ships hard-disabled (`live_exit_ready()` returns `False` unconditionally) with the switch also gated behind `enabled(cfg)`, so `convert()` cannot fire live orders even if `settings.json` were misconfigured, short of both being changed together.

### liquidity.py
- clean — fail-open on missing data is intentional and documented (blocking real entries because a data provider had a bad minute is explicitly called out as the worse failure).

### misses.py
- clean — the STOP blacklist-to-allowlist migration (`symbols.resolve`) is a real historical bug already fixed; no unaddressed issue found in the current code.

### replay_check.py
- clean — read-only audit tool.

### audit_history.py
- clean — read-only audit tool; explicitly documents and works around the pre-9/2 400-verdict truncation bug in the extension rather than hiding it.

### audit_reproductions.py
- clean — this file exists specifically to prove that OLD bugs (F01, F03, F07-F10) are now FIXED via `assert`; every reproduction's assertion in the current code matches the "bug fixed" behavior, not the original bug. Confirms these 20 historical bug classes (multi-contract overwrite, ambiguous-bracket double-buy, orphan cleaner cancelling unowned contracts, atomic-write races, etc.) are patched in the live modules it imports from (`positions.py`, `webull_options.py`, `bridge.py` — outside this audit's scope but referenced here for completeness).

### databento_backfill.py
- clean.

### check_keys.py
- clean — never prints full keys/secrets (only last-4 / char-count), correctly distinguishes "not installed here" from "broker refused."

### provider_key_check.py
- [SEVERITY: medium] provider_key_check.py:31-32 — the Perplexity request is built with `url = 'https://api.perplexity.ai/v1/sonar'` — this does not match Perplexity's actual chat-completions endpoint shape used by every other client in this codebase family (`.../chat/completions`), and the `body` constructed for it (line 33-34, OpenAI-style `messages`/`max_tokens`) is the same shape used for OpenAI, not necessarily what Perplexity's `/sonar` endpoint (if it even exists at that path) expects. This key-health probe will likely always report a failure state (404/`request_rejected`) for Perplexity regardless of whether the actual key is valid, misleading whoever reads `provider-key-check.json` about that provider's real status. — Fix: verify Perplexity's actual current endpoint/schema (typically `https://api.perplexity.ai/chat/completions`) and correct the URL.

### refresh_optionable.py
- clean.

### rename_rooms.py
- clean — dry-run by default, atomic write with validation before swap.

### recover_trade_sources.py
- clean.

### scoped_missed_pull.py
- clean.

### request_journal.py
- clean — correct idempotency pattern (SQLite PK + `INSERT OR IGNORE` + read-back).

### props.py
- clean — extensively guarded (bracket-or-nothing rule, Topstep consistency lock, float-rounding-to-cents fix already applied at line ~230 `round((pct / (1.0 - pct)) * prior, 2)`).

### announcer.py
- [SEVERITY: low] announcer.py:388-389 — the futures-account poll cadence `if _fut and _tick[0] % 5 == 0:` means futures fills are only checked once every 5 polls (~5-10s at default `poll_seconds=1-2`), so a futures fill announcement can lag noticeably behind the actual fill compared to the margin-account path which polls every cycle — not a correctness bug (it's documented as deliberate pacing) but worth flagging since it means futures P&L milestones/stop-outs are announced later than options ones, which could read as "the announcer missed it" during troubleshooting. — informational only, not scored as a real bug given it is clearly an intentional rate-limit tradeoff.

### chika_compare.py, futures_mirror_daily.py
- clean — both are offline research/backtest tooling with no live-path interaction; entry/exit math checked against their own documented formulas and found consistent.

### ds_logs.py
- clean.

### reads.py
- clean.

### clean_tape.py, tape.py, option_tape_pull.py
- clean — tape.py's `Row.mid` property correctly falls back to `price` for greeks-only rows rather than returning `None`/0; `clean_tape.py`'s despike window logic is sound (local-median comparison, never touches genuine persistent moves).

### prove_tastytrade_bracket.py / prove_tradier_bracket.py
- clean — this file only exists as `prove_tradier_bracket.py` (per the task's fallback instruction); defaults to dry-run, requires explicit `--place`, never sent without human action.

### setup_databento.py, setup_keys.py, setup_tastytrade.py, setup_tradier.py
- clean — no plaintext secrets are ever printed (all masked to last-4 chars or `*` count); files are `chmod 600`'d; atomic write-verify-swap pattern used consistently for `settings.json`; OAuth/token exchange is verified BEFORE writing to disk in every setup script, so a bad paste never corrupts saved config.

### build_alerts.py
(see top — the `_alert_meta()` tuple-arity bug)

### reference\ratchet_replay_tape.py, reference\stock_stop_replay.py, reference\caller_profile.py, reference\futures_mirror_replay.py, reference\futures_mirror_alerts.py
- clean — all five are offline, read-only backtest/research scripts (no live order path, no shared mutable state with the trading engine). Math spot-checked: stop/target/ratchet mechanics mirror the equivalent live modules (`ratchet_tiers.py`, `webull_options.stop_below`) rather than reimplementing them divergently, and every file is explicit and repeatedly self-documenting about sample-size limits, coverage gaps, and vendor-mixing risks. No bugs found.

---

## Summary of the single biggest risk

The most consequential finding is the **tuple-unpacking crash in `build_alerts.py:222`**: `_alert_meta()` returns a 2-tuple on its "file missing" path but every caller unpacks 3 values, so a missing/renamed `alert_meta.csv` throws a `ValueError` that silently kills the *entire* `master_alerts.csv` rebuild — and because `ledger.py` wraps that rebuild in a bare `except Exception: pass`, nothing surfaces the failure anywhere (no log line, no error in trades.log, nothing). Since `master_alerts.csv` feeds the daily brief's "what broke" and caller-scoring sections, this is a case where a single missing input file can make performance/decline reporting go silently stale with zero indication to the person reading it — precisely the "misreport trading performance to the user" risk category this audit was asked to find. It's a one-line fix (`return {}, {}, {}`), but its blast radius (silent, systemic, and specifically defeats the codebase's otherwise very strong "never silently swallow" discipline) makes it the standout issue in this slice.
