"""Construction of bounded evidence bundles from deterministically verified citations."""

from __future__ import annotations

from stock_research_agent.domain.documents.enums import CitationStatus
from stock_research_agent.domain.retrieval.enums import RetrievalStatus
from stock_research_agent.domain.retrieval.schemas import (
    EvidenceBundle,
    EvidenceItem,
    RetrievalHitRecord,
    RetrievalRunRecord,
    VerifiedCitationEvidence,
)


def build_evidence_bundle(
    run: RetrievalRunRecord,
    hits: tuple[RetrievalHitRecord, ...],
    citations: tuple[VerifiedCitationEvidence, ...],
    *,
    excerpt_limit: int = 1000,
) -> EvidenceBundle:
    if not 1 <= excerpt_limit <= 1000:
        raise ValueError("excerpt_limit must be between 1 and 1000")
    valid_by_id = {
        citation.citation_id: citation
        for citation in citations
        if citation.status == CitationStatus.VALID
    }
    items: list[EvidenceItem] = []
    for hit in sorted(hits, key=lambda value: value.final_rank):
        if hit.citation_id is None:
            continue
        citation = valid_by_id.get(hit.citation_id)
        if citation is None or citation.chunk_id != hit.chunk_id:
            continue
        items.append(
            EvidenceItem(
                citation_id=citation.citation_id,
                document_version_id=citation.document_version_id,
                chunk_id=citation.chunk_id,
                excerpt=citation.excerpt[:excerpt_limit],
                document_type=citation.document_type,
                trust_level=citation.trust_level,
                published_at=citation.published_at,
                provider_id=citation.provider_id,
                source_document_id=citation.source_document_id,
                evidence_origin=citation.evidence_origin,
                access_mode=citation.access_mode,
                live_status=citation.live_status,
                locator_type=citation.locator_type,
                start_page=citation.start_page,
                end_page=citation.end_page,
                section_path=citation.section_path,
                chunk_version=citation.chunk_version,
                parser_version=citation.parser_version,
                tokenizer_version=citation.tokenizer_version,
                citation_version=citation.citation_version,
                document_checksum=citation.document_checksum,
                match_reason=hit.rerank_reason,
            )
        )
    warnings = list(run.warnings)
    if any(citation.status != CitationStatus.VALID for citation in citations):
        warnings.append("INVALID_CITATION_EXCLUDED")
    status = run.status
    if not items:
        status = RetrievalStatus.BLOCKED
        warnings.append("NO_VALID_CITATIONS")
    return EvidenceBundle(
        status=status,
        retrieval_run_id=run.id,
        mode=run.mode,
        research_as_of_time=run.research_as_of_time,
        snapshot_id=run.snapshot_id,
        lexical_index_version_id=run.lexical_index_version_id,
        vector_index_version_id=run.vector_index_version_id,
        items=tuple(items),
        warnings=tuple(dict.fromkeys(warnings)),
    )
