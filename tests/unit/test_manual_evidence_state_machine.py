from __future__ import annotations

from stock_research_agent.domain.live_evidence.enums import (
    ManualEvidenceState,
    ManualReviewDecision,
    ManualValidationStatus,
)
from stock_research_agent.domain.live_evidence.manual import derive_manual_import_state
from stock_research_agent.domain.live_evidence.schemas import (
    ManualEvidenceImportPlan,
    ManualEvidenceImportRecord,
    ManualEvidenceReviewRecord,
    ManualEvidenceValidationRecord,
)


def _plan() -> ManualEvidenceImportPlan:
    return ManualEvidenceImportPlan.model_construct(state=ManualEvidenceState.RECEIVED)


def _received() -> ManualEvidenceImportRecord:
    return ManualEvidenceImportRecord.model_construct(state=ManualEvidenceState.RECEIVED)


def _validation(status: ManualValidationStatus) -> ManualEvidenceValidationRecord:
    return ManualEvidenceValidationRecord.model_construct(status=status)


def _review(decision: ManualReviewDecision) -> ManualEvidenceReviewRecord:
    return ManualEvidenceReviewRecord.model_construct(decision=decision)


def test_plan_without_received_bytes_stays_received() -> None:
    assert derive_manual_import_state(_plan(), (), (), manifest_present=False) is (
        ManualEvidenceState.RECEIVED
    )


def test_received_bytes_without_validations_are_quarantined() -> None:
    assert derive_manual_import_state(_received(), (), (), manifest_present=False) is (
        ManualEvidenceState.QUARANTINED
    )


def test_validation_without_review_remains_validating() -> None:
    assert (
        derive_manual_import_state(
            _received(),
            (_validation(ManualValidationStatus.PASS),),
            (),
            manifest_present=False,
        )
        is ManualEvidenceState.VALIDATING
    )


def test_blocking_validation_has_precedence_over_approval_and_manifest() -> None:
    assert (
        derive_manual_import_state(
            _received(),
            (_validation(ManualValidationStatus.BLOCKED),),
            (_review(ManualReviewDecision.APPROVED),),
            manifest_present=True,
        )
        is ManualEvidenceState.BLOCKED
    )


def test_failed_validation_is_rejected() -> None:
    assert (
        derive_manual_import_state(
            _received(),
            (_validation(ManualValidationStatus.FAIL),),
            (),
            manifest_present=False,
        )
        is ManualEvidenceState.REJECTED
    )


def test_review_decisions_map_to_stable_states() -> None:
    validation = (_validation(ManualValidationStatus.PASS),)
    assert (
        derive_manual_import_state(
            _received(), validation, (_review(ManualReviewDecision.APPROVED),), False
        )
        is ManualEvidenceState.APPROVED
    )
    assert (
        derive_manual_import_state(
            _received(), validation, (_review(ManualReviewDecision.PARTIAL),), False
        )
        is ManualEvidenceState.PARTIAL
    )
    assert (
        derive_manual_import_state(
            _received(), validation, (_review(ManualReviewDecision.REJECTED),), False
        )
        is ManualEvidenceState.REJECTED
    )
    assert (
        derive_manual_import_state(
            _received(), validation, (_review(ManualReviewDecision.BLOCKED),), False
        )
        is ManualEvidenceState.BLOCKED
    )


def test_manifest_only_advances_approved_or_partial_review() -> None:
    validation = (_validation(ManualValidationStatus.PASS),)

    assert (
        derive_manual_import_state(
            _received(), validation, (_review(ManualReviewDecision.APPROVED),), True
        )
        is ManualEvidenceState.INGESTED
    )
    assert (
        derive_manual_import_state(
            _received(), validation, (_review(ManualReviewDecision.PARTIAL),), True
        )
        is ManualEvidenceState.INGESTED
    )
