"""Deterministic retry classification with no sleeping or hidden I/O."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field, model_validator

from stock_research_agent.domain.providers.schemas import FrozenProviderContract

_TRANSIENT_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
_TRANSIENT_ERROR = frozenset({"CONNECT_TIMEOUT", "READ_TIMEOUT"})


class ProviderRetryOutcome(FrozenProviderContract):
    http_status: int | None = Field(default=None, ge=100, le=599)
    error_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{2,127}$",
    )

    @model_validator(mode="after")
    def require_outcome(self) -> ProviderRetryOutcome:
        if self.http_status is None and self.error_code is None:
            raise ValueError("retry outcome requires a status or error code")
        return self


class ProviderRetryBudget(FrozenProviderContract):
    max_attempts: int = Field(ge=1, le=3)
    remaining_requests: int = Field(ge=0, le=10_000)
    remaining_bytes: int = Field(ge=0, le=10_737_418_240)
    remaining_duration_seconds: Decimal = Field(ge=0, le=86_400)
    base_delay_seconds: Decimal = Field(gt=0, le=60)
    idempotent_read: bool

    @model_validator(mode="after")
    def require_finite_decimals(self) -> ProviderRetryBudget:
        if not self.remaining_duration_seconds.is_finite():
            raise ValueError("remaining duration must be finite")
        if not self.base_delay_seconds.is_finite():
            raise ValueError("base delay must be finite")
        return self


class RetryDecision(FrozenProviderContract):
    retry: bool
    reason_code: str
    next_attempt: int | None
    delay_seconds: Decimal = Field(ge=0)
    resolve_credential_again: bool = False


class ProviderRetryPolicy:
    """Classify one result against a finite immutable retry budget."""

    @staticmethod
    def classify(
        outcome: ProviderRetryOutcome,
        attempt: int,
        budget: ProviderRetryBudget,
    ) -> RetryDecision:
        if attempt < 1:
            raise ValueError("PROVIDER_RETRY_ATTEMPT_INVALID")
        delay = budget.base_delay_seconds * (Decimal(2) ** (attempt - 1))
        budget_available = (
            budget.idempotent_read
            and attempt < budget.max_attempts
            and budget.remaining_requests > 0
            and budget.remaining_bytes > 0
            and budget.remaining_duration_seconds >= delay
        )
        if not budget_available:
            return RetryDecision(
                retry=False,
                reason_code="PROVIDER_RETRY_BUDGET_EXHAUSTED",
                next_attempt=None,
                delay_seconds=Decimal(0),
            )
        eligible = (
            outcome.http_status in _TRANSIENT_STATUS or outcome.error_code in _TRANSIENT_ERROR
        )
        if not eligible:
            return RetryDecision(
                retry=False,
                reason_code="PROVIDER_RETRY_NOT_ELIGIBLE",
                next_attempt=None,
                delay_seconds=Decimal(0),
            )
        return RetryDecision(
            retry=True,
            reason_code="PROVIDER_RETRY_TRANSIENT",
            next_attempt=attempt + 1,
            delay_seconds=delay,
            resolve_credential_again=False,
        )
