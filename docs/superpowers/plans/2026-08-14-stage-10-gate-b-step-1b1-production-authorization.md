# Step 1B-1 Production Authorization Implementation Plan

> **Execution note:** implement this plan task by task with strict RED -> minimal GREEN ->
> regression discipline. Do not begin Step 1B-2 or Step 1B-3 while executing it.

**Goal:** Add the smallest production authorization composition that validates a finite,
secret-free Gate B authorization envelope and makes every future SEC execution structurally
dependent on a separately validated, persisted grant and single-use approval.

**Architecture:** A focused authorization module will distinguish an immutable but non-executable
authorization envelope from an `AuthorizedGateBExecution` capability. The capability can be
constructed only by a production gate that composes the existing grant checksum, event-derived
state, candidate scope, execution approval, and credential-reference metadata validators. A
transport-free SEC pilot shell exposes that gate upstream of the future Step 1B-2 transport and
continues to fail closed for every run operation.

**Tech stack:** Python 3.12, Pydantic 2 frozen/strict contracts, Typer composition factories,
SQLAlchemy domain record types (read/reuse only in this slice), pytest, Ruff, and mypy strict mode.

## Global constraints

- Baseline: `e0b5d1acba9e66781cc20eabaa55da0e91183baf` on
  `feat/stage-10-gate-b-1b1-production-authorization`.
- Gate B remains `NO_GO`, unauthorized, and unexecuted. Stage 11 remains not started.
- External network, DNS, credential-value reads, Live calls, and model calls remain zero.
- Authorization is structurally upstream of transport. No valid authorization means no executable
  SEC Live capability.
- Persisted contact resolver mechanism remains `ENVIRONMENT`; `DECLARED_CONTACT_IDENTITY` remains
  a transient binding role. This slice handles only reference metadata and never resolves or emits
  a User-Agent value.
- Do not modify generic `ProviderRetryPolicy`, generic HTTP timeout defaults, SEC transport,
  response/artifact/audit code, database schema, or migrations.
- Reuse `LiveAuthorizationGrantRecord`, event-derived state, `LiveExecutionApprovalRecord`, and
  their existing validators. Do not introduce a second authorization state machine.
- `create()` must return a non-executable authorization envelope. It must not be possible to obtain
  `AuthorizedGateBExecution` by validating an operator dictionary alone.
- No default grant, implicit approval, test-only production branch, hard-coded test identity,
  silent fallback, `skip`, `xfail`, or assertion weakening is permitted.

## Repository-backed architecture inventory

### Reuse without change

- `stock_research_agent.domain.providers.schemas.FrozenProviderContract` for strict, immutable,
  extra-forbidden input/result contracts with hidden Pydantic inputs.
- `stock_research_agent.domain.live_evidence.schemas.LiveAuthorizationGrantRecord`,
  `AuthorizationExecutionScope`, `LiveExecutionApprovalRecord`, and
  `ValidateExecutionApprovalRequest`.
- `stock_research_agent.domain.live_evidence.canonical.verify_grant_checksum`.
- `stock_research_agent.domain.live_evidence.authorization.require_active_authorization` and
  `validate_execution_scope`.
- `stock_research_agent.domain.live_evidence.execution_approval.ExecutionApprovalService.validate`.
- `stock_research_agent.domain.providers.credentials.CredentialReferenceRecord`,
  `CredentialResolverKind.ENVIRONMENT`, and
  `validate_credential_reference_metadata`.
- `stock_research_agent.domain.providers.sync.ProviderSyncPlanRecord` for authoritative plan ID,
  checksum, slice count, and exact persisted request parameters.
- `stock_research_agent.domain.providers.enums.ProviderCredentialStatus.CONFIGURED_METADATA_ONLY`.
- `stock_research_agent.cli_live.AuthorizationCliApplication`, `SecPilotCliApplication`, and their
  factories as the existing production composition seams.
- `stock_research_agent.db.repositories.live_evidence.reserve_consumption`,
  `settle_consumption`, and `consume_authorization` are deliberately not called or changed in this
  slice; they remain the later reservation/consumption boundary.

### Create

- `src/stock_research_agent/domain/live_evidence/gate_b_authorization.py`: bounded input/result
  contracts, the envelope application, the persisted-record authorization gate, and the
  transport-free SEC pilot shell.

