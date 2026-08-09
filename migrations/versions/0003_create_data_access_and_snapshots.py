"""Create provider data-access lineage and point-in-time snapshot tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_data_access_snapshots"
down_revision: str | Sequence[str] | None = "0002_create_security_master"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATEGORIES = (
    "'DAILY_PRICES', 'CORPORATE_ACTIONS', 'FINANCIAL_FACTS', 'FILING_METADATA', 'SOURCE_DOCUMENTS'"
)


def _immutable_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


def _timestamped_columns() -> list[sa.Column[object]]:
    return [
        *_immutable_columns(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


def _provider_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["provider_id"],
        ["data_providers.id"],
        name=f"fk_{table}_provider_id_data_providers",
        ondelete="RESTRICT",
    )


def _security_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["security_id"],
        ["securities.id"],
        name=f"fk_{table}_security_id_securities",
        ondelete="RESTRICT",
    )


def _payload_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["source_payload_id"],
        ["raw_payloads.id"],
        name=f"fk_{table}_payload_id_raw_payloads",
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.create_table(
        "data_providers",
        *_timestamped_columns(),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=True),
        sa.Column("documentation_url", sa.String(length=2048), nullable=True),
        sa.Column("terms_status", sa.String(length=32), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_data_providers"),
        sa.UniqueConstraint("code", name="uq_data_providers_code"),
        sa.CheckConstraint("code ~ '^[A-Z][A-Z0-9_]{0,63}$'", name="ck_data_providers_code_format"),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 128", name="ck_data_providers_name_length"),
        sa.CheckConstraint(
            "provider_type IN ('FIXTURE', 'MARKET_DATA', 'FINANCIAL_DATA', "
            "'FILINGS', 'MULTI_SOURCE')",
            name="ck_data_providers_provider_type",
        ),
        sa.CheckConstraint(
            "status IN ('APPROVED', 'APPROVED_FOR_PERSONAL_RESEARCH_ONLY', "
            "'NEEDS_CREDENTIALS', 'NEEDS_LICENSE_CONFIRMATION', 'EXPERIMENTAL', "
            "'NOT_ALLOWED')",
            name="ck_data_providers_status",
        ),
        sa.CheckConstraint(
            "terms_status IN ('VERIFIED', 'RESTRICTED', 'NEEDS_REVIEW', 'UNKNOWN')",
            name="ck_data_providers_terms_status",
        ),
        sa.CheckConstraint(
            "base_url IS NULL OR length(base_url) BETWEEN 1 AND 2048",
            name="ck_data_providers_base_url_length",
        ),
        sa.CheckConstraint(
            "documentation_url IS NULL OR length(documentation_url) BETWEEN 1 AND 2048",
            name="ck_data_providers_documentation_url_length",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(capabilities) = 'array'",
            name="ck_data_providers_capabilities_array",
        ),
    )

    op.create_table(
        "provider_instrument_mappings",
        *_timestamped_columns(),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("security_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_symbol", sa.String(length=128), nullable=False),
        sa.Column("provider_exchange_code", sa.String(length=64), nullable=True),
        sa.Column("provider_instrument_id", sa.String(length=256), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_name", sa.String(length=256), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_provider_instrument_mappings"),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_provider_mappings_provider_id_data_providers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_provider_mappings_security_id_securities",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "provider_id",
            "security_id",
            "provider_symbol",
            "valid_from",
            name="uq_provider_mappings_identity",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(
            "length(provider_symbol) BETWEEN 1 AND 128",
            name="ck_provider_mappings_symbol_length",
        ),
        sa.CheckConstraint(
            "provider_exchange_code IS NULL OR length(provider_exchange_code) BETWEEN 1 AND 64",
            name="ck_provider_mappings_exchange_code_length",
        ),
        sa.CheckConstraint(
            "provider_instrument_id IS NULL OR length(provider_instrument_id) BETWEEN 1 AND 256",
            name="ck_provider_mappings_instrument_id_length",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_provider_mappings_validity",
        ),
        sa.CheckConstraint(
            "length(source_name) BETWEEN 1 AND 256",
            name="ck_provider_mappings_source_name_length",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'", name="ck_provider_mappings_metadata_object"
        ),
    )
    op.create_index(
        "ix_provider_mappings_security_provider_active",
        "provider_instrument_mappings",
        ["security_id", "provider_id"],
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "uq_provider_mappings_active_symbol",
        "provider_instrument_mappings",
        ["provider_id", "provider_symbol"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "uq_provider_mappings_active_instrument_id",
        "provider_instrument_mappings",
        ["provider_id", "provider_instrument_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND provider_instrument_id IS NOT NULL"),
    )

    op.create_table(
        "ingestion_runs",
        *_timestamped_columns(),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("security_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("research_as_of_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("records_received", sa.Integer(), nullable=False),
        sa.Column("records_stored", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("safe_error_message", sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_runs"),
        _provider_fk("ingestion_runs"),
        _security_fk("ingestion_runs"),
        sa.UniqueConstraint("idempotency_key", name="uq_ingestion_runs_idempotency_key"),
        sa.CheckConstraint(f"category IN ({_CATEGORIES})", name="ck_ingestion_runs_category"),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'PASS', 'PARTIAL', 'BLOCKED', 'FAIL', 'CANCELLED')",
            name="ck_ingestion_runs_status",
        ),
        sa.CheckConstraint(
            "idempotency_key ~ '^[a-z0-9][a-z0-9:_-]{0,127}$'",
            name="ck_ingestion_runs_idempotency_key_format",
        ),
        sa.CheckConstraint(
            "started_at IS NULL OR started_at >= requested_at",
            name="ck_ingestion_runs_started_order",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= COALESCE(started_at, requested_at)",
            name="ck_ingestion_runs_completed_order",
        ),
        sa.CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('PASS', 'PARTIAL', 'BLOCKED', 'FAIL', 'CANCELLED') "
            "AND completed_at IS NOT NULL)",
            name="ck_ingestion_runs_status_timestamps",
        ),
        sa.CheckConstraint(
            "request_count >= 0 AND records_received >= 0 AND records_stored >= 0 "
            "AND warning_count >= 0",
            name="ck_ingestion_runs_nonnegative_counts",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR length(error_code) BETWEEN 1 AND 64",
            name="ck_ingestion_runs_error_code_length",
        ),
        sa.CheckConstraint(
            "safe_error_message IS NULL OR length(safe_error_message) BETWEEN 1 AND 512",
            name="ck_ingestion_runs_safe_error_length",
        ),
    )
    op.create_index(
        "ix_ingestion_runs_security_category_as_of",
        "ingestion_runs",
        ["security_id", "category", "research_as_of_time"],
    )

    op.create_table(
        "provider_request_logs",
        *_immutable_columns(),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("caller_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_request_id", sa.String(length=256), nullable=True),
        sa.Column("endpoint_name", sa.String(length=128), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("safe_url", sa.String(length=2048), nullable=False),
        sa.Column("request_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("cache_status", sa.String(length=32), nullable=False),
        sa.Column("etag", sa.String(length=512), nullable=True),
        sa.Column("last_modified", sa.String(length=128), nullable=True),
        sa.Column("response_size", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_provider_request_logs"),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name="fk_provider_request_logs_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        _provider_fk("provider_request_logs"),
        sa.CheckConstraint(
            "provider_request_id IS NULL OR "
            "provider_request_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$'",
            name="ck_provider_request_logs_provider_request_id_format",
        ),
        sa.CheckConstraint(
            "length(endpoint_name) BETWEEN 1 AND 128",
            name="ck_provider_request_logs_endpoint_length",
        ),
        sa.CheckConstraint("method IN ('GET', 'HEAD')", name="ck_provider_request_logs_method"),
        sa.CheckConstraint(
            "length(safe_url) BETWEEN 1 AND 2048",
            name="ck_provider_request_logs_safe_url_length",
        ),
        sa.CheckConstraint(
            "response_received_at IS NULL OR response_received_at >= request_started_at",
            name="ck_provider_request_logs_response_order",
        ),
        sa.CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599",
            name="ck_provider_request_logs_http_status",
        ),
        sa.CheckConstraint("attempt > 0", name="ck_provider_request_logs_attempt_positive"),
        sa.CheckConstraint(
            "cache_status IN ('MISS', 'HIT', 'REVALIDATED', 'BYPASS', 'NOT_APPLICABLE')",
            name="ck_provider_request_logs_cache_status",
        ),
        sa.CheckConstraint(
            "etag IS NULL OR length(etag) BETWEEN 1 AND 512",
            name="ck_provider_request_logs_etag_length",
        ),
        sa.CheckConstraint(
            "last_modified IS NULL OR length(last_modified) BETWEEN 1 AND 128",
            name="ck_provider_request_logs_last_modified_length",
        ),
        sa.CheckConstraint(
            "response_size IS NULL OR response_size >= 0",
            name="ck_provider_request_logs_response_size",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR length(error_code) BETWEEN 1 AND 64",
            name="ck_provider_request_logs_error_code_length",
        ),
    )
    op.create_index(
        "ix_provider_request_logs_ingestion_run",
        "provider_request_logs",
        ["ingestion_run_id", "created_at"],
    )

    op.create_table(
        "raw_payloads",
        *_immutable_columns(),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_request_log_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("security_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("storage_uri", sa.String(length=2048), nullable=True),
        sa.Column("inline_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("checksum_algorithm", sa.String(length=16), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_version", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_raw_payloads"),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name="fk_raw_payloads_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provider_request_log_id"],
            ["provider_request_logs.id"],
            name="fk_raw_payloads_request_id_provider_request_logs",
            ondelete="RESTRICT",
        ),
        _provider_fk("raw_payloads"),
        _security_fk("raw_payloads"),
        sa.CheckConstraint(f"category IN ({_CATEGORIES})", name="ck_raw_payloads_category"),
        sa.CheckConstraint(
            "length(content_type) BETWEEN 1 AND 128", name="ck_raw_payloads_content_type_length"
        ),
        sa.CheckConstraint(
            "(storage_uri IS NOT NULL AND inline_json IS NULL) OR "
            "(storage_uri IS NULL AND inline_json IS NOT NULL)",
            name="ck_raw_payloads_storage_shape",
        ),
        sa.CheckConstraint(
            "storage_uri IS NULL OR length(storage_uri) BETWEEN 10 AND 1024",
            name="ck_raw_payloads_storage_uri_length",
        ),
        sa.CheckConstraint(
            "storage_uri IS NULL OR storage_uri ~ "
            "'^blob://[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*"
            "(/[A-Za-z0-9][A-Za-z0-9._-]*)*$'",
            name="ck_raw_payloads_storage_uri_format",
        ),
        sa.CheckConstraint(
            "checksum_algorithm = 'sha256'", name="ck_raw_payloads_checksum_algorithm"
        ),
        sa.CheckConstraint("checksum ~ '^[0-9a-f]{64}$'", name="ck_raw_payloads_checksum_format"),
        sa.CheckConstraint(
            "length(provider_version) BETWEEN 1 AND 64 AND "
            "length(parser_version) BETWEEN 1 AND 64 AND "
            "length(schema_version) BETWEEN 1 AND 64",
            name="ck_raw_payloads_versions_length",
        ),
        sa.CheckConstraint("byte_size >= 0", name="ck_raw_payloads_byte_size"),
    )
    op.create_index("ix_raw_payloads_checksum", "raw_payloads", ["checksum"])
    op.create_index(
        "ix_raw_payloads_security_category_source_time",
        "raw_payloads",
        ["security_id", "category", "source_published_at"],
    )

    _create_daily_price_bars()
    _create_corporate_actions()
    _create_provider_financial_facts()
    _create_source_documents()
    op.create_foreign_key(
        "fk_provider_financial_facts_document_id_source_documents",
        "provider_financial_facts",
        "source_documents",
        ["document_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    _create_snapshots()


def _create_daily_price_bars() -> None:
    op.create_table(
        "daily_price_bars",
        *_immutable_columns(),
        sa.Column("security_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_payload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_symbol", sa.String(length=128), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("market_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("high", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("low", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("close", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("adjustment_type", sa.String(length=32), nullable=True),
        sa.Column("provider_adjusted_close", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_daily_price_bars"),
        _security_fk("daily_price_bars"),
        _provider_fk("daily_price_bars"),
        _payload_fk("daily_price_bars"),
        sa.UniqueConstraint(
            "provider_id",
            "provider_symbol",
            "trading_date",
            "adjustment_type",
            "source_payload_id",
            name="uq_daily_price_bars_provider_revision",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(
            "length(provider_symbol) BETWEEN 1 AND 128",
            name="ck_daily_price_bars_provider_symbol_length",
        ),
        sa.CheckConstraint(
            "open IS NULL OR (open != 'NaN'::numeric AND open >= 0)",
            name="ck_daily_price_bars_open_nonnegative",
        ),
        sa.CheckConstraint(
            "high IS NULL OR (high != 'NaN'::numeric AND high >= 0)",
            name="ck_daily_price_bars_high_nonnegative",
        ),
        sa.CheckConstraint(
            "low IS NULL OR (low != 'NaN'::numeric AND low >= 0)",
            name="ck_daily_price_bars_low_nonnegative",
        ),
        sa.CheckConstraint(
            "close IS NULL OR (close != 'NaN'::numeric AND close >= 0)",
            name="ck_daily_price_bars_close_nonnegative",
        ),
        sa.CheckConstraint("volume IS NULL OR volume >= 0", name="ck_daily_price_bars_volume"),
        sa.CheckConstraint(
            "provider_adjusted_close IS NULL OR "
            "(provider_adjusted_close != 'NaN'::numeric AND provider_adjusted_close >= 0)",
            name="ck_daily_price_bars_adjusted_close_nonnegative",
        ),
        sa.CheckConstraint(
            "high IS NULL OR low IS NULL OR high >= low", name="ck_daily_price_bars_high_low"
        ),
        sa.CheckConstraint(
            "currency_code ~ '^[A-Z]{3}$'", name="ck_daily_price_bars_currency_code"
        ),
        sa.CheckConstraint(
            "adjustment_type IN ('UNADJUSTED', 'PROVIDER_ADJUSTED')",
            name="ck_daily_price_bars_adjustment_type",
        ),
    )
    op.create_index(
        "ix_daily_price_bars_security_date", "daily_price_bars", ["security_id", "trading_date"]
    )
    op.create_index(
        "ix_daily_price_bars_provider_symbol_date",
        "daily_price_bars",
        ["provider_id", "provider_symbol", "trading_date"],
    )


def _create_corporate_actions() -> None:
    op.create_table(
        "corporate_actions",
        *_immutable_columns(),
        sa.Column("security_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_payload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_action_id", sa.String(length=256), nullable=True),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("announcement_date", sa.Date(), nullable=True),
        sa.Column("ex_date", sa.Date(), nullable=True),
        sa.Column("record_date", sa.Date(), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("cash_amount", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("ratio_numerator", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("ratio_denominator", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_corporate_actions"),
        _security_fk("corporate_actions"),
        _provider_fk("corporate_actions"),
        _payload_fk("corporate_actions"),
        sa.CheckConstraint(
            "provider_action_id IS NULL OR length(provider_action_id) BETWEEN 1 AND 256",
            name="ck_corporate_actions_provider_action_id_length",
        ),
        sa.CheckConstraint(
            "action_type IN ('CASH_DIVIDEND', 'STOCK_SPLIT', 'REVERSE_SPLIT', "
            "'STOCK_DIVIDEND', 'RIGHTS_ISSUE', 'SYMBOL_CHANGE', 'OTHER')",
            name="ck_corporate_actions_action_type",
        ),
        sa.CheckConstraint(
            "cash_amount IS NULL OR (cash_amount != 'NaN'::numeric AND cash_amount >= 0)",
            name="ck_corporate_actions_cash_amount",
        ),
        sa.CheckConstraint(
            "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'",
            name="ck_corporate_actions_currency_code",
        ),
        sa.CheckConstraint(
            "ratio_numerator IS NULL OR "
            "(ratio_numerator != 'NaN'::numeric AND ratio_numerator > 0)",
            name="ck_corporate_actions_ratio_numerator",
        ),
        sa.CheckConstraint(
            "ratio_denominator IS NULL OR "
            "(ratio_denominator != 'NaN'::numeric AND ratio_denominator > 0)",
            name="ck_corporate_actions_ratio_denominator",
        ),
        sa.CheckConstraint(
            "status IN ('ANNOUNCED', 'CONFIRMED', 'CANCELLED', 'UNKNOWN')",
            name="ck_corporate_actions_status",
        ),
    )
    op.create_index(
        "ix_corporate_actions_security_ex_date", "corporate_actions", ["security_id", "ex_date"]
    )
    op.create_index(
        "uq_corporate_actions_provider_action_payload",
        "corporate_actions",
        ["provider_id", "provider_action_id", "source_payload_id"],
        unique=True,
        postgresql_where=sa.text("provider_action_id IS NOT NULL"),
    )
    op.create_index(
        "uq_corporate_actions_anonymous_natural_key",
        "corporate_actions",
        [
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
        ],
        unique=True,
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("provider_action_id IS NULL"),
    )


def _create_provider_financial_facts() -> None:
    op.create_table(
        "provider_financial_facts",
        *_immutable_columns(),
        sa.Column("security_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_payload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("statement_type", sa.String(length=32), nullable=False),
        sa.Column("provider_concept", sa.String(length=512), nullable=False),
        sa.Column("reported_label", sa.String(length=512), nullable=True),
        sa.Column("taxonomy", sa.String(length=256), nullable=True),
        sa.Column("context_id", sa.String(length=256), nullable=True),
        sa.Column("dimensions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_quarter", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(length=32), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("instant_date", sa.Date(), nullable=True),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("form_type", sa.String(length=64), nullable=True),
        sa.Column("is_annual", sa.Boolean(), nullable=True),
        sa.Column("is_cumulative", sa.Boolean(), nullable=True),
        sa.Column("is_audited", sa.Boolean(), nullable=True),
        sa.Column("is_restated", sa.Boolean(), nullable=True),
        sa.Column("provider_record_id", sa.String(length=256), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_provider_financial_facts"),
        _security_fk("provider_financial_facts"),
        _provider_fk("provider_financial_facts"),
        _payload_fk("provider_financial_facts"),
        sa.CheckConstraint(
            "statement_type IN ('BALANCE_SHEET', 'INCOME_STATEMENT', 'CASH_FLOW', "
            "'EQUITY', 'COMPREHENSIVE_INCOME', 'OTHER')",
            name="ck_provider_financial_facts_statement_type",
        ),
        sa.CheckConstraint(
            "length(provider_concept) BETWEEN 1 AND 512",
            name="ck_provider_financial_facts_concept_length",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(dimensions) = 'object'",
            name="ck_provider_financial_facts_dimensions_object",
        ),
        sa.CheckConstraint(
            "value IS NULL OR value != 'NaN'::numeric",
            name="ck_provider_financial_facts_value_finite",
        ),
        sa.CheckConstraint(
            "fiscal_year IS NULL OR fiscal_year BETWEEN 1900 AND 9999",
            name="ck_provider_financial_facts_fiscal_year",
        ),
        sa.CheckConstraint(
            "fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4",
            name="ck_provider_financial_facts_fiscal_quarter",
        ),
        sa.CheckConstraint(
            "period_end IS NULL OR period_start IS NULL OR period_end >= period_start",
            name="ck_provider_financial_facts_period_order",
        ),
    )
    op.create_index(
        "ix_provider_financial_facts_security_period_end",
        "provider_financial_facts",
        ["security_id", "period_end"],
    )
    op.create_index(
        "ix_provider_financial_facts_security_filed_at",
        "provider_financial_facts",
        ["security_id", "filed_at"],
    )


def _create_source_documents() -> None:
    op.create_table(
        "source_documents",
        *_timestamped_columns(),
        sa.Column("security_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_payload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_document_id", sa.String(length=256), nullable=True),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("form_type", sa.String(length=64), nullable=True),
        sa.Column("accession_number", sa.String(length=64), nullable=True),
        sa.Column("announcement_id", sa.String(length=256), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("primary_document_name", sa.String(length=256), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("storage_uri", sa.String(length=2048), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("document_status", sa.String(length=32), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_source_documents"),
        _security_fk("source_documents"),
        _provider_fk("source_documents"),
        _payload_fk("source_documents"),
        sa.UniqueConstraint(
            "provider_id",
            "provider_document_id",
            "source_payload_id",
            name="uq_source_documents_provider_document_payload",
        ),
        sa.UniqueConstraint(
            "provider_id",
            "accession_number",
            "source_payload_id",
            name="uq_source_documents_provider_accession_payload",
        ),
        sa.CheckConstraint(
            "provider_document_id IS NULL OR length(provider_document_id) BETWEEN 1 AND 256",
            name="ck_source_documents_provider_document_id_length",
        ),
        sa.CheckConstraint(
            "document_type IN ('ANNUAL_REPORT', 'QUARTERLY_REPORT', 'INTERIM_REPORT', "
            "'EARNINGS_RELEASE', 'MATERIAL_ANNOUNCEMENT', 'SEC_10_K', 'SEC_10_Q', "
            "'SEC_8_K', 'INVESTOR_PRESENTATION', 'OTHER')",
            name="ck_source_documents_document_type",
        ),
        sa.CheckConstraint("length(title) BETWEEN 1 AND 512", name="ck_source_documents_title"),
        sa.CheckConstraint(
            "length(source_url) BETWEEN 1 AND 2048", name="ck_source_documents_source_url"
        ),
        sa.CheckConstraint(
            "storage_uri IS NULL OR length(storage_uri) BETWEEN 10 AND 1024",
            name="ck_source_documents_storage_uri_length",
        ),
        sa.CheckConstraint(
            "storage_uri IS NULL OR storage_uri ~ "
            "'^blob://[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*"
            "(/[A-Za-z0-9][A-Za-z0-9._-]*)*$'",
            name="ck_source_documents_storage_uri_format",
        ),
        sa.CheckConstraint(
            "checksum IS NULL OR checksum ~ '^[0-9a-f]{64}$'",
            name="ck_source_documents_checksum_format",
        ),
        sa.CheckConstraint(
            "byte_size IS NULL OR byte_size >= 0", name="ck_source_documents_byte_size"
        ),
        sa.CheckConstraint(
            "document_status IN ('METADATA_ONLY', 'AVAILABLE', 'DOWNLOAD_FAILED', "
            "'UNAVAILABLE', 'UNKNOWN')",
            name="ck_source_documents_status",
        ),
    )
    op.create_index(
        "ix_source_documents_security_published_at",
        "source_documents",
        ["security_id", "published_at"],
    )
    op.create_index(
        "ix_source_documents_accession_number", "source_documents", ["accession_number"]
    )
    op.create_index(
        "ix_source_documents_provider_document_id",
        "source_documents",
        ["provider_id", "provider_document_id"],
    )


def _create_snapshots() -> None:
    op.create_table(
        "data_snapshots",
        *_immutable_columns(),
        sa.Column("security_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_as_of_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("formula_version", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.String(length=1024), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_data_snapshots"),
        _security_fk("data_snapshots"),
        sa.UniqueConstraint(
            "security_id",
            "research_as_of_time",
            "snapshot_version",
            name="uq_data_snapshots_security_as_of_version",
        ),
        sa.CheckConstraint("snapshot_version > 0", name="ck_data_snapshots_version_positive"),
        sa.CheckConstraint(
            "status IN ('BUILDING', 'COMPLETE', 'PARTIAL', 'FAILED', 'SUPERSEDED')",
            name="ck_data_snapshots_status",
        ),
        sa.CheckConstraint(
            "(status = 'BUILDING' AND completed_at IS NULL AND checksum IS NULL) OR "
            "(status IN ('COMPLETE', 'PARTIAL', 'SUPERSEDED') AND completed_at IS NOT NULL "
            "AND checksum IS NOT NULL) OR "
            "(status = 'FAILED' AND completed_at IS NOT NULL AND checksum IS NULL)",
            name="ck_data_snapshots_completion_shape",
        ),
        sa.CheckConstraint(
            "checksum IS NULL OR checksum ~ '^[0-9a-f]{64}$'",
            name="ck_data_snapshots_checksum_format",
        ),
        sa.CheckConstraint(
            "formula_version = 'raw-data-v1'", name="ck_data_snapshots_formula_version"
        ),
        sa.CheckConstraint(
            "notes IS NULL OR length(notes) BETWEEN 1 AND 1024",
            name="ck_data_snapshots_notes_length",
        ),
    )
    op.create_index(
        "ix_data_snapshots_security_as_of",
        "data_snapshots",
        ["security_id", "research_as_of_time"],
    )

    op.create_table(
        "snapshot_items",
        *_immutable_columns(),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("source_record_type", sa.String(length=64), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checksum_input", sa.String(length=4096), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_snapshot_items"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_snapshot_items_snapshot_id_data_snapshots",
            ondelete="RESTRICT",
        ),
        _provider_fk("snapshot_items"),
        sa.UniqueConstraint(
            "snapshot_id",
            "source_record_type",
            "source_record_id",
            name="uq_snapshot_items_source_record",
        ),
        sa.CheckConstraint(f"category IN ({_CATEGORIES})", name="ck_snapshot_items_category"),
        sa.CheckConstraint(
            "source_record_type IN ('daily_price_bars', 'corporate_actions', "
            "'provider_financial_facts', 'source_documents')",
            name="ck_snapshot_items_source_record_type",
        ),
        sa.CheckConstraint(
            "length(checksum_input) BETWEEN 1 AND 4096",
            name="ck_snapshot_items_checksum_input_length",
        ),
        sa.CheckConstraint("checksum ~ '^[0-9a-f]{64}$'", name="ck_snapshot_items_checksum_format"),
    )
    op.create_index(
        "ix_snapshot_items_snapshot_category", "snapshot_items", ["snapshot_id", "category"]
    )
    _create_snapshot_guards()


def _create_snapshot_guards() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_data_snapshot_immutability()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            item_count integer;
            unknown_publication_count integer;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'BUILDING' THEN
                    RAISE EXCEPTION 'snapshot must start in building state'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;
            IF TG_OP = 'DELETE' THEN
                IF OLD.status <> 'BUILDING' THEN
                    RAISE EXCEPTION 'terminal snapshot is immutable' USING ERRCODE = '23514';
                END IF;
                RETURN OLD;
            END IF;

            IF OLD.status <> 'BUILDING' THEN
                RAISE EXCEPTION 'terminal snapshot is immutable' USING ERRCODE = '23514';
            END IF;
            IF NEW.security_id <> OLD.security_id
               OR NEW.research_as_of_time <> OLD.research_as_of_time
               OR NEW.snapshot_version <> OLD.snapshot_version
               OR NEW.formula_version <> OLD.formula_version THEN
                RAISE EXCEPTION 'snapshot identity is immutable' USING ERRCODE = '23514';
            END IF;
            IF NEW.status = 'BUILDING' THEN
                RETURN NEW;
            END IF;

            SELECT count(*), count(*) FILTER (WHERE source_published_at IS NULL)
              INTO item_count, unknown_publication_count
              FROM snapshot_items
             WHERE snapshot_id = OLD.id;

            IF NEW.status = 'FAILED' AND item_count <> 0 THEN
                RAISE EXCEPTION 'failed snapshot cannot retain items' USING ERRCODE = '23514';
            END IF;
            IF NEW.status = 'COMPLETE'
               AND (item_count = 0 OR unknown_publication_count <> 0) THEN
                RAISE EXCEPTION 'complete snapshot evidence is incomplete'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_snapshot_item_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            parent_status text;
            parent_cutoff timestamptz;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                SELECT status, research_as_of_time
                  INTO parent_status, parent_cutoff
                  FROM data_snapshots
                 WHERE id = OLD.snapshot_id
                   FOR UPDATE;
                IF parent_status IS NULL OR parent_status <> 'BUILDING' THEN
                    RAISE EXCEPTION 'terminal snapshot items are immutable'
                        USING ERRCODE = '23514';
                END IF;
                RETURN OLD;
            END IF;

            IF TG_OP = 'UPDATE' THEN
                SELECT status, research_as_of_time
                  INTO parent_status, parent_cutoff
                  FROM data_snapshots
                 WHERE id = OLD.snapshot_id
                   FOR UPDATE;
                IF parent_status IS NULL OR parent_status <> 'BUILDING' THEN
                    RAISE EXCEPTION 'terminal snapshot items are immutable'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            SELECT status, research_as_of_time
              INTO parent_status, parent_cutoff
              FROM data_snapshots
             WHERE id = NEW.snapshot_id
               FOR UPDATE;
            IF parent_status IS NULL OR parent_status <> 'BUILDING' THEN
                RAISE EXCEPTION 'snapshot items require a building parent'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.retrieved_at > parent_cutoff THEN
                RAISE EXCEPTION 'snapshot item retrieval exceeds cutoff'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.source_published_at IS NOT NULL
               AND NEW.source_published_at > parent_cutoff THEN
                RAISE EXCEPTION 'snapshot item publication exceeds cutoff'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_data_snapshots_immutable
        BEFORE INSERT OR UPDATE OR DELETE ON data_snapshots
        FOR EACH ROW EXECUTE FUNCTION enforce_data_snapshot_immutability()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_snapshot_items_guard
        BEFORE INSERT OR UPDATE OR DELETE ON snapshot_items
        FOR EACH ROW EXECUTE FUNCTION enforce_snapshot_item_guard()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_snapshot_items_guard ON snapshot_items")
    op.execute("DROP TRIGGER IF EXISTS trg_data_snapshots_immutable ON data_snapshots")
    op.execute("DROP FUNCTION IF EXISTS enforce_snapshot_item_guard()")
    op.execute("DROP FUNCTION IF EXISTS enforce_data_snapshot_immutability()")
    op.drop_index("ix_snapshot_items_snapshot_category", table_name="snapshot_items")
    op.drop_table("snapshot_items")
    op.drop_index("ix_data_snapshots_security_as_of", table_name="data_snapshots")
    op.drop_table("data_snapshots")
    op.drop_index(
        "ix_provider_financial_facts_security_filed_at", table_name="provider_financial_facts"
    )
    op.drop_index(
        "ix_provider_financial_facts_security_period_end", table_name="provider_financial_facts"
    )
    op.drop_table("provider_financial_facts")
    op.drop_index("ix_source_documents_provider_document_id", table_name="source_documents")
    op.drop_index("ix_source_documents_accession_number", table_name="source_documents")
    op.drop_index("ix_source_documents_security_published_at", table_name="source_documents")
    op.drop_table("source_documents")
    op.drop_index("uq_corporate_actions_anonymous_natural_key", table_name="corporate_actions")
    op.drop_index("uq_corporate_actions_provider_action_payload", table_name="corporate_actions")
    op.drop_index("ix_corporate_actions_security_ex_date", table_name="corporate_actions")
    op.drop_table("corporate_actions")
    op.drop_index("ix_daily_price_bars_provider_symbol_date", table_name="daily_price_bars")
    op.drop_index("ix_daily_price_bars_security_date", table_name="daily_price_bars")
    op.drop_table("daily_price_bars")
    op.drop_index("ix_raw_payloads_security_category_source_time", table_name="raw_payloads")
    op.drop_index("ix_raw_payloads_checksum", table_name="raw_payloads")
    op.drop_table("raw_payloads")
    op.drop_index("ix_provider_request_logs_ingestion_run", table_name="provider_request_logs")
    op.drop_table("provider_request_logs")
    op.drop_index("ix_ingestion_runs_security_category_as_of", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_index(
        "uq_provider_mappings_active_instrument_id",
        table_name="provider_instrument_mappings",
    )
    op.drop_index(
        "uq_provider_mappings_active_symbol",
        table_name="provider_instrument_mappings",
    )
    op.drop_index(
        "ix_provider_mappings_security_provider_active",
        table_name="provider_instrument_mappings",
    )
    op.drop_table("provider_instrument_mappings")
    op.drop_table("data_providers")
