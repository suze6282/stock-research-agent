# Stage 10 Gate A Implementation Plan

Status: self-checked and approved for Gate A execution

Branch: `stage-10/controlled-live-evidence`

Approved design:

- `docs/specs/stage-10-controlled-live-evidence-design.md`
- `docs/live-authorization-matrix.md`
- `docs/manual-evidence-import-policy.md`
- `docs/real-company-research-runbook.md`

## 1. Fixed execution rules

Every task follows `RED -> minimum implementation -> GREEN -> focused regression
-> independent commit`. No task may delete or weaken an older test. PostgreSQL
tests use `stock_research_test`, never SQLite or the development database.

Boundary notation in every task:

- `A; N/N/N` means Gate A, no network/DNS/socket, no Provider Credential/contact
  resolution, and no real company file.
- All created authorization, evidence, Snapshot, Agent and Report records are
  neutral `SYNTHETIC_TEST_ONLY` or safe offline test data.
- Gate B execution is absent. The SEC run command exists only as a fail-closed
  orchestration surface and cannot construct transport without a matching test
  authorization and injected Fake Transport.

Global quality command after each task group:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

## 2. Interface and type registry

The following names are defined before they are referenced by task rows. All
request/result schemas are frozen Pydantic models; all datetimes are aware UTC;
IDs are UUIDs; checksums are lowercase SHA-256.

```python
class LiveAuthorizationService:
    def create(self, value: LiveAuthorizationGrantWrite) -> LiveAuthorizationGrantRecord: ...
    def append_event(self, value: LiveAuthorizationEventWrite) -> LiveAuthorizationState: ...
    def activate(self, value: ActivateAuthorizationRequest) -> LiveAuthorizationState: ...
    def revoke(self, value: RevokeAuthorizationRequest) -> LiveAuthorizationState: ...
    def reserve(self, value: ConsumptionReservationRequest) -> ConsumptionReservation: ...
    def settle(self, value: ConsumptionSettlementRequest) -> LiveAuthorizationConsumptionRecord: ...

class ExecutionApprovalService:
    def create(self, value: LiveExecutionApprovalWrite) -> LiveExecutionApprovalRecord: ...
    def validate(self, value: ValidateExecutionApprovalRequest) -> ExecutionApprovalDecision: ...

class ManualEvidenceService:
    def plan(self, value: ManualEvidenceImportPlanRequest) -> ManualEvidenceImportPlan: ...
    def receive(self, value: ManualEvidenceReceiveRequest) -> ManualEvidenceImportRecord: ...
    def quarantine(self, value: ManualEvidenceQuarantineRequest) -> ManualEvidenceQuarantineResult: ...
    def validate(self, value: ManualEvidenceValidationRequest) -> ManualEvidenceValidationResult: ...
    def review(self, value: ManualEvidenceReviewRequest) -> ManualEvidenceReviewRecord: ...
    def ingest(self, value: ManualEvidenceIngestRequest) -> EvidenceIngestionResult: ...

class EvidenceManifestService:
    def create(self, value: EvidenceIngestionManifestWrite) -> EvidenceIngestionManifestRecord: ...
    def verify(self, value: VerifyEvidenceManifestRequest) -> EvidenceManifestDecision: ...

class SnapshotFromIngestionService:
    def plan(self, value: SnapshotFromIngestionPlanRequest) -> SnapshotFromIngestionPlan: ...
    def create(self, value: CreateSnapshotFromIngestionRequest) -> SnapshotBuildResult: ...

class OfflineResearchPipelineService:
    def plan_agent(self, value: AgentRunFromSnapshotPlanRequest) -> AgentRunPlan: ...
    def run_agent(self, value: RunAgentFromSnapshotRequest) -> ResearchRunResult: ...
    def plan_report(self, value: ReportFromPackagePlanRequest) -> ReportGenerationPlan: ...
    def generate_report(self, value: GenerateReportFromPackageRequest) -> ReportPipelineResult: ...

class RealCompanyValidationService:
    def create(self, value: RealCompanyValidationRunWrite) -> RealCompanyValidationRunRecord: ...
    def append_check(self, value: EndToEndValidationCheckWrite) -> EndToEndValidationCheckRecord: ...

class EvidenceRetentionService:
    def plan(self, value: EvidenceRetentionPlanRequest) -> EvidenceRetentionPlan: ...
    def execute(self, value: ExecuteEvidenceRetentionRequest) -> EvidenceRetentionActionRecord: ...

class LiveIncidentService:
    def open(self, value: LiveIncidentWrite) -> LiveIncidentRecord: ...
    def append_event(self, value: LiveIncidentEventWrite) -> LiveIncidentState: ...
```

Repository ports are defined in
`src/stock_research_agent/domain/live_evidence/repositories.py`; PostgreSQL
implementations are in `src/stock_research_agent/db/repositories/live_evidence.py`.
They accept caller-owned `Session` objects and never open a Session, file or
network transport.

## 3. Database registry

Migration `0009_controlled_live_evidence` creates:

1. `live_authorization_grants`;
2. `live_authorization_events`;
3. `live_authorization_consumptions`;
4. `live_execution_approvals`;
5. `manual_evidence_import_requests`;
6. `manual_evidence_source_declarations`;
7. `manual_evidence_validations`;
8. `manual_evidence_reviews`;
9. `evidence_ingestion_manifests`;
10. `ingestion_to_snapshot_bindings`;
11. `real_company_validation_runs`;
12. `end_to_end_research_validations`;
13. `evidence_retention_actions`;
14. `live_incidents`;
15. `live_incident_events`.

It also adds `manual_evidence_import_request_id` to `raw_payloads`, makes
`provider_request_log_id` nullable, adds an exactly-one-source CHECK, expands the
`document_versions.byte_size` upper CHECK to 26,214,400 bytes, and adds a nullable
FK from `provider_live_validation_runs` to `live_authorization_grants`. Existing
rows and historical checksums are not updated.

## 4. Task records 1-20: authorization and manual domain

