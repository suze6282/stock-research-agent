from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from stock_research_agent.domain.providers.enums import ProviderLicenseStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
    SemanticVersion,
)


class LicensePermission(StrEnum):
    ALLOWED = "ALLOWED"
    PROHIBITED = "PROHIBITED"
    UNKNOWN_REQUIRES_REVIEW = "UNKNOWN_REQUIRES_REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SourceLicensePolicyWrite(FrozenProviderContract):
    provider_definition_id: UUID
    policy_version: SemanticVersion
    status: ProviderLicenseStatus
    acquisition: LicensePermission
    raw_storage: LicensePermission
    cache: LicensePermission
    derived_use: LicensePermission
    redistribution: LicensePermission
    retention_days: int | None = Field(default=None, ge=1, le=36_500)
    deletion_required: bool
    attribution_required: bool
    terms_source_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    reviewed_at: AwareUtcDateTime
    expires_at: AwareUtcDateTime | None

    @field_validator("terms_source_ids")
    @classmethod
    def validate_terms_source_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("terms_source_ids must be unique and sorted")
        if any(
            not 1 <= len(item) <= 64
            or item != item.upper()
            or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in item)
            for item in value
        ):
            raise ValueError("terms_source_ids must use stable uppercase codes")
        return value

    @model_validator(mode="after")
    def validate_review_window(self) -> SourceLicensePolicyWrite:
        if self.expires_at is not None and self.expires_at <= self.reviewed_at:
            raise ValueError("expires_at must be later than reviewed_at")
        return self


class SourceLicensePolicyRecord(SourceLicensePolicyWrite):
    id: UUID
    checksum: Checksum
    created_at: AwareUtcDateTime


class LicenseUseRequest(FrozenProviderContract):
    acquire: bool
    store_raw: bool
    create_cache: bool
    create_derivative: bool
    redistribute: bool
    requested_retention_days: int | None = Field(default=None, ge=1, le=36_500)

    @model_validator(mode="after")
    def require_a_use(self) -> LicenseUseRequest:
        if not any(
            (
                self.acquire,
                self.store_raw,
                self.create_cache,
                self.create_derivative,
                self.redistribute,
            )
        ):
            raise ValueError("at least one licensed use must be requested")
        return self


class LicenseDecision(FrozenProviderContract):
    allowed: bool
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=8)
    status: ProviderLicenseStatus
    policy_id: UUID


class SourceLicenseGate:
    """Evaluate every requested data use against one immutable license policy."""

    def evaluate(
        self,
        policy: SourceLicensePolicyRecord,
        request: LicenseUseRequest,
        *,
        evaluated_at: datetime,
    ) -> LicenseDecision:
        if policy.status is not ProviderLicenseStatus.APPROVED:
            return LicenseDecision(
                allowed=False,
                reason_codes=(f"LICENSE_{policy.status.value}",),
                status=policy.status,
                policy_id=policy.id,
            )
        if policy.expires_at is not None and evaluated_at >= policy.expires_at:
            return LicenseDecision(
                allowed=False,
                reason_codes=("LICENSE_POLICY_EXPIRED",),
                status=policy.status,
                policy_id=policy.id,
            )

        reasons: list[str] = []
        checks = (
            (request.acquire, policy.acquisition, "ACQUISITION"),
            (request.store_raw, policy.raw_storage, "RAW_STORAGE"),
            (request.create_cache, policy.cache, "CACHE"),
            (request.create_derivative, policy.derived_use, "DERIVED_USE"),
            (request.redistribute, policy.redistribution, "REDISTRIBUTION"),
        )
        for requested, permission, name in checks:
            if requested and permission is not LicensePermission.ALLOWED:
                reasons.append(f"LICENSE_{name}_NOT_ALLOWED")
        if (
            request.requested_retention_days is not None
            and policy.retention_days is not None
            and request.requested_retention_days > policy.retention_days
        ):
            reasons.append("LICENSE_RETENTION_EXCEEDED")

        return LicenseDecision(
            allowed=not reasons,
            reason_codes=tuple(reasons) if reasons else ("LICENSE_USE_APPROVED",),
            status=policy.status,
            policy_id=policy.id,
        )
