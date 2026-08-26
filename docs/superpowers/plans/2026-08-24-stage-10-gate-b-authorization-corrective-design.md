# Stage 10 Gate B Authorization Corrective Design

**Status:** Human decisions ratified; Slice A planning and RED establishment are approved. Production implementation, Slice B/C work, authorization materialization, and Gate B execution are not authorized.

**Repository baseline:** `main` at `1de390731960548ba2f31808dbb090b60bada6a0`

**Goal:** Correct the three Phase 7B-3A review findings without changing the frozen operational request or plan: bind authorization to the exact frozen request, add one atomic production authorization-materialization owner, and make SyncRun creation part of the atomic authorization-to-initial-permit boundary.

**Architecture:** A versioned Gate B authorization contract binds the immutable request and plan directly by ID and checksum, then re-reads and validates all transitive governance records. A dedicated transaction-owning materialization application persists the grant, lifecycle events, and approval together. The existing PostgreSQL SEC execution-start owner is extended to create the SyncRun inside the same short transaction that consumes the approval and grant and reserves the initial attempt.

**Tech stack:** Python 3.12.13, Pydantic frozen contracts, SQLAlchemy 2, PostgreSQL 17.10, Alembic, pytest, Ruff, and strict mypy.

## Global constraints

- The operational freeze records and checksums are immutable inputs; this design creates no replacement request or plan.
- The design creates no authorization, approval, SyncRun, attempt, permit, credential resolution, DNS, HTTP, artifact, terminal state, or Stage 11 state.
- Raw contact and credential values never enter an envelope, grant, approval, checksum, result, log, exception, or audit record.
- Generic `ProviderSyncRequest` and Provider Policy `max_attempts` remain `3`; Gate B physical capacity remains `4`; the plan-global retry limit remains `1`.
- Gate B remains unauthorized and unexecuted. Slice A RED establishment is approved; production implementation still requires the next independent human review gate.

---

## Human Decisions — Approved 2026-08-24

The human reviewer approved the previously open governance decisions for the
Gate B authorization correction. These decisions authorize ratification,
Slice A planning, and Slice A RED establishment only. They do not authorize
production implementation, migration execution, authorization materialization,
Gate B execution, network access, credential resolution, or Stage 11.

| Decision | Approved authority |
|---|---|
| Authorization V2 migration | Direction approved for a later `0014 Gate B Authorization V2` revision. Status remains `DESIGN_APPROVED / NOT_IMPLEMENTED`. The revision must not mutate or replace Operational Freeze records. |
| Approval Registry | An immutable, versioned production code manifest. No pilot-only registry table and no mutable environment/config authority. Status remains `DESIGN_APPROVED / NOT_IMPLEMENTED`. |
| Registry identity | `registry_id = SEC_GATE_B_SINGLE_USE_AUTHORIZATION`; `registry_version = 1.0.0`. |
| Registry checksum | Canonically derived from the final immutable production manifest; never manually invented or hard-coded as a fabricated value. |
| Authorization contract | `2.0.0`; V2 is the only production Gate B executable authorization contract after correction. |
| Approval time | After explicit human authorization, the production application derives one authoritative aware UTC instant `T`. Grant, envelope, and approval `approved_at` all equal `T`. |
| Lifetimes | Grant expiry is at most `T + 30 minutes`; envelope expiry is `T + 10 minutes`; approval expiry is `T + 10 minutes`; approval and envelope expiry must not exceed grant expiry. |
| Retention | Derive `retention_deadline` from the existing approved authorization retention contract using `T`; do not create a competing retention rule. |
| Operator alias | `approved_by = primary-human-operator`, an explicit non-sensitive pilot alias. It must not be derived from an OS username, email, real name, machine name, environment username, or account login. |
| V1 policy | V1 remains readable but is non-executable for production Gate B. No implicit V1-to-V2 upgrade is permitted. V1 checksum semantics remain unchanged. |
| Operational Freeze | Immutable. The accepted request, plan, governance records, versions, and checksums must not be rewritten or replaced. |

The approved lowercase, hyphenated V2 pilot operator alias does not satisfy the
existing V1 actor regex. That is an explicit V2 persistence-contract concern
for Slice B; V1 validation must not be silently broadened during Slice A.

The immutable manifest must represent at least:

```text
purpose: SEC Gate B controlled live validation
authorization_contract: 2.0.0
single_use: true
grant_max_lifetime: 30 minutes
approval_max_lifetime: 10 minutes
envelope_max_lifetime: 10 minutes
frozen_request_binding_required: true
atomic_execution_start_required: true
plan_wide_physical_attempts: 4
plan_wide_retry_count: 1
```

The final exact manifest structure and canonicalization belong to Slice B.

## 1. Phase 7B-3A review findings

| Finding | Confirmed production behavior | Security consequence |
|---|---|---|
| IMPORTANT-01 | `ProductionAuthorizationGate.authorize()` receives an envelope, grant, approval, plan, generic execution scope, and contact reference, but no `ProviderSyncRequestRecord`. The envelope, validation result, and executable capability contain no request identity. | A plan object with the approved plan ID/checksum but a substituted `sync_request_id` can cross the gate. Request checksum, temporal cutoff, mode, credential, and license freeze cannot be authoritatively checked. |
| IMPORTANT-02 | `ProductionAuthorizationApplication.create()` creates only a non-executable envelope. `plan()`, `show()`, `activate()`, and `revoke()` all raise `LIVE_AUTHORIZATION_OPERATION_NOT_CONFIGURED`. Domain constructors exist, but no production transaction persists a grant, its lifecycle, and an approval. | A human decision cannot be materialized through a production-owned atomic boundary. |
| IMPORTANT-03 | `SqlAlchemyProviderSyncRepository.create_run()` is transaction-neutral, but the production SEC start port is constructed with an already persisted `sync_run_id`. `start_execution()` opens a different transaction and locks that pre-existing run. | A committed SyncRun can exist without authorization consumption or an initial permit reservation. |

