from __future__ import annotations

import hashlib
import json
import os
import socket
from datetime import UTC, date, datetime
from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers.enums import (
    ProviderCredentialStatus,
    ProviderLicenseStatus,
    ProviderLiveAuthorizationStatus,
    ProviderSyntheticStatus,
)

SECURITY_ID = UUID("00000000-0000-4000-8000-000000000057")
AS_OF = datetime(2026, 7, 29, tzinfo=UTC)


def _module() -> object:
    return import_module("stock_research_agent.providers.tushare.adapter")


def _schemas() -> object:
    return import_module("stock_research_agent.providers.tushare.schemas")


def _request(**changes: object) -> object:
    module = _module()
    schemas = _schemas()
    values: dict[str, object] = {
        "provider_code": "TUSHARE_PRO_V1",
        "capability_code": "FETCH_EOD_PRICES",
        "capability_version": "1.0.0",
        "adapter_version": "1.0.0",
        "provider_policy_version": "1.0.0",
        "license_policy_version": "1.0.0",
        "market": "CN_A",
        "security_id": SECURITY_ID,
        "provider_security_identifier": "601138.SH",
        "date_from": date(2026, 1, 1),
        "date_to": date(2026, 3, 5),
        "as_of_time": AS_OF,
        "sync_mode": module.TushareSyncMode.OFFLINE_CONTRACT,  # type: ignore[attr-defined]
        "endpoint": schemas.TushareEndpoint.DAILY,  # type: ignore[attr-defined]
        "fields": ("close", "trade_date", "ts_code"),
        "budget": module.TusharePlanBudget(  # type: ignore[attr-defined]
            max_requests=5,
            max_records=500,
            max_bytes=5_000,
            max_response_bytes=1_000,
            max_slices=5,
            page_limit=100,
        ),
        "checkpoint": None,
        "license_status": ProviderLicenseStatus.RESTRICTED_REVIEW_REQUIRED,
        "commercial_use_approved": False,
        "raw_storage_approved": False,
        "credential_status": ProviderCredentialStatus.NOT_READ,
        "live_authorization_status": ProviderLiveAuthorizationStatus.NOT_ATTEMPTED,
        "entitlement_status": module.TushareEntitlementStatus.UNKNOWN,  # type: ignore[attr-defined]
        "synthetic_status": ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
    }
    values.update(changes)
    return module.TusharePlanRequest(**values)  # type: ignore[attr-defined]


def test_same_input_produces_same_finite_plan_and_idempotency_key() -> None:
    adapter = _module().TushareAdapter()  # type: ignore[attr-defined]
    request = _request()

    first = adapter.plan(request)
    second = adapter.plan(request)

    assert first == second
    assert first.allowed is True
    assert first.status.value == "READY"
    assert first.idempotency_key == second.idempotency_key
    assert first.plan is not None
    assert first.plan.to_write().plan_checksum == second.plan.to_write().plan_checksum
    assert tuple((slice_.range_start, slice_.range_end) for slice_ in first.plan.slices) == (
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 3, 3)),
        (date(2026, 3, 4), date(2026, 3, 5)),
    )
    assert tuple(slice_.ordinal for slice_ in first.plan.slices) == (0, 1, 2)
    assert first.estimated_requests == 3
    assert first.estimated_records == 300
    assert first.estimated_bytes == 3_000
    assert first.access_mode == "OFFLINE"
    assert first.live_status == "NOT_LIVE"
    assert first.production_status.value == "BLOCKED"


def test_idempotency_key_matches_independent_canonical_golden() -> None:
    request = _request()
    expected_payload = {
        "adapter_version": "1.0.0",
        "as_of_time": "2026-07-29T00:00:00Z",
        "budget": {
            "max_bytes": 5000,
            "max_records": 500,
            "max_requests": 5,
            "max_response_bytes": 1000,
            "max_slices": 5,
            "page_limit": 100,
        },
        "capability_code": "FETCH_EOD_PRICES",
        "capability_version": "1.0.0",
        "checkpoint": None,
        "date_from": "2026-01-01",
        "date_to": "2026-03-05",
        "endpoint": "daily",
        "fields": ["close", "trade_date", "ts_code"],
        "license_policy_version": "1.0.0",
        "market": "CN_A",
        "provider_code": "TUSHARE_PRO_V1",
        "provider_policy_version": "1.0.0",
        "provider_security_identifier": "601138.SH",
        "security_id": str(SECURITY_ID),
        "sync_mode": "OFFLINE_CONTRACT",
    }
    canonical = json.dumps(
        expected_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    expected = hashlib.sha256(canonical.encode()).hexdigest()

    assert _module().TushareAdapter().plan(request).idempotency_key == expected  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "changes",
    (
        {"date_from": date(2026, 3, 6), "date_to": date(2026, 3, 5)},
        {"date_from": date(2024, 1, 1), "date_to": date(2026, 3, 5)},
        {"date_to": date(2026, 7, 30)},
    ),
)
def test_invalid_unbounded_or_future_date_range_is_rejected(
    changes: dict[str, object],
) -> None:
    with pytest.raises((ValidationError, ValueError)):
        _module().TushareAdapter().plan(_request(**changes))  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"capability_code": "FETCH_EOD"}, "CAPABILITY_NOT_APPROVED"),
        ({"provider_security_identifier": None}, "PROVIDER_MAPPING_MISSING"),
        (
            {"entitlement_status": "BLOCKED"},
            "PROVIDER_ENTITLEMENT_BLOCKED",
        ),
    ),
)
def test_unapproved_capability_mapping_or_entitlement_is_blocked(
    changes: dict[str, object],
    reason: str,
) -> None:
    module = _module()
    if "entitlement_status" in changes:
        changes["entitlement_status"] = module.TushareEntitlementStatus(  # type: ignore[attr-defined]
            changes["entitlement_status"]
        )

    result = module.TushareAdapter().plan(_request(**changes))  # type: ignore[attr-defined]

    assert result.allowed is False
    assert result.plan is None
    assert reason in result.blocking_reasons


