from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from stock_research_agent.domain.live_evidence.enums import ManualReviewDecision
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.manual import (
    ManualEvidenceService,
    manual_review_basis_checksum,
)
from stock_research_agent.domain.live_evidence.schemas import ManualEvidenceReviewWrite


def _review(*, decision: ManualReviewDecision, blocking: int) -> ManualEvidenceReviewWrite:
    file_checksum = "a" * 64
    declaration_checksum = "b" * 64
    validation_set_checksum = "c" * 64
    return ManualEvidenceReviewWrite(
        import_request_id=uuid4(),
        declaration_id=uuid4(),
        file_checksum=file_checksum,
        declaration_checksum=declaration_checksum,
        validation_set_checksum=validation_set_checksum,
        review_basis_checksum=manual_review_basis_checksum(
            file_checksum=file_checksum,
            declaration_checksum=declaration_checksum,
            validation_set_checksum=validation_set_checksum,
        ),
        decision=decision,
        blocking_validation_count=blocking,
        permitted_evidence_roles=("LIMITATION",),
        review_registry_id="LOCAL_HUMAN_REVIEW",
        review_registry_version="1.0.0",
        review_registry_checksum="d" * 64,
        reviewed_by="LOCAL_OPERATOR",
        reviewed_at=datetime(2026, 8, 1, 4, tzinfo=UTC),
    )


def test_review_is_bound_to_file_declaration_and_validation_set() -> None:
    write = _review(decision=ManualReviewDecision.APPROVED, blocking=0)

    record = ManualEvidenceService.review(write)

    assert record.review_basis_checksum == write.review_basis_checksum
    assert len(record.review_checksum) == 64
    assert len(record.review_signature) == 64


def test_review_signature_is_stable_for_same_review() -> None:
    write = _review(decision=ManualReviewDecision.APPROVED, blocking=0)

    assert ManualEvidenceService.review(write).review_signature == (
        ManualEvidenceService.review(write).review_signature
    )


def test_changed_review_basis_checksum_is_rejected() -> None:
    write = _review(decision=ManualReviewDecision.APPROVED, blocking=0).model_copy(
        update={"review_basis_checksum": "e" * 64}
    )

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        ManualEvidenceService.review(write)

    assert exc_info.value.code == "MANUAL_REVIEW_CHECKSUM_MISMATCH"


@pytest.mark.parametrize(
    "decision",
    [ManualReviewDecision.APPROVED, ManualReviewDecision.PARTIAL],
)
def test_blocking_validation_cannot_be_waived(decision: ManualReviewDecision) -> None:
    write = _review(decision=decision, blocking=1)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        ManualEvidenceService.review(write)

    assert exc_info.value.code == "MANUAL_BLOCK_CANNOT_BE_WAIVED"


@pytest.mark.parametrize(
    "decision",
    [ManualReviewDecision.REJECTED, ManualReviewDecision.BLOCKED],
)
def test_blocking_validation_can_only_end_rejected_or_blocked(
    decision: ManualReviewDecision,
) -> None:
    record = ManualEvidenceService.review(_review(decision=decision, blocking=1))

    assert record.decision is decision
