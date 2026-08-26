"""Controlled Research Run context binding for read-only Tool calls."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import NoReturn

from pydantic import BaseModel

from stock_research_agent.domain.research_agent.schemas import (
    AuthorizedToolCall,
    ControlledRunContext,
)


class ResearchToolContextError(RuntimeError):
    """Safe deterministic rejection raised before or after Tool execution."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_CONTROLLED_KEYS = frozenset(
    {
        "security_id",
        "snapshot_id",
        "research_as_of_time",
        "research_agent_run_id",
        "research_request_id",
        "policy_version",
        "tool_catalog_version",
    }
)
_FORBIDDEN_KEYS = frozenset(
    {
        "budget",
        "command",
        "env",
        "environment",
        "file",
        "file_path",
        "model",
        "path",
        "provider",
        "shell",
        "shell_command",
        "sql",
        "uri",
        "url",
    }
)
_SECURITY_AND_SNAPSHOT_TOOLS = frozenset(
    {
        "get_corporate_actions",
        "get_daily_price_history",
        "get_financial_metrics",
        "get_financial_periods",
        "get_latest_close",
        "get_metric_detail",
        "get_normalized_financial_facts",
        "get_reported_financial_facts",
        "get_source_document_metadata",
        "list_document_versions",
        "list_source_documents",
        "search_document_chunks",
    }
)
_SNAPSHOT_TOOLS = frozenset(
    {
        "get_data_snapshot",
        "list_snapshot_items",
        "verify_citation",
    }
)


def bind_tool_input(
    context: ControlledRunContext,
    authorized_call: AuthorizedToolCall,
    arguments: Mapping[str, object],
) -> Mapping[str, object]:
    """Bind immutable scope without exposing unsupported fields to Tool schemas."""

    _validate_untrusted(authorized_call.payload, context)
    _validate_untrusted(arguments, context)

    bound: dict[str, object] = dict(authorized_call.payload)
    for key, value in arguments.items():
        if key in bound and value != bound[key]:
            _reject("PLAN_BINDING_EXPANSION")
        bound[key] = value

    if authorized_call.tool_name in _SECURITY_AND_SNAPSHOT_TOOLS:
        bound["security_id"] = context.security_id
        bound["snapshot_id"] = context.snapshot_id
    elif authorized_call.tool_name in _SNAPSHOT_TOOLS:
        bound["snapshot_id"] = context.snapshot_id
    return bound


def validate_output_scope(
    context: ControlledRunContext,
    result: object,
) -> None:
    """Reject Tool output that escapes the immutable Run scope or as-of time."""

    value = result.model_dump(mode="python") if isinstance(result, BaseModel) else result
    _validate_result(value, context)


def _validate_untrusted(value: object, context: ControlledRunContext) -> None:
    if isinstance(value, datetime):
        if value > context.research_as_of_time:
            _reject("FUTURE_DATA")
        return
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key).casefold()
            if key in _CONTROLLED_KEYS:
                _reject("CONTROLLED_CONTEXT_OVERRIDE")
            if key in _FORBIDDEN_KEYS:
                _reject("FORBIDDEN_TOOL_ARGUMENT")
            _validate_untrusted(item, context)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _validate_untrusted(item, context)


def _validate_result(value: object, context: ControlledRunContext) -> None:
    if isinstance(value, BaseModel):
        _validate_result(value.model_dump(mode="python"), context)
        return
    if isinstance(value, Mapping):
        exact_snapshot_scope = (
            value.get("snapshot_id") == context.snapshot_id
            and value.get("research_as_of_time") is None
        )
        for raw_key, item in value.items():
            key = str(raw_key)
            if key == "security_id" and item != context.security_id:
                _reject("SECURITY_SCOPE_MISMATCH")
            if key == "snapshot_id" and item != context.snapshot_id:
                _reject("SNAPSHOT_SCOPE_MISMATCH")
            if key == "research_agent_run_id" and item != context.research_agent_run_id:
                _reject("RUN_SCOPE_MISMATCH")
            if key == "research_request_id" and item != context.research_request_id:
                _reject("REQUEST_SCOPE_MISMATCH")
            if (
                key == "research_as_of_time"
                and item != context.research_as_of_time
                and not exact_snapshot_scope
            ):
                _reject("AS_OF_SCOPE_MISMATCH")
            if key == "published_at" and isinstance(item, datetime):
                if item > context.research_as_of_time:
                    _reject("FUTURE_DATA")
            _validate_result(item, context)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _validate_result(item, context)


def _reject(code: str) -> NoReturn:
    raise ResearchToolContextError(code)
