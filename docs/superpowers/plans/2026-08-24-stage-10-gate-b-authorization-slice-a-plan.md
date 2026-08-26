# Gate B Authorization V2 Slice A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make production Gate B Authorization V2 bind cryptographically and authoritatively to the exact frozen `ProviderSyncRequest` and `ProviderSyncPlan`, rejecting every request, plan, governance, security, cutoff, or execution-mode substitution.

**Architecture:** Introduce explicit V2-only envelope, grant, validation, and canonical checksum contracts while leaving V1 parsing and checksum bytes unchanged. `ProductionAuthorizationGate` is the single validation owner and consumes a typed authority snapshot loaded from PostgreSQL by exact request and plan IDs; the gate reconstructs and verifies the frozen request checksum, verifies `plan.sync_request_id == request.id`, and then checks every transitive governance field before returning a non-executable V2 validation result.

**Tech Stack:** Python 3.12.13, frozen Pydantic 2 models, SQLAlchemy 2, PostgreSQL 17, pytest with `-W error`, Ruff, and strict mypy.

## Global Constraints

- Slice A solves IMPORTANT-01 only; no Grant/Approval persistence, registry manifest implementation, materialization transaction, SyncRun creation, initial Attempt, permit, or network behavior belongs here.
- `MIGRATION_REQUIRED_FOR_SLICE_A: NO`; do not create or edit an Alembic revision.
- Authorization V2 contract version is exactly `2.0.0`; canonical namespace is exactly `live-authorization-grant-v2`.
- V1 remains readable and byte/checksum compatible, but is rejected by the production Gate B authorization path; no implicit V1-to-V2 upgrade is permitted.
- Direct roots are `sync_request_id`, `request_checksum`, `plan_id`, and `plan_checksum`; each is also independently verified through authoritative readback.
- The accepted Operational Freeze records and checksums are immutable. Tests use disposable records and never update the operational `stock_research` database.
- No raw credential, SEC contact, password, environment value, User-Agent contact string, SyncRun ID, Attempt ID, network result, or wall-clock execution result may enter V2 canonical material.
- `research_as_of_time` remains `2026-08-22T18:47:59.661193Z` for the accepted freeze and is never replaced by authorization or execution time.
- Generic Provider request/policy attempts remain `3`; Gate B physical capacity remains `4`; plan-wide retry count remains `1`.
- No SEC DNS, socket, HTTP, credential resolution, operational authorization, Gate B execution, or Stage 11 work is permitted.

---

## File Map

| File | Slice A responsibility |
|---|---|
| `tests/unit/test_gate_b_authorization_request_binding_red.py` | RED-A-001 through RED-A-017: V2 public contract, fail-closed binding, checksum significance, V1 compatibility, and secret exclusion. |
| `tests/integration/test_gate_b_authorization_request_binding_postgres_red.py` | PostgreSQL proof that exact request/plan rows are authoritative, mismatched joins fail, and validation mutates no freeze rows. |
| `src/stock_research_agent/domain/live_evidence/schemas.py` | Add explicit `GateBLiveAuthorizationGrantWriteV2` and `GateBLiveAuthorizationGrantRecordV2`; do not alter V1 field or validator semantics. |
| `src/stock_research_agent/domain/live_evidence/canonical.py` | Dispatch V1/V2 canonicalization by concrete versioned contract and preserve the V1 vector. |
| `src/stock_research_agent/domain/live_evidence/gate_b_authorization.py` | Add V2 envelope/authority/validation types and make `ProductionAuthorizationGate` the single fail-closed binding owner. |
| `src/stock_research_agent/domain/providers/repositories.py` | Add typed exact `get_request()` and `get_plan()` protocol methods. |
| `src/stock_research_agent/db/repositories/providers.py` | Implement exact request/plan reads with optional `FOR UPDATE`; no commit and no mutation. |
| `src/stock_research_agent/db/repositories/live_evidence.py` | Add the production PostgreSQL authority reader that composes existing typed repositories in one caller-owned Session. |

## Frozen Authority Used by Acceptance Tests

