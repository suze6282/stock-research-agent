"""Strict immutable contracts for document versions, parsing and citations."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from stock_research_agent.domain.documents.enums import (
    CitationStatus,
    ContentKind,
    DocumentLanguage,
    LocatorType,
    PageStatus,
    ParseStatus,
    SourceVersionStatus,
    TrustLevel,
)

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_BLOB_URI_PATTERN = re.compile(r"blob://[a-z][a-z0-9_-]{0,31}/[0-9a-f]{32}\Z")
_VERSION_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,31}-v[1-9][0-9]*\Z")
_MIME_TYPES = frozenset(
    {
        "application/json",
        "application/pdf",
        "text/html",
        "text/plain",
    }
)

EvidenceOrigin = Literal["SOURCE", "SYNTHETIC_TEST_ONLY"]
AccessMode = Literal["OFFLINE", "ONLINE"]
LiveStatus = Literal["NOT_LIVE", "LIVE"]
CompanyEvidenceStatus = Literal["COMPANY_EVIDENCE", "NOT_COMPANY_EVIDENCE"]
DocumentMimeType = Literal["application/pdf", "text/html", "text/plain", "application/json"]


class DocumentModel(BaseModel):
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


def _sha256(value: str) -> str:
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError("value must be a lowercase SHA-256 digest")
    return value


def _opaque_blob_uri(value: str) -> str:
    if _BLOB_URI_PATTERN.fullmatch(value) is None:
        raise ValueError("storage_uri must be an opaque blob URI")
    return value


def _version(value: str) -> str:
    if _VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError("version must be a stable lowercase name-vN token")
    return value


class EvidenceMarkers(DocumentModel):
    evidence_origin: EvidenceOrigin
    company_evidence_status: CompanyEvidenceStatus
    access_mode: AccessMode
    live_status: LiveStatus

    @classmethod
    def synthetic_fixture(cls) -> Self:
        return cls(
            evidence_origin="SYNTHETIC_TEST_ONLY",
            company_evidence_status="NOT_COMPANY_EVIDENCE",
            access_mode="OFFLINE",
            live_status="NOT_LIVE",
        )

    @model_validator(mode="after")
    def validate_marker_set(self) -> Self:
        if self.evidence_origin == "SYNTHETIC_TEST_ONLY" and (
            self.company_evidence_status != "NOT_COMPANY_EVIDENCE"
            or self.access_mode != "OFFLINE"
            or self.live_status != "NOT_LIVE"
        ):
            raise ValueError("synthetic evidence requires all four approved test-only markers")
        return self


class SourceBodyRecord(DocumentModel):
    source_document_id: UUID
    security_id: UUID
    provider_id: UUID
    source_payload_id: UUID
    document_status: Literal["AVAILABLE"]
    storage_uri: str
    checksum: str
    byte_size: int = Field(ge=1, le=10_000_000)
    mime_type: str
    published_at: datetime | None
    filed_at: datetime | None = None
    period_end: date | None = None
    retrieved_at: datetime

    _validate_uri = field_validator("storage_uri")(_opaque_blob_uri)
    _validate_checksum = field_validator("checksum")(_sha256)
    _validate_times = field_validator("published_at", "filed_at")(_optional_utc)
    _validate_retrieved_at = field_validator("retrieved_at")(_utc)

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        if value not in _MIME_TYPES:
            raise ValueError("mime_type is not allowlisted")
        return value


class ValidatedDocumentContent(DocumentModel):
    declared_mime_type: DocumentMimeType
    detected_mime_type: DocumentMimeType
    checksum: str
    byte_size: int = Field(ge=1, le=10_000_000)

    _validate_checksum = field_validator("checksum")(_sha256)


class RegisterDocumentVersionRequest(DocumentModel):
    logical_document_id: UUID | None
    source_body: SourceBodyRecord
    version_number: int | None = Field(default=None, ge=1)
    supersedes_document_version_id: UUID | None = None
    document_language: DocumentLanguage
    trust_level: TrustLevel
    evidence_origin: EvidenceOrigin
    access_mode: AccessMode
    live_status: LiveStatus
    source_version_status: SourceVersionStatus


class DocumentVersionWrite(DocumentModel):
    logical_document_id: UUID
    source_document_id: UUID
    security_id: UUID
    provider_id: UUID
    source_payload_id: UUID
    version_number: int = Field(ge=1)
    supersedes_document_version_id: UUID | None
    storage_uri: str
    mime_type: str
    checksum_algorithm: Literal["sha256"] = "sha256"
    checksum: str
    byte_size: int = Field(ge=1, le=10_000_000)
    published_at: datetime | None
    filed_at: datetime | None
    period_end: date | None
    retrieved_at: datetime
    document_language: DocumentLanguage
    trust_level: TrustLevel
    evidence_origin: EvidenceOrigin
    access_mode: AccessMode
    live_status: LiveStatus
    source_version_status: SourceVersionStatus

    _validate_uri = field_validator("storage_uri")(_opaque_blob_uri)
    _validate_checksum = field_validator("checksum")(_sha256)
    _validate_optional_times = field_validator("published_at", "filed_at")(_optional_utc)
    _validate_retrieved = field_validator("retrieved_at")(_utc)

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        if value not in _MIME_TYPES:
            raise ValueError("mime_type is not allowlisted")
        return value


class DocumentVersionRecord(DocumentVersionWrite):
    id: UUID
    created_at: datetime

    _validate_created = field_validator("created_at")(_utc)


class DocumentVersionResult(DocumentModel):
    status: Literal["CREATED", "REUSED", "BLOCKED"]
    version: DocumentVersionRecord | None
    warnings: tuple[str, ...] = ()


class BindSnapshotDocumentVersionRequest(DocumentModel):
    snapshot_id: UUID
    document_version_id: UUID
    snapshot_item_id: UUID


class SnapshotDocumentVersionWrite(BindSnapshotDocumentVersionRequest):
    pass


class SnapshotDocumentVersionRecord(BindSnapshotDocumentVersionRequest):
    created_at: datetime

    _validate_created = field_validator("created_at")(_utc)


class SnapshotDocumentVersionResult(DocumentModel):
    status: Literal["CREATED", "REUSED", "BLOCKED"]
    link: SnapshotDocumentVersionRecord | None
    warnings: tuple[str, ...] = ()


class SnapshotBodyEvidenceRecord(DocumentModel):
    snapshot_id: UUID
    snapshot_item_id: UUID
    security_id: UUID
    provider_id: UUID
    category: Literal["SOURCE_DOCUMENTS", "FILING_METADATA"]
    source_record_type: Literal["source_documents"]
    source_record_id: UUID
    source_published_at: datetime | None

    _validate_published = field_validator("source_published_at")(_optional_utc)


class ParserConfig(DocumentModel):
    max_document_bytes: int = Field(default=10_000_000, ge=1, le=10_000_000)
    max_pdf_pages: int = Field(default=500, ge=1, le=500)
    max_characters_per_page: int = Field(default=100_000, ge=1, le=100_000)
    max_document_characters: int = Field(default=5_000_000, ge=1, le=5_000_000)
    max_html_nodes: int = Field(default=50_000, ge=1, le=50_000)
    max_html_depth: int = Field(default=64, ge=1, le=64)
    max_json_depth: int = Field(default=32, ge=1, le=32)
    max_json_array_items: int = Field(default=10_000, ge=1, le=10_000)
    approved_json_pointers: tuple[str, ...] = ()
    approved_text_encoding: Literal["utf-8"] = "utf-8"


class ParsedPage(DocumentModel):
    page_number: int = Field(ge=1, le=500)
    text: str = Field(max_length=100_000)
    text_checksum: str
    character_count: int = Field(ge=0, le=100_000)
    status: PageStatus
    warnings: tuple[str, ...] = ()

    _validate_checksum = field_validator("text_checksum")(_sha256)

    @model_validator(mode="after")
    def validate_count(self) -> Self:
        if self.character_count != len(self.text):
            raise ValueError("character_count must match text length")
        return self


class ParsedSection(DocumentModel):
    section_path: str = Field(min_length=1, max_length=512)
    parent_section_path: str | None = Field(default=None, max_length=512)
    level: int = Field(ge=1, le=64)
    title: str = Field(min_length=1, max_length=1000)
    locator_type: LocatorType
    start_page: int | None = Field(default=None, ge=1)
    end_page: int | None = Field(default=None, ge=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    text_checksum: str
    content_kind: ContentKind

    _validate_checksum = field_validator("text_checksum")(_sha256)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        _validate_locator_ranges(
            self.locator_type,
            self.start_page,
            self.end_page,
            self.start_offset,
            self.end_offset,
        )
        return self


class ParsedDocument(DocumentModel):
    canonical_text: str = Field(max_length=5_000_000)
    canonical_text_checksum: str
    pages: tuple[ParsedPage, ...] = ()
    sections: tuple[ParsedSection, ...] = ()
    status: ParseStatus
    warnings: tuple[str, ...] = ()
    safety_markers: tuple[str, ...] = ()
    parser_metadata: dict[str, str] = Field(default_factory=dict)

    _validate_checksum = field_validator("canonical_text_checksum")(_sha256)


class ParseRunKey(DocumentModel):
    document_version_id: UUID
    parser_name: str = Field(min_length=1, max_length=64)
    parser_version: str
    sanitizer_version: str
    config_checksum: str

    _validate_versions = field_validator("parser_version", "sanitizer_version")(_version)
    _validate_checksum = field_validator("config_checksum")(_sha256)


class DocumentParseRunWrite(ParseRunKey):
    status: Literal[ParseStatus.RUNNING] = ParseStatus.RUNNING


class DocumentParseRunRecord(ParseRunKey):
    id: UUID
    status: ParseStatus
    canonical_text_checksum: str | None = None
    warnings: tuple[str, ...] = ()
    started_at: datetime
    completed_at: datetime | None = None

    _validate_canonical_checksum = field_validator("canonical_text_checksum")(
        lambda value: None if value is None else _sha256(value)
    )
    _validate_started = field_validator("started_at")(_utc)
    _validate_completed = field_validator("completed_at")(_optional_utc)


class ParseCompletion(DocumentModel):
    status: ParseStatus
    canonical_text_checksum: str | None = None
    warnings: tuple[str, ...] = ()

    _validate_checksum = field_validator("canonical_text_checksum")(
        lambda value: None if value is None else _sha256(value)
    )

    @field_validator("status")
    @classmethod
    def reject_running(cls, value: ParseStatus) -> ParseStatus:
        if value == ParseStatus.RUNNING:
            raise ValueError("parse completion must be terminal")
        return value


class DocumentParseResult(DocumentModel):
    status: ParseStatus
    run: DocumentParseRunRecord | None
    document: ParsedDocument | None
    reused: bool
    warnings: tuple[str, ...] = ()


class ChunkConfig(DocumentModel):
    chunk_version: str = "chunk-v1"
    target_characters: int = Field(default=1000, ge=120, le=1600)
    maximum_characters: int = Field(default=1600, ge=120, le=1600)
    minimum_characters: int = Field(default=120, ge=1, le=1600)
    overlap_characters: int = Field(default=200, ge=0, le=200)

    _validate_version = field_validator("chunk_version")(_version)

    @model_validator(mode="after")
    def validate_limits(self) -> Self:
        if self.minimum_characters > self.target_characters:
            raise ValueError("minimum characters cannot exceed target")
        if self.target_characters > self.maximum_characters:
            raise ValueError("target characters cannot exceed maximum")
        if self.overlap_characters > self.target_characters // 5:
            raise ValueError("overlap cannot exceed 20 percent of target")
        return self


def _validate_locator_ranges(
    locator_type: LocatorType,
    start_page: int | None,
    end_page: int | None,
    start_offset: int | None,
    end_offset: int | None,
) -> None:
    if (start_page is None) != (end_page is None):
        raise ValueError("page range requires both bounds")
    if start_page is not None and end_page is not None and end_page < start_page:
        raise ValueError("page range is reversed")
    if (start_offset is None) != (end_offset is None):
        raise ValueError("offset range requires both bounds")
    if start_offset is not None and end_offset is not None and end_offset <= start_offset:
        raise ValueError("offset range is empty or reversed")
    if locator_type == LocatorType.PDF_PAGE_RANGE and start_page is None:
        raise ValueError("PDF locator requires a page range")
    if locator_type == LocatorType.TEXT_OFFSET_RANGE and start_offset is None:
        raise ValueError("text locator requires an offset range")


class DocumentChunkDraft(DocumentModel):
    chunk_version: str
    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=1600)
    normalized_text: str = Field(min_length=1, max_length=1600)
    language: DocumentLanguage
    content_kind: ContentKind
    locator_type: LocatorType
    section_path: str | None = Field(default=None, max_length=512)
    html_anchor: str | None = Field(default=None, max_length=256)
    json_pointer: str | None = Field(default=None, max_length=1000)
    start_page: int | None = Field(default=None, ge=1)
    end_page: int | None = Field(default=None, ge=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    token_count: int = Field(ge=0)
    checksum: str
    warnings: tuple[str, ...] = ()

    _validate_version = field_validator("chunk_version")(_version)
    _validate_checksum = field_validator("checksum")(_sha256)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        _validate_locator_ranges(
            self.locator_type,
            self.start_page,
            self.end_page,
            self.start_offset,
            self.end_offset,
        )
        if self.locator_type == LocatorType.HTML_ANCHOR_RANGE and self.html_anchor is None:
            raise ValueError("HTML chunk locator requires an anchor")
        if self.locator_type == LocatorType.JSON_POINTER and self.json_pointer is None:
            raise ValueError("JSON chunk locator requires a pointer")
        return self


class DocumentChunkRecord(DocumentChunkDraft):
    id: UUID
    parse_run_id: UUID
    document_version_id: UUID
    created_at: datetime

    _validate_created = field_validator("created_at")(_utc)


class CreateCitationRequest(DocumentModel):
    document_version_id: UUID
    parse_run_id: UUID
    page_id: UUID | None = None
    section_id: UUID | None = None
    chunk_id: UUID | None = None
    locator_type: LocatorType
    start_page: int | None = Field(default=None, ge=1)
    end_page: int | None = Field(default=None, ge=1)
    html_anchor: str | None = Field(default=None, max_length=256)
    json_pointer: str | None = Field(default=None, max_length=1000)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    excerpt: str = Field(min_length=1, max_length=1000)
    excerpt_checksum: str
    canonical_text_checksum: str
    document_checksum: str
    citation_version: str = "citation-v1"
    parser_version: str
    sanitizer_version: str

    _validate_checksums = field_validator(
        "excerpt_checksum", "canonical_text_checksum", "document_checksum"
    )(_sha256)
    _validate_version = field_validator("citation_version")(_version)
    _validate_parse_versions = field_validator("parser_version", "sanitizer_version")(_version)


class CitationAnchorDraft(CreateCitationRequest):
    locator_checksum: str

    _validate_locator_checksum = field_validator("locator_checksum")(_sha256)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        _validate_locator_ranges(
            self.locator_type,
            self.start_page,
            self.end_page,
            self.start_offset,
            self.end_offset,
        )
        if self.locator_type == LocatorType.HTML_ANCHOR_RANGE and self.html_anchor is None:
            raise ValueError("HTML locator requires an anchor")
        if self.locator_type == LocatorType.JSON_POINTER and self.json_pointer is None:
            raise ValueError("JSON locator requires a pointer")
        return self


class CitationAnchorRecord(CitationAnchorDraft):
    id: UUID
    created_at: datetime

    _validate_created = field_validator("created_at")(_utc)


class CitationContext(DocumentModel):
    citation: CitationAnchorRecord
    document_version: DocumentVersionRecord
    canonical_source_text: str
    blob_bytes: bytes
    blob_mime_type: str
    blob_checksum: str
    blob_size: int = Field(ge=0)
    snapshot_id: UUID | None = None
    version_in_snapshot: bool | None = None
    snapshot_ids: tuple[UUID, ...] = ()
    superseded_by_document_version_id: UUID | None = None
    superseded_at: datetime | None = None
    supersession_time_unknown: bool = False
    available_page_numbers: tuple[int, ...] = ()
    page_texts: dict[int, str] = Field(default_factory=dict)
    available_section_ids: tuple[UUID, ...] = ()
    section_paths: dict[UUID, str] = Field(default_factory=dict)
    section_ranges: dict[UUID, tuple[int | None, int | None]] = Field(default_factory=dict)
    available_html_anchors: tuple[str, ...] = ()
    available_json_pointers: tuple[str, ...] = ()
    chunk_text: str | None = None
    parser_version: str
    sanitizer_version: str

    _validate_blob_checksum = field_validator("blob_checksum")(_sha256)
    _validate_superseded_at = field_validator("superseded_at")(_optional_utc)


class CitationScope(DocumentModel):
    research_as_of_time: datetime | None = None
    strict_historical: bool = True
    snapshot_id: UUID | None = None
    explicit_document_version_id: UUID | None = None

    _validate_as_of = field_validator("research_as_of_time")(_optional_utc)

    @model_validator(mode="after")
    def exact_scope(self) -> Self:
        if (self.snapshot_id is None) == (self.research_as_of_time is None):
            raise ValueError("exactly one citation scope is required")
        return self


class CitationVerification(DocumentModel):
    status: CitationStatus
    citation_id: UUID
    warnings: tuple[str, ...] = ()
