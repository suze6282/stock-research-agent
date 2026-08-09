# Stage 4 Data Access and Read-Only Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build traceable, reproducible, point-in-time raw-data access and immutable snapshots for `601138.SH` and `MU`, then expose the persisted evidence through strict read-only internal tools, API routes, and CLI queries.

**Architecture:** An offline-fixture-first ports-and-adapters design separates providers, safe HTTP, BlobStorage, domain services, SQLAlchemy persistence, snapshot construction, and read-only tools. CLI/internal services own all ingestion and snapshot writes; API and registered tools only read persisted data. Stage 1 evidence is the sole sample-data source, and unavailable live sources remain honestly `BLOCKED`.

**Tech Stack:** Python 3.12.13, Pydantic 2, SQLAlchemy 2, PostgreSQL 17, Alembic, FastAPI, Typer, httpx, structlog, pytest, respx, Ruff, and strict mypy.

## Global constraints

- Develop only on `stage-4/data-access-tools`; never implement Stage 4 directly on `main` and never merge without a later explicit choice.
- Default runtime and default pytest are offline. Loopback is allowed only for the project-owned PostgreSQL integration database.
- Every formal fixture is an immutable safe crop of a real response already captured and validated in Stage 1. Do not invent bars, financial values, document dates, SEC data, actions, identifiers, or timestamps.
- Every fixture has a checked SHA-256 manifest with provider, source/endpoint, security, capture time, publication time when known, content type, crop flag/rules, and usage restrictions.
- Every fixture-facing API, CLI, tool, log, and report uses the markers `FIXTURE`, `OFFLINE`, and `NOT_LIVE`.
- Missing values remain null/absent with `PARTIAL` and warnings; never replace them with zero, empty string, or an estimate.
- Tushare live, licensed U.S. EOD live, and SEC Archive live remain `BLOCKED` unless real credentials, entitlement, or a real SEC contact are explicitly configured later.
- Live smoke tests live outside default pytest collection and require `RUN_LIVE_PROVIDER_TESTS=1`; no live check enters default CI.
- Provider, HTTP, BlobStorage, domain, persistence, snapshot, tool, API, and CLI boundaries remain independently testable and dependency-injected.
- A provider never creates a Session, a repository never calls a provider, and an import never opens the database, network, or filesystem.
- API and registered tools are read-only. A read cannot trigger refresh, ingestion, download, snapshot build, mutation, or deletion.
- Ingestion and snapshot build are `INTERNAL_WRITE`, exposed only through explicit CLI/internal services with owned commit/rollback.
- Use aware UTC datetimes. A market trading date remains the exchange-local `date`; `retrieved_at` and `period_end` never stand in for publication time.
- A known `source_published_at > research_as_of_time` is excluded. Unknown publication time emits a warning and prevents a COMPLETE sample snapshot.
- COMPLETE snapshots and their items are immutable; every changed data set creates a new snapshot.
- Raw payloads are immutable and never overwritten by parsed records, provider revisions, normalization, or later stages.
- All amount/price/fact values use Decimal/NUMERIC. JSON renders them as strings; no binary float enters canonical raw records.
- All external URLs are untrusted. Enforce HTTPS, allowlisted hosts, redirect revalidation, body/MIME limits, TLS verification, bounded retry, low-frequency limiting, and secret redaction.
- Use PostgreSQL parameter binding, restrictive foreign keys, named constraints, explicit indexes, bounded pagination, and no arbitrary sort/provider/URL/SQL input.
- Do not add financial standardization, metric keys, TTM, ratios, valuation, document parsing, OCR, RAG, embeddings, model calls, Agent execution, Reflection runtime, MCP Server, frontend, broker integration, or trading.
- Follow strict RED -> verify expected failure -> GREEN -> refactor for every behavior. Never delete, skip, or weaken an existing test.
- Real PostgreSQL, not SQLite, is required for migration, constraint, idempotency, snapshot, and sample acceptance evidence.
- Final quality gates must exit 0 with zero warnings. Stage 5 remains unauthorized.

---

## 1. Objective

- [ ] Bind stable Stage 3 `security_id` values to auditable provider mappings.
- [ ] Persist provider calls, immutable raw payloads, raw price/action/fact/document records, and their lineage.
- [ ] Build reproducible point-in-time snapshots for both required securities.
- [ ] Expose eight stable, read-only internal tool contracts plus bounded read-only API and CLI queries.
- [ ] Report data gaps as `PARTIAL`/`BLOCKED` rather than inventing evidence.

## 2. In scope

- [ ] Provider capabilities/registry/contracts; safe shared HTTP; cache; rate limit.
- [ ] Data-provider/mapping/run/request/payload/raw-record/snapshot PostgreSQL models and revision `0003`.
- [ ] Local and in-memory BlobStorage.
- [ ] Offline fixture adapter, ingestion service, snapshot builder, query services, and lineage.
- [ ] Eight read-only tools, eight read-only API routes, and Stage 4 CLI groups.
- [ ] Two Stage 1-derived sample snapshots, PostgreSQL/contract/API/CLI tests, docs, and two Reflection rounds.

## 3. Explicit exclusions

- [ ] No unlicensed live provider is enabled and no public website backend is promoted to production use.
- [ ] No financial normalization, cross-provider field mapping, discrete-quarter derivation, TTM, calculation, metric, valuation, report, RAG, model, Agent, MCP, frontend, broker, or trade behavior.
- [ ] No arbitrary URL, SQL, filesystem path, provider selection, sorting expression, or destructive tool is exposed.

## 4. Approved and blocked data sources

