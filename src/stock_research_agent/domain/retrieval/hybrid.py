"""Decimal reciprocal-rank fusion and model-free stable reranking."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from stock_research_agent.domain.retrieval.schemas import (
    HybridHit,
    LexicalHit,
    TokenizedQuery,
    VectorHit,
)

_QUANTUM = Decimal("0.000000000001")


def reciprocal_rank_fusion(
    lexical: tuple[LexicalHit, ...],
    vector: tuple[VectorHit, ...],
    *,
    k: int = 60,
) -> tuple[HybridHit, ...]:
    if k < 1:
        raise ValueError("RRF k must be positive")
    vector_by_chunk = {hit.chunk_id: hit for hit in vector}
    results: list[HybridHit] = []
    for lexical_hit in lexical:
        vector_hit = vector_by_chunk.get(lexical_hit.chunk_id)
        score = Decimal(1) / Decimal(k + lexical_hit.rank)
        if vector_hit is not None:
            score += Decimal(1) / Decimal(k + vector_hit.rank)
        results.append(
            HybridHit(
                chunk_id=lexical_hit.chunk_id,
                document_version_id=lexical_hit.document_version_id,
                citation_id=lexical_hit.citation_id,
                chunk_index=lexical_hit.chunk_index,
                locator_checksum=lexical_hit.locator_checksum,
                text=lexical_hit.text,
                section_title=lexical_hit.section_title,
                lexical_rank=lexical_hit.rank,
                vector_rank=None if vector_hit is None else vector_hit.rank,
                lexical_score=lexical_hit.score,
                vector_score=None if vector_hit is None else vector_hit.score,
                fusion_score=score.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN),
                phrase_match=lexical_hit.phrase_match,
                heading_token_matches=lexical_hit.heading_token_matches,
                rerank_reason="FUSION_SCORE",
            )
        )
    results.sort(key=lambda hit: (-hit.fusion_score, hit.locator_checksum, hit.chunk_index))
    return tuple(results)


def stable_rerank(
    query: TokenizedQuery,
    hits: tuple[HybridHit, ...],
) -> tuple[HybridHit, ...]:
    del query  # The exact phrase/heading features were computed by the lexical generation.
    ordered = sorted(
        hits,
        key=lambda hit: (
            not hit.phrase_match,
            -hit.heading_token_matches,
            -hit.fusion_score,
            min(rank for rank in (hit.lexical_rank, hit.vector_rank) if rank is not None),
            hit.locator_checksum,
            hit.chunk_index,
        ),
    )
    return tuple(hit.model_copy(update={"rerank_reason": _reason(hit)}) for hit in ordered)


def _reason(hit: HybridHit) -> str:
    if hit.phrase_match:
        return "EXACT_PHRASE"
    if hit.heading_token_matches:
        return "HEADING_MATCH"
    return "FUSION_SCORE"
