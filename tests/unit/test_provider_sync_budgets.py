from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from stock_research_agent.providers.control_plane import (
    InMemoryProviderBudgetStore,
    ProviderBudgetLedger,
    ProviderBudgetSnapshot,
)

NOW = datetime(2026, 7, 29, 12, tzinfo=UTC)


def test_budget_reservation_is_hard_and_never_resets() -> None:
    run_id = uuid4()
    store = InMemoryProviderBudgetStore(
        {
            run_id: ProviderBudgetSnapshot(
                run_id=run_id,
                max_requests=2,
                max_bytes=10,
                max_attempts=2,
                max_duration_seconds=60,
                consumed_requests=1,
                consumed_bytes=4,
                consumed_attempts=1,
                started_at=NOW,
            )
        }
    )
    ledger = ProviderBudgetLedger(store, clock=lambda: NOW + timedelta(seconds=1))
    allowed = ledger.reserve(run_id, request_bytes=6)
    blocked = ledger.reserve(run_id, request_bytes=1)
    assert allowed.allowed is True
    assert allowed.consumed_requests == 2
    assert allowed.consumed_bytes == 10
    assert blocked.allowed is False
    assert blocked.reason_code == "PROVIDER_BUDGET_EXHAUSTED"
    assert blocked.consumed_requests == 2
    assert blocked.consumed_bytes == 10


def test_duration_exhaustion_does_not_mutate_counters() -> None:
    run_id = uuid4()
    snapshot = ProviderBudgetSnapshot(
        run_id=run_id,
        max_requests=2,
        max_bytes=10,
        max_attempts=2,
        max_duration_seconds=1,
        consumed_requests=0,
        consumed_bytes=0,
        consumed_attempts=0,
        started_at=NOW,
    )
    ledger = ProviderBudgetLedger(
        InMemoryProviderBudgetStore({run_id: snapshot}),
        clock=lambda: NOW + timedelta(seconds=2),
    )
    result = ledger.reserve(run_id, request_bytes=1)
    assert result.allowed is False
    assert result.reason_code == "PROVIDER_DURATION_EXHAUSTED"
    assert result.consumed_requests == 0
