"""Immutable Provider raw-artifact storage over the hardened blob port."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.providers.artifacts import ProviderRawArtifactDraft
from stock_research_agent.domain.providers.schemas import Checksum, FrozenProviderContract
from stock_research_agent.infrastructure.blob_storage import BlobStorage


class StoredProviderArtifact(FrozenProviderContract):
    blob_key: str = Field(pattern=r"^[0-9a-f]{32}$")
    storage_uri: str
    checksum: Checksum
    byte_count: int = Field(ge=0, le=52_428_800)
    content_type: str


class AtomicProviderArtifactStorage:
    """Preserve exact bytes; the injected blob implementation owns atomic durability."""

    def __init__(self, storage: BlobStorage) -> None:
        self._storage = storage

    def write(
        self,
        draft: ProviderRawArtifactDraft,
        content: bytes,
    ) -> StoredProviderArtifact:
        if not draft.store_raw_permitted:
            raise PermissionError("RAW_STORAGE_PROHIBITED")
        checksum = hashlib.sha256(content).hexdigest()
        if draft.expected_checksum is not None and checksum != draft.expected_checksum:
            raise ValueError("RAW_ARTIFACT_CHECKSUM_MISMATCH")
        metadata = self._storage.put(
            content,
            content_type=draft.content_type,
            metadata={"artifact_kind": "provider_raw"},
        )
        key = urlsplit(metadata.uri).path.removeprefix("/")
        if metadata.checksum_sha256 != checksum or metadata.size_bytes != len(content):
            raise ValueError("RAW_ARTIFACT_DURABILITY_MISMATCH")
        return StoredProviderArtifact(
            blob_key=key,
            storage_uri=metadata.uri,
            checksum=checksum,
            byte_count=len(content),
            content_type=draft.content_type,
        )

    def read(self, artifact: StoredProviderArtifact) -> bytes:
        content = self._storage.get(artifact.storage_uri)
        if len(content) != artifact.byte_count:
            raise ValueError("RAW_ARTIFACT_SIZE_MISMATCH")
        if hashlib.sha256(content).hexdigest() != artifact.checksum:
            raise ValueError("RAW_ARTIFACT_CHECKSUM_MISMATCH")
        return content


class ArtifactReconciliationStatus(StrEnum):
    CONSISTENT = "CONSISTENT"
    MISSING_BLOB = "MISSING_BLOB"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    ORPHAN_BLOB = "ORPHAN_BLOB"


class ArtifactInventoryItem(FrozenProviderContract):
    item_id: UUID
    blob_key: str = Field(pattern=r"^[0-9a-f]{32}$")
    database_checksum: Checksum | None
    storage_checksum: Checksum | None
    database_present: bool
    storage_present: bool


class ArtifactReconciliationItem(FrozenProviderContract):
    item_id: UUID
    blob_key: str = Field(pattern=r"^[0-9a-f]{32}$")
    status: ArtifactReconciliationStatus


class ArtifactReconciliationReport(FrozenProviderContract):
    inspected_count: int = Field(ge=0, le=1000)
    items: tuple[ArtifactReconciliationItem, ...]


class ProviderArtifactInventory(Protocol):
    def inspect(self, limit: int) -> tuple[ArtifactInventoryItem, ...]: ...

    def repair(self, item_id: UUID) -> None: ...


class ProviderArtifactReconciler:
    """Bounded inspection with no implicit mutation or path disclosure."""

    def __init__(self, inventory: ProviderArtifactInventory) -> None:
        self._inventory = inventory

    def inspect(self, limit: int) -> ArtifactReconciliationReport:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        items = self._inventory.inspect(limit)
        results = tuple(
            ArtifactReconciliationItem(
                item_id=item.item_id,
                blob_key=item.blob_key,
                status=_reconciliation_status(item),
            )
            for item in items
        )
        return ArtifactReconciliationReport(
            inspected_count=len(results),
            items=results,
        )

    def repair(self, item_id: UUID, *, deletion_permitted: bool) -> None:
        if not deletion_permitted:
            raise PermissionError("DELETION_POLICY_REQUIRED")
        self._inventory.repair(item_id)


def _reconciliation_status(item: ArtifactInventoryItem) -> ArtifactReconciliationStatus:
    if item.database_present and not item.storage_present:
        return ArtifactReconciliationStatus.MISSING_BLOB
    if item.storage_present and not item.database_present:
        return ArtifactReconciliationStatus.ORPHAN_BLOB
    if item.database_checksum != item.storage_checksum:
        return ArtifactReconciliationStatus.CHECKSUM_MISMATCH
    return ArtifactReconciliationStatus.CONSISTENT
