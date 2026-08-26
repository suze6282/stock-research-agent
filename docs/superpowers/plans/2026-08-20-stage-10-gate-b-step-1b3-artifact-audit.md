# Step 1B-3 Artifact, Audit, Transaction, and STOP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the offline-testable production SEC pilot after transport by atomically reserving attempts, validating and retaining authoritative raw bytes, persisting linked audit/ingestion/document/citation lineage, committing Data Quality as the terminal result, and stopping before Snapshot or research orchestration.

**Architecture:** A focused `SecGateBPilotApplication` receives only an `AuthorizedGateBExecution`, a persisted checksum-bound plan, a Sync Run, and injected production ports. A short Pre-request Reservation Transaction commits the attempt/authorization reservation before the existing Step 1B-2 controller may resolve contact material or send; no transaction remains open during the network window. After transport, validation and blob publication occur outside PostgreSQL, a short Post-response Settlement Transaction makes database lineage authoritative, and bounded follow-on transactions compose DocumentVersion, parse/chunk, Citation, and a committed Data Quality STOP. This Reservation / Settlement Transaction Model is not distributed two-phase commit.

**Tech Stack:** Python 3.12, Pydantic 2 frozen contracts, SQLAlchemy 2, PostgreSQL row locking, the existing provider Sync/Artifact repositories, `AtomicProviderArtifactStorage`, `SecEdgarAdapter`, Data Access and DocumentVersion services, pytest, Ruff, and strict mypy.

## Global Constraints

- Baseline: `7acb8a85bc96990be53c7e5df4c414d9cb0554c3` on `feat/stage-10-gate-b-1b3-artifact-audit`.
- Gate B remains `NO_GO`, unauthorized, and unexecuted. Stage 11 remains not started.
- External network, DNS, real credential reads, Live calls, and model calls remain zero. Unit tests use fake transport/resolvers; PostgreSQL tests use only the documented loopback `TEST_DATABASE_URL`.
- `GateBAuthorizationEnvelope` remains non-executable. Every pilot run consumes an `AuthorizedGateBExecution`; every physical attempt consumes an authoritative `SecAttemptPermit`.
- The Step 1B-2 `SecGateBRetryController` remains the sole retry authority. Generic retry and timeout defaults remain unchanged.
- No database transaction may remain open during credential resolution, DNS, socket creation, HTTP wait, response streaming, response validation, or blob I/O.
- Retry eligibility and reservation are one atomic pre-send operation. A denied second retry cannot reach resolver, DNS, or `send_start`.
- A committed reservation never silently returns to unused. `ABANDONED` requires proof of `socket_opened=False` and `actual_bytes=0`; it never refunds attempt number, retry token, or single-use approval.
- Blob durability is not database authority. A blob without committed database lineage is `NON_AUTHORITATIVE` and cannot feed ingestion, Citation, Evidence, Claim, or Report.
- A Data Quality STOP is a successfully committed, auditable terminal outcome. It retains authoritative artifact/provenance/ingestion records and forbids Snapshot, Research Request, Agent Run, Claim, Report, publication, and Stage 11.
- Existing ORM tables and revision `0012_component_observation_lineage_integrity` are sufficient. No schema or migration change is permitted.
- Exact filing/accession and production Gate B authorization remain outside this implementation slice.
- No `skip`, `xfail`, weakened assertion, test-only production branch, raw-URL entrypoint, synthetic fallback, fixture-as-Live result, secret-bearing log/error, or direct database insert outside repositories is permitted.

---

## Repository-Backed Findings

### Existing contracts to reuse without change

- `AuthorizedGateBExecution`, `ProductionAuthorizationGate`, and `AuthorizationGatedSecPilotApplication` preserve authorization upstream of transport.
- `SecGateBTransportController`, `SecTransportResult`, `SecPhysicalAttempt`, `SecAttemptReservationPort`, `SecAttemptPermit`, and `SecGateBRetryController` own the bounded Step 1B-2 transport/retry behavior.
- `reserve_consumption(...)` and `settle_consumption(...)` already lock Live authorization rows and implement single-use/request/byte settlement, including the existing `ABANDONED` contract.
- `ProviderSyncRunRecord`, `ProviderRequestAttemptWrite`, `ProviderRequestAttemptRecord`, and `SqlAlchemyProviderSyncRepository.get_run(..., for_update=True)` provide Sync Run/attempt lineage.
- `ProviderRawArtifactDraft`, `ProviderRawArtifactWrite`, `ProviderIngestionManifestWrite`, `build_ingestion_manifest`, and `SqlAlchemyProviderArtifactRepository` provide immutable artifact/manifest/DQ persistence.
- `AtomicProviderArtifactStorage` computes SHA-256 and delegates atomic blob durability; `ProviderArtifactReconciler` already classifies an unlinked physical object as `ORPHAN_BLOB` and requires explicit deletion permission for repair.
- `SecEdgarAdapter.parse_response(...) -> ProviderBatch` performs deterministic CIK/accession/path/checksum/future-data validation.
- `SqlAlchemyDataAccessRepository`, `ProviderRequestLogWrite`, `RawPayloadWrite`, and `SourceDocumentWrite` provide the source-neutral lineage required by `DocumentVersionService`.
- `DocumentVersionService`, `DocumentParseService`, `DocumentChunker`, `SqlAlchemyKnowledgeRepository.add_chunks_and_citations`, and `ProviderDataQualityValidator` provide the existing document/citation/DQ path.
- Existing `ProviderAuditEvent` and `ProviderLiveValidationRun` tables can retain secret-free audit and terminal pilot status. Their current schema is sufficient.

### Current RED evidence at the baseline

The focused command below currently collects correctly and fails 3/3 without import, fixture, network, or credential errors:

```powershell
$env:PYTEST_ADDOPTS=''
uv run pytest -q `
  tests/unit/test_gate_b_sec_transport_red.py::test_red_043_production_sec_pipeline_validates_before_artifact_persistence `
  tests/unit/test_gate_b_production_authorization_red.py::test_red_044_audit_models_cover_gate_b_authorization_and_artifact_lineage `
  tests/unit/test_gate_b_sec_transport_red.py::test_red_049_production_gate_b_stops_at_data_quality
