from __future__ import annotations

import re
from datetime import date, timedelta
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from stock_research_agent.domain.live_evidence.enums import (
    ConsumptionState,
    EvidenceSourceType,
    ExecutionApprovalState,
    LiveAuthorizationEventType,
    LiveAuthorizationState,
    ManualEvidenceSourceType,
    ManualEvidenceState,
    ManualLicenseStatus,
    ManualReviewDecision,
    ManualValidationSeverity,
    ManualValidationStatus,
    RightsDecision,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
    ProviderCode,
    SemanticVersion,
)

_DOMAIN_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)
_CAPABILITY_PATTERN = r"^[A-Z][A-Z0-9_]{2,63}$"
_ACTOR_PATTERN = r"^[A-Z][A-Z0-9_]{2,63}$"
_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_FILING_TYPE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,15}$")


class LiveAuthorizationGrantWrite(FrozenProviderContract):
    provider_definition_id: UUID
    provider_code: ProviderCode
    provider_definition_version: SemanticVersion
    provider_definition_checksum: Checksum
    provider_capability_id: UUID
    capability_code: str = Field(pattern=_CAPABILITY_PATTERN)
    capability_version: SemanticVersion
    official_domains: tuple[str, ...] = Field(min_length=1, max_length=8)
    security_id: UUID
    issuer_id: UUID
    provider_security_identifier: str = Field(pattern=_IDENTIFIER_PATTERN)
    request_methods: tuple[str, ...] = Field(min_length=1, max_length=4)
    request_limit: int = Field(ge=1, le=100)
    byte_limit: int = Field(ge=1, le=52_428_800)
    date_from: date
    date_to: date
    filing_types: tuple[str, ...] = Field(min_length=1, max_length=8)
    allowed_document_count: int = Field(ge=1, le=100)
    credential_reference_id: UUID
    user_agent_reference_id: UUID
    license_policy_id: UUID
    license_policy_version: SemanticVersion
    license_policy_checksum: Checksum
    provider_policy_id: UUID
    provider_policy_version: SemanticVersion
    provider_policy_checksum: Checksum
    raw_storage_allowed: bool
    cache_allowed: bool
    retention_deadline: AwareUtcDateTime
    approved_at: AwareUtcDateTime
    expires_at: AwareUtcDateTime
    approved_by: str = Field(pattern=_ACTOR_PATTERN)
    canonical_checksum: Checksum

    @field_validator("official_domains")
    @classmethod
    def validate_official_domains(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("official_domains must be unique and sorted")
        if any(len(domain) > 253 or _DOMAIN_PATTERN.fullmatch(domain) is None for domain in value):
            raise ValueError("official_domains must contain exact lowercase DNS names")
        return value

    @field_validator("request_methods")
    @classmethod
    def validate_request_methods(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))) or any(method != "GET" for method in value):
            raise ValueError("request_methods must be the exact GET allowlist")
        return value

    @field_validator("filing_types")
    @classmethod
    def validate_filing_types(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("filing_types must be unique and sorted")
        if any(_FILING_TYPE_PATTERN.fullmatch(item) is None for item in value):
            raise ValueError("filing_types must use stable form codes")
        return value

    @model_validator(mode="after")
    def validate_finite_scope(self) -> LiveAuthorizationGrantWrite:
        if self.date_to < self.date_from:
            raise ValueError("date_to must not precede date_from")
        if self.allowed_document_count > self.request_limit:
            raise ValueError("allowed_document_count must not exceed request_limit")
        if self.expires_at <= self.approved_at:
            raise ValueError("expires_at must be later than approved_at")
        if self.expires_at - self.approved_at > timedelta(minutes=30):
            raise ValueError("authorization lifetime must not exceed thirty minutes")
        if self.retention_deadline <= self.approved_at:
            raise ValueError("retention_deadline must be later than approved_at")
        return self


class LiveAuthorizationGrantRecord(LiveAuthorizationGrantWrite):
    id: UUID
    created_at: AwareUtcDateTime


class ConsumptionReservationRequest(FrozenProviderContract):
    authorization_id: UUID
    request_attempt_id: UUID
    reserved_bytes: int = Field(ge=1, le=52_428_800)
    reserved_at: AwareUtcDateTime


class ConsumptionReservation(ConsumptionReservationRequest):
    id: UUID
    state: ConsumptionState

    @field_validator("state")
    @classmethod
    def validate_reserved_state(cls, value: ConsumptionState) -> ConsumptionState:
        if value is not ConsumptionState.RESERVED:
            raise ValueError("reservation state must be RESERVED")
        return value


class ConsumptionSettlementRequest(FrozenProviderContract):
    authorization_id: UUID
    request_attempt_id: UUID
    actual_bytes: int = Field(ge=0, le=52_428_800)
    socket_opened: bool
    state: ConsumptionState
    settled_at: AwareUtcDateTime

    @field_validator("state")
    @classmethod
    def validate_terminal_state(cls, value: ConsumptionState) -> ConsumptionState:
        if value not in {ConsumptionState.SETTLED, ConsumptionState.ABANDONED}:
            raise ValueError("settlement state must be SETTLED or ABANDONED")
        return value


class LiveAuthorizationConsumptionRecord(FrozenProviderContract):
    id: UUID
    authorization_id: UUID
    request_attempt_id: UUID
    reserved_bytes: int = Field(ge=1, le=52_428_800)
    actual_bytes: int = Field(ge=0, le=52_428_800)
    socket_opened: bool
    state: ConsumptionState
    reserved_at: AwareUtcDateTime
    settled_at: AwareUtcDateTime


class LiveExecutionApprovalWrite(FrozenProviderContract):
    authorization_id: UUID
    authorization_checksum: Checksum
    sync_plan_id: UUID
    plan_checksum: Checksum
    approval_registry_id: str = Field(pattern=_CAPABILITY_PATTERN)
    approval_registry_version: SemanticVersion
    approval_registry_checksum: Checksum
    approved_by: str = Field(pattern=_ACTOR_PATTERN)
    approved_at: AwareUtcDateTime
    expires_at: AwareUtcDateTime

    @model_validator(mode="after")
    def validate_lifetime(self) -> LiveExecutionApprovalWrite:
        lifetime = self.expires_at - self.approved_at
        if lifetime <= timedelta(0) or lifetime > timedelta(minutes=10):
            raise ValueError("execution approval lifetime must be within ten minutes")
        return self


class LiveExecutionApprovalRecord(LiveExecutionApprovalWrite):
    id: UUID
    approval_signature: Checksum
    state: ExecutionApprovalState
    created_at: AwareUtcDateTime


class ValidateExecutionApprovalRequest(FrozenProviderContract):
    approval: LiveExecutionApprovalRecord
    authorization_checksum: Checksum
    plan_checksum: Checksum
    checked_at: AwareUtcDateTime
    consumed: bool


class ExecutionApprovalDecision(FrozenProviderContract):
    state: ExecutionApprovalState
    failure_code: str | None = Field(default=None, pattern=_CAPABILITY_PATTERN)


class RevokeAuthorizationRequest(FrozenProviderContract):
    authorization_id: UUID
    expected_state: LiveAuthorizationState
    expected_event_count: int = Field(ge=0, le=100)
    reason_code: str = Field(pattern=_CAPABILITY_PATTERN)
    revoked_by: str = Field(pattern=_ACTOR_PATTERN)
    revoked_at: AwareUtcDateTime

    @field_validator("expected_state")
    @classmethod
    def validate_expected_state(
        cls,
        value: LiveAuthorizationState,
    ) -> LiveAuthorizationState:
        if value not in {
            LiveAuthorizationState.DRAFT,
            LiveAuthorizationState.APPROVED,
            LiveAuthorizationState.ACTIVE,
        }:
            raise ValueError("expected_state must be nonterminal")
        return value


class AuthorizationRevocationResult(FrozenProviderContract):
    authorization_id: UUID
    state: LiveAuthorizationState
    events: tuple[LiveAuthorizationEventType, ...]
    event_sequence: int = Field(ge=1, le=101)


class AuthorizationExecutionScope(FrozenProviderContract):
    provider_definition_id: UUID
    provider_code: ProviderCode
    provider_definition_version: SemanticVersion
    provider_capability_id: UUID
    capability_code: str = Field(pattern=_CAPABILITY_PATTERN)
    capability_version: SemanticVersion
    security_id: UUID
    issuer_id: UUID
    provider_security_identifier: str = Field(pattern=_IDENTIFIER_PATTERN)


class AuthorizationDecision(FrozenProviderContract):
    allowed: bool
    failure_code: str | None = Field(default=None, pattern=_CAPABILITY_PATTERN)


class ManualEvidenceImportPlanRequest(FrozenProviderContract):
    security_id: UUID
    issuer_id: UUID
    opaque_file_reference: str = Field(pattern=_IDENTIFIER_PATTERN)
    original_filename: str = Field(min_length=1, max_length=255)
    declared_source_type: ManualEvidenceSourceType
    source_description: str = Field(min_length=1, max_length=1024)
    source_url: str | None = Field(default=None, max_length=2048)
    document_type: str = Field(pattern=_CAPABILITY_PATTERN)
    report_period_start: date | None
    report_period_end: date | None
    source_published_at: AwareUtcDateTime | None
    retrieved_at: AwareUtcDateTime
    language: str = Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    acquisition_method: str = Field(pattern=_CAPABILITY_PATTERN)
    declared_content_type: str = Field(min_length=3, max_length=128)
    declared_byte_size: int = Field(ge=1, le=26_214_400)
    declared_checksum: Checksum
    submitted_by: str = Field(pattern=_ACTOR_PATTERN)
    acquisition_kind: EvidenceSourceType
    synthetic_status: ProviderSyntheticStatus
    company_evidence_status: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    offline: bool
    not_live: bool

    @model_validator(mode="after")
    def validate_period(self) -> ManualEvidenceImportPlanRequest:
        if (
            self.report_period_start is not None
            and self.report_period_end is not None
            and self.report_period_end < self.report_period_start
        ):
            raise ValueError("report period end must not precede start")
        return self


class ManualEvidenceImportPlan(ManualEvidenceImportPlanRequest):
    state: ManualEvidenceState
    plan_checksum: Checksum


class ManualEvidenceReceiveRequest(FrozenProviderContract):
    plan: ManualEvidenceImportPlan
    observed_byte_size: int = Field(ge=1, le=26_214_400)
    observed_checksum: Checksum
    received_at: AwareUtcDateTime


class ManualEvidenceImportRecord(ManualEvidenceImportPlan):
    id: UUID
    observed_byte_size: int = Field(ge=1, le=26_214_400)
    observed_checksum: Checksum
    received_at: AwareUtcDateTime
    created_at: AwareUtcDateTime


class ManualEvidenceSourceDeclarationWrite(FrozenProviderContract):
    import_request_id: UUID
    security_id: UUID
    issuer_id: UUID
    declaration_version: int = Field(ge=1, le=1000)
    source_type: ManualEvidenceSourceType
    source_institution: str = Field(min_length=1, max_length=256)
    source_description: str = Field(min_length=1, max_length=2048)
    source_url: str | None = Field(default=None, max_length=2048)
    acquisition_method: str = Field(pattern=_CAPABILITY_PATTERN)
    license_status: ManualLicenseStatus
    license_policy_reference: str = Field(pattern=_IDENTIFIER_PATTERN)
    acquisition_right: RightsDecision
    raw_storage_right: RightsDecision
    excerpt_right: RightsDecision
    derived_use_right: RightsDecision
    commercial_use_right: RightsDecision
    redistribution_right: RightsDecision
    long_term_retention_right: RightsDecision
    synthetic_status: ProviderSyntheticStatus
    allowed_for_company_research: bool
    declared_by: str = Field(pattern=_ACTOR_PATTERN)
    declared_at: AwareUtcDateTime


class ManualEvidenceSourceDeclarationRecord(ManualEvidenceSourceDeclarationWrite):
    id: UUID
    declaration_checksum: Checksum
    created_at: AwareUtcDateTime


class ManualEvidenceValidationWrite(FrozenProviderContract):
    import_request_id: UUID
    validator_code: str = Field(pattern=_CAPABILITY_PATTERN)
    validator_version: SemanticVersion
    input_checksum: Checksum
    status: ManualValidationStatus
    severity: ManualValidationSeverity
    finding_codes: tuple[str, ...] = Field(max_length=64)
    safe_detail: str = Field(min_length=1, max_length=1024)
    validated_at: AwareUtcDateTime

    @field_validator("finding_codes")
    @classmethod
    def validate_finding_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("finding_codes must be unique and sorted")
        if any(re.fullmatch(_CAPABILITY_PATTERN, item) is None for item in value):
            raise ValueError("finding_codes must use stable uppercase codes")
        return value


class ManualEvidenceValidationRecord(ManualEvidenceValidationWrite):
    id: UUID
    validation_checksum: Checksum
    created_at: AwareUtcDateTime


class ManualEvidenceReviewWrite(FrozenProviderContract):
    import_request_id: UUID
    declaration_id: UUID
    file_checksum: Checksum
    declaration_checksum: Checksum
    validation_set_checksum: Checksum
    review_basis_checksum: Checksum
    decision: ManualReviewDecision
    blocking_validation_count: int = Field(ge=0, le=1000)
    permitted_evidence_roles: tuple[str, ...] = Field(max_length=16)
    review_registry_id: str = Field(pattern=_CAPABILITY_PATTERN)
    review_registry_version: SemanticVersion
    review_registry_checksum: Checksum
    reviewed_by: str = Field(pattern=_ACTOR_PATTERN)
    reviewed_at: AwareUtcDateTime

    @field_validator("permitted_evidence_roles")
    @classmethod
    def validate_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("permitted_evidence_roles must be unique and sorted")
        if any(re.fullmatch(_CAPABILITY_PATTERN, item) is None for item in value):
            raise ValueError("permitted_evidence_roles must use stable codes")
        return value


class ManualEvidenceReviewRecord(ManualEvidenceReviewWrite):
    id: UUID
    review_checksum: Checksum
    review_signature: Checksum
    created_at: AwareUtcDateTime
