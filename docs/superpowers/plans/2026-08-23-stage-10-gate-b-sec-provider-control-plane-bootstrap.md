# Stage 10 Gate B SEC Provider Control-Plane Bootstrap Design

## 1. Decision and scope

This document defines the production contract for materializing the
`SEC_EDGAR_PUBLIC_V1` Provider Definition, one Gate B Capability, and one
Provider Policy. It resolves the control-plane blocker identified after the
operational database reached Alembic revision
`0013_gate_b_attempt_number_capacity`.

This is a design artifact only. It does not implement the manifest, bootstrap
application, CLI, or tests. It does not create a Credential Reference, license
policy, Sync Request, plan, authorization, execution state, artifact, or
terminal state. It does not access the network.

```text
BASELINE_HEAD:
3b236fb5315ecbb751ffe9542337411d1141eeea

OPERATIONAL_DATABASE:
stock_research

OPERATIONAL_SCHEMA_HEAD:
0013_gate_b_attempt_number_capacity

CURRENT_BLOCKER:
OPERATIONAL_PROVIDER_CONTROL_PLANE_MISSING
```

## 2. Problem statement

The database has versioned tables and transaction-neutral repositories for
Provider Definition, Capability, and Provider Policy, but production has no
versioned SEC manifest, application service, or operator command that creates
the three records as one authoritative unit. Existing tests construct different
SEC-shaped rows for their own fixtures. Those fixtures cannot be copied into an
operational database because their names, domains, statuses, and budgets are
not mutually consistent.

The correction must create one production-owned source of truth and one atomic,
idempotent entry point. It must reuse the existing repositories and schema, and
it must stop before Operational Freeze creates credential, license, request, or
plan records.

## 3. Evidence hierarchy

Conflicts are resolved in this order:

1. Human-approved Stage 10 Gate B safety, authorization, and finite-pilot
   contracts.
2. Current production runtime invariants that enforce those contracts.
3. Accepted Stage 10 readiness and acceptance artifacts on the integrated
   mainline.
4. Current typed Provider domain models and database constraints.
5. Current production SEC adapter, endpoint, and transport policy.
6. Stage 10 integration fixtures that exercise the owning production boundary.
7. Unit fixtures used to specify a single type or checksum.
8. Older Stage 9 planning and capability-matrix descriptions.

Tests never become a separate operational source of truth. They may establish
the intent of a field only when it is consistent with higher-ranked evidence.

## 4. Evidence inventory

| Concern | Evidence | Authority and conclusion |
|---|---|---|
| Provider code | `providers/sec_edgar/schemas.py::SEC_PROVIDER_CODE`; authorization envelope validation; Phase 6 readiness | Exact `SEC_EDGAR_PUBLIC_V1`; resolved |
| Provider/adapter version | `providers/sec_edgar/adapter.py::SEC_ADAPTER_VERSION`; Stage 10 grant contracts | `1.0.0`; resolved |
| Definition shape | `domain/providers/schemas.py::ProviderDefinitionWrite` | Exact persisted field set; authoritative type |
| Definition natural identity | model/repository unique identity | `(code, definition_version)` |
| Definition status | Stage 9 matrix plus Gate B conditional posture | `ACTIVE` definition and `CONDITIONAL` production status |
| Domains | Gate B envelope validation and SEC endpoint policies | Sorted pair `data.sec.gov`, `www.sec.gov` |
| Capability name | Stage 10 grant contract and `SecEdgarCapability.FILING_DOCUMENTS` | `FETCH_SEC_FILING_DOCUMENTS` |
| Capability cardinality | `ProviderSyncRequestWrite` binds exactly one capability; accepted Gate B plan is one request/plan | One persisted capability for the finite pilot |
| Gate B resources | `providers/sec_edgar/policy.py::_GATE_B_RESOURCE_CONTRACT` | Exact three-resource runtime contract; not duplicated as mutable bootstrap data |
| Generic Provider Policy | `ProviderPolicyWrite`, `ProviderPolicyGate`, Stage 10 budgets | Four requests, 25 MiB total, generic attempts three |
| SEC transport | `build_sec_http_client_policy` | Separate 10/30/120 timeout, redirect zero, one physical client attempt |
| Gate B attempt/retry | authorization envelope and attempt reservation | Four physical attempts and one retry; not stored in generic `max_attempts` |
| License | `SourceLicensePolicyWrite`, live authorization matrix | Separate later freeze record; not bootstrap-owned |
| Contact | credential-reference model and Phase 6/7 contracts | Separate later freeze metadata record; no value in bootstrap |
| Retention | live authorization matrix | Provider Policy ceiling 30 days; exact grant deadline remains later |
| Existing persistence | `SqlAlchemyProviderDefinitionRepository`, `SqlAlchemyProviderGovernanceRepository` | Transaction-neutral, checksum-idempotent primitives |
| Existing seed pattern | `SecurityMasterSeedService`, `SqlAlchemySecurityMasterRepository.acquire_seed_lock` | Versioned manifest plus PostgreSQL transaction advisory lock |
| Migrations | `0008_production_providers` through current head | Required tables, foreign keys, checks, and unique constraints already exist |

