# Stage 7 Controlled Research Agent Orchestration Implementation Plan

- Approved design:
  `docs/specs/stage-7-controlled-agent-orchestration-design.md`
- Development branch: `stage-7/controlled-agent-orchestration`
- Baseline revision: `5a61e95`
- Design commit: `adb3fcb`
- Python: 3.12.13
- Database: PostgreSQL 17.10
- Starting migration: `0005_rag_citations`
- Target migration: `0006_controlled_research_agent`
- Method: strict RED → GREEN → focused regression → independent commit

## 1. Global execution rules

- [x] Run every pytest command in one foreground process with
  `PYTEST_ADDOPTS=""`.
- [x] Set `TEST_DATABASE_URL` only to the isolated `stock_research_test` database.
- [x] Never run pytest, Alembic, Seed, or schema reset concurrently.
- [x] Record each RED failure in the commit notes or stage report with its exact
  reason.
- [x] A RED run must fail because the named behavior is absent, not because of a
  syntax, import, database, or fixture error.
- [x] Add only the smallest implementation needed for the current task.
- [x] Run `uv run ruff check <changed paths>` and
  `uv run ruff format --check <changed paths>` before every commit.
- [x] Do not alter Stage 2–6 behavior, loosen mypy, add unexplained ignores, or
  introduce network/model dependencies.
- [x] Use `git add -- <explicit paths>` and inspect
  `git diff --cached --name-only` before every commit.
- [x] Do not merge `main`, push, or enter Stage 8.

## 2. Approved versions and limits

| Contract | Value |
|---|---|
| Policy | `controlled-offline-v1` |
| Planner | `deterministic-template-v1` |
| Plan | `research-plan-v1` |
| State machine | `research-run-sm-v1` |
| Observation | `research-observation-v1` |
| Evidence | `research-evidence-v1` |
| Claim builder | `deterministic-claim-builder-v1` |
| Claim validator | `claim-support-v1` |
| Conflict detector | `evidence-conflict-v1` |
| Package | `research-package-v1` |
| Default max Steps | 12 |
| Hard max Steps | 20 |
| Default max Tool calls | 24 |
| Hard max Tool calls | 50 |
| Max calls per Tool | 5 |
| Max retries per Step | 1 |
| Default duration | 120 seconds |
| Hard duration | 600 seconds |
| Model token budget | 0 |

The persisted Policy field names are `max_steps`, `max_tool_calls`,
`max_calls_per_tool`, `max_retries_per_step`, `max_duration_seconds`, and
`model_token_budget`. Existing Stage 4–6 `HTTP`, `RawPayload`, `BlobStorage`,
`IngestionRun`, Snapshot, Calculation Run, and Retrieval Run boundaries are reused
only through approved read-only Tools; Stage 7 does not modify those subsystems.
Synthetic engineering records always carry `SYNTHETIC_TEST_ONLY`,
`NOT_COMPANY_EVIDENCE`, `OFFLINE`, and `NOT_LIVE`.

## 3. Interface inventory

The following interfaces are introduced in this order and may not be referenced by
an earlier task.

```python
def canonical_json(value: object) -> str: ...
def stable_checksum(value: object) -> str: ...

def build_tool_catalog_snapshot(registry: ToolRegistry) -> ToolCatalogSnapshot: ...

class ResearchPolicyRepository(Protocol):
    def get_policy(self, version: str) -> ResearchPolicyRecord | None: ...
    def add_policy(self, value: ResearchPolicyWrite) -> ResearchPolicyRecord: ...

class ResearchRequestRepository(Protocol):
    def add_request(self, value: ResearchRequestWrite) -> ResearchRequestRecord: ...

class ResearchRunRepository(Protocol):
    def create_run(self, value: ResearchRunWrite) -> ResearchAgentRunRecord: ...
    def get_run(self, run_id: UUID, *, for_update: bool = False) -> ResearchAgentRunRecord | None: ...
    def find_reusable_run(self, idempotency_key: str) -> ResearchAgentRunRecord | None: ...
    def update_run(self, run_id: UUID, value: ResearchRunUpdate) -> ResearchAgentRunRecord: ...
    def append_event(self, value: ResearchRunEventWrite) -> ResearchRunEventRecord: ...

class ResearchPlanningRepository(Protocol):
    def add_plan(self, value: ResearchPlanWrite) -> ResearchPlanRecord: ...
    def add_steps(self, values: tuple[ResearchStepWrite, ...]) -> tuple[ResearchStepRecord, ...]: ...
    def get_plan(self, run_id: UUID) -> ResearchPlanRecord | None: ...
    def list_steps(self, plan_id: UUID) -> tuple[ResearchStepRecord, ...]: ...

class ResearchExecutionRepository(Protocol):
    def add_invocation(self, value: ResearchToolInvocationWrite) -> ResearchToolInvocationRecord: ...
    def complete_invocation(self, invocation_id: UUID, value: ResearchToolInvocationCompletion) -> ResearchToolInvocationRecord: ...
    def add_observation(self, value: ResearchObservationWrite) -> ResearchObservationRecord: ...

class ResearchEvidenceRepository(Protocol):
    def add_evidence(self, values: tuple[ResearchEvidenceWrite, ...]) -> tuple[ResearchEvidenceRecord, ...]: ...
    def list_evidence(self, run_id: UUID) -> tuple[ResearchEvidenceRecord, ...]: ...

class ResearchClaimRepository(Protocol):
    def add_claim(self, value: ResearchClaimWrite) -> ResearchClaimRecord: ...
    def add_links(self, values: tuple[ClaimEvidenceLinkWrite, ...]) -> tuple[ClaimEvidenceLinkRecord, ...]: ...
    def complete_claim(self, claim_id: UUID, value: ResearchClaimCompletion) -> ResearchClaimRecord: ...

class ResearchPackageRepository(Protocol):
    def add_package(self, value: ResearchPackageWrite) -> ResearchPackageRecord: ...

class ResearchQueryRepository(Protocol):
    def get_run_view(self, run_id: UUID) -> ResearchAgentRunView | None: ...
    def get_plan_view(self, run_id: UUID) -> ResearchPlanView | None: ...
    def list_step_views(self, run_id: UUID, page: PageRequest) -> Page[ResearchStepView]: ...
    def list_invocation_views(self, run_id: UUID, page: PageRequest) -> Page[ResearchToolInvocationView]: ...
    def list_evidence_views(self, run_id: UUID, page: PageRequest) -> Page[ResearchEvidenceView]: ...
    def list_claim_views(self, run_id: UUID, page: PageRequest) -> Page[ResearchClaimView]: ...
    def get_package_view(self, run_id: UUID) -> ResearchPackageView | None: ...
    def list_event_views(self, run_id: UUID, page: PageRequest) -> Page[ResearchRunEventView]: ...
```

