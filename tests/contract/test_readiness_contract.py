import json
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.main import create_app


def _test_settings(*, database_url: str | None = None) -> Settings:
    return Settings(
        _env_file=None,
        app_name="readiness-agent",
        app_env=AppEnvironment.TEST,
        api_prefix="/contract-api",
        database_url=database_url,
    )


def _request_with_check(
    settings: Settings,
    database_check: Callable[[], None],
):
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.database_check = database_check
        return client.get(
            "/contract-api/health/ready",
            headers={"X-Request-ID": "readiness-request-id"},
        )


def test_readiness_contract_when_database_check_passes() -> None:
    response = _request_with_check(_test_settings(), lambda: None)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "readiness-agent",
    }
    assert response.headers["X-Request-ID"] == "readiness-request-id"


def test_readiness_contract_when_database_check_fails_is_safe(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_url = "postgresql+psycopg://secret-user:secret-password@db/private"

    def fail_database_check() -> None:
        raise SQLAlchemyError(f"could not connect to {secret_url}")

    response = _request_with_check(_test_settings(), fail_database_check)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "DATABASE_UNAVAILABLE",
            "message": "Database is unavailable",
            "request_id": "readiness-request-id",
        }
    }
    assert response.headers["X-Request-ID"] == "readiness-request-id"
    assert "secret-user" not in response.text
    assert "secret-password" not in response.text
    assert secret_url not in response.text
    rendered = capsys.readouterr().out
    assert "secret-user" not in rendered
    assert "secret-password" not in rendered
    assert secret_url not in rendered
    events = [json.loads(line) for line in rendered.splitlines()]
    assert any(
        event.get("event") == "api_request_failed"
        and event.get("request_id") == "readiness-request-id"
        and event.get("error_type") == "SQLAlchemyError"
        and event.get("code") == "DATABASE_UNAVAILABLE"
        for event in events
    )


def test_readiness_contract_when_database_is_not_configured() -> None:
    app = create_app(_test_settings())

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/contract-api/health/ready")

    assert response.status_code == 503
    request_id = response.headers["X-Request-ID"]
    assert response.json() == {
        "error": {
            "code": "DATABASE_UNAVAILABLE",
            "message": "Database is unavailable",
            "request_id": request_id,
        }
    }
    assert request_id
