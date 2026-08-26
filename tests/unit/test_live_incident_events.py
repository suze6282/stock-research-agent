from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.incidents import (
    LiveIncidentEventWrite,
    LiveIncidentRegistry,
)
from tests.unit.test_live_incidents import _write

NOW = datetime(2026, 8, 1, 13, tzinfo=UTC)


def test_incident_events_are_append_only_and_drive_finite_state() -> None:
    registry = LiveIncidentRegistry(id_factory=lambda: UUID(int=10))
    incident = registry.open(_write())
    contained = registry.append_event(
        incident,
        LiveIncidentEventWrite(
            incident_id=incident.id,
            sequence=1,
            event_type="CONTAIN",
            reason_code="ARTIFACT_QUARANTINED",
            created_at=NOW,
        ),
        existing=(),
    )

    assert contained.incident.status == "CONTAINED"
    assert contained.event.sequence == 1


def test_duplicate_sequence_and_invalid_transition_are_rejected() -> None:
    registry = LiveIncidentRegistry(id_factory=lambda: UUID(int=10))
    incident = registry.open(_write())
    first = registry.append_event(
        incident,
        LiveIncidentEventWrite(
            incident_id=incident.id,
            sequence=1,
            event_type="CONTAIN",
            reason_code="ARTIFACT_QUARANTINED",
            created_at=NOW,
        ),
        existing=(),
    )
    with pytest.raises(LiveEvidenceValidationError) as duplicate:
        registry.append_event(first.incident, first.event, existing=(first.event,))
    assert duplicate.value.code == "INCIDENT_EVENT_DUPLICATE"

    with pytest.raises(LiveEvidenceValidationError) as transition:
        registry.append_event(
            incident,
            first.event.model_copy(update={"sequence": 2, "event_type": "CLOSE"}),
            existing=(first.event,),
        )
    assert transition.value.code == "INCIDENT_TRANSITION_INVALID"
