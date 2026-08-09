"""Text-layer-only PDF parser. OCR and attachment handling are intentionally absent."""

from __future__ import annotations

import hashlib
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from stock_research_agent.domain.documents.enums import PageStatus, ParseStatus
from stock_research_agent.domain.documents.injection import mark_untrusted_instructions
from stock_research_agent.domain.documents.schemas import ParsedDocument, ParsedPage, ParserConfig


class PdfTextParser:
    parser_name = "pypdf-text-layer"
    parser_version = "pdf-parser-v1"

    def parse(self, content: bytes, config: ParserConfig) -> ParsedDocument:
        if not content.startswith(b"%PDF-"):
            return _blocked("PDF_MAGIC_MISMATCH")
        if len(content) > config.max_document_bytes:
            return _blocked("DOCUMENT_BYTE_LIMIT_EXCEEDED")
        try:
            reader = PdfReader(BytesIO(content), strict=False)
        except (PdfReadError, ValueError, TypeError):
            return _blocked("PDF_DECODING_FAILED")
        if reader.is_encrypted:
            return _blocked("PDF_ENCRYPTED")
        if len(reader.pages) > config.max_pdf_pages:
            return _blocked("PDF_PAGE_LIMIT_EXCEEDED")

        pages: list[ParsedPage] = []
        warnings: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except (PdfReadError, KeyError, ValueError, TypeError):
                text = ""
                warnings.append(f"PDF_PAGE_{page_number}_EXTRACTION_FAILED")
                status = PageStatus.PARTIAL
            else:
                if not text.strip():
                    warnings.append(f"PDF_PAGE_{page_number}_HAS_NO_TEXT_LAYER")
                    status = PageStatus.NO_TEXT
                elif len(text) > config.max_characters_per_page:
                    text = text[: config.max_characters_per_page]
                    warnings.append(f"PDF_PAGE_{page_number}_CHARACTER_LIMIT_EXCEEDED")
                    status = PageStatus.PARTIAL
                else:
                    status = PageStatus.PASS
            pages.append(
                ParsedPage(
                    page_number=page_number,
                    text=text,
                    text_checksum=hashlib.sha256(text.encode()).hexdigest(),
                    character_count=len(text),
                    status=status,
                    warnings=tuple(item for item in warnings if f"PAGE_{page_number}_" in item),
                )
            )
        canonical_text = "\n\f\n".join(page.text for page in pages)
        if len(canonical_text) > config.max_document_characters:
            return _blocked("DOCUMENT_CHARACTER_LIMIT_EXCEEDED")
        result_status = ParseStatus.PARTIAL if warnings else ParseStatus.PASS
        return ParsedDocument(
            canonical_text=canonical_text,
            canonical_text_checksum=hashlib.sha256(canonical_text.encode()).hexdigest(),
            pages=tuple(pages),
            status=result_status,
            warnings=tuple(warnings),
            safety_markers=tuple(mark_untrusted_instructions(canonical_text)),
            parser_metadata={
                "ocr_used": "false",
                "reading_order": "best-effort",
                "physical_page_numbers": "one-based",
            },
        )


def _blocked(warning: str) -> ParsedDocument:
    return ParsedDocument(
        canonical_text="",
        canonical_text_checksum=hashlib.sha256(b"").hexdigest(),
        status=ParseStatus.BLOCKED,
        warnings=(warning,),
        parser_metadata={"ocr_used": "false", "reading_order": "unavailable"},
    )
