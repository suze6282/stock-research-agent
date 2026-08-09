"""Deterministic report section skeletons with explicit empty states."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.reports.enums import ReportLocale, ReportSection
from stock_research_agent.domain.reports.reporting import ReportSectionStatus
from stock_research_agent.domain.reports.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenReportContract,
    ReportInputManifest,
)
from stock_research_agent.domain.reports.templates import (
    ReportTemplateVersionRecord,
)
from stock_research_agent.domain.research_agent.enums import (
    PackageSectionStatus,
    ResearchSection,
)


class ReportSectionDraft(FrozenReportContract):
    section: ReportSection
    section_index: int = Field(ge=0, le=15)
    title: str = Field(min_length=1, max_length=160)
    status: ReportSectionStatus
    required: bool


class ReportSectionWrite(ReportSectionDraft):
    id: UUID
    report_id: UUID
    checksum: Checksum
    created_at: AwareUtcDateTime


def build_sections(
    template: ReportTemplateVersionRecord,
    manifest: ReportInputManifest,
) -> tuple[ReportSectionDraft, ...]:
    states = {item.section: item.status for item in manifest.section_states}
    rules = {item.section: item for item in template.section_rules}
    return tuple(
        ReportSectionDraft(
            section=section,
            section_index=index,
            title=_title(section, template.locale),
            status=_status(section, states, manifest),
            required=rules[section].required,
        )
        for index, section in enumerate(template.section_keys)
    )


def _status(
    section: ReportSection,
    states: dict[ResearchSection, PackageSectionStatus],
    manifest: ReportInputManifest,
) -> ReportSectionStatus:
    if section is ReportSection.RESEARCH_SCOPE:
        return ReportSectionStatus.COMPLETE
    try:
        research_section = ResearchSection(section.value)
    except ValueError:
        return (
            ReportSectionStatus.NO_EVIDENCE
            if section
            in {
                ReportSection.CONFLICTS,
                ReportSection.UNSUPPORTED_CLAIMS,
            }
            else ReportSectionStatus.NOT_REQUESTED
        )
    package_status = states.get(research_section)
    if package_status is None:
        if section is ReportSection.LIMITATIONS and manifest.blocked_capabilities:
            return ReportSectionStatus.BLOCKED
        if section in {ReportSection.DATA_QUALITY, ReportSection.LIMITATIONS}:
            return ReportSectionStatus.NO_EVIDENCE
        return ReportSectionStatus.NOT_REQUESTED
    return {
        PackageSectionStatus.PASS: ReportSectionStatus.COMPLETE,
        PackageSectionStatus.PARTIAL: ReportSectionStatus.PARTIAL,
        PackageSectionStatus.BLOCKED: ReportSectionStatus.BLOCKED,
        PackageSectionStatus.NO_EVIDENCE: ReportSectionStatus.NO_EVIDENCE,
        PackageSectionStatus.NOT_REQUESTED: ReportSectionStatus.NOT_REQUESTED,
    }[package_status]


_ZH_TITLES = {
    ReportSection.RESEARCH_SCOPE: "研究范围",
    ReportSection.SECURITY_IDENTITY: "证券身份",
    ReportSection.DATA_AVAILABILITY: "数据可用性",
    ReportSection.FINANCIAL_HEALTH: "财务健康",
    ReportSection.VALUATION_SNAPSHOT: "估值快照",
    ReportSection.DOCUMENT_EVIDENCE: "文档证据",
    ReportSection.CATALYST_EVIDENCE: "催化剂证据",
    ReportSection.RISK_EVIDENCE: "风险证据",
    ReportSection.CORPORATE_ACTIONS: "公司行动",
    ReportSection.DATA_QUALITY: "数据质量",
    ReportSection.CONFLICTS: "冲突",
    ReportSection.UNSUPPORTED_CLAIMS: "未支持声明",
    ReportSection.LIMITATIONS: "限制",
    ReportSection.CLAIM_INDEX: "声明索引",
    ReportSection.EVIDENCE_APPENDIX: "证据附录",
    ReportSection.CITATION_APPENDIX: "引用附录",
}

_EN_TITLES = {
    ReportSection.RESEARCH_SCOPE: "Research Scope",
    ReportSection.SECURITY_IDENTITY: "Security Identity",
    ReportSection.DATA_AVAILABILITY: "Data Availability",
    ReportSection.FINANCIAL_HEALTH: "Financial Health",
    ReportSection.VALUATION_SNAPSHOT: "Valuation Snapshot",
    ReportSection.DOCUMENT_EVIDENCE: "Document Evidence",
    ReportSection.CATALYST_EVIDENCE: "Catalyst Evidence",
    ReportSection.RISK_EVIDENCE: "Risk Evidence",
    ReportSection.CORPORATE_ACTIONS: "Corporate Actions",
    ReportSection.DATA_QUALITY: "Data Quality",
    ReportSection.CONFLICTS: "Conflicts",
    ReportSection.UNSUPPORTED_CLAIMS: "Unsupported Claims",
    ReportSection.LIMITATIONS: "Limitations",
    ReportSection.CLAIM_INDEX: "Claim Index",
    ReportSection.EVIDENCE_APPENDIX: "Evidence Appendix",
    ReportSection.CITATION_APPENDIX: "Citation Appendix",
}


def _title(section: ReportSection, locale: ReportLocale) -> str:
    return _ZH_TITLES[section] if locale is ReportLocale.ZH_CN else _EN_TITLES[section]
