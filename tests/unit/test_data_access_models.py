from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Float,
    ForeignKeyConstraint,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from stock_research_agent.db.base import Base
from stock_research_agent.db.models.data_access import (
    CorporateAction,
    DailyPriceBar,
    DataProvider,
    DataSnapshot,
    IngestionRun,
    ProviderFinancialFact,
    ProviderInstrumentMapping,
    ProviderRequestLog,
    RawPayload,
    SnapshotItem,
    SourceDocument,
)

STAGE_4_MODELS = (
    DataProvider,
    ProviderInstrumentMapping,
    IngestionRun,
    ProviderRequestLog,
    RawPayload,
    DailyPriceBar,
    CorporateAction,
    ProviderFinancialFact,
    SourceDocument,
    DataSnapshot,
    SnapshotItem,
)
STAGE_4_TABLES = {
    "data_providers",
    "provider_instrument_mappings",
    "ingestion_runs",
    "provider_request_logs",
    "raw_payloads",
    "daily_price_bars",
    "corporate_actions",
    "provider_financial_facts",
    "source_documents",
    "data_snapshots",
    "snapshot_items",
}


def test_all_stage_4_models_are_registered_with_exact_tables_and_primary_keys() -> None:
    assert {model.__tablename__ for model in STAGE_4_MODELS} == STAGE_4_TABLES
    assert STAGE_4_TABLES <= set(Base.metadata.tables)
    for table_name in STAGE_4_TABLES:
        table = Base.metadata.tables[table_name]
        assert table.primary_key.name == f"pk_{table_name}"
        assert tuple(column.name for column in table.primary_key.columns) == ("id",)


def test_columns_match_the_stage_4_persistence_contract() -> None:
    expected = {
        "data_providers": {
            "id",
            "code",
            "name",
            "provider_type",
            "status",
            "base_url",
            "documentation_url",
            "terms_status",
            "capabilities",
            "created_at",
            "updated_at",
        },
        "provider_instrument_mappings": {
            "id",
            "provider_id",
            "security_id",
            "provider_symbol",
            "provider_exchange_code",
            "provider_instrument_id",
            "valid_from",
            "valid_to",
            "is_primary",
            "metadata",
            "source_name",
            "created_at",
            "updated_at",
        },
        "ingestion_runs": {
            "id",
            "provider_id",
            "security_id",
            "category",
            "status",
            "research_as_of_time",
            "idempotency_key",
            "requested_at",
            "started_at",
            "completed_at",
            "request_count",
            "records_received",
            "records_stored",
            "warning_count",
            "error_code",
            "safe_error_message",
            "created_at",
            "updated_at",
        },
        "provider_request_logs": {
            "id",
            "ingestion_run_id",
            "provider_id",
            "caller_request_id",
            "provider_request_id",
            "endpoint_name",
            "method",
            "safe_url",
            "request_started_at",
            "response_received_at",
            "http_status",
            "attempt",
            "cache_status",
            "etag",
            "last_modified",
            "response_size",
            "error_code",
            "created_at",
        },
        "raw_payloads": {
            "id",
            "ingestion_run_id",
            "provider_request_log_id",
            "provider_id",
            "security_id",
            "category",
            "content_type",
            "storage_uri",
            "inline_json",
            "checksum_algorithm",
            "checksum",
            "source_published_at",
            "retrieved_at",
            "provider_version",
            "parser_version",
            "schema_version",
            "byte_size",
            "created_at",
        },
        "daily_price_bars": {
            "id",
            "security_id",
            "provider_id",
            "source_payload_id",
            "provider_symbol",
            "trading_date",
            "market_timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "currency_code",
            "adjustment_type",
            "provider_adjusted_close",
            "source_published_at",
            "retrieved_at",
            "created_at",
        },
        "corporate_actions": {
            "id",
            "security_id",
            "provider_id",
            "source_payload_id",
            "provider_action_id",
            "action_type",
            "announcement_date",
            "ex_date",
            "record_date",
            "payment_date",
            "cash_amount",
            "currency_code",
            "ratio_numerator",
            "ratio_denominator",
            "status",
            "source_published_at",
            "retrieved_at",
            "created_at",
        },
        "provider_financial_facts": {
            "id",
            "security_id",
            "provider_id",
            "source_payload_id",
            "document_id",
            "statement_type",
            "provider_concept",
            "reported_label",
            "taxonomy",
            "context_id",
            "dimensions",
            "value",
            "unit",
            "currency_code",
            "fiscal_year",
            "fiscal_quarter",
            "fiscal_period",
            "period_start",
            "period_end",
            "instant_date",
            "filed_at",
            "source_published_at",
            "form_type",
            "is_annual",
            "is_cumulative",
            "is_audited",
            "is_restated",
            "provider_record_id",
            "retrieved_at",
            "created_at",
        },
        "source_documents": {
            "id",
            "security_id",
            "provider_id",
            "source_payload_id",
            "provider_document_id",
            "document_type",
            "title",
            "form_type",
            "accession_number",
            "announcement_id",
            "period_end",
            "filed_at",
            "published_at",
            "source_url",
            "primary_document_name",
            "mime_type",
            "storage_uri",
            "checksum",
            "byte_size",
            "document_status",
            "retrieved_at",
            "created_at",
            "updated_at",
        },
        "data_snapshots": {
            "id",
            "security_id",
            "research_as_of_time",
            "snapshot_version",
            "status",
            "completed_at",
            "checksum",
            "formula_version",
            "notes",
            "created_at",
        },
        "snapshot_items": {
            "id",
            "snapshot_id",
            "provider_id",
            "category",
            "source_record_type",
            "source_record_id",
            "source_published_at",
            "retrieved_at",
            "checksum_input",
            "checksum",
            "created_at",
        },
    }
    for table_name, column_names in expected.items():
        assert set(Base.metadata.tables[table_name].columns.keys()) == column_names


