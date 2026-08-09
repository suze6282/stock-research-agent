from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from stock_research_agent.domain.data_access.enums import (
    AccessMode,
    DataCategory,
    DataOrigin,
    LiveStatus,
    ProviderCapability,
    ProviderStatus,
    QualityStatus,
)
from stock_research_agent.domain.data_access.repositories import (
    ProviderCatalogRepository,
    ProviderMappingRepository,
)
from stock_research_agent.domain.data_access.schemas import (
    DailyPriceBarWrite,
    DataQuality,
    ExactDecimal,
    ProviderDescriptor,
    ProviderEnvelope,
    ProviderInstrument,
    ProviderRecord,
    ProviderRequest,
    ProviderRequestLogWrite,
)

REQUEST_ID = UUID("00000000-0000-0000-0000-000000000001")
SECURITY_ID = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 7, 14, 4, 0, tzinfo=UTC)


def _instrument() -> ProviderInstrument:
    return ProviderInstrument(
        security_id=SECURITY_ID,
        provider_symbol="MU",
        provider_exchange_code="XNAS",
        provider_instrument_id=None,
    )


def _quality() -> DataQuality:
    return DataQuality(
        status=QualityStatus.PASS,
        required_fields_present=2,
        required_fields_total=2,
    )


def _envelope_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "provider_code": "OFFLINE_FIXTURE",
        "provider_version": "1.0.0",
        "category": DataCategory.DAILY_PRICES,
        "records": (
            ProviderRecord(
                record_type="daily_price",
                provider_record_id="MU-2026-07-13",
                source_published_at=NOW,
                data={"close": "128.42"},
            ),
        ),
        "raw_payload": b"{}",
        "content_type": "application/json",
        "source_endpoint": "fixture://stage-1/mu-latest-daily",
        "provider_request_id": None,
        "retrieved_at": NOW,
        "source_published_at": NOW,
        "warnings": (),
        "quality": _quality(),
        "data_origin": DataOrigin.FIXTURE,
        "access_mode": AccessMode.OFFLINE,
        "live_status": LiveStatus.NOT_LIVE,
    }
    payload.update(overrides)
    return payload


def test_data_access_enums_have_only_the_approved_values() -> None:
    assert {item.value for item in ProviderCapability} == {
        "SECURITY_REFERENCE",
        "DAILY_PRICES",
        "CORPORATE_ACTIONS",
        "FINANCIAL_FACTS",
        "FILING_METADATA",
        "DOCUMENT_DOWNLOAD",
    }
    assert {item.value for item in DataCategory} == {
        "DAILY_PRICES",
        "CORPORATE_ACTIONS",
        "FINANCIAL_FACTS",
        "FILING_METADATA",
        "SOURCE_DOCUMENTS",
    }
    assert {item.value for item in QualityStatus} == {"PASS", "PARTIAL", "BLOCKED", "FAIL"}
    assert {item.value for item in ProviderStatus} == {
        "APPROVED",
        "APPROVED_FOR_PERSONAL_RESEARCH_ONLY",
        "NEEDS_CREDENTIALS",
        "NEEDS_LICENSE_CONFIRMATION",
        "EXPERIMENTAL",
        "NOT_ALLOWED",
    }
    assert {item.value for item in DataOrigin} == {"FIXTURE", "LIVE"}
    assert {item.value for item in AccessMode} == {"OFFLINE", "ONLINE"}
    assert {item.value for item in LiveStatus} == {"NOT_LIVE", "LIVE"}


def test_provider_request_normalizes_aware_as_of_to_utc() -> None:
    local_time = NOW.astimezone(timezone(timedelta(hours=8)))

    request = ProviderRequest(
        request_id=REQUEST_ID,
        instrument=_instrument(),
        category=DataCategory.DAILY_PRICES,
        research_as_of_time=local_time,
    )

    assert request.research_as_of_time == NOW
    assert request.research_as_of_time.tzinfo is UTC


def test_provider_request_rejects_naive_as_of() -> None:
    with pytest.raises(ValidationError, match="timezone aware"):
        ProviderRequest(
            request_id=REQUEST_ID,
            instrument=_instrument(),
            category=DataCategory.DAILY_PRICES,
            research_as_of_time=NOW.replace(tzinfo=None),
        )