### Modify

- `src/stock_research_agent/cli_live.py`: extend the protocols with the new bounded operations and
  replace only the two unconfigured factories with production, transport-free composition.

### Do not touch

- `src/stock_research_agent/domain/live_evidence/schemas.py`: the focused module can own the new
  bounded types; the shared schema file does not need more Gate-B-specific surface.
- `src/stock_research_agent/db/repositories/live_evidence.py`, provider/security repositories, ORM,
  migrations, credential resolver, HTTP client, retry, SEC endpoint/adapter, artifact, audit,
  ingestion, Claim, Report, and Stage 11 modules.

## Exact bounded interfaces

The implementation may use these new names because no existing abstraction represents the
non-executable Gate B envelope or the capability produced after all persisted authorization gates.
Do not add fields beyond those below unless an existing target test proves they are required.

```python
class GateBCandidate(FrozenProviderContract):
    security_id: UUID
    issuer_id: UUID
    symbol: str
    exchange: str
    cik: str


class GateBAuthorizationCreateRequest(FrozenProviderContract):
    provider: str
    candidate: GateBCandidate
    plan_id: UUID
    plan_checksum: Checksum
    allowed_hosts: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    max_resource_count: int
    max_actual_attempts: int
    retry_limit: int
    redirect_limit: int
    concurrency: int
    connect_timeout_seconds: int
    idle_read_timeout_seconds: int
    total_timeout_seconds: int
    contact_identity_reference: str
    grant_id: str
    single_use: bool
    approved_at: AwareUtcDateTime
    expires_at: AwareUtcDateTime


class GateBAuthorizationEnvelope(GateBAuthorizationCreateRequest):
    """Immutable, secret-free, non-executable validated input."""


class AuthorizedGateBExecution(FrozenProviderContract):
    authorization_id: UUID
    authorization_checksum: Checksum
    approval_id: UUID
    plan_id: UUID
    plan_checksum: Checksum
    provider: str
    security_id: UUID
    issuer_id: UUID
    provider_security_identifier: str
    credential_reference_id: UUID
    user_agent_reference_id: UUID


class ProductionAuthorizationApplication:
    def create(
        self, payload: Mapping[str, object]
    ) -> GateBAuthorizationEnvelope: ...

    def plan(self, authorization_id: UUID, checksum: str) -> dict[str, object]: ...
    def show(self, authorization_id: UUID) -> dict[str, object]: ...
    def activate(self, authorization_id: UUID, checksum: str) -> dict[str, object]: ...
    def revoke(self, authorization_id: UUID, checksum: str) -> dict[str, object]: ...


class ProductionAuthorizationGate:
    def authorize(
        self,
        envelope: GateBAuthorizationEnvelope,
        *,
        grant: LiveAuthorizationGrantRecord,
        events: tuple[LiveAuthorizationEventType, ...],
        approval: LiveExecutionApprovalRecord,
        plan: ProviderSyncPlanRecord,
        scope: AuthorizationExecutionScope,
        contact_reference: CredentialReferenceRecord,
        checked_at: datetime,
        approval_consumed: bool,
    ) -> AuthorizedGateBExecution: ...


class AuthorizationGatedSecPilotApplication:
    authorization_gate: ProductionAuthorizationGate

    def operate(
        self, operation: str, plan_id: UUID, plan_checksum: str
    ) -> dict[str, object]: ...
```

`GateBAuthorizationEnvelope` is not a grant record, execution approval, reservation, or transport
token. The opaque `grant_id` in the RED input remains a human authorization reference; it is not
silently coerced into `LiveAuthorizationGrantRecord.id` during input validation. At the executable
gate, it must equal `str(grant.id)` exactly. Only `ProductionAuthorizationGate` may produce
`AuthorizedGateBExecution`, and only after it receives and validates the authoritative persisted
grant, plan, and approval records. Loading/issuing the future real grant and approval remains an
explicit operational authorization action, not an implicit factory side effect.

## Error semantics

`ProductionAuthorizationApplication.create` must translate strict input-validation failures to
secret-free `LiveEvidenceValidationError` codes. Use one deterministic code per boundary:

