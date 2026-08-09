from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.enums import (
    ResearchRunStatus,
    ResearchStepStatus,
    ResearchStepType,
)
from stock_research_agent.domain.research_agent.policies import (
    build_controlled_offline_policy,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchAgentRunRecord,
    ResearchPlanRecord,
    ResearchStepDefinition,
    ResearchStepRecord,
    RunBudget,
)
from stock_research_agent.domain.research_agent.tool_catalog import (
    build_tool_catalog_snapshot,
)
from stock_research_agent.tools.registry import create_tool_metadata_registry

MODULE = "stock_research_agent.domain.research_agent.resume"
NOW = datetime(2026, 7, 24, 8, tzinfo=UTC)
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
PLAN_ID = UUID("22222222-2222-4222-8222-222222222222")
POLICY = build_controlled_offline_policy()
CATALOG = build_tool_catalog_snapshot(create_tool_metadata_registry())


def _module() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _budget() -> RunBudget:
    return RunBudget(
        max_steps=12,
        max_tool_calls=24,
        max_calls_per_tool=5,
        max_retries_per_step=1,
        max_duration_seconds=120,
        model_token_budget=0,
        consumed_steps=3,
        consumed_tool_calls=7,
        consumed_model_tokens=0,
        elapsed_seconds=Decimal("12.5"),
        calls_per_tool={"get_data_snapshot": 1},
        retries_per_step={"load_snapshot": 1},
    )


def _run(status: ResearchRunStatus = ResearchRunStatus.PAUSED) -> ResearchAgentRunRecord:
    terminal = status in {
        ResearchRunStatus.COMPLETED,
        ResearchRunStatus.PARTIAL,
        ResearchRunStatus.BLOCKED,
        ResearchRunStatus.FAILED,
        ResearchRunStatus.CANCELLED,
    }
    return ResearchAgentRunRecord(
        id=RUN_ID,
        request_id=UUID("33333333-3333-4333-8333-333333333333"),
        security_id=UUID("44444444-4444-4444-8444-444444444444"),
        snapshot_id=UUID("55555555-5555-4555-8555-555555555555"),
        research_as_of_time=NOW,
        status=status,
        policy_version=POLICY.version,
        planner_version="deterministic-template-v1",
        tool_catalog_version=CATALOG.catalog_version,
        tool_catalog_checksum=CATALOG.catalog_checksum,
        idempotency_key="a" * 64,
        budget=_budget(),
        terminal_reason_code="TERMINAL" if terminal else None,
        created_at=NOW,
        updated_at=NOW,
        terminal_at=NOW if terminal else None,
    )


def _plan() -> ResearchPlanRecord:
    return ResearchPlanRecord(
        id=PLAN_ID,
        run_id=RUN_ID,
        planner_version="deterministic-template-v1",
        plan_version="research-plan-v1",
        tool_catalog_version=CATALOG.catalog_version,
        steps=(
            ResearchStepDefinition(
                step_index=0,
                step_key="done",
                step_type=ResearchStepType.LOAD_SNAPSHOT,
                title="Done",
                required=True,
                tool_name="get_data_snapshot",
                tool_version="1.0.0",
            ),
            ResearchStepDefinition(
                step_index=1,
                step_key="pending",
                step_type=ResearchStepType.QUERY_STRUCTURED_DATA,
                title="Pending",
                required=True,
                dependency_keys=("done",),
                tool_name="get_financial_metrics",
                tool_version="1.0.0",
            ),
        ),
        plan_checksum="b" * 64,
        created_at=NOW,
    )


