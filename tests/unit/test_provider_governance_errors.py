import importlib
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).parents[2]
ERRORS_MODULE = ROOT / "src" / "stock_research_agent" / "domain" / "providers" / "errors.py"


def _errors() -> object:
    assert ERRORS_MODULE.is_file(), "safe Provider failure vocabulary is absent"
    return importlib.import_module("stock_research_agent.domain.providers.errors")


def test_blocked_reason_is_structured_and_safe() -> None:
    errors = _errors()
    reason = errors.ProviderBlockedReason(
        code=errors.ProviderFailureCode.LICENSE_BLOCKED,
        gate="LICENSE",
        safe_detail="Provider license review is required",
        provider_code="TUSHARE_PRO_V1",
        capability_code="FETCH_EOD_PRICES",
    )
    result = errors.ProviderGateResult(
        allowed=False,
        gate_order=3,
        reason=reason,
    )

    assert result.reason is not None
    assert result.reason.code is errors.ProviderFailureCode.LICENSE_BLOCKED
    assert result.reason.safe_detail == "Provider license review is required"


@pytest.mark.parametrize(
    "unsafe_detail",
    (
        "secret-sentinel",
        "postgresql+psycopg://user:password@host/database",
        "https://unapproved.example/path",
        "Authorization: Bearer token",
        "Cookie: session=value",
        r"C:\private\provider\payload.json",
        "SELECT * FROM provider_definitions",
        "safe first line\nforged log line",
    ),
)
def test_blocked_reason_rejects_unsafe_diagnostic_text(unsafe_detail: str) -> None:
    errors = _errors()

    with pytest.raises(ValidationError):
        errors.ProviderBlockedReason(
            code=errors.ProviderFailureCode.CONFIGURATION_INVALID,
            gate="CONFIGURATION_VALIDATION",
            safe_detail=unsafe_detail,
            provider_code="SEC_EDGAR_PUBLIC_V1",
            capability_code="FETCH_FILING_METADATA",
        )


def test_unknown_exception_is_mapped_without_raw_details() -> None:
    errors = _errors()
    raw = (
        "postgresql+psycopg://user:secret-sentinel@host/database "
        "Authorization: Bearer token C:\\private\\payload SELECT table"
    )

    failure = errors.safe_provider_error(RuntimeError(raw))
    serialized = failure.model_dump_json()

    assert failure.code is errors.ProviderFailureCode.INTERNAL_PROVIDER_ERROR
    assert failure.safe_message == "Provider operation failed safely"
    for forbidden in (
        "secret-sentinel",
        "postgresql",
        "Authorization",
        "Bearer",
        "private",
        "SELECT",
        "RuntimeError",
    ):
        assert forbidden not in serialized


def test_known_provider_failure_preserves_only_validated_safe_message() -> None:
    errors = _errors()
    expected = errors.ProviderFailure(
        code=errors.ProviderFailureCode.CAPABILITY_NOT_ALLOWLISTED,
        safe_message="Requested capability is not allowlisted",
        retryable=False,
        blocked_reason=None,
    )

    actual = errors.safe_provider_error(errors.ProviderDomainError(expected))

    assert actual == expected
    assert actual.retryable is False
