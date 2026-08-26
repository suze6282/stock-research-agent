from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.enums import EvidenceSourceType
from stock_research_agent.domain.live_evidence.snapshot import (
    SnapshotFromIngestionPlanRequest,
    SnapshotManifestReference,
    SnapshotSyntheticEvidence,
    validate_synthetic_scope,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _plan(
    evidence: SnapshotSyntheticEvidence,
    *,
    execution_mode: str = "REAL_COMPANY",
) -> SnapshotFromIngestionPlanRequest:
    return SnapshotFromIngestionPlanRequest(
        security_id=UUID("00000000-0000-0000-0000-000000000001"),
        issuer_id=UUID("00000000-0000-0000-0000-000000000002"),
        research_as_of_time=NOW,
        manifests=(
            SnapshotManifestReference(
                manifest_id=UUID("00000000-0000-0000-0000-000000000003"),
                manifest_checksum="a" * 64,
                approved=True,
                license_allowed=True,
            ),
        ),
        document_version_ids=(),
        financial_fact_ids=(),
        mapping_version_ids=(),
        formula_version_ids=(),
        required_input_kinds=("DOCUMENT",),
        available_input_kinds=("DOCUMENT",),
        synthetic_evidence=(evidence,),
        execution_mode=execution_mode,
        planner_version="1.0.0",
    )


def _evidence(**changes: object) -> SnapshotSyntheticEvidence:
    values: dict[str, object] = {
        "evidence_id": UUID("00000000-0000-0000-0000-000000000004"),
        "source_type": EvidenceSourceType.SYNTHETIC_TEST,
        "synthetic_status": ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
        "company_evidence_status": "NOT_COMPANY_EVIDENCE",
        "security_is_neutral_synthetic": True,
        "offline": True,
        "not_live": True,
    }
    values.update(changes)
    return SnapshotSyntheticEvidence.model_validate(values)


def test_real_company_plan_rejects_synthetic_test_evidence() -> None:
    decision = validate_synthetic_scope(_plan(_evidence()))

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == ("SYNTHETIC_COMPANY_EVIDENCE_FORBIDDEN",)


def test_real_company_plan_rejects_offline_fixture_evidence() -> None:
    evidence = _evidence(
        source_type=EvidenceSourceType.OFFLINE_FIXTURE,
        synthetic_status=ProviderSyntheticStatus.FIXTURE_REAL_EXCERPT,
    )
    decision = validate_synthetic_scope(_plan(evidence))

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == ("FIXTURE_COMPANY_EVIDENCE_FORBIDDEN",)


def test_neutral_synthetic_security_is_allowed_only_in_test_only_plan() -> None:
    decision = validate_synthetic_scope(_plan(_evidence(), execution_mode="TEST_ONLY"))

    assert decision.status == "PASS"
    assert decision.warning_codes == ()


@pytest.mark.parametrize(
    "changes",
    [
        {"security_is_neutral_synthetic": False},
        {"company_evidence_status": "REAL_COMPANY_EVIDENCE"},
        {"offline": False},
        {"not_live": False},
    ],
)
def test_test_only_plan_requires_all_synthetic_isolation_markers(
    changes: dict[str, object],
) -> None:
    decision = validate_synthetic_scope(_plan(_evidence(**changes), execution_mode="TEST_ONLY"))

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == ("SYNTHETIC_COMPANY_EVIDENCE_FORBIDDEN",)
