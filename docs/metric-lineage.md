# Financial metric lineage

The persisted chain is:

```text
RawPayload -> ProviderFinancialFact -> ProviderFactMapping
           -> NormalizedFinancialFact -> FormulaDefinition
           -> CalculationInput -> DerivedMetric -> CalculationRun
```

Each normalized fact identifies its snapshot, source fact, mapping, canonical concept,
period, original/normalized values and units, publication time and mapping/
normalization versions. Cumulative-derived facts additionally use
`NormalizedFactInput` rows to record every source normalized fact and ordinal role.

Each calculation run is bound to security, immutable snapshot, input checksum and the
calculation/formula/mapping/normalization version set. Numeric derived metrics retain
ordered `CalculationInput` rows. Terminal runs and their inputs/metrics are protected
by repository guards and PostgreSQL triggers. Identical inputs reuse the same run;
concurrent callers serialize through a transaction advisory lock. New evidence or a
new version creates a new run rather than rewriting history.

The lineage API and Tool are read-only. Fixture-backed results carry
`FIXTURE/OFFLINE/NOT_LIVE`; local paths, SQL, credentials, stack traces and raw
exceptions are never returned.
