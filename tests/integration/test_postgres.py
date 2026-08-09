import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Integer, String, select, text
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Mapped, mapped_column

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.db.base import Base
from stock_research_agent.db.session import (
    check_database,
    create_engine_from_settings,
    create_session_factory,
    session_scope,
)
from stock_research_agent.main import create_app

_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_explicitly_selected() -> bool:
    arguments = [argument.replace("\\", "/").lower() for argument in sys.argv[1:]]
    selected_by_path = any(
        "tests/integration" in argument or "test_postgres.py" in argument for argument in arguments
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


class UtcProbe(Base):
    __tablename__ = "task3_utc_probe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(50), unique=True)
    observed_at: Mapped[datetime]


def _integration_settings() -> Settings:
    assert _TEST_DATABASE_URL is not None
    return Settings(
        _env_file=None,
        app_name="integration-agent",
        app_env=AppEnvironment.TEST,
        api_prefix="/integration-api",
        database_url=_TEST_DATABASE_URL,
    )


@pytest.fixture(scope="module")
def postgres_engine() -> Iterator[Engine]:
    engine = create_engine_from_settings(_integration_settings())
    try:
        yield engine
    finally:
        engine.dispose()


def test_postgresql_17_executes_select_one(postgres_engine: Engine) -> None:
    check_database(postgres_engine)

    with postgres_engine.connect() as connection:
        result = connection.scalar(text("SELECT 1"))
        version_number = int(connection.scalar(text("SHOW server_version_num")))

    assert result == 1
    assert 170_000 <= version_number < 180_000


def test_session_scope_rolls_back_real_transaction(postgres_engine: Engine) -> None:
    table_name = "task3_transaction_probe"
    with postgres_engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        connection.execute(text(f"CREATE TABLE {table_name} (value INTEGER NOT NULL)"))

    factory = create_session_factory(postgres_engine)
    try:
        with pytest.raises(RuntimeError, match="force rollback"):
            with session_scope(factory) as session:
                session.execute(text(f"INSERT INTO {table_name} (value) VALUES (1)"))
                raise RuntimeError("force rollback")

        with postgres_engine.connect() as connection:
            row_count = connection.scalar(text(f"SELECT count(*) FROM {table_name}"))

        assert row_count == 0
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {table_name}"))


def test_session_scope_permanently_closes_real_session(postgres_engine: Engine) -> None:
    factory = create_session_factory(postgres_engine)

    with session_scope(factory) as session:
        assert session.scalar(text("SELECT 1")) == 1

    with pytest.raises(InvalidRequestError, match="permanently closed"):
        session.scalar(text("SELECT 1"))


def test_utc_timestamp_round_trip(postgres_engine: Engine) -> None:
    Base.metadata.drop_all(postgres_engine, tables=[UtcProbe.__table__])
    Base.metadata.create_all(postgres_engine, tables=[UtcProbe.__table__])
    factory = create_session_factory(postgres_engine)
    observed_at = datetime(2026, 7, 13, 8, 30, tzinfo=UTC)

    try:
        with session_scope(factory) as session:
            session.add(UtcProbe(label="round-trip", observed_at=observed_at))
            session.commit()

        with session_scope(factory) as session:
            loaded = session.scalar(select(UtcProbe).where(UtcProbe.label == "round-trip"))
            assert loaded is not None
            assert loaded.observed_at.utcoffset() is not None
            assert loaded.observed_at == observed_at
    finally:
        Base.metadata.drop_all(postgres_engine, tables=[UtcProbe.__table__])


def test_readiness_uses_isolated_postgresql_database() -> None:
    app = create_app(_integration_settings())

    with TestClient(app) as client:
        response = client.get("/integration-api/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "integration-agent",
    }
    assert response.headers["X-Request-ID"]
