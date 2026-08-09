from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import UUID

from fastapi.testclient import TestClient

from stock_research_agent.api.dependencies import (
    get_provider_query_service,
    require_database_ready,
)
from stock_research_agent.config import Settings
from stock_research_agent.domain.providers.queries import ProviderQueryService
from stock_research_agent.main import create_app
from tests.contract.test_provider_tools import (
    PROVIDER_CODE,
    RUN_ID,
    SECURITY_ID,
    _ProviderQueryRepository,
)

PROVIDER_PATHS = (
    "/api/v1/providers",
    f"/api/v1/providers/{PROVIDER_CODE}",
    f"/api/v1/providers/{PROVIDER_CODE}/capabilities",
    f"/api/v1/providers/{PROVIDER_CODE}/health",
    f"/api/v1/providers/{PROVIDER_CODE}/license",
    f"/api/v1/provider-sync-runs/{RUN_ID}",
    f"/api/v1/provider-sync-runs/{RUN_ID}/requests",
    f"/api/v1/provider-sync-runs/{RUN_ID}/artifacts",
    f"/api/v1/provider-sync-runs/{RUN_ID}/quality-issues",
    f"/api/v1/provider-sync-runs/{RUN_ID}/dead-letters",
    f"/api/v1/provider-readiness/{SECURITY_ID}",
)
PAGED_PATHS = (
    PROVIDER_PATHS[0],
    PROVIDER_PATHS[2],
    PROVIDER_PATHS[6],
    PROVIDER_PATHS[7],
    PROVIDER_PATHS[8],
    PROVIDER_PATHS[9],
)


class _MissingProviderQueryRepository(_ProviderQueryRepository):
    def get_provider_view(self, provider_code: str) -> None:
        self.calls.append("PROVIDER")
        return None

    def get_health_view(self, provider_code: str) -> None:
        self.calls.append("HEALTH")
        return None

    def get_license_view(self, provider_code: str) -> None:
        self.calls.append("LICENSE")
        return None

    def get_sync_run_view(self, run_id: UUID) -> None:
        self.calls.append("SYNC_RUN")
        return None

    def get_readiness_view(self, security_id: UUID) -> None:
        self.calls.append("READINESS")
        return None


class _UnsafeProviderQueryRepository(_ProviderQueryRepository):
    def get_provider_view(self, provider_code: str) -> Mapping[str, object]:
        self.calls.append("PROVIDER")
        return {
            "resource_type": "PROVIDER",
            "values": {"blob_key": "C:\\private\\provider.json"},
        }


def _client(repository: _ProviderQueryRepository | None = None) -> TestClient:
    app = create_app(Settings(database_url=None))
    app.dependency_overrides[require_database_ready] = lambda: None
    app.dependency_overrides[get_provider_query_service] = lambda: ProviderQueryService(
        repository or _ProviderQueryRepository()
    )
    return TestClient(app)


def test_openapi_exposes_exactly_eleven_provider_get_routes_and_no_writes() -> None:
    with _client() as client:
        paths = client.get("/openapi.json").json()["paths"]
    provider_paths = {
        path: tuple(methods)
        for path, methods in paths.items()
        if path.startswith(("/api/v1/providers", "/api/v1/provider-"))
    }

    assert len(provider_paths) == 11
    assert all(methods == ("get",) for methods in provider_paths.values())


def test_provider_routes_return_only_safe_persisted_metadata_with_request_id() -> None:
    with _client() as client:
        responses = [
            client.get(path, headers={"X-Request-ID": "stage9-provider-contract"})
            for path in PROVIDER_PATHS
        ]

    assert all(response.status_code == 200 for response in responses)
    assert all(
        response.headers["X-Request-ID"] == "stage9-provider-contract" for response in responses
    )
    serialized = json.dumps([response.json() for response in responses]).casefold()
    for forbidden in (
        "blob_key",
        "storage_uri",
        "local_path",
        "raw_payload",
        "authorization",
        "headers",
        "password",
        "credential_value",
        "database_url",
        "traceback",
    ):
        assert forbidden not in serialized


def test_provider_page_routes_are_bounded_and_reject_unknown_sort_or_control_keys() -> None:
    with _client() as client:
        valid = [client.get(path, params={"limit": 10, "offset": 20}) for path in PAGED_PATHS]
        bad_limit = client.get(PROVIDER_PATHS[0], params={"limit": 101})
        bad_offset = client.get(PROVIDER_PATHS[0], params={"offset": 100_001})
        arbitrary_sort = client.get(PROVIDER_PATHS[0], params={"sort": "created_at desc"})
        hidden_sync = client.get(PROVIDER_PATHS[1], params={"refresh": "true"})

    assert all(response.status_code == 200 for response in valid)
    assert all(
        response.json()["limit"] == 10 and response.json()["offset"] == 20 for response in valid
    )
    assert {bad_limit.status_code, bad_offset.status_code} == {422}
    assert arbitrary_sort.status_code == 422
    assert hidden_sync.status_code == 422


def test_missing_or_invalid_provider_resources_fail_safely() -> None:
    with _client(_MissingProviderQueryRepository()) as client:
        missing = [
            client.get(path)
            for path in (PROVIDER_PATHS[1], *PROVIDER_PATHS[3:6], PROVIDER_PATHS[10])
        ]
        invalid_uuid = client.get("/api/v1/provider-sync-runs/not-a-uuid")

    assert all(response.status_code == 404 for response in missing)
    assert all(
        response.json()["error"]["code"] == "PROVIDER_RESOURCE_NOT_FOUND" for response in missing
    )
    assert invalid_uuid.status_code == 422
    assert all("sql" not in response.text.casefold() for response in missing)


def test_unsafe_repository_projection_is_not_leaked_as_an_internal_error() -> None:
    with _client(_UnsafeProviderQueryRepository()) as client:
        response = client.get(PROVIDER_PATHS[1])

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "blob_key" not in response.text.casefold()
    assert "private" not in response.text.casefold()


def test_provider_get_routes_never_probe_sync_or_mutate() -> None:
    repository = _ProviderQueryRepository()
    with _client(repository) as client:
        responses = [client.get(path) for path in PROVIDER_PATHS]

    assert all(response.status_code == 200 for response in responses)
    assert len(repository.calls) == 11
    assert all(
        call
        in {
            "PROVIDER",
            "CAPABILITY",
            "HEALTH",
            "LICENSE",
            "SYNC_RUN",
            "ATTEMPT",
            "ARTIFACT",
            "QUALITY_ISSUE",
            "DEAD_LETTER",
            "READINESS",
        }
        for call in repository.calls
    )
