"""Explicit Stage 5 financial normalization, calculation, and read commands."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Annotated, Any, cast
from uuid import UUID

import typer
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from stock_research_agent.config import Settings
from stock_research_agent.db.repositories.financials import SqlAlchemyFinancialRepository
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.db.session import (
    create_engine_from_settings,
    create_session_factory,
    session_scope,
)
from stock_research_agent.domain.financials.calculation_service import (
    MetricCalculationService,
)
from stock_research_agent.domain.financials.enums import QualityStatus
from stock_research_agent.domain.financials.normalization import (
    FinancialNormalizationService,
)
from stock_research_agent.domain.financials.queries import FinancialQueryService
from stock_research_agent.domain.financials.seed import FinancialReferenceSeedService
from stock_research_agent.domain.securities.enums import ResolutionStatus
from stock_research_agent.domain.securities.resolution import SecurityResolutionService
from stock_research_agent.tools.registry import create_financial_tool_registry
from stock_research_agent.tools.schemas import ToolEnvelope

EXIT_PARTIAL = 2
EXIT_INVALID_INPUT = 4
EXIT_BLOCKED = 5
EXIT_FAIL = 6

financials_app = typer.Typer(
    help="Explicitly normalize/calculate or read persisted financial outputs.",
    no_args_is_help=True,
)
settings_factory = Settings


@dataclass(frozen=True, slots=True)
class _Resources:
    session: Session
    securities: SqlAlchemySecurityMasterRepository
    financials: SqlAlchemyFinancialRepository


@contextmanager
def _resources() -> Iterator[_Resources]:
    engine: Engine | None = None
    try:
        source = settings_factory()
        settings = Settings.model_validate(source.model_dump(warnings=False))
        engine = create_engine_from_settings(settings)
        factory = create_session_factory(engine)
        with session_scope(factory) as session:
            yield _Resources(
                session=session,
                securities=SqlAlchemySecurityMasterRepository(session),
                financials=SqlAlchemyFinancialRepository(session),
            )
    finally:
        if engine is not None:
            engine.dispose()


def _security_id(query: str, resources: _Resources) -> UUID:
    resolution = SecurityResolutionService(resources.securities).resolve(query)
    if resolution.status is not ResolutionStatus.RESOLVED:
        raise ValueError("security query did not resolve uniquely")
    return resolution.candidates[0].security_id


def _verify_snapshot_security(
    security_id: UUID,
    snapshot_id: UUID,
    repository: SqlAlchemyFinancialRepository,
) -> None:
    snapshot = repository.get_snapshot_for_calculation(snapshot_id)
    if snapshot is None or snapshot.security_id != security_id:
        raise ValueError("snapshot does not belong to resolved security")


def _render(value: object, json_output: bool) -> None:
    payload = asdict(cast(Any, value)) if hasattr(value, "__dataclass_fields__") else value
    if json_output:
        typer.echo(json.dumps(payload, indent=2, default=str, ensure_ascii=False))
    else:
        if isinstance(payload, dict):
            for key, item in payload.items():
                typer.echo(f"{key}: {item}")
        else:
            typer.echo(str(payload))


def _exit_for_status(status: QualityStatus) -> None:
    if status is QualityStatus.PARTIAL:
        raise typer.Exit(code=EXIT_PARTIAL)
    if status is QualityStatus.BLOCKED:
        raise typer.Exit(code=EXIT_BLOCKED)
    if status is QualityStatus.FAIL:
        raise typer.Exit(code=EXIT_FAIL)


@financials_app.command("seed-v0")
def seed_v0(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Explicitly seed versioned canonical concepts and formula definitions."""
    try:
        with _resources() as resources:
            result = FinancialReferenceSeedService().seed(resources.financials)
            resources.session.commit()
    except Exception:
        typer.echo("Financial reference seed failed")
        raise typer.Exit(code=EXIT_FAIL) from None
    _render(result, json_output)


