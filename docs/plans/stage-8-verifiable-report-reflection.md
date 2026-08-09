# Stage 8 Verifiable Report and Runtime Reflection Implementation Plan

- Approved design:
  `docs/specs/stage-8-verifiable-report-reflection-design.md`
- Development branch: `stage-8/verifiable-report-reflection`
- Baseline revision: `0bbb54c`
- Design commit: `da27495`
- Python: 3.12.13
- Database: PostgreSQL 17.10
- Starting migration: `0006_controlled_research_agent`
- Target migration: `0007_create_verifiable_reports_and_reflection`
- Method: strict RED → GREEN → focused regression → independent commit

## 1. Global execution rules

- [x] Run every pytest command in one foreground process with
  `PYTEST_ADDOPTS=""`.
- [x] Set `DATABASE_URL` only to `stock_research` and `TEST_DATABASE_URL` only to
  the independently verified `stock_research_test`.
- [x] Never run pytest, Alembic, Seed, or schema reset concurrently.
- [x] A RED must fail because the named behavior is absent, not because of a typo,
  import cycle, database outage, or fixture error.
- [x] Add the minimum implementation for the active Task.
- [x] Do not create production code before its focused RED has been observed.
- [x] Run the focused GREEN command and affected regression before each commit.
- [x] Stage explicit paths only and inspect the staged file list.
- [x] Do not loosen mypy, add unexplained ignores, skip/xfail defects, replace
  PostgreSQL with SQLite, or generate Golden values from the renderer.
- [x] Keep default tests offline and model-free.
- [x] Do not merge `main`, configure a remote, create a PR, or enter Stage 9.

## 2. Approved contracts and limits

| Contract | Value |
|---|---|
| Manifest schema | `report-input-manifest-v1` |
| Report Policy | `verifiable-report-policy-v1` |
| Reflection Policy | `runtime-report-reflection-v1` |
| Template schema | `report-template-v1` |
| Template versions | `1.0.0` |
| Renderer | `deterministic-report-renderer-v1` |
| Structured report | `research-report-v1` |
| Markdown renderer | `deterministic-markdown-v1` |
| Reference allocator | `report-reference-allocator-v1` |
| Reflection engine | `deterministic-report-reflection-v1` |
| Revision engine | `deterministic-report-revision-v1` |
| Release Gate | `report-release-gate-v1` |
| Locales | `zh-CN`, `en-US` |
| Default locale | `zh-CN` |
| Max report blocks | 300 |
| Max Claims per block | 20 |
| Max Citations per block | 20 |
| Max excerpt | 1,000 characters |
| Reflection rounds | 2 |
| Revision rounds | 1 |
| Model calls/tokens | 0 |

`PUBLISHABLE` is always exposed as an internal release decision. No schema uses a
field that implies public distribution.

## 3. Database-table review

The approved 15-table design remains justified:

| Table | Independent responsibility and why it is not merged |
|---|---|
| `report_policies` | immutable generation permission/version contract |
| `report_template_versions` | immutable localized data-only rendering contract |
| `runtime_reflection_policies` | independent audit-rule and round contract |
| `report_requests` | one immutable Manifest seal and requested output |
| `report_generation_runs` | idempotent mutable-to-terminal generation lifecycle |
| `research_reports` | immutable structured/Markdown report versions |
| `report_sections` | ordered bounded section queries and status constraints |
| `report_blocks` | ordered atomic factual/structural units |
| `report_claim_bindings` | location-level Claim audit relation |
| `report_evidence_bindings` | exact Stage 7 Claim-Evidence Link relation |
| `report_citation_bindings` | exact Citation/DocumentVersion projection |
| `report_reflection_runs` | round-specific lifecycle and counts |
| `report_reflection_findings` | append-only per-rule audit findings |
| `report_revision_runs` | one source-to-target subtractive transformation |
| `report_release_gates` | one authoritative internal release decision |

`ReportInputManifest` is a strict domain object embedded in `report_requests` as
typed columns plus bounded canonical JSON. It has no independent lifecycle or query
surface, so a separate Manifest table would add a join without improving
immutability. Sections, Blocks, and bindings remain normalized because collapsing
them into one JSON column would prevent database-enforced lineage and bounded query
contracts. All foreign keys use `RESTRICT`; no circular ownership or cascade delete
is introduced.

## 4. Interface inventory

Every Task may reference only these interfaces or interfaces defined in an earlier
Task.

