"""Process-local provider response cache contracts."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from stock_research_agent.db.models.providers import (
    ProviderCacheEntry,
    ProviderRawArtifact,
)
from stock_research_agent.domain.providers.canonical import provider_checksum


@dataclass(frozen=True, slots=True)
class CachedResponse:
    """Body and validators retained for conditional GET requests."""

    body: bytes
    content_type: str | None
    etag: str | None
    last_modified: str | None


class ResponseCache(Protocol):
    """Minimal cache used by the HTTP boundary."""

    def get(self, key: str) -> CachedResponse | None:
        """Return a cached response when ``key`` exists."""

    def put(self, key: str, response: CachedResponse) -> None:
        """Store ``response`` under ``key``."""


class InMemoryResponseCache:
    """Thread-safe cache whose lifetime is bounded by the current process."""

    def __init__(self) -> None:
        self._responses: dict[str, CachedResponse] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> CachedResponse | None:
        """Return a cached response when ``key`` exists."""
        with self._lock:
            return self._responses.get(key)

    def put(self, key: str, response: CachedResponse) -> None:
        """Store ``response`` under ``key``."""
        with self._lock:
            self._responses[key] = response


class ProviderCacheStatus(StrEnum):
    HIT = "HIT"
    MISS = "MISS"
    STORED = "STORED"
    BLOCKED = "BLOCKED"


class ProviderCacheKey(BaseModel):
    """Governance-complete identity for operational response reuse."""

    model_config = ConfigDict(frozen=True)

    provider_definition_id: UUID
    provider_capability_id: UUID
    license_policy_id: UUID
    adapter_version: str = Field(min_length=1, max_length=32)
    policy_version: str = Field(min_length=1, max_length=32)
    license_policy_version: str = Field(min_length=1, max_length=32)
    request_identity: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def checksum(self) -> str:
        return provider_checksum(self)


class ProviderCacheDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ProviderCacheStatus
    artifact_id: UUID | None = None
    artifact_checksum: str | None = None
    expires_at: datetime | None = None
    reason_code: str | None = None

    @field_validator("artifact_checksum")
    @classmethod
    def _checksum(cls, value: str | None) -> str | None:
        if value is not None and (
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError("artifact_checksum must be lowercase SHA-256")
        return value


@dataclass(frozen=True, slots=True)
class ProviderCacheRecord:
    key: ProviderCacheKey
    artifact_id: UUID
    artifact_checksum: str
    expires_at: datetime
    created_at: datetime


class ProviderCacheStore(Protocol):
    def get(self, key: ProviderCacheKey) -> ProviderCacheRecord | None: ...

    def upsert(self, record: ProviderCacheRecord) -> ProviderCacheRecord: ...


class ProviderCacheService:
    """Operate an expiring cache without promoting entries to evidence."""

    def __init__(self, store: ProviderCacheStore) -> None:
        self._store = store

    def get(self, key: ProviderCacheKey, *, now: datetime) -> ProviderCacheDecision:
        now = _utc(now)
        record = self._store.get(key)
        if record is None or _utc(record.expires_at) <= now:
            return ProviderCacheDecision(
                status=ProviderCacheStatus.MISS,
                reason_code="CACHE_MISS",
            )
        return ProviderCacheDecision(
            status=ProviderCacheStatus.HIT,
            artifact_id=record.artifact_id,
            artifact_checksum=record.artifact_checksum,
            expires_at=_utc(record.expires_at),
        )

    def put(
        self,
        key: ProviderCacheKey,
        *,
        artifact_id: UUID,
        artifact_checksum: str,
        expires_at: datetime,
        now: datetime,
        cache_permitted: bool,
    ) -> ProviderCacheDecision:
        now = _utc(now)
        expires_at = _utc(expires_at)
        if not cache_permitted:
            return ProviderCacheDecision(
                status=ProviderCacheStatus.BLOCKED,
                reason_code="LICENSE_CACHE_PROHIBITED",
            )
        if expires_at <= now:
            return ProviderCacheDecision(
                status=ProviderCacheStatus.BLOCKED,
                reason_code="INVALID_CACHE_EXPIRY",
            )
        decision = ProviderCacheDecision(
            status=ProviderCacheStatus.STORED,
            artifact_id=artifact_id,
            artifact_checksum=artifact_checksum,
            expires_at=expires_at,
        )
        self._store.upsert(
            ProviderCacheRecord(
                key=key,
                artifact_id=artifact_id,
                artifact_checksum=artifact_checksum,
                expires_at=expires_at,
                created_at=now,
            )
        )
        return decision


class InMemoryProviderCacheStore:
    def __init__(self) -> None:
        self._records: dict[str, ProviderCacheRecord] = {}
        self._lock = threading.Lock()

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._records)

    def get(self, key: ProviderCacheKey) -> ProviderCacheRecord | None:
        with self._lock:
            return self._records.get(key.checksum)

    def upsert(self, record: ProviderCacheRecord) -> ProviderCacheRecord:
        with self._lock:
            self._records[record.key.checksum] = record
        return record


class PostgresProviderCacheStore:
    """Transaction-neutral cache store with an atomic pointer upsert."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, key: ProviderCacheKey) -> ProviderCacheRecord | None:
        row = self._session.execute(
            select(ProviderCacheEntry, ProviderRawArtifact.source_checksum)
            .join(
                ProviderRawArtifact,
                ProviderRawArtifact.id == ProviderCacheEntry.artifact_id,
            )
            .where(
                ProviderCacheEntry.provider_definition_id == key.provider_definition_id,
                ProviderCacheEntry.provider_capability_id == key.provider_capability_id,
                ProviderCacheEntry.license_policy_id == key.license_policy_id,
                ProviderCacheEntry.cache_key == key.checksum,
            )
        ).one_or_none()
        if row is None:
            return None
        entry, artifact_checksum = row
        return ProviderCacheRecord(
            key=key,
            artifact_id=entry.artifact_id,
            artifact_checksum=artifact_checksum,
            expires_at=_utc(entry.expires_at),
            created_at=_utc(entry.created_at),
        )

    def upsert(self, record: ProviderCacheRecord) -> ProviderCacheRecord:
        artifact_checksum = self._session.scalar(
            select(ProviderRawArtifact.source_checksum).where(
                ProviderRawArtifact.id == record.artifact_id,
                ProviderRawArtifact.provider_definition_id == record.key.provider_definition_id,
                ProviderRawArtifact.provider_capability_id == record.key.provider_capability_id,
                ProviderRawArtifact.license_policy_id == record.key.license_policy_id,
            )
        )
        if artifact_checksum != record.artifact_checksum:
            raise ValueError("cache artifact lineage or checksum does not match")
        statement = insert(ProviderCacheEntry).values(
            id=uuid4(),
            provider_definition_id=record.key.provider_definition_id,
            provider_capability_id=record.key.provider_capability_id,
            license_policy_id=record.key.license_policy_id,
            artifact_id=record.artifact_id,
            cache_key=record.key.checksum,
            expires_at=record.expires_at,
            created_at=record.created_at,
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_provider_cache_entries_key",
            set_={
                "artifact_id": statement.excluded.artifact_id,
                "expires_at": statement.excluded.expires_at,
            },
        )
        self._session.execute(statement)
        self._session.flush()
        return record


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone")
    return value.astimezone(UTC)
