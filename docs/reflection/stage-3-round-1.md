# Stage 3 Reflection — Round 1

Date: 2026-07-14

Branch: `stage-3/security-master`

Scope: security master, deterministic resolution, seed, API, CLI, migrations,
tests, and documentation only.

## Review method

The review compared the Stage 3 prompt, implementation plan, ORM/migration,
repository SQL, domain contracts, API/CLI adapters, and real PostgreSQL tests.
Critical query paths were independently reviewed, fixed through focused
regression tests, and re-reviewed. Severity vocabulary is limited to
`CRITICAL`, `HIGH`, `MEDIUM`, and `LOW`.

## Findings

| Problem ID | Role | Severity | Problem description | Evidence | Affected files | Fix | Blocking | Fix status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S3-R1-FM-001 | Financial master-data architect | HIGH | A recognized exchange with a missing symbol originally fell through to generic symbol/alias paths and could bind the wrong security. | `test_recognized_exchange_missing_symbol_does_not_fall_through_to_alias` | `domain/securities/repositories.py`, `domain/securities/resolution.py`, `db/repositories/security_master.py` | Added `ExchangeSymbolLookup`; a recognized venue now returns exact candidates or terminal `NOT_FOUND`. | Yes | FIXED; re-review Approved |
| S3-R1-DB-001 | Database architect | HIGH | Exact alias SQL applied `LIMIT` before deduplicating the same security represented by several alias types. | `test_exact_alias_is_deduplicated_in_postgres_before_limit` | `db/repositories/security_master.py` | Added SQL `DISTINCT` before stable ordering and limit. | Yes | FIXED; re-review Approved |
| S3-R1-DB-002 | Database architect | HIGH | Exchange recognition and symbol lookup used two READ COMMITTED statements, allowing an alias state change between snapshots. | `test_explicit_exchange_lookup_uses_one_postgres_snapshot_statement` | `db/repositories/security_master.py` | Replaced both statements with one outer-join query that returns recognition and candidate from one PostgreSQL statement snapshot. | Yes | FIXED; re-review Approved |
| S3-R1-API-001 | API and product designer | HIGH | `INVALID_QUERY` existed in the public result enum but the service always raised, making that domain status unreachable. | `test_invalid_query_returns_stable_domain_result_without_repository_access` | `domain/securities/resolution.py`, `domain/securities/schemas.py` | Invalid input now returns `INVALID_QUERY`, `NONE`, zero candidates; API maps it to uniform HTTP 422 and CLI to exit 4. | Yes | FIXED; API review Approved |
| S3-R1-API-002 | API and product designer | MEDIUM | PostgreSQL returned aware timestamps in the session `+08:00` timezone while the domain required offset zero, breaking detail endpoints. | `test_timestamped_record_converts_aware_database_timestamp_to_utc`; real API detail contracts | `domain/securities/schemas.py` | Reject naive values but convert any aware database timestamp to UTC at the domain boundary. | No | FIXED |
| S3-R1-SEC-001 | Security engineer | MEDIUM | Alias effective-date boundaries needed direct real-database evidence in addition to inactive-alias tests. | `test_alias_validity_boundaries_use_the_injected_clock_date` | `tests/integration/test_security_resolution_postgres.py` | Added future, expired, and inclusive boundary cases using the injected clock date. | No | FIXED |
| S3-R1-TOOL-001 | Agent, Tool Use and MCP architect | MEDIUM | Final service sorting used raw rather than normalized symbols, weakening byte-stable output for future adapters. | `test_candidate_order_uses_normalized_not_raw_symbol` | `domain/securities/resolution.py` | Stable sort now uses `(exchange_mic, normalize_symbol(symbol), security_id)`. | No | FIXED |
| S3-R1-DB-003 | Database architect | MEDIUM | CLI seed conflict evidence proved non-overwrite but initially did not prove rollback of an insert made earlier in the same transaction. | `test_seed_conflict_fails_without_overwriting_user_change` | `tests/integration/test_security_cli.py` | Test now removes an early exchange alias, triggers a later issuer conflict, then proves the alias insertion rolled back and user edit remained. | No | FIXED |
| S3-R1-API-003 | API and product designer | LOW | Installed console-entry behavior existed only as a manual check and in-process `CliRunner` evidence. | `test_installed_entry_smoke_uses_isolated_postgres` | `tests/integration/test_security_cli.py` | Added subprocess tests against the actual installed `stock-research(.exe)` for help, seed, resolve, and show. | No | FIXED |

## Role conclusions

### 1. Financial master-data architect

- Issuer and Security are separate; an issuer owns a collection of securities.
- Market and Exchange are separate; ticker uniqueness is scoped to exchange.
- Same ticker across exchanges and shared aliases return ambiguity rather than a
  popularity guess.
- Name/code changes are represented by dated aliases; inactive aliases are not
  current matches.
- `is_primary_listing` is nullable and does not assert one security per issuer.
- Delisted securities remain traceable and expose their listing status.

Result: PASS after `S3-R1-FM-001` fix.

### 2. Database architect

- ORM and migration agree on eight tables, named constraints, restricted foreign
  keys, focused indexes, nullable unknown semantics, and complete downgrade.
- Seed uses caller-owned transactions, an advisory transaction lock, no
  overwrite, idempotent inserts, and explicit key-collision failure.
- Real PostgreSQL proves uniqueness, CHECK constraints, deletion restrictions,
  rollback, migration cycling, prefix opclasses, and snapshot-consistent venue
  lookup.

Result: PASS after `S3-R1-DB-001`, `S3-R1-DB-002`, and `S3-R1-DB-003` fixes.

### 3. API and product designer

- All four domain statuses and all seven match types have stable semantics.
- Prefix candidates never auto-resolve and no confidence score exists.
- API and CLI use the same service; errors have safe, fixed adapters.
- Candidate structure is adequate for a future frontend or Tool without
  exposing persistence internals.

Result: PASS after API findings were fixed; independent API and CLI reviews are
Approved/Approved.

### 4. Security engineer

- SQLAlchemy parameters all user-controlled values.
- LIKE escapes `%`, `_`, and `\`; output is bounded to ten.
- Length, Unicode/control characters, invalid grammar, and empty input fail
  safely. Logs never include the raw query or exception text.
- Every API request and CLI operation owns and closes its Session; engines are
  disposed; no external internet dependency exists.

Result: PASS.

### 5. Agent, Tool Use and MCP architect

- Domain normalization, schemas, repository protocol, and resolver do not
  import FastAPI or SQLAlchemy.
- API and CLI are thin adapters over the same stable result schema.
- No Agent Tool, Agent workflow, MCP protocol/server, RAG, market data, or
  financial behavior was implemented.

Result: PASS after deterministic sort correction.

## Round 1 gate

- Open CRITICAL: 0
- Open HIGH: 0
- All blocking findings: FIXED and re-reviewed
- Decision: proceed to Round 2 consistency verification; do not enter Stage 4.
