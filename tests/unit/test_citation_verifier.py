from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from stock_research_agent.domain.documents.citations import CitationVerifier, create_citation
from stock_research_agent.domain.documents.enums import (
    CitationStatus,
    DocumentLanguage,
    LocatorType,
    SourceVersionStatus,
    TrustLevel,
)
from stock_research_agent.domain.documents.schemas import (
    CitationAnchorRecord,
    CitationContext,
    CitationScope,
    CreateCitationRequest,
    DocumentVersionRecord,
)
from stock_research_agent.infrastructure.blob_storage import InMemoryBlobStorage

NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
TEXT = "verified excerpt"


class CitationRepository:
    def __init__(self, context: CitationContext | None) -> None:
        self.context = context

    def get_citation_context(self, citation_id: UUID) -> CitationContext | None:
        if self.context is not None and self.context.citation.id == citation_id:
            return self.context
        return None


def _arrange() -> tuple[CitationVerifier, CitationContext]:
    storage = InMemoryBlobStorage(
        max_blob_bytes=10_000_000,
        key_factory=lambda: "0123456789abcdef0123456789abcdef",
    )
    content = b"exact synthetic source bytes"
    blob = storage.put(content, content_type="text/plain")
    version = DocumentVersionRecord(
        id=uuid4(),
        logical_document_id=uuid4(),
        source_document_id=uuid4(),
        security_id=uuid4(),
        provider_id=uuid4(),
        source_payload_id=uuid4(),
        version_number=1,
        supersedes_document_version_id=None,
        storage_uri=blob.uri,
        mime_type=blob.content_type,
        checksum_algorithm="sha256",
        checksum=blob.checksum_sha256,
        byte_size=blob.size_bytes,
        published_at=NOW,
        filed_at=None,
        period_end=None,
        retrieved_at=NOW,
        document_language=DocumentLanguage.EN_US,
        trust_level=TrustLevel.TEST_FIXTURE,
        evidence_origin="SYNTHETIC_TEST_ONLY",
        access_mode="OFFLINE",
        live_status="NOT_LIVE",
        source_version_status=SourceVersionStatus.ACTIVE,
        created_at=NOW,
    )
    request = CreateCitationRequest(
        document_version_id=version.id,
        parse_run_id=uuid4(),
        locator_type=LocatorType.TEXT_OFFSET_RANGE,
        start_offset=0,
        end_offset=len(TEXT),
        excerpt=TEXT,
        excerpt_checksum=hashlib.sha256(TEXT.encode()).hexdigest(),
        canonical_text_checksum=hashlib.sha256(TEXT.encode()).hexdigest(),
        document_checksum=version.checksum,
        citation_version="citation-v1",
        parser_version="text-parser-v1",
        sanitizer_version="sanitizer-v1",
    )
    draft = create_citation(request)
    citation = CitationAnchorRecord(id=uuid4(), created_at=NOW, **draft.model_dump())
    context = CitationContext(
        citation=citation,
        document_version=version,
        canonical_source_text=TEXT,
        blob_bytes=content,
        blob_mime_type=blob.content_type,
        blob_checksum=blob.checksum_sha256,
        blob_size=blob.size_bytes,
        version_in_snapshot=True,
        parser_version="text-parser-v1",
        sanitizer_version="sanitizer-v1",
    )
    return CitationVerifier(CitationRepository(context), storage), context


def test_valid_citation_passes_all_deterministic_checks() -> None:
    verifier, context = _arrange()
    result = verifier.verify(context.citation.id, CitationScope(research_as_of_time=NOW))
    assert result.status == CitationStatus.VALID
    assert result.warnings == ()


def test_future_or_unknown_publication_is_not_admitted_in_strict_history() -> None:
    verifier, context = _arrange()
    future = verifier.verify(
        context.citation.id,
        CitationScope(research_as_of_time=NOW - timedelta(seconds=1)),
    )
    assert future.status == CitationStatus.FUTURE_DATA

    unknown_context = context.model_copy(
        update={
            "document_version": context.document_version.model_copy(update={"published_at": None})
        }
    )
    unknown = CitationVerifier(CitationRepository(unknown_context), verifier.blob_storage).verify(
        context.citation.id, CitationScope(research_as_of_time=NOW)
    )
    assert unknown.status == CitationStatus.INVALID
    assert unknown.warnings == ("SOURCE_PUBLISHED_AT_UNKNOWN",)


