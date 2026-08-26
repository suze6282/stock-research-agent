from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.validation import (
    RealCompanyValidationRunWrite,
    ValidationRunRegistry,
)

NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def _write() -> RealCompanyValidationRunWrite:
    return RealCompanyValidationRunWrite(
        security_id=UUID(int=1),
        snapshot_id=UUID(int=2),
        research_agent_run_id=UUID(int=3),
        report_id=UUID(int=4),
        research_as_of_time=NOW,
        validation_policy_version="real-company-validation-v1",
        input_checksums=("a" * 64, "b" * 64),
        created_at=NOW,
    )


def test_validation_run_has_stable_input_checksum_and_finite_transitions() -> None:
    registry = ValidationRunRegistry(id_factory=lambda: UUID(int=10))
    run = registry.create(_write())
    running = registry.transition(run, "RUNNING", changed_at=NOW)
    terminal = registry.transition(running, "PARTIAL", changed_at=NOW)

    assert run.status == "PLANNED"
    assert run.input_checksum == registry.create(_write()).input_checksum
    assert terminal.status == "PARTIAL"
    with pytest.raises(LiveEvidenceValidationError) as error:
        registry.transition(terminal, "RUNNING", changed_at=NOW)
    assert error.value.code == "VALIDATION_TERMINAL_IMMUTABLE"


def test_validation_scope_rejects_duplicate_or_unsorted_inputs() -> None:
    with pytest.raises(ValueError):
        RealCompanyValidationRunWrite.model_validate(
            {
                **_write().model_dump(mode="python"),
                "input_checksums": ("a" * 64, "a" * 64),
            }
        )

    with pytest.raises(LiveEvidenceValidationError) as error:
        ValidationRunRegistry().create(_write().model_copy(update={"snapshot_id": UUID(int=0)}))
    assert error.value.code == "VALIDATION_SCOPE_INVALID"