```python
def canonical_report_json(value: object) -> str: ...
def report_checksum(value: object) -> str: ...
def build_report_input_manifest(bundle: PersistedReportInput) -> ReportInputManifest: ...
def validate_report_input_manifest(
    manifest: ReportInputManifest,
    bundle: PersistedReportInput,
) -> VerifiedReportInput: ...

class ReportInputRepository(Protocol):
    def get_package_bundle(self, research_package_id: UUID) -> PersistedReportInput | None: ...

class ReportPolicyRepository(Protocol):
    def get_policy(self, version: str) -> ReportPolicyRecord | None: ...
    def add_policy(self, value: ReportPolicyWrite) -> ReportPolicyRecord: ...

class ReportTemplateRepository(Protocol):
    def get_template(
        self, name: str, version: str, locale: ReportLocale
    ) -> ReportTemplateVersionRecord | None: ...
    def add_template(
        self, value: ReportTemplateVersionWrite
    ) -> ReportTemplateVersionRecord: ...

class ReportRequestRepository(Protocol):
    def add_request(self, value: ReportRequestWrite) -> ReportRequestRecord: ...
    def get_request(self, request_id: UUID) -> ReportRequestRecord | None: ...

class ReportGenerationRepository(Protocol):
    def create_run(self, value: ReportGenerationRunWrite) -> ReportGenerationRunRecord: ...
    def get_run(
        self, run_id: UUID, *, for_update: bool = False
    ) -> ReportGenerationRunRecord | None: ...
    def find_reusable_run(self, idempotency_key: str) -> ReportGenerationRunRecord | None: ...
    def transition(
        self, run_id: UUID, value: ReportGenerationTransition
    ) -> ReportGenerationRunRecord: ...

class ResearchReportRepository(Protocol):
    def add_report(self, value: ResearchReportAggregateWrite) -> ResearchReportAggregate: ...
    def get_report(self, report_id: UUID) -> ResearchReportAggregate | None: ...
    def list_versions(self, generation_run_id: UUID) -> tuple[ResearchReportRecord, ...]: ...

class ReportReflectionRepository(Protocol):
    def create_run(self, value: ReportReflectionRunWrite) -> ReportReflectionRunRecord: ...
    def complete_run(
        self,
        run_id: UUID,
        result: ReportReflectionCompletion,
        findings: tuple[ReportReflectionFindingWrite, ...],
    ) -> ReportReflectionResult: ...

class ReportRevisionRepository(Protocol):
    def create_run(self, value: ReportRevisionRunWrite) -> ReportRevisionRunRecord: ...
    def complete_run(
        self,
        run_id: UUID,
        result: ReportRevisionCompletion,
        target: ResearchReportAggregateWrite | None,
    ) -> ReportRevisionResult: ...

class ReportReleaseGateRepository(Protocol):
    def add_gate(self, value: ReportReleaseGateWrite) -> ReportReleaseGateRecord: ...

class ReportQueryRepository(Protocol):
    def get_report_view(self, report_id: UUID) -> ResearchReportView | None: ...
    def list_section_views(self, report_id: UUID, page: PageRequest) -> Page[ReportSectionView]: ...
    def list_block_views(self, report_id: UUID, page: PageRequest) -> Page[ReportBlockView]: ...
    def list_claim_binding_views(self, report_id: UUID, page: PageRequest) -> Page[ReportClaimBindingView]: ...
    def list_evidence_binding_views(self, report_id: UUID, page: PageRequest) -> Page[ReportEvidenceBindingView]: ...
    def list_citation_binding_views(self, report_id: UUID, page: PageRequest) -> Page[ReportCitationBindingView]: ...
    def list_reflection_run_views(self, report_id: UUID, page: PageRequest) -> Page[ReportReflectionRunView]: ...
    def list_finding_views(self, report_id: UUID, page: PageRequest) -> Page[ReportReflectionFindingView]: ...
    def list_revision_views(self, report_id: UUID, page: PageRequest) -> Page[ReportRevisionRunView]: ...
    def get_release_gate_view(self, report_id: UUID) -> ReportReleaseGateView | None: ...

class DeterministicReportRenderer:
    def render(
        self,
        report_input: VerifiedReportInput,
        request: ReportRequestRecord,
        policy: ReportPolicyRecord,
        template: ReportTemplateVersionRecord,
    ) -> RenderedReportDraft: ...

class DeterministicMarkdownRenderer:
    def render(self, content: StructuredReportContent) -> RenderedMarkdown: ...

class ReportReferenceAllocator:
    def allocate(self, content: StructuredReportContent) -> ReferenceAllocation: ...

class DeterministicReportReflectionEngine:
    def reflect(
        self,
        report: ResearchReportAggregate,
        manifest: ReportInputManifest,
        policy: RuntimeReflectionPolicyRecord,
        round_number: int,
    ) -> ReportReflectionDraft: ...

class DeterministicReportRevisionEngine:
    def revise(
        self,
        source: ResearchReportAggregate,
        reflection: ReportReflectionResult,
        policy: ReportPolicyRecord,
    ) -> ReportRevisionDraft: ...

class ReportReleaseGate:
    def evaluate(
        self,
        candidate: ResearchReportAggregate,
        manifest: ReportInputManifest,
        round_two: ReportReflectionResult,
        policy: ReportPolicyRecord,
    ) -> ReportReleaseDecisionResult: ...

class ReportGenerationService:
    def generate(self, command: GenerateReportCommand) -> ReportGenerationResult: ...

class ReportReflectionService:
    def reflect(self, command: ReflectReportCommand) -> ReportReflectionResult: ...

class ReportRevisionService:
    def revise(self, command: ReviseReportCommand) -> ReportRevisionResult: ...

class ReportReleaseService:
    def check(self, command: ReleaseCheckCommand) -> ReportReleaseGateRecord: ...

class ReportQueryService:
    # ten read methods matching ReportQueryRepository projections
    ...
```

`NarrativeProvider` and `ReflectionProvider` use the approved design signatures.
Production factories expose only deterministic providers. Scripted providers exist
under tests and are never production defaults.

## 5. Task sequence

### Task 0 — Update repository Stage 8 boundary

- [x] Files: `AGENTS.md`, `tests/unit/test_stage8_repository_guidelines.py`.
- [x] Contract: repository instructions must name the Stage 8 branch/design/plan,
  Package-only input, deterministic renderer, two/one round limits, model/Tool/
  advice prohibitions, and Stage 9 boundary.
- [x] Database: none.
- [x] RED: documentation contract fails because `AGENTS.md` still prohibits Stage 8.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_stage8_repository_guidelines.py`
- [x] Expected RED: assertion identifies the stale Stage 7 branch/scope text.
- [x] GREEN: replace only obsolete stage guidance; preserve all Stage 7 Evidence,
  model, Tool, PostgreSQL, and real-company restrictions.
- [x] GREEN command: same focused test, then
  `uv run pytest -W error tests/unit/test_stage7_documentation.py`.
- [x] Expected GREEN: both documentation contracts pass, zero warnings.
- [x] Commit: `docs: authorize stage 8 report implementation`.

### Task 1 — Report Input Manifest domain model

- [x] Files: `tests/unit/test_report_input_manifest_schema.py`,
  `src/stock_research_agent/domain/reports/__init__.py`,
  `src/stock_research_agent/domain/reports/enums.py`,
  `src/stock_research_agent/domain/reports/schemas.py`.
- [x] Classes: `ReportInputManifest`, `PersistedReportInput`,
  `VerifiedReportInput`; inputs are Stage 7 records, output is frozen strict
  manifest state.
- [x] Database: `report_requests` will persist this model in Task 4.
- [x] RED: required IDs, ordered tuples, aware UTC, enums, bounds, synthetic status,
  empty honest sets, and extra-field rejection.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_input_manifest_schema.py`.
- [x] Expected RED: import/schema assertions fail because the reports package is
  absent.
- [x] GREEN: add strict frozen Pydantic contracts and closed enums only.
- [x] GREEN command: same focused test.
- [x] Expected GREEN: schema tests pass; no database import in domain package.
- [x] Commit: `feat: define immutable report input manifest`.

### Task 2 — Manifest canonical serializer

- [x] Files: `tests/unit/test_report_manifest_canonical.py`,
  `src/stock_research_agent/domain/reports/canonical.py`.
- [x] Functions:
  `canonical_report_json(value: object) -> str`,
  `report_checksum(value: object) -> str`.
- [x] Inputs: nested strict values; output: UTF-8 canonical JSON/SHA-256.
- [x] Database: none.
- [x] RED: sorted keys; stable tuple order; UUID, Enum, Decimal string, UTC `Z`,
  NFKC; reject float, naive time, sets, default stringification.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_manifest_canonical.py`.
- [x] Expected RED: serializer functions are missing.
- [x] GREEN: implement explicit recursive canonical conversion and compact JSON.
- [x] GREEN command: same focused test.
- [x] Expected GREEN: independently calculated strings/hashes pass.
- [x] Commit: `feat: add canonical report serialization`.

### Task 3 — Manifest checksum and lineage validator

- [x] Files: `tests/unit/test_report_manifest_validation.py`,
  `src/stock_research_agent/domain/reports/input_verification.py`.
- [x] Functions:
  `build_report_input_manifest(PersistedReportInput) -> ReportInputManifest`,
  `validate_report_input_manifest(ReportInputManifest, PersistedReportInput) -> VerifiedReportInput`.
- [x] Database: read-only Stage 7 records; no schema change.
- [x] RED: missing ID, wrong Run/Security/Snapshot/as-of, future data, synthetic
  real-company evidence, unreachable Citation, unused records, unstable ordering,
  Package/Claim/Evidence/Link/Citation checksum mismatch.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_manifest_validation.py`.
- [x] Expected RED: invalid bundles are not classified because validator is absent.
- [x] GREEN: exact set reconstruction and fail-closed canonical checks; empty input
  sets remain empty.
