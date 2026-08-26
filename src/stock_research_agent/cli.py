import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy.engine import Engine

from stock_research_agent import __version__
from stock_research_agent.cli_agent import agent_app
from stock_research_agent.cli_data import data_app
from stock_research_agent.cli_documents import documents_app
from stock_research_agent.cli_evidence import evidence_app
from stock_research_agent.cli_financials import financials_app
from stock_research_agent.cli_live import live_app
from stock_research_agent.cli_providers import provider_app
from stock_research_agent.cli_rag import rag_app
from stock_research_agent.cli_reports import report_app
from stock_research_agent.cli_research_pipeline import research_pipeline_app
from stock_research_agent.cli_snapshot_ingestion import snapshot_ingestion_app
from stock_research_agent.cli_tools import tools_app
from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.db.session import (
    check_database,
    create_engine_from_settings,
    create_session_factory,
    session_scope,
)
from stock_research_agent.domain.securities.enums import ResolutionStatus
from stock_research_agent.domain.securities.resolution import SecurityResolutionService
from stock_research_agent.domain.securities.schemas import (
    SecurityDetail,
    SecurityResolutionResult,
)
from stock_research_agent.domain.securities.seed import SecurityMasterSeedService

app = typer.Typer(
    help="Operational commands for the Stock Research Agent backend.",
    no_args_is_help=True,
)
securities_app = typer.Typer(
    help="Seed and resolve deterministic security master data.",
    no_args_is_help=True,
)
app.add_typer(securities_app, name="securities")
app.add_typer(data_app, name="data")
app.add_typer(tools_app, name="tools")
app.add_typer(financials_app, name="financials")
app.add_typer(documents_app, name="documents")
app.add_typer(rag_app, name="rag")
app.add_typer(agent_app, name="agent")
app.add_typer(report_app, name="report")
app.add_typer(provider_app, name="provider")
app.add_typer(live_app, name="live")
app.add_typer(evidence_app, name="evidence")
app.add_typer(snapshot_ingestion_app, name="snapshot-ingestion")
app.add_typer(research_pipeline_app, name="research-pipeline")
settings_factory: Callable[[], Settings] = Settings
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CHECKOUT_ALEMBIC_INI = _PROJECT_ROOT / "alembic.ini"
_ALEMBIC_CONFIG_ENV = "STOCK_RESEARCH_ALEMBIC_CONFIG"


def _load_settings() -> Settings:
    source = settings_factory()
    return Settings.model_validate(source.model_dump(warnings=False))


def _resolve_alembic_config_path() -> Path:
    configured_path = os.environ.get(_ALEMBIC_CONFIG_ENV)
    if configured_path:
        candidate = Path(configured_path)
        if not candidate.is_absolute():
            raise RuntimeError(f"{_ALEMBIC_CONFIG_ENV} must be an absolute path")
    else:
        candidate = _CHECKOUT_ALEMBIC_INI

    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("Alembic configuration file is unavailable") from exc
    if not resolved.is_file():
        raise RuntimeError("Alembic configuration path must be a file")
    return resolved


def _alembic_config(settings: Settings) -> Config:
    config = Config(str(_resolve_alembic_config_path()))
    config.attributes["settings"] = settings
    return config


@contextmanager
def _security_repository(
    settings: Settings,
    *,
    commit_on_success: bool = False,
) -> Iterator[SqlAlchemySecurityMasterRepository]:
    engine: Engine | None = None
    try:
        engine = create_engine_from_settings(settings)
        factory = create_session_factory(engine)
        with session_scope(factory) as session:
            yield SqlAlchemySecurityMasterRepository(session)
            if commit_on_success:
                session.commit()
    finally:
        if engine is not None:
            engine.dispose()


def _render_resolution(result: SecurityResolutionResult, json_output: bool) -> None:
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
        return
    typer.echo(f"Status: {result.status}")
    typer.echo(f"Match: {result.match_type}")
    typer.echo(f"Candidates: {result.candidate_count}")
    for candidate in result.candidates:
        typer.echo(
            f"- {candidate.symbol} | {candidate.exchange_mic} | "
            f"{candidate.issuer_display_name} | {candidate.listing_status}"
        )
    for warning in result.warnings:
        typer.echo(f"Warning: {warning}")


def _resolution_exit_code(status: ResolutionStatus) -> int:
    return {
        ResolutionStatus.RESOLVED: 0,
        ResolutionStatus.AMBIGUOUS: 2,
        ResolutionStatus.NOT_FOUND: 3,
        ResolutionStatus.INVALID_QUERY: 4,
    }[status]


