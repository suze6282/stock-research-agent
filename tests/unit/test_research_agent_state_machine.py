from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.enums import ResearchRunStatus
from stock_research_agent.domain.research_agent.schemas import (
    ResearchAgentRunRecord,
    ResearchRunUpdate,
    RunBudget,
)

MODULE = "stock_research_agent.domain.research_agent.state_machine"
RUN_ID = UUID("33333333-3333-4333-8333-333333333333")
NOW = datetime(2026, 7, 23, 4, 5, 6, tzinfo=UTC)
ALLOWED = {
    ResearchRunStatus.CREATED: {ResearchRunStatus.PLANNING},
    ResearchRunStatus.PLANNING: {
        ResearchRunStatus.PLANNED,
        ResearchRunStatus.BLOCKED,
        ResearchRunStatus.FAILED,
    },
    ResearchRunStatus.PLANNED: {ResearchRunStatus.RUNNING},
    ResearchRunStatus.RUNNING: {
        ResearchRunStatus.PAUSED,
        ResearchRunStatus.PARTIAL,
        ResearchRunStatus.BLOCKED,
        ResearchRunStatus.COMPLETED,
        ResearchRunStatus.FAILED,
        ResearchRunStatus.CANCELLED,
    },
    ResearchRunStatus.PAUSED: {
        ResearchRunStatus.RUNNING,
        ResearchRunStatus.CANCELLED,
    },
}
TERMINAL = {
    ResearchRunStatus.COMPLETED,
    ResearchRunStatus.PARTIAL,
    ResearchRunStatus.BLOCKED,
    ResearchRunStatus.FAILED,
    ResearchRunStatus.CANCELLED,
}


def _state_machine() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _run(status: ResearchRunStatus) -> ResearchAgentRunRecord:
    return ResearchAgentRunRecord(
        id=RUN_ID,
        request_id=UUID("44444444-4444-4444-8444-444444444444"),
        security_id=UUID("11111111-1111-4111-8111-111111111111"),
        snapshot_id=UUID("22222222-2222-4222-8222-222222222222"),
        research_as_of_time=NOW,
        status=status,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version="tool-catalog-v1:" + "a" * 64,
        tool_catalog_checksum="a" * 64,
        idempotency_key="b" * 64,
        budget=RunBudget(
            max_steps=12,
            max_tool_calls=24,
            max_calls_per_tool=5,
            max_retries_per_step=1,
            max_duration_seconds=120,
            model_token_budget=0,
            consumed_steps=0,
            consumed_tool_calls=0,
            consumed_model_tokens=0,
            elapsed_seconds=Decimal("0"),
        ),
        created_at=NOW,
        updated_at=NOW,
    )


class MemoryRuns:
    def __init__(self, run: ResearchAgentRunRecord) -> None:
        self.run = run
        self.for_update_values: list[bool] = []
        self.events: list[object] = []

    def get_run(self, run_id: UUID, *, for_update: bool = False) -> ResearchAgentRunRecord | None:
        assert run_id == RUN_ID
        self.for_update_values.append(for_update)
        return self.run

    def update_run(self, run_id: UUID, value: ResearchRunUpdate) -> ResearchAgentRunRecord:
        assert run_id == RUN_ID
        assert self.run.status == value.expected_status
        self.run = self.run.model_copy(
            update={
                "status": value.target_status,
                "budget": value.budget,
                "warning_codes": value.warning_codes,
                "terminal_reason_code": value.terminal_reason_code,
                "updated_at": value.changed_at,
                "terminal_at": (value.changed_at if value.target_status in TERMINAL else None),
            }
        )
        return self.run

    def append_event(self, value: object) -> object:
        self.events.append(value)
        return value


@pytest.mark.parametrize(
    ("source", "target"),
    [(source, target) for source, targets in ALLOWED.items() for target in targets],
)
def test_every_approved_transition_locks_updates_and_appends_one_event(
    source: ResearchRunStatus,
    target: ResearchRunStatus,
) -> None:
    state_machine = _state_machine()
    repository = MemoryRuns(_run(source))
    service = state_machine.ResearchRunStateMachine(
        repository,
        event_id_factory=lambda: UUID("55555555-5555-4555-8555-555555555555"),
        next_sequence=lambda _run_id: 1,
        now=lambda: NOW,
    )

    result = service.transition(RUN_ID, target, "APPROVED_TRANSITION")

    assert result.status is target
    assert repository.for_update_values == [True]
    assert len(repository.events) == 1
    event = repository.events[0]
    assert event.from_status is source
    assert event.to_status is target
    assert event.sequence_number == 1


@pytest.mark.parametrize("source", sorted(TERMINAL, key=lambda item: item.value))
def test_terminal_run_cannot_transition_or_append_event(
    source: ResearchRunStatus,
) -> None:
    state_machine = _state_machine()
    repository = MemoryRuns(_run(source))
    service = state_machine.ResearchRunStateMachine(
        repository,
        event_id_factory=lambda: UUID("55555555-5555-4555-8555-555555555555"),
        next_sequence=lambda _run_id: 1,
        now=lambda: NOW,
    )

    with pytest.raises(state_machine.ResearchStateTransitionError) as raised:
        service.transition(RUN_ID, ResearchRunStatus.RUNNING)

    assert raised.value.code == "ILLEGAL_RUN_STATE_TRANSITION"
    assert repository.events == []
