from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime as SqlDateTime
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSqlUuid
from sqlalchemy.exc import IntegrityError

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.db.models import Security

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
_STAGE_3_TABLES = {
    "markets",
    "exchanges",
    "exchange_aliases",
    "issuers",
    "issuer_identifiers",
    "securities",
    "security_identifiers",
    "security_aliases",
}
_DROP_ORDER = (
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


if _TEST_DATABASE_URL is None and _integration_was_explicitly_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for PostgreSQL integration tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(_TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


def _reset(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))


def _create_test_engine(database_url: str) -> Engine:
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=database_url,
    )
    assert settings.database_url is not None
    return create_engine(settings.database_url)


def test_non_test_database_is_rejected_before_destructive_engine_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine_creation_attempted = False

    def fail_if_called(_database_url: str) -> Engine:
        nonlocal engine_creation_attempted
        engine_creation_attempted = True
        raise AssertionError("create_engine must not run for a non-test database")

    monkeypatch.setattr(sys.modules[__name__], "create_engine", fail_if_called)

    with pytest.raises(ValueError, match="database name must end with '_test'"):
        _create_test_engine(
            "postgresql+psycopg://stock_user:password@127.0.0.1:55432/stock_research"
        )

    assert engine_creation_attempted is False


@pytest.fixture(scope="module")
def migrated_engine() -> Iterator[Engine]:
    assert _TEST_DATABASE_URL is not None
    engine = _create_test_engine(_TEST_DATABASE_URL)
    config = Config(str(_PROJECT_ROOT / "alembic.ini"))
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
    _reset(engine)
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        _reset(engine)
        command.upgrade(config, "head")
        engine.dispose()
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url


