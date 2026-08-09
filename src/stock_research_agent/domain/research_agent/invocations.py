"""Bounded, redacted lifecycle helpers for Research Tool invocations."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import NoReturn, cast
from uuid import UUID

from pydantic import JsonValue

from stock_research_agent.domain.research_agent.canonical import (
    canonical_json,
    stable_checksum,
)
from stock_research_agent.domain.research_agent.enums import ToolInvocationStatus
from stock_research_agent.domain.research_agent.schemas import (
    AuthorizedToolCall,
    ControlledRunContext,
    ResearchToolInvocationCompletion,
    ResearchToolInvocationWrite,
)


class ResearchInvocationError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_MAX_INPUT_BYTES = 8_192
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "header",
    "password",
    "path",
    "secret",
    "token",
)
_TERMINAL = frozenset(
    {
        ToolInvocationStatus.PASS,
        ToolInvocationStatus.PARTIAL,
        ToolInvocationStatus.BLOCKED,
        ToolInvocationStatus.FAIL,
    }
)


def redact_tool_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Return a JSON-safe redacted copy without mutating caller-owned data."""

    encoded = canonical_json(payload).encode("utf-8")
    if len(encoded) > _MAX_INPUT_BYTES:
        _reject("INVOCATION_INPUT_TOO_LARGE")
    redacted = _redact(payload)
    normalized = json.loads(canonical_json(redacted))
    if not isinstance(normalized, dict):
        _reject("INVALID_INVOCATION_INPUT")
    return normalized


def start_invocation(
    *,
    invocation_id: UUID,
    context: ControlledRunContext,
    step_id: UUID,
    authorized_call: AuthorizedToolCall,
    bound_input: Mapping[str, object],
    attempt_number: int,
    started_at: datetime,
) -> ResearchToolInvocationWrite:
    """Create the immutable start record for one bounded Tool attempt."""

    if attempt_number not in {1, 2}:
        _reject("INVALID_ATTEMPT_NUMBER")
    return ResearchToolInvocationWrite(
        id=invocation_id,
        run_id=context.research_agent_run_id,
        step_id=step_id,
        attempt_number=attempt_number,
        tool_name=authorized_call.tool_name,
        tool_version=authorized_call.tool_version,
        status=ToolInvocationStatus.RUNNING,
        redacted_input=cast(dict[str, JsonValue], redact_tool_payload(bound_input)),
        input_checksum=stable_checksum(bound_input),
        started_at=started_at,
    )


def complete_invocation(
    *,
    invocation: ResearchToolInvocationWrite,
    status: ToolInvocationStatus,
    completed_at: datetime,
    output: object | None = None,
    error_code: str | None = None,
    safe_error_message: str | None = None,
) -> ResearchToolInvocationCompletion:
    """Build one terminal completion without persisting raw exceptions."""

    if status not in _TERMINAL:
        _reject("INVOCATION_NOT_TERMINAL")
    if completed_at < invocation.started_at:
        _reject("INVALID_COMPLETION_TIME")

    successful = status in {ToolInvocationStatus.PASS, ToolInvocationStatus.PARTIAL}
    if successful and (output is None or error_code is not None):
        _reject("INVALID_COMPLETION_SHAPE")
    if not successful and (output is not None or error_code is None):
        _reject("INVALID_COMPLETION_SHAPE")

    return ResearchToolInvocationCompletion(
        status=status,
        output_checksum=stable_checksum(output) if output is not None else None,
        error_code=error_code,
        safe_error_message=_safe_message(safe_error_message),
        completed_at=completed_at,
    )


def _redact(value: object) -> object:
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized = key.casefold().replace("-", "_")
            if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                result[key] = "[REDACTED]"
            else:
                result[key] = _redact(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_redact(item) for item in value]
    return value


def _safe_message(value: str | None) -> str | None:
    if value is None:
        return None
    sanitized = re.sub(r"[\x00-\x1f\x7f]+", " ", value)
    return " ".join(sanitized.split())[:256]


def _reject(code: str) -> NoReturn:
    raise ResearchInvocationError(code)
