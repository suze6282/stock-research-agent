"""Narrow safe Click behavior shared by Stage 4 CLI groups."""

from __future__ import annotations

import typer
from typer._click.core import Context
from typer._click.exceptions import UsageError
from typer.core import TyperGroup


class StageFourCliGroup(TyperGroup):
    """Translate only nested Stage 4 parser errors to the Stage 4 exit contract."""

    def invoke(self, ctx: Context) -> object:
        try:
            return super().invoke(ctx)
        except UsageError:
            typer.echo("Status: INVALID_INPUT")
            raise typer.Exit(code=4) from None


__all__ = ["StageFourCliGroup"]
