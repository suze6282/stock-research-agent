"""SQLAlchemy model identities for the Stage 9 Provider control plane."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_research_agent.db.base import Base

PROVIDER_TABLE_PURPOSES = {
    "provider_definitions": "immutable Provider and adapter identity",
    "provider_capabilities": "versioned explicit capability allowlist",
    "provider_policies": "bounded execution and storage policy",
    "provider_license_policies": "versioned licensed-use decision",
    "provider_credential_references": "secret-free credential metadata",
    "provider_sync_requests": "immutable bounded sync intent",
    "provider_sync_plans": "finite deterministic sync plan",
    "provider_sync_runs": "sync execution lifecycle and budgets",
    "provider_sync_checkpoints": "transactional scope watermark",
    "provider_request_attempts": "append-only request accounting",
    "provider_raw_artifacts": "immutable source bytes identity",
    "provider_ingestion_manifests": "artifact-to-batch lineage",
    "provider_cache_entries": "expiring operational reuse pointer",
    "provider_circuit_breakers": "cross-process failure state",
    "provider_dead_letters": "append-only rejected record",
    "provider_data_quality_issues": "append-only validation issue",
    "provider_freshness_policies": "versioned freshness expectation",
    "provider_health_snapshots": "append-only readiness observation",
    "provider_audit_events": "append-only governance audit",
    "provider_live_validation_runs": "finite separate Live authorization status",
}


class _ProviderControlPlaneRecord(Base):
    __abstract__ = True

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ProviderDefinition(_ProviderControlPlaneRecord):
    __tablename__ = "provider_definitions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_definitions"),
        ForeignKeyConstraint(
            ["credential_reference_id"],
            ["provider_credential_references.id"],
            name="fk_provider_definitions_credential_reference",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        UniqueConstraint(
            "code",
            "definition_version",
            name="uq_provider_definitions_identity",
        ),
        CheckConstraint(
            "code ~ '^[A-Z][A-Z0-9_]{2,63}$'",
            name="ck_provider_definitions_code",
        ),
        CheckConstraint(
            "definition_status IN ('DRAFT','ACTIVE','SUSPENDED','RETIRED','BLOCKED') "
            "AND production_status IN ('ENABLED','CONDITIONAL','BLOCKED','TEST_ONLY')",
            name="ck_provider_definitions_status",
        ),
        CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_provider_definitions_checksum",
        ),
        Index(
            "ix_provider_definitions_code_status",
            "code",
            "definition_status",
        ),
    )

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_domain: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_status: Mapped[str] = mapped_column(String(16), nullable=False)
    production_status: Mapped[str] = mapped_column(String(16), nullable=False)
    official_domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    license_policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_reference_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_register_version: Mapped[str] = mapped_column(String(32), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class ProviderCapability(_ProviderControlPlaneRecord):
    __tablename__ = "provider_capabilities"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_capabilities"),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_capabilities_definition",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider_definition_id",
            "code",
            "capability_version",
            name="uq_provider_capabilities_identity",
        ),
        CheckConstraint(
            "code ~ '^[A-Z][A-Z0-9_]{2,63}$'",
            name="ck_provider_capabilities_code",
        ),
        CheckConstraint(
            "status IN ('IMPLEMENTED_OFFLINE','ENABLED','BLOCKED','RETIRED')",
            name="ck_provider_capabilities_status",
        ),
        CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_provider_capabilities_checksum",
        ),
        Index(
            "ix_provider_capabilities_lookup",
            "provider_definition_id",
            "code",
            "status",
        ),
    )

    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    capability_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    data_domain: Mapped[str] = mapped_column(String(64), nullable=False)
    market_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    security_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    operations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class ProviderPolicy(_ProviderControlPlaneRecord):
    __tablename__ = "provider_policies"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_policies"),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_policies_definition",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider_definition_id",
            "policy_version",
            name="uq_provider_policies_identity",
        ),
        CheckConstraint(
            "max_requests BETWEEN 1 AND 10000 "
            "AND max_response_bytes BETWEEN 1 AND 52428800 "
            "AND max_total_bytes >= max_response_bytes "
            "AND max_total_bytes <= 10737418240 "
            "AND max_duration_seconds BETWEEN 1 AND 86400 "
            "AND max_attempts BETWEEN 1 AND 3 "
            "AND max_redirects BETWEEN 0 AND 5 "
            "AND rate_limit_per_second > 0 "
            "AND retry_base_delay_seconds > 0 "
            "AND ((cache_enabled AND cache_ttl_seconds BETWEEN 1 AND 86400) "
            "OR (NOT cache_enabled AND cache_ttl_seconds IS NULL)) "
            "AND (retention_days IS NULL OR retention_days BETWEEN 1 AND 36500)",
            name="ck_provider_policies_limits",
        ),
        CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_provider_policies_checksum",
        ),
        Index(
            "ix_provider_policies_lookup",
            "provider_definition_id",
            "policy_version",
        ),
    )

    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint_policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    network_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    max_requests: Mapped[int] = mapped_column(Integer, nullable=False)
    max_response_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_total_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    max_redirects: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_limit_per_second: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    retry_base_delay_seconds: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    cache_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cache_ttl_seconds: Mapped[int | None] = mapped_column(Integer)
    retention_days: Mapped[int | None] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class ProviderLicensePolicy(_ProviderControlPlaneRecord):
    __tablename__ = "provider_license_policies"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_license_policies"),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_license_policies_definition",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider_definition_id",
            "policy_version",
            name="uq_provider_license_policies_identity",
        ),
        CheckConstraint(
            "status IN ('APPROVED','RESTRICTED_REVIEW_REQUIRED','BLOCKED',"
            "'UNKNOWN_REQUIRES_REVIEW')",
            name="ck_provider_license_policies_status",
        ),
        CheckConstraint(
            "acquisition IN ('ALLOWED','PROHIBITED','UNKNOWN_REQUIRES_REVIEW',"
            "'NOT_APPLICABLE') AND "
            "raw_storage IN ('ALLOWED','PROHIBITED','UNKNOWN_REQUIRES_REVIEW',"
            "'NOT_APPLICABLE') AND "
            "cache IN ('ALLOWED','PROHIBITED','UNKNOWN_REQUIRES_REVIEW',"
            "'NOT_APPLICABLE') AND "
            "derived_use IN ('ALLOWED','PROHIBITED','UNKNOWN_REQUIRES_REVIEW',"
            "'NOT_APPLICABLE') AND "
            "redistribution IN ('ALLOWED','PROHIBITED','UNKNOWN_REQUIRES_REVIEW',"
            "'NOT_APPLICABLE')",
            name="ck_provider_license_policies_permissions",
        ),
        CheckConstraint(
            "(retention_days IS NULL OR retention_days BETWEEN 1 AND 36500) "
            "AND (expires_at IS NULL OR expires_at > reviewed_at)",
            name="ck_provider_license_policies_window",
        ),
        CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_provider_license_policies_checksum",
        ),
        Index(
            "ix_provider_license_policies_lookup",
            "provider_definition_id",
            "policy_version",
        ),
    )

    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    acquisition: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_storage: Mapped[str] = mapped_column(String(32), nullable=False)
    cache: Mapped[str] = mapped_column(String(32), nullable=False)
    derived_use: Mapped[str] = mapped_column(String(32), nullable=False)
    redistribution: Mapped[str] = mapped_column(String(32), nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer)
    deletion_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attribution_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    terms_source_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column()
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class ProviderCredentialReference(_ProviderControlPlaneRecord):
    __tablename__ = "provider_credential_references"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_credential_references"),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_credential_references_definition",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider_definition_id",
            "reference_version",
            name="uq_provider_credential_references_identity",
        ),
        CheckConstraint(
            "(resolver_kind = 'NONE' AND declared_name IS NULL "
            "AND status = 'NOT_REQUIRED') OR "
            "(resolver_kind = 'ENVIRONMENT' AND declared_name IS NOT NULL "
            "AND declared_name ~ '^[A-Z][A-Z0-9_]{2,63}$' "
            "AND status <> 'NOT_REQUIRED')",
            name="ck_provider_credential_references_resolver",
        ),
        CheckConstraint(
            "status IN ('NOT_REQUIRED','NOT_READ','CONFIGURED_METADATA_ONLY','MISSING','BLOCKED')",
            name="ck_provider_credential_references_status",
        ),
        CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_provider_credential_references_checksum",
        ),
        Index(
            "ix_provider_credential_references_provider",
            "provider_definition_id",
        ),
    )

    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reference_version: Mapped[str] = mapped_column(String(32), nullable=False)
    resolver_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    declared_name: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    safe_label: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class ProviderSyncRequest(_ProviderControlPlaneRecord):
    __tablename__ = "provider_sync_requests"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_sync_requests"),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_sync_requests_definition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_capability_id"],
            ["provider_capabilities.id"],
            name="fk_provider_sync_requests_capability",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["policy_id"],
            ["provider_policies.id"],
            name="fk_provider_sync_requests_policy",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["license_policy_id"],
            ["provider_license_policies.id"],
            name="fk_provider_sync_requests_license",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["credential_reference_id"],
            ["provider_credential_references.id"],
            name="fk_provider_sync_requests_credential",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_provider_sync_requests_security",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "idempotency_key",
            name="uq_provider_sync_requests_idempotency",
        ),
        CheckConstraint(
            "execution_mode IN ('OFFLINE','LIVE_VALIDATION')",
            name="ck_provider_sync_requests_mode",
        ),
        CheckConstraint(
            "range_start IS NOT NULL AND range_end IS NOT NULL AND range_end >= range_start",
            name="ck_provider_sync_requests_range",
        ),
        CheckConstraint(
            "request_checksum ~ '^[0-9a-f]{64}$' AND idempotency_key ~ '^[0-9a-f]{64}$'",
            name="ck_provider_sync_requests_checksums",
        ),
        CheckConstraint(
            "jsonb_typeof(scope) = 'object' "
            "AND octet_length(scope::text) <= 65536 "
            "AND jsonb_typeof(budget) = 'object' "
            "AND octet_length(budget::text) <= 16384",
            name="ck_provider_sync_requests_json_bounds",
        ),
        Index(
            "ix_provider_sync_requests_provider_created",
            "provider_definition_id",
            "created_at",
        ),
    )

    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_capability_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    license_policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    credential_reference_id: Mapped[UUID | None] = mapped_column(Uuid)
    security_id: Mapped[UUID | None] = mapped_column(Uuid)
    universe_code: Mapped[str | None] = mapped_column(String(64))
    research_as_of_time: Mapped[datetime] = mapped_column(nullable=False)
    range_start: Mapped[date] = mapped_column(Date, nullable=False)
    range_end: Mapped[date] = mapped_column(Date, nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    budget: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)


class ProviderSyncPlan(_ProviderControlPlaneRecord):
    __tablename__ = "provider_sync_plans"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_sync_plans"),
        ForeignKeyConstraint(
            ["sync_request_id"],
            ["provider_sync_requests.id"],
            name="fk_provider_sync_plans_request",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "sync_request_id",
            "plan_checksum",
            name="uq_provider_sync_plans_identity",
        ),
        CheckConstraint(
            "slice_count BETWEEN 1 AND 10000",
            name="ck_provider_sync_plans_slice_count",
        ),
        CheckConstraint(
            "plan_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_provider_sync_plans_checksum",
        ),
        CheckConstraint(
            "jsonb_typeof(slices) = 'array' "
            "AND jsonb_array_length(slices) = slice_count "
            "AND octet_length(slices::text) <= 1048576",
            name="ck_provider_sync_plans_json_bound",
        ),
        Index("ix_provider_sync_plans_request", "sync_request_id"),
    )

    sync_request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(32), nullable=False)
    checkpoint_revision: Mapped[int | None] = mapped_column(Integer)
    slices: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    slice_count: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class ProviderSyncRun(_ProviderControlPlaneRecord):
    __tablename__ = "provider_sync_runs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_sync_runs"),
        ForeignKeyConstraint(
            ["sync_request_id"],
            ["provider_sync_requests.id"],
            name="fk_provider_sync_runs_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["sync_plan_id"],
            ["provider_sync_plans.id"],
            name="fk_provider_sync_runs_plan",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_sync_runs_definition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_capability_id"],
            ["provider_capabilities.id"],
            name="fk_provider_sync_runs_capability",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "sync_request_id",
            "sync_plan_id",
            name="uq_provider_sync_runs_identity",
        ),
        CheckConstraint(
            "status IN ('PLANNED','QUEUED','RUNNING','PAUSED','COMPLETED',"
            "'PARTIAL','BLOCKED','FAILED','CANCELLED')",
            name="ck_provider_sync_runs_status",
        ),
        CheckConstraint(
            "consumed_requests >= 0 AND consumed_bytes >= 0 AND consumed_attempts >= 0",
            name="ck_provider_sync_runs_counters",
        ),
        CheckConstraint(
            "(status IN ('COMPLETED','PARTIAL','BLOCKED','FAILED','CANCELLED') "
            "AND completed_at IS NOT NULL) OR "
            "(status NOT IN ('COMPLETED','PARTIAL','BLOCKED','FAILED','CANCELLED') "
            "AND completed_at IS NULL)",
            name="ck_provider_sync_runs_terminal_time",
        ),
        Index(
            "ix_provider_sync_runs_provider_status",
            "provider_definition_id",
            "status",
        ),
    )

    sync_request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sync_plan_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_capability_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    consumed_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column()
    paused_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column()
    warning_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class ProviderSyncCheckpoint(_ProviderControlPlaneRecord):
    __tablename__ = "provider_sync_checkpoints"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_sync_checkpoints"),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_sync_checkpoints_definition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_capability_id"],
            ["provider_capabilities.id"],
            name="fk_provider_sync_checkpoints_capability",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider_definition_id",
            "provider_capability_id",
            "scope_checksum",
            name="uq_provider_sync_checkpoints_scope",
        ),
        CheckConstraint(
            "scope_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_provider_sync_checkpoints_checksum",
        ),
        CheckConstraint(
            "revision >= 0",
            name="ck_provider_sync_checkpoints_revision",
        ),
        Index(
            "ix_provider_sync_checkpoints_lookup",
            "provider_definition_id",
            "provider_capability_id",
            "scope_checksum",
        ),
    )

    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_capability_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    scope_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    watermark: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProviderRequestAttempt(_ProviderControlPlaneRecord):
    __tablename__ = "provider_request_attempts"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_request_attempts"),
        ForeignKeyConstraint(
            ["sync_run_id"],
            ["provider_sync_runs.id"],
            name="fk_provider_request_attempts_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "sync_run_id",
            "slice_id",
            "attempt_number",
            name="uq_provider_request_attempts_identity",
        ),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETED','BLOCKED','FAILED','CANCELLED')",
            name="ck_provider_request_attempts_status",
        ),
        CheckConstraint(
            "attempt_number BETWEEN 1 AND 3 AND response_bytes >= 0 "
            "AND (response_status_code IS NULL "
            "OR response_status_code BETWEEN 100 AND 599)",
            name="ck_provider_request_attempts_bounds",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_provider_request_attempts_time",
        ),
        Index(
            "ix_provider_request_attempts_run_order",
            "sync_run_id",
            "slice_id",
            "attempt_number",
        ),
    )

    sync_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    slice_id: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    endpoint_id: Mapped[str] = mapped_column(String(128), nullable=False)
    response_status_code: Mapped[int | None] = mapped_column(Integer)
    response_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column()
    safe_error_code: Mapped[str | None] = mapped_column(String(128))


class ProviderRawArtifact(_ProviderControlPlaneRecord):
    __tablename__ = "provider_raw_artifacts"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_raw_artifacts"),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_raw_artifacts_definition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_capability_id"],
            ["provider_capabilities.id"],
            name="fk_provider_raw_artifacts_capability",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["sync_run_id"],
            ["provider_sync_runs.id"],
            name="fk_provider_raw_artifacts_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["request_attempt_id"],
            ["provider_request_attempts.id"],
            name="fk_provider_raw_artifacts_attempt",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["license_policy_id"],
            ["provider_license_policies.id"],
            name="fk_provider_raw_artifacts_license",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider_definition_id",
            "source_identity",
            "source_checksum",
            name="uq_provider_raw_artifacts_identity",
        ),
        CheckConstraint(
            "source_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_provider_raw_artifacts_checksum",
        ),
        CheckConstraint(
            "byte_count > 0",
            name="ck_provider_raw_artifacts_size",
        ),
        CheckConstraint(
            "length(blob_key) BETWEEN 1 AND 512 AND blob_key !~ '(^/|^[A-Za-z]:|\\\\|\\.\\.)'",
            name="ck_provider_raw_artifacts_blob_key",
        ),
        CheckConstraint(
            "synthetic_status IN ('REAL_VERIFIED','FIXTURE_REAL_EXCERPT',"
            "'SYNTHETIC_TEST_ONLY','UNKNOWN')",
            name="ck_provider_raw_artifacts_synthetic",
        ),
        Index(
            "ix_provider_raw_artifacts_source_checksum",
            "provider_definition_id",
            "source_identity",
            "source_checksum",
        ),
    )

    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_capability_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sync_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_attempt_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    license_policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_identity: Mapped[str] = mapped_column(String(512), nullable=False)
    source_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    blob_key: Mapped[str] = mapped_column(String(512), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column()
    synthetic_status: Mapped[str] = mapped_column(String(32), nullable=False)


class ProviderIngestionManifest(_ProviderControlPlaneRecord):
    __tablename__ = "provider_ingestion_manifests"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_ingestion_manifests"),
        ForeignKeyConstraint(
            ["raw_artifact_id"],
            ["provider_raw_artifacts.id"],
            name="fk_provider_ingestion_manifests_artifact",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["sync_run_id"],
            ["provider_sync_runs.id"],
            name="fk_provider_ingestion_manifests_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "raw_artifact_id",
            "adapter_version",
            "parser_version",
            "schema_version",
            "manifest_checksum",
            name="uq_provider_ingestion_manifests_identity",
        ),
        CheckConstraint(
            "batch_checksum ~ '^[0-9a-f]{64}$' AND manifest_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_provider_ingestion_manifests_checksums",
        ),
        CheckConstraint(
            "record_count >= 0",
            name="ck_provider_ingestion_manifests_count",
        ),
        CheckConstraint(
            "synthetic_status IN ('REAL_VERIFIED','FIXTURE_REAL_EXCERPT',"
            "'SYNTHETIC_TEST_ONLY','UNKNOWN')",
            name="ck_provider_ingestion_manifests_synthetic",
        ),
        Index(
            "ix_provider_ingestion_manifests_run",
            "sync_run_id",
            "created_at",
        ),
    )

    raw_artifact_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sync_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(32), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column()
    warning_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    synthetic_status: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class ProviderCacheEntry(_ProviderControlPlaneRecord):
    __tablename__ = "provider_cache_entries"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_cache_entries"),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_cache_entries_definition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_capability_id"],
            ["provider_capabilities.id"],
            name="fk_provider_cache_entries_capability",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["license_policy_id"],
            ["provider_license_policies.id"],
            name="fk_provider_cache_entries_license",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["artifact_id"],
            ["provider_raw_artifacts.id"],
            name="fk_provider_cache_entries_artifact",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider_definition_id",
            "provider_capability_id",
            "license_policy_id",
            "cache_key",
            name="uq_provider_cache_entries_key",
        ),
        CheckConstraint(
            "cache_key ~ '^[0-9a-f]{64}$'",
            name="ck_provider_cache_entries_key",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_provider_cache_entries_expiry",
        ),
        Index(
            "ix_provider_cache_entries_expiry",
            "provider_definition_id",
            "expires_at",
        ),
    )

    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_capability_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    license_policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    artifact_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)


class ProviderCircuitBreaker(_ProviderControlPlaneRecord):
    __tablename__ = "provider_circuit_breakers"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_circuit_breakers"),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_circuit_breakers_definition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_capability_id"],
            ["provider_capabilities.id"],
            name="fk_provider_circuit_breakers_capability",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider_definition_id",
            "provider_capability_id",
            name="uq_provider_circuit_breakers_scope",
        ),
        CheckConstraint(
            "status IN ('CLOSED','OPEN','HALF_OPEN') AND failure_count >= 0",
            name="ck_provider_circuit_breakers_state",
        ),
        Index(
            "ix_provider_circuit_breakers_lookup",
            "provider_definition_id",
            "provider_capability_id",
            "status",
        ),
    )

    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_capability_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opened_at: Mapped[datetime | None] = mapped_column()
    half_open_probe_at: Mapped[datetime | None] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProviderDeadLetter(_ProviderControlPlaneRecord):
    __tablename__ = "provider_dead_letters"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_dead_letters"),
        ForeignKeyConstraint(
            ["sync_run_id"],
            ["provider_sync_runs.id"],
            name="fk_provider_dead_letters_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["manifest_id"],
            ["provider_ingestion_manifests.id"],
            name="fk_provider_dead_letters_manifest",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('OPEN','REPAIRED','DISMISSED')",
            name="ck_provider_dead_letters_status",
        ),
        CheckConstraint(
            "length(source_identity) BETWEEN 1 AND 512 "
            "AND length(safe_error_code) BETWEEN 1 AND 128 "
            "AND length(safe_detail) BETWEEN 1 AND 1024",
            name="ck_provider_dead_letters_safe",
        ),
        Index(
            "ix_provider_dead_letters_run_status",
            "sync_run_id",
            "status",
            "created_at",
        ),
    )

    sync_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    manifest_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_identity: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    safe_error_code: Mapped[str] = mapped_column(String(128), nullable=False)
    safe_detail: Mapped[str] = mapped_column(String(1024), nullable=False)


class ProviderDataQualityIssue(_ProviderControlPlaneRecord):
    __tablename__ = "provider_data_quality_issues"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_data_quality_issues"),
        ForeignKeyConstraint(
            ["sync_run_id"],
            ["provider_sync_runs.id"],
            name="fk_provider_data_quality_issues_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["manifest_id"],
            ["provider_ingestion_manifests.id"],
            name="fk_provider_data_quality_issues_manifest",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "severity IN ('CRITICAL','HIGH','MEDIUM','LOW') "
            "AND status IN ('OPEN','RESOLVED','ACCEPTED')",
            name="ck_provider_data_quality_issues_state",
        ),
        Index(
            "ix_provider_data_quality_issues_run_status",
            "sync_run_id",
            "status",
            "severity",
        ),
    )

    sync_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    manifest_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    rule_code: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    safe_detail: Mapped[str] = mapped_column(String(1024), nullable=False)


class ProviderFreshnessPolicy(_ProviderControlPlaneRecord):
    __tablename__ = "provider_freshness_policies"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_freshness_policies"),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_freshness_policies_definition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_capability_id"],
            ["provider_capabilities.id"],
            name="fk_provider_freshness_policies_capability",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider_definition_id",
            "provider_capability_id",
            "market_code",
            "policy_version",
            name="uq_provider_freshness_policies_identity",
        ),
        CheckConstraint(
            "expected_delay_seconds >= 0 "
            "AND unknown_published_at_status IN ('PARTIAL','BLOCKED') "
            "AND checksum ~ '^[0-9a-f]{64}$'",
            name="ck_provider_freshness_policies_bounds",
        ),
        Index(
            "ix_provider_freshness_policies_lookup",
            "provider_definition_id",
            "provider_capability_id",
            "market_code",
        ),
    )

    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_capability_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    market_code: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    unknown_published_at_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class ProviderHealthSnapshot(_ProviderControlPlaneRecord):
    __tablename__ = "provider_health_snapshots"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_health_snapshots"),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_health_snapshots_definition",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('READY','CONDITIONAL','BLOCKED') "
            "AND configuration_status IN ('VALID','INVALID','BLOCKED') "
            "AND credential_status IN "
            "('NOT_REQUIRED','NOT_READ','CONFIGURED_METADATA_ONLY','MISSING','BLOCKED') "
            "AND license_status IN "
            "('APPROVED','RESTRICTED_REVIEW_REQUIRED','BLOCKED','UNKNOWN_REQUIRES_REVIEW') "
            "AND live_validation_status IN "
            "('NOT_ATTEMPTED','RUNNING','PASSED','FAILED','BLOCKED','CANCELLED')",
            name="ck_provider_health_snapshots_states",
        ),
        CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_provider_health_snapshots_checksum",
        ),
        Index(
            "ix_provider_health_snapshots_provider_time",
            "provider_definition_id",
            "observed_at",
        ),
    )

    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    configuration_status: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_status: Mapped[str] = mapped_column(String(32), nullable=False)
    license_status: Mapped[str] = mapped_column(String(32), nullable=False)
    live_validation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    limiting_reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class ProviderAuditEvent(_ProviderControlPlaneRecord):
    __tablename__ = "provider_audit_events"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_audit_events"),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_audit_events_definition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["sync_run_id"],
            ["provider_sync_runs.id"],
            name="fk_provider_audit_events_run",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "event_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_provider_audit_events_checksum",
        ),
        CheckConstraint(
            "length(actor_type) BETWEEN 1 AND 64 "
            "AND length(action_code) BETWEEN 1 AND 128 "
            "AND length(decision_code) BETWEEN 1 AND 128 "
            "AND length(safe_summary) BETWEEN 1 AND 1024",
            name="ck_provider_audit_events_safe",
        ),
        Index(
            "ix_provider_audit_events_provider_time",
            "provider_definition_id",
            "created_at",
        ),
    )

    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sync_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_code: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_code: Mapped[str] = mapped_column(String(128), nullable=False)
    safe_summary: Mapped[str] = mapped_column(String(1024), nullable=False)
    event_checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class ProviderLiveValidationRun(_ProviderControlPlaneRecord):
    __tablename__ = "provider_live_validation_runs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_live_validation_runs"),
        ForeignKeyConstraint(
            ["provider_definition_id"],
            ["provider_definitions.id"],
            name="fk_provider_live_validation_runs_definition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_capability_id"],
            ["provider_capabilities.id"],
            name="fk_provider_live_validation_runs_capability",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('NOT_ATTEMPTED','AUTHORIZED','RUNNING','PASS','FAILED','BLOCKED')",
            name="ck_provider_live_validation_runs_status",
        ),
        CheckConstraint(
            "max_requests BETWEEN 1 AND 100 "
            "AND max_bytes BETWEEN 1 AND 52428800 "
            "AND consumed_requests BETWEEN 0 AND max_requests "
            "AND consumed_bytes BETWEEN 0 AND max_bytes "
            "AND (completed_at IS NULL OR started_at IS NOT NULL) "
            "AND (started_at IS NULL OR expires_at > started_at)",
            name="ck_provider_live_validation_runs_budgets",
        ),
        Index(
            "ix_provider_live_validation_runs_provider_time",
            "provider_definition_id",
            "created_at",
        ),
    )

    provider_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_capability_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    authorization_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="NOT_ATTEMPTED",
    )
    max_requests: Mapped[int] = mapped_column(Integer, nullable=False)
    max_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    consumed_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
