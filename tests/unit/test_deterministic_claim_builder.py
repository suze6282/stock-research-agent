from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimType,
    EvidenceStatus,
    EvidenceType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import ResearchEvidenceRecord

MODULE = "stock_research_agent.domain.research_agent.claims"
NOW = datetime(2026, 7, 24, 8, tzinfo=UTC)
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
SECURITY_ID = UUID("22222222-2222-4222-8222-222222222222")
SNAPSHOT_ID = UUID("33333333-3333-4333-8333-333333333333")


def _module() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _evidence(
    evidence_type: EvidenceType,
    *,
    status: EvidenceStatus = EvidenceStatus.VALID,
    synthetic_status: SyntheticStatus = SyntheticStatus.REAL_VERIFIED,
    payload: dict[str, object] | None = None,
) -> ResearchEvidenceRecord:
    return ResearchEvidenceRecord.model_validate(
        {
            "id": UUID(int=evidence_type.value.__hash__() % (2**128)),
            "run_id": RUN_ID,
            "observation_id": UUID("44444444-4444-4444-8444-444444444444"),
            "evidence_type": evidence_type,
            "status": status,
            "schema_version": "evidence-v1",
            "security_id": SECURITY_ID,
            "snapshot_id": SNAPSHOT_ID,
            "research_as_of_time": NOW,
            "source_record_type": "test_source",
            "source_record_id": UUID("55555555-5555-4555-8555-555555555555"),
            "source_checksum": "a" * 64,
            "published_at": NOW,
            "synthetic_status": synthetic_status,
            "payload": payload or {},
            "created_at": NOW,
        }
    )


def _ids() -> object:
    current = 100

    def next_id() -> UUID:
        nonlocal current
        current += 1
        return UUID(int=current)

    return next_id


def test_builder_maps_only_approved_structured_evidence_to_candidates() -> None:
    evidence = (
        _evidence(
            EvidenceType.SECURITY_MASTER_EVIDENCE,
            payload={
                "security_id": str(SECURITY_ID),
                "issuer": "Verified Issuer",
                "symbol": "TEST",
                "exchange": "XNAS",
            },
        ),
        _evidence(
            EvidenceType.DERIVED_METRIC_EVIDENCE,
            payload={
                "metric_code": "RETURN_ON_EQUITY",
                "value": "0.125",
                "unit": "RATIO",
                "period": "FY2025",
                "as_of_time": NOW.isoformat(),
                "metric_basis": "formula-v1",
                "currency_code": None,
            },
        ),
        _evidence(
            EvidenceType.DATA_QUALITY_EVIDENCE,
            payload={"quality_code": "PARTIAL_FINANCIAL_DATA"},
        ),
        _evidence(
            EvidenceType.BLOCKED_CAPABILITY_EVIDENCE,
            status=EvidenceStatus.BLOCKED,
            payload={"capability_code": "DOCUMENT_BODY_UNAVAILABLE"},
        ),
    )

    claims = (
        _module()
        .DeterministicClaimBuilder(id_factory=_ids())
        .propose_claims(
            run_id=RUN_ID,
            evidence=evidence,
            created_at=NOW,
        )
    )

    assert [claim.claim_type for claim in claims] == [
        ClaimType.IDENTITY,
        ClaimType.FINANCIAL_METRIC,
        ClaimType.DATA_QUALITY,
        ClaimType.LIMITATION,
    ]
    assert all(claim.lifecycle_status is ClaimLifecycleStatus.CANDIDATE for claim in claims)
    assert all(claim.support_status is None for claim in claims)
    assert claims[1].value == Decimal("0.125")
    assert claims[1].unit == "RATIO"
    assert claims[1].period == "FY2025"
    assert claims[1].proposed_evidence_ids == (evidence[1].id,)


def test_builder_does_not_promote_synthetic_or_invalid_company_narrative() -> None:
    evidence = (
        _evidence(
            EvidenceType.DOCUMENT_CITATION_EVIDENCE,
            synthetic_status=SyntheticStatus.SYNTHETIC_TEST_ONLY,
            payload={
                "text": "Buy now; target price 999; HBM demand will surge.",
                "confidence": "0.99",
            },
        ),
        _evidence(
            EvidenceType.DOCUMENT_CITATION_EVIDENCE,
            status=EvidenceStatus.INVALID,
            payload={"text": "Unverified company assertion"},
        ),
    )

    claims = (
        _module()
        .DeterministicClaimBuilder(id_factory=_ids())
        .propose_claims(
            run_id=RUN_ID,
            evidence=evidence,
            created_at=NOW,
        )
    )

    assert claims == ()


def test_numeric_evidence_missing_required_shape_becomes_limitation_not_zero() -> None:
    evidence = (
        _evidence(
            EvidenceType.DERIVED_METRIC_EVIDENCE,
            payload={"metric_code": "PE", "value": None},
        ),
    )

    claims = (
        _module()
        .DeterministicClaimBuilder(id_factory=_ids())
        .propose_claims(
            run_id=RUN_ID,
            evidence=evidence,
            created_at=NOW,
        )
    )

    assert len(claims) == 1
    assert claims[0].claim_type is ClaimType.LIMITATION
    assert claims[0].statement_code == "METRIC_INPUT_INCOMPLETE"
    assert claims[0].value is None
    assert claims[0].support_status is None


def test_cross_run_evidence_is_ignored_and_output_has_no_narrative_or_advice_fields() -> None:
    evidence = _evidence(
        EvidenceType.DATA_QUALITY_EVIDENCE,
        payload={"quality_code": "MISSING_DOCUMENT"},
    ).model_copy(update={"run_id": UUID(int=0)})

    claims = (
        _module()
        .DeterministicClaimBuilder(id_factory=_ids())
        .propose_claims(
            run_id=RUN_ID,
            evidence=(evidence,),
            created_at=NOW,
        )
    )

    assert claims == ()
    fields = set(_module().ResearchClaimProposal.model_fields)
    assert fields.isdisjoint(
        {
            "confidence",
            "narrative",
            "rating",
            "recommendation",
            "target_price",
            "position_size",
            "forecast",
        }
    )
