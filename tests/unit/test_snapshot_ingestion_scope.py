from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.snapshot import (
    SnapshotFromIngestionPlanRequest,
    SnapshotManifestReference,
    SnapshotScopeEvidence,
    validate_security_scope,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
SECURITY_ID = UUID("00000000-0000-0000-0000-000000000001")
ISSUER_ID = UUID("00000000-0000-0000-0000-000000000002")


def _plan(scope: tuple[SnapshotScopeEvidence, ...]) -> SnapshotFromIngestionPlanRequest:
    return SnapshotFromIngestionPlanRequest(
        security_id=SECURITY_ID,
        issuer_id=ISSUER_ID,
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
        scope_evidence=scope,
        planner_version="1.0.0",
    )


def _scope(**changes: object) -> SnapshotScopeEvidence:
    values: dict[str, object] = {
        "evidence_id": UUID("00000000-0000-0000-0000-000000000004"),
        "evidence_kind": "DOCUMENT",
        "security_id": SECURITY_ID,
        "issuer_id": ISSUER_ID,
    }
    values.update(changes)
    return SnapshotScopeEvidence.model_validate(values)


def test_all_evidence_must_match_explicit_security_and_issuer() -> None:
    decision = validate_security_scope(_plan((_scope(),)))

    assert decision.status == "PASS"
    assert decision.warning_codes == ()


@pytest.mark.parametrize("kind", ["MANIFEST", "ARTIFACT", "DOCUMENT", "FINANCIAL_FACT"])
def test_other_security_is_rejected_for_every_evidence_kind(kind: str) -> None:
    decision = validate_security_scope(
        _plan((_scope(evidence_kind=kind, security_id=UUID(int=99)),))
    )

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == ("SNAPSHOT_SECURITY_MISMATCH",)


def test_other_issuer_is_rejected() -> None:
    decision = validate_security_scope(_plan((_scope(issuer_id=UUID(int=98)),)))

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == ("SNAPSHOT_ISSUER_MISMATCH",)
