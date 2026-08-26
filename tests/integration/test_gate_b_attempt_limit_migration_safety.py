from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url

from tests.integration.test_gate_b_attempt_limit_migration_postgres_red import (
    _insert_attempt,
    _seed_gate_b_scenario,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TEST_DATABASE_ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        TEST_DATABASE_URL is None or TEST_DATABASE_ADMIN_URL is None,
        reason="loopback TEST_DATABASE_URL and TEST_DATABASE_ADMIN_URL are required",
    ),
]


def _alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


def _run_migration(database_url: URL, revision: str, *, downgrade: bool = False) -> None:
    previous_app_env = os.environ.get("APP_ENV")
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = database_url.render_as_string(hide_password=False)
    try:
        operation = command.downgrade if downgrade else command.upgrade
        operation(_alembic_config(), revision)
    finally:
        if previous_app_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = previous_app_env
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url


@contextmanager
def _disposable_database() -> Iterator[tuple[Engine, URL]]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_ADMIN_URL is not None
    base_url = make_url(TEST_DATABASE_URL)
    admin_url = make_url(TEST_DATABASE_ADMIN_URL)
    assert base_url.host in {"127.0.0.1", "localhost"}
    assert admin_url.host in {"127.0.0.1", "localhost"}
    assert base_url.port == admin_url.port == 55432
    assert admin_url.database == "postgres"

    database_name = f"stock_research_gate_b_3e_safety_{uuid4().hex}_test"
    assert re.fullmatch(r"stock_research_gate_b_3e_safety_[0-9a-f]{32}_test", database_name)
    database_url = base_url.set(database=database_name)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(
            text(f'CREATE DATABASE "{database_name}" OWNER stock_user TEMPLATE template0')
        )

    engine = create_engine(database_url)
    try:
        yield engine, database_url
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin.dispose()


def _attempt_constraint(engine: Engine) -> str:
    with engine.connect() as connection:
        definition = connection.scalar(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_provider_request_attempts_bounds'"
            )
        )
    assert isinstance(definition, str)
    return definition


def _assert_complete_constraint(definition: str, *, maximum: int) -> None:
    assert "attempt_number >= 1" in definition
    assert f"attempt_number <= {maximum}" in definition
    assert "response_bytes >= 0" in definition
    assert "response_status_code IS NULL" in definition
    assert "response_status_code >= 100" in definition
    assert "response_status_code <= 599" in definition


def test_attempt_capacity_migration_round_trip_without_attempt_four() -> None:
    with _disposable_database() as (engine, database_url):
        _run_migration(database_url, "0012_component_observation_lineage_integrity")
        _assert_complete_constraint(_attempt_constraint(engine), maximum=3)

        _run_migration(database_url, "0013_gate_b_attempt_number_capacity")
        _assert_complete_constraint(_attempt_constraint(engine), maximum=4)

        _run_migration(
            database_url,
            "0012_component_observation_lineage_integrity",
            downgrade=True,
        )
        _assert_complete_constraint(_attempt_constraint(engine), maximum=3)


def test_attempt_capacity_downgrade_refuses_retained_attempt_four() -> None:
    with _disposable_database() as (engine, database_url):
        _run_migration(database_url, "0013_gate_b_attempt_number_capacity")
        scenario = _seed_gate_b_scenario(engine)
        assert _insert_attempt(
            engine,
            scenario.sync_run_id,
            attempt_number=4,
            slice_id="RETAINED_GATE_B_ATTEMPT_FOUR",
        )

        with pytest.raises(RuntimeError, match="GATE_B_ATTEMPT_FOUR_PREVENTS_DOWNGRADE"):
            _run_migration(
                database_url,
                "0012_component_observation_lineage_integrity",
                downgrade=True,
            )

        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM provider_request_attempts")) == 1
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0013_gate_b_attempt_number_capacity"
            )
        _assert_complete_constraint(_attempt_constraint(engine), maximum=4)
