"""Persistence ports for lexical indexes and immutable retrieval runs."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from stock_research_agent.domain.retrieval.schemas import (
    EvidenceBundle,
    IndexableChunk,
    RetrievalCompletion,
    RetrievalHitRecord,
    RetrievalHitWrite,
    RetrievalRequest,
    RetrievalRunRecord,
    RetrievalRunWrite,
)


class LexicalChunkRepository(Protocol):
    def list_indexable_chunks(self, security_id: UUID) -> tuple[IndexableChunk, ...]: ...


class RetrievalWriteRepository(Protocol):
    def find_run_by_fingerprint(self, fingerprint: str) -> RetrievalRunRecord | None: ...

    def create_run(self, value: RetrievalRunWrite) -> RetrievalRunRecord: ...

    def acquire_run(self, value: RetrievalRunWrite) -> tuple[RetrievalRunRecord, bool]: ...

    def valid_citation_ids(
        self, citation_ids: tuple[UUID, ...], request: RetrievalRequest
    ) -> frozenset[UUID]: ...

    def add_hits(self, run_id: UUID, hits: tuple[RetrievalHitWrite, ...]) -> None: ...

    def finish_run(self, run_id: UUID, completion: RetrievalCompletion) -> RetrievalRunRecord: ...

    def list_hits(self, run_id: UUID, limit: int) -> tuple[RetrievalHitRecord, ...]: ...


class RetrievalReadRepository(Protocol):
    def find_bundle_for_request(
        self, request_basis_fingerprint: str, request: RetrievalRequest
    ) -> EvidenceBundle | None: ...

    def list_document_versions(
        self,
        *,
        security_id: UUID,
        snapshot_id: UUID | None,
        research_as_of_time: datetime | None,
        limit: int,
    ) -> tuple[dict[str, object], ...]: ...

    def get_document_metadata(self, record_id: UUID) -> dict[str, object] | None: ...

    def get_document_chunk(self, record_id: UUID) -> dict[str, object] | None: ...

    def get_citation(self, record_id: UUID) -> dict[str, object] | None: ...

    def verify_citation(
        self,
        record_id: UUID,
        *,
        snapshot_id: UUID | None,
        research_as_of_time: datetime | None,
        strict_historical: bool,
    ) -> dict[str, object] | None: ...

    def get_retrieval_run(self, record_id: UUID) -> dict[str, object] | None: ...

    def get_evidence_bundle(self, record_id: UUID) -> dict[str, object] | None: ...
