import importlib
import json
from typing import Any

import psycopg
import pytest
import sqlalchemy
import structlog
from fastapi import Request
from fastapi.testclient import TestClient

from stock_research_agent import __version__
from stock_research_agent.api.errors import ApiError
from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.main import create_app


def _test_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_name="test-agent",
        app_env=AppEnvironment.TEST,
        api_prefix="/test-api",
    )


def test_create_app_configures_metadata_and_api_prefix() -> None:
    app = create_app(_test_settings())
    client = TestClient(app)

    assert app.title == "test-agent"
    assert app.version == __version__
    assert client.get("/test-api/health/live").status_code == 200
    assert client.get("/api/v1/health/live").status_code == 404


def test_main_import_does_not_connect_to_database(monkeypatch: Any) -> None:
    def reject_connection(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("application import attempted a database connection")

    monkeypatch.setattr(sqlalchemy, "create_engine", reject_connection)
    monkeypatch.setattr(psycopg, "connect", reject_connection)

    import stock_research_agent.main as main_module

    reloaded = importlib.reload(main_module)

    assert reloaded.app.title == Settings(_env_file=None).app_name


def test_request_id_is_stored_on_request_state_and_propagated() -> None:
    app = create_app(_test_settings())

    @app.get("/request-id")
    def read_request_id(request: Request) -> dict[str, str]:
        return {"request_id": request.state.request_id}

    response = TestClient(app).get(
        "/request-id",
        headers={"X-Request-ID": "caller-request-id"},
    )

    assert response.status_code == 200
    assert response.json() == {"request_id": "caller-request-id"}
    assert response.headers["X-Request-ID"] == "caller-request-id"


def test_request_id_is_generated_for_responses_without_one() -> None:
    response = TestClient(create_app(_test_settings())).get("/missing")

    request_id = response.headers["X-Request-ID"]
    assert response.status_code == 404
    assert request_id


def test_successful_request_log_contains_request_id_and_request_context(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(_test_settings())

    response = TestClient(app).get(
        "/test-api/health/live",
        headers={"X-Request-ID": "logged-request-id"},
    )

    assert response.status_code == 200
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert {
        "event": "request_completed",
        "request_id": "logged-request-id",
        "method": "GET",
        "path": "/test-api/health/live",
        "status_code": 200,
    }.items() <= events[-1].items()


def test_request_context_is_available_to_internal_logs_and_cleared_afterward(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(_test_settings())

    @app.get("/internal-log")
    async def internal_log() -> dict[str, str]:
        structlog.get_logger().info("internal_handler_event")
        return {"status": "ok"}

    client = TestClient(app)
    client.get("/internal-log", headers={"X-Request-ID": "first-context-id"})
    client.get("/internal-log", headers={"X-Request-ID": "second-context-id"})
    structlog.get_logger().info("outside_request_event")

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    internal_ids = [
        event.get("request_id")
        for event in events
        if event.get("event") == "internal_handler_event"
    ]
    assert internal_ids == ["first-context-id", "second-context-id"]
    outside = next(event for event in events if event.get("event") == "outside_request_event")
    assert "request_id" not in outside


def test_api_error_uses_uniform_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(_test_settings())

    @app.get("/api-error")
    def raise_api_error() -> None:
        raise ApiError(code="NOT_READY", message="Not ready", status_code=409)

    response = TestClient(app, raise_server_exceptions=False).get("/api-error")

    assert response.status_code == 409
    request_id = response.headers["X-Request-ID"]
    assert response.json() == {
        "error": {
            "code": "NOT_READY",
            "message": "Not ready",
            "request_id": request_id,
        }
    }
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any(
        event.get("event") == "api_request_failed"
        and event.get("request_id") == request_id
        and event.get("error_type") == "ApiError"
        and event.get("code") == "NOT_READY"
        for event in events
    )


def test_validation_error_uses_uniform_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(_test_settings())

    @app.get("/quantities/{quantity}")
    def read_quantity(quantity: int) -> dict[str, int]:
        return {"quantity": quantity}

    response = TestClient(app).get("/quantities/not-an-integer")

    assert response.status_code == 422
    request_id = response.headers["X-Request-ID"]
    assert response.json() == {
        "error": {
            "code": "REQUEST_VALIDATION_ERROR",
            "message": "Request validation failed",
            "request_id": request_id,
        }
    }
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any(
        event.get("event") == "api_request_failed"
        and event.get("request_id") == request_id
        and event.get("error_type") == "RequestValidationError"
        and event.get("code") == "REQUEST_VALIDATION_ERROR"
        for event in events
    )


def test_unknown_error_uses_safe_uniform_envelope() -> None:
    app = create_app(_test_settings())

    @app.get("/explode")
    def explode() -> None:
        raise RuntimeError("unexpected-error-sentinel")

    response = TestClient(app, raise_server_exceptions=False).get("/explode")

    assert response.status_code == 500
    request_id = response.headers["X-Request-ID"]
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "Internal server error",
            "request_id": request_id,
        }
    }
    assert "unexpected-error-sentinel" not in response.text
    assert "Traceback" not in response.text


def test_unknown_error_log_contains_type_and_request_id_but_not_exception_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(_test_settings())

    @app.get("/logged-explode")
    def explode() -> None:
        raise RuntimeError("unexpected-error-log-sentinel")

    response = TestClient(app, raise_server_exceptions=False).get(
        "/logged-explode",
        headers={"X-Request-ID": "failed-request-id"},
    )

    assert response.status_code == 500
    rendered = capsys.readouterr().out
    assert "unexpected-error-log-sentinel" not in rendered
    events = [json.loads(line) for line in rendered.splitlines()]
    assert any(
        event.get("event") == "request_failed"
        and event.get("request_id") == "failed-request-id"
        and event.get("error_type") == "RuntimeError"
        for event in events
    )
    assert any(
        event.get("event") == "request_completed"
        and event.get("request_id") == "failed-request-id"
        and event.get("status_code") == 500
        for event in events
    )


def test_api_error_exposes_only_minimum_fields() -> None:
    error = ApiError(code="CONFLICT", message="Conflict", status_code=409)

    assert sorted(vars(error)) == ["code", "message", "status_code"]
