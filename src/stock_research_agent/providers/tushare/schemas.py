"""Strict offline Tushare schemas."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.schemas import FrozenProviderContract


class TushareEndpoint(StrEnum):
    BALANCE_SHEET = "balancesheet"
    CASH_FLOW = "cashflow"
    DAILY = "daily"
    DISCLOSURE_DATE = "disclosure_date"
    DIVIDEND = "dividend"
    FINA_INDICATOR = "fina_indicator"
    INCOME = "income"
    STOCK_BASIC = "stock_basic"
    TRADE_CAL = "trade_cal"


class TushareFieldRole(StrEnum):
    RAW_FIELD = "RAW_FIELD"
    PROVIDER_METRIC = "PROVIDER_METRIC"


TushareScalar = str | int | None


class TushareOfflineRequest(FrozenProviderContract):
    endpoint: TushareEndpoint
    ts_code: str = Field(pattern=r"^\d{6}\.(?:SH|SZ|BJ)$")
    fields: tuple[str, ...] = Field(min_length=1, max_length=256)
    range_start: date
    range_end: date
    period: date | None
    offset: int = Field(ge=0, le=100_000_000)
    limit: int = Field(ge=1, le=10_000)

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("TUSHARE_FIELDS_MUST_BE_UNIQUE_AND_SORTED")
        if any(
            not item
            or len(item) > 64
            or not item.replace("_", "").isalnum()
            or item != item.casefold()
            for item in value
        ):
            raise ValueError("TUSHARE_FIELD_INVALID")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> TushareOfflineRequest:
        if self.range_end < self.range_start:
            raise ValueError("TUSHARE_RANGE_INVALID")
        if self.period is not None and not self.range_start <= self.period <= self.range_end:
            raise ValueError("TUSHARE_PERIOD_OUTSIDE_RANGE")
        return self

    @property
    def page_identity(self) -> str:
        return provider_checksum(self)


class TushareOfflineResponse(FrozenProviderContract):
    endpoint: TushareEndpoint
    fields: tuple[str, ...] = Field(min_length=1, max_length=256)
    items: tuple[tuple[TushareScalar, ...], ...] = Field(max_length=10_000)
    offset: int = Field(ge=0, le=100_000_000)
    has_more: bool

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return TushareOfflineRequest.validate_fields(value)

    @model_validator(mode="after")
    def validate_items(self) -> TushareOfflineResponse:
        if any(len(item) != len(self.fields) for item in self.items):
            raise ValueError("TUSHARE_ITEM_FIELD_COUNT_MISMATCH")
        if any(isinstance(value, (float, bool)) for item in self.items for value in item):
            raise ValueError("TUSHARE_BINARY_FLOAT_OR_BOOL_FORBIDDEN")
        return self


class TushareRecordMetadata(FrozenProviderContract):
    endpoint: TushareEndpoint
    ts_code: str = Field(pattern=r"^\d{6}\.(?:SH|SZ|BJ)$")
    provider_record_id: str = Field(min_length=1, max_length=256)
    ann_date: date | None
    actual_ann_date: date | None
    period: date | None
    update_flag: Literal["0", "1"] | None
    warning_codes: tuple[str, ...] = Field(max_length=64)

    @model_validator(mode="after")
    def validate_publication_semantics(self) -> TushareRecordMetadata:
        if self.ann_date is None and self.actual_ann_date is None:
            if "UNKNOWN_PUBLISHED_AT" not in self.warning_codes:
                raise ValueError("TUSHARE_PUBLICATION_SEMANTICS_REQUIRED")
        elif "UNKNOWN_PUBLISHED_AT" in self.warning_codes:
            raise ValueError("TUSHARE_PUBLICATION_WARNING_CONTRADICTS_DATE")
        if self.warning_codes != tuple(sorted(set(self.warning_codes))):
            raise ValueError("TUSHARE_WARNINGS_MUST_BE_UNIQUE_AND_SORTED")
        return self


class TushareFieldDescriptor(FrozenProviderContract):
    endpoint: TushareEndpoint
    field_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    field_role: TushareFieldRole
    canonical_formula_code: None

    @model_validator(mode="after")
    def validate_metric_provenance(self) -> TushareFieldDescriptor:
        if (
            self.endpoint is TushareEndpoint.FINA_INDICATOR
            and self.field_role is not TushareFieldRole.PROVIDER_METRIC
        ):
            raise ValueError("TUSHARE_INDICATOR_MUST_REMAIN_PROVIDER_METRIC")
        return self