@financials_app.command("normalize")
def normalize(
    security_query: Annotated[str, typer.Argument()],
    snapshot_id: Annotated[UUID, typer.Option("--snapshot")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Explicitly normalize only facts already present in one immutable snapshot."""
    try:
        with _resources() as resources:
            security_id = _security_id(security_query, resources)
            _verify_snapshot_security(security_id, snapshot_id, resources.financials)
            result = FinancialNormalizationService().normalize_snapshot(
                snapshot_id, resources.financials
            )
            resources.session.commit()
    except ValueError:
        typer.echo("Financial normalization input invalid")
        raise typer.Exit(code=EXIT_INVALID_INPUT) from None
    except Exception:
        typer.echo("Financial normalization failed")
        raise typer.Exit(code=EXIT_FAIL) from None
    _render(result, json_output)
    _exit_for_status(result.status)


@financials_app.command("calculate")
def calculate(
    security_query: Annotated[str, typer.Argument()],
    snapshot_id: Annotated[UUID, typer.Option("--snapshot")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Explicitly calculate from persisted normalized facts without refreshing data."""
    try:
        with _resources() as resources:
            security_id = _security_id(security_query, resources)
            _verify_snapshot_security(security_id, snapshot_id, resources.financials)
            result = MetricCalculationService().calculate_snapshot(
                snapshot_id, resources.financials
            )
            resources.session.commit()
    except ValueError:
        typer.echo("Financial calculation input invalid")
        raise typer.Exit(code=EXIT_INVALID_INPUT) from None
    except Exception:
        typer.echo("Financial calculation failed")
        raise typer.Exit(code=EXIT_FAIL) from None
    _render(result, json_output)
    _exit_for_status(result.status)


def _read_tool(name: str, payload: dict[str, object], json_output: bool) -> None:
    try:
        with _resources() as resources:
            service = FinancialQueryService(resources.financials)
            result = cast(
                ToolEnvelope[object],
                create_financial_tool_registry(service).execute(name, "1.0.0", payload),
            )
    except Exception:
        typer.echo("Financial query failed")
        raise typer.Exit(code=EXIT_FAIL) from None
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        typer.echo(f"Status: {result.status}")
        for item in result.data:
            rendered = item.model_dump(mode="json") if isinstance(item, BaseModel) else str(item)
            typer.echo(json.dumps(rendered, ensure_ascii=False))
        for warning in result.warnings:
            typer.echo(f"Warning: {warning}")
    if result.status == "PARTIAL":
        raise typer.Exit(code=EXIT_PARTIAL)
    if result.status == "BLOCKED":
        raise typer.Exit(code=EXIT_BLOCKED)
    if result.status == "FAIL":
        raise typer.Exit(code=EXIT_FAIL)


def _snapshot_read_command(
    name: str,
    security_query: str,
    snapshot_id: UUID,
    json_output: bool,
    **filters: object,
) -> None:
    try:
        with _resources() as resources:
            security_id = _security_id(security_query, resources)
            _verify_snapshot_security(security_id, snapshot_id, resources.financials)
    except ValueError:
        typer.echo("Financial query input invalid")
        raise typer.Exit(code=EXIT_INVALID_INPUT) from None
    _read_tool(
        name,
        {"security_id": security_id, "snapshot_id": snapshot_id, **filters},
        json_output,
    )


@financials_app.command("periods")
def periods(
    security_query: Annotated[str, typer.Argument()],
    snapshot_id: Annotated[UUID, typer.Option("--snapshot")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _snapshot_read_command(
        "get_financial_periods", security_query, snapshot_id, json_output, limit=100
    )


@financials_app.command("facts")
def facts(
    security_query: Annotated[str, typer.Argument()],
    snapshot_id: Annotated[UUID, typer.Option("--snapshot")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _snapshot_read_command(
        "get_normalized_financial_facts",
        security_query,
        snapshot_id,
        json_output,
        limit=100,
    )


@financials_app.command("metrics")
def metrics(
    security_query: Annotated[str, typer.Argument()],
    snapshot_id: Annotated[UUID, typer.Option("--snapshot")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _snapshot_read_command(
        "get_financial_metrics", security_query, snapshot_id, json_output, limit=100
    )


@financials_app.command("metric")
def metric(
    security_query: Annotated[str, typer.Argument()],
    metric_code: Annotated[str, typer.Argument()],
    snapshot_id: Annotated[UUID, typer.Option("--snapshot")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _snapshot_read_command(
        "get_metric_detail",
        security_query,
        snapshot_id,
        json_output,
        metric_code=metric_code,
    )


@financials_app.command("lineage")
def lineage(
    calculation_run_id: Annotated[UUID, typer.Argument()],
    metric_code: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _read_tool(
        "get_metric_lineage",
        {"calculation_run_id": calculation_run_id, "metric_code": metric_code},
        json_output,
    )


__all__ = ["financials_app"]
