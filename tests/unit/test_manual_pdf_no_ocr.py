from __future__ import annotations

import inspect
from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from stock_research_agent.domain.documents.enums import ParseStatus
from stock_research_agent.domain.documents.parsers import pdf as pdf_parser_module
from stock_research_agent.domain.documents.parsers.pdf import PdfTextParser
from stock_research_agent.domain.documents.schemas import ParserConfig
from stock_research_agent.domain.live_evidence.enums import ManualValidationStatus
from stock_research_agent.domain.live_evidence.pdf_security import pdf_parse_policy


def _pdf(page_texts: tuple[str | None, ...]) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=72, height=72)
        if text is None:
            continue
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 10 Tf 2 50 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(output)
    return output.getvalue()


def test_text_layer_pdf_is_admitted_without_ocr() -> None:
    parsed = PdfTextParser().parse(_pdf(("Synthetic",)), ParserConfig())

    decision = pdf_parse_policy(parsed)

    assert parsed.status is ParseStatus.PASS
    assert decision.status is ManualValidationStatus.PASS
    assert decision.allowed is True
    assert decision.warning_codes == ()


def test_scan_like_pdf_without_any_text_layer_is_blocked() -> None:
    parsed = PdfTextParser().parse(_pdf((None,)), ParserConfig())

    decision = pdf_parse_policy(parsed)

    assert decision.status is ManualValidationStatus.BLOCKED
    assert decision.allowed is False
    assert decision.warning_codes == ("OCR_REQUIRED_BLOCKED",)


def test_partially_missing_text_layer_is_honestly_partial() -> None:
    parsed = PdfTextParser().parse(_pdf(("Synthetic", None)), ParserConfig())

    decision = pdf_parse_policy(parsed)

    assert decision.status is ManualValidationStatus.PARTIAL
    assert decision.allowed is False
    assert decision.warning_codes == ("PDF_TEXT_LAYER_INSUFFICIENT",)


def test_pdf_paths_import_no_ocr_or_subprocess_capability() -> None:
    source = inspect.getsource(pdf_parser_module)
    security_source = inspect.getsource(pdf_parse_policy)

    assert "pytesseract" not in source
    assert "ocrmypdf" not in source
    assert "subprocess" not in source
    assert "subprocess" not in security_source