def test_superseded_version_is_historical_only_unless_explicitly_selected() -> None:
    verifier, context = _arrange()
    superseded_at = NOW + timedelta(days=1)
    context = context.model_copy(
        update={
            "superseded_by_document_version_id": uuid4(),
            "superseded_at": superseded_at,
        }
    )
    verifier = CitationVerifier(CitationRepository(context), verifier.blob_storage)

    before = verifier.verify(
        context.citation.id,
        CitationScope(research_as_of_time=NOW),
    )
    after = verifier.verify(
        context.citation.id,
        CitationScope(research_as_of_time=NOW + timedelta(days=2)),
    )
    explicit = verifier.verify(
        context.citation.id,
        CitationScope(
            research_as_of_time=NOW + timedelta(days=2),
            explicit_document_version_id=context.document_version.id,
        ),
    )

    assert before.status == CitationStatus.VALID
    assert after.status == CitationStatus.STALE_REFERENCE
    assert after.warnings == ("DOCUMENT_VERSION_SUPERSEDED",)
    assert explicit.status == CitationStatus.VALID


def test_excerpt_parse_snapshot_and_blob_mismatch_are_rejected() -> None:
    verifier, context = _arrange()
    invalid_context = context.model_copy(update={"canonical_source_text": "tampered excerpt"})
    invalid = CitationVerifier(CitationRepository(invalid_context), verifier.blob_storage)
    assert (
        invalid.verify(context.citation.id, CitationScope(research_as_of_time=NOW)).status
        == CitationStatus.INVALID
    )

    verifier, context = _arrange()
    context = context.model_copy(update={"parser_version": "text-parser-v2"})
    verifier = CitationVerifier(CitationRepository(context), verifier.blob_storage)
    assert (
        verifier.verify(context.citation.id, CitationScope(research_as_of_time=NOW)).status
        == CitationStatus.PARSE_VERSION_MISMATCH
    )

    verifier, context = _arrange()
    context = context.model_copy(update={"version_in_snapshot": False})
    verifier = CitationVerifier(CitationRepository(context), verifier.blob_storage)
    assert (
        verifier.verify(context.citation.id, CitationScope(snapshot_id=uuid4())).status
        == CitationStatus.STALE_REFERENCE
    )

    verifier, context = _arrange()
    context = context.model_copy(update={"blob_checksum": "f" * 64})
    verifier = CitationVerifier(CitationRepository(context), verifier.blob_storage)
    assert (
        verifier.verify(context.citation.id, CitationScope(research_as_of_time=NOW)).status
        == CitationStatus.SOURCE_MISSING
    )


def test_missing_citation_context_is_source_missing() -> None:
    verifier, _ = _arrange()
    verifier = CitationVerifier(CitationRepository(None), verifier.blob_storage)
    assert (
        verifier.verify(uuid4(), CitationScope(research_as_of_time=NOW)).status
        == CitationStatus.SOURCE_MISSING
    )


def test_pdf_excerpt_must_be_inside_claimed_page_range() -> None:
    verifier, context = _arrange()
    first_page = "page one has no quoted text"
    second_page = TEXT
    canonical = f"{first_page}\n\f\n{second_page}"
    request = CreateCitationRequest(
        document_version_id=context.document_version.id,
        parse_run_id=context.citation.parse_run_id,
        locator_type=LocatorType.PDF_PAGE_RANGE,
        start_page=1,
        end_page=1,
        start_offset=len(first_page) + 3,
        end_offset=len(canonical),
        excerpt=TEXT,
        excerpt_checksum=hashlib.sha256(TEXT.encode()).hexdigest(),
        canonical_text_checksum=hashlib.sha256(canonical.encode()).hexdigest(),
        document_checksum=context.document_version.checksum,
        parser_version=context.parser_version,
        sanitizer_version=context.sanitizer_version,
    )
    citation = CitationAnchorRecord(
        id=context.citation.id,
        created_at=NOW,
        **create_citation(request).model_dump(),
    )
    invalid_context = context.model_copy(
        update={
            "citation": citation,
            "canonical_source_text": canonical,
            "available_page_numbers": (1, 2),
            "page_texts": ((1, first_page), (2, second_page)),
        }
    )

    result = CitationVerifier(CitationRepository(invalid_context), verifier.blob_storage).verify(
        citation.id, CitationScope(research_as_of_time=NOW)
    )

    assert result.status == CitationStatus.INVALID
    assert result.warnings == ("CITATION_EXCERPT_MISMATCH",)
