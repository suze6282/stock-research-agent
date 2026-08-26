# Step 1B-2 SEC Transport Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline-testable SEC Gate B transport controller that can send only from an `AuthorizedGateBExecution`, enforces the exact approved plan and one-attempt HTTP boundary, resolves protected contact identity at execution time, and owns SEC-specific retry decisions without persisting artifacts.

**Architecture:** The existing authorization capability remains upstream of a focused SEC plan binder and execution controller. The controller obtains a committed pre-send permit through an injected reservation port, resolves an ephemeral protected request identity, and delegates exactly one physical GET to `SafeHttpClient`; it alone decides whether a terminal outcome may request the one plan-global retry. Step 1B-2 defines and unit-tests the reservation port and no-send ordering, while Step 1B-3 supplies the PostgreSQL-backed atomic implementation and concurrency proof.

**Tech Stack:** Python 3.12, Pydantic 2 frozen contracts, httpx `MockTransport`, the existing `SafeHttpClient`, SEC endpoint policies, provider credential resolver contracts, pytest, Ruff, and strict mypy.

## Global Constraints

- Baseline: `c704341bbf57718b887bfb221b36532819469344` on `feat/stage-10-gate-b-1b2-sec-transport`.
- Gate B remains `NO_GO`, unauthorized, and unexecuted. Stage 11 remains not started.
- External network, DNS, credential-value reads, Live calls, and model calls remain zero during implementation and tests.
- Every physical SEC attempt is structurally downstream of `AuthorizedGateBExecution` and a committed `SecAttemptPermit`.
- `GateBAuthorizationEnvelope` remains non-executable; operator input cannot be accepted in place of `AuthorizedGateBExecution`.
- Persisted contact resolver kind remains `CredentialResolverKind.ENVIRONMENT`; `DECLARED_CONTACT_IDENTITY` is not added to a database enum.
- Resolved contact material is ephemeral, non-serializable, redacted, and unwrapped only at final protected `User-Agent` emission.
- Generic `ProviderRetryPolicy` remains unchanged and continues to treat 429 according to its shared policy.
- Generic `HttpClientPolicy` defaults remain connect/read/total `5/15/30`, redirects `3`, and attempts `3`.
- SEC Gate B policy is connect/read/total `10/30/120`, redirects `0`, HTTP-client attempts `1`, concurrency `1`, resource count at most `3`, actual attempts at most `4`, and plan-global retries at most `1`.
- `SEC_ENDPOINT_POLICIES` and the checksum-bound `ProviderSyncPlanRecord` are the single source of truth for method, scheme, host, port, path, accepted content types, and resource identity.
- No raw URL, host-only authorization, redirect following, hidden HTTP retry, fallback provider, fixture-as-Live success, or test-only production branch is permitted.
- Step 1B-2 does not persist a Raw Artifact, attempt audit, ingestion manifest, Data Quality result, Citation, Evidence, Claim, Report, or Stage 11 state.
- No schema, ORM, repository, or migration change belongs in this slice.
- No `skip`, `xfail`, weakened assertion, hard-coded authorization bypass, environment-dependent success, or secret-bearing error/result is permitted.

---

## Repository-Backed Architecture Inventory

### Reuse without change

- `stock_research_agent.domain.live_evidence.gate_b_authorization.AuthorizedGateBExecution` as the only executable authorization capability.
- `ProductionAuthorizationGate.authorize(...) -> AuthorizedGateBExecution`; no second authorization state machine is introduced.
- `ProviderSyncPlanRecord`, `ProviderSyncSlice`, and `build_plan_checksum` for the immutable plan identity and persisted slice material.
- `SEC_ENDPOINT_POLICIES` and `build_sec_request(...) -> CanonicalProviderRequest` for exact GET-only SEC request construction.
- `HttpRequest`, `HttpResult`, `SafeHttpClient`, response-size limits, URL validation, DNS/IP safety, protected-header replacement, rate limiting, and redirect rejection.
- `EnvironmentCredentialResolver` and `CredentialReferenceRecord` for explicit injected-mapping resolution after authorization.
- `ProviderRetryOutcome` and `RetryDecision` as generic outcome/decision vocabulary only; `ProviderRetryPolicy.classify` is not called by the SEC controller.
- `ConsumptionReservationRequest`, `reserve_consumption`, and the authorization row-lock pattern as evidence for the Step 1B-3 reservation adapter; Step 1B-2 does not call the SQLAlchemy repository.
- `ProviderRequestAttemptWrite` and `ProviderSyncRunRecord.consumed_attempts` as the existing persisted attempt lineage; no new column is required.

### Create

- `src/stock_research_agent/providers/sec_edgar/policy.py`: SEC policy constants, exact plan binding, and `build_sec_http_client_policy`.
- `src/stock_research_agent/providers/sec_edgar/request_identity.py`: SEC contact-reference-to-protected-identity composition without environment ownership.
- `src/stock_research_agent/providers/sec_edgar/retry.py`: the sole SEC retry classifier/controller and the atomic reservation port contract.
- `src/stock_research_agent/providers/sec_edgar/transport.py`: one-attempt sender, bounded transport result, and authorization/permit-gated controller.
- `tests/unit/test_sec_gate_b_transport.py`: ownership-correct companion REDs for runtime attempt safety, protected identity, one-attempt transport, and structural authorization.

### Modify

- `src/stock_research_agent/providers/credentials.py`: add the minimal protected request-identity type and a resolver operation that never returns a printable/header mapping.
- `src/stock_research_agent/providers/http_client.py`: accept protected identity separately from printable policy metadata and allow an SEC policy to disable its internal HTTP-status retry set while preserving generic defaults.
- `src/stock_research_agent/domain/live_evidence/gate_b_authorization.py`: make the existing transport-free shell describe the fixed SEC policy for `plan`; keep `run` blocked unless an authorized controller is explicitly supplied.
- `src/stock_research_agent/cli_live.py`: compose the policy-aware but still operationally blocked SEC shell; do not resolve credentials or construct a network client in the factory.
- `tests/unit/test_gate_b_sec_transport_red.py`: correct RED-035/036/037/038/039 to target their human-approved owners and retain the existing RED identifiers and safety intent.
- `tests/unit/test_provider_http_client.py`: add protected-header, no-hidden-retry, and generic-default preservation regressions.
- `tests/unit/test_provider_credential_resolver.py`: add protected SEC request-identity validation/redaction tests using an explicit fake mapping.

### Do not touch

- `src/stock_research_agent/providers/retry.py`: generic retry semantics and defaults remain unchanged.
- `src/stock_research_agent/providers/sec_edgar/adapter.py`: planning and parsing are already deterministic; transport does not belong in the adapter.
- `src/stock_research_agent/domain/live_evidence/schemas.py`, `db/repositories/live_evidence.py`, provider repositories, ORM, and migrations: the production reservation adapter and concurrency proof are Step 1B-3.
- Artifact storage, ingestion, DocumentVersion, Citation, Data Quality, Evidence, Claim, Package, Report, release, and Stage 11 modules.

## Exact New Interfaces

These focused types are required because the repository has no protected User-Agent material, no authorization-bound SEC plan, no pre-send attempt capability, and no SEC-specific retry authority.

