from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter

from stock_research_agent.domain.live_evidence.enums import ManualValidationStatus
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.pdf_security import inspect_pdf


def _pdf(*, encrypted: bool = False, title: str | None = None) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    if title is not None:
        writer.add_metadata({"/Title": title})
    if encrypted:
        writer.encrypt("synthetic-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_static_pdf_inspection_accepts_bounded_structural_pdf() -> None:
    result = inspect_pdf(_pdf())

    assert result.status is ManualValidationStatus.PASS
    assert result.page_count == 1
    assert result.object_count > 0
    assert result.finding_codes == ()


def test_encrypted_pdf_is_blocked_without_password_attempt() -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_pdf(_pdf(encrypted=True))

    assert exc_info.value.code == "PDF_ENCRYPTED"


@pytest.mark.parametrize("content", [b"not a pdf", b"%PDF-1.7\ntruncated"])
def test_corrupt_pdf_is_blocked(content: bytes) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_pdf(content)

    assert exc_info.value.code == "PDF_CORRUPT"


def test_pdf_object_limit_is_enforced_before_deep_processing() -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_pdf(_pdf(), max_objects=1)

    assert exc_info.value.code == "PDF_OBJECT_LIMIT"


def test_external_execution_action_is_blocked_as_inert_bytes() -> None:
    content = _pdf().replace(b"/Producer", b"/URI /Producer", 1)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_pdf(content)

    assert exc_info.value.code == "PDF_EXTERNAL_EXECUTION"


@pytest.mark.parametrize("token", [b"/JavaScript", b"/JS"])
def test_pdf_javascript_is_blocked(token: bytes) -> None:
    content = _pdf().replace(b"/Producer", token + b" /Producer", 1)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_pdf(content)

    assert exc_info.value.code == "PDF_JAVASCRIPT"


def test_visible_javascript_word_is_not_treated_as_an_action_name() -> None:
    content = _pdf(title="JavaScript")

    assert inspect_pdf(content).status is ManualValidationStatus.PASS


@pytest.mark.parametrize(
    ("token", "expected_code"),
    [
        (b"/Launch", "PDF_LAUNCH_ACTION"),
        (b"/OpenAction", "PDF_OPEN_ACTION"),
    ],
)
def test_pdf_launch_or_open_action_is_blocked(token: bytes, expected_code: str) -> None:
    content = _pdf().replace(b"/Producer", token + b" /Producer", 1)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_pdf(content)

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    "token",
    [b"/EmbeddedFile", b"/EmbeddedFiles", b"/FileAttachment"],
)
def test_pdf_embedded_file_or_attachment_is_blocked(token: bytes) -> None:
    content = _pdf().replace(b"/Producer", token + b" /Producer", 1)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_pdf(content)

    assert exc_info.value.code == "PDF_EMBEDDED_FILE"


def test_pdf_rich_media_is_blocked() -> None:
    content = _pdf().replace(b"/Producer", b"/RichMedia /Producer", 1)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_pdf(content)

    assert exc_info.value.code == "PDF_RICH_MEDIA"
