from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.live_evidence.enums import (
    ManualEvidenceSourceType,
    ManualLicenseStatus,
    RightsDecision,
)
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.manual import ManualEvidenceService
from stock_research_agent.domain.live_evidence.schemas import (
    ManualEvidenceSourceDeclarationWrite,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus


def _declaration() -> ManualEvidenceSourceDeclarationWrite:
    return ManualEvidenceSourceDeclarationWrite(
        import_request_id=uuid4(),
        security_id=uuid4(),
        issuer_id=uuid4(),
        declaration_version=1,
        source_type=ManualEvidenceSourceType.USER_SUPPLIED_UNVERIFIED_DOCUMENT,
        source_institution="SYNTHETIC_TEST_SOURCE",
        source_description="Synthetic source used only for offline contract tests.",
        source_url=None,
        acquisition_method="USER_SUPPLIED_LOCAL_FILE",
        license_status=ManualLicenseStatus.CONFIRMED,
        license_policy_reference="SYNTHETIC_TEST_POLICY_V1",
        acquisition_right=RightsDecision.ALLOWED,
        raw_storage_right=RightsDecision.ALLOWED,
        excerpt_right=RightsDecision.ALLOWED,
        derived_use_right=RightsDecision.PROHIBITED,
        commercial_use_right=RightsDecision.PROHIBITED,
        redistribution_right=RightsDecision.PROHIBITED,
        long_term_retention_right=RightsDecision.PROHIBITED,
        synthetic_status=ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
        allowed_for_company_research=False,
        declared_by="LOCAL_OPERATOR",
        declared_at=datetime(2026, 8, 1, 2, tzinfo=UTC),
    )


def test_complete_source_declaration_is_immutable_and_versioned() -> None:
    write = _declaration()

    record = ManualEvidenceService.declare_source(write)

    assert record.declaration_version == 1
    assert len(record.declaration_checksum) == 64
    assert record.allowed_for_company_research is False
    with pytest.raises(ValidationError):
        record.source_institution = "CHANGED"


def test_declaration_checksum_is_stable_and_covers_rights() -> None:
    write = _declaration()

    first = ManualEvidenceService.declare_source(write)
    repeated = ManualEvidenceService.declare_source(write)
    changed = ManualEvidenceService.declare_source(
        write.model_copy(update={"excerpt_right": RightsDecision.PROHIBITED})
    )

    assert first.declaration_checksum == repeated.declaration_checksum
    assert first.declaration_checksum != changed.declaration_checksum


@pytest.mark.parametrize(
    "field",
    [
        "acquisition_right",
        "raw_storage_right",
        "excerpt_right",
        "derived_use_right",
        "commercial_use_right",
        "redistribution_right",
        "long_term_retention_right",
    ],
)
def test_unknown_critical_right_blocks_declaration(field: str) -> None:
    write = _declaration().model_copy(update={field: RightsDecision.UNKNOWN})

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        ManualEvidenceService.declare_source(write)

    assert exc_info.value.code == "MANUAL_LICENSE_UNKNOWN"


@pytest.mark.parametrize("field", ["source_institution", "source_description"])
def test_incomplete_source_declaration_fails_closed(field: str) -> None:
    write = _declaration().model_copy(update={field: ""})

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        ManualEvidenceService.declare_source(write)

    assert exc_info.value.code == "MANUAL_DECLARATION_INCOMPLETE"


def test_synthetic_declaration_cannot_enable_company_research() -> None:
    write = _declaration().model_copy(update={"allowed_for_company_research": True})

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        ManualEvidenceService.declare_source(write)

    assert exc_info.value.code == "MANUAL_DECLARATION_INCOMPLETE"