Provider and execution interfaces:

```python
class PlannerProvider(Protocol):
    @property
    def metadata(self) -> PlannerProviderMetadata: ...
    def validate_configuration(self) -> ProviderHealth: ...
    def create_plan(
        self,
        request: ResearchRequestRecord,
        policy: ResearchPolicyRecord,
        tool_catalog: ToolCatalogSnapshot,
    ) -> ResearchPlanDraft: ...

class ReasoningProvider(Protocol):
    @property
    def metadata(self) -> ReasoningProviderMetadata: ...
    def validate_configuration(self) -> ProviderHealth: ...
    def propose_claims(
        self,
        evidence: EvidenceLedgerView,
        policy: ResearchPolicyRecord,
    ) -> tuple[ResearchClaimDraft, ...]: ...

class RegisteredToolInvoker(Protocol):
    def invoke(
        self,
        tool_name: str,
        tool_version: str,
        payload: Mapping[str, object],
    ) -> BaseModel: ...
```

Services:

```python
class ResearchRequestService:
    def create(self, command: CreateResearchRequest) -> ResearchRequestRecord: ...

class ResearchPolicyService:
    def require(self, version: str) -> ResearchPolicyRecord: ...

class ResearchRunStateMachine:
    def transition(self, run_id: UUID, target: ResearchRunStatus, reason: str | None = None) -> ResearchAgentRunRecord: ...

class ResearchPlanValidator:
    def validate(self, draft: ResearchPlanDraft, policy: ResearchPolicyRecord, catalog: ToolCatalogSnapshot) -> ValidatedResearchPlan: ...

class DeterministicTemplatePlanner:
    def create_plan(self, request: ResearchRequestRecord, policy: ResearchPolicyRecord, tool_catalog: ToolCatalogSnapshot) -> ResearchPlanDraft: ...

class RunBudgetTracker:
    def consume_step(self, budget: RunBudget) -> RunBudget: ...
    def consume_tool_call(self, budget: RunBudget, tool_name: str) -> RunBudget: ...
    def consume_retry(self, budget: RunBudget, step_key: str) -> RunBudget: ...
    def ensure_duration(self, budget: RunBudget, elapsed_seconds: Decimal) -> None: ...

class ResearchToolPolicy:
    def authorize(self, context: ControlledRunContext, step: ResearchStepRecord, catalog: ToolCatalogSnapshot, policy: ResearchPolicyRecord) -> AuthorizedToolCall: ...

class ResearchToolExecutor:
    def execute(self, context: ControlledRunContext, step: ResearchStepRecord, arguments: Mapping[str, object], budget: RunBudget) -> ToolExecutionResult: ...

class EvidenceLedgerService:
    def admit(self, context: ControlledRunContext, observations: tuple[ResearchObservationRecord, ...]) -> tuple[ResearchEvidenceRecord, ...]: ...

class DeterministicClaimBuilder:
    def propose_claims(self, evidence: EvidenceLedgerView, policy: ResearchPolicyRecord) -> tuple[ResearchClaimDraft, ...]: ...

class ClaimSupportValidator:
    def validate(self, context: ControlledRunContext, claim: ResearchClaimRecord, links: tuple[ClaimEvidencePair, ...]) -> ResearchClaimCompletion: ...

class EvidenceConflictDetector:
    def detect(self, claim: ResearchClaimRecord, evidence: tuple[ResearchEvidenceRecord, ...]) -> ConflictResult: ...

class ResearchPackageAssembler:
    def assemble(self, run: ResearchAgentRunRecord, claims: tuple[ResearchClaimRecord, ...], evidence: tuple[ResearchEvidenceRecord, ...]) -> ResearchPackageWrite: ...

class ControlledResearchOrchestrator:
    def plan(self, command: CreateResearchRequest) -> ResearchAgentRunRecord: ...
    def run(self, command: CreateResearchRequest) -> ResearchAgentRunRecord: ...
    def resume(self, run_id: UUID) -> ResearchAgentRunRecord: ...
    def pause(self, run_id: UUID) -> ResearchAgentRunRecord: ...
    def cancel(self, run_id: UUID) -> ResearchAgentRunRecord: ...
```

## 4. Task sequence

### Task 1 — Bootstrap the research-agent package boundary

- [x] Files:
  - `tests/unit/test_research_agent_package_boundaries.py`
  - `src/stock_research_agent/domain/research_agent/__init__.py`
- [x] RED: add a test using `importlib.util.find_spec` that requires the package and
  asserts it does not import FastAPI, Typer, SQLAlchemy, provider HTTP code, or blob
  storage.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_package_boundaries.py`
- [x] Expected RED: one assertion failure because the package does not exist.
- [x] GREEN: create only the package initializer with no side effects.
- [x] Expected GREEN: the boundary test passes with zero warnings.
- [x] Commit:
  `test: establish research agent domain boundary`

### Task 2 — Canonical JSON and checksum primitives

- [x] Files:
  - `tests/unit/test_research_agent_canonical.py`
  - `src/stock_research_agent/domain/research_agent/canonical.py`
- [x] Interface:
  - `canonical_json(value: object) -> str`
  - `stable_checksum(value: object) -> str`
- [x] RED cases: key ordering, UUIDs, aware UTC datetimes, Decimal strings, tuples,
  Unicode, float rejection, naive datetime rejection, stable SHA-256.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_canonical.py`
- [x] Expected RED: assertions fail because canonical functions are absent.
- [x] GREEN: implement deterministic encoding without `default=str` or float
  coercion.
