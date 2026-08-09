from datetime import datetime
from typing import Any, cast

import pytest
from sqlalchemy import DateTime
from sqlalchemy.engine import Engine

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.db.base import Base
from stock_research_agent.db.session import (
    check_database,
    create_engine_from_settings,
    create_session_factory,
    session_scope,
)


def _database_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url="postgresql+psycopg://user:password@localhost/isolated_test",
        database_echo=True,
    )


def test_base_maps_datetime_to_timezone_aware_columns() -> None:
    datetime_type = Base.registry.type_annotation_map[datetime]

    assert isinstance(datetime_type, DateTime)
    assert datetime_type.timezone is True


def test_create_engine_is_lazy_and_uses_explicit_settings(monkeypatch: Any) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    engine_sentinel = object()

    def fake_create_engine(url: str, **kwargs: object) -> object:
        calls.append((url, kwargs))
        return engine_sentinel

    monkeypatch.setattr(
        "stock_research_agent.db.session.create_engine",
        fake_create_engine,
    )

    engine = create_engine_from_settings(_database_settings())

    assert engine is engine_sentinel
    assert calls == [
        (
            "postgresql+psycopg://user:password@localhost/isolated_test",
            {
                "connect_args": {"connect_timeout": 5},
                "echo": True,
                "pool_pre_ping": True,
            },
        )
    ]


def test_create_engine_preserves_explicit_connection_timeout(monkeypatch: Any) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_create_engine(url: str, **kwargs: object) -> object:
        calls.append((url, kwargs))
        return object()

    monkeypatch.setattr(
        "stock_research_agent.db.session.create_engine",
        fake_create_engine,
    )
    settings = _database_settings().model_copy(
        update={
            "database_url": (
                "postgresql+psycopg://user:password@localhost/isolated_test?connect_timeout=2"
            )
        }
    )

    create_engine_from_settings(settings)

    assert calls == [
        (
            "postgresql+psycopg://user:password@localhost/isolated_test?connect_timeout=2",
            {"echo": True, "pool_pre_ping": True},
        )
    ]


def test_create_engine_requires_database_url() -> None:
    settings = Settings(_env_file=None, app_env=AppEnvironment.DEVELOPMENT)

    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        create_engine_from_settings(settings)


class RecordingSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closes += 1


def _recording_factory(session: RecordingSession) -> Any:
    def factory() -> RecordingSession:
        return session

    return factory


def test_session_scope_does_not_commit_and_closes_on_success() -> None:
    session = RecordingSession()

    with session_scope(_recording_factory(session)) as yielded:
        assert yielded is session

    assert session.commits == 0
    assert session.rollbacks == 0
    assert session.closes == 1


def test_session_scope_rolls_back_and_closes_on_exception() -> None:
    session = RecordingSession()

    with pytest.raises(RuntimeError, match="transaction failed"):
        with session_scope(_recording_factory(session)):
            raise RuntimeError("transaction failed")

    assert session.commits == 0
    assert session.rollbacks == 1
    assert session.closes == 1


def test_create_session_factory_has_safe_lifecycle_defaults() -> None:
    engine = cast(Engine, object())

    factory = create_session_factory(engine)

    assert factory.kw["bind"] is engine
    assert factory.kw["autoflush"] is False
    assert factory.kw["expire_on_commit"] is False
    assert factory.kw["close_resets_only"] is False


class RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.exited = False

    def __enter__(self) -> "RecordingConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        self.exited = True

    def execute(self, statement: object) -> None:
        self.statements.append(str(statement))


class RecordingEngine:
    def __init__(self) -> None:
        self.connection = RecordingConnection()

    def connect(self) -> RecordingConnection:
        return self.connection


def test_check_database_executes_select_one_and_closes_connection() -> None:
    engine = RecordingEngine()

    check_database(cast(Engine, engine))

    assert engine.connection.statements == ["SELECT 1"]
    assert engine.connection.exited is True
