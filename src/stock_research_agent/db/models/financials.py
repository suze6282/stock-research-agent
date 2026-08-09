"""SQLAlchemy models for normalized facts and deterministic calculations."""

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
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_research_agent.db.base import Base


class _CreatedUuidMixin:
    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class _TimestampedUuidMixin(_CreatedUuidMixin):
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class CanonicalFinancialConcept(_TimestampedUuidMixin, Base):
    __tablename__ = "canonical_financial_concepts"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_canonical_financial_concepts"),
        UniqueConstraint("code", name="uq_canonical_financial_concepts_code"),
        CheckConstraint(
            "code ~ '^[A-Z][A-Z0-9_]{1,63}$'",
            name="ck_canonical_financial_concepts_code",
        ),
        CheckConstraint(
            "length(name) BETWEEN 1 AND 128",
            name="ck_canonical_financial_concepts_name_length",
        ),
        CheckConstraint(
            "statement_type IN ('INCOME_STATEMENT', 'BALANCE_SHEET', 'CASH_FLOW', 'SHARES')",
            name="ck_canonical_financial_concepts_statement_type",
        ),
        CheckConstraint(
            "fact_nature IN ('DURATION', 'INSTANT', 'PER_SHARE', 'SHARES', 'RATIO_INPUT')",
            name="ck_canonical_financial_concepts_fact_nature",
        ),
        CheckConstraint(
            "default_unit_type IN ('MONETARY_AMOUNT', 'PER_SHARE', 'SHARES', 'RATIO')",
            name="ck_canonical_financial_concepts_unit_type",
        ),
        CheckConstraint(
            "supports_duration OR supports_instant",
            name="ck_canonical_financial_concepts_period_support",
        ),
        CheckConstraint(
            "length(description) BETWEEN 1 AND 2048",
            name="ck_canonical_financial_concepts_description_length",
        ),
        CheckConstraint(
            "version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'",
            name="ck_canonical_financial_concepts_version",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'DEPRECATED')",
            name="ck_canonical_financial_concepts_status",
        ),
    )

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    statement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    fact_nature: Mapped[str] = mapped_column(String(32), nullable=False)
    default_unit_type: Mapped[str] = mapped_column(String(32), nullable=False)
    supports_duration: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supports_instant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supports_cumulative: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supports_ttm: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allows_negative: Mapped[bool] = mapped_column(Boolean, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)


class ProviderFactMapping(_TimestampedUuidMixin, Base):
    __tablename__ = "provider_fact_mappings"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_fact_mappings"),
        ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_provider_fact_mappings_provider_id_data_providers",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["canonical_concept_id"],
            ["canonical_financial_concepts.id"],
            name="fk_provider_fact_mappings_concept_id_canonical_concepts",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider_id",
            "provider_concept",
            "taxonomy",
            "statement_type",
            "form_type",
            "mapping_version",
            name="uq_provider_fact_mappings_versioned_rule",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "length(provider_concept) BETWEEN 1 AND 512",
            name="ck_provider_fact_mappings_provider_concept_length",
        ),
        CheckConstraint(
            "taxonomy IS NULL OR length(taxonomy) BETWEEN 1 AND 256",
            name="ck_provider_fact_mappings_taxonomy_length",
        ),
        CheckConstraint(
            "statement_type IN ('INCOME_STATEMENT', 'BALANCE_SHEET', 'CASH_FLOW', 'SHARES')",
            name="ck_provider_fact_mappings_statement_type",
        ),
        CheckConstraint(
            "jsonb_typeof(context_rules) = 'array' AND jsonb_typeof(dimension_rules) = 'array'",
            name="ck_provider_fact_mappings_rule_arrays",
        ),
        CheckConstraint(
            "mapping_status IN ('APPROVED', 'AMBIGUOUS', 'UNMAPPED', 'DEPRECATED')",
            name="ck_provider_fact_mappings_status",
        ),
        CheckConstraint(
            "mapping_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'",
            name="ck_provider_fact_mappings_version",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_provider_fact_mappings_validity",
        ),
        CheckConstraint(
            "mapping_status != 'APPROVED' OR "
            "(canonical_concept_id IS NOT NULL AND length(source_reference) BETWEEN 1 AND 2048 "
            "AND length(reviewed_by) BETWEEN 1 AND 128)",
            name="ck_provider_fact_mappings_approved_evidence",
        ),
        Index(
            "ix_provider_fact_mappings_exact_lookup",
            "provider_id",
            "provider_concept",
            "taxonomy",
            "statement_type",
            "form_type",
            "mapping_status",
        ),
        Index("ix_provider_fact_mappings_concept_id", "canonical_concept_id"),
    )

    provider_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_concept: Mapped[str] = mapped_column(String(512), nullable=False)
    taxonomy: Mapped[str | None] = mapped_column(String(256))
    reported_label_pattern: Mapped[str | None] = mapped_column(String(512))
    statement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    form_type: Mapped[str | None] = mapped_column(String(64))
    context_rules: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    dimension_rules: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    canonical_concept_id: Mapped[UUID | None] = mapped_column(Uuid)
    mapping_status: Mapped[str] = mapped_column(String(16), nullable=False)
    mapping_version: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source_reference: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(128))


