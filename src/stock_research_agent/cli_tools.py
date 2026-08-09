"""Database-free CLI commands for canonical Tool metadata."""

from __future__ import annotations

import re
from typing import Annotated

import typer

from stock_research_agent.cli_support import StageFourCliGroup
from stock_research_agent.tools.registry import (
    ToolRegistryError,
    create_tool_metadata_registry,
)

tools_app = typer.Typer(
    cls=StageFourCliGroup,
    help="Inspect the canonical read-only Tool catalog.",
    no_args_is_help=True,
)
_SEMANTIC_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_SUPPORTED_VERSION = "1.0.0"


def _invalid_input() -> None:
    typer.echo("Status: INVALID_INPUT")
    raise typer.Exit(code=4)


@tools_app.command("list")
def list_tools(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Render the stable metadata list as JSON."),
    ] = False,
) -> None:
    """List the exact canonical read-only Tool registrations."""
    metadata = create_tool_metadata_registry().list()
    if json_output:
        typer.echo(
            "[\n" + ",\n".join(f"  {item.model_dump_json(indent=2)}" for item in metadata) + "\n]"
        )
        return
    for item in metadata:
        typer.echo(
            f"{item.name} {item.version} | {item.domain} | READ_ONLY | NO_NETWORK | NO_WRITES"
        )


@tools_app.command("describe")
def describe_tool(
    tool_name: Annotated[str, typer.Argument(help="Canonical Tool name.")],
    version: Annotated[
        str,
        typer.Option("--version", help="Exact semantic Tool version."),
    ] = "1.0.0",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Render the stable Tool metadata as JSON."),
    ] = False,
) -> None:
    """Describe one canonical Tool registration without executing it."""
    if _SEMANTIC_VERSION.fullmatch(version) is None or version != _SUPPORTED_VERSION:
        _invalid_input()
    try:
        metadata = create_tool_metadata_registry().describe(tool_name, version)
    except ToolRegistryError:
        typer.echo("Tool was not found")
        raise typer.Exit(code=3) from None
    if json_output:
        typer.echo(metadata.model_dump_json(indent=2))
        return
    typer.echo(f"Name: {metadata.name}")
    typer.echo(f"Version: {metadata.version}")
    typer.echo(f"Domain: {metadata.domain}")
    typer.echo(f"Description: {metadata.description}")
    typer.echo("Permission: READ_ONLY")
    typer.echo("Network: NO_NETWORK")
    typer.echo("Writes: NO_WRITES")


__all__ = ["tools_app"]
