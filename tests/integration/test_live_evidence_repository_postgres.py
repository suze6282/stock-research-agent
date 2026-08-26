from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from stock_research_agent.db.models.live_evidence import (
    STAGE10_MODEL_TABLES,
    LiveAuthorizationEvent,
    LiveAuthorizationGrant,
)
from stock_research_agent.db.repositories.live_evidence import (
    SqlAlchemyLiveEvidenceQueryRepository,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def _selected() -> bool:
    return any("tests/integration" in item.replace("\\", "/") for item in sys.argv[1:])


if TEST_DATABASE_URL is None and _selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


def test_stage10_repository_constraints_rollback_and_immutability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1] == "stock_research_test"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    engine = create_engine(TEST_DATABASE_URL)
    grant_id = UUID("a1000000-0000-4000-8000-000000000001")
    event_id = UUID("a1000000-0000-4000-8000-000000000002")
    try:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE TABLE live_authorization_grants CASCADE"))
        with Session(engine) as session:
            session.add(
                LiveAuthorizationGrant(
                    id=grant_id,
                    status="ACTIVE",
                    request_limit=1,
                    byte_limit=1024,
                    canonical_checksum="a" * 64,
                    scope={"marker": "SYNTHETIC_TEST_ONLY"},
                    expires_at=NOW + timedelta(minutes=10),
                )
            )
            session.flush()
            session.add(
                LiveAuthorizationEvent(
                    id=event_id,
                    authorization_id=grant_id,
                    sequence=1,
                    event_type="APPROVE",
                )
            )
            session.commit()

            view = SqlAlchemyLiveEvidenceQueryRepository(session).query_view(
                "get_live_authorization", grant_id, limit=1, offset=0
            )
            assert view is not None and view["id"] == str(grant_id)
            with pytest.raises(IntegrityError):
                session.execute(
                    text("UPDATE live_authorization_events SET event_type='REVOKE' WHERE id=:id"),
                    {"id": event_id},
                )
                session.commit()
            session.rollback()
            assert session.get(LiveAuthorizationEvent, event_id).event_type == "APPROVE"

        inspector = inspect(engine)
        assert set(STAGE10_MODEL_TABLES) <= set(inspector.get_table_names())
        assert inspector.get_indexes("live_incidents")
        assert inspector.get_unique_constraints("live_incident_events")
    finally:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE TABLE live_authorization_grants CASCADE"))
        engine.dispose()
