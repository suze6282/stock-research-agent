"""Bounded MIME and magic-byte validation with no extension or network trust."""

from __future__ import annotations

import hashlib

from stock_research_agent.domain.documents.schemas import DocumentMimeType, ValidatedDocumentContent

_ALLOWED = frozenset({"application/pdf", "text/html", "text/plain", "application/json"})
_DANGEROUS_MAGIC = (b"MZ", b"PK\x03\x04", b"\x7fELF", b"Rar!", b"\x1f\x8b")


class DocumentContentValidationError(ValueError):
    """Safe document validation failure."""


def validate_document_content(
    content: bytes,
    declared_mime_type: str,
    max_bytes: int,
) -> ValidatedDocumentContent:
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise DocumentContentValidationError("maximum document size is invalid")
    if not isinstance(content, bytes):
        raise DocumentContentValidationError("document content must be bytes")
    if not content:
        raise DocumentContentValidationError("document content is empty")
    if len(content) > max_bytes:
        raise DocumentContentValidationError("document exceeds configured size")
    if declared_mime_type not in _ALLOWED:
        raise DocumentContentValidationError("declared MIME type is not allowlisted")
    if content.startswith(_DANGEROUS_MAGIC):
        raise DocumentContentValidationError("dangerous executable or archive magic")

    detected = _detect(content)
    if detected != declared_mime_type:
        raise DocumentContentValidationError("declared MIME type does not match content")
    return ValidatedDocumentContent(
        declared_mime_type=declared_mime_type,
        detected_mime_type=detected,
        checksum=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
    )


def _detect(content: bytes) -> DocumentMimeType:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    prefix = content[:1024].lstrip().lower()
    if prefix.startswith((b"<!doctype html", b"<html", b"<head", b"<body")):
        return "text/html"
    if prefix.startswith((b"{", b"[")):
        return "application/json"
    if content.count(b"\x00") * 20 > len(content):
        raise DocumentContentValidationError("NUL-heavy text is not accepted")
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DocumentContentValidationError("content is not valid UTF-8 text") from None
    return "text/plain"
