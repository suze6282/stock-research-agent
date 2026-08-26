"""Deterministic, offline-only manual evidence intake contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from uuid import uuid4

from stock_research_agent.domain.live_evidence.enums import (
    EvidenceSourceType,
    ManualEvidenceSourceType,
    ManualEvidenceState,
    ManualLicenseStatus,
    ManualReviewDecision,
    ManualValidationStatus,
    RightsDecision,
)
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.schemas import (
    ManualEvidenceImportPlan,
    ManualEvidenceImportPlanRequest,
    ManualEvidenceImportRecord,
    ManualEvidenceReceiveRequest,
    ManualEvidenceReviewRecord,
    ManualEvidenceReviewWrite,
    ManualEvidenceSourceDeclarationRecord,
    ManualEvidenceSourceDeclarationWrite,
    ManualEvidenceValidationRecord,
    ManualEvidenceValidationWrite,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.providers.schemas import FrozenProviderContract


def _checksum(value: FrozenProviderContract) -> str:
    canonical = json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def manual_review_basis_checksum(
    *,
    file_checksum: str,
    declaration_checksum: str,
    validation_set_checksum: str,
) -> str:
    canonical = json.dumps(
        {
            "declaration_checksum": declaration_checksum,
            "file_checksum": file_checksum,
            "validation_set_checksum": validation_set_checksum,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def derive_manual_import_state(
    request: ManualEvidenceImportPlan | ManualEvidenceImportRecord,
    validations: Sequence[ManualEvidenceValidationRecord],
    reviews: Sequence[ManualEvidenceReviewRecord],
    manifest_present: bool,
) -> ManualEvidenceState:
    if not isinstance(request, ManualEvidenceImportRecord):
        return ManualEvidenceState.RECEIVED
    if not validations:
        return ManualEvidenceState.QUARANTINED

    validation_statuses = {item.status for item in validations}
    if ManualValidationStatus.BLOCKED in validation_statuses:
        return ManualEvidenceState.BLOCKED
    if ManualValidationStatus.FAIL in validation_statuses:
        return ManualEvidenceState.REJECTED
    if not reviews:
        return ManualEvidenceState.VALIDATING

    decision = reviews[-1].decision
    if decision is ManualReviewDecision.BLOCKED:
        return ManualEvidenceState.BLOCKED
    if decision is ManualReviewDecision.REJECTED:
        return ManualEvidenceState.REJECTED
    if manifest_present:
        return ManualEvidenceState.INGESTED
    if (
        decision is ManualReviewDecision.PARTIAL
        or ManualValidationStatus.PARTIAL in validation_statuses
    ):
        return ManualEvidenceState.PARTIAL
    return ManualEvidenceState.APPROVED


class ManualEvidenceService:
    @staticmethod
    def plan(value: ManualEvidenceImportPlanRequest) -> ManualEvidenceImportPlan:
        if not isinstance(value.declared_source_type, ManualEvidenceSourceType):
            raise LiveEvidenceValidationError("MANUAL_SOURCE_TYPE_INVALID")
        gate_a_scope = (
            value.acquisition_kind is EvidenceSourceType.MANUAL_IMPORT
            and value.offline
            and value.not_live
            and (
                value.synthetic_status is not ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY
                or value.company_evidence_status == "NOT_COMPANY_EVIDENCE"
            )
        )
        if not gate_a_scope:
            raise LiveEvidenceValidationError("MANUAL_IMPORT_SCOPE_INVALID")
        return ManualEvidenceImportPlan(
            **value.model_dump(),
            state=ManualEvidenceState.RECEIVED,
            plan_checksum=_checksum(value),
        )

    @staticmethod
    def receive(value: ManualEvidenceReceiveRequest) -> ManualEvidenceImportRecord:
        if (
            value.observed_byte_size != value.plan.declared_byte_size
            or value.observed_checksum != value.plan.declared_checksum
        ):
            raise LiveEvidenceValidationError("MANUAL_IMPORT_SCOPE_INVALID")
        return ManualEvidenceImportRecord(
            **value.plan.model_dump(),
            id=uuid4(),
            observed_byte_size=value.observed_byte_size,
            observed_checksum=value.observed_checksum,
            received_at=value.received_at,
            created_at=value.received_at,
        )

    @staticmethod
    def declare_source(
        value: ManualEvidenceSourceDeclarationWrite,
    ) -> ManualEvidenceSourceDeclarationRecord:
        if not value.source_institution or not value.source_description:
            raise LiveEvidenceValidationError("MANUAL_DECLARATION_INCOMPLETE")
        rights = (
            value.acquisition_right,
            value.raw_storage_right,
            value.excerpt_right,
            value.derived_use_right,
            value.commercial_use_right,
            value.redistribution_right,
            value.long_term_retention_right,
        )
        if value.license_status is not ManualLicenseStatus.CONFIRMED or any(
            right is RightsDecision.UNKNOWN for right in rights
        ):
            raise LiveEvidenceValidationError("MANUAL_LICENSE_UNKNOWN")
        if (
            value.synthetic_status is ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY
            and value.allowed_for_company_research
        ):
            raise LiveEvidenceValidationError("MANUAL_DECLARATION_INCOMPLETE")
        return ManualEvidenceSourceDeclarationRecord(
            **value.model_dump(),
            id=uuid4(),
            declaration_checksum=_checksum(value),
            created_at=value.declared_at,
        )

    @staticmethod
    def record_validation(
        value: ManualEvidenceValidationWrite,
        *,
        existing: ManualEvidenceValidationRecord | None = None,
    ) -> ManualEvidenceValidationRecord:
        checksum = _checksum(value)
        if existing is not None:
            identity = (
                value.import_request_id,
                value.validator_code,
                value.validator_version,
                value.input_checksum,
            )
            existing_identity = (
                existing.import_request_id,
                existing.validator_code,
                existing.validator_version,
                existing.input_checksum,
            )
            if identity == existing_identity and checksum == existing.validation_checksum:
                return existing
            raise LiveEvidenceValidationError("MANUAL_VALIDATION_CONFLICT")
        return ManualEvidenceValidationRecord(
            **value.model_dump(),
            id=uuid4(),
            validation_checksum=checksum,
            created_at=value.validated_at,
        )

    @staticmethod
    def review(value: ManualEvidenceReviewWrite) -> ManualEvidenceReviewRecord:
        expected_basis = manual_review_basis_checksum(
            file_checksum=value.file_checksum,
            declaration_checksum=value.declaration_checksum,
            validation_set_checksum=value.validation_set_checksum,
        )
        if value.review_basis_checksum != expected_basis:
            raise LiveEvidenceValidationError("MANUAL_REVIEW_CHECKSUM_MISMATCH")
        if value.blocking_validation_count > 0 and value.decision in {
            ManualReviewDecision.APPROVED,
            ManualReviewDecision.PARTIAL,
        }:
            raise LiveEvidenceValidationError("MANUAL_BLOCK_CANNOT_BE_WAIVED")
        review_checksum = _checksum(value)
        signature = hashlib.sha256(
            f"{value.review_registry_checksum}:{review_checksum}".encode("ascii")
        ).hexdigest()
        return ManualEvidenceReviewRecord(
            **value.model_dump(),
            id=uuid4(),
            review_checksum=review_checksum,
            review_signature=signature,
            created_at=value.reviewed_at,
        )
