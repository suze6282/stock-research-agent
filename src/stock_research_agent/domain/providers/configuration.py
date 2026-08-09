from __future__ import annotations

from pydantic import Field

from stock_research_agent.domain.providers.capabilities import ProviderCapabilityRecord
from stock_research_agent.domain.providers.credentials import (
    CredentialReferenceRecord,
    CredentialResolverKind,
)
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderConfigurationStatus,
    ProviderDefinitionStatus,
    ProviderLicenseStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.licenses import SourceLicensePolicyRecord
from stock_research_agent.domain.providers.policies import ProviderPolicyRecord
from stock_research_agent.domain.providers.schemas import (
    FrozenProviderContract,
    ProviderDefinitionRecord,
    SemanticVersion,
)


class ProviderConfiguration(FrozenProviderContract):
    capability_version: SemanticVersion
    endpoint_policy_version: SemanticVersion
    requested_retention_days: int | None = Field(default=None, ge=1, le=36_500)
    network_requested: bool
    allowed_credential_resolvers: tuple[CredentialResolverKind, ...] = (
        CredentialResolverKind.NONE,
    )


class ConfigurationDecision(FrozenProviderContract):
    allowed: bool
    status: ProviderConfigurationStatus
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=16)


class ProviderConfigurationGate:
    """Validate only supplied immutable metadata; never resolve credentials."""

    @staticmethod
    def validate(
        configuration: ProviderConfiguration,
        definition: ProviderDefinitionRecord,
        capability: ProviderCapabilityRecord,
        policy: ProviderPolicyRecord,
        license_policy: SourceLicensePolicyRecord,
        credential_reference: CredentialReferenceRecord,
    ) -> ConfigurationDecision:
        reasons: list[str] = []
        if definition.definition_status is not ProviderDefinitionStatus.ACTIVE:
            reasons.append("PROVIDER_DEFINITION_NOT_ACTIVE")
        if definition.production_status is ProviderProductionStatus.BLOCKED:
            reasons.append("PROVIDER_BLOCKED")

        provider_ids = {
            definition.id,
            capability.provider_definition_id,
            policy.provider_definition_id,
            license_policy.provider_definition_id,
            credential_reference.provider_definition_id,
        }
        if len(provider_ids) != 1:
            reasons.append("PROVIDER_IDENTITY_MISMATCH")
        if capability.capability_version != configuration.capability_version:
            reasons.append("CAPABILITY_VERSION_MISMATCH")
        if capability.status in {
            ProviderCapabilityStatus.BLOCKED,
            ProviderCapabilityStatus.RETIRED,
        }:
            reasons.append("CAPABILITY_NOT_AVAILABLE")
        if policy.policy_version != definition.policy_version:
            reasons.append("PROVIDER_POLICY_VERSION_MISMATCH")
        if policy.endpoint_policy_version != configuration.endpoint_policy_version:
            reasons.append("ENDPOINT_POLICY_VERSION_MISMATCH")
        if license_policy.policy_version != definition.license_policy_version:
            reasons.append("LICENSE_POLICY_VERSION_MISMATCH")
        if license_policy.status is not ProviderLicenseStatus.APPROVED:
            reasons.append("LICENSE_NOT_APPROVED")
        if configuration.network_requested and not policy.network_enabled:
            reasons.append("PROVIDER_POLICY_NETWORK_DISABLED")
        if (
            configuration.requested_retention_days is not None
            and policy.retention_days is not None
            and configuration.requested_retention_days > policy.retention_days
        ):
            reasons.append("PROVIDER_POLICY_RETENTION_EXCEEDED")
        if (
            configuration.requested_retention_days is not None
            and license_policy.retention_days is not None
            and configuration.requested_retention_days > license_policy.retention_days
        ):
            reasons.append("LICENSE_RETENTION_EXCEEDED")
        if credential_reference.resolver_kind not in configuration.allowed_credential_resolvers:
            reasons.append("CREDENTIAL_RESOLVER_UNSUPPORTED")

        if not reasons:
            return ConfigurationDecision(
                allowed=True,
                status=ProviderConfigurationStatus.VALID,
                reason_codes=("PROVIDER_CONFIGURATION_VALID",),
            )
        status = (
            ProviderConfigurationStatus.BLOCKED
            if "PROVIDER_BLOCKED" in reasons
            else ProviderConfigurationStatus.INVALID
        )
        return ConfigurationDecision(
            allowed=False,
            status=status,
            reason_codes=tuple(reasons),
        )
