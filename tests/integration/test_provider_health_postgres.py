from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from stock_research_agent.db.repositories.providers import (
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
)
from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.enums import (
    ProviderConfigurationStatus,
    ProviderCredentialStatus,
    ProviderDefinitionStatus,
    ProviderLicenseStatus,
    ProviderLiveValidationStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.health import (
    ProviderHealthSnapshotWrite,
    ProviderReadinessStatus,
)
from stock_research_agent.domain.providers.schemas import ProviderDefinitionWrite

PROJECT_ROOT = Config("alembic.ini")
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
NOW = datetime(2026, 8, 1, tzinfo=UTC)


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Provider health tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    previous_app_env = os.environ.get("APP_ENV")
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(PROJECT_ROOT, "head")
    value = create_engine(TEST_DATABASE_URL)
    try:
        yield value
    finally:
        value.dispose()
        if previous_app_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = previous_app_env
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url


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


def _definition_id(session: Session) -> UUID:
    return (
        SqlAlchemyProviderDefinitionRepository(session)
        .add_definition(
            ProviderDefinitionWrite(
                code="HEALTH_REGRESSION_V1",
                definition_version="1.0.0",
                adapter_version="1.0.0",
                display_name="Health regression Provider",
                data_domain="MARKET_DATA",
                definition_status=ProviderDefinitionStatus.ACTIVE,
                production_status=ProviderProductionStatus.BLOCKED,
                official_domains=("example.com",),
                policy_version="1.0.0",
                license_policy_version="1.0.0",
                credential_reference_id=None,
                source_register_version="1.0.0",
            )
        )
        .id
    )


def _health(
    provider_definition_id: UUID,
    *,
    observed_at: datetime = NOW,
    configuration_status: ProviderConfigurationStatus = ProviderConfigurationStatus.BLOCKED,
    credential_status: ProviderCredentialStatus = ProviderCredentialStatus.CONFIGURED_METADATA_ONLY,
    live_status: ProviderLiveValidationStatus = ProviderLiveValidationStatus.PASSED,
) -> ProviderHealthSnapshotWrite:
    values = {
        "provider_definition_id": provider_definition_id,
        "status": ProviderReadinessStatus.BLOCKED,
        "configuration_status": configuration_status,
        "credential_status": credential_status,
        "license_status": ProviderLicenseStatus.RESTRICTED_REVIEW_REQUIRED,
        "live_validation_status": live_status,
        "limiting_reasons": ("PRODUCTION_STATUS_BLOCKED",),
        "observed_at": observed_at,
    }
    return ProviderHealthSnapshotWrite(**values, checksum=provider_checksum(values))


def test_health_repository_persists_domain_vocabulary_and_returns_latest(
    session: Session,
) -> None:
    provider_id = _definition_id(session)
    repository = SqlAlchemyProviderGovernanceRepository(session)
    first = repository.add_health_snapshot(_health(provider_id))
    second = repository.add_health_snapshot(
        _health(
            provider_id,
            observed_at=NOW + timedelta(seconds=1),
            configuration_status=ProviderConfigurationStatus.INVALID,
            credential_status=ProviderCredentialStatus.MISSING,
            live_status=ProviderLiveValidationStatus.CANCELLED,
        )
    )

    assert first.configuration_status is ProviderConfigurationStatus.BLOCKED
    assert first.credential_status is ProviderCredentialStatus.CONFIGURED_METADATA_ONLY
    assert first.live_validation_status is ProviderLiveValidationStatus.PASSED
    assert repository.get_latest_health_snapshot(provider_id) == second


def test_health_snapshot_rejects_obsolete_database_only_state_aliases(session: Session) -> None:
    provider_id = _definition_id(session)
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.execute(
                text(
                    "INSERT INTO provider_health_snapshots "
                    "(id, provider_definition_id, status, configuration_status, "
                    "credential_status, license_status, live_validation_status, "
                    "limiting_reasons, observed_at, checksum) VALUES "
                    "(:id, :provider_id, 'BLOCKED', 'NOT_CONFIGURED', 'REFERENCE_ONLY', "
                    "'BLOCKED', 'PASS', '[]'::jsonb, :observed_at, :checksum)"
                ),
                {
                    "id": uuid4(),
                    "provider_id": provider_id,
                    "observed_at": NOW,
                    "checksum": "a" * 64,
                },
            )


def test_health_snapshot_is_immutable_in_postgresql(session: Session) -> None:
    provider_id = _definition_id(session)
    record = SqlAlchemyProviderGovernanceRepository(session).add_health_snapshot(
        _health(provider_id)
    )

    for statement in (
        "UPDATE provider_health_snapshots SET status = 'READY' WHERE id = :id",
        "DELETE FROM provider_health_snapshots WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="STAGE9_IMMUTABLE_RECORD"):
            with session.begin_nested():
                session.execute(text(statement), {"id": record.id})
