# Stage 10 Gate B Corrective Contract Resolution

Status: **DESIGN / CONTRACT RESOLUTION COMPLETE**

Human approval: **PENDING**
Production correction: **NOT STARTED**

Gate B readiness remains **NO_GO**. Gate B is not authorized or executed, and
Stage 11 has not started. This document freezes the corrective contracts for
GBR-01 through GBR-04 from repository state
`a7574a4b540d7dad4ebaab50f497cd87962892c9`. It creates no RED test, production
behavior, migration, operational filing selection, or Live capability.

## 1. Current canonical state

- Formal main is `b2b68f598b11d12396a97698a23fc6cc784a1334`.
- The current development branch is
  `feat/stage-10-gate-b-1b3-artifact-audit` at `a7574a4`.
- Stage 10 Offline Production Acceptance and Gate A are complete.
- Steps 1A and 1B-0 are complete. Steps 1B-1 through 1B-3 are implemented on
  the development branch and are not integrated into main.
- RED-028 through RED-049 have committed GREEN evidence.
- Gate B remains `NO_GO`, unauthorized, and unexecuted.

## 2. Audit findings

| Finding | Current behavior | Blocking mismatch |
|---|---|---|
| GBR-01 | `ProductionAuthorizationGate.authorize` accepts caller-supplied `approval_consumed`; the Gate B path does not atomically consume the persisted approval | Caller state is not authoritative and two executions can validate the same approval snapshot |
| GBR-02 | `reserve_consumption` excludes `ABANDONED` rows from the grant request count | A committed reservation can silently restore capacity despite the approved no-refund contract |
| GBR-03 | `GateBAuditView` projects only one artifact/attempt and a small subset of the Runbook lineage; terminal writes are not idempotent | A reviewer cannot reconstruct the complete three-resource pilot or prove one terminal outcome |
| GBR-04 | The Runbook requires submissions, filing index, and primary filing document; current fixtures use Company Facts in place of the filing index and the pilot executes one slice | The implemented plan does not match the approved minimum live exposure or provide whole-plan orchestration |

## 3. GBR-01 — authoritative single-use approval consumption

### 3.1 Repository investigation

The existing schema already contains the required state and serialization
primitives:

- `live_execution_approvals.state` supports `VALID`, `EXPIRED`, `CONSUMED`, and
  `BLOCKED`.
- `live_authorization_grants` and `live_execution_approvals` can be locked with
  `SELECT ... FOR UPDATE`.
- `consume_authorization` appends the terminal grant `CONSUME` event while the
  grant row is locked.
- `reserve_consumption` and `SqlAlchemySecAttemptReservationPort` already create
  the authorization consumption and `PENDING` request attempt in one short
  transaction.
- `AuthorizedGateBExecution` contains the approval, grant, plan, provider, and
  candidate identities required for the transaction.

The current defect is not missing storage. It is composition: validation accepts
the caller-provided boolean `approval_consumed`, and approval consumption is not
part of the authoritative initial reservation transaction.

### 3.2 Alternatives

#### Alternative A — consume approval and reserve the initial attempt atomically

One transaction locks the execution approval, grant, and Sync Run in a fixed
order; revalidates all bindings; changes the approval from `VALID` to
`CONSUMED`; appends the grant `CONSUME` event; reserves authorization capacity;
and inserts the initial `PENDING` attempt. It commits before returning the
execution capability and initial attempt permit.

This removes the crash gap between approval consumption and initial reservation,
gives one authoritative concurrency boundary, and reuses the current reservation
architecture. Lock duration remains bounded because the transaction contains no
credential resolution, DNS, blob I/O, or network operation.

#### Alternative B — consume approval, commit, then reserve the attempt

This reuses `consume_authorization` directly but introduces a legal crash window
where the approval is consumed with no attempt lineage. The outcome remains safe
under fail-closed semantics, but it requires additional reconciliation audit and
provides no benefit over the existing short reservation transaction.

#### Alternative C — retain read-only gate validation and caller state

Rejected. Caller state cannot establish persisted single-use truth and cannot
prevent two concurrent executions from both obtaining eligibility.

### 3.3 Approved recommendation

Adopt Alternative A. The authoritative execution-start operation belongs to the
PostgreSQL live-evidence reservation repository and its production application
composition. The operation returns both `AuthorizedGateBExecution` and the
initial `SecAttemptPermit` only after commit.

