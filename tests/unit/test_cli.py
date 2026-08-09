from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import pytest
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from stock_research_agent import __version__, cli
from stock_research_agent.config import AppEnvironment, Settings

runner = CliRunner()


def test_version_prints_exact_package_version() -> None:
    result = runner.invoke(cli.app, ["version"])

    assert result.exit_code == 0
    assert result.stdout == f"stock-research-agent {__version__}\n"


def test_check_config_reports_success_without_database_credentials() -> None:
    secret = "sentinel-password"

    result = runner.invoke(
        cli.app,
        ["check-config"],
        env={
            "APP_ENV": "test",
            "DATABASE_URL": (
                f"postgresql+psycopg://stock_user:{secret}@localhost/stock_research_test"
            ),
        },
    )

    assert result.exit_code == 0
    assert result.stdout == "Configuration valid\n"
    assert secret not in result.stdout


def test_check_config_returns_nonzero_for_invalid_configuration() -> None:
    result = runner.invoke(
        cli.app,
        ["check-config"],
        env={"APP_ENV": "production", "DATABASE_URL": ""},
    )

    assert result.exit_code == 1
    assert result.stdout == "Configuration invalid\n"
    assert "DATABASE_URL" not in result.stdout


class RecordingEngine:
    def __init__(self) -> None:
        self.dispose_calls = 0

    def dispose(self) -> None:
        self.dispose_calls += 1


def _database_environment(secret: str = "sentinel-password") -> dict[str, str]:
    return {
        "APP_ENV": "test",
        "DATABASE_URL": (f"postgresql+psycopg://stock_user:{secret}@localhost/stock_research_test"),
    }


def test_health_checks_database_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = RecordingEngine()
    checked: list[Engine] = []

    monkeypatch.setattr(
        cli,
        "create_engine_from_settings",
        lambda _settings: cast(Engine, engine),
    )
    monkeypatch.setattr(cli, "check_database", checked.append)

    result = runner.invoke(cli.app, ["health"], env=_database_environment())

    assert result.exit_code == 0
    assert result.stdout == "Health check passed\n"
    assert checked == [engine]
    assert engine.dispose_calls == 1


def test_health_returns_nonzero_and_safe_output_when_database_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sentinel-password"
    engine = RecordingEngine()

    monkeypatch.setattr(
        cli,
        "create_engine_from_settings",
        lambda _settings: cast(Engine, engine),
    )

    def fail_check(_engine: Engine) -> None:
        raise SQLAlchemyError(f"could not connect with password {secret}")

    monkeypatch.setattr(cli, "check_database", fail_check)

    result = runner.invoke(
        cli.app,
        ["health"],
        env=_database_environment(secret),
    )

    assert result.exit_code == 1
    assert result.stdout == "Health check failed\n"
    assert secret not in result.stdout
    assert engine.dispose_calls == 1


def test_health_returns_nonzero_for_missing_database_configuration() -> None:
    result = runner.invoke(cli.app, ["health"])

    assert result.exit_code == 1
    assert result.stdout == "Health check failed\n"


def test_db_upgrade_invokes_alembic_with_project_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Config, str]] = []

    def record_upgrade(config: Config, revision: str) -> None:
        calls.append((config, revision))

    monkeypatch.setattr(cli.alembic_command, "upgrade", record_upgrade)

    result = runner.invoke(
        cli.app,
        ["db-upgrade", "--revision", "head"],
        env=_database_environment(),
    )

    assert result.exit_code == 0
    assert result.stdout == "Database upgrade complete\n"
    assert len(calls) == 1
    config, revision = calls[0]
    assert revision == "head"
    assert config.config_file_name is not None
    assert config.config_file_name.endswith("alembic.ini")
    migration_settings = config.attributes["settings"]
    assert isinstance(migration_settings, Settings)
    assert migration_settings.database_url == _database_environment()["DATABASE_URL"]