## 5. Conflict resolution

| Field | Observed values | Sources | Winning value | Reason |
|---|---|---|---|---|
| Display name | `SEC EDGAR public data`; `SEC EDGAR public data and filing archive`; test labels | Provider Definition unit checksum contract; Stage 9 matrix; fixtures | `SEC EDGAR public data` | Exact typed checksum fixture is more precise than descriptive prose and test labels |
| Data domain | `US_SEC_FILINGS`; `REGULATORY_FILINGS`; `DOCUMENT_DISCLOSURES` | Typed Definition fixture/matrix; Gate B fixture; Stage 9 acceptance fixture | `US_SEC_FILINGS` | It is the Provider-level domain used by the canonical Provider Definition contract; narrower fixture labels are not manifests |
| Official domains | both SEC hosts; only `data.sec.gov` in an older fixture | Stage 10 envelope and endpoint policies; Stage 9 fixture | both hosts | Gate B requires submissions and archive resources on both hosts |
| Capability code | `FETCH_SEC_SUBMISSIONS`; `FETCH_SEC_FILING_DOCUMENT`; `FETCH_SEC_FILING_DOCUMENTS`; `SEC_FILING_DOCUMENT` | Stage 9 matrix; design; production adapter and Stage 10 grant; request-identity fixture | `FETCH_SEC_FILING_DOCUMENTS` | Current production adapter and accepted Stage 10 grant agree; exact matching forbids aliases |
| Capability count | separate submissions/doc capabilities; one capability ID per request | Stage 9 general-provider model; current Sync Request and Gate B grant | one | Gate B is one authorized request/plan. Submissions is a mandatory identity prerequisite within that plan, not a separately authorized Sync Request |
| Capability status | `IMPLEMENTED_OFFLINE`; `ENABLED`; test-only variants | enums and Gate B fixtures | `IMPLEMENTED_OFFLINE` | Bootstrap records implementation readiness without declaring live production activation; live remains separately authorized |
| Policy `network_enabled` | `False` in offline fixtures; controlled live transport required | test fixtures; ProviderPolicyGate and accepted Gate B | `True` | The operational policy must permit a later `network_requested=True` Gate B request; authorization remains structurally upstream |
| Policy `max_requests` | 2 or 3 in fixtures; 3 planned resources and 4 physical attempts in Gate B | fixtures; request-identity contract; accepted Stage 10 budget | `3` | The persisted generic request ceiling follows the exact three-resource Sync Request; the fourth physical send is authorized only by the Gate B attempt permit |
| Policy total bytes | 8 KiB fixture; 26 MiB fixture; 25 MiB accepted | fixtures; preparation and live-authorization matrix | `26,214,400` bytes | Human-approved 25 MiB limit outranks fixtures |
| Policy response bytes | small fixture; 20 MiB Gate B primary resource | fixtures; exact resource contract | `20,971,520` bytes | Largest approved single response |
| Policy duration | 30 seconds fixture; 120 seconds Gate B | fixtures; accepted finite pilot | `120` seconds | Accepted hard Gate B run/transport boundary |
| Policy `max_attempts` | 1 or 3 generic; 4 Gate B physical | fixtures; Phase 4 acceptance | `3` | Generic Provider contract stays at three; Gate B attempt four requires authorization and permit |
| Retention | `None`; 30 days | generic model; live authorization matrix | `30` days | Accepted default maximum; later license/grant may narrow it |

