"""Bounded standard-library HTML text parser that never loads resources."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from html.parser import HTMLParser

from stock_research_agent.domain.documents.enums import ContentKind, LocatorType, ParseStatus
from stock_research_agent.domain.documents.injection import mark_untrusted_instructions
from stock_research_agent.domain.documents.schemas import (
    ParsedDocument,
    ParsedSection,
    ParserConfig,
)

_ACTIVE_TAGS = frozenset({"script", "style", "iframe", "object", "embed", "form", "noscript"})
_BLOCK_TAGS = frozenset({"p", "div", "li", "br", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6"})


class _BoundExceeded(Exception):
    pass


@dataclass(frozen=True, slots=True)
class _Block:
    kind: ContentKind
    title: str
    text: str
    anchor: str | None


class _Collector(HTMLParser):
    def __init__(self, config: ParserConfig) -> None:
        super().__init__(convert_charrefs=True)
        self.config = config
        self.nodes = 0
        self.stack: list[str] = []
        self.suppressed = 0
        self.current: list[str] = []
        self.blocks: list[_Block] = []
        self.heading: tuple[str, str | None] | None = None
        self.in_table = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.nodes += 1
        if self.nodes > self.config.max_html_nodes:
            raise _BoundExceeded
        self.stack.append(tag)
        if len(self.stack) > self.config.max_html_depth:
            raise _BoundExceeded
        if tag in _ACTIVE_TAGS:
            self.suppressed += 1
            return
        if self.suppressed:
            return
        if tag == "table":
            self._flush()
            self.in_table += 1
        if tag in {"td", "th"} and self.current:
            self.current.append(" | ")
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush()
            safe_attrs = {key: value for key, value in attrs if key in {"id", "name"}}
            self.heading = (tag, safe_attrs.get("id") or safe_attrs.get("name"))

    def handle_endtag(self, tag: str) -> None:
        if tag in _ACTIVE_TAGS and self.suppressed:
            self.suppressed -= 1
        elif not self.suppressed and tag in _BLOCK_TAGS:
            self._flush()
            if tag == "table" and self.in_table:
                self.in_table -= 1
        if tag in self.stack:
            reverse_index = self.stack[::-1].index(tag)
            del self.stack[len(self.stack) - reverse_index - 1 :]

    def handle_data(self, data: str) -> None:
        if not self.suppressed and data.strip():
            self.current.append(data.strip())

    def close_and_flush(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        text = " ".join(part for part in self.current if part).strip()
        self.current.clear()
        if not text:
            return
        if self.heading is not None:
            _tag, anchor = self.heading
            self.blocks.append(_Block(ContentKind.HEADING, text, text, anchor))
            self.heading = None
        elif self.in_table:
            self.blocks.append(_Block(ContentKind.TABLE, "Table", text, None))
        else:
            self.blocks.append(_Block(ContentKind.TEXT, "Text", text, None))


class SafeHtmlParser:
    parser_name = "safe-html"
    parser_version = "html-parser-v1"

    def parse(self, content: bytes, config: ParserConfig) -> ParsedDocument:
        try:
            source = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return _blocked("HTML_DECODING_FAILED")
        collector = _Collector(config)
        try:
            collector.feed(source)
            collector.close_and_flush()
        except _BoundExceeded:
            return _blocked("HTML_NODE_LIMIT_EXCEEDED")
        text = "\n".join(block.text for block in collector.blocks)
        if len(text) > config.max_document_characters:
            return _blocked("DOCUMENT_CHARACTER_LIMIT_EXCEEDED")
        sections: list[ParsedSection] = []
        offset = 0
        for index, block in enumerate(collector.blocks):
            end = offset + len(block.text)
            sections.append(
                ParsedSection(
                    section_path=block.anchor or f"/block/{index}",
                    level=1,
                    title=block.title,
                    locator_type=(
                        LocatorType.HTML_ANCHOR_RANGE
                        if block.anchor is not None
                        else LocatorType.SECTION_RANGE
                    ),
                    start_offset=offset,
                    end_offset=end,
                    text_checksum=hashlib.sha256(block.text.encode()).hexdigest(),
                    content_kind=block.kind,
                )
            )
            offset = end + 1
        uncertain = bool(collector.stack)
        warnings = ("HTML_STRUCTURE_UNCERTAIN",) if uncertain else ()
        return ParsedDocument(
            canonical_text=text,
            canonical_text_checksum=hashlib.sha256(text.encode()).hexdigest(),
            sections=tuple(sections),
            status=ParseStatus.PARTIAL if uncertain else ParseStatus.PASS,
            warnings=warnings,
            safety_markers=tuple(mark_untrusted_instructions(text)),
            parser_metadata={"reading_order": "best-effort", "resources_loaded": "false"},
        )


def _blocked(warning: str) -> ParsedDocument:
    return ParsedDocument(
        canonical_text="",
        canonical_text_checksum=hashlib.sha256(b"").hexdigest(),
        status=ParseStatus.BLOCKED,
        warnings=(warning,),
    )