def test_provider_request_rejects_end_date_before_start_date() -> None:
    with pytest.raises(ValidationError, match="date_to cannot precede date_from"):
        ProviderRequest(
            request_id=REQUEST_ID,
            instrument=_instrument(),
            category=DataCategory.DAILY_PRICES,
            research_as_of_time=NOW,
            date_from=date(2026, 7, 14),
            date_to=date(2026, 7, 13),
        )


def test_provider_request_parameter_defaults_are_independent() -> None:
    first = ProviderRequest(
        request_id=REQUEST_ID,
        instrument=_instrument(),
        category=DataCategory.DAILY_PRICES,
        research_as_of_time=NOW,
    )
    second = ProviderRequest(
        request_id=UUID("00000000-0000-0000-0000-000000000003"),
        instrument=_instrument(),
        category=DataCategory.DAILY_PRICES,
        research_as_of_time=NOW,
    )

    first.parameters["adjusted"] = False

    assert second.parameters == {}


class _DecimalContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: ExactDecimal


def test_exact_decimal_accepts_exact_input() -> None:
    assert TypeAdapter(ExactDecimal).validate_python("128.42") == Decimal("128.42")
    assert _DecimalContract(value=Decimal("128.42")).value == Decimal("128.42")


def test_exact_decimal_rejects_binary_float_input() -> None:
    with pytest.raises(ValidationError, match="binary float"):
        _DecimalContract(value=128.42)


@pytest.mark.parametrize(
    ("code", "version"),
    [
        ("lowercase", "1.0.0"),
        ("A" * 65, "1.0.0"),
        ("VALID_CODE", "1.0"),
        ("VALID_CODE", "v1.0.0"),
    ],
)
def test_provider_descriptor_validates_code_and_numeric_version(code: str, version: str) -> None:
    with pytest.raises(ValidationError):
        ProviderDescriptor(
            code=code,
            name="Offline fixture",
            version=version,
            status=ProviderStatus.EXPERIMENTAL,
            capabilities=frozenset({ProviderCapability.DAILY_PRICES}),
            is_enabled=True,
            requires_credentials=False,
            credentials_configured=False,
        )


def test_data_quality_enforces_counts_without_a_score() -> None:
    quality = DataQuality(
        status=QualityStatus.PARTIAL,
        required_fields_present=1,
        required_fields_total=2,
        missing_fields=("source_published_at",),
        warnings=("publication time is unknown",),
    )

    assert quality.model_dump(mode="json") == {
        "status": "PARTIAL",
        "required_fields_present": 1,
        "required_fields_total": 2,
        "missing_fields": ["source_published_at"],
        "duplicate_records": 0,
        "conflicting_records": 0,
        "warnings": ["publication time is unknown"],
    }
    assert "score" not in DataQuality.model_fields


@pytest.mark.parametrize(
    ("present", "total", "duplicate_records", "conflicting_records"),
    [(-1, 1, 0, 0), (0, -1, 0, 0), (2, 1, 0, 0), (0, 0, -1, 0), (0, 0, 0, -1)],
)
def test_data_quality_rejects_invalid_counts(
    present: int,
    total: int,
    duplicate_records: int,
    conflicting_records: int,
) -> None:
    with pytest.raises(ValidationError):
        DataQuality(
            status=QualityStatus.FAIL,
            required_fields_present=present,
            required_fields_total=total,
            duplicate_records=duplicate_records,
            conflicting_records=conflicting_records,
        )


def test_provider_record_and_envelope_normalize_aware_timestamps_to_utc() -> None:
    local_time = NOW.astimezone(timezone(timedelta(hours=-4)))
    record = ProviderRecord(
        record_type="daily_price",
        provider_record_id=None,
        source_published_at=local_time,
        data={},
    )

    envelope = ProviderEnvelope.model_validate(
        _envelope_payload(
            records=(record,),
            retrieved_at=local_time,
            source_published_at=local_time,
        )
    )

    assert envelope.records[0].source_published_at == NOW
    assert envelope.records[0].source_published_at is not None
    assert envelope.records[0].source_published_at.tzinfo is UTC
    assert envelope.retrieved_at == NOW
    assert envelope.retrieved_at.tzinfo is UTC
    assert envelope.source_published_at == NOW
    assert envelope.source_published_at.tzinfo is UTC


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("retrieved_at", NOW.replace(tzinfo=None)),
        ("source_published_at", NOW.replace(tzinfo=None)),
    ],
)
def test_provider_envelope_rejects_naive_timestamps(field: str, value: datetime) -> None:
    with pytest.raises(ValidationError, match="timezone aware"):
        ProviderEnvelope.model_validate(_envelope_payload(**{field: value}))