### 5.1 Unresolved human decisions

No unresolved value remains in the proposed control-plane manifest, so
`HUMAN_DECISION_REQUIRED` is `NO` for this bootstrap design. Future human
decisions still determine the exact Credential Reference, license-policy
record, retention deadline, filing identity, request, plan, and authorization;
they are deliberately outside this manifest and do not block the three-row
control-plane bootstrap contract.

## 6. Canonical Provider Definition

The bootstrap persists this exact `ProviderDefinitionWrite` payload:

| Field | Value | Materialization |
|---|---|---|
| `code` | `SEC_EDGAR_PUBLIC_V1` | literal |
| `definition_version` | `1.0.0` | literal |
| `adapter_version` | `1.0.0` | literal |
| `display_name` | `SEC EDGAR public data` | literal |
| `data_domain` | `US_SEC_FILINGS` | literal |
| `definition_status` | `ACTIVE` | enum literal |
| `production_status` | `CONDITIONAL` | enum literal |
| `official_domains` | `("data.sec.gov", "www.sec.gov")` | sorted literal tuple |
| `policy_version` | `1.0.0` | literal |
| `license_policy_version` | `1.0.0` | literal reference version; policy row is created later |
| `credential_reference_id` | `None` | literal; bootstrap cannot reference a not-yet-created row |
| `source_register_version` | `1.0.0` | literal |
| persisted `id` | repository-generated UUID | generated by existing ORM/repository |
| persisted `checksum` | existing repository `_checksum` | generated from the exact write payload |
| `created_at` | database timestamp | generated by database |

The definition's `credential_reference_id=None` is intentional. The later
Credential Reference owns `provider_definition_id`; the exact Sync Request and
grant then bind the reference ID. Bootstrap does not update the immutable
Definition or predeclare a credential UUID. No contact material participates in
the Definition checksum.

## 7. Canonical Capability

The bootstrap materializes one `ProviderCapabilityWrite` after obtaining the
Provider Definition ID:

| Field | Value |
|---|---|
| `provider_definition_id` | generated/reused Definition ID |
| `code` | `FETCH_SEC_FILING_DOCUMENTS` |
| `capability_version` | `1.0.0` |
| `status` | `IMPLEMENTED_OFFLINE` |
| `data_domain` | `US_SEC_FILINGS` |
| `market_codes` | `("US_EQUITY",)` |
| `security_types` | `("COMMON_STOCK",)` |
| `operations` | `("READ_LIVE_VALIDATION",)` |

This capability is the finite Gate B filing-evidence operation. The one Sync
Request and one grant bind this capability ID. The exact plan then requires:

1. `SEC_SUBMISSIONS` / `SEC_SUBMISSIONS_JSON` /
   `SUBMISSIONS_METADATA`;
2. `SEC_FILING_INDEX` / `SEC_FILING_DOCUMENT` / `FILING_INDEX`;
3. `SEC_PRIMARY_DOCUMENT` / `SEC_FILING_DOCUMENT` /
   `PRIMARY_FILING_DOCUMENT`.

The submissions resource establishes filing identity before document
acquisition. It is not a second independently invocable capability in this
pilot. Company Facts, exhibits, complete-submission text, and arbitrary
documents remain outside the capability's Gate B plan.

The bootstrap manifest does not duplicate `_GATE_B_RESOURCE_CONTRACT`; runtime
plan validation in `providers/sec_edgar/policy.py` remains authoritative for
resource order and endpoint identity.

## 8. Canonical persisted Provider Policy

The bootstrap materializes this `ProviderPolicyWrite`:

