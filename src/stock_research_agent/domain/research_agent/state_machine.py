"""Deterministic append-audited Research Run state machine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from stock_research_agent.domain.research_agent.enums import (
    ResearchRunEventType,
    ResearchRunStatus,
)
from stock_research_agent.domain.research_agent.repositories import ResearchRunRepository
from stock_research_agent.domain.research_agent.schemas import (
    ResearchAgentRunRecord,
    ResearchRunEventWrite,
    ResearchRunUpdate,
)

ALLOWED_RUN_TRANSITIONS = MappingProxyType(
    {
        ResearchRunStatus.CREATED: frozenset({ResearchRunStatus.PLANNING}),
        ResearchRunStatus.PLANNING: frozenset(
            {
                ResearchRunStatus.PLANNED,
                ResearchRunStatus.BLOCKED,
                ResearchRunStatus.FAILED,
            }
        ),
        ResearchRunStatus.PLANNED: frozenset({ResearchRunStatus.RUNNING}),
        ResearchRunStatus.RUNNING: frozenset(
            {
                ResearchRunStatus.PAUSED,
                ResearchRunStatus.PARTIAL,
                ResearchRunStatus.BLOCKED,
                ResearchRunStatus.COMPLETED,
                ResearchRunStatus.FAILED,
                ResearchRunStatus.CANCELLED,
            }
        ),
        ResearchRunStatus.PAUSED: frozenset(
            {ResearchRunStatus.RUNNING, ResearchRunStatus.CANCELLED}
        ),
    }
)
TERMINAL_RUN_STATUSES = frozenset(
    {
        ResearchRunStatus.COMPLETED,
        ResearchRunStatus.PARTIAL,
        ResearchRunStatus.BLOCKED,
        ResearchRunStatus.FAILED,
        ResearchRunStatus.CANCELLED,
    }
)


class ResearchStateTransitionError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ResearchRunStateMachine:
    def __init__(
        self,
        repository: ResearchRunRepository,
        *,
        event_id_factory: Callable[[], UUID],
        next_sequence: Callable[[UUID], int],
        now: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._event_id_factory = event_id_factory
        self._next_sequence = next_sequence
        self._now = now

    def transition(
        self,
        run_id: UUID,
        target: ResearchRunStatus,
        reason: str | None = None,
    ) -> ResearchAgentRunRecord:
        current = self._repository.get_run(run_id, for_update=True)
        if current is None:
            raise ResearchStateTransitionError("RESEARCH_RUN_NOT_FOUND")
        if target not in ALLOWED_RUN_TRANSITIONS.get(current.status, frozenset()):
            raise ResearchStateTransitionError("ILLEGAL_RUN_STATE_TRANSITION")

        changed_at = self._now()
        terminal_reason = reason if target in TERMINAL_RUN_STATUSES else None
        updated = self._repository.update_run(
            run_id,
            ResearchRunUpdate(
                expected_status=current.status,
                target_status=target,
                budget=current.budget,
                warning_codes=current.warning_codes,
                terminal_reason_code=terminal_reason,
                changed_at=changed_at,
            ),
        )
        self._repository.append_event(
            ResearchRunEventWrite(
                id=self._event_id_factory(),
                run_id=run_id,
                sequence_number=self._next_sequence(run_id),
                event_type=ResearchRunEventType.STATE_TRANSITION,
                from_status=current.status,
                to_status=target,
                reason_code=reason,
                created_at=changed_at,
            )
        )
        return updated