```

- RED-043: the blocked default shell has no `response_validated` field.
- RED-044: the blocked default shell has no linked artifact/authorization/candidate/checksum/provider/retrieval audit view.
- RED-049: the blocked default shell has no `terminal_stage`.
- RED-045: no automated transaction-boundary test exists; this is the documented testability gap.

The three current REDs incorrectly ask the default operator-facing `operate(plan_id, checksum)` shell to behave as an authorized Live execution. Their safety intent is retained and strengthened by retargeting them to an explicitly injected `SecGateBPilotApplication` that requires `AuthorizedGateBExecution`. The default CLI shell remains blocked and continues to satisfy RED-042/046.

### Data Access bridge decision

`ProviderDefinition` and source-neutral `DataProvider` are separate committed catalogs. Step 1B-3 does not auto-create or infer a `DataProvider`. The pilot loads an existing `DataProvider` by the exact approved provider code `SEC_EDGAR_PUBLIC_V1` and fails closed with `GATE_B_DATA_PROVIDER_NOT_CONFIGURED` if it is missing or not eligible. PostgreSQL tests seed that committed control-plane record explicitly. This preserves the existing `RawPayload -> SourceDocument -> DocumentVersion` FK model without schema work or ticker-only identity inference.

---

## Exact New and Changed Interfaces

New names below are required because the repository has no production pilot application, caller-owned UoW boundary, terminal attempt update, or immutable Live-validation result. They compose existing state machines and do not duplicate them.

```python
# domain/live_evidence/gate_b_pilot.py
class GateBTransactionKind(StrEnum):
    RESERVATION = "RESERVATION"
    SETTLEMENT = "SETTLEMENT"
    DOCUMENT = "DOCUMENT"
    DATA_QUALITY = "DATA_QUALITY"


class GateBUnitOfWork(Protocol):
    sync: ProviderSyncRepository
    artifacts: ProviderArtifactRepository
    data: DataAccessRepository
    knowledge: DocumentVersionRepository

    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool | None: ...


class GateBUnitOfWorkFactory(Protocol):
    def __call__(self, kind: GateBTransactionKind) -> GateBUnitOfWork: ...
```

Production creates one SQLAlchemy session/transaction per factory invocation. Instrumented fakes expose whether a UoW is active and record ordering. Network and blob ports do not receive the session.

```python
class LiveValidationTerminalStage(StrEnum):
    DATA_QUALITY = "DATA_QUALITY"


class LiveValidationResult(FrozenProviderContract):
    status: ProviderLiveValidationStatus
    terminal_stage: LiveValidationTerminalStage
    authorization_id: UUID
    plan_id: UUID
    plan_checksum: Checksum
    sync_run_id: UUID
    request_attempt_ids: tuple[UUID, ...]
    artifact_id: UUID | None
    manifest_id: UUID | None
    document_version_id: UUID | None
    citation_ids: tuple[UUID, ...]
    data_quality_passed: bool
    warning_codes: tuple[str, ...]
```

The result is secret-free and contains no contact value, headers, raw URL, response body, mutable plan, Snapshot ID, Claim ID, Report ID, or Stage 11 state.

```python
class SecGateBPilotApplication:
    def execute(
        self,
        execution: AuthorizedGateBExecution,
        *,
        plan: ProviderSyncPlanRecord,
        sync_run_id: UUID,
        slice_id: str,
        contact_reference: CredentialReferenceRecord,
        ingestion: SecIngestionContext,
    ) -> LiveValidationResult: ...

    def show(self, sync_run_id: UUID) -> GateBAuditView: ...
```

The constructor receives the transport controller factory, SQLAlchemy-backed reservation port factory, UoW factory, response validator/adapter, artifact storage, document services, DQ validator, and bounded clock. It accepts no authorization envelope or raw URL.

```python
# domain/providers/sync.py and repositories
class ProviderRequestAttemptReservation(FrozenProviderContract):
    id: UUID
    value: ProviderRequestAttemptWrite


class ProviderRequestAttemptSettlement(FrozenProviderContract):
    id: UUID
    status: ProviderSyncSliceStatus
    response_status_code: int | None
    response_bytes: int
    completed_at: AwareUtcDateTime
    safe_error_code: str | None


class ProviderSyncRepository(Protocol):
    def reserve_attempt(
        self, value: ProviderRequestAttemptReservation
    ) -> ProviderRequestAttemptRecord: ...
    def settle_attempt(
        self, value: ProviderRequestAttemptSettlement
    ) -> ProviderRequestAttemptRecord: ...
```

`reserve_attempt` accepts the preallocated permit UUID, inserts `PENDING`, and remains idempotent only for exactly matching content. `settle_attempt` locks the same row and permits only `PENDING -> COMPLETED|BLOCKED|FAILED`; repeated identical settlement is safe and conflicting settlement fails closed.

```python
# db/repositories/live_evidence.py
class SqlAlchemySecAttemptReservationPort(SecAttemptReservationPort):
    def reserve(self, request: SecAttemptReservationRequest) -> SecAttemptPermit: ...
```

The adapter is bound at construction to one `AuthorizedGateBExecution`, `sync_run_id`, session factory, and clock. One short transaction locks authorization consumption then Sync Run in a fixed order, verifies plan/run/provider/capability lineage, atomically enforces total attempts `<=4` and plan-global retry attempts `<=1`, preallocates `request_attempt_id`, calls `reserve_consumption`, inserts the matching `PENDING` attempt, and commits before returning the permit.

```python
# providers/sec_edgar/transport.py
class SecPhysicalAttempt(FrozenProviderContract):
    permit: SecAttemptPermit
    response: HttpResult | None
    safe_error_code: str | None
    started_at: AwareUtcDateTime
    completed_at: AwareUtcDateTime
    socket_opened: bool | None
