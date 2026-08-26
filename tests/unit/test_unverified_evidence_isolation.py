from __future__ import annotations

from dataclasses import replace

import pytest

from stock_research_agent.domain.live_evidence.citation_eligibility import (
    EvidenceClaimRequest,
    EvidenceUseTarget,
    evaluate_claim_eligibility,
)
from stock_research_agent.domain.live_evidence.enums import ManualEvidenceState
from stock_research_agent.domain.research_agent.enums import ClaimType, EvidenceRole


def _unverified_request() -> EvidenceClaimRequest:
    return EvidenceClaimRequest(
        evidence_state=ManualEvidenceState.QUARANTINED,
        manifest=None,
        manifest_registry=None,
        claim_type=ClaimType.DOCUMENT_DISCLOSURE,
        evidence_role=EvidenceRole.PRIMARY,
        intended_use=EvidenceUseTarget.CLAIM_SUPPORT,
    )


@pytest.mark.parametrize(
    ("target", "expected_code"),
    [
        (EvidenceUseTarget.CLAIM_SUPPORT, "UNVERIFIED_EVIDENCE_FORBIDDEN"),
        (EvidenceUseTarget.CITATION, "UNVERIFIED_CITATION_FORBIDDEN"),
        (EvidenceUseTarget.REPORT, "UNVERIFIED_REPORT_FORBIDDEN"),
    ],
)
def test_unverified_evidence_cannot_support_business_output(
    target: EvidenceUseTarget,
    expected_code: str,
) -> None:
    decision = evaluate_claim_eligibility(replace(_unverified_request(), intended_use=target))

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == (expected_code,)


@pytest.mark.parametrize("target", [EvidenceUseTarget.CLAIM_SUPPORT, EvidenceUseTarget.REPORT])
@pytest.mark.parametrize("claim_type", [ClaimType.DATA_QUALITY, ClaimType.LIMITATION])
def test_unverified_evidence_is_limited_to_quality_or_limitation_roles(
    target: EvidenceUseTarget,
    claim_type: ClaimType,
) -> None:
    decision = evaluate_claim_eligibility(
        replace(
            _unverified_request(),
            intended_use=target,
            claim_type=claim_type,
            evidence_role=EvidenceRole.LIMITATION,
        )
    )

    assert decision.status == "LIMITATION_ONLY"
    assert decision.warning_codes == ("UNVERIFIED_LIMITATION_ONLY",)


def test_unverified_evidence_cannot_be_promoted_by_claim_type_alone() -> None:
    decision = evaluate_claim_eligibility(
        replace(_unverified_request(), claim_type=ClaimType.DATA_QUALITY)
    )

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == ("UNVERIFIED_EVIDENCE_FORBIDDEN",)
