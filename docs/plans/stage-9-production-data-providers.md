# Stage 9 Production Data Providers Implementation Plan

- Approved design: `docs/specs/stage-9-production-data-provider-design.md`
- Capability register: `docs/provider-capability-matrix.md`
- Development branch: `stage-9/production-data-providers`
- Baseline revision: `66788fa`
- Design commit: `d15440e`
- Python: 3.12.13
- PostgreSQL: 17.10
- Starting migration: `0007_verifiable_reports`
- Target migration: `0008_create_production_data_providers`
- Method: strict RED → minimum GREEN → focused regression → independent commit
- Default execution mode: `OFFLINE`, `NOT_LIVE`, provider credentials not read

## 1. Non-negotiable execution rules

- [ ] Run every pytest process in the foreground, single-process, with
  `PYTEST_ADDOPTS=""`; never overlap pytest, Alembic, Seed, schema reset, or
  Provider control commands.
- [ ] Set `DATABASE_URL` only to `stock_research` and `TEST_DATABASE_URL` only to
  the independently verified `stock_research_test`.
- [ ] A RED must fail because the named contract is absent, not because of an
  import error, typo, database outage, fixture corruption, or accidental network.
- [ ] Write only the minimum implementation needed for the active Task; run its
  GREEN and named regression before staging explicit paths.
- [ ] Never use `git add .`, skip, xfail, SQLite, sleep-based race masking,
  assertion weakening, implementation-generated expected values, or unexplained
  permanent `type: ignore`.
- [ ] Do not read `TUSHARE_TOKEN`, `US_EOD_API_KEY`, SEC contact identity, model
  credentials, or any other real Provider secret in default tests.
- [ ] Do not send SEC, Tushare, SSE, SZSE, CNINFO, U.S. EOD, embedding, DNS, or
  other external traffic. Loopback PostgreSQL is the only default-test network.
- [ ] The exact gate order is Definition → Capability → License → Provider Policy
  → Credential Reference → Configuration Validation → Live Authorization →
  Network. A blocked earlier gate prevents every later gate from executing.
- [ ] Tools and GET API remain read-only and cache/query-only. Only explicit CLI
  or internal services may write, and no Stage 9 command creates a Snapshot,
  Retrieval Run, Research Agent Run, Report, rating, target price, or trade.
- [ ] Historical Stage 2–8 tables and terminal records remain untouched.
- [ ] `批准执行该Provider的有限Live验证` is the only future authorization phrase
  for one disclosed Provider/capability/budget. It has not been granted.
- [ ] Do not merge `main`, configure a remote, create a PR, or enter Stage 10.

## 2. Database-table purpose review

Table count is not a target. Each retained table has an independently queried,
constrained, or append-only lifecycle that would be weakened by a shared JSON blob.
The review retains 20 tables:

| Table | Independent responsibility |
|---|---|
| `provider_definitions` | Immutable Provider/adapter identity and production state |
| `provider_capabilities` | Explicit versioned allowlist; no name/prefix inference |
| `provider_policies` | Request, endpoint, rate, retry, cache, and storage limits |
| `provider_license_policies` | Versioned acquisition/storage/cache/derived-use decision |
| `provider_credential_references` | Secret-free metadata naming an approved resolver slot |
| `provider_sync_requests` | Immutable user intent, versions, scope, as-of, budget, mode |
| `provider_sync_plans` | Finite canonical slice DAG and checksum |
| `provider_sync_runs` | Mutable-to-terminal execution state and consumed budgets |
| `provider_sync_checkpoints` | CAS-protected watermark per Provider/capability/scope |
| `provider_request_attempts` | Append-only request accounting and safe response metadata |
| `provider_raw_artifacts` | Immutable source identity, checksum, size, MIME, blob key |
| `provider_ingestion_manifests` | Immutable artifact-to-parsed-batch lineage |
| `provider_cache_entries` | Expiring operational reuse pointer, not evidence |
| `provider_circuit_breakers` | Cross-process failure state isolated by Provider/capability |
| `provider_dead_letters` | Append-only rejected record with bounded safe diagnostic |
| `provider_data_quality_issues` | Append-only validation result and severity |
| `provider_freshness_policies` | Versioned expected-publication/freshness rule |
| `provider_health_snapshots` | Append-only offline readiness observation |
| `provider_audit_events` | Append-only actor/action/decision history |
| `provider_live_validation_runs` | Separate finite authorization/attempt status; never implied |

`provider_sync_plans` is not merged into requests because plan checksum, finite
slices, and replay identity need an immutable query surface. Attempts are not merged
into Runs because retry accounting and safe per-response metadata are one-to-many.
Artifacts, manifests, quality issues, and audit events remain normalized so
immutability, lineage, retention, and restricted-data queries are enforceable.
Cache entries and circuit breakers are operational mutable records and therefore
must not be conflated with immutable evidence.

## 3. Core interface inventory

These interfaces are introduced in the order used below. Later Tasks may reference
only an earlier interface or one explicitly introduced in that Task.

```python
class ProviderDefinitionRepository(Protocol):
    def get_definition(self, code: str, version: str) -> ProviderDefinitionRecord | None: ...
    def list_definitions(self, page: PageRequest) -> Page[ProviderDefinitionRecord]: ...

class ProviderGovernanceRepository(Protocol):
    def get_capability(self, provider_id: UUID, code: str, version: str) -> ProviderCapabilityRecord | None: ...
    def get_policy(self, provider_id: UUID, version: str) -> ProviderPolicyRecord | None: ...
    def get_license_policy(self, provider_id: UUID, version: str) -> SourceLicensePolicyRecord | None: ...
    def get_credential_reference(self, reference_id: UUID) -> CredentialReferenceRecord | None: ...

class ProviderSyncRepository(Protocol):
    def create_request(self, value: ProviderSyncRequestWrite) -> ProviderSyncRequestRecord: ...
    def add_plan(self, value: ProviderSyncPlanWrite) -> ProviderSyncPlanRecord: ...
    def create_run(self, value: ProviderSyncRunWrite) -> ProviderSyncRunRecord: ...
    def get_run(self, run_id: UUID, *, for_update: bool = False) -> ProviderSyncRunRecord | None: ...
    def transition(self, run_id: UUID, value: ProviderRunTransition) -> ProviderSyncRunRecord: ...
    def append_attempt(self, value: ProviderRequestAttemptWrite) -> ProviderRequestAttemptRecord: ...
    def compare_and_swap_checkpoint(self, value: CheckpointAdvance) -> ProviderSyncCheckpointRecord: ...

class ProviderArtifactRepository(Protocol):
    def add_artifact(self, value: ProviderRawArtifactWrite) -> ProviderRawArtifactRecord: ...
    def add_manifest(self, value: ProviderIngestionManifestWrite) -> ProviderIngestionManifestRecord: ...
    def add_quality_issue(self, value: ProviderDataQualityIssueWrite) -> ProviderDataQualityIssueRecord: ...
    def add_dead_letter(self, value: ProviderDeadLetterWrite) -> ProviderDeadLetterRecord: ...

class CredentialResolver(Protocol):
    def resolve_for_execution(
        self,
        reference: CredentialReferenceRecord,
        declared_names: frozenset[str],
    ) -> ResolvedCredentialContext: ...

class ProductionProviderAdapter(Protocol):
    descriptor: ProviderAdapterDescriptor
    def plan(
        self,
        request: ProviderSyncRequestRecord,
        checkpoint: ProviderSyncCheckpointRecord | None,
    ) -> ProviderSyncPlanDraft: ...
    def build_request(
        self,
        slice_: ProviderSyncSlice,
        context: ProviderExecutionContext,
    ) -> ProviderHttpRequestTemplate: ...
    def parse_response(
        self,
        context: ProviderParseContext,
        response: ProviderHttpResponse,
    ) -> ProviderBatch: ...

class ControlledProviderExecutor(Protocol):
    def execute(
        self,
        template: ProviderHttpRequestTemplate,
        context: ProviderExecutionContext,
        budget: ProviderExecutionBudget,
    ) -> ProviderHttpResponse: ...

class ProviderBridge(Protocol):
    def stage(
        self,
        manifest: ProviderIngestionManifestRecord,
        batch: ProviderBatch,
    ) -> ProviderBridgeResult: ...
```

Every record/write/command/result above is a strict frozen Pydantic model. Secret
material exists only in the non-serializable in-memory `ResolvedCredentialContext`.

For every Task below, `Contract/types` is the exact minimum GREEN implementation;
`RED` states the expected pre-implementation failure; the named focused command is
run once to observe that failure and again after the minimum change, where the
expected GREEN is all named tests passing with zero warnings. No later Task's
implementation may be pulled forward merely to make an earlier GREEN pass.

## 4. Task sequence

### Task 0 — Update repository Stage 9 boundary

- [x] Paths: `AGENTS.md`, `tests/unit/test_stage9_repository_guidelines.py`.
- [x] Contract/types: documentation must name this branch, the approved design,
  offline-only implementation, separate Live approval phrase, credential prohibition,
  read-only Tool/API boundary, and Stage 10 prohibition.