| Provider/source record | Stage 4 status | Capabilities represented | Live result |
| --- | --- | --- | --- |
| `STAGE1_SSE_FIXTURE` | `EXPERIMENTAL` | daily price excerpt, filing metadata excerpt | `BLOCKED`: automation/cache rights not confirmed |
| `STAGE1_NASDAQ_FIXTURE` | `EXPERIMENTAL` | daily price excerpt | `BLOCKED`: no licensed U.S. EOD entitlement |
| `STAGE1_SEC_FIXTURE` | `APPROVED_FOR_PERSONAL_RESEARCH_ONLY` | filing metadata; facts capability with honest empty result | `BLOCKED` for Archive; default offline for submissions/facts |
| `TUSHARE_PRO` | `NEEDS_CREDENTIALS` | declared reference/prices/actions/facts/filings capability | `BLOCKED`: token and cache terms absent |
| `NASDAQ_DATA_LINK` | `NEEDS_LICENSE_CONFIRMATION` | declared daily-price/action capability | `BLOCKED`: subscribed dataset absent |
| `ALPHA_VANTAGE` | `NEEDS_CREDENTIALS` | declared daily-price/action capability | `BLOCKED`: key/entitlement absent |
| `SEC_ARCHIVES` | `NEEDS_CREDENTIALS` | filing metadata/document download | `BLOCKED`: real SEC contact and reproducible document access absent |

- [ ] Provider records distinguish capability from actual availability and never store credentials.
- [ ] Stage 1 website responses remain fixture/cross-check evidence, not live production APIs.

## 5. File and package map

| Path | Responsibility |
| --- | --- |
| `src/stock_research_agent/domain/data_access/enums.py` | controlled statuses, categories, record/document/action types |
| `src/stock_research_agent/domain/data_access/schemas.py` | strict point-in-time records, quality, ingestion, snapshot, and query schemas |
| `src/stock_research_agent/domain/data_access/repositories.py` | persistence protocols consumed by domain services/tools |
| `src/stock_research_agent/domain/data_access/ingestion.py` | provider-to-persistence orchestration and idempotency |
| `src/stock_research_agent/domain/data_access/snapshots.py` | as-of selection, deterministic checksum, immutable completion |
| `src/stock_research_agent/domain/data_access/queries.py` | shared read service for tools/API/CLI |
| `src/stock_research_agent/providers/base.py` | provider request/response ports and adapter protocol |
| `src/stock_research_agent/providers/capabilities.py` | capability declarations and validation |
| `src/stock_research_agent/providers/registry.py` | duplicate-safe in-process adapter registry |
| `src/stock_research_agent/providers/http_client.py` | allowlisted HTTPS client, retry, revalidation, safe response |
| `src/stock_research_agent/providers/rate_limit.py` | injected low-frequency limiter |
| `src/stock_research_agent/providers/cache.py` | ETag/Last-Modified response metadata cache protocol/implementation |
| `src/stock_research_agent/providers/fixtures/provider.py` | package-resource offline fixture adapter |
| `src/stock_research_agent/providers/fixtures/data/` | immutable JSON crops and sibling manifests |
| `src/stock_research_agent/infrastructure/blob_storage.py` | BlobStorage protocol plus local/in-memory implementations |
| `src/stock_research_agent/db/models/data_access.py` | eleven Stage 4 SQLAlchemy tables |
| `src/stock_research_agent/db/repositories/data_access.py` | PostgreSQL implementation of write/read/snapshot ports |
| `migrations/versions/0003_create_data_access_and_snapshots.py` | reversible Stage 4 schema only |
| `src/stock_research_agent/tools/permissions.py` | tool permission levels |
| `src/stock_research_agent/tools/schemas.py` | strict versioned input/output envelope models |
| `src/stock_research_agent/tools/registry.py` | duplicate-safe registry/describe/list, no execution side effects |
| `src/stock_research_agent/tools/market_data.py` | latest close/history/actions read tools |
| `src/stock_research_agent/tools/financial_data.py` | reported raw-facts read tool |
| `src/stock_research_agent/tools/documents.py` | source-document list/metadata read tools |
| `src/stock_research_agent/tools/snapshots.py` | snapshot/detail item read tools |
| `src/stock_research_agent/api/routes/data.py` | bounded provider/security data GET routes |
| `src/stock_research_agent/api/routes/snapshots.py` | bounded snapshot GET routes |
| `src/stock_research_agent/cli_data.py` | data provider/mapping/ingest/snapshot/query commands |
| `src/stock_research_agent/cli_tools.py` | tool list/describe commands |
| `live_tests/test_provider_smoke.py` | explicitly invoked, environment-gated live smoke only |

## 6. Data model and relationships

```text
Security 1 ── * ProviderInstrumentMapping * ── 1 DataProvider
   │                                               │
   ├── * IngestionRun ── * ProviderRequestLog      │
   │          │                  │                 │
   │          └── * RawPayload ──┘                 │
   │                  │                            │
   │                  ├── * DailyPriceBar          │
   │                  ├── * CorporateAction        │
   │                  ├── * ProviderFinancialFact  │
   │                  └── * SourceDocument         │
   │
   └── * DataSnapshot ── * SnapshotItem ───────────┘
```