Existing behavior that remains authoritative: single-use approval consumption, replay blocking, plan checksum and security binding, four Gate B physical attempts, one retry, generic attempt maximum three, 429 terminal behavior, zero redirects, and the secret-free contact boundary.

## 2. Current production data flow and loss points

```text
ProviderSyncRequestRecord
  id, request_checksum, provider/capability/policy/license/credential/security,
  research_as_of_time, execution_mode, exact scope, generic budget
        |
        | ProviderSyncPlanRecord.sync_request_id (FK in PostgreSQL)
        v
ProviderSyncPlanRecord
  id, sync_request_id, plan_checksum, three slices
        |
        | LOSS 1: GateBAuthorizationCreateRequest carries only plan_id/checksum
        v
GateBAuthorizationEnvelope
  provider/candidate, plan_id/checksum, finite transport/budget scope,
  grant reference, approval window
        |
        | LiveAuthorizationGrantRecord contains governance/candidate fields,
        | but no sync_request_id, request_checksum, research_as_of_time, or mode
        v
LiveExecutionApprovalRecord
  authorization checksum and plan ID/checksum
        |
        | LOSS 2: ProductionAuthorizationGate receives no request and does not
        | compare ProviderSyncPlanRecord.sync_request_id to an authorized request
        v
GateBAuthorizationValidation
  grant/approval/plan/provider/security/credential identities only
        |
        | start_execution commits approval/grant/attempt state
        v
AuthorizedGateBExecution
  same fields as validation; still no frozen request authority
```

### 2.1 Exact source evidence

| Evidence | File and symbol | Relevant fields or behavior |
|---|---|---|
| Frozen request authority | `src/stock_research_agent/domain/providers/sync.py::ProviderSyncRequestWrite/Record` | `id`, `request_checksum`, provider definition, capability, policy, license, credential, security, `research_as_of_time`, `execution_mode`, scope, and budget |
| Request-to-plan edge | `src/stock_research_agent/domain/providers/sync.py::ProviderSyncPlanWrite/Record` | `sync_request_id`, `plan_checksum`; PostgreSQL FK in `db/models/providers.py::ProviderSyncPlan` |
| Missing request in envelope | `src/stock_research_agent/domain/live_evidence/gate_b_authorization.py::GateBAuthorizationCreateRequest` | Has `plan_id` and `plan_checksum`; has no request ID or checksum |
| Missing request in grant | `src/stock_research_agent/domain/live_evidence/schemas.py::LiveAuthorizationGrantWrite` | Has provider/governance/candidate fields; has no request ID/checksum, research cutoff, or execution mode |
| Missing request at gate | `gate_b_authorization.py::ProductionAuthorizationGate.authorize` | No request argument; `_require_authoritative_binding` never reads `plan.sync_request_id` |
| Missing request downstream | `gate_b_authorization.py::GateBAuthorizationValidation` and `AuthorizedGateBExecution` | No request ID/checksum, policy/license identity, research cutoff, or mode |
| Materialization block | `gate_b_authorization.py::ProductionAuthorizationApplication` | Only `create()` is configured; persistence operations raise `LIVE_AUTHORIZATION_OPERATION_NOT_CONFIGURED` |
| Separate run creation | `src/stock_research_agent/db/repositories/providers.py::SqlAlchemyProviderSyncRepository.create_run` | Uses caller Session, flushes, and never commits |
| Existing start transaction | `src/stock_research_agent/db/repositories/live_evidence.py::SqlAlchemySecAttemptReservationPort.start_execution` | Opens its own Session/transaction and requires constructor `sync_run_id` |

The first authority loss occurs when `GateBAuthorizationCreateRequest` omits the frozen request. The exploitable acceptance point is `_require_authoritative_binding()`, which validates plan ID/checksum and slice count but never validates `plan.sync_request_id` against a request. The loss is then propagated into both capability types.

## 3. Current persistence and transaction architecture

### 3.1 Authorization persistence primitives

| Primitive | Present behavior | Gap |
|---|---|---|
| `LiveAuthorizationGrantWrite/Record` | Fully validates finite provider, governance, candidate, budget, retention, approver, and lifetime metadata. | No Gate B request contract version or frozen request binding. |
| `canonical_grant()` / `grant_checksum()` | SHA-256 over canonical JSON with schema marker `live-authorization-grant-v1`. | V1 cannot represent the missing request authority. |
| `AuthorizationStateMachine` | Append-only logical transitions `DRAFT -> APPROVED -> ACTIVE -> CONSUMED` and terminal immutability. | No production repository creates the initial lifecycle atomically. |
| `ExecutionApprovalService.create/validate` | Deterministic approval signature, expiry, checksum, and replay checks. | The database cannot reconstruct all signed fields. |
| `LiveAuthorizationGrant` table | Unique canonical checksum, finite request/byte columns, JSON `scope`, expiry, and status. | No production mapper; current scope contract is not versioned as Gate B v2. |
| `LiveAuthorizationEvent` table | Unique `(authorization_id, sequence)`, FK to grant, append-only trigger. | No production creation repository. |
| `LiveExecutionApproval` table | FK to grant, unique signature, plan ID/checksum, state, expiry. | Missing signed authorization checksum, registry metadata, approver, approved time, and contract version; plan ID has no FK. |

`AUTH_MATERIALIZATION_PRIMITIVES_COMPLETE: NO`. Domain validation and lifecycle primitives are reusable, but the production persistence surface and approval storage are incomplete.

### 3.2 Current execution-start ordering

The current operational ordering is:

```text
caller transaction
  -> SqlAlchemyProviderSyncRepository.create_run()
  -> INSERT/flush ProviderSyncRun
  -> caller commit

later, separate start_execution transaction
  -> lock LiveExecutionApproval
  -> lock LiveAuthorizationGrant
  -> lock existing ProviderSyncRun
  -> read ProviderSyncPlan checksum
  -> Approval state = CONSUMED
  -> append grant CONSUME
  -> reserve LiveAuthorizationConsumption
  -> lock Run + Plan for resource/budget validation
  -> insert initial PENDING ProviderRequestAttempt
  -> COMMIT
  -> construct AuthorizedGateBExecution and SecAttemptPermit
```

`create_run()` can safely run inside any caller-owned SQLAlchemy Session because it only flushes. It cannot currently join `start_execution()` because the latter creates its own Session/transaction and accepts only an existing run ID. The obstacle is API and transaction ownership, not an internal commit.

## 4. Model, identity, and locking inventory

| Record/type | Primary or natural identity | Checksum / mutable fields | FK and uniqueness | Locking, replay, idempotency |
|---|---|---|---|---|
| `ProviderSyncRequestRecord` | PK `id`; natural replay identity `idempotency_key` | Immutable `request_checksum`; record is frozen in domain | FKs to definition, capability, policy, license, credential, security; unique idempotency key | `create_request()` reuses exact checksum and conflicts on drift; no update path |
| `ProviderSyncPlanRecord` | PK `id`; natural identity `(sync_request_id, plan_checksum)` | Immutable `plan_checksum`; frozen domain record | FK request; unique request/checksum | `add_plan()` reuses exact identity; no update path |
| `LiveAuthorizationGrantRecord` | PK `id`; natural exact identity `canonical_checksum` | Event-derived lifecycle; table also has mutable `status` | Unique canonical checksum | Grant is locked for consumption; events define replay state |
| `LiveAuthorizationEvent` | PK `id`; `(authorization_id, sequence)` | Append-only type/reason | FK grant; unique sequence; immutable trigger | Event replay is authoritative lifecycle; duplicate sequence conflicts |
| `LiveExecutionApprovalRecord` | PK `id`; exact payload identity `approval_signature` | Mutable state `VALID -> CONSUMED`; expiry | FK grant; unique signature; currently no plan FK | Row lock serializes same-approval starts; signature validates immutable payload only when full payload is available |
| `ProviderSyncRunRecord` | PK `id`; natural identity `(sync_request_id, sync_plan_id)` | Mutable status, counters, times, lease, warnings | FKs request/plan/definition/capability; unique request/plan | `create_run()` reuses exact provider scope; current start locks an existing row |
| `ProviderRequestAttemptRecord` | PK `id` = request-attempt identity | Mutable terminal result after initial PENDING; attempt number permanent | FK run; unique `(run, slice, attempt_number)` | Run/plan lock plus uniqueness prevents duplicate physical identity |
| `SecAttemptPermit` | In-memory immutable `request_attempt_id` plus authorization/plan/resource/attempt scope | No persisted mutable state | Corresponding consumption and PENDING attempt are persistence authority | Created only after reservation commit; wrong scope is rejected |
| `GateBAuthorizationValidation` | In-memory grant + approval + plan identity | Non-executable and immutable | None | Produced by read-only gate validation |
| `AuthorizedGateBExecution` | In-memory committed grant + approval + plan identity | Immutable | None | Produced after execution-start commit; replay is blocked by persisted approval/grant state |

Current schema cannot persist and reconstitute the complete signed approval contract. That is a schema inability, not merely a missing mapper.

## 5. Corrected frozen-request binding contract

The corrected contract uses direct binding for the four immutable roots and authoritative readback for every transitive value.

### 5.1 Directly bound roots

The Gate B v2 envelope and v2 grant carry:

```text
sync_request_id
request_checksum
plan_id
plan_checksum
```

The gate receives authoritative `ProviderSyncRequestRecord` and `ProviderSyncPlanRecord` values loaded by exact IDs. It requires:

```text
envelope.sync_request_id == grant.sync_request_id == request.id
envelope.request_checksum == grant.request_checksum == request.request_checksum
envelope.plan_id == approval.sync_plan_id == plan.id
envelope.plan_checksum == approval.plan_checksum == plan.plan_checksum
plan.sync_request_id == request.id
```

Any mismatch returns a stable secret-free failure before a validation or executable capability is returned.

### 5.2 Transitively validated authority

| Frozen property | Authoritative validation |
|---|---|
| Provider Definition | Request ID equals grant ID; authoritative Definition record version/checksum equals grant. |
| Provider Capability | Request ID equals grant ID; authoritative Capability record version/checksum equals grant. |
| Provider Policy | Request `policy_id` equals grant policy ID; authoritative policy version/checksum equals grant. |
| Credential Reference | Request credential ID equals both grant credential and user-agent reference IDs for this SEC contract; authoritative metadata record is validated. |
| Source License Policy | Request license ID equals grant license ID; authoritative license version/checksum equals grant. |
| Security | Request security ID, grant security/issuer/CIK, envelope candidate, and exact request scope CIK must agree. |
| `research_as_of_time` | V2 grant carries the exact value; it equals request readback. No wall clock substitution is allowed. |
| `execution_mode` | V2 grant requires `LIVE_VALIDATION`; it equals request readback. |

Provider/capability/policy/license/credential records are inputs to the production authorization application or are loaded through its read-only authority port. The envelope does not duplicate all governance UUIDs: it binds the request root, while the v2 grant records the approved governance scope and the gate proves the join.

### 5.3 Request checksum strategy

| Option | Tamper/replay behavior | Schema and duplication | Decision |
|---|---|---|---|
| A: direct checksum only | Detects mismatch among supplied objects but can still trust a forged request object. | Simple; no authoritative readback. | Rejected. |
| B: ID plus readback only | Prevents object substitution, but the human authorization payload does not independently record the approved checksum. | Least duplication. | Insufficient for an auditable human grant. |
| C: direct checksum plus readback | Human authorization records the exact immutable checksum; the gate independently loads the request and verifies the stored value and canonical Gate B request identity. | Two equal values with an explicit equality invariant. | **Selected.** |