- [x] Database: none.
- [x] RED: run `uv run pytest -W error tests/unit/test_stage9_repository_guidelines.py`;
  it fails on stale Stage 8 text.
- [x] GREEN: replace only stale stage guidance; rerun the RED command plus
  `tests/unit/test_stage8_repository_guidelines.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NOT_READ; license=DOCUMENTED;
  live=NOT_ATTEMPTED.
- [x] Commit: `docs: authorize stage 9 offline provider implementation`.

### Task 1 — Provider status vocabulary

- [x] Paths: `tests/unit/test_provider_governance_enums.py`,
  `src/stock_research_agent/domain/providers/__init__.py`,
  `src/stock_research_agent/domain/providers/enums.py`.
- [x] Contract/types: introduce exact `StrEnum` classes for definition,
  capability, license, credential, configuration, authorization, production,
  run, slice, circuit, quality, synthetic, and Live-validation states, including
  `IMPLEMENTED_OFFLINE`, `RESTRICTED_REVIEW_REQUIRED`, `NOT_READ`,
  `NOT_ATTEMPTED`, and `BLOCKED`.
- [x] Database: enum strings later become CHECK values; no native ENUM.
- [x] RED: enum import/value and forbidden-alias assertions fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_governance_enums.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NOT_READ; license=EXPLICIT;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: define provider governance status vocabulary`.

### Task 2 — Provider definition identity

- [x] Paths: `tests/unit/test_provider_definitions.py`,
  `src/stock_research_agent/domain/providers/schemas.py`,
  `src/stock_research_agent/domain/providers/canonical.py`.
- [x] Contract/types: `ProviderDefinitionWrite`, `ProviderDefinitionRecord`,
  `canonical_provider_json(value: object) -> str`, and
  `provider_checksum(value: object) -> str`; validate stable uppercase code,
  semantic adapter version, immutable status, official domains, and safe metadata.
- [x] Database: defines the typed shape for `provider_definitions`.
- [x] RED: canonical checksum, invalid code/version, and mutation tests fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_definitions.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=REFERENCED_ONLY;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add immutable provider definitions`.

### Task 3 — Explicit capability allowlist

- [x] Paths: `tests/unit/test_provider_governance_capabilities.py`,
  `src/stock_research_agent/domain/providers/capabilities.py`.
- [x] Contract/types: `ProviderCapabilityWrite`, `ProviderCapabilityRecord`,
  `CapabilityDecision`, and `ProviderCapabilityGate.evaluate(definition,
  capability_code, capability_version) -> CapabilityDecision`; exact match only.
- [x] Database: typed shape for `provider_capabilities` and unique
  Provider/code/version identity.
- [x] RED: prefix, wildcard, wrong version, inactive, and cross-Provider requests fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_governance_capabilities.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NOT_READ; license=NOT_EVALUATED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: enforce explicit provider capabilities`.

### Task 4 — Versioned source-license policy

- [x] Paths: `tests/unit/test_provider_license_policy.py`,
  `src/stock_research_agent/domain/providers/licenses.py`.
- [x] Contract/types: `SourceLicensePolicyWrite`, `SourceLicensePolicyRecord`,
  `LicenseUseRequest`, `LicenseDecision`, and
  `SourceLicenseGate.evaluate(policy, request) -> LicenseDecision`; separately
  decide acquire, store raw, cache, derive, redistribute, retain, and delete.
- [x] Database: typed shape for `provider_license_policies`.
- [x] RED: unknown/restricted rights block; offline contract success cannot mark
  production approved.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_license_policy.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NOT_READ; license=GATED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add versioned source license gate`.

### Task 5 — Secret-free credential references

- [x] Paths: `tests/unit/test_provider_credential_references.py`,
  `src/stock_research_agent/domain/providers/credentials.py`.
- [x] Contract/types: `CredentialReferenceWrite`, `CredentialReferenceRecord`,
  `CredentialRequirement`, and `validate_credential_reference_metadata(value)`;
  allow only reference ID, Provider ID, resolver kind, declared environment name,
  status, timestamps, and safe labels.
- [x] Database: typed shape for `provider_credential_references`; reject columns or
  fields for value, prefix, suffix, hash, token, key, Cookie, or Authorization.
- [x] RED: secret-shaped fields, arbitrary env names, repr/model dump leakage fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_credential_references.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=METADATA_ONLY; license=PREREQUISITE;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add secret-free credential references`.

### Task 6 — Provider policy and finite budgets

- [x] Paths: `tests/unit/test_provider_policy.py`,
  `src/stock_research_agent/domain/providers/policies.py`.
- [x] Contract/types: `ProviderPolicyWrite`, `ProviderPolicyRecord`,
  `ProviderExecutionBudget`, and `ProviderPolicyGate.evaluate(policy, request)`;
  require finite positive request, byte, duration, retry, redirect, rate, cache,
  and retention bounds.
- [x] Database: typed shape for `provider_policies`.
- [x] RED: unbounded, non-finite, negative, zero-required, excessive retry, and
  caller-overridden limits fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_policy.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NOT_READ; license=MUST_PRECEDE;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: define finite provider policies`.

### Task 7 — Structured blocked reasons and safe errors

- [x] Paths: `tests/unit/test_provider_governance_errors.py`,
  `src/stock_research_agent/domain/providers/errors.py`.
- [x] Contract/types: `ProviderBlockedReason`, `ProviderFailure`,
  `ProviderGateResult`, and error codes for every approved blocked condition;
  `safe_provider_error(exc: Exception) -> ProviderFailure`.
- [x] Database: safe code/detail fields only; no raw exception persistence.
- [x] RED: URLs, headers, SQL, paths, secrets, multiline control text, and unknown
  exceptions are redacted and never swallowed.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_governance_errors.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=REDACTED; license=STRUCTURED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add safe provider failure vocabulary`.

### Task 8 — Repository protocols

- [x] Paths: `tests/unit/test_provider_repository_boundaries.py`,
  `src/stock_research_agent/domain/providers/repositories.py`.
- [x] Contract/types: define the four repository Protocols in section 3 plus
  bounded `ProviderQueryRepository`; domain imports may not include SQLAlchemy,
  FastAPI, Typer, filesystem, HTTP, or socket modules.
- [x] Database: protocol only.
- [x] RED: module-boundary and exact signature tests fail before protocols exist.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_repository_boundaries.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=REFERENCE_ONLY; license=READ_ONLY;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: define provider repository ports`.

### Task 9 — ORM table-manifest review

- [x] Paths: `tests/unit/test_provider_models_manifest.py`,
  `src/stock_research_agent/db/models/providers.py`,
  `src/stock_research_agent/db/models/__init__.py`.
- [x] Contract/types: declare all 20 ORM class names and a manually authored
  expected table/column/constraint/index manifest; each table maps to section 2.
- [x] Database: no table creation yet; manifest rejects giant catch-all JSON,
  secret columns, Float, native ENUM, cascade delete into prior stages, and
  unindexed declared query paths.
- [x] RED: model/table manifest import and structural assertions fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_models_manifest.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=METADATA_ONLY; license=PERSISTED;
  live=NOT_ATTEMPTED.
- [x] Commit: `test: define provider database manifest`.

### Task 10 — Definition/governance ORM models

- [x] Paths: `tests/unit/test_provider_models_governance.py`,
  `src/stock_research_agent/db/models/providers.py`.
- [x] Contract/types: `ProviderDefinition`, `ProviderCapability`,
  `ProviderPolicy`, `ProviderLicensePolicy`, `ProviderCredentialReference`.
- [x] Database: UUID/UTC, RESTRICT FKs, version uniques, CHECK states, safe JSON
  allowlists, and indexes exactly matching Provider/code/version lookups.
- [x] RED: SQLAlchemy metadata constraints and forbidden credential columns fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_models_governance.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=METADATA_ONLY; license=PERSISTED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add provider governance models`.

### Task 11 — Sync lifecycle ORM models

- [x] Paths: `tests/unit/test_provider_models_sync.py`,
  `src/stock_research_agent/db/models/providers.py`.
- [x] Contract/types: `ProviderSyncRequest`, `ProviderSyncPlan`,
  `ProviderSyncRun`, `ProviderSyncCheckpoint`, `ProviderRequestAttempt`.
- [x] Database: idempotency uniques, finite counters, scope/checkpoint uniqueness,
  attempt ordering, terminal timestamps, RESTRICT history, and bounded canonical
  JSON for finite scopes/slices only.
