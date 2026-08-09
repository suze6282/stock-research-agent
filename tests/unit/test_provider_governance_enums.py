import importlib
from enum import StrEnum
from pathlib import Path

ROOT = Path(__file__).parents[2]
ENUMS_MODULE = ROOT / "src" / "stock_research_agent" / "domain" / "providers" / "enums.py"


def _load_enums() -> object:
    assert ENUMS_MODULE.is_file(), "Stage 9 provider status vocabulary is absent"
    return importlib.import_module("stock_research_agent.domain.providers.enums")


def test_provider_governance_status_values_are_exact_and_stable() -> None:
    enums = _load_enums()

    expected = {
        "ProviderDefinitionStatus": (
            "DRAFT",
            "ACTIVE",
            "SUSPENDED",
            "RETIRED",
            "BLOCKED",
        ),
        "ProviderCapabilityStatus": (
            "IMPLEMENTED_OFFLINE",
            "ENABLED",
            "BLOCKED",
            "RETIRED",
        ),
        "ProviderLicenseStatus": (
            "APPROVED",
            "RESTRICTED_REVIEW_REQUIRED",
            "BLOCKED",
            "UNKNOWN_REQUIRES_REVIEW",
        ),
        "ProviderCredentialStatus": (
            "NOT_REQUIRED",
            "NOT_READ",
            "CONFIGURED_METADATA_ONLY",
            "MISSING",
            "BLOCKED",
        ),
        "ProviderConfigurationStatus": ("VALID", "INVALID", "BLOCKED"),
        "ProviderLiveAuthorizationStatus": (
            "NOT_ATTEMPTED",
            "AUTHORIZED",
            "EXPIRED",
            "CONSUMED",
            "BLOCKED",
        ),
        "ProviderProductionStatus": (
            "ENABLED",
            "CONDITIONAL",
            "BLOCKED",
            "TEST_ONLY",
        ),
        "ProviderRunStatus": (
            "PLANNED",
            "QUEUED",
            "RUNNING",
            "PAUSED",
            "COMPLETED",
            "PARTIAL",
            "BLOCKED",
            "FAILED",
            "CANCELLED",
        ),
        "ProviderSyncSliceStatus": (
            "PENDING",
            "RUNNING",
            "COMPLETED",
            "PARTIAL",
            "BLOCKED",
            "FAILED",
            "CANCELLED",
        ),
        "ProviderCircuitStatus": ("CLOSED", "OPEN", "HALF_OPEN"),
        "ProviderDataQualityStatus": ("PASS", "PARTIAL", "BLOCKED", "FAILED"),
        "ProviderSyntheticStatus": (
            "REAL_VERIFIED",
            "FIXTURE_REAL_EXCERPT",
            "SYNTHETIC_TEST_ONLY",
            "UNKNOWN",
        ),
        "ProviderLiveValidationStatus": (
            "NOT_ATTEMPTED",
            "RUNNING",
            "PASSED",
            "FAILED",
            "BLOCKED",
            "CANCELLED",
        ),
    }

    for class_name, expected_values in expected.items():
        enum_type = getattr(enums, class_name)
        assert issubclass(enum_type, StrEnum)
        assert tuple(member.value for member in enum_type) == expected_values
        assert len(enum_type.__members__) == len(expected_values)


def test_tushare_offline_and_production_states_cannot_be_conflated() -> None:
    enums = _load_enums()

    assert (
        enums.ProviderCapabilityStatus.IMPLEMENTED_OFFLINE.value
        != enums.ProviderProductionStatus.BLOCKED.value
    )
    assert (
        enums.ProviderLicenseStatus.RESTRICTED_REVIEW_REQUIRED.value
        != enums.ProviderLiveValidationStatus.NOT_ATTEMPTED.value
    )
    assert enums.ProviderCredentialStatus.NOT_READ.value == "NOT_READ"
