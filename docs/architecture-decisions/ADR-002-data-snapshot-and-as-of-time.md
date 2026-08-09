# ADR-002: Data Snapshot and Research Cutoff

- Status: Accepted for V0.1
- Date: 2026-07-11

## Decision

Every research run freezes an immutable `research_as_of_time` with timezone before any source selection. A fact/document is eligible only when its reliable publication/dissemination time is not later than the cutoff. Retrieval after the cutoff is allowed only to obtain material that was already publicly available by the cutoff; provenance records both times.

Every report and calculation carries:

```text
research_as_of_time
data_snapshot_id
source_published_at
retrieved_at
formula_version
prompt_version
model_version
```

The snapshot also records provider, source identifier/accession, source URL/domain, report period, filed/amended time, currency, unit, content checksum, parser version and selection reason. Corrections are new versions; they do not overwrite history.

## Consequences

- Future-data leakage becomes testable.
- “Latest” always means latest eligible at the cutoff, not latest at replay time.
- Providers without publication/version timestamps cannot supply canonical historical facts without a warning or exclusion.