- [ ] All owner/provider/security foreign keys use `ON DELETE RESTRICT`; no ORM delete cascade.
- [ ] `DataProvider`: code/name/type/status/terms/capabilities/base/docs URLs and UTC timestamps; no secrets.
- [ ] `ProviderInstrumentMapping`: security/provider identity, optional exchange/instrument ID, validity, primary flag, JSON metadata/source, timestamps.
- [ ] `IngestionRun`: category/lifecycle/quality status, UTC as-of/times, unique idempotency key, counts, safe error fields.
- [ ] `ProviderRequestLog`: safe URL only, method/times/status/attempt/cache validators/size/safe error; no headers, cookies, or body.
- [ ] `RawPayload`: provider/run/request/security/category/content type, inline JSON or opaque storage URI, SHA-256, versions, size and UTC source/retrieval times.
- [ ] `DailyPriceBar`: exact OHLC/volume, provider symbol, local trading date, optional UTC market/source times, currency, adjustment semantic, payload lineage.
- [ ] `CorporateAction`: provider action ID/type/dates/exact amount or ratio/status/source times/payload lineage; missing stays null.
- [ ] `ProviderFinancialFact`: raw provider concept/label/taxonomy/context/dimensions/exact value/unit/period/filing flags and lineage; no canonical metric key.
- [ ] `SourceDocument`: raw metadata, accession/announcement IDs, source URL, MIME/storage/checksum/size/status/times and payload lineage; no parsed text.
- [ ] `DataSnapshot`: security, aware UTC cutoff, version/status/completion/checksum, fixed `raw-data-v1`, notes and timestamps.
- [ ] `SnapshotItem`: category/provider/source table+record ID/source/retrieval times and deterministic item checksum input.

## 7. Constraints and indexes

| Constraint/index | Purpose |
| --- | --- |
| unique `data_providers.code` | stable provider lookup |
| unique provider mapping identity plus security/provider index | provider symbol resolution and active mapping lookup |
| unique `ingestion_runs.idempotency_key`; security/category/as-of index | retry idempotency and run history |
| request-log ingestion-run index | bounded lineage traversal |
| raw checksum and security/category/source-time indexes | evidence reconciliation and point-in-time selection |
| daily security/date plus provider/symbol/date/payload uniqueness | history/latest queries without destroying revisions |
| action security/ex-date and provider action/payload uniqueness | bounded action history and idempotency |
| fact security/period-end and security/filed-time indexes | raw period/filed queries |
| document security/published-time and nullable accession indexes | bounded filing lookup |
| snapshot security/as-of/version uniqueness and status checks | deterministic point-in-time lookup |
| snapshot item snapshot/category and unique source reference | listing and no duplicate item |

- [ ] Named CHECK constraints enforce controlled strings, non-negative prices/volume/amount sizes, high >= low, valid date ranges, aware non-null database timestamps, and inline-versus-blob payload shape.
- [ ] No PostgreSQL native ENUM, extension, float amount, full text, trigram, vector, or blind all-column index.

## 8. Migration order and rollback

1. Data providers.
2. Provider mappings.
3. Ingestion runs and request logs.
4. Raw payloads.
5. Daily bars, corporate actions, financial facts, and source documents.
6. Data snapshots and snapshot items.
7. Named indexes.
8. Downgrade in exact reverse dependency order, preserving migrations `0001` and `0002`.

- [ ] Migration inserts no business/provider/fixture data, reads no credential, and performs no network access.
- [ ] Validate development `upgrade head -> downgrade -1 -> upgrade head`.
- [ ] Validate isolated test `base -> 0001 -> 0002 -> 0003 -> downgrade -1 -> upgrade head`.

## 9. Raw payload and BlobStorage strategy

- [ ] Canonical fixture bytes are verified against the sibling manifest checksum before parsing.
- [ ] Small JSON is stored as JSONB; larger/binary content is stored by injected BlobStorage with an opaque `blob://` URI.
- [ ] Blob keys are UUID/content-derived; caller paths, absolute paths, `..`, separators, and traversal are rejected.
- [ ] `LocalBlobStorage` remains under configured root and never returns a local absolute path.
- [ ] `InMemoryBlobStorage` is used for unit tests and never touches user directories.
- [ ] Existing content cannot be overwritten under the same key; delete is not registered as a tool.

## 10. As-of semantics

- [ ] Every ingestion and snapshot request has a timezone-aware `research_as_of_time`, normalized to UTC.
- [ ] `trading_date` is an exchange-local date; `market_timestamp` is aware UTC if the source supplied it.
- [ ] `period_start`, `period_end`, and `instant_date` are reporting dates, not publication times.
- [ ] `filed_at`, `published_at`, and `source_published_at` stay separate from `retrieved_at`.
- [ ] Known post-cutoff publication is excluded; unknown publication emits `SOURCE_PUBLISHED_AT_UNKNOWN` and forces PARTIAL.
- [ ] A daily record also requires `trading_date <= exchange-local(as_of).date()`.

## 11. Snapshot model

- [ ] Builder locks a BUILDING snapshot row, queries requested categories with bounded as-of filters, and writes sorted SnapshotItems.
- [ ] Checksum is SHA-256 over security, UTC as-of, snapshot version, requested categories, and sorted item descriptors.
- [ ] COMPLETE is allowed only when required categories have no missing publication/required-data warning.
- [ ] PARTIAL remains reproducible and immutable after completion; FAILED never carries a completion checksum.
- [ ] Repository rejects update/delete/item insertion for completed snapshots; new evidence creates a new version/snapshot.
- [ ] Both Stage 1 samples build independently and repeated builds over identical inputs produce identical content checksums.

## 12. Tool contracts and permissions

