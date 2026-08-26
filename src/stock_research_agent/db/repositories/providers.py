"""Transaction-neutral PostgreSQL repositories for Provider governance."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from stock_research_agent.db.models.providers import (
    ProviderCapability,
    ProviderCircuitBreaker,
    ProviderCredentialReference,
    ProviderDataQualityIssue,
    ProviderDeadLetter,
    ProviderDefinition,
    ProviderHealthSnapshot,
    ProviderIngestionManifest,
    ProviderLicensePolicy,
    ProviderPolicy,
    ProviderRawArtifact,
    ProviderRequestAttempt,
    ProviderSyncCheckpoint,
    ProviderSyncPlan,
    ProviderSyncRequest,
    ProviderSyncRun,
)
from stock_research_agent.domain.providers.artifacts import (
    ProviderDataQualityIssueRecord,
    ProviderDataQualityIssueWrite,
    ProviderDeadLetterRecord,
    ProviderDeadLetterStatus,
    ProviderDeadLetterWrite,
    ProviderIngestionManifestRecord,
    ProviderIngestionManifestWrite,
    ProviderIssueSeverity,
    ProviderIssueStatus,
    ProviderRawArtifactRecord,
    ProviderRawArtifactReservation,
    ProviderRawArtifactWrite,
)
from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.capabilities import (
    ProviderCapabilityRecord,
    ProviderCapabilityWrite,
)
from stock_research_agent.domain.providers.credentials import (
    CredentialReferenceRecord,
    CredentialReferenceWrite,
    CredentialResolverKind,
)
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderConfigurationStatus,
    ProviderCredentialStatus,
    ProviderDefinitionStatus,
    ProviderLicenseStatus,
    ProviderLiveValidationStatus,
    ProviderProductionStatus,
    ProviderRunStatus,
    ProviderSyncSliceStatus,
    ProviderSyntheticStatus,
)
from stock_research_agent.domain.providers.health import (
    ProviderHealthSnapshotRecord,
    ProviderHealthSnapshotWrite,
    ProviderReadinessStatus,
)
from stock_research_agent.domain.providers.licenses import (
    LicensePermission,
    SourceLicensePolicyRecord,
    SourceLicensePolicyWrite,
)
from stock_research_agent.domain.providers.policies import (
    ProviderPolicyRecord,
    ProviderPolicyWrite,
)
from stock_research_agent.domain.providers.schemas import (
    ProviderDefinitionRecord,
    ProviderDefinitionWrite,
)
from stock_research_agent.domain.providers.sync import (
    CheckpointAdvance,
    CheckpointScope,
    ProviderCheckpointRecord,
    ProviderExecutionMode,
    ProviderRequestAttemptRecord,
    ProviderRequestAttemptReservation,
    ProviderRequestAttemptSettlement,
    ProviderRequestAttemptWrite,
    ProviderRunStateMachine,
    ProviderRunTransition,
    ProviderSyncPlanRecord,
    ProviderSyncPlanWrite,
    ProviderSyncRequestRecord,
    ProviderSyncRequestWrite,
    ProviderSyncRunRecord,
    ProviderSyncRunWrite,
)


class ProviderRepositoryConflict(ValueError):
    """An immutable Provider identity already exists with different content."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _checksum(value: BaseModel) -> str:
    excluded = {"id", "checksum", "created_at"} & set(type(value).model_fields)
    return provider_checksum(value.model_dump(mode="json", exclude=excluded))


def _idempotent_add[
    RowModel: (
        ProviderDefinition,
        ProviderCapability,
        ProviderPolicy,
        ProviderLicensePolicy,
        ProviderCredentialReference,
    )
](
    session: Session,
    query: Select[tuple[RowModel]],
    row: RowModel,
    checksum: str,
    conflict_code: str,
) -> RowModel:
    existing = session.scalar(query)
    if existing is not None:
        if existing.checksum != checksum:
            raise ProviderRepositoryConflict(conflict_code)
        return existing
    session.add(row)
    session.flush()
    return row


