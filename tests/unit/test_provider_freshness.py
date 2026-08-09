from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from stock_research_agent.domain.providers import freshness

NOW = datetime(2026, 7, 29, 12, tzinfo=UTC)


def _policy() -> object:
    return freshness.ProviderFreshnessPolicyWrite(
        provider_definition_id=uuid4(),
        provider_capability_id=uuid4(),
        market_code="US_EQUITY",
        policy_version="1.0.0",
        expected_delay_seconds=3600,
        unknown_published_at_status=freshness.ProviderFreshnessStatus.UNKNOWN,
    )


def _observation(policy: object, published_at: datetime | None) -> object:
    return freshness.ProviderFreshnessObservation(
        provider_definition_id=policy.provider_definition_id,
        provider_capability_id=policy.provider_capability_id,
        market_code=policy.market_code,
        source_published_at=published_at,
        retrieved_at=NOW,
    )


def test_fresh_and_stale_use_source_published_time_only() -> None:
    policy = _policy()
    evaluator = freshness.ProviderFreshnessEvaluator()
    fresh = evaluator.evaluate(policy, _observation(policy, NOW - timedelta(seconds=3599)), NOW)
    stale = evaluator.evaluate(policy, _observation(policy, NOW - timedelta(seconds=3601)), NOW)
    assert fresh.status is freshness.ProviderFreshnessStatus.FRESH
    assert stale.status is freshness.ProviderFreshnessStatus.STALE


def test_unknown_publication_does_not_substitute_retrieved_at() -> None:
    policy = _policy()
    result = freshness.ProviderFreshnessEvaluator().evaluate(
        policy,
        _observation(policy, None),
        NOW,
    )
    assert result.status is freshness.ProviderFreshnessStatus.UNKNOWN
    assert result.warning_codes == ("UNKNOWN_PUBLISHED_AT",)


def test_future_and_cross_market_policy_are_blocked() -> None:
    policy = _policy()
    evaluator = freshness.ProviderFreshnessEvaluator()
    future = evaluator.evaluate(
        policy,
        _observation(policy, NOW + timedelta(seconds=1)),
        NOW,
    )
    assert future.status is freshness.ProviderFreshnessStatus.FUTURE_DATA
    with pytest.raises(ValueError, match="SCOPE"):
        evaluator.evaluate(
            policy,
            _observation(policy, NOW).model_copy(update={"market_code": "CN_A"}),
            NOW,
        )
