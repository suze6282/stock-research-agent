# Stage 4 Implementation Report

## 1. Stage conclusion

**CONDITIONAL GO.** Offline fixture capability, Provider contracts, durable raw
evidence, immutable as-of snapshots, read-only Tools/API/CLI, migrations and all
quality gates pass. Live Tushare, licensed U.S. EOD and SEC Archive remain honestly
`BLOCKED` by credentials, entitlement or contact configuration.

## 2. Current branch

`stage-4/data-access-tools`; it is not merged into `main`.

## 3. Implemented scope

Offline-first ports/adapters, Provider catalog/capabilities/mappings, safe HTTP,
rate limit/cache, IngestionRun/request log, immutable RawPayload and BlobStorage,
raw daily/action/fact/document models, deterministic snapshots, eight read-only
Tools, eight GET routes, CLI read/write boundaries, fixtures, tests and operations
documentation.

## 4. Unimplemented scope

No Live adapter qualification, financial standardization, TTM, metric calculation,
valuation, document-body parsing, RAG, model call, Agent, Reflection runtime, MCP
Server, frontend, broker integration or trading.

## 5. Provider inventory

Implemented offline adapters: `STAGE1_SSE_FIXTURE`, `STAGE1_NASDAQ_FIXTURE`,
`STAGE1_SEC_FIXTURE`. Declared but unavailable targets include `TUSHARE_PRO`, a
named licensed U.S. EOD provider, and `SEC_ARCHIVES`.

## 6. Provider status

SSE/Nasdaq fixture evidence is `EXPERIMENTAL`; SEC fixture evidence is
`APPROVED_FOR_PERSONAL_RESEARCH_ONLY`. Every fixture response is `FIXTURE`,
`OFFLINE`, `NOT_LIVE`. All three Live targets are `BLOCKED`.

## 7. Provider capabilities

SSE crop: one daily-price row. Nasdaq crop: one daily-price row. SEC crop: three
filing metadata records and an intentionally empty financial-facts result. No sample
contains supported corporate actions or normalized facts.

## 8. Credential status

No credential is stored. Tushare token, licensed U.S. EOD key/provider selection,
and SEC contact/User-Agent are absent.

## 9. Authorization status

Fixture use is restricted to the manifest's personal offline research terms.
Caching, redistribution, commercial display, SLA and production API rights are not
claimed. Live use remains unqualified.

## 10. Data model

Eleven Stage 4 tables: `data_providers`, `provider_instrument_mappings`,
`ingestion_runs`, `provider_request_logs`, `raw_payloads`, `daily_price_bars`,
`corporate_actions`, `provider_financial_facts`, `source_documents`,
`data_snapshots`, `snapshot_items`.

## 11. Tables and relationships

Stage 3 `Security` binds to Provider mappings, ingestion runs/raw records and
snapshots. Raw records point to immutable payload/provider/security lineage.
Snapshots own bounded immutable items that reference source record IDs and providers.
All ownership foreign keys are restrictive; there is no destructive cascade.

## 12. Constraints

Named PostgreSQL CHECK/UNIQUE/FK constraints enforce controlled status/category
strings, valid URLs/timestamps/date ranges, nonnegative sizes/values, OHLC validity,
SHA-256 formats, idempotency keys, inline-versus-blob shape, unique raw natural keys,
snapshot version/status/checksum rules and unique snapshot items. Amounts use NUMERIC,
not float or native ENUM.

## 13. Indexes and purpose

- Provider/mapping identity indexes support deterministic security-to-source lookup.
- Ingestion security/category/as-of and request-run indexes support bounded lineage.
- Payload checksum and security/category/source-time indexes support reconciliation/as-of.
- Daily security/date and provider/symbol/date indexes support latest/history reads.
- Action security/ex-date, fact security/period/filed, and document security/published
  indexes support bounded raw queries.
- Snapshot security/as-of and item snapshot/category indexes support replay/read Tools.

## 14. HTTP client policy

One injected `httpx.Client` boundary enforces HTTPS, host allowlists, public DNS/IP,
port rules, TLS, redirect revalidation, response/MIME bounds, cookie refusal, safe URL
rendering and secret-safe errors. Provider/Repository/Tool/API code cannot bypass it.