```python
# providers/credentials.py
class ProviderRequestIdentityExecutionRequest(FrozenProviderContract):
    provider_definition_id: UUID
    credential_reference_id: UUID
    declared_name: str
    license_allowed: bool
    configuration_allowed: bool
    live_authorized: bool


class ProtectedRequestIdentity:
    def __init__(self, value: str) -> None: ...
    def __repr__(self) -> str: ...  # always redacted
    def __reduce__(self) -> NoReturn: ...  # non-serializable
    def _emit_user_agent(self) -> str: ...  # called only by SafeHttpClient


class EnvironmentCredentialResolver:
    def resolve_request_identity(
        self,
        reference: CredentialReferenceRecord,
        request: ProviderRequestIdentityExecutionRequest,
    ) -> ProtectedRequestIdentity: ...
```

`ProtectedRequestIdentity` rejects empty values, values longer than 256 characters, CR, LF, DEL, and every character below ASCII 32. Its value, hash, prefix, suffix, or derived fragment never appears in `repr`, `str`, exceptions, plans, grants, results, or audit metadata.

```python
# providers/sec_edgar/policy.py
class SecAuthorizedResource(FrozenProviderContract):
    plan_id: UUID
    plan_checksum: Checksum
    slice_id: str
    ordinal: int
    request: CanonicalProviderRequest
    max_response_bytes: int


class SecAuthorizedPlan(FrozenProviderContract):
    plan_id: UUID
    plan_checksum: Checksum
    resources: tuple[SecAuthorizedResource, ...]

    def require_resource(self, slice_id: str) -> SecAuthorizedResource: ...


def bind_sec_authorized_plan(
    execution: AuthorizedGateBExecution,
    plan: ProviderSyncPlanRecord,
) -> SecAuthorizedPlan: ...


def build_sec_http_client_policy(*, network_enabled: bool) -> HttpClientPolicy: ...
```

`bind_sec_authorized_plan` revalidates each persisted slice through `ProviderSyncSlice.model_validate`, requires plan ID/checksum equality with the capability, requires one to three unique ordered slices, requires the capability CIK on every slice, and rebuilds every URL only through `build_sec_request`. It accepts no URL, host, path, or header argument from an operator.

```python
# providers/sec_edgar/retry.py
class SecAttemptKind(StrEnum):
    INITIAL = "INITIAL"
    RETRY = "RETRY"


class SecAttemptReservationRequest(FrozenProviderContract):
    authorization_id: UUID
    plan_id: UUID
    plan_checksum: Checksum
    slice_id: str
    endpoint_id: str
    attempt_number: int
    kind: SecAttemptKind


class SecAttemptPermit(SecAttemptReservationRequest):
    request_attempt_id: UUID


class SecAttemptReservationPort(Protocol):
    def reserve(self, request: SecAttemptReservationRequest) -> SecAttemptPermit: ...


class SecGateBRetryController:
    def classify(
        self,
        outcome: ProviderRetryOutcome,
        *,
        execution: AuthorizedGateBExecution,
        resource: SecAuthorizedResource,
        previous_attempt: SecAttemptPermit,
        reservations: SecAttemptReservationPort,
    ) -> RetryDecision | SecAttemptPermit: ...
```

The controller returns a terminal `RetryDecision(retry=False, ...)` for 429 and non-approved outcomes. For an approved timeout/connection failure or 500/502/503/504, it asks the authoritative port for attempt number 2. A retry exists only if the port returns the matching permit. A refusal/exception produces no permit and therefore cannot reach DNS or `send_start`. The PostgreSQL port must atomically count and reserve under the authorization/Sync Run lock in Step 1B-3; an in-memory counter is never production wiring.

```python
# providers/sec_edgar/transport.py
class SecPhysicalAttempt(FrozenProviderContract):
    permit: SecAttemptPermit
    response: HttpResult | None
    safe_error_code: str | None


class SecTransportStatus(StrEnum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class SecTransportResult(FrozenProviderContract):
    status: SecTransportStatus
    reason_code: str
    attempts: tuple[SecPhysicalAttempt, ...]


class SecGateBTransportController:
    def execute(
        self,
        execution: AuthorizedGateBExecution,
        *,
        plan: ProviderSyncPlanRecord,
        slice_id: str,
        contact_reference: CredentialReferenceRecord,
    ) -> SecTransportResult: ...
```

The controller constructor receives `EnvironmentCredentialResolver`, `SecAttemptReservationPort`, `SecGateBRetryController`, and a one-attempt HTTP client factory. It binds the plan, reserves attempt 1, resolves the contact identity, sends exactly once, and only the SEC retry controller may request attempt 2. No public method accepts a raw URL or an authorization envelope.

## Error Semantics

Use deterministic, secret-free codes. Existing safe HTTP errors remain authoritative where applicable. New SEC boundary codes are:

- `SEC_AUTHORIZED_PLAN_MISMATCH`: capability and persisted plan ID/checksum differ.
- `SEC_PLAN_RESOURCE_INVALID`: persisted slice is malformed, duplicated, out of order, over three resources, or not reproducible through `build_sec_request`.
- `SEC_PLAN_RESOURCE_NOT_FOUND`: requested slice is not in the authorized plan.
- `SEC_CONTACT_REFERENCE_INVALID`: the reference ID/name/provider/resolver/status does not match the capability.
- `SEC_CONTACT_IDENTITY_INVALID`: resolved identity is empty, too long, or contains a control character; the message contains no value.
- `SEC_ATTEMPT_RESERVATION_REQUIRED`: no committed, matching permit exists before send.
- `SEC_ATTEMPT_BUDGET_EXHAUSTED`: the authoritative port refuses an initial physical attempt.
- `SEC_RETRY_BUDGET_EXHAUSTED`: the authoritative port refuses the one plan-global retry.
- `SEC_HTTP_429_ABORT`: 429 is terminal with one physical attempt.
- `SEC_TRANSIENT_RETRY_EXHAUSTED`: the approved one retry also ends in a transient failure.
- `SEC_TRANSPORT_BLOCKED`: a typed network/policy failure produced no successful response.

No code includes contact material, request headers, raw environment values, or unsafe URLs.

## Current RED and False-Green Classification

| Contract | Current status at baseline | False-green risk | Actual reason / correction |
|---|---|---|---|
| RED-032 | RED | Low | `operate("plan")` returns `BLOCKED`, so production SEC policy/plan composition is absent. |
| RED-034 | GREEN only at authorization input | **High** | `ProductionAuthorizationApplication.create` rejects `max_actual_attempts=5`; no physical-attempt reservation or pre-send enforcement exists. Add a runtime companion RED. |
| RED-035 | RED | **High (wrong owner)** | The test calls shared `ProviderRetryPolicy`, which intentionally retries 429. Retarget the unchanged 429/no-retry safety intent to `SecGateBRetryController`. |
| RED-036 | RED | **High (wrong owner and no atomic port)** | Two independent shared-policy classifications both retry. Retarget to the SEC controller plus reservation port; final PostgreSQL concurrency GREEN remains Step 1B-3. |
| RED-037 | RED | **High (wrong owner)** | The test constructs generic defaults and sees `5/15/30`. Retarget to `build_sec_http_client_policy` and separately assert generic defaults remain unchanged. |
| RED-038 | RED | **High (superseded assertion)** | The test asks for forbidden enum `DECLARED_CONTACT_IDENTITY`. Replace that assertion with fake resolver, protected identity, validation, and final-emission redaction coverage. |
| RED-039 | RED | Medium | No SEC policy factory exists; exact endpoint construction exists, but policy/plan-to-send binding does not. |

---

### Task 1: Freeze Ownership-Correct REDs and Build the SEC Policy Factory

**Purpose:** Make RED-037 and RED-039 demand the approved SEC-specific owner while proving generic defaults and RED-033 remain unchanged.

