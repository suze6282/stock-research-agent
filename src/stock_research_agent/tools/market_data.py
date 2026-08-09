"""Read-only persisted market-data tools."""

from __future__ import annotations

from datetime import date, datetime
from typing import cast
from uuid import UUID

from stock_research_agent.domain.data_access.enums import DataCategory, QualityStatus
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.domain.data_access.schemas import (
    CorporateActionRecord,
    DailyPriceBarRecord,
)
from stock_research_agent.tools.registry import ReadOnlyToolSupport
from stock_research_agent.tools.schemas import (
    CorporateActionData,
    CorporateActionsEnvelope,
    DailyPriceData,
    DailyPriceHistoryEnvelope,
    GetCorporateActionsInput,
    GetDailyPriceHistoryInput,
    GetLatestCloseInput,
    LatestCloseEnvelope,
)


def _providers(
    records: tuple[DailyPriceBarRecord | CorporateActionRecord, ...],
) -> tuple[UUID, ...]:
    return tuple(dict.fromkeys(record.provider_id for record in records))


def _latest_retrieved(
    records: tuple[DailyPriceBarRecord | CorporateActionRecord, ...],
) -> datetime | None:
    return max((record.retrieved_at for record in records), default=None)


def _sorted_bars(records: tuple[DailyPriceBarRecord, ...]) -> tuple[DailyPriceBarRecord, ...]:
    ordered = sorted(records, key=lambda record: str(record.id))
    ordered.sort(key=lambda record: record.retrieved_at, reverse=True)
    ordered.sort(key=lambda record: record.trading_date, reverse=True)
    return tuple(ordered)


def _sorted_actions(
    records: tuple[CorporateActionRecord, ...],
) -> tuple[CorporateActionRecord, ...]:
    ordered = sorted(records, key=lambda record: str(record.id))
    ordered.sort(key=lambda record: record.retrieved_at, reverse=True)
    ordered.sort(key=lambda record: record.ex_date or date.min, reverse=True)
    return tuple(ordered)


def _bar_data(record: DailyPriceBarRecord) -> DailyPriceData:
    return DailyPriceData(
        id=record.id,
        security_id=record.security_id,
        provider_id=record.provider_id,
        provider_symbol=record.provider_symbol,
        trading_date=record.trading_date,
        market_timestamp=record.market_timestamp,
        open=record.open,
        high=record.high,
        low=record.low,
        close=record.close,
        volume=record.volume,
        currency_code=record.currency_code,
        adjustment_type=record.adjustment_type,
        provider_adjusted_close=record.provider_adjusted_close,
        source_published_at=record.source_published_at,
        retrieved_at=record.retrieved_at,
    )


def _action_data(record: CorporateActionRecord) -> CorporateActionData:
    return CorporateActionData(
        id=record.id,
        security_id=record.security_id,
        provider_id=record.provider_id,
        provider_action_id=record.provider_action_id,
        action_type=record.action_type,
        announcement_date=record.announcement_date,
        ex_date=record.ex_date,
        record_date=record.record_date,
        payment_date=record.payment_date,
        cash_amount=record.cash_amount,
        currency_code=record.currency_code,
        ratio_numerator=record.ratio_numerator,
        ratio_denominator=record.ratio_denominator,
        status=record.status,
        source_published_at=record.source_published_at,
        retrieved_at=record.retrieved_at,
    )


class GetLatestCloseTool(ReadOnlyToolSupport):
    def __init__(self, query_service: DataAccessQueryService) -> None:
        super().__init__(query_service)

    def __call__(self, request: GetLatestCloseInput) -> LatestCloseEnvelope:
        selection = self.select_evidence(
            request,
            category=DataCategory.DAILY_PRICES,
            source_record_type="daily_price_bars",
            as_of_reader=lambda: self._query_service.latest_close(
                request.security_id,
                cast(datetime, request.research_as_of_time),
                request.local_trading_date,
            ),
            snapshot_reader=lambda source_ids: self._query_service.daily_prices_by_ids(
                request.security_id,
                source_ids,
            ),
        )
        records = _sorted_bars(selection.records)
        if request.local_trading_date is not None:
            records = tuple(
                record for record in records if record.trading_date <= request.local_trading_date
            )
        records = records[:1]
        warnings = selection.warnings
        status = selection.status
        if not records and status is QualityStatus.PASS:
            status = QualityStatus.PARTIAL
            warnings = (*warnings, "NO_DAILY_PRICE_DATA")
        return self.envelope(
            LatestCloseEnvelope,
            tool_name="get_latest_close",
            status=status,
            data=tuple(_bar_data(record) for record in records),
            source_record_ids=tuple(record.id for record in records),
            provider_ids=self.selection_provider_ids(selection, _providers(records)),
            snapshot_id=selection.snapshot_id,
            research_as_of_time=selection.research_as_of_time,
            retrieved_at=_latest_retrieved(records),
            warnings=warnings,
        )


