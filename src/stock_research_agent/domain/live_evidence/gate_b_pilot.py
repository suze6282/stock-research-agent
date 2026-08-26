"""Offline application contracts for the authorized SEC Gate B pilot."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field, model_validator

from stock_research_agent.domain.live_evidence.enums import ConsumptionState
from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.gate_b_authorization import (
    AuthorizedGateBExecution,
    GateBAuthorizationValidation,
)
from stock_research_agent.domain.live_evidence.schemas import ConsumptionSettlementRequest
from stock_research_agent.domain.providers.artifacts import (
    ProviderBatch,
    ProviderIngestionContext,
    ProviderIngestionManifestRecord,
    ProviderIngestionManifestWrite,
    ProviderManifestBatch,
    ProviderRawArtifactDraft,
    ProviderRawArtifactRecord,
    ProviderRawArtifactReservation,
    ProviderRawArtifactWrite,
    build_ingestion_manifest,
)
from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.credentials import CredentialReferenceRecord
from stock_research_agent.domain.providers.enums import (
    ProviderSyncSliceStatus,
    ProviderSyntheticStatus,
)
from stock_research_agent.domain.providers.quality import (
    ProviderDataQualityValidator,
    ProviderQualityContext,
    ProviderQualityIssue,
)
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
    SemanticVersion,
)
from stock_research_agent.domain.providers.sync import (
    ProviderRequestAttemptSettlement,
    ProviderSyncPlanRecord,
)
from stock_research_agent.infrastructure.provider_artifact_storage import StoredProviderArtifact
from stock_research_agent.providers.sec_edgar.adapter import (
    SecEdgarAdapter,
    SecParseContext,
)
from stock_research_agent.providers.sec_edgar.policy import (
    SecAuthorizedResource,
    bind_sec_authorized_plan,
)
from stock_research_agent.providers.sec_edgar.retry import (
    SecAttemptKind,
    SecAttemptPermit,
    SecAttemptReservationPort,
    SecAttemptReservationRequest,
    SecExecutionStartResult,
)
from stock_research_agent.providers.sec_edgar.schemas import (
    AccessionNumber,
    SecArtifactKind,
    SecFilename,
)
from stock_research_agent.providers.sec_edgar.transport import (
    SecPhysicalAttempt,
    SecTransportResult,
    SecTransportStatus,
)


class SecIngestionContext(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    sync_run_id: UUID
    license_policy_id: UUID
    security_id: UUID
    research_as_of_time: AwareUtcDateTime
    retrieved_at: AwareUtcDateTime
    source_published_at: AwareUtcDateTime | None
    adapter_version: SemanticVersion
    parser_version: SemanticVersion
    schema_version: str = Field(min_length=1, max_length=64)
    synthetic_status: ProviderSyntheticStatus
    source_identity: str = Field(min_length=1, max_length=512)
    source_endpoint_type: Literal[
        "SEC_SUBMISSIONS_JSON",
        "SEC_COMPANY_FACTS_JSON",
        "SEC_FILING_DOCUMENT",
    ]
    artifact_kind: SecArtifactKind
    expected_accession_number: AccessionNumber | None = None
    expected_document_path: SecFilename | None = None

    def as_ingestion_context(self, request_attempt_id: UUID) -> ProviderIngestionContext:
        return ProviderIngestionContext(
            provider_definition_id=self.provider_definition_id,
            provider_capability_id=self.provider_capability_id,
            sync_run_id=self.sync_run_id,
            request_attempt_id=request_attempt_id,
            security_id=self.security_id,
            research_as_of_time=self.research_as_of_time,
            adapter_version=self.adapter_version,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            synthetic_status=self.synthetic_status,
        )


class ValidatedSecSettlement(FrozenProviderContract):
    artifact_id: UUID
    request_attempt_id: UUID
    source_checksum: Checksum
    content_type: str
    body: bytes = Field(repr=False)
    batch: ProviderBatch
    raw_artifact_draft: ProviderRawArtifactDraft
    context: SecIngestionContext


class CommittedSecSettlement(FrozenProviderContract):
    artifact_id: UUID
    manifest_id: UUID
    request_attempt_id: UUID
    storage_uri: str
    content_checksum: Checksum
    manifest_checksum: Checksum


class SecDocumentCitationResult(FrozenProviderContract):
    document_version_id: UUID
    citation_ids: tuple[UUID, ...] = Field(min_length=1, max_length=10_000)


class CompletedSecResource(FrozenProviderContract):
    resource: SecAuthorizedResource
    committed: CommittedSecSettlement
    validated: ValidatedSecSettlement


class LiveValidationResult(FrozenProviderContract):
    status: Literal["PASSED", "BLOCKED"]
    terminal_stage: Literal["DATA_QUALITY", "RESOURCE_ORCHESTRATION"] = "DATA_QUALITY"
    artifact_id: UUID | None = None
    manifest_id: UUID | None = None
    request_attempt_id: UUID
    document_version_id: UUID | None = None
    citation_ids: tuple[UUID, ...] = ()
    data_quality_issue_count: int = Field(ge=0)
    warning_codes: tuple[str, ...] = Field(default=(), max_length=64)
    stop_reason: str = Field(default="DATA_QUALITY_STOP", min_length=1, max_length=128)
    failed_ordinal: int | None = Field(default=None, ge=0, le=2)
    failed_slice_id: str | None = Field(default=None, min_length=1, max_length=64)
    audit_event_id: UUID | None = None
    snapshot_created: bool = False
    research_request_created: bool = False
    agent_run_created: bool = False
    claim_created: bool = False
    report_created: bool = False
    stage_11_started: bool = False

    @model_validator(mode="after")
    def validate_terminal_lineage(self) -> LiveValidationResult:
        if self.terminal_stage == "DATA_QUALITY":
            if (
                self.artifact_id is None
                or self.manifest_id is None
                or self.document_version_id is None
                or not self.citation_ids
                or self.failed_ordinal is not None
                or self.failed_slice_id is not None
            ):
                raise ValueError("GATE_B_DATA_QUALITY_LINEAGE_REQUIRED")
        elif self.status != "BLOCKED" or self.failed_ordinal is None or not self.failed_slice_id:
            raise ValueError("GATE_B_RESOURCE_FAILURE_LINEAGE_REQUIRED")
        return self


class GateBAuditResourceView(FrozenProviderContract):
    ordinal: int = Field(ge=0, le=2)
    slice_id: str = Field(min_length=1, max_length=64)
    endpoint_id: str | None = Field(default=None, max_length=128)


class GateBAuditAttemptView(FrozenProviderContract):
    request_attempt_id: UUID
    slice_id: str = Field(min_length=1, max_length=64)
    endpoint_id: str = Field(min_length=1, max_length=128)
    attempt_kind: Literal["INITIAL", "RETRY"]
    attempt_number: int = Field(ge=1, le=4)
    retry_number: int = Field(ge=0, le=1)
    started_at: AwareUtcDateTime
    completed_at: AwareUtcDateTime | None
    status: str = Field(min_length=1, max_length=32)
    http_status: int | None = Field(default=None, ge=100, le=599)
    response_bytes: int = Field(ge=0, le=52_428_800)
    safe_error_code: str | None = Field(default=None, max_length=128)
    socket_opened: bool | None


class GateBAuditConsumptionView(FrozenProviderContract):
    consumption_id: UUID
    request_attempt_id: UUID
    reserved_bytes: int = Field(ge=1, le=52_428_800)
    actual_bytes: int | None = Field(default=None, ge=0, le=52_428_800)
    socket_opened: bool | None
    state: str = Field(min_length=1, max_length=16)
    reserved_at: AwareUtcDateTime
    settled_at: AwareUtcDateTime | None


class GateBAuditArtifactView(FrozenProviderContract):
    artifact_id: UUID
    request_attempt_id: UUID
    source_identity: str | None = Field(default=None, max_length=512)
    source_checksum: Checksum
    content_type: str | None = Field(default=None, max_length=128)
    byte_count: int | None = Field(default=None, ge=1, le=52_428_800)
    blob_key: str | None = Field(default=None, max_length=512)
    acquired_at: AwareUtcDateTime
    source_published_at: AwareUtcDateTime | None
    synthetic_status: str | None = Field(default=None, max_length=32)
    license_policy_id: UUID | None = None


class GateBAuditManifestView(FrozenProviderContract):
    manifest_id: UUID
    artifact_id: UUID
    batch_checksum: Checksum
    manifest_checksum: Checksum
    adapter_version: str = Field(min_length=1, max_length=32)
    parser_version: str = Field(min_length=1, max_length=32)
    schema_version: str = Field(min_length=1, max_length=64)
    record_count: int = Field(ge=0)
    warning_codes: tuple[str, ...] = Field(max_length=64)


class GateBAuditDataQualityIssueView(FrozenProviderContract):
    issue_id: UUID
    manifest_id: UUID
    rule_code: str = Field(min_length=1, max_length=128)
    severity: str = Field(min_length=1, max_length=16)
    status: str = Field(min_length=1, max_length=16)
    safe_detail: str = Field(min_length=1, max_length=1024)


class GateBAuditView(FrozenProviderContract):
    grant_id: UUID
    grant_checksum: Checksum
    grant_state: str = Field(min_length=1, max_length=16)
    approval_id: UUID | None = None
    approval_state: str | None = Field(default=None, max_length=16)
    approval_expires_at: AwareUtcDateTime | None = None
    authorization_id: UUID
    candidate: dict[str, str]
    provider: str = Field(min_length=1, max_length=64)
    plan_id: UUID
    plan_checksum: Checksum
    resources: tuple[GateBAuditResourceView, ...] = Field(max_length=3)
    sync_run_id: UUID
    sync_run_status: str | None = Field(default=None, max_length=16)
    consumed_requests: int = Field(default=0, ge=0, le=4)
    consumed_attempts: int = Field(default=0, ge=0, le=4)
    consumed_retries: int = Field(default=0, ge=0, le=1)
    consumed_bytes: int = Field(default=0, ge=0, le=52_428_800)
    started_at: AwareUtcDateTime | None = None
    completed_at: AwareUtcDateTime | None = None
    attempts: tuple[GateBAuditAttemptView, ...] = Field(max_length=4)
    consumptions: tuple[GateBAuditConsumptionView, ...] = Field(max_length=4)
    artifacts: tuple[GateBAuditArtifactView, ...] = Field(max_length=3)
    manifests: tuple[GateBAuditManifestView, ...] = Field(default=(), max_length=3)
    document_version_id: UUID | None = None
    document_checksum: Checksum | None = None
    citation_ids: tuple[UUID, ...] = Field(default=(), max_length=10_000)
    citation_parser_versions: tuple[str, ...] = Field(default=(), max_length=10_000)
    citation_sanitizer_versions: tuple[str, ...] = Field(default=(), max_length=10_000)
    data_quality_issues: tuple[GateBAuditDataQualityIssueView, ...] = Field(
        default=(), max_length=1_000
    )
    terminal_validation_id: UUID | None = None
    terminal_status: str | None = Field(default=None, max_length=32)
    terminal_stage: str | None = Field(default=None, max_length=64)
    warning_codes: tuple[str, ...] = Field(default=(), max_length=64)
    stop_reason: str | None = Field(default=None, max_length=128)
    failed_ordinal: int | None = Field(default=None, ge=0, le=2)
    failed_slice_id: str | None = Field(default=None, max_length=64)
    artifact_id: UUID | None = None
    content_checksum: Checksum | None = None
    retrieved_at: AwareUtcDateTime | None = None
    request_attempt_id: UUID | None = None


class SecTerminalStore(Protocol):
    def commit(
        self,
        result: LiveValidationResult,
        issues: tuple[ProviderQualityIssue, ...],
    ) -> UUID: ...


class GateBAuditRepository(Protocol):
    def get(self) -> GateBAuditView | None: ...


class SecExecutionStartPort(SecAttemptReservationPort, Protocol):
    def start_execution(
        self,
        request: SecAttemptReservationRequest,
    ) -> SecExecutionStartResult: ...


class SecDataQualityStopService:
    """Commit the auditable Data Quality terminal and expose no downstream ports."""

    def __init__(
        self,
        *,
        validator: ProviderDataQualityValidator,
        terminal_store: SecTerminalStore,
    ) -> None:
        self._validator = validator
        self._terminal_store = terminal_store

    def evaluate(
        self,
        completed_resources: tuple[CompletedSecResource, ...],
        document: SecDocumentCitationResult,
    ) -> LiveValidationResult:
        if tuple(item.resource.slice_id for item in completed_resources) != (
            "SEC_SUBMISSIONS",
            "SEC_FILING_INDEX",
            "SEC_PRIMARY_DOCUMENT",
        ):
            raise LiveEvidenceValidationError("GATE_B_RESOURCE_SET_INCOMPLETE")
        primary = completed_resources[-1]
        committed = primary.committed
        validated = primary.validated
        if primary.resource.artifact_kind is not SecArtifactKind.PRIMARY_FILING_DOCUMENT:
            raise LiveEvidenceValidationError("GATE_B_PRIMARY_DOCUMENT_INVALID")
        if (
            committed.artifact_id != validated.artifact_id
            or committed.request_attempt_id != validated.request_attempt_id
            or committed.content_checksum != validated.source_checksum
        ):
            raise ValueError("SEC_DATA_QUALITY_LINEAGE_MISMATCH")
        quality = self._validator.validate(
            validated.batch,
            ProviderQualityContext(
                research_as_of_time=validated.context.research_as_of_time,
                provider_definition_id=validated.context.provider_definition_id,
                provider_capability_id=validated.context.provider_capability_id,
                raw_artifact_id=validated.artifact_id,
                source_checksum=validated.source_checksum,
                synthetic_status=validated.context.synthetic_status,
                allowed_currencies=(),
                allowed_units=(),
            ),
        )
        result = LiveValidationResult(
            status="PASSED" if quality.passed else "BLOCKED",
            artifact_id=committed.artifact_id,
            manifest_id=committed.manifest_id,
            request_attempt_id=committed.request_attempt_id,
            document_version_id=document.document_version_id,
            citation_ids=document.citation_ids,
            data_quality_issue_count=len(quality.issues),
        )
        audit_event_id = self._terminal_store.commit(result, quality.issues)
        return result.model_copy(update={"audit_event_id": audit_event_id})

    def block_resource_failure(
        self,
        resource: SecAuthorizedResource,
        *,
        request_attempt_id: UUID,
        stop_reason: str,
    ) -> LiveValidationResult:
        result = LiveValidationResult(
            status="BLOCKED",
            terminal_stage="RESOURCE_ORCHESTRATION",
            request_attempt_id=request_attempt_id,
            data_quality_issue_count=0,
            stop_reason=stop_reason,
            failed_ordinal=resource.ordinal,
            failed_slice_id=resource.slice_id,
        )
        audit_event_id = self._terminal_store.commit(result, ())
        return result.model_copy(update={"audit_event_id": audit_event_id})


class SecTransportPort(Protocol):
    def execute(
        self,
        execution: AuthorizedGateBExecution,
        *,
        plan: ProviderSyncPlanRecord,
        slice_id: str,
        contact_reference: CredentialReferenceRecord,
        permit: SecAttemptPermit,
    ) -> SecTransportResult: ...


class SecDocumentCitationPort(Protocol):
    def admit(
        self,
        committed: CommittedSecSettlement,
        validated: ValidatedSecSettlement,
    ) -> SecDocumentCitationResult: ...


class SecGateBPilotApplication:
    """Authorized offline-composable pilot that terminates at Data Quality."""

    def __init__(
        self,
        *,
        transport: SecTransportPort,
        adapter: SecEdgarAdapter,
        settlement: SecArtifactSettlementService,
        documents: SecDocumentCitationPort,
        data_quality: SecDataQualityStopService,
        artifact_id_factory: Callable[[], UUID],
        reservations: SecAttemptReservationPort,
        ingestion_context_factory: Callable[[SecAuthorizedResource], SecIngestionContext],
    ) -> None:
        self._transport = transport
        self._adapter = adapter
        self._settlement = settlement
        self._documents = documents
        self._data_quality = data_quality
        self._artifact_id_factory = artifact_id_factory
        self._reservations = reservations
        self._ingestion_context_factory = ingestion_context_factory

    def execute_authorized(
        self,
        start: SecExecutionStartResult,
        *,
        plan: ProviderSyncPlanRecord,
        contact_reference: CredentialReferenceRecord,
    ) -> LiveValidationResult:
        execution = start.execution
        authorized_plan = bind_sec_authorized_plan(execution, plan)
        completed: list[CompletedSecResource] = []
        permit = start.initial_permit
        next_attempt_number = 1
        for resource in authorized_plan.resources:
            if resource.ordinal == 0:
                self._require_permit(execution, resource, permit, expected_attempt=1)
            else:
                permit = self._reserve_resource(
                    execution,
                    resource,
                    attempt_number=next_attempt_number,
                )
            completed_resource, last_attempt_number = self._execute_resource(
                execution,
                plan=plan,
                resource=resource,
                permit=permit,
                contact_reference=contact_reference,
            )
            completed.append(completed_resource)
            try:
                self._require_dependency_lineage(authorized_plan.resources, completed)
            except LiveEvidenceValidationError as exc:
                self._data_quality.block_resource_failure(
                    resource,
                    request_attempt_id=completed_resource.committed.request_attempt_id,
                    stop_reason=exc.code,
                )
                raise
            next_attempt_number = last_attempt_number + 1

        primary = completed[-1]
        document = self._documents.admit(primary.committed, primary.validated)
        return self._data_quality.evaluate(tuple(completed), document)

    def _execute_resource(
        self,
        execution: AuthorizedGateBExecution,
        *,
        plan: ProviderSyncPlanRecord,
        resource: SecAuthorizedResource,
        permit: SecAttemptPermit,
        contact_reference: CredentialReferenceRecord,
    ) -> tuple[CompletedSecResource, int]:
        transport_result = self._transport.execute(
            execution,
            plan=plan,
            slice_id=resource.slice_id,
            contact_reference=contact_reference,
            permit=permit,
        )
        for prior_attempt in transport_result.attempts[:-1]:
            self._settlement.settle_failure(prior_attempt)
        if transport_result.status is not SecTransportStatus.COMPLETED:
            if transport_result.attempts:
                failed_attempt = transport_result.attempts[-1]
                self._settlement.settle_failure(failed_attempt)
                self._data_quality.block_resource_failure(
                    resource,
                    request_attempt_id=failed_attempt.permit.request_attempt_id,
                    stop_reason=(
                        failed_attempt.safe_error_code or "SEC_RESOURCE_EXECUTION_BLOCKED"
                    ),
                )
            raise LiveEvidenceValidationError(transport_result.reason_code)
        attempt = transport_result.attempts[-1]
        try:
            ingestion_context = self._ingestion_context_factory(resource)
            self._require_context(resource, ingestion_context)
            validated = validate_sec_response(
                attempt,
                resource,
                ingestion_context,
                self._adapter,
                artifact_id=self._artifact_id_factory(),
            )
        except ValueError as exc:
            failure_code = (
                exc.code
                if isinstance(exc, LiveEvidenceValidationError)
                else (str(exc) if str(exc).startswith("SEC_") else "SEC_RESPONSE_VALIDATION_FAILED")
            )
            failed_attempt = attempt.model_copy(update={"safe_error_code": failure_code})
            self._settlement.settle_failure(failed_attempt)
            self._data_quality.block_resource_failure(
                resource,
                request_attempt_id=attempt.permit.request_attempt_id,
                stop_reason=failure_code,
            )
            raise LiveEvidenceValidationError(failure_code) from None
        committed = self._settlement.settle(validated, attempt)
        return (
            CompletedSecResource(
                resource=resource,
                committed=committed,
                validated=validated,
            ),
            attempt.permit.attempt_number,
        )

    def _reserve_resource(
        self,
        execution: AuthorizedGateBExecution,
        resource: SecAuthorizedResource,
        *,
        attempt_number: int,
    ) -> SecAttemptPermit:
        permit = self._reservations.reserve(
            SecAttemptReservationRequest(
                authorization_id=execution.authorization_id,
                plan_id=execution.plan_id,
                plan_checksum=execution.plan_checksum,
                slice_id=resource.slice_id,
                endpoint_id=resource.request.endpoint_id,
                attempt_number=attempt_number,
                kind=SecAttemptKind.INITIAL,
            )
        )
        self._require_permit(execution, resource, permit, expected_attempt=attempt_number)
        return permit

    @staticmethod
    def _require_permit(
        execution: AuthorizedGateBExecution,
        resource: SecAuthorizedResource,
        permit: SecAttemptPermit,
        *,
        expected_attempt: int,
    ) -> None:
        if (
            permit.authorization_id != execution.authorization_id
            or permit.plan_id != execution.plan_id
            or permit.plan_checksum != execution.plan_checksum
            or permit.slice_id != resource.slice_id
            or permit.endpoint_id != resource.request.endpoint_id
            or permit.attempt_number != expected_attempt
            or permit.kind is not SecAttemptKind.INITIAL
        ):
            raise LiveEvidenceValidationError("SEC_ATTEMPT_RESERVATION_REQUIRED")

    @staticmethod
    def _require_context(
        resource: SecAuthorizedResource,
        context: SecIngestionContext,
    ) -> None:
        if (
            context.artifact_kind is not resource.artifact_kind
            or context.source_endpoint_type != resource.request.endpoint_id
        ):
            raise LiveEvidenceValidationError("SEC_INGESTION_CONTEXT_MISMATCH")

    @staticmethod
    def _require_dependency_lineage(
        resources: tuple[SecAuthorizedResource, ...],
        completed: list[CompletedSecResource],
    ) -> None:
        primary_filename = resources[2].request.path.rsplit("/", maxsplit=1)[-1]
        if len(completed) == 1:
            index_path = resources[1].request.path
            records = completed[0].validated.batch.records
            matched = any(
                record.text_values.get("primary_document") == primary_filename
                and str(record.text_values.get("accession_number", "")).replace("-", "")
                in index_path
                for record in records
            )
            if not matched:
                raise LiveEvidenceValidationError("SEC_RESOURCE_DEPENDENCY_INVALID")
        elif len(completed) == 2 and primary_filename.encode() not in completed[1].validated.body:
            raise LiveEvidenceValidationError("SEC_RESOURCE_DEPENDENCY_INVALID")


class AuthorizedSecGateBOfflineApplication:
    """Explicit offline production root; the default CLI remains blocked."""

    def __init__(
        self,
        *,
        execution_start: SecExecutionStartPort,
        pilot: SecGateBPilotApplication,
        audit_repository: GateBAuditRepository,
    ) -> None:
        self._execution_start = execution_start
        self._pilot = pilot
        self._audit_repository = audit_repository

    def execute_authorized(
        self,
        validation: GateBAuthorizationValidation,
        *,
        plan: ProviderSyncPlanRecord,
        contact_reference: CredentialReferenceRecord,
    ) -> GateBAuditView:
        authorized_plan = bind_sec_authorized_plan(validation, plan)
        initial = authorized_plan.resources[0]
        start = self._execution_start.start_execution(
            SecAttemptReservationRequest(
                authorization_id=validation.authorization_id,
                plan_id=validation.plan_id,
                plan_checksum=validation.plan_checksum,
                slice_id=initial.slice_id,
                endpoint_id=initial.request.endpoint_id,
                attempt_number=1,
                kind=SecAttemptKind.INITIAL,
            )
        )
        result = self._pilot.execute_authorized(
            start,
            plan=plan,
            contact_reference=contact_reference,
        )
        audit = self._audit_repository.get()
        if (
            audit is None
            or tuple(resource.slice_id for resource in audit.resources)
            != ("SEC_SUBMISSIONS", "SEC_FILING_INDEX", "SEC_PRIMARY_DOCUMENT")
            or audit.terminal_status != result.status
            or audit.terminal_stage != "DATA_QUALITY"
        ):
            raise LiveEvidenceValidationError("GATE_B_AUDIT_INCOMPLETE")
        return audit


class SecSettlementTransaction(Protocol):
    def __enter__(self) -> SecSettlementTransaction: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def settle_attempt(self, value: ProviderRequestAttemptSettlement) -> object: ...

    def settle_consumption(self, value: ConsumptionSettlementRequest) -> object: ...

    def add_artifact(self, value: ProviderRawArtifactReservation) -> object: ...

    def add_manifest(
        self, value: ProviderIngestionManifestWrite
    ) -> ProviderIngestionManifestRecord: ...


class SecArtifactStoragePort(Protocol):
    def write(self, draft: ProviderRawArtifactDraft, content: bytes) -> StoredProviderArtifact: ...


class SecArtifactSettlementService:
    """Write bytes first, then atomically commit authoritative database lineage."""

    def __init__(
        self,
        *,
        storage: SecArtifactStoragePort,
        transaction_factory: Callable[[], SecSettlementTransaction],
    ) -> None:
        self._storage = storage
        self._transaction_factory = transaction_factory

    def settle(
        self,
        value: ValidatedSecSettlement,
        attempt: SecPhysicalAttempt,
    ) -> CommittedSecSettlement:
        if attempt.permit.request_attempt_id != value.request_attempt_id:
            raise ValueError("SEC_SETTLEMENT_ATTEMPT_MISMATCH")
        response = attempt.response
        if response is None or attempt.socket_opened is not True:
            raise ValueError("SEC_SETTLEMENT_RESPONSE_REQUIRED")
        stored = self._storage.write(value.raw_artifact_draft, value.body)
        artifact_write = ProviderRawArtifactWrite(
            provider_definition_id=value.context.provider_definition_id,
            provider_capability_id=value.context.provider_capability_id,
            sync_run_id=value.context.sync_run_id,
            request_attempt_id=value.request_attempt_id,
            license_policy_id=value.context.license_policy_id,
            source_identity=value.context.source_identity,
            source_checksum=value.source_checksum,
            byte_count=stored.byte_count,
            content_type=stored.content_type,
            blob_key=stored.blob_key,
            acquired_at=value.context.retrieved_at,
            source_published_at=value.context.source_published_at,
            synthetic_status=value.context.synthetic_status,
        )
        provisional_artifact = ProviderRawArtifactRecord(
            id=value.artifact_id,
            created_at=value.context.retrieved_at,
            **artifact_write.model_dump(mode="python"),
        )
        manifest = build_ingestion_manifest(
            provisional_artifact,
            ProviderManifestBatch(
                record_identities=tuple(
                    sorted(record.identity.checksum for record in value.batch.records)
                ),
                batch_checksum=value.batch.batch_checksum,
            ),
            value.context.as_ingestion_context(value.request_attempt_id),
        )
        with self._transaction_factory() as transaction:
            transaction.settle_attempt(
                ProviderRequestAttemptSettlement(
                    id=value.request_attempt_id,
                    status=ProviderSyncSliceStatus.COMPLETED,
                    response_status_code=response.status_code,
                    response_bytes=len(response.body),
                    completed_at=attempt.completed_at,
                )
            )
            transaction.settle_consumption(
                ConsumptionSettlementRequest(
                    authorization_id=attempt.permit.authorization_id,
                    request_attempt_id=value.request_attempt_id,
                    actual_bytes=len(response.body),
                    socket_opened=True,
                    state=ConsumptionState.SETTLED,
                    settled_at=attempt.completed_at,
                )
            )
            transaction.add_artifact(
                ProviderRawArtifactReservation(id=value.artifact_id, value=artifact_write)
            )
            manifest_record = transaction.add_manifest(manifest)
        return CommittedSecSettlement(
            artifact_id=value.artifact_id,
            manifest_id=manifest_record.id,
            request_attempt_id=value.request_attempt_id,
            storage_uri=stored.storage_uri,
            content_checksum=stored.checksum,
            manifest_checksum=manifest.manifest_checksum,
        )

    def settle_failure(self, attempt: SecPhysicalAttempt) -> None:
        """Terminally settle a committed permit without creating an artifact."""

        response = attempt.response
        response_bytes = len(response.body) if response is not None else 0
        demonstrably_unstarted = attempt.socket_opened is False and response_bytes == 0
        with self._transaction_factory() as transaction:
            transaction.settle_attempt(
                ProviderRequestAttemptSettlement(
                    id=attempt.permit.request_attempt_id,
                    status=ProviderSyncSliceStatus.BLOCKED,
                    response_status_code=(response.status_code if response is not None else None),
                    response_bytes=response_bytes,
                    completed_at=attempt.completed_at,
                    safe_error_code=attempt.safe_error_code or "SEC_TRANSPORT_BLOCKED",
                )
            )
            transaction.settle_consumption(
                ConsumptionSettlementRequest(
                    authorization_id=attempt.permit.authorization_id,
                    request_attempt_id=attempt.permit.request_attempt_id,
                    actual_bytes=response_bytes,
                    socket_opened=not demonstrably_unstarted,
                    state=(
                        ConsumptionState.ABANDONED
                        if demonstrably_unstarted
                        else ConsumptionState.SETTLED
                    ),
                    settled_at=attempt.completed_at,
                )
            )


def validate_sec_response(
    attempt: SecPhysicalAttempt,
    resource: SecAuthorizedResource,
    context: SecIngestionContext,
    adapter: SecEdgarAdapter,
    *,
    artifact_id: UUID,
) -> ValidatedSecSettlement:
    """Validate exact authorized bytes and build frozen drafts without persistence."""

    response = attempt.response
    if response is None or not 200 <= response.status_code < 300:
        raise ValueError("SEC_RESPONSE_NOT_SUCCESSFUL")
    body = response.body
    if not body or len(body) > resource.max_response_bytes:
        raise ValueError("SEC_RESPONSE_SIZE_INVALID")
    content_type = (response.content_type or "").split(";", maxsplit=1)[0].strip().lower()
    accepted = {value.lower() for value in resource.request.accepted_content_types}
    if content_type not in accepted:
        raise ValueError("SEC_RESPONSE_MIME_INVALID")
    if (
        attempt.permit.plan_id != resource.plan_id
        or attempt.permit.plan_checksum != resource.plan_checksum
        or attempt.permit.slice_id != resource.slice_id
        or attempt.permit.endpoint_id != resource.request.endpoint_id
    ):
        raise ValueError("SEC_SETTLEMENT_RESOURCE_MISMATCH")
    source_checksum = hashlib.sha256(body).hexdigest()
    manifest_checksum = provider_checksum(
        {
            "artifact_id": artifact_id,
            "request_attempt_id": attempt.permit.request_attempt_id,
            "source_identity": context.source_identity,
            "source_checksum": source_checksum,
            "schema_version": context.schema_version,
        }
    )
    batch = adapter.parse_response(
        body,
        SecParseContext(
            provider_definition_id=context.provider_definition_id,
            provider_capability_id=context.provider_capability_id,
            raw_artifact_id=artifact_id,
            source_checksum=source_checksum,
            manifest_checksum=manifest_checksum,
            source_identity=context.source_identity,
            source_endpoint_type=context.source_endpoint_type,
            artifact_kind=context.artifact_kind,
            content_type=content_type,
            research_as_of_time=context.research_as_of_time,
            retrieved_at=context.retrieved_at,
            source_published_at=context.source_published_at,
            expected_accession_number=context.expected_accession_number,
            expected_document_path=context.expected_document_path,
            synthetic_status=context.synthetic_status,
        ),
    )
    return ValidatedSecSettlement(
        artifact_id=artifact_id,
        request_attempt_id=attempt.permit.request_attempt_id,
        source_checksum=source_checksum,
        content_type=content_type,
        body=body,
        batch=batch,
        raw_artifact_draft=ProviderRawArtifactDraft(
            content_type=content_type,
            expected_checksum=source_checksum,
            store_raw_permitted=True,
        ),
        context=context,
    )
