from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from stock_research_agent.domain.providers.capabilities import ProviderCapabilityRecord
from stock_research_agent.domain.providers.configuration import (
    ProviderConfiguration,
    ProviderConfigurationGate,
)
from stock_research_agent.domain.providers.credentials import (
    CredentialReferenceRecord,
    CredentialResolverKind,
)
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderConfigurationStatus,
    ProviderCredentialStatus,
    ProviderDefinitionStatus,
    ProviderLicenseStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.licenses import (
    LicensePermission,
    SourceLicensePolicyRecord,
)
from stock_research_agent.domain.providers.policies import ProviderPolicyRecord
from stock_research_agent.domain.providers.schemas import ProviderDefinitionRecord

NOW = datetime(2026, 7, 29, tzinfo=UTC)


def _records() -> tuple[
    ProviderDefinitionRecord,
    ProviderCapabilityRecord,
    ProviderPolicyRecord,
    SourceLicensePolicyRecord,
    CredentialReferenceRecord,
]:
    provider_id = uuid4()
    definition = ProviderDefinitionRecord(
        id=provider_id,
        code="CONFIG_TEST",
        definition_version="1.0.0",
        adapter_version="1.0.0",
        display_name="Configuration Test",
        data_domain="MARKET_DATA",
        definition_status=ProviderDefinitionStatus.ACTIVE,
        production_status=ProviderProductionStatus.CONDITIONAL,
        official_domains=("example.com",),
        policy_version="1.0.0",
        license_policy_version="1.0.0",
        credential_reference_id=None,
        source_register_version="1.0.0",
        checksum="1" * 64,
        created_at=NOW,
    )
    capability = ProviderCapabilityRecord(
        id=uuid4(),
        provider_definition_id=provider_id,
        code="DAILY_PRICE",
        capability_version="1.0.0",
        status=ProviderCapabilityStatus.IMPLEMENTED_OFFLINE,
        data_domain="MARKET_DATA",
        market_codes=("US_EQUITY",),
        security_types=("COMMON_STOCK",),
        operations=("READ_OFFLINE_FIXTURE",),
        checksum="2" * 64,
        created_at=NOW,
    )
    policy = ProviderPolicyRecord(
        id=uuid4(),
        provider_definition_id=provider_id,
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
        checksum="3" * 64,
        created_at=NOW,
    )
    license_policy = SourceLicensePolicyRecord(
        id=uuid4(),
        provider_definition_id=provider_id,
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
        reviewed_at=NOW,
        expires_at=None,
        checksum="4" * 64,
        created_at=NOW,
    )
    credential = CredentialReferenceRecord(
        id=uuid4(),
        provider_definition_id=provider_id,
        reference_version="1.0.0",
        resolver_kind=CredentialResolverKind.NONE,
        declared_name=None,
        status=ProviderCredentialStatus.NOT_REQUIRED,
        safe_label="No credential required",
        checksum="5" * 64,
        created_at=NOW,
    )
    return definition, capability, policy, license_policy, credential


def test_configuration_gate_accepts_exact_offline_configuration() -> None:
    records = _records()
    decision = ProviderConfigurationGate.validate(
        ProviderConfiguration(
            capability_version="1.0.0",
            endpoint_policy_version="1.0.0",
            requested_retention_days=30,
            network_requested=False,
        ),
        *records,
    )

    assert decision.status is ProviderConfigurationStatus.VALID
    assert decision.allowed is True
    assert decision.reason_codes == ("PROVIDER_CONFIGURATION_VALID",)


@pytest.mark.parametrize(
    ("index", "updates", "reason"),
    [
        (0, {"production_status": ProviderProductionStatus.BLOCKED}, "PROVIDER_BLOCKED"),
        (1, {"capability_version": "2.0.0"}, "CAPABILITY_VERSION_MISMATCH"),
        (2, {"endpoint_policy_version": "2.0.0"}, "ENDPOINT_POLICY_VERSION_MISMATCH"),
        (3, {"retention_days": 10}, "LICENSE_RETENTION_EXCEEDED"),
        (
            4,
            {
                "resolver_kind": CredentialResolverKind.ENVIRONMENT,
                "declared_name": "TOKEN",
                "status": ProviderCredentialStatus.NOT_READ,
            },
            "CREDENTIAL_RESOLVER_UNSUPPORTED",
        ),
    ],
)
def test_configuration_gate_rejects_mismatch_without_environment_access(
    monkeypatch: pytest.MonkeyPatch,
    index: int,
    updates: dict[str, object],
    reason: str,
) -> None:
    monkeypatch.setattr(
        "os.getenv",
        lambda *_args, **_kwargs: pytest.fail("configuration gate read environment"),
    )
    records = list(_records())
    records[index] = records[index].model_copy(update=updates)
    decision = ProviderConfigurationGate.validate(
        ProviderConfiguration(
            capability_version="1.0.0",
            endpoint_policy_version="1.0.0",
            requested_retention_days=30,
            network_requested=False,
        ),
        *records,
    )

    assert decision.allowed is False
    assert reason in decision.reason_codes
