from __future__ import annotations

from uuid import UUID

import pytest

from stock_research_agent.domain.retrieval.enums import RetrievalMode
from stock_research_agent.domain.retrieval.schemas import EvidenceBundle
from stock_research_agent.domain.retrieval.service import PrecomputedRetrievalQueryService
from stock_research_agent.tools.permissions import ToolPermission
from stock_research_agent.tools.registry import (
    ToolRegistryError,
    create_rag_tool_registry,
    create_tool_metadata_registry,
)

NAMES = {
    "list_document_versions",
    "get_document_metadata",
    "search_document_chunks",
    "get_document_chunk",
    "get_citation",
    "verify_citation",
    "get_evidence_bundle",
    "get_retrieval_run",
}


class EmptyReadRepository:
    def find_bundle_for_request(self, *_args: object) -> EvidenceBundle | None:
        return None


class PersistedReadRepository(EmptyReadRepository):
    def list_document_versions(self, **_scope: object) -> tuple[dict[str, object], ...]:
        return ({"document_version_id": "00000000-0000-0000-0000-0000000000b1"},)

    def get_document_metadata(self, _record_id: UUID) -> dict[str, object] | None:
        return {"kind": "document_version"}

    def get_document_chunk(self, _record_id: UUID) -> dict[str, object] | None:
        return {"kind": "chunk", "text": "bounded evidence"}

    def get_citation(self, _record_id: UUID) -> dict[str, object] | None:
        return {"kind": "citation", "excerpt": "bounded evidence"}

    def verify_citation(self, _record_id: UUID, **_scope: object) -> dict[str, object] | None:
        return {"kind": "citation_verification", "citation_status": "VALID"}

    def get_retrieval_run(self, _record_id: UUID) -> dict[str, object] | None:
        return {"kind": "retrieval_run", "status": "PASS"}

    def get_evidence_bundle(self, _record_id: UUID) -> dict[str, object] | None:
        return {"kind": "evidence_bundle", "items": []}


def test_metadata_registry_lists_all_eight_rag_tools_as_strictly_read_only() -> None:
    metadata = {item.name: item for item in create_tool_metadata_registry().list()}

    assert NAMES <= set(metadata)
    for name in NAMES:
        item = metadata[name]
        assert item.version == "1.0.0"
        assert item.permission == ToolPermission.READ_ONLY
        assert item.read_only is True
        assert item.writes is False
        assert item.requires_network is False


def test_search_tool_cache_miss_is_blocked_without_refresh() -> None:
    registry = create_rag_tool_registry(PrecomputedRetrievalQueryService(EmptyReadRepository()))
    result = registry.execute(
        "search_document_chunks",
        "1.0.0",
        {
            "security_id": UUID("00000000-0000-0000-0000-000000000091"),
            "snapshot_id": UUID("00000000-0000-0000-0000-000000000092"),
            "query": "risk",
            "mode": RetrievalMode.HYBRID,
            "max_results": 10,
        },
    )

    assert result.model_dump(mode="json")["status"] == "BLOCKED"
    assert result.model_dump(mode="json")["warnings"] == ["RETRIEVAL_RUN_NOT_PRECOMPUTED"]


def test_all_non_search_rag_tools_return_persisted_records_without_writes() -> None:
    registry = create_rag_tool_registry(PrecomputedRetrievalQueryService(PersistedReadRepository()))
    common_id = UUID("00000000-0000-0000-0000-0000000000b1")
    scope = {
        "security_id": UUID("00000000-0000-0000-0000-000000000091"),
        "snapshot_id": UUID("00000000-0000-0000-0000-000000000092"),
    }
    payloads = {
        "list_document_versions": scope,
        "get_document_metadata": {"document_version_id": common_id},
        "get_document_chunk": {"chunk_id": common_id},
        "get_citation": {"citation_id": common_id},
        "verify_citation": {"citation_id": common_id, "snapshot_id": common_id},
        "get_evidence_bundle": {"retrieval_run_id": common_id},
        "get_retrieval_run": {"retrieval_run_id": common_id},
    }

    for name, payload in payloads.items():
        result = registry.execute(name, "1.0.0", payload)
        assert result.model_dump(mode="json")["status"] == "PASS"
        assert len(result.model_dump(mode="json")["records"]) == 1


def test_verify_citation_tool_requires_exactly_one_scope() -> None:
    registry = create_rag_tool_registry(PrecomputedRetrievalQueryService(PersistedReadRepository()))
    citation_id = UUID("00000000-0000-0000-0000-0000000000b1")

    with pytest.raises(ToolRegistryError, match="invalid"):
        registry.execute(
            "verify_citation",
            "1.0.0",
            {"citation_id": citation_id},
        )
