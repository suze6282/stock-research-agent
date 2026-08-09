"""Read-only persisted snapshot API routes."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from stock_research_agent.api.dependencies import (
    get_data_access_query_service,
    require_database_ready,
)
from stock_research_agent.api.read_only import execute_read_tool, require_query_keys
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.tools.schemas import DataSnapshotEnvelope, SnapshotItemsEnvelope

router = APIRouter(
    prefix="/snapshots",
    tags=["snapshots"],
    dependencies=[Depends(require_database_ready)],
)
QueryServiceDependency = Annotated[
    DataAccessQueryService,
    Depends(get_data_access_query_service),
]


@router.get("/{snapshot_id}", response_model=DataSnapshotEnvelope)
def snapshot_detail(
    request: Request,
    snapshot_id: UUID,
    service: QueryServiceDependency,
) -> DataSnapshotEnvelope:
    require_query_keys(request, frozenset())
    return cast(
        DataSnapshotEnvelope,
        execute_read_tool(
            service,
            name="get_data_snapshot",
            payload={"snapshot_id": snapshot_id},
        ),
    )


@router.get("/{snapshot_id}/items", response_model=SnapshotItemsEnvelope)
def snapshot_items(
    request: Request,
    snapshot_id: UUID,
    service: QueryServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> SnapshotItemsEnvelope:
    require_query_keys(request, frozenset({"limit"}))
    return cast(
        SnapshotItemsEnvelope,
        execute_read_tool(
            service,
            name="list_snapshot_items",
            payload={"snapshot_id": snapshot_id, "limit": limit},
        ),
    )


__all__ = ["router"]
