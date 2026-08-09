from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from stock_research_agent.domain.providers.enums import ProviderCredentialStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
    SemanticVersion,
)

_FORBIDDEN_METADATA_FIELDS = frozenset(
    {
        "value",
        "secret",
        "token",
        "api_key",
        "password",
        "prefix",
        "suffix",
        "hash",
        "cookie",
        "authorization",
    }
)


class CredentialResolverKind(StrEnum):
    NONE = "NONE"
    ENVIRONMENT = "ENVIRONMENT"


class CredentialReferenceWrite(FrozenProviderContract):
    provider_definition_id: UUID
    reference_version: SemanticVersion
    resolver_kind: CredentialResolverKind
    declared_name: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    status: ProviderCredentialStatus
    safe_label: str = Field(min_length=1, max_length=128)

    @field_validator("safe_label")
    @classmethod
    def validate_safe_label(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("safe_label must not contain outer whitespace")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("safe_label must not contain control characters")
        return value

    @model_validator(mode="after")
    def validate_resolver_slot(self) -> CredentialReferenceWrite:
        if self.resolver_kind is CredentialResolverKind.NONE:
            if self.declared_name is not None:
                raise ValueError("NONE resolver must not declare an environment name")
            if self.status is not ProviderCredentialStatus.NOT_REQUIRED:
                raise ValueError("NONE resolver requires NOT_REQUIRED status")
        else:
            if self.declared_name is None:
                raise ValueError("ENVIRONMENT resolver requires one declared name")
            if self.status is ProviderCredentialStatus.NOT_REQUIRED:
                raise ValueError("ENVIRONMENT resolver cannot use NOT_REQUIRED status")
        return self


class CredentialReferenceRecord(CredentialReferenceWrite):
    id: UUID
    checksum: Checksum
    created_at: AwareUtcDateTime


class CredentialRequirement(FrozenProviderContract):
    provider_definition_id: UUID
    required: bool
    resolver_kind: CredentialResolverKind
    declared_names: tuple[str, ...] = Field(default=(), max_length=8)

    @field_validator("declared_names")
    @classmethod
    def validate_declared_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("declared_names must be unique and sorted")
        for item in value:
            if (
                not 3 <= len(item) <= 64
                or item != item.upper()
                or any(
                    character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for character in item
                )
            ):
                raise ValueError("declared_names must use stable uppercase names")
        return value

    @model_validator(mode="after")
    def validate_requirement(self) -> CredentialRequirement:
        if self.resolver_kind is CredentialResolverKind.NONE:
            if self.required or self.declared_names:
                raise ValueError("NONE resolver cannot require credential names")
        elif not self.required or not self.declared_names:
            raise ValueError("credential resolver requires declared names")
        return self


def validate_credential_reference_metadata(value: Mapping[str, object]) -> None:
    """Reject any metadata shape capable of carrying secret material."""

    forbidden = _FORBIDDEN_METADATA_FIELDS.intersection(key.casefold() for key in value)
    if forbidden:
        raise ValueError(f"forbidden credential metadata field: {sorted(forbidden)[0]}")