- `GATE_B_PROVIDER_INVALID`
- `GATE_B_CANDIDATE_INVALID`
- `GATE_B_PLAN_INVALID`
- `GATE_B_GRANT_REFERENCE_INVALID`
- `GATE_B_SINGLE_USE_REQUIRED`
- `GATE_B_HOST_SCOPE_INVALID`
- `GATE_B_RESOURCE_BUDGET_INVALID`
- `GATE_B_ATTEMPT_BUDGET_INVALID`
- `GATE_B_REDIRECT_FORBIDDEN`
- `GATE_B_CONTACT_REFERENCE_INVALID`
- `GATE_B_AUTHORIZATION_WINDOW_INVALID`
- `LIVE_AUTHORIZATION_OPERATION_NOT_CONFIGURED` for the existing plan/show/activate/revoke CLI
  operations until a separately authorized persisted-record command composition is supplied.

The persisted-record gate preserves existing codes where they already define the contract:
`AUTH_CHECKSUM_INVALID`, `AUTHORIZATION_EXPIRED`, `AUTHORIZATION_REVOKED`,
`AUTH_RESERVATION_INVALID`, `AUTH_PROVIDER_MISMATCH`, `AUTH_CAPABILITY_MISMATCH`,
`AUTH_SECURITY_MISMATCH`, `AUTH_PROVIDER_IDENTIFIER_MISMATCH`,
`EXEC_APPROVAL_PLAN_MISMATCH`, `EXEC_APPROVAL_REPLAYED`, `EXEC_APPROVAL_EXPIRED`, and
`EXEC_APPROVAL_SIGNATURE_INVALID`. Add only `GATE_B_CONTACT_REFERENCE_INVALID` for the missing,
wrong-provider, wrong-resolver, wrong-declared-name, wrong-status, or wrong
`user_agent_reference_id` metadata boundary. No exception includes raw input payloads or resolved
credential material.

## Task 1 — RED-028 production authorization envelope

**Purpose:** Replace the unconfigured authorization factory with a production, dependency-free
factory that creates only an immutable, secret-free, non-executable authorization envelope.

**Files:**

- CREATE: `src/stock_research_agent/domain/live_evidence/gate_b_authorization.py`
- MODIFY: `src/stock_research_agent/cli_live.py`
- READ/REUSE: `domain/providers/schemas.py`, `domain/live_evidence/exceptions.py`
- TEST: `tests/unit/test_gate_b_production_authorization_red.py` (do not weaken or rewrite)

**Interfaces:**

- Consumes: `Mapping[str, object]` matching `GateBAuthorizationCreateRequest`.
- Produces: `GateBAuthorizationEnvelope`; never `AuthorizedGateBExecution`.

**Preconditions:** Branch and HEAD match this plan; working tree is clean; no environment or
credential values are read.

**Exact failing test:**

- `test_red_028_production_authorization_creation_composition_exists`

**Exact test command:**

```powershell
uv run pytest tests/unit/test_gate_b_production_authorization_red.py::test_red_028_production_authorization_creation_composition_exists -q
```

**Expected RED reason:** `authorization_application_factory()` raises
`LIVE_AUTHORIZATION_APPLICATION_NOT_CONFIGURED` before a production application is returned.

**Minimal production change:** Implement the strict candidate/request/envelope models and
`ProductionAuthorizationApplication.create`; update `AuthorizationCliApplication` with the exact
`create(payload) -> GateBAuthorizationEnvelope` operation; point
`authorization_application_factory` at a zero-I/O constructor. Keep existing plan/show/activate/
revoke CLI methods intact and blocked unless their existing composition is separately supplied.

**Important invariants:** The fixed provider is `SEC_EDGAR_PUBLIC_V1`; hosts are exact, sorted
`data.sec.gov` and `www.sec.gov`; paths are path-only strings; resource/attempt/retry/redirect/
concurrency/time limits equal the approved envelope; lifetime is positive and at most ten minutes;
`single_use` is true. These checks validate an input envelope only and do not issue a real grant.

**Forbidden changes:** No database access, grant auto-creation, execution approval, environment
resolution, HTTP policy, retry controller, timeout implementation, raw URL, or transport.

**Expected GREEN result:** The production factory returns an application; `create` returns an
immutable envelope with provider `SEC_EDGAR_PUBLIC_V1`, the supplied plan checksum, and
`single_use=True`.

