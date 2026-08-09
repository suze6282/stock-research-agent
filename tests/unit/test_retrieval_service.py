from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.retrieval.enums import RetrievalMode, RetrievalStatus
from stock_research_agent.domain.retrieval.schemas import (
    EvidenceBundle,
    HybridHit,
    LexicalHit,
    LexicalSearchRequest,
    PreparedRetrieval,
    RetrievalCompletion,
    RetrievalFilters,
    RetrievalHitRecord,
    RetrievalHitWrite,
    RetrievalRequest,
    RetrievalRunRecord,
    RetrievalRunWrite,
)
from stock_research_agent.domain.retrieval.service import (
    DeterministicRetrievalEngine,
    PrecomputedRetrievalQueryService,
    RetrievalExecutionService,
    canonical_request_fingerprint,
)

NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
SECURITY_ID = UUID("00000000-0000-0000-0000-000000000081")
SNAPSHOT_ID = UUID("00000000-0000-0000-0000-000000000082")


def _request() -> RetrievalRequest:
    return RetrievalRequest(
        query="risk factors",
        mode=RetrievalMode.HYBRID,
        filters=RetrievalFilters(security_id=SECURITY_ID, snapshot_id=SNAPSHOT_ID),
    )


class FakeEngine:
    def __init__(self) -> None:
        self.calls = 0

    def generation_ids(self, request: RetrievalRequest) -> tuple[UUID | None, UUID | None]:
        return UUID("00000000-0000-0000-0000-000000000083"), None

    def retrieve(self, request: RetrievalRequest) -> PreparedRetrieval:
        self.calls += 1
        return PreparedRetrieval(
            status=RetrievalStatus.PARTIAL,
            lexical_index_version_id=UUID("00000000-0000-0000-0000-000000000083"),
            vector_index_version_id=None,
            hits=(
                HybridHit(
                    chunk_id=UUID("00000000-0000-0000-0000-000000000084"),
                    document_version_id=UUID("00000000-0000-0000-0000-000000000085"),
                    citation_id=UUID("00000000-0000-0000-0000-000000000086"),
                    chunk_index=0,
                    locator_checksum="a" * 64,
                    text="bounded evidence",
                    section_title=None,
                    lexical_rank=1,
                    vector_rank=None,
                    lexical_score=Decimal("1"),
                    vector_score=None,
                    fusion_score=Decimal("0.016393442623"),
                    phrase_match=False,
                    heading_token_matches=0,
                    rerank_reason="FUSION_SCORE",
                ),
            ),
            warnings=("VECTOR_CHANNEL_BLOCKED",),
        )


class FakeWriteRepository:
    def __init__(self) -> None:
        self.runs: dict[str, RetrievalRunRecord] = {}
        self.hits: dict[UUID, list[RetrievalHitRecord]] = {}
        self.rejected_citations: set[UUID] = set()

    def valid_citation_ids(
        self, citation_ids: tuple[UUID, ...], request: RetrievalRequest
    ) -> frozenset[UUID]:
        return frozenset(value for value in citation_ids if value not in self.rejected_citations)

    def find_run_by_fingerprint(self, fingerprint: str) -> RetrievalRunRecord | None:
        return self.runs.get(fingerprint)

    def create_run(self, value: RetrievalRunWrite) -> RetrievalRunRecord:
        row = RetrievalRunRecord(
            id=uuid4(), created_at=NOW, completed_at=None, warnings=(), **value.model_dump()
        )
        self.runs[value.request_fingerprint] = row
        return row

    def acquire_run(self, value: RetrievalRunWrite) -> tuple[RetrievalRunRecord, bool]:
        existing = self.find_run_by_fingerprint(value.request_fingerprint)
        if existing is not None:
            return existing, False
        return self.create_run(value), True

    def add_hits(self, run_id: UUID, hits: tuple[RetrievalHitWrite, ...]) -> None:
        self.hits[run_id] = [
            RetrievalHitRecord(
                id=uuid4(), retrieval_run_id=run_id, created_at=NOW, **hit.model_dump()
            )
            for hit in hits
        ]

    def finish_run(self, run_id: UUID, completion: RetrievalCompletion) -> RetrievalRunRecord:
        fingerprint, current = next(
            (key, row) for key, row in self.runs.items() if row.id == run_id
        )
        terminal = current.model_copy(
            update={
                "status": completion.status,
                "warnings": completion.warnings,
                "completed_at": NOW,
            }
        )
        self.runs[fingerprint] = terminal
        return terminal

    def list_hits(self, run_id: UUID, limit: int) -> tuple[RetrievalHitRecord, ...]:
        return tuple(self.hits.get(run_id, ())[:limit])


class FakeReadRepository:
    def __init__(self, bundle: EvidenceBundle | None = None) -> None:
        self.bundle = bundle
        self.calls = 0

    def find_bundle_for_request(
        self, request_basis_fingerprint: str, request: RetrievalRequest
    ) -> EvidenceBundle | None:
        self.calls += 1
        return self.bundle


def test_explicit_execution_persists_once_and_reuses_terminal_fingerprint() -> None:
    repository = FakeWriteRepository()
    engine = FakeEngine()
    service = RetrievalExecutionService(repository, engine)

    first = service.execute(_request())
    second = service.execute(_request())

    assert first.status == RetrievalStatus.PARTIAL
    assert first.reused is False
    assert second.reused is True
    assert second.run == first.run
    assert engine.calls == 1
    assert len(repository.runs) == 1
    assert len(first.hits) == 1


