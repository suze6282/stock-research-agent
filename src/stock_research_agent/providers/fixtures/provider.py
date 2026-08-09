"""Checksum-verified, offline-only adapters for public synthetic fixtures."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from importlib import resources
from typing import Literal, cast
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from stock_research_agent.domain.common.clock import Clock, SystemClock
from stock_research_agent.domain.data_access.enums import (
    AccessMode,
    DataCategory,
    DataOrigin,
    LiveStatus,
    ProviderCapability,
    ProviderStatus,
    QualityStatus,
)
from stock_research_agent.domain.data_access.schemas import (
    DataQuality,
    ExactDecimal,
    ProviderDescriptor,
    ProviderEnvelope,
    ProviderRecord,
    ProviderRequest,
    PublicSourceUrl,
)
from stock_research_agent.providers.errors import ProviderContractError
from stock_research_agent.providers.registry import ProviderRegistry

_DATA_PACKAGE = "stock_research_agent.providers.fixtures.data"
_FIXTURE_NAMES = frozenset({"test001_sse_public", "tstx_nasdaq_public", "tstx_sec_public"})
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_PAYLOAD_BYTES = 1024 * 1024
_SOURCE_UNKNOWN = "SOURCE_PUBLISHED_AT_UNKNOWN"
_NOT_LIVE = "NOT_LIVE_FIXTURE"


class FixtureResourceError(ProviderContractError):
    """A package fixture failed bounded provenance or shape validation."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class FixtureCapture(_StrictModel):
    date: date
    precision: Literal["DAY"]
    timezone: Literal["Asia/Shanghai"]
    evidence_note: str = Field(min_length=1, max_length=512)


class FixtureChecksum(_StrictModel):
    algorithm: Literal["SHA-256"]
    value: str = Field(pattern=r"^[0-9a-f]{64}$")


class FixtureManifest(_StrictModel):
    fixture_schema_version: Literal["1.0.0"]
    payload_filename: str = Field(pattern=r"^[a-z0-9_]+\.json$", max_length=128)
    provider: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    source_url: PublicSourceUrl | None
    source_endpoint_type: str | None = Field(default=None, min_length=1, max_length=128)
    security: str = Field(min_length=1, max_length=64)
    captured_at: FixtureCapture
    source_published_at: None
    content_type: Literal["application/json"]
    original_response_cropped: Literal[False]
    full_response_bytes_retained: Literal[False]
    crop_rules: tuple[str, ...] = Field(min_length=1, max_length=16)
    payload_byte_size: int = Field(gt=0, le=_MAX_PAYLOAD_BYTES)
    checksum: FixtureChecksum
    authorization_use_restrictions: tuple[str, ...] = Field(min_length=1, max_length=16)
    production_live_qualification: str = Field(min_length=1, max_length=512)
    data_origin: Literal["FIXTURE"]
    access_mode: Literal["OFFLINE"]
    live_status: Literal["NOT_LIVE"]
    synthetic: Literal[True]
    test_only: Literal[True]
    company_evidence: Literal[False]
    live: Literal[False]
    markers: tuple[
        Literal["SYNTHETIC_TEST_ONLY"],
        Literal["NOT_COMPANY_EVIDENCE"],
        Literal["NOT_PROVIDER_DATA"],
        Literal["OFFLINE"],
        Literal["NOT_LIVE"],
    ]

    @model_validator(mode="after")
    def validate_source_and_bounded_text(self) -> FixtureManifest:
        if self.source_url is None and self.source_endpoint_type is None:
            raise ValueError("fixture source must be identified")
        for value in (*self.crop_rules, *self.authorization_use_restrictions):
            if not 1 <= len(value) <= 512:
                raise ValueError("fixture manifest text entries must contain 1..512 characters")
        return self


class _SsePayload(_StrictModel):
    security: Literal["TEST001.SH"]
    provider_symbol: Literal["TEST001"]
    trading_date: date
    observed_row: tuple[int, ExactDecimal, ExactDecimal, ExactDecimal, ExactDecimal, int, int]
    currency_code: Literal["CNY"]
    markers: tuple[
        Literal["SYNTHETIC_TEST_ONLY"],
        Literal["NOT_COMPANY_EVIDENCE"],
        Literal["NOT_PROVIDER_DATA"],
        Literal["OFFLINE"],
        Literal["NOT_LIVE"],
    ]

    @model_validator(mode="after")
    def validate_exact_evidence(self) -> _SsePayload:
        if self.trading_date != date(2026, 1, 15):
            raise ValueError("fixture payload is outside the synthetic public allowlist")
        expected = (
            20260115,
            Decimal("10.00"),
            Decimal("10.50"),
            Decimal("9.50"),
            Decimal("10.25"),
            100000,
            1025000,
        )
        if self.observed_row != expected:
            raise ValueError("fixture payload is outside the synthetic public allowlist")
        return self


