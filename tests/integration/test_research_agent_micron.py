from stock_research_agent.domain.research_agent.enums import (
    ClaimType,
    ResearchPackageStatus,
    SyntheticStatus,
)
from stock_research_agent.domain.securities.seed import MICRON_SECURITY_ID
from tests.support.research_agent_scenarios import build_honest_degradation


def test_micron_metadata_only_state_degrades_without_promoting_metadata_to_body() -> None:
    scenario = build_honest_degradation(
        label="micron",
        security_id=MICRON_SECURITY_ID,
        security_query="MU",
        symbol="MU",
        issuer="Micron Technology, Inc.",
        exchange="XNAS",
    )

    assert scenario.request.security_query == "MU"
    assert scenario.package.status in {
        ResearchPackageStatus.PARTIAL,
        ResearchPackageStatus.BLOCKED,
    }
    assert all(item.synthetic_status is SyntheticStatus.REAL_VERIFIED for item in scenario.evidence)
    assert {claim.claim_type for claim in scenario.claims}.issubset(
        {ClaimType.IDENTITY, ClaimType.DATA_QUALITY, ClaimType.LIMITATION}
    )
    assert "VERIFIED_COMPANY_BODY_UNAVAILABLE" in scenario.package.blocked_capabilities
    serialized = scenario.package.model_dump_json()
    for prohibited in (
        "HBM_DEMAND",
        "INVENTORY_CYCLE",
        "DATA_CENTER_REVENUE",
        "RISK_FACTORS",
    ):
        assert prohibited not in serialized
