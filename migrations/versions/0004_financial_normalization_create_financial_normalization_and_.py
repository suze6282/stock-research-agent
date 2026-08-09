"""create financial normalization and metrics

Revision ID: 0004_financial_normalization
Revises: 0003_data_access_snapshots
Create Date: 2026-07-18 16:36:26.395131
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_financial_normalization"
down_revision: str | Sequence[str] | None = "0003_data_access_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_immutability_guards() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_calculation_run_immutability()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'RUNNING' THEN
                    RAISE EXCEPTION 'calculation run must start in RUNNING state'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;
            IF TG_OP = 'DELETE' THEN
                IF OLD.status <> 'RUNNING' THEN
                    RAISE EXCEPTION 'terminal calculation run is immutable'
                        USING ERRCODE = '23514';
                END IF;
                RETURN OLD;
            END IF;
            IF OLD.status <> 'RUNNING' THEN
                RAISE EXCEPTION 'terminal calculation run is immutable'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.security_id <> OLD.security_id
               OR NEW.snapshot_id <> OLD.snapshot_id
               OR NEW.calculation_version <> OLD.calculation_version
               OR NEW.formula_set_version <> OLD.formula_set_version
               OR NEW.mapping_version <> OLD.mapping_version
               OR NEW.normalization_version <> OLD.normalization_version
               OR NEW.input_checksum <> OLD.input_checksum THEN
                RAISE EXCEPTION 'calculation run identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_calculation_child_immutability()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            parent_run_id uuid;
            parent_status text;
        BEGIN
            parent_run_id := CASE WHEN TG_OP = 'DELETE'
                                  THEN OLD.calculation_run_id
                                  ELSE NEW.calculation_run_id END;
            SELECT status INTO parent_status
              FROM calculation_runs
             WHERE id = parent_run_id;
            IF parent_status IS NULL THEN
                RAISE EXCEPTION 'calculation run lineage is missing'
                    USING ERRCODE = '23503';
            END IF;
            IF parent_status <> 'RUNNING' THEN
                RAISE EXCEPTION 'terminal calculation run children are immutable'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' AND NEW.calculation_run_id <> OLD.calculation_run_id THEN
                RAISE EXCEPTION 'calculation child run identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_financial_version_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'versioned financial row is immutable'
                USING ERRCODE = '23514';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_calculation_runs_immutable
        BEFORE INSERT OR UPDATE OR DELETE ON calculation_runs
        FOR EACH ROW EXECUTE FUNCTION enforce_calculation_run_immutability()
        """
    )
    for table_name in ("calculation_inputs", "derived_metrics"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_terminal_guard
            BEFORE INSERT OR UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION enforce_calculation_child_immutability()
            """
        )
    for table_name in (
        "canonical_financial_concepts",
        "provider_fact_mappings",
        "financial_periods",
        "normalized_financial_facts",
        "normalized_fact_inputs",
        "formula_definitions",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_version_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION prevent_financial_version_mutation()
            """
        )


