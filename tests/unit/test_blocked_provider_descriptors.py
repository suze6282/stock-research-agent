from __future__ import annotations

from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderCredentialStatus,
    ProviderLicenseStatus,
    ProviderLiveValidationStatus,
    ProviderProductionStatus,
)
from stock_research_agent.providers.blocked import (
    BLOCKED_PROVIDER_DESCRIPTORS,
    BlockedProviderReasonCategory,
    get_blocked_provider_descriptor,
)

EXPECTED_CODES = (
    "CNINFO_DISCLOSURE_BODIES_V1",
    "LICENSED_US_EOD_V1",
    "PRODUCTION_EMBEDDING_V1",
    "SSE_DISCLOSURE_BODIES_V1",
    "SZSE_DISCLOSURE_BODIES_V1",
)


def test_all_contract_only_provider_descriptors_are_registered_deterministically() -> None:
    assert tuple(descriptor.provider_code for descriptor in BLOCKED_PROVIDER_DESCRIPTORS) == (
        EXPECTED_CODES
    )
    assert len({descriptor.provider_code for descriptor in BLOCKED_PROVIDER_DESCRIPTORS}) == 5
    assert all(
        descriptor.provider_version == "1.0.0" for descriptor in BLOCKED_PROVIDER_DESCRIPTORS
    )


def test_every_descriptor_is_hard_blocked_and_never_claims_offline_or_live_pass() -> None:
    for descriptor in BLOCKED_PROVIDER_DESCRIPTORS:
        assert descriptor.capability_status is ProviderCapabilityStatus.BLOCKED
        assert descriptor.production_status is ProviderProductionStatus.BLOCKED
        assert descriptor.credential_status is ProviderCredentialStatus.NOT_READ
        assert descriptor.live_status is ProviderLiveValidationStatus.NOT_ATTEMPTED
        assert descriptor.network_status == "HARD_BLOCKED"
        assert descriptor.offline_contract_status == "BLOCKED"
        assert descriptor.reason_codes
        assert descriptor.blocking_reasons


def test_disclosure_descriptors_record_license_endpoint_storage_and_approval_gaps() -> None:
    for provider_code in (
        "CNINFO_DISCLOSURE_BODIES_V1",
        "SSE_DISCLOSURE_BODIES_V1",
        "SZSE_DISCLOSURE_BODIES_V1",
    ):
        descriptor = get_blocked_provider_descriptor(provider_code)
        assert descriptor is not None
        assert descriptor.license_status is ProviderLicenseStatus.UNKNOWN_REQUIRES_REVIEW
        assert {reason.category for reason in descriptor.blocking_reasons} == {
            BlockedProviderReasonCategory.APPROVAL,
            BlockedProviderReasonCategory.ENDPOINT,
            BlockedProviderReasonCategory.LICENSE,
            BlockedProviderReasonCategory.STORAGE_RIGHTS,
        }


def test_disclosure_descriptors_preserve_the_approved_blocking_reason_codes() -> None:
    expected = (
        "AUTOMATION_AUTHORIZATION_UNCONFIRMED",
        "COMMERCIAL_USE_UNCONFIRMED",
        "OFFICIAL_API_UNCONFIRMED",
        "RAW_STORAGE_RIGHT_UNCONFIRMED",
        "REDISTRIBUTION_RIGHT_UNCONFIRMED",
    )

    for provider_code in (
        "CNINFO_DISCLOSURE_BODIES_V1",
        "SSE_DISCLOSURE_BODIES_V1",
        "SZSE_DISCLOSURE_BODIES_V1",
    ):
        descriptor = get_blocked_provider_descriptor(provider_code)
        assert descriptor is not None
        assert descriptor.reason_codes == expected


def test_us_eod_descriptor_records_missing_vendor_contract_endpoint_and_credential() -> None:
    descriptor = get_blocked_provider_descriptor("LICENSED_US_EOD_V1")

    assert descriptor is not None
    assert descriptor.license_status is ProviderLicenseStatus.BLOCKED
    assert {reason.category for reason in descriptor.blocking_reasons} == {
        BlockedProviderReasonCategory.APPROVAL,
        BlockedProviderReasonCategory.CREDENTIAL,
        BlockedProviderReasonCategory.LICENSE,
        BlockedProviderReasonCategory.VENDOR,
    }


def test_us_eod_descriptor_preserves_the_approved_blocking_reason_codes() -> None:
    descriptor = get_blocked_provider_descriptor("LICENSED_US_EOD_V1")

    assert descriptor is not None
    assert descriptor.reason_codes == (
        "CREDENTIAL_NOT_CONFIGURED",
        "LICENSE_NOT_APPROVED",
        "LIVE_NOT_ATTEMPTED",
        "PROVIDER_NOT_SELECTED",
    )


def test_embedding_descriptor_records_missing_model_vendor_credential_and_approval() -> None:
    descriptor = get_blocked_provider_descriptor("PRODUCTION_EMBEDDING_V1")

    assert descriptor is not None
    assert descriptor.license_status is ProviderLicenseStatus.BLOCKED
    assert {reason.category for reason in descriptor.blocking_reasons} == {
        BlockedProviderReasonCategory.APPROVAL,
        BlockedProviderReasonCategory.CREDENTIAL,
        BlockedProviderReasonCategory.MODEL,
        BlockedProviderReasonCategory.VENDOR,
    }


def test_embedding_descriptor_preserves_the_approved_blocking_reason_codes() -> None:
    descriptor = get_blocked_provider_descriptor("PRODUCTION_EMBEDDING_V1")

    assert descriptor is not None
    assert descriptor.reason_codes == (
        "COST_BUDGET_NOT_APPROVED",
        "CREDENTIAL_NOT_CONFIGURED",
        "DATA_TRANSFER_POLICY_NOT_APPROVED",
        "LIVE_NOT_ATTEMPTED",
        "MODEL_NOT_SELECTED",
        "PROVIDER_NOT_SELECTED",
    )


def test_blocking_reasons_are_structured_specific_and_actionable() -> None:
    for descriptor in BLOCKED_PROVIDER_DESCRIPTORS:
        assert descriptor.reason_codes == tuple(
            reason.code for reason in descriptor.blocking_reasons
        )
        assert descriptor.reason_codes == tuple(sorted(set(descriptor.reason_codes)))
        for reason in descriptor.blocking_reasons:
            assert reason.code not in {"BLOCKED", "NOT_CONFIGURED", "UNAVAILABLE"}
            assert len(reason.detail) >= 20
            assert len(reason.required_action) >= 20


def test_descriptor_lookup_requires_an_exact_code_and_never_matches_names_or_prefixes() -> None:
    assert get_blocked_provider_descriptor("SSE_DISCLOSURE_BODIES_V1") is not None
    assert get_blocked_provider_descriptor("SSE") is None
    assert get_blocked_provider_descriptor("SSE_DISCLOSURE") is None
    assert get_blocked_provider_descriptor("sse_disclosure_bodies_v1") is None
    assert get_blocked_provider_descriptor("SSE disclosure bodies") is None
    assert get_blocked_provider_descriptor("PRODUCTION_EMBEDDING_V2") is None
