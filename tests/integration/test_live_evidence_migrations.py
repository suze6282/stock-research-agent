from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from stock_research_agent.db.models.live_evidence import STAGE10_MODEL_TABLES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _selected() -> bool:
    return any("tests/integration" in item.replace("\\", "/") for item in sys.argv[1:])


if TEST_DATABASE_URL is None and _selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Stage 10 migration tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


def test_stage10_upgrade_downgrade_upgrade_preserves_prior_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1] == "stock_research_test"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    engine = create_engine(TEST_DATABASE_URL)
    try:
        command.downgrade(config, "0008_production_providers")
        before = set(inspect(engine).get_table_names())
        assert set(STAGE10_MODEL_TABLES).isdisjoint(before)
        assert "data_snapshots" in before
        assert "research_reports" in before

        command.upgrade(config, "0010_partial_request")
        after = set(inspect(engine).get_table_names())
        assert set(STAGE10_MODEL_TABLES) <= after
        raw_columns = {item["name"] for item in inspect(engine).get_columns("raw_payloads")}
        assert "manual_evidence_import_request_id" in raw_columns
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0010_partial_request"
            )

        command.downgrade(config, "0008_production_providers")
        assert set(STAGE10_MODEL_TABLES).isdisjoint(set(inspect(engine).get_table_names()))
        command.upgrade(config, "0010_partial_request")
        assert set(STAGE10_MODEL_TABLES) <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
