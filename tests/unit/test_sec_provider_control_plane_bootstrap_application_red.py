from __future__ import annotations

import importlib
import inspect
from types import ModuleType

import pytest

MODULE_NAME = "stock_research_agent.providers.sec_edgar.bootstrap"


def _api() -> ModuleType:
    try:
        module = importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as error:
        if error.name == MODULE_NAME:
            pytest.fail("SEC Provider bootstrap application is not implemented", pytrace=False)
        raise
    required = {
        "SecProviderControlPlaneBootstrapApplication",
        "SecProviderControlPlaneBootstrapConflict",
        "SecProviderControlPlaneBootstrapResult",
    }
    if any(not hasattr(module, name) for name in required):
        pytest.fail("SEC Provider bootstrap application is not implemented", pytrace=False)
    return module


def test_bootstrap_application_owns_session_factory_and_manifest() -> None:
    api = _api()
    parameters = inspect.signature(api.SecProviderControlPlaneBootstrapApplication).parameters

    assert tuple(parameters) == ("session_factory", "manifest")


def test_bootstrap_application_exposes_only_inspect_and_bootstrap_actions() -> None:
    api = _api()
    public = {
        name
        for name, value in inspect.getmembers(api.SecProviderControlPlaneBootstrapApplication)
        if not name.startswith("_") and callable(value)
    }

    assert {"inspect", "bootstrap"} <= public
    assert public.isdisjoint({"authorize", "approve", "execute", "send", "run_gate_b", "permit"})


def test_bootstrap_application_has_stable_secret_free_conflict_codes() -> None:
    api = _api()

    assert set(api.SEC_PROVIDER_BOOTSTRAP_CONFLICT_CODES) == {
        "SEC_PROVIDER_BOOTSTRAP_DEFINITION_CONFLICT",
        "SEC_PROVIDER_BOOTSTRAP_CAPABILITY_CONFLICT",
        "SEC_PROVIDER_BOOTSTRAP_POLICY_CONFLICT",
        "SEC_PROVIDER_BOOTSTRAP_READBACK_MISMATCH",
        "SEC_PROVIDER_BOOTSTRAP_DATABASE_INVALID",
        "SEC_PROVIDER_BOOTSTRAP_PERSISTENCE_CONFLICT",
    }


def test_bootstrap_result_contains_control_plane_identity_only() -> None:
    api = _api()
    fields = set(api.SecProviderControlPlaneBootstrapResult.model_fields)

    assert {
        "status",
        "database_name",
        "manifest_name",
        "manifest_version",
        "manifest_checksum",
        "definition_id",
        "definition_checksum",
        "capability_id",
        "capability_checksum",
        "policy_id",
        "policy_checksum",
    } <= fields
    assert fields.isdisjoint(
        {
            "credential",
            "contact",
            "grant",
            "approval",
            "execution",
            "permit",
            "session",
            "database_url",
        }
    )
