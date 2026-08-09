from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.reports.schemas import ReportInputManifest
from stock_research_agent.domain.research_agent.enums import (
    EvidenceRole,
    EvidenceStatus,
    EvidenceType,
    ResearchMode,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ClaimEvidenceLinkRecord,
    ResearchEvidenceRecord,
)

NOW = datetime(2026, 7, 27, 8, tzinfo=UTC)
RUN_ID = UUID("10000000-0000-0000-0000-000000000001")
SECURITY_ID = UUID("10000000-0000-0000-0000-000000000002")
SNAPSHOT_ID = UUID("10000000-0000-0000-0000-000000000003")
CLAIM_ID = UUID("20000000-0000-0000-0000-000000000001")
CLAIM_BINDING_ID = UUID("30000000-0000-0000-0000-000000000001")
BLOCK_ID = UUID("30000000-0000-0000-0000-000000000002")
EVIDENCE_ID = UUID("40000000-0000-0000-0000-000000000001")
LINK_ID = UUID("50000000-0000-0000-0000-000000000001")


def _module() -> object:
    return import_module("stock_research_agent.domain.reports.bindings")


def _claim_binding(**updates: object) -> object:
    module = _module()
    values: dict[str, object] = {
        "id": CLAIM_BINDING_ID,
        "report_block_id": BLOCK_ID,
        "claim_id": CLAIM_ID,
        "role": module.ReportClaimBindingRole.PRIMARY,
        "sentence_index": None,
        "item_or_row_key": "roe.fy2025",
        "created_at": NOW,
    }
    values.update(updates)
    return module.ReportClaimBindingWrite.model_validate(values)


def _link(**updates: object) -> ClaimEvidenceLinkRecord:
    values: dict[str, object] = {
        "id": LINK_ID,
        "run_id": RUN_ID,
        "claim_id": CLAIM_ID,
        "evidence_id": EVIDENCE_ID,
        "role": EvidenceRole.PRIMARY,
        "created_at": NOW,
    }
    values.update(updates)
    return ClaimEvidenceLinkRecord.model_validate(values)


def _evidence(**updates: object) -> ResearchEvidenceRecord:
    values: dict[str, object] = {
        "id": EVIDENCE_ID,
        "run_id": RUN_ID,
        "observation_id": UUID("60000000-0000-0000-0000-000000000001"),
        "evidence_type": EvidenceType.DERIVED_METRIC_EVIDENCE,
        "status": EvidenceStatus.VALID,
        "schema_version": "evidence-v1",
        "security_id": SECURITY_ID,
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": NOW,
        "source_record_type": "derived_metric",
        "source_record_id": UUID("60000000-0000-0000-0000-000000000002"),
        "source_checksum": "a" * 64,
        "published_at": NOW - timedelta(days=1),
        "calculation_run_id": UUID("60000000-0000-0000-0000-000000000003"),
        "calculation_input_ids": (UUID("60000000-0000-0000-0000-000000000004"),),
        "formula_version": "roe-v1",
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
        "payload": {"metric_code": "ROE", "value": "0.125"},
        "warning_codes": (),
        "created_at": NOW,
    }
    values.update(updates)
    return ResearchEvidenceRecord.model_validate(values)


def _manifest(**updates: object) -> ReportInputManifest:
    values: dict[str, object] = {
        "research_agent_run_id": RUN_ID,
        "security_id": SECURITY_ID,
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": NOW,
        "link_ids": (LINK_ID,),
        "evidence_ids": (EVIDENCE_ID,),
        "research_mode": ResearchMode.REAL_RESEARCH,
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
    }
    values.update(updates)
    return ReportInputManifest.model_construct(**values)


def _binding(**updates: object) -> object:
    module = _module()
    values: dict[str, object] = {
        "id": UUID("70000000-0000-0000-0000-000000000001"),
        "report_block_id": BLOCK_ID,
        "report_claim_binding_id": CLAIM_BINDING_ID,
        "claim_evidence_link_id": LINK_ID,
        "evidence_id": EVIDENCE_ID,
        "role": EvidenceRole.PRIMARY,
        "visible_reference_kind": module.VisibleReferenceKind.METRIC,
        "visible_reference": "MET-001",
        "item_or_row_key": "roe.fy2025",
        "source_record_id": UUID("60000000-0000-0000-0000-000000000002"),
        "source_checksum": "a" * 64,
        "created_at": NOW,
    }
    values.update(updates)
    return module.ReportEvidenceBindingWrite.model_validate(values)


def test_exact_stage7_link_backed_evidence_binding_passes() -> None:
    module = _module()
    binding = _binding()

    assert (
        module.validate_evidence_binding(
            _claim_binding(),
            _link(),
            _evidence(),
            binding,
            _manifest(),
        )
        is None
    )
    with pytest.raises(ValidationError, match="Instance is frozen"):
        binding.evidence_id = UUID("ffffffff-0000-0000-0000-000000000001")