| Task | File, symbol and input -> output | Table/state/failure contract | RED, minimum implementation, GREEN and regression | Commit and boundary |
|---|---|---|---|---|
| - [x] 1. LiveAuthorizationGrant domain model | `domain/live_evidence/enums.py`, `schemas.py`; `LiveAuthorizationGrantWrite -> LiveAuthorizationGrantRecord` | `live_authorization_grants`; immutable scope; `AUTH_SCOPE_INVALID`, `AUTH_CHECKSUM_INVALID` | RED `tests/unit/test_live_authorization_models.py`; run `uv run pytest tests/unit/test_live_authorization_models.py -q`; add bounded enums/schemas/canonical validation; GREEN same; regress `tests/unit/test_provider_live_authorization.py` | `feat: add finite live authorization contracts`; A; N/N/N |
| - [x] 2. Immutable authorization Scope | `domain/live_evidence/canonical.py`; `canonical_grant(LiveAuthorizationGrantWrite) -> str`, `grant_checksum(...) -> Checksum` | grant canonical identity; `AUTH_SCOPE_MUTATION`, `AUTH_SCOPE_NONCANONICAL` | RED `tests/unit/test_live_authorization_canonical.py`; implement sorted exact domains/methods/filing scope excluding generated time/ID; GREEN; regress Task 1 | `feat: freeze live authorization scope`; A; N/N/N |
| - [x] 3. Authorization state machine | `domain/live_evidence/authorization.py`; `AuthorizationStateMachine.transition(state,event) -> state` | event-derived DRAFT/APPROVED/ACTIVE/CONSUMED/EXPIRED/REVOKED/CANCELLED; `AUTH_TRANSITION_INVALID`, `AUTH_TERMINAL_IMMUTABLE` | RED `tests/unit/test_live_authorization_state_machine.py`; implement finite transition map; GREEN; regress Tasks 1-2 | `feat: add live authorization state machine`; A; N/N/N |
| - [x] 4. Authorization Consumption | `schemas.py`, `authorization.py`; `ConsumptionReservationRequest -> ConsumptionReservation`, settlement request -> record | `live_authorization_consumptions`; RESERVED/SETTLED/ABANDONED; `AUTH_CONSUMPTION_DUPLICATE`, `AUTH_RESERVATION_INVALID` | RED `tests/unit/test_live_authorization_consumption.py`; implement request-attempt idempotency and actual-byte accounting; GREEN; regress Tasks 1-3 | `feat: account for live authorization consumption`; A; N/N/N |
| - [x] 5. Execution Approval | `domain/live_evidence/execution_approval.py`; create/validate signatures from registry | `live_execution_approvals`; VALID/EXPIRED/CONSUMED/BLOCKED; `EXEC_APPROVAL_PLAN_MISMATCH`, `EXEC_APPROVAL_EXPIRED`, `EXEC_APPROVAL_REPLAYED` | RED `tests/unit/test_live_execution_approval.py`; bind grant/plan checksums and ten-minute upper lifetime; GREEN; regress authorization tests | `feat: bind single use live execution approval`; A; N/N/N |
| - [x] 6. Atomic request budget | `db/repositories/live_evidence.py`; `reserve_consumption(Session, request) -> reservation` | consumption + grant lock; `AUTH_REQUEST_BUDGET_EXCEEDED` | RED PostgreSQL `tests/integration/test_live_authorization_budget_postgres.py::test_request_budget_is_atomic`; implement `SELECT FOR UPDATE`, unique attempt and request sum; GREEN; regress migration lifecycle tests | `feat: enforce atomic live request budgets`; A; N/N/N |
| - [x] 7. Atomic byte budget | same repository; `settle_consumption(Session, settlement) -> record` | consumption totals; `AUTH_BYTE_BUDGET_EXCEEDED`, `AUTH_SETTLEMENT_CONFLICT` | RED second node in `test_live_authorization_budget_postgres.py`; implement reserved/actual byte reconciliation without refunding received bytes; GREEN; regress Task 6 | `feat: enforce atomic live byte budgets`; A; N/N/N |
| - [x] 8. Grant expiry | `authorization.py`; `derive_state(grant,events,now) -> LiveAuthorizationState` | EXPIRED terminal; `AUTHORIZATION_EXPIRED` | RED `tests/unit/test_live_authorization_expiry.py`; compare aware UTC expiry before execution/reservation; GREEN; regress state machine | `feat: expire finite live authorizations`; A; N/N/N |
| - [x] 9. Grant revocation | `authorization.py`, repository; `revoke(RevokeAuthorizationRequest) -> state` | append REVOKED event; `AUTHORIZATION_REVOKED`, `AUTH_REVOCATION_CONFLICT` | RED `tests/unit/test_live_authorization_revocation.py`; implement append-only revoke winning before new reservation; GREEN; regress Tasks 3/6 | `feat: revoke live authorizations safely`; A; N/N/N |
| - [x] 10. Single consumption | authorization service; `activate/validate/reserve` | consumed grant terminal; `AUTHORIZATION_ALREADY_CONSUMED` | RED `tests/integration/test_live_authorization_single_use_postgres.py`; atomically derive final CONSUMED and reject replay; GREEN; regress Tasks 4/6/7 | `feat: enforce single use live grants`; A; N/N/N |
| - [x] 11. Provider cross-scope protection | `authorization.py`; `validate_execution_scope(grant,scope) -> AuthorizationDecision` | no table change; `AUTH_PROVIDER_MISMATCH` | RED `tests/unit/test_live_authorization_scope.py::test_provider_mismatch`; exact UUID/code/version match; GREEN; regress authorization suite | `test: enforce live provider scope`; A; N/N/N |
| - [x] 12. Capability cross-scope protection | same symbol/input/output | no table change; `AUTH_CAPABILITY_MISMATCH` | RED node `test_capability_mismatch`; exact capability ID/code/version; GREEN; regress scope suite | `test: enforce live capability scope`; A; N/N/N |
| - [x] 13. Security cross-scope protection | same symbol/input/output | no table change; `AUTH_SECURITY_MISMATCH`, `AUTH_PROVIDER_IDENTIFIER_MISMATCH` | RED nodes for Security/CIK mismatch; exact Security/issuer/provider identifier; GREEN; regress Security Master resolution tests | `test: enforce live security scope`; A; N/N/N |
| - [x] 14. ManualEvidenceImportRequest | `schemas.py`, `domain/live_evidence/manual.py`; `ManualEvidenceImportPlanRequest -> ManualEvidenceImportPlan`, receive request -> record | `manual_evidence_import_requests`; RECEIVED; `MANUAL_IMPORT_SCOPE_INVALID`, `MANUAL_SOURCE_TYPE_INVALID` | RED `tests/unit/test_manual_evidence_requests.py`; bounded immutable plan/request schemas with MANUAL_IMPORT/OFFLINE/NOT_LIVE; GREEN; regress document schemas | `feat: add controlled manual evidence requests`; A; N/N/N |
| - [x] 15. ManualEvidenceSourceDeclaration | `manual.py`; `ManualEvidenceSourceDeclarationWrite -> record` | declarations; versioned immutable rights/source; `MANUAL_DECLARATION_INCOMPLETE`, `MANUAL_LICENSE_UNKNOWN` | RED `tests/unit/test_manual_evidence_declarations.py`; implement typed source/right fields and canonical checksum; GREEN; regress Task 14 | `feat: add manual evidence source declarations`; A; N/N/N |
| - [x] 16. ManualEvidenceValidation | `manual.py`; `ManualEvidenceValidationWrite -> record`, validator set -> result | validations append-only PASS/PARTIAL/BLOCKED/FAIL; `MANUAL_VALIDATION_CONFLICT` | RED `tests/unit/test_manual_evidence_validation.py`; implement stable validator code/version/input checksum result; GREEN; regress Tasks 14-15 | `feat: record manual evidence validation`; A; N/N/N |
| - [x] 17. ManualEvidenceReview | `manual.py`; registry review signature | reviews APPROVED/PARTIAL/REJECTED/BLOCKED; `MANUAL_REVIEW_CHECKSUM_MISMATCH`, `MANUAL_BLOCK_CANNOT_BE_WAIVED` | RED `tests/unit/test_manual_evidence_review.py`; bind validator-set/file/declaration checksums and forbid blocking waiver; GREEN; regress validation | `feat: add checksum bound manual reviews`; A; N/N/N |
| - [x] 18. Manual evidence state machine | `manual.py`; `derive_manual_import_state(request, validations, reviews, manifest) -> state` | RECEIVED/QUARANTINED/VALIDATING/APPROVED/PARTIAL/REJECTED/BLOCKED/INGESTED | RED `tests/unit/test_manual_evidence_state_machine.py`; implement deterministic derived-state precedence and terminal behavior; GREEN; regress Tasks 14-17 | `feat: add manual evidence state machine`; A; N/N/N |
| - [x] 19. Quarantine | `infrastructure/manual_evidence_storage.py`; `quarantine(QuarantineFileRequest) -> QuarantinedFile` | request remains source; QUARANTINED via validation; `QUARANTINE_WRITE_FAILED`, `QUARANTINE_CHECKSUM_MISMATCH` | RED `tests/unit/test_manual_evidence_quarantine.py`; atomic UUID blob copy, exact SHA-256/size, cleanup on failure using synthetic bytes; GREEN; regress blob storage tests | `feat: quarantine manual evidence atomically`; A; N/N/N |
| - [x] 20. File path safety | `domain/live_evidence/file_security.py`; `resolve_inbox_file(root, relative_name) -> ResolvedInboxFile` | no table; `PATH_TRAVERSAL`, `ABSOLUTE_PATH`, `UNC_PATH`, `SYMLINK_ESCAPE` | RED `tests/unit/test_manual_evidence_paths.py`; root-resolve without follow/escape and no persisted absolute path; GREEN; regress infrastructure storage security | `feat: secure manual evidence paths`; A; N/N/N |

