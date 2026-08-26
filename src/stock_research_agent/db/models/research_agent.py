"""SQLAlchemy models for controlled Research Agent audit state."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_research_agent.db.base import Base


class _CreatedUuidMixin:
    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ResearchPolicy(_CreatedUuidMixin, Base):
    __tablename__ = "research_policies"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_research_policies"),
        UniqueConstraint("version", name="uq_research_policies_version"),
        CheckConstraint("length(version) BETWEEN 3 AND 128", name="ck_research_policies_version"),
        CheckConstraint("checksum ~ '^[0-9a-f]{64}$'", name="ck_research_policies_checksum"),
    )
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class ResearchRequest(_CreatedUuidMixin, Base):
    __tablename__ = "research_requests"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_research_requests"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_research_requests_security",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_research_requests_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["policy_version"],
            ["research_policies.version"],
            name="fk_research_requests_policy",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "request_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_research_requests_checksum",
        ),
        CheckConstraint(
            "length(security_query) BETWEEN 1 AND 256 "
            "AND length(normalized_security_query) BETWEEN 1 AND 256",
            name="ck_research_requests_query",
        ),
        Index(
            "ix_research_requests_security_as_of",
            "security_id",
            "research_as_of_time",
        ),
    )
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_query: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_security_query: Mapped[str] = mapped_column(String(256), nullable=False)
    research_type: Mapped[str] = mapped_column(String(64), nullable=False)
    research_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    research_as_of_time: Mapped[datetime] = mapped_column(nullable=False)
    requested_sections: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    requested_budgets: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    planner_version: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_catalog_version: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_catalog_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class ResearchAgentRun(_CreatedUuidMixin, Base):
    __tablename__ = "research_agent_runs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_research_agent_runs"),
        ForeignKeyConstraint(
            ["research_request_id"],
            ["research_requests.id"],
            name="fk_research_agent_runs_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_research_agent_runs_security",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_research_agent_runs_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["policy_version"],
            ["research_policies.version"],
            name="fk_research_agent_runs_policy",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('CREATED','PLANNING','PLANNED','RUNNING','PAUSED',"
            "'COMPLETED','PARTIAL','BLOCKED','FAILED','CANCELLED')",
            name="ck_research_agent_runs_status",
        ),
        CheckConstraint(
            "idempotency_key ~ '^[0-9a-f]{64}$'",
            name="ck_research_agent_runs_idempotency",
        ),
        Index(
            "ux_research_agent_runs_reusable_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text(
                "status IN ('CREATED','PLANNING','PLANNED','RUNNING','PAUSED','COMPLETED')"
            ),
        ),
        Index(
            "ix_research_agent_runs_security_snapshot",
            "security_id",
            "snapshot_id",
        ),
        Index("ix_research_agent_runs_status", "status"),
    )
    research_request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_as_of_time: Mapped[datetime] = mapped_column(nullable=False)
    research_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    planner_version: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_catalog_version: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_catalog_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    budget: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    warning_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    terminal_reason_code: Mapped[str | None] = mapped_column(String(128))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    terminal_at: Mapped[datetime | None]


class ResearchPlan(_CreatedUuidMixin, Base):
    __tablename__ = "research_plans"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_research_plans"),
        ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_plans_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("research_agent_run_id", name="uq_research_plans_run"),
        CheckConstraint(
            "status IN ('VALIDATED','INVALID')",
            name="ck_research_plans_status",
        ),
        CheckConstraint(
            "plan_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_research_plans_checksum",
        ),
    )
    research_agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    planner_version: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_version: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_catalog_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    steps: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    plan_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime | None]


class ResearchStep(_CreatedUuidMixin, Base):
    __tablename__ = "research_steps"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_research_steps"),
        ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_steps_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["research_plan_id"],
            ["research_plans.id"],
            name="fk_research_steps_plan",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "research_plan_id",
            "step_index",
            name="uq_research_steps_plan_index",
        ),
        UniqueConstraint(
            "research_plan_id",
            "step_key",
            name="uq_research_steps_plan_key",
        ),
        CheckConstraint(
            "step_index BETWEEN 0 AND 19 AND fanout_limit BETWEEN 1 AND 5",
            name="ck_research_steps_bounds",
        ),
        CheckConstraint(
            "status IN ('PENDING','READY','RUNNING','PASS','PARTIAL','BLOCKED','FAIL','SKIPPED')",
            name="ck_research_steps_status",
        ),
        Index("ix_research_steps_plan_index", "research_plan_id", "step_index"),
    )
    research_agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_plan_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    step_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    dependency_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(128))
    tool_version: Mapped[str | None] = mapped_column(String(64))
    component_name: Mapped[str | None] = mapped_column(String(128))
    input_binding: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    fanout_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    skip_reason_code: Mapped[str | None] = mapped_column(String(128))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    terminal_at: Mapped[datetime | None]


class ResearchToolInvocation(_CreatedUuidMixin, Base):
    __tablename__ = "research_tool_invocations"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_research_tool_invocations"),
        ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_tool_invocations_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["research_step_id"],
            ["research_steps.id"],
            name="fk_research_tool_invocations_step",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "research_step_id",
            "attempt_number",
            name="uq_research_tool_invocations_step_attempt",
        ),
        CheckConstraint(
            "attempt_number BETWEEN 1 AND 2",
            name="ck_research_tool_invocations_attempt",
        ),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','PASS','PARTIAL','BLOCKED','FAIL')",
            name="ck_research_tool_invocations_status",
        ),
        Index("ix_research_tool_invocations_run", "research_agent_run_id"),
        Index("ix_research_tool_invocations_step", "research_step_id"),
    )
    research_agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_step_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(64), nullable=False)
    permission: Mapped[str] = mapped_column(String(32), nullable=False)
    redacted_input: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    output_checksum: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    safe_error_message: Mapped[str | None] = mapped_column(String(256))
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None]


class ResearchObservation(_CreatedUuidMixin, Base):
    __tablename__ = "research_observations"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_research_observations"),
        ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_observations_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["research_step_id"],
            ["research_steps.id"],
            name="fk_research_observations_step",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["invocation_id"],
            ["research_tool_invocations.id"],
            name="fk_research_observations_invocation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_research_observations_security",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_research_observations_snapshot",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('PASS','PARTIAL','BLOCKED','FAIL')",
            name="ck_research_observations_status",
        ),
        Index("ix_research_observations_run", "research_agent_run_id"),
        Index(
            "ux_research_observations_invocation_nonnull",
            "invocation_id",
            unique=True,
            postgresql_where=text("invocation_id IS NOT NULL"),
        ),
        Index(
            "ux_research_observations_component_step",
            "research_step_id",
            unique=True,
            postgresql_where=text("invocation_id IS NULL"),
        ),
    )
    research_agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_step_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    invocation_id: Mapped[UUID | None] = mapped_column(Uuid)
    observation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    output_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_as_of_time: Mapped[datetime] = mapped_column(nullable=False)
    synthetic_status: Mapped[str] = mapped_column(String(32), nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class ResearchEvidence(_CreatedUuidMixin, Base):
    __tablename__ = "research_evidence"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_research_evidence"),
        ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_evidence_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["observation_id"],
            ["research_observations.id"],
            name="fk_research_evidence_observation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_research_evidence_security",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_research_evidence_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["citation_id"],
            ["citation_anchors.id"],
            name="fk_research_evidence_citation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_runs.id"],
            name="fk_research_evidence_calculation_run",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('VALID','INVALID','FUTURE_DATA','SOURCE_MISSING','CONFLICTING','BLOCKED')",
            name="ck_research_evidence_status",
        ),
        CheckConstraint(
            "source_checksum IS NULL OR source_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_research_evidence_checksum",
        ),
        Index(
            "ix_research_evidence_run_type",
            "research_agent_run_id",
            "evidence_type",
        ),
        Index(
            "ix_research_evidence_security_snapshot",
            "security_id",
            "snapshot_id",
        ),
    )
    research_agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    observation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(128), nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_as_of_time: Mapped[datetime] = mapped_column(nullable=False)
    source_record_type: Mapped[str | None] = mapped_column(String(128))
    source_record_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_checksum: Mapped[str | None] = mapped_column(String(64))
    published_at: Mapped[datetime | None]
    citation_id: Mapped[UUID | None] = mapped_column(Uuid)
    calculation_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    calculation_input_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    formula_version: Mapped[str | None] = mapped_column(String(128))
    synthetic_status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    warning_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class ResearchClaim(_CreatedUuidMixin, Base):
    __tablename__ = "research_claims"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_research_claims"),
        ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_claims_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "research_agent_run_id",
            "claim_key",
            name="uq_research_claims_run_key",
        ),
        CheckConstraint(
            "lifecycle_status IN ('CANDIDATE','VALIDATED','REJECTED')",
            name="ck_research_claims_lifecycle",
        ),
        CheckConstraint(
            "support_status IS NULL OR support_status IN "
            "('SUPPORTED','PARTIALLY_SUPPORTED','CONFLICTING','UNSUPPORTED','BLOCKED')",
            name="ck_research_claims_support",
        ),
        Index(
            "ix_research_claims_run_support",
            "research_agent_run_id",
            "support_status",
        ),
    )
    research_agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    claim_key: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(16), nullable=False)
    support_status: Mapped[str | None] = mapped_column(String(32))
    statement_code: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    unit: Mapped[str | None] = mapped_column(String(32))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    period: Mapped[str | None] = mapped_column(String(64))
    as_of_time: Mapped[datetime | None]
    metric_basis: Mapped[str | None] = mapped_column(String(128))
    builder_version: Mapped[str] = mapped_column(String(128), nullable=False)
    validator_version: Mapped[str | None] = mapped_column(String(128))
    completed_at: Mapped[datetime | None]


class ClaimEvidenceLink(_CreatedUuidMixin, Base):
    __tablename__ = "claim_evidence_links"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_claim_evidence_links"),
        ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_claim_evidence_links_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["claim_id"],
            ["research_claims.id"],
            name="fk_claim_evidence_links_claim",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evidence_id"],
            ["research_evidence.id"],
            name="fk_claim_evidence_links_evidence",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("claim_id", "evidence_id", name="uq_claim_evidence_links_pair"),
        CheckConstraint(
            "role IN ('PRIMARY','CORROBORATING','CONTRADICTING','CONTEXT','LIMITATION')",
            name="ck_claim_evidence_links_role",
        ),
        Index("ix_claim_evidence_links_claim", "claim_id"),
        Index("ix_claim_evidence_links_evidence", "evidence_id"),
    )
    research_agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    claim_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)


class ResearchPackage(_CreatedUuidMixin, Base):
    __tablename__ = "research_packages"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_research_packages"),
        ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_packages_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["request_id"],
            ["research_requests.id"],
            name="fk_research_packages_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_research_packages_security",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_research_packages_snapshot",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("research_agent_run_id", name="uq_research_packages_run"),
        CheckConstraint(
            "status IN ('COMPLETE','PARTIAL','BLOCKED','FAILED')",
            name="ck_research_packages_status",
        ),
        CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_research_packages_checksum",
        ),
    )
    research_agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_as_of_time: Mapped[datetime] = mapped_column(nullable=False)
    research_type: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    planner_version: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_catalog_version: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_version: Mapped[str] = mapped_column(String(128), nullable=False)
    claim_version: Mapped[str] = mapped_column(String(128), nullable=False)
    package_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    sections: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    unsupported_claim_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    conflicting_claim_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    blocked_capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class ResearchRunEvent(_CreatedUuidMixin, Base):
    __tablename__ = "research_run_events"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_research_run_events"),
        ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_run_events_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["step_id"],
            ["research_steps.id"],
            name="fk_research_run_events_step",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["invocation_id"],
            ["research_tool_invocations.id"],
            name="fk_research_run_events_invocation",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "research_agent_run_id",
            "sequence_number",
            name="uq_research_run_events_sequence",
        ),
        CheckConstraint(
            "sequence_number > 0",
            name="ck_research_run_events_sequence",
        ),
        Index(
            "ix_research_run_events_run_sequence",
            "research_agent_run_id",
            "sequence_number",
        ),
        Index(
            "ix_research_run_events_run_created",
            "research_agent_run_id",
            "created_at",
        ),
    )
    research_agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str | None] = mapped_column(String(16))
    reason_code: Mapped[str | None] = mapped_column(String(128))
    step_id: Mapped[UUID | None] = mapped_column(Uuid)
    invocation_id: Mapped[UUID | None] = mapped_column(Uuid)
    safe_message: Mapped[str | None] = mapped_column(String(256))
    event_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


STAGE7_MODEL_TABLES = (
    ResearchPolicy.__tablename__,
    ResearchRequest.__tablename__,
    ResearchAgentRun.__tablename__,
    ResearchPlan.__tablename__,
    ResearchStep.__tablename__,
    ResearchToolInvocation.__tablename__,
    ResearchObservation.__tablename__,
    ResearchEvidence.__tablename__,
    ResearchClaim.__tablename__,
    ClaimEvidenceLink.__tablename__,
    ResearchPackage.__tablename__,
    ResearchRunEvent.__tablename__,
)
