"""SQLAlchemy persistence models for raw provider data and point-in-time snapshots."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_research_agent.db.base import Base


class _TimestampedUuidMixin:
    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class _ImmutableUuidMixin:
    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())


_DATA_CATEGORIES = (
    "DAILY_PRICES",
    "CORPORATE_ACTIONS",
    "FINANCIAL_FACTS",
    "FILING_METADATA",
    "SOURCE_DOCUMENTS",
)
_CATEGORY_SQL = ", ".join(f"'{value}'" for value in _DATA_CATEGORIES)


class DataProvider(_TimestampedUuidMixin, Base):
    __tablename__ = "data_providers"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_data_providers"),
        UniqueConstraint("code", name="uq_data_providers_code"),
        CheckConstraint("code ~ '^[A-Z][A-Z0-9_]{0,63}$'", name="ck_data_providers_code_format"),
        CheckConstraint("length(name) BETWEEN 1 AND 128", name="ck_data_providers_name_length"),
        CheckConstraint(
            "provider_type IN ('FIXTURE', 'MARKET_DATA', 'FINANCIAL_DATA', "
            "'FILINGS', 'MULTI_SOURCE')",
            name="ck_data_providers_provider_type",
        ),
        CheckConstraint(
            "status IN ('APPROVED', 'APPROVED_FOR_PERSONAL_RESEARCH_ONLY', "
            "'NEEDS_CREDENTIALS', 'NEEDS_LICENSE_CONFIRMATION', 'EXPERIMENTAL', "
            "'NOT_ALLOWED')",
            name="ck_data_providers_status",
        ),
        CheckConstraint(
            "terms_status IN ('VERIFIED', 'RESTRICTED', 'NEEDS_REVIEW', 'UNKNOWN')",
            name="ck_data_providers_terms_status",
        ),
        CheckConstraint(
            "base_url IS NULL OR length(base_url) BETWEEN 1 AND 2048",
            name="ck_data_providers_base_url_length",
        ),
        CheckConstraint(
            "documentation_url IS NULL OR length(documentation_url) BETWEEN 1 AND 2048",
            name="ck_data_providers_documentation_url_length",
        ),
        CheckConstraint(
            "jsonb_typeof(capabilities) = 'array'",
            name="ck_data_providers_capabilities_array",
        ),
    )

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(2048))
    documentation_url: Mapped[str | None] = mapped_column(String(2048))
    terms_status: Mapped[str] = mapped_column(String(32), nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    instrument_mappings: Mapped[list[ProviderInstrumentMapping]] = relationship(
        back_populates="provider", passive_deletes=True
    )


class ProviderInstrumentMapping(_TimestampedUuidMixin, Base):
    __tablename__ = "provider_instrument_mappings"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_instrument_mappings"),
        ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_provider_mappings_provider_id_data_providers",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_provider_mappings_security_id_securities",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider_id",
            "security_id",
            "provider_symbol",
            "valid_from",
            name="uq_provider_mappings_identity",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "length(provider_symbol) BETWEEN 1 AND 128",
            name="ck_provider_mappings_symbol_length",
        ),
        CheckConstraint(
            "provider_exchange_code IS NULL OR length(provider_exchange_code) BETWEEN 1 AND 64",
            name="ck_provider_mappings_exchange_code_length",
        ),
        CheckConstraint(
            "provider_instrument_id IS NULL OR length(provider_instrument_id) BETWEEN 1 AND 256",
            name="ck_provider_mappings_instrument_id_length",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_provider_mappings_validity",
        ),
        CheckConstraint(
            "length(source_name) BETWEEN 1 AND 256",
            name="ck_provider_mappings_source_name_length",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'", name="ck_provider_mappings_metadata_object"
        ),
        Index(
            "ix_provider_mappings_security_provider_active",
            "security_id",
            "provider_id",
            postgresql_where=text("valid_to IS NULL"),
        ),
        Index(
            "uq_provider_mappings_active_symbol",
            "provider_id",
            "provider_symbol",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
        Index(
            "uq_provider_mappings_active_instrument_id",
            "provider_id",
            "provider_instrument_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND provider_instrument_id IS NOT NULL"),
        ),
    )

    provider_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_exchange_code: Mapped[str | None] = mapped_column(String(64))
    provider_instrument_id: Mapped[str | None] = mapped_column(String(256))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mapping_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False)
    source_name: Mapped[str] = mapped_column(String(256), nullable=False)

    provider: Mapped[DataProvider] = relationship(back_populates="instrument_mappings")


class IngestionRun(_TimestampedUuidMixin, Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_ingestion_runs"),
        ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_ingestion_runs_provider_id_data_providers",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_ingestion_runs_security_id_securities",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("idempotency_key", name="uq_ingestion_runs_idempotency_key"),
        CheckConstraint(f"category IN ({_CATEGORY_SQL})", name="ck_ingestion_runs_category"),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'PASS', 'PARTIAL', 'BLOCKED', 'FAIL', 'CANCELLED')",
            name="ck_ingestion_runs_status",
        ),
        CheckConstraint(
            "idempotency_key ~ '^[a-z0-9][a-z0-9:_-]{0,127}$'",
            name="ck_ingestion_runs_idempotency_key_format",
        ),
        CheckConstraint(
            "started_at IS NULL OR started_at >= requested_at",
            name="ck_ingestion_runs_started_order",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= COALESCE(started_at, requested_at)",
            name="ck_ingestion_runs_completed_order",
        ),
        CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('PASS', 'PARTIAL', 'BLOCKED', 'FAIL', 'CANCELLED') "
            "AND completed_at IS NOT NULL)",
            name="ck_ingestion_runs_status_timestamps",
        ),
        CheckConstraint(
            "request_count >= 0 AND records_received >= 0 AND records_stored >= 0 "
            "AND warning_count >= 0",
            name="ck_ingestion_runs_nonnegative_counts",
        ),
        CheckConstraint(
            "error_code IS NULL OR length(error_code) BETWEEN 1 AND 64",
            name="ck_ingestion_runs_error_code_length",
        ),
        CheckConstraint(
            "safe_error_message IS NULL OR length(safe_error_message) BETWEEN 1 AND 512",
            name="ck_ingestion_runs_safe_error_length",
        ),
        Index(
            "ix_ingestion_runs_security_category_as_of",
            "security_id",
            "category",
            "research_as_of_time",
        ),
    )

    provider_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    research_as_of_time: Mapped[datetime] = mapped_column(nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(nullable=False)
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_stored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(String(512))


class ProviderRequestLog(_ImmutableUuidMixin, Base):
    __tablename__ = "provider_request_logs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_request_logs"),
        ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name="fk_provider_request_logs_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_provider_request_logs_provider_id_data_providers",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "provider_request_id IS NULL OR "
            "provider_request_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$'",
            name="ck_provider_request_logs_provider_request_id_format",
        ),
        CheckConstraint(
            "length(endpoint_name) BETWEEN 1 AND 128",
            name="ck_provider_request_logs_endpoint_length",
        ),
        CheckConstraint("method IN ('GET', 'HEAD')", name="ck_provider_request_logs_method"),
        CheckConstraint(
            "length(safe_url) BETWEEN 1 AND 2048",
            name="ck_provider_request_logs_safe_url_length",
        ),
        CheckConstraint(
            "response_received_at IS NULL OR response_received_at >= request_started_at",
            name="ck_provider_request_logs_response_order",
        ),
        CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599",
            name="ck_provider_request_logs_http_status",
        ),
        CheckConstraint("attempt > 0", name="ck_provider_request_logs_attempt_positive"),
        CheckConstraint(
            "cache_status IN ('MISS', 'HIT', 'REVALIDATED', 'BYPASS', 'NOT_APPLICABLE')",
            name="ck_provider_request_logs_cache_status",
        ),
        CheckConstraint(
            "etag IS NULL OR length(etag) BETWEEN 1 AND 512",
            name="ck_provider_request_logs_etag_length",
        ),
        CheckConstraint(
            "last_modified IS NULL OR length(last_modified) BETWEEN 1 AND 128",
            name="ck_provider_request_logs_last_modified_length",
        ),
        CheckConstraint(
            "response_size IS NULL OR response_size >= 0",
            name="ck_provider_request_logs_response_size",
        ),
        CheckConstraint(
            "error_code IS NULL OR length(error_code) BETWEEN 1 AND 64",
            name="ck_provider_request_logs_error_code_length",
        ),
        Index("ix_provider_request_logs_ingestion_run", "ingestion_run_id", "created_at"),
    )

    ingestion_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    caller_request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(256))
    endpoint_name: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    safe_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    request_started_at: Mapped[datetime] = mapped_column(nullable=False)
    response_received_at: Mapped[datetime | None] = mapped_column()
    http_status: Mapped[int | None] = mapped_column(Integer)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_status: Mapped[str] = mapped_column(String(32), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(512))
    last_modified: Mapped[str | None] = mapped_column(String(128))
    response_size: Mapped[int | None] = mapped_column(BigInteger)
    error_code: Mapped[str | None] = mapped_column(String(64))


class RawPayload(_ImmutableUuidMixin, Base):
    __tablename__ = "raw_payloads"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_raw_payloads"),
        ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name="fk_raw_payloads_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_request_log_id"],
            ["provider_request_logs.id"],
            name="fk_raw_payloads_request_id_provider_request_logs",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["manual_evidence_import_request_id"],
            ["manual_evidence_import_requests.id"],
            name="fk_raw_payloads_manual_evidence_import_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_raw_payloads_provider_id_data_providers",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_raw_payloads_security_id_securities",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"category IN ({_CATEGORY_SQL})", name="ck_raw_payloads_category"),
        CheckConstraint(
            "length(content_type) BETWEEN 1 AND 128", name="ck_raw_payloads_content_type_length"
        ),
        CheckConstraint(
            "(storage_uri IS NOT NULL AND inline_json IS NULL) OR "
            "(storage_uri IS NULL AND inline_json IS NOT NULL)",
            name="ck_raw_payloads_storage_shape",
        ),
        CheckConstraint(
            "storage_uri IS NULL OR length(storage_uri) BETWEEN 10 AND 1024",
            name="ck_raw_payloads_storage_uri_length",
        ),
        CheckConstraint(
            "storage_uri IS NULL OR storage_uri ~ "
            "'^blob://[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*"
            "(/[A-Za-z0-9][A-Za-z0-9._-]*)*$'",
            name="ck_raw_payloads_storage_uri_format",
        ),
        CheckConstraint("checksum_algorithm = 'sha256'", name="ck_raw_payloads_checksum_algorithm"),
        CheckConstraint("checksum ~ '^[0-9a-f]{64}$'", name="ck_raw_payloads_checksum_format"),
        CheckConstraint(
            "length(provider_version) BETWEEN 1 AND 64 AND "
            "length(parser_version) BETWEEN 1 AND 64 AND "
            "length(schema_version) BETWEEN 1 AND 64",
            name="ck_raw_payloads_versions_length",
        ),
        CheckConstraint("byte_size >= 0", name="ck_raw_payloads_byte_size"),
        CheckConstraint(
            "(provider_request_log_id IS NOT NULL)::int + "
            "(manual_evidence_import_request_id IS NOT NULL)::int = 1",
            name="ck_raw_payloads_exactly_one_source",
        ),
        Index("ix_raw_payloads_checksum", "checksum"),
        Index(
            "ix_raw_payloads_security_category_source_time",
            "security_id",
            "category",
            "source_published_at",
        ),
    )

    ingestion_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_request_log_id: Mapped[UUID | None] = mapped_column(Uuid)
    manual_evidence_import_request_id: Mapped[UUID | None] = mapped_column(Uuid)
    provider_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(String(2048))
    inline_json: Mapped[dict[str, object] | list[object] | None] = mapped_column(JSONB)
    checksum_algorithm: Mapped[str] = mapped_column(String(16), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column()
    retrieved_at: Mapped[datetime] = mapped_column(nullable=False)
    provider_version: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)


class DailyPriceBar(_ImmutableUuidMixin, Base):
    __tablename__ = "daily_price_bars"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_daily_price_bars"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_daily_price_bars_security_id_securities",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_daily_price_bars_provider_id_data_providers",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_payload_id"],
            ["raw_payloads.id"],
            name="fk_daily_price_bars_payload_id_raw_payloads",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider_id",
            "provider_symbol",
            "trading_date",
            "adjustment_type",
            "source_payload_id",
            name="uq_daily_price_bars_provider_revision",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "length(provider_symbol) BETWEEN 1 AND 128",
            name="ck_daily_price_bars_provider_symbol_length",
        ),
        CheckConstraint(
            "open IS NULL OR (open != 'NaN'::numeric AND open >= 0)",
            name="ck_daily_price_bars_open_nonnegative",
        ),
        CheckConstraint(
            "high IS NULL OR (high != 'NaN'::numeric AND high >= 0)",
            name="ck_daily_price_bars_high_nonnegative",
        ),
        CheckConstraint(
            "low IS NULL OR (low != 'NaN'::numeric AND low >= 0)",
            name="ck_daily_price_bars_low_nonnegative",
        ),
        CheckConstraint(
            "close IS NULL OR (close != 'NaN'::numeric AND close >= 0)",
            name="ck_daily_price_bars_close_nonnegative",
        ),
        CheckConstraint("volume IS NULL OR volume >= 0", name="ck_daily_price_bars_volume"),
        CheckConstraint(
            "provider_adjusted_close IS NULL OR "
            "(provider_adjusted_close != 'NaN'::numeric AND provider_adjusted_close >= 0)",
            name="ck_daily_price_bars_adjusted_close_nonnegative",
        ),
        CheckConstraint(
            "high IS NULL OR low IS NULL OR high >= low", name="ck_daily_price_bars_high_low"
        ),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="ck_daily_price_bars_currency_code"),
        CheckConstraint(
            "adjustment_type IN ('UNADJUSTED', 'PROVIDER_ADJUSTED')",
            name="ck_daily_price_bars_adjustment_type",
        ),
        Index("ix_daily_price_bars_security_date", "security_id", "trading_date"),
        Index(
            "ix_daily_price_bars_provider_symbol_date",
            "provider_id",
            "provider_symbol",
            "trading_date",
        ),
    )

    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_payload_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    market_timestamp: Mapped[datetime | None] = mapped_column()
    open: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    high: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    low: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    close: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    adjustment_type: Mapped[str | None] = mapped_column(String(32))
    provider_adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    source_published_at: Mapped[datetime | None] = mapped_column()
    retrieved_at: Mapped[datetime] = mapped_column(nullable=False)


class CorporateAction(_ImmutableUuidMixin, Base):
    __tablename__ = "corporate_actions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_corporate_actions"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_corporate_actions_security_id_securities",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_corporate_actions_provider_id_data_providers",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_payload_id"],
            ["raw_payloads.id"],
            name="fk_corporate_actions_payload_id_raw_payloads",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "provider_action_id IS NULL OR length(provider_action_id) BETWEEN 1 AND 256",
            name="ck_corporate_actions_provider_action_id_length",
        ),
        CheckConstraint(
            "action_type IN ('CASH_DIVIDEND', 'STOCK_SPLIT', 'REVERSE_SPLIT', "
            "'STOCK_DIVIDEND', 'RIGHTS_ISSUE', 'SYMBOL_CHANGE', 'OTHER')",
            name="ck_corporate_actions_action_type",
        ),
        CheckConstraint(
            "cash_amount IS NULL OR (cash_amount != 'NaN'::numeric AND cash_amount >= 0)",
            name="ck_corporate_actions_cash_amount",
        ),
        CheckConstraint(
            "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'",
            name="ck_corporate_actions_currency_code",
        ),
        CheckConstraint(
            "ratio_numerator IS NULL OR "
            "(ratio_numerator != 'NaN'::numeric AND ratio_numerator > 0)",
            name="ck_corporate_actions_ratio_numerator",
        ),
        CheckConstraint(
            "ratio_denominator IS NULL OR "
            "(ratio_denominator != 'NaN'::numeric AND ratio_denominator > 0)",
            name="ck_corporate_actions_ratio_denominator",
        ),
        CheckConstraint(
            "status IN ('ANNOUNCED', 'CONFIRMED', 'CANCELLED', 'UNKNOWN')",
            name="ck_corporate_actions_status",
        ),
        Index("ix_corporate_actions_security_ex_date", "security_id", "ex_date"),
        Index(
            "uq_corporate_actions_provider_action_payload",
            "provider_id",
            "provider_action_id",
            "source_payload_id",
            unique=True,
            postgresql_where=text("provider_action_id IS NOT NULL"),
        ),
        Index(
            "uq_corporate_actions_anonymous_natural_key",
            "provider_id",
            "security_id",
            "source_payload_id",
            "action_type",
            "announcement_date",
            "ex_date",
            "record_date",
            "payment_date",
            "cash_amount",
            "currency_code",
            "ratio_numerator",
            "ratio_denominator",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where=text("provider_action_id IS NULL"),
        ),
    )

    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_payload_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_action_id: Mapped[str | None] = mapped_column(String(256))
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    announcement_date: Mapped[date | None] = mapped_column(Date)
    ex_date: Mapped[date | None] = mapped_column(Date)
    record_date: Mapped[date | None] = mapped_column(Date)
    payment_date: Mapped[date | None] = mapped_column(Date)
    cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    ratio_numerator: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    ratio_denominator: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column()
    retrieved_at: Mapped[datetime] = mapped_column(nullable=False)


class SourceDocument(_TimestampedUuidMixin, Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_source_documents"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_source_documents_security_id_securities",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_source_documents_provider_id_data_providers",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_payload_id"],
            ["raw_payloads.id"],
            name="fk_source_documents_payload_id_raw_payloads",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider_id",
            "provider_document_id",
            "source_payload_id",
            name="uq_source_documents_provider_document_payload",
        ),
        UniqueConstraint(
            "provider_id",
            "accession_number",
            "source_payload_id",
            name="uq_source_documents_provider_accession_payload",
        ),
        CheckConstraint(
            "provider_document_id IS NULL OR length(provider_document_id) BETWEEN 1 AND 256",
            name="ck_source_documents_provider_document_id_length",
        ),
        CheckConstraint(
            "document_type IN ('ANNUAL_REPORT', 'QUARTERLY_REPORT', 'INTERIM_REPORT', "
            "'EARNINGS_RELEASE', 'MATERIAL_ANNOUNCEMENT', 'SEC_10_K', 'SEC_10_Q', "
            "'SEC_8_K', 'INVESTOR_PRESENTATION', 'OTHER')",
            name="ck_source_documents_document_type",
        ),
        CheckConstraint("length(title) BETWEEN 1 AND 512", name="ck_source_documents_title"),
        CheckConstraint(
            "length(source_url) BETWEEN 1 AND 2048", name="ck_source_documents_source_url"
        ),
        CheckConstraint(
            "storage_uri IS NULL OR length(storage_uri) BETWEEN 10 AND 1024",
            name="ck_source_documents_storage_uri_length",
        ),
        CheckConstraint(
            "storage_uri IS NULL OR storage_uri ~ "
            "'^blob://[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*"
            "(/[A-Za-z0-9][A-Za-z0-9._-]*)*$'",
            name="ck_source_documents_storage_uri_format",
        ),
        CheckConstraint(
            "checksum IS NULL OR checksum ~ '^[0-9a-f]{64}$'",
            name="ck_source_documents_checksum_format",
        ),
        CheckConstraint(
            "byte_size IS NULL OR byte_size >= 0", name="ck_source_documents_byte_size"
        ),
        CheckConstraint(
            "document_status IN ('METADATA_ONLY', 'AVAILABLE', 'DOWNLOAD_FAILED', "
            "'UNAVAILABLE', 'UNKNOWN')",
            name="ck_source_documents_status",
        ),
        Index("ix_source_documents_security_published_at", "security_id", "published_at"),
        Index("ix_source_documents_accession_number", "accession_number"),
        Index("ix_source_documents_provider_document_id", "provider_id", "provider_document_id"),
    )

    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_payload_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_document_id: Mapped[str | None] = mapped_column(String(256))
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    form_type: Mapped[str | None] = mapped_column(String(64))
    accession_number: Mapped[str | None] = mapped_column(String(64))
    announcement_id: Mapped[str | None] = mapped_column(String(256))
    period_end: Mapped[date | None] = mapped_column(Date)
    filed_at: Mapped[datetime | None] = mapped_column()
    published_at: Mapped[datetime | None] = mapped_column()
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    primary_document_name: Mapped[str | None] = mapped_column(String(256))
    mime_type: Mapped[str | None] = mapped_column(String(128))
    storage_uri: Mapped[str | None] = mapped_column(String(2048))
    checksum: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    document_status: Mapped[str] = mapped_column(String(32), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(nullable=False)


class ProviderFinancialFact(_ImmutableUuidMixin, Base):
    __tablename__ = "provider_financial_facts"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_provider_financial_facts"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_provider_financial_facts_security_id_securities",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_provider_financial_facts_provider_id_data_providers",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_payload_id"],
            ["raw_payloads.id"],
            name="fk_provider_financial_facts_payload_id_raw_payloads",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["document_id"],
            ["source_documents.id"],
            name="fk_provider_financial_facts_document_id_source_documents",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "statement_type IN ('BALANCE_SHEET', 'INCOME_STATEMENT', 'CASH_FLOW', "
            "'EQUITY', 'COMPREHENSIVE_INCOME', 'OTHER')",
            name="ck_provider_financial_facts_statement_type",
        ),
        CheckConstraint(
            "length(provider_concept) BETWEEN 1 AND 512",
            name="ck_provider_financial_facts_concept_length",
        ),
        CheckConstraint(
            "jsonb_typeof(dimensions) = 'object'",
            name="ck_provider_financial_facts_dimensions_object",
        ),
        CheckConstraint(
            "value IS NULL OR value != 'NaN'::numeric",
            name="ck_provider_financial_facts_value_finite",
        ),
        CheckConstraint(
            "fiscal_year IS NULL OR fiscal_year BETWEEN 1900 AND 9999",
            name="ck_provider_financial_facts_fiscal_year",
        ),
        CheckConstraint(
            "fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4",
            name="ck_provider_financial_facts_fiscal_quarter",
        ),
        CheckConstraint(
            "period_end IS NULL OR period_start IS NULL OR period_end >= period_start",
            name="ck_provider_financial_facts_period_order",
        ),
        Index("ix_provider_financial_facts_security_period_end", "security_id", "period_end"),
        Index("ix_provider_financial_facts_security_filed_at", "security_id", "filed_at"),
    )

    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_payload_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_id: Mapped[UUID | None] = mapped_column(Uuid)
    statement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_concept: Mapped[str] = mapped_column(String(512), nullable=False)
    reported_label: Mapped[str | None] = mapped_column(String(512))
    taxonomy: Mapped[str | None] = mapped_column(String(256))
    context_id: Mapped[str | None] = mapped_column(String(256))
    dimensions: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    unit: Mapped[str | None] = mapped_column(String(64))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer)
    fiscal_period: Mapped[str | None] = mapped_column(String(32))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    instant_date: Mapped[date | None] = mapped_column(Date)
    filed_at: Mapped[datetime | None] = mapped_column()
    source_published_at: Mapped[datetime | None] = mapped_column()
    form_type: Mapped[str | None] = mapped_column(String(64))
    is_annual: Mapped[bool | None] = mapped_column(Boolean)
    is_cumulative: Mapped[bool | None] = mapped_column(Boolean)
    is_audited: Mapped[bool | None] = mapped_column(Boolean)
    is_restated: Mapped[bool | None] = mapped_column(Boolean)
    provider_record_id: Mapped[str | None] = mapped_column(String(256))
    retrieved_at: Mapped[datetime] = mapped_column(nullable=False)


class DataSnapshot(_ImmutableUuidMixin, Base):
    __tablename__ = "data_snapshots"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_data_snapshots"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_data_snapshots_security_id_securities",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "security_id",
            "research_as_of_time",
            "snapshot_version",
            name="uq_data_snapshots_security_as_of_version",
        ),
        CheckConstraint("snapshot_version > 0", name="ck_data_snapshots_version_positive"),
        CheckConstraint(
            "status IN ('BUILDING', 'COMPLETE', 'PARTIAL', 'FAILED', 'SUPERSEDED')",
            name="ck_data_snapshots_status",
        ),
        CheckConstraint(
            "(status = 'BUILDING' AND completed_at IS NULL AND checksum IS NULL) OR "
            "(status IN ('COMPLETE', 'PARTIAL', 'SUPERSEDED') AND completed_at IS NOT NULL "
            "AND checksum IS NOT NULL) OR "
            "(status = 'FAILED' AND completed_at IS NOT NULL AND checksum IS NULL)",
            name="ck_data_snapshots_completion_shape",
        ),
        CheckConstraint(
            "checksum IS NULL OR checksum ~ '^[0-9a-f]{64}$'",
            name="ck_data_snapshots_checksum_format",
        ),
        CheckConstraint(
            "formula_version = 'raw-data-v1'", name="ck_data_snapshots_formula_version"
        ),
        CheckConstraint(
            "notes IS NULL OR length(notes) BETWEEN 1 AND 1024",
            name="ck_data_snapshots_notes_length",
        ),
        Index("ix_data_snapshots_security_as_of", "security_id", "research_as_of_time"),
    )

    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_as_of_time: Mapped[datetime] = mapped_column(nullable=False)
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column()
    checksum: Mapped[str | None] = mapped_column(String(64))
    formula_version: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1024))


class SnapshotItem(_ImmutableUuidMixin, Base):
    __tablename__ = "snapshot_items"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_snapshot_items"),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_snapshot_items_snapshot_id_data_snapshots",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_snapshot_items_provider_id_data_providers",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "snapshot_id",
            "source_record_type",
            "source_record_id",
            name="uq_snapshot_items_source_record",
        ),
        CheckConstraint(f"category IN ({_CATEGORY_SQL})", name="ck_snapshot_items_category"),
        CheckConstraint(
            "source_record_type IN ('daily_price_bars', 'corporate_actions', "
            "'provider_financial_facts', 'source_documents')",
            name="ck_snapshot_items_source_record_type",
        ),
        CheckConstraint(
            "length(checksum_input) BETWEEN 1 AND 4096",
            name="ck_snapshot_items_checksum_input_length",
        ),
        CheckConstraint("checksum ~ '^[0-9a-f]{64}$'", name="ck_snapshot_items_checksum_format"),
        Index("ix_snapshot_items_snapshot_category", "snapshot_id", "category"),
    )

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    source_record_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_record_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column()
    retrieved_at: Mapped[datetime] = mapped_column(nullable=False)
    checksum_input: Mapped[str] = mapped_column(String(4096), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)


__all__ = [
    "CorporateAction",
    "DailyPriceBar",
    "DataProvider",
    "DataSnapshot",
    "IngestionRun",
    "ProviderFinancialFact",
    "ProviderInstrumentMapping",
    "ProviderRequestLog",
    "RawPayload",
    "SnapshotItem",
    "SourceDocument",
]
