from __future__ import annotations

from stock_research_agent.domain.documents.enums import ContentKind, ParseStatus
from stock_research_agent.domain.documents.parsers.html import SafeHtmlParser
from stock_research_agent.domain.documents.schemas import ParserConfig


def test_html_parser_preserves_safe_content_and_suppresses_active_elements() -> None:
    body = b"""<!doctype html><html><body>
    <h1 id='risk'>Risk Factors</h1><p onclick='steal()'>Safe paragraph.</p>
    <script>fetch('https://evil.invalid')</script><iframe src='https://evil.invalid'></iframe>
    <table><tr><td>A</td><td>B</td></tr></table></body></html>"""

    result = SafeHtmlParser().parse(body, ParserConfig())

    assert result.status == ParseStatus.PASS
    assert "Risk Factors" in result.canonical_text
    assert "Safe paragraph." in result.canonical_text
    assert "fetch" not in result.canonical_text
    assert "evil.invalid" not in result.canonical_text
    assert any(section.title == "Risk Factors" for section in result.sections)
    assert any(section.content_kind == ContentKind.TABLE for section in result.sections)


def test_html_parser_honestly_downgrades_malformed_or_bounded_input() -> None:
    malformed = SafeHtmlParser().parse(b"<html><p>unclosed", ParserConfig())
    assert malformed.status == ParseStatus.PARTIAL
    assert "HTML_STRUCTURE_UNCERTAIN" in malformed.warnings

    bounded = SafeHtmlParser().parse(
        b"<html><p>one</p><p>two</p></html>",
        ParserConfig(max_html_nodes=2),
    )
    assert bounded.status == ParseStatus.BLOCKED
    assert bounded.warnings == ("HTML_NODE_LIMIT_EXCEEDED",)
