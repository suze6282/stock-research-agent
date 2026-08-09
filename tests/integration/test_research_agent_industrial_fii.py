from stock_research_agent.domain.research_agent.enums import (
    ClaimType,
    ResearchPackageStatus,
    ResearchRunStatus,
    SyntheticStatus,
)
from stock_research_agent.domain.securities.seed import INDUSTRIAL_FII_SECURITY_ID
from tests.support.research_agent_scenarios import build_honest_degradation


def test_industrial_fii_real_state_degrades_without_invented_company_claims() -> None:
    first = build_honest_degradation(
        label="industrial-fii",
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        security_query="601138.SH",
        symbol="601138",
        issuer="富士康工业互联网股份有限公司",
        exchange="XSHG",
    )
    replay = build_honest_degradation(
        label="industrial-fii",
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        security_query="601138.SH",
        symbol="601138",
        issuer="富士康工业互联网股份有限公司",
        exchange="XSHG",
    )

    assert first.request.security_query == "601138.SH"
    assert first.plan_checksum == replay.plan_checksum
    assert first.idempotency_key == replay.idempotency_key
    assert first.run_status in {ResearchRunStatus.PARTIAL, ResearchRunStatus.BLOCKED}
    assert first.package.status in {
        ResearchPackageStatus.PARTIAL,
        ResearchPackageStatus.BLOCKED,
    }
    assert "search_document_chunks" in first.tool_names
    assert all(item.synthetic_status is SyntheticStatus.REAL_VERIFIED for item in first.evidence)
    assert {claim.claim_type for claim in first.claims}.issubset(
        {ClaimType.IDENTITY, ClaimType.DATA_QUALITY, ClaimType.LIMITATION}
    )
    serialized = first.package.model_dump_json()
    for prohibited in ("AI_SERVER_GROWTH", "PROFIT_IMPROVEMENT", "ORDER_GROWTH"):
        assert prohibited not in serialized
