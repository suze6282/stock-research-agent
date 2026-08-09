from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.data_access.enums import (
    AccessMode,
    DataCategory,
    DataOrigin,
    LiveStatus,
    ProviderCapability,
    ProviderStatus,
    QualityStatus,
)
from stock_research_agent.domain.data_access.ingestion import (
    IngestionRequest,
    IngestionResult,
    IngestionService,
    compute_ingestion_idempotency_key,
)
from stock_research_agent.domain.data_access.schemas import (
    DataProviderRecord,
    DataQuality,
    IngestionRunRecord,
    ProviderDescriptor,
    ProviderEnvelope,
    ProviderInstrument,
    ProviderRecord,
)
from stock_research_agent.infrastructure.blob_storage import BlobMetadata, InMemoryBlobStorage
from stock_research_agent.providers.registry import ProviderRegistry

NOW = datetime(2026, 7, 15, 8, 30, tzinfo=UTC)
SECURITY_ID = UUID("11111111-1111-1111-1111-111111111111")
PROVIDER_ID = UUID("22222222-2222-2222-2222-222222222222")
REQUEST_ID = UUID("33333333-3333-3333-3333-333333333333")


class FixedClock:
    def __init__(self) -> None:
        self.values: list[datetime] = [NOW + timedelta(seconds=i) for i in range(20)]

    def now(self) -> datetime:
        return self.values.pop(0)


class Adapter:
    code = "TEST_FIXTURE"
    version = "1.2.3"
    capabilities = frozenset(
        {
            ProviderCapability.DAILY_PRICES,
            ProviderCapability.FINANCIAL_FACTS,
            ProviderCapability.CORPORATE_ACTIONS,
            ProviderCapability.FILING_METADATA,
        }
    )

    def __init__(
        self,
        envelope: ProviderEnvelope,
        *,
        status: ProviderStatus = ProviderStatus.APPROVED,
        enabled: bool = True,
        requires_credentials: bool = False,
        credentials_configured: bool = False,
    ) -> None:
        self.envelope = envelope
        self.fetch_count = 0
        self.descriptor = ProviderDescriptor(
            code=self.code,
            name="Test fixture",
            version=self.version,
            status=status,
            capabilities=self.capabilities,
            is_enabled=enabled,
            requires_credentials=requires_credentials,
            credentials_configured=credentials_configured,
        )

    def fetch(self, request: object) -> ProviderEnvelope:
        self.fetch_count += 1
        return self.envelope