def _step(index: int, status: ResearchStepStatus) -> ResearchStepRecord:
    definition = _plan().steps[index]
    return ResearchStepRecord(
        id=UUID(int=100 + index),
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        definition=definition,
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


class _Runs:
    def __init__(self, run: ResearchAgentRunRecord) -> None:
        self.run = run

    def get_run(self, run_id: UUID, *, for_update: bool = False) -> ResearchAgentRunRecord:
        assert run_id == RUN_ID
        assert for_update is False
        return self.run


class _Planning:
    def get_plan(self, run_id: UUID) -> ResearchPlanRecord:
        assert run_id == RUN_ID
        return _plan()

    def list_steps(self, plan_id: UUID) -> tuple[ResearchStepRecord, ...]:
        assert plan_id == PLAN_ID
        return (
            _step(0, ResearchStepStatus.PASS),
            _step(1, ResearchStepStatus.RUNNING),
        )


class _StateMachine:
    def __init__(self, run: ResearchAgentRunRecord) -> None:
        self.run = run
        self.calls: list[tuple[UUID, ResearchRunStatus, str | None]] = []

    def transition(
        self,
        run_id: UUID,
        target: ResearchRunStatus,
        reason: str | None = None,
    ) -> ResearchAgentRunRecord:
        self.calls.append((run_id, target, reason))
        self.run = self.run.model_copy(update={"status": target, "updated_at": NOW})
        return self.run


def _service(run: ResearchAgentRunRecord | None = None) -> tuple[object, _StateMachine]:
    current = run or _run()
    state = _StateMachine(current)
    service = _module().ResearchRunControlService(
        run_repository=_Runs(current),
        planning_repository=_Planning(),
        state_machine=state,
        snapshot_validator=lambda security_id, snapshot_id, as_of: (
            security_id == current.security_id
            and snapshot_id == current.snapshot_id
            and as_of == current.research_as_of_time
        ),
    )
    return service, state


def test_resume_revalidates_exact_context_and_preserves_cumulative_budget() -> None:
    service, state = _service()

    result = service.resume(RUN_ID, POLICY, CATALOG)

    assert result.run.status is ResearchRunStatus.RUNNING
    assert result.run.budget == _budget()
    assert result.pending_step_ids == (UUID(int=101),)
    assert result.completed_step_ids == (UUID(int=100),)
    assert result.reuse_unfinished_invocations is False
    assert state.calls == [(RUN_ID, ResearchRunStatus.RUNNING, "RUN_RESUMED")]


@pytest.mark.parametrize(
    ("policy", "catalog", "code"),
    (
        (
            POLICY.model_copy(update={"version": "controlled-offline-v2"}),
            CATALOG,
            "POLICY_VERSION_MISMATCH",
        ),
        (
            POLICY,
            CATALOG.model_copy(update={"catalog_version": "tool-catalog-v1:" + "f" * 64}),
            "TOOL_CATALOG_VERSION_MISMATCH",
        ),
        (
            POLICY,
            CATALOG.model_copy(update={"catalog_checksum": "f" * 64}),
            "TOOL_CATALOG_CHECKSUM_MISMATCH",
        ),
    ),
)
def test_resume_rejects_policy_or_catalog_drift(
    policy: object,
    catalog: object,
    code: str,
) -> None:
    resume = _module()
    service, state = _service()

    with pytest.raises(resume.ResearchRunControlError) as raised:
        service.resume(RUN_ID, policy, catalog)

    assert raised.value.code == code
    assert state.calls == []


@pytest.mark.parametrize(
    "status",
    (
        ResearchRunStatus.CREATED,
        ResearchRunStatus.RUNNING,
        ResearchRunStatus.COMPLETED,
        ResearchRunStatus.PARTIAL,
        ResearchRunStatus.BLOCKED,
        ResearchRunStatus.FAILED,
        ResearchRunStatus.CANCELLED,
    ),
)
def test_only_paused_run_can_resume(status: ResearchRunStatus) -> None:
    resume = _module()
    service, state = _service(_run(status))

    with pytest.raises(resume.ResearchRunControlError) as raised:
        service.resume(RUN_ID, POLICY, CATALOG)

    assert raised.value.code == "RUN_NOT_PAUSED"
    assert state.calls == []


def test_pause_and_cancel_delegate_to_audited_state_machine() -> None:
    running_service, running_state = _service(_run(ResearchRunStatus.RUNNING))
    paused_service, paused_state = _service(_run(ResearchRunStatus.PAUSED))

    paused = running_service.pause(RUN_ID)
    cancelled = paused_service.cancel(RUN_ID)

    assert paused.status is ResearchRunStatus.PAUSED
    assert cancelled.status is ResearchRunStatus.CANCELLED
    assert running_state.calls == [(RUN_ID, ResearchRunStatus.PAUSED, "RUN_PAUSED")]
    assert paused_state.calls == [(RUN_ID, ResearchRunStatus.CANCELLED, "RUN_CANCELLED")]
