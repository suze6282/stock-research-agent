from __future__ import annotations

import json
from uuid import UUID

from fastapi.testclient import TestClient

from stock_research_agent.api.dependencies import (
    get_live_evidence_query_service,
    require_database_ready,
)
from stock_research_agent.config import Settings
from stock_research_agent.domain.live_evidence.queries import LiveEvidenceQueryService
from stock_research_agent.main import create_app
from tests.contract.test_live_evidence_tools import _Repository

RESOURCE_ID = UUID(int=1)
PATHS = (
    f"/api/v1/live-evidence/authorizations/{RESOURCE_ID}",
    f"/api/v1/live-evidence/authorization-events/{RESOURCE_ID}",
    f"/api/v1/live-evidence/authorization-consumptions/{RESOURCE_ID}",
    f"/api/v1/live-evidence/execution-approvals/{RESOURCE_ID}",
    f"/api/v1/live-evidence/manual-imports/{RESOURCE_ID}",
    f"/api/v1/live-evidence/manifests/{RESOURCE_ID}",
    f"/api/v1/live-evidence/validation-runs/{RESOURCE_ID}",
    f"/api/v1/live-evidence/end-to-end-validations/{RESOURCE_ID}",
    f"/api/v1/live-evidence/incidents/{RESOURCE_ID}",
    f"/api/v1/live-evidence/incident-events/{RESOURCE_ID}",
)


def _client() -> TestClient:
    app = create_app(Settings(database_url=None))
    app.dependency_overrides[require_database_ready] = lambda: None
    app.dependency_overrides[get_live_evidence_query_service] = lambda: LiveEvidenceQueryService(
        _Repository()
    )
    return TestClient(app)


def test_openapi_exposes_exactly_ten_live_evidence_get_routes() -> None:
    with _client() as client:
        paths = client.get("/openapi.json").json()["paths"]
    selected = {
        path: tuple(methods) for path, methods in paths.items() if "/live-evidence/" in path
    }
    assert len(selected) == 10
    assert all(methods == ("get",) for methods in selected.values())


def test_routes_are_bounded_safe_and_preserve_request_id() -> None:
    with _client() as client:
        responses = [
            client.get(path, params={"limit": 10}, headers={"X-Request-ID": "stage10"})
            for path in PATHS
        ]
        bad_limit = client.get(PATHS[0], params={"limit": 101})
        hidden_write = client.post(PATHS[0])
        unknown_query = client.get(PATHS[0], params={"refresh": "true"})

    assert all(response.status_code == 200 for response in responses)
    assert all(response.headers["X-Request-ID"] == "stage10" for response in responses)
    assert bad_limit.status_code == 422
    assert hidden_write.status_code == 405
    assert unknown_query.status_code == 422
    serialized = json.dumps([response.json() for response in responses]).casefold()
    for forbidden in ("password", "database_url", "local_path", "blob_key", "traceback"):
        assert forbidden not in serialized
