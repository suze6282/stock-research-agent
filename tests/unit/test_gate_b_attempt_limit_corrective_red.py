from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers.enums import ProviderSyncSliceStatus
from stock_research_agent.domain.providers.sync import ProviderRequestAttemptWrite


def _generic_attempt(attempt_number: int) -> ProviderRequestAttemptWrite:
    return ProviderRequestAttemptWrite(
        sync_run_id=uuid4(),
        slice_id="GENERIC_PROVIDER_SLICE",
        attempt_number=attempt_number,
        status=ProviderSyncSliceStatus.PENDING,
        endpoint_id="GENERIC_PROVIDER_ENDPOINT",
        response_bytes=0,
        started_at=datetime(2026, 8, 22, tzinfo=UTC),
    )


@pytest.mark.parametrize("attempt_number", (1, 2, 3))
def test_red_064_generic_provider_accepts_only_pre_gate_b_attempt_range(
    attempt_number: int,
) -> None:
    assert _generic_attempt(attempt_number).attempt_number == attempt_number


def test_red_064_generic_provider_rejects_gate_b_only_attempt_four() -> None:
    with pytest.raises(ValidationError):
        _generic_attempt(4)
