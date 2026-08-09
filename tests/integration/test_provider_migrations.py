from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text

from stock_research_agent.db.base import Base
from stock_research_agent.db.models.providers import PROVIDER_TABLE_PURPOSES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
STAGE9_TABLES = set(PROVIDER_TABLE_PURPOSES)
PRIOR_STAGE_TABLES = {
    "alembic_version",
    "calculation_inputs",
    "calculation_runs",
    "canonical_financial_concepts",
    "citation_anchors",
    "claim_evidence_links",
    "corporate_actions",
    "daily_price_bars",
    "data_providers",
    "data_snapshots",
    "derived_metrics",
    "document_chunks",
    "document_pages",
    "document_parse_runs",
    "document_sections",
    "document_versions",
    "embedding_records",
    "exchange_aliases",
    "exchanges",
    "financial_periods",
    "formula_definitions",
    "ingestion_runs",
    "issuer_identifiers",
    "issuers",
    "lexical_index_versions",
    "lexical_postings",
    "logical_documents",
    "markets",
    "normalized_fact_inputs",
    "normalized_financial_facts",
    "provider_fact_mappings",
    "provider_financial_facts",
    "provider_instrument_mappings",
    "provider_request_logs",
    "raw_payloads",
    "report_blocks",
    "report_citation_bindings",
    "report_claim_bindings",
    "report_evidence_bindings",
    "report_generation_runs",
    "report_policies",
    "report_reflection_findings",
    "report_reflection_runs",
    "report_release_gates",
    "report_requests",
    "report_revision_runs",
    "report_sections",
    "report_template_versions",
    "research_agent_runs",
    "research_claims",
    "research_evidence",
    "research_observations",
    "research_packages",
    "research_plans",
    "research_policies",
    "research_reports",
    "research_requests",
    "research_run_events",
    "research_steps",
    "research_tool_invocations",
    "retrieval_hits",
    "retrieval_runs",
    "runtime_reflection_policies",
    "schema_meta",
    "securities",
    "security_aliases",
    "security_identifiers",
    "snapshot_document_versions",
    "snapshot_items",
    "source_documents",
    "vector_index_versions",
}
PRIOR_STAGE_SENTINELS = {
    "schema_meta",
    "securities",
    "data_snapshots",
    "calculation_runs",
    "retrieval_runs",
    "research_agent_runs",
    "research_reports",
}
EXPECTED_TRIGGERS = {
    "trg_provider_sync_runs_lifecycle",
    "trg_provider_sync_checkpoints_revision",
    "trg_provider_raw_artifacts_immutable",
    "trg_provider_ingestion_manifests_immutable",
    "trg_provider_audit_events_immutable",
    "trg_provider_health_snapshots_immutable",
}


def _integration_was_selected() -> bool:
    arguments = [value.replace("\\", "/").casefold() for value in sys.argv[1:]]
    return any("tests/integration" in value for value in arguments)


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Stage 9 migration tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


def _config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


@pytest.fixture
def migration_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    engine = create_engine(TEST_DATABASE_URL)
    command.upgrade(_config(), "head")
    command.downgrade(_config(), "0007_verifiable_reports")
    try:
        yield engine
    finally:
        command.upgrade(_config(), "head")
        engine.dispose()


def test_stage9_upgrade_creates_only_reviewed_tables_and_preserves_prior_stages(
    migration_engine: Engine,
) -> None:
    before = set(inspect(migration_engine).get_table_names())
    assert not (STAGE9_TABLES & before)
    assert PRIOR_STAGE_SENTINELS <= before

    command.upgrade(_config(), "head")
    after = set(inspect(migration_engine).get_table_names())
    assert STAGE9_TABLES <= after
    assert PRIOR_STAGE_SENTINELS <= after


def test_stage9_schema_matches_models_and_contains_no_seed_rows(
    migration_engine: Engine,
) -> None:
    command.upgrade(_config(), "head")
    inspector = inspect(migration_engine)
    for table_name in STAGE9_TABLES:
        table = Base.metadata.tables[table_name]
        assert inspector.get_pk_constraint(table_name)["name"] == f"pk_{table_name}"
        assert set(table.columns.keys()) == {
            column["name"] for column in inspector.get_columns(table_name)
        }
        assert {constraint.name for constraint in table.foreign_key_constraints} == {
            item["name"] for item in inspector.get_foreign_keys(table_name)
        }
        assert {
            constraint.name
            for constraint in table.constraints
            if constraint.__class__.__name__ == "CheckConstraint"
        } == {item["name"] for item in inspector.get_check_constraints(table_name)}
        assert {
            constraint.name
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        } == {item["name"] for item in inspector.get_unique_constraints(table_name)}
        assert {index.name for index in table.indexes} == {
            item["name"]
            for item in inspector.get_indexes(table_name)
            if item.get("duplicates_constraint") is None
        }
        assert all(
            item["options"].get("ondelete") == "RESTRICT"
            for item in inspector.get_foreign_keys(table_name)
        )
        with migration_engine.connect() as connection:
            assert connection.scalar(text(f'SELECT count(*) FROM "{table_name}"')) == 0


def test_stage9_immutability_and_lifecycle_triggers_exist(
    migration_engine: Engine,
) -> None:
    command.upgrade(_config(), "head")
    with migration_engine.connect() as connection:
        triggers = set(
            connection.execute(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE NOT tgisinternal AND tgrelid IN "
                    "(SELECT oid FROM pg_class WHERE relname = ANY(:tables))"
                ),
                {"tables": list(STAGE9_TABLES)},
            )
            .scalars()
            .all()
        )
    assert EXPECTED_TRIGGERS <= triggers


def test_stage9_downgrade_and_reupgrade_preserve_complete_prior_manifest(
    migration_engine: Engine,
) -> None:
    command.upgrade(_config(), "head")
    assert PRIOR_STAGE_TABLES | STAGE9_TABLES == set(inspect(migration_engine).get_table_names())

    command.downgrade(_config(), "0007_verifiable_reports")
    after_downgrade = set(inspect(migration_engine).get_table_names())
    assert after_downgrade == PRIOR_STAGE_TABLES

    with migration_engine.connect() as connection:
        stage9_functions = connection.scalar(
            text(
                "SELECT count(*) FROM pg_proc "
                "WHERE proname IN "
                "('stage9_reject_mutation','stage9_guard_sync_run',"
                "'stage9_guard_checkpoint_revision')"
            )
        )
    assert stage9_functions == 0

    command.upgrade(_config(), "head")
    assert PRIOR_STAGE_TABLES | STAGE9_TABLES == set(inspect(migration_engine).get_table_names())
