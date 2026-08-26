import os
import subprocess
import sys
from collections.abc import Iterator
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, create_engine, inspect, text
from sqlalchemy.engine import Engine

from stock_research_agent.config import AppEnvironment, Settings

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _PROJECT_ROOT / "alembic.ini"
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
_STAGE_4_TABLES = {
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
_STAGE_5_TABLES = {
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
_STAGE_6_TABLES = {
    "logical_documents",
    "document_versions",
    "snapshot_document_versions",
    "document_parse_runs",
    "document_pages",
    "document_sections",
    "document_chunks",
    "citation_anchors",
    "lexical_index_versions",
    "lexical_postings",
    "embedding_records",
    "vector_index_versions",
    "retrieval_runs",
    "retrieval_hits",
}
_STAGE_7_TABLES = {
    "research_policies",
    "research_requests",
    "research_agent_runs",
    "research_plans",
    "research_steps",
    "research_tool_invocations",
    "research_observations",
    "research_evidence",
    "research_claims",
    "claim_evidence_links",
    "research_packages",
    "research_run_events",
}
_STAGE_8_TABLES = {
    "report_policies",
    "report_template_versions",
    "runtime_reflection_policies",
    "report_requests",
    "report_generation_runs",
    "research_reports",
    "report_sections",
    "report_blocks",
    "report_claim_bindings",
    "report_evidence_bindings",
    "report_citation_bindings",
    "report_reflection_runs",
    "report_reflection_findings",
    "report_revision_runs",
    "report_release_gates",
}
_STAGE_9_TABLES = {
    "provider_definitions",
    "provider_capabilities",
    "provider_policies",
    "provider_license_policies",
    "provider_credential_references",
    "provider_sync_requests",
    "provider_sync_plans",
    "provider_sync_runs",
    "provider_sync_checkpoints",
    "provider_request_attempts",
    "provider_raw_artifacts",
    "provider_ingestion_manifests",
    "provider_cache_entries",
    "provider_circuit_breakers",
    "provider_dead_letters",
    "provider_data_quality_issues",
    "provider_freshness_policies",
    "provider_health_snapshots",
    "provider_audit_events",
    "provider_live_validation_runs",
}
_STAGE_10_TABLES = {
    "live_authorization_grants",
    "live_authorization_events",
    "live_authorization_consumptions",
    "live_execution_approvals",
    "manual_evidence_import_requests",
    "manual_evidence_source_declarations",
    "manual_evidence_validations",
    "manual_evidence_reviews",
    "evidence_ingestion_manifests",
    "ingestion_to_snapshot_bindings",
    "real_company_validation_runs",
    "end_to_end_research_validations",
    "evidence_retention_actions",
    "live_incidents",
    "live_incident_events",
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
    selected_by_path = any(
        "tests/integration" in argument or "test_migrations.py" in argument
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


def _alembic_config(*, stdout: StringIO | None = None) -> Config:
    return Config(
        str(_ALEMBIC_INI),
        stdout=stdout or sys.stdout,
        output_buffer=stdout,
    )


def _drop_migration_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))


def _create_migration_engine(database_url: str) -> tuple[Settings, Engine]:
    settings = Settings(
        app_env=AppEnvironment.TEST,
        database_url=database_url,
    )
    assert settings.database_url is not None
    return settings, create_engine(settings.database_url)


def test_non_test_database_is_rejected_before_engine_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine_creation_attempted = False

    def fail_if_called(_database_url: str) -> Engine:
        nonlocal engine_creation_attempted
        engine_creation_attempted = True
        raise AssertionError("create_engine must not be called for a non-test database")

    monkeypatch.setattr(sys.modules[__name__], "create_engine", fail_if_called)

    with pytest.raises(ValueError, match="database name must end with '_test'"):
        _create_migration_engine(
            "postgresql+psycopg://stock_user:password@127.0.0.1:55432/stock_research"
        )

    assert engine_creation_attempted is False


@pytest.fixture
def migration_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    assert _TEST_DATABASE_URL is not None
    settings, engine = _create_migration_engine(_TEST_DATABASE_URL)
    assert settings.database_url is not None
    monkeypatch.setenv("APP_ENV", settings.app_env.value)
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    _drop_migration_tables(engine)
    try:
        yield engine
    finally:
        _drop_migration_tables(engine)
        command.upgrade(_alembic_config(), "head")
        engine.dispose()


def test_upgrade_downgrade_and_second_upgrade_use_postgresql(
    migration_database: Engine,
) -> None:
    config = _alembic_config()
    tables_before_upgrade = set(inspect(migration_database).get_table_names())

    command.upgrade(config, "0001_create_schema_meta")
    assert set(inspect(migration_database).get_table_names()) - tables_before_upgrade == {
        "alembic_version",
        "schema_meta",
    }

    command.upgrade(config, "head")

    inspector = inspect(migration_database)
    created_tables = set(inspector.get_table_names()) - tables_before_upgrade
    assert (
        created_tables
        == {
            "alembic_version",
            "schema_meta",
        }
        | _STAGE_3_TABLES
        | _STAGE_4_TABLES
        | _STAGE_5_TABLES
        | _STAGE_6_TABLES
        | _STAGE_7_TABLES
        | _STAGE_8_TABLES
        | _STAGE_9_TABLES
        | _STAGE_10_TABLES
    )
    columns = inspector.get_columns("schema_meta")
    assert [column["name"] for column in columns] == ["id", "schema_version", "applied_at"]
    assert inspector.get_pk_constraint("schema_meta")["constrained_columns"] == ["id"]
    assert columns[1]["nullable"] is False
    assert columns[2]["nullable"] is False
    assert isinstance(columns[2]["type"], DateTime)
    assert columns[2]["type"].timezone is True

    command.downgrade(config, "-1")
    tables_after_attempt_capacity_downgrade = set(inspect(migration_database).get_table_names())
    assert _STAGE_10_TABLES <= tables_after_attempt_capacity_downgrade

    command.downgrade(config, "-1")
    tables_after_lineage_integrity_downgrade = set(inspect(migration_database).get_table_names())
    assert _STAGE_10_TABLES <= tables_after_lineage_integrity_downgrade

    command.downgrade(config, "-1")
    tables_after_component_lineage_downgrade = set(inspect(migration_database).get_table_names())
    assert _STAGE_10_TABLES <= tables_after_component_lineage_downgrade

    command.downgrade(config, "-1")
    tables_after_request_contract_downgrade = set(inspect(migration_database).get_table_names())
    assert _STAGE_10_TABLES <= tables_after_request_contract_downgrade

    command.downgrade(config, "-1")
    tables_after_stage_10_downgrade = set(inspect(migration_database).get_table_names())
    assert "schema_meta" in tables_after_stage_10_downgrade
    assert _STAGE_3_TABLES <= tables_after_stage_10_downgrade
    assert _STAGE_4_TABLES <= tables_after_stage_10_downgrade
    assert _STAGE_5_TABLES <= tables_after_stage_10_downgrade
    assert _STAGE_6_TABLES <= tables_after_stage_10_downgrade
    assert _STAGE_7_TABLES <= tables_after_stage_10_downgrade
    assert _STAGE_8_TABLES <= tables_after_stage_10_downgrade
    assert _STAGE_9_TABLES <= tables_after_stage_10_downgrade
    assert not (_STAGE_10_TABLES & tables_after_stage_10_downgrade)

    command.upgrade(config, "head")
    assert _STAGE_3_TABLES <= set(inspect(migration_database).get_table_names())
    assert _STAGE_4_TABLES <= set(inspect(migration_database).get_table_names())
    assert _STAGE_5_TABLES <= set(inspect(migration_database).get_table_names())
    assert _STAGE_6_TABLES <= set(inspect(migration_database).get_table_names())
    assert _STAGE_7_TABLES <= set(inspect(migration_database).get_table_names())
    assert _STAGE_8_TABLES <= set(inspect(migration_database).get_table_names())
    assert _STAGE_9_TABLES <= set(inspect(migration_database).get_table_names())
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=_PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "No new upgrade operations detected" in result.stdout


def test_offline_upgrade_emits_postgresql_sql_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unreachable_url_with_percent = "postgresql+psycopg://offline:p%25ss@127.0.0.1:1/offline_test"
    monkeypatch.setenv("DATABASE_URL", unreachable_url_with_percent)
    output = StringIO()

    command.upgrade(_alembic_config(stdout=output), "head", sql=True)

    generated_sql = output.getvalue()
    assert "CREATE TABLE schema_meta" in generated_sql
    assert "CREATE TABLE markets" in generated_sql
    assert "CREATE TABLE securities" in generated_sql
    assert "CREATE TABLE data_providers" in generated_sql
    assert "CREATE TABLE data_snapshots" in generated_sql
    assert "CREATE TABLE canonical_financial_concepts" in generated_sql
    assert "CREATE TABLE calculation_runs" in generated_sql
    assert "TIMESTAMP WITH TIME ZONE" in generated_sql
    assert "INSERT INTO markets" not in generated_sql
    assert "INSERT INTO issuers" not in generated_sql
    assert "INSERT INTO securities" not in generated_sql
    assert "601138" not in generated_sql
    assert "0000723125" not in generated_sql