def test_execution_does_not_write_hits_for_run_owned_by_another_caller() -> None:
    repository = FakeWriteRepository()
    engine = FakeEngine()
    lexical_id, vector_id = engine.generation_ids(_request())
    fingerprint = canonical_request_fingerprint(
        _request(),
        lexical_index_version_id=lexical_id,
        vector_index_version_id=vector_id,
    )
    repository.create_run(
        RetrievalRunWrite(
            request_fingerprint=fingerprint,
            request_basis_fingerprint="c" * 64,
            security_id=SECURITY_ID,
            snapshot_id=SNAPSHOT_ID,
            research_as_of_time=None,
            mode=RetrievalMode.HYBRID,
            original_query="risk factors",
            normalized_query="risk factors",
            max_results=10,
            tokenizer_version="tokenizer-v1",
            lexical_index_version_id=lexical_id,
            vector_index_version_id=vector_id,
            fusion_version="fusion-v1",
            reranker_version="stable-reranker-v1",
            status=RetrievalStatus.PARTIAL,
        )
    )

    result = RetrievalExecutionService(repository, engine).execute(_request())

    assert result.status == RetrievalStatus.BLOCKED
    assert result.warnings == ("RETRIEVAL_RUN_IN_PROGRESS",)
    assert result.reused is True
    assert result.hits == ()
    assert repository.hits == {}
    assert engine.calls == 0


def test_persisted_retrieval_hit_requires_a_citation() -> None:
    with pytest.raises(ValidationError):
        RetrievalHitWrite(
            chunk_id=uuid4(),
            citation_id=None,
            final_rank=1,
            fusion_score=Decimal("1"),
            rerank_reason="STABLE_TIE",
        )


def test_execution_excludes_unverified_citations_and_blocks_empty_evidence() -> None:
    repository = FakeWriteRepository()
    citation_id = UUID("00000000-0000-0000-0000-000000000086")
    repository.rejected_citations.add(citation_id)

    result = RetrievalExecutionService(repository, FakeEngine()).execute(_request())

    assert result.status == RetrievalStatus.BLOCKED
    assert result.hits == ()
    assert result.warnings == ("VECTOR_CHANNEL_BLOCKED", "NO_VALID_CITATIONS")


def test_request_fingerprint_is_canonical_and_versioned() -> None:
    lexical_id = UUID("00000000-0000-0000-0000-000000000083")
    next_lexical_id = UUID("00000000-0000-0000-0000-000000000099")
    assert canonical_request_fingerprint(
        _request(), lexical_index_version_id=lexical_id, vector_index_version_id=None
    ) == canonical_request_fingerprint(
        _request(), lexical_index_version_id=lexical_id, vector_index_version_id=None
    )
    changed = _request().model_copy(update={"query": "revenue"})
    assert canonical_request_fingerprint(
        _request(), lexical_index_version_id=lexical_id, vector_index_version_id=None
    ) != canonical_request_fingerprint(
        changed, lexical_index_version_id=lexical_id, vector_index_version_id=None
    )
    assert canonical_request_fingerprint(
        _request(), lexical_index_version_id=lexical_id, vector_index_version_id=None
    ) != canonical_request_fingerprint(
        _request(), lexical_index_version_id=next_lexical_id, vector_index_version_id=None
    )


def test_cache_only_lookup_returns_blocked_without_writes_or_refresh() -> None:
    repository = FakeReadRepository()
    service = PrecomputedRetrievalQueryService(repository)

    bundle = service.lookup(_request())

    assert bundle.status == RetrievalStatus.BLOCKED
    assert bundle.items == ()
    assert bundle.warnings == ("RETRIEVAL_RUN_NOT_PRECOMPUTED",)
    assert repository.calls == 1


class FakeLexicalSearch:
    def __init__(self) -> None:
        self.requests: list[LexicalSearchRequest] = []

    def search(self, request: LexicalSearchRequest) -> tuple[LexicalHit, ...]:
        self.requests.append(request)
        return (
            LexicalHit(
                chunk_id=UUID("00000000-0000-0000-0000-000000000084"),
                document_version_id=UUID("00000000-0000-0000-0000-000000000085"),
                citation_id=UUID("00000000-0000-0000-0000-000000000086"),
                chunk_index=0,
                locator_checksum="a" * 64,
                text="risk factors",
                section_title="Risk Factors",
                score=Decimal("1.25"),
                rank=1,
                phrase_match=True,
                heading_token_matches=2,
            ),
        )


def test_deterministic_engine_passes_lexical_and_truthfully_degrades_hybrid() -> None:
    search = FakeLexicalSearch()
    index_id = UUID("00000000-0000-0000-0000-000000000083")
    engine = DeterministicRetrievalEngine(index_id, search)

    lexical = engine.retrieve(_request().model_copy(update={"mode": RetrievalMode.LEXICAL}))
    hybrid = engine.retrieve(_request().model_copy(update={"mode": RetrievalMode.HYBRID}))
    vector = engine.retrieve(_request().model_copy(update={"mode": RetrievalMode.VECTOR}))

    assert lexical.status == RetrievalStatus.PASS
    assert lexical.warnings == ()
    assert lexical.hits[0].rerank_reason == "EXACT_PHRASE"
    assert hybrid.status == RetrievalStatus.PARTIAL
    assert hybrid.warnings == ("VECTOR_CHANNEL_BLOCKED",)
    assert vector.status == RetrievalStatus.BLOCKED
    assert vector.hits == ()
    assert vector.warnings == ("EMBEDDING_PROVIDER_NOT_CONFIGURED",)
    assert len(search.requests) == 2
