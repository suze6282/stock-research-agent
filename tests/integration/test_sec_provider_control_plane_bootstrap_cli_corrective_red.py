from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from stock_research_agent.cli import app
from stock_research_agent.db.repositories.providers import SqlAlchemyProviderDefinitionRepository
from stock_research_agent.providers.sec_edgar.bootstrap import (
    SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
runner = CliRunner()
CONFLICT_CODE = "SEC_PROVIDER_BOOTSTRAP_DEFINITION_CONFLICT"


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for SEC Provider bootstrap CLI tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    os.environ["APP_ENV"] = "test"
    command.upgrade(Config("alembic.ini"), "head")
    value = create_engine(TEST_DATABASE_URL)
    with value.connect() as connection:
        assert connection.scalar(text("SELECT current_database()")) != "stock_research"
    yield value
    value.dispose()


def _delete_bootstrap_rows(engine: Engine) -> None:
    identity = "SELECT id FROM provider_definitions WHERE code = 'SEC_EDGAR_PUBLIC_V1'"
    with engine.begin() as connection:
        connection.execute(
            text(f"DELETE FROM provider_policies WHERE provider_definition_id IN ({identity})")
        )
        connection.execute(
            text(f"DELETE FROM provider_capabilities WHERE provider_definition_id IN ({identity})")
        )
        connection.execute(
            text("DELETE FROM provider_definitions WHERE code = 'SEC_EDGAR_PUBLIC_V1'")
        )


@pytest.fixture(autouse=True)
def conflicting_definition(engine: Engine) -> Iterator[None]:
    _delete_bootstrap_rows(engine)
    conflict = SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP.definition.model_copy(
        update={"display_name": "Conflicting SEC Provider"}
    )
    with Session(engine) as session, session.begin():
        SqlAlchemyProviderDefinitionRepository(session).add_definition(conflict)
    yield
    _delete_bootstrap_rows(engine)


def _invoke(*arguments: str) -> object:
    assert TEST_DATABASE_URL is not None
    return runner.invoke(
        app,
        ["provider", "bootstrap-sec-control-plane", *arguments],
        env={"APP_ENV": "test", "DATABASE_URL": TEST_DATABASE_URL},
    )


def _assert_conflict_preserved(engine: Engine) -> None:
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM provider_definitions WHERE code = 'SEC_EDGAR_PUBLIC_V1'")
            )
            == 1
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM provider_capabilities c "
                    "JOIN provider_definitions d ON d.id = c.provider_definition_id "
                    "WHERE d.code = 'SEC_EDGAR_PUBLIC_V1'"
                )
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM provider_policies p "
                    "JOIN provider_definitions d ON d.id = p.provider_definition_id "
                    "WHERE d.code = 'SEC_EDGAR_PUBLIC_V1'"
                )
            )
            == 0
        )


def test_red_bootstrap_corr_001_plain_cli_conflict_is_structured(engine: Engine) -> None:
    result = _invoke("--confirm")

    assert result.exit_code != 0
    assert "status: CONFLICT" in result.stdout
    assert f"code: {CONFLICT_CODE}" in result.stdout
    assert result.stdout.count(CONFLICT_CODE) == 1
    assert "traceback" not in result.stdout.casefold()
    _assert_conflict_preserved(engine)


def test_red_bootstrap_corr_008_json_cli_conflict_is_structured(engine: Engine) -> None:
    result = _invoke("--confirm", "--json")

    assert result.exit_code != 0
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail("CLI conflict output must be structured JSON", pytrace=False)
    assert payload["status"] == "CONFLICT"
    assert payload["code"] == CONFLICT_CODE
    assert set(payload).isdisjoint({"database_url", "password", "sql", "credential"})
    _assert_conflict_preserved(engine)