- [x] GREEN command: same focused test.
- [x] Expected GREEN: all negative cases return stable codes and repeated inputs
  produce the same checksum.
- [x] Commit: `feat: validate sealed report input manifests`.

### Task 4 — Manifest persistence model and repository

- [x] Files: `tests/unit/test_report_models_manifest.py`,
  `src/stock_research_agent/db/models/reports.py`,
  `src/stock_research_agent/db/repositories/reports.py`,
  model/repository `__init__.py`.
- [x] Classes: `ReportRequest`, `SqlAlchemyReportRepository`;
  `get_package_bundle(UUID) -> PersistedReportInput | None`,
  `add_request(ReportRequestWrite) -> ReportRequestRecord`.
- [x] Database: `report_requests`, with manifest JSON/checksum, exact IDs,
  unique idempotency key, restrictive Stage 7 FKs, immutable trigger planned in
  Task 38.
- [x] RED: metadata parity, repository protocol/AST boundaries, compiled exact
  Stage 7 read with stable `ORDER BY`, and no write to Stage 7 models. Real
  persistence/rollback waits for Tasks 38–39 after migration exists.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_models_manifest.py`.
- [x] Expected RED: table/repository assertions fail.
- [x] GREEN: minimum SQLAlchemy model and parameterized repository implementation
  whose SQL shape can be inspected without creating the table; no commit ownership.
- [x] GREEN command: same focused tests.
- [x] Expected GREEN: metadata and repository-boundary tests pass.
- [x] Commit: `feat: persist immutable report manifests`.

### Task 5 — Report Request

- [x] Files: `tests/unit/test_report_requests.py`,
  `src/stock_research_agent/domain/reports/requests.py`.
- [x] Class/signature:
  `ReportRequestService.create(CreateReportRequest) -> ReportRequestRecord`.
- [x] Input/output: package ID plus closed type/locale/template/policy/sections;
  sealed Request.
- [x] Database: `report_requests`.
- [x] RED: BLOCKED/full and BLOCKED/financial rejection, exact fixed versions,
  section/locale/type whitelist, no path/expression/script, policy reductions only.
- [x] RED command: `uv run pytest -W error tests/unit/test_report_requests.py`.
- [x] Expected RED: preflight behavior is absent.
- [x] GREEN: compose Manifest validator and immutable Request builder.
- [x] GREEN command: same focused test.
- [x] Expected GREEN: exact codes and idempotency basis pass.
- [x] Commit: `feat: add report request preflight`.

### Task 6 — Report Policy

- [x] Files: `tests/unit/test_report_policy.py`,
  `src/stock_research_agent/domain/reports/policies.py`.
- [x] Classes/signatures:
  `ReportPolicyService.require(str) -> ReportPolicyRecord`,
  `ReportPolicySeedService.seed_v1() -> ReportPolicySeedResult`.
- [x] Database: `report_policies`.
- [x] RED: exact defaults, all mandatory disclosure flags, synthetic/model disabled,
  300/20/20/1000 bounds, 2/1 rounds, idempotent seed, incompatible-content refusal.
- [x] RED command: `uv run pytest -W error tests/unit/test_report_policy.py`.
- [x] Expected RED: Policy types/service are absent.
- [x] GREEN: immutable checksummed seed and validator.
- [x] GREEN command: same test.
- [x] Expected GREEN: exact values and no-overwrite behavior pass.
- [x] Commit: `feat: add immutable report policy`.

### Task 7 — Report Template Version

- [x] Files: `tests/unit/test_report_templates.py`,
  `src/stock_research_agent/domain/reports/templates.py`.
- [x] Classes/signatures:
  `ReportTemplateVersionRecord`,
  `ReportTemplateSeedService.seed_v1() -> ReportTemplateSeedResult`,
  `ReportTemplateResolver.require(name, version, locale) -> ReportTemplateVersionRecord`.
- [x] Database: `report_template_versions`.
- [x] RED: data-only tokens, exact name/version/locale/type, checksum, immutable/
  idempotent seed, executable syntax/path/attribute/environment/network rejection,
  TEST_ONLY isolation.
- [x] RED command: `uv run pytest -W error tests/unit/test_report_templates.py`.
- [x] Expected RED: template contracts are missing.
- [x] GREEN: closed token enums and fixed data records; no Jinja/evaluation.
- [x] GREEN command: same test.
- [x] Expected GREEN: approved templates validate and attacks fail closed.
- [x] Commit: `feat: add data only report templates`.

### Task 8 — Report Generation Run

- [x] Files: `tests/unit/test_report_generation_runs.py`,
  `src/stock_research_agent/domain/reports/generation.py`.
- [x] Classes/signatures:
  `ReportGenerationStateMachine.transition(current, target) -> ReportGenerationStatus`,
  generation Run schemas.
- [x] Database: `report_generation_runs`.
- [x] RED: CREATED→RUNNING→four terminals, forbidden transitions, immutable identity,
  safe error, exact Package/Policy/template/renderer/locale/checksums.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_generation_runs.py`.
- [x] Expected RED: transition/schema behavior absent.
- [x] GREEN: closed transition map and strict Run contracts.
- [x] GREEN command: same test.
- [x] Expected GREEN: full transition matrix passes.
- [x] Commit: `feat: add report generation lifecycle`.

### Task 9 — Research Report aggregate

- [x] Files: `tests/unit/test_research_report_aggregate.py`,
  `src/stock_research_agent/domain/reports/reporting.py`.
- [x] Classes: `StructuredReportContent`, `ResearchReportRecord`,
  `ResearchReportAggregateWrite`, `ResearchReportAggregate`.
- [x] Inputs/outputs: canonical content plus immutable report metadata/children.
- [x] Database: `research_reports`.
- [x] RED: JSON source required, Markdown/checksums required, exact context, status
  vocabulary, bounded content, no public-publish/advice fields.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_research_report_aggregate.py`.
- [x] Expected RED: aggregate models are absent.
- [x] GREEN: strict immutable report contracts only.
- [x] GREEN command: same test.
- [x] Expected GREEN: valid aggregate passes and invalid shapes fail.
- [x] Commit: `feat: define immutable research reports`.

### Task 10 — Report version chain

- [x] Files: `tests/unit/test_report_version_chain.py`,
  `src/stock_research_agent/domain/reports/versioning.py`.
- [x] Function:
  `validate_report_successor(parent, child) -> None`;
  `next_report_version(parent) -> int`.
- [x] Database: `research_reports.previous_report_id`.
- [x] RED: one initial per Generation, +1 versions, same Generation/context,
  no self/cycle/fork, old version unchanged, PUBLISHABLE seal content identity.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_version_chain.py`.
- [x] Expected RED: chain validation absent.
- [x] GREEN: finite linear-chain validator.
- [x] GREEN command: same test.
- [x] Expected GREEN: all valid/invalid chains match.
- [x] Commit: `feat: enforce report version chains`.

### Task 11 — Report Section

- [x] Files: `tests/unit/test_report_sections.py`,
  `src/stock_research_agent/domain/reports/sections.py`.
- [x] Classes/function:
  `ReportSectionWrite`; `build_sections(template, manifest) -> tuple[ReportSectionDraft, ...]`.
