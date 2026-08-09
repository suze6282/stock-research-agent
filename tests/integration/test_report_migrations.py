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
from stock_research_agent.db.models.reports import STAGE8_MODEL_TABLES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
STAGE8_TABLES = {
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
assert STAGE8_TABLES == set(STAGE8_MODEL_TABLES)
EXPECTED_TRIGGERS = {
    *(f"trg_{table}_immutable" for table in STAGE8_TABLES),
    "trg_report_generation_runs_lifecycle",
    "trg_report_reflection_runs_lifecycle",
    "trg_report_revision_runs_lifecycle",
    "trg_research_reports_validate_version",
} - {
    "trg_report_generation_runs_immutable",
    "trg_report_reflection_runs_immutable",
    "trg_report_revision_runs_immutable",
}


def _integration_was_selected() -> bool:
    arguments = [value.replace("\\", "/").casefold() for value in sys.argv[1:]]
    return any("tests/integration" in value for value in arguments)


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Stage 8 migration tests")

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
    command.downgrade(_config(), "0006_controlled_research_agent")
    try:
        yield engine
    finally:
        command.upgrade(_config(), "head")
        engine.dispose()


def test_stage8_upgrade_downgrade_upgrade_preserves_stage7(
    migration_engine: Engine,
) -> None:
    before = set(inspect(migration_engine).get_table_names())
    assert not (STAGE8_TABLES & before)
    assert {"research_packages", "research_claims", "data_snapshots"} <= before

    command.upgrade(_config(), "head")
    assert STAGE8_TABLES <= set(inspect(migration_engine).get_table_names())

    command.downgrade(_config(), "0006_controlled_research_agent")
    after_downgrade = set(inspect(migration_engine).get_table_names())
    assert not (STAGE8_TABLES & after_downgrade)
    assert {"research_packages", "research_claims", "data_snapshots"} <= after_downgrade

    command.upgrade(_config(), "head")
    assert STAGE8_TABLES <= set(inspect(migration_engine).get_table_names())


def test_stage8_schema_has_named_constraints_indexes_and_no_seed_rows(
    migration_engine: Engine,
) -> None:
    command.upgrade(_config(), "head")
    inspector = inspect(migration_engine)
    for table_name in STAGE8_TABLES:
        assert inspector.get_pk_constraint(table_name)["name"] == f"pk_{table_name}"
        assert all(
            foreign_key["options"].get("ondelete") == "RESTRICT"
            for foreign_key in inspector.get_foreign_keys(table_name)
        )
        assert all(
            constraint["name"] is not None
            for constraint in inspector.get_check_constraints(table_name)
        )
        assert all(
            constraint["name"] is not None
            for constraint in inspector.get_unique_constraints(table_name)
        )
        with migration_engine.connect() as connection:
            assert connection.scalar(text(f'SELECT count(*) FROM "{table_name}"')) == 0

    indexes = {
        table: {item["name"] for item in inspector.get_indexes(table)} for table in STAGE8_TABLES
    }
    columns = {
        table: {item["name"] for item in inspector.get_columns(table)} for table in STAGE8_TABLES
    }
    assert "ix_report_requests_research_package" in indexes["report_requests"]
    assert "ix_report_generation_runs_package" in indexes["report_generation_runs"]
    assert "ix_research_reports_security_snapshot_created" in indexes["research_reports"]
    assert "ix_report_claim_bindings_claim" in indexes["report_claim_bindings"]
    assert "ix_report_evidence_bindings_evidence" in indexes["report_evidence_bindings"]
    assert "ix_report_citation_bindings_citation" in indexes["report_citation_bindings"]
    assert {
        "sentence_index",
        "item_or_row_key",
    }.issubset(columns["report_claim_bindings"])
    assert {
        "visible_reference",
        "citation_id",
        "source_record_id",
        "source_checksum",
    }.issubset(columns["report_evidence_bindings"])
    assert "ix_report_reflection_findings_run_severity" in indexes["report_reflection_findings"]


def test_stage8_status_round_and_version_guards_are_database_enforced(
    migration_engine: Engine,
) -> None:
    command.upgrade(_config(), "head")
    inspector = inspect(migration_engine)
    checks = {
        table: {item["name"] for item in inspector.get_check_constraints(table)}
        for table in STAGE8_TABLES
    }
    assert "ck_report_generation_runs_status" in checks["report_generation_runs"]
    assert "ck_research_reports_status" in checks["research_reports"]
    assert "ck_report_reflection_runs_round" in checks["report_reflection_runs"]
    assert "ck_report_revision_runs_round" in checks["report_revision_runs"]
    assert "ck_report_release_gates_decision" in checks["report_release_gates"]


def test_stage8_migration_matches_sqlalchemy_models(
    migration_engine: Engine,
) -> None:
    command.upgrade(_config(), "head")
    inspector = inspect(migration_engine)
    for table_name in STAGE8_TABLES:
        table = Base.metadata.tables[table_name]
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


def test_stage8_immutability_and_lifecycle_triggers_exist(
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
                {"tables": list(STAGE8_TABLES)},
            )
            .scalars()
            .all()
        )
    assert EXPECTED_TRIGGERS <= triggers
