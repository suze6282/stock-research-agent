from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from typer.testing import CliRunner

from stock_research_agent import cli_reports

runner = CliRunner()


class _FakeReportApplication:
    export_root = Path(".")

    def invoke(self, operation: str, value: object | None = None) -> object:
        return {"operation": operation, "request": value, "status": "PARTIAL"}


def test_generate_from_package_requires_exact_policy_and_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_reports, "application_factory", _FakeReportApplication)
    result = runner.invoke(
        cli_reports.report_app,
        [
            "generate-from-package",
            str(UUID(int=1)),
            "controlled-report-v1",
            "a" * 64,
            "--type",
            "DATA_QUALITY_REPORT",
            "--json",
        ],
    )
    assert result.exit_code == 2
    assert "generate-from-package" in result.stdout


def test_generate_from_package_has_no_force_publish_option() -> None:
    result = runner.invoke(cli_reports.report_app, ["generate-from-package", "--help"])
    assert result.exit_code == 0
    assert "force" not in result.stdout.lower()
    assert "publish" not in result.stdout.lower()
