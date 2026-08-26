"""Inert HTML safety inspection with no renderer or resource loading."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from stock_research_agent.domain.live_evidence.enums import ManualValidationStatus
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.providers.schemas import FrozenProviderContract


class HtmlSafetyResult(FrozenProviderContract):
    status: ManualValidationStatus
    finding_codes: tuple[str, ...]


class _SafetyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.script_found = False
        self.event_handler_found = False
        self.javascript_url_found = False
        self.external_resource_found = False
        self.local_file_reference_found = False
        self.meta_refresh_found = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        lowered_tag = tag.lower()
        if lowered_tag == "script":
            self.script_found = True
        attributes = {name.lower(): value for name, value in attrs}
        if lowered_tag == "meta" and (
            (attributes.get("http-equiv") or "").strip().lower() == "refresh"
        ):
            self.meta_refresh_found = True
        for name, value in attrs:
            lowered_name = name.lower()
            normalized_value = "" if value is None else value.strip().lower()
            if lowered_name.startswith("on"):
                self.event_handler_found = True
            if normalized_value.startswith("javascript:"):
                self.javascript_url_found = True
            if (
                normalized_value.startswith(("file:", "\\\\"))
                or re.match(r"^[a-z]:[\\/]", normalized_value) is not None
            ):
                self.local_file_reference_found = True
        if lowered_tag in {"img", "link", "iframe", "frame", "object", "embed", "source"}:
            self.external_resource_found = True

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)


def inspect_html(content: bytes, *, max_characters: int = 10_000_000) -> HtmlSafetyResult:
    try:
        decoded = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as error:
        raise LiveEvidenceValidationError("HTML_ENCODING_INVALID") from error
    if len(decoded) > max_characters:
        raise LiveEvidenceValidationError("HTML_SIZE_LIMIT")
    parser = _SafetyParser()
    parser.feed(decoded)
    parser.close()
    if parser.script_found:
        raise LiveEvidenceValidationError("HTML_SCRIPT")
    if parser.event_handler_found:
        raise LiveEvidenceValidationError("HTML_EVENT_HANDLER")
    if parser.javascript_url_found:
        raise LiveEvidenceValidationError("HTML_JAVASCRIPT_URL")
    if parser.local_file_reference_found:
        raise LiveEvidenceValidationError("HTML_LOCAL_FILE_REFERENCE")
    if parser.meta_refresh_found:
        raise LiveEvidenceValidationError("HTML_META_REFRESH")
    if parser.external_resource_found:
        raise LiveEvidenceValidationError("HTML_EXTERNAL_RESOURCE")
    return HtmlSafetyResult(
        status=ManualValidationStatus.PASS,
        finding_codes=(),
    )
