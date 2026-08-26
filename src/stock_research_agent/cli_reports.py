"""Explicit offline CLI for verifiable report workflows and reads."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, Protocol, cast
from uuid import UUID

import typer
from pydantic import BaseModel

from stock_research_agent.domain.reports.application import (
    GenerateReportCommand,
    ReflectReportCommand,
    ReleaseCheckCommand,
    ReviseReportCommand,
)
from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.enums import ReportLocale, ReportType

EXIT_PARTIAL = 2
EXIT_BLOCKED = 3
EXIT_FAILED = 4

report_app = typer.Typer(
    help="Explicitly generate, inspect, reflect, revise, or gate persisted reports.",
    no_args_is_help=True,
)
policy_app = typer.Typer(help="Manage fixed report policies.", no_args_is_help=True)
reflection_policy_app = typer.Typer(
    help="Manage fixed runtime Reflection policies.",
    no_args_is_help=True,
)
template_app = typer.Typer(help="Manage fixed data-only report templates.", no_args_is_help=True)
report_app.add_typer(policy_app, name="policy")
report_app.add_typer(reflection_policy_app, name="reflection-policy")
report_app.add_typer(template_app, name="template")


class ReportCliApplication(Protocol):
    export_root: Path

    def invoke(
        self,
        operation: str,
        value: object | None = None,
    ) -> object: ...


def _production_application() -> ReportCliApplication:
    from stock_research_agent.report_cli_application import (
        create_report_cli_application,
    )

    return create_report_cli_application()


application_factory: Callable[[], ReportCliApplication] = _production_application


def _render(value: object, json_output: bool) -> None:
    if isinstance(value, BaseModel):
        payload: object = value.model_dump(mode="json")
    else:
        payload = value
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    elif isinstance(payload, dict):
        for key, item in payload.items():
            typer.echo(f"{key}: {item}")
    else:
        typer.echo(str(payload))


def _status_exit(value: object) -> None:
    if not isinstance(value, dict):
        return
    status = str(value.get("status", value.get("internal_release_status", "")))
    if status == "PARTIAL":
        raise typer.Exit(code=EXIT_PARTIAL)
    if status == "BLOCKED":
        raise typer.Exit(code=EXIT_BLOCKED)
    if status in {"FAILED", "INVALID"}:
        raise typer.Exit(code=EXIT_FAILED)


def _invoke(
    operation: str,
    value: object | None,
    json_output: bool,
) -> None:
    try:
        result = application_factory().invoke(operation, value)
    except Exception:
        typer.echo("Report operation failed")
        raise typer.Exit(code=EXIT_FAILED) from None
    _render(result, json_output)
    _status_exit(result)


def _admin_command(operation: str, json_output: bool) -> None:
    _invoke(operation, None, json_output)


@policy_app.command("seed-v1")
def policy_seed(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _admin_command("policy-seed-v1", json_output)


@policy_app.command("list")
def policy_list(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _admin_command("policy-list", json_output)


@reflection_policy_app.command("seed-v1")
def reflection_policy_seed(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _admin_command("reflection-policy-seed-v1", json_output)


@reflection_policy_app.command("list")
def reflection_policy_list(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _admin_command("reflection-policy-list", json_output)


@template_app.command("seed-v1")
def template_seed(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _admin_command("template-seed-v1", json_output)


@template_app.command("list")
def template_list(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _admin_command("template-list", json_output)


@report_app.command("generate")
def generate(
    package_id: Annotated[UUID, typer.Argument()],
    report_type: Annotated[ReportType, typer.Option("--type")],
    locale: Annotated[ReportLocale, typer.Option("--locale")] = ReportLocale.ZH_CN,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _invoke(
        "generate",
        GenerateReportCommand(
            research_package_id=package_id,
            report_type=report_type,
            report_locale=locale,
        ),
        json_output,
    )


@report_app.command("generate-from-package")
def generate_from_package(
    package_id: Annotated[UUID, typer.Argument()],
    policy_version: Annotated[str, typer.Argument()],
    plan_checksum: Annotated[str, typer.Argument()],
    report_type: Annotated[ReportType, typer.Option("--type")],
    locale: Annotated[ReportLocale, typer.Option("--locale")] = ReportLocale.ZH_CN,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", plan_checksum) is None:
        raise typer.BadParameter("plan checksum must be lowercase sha256")
    _invoke(
        "generate-from-package",
        {
            "research_package_id": package_id,
            "policy_version": policy_version,
            "plan_checksum": plan_checksum,
            "report_type": report_type.value,
            "report_locale": locale.value,
        },
        json_output,
    )


@report_app.command("reflect")
def reflect(
    report_id: Annotated[UUID, typer.Argument()],
    round_number: Annotated[int, typer.Option("--round", min=1, max=2)],
    prior_reflection_run_id: Annotated[
        UUID | None,
        typer.Option("--prior-reflection-run"),
    ] = None,
    revision_run_id: Annotated[
        UUID | None,
        typer.Option("--revision-run"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        command = ReflectReportCommand(
            report_id=report_id,
            round_number=cast(Literal[1, 2], round_number),
            prior_reflection_run_id=prior_reflection_run_id,
            revision_run_id=revision_run_id,
        )
    except ValueError:
        typer.echo("Report Reflection input invalid")
        raise typer.Exit(code=EXIT_FAILED) from None
    _invoke("reflect", command, json_output)


@report_app.command("revise")
def revise(
    report_id: Annotated[UUID, typer.Argument()],
    reflection_run_id: Annotated[UUID, typer.Option("--reflection-run")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _invoke(
        "revise",
        ReviseReportCommand(
            report_id=report_id,
            reflection_run_id=reflection_run_id,
        ),
        json_output,
    )


@report_app.command("release-check")
def release_check(
    report_id: Annotated[UUID, typer.Argument()],
    reflection_run_id: Annotated[UUID, typer.Option("--reflection-run")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _invoke(
        "release-check",
        ReleaseCheckCommand(
            report_id=report_id,
            reflection_run_id=reflection_run_id,
        ),
        json_output,
    )


def _read_command(
    operation: str,
    report_id: UUID,
    json_output: bool,
) -> None:
    _invoke(operation, report_id, json_output)


@report_app.command("show")
def show(
    report_id: Annotated[UUID, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _read_command("show", report_id, json_output)


def _register_simple_read(name: str) -> None:
    def command(
        report_id: Annotated[UUID, typer.Argument()],
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        _read_command(name, report_id, json_output)

    command.__name__ = name.replace("-", "_")
    report_app.command(name)(command)


for _read_name in (
    "sections",
    "claims",
    "evidence",
    "citations",
    "findings",
    "versions",
):
    _register_simple_read(_read_name)


def _safe_export_target(root: Path, relative_name: str) -> Path:
    if not relative_name or Path(relative_name).is_absolute() or ":" in relative_name:
        raise ValueError("REPORT_EXPORT_PATH_INVALID")
    root = root.resolve(strict=True)
    target = (root / relative_name).resolve(strict=False)
    if not target.is_relative_to(root) or target == root:
        raise ValueError("REPORT_EXPORT_PATH_INVALID")
    return target


@report_app.command("export-markdown")
def export_markdown(
    report_id: Annotated[UUID, typer.Argument()],
    filename: Annotated[str, typer.Argument()],
    overwrite: Annotated[bool, typer.Option("--overwrite")] = False,
) -> None:
    try:
        application = application_factory()
        value = application.invoke("show", report_id)
        if not isinstance(value, dict):
            raise ValueError("REPORT_EXPORT_RECORD_INVALID")
        markdown = value.get("markdown_content")
        checksum = value.get("markdown_checksum")
        if not isinstance(markdown, str) or not isinstance(checksum, str):
            raise ValueError("REPORT_EXPORT_RECORD_INVALID")
        encoded = markdown.encode("utf-8")
        if report_checksum(markdown) != checksum:
            raise ValueError("REPORT_EXPORT_CHECKSUM_MISMATCH")
        target = _safe_export_target(application.export_root, filename)
        if target.exists() and not overwrite:
            raise FileExistsError("REPORT_EXPORT_EXISTS")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        if target.read_bytes() != encoded:
            raise OSError("REPORT_EXPORT_VERIFY_FAILED")
    except Exception:
        typer.echo("Report export failed")
        raise typer.Exit(code=EXIT_FAILED) from None
    typer.echo(f"Report export complete: {filename}")


__all__ = ["ReportCliApplication", "application_factory", "report_app"]
