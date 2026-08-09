from __future__ import annotations

from stock_research_agent.domain.reports.enums import ReportLocale, ReportSection
from stock_research_agent.domain.reports.release_gate import ReleaseGateDecision
from stock_research_agent.domain.reports.reporting import (
    ReportSectionStatus,
    ResearchReportStatus,
)
from stock_research_agent.domain.securities.seed import (
    MICRON_ISSUER_ID,
    MICRON_SECURITY_ID,
)
from tests.support.report_scenarios import (
    build_honest_real_company_scenario,
    run_honest_report_flow,
)


def test_micron_report_does_not_promote_sec_metadata_to_filing_body() -> None:
    scenario = build_honest_real_company_scenario(
        namespace="micron-stage8",
        security_id=MICRON_SECURITY_ID,
        issuer_id=MICRON_ISSUER_ID,
        security_query="NASDAQ:MU",
        issuer_name="Micron Technology, Inc.",
        symbol="MU",
        exchange="XNAS",
        locale=ReportLocale.EN_US,
    )
    result = run_honest_report_flow(scenario, namespace="micron-stage8")
    report = result.report.report
    sections = {section.section: section for section in report.structured_content.sections}

    assert report.security_id == MICRON_SECURITY_ID
    assert report.status in {ResearchReportStatus.PARTIAL, ResearchReportStatus.BLOCKED}
    assert sections[ReportSection.DOCUMENT_EVIDENCE].status in {
        ReportSectionStatus.NO_EVIDENCE,
        ReportSectionStatus.BLOCKED,
    }
    assert result.gate.internal_release_status in {
        ReleaseGateDecision.PARTIAL,
        ReleaseGateDecision.BLOCKED,
    }
    normalized = report.markdown_content.casefold()
    for fabricated in (
        "hbm demand",
        "inventory cycle",
        "data center revenue",
        "management guidance",
        "risk factors",
        "buy",
        "target price",
    ):
        assert fabricated not in normalized
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
