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
COMPONENT_LINEAGE_REVISION = "0011_component_observation_lineage"
COMPONENT_LINEAGE_INTEGRITY_REVISION = "0012_component_observation_lineage_integrity"
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


def test_partial_snapshot_request_trigger_upgrade_downgrade_contract(
    migration_engine: Engine,
) -> None:
    command.upgrade(_config(), "head")
    upgraded = _request_snapshot_function(migration_engine)
    assert "linked_status NOT IN ('COMPLETE', 'PARTIAL')" in upgraded

    command.downgrade(_config(), "0009_controlled_live_evidence")
    downgraded = _request_snapshot_function(migration_engine)
    assert "linked_status <> 'COMPLETE'" in downgraded

    command.upgrade(_config(), "head")
    reupgraded = _request_snapshot_function(migration_engine)
    assert "linked_status NOT IN ('COMPLETE', 'PARTIAL')" in reupgraded


def test_component_observation_lineage_upgrade_downgrade_upgrade_contract(
    migration_engine: Engine,
) -> None:
    """Migration RED: 0010 -> 0011 -> 0010 -> 0011 must be reversible without data."""
    command.upgrade(_config(), "0010_partial_request")
    assert _current_revision(migration_engine) == "0010_partial_request"

    command.upgrade(_config(), COMPONENT_LINEAGE_REVISION)
    assert _current_revision(migration_engine) == COMPONENT_LINEAGE_REVISION
    columns = {
        column["name"]: column
        for column in inspect(migration_engine).get_columns("research_observations")
    }
    assert columns["research_step_id"]["nullable"] is False
    assert columns["invocation_id"]["nullable"] is True
    foreign_keys = {
        item["name"]: item
        for item in inspect(migration_engine).get_foreign_keys("research_observations")
    }
    assert foreign_keys["fk_research_observations_step"]["referred_table"] == "research_steps"
    assert foreign_keys["fk_research_observations_step"]["referred_columns"] == ["id"]
    indexes = {
        item["name"]: item
        for item in inspect(migration_engine).get_indexes("research_observations")
    }
    assert indexes["ux_research_observations_invocation_nonnull"]["unique"] is True
    assert indexes["ux_research_observations_component_step"]["unique"] is True

    command.downgrade(_config(), "0010_partial_request")
    assert _current_revision(migration_engine) == "0010_partial_request"
    downgraded_columns = {
        column["name"]: column
        for column in inspect(migration_engine).get_columns("research_observations")
    }
    assert "research_step_id" not in downgraded_columns
    assert downgraded_columns["invocation_id"]["nullable"] is False
    downgraded_uniques = {
        item["name"]
        for item in inspect(migration_engine).get_unique_constraints("research_observations")
    }
    assert "uq_research_observations_invocation" in downgraded_uniques

    command.upgrade(_config(), COMPONENT_LINEAGE_REVISION)
    assert _current_revision(migration_engine) == COMPONENT_LINEAGE_REVISION


def test_component_observation_integrity_upgrade_downgrade_upgrade_contract(
    migration_engine: Engine,
) -> None:
    command.upgrade(_config(), COMPONENT_LINEAGE_REVISION)
    assert _current_revision(migration_engine) == COMPONENT_LINEAGE_REVISION

    command.upgrade(_config(), COMPONENT_LINEAGE_INTEGRITY_REVISION)
    assert _current_revision(migration_engine) == COMPONENT_LINEAGE_INTEGRITY_REVISION
    assert _observation_lineage_trigger_names(migration_engine) == {
        "trg_research_observations_validate_lineage"
    }

    command.downgrade(_config(), "0010_partial_request")
    assert _current_revision(migration_engine) == "0010_partial_request"
    downgraded_columns = {
        column["name"]: column
        for column in inspect(migration_engine).get_columns("research_observations")
    }
    assert "research_step_id" not in downgraded_columns
    assert downgraded_columns["invocation_id"]["nullable"] is False

    command.upgrade(_config(), COMPONENT_LINEAGE_INTEGRITY_REVISION)
    assert _current_revision(migration_engine) == COMPONENT_LINEAGE_INTEGRITY_REVISION
    assert _observation_lineage_trigger_names(migration_engine) == {
        "trg_research_observations_validate_lineage"
    }
    assert _observation_lineage_function_exists(migration_engine)

    command.downgrade(_config(), COMPONENT_LINEAGE_REVISION)
    assert _current_revision(migration_engine) == COMPONENT_LINEAGE_REVISION
    columns = {
        column["name"]: column
        for column in inspect(migration_engine).get_columns("research_observations")
    }
    assert columns["research_step_id"]["nullable"] is False
    assert columns["invocation_id"]["nullable"] is True
    assert not _observation_lineage_trigger_names(migration_engine)
    assert not _observation_lineage_function_exists(migration_engine)

    command.upgrade(_config(), COMPONENT_LINEAGE_INTEGRITY_REVISION)
    assert _current_revision(migration_engine) == COMPONENT_LINEAGE_INTEGRITY_REVISION
    assert _observation_lineage_trigger_names(migration_engine) == {
        "trg_research_observations_validate_lineage"
    }


def _request_snapshot_function(engine: Engine) -> str:
    with engine.connect() as connection:
        definition = connection.scalar(
            text(
                "SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = current_schema() "
                "AND p.proname = 'stage7_validate_request_snapshot'"
            )
        )
    assert isinstance(definition, str)
    return definition


def _current_revision(engine: Engine) -> str:
    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert isinstance(revision, str)
    return revision


def _observation_lineage_trigger_names(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return set(
            connection.scalars(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE NOT tgisinternal "
                    "AND tgrelid = 'research_observations'::regclass "
                    "AND tgname = 'trg_research_observations_validate_lineage'"
                )
            )
        )


def _observation_lineage_function_exists(engine: Engine) -> bool:
    with engine.connect() as connection:
        return bool(
            connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = current_schema() "
                    "AND p.proname = 'stage7_validate_observation_lineage')"
                )
            )
        )
