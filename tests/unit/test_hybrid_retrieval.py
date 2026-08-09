from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from stock_research_agent.domain.retrieval.hybrid import reciprocal_rank_fusion
from stock_research_agent.domain.retrieval.schemas import LexicalHit, VectorHit


def _lexical(number: int, rank: int) -> LexicalHit:
    return LexicalHit(
        chunk_id=UUID(f"00000000-0000-0000-0000-{number:012d}"),
        document_version_id=UUID(f"10000000-0000-0000-0000-{number:012d}"),
        citation_id=UUID(f"20000000-0000-0000-0000-{number:012d}"),
        chunk_index=number,
        locator_checksum=f"{number:064x}",
        text=f"evidence {number}",
        section_title=None,
        score=Decimal("2.5"),
        rank=rank,
    )


def test_rrf_collapses_same_chunk_and_uses_actual_channel_ranks() -> None:
    lexical = (_lexical(1, 1), _lexical(2, 2))
    vector = (
        VectorHit(chunk_id=lexical[1].chunk_id, score=Decimal("0.9"), rank=1),
        VectorHit(chunk_id=lexical[0].chunk_id, score=Decimal("0.8"), rank=2),
    )

    hits = reciprocal_rank_fusion(lexical, vector, k=60)

    assert [hit.chunk_id for hit in hits] == [lexical[0].chunk_id, lexical[1].chunk_id]
    assert hits[0].fusion_score == Decimal("0.032522474881")
    assert hits[0].lexical_rank == 1
    assert hits[0].vector_rank == 2


def test_lexical_only_fusion_keeps_vector_fields_null() -> None:
    hit = reciprocal_rank_fusion((_lexical(1, 1),), (), k=60)[0]

    assert hit.fusion_score == Decimal("0.016393442623")
    assert hit.vector_rank is None
    assert hit.vector_score is None