## 15. Timeouts and retry

Defaults: connect 5s, read/write 15s, total 30s, maximum three attempts, retry base
delay 0.25s, maximum three redirects and 5 MiB body. Only 429 and selected transient
5xx/network errors retry; 404 does not. Retry-After is bounded.

## 16. Rate limiting

The injected monotonic limiter defaults to one request per second per host. Default
offline mode refuses network before any request.

## 17. Domain allowlist

Adapters own fixed HTTPS origins. The client rejects caller-chosen hosts, credentials
in URLs, IP literals, private/loopback/link-local resolutions, unexpected ports and
cross-origin or invalid redirects.

## 18. RawPayload strategy

Exact fixture bytes are checked against manifest SHA-256, persisted with provider/run/
request/security/category/version/timestamp lineage and never overwritten by parsing
or revisions. Raw bytes and normalized records remain separate.

## 19. BlobStorage strategy

Small JSON may use JSONB; opaque bytes use durable `LocalBlobStorage` below an absolute
configured root and return only `blob://local/...`. Traversal, absolute caller paths,
overwrite, symlink/reparse/hardlink attacks and oversized blobs are rejected.

## 20. as-of semantics

Known `source_published_at` after the aware UTC cutoff is excluded. Unknown publication
time is never replaced by retrieval time; it yields warnings and prevents COMPLETE.
Trading date remains exchange-local, and reporting/filed/retrieved times stay distinct.

## 21. Snapshot design

Snapshot items are deterministically sorted and SHA-256 checksummed. Same security,
cutoff, categories and evidence replay the same snapshot/checksum. Terminal COMPLETE
or PARTIAL rows/items are protected in repository logic and PostgreSQL triggers; changed
evidence creates a new version.

## 22. Tool inventory

`get_latest_close`, `get_daily_price_history`, `get_corporate_actions`,
`get_reported_financial_facts`, `list_source_documents`,
`get_source_document_metadata`, `get_data_snapshot`, `list_snapshot_items` — all v1.0.0.

## 23. Tool permissions

All eight are `READ_ONLY`, `writes=false`, `requires_network=false`. Ingestion,
refresh, download, snapshot build, delete, arbitrary URL/SQL and credential mutation
are not registered. Empty snapshot categories retain snapshot fixture provenance.

## 24. API

Eight bounded GET routes cover Provider catalog, latest/history/actions/facts/documents,
snapshot and snapshot items under `/api/v1`. They reuse request IDs and safe errors,
never commit, refresh, download or build snapshots. OpenAPI and 29 data contracts pass.

## 25. CLI

`data providers|mappings|ingest|latest-close|price-history|financial-facts|documents|
snapshot` plus `tools list|describe`. Only explicit fixture ingest and snapshot create
write; reads use the same query service/Tool Registry as API. PARTIAL exits distinctly.

## 26. Industrial FII sample result

`601138.SH` resolved to stable security `40000000-0000-0000-0000-000000000001`.
Final snapshot `e56f0ebe-d2dd-41ff-bc0c-336bc8f114d0` is PARTIAL with one item and
checksum `4d96ad2f92daddac01f0331b805dd0484c49f0458d88a291423285cff42aecec`.
Replay returned the identical ID/checksum. The evidence-only 2026-07-10 close is
66.27 CNY and is explicitly NOT_LIVE; publication time is unknown.

## 27. Micron sample result

`MU` resolved to stable security `40000000-0000-0000-0000-000000000002`. Final
snapshot `41860194-bf16-44e0-87b7-446c68805839` is PARTIAL with four items and
checksum `4028976d39e66d0149e64c977fca66e0f954365fd71bc6009eb9d33999bceb3`.
Replay returned the identical ID/checksum. It contains one evidence-only daily row
and three SEC filing metadata rows; no financial number was invented.

## 28. Fixture result

PASS for offline contracts, manifest fields/checksums, provenance, ingestion,
idempotency, lineage, as-of, snapshots, Tools/API/CLI and durable raw-byte reopening.
All outputs state FIXTURE/OFFLINE/NOT_LIVE where fixture provenance is known.

## 29. Live Smoke Test result

Explicit separate run: three explained skips, each structured `BLOCKED`, HTTP
`NOT_ATTEMPTED`, no RawPayload and no snapshot. This suite is outside default pytest/CI.

