"""Explicit Gate A Research Run command over an exact Snapshot."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Protocol
from uuid import UUID

import typer

from stock_research_agent.cli_datetime import parse_aware_datetime
from stock_research_agent.domain.research_agent.requests import ResearchRequestError

research_pipeline_app = typer.Typer(help="Run offline research from an exact Snapshot.")


class ResearchPipelineCliApplication(Protocol):
    def run(
        self,
        snapshot_id: UUID,
        research_type: str,
        policy_version: str,
        as_of: datetime,
    ) -> dict[str, object]: ...


def _production_application() -> ResearchPipelineCliApplication:
    from stock_research_agent.research_pipeline_application import (
        create_research_pipeline_cli_application,
    )

    return create_research_pipeline_cli_application()


research_application_factory: Callable[[], ResearchPipelineCliApplication] = _production_application


@research_pipeline_app.callback()
def research_pipeline_root() -> None:
    """Require an explicit research-pipeline subcommand."""


@research_pipeline_app.command("run-from-snapshot")
def run_from_snapshot(
    snapshot_id: Annotated[UUID, typer.Argument()],
    research_type: Annotated[str, typer.Argument()],
    policy_version: Annotated[str, typer.Argument()],
    as_of: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        parsed_as_of = parse_aware_datetime(as_of)
    except ValueError:
        typer.echo("AS_OF_MUST_BE_AWARE_ISO_8601")
        raise typer.Exit(code=2) from None
    try:
        payload = research_application_factory().run(
            snapshot_id,
            research_type,
            policy_version,
            parsed_as_of,
        )
    except ResearchRequestError as exc:
        typer.echo(exc.code)
        raise typer.Exit(code=3) from None
    except Exception:
        typer.echo("AGENT_PLAN_REQUIRED")
        raise typer.Exit(code=3) from None
    typer.echo(json.dumps(payload, sort_keys=True) if json_output else str(payload))
    if payload.get("status") == "PARTIAL":
        raise typer.Exit(code=2)
    if payload.get("status") == "BLOCKED":
        raise typer.Exit(code=3)
