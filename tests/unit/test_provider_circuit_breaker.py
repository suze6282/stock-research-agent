from datetime import UTC, datetime, timedelta
from uuid import uuid4

from stock_research_agent.domain.providers.enums import ProviderCircuitStatus
from stock_research_agent.providers.circuit_breaker import (
    CircuitBreakerOutcome,
    CircuitBreakerScope,
    CircuitBreakerSnapshot,
    ProviderCircuitBreakerService,
)

NOW = datetime(2026, 7, 29, tzinfo=UTC)


class MemoryCircuitStore:
    def __init__(self) -> None:
        self.value: CircuitBreakerSnapshot | None = None

    def load_for_update(
        self,
        _scope: CircuitBreakerScope,
    ) -> CircuitBreakerSnapshot | None:
        return self.value

    def save(
        self,
        _scope: CircuitBreakerScope,
        value: CircuitBreakerSnapshot,
    ) -> CircuitBreakerSnapshot:
        self.value = value
        return value


def _scope() -> CircuitBreakerScope:
    return CircuitBreakerScope(
        provider_definition_id=uuid4(),
        provider_capability_id=uuid4(),
    )


def test_circuit_opens_at_threshold_and_success_closes_it() -> None:
    store = MemoryCircuitStore()
    service = ProviderCircuitBreakerService(
        store,
        failure_threshold=2,
        reset_after_seconds=30,
    )
    scope = _scope()

    first = service.record_outcome(scope, CircuitBreakerOutcome.TRANSIENT_FAILURE, NOW)
    second = service.record_outcome(scope, CircuitBreakerOutcome.TRANSIENT_FAILURE, NOW)
    assert first.status is ProviderCircuitStatus.CLOSED
    assert second.status is ProviderCircuitStatus.OPEN
    blocked = service.before_call(scope, NOW + timedelta(seconds=1))
    assert blocked.allowed is False

    success = service.record_outcome(scope, CircuitBreakerOutcome.SUCCESS, NOW)
    assert success.status is ProviderCircuitStatus.CLOSED
    assert success.failure_count == 0


def test_only_expired_open_circuit_enters_half_open_probe() -> None:
    store = MemoryCircuitStore()
    service = ProviderCircuitBreakerService(
        store,
        failure_threshold=1,
        reset_after_seconds=30,
    )
    scope = _scope()
    service.record_outcome(scope, CircuitBreakerOutcome.TRANSIENT_FAILURE, NOW)

    probe = service.before_call(scope, NOW + timedelta(seconds=30))
    second = service.before_call(scope, NOW + timedelta(seconds=30))
    assert probe.allowed is True
    assert probe.status is ProviderCircuitStatus.HALF_OPEN
    assert second.allowed is False
    assert second.reason_code == "PROVIDER_CIRCUIT_PROBE_IN_PROGRESS"


def test_permanent_governance_failure_does_not_poison_circuit() -> None:
    store = MemoryCircuitStore()
    service = ProviderCircuitBreakerService(
        store,
        failure_threshold=1,
        reset_after_seconds=30,
    )
    result = service.record_outcome(
        _scope(),
        CircuitBreakerOutcome.PERMANENT_FAILURE,
        NOW,
    )
    assert result.status is ProviderCircuitStatus.CLOSED
    assert result.failure_count == 0
