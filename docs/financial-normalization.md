# Point-in-time financial normalization

Normalization reads only raw Stage 4 facts already bound to an immutable snapshot.
It requires `source_published_at <= research_as_of_time`; missing publication time is
not replaced by retrieval time and yields a warning. A later amendment/restatement is
therefore invisible to an earlier snapshot. Raw payloads and `ProviderFinancialFact`
rows are never overwritten.

The output records original and normalized Decimal values, original and normalized
units, exact scale factor, currency, concept, period, source fact, mapping, versions,
restatement flag and publication time. Unit scaling supports ONE, THOUSAND, MILLION,
BILLION, PER_SHARE, SHARES, PERCENT and RATIO. Unknown or incompatible units block;
there is no binary float, guessed scale, FX conversion, estimated value, zero fill, or
early display rounding.

`PASS` means every eligible input used by the operation met its contract. `PARTIAL`
means useful output exists with explicit warnings. `BLOCKED` means a required source,
mapping, period, unit or currency basis is unavailable. `NULL` is missing/unavailable,
`N/M` is a present but non-meaningful ratio condition, and numeric zero is stored only
when the exact fact or calculation equals zero.

Explicit write commands are:

```powershell
uv run stock-research financials seed-v0
uv run stock-research financials normalize "MU" --snapshot <SNAPSHOT_ID> --json
uv run stock-research financials calculate "MU" --snapshot <SNAPSHOT_ID> --json
```

API and Tool calls cannot trigger any of these operations or contact a provider.
