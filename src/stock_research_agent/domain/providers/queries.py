"""Read-only safe Provider governance query service."""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field, JsonValue, ValidationError, field_validator, model_validator

from stock_research_agent.domain.providers.schemas import FrozenProviderContract

_FORBIDDEN_KEY_PARTS = frozenset(
    {
        "authorization",
        "blob_key",
        "connection_string",
        "cookie",
        "credential_value",
        "database_url",
        "headers",
        "password",
        "raw_payload",
        "secret",
        "sql",
        "storage_uri",
        "token",
    }
)
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


class ProviderQueryResource(StrEnum):
    PROVIDER = "PROVIDER"
    CAPABILITY = "CAPABILITY"
    POLICY = "POLICY"
    LICENSE = "LICENSE"
    HEALTH = "HEALTH"
    CIRCUIT = "CIRCUIT"
    SYNC_RUN = "SYNC_RUN"
    ATTEMPT = "ATTEMPT"
    ARTIFACT = "ARTIFACT"
    CHECKPOINT = "CHECKPOINT"
    QUALITY_ISSUE = "QUALITY_ISSUE"
    DEAD_LETTER = "DEAD_LETTER"
    READINESS = "READINESS"


class PageRequest(FrozenProviderContract):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=100_000)
    sort: Literal["STABLE_ASC"] = "STABLE_ASC"


class SafeProviderProjection(FrozenProviderContract):
    resource_type: ProviderQueryResource
    values: dict[str, JsonValue] = Field(max_length=128)

    @field_validator("values")
    @classmethod
    def validate_safe_values(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        _validate_safe_mapping(value)
        return value


class ProviderQueryPage(FrozenProviderContract):
    items: tuple[SafeProviderProjection, ...] = Field(max_length=100)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0, le=100_000)
    returned: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_count(self) -> ProviderQueryPage:
        if self.returned != len(self.items):
            raise ValueError("returned must equal item count")
        return self


class ProviderSafeQueryRepository(Protocol):
    def list_provider_views(
        self, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]: ...

    def get_provider_view(self, provider_code: str) -> Mapping[str, object] | None: ...

    def list_capability_views(
        self, provider_code: str, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]: ...

    def get_policy_view(self, provider_code: str) -> Mapping[str, object] | None: ...

    def get_license_view(self, provider_code: str) -> Mapping[str, object] | None: ...

    def get_health_view(self, provider_code: str) -> Mapping[str, object] | None: ...

    def get_circuit_view(self, provider_code: str) -> Mapping[str, object] | None: ...

    def get_sync_run_view(self, run_id: UUID) -> Mapping[str, object] | None: ...

    def list_attempt_views(
        self, run_id: UUID, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]: ...

    def list_artifact_views(
        self, run_id: UUID, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]: ...

    def list_checkpoint_views(
        self, provider_code: str, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]: ...

    def list_quality_issue_views(
        self, run_id: UUID, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]: ...

    def list_dead_letter_views(
        self, run_id: UUID, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]: ...

    def get_readiness_view(self, security_id: UUID) -> Mapping[str, object] | None: ...


