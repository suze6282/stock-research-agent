from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from stock_research_agent.domain.documents.enums import (
    CitationStatus,
    LocatorType,
    TrustLevel,
)
from stock_research_agent.domain.retrieval.enums import RetrievalMode, RetrievalStatus
from stock_research_agent.domain.retrieval.evidence import build_evidence_bundle
from stock_research_agent.domain.retrieval.schemas import (
    RetrievalHitRecord,
    RetrievalRunRecord,
    VerifiedCitationEvidence,
)

NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
RUN_ID = UUID("00000000-0000-0000-0000-000000000071")


def _run(status: RetrievalStatus = RetrievalStatus.PARTIAL) -> RetrievalRunRecord:
    return RetrievalRunRecord(
        id=RUN_ID,
        request_fingerprint="a" * 64,
        request_basis_fingerprint="b" * 64,
        security_id=UUID("00000000-0000-0000-0000-000000000072"),
        snapshot_id=UUID("00000000-0000-0000-0000-000000000073"),
        research_as_of_time=None,
        mode=RetrievalMode.HYBRID,
        original_query="risk",
        normalized_query="risk",
        max_results=10,
        tokenizer_version="tokenizer-v1",
        lexical_index_version_id=UUID("00000000-0000-0000-0000-000000000074"),
        vector_index_version_id=None,
        fusion_version="fusion-v1",
        reranker_version="stable-reranker-v1",
        status=status,
        warnings=("VECTOR_CHANNEL_BLOCKED",),
        created_at=NOW,
        completed_at=NOW,
    )


def _hit() -> RetrievalHitRecord:
    return RetrievalHitRecord(
        id=UUID("00000000-0000-0000-0000-000000000075"),
        retrieval_run_id=RUN_ID,
        chunk_id=UUID("00000000-0000-0000-0000-000000000076"),
        citation_id=UUID("00000000-0000-0000-0000-000000000077"),
        final_rank=1,
        lexical_rank=1,
        vector_rank=None,
        fusion_score=Decimal("0.016393442623"),
        rerank_reason="FUSION_SCORE",
        created_at=NOW,
    )


def test_evidence_bundle_includes_only_valid_citations_and_bounded_excerpt() -> None:
    hit = _hit()
    valid = VerifiedCitationEvidence(
        citation_id=hit.citation_id,
        document_version_id=UUID("00000000-0000-0000-0000-000000000078"),
        chunk_id=hit.chunk_id,
        excerpt="e" * 1100,
        status=CitationStatus.VALID,
        document_type="OTHER",
        trust_level=TrustLevel.TEST_FIXTURE,
        published_at=NOW,
        provider_id=UUID("00000000-0000-0000-0000-000000000090"),
        source_document_id=UUID("00000000-0000-0000-0000-000000000091"),
        evidence_origin="SYNTHETIC_TEST_ONLY",
        access_mode="OFFLINE",
        live_status="NOT_LIVE",
        locator_type=LocatorType.TEXT_OFFSET_RANGE,
        chunk_version="chunk-v1",
        parser_version="text-parser-v1",
        tokenizer_version="tokenizer-v1",
        citation_version="citation-v1",
        document_checksum="c" * 64,
    )
    invalid = valid.model_copy(
        update={
            "citation_id": UUID("00000000-0000-0000-0000-000000000079"),
            "status": CitationStatus.INVALID,
        }
    )

    bundle = build_evidence_bundle(_run(), (hit,), (valid, invalid), excerpt_limit=1000)

    assert bundle.status == RetrievalStatus.PARTIAL
    assert len(bundle.items) == 1
    assert len(bundle.items[0].excerpt) == 1000
    assert bundle.items[0].citation_status == CitationStatus.VALID
    assert bundle.warnings == ("VECTOR_CHANNEL_BLOCKED", "INVALID_CITATION_EXCLUDED")
    dumped = bundle.model_dump(mode="json")
    assert "raw_payload" not in str(dumped)
    assert "storage_uri" not in str(dumped)
    assert "conclusion" not in dumped
    assert "recommendation" not in dumped


def test_zero_valid_evidence_is_blocked_without_fabrication() -> None:
    hit = _hit()
    invalid = VerifiedCitationEvidence(
        citation_id=hit.citation_id,
        document_version_id=UUID("00000000-0000-0000-0000-000000000078"),
        chunk_id=hit.chunk_id,
        excerpt="unverified",
        status=CitationStatus.INVALID,
        document_type="OTHER",
        trust_level=TrustLevel.TEST_FIXTURE,
        published_at=NOW,
        provider_id=UUID("00000000-0000-0000-0000-000000000090"),
        source_document_id=UUID("00000000-0000-0000-0000-000000000091"),
        evidence_origin="SYNTHETIC_TEST_ONLY",
        access_mode="OFFLINE",
        live_status="NOT_LIVE",
        locator_type=LocatorType.TEXT_OFFSET_RANGE,
        chunk_version="chunk-v1",
        parser_version="text-parser-v1",
        tokenizer_version="tokenizer-v1",
        citation_version="citation-v1",
        document_checksum="c" * 64,
    )

    bundle = build_evidence_bundle(_run(RetrievalStatus.PASS), (hit,), (invalid,))

    assert bundle.status == RetrievalStatus.BLOCKED
    assert bundle.items == ()
    assert "NO_VALID_CITATIONS" in bundle.warnings
