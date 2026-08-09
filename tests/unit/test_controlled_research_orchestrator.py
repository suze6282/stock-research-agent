from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.enums import (
    ResearchMode,
    ResearchRunStatus,
    ResearchSection,
    ResearchStepStatus,
    ResearchStepType,
    ResearchType,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchAgentRunRecord,
    ResearchRequestCreate,
    ResearchRequestRecord,
    ResearchStepDefinition,
    ResearchStepRecord,
    RunBudget,
)

MODULE = "stock_research_agent.domain.research_agent.orchestration"
NOW = datetime(2026, 7, 24, 8, tzinfo=UTC)
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
STEP_IDS = (UUID(int=1), UUID(int=2))


def _module() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _command() -> ResearchRequestCreate:
    return ResearchRequestCreate(
        security_query="MU",
        research_type=ResearchType.DATA_QUALITY_REVIEW,
        snapshot_id=UUID("22222222-2222-4222-8222-222222222222"),
        research_as_of_time=NOW,
        requested_sections=(
            ResearchSection.SECURITY_IDENTITY,
            ResearchSection.DATA_QUALITY,
            ResearchSection.LIMITATIONS,
        ),
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        research_mode=ResearchMode.REAL_RESEARCH,
    )


def _request() -> ResearchRequestRecord:
    return ResearchRequestRecord(
        **_command().model_dump(mode="python"),
        id=UUID("33333333-3333-4333-8333-333333333333"),
        resolved_security_id=UUID("44444444-4444-4444-8444-444444444444"),
        normalized_security_query="MU",
        tool_catalog_version="tool-catalog-v1:" + "a" * 64,
        tool_catalog_checksum="a" * 64,
        request_checksum="b" * 64,
        created_at=NOW,
    )


def _budget() -> RunBudget:
    return RunBudget(
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
    )


def _run(status: ResearchRunStatus = ResearchRunStatus.CREATED) -> ResearchAgentRunRecord:
    terminal = status in {
        ResearchRunStatus.COMPLETED,
        ResearchRunStatus.PARTIAL,
        ResearchRunStatus.BLOCKED,
        ResearchRunStatus.FAILED,
        ResearchRunStatus.CANCELLED,
    }
    return ResearchAgentRunRecord(
        id=RUN_ID,
        request_id=_request().id,
        security_id=_request().resolved_security_id,
        snapshot_id=_request().snapshot_id,
        research_as_of_time=NOW,
        status=status,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version=_request().tool_catalog_version,
        tool_catalog_checksum=_request().tool_catalog_checksum,
        idempotency_key="c" * 64,
        budget=_budget(),
        terminal_reason_code="TERMINAL" if terminal else None,
        created_at=NOW,
        updated_at=NOW,
        terminal_at=NOW if terminal else None,
    )


def _step(step_id: UUID, status: ResearchStepStatus) -> ResearchStepRecord:
    index = STEP_IDS.index(step_id)
    return ResearchStepRecord(
        id=step_id,
        run_id=RUN_ID,
        plan_id=UUID("55555555-5555-4555-8555-555555555555"),
        definition=ResearchStepDefinition(
            step_index=index,
            step_key=f"step_{index}",
            step_type=ResearchStepType.QUERY_STRUCTURED_DATA,
            title=f"Step {index}",
            required=True,
            tool_name="get_financial_metrics",
            tool_version="1.0.0",
        ),
        status=status,
        created_at=NOW,
        updated_at=NOW,
        terminal_at=NOW
        if status
        in {
            ResearchStepStatus.PASS,
            ResearchStepStatus.PARTIAL,
            ResearchStepStatus.BLOCKED,
            ResearchStepStatus.FAIL,
            ResearchStepStatus.SKIPPED,
        }
        else None,
    )


class _Requests:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def create(self, command: ResearchRequestCreate) -> ResearchRequestRecord:
        assert command == _command()
        self.log.append("request")
        return _request()


class _Runs:
    def __init__(self, log: list[str], run: ResearchAgentRunRecord | None = None) -> None:
        self.log = log
        self.run = run or _run()

    def create_or_reuse(self, request: ResearchRequestRecord) -> ResearchAgentRunRecord:
        assert request == _request()
        self.log.append("run")
        return self.run