The request record is reconstructed as `GateBSyncRequestIdentity` using contract version `1.0.0`, then `build_gate_b_sync_request()` is used to verify both `request_checksum` and `idempotency_key`. The current public builder already revalidates copied Pydantic state.

## 6. Request-to-plan invariant and ownership

The authoritative invariant is:

```text
ProviderSyncPlanRecord.sync_request_id == ProviderSyncRequestRecord.id
```

Primary owner: the production authorization application's frozen-authority loader. It loads the request by the envelope/grant request ID and the plan by the envelope/approval plan ID, then rejects a mismatched join before constructing v2 grant/approval records or calling the gate.

Defense in depth:

1. `ProductionAuthorizationGate.authorize()` repeats the relationship check over freshly loaded records before returning `GateBAuthorizationValidation`.
2. The PostgreSQL execution-start transaction re-reads and locks both persisted rows and repeats the check before creating a SyncRun.

The provider repository needs explicit read methods `get_request(request_id, for_update=False)` and `get_plan(plan_id, for_update=False)`. These return typed records and never accept raw URL or mutable plan material.

## 7. Gate B v2 authorization structures

### 7.1 `GateBAuthorizationEnvelopeV2`

The production v2 envelope is non-executable and contains:

| Category | Fields |
|---|---|
| Contract | `contract_version = "2.0.0"` |
| Frozen roots | `sync_request_id`, `request_checksum`, `plan_id`, `plan_checksum` |
| Human-authorized finite scope | existing provider, candidate, exact hosts/paths, three resources, four physical attempts, one retry, zero redirects, concurrency one, `10/30/120` timeouts |
| Credential role metadata | existing declared contact reference name only; no value |
| Lifecycle reference | `grant_id`, `single_use`, `approved_at`, `expires_at` |

### 7.2 `GateBLiveAuthorizationGrantWriteV2/RecordV2`

V2 preserves every existing grant field and adds:

```text
contract_version = "2.0.0"
sync_request_id
request_checksum
research_as_of_time
execution_mode = LIVE_VALIDATION
```

The existing direct credential, user-agent, license, provider-policy, security, provider, capability, budget, retention, and operator fields remain. The v2 record is serialized into the existing grant `scope` JSON and crosschecked against the explicit request-limit, byte-limit, checksum, expiry, and status columns.

### 7.3 Validation and execution capability

`GateBAuthorizationValidationV2` and `AuthorizedGateBExecutionV2` add the safe identities needed for authoritative revalidation:

```text
sync_request_id
request_checksum
provider_definition_id
provider_capability_id
provider_policy_id
license_policy_id
research_as_of_time
execution_mode
```

They retain the current grant, approval, plan, provider, security, issuer, CIK, credential, and user-agent reference fields. Neither type contains credential/contact material. The validation type remains non-executable; only the committed start transaction converts it to the executable type.

## 8. Grant and approval checksum/version strategy

### 8.1 Grant

- V1 remains identified by canonical schema marker `live-authorization-grant-v1`.
- Gate B production uses a separate v2 contract and marker `live-authorization-grant-v2`.
- V2 canonical JSON includes the four added fields and all existing grant fields.
- `grant_checksum()` dispatches by the explicit contract type/version; it never guesses a version from missing optional values.
- A V1 grant may remain readable for historical/offline uses but cannot authorize production Gate B execution.

### 8.2 Approval

- Add `contract_version = "2.0.0"` to the Gate B execution-approval payload.
- Keep SHA-256 over sorted canonical JSON; the algorithm does not change.
- The signature changes because the payload explicitly contains the v2 contract version and the v2 grant checksum.
- V1/missing-version approvals remain readable but are non-executable for Gate B.

This is a semantic contract-version change, not a silent reinterpretation of existing checksums.

## 9. Production authorization materialization owner

### 9.1 Proposed application

Add `ProductionGateBAuthorizationMaterializationApplication` to `src/stock_research_agent/domain/live_evidence/gate_b_authorization.py`. It consumes a `GateBAuthorizationMaterializationTransactionFactory` protocol and a safe `GateBAuthorizationMaterializationRequest`.

The request contains exact frozen request/plan IDs and checksums plus human-supplied approval metadata. It contains no raw credential or contact material.

The application flow is:

```text
begin caller-owned materialization transaction
  -> read exact Request, Plan, Definition, Capability, Policy,
     CredentialReference, LicensePolicy, Security/Issuer authority
  -> verify request checksum/idempotency and request-to-plan relation
  -> validate the exact operational freeze IDs/checksums
  -> validate approved_by, approval registry reference, and time window
  -> construct GateBAuthorizationEnvelopeV2
  -> construct GateBLiveAuthorizationGrantWriteV2 and canonical checksum
  -> construct LiveExecutionApprovalWriteV2 and deterministic signature
  -> lookup exact grant checksum and registry identity/signature
  -> insert/reuse exact grant
  -> append APPROVE and ACTIVATE events when newly created
  -> insert/reuse exact VALID approval
  -> authoritative in-transaction readback and signature/checksum replay
commit
  -> return non-executable GateBAuthorizationMaterializationResult
```

The result contains only request/plan IDs and checksums, grant ID/checksum/state, approval ID/signature/state, approved/expiry times, and `CREATED` or `REUSED`. It contains no ORM objects, Session, mutable plan, capability, permit, URL, or secret.

### 9.2 Production repository/transaction adapter

Add `SqlAlchemyGateBAuthorizationMaterializationTransaction` and its factory in `src/stock_research_agent/db/repositories/live_evidence.py`. One `with session_factory() as session, session.begin():` owns all reads, inserts, lifecycle rows, readback, and commit. Existing `SqlAlchemyProviderSyncRepository` and governance repositories are instantiated with that same Session. No repository method commits internally.

