# SEC Provider Control-Plane Bootstrap Corrective Review

## Decision

The corrective implementation is accepted by independent review.

```text
SEC_PROVIDER_BOOTSTRAP_CORRECTIVE_REVIEW: COMPLETE
REVIEW_VERDICT: PASS
CRITICAL_FINDINGS: 0
IMPORTANT_FINDINGS: 0
MINOR_FINDINGS: 0
```

This review authorizes neither operational bootstrap nor Operational Freeze,
Gate B authorization, Gate B execution, or Stage 11 work.

## Reviewed lineage

| Role | Commit |
|---|---|
| Original implementation | `f4d90fbebbbfb9005c7621e5b52b7b4497b053cf` |
| Corrective RED baseline | `ec4ccf0ff5a62a07d992ff96ea58bc06b9afb372` |
| Corrective implementation | `5036d782426345e8aa696c474b67fdb927ea9ab9` |

The corrective implementation changed only:

- `src/stock_research_agent/providers/sec_edgar/bootstrap.py`
- `src/stock_research_agent/cli_providers.py`

It changed no test, migration, configuration, manifest value, schema, or
operational record.

## Previous findings

| Finding | Original defect | Corrective result |
|---|---|---|
| IMPORTANT-01 | CLI conflict output omitted aggregate `CONFLICT` status | Resolved. Plain and JSON output contain `status=CONFLICT` and one stable safe code. |
| IMPORTANT-02 | Partial bootstrap projected aggregate status onto every component | Resolved. Each component retains its own transaction outcome. |

## Component outcome projection

Component outcomes are determined after the transaction advisory lock is
acquired. They are captured from the authoritative per-component existence
observed by the serialized transaction, retained in an immutable internal
snapshot, and projected only after commit succeeds.

| Initial state | Aggregate | Definition | Capability | Policy |
|---|---|---|---|---|
| Empty | `CREATED` | `CREATED` | `CREATED` | `CREATED` |
| Definition only | `CREATED` | `REUSED` | `CREATED` | `CREATED` |
| Definition and Capability | `CREATED` | `REUSED` | `REUSED` | `CREATED` |
| Fully equivalent | `REUSED` | `REUSED` | `REUSED` | `REUSED` |

Fresh PostgreSQL partial-state tests confirmed that pre-existing Definition
and Capability IDs are preserved and only missing component IDs are created.
The aggregate status is not copied into component results.

## Serialization and concurrency

The ordering remains:

```text
begin transaction
-> verify database identity
-> acquire deterministic transaction advisory lock
-> inspect and materialize Definition, Capability, and Policy
-> flush
-> authoritative checksum readback
-> capture immutable component outcomes
-> commit
-> construct public result
```

An independent two-caller PostgreSQL probe established:

| Caller | Aggregate | Definition | Capability | Policy |
|---|---|---|---|---|
| Creator | `CREATED` | `CREATED` | `CREATED` | `CREATED` |
| Serialized reuser | `REUSED` | `REUSED` | `REUSED` | `REUSED` |

Final cardinality was exactly one Definition, one Capability, and one Policy.
Concurrent identical and concurrent conflicting bootstrap contracts also
passed, with no duplicates or mixed committed state.

## CLI conflict projection

Plain conflict output is bounded to:

```text
status: CONFLICT
code: <stable SEC provider bootstrap conflict code>
```

JSON conflict output is a standalone parseable object containing exactly the
safe semantic fields `status` and `code`. Both forms retain the existing
nonzero exit code. Neither form exposes a database URL, credentials, SQL,
connection details, exception representation, or traceback.

The correction did not change CLI mutation safety:

- plain invocation cannot mutate without `--confirm`;
- `--dry-run` remains read-only;
- `--confirm` remains required for bootstrap writes;
- `--json` changes presentation only.

## Failure and transaction semantics

| Contract | Fresh result |
|---|---|
| Component conflict fails closed without a normal success result | PASS |
| Readback mismatch raises `SEC_PROVIDER_BOOTSTRAP_READBACK_MISMATCH` | PASS |
| Readback mismatch rolls back to `0 / 0 / 0` new rows | PASS |
| Injected commit failure propagates | PASS |
| Commit failure leaves `0 / 0 / 0` rows and returns no public result | PASS |
| Public success result is constructed only after commit | PASS |
| Complete equivalent replay reuses all authoritative IDs | PASS |