def test_live_plan_remains_blocked_with_specific_governance_reasons() -> None:
    module = _module()
    result = module.TushareAdapter().plan(  # type: ignore[attr-defined]
        _request(sync_mode=module.TushareSyncMode.LIVE)  # type: ignore[attr-defined]
    )

    assert result.allowed is False
    assert result.plan is None
    assert result.blocking_reasons == (
        "COMMERCIAL_USE_UNCONFIRMED",
        "CREDENTIAL_NOT_READ",
        "LICENSE_RESTRICTED_REVIEW_REQUIRED",
        "LIVE_NOT_AUTHORIZED",
        "PROVIDER_ENTITLEMENT_UNKNOWN",
        "RAW_STORAGE_RIGHT_UNCONFIRMED",
    )


def test_checkpoint_resumes_without_expanding_range_or_resetting_budget() -> None:
    module = _module()
    checkpoint = module.TusharePlanCheckpoint(  # type: ignore[attr-defined]
        endpoint="daily",
        provider_security_identifier="601138.SH",
        next_date=date(2026, 2, 1),
        revision=4,
        consumed_requests=2,
        consumed_records=200,
        consumed_bytes=2_000,
    )

    result = module.TushareAdapter().plan(_request(checkpoint=checkpoint))  # type: ignore[attr-defined]

    assert result.allowed is True
    assert result.plan is not None
    assert result.plan.checkpoint_revision == 4
    assert result.plan.slices[0].range_start == date(2026, 2, 1)
    assert result.remaining_requests == 3
    assert result.remaining_records == 300
    assert result.remaining_bytes == 3_000

    with pytest.raises((ValidationError, ValueError)):
        _request(checkpoint=checkpoint.model_copy(update={"next_date": date(2025, 12, 31)}))


def test_budgets_truncate_deterministically_without_infinite_pagination() -> None:
    module = _module()
    budget = module.TusharePlanBudget(  # type: ignore[attr-defined]
        max_requests=1,
        max_records=50,
        max_bytes=800,
        max_response_bytes=800,
        max_slices=1,
        page_limit=100,
    )

    result = module.TushareAdapter().plan(_request(budget=budget))  # type: ignore[attr-defined]

    assert result.allowed is True
    assert result.status.value == "PARTIAL"
    assert result.warning_codes == ("PLAN_TRUNCATED_BY_BUDGET",)
    assert result.estimated_requests == 1
    assert result.estimated_records == 50
    assert result.estimated_bytes == 800
    assert result.plan is not None
    assert len(result.plan.slices) == 1
    assert result.plan.slices[0].request_parameters["limit"] == 50
    assert "page" not in result.plan.slices[0].request_parameters


def test_endpoint_and_fields_require_exact_approved_contract() -> None:
    schemas = _schemas()
    for changes in (
        {"capability_code": "FETCH_EOD_PRICES_EXTRA"},
        {"fields": ("arbitrary", "ts_code")},
        {"endpoint": schemas.TushareEndpoint.STOCK_BASIC},
    ):
        result = _module().TushareAdapter().plan(_request(**changes))  # type: ignore[attr-defined]
        assert result.allowed is False
        assert result.plan is None


def test_planner_never_reads_token_or_accesses_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "TOP_SECRET_MUST_NOT_APPEAR")

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("network or credential access attempted")

    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)

    result = _module().TushareAdapter().plan(_request())  # type: ignore[attr-defined]

    assert result.allowed is True
    assert "TOP_SECRET" not in repr(result)
