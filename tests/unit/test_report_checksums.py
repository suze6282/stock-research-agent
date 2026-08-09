from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID

import pytest

from stock_research_agent.domain.reports.canonical import canonical_report_json
from stock_research_agent.domain.reports.enums import ReportLocale, ReportSection
from stock_research_agent.domain.reports.markdown import DeterministicMarkdownRenderer
from stock_research_agent.domain.reports.references import (
    ReferenceEntry,
    ReferenceKind,
)
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
    ReportSectionStatus,
    StructuredReportBlock,
    StructuredReportContent,
    StructuredReportSection,
)

NOW = datetime(2026, 7, 28, 8, tzinfo=UTC)
REPORT_ID = UUID(int=1)
METRIC_ID = UUID(int=2)


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.checksums")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 report checksum verifier is missing")


def _content() -> StructuredReportContent:
    return StructuredReportContent(
        schema_version="research-report-v1",
        locale=ReportLocale.EN_US,
        sections=(
            StructuredReportSection(
                section=ReportSection.FINANCIAL_HEALTH,
                section_index=0,
                title="Financial Health",
                status=ReportSectionStatus.PARTIAL,
                blocks=(
                    StructuredReportBlock(
                        block_key="claim.return_on_equity.0",
                        block_index=0,
                        block_type=ReportBlockType.METRIC_TABLE,
                        status=ReportBlockStatus.COMPLETE,
                        text="12.50 PERCENT, FY2025 [MET-001]",
                        payload={
                            "reference": "[MET-001]",
                            "support_status": "SUPPORTED",
                            "value": "12.50",
                            "unit": "PERCENT",
                            "period": "FY2025",
                        },
                    ),
                ),
            ),
            StructuredReportSection(
                section=ReportSection.LIMITATIONS,
                section_index=1,
                title="Limitations",
                status=ReportSectionStatus.BLOCKED,
                blocks=(
                    StructuredReportBlock(
                        block_key="limitation.missing_body.0",
                        block_index=0,
                        block_type=ReportBlockType.LIMITATION,
                        status=ReportBlockStatus.BLOCKED,
                        text="Document body unavailable [LIM-001]",
                        payload={
                            "reference": "[LIM-001]",
                            "support_status": "BLOCKED",
                        },
                    ),
                ),
            ),
        ),
    )


def _context(**updates: object) -> object:
    module = _module()
    values: dict[str, object] = {
        "schema_version": "research-report-v1",
        "template_name": "data_only_full",
        "template_version": "1.0.0",
        "renderer_version": "deterministic-report-renderer-v1",
        "markdown_renderer_version": "deterministic-markdown-v1",
        "locale": ReportLocale.EN_US,
        "input_manifest_checksum": "a" * 64,
        "visible_references": (
            ReferenceEntry(
                kind=ReferenceKind.METRIC,
                record_id=METRIC_ID,
                label="MET-001",
            ),
        ),
        "audit_report_id": REPORT_ID,
        "audit_created_at": NOW,
    }
    values.update(updates)
    return module.ReportChecksumContext.model_validate(values)


def _checksums(content: StructuredReportContent | None = None) -> tuple[object, str]:
    module = _module()
    structured = content or _content()
    markdown = DeterministicMarkdownRenderer().render(structured).markdown_content
    structured_hash = module.structured_report_checksum(structured)
    markdown_hash = module.markdown_checksum(markdown)
    combined = module.combined_report_checksum(
        structured_hash,
        markdown_hash,
        _context(),
    )
    return (
        module.ReportProjectionChecksums(
            structured_checksum=structured_hash,
            markdown_checksum=markdown_hash,
            content_checksum=combined,
        ),
        markdown,
    )