def test_provider_record_rejects_naive_publication_timestamp() -> None:
    with pytest.raises(ValidationError, match="timezone aware"):
        ProviderRecord(
            record_type="daily_price",
            provider_record_id=None,
            source_published_at=NOW.replace(tzinfo=None),
            data={},
        )


@pytest.mark.parametrize(
    ("data_origin", "access_mode", "live_status"),
    [
        (DataOrigin.FIXTURE, AccessMode.ONLINE, LiveStatus.NOT_LIVE),
        (DataOrigin.FIXTURE, AccessMode.OFFLINE, LiveStatus.LIVE),
        (DataOrigin.LIVE, AccessMode.OFFLINE, LiveStatus.LIVE),
        (DataOrigin.LIVE, AccessMode.ONLINE, LiveStatus.NOT_LIVE),
    ],
)
def test_provider_envelope_rejects_inconsistent_origin_markers(
    data_origin: DataOrigin,
    access_mode: AccessMode,
    live_status: LiveStatus,
) -> None:
    with pytest.raises(ValidationError, match="markers"):
        ProviderEnvelope.model_validate(
            _envelope_payload(
                data_origin=data_origin,
                access_mode=access_mode,
                live_status=live_status,
            )
        )


def test_provider_envelope_accepts_live_markers_only_as_a_complete_triple() -> None:
    envelope = ProviderEnvelope.model_validate(
        _envelope_payload(
            data_origin=DataOrigin.LIVE,
            access_mode=AccessMode.ONLINE,
            live_status=LiveStatus.LIVE,
        )
    )

    assert envelope.data_origin is DataOrigin.LIVE
    assert envelope.access_mode is AccessMode.ONLINE
    assert envelope.live_status is LiveStatus.LIVE


def test_data_access_models_are_frozen_and_reject_unknown_fields() -> None:
    instrument = _instrument()

    with pytest.raises(ValidationError):
        instrument.provider_symbol = "OTHER"
    with pytest.raises(ValidationError):
        ProviderInstrument.model_validate({**instrument.model_dump(), "confidence": 0.9})


def test_daily_price_adjustment_preserves_missing_provider_evidence() -> None:
    bar = DailyPriceBarWrite(
        security_id=SECURITY_ID,
        provider_id=UUID("00000000-0000-0000-0000-000000000003"),
        source_payload_id=UUID("00000000-0000-0000-0000-000000000004"),
        provider_symbol="MU",
        trading_date=date(2026, 7, 10),
        close=Decimal("10.25"),
        currency_code="USD",
        retrieved_at=NOW,
    )

    assert bar.adjustment_type is None


def test_request_log_requires_safe_caller_and_provider_request_lineage() -> None:
    log = ProviderRequestLogWrite(
        ingestion_run_id=UUID("00000000-0000-0000-0000-000000000003"),
        provider_id=UUID("00000000-0000-0000-0000-000000000004"),
        caller_request_id=REQUEST_ID,
        provider_request_id="provider-request:123",
        endpoint_name="daily_prices",
        method="GET",
        safe_url="https://fixture.invalid/daily",
        request_started_at=NOW,
        attempt=1,
        cache_status="NOT_APPLICABLE",
    )

    assert log.caller_request_id == REQUEST_ID
    assert log.provider_request_id == "provider-request:123"
    for unsafe in ("token=SECRET", "C:\\private\\payload", "provider/request"):
        with pytest.raises(ValidationError):
            ProviderRequestLogWrite.model_validate(
                log.model_dump() | {"provider_request_id": unsafe}
            )


def test_task_one_repository_ports_expose_only_the_approved_methods() -> None:
    assert ProviderCatalogRepository.__dict__["_is_protocol"] is True
    assert ProviderMappingRepository.__dict__["_is_protocol"] is True
    assert {
        name
        for name, value in ProviderCatalogRepository.__dict__.items()
        if callable(value) and not name.startswith("_")
    } == {"list_providers", "get_provider"}
    assert {
        name
        for name, value in ProviderMappingRepository.__dict__.items()
        if callable(value) and not name.startswith("_")
    } == {"get_active_mapping"}
