from __future__ import annotations

from importlib import import_module
from uuid import UUID

import pytest

from stock_research_agent.domain.reports.enums import ReportLocale, ReportSection, ReportType
from stock_research_agent.domain.reports.schemas import (
    ReportInputManifest,
    ReportInputSectionState,
)
from stock_research_agent.domain.reports.templates import (
    ReportTemplateVersionRecord,
    build_default_template_writes,
)
from stock_research_agent.domain.research_agent.enums import (
    PackageSectionStatus,
    ResearchSection,
)


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.sections")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 deterministic report sections are missing")


def _template(locale: ReportLocale = ReportLocale.ZH_CN) -> ReportTemplateVersionRecord:
    write = next(
        item
        for item in build_default_template_writes()
        if item.report_type is ReportType.EVIDENCE_SUMMARY and item.locale is locale
    )
    return ReportTemplateVersionRecord.model_construct(
        **write.__dict__,
        id=UUID("10000000-0000-0000-0000-000000000001"),
    )


def _manifest() -> ReportInputManifest:
    return ReportInputManifest.model_construct(
        package_status="PARTIAL",
        section_states=(
            ReportInputSectionState(
                section=ResearchSection.SECURITY_IDENTITY,
                status=PackageSectionStatus.PASS,
                claim_ids=(UUID(int=1),),
                warning_codes=(),
            ),
            ReportInputSectionState(
                section=ResearchSection.DOCUMENT_EVIDENCE,
                status=PackageSectionStatus.BLOCKED,
                claim_ids=(UUID(int=2),),
                warning_codes=("BLOCKED_CLAIMS",),
            ),
            ReportInputSectionState(
                section=ResearchSection.DATA_QUALITY,
                status=PackageSectionStatus.PARTIAL,
                claim_ids=(UUID(int=3),),
                warning_codes=("PARTIAL_REAL_EVIDENCE",),
            ),
            ReportInputSectionState(
                section=ResearchSection.LIMITATIONS,
                status=PackageSectionStatus.BLOCKED,
                claim_ids=(UUID(int=4),),
                warning_codes=("BLOCKED_CLAIMS",),
            ),
        ),
        blocked_capabilities=("COMPANY_BODY_MISSING",),
        warnings=("PARTIAL_REAL_EVIDENCE",),
    )


def test_sections_follow_exact_template_order_and_contiguous_indices() -> None:
    module = _module()

    sections = module.build_sections(_template(), _manifest())

    assert tuple(item.section for item in sections) == tuple(ReportSection)
    assert tuple(item.section_index for item in sections) == tuple(range(16))
    assert len({item.section for item in sections}) == 16


def test_sections_project_package_states_without_invented_content() -> None:
    module = _module()
    sections = {item.section: item for item in module.build_sections(_template(), _manifest())}

    assert sections[ReportSection.SECURITY_IDENTITY].status is module.ReportSectionStatus.COMPLETE
    assert sections[ReportSection.DOCUMENT_EVIDENCE].status is module.ReportSectionStatus.BLOCKED
    assert sections[ReportSection.DATA_QUALITY].status is module.ReportSectionStatus.PARTIAL
    assert sections[ReportSection.LIMITATIONS].status is module.ReportSectionStatus.BLOCKED
    assert (
        sections[ReportSection.VALUATION_SNAPSHOT].status
        is module.ReportSectionStatus.NOT_REQUESTED
    )
    assert all(not hasattr(item, "narrative") for item in sections.values())


def test_mandatory_sections_exist_even_when_manifest_has_no_matching_state() -> None:
    module = _module()
    manifest = _manifest().model_copy(update={"section_states": ()})
    sections = {item.section: item for item in module.build_sections(_template(), manifest)}

    assert sections[ReportSection.DATA_QUALITY].status is module.ReportSectionStatus.NO_EVIDENCE
    assert sections[ReportSection.LIMITATIONS].status is module.ReportSectionStatus.BLOCKED
    assert sections[ReportSection.DATA_QUALITY].required is True
    assert sections[ReportSection.LIMITATIONS].required is True


def test_section_titles_are_fixed_bilingual_labels() -> None:
    module = _module()

    zh = module.build_sections(_template(ReportLocale.ZH_CN), _manifest())
    en = module.build_sections(_template(ReportLocale.EN_US), _manifest())

    assert zh[0].title == "研究范围"
    assert en[0].title == "Research Scope"
    assert all(item.title for item in zh)
    assert all(item.title for item in en)
