from __future__ import annotations

import re
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from stock_research_agent.domain.providers.schemas import FrozenProviderContract

_UNSAFE_TEXT = re.compile(
    r"(?i)(?:"
    r"secret|password|token|api[_ -]?key|authorization|bearer|cookie|"
    r"postgres(?:ql)?(?:\+\w+)?://|https?://|"
    r"\b(?:select|insert|update|delete|drop|alter|create)\b|"
    r"(?:^|\s)[a-z]:\\"
    r")"
)
_CODE_PATTERN = r"^[A-Z][A-Z0-9_]{2,127}$"


class ProviderFailureCode(StrEnum):
    PROVIDER_NOT_FOUND = "PROVIDER_NOT_FOUND"
    PROVIDER_VERSION_MISMATCH = "PROVIDER_VERSION_MISMATCH"
    PROVIDER_BLOCKED = "PROVIDER_BLOCKED"
    CAPABILITY_NOT_ALLOWED = "CAPABILITY_NOT_ALLOWED"
    CAPABILITY_NOT_ALLOWLISTED = "CAPABILITY_NOT_ALLOWLISTED"
    LICENSE_UNKNOWN = "LICENSE_UNKNOWN"
    LICENSE_BLOCKED = "LICENSE_BLOCKED"
    LICENSE_RESTRICTION = "LICENSE_RESTRICTION"
    CREDENTIAL_REFERENCE_MISSING = "CREDENTIAL_REFERENCE_MISSING"
    CREDENTIAL_NOT_CONFIGURED = "CREDENTIAL_NOT_CONFIGURED"
    BLOCKED_PROVIDER_ENTITLEMENT = "BLOCKED_PROVIDER_ENTITLEMENT"
    CONFIGURATION_INVALID = "CONFIGURATION_INVALID"
    LIVE_AUTHORIZATION_REQUIRED = "LIVE_AUTHORIZATION_REQUIRED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    HTTP_POLICY_REJECTED = "HTTP_POLICY_REJECTED"
    CONTENT_TYPE_MISMATCH = "CONTENT_TYPE_MISMATCH"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    SCHEMA_DRIFT = "SCHEMA_DRIFT"
    RAW_RETENTION_BLOCKED = "RAW_RETENTION_BLOCKED"
    CHECKSUM_CONFLICT = "CHECKSUM_CONFLICT"
    FUTURE_DATA = "FUTURE_DATA"
    UNKNOWN_PUBLISHED_AT = "UNKNOWN_PUBLISHED_AT"
    PROVIDER_MAPPING_MISSING = "PROVIDER_MAPPING_MISSING"
    CHECKPOINT_CONFLICT = "CHECKPOINT_CONFLICT"
    SYNC_ALREADY_RUNNING = "SYNC_ALREADY_RUNNING"
    INTERNAL_PROVIDER_ERROR = "INTERNAL_PROVIDER_ERROR"


def _validate_safe_text(value: str) -> str:
    if value != value.strip() or not 1 <= len(value) <= 256:
        raise ValueError("safe diagnostic text has invalid length or whitespace")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("safe diagnostic text must not contain control characters")
    if _UNSAFE_TEXT.search(value):
        raise ValueError("safe diagnostic text contains restricted material")
    return value


class ProviderBlockedReason(FrozenProviderContract):
    code: ProviderFailureCode
    gate: str = Field(pattern=_CODE_PATTERN)
    safe_detail: str
    provider_code: str = Field(pattern=_CODE_PATTERN)
    capability_code: str | None = Field(default=None, pattern=_CODE_PATTERN)

    @field_validator("safe_detail")
    @classmethod
    def validate_safe_detail(cls, value: str) -> str:
        return _validate_safe_text(value)


class ProviderFailure(FrozenProviderContract):
    code: ProviderFailureCode
    safe_message: str
    retryable: bool
    blocked_reason: ProviderBlockedReason | None

    @field_validator("safe_message")
    @classmethod
    def validate_safe_message(cls, value: str) -> str:
        return _validate_safe_text(value)


class ProviderGateResult(FrozenProviderContract):
    allowed: bool
    gate_order: int = Field(ge=1, le=32)
    reason: ProviderBlockedReason | None

    @model_validator(mode="after")
    def validate_reason(self) -> ProviderGateResult:
        if self.allowed == (self.reason is not None):
            raise ValueError("allowed results omit a reason; denied results require one")
        return self


class ProviderDomainError(Exception):
    """Domain exception carrying only a validated safe failure."""

    def __init__(self, failure: ProviderFailure) -> None:
        self.failure = failure
        super().__init__(failure.code.value)


def safe_provider_error(exc: Exception) -> ProviderFailure:
    """Map an exception without copying raw exception details."""

    if isinstance(exc, ProviderDomainError):
        return exc.failure
    return ProviderFailure(
        code=ProviderFailureCode.INTERNAL_PROVIDER_ERROR,
        safe_message="Provider operation failed safely",
        retryable=False,
        blocked_reason=None,
    )
