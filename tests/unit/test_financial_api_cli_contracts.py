from __future__ import annotations

from typing import cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from stock_research_agent.api.errors import ApiError
from stock_research_agent.api.read_only import execute_financial_read_tool
from stock_research_agent.cli import app as cli_app
from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.domain.financials.queries import FinancialQueryService
from stock_research_agent.domain.financials.repositories import FinancialReadRepository
from stock_research_agent.main import create_app


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=None,
    )


def test_stage5_read_only_api_paths_are_present_in_openapi() -> None:
    schema = TestClient(create_app(_settings())).get("/openapi.json").json()
    paths = schema["paths"]

    assert "/api/v1/securities/{security_id}/financial-periods" in paths
    assert "/api/v1/securities/{security_id}/normalized-financial-facts" in paths
    assert "/api/v1/securities/{security_id}/financial-metrics" in paths
    assert "/api/v1/securities/{security_id}/financial-metrics/{metric_code}" in paths
    assert "/api/v1/calculation-runs/{calculation_run_id}" in paths
    assert "/api/v1/calculation-runs/{calculation_run_id}/lineage" in paths
    assert all("post" not in paths[path] for path in paths if "financial" in path)


def test_financial_cli_exposes_explicit_write_and_read_commands() -> None:
    result = CliRunner().invoke(cli_app, ["financials", "--help"])

    assert result.exit_code == 0
    for command in (
        "seed-v0",
        "normalize",
        "calculate",
        "periods",
        "facts",
        "metrics",
        "metric",
        "lineage",
    ):
        assert command in result.stdout


class MissingCalculationRunRepository:
    def read_calculation_run(self, calculation_run_id: UUID) -> None:
        assert calculation_run_id == UUID("a0000000-0000-0000-0000-000000000099")
        return None


def test_missing_calculation_run_maps_to_safe_404() -> None:
    service = FinancialQueryService(
        cast(FinancialReadRepository, MissingCalculationRunRepository())
    )

    with pytest.raises(ApiError) as raised:
        execute_financial_read_tool(
            service,
            name="get_calculation_run",
            payload={"calculation_run_id": UUID("a0000000-0000-0000-0000-000000000099")},
        )

    assert raised.value.status_code == 404
    assert raised.value.code == "FINANCIAL_RESOURCE_NOT_FOUND"
