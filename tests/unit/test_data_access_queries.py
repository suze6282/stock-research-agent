from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.domain.data_access.schemas import (
    DailyPriceBarRecord,
    DailyPriceBarWrite,
    DataProviderRecord,
    DataProviderWrite,
    DataSnapshotRecord,
    DataSnapshotWrite,
    ExactDecimal,
    ProviderFinancialFactRecord,
    ProviderFinancialFactWrite,
    ProviderRequestLogRecord,
    ProviderRequestLogWrite,
    RawPayloadWrite,
    SourceDocumentRecord,
    SourceDocumentWrite,
)

SECURITY_ID = UUID("40000000-0000-0000-0000-000000000001")
PROVIDER_ID = UUID("50000000-0000-0000-0000-000000000001")
PAYLOAD_ID = UUID("80000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 7, 10, 20, tzinfo=UTC)


class FakeReadRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.history: tuple[DailyPriceBarRecord, ...] = ()
        self.facts: tuple[ProviderFinancialFactRecord, ...] = ()
        self.snapshot_record: DataSnapshotRecord | None = None
        self.latest_snapshot_record: DataSnapshotRecord | None = None

    def list_daily_history(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        local_trading_date: date | None,
        limit: int,
    ) -> tuple[DailyPriceBarRecord, ...]:
        self.calls.append(("history", limit))
        return self.history

    def list_financial_facts(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
    ) -> tuple[ProviderFinancialFactRecord, ...]:
        self.calls.append(("facts", limit))
        return self.facts

    def list_providers(self, limit: int) -> tuple[()]:
        self.calls.append(("providers", limit))
        return ()

    def get_latest_close(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        local_trading_date: date | None,
    ) -> None:
        self.calls.append(("latest_close", security_id))

    def list_corporate_actions(
        self, security_id: UUID, research_as_of_time: datetime, limit: int
    ) -> tuple[()]:
        self.calls.append(("actions", limit))
        return ()

    def list_source_documents(
        self, security_id: UUID, research_as_of_time: datetime, limit: int
    ) -> tuple[()]:
        self.calls.append(("documents", limit))
        return ()

    def get_snapshot(self, snapshot_id: UUID) -> DataSnapshotRecord | None:
        self.calls.append(("snapshot", snapshot_id))
        return self.snapshot_record

    def get_latest_eligible_snapshot(
        self, security_id: UUID, research_as_of_time: datetime
    ) -> DataSnapshotRecord | None:
        self.calls.append(("latest_snapshot", security_id))
        return self.latest_snapshot_record

    def list_snapshot_items(self, snapshot_id: UUID, limit: int) -> tuple[()]:
        self.calls.append(("snapshot_items", limit))
        return ()


def test_query_service_keeps_empty_data_partial_and_never_infers_values() -> None:
    repository = FakeReadRepository()
    result = DataAccessQueryService(repository).daily_history(
        SECURITY_ID,
        research_as_of_time=NOW,
        local_trading_date=date(2026, 7, 10),
        limit=10,
    )
    assert result.status == "PARTIAL"
    assert result.records == ()
    assert result.warnings == ("NO_DAILY_PRICE_DATA",)
    assert repository.calls == [("history", 10)]


def test_raw_financial_query_preserves_provider_semantics_and_decimal_json_string() -> None:
    repository = FakeReadRepository()
    repository.facts = (
        ProviderFinancialFactRecord(
            id=UUID("90000000-0000-0000-0000-000000000001"),
            security_id=SECURITY_ID,
            provider_id=PROVIDER_ID,
            source_payload_id=PAYLOAD_ID,
            statement_type="OTHER",
            provider_concept="us-gaap:Example",
            reported_label="Reported Example",
            taxonomy="us-gaap",
            context_id="ctx-1",
            dimensions={"segment": "example"},
            value=Decimal("1234567890.123456789012"),
            unit="USD",
            currency_code="USD",
            source_published_at=None,
            retrieved_at=NOW,
            created_at=NOW,
        ),
    )
    result = DataAccessQueryService(repository).reported_financial_facts(
        SECURITY_ID, research_as_of_time=NOW, limit=10
    )
    assert result.status == "PARTIAL"
    assert result.warnings == ("SOURCE_PUBLISHED_AT_UNKNOWN",)
    assert result.records[0].provider_concept == "us-gaap:Example"
    assert result.records[0].model_dump_json().count('"1234567890.123456789012"') == 1
    serialized = result.model_dump()
    assert "metric_key" not in str(serialized)
    assert "storage_uri" not in str(serialized)
    assert "inline_json" not in str(serialized)


def test_query_service_enforces_bounds_before_repository_access() -> None:
    repository = FakeReadRepository()
    service = DataAccessQueryService(repository)
    try:
        service.daily_history(SECURITY_ID, NOW, None, 101)
    except ValueError as error:
        assert "between 1 and 100" in str(error)
    else:
        raise AssertionError("an unbounded query must fail")
    assert repository.calls == []


def test_query_module_has_no_framework_or_provider_dependencies() -> None:
    import stock_research_agent.domain.data_access.queries as queries

    names = set(queries.__dict__)
    assert "Session" not in names
    assert "FastAPI" not in names
    assert "httpx" not in names
    assert "DataProviderAdapter" not in names


def test_all_empty_query_categories_have_controlled_statuses_and_warnings() -> None:
    repository = FakeReadRepository()
    service = DataAccessQueryService(repository)
    assert service.provider_catalog().status == "BLOCKED"
    assert service.latest_close(SECURITY_ID, NOW, None).warnings == ("NO_DAILY_PRICE_DATA",)
    assert service.corporate_actions(SECURITY_ID, NOW, 10).status == "PARTIAL"
    assert service.source_documents(SECURITY_ID, NOW, 10).status == "PARTIAL"
    assert service.snapshot(UUID(int=1)).status == "BLOCKED"
    assert service.latest_snapshot(SECURITY_ID, NOW).status == "BLOCKED"
    assert service.snapshot_items(UUID(int=1), 10).status == "PARTIAL"


def test_write_dtos_reject_binary_float_naive_time_invalid_storage_and_fake_completion() -> None:
    base_bar = {
        "security_id": SECURITY_ID,
        "provider_id": PROVIDER_ID,
        "source_payload_id": PAYLOAD_ID,
        "provider_symbol": "EXM",
        "trading_date": date(2026, 7, 10),
        "close": "10.25",
        "currency_code": "USD",
        "adjustment_type": "UNADJUSTED",
        "retrieved_at": NOW,
    }
    with pytest.raises(ValidationError, match="binary float"):
        DailyPriceBarWrite(**(base_bar | {"close": 10.25}))
    with pytest.raises(ValidationError, match="timezone aware"):
        DailyPriceBarWrite(**(base_bar | {"retrieved_at": datetime(2026, 7, 10)}))
    with pytest.raises(ValidationError, match="exactly one"):
        RawPayloadWrite(
            ingestion_run_id=UUID(int=1),
            provider_request_log_id=UUID(int=2),
            provider_id=PROVIDER_ID,
            security_id=SECURITY_ID,
            category="DAILY_PRICES",
            content_type="application/json",
            checksum="a" * 64,
            retrieved_at=NOW,
            provider_version="1.0.0",
            parser_version="1.0.0",
            schema_version="1.0.0",
            byte_size=0,
        )
    with pytest.raises(ValidationError, match="completed snapshots"):
        DataSnapshotWrite(
            security_id=SECURITY_ID,
            research_as_of_time=NOW,
            snapshot_version=1,
            status="COMPLETE",
            formula_version="raw-data-v1",
        )
    with pytest.raises(ValidationError, match="binary float"):
        ProviderFinancialFactWrite(
            security_id=SECURITY_ID,
            provider_id=PROVIDER_ID,
            source_payload_id=PAYLOAD_ID,
            statement_type="OTHER",
            provider_concept="raw:Example",
            dimensions={},
            value=1.5,
            retrieved_at=NOW,
        )


def test_raw_fact_contract_has_no_normalized_metric_ttm_or_valuation_fields() -> None:
    forbidden = {"metric_key", "normalized_value", "ttm", "valuation", "growth", "margin"}
    assert forbidden.isdisjoint(ProviderFinancialFactWrite.model_fields)
    assert forbidden.isdisjoint(ProviderFinancialFactRecord.model_fields)


@pytest.mark.parametrize(
    ("value"),
    (
        Decimal("1.1234567890123"),
        Decimal("123456789012345678901234567.123456789012"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ),
)
def test_exact_decimal_contract_rejects_rounding_overflow_and_nonfinite_values(
    value: Decimal,
) -> None:
    with pytest.raises(ValidationError):
        DailyPriceBarWrite(
            security_id=SECURITY_ID,
            provider_id=PROVIDER_ID,
            source_payload_id=PAYLOAD_ID,
            provider_symbol="EXM",
            trading_date=date(2026, 7, 10),
            close=value,
            currency_code="USD",
            adjustment_type="UNADJUSTED",
            retrieved_at=NOW,
        )


def _snapshot_record(status: str) -> DataSnapshotRecord:
    completed = status != "BUILDING"
    has_checksum = status not in {"BUILDING", "FAILED"}
    return DataSnapshotRecord(
        id=UUID(int=10),
        security_id=SECURITY_ID,
        research_as_of_time=NOW,
        snapshot_version=1,
        status=status,
        completed_at=NOW if completed else None,
        checksum="d" * 64 if has_checksum else None,
        formula_version="raw-data-v1",
        created_at=NOW,
    )


@pytest.mark.parametrize(
    ("snapshot_status", "query_status", "warning"),
    (
        ("COMPLETE", "PASS", None),
        ("PARTIAL", "PARTIAL", "SNAPSHOT_PARTIAL"),
        ("FAILED", "FAIL", "SNAPSHOT_FAILED"),
        ("BUILDING", "PARTIAL", "SNAPSHOT_BUILDING"),
        ("SUPERSEDED", "PARTIAL", "SNAPSHOT_SUPERSEDED"),
    ),
)
def test_snapshot_detail_maps_persistence_state_to_explicit_query_semantics(
    snapshot_status: str,
    query_status: str,
    warning: str | None,
) -> None:
    repository = FakeReadRepository()
    repository.snapshot_record = _snapshot_record(snapshot_status)
    result = DataAccessQueryService(repository).snapshot(UUID(int=10))
    assert result.status == query_status
    assert result.warnings == (() if warning is None else (warning,))


@pytest.mark.parametrize(
    ("snapshot_status", "query_status", "warning"),
    (
        ("COMPLETE", "PASS", None),
        ("PARTIAL", "PARTIAL", "SNAPSHOT_PARTIAL"),
    ),
)
def test_latest_snapshot_uses_the_same_explicit_state_mapping(
    snapshot_status: str,
    query_status: str,
    warning: str | None,
) -> None:
    repository = FakeReadRepository()
    repository.latest_snapshot_record = _snapshot_record(snapshot_status)
    result = DataAccessQueryService(repository).latest_snapshot(SECURITY_ID, NOW)
    assert result.status == query_status
    assert result.warnings == (() if warning is None else (warning,))


def _request_log_write(safe_url: str) -> ProviderRequestLogWrite:
    return ProviderRequestLogWrite(
        ingestion_run_id=UUID(int=1),
        provider_id=PROVIDER_ID,
        caller_request_id=UUID(int=2),
        endpoint_name="prices",
        method="GET",
        safe_url=safe_url,
        request_started_at=NOW,
        attempt=1,
        cache_status="MISS",
    )


@pytest.mark.parametrize(
    "safe_url",
    (
        "http://provider.example/prices",
        "https://user:pass@provider.example/prices",
        "https://provider.example/prices#fragment",
        "https://provider.example/prices?api_key=secret",
        "https://provider.example/prices?access_token=secret",
    ),
)
def test_request_log_safe_url_rejects_unsafe_or_unredacted_values(safe_url: str) -> None:
    with pytest.raises(ValidationError):
        _request_log_write(safe_url)


def test_request_log_safe_url_accepts_stably_redacted_sensitive_query_values() -> None:
    record = _request_log_write("https://provider.example/prices?api_key=%2A%2A%2A&symbol=MU")
    assert record.safe_url.endswith("api_key=%2A%2A%2A&symbol=MU")


def test_repository_package_exports_security_master_and_data_access_implementations() -> None:
    from stock_research_agent.db import repositories

    assert repositories.__all__ == [
        "SqlAlchemyDataAccessRepository",
        "SqlAlchemyKnowledgeRepository",
        "SqlAlchemyProviderDefinitionRepository",
        "SqlAlchemyProviderArtifactRepository",
        "SqlAlchemyProviderGovernanceRepository",
        "SqlAlchemyProviderQueryRepository",
        "SqlAlchemyProviderSyncRepository",
        "SqlAlchemyResearchAgentRepository",
        "SqlAlchemyReportRepository",
        "SqlAlchemySecurityMasterRepository",
    ]


@pytest.mark.parametrize(
    "safe_url",
    (
        "https://provider.example:invalid/prices",
        "https://provider.example:70000/prices",
        "https://provider.example/prices\n?symbol=MU",
        "https://provider.example/prices?port-secret=visible",
        "https://provider.example/prices?sig=visible",
        "https://provider.example/prices?session_id=visible",
        "https://provider.example/prices?credentials=visible",
        "https://provider.example/prices?passwd=visible",
    ),
)
def test_request_log_shared_url_contract_rejects_invalid_port_controls_and_variants(
    safe_url: str,
) -> None:
    with pytest.raises(ValidationError):
        _request_log_write(safe_url)


def test_request_log_shared_url_contract_accepts_normal_and_redacted_queries() -> None:
    assert _request_log_write("https://provider.example/prices?symbol=MU").safe_url.endswith(
        "symbol=MU"
    )
    assert _request_log_write(
        "https://provider.example:8443/prices?session_id=***&sig=***"
    ).safe_url.endswith("session_id=***&sig=***")


def _provider_write(**overrides: object) -> DataProviderWrite:
    values: dict[str, object] = {
        "code": "SAFE_PROVIDER",
        "name": "Safe Provider",
        "provider_type": "MARKET_DATA",
        "status": "APPROVED",
        "terms_status": "VERIFIED",
        "capabilities": ("DAILY_PRICES",),
    }
    values.update(overrides)
    return DataProviderWrite(**values)


@pytest.mark.parametrize(
    "url",
    (
        "https://provider.example/docs?token=***",
        "https://provider.example/docs?port-secret=***",
        "https://provider.example/docs?session=***",
        "https://user:pass@provider.example/docs",
        "https://provider.example/docs#fragment",
    ),
)
def test_provider_write_and_record_urls_forbid_all_credential_query_keys(url: str) -> None:
    with pytest.raises(ValidationError):
        _provider_write(base_url=url)
    record_values = _provider_write().model_dump()
    record_values["base_url"] = url
    with pytest.raises(ValidationError):
        DataProviderRecord(
            **record_values,
            id=UUID(int=20),
            created_at=NOW,
            updated_at=NOW,
        )


def _source_document_values(source_url: str) -> dict[str, object]:
    return {
        "id": UUID(int=30),
        "security_id": SECURITY_ID,
        "provider_id": PROVIDER_ID,
        "source_payload_id": PAYLOAD_ID,
        "provider_document_id": "doc-1",
        "document_type": "OTHER",
        "title": "Source document",
        "form_type": None,
        "accession_number": None,
        "announcement_id": None,
        "period_end": None,
        "filed_at": None,
        "published_at": None,
        "source_url": source_url,
        "primary_document_name": None,
        "mime_type": None,
        "checksum": None,
        "byte_size": None,
        "document_status": "METADATA_ONLY",
        "retrieved_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
    }


@pytest.mark.parametrize(
    "source_url",
    (
        "https://www.sec.gov/doc?api_key=***",
        "https://www.sec.gov/doc?authorization=***",
        "https://www.sec.gov/doc?refresh_token=***",
        "https://www.sec.gov:bad/doc",
        "https://www.sec.gov/doc\r?symbol=MU",
    ),
)
def test_source_document_write_and_record_reject_credential_urls_and_legacy_rows(
    source_url: str,
) -> None:
    write_values = _source_document_values(source_url)
    for record_field in ("id", "created_at", "updated_at"):
        write_values.pop(record_field)
    with pytest.raises(ValidationError):
        SourceDocumentWrite(**write_values)
    with pytest.raises(ValidationError):
        SourceDocumentRecord(**_source_document_values(source_url))


def test_public_source_urls_allow_https_ports_and_ordinary_queries() -> None:
    provider = _provider_write(
        base_url="https://provider.example:8443/api?region=us",
        documentation_url="https://provider.example/docs?language=en",
    )
    assert provider.base_url == "https://provider.example:8443/api?region=us"
    values = _source_document_values("https://www.sec.gov/doc?format=html")
    assert SourceDocumentRecord(**values).source_url.endswith("format=html")


def test_exact_decimal_contract_declares_an_explicit_json_string_serializer() -> None:
    assert any(
        type(metadata).__name__ == "PlainSerializer" for metadata in ExactDecimal.__metadata__
    )


@pytest.mark.parametrize("record_type", ("provider", "request", "document"))
def test_record_validation_errors_never_echo_legacy_secret_input(record_type: str) -> None:
    sentinel = "SECRET_SENTINEL"
    unsafe_url = f"https://legacy.example/data?api_key={sentinel}"
    with pytest.raises(ValidationError) as captured:
        if record_type == "provider":
            values = _provider_write().model_dump()
            values["base_url"] = unsafe_url
            DataProviderRecord(
                **values,
                id=UUID(int=40),
                created_at=NOW,
                updated_at=NOW,
            )
        elif record_type == "request":
            values = _request_log_write("https://legacy.example/data").model_dump()
            values["safe_url"] = unsafe_url
            ProviderRequestLogRecord(
                **values,
                id=UUID(int=41),
                created_at=NOW,
            )
        else:
            SourceDocumentRecord(**_source_document_values(unsafe_url))
    assert sentinel not in str(captured.value)
    assert sentinel not in repr(captured.value)
    assert "input_value" not in str(captured.value)
    assert "input_value" not in repr(captured.value)
