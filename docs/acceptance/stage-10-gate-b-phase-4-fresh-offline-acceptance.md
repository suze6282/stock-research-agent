# Phase 4 Fresh Offline Production Acceptance

Status: **PASS / HUMAN APPROVED**

```text
PHASE_4_FRESH_OFFLINE_PRODUCTION_ACCEPTANCE: PASS
GATE_B_READINESS: NO_GO
```

## 1. Purpose and scope

This document is the durable Phase 4 acceptance artifact for the fresh,
migration-built, offline Gate B production acceptance completed in Phase 4A-R.
It records the accepted repository identity, database evidence, contract proofs,
regression results, security conclusions, and remaining operational gates.

This artifact creates no production, test, ORM, migration, schema, or runtime
change. It does not authorize or execute Gate B, does not start Phase 5 or
Stage 11, and does not merge any branch into `main`.

## 2. Repository identity and corrective lineage

| Identity | Value |
|---|---|
| Source implementation HEAD | `a950af7adcfbf14c187afe2354f27c3ef2eae0d0` |
| Source branch | `feat/stage-10-gate-b-corrective-3e-attempt-limit` |
| Acceptance branch | `verify/stage-10-gate-b-phase-4-fresh-acceptance` |
| Phase 3D final orchestration | `f2000fa9cac4f913a0a43966ce0ee66f43b2a94d` |
| Phase 3E-0 contract | `8ba096e755352dc0c2a16918e5417e0940dc0230` |
| Phase 3E-1 RED | `db4d26939967b1dd1848b18c5b77034b44f72441` |
| Phase 3E-2 correction | `a950af7adcfbf14c187afe2354f27c3ef2eae0d0` |

The acceptance branch was created from the exact source implementation HEAD.
No merge, rebase, reset, stash, or source rewrite was used.

## 3. Why Phase 3E existed

The first Phase 4A run exposed two hard contract failures:

| Finding | Accepted finding |
|---|---|
| `P4A-H01` | The production migration schema allowed `attempt_number <= 3`, while the authorized Gate B plan required storage for as many as four physical attempts. |
| `P4A-H02` | Generic `ProviderRequestAttemptWrite` had been widened to accept attempt 4, incorrectly granting a Gate B-specific semantic capability to generic provider callers. |

The focused PostgreSQL fixture omitted the production attempt-number CHECK
constraint. That fixture divergence concealed the physical incompatibility.

The corrected contract is deliberately split by ownership:

| Boundary | Maximum / result |
|---|---:|
| Physical PostgreSQL row | 4 |
| SQLAlchemy ORM representation | 4 |
| Generic provider input | 3 |
| Gate B authorized input | 4 |
| `ProviderPolicy.max_attempts` | 3 |
| Attempt 5 | Rejected |
| Focused fixture parity | Restored |

Physical storage capacity is not generic semantic authorization. Attempt 4 is
accepted only through the exact authorized Gate B reservation path; generic and
unauthorized attempt-4 writes remain rejected.

## 4. Fresh database and migration evidence

| Property | Accepted value |
|---|---|
| Database | `stock_research_gate_b_acceptance_retry_20260822_173550_test` |
| Classification | `LOCAL_DISPOSABLE_FRESH_ACCEPTANCE` |
| PostgreSQL | 17.10 |
| Host | `127.0.0.1` |
| Port | `55432` |
| Listen scope | `LOOPBACK_ONLY` |
| Database source | `template0` |
| Initial application tables | 0 |
| Migration path | empty/base → `alembic upgrade head` |
| Alembic head | `0013_gate_b_attempt_number_capacity` |
| Migration result | PASS |
| Final public tables | 106 |
| Manual application DDL | NO |
| Dump restore | NO |

The fresh acceptance database was empty and was built exclusively by committed
migrations. It was not cloned from an application database, restored from a
dump, or repaired with manual DDL.

## 5. Schema acceptance

| Proof | Result |
|---|---|
| ORM maximum | 4 |
| Migration maximum | 4 |
| Focused fixture maximum | 4 |
| Attempt 3 | Accepted everywhere |
| Attempt 4, physical storage | Accepted |
| Attempt 4, authorized Gate B path | Accepted |
| Attempt 4, generic `ProviderRequestAttemptWrite` | Rejected |
| Attempt 4, unauthorized path | Rejected |
| Attempt 5 | Rejected everywhere |
| `TEST_FIXTURE_SCHEMA_DIVERGENCE` | NO |
| `SCHEMA_MODEL_MISSING_COLUMN_PROBLEMS` | 0 |
| Alembic check | PASS |

The migration, ORM metadata, and focused fixture agree on the physical 1–4
range, while the generic application boundary remains 1–3.

## 6. Exact Gate B resource contract

The accepted plan contains exactly three resources in this exact order:

| Ordinal | Slice | Endpoint policy | Artifact kind | Maximum bytes |
|---:|---|---|---|---:|
| 0 | `SEC_SUBMISSIONS` | `SEC_SUBMISSIONS_JSON` | `SUBMISSIONS_METADATA` | 2 MiB |
| 1 | `SEC_FILING_INDEX` | `SEC_FILING_DOCUMENT` | `FILING_INDEX` | 1 MiB |
| 2 | `SEC_PRIMARY_DOCUMENT` | `SEC_FILING_DOCUMENT` | `PRIMARY_FILING_DOCUMENT` | 20 MiB |

Company Facts is `OUT_OF_SCOPE`. Resource count is exactly 3; order is exactly
0 → 1 → 2. The shared plan permits at most four physical attempts and one retry
across all resources; neither counter resets per resource.

## 7. Authorization and budget evidence

| Contract | Result |
|---|---|
| RED-050 | GREEN |
| RED-051 | GREEN |
| RED-052A | GREEN |
| RED-052B | GREEN |
| RED-052C | GREEN |
| RED-053 request budget | GREEN |
| RED-053 retry budget | GREEN |
| RED-054 | GREEN |

Two same-approval execution starts were exercised concurrently. Exactly one
succeeded and one failed closed with `EXEC_APPROVAL_REPLAYED`.

Committed `ABANDONED` request reservations are not refunded. Committed
`ABANDONED` retry reservations are not refunded. Attempt numbers and
request-attempt IDs are never reused.

## 8. Attempt-limit evidence

| Contract | Result |
|---|---|
| RED-062 | GREEN |
| RED-063 | GREEN |
| RED-064 | GREEN |
| RED-065 | GREEN |
| RED-066 | GREEN |
| RED-067 | GREEN |

RED-067 proved the complete four-attempt migration-built scenario:

| Attempt | Resource and outcome |
|---:|---|
| 1 | `SEC_SUBMISSIONS` — success |
| 2 | `SEC_FILING_INDEX` — transient failure |
| 3 | `SEC_FILING_INDEX` — single retry success |
| 4 | `SEC_PRIMARY_DOCUMENT` — success |

The run then created a `DocumentVersion`, created a `Citation`, passed aggregate
Data Quality, committed terminal `PASSED`, and returned a complete
`GateBAuditView`. External network activity was 0.

## 9. Transport evidence

| Transport invariant | Accepted value |
|---|---|
| SEC connect / idle-read / total timeout | 10 / 30 / 120 seconds |
| Redirects | 0 |
| `SafeHttpClient` physical attempts per call | 1 |
| Retry authority | `SecGateBRetryController` only |
| HTTP 429 retry | NO |
| Raw URL input | FORBIDDEN |
| Exact HTTPS/method/host/port/path/resource allowlist | YES |
| Real contact-value reads | 0 |

Transport cannot independently retry. It receives only the exact authorized,
allowlisted request contract and cannot accept a caller-supplied raw URL.

## 10. Transaction and artifact evidence

| Invariant | Result |
|---|---|
| Database transaction held during send | NO |
| Reservation committed before send | YES |
| Response validation before settlement | YES |
| Blob alone authoritative | NO |
| Orphan blob authoritative | NO |
| Artifact/manifest settlement atomic | YES |
| Earlier committed lineage retained after later-resource failure | YES |

Network send occurs outside the short authoritative database transactions. A
blob is never evidence by itself; authority requires the committed settlement
and matching database lineage.

## 11. Audit and terminal evidence

| Contract | Result |
|---|---|
| RED-044 | GREEN |
| RED-055 | GREEN |
| RED-056 equivalent replay | GREEN |
| RED-056 conflicting replay | GREEN |
| RED-056 concurrent replay | GREEN |

The audit projection is complete, bounded, deterministic, and secret-free.

Equivalent terminal replay returns the same authoritative terminal ID.
Conflicting replay fails with `GATE_B_TERMINAL_CONFLICT`. Concurrent identical
terminal calls create one authoritative row and no partial conflicting writes.

## 12. Three-resource orchestration

| Contract | Result |
|---|---|
| RED-057 | GREEN |
| RED-058 | GREEN |
| RED-059 | GREEN |
| RED-060 | GREEN |
| RED-061 | GREEN |

The successful path is:

```text
authorization validation
→ authoritative start
→ SEC_SUBMISSIONS
→ SEC_FILING_INDEX
→ SEC_PRIMARY_DOCUMENT
→ DocumentVersion
→ Citation
→ aggregate Data Quality
→ idempotent terminal
→ GateBAuditView
→ STOP
```

Failure is fail-closed by ordinal:

- ordinal 0 failure produces zero sends for ordinals 1 and 2;
- ordinal 1 failure produces zero sends for ordinal 2;
- ordinal 2 failure cannot produce aggregate PASS; and
- all earlier committed evidence remains authoritative and auditable.

## 13. Complete contract evidence

| Evidence set | Result |
|---|---|
| RED-028 through RED-067 | ALL GREEN |
| Exact Gate B contract tests | 127 passed |
| Fresh focused PostgreSQL proofs | 32 passed |
| Additional repository-name-bound PostgreSQL tests | 3 passed |

### Legacy database-name qualification

Three legacy PostgreSQL tests contain the hard-coded assertion:

```text
current_database() == "stock_research_test"
```

Those tests cannot run against a uniquely named acceptance database without
modifying the tests. They were therefore executed separately against the
repository-standard loopback disposable database `stock_research_test` and
passed 3 / 3.

These three tests were **not** used as evidence for fresh Gate B schema,
migration, attempt-limit, orchestration, or PostgreSQL acceptance. Every
Gate B schema-sensitive and migration-sensitive acceptance proof was established
against `stock_research_gate_b_acceptance_retry_20260822_173550_test`.

This qualification is non-blocking. It does not affect the fresh Gate B evidence,
because the complete Gate B acceptance suite and focused PostgreSQL proofs used
the fresh migration-built database. This document does not claim that every
repository PostgreSQL test used the uniquely named fresh database.

## 14. Full repository regression

The complete non-live repository regression used the standard disposable
`stock_research_test` database because of the three legacy database-name-bound
tests described above.

```text
pytest -W error -m "not live"
```

| Result | Value |
|---|---:|
| Collected | 3167 |
| Passed | 3167 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 0 |
| Warnings | 0 |
| Duration | 873.45 seconds / 14:33 |

The full repository regression result is not represented as a run against the
fresh acceptance database.

## 15. Quality evidence

| Check | Result |
|---|---|
| Ruff | PASS |
| Format | PASS — 672 files |
| mypy | PASS — 290 source files |
| Alembic check | PASS |
| `git diff --check` | PASS |

## 16. Security evidence

| Severity | Findings |
|---|---:|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 0 |

Verified security invariants:

| Prohibited behavior | Observed |
|---|---|
| Authorization bypass | NO |
| Capability before COMMIT | NO |
| Same-approval replay | NO |
| Silent `ABANDONED` refund | NO |
| Generic attempt-4 bypass | NO |
| Attempt-5 acceptance | NO |
| Attempt/retry reset per resource | NO |
| Company Facts in Gate B | NO |
| Raw URL acceptance | NO |
| Redirect bypass | NO |
| Contact leakage | NO |
| Database transaction during send | NO |
| Blob authority bypass | NO |
| Terminal duplication | NO |
| Incomplete-resource PASS | NO |
| Fixture/migration divergence | NO |
| Claim/Report/Publication/Stage 11 continuation | NO |

## 17. Direct CLI safety

The direct CLI default composition remained blocked:

| Field | Result |
|---|---|
| Status | `BLOCKED` |
| Warning | `LIVE_AUTHORIZATION_REQUIRED` |
| Warning | `LIVE_TRANSPORT_NOT_CONFIGURED` |
| Exit code | 3 |
| `DEFAULT_LIVE_COMPOSITION` | `BLOCKED` |
| Automatic SEC connection | NO |
| Automatic credential resolution | NO |
| Automatic authorization | NO |
| Automatic filing discovery | NO |

The offline acceptance did not turn the default CLI into an executable live
composition.

## 18. Operational freeze state

| Candidate field | Value |
|---|---|
| Provider | `SEC_EDGAR_PUBLIC_V1` |
| Company | Micron Technology |
| Ticker | `MU` |
| CIK | `0000723125` |
| Exchange | `XNAS` |

The following operational inputs remain intentionally unfrozen:

- exact accession;
- filing date;
- index filename;
- primary filename;
- `research_as_of_time`;
- contact configuration;
- retention decision; and
- live plan checksum.

No single-use authorization was created.

## 19. Safety accounting

| Safety boundary | Result |
|---|---:|
| External network | 0 |
| External DNS | 0 |
| Credential value reads | 0 |
| SEC calls | 0 |
| Gate B authorized | NO |
| Gate B executed | NO |
| Stage 11 | NOT STARTED |

## 20. Modified surface

This phase changes documentation only:

| Surface | Modified |
|---|---|
| Production | NO |
| Tests | NO |
| ORM | NO |
| Migrations | NO |
| Documentation | YES |

The sole Phase 4B artifact is
`docs/acceptance/stage-10-gate-b-phase-4-fresh-offline-acceptance.md`.

## 21. Verdict and remaining gates

```text
PHASE_4A_FRESH_OFFLINE_TECHNICAL_ACCEPTANCE: PASS / HUMAN_APPROVED
PHASE_4_FRESH_OFFLINE_PRODUCTION_ACCEPTANCE: PASS
GATE_B_READINESS: NO_GO
GATE_B_AUTHORIZED: NO
GATE_B_EXECUTED: NO
STAGE_11: NOT STARTED
```

Phase 4 proves offline production acceptance only. It does not prove operational
readiness for live Gate B execution.

The following remain mandatory before any controlled live Gate B pilot:

1. Phase 5 — integration/main review;
2. Phase 6 — fresh Gate B readiness review;
3. Phase 7 — operational freeze;
4. explicit single-use human authorization; and
5. the separately controlled live Gate B pilot.

Gate B therefore remains `NO_GO`. Human review remains required, Phase 5 has
not started, `main` has not been merged, and this acceptance artifact grants no
live authority.
