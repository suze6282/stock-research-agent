from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict

from stock_research_agent.domain.research_agent.enums import (
    ObservationStatus,
    ObservationType,
    ResearchStepStatus,
    ResearchStepType,
    SyntheticStatus,
    ToolInvocationStatus,
)
from stock_research_agent.domain.research_agent.policies import (
    build_controlled_offline_policy,
)
from stock_research_agent.domain.research_agent.schemas import (
    ControlledRunContext,
    ResearchStepDefinition,
    ResearchStepRecord,
    RunBudget,
)
from stock_research_agent.domain.research_agent.tool_catalog import (
    build_tool_catalog_snapshot,
)
from stock_research_agent.tools.registry import create_tool_metadata_registry

MODULE = "stock_research_agent.domain.research_agent.tool_execution"
NOW = datetime(2026, 7, 24, 8, tzinfo=UTC)
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
STEP_ID = UUID("22222222-2222-4222-8222-222222222222")
SECURITY_ID = UUID("33333333-3333-4333-8333-333333333333")
SNAPSHOT_ID = UUID("44444444-4444-4444-8444-444444444444")
POLICY = build_controlled_offline_policy()
CATALOG = build_tool_catalog_snapshot(create_tool_metadata_registry())


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    security_id: UUID
    snapshot_id: UUID
    status: str = "PASS"


class _Registry:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def execute(self, name: str, version: str, payload: dict[str, object]) -> BaseModel:
        self.calls.append((name, version, dict(payload)))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, BaseModel)
        return outcome


def _module() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _context() -> ControlledRunContext:
    return ControlledRunContext(
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        research_agent_run_id=RUN_ID,
        research_request_id=UUID("55555555-5555-4555-8555-555555555555"),
        policy_version=POLICY.version,
        tool_catalog_version=CATALOG.catalog_version,
    )


def _step() -> ResearchStepRecord:
    return ResearchStepRecord(
        id=STEP_ID,
        run_id=RUN_ID,
        plan_id=UUID("66666666-6666-4666-8666-666666666666"),
        definition=ResearchStepDefinition(
            step_index=0,
            step_key="load_snapshot",
            step_type=ResearchStepType.LOAD_SNAPSHOT,
            title="Load snapshot",
            required=True,
            tool_name="get_data_snapshot",
            tool_version="1.0.0",
        ),
        status=ResearchStepStatus.READY,
        created_at=NOW,
        updated_at=NOW,
    )


def _budget(**updates: object) -> RunBudget:
    values = {
        "max_steps": 20,
        "max_tool_calls": 50,
        "max_calls_per_tool": 5,
        "max_retries_per_step": 1,
        "max_duration_seconds": 60,
        "model_token_budget": 0,
        "consumed_steps": 0,
        "consumed_tool_calls": 0,
        "consumed_model_tokens": 0,
        "elapsed_seconds": Decimal("0"),
        "calls_per_tool": {},
        "retries_per_step": {},
    }
    values.update(updates)
    return RunBudget.model_validate(values)


def _ids() -> object:
    values = iter(
        (
            UUID("77777777-7777-4777-8777-777777777771"),
            UUID("77777777-7777-4777-8777-777777777772"),
            UUID("77777777-7777-4777-8777-777777777773"),
        )
    )
    return lambda: next(values)


def _execute(registry: _Registry, **updates: object) -> object:
    executor = _module().ResearchToolExecutor(
        registry=registry,
        id_factory=_ids(),
        clock=lambda: NOW,
    )
    values = {
        "context": _context(),
        "step": _step(),
        "catalog": CATALOG,
        "policy": POLICY,
        "budget": _budget(),
        "arguments": {},
        "observation_type": ObservationType.DATA_QUALITY,
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
    }
    values.update(updates)
    return executor.execute(**values)


def test_success_executes_exact_tool_once_and_records_observation() -> None:
    registry = _Registry([_Output(security_id=SECURITY_ID, snapshot_id=SNAPSHOT_ID)])

    result = _execute(registry)

    assert registry.calls == [
        (
            "get_data_snapshot",
            "1.0.0",
            {"snapshot_id": SNAPSHOT_ID},
        )
    ]
    assert result.status is ObservationStatus.PASS
    assert result.invocation.status is ToolInvocationStatus.PASS
    assert result.observation is not None
    assert result.observation.security_id == SECURITY_ID
    assert result.budget.consumed_tool_calls == 1
    assert result.budget.consumed_model_tokens == 0


def test_context_and_budget_gates_run_before_registry() -> None:
    tool_execution = _module()
    registry = _Registry([_Output(security_id=SECURITY_ID, snapshot_id=SNAPSHOT_ID)])

    with pytest.raises(tool_execution.ResearchToolExecutionError) as context_error:
        _execute(registry, arguments={"snapshot_id": UUID(int=0)})
    with pytest.raises(tool_execution.ResearchToolExecutionError) as budget_error:
        _execute(registry, budget=_budget(consumed_tool_calls=50))

    assert context_error.value.code == "CONTROLLED_CONTEXT_OVERRIDE"
    assert budget_error.value.code == "TOOL_CALL_BUDGET_EXCEEDED"
    assert registry.calls == []


def test_only_explicit_transient_internal_retries_once_with_identical_input() -> None:
    tool_execution = _module()
    registry = _Registry(
        [
            tool_execution.ResearchToolExecutionError("TRANSIENT_INTERNAL"),
            _Output(security_id=SECURITY_ID, snapshot_id=SNAPSHOT_ID),
        ]
    )

    result = _execute(registry)

    assert len(registry.calls) == 2
    assert registry.calls[0] == registry.calls[1]
    assert result.invocation.attempt_number == 2
    assert result.budget.consumed_tool_calls == 2
    assert result.budget.retries_per_step == {"load_snapshot": 1}


@pytest.mark.parametrize(
    "code",
    (
        "BLOCKED",
        "INVALID_QUERY",
        "NOT_FOUND",
        "PERMISSION_DENIED",
        "FUTURE_DATA",
        "INVALID_CITATION",
        "SCHEMA_ERROR",
    ),
)
def test_forbidden_error_codes_are_never_retried(code: str) -> None:
    tool_execution = _module()
    registry = _Registry([tool_execution.ResearchToolExecutionError(code)])

    result = _execute(registry)

    assert len(registry.calls) == 1
    assert result.observation is None
    assert result.status is ObservationStatus.BLOCKED
    assert result.invocation.status is ToolInvocationStatus.BLOCKED
    assert result.invocation.error_code == code
    assert result.retryable is False


def test_output_scope_violation_fails_without_retry_or_observation() -> None:
    registry = _Registry(
        [
            _Output(
                security_id=UUID("99999999-9999-4999-8999-999999999999"),
                snapshot_id=SNAPSHOT_ID,
            )
        ]
    )

    result = _execute(registry)

    assert len(registry.calls) == 1
    assert result.status is ObservationStatus.FAIL
    assert result.observation is None
    assert result.invocation.error_code == "SECURITY_SCOPE_MISMATCH"
