from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from typer.testing import CliRunner

from stock_research_agent import cli
from stock_research_agent.config import AppEnvironment, Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
runner = CliRunner()


def _integration_was_explicitly_selected() -> bool:
    arguments = [argument.replace("\\", "/").lower() for argument in sys.argv[1:]]
    return any("tests/integration" in argument for argument in arguments)


if TEST_DATABASE_URL is None and _integration_was_explicitly_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for PostgreSQL integration tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture(scope="module")
def agent_cli_engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["settings"] = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=TEST_DATABASE_URL,
    )
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE TABLE research_policies, research_requests, "
                    "research_agent_runs CASCADE"
                )
            )
        engine.dispose()


@pytest.fixture
def environment(agent_cli_engine: Engine) -> Iterator[dict[str, str]]:
    assert TEST_DATABASE_URL is not None
    with agent_cli_engine.begin() as connection:
        connection.execute(
            text("TRUNCATE TABLE research_policies, research_requests, research_agent_runs CASCADE")
        )
    yield {"APP_ENV": "test", "DATABASE_URL": TEST_DATABASE_URL}


def test_agent_help_exposes_only_explicit_commands() -> None:
    result = runner.invoke(cli.app, ["agent", "--help"])

    assert result.exit_code == 0
    for command_name in (
        "policy",
        "tools",
        "plan",
        "run",
        "pause",
        "resume",
        "cancel",
        "run-show",
        "plan-show",
        "steps",
        "tool-calls",
        "evidence",
        "claims",
        "package",
        "events",
    ):
        assert command_name in result.stdout
    for forbidden in ("refresh", "ingest", "download", "model"):
        assert forbidden not in result.stdout.lower()


def test_policy_seed_is_idempotent_and_tools_are_read_only(
    environment: dict[str, str],
    agent_cli_engine: Engine,
) -> None:
    first = runner.invoke(cli.app, ["agent", "policy", "seed-v1", "--json"], env=environment)
    second = runner.invoke(cli.app, ["agent", "policy", "seed-v1", "--json"], env=environment)
    tools = runner.invoke(cli.app, ["agent", "tools", "list", "--json"], env=environment)

    assert first.exit_code == second.exit_code == tools.exit_code == 0
    assert json.loads(first.stdout)["created"] is True
    assert json.loads(second.stdout)["created"] is False
    catalog = json.loads(tools.stdout)
    assert catalog["entry_count"] == 22
    assert all(
        entry["permission"] == "READ_ONLY"
        and entry["writes"] is False
        and entry["requires_network"] is False
        for entry in catalog["entries"]
    )
    with agent_cli_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM research_policies")) == 1


def test_plan_and_run_require_explicit_snapshot_type_policy_and_as_of() -> None:
    plan = runner.invoke(cli.app, ["agent", "plan", "MU"])
    run = runner.invoke(cli.app, ["agent", "run", "MU"])
    help_result = runner.invoke(cli.app, ["agent", "plan", "--help"])

    assert plan.exit_code == run.exit_code == 2
    assert help_result.exit_code == 0
    combined = help_result.output
    assert "--snapshot" in combined
    assert "--type" in combined
    assert "--policy" in combined
    assert "--as-of" in combined
    assert "latest" not in combined.lower()


def test_read_commands_return_safe_not_found_without_writes(
    environment: dict[str, str],
    agent_cli_engine: Engine,
) -> None:
    before: dict[str, int] = {}
    with agent_cli_engine.connect() as connection:
        for table in ("research_agent_runs", "research_requests", "research_run_events"):
            before[table] = int(connection.scalar(text(f"SELECT count(*) FROM {table}")) or 0)

    result = runner.invoke(
        cli.app,
        ["agent", "run-show", str(uuid4()), "--json"],
        env=environment,
    )

    assert result.exit_code == 4
    assert result.stdout.strip() == "Research resource not found"
    with agent_cli_engine.connect() as connection:
        after = {
            table: int(connection.scalar(text(f"SELECT count(*) FROM {table}")) or 0)
            for table in before
        }
    assert after == before