## 30. BLOCKED items

`TUSHARE_PRO`, `LICENSED_US_EOD`, and `SEC_ARCHIVES` Live validation. No fake Live
success is used in this conclusion.

## 31. Authorization confirmations pending

Tushare token/cache terms; named U.S. EOD vendor/key/license/display/cache rights;
SEC real contact and compliant User-Agent; website crop production/cache/redistribution
rights.

## 32. Migration upgrade and rollback result

Development: `upgrade head -> downgrade -1 -> upgrade head`, exit 0, final
`0003_data_access_snapshots (head)`. Isolated test DB: `base -> 0001 -> 0002 -> 0003
-> downgrade -1 -> upgrade head`, exit 0, same final head.

## 33. PostgreSQL integration result

PASS on real project PostgreSQL 17 loopback databases for schema catalog, constraints,
transactions, rollback, concurrency, idempotency, raw immutability, terminal snapshot
triggers, sample replay and test isolation. SQLite was not used as evidence.

## 34. Ruff result

`uv run ruff check .`: `All checks passed!`, exit 0.

## 35. Format-check result

`uv run ruff format --check .`: `129 files already formatted`, exit 0.

## 36. mypy result

`uv run mypy src`: `Success: no issues found in 73 source files`, exit 0.

## 37. Actual pytest count and result

`uv run pytest -W error`: `970 passed in 150.92s`, exit 0, zero warnings and zero
default skips. Default collection excludes the separate Live suite.

## 38. Reflection Round 1

One HIGH durable-blob defect was fixed (`146a123`). Open non-blocking items: MEDIUM
orphan local blob after rare outer commit failure; LOW lack of an exhaustive dedicated
security-diff scan. Unresolved CRITICAL/HIGH: zero.

## 39. Reflection Round 2

All 30 checks pass. Fixed MEDIUM environment-contract omission (`db31719`) and HIGH
empty-category fixture-provenance loss (`5adfb2f`) through observed failing tests.
Unresolved CRITICAL/HIGH: zero.

## 40. Fixed issues

Durable CLI RawPayload storage; BlobStorage configuration contract; empty snapshot
category provenance; earlier HTTP/Tool/API/CLI hardening findings recorded in branch
history and both Reflection reports.

## 41. Unresolved issues

Non-blocking: add blob outbox/garbage collection before Live payload volume; run a
dedicated exhaustive security diff scan before production/Live enablement; acquire
and validate Live credentials/licenses/contact. Empty facts remain correctly absent.

## 42. CRITICAL/HIGH risk

Unresolved `CRITICAL=0`, `HIGH=0`. Live data availability is a declared BLOCKED
external prerequisite, not a fabricated pass.

## 43. Current limitations

Only three Stage 1-derived safe crops and two securities; no licensed Live prices,
corporate actions, numeric financial facts, body downloads, calendar, normalization,
metrics, RAG, model/Agent/MCP or trading. Snapshot contents remain PARTIAL.

## 44. Rollback method

Revert Stage 4 commits only after checking user work. For schema rollback, back up
non-fixture data and run `uv run alembic downgrade 0002_create_security_master` against
an explicitly confirmed non-production URL. Remove blobs only from recorded fixture
keys after verifying containment below the configured root.

## 45. Git status

Feature branch only; no merge/rebase/force operation. Immediately before creating
this report the worktree was clean. Final handoff requires and verifies an empty
`git status --short` after the report commit.

## 46. Whether Stage 5 entry conditions are met

Only conditionally: the offline foundation is technically ready, but Live-dependent
work remains blocked and Stage 5 is not authorized by this report. Do not enter it
without an explicit user instruction defining its scope.

## 47. Stage 5 allowed scope

None is self-authorized. A future explicit Stage 5 prompt may consume immutable
snapshot IDs and raw fact/document metadata through existing read-only contracts,
while respecting the declared Live blockers and provenance.

## 48. Stage 5 forbidden scope

Until separately authorized: all Stage 5 implementation. Stage 4 also continues to
forbid invented/live-labelled fixture data, implicit refresh from reads, financial
normalization/TTM/metrics/valuation, RAG/model/Agent/MCP, broker access and trading.