def test_checksum_functions_match_independent_manual_sha256() -> None:
    module = _module()
    content = _content()
    expected_structured = hashlib.sha256(canonical_report_json(content).encode("utf-8")).hexdigest()
    markdown = DeterministicMarkdownRenderer().render(content).markdown_content
    expected_markdown = hashlib.sha256(canonical_report_json(markdown).encode("utf-8")).hexdigest()
    context = _context()
    expected_combined = hashlib.sha256(
        canonical_report_json(
            {
                "schema_version": "research-report-v1",
                "structured_checksum": expected_structured,
                "markdown_checksum": expected_markdown,
                "template_name": "data_only_full",
                "template_version": "1.0.0",
                "renderer_version": "deterministic-report-renderer-v1",
                "markdown_renderer_version": "deterministic-markdown-v1",
                "locale": "en-US",
                "input_manifest_checksum": "a" * 64,
                "visible_references": [
                    {
                        "kind": "METRIC",
                        "record_id": str(METRIC_ID),
                        "label": "MET-001",
                    }
                ],
            }
        ).encode("utf-8")
    ).hexdigest()

    assert module.structured_report_checksum(content) == expected_structured
    assert module.markdown_checksum(markdown) == expected_markdown
    assert (
        module.combined_report_checksum(
            expected_structured,
            expected_markdown,
            context,
        )
        == expected_combined
    )


def test_projection_verifier_accepts_exact_json_markdown_parity() -> None:
    module = _module()
    expected, markdown = _checksums()

    assert (
        module.verify_report_projection(
            _content(),
            markdown,
            _context(),
            expected,
        )
        == expected
    )


def test_projection_verifier_rejects_manual_markdown_modification() -> None:
    module = _module()
    expected, markdown = _checksums()

    with pytest.raises(module.ReportChecksumError) as raised:
        module.verify_report_projection(
            _content(),
            markdown.replace("12.50", "99.99"),
            _context(),
            expected,
        )

    assert raised.value.code == "REPORT_MARKDOWN_PROJECTION_MISMATCH"


@pytest.mark.parametrize(
    "mutation",
    (
        "SECTION_TITLE",
        "SECTION_STATUS",
        "BLOCK_KEY",
        "BLOCK_TYPE",
        "BLOCK_STATUS",
        "BLOCK_TEXT",
        "REFERENCE",
        "VALUE",
        "UNIT",
        "PERIOD",
    ),
)
def test_projection_verifier_rejects_each_structured_semantic_change(
    mutation: str,
) -> None:
    module = _module()
    expected, markdown = _checksums()
    content = _content()
    section = content.sections[0]
    block = section.blocks[0]
    block_updates: dict[str, object] = {}
    section_updates: dict[str, object] = {}
    if mutation == "SECTION_TITLE":
        section_updates["title"] = "Changed"
    elif mutation == "SECTION_STATUS":
        section_updates["status"] = ReportSectionStatus.COMPLETE
    elif mutation == "BLOCK_KEY":
        block_updates["block_key"] = "claim.changed.0"
    elif mutation == "BLOCK_TYPE":
        block_updates["block_type"] = ReportBlockType.PARAGRAPH
    elif mutation == "BLOCK_STATUS":
        block_updates["status"] = ReportBlockStatus.PARTIAL
    elif mutation == "BLOCK_TEXT":
        block_updates["text"] = "Changed [MET-001]"
    else:
        payload = dict(block.payload)
        payload[
            {
                "REFERENCE": "reference",
                "VALUE": "value",
                "UNIT": "unit",
                "PERIOD": "period",
            }[mutation]
        ] = "changed"
        block_updates["payload"] = payload
    if block_updates:
        section_updates["blocks"] = (block.model_copy(update=block_updates),)
    changed_section = section.model_copy(update=section_updates)
    changed = content.model_copy(update={"sections": (changed_section, content.sections[1])})

    with pytest.raises(module.ReportChecksumError):
        module.verify_report_projection(changed, markdown, _context(), expected)


def test_combined_checksum_excludes_audit_id_and_time_but_includes_versions() -> None:
    module = _module()
    expected, _ = _checksums()
    baseline = module.combined_report_checksum(
        expected.structured_checksum,
        expected.markdown_checksum,
        _context(),
    )

    assert baseline == module.combined_report_checksum(
        expected.structured_checksum,
        expected.markdown_checksum,
        _context(
            audit_report_id=UUID(int=999),
            audit_created_at=NOW.replace(hour=9),
        ),
    )
    for update in (
        {"template_version": "1.0.1"},
        {"renderer_version": "deterministic-report-renderer-v2"},
        {"markdown_renderer_version": "deterministic-markdown-v2"},
        {"input_manifest_checksum": "b" * 64},
        {"locale": ReportLocale.ZH_CN},
    ):
        assert baseline != module.combined_report_checksum(
            expected.structured_checksum,
            expected.markdown_checksum,
            _context(**update),
        )
