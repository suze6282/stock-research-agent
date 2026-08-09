from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient

from stock_research_agent.api.dependencies import (
    get_research_agent_query_service,
    require_database_ready,
)
from stock_research_agent.config import Settings
from stock_research_agent.domain.research_agent.enums import ResearchRunStatus
from stock_research_agent.domain.research_agent.queries import ResearchAgentQueryService
from stock_research_agent.domain.research_agent.schemas import (
    Page,
    PageRequest,
    ResearchAgentRunRecord,
    RunBudget,
)
from stock_research_agent.main import create_app

RUN_ID = UUID("76000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 7, 24, tzinfo=UTC)


def _run() -> ResearchAgentRunRecord:
    return ResearchAgentRunRecord(
        id=RUN_ID,
        request_id=UUID("76000000-0000-4000-8000-000000000002"),
        security_id=UUID("76000000-0000-4000-8000-000000000003"),
        snapshot_id=UUID("76000000-0000-4000-8000-000000000004"),
        research_as_of_time=NOW,
        status=ResearchRunStatus.PARTIAL,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version="tool-catalog-v1:" + "a" * 64,
        tool_catalog_checksum="a" * 64,
        idempotency_key="b" * 64,
        budget=RunBudget(
            max_steps=12,
            max_tool_calls=24,
            max_calls_per_tool=5,
            max_retries_per_step=1,
            max_duration_seconds=120,
            model_token_budget=0,
            consumed_steps=4,
            consumed_tool_calls=2,
            consumed_model_tokens=0,
            elapsed_seconds=Decimal("1.0"),
        ),
        warning_codes=("DOCUMENT_EVIDENCE_BLOCKED",),
        created_at=NOW,
        updated_at=NOW,
    )


class FakeRepository:
    def get_run_view(self, run_id: UUID) -> object | None:
        return _run() if run_id == RUN_ID else None

    def get_plan_view(self, run_id: UUID) -> object | None:
        return None

    def list_step_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)

    def list_invocation_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)

    def list_evidence_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)

    def list_claim_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)

    def get_package_view(self, run_id: UUID) -> object | None:
        return None

    def list_event_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)


def _client() -> TestClient:
    app = create_app(Settings(database_url=None))
    app.dependency_overrides[require_database_ready] = lambda: None
    app.dependency_overrides[get_research_agent_query_service] = lambda: ResearchAgentQueryService(
        FakeRepository()
    )
    return TestClient(app)


def test_openapi_exposes_exactly_eight_research_agent_get_routes() -> None:
    with _client() as client:
        paths = client.get("/openapi.json").json()["paths"]
    agent_paths = {
        path: tuple(methods)
        for path, methods in paths.items()
        if path.startswith("/api/v1/research-agent/")
    }

    assert len(agent_paths) == 8
    assert all(methods == ("get",) for methods in agent_paths.values())


def test_run_projection_is_read_only_bounded_and_preserves_request_id() -> None:
    with _client() as client:
        response = client.get(
            f"/api/v1/research-agent/runs/{RUN_ID}",
            headers={"X-Request-ID": "stage7-contract"},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "stage7-contract"
    assert response.json()["id"] == str(RUN_ID)
    forbidden = {
        "raw_payload",
        "document_body",
        "storage_uri",
        "local_path",
        "database_url",
        "sql",
        "secret",
        "password",
        "input_body",
        "output_body",
    }
    assert forbidden.isdisjoint(response.json())


def test_missing_single_resources_are_safe_404() -> None:
    missing_id = UUID("76000000-0000-4000-8000-000000000099")
    paths = (
        f"/api/v1/research-agent/runs/{missing_id}",
        f"/api/v1/research-agent/runs/{RUN_ID}/plan",
        f"/api/v1/research-agent/runs/{RUN_ID}/package",
    )
    with _client() as client:
        responses = [client.get(path) for path in paths]

    assert all(response.status_code == 404 for response in responses)
    assert all(
        response.json()["error"]["code"] == "RESEARCH_RESOURCE_NOT_FOUND" for response in responses
    )
    assert all("sql" not in response.text.casefold() for response in responses)


def test_list_routes_enforce_uuid_query_bounds_and_exact_query_keys() -> None:
    list_paths = (
        "steps",
        "tool-invocations",
        "evidence",
        "claims",
        "events",
    )
    with _client() as client:
        valid = [
            client.get(
                f"/api/v1/research-agent/runs/{RUN_ID}/{suffix}",
                params={"limit": 10, "offset": 20},
            )
            for suffix in list_paths
        ]
        bad_limit = client.get(
            f"/api/v1/research-agent/runs/{RUN_ID}/steps",
            params={"limit": 101},
        )
        bad_offset = client.get(
            f"/api/v1/research-agent/runs/{RUN_ID}/steps",
            params={"offset": 10_001},
        )
        unknown = client.get(
            f"/api/v1/research-agent/runs/{RUN_ID}/steps",
            params={"sort": "created_at"},
        )
        invalid_uuid = client.get("/api/v1/research-agent/runs/not-a-uuid")

    assert all(response.status_code == 200 for response in valid)
    assert all(
        response.json() == {"items": [], "limit": 10, "offset": 20, "total": 0}
        for response in valid
    )
    assert bad_limit.status_code == 422
    assert bad_offset.status_code == 422
    assert unknown.status_code == 422
    assert invalid_uuid.status_code == 422