`SecProviderControlPlaneBootstrapApplication.bootstrap()` remains the sole
transaction owner. Repositories remain transaction-neutral and perform no
internal commit. The correction added no raw persistence SQL.

## Invariance and scope isolation

The versioned manifest and its Definition, Capability, and Provider Policy
payloads and checksums are unchanged. Generic `ProviderPolicy.max_attempts`
remains `3`; Gate B physical attempt four is not introduced into the generic
policy.

The advisory lock remains a PostgreSQL transaction advisory lock using the
same deterministic SHA-256-derived signed 64-bit key for the same provider and
manifest version. No pre-lock status inspection or post-commit existence
inference was introduced.

Allowed direct SQL remains limited to database identity inspection and advisory
lock acquisition. Control-plane raw SQL writes remain zero, and the repository
route is not bypassed.

Fresh zero-side-effect verification found no changes to Credential Reference,
Source License Policy, Sync Request, Sync Plan, authorization, SyncRun,
attempt, Raw Artifact, Document/Citation, or terminal state.

```text
DNS: 0
HTTP: 0
SEC calls: 0
Credential reads: 0
Authorization created: NO
Permit created: NO
Gate B executed: NO
```

## Corrective test quality

The corrective contracts exercise the owning production boundaries against
real loopback disposable PostgreSQL:

| Contract | Coverage | Result |
|---|---|---|
| CORR-001 | Real CLI plain conflict and persisted conflict preservation | PASS |
| CORR-002 | Definition-only authoritative partial state | PASS |
| CORR-003 | Definition-plus-Capability authoritative partial state | PASS |
| CORR-004 | Fully equivalent per-component reuse | PASS |
| CORR-005 | Empty-state per-component creation | PASS |
| CORR-006 | Readback mismatch rollback | PASS |
| CORR-007 | Commit failure suppresses success | PASS |
| CORR-008 | Real CLI JSON conflict contract | PASS |

No material corrective coverage gap was found.

## Fresh verification

| Verification | Result |
|---|---|
| Corrective suite | `8 passed` |
| Original bootstrap suite | `43 passed` |
| Focused Provider and Gate B regressions | `140 passed` |
| Concurrency/failure/zero-side-effect targeted rerun | `5 passed` |
| Ruff | PASS |
| Format | PASS, 685 files |
| mypy | PASS, 292 source files |
| `git diff --check` | PASS |

The 11 admin fresh-database migration tests were **not executed** because both
a loopback `TEST_DATABASE_URL` and `TEST_DATABASE_ADMIN_URL` are required and
the admin URL was unavailable. They are not represented as passing. This
corrective change introduces no migration.

The previously reported full offline suite at the reviewed implementation SHA
remains supporting evidence only: 3,238 collected, 3,227 passed, 11 skipped,
zero failures, zero errors, and zero warnings. This independent review relied
on the fresh focused executions listed above for its verdict.

## Findings and final state

```text
CRITICAL: 0
IMPORTANT: 0
MINOR: 0

IMPORTANT_01_RESOLVED: YES
IMPORTANT_02_RESOLVED: YES
COMPONENT_OUTCOME_PROJECTION: PASS
CONCURRENT_STATUS_PROJECTION: PASS
CLI_CONFLICT_PROJECTION: PASS
READBACK_MISMATCH_FAIL_CLOSED: PASS
COMMIT_FAILURE_RESULT_SUPPRESSION: PASS
ATOMICITY: PASS
IDEMPOTENCY: PASS
CONCURRENCY: PASS
ZERO_SIDE_EFFECT_BOUNDARY: PASS

READY_FOR_OPERATIONAL_SEC_PROVIDER_BOOTSTRAP: YES
OPERATIONAL_PROVIDER_BOOTSTRAP: NOT_PERFORMED
OPERATIONAL_FREEZE: INCOMPLETE
GATE_B_AUTHORIZED: NO
GATE_B_EXECUTED: NO
STAGE_11: NOT_STARTED
HUMAN_REVIEW_REQUIRED: YES
```
