from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.data_access.enums import (
    DataCategory,
    ProviderCapability,
    QualityStatus,
)
from stock_research_agent.domain.data_access.schemas import ProviderInstrument, ProviderRequest
from stock_research_agent.providers.errors import MissingProviderCapabilityError
from stock_research_agent.providers.fixtures.provider import create_stage1_fixture_registry


def _request(provider_symbol: str, category: DataCategory, as_of: datetime) -> ProviderRequest:
    return ProviderRequest(
        request_id=UUID("90000000-0000-0000-0000-000000000001"),
        instrument=ProviderInstrument(
            security_id=UUID("90000000-0000-0000-0000-000000000002"),
            provider_symbol=provider_symbol,
            provider_exchange_code=None,
            provider_instrument_id=None,
        ),
        category=category,
        research_as_of_time=as_of,
    )


def test_fixture_registry_declares_only_capabilities_backed_by_preserved_evidence() -> None:
    registry = create_stage1_fixture_registry()
    descriptors = {descriptor.code: descriptor for descriptor in registry.list()}

    assert descriptors["STAGE1_SSE_FIXTURE"].capabilities == frozenset(
        {ProviderCapability.DAILY_PRICES}
    )
    assert descriptors["STAGE1_NASDAQ_FIXTURE"].capabilities == frozenset(
        {ProviderCapability.DAILY_PRICES}
    )
    assert descriptors["STAGE1_SEC_FIXTURE"].capabilities == frozenset(
        {ProviderCapability.FILING_METADATA, ProviderCapability.FINANCIAL_FACTS}
    )
    assert all(
        ProviderCapability.CORPORATE_ACTIONS not in descriptor.capabilities
        and ProviderCapability.DOCUMENT_DOWNLOAD not in descriptor.capabilities
        for descriptor in descriptors.values()
    )


def test_capability_gate_rejects_unpreserved_actions_without_provider_fetch() -> None:
    registry = create_stage1_fixture_registry()

    with pytest.raises(MissingProviderCapabilityError, match="does not support"):
        registry.get("STAGE1_NASDAQ_FIXTURE", ProviderCapability.CORPORATE_ACTIONS)


def test_empty_financial_facts_are_partial_and_never_filled() -> None:
    registry = create_stage1_fixture_registry()
    provider = registry.get("STAGE1_SEC_FIXTURE", ProviderCapability.FINANCIAL_FACTS)
    envelope = provider.fetch(
        _request("TSTX", DataCategory.FINANCIAL_FACTS, datetime(2026, 12, 31, tzinfo=UTC))
    )

    assert envelope.quality.status is QualityStatus.PARTIAL
    assert envelope.records == ()
    assert "FINANCIAL_FACTS_NOT_PRESERVED" in envelope.warnings
    assert "SOURCE_PUBLISHED_AT_UNKNOWN" in envelope.warnings


def test_price_capability_applies_exchange_local_as_of_cutoff() -> None:
    registry = create_stage1_fixture_registry()
    provider = registry.get("STAGE1_NASDAQ_FIXTURE", ProviderCapability.DAILY_PRICES)
    before_trading_date = provider.fetch(
        _request("TSTX", DataCategory.DAILY_PRICES, datetime(2026, 1, 15, 3, 59, tzinfo=UTC))
    )
    after_trading_date = provider.fetch(
        _request("TSTX", DataCategory.DAILY_PRICES, datetime(2026, 1, 16, tzinfo=UTC))
    )

    assert before_trading_date.records == ()
    assert "NO_RECORDS_AS_OF" in before_trading_date.warnings
    assert len(after_trading_date.records) == 1
    assert after_trading_date.records[0].source_published_at is None
