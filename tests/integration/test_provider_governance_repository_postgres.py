from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from stock_research_agent.db.repositories.providers import (
    ProviderRepositoryConflict,
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
)
from stock_research_agent.domain.providers.capabilities import ProviderCapabilityWrite
from stock_research_agent.domain.providers.credentials import (
    CredentialReferenceWrite,
    CredentialResolverKind,
)
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderCredentialStatus,
    ProviderDefinitionStatus,
    ProviderLicenseStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.licenses import (
    LicensePermission,
    SourceLicensePolicyWrite,
)
from stock_research_agent.domain.providers.policies import ProviderPolicyWrite
from stock_research_agent.domain.providers.schemas import ProviderDefinitionWrite

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Provider repository tests")

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


def _definition() -> ProviderDefinitionWrite:
    return ProviderDefinitionWrite(
        code="TEST_PROVIDER",
        definition_version="1.0.0",
        adapter_version="1.0.0",
        display_name="Test Provider",
        data_domain="MARKET_DATA",
        definition_status=ProviderDefinitionStatus.ACTIVE,
        production_status=ProviderProductionStatus.TEST_ONLY,
        official_domains=("example.com",),
        policy_version="1.0.0",
        license_policy_version="1.0.0",
        credential_reference_id=None,
        source_register_version="1.0.0",
    )


def test_definition_repository_is_idempotent_bounded_and_transaction_neutral(
    session: Session,
) -> None:
    repository = SqlAlchemyProviderDefinitionRepository(session)
    first = repository.add_definition(_definition())
    second = repository.add_definition(_definition())

    assert first.id == second.id
    assert repository.get_definition("TEST_PROVIDER", "1.0.0") == first
    listed = repository.list_definitions(limit=100, offset=0)
    assert tuple(item for item in listed if item.code == "TEST_PROVIDER") == (first,)
    assert session.in_transaction()


def test_definition_repository_maps_same_identity_different_payload_to_conflict(
    session: Session,
) -> None:
    repository = SqlAlchemyProviderDefinitionRepository(session)
    repository.add_definition(_definition())
    changed = _definition().model_copy(update={"display_name": "Changed Provider"})

    with pytest.raises(ProviderRepositoryConflict, match="PROVIDER_DEFINITION_CONFLICT"):
        repository.add_definition(changed)


def test_governance_repository_round_trips_exact_versioned_records(
    session: Session,
) -> None:
    definition = SqlAlchemyProviderDefinitionRepository(session).add_definition(_definition())
    repository = SqlAlchemyProviderGovernanceRepository(session)
    capability = repository.add_capability(
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
    policy = repository.add_policy(
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
    license_policy = repository.add_license_policy(
        SourceLicensePolicyWrite(
            provider_definition_id=definition.id,
            policy_version="1.0.0",
            status=ProviderLicenseStatus.RESTRICTED_REVIEW_REQUIRED,
            acquisition=LicensePermission.UNKNOWN_REQUIRES_REVIEW,
            raw_storage=LicensePermission.UNKNOWN_REQUIRES_REVIEW,
            cache=LicensePermission.PROHIBITED,
            derived_use=LicensePermission.UNKNOWN_REQUIRES_REVIEW,
            redistribution=LicensePermission.PROHIBITED,
            retention_days=30,
            deletion_required=False,
            attribution_required=True,
            terms_source_ids=("TEST_TERMS",),
            reviewed_at=datetime(2026, 7, 29, tzinfo=UTC),
            expires_at=None,
        )
    )
    credential = repository.add_credential_reference(
        CredentialReferenceWrite(
            provider_definition_id=definition.id,
            reference_version="1.0.0",
            resolver_kind=CredentialResolverKind.ENVIRONMENT,
            declared_name="TEST_PROVIDER_TOKEN",
            status=ProviderCredentialStatus.NOT_READ,
            safe_label="Test token reference",
        )
    )

    assert repository.get_capability(definition.id, "DAILY_PRICE", "1.0.0") == capability
    assert repository.get_policy(definition.id, "1.0.0") == policy
    assert repository.get_license_policy(definition.id, "1.0.0") == license_policy
    assert repository.get_credential_reference(credential.id) == credential
    assert repository.add_capability(capability) == capability