class FakeRepository:
    def __init__(self) -> None:
        self.provider: DataProviderRecord | None = _provider()
        self.mapping: ProviderInstrument | None = ProviderInstrument(
            security_id=SECURITY_ID,
            provider_symbol="EXACT",
            provider_exchange_code="XNAS",
            provider_instrument_id="instrument-1",
        )
        self.runs: dict[str, IngestionRunRecord] = {}
        self.request_logs: list[object] = []
        self.payloads: list[object] = []
        self.prices: list[object] = []
        self.actions: list[object] = []
        self.facts: list[object] = []
        self.documents: list[object] = []
        self.fail_price = False
        self.fail_terminal_pass = False
        self.fail_create = False
        self.fail_running = False
        self.fail_statuses: set[str] = set()

    def get_provider(self, code: str) -> DataProviderRecord | None:
        return self.provider if self.provider is not None and self.provider.code == code else None

    def get_active_mapping(
        self, security_id: UUID, provider_code: str, as_of: date
    ) -> ProviderInstrument | None:
        return self.mapping

    def get_ingestion_run_by_idempotency_key(self, key: str) -> IngestionRunRecord | None:
        return self.runs.get(key)

    def get_or_create_ingestion_run(self, value: object) -> tuple[IngestionRunRecord, bool]:
        if self.fail_create:
            raise RuntimeError("postgresql://user:SECRET@host/db CREATE SQL /private/payload")
        key = value.idempotency_key
        existing = self.runs.get(key)
        if existing is not None:
            return existing, False
        run = IngestionRunRecord(
            id=uuid4(),
            provider_id=value.provider_id,
            security_id=value.security_id,
            category=value.category,
            status="QUEUED",
            research_as_of_time=value.research_as_of_time,
            idempotency_key=key,
            requested_at=value.requested_at,
            started_at=None,
            completed_at=None,
            request_count=0,
            records_received=0,
            records_stored=0,
            warning_count=0,
            error_code=None,
            safe_error_message=None,
            created_at=value.requested_at,
            updated_at=value.requested_at,
        )
        self.runs[key] = run
        return run, True

    def update_ingestion_run(self, run_id: UUID, value: object) -> IngestionRunRecord:
        if self.fail_running and value.status == "RUNNING":
            raise RuntimeError("token=SECRET RUNNING SQL C:\\private\\payload")
        if value.status in self.fail_statuses:
            raise RuntimeError("password=SECRET terminal SQL /private/payload")
        if self.fail_terminal_pass and value.status == "PASS":
            raise RuntimeError("unsafe terminal persistence detail")
        key, current = next((key, run) for key, run in self.runs.items() if run.id == run_id)
        updated = current.model_copy(update=value.model_dump(exclude_unset=True))
        self.runs[key] = updated
        return updated

    @contextmanager
    def ingestion_attempt(self) -> Iterator[None]:
        snapshot = deepcopy(
            (
                self.runs,
                self.request_logs,
                self.payloads,
                self.prices,
                self.actions,
                self.facts,
                self.documents,
            )
        )
        try:
            yield
        except Exception:
            (
                self.runs,
                self.request_logs,
                self.payloads,
                self.prices,
                self.actions,
                self.facts,
                self.documents,
            ) = snapshot
            raise

    def add_request_log(self, value: object) -> object:
        result = value.model_copy(update={"id": uuid4(), "created_at": NOW})
        self.request_logs.append(result)
        return result

    def add_raw_payload(self, value: object) -> object:
        result = value.model_copy(update={"id": uuid4(), "created_at": NOW})
        self.payloads.append(result)
        return result

    def add_daily_price_bar(self, value: object) -> object:
        if self.fail_price:
            raise RuntimeError("postgresql://user:SECRET@host/db SQL payload=/private/raw")
        result = value.model_copy(update={"id": uuid4(), "created_at": NOW})
        self.prices.append(result)
        return result

    def add_financial_fact(self, value: object) -> object:
        self.facts.append(value)
        return value

    def add_corporate_action(self, value: object) -> object:
        self.actions.append(value)
        return value

    def add_source_document(self, value: object) -> object:
        self.documents.append(value)
        return value


