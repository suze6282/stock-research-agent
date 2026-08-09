from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from stock_research_agent import cli_reports
from stock_research_agent.cli import app
from stock_research_agent.domain.reports.application import (
    GenerateReportCommand,
    ReflectReportCommand,
    ReleaseCheckCommand,
    ReportGenerationService,
    ReportReflectionService,
    ReportReleaseService,
    ReportRevisionService,
    ReviseReportCommand,
)
from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.enums import ReportLocale, ReportType

REPORT_ID = UUID("00000000-0000-0000-0000-000000008001")
PACKAGE_ID = UUID("00000000-0000-0000-0000-000000008002")
REFLECTION_ID = UUID("00000000-0000-0000-0000-000000008003")
REVISION_ID = UUID("00000000-0000-0000-0000-000000008004")


@dataclass
class FakeUnitOfWork:
    commits: int = 0
    rollbacks: int = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


@dataclass
class FakeWorkflow:
    result: object = field(default_factory=lambda: {"status": "COMPLETED"})
    error: Exception | None = None
    commands: list[object] = field(default_factory=list)

    def execute(self, command: object) -> object:
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.parametrize(
    ("service_type", "command"),
    [
        (
            ReportGenerationService,
            GenerateReportCommand(
                research_package_id=PACKAGE_ID,
                report_type=ReportType.DATA_QUALITY_REPORT,
                report_locale=ReportLocale.ZH_CN,
            ),
        ),
        (
            ReportReflectionService,
            ReflectReportCommand(report_id=REPORT_ID, round_number=1),
        ),
        (
            ReportRevisionService,
            ReviseReportCommand(
                report_id=REPORT_ID,
                reflection_run_id=REFLECTION_ID,
            ),
        ),
        (
            ReportReleaseService,
            ReleaseCheckCommand(
                report_id=REPORT_ID,
                reflection_run_id=REFLECTION_ID,
            ),
        ),
    ],
)
def test_write_services_own_commit_and_rollback(
    service_type: type[Any],
    command: object,
) -> None:
    successful_workflow = FakeWorkflow()
    successful_uow = FakeUnitOfWork()
    result = service_type(successful_workflow, successful_uow).run(command)
    assert result == {"status": "COMPLETED"}
    assert successful_uow.commits == 1
    assert successful_uow.rollbacks == 0

    failed_workflow = FakeWorkflow(error=RuntimeError("safe test failure"))
    failed_uow = FakeUnitOfWork()
    with pytest.raises(RuntimeError, match="safe test failure"):
        service_type(failed_workflow, failed_uow).run(command)
    assert failed_uow.commits == 0
    assert failed_uow.rollbacks == 1


def test_reflection_commands_require_explicit_finite_predecessors() -> None:
    with pytest.raises(ValidationError, match="round 1"):
        ReflectReportCommand(
            report_id=REPORT_ID,
            round_number=1,
            prior_reflection_run_id=REFLECTION_ID,
        )
    with pytest.raises(ValidationError, match="round 2"):
        ReflectReportCommand(report_id=REPORT_ID, round_number=2)
    with pytest.raises(ValidationError):
        ReflectReportCommand.model_validate(
            {
                "report_id": REPORT_ID,
                "round_number": 3,
            }
        )


class FakeCliApplication:
    def __init__(self, export_root: Path) -> None:
        self.export_root = export_root
        self.calls: list[tuple[str, object]] = []

    def invoke(self, operation: str, value: object | None = None) -> object:
        self.calls.append((operation, value))
        if operation == "show":
            return {
                "id": str(REPORT_ID),
                "status": "PARTIAL",
                "markdown_content": "# Verified\n",
                "markdown_checksum": report_checksum("# Verified\n"),
            }
        return {"status": "COMPLETED", "operation": operation}


def test_cli_exposes_only_explicit_report_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application = FakeCliApplication(tmp_path)
    monkeypatch.setattr(cli_reports, "application_factory", lambda: application)
    runner = CliRunner()

    help_result = runner.invoke(app, ["report", "--help"])
    assert help_result.exit_code == 0
    for command in (
        "policy",
        "reflection-policy",
        "template",
        "generate",
        "reflect",
        "revise",
        "release-check",
        "show",
        "sections",
        "claims",
        "evidence",
        "citations",
        "findings",
        "versions",
        "export-markdown",
    ):
        assert command in help_result.stdout
    for prohibited in ("pipeline", "latest", "publish", "model", "refresh"):
        assert prohibited not in help_result.stdout.casefold()

    result = runner.invoke(
        app,
        [
            "report",
            "generate",
            str(PACKAGE_ID),
            "--type",
            "DATA_QUALITY_REPORT",
            "--locale",
            "zh-CN",
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["operation"] == "generate"
    operation, command = application.calls[-1]
    assert operation == "generate"
    assert command.research_package_id == PACKAGE_ID


def test_installed_cli_uses_the_production_application_factory() -> None:
    assert cli_reports.application_factory.__name__ == "_production_application"


def test_export_is_approved_root_only_checksum_verified_and_no_overwrite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application = FakeCliApplication(tmp_path)
    monkeypatch.setattr(cli_reports, "application_factory", lambda: application)
    runner = CliRunner()

    success = runner.invoke(
        app,
        ["report", "export-markdown", str(REPORT_ID), "exports/report.md"],
    )
    assert success.exit_code == 0
    target = tmp_path / "exports" / "report.md"
    assert target.read_bytes() == b"# Verified\n"

    refused = runner.invoke(
        app,
        ["report", "export-markdown", str(REPORT_ID), "exports/report.md"],
    )
    assert refused.exit_code == 4
    assert target.read_bytes() == b"# Verified\n"

    traversal = runner.invoke(
        app,
        ["report", "export-markdown", str(REPORT_ID), "../escape.md"],
    )
    assert traversal.exit_code == 4
    assert not (tmp_path.parent / "escape.md").exists()
