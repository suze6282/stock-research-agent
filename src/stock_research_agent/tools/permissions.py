"""Stable permission and snapshot-behavior vocabularies for internal tools."""

from enum import StrEnum


class ToolPermission(StrEnum):
    READ_ONLY = "READ_ONLY"
    INTERNAL_WRITE = "INTERNAL_WRITE"
    ADMIN_ONLY = "ADMIN_ONLY"
    FORBIDDEN_FOR_AGENT = "FORBIDDEN_FOR_AGENT"


class SnapshotBehavior(StrEnum):
    SNAPSHOT_OR_AS_OF = "SNAPSHOT_OR_AS_OF"
    SNAPSHOT_REQUIRED = "SNAPSHOT_REQUIRED"
    PERSISTED_METADATA = "PERSISTED_METADATA"


__all__ = ["SnapshotBehavior", "ToolPermission"]
