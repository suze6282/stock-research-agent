"""Immutable runtime report Reflection lifecycle contracts."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.enums import ReportSection
from stock_research_agent.domain.reports.markdown import DeterministicMarkdownRenderer
from stock_research_agent.domain.reports.reflection_policy import (
    ReflectionSeverity,
    RuntimeReflectionCheck,
    RuntimeReflectionPolicyRecord,
)
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
    ResearchReportAggregate,
    ResearchReportRecord,
    StructuredReportBlock,
)
from stock_research_agent.domain.reports.schemas import (
    AwareUtcDateTime,
    Checksum,
    Code,
    FrozenReportContract,
    ReportInputManifest,
    Version,
)
from stock_research_agent.domain.research_agent.enums import (
    ResearchMode,
    SyntheticStatus,
)

if TYPE_CHECKING:
    from stock_research_agent.domain.reports.revision import ReportRevisionResult


class ReportReflectionStatus(StrEnum):
    RUNNING = "RUNNING"
    PASS = "PASS"
    FINDINGS = "FINDINGS"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


TERMINAL_REFLECTION_STATUSES = frozenset(
    {
        ReportReflectionStatus.PASS,
        ReportReflectionStatus.FINDINGS,
        ReportReflectionStatus.BLOCKED,
        ReportReflectionStatus.FAILED,
    }
)


class ReflectionFindingCategory(StrEnum):
    BINDING = "BINDING"
    CONTEXT = "CONTEXT"
    TEMPORAL = "TEMPORAL"
    EVIDENCE = "EVIDENCE"
    DISCLOSURE = "DISCLOSURE"
    REFERENCE = "REFERENCE"
    CHECKSUM = "CHECKSUM"
    CONTENT_SAFETY = "CONTENT_SAFETY"
    DATA_QUALITY = "DATA_QUALITY"
    FORMAT = "FORMAT"
    VERSIONING = "VERSIONING"
    CAPABILITY = "CAPABILITY"


class ReportReflectionRunWrite(FrozenReportContract):
    id: UUID
    research_report_id: UUID
    reflection_policy_version: Version
    engine_name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    engine_version: Version
    round_number: int = Field(ge=1, le=2)
    input_report_checksum: Checksum
    status: Literal[ReportReflectionStatus.RUNNING]
    started_at: AwareUtcDateTime


class ReportReflectionRunRecord(FrozenReportContract):
    id: UUID
    research_report_id: UUID
    reflection_policy_version: Version
    engine_name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    engine_version: Version
    round_number: int = Field(ge=1, le=2)
    input_report_checksum: Checksum
    status: ReportReflectionStatus
    started_at: AwareUtcDateTime
    total_finding_count: int = Field(ge=0, le=10_000)
    critical_count: int = Field(ge=0, le=10_000)
    high_count: int = Field(ge=0, le=10_000)
    medium_count: int = Field(ge=0, le=10_000)
    low_count: int = Field(ge=0, le=10_000)
    blocked_reason_code: Code | None = None
    error_code: Code | None = None
    safe_error_message: str | None = Field(default=None, max_length=256)
    completed_at: AwareUtcDateTime | None = None

    @model_validator(mode="after")
    def require_consistent_state(self) -> Self:
        _validate_reflection_outcome(
            status=self.status,
            total=self.total_finding_count,
            critical=self.critical_count,
            high=self.high_count,
            medium=self.medium_count,
            low=self.low_count,
            blocked_reason=self.blocked_reason_code,
            error_code=self.error_code,
            safe_error_message=self.safe_error_message,
            completed_at=self.completed_at,
        )
        return self


class ReportReflectionCompletion(FrozenReportContract):
    target_status: ReportReflectionStatus
    total_finding_count: int = Field(ge=0, le=10_000)
    critical_count: int = Field(default=0, ge=0, le=10_000)
    high_count: int = Field(default=0, ge=0, le=10_000)
    medium_count: int = Field(default=0, ge=0, le=10_000)
    low_count: int = Field(default=0, ge=0, le=10_000)
    blocked_reason_code: Code | None = None
    error_code: Code | None = None
    safe_error_message: str | None = Field(default=None, max_length=256)
    completed_at: AwareUtcDateTime

    @model_validator(mode="after")
    def require_terminal_shape(self) -> Self:
        _validate_reflection_outcome(
            status=self.target_status,
            total=self.total_finding_count,
            critical=self.critical_count,
            high=self.high_count,
            medium=self.medium_count,
            low=self.low_count,
            blocked_reason=self.blocked_reason_code,
            error_code=self.error_code,
            safe_error_message=self.safe_error_message,
            completed_at=self.completed_at,
        )
        return self


class ReportReflectionFindingWrite(FrozenReportContract):
    id: UUID
    reflection_run_id: UUID
    research_report_id: UUID
    report_section_id: UUID | None = None
    report_block_id: UUID | None = None
    claim_id: UUID | None = None
    evidence_id: UUID | None = None
    citation_id: UUID | None = None
    finding_code: Code
    category: ReflectionFindingCategory
    severity: ReflectionSeverity
    description: str = Field(min_length=1, max_length=512)
    remediation_code: Code
    blocking: bool
    created_at: AwareUtcDateTime

    @field_validator("description")
    @classmethod
    def require_safe_description(cls, value: str) -> str:
        normalized = value.casefold()
        forbidden = (
            "password=",
            "secret=",
            "token=",
            "api_key",
            "select ",
            "insert ",
            "update ",
            "delete ",
            "drop ",
            "file://",
            "blob://",
            "traceback (most recent call last)",
            "<script",
            "</",
            "\u200b",
            "\ufeff",
        )
        if any(token in normalized for token in forbidden) or (
            len(value) >= 3 and value[1:3] == ":\\"
        ):
            raise ValueError("Reflection Finding description is unsafe")
        return value

    @model_validator(mode="after")
    def require_exact_links_and_threshold(self) -> Self:
        if self.report_block_id is not None and self.report_section_id is None:
            raise ValueError("Block-linked Finding requires its Section ID")
        expected_blocking = self.severity in {
            ReflectionSeverity.CRITICAL,
            ReflectionSeverity.HIGH,
        }
        if self.blocking is not expected_blocking:
            raise ValueError("Finding blocking flag must match HIGH threshold")
        return self


class ReportReflectionFindingRecord(ReportReflectionFindingWrite):
    report_section: ReportSection | None = None
    block_key: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_.-]{2,127}$",
    )


class ReportReflectionResult(FrozenReportContract):
    run: ReportReflectionRunRecord
    finding_ids: tuple[UUID, ...] = Field(max_length=10_000)
    findings: tuple[ReportReflectionFindingRecord, ...] = Field(
        default=(),
        max_length=10_000,
    )

    @model_validator(mode="after")
    def require_exact_finding_count(self) -> Self:
        if self.run.status not in TERMINAL_REFLECTION_STATUSES:
            raise ValueError("Reflection result requires a terminal run")
        if len(self.finding_ids) != self.run.total_finding_count:
            raise ValueError("Reflection result finding count mismatch")
        if len(self.finding_ids) != len(set(self.finding_ids)):
            raise ValueError("Reflection result finding IDs must be unique")
        if self.findings:
            finding_ids = tuple(item.id for item in self.findings)
            if finding_ids != self.finding_ids:
                raise ValueError("materialized Finding IDs must match result order")
            if any(
                item.reflection_run_id != self.run.id
                or item.research_report_id != self.run.research_report_id
                for item in self.findings
            ):
                raise ValueError("materialized Findings must match Reflection context")
        return self


class ReflectionSeverityCounts(FrozenReportContract):
    total: int = Field(ge=0, le=10_000)
    critical: int = Field(ge=0, le=10_000)
    high: int = Field(ge=0, le=10_000)
    medium: int = Field(ge=0, le=10_000)
    low: int = Field(ge=0, le=10_000)


def count_findings_by_severity(
    findings: tuple[ReportReflectionFindingWrite, ...],
) -> ReflectionSeverityCounts:
    counts = {severity: 0 for severity in ReflectionSeverity}
    for finding in findings:
        counts[finding.severity] += 1
    return ReflectionSeverityCounts(
        total=len(findings),
        critical=counts[ReflectionSeverity.CRITICAL],
        high=counts[ReflectionSeverity.HIGH],
        medium=counts[ReflectionSeverity.MEDIUM],
        low=counts[ReflectionSeverity.LOW],
    )


REFLECTION_ENGINE_NAME = "deterministic-report-reflection"
REFLECTION_ENGINE_VERSION = "deterministic-report-reflection-v1"


@dataclass(frozen=True, slots=True)
class ReflectionRule:
    check: RuntimeReflectionCheck
    minimum_severity: ReflectionSeverity
    category: ReflectionFindingCategory
    remediation_code: str


_MINIMUM_SEVERITIES = {
    RuntimeReflectionCheck.FACTUAL_BLOCK_HAS_CLAIM: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.PRIMARY_CLAIM_HAS_EVIDENCE: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.DOCUMENT_CLAIM_HAS_VALID_CITATION: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.STRUCTURED_CLAIM_HAS_LINEAGE: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.SECURITY_MATCHES: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.SNAPSHOT_MATCHES: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.AS_OF_MATCHES: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_FUTURE_EVIDENCE: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.STRICT_DOCUMENT_PUBLISHED_AT_KNOWN: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.NO_REAL_RESEARCH_SYNTHETIC_EVIDENCE: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_CROSS_SECURITY_RECORDS: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_CROSS_SNAPSHOT_RECORDS: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.CONFLICTING_CLAIMS_DISCLOSED: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.PARTIAL_SUPPORT_QUALIFIED: ReflectionSeverity.MEDIUM,
    RuntimeReflectionCheck.UNSUPPORTED_CLAIMS_RESTRICTED: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.BLOCKED_CAPABILITY_NOT_COMPLETED: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.DATA_QUALITY_PRESENT: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.LIMITATIONS_PRESENT: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.NO_ORPHAN_BODY_REFERENCE: ReflectionSeverity.MEDIUM,
    RuntimeReflectionCheck.NO_UNUSED_APPENDIX_REFERENCE: ReflectionSeverity.MEDIUM,
    RuntimeReflectionCheck.CITATION_VALID: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.CLAIM_SET_CHECKSUM_MATCHES: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.EVIDENCE_LINK_SET_CHECKSUMS_MATCH: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.PACKAGE_CHECKSUM_MATCHES: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_RATING_LANGUAGE: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_TARGET_PRICE: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_POSITION_ADVICE: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_TRADING_INSTRUCTION: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_UNSUPPORTED_OVERSTATEMENT: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.FIXTURE_NOT_DESCRIBED_AS_LIVE: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.SYNTHETIC_NOT_REAL_COMPANY_RESEARCH: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.EXCERPT_WITHIN_POLICY: ReflectionSeverity.MEDIUM,
    RuntimeReflectionCheck.UNIT_CURRENCY_MATCH: ReflectionSeverity.MEDIUM,
    RuntimeReflectionCheck.REPORT_AS_OF_PRESENT: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.SNAPSHOT_IDENTITY_PRESENT: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.NO_FALSE_MODEL_CALL_CLAIM: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.RETRIEVAL_CAPABILITY_HONEST: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.JSON_MARKDOWN_CHECKSUMS_MATCH: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.REPORT_STRUCTURE_VERSION_CHAIN_VALID: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.REPORT_INPUT_MANIFEST_UNCHANGED: ReflectionSeverity.CRITICAL,
}

_RULE_CATEGORIES = {
    RuntimeReflectionCheck.FACTUAL_BLOCK_HAS_CLAIM: ReflectionFindingCategory.BINDING,
    RuntimeReflectionCheck.PRIMARY_CLAIM_HAS_EVIDENCE: ReflectionFindingCategory.BINDING,
    RuntimeReflectionCheck.DOCUMENT_CLAIM_HAS_VALID_CITATION: (ReflectionFindingCategory.BINDING),
    RuntimeReflectionCheck.STRUCTURED_CLAIM_HAS_LINEAGE: ReflectionFindingCategory.BINDING,
    RuntimeReflectionCheck.SECURITY_MATCHES: ReflectionFindingCategory.CONTEXT,
    RuntimeReflectionCheck.SNAPSHOT_MATCHES: ReflectionFindingCategory.CONTEXT,
    RuntimeReflectionCheck.AS_OF_MATCHES: ReflectionFindingCategory.TEMPORAL,
    RuntimeReflectionCheck.NO_FUTURE_EVIDENCE: ReflectionFindingCategory.TEMPORAL,
    RuntimeReflectionCheck.STRICT_DOCUMENT_PUBLISHED_AT_KNOWN: (ReflectionFindingCategory.TEMPORAL),
    RuntimeReflectionCheck.NO_REAL_RESEARCH_SYNTHETIC_EVIDENCE: (
        ReflectionFindingCategory.EVIDENCE
    ),
    RuntimeReflectionCheck.NO_CROSS_SECURITY_RECORDS: ReflectionFindingCategory.CONTEXT,
    RuntimeReflectionCheck.NO_CROSS_SNAPSHOT_RECORDS: ReflectionFindingCategory.CONTEXT,
    RuntimeReflectionCheck.CONFLICTING_CLAIMS_DISCLOSED: (ReflectionFindingCategory.DISCLOSURE),
    RuntimeReflectionCheck.PARTIAL_SUPPORT_QUALIFIED: (ReflectionFindingCategory.DISCLOSURE),
    RuntimeReflectionCheck.UNSUPPORTED_CLAIMS_RESTRICTED: (ReflectionFindingCategory.DISCLOSURE),
    RuntimeReflectionCheck.BLOCKED_CAPABILITY_NOT_COMPLETED: (ReflectionFindingCategory.CAPABILITY),
    RuntimeReflectionCheck.DATA_QUALITY_PRESENT: ReflectionFindingCategory.DATA_QUALITY,
    RuntimeReflectionCheck.LIMITATIONS_PRESENT: ReflectionFindingCategory.DATA_QUALITY,
    RuntimeReflectionCheck.NO_ORPHAN_BODY_REFERENCE: ReflectionFindingCategory.REFERENCE,
    RuntimeReflectionCheck.NO_UNUSED_APPENDIX_REFERENCE: (ReflectionFindingCategory.REFERENCE),
    RuntimeReflectionCheck.CITATION_VALID: ReflectionFindingCategory.REFERENCE,
    RuntimeReflectionCheck.CLAIM_SET_CHECKSUM_MATCHES: ReflectionFindingCategory.CHECKSUM,
    RuntimeReflectionCheck.EVIDENCE_LINK_SET_CHECKSUMS_MATCH: (ReflectionFindingCategory.CHECKSUM),
    RuntimeReflectionCheck.PACKAGE_CHECKSUM_MATCHES: ReflectionFindingCategory.CHECKSUM,
    RuntimeReflectionCheck.NO_RATING_LANGUAGE: ReflectionFindingCategory.CONTENT_SAFETY,
    RuntimeReflectionCheck.NO_TARGET_PRICE: ReflectionFindingCategory.CONTENT_SAFETY,
    RuntimeReflectionCheck.NO_POSITION_ADVICE: ReflectionFindingCategory.CONTENT_SAFETY,
    RuntimeReflectionCheck.NO_TRADING_INSTRUCTION: (ReflectionFindingCategory.CONTENT_SAFETY),
    RuntimeReflectionCheck.NO_UNSUPPORTED_OVERSTATEMENT: (ReflectionFindingCategory.CONTENT_SAFETY),
    RuntimeReflectionCheck.FIXTURE_NOT_DESCRIBED_AS_LIVE: (ReflectionFindingCategory.DISCLOSURE),
    RuntimeReflectionCheck.SYNTHETIC_NOT_REAL_COMPANY_RESEARCH: (
        ReflectionFindingCategory.EVIDENCE
    ),
    RuntimeReflectionCheck.EXCERPT_WITHIN_POLICY: ReflectionFindingCategory.REFERENCE,
    RuntimeReflectionCheck.UNIT_CURRENCY_MATCH: ReflectionFindingCategory.FORMAT,
    RuntimeReflectionCheck.REPORT_AS_OF_PRESENT: ReflectionFindingCategory.CONTEXT,
    RuntimeReflectionCheck.SNAPSHOT_IDENTITY_PRESENT: ReflectionFindingCategory.CONTEXT,
    RuntimeReflectionCheck.NO_FALSE_MODEL_CALL_CLAIM: ReflectionFindingCategory.CAPABILITY,
    RuntimeReflectionCheck.RETRIEVAL_CAPABILITY_HONEST: (ReflectionFindingCategory.CAPABILITY),
    RuntimeReflectionCheck.JSON_MARKDOWN_CHECKSUMS_MATCH: (ReflectionFindingCategory.CHECKSUM),
    RuntimeReflectionCheck.REPORT_STRUCTURE_VERSION_CHAIN_VALID: (
        ReflectionFindingCategory.VERSIONING
    ),
    RuntimeReflectionCheck.REPORT_INPUT_MANIFEST_UNCHANGED: (ReflectionFindingCategory.CHECKSUM),
}

_REVISION_REMEDIATIONS = {
    RuntimeReflectionCheck.FACTUAL_BLOCK_HAS_CLAIM: "DELETE_UNBOUND_FACT_BLOCK",
    RuntimeReflectionCheck.PRIMARY_CLAIM_HAS_EVIDENCE: "DELETE_UNBOUND_FACT_BLOCK",
    RuntimeReflectionCheck.DOCUMENT_CLAIM_HAS_VALID_CITATION: ("REMOVE_INVALID_CITATION_BLOCK"),
    RuntimeReflectionCheck.STRUCTURED_CLAIM_HAS_LINEAGE: "DELETE_UNBOUND_FACT_BLOCK",
    RuntimeReflectionCheck.CONFLICTING_CLAIMS_DISCLOSED: "MOVE_CONFLICT_TO_CONFLICTS",
    RuntimeReflectionCheck.PARTIAL_SUPPORT_QUALIFIED: "DOWNGRADE_PARTIAL_LANGUAGE",
    RuntimeReflectionCheck.UNSUPPORTED_CLAIMS_RESTRICTED: ("MOVE_UNSUPPORTED_TO_APPENDIX"),
    RuntimeReflectionCheck.BLOCKED_CAPABILITY_NOT_COMPLETED: ("MOVE_BLOCKED_TO_LIMITATIONS"),
    RuntimeReflectionCheck.DATA_QUALITY_PRESENT: ("ADD_DATA_QUALITY_FROM_EXISTING_STATE"),
    RuntimeReflectionCheck.LIMITATIONS_PRESENT: ("ADD_LIMITATIONS_FROM_EXISTING_STATE"),
    RuntimeReflectionCheck.NO_ORPHAN_BODY_REFERENCE: "RENUMBER_EXISTING_REFERENCES",
    RuntimeReflectionCheck.NO_UNUSED_APPENDIX_REFERENCE: ("RENUMBER_EXISTING_REFERENCES"),
    RuntimeReflectionCheck.CITATION_VALID: "REMOVE_INVALID_CITATION_BLOCK",
    RuntimeReflectionCheck.NO_RATING_LANGUAGE: "REMOVE_FORBIDDEN_ADVICE_TEXT",
    RuntimeReflectionCheck.NO_TARGET_PRICE: "REMOVE_FORBIDDEN_ADVICE_TEXT",
    RuntimeReflectionCheck.NO_POSITION_ADVICE: "REMOVE_FORBIDDEN_ADVICE_TEXT",
    RuntimeReflectionCheck.NO_TRADING_INSTRUCTION: "REMOVE_FORBIDDEN_ADVICE_TEXT",
    RuntimeReflectionCheck.NO_UNSUPPORTED_OVERSTATEMENT: ("REMOVE_FORBIDDEN_ADVICE_TEXT"),
    RuntimeReflectionCheck.EXCERPT_WITHIN_POLICY: "TRUNCATE_EXISTING_EXCERPT",
    RuntimeReflectionCheck.NO_FALSE_MODEL_CALL_CLAIM: ("REMOVE_FORBIDDEN_ADVICE_TEXT"),
    RuntimeReflectionCheck.JSON_MARKDOWN_CHECKSUMS_MATCH: "FIX_DETERMINISTIC_FORMAT",
}

REFLECTION_RULES = tuple(
    ReflectionRule(
        check=check,
        minimum_severity=_MINIMUM_SEVERITIES[check],
        category=_RULE_CATEGORIES[check],
        remediation_code=_REVISION_REMEDIATIONS.get(
            check,
            f"REMEDIATE_{check.value}",
        ),
    )
    for check in RuntimeReflectionCheck
)


class CandidateReflectionFinding(FrozenReportContract):
    finding_code: RuntimeReflectionCheck
    category: ReflectionFindingCategory
    severity: ReflectionSeverity
    description: str = Field(min_length=1, max_length=512)
    remediation_code: Code
    blocking: bool
    report_section: ReportSection | None = None
    block_key: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_.-]{2,127}$",
    )
    claim_id: UUID | None = None
    evidence_id: UUID | None = None
    citation_id: UUID | None = None

    @model_validator(mode="after")
    def require_minimum_blocking_threshold(self) -> Self:
        expected = self.severity in {
            ReflectionSeverity.CRITICAL,
            ReflectionSeverity.HIGH,
        }
        if self.blocking is not expected:
            raise ValueError("candidate Finding blocking flag is inconsistent")
        return self


class ReportReflectionDraft(FrozenReportContract):
    research_report_id: UUID
    engine_name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    engine_version: Version
    round_number: int = Field(ge=1, le=2)
    input_report_checksum: Checksum
    status: Literal[ReportReflectionStatus.PASS, ReportReflectionStatus.FINDINGS]
    findings: tuple[CandidateReflectionFinding, ...] = Field(max_length=10_000)
    severity_counts: ReflectionSeverityCounts

    @model_validator(mode="after")
    def require_exact_result_shape(self) -> Self:
        if self.severity_counts.total != len(self.findings):
            raise ValueError("Reflection draft count mismatch")
        if self.status is ReportReflectionStatus.PASS and self.findings:
            raise ValueError("PASS Reflection draft cannot contain findings")
        if self.status is ReportReflectionStatus.FINDINGS and not self.findings:
            raise ValueError("FINDINGS Reflection draft requires findings")
        return self


class ReportReflectionEngineError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class _BlockContext:
    section: ReportSection
    section_index: int
    block: StructuredReportBlock


class DeterministicReportReflectionEngine:
    def reflect(
        self,
        report: ResearchReportAggregate,
        manifest: ReportInputManifest,
        policy: RuntimeReflectionPolicyRecord,
        round_number: int,
    ) -> ReportReflectionDraft:
        if round_number not in {1, 2} or round_number > policy.max_reflection_rounds:
            raise ReportReflectionEngineError("REPORT_REFLECTION_ROUND_INVALID")
        if policy.required_checks != tuple(rule.check for rule in REFLECTION_RULES):
            raise ReportReflectionEngineError("REPORT_REFLECTION_POLICY_CHECKS_INVALID")
        if policy.allow_model_reflection:
            raise ReportReflectionEngineError("MODEL_REFLECTION_FORBIDDEN")

        contexts = _block_contexts(report)
        findings = tuple(
            finding
            for rule in REFLECTION_RULES
            for finding in _evaluate_rule(rule, report, manifest, contexts)
        )
        counts = _candidate_counts(findings)
        return ReportReflectionDraft(
            research_report_id=report.report.id,
            engine_name=REFLECTION_ENGINE_NAME,
            engine_version=REFLECTION_ENGINE_VERSION,
            round_number=round_number,
            input_report_checksum=report.report.content_checksum,
            status=(
                ReportReflectionStatus.PASS if not findings else ReportReflectionStatus.FINDINGS
            ),
            findings=findings,
            severity_counts=counts,
        )


def _block_contexts(report: ResearchReportAggregate) -> tuple[_BlockContext, ...]:
    return tuple(
        _BlockContext(section.section, section.section_index, block)
        for section in report.report.structured_content.sections
        for block in section.blocks
    )


def _evaluate_rule(
    rule: ReflectionRule,
    aggregate: ResearchReportAggregate,
    manifest: ReportInputManifest,
    contexts: tuple[_BlockContext, ...],
) -> tuple[CandidateReflectionFinding, ...]:
    report = aggregate.report
    check = rule.check
    body = tuple(item for item in contexts if not _is_appendix(item.section))
    factual = tuple(item for item in body if _is_factual(item))

    if check is RuntimeReflectionCheck.FACTUAL_BLOCK_HAS_CLAIM:
        return _for_contexts(
            rule,
            (item for item in factual if not _payload_uuid(item, "claim_id")),
        )
    if check is RuntimeReflectionCheck.PRIMARY_CLAIM_HAS_EVIDENCE:
        return _for_contexts(
            rule,
            (
                item
                for item in factual
                if _support(item) in {"SUPPORTED", "PARTIALLY_SUPPORTED", "CONFLICTING"}
                and not _payload_ids(item, "evidence_ids")
            ),
        )
    if check is RuntimeReflectionCheck.DOCUMENT_CLAIM_HAS_VALID_CITATION:
        return _for_contexts(
            rule,
            (
                item
                for item in factual
                if _is_document_section(item.section) and not _has_valid_citation(item)
            ),
        )
    if check is RuntimeReflectionCheck.STRUCTURED_CLAIM_HAS_LINEAGE:
        return _for_contexts(
            rule,
            (
                item
                for item in factual
                if not _is_document_section(item.section)
                and not (_payload_ids(item, "link_ids") or _payload_ids(item, "lineage_ids"))
            ),
        )
    if check is RuntimeReflectionCheck.SECURITY_MATCHES:
        return _global_if(rule, report.security_id != manifest.security_id)
    if check is RuntimeReflectionCheck.SNAPSHOT_MATCHES:
        return _global_if(rule, report.snapshot_id != manifest.snapshot_id)
    if check is RuntimeReflectionCheck.AS_OF_MATCHES:
        return _global_if(rule, report.research_as_of_time != manifest.research_as_of_time)
    if check is RuntimeReflectionCheck.NO_FUTURE_EVIDENCE:
        return _for_contexts(
            rule,
            (
                item
                for item in body
                if any(
                    timestamp > manifest.research_as_of_time
                    for timestamp in _payload_timestamps(item)
                )
            ),
        )
    if check is RuntimeReflectionCheck.STRICT_DOCUMENT_PUBLISHED_AT_KNOWN:
        return _for_contexts(
            rule,
            (
                item
                for item in factual
                if _is_document_section(item.section) and _published_at(item) is None
            ),
        )
    if check is RuntimeReflectionCheck.NO_REAL_RESEARCH_SYNTHETIC_EVIDENCE:
        contaminated = (
            manifest.research_mode is ResearchMode.REAL_RESEARCH
            and manifest.synthetic_status
            not in {
                SyntheticStatus.REAL_VERIFIED,
                SyntheticStatus.FIXTURE_REAL_EXCERPT,
            }
        ) or any(_payload_is_synthetic(item) for item in factual)
        return _global_if(rule, contaminated)
    if check is RuntimeReflectionCheck.NO_CROSS_SECURITY_RECORDS:
        return _for_contexts(
            rule,
            (
                item
                for item in body
                if _payload_context_mismatch(item, "security_id", report.security_id)
            ),
        )
    if check is RuntimeReflectionCheck.NO_CROSS_SNAPSHOT_RECORDS:
        return _for_contexts(
            rule,
            (
                item
                for item in body
                if _payload_context_mismatch(item, "snapshot_id", report.snapshot_id)
            ),
        )
    if check is RuntimeReflectionCheck.CONFLICTING_CLAIMS_DISCLOSED:
        return _for_contexts(
            rule,
            (
                item
                for item in factual
                if _support(item) == "CONFLICTING" and item.section is not ReportSection.CONFLICTS
            ),
        )
    if check is RuntimeReflectionCheck.PARTIAL_SUPPORT_QUALIFIED:
        return _for_contexts(
            rule,
            (
                item
                for item in factual
                if _support(item) == "PARTIALLY_SUPPORTED"
                and not _has_partial_qualifier(item.block.text or "")
            ),
        )
    if check is RuntimeReflectionCheck.UNSUPPORTED_CLAIMS_RESTRICTED:
        return _for_contexts(
            rule,
            (
                item
                for item in factual
                if _support(item) == "UNSUPPORTED"
                and item.section
                not in {
                    ReportSection.UNSUPPORTED_CLAIMS,
                    ReportSection.LIMITATIONS,
                }
            ),
        )
    if check is RuntimeReflectionCheck.BLOCKED_CAPABILITY_NOT_COMPLETED:
        return _for_contexts(
            rule,
            (item for item in body if _claims_blocked_capability_completed(item, manifest)),
        )
    if check is RuntimeReflectionCheck.DATA_QUALITY_PRESENT:
        return _global_if(rule, not _section_present(contexts, ReportSection.DATA_QUALITY))
    if check is RuntimeReflectionCheck.LIMITATIONS_PRESENT:
        return _global_if(rule, not _section_present(contexts, ReportSection.LIMITATIONS))
    if check is RuntimeReflectionCheck.NO_ORPHAN_BODY_REFERENCE:
        body_labels = _body_reference_labels(body)
        appendix_labels = _appendix_reference_labels(contexts)
        return _global_if(rule, bool(body_labels - appendix_labels))
    if check is RuntimeReflectionCheck.NO_UNUSED_APPENDIX_REFERENCE:
        body_labels = _body_reference_labels(body)
        appendix_labels = _appendix_reference_labels(contexts)
        return _global_if(rule, bool(appendix_labels - body_labels))
    if check is RuntimeReflectionCheck.CITATION_VALID:
        return _for_contexts(
            rule,
            (
                item
                for item in contexts
                if any(row.get("citation_status") != "VALID" for row in _citation_rows(item))
            ),
        )
    if check is RuntimeReflectionCheck.CLAIM_SET_CHECKSUM_MATCHES:
        return _global_if(rule, report.claim_set_checksum != manifest.claims_checksum)
    if check is RuntimeReflectionCheck.EVIDENCE_LINK_SET_CHECKSUMS_MATCH:
        return _global_if(
            rule,
            report.evidence_set_checksum != manifest.evidence_checksum
            or report.link_set_checksum != manifest.links_checksum,
        )
    if check is RuntimeReflectionCheck.PACKAGE_CHECKSUM_MATCHES:
        return _global_if(rule, report.package_checksum != manifest.package_checksum)
    if check in _LANGUAGE_PATTERNS:
        return _for_contexts(
            rule,
            (
                item
                for item in body
                if _matches_language_rule(item.block.text, _LANGUAGE_PATTERNS[check])
            ),
        )
    if check is RuntimeReflectionCheck.FIXTURE_NOT_DESCRIBED_AS_LIVE:
        return _global_if(
            rule,
            manifest.synthetic_status is SyntheticStatus.FIXTURE_REAL_EXCERPT
            and _describes_live(body),
        )
    if check is RuntimeReflectionCheck.SYNTHETIC_NOT_REAL_COMPANY_RESEARCH:
        synthetic = (
            manifest.research_mode is ResearchMode.SYNTHETIC_TEST_ONLY
            or manifest.synthetic_status is SyntheticStatus.SYNTHETIC_TEST_ONLY
        )
        return _global_if(
            rule,
            synthetic and not _has_all_synthetic_markers(body),
        )
    if check is RuntimeReflectionCheck.EXCERPT_WITHIN_POLICY:
        return _for_contexts(
            rule,
            (
                item
                for item in contexts
                if any(
                    len(str(row.get("rendered_excerpt", ""))) > 1000 for row in _citation_rows(item)
                )
            ),
        )
    if check is RuntimeReflectionCheck.UNIT_CURRENCY_MATCH:
        return _for_contexts(
            rule,
            (item for item in factual if _unit_currency_mismatch(item)),
        )
    if check is RuntimeReflectionCheck.REPORT_AS_OF_PRESENT:
        return _global_if(rule, report.research_as_of_time is None)
    if check is RuntimeReflectionCheck.SNAPSHOT_IDENTITY_PRESENT:
        return _global_if(rule, report.snapshot_id.int == 0)
    if check is RuntimeReflectionCheck.RETRIEVAL_CAPABILITY_HONEST:
        blocked = any(
            "VECTOR" in code or "HYBRID" in code
            for code in (*manifest.blocked_capabilities, *manifest.warnings)
        )
        return _global_if(rule, blocked and _claims_full_semantic_retrieval(body))
    if check is RuntimeReflectionCheck.JSON_MARKDOWN_CHECKSUMS_MATCH:
        return _global_if(rule, not _projection_matches(report))
    if check is RuntimeReflectionCheck.REPORT_STRUCTURE_VERSION_CHAIN_VALID:
        valid_chain = (report.report_version == 1 and report.previous_report_id is None) or (
            report.report_version > 1 and report.previous_report_id is not None
        )
        valid_structure = (
            report.structured_content.schema_version == "research-report-v1"
            and report.structured_content.locale is report.report_locale
        )
        return _global_if(rule, not valid_chain or not valid_structure)
    if check is RuntimeReflectionCheck.REPORT_INPUT_MANIFEST_UNCHANGED:
        return _global_if(
            rule,
            report.input_manifest_checksum != manifest.canonical_payload_checksum
            or report.research_package_id != manifest.research_package_id,
        )
    raise ReportReflectionEngineError(f"REPORT_REFLECTION_RULE_UNIMPLEMENTED:{check.value}")


_APPENDIX_SECTIONS = frozenset(
    {
        ReportSection.CLAIM_INDEX,
        ReportSection.EVIDENCE_APPENDIX,
        ReportSection.CITATION_APPENDIX,
    }
)
_DOCUMENT_SECTIONS = frozenset(
    {
        ReportSection.DOCUMENT_EVIDENCE,
        ReportSection.CATALYST_EVIDENCE,
        ReportSection.RISK_EVIDENCE,
        ReportSection.CORPORATE_ACTIONS,
    }
)
_LANGUAGE_PATTERNS = {
    RuntimeReflectionCheck.NO_RATING_LANGUAGE: (
        re.compile(
            r"\b(?:strong buy|rating|outperform|underperform|overweight|underweight)\b"
            r"|评级|增持|减持|跑赢|跑输",
            re.IGNORECASE,
        ),
    ),
    RuntimeReflectionCheck.NO_TARGET_PRICE: (
        re.compile(r"\b(?:target price|price target)\b|目标价", re.IGNORECASE),
    ),
    RuntimeReflectionCheck.NO_POSITION_ADVICE: (
        re.compile(
            r"\b(?:position size|portfolio allocation|allocate \d+(?:\.\d+)?%)\b"
            r"|仓位|配置比例",
            re.IGNORECASE,
        ),
    ),
    RuntimeReflectionCheck.NO_TRADING_INSTRUCTION: (
        re.compile(r"\b(?:buy|sell|hold) (?:the |these )?(?:share|stock)", re.IGNORECASE),
        re.compile(r"\b(?:buy|sell) now\b|立即买入|立即卖出|买入该股|卖出该股", re.IGNORECASE),
    ),
    RuntimeReflectionCheck.NO_UNSUPPORTED_OVERSTATEMENT: (
        re.compile(
            r"\b(?:will definitely|guaranteed|without doubt|certain to)\b"
            r"|一定会|必然会|毫无疑问|保证收益",
            re.IGNORECASE,
        ),
    ),
    RuntimeReflectionCheck.NO_FALSE_MODEL_CALL_CLAIM: (
        re.compile(
            r"\b(?:generated|analyzed|written) by (?:an? )?"
            r"(?:(?:openai|ai|language) )?model\b"
            r"|由大模型生成|模型分析得出|AI生成",
            re.IGNORECASE,
        ),
    ),
}
_REFERENCE_PATTERN = re.compile(r"^(?:CIT|EV|MET|LIM|CON)-[0-9]{3}$")
_BRACKETED_REFERENCE_PATTERN = re.compile(r"\[((?:CIT|EV|MET|LIM|CON)-[0-9]{3})\]")


def _candidate_counts(
    findings: tuple[CandidateReflectionFinding, ...],
) -> ReflectionSeverityCounts:
    counts = {severity: 0 for severity in ReflectionSeverity}
    for finding in findings:
        counts[finding.severity] += 1
    return ReflectionSeverityCounts(
        total=len(findings),
        critical=counts[ReflectionSeverity.CRITICAL],
        high=counts[ReflectionSeverity.HIGH],
        medium=counts[ReflectionSeverity.MEDIUM],
        low=counts[ReflectionSeverity.LOW],
    )


def _for_contexts(
    rule: ReflectionRule,
    contexts: Iterable[_BlockContext],
) -> tuple[CandidateReflectionFinding, ...]:
    return tuple(_finding(rule, item) for item in contexts)


def _global_if(
    rule: ReflectionRule,
    condition: bool,
) -> tuple[CandidateReflectionFinding, ...]:
    return (_finding(rule),) if condition else ()


def _finding(
    rule: ReflectionRule,
    context: _BlockContext | None = None,
) -> CandidateReflectionFinding:
    return CandidateReflectionFinding(
        finding_code=rule.check,
        category=rule.category,
        severity=rule.minimum_severity,
        description=f"{rule.check.value} validation failed.",
        remediation_code=rule.remediation_code,
        blocking=rule.minimum_severity in {ReflectionSeverity.CRITICAL, ReflectionSeverity.HIGH},
        report_section=None if context is None else context.section,
        block_key=None if context is None else context.block.block_key,
        claim_id=None if context is None else _payload_uuid(context, "claim_id"),
        evidence_id=None if context is None else _first_payload_uuid(context, "evidence_ids"),
        citation_id=None if context is None else _first_payload_uuid(context, "citation_ids"),
    )


def _is_appendix(section: ReportSection) -> bool:
    return section in _APPENDIX_SECTIONS


def _is_document_section(section: ReportSection) -> bool:
    return section in _DOCUMENT_SECTIONS


def _is_factual(context: _BlockContext) -> bool:
    if _is_appendix(context.section):
        return False
    payload = context.block.payload
    return context.block.block_type in {
        ReportBlockType.METRIC_TABLE,
        ReportBlockType.CONFLICT,
    } or any(key in payload for key in ("claim_id", "statement_code", "support_status"))


def _support(context: _BlockContext) -> str | None:
    value = context.block.payload.get("support_status")
    return value if isinstance(value, str) else None


def _payload_uuid(context: _BlockContext, key: str) -> UUID | None:
    value = context.block.payload.get(key)
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _payload_ids(context: _BlockContext, key: str) -> tuple[UUID, ...]:
    value = context.block.payload.get(key)
    if not isinstance(value, list):
        return ()
    parsed: list[UUID] = []
    for item in value:
        if not isinstance(item, str):
            continue
        try:
            parsed.append(UUID(item))
        except ValueError:
            continue
    return tuple(parsed)


def _first_payload_uuid(context: _BlockContext, key: str) -> UUID | None:
    values = _payload_ids(context, key)
    return values[0] if values else None


def _has_valid_citation(context: _BlockContext) -> bool:
    payload = context.block.payload
    if payload.get("citation_status") != "VALID":
        return False
    citation_id = payload.get("citation_id")
    if isinstance(citation_id, str):
        try:
            UUID(citation_id)
            return True
        except ValueError:
            return False
    return bool(_payload_ids(context, "citation_ids"))


def _payload_timestamps(context: _BlockContext) -> tuple[datetime, ...]:
    return tuple(
        parsed
        for key in ("source_published_at", "published_at", "as_of_time")
        if (parsed := _parse_timestamp(context.block.payload.get(key))) is not None
    )


def _published_at(context: _BlockContext) -> datetime | None:
    return _parse_timestamp(
        context.block.payload.get(
            "source_published_at",
            context.block.payload.get("published_at"),
        )
    )


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _payload_is_synthetic(context: _BlockContext) -> bool:
    value = context.block.payload.get("synthetic_status")
    return value in {
        SyntheticStatus.SYNTHETIC_TEST_ONLY.value,
        SyntheticStatus.UNKNOWN.value,
    }


def _payload_context_mismatch(
    context: _BlockContext,
    key: str,
    expected: UUID,
) -> bool:
    value = context.block.payload.get(key)
    if value is None:
        return False
    if not isinstance(value, str):
        return True
    try:
        return UUID(value) != expected
    except ValueError:
        return True


def _has_partial_qualifier(text: str) -> bool:
    normalized = text.casefold()
    return any(
        marker in normalized
        for marker in (
            "limited by",
            "partial",
            "based on available",
            "verified evidence only",
            "受数据可用性限制",
            "部分支持",
            "仅反映已验证证据",
        )
    )


def _claims_blocked_capability_completed(
    context: _BlockContext,
    manifest: ReportInputManifest,
) -> bool:
    capability = context.block.payload.get("capability_code")
    if not isinstance(capability, str) or capability not in manifest.blocked_capabilities:
        return False
    text = (context.block.text or "").casefold()
    return context.block.status is ReportBlockStatus.COMPLETE or any(
        token in text for token in ("completed", "passed", "available", "已完成", "已通过", "可用")
    )


def _section_present(
    contexts: tuple[_BlockContext, ...],
    section: ReportSection,
) -> bool:
    return any(item.section is section for item in contexts)


def _body_reference_labels(
    contexts: tuple[_BlockContext, ...],
) -> set[str]:
    labels: set[str] = set()
    for context in contexts:
        reference = context.block.payload.get("reference")
        if isinstance(reference, str):
            labels.update(_BRACKETED_REFERENCE_PATTERN.findall(reference))
        targets = context.block.payload.get("reference_targets")
        labels.update(_labels_from_value(targets))
    return labels


def _appendix_reference_labels(
    contexts: tuple[_BlockContext, ...],
) -> set[str]:
    labels: set[str] = set()
    for context in contexts:
        if _is_appendix(context.section):
            labels.update(_labels_from_value(context.block.payload))
    return labels


def _labels_from_value(value: object) -> set[str]:
    if isinstance(value, dict):
        labels = {
            item
            for key, item in value.items()
            if key in {"label", "reference", "visible_reference"}
            and isinstance(item, str)
            and _REFERENCE_PATTERN.fullmatch(item)
        }
        for item in value.values():
            labels.update(_labels_from_value(item))
        return labels
    if isinstance(value, list):
        list_labels: set[str] = set()
        for item in value:
            list_labels.update(_labels_from_value(item))
        return list_labels
    return set()


def _citation_rows(context: _BlockContext) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if "citation_id" in value or "citation_status" in value:
                rows.append(value)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(context.block.payload)
    return tuple(rows)


def _matches_language_rule(
    text: str | None,
    patterns: tuple[re.Pattern[str], ...],
) -> bool:
    return text is not None and any(pattern.search(text) for pattern in patterns)


def _describes_live(contexts: tuple[_BlockContext, ...]) -> bool:
    text = " ".join(item.block.text or "" for item in contexts).casefold()
    if any(marker in text for marker in ("not live", "not_live", "offline", "非实时")):
        return False
    return any(
        marker in text
        for marker in (
            "live data",
            "live market data",
            "real-time",
            "realtime",
            "实时数据",
            "实时行情",
        )
    )


def _has_all_synthetic_markers(contexts: tuple[_BlockContext, ...]) -> bool:
    text = " ".join(item.block.text or "" for item in contexts).upper()
    return all(
        marker in text
        for marker in (
            "SYNTHETIC_TEST_ONLY",
            "NOT_COMPANY_EVIDENCE",
            "OFFLINE",
            "NOT_LIVE",
        )
    )


def _unit_currency_mismatch(context: _BlockContext) -> bool:
    unit = context.block.payload.get("unit")
    currency = context.block.payload.get("currency_code")
    return (
        isinstance(unit, str)
        and isinstance(currency, str)
        and unit in {"CNY", "USD"}
        and currency in {"CNY", "USD"}
        and unit != currency
    )


def _claims_full_semantic_retrieval(
    contexts: tuple[_BlockContext, ...],
) -> bool:
    text = " ".join(item.block.text or "" for item in contexts).casefold()
    return any(
        marker in text
        for marker in (
            "full semantic",
            "complete vector retrieval",
            "full hybrid retrieval",
            "完整语义检索",
            "完整向量检索",
        )
    )


def _projection_matches(report: ResearchReportRecord) -> bool:
    structured_content = report.structured_content
    markdown_content = report.markdown_content
    rendered = DeterministicMarkdownRenderer().render(structured_content)
    return (
        report_checksum(structured_content) == report.structured_checksum
        and report_checksum(markdown_content) == report.markdown_checksum
        and rendered.markdown_content == markdown_content
        and rendered.markdown_checksum == report.markdown_checksum
    )


class ReportReflectionTransitionError(RuntimeError):
    pass


class ReportReflectionStateMachine:
    def transition(
        self,
        current: ReportReflectionStatus,
        target: ReportReflectionStatus,
    ) -> ReportReflectionStatus:
        if (
            current is not ReportReflectionStatus.RUNNING
            or target not in TERMINAL_REFLECTION_STATUSES
        ):
            raise ReportReflectionTransitionError(
                f"REPORT_REFLECTION_TRANSITION_FORBIDDEN:{current.value}:{target.value}"
            )
        return target


def validate_reflection_predecessor(
    report: ResearchReportAggregate,
    round_number: int,
    prior: ReportReflectionResult,
    revision: ReportRevisionResult | None,
) -> None:
    from stock_research_agent.domain.reports.revision import (
        ReportRevisionStatus,
    )

    if (
        round_number != 2
        or prior.run.round_number != 1
        or prior.run.status
        not in {
            ReportReflectionStatus.PASS,
            ReportReflectionStatus.FINDINGS,
        }
    ):
        raise ReportReflectionTransitionError("REPORT_REFLECTION_PREDECESSOR_INVALID")
    if revision is None:
        if (
            prior.run.status is not ReportReflectionStatus.PASS
            or report.report.id != prior.run.research_report_id
            or report.report.content_checksum != prior.run.input_report_checksum
        ):
            raise ReportReflectionTransitionError("REPORT_REFLECTION_PREDECESSOR_INVALID")
        return
    run = revision.run
    if (
        prior.run.status is not ReportReflectionStatus.FINDINGS
        or run.status
        not in {
            ReportRevisionStatus.COMPLETED,
            ReportRevisionStatus.PARTIAL,
        }
        or run.source_report_id != prior.run.research_report_id
        or run.source_reflection_run_id != prior.run.id
        or run.target_report_id != report.report.id
        or report.report.previous_report_id != run.source_report_id
        or report.report.id == run.source_report_id
    ):
        raise ReportReflectionTransitionError("REPORT_REFLECTION_PREDECESSOR_INVALID")


def complete_reflection_run(
    run: ReportReflectionRunRecord,
    completion: ReportReflectionCompletion,
) -> ReportReflectionRunRecord:
    target = ReportReflectionStateMachine().transition(
        run.status,
        completion.target_status,
    )
    return ReportReflectionRunRecord.model_validate(
        {
            **run.model_dump(
                mode="python",
                exclude={
                    "status",
                    "total_finding_count",
                    "critical_count",
                    "high_count",
                    "medium_count",
                    "low_count",
                    "blocked_reason_code",
                    "error_code",
                    "safe_error_message",
                    "completed_at",
                },
            ),
            **completion.model_dump(mode="python", exclude={"target_status"}),
            "status": target,
        }
    )


def reflection_run_uniqueness_key(
    run: ReportReflectionRunWrite | ReportReflectionRunRecord,
) -> tuple[UUID, str, int]:
    return (
        run.research_report_id,
        run.reflection_policy_version,
        run.round_number,
    )


def _validate_reflection_outcome(
    *,
    status: ReportReflectionStatus,
    total: int,
    critical: int,
    high: int,
    medium: int,
    low: int,
    blocked_reason: str | None,
    error_code: str | None,
    safe_error_message: str | None,
    completed_at: object | None,
) -> None:
    if total != critical + high + medium + low:
        raise ValueError("Reflection severity counts must sum to total")
    if status is ReportReflectionStatus.RUNNING:
        if (
            total != 0
            or blocked_reason is not None
            or error_code is not None
            or safe_error_message is not None
            or completed_at is not None
        ):
            raise ValueError("RUNNING Reflection cannot contain terminal outcome")
        return
    if status not in TERMINAL_REFLECTION_STATUSES or completed_at is None:
        raise ValueError("Reflection outcome must be a completed terminal state")
    if status is ReportReflectionStatus.PASS and total != 0:
        raise ValueError("PASS Reflection cannot contain findings")
    if status is ReportReflectionStatus.FINDINGS and total == 0:
        raise ValueError("FINDINGS Reflection requires findings")
    if status is ReportReflectionStatus.BLOCKED and blocked_reason is None:
        raise ValueError("BLOCKED Reflection requires a reason")
    if status is ReportReflectionStatus.FAILED:
        if error_code is None or safe_error_message is None:
            raise ValueError("FAILED Reflection requires a safe error")
    elif error_code is not None or safe_error_message is not None:
        raise ValueError("Non-failed Reflection cannot contain an error")