- [x] Database: `report_sections`.
- [x] RED: closed 16 keys, exact template order/index, mandatory Data Quality/
  Limitations, explicit empty/PARTIAL/BLOCKED states, no invented content.
- [x] RED command: `uv run pytest -W error tests/unit/test_report_sections.py`.
- [x] Expected RED: builder absent.
- [x] GREEN: deterministic section skeleton.
- [x] GREEN command: same test.
- [x] Expected GREEN: order and status Golden expectations pass.
- [x] Commit: `feat: add deterministic report sections`.

### Task 12 — Report Block

- [x] Files: `tests/unit/test_report_blocks.py`,
  `src/stock_research_agent/domain/reports/blocks.py`.
- [x] Classes/function:
  `ReportBlockDraft`, `ReportBlockWrite`,
  `validate_report_block(ReportBlockDraft) -> None`.
- [x] Database: `report_blocks`.
- [x] RED: ten block types, stable key/index/checksum, factual location key,
  bounded payload, structural heading exception, immutable completed block.
- [x] RED command: `uv run pytest -W error tests/unit/test_report_blocks.py`.
- [x] Expected RED: Block schema/validator absent.
- [x] GREEN: strict atomic block contracts.
- [x] GREEN command: same test.
- [x] Expected GREEN: factual/structural cases classify correctly.
- [x] Commit: `feat: add atomic report blocks`.

### Task 13 — Claim Binding

- [x] Files: `tests/unit/test_report_claim_bindings.py`,
  `src/stock_research_agent/domain/reports/bindings.py`.
- [x] Class/function:
  `ReportClaimBindingWrite`,
  `validate_claim_binding(block, claim, binding, manifest) -> None`.
- [x] Database: `report_claim_bindings`.
- [x] RED: required factual binding, location uniqueness, support-state/section-role
  matrix, real/synthetic isolation, duplicate rejection.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_claim_bindings.py`.
- [x] Expected RED: binding validator absent.
- [x] GREEN: exact support and location rules.
- [x] GREEN command: same test.
- [x] Expected GREEN: normal, PARTIAL, conflict, unsupported, blocked cases pass.
- [x] Commit: `feat: bind report blocks to claims`.

### Task 14 — Evidence Binding

- [x] Files: `tests/unit/test_report_evidence_bindings.py`,
  `src/stock_research_agent/domain/reports/bindings.py`.
- [x] Class/function:
  `ReportEvidenceBindingWrite`,
  `validate_evidence_binding(claim_binding, link, evidence, manifest) -> None`.
- [x] Database: `report_evidence_bindings`.
- [x] RED: exact Claim-Evidence Link, valid Run/Security/Snapshot/as-of/checksum,
  primary Evidence status, duplicate/unreachable/future/synthetic rejection.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_evidence_bindings.py`.
- [x] Expected RED: exact-chain checks absent.
- [x] GREEN: Stage 7 link-backed validation only.
- [x] GREEN command: same test.
- [x] Expected GREEN: cross-context and invented bindings fail.
- [x] Commit: `feat: bind report claims to evidence`.

### Task 15 — Citation Binding

- [x] Files: `tests/unit/test_report_citation_bindings.py`,
  `src/stock_research_agent/domain/reports/bindings.py`.
- [x] Class/function:
  `ReportCitationBindingWrite`,
  `validate_citation_binding(evidence_binding, citation, document, verification, manifest) -> None`.
- [x] Database: `report_citation_bindings`.
- [x] RED: exact Citation/Evidence/DocumentVersion, VALID status, publication/as-of,
  locator/excerpt/checksum, 1,000 bound, no rewrite/path/secret/hidden HTML.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_citation_bindings.py`.
- [x] Expected RED: Citation binding checks absent.
- [x] GREEN: read-only exact anchor projection.
- [x] GREEN command: same test.
- [x] Expected GREEN: valid shortest excerpt passes; invalid/future/unknown fails.
- [x] Commit: `feat: bind reports to verified citations`.

### Task 16 — Deterministic JSON Renderer

- [x] Files: `tests/unit/test_deterministic_report_renderer.py`,
  `src/stock_research_agent/domain/reports/rendering.py`.
- [x] Signature: approved `DeterministicReportRenderer.render(...)`.
- [x] Input/output: Verified Manifest context to `RenderedReportDraft`.
- [x] Database: none; persistence occurs in Task 37 composition.
- [x] RED: identical input equality, section/Claim stable order, support
  classification, no free prose, no Tool/model/latest access.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_deterministic_report_renderer.py`.
- [x] Expected RED: renderer absent.
- [x] GREEN: render only approved statement templates and exact bindings.
- [x] GREEN command: same test.
- [x] Expected GREEN: deterministic structured content passes.
- [x] Commit: `feat: render deterministic structured reports`.

### Task 17 — Deterministic Markdown Renderer

- [x] Files: `tests/unit/test_report_markdown_renderer.py`,
  `src/stock_research_agent/domain/reports/markdown.py`.
- [x] Signature:
  `DeterministicMarkdownRenderer.render(StructuredReportContent) -> RenderedMarkdown`.
- [x] Database: persisted `research_reports.markdown_content`.
- [x] RED: JSON-only input, no source repositories, same sections/blocks/references/
  values/statuses, escaped Markdown/HTML, LF plus one trailing newline.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_markdown_renderer.py`.
- [x] Expected RED: projection absent.
- [x] GREEN: pure structured-content traversal.
- [x] GREEN command: same test.
- [x] Expected GREEN: JSON/Markdown parity checks pass.
- [x] Commit: `feat: project report json to markdown`.

### Task 18 — zh-CN templates

- [x] Files: `tests/golden/report_templates_zh_cn.json`,
  `tests/unit/test_report_locale_zh_cn.py`,
  `src/stock_research_agent/domain/reports/templates.py`.
- [x] Interface: fixed `zh-CN` template records for all allowed report types.
- [x] Database: `report_template_versions`.
- [x] RED: independent labels, qualified PARTIAL language, mandatory disclosures,
  exact section order, no promotional/advice language.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_locale_zh_cn.py`.
- [x] Expected RED: locale templates absent.
- [x] GREEN: add literal data-only templates.
- [x] GREEN command: same test.
- [x] Expected GREEN: checked-in Golden template contract passes.
- [x] Commit: `feat: add zh cn report templates`.

### Task 19 — en-US templates

- [x] Files: `tests/golden/report_templates_en_us.json`,
  `tests/unit/test_report_locale_en_us.py`,
  `src/stock_research_agent/domain/reports/templates.py`.
- [x] Interface: fixed `en-US` template records.
- [x] Database: `report_template_versions`.
- [x] RED: English labels/qualifiers, same semantic keys/order, original names/codes/
  excerpts preserved, no translation-service claim.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_locale_en_us.py`.
- [x] Expected RED: locale templates absent.
- [x] GREEN: add matching literal templates.
- [x] GREEN command: same test.
- [x] Expected GREEN: semantic parity with zh-CN and Golden labels pass.
- [x] Commit: `feat: add en us report templates`.

### Task 20 — Numeric, unit, currency, and period formatting

- [x] Files: `tests/unit/test_report_financial_formatting.py`,
  `src/stock_research_agent/domain/reports/formatting.py`.
- [x] Functions:
  `format_report_value(ReportNumericValue, ReportLocale) -> FormattedValue`,
  `validate_financial_display(claim, evidence) -> None`.
- [x] Database: none.
- [x] RED: Decimal precision, CNY/USD no conversion, percent, N/M, NULL, ZERO,
  BLOCKED, TTM method, A-share cumulative basis, non-calendar/52–53-week fiscal.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_financial_formatting.py`.
