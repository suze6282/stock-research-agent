"""Read-only HTTP routes for persisted Stage 5 financial outputs."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from stock_research_agent.api.dependencies import (
    get_financial_query_service,
    require_database_ready,
)
from stock_research_agent.api.read_only import (
    execute_financial_read_tool,
    require_query_keys,
)
from stock_research_agent.domain.financials.queries import FinancialQueryService
from stock_research_agent.tools.schemas import (
    CalculationRunEnvelope,
    FinancialMetricsEnvelope,
    FinancialPeriodsEnvelope,
    MetricDetailEnvelope,
    MetricLineageEnvelope,
    NormalizedFinancialFactsEnvelope,
)

router = APIRouter(
    tags=["financials"],
    dependencies=[Depends(require_database_ready)],
)
FinancialServiceDependency = Annotated[
    FinancialQueryService,
    Depends(get_financial_query_service),
]


@router.get(
    "/securities/{security_id}/financial-periods",
    response_model=FinancialPeriodsEnvelope,
)
def financial_periods(
    request: Request,
    security_id: UUID,
    service: FinancialServiceDependency,
    snapshot_id: Annotated[UUID, Query()],
    period_type: Annotated[str | None, Query(min_length=2, max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> FinancialPeriodsEnvelope:
    require_query_keys(request, frozenset({"snapshot_id", "period_type", "limit"}))
    return cast(
        FinancialPeriodsEnvelope,
        execute_financial_read_tool(
            service,
            name="get_financial_periods",
            payload={
                "security_id": security_id,
                "snapshot_id": snapshot_id,
                "period_type": period_type,
                "limit": limit,
            },
        ),
    )


@router.get(
    "/securities/{security_id}/normalized-financial-facts",
    response_model=NormalizedFinancialFactsEnvelope,
)
def normalized_financial_facts(
    request: Request,
    security_id: UUID,
    service: FinancialServiceDependency,
    snapshot_id: Annotated[UUID, Query()],
    concept_code: Annotated[str | None, Query(min_length=2, max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> NormalizedFinancialFactsEnvelope:
    require_query_keys(request, frozenset({"snapshot_id", "concept_code", "limit"}))
    return cast(
        NormalizedFinancialFactsEnvelope,
        execute_financial_read_tool(
            service,
            name="get_normalized_financial_facts",
            payload={
                "security_id": security_id,
                "snapshot_id": snapshot_id,
                "concept_code": concept_code,
                "limit": limit,
            },
        ),
    )


@router.get(
    "/securities/{security_id}/financial-metrics",
    response_model=FinancialMetricsEnvelope,
)
def financial_metrics(
    request: Request,
    security_id: UUID,
    service: FinancialServiceDependency,
    snapshot_id: Annotated[UUID, Query()],
    metric_code: Annotated[str | None, Query(min_length=2, max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> FinancialMetricsEnvelope:
    require_query_keys(request, frozenset({"snapshot_id", "metric_code", "limit"}))
    return cast(
        FinancialMetricsEnvelope,
        execute_financial_read_tool(
            service,
            name="get_financial_metrics",
            payload={
                "security_id": security_id,
                "snapshot_id": snapshot_id,
                "metric_code": metric_code,
                "limit": limit,
            },
        ),
    )


@router.get(
    "/securities/{security_id}/financial-metrics/{metric_code}",
    response_model=MetricDetailEnvelope,
)
def metric_detail(
    request: Request,
    security_id: UUID,
    metric_code: str,
    service: FinancialServiceDependency,
    snapshot_id: Annotated[UUID, Query()],
) -> MetricDetailEnvelope:
    require_query_keys(request, frozenset({"snapshot_id"}))
    return cast(
        MetricDetailEnvelope,
        execute_financial_read_tool(
            service,
            name="get_metric_detail",
            payload={
                "security_id": security_id,
                "snapshot_id": snapshot_id,
                "metric_code": metric_code,
            },
        ),
    )


@router.get(
    "/calculation-runs/{calculation_run_id}",
    response_model=CalculationRunEnvelope,
)
def calculation_run(
    request: Request,
    calculation_run_id: UUID,
    service: FinancialServiceDependency,
) -> CalculationRunEnvelope:
    require_query_keys(request, frozenset())
    return cast(
        CalculationRunEnvelope,
        execute_financial_read_tool(
            service,
            name="get_calculation_run",
            payload={"calculation_run_id": calculation_run_id},
        ),
    )


@router.get(
    "/calculation-runs/{calculation_run_id}/lineage",
    response_model=MetricLineageEnvelope,
)
def metric_lineage(
    request: Request,
    calculation_run_id: UUID,
    service: FinancialServiceDependency,
    metric_code: Annotated[str, Query(min_length=2, max_length=64)],
) -> MetricLineageEnvelope:
    require_query_keys(request, frozenset({"metric_code"}))
    return cast(
        MetricLineageEnvelope,
        execute_financial_read_tool(
            service,
            name="get_metric_lineage",
            payload={
                "calculation_run_id": calculation_run_id,
                "metric_code": metric_code,
            },
        ),
    )


__all__ = ["router"]
