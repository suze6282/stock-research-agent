from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.retention import (
    EvidenceRetentionActionRecord,
    EvidenceRetentionPlanRequest,
    EvidenceRetentionRegistry,
)

NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


class _SyntheticStorage:
    def __init__(self, *, verify_failure: bool = False) -> None:
        self.present = {UUID(int=1)}
        self.verify_failure = verify_failure

    def delete(self, artifact_id: UUID) -> None:
        self.present.discard(artifact_id)

    def exists(self, artifact_id: UUID) -> bool:
        return self.verify_failure or artifact_id in self.present


def _action() -> EvidenceRetentionActionRecord:
    return EvidenceRetentionRegistry(id_factory=lambda: UUID(int=4)).plan(
        EvidenceRetentionPlanRequest(
            action_type="DELETE_RESTRICTED_ARTIFACT",
            artifact_ids=(UUID(int=1),),
            affected_lineage_ids=(UUID(int=2),),
            reason_code="LICENSE_RETENTION_EXPIRED",
            deadline_at=NOW + timedelta(days=1),
            created_at=NOW,
        )
    )


def test_restricted_synthetic_blob_is_deleted_while_audit_is_retained() -> None:
    action = _action()
    result = EvidenceRetentionRegistry().execute(
        action,
        storage=_SyntheticStorage(),
        completed_at=NOW,
    )

    assert result.status == "PASS"
    assert result.artifact_ids == action.artifact_ids
    assert result.affected_lineage_ids == action.affected_lineage_ids


def test_failed_absence_verification_fails_closed() -> None:
    with pytest.raises(LiveEvidenceValidationError) as error:
        EvidenceRetentionRegistry().execute(
            _action(),
            storage=_SyntheticStorage(verify_failure=True),
            completed_at=NOW,
        )

    assert error.value.code == "RETENTION_DELETE_VERIFY_FAILED"