class FinancialPeriod(_CreatedUuidMixin, Base):
    __tablename__ = "financial_periods"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_financial_periods"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_financial_periods_security_id_securities",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_financial_periods_snapshot_id_data_snapshots",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
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
        CheckConstraint(
            "fiscal_year BETWEEN 1900 AND 9999",
            name="ck_financial_periods_fiscal_year",
        ),
        CheckConstraint(
            "fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4",
            name="ck_financial_periods_fiscal_quarter",
        ),
        CheckConstraint(
            "length(fiscal_period) BETWEEN 1 AND 32",
            name="ck_financial_periods_fiscal_period_length",
        ),
        CheckConstraint(
            "period_type IN ('ANNUAL', 'QUARTER', 'HALF_YEAR', 'NINE_MONTH_YTD', "
            "'YEAR_TO_DATE', 'TTM', 'INSTANT')",
            name="ck_financial_periods_period_type",
        ),
        CheckConstraint(
            "(period_type = 'INSTANT' AND period_start IS NULL AND duration_days IS NULL "
            "AND NOT is_cumulative AND NOT is_single_quarter AND NOT is_ttm) OR "
            "(period_type != 'INSTANT' AND period_start IS NOT NULL AND period_end >= period_start "
            "AND duration_days > 0)",
            name="ck_financial_periods_shape",
        ),
        CheckConstraint(
            "(is_annual = (period_type = 'ANNUAL')) AND (is_ttm = (period_type = 'TTM'))",
            name="ck_financial_periods_flags",
        ),
        CheckConstraint(
            "length(accounting_standard) BETWEEN 1 AND 64 "
            "AND length(source_form_type) BETWEEN 1 AND 64",
            name="ck_financial_periods_source_vocabulary",
        ),
        Index(
            "ix_financial_periods_security_snapshot_end",
            "security_id",
            "snapshot_id",
            "period_end",
        ),
    )

    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer)
    fiscal_period: Mapped[str] = mapped_column(String(32), nullable=False)
    period_type: Mapped[str] = mapped_column(String(32), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime | None] = mapped_column()
    duration_days: Mapped[int | None] = mapped_column(Integer)
    is_annual: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_cumulative: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_single_quarter: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_ttm: Mapped[bool] = mapped_column(Boolean, nullable=False)
    accounting_standard: Mapped[str] = mapped_column(String(64), nullable=False)
    source_form_type: Mapped[str] = mapped_column(String(64), nullable=False)


