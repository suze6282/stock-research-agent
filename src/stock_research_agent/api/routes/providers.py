"""GET-only safe projections for persisted Provider governance state."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, JsonValue

from stock_research_agent.api.dependencies import (
    get_provider_query_service,
    require_database_ready,
)
from stock_research_agent.api.errors import ApiError
from stock_research_agent.api.read_only import require_query_keys
from stock_research_agent.domain.providers.queries import (
    PageRequest,
    ProviderQueryService,
)

router = APIRouter(
    tags=["providers"],
    dependencies=[Depends(require_database_ready)],
)
ProviderServiceDependency = Annotated[
    ProviderQueryService,
    Depends(get_provider_query_service),
]
ProviderCode = Annotated[str, Path(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=100_000)]
JsonObject = dict[str, JsonValue]


def _json(value: BaseModel | None) -> JsonObject:
    if value is None:
        raise ApiError(
            code="PROVIDER_RESOURCE_NOT_FOUND",
            message="Provider resource was not found",
            status_code=404,
        )
    return value.model_dump(mode="json")


def _page(limit: int, offset: int) -> PageRequest:
    return PageRequest(limit=limit, offset=offset)


def _paged_read(
    operation: Callable[[PageRequest], BaseModel], limit: int, offset: int
) -> JsonObject:
    return operation(_page(limit, offset)).model_dump(mode="json")


@router.get("/providers", response_model=JsonObject)
def list_providers(
    request: Request,
    service: ProviderServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _paged_read(service.list_providers, limit, offset)


@router.get("/providers/{provider_code}", response_model=JsonObject)
def get_provider(
    request: Request,
    provider_code: ProviderCode,
    service: ProviderServiceDependency,
) -> JsonObject:
    require_query_keys(request, frozenset())
    return _json(service.get_provider(provider_code))


@router.get("/providers/{provider_code}/capabilities", response_model=JsonObject)
def list_provider_capabilities(
    request: Request,
    provider_code: ProviderCode,
    service: ProviderServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _paged_read(
        lambda page: service.list_capabilities(provider_code, page),
        limit,
        offset,
    )


@router.get("/providers/{provider_code}/health", response_model=JsonObject)
def get_provider_health(
    request: Request,
    provider_code: ProviderCode,
    service: ProviderServiceDependency,
) -> JsonObject:
    require_query_keys(request, frozenset())
    return _json(service.get_health(provider_code))


@router.get("/providers/{provider_code}/license", response_model=JsonObject)
def get_provider_license(
    request: Request,
    provider_code: ProviderCode,
    service: ProviderServiceDependency,
) -> JsonObject:
    require_query_keys(request, frozenset())
    return _json(service.get_license(provider_code))


@router.get("/provider-sync-runs/{run_id}", response_model=JsonObject)
def get_provider_sync_run(
    request: Request,
    run_id: UUID,
    service: ProviderServiceDependency,
) -> JsonObject:
    require_query_keys(request, frozenset())
    return _json(service.get_sync_run(run_id))


@router.get("/provider-sync-runs/{run_id}/requests", response_model=JsonObject)
def list_provider_sync_requests(
    request: Request,
    run_id: UUID,
    service: ProviderServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _paged_read(lambda page: service.list_attempts(run_id, page), limit, offset)


@router.get("/provider-sync-runs/{run_id}/artifacts", response_model=JsonObject)
def list_provider_artifacts(
    request: Request,
    run_id: UUID,
    service: ProviderServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _paged_read(lambda page: service.list_artifacts(run_id, page), limit, offset)


@router.get("/provider-sync-runs/{run_id}/quality-issues", response_model=JsonObject)
def list_provider_quality_issues(
    request: Request,
    run_id: UUID,
    service: ProviderServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _paged_read(
        lambda page: service.list_quality_issues(run_id, page),
        limit,
        offset,
    )


@router.get("/provider-sync-runs/{run_id}/dead-letters", response_model=JsonObject)
def list_provider_dead_letters(
    request: Request,
    run_id: UUID,
    service: ProviderServiceDependency,
    limit: Limit = 50,
    offset: Offset = 0,
) -> JsonObject:
    require_query_keys(request, frozenset({"limit", "offset"}))
    return _paged_read(
        lambda page: service.list_dead_letters(run_id, page),
        limit,
        offset,
    )


@router.get("/provider-readiness/{security_id}", response_model=JsonObject)
def get_provider_readiness(
    request: Request,
    security_id: UUID,
    service: ProviderServiceDependency,
) -> JsonObject:
    require_query_keys(request, frozenset())
    return _json(service.get_readiness(security_id))


__all__ = ["router"]