```

The transport catches secret-free contact/final-policy failures after reservation and returns a terminal attempt outcome. Only demonstrably pre-socket failures set `socket_opened=False`; ambiguity sets `None` and cannot become `ABANDONED`. This extension exposes audit facts without performing persistence.

```python
class GateBAuditView(FrozenProviderContract):
    authorization_id: UUID
    candidate: GateBCandidate
    provider: str
    plan_id: UUID
    plan_checksum: Checksum
    sync_run_id: UUID
    request_attempt_ids: tuple[UUID, ...]
    artifact_id: UUID | None
    content_checksum: Checksum | None
    retrieved_at: AwareUtcDateTime | None
    manifest_id: UUID | None
    document_version_id: UUID | None
    citation_ids: tuple[UUID, ...]
    live_validation_status: ProviderLiveValidationStatus
    terminal_stage: LiveValidationTerminalStage | None
    warning_codes: tuple[str, ...]
```

The query is assembled from committed rows only. It contains identifiers/checksums/statuses, never credential material, response headers, or body bytes.

---

## Task 1: Freeze Ownership-Correct RED-043/044/045/049 Contracts

**Purpose:** Replace default-shell false assumptions with an explicitly authorized, injected offline pilot and establish the missing transaction/orphan/STOP companion REDs before production changes.

**Files:**
- CREATE: `tests/unit/test_sec_gate_b_pilot.py`
- CREATE: `tests/integration/test_gate_b_sec_pilot_postgres.py`
- MODIFY: `tests/unit/test_gate_b_sec_transport_red.py`
- MODIFY: `tests/unit/test_gate_b_production_authorization_red.py`
- READ/REUSE: `tests/unit/test_sec_gate_b_transport.py`, `tests/integration/test_live_authorization_budget_postgres.py`, `tests/integration/test_provider_artifact_repository_postgres.py`

**Interfaces:**
- Consumes: real `AuthorizedGateBExecution`, plan and Sync Run records; deterministic fake transport/resolver/blob storage; instrumented UoW factory.
- Produces: failing contracts for validated-before-persist, linked audit, transaction ordering, PostgreSQL concurrency, orphan safety, and committed DQ STOP.

**Preconditions:** RED-028 through RED-042, RED-046 through RED-048 remain unchanged. Default `sec_pilot_application_factory().operate("run", ...)` remains blocked.

**Exact failing tests:**
- `test_red_043_authorized_sec_response_is_validated_before_authoritative_artifact`
- `test_red_043_blob_success_db_failure_leaves_no_authoritative_artifact`
- `test_red_044_committed_audit_view_links_authorization_attempt_artifact_and_candidate`
- `test_red_045_network_window_has_no_open_ingestion_transaction`
- `test_red_045_committed_pre_send_failure_is_terminal_and_not_silently_refunded`
- `test_red_045_orphan_blob_is_non_authoritative_after_settlement_rollback`
- `test_red_045_postgres_retry_reservation_is_atomic_before_send`
- `test_red_049_data_quality_stop_is_committed_and_blocks_downstream`

**Exact RED command:**

```powershell
$env:PYTEST_ADDOPTS=''
uv run pytest -q tests/unit/test_sec_gate_b_pilot.py `
  tests/unit/test_gate_b_sec_transport_red.py -k "red_043 or red_049" `
  tests/unit/test_gate_b_production_authorization_red.py -k "red_044"
```

Run PostgreSQL RED separately with only the documented loopback test database:

```powershell
$env:PYTEST_ADDOPTS=''
uv run pytest -q -m integration tests/integration/test_gate_b_sec_pilot_postgres.py
```

**Expected RED reason:** `SecGateBPilotApplication`, production UoW/reservation adapter, settlement, audit query, and LiveValidationResult do not exist. Unit tests must fail on those exact missing seams; PostgreSQL tests must collect and fail on missing repository behavior, not fixture or database configuration errors.

**Minimal test change:** Retarget the three named RED tests to the authorized pilot fixture. Keep separate regressions proving the operator/default CLI remains blocked. Use a local SEC response fixture only as fake transport bytes and mark the result as an offline simulation, never Gate B success.

**Important invariants:** Tests assert zero downstream Snapshot/Research/Claim/Report calls through spies; transaction events are exact; secret sentinel is absent from result, exceptions, audit payload, and captured logs.

**Forbidden changes:** No production code, `skip`, `xfail`, live marker, environment resolver, external hostname, or assertion weakening in this task.

**Expected GREEN result:** None in this task; every new production-demanding test is stable RED and existing default-shell safety remains GREEN.

**Regression command:**

```powershell
uv run pytest -q tests/unit/test_gate_b_production_authorization_red.py `
  tests/unit/test_gate_b_sec_transport_red.py `
  tests/unit/test_sec_gate_b_transport.py
```

**Commit boundary:** Commit only tests after stable, ownership-correct REDs.

**Suggested subject:** `test: lock gate b artifact settlement contracts`

---

## Task 2: Add Attempt Reservation and Terminal Settlement Repository Contracts

**Purpose:** Give the existing attempt table one authoritative preallocated ID and a fail-closed terminal transition without changing its schema.

**Files:**
- MODIFY: `src/stock_research_agent/domain/providers/sync.py`
- MODIFY: `src/stock_research_agent/domain/providers/repositories.py`
- MODIFY: `src/stock_research_agent/db/repositories/providers.py`
- MODIFY: `tests/integration/test_provider_sync_repository_postgres.py`
- READ/REUSE: `src/stock_research_agent/db/models/providers.py`

**Interfaces:**
- Consumes: `ProviderRequestAttemptReservation`, `ProviderRequestAttemptSettlement`.
- Produces: exactly identified `ProviderRequestAttemptRecord` across reservation and terminal settlement.

**Preconditions:** Task 1 REDs committed. Existing `append_attempt` behavior remains compatible for non-Gate-B provider paths.

**Exact failing tests:**
- `test_attempt_repository_accepts_preallocated_id_and_settles_same_row`
- `test_attempt_settlement_is_idempotent_and_conflict_fails_closed`
- `test_attempt_reservation_rolls_back_with_caller_transaction`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''
uv run pytest -q -m integration tests/integration/test_provider_sync_repository_postgres.py `
  -k "preallocated_id or settlement or reservation_rolls_back"
