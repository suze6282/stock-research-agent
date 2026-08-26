from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.snapshot import (
    SnapshotFromIngestionPlanRequest,
    SnapshotManifestReference,
    SnapshotTemporalEvidence,
    validate_temporal_scope,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _plan(evidence: SnapshotTemporalEvidence) -> SnapshotFromIngestionPlanRequest:
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
        temporal_evidence=(evidence,),
        strict_publication=True,
        planner_version="1.0.0",
    )


def _evidence(**changes: object) -> SnapshotTemporalEvidence:
    values: dict[str, object] = {
        "evidence_id": UUID("00000000-0000-0000-0000-000000000004"),
        "scope_as_of_time": NOW,
        "published_at": NOW,
        "filed_at": NOW,
        "fact_available_at": NOW,
        "imported_at": NOW,
        "requires_publication_time": True,
    }
    values.update(changes)
    return SnapshotTemporalEvidence.model_validate(values)


@pytest.mark.parametrize(
    "changes",
    [
        {"published_at": NOW + timedelta(seconds=1)},
        {"filed_at": NOW + timedelta(seconds=1)},
        {"fact_available_at": NOW + timedelta(seconds=1)},
    ],
)
def test_any_future_business_time_is_rejected(changes: dict[str, object]) -> None:
    decision = validate_temporal_scope(_plan(_evidence(**changes)))

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == ("FUTURE_DATA",)


def test_import_time_never_substitutes_for_unknown_publication_time() -> None:
    evidence = _evidence(published_at=None, imported_at=NOW - timedelta(days=30))
    decision = validate_temporal_scope(_plan(evidence))

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == ("SOURCE_PUBLISHED_AT_UNKNOWN_STRICT",)


def test_per_evidence_as_of_must_equal_frozen_plan_as_of() -> None:
    evidence = _evidence(scope_as_of_time=NOW - timedelta(seconds=1))
    decision = validate_temporal_scope(_plan(evidence))

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == ("AS_OF_MISMATCH",)


def test_exact_cutoff_is_allowed() -> None:
    decision = validate_temporal_scope(_plan(_evidence()))

    assert decision.status == "PASS"
    assert decision.warning_codes == ()
