from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, Engine, Float, Numeric, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import DatabaseError

from stock_research_agent.db.base import Base
from stock_research_agent.db.models.financials import (  # noqa: F401
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
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
STAGE_4_TABLES = {
    "data_providers",
    "provider_instrument_mappings",
    "ingestion_runs",
    "provider_request_logs",
    "raw_payloads",
    "daily_price_bars",
    "corporate_actions",
    "provider_financial_facts",
    "source_documents",
    "data_snapshots",
    "snapshot_items",
}
DROP_ORDER = (
    *STAGE_5_TABLES,
    "snapshot_items",
    "data_snapshots",
    "provider_financial_facts",
    "source_documents",
    "corporate_actions",
    "daily_price_bars",
    "raw_payloads",
    "provider_request_logs",
    "ingestion_runs",
    "provider_instrument_mappings",
    "data_providers",
    "security_aliases",
    "security_identifiers",
    "securities",
    "issuer_identifiers",
    "issuers",
    "exchange_aliases",
    "exchanges",
    "markets",
    "schema_meta",
    "alembic_version",
)


def _integration_was_selected() -> bool:
    arguments = [value.replace("\\", "/").lower() for value in sys.argv[1:]]
    return any("tests/integration" in value for value in arguments) or "integration" in arguments


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Stage 5 migration tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


def _config(*, stdout: StringIO | None = None) -> Config:
    return Config(
        str(PROJECT_ROOT / "alembic.ini"),
        stdout=stdout or sys.stdout,
        output_buffer=stdout,
    )


def _reset(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))


@pytest.fixture
def migration_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    _reset(engine)
    try:
        yield engine
    finally:
        _reset(engine)
        command.upgrade(_config(), "head")
        engine.dispose()


def test_stage5_upgrade_downgrade_upgrade_preserves_stage4(migration_engine: Engine) -> None:
    config = _config()
    command.upgrade(config, "0003_data_access_snapshots")
    assert STAGE_4_TABLES <= set(inspect(migration_engine).get_table_names())
    assert not (STAGE_5_TABLES & set(inspect(migration_engine).get_table_names()))

    command.upgrade(config, "0004_financial_normalization")
    assert STAGE_5_TABLES <= set(inspect(migration_engine).get_table_names())

    command.downgrade(config, "-1")
    after_downgrade = set(inspect(migration_engine).get_table_names())
    assert STAGE_4_TABLES <= after_downgrade
    assert not (STAGE_5_TABLES & after_downgrade)

    command.upgrade(config, "head")
    assert STAGE_5_TABLES <= set(inspect(migration_engine).get_table_names())


def test_stage5_catalog_matches_model_shape(migration_engine: Engine) -> None:
    command.upgrade(_config(), "head")
    inspector = inspect(migration_engine)

    for table_name in STAGE_5_TABLES:
        model_table = Base.metadata.tables[table_name]
        assert inspector.get_pk_constraint(table_name)["name"] == f"pk_{table_name}"
        actual_columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        assert set(actual_columns) == set(model_table.columns.keys())
        assert not any(isinstance(column["type"], Float) for column in actual_columns.values())
        for column_name, model_column in model_table.columns.items():
            assert actual_columns[column_name]["nullable"] is model_column.nullable
        for timestamp_name in (
            "created_at",
            "updated_at",
            "published_at",
            "source_published_at",
            "started_at",
            "completed_at",
        ):
            if timestamp_name in actual_columns:
                assert isinstance(actual_columns[timestamp_name]["type"], DateTime)
                assert actual_columns[timestamp_name]["type"].timezone is True

    assert isinstance(
        next(
            column["type"]
            for column in inspector.get_columns("normalized_financial_facts")
            if column["name"] == "normalized_value"
        ),
        Numeric,
    )
    assert isinstance(
        next(
            column["type"]
            for column in inspector.get_columns("derived_metrics")
            if column["name"] == "warning_codes"
        ),
        JSONB,
    )


