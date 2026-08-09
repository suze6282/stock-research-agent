from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from importlib import import_module
from uuid import UUID

import pytest

from stock_research_agent.domain.reports.bindings import (
    ReportClaimBindingRole,
    ReportClaimBindingWrite,
    ReportEvidenceBindingWrite,
    VisibleReferenceKind,
)
from stock_research_agent.domain.reports.blocks import validate_report_block
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
)
from stock_research_agent.domain.reports.schemas import ReportInputManifest
from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    ClaimType,
    EvidenceRole,
    EvidenceStatus,
    EvidenceType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchClaimRecord,
    ResearchEvidenceRecord,
)

NOW = datetime(2026, 7, 27, 8, tzinfo=UTC)
RUN_ID = UUID(int=10)
SECURITY_ID = UUID(int=11)
SNAPSHOT_ID = UUID(int=12)
CLAIM_IDS = tuple(UUID(int=value) for value in range(101, 105))
EVIDENCE_IDS = (UUID(int=201), UUID(int=202))
LINK_IDS = (UUID(int=301), UUID(int=302))


def _module() -> object:
    return import_module("stock_research_agent.domain.reports.appendices")


def _claim(
    claim_id: UUID,
    support: ClaimSupportStatus,
    code: str,
    *,
    numeric: bool = False,
) -> ResearchClaimRecord:
    values: dict[str, object] = {
        "id": claim_id,
        "run_id": RUN_ID,
        "claim_type": ClaimType.FINANCIAL_METRIC if numeric else ClaimType.LIMITATION,
        "lifecycle_status": ClaimLifecycleStatus.VALIDATED,
        "support_status": support,
        "statement_code": code,
        "builder_version": "deterministic-claim-builder-v1",
        "validator_version": "claim-support-validator-v1",
        "created_at": NOW,
        "completed_at": NOW,
    }
    if numeric:
        values.update(
            value=Decimal("12.50"),
            unit="PERCENT",
            currency_code=None,
            period="FY2025",
            as_of_time=NOW,
            metric_basis="CANONICAL_V1",
        )
    return ResearchClaimRecord.model_validate(values)


def _evidence(
    evidence_id: UUID,
    *,
    metric: bool,
) -> ResearchEvidenceRecord:
    return ResearchEvidenceRecord(
        id=evidence_id,
        run_id=RUN_ID,
        observation_id=UUID(int=400 + evidence_id.int),
        evidence_type=(
            EvidenceType.DERIVED_METRIC_EVIDENCE
            if metric
            else EvidenceType.STRUCTURED_FACT_EVIDENCE
        ),
        status=EvidenceStatus.VALID,
        schema_version="1.0.0",
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        source_record_type="derived_metric" if metric else "normalized_fact",
        source_record_id=UUID(int=500 + evidence_id.int),
        source_checksum=("b" if metric else "a") * 64,
        published_at=NOW,
        calculation_run_id=UUID(int=701) if metric else None,
        calculation_input_ids=(UUID(int=702), UUID(int=703)) if metric else (),
        formula_version="roe-v1" if metric else None,
        synthetic_status=SyntheticStatus.REAL_VERIFIED,
        payload={"path": "must-not-leak", "raw_value": "must-not-leak"},
        created_at=NOW,
    )


def _claim_binding(claim_id: UUID, index: int) -> ReportClaimBindingWrite:
    return ReportClaimBindingWrite(
        id=UUID(int=800 + index),
        report_block_id=UUID(int=900 + index),
        claim_id=claim_id,
        role=(
            ReportClaimBindingRole.CONTRADICTING
            if index == 3
            else ReportClaimBindingRole.LIMITATION
            if index == 2
            else ReportClaimBindingRole.PRIMARY
        ),
        item_or_row_key=f"row.{index}",
        created_at=NOW,
    )


def _evidence_binding(
    claim_binding: ReportClaimBindingWrite,
    evidence: ResearchEvidenceRecord,
    index: int,
    reference: str,
) -> ReportEvidenceBindingWrite:
    return ReportEvidenceBindingWrite(
        id=UUID(int=1000 + index),
        report_block_id=claim_binding.report_block_id,
        report_claim_binding_id=claim_binding.id,
        claim_evidence_link_id=LINK_IDS[index],
        evidence_id=evidence.id,
        role=EvidenceRole.PRIMARY,
        visible_reference_kind=(
            VisibleReferenceKind.METRIC
            if reference.startswith("MET-")
            else VisibleReferenceKind.EVIDENCE
        ),
        visible_reference=reference,
        item_or_row_key=f"row.{index}",
        source_record_id=evidence.source_record_id,
        source_checksum=evidence.source_checksum,
        created_at=NOW,
    )


def _manifest() -> ReportInputManifest:
    return ReportInputManifest.model_construct(
        research_agent_run_id=RUN_ID,
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        claim_ids=CLAIM_IDS,
        evidence_ids=EVIDENCE_IDS,
        link_ids=LINK_IDS,
    )