```text
sync_request_id = c38ff658-c585-4538-aea4-7f3d62e49874
request_checksum = 35105364b41ee906ab00385f2c346ef6f8a8bb0e868a2a247dfa8305f4b80d50
plan_id = 1f9af496-c858-435b-a5e5-31132714a85e
plan_checksum = 4faf214a562dd9dce4be2d9aec4d9f318277163840d0fa03119fc55f0c206ebd
provider_definition_id = c862ab2e-64ee-4c70-a19e-2a76865cd154
provider_capability_id = 9bb91282-5800-436b-9174-788cdf0dd71b
provider_policy_id = 1319f9a2-3782-4068-ac00-480f703b206d
credential_reference_id = 7c811ba4-a0e1-4955-9063-392d8c361eef
source_license_policy_id = 39af6550-8031-4818-8cf1-648563a89258
security_id = 40000000-0000-0000-0000-000000000002
research_as_of_time = 2026-08-22T18:47:59.661193Z
execution_mode = LIVE_VALIDATION
```

These exact IDs may appear in documentation and non-operational acceptance vectors. PostgreSQL tests must create disposable rows with independently allocated IDs so they cannot mutate or accidentally depend on the operational freeze.

### Task 1: Establish the Slice A RED contract

**Files:**
- Create: `tests/unit/test_gate_b_authorization_request_binding_red.py`
- Create: `tests/integration/test_gate_b_authorization_request_binding_postgres_red.py`

**Interfaces:**
- Consumes: current V1 `ProductionAuthorizationGate`, `LiveAuthorizationGrantWrite/Record`, `canonical_grant()`, `grant_checksum()`, `SqlAlchemyProviderSyncRepository`, and migrated test PostgreSQL schema.
- Produces: executable contract for `GateBAuthorizationEnvelopeV2`, `GateBLiveAuthorizationGrantWriteV2/RecordV2`, `GateBAuthorizationFreezeAuthority`, `GateBAuthorizationValidationV2`, `GateBAuthorizationAuthorityReader`, and the V2 gate path.

- [ ] **Step 1: Add unit REDs A-001 through A-011**

Use a single helper that resolves the intended public V2 symbols with assertion failures rather than import or collection errors:

```python
def _v2_api() -> tuple[type[object], type[object], type[object]]:
    envelope_type = getattr(gate_b_authorization, "GateBAuthorizationEnvelopeV2", None)
    grant_type = getattr(live_schemas, "GateBLiveAuthorizationGrantRecordV2", None)
    authority_type = getattr(gate_b_authorization, "GateBAuthorizationFreezeAuthority", None)
    assert envelope_type is not None, "Gate B Authorization V2 envelope is not implemented"
    assert grant_type is not None, "Gate B Authorization V2 grant is not implemented"
    assert authority_type is not None, "Gate B V2 freeze authority is not implemented"
    return envelope_type, grant_type, authority_type
```

Construct one internally complete V2 candidate and vary exactly one field per test. A-001 through A-009 require a stable `LiveEvidenceValidationError`; A-010 requires a `GateBAuthorizationValidationV2`; A-011 constructs a valid V1 object, proves it remains readable, and requires the production gate to reject it with `GATE_B_AUTHORIZATION_VERSION_UNSUPPORTED`.

- [ ] **Step 2: Add unit REDs A-012 through A-017**

The checksum matrix must change one authority field at a time:

```python
baseline = _v2_grant()
assert grant_checksum_v2(baseline.model_copy(update={"sync_request_id": uuid4()})) != grant_checksum_v2(baseline)
assert grant_checksum_v2(
    baseline.model_copy(update={"request_checksum": "9" * 64})
) != grant_checksum_v2(baseline)
```

Repeat for `plan_id`, `plan_checksum`, `credential_reference_id`, `source_license_policy_id`, `security_id`, `research_as_of_time`, and `execution_mode`. Assert canonical material contains `"schema":"live-authorization-grant-v2"` and contains none of the sentinel raw contact, secret, environment value, or protected User-Agent material.

- [ ] **Step 3: Lock the V1 checksum vector**

Use an existing valid V1 fixture and a literal expected canonical string/checksum captured before any production change:

