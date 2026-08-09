from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from stock_research_agent.db.repositories.providers import (
    SqlAlchemyProviderDefinitionRepository,
)
from stock_research_agent.domain.providers.enums import (
    ProviderDefinitionStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.schemas import ProviderDefinitionWrite
from stock_research_agent.providers.rate_limit import (
    PostgresRateLimitReservationStore,
    ProviderRateLimiter,
    ProviderRateLimitScope,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for rate-limit tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


def test_concurrent_postgres_rate_limit_reservations_have_one_winner() -> None:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(TEST_DATABASE_URL)
    suffix = datetime.now(tz=UTC).strftime("%H%M%S%f")
    with Session(engine) as session, session.begin():
        definition = SqlAlchemyProviderDefinitionRepository(session).add_definition(
            ProviderDefinitionWrite(
                code=f"RATE_{suffix}",
                definition_version="1.0.0",
                adapter_version="1.0.0",
                display_name="Rate Test",
                data_domain="MARKET_DATA",
                definition_status=ProviderDefinitionStatus.ACTIVE,
                production_status=ProviderProductionStatus.TEST_ONLY,
                official_domains=("example.com",),
                policy_version="1.0.0",
                license_policy_version="1.0.0",
                credential_reference_id=None,
                source_register_version="1.0.0",
            )
        )
    scope = ProviderRateLimitScope(
        provider_definition_id=definition.id,
        provider_capability_id=definition.id,
        credential_reference_id=None,
        project_rate_per_second=Decimal("1"),
        official_max_rate_per_second=Decimal("2"),
    )
    barrier = Barrier(2)
    now = datetime.now(tz=UTC)

    def reserve() -> bool:
        with Session(engine) as session, session.begin():
            barrier.wait()
            decision = ProviderRateLimiter(PostgresRateLimitReservationStore(session)).reserve(
                scope, now, units=1
            )
            return decision.allowed

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _value: reserve(), range(2)))
    assert sorted(results) == [False, True]
    engine.dispose()
