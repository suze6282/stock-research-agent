from __future__ import annotations

import hashlib

from stock_research_agent.domain.documents.chunking import DocumentChunker
from stock_research_agent.domain.documents.enums import ParseStatus
from stock_research_agent.domain.documents.schemas import ChunkConfig, ParsedDocument


def _document(parser_version: str = "text-parser-v1") -> ParsedDocument:
    text = "stable evidence paragraph " * 80
    return ParsedDocument(
        canonical_text=text,
        canonical_text_checksum=hashlib.sha256(text.encode()).hexdigest(),
        status=ParseStatus.PASS,
        parser_metadata={"parser_version": parser_version, "config_checksum": "a" * 64},
    )


def test_identical_input_yields_identical_ordered_descriptors_and_checksums() -> None:
    chunker = DocumentChunker()

    first = chunker.chunk(_document(), ChunkConfig())
    second = chunker.chunk(_document(), ChunkConfig())

    assert first == second
    assert [chunk.checksum for chunk in first] == [chunk.checksum for chunk in second]


def test_parser_or_chunk_config_change_changes_generation_checksum() -> None:
    chunker = DocumentChunker()
    default = chunker.chunk(_document(), ChunkConfig())
    parser_changed = chunker.chunk(_document("text-parser-v2"), ChunkConfig())
    config_changed = chunker.chunk(
        _document(),
        ChunkConfig(target_characters=900, maximum_characters=1500, overlap_characters=180),
    )

    assert default[0].checksum != parser_changed[0].checksum
    assert default[0].checksum != config_changed[0].checksum
    assert default[0].chunk_version == "chunk-v1"
