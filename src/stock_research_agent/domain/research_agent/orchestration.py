"""Finite coordinator for controlled deterministic Research Runs."""

from __future__ import annotations

from typing import NoReturn, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from stock_research_agent.domain.research_agent.enums import (
    ResearchRunStatus,
    ResearchStepStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchAgentRunRecord,
    ResearchRequestCreate,
    ResearchRequestRecord,
    ResearchStepRecord,
)
from stock_research_agent.domain.research_agent.state_machine import (
    TERMINAL_RUN_STATUSES,
)


class RequestService(Protocol):
    def create(self, command: ResearchRequestCreate) -> ResearchRequestRecord: ...


class RunService(Protocol):
    def create_or_reuse(
        self,
        request: ResearchRequestRecord,
    ) -> ResearchAgentRunRecord: ...


class ResearchPipeline(Protocol):
    def plan(
        self,
        request: ResearchRequestRecord,
        run: ResearchAgentRunRecord,
    ) -> ResearchAgentRunRecord: ...

    def ordered_step_ids(self, run_id: UUID) -> tuple[UUID, ...]: ...

    def execute_step(
        self,
        run: ResearchAgentRunRecord,
        step_id: UUID,
    ) -> OrchestrationStepResult: ...

    def validate_evidence(
        self,
        run: ResearchAgentRunRecord,
    ) -> ResearchAgentRunRecord: ...

    def detect_conflicts(
        self,
        run: ResearchAgentRunRecord,
    ) -> ResearchAgentRunRecord: ...

    def build_claims(self, run: ResearchAgentRunRecord) -> ResearchAgentRunRecord: ...

    def validate_claims(
        self,
        run: ResearchAgentRunRecord,
    ) -> ResearchAgentRunRecord: ...

    def assemble_package(
        self,
        run: ResearchAgentRunRecord,
    ) -> ResearchAgentRunRecord: ...

    def finalize(self, run: ResearchAgentRunRecord) -> ResearchAgentRunRecord: ...


class RunControl(Protocol):
    def pause(self, run_id: UUID) -> ResearchAgentRunRecord: ...

    def resume(self, run_id: UUID) -> OrchestrationResumeResult: ...

    def cancel(self, run_id: UUID) -> ResearchAgentRunRecord: ...


class ResearchOrchestrationError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class OrchestrationStepResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    run: ResearchAgentRunRecord
    step: ResearchStepRecord


class OrchestrationResumeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    run: ResearchAgentRunRecord
    completed_step_ids: tuple[UUID, ...]
    pending_step_ids: tuple[UUID, ...]


class ControlledResearchOrchestrator:
    """Sequence components without implementing their domain rules."""

    def __init__(
        self,
        *,
        request_service: RequestService,
        run_service: RunService,
        pipeline: ResearchPipeline,
        control: RunControl,
    ) -> None:
        self._requests = request_service
        self._runs = run_service
        self._pipeline = pipeline
        self._control = control

    def plan(self, command: ResearchRequestCreate) -> ResearchAgentRunRecord:
        request = self._requests.create(command)
        run = self._runs.create_or_reuse(request)
        if run.status is not ResearchRunStatus.CREATED:
            return run
        return self._pipeline.plan(request, run)

    def run(self, command: ResearchRequestCreate) -> ResearchAgentRunRecord:
        planned = self.plan(command)
        if planned.status in TERMINAL_RUN_STATUSES:
            return planned
        return self._execute_existing(planned, frozenset())

    def resume(self, run_id: UUID) -> ResearchAgentRunRecord:
        resumed = self._control.resume(run_id)
        return self._execute_existing(
            resumed.run,
            frozenset(resumed.completed_step_ids),
        )

    def pause(self, run_id: UUID) -> ResearchAgentRunRecord:
        return self._control.pause(run_id)

    def cancel(self, run_id: UUID) -> ResearchAgentRunRecord:
        return self._control.cancel(run_id)

    def _execute_existing(
        self,
        run: ResearchAgentRunRecord,
        completed: frozenset[UUID],
    ) -> ResearchAgentRunRecord:
        step_ids = self._pipeline.ordered_step_ids(run.id)
        if len(step_ids) > 20:
            _reject("PLAN_STEP_LIMIT_EXCEEDED")
        if len(set(step_ids)) != len(step_ids):
            _reject("DUPLICATE_PLAN_STEP")

        current = run
        for step_id in step_ids:
            if step_id in completed:
                continue
            result = self._pipeline.execute_step(current, step_id)
            if result.step.definition.required and result.step.status is ResearchStepStatus.SKIPPED:
                _reject("REQUIRED_STEP_SKIPPED")
            current = result.run
            if self._pipeline.ordered_step_ids(run.id) != step_ids:
                _reject("DYNAMIC_PLAN_MUTATION")
            if current.status in TERMINAL_RUN_STATUSES:
                break

        current = self._pipeline.validate_evidence(current)
        current = self._pipeline.detect_conflicts(current)
        current = self._pipeline.build_claims(current)
        current = self._pipeline.validate_claims(current)
        current = self._pipeline.assemble_package(current)
        return self._pipeline.finalize(current)


def _reject(code: str) -> NoReturn:
    raise ResearchOrchestrationError(code)