def _provider(**updates: object) -> DataProviderRecord:
    values = {
        "id": PROVIDER_ID,
        "code": "TEST_FIXTURE",
        "name": "Persisted fixture",
        "provider_type": "FIXTURE",
        "status": ProviderStatus.APPROVED,
        "base_url": "https://fixtures.example.test/data",
        "documentation_url": None,
        "terms_status": "VERIFIED",
        "capabilities": (
            ProviderCapability.DAILY_PRICES,
            ProviderCapability.FINANCIAL_FACTS,
            ProviderCapability.CORPORATE_ACTIONS,
            ProviderCapability.FILING_METADATA,
        ),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(updates)
    return DataProviderRecord(**values)


def _envelope(
    *,
    category: DataCategory = DataCategory.DAILY_PRICES,
    quality: QualityStatus = QualityStatus.PASS,
    raw_payload: object = b'{"exact":1}\n',
    records: tuple[ProviderRecord, ...] | None = None,
) -> ProviderEnvelope:
    if records is None and category is DataCategory.DAILY_PRICES:
        records = (
            ProviderRecord(
                record_type="daily_price",
                provider_record_id=None,
                source_published_at=None,
                data={
                    "trading_date": "2026-07-10",
                    "open": Decimal("964.975"),
                    "high": Decimal("998.00"),
                    "low": Decimal("954.13"),
                    "close": Decimal("979.30"),
                    "volume": 31768090,
                    "currency_code": "USD",
                },
            ),
        )
    records = records or ()
    warnings = ("FIXTURE_WARNING",) if quality is QualityStatus.PARTIAL else ()
    return ProviderEnvelope(
        provider_code="TEST_FIXTURE",
        provider_version="1.2.3",
        category=category,
        records=records,
        raw_payload=raw_payload,
        content_type="application/json",
        source_endpoint="fixture://stage1/example.json",
        provider_request_id=None,
        retrieved_at=NOW,
        source_published_at=None,
        warnings=warnings,
        quality=DataQuality(
            status=quality,
            required_fields_present=1 if records else 0,
            required_fields_total=1,
            warnings=warnings,
        ),
        data_origin=DataOrigin.FIXTURE,
        access_mode=AccessMode.OFFLINE,
        live_status=LiveStatus.NOT_LIVE,
    )


def _request(**updates: object) -> IngestionRequest:
    values = {
        "request_id": REQUEST_ID,
        "security_id": SECURITY_ID,
        "provider_code": "TEST_FIXTURE",
        "category": DataCategory.DAILY_PRICES,
        "research_as_of_time": NOW,
        "date_from": date(2026, 7, 1),
        "date_to": date(2026, 7, 15),
        "parameters": {"b": 2, "a": 1},
        "parser_version": "1.0.0",
        "schema_version": "1.0.0",
    }
    values.update(updates)
    return IngestionRequest(**values)


def _service(
    repository: FakeRepository, adapter: Adapter, storage: object | None = None
) -> tuple[IngestionService, ProviderRegistry, object]:
    registry = ProviderRegistry()
    registry.register(adapter)
    blobs = storage or InMemoryBlobStorage(max_blob_bytes=1024 * 1024)
    return IngestionService(repository, registry, blobs, clock=FixedClock()), registry, blobs


class RecordingBlobStorage:
    def __init__(self, *, lie_checksum: bool = False, lie_size: bool = False) -> None:
        self.backend = InMemoryBlobStorage(max_blob_bytes=1024 * 1024)
        self.lie_checksum = lie_checksum
        self.lie_size = lie_size
        self.put_uris: list[str] = []
        self.deleted_uris: list[str] = []

    def put(
        self, data: bytes, *, content_type: str, metadata: dict[str, str] | None = None
    ) -> BlobMetadata:
        stored = self.backend.put(data, content_type=content_type, metadata=metadata)
        self.put_uris.append(stored.uri)
        return BlobMetadata(
            uri=stored.uri,
            checksum_sha256="f" * 64 if self.lie_checksum else stored.checksum_sha256,
            size_bytes=stored.size_bytes + 1 if self.lie_size else stored.size_bytes,
            content_type=stored.content_type,
            metadata=stored.metadata,
        )

    def get(self, uri: str) -> bytes:
        return self.backend.get(uri)

    def exists(self, uri: str) -> bool:
        return self.backend.exists(uri)

    def delete(self, uri: str) -> None:
        self.backend.delete(uri)
        self.deleted_uris.append(uri)

    def checksum(self, uri: str) -> str:
        return self.backend.checksum(uri)

    def metadata(self, uri: str) -> BlobMetadata:
        return self.backend.metadata(uri)


def test_idempotency_key_is_canonical_versioned_and_semantic() -> None:
    utc_request = _request(parameters={"nested": {"b": 2, "a": 1}, "value": 3})
    equivalent = _request(
        research_as_of_time=NOW.astimezone(timezone(timedelta(hours=8))),
        parameters={"value": 3, "nested": {"a": 1, "b": 2}},
    )
    first = compute_ingestion_idempotency_key(utc_request, provider_version="1.2.3")
    assert first == compute_ingestion_idempotency_key(equivalent, provider_version="1.2.3")
    assert first.startswith("ingest:v1:") and len(first) == 74
    assert first != compute_ingestion_idempotency_key(
        equivalent.model_copy(update={"parser_version": "1.0.1"}),
        provider_version="1.2.3",
    )
    assert first != compute_ingestion_idempotency_key(equivalent, provider_version="1.2.4")


def test_ingestion_request_rejects_naive_time_and_invalid_range() -> None:
    with pytest.raises(ValidationError):
        _request(research_as_of_time=NOW.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        _request(date_from=date(2026, 7, 2), date_to=date(2026, 7, 1))


def test_ingestion_contracts_are_strict_and_error_codes_are_typed() -> None:
    request_payload = _request().model_dump(mode="python")
    request_payload["request_id"] = str(REQUEST_ID)
    with pytest.raises(ValidationError):
        IngestionRequest.model_validate(request_payload)

    repository = FakeRepository()
    service, _, _ = _service(repository, Adapter(_envelope()))
    result = service.ingest(_request())
    assert type(result.error_code).__name__ in {"NoneType", "IngestionErrorCode"}
    result_payload = result.model_dump(mode="python")
    result_payload["request_count"] = "1"
    with pytest.raises(ValidationError):
        IngestionResult.model_validate(result_payload)


@pytest.mark.parametrize("phase", ("create", "running", "blocked", "fail", "fallback"))
def test_lifecycle_persistence_failures_return_fixed_safe_result(phase: str) -> None:
    repository = FakeRepository()
    adapter = Adapter(_envelope())
    request = _request(parameters={"phase": phase, "token": "SECRET_PARAMETER"})
    if phase == "create":
        repository.fail_create = True
    elif phase == "running":
        repository.fail_running = True
    elif phase == "blocked":
        repository.mapping = None
        repository.fail_statuses.add("BLOCKED")
    elif phase == "fail":
        adapter.envelope = _envelope().model_copy(update={"live_status": LiveStatus.LIVE})
        repository.fail_statuses.add("FAIL")
    else:
        repository.fail_price = True
        repository.fail_statuses.add("FAIL")

    service, _, _ = _service(repository, adapter)
    result = service.ingest(request)

    assert result.status == "FAIL"
    assert result.error_code == "PERSISTENCE_FAILED"
    assert type(result.error_code).__name__ == "IngestionErrorCode"
    assert result.safe_error_message == "Ingestion persistence failed safely"
    rendered = result.model_dump_json()
    for sentinel in ("SECRET", "postgresql", "password", " SQL ", "/private"):
        assert sentinel not in rendered


@pytest.mark.parametrize(
    ("provider_update", "adapter_kwargs", "error_code"),
    [
        ({"status": ProviderStatus.NOT_ALLOWED}, {}, "PROVIDER_NOT_ALLOWED"),
        ({}, {"enabled": False}, "PROVIDER_DISABLED"),
        (
            {},
            {"requires_credentials": True, "credentials_configured": False},
            "PROVIDER_CREDENTIALS_BLOCKED",
        ),
    ],
)
def test_provider_policy_maps_to_safe_blocked(
    provider_update: dict[str, object], adapter_kwargs: dict[str, object], error_code: str
) -> None:
    repository = FakeRepository()
    repository.provider = _provider(**provider_update)
    adapter = Adapter(_envelope(), **adapter_kwargs)
    service, _, _ = _service(repository, adapter)
    result = service.ingest(_request())
    assert result.status == "BLOCKED" and result.error_code == error_code
    assert adapter.fetch_count == 0


def test_missing_provider_is_safe_prerun_block_and_missing_mapping_is_persisted_block() -> None:
    repository = FakeRepository()
    repository.provider = None
    adapter = Adapter(_envelope())
    service, _, _ = _service(repository, adapter)
    missing_provider = service.ingest(_request())
    assert missing_provider.status == "BLOCKED"
    assert missing_provider.run_id is None
    assert missing_provider.error_code == "PROVIDER_NOT_FOUND"

    repository.provider = _provider()
    repository.mapping = None
    missing_mapping = service.ingest(_request(parameters={"revision": 2}))
    assert missing_mapping.status == "BLOCKED"
    assert missing_mapping.run_id is not None
    assert missing_mapping.error_code == "MAPPING_NOT_ACTIVE"
    assert adapter.fetch_count == 0


def test_capability_and_persisted_adapter_mismatch_are_blocked_without_fetch() -> None:
    repository = FakeRepository()
    adapter = Adapter(_envelope())
    adapter.capabilities = frozenset({ProviderCapability.FINANCIAL_FACTS})
    adapter.descriptor = adapter.descriptor.model_copy(
        update={"capabilities": adapter.capabilities}
    )
    service, _, _ = _service(repository, adapter)
    result = service.ingest(_request())
    assert result.error_code == "PROVIDER_CAPABILITY_MISMATCH"
    assert adapter.fetch_count == 0

    repository = FakeRepository()
    repository.provider = _provider(capabilities=(ProviderCapability.FINANCIAL_FACTS,))
    adapter = Adapter(_envelope())
    service, _, _ = _service(repository, adapter)
    result = service.ingest(_request(parameters={"revision": 2}))
    assert result.error_code == "PROVIDER_METADATA_MISMATCH"
    assert adapter.fetch_count == 0


def test_adapter_license_status_and_full_capability_mismatch_are_blocked() -> None:
    repository = FakeRepository()
    licensed = Adapter(_envelope(), status=ProviderStatus.NEEDS_LICENSE_CONFIRMATION)
    service, _, _ = _service(repository, licensed)
    result = service.ingest(_request(parameters={"case": "license"}))
    assert result.status == "BLOCKED"
    assert result.error_code == "PROVIDER_LICENSE_BLOCKED"
    assert licensed.fetch_count == 0

    repository = FakeRepository()
    repository.provider = _provider(
        capabilities=(ProviderCapability.DAILY_PRICES, ProviderCapability.FINANCIAL_FACTS)
    )
    adapter = Adapter(_envelope())
    service, _, _ = _service(repository, adapter)
    result = service.ingest(_request(parameters={"case": "full-capabilities"}))
    assert result.status == "BLOCKED"
    assert result.error_code == "PROVIDER_METADATA_MISMATCH"
    assert adapter.fetch_count == 0


def test_fixture_provider_rejects_complete_live_markers_before_raw_persistence() -> None:
    repository = FakeRepository()
    live = _envelope().model_copy(
        update={
            "data_origin": DataOrigin.LIVE,
            "access_mode": AccessMode.ONLINE,
            "live_status": LiveStatus.LIVE,
        }
    )
    adapter = Adapter(live)
    storage = RecordingBlobStorage()
    service, _, _ = _service(repository, adapter, storage)
    result = service.ingest(_request(parameters={"case": "fixture-live"}))
    assert result.status == "FAIL"
    assert result.error_code == "PROVIDER_CONTRACT_FAILED"
    assert storage.put_uris == []
    assert repository.request_logs and repository.payloads == [] and repository.prices == []


def test_nonfixture_provider_does_not_infer_live_mode_authorization() -> None:
    repository = FakeRepository()
    repository.provider = _provider(provider_type="MARKET_DATA")
    live = _envelope().model_copy(
        update={
            "data_origin": DataOrigin.LIVE,
            "access_mode": AccessMode.ONLINE,
            "live_status": LiveStatus.LIVE,
        }
    )
    storage = RecordingBlobStorage()
    adapter = Adapter(live)
    service, _, _ = _service(repository, adapter, storage)

    result = service.ingest(_request(parameters={"case": "no-inferred-live-mode"}))

    assert result.status == "BLOCKED"
    assert result.error_code == "PROVIDER_METADATA_MISMATCH"
    assert adapter.fetch_count == 0
    assert storage.put_uris == []
    assert repository.request_logs == repository.payloads == repository.prices == []


def test_pass_persists_exact_lineage_prices_and_uses_injected_clock() -> None:
    repository = FakeRepository()
    adapter = Adapter(_envelope())
    service, _, blobs = _service(repository, adapter)
    result = service.ingest(_request())
    assert result.status == "PASS" and result.records_stored == 1
    assert result.data_origin is DataOrigin.FIXTURE
    assert (result.access_mode, result.live_status) == (AccessMode.OFFLINE, LiveStatus.NOT_LIVE)
    assert len(repository.request_logs) == len(repository.payloads) == len(repository.prices) == 1
    payload = repository.payloads[0]
    assert payload.storage_uri.startswith("blob://")
    assert blobs.get(payload.storage_uri) == b'{"exact":1}\n'
    assert payload.checksum == "1e7ebc6d05ffd252c1d9298c52fad57c834df612adc1fceeabf01d7783839a95"
    assert payload.byte_size == 12
    price = repository.prices[0]
    assert price.close == Decimal("979.30") and price.volume == 31768090
    assert price.adjustment_type is None
    run = repository.runs[result.idempotency_key]
    assert run.requested_at == NOW and run.started_at == NOW + timedelta(seconds=1)
    assert run.completed_at == NOW + timedelta(seconds=4)
    log = repository.request_logs[0]
    assert log.safe_url == "https://fixtures.example.test/data"
    assert log.caller_request_id == REQUEST_ID
    assert "fixture://" not in log.safe_url


def test_repeat_is_idempotent_and_does_not_refetch_or_rewrite() -> None:
    repository = FakeRepository()
    adapter = Adapter(_envelope())
    service, _, blobs = _service(repository, adapter)
    first = service.ingest(_request())
    first_uri = repository.payloads[0].storage_uri
    repeated = service.ingest(_request(request_id=uuid4()))
    assert repeated.run_id == first.run_id
    assert (repeated.data_origin, repeated.access_mode, repeated.live_status) == (
        DataOrigin.FIXTURE,
        AccessMode.OFFLINE,
        LiveStatus.NOT_LIVE,
    )
    assert adapter.fetch_count == 1
    assert len(repository.payloads) == len(repository.prices) == 1
    assert blobs.get(first_uri) == b'{"exact":1}\n'


def test_partial_empty_financial_facts_persists_no_fake_row() -> None:
    repository = FakeRepository()
    envelope = _envelope(
        category=DataCategory.FINANCIAL_FACTS,
        quality=QualityStatus.PARTIAL,
        records=(),
    )
    adapter = Adapter(envelope)
    service, _, _ = _service(repository, adapter)
    result = service.ingest(_request(category=DataCategory.FINANCIAL_FACTS))
    assert result.status == "PARTIAL"
    assert result.warning_count == 1 and result.warnings == ("FIXTURE_WARNING",)
    assert result.records_stored == 0 and repository.facts == []

    replay = service.ingest(_request(category=DataCategory.FINANCIAL_FACTS, request_id=uuid4()))
    assert replay.run_id == result.run_id
    assert replay.warnings == ("PREVIOUS_INGESTION_COMPLETED_WITH_WARNINGS",)


@pytest.mark.parametrize("quality", (QualityStatus.BLOCKED, QualityStatus.FAIL))
def test_nonpassing_provider_quality_persists_evidence_without_projection(
    quality: QualityStatus,
) -> None:
    repository = FakeRepository()
    adapter = Adapter(_envelope(quality=quality))
    service, _, _ = _service(repository, adapter)
    result = service.ingest(_request(parameters={"quality": quality.value}))
    assert result.status == quality.value
    assert len(repository.request_logs) == len(repository.payloads) == 1
    assert repository.prices == []
    assert result.records_received == 1 and result.records_stored == 0


@pytest.mark.parametrize("lie", ("checksum", "size"))
def test_blob_metadata_mismatch_safe_fails_and_compensates(lie: str) -> None:
    repository = FakeRepository()
    storage = RecordingBlobStorage(
        lie_checksum=lie == "checksum",
        lie_size=lie == "size",
    )
    service, _, _ = _service(repository, Adapter(_envelope()), storage)
    result = service.ingest(_request(parameters={"lie": lie}))
    assert result.status == "FAIL" and result.error_code == "PERSISTENCE_FAILED"
    assert storage.put_uris == storage.deleted_uris
    assert storage.put_uris and all(not storage.exists(uri) for uri in storage.put_uris)
    assert repository.request_logs == repository.payloads == repository.prices == []


def test_non_bytes_raw_payload_safe_fails_without_blob_write() -> None:
    repository = FakeRepository()
    storage = RecordingBlobStorage()
    adapter = Adapter(_envelope(raw_payload={"reconstructed": "json"}))
    service, _, _ = _service(repository, adapter, storage)
    result = service.ingest(_request(parameters={"case": "non-bytes"}))
    assert result.status == "FAIL"
    assert result.error_code == "PROVIDER_CONTRACT_FAILED"
    assert storage.put_uris == []
    assert repository.payloads == repository.prices == []


def test_corporate_action_projection_uses_only_provider_fields() -> None:
    repository = FakeRepository()
    record = ProviderRecord(
        record_type="corporate_action",
        provider_record_id="action-1",
        source_published_at=NOW,
        data={
            "action_type": "CASH_DIVIDEND",
            "announcement_date": "2026-07-01",
            "ex_date": "2026-07-12",
            "cash_amount": Decimal("0.125000000001"),
            "currency_code": "USD",
            "status": "CONFIRMED",
        },
    )
    adapter = Adapter(_envelope(category=DataCategory.CORPORATE_ACTIONS, records=(record,)))
    service, _, _ = _service(repository, adapter)
    result = service.ingest(_request(category=DataCategory.CORPORATE_ACTIONS))
    assert result.status == "PASS" and result.records_stored == 1
    assert repository.actions[0].cash_amount == Decimal("0.125000000001")
    assert repository.actions[0].provider_action_id == "action-1"


def test_nonempty_financial_fact_projection_preserves_reported_value() -> None:
    repository = FakeRepository()
    record = ProviderRecord(
        record_type="financial_fact",
        provider_record_id="fact-1",
        source_published_at=NOW,
        data={
            "statement_type": "INCOME_STATEMENT",
            "provider_concept": "raw:NetIncomeLoss",
            "reported_label": "Net income (loss)",
            "value": Decimal("-123.000000000001"),
            "unit": "USD",
            "fiscal_year": 2026,
            "period_end": "2026-05-28",
        },
    )
    adapter = Adapter(_envelope(category=DataCategory.FINANCIAL_FACTS, records=(record,)))
    service, _, _ = _service(repository, adapter)
    result = service.ingest(_request(category=DataCategory.FINANCIAL_FACTS))
    assert result.status == "PASS" and result.records_stored == 1
    assert repository.facts[0].value == Decimal("-123.000000000001")
    assert repository.facts[0].dimensions == {}


def test_filing_metadata_projection_requires_and_preserves_source_metadata() -> None:
    repository = FakeRepository()
    record = ProviderRecord(
        record_type="filing_metadata",
        provider_record_id="0001-26-000001",
        source_published_at=NOW,
        data={
            "document_type": "SEC_10_Q",
            "title": "Form 10-Q",
            "form_type": "10-Q",
            "accession_number": "0001-26-000001",
            "period_end": "2026-05-28",
            "filed_at": "2026-06-25T00:00:00Z",
            "source_url": "https://www.sec.gov/Archives/example.htm",
            "document_status": "METADATA_ONLY",
        },
    )
    adapter = Adapter(_envelope(category=DataCategory.FILING_METADATA, records=(record,)))
    service, _, _ = _service(repository, adapter)
    result = service.ingest(_request(category=DataCategory.FILING_METADATA))
    assert result.status == "PASS" and result.records_stored == 1
    assert repository.documents[0].storage_uri is None
    assert repository.documents[0].accession_number == "0001-26-000001"


def test_malformed_filing_record_safe_fails_and_rolls_back_evidence() -> None:
    repository = FakeRepository()
    malformed = ProviderRecord(
        record_type="filing_metadata",
        provider_record_id="0001-26-000002",
        source_published_at=NOW,
        data={
            "document_type": "SEC_10_Q",
            "accession_number": "0001-26-000002",
            "document_status": "METADATA_ONLY",
        },
    )
    storage = RecordingBlobStorage()
    adapter = Adapter(_envelope(category=DataCategory.FILING_METADATA, records=(malformed,)))
    service, _, _ = _service(repository, adapter, storage)
    result = service.ingest(_request(category=DataCategory.FILING_METADATA))
    assert result.status == "FAIL" and result.error_code == "PERSISTENCE_FAILED"
    assert repository.request_logs == repository.payloads == repository.documents == []
    assert storage.put_uris == storage.deleted_uris


def test_invalid_fixture_markers_and_envelope_contract_map_to_safe_fail() -> None:
    repository = FakeRepository()
    invalid = _envelope().model_copy(update={"live_status": LiveStatus.LIVE})
    adapter = Adapter(invalid)
    service, _, _ = _service(repository, adapter)
    result = service.ingest(_request())
    assert result.status == "FAIL" and result.error_code == "PROVIDER_CONTRACT_FAILED"
    assert adapter.fetch_count == 1
    assert repository.payloads == []


def test_unsafe_provider_warning_text_is_redacted_from_result() -> None:
    repository = FakeRepository()
    warning = "token=SECRET /private/provider.sql SELECT *"
    envelope = _envelope(quality=QualityStatus.PARTIAL).model_copy(
        update={
            "warnings": (warning,),
            "quality": DataQuality(
                status=QualityStatus.PARTIAL,
                required_fields_present=1,
                required_fields_total=1,
                warnings=(warning,),
            ),
        }
    )
    adapter = Adapter(envelope)
    service, _, _ = _service(repository, adapter)
    result = service.ingest(_request(parameters={"api_token": "SECRET_PARAMETER"}))
    assert result.status == "PARTIAL"
    assert result.warnings == ("PROVIDER_WARNING_REDACTED",)
    rendered = result.model_dump_json()
    for sentinel in ("SECRET", "/private", "SELECT", "api_token"):
        assert sentinel not in rendered


def test_projection_failure_rolls_back_attempt_compensates_blob_and_never_leaks() -> None:
    repository = FakeRepository()
    repository.fail_price = True
    adapter = Adapter(_envelope(raw_payload=b"SECRET_PAYLOAD"))
    storage = RecordingBlobStorage()
    service, _, _ = _service(repository, adapter, storage)
    result = service.ingest(_request(parameters={"token": "do-not-log"}))
    assert result.status == "FAIL" and result.error_code == "PERSISTENCE_FAILED"
    assert repository.request_logs == repository.payloads == repository.prices == []
    assert result.safe_error_message == "Ingestion persistence failed safely"
    rendered = result.model_dump_json()
    for sentinel in ("SECRET", "postgresql", "/private", " SQL ", "do-not-log"):
        assert sentinel not in rendered
    assert storage.put_uris
    assert storage.put_uris == storage.deleted_uris
    assert all(not storage.exists(uri) for uri in storage.put_uris)


def test_terminal_persistence_failure_rolls_back_category_and_compensates_blob() -> None:
    repository = FakeRepository()
    repository.fail_terminal_pass = True
    adapter = Adapter(_envelope())
    storage = RecordingBlobStorage()
    service, _, _ = _service(repository, adapter, storage)
    result = service.ingest(_request(parameters={"revision": "terminal-failure"}))
    assert result.status == "FAIL" and result.error_code == "PERSISTENCE_FAILED"
    assert repository.request_logs == repository.payloads == repository.prices == []
    assert storage.put_uris
    assert storage.put_uris == storage.deleted_uris
    assert all(not storage.exists(uri) for uri in storage.put_uris)


def test_service_module_has_no_api_cli_session_or_network_imports() -> None:
    source = __import__("inspect").getsource(
        __import__("stock_research_agent.domain.data_access.ingestion", fromlist=["*"])
    )
    for forbidden in ("fastapi", "typer", "sqlalchemy", "sessionmaker", "requests", "httpx"):
        assert forbidden not in source.casefold()
