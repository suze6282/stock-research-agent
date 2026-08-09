"""create controlled research agent

Revision ID: 0006_controlled_research_agent
Revises: 0005_rag_citations
Create Date: 2026-07-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_controlled_research_agent"
down_revision: str | Sequence[str] | None = "0005_rag_citations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


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


def _create_tables() -> None:
    op.create_table(
        "research_policies",
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("definition", JSONB, nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_research_policies"),
        sa.UniqueConstraint("version", name="uq_research_policies_version"),
        sa.CheckConstraint(
            "length(version) BETWEEN 3 AND 128",
            name="ck_research_policies_version",
        ),
        sa.CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_research_policies_checksum",
        ),
    )
    op.create_table(
        "research_requests",
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("security_query", sa.String(256), nullable=False),
        sa.Column("normalized_security_query", sa.String(256), nullable=False),
        sa.Column("research_type", sa.String(64), nullable=False),
        sa.Column("research_mode", sa.String(32), nullable=False),
        sa.Column("research_as_of_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_sections", JSONB, nullable=False),
        sa.Column("requested_budgets", JSONB, nullable=False),
        sa.Column("policy_version", sa.String(128), nullable=False),
        sa.Column("planner_version", sa.String(128), nullable=False),
        sa.Column("tool_catalog_version", sa.String(80), nullable=False),
        sa.Column("tool_catalog_checksum", sa.String(64), nullable=False),
        sa.Column("request_checksum", sa.String(64), nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_research_requests"),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_research_requests_security",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_research_requests_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_version"],
            ["research_policies.version"],
            name="fk_research_requests_policy",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "request_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_research_requests_checksum",
        ),
        sa.CheckConstraint(
            "length(security_query) BETWEEN 1 AND 256 "
            "AND length(normalized_security_query) BETWEEN 1 AND 256",
            name="ck_research_requests_query",
        ),
    )
    op.create_index(
        "ix_research_requests_security_as_of",
        "research_requests",
        ["security_id", "research_as_of_time"],
    )
    op.create_table(
        "research_agent_runs",
        sa.Column("research_request_id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("research_as_of_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("research_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("policy_version", sa.String(128), nullable=False),
        sa.Column("planner_version", sa.String(128), nullable=False),
        sa.Column("tool_catalog_version", sa.String(80), nullable=False),
        sa.Column("tool_catalog_checksum", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("budget", JSONB, nullable=False),
        sa.Column("warning_codes", JSONB, nullable=False),
        sa.Column("terminal_reason_code", sa.String(128), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_research_agent_runs"),
        sa.ForeignKeyConstraint(
            ["research_request_id"],
            ["research_requests.id"],
            name="fk_research_agent_runs_request",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_research_agent_runs_security",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_research_agent_runs_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_version"],
            ["research_policies.version"],
            name="fk_research_agent_runs_policy",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('CREATED','PLANNING','PLANNED','RUNNING','PAUSED',"
            "'COMPLETED','PARTIAL','BLOCKED','FAILED','CANCELLED')",
            name="ck_research_agent_runs_status",
        ),
        sa.CheckConstraint(
            "idempotency_key ~ '^[0-9a-f]{64}$'",
            name="ck_research_agent_runs_idempotency",
        ),
    )
    op.create_index(
        "ux_research_agent_runs_reusable_key",
        "research_agent_runs",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('CREATED','PLANNING','PLANNED','RUNNING','PAUSED','COMPLETED')"
        ),
    )
    op.create_index(
        "ix_research_agent_runs_security_snapshot",
        "research_agent_runs",
        ["security_id", "snapshot_id"],
    )
    op.create_index("ix_research_agent_runs_status", "research_agent_runs", ["status"])
    op.create_table(
        "research_plans",
        sa.Column("research_agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("planner_version", sa.String(128), nullable=False),
        sa.Column("plan_version", sa.String(128), nullable=False),
        sa.Column("tool_catalog_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("steps", JSONB, nullable=False),
        sa.Column("plan_checksum", sa.String(64), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_research_plans"),
        sa.ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_plans_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("research_agent_run_id", name="uq_research_plans_run"),
        sa.CheckConstraint(
            "status IN ('VALIDATED','INVALID')",
            name="ck_research_plans_status",
        ),
        sa.CheckConstraint(
            "plan_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_research_plans_checksum",
        ),
    )
    op.create_table(
        "research_steps",
        sa.Column("research_agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("research_plan_id", sa.Uuid(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("step_key", sa.String(64), nullable=False),
        sa.Column("step_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("dependency_keys", JSONB, nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=True),
        sa.Column("tool_version", sa.String(64), nullable=True),
        sa.Column("component_name", sa.String(128), nullable=True),
        sa.Column("input_binding", JSONB, nullable=False),
        sa.Column("fanout_limit", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("skip_reason_code", sa.String(128), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_research_steps"),
        sa.ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_steps_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["research_plan_id"],
            ["research_plans.id"],
            name="fk_research_steps_plan",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "research_plan_id",
            "step_index",
            name="uq_research_steps_plan_index",
        ),
        sa.UniqueConstraint(
            "research_plan_id",
            "step_key",
            name="uq_research_steps_plan_key",
        ),
        sa.CheckConstraint(
            "step_index BETWEEN 0 AND 19 AND fanout_limit BETWEEN 1 AND 5",
            name="ck_research_steps_bounds",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','READY','RUNNING','PASS','PARTIAL','BLOCKED','FAIL','SKIPPED')",
            name="ck_research_steps_status",
        ),
    )
    op.create_index(
        "ix_research_steps_plan_index",
        "research_steps",
        ["research_plan_id", "step_index"],
    )
    op.create_table(
        "research_tool_invocations",
        sa.Column("research_agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("research_step_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("tool_version", sa.String(64), nullable=False),
        sa.Column("permission", sa.String(32), nullable=False),
        sa.Column("redacted_input", JSONB, nullable=False),
        sa.Column("input_checksum", sa.String(64), nullable=False),
        sa.Column("output_checksum", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("safe_error_message", sa.String(256), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_research_tool_invocations"),
        sa.ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_tool_invocations_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["research_step_id"],
            ["research_steps.id"],
            name="fk_research_tool_invocations_step",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "research_step_id",
            "attempt_number",
            name="uq_research_tool_invocations_step_attempt",
        ),
        sa.CheckConstraint(
            "attempt_number BETWEEN 1 AND 2",
            name="ck_research_tool_invocations_attempt",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','PASS','PARTIAL','BLOCKED','FAIL')",
            name="ck_research_tool_invocations_status",
        ),
    )
    op.create_index(
        "ix_research_tool_invocations_run",
        "research_tool_invocations",
        ["research_agent_run_id"],
    )
    op.create_index(
        "ix_research_tool_invocations_step",
        "research_tool_invocations",
        ["research_step_id"],
    )
    op.create_table(
        "research_observations",
        sa.Column("research_agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("invocation_id", sa.Uuid(), nullable=False),
        sa.Column("observation_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("schema_version", sa.String(128), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("output_checksum", sa.String(64), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("research_as_of_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synthetic_status", sa.String(32), nullable=False),
        sa.Column("warnings", JSONB, nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_research_observations"),
        sa.ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_observations_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invocation_id"],
            ["research_tool_invocations.id"],
            name="fk_research_observations_invocation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_research_observations_security",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_research_observations_snapshot",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("invocation_id", name="uq_research_observations_invocation"),
        sa.CheckConstraint(
            "status IN ('PASS','PARTIAL','BLOCKED','FAIL')",
            name="ck_research_observations_status",
        ),
    )
    op.create_index(
        "ix_research_observations_run",
        "research_observations",
        ["research_agent_run_id"],
    )
    op.create_table(
        "research_evidence",
        sa.Column("research_agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("schema_version", sa.String(128), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("research_as_of_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_record_type", sa.String(128), nullable=True),
        sa.Column("source_record_id", sa.Uuid(), nullable=True),
        sa.Column("source_checksum", sa.String(64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("citation_id", sa.Uuid(), nullable=True),
        sa.Column("calculation_run_id", sa.Uuid(), nullable=True),
        sa.Column("calculation_input_ids", JSONB, nullable=False),
        sa.Column("formula_version", sa.String(128), nullable=True),
        sa.Column("synthetic_status", sa.String(32), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("warning_codes", JSONB, nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_research_evidence"),
        sa.ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_evidence_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["research_observations.id"],
            name="fk_research_evidence_observation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_research_evidence_security",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_research_evidence_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["citation_id"],
            ["citation_anchors.id"],
            name="fk_research_evidence_citation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_runs.id"],
            name="fk_research_evidence_calculation_run",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('VALID','INVALID','FUTURE_DATA','SOURCE_MISSING','CONFLICTING','BLOCKED')",
            name="ck_research_evidence_status",
        ),
        sa.CheckConstraint(
            "source_checksum IS NULL OR source_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_research_evidence_checksum",
        ),
    )
    op.create_index(
        "ix_research_evidence_run_type",
        "research_evidence",
        ["research_agent_run_id", "evidence_type"],
    )
    op.create_index(
        "ix_research_evidence_security_snapshot",
        "research_evidence",
        ["security_id", "snapshot_id"],
    )
    op.create_table(
        "research_claims",
        sa.Column("research_agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("claim_key", sa.String(64), nullable=False),
        sa.Column("claim_type", sa.String(64), nullable=False),
        sa.Column("lifecycle_status", sa.String(16), nullable=False),
        sa.Column("support_status", sa.String(32), nullable=True),
        sa.Column("statement_code", sa.String(128), nullable=False),
        sa.Column("value", sa.Numeric(38, 12), nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=True),
        sa.Column("period", sa.String(64), nullable=True),
        sa.Column("as_of_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metric_basis", sa.String(128), nullable=True),
        sa.Column("builder_version", sa.String(128), nullable=False),
        sa.Column("validator_version", sa.String(128), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_research_claims"),
        sa.ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_claims_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "research_agent_run_id",
            "claim_key",
            name="uq_research_claims_run_key",
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('CANDIDATE','VALIDATED','REJECTED')",
            name="ck_research_claims_lifecycle",
        ),
        sa.CheckConstraint(
            "support_status IS NULL OR support_status IN "
            "('SUPPORTED','PARTIALLY_SUPPORTED','CONFLICTING','UNSUPPORTED','BLOCKED')",
            name="ck_research_claims_support",
        ),
    )
    op.create_index(
        "ix_research_claims_run_support",
        "research_claims",
        ["research_agent_run_id", "support_status"],
    )
    op.create_table(
        "claim_evidence_links",
        sa.Column("research_agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_claim_evidence_links"),
        sa.ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_claim_evidence_links_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["research_claims.id"],
            name="fk_claim_evidence_links_claim",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["research_evidence.id"],
            name="fk_claim_evidence_links_evidence",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "claim_id",
            "evidence_id",
            name="uq_claim_evidence_links_pair",
        ),
        sa.CheckConstraint(
            "role IN ('PRIMARY','CORROBORATING','CONTRADICTING','CONTEXT','LIMITATION')",
            name="ck_claim_evidence_links_role",
        ),
    )
    op.create_index(
        "ix_claim_evidence_links_claim",
        "claim_evidence_links",
        ["claim_id"],
    )
    op.create_index(
        "ix_claim_evidence_links_evidence",
        "claim_evidence_links",
        ["evidence_id"],
    )
    op.create_table(
        "research_packages",
        sa.Column("research_agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("research_as_of_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("research_type", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(128), nullable=False),
        sa.Column("planner_version", sa.String(128), nullable=False),
        sa.Column("tool_catalog_version", sa.String(80), nullable=False),
        sa.Column("evidence_version", sa.String(128), nullable=False),
        sa.Column("claim_version", sa.String(128), nullable=False),
        sa.Column("package_version", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("sections", JSONB, nullable=False),
        sa.Column("evidence_ids", JSONB, nullable=False),
        sa.Column("unsupported_claim_ids", JSONB, nullable=False),
        sa.Column("conflicting_claim_ids", JSONB, nullable=False),
        sa.Column("blocked_capabilities", JSONB, nullable=False),
        sa.Column("warnings", JSONB, nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_research_packages"),
        sa.ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_packages_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["research_requests.id"],
            name="fk_research_packages_request",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_research_packages_security",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_research_packages_snapshot",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("research_agent_run_id", name="uq_research_packages_run"),
        sa.CheckConstraint(
            "status IN ('COMPLETE','PARTIAL','BLOCKED','FAILED')",
            name="ck_research_packages_status",
        ),
        sa.CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_research_packages_checksum",
        ),
    )
    op.create_table(
        "research_run_events",
        sa.Column("research_agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=True),
        sa.Column("reason_code", sa.String(128), nullable=True),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("invocation_id", sa.Uuid(), nullable=True),
        sa.Column("safe_message", sa.String(256), nullable=True),
        sa.Column("event_metadata", JSONB, nullable=False),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_research_run_events"),
        sa.ForeignKeyConstraint(
            ["research_agent_run_id"],
            ["research_agent_runs.id"],
            name="fk_research_run_events_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["research_steps.id"],
            name="fk_research_run_events_step",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invocation_id"],
            ["research_tool_invocations.id"],
            name="fk_research_run_events_invocation",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "research_agent_run_id",
            "sequence_number",
            name="uq_research_run_events_sequence",
        ),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_research_run_events_sequence",
        ),
    )
    op.create_index(
        "ix_research_run_events_run_sequence",
        "research_run_events",
        ["research_agent_run_id", "sequence_number"],
    )
    op.create_index(
        "ix_research_run_events_run_created",
        "research_run_events",
        ["research_agent_run_id", "created_at"],
    )


def _create_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION stage7_reject_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'immutable Stage 7 record cannot be modified'
                USING ERRCODE = '23514';
        END;
        $$
        """
    )
    for table_name in (
        "research_policies",
        "research_requests",
        "research_plans",
        "research_observations",
        "research_evidence",
        "claim_evidence_links",
        "research_packages",
        "research_run_events",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION stage7_reject_mutation()
            """
        )
    op.execute(
        """
        CREATE FUNCTION stage7_validate_request_snapshot()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            linked_security_id uuid;
            linked_as_of timestamptz;
            linked_status varchar;
        BEGIN
            SELECT security_id, research_as_of_time, status
              INTO linked_security_id, linked_as_of, linked_status
              FROM data_snapshots WHERE id = NEW.snapshot_id;
            IF linked_security_id IS DISTINCT FROM NEW.security_id
               OR linked_as_of > NEW.research_as_of_time
               OR linked_status <> 'COMPLETE' THEN
                RAISE EXCEPTION 'research request snapshot context does not match'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_requests_validate_snapshot
        BEFORE INSERT ON research_requests
        FOR EACH ROW EXECUTE FUNCTION stage7_validate_request_snapshot()
        """
    )
    op.execute(
        """
        CREATE FUNCTION stage7_validate_run_lineage()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            linked_request research_requests%ROWTYPE;
        BEGIN
            SELECT * INTO linked_request
              FROM research_requests WHERE id = NEW.research_request_id;
            IF linked_request.id IS NULL
               OR linked_request.security_id IS DISTINCT FROM NEW.security_id
               OR linked_request.snapshot_id IS DISTINCT FROM NEW.snapshot_id
               OR linked_request.research_as_of_time IS DISTINCT FROM NEW.research_as_of_time
               OR linked_request.research_type IS DISTINCT FROM NEW.research_type
               OR linked_request.policy_version IS DISTINCT FROM NEW.policy_version
               OR linked_request.planner_version IS DISTINCT FROM NEW.planner_version
               OR linked_request.tool_catalog_version IS DISTINCT FROM NEW.tool_catalog_version
               OR linked_request.tool_catalog_checksum
                  IS DISTINCT FROM NEW.tool_catalog_checksum THEN
                RAISE EXCEPTION 'research run lineage does not match request'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_agent_runs_validate_lineage
        BEFORE INSERT ON research_agent_runs
        FOR EACH ROW EXECUTE FUNCTION stage7_validate_run_lineage()
        """
    )
    op.execute(
        """
        CREATE FUNCTION stage7_guard_run_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'research run cannot be deleted' USING ERRCODE = '23514';
            END IF;
            IF OLD.status IN ('COMPLETED','PARTIAL','BLOCKED','FAILED','CANCELLED') THEN
                RAISE EXCEPTION 'terminal research run is immutable' USING ERRCODE = '23514';
            END IF;
            IF (OLD.research_request_id, OLD.security_id, OLD.snapshot_id,
                OLD.research_as_of_time, OLD.research_type, OLD.policy_version,
                OLD.planner_version, OLD.tool_catalog_version,
                OLD.tool_catalog_checksum, OLD.idempotency_key, OLD.created_at)
               IS DISTINCT FROM
               (NEW.research_request_id, NEW.security_id, NEW.snapshot_id,
                NEW.research_as_of_time, NEW.research_type, NEW.policy_version,
                NEW.planner_version, NEW.tool_catalog_version,
                NEW.tool_catalog_checksum, NEW.idempotency_key, NEW.created_at) THEN
                RAISE EXCEPTION 'research run identity is immutable' USING ERRCODE = '23514';
            END IF;
            IF OLD.status IS DISTINCT FROM NEW.status AND NOT (
                (OLD.status = 'CREATED' AND NEW.status = 'PLANNING') OR
                (OLD.status = 'PLANNING' AND NEW.status IN ('PLANNED','BLOCKED','FAILED')) OR
                (OLD.status = 'PLANNED' AND NEW.status = 'RUNNING') OR
                (OLD.status = 'RUNNING' AND NEW.status IN
                    ('PAUSED','PARTIAL','BLOCKED','COMPLETED','FAILED','CANCELLED')) OR
                (OLD.status = 'PAUSED' AND NEW.status IN ('RUNNING','CANCELLED'))
            ) THEN
                RAISE EXCEPTION 'illegal research run state transition' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_agent_runs_guard_update
        BEFORE UPDATE OR DELETE ON research_agent_runs
        FOR EACH ROW EXECUTE FUNCTION stage7_guard_run_update()
        """
    )
    op.execute(
        """
        CREATE FUNCTION stage7_validate_step_lineage()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE linked_run_id uuid;
        BEGIN
            SELECT research_agent_run_id INTO linked_run_id
              FROM research_plans WHERE id = NEW.research_plan_id;
            IF linked_run_id IS DISTINCT FROM NEW.research_agent_run_id THEN
                RAISE EXCEPTION 'research step must belong to plan run'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_steps_validate_lineage
        BEFORE INSERT ON research_steps
        FOR EACH ROW EXECUTE FUNCTION stage7_validate_step_lineage()
        """
    )
    op.execute(
        """
        CREATE FUNCTION stage7_guard_step_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'research step cannot be deleted' USING ERRCODE = '23514';
            END IF;
            IF OLD.status IN ('PASS','PARTIAL','BLOCKED','FAIL','SKIPPED') THEN
                RAISE EXCEPTION 'terminal research step is immutable' USING ERRCODE = '23514';
            END IF;
            IF (OLD.research_agent_run_id, OLD.research_plan_id, OLD.step_index,
                OLD.step_key, OLD.step_type, OLD.title, OLD.required,
                OLD.dependency_keys, OLD.tool_name, OLD.tool_version,
                OLD.component_name, OLD.input_binding, OLD.fanout_limit, OLD.created_at)
               IS DISTINCT FROM
               (NEW.research_agent_run_id, NEW.research_plan_id, NEW.step_index,
                NEW.step_key, NEW.step_type, NEW.title, NEW.required,
                NEW.dependency_keys, NEW.tool_name, NEW.tool_version,
                NEW.component_name, NEW.input_binding, NEW.fanout_limit, NEW.created_at) THEN
                RAISE EXCEPTION 'research step identity is immutable' USING ERRCODE = '23514';
            END IF;
            IF OLD.status IS DISTINCT FROM NEW.status AND NOT (
                (OLD.status = 'PENDING' AND NEW.status IN ('READY','BLOCKED','SKIPPED')) OR
                (OLD.status = 'READY' AND NEW.status IN ('RUNNING','BLOCKED','SKIPPED')) OR
                (OLD.status = 'RUNNING' AND NEW.status IN
                    ('PASS','PARTIAL','BLOCKED','FAIL'))
            ) THEN
                RAISE EXCEPTION 'illegal research step state transition' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_steps_guard_update
        BEFORE UPDATE OR DELETE ON research_steps
        FOR EACH ROW EXECUTE FUNCTION stage7_guard_step_update()
        """
    )
    op.execute(
        """
        CREATE FUNCTION stage7_validate_invocation_lineage()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE linked_run_id uuid;
        BEGIN
            SELECT research_agent_run_id INTO linked_run_id
              FROM research_steps WHERE id = NEW.research_step_id;
            IF linked_run_id IS DISTINCT FROM NEW.research_agent_run_id THEN
                RAISE EXCEPTION 'tool invocation must belong to step run'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_tool_invocations_validate_lineage
        BEFORE INSERT ON research_tool_invocations
        FOR EACH ROW EXECUTE FUNCTION stage7_validate_invocation_lineage()
        """
    )
    op.execute(
        """
        CREATE FUNCTION stage7_guard_invocation_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'tool invocation cannot be deleted' USING ERRCODE = '23514';
            END IF;
            IF OLD.status IN ('PASS','PARTIAL','BLOCKED','FAIL') THEN
                RAISE EXCEPTION 'terminal tool invocation is immutable' USING ERRCODE = '23514';
            END IF;
            IF (OLD.research_agent_run_id, OLD.research_step_id, OLD.attempt_number,
                OLD.tool_name, OLD.tool_version, OLD.permission, OLD.redacted_input,
                OLD.input_checksum, OLD.started_at, OLD.created_at)
               IS DISTINCT FROM
               (NEW.research_agent_run_id, NEW.research_step_id, NEW.attempt_number,
                NEW.tool_name, NEW.tool_version, NEW.permission, NEW.redacted_input,
                NEW.input_checksum, NEW.started_at, NEW.created_at) THEN
                RAISE EXCEPTION 'tool invocation identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            IF OLD.status IS DISTINCT FROM NEW.status AND NOT (
                (OLD.status = 'PENDING' AND NEW.status IN
                    ('RUNNING','PASS','PARTIAL','BLOCKED','FAIL')) OR
                (OLD.status = 'RUNNING' AND NEW.status IN
                    ('PASS','PARTIAL','BLOCKED','FAIL'))
            ) THEN
                RAISE EXCEPTION 'illegal tool invocation state transition'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_tool_invocations_guard_update
        BEFORE UPDATE OR DELETE ON research_tool_invocations
        FOR EACH ROW EXECUTE FUNCTION stage7_guard_invocation_update()
        """
    )
    op.execute(
        """
        CREATE FUNCTION stage7_guard_claim_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'research claim cannot be deleted' USING ERRCODE = '23514';
            END IF;
            IF OLD.lifecycle_status IN ('VALIDATED','REJECTED') THEN
                RAISE EXCEPTION 'terminal research claim is immutable' USING ERRCODE = '23514';
            END IF;
            IF (OLD.research_agent_run_id, OLD.claim_key, OLD.claim_type,
                OLD.statement_code, OLD.value, OLD.unit, OLD.currency_code,
                OLD.period, OLD.as_of_time, OLD.metric_basis, OLD.builder_version,
                OLD.created_at)
               IS DISTINCT FROM
               (NEW.research_agent_run_id, NEW.claim_key, NEW.claim_type,
                NEW.statement_code, NEW.value, NEW.unit, NEW.currency_code,
                NEW.period, NEW.as_of_time, NEW.metric_basis, NEW.builder_version,
                NEW.created_at) THEN
                RAISE EXCEPTION 'research claim identity is immutable' USING ERRCODE = '23514';
            END IF;
            IF OLD.lifecycle_status IS DISTINCT FROM NEW.lifecycle_status
               AND NOT (
                   OLD.lifecycle_status = 'CANDIDATE'
                   AND NEW.lifecycle_status IN ('VALIDATED','REJECTED')
               ) THEN
                RAISE EXCEPTION 'illegal research claim state transition'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_claims_guard_update
        BEFORE UPDATE OR DELETE ON research_claims
        FOR EACH ROW EXECUTE FUNCTION stage7_guard_claim_update()
        """
    )
    op.execute(
        """
        CREATE FUNCTION stage7_validate_link_lineage()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE claim_run_id uuid; evidence_run_id uuid;
        BEGIN
            SELECT research_agent_run_id INTO claim_run_id
              FROM research_claims WHERE id = NEW.claim_id;
            SELECT research_agent_run_id INTO evidence_run_id
              FROM research_evidence WHERE id = NEW.evidence_id;
            IF claim_run_id IS DISTINCT FROM NEW.research_agent_run_id
               OR evidence_run_id IS DISTINCT FROM NEW.research_agent_run_id THEN
                RAISE EXCEPTION 'claim evidence link must stay within one run'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_claim_evidence_links_validate_lineage
        BEFORE INSERT ON claim_evidence_links
        FOR EACH ROW EXECUTE FUNCTION stage7_validate_link_lineage()
        """
    )
    op.execute(
        """
        CREATE FUNCTION stage7_validate_package_lineage()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE linked_run research_agent_runs%ROWTYPE;
        BEGIN
            SELECT * INTO linked_run
              FROM research_agent_runs WHERE id = NEW.research_agent_run_id;
            IF linked_run.id IS NULL
               OR linked_run.research_request_id IS DISTINCT FROM NEW.request_id
               OR linked_run.security_id IS DISTINCT FROM NEW.security_id
               OR linked_run.snapshot_id IS DISTINCT FROM NEW.snapshot_id
               OR linked_run.research_as_of_time IS DISTINCT FROM NEW.research_as_of_time
               OR linked_run.research_type IS DISTINCT FROM NEW.research_type
               OR linked_run.policy_version IS DISTINCT FROM NEW.policy_version
               OR linked_run.planner_version IS DISTINCT FROM NEW.planner_version
               OR linked_run.tool_catalog_version IS DISTINCT FROM NEW.tool_catalog_version THEN
                RAISE EXCEPTION 'research package lineage does not match run'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_packages_validate_lineage
        BEFORE INSERT ON research_packages
        FOR EACH ROW EXECUTE FUNCTION stage7_validate_package_lineage()
        """
    )
    op.execute(
        """
        CREATE FUNCTION stage7_validate_event_lineage()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE linked_run_id uuid;
        BEGIN
            IF NEW.step_id IS NOT NULL THEN
                SELECT research_agent_run_id INTO linked_run_id
                  FROM research_steps WHERE id = NEW.step_id;
                IF linked_run_id IS DISTINCT FROM NEW.research_agent_run_id THEN
                    RAISE EXCEPTION 'event step must belong to run' USING ERRCODE = '23514';
                END IF;
            END IF;
            IF NEW.invocation_id IS NOT NULL THEN
                SELECT research_agent_run_id INTO linked_run_id
                  FROM research_tool_invocations WHERE id = NEW.invocation_id;
                IF linked_run_id IS DISTINCT FROM NEW.research_agent_run_id THEN
                    RAISE EXCEPTION 'event invocation must belong to run'
                        USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_run_events_validate_lineage
        BEFORE INSERT ON research_run_events
        FOR EACH ROW EXECUTE FUNCTION stage7_validate_event_lineage()
        """
    )


def _drop_guards() -> None:
    for table_name, trigger_name in (
        ("research_run_events", "trg_research_run_events_validate_lineage"),
        ("research_packages", "trg_research_packages_validate_lineage"),
        ("claim_evidence_links", "trg_claim_evidence_links_validate_lineage"),
        ("research_claims", "trg_research_claims_guard_update"),
        (
            "research_tool_invocations",
            "trg_research_tool_invocations_guard_update",
        ),
        (
            "research_tool_invocations",
            "trg_research_tool_invocations_validate_lineage",
        ),
        ("research_steps", "trg_research_steps_guard_update"),
        ("research_steps", "trg_research_steps_validate_lineage"),
        ("research_agent_runs", "trg_research_agent_runs_guard_update"),
        ("research_agent_runs", "trg_research_agent_runs_validate_lineage"),
        ("research_requests", "trg_research_requests_validate_snapshot"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}")
    for table_name in (
        "research_policies",
        "research_requests",
        "research_plans",
        "research_observations",
        "research_evidence",
        "claim_evidence_links",
        "research_packages",
        "research_run_events",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable ON {table_name}")
    for function_name in (
        "stage7_validate_event_lineage",
        "stage7_validate_package_lineage",
        "stage7_validate_link_lineage",
        "stage7_guard_claim_update",
        "stage7_guard_invocation_update",
        "stage7_validate_invocation_lineage",
        "stage7_guard_step_update",
        "stage7_validate_step_lineage",
        "stage7_guard_run_update",
        "stage7_validate_run_lineage",
        "stage7_validate_request_snapshot",
        "stage7_reject_mutation",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {function_name}()")


def upgrade() -> None:
    _create_tables()
    _create_guards()


def downgrade() -> None:
    _drop_guards()
    for table_name in (
        "research_run_events",
        "research_packages",
        "claim_evidence_links",
        "research_claims",
        "research_evidence",
        "research_observations",
        "research_tool_invocations",
        "research_steps",
        "research_plans",
        "research_agent_runs",
        "research_requests",
        "research_policies",
    ):
        op.drop_table(table_name)