**Regression command:**

```powershell
uv run pytest tests/unit/test_live_authorization_cli.py tests/unit/test_live_authorization_models.py tests/unit/test_live_authorization_canonical.py -q
```

**Commit boundary / suggested subject:** `feat: compose gate b authorization envelope`

- [ ] Task 1 exit: RED-028 and its focused CLI regression are GREEN; the returned object remains
  non-executable.

## Task 2 — RED-029 strict fail-closed input composition

**Purpose:** Make every invalid or incomplete authorization envelope fail before any executable
capability can exist.

**Files:**

- CREATE: none
- MODIFY: `src/stock_research_agent/domain/live_evidence/gate_b_authorization.py`
- READ/REUSE: `LiveEvidenceValidationError`, Pydantic strict/frozen validation
- TEST: `tests/unit/test_gate_b_production_authorization_red.py` (existing matrix unchanged)

**Interfaces:**

- Consumes: the same mapping accepted by `ProductionAuthorizationApplication.create`.
- Produces: envelope or a deterministic `LiveEvidenceValidationError`; never a partial result.

**Preconditions:** Task 1 is GREEN. Confirm the valid case still passes before adding each
fail-closed validator.

**Exact failing test:**

- `test_red_029_production_authorization_rejects_fail_closed_matrix`

**Exact test command:**

```powershell
uv run pytest tests/unit/test_gate_b_production_authorization_red.py::test_red_029_production_authorization_rejects_fail_closed_matrix -q
```

**Expected RED reason:** Once Task 1 exposes `create`, the bounded request does not yet reject the
full missing/wrong provider, missing candidate/plan/grant/contact, non-single-use, empty host,
resource > 3, attempt > 4, redirect > 0, and non-positive lifetime matrix with the required domain
failure type.

**Minimal production change:** Add field/model validators for the exact approved envelope and one
small exception-translation helper. Distinguish authorization input budgets from later runtime
enforcement: this task rejects an unauthorized request for excessive resource/attempt metadata;
it does not implement RED-034 attempt reservation or counting.

**Important invariants:** Unknown fields are forbidden; provider/candidate/plan are mandatory;
there is no default authorization, generated grant reference, implicit approval, or fallback. A
failed call returns no envelope and no capability.

**Forbidden changes:** Do not modify RED-029, loosen Pydantic strictness, catch arbitrary runtime
errors as validation success, or implement transport/runtime budgets.

**Expected GREEN result:** Every existing invalid update raises `LiveEvidenceValidationError`, and
the RED-028 valid envelope remains GREEN.

**Regression command:**

```powershell
uv run pytest tests/unit/test_gate_b_production_authorization_red.py::test_red_028_production_authorization_creation_composition_exists tests/unit/test_gate_b_production_authorization_red.py::test_red_029_production_authorization_rejects_fail_closed_matrix -q
```

**Commit boundary / suggested subject:** `fix: fail closed gate b authorization input`

- [ ] Task 2 exit: RED-029 rejects the complete matrix while RED-028 remains GREEN.

## Task 3 — RED-031 credential-reference metadata and persisted-record gate

**Purpose:** Bind the secret-free SEC contact reference and compose the existing persisted
grant/event/approval validators without resolving any credential value.

**Files:**

- CREATE: none
- MODIFY: `src/stock_research_agent/domain/live_evidence/gate_b_authorization.py`
- READ/REUSE: `canonical.py`, `authorization.py`, `execution_approval.py`,
  `domain/providers/credentials.py`, `domain/providers/enums.py`
- TEST: `tests/unit/test_gate_b_production_authorization_red.py`; add focused companion tests for
  gate success and wrong/missing credential-reference metadata without altering existing REDs

**Interfaces:**

- Consumes: envelope plus authoritative `LiveAuthorizationGrantRecord`, immutable event history,
  `LiveExecutionApprovalRecord`, `ProviderSyncPlanRecord`, `AuthorizationExecutionScope`,
  `CredentialReferenceRecord`, UTC check time, and consumed flag.
- Produces: `AuthorizedGateBExecution` only after every existing gate passes.

**Preconditions:** Tasks 1-2 are GREEN. Test fixtures construct domain records directly; they do
not read PostgreSQL, environment values, or credential managers.

**Exact failing test:**