- [x] Expected GREEN: all canonical tests pass.
- [x] Commit:
  `feat: add research agent canonical checksums`

### Task 3 — Freeze the 22-Tool Catalog

- [x] Files:
  - `tests/unit/test_research_agent_tool_catalog.py`
  - `src/stock_research_agent/domain/research_agent/tool_catalog.py`
  - `docs/tool-catalog-stage-7-baseline.json`
- [x] Models:
  - `ToolCatalogEntry`
  - `ToolCatalogSnapshot`
- [x] Interface:
  - `build_tool_catalog_snapshot(registry: ToolRegistry) -> ToolCatalogSnapshot`
- [x] Each entry stores name, Tool version, permission, writes, network flag,
  SHA-256 input-schema version, SHA-256 output-schema version, and data domain.
- [x] RED: assert exact 22 names, sorted order, stable schema hashes, catalog checksum,
  and checked-in manifest equality.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_tool_catalog.py`
- [x] Expected RED: Tool Catalog snapshot/manifest assertions fail.
- [x] GREEN: build the immutable snapshot from `ToolRegistry.list()` and add the
  explicit baseline manifest; no Tool registration changes. The baseline manifest
  remains an immutable record of the 22 pre-Stage-7 Tools.
- [x] Expected GREEN: 22 entries match the live Registry and manifest.
- [x] Commit:
  `feat: freeze stage 7 tool catalog`

### Task 4 — Closed vocabularies and strict core schemas

- [x] Files:
  - `tests/unit/test_research_agent_schemas.py`
  - `src/stock_research_agent/domain/research_agent/enums.py`
  - `src/stock_research_agent/domain/research_agent/schemas.py`
- [x] Define all approved Research Type, section, provider, Run/Step/Invocation,
  Observation, Evidence, Claim, Package, event, support-role, mode, health, and error
  enums.
- [x] Define strict frozen value schemas for Policy, Request, Run, Plan, Step,
  Invocation, Observation, Evidence, Claim, link, Package, Event, controlled context,
  budgets, pages, and views.
- [x] RED: invalid enums, extra fields, naive datetimes, floats, oversized payloads,
  invalid Decimal/unit/period Claim shapes, and model tokens above zero fail.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_schemas.py`
- [x] Expected RED: schema contract assertions fail because types are absent.
- [x] GREEN: implement only closed schemas and validators.
- [x] Expected GREEN: schema tests pass and JSON Decimal output is a string.
- [x] Commit:
  `feat: add controlled research agent schemas`

### Task 5 — Small repository protocols

- [x] Files:
  - `tests/unit/test_research_agent_repository_boundaries.py`
  - `src/stock_research_agent/domain/research_agent/repositories.py`
- [x] Define the nine protocols listed in section 3 with no SQLAlchemy imports.
- [x] RED: AST boundary test requires each exact method and rejects framework/DB
  imports.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_repository_boundaries.py`
- [x] Expected RED: protocol-method assertions fail.
- [x] GREEN: add typed Protocols only.
- [x] Expected GREEN: boundary and mypy-focused checks pass.
- [x] Commit:
  `feat: define research agent repository ports`

### Task 6 — Versioned Research Policy and explicit seed

- [x] Files:
  - `tests/unit/test_research_agent_policy.py`
  - `src/stock_research_agent/domain/research_agent/policies.py`
- [x] Interfaces:
  - `ResearchPolicyService.require(version: str) -> ResearchPolicyRecord`
  - `ResearchPolicySeedService.seed_v1() -> PolicySeedResult`
- [x] RED: exact defaults/hard maxima, explicit 22-Tool allowlist, query-Tool
  exclusion, model/synthetic disabled, idempotent seed, incompatible-content
  rejection, no overwrite.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_policy.py`
- [x] Expected RED: Policy service/seed behavior assertions fail.
- [x] GREEN: implement immutable `controlled-offline-v1` seed and validation.
- [x] Expected GREEN: Policy tests pass with model token budget zero.
- [x] Commit:
  `feat: add immutable research policy`

### Task 7 — Research Request preflight

- [x] Files:
  - `tests/unit/test_research_agent_requests.py`
  - `src/stock_research_agent/domain/research_agent/requests.py`
- [x] Interface:
  - `ResearchRequestService.create(command: CreateResearchRequest) -> ResearchRequestRecord`
- [x] Inject small ports for Security resolution, Snapshot read, Policy read, Tool
  Catalog read, and Request persistence.
- [x] RED: Security/Snapshot/as-of required; explicit Snapshot only; mismatch,
  incomplete/future Snapshot, invalid research type/section/Policy, budget expansion,
  arbitrary instruction, and test mode rejection in production.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_requests.py`
- [x] Expected RED: preflight behavior assertions fail.
- [x] GREEN: implement fixed preflight order and immutable request checksum.
- [x] Expected GREEN: all request tests pass without database access.
- [x] Commit:
  `feat: add research request preflight`

### Task 8 — Run state machine and event vocabulary

- [x] Files:
  - `tests/unit/test_research_agent_state_machine.py`
  - `src/stock_research_agent/domain/research_agent/state_machine.py`
- [x] Interface:
  - `ResearchRunStateMachine.transition(...)`
- [x] RED: every approved transition passes; every forbidden transition fails;
  terminal states reject recovery/mutation; exactly one sequenced Event is appended
  in the same repository operation.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_state_machine.py`
- [x] Expected RED: transition assertions fail.
- [x] GREEN: implement the closed transition map and event mapping.
- [x] Expected GREEN: state-machine matrix passes.
- [x] Commit:
  `feat: add research run state machine`

### Task 9 — Plan checksum and immutable Step definitions

- [x] Files:
  - `tests/unit/test_research_plan_checksum.py`
  - `src/stock_research_agent/domain/research_agent/planning.py`
- [x] Functions:
  - `canonical_plan_payload(draft: ResearchPlanDraft) -> dict[str, object]`
  - `plan_checksum(draft: ResearchPlanDraft) -> str`
