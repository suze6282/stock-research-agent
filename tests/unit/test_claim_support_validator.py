from __future__ import annotations

import importlib
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.claims import ResearchClaimProposal
from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    ClaimType,
    EvidenceRole,
    EvidenceStatus,
    EvidenceType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import ResearchEvidenceRecord

MODULE = "stock_research_agent.domain.research_agent.claims"
NOW = datetime(2026, 7, 24, 8, tzinfo=UTC)
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
EVIDENCE_ID = UUID("22222222-2222-4222-8222-222222222222")
CLAIM_ID = UUID("33333333-3333-4333-8333-333333333333")


def _module() -> object:
    return importlib.import_module(MODULE)


def _claim(
    claim_type: ClaimType = ClaimType.IDENTITY,
    **updates: object,
) -> ResearchClaimProposal:
    values = {
        "id": CLAIM_ID,
        "run_id": RUN_ID,
        "claim_type": claim_type,
        "lifecycle_status": ClaimLifecycleStatus.CANDIDATE,
        "support_status": None,
        "statement_code": "SECURITY_IDENTITY",
        "builder_version": "deterministic-claim-builder-v1",
        "created_at": NOW,
        "proposed_evidence_ids": (EVIDENCE_ID,),
    }
    if claim_type in {
        ClaimType.FINANCIAL_FACT,
        ClaimType.FINANCIAL_METRIC,
        ClaimType.VALUATION_METRIC,
    }:
        values.update(
            {
                "statement_code": "RETURN_ON_EQUITY",
                "value": Decimal("0.125"),
                "unit": "RATIO",
                "period": "FY2025",
                "as_of_time": NOW,
                "metric_basis": "formula-v1",
            }
        )
    values.update(updates)
    return ResearchClaimProposal.model_validate(values)


def _evidence(
    evidence_type: EvidenceType = EvidenceType.SECURITY_MASTER_EVIDENCE,
    **updates: object,
) -> ResearchEvidenceRecord:
    values = {
        "id": EVIDENCE_ID,
        "run_id": RUN_ID,
        "observation_id": UUID("44444444-4444-4444-8444-444444444444"),
        "evidence_type": evidence_type,
        "status": EvidenceStatus.VALID,
        "schema_version": "evidence-v1",
        "security_id": UUID("55555555-5555-4555-8555-555555555555"),
        "snapshot_id": UUID("66666666-6666-4666-8666-666666666666"),
        "research_as_of_time": NOW,
        "source_record_type": "source",
        "source_record_id": UUID("77777777-7777-4777-8777-777777777777"),
        "source_checksum": "a" * 64,
        "published_at": NOW,
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
        "payload": {
            "security_id": "55555555-5555-4555-8555-555555555555",
            "issuer": "Issuer",
            "symbol": "TEST",
            "exchange": "XNAS",
        },
        "created_at": NOW,
    }
    values.update(updates)
    return ResearchEvidenceRecord.model_validate(values)


def _validator() -> object:
    current = 10

    def next_id() -> UUID:
        nonlocal current
        current += 1
        return UUID(int=current)

    return _module().ClaimSupportValidator(id_factory=next_id)


def test_valid_identity_evidence_is_supported_and_linked_once() -> None:
    result = _validator().validate(
        claim=_claim(),
        evidence=(_evidence(), _evidence()),
        completed_at=NOW,
        real_research=True,
    )

    assert result.completion.lifecycle_status is ClaimLifecycleStatus.VALIDATED
    assert result.completion.support_status is ClaimSupportStatus.SUPPORTED
    assert len(result.links) == 1
    assert result.links[0].role is EvidenceRole.PRIMARY
    assert result.links[0].claim_id == CLAIM_ID
    assert result.links[0].evidence_id == EVIDENCE_ID


def test_missing_or_cross_run_evidence_is_unsupported() -> None:
    missing = _validator().validate(
        claim=_claim(),
        evidence=(),
        completed_at=NOW,
        real_research=True,
    )
    cross_run = _validator().validate(
        claim=_claim(),
        evidence=(_evidence(run_id=UUID(int=0)),),
        completed_at=NOW,
        real_research=True,
    )

    assert missing.completion.support_status is ClaimSupportStatus.UNSUPPORTED
    assert cross_run.completion.support_status is ClaimSupportStatus.UNSUPPORTED
    assert cross_run.links == ()