def _render_security(detail: SecurityDetail, json_output: bool) -> None:
    if json_output:
        typer.echo(detail.model_dump_json(indent=2))
        return
    typer.echo(f"Security: {detail.security.display_name}")
    typer.echo(f"Symbol: {detail.security.symbol}")
    typer.echo(f"Exchange: {detail.exchange.mic} ({detail.exchange.name})")
    typer.echo(f"Issuer: {detail.issuer.display_name}")
    typer.echo(f"Currency: {detail.security.currency_code}")
    typer.echo(f"Listing status: {detail.security.listing_status}")


@app.command()
def version() -> None:
    """Print the installed package version."""
    typer.echo(f"stock-research-agent {__version__}")


@app.command("check-config")
def check_config() -> None:
    """Validate configuration without printing its values."""
    try:
        _load_settings()
    except Exception:
        typer.echo("Configuration invalid")
        raise typer.Exit(code=1) from None

    typer.echo("Configuration valid")


@app.command()
def health() -> None:
    """Check configuration and database connectivity."""
    engine: Engine | None = None
    failed = False
    try:
        settings = _load_settings()
        engine = create_engine_from_settings(settings)
        check_database(engine)
    except Exception:
        failed = True
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                failed = True

    if failed:
        typer.echo("Health check failed")
        raise typer.Exit(code=1)

    typer.echo("Health check passed")


@app.command("db-upgrade")
def db_upgrade(
    revision: Annotated[
        str,
        typer.Option("--revision", help="Alembic revision to upgrade to."),
    ] = "head",
) -> None:
    """Upgrade the configured database schema."""
    try:
        settings = _load_settings()
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required")
        alembic_command.upgrade(_alembic_config(settings), revision)
    except Exception:
        typer.echo("Database upgrade failed")
        raise typer.Exit(code=1) from None

    typer.echo("Database upgrade complete")


@app.command("db-downgrade")
def db_downgrade(
    revision: Annotated[
        str,
        typer.Option("--revision", help="Alembic revision to downgrade to."),
    ] = "-1",
    confirm_production: Annotated[
        bool,
        typer.Option(
            "--confirm-production",
            help="Explicitly allow a production database downgrade.",
        ),
    ] = False,
) -> None:
    """Downgrade the configured database schema."""
    try:
        settings = _load_settings()
    except Exception:
        typer.echo("Database downgrade failed")
        raise typer.Exit(code=1) from None

    if settings.app_env == AppEnvironment.PRODUCTION and not confirm_production:
        typer.echo("Production downgrade refused; pass --confirm-production to continue")
        raise typer.Exit(code=1)

    try:
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required")
        alembic_command.downgrade(_alembic_config(settings), revision)
    except Exception:
        typer.echo("Database downgrade failed")
        raise typer.Exit(code=1) from None

    typer.echo("Database downgrade complete")


@securities_app.command("seed-v0")
def securities_seed_v0() -> None:
    """Apply the versioned V0.1 sample master data without overwriting changes."""
    try:
        settings = _load_settings()
        with _security_repository(settings, commit_on_success=True) as repository:
            result = SecurityMasterSeedService().seed(repository)
    except Exception:
        typer.echo("Security seed failed")
        raise typer.Exit(code=1) from None

    typer.echo(
        f"Security seed complete: version={result.version} "
        f"inserted={result.inserted_count} existing={result.existing_count}"
    )


@securities_app.command("resolve")
def securities_resolve(
    query: Annotated[str, typer.Argument(help="Security code, name, or identifier.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Render the stable domain result as JSON."),
    ] = False,
) -> None:
    """Resolve a security identity using deterministic local rules."""
    try:
        settings = _load_settings()
        with _security_repository(settings) as repository:
            result = SecurityResolutionService(repository).resolve(query)
    except Exception:
        typer.echo("Security resolution failed")
        raise typer.Exit(code=1) from None

    _render_resolution(result, json_output)
    exit_code = _resolution_exit_code(result.status)
    if exit_code:
        raise typer.Exit(code=exit_code)


@securities_app.command("show")
def securities_show(
    security_id: Annotated[UUID, typer.Argument(help="Stable security UUID.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Render the security detail as JSON."),
    ] = False,
) -> None:
    """Show security master data without prices, financials, or research."""
    try:
        settings = _load_settings()
        with _security_repository(settings) as repository:
            detail = repository.get_security(security_id)
    except Exception:
        typer.echo("Security lookup failed")
        raise typer.Exit(code=1) from None

    if detail is None:
        typer.echo("Security not found")
        raise typer.Exit(code=3)
    _render_security(detail, json_output)
