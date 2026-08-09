from decimal import Decimal

import pytest

from stock_research_agent.providers.retry import (
    ProviderRetryBudget,
    ProviderRetryOutcome,
    ProviderRetryPolicy,
)


def _budget(**updates: object) -> ProviderRetryBudget:
    values: dict[str, object] = {
        "max_attempts": 2,
        "remaining_requests": 1,
        "remaining_bytes": 1024,
        "remaining_duration_seconds": Decimal("30"),
        "base_delay_seconds": Decimal("1"),
        "idempotent_read": True,
    }
    values.update(updates)
    return ProviderRetryBudget(**values)


@pytest.mark.parametrize(
    "outcome",
    [
        ProviderRetryOutcome(http_status=429, error_code=None),
        ProviderRetryOutcome(http_status=503, error_code=None),
        ProviderRetryOutcome(http_status=None, error_code="CONNECT_TIMEOUT"),
        ProviderRetryOutcome(http_status=None, error_code="READ_TIMEOUT"),
    ],
)
def test_retry_policy_allows_only_approved_transient_idempotent_outcomes(
    outcome: ProviderRetryOutcome,
) -> None:
    decision = ProviderRetryPolicy.classify(outcome, attempt=1, budget=_budget())
    assert decision.retry is True
    assert decision.delay_seconds == Decimal("1")
    assert decision.resolve_credential_again is False


@pytest.mark.parametrize(
    "outcome",
    [
        ProviderRetryOutcome(http_status=401, error_code="AUTHORIZATION_FAILED"),
        ProviderRetryOutcome(http_status=403, error_code="LICENSE_BLOCKED"),
        ProviderRetryOutcome(http_status=404, error_code=None),
        ProviderRetryOutcome(http_status=None, error_code="SCHEMA_DRIFT"),
        ProviderRetryOutcome(http_status=None, error_code="FUTURE_DATA"),
        ProviderRetryOutcome(http_status=None, error_code="INVALID_CONTENT"),
        ProviderRetryOutcome(http_status=None, error_code="CHECKSUM_CONFLICT"),
    ],
)
def test_retry_policy_never_retries_permanent_governance_or_data_failures(
    outcome: ProviderRetryOutcome,
) -> None:
    decision = ProviderRetryPolicy.classify(outcome, attempt=1, budget=_budget())
    assert decision.retry is False
    assert decision.reason_code == "PROVIDER_RETRY_NOT_ELIGIBLE"


@pytest.mark.parametrize(
    "budget",
    [
        _budget(max_attempts=1),
        _budget(remaining_requests=0),
        _budget(remaining_bytes=0),
        _budget(remaining_duration_seconds=Decimal("0")),
        _budget(idempotent_read=False),
    ],
)
def test_retry_policy_hard_stops_at_attempt_or_budget_limit(
    budget: ProviderRetryBudget,
) -> None:
    decision = ProviderRetryPolicy.classify(
        ProviderRetryOutcome(http_status=503, error_code=None),
        attempt=1,
        budget=budget,
    )
    assert decision.retry is False
    assert decision.reason_code == "PROVIDER_RETRY_BUDGET_EXHAUSTED"


def test_retry_schedule_is_deterministic_and_contains_no_sleep() -> None:
    decision = ProviderRetryPolicy.classify(
        ProviderRetryOutcome(http_status=503, error_code=None),
        attempt=2,
        budget=_budget(max_attempts=3),
    )
    assert decision.delay_seconds == Decimal("2")
    assert decision.next_attempt == 3
