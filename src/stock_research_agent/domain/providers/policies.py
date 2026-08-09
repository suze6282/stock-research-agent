from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, Field, model_validator

from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
    SemanticVersion,
)


def _positive_finite_decimal(value: Decimal) -> Decimal:
    if not value.is_finite() or value <= 0:
        raise ValueError("value must be positive and finite")
    return value


PositiveFiniteDecimal = Annotated[
    Decimal,
    AfterValidator(_positive_finite_decimal),
]


class ProviderPolicyWrite(FrozenProviderContract):
    provider_definition_id: UUID
    policy_version: SemanticVersion
    endpoint_policy_version: SemanticVersion
    network_enabled: bool
    max_requests: int = Field(ge=1, le=10_000)
    max_response_bytes: int = Field(ge=1, le=52_428_800)
    max_total_bytes: int = Field(ge=1, le=10_737_418_240)
    max_duration_seconds: int = Field(ge=1, le=86_400)
    max_attempts: int = Field(ge=1, le=3)
    max_redirects: int = Field(ge=0, le=5)
    rate_limit_per_second: PositiveFiniteDecimal
    retry_base_delay_seconds: PositiveFiniteDecimal
    cache_enabled: bool
    cache_ttl_seconds: int | None = Field(default=None, ge=1, le=86_400)
    retention_days: int | None = Field(default=None, ge=1, le=36_500)

    @model_validator(mode="after")
    def validate_internal_limits(self) -> ProviderPolicyWrite:
        if self.max_total_bytes < self.max_response_bytes:
            raise ValueError("max_total_bytes must cover at least one response")
        if self.cache_enabled != (self.cache_ttl_seconds is not None):
            raise ValueError("cache_enabled and cache_ttl_seconds are inconsistent")
        return self


class ProviderPolicyRecord(ProviderPolicyWrite):
    id: UUID
    checksum: Checksum
    created_at: AwareUtcDateTime


class ProviderExecutionBudget(FrozenProviderContract):
    max_requests: int = Field(ge=1, le=10_000)
    max_response_bytes: int = Field(ge=1, le=52_428_800)
    max_total_bytes: int = Field(ge=1, le=10_737_418_240)
    max_duration_seconds: int = Field(ge=1, le=86_400)
    max_attempts: int = Field(ge=1, le=3)
    max_redirects: int = Field(ge=0, le=5)
    requested_rate_per_second: PositiveFiniteDecimal
    use_cache: bool
    cache_ttl_seconds: int | None = Field(default=None, ge=1, le=86_400)
    retention_days: int | None = Field(default=None, ge=1, le=36_500)
    network_requested: bool

    @model_validator(mode="after")
    def validate_internal_limits(self) -> ProviderExecutionBudget:
        if self.max_total_bytes < self.max_response_bytes:
            raise ValueError("max_total_bytes must cover at least one response")
        if self.use_cache != (self.cache_ttl_seconds is not None):
            raise ValueError("use_cache and cache_ttl_seconds are inconsistent")
        return self


class ProviderPolicyDecision(FrozenProviderContract):
    allowed: bool
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=16)
    policy_id: UUID


class ProviderPolicyGate:
    """Ensure a request can only narrow an immutable Provider Policy."""

    def evaluate(
        self,
        policy: ProviderPolicyRecord,
        request: ProviderExecutionBudget,
    ) -> ProviderPolicyDecision:
        reasons: list[str] = []
        comparisons = (
            (
                request.max_requests > policy.max_requests,
                "PROVIDER_POLICY_REQUEST_LIMIT_EXCEEDED",
            ),
            (
                request.max_response_bytes > policy.max_response_bytes,
                "PROVIDER_POLICY_RESPONSE_BYTES_EXCEEDED",
            ),
            (
                request.max_total_bytes > policy.max_total_bytes,
                "PROVIDER_POLICY_TOTAL_BYTES_EXCEEDED",
            ),
            (
                request.max_duration_seconds > policy.max_duration_seconds,
                "PROVIDER_POLICY_DURATION_EXCEEDED",
            ),
            (
                request.max_attempts > policy.max_attempts,
                "PROVIDER_POLICY_ATTEMPTS_EXCEEDED",
            ),
            (
                request.max_redirects > policy.max_redirects,
                "PROVIDER_POLICY_REDIRECTS_EXCEEDED",
            ),
            (
                request.requested_rate_per_second > policy.rate_limit_per_second,
                "PROVIDER_POLICY_RATE_EXCEEDED",
            ),
            (
                request.network_requested and not policy.network_enabled,
                "PROVIDER_POLICY_NETWORK_DISABLED",
            ),
            (
                request.use_cache and not policy.cache_enabled,
                "PROVIDER_POLICY_CACHE_DISABLED",
            ),
            (
                request.use_cache
                and policy.cache_ttl_seconds is not None
                and request.cache_ttl_seconds is not None
                and request.cache_ttl_seconds > policy.cache_ttl_seconds,
                "PROVIDER_POLICY_CACHE_TTL_EXCEEDED",
            ),
            (
                request.retention_days is not None
                and policy.retention_days is not None
                and request.retention_days > policy.retention_days,
                "PROVIDER_POLICY_RETENTION_EXCEEDED",
            ),
        )
        reasons.extend(reason for failed, reason in comparisons if failed)
        return ProviderPolicyDecision(
            allowed=not reasons,
            reason_codes=(tuple(reasons) if reasons else ("PROVIDER_POLICY_APPROVED",)),
            policy_id=policy.id,
        )