- `test_red_031_authorization_binds_contact_reference_without_secret_value`
- New companion: `test_production_gate_requires_valid_persisted_grant_approval_and_contact_metadata`
- New companion: `test_production_gate_never_exposes_or_resolves_contact_value`

**Exact test command:**

```powershell
uv run pytest tests/unit/test_gate_b_production_authorization_red.py::test_red_031_authorization_binds_contact_reference_without_secret_value tests/unit/test_gate_b_production_authorization_red.py::test_production_gate_requires_valid_persisted_grant_approval_and_contact_metadata tests/unit/test_gate_b_production_authorization_red.py::test_production_gate_never_exposes_or_resolves_contact_value -q
```

**Expected RED reason:** The envelope does not yet preserve the reference in a safe result, and no
production gate composes checksum, state, scope, approval, and credential-reference metadata into
a capability.

**Minimal production change:** Preserve `contact_identity_reference` in the immutable envelope.
Implement `ProductionAuthorizationGate.authorize` in this exact order:

1. `verify_grant_checksum(grant)`.
2. Require `envelope.grant_id == str(grant.id)`, `plan.id == envelope.plan_id`, and
   `plan.plan_checksum == envelope.plan_checksum`.
3. Match envelope provider, candidate, exact hosts, resource count, and attempt limit to the grant,
   plan, and supplied execution scope. Preserve the declared path tuple as non-executable metadata;
   Step 1B-2 remains responsible for deriving and enforcing exact endpoint paths from persisted
   plan slices before send.
4. `require_active_authorization(grant, events, checked_at)`.
5. `validate_execution_scope(grant, scope)`.
6. `ExecutionApprovalService.validate(ValidateExecutionApprovalRequest(...))`; require `VALID`.
7. Require `contact_reference.id == grant.user_agent_reference_id`, the same provider definition,
   `CredentialResolverKind.ENVIRONMENT`, declared name `SEC_EDGAR_CONTACT_IDENTITY`, status
   `CONFIGURED_METADATA_ONLY`, and secret-free metadata.
8. Return the minimal `AuthorizedGateBExecution` IDs/checksums only.

**Important invariants:** The environment is never accessed. The credential value, hash, prefix,
suffix, derived fragment, User-Agent string, and raw header are absent from envelope, capability,
checksum, exception, repr, and logs. `DECLARED_CONTACT_IDENTITY` is not added as an enum.

**Forbidden changes:** No call to `EnvironmentCredentialResolver`; no new credential enum, DB
field, migration, formatter, User-Agent construction, or duplicated state/approval logic.

**Expected GREEN result:** RED-031 sees the reference and not the sentinel. Companion tests prove
that a valid persisted contract yields a secret-free capability and every wrong reference binding
fails closed.

**Regression command:**

```powershell
uv run pytest tests/unit/test_live_authorization_scope.py tests/unit/test_live_authorization_expiry.py tests/unit/test_live_authorization_state_machine.py tests/unit/test_live_execution_approval.py tests/unit/test_provider_live_authorization.py -q
```

**Commit boundary / suggested subject:** `feat: gate live execution on persisted authorization`

- [ ] Task 3 exit: RED-031 and the persisted-record/contact companion tests are GREEN with zero
  credential-value access.

## Task 4 — RED-046 no-Live structural gate

**Purpose:** Expose a production SEC pilot composition whose future transport is structurally
downstream of `ProductionAuthorizationGate`, while this slice remains incapable of sending.

**Files:**

- CREATE: none; keep the shell beside its authorization gate in
  `domain/live_evidence/gate_b_authorization.py`
- MODIFY: `src/stock_research_agent/cli_live.py`
- READ/REUSE: current `SecPilotCliApplication` protocol and `_sec_operation` fail-closed rendering
- TEST: `tests/unit/test_gate_b_sec_transport_red.py`; add one no-authorization/no-capability
  companion assertion without changing the existing RED

**Interfaces:**

- Consumes: operation, plan UUID, and checksum for the existing CLI surface.
- Produces: secret-free `BLOCKED` payload only; no transport/request object.

**Preconditions:** Task 3 has established the only capability constructor. No SEC transport or
credential resolver dependency exists in the shell constructor.

**Exact failing test:**

