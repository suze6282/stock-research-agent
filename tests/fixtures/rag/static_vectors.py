"""Fixed test-only vectors; not a semantic model and not production evidence."""

from __future__ import annotations

from decimal import Decimal, localcontext
from uuid import NAMESPACE_URL, UUID, uuid5

from stock_research_agent.domain.retrieval.enums import IndexStatus, VectorHealth
from stock_research_agent.domain.retrieval.schemas import (
    EmbeddingProviderMetadata,
    VectorBuildRequest,
    VectorHit,
    VectorIndexResult,
    VectorSearchRequest,
)

_MARKERS = ("SYNTHETIC_TEST_ONLY", "NOT_COMPANY_EVIDENCE", "OFFLINE", "NOT_LIVE")


class StaticFixtureEmbeddingProvider:
    def __init__(
        self,
        vectors: dict[str, tuple[Decimal, ...]],
        *,
        markers: tuple[str, ...],
    ) -> None:
        if markers != _MARKERS:
            raise ValueError("all synthetic fixture markers are required")
        dimensions = {len(vector) for vector in vectors.values()}
        if len(dimensions) != 1 or not vectors:
            raise ValueError("fixed vectors must share one nonempty dimension")
        self._vectors = dict(vectors)
        self._metadata = EmbeddingProviderMetadata(
            provider="STATIC_TEST_ONLY",
            model="FIXED_INDEPENDENT_INPUTS",
            version="static-test-v1",
            dimensions=dimensions.pop(),
            max_input_characters=256,
            production_approved=False,
        )

    @property
    def metadata(self) -> EmbeddingProviderMetadata:
        return self._metadata

    def health_status(self) -> VectorHealth:
        return VectorHealth.READY

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[Decimal, ...], ...]:
        return tuple(self.embed_query(text) for text in texts)

    def embed_query(self, text: str) -> tuple[Decimal, ...]:
        try:
            return self._vectors[text]
        except KeyError:
            raise ValueError("text has no independent fixed test vector") from None


class InMemoryStaticVectorIndex:
    def __init__(self, vectors: dict[UUID, tuple[Decimal, ...]]) -> None:
        dimensions = {len(vector) for vector in vectors.values()}
        if len(dimensions) != 1 or not vectors:
            raise ValueError("static index vectors must share one dimension")
        self._vectors = dict(vectors)
        self._dimensions = dimensions.pop()

    def build(self, request: VectorBuildRequest) -> VectorIndexResult:
        if not set(request.chunk_ids).issubset(self._vectors):
            return VectorIndexResult(
                status=IndexStatus.BLOCKED,
                warnings=("STATIC_VECTOR_MISSING",),
            )
        return VectorIndexResult(
            status=IndexStatus.COMPLETE,
            vector_index_version_id=uuid5(NAMESPACE_URL, request.index_name),
        )

    def search(self, request: VectorSearchRequest) -> tuple[VectorHit, ...]:
        if len(request.query_vector) != self._dimensions:
            raise ValueError("query vector dimension mismatch")
        scored = [
            (chunk_id, _cosine(request.query_vector, self._vectors[chunk_id]))
            for chunk_id in request.eligible_chunk_ids
            if chunk_id in self._vectors
        ]
        scored.sort(key=lambda item: (-item[1], str(item[0])))
        return tuple(
            VectorHit(chunk_id=chunk_id, score=score, rank=rank)
            for rank, (chunk_id, score) in enumerate(scored[: request.max_results], start=1)
        )


def _cosine(left: tuple[Decimal, ...], right: tuple[Decimal, ...]) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        dot = sum((a * b for a, b in zip(left, right, strict=True)), Decimal(0))
        left_norm = sum((value * value for value in left), Decimal(0)).sqrt()
        right_norm = sum((value * value for value in right), Decimal(0)).sqrt()
        if left_norm == 0 or right_norm == 0:
            return Decimal(0)
        return (dot / (left_norm * right_norm)).quantize(Decimal("0.000000000001"))