- [x] RED: invalid budgets, duplicate scope, terminal inconsistency, and unbounded
  plan data fail metadata/validator tests.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_models_sync.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=REFERENCE_ID_ONLY; license=BOUND_VERSION;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add provider sync lifecycle models`.

### Task 12 — Artifact and manifest ORM models

- [x] Paths: `tests/unit/test_provider_models_artifacts.py`,
  `src/stock_research_agent/db/models/providers.py`.
- [x] Contract/types: `ProviderRawArtifact`, `ProviderIngestionManifest`,
  `ProviderCacheEntry`.
- [x] Database: SHA-256/size/MIME/source identity checks, blob key not absolute
  path, artifact dedup identity, manifest version/checksum uniqueness, expiry
  checks, and RESTRICT lineage.
- [x] RED: mutable/invalid checksum, unsafe path, missing license decision, and
  cache-as-evidence shapes fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_models_artifacts.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=BOUND_DECISION;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add provider artifact and manifest models`.

### Task 13 — Operational audit ORM models

- [x] Paths: `tests/unit/test_provider_models_operations.py`,
  `src/stock_research_agent/db/models/providers.py`.
- [x] Contract/types: `ProviderCircuitBreaker`, `ProviderDeadLetter`,
  `ProviderDataQualityIssue`, `ProviderFreshnessPolicy`,
  `ProviderHealthSnapshot`, `ProviderAuditEvent`, `ProviderLiveValidationRun`.
- [x] Database: scoped circuit unique, bounded diagnostics, severity/status
  checks, append-only observation identities, finite authorization budget, and
  `NOT_ATTEMPTED` defaults.
- [x] RED: raw payload/secret diagnostics, implied Live PASS, and invalid temporal
  ranges fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_models_operations.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=STATUS_ONLY; license=AUDITED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add provider operational audit models`.

### Task 14 — Migration 0008 schema creation

- [x] Paths: `tests/integration/test_provider_migrations.py`,
  `migrations/versions/0008_create_production_data_providers.py`.
- [x] Contract/types: migration file `0008_create_production_data_providers.py`
  uses the Alembic-version-column-safe revision `0008_production_providers`
  (the descriptive name exceeds Alembic's 32-character version column), down
  revision `0007_verifiable_reports`; create only the reviewed 20 tables.
- [x] Database: full FKs, uniques, CHECKs, indexes, append-only/terminal triggers,
  and complete reverse-order downgrade; no data, network, credential, or changes
  to Stage 2–8 tables.
- [x] RED: focused PostgreSQL migration test fails because revision/tables absent.
- [x] RED/GREEN command: `uv run pytest -W error tests/integration/test_provider_migrations.py`.
- [x] Boundaries: network=LOOPBACK_DB_ONLY; credentials=NOT_READ; license=SCHEMA_ONLY;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: create production provider migration`.

### Task 15 — Migration replay and prior-stage preservation

- [x] Paths: `tests/integration/test_provider_migrations.py`.
- [x] Contract/types: inspect a manually authored manifest for all Stage 2–8 and
  Stage 9 tables, constraints, indexes, and trigger names after upgrade/downgrade/
  re-upgrade.
- [x] Database: prove downgrade removes only Stage 9 and re-upgrade is clean.
- [x] RED: preservation/replay assertions fail on any drift.
- [x] RED/GREEN command: same focused migration command, foreground and single-process.
- [x] Boundaries: network=LOOPBACK_DB_ONLY; credentials=NOT_READ; license=SCHEMA_ONLY;
  live=NOT_ATTEMPTED.
- [x] Commit: `test: verify provider migration replay`.

### Task 16 — Definition and governance PostgreSQL repository

- [x] Paths: `tests/integration/test_provider_governance_repository_postgres.py`,
  `src/stock_research_agent/db/repositories/providers.py`,
  `src/stock_research_agent/db/repositories/__init__.py`.
- [x] Contract/types: `SqlAlchemyProviderDefinitionRepository` and
  `SqlAlchemyProviderGovernanceRepository` implement section 3 with bounded,
  stable ordering and no implicit Session creation.
- [x] Database: parameterized queries, transaction ownership by caller, immutable
  writes, duplicate conflict mapping.
- [x] RED: real PostgreSQL CRUD/idempotency/rollback tests fail before repository.
- [x] RED/GREEN command: `uv run pytest -W error tests/integration/test_provider_governance_repository_postgres.py`.
- [x] Boundaries: network=LOOPBACK_DB_ONLY; credentials=METADATA_ONLY; license=READ/WRITE;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: persist provider governance records`.

### Task 17 — Sync PostgreSQL repository

- [x] Paths: `tests/integration/test_provider_sync_repository_postgres.py`,
  `src/stock_research_agent/db/repositories/providers.py`.
- [x] Contract/types: `SqlAlchemyProviderSyncRepository` implements request,
  plan, run, transition, attempt, and checkpoint methods.
- [x] Database: row locking, atomic counters, stable attempt order, idempotent
  request/run lookup, rollback, and closed Session proof.
- [x] RED: lifecycle/concurrency tests fail before implementation.
- [x] RED/GREEN command: `uv run pytest -W error tests/integration/test_provider_sync_repository_postgres.py`.
- [x] Boundaries: network=LOOPBACK_DB_ONLY; credentials=REFERENCE_ID_ONLY;
  license=BOUND_VERSION; live=NOT_ATTEMPTED.
- [x] Commit: `feat: persist provider sync lifecycle`.

### Task 18 — Artifact PostgreSQL repository

- [x] Paths: `tests/integration/test_provider_artifact_repository_postgres.py`,
  `src/stock_research_agent/db/repositories/providers.py`.
- [x] Contract/types: `SqlAlchemyProviderArtifactRepository` implements artifact,
  manifest, quality issue, and dead-letter writes plus bounded lineage reads.
- [x] Database: checksum dedup, append-only, stable ordering, transaction rollback,
  and no blob deletion on row failure.
- [x] RED: real PostgreSQL lineage/idempotency tests fail before repository.
- [x] RED/GREEN command: `uv run pytest -W error tests/integration/test_provider_artifact_repository_postgres.py`.
- [x] Boundaries: network=LOOPBACK_DB_ONLY; credentials=ABSENT; license=BOUND_DECISION;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: persist provider artifacts and lineage`.

### Task 19 — Terminal Run state machine

- [x] Paths: `tests/unit/test_provider_sync_state_machine.py`,
  `src/stock_research_agent/domain/providers/sync.py`.
- [x] Contract/types: `ProviderRunStateMachine.transition(current, target) ->
  ProviderRunState`; terminal `COMPLETED`, `PARTIAL`, `BLOCKED`, `FAILED`,
  `CANCELLED` cannot transition or mutate budgets/plan/policies.
- [x] Database: transition map exactly matches migration trigger.
- [x] RED: invalid recovery, policy swap, budget reset, and repeated terminal writes fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_sync_state_machine.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NOT_READ; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: enforce provider run state machine`.

### Task 20 — Checkpoint compare-and-swap

- [x] Paths: `tests/unit/test_provider_checkpoints.py`,
  `tests/integration/test_provider_checkpoint_postgres.py`,
  `src/stock_research_agent/domain/providers/sync.py`,
  `src/stock_research_agent/db/repositories/providers.py`.
- [x] Contract/types: `CheckpointScope`, `CheckpointAdvance`; require exact
  Provider/capability/universe/security/version and expected revision.
- [x] Database: one winner under concurrent CAS, rollback leaves watermark unchanged.
- [x] RED: stale revision and two-writer PostgreSQL test fail.
- [x] RED/GREEN command: run both named test files in one foreground pytest process.
- [x] Boundaries: network=LOOPBACK_DB_ONLY; credentials=NOT_READ; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add transactional provider checkpoints`.

### Task 21 — Configuration validation gate

- [x] Paths: `tests/unit/test_provider_configuration_gate.py`,
  `src/stock_research_agent/domain/providers/configuration.py`.
- [x] Contract/types: `ProviderConfiguration`, `ConfigurationDecision`,
  `ProviderConfigurationGate.validate(definition, capability, policy, license,
  credential_reference) -> ConfigurationDecision`; no environment read.
- [x] Database: none.
- [x] RED: version mismatch, missing exact endpoint policy, invalid retention,
  unsupported credential resolver, and blocked production state fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_configuration_gate.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=METADATA_ONLY; license=REQUIRED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: validate provider configuration without secrets`.

### Task 22 — Explicit Live authorization gate

- [x] Paths: `tests/unit/test_provider_live_authorization.py`,
  `src/stock_research_agent/domain/providers/authorization.py`.
- [x] Contract/types: `LiveAuthorization`, `LiveAuthorizationDecision`,
  `LiveAuthorizationGate.evaluate(authorization, execution_scope, now)`;
  bind Provider, capability, hosts, exact paths, requests, bytes, expiry, actor,
  approval phrase checksum, and one validation run.
- [x] Database: maps to `provider_live_validation_runs`; default absent means BLOCKED.
- [x] RED: absent, generic approval, wrong Provider/capability, expired, replayed,
  widened, or over-budget authorization fails.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_live_authorization.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NOT_READ; license=PREREQUISITE;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: require finite provider live authorization`.

### Task 23 — Environment credential resolver

- [x] Paths: `tests/unit/test_provider_credential_resolver.py`,
  `src/stock_research_agent/providers/credentials.py`.
