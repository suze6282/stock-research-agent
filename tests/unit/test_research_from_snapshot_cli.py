from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest
from typer.testing import CliRunner

from stock_research_agent import cli_research_pipeline

runner = CliRunner()


class _FakeResearchApplication:
    def run(
        self,
        snapshot_id: UUID,
        research_type: str,
        policy_version: str,
        as_of: datetime,
    ) -> dict[str, object]:
        return {
            "status": "PARTIAL",
            "snapshot_id": str(snapshot_id),
            "research_type": research_type,
            "policy_version": policy_version,
            "research_as_of_time": as_of.isoformat(),
        }


def test_research_run_requires_explicit_snapshot_type_policy_and_as_of(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_research_pipeline,
        "research_application_factory",
        _FakeResearchApplication,
    )
    result = runner.invoke(
        cli_research_pipeline.research_pipeline_app,
        [
            "run-from-snapshot",
            str(UUID(int=1)),
            "DATA_QUALITY_REVIEW",
            "controlled-offline-v1",
            "2026-08-01T00:00:00Z",
            "--json",
        ],
    )
    assert result.exit_code == 2
    assert "PARTIAL" in result.stdout


def test_research_cli_does_not_offer_latest_refresh_or_network() -> None:
    result = runner.invoke(cli_research_pipeline.research_pipeline_app, ["--help"])
    assert result.exit_code == 0
    assert "run-from-snapshot" in result.stdout
    for forbidden in ("latest", "refresh", "network", "provider"):
        assert forbidden not in result.stdout.lower()