## 5. Task records 21-40: file safety and evidence admission

| Task | File, symbol and input -> output | Table/state/failure contract | RED, minimum implementation, GREEN and regression | Commit and boundary |
|---|---|---|---|---|
| - [x] 21. Filename normalization | `file_security.py`; `validate_filename(original: str) -> SafeFilename` | request safe filename; `WINDOWS_DEVICE_NAME`, `DOUBLE_EXTENSION`, `UNICODE_EXTENSION_CONFUSION`, `FILENAME_INVALID` | RED `tests/unit/test_manual_evidence_filenames.py`; NFKC comparison, reserved-name/trailing-dot/ADS/double-extension rules while preserving original in request only; GREEN; regress Task 20 | `feat: normalize manual evidence filenames`; A; N/N/N |
| - [x] 22. MIME validation | `file_security.py`; `validate_mime(content, extension, declared_mime) -> FileContentIdentity` | validation PASS/BLOCKED; `MIME_NOT_ALLOWED`, `MIME_EXTENSION_MISMATCH` | RED `tests/unit/test_manual_evidence_mime.py`; exact PDF/HTML/JSON allowlist; GREEN; regress existing document MIME tests | `feat: validate manual evidence mime`; A; N/N/N |
| - [x] 23. Magic Bytes validation | same module; `detect_content_type(content) -> ContentType` | validation; `MAGIC_BYTES_MISMATCH`, `EXECUTABLE_MAGIC_FORBIDDEN`, `ARCHIVE_FORBIDDEN` | RED `tests/unit/test_manual_evidence_magic.py`; bounded signature detection and UTF-8 structural prefixes; GREEN; regress Task 22 | `feat: validate manual evidence magic bytes`; A; N/N/N |
| - [x] 24. File size limit | same module; `validate_file_size(size: int, limit=26214400) -> None` | validation; `FILE_EMPTY`, `FILE_TOO_LARGE` | RED `tests/unit/test_manual_evidence_size.py`; reject bool/negative/zero/over-25MiB before full read; GREEN; regress quarantine | `feat: bound manual evidence file size`; A; N/N/N |
| - [x] 25. PDF safety inspection | `domain/live_evidence/pdf_security.py`; `inspect_pdf(content: bytes) -> PdfSafetyResult` | validation PASS/PARTIAL/BLOCKED; `PDF_ENCRYPTED`, `PDF_CORRUPT`, `PDF_OBJECT_LIMIT`, `PDF_EXTERNAL_EXECUTION` | RED `tests/unit/test_manual_pdf_security.py`; bounded static object/action inspection using local bytes only; GREEN; regress Stage 6 PDF parser | `feat: inspect manual pdf safety`; A; N/N/N |
| - [x] 26. PDF JavaScript rejection | `pdf_security.py`; `reject_active_pdf_actions(PdfInspection) -> None` | BLOCKED; `PDF_JAVASCRIPT` | RED node `test_pdf_javascript_is_blocked`; detect `/JavaScript` and `/JS` object/action names, not plain visible prose; GREEN; regress Task 25 | `test: reject pdf javascript actions`; A; N/N/N |
| - [x] 27. PDF Launch Action rejection | same symbol | BLOCKED; `PDF_LAUNCH_ACTION`, `PDF_OPEN_ACTION` | RED nodes for Launch/OpenAction; inspect parsed object graph without executing it; GREEN; regress Tasks 25-26 | `test: reject pdf launch actions`; A; N/N/N |
| - [x] 28. PDF embedded-file rejection | same symbol | BLOCKED; `PDF_EMBEDDED_FILE`, `PDF_RICH_MEDIA` | RED nodes for EmbeddedFiles/FileAttachment/RichMedia; reject containers; GREEN; regress PDF safety suite | `test: reject embedded pdf content`; A; N/N/N |
| - [x] 29. OCR prohibition | `pdf_security.py`, `domain/documents/parsers/pdf.py`; `pdf_parse_policy(result) -> ParserAdmissionDecision` | PARTIAL/BLOCKED; `OCR_REQUIRED_BLOCKED`, `PDF_TEXT_LAYER_INSUFFICIENT` | RED `tests/unit/test_manual_pdf_no_ocr.py`; explicit policy/provider absence and no OCR import/subprocess; GREEN; regress PDF parser | `test: enforce no ocr manual import`; A; N/N/N |
| - [x] 30. HTML script rejection | `domain/live_evidence/html_security.py`; `inspect_html(content: bytes) -> HtmlSafetyResult` | BLOCKED; `HTML_SCRIPT`, `HTML_EVENT_HANDLER`, `HTML_JAVASCRIPT_URL` | RED `tests/unit/test_manual_html_security.py`; inert parser identifies executable nodes/attributes without rendering; GREEN; regress Stage 6 HTML parser | `feat: reject active html evidence`; A; N/N/N |
| - [x] 31. HTML external resource rejection | same module/symbol | BLOCKED; `HTML_EXTERNAL_RESOURCE`, `HTML_LOCAL_FILE_REFERENCE`, `HTML_META_REFRESH` | RED nodes for img/link/font/iframe/object/embed/file/UNC/meta refresh; inspect strings only, never resolve; GREEN; regress Task 30 | `test: reject external html resources`; A; N/N/N |
| - [x] 32. JSON depth limit | `domain/live_evidence/json_security.py`; `load_bounded_json(content, policy) -> JsonSafetyResult` | validation; `JSON_DEPTH_EXCEEDED`, `JSON_ENCODING_INVALID` | RED `tests/unit/test_manual_json_security.py::test_depth_limit`; event/bounded recursive parser depth 32 and UTF-8/BOM policy; GREEN; regress document JSON parser | `feat: bound manual json depth`; A; N/N/N |
| - [x] 33. JSON node limit | same module; same input/output | validation; `JSON_NODE_LIMIT_EXCEEDED`, `JSON_STRING_LIMIT_EXCEEDED`, `JSON_ARRAY_LIMIT_EXCEEDED`, `JSON_DUPLICATE_KEY`, `JSON_NONFINITE_NUMBER` | RED remaining nodes in JSON security test; count nodes/array/string and reject duplicates/nonfinite; GREEN; regress Task 32 | `feat: bound manual json structure`; A; N/N/N |
| - [x] 34. Unified Raw Artifact bridge | `domain/live_evidence/artifacts.py`; `bridge_raw_payload(ManualArtifactBridgeRequest) -> RawPayloadRecord` | evolves `raw_payloads`; exactly one provider request/manual request; `RAW_ARTIFACT_SOURCE_CONFLICT`, `RAW_ARTIFACT_CHECKSUM_MISMATCH` | RED `tests/unit/test_manual_artifact_bridge.py`; define source-neutral schema/service using local DataProvider/IngestionRun and no request log; GREEN; regress Stage 4/9 artifact tests | `feat: bridge manual raw artifacts without http`; A; N/N/N |
| - [x] 35. Manual/Provider source distinction | `artifacts.py`; `classify_artifact_source(record) -> EvidenceSourceType` | PROVIDER_LIVE/MANUAL_IMPORT/SYNTHETIC_TEST/OFFLINE_FIXTURE; `ARTIFACT_SOURCE_AMBIGUOUS` | RED `tests/unit/test_evidence_source_classification.py`; exact mutually exclusive classification, manual always OFFLINE/NOT_LIVE; GREEN; regress provider artifacts | `feat: preserve evidence source distinction`; A; N/N/N |
| - [x] 36. Evidence Ingestion Manifest | `domain/live_evidence/manifests.py`; registry create/verify signatures | `evidence_ingestion_manifests`; immutable PROVIDER_LIVE/MANUAL_IMPORT/SYNTHETIC_TEST/OFFLINE_FIXTURE; `MANIFEST_UPSTREAM_INVALID`, `MANIFEST_LICENSE_BLOCKED` | RED `tests/unit/test_evidence_ingestion_manifest.py`; frozen typed source/security/issuer/artifact/document/rights/validation/review fields; GREEN; regress Stage 9 manifest tests | `feat: add source neutral evidence manifests`; A; N/N/N |
| - [x] 37. Manifest canonical checksum | `manifests.py`; `canonical_manifest(write) -> str`, `manifest_checksum(write) -> Checksum` | manifest unique checksum; `MANIFEST_NONCANONICAL`, `MANIFEST_CHECKSUM_MISMATCH` | RED `tests/unit/test_evidence_manifest_checksum.py`; sort stable IDs/reasons, exclude created_at/generated ID, reuse equal input; GREEN; regress Task 36 | `feat: canonicalize evidence manifests`; A; N/N/N |
| - [x] 38. Artifact to DocumentVersion bridge | `domain/live_evidence/document_bridge.py`; `admit_document(ArtifactDocumentAdmissionRequest) -> DocumentVersionResult` | existing logical/source/document tables + generic manifest; `DOCUMENT_ARTIFACT_MISMATCH`, `DOCUMENT_SOURCE_NOT_APPROVED`, `DOCUMENT_IDENTITY_MISMATCH` | RED `tests/unit/test_evidence_document_bridge.py`; require admitted manifest, create SourceDocument/DocumentVersion via existing service, no direct raw body mutation; GREEN; regress Stage 6 identity tests | `feat: admit governed artifacts as document versions`; A; N/N/N |
| - [x] 39. Citation eligibility | `domain/live_evidence/citation_eligibility.py`; `evaluate_citation_eligibility(EvidenceCitationRequest) -> CitationEligibilityDecision` | no new table; ELIGIBLE/BLOCKED; `CITATION_DOCUMENT_UNVERIFIED`, `CITATION_SOURCE_BLOCKED`, `CITATION_FUTURE_DATA` | RED `tests/unit/test_evidence_citation_eligibility.py`; require approved manifest, exact version and existing VALID verifier result; GREEN; regress citation verifier | `feat: gate citation eligibility`; A; N/N/N |
| - [x] 40. Unverified evidence isolation | same module; `evaluate_claim_eligibility(EvidenceClaimRequest) -> ClaimEligibilityDecision` | unverified/QUARANTINED cannot support Claim; `UNVERIFIED_EVIDENCE_FORBIDDEN`, `UNVERIFIED_CITATION_FORBIDDEN`, `UNVERIFIED_REPORT_FORBIDDEN` | RED `tests/unit/test_unverified_evidence_isolation.py`; allow only limitation/data-quality role; GREEN; regress Agent Claim/Report release tests | `feat: isolate unverified company evidence`; A; N/N/N |