| Tool version `1.0.0` | Permission | Network | Writes | Snapshot behavior |
| --- | --- | ---: | ---: | --- |
| `get_latest_close` | `READ_ONLY` | no | no | explicit snapshot or as-of |
| `get_daily_price_history` | `READ_ONLY` | no | no | explicit snapshot or as-of |
| `get_corporate_actions` | `READ_ONLY` | no | no | explicit snapshot or as-of |
| `get_reported_financial_facts` | `READ_ONLY` | no | no | explicit snapshot or as-of |
| `list_source_documents` | `READ_ONLY` | no | no | explicit snapshot or as-of |
| `get_source_document_metadata` | `READ_ONLY` | no | no | persisted metadata only |
| `get_data_snapshot` | `READ_ONLY` | no | no | required snapshot ID |
| `list_snapshot_items` | `READ_ONLY` | no | no | required snapshot ID |

- [ ] Registry metadata includes name/version/domain/input/output schema/permission/read-only/network/snapshot flags.
- [ ] Duplicate name+version is rejected; registry list/describe never executes a tool.
- [ ] Refresh, ingest, snapshot build, and download are `INTERNAL_WRITE` and unregistered.
- [ ] Delete, credential/mapping mutation, arbitrary URL/SQL, and database DDL are `ADMIN_ONLY` or `FORBIDDEN_FOR_AGENT`.
- [ ] Envelope contains tool/version/status/data/source IDs/snapshot/as-of/retrieved/warnings/quality; Decimal JSON values are strings and no pseudo-confidence exists.

## 13. API and CLI

### Read-only API

- [ ] `GET /api/v1/data/providers`
- [ ] `GET /api/v1/securities/{security_id}/prices/latest`
- [ ] `GET /api/v1/securities/{security_id}/prices`
- [ ] `GET /api/v1/securities/{security_id}/corporate-actions`
- [ ] `GET /api/v1/securities/{security_id}/financial-facts`
- [ ] `GET /api/v1/securities/{security_id}/documents`
- [ ] `GET /api/v1/snapshots/{snapshot_id}`
- [ ] `GET /api/v1/snapshots/{snapshot_id}/items`

Inputs use strict UUID/date/aware-time/category/page schemas; history span and page size are bounded. Outputs exclude raw bodies, absolute storage paths, SQL, tokens, headers, and secrets. 404/422/503 reuse the existing safe error contract and `X-Request-ID`.

### CLI/internal writes and reads

- [ ] `stock-research data providers|mappings`
- [ ] `stock-research data ingest QUERY --category ... --as-of ... --fixture`
- [ ] `stock-research data snapshot create QUERY --as-of ...`
- [ ] `stock-research data snapshot show SNAPSHOT_ID`
- [ ] `stock-research data latest-close|price-history|financial-facts|documents ...`
- [ ] `stock-research tools list|describe TOOL_NAME`

Fixture write output visibly prints `FIXTURE OFFLINE NOT_LIVE`. Operational failures are nonzero; `BLOCKED` and `FAIL` have distinct exit codes. CLI and API compose the same domain/tool services and do not duplicate provider or query rules.

## 14. Fixture and Live isolation

- [ ] Fixture JSON/manifests are package resources, contain no token/personal data, and are verified at load time.
- [ ] Formal sample fixture manifests use `captured_at` from Stage 1 (`2026-07-11` evidence window) without inventing a more precise instant than recorded.
- [ ] Unknown source publication time is JSON null plus warning, not copied from retrieval time.
- [ ] `live_tests/` is outside `[tool.pytest].testpaths`; explicit invocation requires the live flag and provider config.
- [ ] Default tests monkeypatch socket creation/connect to deny non-loopback destinations and verify no provider attempts a connection.
- [ ] CI runs only default offline tests. Live outcomes are reported separately and remain BLOCKED when configuration is absent.

## 15. Data quality and lineage

- [ ] Quality contains `status`, present/total counts, missing fields, duplicate/conflict counts, latest period/trading date, optional age, reconciliation flag, and warnings.
- [ ] Status values are exactly `PASS`, `PARTIAL`, `BLOCKED`, `FAIL`; there is no numeric confidence/completeness score.
- [ ] Every parsed record points to `source_payload_id`; every payload points to provider/run/request and preserves checksum/version/times.
- [ ] Provider conflicts and revisions coexist and remain visible; no silent merge or overwrite.

## 16. Testing matrix

- [ ] Provider registry/capability/unavailable/disabled/credential/import-network tests.
- [ ] HTTP timeout, 429, selected 5xx, 404 non-retry, Retry-After, retry cap, redirect/allowlist, redaction, body limit, ETag/304, User-Agent, and TLS tests.
- [ ] Blob checksum/metadata/immutability/path traversal and inline-vs-blob tests.
- [ ] Decimal/high-low/negative/null/idempotent/revision/adjustment price tests.
- [ ] Raw-fact unit/label/taxonomy/context/cumulative flags and explicit no-TTM/no-metric tests.
- [ ] Document metadata/PARTIAL/MIME/size/checksum/storage/no-parsing tests.
- [ ] As-of/future exclusion/unknown publication/PARTIAL/checksum/replay/immutability/failure snapshot tests.
- [ ] Strict tool schema/version/permission/read-only/no-refresh/no-secret/no-raw/Decimal/status tests.
- [ ] Offline provider contracts for prices, facts, filings, warnings, provenance, and future exclusion.
- [ ] Real PostgreSQL tables/FKs/unique/CHECK/index/rollback/session/migration/idempotency/revision/snapshot/sample tests.
- [ ] API providers/data/snapshot/error/request-ID/OpenAPI/no-leak/no-network contracts.
- [ ] CLI fixture/block/idempotency/snapshot/query/tool/JSON/human/exit/no-leak/no-network tests.
- [ ] Industrial FII and MU full offline acceptance: resolution, mapping, ingest, payload, price, query, document, snapshot, as-of, tool, lineage, idempotency, manifest.

## 17. Reflection and acceptance

