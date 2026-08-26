"""SQLAlchemy models for the Stage 10 controlled evidence registry."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_research_agent.db.base import Base


class _Stage10Record(Base):
    __abstract__ = True
    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LiveAuthorizationGrant(_Stage10Record):
    __tablename__ = "live_authorization_grants"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_live_authorization_grants"),
        UniqueConstraint("canonical_checksum", name="uq_live_authorization_grants_checksum"),
        CheckConstraint("request_limit BETWEEN 1 AND 100", name="ck_live_auth_request_limit"),
        CheckConstraint("byte_limit BETWEEN 1 AND 52428800", name="ck_live_auth_byte_limit"),
        CheckConstraint("canonical_checksum ~ '^[0-9a-f]{64}$'", name="ck_live_auth_checksum"),
        Index("ix_live_authorization_grants_status", "status"),
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    request_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_limit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    canonical_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LiveAuthorizationEvent(_Stage10Record):
    __tablename__ = "live_authorization_events"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_live_authorization_events"),
        UniqueConstraint("authorization_id", "sequence", name="uq_live_auth_events_sequence"),
        Index("ix_live_auth_events_authorization", "authorization_id", "sequence"),
    )
    authorization_id: Mapped[UUID] = mapped_column(
        ForeignKey("live_authorization_grants.id", ondelete="RESTRICT"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))


class LiveAuthorizationConsumption(_Stage10Record):
    __tablename__ = "live_authorization_consumptions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_live_authorization_consumptions"),
        UniqueConstraint(
            "authorization_id", "request_attempt_id", name="uq_live_auth_consumption_attempt"
        ),
        CheckConstraint("reserved_bytes > 0", name="ck_live_auth_consumption_reserved"),
        Index("ix_live_auth_consumptions_authorization", "authorization_id", "state"),
    )
    authorization_id: Mapped[UUID] = mapped_column(
        ForeignKey("live_authorization_grants.id", ondelete="RESTRICT"), nullable=False
    )
    request_attempt_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reserved_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_bytes: Mapped[int | None] = mapped_column(BigInteger)
    socket_opened: Mapped[bool | None] = mapped_column(Boolean)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LiveExecutionApproval(_Stage10Record):
    __tablename__ = "live_execution_approvals"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_live_execution_approvals"),
        UniqueConstraint("approval_signature", name="uq_live_execution_approval_signature"),
        Index("ix_live_execution_approvals_authorization", "authorization_id", "state"),
    )
    authorization_id: Mapped[UUID] = mapped_column(
        ForeignKey("live_authorization_grants.id", ondelete="RESTRICT"), nullable=False
    )
    plan_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    plan_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ManualEvidenceImportRequest(_Stage10Record):
    __tablename__ = "manual_evidence_import_requests"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_manual_evidence_import_requests"),
        UniqueConstraint("request_checksum", name="uq_manual_evidence_import_checksum"),
        Index("ix_manual_evidence_import_security", "security_id", "state"),
    )
    security_id: Mapped[UUID] = mapped_column(
        ForeignKey("securities.id", ondelete="RESTRICT"), nullable=False
    )
    issuer_id: Mapped[UUID] = mapped_column(
        ForeignKey("issuers.id", ondelete="RESTRICT"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class ManualEvidenceSourceDeclaration(_Stage10Record):
    __tablename__ = "manual_evidence_source_declarations"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_manual_evidence_source_declarations"),
        UniqueConstraint("import_request_id", name="uq_manual_evidence_declaration_request"),
    )
    import_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("manual_evidence_import_requests.id", ondelete="RESTRICT"), nullable=False
    )
    declaration_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    rights_status: Mapped[str] = mapped_column(String(16), nullable=False)
    declaration: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class ManualEvidenceValidation(_Stage10Record):
    __tablename__ = "manual_evidence_validations"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_manual_evidence_validations"),
        UniqueConstraint(
            "import_request_id", "validator_code", "input_checksum", name="uq_manual_validation"
        ),
        Index("ix_manual_validations_request", "import_request_id", "status"),
    )
    import_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("manual_evidence_import_requests.id", ondelete="RESTRICT"), nullable=False
    )
    validator_code: Mapped[str] = mapped_column(String(64), nullable=False)
    validator_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    findings: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class ManualEvidenceReview(_Stage10Record):
    __tablename__ = "manual_evidence_reviews"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_manual_evidence_reviews"),
        UniqueConstraint("review_checksum", name="uq_manual_evidence_review_checksum"),
        Index("ix_manual_evidence_reviews_request", "import_request_id", "decision"),
    )
    import_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("manual_evidence_import_requests.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    review_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(64), nullable=False)


class EvidenceIngestionManifest(_Stage10Record):
    __tablename__ = "evidence_ingestion_manifests"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_evidence_ingestion_manifests"),
        UniqueConstraint("manifest_checksum", name="uq_evidence_manifest_checksum"),
        Index("ix_evidence_manifest_security", "security_id", "source_type"),
    )
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    artifact_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_payloads.id", ondelete="RESTRICT"), nullable=False
    )
    document_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="RESTRICT")
    )
    security_id: Mapped[UUID] = mapped_column(
        ForeignKey("securities.id", ondelete="RESTRICT"), nullable=False
    )
    issuer_id: Mapped[UUID] = mapped_column(
        ForeignKey("issuers.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class IngestionToSnapshotBinding(_Stage10Record):
    __tablename__ = "ingestion_to_snapshot_bindings"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_ingestion_to_snapshot_bindings"),
        UniqueConstraint(
            "snapshot_id",
            "ingestion_manifest_id",
            name="uq_ingestion_snapshot_bindings_snapshot_manifest",
        ),
        UniqueConstraint("binding_checksum", name="uq_ingestion_snapshot_bindings_checksum"),
        CheckConstraint(
            "manifest_checksum ~ '^[0-9a-f]{64}$' AND "
            "snapshot_checksum ~ '^[0-9a-f]{64}$' AND "
            "binding_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_ingestion_snapshot_bindings_checksums",
        ),
        CheckConstraint(
            "source_published_at IS NULL OR source_published_at <= research_as_of_time",
            name="ck_ingestion_snapshot_bindings_temporal_scope",
        ),
        Index("ix_ingestion_snapshot_bindings_security_snapshot", "security_id", "snapshot_id"),
    )
    ingestion_manifest_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_ingestion_manifests.id", ondelete="RESTRICT"), nullable=False
    )
    manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    document_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="RESTRICT")
    )
    security_id: Mapped[UUID] = mapped_column(
        ForeignKey("securities.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    binding_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    research_as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RealCompanyValidationRun(_Stage10Record):
    __tablename__ = "real_company_validation_runs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_real_company_validation_runs"),
        UniqueConstraint("input_checksum", name="uq_real_company_validation_checksum"),
        Index("ix_real_company_validation_security", "security_id", "status"),
    )
    security_id: Mapped[UUID] = mapped_column(ForeignKey("securities.id", ondelete="RESTRICT"))
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("data_snapshots.id", ondelete="RESTRICT"))
    research_agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_agent_runs.id", ondelete="RESTRICT")
    )
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_reports.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    research_as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EndToEndResearchValidation(_Stage10Record):
    __tablename__ = "end_to_end_research_validations"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_end_to_end_research_validations"),
        UniqueConstraint("validation_run_id", "stage_code", name="uq_end_to_end_validation_stage"),
        Index("ix_end_to_end_validation_run", "validation_run_id", "sequence"),
    )
    validation_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("real_company_validation_runs.id", ondelete="RESTRICT")
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_record_type: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_record_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    evidence_checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class EvidenceRetentionAction(_Stage10Record):
    __tablename__ = "evidence_retention_actions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_evidence_retention_actions"),
        UniqueConstraint("plan_checksum", name="uq_evidence_retention_plan_checksum"),
        Index("ix_evidence_retention_status_deadline", "status", "deadline_at"),
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LiveIncident(_Stage10Record):
    __tablename__ = "live_incidents"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_live_incidents"),
        UniqueConstraint("incident_checksum", name="uq_live_incident_checksum"),
        Index("ix_live_incidents_status_severity", "status", "severity"),
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    summary_code: Mapped[str] = mapped_column(String(64), nullable=False)
    incident_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    affected_lineage: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LiveIncidentEvent(_Stage10Record):
    __tablename__ = "live_incident_events"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_live_incident_events"),
        UniqueConstraint("incident_id", "sequence", name="uq_live_incident_event_sequence"),
        Index("ix_live_incident_events_incident", "incident_id", "sequence"),
    )
    incident_id: Mapped[UUID] = mapped_column(ForeignKey("live_incidents.id", ondelete="RESTRICT"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(16), nullable=False)
    target_status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)


STAGE10_MODEL_TABLES = {
    model.__tablename__: model
    for model in (
        LiveAuthorizationGrant,
        LiveAuthorizationEvent,
        LiveAuthorizationConsumption,
        LiveExecutionApproval,
        ManualEvidenceImportRequest,
        ManualEvidenceSourceDeclaration,
        ManualEvidenceValidation,
        ManualEvidenceReview,
        EvidenceIngestionManifest,
        IngestionToSnapshotBinding,
        RealCompanyValidationRun,
        EndToEndResearchValidation,
        EvidenceRetentionAction,
        LiveIncident,
        LiveIncidentEvent,
    )
}
