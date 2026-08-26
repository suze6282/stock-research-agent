import importlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers.enums import ProviderLicenseStatus

ROOT = Path(__file__).parents[2]
LICENSES_MODULE = ROOT / "src" / "stock_research_agent" / "domain" / "providers" / "licenses.py"
PROVIDER_ID = UUID("11111111-1111-4111-8111-111111111111")


def _licenses() -> object:
    assert LICENSES_MODULE.is_file(), "versioned source-license gate is absent"
    return importlib.import_module("stock_research_agent.domain.providers.licenses")


def _approved_policy(licenses: object) -> object:
    permission = licenses.LicensePermission
    return licenses.SourceLicensePolicyRecord(
        id=UUID("22222222-2222-4222-8222-222222222222"),
        provider_definition_id=PROVIDER_ID,
        policy_version="1.0.0",
        status=ProviderLicenseStatus.APPROVED,
        acquisition=permission.ALLOWED,
        raw_storage=permission.ALLOWED,
        cache=permission.ALLOWED,
        derived_use=permission.ALLOWED,
        redistribution=permission.ALLOWED,
        retention_days=None,
        deletion_required=False,
        attribution_required=True,
        terms_source_ids=("SEC-FAQ", "SEC-RATE"),
        reviewed_at=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
        expires_at=None,
        checksum="a" * 64,
        created_at=datetime(2026, 7, 29, 12, 1, tzinfo=UTC),
    )


def test_license_gate_allows_only_requested_approved_uses() -> None:
    licenses = _licenses()
    request = licenses.LicenseUseRequest(
        acquire=True,
        store_raw=True,
        create_cache=True,
        create_derivative=True,
        redistribute=False,
        requested_retention_days=365,
    )

    decision = licenses.SourceLicenseGate().evaluate(
        _approved_policy(licenses),
        request,
        evaluated_at=datetime(2026, 7, 29, 13, 0, tzinfo=UTC),
    )

    assert decision.allowed is True
    assert decision.reason_codes == ("LICENSE_USE_APPROVED",)
    assert decision.status is ProviderLicenseStatus.APPROVED


def test_restricted_tushare_policy_stays_blocked_after_offline_implementation() -> None:
    licenses = _licenses()
    permission = licenses.LicensePermission
    policy = licenses.SourceLicensePolicyRecord(
        id=UUID("33333333-3333-4333-8333-333333333333"),
        provider_definition_id=PROVIDER_ID,
        policy_version="1.0.0",
        status=ProviderLicenseStatus.RESTRICTED_REVIEW_REQUIRED,
        acquisition=permission.UNKNOWN_REQUIRES_REVIEW,
        raw_storage=permission.UNKNOWN_REQUIRES_REVIEW,
        cache=permission.UNKNOWN_REQUIRES_REVIEW,
        derived_use=permission.UNKNOWN_REQUIRES_REVIEW,
        redistribution=permission.PROHIBITED,
        retention_days=None,
        deletion_required=False,
        attribution_required=False,
        terms_source_ids=("TUSHARE-TERMS",),
        reviewed_at=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
        expires_at=None,
        checksum="b" * 64,
        created_at=datetime(2026, 7, 29, 12, 1, tzinfo=UTC),
    )
    request = licenses.LicenseUseRequest(
        acquire=True,
        store_raw=True,
        create_cache=False,
        create_derivative=False,
        redistribute=False,
        requested_retention_days=None,
    )

    decision = licenses.SourceLicenseGate().evaluate(
        policy,
        request,
        evaluated_at=datetime(2026, 7, 29, 13, 0, tzinfo=UTC),
    )

    assert decision.allowed is False
    assert decision.reason_codes == ("LICENSE_RESTRICTED_REVIEW_REQUIRED",)
    assert decision.status is ProviderLicenseStatus.RESTRICTED_REVIEW_REQUIRED


def test_unknown_cache_or_excess_retention_is_blocked() -> None:
    licenses = _licenses()
    permission = licenses.LicensePermission
    base = _approved_policy(licenses).model_dump()
    base.update(
        cache=permission.UNKNOWN_REQUIRES_REVIEW,
        retention_days=30,
    )
    policy = licenses.SourceLicensePolicyRecord(**base)

    decision = licenses.SourceLicenseGate().evaluate(
        policy,
        licenses.LicenseUseRequest(
            acquire=True,
            store_raw=False,
            create_cache=True,
            create_derivative=False,
            redistribute=False,
            requested_retention_days=31,
        ),
        evaluated_at=datetime(2026, 7, 29, 13, 0, tzinfo=UTC),
    )

    assert decision.allowed is False
    assert decision.reason_codes == (
        "LICENSE_CACHE_NOT_ALLOWED",
        "LICENSE_RETENTION_EXCEEDED",
    )


def test_license_policy_rejects_invalid_review_window() -> None:
    licenses = _licenses()
    values = _approved_policy(licenses).model_dump()
    values["expires_at"] = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)

    with pytest.raises(ValidationError):
        licenses.SourceLicensePolicyRecord(**values)


def test_gate_b_operational_terms_source_codes_satisfy_existing_validation() -> None:
    licenses = _licenses()
    values = _approved_policy(licenses).model_dump()
    values["terms_source_ids"] = (
        "SEC_ACCESSING_EDGAR_DATA",
        "SEC_DEVELOPER_RESOURCES",
        "SEC_PRIVACY_SECURITY_POLICY",
    )

    policy = licenses.SourceLicensePolicyRecord.model_validate(values)

    assert policy.terms_source_ids == (
        "SEC_ACCESSING_EDGAR_DATA",
        "SEC_DEVELOPER_RESOURCES",
        "SEC_PRIVACY_SECURITY_POLICY",
    )
