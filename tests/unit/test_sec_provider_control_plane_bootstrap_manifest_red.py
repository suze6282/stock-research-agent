from __future__ import annotations

import importlib
from decimal import Decimal
from types import ModuleType
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers.canonical import provider_checksum

MODULE_NAME = "stock_research_agent.providers.sec_edgar.bootstrap"
DEFINITION_ID = UUID("78000000-0000-4000-8000-000000000001")


def _api() -> ModuleType:
    try:
        module = importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as error:
        if error.name == MODULE_NAME:
            pytest.fail(
                "SEC Provider control-plane bootstrap API is not implemented", pytrace=False
            )
        raise
    required = {
        "SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP",
        "SecProviderControlPlaneBootstrapManifest",
    }
    if any(not hasattr(module, name) for name in required):
        pytest.fail("SEC Provider control-plane bootstrap API is not implemented", pytrace=False)
    return module


def _manifest() -> object:
    return _api().SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP


def test_sec_bootstrap_manifest_is_strict_frozen_and_versioned() -> None:
    api = _api()
    manifest = api.SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP

    assert manifest.manifest_name == "SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE"
    assert manifest.manifest_version == "1.0.0"
    with pytest.raises(ValidationError):
        manifest.manifest_version = "2.0.0"
    with pytest.raises(ValidationError):
        api.SecProviderControlPlaneBootstrapManifest.model_validate(
            {**manifest.model_dump(mode="python"), "unexpected": "forbidden"}
        )


def test_sec_bootstrap_manifest_has_exact_provider_definition() -> None:
    manifest = _manifest()

    assert manifest.definition.model_dump(mode="python") == {
        "code": "SEC_EDGAR_PUBLIC_V1",
        "definition_version": "1.0.0",
        "adapter_version": "1.0.0",
        "display_name": "SEC EDGAR public data",
        "data_domain": "US_SEC_FILINGS",
        "definition_status": "ACTIVE",
        "production_status": "CONDITIONAL",
        "official_domains": ("data.sec.gov", "www.sec.gov"),
        "policy_version": "1.0.0",
        "license_policy_version": "1.0.0",
        "credential_reference_id": None,
        "source_register_version": "1.0.0",
    }


def test_sec_bootstrap_manifest_has_exact_gate_b_capability() -> None:
    manifest = _manifest()
    capability = manifest.capability.materialize(DEFINITION_ID)

    assert capability.model_dump(mode="python") == {
        "provider_definition_id": DEFINITION_ID,
        "code": "FETCH_SEC_FILING_DOCUMENTS",
        "capability_version": "1.0.0",
        "status": "IMPLEMENTED_OFFLINE",
        "data_domain": "US_SEC_FILINGS",
        "market_codes": ("US_EQUITY",),
        "security_types": ("COMMON_STOCK",),
        "operations": ("READ_LIVE_VALIDATION",),
    }


def test_sec_bootstrap_manifest_has_exact_generic_provider_policy() -> None:
    manifest = _manifest()
    policy = manifest.policy.materialize(DEFINITION_ID)

    assert policy.model_dump(mode="python") == {
        "provider_definition_id": DEFINITION_ID,
        "policy_version": "1.0.0",
        "endpoint_policy_version": "1.0.0",
        "network_enabled": True,
        "max_requests": 3,
        "max_response_bytes": 20_971_520,
        "max_total_bytes": 26_214_400,
        "max_duration_seconds": 120,
        "max_attempts": 3,
        "max_redirects": 0,
        "rate_limit_per_second": Decimal("1"),
        "retry_base_delay_seconds": Decimal("1"),
        "cache_enabled": False,
        "cache_ttl_seconds": None,
        "retention_days": 30,
    }


def test_sec_bootstrap_manifest_checksum_is_canonical_and_stable() -> None:
    manifest = _manifest()

    assert manifest.manifest_checksum == provider_checksum(manifest)
    assert manifest.manifest_checksum == provider_checksum(
        manifest.__class__.model_validate(manifest.model_dump(mode="python"))
    )


def test_sec_bootstrap_manifest_rejects_company_facts_or_extra_capability() -> None:
    api = _api()
    manifest = api.SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP
    payload = manifest.model_dump(mode="python")
    payload["capability"]["code"] = "FETCH_SEC_COMPANY_FACTS"

    with pytest.raises(ValidationError):
        api.SecProviderControlPlaneBootstrapManifest.model_validate(payload)
    assert not hasattr(manifest, "capabilities")


def test_sec_bootstrap_manifest_keeps_generic_attempts_at_three() -> None:
    policy = _manifest().policy.materialize(DEFINITION_ID)

    assert policy.max_attempts == 3


def test_sec_bootstrap_manifest_keeps_provider_request_ceiling_at_three() -> None:
    policy = _manifest().policy.materialize(DEFINITION_ID)

    assert policy.max_requests == 3


def test_sec_bootstrap_manifest_keeps_gate_b_physical_attempt_limit_out_of_policy() -> None:
    manifest_dump = _manifest().model_dump(mode="python")

    assert "physical_attempt_limit" not in manifest_dump
    assert "retry_limit" not in manifest_dump
    assert manifest_dump["policy"]["max_attempts"] == 3


def test_sec_bootstrap_manifest_contains_no_credential_license_or_execution_payload() -> None:
    payload = _manifest().model_dump(mode="python")
    forbidden = {
        "credential",
        "credential_reference",
        "license",
        "sync_request",
        "plan",
        "grant",
        "approval",
        "sync_run",
        "attempt",
        "artifact",
        "terminal",
    }

    assert forbidden.isdisjoint(payload)
    assert payload["definition"]["credential_reference_id"] is None


def test_sec_bootstrap_specs_materialize_existing_domain_write_types() -> None:
    from stock_research_agent.domain.providers.capabilities import ProviderCapabilityWrite
    from stock_research_agent.domain.providers.policies import ProviderPolicyWrite
    from stock_research_agent.domain.providers.schemas import ProviderDefinitionWrite

    manifest = _manifest()

    assert isinstance(manifest.definition, ProviderDefinitionWrite)
    assert isinstance(manifest.capability.materialize(DEFINITION_ID), ProviderCapabilityWrite)
    assert isinstance(manifest.policy.materialize(DEFINITION_ID), ProviderPolicyWrite)


def test_sec_bootstrap_manifest_locks_exact_natural_identities() -> None:
    manifest = _manifest()
    capability = manifest.capability.materialize(DEFINITION_ID)
    policy = manifest.policy.materialize(DEFINITION_ID)

    assert (manifest.definition.code, manifest.definition.definition_version) == (
        "SEC_EDGAR_PUBLIC_V1",
        "1.0.0",
    )
    assert (
        capability.provider_definition_id,
        capability.code,
        capability.capability_version,
    ) == (DEFINITION_ID, "FETCH_SEC_FILING_DOCUMENTS", "1.0.0")
    assert (policy.provider_definition_id, policy.policy_version) == (DEFINITION_ID, "1.0.0")
