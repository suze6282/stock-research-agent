from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.enums import ToolInvocationStatus
from stock_research_agent.domain.research_agent.schemas import (
    AuthorizedToolCall,
    ControlledRunContext,
)

MODULE = "stock_research_agent.domain.research_agent.invocations"
NOW = datetime(2026, 7, 24, 8, tzinfo=UTC)
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
STEP_ID = UUID("22222222-2222-4222-8222-222222222222")
INVOCATION_ID = UUID("33333333-3333-4333-8333-333333333333")


def _module() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _context() -> ControlledRunContext:
    return ControlledRunContext(
        security_id=UUID("44444444-4444-4444-8444-444444444444"),
        snapshot_id=UUID("55555555-5555-4555-8555-555555555555"),
        research_as_of_time=NOW,
        research_agent_run_id=RUN_ID,
        research_request_id=UUID("66666666-6666-4666-8666-666666666666"),
        policy_version="controlled-offline-v1",
        tool_catalog_version="tool-catalog-v1:" + "a" * 64,
    )


def _call() -> AuthorizedToolCall:
    return AuthorizedToolCall(
        tool_name="get_financial_metrics",
        tool_version="1.0.0",
        payload={"limit": 5},
        input_checksum=stable_checksum({"limit": 5}),
    )


def _start(bound_input: dict[str, object] | None = None, attempt: int = 1) -> object:
    invocations = _module()
    return invocations.start_invocation(
        invocation_id=INVOCATION_ID,
        context=_context(),
        step_id=STEP_ID,
        authorized_call=_call(),
        bound_input=bound_input or {"limit": 5},
        attempt_number=attempt,
        started_at=NOW,
    )


def test_start_invocation_records_stable_checksum_and_redacted_input() -> None:
    invocation = _start(
        {
            "limit": 5,
            "authorization": "Bearer secret",
            "headers": {"X-API-Key": "secret"},
            "file_path": "C:\\private\\payload.json",
            "nested": {"password": "hunter2"},
        }
    )

    assert invocation.run_id == RUN_ID
    assert invocation.step_id == STEP_ID
    assert invocation.status is ToolInvocationStatus.RUNNING
    assert invocation.input_checksum == stable_checksum(
        {
            "limit": 5,
            "authorization": "Bearer secret",
            "headers": {"X-API-Key": "secret"},
            "file_path": "C:\\private\\payload.json",
            "nested": {"password": "hunter2"},
        }
    )
    serialized = str(invocation.redacted_input)
    assert "secret" not in serialized
    assert "hunter2" not in serialized
    assert "private" not in serialized
    assert serialized.count("[REDACTED]") >= 4


@pytest.mark.parametrize("attempt", (0, 3))
def test_attempt_number_is_bounded(attempt: int) -> None:
    invocations = _module()

    with pytest.raises(invocations.ResearchInvocationError) as raised:
        _start(attempt=attempt)

    assert raised.value.code == "INVALID_ATTEMPT_NUMBER"


def test_redacted_payload_is_bounded_and_input_is_not_mutated() -> None:
    invocations = _module()
    payload = {"token": "secret", "value": "x" * 9_000}
    original = dict(payload)

    with pytest.raises(invocations.ResearchInvocationError) as raised:
        invocations.redact_tool_payload(payload)

    assert raised.value.code == "INVOCATION_INPUT_TOO_LARGE"
    assert payload == original


def test_complete_success_uses_output_checksum_and_safe_terminal_status() -> None:
    invocations = _module()
    invocation = _start()
    output = {"status": "PASS", "items": [{"value": "1.25"}]}

    completion = invocations.complete_invocation(
        invocation=invocation,
        status=ToolInvocationStatus.PASS,
        completed_at=NOW + timedelta(seconds=1),
        output=output,
    )

    assert completion.status is ToolInvocationStatus.PASS
    assert completion.output_checksum == stable_checksum(output)
    assert completion.error_code is None
    assert completion.safe_error_message is None


def test_failed_completion_never_persists_raw_exception_or_log_injection() -> None:
    invocations = _module()
    invocation = _start()

    completion = invocations.complete_invocation(
        invocation=invocation,
        status=ToolInvocationStatus.FAIL,
        completed_at=NOW + timedelta(seconds=1),
        error_code="TRANSIENT_INTERNAL",
        safe_error_message="safe line\r\nforged log",
    )

    assert completion.output_checksum is None
    assert completion.error_code == "TRANSIENT_INTERNAL"
    assert completion.safe_error_message == "safe line forged log"


@pytest.mark.parametrize(
    "status",
    (ToolInvocationStatus.PENDING, ToolInvocationStatus.RUNNING),
)
def test_completion_requires_terminal_status(status: ToolInvocationStatus) -> None:
    invocations = _module()

    with pytest.raises(invocations.ResearchInvocationError) as raised:
        invocations.complete_invocation(
            invocation=_start(),
            status=status,
            completed_at=NOW + timedelta(seconds=1),
        )

    assert raised.value.code == "INVOCATION_NOT_TERMINAL"


def test_completion_rejects_time_before_start_and_inconsistent_error_shape() -> None:
    invocations = _module()

    with pytest.raises(invocations.ResearchInvocationError) as time_error:
        invocations.complete_invocation(
            invocation=_start(),
            status=ToolInvocationStatus.PASS,
            completed_at=NOW - timedelta(seconds=1),
            output={"status": "PASS"},
        )
    with pytest.raises(invocations.ResearchInvocationError) as shape_error:
        invocations.complete_invocation(
            invocation=_start(),
            status=ToolInvocationStatus.FAIL,
            completed_at=NOW + timedelta(seconds=1),
            output={"secret": "must-not-persist"},
            error_code="INTERNAL_ERROR",
        )

    assert time_error.value.code == "INVALID_COMPLETION_TIME"
    assert shape_error.value.code == "INVALID_COMPLETION_SHAPE"