def test_foreign_keys_are_named_targeted_and_restrict_deletion() -> None:
    expected_targets = {
        "provider_instrument_mappings": {"data_providers.id", "securities.id"},
        "ingestion_runs": {"data_providers.id", "securities.id"},
        "provider_request_logs": {"ingestion_runs.id", "data_providers.id"},
        "raw_payloads": {
            "ingestion_runs.id",
            "provider_request_logs.id",
            "data_providers.id",
            "securities.id",
        },
        "daily_price_bars": {"securities.id", "data_providers.id", "raw_payloads.id"},
        "corporate_actions": {"securities.id", "data_providers.id", "raw_payloads.id"},
        "provider_financial_facts": {
            "securities.id",
            "data_providers.id",
            "raw_payloads.id",
            "source_documents.id",
        },
        "source_documents": {"securities.id", "data_providers.id", "raw_payloads.id"},
        "data_snapshots": {"securities.id"},
        "snapshot_items": {"data_snapshots.id", "data_providers.id"},
    }
    for table_name, targets in expected_targets.items():
        table = Base.metadata.tables[table_name]
        assert {foreign_key.target_fullname for foreign_key in table.foreign_keys} == targets
        for constraint in table.constraints:
            if isinstance(constraint, ForeignKeyConstraint):
                assert constraint.name
                assert constraint.ondelete == "RESTRICT"


