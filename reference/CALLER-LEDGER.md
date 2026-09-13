# Caller research data

Entry provenance is separate from exit ownership. `python entry_attribution.py`
compares exact option contract, same date, quantity and a 0–120 second order-to-entry
window, then reads the adjacent WORKING caller. It scans legacy manual rows too.
`entry_attribution` retains candidate orders and their log lines; `trade_attribution`
and the reading copy show recovered entry caller, entry basis and exit method.
Broker adoption times are excluded from timed promotion. Missing times and
competing orders stay candidates. Matches are correlations, not broker-order-ID
proof; repeated ledger rows can share the same order and must not be counted as
distinct trades without deduplication. Legacy manual flags are not rewritten.

## Start here

Open `local-reader-measure/caller-identity/MASTER-RESEARCH.html` for a local,
searchable reading copy of trades, account sightings, author coverage and import
dates. `python research_report.py` regenerates it from SQL without reimporting;
`python research_ledger.py refresh` refreshes sources and rebuilds the report.
The authoritative integrated query file is `callers.sqlite3`, not the HTML.
Original logs, registry and reviewed evidence remain necessary provenance.
The HTML consolidates existing report views; it does not merge unrelated
accounts, alter fills, or import quote tapes and live extension storage.

## Unified attribution

`trade_attribution` combines the original ledger record, recorded caller name,
recovered posting name, origin log evidence, resolved ID, candidate ID and ID
verification status in one SQL view. `attribution_name` prefers the recorded
caller; a fallback recovered name is explicitly marked `name_basis=log_candidate`.
Names remain usable even when an account ID is missing. A posting name does not
establish the human trader behind a relay. Original source records are untouched.

Use `python research_ledger.py trades Brett` or `python research_ledger.py trades
493537866039689217` to search trades by name or account ID (100-row limit).
This merges retained research records and recovery evidence, not the changing
live Active Trades display; live position-book names still live in state.json.

`python recover_trade_sources.py` records timestamp-matched `trades.log` evidence
in `trade_source_recovery` and local `LOG-RECOVERY.md`. Broker adoption timestamps
are not treated as original entry times, nor as proof of manual ownership.
Reviewed historical identity links live in local `reviewed-trade-identities.json`;
`source_supported` populates `resolved_trader_id`, while `verified_trader_id` is
reserved for explicit source trader IDs. Supporting raw-message record IDs remain
attached to each reviewed link. All of these are research-only attributions.

`python trade_identity.py` reconciles current research records into
`trade_identity_links`; refresh also runs it. Query `attributed_research` for
source fields, candidate account IDs, status and explanation together.
Exact alias/channel matches are candidates only, not verified attribution.
An explicit source `trader_id` may establish a source-provided link; `author_id`
alone cannot identify the trader behind a relay. Manual trades stay separate.
Local `TRADE-IDENTITY-COVERAGE.json` and `TRADE-IDENTITY-GAPS.md` show outstanding
work. This does not alter source ledgers, live routing, or performance statistics.

## Integrated trading research database

`python research_ledger.py refresh` refreshes the catalog and imports master alerts,
broker records, reconciled trades, postmortems, and daily caller-outcome CSVs into
the same SQLite file. `python research_ledger.py search CPS` searches imported
records and original messages; `python research_ledger.py gaps` lists missing
identities. Search/gap output is capped at 100 rows; use SQL for full extraction.

`ledger_records` contains typed records with every source field in `payload`.
Blank source values become SQL NULL / JSON null, never zero or a guessed identity.
`source_path` and `source_row` identify CSV records (header is row 1; multiline CSV
records are logical rows). Previous versions remain with `current=0` when a source
is rebuilt. `research_imports` records content hashes and import times.
`research_links` accepts only unambiguous explicit ledger keys on the same date.
No contract/name/time similarity joins are promoted into confirmed relationships.
Missing files retain their last imported snapshot; consult import timestamps.

`account_sightings` stores verified Discord account ID, channel ID, server ID,
observed name and evidence source. `caller_ledger.py` imports local
`browser-collection*.json` evidence plus curated registry observations. This does
not retroactively assign identities to old messages based only on matching names.
`VERIFIED-ACCOUNTS.md` and `MISSING-INFORMATION.md` in the local identity folder
record the browser collection pass and outstanding gaps. Current visible-author
coverage is distinct from a complete historical membership/caller census.

This integrates search and source evidence; historical records without common IDs
remain unlinked. Quote tapes and simulation engines are not imported by this version.
Refresh is manual, not a live background process. Original ledgers remain authoritative.

Run `python caller_ledger.py` from the project to refresh the additive SQLite catalog.
Local outputs live under `local-reader-measure/caller-identity/`:

- `callers.sqlite3`: queryable author observations, raw message variants, source file/line provenance, confirmed accounts and feed evidence.
- `CALLER-LEDGER.md`: complete readable coverage roster.
- `registry.json`: curated account identity evidence. Import never assigns its IDs by display-name similarity.

Example query: `SELECT * FROM caller_coverage WHERE label LIKE '%Honey%' ORDER BY retained_records DESC;`
This orders by retained records, not profitability. The catalog includes chat participants; caller status is unverified until reviewed. Unknown server IDs remain NULL when no configured channel URL establishes them.

Scope: retained `signal-room-chat*.txt` and `grab *.txt` exports, plus configured channels. This is not a complete Discord membership export or an automatically scheduled ingestion service. Reruns preserve prior evidence and group exact legacy export repeats. Stable-ID edits are separate content variants. Source timestamps retain their original precision/timezone ambiguity.

Backtest joins must use confirmed account/feed relationships and exact contracts with entry/exit evidence. Broker actual results, caller hypothetical results, and ratchet simulations must remain separate. This catalog intentionally supplies no fabricated win rates and has no live order or watched-room side effects.