- `test_red_046_production_sec_run_requires_authorization_before_transport`
- New companion: `test_production_sec_shell_returns_no_executable_path_without_authorized_context`

**Exact test command:**

```powershell
uv run pytest tests/unit/test_gate_b_sec_transport_red.py::test_red_046_production_sec_run_requires_authorization_before_transport tests/unit/test_gate_b_sec_transport_red.py::test_production_sec_shell_returns_no_executable_path_without_authorized_context -q
```

**Expected RED reason:** `sec_pilot_application_factory()` raises
`LIVE_TRANSPORT_NOT_CONFIGURED`; no production object exposes an upstream `authorization_gate`.

**Minimal production change:** Add `authorization_gate` to the protocol; construct
`AuthorizationGatedSecPilotApplication(ProductionAuthorizationGate())`; point the SEC factory at
that shell. Until Step 1B-2 injects an executor that explicitly requires
`AuthorizedGateBExecution`, `operate` returns `BLOCKED` with both
`LIVE_AUTHORIZATION_REQUIRED` and `LIVE_TRANSPORT_NOT_CONFIGURED`. It never accepts raw URLs or a
transport dependency.

**Important invariants:** Authorization failure precedes transport construction. The shell has no
send/DNS/socket method. Future Step 1B-2 must accept `AuthorizedGateBExecution` as a constructor or
method dependency; it cannot make authorization optional.

**Forbidden changes:** No fake transport, request planning, endpoint construction, runtime contact
resolution, retry, timeout, artifact, audit, DQ, model, research orchestration, or Stage 11 call.

**Expected GREEN result:** RED-046 obtains a production object with callable `operate` and a real
`authorization_gate`. The companion proves an unauthenticated run returns no executable capability,
and RED-042 remains fail-closed with `LIVE_TRANSPORT_NOT_CONFIGURED` and no fallback language.

**Regression command:**

```powershell
uv run pytest tests/unit/test_gate_b_sec_transport_red.py::test_red_033_redirect_response_aborts_after_one_fake_attempt tests/unit/test_gate_b_sec_transport_red.py::test_red_041_sec_public_api_has_no_operator_raw_url_entrypoint tests/unit/test_gate_b_sec_transport_red.py::test_red_042_default_sec_failure_has_no_live_or_fixture_success_fallback tests/unit/test_gate_b_sec_transport_red.py::test_red_048_gate_b_modules_have_no_model_runtime_dependency tests/unit/test_sec_live_pilot_cli.py -q
```

**Commit boundary / suggested subject:** `feat: put sec pilot behind authorization gate`

- [ ] Task 4 exit: RED-046 is GREEN, RED-042 remains GREEN, and the production shell has no send
  capability.

## Task 5 — Target authorization and Gate B contract regression

**Purpose:** Prove the four 1B-1 REDs are GREEN, existing GREEN contracts stay GREEN, and later
slice REDs were not accidentally bypassed.

**Files:**

- CREATE: none
- MODIFY: only implementation defects revealed by Tasks 1-4, within the two approved production
  files
- READ/REUSE: all Gate B Step 1A contract tests
- TEST: the two Gate B RED files

**Interfaces:** No new interface; verify the bounded surface exactly as implemented.

**Preconditions:** Tasks 1-4 individually GREEN; no production file outside the approved boundary
changed.

**Exact target command (Level 1):**

```powershell
uv run pytest tests/unit/test_gate_b_production_authorization_red.py::test_red_028_production_authorization_creation_composition_exists tests/unit/test_gate_b_production_authorization_red.py::test_red_029_production_authorization_rejects_fail_closed_matrix tests/unit/test_gate_b_production_authorization_red.py::test_red_031_authorization_binds_contact_reference_without_secret_value tests/unit/test_gate_b_sec_transport_red.py::test_red_046_production_sec_run_requires_authorization_before_transport -q
```

**Expected result:** `4 passed` plus the new companion tests when selected. No skip, xfail, DNS,
socket, credential resolution, or environment-dependent success.

**Existing GREEN command (Level 2):**

