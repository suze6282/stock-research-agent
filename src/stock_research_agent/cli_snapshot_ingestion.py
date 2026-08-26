"""Explicit Snapshot creation from a persisted ingestion plan."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Annotated, Protocol
from uuid import UUID

import typer

snapshot_ingestion_app = typer.Typer(help="Plan or create a Snapshot from governed ingestion.")


class SnapshotCliApplication(Protocol):
    def operate(self, operation: str, plan_id: UUID, checksum: str) -> dict[str, object]: ...


def _unconfigured() -> SnapshotCliApplication:
    raise RuntimeError("SNAPSHOT_APPLICATION_NOT_CONFIGURED")


snapshot_application_factory: Callable[[], SnapshotCliApplication] = _unconfigured


def _operate(operation: str, plan_id: UUID, checksum: str, json_output: bool) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", checksum) is None:
        raise typer.BadParameter("plan checksum must be lowercase sha256")
    try:
        payload = snapshot_application_factory().operate(operation, plan_id, checksum)
    except Exception:
        typer.echo("SNAPSHOT_PLAN_REQUIRED")
        raise typer.Exit(code=3) from None
    typer.echo(json.dumps(payload, sort_keys=True) if json_output else str(payload))


@snapshot_ingestion_app.command("plan-from-ingestion")
def plan_from_ingestion(
    plan_id: Annotated[UUID, typer.Argument()],
    plan_checksum: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _operate("plan", plan_id, plan_checksum, json_output)


@snapshot_ingestion_app.command("create-from-ingestion")
def create_from_ingestion(
    plan_id: Annotated[UUID, typer.Argument()],
    plan_checksum: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _operate("create", plan_id, plan_checksum, json_output)
