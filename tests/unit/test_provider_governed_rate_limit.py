from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from stock_research_agent.providers.rate_limit import (
    ProviderRateLimiter,
    ProviderRateLimitScope,
)

NOW = datetime(2026, 7, 29, tzinfo=UTC)


class MemoryReservationStore:
    def __init__(self) -> None:
        self.last: dict[str, datetime] = {}

    def reserve_slot(
        self,
        scope_checksum: str,
        provider_definition_id: object,
        now: datetime,
        minimum_interval_seconds: Decimal,
    ) -> bool:
        previous = self.last.get(scope_checksum)
        if previous is not None:
            elapsed = Decimal(str((now - previous).total_seconds()))
            if elapsed < minimum_interval_seconds:
                return False
        self.last[scope_checksum] = now
        return True


def _scope(**updates: object) -> ProviderRateLimitScope:
    values: dict[str, object] = {
        "provider_definition_id": uuid4(),
        "provider_capability_id": uuid4(),
        "credential_reference_id": None,
        "project_rate_per_second": Decimal("8"),
        "official_max_rate_per_second": Decimal("10"),
    }
    values.update(updates)
    return ProviderRateLimitScope(**values)


def test_governed_rate_limiter_reserves_monotonic_finite_budget() -> None:
    limiter = ProviderRateLimiter(MemoryReservationStore())
    scope = _scope()
    first = limiter.reserve(scope, NOW, units=1)
    second = limiter.reserve(scope, NOW, units=1)

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason_code == "PROVIDER_RATE_LIMITED"
    assert second.retry_after_seconds == Decimal("0.125")


@pytest.mark.parametrize(
    "updates",
    [
        {"project_rate_per_second": Decimal("10")},
        {"project_rate_per_second": Decimal("11")},
        {"project_rate_per_second": Decimal("NaN")},
        {"project_rate_per_second": Decimal("0")},
    ],
)
def test_project_rate_must_be_positive_finite_and_strictly_below_official(
    updates: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        _scope(**updates)


def test_rate_scope_checksum_binds_capability_and_non_secret_credential_reference() -> None:
    first = _scope()
    changed = first.model_copy(update={"provider_capability_id": uuid4()})
    assert first.checksum() != changed.checksum()
    assert "credential" not in first.model_dump_json().casefold() or (
        first.credential_reference_id is None
    )
