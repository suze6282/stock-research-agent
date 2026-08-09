"""Parser port and fixed MIME registry."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Protocol

from stock_research_agent.domain.documents.schemas import ParsedDocument, ParserConfig

_MIME_TYPES = frozenset({"application/pdf", "text/html", "text/plain", "application/json"})


class DocumentParser(Protocol):
    @property
    def parser_name(self) -> str: ...

    @property
    def parser_version(self) -> str: ...

    def parse(self, content: bytes, config: ParserConfig) -> ParsedDocument: ...


class ParserRegistry:
    def __init__(self, parsers: Mapping[str, DocumentParser]) -> None:
        if not parsers or any(mime not in _MIME_TYPES for mime in parsers):
            raise ValueError("parser registry keys must be approved MIME types")
        self._parsers = MappingProxyType(dict(parsers))

    def select(self, mime_type: str) -> DocumentParser | None:
        return self._parsers.get(mime_type)
