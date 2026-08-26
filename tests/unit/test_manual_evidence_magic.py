from __future__ import annotations

import pytest

from stock_research_agent.domain.live_evidence.enums import ManualContentType
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.file_security import (
    detect_content_type,
    validate_mime,
)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"%PDF-1.7\nsynthetic", ManualContentType.PDF),
        (b"<!doctype html><html></html>", ManualContentType.HTML),
        (b"  <HTML></HTML>", ManualContentType.HTML),
        (b'{"synthetic":true}', ManualContentType.JSON),
        (b"\xef\xbb\xbf [1, 2]", ManualContentType.JSON),
    ],
)
def test_detects_only_initial_allowed_content_signatures(
    content: bytes,
    expected: ManualContentType,
) -> None:
    assert detect_content_type(content) is expected


@pytest.mark.parametrize(
    "content",
    [b"MZ\x90\x00synthetic", b"\x7fELFsynthetic"],
)
def test_executable_magic_is_forbidden(content: bytes) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        detect_content_type(content)

    assert exc_info.value.code == "EXECUTABLE_MAGIC_FORBIDDEN"


@pytest.mark.parametrize(
    "content",
    [b"PK\x03\x04archive", b"\x1f\x8bgzip", b"Rar!\x1a\x07", b"7z\xbc\xaf\x27\x1c"],
)
def test_archive_magic_is_forbidden(content: bytes) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        detect_content_type(content)

    assert exc_info.value.code == "ARCHIVE_FORBIDDEN"


def test_unknown_or_empty_magic_is_rejected() -> None:
    for content in (b"", b"plain text"):
        with pytest.raises(LiveEvidenceValidationError) as exc_info:
            detect_content_type(content)
        assert exc_info.value.code == "MAGIC_BYTES_MISMATCH"


def test_declared_mime_and_extension_must_match_detected_bytes() -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_mime(b"%PDF-1.7\nsynthetic", ".html", "text/html")

    assert exc_info.value.code == "MAGIC_BYTES_MISMATCH"
