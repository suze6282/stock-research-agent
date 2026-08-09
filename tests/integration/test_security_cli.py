from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from typer.testing import CliRunner

from stock_research_agent import cli
from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_ISSUER_ID,
    INDUSTRIAL_FII_SECURITY_ID,
    MICRON_SECURITY_ID,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TRUNCATE_SQL = text(
    "TRUNCATE TABLE security_aliases, security_identifiers, securities, "
    "issuer_identifiers, issuers, exchange_aliases, exchanges, markets CASCADE"
)
runner = CliRunner()


def _integration_was_explicitly_selected() -> bool:
    arguments = [argument.replace("\\", "/").lower() for argument in sys.argv[1:]]
    return any("tests/integration" in argument for argument in arguments) or any(
        argument == "integration" and index > 0 and arguments[index - 1] == "-m"
        for index, argument in enumerate(arguments)
    )


if TEST_DATABASE_URL is None and _integration_was_explicitly_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for PostgreSQL integration tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture(scope="module")
def cli_engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=TEST_DATABASE_URL,
    )
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    previous_app_env = os.environ.get("APP_ENV")
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(TRUNCATE_SQL)
        engine.dispose()
        if previous_app_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = previous_app_env
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url


def _cli_environment() -> dict[str, str]:
    assert TEST_DATABASE_URL is not None
    return {
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DATABASE_URL,
    }


@pytest.fixture
def seeded_cli(cli_engine: Engine) -> Iterator[dict[str, str]]:
    with cli_engine.begin() as connection:
        connection.execute(TRUNCATE_SQL)
    environment = _cli_environment()
    seed = runner.invoke(cli.app, ["securities", "seed-v0"], env=environment)
    assert seed.exit_code == 0, seed.stdout
    try:
        yield environment
    finally:
        with cli_engine.begin() as connection:
            connection.execute(TRUNCATE_SQL)


def test_seed_v0_is_idempotent(cli_engine: Engine) -> None:
    with cli_engine.begin() as connection:
        connection.execute(TRUNCATE_SQL)
    environment = _cli_environment()

    first = runner.invoke(cli.app, ["securities", "seed-v0"], env=environment)
    second = runner.invoke(cli.app, ["securities", "seed-v0"], env=environment)

    assert first.exit_code == 0
    assert "inserted=21" in first.stdout
    assert "existing=0" in first.stdout
    assert second.exit_code == 0
    assert "inserted=0" in second.stdout
    assert "existing=21" in second.stdout


@pytest.mark.parametrize(
    ("query", "symbol"),
    [
        ("601138", "601138"),
        ("工业富联", "601138"),
        ("MU", "MU"),
        ("Micron Technology", "MU"),
    ],
)
def test_resolve_human_output(
    seeded_cli: dict[str, str],
    query: str,
    symbol: str,
) -> None:
    result = runner.invoke(
        cli.app,
        ["securities", "resolve", query],
        env=seeded_cli,
    )

    assert result.exit_code == 0
    assert "Status: RESOLVED" in result.stdout
    assert symbol in result.stdout


def test_resolve_json_output_is_stable_domain_schema(seeded_cli: dict[str, str]) -> None:
    result = runner.invoke(
        cli.app,
        ["securities", "resolve", "MU", "--json"],
        env=seeded_cli,
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "RESOLVED"
    assert payload["match_type"] == "EXACT_SYMBOL"
    assert payload["candidates"][0]["security_id"] == str(MICRON_SECURITY_ID)
    assert "confidence" not in payload


def test_ambiguous_lists_candidates_and_uses_exit_two(
    seeded_cli: dict[str, str],
    cli_engine: Engine,
) -> None:
    with cli_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO security_aliases "
                "(id, security_id, alias, normalized_alias, alias_type, source_name, "
                "is_active) VALUES (:id, :security_id, 'Micron', 'MICRON', "
                "'FORMER_NAME', 'cli integration test', true)"
            ),
            {
                "id": UUID("98000000-0000-0000-0000-000000000001"),
                "security_id": INDUSTRIAL_FII_SECURITY_ID,
            },
        )

    result = runner.invoke(
        cli.app,
        ["securities", "resolve", "Micron"],
        env=seeded_cli,
    )

    assert result.exit_code == 2
    assert "Status: AMBIGUOUS" in result.stdout
    assert "601138" in result.stdout
    assert "MU" in result.stdout


