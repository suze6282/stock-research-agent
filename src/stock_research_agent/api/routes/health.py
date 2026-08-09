from fastapi import APIRouter, Depends

from stock_research_agent import __version__
from stock_research_agent.api.dependencies import require_database_ready
from stock_research_agent.config import Settings


def create_health_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("/live")
    def liveness() -> dict[str, str]:
        return {
            "status": "ok",
            "service": settings.app_name,
            "version": __version__,
        }

    @router.get("/ready", dependencies=[Depends(require_database_ready)])
    def readiness() -> dict[str, str]:
        return {
            "status": "ready",
            "service": settings.app_name,
        }

    return router
