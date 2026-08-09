import os
import sys
from collections.abc import Iterator

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from typer.testing import CliRunner

from stock_research_agent import cli
from stock_research_agent.cli import app
from stock_research_agent.config import AppEnvironment, Settings

_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
runner = CliRunner()
_DROP_ORDER = (
    "retrieval_hits",
    "lexical_postings",
    "embedding_records",
    "citation_anchors",
    "document_sections",
    "document_pages",
    "document_chunks",
    "snapshot_document_versions",
    "document_parse_runs",
    "document_versions",
    "retrieval_runs",
    "lexical_index_versions",
    "vector_index_versions",
    "logical_documents",
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


def _drop_schema_objects(connection: object) -> None:
    from sqlalchemy.engine import Connection

    assert isinstance(connection, Connection)
    connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))


def _integration_was_explicitly_selected() -> bool:
    arguments = [argument.replace("\\", "/").lower() for argument in sys.argv[1:]]
    selected_by_path = any(
        "tests/integration" in argument or "test_cli_database.py" in argument
        for argument in arguments
    )
    selected_by_marker = any(
        argument == "integration" and index > 0 and arguments[index - 1] == "-m"
        for index, argument in enumerate(arguments)
    )
    return selected_by_path or selected_by_marker


if _TEST_DATABASE_URL is None and _integration_was_explicitly_selected():
    raise pytest.UsageError(
        "TEST_DATABASE_URL is required when PostgreSQL integration tests are explicitly selected"
    )

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        _TEST_DATABASE_URL is None,
        reason="PostgreSQL integration tests require TEST_DATABASE_URL",
    ),
]


def _validated_test_environment() -> dict[str, str]:
    assert _TEST_DATABASE_URL is not None
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=_TEST_DATABASE_URL,
    )
    assert settings.database_url is not None
    return {
        "APP_ENV": settings.app_env.value,
        "DATABASE_URL": settings.database_url,
    }


@pytest.fixture
def isolated_cli_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    environment = _validated_test_environment()
    database_url = environment["DATABASE_URL"]
    engine = create_engine(database_url)
    monkeypatch.setenv("APP_ENV", environment["APP_ENV"])
    monkeypatch.setenv("DATABASE_URL", database_url)
    with engine.begin() as connection:
        _drop_schema_objects(connection)
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            _drop_schema_objects(connection)
        alembic_command.upgrade(Config("alembic.ini"), "head")
        engine.dispose()


def test_cli_health_checks_real_postgresql_17() -> None:
    result = runner.invoke(app, ["health"], env=_validated_test_environment())

    assert result.exit_code == 0
    assert result.stdout == "Health check passed\n"


def test_cli_upgrade_and_downgrade_only_validated_test_database(
    isolated_cli_database: Engine,
) -> None:
    environment = _validated_test_environment()

    upgrade = runner.invoke(app, ["db-upgrade"], env=environment)
    assert upgrade.exit_code == 0
    assert upgrade.stdout == "Database upgrade complete\n"
    assert "schema_meta" in inspect(isolated_cli_database).get_table_names()

    downgrade = runner.invoke(
        app,
        ["db-downgrade", "--revision", "base"],
        env=environment,
    )
    assert downgrade.exit_code == 0
    assert downgrade.stdout == "Database downgrade complete\n"
    assert "schema_meta" not in inspect(isolated_cli_database).get_table_names()

    alembic_command.upgrade(Config("alembic.ini"), "head")


def test_cli_migrates_injected_target_despite_conflicting_process_environment(
    isolated_cli_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    injected_settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=_validated_test_environment()["DATABASE_URL"],
    )
    monkeypatch.setattr(cli, "settings_factory", lambda: injected_settings)
    conflicting_environment = {
        "APP_ENV": "production",
        "DATABASE_URL": ("postgresql+psycopg://unreachable:secret@127.0.0.1:1/unreachable"),
    }

    result = runner.invoke(app, ["db-upgrade"], env=conflicting_environment)

    assert result.exit_code == 0
    assert result.stdout == "Database upgrade complete\n"
    assert "schema_meta" in inspect(isolated_cli_database).get_table_names()
