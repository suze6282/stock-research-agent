from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderCredentialStatus,
    ProviderDefinitionStatus,
    ProviderLicenseStatus,
    ProviderLiveValidationStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.schemas import ProviderDefinitionRecord
from stock_research_agent.providers.production_registry import (
    ProductionProviderRegistry,
    ProviderAdapterDescriptor,
)


def _descriptor(
    provider_code: str,
    *,
    provider_version: str = "1.0.0",
    production_status: ProviderProductionStatus = ProviderProductionStatus.BLOCKED,
) -> ProviderAdapterDescriptor:
    return ProviderAdapterDescriptor(
        provider_code=provider_code,
        provider_version=provider_version,
        adapter_version="1.0.0",
        display_name=f"{provider_code} descriptor",
        data_domain="MARKET_DATA",
        capability_codes=("FETCH_EOD_PRICES",),
        capability_status=ProviderCapabilityStatus.BLOCKED,
        definition_status=ProviderDefinitionStatus.BLOCKED,
        production_status=production_status,
        license_status=ProviderLicenseStatus.BLOCKED,
        credential_status=ProviderCredentialStatus.NOT_READ,
        live_status=ProviderLiveValidationStatus.NOT_ATTEMPTED,
        network_status="HARD_BLOCKED",
        policy_version="1.0.0",
        license_policy_version="1.0.0",
        source_register_version="1.0.0",
    )


def _persisted(descriptor: ProviderAdapterDescriptor) -> ProviderDefinitionRecord:
    return ProviderDefinitionRecord(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        code=descriptor.provider_code,
        definition_version=descriptor.provider_version,
        adapter_version=descriptor.adapter_version,
        display_name=descriptor.display_name,
        data_domain=descriptor.data_domain,
        definition_status=descriptor.definition_status,
        production_status=descriptor.production_status,
        official_domains=("example.invalid",),
        policy_version=descriptor.policy_version,
        license_policy_version=descriptor.license_policy_version,
        credential_reference_id=None,
        source_register_version=descriptor.source_register_version,
        checksum="a" * 64,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


def test_registry_registers_gets_and_lists_exact_versioned_descriptors() -> None:
    registry = ProductionProviderRegistry()
    second = _descriptor("Z_PROVIDER")
    first_v2 = _descriptor("A_PROVIDER", provider_version="2.0.0")
    first_v1 = _descriptor("A_PROVIDER")

    registry.register(second)
    registry.register(first_v2)
    registry.register(first_v1)

    assert registry.get("A_PROVIDER", "1.0.0") is first_v1
    assert registry.get("A_PROVIDER", "2.0.0") is first_v2
    assert registry.get("Z_PROVIDER", "1.0.0") is second
    assert registry.list() == (first_v1, first_v2, second)


def test_registry_never_uses_prefix_wildcard_display_name_or_casefold_selection() -> None:
    registry = ProductionProviderRegistry((_descriptor("SEC_EDGAR_PUBLIC_V1"),))

    assert registry.get("SEC_EDGAR_PUBLIC_V1", "1.0.0") is not None
    assert registry.get("SEC", "1.0.0") is None
    assert registry.get("SEC_*", "1.0.0") is None
    assert registry.get("sec_edgar_public_v1", "1.0.0") is None
    assert registry.get("SEC_EDGAR_PUBLIC_V1 descriptor", "1.0.0") is None
    assert registry.get("SEC_EDGAR_PUBLIC_V1", "latest") is None


def test_registry_rejects_duplicate_identity_and_cannot_mutate_blocked_to_enabled() -> None:
    blocked = _descriptor("LOCKED_PROVIDER")
    registry = ProductionProviderRegistry((blocked,))

    with pytest.raises(ValueError, match="PROVIDER_DESCRIPTOR_DUPLICATE"):
        registry.register(blocked)
    with pytest.raises(ValueError, match="PROVIDER_DESCRIPTOR_DUPLICATE"):
        registry.register(
            _descriptor(
                "LOCKED_PROVIDER",
                production_status=ProviderProductionStatus.ENABLED,
            )
        )
    with pytest.raises(ValidationError):
        blocked.production_status = ProviderProductionStatus.ENABLED

    assert registry.get("LOCKED_PROVIDER", "1.0.0") is blocked
    assert registry.get("LOCKED_PROVIDER", "1.0.0").production_status is (
        ProviderProductionStatus.BLOCKED
    )


def test_catalog_checksum_is_stable_independent_of_registration_order() -> None:
    first = _descriptor("A_PROVIDER")
    second = _descriptor("Z_PROVIDER", provider_version="2.0.0")
    left = ProductionProviderRegistry((second, first))
    right = ProductionProviderRegistry((first, second))
    canonical = json.dumps(
        [descriptor.model_dump(mode="json") for descriptor in (first, second)],
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    assert left.catalog_checksum == expected
    assert right.catalog_checksum == expected
    assert left.catalog_version == f"provider-catalog-v1:{expected}"
    assert len(left.catalog_version) == 84


def test_catalog_checksum_changes_for_version_or_governance_change() -> None:
    baseline = ProductionProviderRegistry((_descriptor("A_PROVIDER"),))
    version_changed = ProductionProviderRegistry(
        (_descriptor("A_PROVIDER", provider_version="2.0.0"),)
    )
    status_changed = ProductionProviderRegistry(
        (
            _descriptor(
                "A_PROVIDER",
                production_status=ProviderProductionStatus.ENABLED,
            ),
        )
    )

    assert version_changed.catalog_checksum != baseline.catalog_checksum
    assert status_changed.catalog_checksum != baseline.catalog_checksum


def test_registry_reconciles_exact_persisted_definition_identity_and_governance() -> None:
    descriptor = _descriptor("PERSISTED_PROVIDER")
    registry = ProductionProviderRegistry((descriptor,))

    result = registry.reconcile((_persisted(descriptor),))

    assert result.matched_identities == (("PERSISTED_PROVIDER", "1.0.0"),)
    assert result.missing_persisted_identities == ()
    assert result.unregistered_persisted_identities == ()
    assert result.mismatched_identities == ()
    assert result.is_consistent is True


def test_registry_reconciliation_reports_missing_extra_and_mismatched_definitions() -> None:
    expected = _descriptor("EXPECTED_PROVIDER")
    mismatch = _descriptor("MISMATCH_PROVIDER")
    extra = _descriptor("EXTRA_PROVIDER")
    registry = ProductionProviderRegistry((expected, mismatch))
    persisted_mismatch = _persisted(mismatch).model_copy(
        update={"production_status": ProviderProductionStatus.ENABLED}
    )

    result = registry.reconcile((persisted_mismatch, _persisted(extra)))

    assert result.matched_identities == ()
    assert result.missing_persisted_identities == (("EXPECTED_PROVIDER", "1.0.0"),)
    assert result.unregistered_persisted_identities == (("EXTRA_PROVIDER", "1.0.0"),)
    assert result.mismatched_identities == (("MISMATCH_PROVIDER", "1.0.0"),)
    assert result.is_consistent is False
