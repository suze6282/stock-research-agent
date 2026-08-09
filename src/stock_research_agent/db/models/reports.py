"""SQLAlchemy models for immutable verifiable report state."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_research_agent.db.base import Base


class ReportPolicy(Base):
    """Immutable versioned report-generation policy definition."""

    __tablename__ = "report_policies"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_report_policies"),
        UniqueConstraint("version", name="uq_report_policies_version"),
        CheckConstraint(
            "length(version) BETWEEN 3 AND 128",
            name="ck_report_policies_version",
        ),
        CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_report_policies_checksum",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportTemplateVersion(Base):
    """Immutable localized data-only report template."""

    __tablename__ = "report_template_versions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_report_template_versions"),
        UniqueConstraint(
            "name",
            "version",
            "locale",
            name="uq_report_template_versions_identity",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','DEPRECATED','TEST_ONLY')",
            name="ck_report_template_versions_status",
        ),
        CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_report_template_versions_checksum",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    template_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportRequest(Base):
    """One immutable Stage 7 input seal plus bounded report options."""

    __tablename__ = "report_requests"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_report_requests"),
        ForeignKeyConstraint(
            ["research_package_id"],
            ["research_packages.id"],
            name="fk_report_requests_package",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_report_requests_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["research_request_id"],
            ["research_requests.id"],
            name="fk_report_requests_research_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_report_requests_security",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["issuer_id"],
            ["issuers.id"],
            name="fk_report_requests_issuer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_report_requests_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_policy_version"],
            ["report_policies.version"],
            name="fk_report_requests_policy",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["reflection_policy_version"],
            ["runtime_reflection_policies.version"],
            name="fk_report_requests_reflection_policy",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "idempotency_key",
            name="uq_report_requests_idempotency_key",
        ),
        CheckConstraint(
            "report_type IN ('DATA_QUALITY_REPORT','EVIDENCE_SUMMARY',"
            "'FINANCIAL_RESEARCH_DRAFT','FULL_RESEARCH_DRAFT')",
            name="ck_report_requests_type",
        ),
        CheckConstraint(
            "report_locale IN ('zh-CN','en-US')",
            name="ck_report_requests_locale",
        ),
        CheckConstraint(
            "max_excerpt_length BETWEEN 1 AND 1000",
            name="ck_report_requests_excerpt_length",
        ),
        CheckConstraint(
            "manifest_checksum ~ '^[0-9a-f]{64}$' AND "
            "package_checksum ~ '^[0-9a-f]{64}$' AND "
            "claims_checksum ~ '^[0-9a-f]{64}$' AND "
            "evidence_checksum ~ '^[0-9a-f]{64}$' AND "
            "links_checksum ~ '^[0-9a-f]{64}$' AND "
            "citations_checksum ~ '^[0-9a-f]{64}$' AND "
            "lineage_checksum ~ '^[0-9a-f]{64}$' AND "
            "idempotency_key ~ '^[0-9a-f]{64}$'",
            name="ck_report_requests_checksums",
        ),
        CheckConstraint(
            "octet_length(manifest::text) <= 1048576",
            name="ck_report_requests_manifest_size",
        ),
        Index(
            "ix_report_requests_research_package",
            "research_package_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    research_package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    issuer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_as_of_time: Mapped[datetime] = mapped_column(nullable=False)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    report_locale: Mapped[str] = mapped_column(String(8), nullable=False)
    template_name: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    report_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    reflection_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_sections: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    include_evidence_appendix: Mapped[bool] = mapped_column(Boolean, nullable=False)
    include_claim_index: Mapped[bool] = mapped_column(Boolean, nullable=False)
    max_excerpt_length: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    package_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    claims_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    links_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    citations_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    lineage_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RuntimeReflectionPolicy(Base):
    __tablename__ = "runtime_reflection_policies"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_runtime_reflection_policies"),
        UniqueConstraint("version", name="uq_runtime_reflection_policies_version"),
        CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_runtime_reflection_policies_checksum",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportGenerationRun(Base):
    __tablename__ = "report_generation_runs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_report_generation_runs"),
        ForeignKeyConstraint(
            ["report_request_id"],
            ["report_requests.id"],
            name="fk_report_generation_runs_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["research_package_id"],
            ["research_packages.id"],
            name="fk_report_generation_runs_package",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_report_generation_runs_agent_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_report_generation_runs_security",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_report_generation_runs_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_policy_version"],
            ["report_policies.version"],
            name="fk_report_generation_runs_policy",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('CREATED','RUNNING','COMPLETED','PARTIAL','BLOCKED','FAILED')",
            name="ck_report_generation_runs_status",
        ),
        CheckConstraint(
            "warning_count BETWEEN 0 AND 1000",
            name="ck_report_generation_runs_warning_count",
        ),
        CheckConstraint(
            "idempotency_key ~ '^[0-9a-f]{64}$'",
            name="ck_report_generation_runs_idempotency",
        ),
        Index(
            "ux_report_generation_runs_reusable_key",
            "idempotency_key",
            unique=True,
            postgresql_where=("status IN ('CREATED','RUNNING','COMPLETED','PARTIAL','BLOCKED')"),
        ),
        Index("ix_report_generation_runs_package", "research_package_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    report_request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_as_of_time: Mapped[datetime] = mapped_column(nullable=False)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    report_locale: Mapped[str] = mapped_column(String(8), nullable=False)
    report_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    template_name: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(128), nullable=False)
    manifest_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    package_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    claims_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    links_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    citations_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    lineage_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False)
    blocked_reason_code: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str | None] = mapped_column(String(128))
    safe_error_message: Mapped[str | None] = mapped_column(String(256))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    terminal_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ResearchReport(Base):
    __tablename__ = "research_reports"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_research_reports"),
        ForeignKeyConstraint(
            ["report_generation_run_id"],
            ["report_generation_runs.id"],
            name="fk_research_reports_generation_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["previous_report_id"],
            ["research_reports.id"],
            name="fk_research_reports_previous",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_research_reports_security",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_research_reports_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["research_package_id"],
            ["research_packages.id"],
            name="fk_research_reports_package",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "report_generation_run_id",
            "report_version",
            name="uq_research_reports_generation_version",
        ),
        CheckConstraint("report_version >= 1", name="ck_research_reports_version"),
        CheckConstraint(
            "status IN ('DRAFT','REFLECTED','REVISED','PUBLISHABLE','PARTIAL','BLOCKED','FAILED')",
            name="ck_research_reports_status",
        ),
        CheckConstraint(
            "octet_length(markdown_content) BETWEEN 1 AND 1048576 "
            "AND octet_length(structured_content::text) <= 1048576",
            name="ck_research_reports_content_size",
        ),
        CheckConstraint(
            "input_manifest_checksum ~ '^[0-9a-f]{64}$' AND "
            "package_checksum ~ '^[0-9a-f]{64}$' AND "
            "structured_checksum ~ '^[0-9a-f]{64}$' AND "
            "markdown_checksum ~ '^[0-9a-f]{64}$' AND "
            "content_checksum ~ '^[0-9a-f]{64}$' AND "
            "claim_set_checksum ~ '^[0-9a-f]{64}$' AND "
            "evidence_set_checksum ~ '^[0-9a-f]{64}$' AND "
            "link_set_checksum ~ '^[0-9a-f]{64}$' AND "
            "citation_set_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_research_reports_checksums",
        ),
        Index(
            "ux_research_reports_previous",
            "previous_report_id",
            unique=True,
            postgresql_where="previous_report_id IS NOT NULL",
        ),
        Index(
            "ix_research_reports_security_snapshot_created",
            "security_id",
            "snapshot_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    report_generation_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    report_version: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_report_id: Mapped[UUID | None] = mapped_column(Uuid)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    report_locale: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(512))
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_as_of_time: Mapped[datetime] = mapped_column(nullable=False)
    research_package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    input_manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    package_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    structured_content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    markdown_content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    markdown_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_set_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_set_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    link_set_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    citation_set_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(128), nullable=False)
    template_name: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportSectionRow(Base):
    __tablename__ = "report_sections"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_report_sections"),
        ForeignKeyConstraint(
            ["research_report_id"],
            ["research_reports.id"],
            name="fk_report_sections_report",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "research_report_id",
            "section_index",
            name="uq_report_sections_report_index",
        ),
        UniqueConstraint(
            "research_report_id",
            "section_key",
            name="uq_report_sections_report_key",
        ),
        CheckConstraint(
            "section_index BETWEEN 0 AND 15",
            name="ck_report_sections_index",
        ),
        CheckConstraint(
            "status IN ('COMPLETE','PARTIAL','BLOCKED','NO_EVIDENCE','NOT_REQUESTED')",
            name="ck_report_sections_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    research_report_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    section_key: Mapped[str] = mapped_column(String(64), nullable=False)
    section_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportBlockRow(Base):
    __tablename__ = "report_blocks"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_report_blocks"),
        ForeignKeyConstraint(
            ["research_report_id"],
            ["research_reports.id"],
            name="fk_report_blocks_report",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_section_id"],
            ["report_sections.id"],
            name="fk_report_blocks_section",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "report_section_id",
            "block_index",
            name="uq_report_blocks_section_index",
        ),
        UniqueConstraint(
            "research_report_id",
            "block_key",
            name="uq_report_blocks_report_key",
        ),
        CheckConstraint(
            "block_index BETWEEN 0 AND 299",
            name="ck_report_blocks_index",
        ),
        CheckConstraint(
            "block_type IN ('HEADING','PARAGRAPH','BULLET_LIST','METRIC_TABLE',"
            "'EVIDENCE_TABLE','WARNING','LIMITATION','CONFLICT','CLAIM_INDEX',"
            "'CITATION_LIST')",
            name="ck_report_blocks_type",
        ),
        CheckConstraint(
            "status IN ('COMPLETE','PARTIAL','BLOCKED','NO_EVIDENCE','NOT_REQUESTED')",
            name="ck_report_blocks_status",
        ),
        CheckConstraint(
            "text_content IS NULL OR octet_length(text_content) <= 10000",
            name="ck_report_blocks_text_size",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    research_report_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    report_section_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    block_key: Mapped[str] = mapped_column(String(128), nullable=False)
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    block_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportClaimBinding(Base):
    __tablename__ = "report_claim_bindings"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_report_claim_bindings"),
        ForeignKeyConstraint(
            ["research_report_id"],
            ["research_reports.id"],
            name="fk_report_claim_bindings_report",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_block_id"],
            ["report_blocks.id"],
            name="fk_report_claim_bindings_block",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["claim_id"],
            ["research_claims.id"],
            name="fk_report_claim_bindings_claim",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "binding_role IN ('PRIMARY','SUPPORTING','CONTRADICTING','LIMITATION')",
            name="ck_report_claim_bindings_role",
        ),
        CheckConstraint(
            "(sentence_index IS NOT NULL) <> (item_or_row_key IS NOT NULL) "
            "AND (sentence_index IS NULL OR sentence_index BETWEEN 0 AND 999)",
            name="ck_report_claim_bindings_location",
        ),
        Index("ix_report_claim_bindings_block", "report_block_id"),
        Index("ix_report_claim_bindings_claim", "claim_id"),
        Index(
            "ux_report_claim_bindings_sentence",
            "report_block_id",
            "claim_id",
            "sentence_index",
            unique=True,
            postgresql_where="sentence_index IS NOT NULL",
        ),
        Index(
            "ux_report_claim_bindings_item",
            "report_block_id",
            "claim_id",
            "item_or_row_key",
            unique=True,
            postgresql_where="item_or_row_key IS NOT NULL",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    research_report_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    report_block_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    claim_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    binding_role: Mapped[str] = mapped_column(String(32), nullable=False)
    sentence_index: Mapped[int | None] = mapped_column(Integer)
    item_or_row_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportEvidenceBinding(Base):
    __tablename__ = "report_evidence_bindings"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_report_evidence_bindings"),
        ForeignKeyConstraint(
            ["research_report_id"],
            ["research_reports.id"],
            name="fk_report_evidence_bindings_report",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_block_id"],
            ["report_blocks.id"],
            name="fk_report_evidence_bindings_block",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_claim_binding_id"],
            ["report_claim_bindings.id"],
            name="fk_report_evidence_bindings_claim_binding",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["claim_evidence_link_id"],
            ["claim_evidence_links.id"],
            name="fk_report_evidence_bindings_link",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evidence_id"],
            ["research_evidence.id"],
            name="fk_report_evidence_bindings_evidence",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["citation_id"],
            ["citation_anchors.id"],
            name="fk_report_evidence_bindings_citation",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "report_claim_binding_id",
            "claim_evidence_link_id",
            name="uq_report_evidence_bindings_link",
        ),
        CheckConstraint(
            "binding_role IN ('PRIMARY','CORROBORATING','CONTRADICTING','CONTEXT','LIMITATION')",
            name="ck_report_evidence_bindings_role",
        ),
        CheckConstraint(
            "visible_reference_kind IN ('EVIDENCE','METRIC')",
            name="ck_report_evidence_bindings_reference_kind",
        ),
        CheckConstraint(
            "visible_reference ~ '^(EV|MET)-[0-9]{3}$'",
            name="ck_report_evidence_bindings_visible_reference",
        ),
        CheckConstraint(
            "source_checksum IS NULL OR source_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_report_evidence_bindings_source_checksum",
        ),
        UniqueConstraint(
            "research_report_id",
            "visible_reference",
            name="uq_report_evidence_bindings_visible_reference",
        ),
        Index("ix_report_evidence_bindings_block", "report_block_id"),
        Index("ix_report_evidence_bindings_evidence", "evidence_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    research_report_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    report_block_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    report_claim_binding_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    claim_evidence_link_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    binding_role: Mapped[str] = mapped_column(String(32), nullable=False)
    visible_reference_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    visible_reference: Mapped[str] = mapped_column(String(16), nullable=False)
    item_or_row_key: Mapped[str] = mapped_column(String(128), nullable=False)
    citation_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_record_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_checksum: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportCitationBinding(Base):
    __tablename__ = "report_citation_bindings"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_report_citation_bindings"),
        ForeignKeyConstraint(
            ["research_report_id"],
            ["research_reports.id"],
            name="fk_report_citation_bindings_report",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_block_id"],
            ["report_blocks.id"],
            name="fk_report_citation_bindings_block",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_evidence_binding_id"],
            ["report_evidence_bindings.id"],
            name="fk_report_citation_bindings_evidence_binding",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["citation_id"],
            ["citation_anchors.id"],
            name="fk_report_citation_bindings_citation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_report_citation_bindings_document",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "research_report_id",
            "visible_reference",
            name="uq_report_citation_bindings_visible_reference",
        ),
        CheckConstraint(
            "citation_status = 'VALID'",
            name="ck_report_citation_bindings_status",
        ),
        CheckConstraint(
            "rendered_excerpt_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_report_citation_bindings_checksum",
        ),
        CheckConstraint(
            "octet_length(rendered_excerpt) BETWEEN 1 AND 1000",
            name="ck_report_citation_bindings_excerpt_size",
        ),
        Index("ix_report_citation_bindings_block", "report_block_id"),
        Index("ix_report_citation_bindings_citation", "citation_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    research_report_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    report_block_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    report_evidence_binding_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    citation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    visible_reference: Mapped[str] = mapped_column(String(16), nullable=False)
    locator_summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    rendered_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_excerpt_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    citation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportReflectionRun(Base):
    __tablename__ = "report_reflection_runs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_report_reflection_runs"),
        ForeignKeyConstraint(
            ["research_report_id"],
            ["research_reports.id"],
            name="fk_report_reflection_runs_report",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["reflection_policy_version"],
            ["runtime_reflection_policies.version"],
            name="fk_report_reflection_runs_policy",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "research_report_id",
            "round_number",
            "reflection_policy_version",
            name="uq_report_reflection_runs_report_round_policy",
        ),
        CheckConstraint(
            "round_number BETWEEN 1 AND 2",
            name="ck_report_reflection_runs_round",
        ),
        CheckConstraint(
            "status IN ('RUNNING','PASS','FINDINGS','BLOCKED','FAILED')",
            name="ck_report_reflection_runs_status",
        ),
        CheckConstraint(
            "total_finding_count = critical_count + high_count + medium_count + low_count "
            "AND total_finding_count BETWEEN 0 AND 10000",
            name="ck_report_reflection_runs_counts",
        ),
        CheckConstraint(
            "input_report_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_report_reflection_runs_checksum",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    research_report_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reflection_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    engine_name: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(128), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    input_report_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    total_finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False)
    high_count: Mapped[int] = mapped_column(Integer, nullable=False)
    medium_count: Mapped[int] = mapped_column(Integer, nullable=False)
    low_count: Mapped[int] = mapped_column(Integer, nullable=False)
    blocked_reason_code: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str | None] = mapped_column(String(128))
    safe_error_message: Mapped[str | None] = mapped_column(String(256))
    completed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportReflectionFinding(Base):
    __tablename__ = "report_reflection_findings"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_report_reflection_findings"),
        ForeignKeyConstraint(
            ["report_reflection_run_id"],
            ["report_reflection_runs.id"],
            name="fk_report_reflection_findings_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["research_report_id"],
            ["research_reports.id"],
            name="fk_report_reflection_findings_report",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_section_id"],
            ["report_sections.id"],
            name="fk_report_reflection_findings_section",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_block_id"],
            ["report_blocks.id"],
            name="fk_report_reflection_findings_block",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["claim_id"],
            ["research_claims.id"],
            name="fk_report_reflection_findings_claim",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evidence_id"],
            ["research_evidence.id"],
            name="fk_report_reflection_findings_evidence",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["citation_id"],
            ["citation_anchors.id"],
            name="fk_report_reflection_findings_citation",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "report_reflection_run_id",
            "finding_code",
            "report_block_id",
            "claim_id",
            "evidence_id",
            "citation_id",
            name="uq_report_reflection_findings_identity",
        ),
        CheckConstraint(
            "severity IN ('CRITICAL','HIGH','MEDIUM','LOW')",
            name="ck_report_reflection_findings_severity",
        ),
        CheckConstraint(
            "octet_length(description) BETWEEN 1 AND 512",
            name="ck_report_reflection_findings_description",
        ),
        Index(
            "ix_report_reflection_findings_run_severity",
            "report_reflection_run_id",
            "severity",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    report_reflection_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_report_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    report_section_id: Mapped[UUID | None] = mapped_column(Uuid)
    report_block_id: Mapped[UUID | None] = mapped_column(Uuid)
    claim_id: Mapped[UUID | None] = mapped_column(Uuid)
    evidence_id: Mapped[UUID | None] = mapped_column(Uuid)
    citation_id: Mapped[UUID | None] = mapped_column(Uuid)
    finding_code: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    remediation_code: Mapped[str] = mapped_column(String(128), nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportRevisionRun(Base):
    __tablename__ = "report_revision_runs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_report_revision_runs"),
        ForeignKeyConstraint(
            ["source_report_id"],
            ["research_reports.id"],
            name="fk_report_revision_runs_source_report",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_reflection_run_id"],
            ["report_reflection_runs.id"],
            name="fk_report_revision_runs_source_reflection",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["target_report_id"],
            ["research_reports.id"],
            name="fk_report_revision_runs_target_report",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_policy_version"],
            ["report_policies.version"],
            name="fk_report_revision_runs_policy",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "source_report_id",
            name="uq_report_revision_runs_source_report",
        ),
        UniqueConstraint(
            "target_report_id",
            name="uq_report_revision_runs_target_report",
        ),
        CheckConstraint("revision_round = 1", name="ck_report_revision_runs_round"),
        CheckConstraint(
            "status IN ('RUNNING','COMPLETED','PARTIAL','BLOCKED','FAILED')",
            name="ck_report_revision_runs_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    source_report_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_reflection_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    target_report_id: Mapped[UUID | None] = mapped_column(Uuid)
    report_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    engine_name: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(128), nullable=False)
    revision_round: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    actions: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    applied_finding_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    unresolved_finding_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    blocked_reason_code: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str | None] = mapped_column(String(128))
    safe_error_message: Mapped[str | None] = mapped_column(String(256))
    completed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportReleaseGateRow(Base):
    __tablename__ = "report_release_gates"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_report_release_gates"),
        ForeignKeyConstraint(
            ["candidate_report_id"],
            ["research_reports.id"],
            name="fk_report_release_gates_candidate",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["round_two_reflection_run_id"],
            ["report_reflection_runs.id"],
            name="fk_report_release_gates_reflection",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["sealed_report_id"],
            ["research_reports.id"],
            name="fk_report_release_gates_sealed",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "candidate_report_id",
            "gate_version",
            name="uq_report_release_gates_candidate_version",
        ),
        UniqueConstraint(
            "sealed_report_id",
            name="uq_report_release_gates_sealed_report",
        ),
        CheckConstraint(
            "internal_release_status IN ('PUBLISHABLE','PARTIAL','BLOCKED','FAILED')",
            name="ck_report_release_gates_decision",
        ),
        CheckConstraint(
            "input_manifest_checksum ~ '^[0-9a-f]{64}$' AND report_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_report_release_gates_checksums",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    candidate_report_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    round_two_reflection_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sealed_report_id: Mapped[UUID | None] = mapped_column(Uuid)
    gate_version: Mapped[str] = mapped_column(String(128), nullable=False)
    input_manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    report_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    internal_release_status: Mapped[str] = mapped_column(String(16), nullable=False)
    requirements: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


STAGE8_MODEL_TABLES = (
    "report_policies",
    "report_template_versions",
    "runtime_reflection_policies",
    "report_requests",
    "report_generation_runs",
    "research_reports",
    "report_sections",
    "report_blocks",
    "report_claim_bindings",
    "report_evidence_bindings",
    "report_citation_bindings",
    "report_reflection_runs",
    "report_reflection_findings",
    "report_revision_runs",
    "report_release_gates",
)
