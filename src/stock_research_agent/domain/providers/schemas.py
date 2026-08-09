from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from stock_research_agent.domain.providers.enums import (
    ProviderDefinitionStatus,
    ProviderProductionStatus,
)

_DOMAIN_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("datetime must use an aware UTC timezone")
    return value.astimezone(UTC)


AwareUtcDateTime = Annotated[datetime, AfterValidator(_aware_utc)]
Checksum = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ProviderCode = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")]
DataDomainCode = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")]
SemanticVersion = Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]


class FrozenProviderContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class ProviderDefinitionWrite(FrozenProviderContract):
    code: ProviderCode
    definition_version: SemanticVersion
    adapter_version: SemanticVersion
    display_name: str = Field(min_length=1, max_length=128)
    data_domain: DataDomainCode
    definition_status: ProviderDefinitionStatus
    production_status: ProviderProductionStatus
    official_domains: tuple[str, ...] = Field(min_length=1, max_length=16)
    policy_version: SemanticVersion
    license_policy_version: SemanticVersion
    credential_reference_id: UUID | None
    source_register_version: SemanticVersion

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("display_name must not contain outer whitespace")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("display_name must not contain control characters")
        return value

    @field_validator("official_domains")
    @classmethod
    def validate_official_domains(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("official_domains must be unique and sorted")
        for domain in value:
            if len(domain) > 253 or _DOMAIN_PATTERN.fullmatch(domain) is None:
                raise ValueError("official_domains must contain exact lowercase DNS names")
        return value


class ProviderDefinitionRecord(ProviderDefinitionWrite):
    id: UUID
    checksum: Checksum
    created_at: AwareUtcDateTime