```

**Expected RED reason:** `ProviderSyncRepository` has only `append_attempt`, allocates its UUID internally, and cannot transition the pre-send `PENDING` row.

**Minimal production change:** Add the two frozen inputs and repository methods above. Keep all transaction ownership with the caller. Reuse the existing `(sync_run_id, slice_id, attempt_number)` uniqueness and immutable terminal row vocabulary.

**Important invariants:** A different UUID for the same logical attempt conflicts; terminal-to-terminal mutation conflicts; no completed row can return to PENDING; `response_bytes=0` is explicit rather than missing.

**Forbidden changes:** ORM/migration edits, new attempt status, deletion, automatic refund, or implicit transaction commit.

**Expected GREEN result:** The exact caller-supplied UUID survives reservation/settlement and rollback leaves no row.

**Regression command:**

```powershell
uv run pytest -q -m integration tests/integration/test_provider_sync_repository_postgres.py
```

**Commit boundary:** Repository contract and its PostgreSQL tests.

**Suggested subject:** `feat: reserve provider attempt identities`

---

## Task 3: Implement the PostgreSQL Atomic SEC Attempt Reservation Port

**Purpose:** Close the deferred RED-036 concurrency proof by atomically reserving initial/retry permits before any resolver, DNS, or send activity.

**Files:**
- MODIFY: `src/stock_research_agent/db/repositories/live_evidence.py`
- MODIFY: `tests/integration/test_gate_b_sec_pilot_postgres.py`
- READ/REUSE: `src/stock_research_agent/providers/sec_edgar/retry.py`, `tests/integration/test_live_authorization_budget_postgres.py`

**Interfaces:**
- Consumes: bound `AuthorizedGateBExecution`, Sync Run ID, `SecAttemptReservationRequest`, session factory, clock.
- Produces: committed `SecAttemptPermit` whose UUID equals the PENDING attempt row and Live authorization consumption attempt ID.

**Preconditions:** Task 2 repository contract GREEN. Seeded plan, grant, approval, Sync Run, and consumption FKs all share provider/plan identity.

**Exact failing tests:**
- `test_red_045_postgres_initial_reservation_commits_before_transport`
- `test_red_036_postgres_concurrent_retry_reservation_allows_one_sender`
- `test_postgres_fifth_actual_attempt_is_denied_before_transport`
- `test_postgres_reservation_rolls_back_consumption_and_attempt_together`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''
uv run pytest -q -m integration tests/integration/test_gate_b_sec_pilot_postgres.py `
  -k "reservation or concurrent_retry or fifth_actual_attempt"
```

**Expected RED reason:** Step 1B-2 exposes only `SecAttemptReservationPort`; no SQLAlchemy adapter locks and commits authorization/Sync Run state.

**Minimal production change:** Implement `SqlAlchemySecAttemptReservationPort.reserve`. Lock the Live authorization record through existing consumption reservation, then lock the Sync Run using a documented fixed order. Count committed attempt lineage for total attempts and `attempt_number > 1` for the single retry token. Create the consumption and PENDING attempt in the same short transaction and return only after commit.

**Important invariants:** Two concurrent retry callers cannot both receive permits; denied reservation emits no `send_start`; the permit is scoped to exact authorization/plan/slice/endpoint/attempt; retry accounting never depends on an in-memory counter.

**Forbidden changes:** Holding the transaction beyond `reserve`, modifying generic retry, increasing budgets, retry refund, or adding a table/column.

**Expected GREEN result:** Exactly one concurrent retry reservation succeeds; all denied paths have zero transport calls and no partial consumption/attempt row.

**Regression command:**

```powershell
uv run pytest -q -m integration tests/integration/test_live_authorization_budget_postgres.py `
  tests/integration/test_live_authorization_single_use_postgres.py `
  tests/integration/test_gate_b_sec_pilot_postgres.py
```

**Commit boundary:** Atomic reservation adapter and concurrency proof.

**Suggested subject:** `feat: reserve gate b sec attempts atomically`

---

## Task 4: Expose Auditable Physical Attempt Outcomes Without Persisting in Transport

**Purpose:** Preserve attempt identity and demonstrable pre-socket facts for settlement, including contact/final-policy failure after reservation.

**Files:**
- MODIFY: `src/stock_research_agent/providers/sec_edgar/transport.py`
- MODIFY: `tests/unit/test_sec_gate_b_transport.py`
- READ/REUSE: `src/stock_research_agent/providers/http_client.py`, `src/stock_research_agent/providers/sec_edgar/request_identity.py`

**Interfaces:**
- Consumes: existing authorized plan, permit, fake resolver/client, injected clock.
- Produces: extended immutable `SecPhysicalAttempt` with start/completion and conservative socket evidence.

**Preconditions:** Step 1B-2 target contracts remain GREEN.

**Exact failing tests:**
- `test_committed_permit_contact_failure_returns_terminal_pre_socket_attempt`
- `test_transport_failure_with_uncertain_socket_state_cannot_claim_unstarted`
- `test_success_attempt_exposes_safe_timing_and_no_contact_material`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''
uv run pytest -q tests/unit/test_sec_gate_b_transport.py `
  -k "pre_socket_attempt or uncertain_socket or safe_timing"
```

**Expected RED reason:** contact resolution exceptions escape after reservation and `SecPhysicalAttempt` lacks timestamps/socket evidence.

**Minimal production change:** Add an injected clock, extend the result, and convert known validation failures to secret-free blocked attempt outcomes. Set `False` only before entering the HTTP client send boundary; set `None` for ambiguous client/network failures; successful response sets `True`.

**Important invariants:** The permit is never lost; raw contact material never enters result or exception; transport still opens no repository/UoW and persists nothing.

**Forbidden changes:** Logging identity, claiming `socket_opened=False` after ambiguous transport failure, adding DB dependencies, or changing retry policy.

**Expected GREEN result:** Every reserved attempt yields settlement-ready safe facts and all Step 1B-2 transport tests stay GREEN.

**Regression command:**

```powershell
uv run pytest -q tests/unit/test_sec_gate_b_transport.py `
  tests/unit/test_provider_http_client.py `
  tests/unit/test_provider_credential_resolver.py