class ProviderQueryService:
    """Validate and return persisted metadata without probes or hidden writes."""

    def __init__(self, repository: ProviderSafeQueryRepository) -> None:
        self._repository = repository

    def list_providers(self, page: PageRequest) -> ProviderQueryPage:
        return self._page(
            self._repository.list_provider_views(limit=page.limit, offset=page.offset),
            ProviderQueryResource.PROVIDER,
            page,
        )

    def get_provider(self, provider_code: str) -> SafeProviderProjection | None:
        return self._one(
            self._repository.get_provider_view(provider_code), ProviderQueryResource.PROVIDER
        )

    def list_capabilities(self, provider_code: str, page: PageRequest) -> ProviderQueryPage:
        return self._page(
            self._repository.list_capability_views(
                provider_code,
                limit=page.limit,
                offset=page.offset,
            ),
            ProviderQueryResource.CAPABILITY,
            page,
        )

    def get_policy(self, provider_code: str) -> SafeProviderProjection | None:
        return self._one(
            self._repository.get_policy_view(provider_code), ProviderQueryResource.POLICY
        )

    def get_license(self, provider_code: str) -> SafeProviderProjection | None:
        return self._one(
            self._repository.get_license_view(provider_code), ProviderQueryResource.LICENSE
        )

    def get_health(self, provider_code: str) -> SafeProviderProjection | None:
        return self._one(
            self._repository.get_health_view(provider_code), ProviderQueryResource.HEALTH
        )

    def get_circuit(self, provider_code: str) -> SafeProviderProjection | None:
        return self._one(
            self._repository.get_circuit_view(provider_code), ProviderQueryResource.CIRCUIT
        )

    def get_sync_run(self, run_id: UUID) -> SafeProviderProjection | None:
        return self._one(self._repository.get_sync_run_view(run_id), ProviderQueryResource.SYNC_RUN)

    def list_attempts(self, run_id: UUID, page: PageRequest) -> ProviderQueryPage:
        return self._page(
            self._repository.list_attempt_views(run_id, limit=page.limit, offset=page.offset),
            ProviderQueryResource.ATTEMPT,
            page,
        )

    def list_artifacts(self, run_id: UUID, page: PageRequest) -> ProviderQueryPage:
        return self._page(
            self._repository.list_artifact_views(run_id, limit=page.limit, offset=page.offset),
            ProviderQueryResource.ARTIFACT,
            page,
        )

    def list_checkpoints(self, provider_code: str, page: PageRequest) -> ProviderQueryPage:
        return self._page(
            self._repository.list_checkpoint_views(
                provider_code,
                limit=page.limit,
                offset=page.offset,
            ),
            ProviderQueryResource.CHECKPOINT,
            page,
        )

    def list_quality_issues(self, run_id: UUID, page: PageRequest) -> ProviderQueryPage:
        return self._page(
            self._repository.list_quality_issue_views(
                run_id,
                limit=page.limit,
                offset=page.offset,
            ),
            ProviderQueryResource.QUALITY_ISSUE,
            page,
        )

    def list_dead_letters(self, run_id: UUID, page: PageRequest) -> ProviderQueryPage:
        return self._page(
            self._repository.list_dead_letter_views(
                run_id,
                limit=page.limit,
                offset=page.offset,
            ),
            ProviderQueryResource.DEAD_LETTER,
            page,
        )

    def get_readiness(self, security_id: UUID) -> SafeProviderProjection | None:
        return self._one(
            self._repository.get_readiness_view(security_id),
            ProviderQueryResource.READINESS,
        )

    def _page(
        self,
        values: tuple[Mapping[str, object], ...],
        resource_type: ProviderQueryResource,
        page: PageRequest,
    ) -> ProviderQueryPage:
        items = tuple(self._projection(value, resource_type) for value in values)
        return ProviderQueryPage(
            items=items,
            limit=page.limit,
            offset=page.offset,
            returned=len(items),
        )

    def _one(
        self,
        value: Mapping[str, object] | None,
        resource_type: ProviderQueryResource,
    ) -> SafeProviderProjection | None:
        return None if value is None else self._projection(value, resource_type)

    @staticmethod
    def _projection(
        value: Mapping[str, object],
        resource_type: ProviderQueryResource,
    ) -> SafeProviderProjection:
        raw_resource_type = value.get("resource_type")
        if raw_resource_type not in {resource_type, resource_type.value}:
            raise ValueError("PROVIDER_QUERY_RESOURCE_MISMATCH")
        raw_values = value.get("values")
        if not isinstance(raw_values, Mapping):
            raise ValueError("PROVIDER_QUERY_UNSAFE_PROJECTION")
        try:
            projection = SafeProviderProjection(
                resource_type=resource_type,
                values=dict(raw_values),
            )
        except ValidationError:
            raise ValueError("PROVIDER_QUERY_UNSAFE_PROJECTION") from None
        return projection


def _validate_safe_mapping(value: Mapping[str, JsonValue]) -> None:
    for key, item in value.items():
        normalized = key.casefold()
        if any(part in normalized for part in _FORBIDDEN_KEY_PARTS):
            raise ValueError("sensitive Provider field is forbidden")
        _validate_safe_value(item)


def _validate_safe_value(value: JsonValue) -> None:
    if isinstance(value, str):
        if _WINDOWS_PATH.match(value) or value.startswith(("/", "\\\\")):
            raise ValueError("local path is forbidden")
        return
    if isinstance(value, dict):
        _validate_safe_mapping(value)
        return
    if isinstance(value, list):
        for item in value:
            _validate_safe_value(item)


__all__ = [
    "PageRequest",
    "ProviderQueryPage",
    "ProviderQueryResource",
    "ProviderQueryService",
    "ProviderSafeQueryRepository",
    "SafeProviderProjection",
]
