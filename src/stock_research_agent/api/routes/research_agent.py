"""Read-only HTTP projections for controlled Research Agent audit state."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from stock_research_agent.api.dependencies import (
    get_research_agent_query_service,
    require_database_ready,
)
from stock_research_agent.api.errors import ApiError
from stock_research_agent.api.read_only import require_query_keys
from stock_research_agent.domain.research_agent.queries import (
    ResearchAgentQueryService,
    ResearchQueryNotFoundError,
)
from stock_research_agent.domain.research_agent.schemas import (
    Page,
    PageRequest,
    ResearchAgentRunView,
    ResearchClaimView,
    ResearchEvidenceView,
    ResearchPackageView,
    ResearchPlanView,
    ResearchRunEventView,
    ResearchStepView,
    ResearchToolInvocationView,
)

router = APIRouter(
    prefix="/research-agent",
    tags=["research-agent"],
    dependencies=[Depends(require_database_ready)],
)
ResearchServiceDependency = Annotated[
    ResearchAgentQueryService,
    Depends(get_research_agent_query_service),
]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=10_000)]


def _read[ValueT](operation: Callable[[], ValueT]) -> ValueT:
    try:
        return operation()
    except ResearchQueryNotFoundError as exc:
        raise ApiError(
            code=exc.code,
            message="Research resource was not found",
            status_code=404,
        ) from exc


def _page(limit: int, offset: int) -> PageRequest:
    return PageRequest(limit=limit, offset=offset)


@router.get("/runs/{run_id}", response_model=ResearchAgentRunView)
def get_research_agent_run(
    request: Request,
    run_id: UUID,
    service: ResearchServiceDependency,
) -> ResearchAgentRunView:
    require_query_keys(request, frozenset())
    return _read(lambda: service.get_run(run_id))


@router.get("/runs/{run_id}/plan", response_model=ResearchPlanView)
def get_research_plan(
    request: Request,
    run_id: UUID,
    service: ResearchServiceDependency,
) -> ResearchPlanView:
    require_query_keys(request, frozenset())
    return _read(lambda: service.get_plan(run_id))


@router.get("/runs/{run_id}/steps", response_model=Page[ResearchStepView])
def get_research_steps(
    request: Request,
    run_id: UUID,
    service: ResearchServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[ResearchStepView]:
    require_query_keys(request, frozenset({"limit", "offset"}))
    _read(lambda: service.get_run(run_id))
    return service.list_steps(run_id, _page(limit, offset))


@router.get(
    "/runs/{run_id}/tool-invocations",
    response_model=Page[ResearchToolInvocationView],
)
def get_research_tool_invocations(
    request: Request,
    run_id: UUID,
    service: ResearchServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[ResearchToolInvocationView]:
    require_query_keys(request, frozenset({"limit", "offset"}))
    _read(lambda: service.get_run(run_id))
    return service.list_invocations(run_id, _page(limit, offset))


@router.get("/runs/{run_id}/evidence", response_model=Page[ResearchEvidenceView])
def get_research_evidence(
    request: Request,
    run_id: UUID,
    service: ResearchServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[ResearchEvidenceView]:
    require_query_keys(request, frozenset({"limit", "offset"}))
    _read(lambda: service.get_run(run_id))
    return service.list_evidence(run_id, _page(limit, offset))


@router.get("/runs/{run_id}/claims", response_model=Page[ResearchClaimView])
def get_research_claims(
    request: Request,
    run_id: UUID,
    service: ResearchServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[ResearchClaimView]:
    require_query_keys(request, frozenset({"limit", "offset"}))
    _read(lambda: service.get_run(run_id))
    return service.list_claims(run_id, _page(limit, offset))


@router.get("/runs/{run_id}/events", response_model=Page[ResearchRunEventView])
def get_research_run_events(
    request: Request,
    run_id: UUID,
    service: ResearchServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[ResearchRunEventView]:
    require_query_keys(request, frozenset({"limit", "offset"}))
    _read(lambda: service.get_run(run_id))
    return service.list_events(run_id, _page(limit, offset))


@router.get("/runs/{run_id}/package", response_model=ResearchPackageView)
def get_research_package(
    request: Request,
    run_id: UUID,
    service: ResearchServiceDependency,
) -> ResearchPackageView:
    require_query_keys(request, frozenset())
    return _read(lambda: service.get_package(run_id))


__all__ = ["router"]
