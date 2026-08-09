"""Production deterministic execution over already-persisted offline data."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel

from stock_research_agent.domain.research_agent.enums import (
    ObservationStatus,
    ObservationType,
    ResearchPackageStatus,
    ResearchRunStatus,
    ResearchStepStatus,
    SyntheticStatus,
    ToolInvocationStatus,
)
from stock_research_agent.domain.research_agent.packages import ResearchPackageAssembler
from stock_research_agent.domain.research_agent.schemas import (
    ControlledRunContext,
    ResearchAgentRunRecord,
    ResearchObservationWrite,
    ResearchPackageRecord,
    ResearchPackageWrite,
    ResearchPolicyRecord,
    ResearchRequestRecord,
    ResearchStepRecord,
    ResearchToolInvocationCompletion,
    ResearchToolInvocationWrite,
    RunBudget,
)
from stock_research_agent.domain.research_agent.tool_catalog import ToolCatalogSnapshot
from stock_research_agent.domain.research_agent.tool_execution import ResearchToolExecutor
from stock_research_agent.tools.registry import (
    ToolErrorCode,
    ToolRegistry,
    ToolRegistryError,
)


class ExecutionRepository(Protocol):
    def get_plan(self, run_id: UUID) -> object | None: ...

    def list_steps(self, plan_id: UUID) -> tuple[ResearchStepRecord, ...]: ...

    def transition_step(
        self,
        step_id: UUID,
        *,
        expected_status: ResearchStepStatus,
        target_status: ResearchStepStatus,
        changed_at: datetime,
        skip_reason_code: str | None = None,
    ) -> ResearchStepRecord: ...

    def add_invocation(
        self,
        value: ResearchToolInvocationWrite,
    ) -> object: ...

    def complete_invocation(
        self,
        invocation_id: UUID,
        value: ResearchToolInvocationCompletion,
    ) -> object: ...

    def add_observation(self, value: ResearchObservationWrite) -> object: ...

    def add_package(self, value: ResearchPackageWrite) -> ResearchPackageRecord: ...

    def update_run_budget(
        self,
        run_id: UUID,
        budget: RunBudget,
    ) -> ResearchAgentRunRecord: ...


class RunStateMachine(Protocol):
    def transition(
        self,
        run_id: UUID,
        target: ResearchRunStatus,
        reason: str | None = None,
    ) -> ResearchAgentRunRecord: ...


class CompositeReadOnlyToolInvoker:
    """Route one exact Tool name/version across separately composed registries."""

    def __init__(self, registries: Sequence[ToolRegistry]) -> None:
        self._registries = tuple(registries)
        names: set[tuple[str, str]] = set()
        for registry in self._registries:
            for metadata in registry.list():
                key = (metadata.name, metadata.version)
                if key in names:
                    raise ValueError("DUPLICATE_COMPOSITE_TOOL")
                names.add(key)
        self._names = frozenset(names)

    def execute(
        self,
        name: str,
        version: str,
        payload: Mapping[str, object],
    ) -> BaseModel:
        if (name, version) not in self._names:
            raise ToolRegistryError(ToolErrorCode.TOOL_NOT_FOUND)
        for registry in self._registries:
            if any(item.name == name and item.version == version for item in registry.list()):
                normalized = dict(payload)
                if (
                    name == "search_document_chunks"
                    and normalized.pop("query_template", None) == "company_disclosures_bilingual-v1"
                ):
                    normalized.setdefault("query", "company disclosures")
                return registry.execute(name, version, normalized)
        raise ToolRegistryError(ToolErrorCode.TOOL_NOT_FOUND)


class DeterministicResearchExecutionService:
    """Execute a fixed Plan once, persist its audit trail, and fail closed."""

    def __init__(
        self,
        *,
        repository: ExecutionRepository,
        state_machine: RunStateMachine,
        registries: Sequence[ToolRegistry],
        id_factory: Callable[[], UUID],
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._state_machine = state_machine
        self._id_factory = id_factory
        self._clock = clock
        self._executor = ResearchToolExecutor(
            registry=CompositeReadOnlyToolInvoker(registries),
            id_factory=id_factory,
            clock=clock,
        )

    def execute(
        self,
        *,
        run: ResearchAgentRunRecord,
        request: ResearchRequestRecord,
        policy: ResearchPolicyRecord,
        catalog: ToolCatalogSnapshot,
    ) -> tuple[ResearchAgentRunRecord, ResearchPackageRecord]:
        if run.status is ResearchRunStatus.PLANNED:
            running = self._state_machine.transition(
                run.id,
                ResearchRunStatus.RUNNING,
                "RUN_STARTED",
            )
        elif run.status is ResearchRunStatus.RUNNING:
            running = run
        else:
            raise ValueError("RUN_NOT_EXECUTABLE")
        plan = self._repository.get_plan(run.id)
        if plan is None or not hasattr(plan, "id"):
            raise ValueError("RESEARCH_PLAN_NOT_FOUND")
        steps = self._repository.list_steps(plan.id)
        budget = running.budget
        blocked: list[str] = []
        failed = False

        for step in steps:
            if step.status in {
                ResearchStepStatus.PASS,
                ResearchStepStatus.PARTIAL,
                ResearchStepStatus.BLOCKED,
                ResearchStepStatus.FAIL,
                ResearchStepStatus.SKIPPED,
            }:
                continue
            ready = self._transition(
                step,
                ResearchStepStatus.PENDING,
                ResearchStepStatus.READY,
            )
            active = self._transition(
                ready,
                ResearchStepStatus.READY,
                ResearchStepStatus.RUNNING,
            )
            if active.definition.tool_name is None:
                target = (
                    ResearchStepStatus.BLOCKED
                    if active.definition.step_key == "validate_evidence" and blocked
                    else ResearchStepStatus.PASS
                )
                self._transition(active, ResearchStepStatus.RUNNING, target)
                continue

            result = self._executor.execute(
                context=_context(running, request),
                step=active,
                catalog=catalog,
                policy=policy,
                budget=budget,
                arguments=_arguments(active),
                observation_type=ObservationType.DATA_QUALITY,
                synthetic_status=SyntheticStatus.REAL_VERIFIED,
            )
            budget = result.budget
            self._persist_execution(result)
            target = _step_status(result.status)
            self._transition(active, ResearchStepStatus.RUNNING, target)
            if target is ResearchStepStatus.BLOCKED:
                blocked.append(f"{active.definition.tool_name.upper()}_BLOCKED")
            elif target is ResearchStepStatus.FAIL:
                failed = True
                blocked.append(f"{active.definition.tool_name.upper()}_FAILED")

        running = self._repository.update_run_budget(run.id, budget)
        package = ResearchPackageAssembler().assemble(
            package_id=self._id_factory(),
            run_id=run.id,
            request_id=request.id,
            security_id=run.security_id,
            snapshot_id=run.snapshot_id,
            research_as_of_time=run.research_as_of_time,
            research_type=request.research_type,
            policy_version=run.policy_version,
            planner_version=run.planner_version,
            tool_catalog_version=run.tool_catalog_version,
            requested_sections=request.requested_sections,
            claims=(),
            evidence=(),
            blocked_capabilities=tuple(sorted(set(blocked))),
            warnings=("NO_VALIDATED_CLAIMS",),
            run_failed=failed,
            created_at=self._clock(),
        )
        persisted = self._repository.add_package(package)
        terminal = {
            ResearchPackageStatus.FAILED: ResearchRunStatus.FAILED,
            ResearchPackageStatus.PARTIAL: ResearchRunStatus.PARTIAL,
            ResearchPackageStatus.BLOCKED: ResearchRunStatus.BLOCKED,
            ResearchPackageStatus.COMPLETE: ResearchRunStatus.COMPLETED,
        }[persisted.status]
        completed = self._state_machine.transition(
            running.id,
            terminal,
            f"PACKAGE_{persisted.status.value}",
        )
        return completed, persisted

    def _transition(
        self,
        step: ResearchStepRecord,
        expected: ResearchStepStatus,
        target: ResearchStepStatus,
    ) -> ResearchStepRecord:
        return self._repository.transition_step(
            step.id,
            expected_status=expected,
            target_status=target,
            changed_at=self._clock(),
        )

    def _persist_execution(self, result: object) -> None:
        from stock_research_agent.domain.research_agent.schemas import ToolExecutionResult

        if not isinstance(result, ToolExecutionResult):
            raise TypeError("INVALID_TOOL_EXECUTION_RESULT")
        record = result.invocation
        pending_completion = record.model_dump(
            mode="python",
            exclude={
                "output_checksum",
                "error_code",
                "safe_error_message",
                "completed_at",
            },
        )
        pending_completion["status"] = ToolInvocationStatus.RUNNING
        self._repository.add_invocation(
            ResearchToolInvocationWrite.model_validate(pending_completion)
        )
        self._repository.complete_invocation(
            record.id,
            ResearchToolInvocationCompletion(
                status=record.status,
                output_checksum=record.output_checksum,
                error_code=record.error_code,
                safe_error_message=record.safe_error_message,
                completed_at=record.completed_at or self._clock(),
            ),
        )
        if result.observation is not None:
            self._repository.add_observation(
                ResearchObservationWrite.model_validate(
                    result.observation.model_dump(mode="python")
                )
            )


def _context(
    run: ResearchAgentRunRecord,
    request: ResearchRequestRecord,
) -> ControlledRunContext:
    return ControlledRunContext(
        security_id=run.security_id,
        snapshot_id=run.snapshot_id,
        research_as_of_time=run.research_as_of_time,
        research_agent_run_id=run.id,
        research_request_id=request.id,
        policy_version=run.policy_version,
        tool_catalog_version=run.tool_catalog_version,
    )


def _arguments(step: ResearchStepRecord) -> dict[str, object]:
    name = step.definition.tool_name
    if name == "search_document_chunks":
        return {"query": "company disclosures", "max_results": 10}
    if name in {
        "get_corporate_actions",
        "get_financial_metrics",
        "get_financial_periods",
        "get_normalized_financial_facts",
        "list_document_versions",
        "list_snapshot_items",
    }:
        return {"limit": 20}
    return {}


def _step_status(status: ObservationStatus) -> ResearchStepStatus:
    return {
        ObservationStatus.PASS: ResearchStepStatus.PASS,
        ObservationStatus.PARTIAL: ResearchStepStatus.PARTIAL,
        ObservationStatus.BLOCKED: ResearchStepStatus.BLOCKED,
        ObservationStatus.FAIL: ResearchStepStatus.FAIL,
    }[status]