- [x] Contract/types: `EnvironmentCredentialResolver.resolve_for_execution(...)`;
  allow declared exact names only, return non-serializable/redacted
  `ResolvedCredentialContext`, and expose only executor-specific header/body binding.
- [x] Database: reads reference metadata only.
- [x] RED: default path proves `os.environ` access is never called; undeclared
  name, dump, repr, logging, exception, and persistence leakage fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_credential_resolver.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=TEST_SENTINELS_ONLY;
  license=MUST_PASS_FIRST; live=NOT_ATTEMPTED.
- [x] Commit: `feat: isolate provider credential resolution`.

### Task 24 — HTTP request-template contract

- [x] Paths: `tests/unit/test_provider_http_templates.py`,
  `src/stock_research_agent/domain/providers/http.py`.
- [x] Contract/types: `ProviderEndpointPolicy`, `ProviderHttpRequestTemplate`,
  `ProviderHttpResponse`, `ProviderExecutionContext`; callers supply endpoint ID
  and normalized parameters, never URL, host, path, filesystem location, SQL, raw
  header, Cookie, Authorization, or credential.
- [x] Database: none.
- [x] RED: arbitrary/ambiguous request shapes and unsafe headers fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_http_templates.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=BINDING_SLOT_ONLY; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: define safe provider http templates`.

### Task 25 — Endpoint expansion and URL canonicalization

- [x] Paths: `tests/unit/test_provider_endpoint_policy.py`,
  `src/stock_research_agent/providers/http_policy.py`.
- [x] Contract/types: `expand_endpoint(policy, template) -> CanonicalProviderRequest`;
  exact HTTPS scheme, lowercase IDNA host, fixed port, path-template segments,
  canonical query keys, and no fragment/userinfo.
- [x] Database: none.
- [x] RED: scheme downgrade, encoded traversal, duplicate key, userinfo, fragment,
  Unicode host confusion, port, wildcard host, and caller URL fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_endpoint_policy.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: canonicalize provider endpoints`.

### Task 26 — SSRF address policy

- [x] Paths: `tests/unit/test_provider_ssrf_policy.py`,
  `src/stock_research_agent/providers/http_policy.py`.
- [x] Contract/types: `ProviderAddressPolicy.validate(host, resolved_addresses)`;
  reject loopback, private, link-local, multicast, unspecified, reserved,
  documentation, IPv4-mapped, DNS rebinding, and mixed safe/unsafe sets.
- [x] Database: none.
- [x] RED: exhaustive IPv4/IPv6 and rebinding cases fail before validator.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_ssrf_policy.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `security: enforce provider ssrf address policy`.

### Task 27 — Redirect policy

- [x] Paths: `tests/unit/test_provider_redirect_policy.py`,
  `src/stock_research_agent/providers/http_policy.py`.
- [x] Contract/types: `ProviderRedirectPolicy.evaluate(origin, target, count)`;
  default reference policies allow zero redirects; any permitted future redirect
  re-runs scheme, host, port, path, DNS, and budget gates.
- [x] Database: attempt records store only safe redirect count/code.
- [x] RED: cross-host, downgrade, relative traversal, over-limit, and credential
  forwarding fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_redirect_policy.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NEVER_FORWARDED; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `security: constrain provider redirects`.

### Task 28 — Streaming response bounds

- [x] Paths: `tests/unit/test_provider_response_bounds.py`,
  `src/stock_research_agent/providers/http_response.py`.
- [x] Contract/types: `BoundedResponseReader.read(stream, limits) ->
  BoundedProviderPayload`; enforce declared and actual byte limit, finite chunks,
  decompression ratio, total time, and immediate close.
- [x] Database: safe size/status only.
- [x] RED: missing/false length, chunk overflow, compression bomb, endless stream,
  and close-on-error cases fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_response_bounds.py`.
- [x] Boundaries: network=FAKE_TRANSPORT_ONLY; credentials=ABSENT; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `security: bound provider response streaming`.

### Task 29 — MIME, charset, and payload validation

- [x] Paths: `tests/unit/test_provider_content_validation.py`,
  `src/stock_research_agent/providers/http_response.py`.
- [x] Contract/types: `ProviderContentValidator.validate(headers, payload,
  accepted_types) -> ValidatedProviderPayload`; exact allowed MIME, safe charset,
  JSON structural bounds, no HTML masquerading, and no executable content.
- [x] Database: normalized MIME and checksum only.
- [x] RED: MIME sniff mismatch, invalid charset, NUL/control payload, duplicate
  JSON keys where prohibited, deep JSON, and active content fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_content_validation.py`.
- [x] Boundaries: network=FAKE_TRANSPORT_ONLY; credentials=ABSENT; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `security: validate provider response content`.

### Task 30 — Header and logging redaction

- [x] Paths: `tests/unit/test_provider_http_redaction.py`,
  `src/stock_research_agent/providers/http_redaction.py`,
  `src/stock_research_agent/logging.py`.
- [x] Contract/types: `safe_request_summary(request)`,
  `safe_response_summary(response)`, `redact_provider_headers(headers)`;
  fixed allowlist excludes Authorization, Cookie, Set-Cookie, query secrets,
  local paths, and raw bodies.
- [x] Database: audit/attempt safe-summary shape only.
- [x] RED: sentinel secret and log-injection tests fail before redaction.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_http_redaction.py tests/unit/test_logging.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=REDACTED; license=SAFE_SUMMARY;
  live=NOT_ATTEMPTED.
- [x] Commit: `security: redact provider http telemetry`.

### Task 31 — Cross-process rate limiter

- [x] Paths: `tests/unit/test_provider_governed_rate_limit.py`,
  `tests/integration/test_provider_rate_limit_postgres.py`,
  `src/stock_research_agent/providers/rate_limit.py`.
- [x] Contract/types: `ProviderRateLimiter.reserve(scope, now, units) ->
  RateLimitDecision`; scope Provider/capability/non-secret credential reference,
  project SEC rate strictly below official maximum, monotonic finite budget.
- [x] Database: PostgreSQL advisory/row lock coordinates processes; rollback safe.
- [x] RED: concurrent reservations exceed limit before implementation.
- [x] RED/GREEN command: run both named files in one foreground pytest process.
- [x] Boundaries: network=LOOPBACK_DB_ONLY; credentials=REFERENCE_ID_ONLY;
  license=MUST_PASS_FIRST; live=NOT_ATTEMPTED.
- [x] Commit: `feat: coordinate provider rate limits`.

### Task 32 — Deterministic retry classifier

- [x] Paths: `tests/unit/test_provider_retry_policy.py`,
  `src/stock_research_agent/providers/retry.py`.
- [x] Contract/types: `ProviderRetryPolicy.classify(outcome, attempt, budget) ->
  RetryDecision`; retry only idempotent read on approved transient status/error,
  bounded attempts, deterministic schedule metadata, no sleep in domain tests.
- [x] Database: attempt accounting consumes budget before retry.
- [x] RED: auth/license/schema/404/future/invalid content and budget errors retry incorrectly.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_retry_policy.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NOT_RERESOLVED_UNLESS_APPROVED;
  license=NO_RETRY; live=NOT_ATTEMPTED.
- [x] Commit: `feat: classify bounded provider retries`.

### Task 33 — Persisted circuit breaker

- [x] Paths: `tests/unit/test_provider_circuit_breaker.py`,
  `tests/integration/test_provider_circuit_breaker_postgres.py`,
  `src/stock_research_agent/providers/circuit_breaker.py`,
  `src/stock_research_agent/db/repositories/providers.py`.
- [x] Contract/types: `ProviderCircuitBreakerService.before_call(scope, now)` and
  `record_outcome(scope, outcome, now)`; deterministic CLOSED/OPEN/HALF_OPEN.
- [x] Database: atomic cross-process state, one half-open probe, automatic
  transaction cleanup on exception.
- [x] RED: concurrent probe and incorrect failure classification tests fail.
- [x] RED/GREEN command: run both named files in one foreground pytest process.
- [x] Boundaries: network=LOOPBACK_DB_ONLY; credentials=NOT_READ; license=MUST_PASS_FIRST;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add persisted provider circuit breaker`.

### Task 34 — License-aware operational cache

- [x] Paths: `tests/unit/test_provider_governed_cache.py`,
  `tests/integration/test_provider_cache_postgres.py`,
  `src/stock_research_agent/providers/cache.py`.
- [x] Contract/types: `ProviderCacheKey`, `ProviderCacheDecision`,
  `ProviderCacheService.get/put`; key binds Provider/adapter/capability/policy/
  license/request identity; cache never becomes Raw Artifact or evidence.
- [x] Database: expiry, checksum, license deletion rule, transactional pointer update.
- [x] RED: cross-version/license/scope reuse and prohibited cache creation fail.
- [x] RED/GREEN command: run both named files in one foreground pytest process.
- [x] Boundaries: network=LOOPBACK_DB_ONLY; credentials=NON_SECRET_SCOPE_ONLY;
  license=REQUIRED; live=NOT_ATTEMPTED.
- [x] Commit: `feat: govern provider response cache`.

### Task 35 — Controlled HTTP executor gate order

- [x] Paths: `tests/unit/test_controlled_provider_executor.py`,
  `src/stock_research_agent/providers/http_executor.py`.
- [x] Contract/types: `DefaultControlledProviderExecutor.execute(...)` implements
  the exact eight-stage user gate order, then circuit/endpoint/rate/cache/transport;
  injectable spies prove later gates are untouched after any block.
- [x] Database: writes safe attempt/audit metadata through injected repositories.
- [x] RED: permutation tests expose credential/network access before authorization.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_controlled_provider_executor.py`.
- [x] Boundaries: network=FAKE_TRANSPORT_ONLY; credentials=TEST_SENTINELS_AFTER_GATE;
  license=FIRST_CLASS; live=NOT_ATTEMPTED.