def test_db_upgrade_uses_explicit_absolute_alembic_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Config] = []
    config_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    monkeypatch.setattr(
        cli.alembic_command,
        "upgrade",
        lambda config, _revision: calls.append(config),
    )

    result = runner.invoke(
        cli.app,
        ["db-upgrade"],
        env={
            **_database_environment(),
            "STOCK_RESEARCH_ALEMBIC_CONFIG": str(config_path),
        },
    )

    assert result.exit_code == 0
    assert calls[0].config_file_name == str(config_path.resolve())


def test_db_upgrade_rejects_relative_alembic_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoked = False

    def record_upgrade(_config: Config, _revision: str) -> None:
        nonlocal invoked
        invoked = True

    monkeypatch.setattr(cli.alembic_command, "upgrade", record_upgrade)

    result = runner.invoke(
        cli.app,
        ["db-upgrade"],
        env={
            **_database_environment(),
            "STOCK_RESEARCH_ALEMBIC_CONFIG": "relative/alembic.ini",
        },
    )

    assert result.exit_code == 1
    assert result.stdout == "Database upgrade failed\n"
    assert invoked is False


def test_db_downgrade_refuses_production_without_explicit_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoked = False

    def record_downgrade(_config: Config, _revision: str) -> None:
        nonlocal invoked
        invoked = True

    monkeypatch.setattr(cli.alembic_command, "downgrade", record_downgrade)

    result = runner.invoke(
        cli.app,
        ["db-downgrade", "--revision", "-1"],
        env={
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://prod:secret@localhost/production",
        },
    )

    assert result.exit_code == 1
    assert result.stdout == (
        "Production downgrade refused; pass --confirm-production to continue\n"
    )
    assert invoked is False
    assert "secret" not in result.stdout


def test_db_downgrade_normalizes_raw_production_environment_before_guarding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_settings = Settings.model_construct(
        app_env="production",
        database_url="postgresql+psycopg://prod:secret@localhost/production",
    )
    invoked = False

    monkeypatch.setattr(cli, "settings_factory", lambda: raw_settings)

    def record_downgrade(_config: Config, _revision: str) -> None:
        nonlocal invoked
        invoked = True

    monkeypatch.setattr(cli.alembic_command, "downgrade", record_downgrade)

    result = runner.invoke(cli.app, ["db-downgrade"])

    assert result.exit_code == 1
    assert result.stdout == (
        "Production downgrade refused; pass --confirm-production to continue\n"
    )
    assert invoked is False


def test_db_downgrade_passes_guarded_settings_to_alembic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guarded_settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=("postgresql+psycopg://guarded:secret@localhost/guarded_research_test"),
    )
    calls: list[tuple[Config, str]] = []
    monkeypatch.setattr(cli, "settings_factory", lambda: guarded_settings)
    monkeypatch.setattr(
        cli.alembic_command,
        "downgrade",
        lambda config, revision: calls.append((config, revision)),
    )

    result = runner.invoke(
        cli.app,
        ["db-downgrade"],
        env={
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://other:secret@localhost/other",
        },
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    config, revision = calls[0]
    assert revision == "-1"
    migration_settings = config.attributes["settings"]
    assert isinstance(migration_settings, Settings)
    assert migration_settings.database_url == guarded_settings.database_url


def test_db_downgrade_allows_confirmed_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        cli.alembic_command,
        "downgrade",
        lambda _config, revision: calls.append(revision),
    )

    result = runner.invoke(
        cli.app,
        [
            "db-downgrade",
            "--revision",
            "-1",
            "--confirm-production",
        ],
        env={
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://prod:secret@localhost/production",
        },
    )

    assert result.exit_code == 0
    assert result.stdout == "Database downgrade complete\n"
    assert calls == ["-1"]


def test_migration_failure_returns_safe_nonzero_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sentinel-password"

    def fail_upgrade(_config: Config, _revision: str) -> None:
        raise RuntimeError(f"migration failed using {secret}")

    monkeypatch.setattr(cli.alembic_command, "upgrade", fail_upgrade)

    result = runner.invoke(
        cli.app,
        ["db-upgrade"],
        env=_database_environment(secret),
    )

    assert result.exit_code == 1
    assert result.stdout == "Database upgrade failed\n"
    assert secret not in result.stdout


