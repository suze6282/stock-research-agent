from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from stock_research_agent.domain.providers.enums import ProviderLiveAuthorizationStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
)


class LiveAuthorization(FrozenProviderContract):
    authorization_id: UUID
    provider_definition_id: UUID
    provider_capability_id: UUID
    allowed_hosts: tuple[str, ...] = Field(min_length=1, max_length=8)
    allowed_paths: tuple[str, ...] = Field(min_length=1, max_length=16)
    max_requests: int = Field(ge=1, le=100)
    max_bytes: int = Field(ge=1, le=52_428_800)
    expires_at: AwareUtcDateTime
    actor_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    approval_phrase_checksum: Checksum
    validation_run_id: UUID
    consumed: bool

    @field_validator("allowed_hosts", "allowed_paths")
    @classmethod
    def validate_exact_allowlists(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("authorization allowlists must be unique and sorted")
        return value


class LiveAuthorizationExecutionScope(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    host: str = Field(min_length=1, max_length=253)
    path: str = Field(pattern=r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$")
    requested_requests: int = Field(ge=1, le=100)
    requested_bytes: int = Field(ge=1, le=52_428_800)
    validation_run_id: UUID
    required_approval_phrase_checksum: Checksum


class LiveAuthorizationDecision(FrozenProviderContract):
    allowed: bool
    status: ProviderLiveAuthorizationStatus
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    authorization_id: UUID | None


class LiveAuthorizationGate:
    """Evaluate one explicit finite authorization without resolving secrets."""

    @staticmethod
    def evaluate(
        authorization: LiveAuthorization | None,
        execution_scope: LiveAuthorizationExecutionScope,
        now: datetime,
    ) -> LiveAuthorizationDecision:
        if authorization is None:
            return _denied(
                "LIVE_AUTHORIZATION_REQUIRED",
                ProviderLiveAuthorizationStatus.NOT_ATTEMPTED,
                None,
            )
        checks = (
            (
                authorization.provider_definition_id != execution_scope.provider_definition_id,
                "LIVE_AUTHORIZATION_PROVIDER_MISMATCH",
            ),
            (
                authorization.provider_capability_id != execution_scope.provider_capability_id,
                "LIVE_AUTHORIZATION_CAPABILITY_MISMATCH",
            ),
            (
                execution_scope.host not in authorization.allowed_hosts,
                "LIVE_AUTHORIZATION_HOST_DENIED",
            ),
            (
                execution_scope.path not in authorization.allowed_paths,
                "LIVE_AUTHORIZATION_PATH_DENIED",
            ),
            (
                execution_scope.requested_requests > authorization.max_requests,
                "LIVE_AUTHORIZATION_REQUEST_BUDGET_EXCEEDED",
            ),
            (
                execution_scope.requested_bytes > authorization.max_bytes,
                "LIVE_AUTHORIZATION_BYTE_BUDGET_EXCEEDED",
            ),
            (
                now >= authorization.expires_at,
                "LIVE_AUTHORIZATION_EXPIRED",
            ),
            (
                authorization.consumed,
                "LIVE_AUTHORIZATION_REPLAYED",
            ),
            (
                authorization.validation_run_id != execution_scope.validation_run_id,
                "LIVE_AUTHORIZATION_RUN_MISMATCH",
            ),
            (
                authorization.approval_phrase_checksum
                != execution_scope.required_approval_phrase_checksum,
                "LIVE_AUTHORIZATION_PHRASE_MISMATCH",
            ),
        )
        for failed, reason in checks:
            if failed:
                status = ProviderLiveAuthorizationStatus.BLOCKED
                if reason == "LIVE_AUTHORIZATION_EXPIRED":
                    status = ProviderLiveAuthorizationStatus.EXPIRED
                elif reason == "LIVE_AUTHORIZATION_REPLAYED":
                    status = ProviderLiveAuthorizationStatus.CONSUMED
                return _denied(reason, status, authorization.authorization_id)
        return LiveAuthorizationDecision(
            allowed=True,
            status=ProviderLiveAuthorizationStatus.AUTHORIZED,
            reason_code="LIVE_AUTHORIZATION_EXACT_MATCH",
            authorization_id=authorization.authorization_id,
        )


def _denied(
    reason: str,
    status: ProviderLiveAuthorizationStatus,
    authorization_id: UUID | None,
) -> LiveAuthorizationDecision:
    return LiveAuthorizationDecision(
        allowed=False,
        status=status,
        reason_code=reason,
        authorization_id=authorization_id,
    )
