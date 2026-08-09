"""Internal idempotent ingestion service for immutable provider evidence."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

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
from stock_research_agent.domain.data_access.repositories import DataAccessRepository
from stock_research_agent.domain.data_access.schemas import (
    CorporateActionWrite,
    DailyPriceBarWrite,
    DataProviderRecord,
    IngestionRunRecord,
    IngestionRunUpdate,
    IngestionRunWrite,
    ProviderEnvelope,
    ProviderFinancialFactWrite,
    ProviderInstrument,
    ProviderRequest,
    ProviderRequestLogWrite,
    RawPayloadWrite,
    SourceDocumentWrite,
)
from stock_research_agent.infrastructure.blob_storage import BlobStorage, BlobStorageError
from stock_research_agent.providers.errors import (
    MissingProviderCapabilityError,
    ProviderContractError,
    ProviderCredentialsNotConfiguredError,
    ProviderDisabledError,
    ProviderNotAllowedError,
    ProviderNotFoundError,
    ProviderRegistryError,
)
from stock_research_agent.providers.registry import ProviderRegistry

_IDEMPOTENCY_VERSION = "ingestion-request-v1"
_PARSER_VERSION_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_TERMINAL = frozenset({"PASS", "PARTIAL", "BLOCKED", "FAIL", "CANCELLED"})
_SAFE_WARNING_PATTERN = re.compile(r"[A-Z][A-Z0-9_:-]{0,127}\Z")


class IngestionContractModel(BaseModel):
    """Strict boundary contract for ingestion orchestration inputs and outputs."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )


class IngestionErrorCode(StrEnum):
    """Closed, safe vocabulary exposed by ingestion results."""

    PROVIDER_NOT_FOUND = "PROVIDER_NOT_FOUND"
    MAPPING_NOT_ACTIVE = "MAPPING_NOT_ACTIVE"
    PROVIDER_NOT_ALLOWED = "PROVIDER_NOT_ALLOWED"
    PROVIDER_DISABLED = "PROVIDER_DISABLED"
    PROVIDER_CREDENTIALS_BLOCKED = "PROVIDER_CREDENTIALS_BLOCKED"
    PROVIDER_LICENSE_BLOCKED = "PROVIDER_LICENSE_BLOCKED"
    PROVIDER_CAPABILITY_MISMATCH = "PROVIDER_CAPABILITY_MISMATCH"
    PROVIDER_METADATA_MISMATCH = "PROVIDER_METADATA_MISMATCH"
    PROVIDER_BLOCKED = "PROVIDER_BLOCKED"
    PROVIDER_CONTRACT_FAILED = "PROVIDER_CONTRACT_FAILED"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"


