from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from stock_research_agent.domain.retrieval.hybrid import stable_rerank
from stock_research_agent.domain.retrieval.schemas import HybridHit, LexicalToken, TokenizedQuery


def _hit(number: int, *, phrase: bool, heading: int, score: str) -> HybridHit:
    return HybridHit(
        chunk_id=UUID(f"00000000-0000-0000-0000-{number:012d}"),
        document_version_id=UUID(f"10000000-0000-0000-0000-{number:012d}"),
        citation_id=UUID(f"20000000-0000-0000-0000-{number:012d}"),
        chunk_index=number,
        locator_checksum=f"{number:064x}",
        text=f"risk factors evidence {number}",
        section_title="Risk Factors" if heading else None,
        lexical_rank=number,
        vector_rank=None,
        lexical_score=Decimal("1"),
        vector_score=None,
        fusion_score=Decimal(score),
        phrase_match=phrase,
        heading_token_matches=heading,
        rerank_reason="FUSION_SCORE",
    )


def test_stable_reranker_prioritizes_phrase_then_heading_then_fusion() -> None:
    query = TokenizedQuery(
        original_query="risk factors",
        normalized_query="risk factors",
        tokens=(LexicalToken(value="risk", position=0), LexicalToken(value="factors", position=1)),
    )
    hits = (
        _hit(1, phrase=False, heading=0, score="0.05"),
        _hit(2, phrase=True, heading=0, score="0.01"),
        _hit(3, phrase=False, heading=2, score="0.02"),
    )

    reranked = stable_rerank(query, hits)

    assert [hit.chunk_index for hit in reranked] == [2, 3, 1]
    assert [hit.rerank_reason for hit in reranked] == [
        "EXACT_PHRASE",
        "HEADING_MATCH",
        "FUSION_SCORE",
    ]


def test_stable_reranker_has_deterministic_locator_tie_break() -> None:
    query = TokenizedQuery(
        original_query="risk",
        normalized_query="risk",
        tokens=(LexicalToken(value="risk", position=0),),
    )
    hits = (
        _hit(2, phrase=False, heading=0, score="0.01"),
        _hit(1, phrase=False, heading=0, score="0.01"),
    )

    assert [hit.chunk_index for hit in stable_rerank(query, hits)] == [1, 2]
