from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.data_access.schemas import ProviderFinancialFactWrite
from stock_research_agent.domain.documents.enums import (
    DocumentLanguage,
    SourceVersionStatus,
    TrustLevel,
)
from stock_research_agent.domain.documents.schemas import DocumentVersionWrite
from stock_research_agent.domain.providers.artifacts import (
    ProviderBatch,
    ProviderIngestionManifestRecord,
    ProviderRecord,
    ProviderRecordIdentity,
    ProviderRecordStatus,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.providers.bridges.documents import (
    DocumentBridgeContext,
    DocumentProviderBridge,
)
from stock_research_agent.providers.bridges.financials import (
    FinancialFactBridgeContext,
    FinancialFactProviderBridge,
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


class _DocumentRepository:
    def __init__(self) -> None:
        self.values: list[DocumentVersionWrite] = []
        self.downstream_calls: list[str] = []

    def add_version(self, value: DocumentVersionWrite) -> object:
        self.values.append(value)
        return object()

    def parse(self, value: object) -> None:
        self.downstream_calls.append("parse")

    def build_index(self, value: object) -> None:
        self.downstream_calls.append("index")


class _FinancialRepository:
    def __init__(self) -> None:
        self.values: list[ProviderFinancialFactWrite] = []
        self.downstream_calls: list[str] = []

    def add_financial_fact(self, value: ProviderFinancialFactWrite) -> object:
        self.values.append(value)
        return object()

    def normalize(self, value: object) -> None:
        self.downstream_calls.append("normalize")

    def calculate(self, value: object) -> None:
        self.downstream_calls.append("calculate")


def _record(
    *,
    record_key: str,
    text_values: dict[str, str | None],
    numeric_values: dict[str, str | None] | None = None,
    source_published_at: datetime | None = PUBLISHED_AT,
) -> ProviderRecord:
    return ProviderRecord(
        identity=ProviderRecordIdentity(
            provider_definition_id=UUID("66666666-6666-4666-8666-666666666666"),
            provider_capability_id=UUID("77777777-7777-4777-8777-777777777777"),
            source_identity="provider:evidence:test",
            record_key=record_key,
            revision=1,
        ),
        raw_artifact_id=RAW_ARTIFACT_ID,
        source_checksum=SOURCE_CHECKSUM,
        source_published_at=source_published_at,
        status=ProviderRecordStatus.COMPLETE,
        numeric_values=numeric_values or {},
        text_values=text_values,
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


def _document_record(content_status: str = "VERIFIED_BODY") -> ProviderRecord:
    return _record(
        record_key="document:0001",
        text_values={
            "security_id": str(SECURITY_ID),
            "document_content_status": content_status,
        },
    )


def _document_context(**updates: object) -> DocumentBridgeContext:
    values: dict[str, object] = {
        "logical_document_id": UUID("99999999-9999-4999-8999-999999999999"),
        "source_document_id": UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        "security_id": SECURITY_ID,
        "provider_id": PROVIDER_ID,
        "source_payload_id": SOURCE_PAYLOAD_ID,
        "version_number": 1,
        "supersedes_document_version_id": None,
        "storage_uri": "blob://documents/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "mime_type": "text/html",
        "checksum": SOURCE_CHECKSUM,
        "byte_size": 1024,
        "published_at": PUBLISHED_AT,
        "filed_at": PUBLISHED_AT,
        "period_end": None,
        "retrieved_at": RETRIEVED_AT,
        "document_language": DocumentLanguage.EN_US,
        "trust_level": TrustLevel.OFFICIAL_REGULATORY,
        "evidence_origin": "SOURCE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
        "source_version_status": SourceVersionStatus.ACTIVE,
        "research_as_of_time": AS_OF,
        "derived_use_approved": True,
        "raw_body_retention_approved": True,
    }
    values.update(updates)
    return DocumentBridgeContext(**values)


def _financial_record(**text_updates: str | None) -> ProviderRecord:
    text_values: dict[str, str | None] = {
        "security_id": str(SECURITY_ID),
        "statement_type": "INCOME_STATEMENT",
        "provider_concept": "revenue",
        "reported_label": "Revenue",
        "taxonomy": "TUSHARE_RAW",
        "context_id": "FY2025",
        "unit": "CNY",
        "currency_code": "CNY",
        "fiscal_year": "2025",
        "fiscal_quarter": None,
        "fiscal_period": "FY",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "instant_date": None,
        "filed_at": "2026-03-30T08:00:00Z",
        "form_type": "ANNUAL",
        "is_annual": "true",
        "is_cumulative": "true",
        "is_audited": "true",
        "is_restated": "false",
        "provider_record_id": "raw-revenue-fy2025",
        "aggregation_semantics": "PROVIDER_REPORTED_UNNORMALIZED",
    }
    text_values.update(text_updates)
    return _record(
        record_key="financial:0001",
        text_values=text_values,
        numeric_values={"value": "123456789.01"},
    )


def _financial_context(**updates: object) -> FinancialFactBridgeContext:
    values: dict[str, object] = {
        "security_id": SECURITY_ID,
        "provider_id": PROVIDER_ID,
        "source_payload_id": SOURCE_PAYLOAD_ID,
        "source_payload_checksum": SOURCE_CHECKSUM,
        "retrieved_at": RETRIEVED_AT,
        "research_as_of_time": AS_OF,
        "derived_use_approved": True,
        "raw_fact_retention_approved": True,
    }
    values.update(updates)
    return FinancialFactBridgeContext(**values)


def test_document_bridge_adds_only_immutable_raw_document_version_input() -> None:
    repository = _DocumentRepository()
    batch = _batch(_document_record())

    result = DocumentProviderBridge(repository).stage(_manifest(batch), batch, _document_context())

    assert result.staged_document_version_count == 1
    assert result.manifest_id == MANIFEST_ID
    assert result.raw_artifact_id == RAW_ARTIFACT_ID
    assert result.parse_run_created is False
    assert result.retrieval_run_created is False
    assert repository.downstream_calls == []
    value = repository.values[0]
    assert value.checksum == SOURCE_CHECKSUM
    assert value.storage_uri == "blob://documents/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    assert value.source_payload_id == SOURCE_PAYLOAD_ID


def test_document_bridge_rejects_sec_metadata_as_company_body() -> None:
    repository = _DocumentRepository()
    batch = _batch(_document_record(content_status="METADATA_ONLY"))

    with pytest.raises(ValueError, match="DOCUMENT_BODY_NOT_VERIFIED"):
        DocumentProviderBridge(repository).stage(_manifest(batch), batch, _document_context())

    assert repository.values == []


def test_document_bridge_rejects_future_body_and_unapproved_retention() -> None:
    repository = _DocumentRepository()
    batch = _batch(_document_record())

    with pytest.raises(ValueError, match="DOCUMENT_FUTURE_DATA"):
        DocumentProviderBridge(repository).stage(
            _manifest(batch),
            batch,
            _document_context(published_at=datetime(2026, 8, 2, tzinfo=UTC)),
        )
    with pytest.raises(ValueError, match="DOCUMENT_DERIVED_STORAGE_NOT_APPROVED"):
        DocumentProviderBridge(repository).stage(
            _manifest(batch),
            batch,
            _document_context(raw_body_retention_approved=False),
        )


def test_financial_bridge_preserves_raw_concept_value_unit_period_and_lineage() -> None:
    repository = _FinancialRepository()
    batch = _batch(_financial_record())

    result = FinancialFactProviderBridge(repository).stage(
        _manifest(batch), batch, _financial_context()
    )

    assert result.staged_fact_count == 1
    assert result.manifest_id == MANIFEST_ID
    assert result.normalization_run_created is False
    assert result.calculation_run_created is False
    assert repository.downstream_calls == []
    value = repository.values[0]
    assert str(value.value) == "123456789.01"
    assert value.provider_concept == "revenue"
    assert value.unit == "CNY"
    assert value.currency_code == "CNY"
    assert value.period_start.isoformat() == "2025-01-01"
    assert value.period_end.isoformat() == "2025-12-31"
    assert value.is_cumulative is True
    assert value.source_payload_id == SOURCE_PAYLOAD_ID


def test_financial_bridge_allows_raw_provider_indicator_but_forbids_formula_substitution() -> None:
    repository = _FinancialRepository()
    raw_indicator = _financial_record(
        provider_concept="roe",
        taxonomy="TUSHARE_PROVIDER_INDICATOR",
        provider_metric_fields="roe",
    )
    batch = _batch(raw_indicator)

    FinancialFactProviderBridge(repository).stage(_manifest(batch), batch, _financial_context())

    assert repository.values[0].provider_concept == "roe"
    formula_record = _financial_record(canonical_formula_code="RETURN_ON_EQUITY")
    formula_batch = _batch(formula_record)
    with pytest.raises(ValueError, match="PROVIDER_FORMULA_SUBSTITUTION_FORBIDDEN"):
        FinancialFactProviderBridge(_FinancialRepository()).stage(
            _manifest(formula_batch),
            formula_batch,
            _financial_context(),
        )


def test_financial_bridge_does_not_split_cumulative_or_replace_missing_with_zero() -> None:
    repository = _FinancialRepository()
    missing = _financial_record()
    missing = missing.model_copy(update={"numeric_values": {"value": None}})
    batch = _batch(missing)

    FinancialFactProviderBridge(repository).stage(_manifest(batch), batch, _financial_context())

    assert repository.values[0].value is None
    assert repository.values[0].is_cumulative is True
    assert len(repository.values) == 1


def test_financial_bridge_rejects_future_data_raw_mismatch_and_unapproved_storage() -> None:
    repository = _FinancialRepository()
    future = _financial_record()
    future = future.model_copy(update={"source_published_at": datetime(2026, 8, 2, tzinfo=UTC)})
    future_batch = _batch(future)

    with pytest.raises(ValueError, match="FINANCIAL_FACT_FUTURE_DATA"):
        FinancialFactProviderBridge(repository).stage(
            _manifest(future_batch), future_batch, _financial_context()
        )
    valid_batch = _batch(_financial_record())
    with pytest.raises(ValueError, match="FINANCIAL_FACT_RAW_CHECKSUM_MISMATCH"):
        FinancialFactProviderBridge(repository).stage(
            _manifest(valid_batch),
            valid_batch,
            _financial_context(source_payload_checksum="c" * 64),
        )
    with pytest.raises(ValueError, match="FINANCIAL_FACT_DERIVED_STORAGE_NOT_APPROVED"):
        FinancialFactProviderBridge(repository).stage(
            _manifest(valid_batch),
            valid_batch,
            _financial_context(derived_use_approved=False),
        )
