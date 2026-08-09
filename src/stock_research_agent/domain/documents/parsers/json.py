"""Strict JSON parser that promotes only configured RFC 6901 string values."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from stock_research_agent.domain.documents.enums import ContentKind, LocatorType, ParseStatus
from stock_research_agent.domain.documents.injection import mark_untrusted_instructions
from stock_research_agent.domain.documents.schemas import (
    ParsedDocument,
    ParsedSection,
    ParserConfig,
)


class _DuplicateKey(ValueError):
    pass


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey
        result[key] = value
    return result


class JsonDocumentParser:
    parser_name = "approved-json"
    parser_version = "json-parser-v1"

    def __init__(self, approved_pointers: tuple[str, ...]) -> None:
        if any(not pointer.startswith("/") for pointer in approved_pointers):
            raise ValueError("approved JSON pointers must use RFC 6901 syntax")
        self._approved = tuple(dict.fromkeys(approved_pointers))

    def parse(self, content: bytes, config: ParserConfig) -> ParsedDocument:
        try:
            root = json.loads(content.decode("utf-8-sig"), object_pairs_hook=_object)
        except _DuplicateKey:
            return _blocked("JSON_DUPLICATE_KEY")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _blocked("JSON_DECODING_FAILED")
        if config.approved_json_pointers and config.approved_json_pointers != self._approved:
            return _blocked("JSON_POINTER_CONFIGURATION_MISMATCH")
        try:
            _check_bounds(root, config.max_json_depth, config.max_json_array_items)
        except ValueError as error:
            return _blocked(str(error))
        values: list[tuple[str, str]] = []
        for pointer in self._approved:
            value = _resolve(root, pointer)
            if isinstance(value, str):
                values.append((pointer, value))
        text = "\n".join(value for _, value in values)
        if len(text) > config.max_document_characters:
            return _blocked("DOCUMENT_CHARACTER_LIMIT_EXCEEDED")
        sections: list[ParsedSection] = []
        offset = 0
        for pointer, value in values:
            end = offset + len(value)
            sections.append(
                ParsedSection(
                    section_path=pointer,
                    level=1,
                    title=pointer,
                    locator_type=LocatorType.JSON_POINTER,
                    start_offset=offset,
                    end_offset=end,
                    text_checksum=hashlib.sha256(value.encode()).hexdigest(),
                    content_kind=ContentKind.JSON,
                )
            )
            offset = end + 1
        return ParsedDocument(
            canonical_text=text,
            canonical_text_checksum=hashlib.sha256(text.encode()).hexdigest(),
            sections=tuple(sections),
            status=ParseStatus.PASS,
            safety_markers=tuple(mark_untrusted_instructions(text)),
            parser_metadata={"pointer_order": "lexical", "unknown_fields": "not-searchable"},
        )


def _resolve(root: Any, pointer: str) -> Any:
    value = root
    for raw in pointer.split("/")[1:]:
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdecimal() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def _check_bounds(root: Any, max_depth: int, max_items: int) -> None:
    stack: list[tuple[Any, int]] = [(root, 1)]
    while stack:
        value, depth = stack.pop()
        if depth > max_depth:
            raise ValueError("JSON_DEPTH_LIMIT_EXCEEDED")
        if isinstance(value, list):
            if len(value) > max_items:
                raise ValueError("JSON_ARRAY_LIMIT_EXCEEDED")
            stack.extend((item, depth + 1) for item in value)
        elif isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())


def _blocked(warning: str) -> ParsedDocument:
    return ParsedDocument(
        canonical_text="",
        canonical_text_checksum=hashlib.sha256(b"").hexdigest(),
        status=ParseStatus.BLOCKED,
        warnings=(warning,),
    )