```python
assert canonical_grant(v1_grant) == EXPECTED_V1_CANONICAL
assert grant_checksum(v1_grant) == EXPECTED_V1_CHECKSUM
```

This is `PRE_EXISTING_GREEN`; it prevents V2 work from changing V1 bytes.

- [ ] **Step 4: Add PostgreSQL REDs for authoritative readback**

Migrate only the disposable `stock_research_test` database, create two valid frozen requests plus plans, then prove the production authority path ignores caller model copies and reads exact rows. The adversarial request/plan test must persist plan B, pair it with request A in the candidate, and require `GATE_B_PLAN_REQUEST_MISMATCH`.

```python
with pytest.raises(LiveEvidenceValidationError, match="GATE_B_PLAN_REQUEST_MISMATCH"):
    gate.authorize(
        envelope_for(request_a, plan_b),
        grant=grant_for(request_a, plan_b),
        events=ACTIVE_EVENTS,
        approval=approval_for(plan_b),
        scope=scope_for(request_a),
        contact_reference=credential_a,
        checked_at=NOW,
    )
```

Capture counts and checksums for `provider_credential_references`, `source_license_policies`, `provider_sync_requests`, and `provider_sync_plans` before and after validation; assert identical values and zero row delta.

- [ ] **Step 5: Run the RED suite and classify every result**

Run:

```powershell
uv run pytest -W error tests/unit/test_gate_b_authorization_request_binding_red.py -q
uv run pytest -W error tests/integration/test_gate_b_authorization_request_binding_postgres_red.py -q
```

Expected: A-001 through A-015 and A-017/A-018 fail through explicit assertion or expected-behavior mismatch at the missing V2/authority boundary; A-016 may pass as pre-existing V1 compatibility. No collection, syntax, fixture, unrelated database, environment, or network failure counts as valid RED.

- [ ] **Step 6: Commit the tests-only RED baseline**

```powershell
git add tests/unit/test_gate_b_authorization_request_binding_red.py tests/integration/test_gate_b_authorization_request_binding_postgres_red.py
git diff --cached --name-only
git commit -m "test: define gate b authorization v2 binding red contract"
```

Expected staged paths: exactly the two new test files.

### Task 2: Add explicit V2 grant and canonical checksum contracts

**Files:**
- Modify: `src/stock_research_agent/domain/live_evidence/schemas.py`
- Modify: `src/stock_research_agent/domain/live_evidence/canonical.py`
- Test: `tests/unit/test_gate_b_authorization_request_binding_red.py`

**Interfaces:**
- Consumes: V1 `LiveAuthorizationGrantWrite/Record`, `FrozenProviderContract`, `AwareUtcDateTime`, `Checksum`, and `ProviderExecutionMode`.
- Produces: `GateBLiveAuthorizationGrantWriteV2`, `GateBLiveAuthorizationGrantRecordV2`, V2-aware `GrantContract`, `canonical_grant()`, `grant_checksum()`, and `verify_grant_checksum()`.

- [ ] **Step 1: Run only A-012 through A-017 and observe intended RED**

```powershell
uv run pytest -W error tests/unit/test_gate_b_authorization_request_binding_red.py -k "a_012 or a_013 or a_014 or a_015 or a_016 or a_017" -q
```

Expected: V2 cases fail because the explicit V2 schema/canonical path is absent; A-016 passes.

- [ ] **Step 2: Add the minimum V2 grant types**

Keep V1 untouched and define explicit V2 fields:

```python
class GateBLiveAuthorizationGrantWriteV2(LiveAuthorizationGrantWrite):
    contract_version: Literal["2.0.0"]
    sync_request_id: UUID
    request_checksum: Checksum
    plan_id: UUID
    plan_checksum: Checksum
    research_as_of_time: AwareUtcDateTime
    execution_mode: Literal[ProviderExecutionMode.LIVE_VALIDATION]


class GateBLiveAuthorizationGrantRecordV2(GateBLiveAuthorizationGrantWriteV2):
    id: UUID
    created_at: AwareUtcDateTime
```

The inherited fields retain direct provider, capability, policy, credential, license, security, budget, retention, and approval metadata. Do not add secrets or runtime execution identifiers.