**Files:**
- CREATE: `src/stock_research_agent/providers/sec_edgar/policy.py`
- MODIFY: `src/stock_research_agent/providers/http_client.py`, `tests/unit/test_gate_b_sec_transport_red.py`, `tests/unit/test_provider_http_client.py`
- READ/REUSE: `src/stock_research_agent/providers/http_client.py`, `providers/sec_edgar/endpoints.py`
- TEST: `tests/unit/test_gate_b_sec_transport_red.py`, `tests/unit/test_provider_http_client.py`, `tests/unit/test_sec_edgar_endpoints.py`

**Interfaces:**
- Consumes: immutable `SEC_ENDPOINT_POLICIES` and explicit `network_enabled: bool`.
- Produces: `build_sec_http_client_policy(*, network_enabled: bool) -> HttpClientPolicy` with safe metadata only.

**Preconditions:** Baseline and branch match this plan; working tree is clean; no environment mapping or transport is constructed.

**Exact failing tests:**
- `test_red_037_production_sec_timeout_configuration_matches_runbook`
- `test_red_039_production_sec_allowlist_policy_exists_before_send`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_gate_b_sec_transport_red.py::test_red_037_production_sec_timeout_configuration_matches_runbook tests/unit/test_gate_b_sec_transport_red.py::test_red_039_production_sec_allowlist_policy_exists_before_send -q
```

**Observed/current RED reason:** RED-037 observes the correct generic defaults from the wrong factory. RED-039 cannot find a callable SEC policy factory.

**Minimal production change:** First extend `HttpClientPolicy` backwards-compatibly with `user_agent: str | None` and `retryable_status_codes: frozenset[int]`, whose default is the current global 429/500/502/503/504 set. Validation accepts `None` as a protected-identity-required policy state but otherwise preserves the existing string checks; until Task 4 supplies the protected identity, `SafeHttpClient.get` must fail with a constant policy error before URL validation or DNS whenever `user_agent is None`. Add `build_sec_http_client_policy` in `policy.py`. Derive allowed hosts as a frozen set from `SEC_ENDPOINT_POLICIES`; set connect/read/total `10/30/120`, redirects `0`, attempts `1`, and an empty internal HTTP-status retry set. Do not place resolved contact material in the policy. Change the two REDs to import the SEC factory; RED-037 also creates a generic policy and asserts `5/15/30` remains unchanged.

```python
def build_sec_http_client_policy(*, network_enabled: bool) -> HttpClientPolicy:
    return HttpClientPolicy(
        allowed_hosts=frozenset(policy.host for policy in SEC_ENDPOINT_POLICIES.values()),
        user_agent=None,
        network_enabled=network_enabled,
        connect_timeout_seconds=10,
        read_timeout_seconds=30,
        total_timeout_seconds=120,
        max_redirects=0,
        max_attempts=1,
        retryable_status_codes=frozenset(),
    )
```

**Important invariants:** The host set is derived, not duplicated. Policy creation performs no DNS. `network_enabled` remains explicit. Empty internal retry statuses plus `max_attempts=1` prevent a hidden HTTP retry loop.

**Forbidden changes:** Do not alter the values of generic defaults, generic retry status constants, endpoint templates, redirects, or response persistence.

**Expected GREEN:** Exact SEC values are returned, generic `5/15/30` remains GREEN, host set is exactly `data.sec.gov` and `www.sec.gov`, a policy with no printable or protected identity fails before DNS, and RED-033 still aborts redirects after one fake attempt.

**Regression command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_sec_edgar_endpoints.py tests/unit/test_provider_http_client.py::test_http_client_policy_rejects_unsafe_bounds tests/unit/test_gate_b_sec_transport_red.py::test_red_033_redirect_response_aborts_after_one_fake_attempt -q
```

**Commit boundary / suggested subject:** `feat: add sec gate b transport policy`

- [ ] Write the ownership-correct RED-037/039 assertions.
- [ ] Run the exact RED command and confirm missing SEC policy behavior.
- [ ] Add the minimal factory and the two backwards-compatible policy fields; do not change the send path yet.
- [ ] Run the exact GREEN and regression commands.
- [ ] Commit only the focused policy/test change.

### Task 2: Bind the Authorized Persisted Plan to Exact SEC Resources

**Purpose:** Make RED-032 and RED-039 prove deterministic method/host/path membership rather than host-only policy.

**Files:**
- CREATE: none beyond `providers/sec_edgar/policy.py`
- MODIFY: `src/stock_research_agent/providers/sec_edgar/policy.py`, `domain/live_evidence/gate_b_authorization.py`, `cli_live.py`, `tests/unit/test_gate_b_sec_transport_red.py`
- READ/REUSE: `domain/providers/sync.py`, `providers/sec_edgar/endpoints.py`, `providers/http_policy.py`
- TEST: `tests/unit/test_gate_b_sec_transport_red.py`, `tests/unit/test_sec_edgar_endpoints.py`, `tests/unit/test_sec_edgar_planner.py`

**Interfaces:**
- Consumes: `AuthorizedGateBExecution`, `ProviderSyncPlanRecord`, and a slice ID.
- Produces: `SecAuthorizedPlan` containing only `SecAuthorizedResource` values rebuilt through `build_sec_request`.

**Preconditions:** Task 1 policy factory is GREEN. Use deterministic domain records; no repository or PostgreSQL is involved.

**Exact failing tests:**
- `test_red_032_production_sec_application_constructs_exact_offline_plan`
- `test_red_039_production_sec_allowlist_policy_exists_before_send`
- Companion `test_red_039_authorized_plan_rejects_forged_host_path_or_cik_before_sender`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_gate_b_sec_transport_red.py::test_red_032_production_sec_application_constructs_exact_offline_plan tests/unit/test_gate_b_sec_transport_red.py::test_red_039_production_sec_allowlist_policy_exists_before_send tests/unit/test_sec_gate_b_transport.py::test_red_039_authorized_plan_rejects_forged_host_path_or_cik_before_sender -q
```

**Observed/current RED reason:** The production SEC shell always returns `BLOCKED`; no capability-bound plan binder verifies persisted slices or exposes the fixed offline policy description.

**Minimal production change:** Implement `SecAuthorizedResource`, `SecAuthorizedPlan.require_resource`, and `bind_sec_authorized_plan`. Revalidate serialized slices, compare plan ID/checksum to the capability, require slice count equality and at most three resources, compare every slice CIK with `execution.provider_security_identifier`, rebuild each canonical request, and reject every malformed or extra request parameter that can widen identity. Add a policy descriptor dependency to `AuthorizationGatedSecPilotApplication`; `operate("plan", ...)` returns only `NOT_ATTEMPTED`, `GET`, the exact allowed hosts, and maximum planned-resource count. `operate("run", ...)` remains blocked without an authorized controller and permit port.

```python
def bind_sec_authorized_plan(
    execution: AuthorizedGateBExecution,
    plan: ProviderSyncPlanRecord,
) -> SecAuthorizedPlan:
    if plan.id != execution.plan_id or plan.plan_checksum != execution.plan_checksum:
        raise LiveEvidenceValidationError("SEC_AUTHORIZED_PLAN_MISMATCH")
    slices = tuple(ProviderSyncSlice.model_validate(value) for value in plan.slices)
    # Validate count/order/CIK and build only via build_sec_request.
    return SecAuthorizedPlan(plan_id=plan.id, plan_checksum=plan.plan_checksum, resources=resources)
