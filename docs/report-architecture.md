# Stage 8 verifiable report architecture

Stage 8 consumes one immutable `ReportInputManifest` built only from a sealed
Stage 7 `ResearchPackage`. It never reruns the Research Agent, Tool, retrieval,
calculation, provider, Snapshot, or network workflow.

The canonical source is structured JSON. Markdown is a deterministic projection
of that JSON and is rejected when section order, block order, status, values,
units, periods, references, or checksums differ. A report version stores the
Security, Snapshot, research as-of time, Package and all Claim/Evidence/Link/
Citation set checksums. A successor creates a new immutable row and points to
`previous_report_id`; it never edits the source report.

Fact-bearing content follows this exact chain:

```text
Report Block → Claim → Claim-Evidence Link → Evidence
             → VALID Citation or structured calculation lineage
```

Headings and fixed labels may be unbound only when they contain no company fact.
Unsupported facts stay out of normal factual sections. Conflicts, missing
evidence and blocked capabilities remain visible as `PARTIAL`, `BLOCKED` or
`NO_EVIDENCE`.

The finite workflow is:

```text
Generate → Reflection round 1 → at most one Revision
         → Reflection round 2 → deterministic Release Gate
```

Runtime Reflection records are production feature data. They are distinct from
the two development review documents under `docs/reflection`.

Industrial FII (`601138.SH`) and Micron (`MU`) currently degrade to `PARTIAL` or
`BLOCKED`: no verified company filing body and insufficient verified financial
facts are available. Synthetic fixtures are
`SYNTHETIC_TEST_ONLY/NOT_COMPANY_EVIDENCE/OFFLINE/NOT_LIVE`.
