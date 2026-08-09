"""Explicit retrieval-run writes and strictly cache-only evidence reads."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime
from typing import Protocol
from uuid import UUID

from stock_research_agent.domain.retrieval.enums import RetrievalMode, RetrievalStatus
from stock_research_agent.domain.retrieval.hybrid import reciprocal_rank_fusion, stable_rerank
from stock_research_agent.domain.retrieval.repositories import (
    RetrievalReadRepository,
    RetrievalWriteRepository,
)
from stock_research_agent.domain.retrieval.schemas import (
    EvidenceBundle,
    LexicalHit,
    LexicalSearchRequest,
    PreparedRetrieval,
    RagReadResult,
    RetrievalCompletion,
    RetrievalExecutionResult,
    RetrievalHitWrite,
    RetrievalRequest,
    RetrievalRunRecord,
    RetrievalRunWrite,
)
from stock_research_agent.domain.retrieval.tokenizer import VersionedTokenizer

_TOKENIZER_VERSION = "tokenizer-v1"
_FUSION_VERSION = "fusion-v1"
_RERANKER_VERSION = "stable-reranker-v1"


class RetrievalEngine(Protocol):
    def generation_ids(self, request: RetrievalRequest) -> tuple[UUID | None, UUID | None]: ...

    def retrieve(self, request: RetrievalRequest) -> PreparedRetrieval: ...


class LexicalSearch(Protocol):
    def search(self, request: LexicalSearchRequest) -> tuple[LexicalHit, ...]: ...


class DeterministicRetrievalEngine:
    """Compose lexical retrieval with an honestly blocked production vector channel."""

    def __init__(self, lexical_index_version_id: UUID, lexical_search: LexicalSearch) -> None:
        self._lexical_index_version_id = lexical_index_version_id
        self._lexical_search = lexical_search
        self._tokenizer = VersionedTokenizer()

    def generation_ids(self, request: RetrievalRequest) -> tuple[UUID | None, UUID | None]:
        if request.mode == RetrievalMode.VECTOR:
            return None, None
        return self._lexical_index_version_id, None

    def retrieve(self, request: RetrievalRequest) -> PreparedRetrieval:
        if request.mode == RetrievalMode.VECTOR:
            return PreparedRetrieval(
                status=RetrievalStatus.BLOCKED,
                lexical_index_version_id=None,
                vector_index_version_id=None,
                warnings=("EMBEDDING_PROVIDER_NOT_CONFIGURED",),
            )
        query = self._tokenizer.tokenize_query(request.query)
        lexical = self._lexical_search.search(
            LexicalSearchRequest(
                index_version_id=self._lexical_index_version_id,
                tokenized_query=query,
                filters=request.filters,
                max_results=request.max_results,
            )
        )
        hits = stable_rerank(query, reciprocal_rank_fusion(lexical, ()))
        if request.mode == RetrievalMode.HYBRID:
            return PreparedRetrieval(
                status=RetrievalStatus.PARTIAL,
                lexical_index_version_id=self._lexical_index_version_id,
                vector_index_version_id=None,
                hits=hits,
                warnings=("VECTOR_CHANNEL_BLOCKED",),
            )
        return PreparedRetrieval(
            status=RetrievalStatus.PASS,
            lexical_index_version_id=self._lexical_index_version_id,
            vector_index_version_id=None,
            hits=hits,
        )


def canonical_request_basis_fingerprint(request: RetrievalRequest) -> str:
    normalized_query = " ".join(unicodedata.normalize("NFKC", request.query).casefold().split())
    payload = {
        "query": normalized_query,
        "mode": request.mode.value,
        "filters": request.filters.model_dump(mode="json"),
        "max_results": request.max_results,
        "tokenizer_version": _TOKENIZER_VERSION,
        "fusion_version": _FUSION_VERSION,
        "reranker_version": _RERANKER_VERSION,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def canonical_request_fingerprint(
    request: RetrievalRequest,
    *,
    lexical_index_version_id: UUID | None,
    vector_index_version_id: UUID | None,
) -> str:
    payload = {
        "request_basis_fingerprint": canonical_request_basis_fingerprint(request),
        "lexical_index_version_id": (
            None if lexical_index_version_id is None else str(lexical_index_version_id)
        ),
        "vector_index_version_id": (
            None if vector_index_version_id is None else str(vector_index_version_id)
        ),
        "fusion_version": _FUSION_VERSION,
        "reranker_version": _RERANKER_VERSION,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class RetrievalExecutionService:
    def __init__(
        self,
        repository: RetrievalWriteRepository,
        engine: RetrievalEngine,
    ) -> None:
        self._repository = repository
        self._engine = engine

    def execute(self, request: RetrievalRequest) -> RetrievalExecutionResult:
        lexical_index_version_id, vector_index_version_id = self._engine.generation_ids(request)
        fingerprint = canonical_request_fingerprint(
            request,
            lexical_index_version_id=lexical_index_version_id,
            vector_index_version_id=vector_index_version_id,
        )
        existing = self._repository.find_run_by_fingerprint(fingerprint)
        if existing is not None and existing.completed_at is not None:
            return RetrievalExecutionResult(
                status=existing.status,
                run=existing,
                hits=self._repository.list_hits(existing.id, request.max_results),
                reused=True,
                warnings=existing.warnings,
            )
        if existing is not None:
            return _retrieval_in_progress(existing)
        prepared = self._engine.retrieve(request)
        normalized_query = " ".join(unicodedata.normalize("NFKC", request.query).casefold().split())
        run, acquired = self._repository.acquire_run(
            RetrievalRunWrite(
                request_fingerprint=fingerprint,
                request_basis_fingerprint=canonical_request_basis_fingerprint(request),
                security_id=request.filters.security_id,
                snapshot_id=request.filters.snapshot_id,
                research_as_of_time=request.filters.research_as_of_time,
                mode=request.mode,
                original_query=request.query,
                normalized_query=normalized_query,
                max_results=request.max_results,
                tokenizer_version=_TOKENIZER_VERSION,
                lexical_index_version_id=prepared.lexical_index_version_id,
                vector_index_version_id=prepared.vector_index_version_id,
                fusion_version=_FUSION_VERSION,
                reranker_version=_RERANKER_VERSION,
                status=prepared.status,
            )
        )
        if not acquired:
            if run.completed_at is not None:
                return RetrievalExecutionResult(
                    status=run.status,
                    run=run,
                    hits=self._repository.list_hits(run.id, request.max_results),
                    reused=True,
                    warnings=run.warnings,
                )
            return _retrieval_in_progress(run)
        candidate_hits = prepared.hits[: request.max_results]
        valid_citation_ids = self._repository.valid_citation_ids(
            tuple(hit.citation_id for hit in candidate_hits), request
        )
        verified_hits = tuple(
            hit for hit in candidate_hits if hit.citation_id in valid_citation_ids
        )
        status = prepared.status
        warnings = prepared.warnings
        if len(verified_hits) != len(candidate_hits):
            if verified_hits:
                if status == RetrievalStatus.PASS:
                    status = RetrievalStatus.PARTIAL
                warnings += ("INVALID_CITATIONS_EXCLUDED",)
            else:
                status = RetrievalStatus.BLOCKED
                warnings += ("NO_VALID_CITATIONS",)
        writes = tuple(
            RetrievalHitWrite(
                chunk_id=hit.chunk_id,
                citation_id=hit.citation_id,
                final_rank=rank,
                lexical_rank=hit.lexical_rank,
                vector_rank=hit.vector_rank,
                fusion_score=hit.fusion_score,
                rerank_reason=hit.rerank_reason,
            )
            for rank, hit in enumerate(verified_hits, start=1)
        )
        self._repository.add_hits(run.id, writes)
        terminal = self._repository.finish_run(
            run.id,
            RetrievalCompletion(status=status, warnings=warnings),
        )
        return RetrievalExecutionResult(
            status=terminal.status,
            run=terminal,
            hits=self._repository.list_hits(terminal.id, request.max_results),
            reused=False,
            warnings=terminal.warnings,
        )


class PrecomputedRetrievalQueryService:
    def __init__(self, repository: RetrievalReadRepository) -> None:
        self._repository = repository

    def lookup(self, request: RetrievalRequest) -> EvidenceBundle:
        bundle = self._repository.find_bundle_for_request(
            canonical_request_basis_fingerprint(request), request
        )
        if bundle is not None:
            return bundle
        return EvidenceBundle(
            status=RetrievalStatus.BLOCKED,
            retrieval_run_id=None,
            mode=request.mode,
            research_as_of_time=request.filters.research_as_of_time,
            snapshot_id=request.filters.snapshot_id,
            lexical_index_version_id=None,
            vector_index_version_id=None,
            warnings=("RETRIEVAL_RUN_NOT_PRECOMPUTED",),
        )

    def list_document_versions(
        self,
        *,
        security_id: UUID,
        snapshot_id: UUID | None,
        research_as_of_time: datetime | None,
        limit: int,
    ) -> RagReadResult:
        records = self._repository.list_document_versions(
            security_id=security_id,
            snapshot_id=snapshot_id,
            research_as_of_time=research_as_of_time,
            limit=min(max(limit, 1), 20),
        )
        return _read_result(records, "COMPANY_BODY_NOT_AVAILABLE")

    def get_document_metadata(self, record_id: UUID) -> RagReadResult:
        return _single_read(self._repository.get_document_metadata(record_id))

    def get_document_chunk(self, record_id: UUID) -> RagReadResult:
        return _single_read(self._repository.get_document_chunk(record_id))

    def get_citation(self, record_id: UUID) -> RagReadResult:
        return _single_read(self._repository.get_citation(record_id))

    def verify_citation(
        self,
        record_id: UUID,
        *,
        snapshot_id: UUID | None,
        research_as_of_time: datetime | None,
        strict_historical: bool,
    ) -> RagReadResult:
        record = self._repository.verify_citation(
            record_id,
            snapshot_id=snapshot_id,
            research_as_of_time=research_as_of_time,
            strict_historical=strict_historical,
        )
        if record is None:
            return _single_read(None)
        if record.get("citation_status") == "VALID":
            return _single_read(record)
        raw_warnings = record.get("warnings", ("CITATION_VERIFICATION_BLOCKED",))
        warnings = (
            tuple(str(value) for value in raw_warnings)
            if isinstance(raw_warnings, (tuple, list))
            else ("CITATION_VERIFICATION_BLOCKED",)
        )
        return RagReadResult(
            status=RetrievalStatus.BLOCKED,
            records=(record,),
            warnings=warnings,
        )

    def get_retrieval_run(self, record_id: UUID) -> RagReadResult:
        return _status_read(self._repository.get_retrieval_run(record_id))

    def get_evidence_bundle(self, record_id: UUID) -> RagReadResult:
        return _status_read(self._repository.get_evidence_bundle(record_id))


def _single_read(record: dict[str, object] | None) -> RagReadResult:
    return _read_result(() if record is None else (record,), "RAG_RECORD_NOT_FOUND")


def _status_read(record: dict[str, object] | None) -> RagReadResult:
    if record is None:
        return _single_read(None)
    raw_status = record.get("status", RetrievalStatus.PASS)
    try:
        status = RetrievalStatus(str(raw_status))
    except ValueError:
        status = RetrievalStatus.PASS
    raw_warnings = record.get("warnings", ())
    warnings = (
        tuple(str(value) for value in raw_warnings)
        if isinstance(raw_warnings, (list, tuple))
        else ()
    )
    return RagReadResult(status=status, records=(record,), warnings=warnings)


def _read_result(records: tuple[dict[str, object], ...], missing_warning: str) -> RagReadResult:
    if records:
        return RagReadResult(status=RetrievalStatus.PASS, records=records)
    return RagReadResult(status=RetrievalStatus.BLOCKED, warnings=(missing_warning,))


def _retrieval_in_progress(run: RetrievalRunRecord) -> RetrievalExecutionResult:
    return RetrievalExecutionResult(
        status=RetrievalStatus.BLOCKED,
        run=run,
        hits=(),
        reused=True,
        warnings=("RETRIEVAL_RUN_IN_PROGRESS",),
    )
