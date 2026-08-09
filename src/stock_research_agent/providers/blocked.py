"""Contract-only Provider descriptors that cannot execute offline or Live work."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderCredentialStatus,
    ProviderLicenseStatus,
    ProviderLiveValidationStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.schemas import (
    DataDomainCode,
    FrozenProviderContract,
    ProviderCode,
    SemanticVersion,
)


class BlockedProviderReasonCategory(StrEnum):
    APPROVAL = "APPROVAL"
    CREDENTIAL = "CREDENTIAL"
    ENDPOINT = "ENDPOINT"
    LICENSE = "LICENSE"
    MODEL = "MODEL"
    STORAGE_RIGHTS = "STORAGE_RIGHTS"
    VENDOR = "VENDOR"


class BlockedProviderReason(FrozenProviderContract):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,95}$")
    category: BlockedProviderReasonCategory
    detail: str = Field(min_length=20, max_length=512)
    required_action: str = Field(min_length=20, max_length=512)


class BlockedProviderDescriptor(FrozenProviderContract):
    provider_code: ProviderCode
    provider_version: SemanticVersion
    display_name: str = Field(min_length=1, max_length=128)
    data_domain: DataDomainCode
    capability_codes: tuple[str, ...] = Field(min_length=1, max_length=16)
    capability_status: Literal[ProviderCapabilityStatus.BLOCKED]
    production_status: Literal[ProviderProductionStatus.BLOCKED]
    license_status: ProviderLicenseStatus
    credential_status: Literal[ProviderCredentialStatus.NOT_READ]
    live_status: Literal[ProviderLiveValidationStatus.NOT_ATTEMPTED]
    network_status: Literal["HARD_BLOCKED"]
    offline_contract_status: Literal["BLOCKED"]
    blocking_reasons: tuple[BlockedProviderReason, ...] = Field(min_length=1, max_length=16)
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_deterministic_contract(self) -> BlockedProviderDescriptor:
        if self.capability_codes != tuple(sorted(set(self.capability_codes))):
            raise ValueError("capability_codes must be unique and sorted")
        reason_codes = tuple(reason.code for reason in self.blocking_reasons)
        if reason_codes != tuple(sorted(set(reason_codes))):
            raise ValueError("blocking reasons must have unique sorted codes")
        if self.reason_codes != reason_codes:
            raise ValueError("reason_codes must exactly project blocking reasons")
        return self


def _reason(
    code: str,
    category: BlockedProviderReasonCategory,
    detail: str,
    required_action: str,
) -> BlockedProviderReason:
    return BlockedProviderReason(
        code=code,
        category=category,
        detail=detail,
        required_action=required_action,
    )


def _descriptor(
    *,
    provider_code: str,
    display_name: str,
    data_domain: str,
    capability_codes: tuple[str, ...],
    license_status: ProviderLicenseStatus,
    blocking_reasons: tuple[BlockedProviderReason, ...],
) -> BlockedProviderDescriptor:
    ordered_reasons = tuple(sorted(blocking_reasons, key=lambda reason: reason.code))
    return BlockedProviderDescriptor(
        provider_code=provider_code,
        provider_version="1.0.0",
        display_name=display_name,
        data_domain=data_domain,
        capability_codes=tuple(sorted(capability_codes)),
        capability_status=ProviderCapabilityStatus.BLOCKED,
        production_status=ProviderProductionStatus.BLOCKED,
        license_status=license_status,
        credential_status=ProviderCredentialStatus.NOT_READ,
        live_status=ProviderLiveValidationStatus.NOT_ATTEMPTED,
        network_status="HARD_BLOCKED",
        offline_contract_status="BLOCKED",
        blocking_reasons=ordered_reasons,
        reason_codes=tuple(reason.code for reason in ordered_reasons),
    )


def _disclosure_descriptor(provider_code: str, display_name: str) -> BlockedProviderDescriptor:
    return _descriptor(
        provider_code=provider_code,
        display_name=display_name,
        data_domain="DOCUMENT_DISCLOSURES",
        capability_codes=("FETCH_DISCLOSURE_BODIES",),
        license_status=ProviderLicenseStatus.UNKNOWN_REQUIRES_REVIEW,
        blocking_reasons=(
            _reason(
                "AUTOMATION_AUTHORIZATION_UNCONFIRMED",
                BlockedProviderReasonCategory.APPROVAL,
                "No approval permits automated collection from this formal-source candidate.",
                "Obtain explicit automation approval before defining any executable adapter.",
            ),
            _reason(
                "COMMERCIAL_USE_UNCONFIRMED",
                BlockedProviderReasonCategory.LICENSE,
                "Commercial use rights for the disclosure content are not confirmed.",
                "Approve the commercial-use terms before enabling any production capability.",
            ),
            _reason(
                "OFFICIAL_API_UNCONFIRMED",
                BlockedProviderReasonCategory.ENDPOINT,
                "No stable production API endpoint and contract have been approved.",
                "Approve an official endpoint and exact request policy before network access.",
            ),
            _reason(
                "RAW_STORAGE_RIGHT_UNCONFIRMED",
                BlockedProviderReasonCategory.STORAGE_RIGHTS,
                "Raw-body retention and derived evidence storage rights are unconfirmed.",
                "Approve raw retention and downstream evidence storage before ingestion.",
            ),
            _reason(
                "REDISTRIBUTION_RIGHT_UNCONFIRMED",
                BlockedProviderReasonCategory.LICENSE,
                "Redistribution rights for raw bodies and derived excerpts are unconfirmed.",
                "Approve redistribution and excerpt rights before exposing any content.",
            ),
        ),
    )


BLOCKED_PROVIDER_DESCRIPTORS = tuple(
    sorted(
        (
            _disclosure_descriptor(
                "CNINFO_DISCLOSURE_BODIES_V1",
                "CNINFO disclosure bodies",
            ),
            _descriptor(
                provider_code="LICENSED_US_EOD_V1",
                display_name="Licensed U.S. end-of-day market data",
                data_domain="MARKET_DATA",
                capability_codes=("FETCH_EOD_PRICES",),
                license_status=ProviderLicenseStatus.BLOCKED,
                blocking_reasons=(
                    _reason(
                        "CREDENTIAL_NOT_CONFIGURED",
                        BlockedProviderReasonCategory.CREDENTIAL,
                        "No credential reference exists because no vendor has been selected.",
                        "Select and approve a vendor before configuring a secret reference.",
                    ),
                    _reason(
                        "LICENSE_NOT_APPROVED",
                        BlockedProviderReasonCategory.LICENSE,
                        "Price, caching, display, retention, and redistribution rights are absent.",
                        "Approve the complete vendor license and retention policy before use.",
                    ),
                    _reason(
                        "LIVE_NOT_ATTEMPTED",
                        BlockedProviderReasonCategory.APPROVAL,
                        (
                            "No finite authorized Live validation has been attempted for "
                            "this Provider."
                        ),
                        (
                            "Authorize and complete a bounded Live validation only after "
                            "earlier gates pass."
                        ),
                    ),
                    _reason(
                        "PROVIDER_NOT_SELECTED",
                        BlockedProviderReasonCategory.VENDOR,
                        "No licensed U.S. end-of-day market-data vendor has been selected.",
                        "Select a named vendor through a separately authorized decision.",
                    ),
                ),
            ),
            _descriptor(
                provider_code="PRODUCTION_EMBEDDING_V1",
                display_name="Production embedding provider",
                data_domain="EMBEDDINGS",
                capability_codes=("EMBED_DOCUMENT_CHUNKS",),
                license_status=ProviderLicenseStatus.BLOCKED,
                blocking_reasons=(
                    _reason(
                        "COST_BUDGET_NOT_APPROVED",
                        BlockedProviderReasonCategory.APPROVAL,
                        "No finite production embedding cost budget has been approved.",
                        (
                            "Approve a finite cost budget before enabling any production "
                            "embedding work."
                        ),
                    ),
                    _reason(
                        "CREDENTIAL_NOT_CONFIGURED",
                        BlockedProviderReasonCategory.CREDENTIAL,
                        "No embedding credential reference exists for a production provider.",
                        "Select an approved provider before configuring a secret reference.",
                    ),
                    _reason(
                        "DATA_TRANSFER_POLICY_NOT_APPROVED",
                        BlockedProviderReasonCategory.APPROVAL,
                        "Provider text processing, residency, and transfer approval is absent.",
                        "Approve data processing and residency rules before sending any text.",
                    ),
                    _reason(
                        "LIVE_NOT_ATTEMPTED",
                        BlockedProviderReasonCategory.APPROVAL,
                        "No finite authorized Live validation has been attempted for embedding.",
                        (
                            "Authorize and complete a bounded Live validation only after "
                            "earlier gates pass."
                        ),
                    ),
                    _reason(
                        "MODEL_NOT_SELECTED",
                        BlockedProviderReasonCategory.MODEL,
                        (
                            "No production embedding model, version, or dimensional contract "
                            "is selected."
                        ),
                        "Approve an exact model and immutable output contract before indexing.",
                    ),
                    _reason(
                        "PROVIDER_NOT_SELECTED",
                        BlockedProviderReasonCategory.VENDOR,
                        "No production embedding vendor or self-hosted runtime is selected.",
                        "Select and govern a vendor or runtime in a separately authorized stage.",
                    ),
                ),
            ),
            _disclosure_descriptor(
                "SSE_DISCLOSURE_BODIES_V1",
                "Shanghai Stock Exchange disclosure bodies",
            ),
            _disclosure_descriptor(
                "SZSE_DISCLOSURE_BODIES_V1",
                "Shenzhen Stock Exchange disclosure bodies",
            ),
        ),
        key=lambda descriptor: descriptor.provider_code,
    )
)
_BLOCKED_BY_CODE = {
    descriptor.provider_code: descriptor for descriptor in BLOCKED_PROVIDER_DESCRIPTORS
}


def get_blocked_provider_descriptor(provider_code: str) -> BlockedProviderDescriptor | None:
    """Return only an exact blocked Provider code match."""

    return _BLOCKED_BY_CODE.get(provider_code)


__all__ = [
    "BLOCKED_PROVIDER_DESCRIPTORS",
    "BlockedProviderDescriptor",
    "BlockedProviderReason",
    "BlockedProviderReasonCategory",
    "get_blocked_provider_descriptor",
]
