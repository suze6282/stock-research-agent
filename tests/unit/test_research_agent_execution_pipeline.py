from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

from stock_research_agent.domain.research_agent.enums import (
    ResearchMode,
    ResearchPackageStatus,
    ResearchRunStatus,
    ResearchSection,
    ResearchStepStatus,
    ResearchStepType,
    ResearchType,
    ToolInvocationStatus,
)
from stock_research_agent.domain.research_agent.policies import (
    build_controlled_offline_policy,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchAgentRunRecord,
    ResearchRequestRecord,
    ResearchStepDefinition,
    ResearchStepRecord,
    RunBudget,
)
from stock_research_agent.domain.research_agent.tool_catalog import (
    build_tool_catalog_snapshot,
)
from stock_research_agent.tools.registry import create_tool_metadata_registry

NOW = datetime(2026, 7, 24, tzinfo=UTC)
RUN_ID = UUID("82000000-0000-4000-8000-000000000001")
REQUEST_ID = UUID("82000000-0000-4000-8000-000000000002")
SECURITY_ID = UUID("82000000-0000-4000-8000-000000000003")
SNAPSHOT_ID = UUID("82000000-0000-4000-8000-000000000004")
PLAN_ID = UUID("82000000-0000-4000-8000-000000000005")


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


def _records() -> tuple[
    ResearchAgentRunRecord,
    ResearchRequestRecord,
    object,
    object,
    tuple[ResearchStepRecord, ...],
]:
    policy = build_controlled_offline_policy()
    catalog = build_tool_catalog_snapshot(create_tool_metadata_registry())
    request = ResearchRequestRecord(
        id=REQUEST_ID,
        security_query="MU",
        resolved_security_id=SECURITY_ID,
        normalized_security_query="MU",
        research_type=ResearchType.DATA_QUALITY_REVIEW,
        research_mode=ResearchMode.REAL_RESEARCH,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        requested_sections=(ResearchSection.DATA_QUALITY,),
        policy_version=policy.version,
        planner_version="deterministic-template-v1",
        tool_catalog_version=catalog.catalog_version,
        tool_catalog_checksum=catalog.catalog_checksum,
        request_checksum="a" * 64,
        created_at=NOW,
    )
    run = ResearchAgentRunRecord(
        id=RUN_ID,
        request_id=REQUEST_ID,
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        status=ResearchRunStatus.PLANNED,
        policy_version=policy.version,
        planner_version="deterministic-template-v1",
        tool_catalog_version=catalog.catalog_version,
        tool_catalog_checksum=catalog.catalog_checksum,
        idempotency_key="b" * 64,
        budget=_budget(),
        created_at=NOW,
        updated_at=NOW,
    )
    definitions = (
        ResearchStepDefinition(
            step_index=0,
            step_key="resolve_security",
            step_type=ResearchStepType.RESOLVE_SECURITY,
            title="Resolve security",
            required=True,
            component_name="security-resolution-v1",
        ),
        ResearchStepDefinition(
            step_index=1,
            step_key="get_data_snapshot",
            step_type=ResearchStepType.LOAD_SNAPSHOT,
            title="Get data snapshot",
            required=True,
            dependency_keys=("resolve_security",),
            tool_name="get_data_snapshot",
            tool_version="1.0.0",
        ),
    )
    steps = tuple(
        ResearchStepRecord(
            id=UUID(f"82000000-0000-4000-8000-{10 + index:012d}"),
            run_id=RUN_ID,
            plan_id=PLAN_ID,
            definition=definition,
            status=ResearchStepStatus.PENDING,
            created_at=NOW,
            updated_at=NOW,
        )
        for index, definition in enumerate(definitions)
    )
    return run, request, policy, catalog, steps


class _Repository:
    def __init__(self, steps: tuple[ResearchStepRecord, ...]) -> None:
        self.steps = {step.id: step for step in steps}
        self.invocations: list[object] = []
        self.completions: list[tuple[UUID, object]] = []
        self.packages: list[object] = []

    def get_plan(self, run_id: UUID) -> object:
        assert run_id == RUN_ID
        return SimpleNamespace(id=PLAN_ID)

    def list_steps(self, plan_id: UUID) -> tuple[ResearchStepRecord, ...]:
        assert plan_id == PLAN_ID
        return tuple(sorted(self.steps.values(), key=lambda item: item.definition.step_index))

    def transition_step(
        self,
        step_id: UUID,
        *,
        expected_status: ResearchStepStatus,
        target_status: ResearchStepStatus,
        changed_at: datetime,
        skip_reason_code: str | None = None,
    ) -> ResearchStepRecord:
        current = self.steps[step_id]
        assert current.status is expected_status
        updated = current.model_copy(
            update={
                "status": target_status,
                "updated_at": changed_at,
                "skip_reason_code": skip_reason_code,
            }
        )
        self.steps[step_id] = updated
        return updated

    def add_invocation(self, value: object) -> object:
        self.invocations.append(value)
        return value

    def complete_invocation(self, invocation_id: UUID, value: object) -> object:
        self.completions.append((invocation_id, value))
        return value

    def add_observation(self, value: object) -> object:
        raise AssertionError("metadata-only registry must fail closed")

    def add_package(self, value: object) -> object:
        self.packages.append(value)
        return value

    def update_run_budget(
        self,
        run_id: UUID,
        budget: RunBudget,
    ) -> ResearchAgentRunRecord:
        assert run_id == RUN_ID
        self.run = self.run.model_copy(update={"budget": budget})
        return self.run


class _State:
    def __init__(self, run: ResearchAgentRunRecord) -> None:
        self.run = run

    def transition(
        self,
        run_id: UUID,
        target: ResearchRunStatus,
        reason: str | None = None,
    ) -> ResearchAgentRunRecord:
        assert run_id == RUN_ID
        self.run = self.run.model_copy(update={"status": target, "terminal_reason_code": reason})
        return self.run


def test_production_execution_pipeline_runs_fixed_tools_and_fails_closed() -> None:
    module_name = "stock_research_agent.domain.research_agent.application"
    assert importlib.util.find_spec(module_name) is not None
    module = importlib.import_module(module_name)
    run, request, policy, catalog, steps = _records()
    repository = _Repository(steps)
    repository.run = run
    state = _State(run)
    service = module.DeterministicResearchExecutionService(
        repository=repository,
        state_machine=state,
        registries=(create_tool_metadata_registry(),),
        id_factory=uuid4,
        clock=lambda: NOW,
    )

    terminal, package = service.execute(
        run=run,
        request=request,
        policy=policy,
        catalog=catalog,
    )

    assert terminal.status is ResearchRunStatus.FAILED
    assert package.status is ResearchPackageStatus.FAILED
    assert len(repository.invocations) == 1
    assert repository.invocations[0].status is ToolInvocationStatus.RUNNING
    assert len(repository.completions) == 1
    assert repository.completions[0][1].status is ToolInvocationStatus.FAIL
    assert repository.run.budget.consumed_tool_calls == 1
    assert repository.run.budget.consumed_model_tokens == 0
    assert all(
        step.status
        in {
            ResearchStepStatus.PASS,
            ResearchStepStatus.FAIL,
        }
        for step in repository.steps.values()
    )
    assert (
        "EXECUTION_ADAPTER_NOT_COMPOSED"
        not in importlib.import_module(
            "stock_research_agent.cli_agent"
        )._plan_or_run.__code__.co_consts
    )
