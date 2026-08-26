"""Bounded query-only projections for controlled evidence records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from pydantic import JsonValue


class LiveEvidenceQueryRepository(Protocol):
    def query_view(
        self,
        resource_type: str,
        resource_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> Mapping[str, JsonValue] | None: ...


class LiveEvidenceQueryService:
    def __init__(self, repository: LiveEvidenceQueryRepository) -> None:
        self._repository = repository

    def query(
        self,
        resource_type: str,
        resource_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> dict[str, JsonValue] | None:
        value = self._repository.query_view(
            resource_type,
            resource_id,
            limit=limit,
            offset=offset,
        )
        return None if value is None else dict(value)
