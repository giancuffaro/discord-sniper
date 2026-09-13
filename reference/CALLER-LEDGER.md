# Caller research data

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
