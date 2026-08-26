from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.live_evidence.enums import (
    ManualValidationSeverity,
    ManualValidationStatus,
)
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.manual import ManualEvidenceService
from stock_research_agent.domain.live_evidence.schemas import ManualEvidenceValidationWrite


def _validation() -> ManualEvidenceValidationWrite:
    return ManualEvidenceValidationWrite(
        import_request_id=uuid4(),
        validator_code="FILE_IDENTITY",
        validator_version="1.0.0",
        input_checksum="a" * 64,
        status=ManualValidationStatus.PASS,
        severity=ManualValidationSeverity.INFO,
        finding_codes=(),
        safe_detail="Synthetic file identity matches its declared checksum.",
        validated_at=datetime(2026, 8, 1, 3, tzinfo=UTC),
    )


def test_validation_result_is_append_only_and_checksum_bound() -> None:
    write = _validation()

    record = ManualEvidenceService.record_validation(write)

    assert record.status is ManualValidationStatus.PASS
    assert len(record.validation_checksum) == 64
    with pytest.raises(ValidationError):
        record.status = ManualValidationStatus.BLOCKED


def test_exact_validation_replay_is_idempotent() -> None:
    write = _validation()
    existing = ManualEvidenceService.record_validation(write)

    repeated = ManualEvidenceService.record_validation(write, existing=existing)

    assert repeated is existing


def test_same_validator_input_with_changed_result_is_conflict() -> None:
    write = _validation()
    existing = ManualEvidenceService.record_validation(write)
    changed = write.model_copy(
        update={
            "status": ManualValidationStatus.BLOCKED,
            "severity": ManualValidationSeverity.HIGH,
            "finding_codes": ("CHECKSUM_MISMATCH",),
        }
    )

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        ManualEvidenceService.record_validation(changed, existing=existing)

    assert exc_info.value.code == "MANUAL_VALIDATION_CONFLICT"


def test_validation_finding_codes_are_unique_and_sorted() -> None:
    with pytest.raises(ValidationError):
        ManualEvidenceValidationWrite(
            **{
                **_validation().model_dump(exclude={"finding_codes"}),
                "finding_codes": ("SECOND", "FIRST"),
            }
        )


def test_manual_validation_statuses_are_finite() -> None:
    assert {item.value for item in ManualValidationStatus} == {
        "PASS",
        "PARTIAL",
        "BLOCKED",
        "FAIL",
    }
