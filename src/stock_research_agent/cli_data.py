"""Stage 4 data CLI commands with explicit transaction and offline boundaries."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import typer
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from stock_research_agent.cli_support import StageFourCliGroup
from stock_research_agent.config import Settings
from stock_research_agent.db.repositories.data_access import SqlAlchemyDataAccessRepository
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.db.session import (
    create_engine_from_settings,
    create_session_factory,
    session_scope,
)
from stock_research_agent.domain.data_access.enums import (
    AccessMode,
    DataCategory,
    DataOrigin,
    LiveStatus,
    ProviderCapability,
    QualityStatus,
)
from stock_research_agent.domain.data_access.ingestion import (
    IngestionRequest,
    IngestionResult,
    IngestionService,
)
from stock_research_agent.domain.data_access.provenance import classify_provider_evidence
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.domain.data_access.schemas import (
    DataProviderRecord,
    DataProviderWrite,
    ProviderInstrumentMappingWrite,
)
from stock_research_agent.domain.data_access.snapshots import (
    SnapshotBuilder,
    SnapshotBuildError,
    SnapshotBuildRequest,
    SnapshotBuildResult,
    SnapshotErrorCode,
)
from stock_research_agent.domain.securities.enums import ResolutionStatus
from stock_research_agent.domain.securities.resolution import SecurityResolutionService
from stock_research_agent.domain.securities.schemas import (
    SecurityDetail,
    SecurityResolutionResult,
)
from stock_research_agent.infrastructure.blob_storage import LocalBlobStorage
from stock_research_agent.providers.base import DataProviderAdapter
from stock_research_agent.providers.fixtures import create_stage1_fixture_registry
from stock_research_agent.providers.registry import ProviderRegistry
from stock_research_agent.tools.registry import ToolRegistryError, create_tool_registry
from stock_research_agent.tools.schemas import ToolEnvelope

EXIT_PASS = 0
EXIT_PARTIAL = 2
EXIT_NOT_FOUND = 3
EXIT_INVALID_INPUT = 4
EXIT_BLOCKED = 5
EXIT_FAIL = 6
_DEFAULT_SNAPSHOT_CATEGORIES = (
    DataCategory.DAILY_PRICES,
    DataCategory.FINANCIAL_FACTS,
    DataCategory.FILING_METADATA,
)
_FIXTURE_MARKERS = {
    "data_origin": "FIXTURE",
    "access_mode": "OFFLINE",
    "live_status": "NOT_LIVE",
}

data_app = typer.Typer(
    cls=StageFourCliGroup,
    help="Read persisted evidence or explicitly ingest approved offline fixtures.",
    no_args_is_help=True,
)
snapshot_app = typer.Typer(
    cls=StageFourCliGroup,
    help="Create or show immutable persisted data snapshots.",
    no_args_is_help=True,
)
data_app.add_typer(snapshot_app, name="snapshot")
settings_factory = Settings


@dataclass(frozen=True)
class _DataResources:
    settings: Settings
    session: Session
    securities: SqlAlchemySecurityMasterRepository
    data: SqlAlchemyDataAccessRepository


@dataclass(frozen=True)
class _FixtureSelection:
    adapter: DataProviderAdapter
    registry: ProviderRegistry


def _load_settings() -> Settings:
    source = settings_factory()
    return Settings.model_validate(source.model_dump(warnings=False))


@contextmanager
def _data_resources() -> Iterator[_DataResources]:
    engine: Engine | None = None
    try:
        settings = _load_settings()
        engine = create_engine_from_settings(settings)
        factory = create_session_factory(engine)
        with session_scope(factory) as session:
            yield _DataResources(
                settings=settings,
                session=session,
                securities=SqlAlchemySecurityMasterRepository(session),
                data=SqlAlchemyDataAccessRepository(session),
            )
    finally:
        if engine is not None:
            engine.dispose()


def _parse_aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid aware ISO datetime") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("invalid aware ISO datetime")
    return parsed.astimezone(UTC)


def _parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise ValueError("invalid UUID") from None


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("invalid ISO date") from None


def _parse_category(value: str) -> DataCategory:
    try:
        return DataCategory(value)
    except ValueError:
        raise ValueError("invalid data category") from None


def _invalid_input(*, json_output: bool = False) -> None:
    if json_output:
        typer.echo(json.dumps({"status": "INVALID_INPUT"}, indent=2))
    else:
        typer.echo("Status: INVALID_INPUT")
    raise typer.Exit(code=EXIT_INVALID_INPUT)


def _safe_failure(message: str, *, json_output: bool = False) -> None:
    if json_output:
        typer.echo(json.dumps({"status": "FAIL", "message": message}, indent=2))
    else:
        typer.echo("Status: FAIL")
        typer.echo(f"Message: {message}")
    raise typer.Exit(code=EXIT_FAIL)


def _status_exit(status: str | QualityStatus) -> int:
    value = status.value if isinstance(status, QualityStatus) else status
    return {
        "PASS": EXIT_PASS,
        "COMPLETE": EXIT_PASS,
        "PARTIAL": EXIT_PARTIAL,
        "AMBIGUOUS": EXIT_PARTIAL,
        "NOT_FOUND": EXIT_NOT_FOUND,
        "INVALID_QUERY": EXIT_INVALID_INPUT,
        "BLOCKED": EXIT_BLOCKED,
        "FAIL": EXIT_FAIL,
        "FAILED": EXIT_FAIL,
    }.get(value, EXIT_FAIL)


def _raise_for_status(status: str | QualityStatus) -> None:
    code = _status_exit(status)
    if code:
        raise typer.Exit(code=code)


def _resolve(
    resources: _DataResources,
    query: str,
) -> tuple[SecurityResolutionResult, SecurityDetail | None]:
    result = SecurityResolutionService(resources.securities).resolve(query)
    if result.status is not ResolutionStatus.RESOLVED:
        return result, None
    detail = resources.securities.get_security(result.candidates[0].security_id)
    if detail is None:
        return (
            result.model_copy(
                update={
                    "status": ResolutionStatus.NOT_FOUND,
                    "candidate_count": 0,
                    "candidates": (),
                    "warnings": ("SECURITY_MASTER_DETAIL_NOT_FOUND",),
                }
            ),
            None,
        )
    return result, detail


def _render_resolution_failure(
    result: SecurityResolutionResult,
    *,
    json_output: bool,
) -> None:
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        typer.echo(f"Status: {result.status.value}")
        typer.echo(f"Candidates: {result.candidate_count}")
        for candidate in result.candidates:
            typer.echo(f"- {candidate.symbol} | {candidate.exchange_mic}")
        for warning in result.warnings:
            typer.echo(f"Warning: {warning}")
    _raise_for_status(result.status.value)


def _fixture_selection(
    detail: SecurityDetail,
    category: DataCategory,
) -> _FixtureSelection | None:
    symbol = detail.security.symbol
    mic = detail.exchange.mic
    provider_code: str | None = None
    if (symbol, mic, category) == ("TEST001", "XSHG", DataCategory.DAILY_PRICES):
        provider_code = "STAGE1_SSE_FIXTURE"
    elif (symbol, mic, category) == ("TSTX", "XNAS", DataCategory.DAILY_PRICES):
        provider_code = "STAGE1_NASDAQ_FIXTURE"
    elif (
        symbol == "TSTX"
        and mic == "XNAS"
        and category
        in {
            DataCategory.FILING_METADATA,
            DataCategory.FINANCIAL_FACTS,
        }
    ):
        provider_code = "STAGE1_SEC_FIXTURE"
    if provider_code is None:
        return None
    registry = create_stage1_fixture_registry()
    capability = ProviderCapability(category.value)
    return _FixtureSelection(
        adapter=registry.get(provider_code, required_capability=capability),
        registry=registry,
    )


def _provider_write(adapter: DataProviderAdapter) -> DataProviderWrite:
    descriptor = adapter.descriptor
    terms_status: Literal["RESTRICTED", "NEEDS_REVIEW"] = (
        "RESTRICTED"
        if descriptor.status.value == "APPROVED_FOR_PERSONAL_RESEARCH_ONLY"
        else "NEEDS_REVIEW"
    )
    return DataProviderWrite(
        code=descriptor.code,
        name=descriptor.name,
        provider_type="FIXTURE",
        status=descriptor.status,
        base_url=None,
        documentation_url=None,
        terms_status=terms_status,
        capabilities=tuple(sorted(descriptor.capabilities, key=lambda value: value.value)),
    )


def _same_provider(existing: DataProviderRecord, expected: DataProviderWrite) -> bool:
    return existing.model_dump(
        mode="python",
        exclude={"id", "created_at", "updated_at"},
    ) == expected.model_dump(mode="python")


def _mapping_write(
    provider_id: UUID,
    detail: SecurityDetail,
    adapter: DataProviderAdapter,
) -> ProviderInstrumentMappingWrite:
    return ProviderInstrumentMappingWrite(
        provider_id=provider_id,
        security_id=detail.security.id,
        provider_symbol=detail.security.symbol,
        provider_exchange_code=detail.exchange.mic,
        provider_instrument_id=None,
        valid_from=None,
        valid_to=None,
        is_primary=True,
        metadata={**_FIXTURE_MARKERS, "provider_version": adapter.version},
        source_name=f"Stage 4 CLI fixture bootstrap {adapter.code}",
    )


def _ensure_fixture_bootstrap(
    resources: _DataResources,
    detail: SecurityDetail,
    selection: _FixtureSelection,
    as_of: date,
) -> DataProviderRecord:
    expected_provider = _provider_write(selection.adapter)
    existing_provider = resources.data.get_provider(selection.adapter.code)
    if existing_provider is None:
        provider = resources.data.add_provider(expected_provider)
    elif _same_provider(existing_provider, expected_provider):
        provider = existing_provider
    else:
        raise RuntimeError("fixture provider metadata conflict")

    expected_mapping = _mapping_write(provider.id, detail, selection.adapter)
    existing_mapping = resources.data.get_active_mapping(
        detail.security.id,
        provider.code,
        as_of,
    )
    if existing_mapping is None:
        resources.data.add_provider_mapping(expected_mapping)
    elif (
        existing_mapping.provider_symbol != expected_mapping.provider_symbol
        or existing_mapping.provider_exchange_code != expected_mapping.provider_exchange_code
        or existing_mapping.provider_instrument_id != expected_mapping.provider_instrument_id
    ):
        raise RuntimeError("fixture provider mapping conflict")
    return provider


def _render_ingestion(result: IngestionResult, *, json_output: bool) -> None:
    payload = {
        "run_id": None if result.run_id is None else str(result.run_id),
        "status": result.status,
        "idempotency_key": result.idempotency_key,
        "request_count": result.request_count,
        "records_received": result.records_received,
        "records_stored": result.records_stored,
        "warning_count": result.warning_count,
        "warnings": list(result.warnings),
        "data_origin": None if result.data_origin is None else result.data_origin.value,
        "access_mode": None if result.access_mode is None else result.access_mode.value,
        "live_status": None if result.live_status is None else result.live_status.value,
        "error_code": None if result.error_code is None else result.error_code.value,
        "safe_error_message": result.safe_error_message,
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(f"Status: {result.status}")
    typer.echo(f"Run ID: {payload['run_id']}")
    typer.echo(f"Idempotency key: {result.idempotency_key}")
    typer.echo(
        "Counters: "
        f"requests={result.request_count} received={result.records_received} "
        f"stored={result.records_stored} warnings={result.warning_count}"
    )
    typer.echo(
        f"Provenance: {payload['data_origin']} | {payload['access_mode']} | "
        f"{payload['live_status']}"
    )
    for warning in result.warnings:
        typer.echo(f"Warning: {warning}")
    if result.safe_error_message:
        typer.echo(f"Message: {result.safe_error_message}")


def _snapshot_payload(
    result: SnapshotBuildResult,
    evidence: ToolEnvelope[Any],
) -> dict[str, object]:
    warnings = tuple(dict.fromkeys((*result.warnings, *evidence.warnings)))
    retrieved_at = (
        None
        if evidence.retrieved_at is None
        else evidence.retrieved_at.isoformat().replace("+00:00", "Z")
    )
    return {
        "snapshot_id": str(result.snapshot.id),
        "security_id": str(result.snapshot.security_id),
        "status": result.status,
        "snapshot_version": result.snapshot.snapshot_version,
        "checksum": result.checksum,
        "item_count": len(result.items),
        "warnings": list(warnings),
        "retrieved_at": retrieved_at,
        "data_origin": evidence.provenance.data_origin,
        "access_mode": evidence.provenance.access_mode,
        "live_status": evidence.provenance.live_status,
    }


def _render_snapshot(
    result: SnapshotBuildResult,
    evidence: ToolEnvelope[Any],
    *,
    json_output: bool,
) -> None:
    payload = _snapshot_payload(result, evidence)
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(f"Status: {result.status}")
    typer.echo(f"Snapshot ID: {result.snapshot.id}")
    typer.echo(f"Version: {result.snapshot.snapshot_version}")
    typer.echo(f"Checksum: {result.checksum}")
    typer.echo(f"Items: {len(result.items)}")
    typer.echo(
        f"Provenance: {payload['data_origin']} | {payload['access_mode']} | "
        f"{payload['live_status']}"
    )
    typer.echo(f"Retrieved at: {payload['retrieved_at']}")
    for warning in cast(list[str], payload["warnings"]):
        typer.echo(f"Warning: {warning}")


def _failed_snapshot_was_persisted(
    resources: _DataResources,
    request: SnapshotBuildRequest,
) -> bool:
    terminal = resources.data.get_latest_snapshot_at_as_of(
        request.security_id,
        request.research_as_of_time,
    )
    return (
        terminal is not None
        and terminal.snapshot_version == request.snapshot_version
        and terminal.status == "FAILED"
    )


def _build_snapshot_attempt(
    resources: _DataResources,
    builder: SnapshotBuilder,
    request: SnapshotBuildRequest,
) -> SnapshotBuildResult:
    try:
        return builder.build(request)
    except SnapshotBuildError as error:
        if error.code is SnapshotErrorCode.BUILD_FAILED and _failed_snapshot_was_persisted(
            resources, request
        ):
            resources.session.commit()
        raise


def _validate_scope(
    as_of: str | None,
    snapshot: str | None,
    *,
    json_output: bool,
) -> tuple[datetime | None, UUID | None]:
    if (as_of is None) == (snapshot is None):
        _invalid_input(json_output=json_output)
    try:
        return (
            None if as_of is None else _parse_aware_datetime(as_of),
            None if snapshot is None else _parse_uuid(snapshot),
        )
    except ValueError:
        _invalid_input(json_output=json_output)
    raise AssertionError("unreachable")


def _render_tool_envelope(envelope: ToolEnvelope[Any], *, json_output: bool) -> None:
    if json_output:
        typer.echo(envelope.model_dump_json(indent=2))
        return
    typer.echo(f"Status: {envelope.status}")
    if envelope.snapshot_id is not None:
        typer.echo(f"Scope: snapshot={envelope.snapshot_id}")
    else:
        typer.echo(f"Scope: as-of={envelope.research_as_of_time}")
    typer.echo(
        "Provenance: "
        f"{envelope.provenance.data_origin} | {envelope.provenance.access_mode} | "
        f"{envelope.provenance.live_status}"
    )
    typer.echo(
        "Source IDs: " + (", ".join(str(value) for value in envelope.source_record_ids) or "NONE")
    )
    typer.echo(
        "Provider IDs: " + (", ".join(str(value) for value in envelope.provider_ids) or "NONE")
    )
    for warning in envelope.warnings:
        typer.echo(f"Warning: {warning}")
    for record in envelope.data:
        if isinstance(record, BaseModel):
            typer.echo(record.model_dump_json())


def _execute_tool(
    resources: _DataResources,
    *,
    name: str,
    payload: dict[str, object],
) -> ToolEnvelope[Any]:
    registry = create_tool_registry(DataAccessQueryService(resources.data))
    result = registry.execute(name, "1.0.0", payload)
    return cast(ToolEnvelope[Any], result)


def _provider_marker(provider: DataProviderRecord) -> dict[str, object]:
    markers = classify_provider_evidence(
        provider_type=provider.provider_type,
        status=provider.status,
        terms_status=provider.terms_status,
    )
    return {
        "id": str(provider.id),
        "code": provider.code,
        "name": provider.name,
        "provider_type": provider.provider_type,
        "status": provider.status.value,
        "terms_status": provider.terms_status,
        "capabilities": [value.value for value in provider.capabilities],
        "data_origin": markers.data_origin,
        "access_mode": markers.access_mode,
        "live_status": markers.live_status,
        "warnings": list(markers.warnings),
    }


@data_app.command("providers")
def providers(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Render the bounded safe provider list as JSON."),
    ] = False,
) -> None:
    """List configured provider metadata without credentials, URLs, or paths."""
    try:
        with _data_resources() as resources:
            result = DataAccessQueryService(resources.data).provider_catalog()
            providers = [_provider_marker(provider) for provider in result.records]
            warnings = list(result.warnings)
            if any(provider["warnings"] for provider in providers):
                warnings.append("PROVIDER_CATALOG_CONTAINS_UNVERIFIED_LIVE_STATUS")
            payload = {
                "status": (
                    "PARTIAL"
                    if result.status is QualityStatus.PASS
                    and any(provider["warnings"] for provider in providers)
                    else result.status.value
                ),
                "providers": providers,
                "warnings": list(dict.fromkeys(warnings)),
            }
    except Exception:
        _safe_failure("Provider catalog query failed safely", json_output=json_output)
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(f"Status: {payload['status']}")
        for provider in cast(list[dict[str, object]], payload["providers"]):
            typer.echo(
                f"{provider['code']} | {provider['status']} | "
                f"{provider['data_origin']} | {provider['access_mode']} | "
                f"{provider['live_status']}"
            )
            for warning in cast(list[str], provider["warnings"]):
                typer.echo(f"Warning: {provider['code']}:{warning}")
        for warning in cast(list[str], payload["warnings"]):
            typer.echo(f"Warning: {warning}")
    _raise_for_status(cast(str, payload["status"]))


@data_app.command("mappings")
def mappings(
    query: Annotated[str, typer.Argument(help="Security code, name, or identifier.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Render the bounded safe mapping list as JSON."),
    ] = False,
) -> None:
    """List bounded provider mappings for one deterministically resolved security."""
    try:
        with _data_resources() as resources:
            resolution, detail = _resolve(resources, query)
            if detail is None:
                failure = resolution
                payload = None
            else:
                failure = None
                providers_by_id = {
                    provider.id: provider for provider in resources.data.list_providers(100)
                }
                records = resources.data.list_provider_mappings(detail.security.id, 100)
                safe_mappings = [
                    {
                        "provider_code": providers_by_id[record.provider_id].code,
                        "security_id": str(record.security_id),
                        "provider_symbol": record.provider_symbol,
                        "provider_exchange_code": record.provider_exchange_code,
                        "is_primary": record.is_primary,
                        **_FIXTURE_MARKERS,
                    }
                    for record in records
                    if record.provider_id in providers_by_id
                    and providers_by_id[record.provider_id].provider_type == "FIXTURE"
                ]
                payload = {
                    "status": "PASS" if safe_mappings else "PARTIAL",
                    "mappings": safe_mappings,
                    "warnings": [] if safe_mappings else ["NO_PROVIDER_MAPPINGS"],
                }
    except Exception:
        _safe_failure("Provider mapping query failed safely", json_output=json_output)
    if failure is not None:
        _render_resolution_failure(failure, json_output=json_output)
    assert payload is not None
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(f"Status: {payload['status']}")
        for mapping in cast(list[dict[str, object]], payload["mappings"]):
            typer.echo(
                f"{mapping['provider_code']} | {mapping['provider_symbol']} | "
                f"{mapping['provider_exchange_code']} | FIXTURE | OFFLINE | NOT_LIVE"
            )
        for warning in cast(list[str], payload["warnings"]):
            typer.echo(f"Warning: {warning}")
    _raise_for_status(cast(str, payload["status"]))


@data_app.command("ingest")
def ingest(
    query: Annotated[str, typer.Argument(help="Security code, name, or identifier.")],
    category: Annotated[str, typer.Option("--category", help="Exact DataCategory value.")],
    as_of: Annotated[str, typer.Option("--as-of", help="Aware ISO research cutoff.")],
    fixture: Annotated[
        bool,
        typer.Option("--fixture", help="Explicitly select approved offline fixture evidence."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Render the stable safe ingestion result as JSON."),
    ] = False,
) -> None:
    """Ingest one explicitly selected approved offline fixture."""
    if not fixture:
        payload = {
            "status": "BLOCKED",
            "reason": "LIVE_PROVIDER_NOT_CONFIGURED",
            "data_origin": "LIVE",
            "access_mode": "ONLINE",
            "live_status": "LIVE",
        }
        if json_output:
            typer.echo(json.dumps(payload, indent=2))
        else:
            typer.echo("Status: BLOCKED")
            typer.echo("Mode: LIVE")
            typer.echo("Reason: LIVE_PROVIDER_NOT_CONFIGURED")
        raise typer.Exit(code=EXIT_BLOCKED)
    try:
        parsed_category = _parse_category(category)
        parsed_as_of = _parse_aware_datetime(as_of)
    except ValueError:
        _invalid_input(json_output=json_output)
    try:
        with _data_resources() as resources:
            resolution, detail = _resolve(resources, query)
            if detail is None:
                failure = resolution
                result = None
            else:
                failure = None
                selection = _fixture_selection(detail, parsed_category)
                if selection is None:
                    result = IngestionResult(
                        run_id=None,
                        status="BLOCKED",
                        idempotency_key="ingest:v1:unsupported",
                        request_count=0,
                        records_received=0,
                        records_stored=0,
                        warning_count=1,
                        warnings=("UNSUPPORTED_FIXTURE_COMBINATION",),
                        data_origin=DataOrigin.FIXTURE,
                        access_mode=AccessMode.OFFLINE,
                        live_status=LiveStatus.NOT_LIVE,
                        safe_error_message=(
                            "Fixture security and category combination is unsupported"
                        ),
                    )
                else:
                    _ensure_fixture_bootstrap(
                        resources,
                        detail,
                        selection,
                        parsed_as_of.date(),
                    )
                    blob_storage = LocalBlobStorage(
                        resources.settings.blob_storage_root,
                        max_blob_bytes=resources.settings.provider_max_response_bytes,
                    )
                    try:
                        service = IngestionService(
                            resources.data,
                            selection.registry,
                            blob_storage,
                        )
                        result = service.ingest(
                            IngestionRequest(
                                request_id=uuid4(),
                                security_id=detail.security.id,
                                provider_code=selection.adapter.code,
                                category=parsed_category,
                                research_as_of_time=parsed_as_of,
                                parser_version="1.0.0",
                                schema_version="1.0.0",
                            )
                        )
                    finally:
                        blob_storage.close()
                    if result.status in {"PASS", "PARTIAL", "BLOCKED"}:
                        resources.session.commit()
    except Exception:
        _safe_failure("Fixture ingestion failed safely", json_output=json_output)
    if failure is not None:
        _render_resolution_failure(failure, json_output=json_output)
    assert result is not None
    _render_ingestion(result, json_output=json_output)
    _raise_for_status(result.status)


@snapshot_app.command("create")
def snapshot_create(
    query: Annotated[str, typer.Argument(help="Security code, name, or identifier.")],
    as_of: Annotated[str, typer.Option("--as-of", help="Aware ISO research cutoff.")],
    category: Annotated[
        list[str] | None,
        typer.Option(
            "--category",
            help=("Repeat to replace defaults: DAILY_PRICES, FINANCIAL_FACTS, FILING_METADATA."),
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Render the stable safe snapshot result as JSON."),
    ] = False,
) -> None:
    """Create an immutable snapshot from persisted evidence without fetching."""
    try:
        parsed_as_of = _parse_aware_datetime(as_of)
        categories = (
            _DEFAULT_SNAPSHOT_CATEGORIES
            if not category
            else tuple(_parse_category(value) for value in category)
        )
        if len(set(categories)) != len(categories):
            raise ValueError("duplicate categories")
    except ValueError:
        _invalid_input(json_output=json_output)
    try:
        with _data_resources() as resources:
            resolution, detail = _resolve(resources, query)
            if detail is None:
                failure = resolution
                result = None
            else:
                failure = None
                builder = SnapshotBuilder(resources.data)
                latest = resources.data.get_latest_snapshot_at_as_of(
                    detail.security.id, parsed_as_of
                )
                version = 1 if latest is None else latest.snapshot_version
                request = SnapshotBuildRequest(
                    security_id=detail.security.id,
                    research_as_of_time=parsed_as_of,
                    snapshot_version=version,
                    categories=categories,
                    exchange_timezone=detail.exchange.timezone,
                )
                try:
                    result = _build_snapshot_attempt(resources, builder, request)
                except SnapshotBuildError as error:
                    if error.code is not SnapshotErrorCode.VERSION_CONFLICT or latest is None:
                        raise
                    result = _build_snapshot_attempt(
                        resources,
                        builder,
                        request.model_copy(
                            update={"snapshot_version": latest.snapshot_version + 1}
                        ),
                    )
                evidence = _execute_tool(
                    resources,
                    name="get_data_snapshot",
                    payload={"snapshot_id": result.snapshot.id},
                )
                if (
                    evidence.status is QualityStatus.FAIL
                    or evidence.snapshot_id != result.snapshot.id
                    or not evidence.data
                ):
                    raise RuntimeError("snapshot evidence projection failed")
                resources.session.commit()
    except SnapshotBuildError:
        _safe_failure("Snapshot creation failed safely", json_output=json_output)
    except Exception:
        _safe_failure("Snapshot creation failed safely", json_output=json_output)
    if failure is not None:
        _render_resolution_failure(failure, json_output=json_output)
    assert result is not None
    _render_snapshot(result, evidence, json_output=json_output)
    _raise_for_status(result.status)


@snapshot_app.command("show")
def snapshot_show(
    snapshot_id: Annotated[str, typer.Argument(help="Stable snapshot UUID.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Render the exact stable Tool envelope as JSON."),
    ] = False,
) -> None:
    """Show one persisted snapshot through the approved read-only Tool."""
    try:
        parsed_id = _parse_uuid(snapshot_id)
    except ValueError:
        _invalid_input(json_output=json_output)
    try:
        with _data_resources() as resources:
            envelope = _execute_tool(
                resources,
                name="get_data_snapshot",
                payload={"snapshot_id": parsed_id},
            )
    except (ToolRegistryError, Exception):
        _safe_failure("Snapshot query failed safely", json_output=json_output)
    _render_tool_envelope(envelope, json_output=json_output)
    _raise_for_status(envelope.status)


def _query_command(
    *,
    query: str,
    as_of: str | None,
    snapshot: str | None,
    tool_name: str,
    json_output: bool,
    extra_payload: dict[str, object] | None = None,
) -> None:
    parsed_as_of, parsed_snapshot = _validate_scope(as_of, snapshot, json_output=json_output)
    try:
        with _data_resources() as resources:
            resolution, detail = _resolve(resources, query)
            if detail is None:
                failure = resolution
                envelope = None
            else:
                failure = None
                payload: dict[str, object] = {
                    "security_id": detail.security.id,
                    "research_as_of_time": parsed_as_of,
                    "snapshot_id": parsed_snapshot,
                    **(extra_payload or {}),
                }
                if parsed_as_of is not None and tool_name in {
                    "get_latest_close",
                    "get_daily_price_history",
                }:
                    payload.setdefault(
                        "local_trading_date",
                        parsed_as_of.astimezone(ZoneInfo(detail.exchange.timezone)).date(),
                    )
                envelope = _execute_tool(resources, name=tool_name, payload=payload)
    except Exception:
        _safe_failure("Data query failed safely", json_output=json_output)
    if failure is not None:
        _render_resolution_failure(failure, json_output=json_output)
    assert envelope is not None
    _render_tool_envelope(envelope, json_output=json_output)
    _raise_for_status(envelope.status)


@data_app.command("latest-close")
def latest_close(
    query: Annotated[str, typer.Argument(help="Security code, name, or identifier.")],
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    snapshot: Annotated[str | None, typer.Option("--snapshot")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Read one persisted latest close under an exact as-of or snapshot scope."""
    _query_command(
        query=query,
        as_of=as_of,
        snapshot=snapshot,
        tool_name="get_latest_close",
        json_output=json_output,
    )


