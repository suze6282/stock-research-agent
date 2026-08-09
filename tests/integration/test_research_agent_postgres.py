from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session

from stock_research_agent.db.models.research_agent import STAGE7_MODEL_TABLES
from stock_research_agent.db.repositories.research_agent import (
    SqlAlchemyResearchAgentRepository,
)
from stock_research_agent.domain.research_agent.policies import ResearchPolicySeedService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_selected() -> bool:
    arguments = [value.replace("\\", "/").lower() for value in sys.argv[1:]]
    return any("tests/integration" in value for value in arguments)


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Stage 7 PostgreSQL tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture(scope="module")
def lifecycle_engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1] == "stock_research_test"
    previous_app_env = os.environ.get("APP_ENV")
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    engine = create_engine(TEST_DATABASE_URL)
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE TABLE research_policies CASCADE"))
        engine.dispose()
        if previous_app_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = previous_app_env
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url


def test_stage7_lifecycle_uses_isolated_postgresql_with_all_prior_stages(
    lifecycle_engine: Engine,
) -> None:
    with lifecycle_engine.connect() as connection:
        identity = connection.execute(
            text(
                "SELECT current_database(), current_setting('server_version_num')::int, "
                "current_schema()"
            )
        ).one()
    assert identity[0] == "stock_research_test"
    assert identity[1] >= 170000
    assert identity[2] == "public"
    tables = set(inspect(lifecycle_engine).get_table_names())
    assert set(STAGE7_MODEL_TABLES) <= tables
    assert {
        "schema_meta",
        "securities",
        "data_snapshots",
        "calculation_runs",
        "document_versions",
        "retrieval_runs",
    } <= tables


def test_research_policy_write_rolls_back_without_schema_or_row_pollution(
    lifecycle_engine: Engine,
) -> None:
    with lifecycle_engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE research_policies CASCADE"))
    before_schemas = set(inspect(lifecycle_engine).get_schema_names())

    session = Session(lifecycle_engine)
    try:
        result = ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        assert result.created is True
        assert session.scalar(text("SELECT count(*) FROM research_policies")) == 1
        session.rollback()
    finally:
        session.close()

    with lifecycle_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM research_policies")) == 0
        connection.rollback()
        assert not connection.in_transaction()
    assert set(inspect(lifecycle_engine).get_schema_names()) == before_schemas


def test_policy_convergence_is_idempotent_in_one_postgresql_transaction(
    lifecycle_engine: Engine,
) -> None:
    with lifecycle_engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE research_policies CASCADE"))
    with Session(lifecycle_engine) as session:
        service = ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session))
        first = service.seed_v1()
        second = service.seed_v1()
        session.commit()
        assert first.created is True
        assert second.created is False
    with lifecycle_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM research_policies")) == 1
