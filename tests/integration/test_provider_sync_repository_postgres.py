from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from stock_research_agent.db.models import ProviderRequestAttempt
from stock_research_agent.db.repositories.providers import (
    ProviderRepositoryConflict,
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
    SqlAlchemyProviderSyncRepository,
)
from stock_research_agent.domain.providers import sync as sync_contracts
from stock_research_agent.domain.providers.capabilities import ProviderCapabilityWrite
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderDefinitionStatus,
    ProviderLicenseStatus,
    ProviderProductionStatus,
    ProviderRunStatus,
    ProviderSyncSliceStatus,
)
from stock_research_agent.domain.providers.licenses import (
    LicensePermission,
    SourceLicensePolicyWrite,
)
from stock_research_agent.domain.providers.policies import ProviderPolicyWrite
from stock_research_agent.domain.providers.schemas import ProviderDefinitionWrite
from stock_research_agent.domain.providers.sync import (
    ProviderExecutionMode,
    ProviderRequestAttemptWrite,
    ProviderRunTransition,
    ProviderSyncPlanWrite,
    ProviderSyncRequestWrite,
    ProviderSyncRunWrite,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Provider sync tests")

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


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    value = Session(bind=connection)
    try:
        yield value
    finally:
        value.close()
        transaction.rollback()
        connection.close()


def _governance(session: Session) -> tuple[object, object, object, object]:
    definition = SqlAlchemyProviderDefinitionRepository(session).add_definition(
        ProviderDefinitionWrite(
            code="SYNC_TEST",
            definition_version="1.0.0",
            adapter_version="1.0.0",
            display_name="Sync Test",
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
    governance = SqlAlchemyProviderGovernanceRepository(session)
    capability = governance.add_capability(
        ProviderCapabilityWrite(
            provider_definition_id=definition.id,
            code="DAILY_PRICE",
            capability_version="1.0.0",
            status=ProviderCapabilityStatus.IMPLEMENTED_OFFLINE,
            data_domain="MARKET_DATA",
            market_codes=("US_EQUITY",),
            security_types=("COMMON_STOCK",),
            operations=("READ_OFFLINE_FIXTURE",),
        )
    )
    policy = governance.add_policy(
        ProviderPolicyWrite(
            provider_definition_id=definition.id,
            policy_version="1.0.0",
            endpoint_policy_version="1.0.0",
            network_enabled=False,
            max_requests=10,
            max_response_bytes=1024,
            max_total_bytes=4096,
            max_duration_seconds=30,
            max_attempts=1,
            max_redirects=0,
            rate_limit_per_second=Decimal("1"),
            retry_base_delay_seconds=Decimal("1"),
            cache_enabled=False,
            cache_ttl_seconds=None,
            retention_days=30,
        )
    )
    license_policy = governance.add_license_policy(
        SourceLicensePolicyWrite(
            provider_definition_id=definition.id,
            policy_version="1.0.0",
            status=ProviderLicenseStatus.APPROVED,
            acquisition=LicensePermission.ALLOWED,
            raw_storage=LicensePermission.ALLOWED,
            cache=LicensePermission.PROHIBITED,
            derived_use=LicensePermission.ALLOWED,
            redistribution=LicensePermission.PROHIBITED,
            retention_days=30,
            deletion_required=False,
            attribution_required=True,
            terms_source_ids=("TEST_TERMS",),
            reviewed_at=datetime(2026, 7, 29, tzinfo=UTC),
            expires_at=None,
        )
    )
    return definition, capability, policy, license_policy


def test_sync_repository_persists_idempotent_request_plan_run_and_attempt(
    session: Session,
) -> None:
    definition, capability, policy, license_policy = _governance(session)
    repository = SqlAlchemyProviderSyncRepository(session)
    request_value = ProviderSyncRequestWrite(
        provider_definition_id=definition.id,
        provider_capability_id=capability.id,
        policy_id=policy.id,
        license_policy_id=license_policy.id,
        credential_reference_id=None,
        security_id=None,
        universe_code="TEST_UNIVERSE",
        research_as_of_time=datetime(2026, 7, 29, tzinfo=UTC),
        range_start=date(2026, 7, 1),
        range_end=date(2026, 7, 29),
        execution_mode=ProviderExecutionMode.OFFLINE,
        scope={"universe_code": "TEST_UNIVERSE"},
        budget={
            "max_requests": 1,
            "max_bytes": 1_000_000,
            "max_attempts": 1,
            "max_duration_seconds": 60,
        },
        request_checksum="1" * 64,
        idempotency_key="2" * 64,
    )
    request = repository.create_request(request_value)
    assert repository.create_request(request_value).id == request.id
    plan = repository.add_plan(
        ProviderSyncPlanWrite(
            sync_request_id=request.id,
            adapter_version="1.0.0",
            checkpoint_revision=None,
            slices=({"slice_id": "ONE"},),
            plan_checksum="3" * 64,
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
    assert repository.get_run(run.id, for_update=True) == run
    queued = repository.transition(
        run.id,
        ProviderRunTransition(target=ProviderRunStatus.QUEUED),
    )
    assert queued.status is ProviderRunStatus.QUEUED
    attempt = repository.append_attempt(
        ProviderRequestAttemptWrite(
            sync_run_id=run.id,
            slice_id="ONE",
            attempt_number=1,
            status=ProviderSyncSliceStatus.PENDING,
            endpoint_id="OFFLINE_FIXTURE",
            response_status_code=None,
            response_bytes=0,
            started_at=datetime(2026, 7, 29, tzinfo=UTC),
        )
    )
    assert (
        repository.append_attempt(
            ProviderRequestAttemptWrite(
                **attempt.model_dump(mode="python", exclude={"id", "created_at"})
            )
        ).id
        == attempt.id
    )
    assert session.in_transaction()


def _attempt_lineage(session: Session) -> tuple[SqlAlchemyProviderSyncRepository, object]:
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
            universe_code="ATTEMPT_TEST_UNIVERSE",
            research_as_of_time=datetime(2026, 8, 20, tzinfo=UTC),
            range_start=date(2026, 8, 20),
            range_end=date(2026, 8, 20),
            execution_mode=ProviderExecutionMode.OFFLINE,
            scope={"universe_code": "ATTEMPT_TEST_UNIVERSE"},
            budget={
                "max_requests": 1,
                "max_bytes": 1_000_000,
                "max_attempts": 1,
                "max_duration_seconds": 60,
            },
            request_checksum="8" * 64,
            idempotency_key="9" * 64,
        )
    )
    plan = repository.add_plan(
        ProviderSyncPlanWrite(
            sync_request_id=request.id,
            adapter_version="1.0.0",
            checkpoint_revision=None,
            slices=({"slice_id": "ATTEMPT_ONE"},),
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
    return repository, run


def _attempt_write(run_id: object) -> ProviderRequestAttemptWrite:
    return ProviderRequestAttemptWrite(
        sync_run_id=run_id,
        slice_id="ATTEMPT_ONE",
        attempt_number=1,
        status=ProviderSyncSliceStatus.PENDING,
        endpoint_id="OFFLINE_FIXTURE",
        response_status_code=None,
        response_bytes=0,
        started_at=datetime(2026, 8, 20, tzinfo=UTC),
    )


def test_attempt_repository_accepts_preallocated_id_and_settles_same_row(
    session: Session,
) -> None:
    reservation_type = sync_contracts.ProviderRequestAttemptReservation
    settlement_type = sync_contracts.ProviderRequestAttemptSettlement
    repository, run = _attempt_lineage(session)
    attempt_id = UUID("80000000-0000-0000-0000-000000000001")

    reserved = repository.reserve_attempt(
        reservation_type(id=attempt_id, value=_attempt_write(run.id))
    )
    settled = repository.settle_attempt(
        settlement_type(
            id=attempt_id,
            status=ProviderSyncSliceStatus.COMPLETED,
            response_status_code=200,
            response_bytes=128,
            completed_at=datetime(2026, 8, 20, 0, 0, 1, tzinfo=UTC),
            safe_error_code=None,
        )
    )

    assert reserved.id == attempt_id
    assert settled.id == attempt_id
    assert settled.status is ProviderSyncSliceStatus.COMPLETED
    assert settled.response_status_code == 200
    assert settled.response_bytes == 128


def test_attempt_settlement_is_idempotent_and_conflict_fails_closed(
    session: Session,
) -> None:
    reservation_type = sync_contracts.ProviderRequestAttemptReservation
    settlement_type = sync_contracts.ProviderRequestAttemptSettlement
    repository, run = _attempt_lineage(session)
    attempt_id = UUID("80000000-0000-0000-0000-000000000002")
    repository.reserve_attempt(reservation_type(id=attempt_id, value=_attempt_write(run.id)))
    settlement = settlement_type(
        id=attempt_id,
        status=ProviderSyncSliceStatus.BLOCKED,
        response_status_code=429,
        response_bytes=0,
        completed_at=datetime(2026, 8, 20, 0, 0, 1, tzinfo=UTC),
        safe_error_code="SEC_HTTP_429_ABORT",
    )

    first = repository.settle_attempt(settlement)
    assert repository.settle_attempt(settlement) == first
    with pytest.raises(
        ProviderRepositoryConflict,
        match="PROVIDER_ATTEMPT_SETTLEMENT_CONFLICT",
    ):
        repository.settle_attempt(settlement.model_copy(update={"response_status_code": 503}))


def test_attempt_reservation_rolls_back_with_caller_transaction(session: Session) -> None:
    reservation_type = sync_contracts.ProviderRequestAttemptReservation
    repository, run = _attempt_lineage(session)
    attempt_id = UUID("80000000-0000-0000-0000-000000000003")
    savepoint = session.begin_nested()

    repository.reserve_attempt(reservation_type(id=attempt_id, value=_attempt_write(run.id)))
    savepoint.rollback()
    session.expire_all()

    assert session.get(ProviderRequestAttempt, attempt_id) is None