- [x] RED: IDs/timestamps/status do not affect checksum; Step order, Tool version,
  dependencies, input binding, Policy/planner/catalog versions do.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_plan_checksum.py`
- [x] Expected RED: checksum behavior assertions fail.
- [x] GREEN: implement canonical immutable Plan representation.
- [x] Expected GREEN: stable independently expected hashes pass.
- [x] Commit:
  `feat: add deterministic research plan checksums`

### Task 10 — Deterministic DAG validator

- [x] Files:
  - `tests/unit/test_research_plan_validator.py`
  - `src/stock_research_agent/domain/research_agent/plan_validation.py`
- [x] Interface:
  - `ResearchPlanValidator.validate(...) -> ValidatedResearchPlan`
- [x] RED: duplicate keys/indexes, gaps, missing/self dependencies, cycles, missing
  identity/Snapshot, incorrect Claim ordering, unknown/wrong-version/write/network/
  denied/query Tool, and Step-budget excess are rejected without repair.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_plan_validator.py`
- [x] Expected RED: invalid Plan cases are not rejected as specified.
- [x] GREEN: implement stable topological validation with no dynamic evaluation.
- [x] Expected GREEN: valid DAG passes; every negative case returns its exact code.
- [x] Commit:
  `feat: validate finite research plan dags`

### Task 11 — Deterministic Template Planner

- [x] Files:
  - `tests/golden/research_plans.json`
  - `tests/unit/test_deterministic_research_planner.py`
  - `src/stock_research_agent/domain/research_agent/planning.py`
- [x] Interface:
  - `DeterministicTemplatePlanner.create_plan(...)`
- [x] RED: six research types match independently written Golden Step lists,
  dependencies, fixed query templates, Tool versions, and checksums; FULL has exactly
  12 finite Steps.
- [x] Run:
  `uv run pytest -W error tests/unit/test_deterministic_research_planner.py`
- [x] Expected RED: planner output is absent.
- [x] GREEN: implement six versioned templates and deterministic composition only.
- [x] Expected GREEN: all Golden plans and repeated-call equality pass.
- [x] Commit:
  `feat: add deterministic research templates`

### Task 12 — Provider ports and production/test isolation

- [x] Files:
  - `tests/support/research_agent_providers.py`
  - `tests/unit/test_research_agent_provider_boundaries.py`
  - `src/stock_research_agent/domain/research_agent/providers.py`
- [x] Interfaces: `PlannerProvider`, `ReasoningProvider`,
  `BlockedModelProviderMetadata`, production provider validation.
- [x] RED: deterministic providers are ready; model types are blocked; Scripted
  providers are marked test-only; production modules cannot import test support or
  discover environment model configuration.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_provider_boundaries.py`
- [x] Expected RED: provider boundary assertions fail.
- [x] GREEN: add Protocols and blocked metadata; scripted implementations only under
  `tests/support`.
- [x] Expected GREEN: isolation and zero-model-token assertions pass.
- [x] Commit:
  `feat: add blocked research provider ports`

### Task 13 — Hard Run budgets

- [x] Files:
  - `tests/unit/test_research_agent_budgets.py`
  - `src/stock_research_agent/domain/research_agent/budgets.py`
- [x] Interface: `RunBudgetTracker` methods in section 3.
- [x] RED: Step, total Tool, per-Tool, duration, retry and model budgets; no
  expansion; pause/resume retains consumption; exact warning codes.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_budgets.py`
- [x] Expected RED: budget exhaustion is not enforced.
- [x] GREEN: immutable budget updates and fixed exceptions.
- [x] Expected GREEN: all hard-limit cases pass; consumed model tokens stay zero.
- [x] Commit:
  `feat: enforce research run budgets`

### Task 14 — Research Tool Policy

- [x] Files:
  - `tests/unit/test_research_tool_policy.py`
  - `src/stock_research_agent/domain/research_agent/tool_policy.py`
- [x] Interface:
  - `ResearchToolPolicy.authorize(...) -> AuthorizedToolCall`
- [x] RED: exact name/version/allowlist only; unknown, prefix, query Tool, write,
  network, admin, disabled and catalog-drift cases fail.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_tool_policy.py`
- [x] Expected RED: unauthorized Tool cases are not denied.
- [x] GREEN: implement deny-by-default authorization.
- [x] Expected GREEN: all permission cases return stable codes.
- [x] Commit:
  `feat: enforce research tool policy`

### Task 15 — Controlled context and input binding

- [x] Files:
  - `tests/unit/test_research_tool_context.py`
  - `src/stock_research_agent/domain/research_agent/tool_context.py`
- [x] Functions:
  - `bind_tool_input(context, authorized_call, arguments) -> Mapping[str, object]`
  - `validate_output_scope(context, result) -> None`
- [x] RED: Security, Snapshot, as-of, Run, Request, Policy and Catalog replacement;
  future time; other Run IDs; URL/path/SQL/provider/model/environment fields; limit
  expansion.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_tool_context.py`
- [x] Expected RED: malicious bindings are accepted.
- [x] GREEN: closed binding descriptors and recursive forbidden-key/value checks.
- [x] Expected GREEN: exact controlled values are injected and override attempts fail.
- [x] Commit:
  `feat: lock research tool context`

### Task 16 — Tool Invocation lifecycle

- [x] Files:
  - `tests/unit/test_research_tool_invocations.py`
  - `src/stock_research_agent/domain/research_agent/invocations.py`
- [x] Functions:
  - `start_invocation(...) -> ResearchToolInvocationWrite`
  - `complete_invocation(...) -> ResearchToolInvocationCompletion`
  - `redact_tool_payload(...) -> dict[str, object]`
- [x] RED: stable input checksum, secret/header/path redaction, attempt uniqueness,
  bounded payload, terminal lifecycle and safe errors.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_tool_invocations.py`
- [x] Expected RED: Invocation lifecycle assertions fail.
- [x] GREEN: add deterministic lifecycle helpers.
- [x] Expected GREEN: Invocation tests pass with no sensitive values.
- [x] Commit:
  `feat: record bounded research tool invocations`

### Task 17 — Observation builder

- [x] Files:
  - `tests/unit/test_research_observations.py`
  - `src/stock_research_agent/domain/research_agent/observations.py`
- [x] Interface:
  - `ResearchObservationBuilder.build(...) -> ResearchObservationWrite`
- [x] RED: only schema-valid output creates a valid Observation; output checksum,
  256 KiB bound, source IDs, provenance, Snapshot/as-of, Tool-error and synthetic
  markers.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_observations.py`