| Field | Exact value | Authority |
|---|---:|---|
| `provider_definition_id` | generated/reused Definition ID | natural relationship |
| `policy_version` | `1.0.0` | Definition contract |
| `endpoint_policy_version` | `1.0.0` | SEC endpoint/adapter version |
| `network_enabled` | `True` | controlled Gate B network request must be policy-permitted |
| `max_requests` | `3` | exact three-resource generic Sync Request ceiling |
| `max_response_bytes` | `20,971,520` | 20 MiB primary-document ceiling |
| `max_total_bytes` | `26,214,400` | accepted 25 MiB total ceiling |
| `max_duration_seconds` | `120` | accepted hard runtime boundary |
| `max_attempts` | `3` | unchanged generic Provider maximum |
| `max_redirects` | `0` | Gate B redirects forbidden |
| `rate_limit_per_second` | `Decimal("1")` | conservative project rate |
| `retry_base_delay_seconds` | `Decimal("1")` | minimum interval and deterministic retry base |
| `cache_enabled` | `False` | Gate B cache disabled |
| `cache_ttl_seconds` | `None` | required when cache is disabled |
| `retention_days` | `30` | default maximum; later license/grant may narrow |

### 8.1 Policy separation

These values do not collapse separate policy owners:

- `ProviderPolicy` is the persisted finite ceiling above.
- SEC transport policy remains 10-second connect, 30-second idle read,
  120-second total, zero redirects, and one `SafeHttpClient` attempt per
  controller invocation.
- Gate B authorization and `SecAttemptPermit` own four physical attempts, one
  plan-global retry, single-use approval, and pre-send reservation. The fourth
  physical attempt does not widen `ProviderPolicy.max_requests` or the generic
  Sync Request budget beyond three resources.
- `ProviderLicensePolicy` separately owns acquisition, storage, cache, derived
  use, redistribution, attribution, deletion, and license review.
- The later grant owns the exact retention deadline and may only narrow the
  30-day Provider Policy ceiling.
- Official domains live in the Definition and exact endpoint catalog, not in
  `ProviderPolicyWrite`.
- Allowed operation lives in the Capability, not in `ProviderPolicyWrite`.

## 9. Versioned manifest design

### 9.1 Production location

Create:

```text
src/stock_research_agent/providers/sec_edgar/bootstrap.py
```

The module will own these immutable types:

```text
SecProviderCapabilityBootstrapSpec
SecProviderPolicyBootstrapSpec
SecProviderControlPlaneBootstrapManifest
SecProviderControlPlaneBootstrapResult
SecProviderControlPlaneComponentResult
SecProviderControlPlaneBootstrapConflict
SecProviderControlPlaneBootstrapApplication
```

It will export exactly one V1 manifest constant:

```text
SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP
```

### 9.2 Manifest structure

`SecProviderControlPlaneBootstrapManifest` extends
`FrozenProviderContract` and contains:

```text
manifest_name = SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE
manifest_version = 1.0.0
definition: ProviderDefinitionWrite
capability: SecProviderCapabilityBootstrapSpec
policy: SecProviderPolicyBootstrapSpec
```

Capability and Policy specs contain every field except
`provider_definition_id`. Each has a method that accepts the authoritative
Definition ID and returns an existing `ProviderCapabilityWrite` or
`ProviderPolicyWrite`. This avoids free-form dictionaries and keeps validation
inside the current domain types.

The manifest validator requires:

- exact SEC Provider code and aligned V1 versions;
- capability and policy domains consistent with the Definition;
- exact sorted domains and allowlists;
- policy values equal to the resolved contract above;
- no credential, license, request, plan, authorization, or execution payload;
- no Company Facts capability;
- no secret-bearing field.

### 9.3 Checksum and versioning

`manifest_checksum` is `provider_checksum` over the canonical JSON form of the
entire manifest, including `manifest_name` and `manifest_version`, but excluding
generated database IDs and timestamps.

The repository continues to compute per-record checksums from the materialized
domain writes. The bootstrap result returns both the manifest checksum and the
three persisted record checksums.

A future compatible bootstrap release creates a new immutable manifest
constant and increments `manifest_version`. A change to Definition identity or
governance creates a new `definition_version`; changed Capability or Policy
payloads likewise require a new natural-key version. Existing rows are never
overwritten. An implementation must not silently apply a new manifest payload
under an old natural identity.

