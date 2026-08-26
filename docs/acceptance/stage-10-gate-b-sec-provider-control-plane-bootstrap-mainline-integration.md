# SEC Provider Control-Plane Bootstrap Mainline Integration

## Decision

The fully reviewed SEC Provider control-plane bootstrap lineage was integrated
into authoritative `main` by fast-forward and freshly verified offline.

```text
SEC_PROVIDER_BOOTSTRAP_MAINLINE_INTEGRATION: COMPLETE
REVIEWED_BOOTSTRAP_MAINLINE_INTEGRATED: YES
READY_FOR_OPERATIONAL_SEC_PROVIDER_BOOTSTRAP_PREFLIGHT: YES
```

This integration did not perform the operational bootstrap or Operational
Freeze. It created no authorization and executed no Gate B or Stage 11 work.

## Repository integration

| Field | Value |
|---|---|
| Prior `main` | `3b236fb5315ecbb751ffe9542337411d1141eeea` |
| Reviewed candidate | `3082d4cc0e1a7677f0a18db6c4d310edb6e51a69` |
| Relationship before integration | `ANCESTOR` — prior `main` was the merge base and an ancestor of the candidate |
| Integration method | `git merge --ff-only` |
| Merge commit | None |
| Rebase, squash, or cherry-pick | None |

The reviewed candidate contains the previously integrated Phase 7A operational
discovery lineage and Gate B request-identity RED, implementation, corrective,
review, and mainline-integration lineage.

The bootstrap lineage is complete:

| Role | Commit |
|---|---|
| Approved design | `2330773e9b950565e94712462fb8c024b0f2c818` |
| Original RED | `71744b5976c79f1c8fdfae8a811b3f6a850e0e11` |
| Original implementation | `f4d90fbebbbfb9005c7621e5b52b7b4497b053cf` |
| Corrective RED | `ec4ccf0ff5a62a07d992ff96ea58bc06b9afb372` |
| Corrective implementation | `5036d782426345e8aa696c474b67fdb927ea9ab9` |
| Corrective review | `3082d4cc0e1a7677f0a18db6c4d310edb6e51a69` |

The candidate introduced only the reviewed SEC Provider bootstrap design,
application and CLI, tests, module-boundary registration, and corrective
review artifact. No unrelated production change was found.

## Review disposition

The final independent corrective review verdict was `PASS`:

```text
IMPORTANT_01_RESOLVED: YES
IMPORTANT_02_RESOLVED: YES
CRITICAL_FINDINGS: 0
IMPORTANT_FINDINGS: 0
```

The implementation projects each component's authoritative CREATED/REUSED
outcome rather than copying aggregate status. Plain and JSON conflict output
contain aggregate `CONFLICT` plus one stable safe error code.

## Migration invariant

```text
ALEMBIC_HEAD: 0013_gate_b_attempt_number_capacity
NEW_MIGRATIONS: 0
COMPETING_ALEMBIC_HEADS: NO
```

The integration performed repository inspection only for this invariant and
did not connect to the operational database.

## Fresh bootstrap verification on main

| Suite | Result |
|---|---|
| Corrective bootstrap contracts | `8 passed` |
| Original bootstrap contracts | `43 passed` |
| Focused Provider and Gate B regressions | `140 passed` |
| Selected PostgreSQL invariant rerun | `8 passed` |

The PostgreSQL invariant rerun established:

| Invariant | Result |
|---|---|
| Atomic success | PASS |
| Transaction rollback | PASS |
| Idempotent replay | PASS |
| Equivalent partial-state completion | PASS |
| Concurrent identical bootstrap | PASS |
| Concurrent conflicting bootstrap | PASS |
| Readback-mismatch rollback | PASS |
| Commit-failure result suppression | PASS |
| Zero-side-effect boundary | PASS |

All PostgreSQL verification used the repository-standard loopback disposable
test database. The operational `stock_research` database was not configured or
mutated.

## CLI contract

```text
PLAIN_CONFLICT: PASS
JSON_CONFLICT: PASS
CONFLICT_STATUS: CONFLICT
STABLE_SAFE_CODE: PRESENT
SENSITIVE_LEAKAGE: NO
PLAIN_INVOCATION_IMPLICIT_MUTATION: NO
DRY_RUN_MUTATION: NO
CONFIRM_REQUIRED_FOR_WRITE: YES
```

The integration did not invoke bootstrap against an operational database.

## Provider and Gate B regression

Fresh focused verification passed for:

- Provider Definition;
- Provider Capability;
- Provider Policy;
- Provider repositories;
- canonicalization and registries;
- module boundaries;
- Gate B request identity;
- Gate B authorization, transport, attempt, and budget boundaries.

## Full offline suite

Command:

```text
pytest -W error -m "not live"
```

Result:

```text
COLLECTED: 3238
PASSED: 3227
FAILED: 0
ERRORS: 0
SKIPPED: 11
WARNINGS: 0
DURATION: 1005.66 seconds / 16:45
```

The 11 admin fresh-database migration tests were **not executed** because both
a loopback `TEST_DATABASE_URL` and `TEST_DATABASE_ADMIN_URL` are required and
the admin URL was unavailable. They are not represented as passing. The SEC
Provider bootstrap introduces no migration.

## Quality

| Check | Result |
|---|---|
| Ruff | PASS |
| Format | PASS, 685 files |
| mypy | PASS, 292 source files |
| `git diff --check` | PASS |

## Safety and operational state

```text
EXTERNAL_NETWORK: 0
OPERATIONAL_DATABASE_URL: NOT_CONFIGURED
OPERATIONAL_STOCK_RESEARCH_MUTATIONS: 0
CREDENTIAL_READS: 0
RAW_CONTACT: NO
AUTHORIZATION: NO
GATE_B_EXECUTION: NO
STAGE_11: NOT_STARTED

OPERATIONAL_PROVIDER_BOOTSTRAP: NOT_PERFORMED
OPERATIONAL_FREEZE: INCOMPLETE
GATE_B_AUTHORIZED: NO
GATE_B_EXECUTED: NO
HUMAN_REVIEW_REQUIRED: YES
```

The canonical mainline code is ready only for a separately authorized
operational SEC Provider bootstrap preflight. This artifact does not authorize
configuring the operational database, invoking `bootstrap --confirm`, retrying
Operational Freeze, or proceeding to Gate B authorization.
