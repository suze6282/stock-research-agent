from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Engine,
    Float,
    ForeignKeyConstraint,
    Numeric,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.db.base import Base

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
STAGE_3_TABLES = {
    "markets",
    "exchanges",
    "exchange_aliases",
    "issuers",
    "issuer_identifiers",
    "securities",
    "security_identifiers",
    "security_aliases",
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
    "normalized_fact_inputs",
    "calculation_inputs",
    "derived_metrics",
    "calculation_runs",
    "normalized_financial_facts",
    "financial_periods",
    "provider_fact_mappings",
    "formula_definitions",
    "canonical_financial_concepts",
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


def _integration_was_explicitly_selected() -> bool:
    arguments = [argument.replace("\\", "/").lower() for argument in sys.argv[1:]]
    return any("tests/integration" in argument for argument in arguments) or any(
        argument == "integration" and index > 0 and arguments[index - 1] == "-m"
        for index, argument in enumerate(arguments)
    )


if TEST_DATABASE_URL is None and _integration_was_explicitly_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for PostgreSQL integration tests")

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


def _test_engine(database_url: str) -> Engine:
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=database_url,
    )
    assert settings.database_url is not None
    return create_engine(settings.database_url)


def _normalized_predicate(value: object | None) -> str:
    if value is None:
        return ""
    return "".join(character for character in str(value).lower() if character not in " ()\t\r\n")