## 10. Atomic bootstrap application

### 10.1 Interface

`SecProviderControlPlaneBootstrapApplication` owns the transaction and accepts:

```text
session_factory: Callable[[], Session]
manifest: SecProviderControlPlaneBootstrapManifest
```

Public methods:

```text
inspect() -> SecProviderControlPlaneBootstrapResult
bootstrap() -> SecProviderControlPlaneBootstrapResult
```

`inspect` is read-only and reports `WOULD_CREATE`, `REUSED`, or `CONFLICT` per
component. `bootstrap` returns only after the transaction commits and reports
`CREATED` if any component was inserted or `REUSED` when all three were already
equivalent. Conflict raises the stable application exception and produces no
result suggesting success.

The result contains only:

- aggregate and per-component status;
- database name;
- manifest name, version, and checksum;
- Provider Definition, Capability, and Policy IDs/checksums;
- safe conflict code when rendered by the CLI.

It contains no ORM entity, Session, database URL, credential/contact material,
license decision, request, plan, grant, approval, or execution capability.

### 10.2 Dependencies

The application constructs and uses only:

```text
SqlAlchemyProviderDefinitionRepository
SqlAlchemyProviderGovernanceRepository
```

It must not import Provider Sync, live-evidence, authorization, execution,
artifact, terminal, HTTP, credential resolver, or SEC transport repositories.

### 10.3 Transaction sequence

```text
open Session
  -> begin transaction
  -> verify current_database identity
  -> acquire transaction advisory lock for manifest natural identity
  -> load Definition natural identity
  -> compare or insert Definition
  -> materialize Capability and Policy with authoritative Definition ID
  -> load/compare or insert Capability
  -> load/compare or insert Policy
  -> authoritative readback of all three rows
  -> verify natural keys and per-record checksums
  -> flush
  -> COMMIT
  -> construct/return success result
```

No success result escapes before commit. Any validation, repository, readback,
or database error rolls back all inserts. The advisory lock key is a stable
signed 64-bit value derived from SHA-256 of:

```text
SEC_PROVIDER_CONTROL_PLANE_BOOTSTRAP:
SEC_EDGAR_PUBLIC_V1:
1.0.0
```

This follows the existing Security Master seed pattern and serializes all
conforming bootstrap invocations for the natural identity.

### 10.4 Conflict projection

Application error codes are:

```text
SEC_PROVIDER_BOOTSTRAP_DEFINITION_CONFLICT
SEC_PROVIDER_BOOTSTRAP_CAPABILITY_CONFLICT
SEC_PROVIDER_BOOTSTRAP_POLICY_CONFLICT
SEC_PROVIDER_BOOTSTRAP_READBACK_MISMATCH
SEC_PROVIDER_BOOTSTRAP_DATABASE_INVALID
SEC_PROVIDER_BOOTSTRAP_PERSISTENCE_CONFLICT
```

Known `ProviderRepositoryConflict` values and named unique-constraint
`IntegrityError` races are translated narrowly. Raw SQL, constraint detail,
database URL, and connection information are not included in the public error.
There is no broad exception-to-success conversion.

No persistent `ProviderAuditEvent` is written by bootstrap. The manifest and
result provide deterministic operator evidence without adding a fourth
control-plane side effect.

## 11. Idempotency and partial-state contract

| Initial state | Required outcome |
|---|---|
| Empty | Insert all three in one transaction; `CREATED` |
| Complete equivalent | Insert nothing; reuse all IDs; `REUSED` |
| Definition only, equivalent | Reuse Definition; create Capability and Policy atomically; `CREATED` |
| Definition + Capability, both equivalent | Create only Policy; `CREATED` |
| Definition + Policy, both equivalent | Create only Capability; `CREATED` |
| Any natural identity with different checksum | Roll back; exact component conflict |
| Partial state plus any conflict | Insert nothing; leave pre-existing rows unchanged; conflict |
| Missing parent referenced by partial child | Database/integrity conflict; no repair by guessing |

