from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.offline_pipeline import (
    OfflineAgentExecutionResult,
    OfflineAgentPlan,
    OfflineAgentPlanRequest,
    OfflinePipelineRegistry,
)
from stock_research_agent.domain.research_agent.enums import (
    ResearchRunStatus,
    ResearchType,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchAgentRunRecord,
    RunBudget,
)

NOW = datetime(2026, 7, 13, 12, tzinfo=UTC)
SECURITY_ID = UUID("91000000-0000-4000-8000-000000000001")
SNAPSHOT_ID = UUID("91000000-0000-4000-8000-000000000002")
RUN_ID = UUID("91000000-0000-4000-8000-000000000003")
REQUEST_ID = UUID("91000000-0000-4000-8000-000000000004")
PACKAGE_ID = UUID("91000000-0000-4000-8000-000000000005")


def _registry() -> OfflinePipelineRegistry:
    return OfflinePipelineRegistry(
        registry_id="OFFLINE_PIPELINE_REGISTRY",
        registry_version="1.0.0",
        registry_checksum="f" * 64,
    )


def _plan() -> OfflineAgentPlan:
    return _registry().plan_agent(
        OfflineAgentPlanRequest(
            snapshot_id=SNAPSHOT_ID,
            snapshot_checksum="a" * 64,
            snapshot_status="COMPLETE",
            security_id=SECURITY_ID,
            research_as_of_time=NOW,
            research_type=ResearchType.DATA_QUALITY_REVIEW,
            policy_version="controlled-offline-v1",
            policy_checksum="b" * 64,
            approved_policy_version="controlled-offline-v1",
            approved_policy_checksum="b" * 64,
            tool_catalog_version="tool-catalog-v1:" + "c" * 64,
            tool_catalog_checksum="c" * 64,
            planner_version="deterministic-template-v1",
        )
    )


def _run() -> ResearchAgentRunRecord:
    return ResearchAgentRunRecord(
        id=RUN_ID,
        request_id=REQUEST_ID,
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        status=ResearchRunStatus.PARTIAL,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version="tool-catalog-v1:" + "c" * 64,
        tool_catalog_checksum="c" * 64,
        idempotency_key="d" * 64,
        budget=RunBudget(
            max_steps=12,
            max_tool_calls=24,
            max_calls_per_tool=5,
            max_retries_per_step=1,
            max_duration_seconds=120,
            model_token_budget=0,
            consumed_steps=3,
            consumed_tool_calls=2,
            consumed_model_tokens=0,
            elapsed_seconds=Decimal("0"),
        ),
        warning_codes=("NO_COMPANY_EVIDENCE",),
        terminal_reason_code="PACKAGE_PARTIAL",
        created_at=NOW,
        updated_at=NOW,
        terminal_at=NOW,
    )


class _PersistedControlledAgent:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def execute(self, plan: OfflineAgentPlan) -> OfflineAgentExecutionResult:
        del plan
        self.calls += 1
        if self.fail:
            raise RuntimeError("unsafe internal details")
        return OfflineAgentExecutionResult(run=_run(), package_id=PACKAGE_ID)


def test_explicit_snapshot_executes_once_and_returns_terminal_persisted_run() -> None:
    executor = _PersistedControlledAgent()

    result = _registry().run_agent(_plan(), executor=executor)

    assert executor.calls == 1
    assert result.run.status is ResearchRunStatus.PARTIAL
    assert result.run.snapshot_id == SNAPSHOT_ID
    assert result.run.security_id == SECURITY_ID
    assert result.package_id == PACKAGE_ID


def test_tampered_or_blocked_plan_never_reaches_agent_executor() -> None:
    executor = _PersistedControlledAgent()
    tampered = _plan().model_copy(update={"plan_checksum": "0" * 64})

    with pytest.raises(LiveEvidenceValidationError) as error:
        _registry().run_agent(tampered, executor=executor)

    assert error.value.code == "AGENT_PLAN_CHECKSUM_MISMATCH"
    assert executor.calls == 0


def test_agent_execution_failure_is_reduced_to_safe_blocked_code() -> None:
    executor = _PersistedControlledAgent(fail=True)

    with pytest.raises(LiveEvidenceValidationError) as error:
        _registry().run_agent(_plan(), executor=executor)

    assert error.value.code == "AGENT_EXECUTION_BLOCKED"
