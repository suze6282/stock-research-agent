"""Deterministic offline SEC EDGAR adapter."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Literal, cast
from uuid import UUID

from pydantic import Field, ValidationError, field_validator, model_validator

from stock_research_agent.domain.providers.artifacts import (
    ProviderBatch,
    ProviderRecord,
    ProviderRecordIdentity,
    ProviderRecordStatus,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
)
from stock_research_agent.domain.providers.sync import (
    ProviderSyncPlanDraft,
    ProviderSyncSlice,
)
from stock_research_agent.providers.sec_edgar.endpoints import build_sec_request
from stock_research_agent.providers.sec_edgar.schemas import (
    AccessionNumber,
    Cik,
    SecArtifactKind,
    SecFilename,
    SecFilingMetadata,
    SecForm,
    normalize_cik,
)

SEC_ADAPTER_VERSION = "1.0.0"
SEC_CATALOG_VERSION = "1.0.0"
_MAX_RANGE_DAYS = 3_660
_MIN_RESPONSE_BUDGET = 1_024
_MAX_RESPONSE_BYTES = 52_428_800


class _SecBoundaryError(ValueError):
    """A validated governance boundary failure, not malformed source syntax."""


class SecEdgarCapability(StrEnum):
    COMPANY_FACTS = "FETCH_SEC_COMPANY_FACTS"
    FILING_DOCUMENTS = "FETCH_SEC_FILING_DOCUMENTS"
    SUBMISSIONS_METADATA = "FETCH_SEC_SUBMISSIONS"


class SecPlannedDocument(FrozenProviderContract):
    accession_number: AccessionNumber
    filed_date: date
    form: SecForm
    document_path: SecFilename


class SecEdgarPlanRequest(FrozenProviderContract):
    sync_request_id: UUID
    security_id: UUID
    capability: SecEdgarCapability
    form_filters: tuple[SecForm, ...] = Field(max_length=32)
    range_start: date
    range_end: date
    research_as_of_time: AwareUtcDateTime
    checkpoint_revision: int | None = Field(default=None, ge=0)
    max_requests: int = Field(ge=0, le=10_000)
    max_bytes: int = Field(ge=0, le=10_737_418_240)
    documents: tuple[SecPlannedDocument, ...] = Field(max_length=10_000)

    @field_validator("form_filters")
    @classmethod
    def validate_form_filters(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("SEC_FORM_FILTERS_MUST_BE_UNIQUE_AND_SORTED")
        return value

    @model_validator(mode="after")
    def validate_finite_range(self) -> SecEdgarPlanRequest:
        if self.range_end < self.range_start:
            raise ValueError("SEC_RANGE_INVALID")
        if self.range_end > self.research_as_of_time.date():
            raise ValueError("SEC_FUTURE_RANGE_FORBIDDEN")
        if (self.range_end - self.range_start).days > _MAX_RANGE_DAYS:
            raise ValueError("SEC_OPEN_ENDED_HISTORY_FORBIDDEN")
        return self


class SecParseContext(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    raw_artifact_id: UUID
    source_checksum: Checksum
    manifest_checksum: Checksum
    source_identity: str = Field(min_length=1, max_length=512)
    source_endpoint_type: Literal[
        "SEC_SUBMISSIONS_JSON",
        "SEC_COMPANY_FACTS_JSON",
        "SEC_FILING_DOCUMENT",
    ]
    artifact_kind: SecArtifactKind
    content_type: str = Field(min_length=1, max_length=64)
    research_as_of_time: AwareUtcDateTime
    retrieved_at: AwareUtcDateTime
    source_published_at: AwareUtcDateTime | None
    expected_accession_number: AccessionNumber | None
    expected_document_path: SecFilename | None
    synthetic_status: ProviderSyntheticStatus

    @model_validator(mode="after")
    def validate_endpoint_kind(self) -> SecParseContext:
        allowed = {
            "SEC_SUBMISSIONS_JSON": {SecArtifactKind.SUBMISSIONS_METADATA},
            "SEC_COMPANY_FACTS_JSON": {SecArtifactKind.COMPANY_FACTS},
            "SEC_FILING_DOCUMENT": {
                SecArtifactKind.FILING_INDEX,
                SecArtifactKind.PRIMARY_FILING_DOCUMENT,
                SecArtifactKind.COMPLETE_SUBMISSION_TEXT,
                SecArtifactKind.XBRL_INSTANCE,
                SecArtifactKind.EXHIBIT,
            },
        }
        if self.artifact_kind not in allowed[self.source_endpoint_type]:
            raise ValueError("SEC_ENDPOINT_ARTIFACT_KIND_MISMATCH")
        if self.source_endpoint_type == "SEC_FILING_DOCUMENT":
            if self.expected_accession_number is None or self.expected_document_path is None:
                raise ValueError("SEC_DOCUMENT_IDENTITY_REQUIRED")
        elif self.expected_accession_number is not None or self.expected_document_path is not None:
            raise ValueError("SEC_METADATA_DOCUMENT_IDENTITY_FORBIDDEN")
        return self


class SecEdgarAdapter:
    """Build finite SEC request plans from explicit governed inputs."""

    def __init__(
        self,
        *,
        security_id: UUID,
        cik: str,
        approved_capabilities: tuple[SecEdgarCapability, ...],
        approved_forms: tuple[str, ...],
    ) -> None:
        if approved_capabilities != tuple(sorted(set(approved_capabilities))):
            raise ValueError("SEC_CAPABILITIES_MUST_BE_UNIQUE_AND_SORTED")
        if approved_forms != tuple(sorted(set(approved_forms))):
            raise ValueError("SEC_FORMS_MUST_BE_UNIQUE_AND_SORTED")
        self._security_id = security_id
        self._cik: Cik = normalize_cik(cik)
        self._approved_capabilities = frozenset(approved_capabilities)
        self._approved_forms = frozenset(approved_forms)

    def plan(self, request: SecEdgarPlanRequest) -> ProviderSyncPlanDraft:
        """Return a stable finite plan without opening a Session or transport."""

        if request.security_id != self._security_id:
            raise ValueError("SEC_SECURITY_SCOPE_MISMATCH")
        if request.capability not in self._approved_capabilities:
            raise ValueError("SEC_CAPABILITY_NOT_APPROVED")
        if not set(request.form_filters) <= self._approved_forms:
            raise ValueError("SEC_FORM_NOT_APPROVED")

        slices = self._build_slices(request)
        if len(slices) > request.max_requests:
            raise ValueError("SEC_REQUEST_BUDGET_EXCEEDED")
        if not slices or request.max_bytes // len(slices) < _MIN_RESPONSE_BUDGET:
            raise ValueError("SEC_BYTE_BUDGET_TOO_SMALL")
        return ProviderSyncPlanDraft(
            sync_request_id=request.sync_request_id,
            adapter_version=SEC_ADAPTER_VERSION,
            catalog_version=SEC_CATALOG_VERSION,
            checkpoint_revision=request.checkpoint_revision,
            slices=self._apply_byte_budget(slices, request.max_bytes),
        )

    def parse_response(self, body: bytes, context: SecParseContext) -> ProviderBatch:
        """Parse bounded already-acquired bytes without transport or persistence."""

        if not body or len(body) > _MAX_RESPONSE_BYTES:
            raise ValueError("SEC_RESPONSE_SIZE_INVALID")
        if hashlib.sha256(body).hexdigest() != context.source_checksum:
            raise ValueError("SEC_RESPONSE_CHECKSUM_MISMATCH")
        if (
            context.source_published_at is not None
            and context.source_published_at > context.research_as_of_time
        ):
            raise ValueError("SEC_FUTURE_DATA")
        if context.source_endpoint_type == "SEC_SUBMISSIONS_JSON":
            records = self._parse_submissions(body, context)
        elif context.source_endpoint_type == "SEC_COMPANY_FACTS_JSON":
            records = self._parse_company_facts(body, context)
        else:
            records = (self._parse_document(body, context),)
        return ProviderBatch(
            manifest_checksum=context.manifest_checksum,
            records=tuple(sorted(records, key=lambda item: item.identity.record_key)),
        )

    def _parse_submissions(
        self,
        body: bytes,
        context: SecParseContext,
    ) -> tuple[ProviderRecord, ...]:
        payload = _load_json_object(body)
        try:
            cik = normalize_cik(str(payload["cik"]))
            if cik != self._cik:
                raise _SecBoundaryError("SEC_CIK_MISMATCH")
            raw_filings = _object_list(payload["filings"])
            records: list[ProviderRecord] = []
            for raw in raw_filings:
                accepted_at = _parse_utc_datetime(raw["acceptanceDateTime"])
                filing = SecFilingMetadata(
                    accession_number=cast(str, raw["accessionNumber"]),
                    form=cast(str, raw["form"]),
                    filed_date=date.fromisoformat(cast(str, raw["filingDate"])),
                    report_date=(
                        date.fromisoformat(cast(str, raw["reportDate"]))
                        if raw.get("reportDate")
                        else None
                    ),
                    accepted_at=accepted_at,
                    primary_document=cast(str, raw["primaryDocument"]),
                )
                if filing.form not in self._approved_forms:
                    raise _SecBoundaryError("SEC_FORM_NOT_APPROVED")
                _reject_future(accepted_at, context)
                records.append(
                    self._record(
                        context,
                        record_key=f"FILING:{filing.accession_number}",
                        source_published_at=accepted_at,
                        numeric_values={},
                        text_values={
                            "accession_number": filing.accession_number,
                            "accepted_at": accepted_at.isoformat().replace("+00:00", "Z"),
                            "evidence_role": "METADATA_ONLY",
                            "filed_date": filing.filed_date.isoformat(),
                            "form": filing.form,
                            "primary_document": filing.primary_document,
                            "report_date": (
                                filing.report_date.isoformat()
                                if filing.report_date is not None
                                else None
                            ),
                        },
                    )
                )
        except _SecBoundaryError:
            raise
        except (KeyError, TypeError, ValueError, ValidationError):
            raise ValueError("SEC_RESPONSE_MALFORMED") from None
        if not records:
            raise ValueError("SEC_RESPONSE_MALFORMED")
        return tuple(records)

    def _parse_company_facts(
        self,
        body: bytes,
        context: SecParseContext,
    ) -> tuple[ProviderRecord, ...]:
        payload = _load_json_object(body)
        try:
            cik = normalize_cik(str(payload["cik"]))
            if cik != self._cik:
                raise _SecBoundaryError("SEC_CIK_MISMATCH")
            taxonomies = _object_mapping(payload["facts"])
            records: list[ProviderRecord] = []
            for taxonomy in sorted(taxonomies):
                concepts = _object_mapping(taxonomies[taxonomy])
                for concept in sorted(concepts):
                    concept_payload = _object_mapping(concepts[concept])
                    units = _object_mapping(concept_payload["units"])
                    for unit in sorted(units):
                        facts = _object_list(units[unit])
                        for index, fact in enumerate(facts):
                            accession = cast(str, fact["accn"])
                            if (
                                context.expected_accession_number is not None
                                and accession != context.expected_accession_number
                            ):
                                raise _SecBoundaryError("SEC_ACCESSION_MISMATCH")
                            numeric_value = _decimal_string(fact["val"])
                            record_key = (
                                f"FACT:{taxonomy}:{concept}:{unit}:{accession}:"
                                f"{cast(str, fact['end'])}:{index:04d}"
                            )
                            records.append(
                                self._record(
                                    context,
                                    record_key=record_key,
                                    source_published_at=context.source_published_at,
                                    numeric_values={"value": numeric_value},
                                    text_values={
                                        "accession_number": accession,
                                        "concept": concept,
                                        "evidence_role": "STRUCTURED_FACT",
                                        "filed_date": cast(str, fact["filed"]),
                                        "fiscal_period": cast(str, fact["fp"]),
                                        "fiscal_year": str(fact["fy"]),
                                        "form": cast(str, fact["form"]),
                                        "period_end": cast(str, fact["end"]),
                                        "period_start": cast(str | None, fact.get("start")),
                                        "taxonomy": taxonomy,
                                        "unit": unit,
                                    },
                                )
                            )
        except _SecBoundaryError:
            raise
        except (KeyError, TypeError, ValueError, ValidationError):
            raise ValueError("SEC_RESPONSE_MALFORMED") from None
        if not records:
            raise ValueError("SEC_RESPONSE_MALFORMED")
        return tuple(records)

    def _parse_document(
        self,
        body: bytes,
        context: SecParseContext,
    ) -> ProviderRecord:
        accession = cast(str, context.expected_accession_number)
        document_path = cast(str, context.expected_document_path)
        expected_identity = f"SEC_FILING_DOCUMENT:{self._cik}:{accession}:{document_path}"
        if context.source_identity != expected_identity:
            raise ValueError("SEC_ACCESSION_IDENTITY_MISMATCH")
        _validate_document_body(body, context.content_type)
        metadata_only = {
            SecArtifactKind.FILING_INDEX,
            SecArtifactKind.XBRL_INSTANCE,
        }
        evidence_role = (
            "METADATA_ONLY" if context.artifact_kind in metadata_only else "COMPANY_BODY"
        )
        return self._record(
            context,
            record_key=f"DOCUMENT:{accession}:{document_path}",
            source_published_at=context.source_published_at,
            numeric_values={},
            text_values={
                "accession_number": accession,
                "artifact_kind": context.artifact_kind.value,
                "content_type": context.content_type,
                "document_path": document_path,
                "evidence_role": evidence_role,
            },
        )

    @staticmethod
    def _record(
        context: SecParseContext,
        *,
        record_key: str,
        source_published_at: AwareUtcDateTime | None,
        numeric_values: dict[str, str | None],
        text_values: dict[str, str | None],
    ) -> ProviderRecord:
        warnings = ("UNKNOWN_PUBLISHED_AT",) if source_published_at is None else ()
        return ProviderRecord(
            identity=ProviderRecordIdentity(
                provider_definition_id=context.provider_definition_id,
                provider_capability_id=context.provider_capability_id,
                source_identity=context.source_identity,
                record_key=record_key,
                revision=1,
            ),
            raw_artifact_id=context.raw_artifact_id,
            source_checksum=context.source_checksum,
            source_published_at=source_published_at,
            status=(ProviderRecordStatus.PARTIAL if warnings else ProviderRecordStatus.COMPLETE),
            numeric_values=numeric_values,
            text_values=text_values,
            warning_codes=warnings,
            synthetic_status=context.synthetic_status,
        )

    def _build_slices(
        self,
        request: SecEdgarPlanRequest,
    ) -> tuple[ProviderSyncSlice, ...]:
        if request.capability is SecEdgarCapability.SUBMISSIONS_METADATA:
            if request.documents:
                raise ValueError("SEC_PLAN_EXPANSION_FORBIDDEN")
            return (
                self._metadata_slice(
                    request,
                    endpoint_id="SEC_SUBMISSIONS_JSON",
                    slice_id="SEC_SUBMISSIONS",
                ),
            )
        if request.capability is SecEdgarCapability.COMPANY_FACTS:
            if request.documents or request.form_filters:
                raise ValueError("SEC_ENDPOINT_ARGUMENTS_INVALID")
            return (
                self._metadata_slice(
                    request,
                    endpoint_id="SEC_COMPANY_FACTS_JSON",
                    slice_id="SEC_COMPANY_FACTS",
                ),
            )
        if not request.documents:
            raise ValueError("SEC_DOCUMENT_PLAN_EMPTY")
        documents = tuple(
            sorted(
                request.documents,
                key=lambda item: (
                    item.filed_date,
                    item.accession_number,
                    item.document_path,
                ),
            )
        )
        identities = tuple((item.accession_number, item.document_path) for item in documents)
        if len(identities) != len(set(identities)):
            raise ValueError("SEC_DOCUMENT_PLAN_DUPLICATE")
        slices: list[ProviderSyncSlice] = []
        for ordinal, document in enumerate(documents):
            self._validate_document(request, document)
            build_sec_request(
                "SEC_FILING_DOCUMENT",
                cik=self._cik,
                accession_number=document.accession_number,
                document_path=document.document_path,
            )
            slices.append(
                ProviderSyncSlice(
                    slice_id=f"SEC_DOCUMENT_{ordinal:04d}",
                    ordinal=ordinal,
                    range_start=document.filed_date,
                    range_end=document.filed_date,
                    request_parameters={
                        "endpoint_id": "SEC_FILING_DOCUMENT",
                        "cik": self._cik,
                        "accession_number": document.accession_number,
                        "document_path": document.document_path,
                        "form": document.form,
                        "max_response_bytes": 1,
                    },
                )
            )
        return tuple(slices)

    def _metadata_slice(
        self,
        request: SecEdgarPlanRequest,
        *,
        endpoint_id: str,
        slice_id: str,
    ) -> ProviderSyncSlice:
        build_sec_request(endpoint_id, cik=self._cik)
        return ProviderSyncSlice(
            slice_id=slice_id,
            ordinal=0,
            range_start=request.range_start,
            range_end=request.range_end,
            request_parameters={
                "endpoint_id": endpoint_id,
                "cik": self._cik,
                "form_filters": request.form_filters,
                "max_response_bytes": 1,
            },
        )

    def _validate_document(
        self,
        request: SecEdgarPlanRequest,
        document: SecPlannedDocument,
    ) -> None:
        if not request.range_start <= document.filed_date <= request.range_end:
            raise ValueError("SEC_DOCUMENT_OUTSIDE_RANGE")
        if document.filed_date > request.research_as_of_time.date():
            raise ValueError("SEC_FUTURE_DOCUMENT_FORBIDDEN")
        if request.form_filters and document.form not in request.form_filters:
            raise ValueError("SEC_DOCUMENT_FORM_FILTERED")
        if document.form not in self._approved_forms:
            raise ValueError("SEC_FORM_NOT_APPROVED")

    @staticmethod
    def _apply_byte_budget(
        slices: tuple[ProviderSyncSlice, ...],
        max_bytes: int,
    ) -> tuple[ProviderSyncSlice, ...]:
        per_response = max_bytes // len(slices)
        return tuple(
            ProviderSyncSlice(
                **(
                    item.model_dump()
                    | {
                        "request_parameters": item.request_parameters
                        | {"max_response_bytes": per_response}
                    }
                )
            )
            for item in slices
        )


def _load_json_object(body: bytes) -> dict[str, object]:
    try:
        decoded = json.loads(
            body,
            parse_float=Decimal,
            parse_int=int,
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("SEC_RESPONSE_MALFORMED") from None
    if not isinstance(decoded, dict):
        raise ValueError("SEC_RESPONSE_MALFORMED")
    return cast(dict[str, object], decoded)


def _object_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("SEC_RESPONSE_MALFORMED")
    return cast(dict[str, object], value)


def _object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("SEC_RESPONSE_MALFORMED")
    return cast(list[dict[str, object]], value)


def _parse_utc_datetime(value: object) -> AwareUtcDateTime:
    if not isinstance(value, str):
        raise ValueError("SEC_RESPONSE_MALFORMED")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("SEC_RESPONSE_MALFORMED")
    return parsed


def _decimal_string(value: object) -> str:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("SEC_NUMERIC_VALUE_INVALID")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("SEC_NUMERIC_VALUE_INVALID") from None
    if not number.is_finite():
        raise ValueError("SEC_NUMERIC_VALUE_INVALID")
    return str(value)


def _reject_future(
    published_at: AwareUtcDateTime,
    context: SecParseContext,
) -> None:
    if published_at > context.research_as_of_time:
        raise _SecBoundaryError("SEC_FUTURE_DATA")


def _validate_document_body(body: bytes, content_type: str) -> None:
    lowered = body[:4_096].lstrip().lower()
    if content_type in {"text/html", "application/xhtml+xml"}:
        if b"<html" not in lowered and b"<!doctype html" not in lowered:
            raise ValueError("SEC_RESPONSE_MALFORMED")
    elif content_type == "application/pdf":
        if not body.startswith(b"%PDF-"):
            raise ValueError("SEC_RESPONSE_MALFORMED")
    elif content_type == "application/json":
        _load_json_object(body)
    elif content_type in {"application/xml", "text/xml"}:
        if not lowered.startswith(b"<"):
            raise ValueError("SEC_RESPONSE_MALFORMED")
    elif content_type == "text/plain":
        try:
            body.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("SEC_RESPONSE_MALFORMED") from None
    else:
        raise ValueError("SEC_CONTENT_TYPE_INVALID")
