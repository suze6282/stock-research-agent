"""Read-only security master API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from stock_research_agent.api.dependencies import get_security_master_repository
from stock_research_agent.api.errors import ApiError
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.domain.securities.enums import ResolutionStatus
from stock_research_agent.domain.securities.normalization import MAX_SECURITY_QUERY_LENGTH
from stock_research_agent.domain.securities.resolution import SecurityResolutionService
from stock_research_agent.domain.securities.schemas import (
    SecurityDetail,
    SecurityResolutionResult,
)

router = APIRouter(prefix="/securities", tags=["securities"])
SecurityRepositoryDependency = Annotated[
    SqlAlchemySecurityMasterRepository,
    Depends(get_security_master_repository),
]


@router.get("/resolve", response_model=SecurityResolutionResult)
def resolve_security(
    query: Annotated[
        str,
        Query(min_length=1, max_length=MAX_SECURITY_QUERY_LENGTH),
    ],
    repository: SecurityRepositoryDependency,
) -> SecurityResolutionResult:
    result = SecurityResolutionService(repository).resolve(query)
    if result.status is ResolutionStatus.INVALID_QUERY:
        raise ApiError(
            code="INVALID_QUERY",
            message="Security query is invalid",
            status_code=422,
        )
    return result


@router.get("/{security_id}", response_model=SecurityDetail)
def get_security(
    security_id: UUID,
    repository: SecurityRepositoryDependency,
) -> SecurityDetail:
    detail = repository.get_security(security_id)
    if detail is None:
        raise ApiError(
            code="SECURITY_NOT_FOUND",
            message="Security was not found",
            status_code=404,
        )
    return detail
