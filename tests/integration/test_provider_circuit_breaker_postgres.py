from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from stock_research_agent.db.repositories.providers import (
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
)
from stock_research_agent.domain.providers.capabilities import ProviderCapabilityWrite
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderCircuitStatus,
    ProviderDefinitionStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.schemas import ProviderDefinitionWrite
from stock_research_agent.providers.circuit_breaker import (
    CircuitBreakerOutcome,
    CircuitBreakerScope,
    PostgresCircuitBreakerStore,
    ProviderCircuitBreakerService,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for circuit tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


def test_postgres_circuit_allows_only_one_half_open_probe() -> None:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(TEST_DATABASE_URL)
    suffix = datetime.now(tz=UTC).strftime("%H%M%S%f")
    opened_at = datetime.now(tz=UTC) - timedelta(seconds=60)
    with Session(engine) as session, session.begin():
        definition = SqlAlchemyProviderDefinitionRepository(session).add_definition(
            ProviderDefinitionWrite(
                code=f"CIRCUIT_{suffix}",
                definition_version="1.0.0",
                adapter_version="1.0.0",
                display_name="Circuit Test",
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
        capability = SqlAlchemyProviderGovernanceRepository(session).add_capability(
            ProviderCapabilityWrite(
                provider_definition_id=definition.id,
                code="CIRCUIT_TEST",
                capability_version="1.0.0",
                status=ProviderCapabilityStatus.IMPLEMENTED_OFFLINE,
                data_domain="MARKET_DATA",
                market_codes=("US_EQUITY",),
                security_types=("COMMON_STOCK",),
                operations=("READ_OFFLINE_FIXTURE",),
            )
        )
        scope = CircuitBreakerScope(
            provider_definition_id=definition.id,
            provider_capability_id=capability.id,
        )
        service = ProviderCircuitBreakerService(
            PostgresCircuitBreakerStore(session),
            failure_threshold=1,
            reset_after_seconds=30,
        )
        opened = service.record_outcome(
            scope,
            CircuitBreakerOutcome.TRANSIENT_FAILURE,
            opened_at,
        )
        assert opened.status is ProviderCircuitStatus.OPEN

    barrier = Barrier(2)
    probe_at = datetime.now(tz=UTC)

    def before_call() -> bool:
        with Session(engine) as session, session.begin():
            barrier.wait()
            return (
                ProviderCircuitBreakerService(
                    PostgresCircuitBreakerStore(session),
                    failure_threshold=1,
                    reset_after_seconds=30,
                )
                .before_call(scope, probe_at)
                .allowed
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: before_call(), range(2)))
    assert sorted(results) == [False, True]
    engine.dispose()