```powershell
uv run pytest tests/unit/test_gate_b_production_authorization_red.py::test_red_030_authorization_is_immutable_and_execution_approval_is_single_use tests/unit/test_gate_b_production_authorization_red.py::test_red_040_authorization_binds_exact_sec_paths_not_only_hosts tests/unit/test_gate_b_production_authorization_red.py::test_red_047_authorization_binds_filing_path_and_plan_checksum tests/unit/test_gate_b_sec_transport_red.py::test_red_033_redirect_response_aborts_after_one_fake_attempt tests/unit/test_gate_b_sec_transport_red.py::test_red_041_sec_public_api_has_no_operator_raw_url_entrypoint tests/unit/test_gate_b_sec_transport_red.py::test_red_042_default_sec_failure_has_no_live_or_fixture_success_fallback tests/unit/test_gate_b_sec_transport_red.py::test_red_048_gate_b_modules_have_no_model_runtime_dependency -q
```

**Later-slice boundary command:**

```powershell
uv run pytest tests/unit/test_gate_b_sec_transport_red.py::test_red_032_production_sec_application_constructs_exact_offline_plan tests/unit/test_gate_b_sec_transport_red.py::test_red_035_http_429_is_never_retried_for_gate_b tests/unit/test_gate_b_sec_transport_red.py::test_red_036_retry_budget_is_global_across_the_whole_sec_plan tests/unit/test_gate_b_sec_transport_red.py::test_red_037_production_sec_timeout_configuration_matches_runbook tests/unit/test_gate_b_sec_transport_red.py::test_red_038_declared_contact_identity_contract_is_defined_without_secret_output tests/unit/test_gate_b_sec_transport_red.py::test_red_039_production_sec_allowlist_policy_exists_before_send tests/unit/test_gate_b_sec_transport_red.py::test_red_043_production_sec_pipeline_validates_before_artifact_persistence tests/unit/test_gate_b_production_authorization_red.py::test_red_044_audit_models_cover_gate_b_authorization_and_artifact_lineage tests/unit/test_gate_b_sec_transport_red.py::test_red_049_production_gate_b_stops_at_data_quality -q
```

**Expected later-slice result:** These nodes remain RED at their approved Step 1B-2/1B-3
boundaries. A new failure caused by an import, fixture, environment, or authorization regression is
unexpected. RED-034 remains a later runtime attempt-budget contract even though RED-029 already
rejects an over-broad authorization envelope.

**Important invariants:** Do not make later REDs GREEN with placeholders or generic blocked
payloads. Their expected assertions must still demand real transport/policy/artifact/audit/DQ
composition.

**Forbidden changes:** No test weakening, broad exception swallowing, fallback, or expansion into
Step 1B-2/1B-3.

**Commit boundary / suggested subject:** no separate commit unless a bounded regression fix was
required; otherwise retain the Task 1-4 commits.

- [ ] Task 5 exit: all four target REDs and all seven preserved GREEN contracts have the expected
  status; later-slice REDs remain at their approved boundaries.

## Task 6 — Relevant Stage 10 regression and static verification

**Purpose:** Verify the new composition does not regress existing authorization/domain/CLI safety
or offline Stage 10 isolation.

**Files:** No new files expected.

**Preconditions:** Task 5 classification is complete; only approved production/test files changed.

**Level 3 regression command:**

```powershell
uv run pytest tests/unit/test_live_authorization_models.py tests/unit/test_live_authorization_canonical.py tests/unit/test_live_authorization_state_machine.py tests/unit/test_live_authorization_consumption.py tests/unit/test_live_authorization_expiry.py tests/unit/test_live_authorization_revocation.py tests/unit/test_live_authorization_scope.py tests/unit/test_live_execution_approval.py tests/unit/test_provider_live_authorization.py tests/unit/test_live_authorization_cli.py tests/unit/test_sec_live_pilot_cli.py tests/unit/test_stage10_offline_isolation.py tests/unit/test_stage10_live_test_isolation.py tests/unit/test_stage10_security_matrix.py -q
```

This is the smallest meaningful Stage 10 unit regression for authorization, CLI fail-closed
behavior, offline isolation, and the security matrix. Do not invoke `live` tests or external
provider smoke tests. PostgreSQL budget/single-use tests are not required for this no-schema,
no-repository slice; if run voluntarily, use only the documented loopback `TEST_DATABASE_URL`.

**Static commands:**