## 6. Task records 41-60: Snapshot, Agent, Report, retention and incidents

| Task | File, symbol and input -> output | Table/state/failure contract | RED, minimum implementation, GREEN and regression | Commit and boundary |
|---|---|---|---|---|
| - [x] 41. Ingestion-to-Snapshot Binding | `domain/live_evidence/snapshot.py`; `bind_manifest_to_snapshot(IngestionSnapshotBindingWrite) -> record` | `ingestion_to_snapshot_bindings`; immutable; `SNAPSHOT_BINDING_SCOPE_MISMATCH`, `SNAPSHOT_BINDING_DUPLICATE` | RED `tests/unit/test_ingestion_snapshot_binding.py`; exact manifest/Security/Snapshot/checksum link; GREEN; regress snapshot-document link tests | `feat: bind evidence manifests to snapshots`; A; N/N/N |
| - [x] 42. Snapshot Plan | same module; registry plan signature | no write; READY/PARTIAL/BLOCKED; `SNAPSHOT_MANIFEST_NOT_APPROVED`, `SNAPSHOT_INPUT_INCOMPLETE`, `SNAPSHOT_LICENSE_BLOCKED` | RED `tests/unit/test_snapshot_from_ingestion_plan.py`; deterministic plan over explicit manifest/document/fact/mapping/formula/as-of IDs; GREEN; regress existing SnapshotBuilder tests | `feat: plan snapshots from governed ingestion`; A; N/N/N |
| - [x] 43. Snapshot Create | same module; registry create signature | data_snapshots/items/document links/bindings; COMPLETE/PARTIAL/BLOCKED; `SNAPSHOT_PLAN_CHECKSUM_MISMATCH`, `SNAPSHOT_PERSISTENCE_FAILED` | RED `tests/integration/test_snapshot_from_ingestion_postgres.py`; revalidate plan in caller-owned transaction and call existing builder using synthetic test evidence; GREEN; regress Stage 4 snapshots | `feat: create snapshots from evidence manifests`; A; N/N/N |
| - [x] 44. Snapshot immutability | DB triggers/service; `verify_snapshot_immutability(snapshot_id) -> decision` | existing terminal Snapshot + new binding immutable; `SNAPSHOT_IMMUTABLE`, `SNAPSHOT_BINDING_IMMUTABLE` | RED PostgreSQL nodes attempting update/delete/late binding; add 0009 trigger for binding and retain existing Snapshot triggers; GREEN; regress migration tests | `test: preserve historical snapshot immutability`; A; N/N/N |
| - [x] 45. Future Data protection | `snapshot.py`; `validate_temporal_scope(plan) -> TemporalDecision` | plan BLOCKED; `FUTURE_DATA`, `SOURCE_PUBLISHED_AT_UNKNOWN_STRICT`, `AS_OF_MISMATCH` | RED `tests/unit/test_snapshot_ingestion_as_of.py`; reject published/filed/fact time after cutoff and never substitute import time; GREEN; regress Stage 4/5 as-of tests | `feat: reject future evidence snapshots`; A; N/N/N |
| - [x] 46. Security isolation | `snapshot.py`; `validate_security_scope(plan) -> ScopeDecision` | plan BLOCKED; `SNAPSHOT_SECURITY_MISMATCH`, `SNAPSHOT_ISSUER_MISMATCH` | RED `tests/unit/test_snapshot_ingestion_scope.py`; require manifest/artifact/document/facts equal explicit Security/issuer; GREEN; regress Task 13 and Security resolution | `feat: isolate snapshot evidence security`; A; N/N/N |
| - [x] 47. Synthetic isolation | `snapshot.py`; `validate_synthetic_scope(plan) -> ScopeDecision` | real-company plan BLOCKED; `SYNTHETIC_COMPANY_EVIDENCE_FORBIDDEN`, `FIXTURE_COMPANY_EVIDENCE_FORBIDDEN` | RED `tests/unit/test_snapshot_ingestion_synthetic.py`; neutral synthetic Security allowed only in TEST_ONLY plan; GREEN; regress Stage 7/8 synthetic boundaries | `feat: isolate synthetic snapshot evidence`; A; N/N/N |
| - [x] 48. Agent Run plan | `domain/live_evidence/offline_pipeline.py`; registry `plan_agent` | no write; READY/PARTIAL/BLOCKED; `AGENT_SNAPSHOT_NOT_SEALED`, `AGENT_POLICY_MISMATCH` | RED `tests/unit/test_agent_from_snapshot_plan.py`; bind exact Snapshot/Security/as-of/policy/tool catalog with no latest shortcut; GREEN; regress Stage 7 planning tests | `feat: plan explicit agent runs from snapshots`; A; N/N/N |
| - [x] 49. Explicit Agent Run | same module; registry `run_agent` | existing research request/run/plan/package; deterministic terminal state; `AGENT_PLAN_CHECKSUM_MISMATCH`, `AGENT_EXECUTION_BLOCKED` | RED `tests/integration/test_offline_agent_from_snapshot.py`; call existing controlled orchestrator with neutral synthetic persisted Snapshot; GREEN; regress Stage 7 synthetic flow | `feat: run controlled agent from explicit snapshot`; A; N/N/N |
| - [x] 50. Agent read-only boundary | same module and existing executor policy; `validate_agent_boundary(plan) -> decision` | no table; `AGENT_TOOL_NOT_READ_ONLY`, `AGENT_TOOL_NETWORK_FORBIDDEN`, `AGENT_CREDENTIAL_ACCESS_FORBIDDEN`, `AGENT_PROVIDER_SYNC_FORBIDDEN` | RED `tests/unit/test_gate_a_agent_boundaries.py`; assert catalog permission/writes/network and prohibit Provider/credential services; GREEN; regress all Agent Tool contracts | `test: enforce gate a agent boundaries`; A; N/N/N |
| - [x] 51. Report Generation plan | `offline_pipeline.py`; registry `plan_report` | no write; READY/PARTIAL/BLOCKED; `REPORT_PACKAGE_NOT_SEALED`, `REPORT_MANIFEST_INVALID` | RED `tests/unit/test_report_from_package_plan.py`; bind exact package/run/Snapshot/policy/template/reflection versions/checksums; GREEN; regress Stage 8 manifest tests | `feat: plan reports from explicit packages`; A; N/N/N |
| - [x] 52. Explicit Report execution | same module; registry `generate_report` | existing report request/run/report/reflection/revision/release rows; `REPORT_PLAN_CHECKSUM_MISMATCH`, `REPORT_PIPELINE_BLOCKED` | RED `tests/integration/test_offline_report_from_package.py`; invoke existing deterministic pipeline with neutral synthetic package; GREEN; regress Stage 8 synthetic flow | `feat: generate reports from explicit packages`; A; N/N/N |
| - [x] 53. Report version chain | existing versioning + wrapper; `validate_report_predecessor(request) -> decision` | research_reports immutable chain; `REPORT_PREDECESSOR_MISMATCH`, `REPORT_HISTORY_MUTATION` | RED `tests/unit/test_gate_a_report_versions.py`; require new row/previous ID and reject overwrite; GREEN; regress report version tests | `test: preserve report version history`; A; N/N/N |
| - [x] 54. Release Gate reuse | wrapper; `release(report_id, round_two_id) -> ReportReleaseDecision` | existing release gate; `RELEASE_GATE_BYPASS_FORBIDDEN`, `RELEASE_REQUIREMENT_FAILED` | RED `tests/unit/test_gate_a_release_gate.py`; delegate only to existing deterministic gate, no force flag; GREEN; regress release gate suite | `test: prevent report release gate bypass`; A; N/N/N |
| - [x] 55. RealCompanyValidationRun | `domain/live_evidence/validation.py`; registry create signature | `real_company_validation_runs`; PLANNED/RUNNING/PASS/PARTIAL/BLOCKED/FAIL/CANCELLED; `VALIDATION_SCOPE_INVALID`, terminal immutable | RED `tests/unit/test_real_company_validation_run.py`; frozen input checksum and finite state machine; GREEN; regress Agent/Report run states | `feat: add real company validation runs`; A; N/N/N |
| - [x] 56. EndToEndResearchValidation | same module; registry append-check signature | `end_to_end_research_validations`; per check PASS/PARTIAL/BLOCKED/NOT_ATTEMPTED/FAIL; `VALIDATION_CHECK_DUPLICATE`, `VALIDATION_EVIDENCE_INVALID` | RED `tests/unit/test_end_to_end_research_validation.py`; append typed stage check/evidence reference; GREEN; regress Task 55 | `feat: record end to end evidence validation`; A; N/N/N |
| - [x] 57. Evidence Retention Action | `domain/live_evidence/retention.py`; registry plan signature | `evidence_retention_actions`; PLANNED/RUNNING/PASS/PARTIAL/BLOCKED/FAIL; `RETENTION_SCOPE_INVALID`, `RETENTION_DEADLINE_INVALID` | RED `tests/unit/test_evidence_retention.py`; deterministic affected-lineage/deadline/action plan without bytes; GREEN; regress license policy tests | `feat: plan governed evidence retention`; A; N/N/N |
| - [x] 58. Restricted Artifact deletion | retention service execute signature + storage port | action terminal; `RETENTION_DELETE_BLOCKED`, `RETENTION_DELETE_VERIFY_FAILED`, `RETENTION_HISTORY_REWRITE_FORBIDDEN` | RED `tests/unit/test_evidence_retention_delete.py`; delete only injected synthetic blob, verify absence, retain allowed audit and impact; GREEN; regress blob safety | `feat: delete restricted evidence safely`; A; N/N/N |
| - [x] 59. Incident model | `domain/live_evidence/incidents.py`; registry open signature | `live_incidents`; OPEN/CONTAINED/REMEDIATING/CLOSED; `INCIDENT_SCOPE_INVALID`, terminal closure | RED `tests/unit/test_live_incidents.py`; typed category/severity/affected lineage/checksum; GREEN; regress Provider audit tests | `feat: add live evidence incidents`; A; N/N/N |
| - [x] 60. Incident events | same module; registry append-event signature | `live_incident_events`; append-only sequence; `INCIDENT_TRANSITION_INVALID`, `INCIDENT_EVENT_DUPLICATE` | RED `tests/unit/test_live_incident_events.py`; finite event state transitions and immutable audit; GREEN; regress Task 59 | `feat: add append only incident events`; A; N/N/N |

