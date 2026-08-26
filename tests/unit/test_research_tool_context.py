from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.schemas import (
    AuthorizedToolCall,
    ControlledRunContext,
)

MODULE = "stock_research_agent.domain.research_agent.tool_context"
AS_OF = datetime(2026, 7, 24, tzinfo=UTC)
SECURITY_ID = UUID("11111111-1111-4111-8111-111111111111")
SNAPSHOT_ID = UUID("22222222-2222-4222-8222-222222222222")
RUN_ID = UUID("33333333-3333-4333-8333-333333333333")
REQUEST_ID = UUID("44444444-4444-4444-8444-444444444444")


def _module() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _context() -> ControlledRunContext:
    return ControlledRunContext(
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=AS_OF,
        research_agent_run_id=RUN_ID,
        research_request_id=REQUEST_ID,
        policy_version="controlled-offline-v1",
        tool_catalog_version="tool-catalog-v1:" + "a" * 64,
    )


def _call(
    tool_name: str,
    payload: dict[str, object] | None = None,
) -> AuthorizedToolCall:
    values = payload or {}
    return AuthorizedToolCall(
        tool_name=tool_name,
        tool_version="1.0.0",
        payload=values,
        input_checksum=stable_checksum(values),
    )


def test_binder_injects_only_schema_supported_controlled_scope() -> None:
    tool_context = _module()

    snapshot = tool_context.bind_tool_input(
        _context(),
        _call("list_snapshot_items"),
        {"limit": 10},
    )
    financial = tool_context.bind_tool_input(
        _context(),
        _call("get_financial_metrics"),
        {"limit": 5},
    )

    assert snapshot == {"limit": 10, "snapshot_id": SNAPSHOT_ID}
    assert financial == {
        "limit": 5,
        "security_id": SECURITY_ID,
        "snapshot_id": SNAPSHOT_ID,
    }
    assert "research_agent_run_id" not in financial


@pytest.mark.parametrize(
    "field",
    (
        "security_id",
        "snapshot_id",
        "research_as_of_time",
        "research_agent_run_id",
        "research_request_id",
        "policy_version",
        "tool_catalog_version",
    ),
)
def test_no_caller_or_planner_value_can_override_controlled_context(field: str) -> None:
    tool_context = _module()

    with pytest.raises(tool_context.ResearchToolContextError) as raised:
        tool_context.bind_tool_input(
            _context(),
            _call("get_financial_metrics"),
            {field: "attacker-value"},
        )

    assert raised.value.code == "CONTROLLED_CONTEXT_OVERRIDE"


@pytest.mark.parametrize(
    "arguments",
    (
        {"url": "https://attacker.invalid"},
        {"file_path": "C:\\secrets.txt"},
        {"sql": "SELECT * FROM secrets"},
        {"shell_command": "whoami"},
        {"environment": {"API_KEY": "secret"}},
        {"provider": "unapproved"},
        {"model": "unapproved"},
        {"budget": 999},
        {"nested": {"path": "/etc/passwd"}},
    ),
)
def test_forbidden_resource_or_control_arguments_are_rejected(
    arguments: dict[str, object],
) -> None:
    tool_context = _module()

    with pytest.raises(tool_context.ResearchToolContextError) as raised:
        tool_context.bind_tool_input(
            _context(),
            _call("get_financial_metrics"),
            arguments,
        )

    assert raised.value.code == "FORBIDDEN_TOOL_ARGUMENT"


def test_fixed_plan_binding_cannot_be_expanded_and_future_time_is_rejected() -> None:
    tool_context = _module()

    with pytest.raises(tool_context.ResearchToolContextError) as limit_error:
        tool_context.bind_tool_input(
            _context(),
            _call("list_snapshot_items", {"limit": 10}),
            {"limit": 11},
        )
    with pytest.raises(tool_context.ResearchToolContextError) as future_error:
        tool_context.bind_tool_input(
            _context(),
            _call("list_snapshot_items"),
            {"published_at": AS_OF + timedelta(seconds=1)},
        )

    assert limit_error.value.code == "PLAN_BINDING_EXPANSION"
    assert future_error.value.code == "FUTURE_DATA"


@pytest.mark.parametrize(
    ("result", "code"),
    (
        ({"security_id": UUID("99999999-9999-4999-8999-999999999999")}, "SECURITY_SCOPE_MISMATCH"),
        ({"snapshot_id": UUID("99999999-9999-4999-8999-999999999999")}, "SNAPSHOT_SCOPE_MISMATCH"),
        (
            {"research_agent_run_id": UUID("99999999-9999-4999-8999-999999999999")},
            "RUN_SCOPE_MISMATCH",
        ),
        ({"published_at": AS_OF + timedelta(seconds=1)}, "FUTURE_DATA"),
    ),
)
def test_output_scope_must_match_run_context(
    result: dict[str, object],
    code: str,
) -> None:
    tool_context = _module()

    with pytest.raises(tool_context.ResearchToolContextError) as raised:
        tool_context.validate_output_scope(_context(), result)

    assert raised.value.code == code


def test_exact_snapshot_output_may_omit_as_of_when_snapshot_scope_matches() -> None:
    tool_context = _module()

    tool_context.validate_output_scope(
        _context(),
        {
            "snapshot_id": SNAPSHOT_ID,
            "research_as_of_time": None,
        },
    )


def test_missing_as_of_without_matching_snapshot_scope_is_rejected() -> None:
    tool_context = _module()

    with pytest.raises(tool_context.ResearchToolContextError) as raised:
        tool_context.validate_output_scope(
            _context(),
            {"research_as_of_time": None},
        )

    assert raised.value.code == "AS_OF_SCOPE_MISMATCH"
