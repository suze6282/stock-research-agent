"""Explicit offline manual-evidence intake commands."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import PurePath, PureWindowsPath
from typing import Annotated, Protocol
from uuid import UUID

import typer

evidence_app = typer.Typer(help="Import and review offline manual evidence explicitly.")


class EvidenceCliApplication(Protocol):
    def operate(
        self,
        operation: str,
        request_id: UUID,
        value: str | None,
    ) -> dict[str, object]: ...


def _unconfigured() -> EvidenceCliApplication:
    raise RuntimeError("MANUAL_EVIDENCE_APPLICATION_NOT_CONFIGURED")


evidence_application_factory: Callable[[], EvidenceCliApplication] = _unconfigured


def _relative_name(value: str) -> str:
    windows = PureWindowsPath(value)
    generic = PurePath(value)
    if windows.is_absolute() or generic.is_absolute() or ".." in windows.parts:
        raise typer.BadParameter("file must be an inbox-relative name")
    return value


def _operate(operation: str, request_id: UUID, value: str | None, json_output: bool) -> None:
    try:
        if operation == "import-file" and value is not None:
            value = _relative_name(value)
        payload = evidence_application_factory().operate(operation, request_id, value)
    except typer.BadParameter:
        raise
    except Exception:
        typer.echo("Manual evidence operation blocked")
        raise typer.Exit(code=3) from None
    if json_output:
        typer.echo(json.dumps(payload, sort_keys=True))
    else:
        for key, item in payload.items():
            typer.echo(f"{key}: {item}")


def _command(operation: str) -> Callable[..., None]:
    def command(
        request_id: Annotated[UUID, typer.Argument()],
        value: Annotated[str | None, typer.Argument()] = None,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        _operate(operation, request_id, value, json_output)

    command.__name__ = operation.replace("-", "_")
    return evidence_app.command(operation)(command)


for _operation in ("import-plan", "import-file", "validate", "approve", "reject", "show"):
    _command(_operation)