```

**Important invariants:** Neither binder nor CLI accepts `url`. A valid host with an unapproved path is rejected because the transport receives only a resource returned by the plan binder. The CLI policy description is non-executable and does not freeze a real filing.

**Forbidden changes:** Do not fabricate three filing resources, accept an operator path, store a second endpoint registry, create transport, or make `run` succeed.

**Expected GREEN:** RED-032 returns the offline policy description; exact binder tests accept a canonical persisted plan and reject changed CIK/endpoint/path/checksum before any sender is called. RED-041 remains GREEN.

**Regression command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_sec_edgar_endpoints.py tests/unit/test_sec_edgar_planner.py tests/unit/test_gate_b_sec_transport_red.py::test_red_041_sec_public_api_has_no_operator_raw_url_entrypoint tests/unit/test_gate_b_sec_transport_red.py::test_red_042_default_sec_failure_has_no_live_or_fixture_success_fallback -q
```

**Commit boundary / suggested subject:** `feat: bind authorized sec request plan`

- [ ] Add the exact plan-binding companion RED.
- [ ] Run the exact RED command and record the missing binder/shell behavior.
- [ ] Implement only deterministic plan binding and the non-executable plan descriptor.
- [ ] Run GREEN and regression commands.
- [ ] Commit the exact plan binding separately from transport.

### Task 3: Resolve and Validate Protected SEC Contact Identity

**Purpose:** Replace the superseded RED-038 enum assertion with the approved runtime protected-identity contract using an injected fake environment mapping.

**Files:**
- CREATE: `src/stock_research_agent/providers/sec_edgar/request_identity.py`
- MODIFY: `src/stock_research_agent/providers/credentials.py`, `tests/unit/test_gate_b_sec_transport_red.py`, `tests/unit/test_provider_credential_resolver.py`
- READ/REUSE: `domain/providers/credentials.py`, `domain/providers/enums.py`, `gate_b_authorization.py`
- TEST: `tests/unit/test_provider_credential_resolver.py`, `tests/unit/test_sec_gate_b_transport.py`

**Interfaces:**
- Consumes: `AuthorizedGateBExecution`, matching `CredentialReferenceRecord`, and injected `EnvironmentCredentialResolver`.
- Produces: `ProtectedRequestIdentity`; no string/header mapping is returned from SEC composition.

**Preconditions:** Task 2 is GREEN. The test resolver is constructed only with `{ "SEC_EDGAR_CONTACT_IDENTITY": "SECRET_SENTINEL_DO_NOT_LOG" }`; `os.environ`, `os.getenv`, and credential managers are not read.

**Exact failing tests:**
- Retargeted `test_red_038_declared_contact_identity_contract_is_defined_without_secret_output`
- Companion `test_red_038_invalid_contact_material_fails_without_value_leak`
- Companion `test_red_038_sec_identity_requires_authorized_matching_reference`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_gate_b_sec_transport_red.py::test_red_038_declared_contact_identity_contract_is_defined_without_secret_output tests/unit/test_sec_gate_b_transport.py::test_red_038_invalid_contact_material_fails_without_value_leak tests/unit/test_sec_gate_b_transport.py::test_red_038_sec_identity_requires_authorized_matching_reference -q
```

**Observed/current RED reason:** The current test asks for a forbidden persisted resolver enum. The repository has only a generic printable `ResolvedCredentialContext.bind_header()` path and no protected User-Agent material or SEC runtime composition.

**Minimal production change:** Add `ProviderRequestIdentityExecutionRequest`, `ProtectedRequestIdentity`, and `EnvironmentCredentialResolver.resolve_request_identity`. Factor shared reference/gate checks into a private resolver helper; do not change existing token/header binding behavior. Add `resolve_sec_request_identity(...)` that verifies capability reference ID, provider `SEC_EDGAR_PUBLIC_V1`, `ENVIRONMENT`, declared name, and configured metadata before invoking the injected resolver.

```python
def resolve_sec_request_identity(
    execution: AuthorizedGateBExecution,
    reference: CredentialReferenceRecord,
    resolver: EnvironmentCredentialResolver,
) -> ProtectedRequestIdentity:
    if reference.id != execution.user_agent_reference_id:
        raise LiveEvidenceValidationError("SEC_CONTACT_REFERENCE_INVALID")
    return resolver.resolve_request_identity(
        reference,
        ProviderRequestIdentityExecutionRequest(
            provider_definition_id=reference.provider_definition_id,
            credential_reference_id=reference.id,
            declared_name="SEC_EDGAR_CONTACT_IDENTITY",
            license_allowed=True,
            configuration_allowed=True,
            live_authorized=True,
        ),
    )
```

**Important invariants:** `repr`/`str` are fixed redacted text; serialization raises `TypeError`; validation errors are constant codes; no value/hash/fragment is returned. `DECLARED_CONTACT_IDENTITY` remains absent from `CredentialResolverKind`.

**Forbidden changes:** No ambient environment access, new DB enum, migration, printable User-Agent policy, logging, audit field, or header dict returned to the SEC application.

**Expected GREEN:** The fake resolver produces a protected identity, invalid values fail without sentinel leakage, wrong reference fails before resolution, and existing credential resolver tests remain GREEN.

**Regression command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_provider_credential_resolver.py tests/unit/test_provider_credential_references.py tests/unit/test_gate_b_production_authorization_red.py::test_existing_resolved_contact_context_cannot_be_logged_or_serialized -q
```

**Commit boundary / suggested subject:** `feat: protect sec request identity`

- [ ] Replace only the superseded RED-038 owner assertion with the approved contract.
- [ ] Run RED and confirm protected identity is missing.
- [ ] Implement the minimal protected type/resolver composition.
- [ ] Run GREEN and credential regressions.
- [ ] Commit without any real credential or environment dependency.

### Task 4: Add the Final Protected Header and One-Physical-Attempt HTTP Boundary

**Purpose:** Make `SafeHttpClient` emit protected SEC identity only on the wire and make the SEC policy incapable of hidden HTTP-status retries.

**Files:**
- CREATE: none
- MODIFY: `src/stock_research_agent/providers/http_client.py`, `tests/unit/test_provider_http_client.py`, `tests/unit/test_sec_gate_b_transport.py`
- READ/REUSE: `providers/http_redaction.py`, `providers/errors.py`
- TEST: `tests/unit/test_provider_http_client.py`, `tests/unit/test_sec_gate_b_transport.py`

**Interfaces:**
- Consumes: `HttpClientPolicy`, optional `ProtectedRequestIdentity`, and existing injected mock transport/resolver.
- Produces: unchanged `HttpResult`; the protected value exists only in the final httpx request header.

**Preconditions:** Task 3 protected identity is GREEN. All sends use `httpx.MockTransport` and a fixed public-IP resolver lambda; no DNS or socket occurs.