- [x] Expected RED: formatter absent.
- [x] GREEN: exact string formatting without float.
- [x] GREEN command: same test.
- [x] Expected GREEN: independent expected strings pass.
- [x] Commit: `feat: preserve report financial semantics`.

### Task 21 — Stable reference numbering

- [x] Files: `tests/unit/test_report_reference_allocator.py`,
  `src/stock_research_agent/domain/reports/references.py`.
- [x] Signature:
  `ReportReferenceAllocator.allocate(StructuredReportContent) -> ReferenceAllocation`.
- [x] Database: visible references in binding tables.
- [x] RED: first appearance, reuse, five prefixes, UUID independence, duplicate/
  orphan/unused rejection, stable revision renumber.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_reference_allocator.py`.
- [x] Expected RED: allocator absent.
- [x] GREEN: deterministic ordered traversal and bijection validator.
- [x] GREEN command: same test.
- [x] Expected GREEN: independent reference maps pass.
- [x] Commit: `feat: allocate stable report references`.

### Task 22 — Claim index

- [x] Files: `tests/unit/test_report_claim_index.py`,
  `src/stock_research_agent/domain/reports/appendices.py`.
- [x] Function:
  `build_claim_index(content, claims, bindings) -> ReportBlockDraft`.
- [x] Database: `report_blocks`, `report_claim_bindings`.
- [x] RED: all used Claims once, support state visible, unsupported/conflicting/
  blocked classification, no unused Claim.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_claim_index.py`.
- [x] Expected RED: index builder absent.
- [x] GREEN: stable index rows from existing bindings only.
- [x] GREEN command: same test.
- [x] Expected GREEN: exact rows/order pass.
- [x] Commit: `feat: add report claim index`.

### Task 23 — Evidence appendix

- [x] Files: `tests/unit/test_report_evidence_appendix.py`,
  `src/stock_research_agent/domain/reports/appendices.py`.
- [x] Function:
  `build_evidence_appendix(manifest, bindings) -> ReportBlockDraft`.
- [x] Database: `report_blocks`, `report_evidence_bindings`.
- [x] RED: EV/MET/LIM/CON rows, exact code/value/unit/period/as-of/source/calculation/
  formula/status, no payload/path/unused row.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_evidence_appendix.py`.
- [x] Expected RED: appendix absent.
- [x] GREEN: bounded DTO projection from bound Evidence only.
- [x] GREEN command: same test.
- [x] Expected GREEN: Golden rows and safe-field checks pass.
- [x] Commit: `feat: add report evidence appendix`.

### Task 24 — Citation appendix

- [x] Files: `tests/unit/test_report_citation_appendix.py`,
  `src/stock_research_agent/domain/reports/appendices.py`.
- [x] Function:
  `build_citation_appendix(manifest, bindings, max_excerpt_length) -> ReportBlockDraft`.
- [x] Database: `report_blocks`, `report_citation_bindings`.
- [x] RED: CIT rows, exact title/type/version/published/period/locator/original excerpt/
  VALID/trust, shortest bounded excerpt, no reconstructed document/hidden HTML/path.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_citation_appendix.py`.
- [x] Expected RED: appendix absent.
- [x] GREEN: one row per used verified Citation.
- [x] GREEN command: same test.
- [x] Expected GREEN: copyright/security bounds pass.
- [x] Commit: `feat: add bounded citation appendix`.

### Task 25 — Report checksums and JSON/Markdown consistency

- [x] Files: `tests/unit/test_report_checksums.py`,
  `src/stock_research_agent/domain/reports/checksums.py`.
- [x] Functions:
  `structured_report_checksum`, `markdown_checksum`, `combined_report_checksum`,
  `verify_report_projection`.
- [x] Database: checksum columns on `research_reports`/blocks.
- [x] RED: all 15 JSON/Markdown parity properties, manual Markdown modification,
  block/reference/value/status change sensitivity, audit ID/time exclusion.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_checksums.py`.
- [x] Expected RED: checksum/projection verifier absent.
- [x] GREEN: canonical semantic payload and deterministic parity traversal.
- [x] GREEN command: same test.
- [x] Expected GREEN: hand-calculated hashes pass.
- [x] Commit: `feat: verify report content checksums`.

### Task 26 — Report idempotency

- [x] Files: `tests/unit/test_report_idempotency.py`,
  `src/stock_research_agent/domain/reports/idempotency.py`.
- [x] Functions:
  `report_request_idempotency_key`, `report_generation_idempotency_key`,
  `is_reusable_generation_run`.
- [x] Database: unique keys on Request/Generation Run.
- [x] RED: Manifest, Package/set checksums, Policy/template/renderer/locale/type/
  sections/options sensitivity; FAILED/BLOCKED/partial reuse rules.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_idempotency.py`.
- [x] Expected RED: keys absent.
- [x] GREEN: canonical keys and explicit reusable states.
- [x] GREEN command: same test.
- [x] Expected GREEN: independent hashes pass.
- [x] Commit: `feat: add report generation idempotency`.

### Task 27 — Runtime Reflection Policy

- [x] Files: `tests/unit/test_runtime_reflection_policy.py`,
  `src/stock_research_agent/domain/reports/reflection_policy.py`.
- [x] Classes/services:
  `RuntimeReflectionPolicyRecord`,
  `RuntimeReflectionPolicySeedService.seed_v1()`.
- [x] Database: `runtime_reflection_policies`.
- [x] RED: exact check set, HIGH threshold, 2/1 limits, model false, Gate required,
  immutable/idempotent/incompatible seed.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_runtime_reflection_policy.py`.
- [x] Expected RED: Policy absent.
- [x] GREEN: fixed checksummed Policy.
- [x] GREEN command: same test.
- [x] Expected GREEN: exact defaults and no expansion pass.
- [x] Commit: `feat: add runtime reflection policy`.

### Task 28 — Reflection Run

- [x] Files: `tests/unit/test_report_reflection_runs.py`,
  `src/stock_research_agent/domain/reports/reflection.py`.
- [x] Classes: Run write/record/completion/result; finite Run state helper.
- [x] Database: `report_reflection_runs`.
- [x] RED: round 1/2 only, RUNNING→four terminals, exact Report checksum/Policy/
  engine, terminal immutability, same-report-round uniqueness.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_reflection_runs.py`.
- [x] Expected RED: lifecycle absent.
- [x] GREEN: strict schemas and transition map.
- [x] GREEN command: same test.
- [x] Expected GREEN: matrix passes.
- [x] Commit: `feat: add report reflection runs`.

### Task 29 — Reflection Finding

- [x] Files: `tests/unit/test_report_reflection_findings.py`,
  `src/stock_research_agent/domain/reports/reflection.py`.
