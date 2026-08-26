from __future__ import annotations

import pytest

from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.file_security import validate_mime


@pytest.mark.parametrize(
    ("content", "extension", "declared_mime"),
    [
        (b"%PDF-1.7\n", ".pdf", "application/pdf"),
        (b"<html></html>", ".html", "text/html"),
        (b"<!doctype html>", ".htm", "text/html"),
        (b"{}", ".json", "application/json"),
    ],
)
def test_initial_mime_allowlist_is_exact(
    content: bytes,
    extension: str,
    declared_mime: str,
) -> None:
    result = validate_mime(content, extension, declared_mime)

    assert result.extension == extension
    assert result.declared_mime == declared_mime
    assert result.allowed is True


@pytest.mark.parametrize(
    ("extension", "declared_mime"),
    [
        (".xml", "application/xml"),
        (".svg", "image/svg+xml"),
        (".zip", "application/zip"),
        (".exe", "application/octet-stream"),
        (".pdf", "application/octet-stream"),
    ],
)
def test_unapproved_mime_or_extension_is_rejected(
    extension: str,
    declared_mime: str,
) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_mime(b"synthetic", extension, declared_mime)

    assert exc_info.value.code == "MIME_NOT_ALLOWED"


@pytest.mark.parametrize(
    ("extension", "declared_mime"),
    [
        (".pdf", "text/html"),
        (".html", "application/pdf"),
        (".json", "text/html"),
    ],
)
def test_allowed_but_mismatched_extension_and_mime_is_rejected(
    extension: str,
    declared_mime: str,
) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_mime(b"synthetic", extension, declared_mime)

    assert exc_info.value.code == "MIME_EXTENSION_MISMATCH"
