# Deterministic Claims

`DeterministicClaimBuilder` proposes bounded structured Claim candidates. Only
`ClaimSupportValidator` assigns `SUPPORTED`, `PARTIALLY_SUPPORTED`,
`CONFLICTING`, `UNSUPPORTED`, or `BLOCKED`.

Numeric Claims require value, unit, period, as-of, metric basis, Evidence, and
formula or source lineage. Missing values are never represented as zero.
Confidence scores are not used.

Conflicting values, providers, restatements, currencies, units, securities,
Snapshots, future Evidence, and synthetic/real mixtures remain
`CONFLICTING`. The system never averages or chooses the most convenient source.

Industrial FII and MU currently permit identity, data-quality, and limitation
Claims only; their missing verified bodies cannot support business assertions.
