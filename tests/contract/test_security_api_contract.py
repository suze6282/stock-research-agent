from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.db.session import create_session_factory, session_scope
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_ISSUER_ID,
    INDUSTRIAL_FII_SECURITY_ID,
    MICRON_ISSUER_ID,
    MICRON_SECURITY_ID,
    SecurityMasterSeedService,
)
from stock_research_agent.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TRUNCATE_SQL = text(
    "TRUNCATE TABLE security_aliases, security_identifiers, securities, "
    "issuer_identifiers, issuers, exchange_aliases, exchanges, markets CASCADE"
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture(scope="module")
def api_engine() -> Iterator[Engine]:
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


@pytest.fixture
def api_client(api_engine: Engine) -> Iterator[TestClient]:
    assert TEST_DATABASE_URL is not None
    with api_engine.begin() as connection:
        connection.execute(TRUNCATE_SQL)
    factory = create_session_factory(api_engine)
    with session_scope(factory) as session:
        SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
        session.commit()
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=TEST_DATABASE_URL,
        api_prefix="/api/v1",
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client
    with api_engine.begin() as connection:
        connection.execute(TRUNCATE_SQL)


@pytest.mark.parametrize(
    ("query", "symbol"),
    [
        ("601138", "601138"),
        ("工业富联", "601138"),
        ("MU", "MU"),
        ("Micron Technology", "MU"),
    ],
)
def test_resolve_contract_returns_seeded_samples(
    api_client: TestClient,
    query: str,
    symbol: str,
) -> None:
    response = api_client.get(
        "/api/v1/securities/resolve",
        params={"query": query},
        headers={"X-Request-ID": "security-contract-request"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "security-contract-request"
    payload = response.json()
    assert payload["status"] == "RESOLVED"
    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["symbol"] == symbol
    assert set(payload["candidates"][0]) == {
        "security_id",
        "issuer_id",
        "issuer_display_name",
        "security_display_name",
        "symbol",
        "exchange_mic",
        "exchange_name",
        "market_code",
        "currency_code",
        "listing_status",
        "match_reason",
    }
    assert "confidence" not in response.text


def test_resolve_not_found_is_http_200_business_status(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/securities/resolve",
        params={"query": "Definitely Missing"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "NOT_FOUND"
    assert response.json()["candidates"] == []


def test_resolve_shared_alias_is_ambiguous(
    api_client: TestClient,
    api_engine: Engine,
) -> None:
    with api_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO security_aliases "
                "(id, security_id, alias, normalized_alias, alias_type, source_name, "
                "is_active) VALUES (:id, :security_id, 'Micron', 'MICRON', "
                "'FORMER_NAME', 'api contract test', true)"
            ),
            {
                "id": UUID("99000000-0000-0000-0000-000000000001"),
                "security_id": INDUSTRIAL_FII_SECURITY_ID,
            },
        )

    response = api_client.get(
        "/api/v1/securities/resolve",
        params={"query": "Micron"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "AMBIGUOUS"
    assert response.json()["candidate_count"] == 2


@pytest.mark.parametrize(
    "query",
    ["", "   ", "MU\nDROP", "A" * 257],
)
def test_invalid_query_uses_safe_422_contract(
    api_client: TestClient,
    query: str,
) -> None:
    response = api_client.get(
        "/api/v1/securities/resolve",
        params={"query": query},
    )

    assert response.status_code == 422
    payload = response.json()
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message", "request_id"}
    assert response.headers["X-Request-ID"] == payload["error"]["request_id"]
    assert "SELECT" not in response.text
    assert "Traceback" not in response.text


@pytest.mark.parametrize(
    ("path", "expected_id"),
    [
        (f"/api/v1/securities/{INDUSTRIAL_FII_SECURITY_ID}", INDUSTRIAL_FII_SECURITY_ID),
        (f"/api/v1/securities/{MICRON_SECURITY_ID}", MICRON_SECURITY_ID),
    ],
)
def test_security_detail_contains_only_master_data(
    api_client: TestClient,
    path: str,
    expected_id: UUID,
) -> None:
    response = api_client.get(path)

    assert response.status_code == 200
    payload = response.json()
    assert payload["security"]["id"] == str(expected_id)
    rendered_keys = str(payload.keys()).lower() + response.text.lower()
    for forbidden in ("price", "quote", "financial", "valuation", "research"):
        assert forbidden not in rendered_keys


@pytest.mark.parametrize(
    "issuer_id",
    [INDUSTRIAL_FII_ISSUER_ID, MICRON_ISSUER_ID],
)
def test_issuer_detail_contract(api_client: TestClient, issuer_id: UUID) -> None:
    response = api_client.get(f"/api/v1/issuers/{issuer_id}")

    assert response.status_code == 200
    assert response.json()["issuer"]["id"] == str(issuer_id)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/securities/not-a-uuid",
        "/api/v1/issuers/not-a-uuid",
    ],
)
def test_invalid_detail_id_is_safe_422(api_client: TestClient, path: str) -> None:
    response = api_client.get(path)

    assert response.status_code == 422
    assert "UUID" not in response.text
    assert "Traceback" not in response.text


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/securities/ffffffff-ffff-ffff-ffff-ffffffffffff",
        "/api/v1/issuers/ffffffff-ffff-ffff-ffff-ffffffffffff",
    ],
)
def test_missing_detail_is_safe_404(api_client: TestClient, path: str) -> None:
    response = api_client.get(path)

    assert response.status_code == 404
    assert "SELECT" not in response.text
    assert "Traceback" not in response.text


def test_security_routes_are_present_in_openapi(api_client: TestClient) -> None:
    paths = api_client.get("/openapi.json").json()["paths"]

    assert "/api/v1/securities/resolve" in paths
    assert "/api/v1/securities/{security_id}" in paths
    assert "/api/v1/issuers/{issuer_id}" in paths


def test_repeated_resolve_response_body_is_stable(api_client: TestClient) -> None:
    first = api_client.get("/api/v1/securities/resolve", params={"query": "MU"})
    second = api_client.get("/api/v1/securities/resolve", params={"query": "MU"})

    assert first.content == second.content


def test_api_closes_its_request_session(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_close = Session.close
    closed_sessions: list[Session] = []

    def record_close(session: Session) -> None:
        closed_sessions.append(session)
        original_close(session)

    monkeypatch.setattr(Session, "close", record_close)

    response = api_client.get("/api/v1/securities/resolve", params={"query": "MU"})

    assert response.status_code == 200
    assert len(closed_sessions) == 1


def test_security_api_without_database_returns_safe_503() -> None:
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=None,
        api_prefix="/api/v1",
    )

    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.get("/api/v1/securities/resolve", params={"query": "MU"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert "Traceback" not in response.text


def test_database_error_does_not_leak_sql_or_connection_details(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "SELECT secret FROM securities password=sentinel"

    def fail_lookup(
        _repository: SqlAlchemySecurityMasterRepository,
        _normalized_symbol: str,
        _limit: int,
    ) -> tuple[object, ...]:
        raise RuntimeError(sentinel)

    monkeypatch.setattr(SqlAlchemySecurityMasterRepository, "find_symbol", fail_lookup)

    response = api_client.get(
        "/api/v1/securities/resolve",
        params={"query": "MU"},
    )

    assert response.status_code == 500
    assert sentinel not in response.text
    assert "sentinel" not in response.text
    assert "Traceback" not in response.text
