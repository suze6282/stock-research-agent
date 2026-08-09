"""Strict inputs and bounded outputs for Stage 6 read-only RAG tools."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from stock_research_agent.domain.retrieval.enums import RetrievalMode, RetrievalStatus


class RagToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)


class ExactScopeInput(RagToolModel):
    security_id: UUID
    snapshot_id: UUID | None = None
    research_as_of_time: datetime | None = None

    @field_validator("research_as_of_time")
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("research_as_of_time must be timezone aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def exact_scope(self) -> Self:
        if (self.snapshot_id is None) == (self.research_as_of_time is None):
            raise ValueError("exactly one scope is required")
        return self


class ListDocumentVersionsInput(ExactScopeInput):
    limit: int = Field(default=20, ge=1, le=20)


class GetDocumentMetadataInput(RagToolModel):
    document_version_id: UUID


class SearchDocumentChunksInput(ExactScopeInput):
    query: str = Field(min_length=1, max_length=256)
    mode: RetrievalMode = RetrievalMode.LEXICAL
    max_results: int = Field(default=10, ge=1, le=20)


class GetDocumentChunkInput(RagToolModel):
    chunk_id: UUID


class GetCitationInput(RagToolModel):
    citation_id: UUID


class VerifyCitationInput(GetCitationInput):
    snapshot_id: UUID | None = None
    research_as_of_time: datetime | None = None
    strict_historical: bool = True

    @field_validator("research_as_of_time")
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("research_as_of_time must be timezone aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def exact_scope(self) -> Self:
        if (self.snapshot_id is None) == (self.research_as_of_time is None):
            raise ValueError("exactly one scope is required")
        return self


class GetEvidenceBundleInput(RagToolModel):
    retrieval_run_id: UUID


class GetRetrievalRunInput(RagToolModel):
    retrieval_run_id: UUID


class RagReadEnvelope(RagToolModel):
    status: RetrievalStatus
    records: tuple[dict[str, object], ...] = Field(default=(), max_length=20)
    warnings: tuple[str, ...] = ()
