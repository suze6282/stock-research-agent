# Stage 4 raw data and lineage model

The Stage 4 schema keeps provider evidence raw and traceable. `DataProvider` declares
source metadata and capabilities. `ProviderInstrumentMapping` connects the stable
Stage 3 security to a Provider identity. `IngestionRun` records lifecycle,
`research_as_of_time`, quality and idempotency. `ProviderRequestLog` stores only a
safe URL and bounded request metadata. `RawPayload` stores exact immutable JSON or an
opaque BlobStorage URI with SHA-256, source/retrieval times and lineage.

Typed child tables are `DailyPriceBar`, `CorporateAction`,
`ProviderFinancialFact`, and `SourceDocument`. They retain Provider-native concepts
and link back to the payload; they do not overwrite it. `DataSnapshot` and
`SnapshotItem` reference selected records at an as-of cutoff.

## Meaning of raw records

A daily price row is one Provider observation for an exchange-local trading date;
prices and volumes use exact Decimal/NUMERIC, not float. Stage 4 does not assert a
canonical adjusted-price series. Corporate actions are stored only when the source
actually supplied an event—an empty result is not an invented “no action” fact.
Provider financial facts preserve raw taxonomy, concept, context, unit, period and
value; there is no 财务标准化, TTM, 财务指标, ratio, or 估值. Source documents contain
metadata and optional opaque storage reference; Stage 4 does not parse bodies, OCR,
or create RAG chunks.

## Publication and missing data

`source_published_at`, filed/published timestamps, `retrieved_at`, period dates and
trading dates are distinct. Known future publication is excluded from an as-of
snapshot. Unknown `source_published_at` remains null, warns, and forces `PARTIAL`;
retrieval time is not substituted. Absent values remain absent, never zero, empty
text, or estimates.

## Storage and deletion

Small JSON may be JSONB; larger/binary bytes use injected BlobStorage and opaque
`blob://` URIs. Keys are generated and traversal is rejected. Foreign keys are
restrictive. Completed snapshots are immutable in PostgreSQL. Fixture records are
`FIXTURE`, `OFFLINE`, `NOT_LIVE`; Live `TUSHARE_PRO`, U.S. EOD and `SEC_ARCHIVES`
are `BLOCKED`.

API and Tools are `READ_ONLY`; only explicit CLI/internal services are
`INTERNAL_WRITE`. Agent, MCP, 自动交易 and Stage 5 are not implemented; 不得进入第5阶段.
# Stage 9 raw artifacts and rights

`provider_raw_artifacts` stores immutable source identity, source checksum,
content type, byte count, acquisition/publication times and synthetic status. Raw
bytes remain in `BlobStorage`; query projections never expose the local blob key or
path. The raw payload is never overwritten by parsing, normalization or a later
Provider response.

Each accepted artifact is tied to Provider/Capability/Run/Attempt and a manifest.
The license policy decides acquisition, raw storage, cache, derived use,
redistribution, retention and deletion duties before bytes are accepted. A denied
or unknown right blocks persistence rather than filling a placeholder. Stage 9 is
`CONDITIONAL GO`; Stage 10 may not reinterpret missing rights.
