"""create controlled live evidence

Revision ID: 0009_controlled_live_evidence
Revises: 0008_production_providers
Create Date: 2026-08-01 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from stock_research_agent.db.models.live_evidence import STAGE10_MODEL_TABLES

revision: str = "0009_controlled_live_evidence"
down_revision: str | Sequence[str] | None = "0008_production_providers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_ORDER = tuple(STAGE10_MODEL_TABLES)
_APPEND_ONLY_TABLES = (
    "live_authorization_events",
    "manual_evidence_source_declarations",
    "manual_evidence_validations",
    "manual_evidence_reviews",
    "evidence_ingestion_manifests",
    "ingestion_to_snapshot_bindings",
    "end_to_end_research_validations",
    "live_incident_events",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in _TABLE_ORDER:
        STAGE10_MODEL_TABLES[table_name].__table__.create(bind, checkfirst=False)

    op.alter_column("raw_payloads", "provider_request_log_id", nullable=True)
    op.add_column(
        "raw_payloads",
        sa.Column("manual_evidence_import_request_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_raw_payloads_manual_evidence_import_request",
        "raw_payloads",
        "manual_evidence_import_requests",
        ["manual_evidence_import_request_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_raw_payloads_exactly_one_source",
        "raw_payloads",
        "(provider_request_log_id IS NOT NULL)::int + "
        "(manual_evidence_import_request_id IS NOT NULL)::int = 1",
    )

    op.drop_constraint("ck_document_versions_size", "document_versions", type_="check")
    op.create_check_constraint(
        "ck_document_versions_size",
        "document_versions",
        "byte_size BETWEEN 1 AND 26214400",
    )
    op.add_column(
        "provider_live_validation_runs",
        sa.Column("live_authorization_grant_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_provider_live_validation_runs_live_authorization",
        "provider_live_validation_runs",
        "live_authorization_grants",
        ["live_authorization_grant_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.execute(
        """
        CREATE FUNCTION stage10_reject_history_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'STAGE10_HISTORY_IMMUTABLE' USING ERRCODE = '23514';
        END;
        $$;
        """
    )
    for table_name in _APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table_name}_immutable "
            f"BEFORE UPDATE OR DELETE ON {table_name} "
            "FOR EACH ROW EXECUTE FUNCTION stage10_reject_history_mutation()"
        )
    op.execute(
        """
        CREATE FUNCTION stage10_guard_snapshot_binding_insert() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE parent_status text; parent_security_id uuid; parent_as_of timestamptz;
        BEGIN
            SELECT status, security_id, research_as_of_time
              INTO parent_status, parent_security_id, parent_as_of
              FROM data_snapshots WHERE id = NEW.snapshot_id FOR UPDATE;
            IF parent_status IS NULL OR parent_status <> 'BUILDING' THEN
                RAISE EXCEPTION 'SNAPSHOT_BINDING_IMMUTABLE' USING ERRCODE = '23514';
            END IF;
            IF parent_security_id <> NEW.security_id OR parent_as_of <> NEW.research_as_of_time THEN
                RAISE EXCEPTION 'SNAPSHOT_BINDING_SCOPE_MISMATCH' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER trg_ingestion_snapshot_bindings_insert_scope
        BEFORE INSERT ON ingestion_to_snapshot_bindings
        FOR EACH ROW EXECUTE FUNCTION stage10_guard_snapshot_binding_insert();
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.has_table(bind, "ingestion_to_snapshot_bindings"):
        op.execute(
            "DROP TRIGGER IF EXISTS trg_ingestion_snapshot_bindings_insert_scope "
            "ON ingestion_to_snapshot_bindings"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_ingestion_snapshot_bindings_immutable "
            "ON ingestion_to_snapshot_bindings"
        )
    op.execute("DROP FUNCTION IF EXISTS stage10_guard_snapshot_binding_insert()")
    op.execute("DROP FUNCTION IF EXISTS stage10_guard_snapshot_binding()")
    for table_name in reversed(_APPEND_ONLY_TABLES):
        if bind.dialect.has_table(bind, table_name):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS stage10_reject_history_mutation()")

    op.execute(
        "ALTER TABLE provider_live_validation_runs DROP CONSTRAINT IF EXISTS "
        "fk_provider_live_validation_runs_live_authorization"
    )
    op.execute(
        "ALTER TABLE provider_live_validation_runs "
        "DROP COLUMN IF EXISTS live_authorization_grant_id"
    )
    op.drop_constraint("ck_document_versions_size", "document_versions", type_="check")
    op.create_check_constraint(
        "ck_document_versions_size",
        "document_versions",
        "byte_size BETWEEN 1 AND 10000000",
    )
    op.execute(
        "ALTER TABLE raw_payloads DROP CONSTRAINT IF EXISTS ck_raw_payloads_exactly_one_source"
    )
    op.execute(
        "ALTER TABLE raw_payloads DROP CONSTRAINT IF EXISTS "
        "fk_raw_payloads_manual_evidence_import_request"
    )
    op.execute("ALTER TABLE raw_payloads DROP COLUMN IF EXISTS manual_evidence_import_request_id")
    op.alter_column("raw_payloads", "provider_request_log_id", nullable=False)

    for table_name in reversed(_TABLE_ORDER):
        STAGE10_MODEL_TABLES[table_name].__table__.drop(bind, checkfirst=True)