Equivalent means exact natural identity and exact repository checksum for the
materialized domain write. Display-name similarity, aliases, case folding,
latest-version lookup, or partial field equality are insufficient.

The application completes equivalent partial state because all missing payloads
come from the same immutable manifest. It never overwrites or updates a
conflicting row.

## 12. Concurrency contract

### 12.1 Concurrent identical calls

Both calls acquire the same transaction advisory lock. The first inserts and
commits. The second then re-reads all three rows and returns `REUSED`. Final
cardinality is exactly one Definition, one Capability, and one Policy.

### 12.2 Concurrent conflicting calls

Calls using the same natural identity but different manifest checksum acquire
the same lock. Whichever commits first becomes authoritative; the other re-reads
and returns the exact component conflict. It writes nothing.

### 12.3 Unique-constraint backstop

Existing constraints remain authoritative:

```text
Provider Definition: (code, definition_version)
Capability: (provider_definition_id, code, capability_version)
Provider Policy: (provider_definition_id, policy_version)
```

If a nonconforming writer bypasses the advisory-lock application and creates a
race, named unique-constraint failure is projected as a deterministic bootstrap
conflict after rollback. Bootstrap does not retry a write on stale assumptions.

## 13. Zero-side-effect boundary

The bootstrap transaction may write only:

```text
provider_definitions
provider_capabilities
provider_policies
```

It is structurally forbidden from writing:

```text
provider_credential_references
provider_license_policies
provider_sync_requests
provider_sync_plans
provider_sync_runs
provider_request_attempts
provider_raw_artifacts
provider_live_validation_runs
live_authorization_grants
live_execution_approvals
```

It also creates no plan checksum, `AuthorizedGateBExecution`, attempt permit,
blob, network client, DNS lookup, HTTP request, or model call.

Boundary tests inspect imports and repository construction, then compare all
forbidden table counts before and after CREATED, REUSED, partial completion,
conflict, and concurrent calls. Every count must remain unchanged.

## 14. CLI/operator entry point

Add one command to the existing `provider` Typer application:

```text
stock-research provider bootstrap-sec-control-plane
```

Options:

```text
--dry-run
--confirm
--json
```

Rules:

- `DATABASE_URL` is required through existing `Settings`; the value is never
  printed.
- The command queries and displays only `current_database()` as database
  identity.
- `--dry-run` invokes `inspect`, performs no persistent write, and does not
  require `--confirm`.
- A mutating invocation requires `--confirm`; absence fails closed before the
  application is called.
- Output includes manifest name/version/checksum and per-component status.
- Success aggregate status is `CREATED` or `REUSED`.
- Conflict output is `CONFLICT` with one stable safe error code and a nonzero
  exit status.
- The command has no host, URL, contact, credential, license, request, plan,
  authorization, or execution option.
- It never imports or constructs `SafeHttpClient`, a credential resolver,
  authorization service, Gate B application, or SEC adapter transport.

The CLI uses the existing engine/session-factory construction, while transaction
begin/commit/rollback remains owned by
`SecProviderControlPlaneBootstrapApplication`.

## 15. Migration decision

No migration is required.

Existing schema already provides:

- all fields required by the three domain write types;
- UUID primary keys and database timestamps;
- checksum columns and validation;
- `RESTRICT` parent foreign keys;
- exact natural-key unique constraints;
- finite Provider Policy checks supporting every proposed value;
- current Alembic head `0013_gate_b_attempt_number_capacity`.

The implementation adds only application code, a typed manifest, CLI wiring,
and tests. Business seed data remains outside Alembic.

```text
MIGRATION_REQUIRED:
NO
```

## 16. RED-test plan

No test is implemented by this design phase. The implementation workstream must
first establish the following REDs.

### 16.1 Unit manifest contracts

Create:

```text
tests/unit/test_sec_provider_control_plane_bootstrap_manifest_red.py
```

Tests:

```text
test_sec_bootstrap_manifest_is_strict_frozen_and_versioned
test_sec_bootstrap_manifest_has_exact_provider_definition
test_sec_bootstrap_manifest_has_exact_gate_b_capability
test_sec_bootstrap_manifest_has_exact_generic_provider_policy
test_sec_bootstrap_manifest_checksum_is_canonical_and_stable
test_sec_bootstrap_manifest_rejects_company_facts_or_extra_capability
test_sec_bootstrap_manifest_keeps_generic_attempts_at_three
test_sec_bootstrap_manifest_keeps_provider_request_ceiling_at_three
test_sec_bootstrap_manifest_keeps_gate_b_physical_attempt_limit_out_of_policy
test_sec_bootstrap_manifest_contains_no_credential_license_or_execution_payload
test_sec_bootstrap_specs_materialize_existing_domain_write_types
```

### 16.2 Unit application contracts

Create:

```text
tests/unit/test_sec_provider_control_plane_bootstrap_application_red.py
```

Tests with transaction/repository fakes:

```text
test_empty_state_creates_definition_capability_policy_in_order
test_complete_equivalent_state_returns_reused
test_equivalent_partial_state_creates_only_missing_components
test_definition_conflict_fails_before_child_writes
test_capability_conflict_rolls_back_new_definition_and_policy
test_policy_conflict_rolls_back_new_definition_and_capability
test_readback_mismatch_rolls_back
test_success_result_is_created_only_after_commit
test_known_repository_conflicts_project_to_stable_safe_codes
test_unexpected_exception_rolls_back_and_does_not_report_success
test_application_uses_one_manifest_for_all_materialized_writes
```

### 16.3 PostgreSQL contracts

Create:

```text
tests/integration/test_sec_provider_control_plane_bootstrap_postgres_red.py
```

Use only the repository loopback disposable test database. Tests:

```text
test_postgres_empty_bootstrap_creates_exact_three_rows
test_postgres_second_equivalent_bootstrap_reuses_all_ids
test_postgres_definition_only_state_completes_atomically
test_postgres_definition_capability_state_completes_policy
test_postgres_definition_policy_state_completes_capability
test_postgres_conflicting_definition_rolls_back_every_new_row
test_postgres_conflicting_capability_rolls_back_every_new_row
test_postgres_conflicting_policy_rolls_back_every_new_row
test_postgres_failure_before_commit_leaves_no_partial_bootstrap
test_postgres_concurrent_identical_bootstrap_creates_one_triplet
test_postgres_concurrent_conflicting_bootstrap_has_one_winner_one_conflict
test_postgres_readback_matches_manifest_and_record_checksums
test_postgres_bootstrap_changes_no_forbidden_table_counts
```

These tests must exercise real unique constraints, advisory transaction locks,
commit/rollback, and independent post-transaction readback. Sequential mocks
cannot replace the concurrency tests.

### 16.4 CLI contracts

Create:

```text
tests/unit/test_provider_cli_sec_bootstrap_red.py
tests/integration/test_provider_cli_sec_bootstrap_postgres_red.py
```

Tests:

```text
test_sec_bootstrap_cli_requires_database_url
test_sec_bootstrap_cli_requires_confirm_for_write
test_sec_bootstrap_cli_dry_run_writes_nothing
test_sec_bootstrap_cli_reports_database_and_manifest_identity_without_url
test_sec_bootstrap_cli_reports_created
test_sec_bootstrap_cli_reports_reused
test_sec_bootstrap_cli_reports_conflict_with_safe_nonzero_exit
test_sec_bootstrap_cli_never_resolves_contact_or_opens_network
test_sec_bootstrap_cli_creates_no_freeze_authorization_or_execution_rows
```

### 16.5 Static boundary contracts

Create:

```text
tests/unit/test_sec_provider_control_plane_bootstrap_boundaries_red.py
```

Tests:

```text
test_bootstrap_imports_only_definition_and_governance_repositories
test_bootstrap_does_not_import_live_authorization_or_execution_modules
test_bootstrap_does_not_import_sync_artifact_terminal_or_transport_owners
test_bootstrap_manifest_is_the_only_production_sec_control_plane_payload
test_tests_reference_production_manifest_instead_of_redeclaring_sec_values
test_alembic_contains_no_sec_business_seed
```

### 16.6 Regression commands

The later implementation plan must use repository-standard commands equivalent
to:

