# Caller research data

Run `python caller_ledger.py` from the project to refresh the additive SQLite catalog.
Local outputs live under `local-reader-measure/caller-identity/`:

- `callers.sqlite3`: queryable author observations, raw message variants, source file/line provenance, confirmed accounts and feed evidence.
- `CALLER-LEDGER.md`: complete readable coverage roster.
- `registry.json`: curated account identity evidence. Import never assigns its IDs by display-name similarity.

Example query: `SELECT * FROM caller_coverage WHERE label LIKE '%Honey%' ORDER BY retained_records DESC;`
This orders by retained records, not profitability. The catalog includes chat participants; caller status is unverified until reviewed. Unknown server IDs remain NULL when no configured channel URL establishes them.

Scope: retained `signal-room-chat*.txt` and `grab *.txt` exports, plus configured channels. This is not a complete Discord membership export or an automatically scheduled ingestion service. Reruns preserve prior evidence and group exact legacy export repeats. Stable-ID edits are separate content variants. Source timestamps retain their original precision/timezone ambiguity.

Backtest joins must use confirmed account/feed relationships and exact contracts with entry/exit evidence. Broker actual results, caller hypothetical results, and ratchet simulations must remain separate. This catalog intentionally supplies no fabricated win rates and has no live order or watched-room side effects.
