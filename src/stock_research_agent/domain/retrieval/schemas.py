"""Strict immutable schemas for deterministic retrieval and evidence."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

from stock_research_agent.domain.documents.enums import (
    CitationStatus,
    DocumentLanguage,
    LocatorType,
    TrustLevel,
)
from stock_research_agent.domain.retrieval.enums import (
    IndexStatus,
    RetrievalMode,
    RetrievalStatus,
)

_SHA = re.compile(r"[0-9a-f]{64}\Z")
DocumentType = Literal[
    "ANNUAL_REPORT",
    "QUARTERLY_REPORT",
    "INTERIM_REPORT",
    "EARNINGS_RELEASE",
    "MATERIAL_ANNOUNCEMENT",
    "SEC_10_K",
    "SEC_10_Q",
    "SEC_8_K",
    "INVESTOR_PRESENTATION",
    "OTHER",
]


class RetrievalModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        from_attributes=True,
        hide_input_in_errors=True,
        strict=True,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone aware")
    return value.astimezone(UTC)


def _optional_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _utc(value)


def _sha(value: str) -> str:
    if _SHA.fullmatch(value) is None:
        raise ValueError("value must be a lowercase SHA-256 digest")
    return value


def _reject_float(value: object) -> object:
    if isinstance(value, float):
        raise ValueError("binary float is not accepted")
    return value


def _finite(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("Decimal must be finite")
    return value


ExactDecimal = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    AfterValidator(_finite),
    PlainSerializer(lambda value: str(value), return_type=str, when_used="json"),
]


class LexicalToken(RetrievalModel):
    value: str = Field(min_length=1, max_length=64)
    position: int = Field(ge=0, le=4095)


class TokenizedQuery(RetrievalModel):
    original_query: str = Field(min_length=1, max_length=256)
    normalized_query: str = Field(min_length=1, max_length=256)
    tokenizer_version: Literal["tokenizer-v1"] = "tokenizer-v1"
    tokens: tuple[LexicalToken, ...] = Field(min_length=1, max_length=64)


class RetrievalFilters(RetrievalModel):
    security_id: UUID
    snapshot_id: UUID | None = None
    research_as_of_time: datetime | None = None
    document_types: tuple[DocumentType, ...] = Field(default=(), max_length=10)
    languages: tuple[DocumentLanguage, ...] = Field(default=(), max_length=4)
    trust_levels: tuple[TrustLevel, ...] = Field(default=(), max_length=5)
    section_paths: tuple[str, ...] = Field(default=(), max_length=20)
    strict_unknown_publication: bool = True

    _validate_time = field_validator("research_as_of_time")(_optional_utc)

    @model_validator(mode="after")
    def require_one_scope(self) -> Self:
        if (self.snapshot_id is None) == (self.research_as_of_time is None):
            raise ValueError("exactly one of snapshot_id or research_as_of_time is required")
        return self


class RetrievalRequest(RetrievalModel):
    query: str = Field(min_length=1, max_length=256)
    mode: RetrievalMode
    filters: RetrievalFilters
    max_results: int = Field(default=10, ge=1, le=20)


class LexicalBuildRequest(RetrievalModel):
    index_name: str = Field(min_length=1, max_length=64)
    security_id: UUID
    snapshot_id: UUID | None = None
    index_as_of_time: datetime | None = None
    tokenizer_version: Literal["tokenizer-v1"] = "tokenizer-v1"
    chunk_version: Literal["chunk-v1"] = "chunk-v1"
    scoring_version: Literal["lexical-rank-v1"] = "lexical-rank-v1"

    _validate_time = field_validator("index_as_of_time")(_optional_utc)

    @model_validator(mode="after")
    def require_one_scope(self) -> Self:
        if (self.snapshot_id is None) == (self.index_as_of_time is None):
            raise ValueError("exactly one lexical index scope is required")
        return self


class IndexableChunk(RetrievalModel):
    chunk_id: UUID
    document_version_id: UUID
    document_checksum: str
    security_id: UUID
    published_at: datetime | None
    snapshot_ids: tuple[UUID, ...]
    chunk_index: int = Field(ge=0)
    locator_checksum: str
    text: str = Field(min_length=1, max_length=1600)
    section_title: str | None = Field(default=None, max_length=1000)
    document_type: DocumentType
    language: DocumentLanguage
    trust_level: TrustLevel
    superseded_at: datetime | None = None
    supersession_time_unknown: bool = False

    _validate_checksums = field_validator("document_checksum", "locator_checksum")(_sha)
    _validate_times = field_validator("published_at", "superseded_at")(_optional_utc)


class LexicalPostingDraft(RetrievalModel):
    token: str = Field(min_length=1, max_length=64)
    chunk_id: UUID
    term_frequency: int = Field(ge=1)
    field_kind: Literal["BODY", "SECTION_TITLE"]
    positions: tuple[int, ...]


class LexicalIndexResult(RetrievalModel):
    status: IndexStatus
    index_version_id: UUID | None = None
    document_set_checksum: str | None = None
    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    average_chunk_length: ExactDecimal | None = None
    postings: tuple[LexicalPostingDraft, ...] = ()
    reused: bool = False
    warnings: tuple[str, ...] = ()

    _validate_checksum = field_validator("document_set_checksum")(
        lambda value: None if value is None else _sha(value)
    )


class LexicalSearchRequest(RetrievalModel):
    index_version_id: UUID
    tokenized_query: TokenizedQuery
    filters: RetrievalFilters
    max_results: int = Field(default=10, ge=1, le=20)


class LexicalHit(RetrievalModel):
    chunk_id: UUID
    document_version_id: UUID
    citation_id: UUID
    chunk_index: int = Field(ge=0)
    locator_checksum: str
    text: str = Field(min_length=1, max_length=1600)
    section_title: str | None = Field(default=None, max_length=1000)
    score: ExactDecimal
    rank: int = Field(ge=1, le=20)
    phrase_match: bool = False
    heading_token_matches: int = Field(default=0, ge=0, le=64)

    _validate_locator = field_validator("locator_checksum")(_sha)


class Bm25Stats(RetrievalModel):
    term_frequency: int = Field(ge=0)
    document_frequency: int = Field(ge=0)
    document_count: int = Field(ge=1)
    document_length: int = Field(ge=0)
    average_document_length: ExactDecimal

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.document_frequency > self.document_count:
            raise ValueError("document frequency cannot exceed document count")
        if self.average_document_length <= 0:
            raise ValueError("average document length must be positive")
        return self


class EmbeddingProviderMetadata(RetrievalModel):
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    dimensions: int = Field(ge=1, le=65_536)
    max_input_characters: int = Field(ge=1, le=5_000_000)
    production_approved: bool


class VectorBuildRequest(RetrievalModel):
    security_id: UUID
    chunk_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100_000)
    index_name: str = Field(min_length=1, max_length=64)


class VectorIndexResult(RetrievalModel):
    status: IndexStatus
    vector_index_version_id: UUID | None = None
    warnings: tuple[str, ...] = ()


class VectorSearchRequest(RetrievalModel):
    vector_index_version_id: UUID
    security_id: UUID
    eligible_chunk_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100_000)
    query_vector: tuple[ExactDecimal, ...] = Field(min_length=1, max_length=65_536)
    max_results: int = Field(default=10, ge=1, le=20)


class VectorHit(RetrievalModel):
    chunk_id: UUID
    score: ExactDecimal
    rank: int = Field(ge=1, le=20)


class HybridHit(RetrievalModel):
    chunk_id: UUID
    document_version_id: UUID
    citation_id: UUID
    chunk_index: int = Field(ge=0)
    locator_checksum: str
    text: str = Field(min_length=1, max_length=1600)
    section_title: str | None = Field(default=None, max_length=1000)
    lexical_rank: int | None = Field(default=None, ge=1, le=20)
    vector_rank: int | None = Field(default=None, ge=1, le=20)
    lexical_score: ExactDecimal | None = None
    vector_score: ExactDecimal | None = None
    fusion_score: ExactDecimal
    phrase_match: bool
    heading_token_matches: int = Field(ge=0, le=64)
    rerank_reason: Literal["EXACT_PHRASE", "HEADING_MATCH", "FUSION_SCORE", "STABLE_TIE"]

    _validate_locator = field_validator("locator_checksum")(_sha)

    @model_validator(mode="after")
    def require_channel(self) -> Self:
        if self.lexical_rank is None and self.vector_rank is None:
            raise ValueError("hybrid hit requires at least one channel rank")
        return self


class RetrievalRunWrite(RetrievalModel):
    request_fingerprint: str
    request_basis_fingerprint: str
    security_id: UUID
    snapshot_id: UUID | None
    research_as_of_time: datetime | None
    mode: RetrievalMode
    original_query: str = Field(min_length=1, max_length=256)
    normalized_query: str = Field(min_length=1, max_length=256)
    max_results: int = Field(ge=1, le=20)
    tokenizer_version: str
    lexical_index_version_id: UUID | None
    vector_index_version_id: UUID | None
    fusion_version: str
    reranker_version: str
    status: RetrievalStatus = RetrievalStatus.BLOCKED

    _validate_fingerprints = field_validator("request_fingerprint", "request_basis_fingerprint")(
        _sha
    )
    _validate_time = field_validator("research_as_of_time")(_optional_utc)


class RetrievalRunRecord(RetrievalRunWrite):
    id: UUID
    status: RetrievalStatus
    warnings: tuple[str, ...] = ()
    created_at: datetime
    completed_at: datetime | None = None

    _validate_created = field_validator("created_at")(_utc)
    _validate_completed = field_validator("completed_at")(_optional_utc)


class RetrievalHitWrite(RetrievalModel):
    chunk_id: UUID
    citation_id: UUID
    final_rank: int = Field(ge=1, le=20)
    lexical_rank: int | None = Field(default=None, ge=1, le=20)
    vector_rank: int | None = Field(default=None, ge=1, le=20)
    fusion_score: ExactDecimal
    rerank_reason: str


class RetrievalHitRecord(RetrievalHitWrite):
    id: UUID
    retrieval_run_id: UUID
    created_at: datetime

    _validate_created = field_validator("created_at")(_utc)


class RetrievalCompletion(RetrievalModel):
    status: RetrievalStatus
    warnings: tuple[str, ...] = ()


class RetrievalExecutionResult(RetrievalModel):
    status: RetrievalStatus
    run: RetrievalRunRecord | None
    hits: tuple[RetrievalHitRecord, ...] = ()
    reused: bool
    warnings: tuple[str, ...] = ()


class PreparedRetrieval(RetrievalModel):
    status: RetrievalStatus
    lexical_index_version_id: UUID | None
    vector_index_version_id: UUID | None
    hits: tuple[HybridHit, ...] = Field(default=(), max_length=20)
    warnings: tuple[str, ...] = ()


class EvidenceItem(RetrievalModel):
    citation_id: UUID
    document_version_id: UUID
    chunk_id: UUID
    excerpt: str = Field(min_length=1, max_length=1000)
    citation_status: Literal[CitationStatus.VALID] = CitationStatus.VALID
    document_type: DocumentType
    trust_level: TrustLevel
    published_at: datetime | None
    provider_id: UUID
    source_document_id: UUID
    evidence_origin: Literal["SOURCE", "SYNTHETIC_TEST_ONLY"]
    access_mode: Literal["OFFLINE", "ONLINE"]
    live_status: Literal["NOT_LIVE", "LIVE"]
    locator_type: LocatorType
    start_page: int | None = Field(default=None, ge=1)
    end_page: int | None = Field(default=None, ge=1)
    section_path: str | None = Field(default=None, max_length=1000)
    chunk_version: str
    parser_version: str
    tokenizer_version: str
    citation_version: str
    document_checksum: str
    match_reason: str = Field(min_length=1, max_length=256)

    _validate_published_at = field_validator("published_at")(_optional_utc)
    _validate_document_checksum = field_validator("document_checksum")(_sha)


class VerifiedCitationEvidence(RetrievalModel):
    citation_id: UUID
    document_version_id: UUID
    chunk_id: UUID
    excerpt: str = Field(min_length=1, max_length=5_000_000)
    status: CitationStatus
    document_type: DocumentType
    trust_level: TrustLevel
    published_at: datetime | None
    provider_id: UUID
    source_document_id: UUID
    evidence_origin: Literal["SOURCE", "SYNTHETIC_TEST_ONLY"]
    access_mode: Literal["OFFLINE", "ONLINE"]
    live_status: Literal["NOT_LIVE", "LIVE"]
    locator_type: LocatorType
    start_page: int | None = Field(default=None, ge=1)
    end_page: int | None = Field(default=None, ge=1)
    section_path: str | None = Field(default=None, max_length=1000)
    chunk_version: str
    parser_version: str
    tokenizer_version: str
    citation_version: str
    document_checksum: str

    _validate_published_at = field_validator("published_at")(_optional_utc)
    _validate_document_checksum = field_validator("document_checksum")(_sha)


class EvidenceBundle(RetrievalModel):
    status: RetrievalStatus
    retrieval_run_id: UUID | None
    mode: RetrievalMode
    research_as_of_time: datetime | None
    snapshot_id: UUID | None
    lexical_index_version_id: UUID | None
    vector_index_version_id: UUID | None
    items: tuple[EvidenceItem, ...] = Field(default=(), max_length=20)
    warnings: tuple[str, ...] = ()

    _validate_time = field_validator("research_as_of_time")(_optional_utc)


class RagReadResult(RetrievalModel):
    status: RetrievalStatus
    records: tuple[dict[str, object], ...] = Field(default=(), max_length=20)
    warnings: tuple[str, ...] = ()