- [x] Expected RED: Observation validation behavior is absent.
- [x] GREEN: implement safe output canonicalization and typed observations.
- [x] Expected GREEN: all Observation cases pass.
- [x] Commit:
  `feat: add immutable research observations`

### Task 18 — Tool Executor and bounded retry

- [x] Files:
  - `tests/unit/test_research_tool_executor.py`
  - `src/stock_research_agent/domain/research_agent/tool_execution.py`
- [x] Interface:
  - `ResearchToolExecutor.execute(...) -> ToolExecutionResult`
- [x] RED: Policy/schema/context/budget gates order; Registry input/output failures;
  one retry only for explicit `TRANSIENT_INTERNAL`; no retry for every forbidden
  code; identical retry input; no sleep/randomness.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_tool_executor.py`
- [x] Expected RED: executor behavior assertions fail.
- [x] GREEN: compose Policy, binder, budget, invoker, Invocation and Observation
  components without Claim logic.
- [x] Expected GREEN: exact call/attempt order and budget consumption pass.
- [x] Commit:
  `feat: execute approved research tools safely`

### Task 19 — Evidence Ledger admission

- [x] Files:
  - `tests/unit/test_research_evidence_ledger.py`
  - `src/stock_research_agent/domain/research_agent/evidence.py`
- [x] Interface:
  - `EvidenceLedgerService.admit(...)`
- [x] RED: Run/Security/Snapshot/as-of/source/checksum validation; valid/invalid/
  future/missing/blocked statuses; unknown publication; Citation validity; metric
  Calculation Run/Input lineage; synthetic status.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_evidence_ledger.py`
- [x] Expected RED: invalid Evidence is admitted as valid.
- [x] GREEN: implement typed source validators and immutable admission results.
- [x] Expected GREEN: every evidence rule returns the independently expected status.
- [x] Commit:
  `feat: add point in time evidence ledger`

### Task 20 — Deterministic Claim builder

- [x] Files:
  - `tests/unit/test_deterministic_claim_builder.py`
  - `src/stock_research_agent/domain/research_agent/claims.py`
- [x] Interface:
  - `DeterministicClaimBuilder.propose_claims(...)`
- [x] RED: only structured identity, available financial, data-quality and limitation
  candidates; no support assignment; no free-form report, advice, prohibited company
  assertions, or pseudo-confidence.
- [x] Run:
  `uv run pytest -W error tests/unit/test_deterministic_claim_builder.py`
- [x] Expected RED: candidate rules are absent.
- [x] GREEN: fixed evidence-type-to-candidate mappings.
- [x] Expected GREEN: candidates remain `CANDIDATE` and untrusted.
- [x] Commit:
  `feat: build deterministic research claim candidates`

### Task 21 — Claim-Evidence links and support validation

- [x] Files:
  - `tests/unit/test_claim_support_validator.py`
  - `src/stock_research_agent/domain/research_agent/claims.py`
- [x] Interface:
  - `ClaimSupportValidator.validate(...)`
- [x] RED: identity/fact/metric/document/valuation/data-quality rules; same Run;
  primary validity; unit/period/as-of/formula/lineage; synthetic/unknown/future/
  blocked primary rejection; missing evidence; link uniqueness.
- [x] Run:
  `uv run pytest -W error tests/unit/test_claim_support_validator.py`
- [x] Expected RED: unsupported candidates can be marked supported.
- [x] GREEN: deterministic support matrix; only validator sets final support.
- [x] Expected GREEN: five support states match Golden expectations.
- [x] Commit:
  `feat: validate claim evidence support`

### Task 22 — Evidence conflict detector

- [x] Files:
  - `tests/unit/test_research_evidence_conflicts.py`
  - `src/stock_research_agent/domain/research_agent/conflicts.py`
- [x] Interface:
  - `EvidenceConflictDetector.detect(...)`
- [x] RED: value, provider, restatement, opposite document, currency, unit, Security,
  Snapshot, future and synthetic/real conflicts; preserve all evidence; no newest,
  averaging or source-priority resolution.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_evidence_conflicts.py`
- [x] Expected RED: conflict cases are not detected.
- [x] GREEN: deterministic pair/group comparisons.
- [x] Expected GREEN: conflicts are stable and Claim completion is `CONFLICTING`.
- [x] Commit:
  `feat: detect research evidence conflicts`

### Task 23 — Research Package assembly

- [x] Files:
  - `tests/golden/research_packages.json`
  - `tests/unit/test_research_package_assembler.py`
  - `src/stock_research_agent/domain/research_agent/packages.py`
- [x] Interface:
  - `ResearchPackageAssembler.assemble(...)`
- [x] RED: complete/partial/blocked/failed rules; ten section statuses; visible
  unsupported/conflicting/blocked/quality/limitations; one checksum; prohibited
  narrative/advice/rating/target/forecast fields absent.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_package_assembler.py`
- [x] Expected RED: Package output is absent.
- [x] GREEN: assemble bounded structural IDs/summaries only.
- [x] Expected GREEN: independent Golden Package payloads/checksums pass.
- [x] Commit:
  `feat: assemble structured research packages`

### Task 24 — Run idempotency

- [x] Files:
  - `tests/unit/test_research_run_idempotency.py`
  - `src/stock_research_agent/domain/research_agent/idempotency.py`
- [x] Functions:
  - `research_run_idempotency_key(...) -> str`
  - `is_reusable_run(run, policy) -> bool`