class _NasdaqDisplayValues(_StrictModel):
    open: ExactDecimal
    high: ExactDecimal
    low: ExactDecimal
    close: ExactDecimal
    volume: int = Field(ge=0)


class _NasdaqPayload(_StrictModel):
    security: Literal["TSTX"]
    provider_symbol: Literal["TSTX"]
    trading_date: date
    display_values: _NasdaqDisplayValues
    currency_code: Literal["USD"]
    markers: tuple[
        Literal["SYNTHETIC_TEST_ONLY"],
        Literal["NOT_COMPANY_EVIDENCE"],
        Literal["NOT_PROVIDER_DATA"],
        Literal["OFFLINE"],
        Literal["NOT_LIVE"],
    ]

    @model_validator(mode="after")
    def validate_exact_evidence(self) -> _NasdaqPayload:
        if self.trading_date != date(2026, 1, 15):
            raise ValueError("fixture payload is outside the synthetic public allowlist")
        expected = (
            Decimal("20.00"),
            Decimal("21.00"),
            Decimal("19.50"),
            Decimal("20.50"),
            100000,
        )
        actual = (
            self.display_values.open,
            self.display_values.high,
            self.display_values.low,
            self.display_values.close,
            self.display_values.volume,
        )
        if actual != expected:
            raise ValueError("fixture payload is outside the synthetic public allowlist")
        return self


class _SecFiling(_StrictModel):
    form: Literal["10-K", "10-Q", "8-K"]
    filed_date: date
    report_date: date | None
    accession: str


class _SecPayload(_StrictModel):
    issuer: Literal["Example Semiconductor Research Corp."]
    ticker: Literal["TSTX"]
    cik: Literal["0000000000"]
    exchange_label: Literal["Nasdaq"]
    filings: tuple[_SecFiling, _SecFiling, _SecFiling]
    financial_facts: tuple[()]
    fixture_notice: Literal["This synthetic filing exists solely for parser and citation tests."]
    markers: tuple[
        Literal["SYNTHETIC_TEST_ONLY"],
        Literal["NOT_COMPANY_EVIDENCE"],
        Literal["NOT_PROVIDER_DATA"],
        Literal["OFFLINE"],
        Literal["NOT_LIVE"],
    ]

    @model_validator(mode="after")
    def validate_exact_evidence(self) -> _SecPayload:
        expected = (
            ("10-K", date(2026, 1, 10), date(2025, 12, 31), "0000000000-26-000001"),
            ("10-Q", date(2026, 1, 11), date(2025, 9, 30), "0000000000-26-000002"),
            ("8-K", date(2026, 1, 12), None, "0000000000-26-000003"),
        )
        actual = tuple(
            (filing.form, filing.filed_date, filing.report_date, filing.accession)
            for filing in self.filings
        )
        if actual != expected:
            raise ValueError("fixture payload is outside the synthetic public allowlist")
        return self


FixturePayload = _SsePayload | _NasdaqPayload | _SecPayload


@dataclass(frozen=True)
class LoadedFixture:
    manifest: FixtureManifest
    payload_bytes: bytes
    payload: FixturePayload


def load_fixture_resource(fixture_name: str) -> LoadedFixture:
    """Load one allowlisted package fixture after verifying bytes before JSON parsing."""
    if fixture_name not in _FIXTURE_NAMES:
        raise FixtureResourceError("fixture resource is not allowlisted")
    try:
        package = resources.files(_DATA_PACKAGE)
        manifest_bytes = package.joinpath(f"{fixture_name}.manifest.json").read_bytes()
        if not 0 < len(manifest_bytes) <= _MAX_MANIFEST_BYTES:
            raise FixtureResourceError("fixture manifest size is invalid")
        manifest = FixtureManifest.model_validate_json(manifest_bytes)
        expected_filename = f"{fixture_name}.json"
        if manifest.payload_filename != expected_filename:
            raise FixtureResourceError("fixture payload filename is invalid")
        payload_bytes = package.joinpath(expected_filename).read_bytes()
        checksum = hashlib.sha256(payload_bytes).hexdigest()
        if checksum != manifest.checksum.value:
            raise FixtureResourceError("fixture payload checksum mismatch")
        if len(payload_bytes) != manifest.payload_byte_size:
            raise FixtureResourceError("fixture payload size mismatch")
        decoded = json.loads(payload_bytes, parse_float=ExactDecimal, parse_int=int)
        payload = _validate_payload(fixture_name, decoded)
    except FixtureResourceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, TypeError, ValueError):
        raise FixtureResourceError("fixture resource failed safe validation") from None
    return LoadedFixture(manifest=manifest, payload_bytes=payload_bytes, payload=payload)


