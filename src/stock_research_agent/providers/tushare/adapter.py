"""Offline-only Tushare adapter."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Literal, cast
from uuid import UUID

from pydantic import Field, model_validator

from stock_research_agent.domain.providers.artifacts import (
    ProviderBatch,
    ProviderRecord,
    ProviderRecordIdentity,
    ProviderRecordStatus,
)
from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderCredentialStatus,
    ProviderLicenseStatus,
    ProviderLiveAuthorizationStatus,
    ProviderLiveValidationStatus,
    ProviderProductionStatus,
    ProviderSyntheticStatus,
)
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
    SemanticVersion,
)
from stock_research_agent.domain.providers.sync import (
    ProviderSyncPlanDraft,
    ProviderSyncSlice,
)
from stock_research_agent.providers.tushare.schemas import (
    TushareEndpoint,
    TushareOfflineResponse,
)

_MAX_RANGE_DAYS = 366
_SLICE_DAYS = 31
_CAPABILITY_ENDPOINTS = {
    "FETCH_SECURITY_MASTER": frozenset({TushareEndpoint.STOCK_BASIC}),
    "FETCH_MARKET_CALENDAR": frozenset({TushareEndpoint.TRADE_CAL}),
    "FETCH_EOD_PRICES": frozenset({TushareEndpoint.DAILY}),
    "FETCH_FINANCIAL_STATEMENTS": frozenset(
        {
            TushareEndpoint.BALANCE_SHEET,
            TushareEndpoint.CASH_FLOW,
            TushareEndpoint.INCOME,
        }
    ),
    "FETCH_FINANCIAL_METRICS": frozenset({TushareEndpoint.FINA_INDICATOR}),
    "FETCH_CORPORATE_ACTIONS": frozenset({TushareEndpoint.DIVIDEND}),
    "FETCH_DISCLOSURE_METADATA": frozenset({TushareEndpoint.DISCLOSURE_DATE}),
}
_ENDPOINT_FIELDS = {
    TushareEndpoint.DAILY: frozenset(
        {
            "amount",
            "change",
            "close",
            "high",
            "low",
            "open",
            "pct_chg",
            "pre_close",
            "trade_date",
            "ts_code",
            "vol",
        }
    ),
    TushareEndpoint.STOCK_BASIC: frozenset(
        {"area", "industry", "list_date", "list_status", "market", "name", "symbol", "ts_code"}
    ),
    TushareEndpoint.TRADE_CAL: frozenset({"cal_date", "exchange", "is_open", "pretrade_date"}),
    TushareEndpoint.INCOME: frozenset(
        {
            "actual_ann_date",
            "ann_date",
            "end_date",
            "f_ann_date",
            "report_type",
            "revenue",
            "total_profit",
            "ts_code",
            "update_flag",
        }
    ),
    TushareEndpoint.BALANCE_SHEET: frozenset(
        {
            "actual_ann_date",
            "ann_date",
            "end_date",
            "f_ann_date",
            "report_type",
            "total_assets",
            "total_liab",
            "ts_code",
            "update_flag",
        }
    ),
    TushareEndpoint.CASH_FLOW: frozenset(
        {
            "actual_ann_date",
            "ann_date",
            "end_date",
            "f_ann_date",
            "n_cashflow_act",
            "report_type",
            "ts_code",
            "update_flag",
        }
    ),
    TushareEndpoint.FINA_INDICATOR: frozenset(
        {"ann_date", "end_date", "roe", "ts_code", "update_flag"}
    ),
    TushareEndpoint.DIVIDEND: frozenset(
        {"ann_date", "cash_div", "div_proc", "end_date", "ex_date", "ts_code"}
    ),
    TushareEndpoint.DISCLOSURE_DATE: frozenset(
        {"actual_date", "ann_date", "end_date", "modify_date", "pre_date", "ts_code"}
    ),
}


class TushareSyncMode(StrEnum):
    OFFLINE_CONTRACT = "OFFLINE_CONTRACT"
    LIVE = "LIVE"


class TushareEntitlementStatus(StrEnum):
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class TusharePlanStatus(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


class TusharePlanBudget(FrozenProviderContract):
    max_requests: int = Field(ge=1, le=10_000)
    max_records: int = Field(ge=1, le=10_000_000)
    max_bytes: int = Field(ge=1, le=10_737_418_240)
    max_response_bytes: int = Field(ge=1, le=52_428_800)
    max_slices: int = Field(ge=1, le=10_000)
    page_limit: int = Field(ge=1, le=10_000)

    @model_validator(mode="after")
    def validate_bytes(self) -> TusharePlanBudget:
        if self.max_response_bytes > self.max_bytes:
            raise ValueError("TUSHARE_RESPONSE_BUDGET_EXCEEDS_TOTAL")
        return self


class TusharePlanCheckpoint(FrozenProviderContract):
    endpoint: str = Field(pattern=r"^[a-z][a-z_]{1,31}$")
    provider_security_identifier: str = Field(pattern=r"^\d{6}\.(?:SH|SZ|BJ)$")
    next_date: date
    revision: int = Field(ge=0)
    consumed_requests: int = Field(ge=0)
    consumed_records: int = Field(ge=0)
    consumed_bytes: int = Field(ge=0)


class TusharePlanRequest(FrozenProviderContract):
    provider_code: Literal["TUSHARE_PRO_V1"]
    capability_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    capability_version: SemanticVersion
    adapter_version: SemanticVersion
    provider_policy_version: SemanticVersion
    license_policy_version: SemanticVersion
    market: Literal["CN_A"]
    security_id: UUID
    provider_security_identifier: str | None = Field(default=None, pattern=r"^\d{6}\.(?:SH|SZ|BJ)$")
    date_from: date
    date_to: date
    as_of_time: AwareUtcDateTime
    sync_mode: TushareSyncMode
    endpoint: TushareEndpoint
    fields: tuple[str, ...] = Field(min_length=1, max_length=256)
    budget: TusharePlanBudget
    checkpoint: TusharePlanCheckpoint | None
    license_status: ProviderLicenseStatus
    commercial_use_approved: bool
    raw_storage_approved: bool
    credential_status: ProviderCredentialStatus
    live_authorization_status: ProviderLiveAuthorizationStatus
    entitlement_status: TushareEntitlementStatus
    synthetic_status: ProviderSyntheticStatus

    @model_validator(mode="after")
    def validate_request_bounds(self) -> TusharePlanRequest:
        if self.date_to < self.date_from:
            raise ValueError("TUSHARE_RANGE_INVALID")
        if (self.date_to - self.date_from).days > _MAX_RANGE_DAYS:
            raise ValueError("TUSHARE_RANGE_EXCEEDS_MAXIMUM")
        if self.date_to > self.as_of_time.date():
            raise ValueError("TUSHARE_FUTURE_RANGE_FORBIDDEN")
        if self.fields != tuple(sorted(set(self.fields))):
            raise ValueError("TUSHARE_FIELDS_MUST_BE_UNIQUE_AND_SORTED")
        if self.checkpoint is not None:
            if (
                self.checkpoint.endpoint != self.endpoint.value
                or self.checkpoint.provider_security_identifier != self.provider_security_identifier
            ):
                raise ValueError("TUSHARE_CHECKPOINT_SCOPE_MISMATCH")
            if not self.date_from <= self.checkpoint.next_date <= self.date_to:
                raise ValueError("TUSHARE_CHECKPOINT_CANNOT_EXPAND_RANGE")
        return self


class TusharePlanResult(FrozenProviderContract):
    allowed: bool
    status: TusharePlanStatus
    blocking_reasons: tuple[str, ...]
    production_blocking_reasons: tuple[str, ...]
    warning_codes: tuple[str, ...]
    plan: ProviderSyncPlanDraft | None
    idempotency_key: Checksum
    normalized_parameters: tuple[tuple[str, str], ...]
    estimated_requests: int
    estimated_records: int
    estimated_bytes: int
    remaining_requests: int
    remaining_records: int
    remaining_bytes: int
    capability_version: SemanticVersion
    policy_version: SemanticVersion
    license_policy_version: SemanticVersion
    adapter_version: SemanticVersion
    access_mode: Literal["OFFLINE"]
    live_status: Literal["NOT_LIVE"]
    production_status: ProviderProductionStatus
    synthetic_status: ProviderSyntheticStatus


class TushareParseContext(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    raw_artifact_id: UUID
    source_checksum: Checksum
    manifest_checksum: Checksum
    source_identity: str = Field(min_length=1, max_length=512)
    endpoint: TushareEndpoint
    provider_security_identifier: str = Field(pattern=r"^\d{6}\.(?:SH|SZ|BJ)$")
    numeric_fields: tuple[str, ...]
    provider_metric_fields: tuple[str, ...]
    publication_fields: tuple[str, ...]
    period_field: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    source_published_at: AwareUtcDateTime | None
    research_as_of_time: AwareUtcDateTime
    synthetic_status: ProviderSyntheticStatus

    @model_validator(mode="after")
    def validate_field_roles(self) -> TushareParseContext:
        for fields in (
            self.numeric_fields,
            self.provider_metric_fields,
            self.publication_fields,
        ):
            if fields != tuple(sorted(set(fields))):
                raise ValueError("TUSHARE_PARSE_FIELDS_MUST_BE_UNIQUE_AND_SORTED")
        if not set(self.provider_metric_fields) <= set(self.numeric_fields):
            raise ValueError("TUSHARE_PROVIDER_METRICS_MUST_BE_NUMERIC")
        return self


class TushareGovernanceDescriptor(FrozenProviderContract):
    capability_status: ProviderCapabilityStatus
    license_status: ProviderLicenseStatus
    credential_status: ProviderCredentialStatus
    live_status: ProviderLiveValidationStatus
    production_status: ProviderProductionStatus
    network_status: Literal["HARD_BLOCKED"]
    reason_codes: tuple[str, ...]


class TushareAdapter:
    """Expose offline contracts while keeping all production transport blocked."""

    descriptor = TushareGovernanceDescriptor(
        capability_status=ProviderCapabilityStatus.IMPLEMENTED_OFFLINE,
        license_status=ProviderLicenseStatus.RESTRICTED_REVIEW_REQUIRED,
        credential_status=ProviderCredentialStatus.NOT_READ,
        live_status=ProviderLiveValidationStatus.NOT_ATTEMPTED,
        production_status=ProviderProductionStatus.BLOCKED,
        network_status="HARD_BLOCKED",
        reason_codes=(
            "HTTPS_ENDPOINT_NOT_APPROVED",
            "LICENSE_RIGHTS_NOT_APPROVED",
            "TOKEN_ENTITLEMENTS_UNKNOWN",
        ),
    )

    def plan(self, request: TusharePlanRequest) -> TusharePlanResult:
        """Build a finite offline contract plan without reading credentials."""

        idempotency_key = provider_checksum(_idempotency_payload(request))
        production_reasons = _production_blocking_reasons(request)
        blocking: list[str] = []
        allowed_endpoints = _CAPABILITY_ENDPOINTS.get(request.capability_code)
        if allowed_endpoints is None:
            blocking.append("CAPABILITY_NOT_APPROVED")
        elif request.endpoint not in allowed_endpoints:
            blocking.append("ENDPOINT_NOT_APPROVED_FOR_CAPABILITY")
        if not set(request.fields) <= _ENDPOINT_FIELDS[request.endpoint]:
            blocking.append("FIELDS_NOT_APPROVED")
        if request.provider_security_identifier is None:
            blocking.append("PROVIDER_MAPPING_MISSING")
        if request.entitlement_status is TushareEntitlementStatus.BLOCKED:
            blocking.append("PROVIDER_ENTITLEMENT_BLOCKED")
        if request.sync_mode is TushareSyncMode.LIVE:
            blocking.extend(production_reasons)

        remaining = _remaining_budget(request)
        if any(value <= 0 for value in remaining):
            blocking.append("SYNC_BUDGET_EXHAUSTED")
        if blocking:
            return _blocked_result(
                request,
                idempotency_key=idempotency_key,
                reasons=tuple(sorted(set(blocking))),
                production_reasons=production_reasons,
                remaining=remaining,
            )

        start = (
            request.checkpoint.next_date if request.checkpoint is not None else request.date_from
        )
        slices: list[ProviderSyncSlice] = []
        cursor = start
        requests_left, records_left, bytes_left = remaining
        while (
            cursor <= request.date_to
            and requests_left > 0
            and records_left > 0
            and bytes_left > 0
            and len(slices) < request.budget.max_slices
        ):
            end = min(cursor + timedelta(days=_SLICE_DAYS - 1), request.date_to)
            limit = min(request.budget.page_limit, records_left)
            response_bytes = min(request.budget.max_response_bytes, bytes_left)
            ordinal = len(slices)
            slices.append(
                ProviderSyncSlice(
                    slice_id=f"TUSHARE_{request.endpoint.value.upper()}_{ordinal:04d}",
                    ordinal=ordinal,
                    range_start=cursor,
                    range_end=end,
                    request_parameters={
                        "endpoint_id": request.endpoint.value,
                        "ts_code": request.provider_security_identifier,
                        "fields": request.fields,
                        "date_from": cursor.isoformat(),
                        "date_to": end.isoformat(),
                        "offset": 0,
                        "limit": limit,
                        "max_response_bytes": response_bytes,
                    },
                )
            )
            requests_left -= 1
            records_left -= limit
            bytes_left -= response_bytes
            cursor = end + timedelta(days=1)

        if not slices:
            return _blocked_result(
                request,
                idempotency_key=idempotency_key,
                reasons=("SYNC_BUDGET_EXHAUSTED",),
                production_reasons=production_reasons,
                remaining=remaining,
            )
        truncated = cursor <= request.date_to
        estimated_records = sum(cast(int, slice_.request_parameters["limit"]) for slice_ in slices)
        estimated_bytes = sum(
            cast(int, slice_.request_parameters["max_response_bytes"]) for slice_ in slices
        )
        plan = ProviderSyncPlanDraft(
            sync_request_id=UUID(idempotency_key[:32]),
            adapter_version=request.adapter_version,
            catalog_version=request.capability_version,
            checkpoint_revision=(
                request.checkpoint.revision if request.checkpoint is not None else None
            ),
            slices=tuple(slices),
        )
        return TusharePlanResult(
            allowed=True,
            status=(TusharePlanStatus.PARTIAL if truncated else TusharePlanStatus.READY),
            blocking_reasons=(),
            production_blocking_reasons=production_reasons,
            warning_codes=(("PLAN_TRUNCATED_BY_BUDGET",) if truncated else ()),
            plan=plan,
            idempotency_key=idempotency_key,
            normalized_parameters=_normalized_parameters(request),
            estimated_requests=len(slices),
            estimated_records=estimated_records,
            estimated_bytes=estimated_bytes,
            remaining_requests=remaining[0],
            remaining_records=remaining[1],
            remaining_bytes=remaining[2],
            capability_version=request.capability_version,
            policy_version=request.provider_policy_version,
            license_policy_version=request.license_policy_version,
            adapter_version=request.adapter_version,
            access_mode="OFFLINE",
            live_status="NOT_LIVE",
            production_status=ProviderProductionStatus.BLOCKED,
            synthetic_status=request.synthetic_status,
        )

    def parse_response(
        self,
        body: bytes,
        context: TushareParseContext,
    ) -> ProviderBatch:
        """Project an already-acquired offline response without normalization."""

        if hashlib.sha256(body).hexdigest() != context.source_checksum:
            raise ValueError("TUSHARE_RESPONSE_CHECKSUM_MISMATCH")
        if (
            context.source_published_at is not None
            and context.source_published_at > context.research_as_of_time
        ):
            raise ValueError("TUSHARE_FUTURE_DATA")
        try:
            payload = json.loads(body)
            if (
                not isinstance(payload, dict)
                or payload.get("code") != 0
                or not isinstance(payload.get("data"), dict)
            ):
                raise ValueError
            data = payload["data"]
            response = TushareOfflineResponse(
                endpoint=context.endpoint,
                fields=tuple(data["fields"]),
                items=tuple(tuple(item) for item in data["items"]),
                offset=0,
                has_more=False,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("TUSHARE_RESPONSE_MALFORMED") from None
        fields = response.fields
        required = {
            "ts_code",
            context.period_field,
            *context.numeric_fields,
            *context.provider_metric_fields,
            *context.publication_fields,
        }
        if not required <= set(fields) or not set(fields) <= _ENDPOINT_FIELDS[context.endpoint]:
            raise ValueError("TUSHARE_RESPONSE_FIELDS_NOT_APPROVED")
        records: list[ProviderRecord] = []
        for index, item in enumerate(response.items):
            row = dict(zip(fields, item, strict=True))
            if row["ts_code"] != context.provider_security_identifier:
                raise ValueError("TUSHARE_SECURITY_IDENTITY_MISMATCH")
            numeric_values = {
                field: _exact_numeric_string(row[field]) for field in context.numeric_fields
            }
            text_values = {
                field: (None if value is None else str(value))
                for field, value in row.items()
                if field not in context.numeric_fields
            }
            if context.endpoint in {
                TushareEndpoint.INCOME,
                TushareEndpoint.BALANCE_SHEET,
                TushareEndpoint.CASH_FLOW,
            }:
                text_values["aggregation_semantics"] = "PROVIDER_REPORTED_UNNORMALIZED"
            if context.provider_metric_fields:
                text_values["provider_metric_fields"] = ",".join(context.provider_metric_fields)
            warnings = ("UNKNOWN_PUBLISHED_AT",) if context.source_published_at is None else ()
            period = row[context.period_field]
            update_flag = row.get("update_flag")
            record_key = (
                f"{context.endpoint.value}:{context.provider_security_identifier}:"
                f"{period}:{update_flag}:{index:04d}"
            )
            records.append(
                ProviderRecord(
                    identity=ProviderRecordIdentity(
                        provider_definition_id=context.provider_definition_id,
                        provider_capability_id=context.provider_capability_id,
                        source_identity=context.source_identity,
                        record_key=record_key,
                        revision=1,
                    ),
                    raw_artifact_id=context.raw_artifact_id,
                    source_checksum=context.source_checksum,
                    source_published_at=context.source_published_at,
                    status=(
                        ProviderRecordStatus.PARTIAL if warnings else ProviderRecordStatus.COMPLETE
                    ),
                    numeric_values=numeric_values,
                    text_values=text_values,
                    warning_codes=warnings,
                    synthetic_status=context.synthetic_status,
                )
            )
        if not records:
            raise ValueError("TUSHARE_RESPONSE_EMPTY")
        return ProviderBatch(
            manifest_checksum=context.manifest_checksum,
            records=tuple(sorted(records, key=lambda record: record.identity.record_key)),
        )


def _idempotency_payload(request: TusharePlanRequest) -> dict[str, object]:
    return {
        "provider_code": request.provider_code,
        "capability_code": request.capability_code,
        "capability_version": request.capability_version,
        "adapter_version": request.adapter_version,
        "provider_policy_version": request.provider_policy_version,
        "license_policy_version": request.license_policy_version,
        "market": request.market,
        "security_id": request.security_id,
        "provider_security_identifier": request.provider_security_identifier,
        "date_from": request.date_from,
        "date_to": request.date_to,
        "as_of_time": request.as_of_time,
        "sync_mode": request.sync_mode,
        "endpoint": request.endpoint,
        "fields": request.fields,
        "budget": request.budget,
        "checkpoint": request.checkpoint,
    }


def _production_blocking_reasons(
    request: TusharePlanRequest,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not request.commercial_use_approved:
        reasons.append("COMMERCIAL_USE_UNCONFIRMED")
    if not request.raw_storage_approved:
        reasons.append("RAW_STORAGE_RIGHT_UNCONFIRMED")
    if request.license_status is not ProviderLicenseStatus.APPROVED:
        reasons.append(f"LICENSE_{request.license_status.value}")
    if request.credential_status is not ProviderCredentialStatus.CONFIGURED_METADATA_ONLY:
        reasons.append("CREDENTIAL_NOT_READ")
    if request.live_authorization_status is not ProviderLiveAuthorizationStatus.AUTHORIZED:
        reasons.append("LIVE_NOT_AUTHORIZED")
    if request.entitlement_status is TushareEntitlementStatus.UNKNOWN:
        reasons.append("PROVIDER_ENTITLEMENT_UNKNOWN")
    elif request.entitlement_status is TushareEntitlementStatus.BLOCKED:
        reasons.append("PROVIDER_ENTITLEMENT_BLOCKED")
    return tuple(sorted(set(reasons)))


def _remaining_budget(request: TusharePlanRequest) -> tuple[int, int, int]:
    checkpoint = request.checkpoint
    if checkpoint is None:
        return (
            request.budget.max_requests,
            request.budget.max_records,
            request.budget.max_bytes,
        )
    return (
        request.budget.max_requests - checkpoint.consumed_requests,
        request.budget.max_records - checkpoint.consumed_records,
        request.budget.max_bytes - checkpoint.consumed_bytes,
    )


def _normalized_parameters(
    request: TusharePlanRequest,
) -> tuple[tuple[str, str], ...]:
    return (
        ("endpoint", request.endpoint.value),
        ("fields", ",".join(request.fields)),
        ("provider_security_identifier", request.provider_security_identifier or ""),
    )


def _blocked_result(
    request: TusharePlanRequest,
    *,
    idempotency_key: str,
    reasons: tuple[str, ...],
    production_reasons: tuple[str, ...],
    remaining: tuple[int, int, int],
) -> TusharePlanResult:
    return TusharePlanResult(
        allowed=False,
        status=TusharePlanStatus.BLOCKED,
        blocking_reasons=reasons,
        production_blocking_reasons=production_reasons,
        warning_codes=(),
        plan=None,
        idempotency_key=idempotency_key,
        normalized_parameters=_normalized_parameters(request),
        estimated_requests=0,
        estimated_records=0,
        estimated_bytes=0,
        remaining_requests=max(remaining[0], 0),
        remaining_records=max(remaining[1], 0),
        remaining_bytes=max(remaining[2], 0),
        capability_version=request.capability_version,
        policy_version=request.provider_policy_version,
        license_policy_version=request.license_policy_version,
        adapter_version=request.adapter_version,
        access_mode="OFFLINE",
        live_status="NOT_LIVE",
        production_status=ProviderProductionStatus.BLOCKED,
        synthetic_status=request.synthetic_status,
    )


def _exact_numeric_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (bool, float)):
        raise ValueError("TUSHARE_BINARY_FLOAT_FORBIDDEN")
    if not isinstance(value, (str, int)):
        raise ValueError("TUSHARE_NUMERIC_VALUE_INVALID")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("TUSHARE_NUMERIC_VALUE_INVALID") from None
    if not number.is_finite():
        raise ValueError("TUSHARE_NUMERIC_VALUE_INVALID")
    return str(value)
