# E2E-003 Partial Snapshot Research Contract

## Status

APPROVED DECISION: CONTROLLED DEGRADED EXECUTION

This decision records the approved contract. It does not implement or relax any
production behavior.

## Problem

Stage 4 defines `PARTIAL` as a sealed, immutable, checksummed, reproducible
Snapshot whose evidence coverage has known gaps. The Stage 7 production request
preflight currently accepts only `COMPLETE`, so a valid `PARTIAL` Snapshot stops
at `SNAPSHOT_NOT_COMPLETE` before a Research Request, Plan, Run, Tool Invocation,
Package, or Report can be audited.

## Existing conflicting contracts

- Stage 4 creates honest immutable `PARTIAL` Snapshots when a source category or
  publication timestamp is unavailable; missing values remain absent.
- Stage 5 and Stage 6 preserve `PARTIAL`, `BLOCKED`, `NULL`, and missing-evidence
  states.
- Stage 7 Request preflight requires `Snapshot.status == COMPLETE`, while its
  Run, Tool, Evidence, Claim, and Package contracts support degraded outcomes.
- Stage 8 supports `PARTIAL` and `BLOCKED` reports and prevents them from being
  released as `PUBLISHABLE`.
- Stage 10 offline planning accepts `COMPLETE` and `PARTIAL`, but the production
  research-pipeline entry delegates to the Stage 7 COMPLETE-only preflight.

## Route A: stop at PARTIAL

Only `COMPLETE` may create a Research Request. This is maximally conservative,
but it prevents an auditable degraded result for the real offline samples and
conflicts with the downstream contracts and Stage 10 offline planning contract.

## Route B: controlled degraded execution

A sealed `PARTIAL` Snapshot may create an immutable Research Request and proceed
through the deterministic Planner and approved read-only offline Tools. Evidence,
Claims, Package, Report, Reflection, and Release Gate must retain missing-data and
blocked states. A degraded run must never become publishable.

## Approved decision

Route B is approved. `PARTIAL` is admissible only when the Snapshot is:

- sealed;
- immutable;
- checksummed;
- reproducible.

`PARTIAL != COMPLETE`. Admission must not change the Snapshot status or erase its
warnings.

## Safety invariants

1. Missing data is never replaced by zero, an empty string, or an estimate.
2. `UNKNOWN` never becomes `SUPPORTED`.
3. `PARTIAL` never becomes `COMPLETE` implicitly.
4. A Claim without valid Evidence never becomes `SUPPORTED`.
5. Invalid Citations never enter a valid factual chain.
6. Synthetic fixtures never substitute for real company evidence.
7. Future evidence and cross-Snapshot evidence remain invalid.
8. Revision is subtractive or disclosure-only and creates no new facts, Evidence,
   Citations, or Tool results.
9. A `PARTIAL` or `BLOCKED` Package/Report is never `PUBLISHABLE`.
10. Security, Snapshot, Request, Planner, Policy, Tool Catalog, and as-of bindings
    remain exact and immutable.
11. Offline execution performs zero network, Credential, Live Provider, and model
    calls.

## Allowed Snapshot states

- `COMPLETE`: normal controlled execution.
- `PARTIAL`: controlled degraded execution, only when sealed, immutable,
  checksummed, and reproducible.

## Rejected Snapshot states

- `BUILDING`;
- `FAILED`;
- any other unsealed state;
- `SUPERSEDED` for creation of a new Research Request by default.

Historical records may continue to reference their original Snapshot. This ADR
does not authorize a new Request from `SUPERSEDED`.

## Expected status propagation

- Snapshot `PARTIAL` remains visible as degraded context.
- Run status and warning codes must not imply complete evidence coverage.
- Tool Observations preserve `PASS`, `PARTIAL`, `BLOCKED`, and `FAIL`.
- Missing or invalid Evidence produces honest Evidence status.
- Unsupported, partial, conflicting, or blocked Claims remain so.
- Package and Report may be only `PARTIAL` or `BLOCKED` for this degraded path.
- Warning codes must be persisted and auditable.

## Expected release behavior

Reflection runs under the existing deterministic constraints. Revision may only
delete, downgrade, disclose, or safely crop existing material. Release Gate must
return a non-publishable decision for a `PARTIAL` or `BLOCKED` Package/Report.

## Explicit non-goals

- No change to Snapshot construction, immutability, checksums, or status meaning.
- No automatic upgrade from `PARTIAL` to `COMPLETE`.
- No relaxation of Evidence, Claim, Citation, Reflection, or Release Gate rules.
- No schema or migration decision in this RED-test task.
- No Live Provider, Credential, network, model, Gate B, or Stage 11 work.
- No synthetic evidence for Industrial FII or Micron.

## Required RED tests

1. Request admission accepts sealed `PARTIAL` and rejects `BUILDING`, `FAILED`,
   and `SUPERSEDED`.
2. The PostgreSQL production composition creates Request, Plan, and Run from a
   sealed `PARTIAL` Snapshot.
3. The degraded context persists to Run and Package warning/status outputs without
   any implicit `COMPLETE` promotion.
4. Existing Evidence and Claim safety contracts remain enforced.
5. Existing Report, Reflection, Revision, and Release Gate safety contracts remain
   enforced.
6. A production-composed offline E2E contract reaches auditable degraded records
   and never produces a publishable result.

## Future minimal implementation boundary

The future implementation may change only the sealed-Snapshot admission contract,
deterministic degraded-status/warning propagation, and the production composition
needed to invoke the existing Evidence and Claim services. Stage 10 and Stage 7
preflight must express one consistent rule. Snapshot semantics, Planner budgets,
Tool permissions, Evidence/Claim validation, Report/Reflection behavior, and the
Release Gate safety rules must remain unchanged.
