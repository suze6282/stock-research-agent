from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from pydantic import Field, field_validator

from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderDefinitionStatus,
)
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    DataDomainCode,
    FrozenProviderContract,
    ProviderDefinitionRecord,
    SemanticVersion,
)

CapabilityCode = str
_CODE_PATTERN = r"^[A-Z][A-Z0-9_]{2,63}$"


class ProviderCapabilityWrite(FrozenProviderContract):
    provider_definition_id: UUID
    code: CapabilityCode = Field(pattern=_CODE_PATTERN)
    capability_version: SemanticVersion
    status: ProviderCapabilityStatus
    data_domain: DataDomainCode
    market_codes: tuple[str, ...] = Field(min_length=1, max_length=32)
    security_types: tuple[str, ...] = Field(min_length=1, max_length=32)
    operations: tuple[str, ...] = Field(min_length=1, max_length=32)

    @field_validator("market_codes", "security_types", "operations")
    @classmethod
    def validate_code_allowlist(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("allowlist values must be unique and sorted")
        if any(
            len(item) > 64
            or len(item) < 3
            or not item[0].isalpha()
            or not item.replace("_", "").isalnum()
            or item != item.upper()
            for item in value
        ):
            raise ValueError("allowlist values must use stable uppercase codes")
        return value


class ProviderCapabilityRecord(ProviderCapabilityWrite):
    id: UUID
    checksum: Checksum
    created_at: AwareUtcDateTime


class CapabilityDecision(FrozenProviderContract):
    allowed: bool
    reason_code: str = Field(pattern=_CODE_PATTERN)
    status: ProviderCapabilityStatus | None
    capability_id: UUID | None


class ProviderCapabilityGate:
    """Resolve only an exact Provider, capability code, and capability version."""

    def __init__(self, capabilities: Iterable[ProviderCapabilityRecord]) -> None:
        entries: dict[tuple[UUID, str, str], ProviderCapabilityRecord] = {}
        for capability in capabilities:
            key = (
                capability.provider_definition_id,
                capability.code,
                capability.capability_version,
            )
            if key in entries:
                raise ValueError("duplicate Provider capability identity")
            entries[key] = capability
        self._entries = entries

    def evaluate(
        self,
        definition: ProviderDefinitionRecord,
        capability_code: str,
        capability_version: str,
    ) -> CapabilityDecision:
        if definition.definition_status is not ProviderDefinitionStatus.ACTIVE:
            return CapabilityDecision(
                allowed=False,
                reason_code="PROVIDER_DEFINITION_NOT_ACTIVE",
                status=None,
                capability_id=None,
            )
        capability = self._entries.get((definition.id, capability_code, capability_version))
        if capability is None:
            return CapabilityDecision(
                allowed=False,
                reason_code="CAPABILITY_NOT_ALLOWLISTED",
                status=None,
                capability_id=None,
            )
        if capability.status in {
            ProviderCapabilityStatus.BLOCKED,
            ProviderCapabilityStatus.RETIRED,
        }:
            return CapabilityDecision(
                allowed=False,
                reason_code=f"CAPABILITY_{capability.status.value}",
                status=capability.status,
                capability_id=capability.id,
            )
        return CapabilityDecision(
            allowed=True,
            reason_code="CAPABILITY_EXACT_MATCH",
            status=capability.status,
            capability_id=capability.id,
        )