class NormalizedFinancialFact(_CreatedUuidMixin, Base):
    __tablename__ = "normalized_financial_facts"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_normalized_financial_facts"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_normalized_facts_security_id_securities",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_normalized_facts_snapshot_id_data_snapshots",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["financial_period_id"],
            ["financial_periods.id"],
            name="fk_normalized_facts_period_id_financial_periods",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["canonical_concept_id"],
            ["canonical_financial_concepts.id"],
            name="fk_normalized_facts_concept_id_canonical_concepts",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_financial_fact_id"],
            ["provider_financial_facts.id"],
            name="fk_normalized_facts_source_id_provider_financial_facts",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["mapping_id"],
            ["provider_fact_mappings.id"],
            name="fk_normalized_facts_mapping_id_provider_fact_mappings",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "snapshot_id",
            "source_financial_fact_id",
            "mapping_version",
            "normalization_version",
            "is_derived_from_cumulative",
            name="uq_normalized_facts_source_mapping_version",
        ),
        CheckConstraint(
            "original_value != 'NaN'::numeric AND normalized_value != 'NaN'::numeric "
            "AND scale_factor != 'NaN'::numeric AND scale_factor > 0",
            name="ck_normalized_facts_finite_values",
        ),
        CheckConstraint(
            "length(original_unit) BETWEEN 1 AND 64 AND length(normalized_unit) BETWEEN 1 AND 64",
            name="ck_normalized_facts_unit_length",
        ),
        CheckConstraint(
            "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'",
            name="ck_normalized_facts_currency_code",
        ),
        CheckConstraint(
            "fact_nature IN ('DURATION', 'INSTANT', 'PER_SHARE', 'SHARES', 'RATIO_INPUT')",
            name="ck_normalized_facts_fact_nature",
        ),
        CheckConstraint(
            "mapping_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$' "
            "AND normalization_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'",
            name="ck_normalized_facts_versions",
        ),
        Index(
            "ix_normalized_facts_snapshot_concept_period",
            "snapshot_id",
            "canonical_concept_id",
            "financial_period_id",
        ),
        Index("ix_normalized_facts_source_id", "source_financial_fact_id"),
    )

    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    financial_period_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    canonical_concept_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_financial_fact_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    mapping_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    original_value: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    normalized_value: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    original_unit: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_unit: Mapped[str] = mapped_column(String(64), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    scale_factor: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    fact_nature: Mapped[str] = mapped_column(String(32), nullable=False)
    is_reported: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_derived_from_cumulative: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_restated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column()
    mapping_version: Mapped[str] = mapped_column(String(32), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(32), nullable=False)


class NormalizedFactInput(_CreatedUuidMixin, Base):
    __tablename__ = "normalized_fact_inputs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_normalized_fact_inputs"),
        ForeignKeyConstraint(
            ["normalized_fact_id"],
            ["normalized_financial_facts.id"],
            name="fk_normalized_fact_inputs_fact_id_normalized_facts",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["input_normalized_fact_id"],
            ["normalized_financial_facts.id"],
            name="fk_normalized_fact_inputs_input_id_normalized_facts",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "normalized_fact_id",
            "input_role",
            "input_normalized_fact_id",
            name="uq_normalized_fact_inputs_lineage",
        ),
        CheckConstraint(
            "normalized_fact_id != input_normalized_fact_id",
            name="ck_normalized_fact_inputs_no_self_reference",
        ),
        CheckConstraint(
            "length(input_role) BETWEEN 1 AND 64 AND input_ordinal >= 0",
            name="ck_normalized_fact_inputs_role",
        ),
        Index("ix_normalized_fact_inputs_fact_id", "normalized_fact_id", "input_ordinal"),
    )

    normalized_fact_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    input_normalized_fact_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    input_role: Mapped[str] = mapped_column(String(64), nullable=False)
    input_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class FormulaDefinition(_TimestampedUuidMixin, Base):
    __tablename__ = "formula_definitions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_formula_definitions"),
        UniqueConstraint(
            "metric_code",
            "formula_version",
            name="uq_formula_definitions_metric_version",
        ),
        CheckConstraint(
            "metric_code ~ '^[a-z][a-z0-9_]{1,63}$'",
            name="ck_formula_definitions_metric_code",
        ),
        CheckConstraint(
            "length(name) BETWEEN 1 AND 128 AND length(formula_expression) BETWEEN 1 AND 2048",
            name="ck_formula_definitions_text_length",
        ),
        CheckConstraint(
            "formula_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'",
            name="ck_formula_definitions_version",
        ),
        CheckConstraint(
            "jsonb_typeof(required_concepts) = 'array' "
            "AND jsonb_typeof(optional_concepts) = 'array'",
            name="ck_formula_definitions_concept_arrays",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'DEPRECATED')",
            name="ck_formula_definitions_status",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_formula_definitions_validity",
        ),
    )

    metric_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    formula_expression: Mapped[str] = mapped_column(Text, nullable=False)
    formula_version: Mapped[str] = mapped_column(String(32), nullable=False)
    required_concepts: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    optional_concepts: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    period_requirement: Mapped[str] = mapped_column(String(64), nullable=False)
    currency_requirement: Mapped[str] = mapped_column(String(64), nullable=False)
    denominator_policy: Mapped[str] = mapped_column(String(64), nullable=False)
    negative_value_policy: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)


