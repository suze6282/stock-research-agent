"""Deterministic citation construction and verification."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from stock_research_agent.domain.documents.enums import (
    CitationStatus,
    LocatorType,
    SourceVersionStatus,
)
from stock_research_agent.domain.documents.repositories import CitationRepository
from stock_research_agent.domain.documents.schemas import (
    CitationAnchorDraft,
    CitationAnchorRecord,
    CitationContext,
    CitationScope,
    CitationVerification,
    CreateCitationRequest,
)
from stock_research_agent.infrastructure.blob_storage import BlobStorage, BlobStorageError


def create_citation(request: CreateCitationRequest) -> CitationAnchorDraft:
    expected_excerpt_checksum = hashlib.sha256(request.excerpt.encode()).hexdigest()
    if request.excerpt_checksum != expected_excerpt_checksum:
        raise ValueError("excerpt checksum does not match exact excerpt")
    if (
        request.start_offset is not None
        and request.end_offset is not None
        and request.end_offset - request.start_offset != len(request.excerpt)
    ):
        raise ValueError("locator range does not match exact excerpt length")
    locator = {
        "document_version_id": str(request.document_version_id),
        "parse_run_id": str(request.parse_run_id),
        "locator_type": request.locator_type.value,
        "start_page": request.start_page,
        "end_page": request.end_page,
        "html_anchor": request.html_anchor,
        "json_pointer": request.json_pointer,
        "start_offset": request.start_offset,
        "end_offset": request.end_offset,
        "excerpt_checksum": request.excerpt_checksum,
        "citation_version": request.citation_version,
    }
    locator_checksum = hashlib.sha256(
        json.dumps(locator, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CitationAnchorDraft(
        locator_checksum=locator_checksum,
        **request.model_dump(),
    )


class CitationVerifier:
    def __init__(self, repository: CitationRepository, blob_storage: BlobStorage) -> None:
        self._repository = repository
        self._blob_storage = blob_storage

    @property
    def blob_storage(self) -> BlobStorage:
        return self._blob_storage

    def verify(self, citation_id: UUID, scope: CitationScope) -> CitationVerification:
        context = self._repository.get_citation_context(citation_id)
        if context is None:
            return _result(citation_id, CitationStatus.SOURCE_MISSING, "CITATION_SOURCE_NOT_FOUND")
        citation = context.citation
        version = context.document_version
        if (
            citation.document_version_id != version.id
            or citation.document_checksum != version.checksum
        ):
            return _result(citation_id, CitationStatus.STALE_REFERENCE, "DOCUMENT_VERSION_MISMATCH")
        if not _locator_checksum_matches(citation):
            return _result(
                citation_id, CitationStatus.INVALID, "CITATION_LOCATOR_CHECKSUM_MISMATCH"
            )
        if (
            citation.parser_version != context.parser_version
            or citation.sanitizer_version != context.sanitizer_version
        ):
            return _result(
                citation_id,
                CitationStatus.PARSE_VERSION_MISMATCH,
                "PARSE_GENERATION_MISMATCH",
            )
        if (
            scope.snapshot_id is not None
            and context.version_in_snapshot is not True
            and scope.snapshot_id not in context.snapshot_ids
        ):
            return _result(
                citation_id, CitationStatus.STALE_REFERENCE, "SNAPSHOT_MEMBERSHIP_MISMATCH"
            )
        if version.source_version_status == SourceVersionStatus.WITHDRAWN:
            return _result(
                citation_id, CitationStatus.STALE_REFERENCE, "DOCUMENT_VERSION_WITHDRAWN"
            )
        if _superseded_for_scope(context, scope):
            return _result(
                citation_id, CitationStatus.STALE_REFERENCE, "DOCUMENT_VERSION_SUPERSEDED"
            )
        if scope.strict_historical and version.published_at is None:
            return _result(citation_id, CitationStatus.INVALID, "SOURCE_PUBLISHED_AT_UNKNOWN")
        if (
            scope.research_as_of_time is not None
            and version.published_at is not None
            and version.published_at > scope.research_as_of_time
        ):
            return _result(citation_id, CitationStatus.FUTURE_DATA, "SOURCE_PUBLISHED_AFTER_AS_OF")
        if not self._valid_blob(context):
            return _result(citation_id, CitationStatus.SOURCE_MISSING, "DOCUMENT_BLOB_MISMATCH")
        if not _locator_exists(context):
            return _result(citation_id, CitationStatus.INVALID, "CITATION_LOCATOR_NOT_FOUND")
        if (
            hashlib.sha256(context.canonical_source_text.encode()).hexdigest()
            != citation.canonical_text_checksum
        ):
            return _result(citation_id, CitationStatus.INVALID, "CANONICAL_TEXT_CHECKSUM_MISMATCH")
        if not _excerpt_matches(context):
            return _result(citation_id, CitationStatus.INVALID, "CITATION_EXCERPT_MISMATCH")
        return CitationVerification(status=CitationStatus.VALID, citation_id=citation_id)

    def _valid_blob(self, context: CitationContext) -> bool:
        version = context.document_version
        try:
            metadata = self._blob_storage.metadata(version.storage_uri)
            content = self._blob_storage.get(version.storage_uri)
        except BlobStorageError:
            return False
        actual_checksum = hashlib.sha256(content).hexdigest()
        return (
            context.blob_bytes == content
            and context.blob_checksum
            == actual_checksum
            == version.checksum
            == metadata.checksum_sha256
            and context.blob_size == len(content) == version.byte_size == metadata.size_bytes
            and context.blob_mime_type == version.mime_type == metadata.content_type
        )


def _excerpt_matches(context: CitationContext) -> bool:
    citation = context.citation
    if citation.start_offset is not None and citation.end_offset is not None:
        if not _range_is_inside_locator(context):
            return False
        excerpt = context.canonical_source_text[citation.start_offset : citation.end_offset]
    elif citation.locator_type == LocatorType.PDF_PAGE_RANGE:
        page_texts = dict(context.page_texts)
        if citation.start_page is None or citation.end_page is None:
            return False
        claimed_text = "\n\f\n".join(
            page_texts.get(page_number, "")
            for page_number in range(citation.start_page, citation.end_page + 1)
        )
        excerpt = citation.excerpt if citation.excerpt in claimed_text else ""
    else:
        return False
    return (
        excerpt == citation.excerpt
        and hashlib.sha256(excerpt.encode()).hexdigest() == citation.excerpt_checksum
        and (context.chunk_text is None or excerpt in context.chunk_text)
    )


def _range_is_inside_locator(context: CitationContext) -> bool:
    citation = context.citation
    assert citation.start_offset is not None
    assert citation.end_offset is not None
    if citation.locator_type == LocatorType.PDF_PAGE_RANGE:
        if citation.start_page is None or citation.end_page is None:
            return False
        spans = _page_spans(context)
        if citation.start_page not in spans or citation.end_page not in spans:
            return False
        locator_start = spans[citation.start_page][0]
        locator_end = spans[citation.end_page][1]
        return locator_start <= citation.start_offset < citation.end_offset <= locator_end
    if citation.locator_type in {
        LocatorType.HTML_ANCHOR_RANGE,
        LocatorType.JSON_POINTER,
        LocatorType.SECTION_RANGE,
    }:
        if citation.section_id is None:
            return False
        section_range = context.section_ranges.get(citation.section_id)
        if section_range is None:
            return False
        section_start, section_end = section_range
        if section_start is None or section_end is None:
            return False
        return section_start <= citation.start_offset < citation.end_offset <= section_end
    return True


def _page_spans(context: CitationContext) -> dict[int, tuple[int, int]]:
    spans: dict[int, tuple[int, int]] = {}
    cursor = 0
    page_texts = dict(context.page_texts)
    ordered = sorted(page_texts.items())
    for index, (page_number, text) in enumerate(ordered):
        end = cursor + len(text)
        spans[page_number] = (cursor, end)
        cursor = end + (3 if index + 1 < len(ordered) else 0)
    return spans


def _locator_checksum_matches(citation: CitationAnchorRecord) -> bool:
    values = citation.model_dump(exclude={"id", "created_at", "locator_checksum"}, mode="python")
    try:
        rebuilt = create_citation(CreateCitationRequest.model_validate(values))
    except ValueError:
        return False
    return rebuilt.locator_checksum == citation.locator_checksum


def _locator_exists(context: CitationContext) -> bool:
    citation = context.citation
    if citation.section_id is not None and citation.section_id not in context.available_section_ids:
        return False
    if citation.locator_type == LocatorType.PDF_PAGE_RANGE:
        if citation.start_page is None or citation.end_page is None:
            return False
        required = set(range(citation.start_page, citation.end_page + 1))
        return required <= set(context.available_page_numbers)
    if citation.locator_type == LocatorType.HTML_ANCHOR_RANGE:
        return (
            citation.section_id is not None
            and context.section_paths.get(citation.section_id) == citation.html_anchor
            and citation.html_anchor in context.available_html_anchors
        )
    if citation.locator_type == LocatorType.JSON_POINTER:
        return (
            citation.section_id is not None
            and context.section_paths.get(citation.section_id) == citation.json_pointer
            and citation.json_pointer in context.available_json_pointers
        )
    if citation.locator_type == LocatorType.SECTION_RANGE:
        return citation.section_id is not None
    return True


def _superseded_for_scope(context: CitationContext, scope: CitationScope) -> bool:
    if context.superseded_by_document_version_id is None:
        return False
    if scope.explicit_document_version_id == context.document_version.id:
        return False
    if scope.snapshot_id is not None and context.version_in_snapshot is True:
        return False
    if context.supersession_time_unknown:
        return True
    if scope.research_as_of_time is None:
        return True
    return context.superseded_at is None or context.superseded_at <= scope.research_as_of_time


def _result(citation_id: UUID, status: CitationStatus, warning: str) -> CitationVerification:
    return CitationVerification(status=status, citation_id=citation_id, warnings=(warning,))