def test_settings_loader_is_injectable(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None, app_env=AppEnvironment.DEVELOPMENT)
    monkeypatch.setattr(cli, "settings_factory", lambda: settings)

    result = runner.invoke(cli.app, ["check-config"])

    assert result.exit_code == 0
    assert result.stdout == "Configuration valid\n"


def test_health_reports_one_safe_failure_when_dispose_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sentinel-dispose-secret"

    class FailingDisposeEngine(RecordingEngine):
        def dispose(self) -> None:
            raise RuntimeError(f"dispose failed with {secret}")

    engine = FailingDisposeEngine()
    monkeypatch.setattr(
        cli,
        "create_engine_from_settings",
        lambda _settings: cast(Engine, engine),
    )
    monkeypatch.setattr(cli, "check_database", lambda _engine: None)

    result = runner.invoke(cli.app, ["health"], env=_database_environment())

    assert result.exit_code == 1
    assert result.stdout == "Health check failed\n"
    assert secret not in result.stdout


def test_health_reports_one_safe_failure_when_check_and_dispose_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sentinel-double-failure"

    class FailingDisposeEngine(RecordingEngine):
        def dispose(self) -> None:
            raise RuntimeError(f"dispose failed with {secret}")

    engine = FailingDisposeEngine()
    monkeypatch.setattr(
        cli,
        "create_engine_from_settings",
        lambda _settings: cast(Engine, engine),
    )

    def fail_check(_engine: Engine) -> None:
        raise SQLAlchemyError(f"check failed with {secret}")

    monkeypatch.setattr(cli, "check_database", fail_check)

    result = runner.invoke(cli.app, ["health"], env=_database_environment())

    assert result.exit_code == 1
    assert result.stdout == "Health check failed\n"
    assert secret not in result.stdout


@pytest.mark.parametrize("command", ["check-config", "health", "db-upgrade", "db-downgrade"])
def test_commands_safely_handle_unexpected_settings_source_failure(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    secret = "sentinel-settings-source-secret"

    def fail_settings_source() -> Settings:
        raise RuntimeError(f"settings source failed with {secret}")

    monkeypatch.setattr(cli, "settings_factory", fail_settings_source)

    result = runner.invoke(cli.app, [command])

    assert result.exit_code == 1
    assert secret not in result.stdout
    assert result.stdout in {
        "Configuration invalid\n",
        "Health check failed\n",
        "Database upgrade failed\n",
        "Database downgrade failed\n",
    }


class RecordingSession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.close_calls += 1


def _patch_security_repository_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[RecordingEngine, RecordingSession]:
    engine = RecordingEngine()
    session = RecordingSession()

    @contextmanager
    def recording_scope(_factory: object) -> Iterator[RecordingSession]:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(
        cli,
        "create_engine_from_settings",
        lambda _settings: cast(Engine, engine),
    )
    monkeypatch.setattr(cli, "create_session_factory", lambda _engine: object())
    monkeypatch.setattr(cli, "session_scope", recording_scope)
    return engine, session


def test_security_repository_context_commits_and_disposes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, session = _patch_security_repository_resources(monkeypatch)
    settings = Settings(_env_file=None, app_env=AppEnvironment.DEVELOPMENT)

    with cli._security_repository(settings, commit_on_success=True):
        pass

    assert session.commit_calls == 1
    assert session.rollback_calls == 0
    assert session.close_calls == 1
    assert engine.dispose_calls == 1


def test_security_repository_context_rolls_back_and_disposes_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, session = _patch_security_repository_resources(monkeypatch)
    settings = Settings(_env_file=None, app_env=AppEnvironment.DEVELOPMENT)

    with pytest.raises(RuntimeError, match="sentinel failure"):
        with cli._security_repository(settings, commit_on_success=True):
            raise RuntimeError("sentinel failure")

    assert session.commit_calls == 0
    assert session.rollback_calls == 1
    assert session.close_calls == 1
    assert engine.dispose_calls == 1