```text
uv run pytest -W error tests/unit/test_provider_definitions.py
uv run pytest -W error tests/unit/test_provider_governance_capabilities.py
uv run pytest -W error tests/unit/test_provider_policy.py
uv run pytest -W error tests/unit/test_production_provider_registry.py
uv run pytest -W error tests/integration/test_provider_governance_repository_postgres.py
uv run pytest -W error tests/integration/test_provider_migrations.py
uv run ruff check <modified Python files>
uv run ruff format --check <modified Python files>
uv run mypy src/stock_research_agent
git diff --check
```

No external/live tests are part of bootstrap verification.

## 17. Operational Freeze reintegration

The repository contract supports this exact sequence after a separately
approved implementation and bootstrap invocation:

```text
SEC control-plane bootstrap transaction
  -> authoritative readback of Definition, Capability, Policy
  -> STOP bootstrap scope

Operational Freeze transaction(s)
  -> create/reuse Credential Reference metadata for the Definition
  -> create/reuse approved ProviderLicensePolicy
  -> build GateBSyncRequestIdentity from authoritative IDs
  -> build and persist one LIVE_VALIDATION Sync Request
  -> materialize exact three-resource plan
  -> compute final plan checksum using actual sync_request_id
  -> persist plan
  -> field-by-field readback and checksum verification
  -> Operational Freeze COMPLETE
  -> STOP before Grant or Approval
```

Bootstrap does not create or validate the contact value, select filing data,
make a retention/legal decision, or compute the final request/plan checksum.
Operational Freeze must use the bootstrapped IDs and checksums; it may not
redeclare Provider values or select the latest row implicitly.

Only a later human-authorized phase may create a single-use grant and approval.
Only after that may the authoritative execution-start transaction create a Sync
Run and attempt permit.

## 18. Implementation file-change forecast

Expected production changes:

```text
CREATE  src/stock_research_agent/providers/sec_edgar/bootstrap.py
MODIFY  src/stock_research_agent/cli_providers.py
```

Expected tests:

```text
CREATE  tests/unit/test_sec_provider_control_plane_bootstrap_manifest_red.py
CREATE  tests/unit/test_sec_provider_control_plane_bootstrap_application_red.py
CREATE  tests/unit/test_sec_provider_control_plane_bootstrap_boundaries_red.py
CREATE  tests/unit/test_provider_cli_sec_bootstrap_red.py
CREATE  tests/integration/test_sec_provider_control_plane_bootstrap_postgres_red.py
CREATE  tests/integration/test_provider_cli_sec_bootstrap_postgres_red.py
```

Reuse without behavior changes:

```text
src/stock_research_agent/domain/providers/schemas.py
src/stock_research_agent/domain/providers/capabilities.py
src/stock_research_agent/domain/providers/policies.py
src/stock_research_agent/domain/providers/canonical.py
src/stock_research_agent/db/repositories/providers.py
src/stock_research_agent/db/session.py
src/stock_research_agent/providers/sec_edgar/adapter.py
src/stock_research_agent/providers/sec_edgar/policy.py
```

Do not touch:

```text
migrations/
live authorization or approval code
attempt reservation/execution code
credential resolver
SEC transport
artifact/terminal persistence
Stage 11
```

## 19. Design self-review

```text
CANONICAL_PROVIDER_DEFINITION_RESOLVED: YES
CANONICAL_CAPABILITY_RESOLVED: YES
CANONICAL_PROVIDER_POLICY_RESOLVED: YES
HUMAN_DECISION_REQUIRED: NO
VERSIONED_MANIFEST_DESIGNED: YES
ATOMIC_APPLICATION_DESIGNED: YES
IDEMPOTENCY_CONTRACT_DESIGNED: YES
CONCURRENCY_CONTRACT_DESIGNED: YES
ZERO_SIDE_EFFECT_BOUNDARY_DESIGNED: YES
MIGRATION_REQUIRED: NO
RED_TEST_PLAN_COMPLETE: YES
```

The design is ready for human review. Approval of this document would authorize
neither RED-test creation nor production implementation; each requires a
separately scoped phase.