def test_not_found_and_invalid_query_use_nonzero_exit_codes(
    seeded_cli: dict[str, str],
) -> None:
    missing = runner.invoke(
        cli.app,
        ["securities", "resolve", "Definitely Missing"],
        env=seeded_cli,
    )
    invalid = runner.invoke(
        cli.app,
        ["securities", "resolve", "..."],
        env=seeded_cli,
    )

    assert missing.exit_code == 3
    assert "Status: NOT_FOUND" in missing.stdout
    assert invalid.exit_code == 4
    assert "Status: INVALID_QUERY" in invalid.stdout


def test_show_security_human_and_json(seeded_cli: dict[str, str]) -> None:
    human = runner.invoke(
        cli.app,
        ["securities", "show", str(MICRON_SECURITY_ID)],
        env=seeded_cli,
    )
    json_result = runner.invoke(
        cli.app,
        ["securities", "show", str(MICRON_SECURITY_ID), "--json"],
        env=seeded_cli,
    )

    assert human.exit_code == 0
    assert "Security: Micron Technology" in human.stdout
    assert "Symbol: MU" in human.stdout
    assert json_result.exit_code == 0
    assert json.loads(json_result.stdout)["security"]["id"] == str(MICRON_SECURITY_ID)


def test_show_missing_security_uses_not_found_exit(seeded_cli: dict[str, str]) -> None:
    result = runner.invoke(
        cli.app,
        ["securities", "show", "ffffffff-ffff-ffff-ffff-ffffffffffff"],
        env=seeded_cli,
    )

    assert result.exit_code == 3
    assert result.stdout == "Security not found\n"


def test_seed_conflict_fails_without_overwriting_user_change(
    seeded_cli: dict[str, str],
    cli_engine: Engine,
) -> None:
    with cli_engine.begin() as connection:
        connection.execute(text("DELETE FROM exchange_aliases WHERE normalized_alias = 'SH'"))
        connection.execute(
            text("UPDATE issuers SET display_name = 'User Managed Name' WHERE id = :id"),
            {"id": INDUSTRIAL_FII_ISSUER_ID},
        )

    result = runner.invoke(cli.app, ["securities", "seed-v0"], env=seeded_cli)

    assert result.exit_code == 1
    assert result.stdout == "Security seed failed\n"
    with cli_engine.connect() as connection:
        display_name = connection.scalar(
            text("SELECT display_name FROM issuers WHERE id = :id"),
            {"id": INDUSTRIAL_FII_ISSUER_ID},
        )
        restored_alias_count = connection.scalar(
            text("SELECT count(*) FROM exchange_aliases WHERE normalized_alias = 'SH'")
        )
    assert display_name == "User Managed Name"
    assert restored_alias_count == 0


def test_installed_entry_smoke_uses_isolated_postgres(
    seeded_cli: dict[str, str],
) -> None:
    executable_name = "stock-research.exe" if sys.platform == "win32" else "stock-research"
    executable = Path(sys.executable).with_name(executable_name)
    assert executable.is_file()
    environment = {**os.environ, **seeded_cli}

    commands = (
        ("securities", "--help"),
        ("securities", "seed-v0"),
        ("securities", "resolve", "MU", "--json"),
        ("securities", "show", str(MICRON_SECURITY_ID), "--json"),
    )
    results = [
        subprocess.run(
            [str(executable), *arguments],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        for arguments in commands
    ]

    assert [result.returncode for result in results] == [0, 0, 0, 0]
    assert "seed-v0" in results[0].stdout
    assert "inserted=0" in results[1].stdout
    assert json.loads(results[2].stdout)["status"] == "RESOLVED"
    assert json.loads(results[3].stdout)["security"]["id"] == str(MICRON_SECURITY_ID)


def test_security_cli_help_lists_only_stage_three_commands() -> None:
    result = runner.invoke(cli.app, ["securities", "--help"])

    assert result.exit_code == 0
    assert "seed-v0" in result.stdout
    assert "resolve" in result.stdout
    assert "show" in result.stdout
    for forbidden in ("rag", "agent", "mcp", "trade"):
        assert forbidden not in result.stdout.lower()


def test_security_cli_safe_failure_does_not_leak_database_url() -> None:
    secret = "cli-database-secret"
    environment = {
        "APP_ENV": "test",
        "DATABASE_URL": (f"postgresql+psycopg://stock_user:{secret}@127.0.0.1:1/unavailable_test"),
    }

    result = runner.invoke(
        cli.app,
        ["securities", "resolve", "MU"],
        env=environment,
    )

    assert result.exit_code == 1
    assert result.stdout == "Security resolution failed\n"
    assert secret not in result.stdout