class CalculationRun(_CreatedUuidMixin, Base):
    __tablename__ = "calculation_runs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_calculation_runs"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_calculation_runs_security_id_securities",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_calculation_runs_snapshot_id_data_snapshots",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "snapshot_id",
            "calculation_version",
            "formula_set_version",
            "mapping_version",
            "normalization_version",
            "input_checksum",
            name="uq_calculation_runs_idempotency",
        ),
        CheckConstraint(
            "status IN ('RUNNING', 'PASS', 'PARTIAL', 'BLOCKED', 'FAIL')",
            name="ck_calculation_runs_status",
        ),
        CheckConstraint(
            "calculation_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$' "
            "AND formula_set_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$' "
            "AND mapping_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$' "
            "AND normalization_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'",
            name="ck_calculation_runs_versions",
        ),
        CheckConstraint(
            "input_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_calculation_runs_checksum",
        ),
        CheckConstraint(
            "(status = 'RUNNING' AND completed_at IS NULL) OR "
            "(status != 'RUNNING' AND completed_at IS NOT NULL)",
            name="ck_calculation_runs_lifecycle",
        ),
        CheckConstraint(
            "started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at",
            name="ck_calculation_runs_timestamp_order",
        ),
        CheckConstraint(
            "warning_count >= 0",
            name="ck_calculation_runs_warning_count",
        ),
        Index("ix_calculation_runs_security_snapshot", "security_id", "snapshot_id"),
    )

    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(32), nullable=False)
    formula_set_version: Mapped[str] = mapped_column(String(32), nullable=False)
    mapping_version: Mapped[str] = mapped_column(String(32), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(String(512))


class CalculationInput(_CreatedUuidMixin, Base):
    __tablename__ = "calculation_inputs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_calculation_inputs"),
        ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_runs.id"],
            name="fk_calculation_inputs_run_id_calculation_runs",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["normalized_fact_id"],
            ["normalized_financial_facts.id"],
            name="fk_calculation_inputs_fact_id_normalized_facts",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "calculation_run_id",
            "metric_code",
            "input_role",
            "normalized_fact_id",
            "source_record_type",
            "source_record_id",
            name="uq_calculation_inputs_lineage",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "(normalized_fact_id IS NOT NULL AND source_record_type IS NULL "
            "AND source_record_id IS NULL) OR "
            "(normalized_fact_id IS NULL AND source_record_type IS NOT NULL "
            "AND source_record_id IS NOT NULL)",
            name="ck_calculation_inputs_lineage_shape",
        ),
        CheckConstraint(
            "metric_code ~ '^[a-z][a-z0-9_]{1,63}$' AND length(input_role) BETWEEN 1 AND 64",
            name="ck_calculation_inputs_vocabulary",
        ),
        CheckConstraint(
            "value_used != 'NaN'::numeric",
            name="ck_calculation_inputs_value_finite",
        ),
        CheckConstraint(
            "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'",
            name="ck_calculation_inputs_currency_code",
        ),
        Index("ix_calculation_inputs_run_metric", "calculation_run_id", "metric_code"),
    )

    calculation_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    metric_code: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_fact_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_record_type: Mapped[str | None] = mapped_column(String(64))
    source_record_id: Mapped[UUID | None] = mapped_column(Uuid)
    input_role: Mapped[str] = mapped_column(String(64), nullable=False)
    value_used: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))


class DerivedMetric(_CreatedUuidMixin, Base):
    __tablename__ = "derived_metrics"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_derived_metrics"),
        ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_runs.id"],
            name="fk_derived_metrics_run_id_calculation_runs",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_derived_metrics_security_id_securities",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_derived_metrics_snapshot_id_data_snapshots",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["formula_definition_id"],
            ["formula_definitions.id"],
            name="fk_derived_metrics_formula_id_formula_definitions",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "calculation_run_id",
            "metric_code",
            "metric_period",
            "period_end",
            name="uq_derived_metrics_run_metric_period",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "metric_code ~ '^[a-z][a-z0-9_]{1,63}$' AND length(metric_period) BETWEEN 1 AND 32",
            name="ck_derived_metrics_vocabulary",
        ),
        CheckConstraint(
            "(value_state = 'VALUE' AND value IS NOT NULL AND value != 0) OR "
            "(value_state = 'ZERO' AND value = 0) OR "
            "(value_state IN ('NULL', 'NOT_MEANINGFUL') AND value IS NULL)",
            name="ck_derived_metrics_value_state",
        ),
        CheckConstraint(
            "value IS NULL OR value != 'NaN'::numeric",
            name="ck_derived_metrics_value_finite",
        ),
        CheckConstraint(
            "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'",
            name="ck_derived_metrics_currency_code",
        ),
        CheckConstraint(
            "quality_status IN ('PASS', 'PARTIAL', 'BLOCKED', 'FAIL')",
            name="ck_derived_metrics_quality_status",
        ),
        CheckConstraint(
            "formula_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'",
            name="ck_derived_metrics_formula_version",
        ),
        CheckConstraint(
            "jsonb_typeof(warning_codes) = 'array'",
            name="ck_derived_metrics_warning_codes",
        ),
        Index(
            "ix_derived_metrics_snapshot_code_period",
            "snapshot_id",
            "metric_code",
            "period_end",
        ),
        Index("ix_derived_metrics_run_id", "calculation_run_id"),
    )

    calculation_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    formula_definition_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    metric_code: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_period: Mapped[str] = mapped_column(String(32), nullable=False)
    period_end: Mapped[date | None] = mapped_column(Date)
    value: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    value_state: Mapped[str] = mapped_column(String(32), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    quality_status: Mapped[str] = mapped_column(String(16), nullable=False)
    formula_version: Mapped[str] = mapped_column(String(32), nullable=False)
    warning_codes: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
