from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session

from stock_research_agent.db.models.providers import ProviderCacheEntry
from stock_research_agent.db.repositories.providers import (
    SqlAlchemyProviderArtifactRepository,
    SqlAlchemyProviderSyncRepository,
)
from stock_research_agent.domain.providers.artifacts import ProviderRawArtifactWrite
from stock_research_agent.domain.providers.enums import (
    ProviderSyncSliceStatus,
    ProviderSyntheticStatus,
)
from stock_research_agent.domain.providers.sync import (
    ProviderExecutionMode,
    ProviderRequestAttemptWrite,
    ProviderSyncPlanWrite,
    ProviderSyncRequestWrite,
    ProviderSyncRunWrite,
)
from stock_research_agent.providers.cache import (
    PostgresProviderCacheStore,
    ProviderCacheKey,
    ProviderCacheService,
    ProviderCacheStatus,
)
from tests.integration.test_provider_sync_repository_postgres import _governance

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Provider cache tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(Config("alembic.ini"), "head")
    value = create_engine(TEST_DATABASE_URL)
    yield value
    value.dispose()


def test_postgres_cache_updates_one_transactional_pointer_and_respects_expiry(
    engine: Engine,
) -> None:
    now = datetime(2026, 7, 29, 12, tzinfo=UTC)
    with Session(engine) as session, session.begin():
        definition, capability, policy, license_policy = _governance(session)
        sync = SqlAlchemyProviderSyncRepository(session)
        request = sync.create_request(
            ProviderSyncRequestWrite(
                provider_definition_id=definition.id,
                provider_capability_id=capability.id,
                policy_id=policy.id,
                license_policy_id=license_policy.id,
                credential_reference_id=None,
                security_id=None,
                universe_code=f"CACHE_{uuid4().hex}",
                research_as_of_time=now,
                range_start=date(2026, 7, 29),
                range_end=date(2026, 7, 29),
                execution_mode=ProviderExecutionMode.OFFLINE,
                scope={"kind": "CACHE_TEST"},
                budget={
                    "max_requests": 1,
                    "max_bytes": 1_000_000,
                    "max_attempts": 1,
                    "max_duration_seconds": 60,
                },
                request_checksum="1" * 64,
                idempotency_key=uuid4().hex * 2,
            )
        )
        plan = sync.add_plan(
            ProviderSyncPlanWrite(
                sync_request_id=request.id,
                adapter_version="1.0.0",
                slices=({"slice_id": "ONE"},),
                plan_checksum="2" * 64,
            )
        )
        run = sync.create_run(
            ProviderSyncRunWrite(
                sync_request_id=request.id,
                sync_plan_id=plan.id,
                provider_definition_id=definition.id,
                provider_capability_id=capability.id,
            )
        )
        attempt = sync.append_attempt(
            ProviderRequestAttemptWrite(
                sync_run_id=run.id,
                slice_id="ONE",
                attempt_number=1,
                status=ProviderSyncSliceStatus.COMPLETED,
                endpoint_id="OFFLINE_FIXTURE",
                response_status_code=200,
                response_bytes=1,
                started_at=now,
                completed_at=now,
            )
        )
        artifact = SqlAlchemyProviderArtifactRepository(session).add_artifact(
            ProviderRawArtifactWrite(
                provider_definition_id=definition.id,
                provider_capability_id=capability.id,
                sync_run_id=run.id,
                request_attempt_id=attempt.id,
                license_policy_id=license_policy.id,
                source_identity=f"cache:{uuid4().hex}",
                source_checksum="3" * 64,
                byte_count=1,
                content_type="application/json",
                blob_key=f"cache/{uuid4().hex}.json",
                acquired_at=now,
                source_published_at=now,
                synthetic_status=ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
            )
        )
        key = ProviderCacheKey(
            provider_definition_id=definition.id,
            provider_capability_id=capability.id,
            license_policy_id=license_policy.id,
            adapter_version=definition.adapter_version,
            policy_version=definition.policy_version,
            license_policy_version=definition.license_policy_version,
            request_identity="4" * 64,
        )
        service = ProviderCacheService(PostgresProviderCacheStore(session))
        first = service.put(
            key,
            artifact_id=artifact.id,
            artifact_checksum=artifact.source_checksum,
            expires_at=now + timedelta(minutes=5),
            now=now,
            cache_permitted=True,
        )
        second = service.put(
            key,
            artifact_id=artifact.id,
            artifact_checksum=artifact.source_checksum,
            expires_at=now + timedelta(minutes=10),
            now=now,
            cache_permitted=True,
        )
        assert first.status is ProviderCacheStatus.STORED
        assert second.status is ProviderCacheStatus.STORED
        assert session.scalar(select(func.count()).select_from(ProviderCacheEntry)) == 1
        assert service.get(key, now=now).status is ProviderCacheStatus.HIT
        assert service.get(key, now=now + timedelta(minutes=10)).status is ProviderCacheStatus.MISS
