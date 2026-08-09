"""GET-only projections for persisted verifiable research reports."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, JsonValue

from stock_research_agent.api.dependencies import (
    get_report_query_service,
    require_database_ready,
)
from stock_research_agent.api.errors import ApiError
from stock_research_agent.api.read_only import require_query_keys
from stock_research_agent.domain.reports.queries import (
    ReportQueryNotFoundError,
    ReportQueryService,
)
from stock_research_agent.domain.research_agent.schemas import (
    Page,
    PageRequest,
)

router = APIRouter(
    prefix="/research-reports",
    tags=["research-reports"],
    dependencies=[Depends(require_database_ready)],
)
ReportServiceDependency = Annotated[
    ReportQueryService,
    Depends(get_report_query_service),
]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=10_000)]
JsonObject = dict[str, JsonValue]


def _read[ValueT](operation: Callable[[], ValueT]) -> ValueT:
    try:
        return operation()
    except ReportQueryNotFoundError as exc:
        raise ApiError(
            code=exc.code,
            message="Report resource was not found",
            status_code=404,
        ) from exc


def _json(value: object) -> JsonObject:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    raise TypeError("invalid report query projection")


def _page(value: Page[object]) -> JsonObject:
    return value.model_dump(mode="json")


def _request_page(limit: int, offset: int) -> PageRequest:
    return PageRequest(limit=limit, offset=offset)


@router.get("/{report_id}", response_model=JsonObject)
def get_research_report(
    request: Request,
    report_id: UUID,
    service: ReportServiceDependency,
) -> JsonObject:
    require_query_keys(request, frozenset())
    return _json(_read(lambda: service.get_report(report_id)))


@router.get("/{report_id}/sections", response_model=JsonObject)
def get_report_sections(
    request: Request,
    report_id: UUID,
    service: ReportServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _page(
        _read(
            lambda: service.list_sections(
                report_id,
                _request_page(limit, offset),
            )
        )
    )


@router.get("/{report_id}/blocks", response_model=JsonObject)
def get_report_blocks(
    request: Request,
    report_id: UUID,
    service: ReportServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _page(
        _read(
            lambda: service.list_blocks(
                report_id,
                _request_page(limit, offset),
            )
        )
    )


@router.get("/{report_id}/claims", response_model=JsonObject)
def get_report_claim_bindings(
    request: Request,
    report_id: UUID,
    service: ReportServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _page(
        _read(
            lambda: service.list_claim_bindings(
                report_id,
                _request_page(limit, offset),
            )
        )
    )


@router.get("/{report_id}/evidence", response_model=JsonObject)
def get_report_evidence_bindings(
    request: Request,
    report_id: UUID,
    service: ReportServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _page(
        _read(
            lambda: service.list_evidence_bindings(
                report_id,
                _request_page(limit, offset),
            )
        )
    )


@router.get("/{report_id}/citations", response_model=JsonObject)
def get_report_citations(
    request: Request,
    report_id: UUID,
    service: ReportServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _page(
        _read(
            lambda: service.list_citations(
                report_id,
                _request_page(limit, offset),
            )
        )
    )


@router.get("/{report_id}/reflection-runs", response_model=JsonObject)
def get_report_reflection_runs(
    request: Request,
    report_id: UUID,
    service: ReportServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _page(
        _read(
            lambda: service.list_reflection_runs(
                report_id,
                _request_page(limit, offset),
            )
        )
    )


@router.get(
    "/{report_id}/reflection-findings",
    response_model=JsonObject,
)
def get_report_reflection_findings(
    request: Request,
    report_id: UUID,
    service: ReportServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _page(
        _read(
            lambda: service.list_reflection_findings(
                report_id,
                _request_page(limit, offset),
            )
        )
    )


@router.get("/{report_id}/revisions", response_model=JsonObject)
def get_report_revision_runs(
    request: Request,
    report_id: UUID,
    service: ReportServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _page(
        _read(
            lambda: service.list_revisions(
                report_id,
                _request_page(limit, offset),
            )
        )
    )


@router.get("/{report_id}/release-gate", response_model=JsonObject)
def get_report_release_gate(
    request: Request,
    report_id: UUID,
    service: ReportServiceDependency,
) -> JsonObject:
    require_query_keys(request, frozenset())
    return _json(_read(lambda: service.get_release_gate(report_id)))


__all__ = ["router"]
