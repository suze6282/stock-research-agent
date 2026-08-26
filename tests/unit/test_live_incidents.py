from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.incidents import (
    LiveIncidentRegistry,
    LiveIncidentWrite,
)

NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def _write(**updates: object) -> LiveIncidentWrite:
    values: dict[str, object] = {
        "category": "EVIDENCE_INTEGRITY",
        "severity": "HIGH",
        "summary_code": "CHECKSUM_MISMATCH",
        "affected_record_ids": (UUID(int=1), UUID(int=2)),
        "source_checksum": "a" * 64,
        "opened_at": NOW,
    }
    values.update(updates)
    return LiveIncidentWrite.model_validate(values)


def test_incident_open_is_typed_immutable_and_checksum_bound() -> None:
    registry = LiveIncidentRegistry(id_factory=lambda: UUID(int=3))
    first = registry.open(_write())
    second = registry.open(_write())

    assert first.status == "OPEN"
    assert first.incident_checksum == second.incident_checksum
    assert first.affected_record_ids == (UUID(int=1), UUID(int=2))


def test_incident_rejects_empty_or_nil_scope() -> None:
    with pytest.raises(LiveEvidenceValidationError) as error:
        LiveIncidentRegistry().open(_write(affected_record_ids=(UUID(int=0),)))
    assert error.value.code == "INCIDENT_SCOPE_INVALID"
