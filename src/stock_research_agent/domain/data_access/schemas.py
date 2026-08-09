"""Strict provider-neutral schemas for raw data access."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    PlainSerializer,
    field_validator,
    model_validator,
)

from stock_research_agent.domain.data_access.enums import (
    AccessMode,
    DataCategory,
    DataOrigin,
    LiveStatus,
    ProviderCapability,
    ProviderStatus,
    QualityStatus,
)

_PROVIDER_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_SEMANTIC_VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")


class DataAccessModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        from_attributes=True,
        hide_input_in_errors=True,
    )


def _reject_binary_float(value: object) -> object:
    if isinstance(value, float):
        raise ValueError("binary float input is not allowed for exact Decimal fields")
    return value


def _validate_numeric_38_12(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("exact Decimal fields must be finite")
    decimal_tuple = value.as_tuple()
    digits = list(decimal_tuple.digits)
    exponent = decimal_tuple.exponent
    if not isinstance(exponent, int):
        raise ValueError("exact Decimal fields must be finite")
    if not any(digits):
        return value
    while exponent < 0 and digits and digits[-1] == 0:
        digits.pop()
        exponent += 1
    fractional_digits = max(-exponent, 0)
    whole_digits = max(len(digits) + exponent, 0)
    if fractional_digits > 12:
        raise ValueError("exact Decimal fields support at most 12 fractional digits")
    if whole_digits > 26:
        raise ValueError("exact Decimal fields support at most 26 whole digits")
    return value


ExactDecimal = Annotated[
    Decimal,
    BeforeValidator(_reject_binary_float),
    AfterValidator(_validate_numeric_38_12),
    Field(max_digits=38, decimal_places=12, allow_inf_nan=False),
    PlainSerializer(lambda value: str(value), return_type=str, when_used="json"),
]

ProviderType = Literal["FIXTURE", "MARKET_DATA", "FINANCIAL_DATA", "FILINGS", "MULTI_SOURCE"]
TermsStatus = Literal["VERIFIED", "RESTRICTED", "NEEDS_REVIEW", "UNKNOWN"]
IngestionStatus = Literal["QUEUED", "RUNNING", "PASS", "PARTIAL", "BLOCKED", "FAIL", "CANCELLED"]
CacheStatus = Literal["MISS", "HIT", "REVALIDATED", "BYPASS", "NOT_APPLICABLE"]
AdjustmentType = Literal["UNADJUSTED", "PROVIDER_ADJUSTED"]
CorporateActionType = Literal[
    "CASH_DIVIDEND",
    "STOCK_SPLIT",
    "REVERSE_SPLIT",
    "STOCK_DIVIDEND",
    "RIGHTS_ISSUE",
    "SYMBOL_CHANGE",
    "OTHER",
]
CorporateActionStatus = Literal["ANNOUNCED", "CONFIRMED", "CANCELLED", "UNKNOWN"]
StatementType = Literal[
    "BALANCE_SHEET",
    "INCOME_STATEMENT",
    "CASH_FLOW",
    "EQUITY",
    "COMPREHENSIVE_INCOME",
    "OTHER",
]
DocumentType = Literal[
    "ANNUAL_REPORT",
    "QUARTERLY_REPORT",
    "INTERIM_REPORT",
    "EARNINGS_RELEASE",
    "MATERIAL_ANNOUNCEMENT",
    "SEC_10_K",
    "SEC_10_Q",
    "SEC_8_K",
    "INVESTOR_PRESENTATION",
    "OTHER",
]
DocumentStatus = Literal["METADATA_ONLY", "AVAILABLE", "DOWNLOAD_FAILED", "UNAVAILABLE", "UNKNOWN"]
SnapshotStatus = Literal["BUILDING", "COMPLETE", "PARTIAL", "FAILED", "SUPERSEDED"]
SnapshotSourceRecordType = Literal[
    "daily_price_bars", "corporate_actions", "provider_financial_facts", "source_documents"
]


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone aware")
    return value.astimezone(UTC)


def _normalize_optional_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return _normalize_utc(value)


def _reject_controls(value: str | None) -> str | None:
    if value is not None and any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError("control characters are not allowed")
    return value


_CREDENTIAL_QUERY_KEY_PARTS = {
    "auth",
    "authorization",
    "credential",
    "credentials",
    "key",
    "passwd",
    "password",
    "secret",
    "session",
    "sig",
    "signature",
    "token",
}
_CREDENTIAL_QUERY_KEYS = {
    "accesstoken",
    "apikey",
    "auth",
    "authorization",
    "authtoken",
    "clientsecret",
    "credential",
    "credentials",
    "key",
    "passwd",
    "password",
    "refreshtoken",
    "secret",
    "session",
    "sessionid",
    "sig",
    "signature",
    "token",
}


def _is_credential_query_key(key: str) -> bool:
    normalized = key.casefold()
    parts = set(re.findall(r"[a-z0-9]+", normalized))
    collapsed = re.sub(r"[^a-z0-9]", "", normalized)
    return bool(parts & _CREDENTIAL_QUERY_KEY_PARTS) or collapsed in _CREDENTIAL_QUERY_KEYS


def _validated_https_url(value: object) -> tuple[str, tuple[tuple[str, str], ...]]:
    if not isinstance(value, str):
        raise ValueError("URL must be a string")
    _reject_controls(value)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("URL contains an invalid host or port") from None
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("URL must be an absolute HTTPS URL")
    if port == 0:
        raise ValueError("URL port must be between 1 and 65535")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must not contain user information")
    if parsed.fragment:
        raise ValueError("URL must not contain a fragment")
    query = tuple(parse_qsl(parsed.query, keep_blank_values=True))
    return value, query


def _validate_request_log_url(value: object) -> str:
    original, query = _validated_https_url(value)
    for key, query_value in query:
        if _is_credential_query_key(key) and query_value != "***":
            raise ValueError("sensitive request URL query values must be redacted as ***")
    return original


def _validate_public_source_url(value: object) -> str:
    original, query = _validated_https_url(value)
    if any(_is_credential_query_key(key) for key, _query_value in query):
        raise ValueError("public source URLs must not contain credential query keys")
    return original


RequestLogUrl = Annotated[str, BeforeValidator(_validate_request_log_url)]
PublicSourceUrl = Annotated[str, BeforeValidator(_validate_public_source_url)]


class ProviderDescriptor(DataAccessModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    version: str
    status: ProviderStatus
    capabilities: frozenset[ProviderCapability]
    is_enabled: bool
    requires_credentials: bool
    credentials_configured: bool

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not _PROVIDER_CODE_PATTERN.fullmatch(value):
            raise ValueError("provider code must be an uppercase token of at most 64 characters")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not _SEMANTIC_VERSION_PATTERN.fullmatch(value):
            raise ValueError("provider version must use numeric X.Y.Z format")
        return value


class ProviderInstrument(DataAccessModel):
    security_id: UUID
    provider_symbol: str = Field(min_length=1, max_length=128)
    provider_exchange_code: str | None
    provider_instrument_id: str | None


class ProviderRequest(DataAccessModel):
    request_id: UUID
    instrument: ProviderInstrument
    category: DataCategory
    research_as_of_time: datetime
    date_from: date | None = None
    date_to: date | None = None
    parameters: dict[str, JsonValue] = Field(default_factory=dict)

    _research_as_of_utc = field_validator("research_as_of_time")(_normalize_utc)

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_to < self.date_from
        ):
            raise ValueError("date_to cannot precede date_from")
        return self


class DataQuality(DataAccessModel):
    status: QualityStatus
    required_fields_present: int = Field(ge=0)
    required_fields_total: int = Field(ge=0)
    missing_fields: tuple[str, ...] = ()
    duplicate_records: int = Field(default=0, ge=0)
    conflicting_records: int = Field(default=0, ge=0)
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_required_field_counts(self) -> Self:
        if self.required_fields_present > self.required_fields_total:
            raise ValueError("required_fields_present cannot exceed required_fields_total")
        return self


class ProviderRecord(DataAccessModel):
    record_type: str
    provider_record_id: str | None
    source_published_at: datetime | None
    data: dict[str, JsonValue | ExactDecimal]

    _source_published_at_utc = field_validator("source_published_at")(_normalize_optional_utc)


class ProviderEnvelope(DataAccessModel):
    provider_code: str
    provider_version: str
    category: DataCategory
    records: tuple[ProviderRecord, ...]
    raw_payload: bytes | dict[str, JsonValue] | list[JsonValue]
    content_type: str
    source_endpoint: str
    provider_request_id: str | None
    retrieved_at: datetime
    source_published_at: datetime | None
    warnings: tuple[str, ...]
    quality: DataQuality
    data_origin: DataOrigin
    access_mode: AccessMode
    live_status: LiveStatus

    _retrieved_at_utc = field_validator("retrieved_at")(_normalize_utc)
    _source_published_at_utc = field_validator("source_published_at")(_normalize_optional_utc)

    @model_validator(mode="after")
    def validate_origin_markers(self) -> Self:
        markers = (self.data_origin, self.access_mode, self.live_status)
        fixture_markers = (DataOrigin.FIXTURE, AccessMode.OFFLINE, LiveStatus.NOT_LIVE)
        live_markers = (DataOrigin.LIVE, AccessMode.ONLINE, LiveStatus.LIVE)
        if markers not in {fixture_markers, live_markers}:
            raise ValueError("data origin markers must form the approved fixture or live triple")
        return self


def _validate_optional_decimal(
    value: Decimal | None, *, strictly_positive: bool = False
) -> Decimal | None:
    if value is None:
        return None
    if not value.is_finite():
        raise ValueError("exact Decimal fields must be finite")
    if (strictly_positive and value <= 0) or (not strictly_positive and value < 0):
        comparator = "positive" if strictly_positive else "non-negative"
        raise ValueError(f"exact Decimal fields must be {comparator}")
    return value


class DataProviderWrite(DataAccessModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=128)
    provider_type: ProviderType
    status: ProviderStatus
    base_url: PublicSourceUrl | None = Field(default=None, max_length=2048)
    documentation_url: PublicSourceUrl | None = Field(default=None, max_length=2048)
    terms_status: TermsStatus
    capabilities: tuple[ProviderCapability, ...]


class DataProviderRecord(DataProviderWrite):
    id: UUID
    created_at: datetime
    updated_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)
    _updated_at_utc = field_validator("updated_at")(_normalize_utc)


class ProviderProvenanceRecord(DataAccessModel):
    """Minimum persisted provider fields needed to label tool evidence safely."""

    id: UUID
    code: str = Field(min_length=1, max_length=64)
    provider_type: ProviderType
    status: ProviderStatus
    terms_status: TermsStatus


class ProviderInstrumentMappingWrite(DataAccessModel):
    provider_id: UUID
    security_id: UUID
    provider_symbol: str = Field(min_length=1, max_length=128)
    provider_exchange_code: str | None = Field(default=None, max_length=64)
    provider_instrument_id: str | None = Field(default=None, max_length=256)
    valid_from: date | None = None
    valid_to: date | None = None
    is_primary: bool = False
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    source_name: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_validity(self) -> Self:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to cannot precede valid_from")
        return self


class ProviderInstrumentMappingRecord(ProviderInstrumentMappingWrite):
    id: UUID
    created_at: datetime
    updated_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)
    _updated_at_utc = field_validator("updated_at")(_normalize_utc)


class IngestionRunWrite(DataAccessModel):
    provider_id: UUID
    security_id: UUID
    category: DataCategory
    research_as_of_time: datetime
    idempotency_key: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9:_-]{0,127}$"
    )
    requested_at: datetime

    _research_as_of_utc = field_validator("research_as_of_time")(_normalize_utc)
    _requested_at_utc = field_validator("requested_at")(_normalize_utc)


class IngestionRunUpdate(DataAccessModel):
    status: IngestionStatus | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    request_count: int = Field(default=0, ge=0)
    records_received: int = Field(default=0, ge=0)
    records_stored: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    error_code: str | None = Field(default=None, min_length=1, max_length=64)
    safe_error_message: str | None = Field(default=None, min_length=1, max_length=512)

    _started_at_utc = field_validator("started_at")(_normalize_optional_utc)
    _completed_at_utc = field_validator("completed_at")(_normalize_optional_utc)
    _safe_error_text = field_validator("error_code", "safe_error_message")(_reject_controls)

    @model_validator(mode="after")
    def validate_status_shape(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("an ingestion run patch must set at least one field")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be explicitly cleared")
        if self.status == "QUEUED" and (
            self.started_at is not None or self.completed_at is not None
        ):
            raise ValueError("QUEUED runs cannot have lifecycle timestamps")
        if self.status == "RUNNING" and (self.started_at is None or self.completed_at is not None):
            raise ValueError("RUNNING runs require started_at and no completed_at")
        terminal = {"PASS", "PARTIAL", "BLOCKED", "FAIL", "CANCELLED"}
        if self.status in terminal and self.completed_at is None:
            raise ValueError("terminal runs require completed_at")
        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("completed_at cannot precede started_at")
        return self


class IngestionRunRecord(DataAccessModel):
    id: UUID
    provider_id: UUID
    security_id: UUID
    category: DataCategory
    status: IngestionStatus
    research_as_of_time: datetime
    idempotency_key: str
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    request_count: int
    records_received: int
    records_stored: int
    warning_count: int
    error_code: str | None
    safe_error_message: str | None
    created_at: datetime
    updated_at: datetime

    _timestamps_utc = field_validator(
        "research_as_of_time", "requested_at", "created_at", "updated_at"
    )(_normalize_utc)
    _optional_timestamps_utc = field_validator("started_at", "completed_at")(
        _normalize_optional_utc
    )


class ProviderRequestLogWrite(DataAccessModel):
    ingestion_run_id: UUID
    provider_id: UUID
    caller_request_id: UUID
    provider_request_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
    )
    endpoint_name: str = Field(min_length=1, max_length=128)
    method: str = Field(pattern=r"^(GET|HEAD)$")
    safe_url: RequestLogUrl = Field(min_length=1, max_length=2048)
    request_started_at: datetime
    response_received_at: datetime | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)
    attempt: int = Field(gt=0)
    cache_status: CacheStatus
    etag: str | None = Field(default=None, min_length=1, max_length=512)
    last_modified: str | None = Field(default=None, min_length=1, max_length=128)
    response_size: int | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, min_length=1, max_length=64)

    _request_started_at_utc = field_validator("request_started_at")(_normalize_utc)
    _response_received_at_utc = field_validator("response_received_at")(_normalize_optional_utc)
    _safe_text = field_validator("endpoint_name", "error_code")(_reject_controls)

    @model_validator(mode="after")
    def validate_response_order(self) -> Self:
        if (
            self.response_received_at is not None
            and self.response_received_at < self.request_started_at
        ):
            raise ValueError("response_received_at cannot precede request_started_at")
        return self


class ProviderRequestLogRecord(ProviderRequestLogWrite):
    id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class RawPayloadWrite(DataAccessModel):
    ingestion_run_id: UUID
    provider_request_log_id: UUID
    provider_id: UUID
    security_id: UUID
    category: DataCategory
    content_type: str = Field(min_length=1, max_length=128)
    storage_uri: str | None = Field(default=None, min_length=10, max_length=1024)
    inline_json: dict[str, JsonValue] | list[JsonValue] | None = None
    checksum_algorithm: str = Field(default="sha256", pattern=r"^sha256$")
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_published_at: datetime | None = None
    retrieved_at: datetime
    provider_version: str = Field(min_length=1, max_length=64)
    parser_version: str = Field(min_length=1, max_length=64)
    schema_version: str = Field(min_length=1, max_length=64)
    byte_size: int = Field(ge=0)

    _source_published_at_utc = field_validator("source_published_at")(_normalize_optional_utc)
    _retrieved_at_utc = field_validator("retrieved_at")(_normalize_utc)

    @model_validator(mode="after")
    def validate_storage_shape(self) -> Self:
        if (self.storage_uri is None) == (self.inline_json is None):
            raise ValueError("exactly one of storage_uri and inline_json is required")
        if self.storage_uri is not None and not re.fullmatch(
            r"blob://[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*",
            self.storage_uri,
        ):
            raise ValueError("storage_uri must be an opaque blob URI")
        return self


class RawPayloadRecord(RawPayloadWrite):
    id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class RawPayloadMetadataRecord(DataAccessModel):
    id: UUID
    ingestion_run_id: UUID
    provider_request_log_id: UUID
    provider_id: UUID
    security_id: UUID
    category: DataCategory
    content_type: str
    checksum_algorithm: str
    checksum: str
    source_published_at: datetime | None
    retrieved_at: datetime
    provider_version: str
    parser_version: str
    schema_version: str
    byte_size: int
    created_at: datetime

    _source_published_at_utc = field_validator("source_published_at")(_normalize_optional_utc)
    _timestamps_utc = field_validator("retrieved_at", "created_at")(_normalize_utc)


class DailyPriceBarWrite(DataAccessModel):
    security_id: UUID
    provider_id: UUID
    source_payload_id: UUID
    provider_symbol: str = Field(min_length=1, max_length=128)
    trading_date: date
    market_timestamp: datetime | None = None
    open: ExactDecimal | None = None
    high: ExactDecimal | None = None
    low: ExactDecimal | None = None
    close: ExactDecimal | None = None
    volume: int | None = Field(default=None, ge=0)
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    adjustment_type: AdjustmentType | None = None
    provider_adjusted_close: ExactDecimal | None = None
    source_published_at: datetime | None = None
    retrieved_at: datetime

    _market_timestamp_utc = field_validator("market_timestamp")(_normalize_optional_utc)
    _source_published_at_utc = field_validator("source_published_at")(_normalize_optional_utc)
    _retrieved_at_utc = field_validator("retrieved_at")(_normalize_utc)

    @field_validator("open", "high", "low", "close", "provider_adjusted_close")
    @classmethod
    def validate_nonnegative_decimal(cls, value: Decimal | None) -> Decimal | None:
        return _validate_optional_decimal(value)

    @model_validator(mode="after")
    def validate_high_low(self) -> Self:
        if self.high is not None and self.low is not None and self.high < self.low:
            raise ValueError("high cannot be less than low")
        return self


class DailyPriceBarRecord(DailyPriceBarWrite):
    id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class CorporateActionWrite(DataAccessModel):
    security_id: UUID
    provider_id: UUID
    source_payload_id: UUID
    provider_action_id: str | None = Field(default=None, min_length=1, max_length=256)
    action_type: CorporateActionType
    announcement_date: date | None = None
    ex_date: date | None = None
    record_date: date | None = None
    payment_date: date | None = None
    cash_amount: ExactDecimal | None = None
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    ratio_numerator: ExactDecimal | None = None
    ratio_denominator: ExactDecimal | None = None
    status: CorporateActionStatus
    source_published_at: datetime | None = None
    retrieved_at: datetime

    _source_published_at_utc = field_validator("source_published_at")(_normalize_optional_utc)
    _retrieved_at_utc = field_validator("retrieved_at")(_normalize_utc)

    @field_validator("cash_amount")
    @classmethod
    def validate_cash_amount(cls, value: Decimal | None) -> Decimal | None:
        return _validate_optional_decimal(value)

    @field_validator("ratio_numerator", "ratio_denominator")
    @classmethod
    def validate_ratio(cls, value: Decimal | None) -> Decimal | None:
        return _validate_optional_decimal(value, strictly_positive=True)


class CorporateActionRecord(CorporateActionWrite):
    id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class SourceDocumentWrite(DataAccessModel):
    security_id: UUID
    provider_id: UUID
    source_payload_id: UUID
    provider_document_id: str | None = Field(default=None, min_length=1, max_length=256)
    document_type: DocumentType
    title: str = Field(min_length=1, max_length=512)
    form_type: str | None = Field(default=None, max_length=64)
    accession_number: str | None = Field(default=None, max_length=64)
    announcement_id: str | None = Field(default=None, max_length=256)
    period_end: date | None = None
    filed_at: datetime | None = None
    published_at: datetime | None = None
    source_url: PublicSourceUrl = Field(min_length=1, max_length=2048)
    primary_document_name: str | None = Field(default=None, max_length=256)
    mime_type: str | None = Field(default=None, max_length=128)
    storage_uri: str | None = Field(default=None, min_length=10, max_length=1024)
    checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    byte_size: int | None = Field(default=None, ge=0)
    document_status: DocumentStatus
    retrieved_at: datetime

    _filed_at_utc = field_validator("filed_at")(_normalize_optional_utc)
    _published_at_utc = field_validator("published_at")(_normalize_optional_utc)
    _retrieved_at_utc = field_validator("retrieved_at")(_normalize_utc)

    @field_validator("storage_uri")
    @classmethod
    def validate_storage_uri(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(
            r"blob://[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*",
            value,
        ):
            raise ValueError("storage_uri must be an opaque blob URI")
        return value


class SourceDocumentRecord(DataAccessModel):
    id: UUID
    security_id: UUID
    provider_id: UUID
    source_payload_id: UUID
    provider_document_id: str | None
    document_type: DocumentType
    title: str
    form_type: str | None
    accession_number: str | None
    announcement_id: str | None
    period_end: date | None
    filed_at: datetime | None
    published_at: datetime | None
    source_url: PublicSourceUrl
    primary_document_name: str | None
    mime_type: str | None
    checksum: str | None
    byte_size: int | None
    document_status: DocumentStatus
    retrieved_at: datetime
    created_at: datetime
    updated_at: datetime

    _optional_timestamps_utc = field_validator("filed_at", "published_at")(_normalize_optional_utc)
    _timestamps_utc = field_validator("retrieved_at", "created_at", "updated_at")(_normalize_utc)


class ProviderFinancialFactWrite(DataAccessModel):
    security_id: UUID
    provider_id: UUID
    source_payload_id: UUID
    document_id: UUID | None = None
    statement_type: StatementType
    provider_concept: str = Field(min_length=1, max_length=512)
    reported_label: str | None = Field(default=None, max_length=512)
    taxonomy: str | None = Field(default=None, max_length=256)
    context_id: str | None = Field(default=None, max_length=256)
    dimensions: dict[str, JsonValue] = Field(default_factory=dict)
    value: ExactDecimal | None = None
    unit: str | None = Field(default=None, max_length=64)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    fiscal_year: int | None = Field(default=None, ge=1900, le=9999)
    fiscal_quarter: int | None = Field(default=None, ge=1, le=4)
    fiscal_period: str | None = Field(default=None, max_length=32)
    period_start: date | None = None
    period_end: date | None = None
    instant_date: date | None = None
    filed_at: datetime | None = None
    source_published_at: datetime | None = None
    form_type: str | None = Field(default=None, max_length=64)
    is_annual: bool | None = None
    is_cumulative: bool | None = None
    is_audited: bool | None = None
    is_restated: bool | None = None
    provider_record_id: str | None = Field(default=None, max_length=256)
    retrieved_at: datetime

    _filed_at_utc = field_validator("filed_at")(_normalize_optional_utc)
    _source_published_at_utc = field_validator("source_published_at")(_normalize_optional_utc)
    _retrieved_at_utc = field_validator("retrieved_at")(_normalize_utc)

    @field_validator("value")
    @classmethod
    def validate_finite_value(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("financial fact value must be finite")
        return value

    @model_validator(mode="after")
    def validate_period_order(self) -> Self:
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_end < self.period_start
        ):
            raise ValueError("period_end cannot precede period_start")
        return self


class ProviderFinancialFactRecord(ProviderFinancialFactWrite):
    id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class DataSnapshotWrite(DataAccessModel):
    security_id: UUID
    research_as_of_time: datetime
    snapshot_version: int = Field(gt=0)
    status: SnapshotStatus
    completed_at: datetime | None = None
    checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    formula_version: str = Field(pattern=r"^raw-data-v1$")
    notes: str | None = Field(default=None, min_length=1, max_length=1024)

    _research_as_of_utc = field_validator("research_as_of_time")(_normalize_utc)
    _completed_at_utc = field_validator("completed_at")(_normalize_optional_utc)

    @model_validator(mode="after")
    def validate_completion_shape(self) -> Self:
        if self.status == "BUILDING" and (
            self.completed_at is not None or self.checksum is not None
        ):
            raise ValueError("BUILDING snapshot cannot be completed")
        if self.status in {"COMPLETE", "PARTIAL", "SUPERSEDED"} and (
            self.completed_at is None or self.checksum is None
        ):
            raise ValueError("completed snapshots require completed_at and checksum")
        if self.status == "FAILED" and (self.completed_at is None or self.checksum is not None):
            raise ValueError("FAILED snapshot requires completed_at and no checksum")
        if self.status not in {"BUILDING", "COMPLETE", "PARTIAL", "FAILED", "SUPERSEDED"}:
            raise ValueError("unsupported snapshot status")
        return self


class DataSnapshotRecord(DataSnapshotWrite):
    id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class DataSnapshotUpdate(DataAccessModel):
    """Allowed one-way update from BUILDING to a terminal snapshot state."""

    status: Literal["COMPLETE", "PARTIAL", "FAILED"]
    completed_at: datetime
    checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    notes: str | None = Field(default=None, min_length=1, max_length=1024)

    _completed_at_utc = field_validator("completed_at")(_normalize_utc)

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> Self:
        if self.status == "FAILED" and self.checksum is not None:
            raise ValueError("FAILED snapshot cannot have a checksum")
        if self.status in {"COMPLETE", "PARTIAL"} and self.checksum is None:
            raise ValueError("completed snapshot requires a checksum")
        return self


class SnapshotItemWrite(DataAccessModel):
    snapshot_id: UUID
    provider_id: UUID
    category: DataCategory
    source_record_type: SnapshotSourceRecordType
    source_record_id: UUID
    source_published_at: datetime | None = None
    retrieved_at: datetime
    checksum_input: str = Field(min_length=1, max_length=4096)
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    _source_published_at_utc = field_validator("source_published_at")(_normalize_optional_utc)
    _retrieved_at_utc = field_validator("retrieved_at")(_normalize_utc)


class SnapshotItemRecord(SnapshotItemWrite):
    id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class SnapshotEvidenceAggregateRecord(DataAccessModel):
    """Safe whole-snapshot provenance aggregate with no item payload projection."""

    snapshot_id: UUID
    provider_ids: tuple[UUID, ...] = Field(max_length=396)
    latest_retrieved_at: datetime | None
    item_count: int = Field(ge=0, le=396)

    _latest_retrieved_at_utc = field_validator("latest_retrieved_at")(_normalize_optional_utc)

    @field_validator("provider_ids")
    @classmethod
    def validate_provider_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value) or value != tuple(sorted(value, key=str)):
            raise ValueError("aggregate provider IDs must be unique and sorted")
        return value

    @model_validator(mode="after")
    def validate_aggregate_shape(self) -> Self:
        if self.item_count == 0:
            if self.provider_ids or self.latest_retrieved_at is not None:
                raise ValueError("empty aggregate cannot contain provider or retrieval data")
        elif (
            not self.provider_ids
            or self.latest_retrieved_at is None
            or len(self.provider_ids) > self.item_count
        ):
            raise ValueError("non-empty aggregate requires consistent provider and retrieval data")
        return self


class DataQueryResult[RecordT](DataAccessModel):
    status: QualityStatus
    records: tuple[RecordT, ...]
    warnings: tuple[str, ...] = ()