```

**Commit boundary:** Transport outcome contract only.

**Suggested subject:** `feat: expose sec attempt settlement facts`

---

## Task 5: Validate Responses and Build Deterministic Settlement Drafts

**Purpose:** Prove MIME/body/checksum/candidate/as-of validity before any authoritative artifact row or downstream ingestion can exist.

**Files:**
- CREATE: `src/stock_research_agent/domain/live_evidence/gate_b_pilot.py`
- MODIFY: `tests/unit/test_sec_gate_b_pilot.py`
- READ/REUSE: `src/stock_research_agent/providers/sec_edgar/adapter.py`, `domain/providers/artifacts.py`, `infrastructure/provider_artifact_storage.py`

**Interfaces:**
- Consumes: successful `SecPhysicalAttempt`, `SecAuthorizedResource`, `SecIngestionContext`, preallocated artifact UUID.
- Produces: immutable `ValidatedSecSettlement` containing safe response metadata, `ProviderRawArtifactDraft`, parsed `ProviderBatch`, source identity/checksum/timestamps, and deterministic manifest inputs.

**Preconditions:** Attempt facts from Task 4; exact plan/candidate binding already validated by Step 1B-2.

**Exact failing tests:**
- `test_red_043_wrong_mime_empty_body_checksum_or_future_data_creates_no_artifact_draft`
- `test_red_043_valid_response_is_parsed_once_before_blob_and_database_persistence`
- `test_validated_settlement_rejects_cik_accession_and_resource_mismatch`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''
uv run pytest -q tests/unit/test_sec_gate_b_pilot.py -k "red_043 or validated_settlement"
```

**Expected RED reason:** no pilot response validator/settlement draft exists.

**Minimal production change:** Add the focused domain module, reuse `SecEdgarAdapter.parse_response`, preallocate one artifact UUID for deterministic record lineage, validate expected MIME/non-empty/bounded bytes and checksum, and produce frozen drafts only. No repository or blob write occurs in this task.

**Important invariants:** Field authority comes from the authorized resource and candidate, never from response guesses; future data fails closed; the adapter parses exact bytes once; fixture bytes are explicitly test transport input.

**Forbidden changes:** Persisting artifact/audit, accepting arbitrary URL/path, synthesizing missing filing data, or creating DocumentVersion/Citation.

**Expected GREEN result:** Valid response produces deterministic drafts; every corrupt/mismatched response produces no artifact/storage/persistence call.

**Regression command:**

```powershell
uv run pytest -q tests/unit/test_sec_edgar_parser.py tests/unit/test_provider_raw_artifacts.py `
  tests/unit/test_provider_ingestion_manifests.py tests/unit/test_sec_gate_b_pilot.py
```

**Commit boundary:** Pure response-validation/application contracts.

**Suggested subject:** `feat: validate sec gate b settlement drafts`

---

## Task 6: Persist Attempt, Blob, Artifact, Manifest, and Secret-Free Audit Atomically

**Purpose:** Make database lineage authoritative only after validated bytes are durable and settlement commits, while retaining safe orphan semantics on failure.

**Files:**
- MODIFY: `src/stock_research_agent/domain/live_evidence/gate_b_pilot.py`
- MODIFY: `src/stock_research_agent/domain/providers/artifacts.py`
- MODIFY: `src/stock_research_agent/domain/providers/repositories.py`
- MODIFY: `src/stock_research_agent/db/repositories/providers.py`
- MODIFY: `src/stock_research_agent/infrastructure/provider_artifact_storage.py` only if an exact-key compensation operation is absent and required
- MODIFY: `tests/unit/test_sec_gate_b_pilot.py`
- MODIFY: `tests/integration/test_gate_b_sec_pilot_postgres.py`
- READ/REUSE: `ProviderArtifactReconciler`, `settle_consumption`, `build_ingestion_manifest`

**Interfaces:**
- Consumes: `ValidatedSecSettlement`, stored blob metadata, terminal attempt facts, UoW factory.
- Produces: committed terminal attempt/consumption, `ProviderRawArtifactRecord`, `ProviderIngestionManifestRecord`, audit event, and settlement result.

**Preconditions:** Tasks 2–5 GREEN. Blob write is outside the settlement transaction.

**Exact failing tests:**
- `test_red_043_validated_blob_settlement_commits_one_authoritative_artifact`
- `test_red_043_invalid_response_never_calls_blob_or_artifact_repository`
- `test_red_045_blob_success_database_failure_rolls_back_authoritative_lineage`
- `test_red_045_orphan_blob_is_reported_non_authoritative_and_requires_explicit_cleanup`
- `test_network_failure_settles_attempt_without_raw_artifact`
- `test_pre_send_failure_settles_abandoned_without_reuse_or_retry_refund`

**Exact test commands:**

```powershell
$env:PYTEST_ADDOPTS=''
uv run pytest -q tests/unit/test_sec_gate_b_pilot.py -k "settlement or orphan or network_failure"
uv run pytest -q -m integration tests/integration/test_gate_b_sec_pilot_postgres.py `
  -k "artifact or settlement or orphan or network_failure"
```

**Expected RED reason:** there is no caller-owned settlement orchestration; artifact repository allocates IDs internally; audit/live-validation repositories are not composed.

**Minimal production change:** Permit an application-supplied artifact UUID using the same idempotent/conflict rules as attempt IDs. Write validated bytes with `AtomicProviderArtifactStorage` outside the UoW. Open a SETTLEMENT UoW and atomically settle Live consumption and attempt, persist artifact/manifest/checkpoint and linked safe audit. On transaction failure, roll back all DB rows and perform only exact-URI best-effort compensation; regardless of cleanup outcome, the blob has no authority without committed DB lineage and `ProviderArtifactReconciler` reports it as `ORPHAN_BLOB`.

**Important invariants:** No successful audit if settlement rolls back; no ProviderRawArtifact without matching terminal attempt; repeated exact artifact/checksum is idempotent; different bytes/source identity conflict; `ABANDONED` requires false socket + zero bytes and does not make the human authorization reusable.

**Forbidden changes:** Distributed 2PC, recursive/blob-prefix deletion, automatic orphan adoption, deletion of failed audit rows, or treating blob existence as success.

