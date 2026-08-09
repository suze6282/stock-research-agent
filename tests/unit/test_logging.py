import json

import pytest
import structlog

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.logging import configure_logging, redact_sensitive_data


def test_redact_sensitive_data_removes_nested_secrets() -> None:
    event = {
        "DATABASE_PASSWORD": "database-password-sentinel",
        "nested": {
            "OPENAI_API_KEY": "openai-key-sentinel",
            "items": [
                {"access_token": "token-sentinel"},
                {"Authorization": "Bearer authorization-sentinel"},
            ],
        },
    }

    redacted = redact_sensitive_data(event)
    serialized = json.dumps(redacted)

    for sentinel in (
        "database-password-sentinel",
        "openai-key-sentinel",
        "token-sentinel",
        "authorization-sentinel",
    ):
        assert sentinel not in serialized
    assert redacted == {
        "DATABASE_PASSWORD": "***",
        "nested": {
            "OPENAI_API_KEY": "***",
            "items": [
                {"access_token": "***"},
                {"Authorization": "***"},
            ],
        },
    }


def test_redact_sensitive_data_removes_provider_header_credentials() -> None:
    event = {
        "headers": {
            "X-API-Key": "api-key-sentinel",
            "x-RapidAPI-key": "rapidapi-sentinel",
            "X-Auth-Token": "token-header-sentinel",
            "X-Client-Secret": "secret-header-sentinel",
            "X-Signature": "signature-header-sentinel",
            "Cookie": "session=cookie-header-sentinel",
            "Set-Cookie": "session=set-cookie-header-sentinel",
            "X-Trace": "safe-trace",
        }
    }

    redacted = redact_sensitive_data(event)
    serialized = json.dumps(redacted)

    for sentinel in (
        "api-key-sentinel",
        "rapidapi-sentinel",
        "token-header-sentinel",
        "secret-header-sentinel",
        "signature-header-sentinel",
        "cookie-header-sentinel",
        "set-cookie-header-sentinel",
    ):
        assert sentinel not in serialized
    assert redacted["headers"] == {
        "X-API-Key": "***",
        "x-RapidAPI-key": "***",
        "X-Auth-Token": "***",
        "X-Client-Secret": "***",
        "X-Signature": "***",
        "Cookie": "***",
        "Set-Cookie": "***",
        "X-Trace": "safe-trace",
    }


def test_redact_sensitive_data_removes_postgresql_url_credentials() -> None:
    event = {
        "database_url": (
            "postgresql+psycopg://analyst:postgres-password-sentinel@db.example.com/stocks"
        )
    }

    redacted = redact_sensitive_data(event)
    serialized = json.dumps(redacted)

    assert "postgres-password-sentinel" not in serialized
    assert redacted["database_url"] == ("postgresql+psycopg://analyst:***@db.example.com/stocks")


@pytest.mark.parametrize(
    "scheme",
    ["POSTGRESQL", "PoStGrEsQl+PsYcOpG"],
    ids=["uppercase", "mixed-case-driver"],
)
def test_redact_sensitive_data_handles_case_insensitive_postgresql_schemes(
    scheme: str,
) -> None:
    event = {"database_url": (f"{scheme}://analyst:case-password-sentinel@db.example.com/stocks")}

    redacted = redact_sensitive_data(event)
    serialized = json.dumps(redacted)

    assert "case-password-sentinel" not in serialized
    assert redacted["database_url"] == (f"{scheme}://analyst:***@db.example.com/stocks")


@pytest.mark.parametrize(
    "environment",
    [AppEnvironment.TEST, AppEnvironment.PRODUCTION],
)
def test_configure_logging_emits_json_with_required_context(
    environment: AppEnvironment,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        _env_file=None,
        app_name="logging-test",
        app_env=environment,
        database_url=(
            "postgresql+psycopg://analyst:secret@db.example.com/stocks_test"
            if environment is AppEnvironment.PRODUCTION
            else None
        ),
    )

    configure_logging(settings)
    structlog.get_logger().info("structured event")

    payload = json.loads(capsys.readouterr().out)
    assert payload["event"] == "structured event"
    assert payload["level"] == "info"
    assert payload["service"] == "logging-test"
    assert isinstance(payload["timestamp"], str)
    assert payload["timestamp"]


def test_configure_logging_uses_console_output_in_development(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        _env_file=None,
        app_name="logging-test",
        app_env=AppEnvironment.DEVELOPMENT,
    )

    configure_logging(settings)
    structlog.get_logger().info("development event")

    rendered = capsys.readouterr().out.strip()
    assert not rendered.startswith("{")
    assert "development event" in rendered
    assert "info" in rendered
    assert "service=logging-test" in rendered