- [x] Classes: Finding category/severity/write/record.
- [x] Database: `report_reflection_findings`.
- [x] RED: closed categories, exact linked IDs, bounded safe description/remediation,
  append-only semantics, counts by severity.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_reflection_findings.py`.
- [x] Expected RED: Finding schema absent.
- [x] GREEN: strict finding contracts and count helper.
- [x] GREEN command: same test.
- [x] Expected GREEN: all required categories validate.
- [x] Commit: `feat: add append only reflection findings`.

### Task 30 — Deterministic Reflection rules engine

- [x] Files: `tests/unit/test_report_reflection_engine.py`,
  `src/stock_research_agent/domain/reports/reflection.py`.
- [x] Signature: approved `DeterministicReportReflectionEngine.reflect(...)`.
- [x] Database: Reflection Run/Finding persistence occurs in Task 37.
- [x] RED: all 40 design checks, contextual language classification, excerpt quote
  exception, forbidden advice, no Tool/model/network, deterministic findings/order.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_reflection_engine.py`.
- [x] Expected RED: engine absent.
- [x] GREEN: closed rule registry with fixed minimum severities.
- [x] GREEN command: same test.
- [x] Expected GREEN: hand-written Finding sets pass.
- [x] Commit: `feat: reflect on reports deterministically`.

### Task 31 — Deterministic Revision Engine

- [x] Files: `tests/unit/test_report_revision_engine.py`,
  `src/stock_research_agent/domain/reports/revision.py`.
- [x] Signature: approved `DeterministicReportRevisionEngine.revise(...)`.
- [x] Database: target Report and `report_revision_runs`.
- [x] RED: every allowed action, all prohibited fact/source/context mutations,
  unresolved findings retained, no provider/Tool/model, deterministic new aggregate.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_revision_engine.py`.
- [x] Expected RED: engine absent.
- [x] GREEN: closed subtractive/disclosure action dispatcher.
- [x] GREEN command: same test.
- [x] Expected GREEN: source unchanged, target only allowed deltas.
- [x] Commit: `feat: revise reports without creating facts`.

### Task 32 — Revision Run

- [x] Files: `tests/unit/test_report_revision_runs.py`,
  `src/stock_research_agent/domain/reports/revision.py`.
- [x] Classes: Revision Run write/record/completion/result/state helper.
- [x] Database: `report_revision_runs`.
- [x] RED: round exactly 1, valid Round 1 source, one target, terminal immutability,
  applied/unresolved IDs, failed no target, no second revision.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_revision_runs.py`.
- [x] Expected RED: lifecycle absent.
- [x] GREEN: strict Run schemas and transition rules.
- [x] GREEN command: same test.
- [x] Expected GREEN: finite matrix passes.
- [x] Commit: `feat: record deterministic report revisions`.

### Task 33 — Second-round Reflection

- [x] Files: `tests/unit/test_report_reflection_round_two.py`,
  `src/stock_research_agent/domain/reports/reflection.py`.
- [x] Function:
  `validate_reflection_predecessor(report, round_number, prior, revision) -> None`.
- [x] Database: `report_reflection_runs`.
- [x] RED: Round 2 requires completed Round 1, targets revision when present,
  accepts same content when no revision, rejects round skipping/reuse/child bypass.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_reflection_round_two.py`.
- [x] Expected RED: predecessor validation absent.
- [x] GREEN: exact finite predecessor rules.
- [x] GREEN command: same test.
- [x] Expected GREEN: allowed two paths pass; all bypasses fail.
- [x] Commit: `feat: enforce second report reflection round`.

### Task 34 — Report Release Gate

- [x] Files: `tests/unit/test_report_release_gate.py`,
  `src/stock_research_agent/domain/reports/release_gate.py`.
- [x] Signature: approved `ReportReleaseGate.evaluate(...)`.
- [x] Database: `report_release_gates`, optional PUBLISHABLE report seal.
- [x] RED: PUBLISHABLE/PARTIAL/BLOCKED/FAILED, all 18 requirements, internal release
  semantics, second round mandatory, BLOCKED Package always BLOCKED, no public flag.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_release_gate.py`.
- [x] Expected RED: Gate absent.
- [x] GREEN: pure deterministic decision and content-identical seal draft.
- [x] GREEN command: same test.
- [x] Expected GREEN: independent decision matrix passes.
- [x] Commit: `feat: gate reports for internal release`.

### Task 35 — Ten read-only Report query Tools

- [x] Files: `tests/contract/test_report_tools.py`,
  `src/stock_research_agent/domain/reports/queries.py`,
  `src/stock_research_agent/tools/schemas_reports.py`,
  `src/stock_research_agent/tools/reports.py`,
  `src/stock_research_agent/tools/registry.py`,
  `docs/tool-catalog-stage-8-final.json`.
- [x] Classes: strict input/output DTOs, `ReportQueryService`, and
  `ReportReadTool`.
- [x] Database: read-only projections across Stage 8 tables.
- [x] RED: exact ten names/version, permission/read/write/network flags, pagination,
  safe missing resource, no generation/reflection/revision/Gate/model/path/body.
- [x] RED command:
  `uv run pytest -W error tests/contract/test_report_tools.py`.
- [x] Expected RED: registrations absent.
- [x] GREEN: separate report query registry; preserve Stage 7 22-Tool execution
  catalog/checksum.
- [x] GREEN command: same test plus Stage 7 Tool contracts.
- [x] Expected GREEN: all contracts pass and old catalog manifest is unchanged.
- [x] Commit: `feat: add read only report query tools`.

### Task 36 — Ten GET Report API routes

- [x] Files: `tests/contract/test_report_api_contract.py`,
  `src/stock_research_agent/api/routes/reports.py`,
  API dependency/router files.
- [x] Interface: exact ten GET routes from the design, no write route.
- [x] Database: query-only Session scope.
- [x] RED: DTOs, 404/422, bounded pagination, request ID, OpenAPI, persisted Markdown,
  no implicit write/model/latest/path/secret.
- [x] RED command:
  `uv run pytest -W error tests/contract/test_report_api_contract.py`.
- [x] Expected RED: routes absent.
- [x] GREEN: thin `ReportQueryService` adapters.
- [x] GREEN command: same test.
- [x] Expected GREEN: OpenAPI exposes only ten GET Report routes.
- [x] Commit: `feat: expose read only report api`.

### Task 37 — Explicit Report CLI and application services

- [x] Files: `tests/unit/test_report_cli.py`,
  `src/stock_research_agent/domain/reports/application.py`,
  `src/stock_research_agent/domain/reports/queries.py`,
  `src/stock_research_agent/cli_reports.py`, `src/stock_research_agent/cli.py`.
- [x] Classes: four approved write services, `ReportQueryService`; explicit
  seed/list/generate/reflect/revise/release-check/read/export commands.
- [x] Database: transaction ownership is expressed through injected unit-of-work
  ports; the real PostgreSQL CLI roundtrip is deferred to Task 39 after migration.
