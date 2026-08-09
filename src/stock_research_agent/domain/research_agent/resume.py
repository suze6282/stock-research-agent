"""Explicit pause, resume, and cancel controls for Research Runs."""

from __future__ import annotations

from collections.abc import Callable
from typing import NoReturn, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from stock_research_agent.domain.research_agent.enums import (
    ResearchRunStatus,
    ResearchStepStatus,
)
from stock_research_agent.domain.research_agent.repositories import (
    ResearchPlanningRepository,
    ResearchRunRepository,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchAgentRunRecord,
    ResearchPolicyRecord,
)
from stock_research_agent.domain.research_agent.tool_catalog import ToolCatalogSnapshot


class RunStateMachine(Protocol):
    def transition(
        self,
        run_id: UUID,
        target: ResearchRunStatus,
        reason: str | None = None,
    ) -> ResearchAgentRunRecord: ...


class ResearchRunControlError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ResumeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    run: ResearchAgentRunRecord
    completed_step_ids: tuple[UUID, ...]
    pending_step_ids: tuple[UUID, ...]
    reuse_unfinished_invocations: bool = False


_TERMINAL_STEPS = frozenset(
    {
        ResearchStepStatus.PASS,
        ResearchStepStatus.PARTIAL,
        ResearchStepStatus.BLOCKED,
        ResearchStepStatus.FAIL,
        ResearchStepStatus.SKIPPED,
    }
)


class ResearchRunControlService:
    def __init__(
        self,
        *,
        run_repository: ResearchRunRepository,
        planning_repository: ResearchPlanningRepository,
        state_machine: RunStateMachine,
        snapshot_validator: Callable[[UUID, UUID, object], bool],
    ) -> None:
        self._runs = run_repository
        self._planning = planning_repository
        self._state_machine = state_machine
        self._snapshot_validator = snapshot_validator

    def pause(self, run_id: UUID) -> ResearchAgentRunRecord:
        run = self._require(run_id)
        if run.status is not ResearchRunStatus.RUNNING:
            _reject("RUN_NOT_RUNNING")
        return self._state_machine.transition(
            run_id,
            ResearchRunStatus.PAUSED,
            "RUN_PAUSED",
        )

    def resume(
        self,
        run_id: UUID,
        current_policy: ResearchPolicyRecord,
        current_catalog: ToolCatalogSnapshot,
    ) -> ResumeResult:
        run = self._require(run_id)
        if run.status is not ResearchRunStatus.PAUSED:
            _reject("RUN_NOT_PAUSED")
        if run.policy_version != current_policy.version:
            _reject("POLICY_VERSION_MISMATCH")
        if run.tool_catalog_version != current_catalog.catalog_version:
            _reject("TOOL_CATALOG_VERSION_MISMATCH")
        if run.tool_catalog_checksum != current_catalog.catalog_checksum:
            _reject("TOOL_CATALOG_CHECKSUM_MISMATCH")
        if not self._snapshot_validator(
            run.security_id,
            run.snapshot_id,
            run.research_as_of_time,
        ):
            _reject("SNAPSHOT_CONTEXT_MISMATCH")

        plan = self._planning.get_plan(run_id)
        if plan is None:
            _reject("RESEARCH_PLAN_NOT_FOUND")
        steps = self._planning.list_steps(plan.id)
        completed = tuple(step.id for step in steps if step.status in _TERMINAL_STEPS)
        pending = tuple(step.id for step in steps if step.status not in _TERMINAL_STEPS)
        resumed = self._state_machine.transition(
            run_id,
            ResearchRunStatus.RUNNING,
            "RUN_RESUMED",
        )
        return ResumeResult(
            run=resumed,
            completed_step_ids=completed,
            pending_step_ids=pending,
            reuse_unfinished_invocations=False,
        )

    def cancel(self, run_id: UUID) -> ResearchAgentRunRecord:
        run = self._require(run_id)
        if run.status not in {ResearchRunStatus.RUNNING, ResearchRunStatus.PAUSED}:
            _reject("RUN_NOT_CANCELLABLE")
        return self._state_machine.transition(
            run_id,
            ResearchRunStatus.CANCELLED,
            "RUN_CANCELLED",
        )

    def _require(self, run_id: UUID) -> ResearchAgentRunRecord:
        run = self._runs.get_run(run_id)
        if run is None:
            _reject("RESEARCH_RUN_NOT_FOUND")
        return run


def _reject(code: str) -> NoReturn:
    raise ResearchRunControlError(code)