- [ ] Round 1 reviews financial-data time/unit/revision semantics, platform schema/idempotency/storage, Tool/MCP boundary, security, and reliability/testing.
- [ ] Fix every CRITICAL/HIGH finding through a failing test before Round 2.
- [ ] Round 2 executes all 30 prompt checks against code/tests/docs and records evidence.
- [ ] Acceptance requires zero unresolved CRITICAL/HIGH, all offline/provider/snapshot/tool/PostgreSQL gates green, and honest Live BLOCKED status.
- [ ] Expected conclusion is `CONDITIONAL GO` while live credentials/entitlements remain blocked; do not default to GO.

## 18. Rollback

- [ ] Code rollback reverts only Stage 4 commits on the feature branch; never reset user work.
- [ ] Database rollback backs up non-fixture data and runs `uv run alembic downgrade 0002_create_security_master` against an explicitly confirmed non-production URL.
- [ ] Local BlobStorage rollback removes only keys recorded by the selected fixture ingestion after resolving and validating they remain under the configured Stage 4 blob root.
- [ ] Re-upgrade uses `uv run alembic upgrade head`; no migration deletes Stage 3 master data.

---

## 19. Task-by-task TDD execution

### Task 1: Domain contracts and provider registry

**Files:**
- Create: `src/stock_research_agent/domain/data_access/{__init__,enums,schemas,repositories}.py`
- Create: `src/stock_research_agent/providers/{__init__,base,capabilities,registry,errors}.py`
- Test: `tests/unit/test_provider_registry.py`
- Test: `tests/unit/test_data_access_schemas.py`

**Interfaces:**
- Produces: `ProviderCapability`, `DataCategory`, `QualityStatus`, `ProviderRequest`, `ProviderEnvelope`, `DataProviderAdapter`, `ProviderRegistry`, and repository Protocols.
- Consumes: aware UTC clock/UUID/Pydantic conventions already used by Stage 3.

- [ ] Write failing tests that register one provider, reject duplicate code, enforce capabilities/status/credentials, validate aware `as_of`, reject floats for Decimal fields, and prove import performs no I/O.
- [ ] Run `uv run pytest tests/unit/test_provider_registry.py tests/unit/test_data_access_schemas.py -v` and confirm failures are missing-module/contract failures.
- [ ] Implement the minimum strict enums/schemas/protocols/registry. The registry stores adapters but never invokes them during registration/list/describe.
- [ ] Rerun the focused tests and existing module-boundary tests; refactor only after green.

Expected provider protocol shape:

```python
class DataProviderAdapter(Protocol):
    code: str
    version: str
    capabilities: frozenset[ProviderCapability]

    def fetch(self, request: ProviderRequest) -> ProviderEnvelope: ...
```

### Task 2: Safe HTTP, cache, and rate limiter

**Files:**
- Create: `src/stock_research_agent/providers/{http_client,cache,rate_limit}.py`
- Modify: `src/stock_research_agent/config.py`
- Modify: `.env.example`
- Test: `tests/unit/test_provider_http_client.py`
- Test: `tests/unit/test_provider_rate_limit.py`

**Interfaces:**
- Produces: `SafeHttpClient.get(HttpRequest) -> HttpResult`, `ResponseCache`, `RateLimiter`.
- Consumes: fixed provider allowlist/config, never a CLI/API caller URL.

- [ ] Write one failing behavior test at a time for offline refusal, HTTPS/host/port/IP validation, redirect revalidation, TLS, timeout, 404 no-retry, 429/5xx retry, bounded Retry-After, response size, ETag/Last-Modified/304, User-Agent, and URL/header/query redaction.
- [ ] Run each targeted test and observe the expected policy/retry failure before implementation.
- [ ] Implement a single injected `httpx.Client` boundary, in-memory metadata cache, and monotonic low-frequency limiter; no provider may instantiate `httpx` directly.
- [ ] Rerun the focused suite and `uv run ruff check` on touched files after green.

Safe URL output must preserve scheme/host/path while replacing sensitive query values with `***`; Authorization/Cookie values never enter result/log schemas.

### Task 3: BlobStorage

**Files:**
- Create: `src/stock_research_agent/infrastructure/blob_storage.py`
- Test: `tests/unit/test_blob_storage.py`

**Interfaces:**
- Produces: `BlobStorage.put/get/exists/delete/checksum/metadata`, `LocalBlobStorage`, `InMemoryBlobStorage`.
- Returns: opaque `blob://local/<generated-key>` or `blob://memory/<generated-key>` URIs.

- [ ] Write failing tests for round-trip, deterministic SHA-256, metadata, generated keys, no overwrite, traversal/absolute-path rejection, bounded size, and no local absolute-path output.
- [ ] Run the file and confirm missing interface failures.
- [ ] Implement system-generated keys and containment checks using resolved paths under the configured root; unit tests use only temporary/in-memory storage.
- [ ] Rerun focused tests and keep deletion unregistered from tools.

### Task 4: SQLAlchemy models and migration 0003

**Files:**
- Create: `src/stock_research_agent/db/models/data_access.py`
- Modify: `src/stock_research_agent/db/models/__init__.py`
- Create: `migrations/versions/0003_create_data_access_and_snapshots.py`
- Test: `tests/unit/test_data_access_models.py`
- Test: `tests/integration/test_data_access_migrations.py`

**Interfaces:**
- Produces the eleven tables and named constraints/indexes in Sections 6–8.
- Consumes Stage 3 `securities.id` through restrictive foreign keys.