- [x] RED: every required input affects key; identical inputs stable; catalog drift,
  Policy/planner/Snapshot/as-of differences; failed/cancelled/partial reuse rules.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_run_idempotency.py`
- [x] Expected RED: idempotency behavior assertions fail.
- [x] GREEN: canonical key and explicit reusable-state policy.
- [x] Expected GREEN: independent expected hashes pass.
- [x] Commit:
  `feat: add research run idempotency`

### Task 25 — Pause, resume, cancel, and budget continuity

- [x] Files:
  - `tests/unit/test_research_run_resume.py`
  - `src/stock_research_agent/domain/research_agent/resume.py`
- [x] Interfaces:
  - `ResearchRunControlService.pause(run_id)`
  - `resume(run_id, current_policy, current_catalog)`
  - `cancel(run_id)`
- [x] RED: only PAUSED resumes; terminal rejection; exact Policy/Catalog/Snapshot
  revalidation; completed Steps not repeated; unfinished Invocation not reused;
  budgets retained; Events appended.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_run_resume.py`
- [x] Expected RED: lifecycle safeguards are absent.
- [x] GREEN: implement control service over state-machine and repositories.
- [x] Expected GREEN: pause/resume/cancel matrix passes.
- [x] Commit:
  `feat: control research run pause and resume`

### Task 26 — Controlled orchestrator

- [x] Files:
  - `tests/unit/test_controlled_research_orchestrator.py`
  - `src/stock_research_agent/domain/research_agent/orchestration.py`
- [x] Interface: `ControlledResearchOrchestrator` methods in section 3.
- [x] RED: fixed component order, one finite Step at a time, no skipped required
  Step, budget termination, Plan invalidity, blocked evidence, Claim validation
  before Package, append-only Events, no dynamic Steps/model/network.
- [x] Run:
  `uv run pytest -W error tests/unit/test_controlled_research_orchestrator.py`
- [x] Expected RED: orchestration behavior is absent.
- [x] GREEN: thin coordinator only; delegate all rules.
- [x] Expected GREEN: call order and terminal outcomes pass.
- [x] Commit:
  `feat: orchestrate finite research runs`

### Task 27 — SQLAlchemy Stage 7 models

- [x] Files:
  - `tests/unit/test_research_agent_models.py`
  - `src/stock_research_agent/db/models/research_agent.py`
  - `src/stock_research_agent/db/models/__init__.py`
- [x] Add exactly the 12 approved pluralized tables, explicit named constraints,
  `RESTRICT` foreign keys, JSONB bounds, indexes, and typed UTC columns.
- [x] RED: metadata test requires table/column/FK/CHECK/UNIQUE/index parity and no
  changes to existing table definitions.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_models.py`
- [x] Expected RED: Stage 7 tables are absent.
- [x] GREEN: implement declarative models only.
- [x] Expected GREEN: metadata parity tests pass.
- [x] Commit:
  `feat: add controlled research agent models`

### Task 28 — Alembic 0006 migration and database guards

- [x] Files:
  - `tests/integration/test_research_agent_migrations.py`
  - `migrations/versions/0006_create_controlled_research_agent.py`
- [x] RED: isolated PostgreSQL migration test requires 12 tables, named constraints,
  indexes, transition/lineage/immutability triggers and downgrade/re-upgrade.
- [x] Run:
  `uv run pytest -W error tests/integration/test_research_agent_migrations.py`
- [x] Expected RED: revision/table assertions fail against `0005`.
- [x] GREEN: create migration matching models; no seed, Tool, network or historical
  table mutation.
- [x] Expected GREEN: base→0006→0005→0006 passes on test DB.
- [x] Commit:
  `feat: migrate controlled research agent schema`

### Task 29 — SQLAlchemy repository implementation

- [x] Files:
  - `tests/integration/test_research_agent_repository_postgres.py`
  - `src/stock_research_agent/db/repositories/research_agent.py`
  - `src/stock_research_agent/db/repositories/__init__.py`
- [x] Implement the small repository protocols with parameterized SQLAlchemy queries,
  bounded pages, row locks, safe record conversion and no commit ownership.
- [x] RED: create/read/update lifecycle, append events, immutable children, rollback,
  cross-Run lineage rejection, duplicate Step/attempt/link/package.
- [x] Run:
  `uv run pytest -W error tests/integration/test_research_agent_repository_postgres.py`
- [x] Expected RED: repository integration behavior is absent.
- [x] GREEN: implement repository against isolated PostgreSQL.
- [x] Expected GREEN: repository tests pass and Session rollback isolates data.
- [x] Commit:
  `feat: persist controlled research runs`

### Task 30 — PostgreSQL Policy seed and concurrent idempotency

- [x] Files:
  - `tests/integration/test_research_agent_policy_postgres.py`
  - `src/stock_research_agent/db/repositories/research_agent.py`
- [x] RED: first/second seed, incompatible seed, Policy immutability, concurrent
  identical active Run convergence, failed/cancelled history, no development DB use.
- [x] Run:
  `uv run pytest -W error tests/integration/test_research_agent_policy_postgres.py`
- [x] Expected RED: concurrency/seed assertions fail.
- [x] GREEN: use unique/partial indexes and IntegrityError convergence; no retry
  sleep.
- [x] Expected GREEN: deterministic concurrency tests pass.
- [x] Commit:
  `feat: converge research policy and run writes`

### Task 31 — Read-only Research query service

- [x] Files:
  - `tests/unit/test_research_agent_queries.py`
  - `src/stock_research_agent/domain/research_agent/queries.py`
- [x] Interface:
  - `ResearchAgentQueryService` with eight bounded read methods.
- [x] RED: safe not-found, stable order, max limits/cursors, no full document,
  RawPayload, local path, secret, input/output body or SQL fields.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_queries.py`
- [x] Expected RED: query DTO behavior is absent.
- [x] GREEN: implement read-only projection service.
- [x] Expected GREEN: query tests pass with no write calls.
- [x] Commit:
  `feat: query persisted research runs`

### Task 32 — Eight Research Run query Tools

- [x] Files:
  - `tests/contract/test_research_agent_tools.py`
  - `src/stock_research_agent/tools/schemas_research_agent.py`
  - `src/stock_research_agent/tools/research_agent.py`
  - `src/stock_research_agent/tools/registry.py`
  - `docs/tool-catalog-stage-7-final.json`
- [x] Add exactly the eight approved `1.0.0` query Tools to the existing canonical
  Registry and a `create_research_agent_tool_registry` factory.
