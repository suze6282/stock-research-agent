"""Offline-only Provider health and readiness contracts."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderCircuitStatus,
    ProviderConfigurationStatus,
    ProviderCredentialStatus,
    ProviderDefinitionStatus,
    ProviderLicenseStatus,
    ProviderLiveValidationStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
)


class ProviderReadinessStatus(StrEnum):
    READY = "READY"
    CONDITIONAL = "CONDITIONAL"
    BLOCKED = "BLOCKED"


class ProviderReadinessContext(FrozenProviderContract):
    provider_definition_id: UUID
    definition_status: ProviderDefinitionStatus
    production_status: ProviderProductionStatus
    capability_status: ProviderCapabilityStatus
    license_status: ProviderLicenseStatus
    credential_status: ProviderCredentialStatus
    configuration_status: ProviderConfigurationStatus
    circuit_status: ProviderCircuitStatus
    schema_valid: bool
    mapping_valid: bool
    retention_allowed: bool
    live_validation_status: ProviderLiveValidationStatus
    last_validation_at: AwareUtcDateTime | None
    observed_at: AwareUtcDateTime


class ProviderReadinessResult(FrozenProviderContract):
    status: ProviderReadinessStatus
    limiting_reasons: tuple[str, ...] = Field(max_length=32)


class ProviderHealthSnapshotWrite(FrozenProviderContract):
    provider_definition_id: UUID
    status: ProviderReadinessStatus
    configuration_status: ProviderConfigurationStatus
    credential_status: ProviderCredentialStatus
    license_status: ProviderLicenseStatus
    live_validation_status: ProviderLiveValidationStatus
    limiting_reasons: tuple[str, ...] = Field(max_length=32)
    observed_at: AwareUtcDateTime
    checksum: Checksum


class ProviderHealthSnapshotRecord(ProviderHealthSnapshotWrite):
    id: UUID
    created_at: AwareUtcDateTime


class ProviderReadinessService:
    """Evaluate supplied metadata only; no probe, resolver, or transport dependency."""

    def evaluate(self, context: ProviderReadinessContext) -> ProviderReadinessResult:
        reasons: list[str] = []
        checks = (
            (
                context.definition_status is not ProviderDefinitionStatus.ACTIVE,
                "PROVIDER_DEFINITION_NOT_ACTIVE",
            ),
            (
                context.production_status is not ProviderProductionStatus.ENABLED,
                "PRODUCTION_STATUS_BLOCKED",
            ),
            (
                context.capability_status is not ProviderCapabilityStatus.ENABLED,
                "CAPABILITY_NOT_PRODUCTION_ENABLED",
            ),
            (
                context.license_status is not ProviderLicenseStatus.APPROVED,
                "LICENSE_NOT_APPROVED",
            ),
            (
                context.credential_status
                not in {
                    ProviderCredentialStatus.NOT_REQUIRED,
                    ProviderCredentialStatus.CONFIGURED_METADATA_ONLY,
                },
                "CREDENTIAL_METADATA_NOT_READY",
            ),
            (
                context.configuration_status is not ProviderConfigurationStatus.VALID,
                "CONFIGURATION_NOT_VALID",
            ),
            (
                context.circuit_status is not ProviderCircuitStatus.CLOSED,
                "CIRCUIT_NOT_CLOSED",
            ),
            (not context.schema_valid, "SCHEMA_NOT_VALIDATED"),
            (not context.mapping_valid, "MAPPING_NOT_VALIDATED"),
            (not context.retention_allowed, "RETENTION_NOT_ALLOWED"),
            (
                context.live_validation_status is not ProviderLiveValidationStatus.PASSED,
                "LIVE_VALIDATION_NOT_PASSED",
            ),
            (
                context.last_validation_at is None
                or context.last_validation_at > context.observed_at,
                "LAST_VALIDATION_NOT_AVAILABLE",
            ),
        )
        reasons.extend(reason for failed, reason in checks if failed)
        ordered = tuple(sorted(reasons))
        return ProviderReadinessResult(
            status=(ProviderReadinessStatus.BLOCKED if ordered else ProviderReadinessStatus.READY),
            limiting_reasons=ordered,
        )


def build_health_snapshot(
    context: ProviderReadinessContext,
    result: ProviderReadinessResult,
) -> ProviderHealthSnapshotWrite:
    payload = {
        "provider_definition_id": context.provider_definition_id,
        "status": result.status,
        "configuration_status": context.configuration_status,
        "credential_status": context.credential_status,
        "license_status": context.license_status,
        "live_validation_status": context.live_validation_status,
        "limiting_reasons": result.limiting_reasons,
        "observed_at": context.observed_at,
    }
    return ProviderHealthSnapshotWrite(
        provider_definition_id=context.provider_definition_id,
        status=result.status,
        configuration_status=context.configuration_status,
        credential_status=context.credential_status,
        license_status=context.license_status,
        live_validation_status=context.live_validation_status,
        limiting_reasons=result.limiting_reasons,
        observed_at=context.observed_at,
        checksum=provider_checksum(payload),
    )
