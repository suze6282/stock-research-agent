from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.retention import (
    EvidenceRetentionPlanRequest,
    EvidenceRetentionRegistry,
)

NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def _request(**updates: object) -> EvidenceRetentionPlanRequest:
    values: dict[str, object] = {
        "action_type": "DELETE_RESTRICTED_ARTIFACT",
        "artifact_ids": (UUID(int=1),),
        "affected_lineage_ids": (UUID(int=2), UUID(int=3)),
        "reason_code": "LICENSE_RETENTION_EXPIRED",
        "deadline_at": NOW + timedelta(days=7),
        "created_at": NOW,
    }
    values.update(updates)
    return EvidenceRetentionPlanRequest.model_validate(values)


def test_retention_plan_is_deterministic_and_contains_no_artifact_bytes() -> None:
    registry = EvidenceRetentionRegistry(id_factory=lambda: UUID(int=4))
    first = registry.plan(_request())
    second = registry.plan(_request())

    assert first.plan_checksum == second.plan_checksum
    assert first.status == "PLANNED"
    assert "bytes" not in first.model_dump()


def test_retention_plan_rejects_invalid_deadline_or_scope() -> None:
    registry = EvidenceRetentionRegistry()
    with pytest.raises(LiveEvidenceValidationError) as deadline:
        registry.plan(_request(deadline_at=NOW))
    assert deadline.value.code == "RETENTION_DEADLINE_INVALID"

    with pytest.raises(LiveEvidenceValidationError) as scope:
        registry.plan(_request(artifact_ids=(UUID(int=0),)))
    assert scope.value.code == "RETENTION_SCOPE_INVALID"