## 7. Task records 61-80: interfaces, persistence, tests and acceptance

| Task | File, symbol and input -> output | Table/state/failure contract | RED, minimum implementation, GREEN and regression | Commit and boundary |
|---|---|---|---|---|
| - [x] 61. Live authorization CLI | `cli_live.py`; `authorization_plan/show/activate/revoke(...) -> None` | grant/events/approval query or explicit write; stable exit codes for BLOCKED/INVALID | RED `tests/unit/test_live_authorization_cli.py`; Typer commands require exact IDs/checksums, Fake app injection, JSON/human output; GREEN; regress existing CLI help | `feat: add live authorization cli`; A; N/N/N |
| - [x] 62. SEC pilot CLI offline plan | `cli_live.py`; `sec_plan/validate/run/show(...) -> None` | plan/read/test-only execution; `LIVE_AUTHORIZATION_REQUIRED`, `LIVE_EXECUTION_APPROVAL_REQUIRED`, `LIVE_TRANSPORT_NOT_CONFIGURED` | RED `tests/unit/test_sec_live_pilot_cli.py`; plan resolves persisted MU/CIK via injected repository, run fails before transport unless TEST_ONLY grant+Fake Transport; GREEN; regress Stage 9 SEC planner/CLI | `feat: add fail closed sec pilot cli`; A; N/N/N |
| - [x] 63. Manual import CLI | `cli_evidence.py`; `import_plan/import_file/validate/approve/reject/show(...) -> None` | manual tables/payload/manifest; stable nonzero BLOCKED/REJECTED | RED `tests/unit/test_manual_evidence_cli.py`; explicit separated commands, inbox-relative path and checksums, synthetic fixtures only; GREEN; regress document CLI | `feat: add controlled evidence import cli`; A; N/N/N |
| - [x] 64. Snapshot CLI | `cli_snapshot_ingestion.py`; `plan_from_ingestion/create_from_ingestion(...) -> None` | plan read/create synthetic test Snapshot; `SNAPSHOT_PLAN_REQUIRED` | RED `tests/unit/test_snapshot_ingestion_cli.py`; exact plan ID/checksum, no latest, app injection; GREEN; regress data snapshot CLI | `feat: add snapshot ingestion cli`; A; N/N/N |
| - [x] 65. Research Run CLI | `cli_research_pipeline.py`; `run_from_snapshot(...) -> None` | existing Agent tables; `AGENT_PLAN_REQUIRED` | RED `tests/unit/test_research_from_snapshot_cli.py`; exact Snapshot/research type/policy and offline application injection; GREEN; regress Agent CLI | `feat: add explicit research run cli`; A; N/N/N |
| - [x] 66. Report CLI | existing `cli_reports.py`; `generate_from_package(...) -> None` | existing Report tables; `REPORT_PLAN_REQUIRED` | RED `tests/unit/test_report_from_package_cli.py`; exact Package/policy plan and no force-publish option; GREEN; regress Report CLI | `feat: add explicit package report cli`; A; N/N/N |
| - [x] 67. Query Tool | `tools/live_evidence.py`, `tools/schemas_live_evidence.py`, registry; ten bounded query callables -> safe summaries | READ_ONLY/writes=false/requires_network=false; `RESOURCE_NOT_FOUND`, `QUERY_LIMIT_INVALID` | RED `tests/contract/test_live_evidence_tools.py`; add exact versioned Tool names, input/output schemas and persisted-query-only adapters; GREEN; regress Tool catalog checksum/permissions | `feat: add read only live evidence tools`; A; N/N/N |
| - [x] 68. GET-only API | `api/routes/live_evidence.py`, router; ten approved GET handlers -> stable JSON | query-only; 404/422 safe, no raw/path/secret; methods other than GET absent | RED `tests/contract/test_live_evidence_api_contract.py`; add bounded routes/dependencies/query service only; GREEN; regress OpenAPI/request ID/API read-only tests | `feat: add live evidence query api`; A; N/N/N |
| - [x] 69. Database models | `db/models/live_evidence.py`, models init/base metadata | 15 registry tables + typed constraints/indexes/RESTRICT/terminal triggers contract; model validation failures | RED `tests/unit/test_live_evidence_models.py`; SQLAlchemy 2.x typed models matching registry; GREEN; regress metadata naming tests | `feat: add controlled live evidence models`; A; N/N/N |
| - [x] 70. Alembic migration | `migrations/versions/0009_controlled_live_evidence.py`; `upgrade/downgrade` | create 15 tables, evolve raw_payloads/document size/provider validation FK, immutable triggers; downgrade Stage10 only | RED `tests/integration/test_live_evidence_migrations.py`; prove pre-0009 failure/missing, implement named DDL/downgrade; GREEN; regress all prior migration suites | `feat: migrate controlled live evidence schema`; A; N/N/N |
| - [x] 71. PostgreSQL integration | repository + `tests/integration/test_live_evidence_repository_postgres.py` | all tables, FK/UNIQUE/CHECK/index/rollback/immutability/lock behavior | RED focused repository tests; implement SQLAlchemy repository mappings/atomic transactions; GREEN; regress Provider/Snapshot/Agent/Report repositories | `test: verify live evidence postgres contracts`; A; N/N/N |
| - [x] 72. Default offline isolation | `tests/unit/test_stage10_offline_isolation.py`, network fixture reuse | no table; fail on DNS/socket/credential resolver/model/Provider transport | RED audit importing all Stage10 entrypoints and patching forbidden calls; remove any import-time side effect/inject ports; GREEN; regress Stage 9 offline isolation | `test: enforce stage 10 offline defaults`; A; N/N/N |
| - [x] 73. tests_live isolation | `pyproject.toml`, `tests_live/test_sec_controlled_live.py`, default collection contract | external state NOT_ATTEMPTED/BLOCKED without approved environment; not default collected | RED `tests/unit/test_stage10_live_test_isolation.py`; use collection exclusion/explicit harness, no skip-as-PASS; GREEN; regress default collect count semantics | `test: isolate controlled live tests`; A; N/N/N |
| - [x] 74. Fixture LF | `tests/fixtures/live_evidence/**`, manifests, `.gitattributes` exact path | synthetic/offline/not-live/checksum/license metadata; `FIXTURE_CHECKSUM_MISMATCH` | RED `tests/unit/test_stage10_fixture_integrity.py`; add minimal synthetic PDF/HTML/JSON attacks and manifests with LF/checksums; GREEN; regress Stage 6/8/9 fixtures | `test: add reproducible live evidence fixtures`; A; N/N/N |
| - [x] 75. Security matrix | focused tests listed in Prompt across authorization/file/source/Snapshot/API/logging | all relevant states; exact security failure codes from Tasks 1-74 | RED `tests/unit/test_stage10_security_matrix.py`; add missing cross-component assertions only, no duplicate meaningless parameterization; GREEN; regress full security/provider/document suites | `test: complete stage 10 security matrix`; A; N/N/N |
| - [x] 76. Reflection round one | `docs/reflection/stage-10-round-1.md`; seven roles, issue rows -> findings | CRITICAL/HIGH/MEDIUM/LOW with evidence/files/fix/block/status | RED `tests/unit/test_stage10_reflection_documents.py`; document real audit and failing commands/findings; GREEN document contract; regress documentation tests | `docs: review stage 10 gate a implementation`; A; N/N/N |
| - [x] 77. CRITICAL/HIGH fixes | `tests/unit/test_stage10_reflection_remediations.py`; `verify_closed_findings(Stage10RoundOneReview) -> ReflectionRemediationResult`; each finding also names its exact affected production file/symbol before modification | finding IDs map to affected table/state/code; `REFLECTION_CRITICAL_OPEN`, `REFLECTION_HIGH_OPEN` | RED remediation test requires every CRITICAL/HIGH finding to own a focused failing node and affected symbol; apply each minimum finding-specific fix, GREEN remediation and affected test, then regress authorization/manual/Snapshot/Agent/Report/security suites; no waiver | `fix: resolve stage 10 critical and high findings`; A; N/N/N |
| - [x] 78. Reflection round two | `docs/reflection/stage-10-round-2.md`; actual test/migration evidence -> verification rows | unresolved CRITICAL=0/HIGH=0 required | RED doc test requires all round-one critical/high IDs and commands/results; rerun actual tests, document checks, GREEN; regress full focused suite | `docs: verify stage 10 reflection fixes`; A; N/N/N |
| - [x] 79. Implementation report | `docs/stage-10-implementation-report.md`, README/database/testing/API/security docs, `AGENTS.md`; actual evidence -> GATE_A status | GATE_A_COMPLETE/CONDITIONAL/NO_GO only; Stage10 overall CONDITIONAL GO when Gate B absent | RED `tests/unit/test_stage10_documentation.py`, `test_stage10_implementation_report.py`, repository guideline test; update exact commands/results/boundaries; GREEN; regress all docs tests | `docs: report stage 10 gate a implementation`; A; N/N/N |
| - [x] 80. Gate A final acceptance | no production symbol; execute full commands and record immutable evidence in report | final Head 0009; clean branch; zero failures/errors/skips/warnings; Live NOT_ATTEMPTED | RED `tests/unit/test_stage10_implementation_report.py` rejects missing final evidence; run `uv sync`, Ruff, format, mypy, full pytest, then Alembic current/upgrade/downgrade/upgrade/current; minimally record exact results; GREEN report test; regress full suite and verify 15 tables, history counts, no process/schema pollution | `chore: complete stage 10 gate a acceptance`; A; N/N/N |