@data_app.command("price-history")
def price_history(
    query: Annotated[str, typer.Argument(help="Security code, name, or identifier.")],
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    snapshot: Annotated[str | None, typer.Option("--snapshot")] = None,
    date_from: Annotated[str | None, typer.Option("--date-from")] = None,
    date_to: Annotated[str | None, typer.Option("--date-to")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 100,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Read bounded persisted price history under an exact point-in-time scope."""
    try:
        parsed_from = _parse_date(date_from)
        parsed_to = _parse_date(date_to)
        if parsed_from is not None and parsed_to is not None and parsed_to < parsed_from:
            raise ValueError("invalid date range")
    except ValueError:
        _invalid_input(json_output=json_output)
    payload: dict[str, object] = {"limit": limit}
    if parsed_from is not None:
        payload["date_from"] = parsed_from
    if parsed_to is not None:
        payload["local_trading_date"] = parsed_to
    _query_command(
        query=query,
        as_of=as_of,
        snapshot=snapshot,
        tool_name="get_daily_price_history",
        json_output=json_output,
        extra_payload=payload,
    )


@data_app.command("financial-facts")
def financial_facts(
    query: Annotated[str, typer.Argument(help="Security code, name, or identifier.")],
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    snapshot: Annotated[str | None, typer.Option("--snapshot")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 100,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Read bounded persisted raw reported financial facts."""
    _query_command(
        query=query,
        as_of=as_of,
        snapshot=snapshot,
        tool_name="get_reported_financial_facts",
        json_output=json_output,
        extra_payload={"limit": limit},
    )


@data_app.command("documents")
def documents(
    query: Annotated[str, typer.Argument(help="Security code, name, or identifier.")],
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    snapshot: Annotated[str | None, typer.Option("--snapshot")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 100,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Read bounded persisted source-document metadata without downloading."""
    _query_command(
        query=query,
        as_of=as_of,
        snapshot=snapshot,
        tool_name="list_source_documents",
        json_output=json_output,
        extra_payload={"limit": limit},
    )


__all__ = ["data_app"]