def _validate_payload(fixture_name: str, decoded: object) -> FixturePayload:
    model: type[_SsePayload] | type[_NasdaqPayload] | type[_SecPayload]
    if fixture_name == "test001_sse_public":
        model = _SsePayload
    elif fixture_name == "tstx_nasdaq_public":
        model = _NasdaqPayload
    else:
        model = _SecPayload
    return model.model_validate(decoded)


class _FixtureProvider:
    code: str
    version = "1.0.0"
    capabilities: frozenset[ProviderCapability]
    descriptor: ProviderDescriptor
    _fixture_name: str
    _symbol: str

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()

    def _validate_request(self, request: ProviderRequest) -> None:
        if request.instrument.provider_symbol != self._symbol:
            raise ProviderContractError("fixture provider symbol is not supported")
        try:
            capability = ProviderCapability(request.category.value)
        except ValueError:
            raise ProviderContractError("fixture provider category is not supported") from None
        if capability not in self.capabilities:
            raise ProviderContractError("fixture provider category is not supported")

    def _envelope(
        self,
        request: ProviderRequest,
        loaded: LoadedFixture,
        records: tuple[ProviderRecord, ...],
        warnings: tuple[str, ...],
        missing_fields: tuple[str, ...],
    ) -> ProviderEnvelope:
        return ProviderEnvelope(
            provider_code=self.code,
            provider_version=self.version,
            category=request.category,
            records=records,
            raw_payload=loaded.payload_bytes,
            content_type=loaded.manifest.content_type,
            source_endpoint=f"fixture://stage1/{loaded.manifest.payload_filename}",
            provider_request_id=None,
            retrieved_at=self._clock.now(),
            source_published_at=None,
            warnings=warnings,
            quality=DataQuality(
                status=QualityStatus.PARTIAL,
                required_fields_present=0 if not records else 1,
                required_fields_total=2,
                missing_fields=missing_fields,
                warnings=warnings,
            ),
            data_origin=DataOrigin.FIXTURE,
            access_mode=AccessMode.OFFLINE,
            live_status=LiveStatus.NOT_LIVE,
        )


def _date_is_visible(request: ProviderRequest, value: date, timezone_name: str) -> bool:
    local_as_of = request.research_as_of_time.astimezone(ZoneInfo(timezone_name)).date()
    if value > local_as_of:
        return False
    if request.date_from is not None and value < request.date_from:
        return False
    return request.date_to is None or value <= request.date_to


class Stage1SseFixtureProvider(_FixtureProvider):
    code = "STAGE1_SSE_FIXTURE"
    capabilities = frozenset({ProviderCapability.DAILY_PRICES})
    descriptor = ProviderDescriptor(
        code=code,
        name="Public synthetic SSE schema fixture",
        version="1.0.0",
        status=ProviderStatus.EXPERIMENTAL,
        capabilities=capabilities,
        is_enabled=True,
        requires_credentials=False,
        credentials_configured=False,
    )
    _fixture_name = "test001_sse_public"
    _symbol = "TEST001"

    def fetch(self, request: ProviderRequest) -> ProviderEnvelope:
        self._validate_request(request)
        loaded = load_fixture_resource(self._fixture_name)
        payload = cast(_SsePayload, loaded.payload)
        records: tuple[ProviderRecord, ...] = ()
        if _date_is_visible(request, payload.trading_date, "Asia/Shanghai"):
            row = payload.observed_row
            records = (
                ProviderRecord(
                    record_type="daily_price",
                    provider_record_id=None,
                    source_published_at=None,
                    data={
                        "trading_date": payload.trading_date.isoformat(),
                        "open": row[1],
                        "high": row[2],
                        "low": row[3],
                        "close": row[4],
                        "volume": row[5],
                        "currency_code": payload.currency_code,
                    },
                ),
            )
        warnings = (
            _SOURCE_UNKNOWN,
            "SYNTHETIC_TEST_ONLY",
            "NOT_PROVIDER_DATA",
            _NOT_LIVE,
            *(("NO_RECORDS_AS_OF",) if not records else ()),
        )
        return self._envelope(request, loaded, records, warnings, ("source_published_at",))


