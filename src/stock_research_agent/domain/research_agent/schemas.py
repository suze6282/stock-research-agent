"""Strict immutable contracts for controlled research orchestration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from stock_research_agent.domain.research_agent.canonical import canonical_json
from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    ClaimType,
    EvidenceRole,
    EvidenceStatus,
    EvidenceType,
    ObservationStatus,
    ObservationType,
    PackageSectionStatus,
    PlannerType,
    ProviderHealthStatus,
    ReasoningProviderType,
    ResearchMode,
    ResearchPackageStatus,
    ResearchRunEventType,
    ResearchRunStatus,
    ResearchSection,
    ResearchStepStatus,
    ResearchStepType,
    ResearchType,
    SyntheticStatus,
    ToolInvocationStatus,
)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("datetime must use an aware UTC timezone")
    return value.astimezone(UTC)


def _finite_decimal(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("Decimal must be finite")
    return value


def _reject_binary_float(value: object) -> None:
    if isinstance(value, float):
        raise ValueError("binary floating-point values are not allowed")
    if isinstance(value, dict):
        for item in value.values():
            _reject_binary_float(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_binary_float(item)


AwareUtcDateTime = Annotated[datetime, AfterValidator(_aware_utc)]
ExactDecimal = Annotated[Decimal, AfterValidator(_finite_decimal)]
Checksum = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Version = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,127}$")]
Code = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_:-]{0,127}$")]


class FrozenContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    @model_validator(mode="after")
    def reject_binary_floats(self) -> FrozenContract:
        _reject_binary_float(self.model_dump(mode="python"))
        return self


class AllowedTool(FrozenContract):
    tool_name: str = Field(min_length=1, max_length=128)
    tool_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")


class RequestedBudgets(FrozenContract):
    max_steps: int | None = Field(default=None, ge=1, le=20)
    max_tool_calls: int | None = Field(default=None, ge=1, le=50)
    max_calls_per_tool: int | None = Field(default=None, ge=1, le=5)
    max_retries_per_step: int | None = Field(default=None, ge=0, le=1)
    max_duration_seconds: int | None = Field(default=None, ge=1, le=600)


class ResearchPolicyRecord(FrozenContract):
    version: Version
    checksum: Checksum
    allowed_research_types: tuple[ResearchType, ...] = Field(min_length=1, max_length=6)
    allowed_sections: tuple[ResearchSection, ...] = Field(min_length=1, max_length=10)
    allowed_tools: tuple[AllowedTool, ...] = Field(min_length=1, max_length=50)
    denied_tools: tuple[AllowedTool, ...] = Field(default=(), max_length=50)
    max_steps: int = Field(ge=1, le=20)
    max_tool_calls: int = Field(ge=1, le=50)
    max_calls_per_tool: int = Field(ge=1, le=5)
    max_retries_per_step: int = Field(ge=0, le=1)
    max_duration_seconds: int = Field(ge=1, le=600)
    model_token_budget: int = Field(ge=0, le=0)
    require_snapshot: bool = True
    require_as_of: bool = True
    require_evidence_for_claims: bool = True
    allow_synthetic_evidence: bool = False
    allow_unknown_published_at: bool = False
    allow_partial_completion: bool = True
    reuse_partial_runs: bool = False
    allow_model_planner: bool = False
    allow_model_reasoner: bool = False


class ResearchPolicyWrite(ResearchPolicyRecord):
    pass


class ResearchRequestCreate(FrozenContract):
    security_query: str = Field(min_length=1, max_length=256)
    research_type: ResearchType
    snapshot_id: UUID
    research_as_of_time: AwareUtcDateTime
    requested_sections: tuple[ResearchSection, ...] = Field(min_length=1, max_length=10)
    policy_version: Version
    planner_version: Version
    requested_budgets: RequestedBudgets = Field(default_factory=RequestedBudgets)
    research_mode: ResearchMode = ResearchMode.REAL_RESEARCH


class ResearchRequestRecord(ResearchRequestCreate):
    id: UUID
    resolved_security_id: UUID
    normalized_security_query: str = Field(min_length=1, max_length=256)
    tool_catalog_version: str = Field(min_length=80, max_length=80)
    tool_catalog_checksum: Checksum
    request_checksum: Checksum
    created_at: AwareUtcDateTime


class ResearchRequestWrite(ResearchRequestRecord):
    pass


class ControlledRunContext(FrozenContract):
    security_id: UUID
    snapshot_id: UUID
    research_as_of_time: AwareUtcDateTime
    research_agent_run_id: UUID
    research_request_id: UUID
    policy_version: Version
    tool_catalog_version: str = Field(min_length=80, max_length=80)


class RunBudget(FrozenContract):
    max_steps: int = Field(ge=1, le=20)
    max_tool_calls: int = Field(ge=1, le=50)
    max_calls_per_tool: int = Field(ge=1, le=5)
    max_retries_per_step: int = Field(ge=0, le=1)
    max_duration_seconds: int = Field(ge=1, le=600)
    model_token_budget: int = Field(ge=0, le=0)
    consumed_steps: int = Field(ge=0)
    consumed_tool_calls: int = Field(ge=0)
    consumed_model_tokens: int = Field(ge=0, le=0)
    elapsed_seconds: ExactDecimal = Field(ge=0)
    calls_per_tool: dict[str, int] = Field(default_factory=dict)
    retries_per_step: dict[str, int] = Field(default_factory=dict)


class ResearchAgentRunRecord(FrozenContract):
    id: UUID
    request_id: UUID
    security_id: UUID
    snapshot_id: UUID
    research_as_of_time: AwareUtcDateTime
    status: ResearchRunStatus
    policy_version: Version
    planner_version: Version
    tool_catalog_version: str = Field(min_length=80, max_length=80)
    tool_catalog_checksum: Checksum
    idempotency_key: Checksum
    budget: RunBudget
    warning_codes: tuple[Code, ...] = Field(default=(), max_length=100)
    terminal_reason_code: Code | None = None
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    terminal_at: AwareUtcDateTime | None = None


class ResearchRunWrite(ResearchAgentRunRecord):
    pass


class ResearchRunUpdate(FrozenContract):
    expected_status: ResearchRunStatus
    target_status: ResearchRunStatus
    budget: RunBudget
    warning_codes: tuple[Code, ...] = Field(default=(), max_length=100)
    terminal_reason_code: Code | None = None
    changed_at: AwareUtcDateTime


class ResearchStepDefinition(FrozenContract):
    step_index: int = Field(ge=0, le=19)
    step_key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    step_type: ResearchStepType
    title: str = Field(min_length=1, max_length=160)
    required: bool
    dependency_keys: tuple[str, ...] = Field(default=(), max_length=20)
    tool_name: str | None = Field(default=None, min_length=1, max_length=128)
    tool_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    component_name: str | None = Field(default=None, min_length=1, max_length=128)
    input_binding: dict[str, JsonValue] = Field(default_factory=dict)
    fanout_limit: int = Field(default=1, ge=1, le=5)


class ResearchPlanDraft(FrozenContract):
    planner_version: Version
    plan_version: Version
    tool_catalog_version: str = Field(min_length=80, max_length=80)
    steps: tuple[ResearchStepDefinition, ...] = Field(min_length=1, max_length=20)


class ValidatedResearchPlan(ResearchPlanDraft):
    plan_checksum: Checksum


class ResearchPlanWrite(ValidatedResearchPlan):
    id: UUID
    run_id: UUID
    created_at: AwareUtcDateTime


class ResearchPlanRecord(ResearchPlanWrite):
    pass


class ResearchStepWrite(FrozenContract):
    id: UUID
    run_id: UUID
    plan_id: UUID
    definition: ResearchStepDefinition
    status: ResearchStepStatus
    skip_reason_code: Code | None = None
    created_at: AwareUtcDateTime


class ResearchStepRecord(ResearchStepWrite):
    updated_at: AwareUtcDateTime
    terminal_at: AwareUtcDateTime | None = None


class ResearchToolInvocationWrite(FrozenContract):
    id: UUID
    run_id: UUID
    step_id: UUID
    attempt_number: int = Field(ge=1, le=2)
    tool_name: str = Field(min_length=1, max_length=128)
    tool_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: ToolInvocationStatus
    redacted_input: dict[str, JsonValue]
    input_checksum: Checksum
    started_at: AwareUtcDateTime


class ResearchToolInvocationCompletion(FrozenContract):
    status: ToolInvocationStatus
    output_checksum: Checksum | None = None
    error_code: Code | None = None
    safe_error_message: str | None = Field(default=None, max_length=256)
    completed_at: AwareUtcDateTime


class ResearchToolInvocationRecord(ResearchToolInvocationWrite):
    output_checksum: Checksum | None = None
    error_code: Code | None = None
    safe_error_message: str | None = Field(default=None, max_length=256)
    completed_at: AwareUtcDateTime | None = None


class ResearchObservationWrite(FrozenContract):
    id: UUID
    run_id: UUID
    research_step_id: UUID
    invocation_id: UUID | None
    observation_type: ObservationType
    status: ObservationStatus
    schema_version: Version
    payload: dict[str, JsonValue]
    output_checksum: Checksum
    security_id: UUID
    snapshot_id: UUID
    research_as_of_time: AwareUtcDateTime
    synthetic_status: SyntheticStatus
    warnings: tuple[Code, ...] = Field(default=(), max_length=100)
    created_at: AwareUtcDateTime

    @model_validator(mode="after")
    def limit_payload(self) -> ResearchObservationWrite:
        if len(canonical_json(self.payload).encode("utf-8")) > 262_144:
            raise ValueError("Observation payload exceeds 256 KiB")
        return self


class ResearchObservationRecord(ResearchObservationWrite):
    pass


class ResearchEvidenceWrite(FrozenContract):
    id: UUID
    run_id: UUID
    observation_id: UUID
    evidence_type: EvidenceType
    status: EvidenceStatus
    schema_version: Version
    security_id: UUID
    snapshot_id: UUID
    research_as_of_time: AwareUtcDateTime
    source_record_type: str | None = Field(default=None, max_length=128)
    source_record_id: UUID | None = None
    source_checksum: Checksum | None = None
    published_at: AwareUtcDateTime | None = None
    citation_id: UUID | None = None
    calculation_run_id: UUID | None = None
    calculation_input_ids: tuple[UUID, ...] = Field(default=(), max_length=100)
    formula_version: str | None = Field(default=None, max_length=128)
    synthetic_status: SyntheticStatus
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    warning_codes: tuple[Code, ...] = Field(default=(), max_length=100)
    created_at: AwareUtcDateTime


class ResearchEvidenceRecord(ResearchEvidenceWrite):
    pass


class ResearchClaimWrite(FrozenContract):
    id: UUID
    run_id: UUID
    claim_type: ClaimType
    lifecycle_status: ClaimLifecycleStatus
    support_status: ClaimSupportStatus | None
    statement_code: Code
    value: ExactDecimal | None = None
    unit: str | None = Field(default=None, max_length=32)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    period: str | None = Field(default=None, max_length=64)
    as_of_time: AwareUtcDateTime | None = None
    metric_basis: str | None = Field(default=None, max_length=128)
    builder_version: Version
    validator_version: Version | None = None
    created_at: AwareUtcDateTime
    completed_at: AwareUtcDateTime | None = None

    @model_validator(mode="after")
    def validate_numeric_shape(self) -> ResearchClaimWrite:
        numeric_types = {
            ClaimType.FINANCIAL_FACT,
            ClaimType.FINANCIAL_METRIC,
            ClaimType.VALUATION_METRIC,
        }
        if self.claim_type in numeric_types and any(
            value is None
            for value in (
                self.value,
                self.unit,
                self.period,
                self.as_of_time,
                self.metric_basis,
            )
        ):
            raise ValueError("numeric Claims require value, unit, period, as-of, and basis")
        if (
            self.lifecycle_status is ClaimLifecycleStatus.CANDIDATE
            and self.support_status is not None
        ):
            raise ValueError("candidate Claims cannot have a support status")
        return self


class ResearchClaimRecord(ResearchClaimWrite):
    pass


class ResearchClaimDraft(FrozenContract):
    claim_type: ClaimType
    statement_code: Code
    value: ExactDecimal | None = None
    unit: str | None = Field(default=None, max_length=32)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    period: str | None = Field(default=None, max_length=64)
    as_of_time: AwareUtcDateTime | None = None
    metric_basis: str | None = Field(default=None, max_length=128)
    proposed_evidence_ids: tuple[UUID, ...] = Field(default=(), max_length=100)


class ResearchClaimCompletion(FrozenContract):
    lifecycle_status: ClaimLifecycleStatus
    support_status: ClaimSupportStatus
    validator_version: Version
    completed_at: AwareUtcDateTime


class ClaimEvidenceLinkWrite(FrozenContract):
    id: UUID
    run_id: UUID
    claim_id: UUID
    evidence_id: UUID
    role: EvidenceRole
    created_at: AwareUtcDateTime


class ClaimEvidenceLinkRecord(ClaimEvidenceLinkWrite):
    pass


class ClaimEvidencePair(FrozenContract):
    link: ClaimEvidenceLinkRecord
    evidence: ResearchEvidenceRecord


class EvidenceLedgerView(FrozenContract):
    run_id: UUID
    evidence: tuple[ResearchEvidenceRecord, ...] = Field(max_length=500)


class ResearchPackageSection(FrozenContract):
    section: ResearchSection
    status: PackageSectionStatus
    claim_ids: tuple[UUID, ...] = Field(max_length=100)
    warning_codes: tuple[Code, ...] = Field(default=(), max_length=100)


class ResearchPackageWrite(FrozenContract):
    run_id: UUID
    request_id: UUID
    security_id: UUID
    snapshot_id: UUID
    research_as_of_time: AwareUtcDateTime
    research_type: ResearchType
    policy_version: Version
    planner_version: Version
    tool_catalog_version: str = Field(min_length=80, max_length=80)
    evidence_version: Version
    claim_version: Version
    package_version: Version
    status: ResearchPackageStatus
    sections: tuple[ResearchPackageSection, ...] = Field(min_length=1, max_length=10)
    evidence_ids: tuple[UUID, ...] = Field(max_length=500)
    unsupported_claim_ids: tuple[UUID, ...] = Field(max_length=100)
    conflicting_claim_ids: tuple[UUID, ...] = Field(max_length=100)
    blocked_capabilities: tuple[Code, ...] = Field(max_length=100)
    warnings: tuple[Code, ...] = Field(max_length=100)
    checksum: Checksum


class ResearchPackageRecord(ResearchPackageWrite):
    id: UUID
    created_at: AwareUtcDateTime


class ResearchRunEventWrite(FrozenContract):
    id: UUID
    run_id: UUID
    sequence_number: int = Field(ge=1)
    event_type: ResearchRunEventType
    from_status: ResearchRunStatus | None = None
    to_status: ResearchRunStatus | None = None
    reason_code: Code | None = None
    safe_detail: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: AwareUtcDateTime


class ResearchRunEventRecord(ResearchRunEventWrite):
    pass


class PlannerProviderMetadata(FrozenContract):
    provider_name: str = Field(min_length=1, max_length=128)
    provider_version: Version
    provider_type: PlannerType
    test_only: bool
    requires_network: bool
    uses_model: bool


class ReasoningProviderMetadata(FrozenContract):
    provider_name: str = Field(min_length=1, max_length=128)
    provider_version: Version
    provider_type: ReasoningProviderType
    test_only: bool
    requires_network: bool
    uses_model: bool


class ProviderHealth(FrozenContract):
    status: ProviderHealthStatus
    code: Code


class AuthorizedToolCall(FrozenContract):
    tool_name: str = Field(min_length=1, max_length=128)
    tool_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    payload: dict[str, JsonValue]
    input_checksum: Checksum


class ToolExecutionResult(FrozenContract):
    status: ObservationStatus
    invocation: ResearchToolInvocationRecord
    observation: ResearchObservationRecord | None
    budget: RunBudget
    retryable: bool = False


class ConflictResult(FrozenContract):
    conflicting: bool
    reason_codes: tuple[Code, ...] = Field(max_length=100)
    evidence_ids: tuple[UUID, ...] = Field(max_length=100)


class PageRequest(FrozenContract):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10_000)


class Page[PageItemT](FrozenContract):
    items: tuple[PageItemT, ...]
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)


ResearchAgentRunView = ResearchAgentRunRecord
ResearchPlanView = ResearchPlanRecord
ResearchStepView = ResearchStepRecord
ResearchToolInvocationView = ResearchToolInvocationRecord


class ResearchEvidenceView(FrozenContract):
    """Bounded evidence metadata that deliberately excludes the payload body."""

    id: UUID
    run_id: UUID
    observation_id: UUID
    evidence_type: EvidenceType
    status: EvidenceStatus
    schema_version: Version
    security_id: UUID
    snapshot_id: UUID
    research_as_of_time: AwareUtcDateTime
    source_record_type: str | None = Field(default=None, max_length=128)
    source_record_id: UUID | None = None
    source_checksum: Checksum | None = None
    published_at: AwareUtcDateTime | None = None
    citation_id: UUID | None = None
    calculation_run_id: UUID | None = None
    calculation_input_ids: tuple[UUID, ...] = Field(default=(), max_length=100)
    formula_version: str | None = Field(default=None, max_length=128)
    synthetic_status: SyntheticStatus
    warning_codes: tuple[Code, ...] = Field(default=(), max_length=100)
    created_at: AwareUtcDateTime


ResearchClaimView = ResearchClaimRecord
ResearchPackageView = ResearchPackageRecord
ResearchRunEventView = ResearchRunEventRecord