- [x] RED: metadata/schema snapshots, read-only/offline flags, bounded pagination,
  safe missing Run, no execution/create/resume/model/raw path behavior.
- [x] Run:
  `uv run pytest -W error tests/contract/test_research_agent_tools.py`
- [x] Expected RED: canonical registrations are absent.
- [x] GREEN: add thin query adapters only; keep them outside Policy execution
  allowlist; preserve the 22-Tool baseline manifest and add a separate final Catalog
  manifest/checksum containing the eight query Tools.
- [x] Expected GREEN: Tool contracts pass; old Run catalog versions remain distinct.
- [x] Commit:
  `feat: add read only research query tools`

### Task 33 — Eight GET API routes

- [x] Files:
  - `tests/contract/test_research_agent_api_contract.py`
  - `src/stock_research_agent/api/routes/research_agent.py`
  - `src/stock_research_agent/api/dependencies.py`
  - `src/stock_research_agent/api/router.py`
- [x] Add the eight approved GET routes under the existing prefix only.
- [x] RED: successful projections, 404, UUID/query 422, bounded pagination,
  `X-Request-ID`, OpenAPI, no write methods, no sensitive fields or hidden writes.
- [x] Run:
  `uv run pytest -W error tests/contract/test_research_agent_api_contract.py`
- [x] Expected RED: routes are absent.
- [x] GREEN: compose query service and GET router.
- [x] Expected GREEN: contract tests pass and OpenAPI contains no Agent write route.
- [x] Commit:
  `feat: expose read only research agent api`

### Task 34 — Explicit Agent CLI

- [x] Files:
  - `tests/integration/test_research_agent_cli.py`
  - `src/stock_research_agent/cli_agent.py`
  - `src/stock_research_agent/cli.py`
- [x] Add explicit Policy seed, plan/run/pause/resume/cancel writes and all approved
  read commands with JSON/human output and exit codes 0/2/3/4.
- [x] RED: missing Snapshot/type/Policy/as-of, no latest default, idempotent seed,
  read commands, lifecycle writes, no implicit network/refresh/parse/index/embed/model.
- [x] Run:
  `uv run pytest -W error tests/integration/test_research_agent_cli.py`
- [x] Expected RED: Agent CLI group is absent.
- [x] GREEN: compose services in explicit Session scopes; no API writes.
- [x] Expected GREEN: CLI tests pass against isolated PostgreSQL.
- [x] Commit:
  `feat: add explicit controlled research cli`

### Task 35 — Industrial FII honest-degradation flow

- [x] Files:
  - `tests/integration/test_research_agent_industrial_fii.py`
- [x] RED: run `601138.SH` against its real persisted Snapshot and assert identity,
  fixed Plan, read-only Tools, blocked document evidence, no synthetic evidence, only
  supported identity/data-quality/limitation Claims, partial/blocked Package,
  prohibited company assertions absent, idempotency.
- [x] Run:
  `uv run pytest -W error tests/integration/test_research_agent_industrial_fii.py`
- [x] Expected RED: acceptance flow fails at the first missing orchestration adapter
  or incorrect terminal result.
- [x] GREEN: make the smallest orchestration/repository composition correction;
  do not add Fixture or company data.
- [x] Expected GREEN: real-state flow passes as `PARTIAL` or `BLOCKED`.
- [x] Commit:
  `test: verify industrial fii evidence boundaries`

### Task 36 — Micron honest-degradation flow

- [x] Files:
  - `tests/integration/test_research_agent_micron.py`
- [x] RED: `MU` identity/CIK/Snapshot; metadata not body; blocked filings; no
  synthetic evidence or HBM/inventory/data-center assertions; partial/blocked
  Package; idempotency.
- [x] Run:
  `uv run pytest -W error tests/integration/test_research_agent_micron.py`
- [x] Expected RED: acceptance flow fails if metadata is promoted or result is
  complete.
- [x] GREEN: smallest composition correction; no company-body or financial values.
- [x] Expected GREEN: real-state Micron flow passes as `PARTIAL` or `BLOCKED`.
- [x] Commit:
  `test: verify micron evidence boundaries`

### Task 37 — Isolated Synthetic complete flow

- [x] Files:
  - `tests/integration/test_research_agent_synthetic_flow.py`
  - `tests/fixtures/research_agent/synthetic_research.json`
  - `tests/fixtures/research_agent/synthetic_research.manifest.json`
- [x] RED: neutral test Security, four markers, complete finite Plan, financial and
  valid Citation evidence, conflict branch, complete Package, idempotency,
  pause/resume, budget/failure degradation, no real Security linkage.
- [x] Run:
  `uv run pytest -W error tests/integration/test_research_agent_synthetic_flow.py`
- [x] Expected RED: isolated complete flow is absent.
- [x] GREEN: add test-only Fixture and scripted providers under tests; production
  composition remains unchanged.
- [x] Expected GREEN: Synthetic flow is `COMPLETE` and both real-company isolation
  checks pass.
- [x] Commit:
  `test: add isolated synthetic research flow`

### Task 38 — Independent Golden acceptance suite

- [x] Files:
  - `tests/golden/research_agent_expected.json`
  - `tests/unit/test_research_agent_golden.py`
- [x] Hand-calculate expected Plan checksum, idempotency key, Tool order, budget
  consumption, Evidence Ledger, support/conflict states, Package checksum, two
  real-company degradations, Synthetic complete result, future rejection and
  injection invariance.
