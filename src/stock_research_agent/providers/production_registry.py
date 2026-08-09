"""Immutable, versioned metadata registry for production Provider adapters."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import Field, field_validator

from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderCredentialStatus,
    ProviderDefinitionStatus,
    ProviderLicenseStatus,
    ProviderLiveValidationStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.schemas import (
    DataDomainCode,
    FrozenProviderContract,
    ProviderCode,
    ProviderDefinitionRecord,
    SemanticVersion,
)

ProviderIdentity = tuple[str, str]


class ProviderAdapterDescriptor(FrozenProviderContract):
    provider_code: ProviderCode
    provider_version: SemanticVersion
    adapter_version: SemanticVersion
    display_name: str = Field(min_length=1, max_length=128)
    data_domain: DataDomainCode
    capability_codes: tuple[str, ...] = Field(min_length=1, max_length=32)
    capability_status: ProviderCapabilityStatus
    definition_status: ProviderDefinitionStatus
    production_status: ProviderProductionStatus
    license_status: ProviderLicenseStatus
    credential_status: ProviderCredentialStatus
    live_status: ProviderLiveValidationStatus
    network_status: Literal["HARD_BLOCKED", "CONTROLLED_ONLY"]
    policy_version: SemanticVersion
    license_policy_version: SemanticVersion
    source_register_version: SemanticVersion

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("display_name must be trimmed and contain no control characters")
        return value

    @field_validator("capability_codes")
    @classmethod
    def validate_capability_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("capability_codes must be unique and sorted")
        if any(
            len(code) > 64
            or len(code) < 3
            or not code[0].isalpha()
            or code != code.upper()
            or not code.replace("_", "").isalnum()
            for code in value
        ):
            raise ValueError("capability_codes must use stable uppercase codes")
        return value


class ProviderRegistryReconciliation(FrozenProviderContract):
    matched_identities: tuple[ProviderIdentity, ...]
    missing_persisted_identities: tuple[ProviderIdentity, ...]
    unregistered_persisted_identities: tuple[ProviderIdentity, ...]
    mismatched_identities: tuple[ProviderIdentity, ...]
    is_consistent: bool


class ProductionProviderRegistry:
    """Register and resolve exact immutable Provider descriptor versions."""

    def __init__(self, descriptors: Iterable[ProviderAdapterDescriptor] = ()) -> None:
        self._descriptors: dict[ProviderIdentity, ProviderAdapterDescriptor] = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: ProviderAdapterDescriptor) -> None:
        identity = (descriptor.provider_code, descriptor.provider_version)
        if identity in self._descriptors:
            raise ValueError("PROVIDER_DESCRIPTOR_DUPLICATE")
        self._descriptors[identity] = descriptor

    def get(
        self,
        provider_code: str,
        provider_version: str,
    ) -> ProviderAdapterDescriptor | None:
        return self._descriptors.get((provider_code, provider_version))

    def list(self) -> tuple[ProviderAdapterDescriptor, ...]:
        return tuple(self._descriptors[identity] for identity in sorted(self._descriptors))

    @property
    def catalog_checksum(self) -> str:
        return provider_checksum(self.list())

    @property
    def catalog_version(self) -> str:
        return f"provider-catalog-v1:{self.catalog_checksum}"

    def reconcile(
        self,
        definitions: Iterable[ProviderDefinitionRecord],
    ) -> ProviderRegistryReconciliation:
        persisted: dict[ProviderIdentity, ProviderDefinitionRecord] = {}
        duplicate_identities: set[ProviderIdentity] = set()
        for definition in definitions:
            identity = (definition.code, definition.definition_version)
            if identity in persisted:
                duplicate_identities.add(identity)
            persisted[identity] = definition

        registered_identities = set(self._descriptors)
        persisted_identities = set(persisted)
        matched: list[ProviderIdentity] = []
        mismatched: list[ProviderIdentity] = list(duplicate_identities)
        for identity in sorted(registered_identities & persisted_identities):
            descriptor = self._descriptors[identity]
            definition = persisted[identity]
            if _definition_matches_descriptor(definition, descriptor):
                matched.append(identity)
            else:
                mismatched.append(identity)
        mismatched_result = tuple(sorted(set(mismatched)))
        missing = tuple(sorted(registered_identities - persisted_identities))
        unregistered = tuple(sorted(persisted_identities - registered_identities))
        return ProviderRegistryReconciliation(
            matched_identities=tuple(matched),
            missing_persisted_identities=missing,
            unregistered_persisted_identities=unregistered,
            mismatched_identities=mismatched_result,
            is_consistent=not missing and not unregistered and not mismatched_result,
        )


def _definition_matches_descriptor(
    definition: ProviderDefinitionRecord,
    descriptor: ProviderAdapterDescriptor,
) -> bool:
    return (
        definition.code == descriptor.provider_code
        and definition.definition_version == descriptor.provider_version
        and definition.adapter_version == descriptor.adapter_version
        and definition.display_name == descriptor.display_name
        and definition.data_domain == descriptor.data_domain
        and definition.definition_status is descriptor.definition_status
        and definition.production_status is descriptor.production_status
        and definition.policy_version == descriptor.policy_version
        and definition.license_policy_version == descriptor.license_policy_version
        and definition.source_register_version == descriptor.source_register_version
    )


__all__ = [
    "ProductionProviderRegistry",
    "ProviderAdapterDescriptor",
    "ProviderRegistryReconciliation",
]
