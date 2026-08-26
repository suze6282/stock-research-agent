from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.snapshot import (
    SnapshotFromIngestionPlanRequest,
    SnapshotManifestReference,
    SnapshotPlanRegistry,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _manifest(**changes: object) -> SnapshotManifestReference:
    values: dict[str, object] = {
        "manifest_id": UUID("00000000-0000-0000-0000-000000000001"),
        "manifest_checksum": "a" * 64,
        "approved": True,
        "license_allowed": True,
    }
    values.update(changes)
    return SnapshotManifestReference.model_validate(values)


def _request(**changes: object) -> SnapshotFromIngestionPlanRequest:
    values: dict[str, object] = {
        "security_id": UUID("00000000-0000-0000-0000-000000000002"),
        "issuer_id": UUID("00000000-0000-0000-0000-000000000003"),
        "research_as_of_time": NOW,
        "manifests": (_manifest(),),
        "document_version_ids": (UUID("00000000-0000-0000-0000-000000000004"),),
        "financial_fact_ids": (UUID("00000000-0000-0000-0000-000000000005"),),
        "mapping_version_ids": (UUID("00000000-0000-0000-0000-000000000006"),),
        "formula_version_ids": (UUID("00000000-0000-0000-0000-000000000007"),),
        "required_input_kinds": ("DOCUMENT", "FINANCIAL_FACT"),
        "available_input_kinds": ("DOCUMENT", "FINANCIAL_FACT"),
        "planner_version": "1.0.0",
    }
    values.update(changes)
    return SnapshotFromIngestionPlanRequest.model_validate(values)


def _registry() -> SnapshotPlanRegistry:
    return SnapshotPlanRegistry(
        registry_id="SNAPSHOT_PLAN_REGISTRY",
        registry_version="1.0.0",
        registry_checksum="f" * 64,
    )


def test_complete_explicit_inputs_produce_stable_ready_plan() -> None:
    first = _registry().plan(_request())
    second = _registry().plan(_request())

    assert first.status == "READY"
    assert first.warning_codes == ()
    assert first.plan_checksum == second.plan_checksum
    assert first.registry_signature == second.registry_signature


def test_missing_required_input_produces_partial_plan() -> None:
    result = _registry().plan(_request(available_input_kinds=("DOCUMENT",), financial_fact_ids=()))

    assert result.status == "PARTIAL"
    assert result.warning_codes == ("SNAPSHOT_INPUT_INCOMPLETE",)


def test_no_usable_input_is_blocked() -> None:
    result = _registry().plan(
        _request(
            available_input_kinds=(),
            document_version_ids=(),
            financial_fact_ids=(),
        )
    )

    assert result.status == "BLOCKED"
    assert result.warning_codes == ("SNAPSHOT_INPUT_INCOMPLETE",)


@pytest.mark.parametrize(
    ("manifest", "expected_code"),
    [
        (_manifest(approved=False), "SNAPSHOT_MANIFEST_NOT_APPROVED"),
        (_manifest(license_allowed=False), "SNAPSHOT_LICENSE_BLOCKED"),
    ],
)
def test_manifest_approval_and_license_are_hard_gates(
    manifest: SnapshotManifestReference,
    expected_code: str,
) -> None:
    result = _registry().plan(_request(manifests=(manifest,)))

    assert result.status == "BLOCKED"
    assert result.warning_codes == (expected_code,)