```powershell
uv run ruff check src/stock_research_agent/domain/live_evidence/gate_b_authorization.py src/stock_research_agent/cli_live.py tests/unit/test_gate_b_production_authorization_red.py tests/unit/test_gate_b_sec_transport_red.py
uv run ruff format --check src/stock_research_agent/domain/live_evidence/gate_b_authorization.py src/stock_research_agent/cli_live.py tests/unit/test_gate_b_production_authorization_red.py tests/unit/test_gate_b_sec_transport_red.py
uv run mypy
git diff --check
```

**Expected GREEN result:** All selected existing suites and static checks pass; network, DNS,
credential values, Live calls, and model calls remain zero.

**Forbidden changes:** Do not run Live markers, read real environment contact values, or treat
later-slice expected REDs as implementation work.

**Commit boundary / suggested subject:** `fix: complete gate b authorization regressions` only if a
bounded implementation correction is needed; otherwise no new commit.

- [ ] Task 6 exit: relevant Stage 10 tests, Ruff, format, mypy, and `git diff --check` pass offline.

## Task 7 — Slice exit audit

**Purpose:** Prevent false completion and hand back a reviewable Step 1B-1 implementation without
starting the next slice.

**Preconditions:** Tasks 1-6 complete.

**Audit commands:**

```powershell
git status --short
git diff --check
git diff --name-only e0b5d1acba9e66781cc20eabaa55da0e91183baf..HEAD
git log --oneline e0b5d1acba9e66781cc20eabaa55da0e91183baf..HEAD
```

**Exit criteria:**

- RED-028, RED-029, RED-031, and RED-046 are GREEN.
- RED-030, RED-033, RED-040, RED-041, RED-042, RED-047, and RED-048 remain GREEN.
- The authorization factory exists and validates only a secret-free, non-executable envelope.
- `AuthorizedGateBExecution` can be produced only by the persisted-record authorization gate.
- The SEC pilot composition exposes that gate but contains no transport and sends nothing.
- Credential values were not read, resolved, persisted, hashed, logged, or returned.
- No schema, migration, generic retry, generic timeout, SEC transport, artifact, audit,
  transaction-boundary, DQ, research, Report, or Stage 11 change exists.
- Gate B remains `NO_GO`, unauthorized, and unexecuted.

**Stop condition:** Hand the implementation back for human review. Do not start Step 1B-2.

- [ ] Task 7 exit: the slice audit is recorded and implementation stops for human review.

## RED-to-seam map

| Contract | Current failure | Production seam | Minimal planned behavior |
|---|---|---|---|
| RED-028 | authorization factory raises `LIVE_AUTHORIZATION_APPLICATION_NOT_CONFIGURED` | `ProductionAuthorizationApplication.create` + CLI factory | strict immutable non-executable envelope |
| RED-029 | same missing factory; no production fail-closed matrix | request validators + safe error translation | reject every invalid envelope with no result/capability |
| RED-031 | same missing factory; no reference-bearing safe result | envelope + `ProductionAuthorizationGate` credential metadata check | preserve reference only; no resolution or secret material |
| RED-046 | SEC factory raises `LIVE_TRANSPORT_NOT_CONFIGURED` | `AuthorizationGatedSecPilotApplication.authorization_gate` + CLI factory | production gate exists upstream; unauthenticated run remains blocked and transport-free |

## Explicit scope exclusions

Step 1B-1 does not implement RED-032 SEC transport, RED-034 runtime attempt-budget enforcement,
RED-035 SEC 429 policy, RED-036 atomic global retry reservation, RED-037 SEC timeout policy,
RED-038 runtime contact resolution/header emission, RED-039 final allowlist enforcement, RED-043
Raw Artifact composition, RED-044 audit composition, RED-045 transaction ordering, or RED-049
committed Data Quality STOP. It does not create a real Gate B grant, freeze filing/accession data,
authorize Gate B, execute Gate B, or enter Stage 11.

## Blocker decision

- `IMPLEMENTATION_BLOCKER = NO`: the existing frozen domain contracts and CLI seams are sufficient
  for the bounded envelope, persisted-record gate, and transport-free shell.
- `SCHEMA_CHANGE_BLOCKER = NO`: this slice does not need to reconstruct or mutate authorization
  rows, issue an execution approval, reserve a budget, or add persisted contact fields. Actual
  operational grant/approval issuance remains a separately authorized action using existing schema.
