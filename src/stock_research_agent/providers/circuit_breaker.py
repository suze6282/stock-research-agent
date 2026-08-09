"""Deterministic persisted Provider circuit breaker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_research_agent.db.models.providers import ProviderCircuitBreaker
from stock_research_agent.domain.providers.enums import ProviderCircuitStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    FrozenProviderContract,
)


class CircuitBreakerOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"


class CircuitBreakerScope(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID


class CircuitBreakerSnapshot(FrozenProviderContract):
    status: ProviderCircuitStatus
    failure_count: int = Field(ge=0)
    opened_at: AwareUtcDateTime | None
    half_open_probe_at: AwareUtcDateTime | None
    updated_at: AwareUtcDateTime


class CircuitBreakerDecision(FrozenProviderContract):
    allowed: bool
    status: ProviderCircuitStatus
    reason_code: str


class CircuitBreakerStore(Protocol):
    def load_for_update(
        self,
        scope: CircuitBreakerScope,
    ) -> CircuitBreakerSnapshot | None: ...

    def save(
        self,
        scope: CircuitBreakerScope,
        value: CircuitBreakerSnapshot,
    ) -> CircuitBreakerSnapshot: ...


class ProviderCircuitBreakerService:
    """Apply one finite state machine through a transaction-owned store."""

    def __init__(
        self,
        store: CircuitBreakerStore,
        *,
        failure_threshold: int,
        reset_after_seconds: int,
    ) -> None:
        if not 1 <= failure_threshold <= 100:
            raise ValueError("CIRCUIT_FAILURE_THRESHOLD_INVALID")
        if not 1 <= reset_after_seconds <= 86_400:
            raise ValueError("CIRCUIT_RESET_WINDOW_INVALID")
        self._store = store
        self._failure_threshold = failure_threshold
        self._reset_after = timedelta(seconds=reset_after_seconds)

    def before_call(
        self,
        scope: CircuitBreakerScope,
        now: AwareUtcDateTime,
    ) -> CircuitBreakerDecision:
        snapshot = self._store.load_for_update(scope)
        if snapshot is None:
            snapshot = self._store.save(scope, _closed(now))
        if snapshot.status is ProviderCircuitStatus.CLOSED:
            return CircuitBreakerDecision(
                allowed=True,
                status=snapshot.status,
                reason_code="PROVIDER_CIRCUIT_CLOSED",
            )
        if snapshot.status is ProviderCircuitStatus.HALF_OPEN:
            return CircuitBreakerDecision(
                allowed=False,
                status=snapshot.status,
                reason_code="PROVIDER_CIRCUIT_PROBE_IN_PROGRESS",
            )
        if snapshot.opened_at is not None and now >= snapshot.opened_at + self._reset_after:
            half_open = snapshot.model_copy(
                update={
                    "status": ProviderCircuitStatus.HALF_OPEN,
                    "half_open_probe_at": now,
                    "updated_at": now,
                }
            )
            self._store.save(scope, half_open)
            return CircuitBreakerDecision(
                allowed=True,
                status=ProviderCircuitStatus.HALF_OPEN,
                reason_code="PROVIDER_CIRCUIT_HALF_OPEN_PROBE",
            )
        return CircuitBreakerDecision(
            allowed=False,
            status=snapshot.status,
            reason_code="PROVIDER_CIRCUIT_OPEN",
        )

    def record_outcome(
        self,
        scope: CircuitBreakerScope,
        outcome: CircuitBreakerOutcome,
        now: AwareUtcDateTime,
    ) -> CircuitBreakerSnapshot:
        current = self._store.load_for_update(scope) or _closed(now)
        if outcome is CircuitBreakerOutcome.SUCCESS:
            target = _closed(now)
        elif outcome is CircuitBreakerOutcome.PERMANENT_FAILURE:
            target = current.model_copy(update={"updated_at": now})
        else:
            failure_count = current.failure_count + 1
            should_open = (
                current.status is ProviderCircuitStatus.HALF_OPEN
                or failure_count >= self._failure_threshold
            )
            target = current.model_copy(
                update={
                    "status": (
                        ProviderCircuitStatus.OPEN if should_open else ProviderCircuitStatus.CLOSED
                    ),
                    "failure_count": failure_count,
                    "opened_at": now if should_open else None,
                    "half_open_probe_at": None,
                    "updated_at": now,
                }
            )
        return self._store.save(scope, target)


class PostgresCircuitBreakerStore:
    """Atomic cross-process state backed by the Stage 9 circuit table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def load_for_update(
        self,
        scope: CircuitBreakerScope,
    ) -> CircuitBreakerSnapshot | None:
        row = self._session.scalar(
            select(ProviderCircuitBreaker)
            .where(
                ProviderCircuitBreaker.provider_definition_id == scope.provider_definition_id,
                ProviderCircuitBreaker.provider_capability_id == scope.provider_capability_id,
            )
            .with_for_update()
        )
        return None if row is None else _snapshot(row)

    def save(
        self,
        scope: CircuitBreakerScope,
        value: CircuitBreakerSnapshot,
    ) -> CircuitBreakerSnapshot:
        row = self._session.scalar(
            select(ProviderCircuitBreaker)
            .where(
                ProviderCircuitBreaker.provider_definition_id == scope.provider_definition_id,
                ProviderCircuitBreaker.provider_capability_id == scope.provider_capability_id,
            )
            .with_for_update()
        )
        if row is None:
            row = ProviderCircuitBreaker(
                provider_definition_id=scope.provider_definition_id,
                provider_capability_id=scope.provider_capability_id,
                status=value.status.value,
                failure_count=value.failure_count,
                opened_at=value.opened_at,
                half_open_probe_at=value.half_open_probe_at,
                updated_at=value.updated_at,
            )
            self._session.add(row)
        else:
            row.status = value.status.value
            row.failure_count = value.failure_count
            row.opened_at = value.opened_at
            row.half_open_probe_at = value.half_open_probe_at
            row.updated_at = value.updated_at
        self._session.flush()
        return _snapshot(row)


def _closed(now: datetime) -> CircuitBreakerSnapshot:
    return CircuitBreakerSnapshot(
        status=ProviderCircuitStatus.CLOSED,
        failure_count=0,
        opened_at=None,
        half_open_probe_at=None,
        updated_at=now,
    )


def _snapshot(row: ProviderCircuitBreaker) -> CircuitBreakerSnapshot:
    updated = row.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return CircuitBreakerSnapshot(
        status=ProviderCircuitStatus(row.status),
        failure_count=row.failure_count,
        opened_at=(
            None
            if row.opened_at is None
            else row.opened_at.replace(tzinfo=UTC)
            if row.opened_at.tzinfo is None
            else row.opened_at.astimezone(UTC)
        ),
        half_open_probe_at=(
            None
            if row.half_open_probe_at is None
            else row.half_open_probe_at.replace(tzinfo=UTC)
            if row.half_open_probe_at.tzinfo is None
            else row.half_open_probe_at.astimezone(UTC)
        ),
        updated_at=updated.astimezone(UTC),
    )