class SqlAlchemyProviderDefinitionRepository:
    """Persist immutable Provider definitions without owning the transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_definition(
        self,
        value: ProviderDefinitionWrite,
    ) -> ProviderDefinitionRecord:
        checksum = _checksum(value)
        row = _idempotent_add(
            self._session,
            select(ProviderDefinition).where(
                ProviderDefinition.code == value.code,
                ProviderDefinition.definition_version == value.definition_version,
            ),
            ProviderDefinition(
                **value.model_dump(mode="python"),
                checksum=checksum,
            ),
            checksum,
            "PROVIDER_DEFINITION_CONFLICT",
        )
        return _definition_record(row)

    def get_definition(
        self,
        code: str,
        version: str,
    ) -> ProviderDefinitionRecord | None:
        row = self._session.scalar(
            select(ProviderDefinition).where(
                ProviderDefinition.code == code,
                ProviderDefinition.definition_version == version,
            )
        )
        return None if row is None else _definition_record(row)

    def list_definitions(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[ProviderDefinitionRecord, ...]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("PROVIDER_QUERY_BOUNDS_INVALID")
        rows = self._session.scalars(
            select(ProviderDefinition)
            .order_by(
                ProviderDefinition.code,
                ProviderDefinition.definition_version,
                ProviderDefinition.id,
            )
            .limit(limit)
            .offset(offset)
        )
        return tuple(_definition_record(row) for row in rows)


class SqlAlchemyProviderGovernanceRepository:
    """Persist exact versioned capability, policy, license and credential metadata."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_capability(
        self,
        value: ProviderCapabilityWrite,
    ) -> ProviderCapabilityRecord:
        checksum = _checksum(value)
        row = _idempotent_add(
            self._session,
            select(ProviderCapability).where(
                ProviderCapability.provider_definition_id == value.provider_definition_id,
                ProviderCapability.code == value.code,
                ProviderCapability.capability_version == value.capability_version,
            ),
            ProviderCapability(
                **value.model_dump(mode="python", exclude={"id", "checksum", "created_at"}),
                checksum=checksum,
            ),
            checksum,
            "PROVIDER_CAPABILITY_CONFLICT",
        )
        return _capability_record(row)

    def add_policy(self, value: ProviderPolicyWrite) -> ProviderPolicyRecord:
        checksum = _checksum(value)
        row = _idempotent_add(
            self._session,
            select(ProviderPolicy).where(
                ProviderPolicy.provider_definition_id == value.provider_definition_id,
                ProviderPolicy.policy_version == value.policy_version,
            ),
            ProviderPolicy(
                **value.model_dump(mode="python", exclude={"id", "checksum", "created_at"}),
                checksum=checksum,
            ),
            checksum,
            "PROVIDER_POLICY_CONFLICT",
        )
        return _policy_record(row)

    def add_license_policy(
        self,
        value: SourceLicensePolicyWrite,
    ) -> SourceLicensePolicyRecord:
        checksum = _checksum(value)
        row = _idempotent_add(
            self._session,
            select(ProviderLicensePolicy).where(
                ProviderLicensePolicy.provider_definition_id == value.provider_definition_id,
                ProviderLicensePolicy.policy_version == value.policy_version,
            ),
            ProviderLicensePolicy(
                **value.model_dump(mode="python", exclude={"id", "checksum", "created_at"}),
                checksum=checksum,
            ),
            checksum,
            "PROVIDER_LICENSE_POLICY_CONFLICT",
        )
        return _license_record(row)

    def add_credential_reference(
        self,
        value: CredentialReferenceWrite,
    ) -> CredentialReferenceRecord:
        checksum = _checksum(value)
        row = _idempotent_add(
            self._session,
            select(ProviderCredentialReference).where(
                ProviderCredentialReference.provider_definition_id == value.provider_definition_id,
                ProviderCredentialReference.reference_version == value.reference_version,
            ),
            ProviderCredentialReference(
                **value.model_dump(mode="python", exclude={"id", "checksum", "created_at"}),
                checksum=checksum,
            ),
            checksum,
            "PROVIDER_CREDENTIAL_REFERENCE_CONFLICT",
        )
        return _credential_record(row)

    def add_health_snapshot(
        self,
        value: ProviderHealthSnapshotWrite,
    ) -> ProviderHealthSnapshotRecord:
        row = ProviderHealthSnapshot(
            provider_definition_id=value.provider_definition_id,
            status=value.status.value,
            configuration_status=value.configuration_status.value,
            credential_status=value.credential_status.value,
            license_status=value.license_status.value,
            live_validation_status=value.live_validation_status.value,
            limiting_reasons=list(value.limiting_reasons),
            observed_at=value.observed_at,
            checksum=value.checksum,
        )
        self._session.add(row)
        self._session.flush()
        return _health_record(row)

    def get_capability(
        self,
        provider_id: UUID,
        code: str,
        version: str,
    ) -> ProviderCapabilityRecord | None:
        row = self._session.scalar(
            select(ProviderCapability).where(
                ProviderCapability.provider_definition_id == provider_id,
                ProviderCapability.code == code,
                ProviderCapability.capability_version == version,
            )
        )
        return None if row is None else _capability_record(row)

    def get_policy(
        self,
        provider_id: UUID,
        version: str,
    ) -> ProviderPolicyRecord | None:
        row = self._session.scalar(
            select(ProviderPolicy).where(
                ProviderPolicy.provider_definition_id == provider_id,
                ProviderPolicy.policy_version == version,
            )
        )
        return None if row is None else _policy_record(row)

    def get_license_policy(
        self,
        provider_id: UUID,
        version: str,
    ) -> SourceLicensePolicyRecord | None:
        row = self._session.scalar(
            select(ProviderLicensePolicy).where(
                ProviderLicensePolicy.provider_definition_id == provider_id,
                ProviderLicensePolicy.policy_version == version,
            )
        )
        return None if row is None else _license_record(row)

    def get_credential_reference(
        self,
        reference_id: UUID,
    ) -> CredentialReferenceRecord | None:
        row = self._session.get(ProviderCredentialReference, reference_id)
        return None if row is None else _credential_record(row)

    def get_latest_health_snapshot(
        self,
        provider_id: UUID,
    ) -> ProviderHealthSnapshotRecord | None:
        row = self._session.scalar(
            select(ProviderHealthSnapshot)
            .where(ProviderHealthSnapshot.provider_definition_id == provider_id)
            .order_by(
                ProviderHealthSnapshot.observed_at.desc(),
                ProviderHealthSnapshot.created_at.desc(),
                ProviderHealthSnapshot.id.desc(),
            )
            .limit(1)
        )
        return None if row is None else _health_record(row)


