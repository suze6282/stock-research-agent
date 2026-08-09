from __future__ import annotations

import hashlib

from stock_research_agent.domain.documents.chunking import DocumentChunker
from stock_research_agent.domain.documents.enums import (
    ContentKind,
    LocatorType,
    PageStatus,
    ParseStatus,
)
from stock_research_agent.domain.documents.schemas import (
    ChunkConfig,
    ParsedDocument,
    ParsedPage,
    ParsedSection,
)


def _parsed(text: str) -> ParsedDocument:
    return ParsedDocument(
        canonical_text=text,
        canonical_text_checksum=hashlib.sha256(text.encode()).hexdigest(),
        status=ParseStatus.PASS,
        parser_metadata={"parser_version": "text-parser-v1", "config_checksum": "c" * 64},
    )


def test_chunker_retains_half_open_offsets_and_short_document() -> None:
    text = "Industrial FII synthetic parser contract evidence."

    chunks = DocumentChunker().chunk(_parsed(text), ChunkConfig())

    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].start_offset == 0
    assert chunks[0].end_offset == len(text)


def test_chunker_uses_bounded_paragraph_windows_and_merges_short_tail() -> None:
    text = "\n\n".join(["A" * 700, "B" * 700, "short tail"])

    chunks = DocumentChunker().chunk(
        _parsed(text),
        ChunkConfig(target_characters=800, maximum_characters=1000, overlap_characters=100),
    )

    assert all(1 <= len(chunk.text) <= 1000 for chunk in chunks)
    assert len(chunks[-1].text) >= 120
    assert chunks == tuple(sorted(chunks, key=lambda chunk: chunk.chunk_index))


def test_chunker_avoids_splitting_protected_financial_tokens() -> None:
    prefix = "word " * 35
    text = f"{prefix}601138.SH 12.5% 123.45RMB NASDAQ:MU ending"

    chunks = DocumentChunker().chunk(
        _parsed(text),
        ChunkConfig(
            target_characters=180,
            maximum_characters=220,
            minimum_characters=60,
            overlap_characters=30,
        ),
    )

    for token in ("601138.SH", "12.5%", "123.45RMB", "NASDAQ:MU"):
        assert sum(token in chunk.text for chunk in chunks) >= 1


def test_chunker_rejects_empty_canonical_document() -> None:
    assert DocumentChunker().chunk(_parsed(""), ChunkConfig()) == ()


def test_chunker_preserves_pdf_page_boundaries_and_native_locator() -> None:
    first = "first page evidence"
    second = "second page evidence"
    text = f"{first}\n\f\n{second}"
    parsed = ParsedDocument(
        canonical_text=text,
        canonical_text_checksum=hashlib.sha256(text.encode()).hexdigest(),
        pages=(
            ParsedPage(
                page_number=1,
                text=first,
                text_checksum=hashlib.sha256(first.encode()).hexdigest(),
                character_count=len(first),
                status=PageStatus.PASS,
            ),
            ParsedPage(
                page_number=2,
                text=second,
                text_checksum=hashlib.sha256(second.encode()).hexdigest(),
                character_count=len(second),
                status=PageStatus.PASS,
            ),
        ),
        status=ParseStatus.PASS,
    )

    chunks = DocumentChunker().chunk(parsed, ChunkConfig())

    assert tuple((chunk.text, chunk.locator_type) for chunk in chunks) == (
        (first, LocatorType.PDF_PAGE_RANGE),
        (second, LocatorType.PDF_PAGE_RANGE),
    )
    assert tuple((chunk.start_page, chunk.end_page) for chunk in chunks) == ((1, 1), (2, 2))


def test_chunker_preserves_html_anchor_and_json_pointer() -> None:
    html_text = "anchored evidence"
    html = ParsedDocument(
        canonical_text=html_text,
        canonical_text_checksum=hashlib.sha256(html_text.encode()).hexdigest(),
        sections=(
            ParsedSection(
                section_path="risk-factors",
                level=1,
                title="Risk Factors",
                locator_type=LocatorType.HTML_ANCHOR_RANGE,
                start_offset=0,
                end_offset=len(html_text),
                text_checksum=hashlib.sha256(html_text.encode()).hexdigest(),
                content_kind=ContentKind.HEADING,
            ),
        ),
        status=ParseStatus.PASS,
    )
    pointer = "/facts/risk"
    json_text = "json evidence"
    parsed_json = ParsedDocument(
        canonical_text=json_text,
        canonical_text_checksum=hashlib.sha256(json_text.encode()).hexdigest(),
        sections=(
            ParsedSection(
                section_path=pointer,
                level=1,
                title=pointer,
                locator_type=LocatorType.JSON_POINTER,
                start_offset=0,
                end_offset=len(json_text),
                text_checksum=hashlib.sha256(json_text.encode()).hexdigest(),
                content_kind=ContentKind.JSON,
            ),
        ),
        status=ParseStatus.PASS,
    )

    html_chunk = DocumentChunker().chunk(html, ChunkConfig())[0]
    json_chunk = DocumentChunker().chunk(parsed_json, ChunkConfig())[0]

    assert html_chunk.locator_type == LocatorType.HTML_ANCHOR_RANGE
    assert html_chunk.html_anchor == "risk-factors"
    assert html_chunk.section_path == "risk-factors"
    assert json_chunk.locator_type == LocatorType.JSON_POINTER
    assert json_chunk.json_pointer == pointer
    assert json_chunk.section_path == pointer
