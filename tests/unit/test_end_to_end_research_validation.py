from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.validation import (
    EndToEndValidationCheckWrite,
    EndToEndValidationRegistry,
)

NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def _check(**updates: object) -> EndToEndValidationCheckWrite:
    values: dict[str, object] = {
        "validation_run_id": UUID(int=1),
        "sequence": 1,
        "stage_code": "SNAPSHOT",
        "status": "PASS",
        "evidence_record_type": "data_snapshot",
        "evidence_record_id": UUID(int=2),
        "evidence_checksum": "a" * 64,
        "reason_codes": (),
        "created_at": NOW,
    }
    values.update(updates)
    return EndToEndValidationCheckWrite.model_validate(values)


def test_append_check_preserves_typed_status_and_evidence_reference() -> None:
    registry = EndToEndValidationRegistry(id_factory=lambda: UUID(int=3))

    result = registry.append(_check(), existing=())

    assert result.status == "PASS"
    assert result.evidence_record_id == UUID(int=2)
    assert result.id == UUID(int=3)


def test_duplicate_stage_or_invalid_evidence_is_rejected() -> None:
    registry = EndToEndValidationRegistry()
    existing = (registry.append(_check(), existing=()),)
    with pytest.raises(LiveEvidenceValidationError) as duplicate:
        registry.append(_check(sequence=2), existing=existing)
    assert duplicate.value.code == "VALIDATION_CHECK_DUPLICATE"

    with pytest.raises(LiveEvidenceValidationError) as invalid:
        registry.append(_check(evidence_record_id=UUID(int=0)), existing=())
    assert invalid.value.code == "VALIDATION_EVIDENCE_INVALID"