### 9.3 Atomicity and idempotency

- Grant, `APPROVE`, `ACTIVATE`, and approval are all committed or all rolled back.
- The grant exact identity is its v2 canonical checksum.
- The approval exact identity is its v2 approval signature.
- The authoritative human-decision identity is the tuple `(approval_registry_id, approval_registry_version, approval_registry_checksum)`.
- Equivalent replay requires all three identities and all persisted fields/events to match; it returns the same IDs and inserts nothing.
- A partial match, lifecycle divergence, same registry identity with different authorization/plan/times, or same checksum with different payload fails closed.
- A consumed/revoked/expired exact replay returns the existing non-executable state; it never creates a replacement approval.
- Materialization creates no SyncRun, consumption, attempt, permit, or network-capable result.

`ATOMIC_AUTHORIZATION_MATERIALIZATION: YES` in the target design.

## 10. Approval persistence schema gap and migration decision

The existing `live_execution_approvals` table cannot reconstruct the signed `LiveExecutionApprovalWrite` because it does not persist:

```text
authorization_checksum
approval_registry_id
approval_registry_version
approval_registry_checksum
approved_by
approved_at
contract_version
```

The approved signature cannot be independently replayed from authoritative database state. A production materializer cannot satisfy authoritative readback without schema support.

The required future Alembic revision must:

1. add nullable columns for the seven fields above so historical V1 rows remain readable but non-executable;
2. add lowercase SHA-256 checks for authorization and registry checksums;
3. add format checks matching the domain actor, capability, and semantic-version contracts;
4. add a FK from `live_execution_approvals.plan_id` to `provider_sync_plans.id` with `ON DELETE RESTRICT`;
5. add a uniqueness constraint over `(approval_registry_id, approval_registry_version, approval_registry_checksum)` for non-null v2 rows;
6. require every newly inserted v2 approval to have the complete field set through a check constraint, while allowing all-null legacy metadata;
7. update the ORM model and migration parity fixtures; and
8. leave operational V1 rows untouched. The accepted operational database currently has zero grants and zero approvals.

The existing grant `scope` JSON can carry the complete v2 grant payload. No new grant table or replacement freeze record is required. The materializer must bound the JSON object and revalidate it into the v2 Pydantic contract on every read.

```text
DATABASE_MIGRATION_REQUIRED: YES
```

## 11. Human authorization metadata classification

| Field | Classification | Exact contract |
|---|---|---|
| `approved_by` | `HUMAN_APPROVED_CONSTANT` | Exact non-sensitive V2 pilot alias `primary-human-operator`; never inferred from local identity. |
| Grant `approved_at` | `SYSTEM_DERIVED_AFTER_EXPLICIT_HUMAN_APPROVAL` | One authoritative aware UTC instant `T` derived by the production application after the explicit human authorization action. |
| Envelope `approved_at` | `SYSTEM_DERIVED_AFTER_EXPLICIT_HUMAN_APPROVAL` | Exactly `T`; no independent clock drift. |
| Approval `approved_at` | `SYSTEM_DERIVED_AFTER_EXPLICIT_HUMAN_APPROVAL` | Exactly `T`. |
| Grant `expires_at` | `SYSTEM_DERIVED_AFTER_EXPLICIT_HUMAN_APPROVAL` | At most `T + 30 minutes`. |
| Envelope `expires_at` | `SYSTEM_DERIVED_AFTER_EXPLICIT_HUMAN_APPROVAL` | Exactly `T + 10 minutes` and no later than grant expiry. |
| Approval `expires_at` | `SYSTEM_DERIVED_AFTER_EXPLICIT_HUMAN_APPROVAL` | Exactly `T + 10 minutes` and no later than grant expiry. |
| `retention_deadline` | `SYSTEM_DERIVED` | Grant approved instant plus the frozen license policy's 30-day retention period. |
| Registry ID/version/checksum | `HUMAN_APPROVED_AUTHORITY` | Immutable production code manifest; ID `SEC_GATE_B_SINGLE_USE_AUTHORIZATION`, version `1.0.0`, checksum canonically derived from the final manifest. |

Time invariants:

```text
grant.approved_at == envelope.approved_at == approval.approved_at
approval.expires_at == envelope.expires_at <= grant.expires_at
0 < approval lifetime <= 10 minutes
0 < grant lifetime <= 30 minutes
retention_deadline == grant.approved_at + 30 days
checked_at < approval.expires_at <= grant.expires_at
```

The materializer receives the explicit human authorization action and derives
`T` plus the approved bounded expiry windows. It uses an injected trusted UTC
clock for that derivation and stale-window checks; it never substitutes the
clock for `research_as_of_time`.

## 12. Approval registry authority

Repository-wide inspection found no existing approval-registry table, config
object, producer, verifier, or committed operational registry record. The
strings `LOCAL_OPERATOR_CONFIRMATION`, version `1.0.0`, and arbitrary checksums
occur only in tests. They remain test fixtures, not operational authority.

```text
APPROVAL_REGISTRY_AUTHORITY: IMMUTABLE_PRODUCTION_CODE_MANIFEST_APPROVED
APPROVAL_REGISTRY_IMPLEMENTATION: NOT_IMPLEMENTED
```

Slice B must implement the approved immutable manifest, its canonical checksum
producer, and the production read/verification port. The checksum must be
derived from the final manifest and must not be invented in advance. Slice B
tests may use explicitly synthetic registry fixtures, but production
materialization remains fail closed until the approved manifest adapter exists.

## 13. Corrected atomic execution-start architecture

### 13.1 Selected ownership: Approach A with the existing transaction-neutral run repository

