from __future__ import annotations

import inspect
import os
from importlib import import_module

import pytest


def _adapter_module() -> object:
    return import_module("stock_research_agent.providers.tushare.adapter")


def _endpoint_module() -> object:
    return import_module("stock_research_agent.providers.tushare.endpoints")


def test_tushare_descriptor_is_explicitly_offline_and_production_blocked() -> None:
    module = _adapter_module()
    descriptor = module.TushareAdapter().descriptor  # type: ignore[attr-defined]

    assert descriptor.capability_status.value == "IMPLEMENTED_OFFLINE"
    assert descriptor.license_status.value == "RESTRICTED_REVIEW_REQUIRED"
    assert descriptor.credential_status.value == "NOT_READ"
    assert descriptor.live_status.value == "NOT_ATTEMPTED"
    assert descriptor.production_status.value == "BLOCKED"
    assert descriptor.network_status == "HARD_BLOCKED"
    assert descriptor.reason_codes == (
        "HTTPS_ENDPOINT_NOT_APPROVED",
        "LICENSE_RIGHTS_NOT_APPROVED",
        "TOKEN_ENTITLEMENTS_UNKNOWN",
    )


def test_tushare_has_no_production_endpoint_policy_or_url_input() -> None:
    module = _endpoint_module()

    assert module.TUSHARE_PRODUCTION_ENDPOINT_POLICIES == {}  # type: ignore[attr-defined]
    signature = inspect.signature(module.resolve_tushare_live_endpoint)  # type: ignore[attr-defined]
    assert "url" not in signature.parameters
    assert "token" not in signature.parameters
    with pytest.raises(ValueError, match="TUSHARE_PRODUCTION_ACCESS_BLOCKED"):
        module.resolve_tushare_live_endpoint("daily")  # type: ignore[attr-defined]


def test_offline_contract_success_does_not_enable_network_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schemas = import_module("stock_research_agent.providers.tushare.schemas")
    monkeypatch.setenv("TUSHARE_TOKEN", "must-not-be-read")

    def forbidden_getenv(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("credential environment was read")

    monkeypatch.setattr(os, "getenv", forbidden_getenv)
    response = schemas.TushareOfflineResponse(  # type: ignore[attr-defined]
        endpoint=schemas.TushareEndpoint.DAILY,  # type: ignore[attr-defined]
        fields=("close", "trade_date", "ts_code"),
        items=(("66.27", "20260710", "601138.SH"),),
        offset=0,
        has_more=False,
    )
    adapter = _adapter_module().TushareAdapter()  # type: ignore[attr-defined]

    assert response.items
    assert adapter.descriptor.production_status.value == "BLOCKED"
