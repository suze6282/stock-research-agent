from __future__ import annotations

from stock_research_agent.domain.reports.enums import ReportLocale, ReportSection
from stock_research_agent.domain.reports.release_gate import ReleaseGateDecision
from stock_research_agent.domain.reports.reporting import (
    ReportSectionStatus,
    ResearchReportStatus,
)
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_ISSUER_ID,
    INDUSTRIAL_FII_SECURITY_ID,
)
from tests.support.report_scenarios import (
    build_honest_real_company_scenario,
    run_honest_report_flow,
)


def test_industrial_fii_report_honestly_degrades_without_company_body_or_financials() -> None:
    scenario = build_honest_real_company_scenario(
        namespace="industrial-fii-stage8",
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        issuer_id=INDUSTRIAL_FII_ISSUER_ID,
        security_query="601138.SH",
        issuer_name="富士康工业互联网股份有限公司",
        symbol="601138",
        exchange="XSHG",
        locale=ReportLocale.ZH_CN,
    )
    result = run_honest_report_flow(
        scenario,
        namespace="industrial-fii-stage8",
    )
    report = result.report.report
    sections = {section.section: section for section in report.structured_content.sections}

    assert report.security_id == INDUSTRIAL_FII_SECURITY_ID
    assert report.status in {ResearchReportStatus.PARTIAL, ResearchReportStatus.BLOCKED}
    assert sections[ReportSection.DOCUMENT_EVIDENCE].status in {
        ReportSectionStatus.NO_EVIDENCE,
        ReportSectionStatus.BLOCKED,
    }
    assert sections[ReportSection.FINANCIAL_HEALTH].status in {
        ReportSectionStatus.NO_EVIDENCE,
        ReportSectionStatus.PARTIAL,
        ReportSectionStatus.BLOCKED,
    }
    assert result.gate.internal_release_status in {
        ReleaseGateDecision.PARTIAL,
        ReleaseGateDecision.BLOCKED,
    }
    normalized = report.markdown_content.casefold()
    for fabricated in ("ai服务器增长", "利润改善", "订单增长", "买入", "目标价"):
        assert fabricated.casefold() not in normalized
    assert scenario.report_input.manifest.citation_ids == ()
    assert len(scenario.report_input.input.claims) == 1
    assert len(scenario.report_input.input.evidence) == 1
    assert len(result.report.claim_bindings) == 1
    assert len(result.report.evidence_bindings) == 1
    assert result.report.citation_bindings == ()
    assert (
        result.report.evidence_bindings[0].report_claim_binding_id
        == result.report.claim_bindings[0].id
    )