**Exact failing tests:**
- `test_red_038_protected_identity_unwraps_only_at_final_user_agent_emission`
- `test_sec_policy_performs_one_physical_attempt_for_429_and_503`
- `test_sec_policy_without_protected_identity_fails_before_dns_or_send`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_sec_gate_b_transport.py::test_red_038_protected_identity_unwraps_only_at_final_user_agent_emission tests/unit/test_sec_gate_b_transport.py::test_sec_policy_performs_one_physical_attempt_for_429_and_503 tests/unit/test_sec_gate_b_transport.py::test_sec_policy_without_protected_identity_fails_before_dns_or_send -q
```

**Observed/current RED reason:** `HttpClientPolicy.user_agent` is a required printable string, and `SafeHttpClient` owns a fixed global retryable-status set that raises/retries 429/5xx internally.

**Minimal production change:** Make `HttpClientPolicy.user_agent` accept `str | None`; add `retryable_status_codes` with the current global set as its default. Add optional `request_identity` to `SafeHttpClient.__init__`. At the start of `get`, before URL validation/DNS, require either the protected identity or a printable generic policy User-Agent. At final protected-header construction, call `_emit_user_agent()` and never retain the returned string outside the local header dictionary. Use `self._policy.retryable_status_codes` instead of the module constant in the retry loop.

```python
class SafeHttpClient:
    def __init__(
        self,
        policy: HttpClientPolicy,
        *,
        cache: ResponseCache,
        rate_limiter: RateLimiter,
        request_identity: ProtectedRequestIdentity | None = None,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None: ...
```

**Important invariants:** Generic callers receive identical defaults and retry behavior. Arbitrary `HttpRequest.headers` cannot override User-Agent. SEC 429/5xx are returned after one physical attempt for controller classification. Protected identity is absent from object reprs, exceptions, `HttpResult`, and logs.

**Forbidden changes:** Do not remove SSRF/DNS/rate/size/deadline enforcement, change generic retry tests, add a raw-header API, or let missing identity reach DNS.

**Expected GREEN:** Mock transport sees the sentinel exactly once only as `User-Agent`; callers/reprs/results do not. SEC policy sends 429/503 once and returns them. Generic policy still retries 429 and approved 5xx exactly as before.

**Regression command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_provider_http_client.py tests/unit/test_provider_http_redaction.py tests/unit/test_provider_ssrf_policy.py tests/unit/test_provider_retry_policy.py -q
```

**Commit boundary / suggested subject:** `feat: emit protected sec request identity`

- [ ] Add the three focused REDs.
- [ ] Run RED and record printable identity/internal retry failure.
- [ ] Implement the backwards-compatible HTTP boundary.
- [ ] Run focused GREEN and the full HTTP/retry regression.
- [ ] Commit only the protected identity and one-attempt boundary.

### Task 5: Require a Committed Attempt Permit Before Every Physical Send

**Purpose:** Correct RED-034's shallow GREEN by proving runtime attempt exhaustion blocks before DNS/send.

**Files:**
- CREATE: `src/stock_research_agent/providers/sec_edgar/retry.py`, `src/stock_research_agent/providers/sec_edgar/transport.py`, `tests/unit/test_sec_gate_b_transport.py`
- MODIFY: none outside those files
- READ/REUSE: `domain/live_evidence/schemas.py`, `db/repositories/live_evidence.py`, `domain/providers/sync.py`
- TEST: `tests/unit/test_sec_gate_b_transport.py`, existing RED-034 authorization test

**Interfaces:**
- Consumes: capability, bound resource, and injected `SecAttemptReservationPort`.
- Produces: matching `SecAttemptPermit` before one-shot sender invocation.

**Preconditions:** Tasks 1-4 are GREEN. Use an instrumented fake reservation port and fake sender; no SQLAlchemy session or network client is constructed.

**Exact failing tests:**
- Existing `test_red_034_gate_b_authorization_rejects_fifth_actual_attempt` remains GREEN as authorization-layer validation.
- New `test_red_034_runtime_attempt_budget_blocks_fifth_send_before_transport`
- New `test_attempt_permit_must_match_authorization_plan_slice_and_attempt`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_gate_b_production_authorization_red.py::test_red_034_gate_b_authorization_rejects_fifth_actual_attempt tests/unit/test_sec_gate_b_transport.py::test_red_034_runtime_attempt_budget_blocks_fifth_send_before_transport tests/unit/test_sec_gate_b_transport.py::test_attempt_permit_must_match_authorization_plan_slice_and_attempt -q
```

**Observed/current RED reason:** Only envelope metadata rejects a declared fifth attempt. No runtime API requires an authoritative permit, so no test proves that a fifth physical attempt is stopped before send.

**Minimal production change:** Add immutable reservation request/permit types and port protocol. Add the initial controller path that asks the port for attempt 1 and validates every returned identifier before resolving identity or invoking the sender. The fake port refuses after four plan-wide reservations and records events; the sender spy must remain at zero calls on refusal.

```python
permit = self._reservations.reserve(
    SecAttemptReservationRequest(
        authorization_id=execution.authorization_id,
        plan_id=execution.plan_id,
        plan_checksum=execution.plan_checksum,
        slice_id=resource.slice_id,
        endpoint_id=resource.request.endpoint_id,
        attempt_number=1,
        kind=SecAttemptKind.INITIAL,
    )
)
self._require_matching_permit(execution, resource, permit)
# Only this point may precede contact resolution and sender.send(...).
```

**Important invariants:** A permit is a capability, not a counter snapshot. Failure to reserve or a mismatched permit causes no resolver, DNS, or sender call. The production SQLAlchemy port is absent, so the default CLI remains blocked.

**Forbidden changes:** No in-memory production counter, repository call, transaction, consumption settlement, audit row, or interpretation of the fake as concurrency proof.

**Expected GREEN:** Both authorization-layer and controller-layer attempt checks are explicit; a refused fifth reservation makes sender count zero for that request.

**Regression command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_live_authorization_consumption.py tests/unit/test_gate_b_production_authorization_red.py::test_red_030_authorization_is_immutable_and_execution_approval_is_single_use tests/unit/test_gate_b_sec_transport_red.py::test_red_046_production_sec_run_requires_authorization_before_transport -q
```

**Commit boundary / suggested subject:** `feat: require sec pre-send attempt permits`

- [ ] Add the runtime RED-034 and permit-integrity tests.
- [ ] Run RED and confirm sender can currently be reached without a permit seam.
- [ ] Implement only the port contract and initial permit gate.
- [ ] Run GREEN and authorization regressions.
- [ ] Commit without a database adapter.

### Task 6: Compose the One-Shot SEC Transport Response Boundary

**Purpose:** Complete RED-032's real transport seam using injected fake transport while returning only bounded response data for Step 1B-3.

**Files:**
- CREATE: none beyond `providers/sec_edgar/transport.py`
- MODIFY: `src/stock_research_agent/providers/sec_edgar/transport.py`, `tests/unit/test_sec_gate_b_transport.py`
- READ/REUSE: `providers/http_client.py`, `providers/sec_edgar/policy.py`, `providers/sec_edgar/request_identity.py`
- TEST: `tests/unit/test_sec_gate_b_transport.py`, `tests/unit/test_gate_b_sec_transport_red.py`

**Interfaces:**
- Consumes: capability, authoritative plan, slice ID, matching contact reference, resolver, permit port, and one-shot HTTP client factory.
- Produces: secret-free `SecTransportResult` containing one or two bounded physical-attempt results; no persisted object.

**Preconditions:** Task 5 permit gate is GREEN. Tests inject `httpx.MockTransport`; the production default shell still has no live network composition.

**Exact failing tests:**
- `test_red_032_authorized_sec_controller_sends_only_canonical_plan_resource`
- `test_sec_transport_result_contains_bounded_response_without_artifact_fields`
- `test_transport_rejects_envelope_or_raw_url_in_place_of_capability_and_resource`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_sec_gate_b_transport.py::test_red_032_authorized_sec_controller_sends_only_canonical_plan_resource tests/unit/test_sec_gate_b_transport.py::test_sec_transport_result_contains_bounded_response_without_artifact_fields tests/unit/test_sec_gate_b_transport.py::test_transport_rejects_envelope_or_raw_url_in_place_of_capability_and_resource -q
```

**Observed/current RED reason:** There is no SEC transport controller, no sender that requires both capability and permit, and no bounded non-persistent response type.

**Minimal production change:** Implement the first-attempt path in `SecGateBTransportController.execute`. Bind the plan, reserve, resolve protected identity, construct `HttpRequest` solely from `CanonicalProviderRequest`, instantiate `SafeHttpClient` with the SEC policy and identity, and convert `HttpResult` or typed safe failure into `SecPhysicalAttempt`. Reject direct envelopes and raw URLs through the method signature and strict models.

**Important invariants:** Authorization and reservation precede contact resolution. Sender receives one canonical resource. Result contains request-attempt ID, safe URL, response bytes/status/content type, and safe failure code only; it has no artifact ID, audit row, DQ state, credential, header dump, or raw URL input.

**Forbidden changes:** No Raw Artifact, checksum/provenance persistence, response parser, audit, transaction, DQ, Citation, or fallback.

**Expected GREEN:** One authorized fake request produces one bounded result with `HttpResult.attempts == 1`; invalid capability/resource cannot reach resolver or sender.

**Regression command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_gate_b_sec_transport_red.py::test_red_032_production_sec_application_constructs_exact_offline_plan tests/unit/test_gate_b_sec_transport_red.py::test_red_033_redirect_response_aborts_after_one_fake_attempt tests/unit/test_gate_b_sec_transport_red.py::test_red_041_sec_public_api_has_no_operator_raw_url_entrypoint tests/unit/test_gate_b_sec_transport_red.py::test_red_042_default_sec_failure_has_no_live_or_fixture_success_fallback -q
```

**Commit boundary / suggested subject:** `feat: compose authorized sec transport`

- [ ] Add the authorized transport REDs.
- [ ] Run RED and confirm the missing controller/response seam.
- [ ] Implement the one-attempt fake-injectable path.
- [ ] Run GREEN and shell/fallback regressions.
- [ ] Commit without adding default live wiring.

### Task 7: Make the SEC Controller the Sole 429 and Transient Retry Authority

**Purpose:** Turn RED-035 GREEN at the correct owner and allow only approved transient outcomes to ask for a retry permit.

**Files:**
- CREATE: none beyond `providers/sec_edgar/retry.py`
- MODIFY: `src/stock_research_agent/providers/sec_edgar/retry.py`, `providers/sec_edgar/transport.py`, `tests/unit/test_gate_b_sec_transport_red.py`, `tests/unit/test_sec_gate_b_transport.py`
- READ/REUSE: `providers/retry.py`, `providers/errors.py`
- TEST: the two Gate B transport test files and generic retry tests

**Interfaces:**
- Consumes: `ProviderRetryOutcome`, previous permit, authorized resource/capability, and reservation port.
- Produces: terminal `RetryDecision` or one new matching retry permit.

**Preconditions:** Task 6 one-attempt transport is GREEN; SafeHttpClient has no internal SEC retry.

**Exact failing tests:**
- Retargeted `test_red_035_http_429_is_never_retried_for_gate_b`
- Companion `test_red_035_429_returns_abort_after_exactly_one_physical_send`
- Companion `test_sec_retry_controller_allows_only_approved_transient_outcomes`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_gate_b_sec_transport_red.py::test_red_035_http_429_is_never_retried_for_gate_b tests/unit/test_sec_gate_b_transport.py::test_red_035_429_returns_abort_after_exactly_one_physical_send tests/unit/test_sec_gate_b_transport.py::test_sec_retry_controller_allows_only_approved_transient_outcomes -q
```

**Observed/current RED reason:** RED-035 calls shared `ProviderRetryPolicy`, which intentionally returns retry for 429. No SEC-specific classifier exists.

**Minimal production change:** Implement `SecGateBRetryController.classify`. Treat 429 as terminal `SEC_HTTP_429_ABORT`. Treat 500/502/503/504 and safe connect/read timeout codes as eligible for the one plan-global reservation request. Treat 403, 404, policy, redirect, invalid content, future data, checksum, and contact failures as terminal. The transport controller loops only when it receives a valid retry permit.

```python
if outcome.http_status == 429:
    return RetryDecision(
        retry=False,
        reason_code="SEC_HTTP_429_ABORT",
        next_attempt=None,
        delay_seconds=None,
        resolve_credential_again=False,
    )
```

**Important invariants:** Generic policy is unchanged. SafeHttpClient performs one attempt. The SEC controller is the sole retry authority. 429 produces one send, no sleep, no reservation request, and terminal BLOCKED output.

**Forbidden changes:** Do not special-case 429 in generic retry, add transport retries, sleep on 429, or convert errors to success.

**Expected GREEN:** RED-035 targets the SEC controller and passes; the integration-style fake proves exactly one physical send; generic retry tests still prove their independent 429 behavior.

**Regression command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_provider_retry_policy.py tests/unit/test_provider_http_client.py::test_429_is_retried_with_exponential_delay tests/unit/test_gate_b_sec_transport_red.py::test_red_042_default_sec_failure_has_no_live_or_fixture_success_fallback -q
```

**Commit boundary / suggested subject:** `feat: isolate sec gate b retry policy`

- [ ] Retarget RED-035 without changing its one-send/no-retry intent.
- [ ] Run RED and observe the missing SEC owner.
- [ ] Implement the minimal classifier/controller loop.
- [ ] Run GREEN and generic retry regressions.
- [ ] Commit with generic retry untouched.

### Task 8: Enforce the Plan-Global Retry Token Before the Second Send

**Purpose:** Make RED-036 prove controller/port ordering and zero-send refusal while preserving the Step 1B-3 PostgreSQL concurrency dependency.

**Files:**
- CREATE: none
- MODIFY: `src/stock_research_agent/providers/sec_edgar/retry.py`, `providers/sec_edgar/transport.py`, `tests/unit/test_gate_b_sec_transport_red.py`, `tests/unit/test_sec_gate_b_transport.py`
- READ/REUSE: `db/repositories/live_evidence.py`, `domain/providers/sync.py`, `tests/integration/test_live_authorization_budget_postgres.py`
- TEST: Gate B transport unit tests; no PostgreSQL is used in this task

**Interfaces:**
- Consumes: the same `SecAttemptReservationPort`; retry request has `attempt_number=2` and `kind=RETRY` for the same plan resource.
- Produces: at most one retry permit across the fake plan-global state, or `SEC_RETRY_BUDGET_EXHAUSTED` with no second send.

**Preconditions:** Task 7 is GREEN. The fake port records `retry_eligibility_checked`, `retry_reserved`, `reservation_commit`, and sender events.

**Exact failing tests:**
- Retargeted `test_red_036_retry_budget_is_global_across_the_whole_sec_plan`
- Companion `test_red_036_rejected_second_retry_never_reaches_send_start`
- Companion `test_red_036_retry_permit_precedes_second_send`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_gate_b_sec_transport_red.py::test_red_036_retry_budget_is_global_across_the_whole_sec_plan tests/unit/test_sec_gate_b_transport.py::test_red_036_rejected_second_retry_never_reaches_send_start tests/unit/test_sec_gate_b_transport.py::test_red_036_retry_permit_precedes_second_send -q
```

**Observed/current RED reason:** Two calls to stateless shared retry classification both return retry. There is no authoritative plan-global reservation port and no pre-send permit requirement.

**Minimal production change:** Complete controller logic so every retry asks the port for a matching attempt-2 permit. The fake port consumes exactly one plan-global retry token and rejects the second endpoint's retry before sender invocation. Validate event order `retry_eligibility_checked -> retry_reserved -> reservation_commit -> send_start`.

**Important invariants:** The unit GREEN proves dependency and no-send ordering, not database atomicity. `RED-036_FINAL_POSTGRES_CONCURRENCY = RED` remains explicitly recorded until Step 1B-3 implements the port with row locking and proves two concurrent controllers cannot both commit.

**Forbidden changes:** No production in-memory global counter, SQLAlchemy session, repository mutation, transaction, or claim that fake serialization is a concurrency proof.

**Expected GREEN:** Ownership-correct unit RED-036 passes; the losing retry has zero send/DNS events. The final PostgreSQL concurrency contract remains a named Step 1B-3 entry condition.

**Regression command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_gate_b_sec_transport_red.py::test_red_035_http_429_is_never_retried_for_gate_b tests/unit/test_provider_retry_policy.py tests/unit/test_live_authorization_consumption.py -q
```

**Commit boundary / suggested subject:** `feat: gate sec retries on global reservation`

- [ ] Retarget RED-036 to the approved owner and add ordering/no-send companions.
- [ ] Run RED and record the missing reservation interaction.
- [ ] Implement only controller/port behavior.
- [ ] Run GREEN and retry/consumption regressions.
- [ ] Commit while explicitly leaving PostgreSQL port implementation absent.

### Task 9: Compose Authorization-to-Transport Without Enabling Live Execution

**Purpose:** Wire the production object graph so transport can be invoked only with `AuthorizedGateBExecution`, while the default CLI remains blocked because no production reservation transaction adapter or authorized execution parameters are supplied.

**Files:**
- CREATE: none
- MODIFY: `src/stock_research_agent/domain/live_evidence/gate_b_authorization.py`, `src/stock_research_agent/cli_live.py`, `src/stock_research_agent/providers/sec_edgar/transport.py`, `tests/unit/test_sec_gate_b_transport.py`
- READ/REUSE: Step 1B-1 gate and CLI protocols
- TEST: Gate B authorization and transport tests

**Interfaces:**
- Consumes: `AuthorizedGateBExecution`; no overload accepts envelope or operator mapping.
- Produces: an offline plan description through CLI or a transport result through explicitly injected controller dependencies.

**Preconditions:** Tasks 1-8 are GREEN. Production default construction has no resolver mapping, reservation adapter, or network-enabled client.

**Exact failing tests:**
- `test_transport_controller_signature_requires_authorized_gate_b_execution`
- `test_default_sec_shell_has_no_send_path_without_production_reservation_port`
- Existing `test_production_sec_shell_returns_no_executable_path_without_authorized_context`

**Exact test command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_sec_gate_b_transport.py::test_transport_controller_signature_requires_authorized_gate_b_execution tests/unit/test_sec_gate_b_transport.py::test_default_sec_shell_has_no_send_path_without_production_reservation_port tests/unit/test_gate_b_sec_transport_red.py::test_production_sec_shell_returns_no_executable_path_without_authorized_context -q
```

**Observed/current RED reason:** Step 1B-1 exposes only a transport-free shell; the new controller is not yet attached to the shell's explicit authorized seam.

**Minimal production change:** Add an `execute_authorized(execution: AuthorizedGateBExecution, ...)` port/method that delegates only to an injected `SecGateBTransportController`. Keep `operate("run", plan_id, checksum)` blocked because those two operator values cannot create a capability or permit. The production CLI factory supplies only the plan descriptor and authorization gate; it supplies no network-enabled transport, resolver environment, or reservation adapter.

**Important invariants:** Authorization is structurally upstream. Default CLI cannot send. A caller cannot substitute an envelope. Step 1B-3 must inject the production reservation/settlement composition after separate authorization.

**Forbidden changes:** No default fake permit, environment resolver, network-enabled policy, auto-created capability, operational grant, or Live success payload.

**Expected GREEN:** Type/signature tests prove the controller requires the capability; default CLI continues to return BLOCKED for run and no execution capability.

**Regression command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_gate_b_production_authorization_red.py tests/unit/test_sec_live_pilot_cli.py tests/unit/test_gate_b_sec_transport_red.py::test_red_046_production_sec_run_requires_authorization_before_transport tests/unit/test_gate_b_sec_transport_red.py::test_red_048_gate_b_modules_have_no_model_runtime_dependency -q
```

**Commit boundary / suggested subject:** `feat: compose authorized sec transport boundary`

- [ ] Add the structural composition REDs.
- [ ] Run RED and record the absent explicit seam.
- [ ] Add only the capability-typed delegation and offline factory.
- [ ] Run GREEN and authorization/CLI regressions.
- [ ] Commit without operational Live wiring.

### Task 10: Target, Preserved-Contract, and Stage 10 Offline Regression

**Purpose:** Verify Step 1B-2 contracts at their correct layer, preserve Step 1B-1 and prior GREEN contracts, and keep Step 1B-3 contracts unresolved.

**Files:** No new production or test files are expected.

**Interfaces:** No new interfaces; verify the exact surface built in Tasks 1-9.

**Preconditions:** All task-level GREEN commands pass, no production file outside the approved boundary changed, and no PostgreSQL/live configuration is active.

**Level 1 target command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_gate_b_sec_transport_red.py::test_red_032_production_sec_application_constructs_exact_offline_plan tests/unit/test_gate_b_production_authorization_red.py::test_red_034_gate_b_authorization_rejects_fifth_actual_attempt tests/unit/test_sec_gate_b_transport.py::test_red_034_runtime_attempt_budget_blocks_fifth_send_before_transport tests/unit/test_gate_b_sec_transport_red.py::test_red_035_http_429_is_never_retried_for_gate_b tests/unit/test_gate_b_sec_transport_red.py::test_red_036_retry_budget_is_global_across_the_whole_sec_plan tests/unit/test_sec_gate_b_transport.py::test_red_036_rejected_second_retry_never_reaches_send_start tests/unit/test_gate_b_sec_transport_red.py::test_red_037_production_sec_timeout_configuration_matches_runbook tests/unit/test_gate_b_sec_transport_red.py::test_red_038_declared_contact_identity_contract_is_defined_without_secret_output tests/unit/test_gate_b_sec_transport_red.py::test_red_039_production_sec_allowlist_policy_exists_before_send -q
```

**Expected result:** Every Step 1B-2 unit contract is GREEN. RED-034 is reported as authorization-layer GREEN plus controller/pre-send-port GREEN. RED-036 is reported as controller/port GREEN with final PostgreSQL concurrency proof still RED by design.

**Level 2 preserved-contract command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_gate_b_production_authorization_red.py::test_red_028_production_authorization_creation_composition_exists tests/unit/test_gate_b_production_authorization_red.py::test_red_029_production_authorization_rejects_fail_closed_matrix tests/unit/test_gate_b_production_authorization_red.py::test_red_030_authorization_is_immutable_and_execution_approval_is_single_use tests/unit/test_gate_b_production_authorization_red.py::test_red_031_authorization_binds_contact_reference_without_secret_value tests/unit/test_gate_b_sec_transport_red.py::test_red_033_redirect_response_aborts_after_one_fake_attempt tests/unit/test_gate_b_production_authorization_red.py::test_red_040_authorization_binds_exact_sec_paths_not_only_hosts tests/unit/test_gate_b_sec_transport_red.py::test_red_041_sec_public_api_has_no_operator_raw_url_entrypoint tests/unit/test_gate_b_sec_transport_red.py::test_red_042_default_sec_failure_has_no_live_or_fixture_success_fallback tests/unit/test_gate_b_sec_transport_red.py::test_red_046_production_sec_run_requires_authorization_before_transport tests/unit/test_gate_b_production_authorization_red.py::test_red_047_authorization_binds_filing_path_and_plan_checksum tests/unit/test_gate_b_sec_transport_red.py::test_red_048_gate_b_modules_have_no_model_runtime_dependency -q
```

**Step 1B-3 boundary command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_gate_b_sec_transport_red.py::test_red_043_production_sec_pipeline_validates_before_artifact_persistence tests/unit/test_gate_b_production_authorization_red.py::test_red_044_audit_models_cover_gate_b_authorization_and_artifact_lineage tests/unit/test_gate_b_sec_transport_red.py::test_red_049_production_gate_b_stops_at_data_quality -q
```

**Expected Step 1B-3 result:** RED-043, RED-044, and RED-049 remain RED for missing artifact/audit/DQ composition. RED-045 remains `TRANSACTION_BOUNDARY_TESTABILITY_GAP`; no unit-only change may mark its database ordering contract GREEN.

**Level 3 relevant Stage 10 command:**

```powershell
$env:PYTEST_ADDOPTS=''; uv run pytest -W error tests/unit/test_provider_http_client.py tests/unit/test_provider_retry_policy.py tests/unit/test_provider_credential_resolver.py tests/unit/test_sec_edgar_endpoints.py tests/unit/test_sec_edgar_planner.py tests/unit/test_gate_b_production_authorization_red.py tests/unit/test_sec_live_pilot_cli.py tests/unit/test_stage10_offline_isolation.py tests/unit/test_stage10_live_test_isolation.py tests/unit/test_stage10_security_matrix.py -q
```

**Static commands:**

```powershell
uv run ruff check src/stock_research_agent/providers/credentials.py src/stock_research_agent/providers/http_client.py src/stock_research_agent/providers/sec_edgar src/stock_research_agent/domain/live_evidence/gate_b_authorization.py src/stock_research_agent/cli_live.py tests/unit/test_gate_b_sec_transport_red.py tests/unit/test_sec_gate_b_transport.py tests/unit/test_provider_http_client.py tests/unit/test_provider_credential_resolver.py
uv run ruff format --check src/stock_research_agent/providers/credentials.py src/stock_research_agent/providers/http_client.py src/stock_research_agent/providers/sec_edgar src/stock_research_agent/domain/live_evidence/gate_b_authorization.py src/stock_research_agent/cli_live.py tests/unit/test_gate_b_sec_transport_red.py tests/unit/test_sec_gate_b_transport.py tests/unit/test_provider_http_client.py tests/unit/test_provider_credential_resolver.py
uv run mypy src
git diff --check
```

**Important invariants:** Tests use fake transport/resolver/permit ports only. No Live marker, DNS, socket, credential environment, fixture-as-success, or PostgreSQL is invoked.

**Forbidden changes:** Do not repair Step 1B-3 REDs, hide expected REDs with xfail/skip, or claim final RED-036 concurrency completion.

**Expected GREEN:** All target and preserved unit contracts pass at their stated layer, Level 3 passes, static checks pass, and Step 1B-3 remains the only production-persistence boundary.

**Commit boundary / suggested subject:** `fix: complete sec transport policy regressions` only for a bounded defect in approved files; otherwise no new commit.

- [ ] Run Level 1 and record counts/status by contract.
- [ ] Run Level 2 and confirm every preserved contract remains GREEN.
- [ ] Run the Step 1B-3 boundary command and confirm failures remain at approved seams.
- [ ] Run Level 3 and all static commands.
- [ ] Inspect the diff for secrets, schema changes, generic-policy changes, and cross-slice leakage.

### Task 11: Slice Exit Audit

**Purpose:** Prevent a fake or cross-slice completion claim and hand back a reviewable offline Step 1B-2 implementation.

**Files:** No changes expected.

**Preconditions:** Tasks 1-10 are complete.

**Audit commands:**

```powershell
git status --short
git diff --check
git diff --name-only c704341bbf57718b887bfb221b36532819469344..HEAD
git log --oneline c704341bbf57718b887bfb221b36532819469344..HEAD
```

**Exit criteria:**

- RED-032, ownership-correct RED-035/037/038/039, RED-034 runtime companion, and RED-036 controller/port companion are GREEN.
- RED-028/029/030/031/033/040/041/042/046/047/048 remain GREEN.
- Generic retry behavior, generic timeout defaults, and generic HTTP retry tests are unchanged.
- SafeHttpClient performs exactly one SEC physical attempt; the SEC controller is the only retry authority.
- 429 is terminal/no-retry. The plan-global retry port is consulted atomically by contract before retry send.
- The forbidden fifth attempt and losing second retry have no resolver/DNS/send activity.
- Final PostgreSQL concurrency proof for RED-036 is still explicitly assigned to Step 1B-3.
- Contact values were not read from real environment, serialized, logged, returned, hashed, or placed in policy.
- No Raw Artifact, audit, settlement transaction, DQ, Citation, Claim, Report, Gate B execution, or Stage 11 behavior exists.
- No schema or migration changed. Gate B remains `NO_GO`, unauthorized, and unexecuted.

**Stop condition:** Return the implementation for human review. Do not start Step 1B-3.

- [ ] Confirm every exit criterion with fresh command output and stop.

## RED-to-Seam Map

| Contract | Production seam | Minimal planned behavior | Final slice qualification |
|---|---|---|---|
| RED-032 | SEC policy descriptor + authorized plan binder + controller | exact offline plan and capability-bound canonical request | Step 1B-2 GREEN |
| RED-034 | pre-send `SecAttemptReservationPort` and permit gate | reject fifth runtime attempt before resolver/DNS/send | controller GREEN; DB adapter proof in 1B-3 |
| RED-035 | `SecGateBRetryController` | 429 terminal, one physical send, no retry | Step 1B-2 GREEN |
| RED-036 | SEC controller + atomic reservation port | one plan-global retry token; rejected second retry cannot send | unit port/order GREEN; final PostgreSQL concurrency RED until 1B-3 |
| RED-037 | `build_sec_http_client_policy` | SEC `10/30/120`, redirects 0, attempts 1; generic unchanged | Step 1B-2 GREEN |
| RED-038 | protected request identity + injected resolver + HTTP emission | ephemeral validated/redacted identity, final-boundary unwrap only | Step 1B-2 GREEN |
| RED-039 | plan binder + SEC policy + SafeHttpClient | exact scheme/method/host/port/path membership before send | Step 1B-2 GREEN |

## Explicit Scope Exclusions

Step 1B-2 does not implement RED-043 response-to-Raw-Artifact persistence, RED-044 audit composition, RED-045 Reservation / Settlement transaction orchestration, the PostgreSQL implementation of `SecAttemptReservationPort`, or RED-049 committed Data Quality STOP. It does not create DocumentVersion, Citation, Evidence, Claim, Package, Report, publication, a real grant, a frozen filing/accession, Gate B authorization, Gate B execution, or Stage 11 state.

## Blocker Decision

- `IMPLEMENTATION_BLOCKER = NO`: existing endpoint, authorization, credential resolver, HTTP, sync-plan, and consumption contracts are sufficient to define the offline controller, protected identity, exact plan binder, and reservation port.
- `SCHEMA_CHANGE_BLOCKER = NO`: existing authorization consumption and request-attempt lineage can support the production adapter and atomic proof in Step 1B-3. Step 1B-2 creates no persisted state.
- `RED_036_FINAL_POSTGRES_CONCURRENCY = STEP_1B_3_ENTRY_CONDITION`: this is an explicit approved slice dependency, not an unresolved architecture question and not a reason to weaken the Step 1B-2 no-send port contract.
