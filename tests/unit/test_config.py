import math
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from stock_research_agent import __version__
from stock_research_agent.config import AppEnvironment, Settings


def test_package_version() -> None:
    assert __version__ == "0.1.0"


def test_development_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "stock-research-agent"
    assert settings.app_env is AppEnvironment.DEVELOPMENT
    assert settings.app_debug is False
    assert settings.app_host == "127.0.0.1"
    assert settings.app_port == 8000
    assert settings.log_level == "INFO"
    assert settings.database_url is None
    assert settings.database_echo is False
    assert settings.api_prefix == "/api/v1"
    assert settings.blob_storage_root.is_absolute()


def test_provider_http_defaults_are_offline_and_bounded() -> None:
    settings = Settings(_env_file=None)

    assert settings.provider_network_enabled is False
    assert settings.provider_connect_timeout_seconds == 5.0
    assert settings.provider_read_timeout_seconds == 15.0
    assert settings.provider_total_timeout_seconds == 30.0
    assert settings.provider_max_response_bytes == 5_242_880
    assert settings.provider_max_redirects == 3
    assert settings.provider_max_attempts == 3
    assert settings.provider_retry_base_delay_seconds == 0.25
    assert settings.provider_rate_limit_per_second == 1.0
    assert settings.provider_user_agent == "stock-research-agent/0.1 (offline-default)"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        (field_name, value)
        for field_name in (
            "provider_connect_timeout_seconds",
            "provider_read_timeout_seconds",
            "provider_total_timeout_seconds",
            "provider_retry_base_delay_seconds",
            "provider_rate_limit_per_second",
        )
        for value in (0.0, -1.0, math.inf, math.nan)
    ],
)
def test_provider_time_and_rate_settings_must_be_positive_and_finite(
    field_name: str,
    value: float,
) -> None:
    with pytest.raises(ValidationError, match="positive and finite"):
        Settings(_env_file=None, **{field_name: value})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("provider_max_response_bytes", 0),
        ("provider_max_response_bytes", 52_428_801),
        ("provider_max_redirects", -1),
        ("provider_max_redirects", 6),
        ("provider_max_attempts", 0),
        ("provider_max_attempts", 4),
    ],
)
def test_provider_count_and_size_settings_enforce_exact_ranges(
    field_name: str,
    value: int,
) -> None:
    with pytest.raises(ValidationError, match="must be between"):
        Settings(_env_file=None, **{field_name: value})


@pytest.mark.parametrize(
    "user_agent",
    ["", "x" * 257, "agent\nvalue", "agent\rvalue", "agent\tvalue", "agent\x00", "agent\x7f"],
)
def test_provider_user_agent_enforces_length_and_rejects_controls(
    user_agent: str,
) -> None:
    with pytest.raises(ValidationError, match="USER_AGENT"):
        Settings(_env_file=None, provider_user_agent=user_agent)


def test_environment_variable_names_are_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("app_name", "configured-agent")
    monkeypatch.setenv("app_env", "test")
    monkeypatch.setenv("app_debug", "true")
    monkeypatch.setenv("app_host", "0.0.0.0")
    monkeypatch.setenv("app_port", "9000")
    monkeypatch.setenv("log_level", "DEBUG")
    monkeypatch.setenv("database_echo", "true")
    monkeypatch.setenv("api_prefix", "/configured")

    settings = Settings(_env_file=None)

    assert settings.app_name == "configured-agent"
    assert settings.app_env is AppEnvironment.TEST
    assert settings.app_debug is True
    assert settings.app_host == "0.0.0.0"
    assert settings.app_port == 9000
    assert settings.log_level == "DEBUG"
    assert settings.database_echo is True
    assert settings.api_prefix == "/configured"


def test_invalid_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="staging")  # type: ignore[arg-type]


@pytest.mark.parametrize("port", [0, 65_536])
def test_port_outside_valid_range_is_rejected(port: int) -> None:
    with pytest.raises(ValidationError, match="APP_PORT must be between 1 and 65535"):
        Settings(_env_file=None, app_port=port)


def test_production_requires_database_url() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL is required in production"):
        Settings(_env_file=None, app_env=AppEnvironment.PRODUCTION)


def test_database_url_rejects_drivername_with_postgresql_prefix() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL uses an unsupported driver"):
        Settings(
            _env_file=None,
            app_env=AppEnvironment.PRODUCTION,
            database_url="postgresqlnotreally://analyst@db.example.com/stocks",
        )


