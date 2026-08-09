from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.data_access.schemas import DailyPriceBarWrite
from stock_research_agent.domain.providers.artifacts import (
    ProviderBatch,
    ProviderIngestionManifestRecord,
    ProviderRecord,
    ProviderRecordIdentity,
    ProviderRecordStatus,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.providers.bridges.market_data import (
    MarketDataBridgeContext,
    MarketDataProviderBridge,
)

SECURITY_ID = UUID("11111111-1111-4111-8111-111111111111")
PROVIDER_ID = UUID("22222222-2222-4222-8222-222222222222")
SOURCE_PAYLOAD_ID = UUID("33333333-3333-4333-8333-333333333333")
RAW_ARTIFACT_ID = UUID("44444444-4444-4444-8444-444444444444")
MANIFEST_ID = UUID("55555555-5555-4555-8555-555555555555")
MANIFEST_CHECKSUM = "a" * 64
SOURCE_CHECKSUM = "b" * 64
PUBLISHED_AT = datetime(2026, 7, 29, 8, tzinfo=UTC)
RETRIEVED_AT = datetime(2026, 7, 29, 9, tzinfo=UTC)
AS_OF = datetime(2026, 7, 31, 12, tzinfo=UTC)


class _Repository:
    def __init__(self) -> None:
        self.values: list[DailyPriceBarWrite] = []
        self.snapshot_calls = 0

    def add_daily_price_bar(self, value: DailyPriceBarWrite) -> object:
        self.values.append(value)
        return object()

    def add_snapshot(self, value: object) -> object:
        self.snapshot_calls += 1
        raise AssertionError("market bridge must never create a Snapshot")


def _record(
    *,
    source_published_at: datetime | None = PUBLISHED_AT,
    source_checksum: str = SOURCE_CHECKSUM,
    numeric_values: dict[str, object] | None = None,
    currency_code: str = "USD",
    trading_date: str = "2026-07-29",
) -> ProviderRecord:
    return ProviderRecord.model_construct(
        identity=ProviderRecordIdentity(
            provider_definition_id=UUID("66666666-6666-4666-8666-666666666666"),
            provider_capability_id=UUID("77777777-7777-4777-8777-777777777777"),
            source_identity="tushare:daily:test",
            record_key=f"daily:{trading_date}",
            revision=1,
        ),
        raw_artifact_id=RAW_ARTIFACT_ID,
        source_checksum=source_checksum,
        source_published_at=source_published_at,
        status=ProviderRecordStatus.COMPLETE,
        numeric_values=(
            numeric_values
            if numeric_values is not None
            else {
                "open": "10.10",
                "high": "11.20",
                "low": "9.90",
                "close": "10.80",
                "volume": "1200",
                "provider_adjusted_close": "10.75",
            }
        ),
        text_values={
            "security_id": str(SECURITY_ID),
            "provider_symbol": "TEST.US",
            "trading_date": trading_date,
            "market_timestamp": "2026-07-29T20:00:00Z",
            "currency_code": currency_code,
            "adjustment_type": "PROVIDER_ADJUSTED",
        },
        warning_codes=(),
        synthetic_status=ProviderSyntheticStatus.REAL_VERIFIED,
    )


def _batch(record: ProviderRecord) -> ProviderBatch:
    return ProviderBatch(manifest_checksum=MANIFEST_CHECKSUM, records=(record,))


def _manifest(batch: ProviderBatch) -> ProviderIngestionManifestRecord:
    return ProviderIngestionManifestRecord(
        id=MANIFEST_ID,
        raw_artifact_id=RAW_ARTIFACT_ID,
        sync_run_id=UUID("88888888-8888-4888-8888-888888888888"),
        adapter_version="1.0.0",
        parser_version="1.0.0",
        schema_version="1.0.0",
        batch_checksum=batch.batch_checksum,
        record_count=batch.record_count,
        source_published_at=PUBLISHED_AT,
        warning_codes=(),
        synthetic_status=ProviderSyntheticStatus.REAL_VERIFIED,
        manifest_checksum=MANIFEST_CHECKSUM,
        created_at=AS_OF,
    )


def _context(**updates: object) -> MarketDataBridgeContext:
    values: dict[str, object] = {
        "provider_id": PROVIDER_ID,
        "security_id": SECURITY_ID,
        "source_payload_id": SOURCE_PAYLOAD_ID,
        "source_payload_checksum": SOURCE_CHECKSUM,
        "expected_currency_code": "USD",
        "retrieved_at": RETRIEVED_AT,
        "research_as_of_time": AS_OF,
        "derived_use_approved": True,
        "cache_retention_approved": True,
        "allow_snapshot_creation": False,
    }
    values.update(updates)
    return MarketDataBridgeContext(**values)


def test_bridge_preserves_exact_values_times_adjustment_provider_and_lineage() -> None:
    repository = _Repository()
    batch = _batch(_record())

    result = MarketDataProviderBridge(repository).stage(_manifest(batch), batch, _context())

    assert result.staged_price_bar_count == 1
    assert result.manifest_id == MANIFEST_ID
    assert result.manifest_checksum == MANIFEST_CHECKSUM
    assert result.raw_artifact_id == RAW_ARTIFACT_ID
    assert result.source_payload_id == SOURCE_PAYLOAD_ID
    assert result.snapshot_created is False
    assert repository.snapshot_calls == 0
    value = repository.values[0]
    assert value.model_dump(mode="json") == {
        "security_id": str(SECURITY_ID),
        "provider_id": str(PROVIDER_ID),
        "source_payload_id": str(SOURCE_PAYLOAD_ID),
        "provider_symbol": "TEST.US",
        "trading_date": "2026-07-29",
        "market_timestamp": "2026-07-29T20:00:00Z",
        "open": "10.10",
        "high": "11.20",
        "low": "9.90",
        "close": "10.80",
        "volume": 1200,
        "currency_code": "USD",
        "adjustment_type": "PROVIDER_ADJUSTED",
        "provider_adjusted_close": "10.75",
        "source_published_at": "2026-07-29T08:00:00Z",
        "retrieved_at": "2026-07-29T09:00:00Z",
    }


def test_bridge_rejects_binary_float_before_any_write() -> None:
    repository = _Repository()
    batch = _batch(_record(numeric_values={"close": 10.8}))
    manifest = _manifest(_batch(_record()))

    with pytest.raises(ValueError, match="MARKET_DATA_BINARY_FLOAT_FORBIDDEN"):
        MarketDataProviderBridge(repository).stage(manifest, batch, _context())

    assert repository.values == []


def test_bridge_preserves_missing_as_none_instead_of_zero() -> None:
    repository = _Repository()
    batch = _batch(
        _record(
            numeric_values={
                "open": None,
                "high": None,
                "low": None,
                "close": None,
                "volume": None,
                "provider_adjusted_close": None,
            }
        )
    )

    MarketDataProviderBridge(repository).stage(_manifest(batch), batch, _context())

    value = repository.values[0]
    assert value.open is None
    assert value.close is None
    assert value.volume is None
    assert value.provider_adjusted_close is None


@pytest.mark.parametrize(
    "context_updates",
    (
        {"derived_use_approved": False},
        {"cache_retention_approved": False},
    ),
)
def test_bridge_rejects_unlicensed_derived_cache(context_updates: dict[str, object]) -> None:
    repository = _Repository()
    batch = _batch(_record())

    with pytest.raises(ValueError, match="MARKET_DATA_DERIVED_STORAGE_NOT_APPROVED"):
        MarketDataProviderBridge(repository).stage(
            _manifest(batch),
            batch,
            _context(**context_updates),
        )


def test_bridge_rejects_currency_mixing() -> None:
    repository = _Repository()
    batch = _batch(_record(currency_code="CNY"))

    with pytest.raises(ValueError, match="MARKET_DATA_CURRENCY_MISMATCH"):
        MarketDataProviderBridge(repository).stage(_manifest(batch), batch, _context())


@pytest.mark.parametrize(
    "record",
    (
        _record(source_published_at=datetime(2026, 8, 1, tzinfo=UTC)),
        _record(trading_date="2026-08-01"),
    ),
)
def test_bridge_rejects_future_publication_or_trading_date(record: ProviderRecord) -> None:
    repository = _Repository()
    batch = _batch(record)

    with pytest.raises(ValueError, match="MARKET_DATA_FUTURE_DATA"):
        MarketDataProviderBridge(repository).stage(_manifest(batch), batch, _context())


def test_bridge_rejects_raw_checksum_or_manifest_lineage_mismatch() -> None:
    repository = _Repository()
    batch = _batch(_record(source_checksum="c" * 64))

    with pytest.raises(ValueError, match="MARKET_DATA_RAW_CHECKSUM_MISMATCH"):
        MarketDataProviderBridge(repository).stage(_manifest(batch), batch, _context())
    with pytest.raises(ValueError, match="MARKET_DATA_MANIFEST_MISMATCH"):
        valid_batch = _batch(_record())
        MarketDataProviderBridge(repository).stage(
            _manifest(valid_batch),
            valid_batch.model_copy(update={"manifest_checksum": "d" * 64}),
            _context(),
        )


def test_context_forbids_implicit_snapshot_creation() -> None:
    with pytest.raises(ValueError):
        _context(allow_snapshot_creation=True)
