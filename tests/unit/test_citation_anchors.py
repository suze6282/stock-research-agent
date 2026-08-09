from __future__ import annotations

import hashlib
from uuid import UUID

import pytest

from stock_research_agent.domain.documents.citations import create_citation
from stock_research_agent.domain.documents.enums import LocatorType
from stock_research_agent.domain.documents.schemas import CreateCitationRequest

VERSION_ID = UUID("00000000-0000-0000-0000-000000000031")
PARSE_ID = UUID("00000000-0000-0000-0000-000000000032")
TEXT = "verified excerpt"
SHA = hashlib.sha256(TEXT.encode()).hexdigest()


def _request(**overrides: object) -> CreateCitationRequest:
    values: dict[str, object] = {
        "document_version_id": VERSION_ID,
        "parse_run_id": PARSE_ID,
        "locator_type": LocatorType.TEXT_OFFSET_RANGE,
        "start_offset": 0,
        "end_offset": len(TEXT),
        "excerpt": TEXT,
        "excerpt_checksum": SHA,
        "canonical_text_checksum": SHA,
        "document_checksum": "d" * 64,
        "citation_version": "citation-v1",
        "parser_version": "text-parser-v1",
        "sanitizer_version": "sanitizer-v1",
    }
    values.update(overrides)
    return CreateCitationRequest.model_validate(values)


def test_create_citation_binds_exact_version_parse_and_deterministic_locator() -> None:
    first = create_citation(_request())
    second = create_citation(_request())

    assert first.document_version_id == VERSION_ID
    assert first.parse_run_id == PARSE_ID
    assert first.locator_checksum == second.locator_checksum
    assert first.excerpt == TEXT


def test_create_citation_rejects_excerpt_checksum_or_range_mismatch() -> None:
    with pytest.raises(ValueError, match="excerpt checksum"):
        create_citation(_request(excerpt_checksum="a" * 64))
    with pytest.raises(ValueError, match="locator range"):
        create_citation(_request(end_offset=len(TEXT) + 2))


def test_create_citation_supports_pdf_page_and_json_pointer_without_guessing() -> None:
    pdf = create_citation(
        _request(
            locator_type=LocatorType.PDF_PAGE_RANGE,
            start_page=1,
            end_page=1,
            start_offset=None,
            end_offset=None,
        )
    )
    pointer = create_citation(
        _request(
            locator_type=LocatorType.JSON_POINTER,
            json_pointer="/facts/0/text",
            start_offset=0,
            end_offset=len(TEXT),
        )
    )

    assert pdf.start_page == 1
    assert pointer.json_pointer == "/facts/0/text"
