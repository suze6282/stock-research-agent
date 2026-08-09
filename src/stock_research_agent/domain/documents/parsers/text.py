"""Bounded canonical UTF-8 text parser."""

from __future__ import annotations

import hashlib
import unicodedata

from stock_research_agent.domain.documents.enums import ParseStatus
from stock_research_agent.domain.documents.injection import mark_untrusted_instructions
from stock_research_agent.domain.documents.schemas import ParsedDocument, ParserConfig


class PlainTextParser:
    parser_name = "plain-text"
    parser_version = "text-parser-v1"

    def parse(self, content: bytes, config: ParserConfig) -> ParsedDocument:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return _blocked("TEXT_DECODING_FAILED")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if len(text) > config.max_document_characters:
            return _blocked("DOCUMENT_CHARACTER_LIMIT_EXCEEDED")
        if any(
            unicodedata.category(character) == "Cc" and character not in "\n\t"
            for character in text
        ):
            return _blocked("UNSAFE_CONTROL_CHARACTER")
        checksum = hashlib.sha256(text.encode()).hexdigest()
        return ParsedDocument(
            canonical_text=text,
            canonical_text_checksum=checksum,
            status=ParseStatus.PASS,
            safety_markers=tuple(mark_untrusted_instructions(text)),
            parser_metadata={"encoding": "utf-8", "offset_model": "half-open"},
        )


def _blocked(warning: str) -> ParsedDocument:
    return ParsedDocument(
        canonical_text="",
        canonical_text_checksum=hashlib.sha256(b"").hexdigest(),
        status=ParseStatus.BLOCKED,
        warnings=(warning,),
    )
