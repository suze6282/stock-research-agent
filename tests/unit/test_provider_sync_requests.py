from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers.sync import (
    ProviderExecutionMode,
    ProviderSyncRequestWrite,
)


def _request(**changes: object) -> ProviderSyncRequestWrite:
    values: dict[str, object] = {
        "provider_definition_id": uuid4(),
        "provider_capability_id": uuid4(),
        "policy_id": uuid4(),
        "license_policy_id": uuid4(),
        "credential_reference_id": None,
        "security_id": uuid4(),
        "universe_code": None,
        "research_as_of_time": datetime(2026, 7, 29, tzinfo=UTC),
        "range_start": date(2026, 7, 1),
        "range_end": date(2026, 7, 29),
        "execution_mode": ProviderExecutionMode.OFFLINE,
        "scope": {"security_scope": "EXACT"},
        "budget": {
            "max_requests": 10,
            "max_bytes": 1_000_000,
            "max_attempts": 2,
            "max_duration_seconds": 60,
        },
        "request_checksum": "a" * 64,
        "idempotency_key": "b" * 64,
    }
    values.update(changes)
    return ProviderSyncRequestWrite.model_validate(values)


def test_sync_request_requires_explicit_credential_reference_or_none() -> None:
    values = _request().model_dump()
    del values["credential_reference_id"]
    with pytest.raises(ValidationError):
        ProviderSyncRequestWrite.model_validate(values)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("universe_code", "LATEST", "LATEST"),
        ("range_end", date(2026, 7, 30), "FUTURE"),
        ("scope", {"url": "https://example.com/data"}, "ARBITRARY"),
        ("scope", {"path": "C:\\private\\data"}, "ARBITRARY"),
        ("scope", {"query": "SELECT * FROM secrets"}, "ARBITRARY"),
        ("budget", {}, "BUDGET"),
        ("budget", {"max_requests": 10}, "BUDGET"),
    ],
)
def test_sync_request_rejects_open_future_or_arbitrary_scope(
    field: str,
    value: object,
    message: str,
) -> None:
    changes: dict[str, object] = {field: value}
    if field == "universe_code":
        changes["security_id"] = None
    with pytest.raises(ValidationError, match=message):
        _request(**changes)


def test_sync_request_is_frozen_and_has_finite_exact_budget() -> None:
    request = _request()
    assert request.budget == {
        "max_requests": 10,
        "max_bytes": 1_000_000,
        "max_attempts": 2,
        "max_duration_seconds": 60,
    }
    with pytest.raises(ValidationError):
        request.range_end = date(2026, 7, 28)
