# Stage 4 Data Access and Read-Only Tools Design

## Approval and purpose

The user approved this design direction on 2026-07-14: an offline-fixture-first,
layered ports-and-adapters architecture for point-in-time source data, immutable
snapshots, and strictly read-only internal tools. Stage 4 proves the data-access
boundary for Industrial FII `601138.SH` and Micron `MU`; it does not perform
financial normalization, calculations, research, model calls, Agent execution,
RAG, MCP, or trading.

The stage is expected to conclude `CONDITIONAL GO` when the offline architecture,
provider contracts, snapshots, and tool contracts pass while licensed live
market-data or SEC Archive access remains blocked. A `GO` result is not obtained
by weakening source, credential, or live-test requirements.

## Chosen architecture

The existing modular monolith gains six separated boundaries:

1. `providers/` defines provider capabilities, typed response envelopes, a
   registry, the unified safe HTTP client, cache, rate limiter, and offline
   fixture adapters. Providers never create database sessions.
2. `infrastructure/blob_storage.py` defines content storage independent of
   provider and database code. Local storage exposes opaque `blob://` URIs;
   callers never control a filesystem path.
3. `domain/data_access/` defines enums, schemas, repository ports, ingestion,
   snapshot, and read/query services without FastAPI or SQLAlchemy imports.
4. `db/models/data_access.py` and `db/repositories/data_access.py` implement the
   PostgreSQL persistence boundary. The migration contains schema only.
5. `tools/` exposes strict, versioned, read-only contracts over persisted data
   and snapshots. A tool cannot refresh, download, ingest, build, update, or
   delete anything.
6. API routes expose only read services. CLI commands own explicit write
   transactions for provider bootstrap, fixture ingestion, and snapshot build.

Dependencies point inward: API and CLI compose services; tools and domain
services depend on repository protocols; repositories implement those protocols;
providers and blob storage are injected. No import opens a network connection,
database session, or file.

## Source and fixture policy

Stage 4 does not promote an undocumented public website endpoint into a live
production provider. Provider records preserve the Stage 1 decision:

| Source | Stage 4 status | Live behavior |
| --- | --- | --- |
| Stage 1 validated SSE response excerpts | `EXPERIMENTAL` fixture provenance | `BLOCKED` pending automation/cache rights |
| Stage 1 validated Nasdaq response excerpts | `EXPERIMENTAL` fixture provenance | `BLOCKED` pending licensed U.S. EOD entitlement |
| SEC submissions and Company Facts | `APPROVED_FOR_PERSONAL_RESEARCH_ONLY` | submissions/facts adapter contract only; live disabled by default |
| SEC Archives | `NEEDS_CREDENTIALS` | `BLOCKED` until a real SEC contact and reproducible access exist |
| Tushare Pro | `NEEDS_CREDENTIALS` | `BLOCKED` until a token and personal-cache terms are confirmed |
| Nasdaq Data Link / Alpha Vantage EOD | `NEEDS_LICENSE_CONFIRMATION` | `BLOCKED` until a suitable licensed product is configured |

Repository fixtures are safe, immutable crops of values explicitly recorded by
Stage 1. Every fixture has a sibling manifest recording provider, source URL or
endpoint type, security, capture time, publication time when known, content
type, crop status/rules, SHA-256 checksum, and authorization/use limits. Fixture
responses and all outward representations carry `FIXTURE`, `OFFLINE`, and
`NOT_LIVE` markers.

Only values preserved in Stage 1 evidence are allowed. The confirmed latest
daily rows and document metadata may be stored. No additional bar, financial
amount, company action, publication timestamp, or provider identifier is
invented. Because Stage 1 did not preserve verified financial amounts in the
repository, financial-fact results remain empty with `PARTIAL` and a warning.
Missing values are never represented as zero, empty string, or an estimate.

## Provider and HTTP boundary

Providers declare a stable code, version, status, capabilities, allowed hosts,
credential requirements, and terms state. Each call receives a validated
provider mapping plus explicit `research_as_of_time` and returns a typed raw
envelope with records, source metadata, warnings, and quality status.

The unified HTTP client accepts only configured HTTPS URL templates. It rejects
credentials in URLs, IP literals, private/loopback/link-local targets, unexpected
ports, unapproved hosts, and redirects to unapproved hosts. It keeps TLS
verification enabled, bounds redirects/body size/timeouts/retries, retries only
idempotent GET requests for 429 and selected 5xx responses, honors bounded
`Retry-After`, sends configured User-Agent/Accept headers, supports ETag and
Last-Modified revalidation, and redacts tokens, authorization, cookies, and
sensitive query parameters. Providers cannot construct an alternative client.

Network access is disabled in ordinary settings. Live smoke tests live outside
the default pytest testpath and require `RUN_LIVE_PROVIDER_TESTS=1` plus the
provider's real configuration. Missing requirements produce `BLOCKED`, never a
fabricated pass. Default tests reject non-loopback sockets; loopback remains
available only for PostgreSQL integration tests.

## Persistence and lineage

Migration `0003_create_data_access_and_snapshots` creates:

