from __future__ import annotations

from importlib import import_module

import pytest

from stock_research_agent.domain.reports.enums import ReportLocale, ReportSection
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
    ReportSectionStatus,
    StructuredReportBlock,
    StructuredReportContent,
    StructuredReportSection,
)


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.markdown")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 deterministic Markdown renderer is missing")


def _content() -> StructuredReportContent:
    return StructuredReportContent(
        schema_version="research-report-v1",
        locale=ReportLocale.EN_US,
        sections=(
            StructuredReportSection(
                section=ReportSection.FINANCIAL_HEALTH,
                section_index=0,
                title="Financial *Health* <unsafe>",
                status=ReportSectionStatus.PARTIAL,
                blocks=(
                    StructuredReportBlock(
                        block_key="claim.return_on_equity.0",
                        block_index=0,
                        block_type=ReportBlockType.METRIC_TABLE,
                        status=ReportBlockStatus.COMPLETE,
                        text="0.125 RATIO, period: FY2025 [MET-001]",
                        payload={
                            "claim_id": "20000000-0000-0000-0000-000000000001",
                            "reference": "[MET-001]",
                            "value": "0.125",
                            "unsafe": "<script>alert(1)</script>",
                        },
                    ),
                    StructuredReportBlock(
                        block_key="limitation.body_missing.1",
                        block_index=1,
                        block_type=ReportBlockType.LIMITATION,
                        status=ReportBlockStatus.BLOCKED,
                        text="Body _missing_ [LIM-001]\nsource unavailable",
                        payload={"warning": "BODY_MISSING"},
                    ),
                ),
            ),
            StructuredReportSection(
                section=ReportSection.CITATION_APPENDIX,
                section_index=1,
                title="Citation Appendix",
                status=ReportSectionStatus.NO_EVIDENCE,
                blocks=(
                    StructuredReportBlock(
                        block_key="empty.citation_appendix",
                        block_index=0,
                        block_type=ReportBlockType.HEADING,
                        status=ReportBlockStatus.NO_EVIDENCE,
                        text="NO_EVIDENCE",
                        payload={},
                    ),
                ),
            ),
        ),
    )


def test_markdown_is_a_pure_deterministic_projection() -> None:
    module = _module()
    renderer = module.DeterministicMarkdownRenderer()

    first = renderer.render(_content())
    second = renderer.render(_content())

    assert first == second
    assert first.renderer_version == "deterministic-markdown-v1"
    assert first.markdown_checksum == module.report_checksum(first.markdown_content)
    assert vars(renderer) == {}


def test_markdown_preserves_sections_blocks_statuses_references_and_values() -> None:
    markdown = _module().DeterministicMarkdownRenderer().render(_content()).markdown_content

    assert "FINANCIAL\\_HEALTH" in markdown
    assert "PARTIAL" in markdown
    assert "claim.return\\_on\\_equity.0" in markdown
    assert "METRIC\\_TABLE" in markdown
    assert "COMPLETE" in markdown
    assert "\\[MET-001\\]" in markdown
    assert "0.125" in markdown
    assert "FY2025" in markdown
    assert "LIMITATION" in markdown
    assert "BLOCKED" in markdown
    assert "\\[LIM-001\\]" in markdown
    assert "CITATION\\_APPENDIX" in markdown
    assert "NO\\_EVIDENCE" in markdown


def test_markdown_escapes_html_markdown_and_embedded_newlines() -> None:
    markdown = _module().DeterministicMarkdownRenderer().render(_content()).markdown_content

    assert "<script>" not in markdown
    assert "<unsafe>" not in markdown
    assert "&lt;script&gt;" in markdown
    assert "Financial \\*Health\\* &lt;unsafe&gt;" in markdown
    assert "Body \\_missing\\_" in markdown
    assert "Body _missing_" not in markdown
    assert "\\nsource unavailable" in markdown


def test_markdown_uses_lf_and_exactly_one_trailing_newline() -> None:
    markdown = _module().DeterministicMarkdownRenderer().render(_content()).markdown_content

    assert "\r" not in markdown
    assert markdown.endswith("\n")
    assert not markdown.endswith("\n\n")
