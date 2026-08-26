from __future__ import annotations

import os
import sys
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from typer.testing import CliRunner

from stock_research_agent.cli import app

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
runner = CliRunner()


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


@pytest.fixture(autouse=True)
def clean_sec_rows(engine: Engine) -> Iterator[None]:
    statement = (
        "SELECT id FROM provider_definitions "
        "WHERE code = 'SEC_EDGAR_PUBLIC_V1' AND definition_version = '1.0.0'"
    )
    for _phase in range(2):
        with engine.begin() as connection:
            connection.execute(
                text(f"DELETE FROM provider_policies WHERE provider_definition_id IN ({statement})")
            )
            connection.execute(
                text(
                    "DELETE FROM provider_capabilities "
                    f"WHERE provider_definition_id IN ({statement})"
                )
            )
            connection.execute(
                text(
                    "DELETE FROM provider_definitions "
                    "WHERE code = 'SEC_EDGAR_PUBLIC_V1' AND definition_version = '1.0.0'"
                )
            )
        if _phase == 0:
            yield


def _invoke(*arguments: str) -> object:
    assert TEST_DATABASE_URL is not None
    return runner.invoke(
        app,
        ["provider", "bootstrap-sec-control-plane", *arguments],
        env={"APP_ENV": "test", "DATABASE_URL": TEST_DATABASE_URL},
    )


def _counts(engine: Engine) -> tuple[int, int, int]:
    with engine.connect() as connection:
        definition = connection.scalar(
            text("SELECT count(*) FROM provider_definitions WHERE code = 'SEC_EDGAR_PUBLIC_V1'")
        )
        capability = connection.scalar(
            text(
                "SELECT count(*) FROM provider_capabilities c JOIN provider_definitions d "
                "ON d.id = c.provider_definition_id WHERE d.code = 'SEC_EDGAR_PUBLIC_V1'"
            )
        )
        policy = connection.scalar(
            text(
                "SELECT count(*) FROM provider_policies p JOIN provider_definitions d "
                "ON d.id = p.provider_definition_id WHERE d.code = 'SEC_EDGAR_PUBLIC_V1'"
            )
        )
    return definition, capability, policy


def test_sec_bootstrap_cli_dry_run_writes_nothing(engine: Engine) -> None:
    result = _invoke("--dry-run", "--json")

    assert result.exit_code == 0
    assert _counts(engine) == (0, 0, 0)


def test_sec_bootstrap_cli_reports_created(engine: Engine) -> None:
    result = _invoke("--confirm", "--json")

    assert result.exit_code == 0
    assert '"status":"CREATED"' in result.stdout.replace(" ", "")
    assert _counts(engine) == (1, 1, 1)


def test_sec_bootstrap_cli_reports_reused(engine: Engine) -> None:
    first = _invoke("--confirm", "--json")
    second = _invoke("--confirm", "--json")

    assert first.exit_code == second.exit_code == 0
    assert '"status":"REUSED"' in second.stdout.replace(" ", "")
    assert _counts(engine) == (1, 1, 1)


def test_sec_bootstrap_cli_creates_no_freeze_authorization_or_execution_rows(
    engine: Engine,
) -> None:
    tables = (
        "provider_credential_references",
        "provider_license_policies",
        "provider_sync_requests",
        "provider_sync_plans",
        "live_authorization_grants",
        "live_execution_approvals",
        "provider_sync_runs",
        "provider_request_attempts",
        "provider_raw_artifacts",
        "provider_live_validation_runs",
    )
    with engine.connect() as connection:
        before = {
            table: connection.scalar(text(f'SELECT count(*) FROM "{table}"')) for table in tables
        }

    result = _invoke("--confirm", "--json")

    with engine.connect() as connection:
        after = {
            table: connection.scalar(text(f'SELECT count(*) FROM "{table}"')) for table in tables
        }
    assert result.exit_code == 0
    assert after == before
