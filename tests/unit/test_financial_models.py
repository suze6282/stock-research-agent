from __future__ import annotations

from sqlalchemy import Float, Numeric, UniqueConstraint

from stock_research_agent.db.base import Base
from stock_research_agent.db.models.financials import (
    CalculationInput,
    CalculationRun,
    CanonicalFinancialConcept,
    DerivedMetric,
    FinancialPeriod,
    FormulaDefinition,
    NormalizedFactInput,
    NormalizedFinancialFact,
    ProviderFactMapping,
)

STAGE_5_TABLES = {
    "canonical_financial_concepts",
    "provider_fact_mappings",
    "financial_periods",
    "normalized_financial_facts",
    "normalized_fact_inputs",
    "formula_definitions",
    "calculation_runs",
    "calculation_inputs",
    "derived_metrics",
}


def test_stage5_models_register_exact_expected_tables() -> None:
    models = (
        CanonicalFinancialConcept,
        ProviderFactMapping,
        FinancialPeriod,
        NormalizedFinancialFact,
        NormalizedFactInput,
        FormulaDefinition,
        CalculationRun,
        CalculationInput,
        DerivedMetric,
    )

    assert {model.__tablename__ for model in models} == STAGE_5_TABLES
    assert STAGE_5_TABLES <= set(Base.metadata.tables)


def test_stage5_models_use_numeric_not_float_for_every_value() -> None:
    numeric_columns = {
        ("normalized_financial_facts", "original_value"),
        ("normalized_financial_facts", "normalized_value"),
        ("normalized_financial_facts", "scale_factor"),
        ("calculation_inputs", "value_used"),
        ("derived_metrics", "value"),
    }

    for table_name in STAGE_5_TABLES:
        table = Base.metadata.tables[table_name]
        assert not any(isinstance(column.type, Float) for column in table.columns)
    for table_name, column_name in numeric_columns:
        assert isinstance(Base.metadata.tables[table_name].c[column_name].type, Numeric)


def test_stage5_foreign_keys_all_restrict_deletion() -> None:
    for table_name in STAGE_5_TABLES:
        for foreign_key in Base.metadata.tables[table_name].foreign_keys:
            assert foreign_key.ondelete == "RESTRICT"


def test_model_constraints_capture_idempotency_and_lineage_contracts() -> None:
    concept_constraints = {
        constraint.name
        for constraint in Base.metadata.tables["canonical_financial_concepts"].constraints
    }
    normalized_constraints = {
        constraint.name
        for constraint in Base.metadata.tables["normalized_financial_facts"].constraints
    }
    run_constraints = {
        constraint.name for constraint in Base.metadata.tables["calculation_runs"].constraints
    }
    input_constraints = {
        constraint.name for constraint in Base.metadata.tables["calculation_inputs"].constraints
    }

    assert "uq_canonical_financial_concepts_code" in concept_constraints
    assert "uq_normalized_facts_source_mapping_version" in normalized_constraints
    assert "uq_calculation_runs_idempotency" in run_constraints
    assert "ck_calculation_inputs_lineage_shape" in input_constraints


def test_reported_and_deaccumulated_rows_have_distinct_idempotency_keys() -> None:
    period_constraint = next(
        constraint
        for constraint in Base.metadata.tables["financial_periods"].constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_financial_periods_snapshot_identity"
    )
    fact_constraint = next(
        constraint
        for constraint in Base.metadata.tables["normalized_financial_facts"].constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_normalized_facts_source_mapping_version"
    )

    assert {column.name for column in period_constraint.columns} >= {
        "is_cumulative",
        "is_single_quarter",
    }
    assert "is_derived_from_cumulative" in {column.name for column in fact_constraint.columns}


def test_query_indexes_are_present_for_real_stage5_paths() -> None:
    expected = {
        "provider_fact_mappings": {
            "ix_provider_fact_mappings_exact_lookup",
        },
        "financial_periods": {
            "ix_financial_periods_security_snapshot_end",
        },
        "normalized_financial_facts": {
            "ix_normalized_facts_snapshot_concept_period",
        },
        "calculation_runs": {
            "ix_calculation_runs_security_snapshot",
        },
        "derived_metrics": {
            "ix_derived_metrics_snapshot_code_period",
        },
    }

    for table_name, names in expected.items():
        actual = {index.name for index in Base.metadata.tables[table_name].indexes}
        assert names <= actual