- [ ] Write metadata tests first for every table, FK delete policy, unique/CHECK/index name, NUMERIC type, and absence of native ENUM/float.
- [ ] Run unit metadata tests and confirm tables are missing.
- [ ] Implement SQLAlchemy 2 annotated models and make model registry import them.
- [ ] Run metadata tests green, then write real PostgreSQL migration-cycle/catalog tests and observe revision/table failures.
- [ ] Implement reversible schema-only revision `0003`; run isolated targeted migration tests green.

### Task 5: PostgreSQL repository and query ports

**Files:**
- Create: `src/stock_research_agent/db/repositories/data_access.py`
- Modify: `src/stock_research_agent/db/repositories/__init__.py`
- Create: `src/stock_research_agent/domain/data_access/queries.py`
- Test: `tests/integration/test_data_access_repository_postgres.py`
- Test: `tests/unit/test_data_access_queries.py`

**Interfaces:**
- Produces explicit provider/mapping/run/request/payload/record/snapshot write methods and bounded read methods.
- Query service produces provider lists, latest close/history/actions/facts/documents/snapshot DTOs without raw payload bodies or storage paths.

- [ ] Write failing PostgreSQL tests for restrictive FKs, uniqueness/CHECKs, transaction rollback, exact Decimal, revision coexistence, idempotent natural keys, bounded/stable query ordering, and session closure.
- [ ] Run tests and confirm repository methods are absent.
- [ ] Implement parameterized SQLAlchemy methods; write methods never commit, read methods never mutate/flush.
- [ ] Rerun PostgreSQL tests, then add pure query-service tests proving status/warning/quality and Decimal string serialization.

### Task 6: Verified fixture package and provider contract

**Files:**
- Create: `src/stock_research_agent/providers/fixtures/provider.py`
- Create: `src/stock_research_agent/providers/fixtures/data/601138_sse_stage1.json`
- Create: `src/stock_research_agent/providers/fixtures/data/601138_sse_stage1.manifest.json`
- Create: `src/stock_research_agent/providers/fixtures/data/mu_nasdaq_stage1.json`
- Create: `src/stock_research_agent/providers/fixtures/data/mu_nasdaq_stage1.manifest.json`
- Create: `src/stock_research_agent/providers/fixtures/data/mu_sec_stage1.json`
- Create: `src/stock_research_agent/providers/fixtures/data/mu_sec_stage1.manifest.json`
- Create: `docs/fixture-sources.md`
- Test: `tests/contract/test_fixture_provider_contract.py`
- Test: `tests/unit/test_fixture_manifests.py`

**Interfaces:**
- Produces only records explicitly present in `docs/sample-data-validation/601138.SH.md`, `docs/sample-data-validation/MU.md`, and Stage 1 request evidence.
- Every envelope includes fixture-mode markers and never opens a socket.

- [ ] Write failing manifest tests for all mandatory fields, SHA-256 match, crop rules, null unknown publication time, use restrictions, and the three fixture markers.
- [ ] Run tests and confirm resources are absent.
- [ ] Add exact Stage 1-preserved fields only: one validated daily row per security and validated filing metadata; facts/actions remain empty with explicit warnings where no value/event evidence was preserved.
- [ ] Implement resource loading/checksum verification and typed fixture adapter outputs; rerun tests green.
- [ ] Add provider capability contract tests for prices, empty-PARTIAL facts, filing metadata, as-of exclusion, provenance, Decimal, and no future record.

### Task 7: Ingestion service and idempotency

**Files:**
- Create: `src/stock_research_agent/domain/data_access/ingestion.py`
- Test: `tests/unit/test_ingestion_service.py`
- Test: `tests/integration/test_ingestion_postgres.py`

**Interfaces:**
- Consumes: repository protocol, provider registry, BlobStorage, `IngestionRequest`.
- Produces: persisted run/request/payload/raw records plus `IngestionResult`.

- [ ] Write failing service tests for mapping/capability/policy checks, idempotency-key stability, fixture markers, PASS/PARTIAL/BLOCKED/FAIL mapping, safe error codes, no overwrite, and no Session creation.
- [ ] Verify failures, implement deterministic SHA-256 idempotency and category transaction boundaries, and rerun green.
- [ ] Write PostgreSQL tests for first/repeated ingestion, concurrent uniqueness, rollback, correction payload coexistence, request lineage, and raw immutability; implement minimum repository coordination and rerun.

### Task 8: Snapshot builder

**Files:**
- Create: `src/stock_research_agent/domain/data_access/snapshots.py`
- Test: `tests/unit/test_snapshot_builder.py`
- Test: `tests/integration/test_snapshot_postgres.py`

**Interfaces:**
- Consumes: repository point-in-time candidates plus security/cutoff/categories/provider preference/version.
- Produces: immutable `DataSnapshotRecord`, ordered SnapshotItems, deterministic content checksum.

- [ ] Write failing unit tests for aware UTC cutoff, known-future exclusion, exchange-local trading date, unknown publication warning, PARTIAL/COMPLETE/FAILED transitions, stable checksum/order, and same-input replay.
- [ ] Run and observe missing builder failures; implement pure selection/checksum logic and rerun.
- [ ] Write PostgreSQL tests for row locking, immutable completed snapshot/item rejection, new data/new snapshot, no fake COMPLETE, protected delete, and both sample snapshot builds.
- [ ] Implement minimum repository transaction coordination and rerun focused integration tests.

### Task 9: Read-only tool schemas, registry, and eight tools

**Files:**
- Create/modify: `src/stock_research_agent/tools/{__init__,permissions,schemas,registry,market_data,financial_data,documents,snapshots}.py`
- Test: `tests/unit/test_tool_registry.py`
- Test: `tests/unit/test_read_only_tools.py`