**Expected GREEN result:** A valid response commits one linked artifact/manifest/audit; injected DB failure commits none and leaves at most a safely classified non-authoritative orphan.

**Regression command:**

```powershell
uv run pytest -q tests/unit/test_provider_raw_artifacts.py `
  tests/unit/test_provider_artifact_reconciliation.py `
  tests/integration/test_provider_artifact_repository_postgres.py `
  tests/integration/test_gate_b_sec_pilot_postgres.py
```

**Commit boundary:** Artifact settlement and orphan safety.

**Suggested subject:** `feat: settle gate b sec artifacts safely`

---

## Task 7: Bridge Committed Provider Artifact to DocumentVersion and Citation

**Purpose:** Reuse committed Data Access and document contracts so Citation lineage derives only from the authoritative artifact, without creating a Snapshot or research request.

**Files:**
- MODIFY: `src/stock_research_agent/domain/live_evidence/gate_b_pilot.py`
- MODIFY: `src/stock_research_agent/domain/live_evidence/document_bridge.py` only if a provider-artifact request adapter is needed around the existing `admit_document`
- MODIFY: `src/stock_research_agent/db/repositories/data_access.py` only for a bounded existing-record query proven absent
- MODIFY: `tests/unit/test_sec_gate_b_pilot.py`
- MODIFY: `tests/integration/test_gate_b_sec_pilot_postgres.py`
- READ/REUSE: `domain/data_access/ingestion.py`, `domain/documents/identity.py`, parser/chunker services, `db/repositories/knowledge.py`

**Interfaces:**
- Consumes: committed artifact/manifest, existing exact `DataProvider`, security/candidate, parsed SEC filing metadata/document bytes.
- Produces: committed `ProviderRequestLog`, `RawPayload`, `SourceDocument`, `DocumentVersion`, parse/chunks, and Citations linked to the same storage URI/checksum/security/provider.

**Preconditions:** Artifact settlement committed. Exact `DataProvider(code="SEC_EDGAR_PUBLIC_V1")` and stable logical-document identity are seeded; absence blocks with no inferred replacement.

**Exact failing tests:**
- `test_committed_artifact_bridges_to_document_version_with_exact_checksum_lineage`
- `test_document_version_or_citation_failure_cannot_claim_live_validation_pass`
- `test_missing_data_provider_or_logical_document_fails_closed`
- `test_provider_artifact_identity_cannot_cross_security_or_filing`

**Exact test commands:**

```powershell
$env:PYTEST_ADDOPTS=''
uv run pytest -q tests/unit/test_sec_gate_b_pilot.py -k "document_version or citation"
uv run pytest -q -m integration tests/integration/test_gate_b_sec_pilot_postgres.py `
  -k "document_version or citation or data_provider"
```

**Expected RED reason:** no production bridge composes Provider artifact lineage into the source-neutral Data Access/DocumentVersion path.

**Minimal production change:** In bounded DOCUMENT UoWs, require the exact existing provider/security records, persist request log/raw payload/source document from committed artifact metadata, delegate immutable version registration, parse/chunk, and persist citations through existing services. Reuse the authoritative artifact blob URI and SHA-256; never copy or re-hash into an unrelated source identity.

**Important invariants:** Provider ID and security ID are FK-backed; publication/retrieval times preserve as-of rules; a missing financial fact remains missing; Citation cannot precede DocumentVersion; no Snapshot is created.

**Forbidden changes:** Auto-seeding production provider records, ticker-only identity, manual Citation insertion, Evidence/Claim/Report composition, or synthetic fallback.

**Expected GREEN result:** The committed artifact produces exact immutable document/citation lineage or a committed blocked pilot outcome with no false success.

**Regression command:**

```powershell
uv run pytest -q tests/unit/test_document_identity.py `
  tests/unit/test_document_parsing_service.py `
  tests/unit/test_document_chunking.py `
  tests/unit/test_evidence_citation_eligibility.py `
  tests/integration/test_data_access_repository_postgres.py `
  tests/integration/test_knowledge_repository_postgres.py
```

**Commit boundary:** Source-neutral document/citation bridge.

**Suggested subject:** `feat: bridge gate b artifacts to citations`

---

## Task 8: Commit Data Quality as the Terminal STOP

**Purpose:** Persist DQ and the live-validation terminal result without rolling back valid artifact/document lineage or invoking downstream research.

**Files:**
- MODIFY: `src/stock_research_agent/domain/live_evidence/gate_b_pilot.py`
- MODIFY: `src/stock_research_agent/domain/live_evidence/schemas.py` only for `LiveValidationResult`/`GateBAuditView` if the focused pilot module would create a circular dependency
- MODIFY: `src/stock_research_agent/domain/providers/repositories.py`
- MODIFY: `src/stock_research_agent/db/repositories/providers.py`
- MODIFY: `tests/unit/test_sec_gate_b_pilot.py`
- MODIFY: `tests/integration/test_gate_b_sec_pilot_postgres.py`
- READ/REUSE: `ProviderDataQualityValidator`, `ProviderDataQualityIssueWrite`, existing `ProviderLiveValidationRun` and `ProviderAuditEvent` ORM models

**Interfaces:**
- Consumes: committed artifact/manifest/batch/document/citation lineage and DQ context.
- Produces: persisted quality issues/pass decision, terminal live-validation status/audit, immutable `LiveValidationResult(terminal_stage=DATA_QUALITY)`.

**Preconditions:** Tasks 6–7 GREEN. DQ starts only from committed authoritative lineage.

**Exact failing tests:**
- `test_red_049_data_quality_pass_commits_terminal_result_and_stops`
- `test_red_049_data_quality_blocked_commits_issues_and_retains_artifact`
- `test_red_049_stop_invokes_no_snapshot_research_claim_report_or_stage11_port`
- `test_dq_persistence_failure_rolls_back_only_dq_transaction_not_artifact_settlement`

**Exact test commands:**

```powershell
$env:PYTEST_ADDOPTS=''
uv run pytest -q tests/unit/test_sec_gate_b_pilot.py -k "red_049 or data_quality"
uv run pytest -q -m integration tests/integration/test_gate_b_sec_pilot_postgres.py `
  -k "data_quality or terminal_stop"
```