def test_named_unique_constraints_and_query_indexes_are_exact() -> None:
    expected_uniques = {
        "data_providers": {"uq_data_providers_code"},
        "provider_instrument_mappings": {"uq_provider_mappings_identity"},
        "ingestion_runs": {"uq_ingestion_runs_idempotency_key"},
        "daily_price_bars": {"uq_daily_price_bars_provider_revision"},
        "source_documents": {
            "uq_source_documents_provider_document_payload",
            "uq_source_documents_provider_accession_payload",
        },
        "data_snapshots": {"uq_data_snapshots_security_as_of_version"},
        "snapshot_items": {"uq_snapshot_items_source_record"},
    }
    expected_indexes = {
        "ix_provider_mappings_security_provider_active",
        "uq_provider_mappings_active_symbol",
        "uq_provider_mappings_active_instrument_id",
        "ix_ingestion_runs_security_category_as_of",
        "ix_provider_request_logs_ingestion_run",
        "ix_raw_payloads_checksum",
        "ix_raw_payloads_security_category_source_time",
        "ix_daily_price_bars_security_date",
        "ix_daily_price_bars_provider_symbol_date",
        "ix_corporate_actions_security_ex_date",
        "uq_corporate_actions_provider_action_payload",
        "uq_corporate_actions_anonymous_natural_key",
        "ix_provider_financial_facts_security_period_end",
        "ix_provider_financial_facts_security_filed_at",
        "ix_source_documents_security_published_at",
        "ix_source_documents_accession_number",
        "ix_source_documents_provider_document_id",
        "ix_data_snapshots_security_as_of",
        "ix_snapshot_items_snapshot_category",
    }
    actual_indexes: set[str] = set()
    for table_name in STAGE_4_TABLES:
        table = Base.metadata.tables[table_name]
        assert table.primary_key.name
        check_names = {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert check_names
        assert None not in check_names
        actual_unique_names = {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        if table_name in expected_uniques:
            assert actual_unique_names == expected_uniques[table_name]
        else:
            assert not actual_unique_names
        actual_indexes.update(index.name for index in table.indexes if index.name)
    assert expected_indexes <= actual_indexes


def test_storage_uri_and_exact_numeric_checks_cover_hostile_values() -> None:
    raw_checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in Base.metadata.tables["raw_payloads"].constraints
        if isinstance(constraint, CheckConstraint)
    }
    document_checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in Base.metadata.tables["source_documents"].constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "length(storage_uri) BETWEEN" in raw_checks["ck_raw_payloads_storage_uri_length"]
    assert "blob://" in raw_checks["ck_raw_payloads_storage_uri_format"]
    assert (
        "length(storage_uri) BETWEEN" in document_checks["ck_source_documents_storage_uri_length"]
    )

    expected_nan_checks = {
        "daily_price_bars": {
            "open",
            "high",
            "low",
            "close",
            "provider_adjusted_close",
        },
        "corporate_actions": {"cash_amount", "ratio_numerator", "ratio_denominator"},
        "provider_financial_facts": {"value"},
    }
    for table_name, column_names in expected_nan_checks.items():
        check_sql = " ".join(
            str(constraint.sqltext)
            for constraint in Base.metadata.tables[table_name].constraints
            if isinstance(constraint, CheckConstraint)
        )
        for column_name in column_names:
            assert f"{column_name} != 'NaN'::numeric" in check_sql


def test_partial_unique_indexes_encode_active_and_anonymous_identity() -> None:
    expected = {
        "uq_provider_mappings_active_symbol": {
            "columns": ("provider_id", "provider_symbol"),
            "predicate": "valid_to IS NULL",
            "nulls_not_distinct": False,
        },
        "uq_provider_mappings_active_instrument_id": {
            "columns": ("provider_id", "provider_instrument_id"),
            "predicate": "valid_to IS NULL AND provider_instrument_id IS NOT NULL",
            "nulls_not_distinct": False,
        },
        "uq_corporate_actions_provider_action_payload": {
            "columns": ("provider_id", "provider_action_id", "source_payload_id"),
            "predicate": "provider_action_id IS NOT NULL",
            "nulls_not_distinct": False,
        },
        "uq_corporate_actions_anonymous_natural_key": {
            "columns": (
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
            ),
            "predicate": "provider_action_id IS NULL",
            "nulls_not_distinct": True,
        },
    }
    indexes = {
        index.name: index
        for table_name in ("provider_instrument_mappings", "corporate_actions")
        for index in Base.metadata.tables[table_name].indexes
    }
    for name, contract in expected.items():
        index = indexes[name]
        assert index.unique is True
        assert tuple(column.name for column in index.columns) == contract["columns"]
        assert str(index.dialect_options["postgresql"]["where"]) == contract["predicate"]
        assert (
            bool(index.dialect_options["postgresql"]["nulls_not_distinct"])
            is contract["nulls_not_distinct"]
        )


def test_json_exact_numeric_timestamp_and_immutable_payload_types() -> None:
    for table_name, column_name in (
        ("data_providers", "capabilities"),
        ("provider_instrument_mappings", "metadata"),
        ("raw_payloads", "inline_json"),
        ("provider_financial_facts", "dimensions"),
    ):
        assert isinstance(Base.metadata.tables[table_name].c[column_name].type, JSONB)

    exact_numeric_columns = {
        "daily_price_bars": {
            "open",
            "high",
            "low",
            "close",
            "provider_adjusted_close",
        },
        "corporate_actions": {"cash_amount", "ratio_numerator", "ratio_denominator"},
        "provider_financial_facts": {"value"},
    }
    for table_name, column_names in exact_numeric_columns.items():
        for column_name in column_names:
            assert isinstance(Base.metadata.tables[table_name].c[column_name].type, Numeric)
    assert isinstance(Base.metadata.tables["daily_price_bars"].c.volume.type, BigInteger)
    assert Base.metadata.tables["daily_price_bars"].c.adjustment_type.nullable is True
    assert Base.metadata.tables["provider_request_logs"].c.caller_request_id.nullable is False
    assert Base.metadata.tables["provider_request_logs"].c.provider_request_id.nullable is True

    daily_unique = next(
        constraint
        for constraint in Base.metadata.tables["daily_price_bars"].constraints
        if constraint.name == "uq_daily_price_bars_provider_revision"
    )
    assert bool(daily_unique.dialect_options["postgresql"]["nulls_not_distinct"])

    for table_name in STAGE_4_TABLES:
        for column in Base.metadata.tables[table_name].columns:
            assert not isinstance(column.type, Float)
            assert not getattr(column.type, "native_enum", False)
    assert "updated_at" not in Base.metadata.tables["raw_payloads"].c
    assert "updated_at" not in Base.metadata.tables["data_snapshots"].c
    assert "updated_at" not in Base.metadata.tables["snapshot_items"].c


def test_forbidden_secret_normalized_and_executable_content_columns_are_absent() -> None:
    forbidden = {
        "api_key",
        "token",
        "secret",
        "authorization",
        "cookie",
        "headers",
        "body",
        "raw_headers",
        "local_path",
        "metric_key",
        "ttm",
        "growth",
        "margin",
        "normalized_value",
        "parsed_text",
        "embedding",
        "model_output",
        "executable_content",
    }
    for table_name in STAGE_4_TABLES:
        assert forbidden.isdisjoint(Base.metadata.tables[table_name].columns.keys())


def test_orm_relationships_never_enable_delete_cascade() -> None:
    for model in STAGE_4_MODELS:
        for relationship in model.__mapper__.relationships:
            assert "delete" not in relationship.cascade
            assert "delete-orphan" not in relationship.cascade