- [x] Commit: `security: enforce controlled provider execution gates`.

### Task 36 — Default offline transport kill switch

- [x] Paths: `tests/unit/test_provider_executor_offline.py`,
  `src/stock_research_agent/providers/http_executor.py`,
  `src/stock_research_agent/config.py`.
- [x] Contract/types: `ProviderNetworkMode.OFFLINE` default and
  `OfflineProviderTransport.send(...)` always returns structured BLOCKED without
  DNS, socket, credential resolver, or HTTP-client construction.
- [x] Database: optional safe audit event only when called through write service.
- [x] RED: socket/DNS/env access spies are triggered before implementation.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_executor_offline.py tests/unit/test_default_network_policy.py`.
- [x] Boundaries: network=HARD_BLOCKED; credentials=NOT_READ; license=UNCHANGED;
  live=NOT_ATTEMPTED.
- [x] Commit: `security: hard-disable provider network by default`.

### Task 37 — Immutable Sync Request

- [x] Paths: `tests/unit/test_provider_sync_requests.py`,
  `src/stock_research_agent/domain/providers/sync.py`.
- [x] Contract/types: `ProviderSyncRequestWrite/Record`; require exact Provider,
  capability, versions, security/universe, bounded start/end/as-of, policy,
  license, credential reference or NONE, offline mode, finite budget, idempotency.
- [x] Database: maps to request uniqueness and immutable trigger.
- [x] RED: “latest”, open-ended history, future range, arbitrary URL/path/SQL,
  version omission, and budget omission fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_sync_requests.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=REFERENCE_ONLY; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add immutable provider sync requests`.

### Task 38 — Finite deterministic Sync Plan

- [x] Paths: `tests/unit/test_provider_sync_plans.py`,
  `src/stock_research_agent/domain/providers/sync.py`.
- [x] Contract/types: `ProviderSyncSlice`, `ProviderSyncPlanDraft/Write/Record`,
  `build_plan_checksum`; finite ordered slices, no cycles/self-dependency/runtime
  expansion, stable checksum from request/adapter/checkpoint.
- [x] Database: plan checksum and request unique identity.
- [x] RED: nondeterminism, duplicate slice, unbounded slice, cycle, and context
  override tests fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_sync_plans.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=REFERENCE_ONLY; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: build deterministic provider sync plans`.

### Task 39 — Sync orchestration service

- [x] Paths: `tests/unit/test_provider_sync_service.py`,
  `src/stock_research_agent/providers/control_plane.py`.
- [x] Contract/types: `ProviderSyncService.plan(command) -> ProviderSyncPlanRecord`
  and `run(command) -> ProviderSyncResult`; inject all gates, adapter, executor,
  repositories, bridge, clock, and storage.
- [x] Database: caller-owned transaction boundaries and idempotent run reuse only
  for identical request/plan/checkpoint/catalog versions.
- [x] RED: run creation before gates and version-mismatched reuse fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_sync_service.py`.
- [x] Boundaries: network=FAKE/OFFLINE_ONLY; credentials=NOT_READ_IN_DEFAULT;
  license=GATED; live=NOT_ATTEMPTED.
- [x] Commit: `feat: orchestrate governed provider sync`.

### Task 40 — Pause, resume, and cancel

- [x] Paths: `tests/unit/test_provider_sync_control.py`,
  `src/stock_research_agent/providers/control_plane.py`,
  `src/stock_research_agent/domain/providers/sync.py`.
- [x] Contract/types: `pause(run_id)`, `resume(run_id)`, `cancel(run_id)`; resume
  retains consumed budget/checkpoint/plan and terminal Runs never resume.
- [x] Database: transition/event append and row-lock semantics.
- [x] RED: budget reset, policy swap, new slice, terminal resume, and cross-run
  control fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_sync_control.py`.
- [x] Boundaries: network=FORBIDDEN_DURING_CONTROL; credentials=NOT_READ;
  license=BOUND; live=NOT_ATTEMPTED.
- [x] Commit: `feat: control provider sync lifecycle`.

### Task 41 — Budget reservation and exhaustion

- [x] Paths: `tests/unit/test_provider_sync_budgets.py`,
  `tests/integration/test_provider_sync_budget_postgres.py`,
  `src/stock_research_agent/providers/control_plane.py`.
- [x] Contract/types: `ProviderBudgetLedger.reserve(run_id, request_bytes)`;
  requests, bytes, attempts, and duration are hard limits, consumed atomically,
  never increased or reset.
- [x] Database: concurrent reservation permits at most remaining budget.
- [x] RED: oversubscription and post-resume reset fail.
- [x] RED/GREEN command: run both named files in one foreground pytest process.
- [x] Boundaries: network=LOOPBACK_DB_ONLY; credentials=NOT_READ; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: enforce provider execution budgets`.

### Task 42 — Raw Artifact atomic storage

- [x] Paths: `tests/unit/test_provider_raw_artifacts.py`,
  `src/stock_research_agent/domain/providers/artifacts.py`,
  `src/stock_research_agent/infrastructure/provider_artifact_storage.py`.
- [x] Contract/types: `ProviderRawArtifactDraft`,
  `AtomicProviderArtifactStorage.write(draft, content) -> StoredProviderArtifact`;
  safe generated relative key, temp file in same root, fsync/replace, SHA-256,
  immutable existing-byte verification.
- [x] Database: artifact row is committed only after durable blob; DB failure
  reconciles safe orphan without overwriting.
- [x] RED: traversal, symlink/reparse, partial write, checksum mismatch, collision,
  newline mutation, and overwrite tests fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_raw_artifacts.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=STORE_RAW_REQUIRED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: store immutable provider raw artifacts`.

### Task 43 — Blob/database reconciliation

- [x] Paths: `tests/unit/test_provider_artifact_reconciliation.py`,
  `src/stock_research_agent/infrastructure/provider_artifact_storage.py`.
- [x] Contract/types: `ProviderArtifactReconciler.inspect(limit) ->
  ArtifactReconciliationReport` and explicit `repair(item_id)`; bounded, root-safe,
  checksum-first, no automatic delete.
- [x] Database: identifies orphan/missing/mismatch without mutating historical rows.
- [x] RED: unbounded scan, absolute-path output, silent delete, and wrong-root repair fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_artifact_reconciliation.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=DELETION_POLICY_REQUIRED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: reconcile provider artifact storage`.

### Task 44 — Immutable Ingestion Manifest

- [x] Paths: `tests/unit/test_provider_ingestion_manifests.py`,
  `src/stock_research_agent/domain/providers/artifacts.py`.
- [x] Contract/types: `ProviderIngestionManifestWrite/Record`,
  `build_ingestion_manifest(artifact, batch, context)`; bind definition,
  capability, run, attempt, artifact, parser/adapter schema, record identities,
  source/retrieved/published times, synthetic status, and checksum.
- [x] Database: append-only manifest unique by artifact/parser/version/checksum.
- [x] RED: missing/unknown published time without warning, future data, cross-run,
  cross-security, mutated raw checksum, and synthetic confusion fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_ingestion_manifests.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=BOUND_DECISION;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: seal provider ingestion manifests`.

### Task 45 — Provider batch and record contracts

- [x] Paths: `tests/unit/test_provider_batches.py`,
  `src/stock_research_agent/domain/providers/artifacts.py`.
- [x] Contract/types: `ProviderRecordIdentity`, `ProviderRecord`,
  `ProviderBatch`; Decimal strings, original payload references, explicit
  missing/partial/warning states, stable source identity, bounded record count.
- [x] Database: records remain typed manifest projection or bridge input, not a
  catch-all business-fact table.
- [x] RED: float, zero-for-missing, raw overwrite, unstable order, and oversized
  batch tests fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_batches.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: define provider batch contracts`.

### Task 46 — Data-quality validator

- [x] Paths: `tests/unit/test_provider_data_quality.py`,
  `src/stock_research_agent/domain/providers/quality.py`.
- [x] Contract/types: `ProviderQualityRule`, `ProviderQualityResult`,
  `ProviderDataQualityValidator.validate(batch, context)`; deterministic schema,
  identity, temporal, duplicate, currency/unit, missing, and synthetic checks.
