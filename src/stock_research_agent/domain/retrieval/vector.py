"""Pluggable vector ports and the safe production-blocked default."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from stock_research_agent.domain.retrieval.enums import VectorHealth
from stock_research_agent.domain.retrieval.schemas import (
    EmbeddingProviderMetadata,
    VectorBuildRequest,
    VectorHit,
    VectorIndexResult,
    VectorSearchRequest,
)


class EmbeddingBlockedError(RuntimeError):
    """Raised when a production embedding provider is not configured."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def metadata(self) -> EmbeddingProviderMetadata: ...

    def health_status(self) -> VectorHealth: ...

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[Decimal, ...], ...]: ...

    def embed_query(self, text: str) -> tuple[Decimal, ...]: ...


@runtime_checkable
class VectorIndex(Protocol):
    def build(self, request: VectorBuildRequest) -> VectorIndexResult: ...

    def search(self, request: VectorSearchRequest) -> tuple[VectorHit, ...]: ...


class BlockedEmbeddingProvider:
    _metadata = EmbeddingProviderMetadata(
        provider="NOT_CONFIGURED",
        model="NOT_CONFIGURED",
        version="blocked-v1",
        dimensions=1,
        max_input_characters=1,
        production_approved=False,
    )

    @property
    def metadata(self) -> EmbeddingProviderMetadata:
        return self._metadata

    def health_status(self) -> VectorHealth:
        return VectorHealth.BLOCKED

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[Decimal, ...], ...]:
        raise EmbeddingBlockedError("EMBEDDING_PROVIDER_NOT_CONFIGURED")

    def embed_query(self, text: str) -> tuple[Decimal, ...]:
        raise EmbeddingBlockedError("EMBEDDING_PROVIDER_NOT_CONFIGURED")
