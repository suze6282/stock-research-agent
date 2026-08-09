from __future__ import annotations

from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from stock_research_agent.domain.documents.enums import PageStatus, ParseStatus
from stock_research_agent.domain.documents.parsers.pdf import PdfTextParser
from stock_research_agent.domain.documents.schemas import ParserConfig


def _pdf(*, text: str | None = None, pages: int = 1, encrypted: bool = False) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        if text is not None:
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            resources = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {NameObject("/F1"): writer._add_object(font)}
                    )
                }
            )
            page[NameObject("/Resources")] = resources
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("synthetic-password")
    writer.write(output)
    return output.getvalue()


def test_pdf_parser_extracts_text_layer_with_one_based_physical_pages() -> None:
    result = PdfTextParser().parse(_pdf(text="Synthetic evidence"), ParserConfig())

    assert result.status == ParseStatus.PASS
    assert result.pages[0].page_number == 1
    assert result.pages[0].text.strip() == "Synthetic evidence"
    assert result.pages[0].status == PageStatus.PASS
    assert result.parser_metadata == {
        "ocr_used": "false",
        "reading_order": "best-effort",
        "physical_page_numbers": "one-based",
    }


def test_pdf_parser_marks_blank_text_layer_without_ocr() -> None:
    result = PdfTextParser().parse(_pdf(), ParserConfig())

    assert result.status == ParseStatus.PARTIAL
    assert result.pages[0].status == PageStatus.NO_TEXT
    assert result.warnings == ("PDF_PAGE_1_HAS_NO_TEXT_LAYER",)


def test_pdf_parser_blocks_encryption_page_limit_and_non_pdf_magic() -> None:
    encrypted = PdfTextParser().parse(_pdf(encrypted=True), ParserConfig())
    assert encrypted.status == ParseStatus.BLOCKED
    assert encrypted.warnings == ("PDF_ENCRYPTED",)

    too_many = PdfTextParser().parse(_pdf(pages=2), ParserConfig(max_pdf_pages=1))
    assert too_many.status == ParseStatus.BLOCKED
    assert too_many.warnings == ("PDF_PAGE_LIMIT_EXCEEDED",)

    invalid = PdfTextParser().parse(b"not a pdf", ParserConfig())
    assert invalid.status == ParseStatus.BLOCKED
    assert invalid.warnings == ("PDF_MAGIC_MISMATCH",)