def _views() -> tuple[object, ...]:
    module = _module()
    fact_claim = _claim(
        CLAIM_IDS[0],
        ClaimSupportStatus.SUPPORTED,
        "REVENUE_GROWTH",
        numeric=True,
    )
    metric_claim = _claim(
        CLAIM_IDS[1],
        ClaimSupportStatus.PARTIALLY_SUPPORTED,
        "RETURN_ON_EQUITY",
        numeric=True,
    )
    limitation_claim = _claim(
        CLAIM_IDS[2],
        ClaimSupportStatus.BLOCKED,
        "FINANCIAL_DATA_UNAVAILABLE",
    )
    conflict_claim = _claim(
        CLAIM_IDS[3],
        ClaimSupportStatus.CONFLICTING,
        "PROVIDER_VALUES_CONFLICT",
    )
    fact_evidence = _evidence(EVIDENCE_IDS[0], metric=False)
    metric_evidence = _evidence(EVIDENCE_IDS[1], metric=True)
    fact_binding = _claim_binding(fact_claim.id, 0)
    metric_binding = _claim_binding(metric_claim.id, 1)
    return (
        module.EvidenceAppendixBindingView(
            visible_reference="CON-001",
            claim=conflict_claim,
            claim_binding=_claim_binding(conflict_claim.id, 3),
        ),
        module.EvidenceAppendixBindingView(
            visible_reference="MET-001",
            claim=metric_claim,
            claim_binding=metric_binding,
            evidence=metric_evidence,
            evidence_binding=_evidence_binding(
                metric_binding,
                metric_evidence,
                1,
                "MET-001",
            ),
        ),
        module.EvidenceAppendixBindingView(
            visible_reference="LIM-001",
            claim=limitation_claim,
            claim_binding=_claim_binding(limitation_claim.id, 2),
        ),
        module.EvidenceAppendixBindingView(
            visible_reference="EV-001",
            claim=fact_claim,
            claim_binding=fact_binding,
            evidence=fact_evidence,
            evidence_binding=_evidence_binding(
                fact_binding,
                fact_evidence,
                0,
                "EV-001",
            ),
        ),
    )


def test_evidence_appendix_projects_only_safe_exact_bound_fields() -> None:
    module = _module()

    block = module.build_evidence_appendix(_manifest(), _views())

    assert block.block_key == "appendix.evidence"
    assert block.block_type is ReportBlockType.EVIDENCE_TABLE
    assert block.status is ReportBlockStatus.PARTIAL
    rows = block.payload["rows"]
    assert [row["reference"] for row in rows] == [
        "EV-001",
        "MET-001",
        "LIM-001",
        "CON-001",
    ]
    assert rows[0] == {
        "reference": "EV-001",
        "claim_id": str(CLAIM_IDS[0]),
        "evidence_id": str(EVIDENCE_IDS[0]),
        "statement_code": "REVENUE_GROWTH",
        "value": "12.50",
        "unit": "PERCENT",
        "currency_code": None,
        "period": "FY2025",
        "as_of_time": "2026-07-27T08:00:00Z",
        "source_record_type": "normalized_fact",
        "source_record_id": str(UUID(int=701)),
        "source_checksum": "a" * 64,
        "calculation_run_id": None,
        "calculation_input_ids": [],
        "formula_version": None,
        "support_status": "SUPPORTED",
        "evidence_status": "VALID",
    }
    assert rows[1]["calculation_run_id"] == str(UUID(int=701))
    assert rows[1]["calculation_input_ids"] == [
        str(UUID(int=702)),
        str(UUID(int=703)),
    ]
    assert rows[1]["formula_version"] == "roe-v1"
    assert rows[2]["evidence_id"] is None
    assert rows[2]["support_status"] == "BLOCKED"
    assert rows[3]["support_status"] == "CONFLICTING"
    assert "payload" not in str(block.payload).casefold()
    assert "must-not-leak" not in str(block.payload)
    assert "path" not in str(block.payload).casefold()
    validate_report_block(block)


def test_evidence_appendix_rejects_unsealed_or_mismatched_binding() -> None:
    module = _module()
    view = _views()[1]

    for manifest, broken_view, code in (
        (
            _manifest().model_copy(update={"evidence_ids": ()}),
            view,
            "EVIDENCE_APPENDIX_EVIDENCE_NOT_IN_MANIFEST",
        ),
        (
            _manifest(),
            view.model_copy(update={"visible_reference": "EV-999"}),
            "EVIDENCE_APPENDIX_REFERENCE_MISMATCH",
        ),
    ):
        with pytest.raises(module.ReportAppendixError) as raised:
            module.build_evidence_appendix(manifest, (broken_view,))
        assert raised.value.code == code
