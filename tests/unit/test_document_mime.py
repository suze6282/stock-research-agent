from __future__ import annotations

import hashlib

import pytest

from stock_research_agent.domain.documents.mime import (
    DocumentContentValidationError,
    validate_document_content,
)


@pytest.mark.parametrize(
    ("content", "mime_type", "detected"),
    [
        (b"%PDF-1.4\nsynthetic", "application/pdf", "application/pdf"),
        (b"<!doctype html><p>safe</p>", "text/html", "text/html"),
        (b"safe utf-8 text", "text/plain", "text/plain"),
        (b'{"safe":"text"}', "application/json", "application/json"),
    ],
)
def test_validate_document_content_accepts_allowlisted_magic(
    content: bytes, mime_type: str, detected: str
) -> None:
    result = validate_document_content(content, mime_type, 10_000_000)

    assert result.detected_mime_type == detected
    assert result.checksum == hashlib.sha256(content).hexdigest()
    assert result.byte_size == len(content)


@pytest.mark.parametrize(
    ("content", "mime_type", "message"),
    [
        (b"", "text/plain", "empty"),
        (b"MZ executable", "text/plain", "dangerous"),
        (b"PK\x03\x04archive", "application/pdf", "dangerous"),
        (b"%PDF-1.4", "text/plain", "MIME"),
        (b"\x00" * 20 + b"text", "text/plain", "NUL"),
        (b"text", "application/octet-stream", "allowlisted"),
    ],
)
def test_validate_document_content_rejects_unsafe_or_mismatched_content(
    content: bytes, mime_type: str, message: str
) -> None:
    with pytest.raises(DocumentContentValidationError, match=message):
        validate_document_content(content, mime_type, 10_000_000)


def test_validate_document_content_enforces_bound_before_parsing() -> None:
    with pytest.raises(DocumentContentValidationError, match="size"):
        validate_document_content(b"four", "text/plain", 3)
