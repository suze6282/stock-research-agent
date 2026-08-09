from __future__ import annotations

from uuid import uuid4

import pytest

from stock_research_agent.infrastructure.provider_artifact_storage import (
    ArtifactInventoryItem,
    ArtifactReconciliationStatus,
    ProviderArtifactReconciler,
)


class FakeInventory:
    def __init__(self, items: tuple[ArtifactInventoryItem, ...]) -> None:
        self.items = items
        self.limits: list[int] = []
        self.repairs: list[object] = []

    def inspect(self, limit: int) -> tuple[ArtifactInventoryItem, ...]:
        self.limits.append(limit)
        return self.items[:limit]

    def repair(self, item_id: object) -> None:
        self.repairs.append(item_id)


def test_reconciliation_is_bounded_checksum_first_and_path_safe() -> None:
    missing_id, mismatch_id, orphan_id = uuid4(), uuid4(), uuid4()
    inventory = FakeInventory(
        (
            ArtifactInventoryItem(
                item_id=missing_id,
                blob_key="a" * 32,
                database_checksum="1" * 64,
                storage_checksum=None,
                database_present=True,
                storage_present=False,
            ),
            ArtifactInventoryItem(
                item_id=mismatch_id,
                blob_key="b" * 32,
                database_checksum="2" * 64,
                storage_checksum="3" * 64,
                database_present=True,
                storage_present=True,
            ),
            ArtifactInventoryItem(
                item_id=orphan_id,
                blob_key="c" * 32,
                database_checksum=None,
                storage_checksum="4" * 64,
                database_present=False,
                storage_present=True,
            ),
        )
    )
    report = ProviderArtifactReconciler(inventory).inspect(limit=3)
    assert inventory.limits == [3]
    assert tuple(item.status for item in report.items) == (
        ArtifactReconciliationStatus.MISSING_BLOB,
        ArtifactReconciliationStatus.CHECKSUM_MISMATCH,
        ArtifactReconciliationStatus.ORPHAN_BLOB,
    )
    assert all("\\" not in item.blob_key and ":" not in item.blob_key for item in report.items)
    assert inventory.repairs == []


def test_repair_is_explicit_and_requires_deletion_policy() -> None:
    item_id = uuid4()
    inventory = FakeInventory(())
    reconciler = ProviderArtifactReconciler(inventory)
    with pytest.raises(PermissionError, match="DELETION_POLICY"):
        reconciler.repair(item_id, deletion_permitted=False)
    reconciler.repair(item_id, deletion_permitted=True)
    assert inventory.repairs == [item_id]


@pytest.mark.parametrize("limit", (0, 1001))
def test_unbounded_inspection_is_rejected(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        ProviderArtifactReconciler(FakeInventory(())).inspect(limit=limit)