`ProductionAuthorizationGate` remains responsible for deterministic envelope,
grant, approval, plan, candidate, scope, checksum, expiry, and credential-reference
validation. It no longer accepts `approval_consumed` from a caller and cannot by
itself return an executable capability before the execution-start transaction.

### 3.4 Frozen contract

1. Caller-supplied approval-consumption truth is forbidden.
2. The initial execution-start transaction locks, in documented fixed order,
   the persisted approval, grant, and Sync Run rows.
3. The transaction requires approval state `VALID`, exact approval/grant/plan
   binding, unexpired approval, active grant, exact candidate/provider scope,
   and an unused initial resource reservation.
4. In that transaction, approval state becomes `CONSUMED`, one grant `CONSUME`
   event is appended, one authorization consumption is reserved, and the exact
   initial `PENDING` request attempt is inserted.
5. `AuthorizedGateBExecution` and the initial `SecAttemptPermit` become usable
   only after that transaction commits.
6. Two concurrent callers using one approval produce exactly one committed
   execution start. The loser receives a deterministic replay/consumption error
   before contact resolution, DNS, or `send_start`.
7. A crash or local failure after commit does not revert the approval, grant
   event, attempt number, request-attempt identity, or reservation to unused.
8. A failed initial reservation rolls back the approval state change, grant
   event, consumption row, and request-attempt row together.
9. A committed execution-start transaction followed by a pre-send failure is
   terminal for that human approval. Automatic reuse is forbidden.
10. Retry permits belong to the same approval, grant, plan, authorization, and
    Sync Run. A consumed approval authorizes only retries within that already
    committed run; it cannot start another run.
11. Audit lineage consists of the consumed approval row, grant `CONSUME` event,
    authorization consumption, Sync Run, initial request attempt, and the
    checksummed Gate B audit event containing the exact approval ID.
12. Process restart cannot reconstruct an executable capability from a consumed
    approval without an explicit reconciliation contract. No such reconciliation
    contract exists in Gate B.

Schema change: **NO**.

## 4. GBR-02 — ABANDONED reservation and no silent refund

### 4.1 Repository investigation

`ConsumptionState` contains `RESERVED`, `SETTLED`, and `ABANDONED`.
`AuthorizationConsumption.settle` permits `ABANDONED` only when
`socket_opened=False` and `actual_bytes=0`. `SecArtifactSettlementService`
uses that state only for a demonstrably unstarted attempt. The corresponding
`ProviderRequestAttempt` remains terminal and permanent.

The grant request-limit query currently counts rows with
`state <> 'ABANDONED'`. In contrast, the Sync Run attempt and retry queries count
all committed request-attempt rows, including attempts whose consumption later
becomes `ABANDONED`.

No authorization-capacity reconciliation service or approved administrative
refund transition exists. `ProviderArtifactReconciler` owns blob authority and
does not own Live authorization capacity.

### 4.2 Alternatives

#### Alternative A — count every committed reservation permanently

Grant request capacity, Sync Run attempt capacity, attempt number, and retry
tokens remain consumed for `ABANDONED`. A new execution requires a new grant and
single-use approval. This exactly implements the approved fail-closed contract
and requires only query/composition changes.

#### Alternative B — reclaim grant capacity while retaining attempt lineage

This is the current mixed behavior. It creates two competing budget truths and
permits an application to infer replay capacity from a settlement status.
Rejected.

#### Alternative C — add an administrative refund transition

No repository-native transition, audit vocabulary, or human authorization
contract exists for this operation. It is outside the current Gate B scope.

### 4.3 Approved recommendation

Adopt Alternative A. Remove `ABANDONED` exclusion from authoritative request
counting. No Gate B operation reclaims authorization, attempt, or retry capacity.

### 4.4 Frozen contract

1. `ABANDONED` is terminal audit lineage, not `UNUSED`.
2. An `ABANDONED` consumption counts against the grant request budget.
3. Its request attempt counts against the Sync Run attempt budget.
4. An `ABANDONED` retry attempt counts against the plan-global retry budget.
5. `attempt_number` and `request_attempt_id` remain permanent and cannot be
   reused.
6. The single-use execution approval and grant remain consumed.
7. Automatic refund, query-based exclusion, capacity reset, and same-approval
   replay are forbidden.
8. Current Gate B exposes no capacity-reclamation operation. Recovery requires a
   new grant, a new single-use approval, and a new immutable plan authorization.
9. Any future reclamation feature requires a separately reviewed append-only
   reconciliation contract. It cannot mutate or delete the abandoned lineage.