**Expected RED reason:** no repository/domain composition writes ProviderLiveValidationRun/Audit terminal state and no production `LiveValidationResult` exists.

**Minimal production change:** Add focused repository methods for create/transition/query of the existing live-validation/audit rows; persist DQ result and terminal status in a short DATA_QUALITY UoW; return the frozen secret-free result. The pilot constructor exposes no Snapshot/Research/Claim/Report/Stage11 dependencies, making downstream execution structurally impossible.

**Important invariants:** DQ STOP is not a persistence failure and not a rollback trigger; committed artifact/provenance remains after DQ blocked/failure; status vocabulary maps domain `PASSED/FAILED/BLOCKED` to existing ORM `PASS/FAILED/BLOCKED` at one repository boundary.

**Forbidden changes:** Creating a Snapshot, Evidence, Claim, Package, Report, Release Gate, publication, or Stage 11 port; converting DQ issues to business facts.

**Expected GREEN result:** RED-049 proves both committed auditability and total downstream isolation.

**Regression command:**

```powershell
uv run pytest -q tests/unit/test_provider_data_quality.py `
  tests/unit/test_sec_gate_b_pilot.py `
  tests/integration/test_gate_b_sec_pilot_postgres.py
```

**Commit boundary:** DQ terminal STOP and audit query.

**Suggested subject:** `feat: commit gate b data quality stop`

---

## Task 9: Compose the Production Pilot While Keeping the Operator Shell Blocked

**Purpose:** Wire the application factory for explicit authorized use and linked audit inspection without creating an operator path that can self-authorize or send.

**Files:**
- MODIFY: `src/stock_research_agent/domain/live_evidence/gate_b_authorization.py`
- MODIFY: `src/stock_research_agent/cli_live.py`
- MODIFY: `tests/unit/test_gate_b_production_authorization_red.py`
- MODIFY: `tests/unit/test_gate_b_sec_transport_red.py`
- MODIFY: `tests/integration/test_gate_b_sec_pilot_postgres.py`
- READ/REUSE: production SQLAlchemy/session/blob/document composition roots

**Interfaces:**
- Consumes: explicit authoritative execution capability and injected operational dependencies.
- Produces: `SecGateBPilotApplication`; default CLI `operate` remains blocked; explicit application `show(sync_run_id)` returns `GateBAuditView` from committed rows.

**Preconditions:** Tasks 3–8 GREEN.

**Exact failing tests:**
- `test_red_043_authorized_production_composition_reaches_committed_artifact`
- `test_red_044_production_audit_view_is_complete_linked_and_secret_free`
- `test_default_cli_cannot_create_authorization_or_execute_pilot_from_plan_arguments`
- `test_red_049_production_composition_returns_data_quality_stop`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''
uv run pytest -q tests/unit/test_gate_b_production_authorization_red.py `
  tests/unit/test_gate_b_sec_transport_red.py `
  tests/unit/test_sec_gate_b_pilot.py `
  tests/integration/test_gate_b_sec_pilot_postgres.py
```

**Expected RED reason:** current production factory exposes only the intentionally blocked Step 1B-1 shell and has no authorized pilot composition/query.

**Minimal production change:** Extend the shell with an explicitly injected authorized-pilot port or add a separate production factory used only after the authoritative gate. Do not make `operate("run", plan_id, checksum)` executable. Wire SQLAlchemy UoWs, reservation adapter, existing transport, blob storage, parser/document/DQ services, and audit query through constructors.

**Important invariants:** A plan ID/checksum from an operator remains non-executable; factory creation reads no credential value and opens no network; only `execute_authorized(AuthorizedGateBExecution, ...)` can reach transport.

**Forbidden changes:** Implicit grant lookup/activation from CLI, default credential resolution, live network construction in tests, or returning an execution capability in JSON.

**Expected GREEN result:** RED-043/044/049 are GREEN through real production composition with fakes/loopback PostgreSQL, while RED-042/046 and no-raw-URL contracts remain GREEN.

**Regression command:**

```powershell
uv run pytest -q tests/unit/test_gate_b_production_authorization_red.py `
  tests/unit/test_gate_b_sec_transport_red.py `
  tests/unit/test_sec_gate_b_transport.py `
  tests/unit/test_sec_gate_b_pilot.py
```

**Commit boundary:** Production composition root and RED closure.

**Suggested subject:** `feat: compose authorized gate b sec pilot`

---

## Task 10: Full Offline Regression, Static Checks, and Security Review

**Purpose:** Prove Step 1B-3 closes only its four contracts, preserves Step 1B-1/2 and Stage 10 offline acceptance, and leaves Gate B unexecuted.

**Files:**
- MODIFY: none unless a failure is caused by this slice and the correction stays within the approved files/contracts.
- TEST: all Gate B unit/integration tests and the smallest Stage 10 offline production regression.

**Preconditions:** Tasks 1–9 committed and working tree clean.

**Exact target command:**

```powershell
$env:PYTEST_ADDOPTS=''
uv run pytest -q `
  tests/unit/test_gate_b_production_authorization_red.py `
  tests/unit/test_gate_b_sec_transport_red.py `
  tests/unit/test_sec_gate_b_transport.py `
  tests/unit/test_sec_gate_b_pilot.py `
  tests/integration/test_live_authorization_budget_postgres.py `
  tests/integration/test_live_authorization_single_use_postgres.py `
  tests/integration/test_provider_sync_repository_postgres.py `
  tests/integration/test_provider_artifact_repository_postgres.py `
  tests/integration/test_gate_b_sec_pilot_postgres.py
```

**Expected GREEN:** RED-028 through RED-049 are GREEN where implemented; RED-045 now has automated unit and PostgreSQL evidence. RED-036 final PostgreSQL concurrency proof is GREEN. No cross-slice work remains inside Step 1B.

**Relevant Stage 10 offline regression:**