- [x] Database: append one issue per failed rule with bounded safe evidence.
- [x] RED: future publication, duplicate identity conflict, malformed Decimal,
  source checksum mismatch, and real/synthetic mixing fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_data_quality.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: validate provider data quality`.

### Task 47 — Dead-letter handling

- [x] Paths: `tests/unit/test_provider_dead_letters.py`,
  `src/stock_research_agent/domain/providers/quality.py`.
- [x] Contract/types: `ProviderDeadLetterWrite/Record`,
  `DeadLetterService.reject(record, failure, context)`; raw bytes stay only in
  artifact, diagnostic is bounded/redacted, replay requires explicit CLI repair.
- [x] Database: append-only, stable source identity, status transition only through
  explicit repair audit.
- [x] RED: raw body, secret, local path, SQL, silent drop, and implicit replay fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_dead_letters.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=REDACTED; license=RETENTION_BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: preserve provider dead letters safely`.

### Task 48 — Freshness policies

- [x] Paths: `tests/unit/test_provider_freshness.py`,
  `src/stock_research_agent/domain/providers/freshness.py`.
- [x] Contract/types: `ProviderFreshnessPolicyWrite/Record`,
  `ProviderFreshnessEvaluator.evaluate(policy, latest, as_of)`;
  market/capability-aware expected delay, UNKNOWN publication warning, no invented
  calendars or publication time.
- [x] Database: versioned policy and bounded lookup index.
- [x] RED: retrieved_at substitution, future data, absent calendar guessing, and
  cross-market policy reuse fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_freshness.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: evaluate provider freshness deterministically`.

### Task 49 — Offline health and readiness

- [x] Paths: `tests/unit/test_provider_health.py`,
  `src/stock_research_agent/domain/providers/health.py`.
- [x] Contract/types: `ProviderHealthSnapshotWrite/Record`,
  `ProviderReadinessService.evaluate(context) -> ProviderReadinessResult`;
  definition, capability, license, credential metadata, configuration, circuit,
  schema, mapping, retention, and last validation; no probe.
- [x] Database: append-only health snapshot; stable limiting reasons.
- [x] RED: offline adapter PASS incorrectly produces production ready, missing
  credentials are read, or health implicitly calls network.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_health.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=STATUS_ONLY; license=GATED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: report provider readiness offline`.

### Task 50 — SEC contract schemas

- [x] Paths: `tests/unit/test_sec_edgar_contracts.py`,
  `src/stock_research_agent/providers/sec_edgar/__init__.py`,
  `src/stock_research_agent/providers/sec_edgar/schemas.py`.
- [x] Contract/types: strict source-attributed models for submissions metadata,
  Company Facts envelope, filing index, document artifact descriptor, CIK and
  accession normalization; unknown fields retained only in raw artifact.
- [x] Database: none beyond manifest projections.
- [x] RED: invalid CIK/accession/form/time/MIME/source identity and metadata-as-body fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_sec_edgar_contracts.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=CONTACT_REFERENCE_ONLY;
  license=SEC_PUBLIC_POLICY; live=NOT_ATTEMPTED.
- [x] Commit: `feat: define sec edgar offline contracts`.

### Task 51 — SEC exact endpoint policies

- [x] Paths: `tests/unit/test_sec_edgar_endpoints.py`,
  `src/stock_research_agent/providers/sec_edgar/endpoints.py`.
- [x] Contract/types: immutable endpoint IDs for exact official HTTPS templates on
  `data.sec.gov` and `www.sec.gov`; validated CIK, accession-without-dashes, and
  allowlisted document path segments.
- [x] Database: policy version referenced by definition/policy.
- [x] RED: arbitrary Archives path, encoded traversal, alternate host, redirect,
  query widening, and user URL fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_sec_edgar_endpoints.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=CONTACT_BINDING_SLOT;
  license=SEC_PUBLIC_POLICY; live=NOT_ATTEMPTED.
- [x] Commit: `security: constrain sec edgar endpoints`.

### Task 52 — SEC deterministic planner

- [x] Paths: `tests/unit/test_sec_edgar_planner.py`,
  `src/stock_research_agent/providers/sec_edgar/adapter.py`.
- [x] Contract/types: `SecEdgarAdapter.plan(...)`; finite slices for approved
  capability, CIK, form filters, explicit dates/as-of, checkpoint, request/byte
  budget; stable order/checksum.
- [x] Database: no direct Session; returns plan draft only.
- [x] RED: open-ended history, “latest”, future range, unsupported form/capability,
  wrong security, and plan expansion fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_sec_edgar_planner.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NOT_READ; license=SEC_PUBLIC_POLICY;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: plan bounded sec edgar sync`.

### Task 53 — SEC offline parser

- [x] Paths: `tests/unit/test_sec_edgar_parser.py`,
  `src/stock_research_agent/providers/sec_edgar/adapter.py`.
- [x] Contract/types: `SecEdgarAdapter.parse_response(...)`; distinguish filing
  metadata, facts, primary document, and exhibits; preserve raw checksum, source
  timestamps, amendments, and UNKNOWN published warning.
- [x] Database: returns ProviderBatch only.
- [x] RED: SEC metadata becoming company正文, retrieved time becoming published,
  future evidence, malformed JSON/HTML, and accession mismatch fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_sec_edgar_parser.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=SEC_PUBLIC_POLICY;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: parse sec edgar offline responses`.

### Task 54 — SEC fixtures and manifests

- [x] Paths: `tests/fixtures/providers/sec/*.json`,
  `tests/fixtures/providers/sec/*.manifest.json`,
  `tests/unit/test_sec_edgar_fixtures.py`.
- [x] Contract/types: minimal source-attributed safe crops already present in
  verified Stage 1 material or synthetic protocol fixtures; manifest records
  provider, official endpoint type, security, captured/published time, MIME,
  crop rule, SHA-256, rights, `OFFLINE`, `NOT_LIVE`.
- [x] Database: none.
- [x] RED: independently calculated byte checksum and LF contract fail before files.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_sec_edgar_fixtures.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=MANIFESTED;
  live=NOT_ATTEMPTED.
- [x] Commit: `test: add governed sec offline fixtures`.

### Task 55 — Tushare contract schemas

- [x] Paths: `tests/unit/test_tushare_contracts.py`,
  `src/stock_research_agent/providers/tushare/__init__.py`,
  `src/stock_research_agent/providers/tushare/schemas.py`.
- [x] Contract/types: strict offline response/request models for approved endpoint
  shapes, `ts_code`, fields/items, pagination identity, announcement/period/update
  metadata; Provider metrics never become Stage 5 formulas.
- [x] Database: none beyond manifest projections.
- [x] RED: float, missing identity, duplicate field, unverified endpoint, metric
  promotion, and missing publication semantics fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_tushare_contracts.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NOT_READ; license=RESTRICTED_REVIEW_REQUIRED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: define tushare offline contracts`.

### Task 56 — Tushare blocked endpoint policy

- [x] Paths: `tests/unit/test_tushare_endpoint_policy.py`,
  `src/stock_research_agent/providers/tushare/endpoints.py`,
  `src/stock_research_agent/providers/tushare/adapter.py`.
- [x] Contract/types: `TushareAdapter` descriptor reports
  `IMPLEMENTED_OFFLINE`, `RESTRICTED_REVIEW_REQUIRED`, `NOT_READ`,
  `NOT_ATTEMPTED`, `BLOCKED`; no production endpoint policy exists until official
  HTTPS REST and license/entitlement approval.
- [x] Database: blocked definition/capability status seeds are explicit internal
  governance records, not business data.
- [x] RED: offline parser success incorrectly authorizes URL/Token/network.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_tushare_endpoint_policy.py`.
- [x] Boundaries: network=HARD_BLOCKED; credentials=NOT_READ; license=BLOCKED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: keep tushare production access blocked`.

### Task 57 — Tushare deterministic planner

- [x] Paths: `tests/unit/test_tushare_planner.py`,
  `src/stock_research_agent/providers/tushare/adapter.py`.
- [x] Contract/types: `TushareAdapter.plan(...)` produces finite offline slices for
  explicit endpoint capability/security/date/period and checkpoint; plan is useful
  for contract validation but cannot execute Live.
- [x] Database: no direct Session.
- [x] RED: prefix endpoint, unbounded history, arbitrary fields, unsupported Token
  entitlement, future range, and plan nondeterminism fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_tushare_planner.py`.
- [x] Boundaries: network=HARD_BLOCKED; credentials=NOT_READ; license=BLOCKED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add deterministic offline tushare sync planning`.

### Task 58 — Tushare offline parser

- [x] Paths: `tests/unit/test_tushare_parser.py`,
  `src/stock_research_agent/providers/tushare/adapter.py`.
- [x] Contract/types: `TushareAdapter.parse_response(...)`; map only verified
  fields, preserve provider record identity/raw reference, Decimal strings,
  missing publication warning, and provider-metric provenance.
- [x] Database: returns ProviderBatch only.
- [x] RED: fabricated zeros, inferred dates, cumulative-statement normalization,
  TTM, formula substitution, and raw overwrite fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_tushare_parser.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=BLOCKED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: parse tushare offline responses`.

