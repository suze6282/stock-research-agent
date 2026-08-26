"""GET-only bounded projections for controlled evidence governance."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import JsonValue

from stock_research_agent.api.dependencies import (
    get_live_evidence_query_service,
    require_database_ready,
)
from stock_research_agent.api.errors import ApiError
from stock_research_agent.api.read_only import require_query_keys
from stock_research_agent.domain.live_evidence.queries import LiveEvidenceQueryService

router = APIRouter(
    prefix="/live-evidence",
    tags=["live-evidence"],
    dependencies=[Depends(require_database_ready)],
)
Service = Annotated[LiveEvidenceQueryService, Depends(get_live_evidence_query_service)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=100_000)]
JsonObject = dict[str, JsonValue]

_ROUTES = {
    "authorizations": "get_live_authorization",
    "authorization-events": "list_live_authorization_events",
    "authorization-consumptions": "list_live_authorization_consumptions",
    "execution-approvals": "get_live_execution_approval",
    "manual-imports": "get_manual_evidence_import",
    "manifests": "get_evidence_ingestion_manifest",
    "validation-runs": "get_real_company_validation_run",
    "end-to-end-validations": "list_end_to_end_validations",
    "incidents": "get_live_incident",
    "incident-events": "list_live_incident_events",
}


def _handler(resource_type: str) -> Callable[..., JsonObject]:
    def read_resource(
        request: Request,
        resource_id: UUID,
        service: Service,
        limit: Limit = 50,
        offset: Offset = 0,
    ) -> JsonObject:
        require_query_keys(request, frozenset({"limit", "offset"}))
        value = service.query(resource_type, resource_id, limit=limit, offset=offset)
        if value is None:
            raise ApiError(
                code="RESOURCE_NOT_FOUND",
                message="Controlled evidence resource was not found",
                status_code=404,
            )
        return value

    read_resource.__name__ = resource_type
    return read_resource


for _path, _resource_type in _ROUTES.items():
    router.add_api_route(
        f"/{_path}/{{resource_id}}",
        _handler(_resource_type),
        methods=["GET"],
        response_model=JsonObject,
    )