class Stage1NasdaqFixtureProvider(_FixtureProvider):
    code = "STAGE1_NASDAQ_FIXTURE"
    capabilities = frozenset({ProviderCapability.DAILY_PRICES})
    descriptor = ProviderDescriptor(
        code=code,
        name="Public synthetic Nasdaq schema fixture",
        version="1.0.0",
        status=ProviderStatus.EXPERIMENTAL,
        capabilities=capabilities,
        is_enabled=True,
        requires_credentials=False,
        credentials_configured=False,
    )
    _fixture_name = "tstx_nasdaq_public"
    _symbol = "TSTX"

    def fetch(self, request: ProviderRequest) -> ProviderEnvelope:
        self._validate_request(request)
        loaded = load_fixture_resource(self._fixture_name)
        payload = cast(_NasdaqPayload, loaded.payload)
        records: tuple[ProviderRecord, ...] = ()
        if _date_is_visible(request, payload.trading_date, "America/New_York"):
            values = payload.display_values
            records = (
                ProviderRecord(
                    record_type="daily_price",
                    provider_record_id=None,
                    source_published_at=None,
                    data={
                        "trading_date": payload.trading_date.isoformat(),
                        "open": values.open,
                        "high": values.high,
                        "low": values.low,
                        "close": values.close,
                        "volume": values.volume,
                        "currency_code": payload.currency_code,
                    },
                ),
            )
        warnings = (
            _SOURCE_UNKNOWN,
            "SYNTHETIC_TEST_ONLY",
            "NOT_PROVIDER_DATA",
            _NOT_LIVE,
            *(("NO_RECORDS_AS_OF",) if not records else ()),
        )
        return self._envelope(request, loaded, records, warnings, ("source_published_at",))


class Stage1SecFixtureProvider(_FixtureProvider):
    code = "STAGE1_SEC_FIXTURE"
    capabilities = frozenset(
        {ProviderCapability.FILING_METADATA, ProviderCapability.FINANCIAL_FACTS}
    )
    descriptor = ProviderDescriptor(
        code=code,
        name="Public synthetic SEC submissions schema fixture",
        version="1.0.0",
        status=ProviderStatus.EXPERIMENTAL,
        capabilities=capabilities,
        is_enabled=True,
        requires_credentials=False,
        credentials_configured=False,
    )
    _fixture_name = "tstx_sec_public"
    _symbol = "TSTX"

    def fetch(self, request: ProviderRequest) -> ProviderEnvelope:
        self._validate_request(request)
        loaded = load_fixture_resource(self._fixture_name)
        payload = cast(_SecPayload, loaded.payload)
        if request.category is DataCategory.FINANCIAL_FACTS:
            warnings = (_SOURCE_UNKNOWN, "FINANCIAL_FACTS_NOT_PRESERVED", _NOT_LIVE)
            return self._envelope(
                request,
                loaded,
                (),
                warnings,
                ("financial_facts", "source_published_at"),
            )
        if loaded.manifest.source_url is None:
            raise FixtureResourceError("SEC fixture source URL is unavailable")
        document_types = {
            "10-K": "SEC_10_K",
            "10-Q": "SEC_10_Q",
            "8-K": "SEC_8_K",
        }
        records = tuple(
            ProviderRecord(
                record_type="filing_metadata",
                provider_record_id=filing.accession,
                source_published_at=None,
                data={
                    "issuer": payload.issuer,
                    "ticker": payload.ticker,
                    "cik": payload.cik,
                    "exchange_label": payload.exchange_label,
                    "form": filing.form,
                    "filed_date": filing.filed_date.isoformat(),
                    "report_date": (
                        filing.report_date.isoformat() if filing.report_date is not None else None
                    ),
                    "accession": filing.accession,
                    "document_type": document_types[filing.form],
                    "title": f"{payload.issuer} {filing.form} filing metadata",
                    "form_type": filing.form,
                    "accession_number": filing.accession,
                    "period_end": (
                        filing.report_date.isoformat() if filing.report_date is not None else None
                    ),
                    "filed_at": f"{filing.filed_date.isoformat()}T00:00:00Z",
                    "source_url": loaded.manifest.source_url,
                    "mime_type": loaded.manifest.content_type,
                    "document_status": "METADATA_ONLY",
                },
            )
            for filing in payload.filings
            if _date_is_visible(request, filing.filed_date, "America/New_York")
        )
        warnings = (
            _SOURCE_UNKNOWN,
            _NOT_LIVE,
            *(("NO_RECORDS_AS_OF",) if not records else ()),
        )
        return self._envelope(request, loaded, records, warnings, ("source_published_at",))


def create_stage1_fixture_registry(clock: Clock | None = None) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(Stage1SseFixtureProvider(clock=clock))
    registry.register(Stage1NasdaqFixtureProvider(clock=clock))
    registry.register(Stage1SecFixtureProvider(clock=clock))
    return registry
