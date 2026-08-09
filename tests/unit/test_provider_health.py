from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from stock_research_agent.domain.providers import health
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

NOW = datetime(2026, 7, 29, tzinfo=UTC)


def _context(**changes: object) -> object:
    values: dict[str, object] = {
        "provider_definition_id": uuid4(),
        "definition_status": ProviderDefinitionStatus.ACTIVE,
        "production_status": ProviderProductionStatus.ENABLED,
        "capability_status": ProviderCapabilityStatus.ENABLED,
        "license_status": ProviderLicenseStatus.APPROVED,
        "credential_status": ProviderCredentialStatus.NOT_REQUIRED,
        "configuration_status": ProviderConfigurationStatus.VALID,
        "circuit_status": ProviderCircuitStatus.CLOSED,
        "schema_valid": True,
        "mapping_valid": True,
        "retention_allowed": True,
        "live_validation_status": ProviderLiveValidationStatus.PASSED,
        "last_validation_at": NOW,
        "observed_at": NOW,
    }
    values.update(changes)
    return health.ProviderReadinessContext.model_validate(values)


def test_all_explicit_offline_inputs_can_report_ready_without_probe() -> None:
    result = health.ProviderReadinessService().evaluate(_context())
    assert result.status is health.ProviderReadinessStatus.READY
    assert result.limiting_reasons == ()


def test_offline_adapter_success_never_implies_production_ready() -> None:
    result = health.ProviderReadinessService().evaluate(
        _context(
            capability_status=ProviderCapabilityStatus.IMPLEMENTED_OFFLINE,
            production_status=ProviderProductionStatus.BLOCKED,
            license_status=ProviderLicenseStatus.RESTRICTED_REVIEW_REQUIRED,
            credential_status=ProviderCredentialStatus.NOT_READ,
            live_validation_status=ProviderLiveValidationStatus.NOT_ATTEMPTED,
        )
    )
    assert result.status is health.ProviderReadinessStatus.BLOCKED
    assert result.limiting_reasons == tuple(sorted(result.limiting_reasons))
    assert {
        "CAPABILITY_NOT_PRODUCTION_ENABLED",
        "LICENSE_NOT_APPROVED",
        "LIVE_VALIDATION_NOT_PASSED",
        "PRODUCTION_STATUS_BLOCKED",
    } <= set(result.limiting_reasons)


def test_health_snapshot_is_append_only_shape_with_stable_checksum() -> None:
    context = _context()
    result = health.ProviderReadinessService().evaluate(context)
    first = health.build_health_snapshot(context, result)
    second = health.build_health_snapshot(context, result)
    assert first == second
    assert first.checksum == second.checksum
    assert "network" not in first.model_dump(mode="json")