### Task 59 — Tushare synthetic contract fixtures

- [x] Paths: `tests/fixtures/providers/tushare/*.json`,
  `tests/fixtures/providers/tushare/*.manifest.json`,
  `tests/unit/test_tushare_fixtures.py`.
- [x] Contract/types: protocol-only data is labeled `SYNTHETIC_TEST_ONLY`,
  `NOT_COMPANY_EVIDENCE`, `OFFLINE`, `NOT_LIVE`; any real safe crop must have the
  full source/rights/crop/checksum manifest and cannot invent financial values.
- [x] Database: none.
- [x] RED: checksum, LF, label, forbidden real-company evidence, and manifest
  completeness tests fail before fixtures.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_tushare_fixtures.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=TEST_ONLY;
  live=NOT_ATTEMPTED.
- [x] Commit: `test: add isolated tushare contract fixtures`.

### Task 60 — Blocked Provider descriptors

- [x] Paths: `tests/unit/test_blocked_provider_descriptors.py`,
  `src/stock_research_agent/providers/blocked.py`.
- [x] Contract/types: descriptors for SSE/SZSE/CNINFO disclosure automation,
  licensed U.S. EOD, and production embedding; each returns structured missing
  license/vendor/endpoint/credential/model/approval reasons.
- [x] Database: definitions may be queried but no capability is production-enabled.
- [x] RED: name/prefix auto-enable, generic reason, offline PASS, or Live PASS fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_blocked_provider_descriptors.py`.
- [x] Boundaries: network=HARD_BLOCKED; credentials=NOT_READ; license=BLOCKED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: register blocked production provider contracts`.

### Task 61 — Provider Registry versioning

- [x] Paths: `tests/unit/test_production_provider_registry.py`,
  `src/stock_research_agent/providers/production_registry.py`.
- [x] Contract/types: `ProductionProviderRegistry.register/get/list`,
  `ProviderAdapterDescriptor`, stable catalog checksum; exact code/version,
  duplicate rejection, deterministic order.
- [x] Database: registry descriptors reconcile with persisted definitions.
- [x] RED: prefix/wildcard selection, duplicate version, unstable checksum, and
  blocked-to-enabled mutation fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_production_provider_registry.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NOT_READ; license=DESCRIPTOR_STATUS;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: version production provider registry`.

### Task 62 — Security-master bridge

- [x] Paths: `tests/unit/test_provider_security_bridge.py`,
  `src/stock_research_agent/providers/bridges/security_master.py`.
- [x] Contract/types: `SecurityMasterProviderBridge.stage(...)`; only verified
  security identifiers/aliases with exact Security mapping and manifest lineage;
  no issuer guessing or destructive update.
- [x] Database: writes existing Stage 3 structures in caller transaction; append
  identifiers/aliases, never overwrite historical identity.
- [x] RED: unknown security, cross-market ticker, synthetic-real mixing, conflict,
  and future data fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_security_bridge.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=DERIVED_USE_REQUIRED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: bridge verified provider security master data`.

### Task 63 — Market-data bridge

- [x] Paths: `tests/unit/test_provider_market_data_bridge.py`,
  `src/stock_research_agent/providers/bridges/market_data.py`.
- [x] Contract/types: `MarketDataProviderBridge.stage(...)`; preserve Decimal,
  currency, source time, published/retrieved distinction, adjustments, provider
  identity, manifest and raw lineage.
- [x] Database: writes existing Stage 4 raw/provider structures only; no Snapshot.
- [x] RED: float, missing-as-zero, future data, currency mixing, unlicensed cache,
  and implicit Snapshot fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_market_data_bridge.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=DERIVED_USE_REQUIRED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: bridge verified provider market data`.

### Task 64 — Filing and financial-fact bridges

- [x] Paths: `tests/unit/test_provider_evidence_bridges.py`,
  `src/stock_research_agent/providers/bridges/documents.py`,
  `src/stock_research_agent/providers/bridges/financials.py`.
- [x] Contract/types: `DocumentProviderBridge` creates only raw document-version
  inputs; `FinancialFactProviderBridge` creates only provider facts/mappings with
  explicit concept/unit/period/source lineage.
- [x] Database: existing Stage 5/6 inputs only; no parsing/indexing, normalization,
  cumulative split, TTM, metric calculation, Retrieval Run, Snapshot, Agent, Report.
- [x] RED: SEC metadata-as-body, Tushare indicator-as-formula, raw overwrite,
  future data, and implicit downstream processing fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_evidence_bridges.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=DERIVED_USE_REQUIRED;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: bridge provider filing and fact inputs`.

### Task 65 — Research as-of and revision enforcement

- [x] Paths: `tests/unit/test_provider_as_of_revisions.py`,
  `src/stock_research_agent/domain/providers/temporal.py`.
- [x] Contract/types: `ProviderTemporalValidator.validate(record, research_as_of)`;
  source_published_at controls eligibility, UNKNOWN warns/blocks strict historical
  use, retrieved_at never substitutes, revisions append rather than mutate.
- [x] Database: revision/source identities unique; old artifact/manifest remains.
- [x] RED: future inclusion, UNKNOWN strict use, overwrite, “latest wins”, and
  restatement erasure fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_as_of_revisions.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=ABSENT; license=BOUND;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: enforce provider as-of revisions`.

### Task 66 — Read-only Provider query service

- [x] Paths: `tests/unit/test_provider_queries.py`,
  `src/stock_research_agent/domain/providers/queries.py`,
  `src/stock_research_agent/db/repositories/providers.py`.
- [x] Contract/types: `ProviderQueryService` methods for definitions,
  capabilities, policy/license, health, circuit, Runs, attempts, artifacts,
  checkpoints, quality, dead letters, and readiness with `PageRequest(max<=100)`.
- [x] Database: parameterized stable bounded queries; safe projections exclude
  local blob path, raw restricted payload, headers, secrets, and SQL details.
- [x] RED: unbounded/unsafe sort, hidden write, implicit probe/sync, and leakage fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_queries.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=STATUS_ONLY; license=SAFE_SUMMARY;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: query provider governance safely`.

### Task 67 — Read-only Provider Tools and catalog

- [x] Paths: `tests/contract/test_provider_tools.py`,
  `src/stock_research_agent/tools/providers.py`,
  `src/stock_research_agent/tools/schemas_providers.py`,
  `src/stock_research_agent/tools/registry.py`,
  `docs/tool-catalog-stage-9-final.json`.
- [x] Contract/types: approved query Tools call only `ProviderQueryService`;
  `permission=READ_ONLY`, `writes=false`, `requires_network=false`, stable schema
  versions and new catalog checksum; no existing Research Policy auto-allowlist.
- [x] Database: reads only.
- [x] RED: registry lacks tools/catalog checksum and mutation/network-spy tests fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/contract/test_provider_tools.py tests/unit/test_tool_registry.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=STATUS_ONLY; license=SAFE_SUMMARY;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add read-only provider tools`.

### Task 68 — GET-only Provider API

- [x] Paths: `tests/contract/test_provider_api_contract.py`,
  `src/stock_research_agent/api/routes/providers.py`,
  `src/stock_research_agent/api/router.py`,
  `src/stock_research_agent/api/dependencies.py`.
- [x] Contract/types: eleven approved GET routes, existing prefix/error/request-ID,
  stable safe schemas, bounded pagination; no POST/PUT/PATCH/DELETE.
- [x] Database: query repository only; 404/422 safe, blocked status remains HTTP 200
  business state where applicable.
- [x] RED: OpenAPI, method, leakage, sync/probe/network, arbitrary sort, and invalid
  UUID tests fail before routes.
- [x] RED/GREEN command: `uv run pytest -W error tests/contract/test_provider_api_contract.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=STATUS_ONLY; license=SAFE_SUMMARY;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: expose read-only provider api`.

### Task 69 — Provider CLI read commands

- [x] Paths: `tests/unit/test_provider_cli_read.py`,
  `src/stock_research_agent/cli_providers.py`,
  `src/stock_research_agent/cli.py`.
- [x] Contract/types: `provider list/show/capabilities/policy/license/health/
  circuit-status/sync-show/checkpoints/raw-artifacts/quality-issues/dead-letters/
  readiness`; human and JSON safe outputs.
- [x] Database: query service only.
- [x] RED: help, exits, pagination, output schema, storage/header/secret leakage,
  and implicit network tests fail.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_provider_cli_read.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=STATUS_ONLY; license=SAFE_SUMMARY;
  live=NOT_ATTEMPTED.
- [x] Commit: `feat: add provider query cli`.

### Task 70 — Provider CLI control commands

- [x] Paths: `tests/unit/test_provider_cli_control.py`,
  `tests/integration/test_provider_cli_postgres.py`,
  `src/stock_research_agent/cli_providers.py`.
- [x] Contract/types: explicit `credential-check`, `sync-plan`, `sync-run`,
  `sync-pause`, `sync-resume`, `sync-cancel`, `repair`, `live-check`; require exact
  versions/scope/as-of/budgets/confirmation and reject URL/path/SQL/secret/latest.
- [x] Database: caller-owned transactions and audit events; offline sync uses
  fixtures only, `live-check` returns BLOCKED without approved authorization.
- [x] RED: write command safety and PostgreSQL audit tests fail.
- [x] RED/GREEN command: run both named files in one foreground pytest process.
- [x] Boundaries: network=HARD_BLOCKED; credentials=NOT_READ_DEFAULT;
  license=GATED; live=NOT_ATTEMPTED.
- [x] Commit: `feat: add explicit provider control cli`.

### Task 71 — Default-test and Live-suite isolation

- [x] Paths: `tests/unit/test_stage9_offline_isolation.py`,
  `tests/conftest.py`, `pyproject.toml`, `tests_live/providers/README.md`.
- [x] Contract/types: default collection excludes `tests_live`, blocks non-loopback
  DNS/socket, deletes Provider credential env names before each test, and asserts
  no production transport/model auto-enable; Live README states exact separate
  approval and finite disclosure workflow.
- [x] Database: loopback PostgreSQL remains permitted.
- [x] RED: env/socket/collection sentinels prove current gaps.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_stage9_offline_isolation.py`.
- [x] Boundaries: network=HARD_BLOCKED; credentials=REMOVED; license=UNCHANGED;
  live=NOT_ATTEMPTED.
