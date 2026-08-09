"""Versioned deterministic Provider freshness contracts."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    FrozenProviderContract,
    SemanticVersion,
)


class ProviderFreshnessStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    FUTURE_DATA = "FUTURE_DATA"
    BLOCKED = "BLOCKED"


class ProviderFreshnessPolicyWrite(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    market_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,31}$")
    policy_version: SemanticVersion
    expected_delay_seconds: int = Field(ge=1, le=2_592_000)
    unknown_published_at_status: ProviderFreshnessStatus

    @model_validator(mode="after")
    def validate_unknown_status(self) -> ProviderFreshnessPolicyWrite:
        if self.unknown_published_at_status not in {
            ProviderFreshnessStatus.UNKNOWN,
            ProviderFreshnessStatus.BLOCKED,
        }:
            raise ValueError("unknown publication policy must be UNKNOWN or BLOCKED")
        return self

    @property
    def checksum(self) -> str:
        return provider_checksum(self)


class ProviderFreshnessPolicyRecord(ProviderFreshnessPolicyWrite):
    id: UUID
    created_at: AwareUtcDateTime


class ProviderFreshnessObservation(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    market_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,31}$")
    source_published_at: AwareUtcDateTime | None
    retrieved_at: AwareUtcDateTime


class ProviderFreshnessResult(FrozenProviderContract):
    status: ProviderFreshnessStatus
    age_seconds: int | None = Field(default=None, ge=0)
    warning_codes: tuple[str, ...] = Field(default=(), max_length=8)


class ProviderFreshnessEvaluator:
    """Evaluate source publication age without calendar or retrieval-time inference."""

    def evaluate(
        self,
        policy: ProviderFreshnessPolicyWrite | ProviderFreshnessPolicyRecord,
        latest: ProviderFreshnessObservation,
        as_of: AwareUtcDateTime,
    ) -> ProviderFreshnessResult:
        policy_scope = (
            policy.provider_definition_id,
            policy.provider_capability_id,
            policy.market_code,
        )
        observation_scope = (
            latest.provider_definition_id,
            latest.provider_capability_id,
            latest.market_code,
        )
        if policy_scope != observation_scope:
            raise ValueError("PROVIDER_FRESHNESS_SCOPE_MISMATCH")
        if latest.source_published_at is None:
            return ProviderFreshnessResult(
                status=policy.unknown_published_at_status,
                warning_codes=("UNKNOWN_PUBLISHED_AT",),
            )
        if latest.source_published_at > as_of:
            return ProviderFreshnessResult(
                status=ProviderFreshnessStatus.FUTURE_DATA,
                warning_codes=("FUTURE_DATA",),
            )
        age_seconds = int((as_of - latest.source_published_at).total_seconds())
        status = (
            ProviderFreshnessStatus.FRESH
            if age_seconds <= policy.expected_delay_seconds
            else ProviderFreshnessStatus.STALE
        )
        return ProviderFreshnessResult(
            status=status,
            age_seconds=age_seconds,
            warning_codes=(
                ("STALE_PROVIDER_DATA",) if status is ProviderFreshnessStatus.STALE else ()
            ),
        )
