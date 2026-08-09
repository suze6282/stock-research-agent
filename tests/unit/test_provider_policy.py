import importlib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).parents[2]
POLICIES_MODULE = ROOT / "src" / "stock_research_agent" / "domain" / "providers" / "policies.py"
PROVIDER_ID = UUID("11111111-1111-4111-8111-111111111111")


def _policies() -> object:
    assert POLICIES_MODULE.is_file(), "finite Provider Policy contracts are absent"
    return importlib.import_module("stock_research_agent.domain.providers.policies")


def _policy_values() -> dict[str, object]:
    return {
        "provider_definition_id": PROVIDER_ID,
        "policy_version": "1.0.0",
        "endpoint_policy_version": "1.0.0",
        "network_enabled": False,
        "max_requests": 10,
        "max_response_bytes": 1_000_000,
        "max_total_bytes": 5_000_000,
        "max_duration_seconds": 60,
        "max_attempts": 2,
        "max_redirects": 0,
        "rate_limit_per_second": Decimal("1.0"),
        "retry_base_delay_seconds": Decimal("0.25"),
        "cache_enabled": True,
        "cache_ttl_seconds": 300,
        "retention_days": 365,
    }


def _policy(policies: object) -> object:
    return policies.ProviderPolicyRecord(
        **_policy_values(),
        id=UUID("22222222-2222-4222-8222-222222222222"),
        checksum="a" * 64,
        created_at=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
    )


def test_provider_policy_gate_accepts_only_within_finite_limits() -> None:
    policies = _policies()
    request = policies.ProviderExecutionBudget(
        max_requests=2,
        max_response_bytes=500_000,
        max_total_bytes=1_000_000,
        max_duration_seconds=30,
        max_attempts=1,
        max_redirects=0,
        requested_rate_per_second=Decimal("0.5"),
        use_cache=True,
        cache_ttl_seconds=60,
        retention_days=30,
        network_requested=False,
    )

    decision = policies.ProviderPolicyGate().evaluate(_policy(policies), request)

    assert decision.allowed is True
    assert decision.reason_codes == ("PROVIDER_POLICY_APPROVED",)


def test_provider_policy_gate_blocks_caller_budget_expansion() -> None:
    policies = _policies()
    base = {
        "max_requests": 2,
        "max_response_bytes": 500_000,
        "max_total_bytes": 1_000_000,
        "max_duration_seconds": 30,
        "max_attempts": 1,
        "max_redirects": 0,
        "requested_rate_per_second": Decimal("0.5"),
        "use_cache": True,
        "cache_ttl_seconds": 60,
        "retention_days": 30,
        "network_requested": False,
    }

    for field, value, reason in (
        ("max_requests", 11, "PROVIDER_POLICY_REQUEST_LIMIT_EXCEEDED"),
        ("max_total_bytes", 5_000_001, "PROVIDER_POLICY_TOTAL_BYTES_EXCEEDED"),
        ("max_attempts", 3, "PROVIDER_POLICY_ATTEMPTS_EXCEEDED"),
        (
            "requested_rate_per_second",
            Decimal("1.1"),
            "PROVIDER_POLICY_RATE_EXCEEDED",
        ),
        ("retention_days", 366, "PROVIDER_POLICY_RETENTION_EXCEEDED"),
        ("network_requested", True, "PROVIDER_POLICY_NETWORK_DISABLED"),
    ):
        budget = policies.ProviderExecutionBudget(**{**base, field: value})
        decision = policies.ProviderPolicyGate().evaluate(_policy(policies), budget)
        assert decision.allowed is False
        assert reason in decision.reason_codes


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("max_requests", 0),
        ("max_response_bytes", 52_428_801),
        ("max_attempts", 4),
        ("max_redirects", 6),
        ("rate_limit_per_second", Decimal("0")),
        ("rate_limit_per_second", Decimal("NaN")),
        ("retry_base_delay_seconds", Decimal("Infinity")),
        ("rate_limit_per_second", 1.0),
    ),
)
def test_provider_policy_rejects_non_finite_or_unsafe_limits(
    field: str,
    invalid: object,
) -> None:
    policies = _policies()
    values = {**_policy_values(), field: invalid}

    with pytest.raises(ValidationError):
        policies.ProviderPolicyWrite(**values)


def test_cache_configuration_must_be_internally_consistent() -> None:
    policies = _policies()

    with pytest.raises(ValidationError):
        policies.ProviderPolicyWrite(
            **{
                **_policy_values(),
                "cache_enabled": False,
                "cache_ttl_seconds": 300,
            }
        )
