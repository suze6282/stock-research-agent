from __future__ import annotations

from uuid import UUID

import pytest
from typer.testing import CliRunner

from stock_research_agent import cli_snapshot_ingestion

runner = CliRunner()


class _FakeSnapshotApplication:
    def operate(self, operation: str, plan_id: UUID, checksum: str) -> dict[str, object]:
        return {
            "operation": operation,
            "plan_id": str(plan_id),
            "plan_checksum": checksum,
            "status": "COMPLETE",
        }


def test_snapshot_create_requires_exact_plan_id_and_checksum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_snapshot_ingestion,
        "snapshot_application_factory",
        _FakeSnapshotApplication,
    )
    result = runner.invoke(
        cli_snapshot_ingestion.snapshot_ingestion_app,
        ["create-from-ingestion", str(UUID(int=1)), "a" * 64, "--json"],
    )
    assert result.exit_code == 0
    assert "COMPLETE" in result.stdout


def test_snapshot_cli_has_no_latest_shortcut() -> None:
    result = runner.invoke(cli_snapshot_ingestion.snapshot_ingestion_app, ["--help"])
    assert result.exit_code == 0
    assert "plan-from-ingestion" in result.stdout
    assert "create-from-ingestion" in result.stdout
    assert "latest" not in result.stdout.lower()
