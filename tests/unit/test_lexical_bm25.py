from __future__ import annotations

from decimal import Decimal

from stock_research_agent.domain.retrieval.lexical import bm25_score
from stock_research_agent.domain.retrieval.schemas import Bm25Stats


def test_bm25_matches_independently_calculated_golden_values() -> None:
    assert bm25_score(
        Bm25Stats(
            term_frequency=3,
            document_frequency=2,
            document_count=10,
            document_length=100,
            average_document_length=Decimal("80"),
        )
    ) == Decimal("2.209850840701")


def test_bm25_zero_term_frequency_is_exact_zero() -> None:
    assert bm25_score(
        Bm25Stats(
            term_frequency=0,
            document_frequency=2,
            document_count=10,
            document_length=100,
            average_document_length=Decimal("80"),
        )
    ) == Decimal("0E-12")