Schema change: **NO**.

## 5. GBR-03 — complete operational audit projection

### 5.1 Runbook requirement and current gap

The Runbook requires reconstruction of the exact authorization, grant, approval,
candidate, immutable plan, resources, attempts, statuses, bytes, MIME, artifacts,
checksums, manifest, DocumentVersion, citations, Data Quality outcome, warnings,
budget state, and stable stop reason without credential/header values.

The current `GateBAuditView` returns only one artifact, one attempt, grant
authorization ID, candidate subset, checksum, plan checksum, provider,
retrieval time, and terminal decision. `get_gate_b_audit_view` uses `LIMIT 1`.
`SqlAlchemySecTerminalStore.commit` always inserts a new terminal run and event,
so repeated or concurrent terminal calls can create duplicate authoritative
outcomes.

### 5.2 Existing authoritative sources

| Projection field | Authoritative source | Nullable | Secret risk |
|---|---|---:|---:|
| grant ID and grant checksum | `live_authorization_grants` plus consumption FK | no | no |
| execution approval ID/state/expiry | `live_execution_approvals`; exact ID recorded in checksummed audit summary | no | no |
| provider, security, issuer, CIK | provider definition plus grant scope | no | no |
| plan ID/checksum/resources/order | `provider_sync_plans` and its immutable `slices` | no | no |
| Sync Run and aggregate counters/status | `provider_sync_runs` | no | no |
| resource/slice/endpoint/attempt/retry | `provider_request_attempts` | no | no |
| request start/end/status/HTTP status/bytes/failure code | `provider_request_attempts` | status-dependent | no |
| consumption reservation/actual bytes/socket/state/times | `live_authorization_consumptions` | status-dependent | no |
| observed response MIME for success | `provider_raw_artifacts.content_type` | yes | no |
| observed invalid MIME for failure | checksummed per-attempt `ProviderAuditEvent.safe_summary` | yes | no |
| artifact ID/source/checksum/blob key/size/times/synthetic/license | `provider_raw_artifacts` | yes | blob key is safe metadata |
| manifest ID/checksums/versions/count/warnings | `provider_ingestion_manifests` | yes | no |
| retention decision | artifact license-policy FK joined to existing license policy | yes | no |
| DocumentVersion ID/checksum/parser lineage | document tables, validated from terminal event IDs and artifact checksum | yes | no |
| citation IDs and parser/sanitizer versions | citation tables, validated from terminal event IDs and DocumentVersion | yes | no |
| DQ issues | `provider_data_quality_issues` by Sync Run/manifest | yes | safe detail only |
| terminal validation ID/status/budgets/times | `provider_live_validation_runs`; exact ID in terminal event | no after terminal | no |
| stop reason and terminal stage | checksummed `DATA_QUALITY_STOP` audit event | no after terminal | no |
| credential/contact material | nowhere | forbidden | **must remain absent** |

The exact human approver's personal identity is not persisted by the current
approval table and is not part of the Runbook's minimum database projection.
The operational projection identifies the exact immutable execution approval ID,
registry identity available in the approval contract, and external human
authorization record reference. It does not infer a person from system actor
fields.

### 5.3 Alternatives

#### Alternative A — composed read-only projection over existing lineage

Extend `GateBAuditView` into bounded nested resource/attempt/artifact/ingestion/DQ
records. Query every resource in ordinal order and validate all cross-table IDs,
checksums, counts, and terminal event references. Add checksummed per-attempt and
terminal summaries only for safe facts not represented in typed columns.

#### Alternative B — one additional derived audit row

This duplicates authoritative facts, creates synchronization risks, and still
requires joins for validation. Rejected.

#### Alternative C — new audit table/schema

Existing tables and the bounded checksummed `ProviderAuditEvent` payload can
represent the required projection. Rejected as unnecessary.

### 5.4 Approved recommendation

Adopt Alternative A. The operational audit is a read-only composition, not a new
system of record. Typed columns and FKs remain authoritative; checksummed audit
summaries carry only approval ID, terminal object IDs, observed invalid MIME, and
other bounded safe facts that have no typed column. Every summary identifier is
verified against its source table before returning the view.

### 5.5 Frozen operational projection

The projection returns:

1. grant ID/checksum/state and execution approval ID/state/expiry;
2. provider and complete candidate identity;
3. plan ID/checksum, exactly three ordered resource identities, and approved
   budget/time/redirect policy;