Extend `SqlAlchemySecAttemptReservationPort.start_execution()` so the port remains the one PostgreSQL transaction owner and creates the SyncRun inside its transaction through `SqlAlchemyProviderSyncRepository(session).create_run()`.

The port no longer requires a pre-existing `sync_run_id` for the initial start. It receives the v2 validation plus exact request/plan/provider/capability identity. `SecExecutionStartResult` is extended with the committed `sync_run_id`. After commit, the port may use that ID for retry reservations; downstream pilot/audit/storage components are created through factories keyed by the committed result rather than a pre-created run.

### 13.2 Target transaction and lock order

```text
BEGIN
  -> SELECT ProviderSyncRequest FOR UPDATE
  -> SELECT ProviderSyncPlan FOR UPDATE
  -> verify request checksum, request-to-plan relation, and v2 capability
  -> SELECT LiveExecutionApproval FOR UPDATE
  -> SELECT LiveAuthorizationGrant FOR UPDATE
  -> replay and validate grant lifecycle, approval state/signature, expiry,
     provider/governance/security/request/plan bindings
  -> create ProviderSyncRun using the same Session (flush only)
  -> update Approval VALID -> CONSUMED
  -> append grant CONSUME
  -> reserve one authorization consumption
  -> allocate permanent request_attempt_id / attempt number 1
  -> insert initial PENDING ProviderRequestAttempt
  -> authoritative in-transaction readback
COMMIT
  -> construct AuthorizedGateBExecutionV2
  -> construct SecAttemptPermit
  -> return SecExecutionStartResult(sync_run_id, execution, initial_permit)
```

No executable capability or permit is returned before `session.begin()` exits successfully. Any failure rolls back the SyncRun, approval state, grant event, consumption, and attempt.

### 13.3 Alternatives

| Approach | Benefits | Risks / costs | Decision |
|---|---|---|---|
| A: start port creates run | Preserves the current authoritative short transaction and one-winner lock; reuses transaction-neutral `create_run()`; smallest number of transaction owners. | Requires start-result and downstream factory API changes. | **Selected.** |
| B: higher-level application owns Session and composes run + start | Clear application orchestration. | Existing port currently owns a private Session/transaction; would require exposing many raw locking/reservation internals and risks two transaction owners. | Rejected. |
| C: new no-commit run primitive | Can preallocate a run ID. | Existing `create_run()` already is no-commit and flush-only; a duplicate primitive adds no authority. | Rejected. |

### 13.4 SyncRun idempotency

- Database uniqueness `(sync_request_id, sync_plan_id)` remains the natural run identity.
- Same consumed approval always fails before returning or reusing a run.
- Concurrent same-approval starts lock the same approval; only one transaction can create/commit the run and initial lineage.
- A pre-commit failure leaves no SyncRun and leaves the approval/grant usable because every write rolls back.
- A committed start has exactly one run. A retry uses that run; it never calls `create_run()`.
- An unexpected existing run with no matching consumed authorization/initial lineage is an integrity conflict, not an idempotent success.

No new SyncRun uniqueness constraint is required.

## 14. Initial-attempt atomicity and capability boundary

The required committed invariant is:

```text
SyncRun exists for the frozen request/plan
IFF the same committed execution-start transaction also contains:
  approval state CONSUMED
  exactly one grant CONSUME event
  exactly one initial authorization consumption
  exactly one PENDING attempt number 1 for SEC_SUBMISSIONS
```

The logical `IFF` is scoped to creation by the Gate B production execution-start path; later settlement changes attempt state without invalidating the committed lineage.

`AuthorizedGateBExecutionV2` and `SecAttemptPermit` are constructed after commit from the authoritative readback. Public Pydantic construction remains available for isolated tests, but no production composition returns them early.

## 15. Attempt and retry layering preservation

| Layer | Limit | Owner after correction |
|---|---:|---|
| Generic sync request | `max_attempts = 3` | `ProviderSyncRequestWrite` and frozen request |
| Generic Provider Policy | `max_attempts = 3` | `ProviderPolicyRecord` |
| Gate B physical attempts | `4` | V2 grant request limit plus `SqlAlchemySecAttemptReservationPort` persisted run count |
| Gate B plan-global retries | `1` | `SecGateBRetryController` plus persisted run attempt lineage |

The v2 request binding never writes `4` into the generic request or policy. Retry capacity is computed across the single SyncRun, not reset per resource. The ordered resource contract remains `SEC_SUBMISSIONS -> SEC_FILING_INDEX -> SEC_PRIMARY_DOCUMENT`; 429 is terminal, redirects remain zero, and failure at ordinal N prevents sends for N+1.

## 16. Backward-compatibility policy

Selected policy: **readable but non-executable for Gate B**.

- V1 grants/envelopes/approvals remain parseable for historical tests and non-Gate-B inspection.
- `ProductionAuthorizationGate` requires the v2 contract, complete request binding, and authoritative request readback for Gate B.
- Missing v2 fields or a legacy approval metadata NULL set yields a deterministic version/binding failure.
- No in-memory upgrade is allowed. V1 lacks human-approved request checksum, research cutoff, and mode, so complete authority cannot be proven.
- Operational DB migration of live authorization data is unnecessary because the accepted operational state has zero grants and approvals.

## 17. Slice A — Frozen Request Authorization Binding

### Production surface

- Modify `src/stock_research_agent/domain/live_evidence/gate_b_authorization.py`: v2 envelope, validation/capability fields, request/plan/governance checks, version failure codes.
- Modify `src/stock_research_agent/domain/live_evidence/schemas.py`: v2 Gate B grant types; leave generic V1 types readable.
- Modify `src/stock_research_agent/domain/live_evidence/canonical.py`: explicit v1/v2 grant canonicalization.
- Modify `src/stock_research_agent/domain/providers/repositories.py` and `src/stock_research_agent/db/repositories/providers.py`: exact typed `get_request()` and `get_plan()` read methods with optional row locks.
- Reuse `gate_b_request_identity.py`, governance repositories, and frozen operational records without mutation.

