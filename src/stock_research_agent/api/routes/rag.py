"""Strictly read-only, cache-only Stage 6 document and retrieval routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from stock_research_agent.api.dependencies import get_rag_query_service, require_database_ready
from stock_research_agent.api.errors import ApiError
from stock_research_agent.domain.retrieval.enums import RetrievalMode
from stock_research_agent.domain.retrieval.schemas import (
    EvidenceBundle,
    RagReadResult,
    RetrievalFilters,
    RetrievalRequest,
)
from stock_research_agent.domain.retrieval.service import PrecomputedRetrievalQueryService
from stock_research_agent.tools.schemas_rag import RagReadEnvelope

router = APIRouter(tags=["rag"], dependencies=[Depends(require_database_ready)])
RagService = Annotated[PrecomputedRetrievalQueryService, Depends(get_rag_query_service)]


def _scope(snapshot_id: UUID | None, research_as_of_time: datetime | None) -> None:
    if (snapshot_id is None) == (research_as_of_time is None):
        raise ApiError(
            code="INVALID_RETRIEVAL_SCOPE",
            message="Exactly one retrieval scope is required",
            status_code=422,
        )
    if research_as_of_time is not None and (
        research_as_of_time.tzinfo is None or research_as_of_time.utcoffset() is None
    ):
        raise ApiError(
            code="INVALID_RETRIEVAL_SCOPE",
            message="research_as_of_time must be timezone aware",
            status_code=422,
        )


def _envelope(value: RagReadResult) -> RagReadEnvelope:
    return RagReadEnvelope.model_validate(value.model_dump())


def _detail(value: RagReadResult) -> RagReadEnvelope:
    if not value.records and "RAG_RECORD_NOT_FOUND" in value.warnings:
        raise ApiError(
            code="RAG_RESOURCE_NOT_FOUND",
            message="The requested RAG resource was not found",
            status_code=404,
        )
    return _envelope(value)


@router.get("/document-versions", response_model=RagReadEnvelope)
def list_document_versions(
    service: RagService,
    security_id: Annotated[UUID, Query()],
    snapshot_id: Annotated[UUID | None, Query()] = None,
    research_as_of_time: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 20,
) -> RagReadEnvelope:
    _scope(snapshot_id, research_as_of_time)
    return _envelope(
        service.list_document_versions(
            security_id=security_id,
            snapshot_id=snapshot_id,
            research_as_of_time=research_as_of_time,
            limit=limit,
        )
    )


@router.get("/document-versions/{document_version_id}", response_model=RagReadEnvelope)
def get_document_metadata(service: RagService, document_version_id: UUID) -> RagReadEnvelope:
    return _detail(service.get_document_metadata(document_version_id))


@router.get("/rag/search", response_model=EvidenceBundle)
def search_document_chunks(
    service: RagService,
    security_id: Annotated[UUID, Query()],
    query: Annotated[str, Query(min_length=1, max_length=256)],
    mode: Annotated[RetrievalMode, Query()] = RetrievalMode.LEXICAL,
    snapshot_id: Annotated[UUID | None, Query()] = None,
    research_as_of_time: Annotated[datetime | None, Query()] = None,
    max_results: Annotated[int, Query(ge=1, le=20)] = 10,
) -> EvidenceBundle:
    _scope(snapshot_id, research_as_of_time)
    return service.lookup(
        RetrievalRequest(
            query=query,
            mode=mode,
            filters=RetrievalFilters(
                security_id=security_id,
                snapshot_id=snapshot_id,
                research_as_of_time=research_as_of_time,
            ),
            max_results=max_results,
        )
    )


@router.get("/document-chunks/{chunk_id}", response_model=RagReadEnvelope)
def get_document_chunk(service: RagService, chunk_id: UUID) -> RagReadEnvelope:
    return _detail(service.get_document_chunk(chunk_id))


@router.get("/citations/{citation_id}", response_model=RagReadEnvelope)
def get_citation(service: RagService, citation_id: UUID) -> RagReadEnvelope:
    return _detail(service.get_citation(citation_id))


@router.get("/citations/{citation_id}/verify", response_model=RagReadEnvelope)
def verify_citation(
    service: RagService,
    citation_id: UUID,
    snapshot_id: Annotated[UUID | None, Query()] = None,
    research_as_of_time: Annotated[datetime | None, Query()] = None,
    strict_historical: Annotated[bool, Query()] = True,
) -> RagReadEnvelope:
    _scope(snapshot_id, research_as_of_time)
    return _detail(
        service.verify_citation(
            citation_id,
            snapshot_id=snapshot_id,
            research_as_of_time=research_as_of_time,
            strict_historical=strict_historical,
        )
    )


@router.get("/retrieval-runs/{retrieval_run_id}", response_model=RagReadEnvelope)
def get_retrieval_run(service: RagService, retrieval_run_id: UUID) -> RagReadEnvelope:
    return _detail(service.get_retrieval_run(retrieval_run_id))


@router.get("/retrieval-runs/{retrieval_run_id}/evidence", response_model=RagReadEnvelope)
def get_evidence_bundle(service: RagService, retrieval_run_id: UUID) -> RagReadEnvelope:
    return _detail(service.get_evidence_bundle(retrieval_run_id))