def _drop_immutability_guards() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_calculation_runs_immutable ON calculation_runs")
    for table_name in ("calculation_inputs", "derived_metrics"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_terminal_guard ON {table_name}")
    for table_name in (
        "canonical_financial_concepts",
        "provider_fact_mappings",
        "financial_periods",
        "normalized_financial_facts",
        "normalized_fact_inputs",
        "formula_definitions",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_version_immutable ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS enforce_calculation_child_immutability()")
    op.execute("DROP FUNCTION IF EXISTS enforce_calculation_run_immutability()")
    op.execute("DROP FUNCTION IF EXISTS prevent_financial_version_mutation()")


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "canonical_financial_concepts",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("statement_type", sa.String(length=32), nullable=False),
        sa.Column("fact_nature", sa.String(length=32), nullable=False),
        sa.Column("default_unit_type", sa.String(length=32), nullable=False),
        sa.Column("supports_duration", sa.Boolean(), nullable=False),
        sa.Column("supports_instant", sa.Boolean(), nullable=False),
        sa.Column("supports_cumulative", sa.Boolean(), nullable=False),
        sa.Column("supports_ttm", sa.Boolean(), nullable=False),
        sa.Column("allows_negative", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "code ~ '^[A-Z][A-Z0-9_]{1,63}$'", name="ck_canonical_financial_concepts_code"
        ),
        sa.CheckConstraint(
            "default_unit_type IN ('MONETARY_AMOUNT', 'PER_SHARE', 'SHARES', 'RATIO')",
            name="ck_canonical_financial_concepts_unit_type",
        ),
        sa.CheckConstraint(
            "fact_nature IN ('DURATION', 'INSTANT', 'PER_SHARE', 'SHARES', 'RATIO_INPUT')",
            name="ck_canonical_financial_concepts_fact_nature",
        ),
        sa.CheckConstraint(
            "statement_type IN ('INCOME_STATEMENT', 'BALANCE_SHEET', 'CASH_FLOW', 'SHARES')",
            name="ck_canonical_financial_concepts_statement_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DEPRECATED')", name="ck_canonical_financial_concepts_status"
        ),
        sa.CheckConstraint(
            "version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name="ck_canonical_financial_concepts_version"
        ),
        sa.CheckConstraint(
            "length(description) BETWEEN 1 AND 2048",
            name="ck_canonical_financial_concepts_description_length",
        ),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 128", name="ck_canonical_financial_concepts_name_length"
        ),
        sa.CheckConstraint(
            "supports_duration OR supports_instant",
            name="ck_canonical_financial_concepts_period_support",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_canonical_financial_concepts"),
        sa.UniqueConstraint("code", name="uq_canonical_financial_concepts_code"),
    )
    op.create_table(
        "formula_definitions",
        sa.Column("metric_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("formula_expression", sa.Text(), nullable=False),
        sa.Column("formula_version", sa.String(length=32), nullable=False),
        sa.Column("required_concepts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("optional_concepts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("period_requirement", sa.String(length=64), nullable=False),
        sa.Column("currency_requirement", sa.String(length=64), nullable=False),
        sa.Column("denominator_policy", sa.String(length=64), nullable=False),
        sa.Column("negative_value_policy", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "formula_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name="ck_formula_definitions_version"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(required_concepts) = 'array' "
            "AND jsonb_typeof(optional_concepts) = 'array'",
            name="ck_formula_definitions_concept_arrays",
        ),
        sa.CheckConstraint(
            "metric_code ~ '^[a-z][a-z0-9_]{1,63}$'", name="ck_formula_definitions_metric_code"
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DEPRECATED')", name="ck_formula_definitions_status"
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_formula_definitions_validity",
        ),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 128 AND length(formula_expression) BETWEEN 1 AND 2048",
            name="ck_formula_definitions_text_length",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_formula_definitions"),
        sa.UniqueConstraint(
            "metric_code", "formula_version", name="uq_formula_definitions_metric_version"
        ),
    )
    op.create_table(
        "provider_fact_mappings",
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("provider_concept", sa.String(length=512), nullable=False),
        sa.Column("taxonomy", sa.String(length=256), nullable=True),
        sa.Column("reported_label_pattern", sa.String(length=512), nullable=True),
        sa.Column("statement_type", sa.String(length=32), nullable=False),
        sa.Column("form_type", sa.String(length=64), nullable=True),
        sa.Column("context_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dimension_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("canonical_concept_id", sa.Uuid(), nullable=True),
        sa.Column("mapping_status", sa.String(length=16), nullable=False),
        sa.Column("mapping_version", sa.String(length=32), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "jsonb_typeof(context_rules) = 'array' AND jsonb_typeof(dimension_rules) = 'array'",
            name="ck_provider_fact_mappings_rule_arrays",
        ),
        sa.CheckConstraint(
            "mapping_status != 'APPROVED' OR "
            "(canonical_concept_id IS NOT NULL "
            "AND length(source_reference) BETWEEN 1 AND 2048 "
            "AND length(reviewed_by) BETWEEN 1 AND 128)",
            name="ck_provider_fact_mappings_approved_evidence",
        ),
        sa.CheckConstraint(
            "mapping_status IN ('APPROVED', 'AMBIGUOUS', 'UNMAPPED', 'DEPRECATED')",
            name="ck_provider_fact_mappings_status",
        ),
        sa.CheckConstraint(
            "mapping_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'",
            name="ck_provider_fact_mappings_version",
        ),
        sa.CheckConstraint(
            "statement_type IN ('INCOME_STATEMENT', 'BALANCE_SHEET', 'CASH_FLOW', 'SHARES')",
            name="ck_provider_fact_mappings_statement_type",
        ),
        sa.CheckConstraint(
            "length(provider_concept) BETWEEN 1 AND 512",
            name="ck_provider_fact_mappings_provider_concept_length",
        ),
        sa.CheckConstraint(
            "taxonomy IS NULL OR length(taxonomy) BETWEEN 1 AND 256",
            name="ck_provider_fact_mappings_taxonomy_length",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_provider_fact_mappings_validity",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_concept_id"],
            ["canonical_financial_concepts.id"],
            name="fk_provider_fact_mappings_concept_id_canonical_concepts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_provider_fact_mappings_provider_id_data_providers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_provider_fact_mappings"),
        sa.UniqueConstraint(
            "provider_id",
            "provider_concept",
            "taxonomy",
            "statement_type",
            "form_type",
            "mapping_version",
            name="uq_provider_fact_mappings_versioned_rule",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_provider_fact_mappings_concept_id",
        "provider_fact_mappings",
        ["canonical_concept_id"],
        unique=False,
    )
    op.create_index(
        "ix_provider_fact_mappings_exact_lookup",
        "provider_fact_mappings",
        [
            "provider_id",
            "provider_concept",
            "taxonomy",
            "statement_type",
            "form_type",
            "mapping_status",
        ],
        unique=False,
    )
    op.create_table(
        "calculation_runs",
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("calculation_version", sa.String(length=32), nullable=False),
        sa.Column("formula_set_version", sa.String(length=32), nullable=False),
        sa.Column("mapping_version", sa.String(length=32), nullable=False),
        sa.Column("normalization_version", sa.String(length=32), nullable=False),
        sa.Column("input_checksum", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("safe_error_message", sa.String(length=512), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'RUNNING' AND completed_at IS NULL) OR "
            "(status != 'RUNNING' AND completed_at IS NOT NULL)",
            name="ck_calculation_runs_lifecycle",
        ),
        sa.CheckConstraint(
            "calculation_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$' "
            "AND formula_set_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$' "
            "AND mapping_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$' "
            "AND normalization_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'",
            name="ck_calculation_runs_versions",
        ),
        sa.CheckConstraint(
            "input_checksum ~ '^[0-9a-f]{64}$'", name="ck_calculation_runs_checksum"
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'PASS', 'PARTIAL', 'BLOCKED', 'FAIL')",
            name="ck_calculation_runs_status",
        ),
        sa.CheckConstraint(
            "started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at",
            name="ck_calculation_runs_timestamp_order",
        ),
        sa.CheckConstraint("warning_count >= 0", name="ck_calculation_runs_warning_count"),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_calculation_runs_security_id_securities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_calculation_runs_snapshot_id_data_snapshots",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_calculation_runs"),
        sa.UniqueConstraint(
            "snapshot_id",
            "calculation_version",
            "formula_set_version",
            "mapping_version",
            "normalization_version",
            "input_checksum",
            name="uq_calculation_runs_idempotency",
        ),
    )
    op.create_index(
        "ix_calculation_runs_security_snapshot",
        "calculation_runs",
        ["security_id", "snapshot_id"],
        unique=False,
    )
    op.create_table(
        "financial_periods",
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_quarter", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(length=32), nullable=False),
        sa.Column("period_type", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("is_annual", sa.Boolean(), nullable=False),
        sa.Column("is_cumulative", sa.Boolean(), nullable=False),
        sa.Column("is_single_quarter", sa.Boolean(), nullable=False),
        sa.Column("is_ttm", sa.Boolean(), nullable=False),
        sa.Column("accounting_standard", sa.String(length=64), nullable=False),
        sa.Column("source_form_type", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(is_annual = (period_type = 'ANNUAL')) AND (is_ttm = (period_type = 'TTM'))",
            name="ck_financial_periods_flags",
        ),
        sa.CheckConstraint(
            "(period_type = 'INSTANT' AND period_start IS NULL "
            "AND duration_days IS NULL AND NOT is_cumulative "
            "AND NOT is_single_quarter AND NOT is_ttm) OR "
            "(period_type != 'INSTANT' AND period_start IS NOT NULL "
            "AND period_end >= period_start AND duration_days > 0)",
            name="ck_financial_periods_shape",
        ),
        sa.CheckConstraint(
            "period_type IN ('ANNUAL', 'QUARTER', 'HALF_YEAR', "
            "'NINE_MONTH_YTD', 'YEAR_TO_DATE', 'TTM', 'INSTANT')",
            name="ck_financial_periods_period_type",
        ),
        sa.CheckConstraint(
            "fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4",
            name="ck_financial_periods_fiscal_quarter",
        ),
        sa.CheckConstraint(
            "fiscal_year BETWEEN 1900 AND 9999", name="ck_financial_periods_fiscal_year"
        ),
        sa.CheckConstraint(
            "length(accounting_standard) BETWEEN 1 AND 64 "
            "AND length(source_form_type) BETWEEN 1 AND 64",
            name="ck_financial_periods_source_vocabulary",
        ),
        sa.CheckConstraint(
            "length(fiscal_period) BETWEEN 1 AND 32",
            name="ck_financial_periods_fiscal_period_length",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_financial_periods_security_id_securities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_financial_periods_snapshot_id_data_snapshots",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_financial_periods"),
        sa.UniqueConstraint(
            "security_id",
            "snapshot_id",
            "fiscal_year",
            "fiscal_quarter",
            "fiscal_period",
            "period_type",
            "period_start",
            "period_end",
            "is_cumulative",
            "is_single_quarter",
            "accounting_standard",
            "source_form_type",
            name="uq_financial_periods_snapshot_identity",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_financial_periods_security_snapshot_end",
        "financial_periods",
        ["security_id", "snapshot_id", "period_end"],
        unique=False,
    )
    op.create_table(
        "derived_metrics",
        sa.Column("calculation_run_id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("formula_definition_id", sa.Uuid(), nullable=False),
        sa.Column("metric_code", sa.String(length=64), nullable=False),
        sa.Column("metric_period", sa.String(length=32), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("value", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("value_state", sa.String(length=32), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("quality_status", sa.String(length=16), nullable=False),
        sa.Column("formula_version", sa.String(length=32), nullable=False),
        sa.Column("warning_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(value_state = 'VALUE' AND value IS NOT NULL AND value != 0) OR "
            "(value_state = 'ZERO' AND value = 0) OR "
            "(value_state IN ('NULL', 'NOT_MEANINGFUL') AND value IS NULL)",
            name="ck_derived_metrics_value_state",
        ),
        sa.CheckConstraint(
            "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'",
            name="ck_derived_metrics_currency_code",
        ),
        sa.CheckConstraint(
            "formula_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'",
            name="ck_derived_metrics_formula_version",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(warning_codes) = 'array'", name="ck_derived_metrics_warning_codes"
        ),
        sa.CheckConstraint(
            "metric_code ~ '^[a-z][a-z0-9_]{1,63}$' AND length(metric_period) BETWEEN 1 AND 32",
            name="ck_derived_metrics_vocabulary",
        ),
        sa.CheckConstraint(
            "quality_status IN ('PASS', 'PARTIAL', 'BLOCKED', 'FAIL')",
            name="ck_derived_metrics_quality_status",
        ),
        sa.CheckConstraint(
            "value IS NULL OR value != 'NaN'::numeric", name="ck_derived_metrics_value_finite"
        ),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_runs.id"],
            name="fk_derived_metrics_run_id_calculation_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["formula_definition_id"],
            ["formula_definitions.id"],
            name="fk_derived_metrics_formula_id_formula_definitions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_derived_metrics_security_id_securities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_derived_metrics_snapshot_id_data_snapshots",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_derived_metrics"),
        sa.UniqueConstraint(
            "calculation_run_id",
            "metric_code",
            "metric_period",
            "period_end",
            name="uq_derived_metrics_run_metric_period",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_derived_metrics_run_id", "derived_metrics", ["calculation_run_id"], unique=False
    )
    op.create_index(
        "ix_derived_metrics_snapshot_code_period",
        "derived_metrics",
        ["snapshot_id", "metric_code", "period_end"],
        unique=False,
    )
    op.create_table(
        "normalized_financial_facts",
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("financial_period_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_concept_id", sa.Uuid(), nullable=False),
        sa.Column("source_financial_fact_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_id", sa.Uuid(), nullable=False),
        sa.Column("original_value", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("normalized_value", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("original_unit", sa.String(length=64), nullable=False),
        sa.Column("normalized_unit", sa.String(length=64), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("scale_factor", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("fact_nature", sa.String(length=32), nullable=False),
        sa.Column("is_reported", sa.Boolean(), nullable=False),
        sa.Column("is_derived_from_cumulative", sa.Boolean(), nullable=False),
        sa.Column("is_restated", sa.Boolean(), nullable=False),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mapping_version", sa.String(length=32), nullable=False),
        sa.Column("normalization_version", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'",
            name="ck_normalized_facts_currency_code",
        ),
        sa.CheckConstraint(
            "fact_nature IN ('DURATION', 'INSTANT', 'PER_SHARE', 'SHARES', 'RATIO_INPUT')",
            name="ck_normalized_facts_fact_nature",
        ),
        sa.CheckConstraint(
            "mapping_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$' "
            "AND normalization_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'",
            name="ck_normalized_facts_versions",
        ),
        sa.CheckConstraint(
            "original_value != 'NaN'::numeric "
            "AND normalized_value != 'NaN'::numeric "
            "AND scale_factor != 'NaN'::numeric AND scale_factor > 0",
            name="ck_normalized_facts_finite_values",
        ),
        sa.CheckConstraint(
            "length(original_unit) BETWEEN 1 AND 64 AND length(normalized_unit) BETWEEN 1 AND 64",
            name="ck_normalized_facts_unit_length",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_concept_id"],
            ["canonical_financial_concepts.id"],
            name="fk_normalized_facts_concept_id_canonical_concepts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["financial_period_id"],
            ["financial_periods.id"],
            name="fk_normalized_facts_period_id_financial_periods",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mapping_id"],
            ["provider_fact_mappings.id"],
            name="fk_normalized_facts_mapping_id_provider_fact_mappings",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_normalized_facts_security_id_securities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_normalized_facts_snapshot_id_data_snapshots",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_financial_fact_id"],
            ["provider_financial_facts.id"],
            name="fk_normalized_facts_source_id_provider_financial_facts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_normalized_financial_facts"),
        sa.UniqueConstraint(
            "snapshot_id",
            "source_financial_fact_id",
            "mapping_version",
            "normalization_version",
            "is_derived_from_cumulative",
            name="uq_normalized_facts_source_mapping_version",
        ),
    )
    op.create_index(
        "ix_normalized_facts_snapshot_concept_period",
        "normalized_financial_facts",
        ["snapshot_id", "canonical_concept_id", "financial_period_id"],
        unique=False,
    )
    op.create_index(
        "ix_normalized_facts_source_id",
        "normalized_financial_facts",
        ["source_financial_fact_id"],
        unique=False,
    )
    op.create_table(
        "calculation_inputs",
        sa.Column("calculation_run_id", sa.Uuid(), nullable=False),
        sa.Column("metric_code", sa.String(length=64), nullable=False),
        sa.Column("normalized_fact_id", sa.Uuid(), nullable=True),
        sa.Column("source_record_type", sa.String(length=64), nullable=True),
        sa.Column("source_record_id", sa.Uuid(), nullable=True),
        sa.Column("input_role", sa.String(length=64), nullable=False),
        sa.Column("value_used", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'",
            name="ck_calculation_inputs_currency_code",
        ),
        sa.CheckConstraint(
            "metric_code ~ '^[a-z][a-z0-9_]{1,63}$' AND length(input_role) BETWEEN 1 AND 64",
            name="ck_calculation_inputs_vocabulary",
        ),
        sa.CheckConstraint(
            "value_used != 'NaN'::numeric", name="ck_calculation_inputs_value_finite"
        ),
        sa.CheckConstraint(
            "(normalized_fact_id IS NOT NULL AND source_record_type IS NULL "
            "AND source_record_id IS NULL) OR "
            "(normalized_fact_id IS NULL AND source_record_type IS NOT NULL "
            "AND source_record_id IS NOT NULL)",
            name="ck_calculation_inputs_lineage_shape",
        ),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_runs.id"],
            name="fk_calculation_inputs_run_id_calculation_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["normalized_fact_id"],
            ["normalized_financial_facts.id"],
            name="fk_calculation_inputs_fact_id_normalized_facts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_calculation_inputs"),
        sa.UniqueConstraint(
            "calculation_run_id",
            "metric_code",
            "input_role",
            "normalized_fact_id",
            "source_record_type",
            "source_record_id",
            name="uq_calculation_inputs_lineage",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_calculation_inputs_run_metric",
        "calculation_inputs",
        ["calculation_run_id", "metric_code"],
        unique=False,
    )
    op.create_table(
        "normalized_fact_inputs",
        sa.Column("normalized_fact_id", sa.Uuid(), nullable=False),
        sa.Column("input_normalized_fact_id", sa.Uuid(), nullable=False),
        sa.Column("input_role", sa.String(length=64), nullable=False),
        sa.Column("input_ordinal", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(input_role) BETWEEN 1 AND 64 AND input_ordinal >= 0",
            name="ck_normalized_fact_inputs_role",
        ),
        sa.CheckConstraint(
            "normalized_fact_id != input_normalized_fact_id",
            name="ck_normalized_fact_inputs_no_self_reference",
        ),
        sa.ForeignKeyConstraint(
            ["input_normalized_fact_id"],
            ["normalized_financial_facts.id"],
            name="fk_normalized_fact_inputs_input_id_normalized_facts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["normalized_fact_id"],
            ["normalized_financial_facts.id"],
            name="fk_normalized_fact_inputs_fact_id_normalized_facts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_normalized_fact_inputs"),
        sa.UniqueConstraint(
            "normalized_fact_id",
            "input_role",
            "input_normalized_fact_id",
            name="uq_normalized_fact_inputs_lineage",
        ),
    )
    op.create_index(
        "ix_normalized_fact_inputs_fact_id",
        "normalized_fact_inputs",
        ["normalized_fact_id", "input_ordinal"],
        unique=False,
    )
    _create_immutability_guards()
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    _drop_immutability_guards()
    op.drop_index("ix_normalized_fact_inputs_fact_id", table_name="normalized_fact_inputs")
    op.drop_table("normalized_fact_inputs")
    op.drop_index("ix_calculation_inputs_run_metric", table_name="calculation_inputs")
    op.drop_table("calculation_inputs")
    op.drop_index("ix_normalized_facts_source_id", table_name="normalized_financial_facts")
    op.drop_index(
        "ix_normalized_facts_snapshot_concept_period", table_name="normalized_financial_facts"
    )
    op.drop_table("normalized_financial_facts")
    op.drop_index("ix_derived_metrics_snapshot_code_period", table_name="derived_metrics")
    op.drop_index("ix_derived_metrics_run_id", table_name="derived_metrics")
    op.drop_table("derived_metrics")
    op.drop_index("ix_financial_periods_security_snapshot_end", table_name="financial_periods")
    op.drop_table("financial_periods")
    op.drop_index("ix_calculation_runs_security_snapshot", table_name="calculation_runs")
    op.drop_table("calculation_runs")
    op.drop_index("ix_provider_fact_mappings_exact_lookup", table_name="provider_fact_mappings")
    op.drop_index("ix_provider_fact_mappings_concept_id", table_name="provider_fact_mappings")
    op.drop_table("provider_fact_mappings")
    op.drop_table("formula_definitions")
    op.drop_table("canonical_financial_concepts")
    # ### end Alembic commands ###
