from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderDefinitionStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.schemas import ProviderDefinitionRecord

PROVIDER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_PROVIDER_ID = UUID("22222222-2222-4222-8222-222222222222")


def _definition(provider_id: UUID = PROVIDER_ID) -> ProviderDefinitionRecord:
    return ProviderDefinitionRecord(
        id=provider_id,
        code="SEC_EDGAR_PUBLIC_V1",
        definition_version="1.0.0",
        adapter_version="1.0.0",
        display_name="SEC EDGAR public data",
        data_domain="US_SEC_FILINGS",
        definition_status=ProviderDefinitionStatus.ACTIVE,
        production_status=ProviderProductionStatus.CONDITIONAL,
        official_domains=("data.sec.gov", "www.sec.gov"),
        policy_version="1.0.0",
        license_policy_version="1.0.0",
        credential_reference_id=None,
        source_register_version="1.0.0",
        checksum="a" * 64,
        created_at=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
    )


def _capability(
    *,
    provider_id: UUID = PROVIDER_ID,
    code: str = "FETCH_FILING_METADATA",
    version: str = "1.0.0",
    status: ProviderCapabilityStatus = ProviderCapabilityStatus.IMPLEMENTED_OFFLINE,
) -> object:
    from stock_research_agent.domain.providers.capabilities import (
        ProviderCapabilityRecord,
    )

    return ProviderCapabilityRecord(
        id=UUID("33333333-3333-4333-8333-333333333333"),
        provider_definition_id=provider_id,
        code=code,
        capability_version=version,
        status=status,
        data_domain="US_SEC_FILINGS",
        market_codes=("US_EQUITY",),
        security_types=("COMMON_STOCK",),
        operations=("READ_SOURCE",),
        checksum="b" * 64,
        created_at=datetime(2026, 7, 29, 12, 1, tzinfo=UTC),
    )


def test_capability_gate_requires_exact_provider_code_and_version() -> None:
    from stock_research_agent.domain.providers.capabilities import (
        ProviderCapabilityGate,
    )

    gate = ProviderCapabilityGate((_capability(),))

    allowed = gate.evaluate(
        _definition(),
        "FETCH_FILING_METADATA",
        "1.0.0",
    )
    assert allowed.allowed is True
    assert allowed.reason_code == "CAPABILITY_EXACT_MATCH"
    assert allowed.status is ProviderCapabilityStatus.IMPLEMENTED_OFFLINE

    for code, version in (
        ("FETCH_FILING", "1.0.0"),
        ("FETCH_FILING_*", "1.0.0"),
        ("FETCH_FILING_METADATA", "1.0.1"),
    ):
        denied = gate.evaluate(_definition(), code, version)
        assert denied.allowed is False
        assert denied.reason_code == "CAPABILITY_NOT_ALLOWLISTED"

    cross_provider = gate.evaluate(
        _definition(OTHER_PROVIDER_ID),
        "FETCH_FILING_METADATA",
        "1.0.0",
    )
    assert cross_provider.allowed is False


def test_blocked_or_retired_capability_is_not_allowed() -> None:
    from stock_research_agent.domain.providers.capabilities import (
        ProviderCapabilityGate,
    )

    for status in (
        ProviderCapabilityStatus.BLOCKED,
        ProviderCapabilityStatus.RETIRED,
    ):
        decision = ProviderCapabilityGate((_capability(status=status),)).evaluate(
            _definition(),
            "FETCH_FILING_METADATA",
            "1.0.0",
        )
        assert decision.allowed is False
        assert decision.reason_code == f"CAPABILITY_{status.value}"


def test_capability_contract_rejects_unstable_allowlist_values() -> None:
    from stock_research_agent.domain.providers.capabilities import (
        ProviderCapabilityWrite,
    )

    base = {
        "provider_definition_id": PROVIDER_ID,
        "code": "FETCH_FILING_METADATA",
        "capability_version": "1.0.0",
        "status": ProviderCapabilityStatus.IMPLEMENTED_OFFLINE,
        "data_domain": "US_SEC_FILINGS",
        "market_codes": ("US_EQUITY",),
        "security_types": ("COMMON_STOCK",),
        "operations": ("READ_SOURCE",),
    }

    for field, value in (
        ("code", "FETCH_*"),
        ("capability_version", "latest"),
        ("market_codes", ("US_EQUITY", "US_EQUITY")),
        ("operations", ("read_source",)),
    ):
        invalid = {**base, field: value}
        with pytest.raises(ValidationError):
            ProviderCapabilityWrite(**invalid)
