"""Read-only persisted data API routes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict

from stock_research_agent.api.dependencies import (
    get_data_access_query_service,
    require_database_ready,
)
from stock_research_agent.api.errors import ApiError
from stock_research_agent.api.read_only import (
    execute_read_tool,
    require_query_keys,
    validation_error,
)
from stock_research_agent.domain.data_access.enums import QualityStatus
from stock_research_agent.domain.data_access.provenance import classify_provider_evidence
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.domain.data_access.schemas import DataProviderRecord
from stock_research_agent.tools.schemas import (
    CorporateActionsEnvelope,
    DailyPriceHistoryEnvelope,
    LatestCloseEnvelope,
    ReportedFinancialFactsEnvelope,
    SourceDocumentsEnvelope,
    ToolProvenance,
    ToolQuality,
)

router = APIRouter(
    tags=["data"],
    dependencies=[Depends(require_database_ready)],
)
QueryServiceDependency = Annotated[
    DataAccessQueryService,
    Depends(get_data_access_query_service),
]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderCatalogItem(ApiModel):
    id: UUID
    code: str
    name: str
    provider_type: str
    status: str
    terms_status: str
    capabilities: tuple[str, ...]
    warnings: tuple[str, ...]
    provenance: ToolProvenance


class ProviderCatalogEnvelope(ApiModel):
    status: Literal["PASS", "PARTIAL", "BLOCKED"]
    data: tuple[ProviderCatalogItem, ...] = ()
    warnings: tuple[str, ...] = ()
    quality: ToolQuality
    provenance: ToolProvenance


def _scope_payload(
    *,
    security_id: UUID,
    snapshot_id: UUID | None,
    research_as_of_time: datetime | None,
) -> dict[str, object]:
    if (snapshot_id is None) == (research_as_of_time is None):
        validation_error()
    if research_as_of_time is not None and (
        research_as_of_time.tzinfo is None or research_as_of_time.utcoffset() is None
    ):
        validation_error()
    return {
        "security_id": security_id,
        "snapshot_id": snapshot_id,
        "research_as_of_time": research_as_of_time,
    }


def _provider_markers(
    record: DataProviderRecord,
) -> tuple[ToolProvenance, tuple[str, ...]]:
    markers = classify_provider_evidence(
        provider_type=record.provider_type,
        status=record.status,
        terms_status=record.terms_status,
    )
    return (
        ToolProvenance(
            data_origin=markers.data_origin,
            access_mode=markers.access_mode,
            live_status=markers.live_status,
        ),
        markers.warnings,
    )


def _provider_item(record: DataProviderRecord) -> ProviderCatalogItem:
    provenance, warnings = _provider_markers(record)
    return ProviderCatalogItem(
        id=record.id,
        code=record.code,
        name=record.name,
        provider_type=record.provider_type,
        status=record.status.value,
        terms_status=record.terms_status,
        capabilities=tuple(capability.value for capability in record.capabilities),
        warnings=warnings,
        provenance=provenance,
    )


def _catalog_provenance(items: tuple[ProviderCatalogItem, ...]) -> ToolProvenance:
    provenances = tuple(dict.fromkeys(item.provenance for item in items))
    if len(provenances) == 1:
        return provenances[0]
    if provenances:
        return ToolProvenance(
            data_origin="MIXED",
            access_mode="MIXED",
            live_status="MIXED",
        )
    return ToolProvenance(
        data_origin="UNKNOWN",
        access_mode="UNKNOWN",
        live_status="UNKNOWN",
    )


@router.get("/data/providers", response_model=ProviderCatalogEnvelope)
def provider_catalog(
    request: Request,
    service: QueryServiceDependency,
) -> ProviderCatalogEnvelope:
    require_query_keys(request, frozenset())
    try:
        result = service.provider_catalog(100)
    except Exception as exc:
        raise ApiError(
            code="DATA_ACCESS_QUERY_FAILED",
            message="Data access query failed",
            status_code=503,
        ) from exc
    items = tuple(_provider_item(record) for record in result.records)
    contains_unverified = any(item.warnings for item in items)
    warnings = result.warnings
    if contains_unverified:
        warnings = (*warnings, "PROVIDER_CATALOG_CONTAINS_UNVERIFIED_LIVE_STATUS")
    if result.status is QualityStatus.BLOCKED:
        status: Literal["PASS", "PARTIAL", "BLOCKED"] = "BLOCKED"
        quality_status = QualityStatus.BLOCKED
    elif contains_unverified:
        status = "PARTIAL"
        quality_status = QualityStatus.PARTIAL
    else:
        status = "PASS"
        quality_status = QualityStatus.PASS
    return ProviderCatalogEnvelope(
        status=status,
        data=items,
        warnings=warnings,
        quality=ToolQuality(status=quality_status, record_count=len(items)),
        provenance=_catalog_provenance(items),
    )


@router.get(
    "/securities/{security_id}/prices/latest",
    response_model=LatestCloseEnvelope,
)
def latest_close(
    request: Request,
    security_id: UUID,
    service: QueryServiceDependency,
    snapshot_id: Annotated[UUID | None, Query()] = None,
    research_as_of_time: Annotated[datetime | None, Query()] = None,
    local_trading_date: Annotated[date | None, Query()] = None,
) -> LatestCloseEnvelope:
    require_query_keys(
        request,
        frozenset({"snapshot_id", "research_as_of_time", "local_trading_date"}),
    )
    payload = _scope_payload(
        security_id=security_id,
        snapshot_id=snapshot_id,
        research_as_of_time=research_as_of_time,
    )
    payload["local_trading_date"] = local_trading_date
    return cast(
        LatestCloseEnvelope,
        execute_read_tool(service, name="get_latest_close", payload=payload),
    )


@router.get(
    "/securities/{security_id}/prices",
    response_model=DailyPriceHistoryEnvelope,
)
def price_history(
    request: Request,
    security_id: UUID,
    service: QueryServiceDependency,
    snapshot_id: Annotated[UUID | None, Query()] = None,
    research_as_of_time: Annotated[datetime | None, Query()] = None,
    local_trading_date: Annotated[date | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> DailyPriceHistoryEnvelope:
    require_query_keys(
        request,
        frozenset(
            {
                "snapshot_id",
                "research_as_of_time",
                "local_trading_date",
                "date_from",
                "date_to",
                "limit",
            }
        ),
    )
    if date_from is not None and date_to is not None:
        if date_to < date_from or (date_to - date_from).days + 1 > 366:
            validation_error()
    upper_dates = tuple(value for value in (local_trading_date, date_to) if value is not None)
    effective_upper = min(upper_dates) if upper_dates else None
    payload = _scope_payload(
        security_id=security_id,
        snapshot_id=snapshot_id,
        research_as_of_time=research_as_of_time,
    )
    payload.update(
        {
            "date_from": date_from,
            "local_trading_date": effective_upper,
            "limit": limit,
        }
    )
    return cast(
        DailyPriceHistoryEnvelope,
        execute_read_tool(service, name="get_daily_price_history", payload=payload),
    )


@router.get(
    "/securities/{security_id}/corporate-actions",
    response_model=CorporateActionsEnvelope,
)
def corporate_actions(
    request: Request,
    security_id: UUID,
    service: QueryServiceDependency,
    snapshot_id: Annotated[UUID | None, Query()] = None,
    research_as_of_time: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> CorporateActionsEnvelope:
    require_query_keys(
        request,
        frozenset({"snapshot_id", "research_as_of_time", "limit"}),
    )
    payload = _scope_payload(
        security_id=security_id,
        snapshot_id=snapshot_id,
        research_as_of_time=research_as_of_time,
    )
    payload["limit"] = limit
    return cast(
        CorporateActionsEnvelope,
        execute_read_tool(service, name="get_corporate_actions", payload=payload),
    )


@router.get(
    "/securities/{security_id}/financial-facts",
    response_model=ReportedFinancialFactsEnvelope,
)
def financial_facts(
    request: Request,
    security_id: UUID,
    service: QueryServiceDependency,
    snapshot_id: Annotated[UUID | None, Query()] = None,
    research_as_of_time: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> ReportedFinancialFactsEnvelope:
    require_query_keys(
        request,
        frozenset({"snapshot_id", "research_as_of_time", "limit"}),
    )
    payload = _scope_payload(
        security_id=security_id,
        snapshot_id=snapshot_id,
        research_as_of_time=research_as_of_time,
    )
    payload["limit"] = limit
    return cast(
        ReportedFinancialFactsEnvelope,
        execute_read_tool(service, name="get_reported_financial_facts", payload=payload),
    )


@router.get(
    "/securities/{security_id}/documents",
    response_model=SourceDocumentsEnvelope,
)
def source_documents(
    request: Request,
    security_id: UUID,
    service: QueryServiceDependency,
    snapshot_id: Annotated[UUID | None, Query()] = None,
    research_as_of_time: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> SourceDocumentsEnvelope:
    require_query_keys(
        request,
        frozenset({"snapshot_id", "research_as_of_time", "limit"}),
    )
    payload = _scope_payload(
        security_id=security_id,
        snapshot_id=snapshot_id,
        research_as_of_time=research_as_of_time,
    )
    payload["limit"] = limit
    return cast(
        SourceDocumentsEnvelope,
        execute_read_tool(service, name="list_source_documents", payload=payload),
    )


__all__ = ["router"]