class SqlAlchemyProviderSyncRepository:
    """Persist finite sync lifecycles without committing or creating Sessions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_request(
        self,
        value: ProviderSyncRequestWrite,
    ) -> ProviderSyncRequestRecord:
        existing = self._session.scalar(
            select(ProviderSyncRequest).where(
                ProviderSyncRequest.idempotency_key == value.idempotency_key
            )
        )
        if existing is not None:
            if existing.request_checksum != value.request_checksum:
                raise ProviderRepositoryConflict("PROVIDER_SYNC_REQUEST_CONFLICT")
            return _sync_request_record(existing)
        row = ProviderSyncRequest(
            **value.model_dump(
                mode="python",
                exclude={"execution_mode"},
            ),
            execution_mode=value.execution_mode.value,
        )
        self._session.add(row)
        self._session.flush()
        return _sync_request_record(row)

    def add_plan(self, value: ProviderSyncPlanWrite) -> ProviderSyncPlanRecord:
        existing = self._session.scalar(
            select(ProviderSyncPlan).where(
                ProviderSyncPlan.sync_request_id == value.sync_request_id,
                ProviderSyncPlan.plan_checksum == value.plan_checksum,
            )
        )
        if existing is not None:
            return _sync_plan_record(existing)
        row = ProviderSyncPlan(
            sync_request_id=value.sync_request_id,
            adapter_version=value.adapter_version,
            checkpoint_revision=value.checkpoint_revision,
            slices=list(value.slices),
            slice_count=len(value.slices),
            plan_checksum=value.plan_checksum,
        )
        self._session.add(row)
        self._session.flush()
        return _sync_plan_record(row)

    def create_run(self, value: ProviderSyncRunWrite) -> ProviderSyncRunRecord:
        existing = self._session.scalar(
            select(ProviderSyncRun).where(
                ProviderSyncRun.sync_request_id == value.sync_request_id,
                ProviderSyncRun.sync_plan_id == value.sync_plan_id,
            )
        )
        if existing is not None:
            expected = (
                value.provider_definition_id,
                value.provider_capability_id,
            )
            actual = (
                existing.provider_definition_id,
                existing.provider_capability_id,
            )
            if actual != expected:
                raise ProviderRepositoryConflict("PROVIDER_SYNC_RUN_CONFLICT")
            return _sync_run_record(existing)
        row = ProviderSyncRun(
            **value.model_dump(mode="python"),
            status=ProviderRunStatus.PLANNED.value,
            consumed_requests=0,
            consumed_bytes=0,
            consumed_attempts=0,
            warning_codes=[],
        )
        self._session.add(row)
        self._session.flush()
        return _sync_run_record(row)

    def get_run(
        self,
        run_id: UUID,
        *,
        for_update: bool = False,
    ) -> ProviderSyncRunRecord | None:
        query = select(ProviderSyncRun).where(ProviderSyncRun.id == run_id)
        if for_update:
            query = query.with_for_update()
        row = self._session.scalar(query)
        return None if row is None else _sync_run_record(row)

    def transition(
        self,
        run_id: UUID,
        value: ProviderRunTransition,
    ) -> ProviderSyncRunRecord:
        row = self._session.scalar(
            select(ProviderSyncRun).where(ProviderSyncRun.id == run_id).with_for_update()
        )
        if row is None:
            raise LookupError("PROVIDER_SYNC_RUN_NOT_FOUND")
        ProviderRunStateMachine.transition(ProviderRunStatus(row.status), value.target)
        row.status = value.target.value
        row.consumed_requests = value.consumed_requests
        row.consumed_bytes = value.consumed_bytes
        row.consumed_attempts = value.consumed_attempts
        row.started_at = value.started_at
        row.paused_at = value.paused_at
        row.completed_at = value.completed_at
        row.lease_owner = value.lease_owner
        row.lease_expires_at = value.lease_expires_at
        row.warning_codes = list(value.warning_codes)
        self._session.flush()
        return _sync_run_record(row)

    def append_attempt(
        self,
        value: ProviderRequestAttemptWrite,
    ) -> ProviderRequestAttemptRecord:
        existing = self._session.scalar(
            select(ProviderRequestAttempt).where(
                ProviderRequestAttempt.sync_run_id == value.sync_run_id,
                ProviderRequestAttempt.slice_id == value.slice_id,
                ProviderRequestAttempt.attempt_number == value.attempt_number,
            )
        )
        if existing is not None:
            candidate = value.model_dump(mode="json")
            persisted = _attempt_record(existing).model_dump(
                mode="json",
                exclude={"id", "created_at"},
            )
            if candidate != persisted:
                raise ProviderRepositoryConflict("PROVIDER_ATTEMPT_CONFLICT")
            return _attempt_record(existing)
        row = ProviderRequestAttempt(
            **value.model_dump(mode="python", exclude={"status"}),
            status=value.status.value,
        )
        self._session.add(row)
        self._session.flush()
        return _attempt_record(row)

    def reserve_attempt(
        self,
        value: ProviderRequestAttemptReservation,
    ) -> ProviderRequestAttemptRecord:
        attempt = value.value
        existing = self._session.scalar(
            select(ProviderRequestAttempt).where(
                (ProviderRequestAttempt.id == value.id)
                | (
                    (ProviderRequestAttempt.sync_run_id == attempt.sync_run_id)
                    & (ProviderRequestAttempt.slice_id == attempt.slice_id)
                    & (ProviderRequestAttempt.attempt_number == attempt.attempt_number)
                )
            )
        )
        if existing is not None:
            persisted = _attempt_record(existing).model_dump(
                mode="json",
                exclude={"created_at"},
            )
            candidate = {
                "id": str(value.id),
                **attempt.model_dump(mode="json"),
            }
            if persisted != candidate:
                raise ProviderRepositoryConflict("PROVIDER_ATTEMPT_CONFLICT")
            return _attempt_record(existing)
        row = ProviderRequestAttempt(
            id=value.id,
            **attempt.model_dump(mode="python", exclude={"status"}),
            status=attempt.status.value,
        )
        self._session.add(row)
        self._session.flush()
        return _attempt_record(row)

    def settle_attempt(
        self,
        value: ProviderRequestAttemptSettlement,
    ) -> ProviderRequestAttemptRecord:
        row = self._session.scalar(
            select(ProviderRequestAttempt)
            .where(ProviderRequestAttempt.id == value.id)
            .with_for_update()
        )
        if row is None:
            raise LookupError("PROVIDER_ATTEMPT_NOT_FOUND")
        if row.status != ProviderSyncSliceStatus.PENDING.value:
            persisted = (
                row.status,
                row.response_status_code,
                row.response_bytes,
                row.completed_at,
                row.safe_error_code,
            )
            expected = (
                value.status.value,
                value.response_status_code,
                value.response_bytes,
                value.completed_at,
                value.safe_error_code,
            )
            if persisted != expected:
                raise ProviderRepositoryConflict("PROVIDER_ATTEMPT_SETTLEMENT_CONFLICT")
            return _attempt_record(row)
        row.status = value.status.value
        row.response_status_code = value.response_status_code
        row.response_bytes = value.response_bytes
        row.completed_at = value.completed_at
        row.safe_error_code = value.safe_error_code
        self._session.flush()
        return _attempt_record(row)

    def compare_and_swap_checkpoint(
        self,
        value: CheckpointAdvance,
    ) -> ProviderCheckpointRecord:
        checksum = value.scope.checksum()
        row = self._session.scalar(
            select(ProviderSyncCheckpoint)
            .where(
                ProviderSyncCheckpoint.provider_definition_id == value.scope.provider_definition_id,
                ProviderSyncCheckpoint.provider_capability_id == value.scope.provider_capability_id,
                ProviderSyncCheckpoint.scope_checksum == checksum,
            )
            .with_for_update()
        )
        if row is None:
            if value.expected_revision != 0:
                raise ProviderRepositoryConflict("PROVIDER_CHECKPOINT_CONFLICT")
            row = ProviderSyncCheckpoint(
                provider_definition_id=value.scope.provider_definition_id,
                provider_capability_id=value.scope.provider_capability_id,
                scope_checksum=checksum,
                watermark=value.watermark,
                revision=0,
            )
            self._session.add(row)
            self._session.flush()
            return _checkpoint_record(row, value.scope)
        if row.revision != value.expected_revision:
            raise ProviderRepositoryConflict("PROVIDER_CHECKPOINT_CONFLICT")
        row.watermark = value.watermark
        row.revision += 1
        self._session.flush()
        return _checkpoint_record(row, value.scope)

    def get_checkpoint(
        self,
        scope: CheckpointScope,
    ) -> ProviderCheckpointRecord | None:
        row = self._session.scalar(
            select(ProviderSyncCheckpoint).where(
                ProviderSyncCheckpoint.provider_definition_id == scope.provider_definition_id,
                ProviderSyncCheckpoint.provider_capability_id == scope.provider_capability_id,
                ProviderSyncCheckpoint.scope_checksum == scope.checksum(),
            )
        )
        return None if row is None else _checkpoint_record(row, scope)


class SqlAlchemyProviderArtifactRepository:
    """Persist immutable raw lineage and append-only diagnostics."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_artifact(
        self,
        value: ProviderRawArtifactWrite,
    ) -> ProviderRawArtifactRecord:
        existing = self._session.scalar(
            select(ProviderRawArtifact).where(
                ProviderRawArtifact.provider_definition_id == value.provider_definition_id,
                ProviderRawArtifact.source_identity == value.source_identity,
                ProviderRawArtifact.source_checksum == value.source_checksum,
            )
        )
        if existing is not None:
            persisted = _artifact_record(existing).model_dump(
                mode="json",
                exclude={"id", "created_at"},
            )
            if persisted != value.model_dump(mode="json"):
                raise ProviderRepositoryConflict("PROVIDER_ARTIFACT_CONFLICT")
            return _artifact_record(existing)
        row = ProviderRawArtifact(
            **value.model_dump(
                mode="python",
                exclude={"synthetic_status"},
            ),
            synthetic_status=value.synthetic_status.value,
        )
        self._session.add(row)
        self._session.flush()
        return _artifact_record(row)

    def add_artifact_with_id(
        self,
        value: ProviderRawArtifactReservation,
    ) -> ProviderRawArtifactRecord:
        artifact = value.value
        existing = self._session.scalar(
            select(ProviderRawArtifact).where(
                (ProviderRawArtifact.id == value.id)
                | (
                    (ProviderRawArtifact.provider_definition_id == artifact.provider_definition_id)
                    & (ProviderRawArtifact.source_identity == artifact.source_identity)
                    & (ProviderRawArtifact.source_checksum == artifact.source_checksum)
                )
            )
        )
        if existing is not None:
            persisted = _artifact_record(existing).model_dump(
                mode="json",
                exclude={"created_at"},
            )
            candidate = {"id": str(value.id), **artifact.model_dump(mode="json")}
            if persisted != candidate:
                raise ProviderRepositoryConflict("PROVIDER_ARTIFACT_CONFLICT")
            return _artifact_record(existing)
        row = ProviderRawArtifact(
            id=value.id,
            **artifact.model_dump(mode="python", exclude={"synthetic_status"}),
            synthetic_status=artifact.synthetic_status.value,
        )
        self._session.add(row)
        self._session.flush()
        return _artifact_record(row)

    def add_manifest(
        self,
        value: ProviderIngestionManifestWrite,
    ) -> ProviderIngestionManifestRecord:
        existing = self._session.scalar(
            select(ProviderIngestionManifest).where(
                ProviderIngestionManifest.raw_artifact_id == value.raw_artifact_id,
                ProviderIngestionManifest.adapter_version == value.adapter_version,
                ProviderIngestionManifest.parser_version == value.parser_version,
                ProviderIngestionManifest.schema_version == value.schema_version,
                ProviderIngestionManifest.manifest_checksum == value.manifest_checksum,
            )
        )
        if existing is not None:
            return _manifest_record(existing)
        row = ProviderIngestionManifest(
            **value.model_dump(
                mode="python",
                exclude={"synthetic_status", "warning_codes"},
            ),
            warning_codes=list(value.warning_codes),
            synthetic_status=value.synthetic_status.value,
        )
        self._session.add(row)
        self._session.flush()
        return _manifest_record(row)

    def add_quality_issue(
        self,
        value: ProviderDataQualityIssueWrite,
    ) -> ProviderDataQualityIssueRecord:
        row = ProviderDataQualityIssue(
            **value.model_dump(
                mode="python",
                exclude={"severity", "status"},
            ),
            severity=value.severity.value,
            status=value.status.value,
        )
        self._session.add(row)
        self._session.flush()
        return _quality_issue_record(row)

    def add_dead_letter(
        self,
        value: ProviderDeadLetterWrite,
    ) -> ProviderDeadLetterRecord:
        row = ProviderDeadLetter(
            **value.model_dump(mode="python", exclude={"status"}),
            status=value.status.value,
        )
        self._session.add(row)
        self._session.flush()
        return _dead_letter_record(row)


