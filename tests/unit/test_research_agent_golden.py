from __future__ import annotations

import json
from pathlib import Path

from stock_research_agent.domain.research_agent.enums import (
    ClaimType,
    EvidenceStatus,
    EvidenceType,
    SyntheticStatus,
)
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_SECURITY_ID,
    MICRON_SECURITY_ID,
)
from tests.support.research_agent_scenarios import build_honest_degradation

GOLDEN = Path(__file__).parents[1] / "golden" / "research_agent_expected.json"


def _scenarios() -> dict[str, object]:
    industrial = build_honest_degradation(
        label="industrial-fii",
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        security_query="601138.SH",
        symbol="601138",
        issuer="富士康工业互联网股份有限公司",
        exchange="XSHG",
    )
    micron = build_honest_degradation(
        label="micron",
        security_id=MICRON_SECURITY_ID,
        security_query="MU",
        symbol="MU",
        issuer="Micron Technology, Inc.",
        exchange="XNAS",
    )
    return {
        "plan_checksum": industrial.plan_checksum,
        "tool_order": list(industrial.tool_names),
        "industrial_idempotency_key": industrial.idempotency_key,
        "micron_idempotency_key": micron.idempotency_key,
        "industrial_package_checksum": industrial.package.checksum,
        "micron_package_checksum": micron.package.checksum,
        "industrial_terminal": industrial.run_status.value,
        "micron_terminal": micron.run_status.value,
        "industrial_claim_types": sorted({claim.claim_type.value for claim in industrial.claims}),
        "micron_claim_types": sorted({claim.claim_type.value for claim in micron.claims}),
        "synthetic_real_isolation": all(
            item.synthetic_status is SyntheticStatus.REAL_VERIFIED
            for item in (*industrial.evidence, *micron.evidence)
        ),
        "blocked_evidence_status": EvidenceStatus.BLOCKED.value,
        "blocked_evidence_type": EvidenceType.BLOCKED_CAPABILITY_EVIDENCE.value,
        "allowed_real_claim_types": sorted(
            {
                ClaimType.IDENTITY.value,
                ClaimType.DATA_QUALITY.value,
                ClaimType.LIMITATION.value,
            }
        ),
        "future_rejection_code": "FUTURE_DATA",
    }


def test_fifteen_independently_recorded_golden_contracts_are_stable() -> None:
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = _scenarios()

    assert len(expected) == 15
    assert actual == expected
