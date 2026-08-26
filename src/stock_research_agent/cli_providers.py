"""Read-only CLI for persisted Provider governance metadata."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Annotated, Literal, Protocol
from uuid import UUID

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from stock_research_agent.config import Settings
from stock_research_agent.db.models.providers import ProviderAuditEvent
from stock_research_agent.db.repositories.providers import (
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
    SqlAlchemyProviderQueryRepository,
    SqlAlchemyProviderSyncRepository,
)
from stock_research_agent.db.session import (
    create_engine_from_settings,
    create_session_factory,
    session_scope,
)
from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderDefinitionStatus,
    ProviderLicenseStatus,
    ProviderRunStatus,
)
from stock_research_agent.domain.providers.licenses import LicensePermission
from stock_research_agent.domain.providers.queries import (
    PageRequest,
    ProviderQueryPage,
    ProviderQueryService,
    SafeProviderProjection,
)
from stock_research_agent.domain.providers.sync import (
    ProviderExecutionMode,
    ProviderRunTransition,
    ProviderSyncPlanWrite,
    ProviderSyncRequestWrite,
    ProviderSyncRunWrite,
)
from stock_research_agent.providers.control_plane import (
    ProviderSyncControlCommand,
    ProviderSyncControlService,
)
from stock_research_agent.providers.sec_edgar.bootstrap import (
    SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP,
    SecProviderControlPlaneBootstrapApplication,
    SecProviderControlPlaneBootstrapConflict,
)

EXIT_NOT_FOUND = 3
EXIT_FAILED = 4

provider_app = typer.Typer(
    help="Read persisted Provider governance metadata without probing or syncing.",
    no_args_is_help=True,
)
Limit = Annotated[int, typer.Option("--limit", min=1, max=100)]
Offset = Annotated[int, typer.Option("--offset", min=0, max=100_000)]
JsonOutput = Annotated[bool, typer.Option("--json")]


class ProviderCliApplication(Protocol):
    def invoke(
        self,
        operation: str,
        identity: str | UUID | None,
        page: PageRequest,
    ) -> SafeProviderProjection | ProviderQueryPage | None: ...

    def control(self, command: ProviderControlCommand) -> dict[str, object]: ...


class ProviderControlCommand(BaseModel):
    """Validated finite intent for one explicit Provider control command."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation: Literal[
        "credential-check",
        "sync-plan",
        "sync-run",
        "sync-pause",
        "sync-resume",
        "sync-cancel",
        "repair",
        "live-check",
    ]
    provider_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    capability_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    provider_version: str | None = Field(default=None, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    capability_version: str | None = Field(default=None, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    policy_version: str | None = Field(default=None, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    license_version: str | None = Field(default=None, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    security_id: UUID | None = None
    universe_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    research_as_of_time: datetime | None = None
    range_start: date | None = None
    range_end: date | None = None
    max_requests: int | None = Field(default=None, ge=1, le=10_000)
    max_bytes: int | None = Field(default=None, ge=1, le=10_737_418_240)
    max_attempts: int | None = Field(default=None, ge=1, le=3)
    max_duration_seconds: int | None = Field(default=None, ge=1, le=86_400)
    run_id: UUID | None = None
    sync_request_id: UUID | None = None
    sync_plan_id: UUID | None = None
    provider_definition_id: UUID | None = None
    provider_capability_id: UUID | None = None
    dead_letter_id: UUID | None = None
    confirmed: bool

    @model_validator(mode="after")
    def validate_exact_control_scope(self) -> ProviderControlCommand:
        if not self.confirmed:
            raise ValueError("PROVIDER_CONTROL_CONFIRMATION_REQUIRED")
        if self.operation == "credential-check":
            self._require("provider_code", "provider_version")
        elif self.operation in {"sync-plan", "sync-run"}:
            self._require(
                "provider_code",
                "capability_code",
                "provider_version",
                "capability_version",
                "policy_version",
                "license_version",
                "research_as_of_time",
                "range_start",
                "range_end",
                "max_requests",
                "max_bytes",
                "max_attempts",
                "max_duration_seconds",
            )
            if (self.security_id is None) == (self.universe_code is None):
                raise ValueError("PROVIDER_CONTROL_EXACT_SCOPE_REQUIRED")
            if self.universe_code == "LATEST":
                raise ValueError("PROVIDER_CONTROL_LATEST_FORBIDDEN")
            if self.research_as_of_time is None or self.research_as_of_time.tzinfo is None:
                raise ValueError("PROVIDER_CONTROL_AWARE_AS_OF_REQUIRED")
            if self.range_start is None or self.range_end is None:
                raise ValueError("PROVIDER_CONTROL_RANGE_REQUIRED")
            if self.range_end < self.range_start:
                raise ValueError("PROVIDER_CONTROL_RANGE_INVALID")
            if self.range_end > self.research_as_of_time.date():
                raise ValueError("PROVIDER_CONTROL_FUTURE_DATA_FORBIDDEN")
        elif self.operation in {"sync-pause", "sync-resume", "sync-cancel"}:
            self._require(
                "run_id",
                "sync_request_id",
                "sync_plan_id",
                "provider_definition_id",
                "provider_capability_id",
            )
        elif self.operation == "repair":
            self._require("dead_letter_id", "provider_definition_id")
        elif self.operation == "live-check":
            self._require(
                "provider_code",
                "capability_code",
                "provider_version",
                "capability_version",
                "max_requests",
                "max_bytes",
            )
            if self.max_requests is not None and self.max_requests > 100:
                raise ValueError("PROVIDER_LIVE_REQUEST_BUDGET_EXCEEDED")
            if self.max_bytes is not None and self.max_bytes > 52_428_800:
                raise ValueError("PROVIDER_LIVE_BYTE_BUDGET_EXCEEDED")
        return self

    def _require(self, *names: str) -> None:
        if any(getattr(self, name) is None for name in names):
            raise ValueError("PROVIDER_CONTROL_CONTEXT_REQUIRED")


class _ProductionProviderCliApplication:
    """Open one local database session for one explicit read command."""

    def invoke(
        self,
        operation: str,
        identity: str | UUID | None,
        page: PageRequest,
    ) -> SafeProviderProjection | ProviderQueryPage | None:
        engine: Engine | None = None
        try:
            settings = Settings()
            engine = create_engine_from_settings(settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                service = ProviderQueryService(SqlAlchemyProviderQueryRepository(session))
                return _read(service, operation, identity, page)
        finally:
            if engine is not None:
                engine.dispose()

    def control(self, command: ProviderControlCommand) -> dict[str, object]:
        engine: Engine | None = None
        try:
            settings = Settings()
            engine = create_engine_from_settings(settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                result = execute_provider_control(session, command)
                session.commit()
                return result
        finally:
            if engine is not None:
                engine.dispose()


def _production_application() -> ProviderCliApplication:
    return _ProductionProviderCliApplication()


application_factory: Callable[[], ProviderCliApplication] = _production_application


def execute_provider_control(
    session: Session,
    command: ProviderControlCommand,
) -> dict[str, object]:
    """Execute one already-validated control inside the caller-owned transaction."""

    if command.operation in {"sync-pause", "sync-resume", "sync-cancel"}:
        return _change_run_state(session, command)
    if command.operation == "repair":
        return _record_repair_block(session, command)

    definition = SqlAlchemyProviderDefinitionRepository(session).get_definition(
        command.provider_code or "",
        command.provider_version or "",
    )
    if definition is None:
        return {"status": "BLOCKED", "warning": "PROVIDER_DEFINITION_NOT_FOUND"}
    if command.operation == "credential-check":
        governance = SqlAlchemyProviderGovernanceRepository(session)
        credential_status = "NOT_CONFIGURED"
        if definition.credential_reference_id is not None:
            reference = governance.get_credential_reference(definition.credential_reference_id)
            credential_status = (
                "REFERENCE_NOT_FOUND" if reference is None else reference.status.value
            )
        status = "PASS" if credential_status == "CONFIGURED_METADATA_ONLY" else "BLOCKED"
        _append_control_audit(
            session,
            definition.id,
            None,
            "CREDENTIAL_METADATA_CHECK",
            status,
            "Credential metadata status checked without resolving secret values.",
        )
        return {"status": status, "credential_status": credential_status}

    governance = SqlAlchemyProviderGovernanceRepository(session)
    capability = governance.get_capability(
        definition.id,
        command.capability_code or "",
        command.capability_version or "",
    )
    if capability is None:
        return {"status": "BLOCKED", "warning": "PROVIDER_CAPABILITY_NOT_FOUND"}
    if command.operation == "live-check":
        _append_control_audit(
            session,
            definition.id,
            None,
            "LIVE_CHECK_REFUSED",
            "NOT_ATTEMPTED",
            "Live validation requires a separate exact authorization record.",
        )
        return {
            "status": "BLOCKED",
            "live_status": "NOT_ATTEMPTED",
            "warning": "LIVE_AUTHORIZATION_REQUIRED",
        }
    return _create_offline_sync_control(session, command, definition, capability)


def _create_offline_sync_control(
    session: Session,
    command: ProviderControlCommand,
    definition: object,
    capability: object,
) -> dict[str, object]:
    from stock_research_agent.domain.providers.capabilities import ProviderCapabilityRecord
    from stock_research_agent.domain.providers.schemas import ProviderDefinitionRecord

    if not isinstance(definition, ProviderDefinitionRecord) or not isinstance(
        capability, ProviderCapabilityRecord
    ):
        raise TypeError("PROVIDER_CONTROL_RECORD_INVALID")
    governance = SqlAlchemyProviderGovernanceRepository(session)
    policy = governance.get_policy(definition.id, command.policy_version or "")
    license_policy = governance.get_license_policy(
        definition.id,
        command.license_version or "",
    )
    gate_failures: list[str] = []
    if definition.definition_status is not ProviderDefinitionStatus.ACTIVE:
        gate_failures.append("PROVIDER_DEFINITION_NOT_ACTIVE")
    if capability.status is not ProviderCapabilityStatus.IMPLEMENTED_OFFLINE:
        gate_failures.append("PROVIDER_CAPABILITY_NOT_OFFLINE_READY")
    if policy is None:
        gate_failures.append("PROVIDER_POLICY_NOT_FOUND")
    elif policy.network_enabled:
        gate_failures.append("PROVIDER_OFFLINE_POLICY_REQUIRES_NETWORK")
    if license_policy is None:
        gate_failures.append("PROVIDER_LICENSE_NOT_FOUND")
    elif (
        license_policy.status is not ProviderLicenseStatus.APPROVED
        or license_policy.acquisition is not LicensePermission.ALLOWED
    ):
        gate_failures.append("PROVIDER_LICENSE_NOT_APPROVED")
    if gate_failures:
        _append_control_audit(
            session,
            definition.id,
            None,
            command.operation.upper().replace("-", "_"),
            "BLOCKED",
            "Offline Provider control was blocked by an exact governance gate.",
        )
        return {"status": "BLOCKED", "warnings": tuple(sorted(gate_failures))}
    assert policy is not None and license_policy is not None
    assert command.research_as_of_time is not None
    assert command.range_start is not None and command.range_end is not None
    assert command.max_requests is not None and command.max_bytes is not None
    assert command.max_attempts is not None and command.max_duration_seconds is not None
    if command.security_id is not None:
        scope: dict[str, object] = {
            "scope_type": "SECURITY",
            "scope_value": str(command.security_id),
        }
    else:
        assert command.universe_code is not None
        scope = {"scope_type": "UNIVERSE", "scope_value": command.universe_code}
    budget: dict[str, object] = {
        "max_requests": command.max_requests,
        "max_bytes": command.max_bytes,
        "max_attempts": command.max_attempts,
        "max_duration_seconds": command.max_duration_seconds,
    }
    identity = {
        "provider_definition_id": str(definition.id),
        "provider_capability_id": str(capability.id),
        "policy_id": str(policy.id),
        "license_policy_id": str(license_policy.id),
        "security_id": str(command.security_id) if command.security_id is not None else None,
        "universe_code": command.universe_code,
        "research_as_of_time": command.research_as_of_time.isoformat(),
        "range_start": command.range_start.isoformat(),
        "range_end": command.range_end.isoformat(),
        "scope": scope,
        "budget": budget,
    }
    repository = SqlAlchemyProviderSyncRepository(session)
    request = repository.create_request(
        ProviderSyncRequestWrite(
            provider_definition_id=definition.id,
            provider_capability_id=capability.id,
            policy_id=policy.id,
            license_policy_id=license_policy.id,
            credential_reference_id=definition.credential_reference_id,
            security_id=command.security_id,
            universe_code=command.universe_code,
            research_as_of_time=command.research_as_of_time,
            range_start=command.range_start,
            range_end=command.range_end,
            execution_mode=ProviderExecutionMode.OFFLINE,
            scope=scope,
            budget=budget,
            request_checksum=provider_checksum(identity),
            idempotency_key=provider_checksum({"offline_sync": identity}),
        )
    )
    slices = (
        {
            "slice_id": "OFFLINE_EXACT_SCOPE",
            "ordinal": 0,
            "range_start": command.range_start.isoformat(),
            "range_end": command.range_end.isoformat(),
            "request_parameters": {"mode": "OFFLINE_FIXTURE_ONLY"},
        },
    )
    plan = repository.add_plan(
        ProviderSyncPlanWrite(
            sync_request_id=request.id,
            adapter_version=definition.adapter_version,
            checkpoint_revision=None,
            slices=slices,
            plan_checksum=provider_checksum(
                {
                    "request_id": str(request.id),
                    "adapter_version": definition.adapter_version,
                    "slices": slices,
                }
            ),
        )
    )
    if command.operation == "sync-plan":
        _append_control_audit(
            session,
            definition.id,
            None,
            "SYNC_PLAN",
            "PLANNED",
            "Finite offline-only Provider plan persisted after all governance gates.",
        )
        return {
            "status": "PLANNED",
            "sync_request_id": str(request.id),
            "sync_plan_id": str(plan.id),
            "slice_count": plan.slice_count,
            "execution_mode": "OFFLINE",
        }
    run = repository.create_run(
        ProviderSyncRunWrite(
            sync_request_id=request.id,
            sync_plan_id=plan.id,
            provider_definition_id=definition.id,
            provider_capability_id=capability.id,
        )
    )
    blocked = repository.transition(
        run.id,
        ProviderRunTransition(
            target=ProviderRunStatus.BLOCKED,
            completed_at=datetime.now(UTC),
            warning_codes=("OFFLINE_FIXTURE_EXECUTOR_NOT_SELECTED",),
        ),
    )
    _append_control_audit(
        session,
        definition.id,
        blocked.id,
        "SYNC_RUN",
        "BLOCKED",
        "Run persisted but execution stayed blocked without an explicit fixture executor.",
    )
    return {
        "status": "BLOCKED",
        "sync_run_id": str(blocked.id),
        "execution_mode": "OFFLINE",
        "warning": "OFFLINE_FIXTURE_EXECUTOR_NOT_SELECTED",
    }


def _change_run_state(session: Session, command: ProviderControlCommand) -> dict[str, object]:
    assert command.run_id is not None
    assert command.sync_request_id is not None and command.sync_plan_id is not None
    assert command.provider_definition_id is not None
    assert command.provider_capability_id is not None
    service = ProviderSyncControlService(
        SqlAlchemyProviderSyncRepository(session),
        clock=lambda: datetime.now(UTC),
    )
    value = ProviderSyncControlCommand(
        run_id=command.run_id,
        sync_request_id=command.sync_request_id,
        sync_plan_id=command.sync_plan_id,
        provider_definition_id=command.provider_definition_id,
        provider_capability_id=command.provider_capability_id,
    )
    operation = {
        "sync-pause": service.pause,
        "sync-resume": service.resume,
        "sync-cancel": service.cancel,
    }[command.operation]
    run = operation(value)
    _append_control_audit(
        session,
        command.provider_definition_id,
        run.id,
        command.operation.upper().replace("-", "_"),
        run.status.value,
        "Exact-context Provider Run lifecycle transition applied.",
    )
    return {"status": run.status.value, "sync_run_id": str(run.id)}


def _record_repair_block(session: Session, command: ProviderControlCommand) -> dict[str, object]:
    assert command.provider_definition_id is not None
    _append_control_audit(
        session,
        command.provider_definition_id,
        None,
        "DEAD_LETTER_REPAIR",
        "BLOCKED",
        "Repair stayed blocked because no exact offline replay executor was selected.",
    )
    return {"status": "BLOCKED", "warning": "REPAIR_EXECUTOR_NOT_SELECTED"}


def _append_control_audit(
    session: Session,
    provider_definition_id: UUID,
    sync_run_id: UUID | None,
    action_code: str,
    decision_code: str,
    safe_summary: str,
) -> None:
    event = {
        "provider_definition_id": str(provider_definition_id),
        "sync_run_id": str(sync_run_id) if sync_run_id is not None else None,
        "actor_type": "CLI",
        "action_code": action_code,
        "decision_code": decision_code,
        "safe_summary": safe_summary,
    }
    session.add(
        ProviderAuditEvent(
            provider_definition_id=provider_definition_id,
            sync_run_id=sync_run_id,
            actor_type="CLI",
            action_code=action_code,
            decision_code=decision_code,
            safe_summary=safe_summary,
            event_checksum=provider_checksum(event),
        )
    )
    session.flush()


def _read(
    service: ProviderQueryService,
    operation: str,
    identity: str | UUID | None,
    page: PageRequest,
) -> SafeProviderProjection | ProviderQueryPage | None:
    if operation == "list":
        return service.list_providers(page)
    if operation == "show" and isinstance(identity, str):
        return service.get_provider(identity)
    if operation == "capabilities" and isinstance(identity, str):
        return service.list_capabilities(identity, page)
    if operation == "policy" and isinstance(identity, str):
        return service.get_policy(identity)
    if operation == "license" and isinstance(identity, str):
        return service.get_license(identity)
    if operation == "health" and isinstance(identity, str):
        return service.get_health(identity)
    if operation == "circuit-status" and isinstance(identity, str):
        return service.get_circuit(identity)
    if operation == "sync-show" and isinstance(identity, UUID):
        return service.get_sync_run(identity)
    if operation == "checkpoints" and isinstance(identity, str):
        return service.list_checkpoints(identity, page)
    if operation == "raw-artifacts" and isinstance(identity, UUID):
        return service.list_artifacts(identity, page)
    if operation == "quality-issues" and isinstance(identity, UUID):
        return service.list_quality_issues(identity, page)
    if operation == "dead-letters" and isinstance(identity, UUID):
        return service.list_dead_letters(identity, page)
    if operation == "readiness" and isinstance(identity, UUID):
        return service.get_readiness(identity)
    raise ValueError("PROVIDER_CLI_OPERATION_INVALID")


def _render(value: BaseModel, json_output: bool) -> None:
    payload = value.model_dump(mode="json")
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for key, item in payload.items():
        typer.echo(f"{key}: {item}")


@provider_app.command("bootstrap-sec-control-plane")
def bootstrap_sec_control_plane(
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    confirm: Annotated[bool, typer.Option("--confirm")] = False,
    json_output: JsonOutput = False,
) -> None:
    """Inspect or materialize the exact SEC control-plane manifest."""
    if not dry_run and not confirm:
        typer.echo("SEC_PROVIDER_BOOTSTRAP_CONFIRMATION_REQUIRED")
        raise typer.Exit(code=EXIT_FAILED)
    engine: Engine | None = None
    try:
        settings = Settings()
        if settings.database_url is None:
            typer.echo("SEC_PROVIDER_BOOTSTRAP_DATABASE_URL_REQUIRED")
            raise typer.Exit(code=EXIT_FAILED)
        engine = create_engine_from_settings(settings)
        application = SecProviderControlPlaneBootstrapApplication(
            create_session_factory(engine),
            SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP,
        )
        result = application.inspect() if dry_run else application.bootstrap()
        payload = result.model_dump(mode="json")
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        else:
            for key, item in payload.items():
                typer.echo(f"{key}: {item}")
        if result.status.value == "CONFLICT":
            raise typer.Exit(code=EXIT_FAILED)
    except SecProviderControlPlaneBootstrapConflict as error:
        payload = {"status": "CONFLICT", "code": error.code}
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        else:
            for key, item in payload.items():
                typer.echo(f"{key}: {item}")
        raise typer.Exit(code=EXIT_FAILED) from None
    finally:
        if engine is not None:
            engine.dispose()


def _invoke(
    operation: str,
    identity: str | UUID | None,
    limit: int,
    offset: int,
    json_output: bool,
) -> None:
    try:
        result = application_factory().invoke(
            operation,
            identity,
            PageRequest(limit=limit, offset=offset),
        )
    except Exception:
        typer.echo("Provider query failed")
        raise typer.Exit(code=EXIT_FAILED) from None
    if result is None:
        typer.echo("Provider resource not found")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    _render(result, json_output)


@provider_app.command("list")
def list_providers(
    limit: Limit = 50,
    offset: Offset = 0,
    json_output: JsonOutput = False,
) -> None:
    _invoke("list", None, limit, offset, json_output)


def _provider_read(operation: str, provider_code: str, json_output: bool) -> None:
    _invoke(operation, provider_code, 50, 0, json_output)


@provider_app.command("show")
def show(provider_code: str, json_output: JsonOutput = False) -> None:
    _provider_read("show", provider_code, json_output)


@provider_app.command("capabilities")
def capabilities(
    provider_code: str,
    limit: Limit = 50,
    offset: Offset = 0,
    json_output: JsonOutput = False,
) -> None:
    _invoke("capabilities", provider_code, limit, offset, json_output)


@provider_app.command("policy")
def policy(provider_code: str, json_output: JsonOutput = False) -> None:
    _provider_read("policy", provider_code, json_output)


@provider_app.command("license")
def license_status(provider_code: str, json_output: JsonOutput = False) -> None:
    _provider_read("license", provider_code, json_output)


@provider_app.command("health")
def health(provider_code: str, json_output: JsonOutput = False) -> None:
    _provider_read("health", provider_code, json_output)


@provider_app.command("circuit-status")
def circuit_status(provider_code: str, json_output: JsonOutput = False) -> None:
    _provider_read("circuit-status", provider_code, json_output)


@provider_app.command("sync-show")
def sync_show(run_id: UUID, json_output: JsonOutput = False) -> None:
    _invoke("sync-show", run_id, 50, 0, json_output)


@provider_app.command("checkpoints")
def checkpoints(
    provider_code: str,
    limit: Limit = 50,
    offset: Offset = 0,
    json_output: JsonOutput = False,
) -> None:
    _invoke("checkpoints", provider_code, limit, offset, json_output)


def _run_page_read(
    operation: str,
    run_id: UUID,
    limit: int,
    offset: int,
    json_output: bool,
) -> None:
    _invoke(operation, run_id, limit, offset, json_output)


@provider_app.command("raw-artifacts")
def raw_artifacts(
    run_id: UUID,
    limit: Limit = 50,
    offset: Offset = 0,
    json_output: JsonOutput = False,
) -> None:
    _run_page_read("raw-artifacts", run_id, limit, offset, json_output)


@provider_app.command("quality-issues")
def quality_issues(
    run_id: UUID,
    limit: Limit = 50,
    offset: Offset = 0,
    json_output: JsonOutput = False,
) -> None:
    _run_page_read("quality-issues", run_id, limit, offset, json_output)


@provider_app.command("dead-letters")
def dead_letters(
    run_id: UUID,
    limit: Limit = 50,
    offset: Offset = 0,
    json_output: JsonOutput = False,
) -> None:
    _run_page_read("dead-letters", run_id, limit, offset, json_output)


@provider_app.command("readiness")
def readiness(security_id: UUID, json_output: JsonOutput = False) -> None:
    _invoke("readiness", security_id, 50, 0, json_output)


def _control(command: ProviderControlCommand, json_output: bool) -> None:
    try:
        result = application_factory().control(command)
    except Exception:
        typer.echo("Provider control failed")
        raise typer.Exit(code=EXIT_FAILED) from None
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        for key, item in result.items():
            typer.echo(f"{key}: {item}")
    if result.get("status") == "BLOCKED":
        raise typer.Exit(code=EXIT_NOT_FOUND)
    if result.get("status") in {"FAILED", "INVALID"}:
        raise typer.Exit(code=EXIT_FAILED)


@provider_app.command("credential-check")
def credential_check(
    provider_code: str,
    provider_version: Annotated[str, typer.Option("--provider-version")],
    confirmed: Annotated[bool, typer.Option("--confirm")] = False,
    json_output: JsonOutput = False,
) -> None:
    _control(
        ProviderControlCommand(
            operation="credential-check",
            provider_code=provider_code,
            provider_version=provider_version,
            confirmed=confirmed,
        ),
        json_output,
    )


def _sync_control(
    operation: Literal["sync-plan", "sync-run"],
    provider_code: str,
    capability_code: str,
    provider_version: str,
    capability_version: str,
    policy_version: str,
    license_version: str,
    security_id: UUID | None,
    universe_code: str | None,
    research_as_of_time: datetime,
    range_start: date,
    range_end: date,
    max_requests: int,
    max_bytes: int,
    max_attempts: int,
    max_duration_seconds: int,
    confirmed: bool,
    json_output: bool,
) -> None:
    _control(
        ProviderControlCommand(
            operation=operation,
            provider_code=provider_code,
            capability_code=capability_code,
            provider_version=provider_version,
            capability_version=capability_version,
            policy_version=policy_version,
            license_version=license_version,
            security_id=security_id,
            universe_code=universe_code,
            research_as_of_time=research_as_of_time,
            range_start=range_start,
            range_end=range_end,
            max_requests=max_requests,
            max_bytes=max_bytes,
            max_attempts=max_attempts,
            max_duration_seconds=max_duration_seconds,
            confirmed=confirmed,
        ),
        json_output,
    )


def _sync_options(
    operation: Literal["sync-plan", "sync-run"],
    provider_code: str,
    capability_code: str,
    provider_version: str,
    capability_version: str,
    policy_version: str,
    license_version: str,
    security_id: UUID | None,
    universe_code: str | None,
    as_of: str,
    range_start: str,
    range_end: str,
    max_requests: int,
    max_bytes: int,
    max_attempts: int,
    max_duration_seconds: int,
    confirmed: bool,
    json_output: bool,
) -> None:
    _sync_control(
        operation,
        provider_code,
        capability_code,
        provider_version,
        capability_version,
        policy_version,
        license_version,
        security_id,
        universe_code,
        datetime.fromisoformat(as_of.replace("Z", "+00:00")),
        date.fromisoformat(range_start),
        date.fromisoformat(range_end),
        max_requests,
        max_bytes,
        max_attempts,
        max_duration_seconds,
        confirmed,
        json_output,
    )


@provider_app.command("sync-plan")
def sync_plan(
    provider_code: str,
    capability_code: str,
    provider_version: Annotated[str, typer.Option("--provider-version")],
    capability_version: Annotated[str, typer.Option("--capability-version")],
    policy_version: Annotated[str, typer.Option("--policy-version")],
    license_version: Annotated[str, typer.Option("--license-version")],
    as_of: Annotated[str, typer.Option("--as-of")],
    range_start: Annotated[str, typer.Option("--range-start")],
    range_end: Annotated[str, typer.Option("--range-end")],
    security_id: Annotated[UUID | None, typer.Option("--security-id")] = None,
    universe_code: Annotated[str | None, typer.Option("--universe")] = None,
    max_requests: Annotated[int, typer.Option("--max-requests", min=1, max=10_000)] = 10,
    max_bytes: Annotated[int, typer.Option("--max-bytes", min=1, max=10_737_418_240)] = 1_000_000,
    max_attempts: Annotated[int, typer.Option("--max-attempts", min=1, max=3)] = 1,
    max_duration_seconds: Annotated[
        int, typer.Option("--max-duration-seconds", min=1, max=86_400)
    ] = 60,
    confirmed: Annotated[bool, typer.Option("--confirm")] = False,
    json_output: JsonOutput = False,
) -> None:
    _sync_options(
        "sync-plan",
        provider_code,
        capability_code,
        provider_version,
        capability_version,
        policy_version,
        license_version,
        security_id,
        universe_code,
        as_of,
        range_start,
        range_end,
        max_requests,
        max_bytes,
        max_attempts,
        max_duration_seconds,
        confirmed,
        json_output,
    )


@provider_app.command("sync-run")
def sync_run(
    provider_code: str,
    capability_code: str,
    provider_version: Annotated[str, typer.Option("--provider-version")],
    capability_version: Annotated[str, typer.Option("--capability-version")],
    policy_version: Annotated[str, typer.Option("--policy-version")],
    license_version: Annotated[str, typer.Option("--license-version")],
    as_of: Annotated[str, typer.Option("--as-of")],
    range_start: Annotated[str, typer.Option("--range-start")],
    range_end: Annotated[str, typer.Option("--range-end")],
    security_id: Annotated[UUID | None, typer.Option("--security-id")] = None,
    universe_code: Annotated[str | None, typer.Option("--universe")] = None,
    max_requests: Annotated[int, typer.Option("--max-requests", min=1, max=10_000)] = 10,
    max_bytes: Annotated[int, typer.Option("--max-bytes", min=1, max=10_737_418_240)] = 1_000_000,
    max_attempts: Annotated[int, typer.Option("--max-attempts", min=1, max=3)] = 1,
    max_duration_seconds: Annotated[
        int, typer.Option("--max-duration-seconds", min=1, max=86_400)
    ] = 60,
    confirmed: Annotated[bool, typer.Option("--confirm")] = False,
    json_output: JsonOutput = False,
) -> None:
    _sync_options(
        "sync-run",
        provider_code,
        capability_code,
        provider_version,
        capability_version,
        policy_version,
        license_version,
        security_id,
        universe_code,
        as_of,
        range_start,
        range_end,
        max_requests,
        max_bytes,
        max_attempts,
        max_duration_seconds,
        confirmed,
        json_output,
    )


def _run_control(
    operation: Literal["sync-pause", "sync-resume", "sync-cancel"],
    run_id: UUID,
    sync_request_id: UUID,
    sync_plan_id: UUID,
    provider_definition_id: UUID,
    provider_capability_id: UUID,
    confirmed: bool,
    json_output: bool,
) -> None:
    _control(
        ProviderControlCommand(
            operation=operation,
            run_id=run_id,
            sync_request_id=sync_request_id,
            sync_plan_id=sync_plan_id,
            provider_definition_id=provider_definition_id,
            provider_capability_id=provider_capability_id,
            confirmed=confirmed,
        ),
        json_output,
    )


def _lifecycle_options(
    operation: Literal["sync-pause", "sync-resume", "sync-cancel"],
    run_id: UUID,
    sync_request_id: UUID,
    sync_plan_id: UUID,
    provider_definition_id: UUID,
    provider_capability_id: UUID,
    confirmed: bool,
    json_output: bool,
) -> None:
    _run_control(
        operation,
        run_id,
        sync_request_id,
        sync_plan_id,
        provider_definition_id,
        provider_capability_id,
        confirmed,
        json_output,
    )


@provider_app.command("sync-pause")
def sync_pause(
    run_id: UUID,
    sync_request_id: Annotated[UUID, typer.Option("--sync-request-id")],
    sync_plan_id: Annotated[UUID, typer.Option("--sync-plan-id")],
    provider_definition_id: Annotated[UUID, typer.Option("--provider-definition-id")],
    provider_capability_id: Annotated[UUID, typer.Option("--provider-capability-id")],
    confirmed: Annotated[bool, typer.Option("--confirm")] = False,
    json_output: JsonOutput = False,
) -> None:
    _lifecycle_options(
        "sync-pause",
        run_id,
        sync_request_id,
        sync_plan_id,
        provider_definition_id,
        provider_capability_id,
        confirmed,
        json_output,
    )


@provider_app.command("sync-resume")
def sync_resume(
    run_id: UUID,
    sync_request_id: Annotated[UUID, typer.Option("--sync-request-id")],
    sync_plan_id: Annotated[UUID, typer.Option("--sync-plan-id")],
    provider_definition_id: Annotated[UUID, typer.Option("--provider-definition-id")],
    provider_capability_id: Annotated[UUID, typer.Option("--provider-capability-id")],
    confirmed: Annotated[bool, typer.Option("--confirm")] = False,
    json_output: JsonOutput = False,
) -> None:
    _lifecycle_options(
        "sync-resume",
        run_id,
        sync_request_id,
        sync_plan_id,
        provider_definition_id,
        provider_capability_id,
        confirmed,
        json_output,
    )


@provider_app.command("sync-cancel")
def sync_cancel(
    run_id: UUID,
    sync_request_id: Annotated[UUID, typer.Option("--sync-request-id")],
    sync_plan_id: Annotated[UUID, typer.Option("--sync-plan-id")],
    provider_definition_id: Annotated[UUID, typer.Option("--provider-definition-id")],
    provider_capability_id: Annotated[UUID, typer.Option("--provider-capability-id")],
    confirmed: Annotated[bool, typer.Option("--confirm")] = False,
    json_output: JsonOutput = False,
) -> None:
    _lifecycle_options(
        "sync-cancel",
        run_id,
        sync_request_id,
        sync_plan_id,
        provider_definition_id,
        provider_capability_id,
        confirmed,
        json_output,
    )


@provider_app.command("repair")
def repair(
    dead_letter_id: UUID,
    provider_definition_id: Annotated[UUID, typer.Option("--provider-definition-id")],
    confirmed: Annotated[bool, typer.Option("--confirm")] = False,
    json_output: JsonOutput = False,
) -> None:
    _control(
        ProviderControlCommand(
            operation="repair",
            dead_letter_id=dead_letter_id,
            provider_definition_id=provider_definition_id,
            confirmed=confirmed,
        ),
        json_output,
    )


@provider_app.command("live-check")
def live_check(
    provider_code: str,
    capability_code: str,
    provider_version: Annotated[str, typer.Option("--provider-version")],
    capability_version: Annotated[str, typer.Option("--capability-version")],
    max_requests: Annotated[int, typer.Option("--max-requests", min=1, max=100)],
    max_bytes: Annotated[int, typer.Option("--max-bytes", min=1, max=52_428_800)],
    confirmed: Annotated[bool, typer.Option("--confirm")] = False,
    json_output: JsonOutput = False,
) -> None:
    _control(
        ProviderControlCommand(
            operation="live-check",
            provider_code=provider_code,
            capability_code=capability_code,
            provider_version=provider_version,
            capability_version=capability_version,
            max_requests=max_requests,
            max_bytes=max_bytes,
            confirmed=confirmed,
        ),
        json_output,
    )


__all__ = [
    "ProviderCliApplication",
    "ProviderControlCommand",
    "application_factory",
    "provider_app",
]
