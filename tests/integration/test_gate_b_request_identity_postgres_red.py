from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from types import ModuleType

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from stock_research_agent.db.repositories.providers import (
    ProviderRepositoryConflict,
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
    SqlAlchemyProviderSyncRepository,
)
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
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
from stock_research_agent.domain.providers.sync import ProviderExecutionMode
from stock_research_agent.domain.securities.seed import (
    MICRON_SECURITY_ID,
    SecurityMasterSeedService,
)

MODULE_NAME = "stock_research_agent.domain.live_evidence.gate_b_request_identity"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
NOW = datetime(2026, 8, 22, 18, 47, 59, 661193, tzinfo=UTC)
FILING_DATE = date(2026, 6, 25)


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Gate B request identity tests")

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


def _api() -> ModuleType:
    try:
        module = importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as error:
        if error.name == MODULE_NAME:
            pytest.fail("Gate B request identity API is not implemented", pytrace=False)
        raise
    required = {
        "GateBSyncRequestScope",
        "GateBSyncRequestIdentity",
        "build_gate_b_sync_request",
    }
    if any(not hasattr(module, name) for name in required):
        pytest.fail("Gate B request identity API is not implemented", pytrace=False)
    return module


def _governance(session: Session) -> tuple[object, object, object, object, object]:
    SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
    definition = SqlAlchemyProviderDefinitionRepository(session).add_definition(
        ProviderDefinitionWrite(
            code="GATE_B_REQUEST_IDENTITY_RED",
            definition_version="1.0.0",
            adapter_version="1.0.0",
            display_name="Gate B Request Identity RED",
            data_domain="REGULATORY_FILINGS",
            definition_status=ProviderDefinitionStatus.ACTIVE,
            production_status=ProviderProductionStatus.TEST_ONLY,
            official_domains=("data.sec.gov", "www.sec.gov"),
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
            code="SEC_FILING_DOCUMENT",
            capability_version="1.0.0",
            status=ProviderCapabilityStatus.IMPLEMENTED_OFFLINE,
            data_domain="REGULATORY_FILINGS",
            market_codes=("US_EQUITY",),
            security_types=("COMMON_STOCK",),
            operations=("READ_LIVE_VALIDATION",),
        )
    )
    policy = governance.add_policy(
        ProviderPolicyWrite(
            provider_definition_id=definition.id,
            policy_version="1.0.0",
            endpoint_policy_version="1.0.0",
            network_enabled=False,
            max_requests=3,
            max_response_bytes=20 * 1024 * 1024,
            max_total_bytes=26 * 1024 * 1024,
            max_duration_seconds=120,
            max_attempts=3,
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
            deletion_required=True,
            attribution_required=True,
            terms_source_ids=(
                "SEC_ACCESSING_EDGAR_DATA",
                "SEC_DEVELOPER_RESOURCES",
                "SEC_PRIVACY_SECURITY_POLICY",
            ),
            reviewed_at=NOW,
            expires_at=None,
        )
    )
    credential = governance.add_credential_reference(
        CredentialReferenceWrite(
            provider_definition_id=definition.id,
            reference_version="1.0.0",
            resolver_kind=CredentialResolverKind.ENVIRONMENT,
            declared_name="SEC_EDGAR_CONTACT_IDENTITY",
            status=ProviderCredentialStatus.CONFIGURED_METADATA_ONLY,
            safe_label="sec-edgar-contact-gate-b",
        )
    )
    return definition, capability, policy, license_policy, credential


def test_red_gateb_req_006_same_idempotency_with_different_checksum_fails_closed(
    session: Session,
) -> None:
    assert session.scalar(text("SELECT 1")) == 1
    api = _api()
    definition, capability, policy, license_policy, credential = _governance(session)
    identity = api.GateBSyncRequestIdentity.model_validate(
        {
            "contract_version": "1.0.0",
            "provider_definition_id": definition.id,
            "provider_capability_id": capability.id,
            "policy_id": policy.id,
            "license_policy_id": license_policy.id,
            "credential_reference_id": credential.id,
            "security_id": MICRON_SECURITY_ID,
            "universe_code": None,
            "research_as_of_time": NOW,
            "range_start": FILING_DATE,
            "range_end": FILING_DATE,
            "execution_mode": ProviderExecutionMode.LIVE_VALIDATION,
            "scope": {
                "provider_code": "SEC_EDGAR_PUBLIC_V1",
                "cik": "0000723125",
                "form": "10-Q",
                "accession_number": "0000723125-26-000015",
                "filed_date": FILING_DATE,
                "report_period": date(2026, 5, 28),
            },
            "budget": {
                "max_requests": 3,
                "max_bytes": 26 * 1024 * 1024,
                "max_attempts": 3,
                "max_duration_seconds": 120,
            },
        }
    )
    request = api.build_gate_b_sync_request(identity)
    repository = SqlAlchemyProviderSyncRepository(session)

    first = repository.create_request(request)
    assert repository.create_request(request).id == first.id
    conflicting_checksum = "0" * 64 if request.request_checksum != "0" * 64 else "1" * 64
    with pytest.raises(ProviderRepositoryConflict, match="PROVIDER_SYNC_REQUEST_CONFLICT"):
        repository.create_request(
            request.model_copy(update={"request_checksum": conflicting_checksum})
        )