## 8. Dependency order

Tasks execute numerically. Tasks 1-13 precede any CLI or persistence use of a
grant. Tasks 14-40 precede Snapshot admission. Tasks 41-47 precede Agent planning;
Tasks 48-54 reuse existing Stage 7/8 services rather than reimplement them. Models
and migration are introduced only after domain contracts are stable, while RED
PostgreSQL tests may be created earlier and remain failing until Tasks 69-71.
Tasks 76-80 cannot begin until all implementation tasks pass.

## 9. Plan self-check

- [x] All 80 Prompt tasks occur exactly once and in dependency order.
- [x] Every row names a file, symbol/signature, input/output, table/state/failure,
  RED command/test, minimum implementation, GREEN/regression, commit and boundary.
- [x] Domain interfaces are defined before task rows reference them.
- [x] Database registry matches the approved design and avoids fake HTTP lineage.
- [x] Existing Provider, Snapshot, Agent, Package and Report history is immutable.
- [x] Gate A never reads a Provider Credential/contact value or creates transport.
- [x] Manual evidence is MANUAL_IMPORT/OFFLINE/NOT_LIVE and uses only synthetic
  or safe fixture bytes in tests.
- [x] SEC CLI cannot execute Live without a separately approved exact Grant and
  injected transport; Gate A never supplies a real transport.
- [x] API and Tools are GET/query-only, read-only and offline.
- [x] No task enables Tushare, A-share automation, U.S. EOD, production Embedding,
  Narrative/Reflection models, advice, broker, trading or Stage 11.
- [x] No task uses an undefined operational placeholder or an open-ended scope.
- [x] Migration downgrade removes only Stage 10 objects and preserves Stage 2-9.
- [x] Default pytest has zero network, credentials, skips and warnings.
- [x] Fixture copyright/source/checksum/LF rules are explicit.
- [x] Reflection and final acceptance require actual commands and zero unresolved
  CRITICAL/HIGH findings.

## 10. Planned Gate A conclusion

Only verified completion of Task 80 permits `GATE_A_COMPLETE`. Gate B remains
`NOT_ATTEMPTED`; Stage 10 remains `CONDITIONAL GO`. No implementation or test in
this plan authorizes the phrase `批准执行该SEC有限Live验证` on the user's behalf.
