from __future__ import annotations

from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.offline_pipeline import release_report
from stock_research_agent.domain.reports.release_gate import ReleaseGateDecision


class _ExistingGate:
    def __init__(self, decision: ReleaseGateDecision) -> None:
        self.decision = decision
        self.calls: list[tuple[UUID, UUID]] = []

    def release(self, report_id: UUID, round_two_id: UUID) -> ReleaseGateDecision:
        self.calls.append((report_id, round_two_id))
        return self.decision


def test_release_delegates_to_existing_gate_without_force_or_bypass() -> None:
    gate = _ExistingGate(ReleaseGateDecision.PUBLISHABLE)

    result = release_report(UUID(int=1), UUID(int=2), gate=gate)

    assert result is ReleaseGateDecision.PUBLISHABLE
    assert gate.calls == [(UUID(int=1), UUID(int=2))]


def test_nonpublishable_existing_gate_result_cannot_be_overridden() -> None:
    gate = _ExistingGate(ReleaseGateDecision.BLOCKED)

    with pytest.raises(LiveEvidenceValidationError) as error:
        release_report(UUID(int=1), UUID(int=2), gate=gate)

    assert error.value.code == "RELEASE_REQUIREMENT_FAILED"
