from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)

NOW = datetime(2026, 7, 26, 15, tzinfo=UTC)


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.reporting")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 immutable research report aggregate is missing")


def _content() -> object:
    module = _module()
    return module.StructuredReportContent(
        schema_version="research-report-v1",
        locale=ReportLocale.ZH_CN,
        sections=(
            module.StructuredReportSection(
                section=ReportSection.DATA_QUALITY,
                section_index=0,
                title="数据质量",
                status=module.ReportSectionStatus.PARTIAL,
                blocks=(
                    module.StructuredReportBlock(
                        block_key="data_quality.summary",
                        block_index=0,
                        block_type=module.ReportBlockType.WARNING,
                        status=module.ReportBlockStatus.PARTIAL,
                        text="当前证据不完整。",
                        payload={"warning_code": "REAL_COMPANY_EVIDENCE_PARTIAL"},
                    ),
                ),
            ),
            module.StructuredReportSection(
                section=ReportSection.LIMITATIONS,
                section_index=1,
                title="限制",
                status=module.ReportSectionStatus.BLOCKED,
                blocks=(
                    module.StructuredReportBlock(
                        block_key="limitations.document",
                        block_index=0,
                        block_type=module.ReportBlockType.LIMITATION,
                        status=module.ReportBlockStatus.BLOCKED,
                        text="公司正文证据缺失。",
                        payload={"code": "COMPANY_BODY_MISSING"},
                    ),
                ),
            ),
        ),
    )


def _record_values(**updates: object) -> dict[str, object]:
    module = _module()
    values: dict[str, object] = {
        "id": UUID("10000000-0000-0000-0000-000000000001"),
        "report_generation_run_id": UUID("10000000-0000-0000-0000-000000000002"),
        "report_version": 1,
        "previous_report_id": None,
        "report_type": ReportType.EVIDENCE_SUMMARY,
        "report_locale": ReportLocale.ZH_CN,
        "status": module.ResearchReportStatus.PARTIAL,
        "title": "可验证研究摘要",
        "subtitle": "离线证据约束结果",
        "security_id": UUID("10000000-0000-0000-0000-000000000003"),
        "snapshot_id": UUID("10000000-0000-0000-0000-000000000004"),
        "research_as_of_time": NOW,
        "research_package_id": UUID("10000000-0000-0000-0000-000000000005"),
        "input_manifest_checksum": "a" * 64,
        "package_checksum": "b" * 64,
        "structured_content": _content(),
        "markdown_content": "# 可验证研究摘要\n",
        "structured_checksum": "c" * 64,
        "markdown_checksum": "d" * 64,
        "content_checksum": "e" * 64,
        "claim_set_checksum": "f" * 64,
        "evidence_set_checksum": "0" * 64,
        "link_set_checksum": "1" * 64,
        "citation_set_checksum": "2" * 64,
        "renderer_version": "deterministic-report-renderer-v1",
        "template_name": "evidence_summary",
        "template_version": "1.0.0",
        "created_at": NOW,
    }
    values.update(updates)
    return values


def test_report_record_requires_canonical_json_markdown_and_all_checksums() -> None:
    module = _module()

    record = module.ResearchReportRecord.model_validate(_record_values())

    assert record.structured_content.schema_version == "research-report-v1"
    assert record.markdown_content.endswith("\n")
    assert record.status is module.ResearchReportStatus.PARTIAL
    assert len(record.content_checksum) == 64


def test_structured_content_is_bounded_ordered_and_frozen() -> None:
    content = _content()

    assert tuple(section.section_index for section in content.sections) == (0, 1)
    assert content.sections[0].blocks[0].block_index == 0
    with pytest.raises(ValidationError, match="Instance is frozen"):
        content.sections[0].title = "replaced"

    module = _module()
    with pytest.raises(ValidationError, match="contiguous"):
        module.StructuredReportContent(
            schema_version="research-report-v1",
            locale=ReportLocale.ZH_CN,
            sections=(content.sections[0].model_copy(update={"section_index": 2}),),
        )


@pytest.mark.parametrize(
    "field",
    [
        "structured_content",
        "markdown_content",
        "structured_checksum",
        "markdown_checksum",
        "content_checksum",
    ],
)
def test_report_record_rejects_missing_canonical_artifact_fields(field: str) -> None:
    module = _module()
    values = _record_values()
    values.pop(field)

    with pytest.raises(ValidationError):
        module.ResearchReportRecord.model_validate(values)


def test_report_contract_exposes_no_advice_forecast_or_public_publish_fields() -> None:
    module = _module()
    fields = set(module.ResearchReportRecord.model_fields)
    forbidden = {
        "rating",
        "recommendation",
        "target_price",
        "position_size",
        "forecast",
        "confidence",
        "public_url",
        "published_at",
        "distribution_status",
    }

    assert forbidden.isdisjoint(fields)
    serialized = module.ResearchReportRecord.model_validate(_record_values()).model_dump(
        mode="json"
    )
    assert forbidden.isdisjoint(serialized)


def test_report_rejects_bad_markdown_shape_unknown_fields_and_oversized_blocks() -> None:
    module = _module()
    with pytest.raises(ValidationError, match="trailing newline"):
        module.ResearchReportRecord.model_validate(
            _record_values(markdown_content="# missing newline")
        )
    with pytest.raises(ValidationError):
        module.ResearchReportRecord.model_validate(_record_values(recommendation="BUY"))
    with pytest.raises(ValidationError):
        module.StructuredReportContent(
            schema_version="research-report-v1",
            locale=ReportLocale.ZH_CN,
            sections=tuple(
                _content().sections[0].model_copy(update={"section_index": index})
                for index in range(17)
            ),
        )