- [x] Commit: `test: isolate provider live validation`.

### Task 72 — Provider documentation

- [x] Paths: `README.md`, `docs/data-providers.md`, `docs/data-ingestion.md`,
  `docs/raw-data-model.md`, `docs/database.md`, `docs/testing.md`,
  `docs/api.md`, `docs/tool-contracts.md`, `docs/compliance-boundaries.md`,
  `docs/security-boundaries.md`, `tests/unit/test_stage9_documentation.py`.
- [x] Contract/types: document gate order, table purposes, SEC/Tushare/blocked
  states, offline labels, credential boundary, HTTP security, artifact rights,
  checkpoint/as-of/revisions, API/Tool/CLI, Live approval, rollback, and Stage 10.
- [x] Database: document migration/replay and RESTRICT/immutability.
- [x] RED: exact command/status/boundary assertions fail before updates.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_stage9_documentation.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NEVER_PRINTED; license=EXPLICIT;
  live=NOT_ATTEMPTED.
- [x] Commit: `docs: document production provider governance`.

### Task 73 — Real-company offline acceptance

- [x] Paths: `tests/integration/test_stage9_company_acceptance.py`,
  `docs/sample-data-validation/601138.SH.md`,
  `docs/sample-data-validation/MU.md`.
- [x] Contract/types: Micron SEC adapter/contracts/metadata are offline-valid but
  company正文/financial completion remains BLOCKED; Industrial FII Tushare and
  disclosure Live remain BLOCKED; no synthetic fixture fills either company.
- [x] Database: real PostgreSQL readiness and query results; no Snapshot/Agent/Report.
- [x] RED: any COMPLETE/Live/PASS claim, synthetic mixing, or fabricated evidence fails.
- [x] RED/GREEN command: `uv run pytest -W error tests/integration/test_stage9_company_acceptance.py`.
- [x] Boundaries: network=LOOPBACK_DB_ONLY; credentials=NOT_READ; license=BLOCKED_OR_CONDITIONAL;
  live=NOT_ATTEMPTED.
- [x] Commit: `test: verify stage 9 real-company boundaries`.

### Task 74 — Reflection round one

- [x] Paths: `docs/reflection/stage-9-round-1.md`,
  `tests/unit/test_stage9_reflection_documents.py`.
- [x] Contract/types: findings have ID, role, severity, description, evidence,
  files, fix, blocker, status; roles cover data platform, Provider contracts,
  licensing/compliance, HTTP/security, database/concurrency, operations, API/Tool/
  CLI, fixtures/testing, and historical immutability.
- [x] Database: inspect models versus migration and real PostgreSQL evidence.
- [x] RED: reflection contract fails before document; GREEN records every finding,
  including zero-count categories with evidence.
- [x] RED/GREEN command: `uv run pytest -W error tests/unit/test_stage9_reflection_documents.py`.
- [x] Boundaries: network=FORBIDDEN; credentials=NOT_READ; license=REVIEWED;
  live=NOT_ATTEMPTED.
- [x] Commit: `docs: complete stage 9 reflection round one`.

### Task 75 — Resolve all critical and high findings

- [x] Paths: exact source/test/docs named by round-one findings plus
  `docs/reflection/stage-9-round-1.md`.
- [x] Contract/types: each CRITICAL/HIGH receives a focused regression test that
  fails before its minimum fix and passes after; finding status records test evidence.
- [x] Database: any schema correction uses only a new change inside unmerged
  migration `0008`; never edit Stage 2–8 migrations/tables.
- [x] RED: each new finding-specific regression must fail for the recorded defect
  before the associated source or migration change.
- [x] RED/GREEN command: one focused command per finding, then all Stage 9 tests;
  unresolved CRITICAL=0 and HIGH=0.
- [x] Boundaries: network=FORBIDDEN; credentials=NOT_READ; license=REVIEWED;
  live=NOT_ATTEMPTED.
- [x] Commit: `fix: resolve stage 9 critical and high findings`.

### Task 76 — Reflection round two, full acceptance, and report

- [x] Paths: `docs/reflection/stage-9-round-2.md`,
  `docs/stage-9-implementation-report.md`,
  `tests/unit/test_stage9_implementation_report.py`,
  `tests/unit/test_stage9_reflection_documents.py`.
- [x] Contract/types: round two rechecks every fix with actual commands; report
  separates offline engineering, Provider contracts, Snapshot/Agent/report
  non-execution, SEC conditional state, Tushare blocked state, all other blocked
  Providers, license/credential/Live states, tests, migration, risks, rollback,
  Git status, Stage 10 prohibition, and conclusion `CONDITIONAL GO` unless evidence
  justifies a stricter `NO-GO`.
- [x] Database: execute `uv run alembic current`, upgrade, downgrade `-1`,
  re-upgrade, current; final head `0008_production_providers`.
- [x] RED: report/reflection contracts fail before documents.
- [x] GREEN: run Stage 9 doc tests, `uv sync`, Ruff, format, mypy, full
  `uv run pytest -W error`, migration replay, residual-process and Git checks.
- [x] Boundaries: network=HARD_BLOCKED; credentials=NOT_READ; license=AS_RECORDED;
  live=NOT_ATTEMPTED.
- [x] Commit: `docs: complete stage 9 provider implementation report`.

## 5. Plan self-check

- [x] Exactly 77 Tasks exist: Task 0 through Task 76 with no missing or duplicate ID.
- [x] Every Task names concrete paths, interfaces/types, database impact, observable
  RED, RED/GREEN command, minimum GREEN, independent commit, and all four boundary
  flags.
- [x] Prompt coverage includes Registry, Capability, License, Credential Reference,
  configuration, authorization, HTTP/SSRF, rate/retry/circuit/cache, finite Sync,
  checkpoint, artifact/blob atomicity, manifest, quality, dead letter, freshness,
  health, adapters, bridges, API, Tool, CLI, PostgreSQL, docs, Reflection, report.
- [x] Design coverage preserves Route C and all interface/layer boundaries.
- [x] Gate-order review confirms no credential resolution or network construction
  can precede Definition, Capability, License, Policy, Credential Reference,
  Configuration, and explicit Live Authorization.
- [x] Table review justifies every retained table and rejects both meaningless
  tables and a giant JSON catch-all.
- [x] Database model/migration review confirms the same names, constraints, indexes,
  triggers, downgrade, and no Stage 2–8 mutation.
- [x] SEC policy review confirms exact HTTPS hosts/paths, conservative shared rate,
  contact-reference metadata only, and no Live request.
- [x] Tushare review confirms offline implementation is distinct from blocked
  license, not-read credential, not-attempted Live, and blocked production.
- [x] Fixture review confirms source manifests, byte checksums, LF stability,
  `OFFLINE`/`NOT_LIVE`, and synthetic separation.
- [x] API/Tool review confirms strict reads; CLI review confirms explicit writes and
  no arbitrary URL/path/SQL/provider/secret/latest.
- [x] Default-test review confirms external network and real credential reads are
  impossible and `tests_live` is excluded.
- [x] Historical-boundary review confirms no Snapshot, financial normalization,
  Retrieval, Agent, Report, advice, model, MCP, trading, frontend, or Stage 10 work.
- [x] Placeholder scan for banned planning markers and vague implementation phrases
  returns no matches.
- [x] Interface/type ordering review confirms every later reference is defined in
  section 3 or an earlier Task.