4. Sync Run ID/status and aggregate consumed resource/attempt/retry/byte counts;
5. every request attempt, including kind, attempt number, endpoint, timing,
   terminal status, HTTP status, received bytes, safe error code, consumption
   state, and socket evidence;
6. every authoritative artifact and its exact attempt, checksum, MIME, byte
   count, source identity, storage reference, acquisition/publication time,
   synthetic status, and license/retention reference;
7. every manifest and its batch/manifest checksums, adapter/parser/schema
   versions, record count, warnings, and source time;
8. committed DocumentVersion and citation IDs with exact checksum and parser/
   sanitizer lineage;
9. DQ issue codes, severities, statuses, safe details, terminal validation ID,
   terminal status, terminal stage, warning codes, and stable stop reason;
10. explicit absence of contact value, User-Agent, credential hash, header dump,
    body bytes, cookies, or authorization headers.

Failed resources have null artifact/manifest/document/citation fields but retain
attempt, consumption, safe response, and terminal failure lineage. A missing
required join, count mismatch, checksum mismatch, duplicate terminal, or
ambiguous approval produces a deterministic audit-integrity failure; it cannot
return a partial success view.

### 5.6 Terminal idempotency contract

1. Terminal persistence locks the authoritative Sync Run row.
2. It queries the checksummed `DATA_QUALITY_STOP` event for that Sync Run before
   inserting DQ issues, a live-validation run, or a terminal event.
3. No existing terminal produces exactly one live-validation run, its DQ issues,
   and one terminal audit event in the same short transaction.
4. An existing byte-for-byte equivalent terminal checksum returns the existing
   IDs and inserts nothing.
5. A different terminal checksum, status, issue set, object ID, or lineage for
   the same Sync Run fails with a terminal-conflict error.
6. Concurrent terminal calls serialize on the Sync Run lock and commit exactly
   one authoritative terminal.
7. The terminal audit summary includes the preallocated live-validation-run ID,
   approval ID, all terminal lineage IDs, status, stage, warning codes, and stop
   reason. The projection validates each ID against committed rows.

Schema change: **NO**.

## 6. GBR-04 — exact three-resource plan and full orchestration

### 6.1 Repository investigation

The Preparation Runbook explicitly excludes Company Facts and defines:

1. SEC submissions JSON for filing discovery and candidate/as-of verification;
2. the exact filing index for primary-document identity verification;
3. the exact primary filing document for the controlled raw artifact.

Current `SEC_ENDPOINT_POLICIES` contains `SEC_SUBMISSIONS_JSON`,
`SEC_COMPANY_FACTS_JSON`, and `SEC_FILING_DOCUMENT`. The filing-index schema and
`SecArtifactKind.FILING_INDEX` already exist. `SecEdgarAdapter` permits
`FILING_INDEX` through `SEC_FILING_DOCUMENT`. Therefore an exact filing index is
represented as a second checksum-bound `SEC_FILING_DOCUMENT` resource with its
own safe index filename and `FILING_INDEX` artifact kind. No endpoint or schema
addition is required.

Current transport fixtures instead use Company Facts, and
`SecGateBPilotApplication.execute_authorized` executes one caller-selected
`slice_id`, settles one artifact, runs DQ, and stops. That is a per-slice harness,
not the approved full Gate B pilot.

### 6.2 Alternatives

#### Alternative A — preserve the Preparation Runbook

Use submissions, exact filing index, and exact primary filing document. This is
the minimum resource set that proves filing discovery, primary-document identity,
and authoritative content while remaining within three resources.

#### Alternative B — retain Company Facts

Company Facts does not prove the selected filing's primary-document identity and
was explicitly excluded from the Gate B grant. Rejected.

#### Alternative C — submissions and primary document only

This reduces requests but removes the independent filing-index identity check
required by the approved plan. Rejected.

### 6.3 Approved recommendation

Adopt Alternative A. `SecGateBPilotApplication` owns full-plan orchestration.
The public execution method accepts the immutable authorized plan and no
caller-selected slice. A private resource executor can reuse the existing
single-slice transport, validation, and settlement components.

### 6.4 Frozen exact plan

