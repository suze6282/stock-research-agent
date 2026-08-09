from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from stock_research_agent.domain.retrieval.enums import VectorHealth
from stock_research_agent.domain.retrieval.schemas import VectorSearchRequest
from stock_research_agent.domain.retrieval.vector import (
    BlockedEmbeddingProvider,
    EmbeddingBlockedError,
    EmbeddingProvider,
    VectorIndex,
)
from tests.fixtures.rag.static_vectors import (
    InMemoryStaticVectorIndex,
    StaticFixtureEmbeddingProvider,
)


def test_blocked_embedding_provider_has_fixed_safe_metadata_and_health() -> None:
    provider = BlockedEmbeddingProvider()

    assert isinstance(provider, EmbeddingProvider)
    assert provider.health_status() == VectorHealth.BLOCKED
    assert provider.metadata.model_dump() == {
        "provider": "NOT_CONFIGURED",
        "model": "NOT_CONFIGURED",
        "version": "blocked-v1",
        "dimensions": 1,
        "max_input_characters": 1,
        "production_approved": False,
    }
    assert "key" not in provider.metadata.model_dump_json().casefold()


def test_blocked_provider_never_embeds_or_performs_network_work() -> None:
    provider = BlockedEmbeddingProvider()

    with pytest.raises(EmbeddingBlockedError, match="EMBEDDING_PROVIDER_NOT_CONFIGURED"):
        provider.embed_documents(("text",))
    with pytest.raises(EmbeddingBlockedError, match="EMBEDDING_PROVIDER_NOT_CONFIGURED"):
        provider.embed_query("query")


def test_ports_are_runtime_checkable_without_concrete_backend() -> None:
    assert isinstance(BlockedEmbeddingProvider(), EmbeddingProvider)
    assert not isinstance(BlockedEmbeddingProvider(), VectorIndex)


def test_static_fixture_vectors_require_all_test_only_markers_and_fixed_inputs() -> None:
    with pytest.raises(ValueError, match="markers"):
        StaticFixtureEmbeddingProvider({"risk": (Decimal("1"), Decimal("0"))}, markers=())
    provider = StaticFixtureEmbeddingProvider(
        {"risk": (Decimal("1"), Decimal("0"))},
        markers=("SYNTHETIC_TEST_ONLY", "NOT_COMPANY_EVIDENCE", "OFFLINE", "NOT_LIVE"),
    )
    assert provider.embed_query("risk") == (Decimal("1"), Decimal("0"))
    with pytest.raises(ValueError, match="fixed"):
        provider.embed_query("unmapped")


def test_static_vector_index_uses_stable_cosine_order_and_eligible_filter() -> None:
    first = UUID("00000000-0000-0000-0000-000000000061")
    second = UUID("00000000-0000-0000-0000-000000000062")
    index = InMemoryStaticVectorIndex(
        {first: (Decimal("1"), Decimal("0")), second: (Decimal("0.5"), Decimal("0.5"))}
    )
    hits = index.search(
        VectorSearchRequest(
            vector_index_version_id=UUID("00000000-0000-0000-0000-000000000063"),
            security_id=UUID("00000000-0000-0000-0000-000000000064"),
            eligible_chunk_ids=(first, second),
            query_vector=(Decimal("1"), Decimal("0")),
            max_results=2,
        )
    )
    assert [hit.chunk_id for hit in hits] == [first, second]
