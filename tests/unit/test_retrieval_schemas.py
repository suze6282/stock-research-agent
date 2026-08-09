from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.documents.enums import DocumentLanguage, TrustLevel
from stock_research_agent.domain.retrieval.enums import (
    IndexStatus,
    RetrievalMode,
    RetrievalStatus,
    VectorHealth,
)
from stock_research_agent.domain.retrieval.schemas import (
    HybridHit,
    RetrievalFilters,
    RetrievalRequest,
)

SECURITY_ID = UUID("00000000-0000-0000-0000-000000000041")
SNAPSHOT_ID = UUID("00000000-0000-0000-0000-000000000042")
NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


def test_retrieval_enums_are_closed_and_do_not_claim_vector_availability() -> None:
    assert {item.value for item in RetrievalMode} == {"LEXICAL", "VECTOR", "HYBRID"}
    assert {item.value for item in IndexStatus} == {
        "BUILDING",
        "COMPLETE",
        "PARTIAL",
        "BLOCKED",
        "FAILED",
    }
    assert {item.value for item in VectorHealth} == {"READY", "DEGRADED", "BLOCKED"}
    assert {item.value for item in RetrievalStatus} == {"PASS", "PARTIAL", "BLOCKED", "FAIL"}


def test_retrieval_request_requires_exact_security_and_one_scope() -> None:
    request = RetrievalRequest(
        query="风险 factors",
        mode=RetrievalMode.HYBRID,
        filters=RetrievalFilters(security_id=SECURITY_ID, snapshot_id=SNAPSHOT_ID),
        max_results=10,
    )

    assert request.filters.strict_unknown_publication is True
    with pytest.raises(ValidationError, match="exactly one"):
        RetrievalFilters(security_id=SECURITY_ID)
    with pytest.raises(ValidationError, match="exactly one"):
        RetrievalFilters(
            security_id=SECURITY_ID,
            snapshot_id=SNAPSHOT_ID,
            research_as_of_time=NOW,
        )


def test_retrieval_request_rejects_naive_time_query_bounds_and_unknown_filters() -> None:
    with pytest.raises(ValidationError, match="timezone aware"):
        RetrievalFilters(security_id=SECURITY_ID, research_as_of_time=NOW.replace(tzinfo=None))
    for query in ("", "x" * 257):
        with pytest.raises(ValidationError):
            RetrievalRequest(
                query=query,
                mode=RetrievalMode.LEXICAL,
                filters=RetrievalFilters(security_id=SECURITY_ID, snapshot_id=SNAPSHOT_ID),
            )
    with pytest.raises(ValidationError):
        RetrievalRequest.model_validate(
            {
                "query": "safe",
                "mode": "LEXICAL",
                "filters": {
                    "security_id": str(SECURITY_ID),
                    "snapshot_id": str(SNAPSHOT_ID),
                    "arbitrary_sort": "DROP TABLE",
                },
                "max_results": 21,
            }
        )


def test_filters_accept_only_document_language_and_trust_vocabularies() -> None:
    filters = RetrievalFilters(
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        document_types=("SEC_10_K",),
        languages=(DocumentLanguage.EN_US,),
        trust_levels=(TrustLevel.OFFICIAL_REGULATORY,),
    )
    assert filters.document_types == ("SEC_10_K",)


def test_hybrid_hit_serializes_decimal_as_string_and_allows_missing_vector_rank() -> None:
    hit = HybridHit(
        chunk_id=UUID("00000000-0000-0000-0000-000000000043"),
        document_version_id=UUID("00000000-0000-0000-0000-000000000044"),
        citation_id=UUID("00000000-0000-0000-0000-000000000045"),
        chunk_index=0,
        locator_checksum="a" * 64,
        text="bounded excerpt",
        section_title=None,
        lexical_rank=1,
        vector_rank=None,
        lexical_score=Decimal("1.25"),
        vector_score=None,
        fusion_score=Decimal("0.016393442623"),
        phrase_match=False,
        heading_token_matches=0,
        rerank_reason="FUSION_SCORE",
    )

    dumped = hit.model_dump(mode="json")
    assert dumped["fusion_score"] == "0.016393442623"
    assert dumped["vector_rank"] is None