**Interfaces:**
- Consumes: `DataAccessQueryService` only.
- Produces: eight `1.0.0` registrations and strict `ToolEnvelope[T]` outputs.

- [ ] Write failing registry tests for stable metadata, duplicate name/version, JSON schemas, permissions, network/write flags, list/describe without execution, and forbidden write registrations.
- [ ] Implement registry/permissions/schema minimum and rerun green.
- [ ] Write failing tests for all eight tools: snapshot/as-of validation, no refresh/write/download, Decimal strings, PARTIAL/BLOCKED, bounded data, source IDs, warnings, and no raw/secret/path fields.
- [ ] Implement thin read-only adapters over the query service and rerun focused tests.

### Task 10: Read-only API

**Files:**
- Create: `src/stock_research_agent/api/routes/data.py`
- Create: `src/stock_research_agent/api/routes/snapshots.py`
- Modify: `src/stock_research_agent/api/dependencies.py`
- Modify: `src/stock_research_agent/api/router.py`
- Test: `tests/contract/test_data_api_contract.py`

**Interfaces:**
- Consumes: request-scoped Session -> SQLAlchemy repository -> shared query service.
- Produces: the eight GET routes in Section 13 and existing uniform errors/request IDs.

- [ ] Write failing contracts for providers/latest/history/actions/facts/documents/snapshot/items, 404/422/503, max span/page, PARTIAL/BLOCKED, stable schemas, request ID, OpenAPI, and no SQL/token/storage/raw leak.
- [ ] Run and confirm route failures.
- [ ] Implement only GET routes with fixed ordering and strict query constraints; no endpoint commits or exposes ingestion/build/download.
- [ ] Rerun contract tests and existing health/security API contracts.

### Task 11: CLI write/read boundaries

**Files:**
- Create: `src/stock_research_agent/cli_data.py`
- Create: `src/stock_research_agent/cli_tools.py`
- Modify: `src/stock_research_agent/cli.py`
- Test: `tests/integration/test_data_cli.py`
- Test: `tests/unit/test_cli_data.py`

**Interfaces:**
- Consumes: existing settings/session/resolution composition; ingestion/snapshot writes explicitly commit.
- Produces: commands in Section 13 with human/JSON output and distinct exit codes.

- [ ] Write failing help/composition tests proving no duplicated provider/tool logic and no import-time I/O.
- [ ] Implement Typer groups and renderers, then run unit CLI tests green.
- [ ] Write subprocess PostgreSQL tests for provider/mapping list, first/repeat fixture ingest, BLOCKED live attempt, snapshot create/show, price/facts/docs queries, tools list/describe, JSON/human markers, exits, and no secret/path output.
- [ ] Implement explicit transaction ownership and rerun focused integration tests.

### Task 12: Default-offline and explicit Live harness