- `data_providers` and `provider_instrument_mappings`;
- `ingestion_runs` and `provider_request_logs`;
- immutable `raw_payloads`;
- `daily_price_bars`, `corporate_actions`, `provider_financial_facts`, and
  `source_documents`;
- `data_snapshots` and `snapshot_items`.

All tables use UUID keys, UTC-aware timestamps, named foreign keys with
restrictive deletion, named string CHECK constraints, and indexes justified by
actual lookups. Decimal values use PostgreSQL `NUMERIC`; volume uses exact
integer/numeric storage. A source record always references its raw payload.
Provider revisions create new raw payload/source rows and never overwrite old
evidence. The migration performs no network access and inserts no provider or
sample business data.

`RawPayload` stores small JSON inline and larger content in injected BlobStorage.
It records SHA-256, byte size, content type, provider/parser/schema versions,
publication time when known, and retrieval time. Content is immutable after
creation. Duplicate checksums are indexed for reconciliation but do not erase
request lineage.

## Ingestion and idempotency

`IngestionService` resolves an active provider mapping, checks capability and
provider policy, creates or reuses an idempotent run, calls the injected
provider, records request metadata, persists an immutable raw payload, and
writes provider-neutral raw records in one category-specific transaction.

The idempotency key hashes provider, security, category, validated parameters,
as-of, date range, provider version, and schema version. Repeating the same
fixture ingestion returns the existing result without duplicating data. A
provider correction with different content creates a new payload/version.
Statuses are only `PASS`, `PARTIAL`, `BLOCKED`, `FAIL` (plus lifecycle states on
the run), with safe error codes and bounded warnings.

## Point-in-time snapshot semantics

`research_as_of_time` is required, timezone-aware, and converted to UTC. The
snapshot builder selects only source data demonstrably public no later than the
cutoff. `retrieved_at` and financial `period_end` never substitute for
`source_published_at`.

Where publication time is unknown, the record is not silently treated as known.
For the Stage 1 daily fixture, eligibility additionally requires its local
trading date not to exceed the exchange-local as-of date; inclusion produces a
warning and forces `PARTIAL`. A record with a known publication time after the
cutoff is always excluded. Tests include a future record to prove this filter.

Snapshot items are sorted by category, provider, record type, record ID, source
publication time, retrieval time, and checksum input. The deterministic SHA-256
digest includes security, UTC cutoff, snapshot version, and the sorted item
descriptors. A BUILDING snapshot transitions atomically to COMPLETE or PARTIAL.
COMPLETE snapshots and their items cannot be updated or deleted through the
repository; any later data creates a new snapshot. A failed build never becomes
COMPLETE.

Both `601138.SH` and `MU` receive reproducible snapshots. Given the honest source
gaps, initial sample snapshots are expected to be `PARTIAL`, not COMPLETE.

## Read-only tools and permissions

The stable tool registry contains version `1.0.0` contracts for:

- `get_latest_close`;
- `get_daily_price_history`;
- `get_corporate_actions`;
- `get_reported_financial_facts`;
- `list_source_documents`;
- `get_source_document_metadata`;
- `get_data_snapshot`;
- `list_snapshot_items`.

Every registration declares JSON-compatible input/output schemas, domain,
permission, read-only state, network prohibition, and snapshot requirement.
Registered query tools are `READ_ONLY`; ingestion, download, and snapshot build
remain `INTERNAL_WRITE` and are not registered. Deletion, provider credential
changes, mapping changes, arbitrary SQL/URL, and destructive database actions
are `ADMIN_ONLY` or `FORBIDDEN_FOR_AGENT`.

Tool envelopes contain the tool/version, structured status/data, source IDs,
snapshot ID, UTC as-of/retrieval times, warnings, and count-based quality fields.
Decimal values serialize as strings. Tools read the selected snapshot/as-of and
never cause a refresh, download, write, calculation, natural-language advice,
model call, or RAG operation.

## API and CLI

The existing `/api/v1` prefix gains the eight requested GET routes. They use
bounded date ranges and pagination, stable 404/422/503 errors, request IDs, and
response schemas that exclude raw bodies, credentials, SQL, and local storage
paths. API dependencies provide read-only repository/query services only.

Typer gains `data` and `tools` groups. `data ingest` and `data snapshot create`
are the only Stage 4 user-facing write paths; they require explicit fixture mode
or explicit live enablement and own commit/rollback. Read commands share the
same query/tool services as API and the internal tool registry. Human and JSON
output always identify fixture results as `FIXTURE / OFFLINE / NOT_LIVE`.

## Verification and completion

Every production behavior follows RED, observed failure, minimum GREEN,
refactor, and focused regression. Provider contracts use offline fixture
adapters. PostgreSQL integration proves all tables, constraints/indexes,
idempotency, revisions, lineage, rollback, snapshot cutoff, immutability, and
both sample snapshots. API and CLI contract tests prove read/write boundaries
and safe output.

The final gate is `uv sync`, Ruff, format check, strict mypy, full pytest with
warnings as errors, development and isolated-test migration upgrade/downgrade/
upgrade, sample ingestion/snapshot/tool smoke tests, and two written Reflection
rounds. Live outcomes are reported separately as `BLOCKED` unless explicit real
configuration becomes available. Stage 5 is not entered or inferred.
