"""Read-only issuer master-data API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from stock_research_agent.api.dependencies import get_security_master_repository
from stock_research_agent.api.errors import ApiError
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.domain.securities.schemas import IssuerDetail

router = APIRouter(prefix="/issuers", tags=["issuers"])
SecurityRepositoryDependency = Annotated[
    SqlAlchemySecurityMasterRepository,
    Depends(get_security_master_repository),
]


@router.get("/{issuer_id}", response_model=IssuerDetail)
def get_issuer(
    issuer_id: UUID,
    repository: SecurityRepositoryDependency,
) -> IssuerDetail:
    detail = repository.get_issuer(issuer_id)
    if detail is None:
        raise ApiError(
            code="ISSUER_NOT_FOUND",
            message="Issuer was not found",
            status_code=404,
        )
    return detail
