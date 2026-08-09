"""create verifiable reports and runtime reflection

Revision ID: 0007_verifiable_reports
Revises: 0006_controlled_research_agent
Create Date: 2026-07-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_verifiable_reports"
down_revision: str | Sequence[str] | None = "0006_controlled_research_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
CHECKSUM = r"^[0-9a-f]{64}$"


def _identity_columns() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def _fk(
    local: str,
    remote: str,
    name: str,
) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [local],
        [remote],
        name=name,
        ondelete="RESTRICT",
    )


def _create_reference_tables() -> None:
    op.create_table(
        "report_policies",
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("definition", JSONB, nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_report_policies"),
        sa.UniqueConstraint("version", name="uq_report_policies_version"),
        sa.CheckConstraint(
            "length(version) BETWEEN 3 AND 128",
            name="ck_report_policies_version",
        ),
        sa.CheckConstraint(
            f"checksum ~ '{CHECKSUM}'",
            name="ck_report_policies_checksum",
        ),
    )
    op.create_table(
        "report_template_versions",
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("locale", sa.String(8), nullable=False),
        sa.Column("template_schema_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("definition", JSONB, nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_report_template_versions"),
        sa.UniqueConstraint(
            "name",
            "version",
            "locale",
            name="uq_report_template_versions_identity",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','DEPRECATED','TEST_ONLY')",
            name="ck_report_template_versions_status",
        ),
        sa.CheckConstraint(
            f"checksum ~ '{CHECKSUM}'",
            name="ck_report_template_versions_checksum",
        ),
    )
    op.create_table(
        "runtime_reflection_policies",
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("definition", JSONB, nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_runtime_reflection_policies"),
        sa.UniqueConstraint(
            "version",
            name="uq_runtime_reflection_policies_version",
        ),
        sa.CheckConstraint(
            f"checksum ~ '{CHECKSUM}'",
            name="ck_runtime_reflection_policies_checksum",
        ),
    )


def _create_request_and_generation_tables() -> None:
    op.create_table(
        "report_requests",
        sa.Column("research_package_id", sa.Uuid(), nullable=False),
        sa.Column("research_agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("research_request_id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("issuer_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("research_as_of_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("report_locale", sa.String(8), nullable=False),
        sa.Column("template_name", sa.String(64), nullable=False),
        sa.Column("template_version", sa.String(32), nullable=False),
        sa.Column("report_policy_version", sa.String(128), nullable=False),
        sa.Column("reflection_policy_version", sa.String(128), nullable=False),
        sa.Column("requested_sections", JSONB, nullable=False),
        sa.Column("include_evidence_appendix", sa.Boolean(), nullable=False),
        sa.Column("include_claim_index", sa.Boolean(), nullable=False),
        sa.Column("max_excerpt_length", sa.Integer(), nullable=False),
        sa.Column("manifest_schema_version", sa.String(64), nullable=False),
        sa.Column("manifest", JSONB, nullable=False),
        sa.Column("manifest_checksum", sa.String(64), nullable=False),
        sa.Column("package_checksum", sa.String(64), nullable=False),
        sa.Column("claims_checksum", sa.String(64), nullable=False),
        sa.Column("evidence_checksum", sa.String(64), nullable=False),
        sa.Column("links_checksum", sa.String(64), nullable=False),
        sa.Column("citations_checksum", sa.String(64), nullable=False),
        sa.Column("lineage_checksum", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_report_requests"),
        _fk("research_package_id", "research_packages.id", "fk_report_requests_package"),
        _fk("research_agent_run_id", "research_agent_runs.id", "fk_report_requests_run"),
        _fk(
            "research_request_id",
            "research_requests.id",
            "fk_report_requests_research_request",
        ),
        _fk("security_id", "securities.id", "fk_report_requests_security"),
        _fk("issuer_id", "issuers.id", "fk_report_requests_issuer"),
        _fk("snapshot_id", "data_snapshots.id", "fk_report_requests_snapshot"),
        _fk(
            "report_policy_version",
            "report_policies.version",
            "fk_report_requests_policy",
        ),
        _fk(
            "reflection_policy_version",
            "runtime_reflection_policies.version",
            "fk_report_requests_reflection_policy",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_report_requests_idempotency_key"),
        sa.CheckConstraint(
            "report_type IN ('DATA_QUALITY_REPORT','EVIDENCE_SUMMARY',"
            "'FINANCIAL_RESEARCH_DRAFT','FULL_RESEARCH_DRAFT')",
            name="ck_report_requests_type",
        ),
        sa.CheckConstraint(
            "report_locale IN ('zh-CN','en-US')",
            name="ck_report_requests_locale",
        ),
        sa.CheckConstraint(
            "max_excerpt_length BETWEEN 1 AND 1000",
            name="ck_report_requests_excerpt_length",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "octet_length(manifest::text) <= 1048576",
            name="ck_report_requests_manifest_size",
        ),
    )
    op.create_index(
        "ix_report_requests_research_package",
        "report_requests",
        ["research_package_id"],
    )
    op.create_table(
        "report_generation_runs",
        sa.Column("report_request_id", sa.Uuid(), nullable=False),
        sa.Column("research_package_id", sa.Uuid(), nullable=False),
        sa.Column("research_agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("research_as_of_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("report_locale", sa.String(8), nullable=False),
        sa.Column("report_policy_version", sa.String(128), nullable=False),
        sa.Column("template_name", sa.String(64), nullable=False),
        sa.Column("template_version", sa.String(32), nullable=False),
        sa.Column("renderer_version", sa.String(128), nullable=False),
        sa.Column("manifest_schema_version", sa.String(64), nullable=False),
        sa.Column("manifest_checksum", sa.String(64), nullable=False),
        sa.Column("package_checksum", sa.String(64), nullable=False),
        sa.Column("claims_checksum", sa.String(64), nullable=False),
        sa.Column("evidence_checksum", sa.String(64), nullable=False),
        sa.Column("links_checksum", sa.String(64), nullable=False),
        sa.Column("citations_checksum", sa.String(64), nullable=False),
        sa.Column("lineage_checksum", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("blocked_reason_code", sa.String(128), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("safe_error_message", sa.String(256), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_report_generation_runs"),
        _fk("report_request_id", "report_requests.id", "fk_report_generation_runs_request"),
        _fk(
            "research_package_id",
            "research_packages.id",
            "fk_report_generation_runs_package",
        ),
        _fk(
            "research_agent_run_id",
            "research_agent_runs.id",
            "fk_report_generation_runs_agent_run",
        ),
        _fk("security_id", "securities.id", "fk_report_generation_runs_security"),
        _fk("snapshot_id", "data_snapshots.id", "fk_report_generation_runs_snapshot"),
        _fk(
            "report_policy_version",
            "report_policies.version",
            "fk_report_generation_runs_policy",
        ),
        sa.CheckConstraint(
            "status IN ('CREATED','RUNNING','COMPLETED','PARTIAL','BLOCKED','FAILED')",
            name="ck_report_generation_runs_status",
        ),
        sa.CheckConstraint(
            "warning_count BETWEEN 0 AND 1000",
            name="ck_report_generation_runs_warning_count",
        ),
        sa.CheckConstraint(
            f"idempotency_key ~ '{CHECKSUM}'",
            name="ck_report_generation_runs_idempotency",
        ),
    )
    op.create_index(
        "ux_report_generation_runs_reusable_key",
        "report_generation_runs",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('CREATED','RUNNING','COMPLETED','PARTIAL','BLOCKED')"),
    )
    op.create_index(
        "ix_report_generation_runs_package",
        "report_generation_runs",
        ["research_package_id"],
    )


def _create_report_tables() -> None:
    op.create_table(
        "research_reports",
        sa.Column("report_generation_run_id", sa.Uuid(), nullable=False),
        sa.Column("report_version", sa.Integer(), nullable=False),
        sa.Column("previous_report_id", sa.Uuid(), nullable=True),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("report_locale", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("subtitle", sa.String(512), nullable=True),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("research_as_of_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("research_package_id", sa.Uuid(), nullable=False),
        sa.Column("input_manifest_checksum", sa.String(64), nullable=False),
        sa.Column("package_checksum", sa.String(64), nullable=False),
        sa.Column("structured_content", JSONB, nullable=False),
        sa.Column("markdown_content", sa.Text(), nullable=False),
        sa.Column("structured_checksum", sa.String(64), nullable=False),
        sa.Column("markdown_checksum", sa.String(64), nullable=False),
        sa.Column("content_checksum", sa.String(64), nullable=False),
        sa.Column("claim_set_checksum", sa.String(64), nullable=False),
        sa.Column("evidence_set_checksum", sa.String(64), nullable=False),
        sa.Column("link_set_checksum", sa.String(64), nullable=False),
        sa.Column("citation_set_checksum", sa.String(64), nullable=False),
        sa.Column("renderer_version", sa.String(128), nullable=False),
        sa.Column("template_name", sa.String(64), nullable=False),
        sa.Column("template_version", sa.String(32), nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_research_reports"),
        _fk(
            "report_generation_run_id",
            "report_generation_runs.id",
            "fk_research_reports_generation_run",
        ),
        _fk("previous_report_id", "research_reports.id", "fk_research_reports_previous"),
        _fk("security_id", "securities.id", "fk_research_reports_security"),
        _fk("snapshot_id", "data_snapshots.id", "fk_research_reports_snapshot"),
        _fk("research_package_id", "research_packages.id", "fk_research_reports_package"),
        sa.UniqueConstraint(
            "report_generation_run_id",
            "report_version",
            name="uq_research_reports_generation_version",
        ),
        sa.CheckConstraint(
            "report_version >= 1",
            name="ck_research_reports_version",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','REFLECTED','REVISED','PUBLISHABLE','PARTIAL','BLOCKED','FAILED')",
            name="ck_research_reports_status",
        ),
        sa.CheckConstraint(
            "octet_length(markdown_content) BETWEEN 1 AND 1048576 "
            "AND octet_length(structured_content::text) <= 1048576",
            name="ck_research_reports_content_size",
        ),
        sa.CheckConstraint(
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
    )
    op.create_index(
        "ux_research_reports_previous",
        "research_reports",
        ["previous_report_id"],
        unique=True,
        postgresql_where=sa.text("previous_report_id IS NOT NULL"),
    )
    op.create_index(
        "ix_research_reports_security_snapshot_created",
        "research_reports",
        ["security_id", "snapshot_id", "created_at"],
    )
    op.create_table(
        "report_sections",
        sa.Column("research_report_id", sa.Uuid(), nullable=False),
        sa.Column("section_key", sa.String(64), nullable=False),
        sa.Column("section_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_report_sections"),
        _fk("research_report_id", "research_reports.id", "fk_report_sections_report"),
        sa.UniqueConstraint(
            "research_report_id",
            "section_index",
            name="uq_report_sections_report_index",
        ),
        sa.UniqueConstraint(
            "research_report_id",
            "section_key",
            name="uq_report_sections_report_key",
        ),
        sa.CheckConstraint(
            "section_index BETWEEN 0 AND 15",
            name="ck_report_sections_index",
        ),
        sa.CheckConstraint(
            "status IN ('COMPLETE','PARTIAL','BLOCKED','NO_EVIDENCE','NOT_REQUESTED')",
            name="ck_report_sections_status",
        ),
    )
    op.create_table(
        "report_blocks",
        sa.Column("research_report_id", sa.Uuid(), nullable=False),
        sa.Column("report_section_id", sa.Uuid(), nullable=False),
        sa.Column("block_key", sa.String(128), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_report_blocks"),
        _fk("research_report_id", "research_reports.id", "fk_report_blocks_report"),
        _fk("report_section_id", "report_sections.id", "fk_report_blocks_section"),
        sa.UniqueConstraint(
            "report_section_id",
            "block_index",
            name="uq_report_blocks_section_index",
        ),
        sa.UniqueConstraint(
            "research_report_id",
            "block_key",
            name="uq_report_blocks_report_key",
        ),
        sa.CheckConstraint(
            "block_index BETWEEN 0 AND 299",
            name="ck_report_blocks_index",
        ),
        sa.CheckConstraint(
            "block_type IN ('HEADING','PARAGRAPH','BULLET_LIST','METRIC_TABLE',"
            "'EVIDENCE_TABLE','WARNING','LIMITATION','CONFLICT','CLAIM_INDEX',"
            "'CITATION_LIST')",
            name="ck_report_blocks_type",
        ),
        sa.CheckConstraint(
            "status IN ('COMPLETE','PARTIAL','BLOCKED','NO_EVIDENCE','NOT_REQUESTED')",
            name="ck_report_blocks_status",
        ),
        sa.CheckConstraint(
            "text_content IS NULL OR octet_length(text_content) <= 10000",
            name="ck_report_blocks_text_size",
        ),
    )


def _create_binding_tables() -> None:
    op.create_table(
        "report_claim_bindings",
        sa.Column("research_report_id", sa.Uuid(), nullable=False),
        sa.Column("report_block_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("binding_role", sa.String(32), nullable=False),
        sa.Column("sentence_index", sa.Integer(), nullable=True),
        sa.Column("item_or_row_key", sa.String(128), nullable=True),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_report_claim_bindings"),
        _fk(
            "research_report_id",
            "research_reports.id",
            "fk_report_claim_bindings_report",
        ),
        _fk("report_block_id", "report_blocks.id", "fk_report_claim_bindings_block"),
        _fk("claim_id", "research_claims.id", "fk_report_claim_bindings_claim"),
        sa.CheckConstraint(
            "binding_role IN ('PRIMARY','SUPPORTING','CONTRADICTING','LIMITATION')",
            name="ck_report_claim_bindings_role",
        ),
        sa.CheckConstraint(
            "(sentence_index IS NOT NULL) <> (item_or_row_key IS NOT NULL) "
            "AND (sentence_index IS NULL OR sentence_index BETWEEN 0 AND 999)",
            name="ck_report_claim_bindings_location",
        ),
    )
    op.create_index(
        "ix_report_claim_bindings_block",
        "report_claim_bindings",
        ["report_block_id"],
    )
    op.create_index(
        "ix_report_claim_bindings_claim",
        "report_claim_bindings",
        ["claim_id"],
    )
    op.create_index(
        "ux_report_claim_bindings_sentence",
        "report_claim_bindings",
        ["report_block_id", "claim_id", "sentence_index"],
        unique=True,
        postgresql_where=sa.text("sentence_index IS NOT NULL"),
    )
    op.create_index(
        "ux_report_claim_bindings_item",
        "report_claim_bindings",
        ["report_block_id", "claim_id", "item_or_row_key"],
        unique=True,
        postgresql_where=sa.text("item_or_row_key IS NOT NULL"),
    )
    op.create_table(
        "report_evidence_bindings",
        sa.Column("research_report_id", sa.Uuid(), nullable=False),
        sa.Column("report_block_id", sa.Uuid(), nullable=False),
        sa.Column("report_claim_binding_id", sa.Uuid(), nullable=False),
        sa.Column("claim_evidence_link_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("binding_role", sa.String(32), nullable=False),
        sa.Column("visible_reference_kind", sa.String(16), nullable=False),
        sa.Column("visible_reference", sa.String(16), nullable=False),
        sa.Column("item_or_row_key", sa.String(128), nullable=False),
        sa.Column("citation_id", sa.Uuid(), nullable=True),
        sa.Column("source_record_id", sa.Uuid(), nullable=True),
        sa.Column("source_checksum", sa.String(64), nullable=True),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_report_evidence_bindings"),
        _fk(
            "research_report_id",
            "research_reports.id",
            "fk_report_evidence_bindings_report",
        ),
        _fk("report_block_id", "report_blocks.id", "fk_report_evidence_bindings_block"),
        _fk(
            "report_claim_binding_id",
            "report_claim_bindings.id",
            "fk_report_evidence_bindings_claim_binding",
        ),
        _fk(
            "claim_evidence_link_id",
            "claim_evidence_links.id",
            "fk_report_evidence_bindings_link",
        ),
        _fk(
            "evidence_id",
            "research_evidence.id",
            "fk_report_evidence_bindings_evidence",
        ),
        _fk(
            "citation_id",
            "citation_anchors.id",
            "fk_report_evidence_bindings_citation",
        ),
        sa.UniqueConstraint(
            "report_claim_binding_id",
            "claim_evidence_link_id",
            name="uq_report_evidence_bindings_link",
        ),
        sa.CheckConstraint(
            "binding_role IN ('PRIMARY','CORROBORATING','CONTRADICTING','CONTEXT','LIMITATION')",
            name="ck_report_evidence_bindings_role",
        ),
        sa.CheckConstraint(
            "visible_reference_kind IN ('EVIDENCE','METRIC')",
            name="ck_report_evidence_bindings_reference_kind",
        ),
        sa.CheckConstraint(
            "visible_reference ~ '^(EV|MET)-[0-9]{3}$'",
            name="ck_report_evidence_bindings_visible_reference",
        ),
        sa.CheckConstraint(
            f"source_checksum IS NULL OR source_checksum ~ '{CHECKSUM}'",
            name="ck_report_evidence_bindings_source_checksum",
        ),
        sa.UniqueConstraint(
            "research_report_id",
            "visible_reference",
            name="uq_report_evidence_bindings_visible_reference",
        ),
    )
    op.create_index(
        "ix_report_evidence_bindings_block",
        "report_evidence_bindings",
        ["report_block_id"],
    )
    op.create_index(
        "ix_report_evidence_bindings_evidence",
        "report_evidence_bindings",
        ["evidence_id"],
    )
    op.create_table(
        "report_citation_bindings",
        sa.Column("research_report_id", sa.Uuid(), nullable=False),
        sa.Column("report_block_id", sa.Uuid(), nullable=False),
        sa.Column("report_evidence_binding_id", sa.Uuid(), nullable=False),
        sa.Column("citation_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("visible_reference", sa.String(16), nullable=False),
        sa.Column("locator_summary", sa.String(1000), nullable=False),
        sa.Column("rendered_excerpt", sa.Text(), nullable=False),
        sa.Column("rendered_excerpt_checksum", sa.String(64), nullable=False),
        sa.Column("citation_status", sa.String(16), nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_report_citation_bindings"),
        _fk(
            "research_report_id",
            "research_reports.id",
            "fk_report_citation_bindings_report",
        ),
        _fk("report_block_id", "report_blocks.id", "fk_report_citation_bindings_block"),
        _fk(
            "report_evidence_binding_id",
            "report_evidence_bindings.id",
            "fk_report_citation_bindings_evidence_binding",
        ),
        _fk(
            "citation_id",
            "citation_anchors.id",
            "fk_report_citation_bindings_citation",
        ),
        _fk(
            "document_version_id",
            "document_versions.id",
            "fk_report_citation_bindings_document",
        ),
        sa.UniqueConstraint(
            "research_report_id",
            "visible_reference",
            name="uq_report_citation_bindings_visible_reference",
        ),
        sa.CheckConstraint(
            "citation_status = 'VALID'",
            name="ck_report_citation_bindings_status",
        ),
        sa.CheckConstraint(
            f"rendered_excerpt_checksum ~ '{CHECKSUM}'",
            name="ck_report_citation_bindings_checksum",
        ),
        sa.CheckConstraint(
            "octet_length(rendered_excerpt) BETWEEN 1 AND 1000",
            name="ck_report_citation_bindings_excerpt_size",
        ),
    )
    op.create_index(
        "ix_report_citation_bindings_block",
        "report_citation_bindings",
        ["report_block_id"],
    )
    op.create_index(
        "ix_report_citation_bindings_citation",
        "report_citation_bindings",
        ["citation_id"],
    )


def _create_reflection_revision_gate_tables() -> None:
    op.create_table(
        "report_reflection_runs",
        sa.Column("research_report_id", sa.Uuid(), nullable=False),
        sa.Column("reflection_policy_version", sa.String(128), nullable=False),
        sa.Column("engine_name", sa.String(64), nullable=False),
        sa.Column("engine_version", sa.String(128), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("input_report_checksum", sa.String(64), nullable=False),
        sa.Column("total_finding_count", sa.Integer(), nullable=False),
        sa.Column("critical_count", sa.Integer(), nullable=False),
        sa.Column("high_count", sa.Integer(), nullable=False),
        sa.Column("medium_count", sa.Integer(), nullable=False),
        sa.Column("low_count", sa.Integer(), nullable=False),
        sa.Column("blocked_reason_code", sa.String(128), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("safe_error_message", sa.String(256), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_report_reflection_runs"),
        _fk(
            "research_report_id",
            "research_reports.id",
            "fk_report_reflection_runs_report",
        ),
        _fk(
            "reflection_policy_version",
            "runtime_reflection_policies.version",
            "fk_report_reflection_runs_policy",
        ),
        sa.UniqueConstraint(
            "research_report_id",
            "round_number",
            "reflection_policy_version",
            name="uq_report_reflection_runs_report_round_policy",
        ),
        sa.CheckConstraint(
            "round_number BETWEEN 1 AND 2",
            name="ck_report_reflection_runs_round",
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING','PASS','FINDINGS','BLOCKED','FAILED')",
            name="ck_report_reflection_runs_status",
        ),
        sa.CheckConstraint(
            "total_finding_count = critical_count + high_count + medium_count + low_count "
            "AND total_finding_count BETWEEN 0 AND 10000",
            name="ck_report_reflection_runs_counts",
        ),
        sa.CheckConstraint(
            f"input_report_checksum ~ '{CHECKSUM}'",
            name="ck_report_reflection_runs_checksum",
        ),
    )
    op.create_table(
        "report_reflection_findings",
        sa.Column("report_reflection_run_id", sa.Uuid(), nullable=False),
        sa.Column("research_report_id", sa.Uuid(), nullable=False),
        sa.Column("report_section_id", sa.Uuid(), nullable=True),
        sa.Column("report_block_id", sa.Uuid(), nullable=True),
        sa.Column("claim_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_id", sa.Uuid(), nullable=True),
        sa.Column("citation_id", sa.Uuid(), nullable=True),
        sa.Column("finding_code", sa.String(128), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("description", sa.String(512), nullable=False),
        sa.Column("remediation_code", sa.String(128), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_report_reflection_findings"),
        _fk(
            "report_reflection_run_id",
            "report_reflection_runs.id",
            "fk_report_reflection_findings_run",
        ),
        _fk(
            "research_report_id",
            "research_reports.id",
            "fk_report_reflection_findings_report",
        ),
        _fk(
            "report_section_id",
            "report_sections.id",
            "fk_report_reflection_findings_section",
        ),
        _fk(
            "report_block_id",
            "report_blocks.id",
            "fk_report_reflection_findings_block",
        ),
        _fk("claim_id", "research_claims.id", "fk_report_reflection_findings_claim"),
        _fk(
            "evidence_id",
            "research_evidence.id",
            "fk_report_reflection_findings_evidence",
        ),
        _fk(
            "citation_id",
            "citation_anchors.id",
            "fk_report_reflection_findings_citation",
        ),
        sa.UniqueConstraint(
            "report_reflection_run_id",
            "finding_code",
            "report_block_id",
            "claim_id",
            "evidence_id",
            "citation_id",
            name="uq_report_reflection_findings_identity",
        ),
        sa.CheckConstraint(
            "severity IN ('CRITICAL','HIGH','MEDIUM','LOW')",
            name="ck_report_reflection_findings_severity",
        ),
        sa.CheckConstraint(
            "octet_length(description) BETWEEN 1 AND 512",
            name="ck_report_reflection_findings_description",
        ),
    )
    op.create_index(
        "ix_report_reflection_findings_run_severity",
        "report_reflection_findings",
        ["report_reflection_run_id", "severity"],
    )
    op.create_table(
        "report_revision_runs",
        sa.Column("source_report_id", sa.Uuid(), nullable=False),
        sa.Column("source_reflection_run_id", sa.Uuid(), nullable=False),
        sa.Column("target_report_id", sa.Uuid(), nullable=True),
        sa.Column("report_policy_version", sa.String(128), nullable=False),
        sa.Column("engine_name", sa.String(64), nullable=False),
        sa.Column("engine_version", sa.String(128), nullable=False),
        sa.Column("revision_round", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("actions", JSONB, nullable=False),
        sa.Column("applied_finding_ids", JSONB, nullable=False),
        sa.Column("unresolved_finding_ids", JSONB, nullable=False),
        sa.Column("blocked_reason_code", sa.String(128), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("safe_error_message", sa.String(256), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_report_revision_runs"),
        _fk(
            "source_report_id",
            "research_reports.id",
            "fk_report_revision_runs_source_report",
        ),
        _fk(
            "source_reflection_run_id",
            "report_reflection_runs.id",
            "fk_report_revision_runs_source_reflection",
        ),
        _fk(
            "target_report_id",
            "research_reports.id",
            "fk_report_revision_runs_target_report",
        ),
        _fk(
            "report_policy_version",
            "report_policies.version",
            "fk_report_revision_runs_policy",
        ),
        sa.UniqueConstraint(
            "source_report_id",
            name="uq_report_revision_runs_source_report",
        ),
        sa.UniqueConstraint(
            "target_report_id",
            name="uq_report_revision_runs_target_report",
        ),
        sa.CheckConstraint(
            "revision_round = 1",
            name="ck_report_revision_runs_round",
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING','COMPLETED','PARTIAL','BLOCKED','FAILED')",
            name="ck_report_revision_runs_status",
        ),
    )
    op.create_table(
        "report_release_gates",
        sa.Column("candidate_report_id", sa.Uuid(), nullable=False),
        sa.Column("round_two_reflection_run_id", sa.Uuid(), nullable=False),
        sa.Column("sealed_report_id", sa.Uuid(), nullable=True),
        sa.Column("gate_version", sa.String(128), nullable=False),
        sa.Column("input_manifest_checksum", sa.String(64), nullable=False),
        sa.Column("report_checksum", sa.String(64), nullable=False),
        sa.Column("internal_release_status", sa.String(16), nullable=False),
        sa.Column("requirements", JSONB, nullable=False),
        sa.Column("reason_codes", JSONB, nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_report_release_gates"),
        _fk(
            "candidate_report_id",
            "research_reports.id",
            "fk_report_release_gates_candidate",
        ),
        _fk(
            "round_two_reflection_run_id",
            "report_reflection_runs.id",
            "fk_report_release_gates_reflection",
        ),
        _fk(
            "sealed_report_id",
            "research_reports.id",
            "fk_report_release_gates_sealed",
        ),
        sa.UniqueConstraint(
            "candidate_report_id",
            "gate_version",
            name="uq_report_release_gates_candidate_version",
        ),
        sa.UniqueConstraint(
            "sealed_report_id",
            name="uq_report_release_gates_sealed_report",
        ),
        sa.CheckConstraint(
            "internal_release_status IN ('PUBLISHABLE','PARTIAL','BLOCKED','FAILED')",
            name="ck_report_release_gates_decision",
        ),
        sa.CheckConstraint(
            "input_manifest_checksum ~ '^[0-9a-f]{64}$' AND report_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_report_release_gates_checksums",
        ),
    )


def _create_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION stage8_reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'STAGE8_IMMUTABLE_RECORD';
        END;
        $$;
        """
    )
    immutable_tables = (
        "report_policies",
        "report_template_versions",
        "runtime_reflection_policies",
        "report_requests",
        "research_reports",
        "report_sections",
        "report_blocks",
        "report_claim_bindings",
        "report_evidence_bindings",
        "report_citation_bindings",
        "report_reflection_findings",
        "report_release_gates",
    )
    for table in immutable_tables:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION stage8_reject_mutation();
            """
        )
    op.execute(
        """
        CREATE FUNCTION stage8_guard_lifecycle() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            terminal text[];
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'STAGE8_LIFECYCLE_DELETE_FORBIDDEN';
            END IF;
            IF TG_TABLE_NAME = 'report_generation_runs' THEN
                terminal := ARRAY['COMPLETED','PARTIAL','BLOCKED','FAILED'];
                IF OLD.status = ANY(terminal)
                   OR NOT (
                       (OLD.status = 'CREATED' AND NEW.status = 'RUNNING')
                       OR (OLD.status = 'RUNNING' AND NEW.status = ANY(terminal))
                   ) THEN
                    RAISE EXCEPTION 'STAGE8_GENERATION_TRANSITION_FORBIDDEN';
                END IF;
                IF to_jsonb(OLD) - ARRAY[
                    'status','warning_count','blocked_reason_code','error_code',
                    'safe_error_message','updated_at','terminal_at'
                ] <> to_jsonb(NEW) - ARRAY[
                    'status','warning_count','blocked_reason_code','error_code',
                    'safe_error_message','updated_at','terminal_at'
                ] THEN
                    RAISE EXCEPTION 'STAGE8_GENERATION_CONTEXT_MUTATION_FORBIDDEN';
                END IF;
            ELSIF TG_TABLE_NAME = 'report_reflection_runs' THEN
                terminal := ARRAY['PASS','FINDINGS','BLOCKED','FAILED'];
                IF OLD.status <> 'RUNNING' OR NOT NEW.status = ANY(terminal) THEN
                    RAISE EXCEPTION 'STAGE8_REFLECTION_TRANSITION_FORBIDDEN';
                END IF;
                IF to_jsonb(OLD) - ARRAY[
                    'status','total_finding_count','critical_count','high_count',
                    'medium_count','low_count','blocked_reason_code','error_code',
                    'safe_error_message','completed_at'
                ] <> to_jsonb(NEW) - ARRAY[
                    'status','total_finding_count','critical_count','high_count',
                    'medium_count','low_count','blocked_reason_code','error_code',
                    'safe_error_message','completed_at'
                ] THEN
                    RAISE EXCEPTION 'STAGE8_REFLECTION_CONTEXT_MUTATION_FORBIDDEN';
                END IF;
            ELSE
                terminal := ARRAY['COMPLETED','PARTIAL','BLOCKED','FAILED'];
                IF OLD.status <> 'RUNNING' OR NOT NEW.status = ANY(terminal) THEN
                    RAISE EXCEPTION 'STAGE8_REVISION_TRANSITION_FORBIDDEN';
                END IF;
                IF to_jsonb(OLD) - ARRAY[
                    'status','target_report_id','actions','applied_finding_ids',
                    'unresolved_finding_ids','blocked_reason_code','error_code',
                    'safe_error_message','completed_at'
                ] <> to_jsonb(NEW) - ARRAY[
                    'status','target_report_id','actions','applied_finding_ids',
                    'unresolved_finding_ids','blocked_reason_code','error_code',
                    'safe_error_message','completed_at'
                ] THEN
                    RAISE EXCEPTION 'STAGE8_REVISION_CONTEXT_MUTATION_FORBIDDEN';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    for table in (
        "report_generation_runs",
        "report_reflection_runs",
        "report_revision_runs",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_lifecycle
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION stage8_guard_lifecycle();
            """
        )
    op.execute(
        """
        CREATE FUNCTION stage8_validate_report_version() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            parent_run uuid;
            parent_version integer;
        BEGIN
            IF NEW.previous_report_id IS NULL THEN
                IF NEW.report_version <> 1 THEN
                    RAISE EXCEPTION 'STAGE8_INITIAL_REPORT_VERSION_INVALID';
                END IF;
                RETURN NEW;
            END IF;
            SELECT report_generation_run_id, report_version
              INTO parent_run, parent_version
              FROM research_reports
             WHERE id = NEW.previous_report_id;
            IF parent_run IS NULL
               OR parent_run <> NEW.report_generation_run_id
               OR NEW.report_version <> parent_version + 1 THEN
                RAISE EXCEPTION 'STAGE8_REPORT_VERSION_CHAIN_INVALID';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_reports_validate_version
        BEFORE INSERT ON research_reports
        FOR EACH ROW EXECUTE FUNCTION stage8_validate_report_version();
        """
    )


def upgrade() -> None:
    _create_reference_tables()
    _create_request_and_generation_tables()
    _create_report_tables()
    _create_binding_tables()
    _create_reflection_revision_gate_tables()
    _create_guards()


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS stage8_validate_report_version() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS stage8_guard_lifecycle() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS stage8_reject_mutation() CASCADE")
    for table in (
        "report_release_gates",
        "report_revision_runs",
        "report_reflection_findings",
        "report_reflection_runs",
        "report_citation_bindings",
        "report_evidence_bindings",
        "report_claim_bindings",
        "report_blocks",
        "report_sections",
        "research_reports",
        "report_generation_runs",
        "report_requests",
        "runtime_reflection_policies",
        "report_template_versions",
        "report_policies",
    ):
        op.drop_table(table)