@pytest.mark.parametrize(
    ("link_updates", "binding_updates", "expected_code"),
    [
        (
            {"claim_id": UUID("ffffffff-0000-0000-0000-000000000001")},
            {},
            "CLAIM_EVIDENCE_LINK_CLAIM_MISMATCH",
        ),
        (
            {"evidence_id": UUID("ffffffff-0000-0000-0000-000000000001")},
            {},
            "CLAIM_EVIDENCE_LINK_EVIDENCE_MISMATCH",
        ),
        (
            {},
            {"claim_evidence_link_id": UUID("ffffffff-0000-0000-0000-000000000001")},
            "EVIDENCE_BINDING_LINK_ID_MISMATCH",
        ),
        (
            {},
            {"item_or_row_key": "roe.fy2024"},
            "EVIDENCE_BINDING_LOCATION_MISMATCH",
        ),
    ],
)
def test_invented_or_cross_chain_evidence_binding_is_rejected(
    link_updates: dict[str, object],
    binding_updates: dict[str, object],
    expected_code: str,
) -> None:
    module = _module()
    with pytest.raises(module.ReportBindingError) as raised:
        module.validate_evidence_binding(
            _claim_binding(),
            _link(**link_updates),
            _evidence(),
            _binding(**binding_updates),
            _manifest(),
        )
    assert raised.value.code == expected_code


@pytest.mark.parametrize(
    ("evidence_updates", "manifest_updates", "expected_code"),
    [
        (
            {"run_id": UUID("ffffffff-0000-0000-0000-000000000001")},
            {},
            "EVIDENCE_RUN_MISMATCH",
        ),
        (
            {"security_id": UUID("ffffffff-0000-0000-0000-000000000001")},
            {},
            "EVIDENCE_SECURITY_MISMATCH",
        ),
        (
            {"snapshot_id": UUID("ffffffff-0000-0000-0000-000000000001")},
            {},
            "EVIDENCE_SNAPSHOT_MISMATCH",
        ),
        (
            {"research_as_of_time": NOW - timedelta(seconds=1)},
            {},
            "EVIDENCE_AS_OF_MISMATCH",
        ),
        (
            {"published_at": NOW + timedelta(seconds=1)},
            {},
            "FUTURE_REPORT_EVIDENCE",
        ),
        (
            {"source_checksum": None},
            {},
            "PRIMARY_EVIDENCE_CHECKSUM_REQUIRED",
        ),
        (
            {},
            {"evidence_ids": ()},
            "EVIDENCE_NOT_IN_REPORT_MANIFEST",
        ),
        (
            {},
            {"link_ids": ()},
            "LINK_NOT_IN_REPORT_MANIFEST",
        ),
    ],
)
def test_evidence_must_match_sealed_report_context(
    evidence_updates: dict[str, object],
    manifest_updates: dict[str, object],
    expected_code: str,
) -> None:
    module = _module()
    with pytest.raises(module.ReportBindingError) as raised:
        module.validate_evidence_binding(
            _claim_binding(),
            _link(),
            _evidence(**evidence_updates),
            _binding(),
            _manifest(**manifest_updates),
        )
    assert raised.value.code == expected_code


@pytest.mark.parametrize(
    "status",
    [
        EvidenceStatus.INVALID,
        EvidenceStatus.FUTURE_DATA,
        EvidenceStatus.SOURCE_MISSING,
        EvidenceStatus.BLOCKED,
    ],
)
def test_primary_factual_evidence_must_be_valid(status: EvidenceStatus) -> None:
    module = _module()
    with pytest.raises(module.ReportBindingError) as raised:
        module.validate_evidence_binding(
            _claim_binding(),
            _link(),
            _evidence(status=status),
            _binding(),
            _manifest(),
        )
    assert raised.value.code == "PRIMARY_EVIDENCE_NOT_VALID"


def test_real_report_rejects_synthetic_or_unknown_evidence() -> None:
    module = _module()
    for status in (
        SyntheticStatus.SYNTHETIC_TEST_ONLY,
        SyntheticStatus.UNKNOWN,
    ):
        with pytest.raises(module.ReportBindingError) as raised:
            module.validate_evidence_binding(
                _claim_binding(),
                _link(),
                _evidence(synthetic_status=status),
                _binding(),
                _manifest(),
            )
        assert raised.value.code == "REAL_REPORT_SYNTHETIC_EVIDENCE_FORBIDDEN"


def test_evidence_binding_set_rejects_duplicate_link_or_visible_reference() -> None:
    module = _module()
    duplicate_link = _binding(
        id=UUID("70000000-0000-0000-0000-000000000002"),
        visible_reference="MET-002",
    )
    with pytest.raises(module.ReportBindingError) as raised:
        module.validate_evidence_binding_set((_binding(), duplicate_link))
    assert raised.value.code == "DUPLICATE_EVIDENCE_LINK_BINDING"

    duplicate_reference = _binding(
        id=UUID("70000000-0000-0000-0000-000000000003"),
        claim_evidence_link_id=UUID("50000000-0000-0000-0000-000000000002"),
    )
    with pytest.raises(module.ReportBindingError) as raised:
        module.validate_evidence_binding_set((_binding(), duplicate_reference))
    assert raised.value.code == "DUPLICATE_VISIBLE_EVIDENCE_REFERENCE"
