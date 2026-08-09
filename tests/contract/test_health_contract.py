from fastapi.testclient import TestClient

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.main import create_app


def test_liveness_contract() -> None:
    settings = Settings(
        _env_file=None,
        app_name="contract-agent",
        app_env=AppEnvironment.TEST,
        api_prefix="/contract-api",
    )
    response = TestClient(create_app(settings)).get("/contract-api/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "contract-agent",
        "version": "0.1.0",
    }
    assert response.headers["X-Request-ID"]