class IngestionRequest(IngestionContractModel):
    """Provider-neutral request identity and explicit lineage versions."""

    request_id: UUID
    security_id: UUID
    provider_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    category: DataCategory
    research_as_of_time: datetime
    date_from: date | None = None
    date_to: date | None = None
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    parser_version: str = Field(pattern=_PARSER_VERSION_PATTERN)
    schema_version: str = Field(pattern=_PARSER_VERSION_PATTERN)

    @field_validator("research_as_of_time")
    @classmethod
    def normalize_research_as_of(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("research_as_of_time must be timezone aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_date_range(self) -> IngestionRequest:
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_to < self.date_from
        ):
            raise ValueError("date_to cannot precede date_from")
        return self


class IngestionResult(IngestionContractModel):
    """Safe ingestion outcome containing metadata but never provider payload data."""

    run_id: UUID | None
    status: Literal["QUEUED", "RUNNING", "PASS", "PARTIAL", "BLOCKED", "FAIL", "CANCELLED"]
    idempotency_key: str
    request_count: int = Field(ge=0)
    records_received: int = Field(ge=0)
    records_stored: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    warnings: tuple[str, ...] = ()
    data_origin: DataOrigin | None = None
    access_mode: AccessMode | None = None
    live_status: LiveStatus | None = None
    error_code: IngestionErrorCode | None = None
    safe_error_message: str | None = Field(default=None, max_length=512)


def compute_ingestion_idempotency_key(
    request: IngestionRequest,
    *,
    provider_version: str | None = None,
) -> str:
    """Hash a canonical, explicitly versioned semantic request identity."""
    identity = {
        "category": request.category.value,
        "date_from": request.date_from.isoformat() if request.date_from is not None else None,
        "date_to": request.date_to.isoformat() if request.date_to is not None else None,
        "parameters": request.parameters,
        "parser_version": request.parser_version,
        "provider_code": request.provider_code,
        "provider_version": provider_version,
        "research_as_of_time": request.research_as_of_time.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "schema_version": request.schema_version,
        "security_id": str(request.security_id),
        "version": _IDEMPOTENCY_VERSION,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"ingest:v1:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


class IngestionService:
    """Compose injected ports without owning their outer transaction or lifecycle."""

    def __init__(
        self,
        repository: DataAccessRepository,
        registry: ProviderRegistry,
        blob_storage: BlobStorage,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._blob_storage = blob_storage
        self._clock = clock or SystemClock()

    def ingest(self, request: IngestionRequest) -> IngestionResult:
        initial_key = compute_ingestion_idempotency_key(request)
        try:
            provider = self._repository.get_provider(request.provider_code)
        except Exception:
            return self._safe_persistence_failure(initial_key)
        if provider is None:
            return self._prerun_blocked(
                initial_key,
                IngestionErrorCode.PROVIDER_NOT_FOUND,
                "Provider is not configured",
            )

        try:
            descriptor = self._registry.describe(request.provider_code)
            provider_version = descriptor.version
        except ProviderNotFoundError:
            key = initial_key
            return self._blocked_run(
                request,
                provider,
                key,
                IngestionErrorCode.PROVIDER_NOT_FOUND,
                "Provider adapter is not registered",
            )

        key = compute_ingestion_idempotency_key(request, provider_version=provider_version)
        try:
            existing = self._repository.get_ingestion_run_by_idempotency_key(key)
        except Exception:
            return self._safe_persistence_failure(key)
        if existing is not None:
            return self._from_run(existing, provider=provider)

        try:
            run, created = self._repository.get_or_create_ingestion_run(
                IngestionRunWrite(
                    provider_id=provider.id,
                    security_id=request.security_id,
                    category=request.category,
                    research_as_of_time=request.research_as_of_time,
                    idempotency_key=key,
                    requested_at=self._clock.now(),
                )
            )
        except Exception:
            return self._safe_persistence_failure(key)
        if not created:
            return self._from_run(run, provider=provider)
        try:
            run = self._repository.update_ingestion_run(
                run.id, IngestionRunUpdate(status="RUNNING", started_at=self._clock.now())
            )
        except Exception:
            return self._safe_persistence_failure(key, run=run)

        try:
            mapping = self._repository.get_active_mapping(
                request.security_id, request.provider_code, request.research_as_of_time.date()
            )
        except Exception:
            return self._finish_failed(
                run,
                IngestionErrorCode.PERSISTENCE_FAILED,
                "Ingestion persistence failed safely",
            )
        if mapping is None:
            return self._finish_blocked(
                run,
                IngestionErrorCode.MAPPING_NOT_ACTIVE,
                "Provider mapping is not active",
            )

        policy_error = self._persisted_policy_error(provider)
        if policy_error is not None:
            return self._finish_blocked(run, *policy_error)

        capability = self._capability_for(request.category)
        if capability not in provider.capabilities:
            return self._finish_blocked(
                run,
                IngestionErrorCode.PROVIDER_METADATA_MISMATCH,
                "Persisted provider metadata is incompatible with the request",
            )
        descriptor_policy_error = self._descriptor_policy_error(descriptor.status)
        if descriptor_policy_error is not None:
            return self._finish_blocked(run, *descriptor_policy_error)
        try:
            adapter = self._registry.get(request.provider_code, required_capability=capability)
        except ProviderRegistryError as error:
            code, message = self._registry_error(error)
            return self._finish_blocked(run, code, message)
        if (
            adapter.code != provider.code
            or adapter.version != descriptor.version
            or descriptor.status is not provider.status
            or set(adapter.capabilities) != set(descriptor.capabilities)
            or set(descriptor.capabilities) != set(provider.capabilities)
        ):
            return self._finish_blocked(
                run,
                IngestionErrorCode.PROVIDER_METADATA_MISMATCH,
                "Provider adapter metadata is incompatible with persisted metadata",
            )
        if provider.provider_type != "FIXTURE":
            return self._finish_blocked(
                run,
                IngestionErrorCode.PROVIDER_METADATA_MISMATCH,
                "Provider mode is not approved for ingestion",
            )

        provider_request = ProviderRequest(
            request_id=request.request_id,
            instrument=mapping,
            category=request.category,
            research_as_of_time=request.research_as_of_time,
            date_from=request.date_from,
            date_to=request.date_to,
            parameters=request.parameters,
        )
        request_started_at = self._clock.now()
        try:
            envelope = adapter.fetch(provider_request)
            response_received_at = self._clock.now()
            self._validate_envelope(envelope, request, provider, adapter.code, adapter.version)
        except Exception:
            return self._finish_fetch_failure(
                run, provider, request, request_started_at, self._clock.now()
            )

        try:
            raw_bytes = self._raw_bytes(envelope.raw_payload)
        except ProviderContractError:
            return self._finish_fetch_failure(
                run, provider, request, request_started_at, response_received_at
            )
        checksum = hashlib.sha256(raw_bytes).hexdigest()
        byte_size = len(raw_bytes)
        warnings = self._safe_warnings(envelope)
        status = self._quality_status(envelope.quality.status)
        error_code = None
        safe_message = None
        if status == "BLOCKED":
            error_code, safe_message = (
                IngestionErrorCode.PROVIDER_BLOCKED,
                "Provider returned blocked evidence",
            )
        elif status == "FAIL":
            error_code, safe_message = (
                IngestionErrorCode.PROVIDER_CONTRACT_FAILED,
                "Provider evidence failed quality checks",
            )
        blob_uri: str | None = None
        try:
            blob = self._blob_storage.put(
                raw_bytes,
                content_type=envelope.content_type,
                metadata={
                    "category": request.category.value,
                    "provider": provider.code,
                    "run_id": str(run.id),
                },
            )
            blob_uri = blob.uri
            if blob.checksum_sha256 != checksum or blob.size_bytes != byte_size:
                raise BlobStorageError("blob metadata did not match locally computed evidence")
            with self._repository.ingestion_attempt():
                stored = self._persist_attempt(
                    run=run,
                    provider=provider,
                    mapping=mapping,
                    request=request,
                    envelope=envelope,
                    request_started_at=request_started_at,
                    response_received_at=response_received_at,
                    blob_uri=blob.uri,
                    checksum=checksum,
                    byte_size=byte_size,
                )
                completed = self._repository.update_ingestion_run(
                    run.id,
                    IngestionRunUpdate(
                        status=status,
                        completed_at=self._clock.now(),
                        request_count=1,
                        records_received=len(envelope.records),
                        records_stored=stored,
                        warning_count=len(warnings),
                        error_code=error_code,
                        safe_error_message=safe_message,
                    ),
                )
        except Exception:
            if blob_uri is not None:
                try:
                    self._blob_storage.delete(blob_uri)
                except BlobStorageError:
                    pass
            return self._finish_failed(
                run,
                IngestionErrorCode.PERSISTENCE_FAILED,
                "Ingestion persistence failed safely",
            )

        return self._from_run(completed, warnings=warnings, envelope=envelope)

    def _persist_attempt(
        self,
        *,
        run: IngestionRunRecord,
        provider: DataProviderRecord,
        mapping: ProviderInstrument,
        request: IngestionRequest,
        envelope: ProviderEnvelope,
        request_started_at: datetime,
        response_received_at: datetime,
        blob_uri: str,
        checksum: str,
        byte_size: int,
    ) -> int:
        with self._repository.ingestion_attempt():
            request_log = self._repository.add_request_log(
                ProviderRequestLogWrite(
                    ingestion_run_id=run.id,
                    provider_id=provider.id,
                    caller_request_id=request.request_id,
                    provider_request_id=envelope.provider_request_id,
                    endpoint_name=request.category.value.casefold(),
                    method="GET",
                    safe_url=self._safe_url(provider),
                    request_started_at=request_started_at,
                    response_received_at=response_received_at,
                    http_status=None,
                    attempt=1,
                    cache_status="NOT_APPLICABLE",
                    response_size=byte_size,
                )
            )
            payload = self._repository.add_raw_payload(
                RawPayloadWrite(
                    ingestion_run_id=run.id,
                    provider_request_log_id=request_log.id,
                    provider_id=provider.id,
                    security_id=request.security_id,
                    category=request.category,
                    content_type=envelope.content_type,
                    storage_uri=blob_uri,
                    checksum=checksum,
                    source_published_at=envelope.source_published_at,
                    retrieved_at=envelope.retrieved_at,
                    provider_version=envelope.provider_version,
                    parser_version=request.parser_version,
                    schema_version=request.schema_version,
                    byte_size=byte_size,
                )
            )
            if envelope.quality.status in {QualityStatus.BLOCKED, QualityStatus.FAIL}:
                return 0
            if request.category is DataCategory.DAILY_PRICES:
                for record in envelope.records:
                    if record.record_type != "daily_price":
                        raise ProviderContractError("daily price record type is invalid")
                    data = record.data
                    self._repository.add_daily_price_bar(
                        DailyPriceBarWrite(
                            security_id=request.security_id,
                            provider_id=provider.id,
                            source_payload_id=payload.id,
                            provider_symbol=mapping.provider_symbol,
                            trading_date=date.fromisoformat(cast(str, data["trading_date"])),
                            open=cast(Decimal | None, data.get("open")),
                            high=cast(Decimal | None, data.get("high")),
                            low=cast(Decimal | None, data.get("low")),
                            close=cast(Decimal | None, data.get("close")),
                            volume=cast(int | None, data.get("volume")),
                            currency_code=cast(str, data["currency_code"]),
                            source_published_at=record.source_published_at,
                            retrieved_at=envelope.retrieved_at,
                        )
                    )
                return len(envelope.records)
            if request.category is DataCategory.FINANCIAL_FACTS and not envelope.records:
                return 0
            if request.category is DataCategory.CORPORATE_ACTIONS:
                for record in envelope.records:
                    if record.record_type != "corporate_action":
                        raise ProviderContractError("corporate action record type is invalid")
                    values: dict[str, object] = {
                        "security_id": request.security_id,
                        "provider_id": provider.id,
                        "source_payload_id": payload.id,
                        "provider_action_id": record.provider_record_id,
                        "source_published_at": record.source_published_at,
                        "retrieved_at": envelope.retrieved_at,
                    }
                    values.update(
                        self._selected_data(
                            record.data,
                            {
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
                            },
                        )
                    )
                    self._repository.add_corporate_action(
                        CorporateActionWrite.model_validate(values)
                    )
                return len(envelope.records)
            if request.category is DataCategory.FINANCIAL_FACTS:
                for record in envelope.records:
                    if record.record_type != "financial_fact":
                        raise ProviderContractError("financial fact record type is invalid")
                    values = {
                        "security_id": request.security_id,
                        "provider_id": provider.id,
                        "source_payload_id": payload.id,
                        "provider_record_id": record.provider_record_id,
                        "source_published_at": record.source_published_at,
                        "retrieved_at": envelope.retrieved_at,
                    }
                    values.update(
                        self._selected_data(
                            record.data,
                            {
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
                                "form_type",
                                "is_annual",
                                "is_cumulative",
                                "is_audited",
                                "is_restated",
                            },
                        )
                    )
                    self._repository.add_financial_fact(
                        ProviderFinancialFactWrite.model_validate(values)
                    )
                return len(envelope.records)
            if request.category is DataCategory.FILING_METADATA:
                stored = 0
                for record in envelope.records:
                    if record.record_type != "filing_metadata":
                        raise ProviderContractError("filing metadata record type is invalid")
                    required = {"document_type", "title", "source_url", "document_status"}
                    if not required.issubset(record.data):
                        raise ProviderContractError("filing metadata record is incomplete")
                    values = {
                        "security_id": request.security_id,
                        "provider_id": provider.id,
                        "source_payload_id": payload.id,
                        "provider_document_id": record.provider_record_id,
                        "published_at": record.source_published_at,
                        "retrieved_at": envelope.retrieved_at,
                    }
                    values.update(
                        self._selected_data(
                            record.data,
                            {
                                "document_type",
                                "title",
                                "form_type",
                                "accession_number",
                                "announcement_id",
                                "period_end",
                                "filed_at",
                                "source_url",
                                "primary_document_name",
                                "mime_type",
                                "document_status",
                            },
                        )
                    )
                    self._repository.add_source_document(SourceDocumentWrite.model_validate(values))
                    stored += 1
                return stored
            if envelope.records:
                raise ProviderContractError("category projection is not implemented")
            return 0

    def _finish_fetch_failure(
        self,
        run: IngestionRunRecord,
        provider: DataProviderRecord,
        request: IngestionRequest,
        started: datetime,
        completed: datetime,
    ) -> IngestionResult:
        try:
            with self._repository.ingestion_attempt():
                self._repository.add_request_log(
                    ProviderRequestLogWrite(
                        ingestion_run_id=run.id,
                        provider_id=provider.id,
                        caller_request_id=request.request_id,
                        endpoint_name=request.category.value.casefold(),
                        method="GET",
                        safe_url=self._safe_url(provider),
                        request_started_at=started,
                        response_received_at=completed,
                        attempt=1,
                        cache_status="NOT_APPLICABLE",
                        error_code="PROVIDER_CONTRACT_FAILED",
                    )
                )
        except Exception:
            pass
        return self._finish_failed(
            run,
            IngestionErrorCode.PROVIDER_CONTRACT_FAILED,
            "Provider response failed safe validation",
        )

    def _blocked_run(
        self,
        request: IngestionRequest,
        provider: DataProviderRecord,
        key: str,
        code: IngestionErrorCode,
        message: str,
    ) -> IngestionResult:
        try:
            run, created = self._repository.get_or_create_ingestion_run(
                IngestionRunWrite(
                    provider_id=provider.id,
                    security_id=request.security_id,
                    category=request.category,
                    research_as_of_time=request.research_as_of_time,
                    idempotency_key=key,
                    requested_at=self._clock.now(),
                )
            )
        except Exception:
            return self._safe_persistence_failure(key)
        if not created:
            return self._from_run(run)
        try:
            running = self._repository.update_ingestion_run(
                run.id, IngestionRunUpdate(status="RUNNING", started_at=self._clock.now())
            )
        except Exception:
            return self._safe_persistence_failure(key, run=run)
        return self._finish_blocked(running, code, message)

    def _finish_blocked(
        self, run: IngestionRunRecord, code: IngestionErrorCode, message: str
    ) -> IngestionResult:
        try:
            completed = self._repository.update_ingestion_run(
                run.id,
                IngestionRunUpdate(
                    status="BLOCKED",
                    completed_at=self._clock.now(),
                    error_code=code,
                    safe_error_message=message,
                ),
            )
        except Exception:
            return self._safe_persistence_failure(run.idempotency_key, run=run)
        return self._from_run(completed)

    def _finish_failed(
        self, run: IngestionRunRecord, code: IngestionErrorCode, message: str
    ) -> IngestionResult:
        try:
            completed = self._repository.update_ingestion_run(
                run.id,
                IngestionRunUpdate(
                    status="FAIL",
                    completed_at=self._clock.now(),
                    request_count=1,
                    error_code=code,
                    safe_error_message=message,
                ),
            )
        except Exception:
            return self._safe_persistence_failure(run.idempotency_key, run=run)
        return self._from_run(completed)

    @staticmethod
    def _safe_persistence_failure(
        key: str, *, run: IngestionRunRecord | None = None
    ) -> IngestionResult:
        return IngestionResult(
            run_id=run.id if run is not None else None,
            status="FAIL",
            idempotency_key=key,
            request_count=run.request_count if run is not None else 0,
            records_received=run.records_received if run is not None else 0,
            records_stored=run.records_stored if run is not None else 0,
            warning_count=run.warning_count if run is not None else 0,
            error_code=IngestionErrorCode.PERSISTENCE_FAILED,
            safe_error_message="Ingestion persistence failed safely",
        )

    @staticmethod
    def _validate_envelope(
        envelope: ProviderEnvelope,
        request: IngestionRequest,
        provider: DataProviderRecord,
        adapter_code: str,
        adapter_version: str,
    ) -> None:
        fixture = (DataOrigin.FIXTURE, AccessMode.OFFLINE, LiveStatus.NOT_LIVE)
        live = (DataOrigin.LIVE, AccessMode.ONLINE, LiveStatus.LIVE)
        markers = (envelope.data_origin, envelope.access_mode, envelope.live_status)
        if markers not in {fixture, live}:
            raise ProviderContractError("provider origin markers are inconsistent")
        if provider.provider_type == "FIXTURE" and markers != fixture:
            raise ProviderContractError("fixture provider origin markers are incompatible")
        if (
            envelope.provider_code != adapter_code
            or envelope.provider_version != adapter_version
            or envelope.category is not request.category
        ):
            raise ProviderContractError("provider envelope metadata is incompatible")

    @staticmethod
    def _raw_bytes(value: bytes | dict[str, JsonValue] | list[JsonValue]) -> bytes:
        if isinstance(value, bytes):
            return value
        raise ProviderContractError("provider raw payload must be exact bytes")

    @staticmethod
    def _selected_data(
        data: dict[str, JsonValue | Decimal], allowed: set[str]
    ) -> dict[str, object]:
        return {name: value for name, value in data.items() if name in allowed}

    @staticmethod
    def _safe_warnings(envelope: ProviderEnvelope) -> tuple[str, ...]:
        safe = (
            warning if _SAFE_WARNING_PATTERN.fullmatch(warning) else "PROVIDER_WARNING_REDACTED"
            for warning in (*envelope.warnings, *envelope.quality.warnings)
        )
        return tuple(dict.fromkeys(safe))

    @staticmethod
    def _safe_url(provider: DataProviderRecord) -> str:
        return (
            provider.base_url
            or provider.documentation_url
            or (f"https://fixtures.stock-research-agent.invalid/{provider.code.casefold()}")
        )

    @staticmethod
    def _capability_for(category: DataCategory) -> ProviderCapability:
        if category is DataCategory.SOURCE_DOCUMENTS:
            return ProviderCapability.DOCUMENT_DOWNLOAD
        return ProviderCapability(category.value)

    @staticmethod
    def _persisted_policy_error(
        provider: DataProviderRecord,
    ) -> tuple[IngestionErrorCode, str] | None:
        mapping = {
            ProviderStatus.NOT_ALLOWED: (
                IngestionErrorCode.PROVIDER_NOT_ALLOWED,
                "Provider is not allowed",
            ),
            ProviderStatus.NEEDS_CREDENTIALS: (
                IngestionErrorCode.PROVIDER_CREDENTIALS_BLOCKED,
                "Provider credentials are not configured",
            ),
            ProviderStatus.NEEDS_LICENSE_CONFIRMATION: (
                IngestionErrorCode.PROVIDER_LICENSE_BLOCKED,
                "Provider license requires confirmation",
            ),
        }
        return mapping.get(provider.status)

    @staticmethod
    def _descriptor_policy_error(
        status: ProviderStatus,
    ) -> tuple[IngestionErrorCode, str] | None:
        mapping = {
            ProviderStatus.NOT_ALLOWED: (
                IngestionErrorCode.PROVIDER_NOT_ALLOWED,
                "Provider adapter is not allowed",
            ),
            ProviderStatus.NEEDS_CREDENTIALS: (
                IngestionErrorCode.PROVIDER_CREDENTIALS_BLOCKED,
                "Provider credentials are not configured",
            ),
            ProviderStatus.NEEDS_LICENSE_CONFIRMATION: (
                IngestionErrorCode.PROVIDER_LICENSE_BLOCKED,
                "Provider license requires confirmation",
            ),
        }
        return mapping.get(status)

    @staticmethod
    def _registry_error(error: ProviderRegistryError) -> tuple[IngestionErrorCode, str]:
        if isinstance(error, ProviderDisabledError):
            return IngestionErrorCode.PROVIDER_DISABLED, "Provider adapter is disabled"
        if isinstance(error, ProviderNotAllowedError):
            return IngestionErrorCode.PROVIDER_NOT_ALLOWED, "Provider adapter is not allowed"
        if isinstance(error, ProviderCredentialsNotConfiguredError):
            return (
                IngestionErrorCode.PROVIDER_CREDENTIALS_BLOCKED,
                "Provider credentials are not configured",
            )
        if isinstance(error, MissingProviderCapabilityError):
            return (
                IngestionErrorCode.PROVIDER_CAPABILITY_MISMATCH,
                "Provider capability is not available",
            )
        return IngestionErrorCode.PROVIDER_NOT_FOUND, "Provider adapter is not registered"

    @staticmethod
    def _quality_status(status: QualityStatus) -> Literal["PASS", "PARTIAL", "BLOCKED", "FAIL"]:
        return status.value

    @staticmethod
    def _prerun_blocked(key: str, code: IngestionErrorCode, message: str) -> IngestionResult:
        return IngestionResult(
            run_id=None,
            status="BLOCKED",
            idempotency_key=key,
            request_count=0,
            records_received=0,
            records_stored=0,
            warning_count=0,
            error_code=code,
            safe_error_message=message,
        )

    @staticmethod
    def _from_run(
        run: IngestionRunRecord,
        *,
        warnings: tuple[str, ...] = (),
        envelope: ProviderEnvelope | None = None,
        provider: DataProviderRecord | None = None,
    ) -> IngestionResult:
        fixture = envelope is None and provider is not None and provider.provider_type == "FIXTURE"
        if not warnings and run.warning_count > 0:
            warnings = ("PREVIOUS_INGESTION_COMPLETED_WITH_WARNINGS",)
        error_code = IngestionErrorCode(run.error_code) if run.error_code is not None else None
        return IngestionResult(
            run_id=run.id,
            status=run.status,
            idempotency_key=run.idempotency_key,
            request_count=run.request_count,
            records_received=run.records_received,
            records_stored=run.records_stored,
            warning_count=run.warning_count,
            warnings=warnings,
            data_origin=(
                envelope.data_origin
                if envelope is not None
                else DataOrigin.FIXTURE
                if fixture
                else None
            ),
            access_mode=(
                envelope.access_mode
                if envelope is not None
                else AccessMode.OFFLINE
                if fixture
                else None
            ),
            live_status=(
                envelope.live_status
                if envelope is not None
                else LiveStatus.NOT_LIVE
                if fixture
                else None
            ),
            error_code=error_code,
            safe_error_message=run.safe_error_message,
        )


__all__ = [
    "IngestionErrorCode",
    "IngestionRequest",
    "IngestionResult",
    "IngestionService",
    "compute_ingestion_idempotency_key",
]
