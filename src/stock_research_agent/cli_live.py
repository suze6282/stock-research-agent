"""Explicit Gate A commands for finite Live authorization records."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Annotated, Protocol
from uuid import UUID

import typer

from stock_research_agent.domain.live_evidence.gate_b_authorization import (
    AuthorizationGatedSecPilotApplication,
    AuthorizedGateBExecution,
    GateBAuthorizationEnvelope,
    ProductionAuthorizationApplication,
    ProductionAuthorizationGate,
)
from stock_research_agent.domain.live_evidence.gate_b_pilot import (
    AuthorizedSecGateBOfflineApplication,
    GateBAuditRepository,
    SecArtifactSettlementService,
    SecDataQualityStopService,
    SecDocumentCitationPort,
    SecExecutionStartPort,
    SecGateBPilotApplication,
    SecIngestionContext,
    SecTransportPort,
)
from stock_research_agent.domain.providers.credentials import CredentialReferenceRecord
from stock_research_agent.domain.providers.sync import ProviderSyncPlanRecord
from stock_research_agent.providers.sec_edgar.adapter import SecEdgarAdapter
from stock_research_agent.providers.sec_edgar.policy import (
    SecAuthorizedResource,
    describe_sec_gate_b_policy,
)

live_app = typer.Typer(help="Plan and inspect controlled Live evidence operations.")
authorization_app = typer.Typer(help="Manage finite checksum-bound Live authorizations.")
sec_app = typer.Typer(help="Plan the finite SEC pilot; Gate A has no Live transport.")
live_app.add_typer(authorization_app, name="authorization")
live_app.add_typer(sec_app, name="sec")


class AuthorizationCliApplication(Protocol):
    def create(self, payload: Mapping[str, object]) -> GateBAuthorizationEnvelope: ...

    def plan(self, authorization_id: UUID, checksum: str) -> dict[str, object]: ...

    def show(self, authorization_id: UUID) -> dict[str, object]: ...

    def activate(self, authorization_id: UUID, checksum: str) -> dict[str, object]: ...

    def revoke(self, authorization_id: UUID, checksum: str) -> dict[str, object]: ...


def _production_authorization_application() -> AuthorizationCliApplication:
    return ProductionAuthorizationApplication()


authorization_application_factory: Callable[[], AuthorizationCliApplication] = (
    _production_authorization_application
)


class SecPilotCliApplication(Protocol):
    authorization_gate: ProductionAuthorizationGate

    def operate(
        self,
        operation: str,
        plan_id: UUID,
        plan_checksum: str,
    ) -> dict[str, object]: ...

    def execute_authorized(
        self,
        execution: AuthorizedGateBExecution,
        *,
        plan: ProviderSyncPlanRecord,
        slice_id: str,
        contact_reference: CredentialReferenceRecord,
    ) -> object: ...


def _production_sec_pilot_application() -> SecPilotCliApplication:
    return AuthorizationGatedSecPilotApplication(
        ProductionAuthorizationGate(),
        plan_descriptor=describe_sec_gate_b_policy(),
    )


sec_pilot_application_factory: Callable[[], SecPilotCliApplication] = (
    _production_sec_pilot_application
)


def authorized_sec_pilot_application_factory(
    *,
    execution_start: SecExecutionStartPort,
    audit_repository: GateBAuditRepository,
    transport: SecTransportPort,
    adapter: SecEdgarAdapter,
    settlement: SecArtifactSettlementService,
    documents: SecDocumentCitationPort,
    data_quality: SecDataQualityStopService,
    artifact_id_factory: Callable[[], UUID],
    ingestion_context_factory: Callable[[SecAuthorizedResource], SecIngestionContext],
) -> AuthorizedSecGateBOfflineApplication:
    """Compose only from an explicit authoritative capability path and injected ports."""

    pilot = SecGateBPilotApplication(
        transport=transport,
        adapter=adapter,
        settlement=settlement,
        documents=documents,
        data_quality=data_quality,
        artifact_id_factory=artifact_id_factory,
        reservations=execution_start,
        ingestion_context_factory=ingestion_context_factory,
    )
    return AuthorizedSecGateBOfflineApplication(
        execution_start=execution_start,
        pilot=pilot,
        audit_repository=audit_repository,
    )


def _checksum(value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise typer.BadParameter("checksum must be lowercase sha256")
    return value


def _render(payload: dict[str, object], json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(payload, sort_keys=True))
    else:
        for key, value in payload.items():
            typer.echo(f"{key}: {value}")


def _invoke(
    operation: str,
    authorization_id: UUID,
    checksum: str | None,
    json_output: bool,
) -> None:
    try:
        application = authorization_application_factory()
        if operation == "show":
            payload = application.show(authorization_id)
        else:
            if checksum is None:
                raise ValueError("checksum is required")
            safe_checksum = _checksum(checksum)
            payload = getattr(application, operation)(authorization_id, safe_checksum)
    except typer.BadParameter:
        raise
    except Exception:
        typer.echo("Live authorization operation blocked")
        raise typer.Exit(code=3) from None
    _render(payload, json_output)


@authorization_app.command("plan")
def authorization_plan(
    authorization_id: Annotated[UUID, typer.Argument()],
    checksum: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _invoke("plan", authorization_id, checksum, json_output)


@authorization_app.command("show")
def authorization_show(
    authorization_id: Annotated[UUID, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _invoke("show", authorization_id, None, json_output)


@authorization_app.command("activate")
def authorization_activate(
    authorization_id: Annotated[UUID, typer.Argument()],
    checksum: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _invoke("activate", authorization_id, checksum, json_output)


@authorization_app.command("revoke")
def authorization_revoke(
    authorization_id: Annotated[UUID, typer.Argument()],
    checksum: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _invoke("revoke", authorization_id, checksum, json_output)


def _sec_operation(
    operation: str,
    plan_id: UUID,
    plan_checksum: str,
    json_output: bool,
) -> None:
    try:
        payload = sec_pilot_application_factory().operate(
            operation,
            plan_id,
            _checksum(plan_checksum),
        )
    except typer.BadParameter:
        raise
    except Exception:
        payload = {
            "status": "BLOCKED",
            "warning_codes": ["LIVE_TRANSPORT_NOT_CONFIGURED"],
        }
    _render(payload, json_output)
    if payload.get("status") == "BLOCKED":
        raise typer.Exit(code=3)


@sec_app.command("plan")
def sec_plan(
    plan_id: Annotated[UUID, typer.Argument()],
    plan_checksum: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _sec_operation("plan", plan_id, plan_checksum, json_output)


@sec_app.command("validate")
def sec_validate(
    plan_id: Annotated[UUID, typer.Argument()],
    plan_checksum: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _sec_operation("validate", plan_id, plan_checksum, json_output)


@sec_app.command("run")
def sec_run(
    plan_id: Annotated[UUID, typer.Argument()],
    plan_checksum: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _sec_operation("run", plan_id, plan_checksum, json_output)


@sec_app.command("show")
def sec_show(
    plan_id: Annotated[UUID, typer.Argument()],
    plan_checksum: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _sec_operation("show", plan_id, plan_checksum, json_output)