| Ordinal | Slice identity | Endpoint policy | Artifact kind | Dependency | Maximum bytes |
|---:|---|---|---|---|---:|
| 0 | `SEC_SUBMISSIONS` | `SEC_SUBMISSIONS_JSON` | `SUBMISSIONS_METADATA` | none | 2 MiB |
| 1 | `SEC_FILING_INDEX` | `SEC_FILING_DOCUMENT` with exact frozen index filename | `FILING_INDEX` | submissions identity matches frozen CIK/accession/form/as-of | 1 MiB |
| 2 | `SEC_PRIMARY_DOCUMENT` | `SEC_FILING_DOCUMENT` with exact frozen primary filename | `PRIMARY_FILING_DOCUMENT` | index identifies the exact primary filename and filing identity | 20 MiB |

Company Facts is **OUT_OF_SCOPE** and its presence causes plan rejection before
credential resolution, DNS, or send.

Additional frozen semantics:

1. `resource_count` is exactly 3; unique ordinals are exactly `(0, 1, 2)`.
2. All resources share one provider, candidate, CIK, accession, form, as-of,
   plan ID/checksum, grant, execution approval, authorization, and Sync Run.
3. Resource order is mandatory. A later resource cannot execute before every
   predecessor commits validated authoritative lineage.
4. Resource budget is exactly 3. Attempt budget is at most 4 across the plan.
   Retry budget is at most 1 across the plan. No counter resets by resource.
5. Approval consumption occurs once with the initial submissions reservation.
   Resources 2 and 3 and the one permitted retry belong to that same committed
   execution.
6. Each response receives resource-local transport, identity, MIME, size,
   checksum, temporal, parse, blob, artifact, manifest, and attempt settlement
   validation.
7. Submissions and filing-index outputs are metadata-only. Only the exact primary
   filing document proceeds through DocumentVersion, parse/chunk, and Citation.
8. Aggregate Data Quality runs exactly once after all three resources commit,
   the index verifies the primary document, and primary-document citation
   lineage exists.
9. Resource 1 failure stops before resources 2 and 3. Resource 2 failure stops
   before resource 3. Resource 3 failure stops before document/citation and
   aggregate DQ success evaluation.
10. Every committed earlier artifact and failure attempt remains auditable after
    a later resource failure.
11. A partial three-resource set cannot produce `LIVE_VALIDATION_PASS` or a
    `PASSED` terminal. It ends `BLOCKED` or `FAILED` according to the existing
    typed failure classification. Gate B exposes no successful `PARTIAL` result.
12. The terminal failure is committed once and the pilot stops. No Snapshot,
    Research Request, Agent Run, Evidence, Claim, Report, publication, or Stage
    11 path is invoked.

Schema change: **NO**.

## 7. Cross-contract architecture

```text
operator authorization input
        ↓
non-executable GateBAuthorizationEnvelope
        ↓
deterministic persisted-record validation
        ↓
authoritative execution-start transaction
  lock approval → lock grant → lock Sync Run
  approval VALID → CONSUMED
  append grant CONSUME
  reserve request capacity
  insert initial PENDING attempt
        ↓ COMMIT
AuthorizedGateBExecution + initial SecAttemptPermit
        ↓
immutable exact three-resource plan
        ↓
SEC_SUBMISSIONS
        ↓ committed attempt/artifact/manifest
SEC_FILING_INDEX
        ↓ committed attempt/artifact/manifest
SEC_PRIMARY_DOCUMENT
        ↓ committed attempt/artifact/manifest
DocumentVersion → parse/chunk → Citation
        ↓
aggregate Data Quality
        ↓
idempotent terminal transaction under Sync Run lock
        ↓
complete secret-free GateBAuditView
        ↓
STOP
```

One approval authorizes one Gate B run. One run owns one immutable plan and one
shared resource/attempt/retry budget. Every reservation remains permanent audit
lineage. The operational audit reconstructs every resource and exactly one
terminal outcome.

## 8. Corrective RED inventory

The current highest identifier is RED-049. The following IDs are proposals and
become authoritative only after human approval of this document.

