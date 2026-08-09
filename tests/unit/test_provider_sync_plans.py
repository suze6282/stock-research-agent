from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers.sync import (
    ProviderSyncPlanDraft,
    ProviderSyncSlice,
    build_plan_checksum,
)


def _slice(
    slice_id: str,
    ordinal: int,
    *,
    depends_on: tuple[str, ...] = (),
    parameters: dict[str, object] | None = None,
) -> ProviderSyncSlice:
    return ProviderSyncSlice(
        slice_id=slice_id,
        ordinal=ordinal,
        range_start=date(2026, 7, 1),
        range_end=date(2026, 7, 29),
        depends_on=depends_on,
        request_parameters=parameters or {"page": ordinal + 1},
    )


def _plan(*slices: ProviderSyncSlice) -> ProviderSyncPlanDraft:
    return ProviderSyncPlanDraft(
        sync_request_id=uuid4(),
        adapter_version="1.0.0",
        catalog_version="1.0.0",
        checkpoint_revision=3,
        slices=slices,
    )


def test_plan_checksum_is_stable_for_same_finite_ordered_input() -> None:
    request_id = uuid4()
    slices = (_slice("FIRST", 0), _slice("SECOND", 1, depends_on=("FIRST",)))
    first = ProviderSyncPlanDraft(
        sync_request_id=request_id,
        adapter_version="1.0.0",
        catalog_version="1.0.0",
        checkpoint_revision=3,
        slices=slices,
    )
    second = ProviderSyncPlanDraft.model_validate(first.model_dump())
    assert build_plan_checksum(first) == build_plan_checksum(second)
    assert first.to_write().plan_checksum == build_plan_checksum(first)
    assert first.to_write().slices[0]["slice_id"] == "FIRST"


@pytest.mark.parametrize(
    "slices",
    [
        (_slice("SAME", 0), _slice("SAME", 1)),
        (_slice("SECOND", 0, depends_on=("FIRST",)), _slice("FIRST", 1)),
        (_slice("FIRST", 0, depends_on=("MISSING",)),),
        (_slice("FIRST", 1),),
    ],
)
def test_plan_rejects_duplicate_cycle_unknown_or_nondeterministic_order(
    slices: tuple[ProviderSyncSlice, ...],
) -> None:
    with pytest.raises(ValidationError):
        _plan(*slices)


def test_slice_rejects_self_dependency() -> None:
    with pytest.raises(ValidationError):
        _slice("SELF", 0, depends_on=("SELF",))


@pytest.mark.parametrize(
    "parameters",
    [
        {"security_id": str(uuid4())},
        {"snapshot_id": str(uuid4())},
        {"research_as_of_time": "2026-07-30T00:00:00Z"},
        {"url": "https://example.com"},
        {"sql": "SELECT 1"},
    ],
)
def test_slice_cannot_override_context_or_supply_arbitrary_io(
    parameters: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="CONTEXT|ARBITRARY"):
        _slice("FIRST", 0, parameters=parameters)


def test_plan_has_hard_slice_limit() -> None:
    with pytest.raises(ValidationError):
        ProviderSyncPlanDraft(
            sync_request_id=uuid4(),
            adapter_version="1.0.0",
            catalog_version="1.0.0",
            checkpoint_revision=None,
            slices=tuple(_slice(f"S{index}", index) for index in range(10_001)),
        )