def _insert_minimum_master_data(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO markets
                    (id, code, name, country_code, default_currency_code, status)
                VALUES
                    (:cn_id, 'CN_A', 'China A Shares', 'CN', 'CNY', 'ACTIVE'),
                    (:us_id, 'US_EQUITY', 'US Equity', 'US', 'USD', 'ACTIVE')
                """
            ),
            {
                "cn_id": UUID("10000000-0000-0000-0000-000000000001"),
                "us_id": UUID("10000000-0000-0000-0000-000000000002"),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO exchanges
                    (id, market_id, mic, name, short_name, country_code, timezone,
                     default_currency_code, status)
                VALUES
                    (:xshg, :cn_id, 'XSHG', 'Shanghai Stock Exchange', 'SSE', 'CN',
                     'Asia/Shanghai', 'CNY', 'ACTIVE'),
                    (:xnas, :us_id, 'XNAS', 'Nasdaq', 'Nasdaq', 'US',
                     'America/New_York', 'USD', 'ACTIVE')
                """
            ),
            {
                "xshg": UUID("20000000-0000-0000-0000-000000000001"),
                "xnas": UUID("20000000-0000-0000-0000-000000000002"),
                "cn_id": UUID("10000000-0000-0000-0000-000000000001"),
                "us_id": UUID("10000000-0000-0000-0000-000000000002"),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO issuers
                    (id, legal_name, normalized_legal_name, display_name,
                     normalized_display_name, country_code, issuer_status)
                VALUES
                    (:issuer_one, 'One Inc.', 'ONE INC', 'One', 'ONE', 'US', 'ACTIVE'),
                    (:issuer_two, 'Two Inc.', 'TWO INC', 'Two', 'TWO', 'US', 'ACTIVE')
                """
            ),
            {
                "issuer_one": UUID("30000000-0000-0000-0000-000000000001"),
                "issuer_two": UUID("30000000-0000-0000-0000-000000000002"),
            },
        )


def _truncate_master_data(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE security_aliases, security_identifiers, securities, "
                "issuer_identifiers, issuers, exchange_aliases, exchanges, markets CASCADE"
            )
        )


@pytest.fixture
def master_data_engine(migrated_engine: Engine) -> Iterator[Engine]:
    _truncate_master_data(migrated_engine)
    _insert_minimum_master_data(migrated_engine)
    try:
        yield migrated_engine
    finally:
        _truncate_master_data(migrated_engine)


def test_migration_creates_all_tables_constraints_and_indexes(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    assert _STAGE_3_TABLES <= set(inspector.get_table_names())

    expected_indexes = {
        "ix_issuers_normalized_legal_name",
        "ix_issuers_normalized_display_name",
        "ix_issuers_normalized_legal_name_prefix",
        "ix_issuers_normalized_display_name_prefix",
        "ix_securities_normalized_symbol",
        "ix_securities_normalized_symbol_prefix",
        "ix_security_aliases_normalized_alias",
        "ix_security_aliases_normalized_alias_prefix",
    }
    actual_indexes = {
        index["name"]
        for table_name in _STAGE_3_TABLES
        for index in inspector.get_indexes(table_name)
    }
    assert expected_indexes <= actual_indexes

    for table_name in _STAGE_3_TABLES:
        primary_key = inspector.get_pk_constraint(table_name)
        assert primary_key["name"] == f"pk_{table_name}"
        assert primary_key["constrained_columns"] == ["id"]

        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        assert isinstance(columns["id"]["type"], PostgreSqlUuid)
        assert columns["id"]["nullable"] is False
        for timestamp_name in ("created_at", "updated_at"):
            assert isinstance(columns[timestamp_name]["type"], SqlDateTime)
            assert columns[timestamp_name]["type"].timezone is True
            assert columns[timestamp_name]["nullable"] is False

        metadata_table = Security.metadata.tables[table_name]
        expected_uniques = {
            constraint.name: [column.name for column in constraint.columns]
            for constraint in metadata_table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        actual_uniques = {
            constraint["name"]: constraint["column_names"]
            for constraint in inspector.get_unique_constraints(table_name)
        }
        assert actual_uniques == expected_uniques

        expected_checks = {
            constraint.name
            for constraint in metadata_table.constraints
            if constraint.__class__.__name__ == "CheckConstraint"
        }
        actual_checks = {
            constraint["name"] for constraint in inspector.get_check_constraints(table_name)
        }
        assert actual_checks == expected_checks

        for foreign_key in inspector.get_foreign_keys(table_name):
            assert foreign_key["options"].get("ondelete") == "RESTRICT"

    with migrated_engine.connect() as connection:
        index_definitions = dict(
            connection.execute(
                text(
                    """
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND indexname LIKE :suffix
                    """
                ),
                {"suffix": "%_prefix"},
            ).all()
        )
    assert set(index_definitions) == {
        "ix_issuers_normalized_legal_name_prefix",
        "ix_issuers_normalized_display_name_prefix",
        "ix_securities_normalized_symbol_prefix",
        "ix_security_aliases_normalized_alias_prefix",
    }
    assert all("text_pattern_ops" in definition for definition in index_definitions.values())


def test_exchange_symbol_uniqueness_is_scoped_to_exchange(master_data_engine: Engine) -> None:
    security_id = UUID("40000000-0000-0000-0000-000000000001")
    statement = text(
        """
        INSERT INTO securities
            (id, issuer_id, exchange_id, symbol, normalized_symbol, display_name,
             security_type, currency_code, listing_status, is_primary_listing)
        VALUES
            (:id, :issuer_id, :exchange_id, 'DUP', 'DUP', 'Duplicate',
             'COMMON_STOCK', :currency, 'ACTIVE', false)
        """
    )
    with master_data_engine.begin() as connection:
        connection.execute(
            statement,
            {
                "id": security_id,
                "issuer_id": UUID("30000000-0000-0000-0000-000000000001"),
                "exchange_id": UUID("20000000-0000-0000-0000-000000000002"),
                "currency": "USD",
            },
        )

    with pytest.raises(IntegrityError):
        with master_data_engine.begin() as connection:
            connection.execute(
                statement,
                {
                    "id": UUID("40000000-0000-0000-0000-000000000002"),
                    "issuer_id": UUID("30000000-0000-0000-0000-000000000002"),
                    "exchange_id": UUID("20000000-0000-0000-0000-000000000002"),
                    "currency": "USD",
                },
            )

    with master_data_engine.begin() as connection:
        connection.execute(
            statement,
            {
                "id": UUID("40000000-0000-0000-0000-000000000003"),
                "issuer_id": UUID("30000000-0000-0000-0000-000000000002"),
                "exchange_id": UUID("20000000-0000-0000-0000-000000000001"),
                "currency": "CNY",
            },
        )


@pytest.mark.parametrize(
    ("statement", "parameters"),
    [
        (
            "INSERT INTO markets (id, code, name, country_code, default_currency_code, status) "
            "VALUES (gen_random_uuid(), 'BAD', 'Bad', 'ZZ', 'USD', 'ACTIVE')",
            {},
        ),
        (
            "INSERT INTO markets (id, code, name, country_code, default_currency_code, status) "
            "VALUES (gen_random_uuid(), 'bad', 'Bad', 'US', 'USD', 'ACTIVE')",
            {},
        ),
        (
            "INSERT INTO securities "
            "(id, issuer_id, exchange_id, symbol, normalized_symbol, display_name, "
            "security_type, currency_code, listing_status, listing_date, delisting_date, "
            "is_primary_listing) VALUES (gen_random_uuid(), :issuer_id, :exchange_id, "
            "'BAD', 'BAD', 'Bad', 'COMMON_STOCK', 'USD', 'DELISTED', :listing, :delisting, false)",
            {
                "issuer_id": UUID("30000000-0000-0000-0000-000000000001"),
                "exchange_id": UUID("20000000-0000-0000-0000-000000000002"),
                "listing": date(2026, 1, 2),
                "delisting": date(2026, 1, 1),
            },
        ),
    ],
)
def test_database_check_constraints_reject_invalid_values(
    master_data_engine: Engine, statement: str, parameters: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError):
        with master_data_engine.begin() as connection:
            connection.execute(text(statement), parameters)


@pytest.mark.parametrize(
    ("statement", "parameters"),
    [
        (
            "UPDATE exchanges SET mic = 'ZZZZ' WHERE id = :id",
            {
                "id": UUID("20000000-0000-0000-0000-000000000002"),
            },
        ),
        (
            "UPDATE exchanges SET default_currency_code = 'ZZZ' WHERE id = :id",
            {
                "id": UUID("20000000-0000-0000-0000-000000000002"),
            },
        ),
        (
            "INSERT INTO securities "
            "(id, issuer_id, exchange_id, symbol, normalized_symbol, display_name, "
            "security_type, currency_code, listing_status, is_primary_listing) "
            "VALUES (:id, :issuer, :exchange, 'BAD', 'BAD', 'Bad', 'COMMON_STOCK', "
            "'USD', 'REMOVED', false)",
            {
                "id": UUID("50000000-0000-0000-0000-000000000003"),
                "issuer": UUID("30000000-0000-0000-0000-000000000001"),
                "exchange": UUID("20000000-0000-0000-0000-000000000002"),
            },
        ),
        (
            "INSERT INTO issuer_identifiers "
            "(id, issuer_id, scheme, value, normalized_value, source_name, valid_from, "
            "valid_to, is_primary) VALUES (:id, :issuer, 'SEC_CIK', '1', '0000000001', "
            "'test', '2026-01-02', '2026-01-01', false)",
            {
                "id": UUID("50000000-0000-0000-0000-000000000004"),
                "issuer": UUID("30000000-0000-0000-0000-000000000001"),
            },
        ),
    ],
)
def test_additional_code_status_and_validity_checks_are_enforced(
    master_data_engine: Engine, statement: str, parameters: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError):
        with master_data_engine.begin() as connection:
            connection.execute(text(statement), parameters)


def test_identifier_values_cannot_bind_to_different_owners(
    master_data_engine: Engine,
) -> None:
    statement = text(
        """
        INSERT INTO issuer_identifiers
            (id, issuer_id, scheme, value, normalized_value, source_name, is_primary)
        VALUES (:id, :issuer_id, 'SEC_CIK', '0000000001', '0000000001', 'test', false)
        """
    )
    with master_data_engine.begin() as connection:
        connection.execute(
            statement,
            {
                "id": UUID("60000000-0000-0000-0000-000000000001"),
                "issuer_id": UUID("30000000-0000-0000-0000-000000000001"),
            },
        )

    with pytest.raises(IntegrityError):
        with master_data_engine.begin() as connection:
            connection.execute(
                statement,
                {
                    "id": UUID("60000000-0000-0000-0000-000000000002"),
                    "issuer_id": UUID("30000000-0000-0000-0000-000000000002"),
                },
            )


def test_exchange_alias_conflict_is_global(master_data_engine: Engine) -> None:
    statement = text(
        """
        INSERT INTO exchange_aliases
            (id, exchange_id, alias, normalized_alias, alias_type, is_active)
        VALUES (:id, :exchange_id, :alias, 'SHARED', 'SHORT_NAME', true)
        """
    )
    with master_data_engine.begin() as connection:
        connection.execute(
            statement,
            {
                "id": UUID("70000000-0000-0000-0000-000000000001"),
                "exchange_id": UUID("20000000-0000-0000-0000-000000000001"),
                "alias": "Shared One",
            },
        )

    with pytest.raises(IntegrityError):
        with master_data_engine.begin() as connection:
            connection.execute(
                statement,
                {
                    "id": UUID("70000000-0000-0000-0000-000000000002"),
                    "exchange_id": UUID("20000000-0000-0000-0000-000000000002"),
                    "alias": "Shared Two",
                },
            )


def test_security_identifier_conflicts_and_shared_alias_scope(
    master_data_engine: Engine,
) -> None:
    security_statement = text(
        """
        INSERT INTO securities
            (id, issuer_id, exchange_id, symbol, normalized_symbol, display_name,
             security_type, currency_code, listing_status, is_primary_listing)
        VALUES (:id, :issuer, :exchange, :symbol, :symbol, :symbol,
                'COMMON_STOCK', :currency, 'ACTIVE', false)
        """
    )
    first_security = UUID("75000000-0000-0000-0000-000000000001")
    second_security = UUID("75000000-0000-0000-0000-000000000002")
    with master_data_engine.begin() as connection:
        connection.execute(
            security_statement,
            {
                "id": first_security,
                "issuer": UUID("30000000-0000-0000-0000-000000000001"),
                "exchange": UUID("20000000-0000-0000-0000-000000000002"),
                "symbol": "ONE",
                "currency": "USD",
            },
        )
        connection.execute(
            security_statement,
            {
                "id": second_security,
                "issuer": UUID("30000000-0000-0000-0000-000000000002"),
                "exchange": UUID("20000000-0000-0000-0000-000000000001"),
                "symbol": "TWO",
                "currency": "CNY",
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO security_identifiers
                    (id, security_id, scheme, value, normalized_value, source_name, is_primary)
                VALUES (:id, :security, 'TEST_SECURITY_ID', 'shared', 'SHARED', 'test', false)
                """
            ),
            {
                "id": UUID("76000000-0000-0000-0000-000000000001"),
                "security": first_security,
            },
        )
        for alias_id, security_id in (
            (UUID("77000000-0000-0000-0000-000000000001"), first_security),
            (UUID("77000000-0000-0000-0000-000000000002"), second_security),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO security_aliases
                        (id, security_id, alias, normalized_alias, alias_type, source_name,
                         is_active)
                    VALUES (:id, :security, 'Shared Name', 'SHARED NAME',
                            'COMPANY_SHORT_NAME', 'test', true)
                    """
                ),
                {"id": alias_id, "security": security_id},
            )

    with pytest.raises(IntegrityError):
        with master_data_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO security_identifiers
                        (id, security_id, scheme, value, normalized_value, source_name,
                         is_primary)
                    VALUES (:id, :security, 'TEST_SECURITY_ID', 'shared', 'SHARED',
                            'test', false)
                    """
                ),
                {
                    "id": UUID("76000000-0000-0000-0000-000000000002"),
                    "security": second_security,
                },
            )

    with pytest.raises(IntegrityError):
        with master_data_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO security_aliases
                        (id, security_id, alias, normalized_alias, alias_type, source_name,
                         valid_from, valid_to, is_active)
                    VALUES (:id, :security, 'Bad Dates', 'BAD DATES', 'FORMER_NAME', 'test',
                            '2026-01-02', '2026-01-01', false)
                    """
                ),
                {
                    "id": UUID("77000000-0000-0000-0000-000000000003"),
                    "security": first_security,
                },
            )


def test_foreign_keys_restrict_master_data_deletion(master_data_engine: Engine) -> None:
    security_statement = text(
        """
        INSERT INTO securities
            (id, issuer_id, exchange_id, symbol, normalized_symbol, display_name,
             security_type, currency_code, listing_status, is_primary_listing)
        VALUES (:id, :issuer, :exchange, 'LOCK', 'LOCK', 'Locked',
                'COMMON_STOCK', 'USD', 'ACTIVE', false)
        """
    )
    with master_data_engine.begin() as connection:
        connection.execute(
            security_statement,
            {
                "id": UUID("80000000-0000-0000-0000-000000000001"),
                "issuer": UUID("30000000-0000-0000-0000-000000000001"),
                "exchange": UUID("20000000-0000-0000-0000-000000000002"),
            },
        )

    with pytest.raises(IntegrityError):
        with master_data_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM issuers WHERE id = :issuer_id"),
                {"issuer_id": UUID("30000000-0000-0000-0000-000000000001")},
            )
