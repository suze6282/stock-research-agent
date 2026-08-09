"""Provider market-data bridge into existing Stage 4 raw price structures."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol, cast
from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.data_access.schemas import DailyPriceBarWrite
from stock_research_agent.domain.providers.artifacts import (
    ProviderBatch,
    ProviderIngestionManifestRecord,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
)

AdjustmentValue = Literal["UNADJUSTED", "PROVIDER_ADJUSTED"]


class MarketDataBridgeContext(FrozenProviderContract):
    provider_id: UUID
    security_id: UUID
    source_payload_id: UUID
    source_payload_checksum: Checksum
    expected_currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    retrieved_at: AwareUtcDateTime
    research_as_of_time: AwareUtcDateTime
    derived_use_approved: bool
    cache_retention_approved: bool
    allow_snapshot_creation: Literal[False] = False


class MarketDataBridgeResult(FrozenProviderContract):
    staged_price_bar_count: int = Field(ge=0)
    manifest_id: UUID
    manifest_checksum: Checksum
    raw_artifact_id: UUID
    source_payload_id: UUID
    snapshot_created: Literal[False] = False


class MarketDataBridgeRepository(Protocol):
    def add_daily_price_bar(self, value: DailyPriceBarWrite) -> object: ...


class MarketDataProviderBridge:
    """Stage exact price bars while leaving Snapshot creation to an explicit service."""

    def __init__(self, repository: MarketDataBridgeRepository) -> None:
        self._repository = repository

    def stage(
        self,
        manifest: ProviderIngestionManifestRecord,
        batch: ProviderBatch,
        context: MarketDataBridgeContext,
    ) -> MarketDataBridgeResult:
        if not context.derived_use_approved or not context.cache_retention_approved:
            raise ValueError("MARKET_DATA_DERIVED_STORAGE_NOT_APPROVED")
        if context.retrieved_at > context.research_as_of_time:
            raise ValueError("MARKET_DATA_FUTURE_DATA")
        if manifest.manifest_checksum != batch.manifest_checksum:
            raise ValueError("MARKET_DATA_MANIFEST_MISMATCH")
        if manifest.record_count != batch.record_count:
            raise ValueError("MARKET_DATA_RECORD_COUNT_MISMATCH")
        if manifest.source_published_at is not None and (
            manifest.source_published_at > context.research_as_of_time
        ):
            raise ValueError("MARKET_DATA_FUTURE_DATA")
        if manifest.synthetic_status in {
            ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
            ProviderSyntheticStatus.UNKNOWN,
        }:
            raise ValueError("SYNTHETIC_MARKET_DATA_WRITE_FORBIDDEN")

        staged: list[DailyPriceBarWrite] = []
        for record in batch.records:
            if record.raw_artifact_id != manifest.raw_artifact_id:
                raise ValueError("MARKET_DATA_RAW_ARTIFACT_MISMATCH")
            if record.source_checksum != context.source_payload_checksum:
                raise ValueError("MARKET_DATA_RAW_CHECKSUM_MISMATCH")
            if record.synthetic_status is not manifest.synthetic_status:
                raise ValueError("MARKET_DATA_SYNTHETIC_STATUS_MISMATCH")
            if record.source_published_at is not None and (
                record.source_published_at > context.research_as_of_time
            ):
                raise ValueError("MARKET_DATA_FUTURE_DATA")
            values = record.text_values
            if _uuid_value(values.get("security_id")) != context.security_id:
                raise ValueError("MARKET_DATA_SECURITY_MISMATCH")
            trading_date = _date_value(values.get("trading_date"))
            if trading_date > context.research_as_of_time.date():
                raise ValueError("MARKET_DATA_FUTURE_DATA")
            currency_code = _required(values.get("currency_code"), "CURRENCY")
            if currency_code != context.expected_currency_code:
                raise ValueError("MARKET_DATA_CURRENCY_MISMATCH")
            adjustment = _adjustment_value(values.get("adjustment_type"))
            staged.append(
                DailyPriceBarWrite(
                    security_id=context.security_id,
                    provider_id=context.provider_id,
                    source_payload_id=context.source_payload_id,
                    provider_symbol=_required(values.get("provider_symbol"), "SYMBOL"),
                    trading_date=trading_date,
                    market_timestamp=_datetime_value(values.get("market_timestamp")),
                    open=_decimal_value(record.numeric_values.get("open")),
                    high=_decimal_value(record.numeric_values.get("high")),
                    low=_decimal_value(record.numeric_values.get("low")),
                    close=_decimal_value(record.numeric_values.get("close")),
                    volume=_volume_value(record.numeric_values.get("volume")),
                    currency_code=currency_code,
                    adjustment_type=adjustment,
                    provider_adjusted_close=_decimal_value(
                        record.numeric_values.get("provider_adjusted_close")
                    ),
                    source_published_at=record.source_published_at,
                    retrieved_at=context.retrieved_at,
                )
            )

        if manifest.batch_checksum != batch.batch_checksum:
            raise ValueError("MARKET_DATA_BATCH_CHECKSUM_MISMATCH")
        for value in staged:
            self._repository.add_daily_price_bar(value)
        return MarketDataBridgeResult(
            staged_price_bar_count=len(staged),
            manifest_id=manifest.id,
            manifest_checksum=manifest.manifest_checksum,
            raw_artifact_id=manifest.raw_artifact_id,
            source_payload_id=context.source_payload_id,
            snapshot_created=False,
        )


def _decimal_value(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (bool, float)):
        raise ValueError("MARKET_DATA_BINARY_FLOAT_FORBIDDEN")
    if not isinstance(value, str):
        raise ValueError("MARKET_DATA_DECIMAL_INVALID")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError("MARKET_DATA_DECIMAL_INVALID") from None
    if not result.is_finite():
        raise ValueError("MARKET_DATA_DECIMAL_INVALID")
    return result


def _volume_value(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, (bool, float)):
        raise ValueError("MARKET_DATA_BINARY_FLOAT_FORBIDDEN")
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise ValueError("MARKET_DATA_VOLUME_INVALID")
    return int(value)


def _required(value: str | None, field: str) -> str:
    if value is None or value != value.strip() or not value:
        raise ValueError(f"MARKET_DATA_{field}_MISSING")
    return value


def _uuid_value(value: str | None) -> UUID:
    try:
        return UUID(_required(value, "SECURITY"))
    except ValueError as error:
        if str(error).startswith("MARKET_DATA_"):
            raise
        raise ValueError("MARKET_DATA_SECURITY_INVALID") from None


def _date_value(value: str | None) -> date:
    try:
        return date.fromisoformat(_required(value, "TRADING_DATE"))
    except ValueError as error:
        if str(error).startswith("MARKET_DATA_"):
            raise
        raise ValueError("MARKET_DATA_TRADING_DATE_INVALID") from None


def _datetime_value(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("MARKET_DATA_TIMESTAMP_INVALID") from None


def _adjustment_value(value: str | None) -> AdjustmentValue | None:
    if value is None:
        return None
    if value not in {"UNADJUSTED", "PROVIDER_ADJUSTED"}:
        raise ValueError("MARKET_DATA_ADJUSTMENT_INVALID")
    return cast(AdjustmentValue, value)


__all__ = [
    "MarketDataBridgeContext",
    "MarketDataBridgeRepository",
    "MarketDataBridgeResult",
    "MarketDataProviderBridge",
]
