from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from stock_research_agent.db.repositories.providers import SqlAlchemyProviderSyncRepository
from stock_research_agent.domain.providers.enums import ProviderRunStatus
from stock_research_agent.domain.providers.sync import (
    ProviderExecutionMode,
    ProviderRunTransition,
    ProviderSyncPlanWrite,
    ProviderSyncRequestWrite,
    ProviderSyncRunWrite,
)
from stock_research_agent.providers.control_plane import (
    PostgresProviderBudgetStore,
    ProviderBudgetLedger,
)
from tests.integration.test_provider_sync_repository_postgres import _governance

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Provider budget tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


def test_concurrent_reservation_cannot_oversubscribe_remaining_budget() -> None:
    assert TEST_DATABASE_URL is not None
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(TEST_DATABASE_URL)
    now = datetime(2026, 7, 29, 12, tzinfo=UTC)
    suffix = uuid4().hex
    with Session(engine) as session, session.begin():
        definition, capability, policy, license_policy = _governance(session)
        repository = SqlAlchemyProviderSyncRepository(session)
        request = repository.create_request(
            ProviderSyncRequestWrite(
                provider_definition_id=definition.id,
                provider_capability_id=capability.id,
                policy_id=policy.id,
                license_policy_id=license_policy.id,
                credential_reference_id=None,
                security_id=None,
                universe_code=f"BUDGET_{suffix}",
                research_as_of_time=now,
                range_start=date(2026, 7, 29),
                range_end=date(2026, 7, 29),
                execution_mode=ProviderExecutionMode.OFFLINE,
                scope={"universe_code": f"BUDGET_{suffix}"},
                budget={
                    "max_requests": 1,
                    "max_bytes": 10,
                    "max_attempts": 1,
                    "max_duration_seconds": 60,
                },
                request_checksum="8" * 64,
                idempotency_key=uuid4().hex * 2,
            )
        )
        plan = repository.add_plan(
            ProviderSyncPlanWrite(
                sync_request_id=request.id,
                adapter_version="1.0.0",
                slices=({"slice_id": "ONE"},),
                plan_checksum="a" * 64,
            )
        )
        run = repository.create_run(
            ProviderSyncRunWrite(
                sync_request_id=request.id,
                sync_plan_id=plan.id,
                provider_definition_id=definition.id,
                provider_capability_id=capability.id,
            )
        )
        run = repository.transition(
            run.id,
            ProviderRunTransition(target=ProviderRunStatus.QUEUED),
        )
        repository.transition(
            run.id,
            ProviderRunTransition(target=ProviderRunStatus.RUNNING, started_at=now),
        )

    barrier = Barrier(2)

    def reserve() -> bool:
        with Session(engine) as session, session.begin():
            barrier.wait()
            return (
                ProviderBudgetLedger(
                    PostgresProviderBudgetStore(session),
                    clock=lambda: now,
                )
                .reserve(run.id, request_bytes=10)
                .allowed
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: reserve(), range(2)))
    assert sorted(results) == [False, True]
    engine.dispose()