- [ ] **Step 3: Dispatch canonicalization by concrete V1/V2 type**

```python
def _grant_schema(value: GrantContract) -> str:
    if isinstance(value, (GateBLiveAuthorizationGrantWriteV2, GateBLiveAuthorizationGrantRecordV2)):
        return "live-authorization-grant-v2"
    return "live-authorization-grant-v1"
```

Use the selected schema marker in `canonical_grant()` without changing V1 exclusions, JSON sorting, separators, UTC formatting, or field conversion. Never infer V2 from optional field presence.

- [ ] **Step 4: Run canonical tests GREEN and full V1 canonical regression**

```powershell
uv run pytest -W error tests/unit/test_gate_b_authorization_request_binding_red.py -k "a_012 or a_013 or a_014 or a_015 or a_016 or a_017" -q
uv run pytest -W error tests/unit/test_live_evidence_canonical.py tests/unit/test_gate_b_production_authorization_red.py -q
```

Expected: V2 checksum significance and secret exclusion pass; V1 literal vector remains unchanged; existing canonical/authorization tests pass.

- [ ] **Step 5: Commit the versioned canonical contract**

```powershell
git add src/stock_research_agent/domain/live_evidence/schemas.py src/stock_research_agent/domain/live_evidence/canonical.py tests/unit/test_gate_b_authorization_request_binding_red.py
git commit -m "feat: add gate b authorization v2 canonical contract"
```

### Task 3: Add exact request and plan repository readback

**Files:**
- Modify: `src/stock_research_agent/domain/providers/repositories.py`
- Modify: `src/stock_research_agent/db/repositories/providers.py`
- Test: `tests/integration/test_gate_b_authorization_request_binding_postgres_red.py`

**Interfaces:**
- Consumes: `ProviderSyncRequestRecord`, `ProviderSyncPlanRecord`, SQLAlchemy `Session`, and existing ORM models.
- Produces: `ProviderSyncRepository.get_request(request_id, for_update=False)` and `get_plan(plan_id, for_update=False)`.

- [ ] **Step 1: Run repository readback tests and observe RED**

```powershell
uv run pytest -W error tests/integration/test_gate_b_authorization_request_binding_postgres_red.py -k "repository" -q
```

Expected: clean failure stating the exact read methods are absent.

- [ ] **Step 2: Add protocol methods**

```python
def get_request(
    self,
    request_id: UUID,
    *,
    for_update: bool = False,
) -> ProviderSyncRequestRecord | None: ...

def get_plan(
    self,
    plan_id: UUID,
    *,
    for_update: bool = False,
) -> ProviderSyncPlanRecord | None: ...
```

- [ ] **Step 3: Implement exact transaction-neutral queries**

```python
def get_request(self, request_id: UUID, *, for_update: bool = False) -> ProviderSyncRequestRecord | None:
    query = select(ProviderSyncRequest).where(ProviderSyncRequest.id == request_id)
    if for_update:
        query = query.with_for_update()
    row = self._session.scalar(query)
    return None if row is None else _sync_request_record(row)
```

Implement `get_plan()` identically over `ProviderSyncPlan.id`. Neither method commits, updates, reconstructs a caller copy, or accepts a natural identity in place of the exact UUID.

- [ ] **Step 4: Run repository and existing Provider PostgreSQL tests GREEN**

```powershell
uv run pytest -W error tests/integration/test_gate_b_authorization_request_binding_postgres_red.py -k "repository" -q
uv run pytest -W error tests/integration/test_gate_b_request_identity_postgres_red.py tests/integration/test_provider_sync_postgres.py -q
```

- [ ] **Step 5: Commit exact readback**

```powershell
git add src/stock_research_agent/domain/providers/repositories.py src/stock_research_agent/db/repositories/providers.py tests/integration/test_gate_b_authorization_request_binding_postgres_red.py
git commit -m "feat: add exact gate b freeze readback"
```

### Task 4: Make ProductionAuthorizationGate the authoritative V2 binding owner