- [x] RED: compare current outputs to independent Golden values before adjusting
  implementation.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_golden.py`
- [x] Expected RED: any remaining semantic mismatch fails with a precise field.
- [x] GREEN: correct the smallest domain rule; never regenerate expected values from
  the implementation.
- [x] Expected GREEN: all 15 approved Golden scenarios pass.
- [x] Commit:
  `test: add controlled research golden contracts`

### Task 39 — Security and no-model suite

- [x] Files:
  - `tests/unit/test_research_agent_security.py`
  - `tests/unit/test_research_agent_no_model.py`
- [x] RED: Tool/name/context/Policy/budget injection; URL/path/SQL/Shell/env/secret;
  document-triggered Tool/network/Claim; Scripted production registration; model
  package/config/network absence; synthetic isolation.
- [x] Run:
  `uv run pytest -W error tests/unit/test_research_agent_security.py tests/unit/test_research_agent_no_model.py`
- [x] Expected RED: any unguarded security path fails explicitly.
- [x] GREEN: minimum guard hardening only, without blanket exception swallowing.
- [x] Expected GREEN: security tests pass offline with model tokens zero.
- [x] Commit:
  `test: enforce research agent security boundaries`

### Task 40 — Full PostgreSQL lifecycle suite

- [x] Files:
  - `tests/integration/test_research_agent_postgres.py`
- [x] RED: tables/FKs/CHECKs/uniques/indexes, all entities, transition parity,
  terminal immutability, append-only Events, concurrent Run, transaction rollback,
  pause/resume, three flows, isolated database, no schema pollution.
- [x] Run:
  `uv run pytest -W error tests/integration/test_research_agent_postgres.py`
- [x] Expected RED: any database/application parity gap fails.
- [x] GREEN: smallest model/migration/repository trigger correction.
- [x] Expected GREEN: full Stage 7 PostgreSQL suite passes in one process.
- [x] Commit:
  `test: verify controlled research postgres lifecycle`

### Task 41 — Documentation and first Reflection

- [x] Files:
  - all 17 documentation paths approved in the design;
  - `tests/unit/test_stage7_documentation.py`;
  - `docs/reflection/stage-7-round-1.md`.
- [x] RED: documentation contract test requires finite Agent, deterministic defaults,
  Tool/Policy/budget/state/evidence/claim/conflict/as-of/injection/synthetic/sample
  limits and all prohibited capabilities.
- [x] Run:
  `uv run pytest -W error tests/unit/test_stage7_documentation.py`
- [x] Expected RED: missing Stage 7 documents/sections fail.
- [x] GREEN: write accurate commands/contracts, then perform six-role review with
  complete finding records.
- [x] Expected GREEN: documentation test passes; all Round 1 `CRITICAL`/`HIGH`
  findings have explicit fixes assigned.
- [x] Commit:
  `docs: document controlled research orchestration`

### Task 42 — Reflection fixes, Round 2, report, and final gates

- [x] Files:
  - code/tests/docs named by Round 1 findings;
  - `docs/reflection/stage-7-round-2.md`;
  - `docs/stage-7-implementation-report.md`.
- [x] For every code finding, add a focused failing regression test and observe RED
  before fixing.
- [x] RED: run every newly added Round 1 regression test before its fix.
- [x] Expected RED: each regression test fails for the exact recorded finding, with
  no collection, fixture, or environment error.
- [x] GREEN: apply the minimum fix for each finding and update only the affected
  documentation facts.
- [x] Run: execute each focused regression command recorded in Round 1 to GREEN,
  then:
  - `uv sync`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy src`
  - `uv run pytest -W error`
- [x] Expected: all collected tests pass, zero failed/errors/skipped/warnings, no
  residual pytest process.
- [x] Expected GREEN: focused regressions, full quality gates, database cycles, and
  all 36 Round 2 checks pass.
- [x] Run sequential development and test database cycles:
  - `uv run alembic current`
  - `uv run alembic upgrade head`
  - `uv run alembic downgrade -1`
  - `uv run alembic upgrade head`
  - `uv run alembic current`
- [x] Expected: both databases end at `0006_controlled_research_agent`, Stage 2–6
  tables remain, Stage 7 catalog/constraints/indexes/triggers match models, no open
  transactions or schema pollution.
- [x] Round 2 reruns all 36 approved checks and records zero unresolved `CRITICAL`
  and `HIGH`.
- [x] Report real counts/durations and `CONDITIONAL GO` unless evidence/provider
  reality materially changes through separately approved data.
- [x] Commit:
  `feat: add controlled research agent orchestration`

## 5. Plan self-check

Run before Task 1:

```powershell
$plan = Get-Content -Raw docs/plans/stage-7-controlled-agent-orchestration.md
$forbidden = @(
    ("T" + "BD"),
    ("T" + "ODO"),
    ("F" + "IXME"),
    ("添加" + "适当测试"),
    ("实现" + "相应功能")
)
$forbidden | ForEach-Object {
    if ($plan.Contains($_)) { throw "Forbidden placeholder phrase detected" }
}
```

- [x] Prompt coverage: all 22 supplemental sections and all original Stage 7
  requirements map to at least one Task.
- [x] Design coverage: all 29 design sections map to Tasks 1–42.
- [x] State consistency: Run, Step, Invocation and Claim transitions match schemas,
  state machine, migration triggers and tests.
- [x] Type consistency: every referenced interface appears in section 3 or an earlier
  Task.
- [x] Tool consistency: exact audited 22 names before Task 32; exactly eight explicit
  query Tools added in Task 32; no prefix authorization.
- [x] Database consistency: exactly 12 Stage 7 tables in models and migration;
  downgrade touches no earlier table.
- [x] Policy consistency: default/hard limits and zero model budget match design.
- [x] Evidence/Claim consistency: only deterministic validator assigns support;
  synthetic/future/unknown/blocked primary evidence is rejected.
- [x] Synthetic consistency: test-only Policy, Security, providers and fixtures never
  enter production composition or real-company Runs.
- [x] Scope consistency: no model, report, rating, target, forecast, trade, MCP,
  frontend, broker, production Reflection runtime, or Stage 8 behavior.
- [x] Task completeness: each Task names files, interface/behavior, RED command and
  expected reason, minimum GREEN, expected pass, and commit message.
- [x] Dependency order: no Task uses an undefined domain interface.

## 6. Completion and handoff

After Task 42:

- [x] Inspect every Stage 7 commit and changed path.
- [x] Check for secrets, tokens, URLs with credentials, local database files, Blob
  files, absolute paths, model dependencies, and unexpected binaries.
- [x] Confirm branch worktree is clean.
- [x] Preserve `stage-7/controlled-agent-orchestration`.
- [x] Do not merge or push without the user's explicit finishing choice.
- [x] Present exactly:
  - Merge back to main locally
  - Push and create a Pull Request
  - Keep branch as-is
  - Discard this work
