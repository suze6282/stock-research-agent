"""Shared safe helpers for read-only API routes."""

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

from stock_research_agent.api.errors import ApiError
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.domain.financials.queries import FinancialQueryService
from stock_research_agent.tools.registry import (
    ToolErrorCode,
    ToolRegistryError,
    create_financial_tool_registry,
    create_tool_registry,
)
from stock_research_agent.tools.schemas import ToolEnvelope


def validation_error() -> None:
    raise RequestValidationError([])


def require_query_keys(request: Request, allowed: frozenset[str]) -> None:
    keys = [key for key, _value in request.query_params.multi_items()]
    if any(key not in allowed for key in keys) or len(keys) != len(set(keys)):
        validation_error()


def execute_read_tool(
    service: DataAccessQueryService,
    *,
    name: str,
    payload: dict[str, object],
) -> BaseModel:
    try:
        result = create_tool_registry(service).execute(name, "1.0.0", payload)
    except ToolRegistryError as exc:
        if exc.code is ToolErrorCode.INVALID_INPUT:
            validation_error()
        raise ApiError(
            code="DATA_ACCESS_QUERY_FAILED",
            message="Data access query failed",
            status_code=503,
        ) from exc
    if not isinstance(result, ToolEnvelope):
        raise ApiError(
            code="DATA_ACCESS_QUERY_FAILED",
            message="Data access query failed",
            status_code=503,
        )
    _raise_for_tool_outcome(result)
    return result


def execute_financial_read_tool(
    service: FinancialQueryService,
    *,
    name: str,
    payload: dict[str, object],
) -> BaseModel:
    try:
        result = create_financial_tool_registry(service).execute(name, "1.0.0", payload)
    except ToolRegistryError as exc:
        if exc.code is ToolErrorCode.INVALID_INPUT:
            validation_error()
        raise ApiError(
            code="FINANCIAL_QUERY_FAILED",
            message="Financial query failed",
            status_code=503,
        ) from exc
    if not isinstance(result, ToolEnvelope):
        raise ApiError(
            code="FINANCIAL_QUERY_FAILED",
            message="Financial query failed",
            status_code=503,
        )
    _raise_for_financial_tool_outcome(result)
    return result


def _raise_for_tool_outcome(envelope: ToolEnvelope[object]) -> None:
    warnings = set(envelope.warnings)
    if "SNAPSHOT_NOT_FOUND" in warnings or "SNAPSHOT_SECURITY_MISMATCH" in warnings:
        raise ApiError(
            code="SNAPSHOT_NOT_FOUND",
            message="Snapshot was not found",
            status_code=404,
        )
    if warnings & {
        "DATA_ACCESS_QUERY_FAILED",
        "SNAPSHOT_AGGREGATION_UNAVAILABLE",
        "SNAPSHOT_AGGREGATION_INCONSISTENT",
    }:
        raise ApiError(
            code="DATA_ACCESS_QUERY_FAILED",
            message="Data access query failed",
            status_code=503,
        )


def _raise_for_financial_tool_outcome(envelope: ToolEnvelope[object]) -> None:
    warnings = set(envelope.warnings)
    if warnings & {
        "SNAPSHOT_NOT_FOUND",
        "SNAPSHOT_SECURITY_MISMATCH",
        "CALCULATION_RUN_NOT_FOUND",
    }:
        raise ApiError(
            code="FINANCIAL_RESOURCE_NOT_FOUND",
            message="Financial resource was not found",
            status_code=404,
        )
    if "FINANCIAL_QUERY_FAILED" in warnings:
        raise ApiError(
            code="FINANCIAL_QUERY_FAILED",
            message="Financial query failed",
            status_code=503,
        )


__all__ = [
    "execute_financial_read_tool",
    "execute_read_tool",
    "require_query_keys",
    "validation_error",
]
