# Stage 4 Reflection — Round 1

## Conclusion

Round 1 reviewed the complete Stage 4 branch from five required roles. One `HIGH`
finding was validated and fixed through a failing PostgreSQL regression. Unresolved
counts are `CRITICAL=0`, `HIGH=0`, `MEDIUM=1`, `LOW=1`.

The Codex Security exhaustive diff-scan workflow could not be used as a full scan
because it requires a dedicated scan workspace and sub-agent coverage not authorized
for this execution. The security role below is therefore a targeted evidence-based
diff review, not a claim of exhaustive vulnerability coverage.

## Role review

### Financial data engineer

- UTC retrieval/publication times, exchange-local trading dates and reporting dates
  remain distinct.
- `period_end`, `filed_at`, `published_at`, `source_published_at`, and `retrieved_at`
  are not substituted for each other.
- Exact values retain Decimal/NUMERIC and raw units/context; no binary float or
  financial normalization exists.
- Provider revisions coexist through payload/source IDs; history is not overwritten.
- Daily records preserve provider adjustment semantics; no canonical adjustment is
  claimed.
- PostgreSQL point-in-time queries require retrieval by cutoff and known publication
  by cutoff. Exchange-local future dates are excluded.

### Data platform and database architect

- Eleven Stage 4 tables have restrictive foreign keys, named checks/indexes and
  explicit bounded queries.
- Ingestion idempotency, RawPayload checksum/lineage, snapshot deterministic checksum,
  transaction rollback and concurrent replay have PostgreSQL tests.
- Terminal snapshots and items are protected by repository checks and PostgreSQL
  triggers; downgrade/re-upgrade recreates the triggers.
- LocalBlobStorage is root-anchored with opaque URI, traversal/reparse/symlink/hardlink
  defenses and bounded sidecars.

### Tool Use and MCP architect

- Exactly eight `1.0.0` registrations expose strict schemas and `READ_ONLY` metadata.
- Tools depend on the shared query service, not Provider or HTTP adapters.
- No Tool can ingest, refresh, download, build a snapshot, mutate mapping, execute SQL,
  or perform network access.
- Schemas are reusable by a future Agent/MCP adapter, but no Agent or MCP runtime was
  added.

### Security engineer

- The only HTTP client is the shared provider client. It enforces HTTPS, an exact host
  allowlist, public DNS/IP policy, same-origin redirect revalidation, TLS, response
  and MIME bounds, bounded retry/Retry-After, rate limiting, redaction and rejected
  cookies.
- API and Tool scans found no write route or network/storage call.
- Default pytest blocks non-loopback DNS/IP; fixture adapters do not open sockets.
- BlobStorage and response schemas expose opaque IDs/URIs, not local absolute paths,
  SQL, headers, tokens or raw bodies.

### Reliability and test engineer

- Default collection excludes `live_tests/`; the explicit three-provider suite records
  honest `BLOCKED` results.
- Fixture manifests have checked SHA-256 and real-source crop metadata.
- Ingestion partial/fail/blocked transitions, idempotent retry, snapshot replay,
  concurrency and migration cycles use real PostgreSQL.
- Both required sample paths and counterexamples are non-vacuous and inspect persisted
  row counts, IDs, checksums and bytes.

## Findings

| Problem ID | Role | Severity | Description | Evidence | Affected files | Fix | Blocking | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S4-R1-001 | Data platform / reliability | HIGH | CLI ingestion used `InMemoryBlobStorage`, then persisted `blob://memory/...`; after command exit the raw bytes were no longer retrievable, so RawPayload persistence was not durable. | New PostgreSQL test first failed because the stored URI was `blob://memory/...`; process-local backend documentation confirmed lifetime. | `src/stock_research_agent/cli_data.py`, `src/stock_research_agent/config.py`, CLI/config tests and docs | Added absolute, redacted `BLOB_STORAGE_ROOT`; CLI now uses and closes `LocalBlobStorage`. Regression reopens storage after CLI resource scope and compares exact bytes with the fixture. | Yes | FIXED (`146a123`) |
| S4-R1-002 | Data platform / reliability | MEDIUM | Blob write precedes the caller-owned database commit. A rare outer commit failure can leave an unreferenced local blob, although no database row falsely points to missing evidence. | Transaction boundary review of `IngestionService` and CLI commit ownership. | `src/stock_research_agent/domain/data_access/ingestion.py`, `src/stock_research_agent/cli_data.py` | Future operations work: add a durable blob-outbox/garbage-collection ledger before Live payload volume. Current fixture bytes are public, bounded, and content-checksummed. | No | OPEN |
| S4-R1-003 | Security | LOW | Full automated exhaustive security-diff coverage was unavailable under current no-subagent execution constraints. | Security skill preconditions versus current workflow; targeted grep/test review completed instead. | Stage 4 branch | Run the dedicated Codex Security diff scan before production/Live enablement. | No | OPEN |

## Fix verification

Focused TDD cycle:

```text
RED: persisted URI was blob://memory/... and reopenability assertion failed
GREEN: reopenable LocalBlobStorage test plus config/CLI tests — 74 passed
affected ingestion/blob/config/CLI suite — 211 passed
```

Role-oriented safety and database suite:

```text
HTTP policy, BlobStorage, snapshot builder, Tool registry, data API,
migration and PostgreSQL snapshot tests — 326 passed in 43.04s
```

Static results after the HIGH fix:

```text
ruff check: passed
ruff format --check: passed
mypy src: no issues in 73 source files
```

No CRITICAL or HIGH finding remains open. Stage 5 is not authorized.
