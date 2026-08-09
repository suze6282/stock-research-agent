# Evidence Ledger

Every Evidence record is scoped to one run, security, Snapshot, and
`research_as_of_time`. Admission verifies source existence, checksum, scope,
publication time, Citation validity, and metric lineage.

Evidence states include valid, invalid, future, conflicting, missing-source,
and `BLOCKED`. Citation Evidence must bind a valid Citation and concrete
DocumentVersion. Metric Evidence requires Calculation Run, Calculation Inputs,
and Formula version.

`SYNTHETIC_TEST_ONLY` and unknown sources cannot be primary Evidence for a real
company Claim. Blocked capability Evidence explains a limitation; it does not
prove a company fact. Evidence is preserved when conflicts are found.
