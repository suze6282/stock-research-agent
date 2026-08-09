# Stage 4–5 read-only Tool contracts

The canonical registry exposes exactly eight version `1.0.0` Tools:

1. `get_latest_close`
2. `get_daily_price_history`
3. `get_corporate_actions`
4. `get_reported_financial_facts`
5. `list_source_documents`
6. `get_source_document_metadata`
7. `get_data_snapshot`
8. `list_snapshot_items`

Every registration is `READ_ONLY`, `read_only=true`, `writes=false`, and
`requires_network=false`. Registry list/describe operations only expose bounded
metadata and JSON Schemas; they never execute a Tool. Ingestion, refresh, download,
Snapshot build, mapping mutation, deletion, arbitrary URL/SQL, and DDL are not
registered. Writes remain explicit CLI/internal-service `INTERNAL_WRITE` operations.

## Envelope and point-in-time scope

Tool inputs require strict IDs and either a persisted snapshot or an aware
`research_as_of_time` where supported. Outputs include tool/version/status, bounded
data, stable source IDs, snapshot/as-of/retrieval fields, warnings, quality, and
Provider provenance. Decimal values serialize as strings. There is no invented
confidence score.

Evidence derived only from the approved crops is marked `FIXTURE`, `OFFLINE`, and
`NOT_LIVE`. Mixed or unverified provenance is never collapsed into a fixture or Live
claim. Missing facts remain absent and produce `PARTIAL`; no zero, empty string, or
estimate is inserted. `source_published_at` uncertainty remains a warning.

## Inspection

```powershell
uv run stock-research tools list --json
uv run stock-research tools describe get_latest_close --json
uv run stock-research data latest-close "MU" --as-of 2026-12-31T00:00:00Z --json
```

The HTTP API and CLI read paths compose the same query service and Tool definitions.
Neither can implicitly fetch a Provider or create a Snapshot. Tushare
`TUSHARE_PRO`, licensed U.S. EOD, and `SEC_ARCHIVES` Live remain `BLOCKED`.

## Stage 5 financial tools

The canonical metadata catalog now contains the eight Stage 4 registrations plus six
Stage 5 version `1.0.0` registrations. The financial execution registry is composed
with one `FinancialQueryService` and exposes exactly:

1. `get_normalized_financial_facts`
2. `get_financial_periods`
3. `get_financial_metrics`
4. `get_metric_detail`
5. `get_metric_lineage`
6. `get_calculation_run`

All six are `READ_ONLY`, `writes=false`, and `requires_network=false`. They read only
persisted periods, normalized facts, terminal runs, metrics and lineage. They cannot
seed, normalize, calculate, ingest, refresh, download or rebuild a snapshot. Bounded
strict inputs prevent arbitrary sorting/SQL and all fixture-backed envelopes retain
`FIXTURE/OFFLINE/NOT_LIVE`.

Financial Tool schemas are suitable for a future Agent/MCP adapter, but no Agent,
model call, MCP Server, RAG, narrative conclusion, target price or trading operation
exists. Stage 6 is not authorized by this reusable contract.
# Stage 6 RAG tools

The canonical registry additionally exposes eight version `1.0.0` RAG tools:
`list_document_versions`, `get_document_metadata`, `search_document_chunks`,
`get_document_chunk`, `get_citation`, `verify_citation`, `get_evidence_bundle`, and
`get_retrieval_run`. Every registration is `READ_ONLY`, `writes=false`, and
`requires_network=false`. Search reads only a compatible precomputed Retrieval Run; a miss returns
`RETRIEVAL_RUN_NOT_PRECOMPUTED`. No Tool parses, indexes, embeds, refreshes or downloads.
# Stage 7 Research Agent contracts

The production execution catalog contains the frozen 22 offline read Tools; the
post-Stage-7 query catalog adds eight read-only research audit Tools. Every
entry records exact name/version, input/output schema checksums, domain,
permission=`READ_ONLY`, `writes=false`, and `requires_network=false`.
Research runs bind `tool_catalog_version`; catalog changes prevent incorrect run
reuse. Tools do not assign Claim support and cannot trigger refresh, parsing,
indexing, Embedding, or model calls.
# Stage 9 Provider Tool catalog

Stage 9 adds 10 Provider query Tools: definition, capabilities, health, license,
Sync Run, Checkpoint, raw-artifact metadata, quality issues, dead letters and
readiness. Every Tool is `READ_ONLY`, `writes=false` and
`requires_network=false`, and calls only `ProviderQueryService`.

The stable 50-entry manifest is
`docs/tool-catalog-stage-9-final.json`. Its checksum differs from Stage 8 while the
Stage 8 manifest remains unchanged. New Provider Tools are not automatically added
to an existing Research Policy allowlist, so historical Runs retain their bound
catalog. Tools cannot refresh data, create a Snapshot, run an Agent or generate a
report. Stage 9 is `CONDITIONAL GO`; Tool availability does not authorize Stage 10.