### RED tests

Create `tests/unit/test_gate_b_authorization_request_binding_red.py`:

1. `test_gate_b_authorization_rejects_wrong_sync_request_id`
2. `test_gate_b_authorization_rejects_wrong_request_checksum`
3. `test_gate_b_authorization_rejects_plan_request_mismatch`
4. `test_gate_b_authorization_rejects_wrong_credential_reference`
5. `test_gate_b_authorization_rejects_wrong_license_policy`
6. `test_gate_b_authorization_rejects_wrong_research_as_of`
7. `test_gate_b_authorization_rejects_non_live_validation_mode`
8. `test_gate_b_authorization_accepts_exact_frozen_request_and_plan`
9. `test_gate_b_authorization_rejects_legacy_unbound_grant_for_execution`

Exact RED command:

```powershell
uv run pytest -W error tests/unit/test_gate_b_authorization_request_binding_red.py -q
```

Create `tests/integration/test_gate_b_authorization_request_binding_postgres_red.py` to prove the production loader ignores forged caller model copies, reads the exact persisted request/plan/governance rows, and fails before returning validation on every mismatch.

```powershell
uv run pytest -W error tests/integration/test_gate_b_authorization_request_binding_postgres_red.py -q
```

### Completion criteria

All nine unit contracts and PostgreSQL authoritative-readback contracts are GREEN; old V1 authorization cannot execute; no operational freeze row, grant, approval, run, or attempt is mutated by validation tests.

## 18. Slice B — Production Authorization Materialization

### Production surface

- Modify `gate_b_authorization.py`: safe materialization request/result and application/transaction protocols.
- Modify `db/models/live_evidence.py`: complete v2 approval persistence fields.
- Modify `db/repositories/live_evidence.py`: materialization transaction adapter and authoritative mappers.
- Create the reviewed Alembic revision after `0013_gate_b_attempt_number_capacity`.
- Modify `cli_live.py` only to inject an explicitly configured materialization application; default operations remain blocked without the approved registry/human inputs.

### RED tests

Create `tests/unit/test_gate_b_authorization_materialization_red.py` for required actor/registry/time validation, no executable result, and no credential resolution.

Create `tests/integration/test_gate_b_authorization_materialization_postgres_red.py` with:

1. atomic grant + APPROVE + ACTIVATE + approval creation;
2. rollback after grant insertion;
3. rollback after lifecycle insertion;
4. rollback after approval insertion/readback failure;
5. exact equivalent replay returns same IDs and zero inserts;
6. conflicting registry replay fails closed;
7. expired or incoherent windows fail before persistence;
8. missing/invalid `approved_by` fails;
9. registry checksum mismatch fails;
10. no SyncRun, attempt, consumption, permit, network, or credential read.

```powershell
uv run pytest -W error tests/unit/test_gate_b_authorization_materialization_red.py tests/integration/test_gate_b_authorization_materialization_postgres_red.py -q
```

### Completion criteria

The migration is at one head; fresh and upgraded PostgreSQL schemas match ORM/fixtures; exact replay is idempotent; conflict and rollback proofs pass; materialization returns only non-executable safe IDs/checksums; all prohibited row deltas remain zero.

## 19. Slice C — Atomic Authorized Execution Start

### Production surface

- Modify `db/repositories/live_evidence.py`: lock request/plan/approval/grant in fixed order, create run in the same Session, reserve initial lineage, and return only after commit.
- Modify `providers/sec_edgar/retry.py`: add committed `sync_run_id` to `SecExecutionStartResult`; keep attempt/retry limits unchanged.
- Modify `domain/live_evidence/gate_b_pilot.py`: create run-keyed pilot/audit dependencies only after start succeeds.
- Modify `cli_live.py`: compose factories around the committed start result; default CLI remains blocked.
- Reuse `SqlAlchemyProviderSyncRepository.create_run()` in the same transaction; do not create a second run repository.

### PostgreSQL RED tests

Create `tests/integration/test_gate_b_authorized_execution_start_postgres_red.py`:

1. `test_start_creates_exactly_one_sync_run`
2. `test_start_atomically_consumes_grant_and_approval`
3. `test_start_atomically_creates_initial_pending_attempt`
4. `test_failure_after_run_creation_rolls_back_run`
5. `test_failure_after_grant_lock_rolls_back_everything`
6. `test_attempt_reservation_failure_rolls_back_grant_approval_and_run`
7. `test_concurrent_same_authorization_has_one_winner`
8. `test_concurrent_loser_receives_replay_failure`
9. `test_wrong_request_plan_binding_creates_no_run`
10. `test_expired_authorization_creates_no_run`
11. `test_transport_cannot_start_before_committed_permit`
12. `test_existing_unbound_run_is_integrity_conflict`

```powershell
uv run pytest -W error tests/integration/test_gate_b_authorized_execution_start_postgres_red.py -q
```

### Completion criteria

Every failure point leaves zero partial start lineage; two concurrent starts yield exactly one committed run/permit; request/plan drift and expiry create no run; transport event count is zero until after commit; existing RED-028 through RED-067 and request-identity contracts remain GREEN.

## 20. Cross-slice RED and regression matrix

| Contract | Slice A | Slice B | Slice C |
|---|---:|---:|---:|
| Exact request ID/checksum | Primary | Revalidate before persist | Revalidate under lock |
| Request-to-plan equality | Primary | Required | Required under lock |
| Credential/license substitution | Primary | Revalidate | Revalidate safe IDs |
| Research cutoff / LIVE mode | Primary | Persist in v2 grant | Revalidate under lock |
| Legacy V1 non-executable | Primary | Never materialize as v2 | Reject before run |
| Grant/lifecycle/approval atomicity | Preserve | Primary | Consume only after valid materialization |
| Materialization replay/conflict | Not applicable | Primary | Consumed replay blocked |
| SyncRun/start atomicity | No run | No run | Primary |
| Concurrent one-winner | Gate result non-executable | Registry/checksum uniqueness | Approval row lock + run uniqueness |
| No network/credential resolution | Required | Required | Required until committed permit |

