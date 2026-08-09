# Stage 4 immutable as-of snapshots

A `DataSnapshot` freezes a reproducible set of persisted raw-record references for
one stable Stage 3 security and one aware UTC `research_as_of_time`. A
`SnapshotItem` contains category, Provider, source table/record ID, publication and
retrieval times, and deterministic item material. Snapshot rows do not copy or
rewrite `RawPayload` bodies.

## As-of selection

Known `source_published_at > research_as_of_time` is excluded. A daily bar also
requires its exchange-local trading date to be no later than the cutoff's local
date. `source_published_at` that cannot be confirmed stays null and emits
`SOURCE_PUBLISHED_AT_UNKNOWN`; `retrieved_at` never masquerades as publication time.
That uncertainty forces `PARTIAL`. Missing categories and unsupported evidence also
remain explicit warnings.

## Immutability and checksum

The builder sorts selected items and computes SHA-256 from security, normalized UTC
cutoff, requested categories, snapshot schema version, and stable item descriptors.
The same cutoff and data set therefore produces the same checksum regardless of
query order. Once status is `COMPLETE` or `PARTIAL`, PostgreSQL triggers reject
snapshot update/delete and SnapshotItem insert/update/delete. New evidence creates a
new version; it cannot mutate completed history. `FAILED` has no completion
checksum.

Both required samples have reproducible fixture-backed immutable snapshots:
`601138.SH` and `MU`. They are honestly `PARTIAL`, `FIXTURE`, `OFFLINE`, and
`NOT_LIVE`; this is not Live market data.

## Commands and read boundary

```powershell
uv run stock-research data snapshot create "601138.SH" --as-of 2026-12-31T00:00:00Z --json
uv run stock-research data snapshot create "MU" --as-of 2026-12-31T00:00:00Z --json
uv run stock-research data snapshot show SNAPSHOT_ID --json
```

Snapshot create is an explicit CLI `INTERNAL_WRITE`. The API and registered Tools
are `READ_ONLY`: reading a snapshot never refreshes a Provider, downloads a file, or
rebuilds anything. Stage 4 excludes 财务标准化, TTM, 财务指标, 估值, RAG, Agent, MCP,
and 自动交易, and 不得进入第5阶段.