- [x] RED: single responsibility, predecessor IDs, rollback, exit codes, JSON/human,
  approved-root export/no overwrite, no automatic pipeline/latest/Tool/model/network.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_cli.py`.
- [x] Expected RED: CLI group/services absent.
- [x] GREEN: explicit compositions using existing Session factory and safe paths.
- [x] GREEN command: same test.
- [x] Expected GREEN: command contracts and rollback calls pass with deterministic
  in-memory ports; export bytes match persisted checksum.
- [x] Commit: `feat: add explicit verifiable report cli`.

### Task 38 — Stage 8 migration

- [x] Files: `tests/integration/test_report_migrations.py`,
  `migrations/versions/0007_create_verifiable_reports_and_reflection.py`.
- [x] Interface: Alembic `upgrade()` and `downgrade()`.
- [x] Database: all 15 reviewed tables, named FKs/CHECKs/uniques/indexes/triggers.
- [x] RED: migrate 0006→0007, model parity, immutability, lineage/version/round/Gate
  guards, downgrade→0006→upgrade, no Stage 2–7 change.
- [x] RED command:
  `uv run pytest -W error tests/integration/test_report_migrations.py`.
- [x] Expected RED: revision/tables absent.
- [x] GREEN: schema-only migration and complete reverse-order downgrade.
- [x] GREEN command: same test.
- [x] Expected GREEN: isolated PostgreSQL cycle ends at 0007.
- [x] Commit: `feat: migrate verifiable report schema`.

### Task 39 — Full PostgreSQL repository and lifecycle

- [x] Files: `tests/integration/test_report_repository_postgres.py`,
  `tests/integration/test_report_postgres.py`,
  `tests/integration/test_report_cli_postgres.py`,
  `src/stock_research_agent/db/repositories/reports.py`.
- [x] Interfaces: all ten repository protocols in section 4.
- [x] Database: all Stage 8 tables.
- [x] RED: CRUD boundaries, exact Manifest read, all constraints/triggers,
  concurrent generate/reflect convergence, rollback, version chain, terminal
  immutability, explicit CLI transactions, development/test isolation, no open
  transaction/schema pollution.
- [x] RED command:
  `uv run pytest -W error tests/integration/test_report_repository_postgres.py tests/integration/test_report_postgres.py tests/integration/test_report_cli_postgres.py`.
- [x] Expected RED: unimplemented repository/lifecycle assertions fail.
- [x] GREEN: parameterized SQLAlchemy repositories, row locks, unique-key
  convergence, no sleep/retry loop.
- [x] GREEN command: same tests.
- [x] Expected GREEN: real PostgreSQL lifecycle passes.
- [x] Commit: `feat: persist verifiable report lifecycles`.

### Task 40 — Industrial FII honest-degradation flow

- [x] Files: `tests/integration/test_report_industrial_fii.py`.
- [x] Interface: `ReportGenerationService` through Reflection/Revision/Gate against
  current persisted `601138.SH` Package.
- [x] Database: existing real Stage 7 records plus Stage 8 derived records.
- [x] RED: exact context, no body/financial fabrication, blocked/no-evidence document,
  partial/blocked financial, no prohibited Claims/advice, all facts bound, Gate
  PARTIAL/BLOCKED.
- [x] RED command:
  `uv run pytest -W error tests/integration/test_report_industrial_fii.py`.
- [x] Expected RED: first missing/incorrect composition behavior fails.
- [x] GREEN: smallest composition/template correction; no data or Fixture creation.
- [x] GREEN command: same test.
- [x] Expected GREEN: honest PARTIAL/BLOCKED flow passes.
- [x] Commit: `test: verify industrial fii report boundaries`.

### Task 41 — Micron honest-degradation flow

- [x] Files: `tests/integration/test_report_micron.py`.
- [x] Interface: full fixed report workflow against current persisted `MU` Package.
- [x] Database: current real Stage 7 records plus Stage 8 derived rows.
- [x] RED: SEC metadata not body, document BLOCKED, no HBM/inventory/data-center/
  guidance/risk assertions, all facts bound, no advice, Gate PARTIAL/BLOCKED.
- [x] RED command:
  `uv run pytest -W error tests/integration/test_report_micron.py`.
- [x] Expected RED: metadata promotion or incorrect completeness fails.
- [x] GREEN: smallest composition/template correction; no filing body or fact added.
- [x] GREEN command: same test.
- [x] Expected GREEN: honest Micron degradation passes.
- [x] Commit: `test: verify micron report boundaries`.

### Task 42 — Isolated Synthetic complete flow

- [x] Files: `tests/integration/test_report_synthetic_flow.py`,
  `.gitattributes`,
  `tests/fixtures/reports/synthetic_report_input.json`,
  manifest and independent zh-CN/en-US JSON/Markdown expected files.
- [x] Interface: fixed full workflow and both locales on neutral Synthetic Security.
- [x] Database: isolated test rows only.
- [x] RED: four markers, complete bindings/appendices, Round1→Revision→Round2→
  PUBLISHABLE internal Gate, idempotency, version/checksum, no real-company IDs.
- [x] RED command:
  `uv run pytest -W error tests/integration/test_report_synthetic_flow.py`.
- [x] Expected RED: fixture/workflow absent.
- [x] GREEN: add `*.json text eol=lf` and `*.md text eol=lf` before the fixture
  files are staged, then add test-only fixture/provider/policy and minimum
  composition. Do not change global Git settings or renormalize unrelated paths.
- [x] GREEN command: same test.
- [x] Expected GREEN: Synthetic engineering PUBLISHABLE passes and real-company
  isolation assertions pass.
- [x] Commit: `test: add isolated synthetic report flow`.

### Task 43 — Fixture LF and cross-platform checksums

- [x] Files: `tests/unit/test_report_fixture_integrity.py`,
  actual files in `tests/fixtures/reports`.
- [x] Function:
  fixture integrity helper reads Git Blob/worktree/Manifest bytes.
- [x] Database: none.
- [x] RED: integrity verifier is absent, so Blob/worktree/Manifest and CRLF
  guarantees are not yet enforced even though Task 42 added the rules at creation.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_fixture_integrity.py`.
- [x] Expected RED: missing integrity contract/helper assertions.
- [x] GREEN: verify the existing exact `*.json`/`*.md` LF rules and manifests
  against source bytes; correct only a demonstrably wrong new fixture before it is
  used by other tests; no repository renormalization.
- [x] GREEN command: same test.
- [x] Expected GREEN: all three checksums match and CRLF count is zero.
- [x] Commit: `fix: enforce stable report fixture line endings`.

### Task 44 — Report security and provider isolation

- [x] Files: `tests/unit/test_report_security.py`,
  `tests/unit/test_report_no_model.py`,
  `tests/support/report_providers.py`,
  `src/stock_research_agent/domain/reports/providers.py`.
- [x] Interfaces: approved `NarrativeProvider`, `ReflectionProvider`; blocked model
  metadata; scripted test-only providers.