Required regression after each slice:

```powershell
uv run pytest -W error tests/unit/test_gate_b_production_authorization_red.py tests/unit/test_gate_b_corrective_authorization_red.py -q
uv run pytest -W error tests/unit/test_gate_b_request_identity_red.py tests/unit/test_gate_b_request_identity_boundary_red.py -q
uv run pytest -W error tests/integration/test_gate_b_corrective_postgres_red.py tests/integration/test_gate_b_attempt_limit_migration_postgres_red.py -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

No live marker, SEC network, or operational authorization command belongs in these RED or implementation slices.

## 21. Security boundaries

1. Operator input and an envelope are never executable.
2. A gate result is non-executable until the PostgreSQL start transaction commits.
3. Request ID and checksum are directly approved and independently re-read.
4. Plan/request, credential, license, provider, policy, security, cutoff, and mode mismatches fail closed.
5. V1 weaker authorization cannot execute Gate B.
6. Grant/lifecycle/approval materialization is all-or-nothing and creates no run.
7. Start is all-or-nothing and creates no network activity.
8. Contact metadata remains a UUID/name/status binding; raw resolution occurs only in the existing protected transport boundary after permit commit.
9. No DB transaction remains open during DNS, socket, send, blob I/O, or response processing.
10. Generic request/policy attempt limits remain three; Gate B's fourth physical attempt remains reservation-controller-only.

## 22. Operational Freeze immutability

The following accepted records are read-only inputs to all three slices:

```text
CredentialReference
7c811ba4-a0e1-4955-9063-392d8c361eef

SourceLicensePolicy
39af6550-8031-4818-8cf1-648563a89258

ProviderSyncRequest
c38ff658-c585-4538-aea4-7f3d62e49874
checksum 35105364b41ee906ab00385f2c346ef6f8a8bb0e868a2a247dfa8305f4b80d50

ProviderSyncPlan
1f9af496-c858-435b-a5e5-31132714a85e
checksum 4faf214a562dd9dce4be2d9aec4d9f318277163840d0fa03119fc55f0c206ebd

research_as_of_time
2026-08-22T18:47:59.661193Z
```

No slice replaces these rows, changes their checksums, discovers another filing, or creates a new freeze. The v2 authorization binds to them.

## 23. Migration conclusion

```text
DATABASE_MIGRATION_REQUIRED: YES
```

Reason: the current approval table cannot authoritatively reconstruct or verify the domain approval signature and registry/human metadata. JSON grant scope and existing provider/request/plan tables are otherwise sufficient for request binding and atomic run creation. The migration is limited to v2 approval persistence completeness, FK/integrity checks, and legacy-null compatibility; it creates no authorization data.

## 24. Ratified human decisions and remaining execution gate

| Decision | Required before | Current state |
|---|---|---|
| Authoritative approval-registry source | Slice B implementation | `APPROVED: IMMUTABLE_PRODUCTION_CODE_MANIFEST` |
| Registry ID and version | Slice B implementation | `APPROVED: SEC_GATE_B_SINGLE_USE_AUTHORIZATION / 1.0.0` |
| Registry checksum | Slice B implementation | `CANONICALLY_DERIVED_FROM_FINAL_MANIFEST` |
| Stable `approved_by` actor code | Slice B V2 contract | `APPROVED: primary-human-operator` |
| Approval instant and windows | Operational materialization | `SYSTEM_DERIVED_AFTER_EXPLICIT_HUMAN_APPROVAL` |
| V2 schema migration direction and legacy policy | Slice B implementation | `DESIGN_APPROVED / NOT_IMPLEMENTED` |
| Actual single-use operational authorization action | Operational materialization | `NOT_AUTHORIZED` |

The governance decisions are resolved, but no implementation or operational
authorization exists. The production path must remain fail closed until Slice B
implements the approved authority and a later explicit human action authorizes
one bounded materialization.

## 25. Design decisions and readiness

```text
IMPORTANT_01_DESIGN_RESOLVED: YES
IMPORTANT_02_DESIGN_RESOLVED: YES
IMPORTANT_03_DESIGN_RESOLVED: YES

AUTHORIZATION_BINDING_DESIGN_COMPLETE: YES
MATERIALIZATION_DESIGN_COMPLETE: YES
ATOMIC_EXECUTION_START_DESIGN_COMPLETE: YES

DATABASE_MIGRATION_REQUIRED: YES
MIGRATION_DIRECTION: DESIGN_APPROVED_NOT_IMPLEMENTED
APPROVAL_REGISTRY_MANIFEST: DESIGN_APPROVED_NOT_IMPLEMENTED
HUMAN_DECISION_REQUIRED: NO

SLICE_A_RED_PLAN: COMPLETE
SLICE_B_RED_PLAN: COMPLETE
SLICE_C_RED_PLAN: COMPLETE

READY_FOR_AUTHORIZATION_CORRECTIVE_RED_PHASE: YES_SLICE_A_ONLY
```

The architecture and governance decisions are approved for Phase 7B-3C. Slice A
planning and RED establishment are authorized. Production implementation,
Slice B/C work, migration implementation, operational authorization, and Gate B
execution remain unauthorized.

## 26. Safety accounting

```text
Operational database mutations: 0
Authorization rows created: 0
Approval rows created: 0
SyncRuns created: 0
Attempts created: 0
SEC network calls: 0
SEC DNS: 0
Credential/contact reads: 0
Gate B executions: 0
Stage 11: NOT_STARTED
```
