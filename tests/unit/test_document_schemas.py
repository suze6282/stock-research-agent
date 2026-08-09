from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

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
from stock_research_agent.domain.documents.schemas import (
    CitationAnchorDraft,
    DocumentChunkDraft,
    DocumentVersionRecord,
    EvidenceMarkers,
    ParsedPage,
)

NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_ID = UUID("00000000-0000-0000-0000-000000000002")
SHA256 = "a" * 64


def _version(**overrides: object) -> DocumentVersionRecord:
    values: dict[str, object] = {
        "id": ID,
        "logical_document_id": OTHER_ID,
        "source_document_id": UUID("00000000-0000-0000-0000-000000000003"),
        "security_id": UUID("00000000-0000-0000-0000-000000000004"),
        "provider_id": UUID("00000000-0000-0000-0000-000000000005"),
        "source_payload_id": UUID("00000000-0000-0000-0000-000000000006"),
        "version_number": 1,
        "supersedes_document_version_id": None,
        "storage_uri": "blob://memory/0123456789abcdef0123456789abcdef",
        "mime_type": "text/plain",
        "checksum_algorithm": "sha256",
        "checksum": SHA256,
        "byte_size": 12,
        "published_at": NOW,
        "filed_at": None,
        "period_end": None,
        "retrieved_at": NOW,
        "document_language": DocumentLanguage.EN_US,
        "trust_level": TrustLevel.TEST_FIXTURE,
        "evidence_origin": "SYNTHETIC_TEST_ONLY",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
        "source_version_status": SourceVersionStatus.ACTIVE,
        "created_at": NOW,
    }
    values.update(overrides)
    return DocumentVersionRecord.model_validate(values)


def test_document_vocabularies_are_closed() -> None:
    assert {item.value for item in DocumentLanguage} == {"zh-CN", "en-US", "MIXED", "UNKNOWN"}
    assert {item.value for item in TrustLevel} == {
        "OFFICIAL_REGULATORY",
        "OFFICIAL_COMPANY",
        "APPROVED_PROVIDER",
        "TEST_FIXTURE",
        "UNKNOWN",
    }
    assert {item.value for item in SourceVersionStatus} == {"ACTIVE", "WITHDRAWN", "UNKNOWN"}
    assert {item.value for item in ParseStatus} == {
        "RUNNING",
        "PASS",
        "PARTIAL",
        "BLOCKED",
        "FAIL",
    }
    assert {item.value for item in PageStatus} == {"PASS", "BLANK", "NO_TEXT", "PARTIAL"}
    assert {item.value for item in LocatorType} == {
        "PDF_PAGE_RANGE",
        "HTML_ANCHOR_RANGE",
        "TEXT_OFFSET_RANGE",
        "JSON_POINTER",
        "SECTION_RANGE",
    }
    assert {item.value for item in CitationStatus} == {
        "VALID",
        "INVALID",
        "STALE_REFERENCE",
        "FUTURE_DATA",
        "SOURCE_MISSING",
        "PARSE_VERSION_MISMATCH",
    }


def test_document_version_normalizes_aware_times_to_utc_and_is_frozen() -> None:
    record = _version()

    assert record.published_at is not None
    assert record.published_at.tzinfo is UTC
    with pytest.raises(ValidationError, match="frozen"):
        record.version_number = 2


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("created_at", NOW.replace(tzinfo=None), "timezone aware"),
        ("checksum", "not-sha256", "SHA-256"),
        ("storage_uri", "C:/secret/body.txt", "opaque blob URI"),
        ("storage_uri", "blob://memory/key?secret=yes", "opaque blob URI"),
        ("byte_size", 0, "greater than or equal to 1"),
        ("checksum_algorithm", "md5", "sha256"),
    ],
)
def test_document_version_rejects_invalid_evidence_metadata(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _version(**{field: value})


def test_synthetic_evidence_requires_all_four_exact_markers() -> None:
    markers = EvidenceMarkers.synthetic_fixture()

    assert markers.model_dump(mode="json") == {
        "evidence_origin": "SYNTHETIC_TEST_ONLY",
        "company_evidence_status": "NOT_COMPANY_EVIDENCE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
    }
    with pytest.raises(ValidationError):
        EvidenceMarkers(
            evidence_origin="SYNTHETIC_TEST_ONLY",
            company_evidence_status="COMPANY_EVIDENCE",
            access_mode="OFFLINE",
            live_status="NOT_LIVE",
        )


def test_parsed_page_requires_one_based_page_number_and_matching_count() -> None:
    page = ParsedPage(
        page_number=1,
        text="safe text",
        text_checksum=SHA256,
        character_count=9,
        status=PageStatus.PASS,
    )

    assert page.page_number == 1
    with pytest.raises(ValidationError):
        ParsedPage(
            page_number=0,
            text="safe text",
            text_checksum=SHA256,
            character_count=9,
            status=PageStatus.PASS,
        )
    with pytest.raises(ValidationError, match="character_count"):
        page.model_copy(update={"character_count": 99}).model_validate(
            page.model_copy(update={"character_count": 99}).model_dump()
        )


def test_chunk_rejects_reversed_page_and_offset_ranges() -> None:
    common: dict[str, object] = {
        "chunk_version": "chunk-v1",
        "chunk_index": 0,
        "text": "safe text",
        "normalized_text": "safe text",
        "language": DocumentLanguage.EN_US,
        "content_kind": ContentKind.TEXT,
        "locator_type": LocatorType.TEXT_OFFSET_RANGE,
        "start_page": None,
        "end_page": None,
        "start_offset": 0,
        "end_offset": 9,
        "token_count": 2,
        "checksum": SHA256,
        "warnings": (),
    }
    assert DocumentChunkDraft.model_validate(common).end_offset == 9

    with pytest.raises(ValidationError, match="offset range"):
        DocumentChunkDraft.model_validate({**common, "start_offset": 9, "end_offset": 2})
    with pytest.raises(ValidationError, match="page range"):
        DocumentChunkDraft.model_validate(
            {
                **common,
                "locator_type": LocatorType.PDF_PAGE_RANGE,
                "start_page": 3,
                "end_page": 2,
                "start_offset": None,
                "end_offset": None,
            }
        )


def test_citation_requires_locator_specific_coordinates_and_bounded_excerpt() -> None:
    citation = CitationAnchorDraft(
        document_version_id=ID,
        parse_run_id=OTHER_ID,
        locator_type=LocatorType.TEXT_OFFSET_RANGE,
        start_offset=0,
        end_offset=9,
        excerpt="safe text",
        excerpt_checksum=SHA256,
        canonical_text_checksum=SHA256,
        document_checksum=SHA256,
        locator_checksum=SHA256,
        citation_version="citation-v1",
        parser_version="text-parser-v1",
        sanitizer_version="sanitizer-v1",
    )

    assert citation.end_offset == 9
    with pytest.raises(ValidationError, match="at most 1000"):
        citation.model_copy(update={"excerpt": "x" * 1001}).model_validate(
            citation.model_copy(update={"excerpt": "x" * 1001}).model_dump()
        )
    with pytest.raises(ValidationError, match="offset"):
        CitationAnchorDraft(
            document_version_id=ID,
            parse_run_id=OTHER_ID,
            locator_type=LocatorType.TEXT_OFFSET_RANGE,
            excerpt="safe text",
            excerpt_checksum=SHA256,
            canonical_text_checksum=SHA256,
            document_checksum=SHA256,
            locator_checksum=SHA256,
            citation_version="citation-v1",
            parser_version="text-parser-v1",
            sanitizer_version="sanitizer-v1",
        )
