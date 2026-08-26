"""Bounded static PDF inspection; never renders, follows links, or invokes OCR."""

from __future__ import annotations

import re
from io import BytesIO

from pydantic import Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from stock_research_agent.domain.documents.enums import PageStatus, ParseStatus
from stock_research_agent.domain.documents.schemas import ParsedDocument
from stock_research_agent.domain.live_evidence.enums import ManualValidationStatus
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.providers.schemas import FrozenProviderContract


class PdfSafetyResult(FrozenProviderContract):
    status: ManualValidationStatus
    page_count: int = Field(ge=0, le=2000)
    object_count: int = Field(ge=0, le=200_000)
    finding_codes: tuple[str, ...]


class PdfInspection(FrozenProviderContract):
    action_names: tuple[str, ...]


class ParserAdmissionDecision(FrozenProviderContract):
    status: ManualValidationStatus
    allowed: bool
    warning_codes: tuple[str, ...]


def inspect_pdf_actions(content: bytes) -> PdfInspection:
    names = tuple(
        sorted({match.decode("ascii") for match in re.findall(rb"/([A-Za-z]+)\b", content)})
    )
    return PdfInspection(action_names=names)


def reject_active_pdf_actions(inspection: PdfInspection) -> None:
    if {"JavaScript", "JS"}.intersection(inspection.action_names):
        raise LiveEvidenceValidationError("PDF_JAVASCRIPT")
    if "Launch" in inspection.action_names:
        raise LiveEvidenceValidationError("PDF_LAUNCH_ACTION")
    if "OpenAction" in inspection.action_names:
        raise LiveEvidenceValidationError("PDF_OPEN_ACTION")
    if {"EmbeddedFile", "EmbeddedFiles", "FileAttachment"}.intersection(inspection.action_names):
        raise LiveEvidenceValidationError("PDF_EMBEDDED_FILE")
    if "RichMedia" in inspection.action_names:
        raise LiveEvidenceValidationError("PDF_RICH_MEDIA")


def pdf_parse_policy(result: ParsedDocument) -> ParserAdmissionDecision:
    text_page_count = sum(1 for page in result.pages if page.text.strip())
    if text_page_count == 0:
        return ParserAdmissionDecision(
            status=ManualValidationStatus.BLOCKED,
            allowed=False,
            warning_codes=("OCR_REQUIRED_BLOCKED",),
        )
    if result.status is ParseStatus.BLOCKED or any(
        page.status is not PageStatus.PASS for page in result.pages
    ):
        return ParserAdmissionDecision(
            status=ManualValidationStatus.PARTIAL,
            allowed=False,
            warning_codes=("PDF_TEXT_LAYER_INSUFFICIENT",),
        )
    return ParserAdmissionDecision(
        status=ManualValidationStatus.PASS,
        allowed=True,
        warning_codes=(),
    )


def inspect_pdf(
    content: bytes,
    *,
    max_objects: int = 200_000,
    max_pages: int = 2000,
) -> PdfSafetyResult:
    if not content.startswith(b"%PDF-"):
        raise LiveEvidenceValidationError("PDF_CORRUPT")
    reject_active_pdf_actions(inspect_pdf_actions(content))
    if any(token in content for token in (b"/URI", b"/GoToR", b"/SubmitForm")):
        raise LiveEvidenceValidationError("PDF_EXTERNAL_EXECUTION")
    object_count = len(re.findall(rb"\b\d+\s+\d+\s+obj\b", content))
    if object_count > max_objects:
        raise LiveEvidenceValidationError("PDF_OBJECT_LIMIT")
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise LiveEvidenceValidationError("PDF_ENCRYPTED")
        page_count = len(reader.pages)
    except LiveEvidenceValidationError:
        raise
    except (PdfReadError, ValueError, TypeError, OSError) as error:
        raise LiveEvidenceValidationError("PDF_CORRUPT") from error
    if page_count > max_pages:
        raise LiveEvidenceValidationError("PDF_OBJECT_LIMIT")
    return PdfSafetyResult(
        status=ManualValidationStatus.PASS,
        page_count=page_count,
        object_count=object_count,
        finding_codes=(),
    )