class GetDailyPriceHistoryTool(ReadOnlyToolSupport):
    def __init__(self, query_service: DataAccessQueryService) -> None:
        super().__init__(query_service)

    def __call__(self, request: GetDailyPriceHistoryInput) -> DailyPriceHistoryEnvelope:
        selection = self.select_evidence(
            request,
            category=DataCategory.DAILY_PRICES,
            source_record_type="daily_price_bars",
            as_of_reader=lambda: self._query_service.daily_history(
                request.security_id,
                cast(datetime, request.research_as_of_time),
                request.local_trading_date,
                request.limit,
            ),
            snapshot_reader=lambda source_ids: self._query_service.daily_prices_by_ids(
                request.security_id,
                source_ids,
            ),
        )
        records = _sorted_bars(selection.records)
        if request.local_trading_date is not None:
            records = tuple(
                record for record in records if record.trading_date <= request.local_trading_date
            )
        if request.date_from is not None:
            records = tuple(
                record for record in records if record.trading_date >= request.date_from
            )
        records = records[: request.limit]
        warnings = tuple(
            warning for warning in selection.warnings if warning != "SOURCE_PUBLISHED_AT_UNKNOWN"
        )
        status = selection.status
        if status not in {QualityStatus.BLOCKED, QualityStatus.FAIL}:
            if any(record.source_published_at is None for record in records):
                warnings = (*warnings, "SOURCE_PUBLISHED_AT_UNKNOWN")
            if not records and selection.records:
                warnings = (*warnings, "NO_DAILY_PRICE_DATA_IN_RANGE")
            if not records or warnings:
                status = QualityStatus.PARTIAL
            else:
                status = QualityStatus.PASS
        return self.envelope(
            DailyPriceHistoryEnvelope,
            tool_name="get_daily_price_history",
            status=status,
            data=tuple(_bar_data(record) for record in records),
            source_record_ids=tuple(record.id for record in records),
            provider_ids=self.selection_provider_ids(selection, _providers(records)),
            snapshot_id=selection.snapshot_id,
            research_as_of_time=selection.research_as_of_time,
            retrieved_at=_latest_retrieved(records),
            warnings=warnings,
        )


class GetCorporateActionsTool(ReadOnlyToolSupport):
    def __init__(self, query_service: DataAccessQueryService) -> None:
        super().__init__(query_service)

    def __call__(self, request: GetCorporateActionsInput) -> CorporateActionsEnvelope:
        selection = self.select_evidence(
            request,
            category=DataCategory.CORPORATE_ACTIONS,
            source_record_type="corporate_actions",
            as_of_reader=lambda: self._query_service.corporate_actions(
                request.security_id,
                cast(datetime, request.research_as_of_time),
                request.limit,
            ),
            snapshot_reader=lambda source_ids: self._query_service.corporate_actions_by_ids(
                request.security_id,
                source_ids,
            ),
        )
        records = _sorted_actions(selection.records)[: request.limit]
        return self.envelope(
            CorporateActionsEnvelope,
            tool_name="get_corporate_actions",
            status=selection.status,
            data=tuple(_action_data(record) for record in records),
            source_record_ids=tuple(record.id for record in records),
            provider_ids=self.selection_provider_ids(selection, _providers(records)),
            snapshot_id=selection.snapshot_id,
            research_as_of_time=selection.research_as_of_time,
            retrieved_at=_latest_retrieved(records),
            warnings=selection.warnings,
        )


__all__ = ["GetCorporateActionsTool", "GetDailyPriceHistoryTool", "GetLatestCloseTool"]
