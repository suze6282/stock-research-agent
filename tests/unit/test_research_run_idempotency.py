from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.enums import (
    ResearchRunStatus,
    ResearchSection,
    ResearchType,
)
from stock_research_agent.domain.research_agent.policies import (
    build_controlled_offline_policy,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchAgentRunRecord,
    RunBudget,
)

MODULE = "stock_research_agent.domain.research_agent.idempotency"
NOW = datetime(2026, 7, 24, 8, tzinfo=UTC)
BASE = {
    "normalized_request": "MU|FULL_RESEARCH_PACKAGE",
    "security_id": UUID("11111111-1111-4111-8111-111111111111"),
    "snapshot_id": UUID("22222222-2222-4222-8222-222222222222"),
    "research_as_of_time": NOW,
    "research_type": ResearchType.FULL_RESEARCH_PACKAGE,
    "requested_sections": (
        ResearchSection.SECURITY_IDENTITY,
        ResearchSection.DATA_QUALITY,
    ),
    "policy_version": "controlled-offline-v1",
    "planner_version": "deterministic-template-v1",
    "tool_catalog_checksum": "a" * 64,
}


def _module() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _key(**updates: object) -> str:
    values = dict(BASE)
    values.update(updates)
    return _module().research_run_idempotency_key(**values)


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


def _run(status: ResearchRunStatus) -> ResearchAgentRunRecord:
    terminal = status in {
        ResearchRunStatus.COMPLETED,
        ResearchRunStatus.PARTIAL,
        ResearchRunStatus.BLOCKED,
        ResearchRunStatus.FAILED,
        ResearchRunStatus.CANCELLED,
    }
    return ResearchAgentRunRecord(
        id=UUID("33333333-3333-4333-8333-333333333333"),
        request_id=UUID("44444444-4444-4444-8444-444444444444"),
        security_id=BASE["security_id"],
        snapshot_id=BASE["snapshot_id"],
        research_as_of_time=NOW,
        status=status,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version="tool-catalog-v1:" + "a" * 64,
        tool_catalog_checksum="a" * 64,
        idempotency_key=_key(),
        budget=_budget(),
        terminal_reason_code="TERMINAL" if terminal else None,
        created_at=NOW,
        updated_at=NOW,
        terminal_at=NOW if terminal else None,
    )


def test_identical_inputs_are_stable_and_ordered_sections_are_semantic() -> None:
    first = _key()
    second = _key()
    reversed_sections = _key(requested_sections=tuple(reversed(BASE["requested_sections"])))

    assert first == second
    assert len(first) == 64
    assert reversed_sections != first


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("normalized_request", "601138.SH|FULL_RESEARCH_PACKAGE"),
        ("security_id", UUID(int=9)),
        ("snapshot_id", UUID(int=9)),
        ("research_as_of_time", datetime(2026, 7, 23, 8, tzinfo=UTC)),
        ("research_type", ResearchType.DATA_QUALITY_REVIEW),
        ("policy_version", "controlled-offline-v2"),
        ("planner_version", "deterministic-template-v2"),
        ("tool_catalog_checksum", "b" * 64),
    ),
)
def test_every_reproducibility_input_changes_the_key(field: str, value: object) -> None:
    assert _key(**{field: value}) != _key()


@pytest.mark.parametrize(
    "status",
    (
        ResearchRunStatus.CREATED,
        ResearchRunStatus.PLANNING,
        ResearchRunStatus.PLANNED,
        ResearchRunStatus.RUNNING,
        ResearchRunStatus.PAUSED,
        ResearchRunStatus.COMPLETED,
    ),
)
def test_active_and_completed_runs_are_reusable(status: ResearchRunStatus) -> None:
    assert _module().is_reusable_run(_run(status), build_controlled_offline_policy())


@pytest.mark.parametrize(
    "status",
    (
        ResearchRunStatus.BLOCKED,
        ResearchRunStatus.FAILED,
        ResearchRunStatus.CANCELLED,
    ),
)
def test_failed_blocked_and_cancelled_runs_are_not_reusable(
    status: ResearchRunStatus,
) -> None:
    assert not _module().is_reusable_run(_run(status), build_controlled_offline_policy())


def test_partial_reuse_is_controlled_only_by_exact_policy() -> None:
    policy = build_controlled_offline_policy()

    assert not _module().is_reusable_run(_run(ResearchRunStatus.PARTIAL), policy)
    assert _module().is_reusable_run(
        _run(ResearchRunStatus.PARTIAL),
        policy.model_copy(update={"reuse_partial_runs": True}),
    )
    assert not _module().is_reusable_run(
        _run(ResearchRunStatus.PARTIAL),
        policy.model_copy(update={"version": "controlled-offline-v2"}),
    )