def _load_stage_4_revision() -> ModuleType:
    path = PROJECT_ROOT / "migrations" / "versions" / "0003_create_data_access_and_snapshots.py"
    spec = importlib.util.spec_from_file_location("stage4_revision_for_parity", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_lineage(engine: Engine) -> dict[str, UUID]:
    command.upgrade(_config(), "head")
    ids = {
        "market": UUID("10000000-0000-0000-0000-000000000001"),
        "exchange": UUID("20000000-0000-0000-0000-000000000001"),
        "issuer_one": UUID("30000000-0000-0000-0000-000000000001"),
        "issuer_two": UUID("30000000-0000-0000-0000-000000000002"),
        "security_one": UUID("40000000-0000-0000-0000-000000000001"),
        "security_two": UUID("40000000-0000-0000-0000-000000000002"),
        "provider": UUID("50000000-0000-0000-0000-000000000001"),
        "run": UUID("60000000-0000-0000-0000-000000000001"),
        "request": UUID("70000000-0000-0000-0000-000000000001"),
        "caller_request": UUID("71000000-0000-0000-0000-000000000001"),
        "payload": UUID("80000000-0000-0000-0000-000000000001"),
    }
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO markets
                    (id, code, name, country_code, default_currency_code, status)
                VALUES (:id, 'US_EQUITY', 'US Equity', 'US', 'USD', 'ACTIVE')
                """
            ),
            {"id": ids["market"]},
        )
        connection.execute(
            text(
                """
                INSERT INTO exchanges
                    (id, market_id, mic, name, short_name, country_code, timezone,
                     default_currency_code, status)
                VALUES (:id, :market, 'XNAS', 'Nasdaq', 'Nasdaq', 'US',
                        'America/New_York', 'USD', 'ACTIVE')
                """
            ),
            {"id": ids["exchange"], "market": ids["market"]},
        )
        connection.execute(
            text(
                """
                INSERT INTO issuers
                    (id, legal_name, normalized_legal_name, display_name,
                     normalized_display_name, country_code, issuer_status)
                VALUES
                    (:one, 'One Inc.', 'ONE INC', 'One', 'ONE', 'US', 'ACTIVE'),
                    (:two, 'Two Inc.', 'TWO INC', 'Two', 'TWO', 'US', 'ACTIVE')
                """
            ),
            {"one": ids["issuer_one"], "two": ids["issuer_two"]},
        )
        connection.execute(
            text(
                """
                INSERT INTO securities
                    (id, issuer_id, exchange_id, symbol, normalized_symbol, display_name,
                     security_type, currency_code, listing_status, is_primary_listing)
                VALUES
                    (:one, :issuer_one, :exchange, 'ONE', 'ONE', 'One',
                     'COMMON_STOCK', 'USD', 'ACTIVE', true),
                    (:two, :issuer_two, :exchange, 'TWO', 'TWO', 'Two',
                     'COMMON_STOCK', 'USD', 'ACTIVE', true)
                """
            ),
            {
                "one": ids["security_one"],
                "two": ids["security_two"],
                "issuer_one": ids["issuer_one"],
                "issuer_two": ids["issuer_two"],
                "exchange": ids["exchange"],
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO data_providers
                    (id, code, name, provider_type, status, terms_status, capabilities)
                VALUES (:id, 'TEST_FIXTURE', 'Test Fixture', 'FIXTURE', 'APPROVED',
                        'VERIFIED', '["DAILY_PRICES"]'::jsonb)
                """
            ),
            {"id": ids["provider"]},
        )
        instant = datetime(2026, 7, 10, 20, tzinfo=UTC)
        connection.execute(
            text(
                """
                INSERT INTO ingestion_runs
                    (id, provider_id, security_id, category, status, research_as_of_time,
                     idempotency_key, requested_at, started_at, completed_at, request_count,
                     records_received, records_stored, warning_count)
                VALUES (:id, :provider, :security, 'DAILY_PRICES', 'PASS', :instant,
                        'test:lineage:one', :instant, :instant, :instant, 1, 1, 1, 0)
                """
            ),
            {
                "id": ids["run"],
                "provider": ids["provider"],
                "security": ids["security_one"],
                "instant": instant,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO provider_request_logs
                    (id, ingestion_run_id, provider_id, caller_request_id,
                     provider_request_id, endpoint_name, method, safe_url,
                     request_started_at, response_received_at, http_status, attempt,
                     cache_status, response_size)
                VALUES (:id, :run, :provider, :caller_request, 'fixture-request:one',
                        'fixture', 'GET',
                        'https://example.invalid/fixture', :instant, :instant, 200, 1,
                        'NOT_APPLICABLE', 2)
                """
            ),
            {
                "id": ids["request"],
                "run": ids["run"],
                "provider": ids["provider"],
                "caller_request": ids["caller_request"],
                "instant": instant,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO raw_payloads
                    (id, ingestion_run_id, provider_request_log_id, provider_id, security_id,
                     category, content_type, inline_json, checksum_algorithm, checksum,
                     retrieved_at, provider_version, parser_version, schema_version, byte_size)
                VALUES (:id, :run, :request, :provider, :security, 'DAILY_PRICES',
                        'application/json', '{}'::jsonb, 'sha256', :checksum, :instant,
                        '1.0.0', '1.0.0', '1.0.0', 2)
                """
            ),
            {
                "id": ids["payload"],
                "run": ids["run"],
                "request": ids["request"],
                "provider": ids["provider"],
                "security": ids["security_one"],
                "checksum": "a" * 64,
                "instant": instant,
            },
        )
    return ids


@pytest.fixture
def migration_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    engine = _test_engine(TEST_DATABASE_URL)
    monkeypatch.setenv("APP_ENV", AppEnvironment.TEST.value)
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    _reset(engine)
    try:
        yield engine
    finally:
        _reset(engine)
        command.upgrade(_config(), "head")
        engine.dispose()


def test_stage_4_upgrade_downgrade_upgrade_cycle_preserves_stage_3(
    migration_engine: Engine,
) -> None:
    config = _config()
    command.upgrade(config, "0002_create_security_master")
    assert STAGE_3_TABLES <= set(inspect(migration_engine).get_table_names())
    assert not (STAGE_4_TABLES & set(inspect(migration_engine).get_table_names()))

    command.upgrade(config, "0003_data_access_snapshots")
    assert STAGE_4_TABLES <= set(inspect(migration_engine).get_table_names())

    command.downgrade(config, "-1")
    after_downgrade = set(inspect(migration_engine).get_table_names())
    assert STAGE_3_TABLES <= after_downgrade
    assert not (STAGE_4_TABLES & after_downgrade)

    command.upgrade(config, "head")
    assert STAGE_4_TABLES <= set(inspect(migration_engine).get_table_names())


