from collections.abc import Callable, Iterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from stock_research_agent.api.errors import ApiError
from stock_research_agent.config import Settings
from stock_research_agent.db.repositories.data_access import SqlAlchemyDataAccessRepository
from stock_research_agent.db.repositories.financials import SqlAlchemyFinancialRepository
from stock_research_agent.db.repositories.knowledge import SqlAlchemyKnowledgeRepository
from stock_research_agent.db.repositories.live_evidence import (
    SqlAlchemyLiveEvidenceQueryRepository,
)
from stock_research_agent.db.repositories.providers import SqlAlchemyProviderQueryRepository
from stock_research_agent.db.repositories.research_agent import (
    SqlAlchemyResearchAgentRepository,
)
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.db.session import session_scope
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.domain.financials.queries import FinancialQueryService
from stock_research_agent.domain.live_evidence.queries import LiveEvidenceQueryService
from stock_research_agent.domain.providers.queries import ProviderQueryService
from stock_research_agent.domain.reports.queries import (
    ReportQueryRepository,
    ReportQueryService,
)
from stock_research_agent.domain.research_agent.queries import (
    ResearchAgentQueryService,
)
from stock_research_agent.domain.retrieval.service import PrecomputedRetrievalQueryService
from stock_research_agent.infrastructure.blob_storage import LocalBlobStorage

DatabaseCheck = Callable[[], None]


def require_database_ready(request: Request) -> None:
    database_check = cast(DatabaseCheck, request.app.state.database_check)
    try:
        database_check()
    except SQLAlchemyError as exc:
        raise ApiError(
            code="DATABASE_UNAVAILABLE",
            message="Database is unavailable",
            status_code=503,
        ) from exc


def get_database_session(request: Request) -> Iterator[Session]:
    factory = cast(
        sessionmaker[Session] | None,
        request.app.state.database_session_factory,
    )
    if factory is None:
        raise ApiError(
            code="DATABASE_UNAVAILABLE",
            message="Database is unavailable",
            status_code=503,
        )
    with session_scope(factory) as session:
        yield session


def get_live_evidence_query_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> LiveEvidenceQueryService:
    return LiveEvidenceQueryService(SqlAlchemyLiveEvidenceQueryRepository(session))


def get_security_master_repository(
    session: Annotated[Session, Depends(get_database_session)],
) -> SqlAlchemySecurityMasterRepository:
    return SqlAlchemySecurityMasterRepository(session)


def get_data_access_query_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> DataAccessQueryService:
    return DataAccessQueryService(SqlAlchemyDataAccessRepository(session))


def get_financial_query_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> FinancialQueryService:
    return FinancialQueryService(SqlAlchemyFinancialRepository(session))


def get_provider_query_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> ProviderQueryService:
    return ProviderQueryService(SqlAlchemyProviderQueryRepository(session))


def get_research_agent_query_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> ResearchAgentQueryService:
    return ResearchAgentQueryService(SqlAlchemyResearchAgentRepository(session))


def get_report_query_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> ReportQueryService:
    from stock_research_agent.db.repositories.reports import (
        SqlAlchemyReportRepository,
    )

    repository = cast(
        ReportQueryRepository,
        SqlAlchemyReportRepository(session),
    )
    return ReportQueryService(repository)


def get_rag_query_service(
    request: Request,
    session: Annotated[Session, Depends(get_database_session)],
) -> Iterator[PrecomputedRetrievalQueryService]:
    settings = cast(Settings, request.app.state.settings)
    storage = LocalBlobStorage(
        settings.blob_storage_root,
        max_blob_bytes=settings.document_max_bytes,
    )
    try:
        yield PrecomputedRetrievalQueryService(
            SqlAlchemyKnowledgeRepository(session, blob_storage=storage)
        )
    finally:
        storage.close()
