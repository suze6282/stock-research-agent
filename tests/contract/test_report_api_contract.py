from __future__ import annotations

import json
from uuid import UUID

from fastapi.testclient import TestClient

from stock_research_agent.api.dependencies import (
    get_report_query_service,
    require_database_ready,
)
from stock_research_agent.config import Settings
from stock_research_agent.domain.reports.queries import ReportQueryService
from stock_research_agent.main import create_app
from tests.contract.test_report_tools import (
    REPORT_ID,
    FakeReportQueryRepository,
)

REPORT_PATHS = (
    f"/api/v1/research-reports/{REPORT_ID}",
    f"/api/v1/research-reports/{REPORT_ID}/sections",
    f"/api/v1/research-reports/{REPORT_ID}/blocks",
    f"/api/v1/research-reports/{REPORT_ID}/claims",
    f"/api/v1/research-reports/{REPORT_ID}/evidence",
    f"/api/v1/research-reports/{REPORT_ID}/citations",
    f"/api/v1/research-reports/{REPORT_ID}/reflection-runs",
    f"/api/v1/research-reports/{REPORT_ID}/reflection-findings",
    f"/api/v1/research-reports/{REPORT_ID}/revisions",
    f"/api/v1/research-reports/{REPORT_ID}/release-gate",
)


def _client(
    repository: FakeReportQueryRepository | None = None,
) -> TestClient:
    app = create_app(Settings(database_url=None))
    app.dependency_overrides[require_database_ready] = lambda: None
    app.dependency_overrides[get_report_query_service] = lambda: ReportQueryService(
        repository or FakeReportQueryRepository()
    )
    return TestClient(app)


def test_openapi_exposes_exactly_ten_report_get_routes_and_no_writes() -> None:
    with _client() as client:
        paths = client.get("/openapi.json").json()["paths"]
    report_paths = {
        path: tuple(methods)
        for path, methods in paths.items()
        if path.startswith("/api/v1/research-reports/")
    }

    assert len(report_paths) == 10
    assert all(methods == ("get",) for methods in report_paths.values())


def test_report_get_reads_persisted_json_and_markdown_with_request_id() -> None:
    with _client() as client:
        response = client.get(
            REPORT_PATHS[0],
            headers={"X-Request-ID": "stage8-report-contract"},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "stage8-report-contract"
    payload = response.json()
    assert payload["id"] == str(REPORT_ID)
    assert payload["structured_content"]["schema_version"] == "research-report-v1"
    assert payload["markdown_content"].endswith("\n")
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    for forbidden in (
        "database_url",
        "storage_uri",
        "local_path",
        "raw_payload",
        "document_body",
        "authorization",
        "password",
        "traceback",
    ):
        assert forbidden not in serialized


def test_all_page_routes_are_bounded_and_reject_unknown_query_keys() -> None:
    page_paths = REPORT_PATHS[1:9]
    with _client() as client:
        valid = [client.get(path, params={"limit": 10, "offset": 20}) for path in page_paths]
        bad_limit = client.get(REPORT_PATHS[1], params={"limit": 101})
        bad_offset = client.get(REPORT_PATHS[1], params={"offset": 10_001})
        unknown = client.get(
            REPORT_PATHS[1],
            params={"sort": "DROP TABLE research_reports"},
        )
        invalid_uuid = client.get("/api/v1/research-reports/not-a-uuid")

    assert all(response.status_code == 200 for response in valid)
    assert all(
        response.json()["limit"] == 10
        and response.json()["offset"] == 20
        and response.json()["total"] >= 0
        for response in valid
    )
    assert bad_limit.status_code == 422
    assert bad_offset.status_code == 422
    assert unknown.status_code == 422
    assert invalid_uuid.status_code == 422


def test_missing_report_or_gate_is_safe_404_without_internal_error() -> None:
    missing = UUID("81000000-0000-4000-8000-000000000099")
    repository = FakeReportQueryRepository(exists=False)
    with _client(repository) as client:
        report = client.get(f"/api/v1/research-reports/{missing}")
        sections = client.get(f"/api/v1/research-reports/{missing}/sections")
        gate = client.get(f"/api/v1/research-reports/{missing}/release-gate")

    assert {report.status_code, sections.status_code, gate.status_code} == {404}
    assert all(
        response.json()["error"]["code"] == "REPORT_RESOURCE_NOT_FOUND"
        for response in (report, sections, gate)
    )
    assert all("sql" not in response.text.casefold() for response in (report, sections, gate))


def test_get_routes_do_not_implicitly_run_any_report_workflow() -> None:
    repository = FakeReportQueryRepository()
    with _client(repository) as client:
        responses = [client.get(path) for path in REPORT_PATHS]

    assert all(response.status_code == 200 for response in responses)
    assert all(call.startswith(("get_", "list_")) for call in repository.calls)
    assert not any(
        call.startswith(
            (
                "create_",
                "add_",
                "update_",
                "delete_",
                "generate_",
                "execute_",
            )
        )
        for call in repository.calls
    )
