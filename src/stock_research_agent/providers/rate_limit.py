"""Thread-safe monotonic provider rate limiting."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from stock_research_agent.db.models.providers import ProviderAuditEvent
from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    FrozenProviderContract,
)


class RateLimiter(Protocol):
    """Contract used by the provider HTTP boundary."""

    def acquire(self, bucket: str) -> None:
        """Wait until a request may use ``bucket``."""


class MonotonicRateLimiter:
    """Limit request starts independently for each named bucket."""

    def __init__(
        self,
        requests_per_second: float,
        *,
        monotonic: Callable[[], float],
        sleeper: Callable[[float], None],
    ) -> None:
        if requests_per_second <= 0 or not math.isfinite(requests_per_second):
            raise ValueError("requests_per_second must be positive and finite")
        self._interval = 1.0 / requests_per_second
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._deadlines: dict[str, float] = {}
        self._lock = threading.Lock()

    def acquire(self, bucket: str) -> None:
        """Wait until a request may use ``bucket``."""
        with self._lock:
            now = self._monotonic()
            deadline = self._deadlines.get(bucket, now)
            wait = max(0.0, deadline - now)
            self._deadlines[bucket] = max(now, deadline) + self._interval
        if wait > 0:
            self._sleeper(wait)


class ProviderRateLimitScope(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    credential_reference_id: UUID | None
    project_rate_per_second: Decimal
    official_max_rate_per_second: Decimal

    @model_validator(mode="after")
    def validate_rates(self) -> ProviderRateLimitScope:
        rates = (
            self.project_rate_per_second,
            self.official_max_rate_per_second,
        )
        if any(not value.is_finite() or value <= 0 for value in rates):
            raise ValueError("Provider rates must be positive and finite")
        if self.project_rate_per_second >= self.official_max_rate_per_second:
            raise ValueError("project rate must be strictly below official maximum")
        return self

    def checksum(self) -> str:
        return provider_checksum(self.model_dump(mode="json"))


class RateLimitDecision(FrozenProviderContract):
    allowed: bool
    reason_code: str
    retry_after_seconds: Decimal = Field(ge=0)
    scope_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class RateLimitReservationStore(Protocol):
    def reserve_slot(
        self,
        scope_checksum: str,
        provider_definition_id: UUID,
        now: datetime,
        minimum_interval_seconds: Decimal,
    ) -> bool: ...


class ProviderRateLimiter:
    """Coordinate finite Provider reservations through an injected store."""

    def __init__(self, store: RateLimitReservationStore) -> None:
        self._store = store

    def reserve(
        self,
        scope: ProviderRateLimitScope,
        now: AwareUtcDateTime,
        units: int,
    ) -> RateLimitDecision:
        if not 1 <= units <= 100:
            raise ValueError("PROVIDER_RATE_LIMIT_UNITS_INVALID")
        interval = Decimal(units) / scope.project_rate_per_second
        checksum = scope.checksum()
        allowed = self._store.reserve_slot(
            checksum,
            scope.provider_definition_id,
            now,
            interval,
        )
        return RateLimitDecision(
            allowed=allowed,
            reason_code=("PROVIDER_RATE_RESERVED" if allowed else "PROVIDER_RATE_LIMITED"),
            retry_after_seconds=Decimal(0) if allowed else interval,
            scope_checksum=checksum,
        )


class PostgresRateLimitReservationStore:
    """Serialize reservations with a transaction-scoped advisory lock."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def reserve_slot(
        self,
        scope_checksum: str,
        provider_definition_id: UUID,
        now: datetime,
        minimum_interval_seconds: Decimal,
    ) -> bool:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": scope_checksum},
        )
        decision_code = f"RATE_{scope_checksum}"
        previous = self._session.scalar(
            select(ProviderAuditEvent.created_at)
            .where(
                ProviderAuditEvent.provider_definition_id == provider_definition_id,
                ProviderAuditEvent.action_code == "RATE_LIMIT_RESERVATION",
                ProviderAuditEvent.decision_code == decision_code,
            )
            .order_by(ProviderAuditEvent.created_at.desc(), ProviderAuditEvent.id.desc())
            .limit(1)
        )
        if previous is not None:
            elapsed = Decimal(str((now - previous).total_seconds()))
            if elapsed < minimum_interval_seconds:
                return False
        event_checksum = provider_checksum(
            {
                "provider_definition_id": str(provider_definition_id),
                "scope_checksum": scope_checksum,
                "reserved_at": now.isoformat(),
            }
        )
        self._session.add(
            ProviderAuditEvent(
                provider_definition_id=provider_definition_id,
                sync_run_id=None,
                actor_type="SYSTEM",
                action_code="RATE_LIMIT_RESERVATION",
                decision_code=decision_code,
                safe_summary="Rate limit reservation",
                event_checksum=event_checksum,
                created_at=now,
            )
        )
        self._session.flush()
        return True
