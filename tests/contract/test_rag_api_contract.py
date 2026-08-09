from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient

from stock_research_agent.api.dependencies import get_rag_query_service, require_database_ready
from stock_research_agent.config import Settings
from stock_research_agent.domain.retrieval.schemas import EvidenceBundle
from stock_research_agent.domain.retrieval.service import PrecomputedRetrievalQueryService
from stock_research_agent.main import create_app


class EmptyRepository:
    def find_bundle_for_request(self, *_args: object) -> EvidenceBundle | None:
        return None

    def list_document_versions(self, **_scope: object) -> tuple[dict[str, object], ...]:
        return ()

    def get_document_metadata(self, _record_id: UUID) -> dict[str, object] | None:
        return None

    def get_document_chunk(self, _record_id: UUID) -> dict[str, object] | None:
        return None

    def get_citation(self, _record_id: UUID) -> dict[str, object] | None:
        return None

    def verify_citation(self, _record_id: UUID, **_scope: object) -> dict[str, object] | None:
        return None

    def get_retrieval_run(self, _record_id: UUID) -> dict[str, object] | None:
        return None

    def get_evidence_bundle(self, _record_id: UUID) -> dict[str, object] | None:
        return None


def _client() -> TestClient:
    app = create_app(Settings(database_url=None))
    app.dependency_overrides[require_database_ready] = lambda: None
    app.dependency_overrides[get_rag_query_service] = lambda: PrecomputedRetrievalQueryService(
        EmptyRepository()
    )
    return TestClient(app)


def test_rag_openapi_exposes_only_eight_get_routes() -> None:
    with _client() as client:
        paths = client.get("/openapi.json").json()["paths"]
    expected_paths = {
        "/api/v1/document-versions",
        "/api/v1/document-versions/{document_version_id}",
        "/api/v1/rag/search",
        "/api/v1/document-chunks/{chunk_id}",
        "/api/v1/citations/{citation_id}",
        "/api/v1/citations/{citation_id}/verify",
        "/api/v1/retrieval-runs/{retrieval_run_id}",
        "/api/v1/retrieval-runs/{retrieval_run_id}/evidence",
    }
    rag_paths = {path: tuple(paths[path]) for path in expected_paths}
    assert set(rag_paths) == expected_paths
    assert all(methods == ("get",) for methods in rag_paths.values())


def test_rag_search_cache_miss_is_http_200_blocked_with_request_id() -> None:
    security_id = UUID("00000000-0000-0000-0000-0000000000a1")
    snapshot_id = UUID("00000000-0000-0000-0000-0000000000a2")
    with _client() as client:
        response = client.get(
            "/api/v1/rag/search",
            params={
                "security_id": str(security_id),
                "snapshot_id": str(snapshot_id),
                "query": "risk",
                "mode": "HYBRID",
            },
            headers={"X-Request-ID": "stage6-contract"},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"
    assert response.json()["warnings"] == ["RETRIEVAL_RUN_NOT_PRECOMPUTED"]
    assert response.headers["X-Request-ID"] == "stage6-contract"


def test_rag_search_rejects_empty_or_oversized_query_without_leaking_sql() -> None:
    with _client() as client:
        response = client.get(
            "/api/v1/rag/search",
            params={
                "security_id": "00000000-0000-0000-0000-0000000000a1",
                "snapshot_id": "00000000-0000-0000-0000-0000000000a2",
                "query": "",
                "mode": "LEXICAL",
            },
        )
    assert response.status_code == 422
    assert "sql" not in response.text.casefold()


def test_rag_search_requires_exactly_one_scope_without_internal_error() -> None:
    with _client() as client:
        missing = client.get(
            "/api/v1/rag/search",
            params={
                "security_id": "00000000-0000-0000-0000-0000000000a1",
                "query": "risk",
            },
        )
        both = client.get(
            "/api/v1/rag/search",
            params={
                "security_id": "00000000-0000-0000-0000-0000000000a1",
                "snapshot_id": "00000000-0000-0000-0000-0000000000a2",
                "research_as_of_time": "2026-07-20T08:00:00Z",
                "query": "risk",
            },
        )

    assert missing.status_code == 422
    assert both.status_code == 422
    assert missing.json()["error"]["code"] == "INVALID_RETRIEVAL_SCOPE"
    assert both.json()["error"]["code"] == "INVALID_RETRIEVAL_SCOPE"


def test_rag_detail_misses_are_safe_404_while_empty_collection_is_200() -> None:
    record_id = "00000000-0000-0000-0000-0000000000a1"
    snapshot_id = "00000000-0000-0000-0000-0000000000a2"
    collection = (
        "/api/v1/document-versions",
        {"security_id": record_id, "snapshot_id": snapshot_id},
    )
    requests = (
        (f"/api/v1/document-versions/{record_id}", {}),
        (f"/api/v1/document-chunks/{record_id}", {}),
        (f"/api/v1/citations/{record_id}", {}),
        (f"/api/v1/citations/{record_id}/verify", {"snapshot_id": snapshot_id}),
        (f"/api/v1/retrieval-runs/{record_id}", {}),
        (f"/api/v1/retrieval-runs/{record_id}/evidence", {}),
    )
    with _client() as client:
        collection_response = client.get(collection[0], params=collection[1])
        responses = [client.get(path, params=params) for path, params in requests]

    assert collection_response.status_code == 200
    assert collection_response.json()["status"] == "BLOCKED"
    assert all(response.status_code == 404 for response in responses)
    assert all(
        response.json()["error"]["code"] == "RAG_RESOURCE_NOT_FOUND" for response in responses
    )
    assert all("storage_uri" not in response.text for response in responses)


def test_document_version_list_requires_exactly_one_scope() -> None:
    with _client() as client:
        response = client.get(
            "/api/v1/document-versions",
            params={"security_id": "00000000-0000-0000-0000-0000000000a1"},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_RETRIEVAL_SCOPE"


def test_citation_verification_requires_exactly_one_scope() -> None:
    citation_id = "00000000-0000-0000-0000-0000000000a1"
    with _client() as client:
        missing = client.get(f"/api/v1/citations/{citation_id}/verify")
        both = client.get(
            f"/api/v1/citations/{citation_id}/verify",
            params={
                "snapshot_id": "00000000-0000-0000-0000-0000000000a2",
                "research_as_of_time": "2026-07-20T08:00:00Z",
            },
        )

    assert missing.status_code == 422
    assert both.status_code == 422
    assert missing.json()["error"]["code"] == "INVALID_RETRIEVAL_SCOPE"
    assert both.json()["error"]["code"] == "INVALID_RETRIEVAL_SCOPE"


def test_naive_research_as_of_time_is_rejected_at_api_boundary() -> None:
    security_id = "00000000-0000-0000-0000-0000000000a1"
    with _client() as client:
        search = client.get(
            "/api/v1/rag/search",
            params={
                "security_id": security_id,
                "query": "risk",
                "research_as_of_time": "2026-07-20T08:00:00",
            },
        )
        versions = client.get(
            "/api/v1/document-versions",
            params={
                "security_id": security_id,
                "research_as_of_time": "2026-07-20T08:00:00",
            },
        )

    assert search.status_code == 422
    assert versions.status_code == 422
    assert search.json()["error"]["code"] == "INVALID_RETRIEVAL_SCOPE"
    assert versions.json()["error"]["code"] == "INVALID_RETRIEVAL_SCOPE"