- [x] Database: none.
- [x] RED: template/expression/file/env/URL/Shell/SQL/path/Markdown/HTML/ID/context/
  round/document injection, secret/path leakage, production scripted/model enabling.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_report_security.py tests/unit/test_report_no_model.py`.
- [x] Expected RED: provider ports/guards absent.
- [x] GREEN: blocked production metadata and minimum boundary hardening.
- [x] GREEN command: same tests.
- [x] Expected GREEN: offline tests pass, model consumption zero.
- [x] Commit: `test: enforce report security boundaries`.

### Task 45 — Stage 8 documentation

- [x] Files: all report documentation paths from the approved design,
  shared API/database/testing/security/risk/open-questions/README,
  `tests/unit/test_stage8_documentation.py`.
- [x] Contract: Package-only input, JSON source, Markdown projection, bindings,
  states, 2/1 runtime limits, internal release semantics, synthetic/real limits,
  no model/Tool/advice/PDF/frontend/MCP/Stage9.
- [x] Database: documentation of 15 tables and rollback.
- [x] RED: required files/phrases/commands absent or stale.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_stage8_documentation.py`.
- [x] Expected RED: documentation contract failures list missing content.
- [x] GREEN: write accurate bounded documentation only.
- [x] GREEN command: same test plus Stage 7 documentation regression.
- [x] Expected GREEN: documentation matches code and commands.
- [x] Commit: `docs: document verifiable reports and reflection`.

### Task 46 — Development Reflection Round 1

- [x] Files: `docs/reflection/stage-8-round-1.md`,
  `tests/unit/test_stage8_reflection_documents.py`.
- [x] Interface: ten-role finding table with ID/role/severity/description/evidence/
  affected files/fix/blocking/status.
- [x] Database: audit model/migration/repository parity.
- [x] RED: document contract fails before Round 1 exists.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_stage8_reflection_documents.py`.
- [x] Expected RED: missing Round 1 artifact.
- [x] GREEN: perform actual architecture/finance/Citation/runtime Reflection/
  Revision/Gate/security/PostgreSQL/fixture/testing review.
- [x] GREEN command: same test.
- [x] Expected GREEN: every finding is complete; critical/high fixes are assigned.
- [x] Commit: `docs: record stage 8 reflection round 1`.

### Task 47 — Fix all CRITICAL and HIGH findings

- [x] Files: every exact path named by Round 1 and focused regression tests named in
  each finding.
- [x] Interface: unchanged unless Round 1 proves an approved contract inconsistency;
  any correction is recorded.
- [x] Database: only finding-specific Stage 8 changes, never Stage 2–7 mutation.
- [x] RED: one focused regression per critical/high finding, observed failing for
  the recorded defect.
- [x] RED command: exact node IDs recorded beside each finding.
- [x] Expected RED: each test fails for the stated behavior.
- [x] GREEN: minimum fix, no scope expansion.
- [x] GREEN command: each focused test plus affected suite.
- [x] Expected GREEN: all critical/high regressions pass.
- [x] Commit: `fix: resolve stage 8 critical and high findings`.

### Task 48 — Development Reflection Round 2

- [x] Files: `docs/reflection/stage-8-round-2.md`,
  `tests/unit/test_stage8_reflection_documents.py`.
- [x] Interface: fixed 36-check verification matrix.
- [x] Database: records real migration/PostgreSQL evidence.
- [x] RED: Round 2 document absent or any required check lacks evidence.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_stage8_reflection_documents.py`.
- [x] Expected RED: missing/incomplete Round 2.
- [x] GREEN: rerun all required focused checks and record results.
- [x] GREEN command: documentation test plus Round 1 regression set.
- [x] Expected GREEN: unresolved critical=0 and high=0.
- [x] Commit: `docs: complete stage 8 reflection round 2`.

### Task 49 — Stage 8 implementation report

- [x] Files: `docs/stage-8-implementation-report.md`,
  `tests/unit/test_stage8_implementation_report.py`.
- [x] Interface: required 57-section factual report with actual commands/counts,
  provider/business limits, rollback, Git state, and `CONDITIONAL GO`.
- [x] Database: actual migration and PostgreSQL results.
- [x] RED: report absent or required fields/status distinctions missing.
- [x] RED command:
  `uv run pytest -W error tests/unit/test_stage8_implementation_report.py`.
- [x] Expected RED: missing report.
- [x] GREEN: populate only verified results, no copied historical claims.
- [x] GREEN command: same test.
- [x] Expected GREEN: report contract passes.
- [x] Commit: `docs: report stage 8 implementation`.

### Task 50 — Final acceptance and implementation commit

- [x] Files: only verified fixes/report count updates arising from final checks.
- [x] Interface: no new capability.
- [x] Database: both databases end at 0007; no residual transaction/schema pollution.
- [x] RED: any final failure is reproduced with a focused regression before a fix.
- [x] Commands, sequentially:
  - `uv sync`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy src`
  - `uv run pytest -W error`
  - Alembic current/upgrade/downgrade/upgrade/current
- [x] Expected: zero failed/errors/skipped/warnings; all Stage 2–7 regressions; no
  model/network/residual pytest; 0007 head.
- [x] GREEN: inspect changed paths, secrets, fixtures, binaries, local DB/Blob/path
  leaks, and exact Stage 8 scope; update only true final evidence in report.
- [x] Commit:
  `feat: add verifiable research reports and runtime reflection`.
- [x] Preserve the branch, do not merge, and offer only the three approved local
  finishing choices.

## 6. Plan self-check

Before Task 0, run a script that constructs the five forbidden placeholder tokens
from string fragments and fails if any complete token occurs. It also validates:

- [x] Prompt coverage: all 29 supplemental sections map to Tasks 0–50.
- [x] Design coverage: all 40 approved design sections map to Tasks.
- [x] Type consistency: every interface is defined in section 4 or an earlier Task.
- [x] Database consistency: 15 reviewed tables appear in model, migration, repository,
  query, and PostgreSQL Tasks; Manifest is intentionally embedded in Request.
- [x] Manifest integrity: actual ordered inputs only; no latest data, cross-context,
  future, synthetic contamination, invented or unused records.
- [x] Binding integrity: Block→Claim→Stage 7 Link→Evidence→Citation/lineage.
- [x] JSON authority: Markdown has only persisted structured content as input.
- [x] State consistency: Generation, Report version, Reflection, Revision, and Gate
  states match application and database rules.
- [x] Reflection limit: exactly two rounds maximum.
- [x] Revision limit: exactly one round maximum.
- [x] Gate consistency: internal PUBLISHABLE only after Round 2 and all checks.
- [x] Tool/catalog consistency: exactly ten report query Tools; Stage 7 22-Tool
  execution catalog unchanged.
- [x] API consistency: exactly ten report GET routes and no report write route.
- [x] CLI consistency: each write is explicit and transactional.
- [x] Fixture consistency: LF rules are added at fixture creation, not after failure.
- [x] Real-company consistency: Industrial FII and Micron remain honest
  PARTIAL/BLOCKED; Synthetic stays neutral/test-only.
- [x] Scope consistency: no model, Tool research, refresh, advice, public publish,
  PDF, frontend, MCP, remote/PR, Stage 9.
- [x] Task completeness: every Task names paths, interfaces, input/output or contract,
  database impact, RED command/reason, minimum GREEN, GREEN command/result, and
  commit.
- [x] Dependency order: no Task consumes an undefined production interface.

## 7. Completion boundary

After Task 50:

- keep `stage-8/verifiable-report-reflection`;
- do not merge or delete it;
- do not create a Draft PR or configure a remote;
- do not enter Stage 9;
- report the real Stage 8 status and current BLOCKED providers/evidence;
- offer exactly:
  - Merge back to main locally
  - Keep branch as-is
  - Discard this work
