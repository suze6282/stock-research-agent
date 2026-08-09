# Stage 4 data ingestion

Ingestion is an explicit CLI/internal-service write workflow. It resolves the
security through the Stage 3 deterministic resolver, selects an exact active
`ProviderInstrumentMapping`, checks Provider capability/status/terms, fetches an
approved adapter envelope, verifies fixture provenance, and persists one
`IngestionRun`, request lineage, immutable `RawPayload`, and typed raw records in a
caller-owned transaction. Provider, HTTP, BlobStorage, domain, and PostgreSQL layers
remain dependency-injected and independently testable.

## Commands

The only implemented data source is an approved offline fixture:

```powershell
uv run stock-research data ingest "601138.SH" --category DAILY_PRICES --as-of 2026-12-31T00:00:00Z --fixture
uv run stock-research data ingest "MU" --category DAILY_PRICES --as-of 2026-12-31T00:00:00Z --fixture
uv run stock-research data ingest "MU" --category FILING_METADATA --as-of 2026-12-31T00:00:00Z --fixture
uv run stock-research data ingest "MU" --category FINANCIAL_FACTS --as-of 2026-12-31T00:00:00Z --fixture --json
```

Outputs say `FIXTURE | OFFLINE | NOT_LIVE`. Omitting `--fixture` is an explicit Live
attempt and returns `BLOCKED`; it does not silently fall back, open a socket, or
claim success.

## Idempotency and evidence

The idempotency key is a deterministic SHA-256 over the security, Provider,
category, UTC `research_as_of_time`, adapter version and request identity. Repeating
the same accepted request returns the existing run and does not duplicate payloads
or raw records. A provider correction is preserved as new evidence; it does not
overwrite the prior payload. `RawPayload` retains exact original bytes or immutable
JSON plus checksum and lineage. Parsed/normalized output never replaces it.

Known `source_published_at` later than `research_as_of_time` is excluded. Unknown
publication time remains null, creates `SOURCE_PUBLISHED_AT_UNKNOWN`, and produces
`PARTIAL`; `retrieved_at` is never substituted. Missing financial fields remain
absent—never zero, empty text, or estimates.

`INTERNAL_WRITE` commands own commit/rollback. API and Tools are `READ_ONLY` and
cannot refresh, ingest, download, or rebuild snapshots. No 财务标准化, TTM, 财务指标,
估值, RAG, Agent, MCP, 自动交易, or Stage 5 behavior is implemented; 不得进入第5阶段.
# Stage 9 governed ingestion

Every intent binds immutable Provider, Capability, Policy and License versions,
an exact Security or bounded universe, `research_as_of_time`, date range and hard
budgets. `OFFLINE` execution may consume only source-attributed fixtures marked
`OFFLINE` and `NOT_LIVE`; it cannot silently select a production transport.

Repository methods use a caller-owned transaction. Artifact acceptance, manifest,
bridge write and Checkpoint advancement are designed to share that transaction;
a failed transaction does not advance the Checkpoint. Stable source identities and
checksums make replay idempotent. A new upstream revision creates new immutable
evidence; it never overwrites an older revision. Records published after
`research_as_of_time` are excluded, and unknown publication time remains warned.

Ingestion does not create a Snapshot, run an Agent, generate a report, or start
Stage 10. Those require later explicit workflows and authorization.