**Files:**
- Modify: `src/stock_research_agent/domain/live_evidence/gate_b_authorization.py`
- Modify: `src/stock_research_agent/db/repositories/live_evidence.py`
- Test: `tests/unit/test_gate_b_authorization_request_binding_red.py`
- Test: `tests/integration/test_gate_b_authorization_request_binding_postgres_red.py`
- Modify: `tests/unit/test_gate_b_production_authorization_red.py`

**Interfaces:**
- Consumes: exact V2 envelope/grant, authoritative typed request/plan/governance records, existing grant lifecycle and approval validation, and contact metadata validation.
- Produces: `GateBAuthorizationEnvelopeV2`, `GateBAuthorizationFreezeAuthority`, `GateBAuthorizationAuthorityReader`, `GateBAuthorizationValidationV2`, and V2-only `ProductionAuthorizationGate.authorize()`.

- [ ] **Step 1: Run A-001 through A-011 and PostgreSQL mismatch tests RED**

```powershell
uv run pytest -W error tests/unit/test_gate_b_authorization_request_binding_red.py -k "a_001 or a_002 or a_003 or a_004 or a_005 or a_006 or a_007 or a_008 or a_009 or a_010 or a_011" -q
uv run pytest -W error tests/integration/test_gate_b_authorization_request_binding_postgres_red.py -k "binding or mismatch" -q
```

- [ ] **Step 2: Define the explicit V2 envelope and authority snapshot**

```python
class GateBAuthorizationEnvelopeV2(GateBAuthorizationCreateRequest):
    contract_version: Literal["2.0.0"]
    sync_request_id: UUID
    request_checksum: Checksum


class GateBAuthorizationFreezeAuthority(FrozenProviderContract):
    request: ProviderSyncRequestRecord
    plan: ProviderSyncPlanRecord
    definition: ProviderDefinitionRecord
    capability: ProviderCapabilityRecord
    policy: ProviderPolicyRecord
    credential_reference: CredentialReferenceRecord
    license_policy: SourceLicensePolicyRecord
```

`GateBAuthorizationValidationV2` carries the four frozen roots plus provider definition, capability, policy, credential, license, security, `research_as_of_time`, and `execution_mode`. It remains non-executable and contains no Session, URL, permit, or secret.

- [ ] **Step 3: Add the authority reader protocol and PostgreSQL adapter**

```python
class GateBAuthorizationAuthorityReader(Protocol):
    def load(
        self,
        sync_request_id: UUID,
        plan_id: UUID,
    ) -> GateBAuthorizationFreezeAuthority: ...
```

The production adapter loads exact records through existing typed repositories in one caller-owned Session. Missing rows map to stable secret-free `GATE_B_*_NOT_FOUND` errors. It never accepts caller-supplied request or plan objects as authority and performs no mutation.

- [ ] **Step 4: Enforce the direct and transitive binding matrix**

Within `ProductionAuthorizationGate.authorize()`:

```python
authority = self._authority_reader.load(envelope.sync_request_id, envelope.plan_id)
request = authority.request
plan = authority.plan

if envelope.contract_version != "2.0.0":
    raise LiveEvidenceValidationError("GATE_B_AUTHORIZATION_VERSION_UNSUPPORTED")
if envelope.request_checksum != request.request_checksum:
    raise LiveEvidenceValidationError("GATE_B_REQUEST_CHECKSUM_MISMATCH")
if envelope.plan_checksum != plan.plan_checksum:
    raise LiveEvidenceValidationError("EXEC_APPROVAL_PLAN_MISMATCH")
if plan.sync_request_id != request.id:
    raise LiveEvidenceValidationError("GATE_B_PLAN_REQUEST_MISMATCH")
```

Freshly reconstruct the accepted `GateBSyncRequestIdentity` from the persisted request and call `build_gate_b_sync_request()` to verify both `request_checksum` and `idempotency_key`. Then compare request provider definition, capability, policy, credential, license, security, cutoff, and `LIVE_VALIDATION` mode against V2 grant/envelope scope and authoritative governance records. Do not trust `model_validate(existing_model)` or `model_copy(update=...)` as validation.

- [ ] **Step 5: Reject V1 before returning production Gate B validation**