def test_test_environment_rejects_production_database_name() -> None:
    with pytest.raises(
        ValidationError,
        match="Test DATABASE_URL database name must end with '_test'",
    ):
        Settings(
            _env_file=None,
            app_env=AppEnvironment.TEST,
            database_url="postgresql+psycopg://analyst:secret@db.example.com:5432/stocks",
        )


def test_safe_summary_redacts_database_password() -> None:
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.PRODUCTION,
        database_url="postgresql+psycopg://analyst:super-secret@db.example.com:5432/stocks",
    )

    summary = settings.safe_summary()
    rendered_summary = repr(summary)

    assert summary == {
        "app_name": "stock-research-agent",
        "app_env": "production",
        "app_debug": False,
        "app_host": "127.0.0.1",
        "app_port": 8000,
        "log_level": "INFO",
        "database_url": "postgresql+psycopg://analyst:***@db.example.com:5432/stocks",
        "database_echo": False,
        "api_prefix": "/api/v1",
        "provider_network_enabled": False,
        "provider_network_mode": "OFFLINE",
        "provider_connect_timeout_seconds": 5.0,
        "provider_read_timeout_seconds": 15.0,
        "provider_total_timeout_seconds": 30.0,
        "provider_max_response_bytes": 5_242_880,
        "provider_max_redirects": 3,
        "provider_max_attempts": 3,
        "provider_retry_base_delay_seconds": 0.25,
        "provider_rate_limit_per_second": 1.0,
        "provider_user_agent": "stock-research-agent/0.1 (offline-default)",
        "blob_storage_root": "<configured>",
        "document_max_bytes": 10_000_000,
        "document_max_pdf_pages": 500,
        "document_max_characters": 5_000_000,
        "rag_query_max_characters": 256,
        "rag_max_results": 20,
        "rag_production_embedding_enabled": False,
    }
    assert "super-secret" not in rendered_summary
    assert "SecretStr(" not in rendered_summary
    assert str(settings.blob_storage_root) not in rendered_summary


@pytest.mark.parametrize("root", [Path("relative/blobs"), Path(Path.cwd().anchor)])
def test_blob_storage_root_rejects_relative_and_filesystem_root(root: Path) -> None:
    with pytest.raises(ValidationError, match="BLOB_STORAGE_ROOT"):
        Settings(_env_file=None, blob_storage_root=root)


def test_safe_summary_redacts_password_query_parameter() -> None:
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.PRODUCTION,
        database_url=("postgresql+psycopg://analyst@db.example.com/stocks?password=super-secret"),
    )

    summary_url = str(settings.safe_summary()["database_url"])

    assert "super-secret" not in summary_url
    assert make_url(summary_url).query["password"] == "***"


def test_safe_summary_redacts_unknown_query_parameter_value() -> None:
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.PRODUCTION,
        database_url=(
            "postgresql+psycopg://analyst@db.example.com/stocks?sslpassword=super-secret"
        ),
    )

    summary_url = str(settings.safe_summary()["database_url"])

    assert "super-secret" not in summary_url
    assert make_url(summary_url).query["sslpassword"] == "***"


@pytest.mark.parametrize("sensitive_key", ["token", "secret", "api_key"])
def test_safe_summary_redacts_all_query_values_while_preserving_keys(
    sensitive_key: str,
) -> None:
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.PRODUCTION,
        database_url=(
            "postgresql+psycopg://analyst@db.example.com/stocks"
            f"?{sensitive_key}=super-secret&sslmode=require"
        ),
    )

    summary_url = str(settings.safe_summary()["database_url"])
    summary_query = make_url(summary_url).query

    assert "super-secret" not in summary_url
    assert summary_query[sensitive_key] == "***"
    assert summary_query["sslmode"] == "***"


def test_safe_summary_preserves_repeated_query_parameter_structure() -> None:
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.PRODUCTION,
        database_url=(
            "postgresql+psycopg://analyst@db.example.com/stocks?sslmode=require&sslmode=verify-full"
        ),
    )

    summary_url = str(settings.safe_summary()["database_url"])

    assert make_url(summary_url).query["sslmode"] == ("***", "***")


def test_stage6_parser_and_retrieval_limits_are_bounded_offline_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.document_max_bytes == 10_000_000
    assert settings.document_max_pdf_pages == 500
    assert settings.document_max_characters == 5_000_000
    assert settings.rag_query_max_characters == 256
    assert settings.rag_max_results == 20
    assert settings.rag_production_embedding_enabled is False

    with pytest.raises(ValidationError):
        Settings(_env_file=None, rag_max_results=21)