```powershell
uv run pytest -q tests/unit `
  tests/integration/test_provider_sync_repository_postgres.py `
  tests/integration/test_provider_sync_budget_postgres.py `
  tests/integration/test_provider_artifact_repository_postgres.py `
  tests/integration/test_provider_checkpoint_postgres.py `
  tests/integration/test_live_authorization_budget_postgres.py `
  tests/integration/test_live_authorization_single_use_postgres.py `
  tests/integration/test_gate_b_sec_pilot_postgres.py
```

**Static checks:**

```powershell
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
git diff --check
git status --short
```

**Security review assertions:**

- authorization envelope cannot execute; `AuthorizedGateBExecution` and committed permits remain mandatory;
- reservation/retry concurrency proof precedes `send_start` and no DB transaction spans network;
- pre-send failure cannot silently refund/reuse authorization;
- contact value is absent from logs, exceptions, audit, checksum, artifacts, and results;
- invalid response creates no authoritative artifact;
- blob/DB rollback leaves no authoritative lineage and orphan reconciliation is explicit;
- DQ STOP is committed and no downstream Snapshot/Research/Claim/Report/Stage11 dependency exists;
- network/DNS/real credential/model counters remain zero.

**Forbidden changes:** full Live tests, SEC requests, credential manager/environment reads, schema/migration, generic retry/timeout changes, Gate B authorization/execution, or Stage 11.

**Expected result:** All focused/regression/static checks pass with zero external side effects; working tree contains only intended Step 1B-3 commits.

**Commit boundary:** No empty acceptance commit. If a scoped correction is required, commit it separately with a behavior-specific subject.

---

## RED Mapping and Exit Criteria

| Contract | Baseline | Required production proof | Exit state |
|---|---|---|---|
| RED-043 | RED: blocked shell lacks validation/artifact fields | validate exact bytes before storage; valid blob + atomic DB settlement; DB rollback creates no authoritative artifact | GREEN |
| RED-044 | RED: blocked shell lacks audit view | committed query links authorization, candidate, plan, attempt, artifact, checksum, retrieval, manifest, document/citations and DQ terminal state; secret-free | GREEN |
| RED-045 | testability gap | observable reservation/network/settlement ordering; no open UoW during send; PostgreSQL atomic retry reservation; abandonment, failure audit, blob/DB rollback/orphan proof | GREEN |
| RED-049 | RED: blocked shell lacks terminal stage | DQ outcome and terminal live-validation run committed; artifact retained; no Snapshot/Research/Claim/Report/Stage11 composition | GREEN |

Step 1B-3 is complete only if:

- RED-043, RED-044, RED-045, and RED-049 are GREEN for the approved ownership-correct reasons;
- RED-028 through RED-042 and RED-046 through RED-048 remain GREEN;
- PostgreSQL proves concurrent retry reservation cannot permit a forbidden second retry socket;
- caller-owned Reservation / Settlement ordering proves no transaction is open during network;
- no schema or migration changed;
- no real network, DNS, credential value, Live, or model call occurred;
- Gate B remains `NO_GO`, unauthorized, and unexecuted;
- Stage 11 remains not started.

## Planned Production File Classification

### Create

- `src/stock_research_agent/domain/live_evidence/gate_b_pilot.py` — focused authorized pilot, UoW protocols, response/settlement orchestration, audit view, and terminal result.

### Modify only as demanded by REDs

- `src/stock_research_agent/domain/providers/sync.py` — application-supplied attempt identity and terminal settlement types.
- `src/stock_research_agent/domain/providers/repositories.py` — bounded attempt/artifact/audit/live-validation repository ports.
- `src/stock_research_agent/db/repositories/providers.py` — existing-table attempt/artifact/audit/live-validation persistence and query.
- `src/stock_research_agent/db/repositories/live_evidence.py` — PostgreSQL `SqlAlchemySecAttemptReservationPort` using existing consumption locks.
- `src/stock_research_agent/providers/sec_edgar/transport.py` — safe settlement facts only; no persistence.
- `src/stock_research_agent/infrastructure/provider_artifact_storage.py` — exact-key compensation only if existing blob port cannot perform it safely.
- `src/stock_research_agent/domain/live_evidence/document_bridge.py` — minimal provider-artifact adapter only if the existing request type cannot express committed lineage.
- `src/stock_research_agent/db/repositories/data_access.py` — bounded existing provider lookup only if the current `get_provider(code)` surface cannot be injected directly.
- `src/stock_research_agent/domain/live_evidence/gate_b_authorization.py` and `src/stock_research_agent/cli_live.py` — explicit authorized-pilot composition while the operator shell stays blocked.
- `src/stock_research_agent/domain/live_evidence/schemas.py` — result/query contracts only if import layering requires them outside `gate_b_pilot.py`.

### Reuse without change

- `src/stock_research_agent/providers/sec_edgar/adapter.py`
- `src/stock_research_agent/providers/sec_edgar/endpoints.py`
- `src/stock_research_agent/providers/sec_edgar/policy.py`
- `src/stock_research_agent/providers/sec_edgar/request_identity.py`
- `src/stock_research_agent/providers/sec_edgar/retry.py`
- `src/stock_research_agent/providers/retry.py`
- `src/stock_research_agent/providers/http_client.py`
- `src/stock_research_agent/domain/documents/identity.py`
- document parser/chunker and knowledge repository contracts
- `src/stock_research_agent/domain/providers/quality.py`
- ORM models and Alembic migrations

## Implementation Blocker Review

- `SCHEMA_CHANGE_BLOCKER = NO`: every required persisted fact has an existing table/column/FK; preallocated UUID and repository transitions are interface changes.
- `IMPLEMENTATION_BLOCKER = NO`: the repository exposes sufficient authorization, Sync Run, blob, artifact, Data Access, document, citation, DQ, audit, and live-validation primitives.
- Operational Gate B inputs remain intentionally unfrozen and do not block offline implementation: exact filing/accession/path set, as-of, retention, contact reference, grant, single-use approval, plan checksum, and fresh provider-policy verification.

## Safety State After Planning

```text
External Network = 0
DNS = 0
Credential value reads = 0
Live calls = 0
Model calls = 0

Gate B readiness = NO_GO
Gate B authorized = NO
Gate B executed = NO

Stage 11 = NOT STARTED
Step 1B-3 implementation = NOT STARTED
```
