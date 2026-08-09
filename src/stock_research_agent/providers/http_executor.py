"""Controlled Provider execution with fail-closed gate ordering."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class ProviderExecutionGate(StrEnum):
    DEFINITION = "DEFINITION"
    CAPABILITY = "CAPABILITY"
    LICENSE = "LICENSE"
    PROVIDER_POLICY = "PROVIDER_POLICY"
    CREDENTIAL_REFERENCE = "CREDENTIAL_REFERENCE"
    CONFIGURATION_VALIDATION = "CONFIGURATION_VALIDATION"
    LIVE_AUTHORIZATION = "LIVE_AUTHORIZATION"
    NETWORK = "NETWORK"
    CIRCUIT = "CIRCUIT"
    ENDPOINT = "ENDPOINT"
    RATE_LIMIT = "RATE_LIMIT"
    CACHE = "CACHE"


class ControlledExecutionStatus(StrEnum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class ProviderTransportStatus(StrEnum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class ControlledExecutionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")


class ProviderGateDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")


class ControlledExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ControlledExecutionStatus
    blocked_gate: ProviderExecutionGate | None = None
    reason_code: str
    executed_gates: tuple[ProviderExecutionGate, ...]
    body: bytes | None = None


class ProviderTransportResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ProviderTransportStatus
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    body: bytes | None = None


class ProviderExecutionGatePort(Protocol):
    def evaluate(self, request: ControlledExecutionRequest) -> ProviderGateDecision: ...


class ProviderCredentialResolverPort(Protocol):
    def resolve(self, request: ControlledExecutionRequest) -> object: ...


class ProviderTransportPort(Protocol):
    def send(
        self,
        request: ControlledExecutionRequest,
        credential: object,
    ) -> bytes | ProviderTransportResult: ...


class ProviderExecutionAuditSink(Protocol):
    def record(
        self,
        request: ControlledExecutionRequest,
        status: ControlledExecutionStatus,
        reason_code: str,
    ) -> None: ...


class DefaultControlledProviderExecutor:
    """Apply immutable governance order before secret or transport access."""

    def __init__(
        self,
        *,
        definition_gate: ProviderExecutionGatePort,
        capability_gate: ProviderExecutionGatePort,
        license_gate: ProviderExecutionGatePort,
        provider_policy_gate: ProviderExecutionGatePort,
        credential_reference_gate: ProviderExecutionGatePort,
        configuration_gate: ProviderExecutionGatePort,
        live_authorization_gate: ProviderExecutionGatePort,
        network_gate: ProviderExecutionGatePort,
        credential_resolver: ProviderCredentialResolverPort,
        circuit_gate: ProviderExecutionGatePort,
        endpoint_gate: ProviderExecutionGatePort,
        rate_limit_gate: ProviderExecutionGatePort,
        cache_gate: ProviderExecutionGatePort,
        transport: ProviderTransportPort,
        audit_sink: ProviderExecutionAuditSink | None = None,
    ) -> None:
        self._governance = (
            (ProviderExecutionGate.DEFINITION, definition_gate),
            (ProviderExecutionGate.CAPABILITY, capability_gate),
            (ProviderExecutionGate.LICENSE, license_gate),
            (ProviderExecutionGate.PROVIDER_POLICY, provider_policy_gate),
            (ProviderExecutionGate.CREDENTIAL_REFERENCE, credential_reference_gate),
            (ProviderExecutionGate.CONFIGURATION_VALIDATION, configuration_gate),
            (ProviderExecutionGate.LIVE_AUTHORIZATION, live_authorization_gate),
            (ProviderExecutionGate.NETWORK, network_gate),
        )
        self._operational = (
            (ProviderExecutionGate.CIRCUIT, circuit_gate),
            (ProviderExecutionGate.ENDPOINT, endpoint_gate),
            (ProviderExecutionGate.RATE_LIMIT, rate_limit_gate),
            (ProviderExecutionGate.CACHE, cache_gate),
        )
        self._credential_resolver = credential_resolver
        self._transport = transport
        self._audit_sink = audit_sink

    def execute(self, request: ControlledExecutionRequest) -> ControlledExecutionResult:
        executed: list[ProviderExecutionGate] = []
        for gate_name, gate in self._governance:
            blocked = self._evaluate(request, gate_name, gate, executed)
            if blocked is not None:
                return blocked

        credential = self._credential_resolver.resolve(request)
        for gate_name, gate in self._operational:
            blocked = self._evaluate(request, gate_name, gate, executed)
            if blocked is not None:
                return blocked

        transport_result = self._transport.send(request, credential)
        if isinstance(transport_result, ProviderTransportResult):
            if transport_result.status is ProviderTransportStatus.BLOCKED:
                result = ControlledExecutionResult(
                    status=ControlledExecutionStatus.BLOCKED,
                    blocked_gate=ProviderExecutionGate.NETWORK,
                    reason_code=transport_result.reason_code,
                    executed_gates=tuple(executed),
                )
                self._audit(request, result.status, result.reason_code)
                return result
            body = transport_result.body
        else:
            body = transport_result
        result = ControlledExecutionResult(
            status=ControlledExecutionStatus.COMPLETED,
            reason_code="PROVIDER_EXECUTION_COMPLETED",
            executed_gates=tuple(executed),
            body=body,
        )
        self._audit(request, result.status, result.reason_code)
        return result

    def _evaluate(
        self,
        request: ControlledExecutionRequest,
        gate_name: ProviderExecutionGate,
        gate: ProviderExecutionGatePort,
        executed: list[ProviderExecutionGate],
    ) -> ControlledExecutionResult | None:
        decision = gate.evaluate(request)
        executed.append(gate_name)
        if decision.allowed:
            return None
        result = ControlledExecutionResult(
            status=ControlledExecutionStatus.BLOCKED,
            blocked_gate=gate_name,
            reason_code=decision.reason_code,
            executed_gates=tuple(executed),
        )
        self._audit(request, result.status, result.reason_code)
        return result

    def _audit(
        self,
        request: ControlledExecutionRequest,
        status: ControlledExecutionStatus,
        reason_code: str,
    ) -> None:
        if self._audit_sink is not None:
            self._audit_sink.record(request, status, reason_code)


class OfflineProviderTransport:
    """Hard kill switch that performs no credential, DNS, socket, or client access."""

    def send(
        self,
        request: ControlledExecutionRequest,
        credential: object,
    ) -> ProviderTransportResult:
        del request, credential
        return ProviderTransportResult(
            status=ProviderTransportStatus.BLOCKED,
            reason_code="PROVIDER_NETWORK_OFFLINE",
        )