class _Pipeline:
    def __init__(
        self,
        log: list[str],
        *,
        dynamic: bool = False,
        skipped_required: bool = False,
        terminal_after_first: bool = False,
        step_ids: tuple[UUID, ...] = STEP_IDS,
    ) -> None:
        self.log = log
        self.dynamic = dynamic
        self.skipped_required = skipped_required
        self.terminal_after_first = terminal_after_first
        self.ids = step_ids
        self.executed = 0

    def plan(
        self,
        request: ResearchRequestRecord,
        run: ResearchAgentRunRecord,
    ) -> ResearchAgentRunRecord:
        self.log.append("plan")
        return run.model_copy(update={"status": ResearchRunStatus.PLANNED})

    def ordered_step_ids(self, run_id: UUID) -> tuple[UUID, ...]:
        assert run_id == RUN_ID
        if self.dynamic and self.executed:
            return (*self.ids, UUID(int=99))
        return self.ids

    def execute_step(
        self,
        run: ResearchAgentRunRecord,
        step_id: UUID,
    ) -> object:
        self.executed += 1
        self.log.append(f"step:{step_id.int}")
        status = ResearchStepStatus.SKIPPED if self.skipped_required else ResearchStepStatus.PASS
        run_status = (
            ResearchRunStatus.PARTIAL if self.terminal_after_first else ResearchRunStatus.RUNNING
        )
        return _module().OrchestrationStepResult(
            run=run.model_copy(update={"status": run_status}),
            step=_step(step_id, status),
        )

    def validate_evidence(self, run: ResearchAgentRunRecord) -> ResearchAgentRunRecord:
        self.log.append("evidence")
        return run

    def detect_conflicts(self, run: ResearchAgentRunRecord) -> ResearchAgentRunRecord:
        self.log.append("conflicts")
        return run

    def build_claims(self, run: ResearchAgentRunRecord) -> ResearchAgentRunRecord:
        self.log.append("claims")
        return run

    def validate_claims(self, run: ResearchAgentRunRecord) -> ResearchAgentRunRecord:
        self.log.append("claim_validation")
        return run

    def assemble_package(self, run: ResearchAgentRunRecord) -> ResearchAgentRunRecord:
        self.log.append("package")
        return run

    def finalize(self, run: ResearchAgentRunRecord) -> ResearchAgentRunRecord:
        self.log.append("finalize")
        return run.model_copy(update={"status": ResearchRunStatus.COMPLETED})


class _Control:
    def pause(self, run_id: UUID) -> ResearchAgentRunRecord:
        return _run(ResearchRunStatus.PAUSED)

    def resume(self, run_id: UUID) -> object:
        return _module().OrchestrationResumeResult(
            run=_run(ResearchRunStatus.RUNNING),
            completed_step_ids=(STEP_IDS[0],),
            pending_step_ids=(STEP_IDS[1],),
        )

    def cancel(self, run_id: UUID) -> ResearchAgentRunRecord:
        return _run(ResearchRunStatus.CANCELLED)


def _orchestrator(pipeline: _Pipeline, log: list[str]) -> object:
    return _module().ControlledResearchOrchestrator(
        request_service=_Requests(log),
        run_service=_Runs(log),
        pipeline=pipeline,
        control=_Control(),
    )


def test_run_uses_fixed_component_order_and_one_step_at_a_time() -> None:
    log: list[str] = []

    result = _orchestrator(_Pipeline(log), log).run(_command())

    assert result.status is ResearchRunStatus.COMPLETED
    assert log == [
        "request",
        "run",
        "plan",
        "step:1",
        "step:2",
        "evidence",
        "conflicts",
        "claims",
        "claim_validation",
        "package",
        "finalize",
    ]


def test_plan_is_finite_and_runtime_cannot_add_steps() -> None:
    orchestration = _module()
    log: list[str] = []
    dynamic = _orchestrator(_Pipeline(log, dynamic=True), log)
    too_many = _orchestrator(
        _Pipeline(log, step_ids=tuple(UUID(int=index) for index in range(1, 22))),
        log,
    )

    with pytest.raises(orchestration.ResearchOrchestrationError) as dynamic_error:
        dynamic.run(_command())
    with pytest.raises(orchestration.ResearchOrchestrationError) as size_error:
        too_many.run(_command())

    assert dynamic_error.value.code == "DYNAMIC_PLAN_MUTATION"
    assert size_error.value.code == "PLAN_STEP_LIMIT_EXCEEDED"


def test_required_step_cannot_be_skipped() -> None:
    orchestration = _module()
    log: list[str] = []

    with pytest.raises(orchestration.ResearchOrchestrationError) as raised:
        _orchestrator(_Pipeline(log, skipped_required=True), log).run(_command())

    assert raised.value.code == "REQUIRED_STEP_SKIPPED"
    assert "package" not in log


def test_terminal_budget_outcome_stops_remaining_steps_but_preserves_postprocessing() -> None:
    log: list[str] = []

    _orchestrator(_Pipeline(log, terminal_after_first=True), log).run(_command())

    assert "step:1" in log
    assert "step:2" not in log
    assert log[-6:] == [
        "evidence",
        "conflicts",
        "claims",
        "claim_validation",
        "package",
        "finalize",
    ]


def test_plan_only_does_not_execute_tools_or_postprocessing() -> None:
    log: list[str] = []

    result = _orchestrator(_Pipeline(log), log).plan(_command())

    assert result.status is ResearchRunStatus.PLANNED
    assert log == ["request", "run", "plan"]


def test_pause_resume_cancel_are_explicit_and_resume_skips_completed_steps() -> None:
    log: list[str] = []
    orchestrator = _orchestrator(_Pipeline(log), log)

    paused = orchestrator.pause(RUN_ID)
    resumed = orchestrator.resume(RUN_ID)
    cancelled = orchestrator.cancel(RUN_ID)

    assert paused.status is ResearchRunStatus.PAUSED
    assert resumed.status is ResearchRunStatus.COMPLETED
    assert cancelled.status is ResearchRunStatus.CANCELLED
    assert "step:1" not in log
    assert "step:2" in log
