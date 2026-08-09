from __future__ import annotations

from dataclasses import dataclass

import pytest

from stock_research_agent.providers.http_executor import (
    ControlledExecutionRequest,
    ControlledExecutionStatus,
    DefaultControlledProviderExecutor,
    ProviderExecutionGate,
    ProviderGateDecision,
)

GOVERNANCE_GATES = (
    ProviderExecutionGate.DEFINITION,
    ProviderExecutionGate.CAPABILITY,
    ProviderExecutionGate.LICENSE,
    ProviderExecutionGate.PROVIDER_POLICY,
    ProviderExecutionGate.CREDENTIAL_REFERENCE,
    ProviderExecutionGate.CONFIGURATION_VALIDATION,
    ProviderExecutionGate.LIVE_AUTHORIZATION,
    ProviderExecutionGate.NETWORK,
)
OPERATIONAL_GATES = (
    ProviderExecutionGate.CIRCUIT,
    ProviderExecutionGate.ENDPOINT,
    ProviderExecutionGate.RATE_LIMIT,
    ProviderExecutionGate.CACHE,
)


@dataclass
class SpyGate:
    name: ProviderExecutionGate
    calls: list[str]
    blocked: ProviderExecutionGate | None = None

    def evaluate(self, request: ControlledExecutionRequest) -> ProviderGateDecision:
        del request
        self.calls.append(self.name.value)
        return ProviderGateDecision(
            allowed=self.name is not self.blocked,
            reason_code=(
                f"{self.name.value}_ALLOWED"
                if self.name is not self.blocked
                else f"{self.name.value}_BLOCKED"
            ),
        )


class SpyCredentialResolver:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def resolve(self, request: ControlledExecutionRequest) -> object:
        del request
        self.calls.append("SECRET_RESOLUTION")
        return object()


class SpyTransport:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def send(self, request: ControlledExecutionRequest, credential: object) -> bytes:
        del request, credential
        self.calls.append("TRANSPORT")
        return b"offline-test"


def _executor(
    calls: list[str],
    blocked: ProviderExecutionGate | None = None,
) -> DefaultControlledProviderExecutor:
    gates = {
        name: SpyGate(name=name, calls=calls, blocked=blocked)
        for name in (*GOVERNANCE_GATES, *OPERATIONAL_GATES)
    }
    return DefaultControlledProviderExecutor(
        definition_gate=gates[ProviderExecutionGate.DEFINITION],
        capability_gate=gates[ProviderExecutionGate.CAPABILITY],
        license_gate=gates[ProviderExecutionGate.LICENSE],
        provider_policy_gate=gates[ProviderExecutionGate.PROVIDER_POLICY],
        credential_reference_gate=gates[ProviderExecutionGate.CREDENTIAL_REFERENCE],
        configuration_gate=gates[ProviderExecutionGate.CONFIGURATION_VALIDATION],
        live_authorization_gate=gates[ProviderExecutionGate.LIVE_AUTHORIZATION],
        network_gate=gates[ProviderExecutionGate.NETWORK],
        credential_resolver=SpyCredentialResolver(calls),
        circuit_gate=gates[ProviderExecutionGate.CIRCUIT],
        endpoint_gate=gates[ProviderExecutionGate.ENDPOINT],
        rate_limit_gate=gates[ProviderExecutionGate.RATE_LIMIT],
        cache_gate=gates[ProviderExecutionGate.CACHE],
        transport=SpyTransport(calls),
    )


@pytest.mark.parametrize("blocked", GOVERNANCE_GATES)
def test_each_governance_block_stops_all_later_gates_and_secret_access(
    blocked: ProviderExecutionGate,
) -> None:
    calls: list[str] = []
    result = _executor(calls, blocked).execute(ControlledExecutionRequest(request_id="REQUEST_001"))

    assert result.status is ControlledExecutionStatus.BLOCKED
    assert result.blocked_gate is blocked
    assert calls == [gate.value for gate in GOVERNANCE_GATES[: GOVERNANCE_GATES.index(blocked) + 1]]
    assert "SECRET_RESOLUTION" not in calls
    assert "TRANSPORT" not in calls


def test_success_uses_exact_gate_order_before_credentials_and_transport() -> None:
    calls: list[str] = []
    result = _executor(calls).execute(ControlledExecutionRequest(request_id="REQUEST_001"))

    assert result.status is ControlledExecutionStatus.COMPLETED
    assert result.body == b"offline-test"
    assert calls == [
        *(gate.value for gate in GOVERNANCE_GATES),
        "SECRET_RESOLUTION",
        *(gate.value for gate in OPERATIONAL_GATES),
        "TRANSPORT",
    ]


def test_operational_block_never_reaches_transport() -> None:
    calls: list[str] = []
    result = _executor(calls, ProviderExecutionGate.CIRCUIT).execute(
        ControlledExecutionRequest(request_id="REQUEST_001")
    )
    assert result.status is ControlledExecutionStatus.BLOCKED
    assert result.blocked_gate is ProviderExecutionGate.CIRCUIT
    assert "TRANSPORT" not in calls
