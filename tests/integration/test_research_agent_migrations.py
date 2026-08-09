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
from stock_research_agent.db.models.research_agent import STAGE7_MODEL_TABLES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
STAGE7_TABLES = set(STAGE7_MODEL_TABLES)
EXPECTED_TRIGGERS = {
    "trg_research_requests_validate_snapshot",
    "trg_research_agent_runs_validate_lineage",
    "trg_research_agent_runs_guard_update",
    "trg_research_steps_validate_lineage",
    "trg_research_steps_guard_update",
    "trg_research_tool_invocations_validate_lineage",
    "trg_research_tool_invocations_guard_update",
    "trg_research_claims_guard_update",
    "trg_claim_evidence_links_validate_lineage",
    "trg_research_packages_validate_lineage",
    "trg_research_run_events_validate_lineage",
    "trg_research_policies_immutable",
    "trg_research_requests_immutable",
    "trg_research_plans_immutable",
    "trg_research_observations_immutable",
    "trg_research_evidence_immutable",
    "trg_claim_evidence_links_immutable",
    "trg_research_packages_immutable",
    "trg_research_run_events_immutable",
}


def _integration_was_selected() -> bool:
    arguments = [value.replace("\\", "/").lower() for value in sys.argv[1:]]
    return any("tests/integration" in value for value in arguments) or "integration" in arguments


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Stage 7 migration tests")

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
    command.downgrade(_config(), "0005_rag_citations")
    try:
        yield engine
    finally:
        command.upgrade(_config(), "head")
        engine.dispose()


def test_stage7_upgrade_downgrade_upgrade_preserves_stage6(
    migration_engine: Engine,
) -> None:
    assert not (STAGE7_TABLES & set(inspect(migration_engine).get_table_names()))

    command.upgrade(_config(), "head")
    assert STAGE7_TABLES <= set(inspect(migration_engine).get_table_names())

    command.downgrade(_config(), "0005_rag_citations")
    after_downgrade = set(inspect(migration_engine).get_table_names())
    assert not (STAGE7_TABLES & after_downgrade)
    assert {"retrieval_runs", "citation_anchors", "calculation_runs", "data_snapshots"} <= (
        after_downgrade
    )

    command.upgrade(_config(), "head")
    assert STAGE7_TABLES <= set(inspect(migration_engine).get_table_names())


def test_stage7_catalog_matches_models_and_contains_no_seed_rows(
    migration_engine: Engine,
) -> None:
    command.upgrade(_config(), "head")
    inspector = inspect(migration_engine)

    for table_name in STAGE7_TABLES:
        assert inspector.get_pk_constraint(table_name)["name"] == f"pk_{table_name}"
        assert all(
            foreign_key["options"].get("ondelete") == "RESTRICT"
            for foreign_key in inspector.get_foreign_keys(table_name)
        )
        with migration_engine.connect() as connection:
            assert connection.scalar(text(f'SELECT count(*) FROM "{table_name}"')) == 0

    model_tables = {
        table_name: {
            "columns": set(table.columns.keys()),
            "foreign_keys": {constraint.name for constraint in table.foreign_key_constraints},
            "checks": {
                constraint.name
                for constraint in table.constraints
                if constraint.__class__.__name__ == "CheckConstraint"
            },
            "uniques": {
                constraint.name
                for constraint in table.constraints
                if constraint.__class__.__name__ == "UniqueConstraint"
            },
            "indexes": {index.name for index in table.indexes},
        }
        for table_name, table in ((name, Base.metadata.tables[name]) for name in STAGE7_TABLES)
    }
    for table_name, expected in model_tables.items():
        assert set(expected["columns"]) == {
            column["name"] for column in inspector.get_columns(table_name)
        }
        assert expected["foreign_keys"] == {
            foreign_key["name"] for foreign_key in inspector.get_foreign_keys(table_name)
        }
        assert expected["checks"] == {
            constraint["name"] for constraint in inspector.get_check_constraints(table_name)
        }
        assert expected["uniques"] == {
            constraint["name"] for constraint in inspector.get_unique_constraints(table_name)
        }
        assert expected["indexes"] == {
            index["name"]
            for index in inspector.get_indexes(table_name)
            if index.get("duplicates_constraint") is None
        }


def test_stage7_catalog_has_transition_lineage_and_immutability_guards(
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
                {"tables": list(STAGE7_TABLES)},
            )
            .scalars()
            .all()
        )
    assert EXPECTED_TRIGGERS <= triggers
