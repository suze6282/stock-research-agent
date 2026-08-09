"""Deterministic chunk-v1 construction over canonical document text."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass

from stock_research_agent.domain.documents.enums import ContentKind, DocumentLanguage, LocatorType
from stock_research_agent.domain.documents.schemas import (
    ChunkConfig,
    DocumentChunkDraft,
    ParsedDocument,
)

_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[.:%-][A-Za-z0-9]+)*|[\u3400-\u9fff]")


class DocumentChunker:
    def chunk(
        self,
        parsed: ParsedDocument,
        config: ChunkConfig,
    ) -> tuple[DocumentChunkDraft, ...]:
        text = parsed.canonical_text
        if not text:
            return ()
        results: list[DocumentChunkDraft] = []
        config_payload = config.model_dump(mode="json")
        for segment in _segments(parsed):
            segment_text = text[segment.start : segment.end]
            for local_start, local_end, forced in _ranges(segment_text, config):
                start = segment.start + local_start
                end = segment.start + local_end
                chunk_text = text[start:end]
                index = len(results)
                descriptor = {
                    "canonical_text_checksum": parsed.canonical_text_checksum,
                    "parser_metadata": parsed.parser_metadata,
                    "chunk_config": config_payload,
                    "chunk_version": config.chunk_version,
                    "chunk_index": index,
                    "locator_type": segment.locator_type.value,
                    "section_path": segment.section_path,
                    "html_anchor": segment.html_anchor,
                    "json_pointer": segment.json_pointer,
                    "start_page": segment.start_page,
                    "end_page": segment.end_page,
                    "start_offset": start,
                    "end_offset": end,
                    "text": chunk_text,
                }
                checksum = hashlib.sha256(
                    json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                results.append(
                    DocumentChunkDraft(
                        chunk_version=config.chunk_version,
                        chunk_index=index,
                        text=chunk_text,
                        normalized_text=_normalize(chunk_text),
                        language=_language(chunk_text),
                        content_kind=segment.content_kind,
                        locator_type=segment.locator_type,
                        section_path=segment.section_path,
                        html_anchor=segment.html_anchor,
                        json_pointer=segment.json_pointer,
                        start_page=segment.start_page,
                        end_page=segment.end_page,
                        start_offset=start,
                        end_offset=end,
                        token_count=len(_TOKEN.findall(chunk_text)),
                        checksum=checksum,
                        warnings=("FORCED_TOKEN_SPLIT",) if forced else (),
                    )
                )
        return tuple(results)


@dataclass(frozen=True, slots=True)
class _Segment:
    start: int
    end: int
    locator_type: LocatorType
    content_kind: ContentKind
    section_path: str | None = None
    html_anchor: str | None = None
    json_pointer: str | None = None
    start_page: int | None = None
    end_page: int | None = None


def _segments(parsed: ParsedDocument) -> tuple[_Segment, ...]:
    if parsed.pages:
        segments: list[_Segment] = []
        cursor = 0
        for page in parsed.pages:
            end = cursor + len(page.text)
            if end > cursor:
                segments.append(
                    _Segment(
                        start=cursor,
                        end=end,
                        locator_type=LocatorType.PDF_PAGE_RANGE,
                        content_kind=ContentKind.TEXT,
                        start_page=page.page_number,
                        end_page=page.page_number,
                    )
                )
            cursor = end + 3
        return tuple(segments)
    if parsed.sections:
        return tuple(
            _Segment(
                start=section.start_offset,
                end=section.end_offset,
                locator_type=section.locator_type,
                content_kind=section.content_kind,
                section_path=section.section_path,
                html_anchor=(
                    section.section_path
                    if section.locator_type == LocatorType.HTML_ANCHOR_RANGE
                    else None
                ),
                json_pointer=(
                    section.section_path
                    if section.locator_type == LocatorType.JSON_POINTER
                    else None
                ),
                start_page=section.start_page,
                end_page=section.end_page,
            )
            for section in parsed.sections
            if section.start_offset is not None
            and section.end_offset is not None
            and section.end_offset > section.start_offset
        )
    return (
        _Segment(
            start=0,
            end=len(parsed.canonical_text),
            locator_type=LocatorType.TEXT_OFFSET_RANGE,
            content_kind=ContentKind.TEXT,
        ),
    )


def _ranges(text: str, config: ChunkConfig) -> tuple[tuple[int, int, bool], ...]:
    if len(text) <= config.maximum_characters:
        return ((0, len(text), False),)
    ranges: list[tuple[int, int, bool]] = []
    start = 0
    while start < len(text):
        remaining = len(text) - start
        if remaining <= config.maximum_characters:
            end = len(text)
            forced = False
        else:
            target = min(start + config.target_characters, len(text))
            lower = min(start + config.minimum_characters, target)
            boundary = _last_boundary(text, lower, target)
            forced = boundary is None
            end = (
                boundary
                if boundary is not None
                else min(start + config.maximum_characters, len(text))
            )
        if ranges and end - start < config.minimum_characters:
            previous_start, _previous_end, previous_forced = ranges[-1]
            if end - previous_start <= config.maximum_characters:
                ranges[-1] = (previous_start, end, previous_forced or forced)
                break
            start = max(previous_start + 1, end - config.minimum_characters)
        ranges.append((start, end, forced))
        if end == len(text):
            break
        overlap = min(config.overlap_characters, config.target_characters // 5)
        next_start = end - overlap
        boundary = _first_boundary(text, next_start, end)
        start = boundary if boundary is not None and boundary < end else next_start
    return tuple(ranges)


def _last_boundary(text: str, lower: int, upper: int) -> int | None:
    for index in range(upper, lower, -1):
        if text[index - 1].isspace():
            return index
    return None


def _first_boundary(text: str, lower: int, upper: int) -> int | None:
    for index in range(max(lower, 0), upper):
        if text[index].isspace():
            return index + 1
    return None


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _language(value: str) -> DocumentLanguage:
    has_cjk = re.search(r"[\u3400-\u9fff]", value) is not None
    has_latin = re.search(r"[A-Za-z]", value) is not None
    if has_cjk and has_latin:
        return DocumentLanguage.MIXED
    if has_cjk:
        return DocumentLanguage.ZH_CN
    if has_latin:
        return DocumentLanguage.EN_US
    return DocumentLanguage.UNKNOWN