Keep V1 models and canonical functions readable. If `authorize()` receives V1 envelope or grant authority, raise `GATE_B_AUTHORIZATION_VERSION_UNSUPPORTED`; do not upgrade it, fill missing request fields, or return a Gate B validation result. Update the old focused test that expected V1 gate acceptance so it now asserts readability plus fail-closed execution rejection.

- [ ] **Step 6: Run Slice A unit and PostgreSQL tests GREEN**

```powershell
uv run pytest -W error tests/unit/test_gate_b_authorization_request_binding_red.py -q
uv run pytest -W error tests/integration/test_gate_b_authorization_request_binding_postgres_red.py -q
```

Expected: all A-001 through A-018 contracts pass, including real persisted request/plan mismatch and zero mutation proof.

- [ ] **Step 7: Commit the V2 gate binding**

```powershell
git add src/stock_research_agent/domain/live_evidence/gate_b_authorization.py src/stock_research_agent/db/repositories/live_evidence.py tests/unit/test_gate_b_authorization_request_binding_red.py tests/integration/test_gate_b_authorization_request_binding_postgres_red.py tests/unit/test_gate_b_production_authorization_red.py
git commit -m "feat: bind gate b authorization v2 to frozen request"
```

### Task 5: Run Slice A regression and independent review gate

**Files:**
- Verify only; no new production surface.

**Interfaces:**
- Consumes: completed Slice A commits.
- Produces: evidence package for independent review; it does not authorize Slice B.

- [ ] **Step 1: Run focused authorization and request-identity regression**

```powershell
uv run pytest -W error tests/unit/test_gate_b_authorization_request_binding_red.py tests/unit/test_gate_b_production_authorization_red.py tests/unit/test_gate_b_corrective_authorization_red.py tests/unit/test_gate_b_request_identity_red.py tests/unit/test_gate_b_request_identity_boundary_red.py -q
```

- [ ] **Step 2: Run focused PostgreSQL regression**

```powershell
uv run pytest -W error tests/integration/test_gate_b_authorization_request_binding_postgres_red.py tests/integration/test_gate_b_request_identity_postgres_red.py tests/integration/test_gate_b_corrective_postgres_red.py tests/integration/test_gate_b_attempt_limit_migration_postgres_red.py -q
```

- [ ] **Step 3: Run full non-live regression and quality gates**

```powershell
uv run pytest -W error -m "not live" -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
git diff --check
```

Report every skip and warning exactly. Do not describe missing `TEST_DATABASE_ADMIN_URL` migration tests as passing.

- [ ] **Step 4: Prove the Slice A boundary**

```powershell
git diff --name-only main...HEAD
git log --oneline --decorate main..HEAD
git status --short
```

Required: no migration, Grant/Approval persistence, registry manifest implementation, materialization, SyncRun/Attempt creation, network, credential resolution, operational DB mutation, or Slice B/C production work.

- [ ] **Step 5: Stop for independent human review**

Record:

```text
IMPORTANT_01_RESOLVED: YES
SLICE_A_IMPLEMENTATION_COMPLETE: YES
SLICE_A_INDEPENDENT_REVIEW_REQUIRED: YES
SLICE_B_STARTED: NO
GATE_B_AUTHORIZED: NO
GATE_B_EXECUTED: NO
STAGE_11: NOT_STARTED
```

Do not create the Slice B branch or migration until the independent review explicitly approves Slice A.

## Self-Review Checklist

- [ ] Every RED-A-001 through RED-A-018 requirement maps to an exact test.
- [ ] Request ID/checksum and plan ID/checksum are both directly bound and independently re-read.
- [ ] PostgreSQL proves `plan.sync_request_id == request.id` using persisted rows, not a mock.
- [ ] Provider, capability, policy, credential, license, security, cutoff, and mode are checked from the frozen request authority.
- [ ] V1 canonical bytes remain unchanged and V1 cannot execute Gate B.
- [ ] No optional-field version guessing or implicit upgrade exists.
- [ ] No raw credential/contact data enters schema, canonical JSON, error, result, or test output.
- [ ] Slice A contains no migration and no Slice B/C behavior.
- [ ] Operational Freeze records and checksums remain immutable.