def test_stage_4_catalog_matches_model_metadata(migration_engine: Engine) -> None:
    command.upgrade(_config(), "head")
    inspector = inspect(migration_engine)

    for table_name in STAGE_4_TABLES:
        model_table = Base.metadata.tables[table_name]
        assert inspector.get_pk_constraint(table_name)["name"] == f"pk_{table_name}"

        actual_columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        assert set(actual_columns) == set(model_table.columns.keys())
        for column_name, model_column in model_table.columns.items():
            assert actual_columns[column_name]["nullable"] is model_column.nullable

        expected_checks = {
            constraint.name
            for constraint in model_table.constraints
            if constraint.__class__.__name__ == "CheckConstraint"
        }
        assert {
            constraint["name"] for constraint in inspector.get_check_constraints(table_name)
        } == expected_checks

        expected_uniques = {
            constraint.name: {
                "columns": tuple(column.name for column in constraint.columns),
                "nulls_not_distinct": bool(
                    constraint.dialect_options["postgresql"]["nulls_not_distinct"]
                ),
            }
            for constraint in model_table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert {
            constraint["name"]: {
                "columns": tuple(constraint["column_names"]),
                "nulls_not_distinct": bool(
                    constraint.get("dialect_options", {}).get(
                        "postgresql_nulls_not_distinct", False
                    )
                ),
            }
            for constraint in inspector.get_unique_constraints(table_name)
        } == expected_uniques

        expected_indexes = {
            index.name: {
                "columns": tuple(column.name for column in index.columns),
                "unique": bool(index.unique),
                "predicate": _normalized_predicate(index.dialect_options["postgresql"]["where"]),
                "nulls_not_distinct": bool(
                    index.dialect_options["postgresql"]["nulls_not_distinct"]
                ),
            }
            for index in model_table.indexes
        }
        reflected_indexes = {
            index["name"]: {
                "columns": tuple(index["column_names"]),
                "unique": bool(index["unique"]),
                "predicate": _normalized_predicate(
                    index.get("dialect_options", {}).get("postgresql_where")
                ),
                "nulls_not_distinct": bool(
                    index.get("dialect_options", {}).get("postgresql_nulls_not_distinct", False)
                ),
            }
            for index in inspector.get_indexes(table_name)
            if index["name"] in expected_indexes
        }
        assert reflected_indexes == expected_indexes

        expected_foreign_keys = {}
        for constraint in model_table.constraints:
            if isinstance(constraint, ForeignKeyConstraint):
                element = next(iter(constraint.elements))
                expected_foreign_keys[constraint.name] = {
                    "columns": tuple(column.name for column in constraint.columns),
                    "target_table": element.column.table.name,
                    "target_columns": tuple(item.column.name for item in constraint.elements),
                    "ondelete": constraint.ondelete,
                }
        actual_foreign_keys = {
            foreign_key["name"]: {
                "columns": tuple(foreign_key["constrained_columns"]),
                "target_table": foreign_key["referred_table"],
                "target_columns": tuple(foreign_key["referred_columns"]),
                "ondelete": foreign_key["options"].get("ondelete"),
            }
            for foreign_key in inspector.get_foreign_keys(table_name)
        }
        assert actual_foreign_keys == expected_foreign_keys

        for timestamp_name in (
            "created_at",
            "updated_at",
            "research_as_of_time",
            "requested_at",
            "started_at",
            "completed_at",
            "request_started_at",
            "response_received_at",
            "source_published_at",
            "retrieved_at",
            "market_timestamp",
            "filed_at",
            "published_at",
        ):
            if timestamp_name in actual_columns:
                assert isinstance(actual_columns[timestamp_name]["type"], DateTime)
                assert actual_columns[timestamp_name]["type"].timezone is True

        assert not any(isinstance(column["type"], Float) for column in actual_columns.values())

    for table_name, column_name in (
        ("data_providers", "capabilities"),
        ("provider_instrument_mappings", "metadata"),
        ("raw_payloads", "inline_json"),
        ("provider_financial_facts", "dimensions"),
    ):
        actual_columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        assert isinstance(actual_columns[column_name]["type"], JSONB)
    assert isinstance(
        next(
            column["type"]
            for column in inspector.get_columns("daily_price_bars")
            if column["name"] == "close"
        ),
        Numeric,
    )


def test_ingestion_lineage_and_nullable_adjustment_migration_contract(
    migration_engine: Engine,
) -> None:
    command.upgrade(_config(), "head")
    inspector = inspect(migration_engine)
    request_columns = {
        column["name"]: column for column in inspector.get_columns("provider_request_logs")
    }
    price_columns = {column["name"]: column for column in inspector.get_columns("daily_price_bars")}

    assert request_columns["caller_request_id"]["nullable"] is False
    assert request_columns["provider_request_id"]["nullable"] is True
    assert price_columns["adjustment_type"]["nullable"] is True
    daily_unique = next(
        constraint
        for constraint in inspector.get_unique_constraints("daily_price_bars")
        if constraint["name"] == "uq_daily_price_bars_provider_revision"
    )
    assert daily_unique["dialect_options"]["postgresql_nulls_not_distinct"] is True


def test_migration_check_sql_exactly_matches_orm_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _load_stage_4_revision()
    captured_tables: dict[str, tuple[object, ...]] = {}

    def capture_table(table_name: str, *elements: object, **_kwargs: object) -> None:
        captured_tables[table_name] = elements

    monkeypatch.setattr(revision.op, "create_table", capture_table)
    monkeypatch.setattr(revision.op, "create_index", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(revision.op, "create_foreign_key", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(revision.op, "execute", lambda *_args, **_kwargs: None)
    revision.upgrade()

    assert set(captured_tables) == STAGE_4_TABLES
    for table_name in STAGE_4_TABLES:
        migration_checks = {
            constraint.name: str(constraint.sqltext)
            for constraint in captured_tables[table_name]
            if isinstance(constraint, CheckConstraint)
        }
        model_checks = {
            constraint.name: str(constraint.sqltext)
            for constraint in Base.metadata.tables[table_name].constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert migration_checks == model_checks


def test_stage_4_migration_inserts_no_rows_or_business_data(migration_engine: Engine) -> None:
    command.upgrade(_config(), "head")
    with migration_engine.connect() as connection:
        for table_name in STAGE_4_TABLES:
            assert connection.scalar(text(f'SELECT count(*) FROM "{table_name}"')) == 0

    output = StringIO()
    command.upgrade(_config(stdout=output), "head", sql=True)
    generated_sql = output.getvalue()
    assert "CREATE TABLE data_providers" in generated_sql
    assert "CREATE TABLE data_snapshots" in generated_sql
    assert "INSERT INTO data_providers" not in generated_sql
    assert "INSERT INTO daily_price_bars" not in generated_sql
    assert "601138" not in generated_sql
    assert "NASDAQ:MU" not in generated_sql


def test_blob_storage_uri_accepts_safe_opaque_shape_and_rejects_hostile_shapes(
    migration_engine: Engine,
) -> None:
    ids = _seed_lineage(migration_engine)
    raw_statement = text(
        """
        INSERT INTO raw_payloads
            (id, ingestion_run_id, provider_request_log_id, provider_id, security_id,
             category, content_type, storage_uri, checksum_algorithm, checksum, retrieved_at,
             provider_version, parser_version, schema_version, byte_size)
        VALUES (:id, :run, :request, :provider, :security, 'DAILY_PRICES',
                'application/json', :storage_uri, 'sha256', :checksum, :retrieved_at,
                '1.0.0', '1.0.0', '1.0.0', 2)
        """
    )
    common = {
        "run": ids["run"],
        "request": ids["request"],
        "provider": ids["provider"],
        "security": ids["security_one"],
        "retrieved_at": datetime(2026, 7, 10, 20, tzinfo=UTC),
    }
    safe_raw_id = uuid4()
    with migration_engine.begin() as connection:
        connection.execute(
            raw_statement,
            {
                **common,
                "id": safe_raw_id,
                "storage_uri": "blob://local/abc-123/file.json",
                "checksum": "b" * 64,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO source_documents
                    (id, security_id, provider_id, source_payload_id, document_type, title,
                     source_url, storage_uri, document_status, retrieved_at)
                VALUES (:id, :security, :provider, :payload, 'OTHER', 'Safe document',
                        'https://example.invalid/doc', 'blob://memory/abc_123/file.pdf',
                        'AVAILABLE', :retrieved_at)
                """
            ),
            {
                "id": uuid4(),
                "security": ids["security_one"],
                "provider": ids["provider"],
                "payload": safe_raw_id,
                "retrieved_at": common["retrieved_at"],
            },
        )

    hostile_uris = (
        "blob://local/../secret",
        "blob:///absolute",
        "blob://local//empty",
        "blob://local/./secret",
        "blob://local\\secret",
        "blob://local/key?token=value",
        "blob://local/key#fragment",
        "blob://user@host/key",
        "blob://local/" + "x" * 1012,
    )
    for offset, storage_uri in enumerate(hostile_uris):
        with pytest.raises(IntegrityError):
            with migration_engine.begin() as connection:
                connection.execute(
                    raw_statement,
                    {
                        **common,
                        "id": uuid4(),
                        "storage_uri": storage_uri,
                        "checksum": f"{offset + 1:064x}",
                    },
                )

    document_statement = text(
        """
        INSERT INTO source_documents
            (id, security_id, provider_id, source_payload_id, document_type, title,
             source_url, storage_uri, document_status, retrieved_at)
        VALUES (:id, :security, :provider, :payload, 'OTHER', :title,
                'https://example.invalid/doc', :storage_uri, 'AVAILABLE', :retrieved_at)
        """
    )
    for offset, storage_uri in enumerate(
        ("blob://local/../secret", "blob:///absolute", "blob://local/" + "x" * 1012)
    ):
        with pytest.raises(IntegrityError):
            with migration_engine.begin() as connection:
                connection.execute(
                    document_statement,
                    {
                        "id": uuid4(),
                        "security": ids["security_one"],
                        "provider": ids["provider"],
                        "payload": safe_raw_id,
                        "title": f"Hostile document {offset}",
                        "storage_uri": storage_uri,
                        "retrieved_at": common["retrieved_at"],
                    },
                )


def test_raw_payload_requires_exactly_one_storage_location_and_restricts_lineage_deletes(
    migration_engine: Engine,
) -> None:
    ids = _seed_lineage(migration_engine)
    statement = text(
        """
        INSERT INTO raw_payloads
            (id, ingestion_run_id, provider_request_log_id, provider_id, security_id,
             category, content_type, storage_uri, inline_json, checksum_algorithm, checksum,
             retrieved_at, provider_version, parser_version, schema_version, byte_size)
        VALUES (:id, :run, :request, :provider, :security, 'DAILY_PRICES',
                'application/json', :storage_uri, CAST(:inline_json AS jsonb), 'sha256',
                :checksum, :retrieved_at, '1.0.0', '1.0.0', '1.0.0', 2)
        """
    )
    common = {
        "run": ids["run"],
        "request": ids["request"],
        "provider": ids["provider"],
        "security": ids["security_one"],
        "retrieved_at": datetime(2026, 7, 10, 20, tzinfo=UTC),
    }
    for storage_uri, inline_json in ((None, None), ("blob://local/key", "{}")):
        with pytest.raises(IntegrityError):
            with migration_engine.begin() as connection:
                connection.execute(
                    statement,
                    {
                        **common,
                        "id": uuid4(),
                        "storage_uri": storage_uri,
                        "inline_json": inline_json,
                        "checksum": "c" * 64,
                    },
                )

    for delete_statement, parameters in (
        ("DELETE FROM provider_request_logs WHERE id = :id", {"id": ids["request"]}),
        ("DELETE FROM ingestion_runs WHERE id = :id", {"id": ids["run"]}),
        ("DELETE FROM data_providers WHERE id = :id", {"id": ids["provider"]}),
        ("DELETE FROM securities WHERE id = :id", {"id": ids["security_one"]}),
    ):
        with pytest.raises(IntegrityError):
            with migration_engine.begin() as connection:
                connection.execute(text(delete_statement), parameters)


def _insert_mapping(
    engine: Engine,
    ids: dict[str, UUID],
    *,
    security_id: UUID,
    symbol: str,
    instrument_id: str | None,
    valid_from: date,
    valid_to: date | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO provider_instrument_mappings
                    (id, provider_id, security_id, provider_symbol, provider_instrument_id,
                     valid_from, valid_to, is_primary, metadata, source_name)
                VALUES (:id, :provider, :security, :symbol, :instrument_id, :valid_from,
                        :valid_to, false, '{}'::jsonb, 'verified test source')
                """
            ),
            {
                "id": uuid4(),
                "provider": ids["provider"],
                "security": security_id,
                "symbol": symbol,
                "instrument_id": instrument_id,
                "valid_from": valid_from,
                "valid_to": valid_to,
            },
        )


def test_active_provider_symbol_cannot_map_to_two_securities(migration_engine: Engine) -> None:
    ids = _seed_lineage(migration_engine)
    _insert_mapping(
        migration_engine,
        ids,
        security_id=ids["security_one"],
        symbol="SHARED",
        instrument_id="ONE",
        valid_from=date(2026, 1, 1),
    )
    with pytest.raises(IntegrityError):
        _insert_mapping(
            migration_engine,
            ids,
            security_id=ids["security_two"],
            symbol="SHARED",
            instrument_id="TWO",
            valid_from=date(2026, 2, 1),
        )


def test_active_mapping_rejects_parallel_valid_from_and_external_id(
    migration_engine: Engine,
) -> None:
    ids = _seed_lineage(migration_engine)
    _insert_mapping(
        migration_engine,
        ids,
        security_id=ids["security_one"],
        symbol="ONE",
        instrument_id="EXTERNAL-ONE",
        valid_from=date(2026, 1, 1),
    )
    with pytest.raises(IntegrityError):
        _insert_mapping(
            migration_engine,
            ids,
            security_id=ids["security_one"],
            symbol="ONE",
            instrument_id="EXTERNAL-TWO",
            valid_from=date(2026, 2, 1),
        )
    with pytest.raises(IntegrityError):
        _insert_mapping(
            migration_engine,
            ids,
            security_id=ids["security_two"],
            symbol="TWO",
            instrument_id="EXTERNAL-ONE",
            valid_from=date(2026, 2, 1),
        )


def test_expired_mapping_history_allows_reused_symbol_and_instrument_id(
    migration_engine: Engine,
) -> None:
    ids = _seed_lineage(migration_engine)
    for security_id, valid_from, valid_to in (
        (ids["security_one"], date(2025, 1, 1), date(2025, 12, 31)),
        (ids["security_two"], date(2026, 1, 1), date(2026, 12, 31)),
    ):
        _insert_mapping(
            migration_engine,
            ids,
            security_id=security_id,
            symbol="HISTORICAL",
            instrument_id="HISTORICAL-ID",
            valid_from=valid_from,
            valid_to=valid_to,
        )


@pytest.mark.parametrize(
    "column_name",
    ("open", "high", "low", "close", "provider_adjusted_close"),
)
def test_daily_price_bar_rejects_numeric_nan(
    migration_engine: Engine,
    column_name: str,
) -> None:
    ids = _seed_lineage(migration_engine)
    with pytest.raises(IntegrityError):
        with migration_engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    INSERT INTO daily_price_bars
                        (id, security_id, provider_id, source_payload_id, provider_symbol,
                         trading_date, {column_name}, currency_code, adjustment_type,
                         retrieved_at)
                    VALUES (:id, :security, :provider, :payload, 'ONE', '2026-07-10',
                            :value, 'USD', 'UNADJUSTED', :retrieved_at)
                    """
                ),
                {
                    "id": uuid4(),
                    "security": ids["security_one"],
                    "provider": ids["provider"],
                    "payload": ids["payload"],
                    "value": Decimal("NaN"),
                    "retrieved_at": datetime(2026, 7, 10, 20, tzinfo=UTC),
                },
            )


@pytest.mark.parametrize("column_name", ("cash_amount", "ratio_numerator", "ratio_denominator"))
def test_corporate_action_rejects_numeric_nan(
    migration_engine: Engine,
    column_name: str,
) -> None:
    ids = _seed_lineage(migration_engine)
    with pytest.raises(IntegrityError):
        with migration_engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    INSERT INTO corporate_actions
                        (id, security_id, provider_id, source_payload_id, action_type,
                         {column_name}, status, retrieved_at)
                    VALUES (:id, :security, :provider, :payload, 'OTHER', :value,
                            'UNKNOWN', :retrieved_at)
                    """
                ),
                {
                    "id": uuid4(),
                    "security": ids["security_one"],
                    "provider": ids["provider"],
                    "payload": ids["payload"],
                    "value": Decimal("NaN"),
                    "retrieved_at": datetime(2026, 7, 10, 20, tzinfo=UTC),
                },
            )


def test_financial_fact_allows_negative_finite_value_but_rejects_nan(
    migration_engine: Engine,
) -> None:
    ids = _seed_lineage(migration_engine)
    statement = text(
        """
        INSERT INTO provider_financial_facts
            (id, security_id, provider_id, source_payload_id, statement_type,
             provider_concept, dimensions, value, retrieved_at)
        VALUES (:id, :security, :provider, :payload, 'OTHER', :concept,
                '{}'::jsonb, :value, :retrieved_at)
        """
    )
    common = {
        "security": ids["security_one"],
        "provider": ids["provider"],
        "payload": ids["payload"],
        "retrieved_at": datetime(2026, 7, 10, 20, tzinfo=UTC),
    }
    with migration_engine.begin() as connection:
        connection.execute(
            statement,
            {**common, "id": uuid4(), "concept": "FiniteLoss", "value": Decimal("-1.25")},
        )
    with pytest.raises(IntegrityError):
        with migration_engine.begin() as connection:
            connection.execute(
                statement,
                {**common, "id": uuid4(), "concept": "NotANumber", "value": Decimal("NaN")},
            )


def _insert_action(
    engine: Engine,
    ids: dict[str, UUID],
    *,
    action_id: UUID,
    provider_action_id: str | None,
    cash_amount: Decimal,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO corporate_actions
                    (id, security_id, provider_id, source_payload_id, provider_action_id,
                     action_type, announcement_date, ex_date, cash_amount, currency_code,
                     status, retrieved_at)
                VALUES (:id, :security, :provider, :payload, :provider_action_id,
                        'CASH_DIVIDEND', '2026-07-01', '2026-07-10', :cash_amount,
                        'USD', 'CONFIRMED', :retrieved_at)
                """
            ),
            {
                "id": action_id,
                "security": ids["security_one"],
                "provider": ids["provider"],
                "payload": ids["payload"],
                "provider_action_id": provider_action_id,
                "cash_amount": cash_amount,
                "retrieved_at": datetime(2026, 7, 10, 20, tzinfo=UTC),
            },
        )


def test_anonymous_corporate_action_identity_rejects_exact_duplicate_but_allows_distinct(
    migration_engine: Engine,
) -> None:
    ids = _seed_lineage(migration_engine)
    _insert_action(
        migration_engine,
        ids,
        action_id=uuid4(),
        provider_action_id=None,
        cash_amount=Decimal("1.25"),
    )
    with pytest.raises(IntegrityError):
        _insert_action(
            migration_engine,
            ids,
            action_id=uuid4(),
            provider_action_id=None,
            cash_amount=Decimal("1.25"),
        )
    _insert_action(
        migration_engine,
        ids,
        action_id=uuid4(),
        provider_action_id=None,
        cash_amount=Decimal("2.50"),
    )


def test_provider_action_id_identity_is_scoped_to_payload(migration_engine: Engine) -> None:
    ids = _seed_lineage(migration_engine)
    _insert_action(
        migration_engine,
        ids,
        action_id=uuid4(),
        provider_action_id="ACTION-1",
        cash_amount=Decimal("1.25"),
    )
    with pytest.raises(IntegrityError):
        _insert_action(
            migration_engine,
            ids,
            action_id=uuid4(),
            provider_action_id="ACTION-1",
            cash_amount=Decimal("2.50"),
        )
