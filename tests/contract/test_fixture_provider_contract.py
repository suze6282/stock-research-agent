from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from stock_research_agent.domain.data_access.enums import (
    AccessMode,
    DataCategory,
    DataOrigin,
    LiveStatus,
    ProviderCapability,
    ProviderStatus,
    QualityStatus,
)
from stock_research_agent.domain.data_access.schemas import ProviderInstrument, ProviderRequest
from stock_research_agent.providers.errors import ProviderContractError
from stock_research_agent.providers.fixtures.provider import (
    Stage1NasdaqFixtureProvider,
    Stage1SecFixtureProvider,
    Stage1SseFixtureProvider,
    create_stage1_fixture_registry,
)

SECURITY_ID = UUID("00000000-0000-0000-0000-000000000001")
REQUEST_ID = UUID("00000000-0000-0000-0000-000000000002")
RETRIEVED_AT = datetime(2026, 7, 15, 1, 2, 3, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return RETRIEVED_AT


def request(symbol: str, category: DataCategory, as_of: datetime) -> ProviderRequest:
    return ProviderRequest(
        request_id=REQUEST_ID,
        instrument=ProviderInstrument(
            security_id=SECURITY_ID,
            provider_symbol=symbol,
            provider_exchange_code=None,
            provider_instrument_id=None,
        ),
        category=category,
        research_as_of_time=as_of,
    )


def assert_offline_partial(envelope: object) -> None:
    assert envelope.data_origin is DataOrigin.FIXTURE  # type: ignore[attr-defined]
    assert envelope.access_mode is AccessMode.OFFLINE  # type: ignore[attr-defined]
    assert envelope.live_status is LiveStatus.NOT_LIVE  # type: ignore[attr-defined]
    assert envelope.quality.status is QualityStatus.PARTIAL  # type: ignore[attr-defined]
    assert envelope.retrieved_at == RETRIEVED_AT  # type: ignore[attr-defined]
    assert envelope.source_published_at is None  # type: ignore[attr-defined]
    assert "SOURCE_PUBLISHED_AT_UNKNOWN" in envelope.warnings  # type: ignore[attr-defined]
    assert isinstance(envelope.raw_payload, bytes)  # type: ignore[attr-defined]


def test_registry_exposes_three_exact_enabled_offline_descriptors() -> None:
    registry = create_stage1_fixture_registry(clock=FixedClock())

    descriptors = registry.list()
    assert [item.code for item in descriptors] == [
        "STAGE1_NASDAQ_FIXTURE",
        "STAGE1_SEC_FIXTURE",
        "STAGE1_SSE_FIXTURE",
    ]
    assert all(item.is_enabled for item in descriptors)
    assert all(not item.requires_credentials for item in descriptors)
    assert all(not item.credentials_configured for item in descriptors)
    assert descriptors[0].status is ProviderStatus.EXPERIMENTAL
    assert descriptors[0].capabilities == frozenset({ProviderCapability.DAILY_PRICES})
    assert descriptors[1].status is ProviderStatus.EXPERIMENTAL
    assert descriptors[1].capabilities == frozenset(
        {ProviderCapability.FILING_METADATA, ProviderCapability.FINANCIAL_FACTS}
    )
    assert descriptors[2].status is ProviderStatus.EXPERIMENTAL


@pytest.mark.parametrize(
    ("provider", "symbol", "expected"),
    [
        (
            Stage1SseFixtureProvider,
            "TEST001",
            {
                "trading_date": "2026-01-15",
                "open": Decimal("10.00"),
                "high": Decimal("10.50"),
                "low": Decimal("9.50"),
                "close": Decimal("10.25"),
                "volume": 100000,
                "currency_code": "CNY",
            },
        ),
        (
            Stage1NasdaqFixtureProvider,
            "TSTX",
            {
                "trading_date": "2026-01-15",
                "open": Decimal("20.00"),
                "high": Decimal("21.00"),
                "low": Decimal("19.50"),
                "close": Decimal("20.50"),
                "volume": 100000,
                "currency_code": "USD",
            },
        ),
    ],
)
def test_price_provider_returns_only_exact_decimal_evidence(
    provider: type[object], symbol: str, expected: dict[str, object]
) -> None:
    adapter = provider(clock=FixedClock())  # type: ignore[call-arg]
    envelope = adapter.fetch(
        request(symbol, DataCategory.DAILY_PRICES, datetime(2026, 1, 16, 12, tzinfo=UTC))
    )

    assert_offline_partial(envelope)
    assert len(envelope.records) == 1
    assert envelope.records[0].data == expected
    assert all(not isinstance(value, float) for value in envelope.records[0].data.values())
    assert envelope.records[0].source_published_at is None
    assert envelope.provider_request_id is None


@pytest.mark.parametrize(
    ("provider", "symbol", "as_of"),
    [
        (Stage1SseFixtureProvider, "TEST001", datetime(2026, 1, 14, 15, 59, tzinfo=UTC)),
        (Stage1NasdaqFixtureProvider, "TSTX", datetime(2026, 1, 15, 3, 59, tzinfo=UTC)),
    ],
)
def test_price_provider_excludes_exchange_local_future_date(
    provider: type[object], symbol: str, as_of: datetime
) -> None:
    envelope = provider(clock=FixedClock()).fetch(  # type: ignore[call-arg]
        request(symbol, DataCategory.DAILY_PRICES, as_of)
    )

    assert envelope.records == ()
    assert "NO_RECORDS_AS_OF" in envelope.warnings


def test_sec_provider_returns_exact_stable_synthetic_metadata_and_as_of_filter() -> None:
    provider = Stage1SecFixtureProvider(clock=FixedClock())
    all_records = provider.fetch(
        request("TSTX", DataCategory.FILING_METADATA, datetime(2026, 2, 1, tzinfo=UTC))
    )

    assert_offline_partial(all_records)
    raw_keys = {
        "issuer",
        "ticker",
        "cik",
        "exchange_label",
        "form",
        "filed_date",
        "report_date",
        "accession",
    }
    assert [{key: record.data[key] for key in raw_keys} for record in all_records.records] == [
        {
            "issuer": "Example Semiconductor Research Corp.",
            "ticker": "TSTX",
            "cik": "0000000000",
            "exchange_label": "Nasdaq",
            "form": "10-K",
            "filed_date": "2026-01-10",
            "report_date": "2025-12-31",
            "accession": "0000000000-26-000001",
        },
        {
            "issuer": "Example Semiconductor Research Corp.",
            "ticker": "TSTX",
            "cik": "0000000000",
            "exchange_label": "Nasdaq",
            "form": "10-Q",
            "filed_date": "2026-01-11",
            "report_date": "2025-09-30",
            "accession": "0000000000-26-000002",
        },
        {
            "issuer": "Example Semiconductor Research Corp.",
            "ticker": "TSTX",
            "cik": "0000000000",
            "exchange_label": "Nasdaq",
            "form": "8-K",
            "filed_date": "2026-01-12",
            "report_date": None,
            "accession": "0000000000-26-000003",
        },
    ]

    early = provider.fetch(
        request("TSTX", DataCategory.FILING_METADATA, datetime(2026, 1, 11, 3, 59, tzinfo=UTC))
    )
    assert [record.data["form"] for record in early.records] == ["10-K"]


def test_sec_filing_records_satisfy_ingestion_metadata_contract() -> None:
    provider = Stage1SecFixtureProvider(clock=FixedClock())
    envelope = provider.fetch(
        request("TSTX", DataCategory.FILING_METADATA, datetime(2026, 2, 1, tzinfo=UTC))
    )

    assert all(record.source_published_at is None for record in envelope.records)
    assert [record.data["document_type"] for record in envelope.records] == [
        "SEC_10_K",
        "SEC_10_Q",
        "SEC_8_K",
    ]
    assert all(record.data["title"].endswith("filing metadata") for record in envelope.records)
    assert all(
        record.data["source_url"] == "https://example.invalid/synthetic/sec-submissions"
        for record in envelope.records
    )
    assert all(record.data["document_status"] == "METADATA_ONLY" for record in envelope.records)
    assert all("storage_uri" not in record.data for record in envelope.records)
    assert all("body" not in record.data for record in envelope.records)
    assert ProviderCapability.DOCUMENT_DOWNLOAD not in provider.capabilities
    assert envelope.records[2].data["period_end"] is None


def test_sec_financial_facts_are_honestly_empty_partial() -> None:
    envelope = Stage1SecFixtureProvider(clock=FixedClock()).fetch(
        request("TSTX", DataCategory.FINANCIAL_FACTS, datetime(2026, 2, 1, tzinfo=UTC))
    )

    assert_offline_partial(envelope)
    assert envelope.records == ()
    assert envelope.quality.missing_fields == ("financial_facts", "source_published_at")
    assert "FINANCIAL_FACTS_NOT_PRESERVED" in envelope.warnings


@pytest.mark.parametrize(
    ("adapter", "symbol", "category"),
    [
        (Stage1SseFixtureProvider(clock=FixedClock()), "TEST001.SH", DataCategory.DAILY_PRICES),
        (Stage1NasdaqFixtureProvider(clock=FixedClock()), "TSTX.US", DataCategory.DAILY_PRICES),
        (Stage1SecFixtureProvider(clock=FixedClock()), "EXAMPLE", DataCategory.FILING_METADATA),
        (Stage1SseFixtureProvider(clock=FixedClock()), "TEST001", DataCategory.FILING_METADATA),
    ],
)
def test_wrong_symbol_or_category_fails_without_guessing(
    adapter: object, symbol: str, category: DataCategory
) -> None:
    with pytest.raises(ProviderContractError):
        adapter.fetch(request(symbol, category, datetime(2026, 7, 11, tzinfo=UTC)))  # type: ignore[attr-defined]
