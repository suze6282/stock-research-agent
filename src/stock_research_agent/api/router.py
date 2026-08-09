from fastapi import APIRouter

from stock_research_agent.api.routes.data import router as data_router
from stock_research_agent.api.routes.financials import router as financials_router
from stock_research_agent.api.routes.health import create_health_router
from stock_research_agent.api.routes.issuers import router as issuers_router
from stock_research_agent.api.routes.providers import router as providers_router
from stock_research_agent.api.routes.rag import router as rag_router
from stock_research_agent.api.routes.reports import router as reports_router
from stock_research_agent.api.routes.research_agent import (
    router as research_agent_router,
)
from stock_research_agent.api.routes.securities import router as securities_router
from stock_research_agent.api.routes.snapshots import router as snapshots_router
from stock_research_agent.config import Settings


def create_api_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix=settings.api_prefix)
    router.include_router(create_health_router(settings))
    router.include_router(securities_router)
    router.include_router(issuers_router)
    router.include_router(data_router)
    router.include_router(snapshots_router)
    router.include_router(financials_router)
    router.include_router(rag_router)
    router.include_router(research_agent_router)
    router.include_router(reports_router)
    router.include_router(providers_router)
    return router
