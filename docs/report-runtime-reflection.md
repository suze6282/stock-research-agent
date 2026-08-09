# Runtime Reflection and deterministic Revision

`runtime-report-reflection-v1` contains exactly 40 deterministic checks. It
validates binding reachability, context, as-of filtering, Citation status,
checksums, reference parity, disclosure, language safety, Synthetic isolation,
data quality and limitations.

Reflection has at most two rounds. Findings are append-only and carry a stable
code, category, severity, location, remediation code and blocking flag.
`CRITICAL` and `HIGH` are blocking.

Revision has at most one round and is subtractive or disclosure-only. It may
remove unsafe/unbound content, downgrade partial language, disclose conflicts,
move unsupported/blocked content, repair deterministic formatting/reference
numbers and truncate an excerpt. It cannot create or change a Claim, Evidence,
Citation, Security, Snapshot, as-of time, support decision, calculation,
retrieval, Tool result or model result. Unrepairable findings remain unresolved.