def test_stage5_catalog_has_named_constraints_and_query_indexes(migration_engine: Engine) -> None:
    command.upgrade(_config(), "head")
    inspector = inspect(migration_engine)

    normalized_unique = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("normalized_financial_facts")
    }
    run_unique = {
        constraint["name"] for constraint in inspector.get_unique_constraints("calculation_runs")
    }
    input_checks = {
        constraint["name"] for constraint in inspector.get_check_constraints("calculation_inputs")
    }
    indexes = {
        table: {index["name"] for index in inspector.get_indexes(table)}
        for table in (
            "provider_fact_mappings",
            "financial_periods",
            "normalized_financial_facts",
            "calculation_runs",
            "derived_metrics",
        )
    }

    assert "uq_normalized_facts_source_mapping_version" in normalized_unique
    assert "uq_calculation_runs_idempotency" in run_unique
    assert "ck_calculation_inputs_lineage_shape" in input_checks
    assert "ix_provider_fact_mappings_exact_lookup" in indexes["provider_fact_mappings"]
    assert "ix_financial_periods_security_snapshot_end" in indexes["financial_periods"]
    assert "ix_normalized_facts_snapshot_concept_period" in indexes["normalized_financial_facts"]
    assert "ix_calculation_runs_security_snapshot" in indexes["calculation_runs"]
    assert "ix_derived_metrics_snapshot_code_period" in indexes["derived_metrics"]