| Proposed ID | Behavior | Level | Expected initial RED reason | Production owner |
|---|---|---|---|---|
| RED-050 | Caller state removed; authoritative execution start consumes approval and returns capability plus initial permit | unit | gate accepts `approval_consumed` and returns capability before persistence | `gate_b_authorization.py`, live-evidence repository |
| RED-051 | Two concurrent starts with one approval commit exactly one execution | PostgreSQL | no approval-lock/update in reservation transaction | `db/repositories/live_evidence.py` |
| RED-052 | Initial reservation failure rolls back approval/grant event/consumption/attempt together; post-commit crash stays consumed | PostgreSQL | approval and reservation are not one transaction | live-evidence repository |
| RED-053 | `ABANDONED` counts against grant, attempt, and retry budgets | unit + PostgreSQL | grant query excludes `ABANDONED` | `reserve_consumption`, reservation port |
| RED-054 | Abandoned execution cannot restart and no implicit reconciliation/refund API exists | unit | current tests assert settlement events only | authorization/pilot composition |
| RED-055 | Operational audit projects all three resources, attempts, artifacts, ingestion, citations, DQ, budgets, and stop reason without secret data | unit + PostgreSQL | current view is a one-row subset | `GateBAuditView`, `get_gate_b_audit_view` |
| RED-056 | Repeated and concurrent terminal commits produce one identical terminal; conflicting replay fails | PostgreSQL | terminal store always inserts | `SqlAlchemySecTerminalStore` |
| RED-057 | Exact ordered plan is submissions/index/primary; Company Facts and non-exact plans fail before send | unit | current fixture accepts Company Facts | `sec_edgar/policy.py` |
| RED-058 | Full orchestrator executes exactly three resources in order under one authorization and shared budgets | unit | pilot accepts one caller-selected slice | `SecGateBPilotApplication` |
| RED-059 | Failure at each ordinal stops before the next resource and retains prior authoritative lineage | unit + PostgreSQL | no whole-plan failure orchestration | pilot and settlement repositories |
| RED-060 | Aggregate DQ commits only after all resources and primary citation; partial set cannot pass or invoke downstream | unit + PostgreSQL | current DQ runs after one slice | pilot, document bridge, terminal store |
| RED-061 | Production-composed offline Gate B completes the exact three-resource flow and returns one complete audit view | integration | default composition remains single-slice/injected | `cli_live.py` production factory and existing ports |

No corrective test is created by this design phase.

## 9. Production owner map

| Corrective behavior | Existing owner to extend |
|---|---|
| envelope/persisted validation without caller consumption truth | `domain/live_evidence/gate_b_authorization.py` |
| atomic approval/grant/initial-attempt start | `db/repositories/live_evidence.py` |
| ABANDONED accounting | `reserve_consumption` and `SqlAlchemySecAttemptReservationPort` |
| exact three-resource binding | `providers/sec_edgar/policy.py` using `SEC_ENDPOINT_POLICIES` |
| ordered whole-plan execution | `domain/live_evidence/gate_b_pilot.py` |
| per-resource response/artifact settlement | existing pilot validation and `SecArtifactSettlementService` |
| complete audit projection and terminal idempotency | `GateBAuditView`, `SqlAlchemySecTerminalStore`, `get_gate_b_audit_view` |
| explicit authorized production composition | `cli_live.py` and existing injected ports |

No broad provider service, parallel authorization state machine, or new audit
system is approved.

## 10. Schema verdict

```text
GBR-01 schema change: NO
GBR-02 schema change: NO
GBR-03 schema change: NO
GBR-04 schema change: NO

SCHEMA_CHANGE_REQUIRED: NO
```

Existing approval state, grant events, consumption rows, request attempts, Sync
Run, artifacts, manifests, document/citation lineage, DQ issues, live-validation
runs, and checksummed audit events are sufficient. Required changes are
transaction ownership, repository methods, projection composition, safe audit
summaries, and orchestration.

## 11. Remaining risks

- The exact filing, accession, index filename, primary filename, as-of, storage
  decision, and plan checksum remain operationally unfrozen.
- Fresh SEC policy verification and contact-reference configuration remain future
  authorization prerequisites.
- The development stack remains unmerged into main.
- PostgreSQL corrective REDs require the documented loopback test database.
- No corrective implementation is approved until human review accepts all four
  frozen contracts and the proposed RED inventory.

No unresolved architecture blocker remains inside this corrective design.

## 12. Entry criteria for corrective TDD

Corrective RED work starts only after all conditions below are met:

1. Human review explicitly approves GBR-01, GBR-02, GBR-03, and GBR-04.
2. Human review approves or renumbers RED-050 through RED-061.
3. The branch and baseline commit for the corrective RED slice are frozen.
4. The loopback-only PostgreSQL test database is reachable for RED-051, RED-052,
   RED-053, RED-055, RED-056, RED-059, and RED-060.
5. The implementation boundary remains offline: no SEC request, DNS, real
   credential resolution, Gate B authorization/execution, or Stage 11 work.
6. Tests are written and observed RED before production correction begins.

Until that approval occurs:

```text
CORRECTIVE_RED_PHASE_READY_TO_START: NO
```