**Files:**
- Modify: `tests/conftest.py`
- Create: `tests/unit/test_default_network_policy.py`
- Create: `live_tests/test_provider_smoke.py`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/backend-ci.yml`

**Interfaces:**
- Default pytest denies non-loopback sockets; live suite is outside default `testpaths` and requires explicit environment/config.

- [x] Add explicit external DNS/IP policy tests. The loopback-only guard had already
  landed as a Task 6 review fix, so Task 12 verified that behavior instead of
  fabricating a second RED for an already-closed gap.
- [x] Keep the loopback-only autouse network guard and force the default CI provider
  policy offline; all 188 explicitly selected PostgreSQL integration/contract tests
  passed over loopback.
- [x] Add explicit live test metadata/result schema; absent flags/config produce
  recorded `BLOCKED` results only when `live_tests` is explicitly invoked.
- [x] Prove `uv run pytest --collect-only` does not collect `live_tests`, and CI
  contains no live-provider invocation.

### Task 13: Documentation, fixture/source manifest, and operational examples

**Files:**
- Create: `docs/{data-providers,data-ingestion,data-snapshots,tool-contracts,raw-data-model}.md`
- Modify: `README.md`, `AGENTS.md`, `docs/{api,database,testing,security-boundaries,risk-register,open-questions}.md`
- Test: `tests/unit/test_stage4_documentation.py`

**Interfaces:**
- Documents actual commands/schemas/statuses only; updates stale AGENTS Stage 2 boundary to the approved Stage 4 boundary.

- [x] Write failing documentation tests for required files/headings/commands, fixture
  markers, blocked live sources, no Stage 5 claims, and CLI command parity.
- [x] Update docs with Provider selection/capabilities/mappings,
  payload/blob/as-of/snapshot/tool/fixture-vs-live/license/current limitations and
  explicit no-metric/RAG/Agent/MCP/trading boundaries.
- [x] Rerun documentation tests and manually execute every Stage 4 documented command
  against the isolated PostgreSQL test environment with per-command exit checks.

### Task 14: PostgreSQL and two-sample acceptance

**Files:**
- Create: `tests/integration/test_stage4_sample_snapshots.py`
- Create: `tests/contract/test_provider_capability_contracts.py`

**Interfaces:**
- Proves both stable Stage 3 security IDs traverse mapping -> ingest -> payload -> raw records -> snapshot -> read tool -> lineage.

- [x] Add Industrial FII acceptance through resolution, mapping, idempotent fixture
  ingestion, one verified price, snapshot cutoff, Tool read, lineage and manifest
  checksum.
- [x] Run the acceptance tests and correct only test assembly defects; no production
  behavior change was required because Tasks 6–11 already satisfied the path.
- [x] Repeat the acceptance for Micron with Nasdaq price, SEC filing metadata and
  empty-PARTIAL financial facts.
- [x] Add explicit future-date exclusion, unknown-publication warnings,
  no-corporate-action, provider-revision and duplicate-ingestion counterexamples.

### Task 15: Reflection Round 1 and fixes

**Files:**
- Create: `docs/reflection/stage-4-round-1.md`
- Modify only files named by validated findings.
- Test: targeted regression tests per finding.

- [x] Review the five required roles and record
  ID/role/severity/description/evidence/files/fix/blocking/status for every finding.
- [x] For the one HIGH finding, write and observe a failing PostgreSQL regression,
  implement the minimum durable-BlobStorage fix, rerun focused/related suites, and
  mark it FIXED with byte-for-byte runtime evidence.
- [x] Do not close a finding on documentation assertion alone when runtime proof is
  possible; Round 1 has zero unresolved CRITICAL/HIGH findings.

### Task 16: Reflection Round 2, migration replay, full gates, and report

**Files:**
- Create: `docs/reflection/stage-4-round-2.md`
- Create: `docs/stage-4-implementation-report.md`
- Modify: this plan's checkboxes/evidence as tasks pass.

- [x] Execute all 30 Round 2 checks with code/test/command evidence and fix every new CRITICAL/HIGH through TDD.
- [x] Run development and isolated-test migration cycles and finish both at `0003_data_access_snapshots (head)`.
- [x] Run `uv sync`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, and `uv run pytest -W error`; exact final result: 970 passed, zero warnings/skips.
- [x] Re-run both fixture ingestions twice, build both snapshots twice, execute all eight Tool contracts, API/OpenAPI smokes, and CLI smokes; exact replay IDs/checksums are in the report.
- [x] Record Live Tushare/U.S. EOD/SEC Archive as BLOCKED; explicit suite performed no HTTP request.
- [x] Write the 48-section report, use `CONDITIONAL GO`, and do not enter Stage 5.

---

## 20. Plan self-review

### Required boundary coverage

- [x] Provider: Sections 4–7 and Tasks 1, 6, 7, 14.
- [x] HTTP: Global constraints and Task 2.
- [x] RawPayload: Sections 6, 7, 9 and Tasks 4, 5, 7.
- [x] BlobStorage: Sections 5, 9 and Task 3.
- [x] IngestionRun: Sections 6–7 and Tasks 4, 5, 7.
- [x] as-of: Sections 10–11 and Tasks 6, 8, 14.
- [x] Snapshot: Sections 6, 7, 11 and Tasks 8, 14, 16.
- [x] Tool permissions: Section 12 and Task 9.
- [x] API read-only: Section 13 and Task 10.
- [x] CLI writes: Section 13 and Task 11.
- [x] fixture/Live isolation: Sections 4, 14 and Tasks 6, 12, 16.
- [x] Security: Global constraints, Tasks 2, 3, 9, 10, 11, 12.
- [x] Tests: Section 16 and every RED/GREEN task.
- [x] Reflection: Section 17 and Tasks 15–16.

### Prompt/additional-requirement consistency

- [x] Both required securities have honest immutable PARTIAL snapshot acceptance paths.
- [x] Formal fixture manifests contain every user-required field and verified checksum.
- [x] Unknown financial values remain absent; no zero/empty/estimate substitution exists.
- [x] Known future data is excluded; unknown publication time warns and prevents COMPLETE.
- [x] Raw evidence is immutable and provider corrections preserve history.
- [x] Registered tools and HTTP API are read-only and cannot trigger writes.
- [x] Live validation cannot enter default pytest/CI or be fabricated to obtain GO.
- [x] All eleven required tables, downgrade, indexes, constraints, and real PostgreSQL proof are assigned.
- [x] No plan task implements Stage 5 functionality or any prohibited model/RAG/Agent/MCP/trading behavior.
- [x] No unresolved placeholder, unowned requirement, conflicting type name, or unexplained implementation gap remains.

## 21. Acceptance evidence to capture

- [x] Exact provider codes/statuses/capabilities and credential/terms state.
- [x] Fixture file/manifest SHA-256 results and three offline markers.
- [x] Raw payload checksums, ingestion idempotency counts, and revision behavior.
- [x] Both snapshot IDs/content checksums/status/warnings and replay equality.
- [x] Eight tool registry entries and representative PARTIAL envelopes.
- [x] API/OpenAPI/CLI outputs, safe errors, request IDs, exit codes, and no-leak checks.
- [x] Development/test migration histories and final heads.
- [x] Ruff/format/mypy/pytest exact results and zero-warning evidence.
- [x] Reflection findings/fixes and unresolved CRITICAL/HIGH counts.
- [x] Separate offline/provider/snapshot/tool outcomes and Live BLOCKED inventory.

## 22. Stage conclusion policy

- [ ] `GO` only if every acceptance item, including required live authorization/data, actually passes.
- [x] `CONDITIONAL GO` applies: core offline architecture, provider contracts, snapshots, tools, API/CLI, PostgreSQL, migrations, tests, and Reflections pass while enumerated live providers remain credential/license/contact BLOCKED.
- [ ] `NO-GO` when a core offline, snapshot, lineage, security, tool, migration, or unresolved CRITICAL/HIGH requirement fails.

## 23. Final branch handling

- [ ] Inspect `git status --short`, `git diff --check`, and changed paths before staging.
- [ ] Stage only Stage 4 files; do not use an unchecked blanket `git add .`.
- [ ] Suggested final implementation commit: `feat: add point-in-time data access and read-only tools`.
- [ ] Keep `stage-4/data-access-tools` unmerged and offer exactly the four requested finishing options.
- [ ] Wait for the user's choice and do not begin Stage 5.
