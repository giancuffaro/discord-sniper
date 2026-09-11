# Discord Sniper end-of-day benchmark contract

## Product goal

Discord Sniper is an evidence system that can execute eligible alerts. Its main
long-term job is to preserve enough trustworthy data to answer, every day and
over a growing sample:

1. Which configured rooms were actually watched?
2. What did each room post?
3. Which posts became entry, add, trim, or exit signals?
4. What did the system do with each signal, and why?
5. What reached the broker, filled, remained open, and closed?
6. Did the trade win or lose after fees?
7. What would have happened under the caller's documented entry and exits?
8. What would the current bot entry and exit policy have done on the same call?
9. Which room, caller, parser rule, entry rule, and exit rule improve results on
   repeated evidence rather than one day's hindsight?

The daily report is the readable output. The append-only event and price data
are the product because they make later backtests possible.

## One lifecycle, with fixed meanings

Every alert needs one stable `event_id`, preferably the source lane + channel
ID + Discord/Whop message ID. A relay copy points to the original event instead
of becoming a second alert. A deliberate new entry in the same contract remains
a separate event.

| Stage | Meaning |
|---|---|
| Posted | The source message existed in a configured room. |
| Captured | A live reader stored the exact message and source identity. |
| Emitted | The production parser produced an action from it. |
| Reviewed | Policy assigned a terminal decision and reason. |
| Sent | An order request reached the broker adapter. |
| Filled | The broker confirmed quantity and price. |
| Closed | Broker fills establish the realized result. |
| Simulated | A versioned policy was replayed on market data; never mixed with actual fills. |

Each captured actionable message must end the day with a reviewed outcome or an
explicit audit gap. Silence is not an outcome.

## Required daily report

The report must show:

- Coverage: configured rooms by lane, rooms expected open, reader heartbeat,
  first/last message, messages captured, and rooms that were quiet versus
  unverified.
- Funnel: posted/captured candidates, parser emissions, reviewed alerts, sent
  orders, fills, closes, refusals, stale alerts, duplicates, disabled routes,
  parser gaps, reader outages, and unresolved records.
- Every alert: timestamp, lane, room, caller, original event ID, contract,
  caller price, parsed action, decision, reason, order/fill linkage, and price
  data coverage.
- Actual results: broker-confirmed bot trades, wins/losses/flats, gross and net
  P&L, fees when available, entry slippage, holding time, MAE/MFE, and exit
  classification.
- Counterfactual results: exact caller result where both entry and exit evidence
  exist; current bot policy replayed from the same alert; refused/missed calls
  replayed through the same versioned policy when sufficient tape exists.
- Comparison: paired caller-versus-bot rows, sample size, coverage percentage,
  mean/median result, total P&L, win rate, drawdown, and a confidence interval.
  If the evidence cannot support a comparison, the report says unavailable.
- Data quality: missing room heartbeats, missing event links, missing contracts,
  missing quote windows, unconfirmed fills, unknown callers, and test failures.

## Honest benchmark rules

- Broker records are truth for actual orders, fills, quantities, and realized
  P&L. Book state and logs explain intent but cannot overrule the broker.
- Caller performance is exact only when timestamped caller entry and exit/trim
  evidence can be paired with contemporaneous quotes. A later high is not an
  exit. Missing exits stay unresolved.
- Bot counterfactuals replay the exact policy version and information available
  at that timestamp. They include stale gates, buying-power-independent strategy
  gates, spreads, tick size, order latency, no-fills, partial fills, and the
  actual polling cadence. They never use a future high or low to choose an exit.
- Actual, caller, and simulated outcomes remain separate columns and totals.
- Relay duplicates do not count twice. Re-entries and later adds do count as
  distinct events when their source message IDs differ.
- Paper records never enter real-money totals. Manual trades remain available
  for account reconciliation but do not become caller or bot performance.
- A strategy change needs a named hypothesis, minimum sample, uncertainty band,
  out-of-sample or forward validation, regression coverage, and a recorded
  version boundary. One trade or one day can identify a bug, not prove an edge.

## Automated learning loop

1. Capture immutable raw events and quote windows during the day.
2. At 16:40 Eastern, replay every live parser input through the production
   parser and reconcile every stage of the lifecycle.
3. Write the daily report and append normalized benchmark rows.
4. Put unexplained gaps and new message shapes in a review queue.
5. Fix a parser or reliability class once, add the real message as a regression
   case, replay the historical corpus, and reject changes that introduce junk.
6. Recompute versioned strategy comparisons on the accumulated eligible sample.
7. Promote a strategy change only after the evidence threshold is met. Discord
   text and historical Claude notes never rewrite live trading rules themselves.

## Current implementation

Already present:

- Exact Discord and Whop exports, production-parser replay, missed-entry
  heuristics, a durable review queue, and full regression execution.
- `master_alerts.csv`, `master_ledger.csv`, `master_broker.csv`, quote tapes,
  RN ledger, telemetry, and per-trade postmortems.
- Broker-truth reconciliation and separation of manual, bot, paper, and unknown
  records.
- A weekday 16:40 audit plus `daily-reports/REPORT-<date>.md` with coverage,
  alert flow, decisions, actual outcomes, recovered gaps, and room activity.
- A common tape registry and a clean Databento historical tape for replay.

Remaining work, in order:

1. Make `event_id`/`trade_id` durable across raw capture, parser verdict,
   `master_alerts`, order journal, broker legs, postmortem, and benchmark rows.
   Current joins still reconstruct some identity from text, contract, and time.
2. Record caller and room directly on telemetry; they are blank in existing
   rows and require weaker recovery from logs.
3. Extend alert quote capture to every valid option alert within the API budget,
   including refused and missed calls, and record an explicit coverage result
   when no quote window can be obtained. `alert_tape.csv` began on 2026-09-11,
   so it cannot recover earlier gaps by itself.
4. Build an append-only counterfactual ledger with one row per event and policy
   version. The current daily report describes comparison evidence but does not
   yet produce a complete cumulative caller-versus-bot benchmark.
5. Pair caller exits and trims to their originating event. Caller targets are
   mostly absent today, so exact caller outcomes are often unavailable.
6. Add cumulative and rolling 5/20-day benchmark sections, grouped by caller,
   room, strategy version, DTE, ticker class, and refusal reason, with coverage
   and uncertainty beside every result.
7. Add futures broker fills and value them with the correct contract multiplier;
   current futures records can be counted but often cannot be assigned P&L.

## Databento scope on 2026-09-11

`databento_tape_clean.csv` is cached locally and usable without another API
purchase: 1,022,106 quote rows, 510 distinct option contracts, 49 trading days,
2026-06-12 through 2026-09-08. It is market bid/ask history for requested
contracts, not one caller's alerts. The covered universe is mixed: 479 distinct
contracts overlap manual-trade ledger rows and 103 overlap live non-manual bot
rows; the sets overlap when both traded the same OCC contract. Caller/room
identity comes from alert and ledger records, not from Databento.

The configured Databento credential is present. New downloads may consume
credit and may be limited by the OPRA license window, so cached data should be
used first and any paid backfill should begin with a quoted cost and a precise
missing-contract list.
