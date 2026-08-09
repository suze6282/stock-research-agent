"""Thin read-only RAG adapters; search reads precomputed retrieval only."""

from __future__ import annotations

from pydantic import BaseModel

from stock_research_agent.domain.retrieval.enums import RetrievalStatus
from stock_research_agent.domain.retrieval.schemas import RetrievalFilters, RetrievalRequest
from stock_research_agent.domain.retrieval.service import PrecomputedRetrievalQueryService
from stock_research_agent.tools.schemas_rag import (
    GetCitationInput,
    GetDocumentChunkInput,
    GetDocumentMetadataInput,
    GetEvidenceBundleInput,
    GetRetrievalRunInput,
    ListDocumentVersionsInput,
    RagReadEnvelope,
    SearchDocumentChunksInput,
    VerifyCitationInput,
)


class SearchDocumentChunksTool:
    def __init__(self, service: PrecomputedRetrievalQueryService) -> None:
        self._service = service

    def __call__(self, value: BaseModel) -> BaseModel:
        request = SearchDocumentChunksInput.model_validate(value)
        return self._service.lookup(
            RetrievalRequest(
                query=request.query,
                mode=request.mode,
                filters=RetrievalFilters(
                    security_id=request.security_id,
                    snapshot_id=request.snapshot_id,
                    research_as_of_time=request.research_as_of_time,
                ),
                max_results=request.max_results,
            )
        )


class RagReadTool:
    def __init__(self, service: PrecomputedRetrievalQueryService, operation: str) -> None:
        self._service = service
        self._operation = operation

    def __call__(self, value: BaseModel) -> BaseModel:
        if self._operation == "list_document_versions":
            list_request = ListDocumentVersionsInput.model_validate(value)
            result = self._service.list_document_versions(
                security_id=list_request.security_id,
                snapshot_id=list_request.snapshot_id,
                research_as_of_time=list_request.research_as_of_time,
                limit=list_request.limit,
            )
        elif self._operation == "get_document_metadata":
            metadata_request = GetDocumentMetadataInput.model_validate(value)
            result = self._service.get_document_metadata(metadata_request.document_version_id)
        elif self._operation == "get_document_chunk":
            chunk_request = GetDocumentChunkInput.model_validate(value)
            result = self._service.get_document_chunk(chunk_request.chunk_id)
        elif self._operation == "get_citation":
            citation_request = GetCitationInput.model_validate(value)
            result = self._service.get_citation(citation_request.citation_id)
        elif self._operation == "verify_citation":
            verify_request = VerifyCitationInput.model_validate(value)
            result = self._service.verify_citation(
                verify_request.citation_id,
                snapshot_id=verify_request.snapshot_id,
                research_as_of_time=verify_request.research_as_of_time,
                strict_historical=verify_request.strict_historical,
            )
        elif self._operation == "get_evidence_bundle":
            bundle_request = GetEvidenceBundleInput.model_validate(value)
            result = self._service.get_evidence_bundle(bundle_request.retrieval_run_id)
        elif self._operation == "get_retrieval_run":
            run_request = GetRetrievalRunInput.model_validate(value)
            result = self._service.get_retrieval_run(run_request.retrieval_run_id)
        else:
            return RagReadEnvelope(
                status=RetrievalStatus.BLOCKED,
                warnings=("RAG_READ_OPERATION_NOT_APPROVED",),
            )
        return RagReadEnvelope.model_validate(result.model_dump())