class SqlAlchemyProviderQueryRepository:
    """Execute bounded, explicit-column Provider metadata reads only."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_provider_views(self, *, limit: int, offset: int) -> tuple[Mapping[str, object], ...]:
        statement = (
            select(
                ProviderDefinition.id.label("id"),
                ProviderDefinition.code.label("provider_code"),
                ProviderDefinition.definition_version.label("definition_version"),
                ProviderDefinition.adapter_version.label("adapter_version"),
                ProviderDefinition.display_name.label("display_name"),
                ProviderDefinition.data_domain.label("data_domain"),
                ProviderDefinition.definition_status.label("definition_status"),
                ProviderDefinition.production_status.label("production_status"),
                ProviderCredentialReference.status.label("credential_status"),
                ProviderDefinition.policy_version.label("policy_version"),
                ProviderDefinition.license_policy_version.label("license_policy_version"),
            )
            .outerjoin(
                ProviderCredentialReference,
                ProviderCredentialReference.id == ProviderDefinition.credential_reference_id,
            )
            .order_by(
                ProviderDefinition.code,
                ProviderDefinition.definition_version,
                ProviderDefinition.id,
            )
            .limit(limit)
            .offset(offset)
        )
        return self._many(statement, "PROVIDER")

    def get_provider_view(self, provider_code: str) -> Mapping[str, object] | None:
        statement = (
            select(
                ProviderDefinition.id.label("id"),
                ProviderDefinition.code.label("provider_code"),
                ProviderDefinition.definition_version.label("definition_version"),
                ProviderDefinition.adapter_version.label("adapter_version"),
                ProviderDefinition.display_name.label("display_name"),
                ProviderDefinition.data_domain.label("data_domain"),
                ProviderDefinition.definition_status.label("definition_status"),
                ProviderDefinition.production_status.label("production_status"),
                ProviderCredentialReference.status.label("credential_status"),
                ProviderDefinition.policy_version.label("policy_version"),
                ProviderDefinition.license_policy_version.label("license_policy_version"),
            )
            .outerjoin(
                ProviderCredentialReference,
                ProviderCredentialReference.id == ProviderDefinition.credential_reference_id,
            )
            .where(ProviderDefinition.code == provider_code)
            .order_by(ProviderDefinition.definition_version, ProviderDefinition.id)
            .limit(1)
        )
        return self._one(statement, "PROVIDER")

    def list_capability_views(
        self,
        provider_code: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[Mapping[str, object], ...]:
        statement = (
            select(
                ProviderCapability.id.label("id"),
                ProviderDefinition.code.label("provider_code"),
                ProviderCapability.code.label("capability_code"),
                ProviderCapability.capability_version.label("capability_version"),
                ProviderCapability.status.label("status"),
                ProviderCapability.data_domain.label("data_domain"),
                ProviderCapability.market_codes.label("market_codes"),
                ProviderCapability.security_types.label("security_types"),
                ProviderCapability.operations.label("operations"),
            )
            .join(
                ProviderDefinition,
                ProviderDefinition.id == ProviderCapability.provider_definition_id,
            )
            .where(ProviderDefinition.code == provider_code)
            .order_by(
                ProviderCapability.code,
                ProviderCapability.capability_version,
                ProviderCapability.id,
            )
            .limit(limit)
            .offset(offset)
        )
        return self._many(statement, "CAPABILITY")

    def get_policy_view(self, provider_code: str) -> Mapping[str, object] | None:
        statement = (
            select(
                ProviderPolicy.id.label("id"),
                ProviderDefinition.code.label("provider_code"),
                ProviderPolicy.policy_version.label("policy_version"),
                ProviderPolicy.endpoint_policy_version.label("endpoint_policy_version"),
                ProviderPolicy.network_enabled.label("network_enabled"),
                ProviderPolicy.max_requests.label("max_requests"),
                ProviderPolicy.max_response_bytes.label("max_response_bytes"),
                ProviderPolicy.max_total_bytes.label("max_total_bytes"),
                ProviderPolicy.max_duration_seconds.label("max_duration_seconds"),
                ProviderPolicy.max_attempts.label("max_attempts"),
                ProviderPolicy.max_redirects.label("max_redirects"),
                ProviderPolicy.cache_enabled.label("cache_enabled"),
                ProviderPolicy.cache_ttl_seconds.label("cache_ttl_seconds"),
                ProviderPolicy.retention_days.label("retention_days"),
            )
            .join(
                ProviderDefinition,
                ProviderDefinition.id == ProviderPolicy.provider_definition_id,
            )
            .where(
                ProviderDefinition.code == provider_code,
                ProviderPolicy.policy_version == ProviderDefinition.policy_version,
            )
            .order_by(ProviderDefinition.definition_version, ProviderPolicy.id)
            .limit(1)
        )
        return self._one(statement, "POLICY")

    def get_license_view(self, provider_code: str) -> Mapping[str, object] | None:
        statement = (
            select(
                ProviderLicensePolicy.id.label("id"),
                ProviderDefinition.code.label("provider_code"),
                ProviderLicensePolicy.policy_version.label("policy_version"),
                ProviderLicensePolicy.status.label("status"),
                ProviderLicensePolicy.acquisition.label("acquisition"),
                ProviderLicensePolicy.raw_storage.label("raw_storage"),
                ProviderLicensePolicy.cache.label("cache"),
                ProviderLicensePolicy.derived_use.label("derived_use"),
                ProviderLicensePolicy.redistribution.label("redistribution"),
                ProviderLicensePolicy.retention_days.label("retention_days"),
                ProviderLicensePolicy.deletion_required.label("deletion_required"),
                ProviderLicensePolicy.attribution_required.label("attribution_required"),
                ProviderLicensePolicy.reviewed_at.label("reviewed_at"),
                ProviderLicensePolicy.expires_at.label("expires_at"),
            )
            .join(
                ProviderDefinition,
                ProviderDefinition.id == ProviderLicensePolicy.provider_definition_id,
            )
            .where(
                ProviderDefinition.code == provider_code,
                ProviderLicensePolicy.policy_version == ProviderDefinition.license_policy_version,
            )
            .order_by(ProviderDefinition.definition_version, ProviderLicensePolicy.id)
            .limit(1)
        )
        return self._one(statement, "LICENSE")

    def get_health_view(self, provider_code: str) -> Mapping[str, object] | None:
        statement = (
            select(
                ProviderHealthSnapshot.id.label("id"),
                ProviderDefinition.code.label("provider_code"),
                ProviderHealthSnapshot.status.label("status"),
                ProviderHealthSnapshot.configuration_status.label("configuration_status"),
                ProviderHealthSnapshot.credential_status.label("credential_status"),
                ProviderHealthSnapshot.license_status.label("license_status"),
                ProviderHealthSnapshot.live_validation_status.label("live_validation_status"),
                ProviderHealthSnapshot.limiting_reasons.label("limiting_reasons"),
                ProviderHealthSnapshot.observed_at.label("observed_at"),
            )
            .join(
                ProviderDefinition,
                ProviderDefinition.id == ProviderHealthSnapshot.provider_definition_id,
            )
            .where(ProviderDefinition.code == provider_code)
            .order_by(ProviderHealthSnapshot.observed_at.desc(), ProviderHealthSnapshot.id)
            .limit(1)
        )
        return self._one(statement, "HEALTH")

    def get_circuit_view(self, provider_code: str) -> Mapping[str, object] | None:
        statement = (
            select(
                ProviderCircuitBreaker.id.label("id"),
                ProviderDefinition.code.label("provider_code"),
                ProviderCircuitBreaker.provider_capability_id.label("provider_capability_id"),
                ProviderCircuitBreaker.status.label("status"),
                ProviderCircuitBreaker.failure_count.label("failure_count"),
                ProviderCircuitBreaker.opened_at.label("opened_at"),
                ProviderCircuitBreaker.half_open_probe_at.label("half_open_probe_at"),
                ProviderCircuitBreaker.updated_at.label("updated_at"),
            )
            .join(
                ProviderDefinition,
                ProviderDefinition.id == ProviderCircuitBreaker.provider_definition_id,
            )
            .where(ProviderDefinition.code == provider_code)
            .order_by(ProviderCircuitBreaker.provider_capability_id, ProviderCircuitBreaker.id)
            .limit(1)
        )
        return self._one(statement, "CIRCUIT")

    def get_sync_run_view(self, run_id: UUID) -> Mapping[str, object] | None:
        statement = select(
            ProviderSyncRun.id.label("id"),
            ProviderSyncRun.provider_definition_id.label("provider_definition_id"),
            ProviderSyncRun.provider_capability_id.label("provider_capability_id"),
            ProviderSyncRun.sync_request_id.label("sync_request_id"),
            ProviderSyncRun.sync_plan_id.label("sync_plan_id"),
            ProviderSyncRun.status.label("status"),
            ProviderSyncRun.consumed_requests.label("consumed_requests"),
            ProviderSyncRun.consumed_bytes.label("consumed_bytes"),
            ProviderSyncRun.consumed_attempts.label("consumed_attempts"),
            ProviderSyncRun.started_at.label("started_at"),
            ProviderSyncRun.paused_at.label("paused_at"),
            ProviderSyncRun.completed_at.label("completed_at"),
            ProviderSyncRun.warning_codes.label("warning_codes"),
        ).where(ProviderSyncRun.id == run_id)
        return self._one(statement, "SYNC_RUN")

    def list_attempt_views(
        self,
        run_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[Mapping[str, object], ...]:
        statement = (
            select(
                ProviderRequestAttempt.id.label("id"),
                ProviderRequestAttempt.sync_run_id.label("sync_run_id"),
                ProviderRequestAttempt.slice_id.label("slice_id"),
                ProviderRequestAttempt.attempt_number.label("attempt_number"),
                ProviderRequestAttempt.status.label("status"),
                ProviderRequestAttempt.endpoint_id.label("endpoint_id"),
                ProviderRequestAttempt.response_status_code.label("response_status_code"),
                ProviderRequestAttempt.response_bytes.label("response_bytes"),
                ProviderRequestAttempt.started_at.label("started_at"),
                ProviderRequestAttempt.completed_at.label("completed_at"),
                ProviderRequestAttempt.safe_error_code.label("safe_error_code"),
            )
            .where(ProviderRequestAttempt.sync_run_id == run_id)
            .order_by(
                ProviderRequestAttempt.slice_id,
                ProviderRequestAttempt.attempt_number,
                ProviderRequestAttempt.id,
            )
            .limit(limit)
            .offset(offset)
        )
        return self._many(statement, "ATTEMPT")

    def list_artifact_views(
        self,
        run_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[Mapping[str, object], ...]:
        statement = (
            select(
                ProviderRawArtifact.id.label("id"),
                ProviderRawArtifact.provider_definition_id.label("provider_definition_id"),
                ProviderRawArtifact.provider_capability_id.label("provider_capability_id"),
                ProviderRawArtifact.sync_run_id.label("sync_run_id"),
                ProviderRawArtifact.request_attempt_id.label("request_attempt_id"),
                ProviderRawArtifact.source_identity.label("source_identity"),
                ProviderRawArtifact.source_checksum.label("source_checksum"),
                ProviderRawArtifact.byte_count.label("byte_count"),
                ProviderRawArtifact.content_type.label("content_type"),
                ProviderRawArtifact.acquired_at.label("acquired_at"),
                ProviderRawArtifact.source_published_at.label("source_published_at"),
                ProviderRawArtifact.synthetic_status.label("synthetic_status"),
            )
            .where(ProviderRawArtifact.sync_run_id == run_id)
            .order_by(ProviderRawArtifact.created_at, ProviderRawArtifact.id)
            .limit(limit)
            .offset(offset)
        )
        return self._many(statement, "ARTIFACT")

    def list_checkpoint_views(
        self,
        provider_code: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[Mapping[str, object], ...]:
        statement = (
            select(
                ProviderSyncCheckpoint.id.label("id"),
                ProviderDefinition.code.label("provider_code"),
                ProviderSyncCheckpoint.provider_capability_id.label("provider_capability_id"),
                ProviderSyncCheckpoint.scope_checksum.label("scope_checksum"),
                ProviderSyncCheckpoint.watermark.label("watermark"),
                ProviderSyncCheckpoint.revision.label("revision"),
                ProviderSyncCheckpoint.updated_at.label("updated_at"),
            )
            .join(
                ProviderDefinition,
                ProviderDefinition.id == ProviderSyncCheckpoint.provider_definition_id,
            )
            .where(ProviderDefinition.code == provider_code)
            .order_by(
                ProviderSyncCheckpoint.provider_capability_id,
                ProviderSyncCheckpoint.scope_checksum,
                ProviderSyncCheckpoint.id,
            )
            .limit(limit)
            .offset(offset)
        )
        return self._many(statement, "CHECKPOINT")

    def list_quality_issue_views(
        self,
        run_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[Mapping[str, object], ...]:
        statement = (
            select(
                ProviderDataQualityIssue.id.label("id"),
                ProviderDataQualityIssue.sync_run_id.label("sync_run_id"),
                ProviderDataQualityIssue.manifest_id.label("manifest_id"),
                ProviderDataQualityIssue.rule_code.label("rule_code"),
                ProviderDataQualityIssue.severity.label("severity"),
                ProviderDataQualityIssue.status.label("status"),
                ProviderDataQualityIssue.safe_detail.label("safe_detail"),
                ProviderDataQualityIssue.created_at.label("created_at"),
            )
            .where(ProviderDataQualityIssue.sync_run_id == run_id)
            .order_by(
                ProviderDataQualityIssue.severity,
                ProviderDataQualityIssue.rule_code,
                ProviderDataQualityIssue.id,
            )
            .limit(limit)
            .offset(offset)
        )
        return self._many(statement, "QUALITY_ISSUE")

    def list_dead_letter_views(
        self,
        run_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[Mapping[str, object], ...]:
        statement = (
            select(
                ProviderDeadLetter.id.label("id"),
                ProviderDeadLetter.sync_run_id.label("sync_run_id"),
                ProviderDeadLetter.manifest_id.label("manifest_id"),
                ProviderDeadLetter.source_identity.label("source_identity"),
                ProviderDeadLetter.status.label("status"),
                ProviderDeadLetter.safe_error_code.label("safe_error_code"),
                ProviderDeadLetter.safe_detail.label("safe_detail"),
                ProviderDeadLetter.created_at.label("created_at"),
            )
            .where(ProviderDeadLetter.sync_run_id == run_id)
            .order_by(
                ProviderDeadLetter.status, ProviderDeadLetter.created_at, ProviderDeadLetter.id
            )
            .limit(limit)
            .offset(offset)
        )
        return self._many(statement, "DEAD_LETTER")

    def get_readiness_view(self, security_id: UUID) -> Mapping[str, object] | None:
        latest_health_id = (
            select(ProviderHealthSnapshot.id)
            .where(ProviderHealthSnapshot.provider_definition_id == ProviderDefinition.id)
            .order_by(
                ProviderHealthSnapshot.observed_at.desc(),
                ProviderHealthSnapshot.created_at.desc(),
                ProviderHealthSnapshot.id.desc(),
            )
            .limit(1)
            .correlate(ProviderDefinition)
            .scalar_subquery()
        )
        statement = (
            select(
                ProviderSyncRequest.security_id.label("security_id"),
                ProviderDefinition.code.label("provider_code"),
                ProviderDefinition.definition_status.label("definition_status"),
                ProviderDefinition.production_status.label("production_status"),
                ProviderCapability.code.label("capability_code"),
                ProviderCapability.status.label("capability_status"),
                ProviderHealthSnapshot.status.label("readiness_status"),
                ProviderHealthSnapshot.limiting_reasons.label("limiting_reasons"),
                ProviderHealthSnapshot.observed_at.label("health_observed_at"),
            )
            .join(
                ProviderDefinition,
                ProviderDefinition.id == ProviderSyncRequest.provider_definition_id,
            )
            .join(
                ProviderCapability,
                ProviderCapability.id == ProviderSyncRequest.provider_capability_id,
            )
            .outerjoin(ProviderHealthSnapshot, ProviderHealthSnapshot.id == latest_health_id)
            .where(ProviderSyncRequest.security_id == security_id)
            .order_by(ProviderDefinition.code, ProviderCapability.code)
            .distinct()
            .limit(100)
        )
        rows = self._session.execute(statement).mappings().all()
        if not rows:
            return None
        providers: list[dict[str, object]] = []
        all_reasons: set[str] = set()
        overall = ProviderReadinessStatus.READY
        rank = {
            ProviderReadinessStatus.READY: 0,
            ProviderReadinessStatus.CONDITIONAL: 1,
            ProviderReadinessStatus.BLOCKED: 2,
        }
        for row in rows:
            provider_code = str(row["provider_code"])
            capability_code = str(row["capability_code"])
            raw_status = row["readiness_status"]
            status = (
                ProviderReadinessStatus.BLOCKED
                if raw_status is None
                else ProviderReadinessStatus(str(raw_status))
            )
            raw_reasons = row["limiting_reasons"]
            reasons = (
                ("HEALTH_SNAPSHOT_NOT_FOUND",)
                if raw_reasons is None
                else tuple(sorted(str(reason) for reason in raw_reasons))
            )
            if rank[status] > rank[overall]:
                overall = status
            all_reasons.update(f"{provider_code}:{capability_code}:{reason}" for reason in reasons)
            providers.append(
                {
                    "provider_code": provider_code,
                    "definition_status": row["definition_status"],
                    "production_status": row["production_status"],
                    "capability_code": capability_code,
                    "capability_status": row["capability_status"],
                    "readiness_status": status.value,
                    "limiting_reasons": list(reasons),
                    "health_observed_at": _query_json_value(row["health_observed_at"]),
                }
            )
        return _safe_query_projection(
            "READINESS",
            {
                "security_id": security_id,
                "status": overall.value,
                "provider_count": len(providers),
                "providers": providers,
                "limiting_reasons": sorted(all_reasons),
            },
        )

    def _many(
        self,
        statement: Select[Any],
        resource_type: str,
    ) -> tuple[Mapping[str, object], ...]:
        rows = self._session.execute(statement).mappings().all()
        return tuple(_safe_query_projection(resource_type, dict(row)) for row in rows)

    def _one(
        self,
        statement: Select[Any],
        resource_type: str,
    ) -> Mapping[str, object] | None:
        row = self._session.execute(statement).mappings().first()
        return None if row is None else _safe_query_projection(resource_type, dict(row))


def _safe_query_projection(
    resource_type: str,
    row: Mapping[str, object],
) -> Mapping[str, object]:
    return {
        "resource_type": resource_type,
        "values": {key: _query_json_value(value) for key, value in row.items()},
    }


def _query_json_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return _utc(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return _query_json_value(value.value)
    if isinstance(value, list):
        return [_query_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _query_json_value(item) for key, item in value.items()}
    raise TypeError(f"unsupported Provider query value: {type(value).__name__}")


def _definition_record(row: ProviderDefinition) -> ProviderDefinitionRecord:
    return ProviderDefinitionRecord(
        id=row.id,
        code=row.code,
        definition_version=row.definition_version,
        adapter_version=row.adapter_version,
        display_name=row.display_name,
        data_domain=row.data_domain,
        definition_status=ProviderDefinitionStatus(row.definition_status),
        production_status=ProviderProductionStatus(row.production_status),
        official_domains=tuple(row.official_domains),
        policy_version=row.policy_version,
        license_policy_version=row.license_policy_version,
        credential_reference_id=row.credential_reference_id,
        source_register_version=row.source_register_version,
        checksum=row.checksum,
        created_at=_utc(row.created_at),
    )


def _capability_record(row: ProviderCapability) -> ProviderCapabilityRecord:
    return ProviderCapabilityRecord(
        id=row.id,
        provider_definition_id=row.provider_definition_id,
        code=row.code,
        capability_version=row.capability_version,
        status=ProviderCapabilityStatus(row.status),
        data_domain=row.data_domain,
        market_codes=tuple(row.market_codes),
        security_types=tuple(row.security_types),
        operations=tuple(row.operations),
        checksum=row.checksum,
        created_at=_utc(row.created_at),
    )


def _policy_record(row: ProviderPolicy) -> ProviderPolicyRecord:
    return ProviderPolicyRecord(
        id=row.id,
        provider_definition_id=row.provider_definition_id,
        policy_version=row.policy_version,
        endpoint_policy_version=row.endpoint_policy_version,
        network_enabled=row.network_enabled,
        max_requests=row.max_requests,
        max_response_bytes=row.max_response_bytes,
        max_total_bytes=row.max_total_bytes,
        max_duration_seconds=row.max_duration_seconds,
        max_attempts=row.max_attempts,
        max_redirects=row.max_redirects,
        rate_limit_per_second=row.rate_limit_per_second,
        retry_base_delay_seconds=row.retry_base_delay_seconds,
        cache_enabled=row.cache_enabled,
        cache_ttl_seconds=row.cache_ttl_seconds,
        retention_days=row.retention_days,
        checksum=row.checksum,
        created_at=_utc(row.created_at),
    )


def _license_record(row: ProviderLicensePolicy) -> SourceLicensePolicyRecord:
    return SourceLicensePolicyRecord(
        id=row.id,
        provider_definition_id=row.provider_definition_id,
        policy_version=row.policy_version,
        status=ProviderLicenseStatus(row.status),
        acquisition=LicensePermission(row.acquisition),
        raw_storage=LicensePermission(row.raw_storage),
        cache=LicensePermission(row.cache),
        derived_use=LicensePermission(row.derived_use),
        redistribution=LicensePermission(row.redistribution),
        retention_days=row.retention_days,
        deletion_required=row.deletion_required,
        attribution_required=row.attribution_required,
        terms_source_ids=tuple(row.terms_source_ids),
        reviewed_at=_utc(row.reviewed_at),
        expires_at=None if row.expires_at is None else _utc(row.expires_at),
        checksum=row.checksum,
        created_at=_utc(row.created_at),
    )


def _health_record(row: ProviderHealthSnapshot) -> ProviderHealthSnapshotRecord:
    return ProviderHealthSnapshotRecord(
        id=row.id,
        provider_definition_id=row.provider_definition_id,
        status=ProviderReadinessStatus(row.status),
        configuration_status=ProviderConfigurationStatus(row.configuration_status),
        credential_status=ProviderCredentialStatus(row.credential_status),
        license_status=ProviderLicenseStatus(row.license_status),
        live_validation_status=ProviderLiveValidationStatus(row.live_validation_status),
        limiting_reasons=tuple(row.limiting_reasons),
        observed_at=_utc(row.observed_at),
        checksum=row.checksum,
        created_at=_utc(row.created_at),
    )


def _credential_record(
    row: ProviderCredentialReference,
) -> CredentialReferenceRecord:
    return CredentialReferenceRecord(
        id=row.id,
        provider_definition_id=row.provider_definition_id,
        reference_version=row.reference_version,
        resolver_kind=CredentialResolverKind(row.resolver_kind),
        declared_name=row.declared_name,
        status=ProviderCredentialStatus(row.status),
        safe_label=row.safe_label,
        checksum=row.checksum,
        created_at=_utc(row.created_at),
    )


def _sync_request_record(row: ProviderSyncRequest) -> ProviderSyncRequestRecord:
    return ProviderSyncRequestRecord(
        id=row.id,
        provider_definition_id=row.provider_definition_id,
        provider_capability_id=row.provider_capability_id,
        policy_id=row.policy_id,
        license_policy_id=row.license_policy_id,
        credential_reference_id=row.credential_reference_id,
        security_id=row.security_id,
        universe_code=row.universe_code,
        research_as_of_time=_utc(row.research_as_of_time),
        range_start=row.range_start,
        range_end=row.range_end,
        execution_mode=ProviderExecutionMode(row.execution_mode),
        scope=row.scope,
        budget=row.budget,
        request_checksum=row.request_checksum,
        idempotency_key=row.idempotency_key,
        created_at=_utc(row.created_at),
    )


def _sync_plan_record(row: ProviderSyncPlan) -> ProviderSyncPlanRecord:
    return ProviderSyncPlanRecord(
        id=row.id,
        sync_request_id=row.sync_request_id,
        adapter_version=row.adapter_version,
        checkpoint_revision=row.checkpoint_revision,
        slices=tuple(row.slices),
        slice_count=row.slice_count,
        plan_checksum=row.plan_checksum,
        created_at=_utc(row.created_at),
    )


def _sync_run_record(row: ProviderSyncRun) -> ProviderSyncRunRecord:
    return ProviderSyncRunRecord(
        id=row.id,
        sync_request_id=row.sync_request_id,
        sync_plan_id=row.sync_plan_id,
        provider_definition_id=row.provider_definition_id,
        provider_capability_id=row.provider_capability_id,
        status=ProviderRunStatus(row.status),
        consumed_requests=row.consumed_requests,
        consumed_bytes=row.consumed_bytes,
        consumed_attempts=row.consumed_attempts,
        started_at=None if row.started_at is None else _utc(row.started_at),
        paused_at=None if row.paused_at is None else _utc(row.paused_at),
        completed_at=None if row.completed_at is None else _utc(row.completed_at),
        lease_owner=row.lease_owner,
        lease_expires_at=(None if row.lease_expires_at is None else _utc(row.lease_expires_at)),
        warning_codes=tuple(row.warning_codes),
        created_at=_utc(row.created_at),
    )


def _attempt_record(row: ProviderRequestAttempt) -> ProviderRequestAttemptRecord:
    return ProviderRequestAttemptRecord(
        id=row.id,
        sync_run_id=row.sync_run_id,
        slice_id=row.slice_id,
        attempt_number=row.attempt_number,
        status=ProviderSyncSliceStatus(row.status),
        endpoint_id=row.endpoint_id,
        response_status_code=row.response_status_code,
        response_bytes=row.response_bytes,
        started_at=_utc(row.started_at),
        completed_at=None if row.completed_at is None else _utc(row.completed_at),
        safe_error_code=row.safe_error_code,
        created_at=_utc(row.created_at),
    )


def _checkpoint_record(
    row: ProviderSyncCheckpoint,
    scope: CheckpointScope,
) -> ProviderCheckpointRecord:
    return ProviderCheckpointRecord(
        id=row.id,
        scope=scope,
        scope_checksum=row.scope_checksum,
        watermark=row.watermark,
        revision=row.revision,
        updated_at=_utc(row.updated_at),
        created_at=_utc(row.created_at),
    )


def _artifact_record(row: ProviderRawArtifact) -> ProviderRawArtifactRecord:
    return ProviderRawArtifactRecord(
        id=row.id,
        provider_definition_id=row.provider_definition_id,
        provider_capability_id=row.provider_capability_id,
        sync_run_id=row.sync_run_id,
        request_attempt_id=row.request_attempt_id,
        license_policy_id=row.license_policy_id,
        source_identity=row.source_identity,
        source_checksum=row.source_checksum,
        byte_count=row.byte_count,
        content_type=row.content_type,
        blob_key=row.blob_key,
        acquired_at=_utc(row.acquired_at),
        source_published_at=(
            None if row.source_published_at is None else _utc(row.source_published_at)
        ),
        synthetic_status=ProviderSyntheticStatus(row.synthetic_status),
        created_at=_utc(row.created_at),
    )


def _manifest_record(
    row: ProviderIngestionManifest,
) -> ProviderIngestionManifestRecord:
    return ProviderIngestionManifestRecord(
        id=row.id,
        raw_artifact_id=row.raw_artifact_id,
        sync_run_id=row.sync_run_id,
        adapter_version=row.adapter_version,
        parser_version=row.parser_version,
        schema_version=row.schema_version,
        batch_checksum=row.batch_checksum,
        record_count=row.record_count,
        source_published_at=(
            None if row.source_published_at is None else _utc(row.source_published_at)
        ),
        warning_codes=tuple(row.warning_codes),
        synthetic_status=ProviderSyntheticStatus(row.synthetic_status),
        manifest_checksum=row.manifest_checksum,
        created_at=_utc(row.created_at),
    )


def _quality_issue_record(
    row: ProviderDataQualityIssue,
) -> ProviderDataQualityIssueRecord:
    return ProviderDataQualityIssueRecord(
        id=row.id,
        sync_run_id=row.sync_run_id,
        manifest_id=row.manifest_id,
        rule_code=row.rule_code,
        severity=ProviderIssueSeverity(row.severity),
        status=ProviderIssueStatus(row.status),
        safe_detail=row.safe_detail,
        created_at=_utc(row.created_at),
    )


def _dead_letter_record(row: ProviderDeadLetter) -> ProviderDeadLetterRecord:
    return ProviderDeadLetterRecord(
        id=row.id,
        sync_run_id=row.sync_run_id,
        manifest_id=row.manifest_id,
        source_identity=row.source_identity,
        status=ProviderDeadLetterStatus(row.status),
        safe_error_code=row.safe_error_code,
        safe_detail=row.safe_detail,
        created_at=_utc(row.created_at),
    )