def test_stage5_migration_inserts_no_business_rows(migration_engine: Engine) -> None:
    command.upgrade(_config(), "head")
    with migration_engine.connect() as connection:
        for table_name in STAGE_5_TABLES:
            assert connection.scalar(text(f'SELECT count(*) FROM "{table_name}"')) == 0

    output = StringIO()
    command.upgrade(_config(stdout=output), "head", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE canonical_financial_concepts" in sql
    assert "CREATE TABLE derived_metrics" in sql
    assert "INSERT INTO canonical_financial_concepts" not in sql
    assert "601138" not in sql
    assert "Micron" not in sql


def _seed_terminal_calculation_run(engine: Engine) -> dict[str, UUID]:
    ids = {
        "market": uuid4(),
        "exchange": uuid4(),
        "issuer": uuid4(),
        "security": uuid4(),
        "snapshot": uuid4(),
        "formula": uuid4(),
        "run": uuid4(),
        "input": uuid4(),
        "metric": uuid4(),
    }
    instant = datetime(2026, 7, 18, 8, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO markets "
                "(id, code, name, country_code, default_currency_code, status) "
                "VALUES (:id, 'US_EQUITY', 'US Equity', 'US', 'USD', 'ACTIVE')"
            ),
            {"id": ids["market"]},
        )
        connection.execute(
            text(
                "INSERT INTO exchanges "
                "(id, market_id, mic, name, short_name, country_code, timezone, "
                "default_currency_code, status) VALUES "
                "(:id, :market, 'XNAS', 'Nasdaq', 'Nasdaq', 'US', "
                "'America/New_York', 'USD', 'ACTIVE')"
            ),
            {"id": ids["exchange"], "market": ids["market"]},
        )
        connection.execute(
            text(
                "INSERT INTO issuers "
                "(id, legal_name, normalized_legal_name, display_name, "
                "normalized_display_name, country_code, issuer_status) VALUES "
                "(:id, 'One Inc.', 'ONE INC', 'One', 'ONE', 'US', 'ACTIVE')"
            ),
            {"id": ids["issuer"]},
        )
        connection.execute(
            text(
                "INSERT INTO securities "
                "(id, issuer_id, exchange_id, symbol, normalized_symbol, display_name, "
                "security_type, currency_code, listing_status) VALUES "
                "(:id, :issuer, :exchange, 'ONE', 'ONE', 'One', "
                "'COMMON_STOCK', 'USD', 'ACTIVE')"
            ),
            {
                "id": ids["security"],
                "issuer": ids["issuer"],
                "exchange": ids["exchange"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO data_snapshots "
                "(id, security_id, research_as_of_time, snapshot_version, status, "
                "formula_version) VALUES "
                "(:id, :security, :instant, 1, 'BUILDING', 'raw-data-v1')"
            ),
            {
                "id": ids["snapshot"],
                "security": ids["security"],
                "instant": instant,
                "checksum": "a" * 64,
            },
        )
        connection.execute(
            text(
                "UPDATE data_snapshots SET status = 'PARTIAL', completed_at = :instant, "
                "checksum = :checksum WHERE id = :id"
            ),
            {"id": ids["snapshot"], "instant": instant, "checksum": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO formula_definitions "
                "(id, metric_code, name, formula_expression, formula_version, "
                "required_concepts, optional_concepts, period_requirement, "
                "currency_requirement, denominator_policy, negative_value_policy, status) "
                "VALUES (:id, 'revenue_growth', 'Revenue Growth', 'current / prior', "
                "'1.0.0', '[]'::jsonb, '[]'::jsonb, 'COMPARABLE', 'SAME', "
                "'NON_POSITIVE_IS_NM', 'ALLOWED', 'ACTIVE')"
            ),
            {"id": ids["formula"]},
        )
        connection.execute(
            text(
                "INSERT INTO calculation_runs "
                "(id, security_id, snapshot_id, status, calculation_version, "
                "formula_set_version, mapping_version, normalization_version, "
                "input_checksum, started_at, warning_count) VALUES "
                "(:id, :security, :snapshot, 'RUNNING', '1.0.0', '1.0.0', "
                "'1.0.0', '1.0.0', :checksum, :instant, 0)"
            ),
            {
                "id": ids["run"],
                "security": ids["security"],
                "snapshot": ids["snapshot"],
                "checksum": "b" * 64,
                "instant": instant,
            },
        )
        connection.execute(
            text(
                "INSERT INTO calculation_inputs "
                "(id, calculation_run_id, metric_code, source_record_type, source_record_id, "
                "input_role, value_used, unit, currency_code) VALUES "
                "(:id, :run, 'revenue_growth', 'provider_financial_facts', :source, "
                "'current_revenue', :value, 'ONE', 'USD')"
            ),
            {
                "id": ids["input"],
                "run": ids["run"],
                "source": uuid4(),
                "value": Decimal("1"),
            },
        )
        connection.execute(
            text(
                "INSERT INTO derived_metrics "
                "(id, calculation_run_id, security_id, snapshot_id, formula_definition_id, "
                "metric_code, metric_period, value, value_state, unit, quality_status, "
                "formula_version, warning_codes) VALUES "
                "(:id, :run, :security, :snapshot, :formula, 'revenue_growth', 'FY', "
                ":value, 'VALUE', 'RATIO', 'PASS', '1.0.0', '[]'::jsonb)"
            ),
            {
                "id": ids["metric"],
                "run": ids["run"],
                "security": ids["security"],
                "snapshot": ids["snapshot"],
                "formula": ids["formula"],
                "value": Decimal("0.1"),
            },
        )
        connection.execute(
            text(
                "UPDATE calculation_runs SET status = 'PASS', completed_at = :instant "
                "WHERE id = :id"
            ),
            {"id": ids["run"], "instant": instant},
        )
    return ids


def test_terminal_calculation_run_and_children_are_database_immutable(
    migration_engine: Engine,
) -> None:
    command.upgrade(_config(), "head")
    ids = _seed_terminal_calculation_run(migration_engine)

    mutations = (
        ("UPDATE calculation_runs SET warning_count = 1 WHERE id = :id", ids["run"]),
        ("DELETE FROM calculation_runs WHERE id = :id", ids["run"]),
        ("UPDATE calculation_inputs SET value_used = 2 WHERE id = :id", ids["input"]),
        ("DELETE FROM calculation_inputs WHERE id = :id", ids["input"]),
        ("UPDATE derived_metrics SET value = 0.2 WHERE id = :id", ids["metric"]),
        ("DELETE FROM derived_metrics WHERE id = :id", ids["metric"]),
    )
    for statement, record_id in mutations:
        with pytest.raises(DatabaseError, match="immutable"):
            with migration_engine.begin() as connection:
                connection.execute(text(statement), {"id": record_id})

    with pytest.raises(DatabaseError, match="immutable"):
        with migration_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO calculation_inputs "
                    "(id, calculation_run_id, metric_code, source_record_type, source_record_id, "
                    "input_role, value_used, unit, currency_code) VALUES "
                    "(:id, :run, 'revenue_growth', 'provider_financial_facts', :source, "
                    "'prior_revenue', 1, 'ONE', 'USD')"
                ),
                {"id": uuid4(), "run": ids["run"], "source": uuid4()},
            )
