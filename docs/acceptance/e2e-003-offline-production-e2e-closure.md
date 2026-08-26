# E2E-003 Offline Production E2E Closure

- Acceptance date: 2026-08-13
- Original severity: HIGH
- Final status: CLOSED
- Candidate baseline: `ab071e8002c8d986fdbabb9b10b06ae38d3e0627`
- Acceptance environment: offline production composition with SQLAlchemy repositories and
  loopback PostgreSQL test database

## Original finding and root cause

E2E-003 originally prevented a sealed `PARTIAL` Snapshot from traversing the real production
research path. The failure had three layers:

1. Request admission incorrectly required a `COMPLETE` Snapshot.
2. The PostgreSQL request trigger enforced the same overly narrow rule.
3. Production artifact wiring did not carry the degraded state and the full auditable artifact
   chain through Observation, Evidence, Claim, Package, identity verification, and Report.

The final identity blocker was `ISSUER_IDENTITY_MISMATCH`. Canonical Security, Issuer, Snapshot,
Request, Run, and Package identity were already consistent; the missing artifact was frozen
`SECURITY_MASTER_EVIDENCE`. `resolve_security` is a component, not a Tool, so a fake Tool
Invocation was not acceptable.

## Architecture and implementation

The approved Route A lineage model is:

- every Observation has a real `research_step_id`;
- Tool Observations have a real `invocation_id`;
- component Observations have `invocation_id = NULL`;
- PostgreSQL rejects orphan, cross-run, cross-step, cross-security, and cross-snapshot lineage;
- Evidence continues to reference the unified Observation table.

The migration chain is linear and has one head:

`0009_controlled_live_evidence` → `0010_partial_request` →
`0011_component_observation_lineage` →
`0012_component_observation_lineage_integrity`.

The implementation stack is inherited through:

`bab1845` → `b448e18` → `55512d4` → `a4ce86b` → `0b921c8` → `ed81876` →
`bf54f26` → `3854e51` → `9a07624` → `6dcd24f` → `400d667` → `ab071e8`.

All twelve commits were independently confirmed as ancestors of the candidate baseline.

## Fresh contract and migration verification

RED-001 through RED-027 all passed in the final acceptance run. Migration verification covered
upgrade, downgrade without component data, re-upgrade, historical backfill, Evidence link
preservation, Observation immutability, and the fail-closed
`COMPONENT_OBSERVATIONS_PREVENT_DOWNGRADE` guard when component data exists. Historical row loss
was zero.

The focused migration, repository, lineage, Evidence, Claim, Package, Report, citation,
synthetic-isolation, and financial-lineage selection completed with `198 passed`.

## PARTIAL production acceptance

The real `research-pipeline run-from-snapshot` CLI entered the production application with the
committed Industrial FII offline fixture:

- Snapshot: `72000000-0000-4000-8000-000000000006`, `PARTIAL`, as-of
  `2026-07-10T12:00:00Z`
- Security: `40000000-0000-0000-0000-000000000001`
- Issuer: `30000000-0000-0000-0000-000000000001`
- Request / Plan / Run: 1 / 1 / 1; Run status `PARTIAL`
- Tool Invocations: 7 (`PASS` 6, `BLOCKED` 1, `FAIL` 0)
- Observations: 7 (`DATA_QUALITY` 6, `SECURITY_IDENTITY` 1)
- Evidence: 7 (`VALID` 3, `BLOCKED` 4)
- Claims: 6 (`IDENTITY` 1, `DATA_QUALITY` 1, `LIMITATION` 4); support status
  `SUPPORTED` 2 and `BLOCKED` 4
- Supported factual business Claims: 0
- Claim-Evidence links: 6
- Package: 1, `PARTIAL`, 7 Evidence, 6 Claims
- Package warnings: exactly one `AGENT_SNAPSHOT_PARTIAL`; no stale
  `NO_VALIDATED_CLAIMS`
- Report: 1, `PARTIAL`, not publishable

The component identity Observation used the real `resolve_security` Step and a NULL Invocation.
Tool Observations missing a real Invocation numbered zero. The source was
`SECURITY_MASTER_IDENTITY_V1`, its source record ID was the canonical Security ID, and its
independently recomputed checksum matched
`172a8d38dca9c52cf30ee48c0fad4003bdfa6fc34c88b9a2562c06167f3cdeff`.
Exactly one VALID `SECURITY_MASTER_EVIDENCE`, one terminal SUPPORTED `IDENTITY` Claim, and one
identity Claim-Evidence link were present. The unchanged Report issuer validator passed.

Report Reflection R1 executed with `PASS` and zero findings. No revision was required. R2
executed with `PASS` and zero findings. Release Gate executed with internal status `PARTIAL`,
reason `PACKAGE_ELIGIBLE`, and no sealed report. This is the correct fail-closed result: the
PARTIAL package is not eligible for publication.

## Regression and safety results

The committed COMPLETE Snapshot production contract passed, created canonical identity
artifacts, preserved Tool/component lineage, and did not emit `AGENT_SNAPSHOT_PARTIAL`.
`BUILDING`, `FAILED`, and `SUPERSEDED` Snapshots remained inadmissible at both application and
PostgreSQL boundaries.

Cross-security, cross-issuer, duplicate identity, missing identity, invalid checksum, and
synthetic replacement cases failed closed. Future Evidence, invalid Citation, missing financial
lineage, Evidence-free factual support, and BLOCKED-Evidence promotion protections remained
effective. A PASS Invocation was not treated as VALID Evidence, and an Observation was not
treated as Evidence.

No external network, credential, live-provider, or model calls occurred. Only loopback
PostgreSQL was used.

## Final quality evidence

- Ruff: PASS
- Ruff format check: PASS (`653 files already formatted`)
- mypy: PASS (`284 source files`)
- `git diff --check`: PASS
- Full pytest: `3035 passed in 655.86s (0:10:55)`
- Failed / errors / skipped / warnings: 0 / 0 / 0 / 0
- CRITICAL: 0
- New HIGH findings: 0

## Closure decision

E2E-003 is **CLOSED**. The historical finding, root cause, architecture decision, implementation
chain, and acceptance evidence remain recorded. Its HIGH count moves from 1 open finding to 0;
no finding was deleted and no security contract was weakened.

This closure does not authorize Gate B, Stage 11, Live execution, a merge to `main`, or a push.