@pytest.mark.parametrize(
    "updates",
    (
        {"status": EvidenceStatus.INVALID},
        {"status": EvidenceStatus.FUTURE_DATA},
        {"synthetic_status": SyntheticStatus.SYNTHETIC_TEST_ONLY},
        {"synthetic_status": SyntheticStatus.UNKNOWN},
    ),
)
def test_invalid_future_or_synthetic_primary_is_rejected_for_real_run(
    updates: dict[str, object],
) -> None:
    result = _validator().validate(
        claim=_claim(),
        evidence=(_evidence(**updates),),
        completed_at=NOW,
        real_research=True,
    )

    assert result.completion.support_status is ClaimSupportStatus.UNSUPPORTED


def test_blocked_capability_can_only_explain_limitation() -> None:
    evidence = _evidence(
        EvidenceType.BLOCKED_CAPABILITY_EVIDENCE,
        status=EvidenceStatus.BLOCKED,
        payload={"capability_code": "DOCUMENT_BODY_UNAVAILABLE"},
    )
    limitation = _validator().validate(
        claim=_claim(
            ClaimType.LIMITATION,
            statement_code="DOCUMENT_BODY_UNAVAILABLE",
        ),
        evidence=(evidence,),
        completed_at=NOW,
        real_research=True,
    )
    company_fact = _validator().validate(
        claim=_claim(),
        evidence=(evidence,),
        completed_at=NOW,
        real_research=True,
    )

    assert limitation.completion.support_status is ClaimSupportStatus.BLOCKED
    assert company_fact.completion.support_status is ClaimSupportStatus.UNSUPPORTED


def test_metric_support_requires_exact_shape_formula_and_lineage() -> None:
    claim = _claim(ClaimType.FINANCIAL_METRIC)
    valid = _evidence(
        EvidenceType.DERIVED_METRIC_EVIDENCE,
        calculation_run_id=UUID("88888888-8888-4888-8888-888888888888"),
        calculation_input_ids=(UUID("99999999-9999-4999-8999-999999999999"),),
        formula_version="formula-v1",
        payload={
            "metric_code": "RETURN_ON_EQUITY",
            "value": "0.125",
            "unit": "RATIO",
            "period": "FY2025",
            "as_of_time": NOW.isoformat(),
            "metric_basis": "formula-v1",
        },
    )
    invalid = valid.model_copy(update={"formula_version": None})

    supported = _validator().validate(
        claim=claim,
        evidence=(valid,),
        completed_at=NOW,
        real_research=True,
    )
    partial = _validator().validate(
        claim=claim,
        evidence=(invalid,),
        completed_at=NOW,
        real_research=True,
    )

    assert supported.completion.support_status is ClaimSupportStatus.SUPPORTED
    assert partial.completion.support_status is ClaimSupportStatus.PARTIALLY_SUPPORTED


def test_document_claim_requires_valid_known_published_citation() -> None:
    claim = _claim(
        ClaimType.DOCUMENT_DISCLOSURE,
        statement_code="DISCLOSURE_AVAILABLE",
    )
    evidence = _evidence(
        EvidenceType.DOCUMENT_CITATION_EVIDENCE,
        citation_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        payload={"disclosure_code": "DISCLOSURE_AVAILABLE"},
    )
    unknown = evidence.model_copy(update={"published_at": None})

    supported = _validator().validate(
        claim=claim,
        evidence=(evidence,),
        completed_at=NOW,
        real_research=True,
    )
    blocked = _validator().validate(
        claim=claim,
        evidence=(unknown,),
        completed_at=NOW,
        real_research=True,
    )

    assert supported.completion.support_status is ClaimSupportStatus.SUPPORTED
    assert blocked.completion.support_status is ClaimSupportStatus.BLOCKED


def test_conflicting_evidence_status_forces_conflicting_claim() -> None:
    result = _validator().validate(
        claim=_claim(),
        evidence=(_evidence(status=EvidenceStatus.CONFLICTING),),
        completed_at=NOW,
        real_research=True,
    )

    assert result.completion.support_status is ClaimSupportStatus.CONFLICTING
