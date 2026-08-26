"""Production composition contracts for a finite Gate B authorization."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError

from stock_research_agent.domain.live_evidence.authorization import (
    require_active_authorization,
    validate_execution_scope,
)
from stock_research_agent.domain.live_evidence.canonical import verify_grant_checksum
from stock_research_agent.domain.live_evidence.enums import (
    ExecutionApprovalState,
    LiveAuthorizationEventType,
)
from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.execution_approval import ExecutionApprovalService
from stock_research_agent.domain.live_evidence.schemas import (
    AuthorizationExecutionScope,
    LiveAuthorizationGrantRecord,
    LiveExecutionApprovalRecord,
    ValidateExecutionApprovalRequest,
)
from stock_research_agent.domain.providers.credentials import (
    CredentialReferenceRecord,
    CredentialResolverKind,
    validate_credential_reference_metadata,
)
from stock_research_agent.domain.providers.enums import ProviderCredentialStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
)
from stock_research_agent.domain.providers.sync import ProviderSyncPlanRecord


class GateBCandidate(FrozenProviderContract):
    security_id: UUID
    issuer_id: UUID
    symbol: str
    exchange: str
    cik: str


class GateBAuthorizationCreateRequest(FrozenProviderContract):
    provider: str
    candidate: GateBCandidate
    plan_id: UUID
    plan_checksum: Checksum
    allowed_hosts: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    max_resource_count: int
    max_actual_attempts: int
    retry_limit: int
    redirect_limit: int
    concurrency: int
    connect_timeout_seconds: int
    idle_read_timeout_seconds: int
    total_timeout_seconds: int
    contact_identity_reference: str
    grant_id: str
    single_use: bool
    approved_at: AwareUtcDateTime
    expires_at: AwareUtcDateTime


class GateBAuthorizationEnvelope(GateBAuthorizationCreateRequest):
    """Immutable, secret-free input that grants no execution capability."""


class GateBAuthorizationValidation(FrozenProviderContract):
    """Secret-free persisted-contract validation that is not executable."""

    authorization_id: UUID
    authorization_checksum: Checksum
    approval_id: UUID
    plan_id: UUID
    plan_checksum: Checksum
    provider: str
    security_id: UUID
    issuer_id: UUID
    provider_security_identifier: str
    credential_reference_id: UUID
    user_agent_reference_id: UUID


class AuthorizedGateBExecution(FrozenProviderContract):
    authorization_id: UUID
    authorization_checksum: Checksum
    approval_id: UUID
    plan_id: UUID
    plan_checksum: Checksum
    provider: str
    security_id: UUID
    issuer_id: UUID
    provider_security_identifier: str
    credential_reference_id: UUID
    user_agent_reference_id: UUID


class ProductionAuthorizationApplication:
    def create(self, payload: Mapping[str, object]) -> GateBAuthorizationEnvelope:
        try:
            envelope = GateBAuthorizationEnvelope.model_validate(_parse_uuid_fields(payload))
        except ValidationError as error:
            raise LiveEvidenceValidationError(_validation_code(error)) from None
        _require_approved_envelope(envelope)
        return envelope

    def plan(self, authorization_id: UUID, checksum: str) -> dict[str, object]:
        del authorization_id, checksum
        raise LiveEvidenceValidationError("LIVE_AUTHORIZATION_OPERATION_NOT_CONFIGURED")

    def show(self, authorization_id: UUID) -> dict[str, object]:
        del authorization_id
        raise LiveEvidenceValidationError("LIVE_AUTHORIZATION_OPERATION_NOT_CONFIGURED")

    def activate(self, authorization_id: UUID, checksum: str) -> dict[str, object]:
        del authorization_id, checksum
        raise LiveEvidenceValidationError("LIVE_AUTHORIZATION_OPERATION_NOT_CONFIGURED")

    def revoke(self, authorization_id: UUID, checksum: str) -> dict[str, object]:
        del authorization_id, checksum
        raise LiveEvidenceValidationError("LIVE_AUTHORIZATION_OPERATION_NOT_CONFIGURED")


class ProductionAuthorizationGate:
    """Produce an execution capability only from authoritative persisted contracts."""

    def authorize(
        self,
        envelope: GateBAuthorizationEnvelope,
        *,
        grant: LiveAuthorizationGrantRecord,
        events: tuple[LiveAuthorizationEventType, ...],
        approval: LiveExecutionApprovalRecord,
        plan: ProviderSyncPlanRecord,
        scope: AuthorizationExecutionScope,
        contact_reference: CredentialReferenceRecord,
        checked_at: datetime,
    ) -> GateBAuthorizationValidation:
        verify_grant_checksum(grant)
        _require_authoritative_binding(envelope, grant, approval, plan)
        require_active_authorization(grant, events, checked_at)
        if approval.state is ExecutionApprovalState.EXPIRED:
            raise LiveEvidenceValidationError("EXEC_APPROVAL_EXPIRED")
        if approval.state is ExecutionApprovalState.BLOCKED:
            raise LiveEvidenceValidationError("EXEC_APPROVAL_SIGNATURE_INVALID")
        validate_execution_scope(grant, scope)
        decision = ExecutionApprovalService.validate(
            ValidateExecutionApprovalRequest(
                approval=approval,
                authorization_checksum=grant.canonical_checksum,
                plan_checksum=plan.plan_checksum,
                checked_at=checked_at,
                consumed=approval.state is ExecutionApprovalState.CONSUMED,
            )
        )
        if decision.state is not ExecutionApprovalState.VALID:
            raise LiveEvidenceValidationError(
                decision.failure_code or "EXEC_APPROVAL_SIGNATURE_INVALID"
            )
        _require_contact_reference(grant, contact_reference)
        return GateBAuthorizationValidation(
            authorization_id=grant.id,
            authorization_checksum=grant.canonical_checksum,
            approval_id=approval.id,
            plan_id=plan.id,
            plan_checksum=plan.plan_checksum,
            provider=grant.provider_code,
            security_id=grant.security_id,
            issuer_id=grant.issuer_id,
            provider_security_identifier=grant.provider_security_identifier,
            credential_reference_id=grant.credential_reference_id,
            user_agent_reference_id=grant.user_agent_reference_id,
        )


class AuthorizedSecTransportPort(Protocol):
    def execute(
        self,
        execution: AuthorizedGateBExecution,
        *,
        plan: ProviderSyncPlanRecord,
        slice_id: str,
        contact_reference: CredentialReferenceRecord,
    ) -> object: ...


class AuthorizationGatedSecPilotApplication:
    """Transport-free shell that keeps authorization structurally upstream."""

    def __init__(
        self,
        authorization_gate: ProductionAuthorizationGate,
        *,
        plan_descriptor: Mapping[str, object] | None = None,
        transport_controller: AuthorizedSecTransportPort | None = None,
    ) -> None:
        self.authorization_gate = authorization_gate
        self._plan_descriptor = dict(plan_descriptor or {})
        self._transport_controller = transport_controller

    def operate(
        self,
        operation: str,
        plan_id: UUID,
        plan_checksum: str,
    ) -> dict[str, object]:
        del plan_id, plan_checksum
        if operation == "plan" and self._plan_descriptor:
            return dict(self._plan_descriptor)
        return {
            "status": "BLOCKED",
            "warning_codes": [
                "LIVE_AUTHORIZATION_REQUIRED",
                "LIVE_TRANSPORT_NOT_CONFIGURED",
            ],
        }

    def execute_authorized(
        self,
        execution: AuthorizedGateBExecution,
        *,
        plan: ProviderSyncPlanRecord,
        slice_id: str,
        contact_reference: CredentialReferenceRecord,
    ) -> object:
        if self._transport_controller is None:
            raise LiveEvidenceValidationError("LIVE_TRANSPORT_NOT_CONFIGURED")
        return self._transport_controller.execute(
            execution,
            plan=plan,
            slice_id=slice_id,
            contact_reference=contact_reference,
        )


def _parse_uuid_fields(payload: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    plan_id = normalized.get("plan_id")
    if isinstance(plan_id, str):
        try:
            normalized["plan_id"] = UUID(plan_id)
        except ValueError:
            pass
    candidate = normalized.get("candidate")
    if isinstance(candidate, Mapping):
        normalized_candidate = dict(candidate)
        for field in ("security_id", "issuer_id"):
            value = normalized_candidate.get(field)
            if isinstance(value, str):
                try:
                    normalized_candidate[field] = UUID(value)
                except ValueError:
                    pass
        normalized["candidate"] = normalized_candidate
    return normalized


def _validation_code(error: ValidationError) -> str:
    location = error.errors(include_input=False)[0].get("loc", ())
    field = str(location[0]) if location else ""
    return {
        "provider": "GATE_B_PROVIDER_INVALID",
        "candidate": "GATE_B_CANDIDATE_INVALID",
        "plan_id": "GATE_B_PLAN_INVALID",
        "plan_checksum": "GATE_B_PLAN_INVALID",
        "grant_id": "GATE_B_GRANT_REFERENCE_INVALID",
        "single_use": "GATE_B_SINGLE_USE_REQUIRED",
        "allowed_hosts": "GATE_B_HOST_SCOPE_INVALID",
        "max_resource_count": "GATE_B_RESOURCE_BUDGET_INVALID",
        "max_actual_attempts": "GATE_B_ATTEMPT_BUDGET_INVALID",
        "redirect_limit": "GATE_B_REDIRECT_FORBIDDEN",
        "contact_identity_reference": "GATE_B_CONTACT_REFERENCE_INVALID",
        "approved_at": "GATE_B_AUTHORIZATION_WINDOW_INVALID",
        "expires_at": "GATE_B_AUTHORIZATION_WINDOW_INVALID",
    }.get(field, "GATE_B_PLAN_INVALID")


def _require_authoritative_binding(
    envelope: GateBAuthorizationEnvelope,
    grant: LiveAuthorizationGrantRecord,
    approval: LiveExecutionApprovalRecord,
    plan: ProviderSyncPlanRecord,
) -> None:
    if envelope.grant_id != str(grant.id):
        raise LiveEvidenceValidationError("GATE_B_GRANT_REFERENCE_INVALID")
    if (
        envelope.plan_id != plan.id
        or envelope.plan_checksum != plan.plan_checksum
        or plan.slice_count != envelope.max_resource_count
        or approval.authorization_id != grant.id
        or approval.sync_plan_id != plan.id
    ):
        raise LiveEvidenceValidationError("EXEC_APPROVAL_PLAN_MISMATCH")
    if (
        envelope.provider != grant.provider_code
        or envelope.candidate.security_id != grant.security_id
        or envelope.candidate.issuer_id != grant.issuer_id
        or envelope.candidate.cik != grant.provider_security_identifier
        or envelope.allowed_hosts != grant.official_domains
        or envelope.max_actual_attempts != grant.request_limit
    ):
        raise LiveEvidenceValidationError("AUTH_SECURITY_MISMATCH")


def _require_contact_reference(
    grant: LiveAuthorizationGrantRecord,
    reference: CredentialReferenceRecord,
) -> None:
    validate_credential_reference_metadata(reference.model_dump(mode="python"))
    valid = (
        reference.id == grant.user_agent_reference_id
        and reference.provider_definition_id == grant.provider_definition_id
        and reference.resolver_kind is CredentialResolverKind.ENVIRONMENT
        and reference.declared_name == "SEC_EDGAR_CONTACT_IDENTITY"
        and reference.status is ProviderCredentialStatus.CONFIGURED_METADATA_ONLY
    )
    if not valid:
        raise LiveEvidenceValidationError("GATE_B_CONTACT_REFERENCE_INVALID")


def _require_approved_envelope(value: GateBAuthorizationEnvelope) -> None:
    if value.provider != "SEC_EDGAR_PUBLIC_V1":
        raise LiveEvidenceValidationError("GATE_B_PROVIDER_INVALID")
    if not _candidate_is_finite(value.candidate):
        raise LiveEvidenceValidationError("GATE_B_CANDIDATE_INVALID")
    if not value.grant_id:
        raise LiveEvidenceValidationError("GATE_B_GRANT_REFERENCE_INVALID")
    if not value.single_use:
        raise LiveEvidenceValidationError("GATE_B_SINGLE_USE_REQUIRED")
    if value.allowed_hosts != ("data.sec.gov", "www.sec.gov"):
        raise LiveEvidenceValidationError("GATE_B_HOST_SCOPE_INVALID")
    if value.max_resource_count != 3:
        raise LiveEvidenceValidationError("GATE_B_RESOURCE_BUDGET_INVALID")
    if value.max_actual_attempts != 4:
        raise LiveEvidenceValidationError("GATE_B_ATTEMPT_BUDGET_INVALID")
    if value.retry_limit != 1:
        raise LiveEvidenceValidationError("GATE_B_ATTEMPT_BUDGET_INVALID")
    if value.redirect_limit != 0:
        raise LiveEvidenceValidationError("GATE_B_REDIRECT_FORBIDDEN")
    if value.concurrency != 1:
        raise LiveEvidenceValidationError("GATE_B_ATTEMPT_BUDGET_INVALID")
    if (
        value.connect_timeout_seconds,
        value.idle_read_timeout_seconds,
        value.total_timeout_seconds,
    ) != (10, 30, 120):
        raise LiveEvidenceValidationError("GATE_B_PLAN_INVALID")
    if value.contact_identity_reference != "SEC_EDGAR_CONTACT_IDENTITY":
        raise LiveEvidenceValidationError("GATE_B_CONTACT_REFERENCE_INVALID")
    lifetime = value.expires_at - value.approved_at
    if lifetime <= timedelta(0) or lifetime > timedelta(minutes=10):
        raise LiveEvidenceValidationError("GATE_B_AUTHORIZATION_WINDOW_INVALID")
    if not _paths_are_finite(value.allowed_paths):
        raise LiveEvidenceValidationError("GATE_B_PLAN_INVALID")


def _candidate_is_finite(value: GateBCandidate) -> bool:
    return bool(
        re.fullmatch(r"[A-Z0-9.-]{1,32}", value.symbol)
        and re.fullmatch(r"X[A-Z0-9]{3}", value.exchange)
        and re.fullmatch(r"\d{10}", value.cik)
    )


def _paths_are_finite(paths: tuple[str, ...]) -> bool:
    return bool(
        len(paths) == 3
        and len(set(paths)) == len(paths)
        and all(path.startswith("/") and "://" not in path for path in paths)
    )
