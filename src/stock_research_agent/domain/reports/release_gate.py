"""Deterministic internal release gate for immutable research reports."""

from __future__ import annotations

from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field

from stock_research_agent.domain.reports.checksums import (
    ReportChecksumContext,
    ReportProjectionChecksums,
    verify_report_projection,
)
from stock_research_agent.domain.reports.enums import ReportSection, ReportType
from stock_research_agent.domain.reports.markdown import (
    MARKDOWN_RENDERER_VERSION,
    DeterministicMarkdownRenderer,
)
from stock_research_agent.domain.reports.references import ReportReferenceAllocator
from stock_research_agent.domain.reports.reflection import (
    ReportReflectionResult,
    ReportReflectionStatus,
)
from stock_research_agent.domain.reports.reflection_policy import (
    RuntimeReflectionCheck,
)
from stock_research_agent.domain.reports.reporting import (
    ResearchReportAggregate,
    ResearchReportStatus,
)
from stock_research_agent.domain.reports.revision import rebase_report_bindings
from stock_research_agent.domain.reports.schemas import (
    AwareUtcDateTime,
    Checksum,
    Code,
    FrozenReportContract,
    ReportInputManifest,
    ReportPolicyRecord,
    Version,
)
from stock_research_agent.domain.reports.versioning import (
    validate_report_successor,
)
from stock_research_agent.domain.research_agent.enums import (
    ResearchMode,
    ResearchPackageStatus,
    SyntheticStatus,
)

RELEASE_GATE_VERSION = "report-release-gate-v1"


class ReleaseGateDecision(StrEnum):
    PUBLISHABLE = "PUBLISHABLE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class ReleaseGateRequirement(StrEnum):
    REPORT_CHECKSUMS_VALID = "REPORT_CHECKSUMS_VALID"
    PACKAGE_INPUT_CHECKSUMS_VALID = "PACKAGE_INPUT_CHECKSUMS_VALID"
    ROUND_TWO_COMPLETED = "ROUND_TWO_COMPLETED"
    NO_CRITICAL_FINDINGS = "NO_CRITICAL_FINDINGS"
    NO_HIGH_FINDINGS = "NO_HIGH_FINDINGS"
    NO_UNSUPPORTED_FACTUAL_BODY_CLAIMS = "NO_UNSUPPORTED_FACTUAL_BODY_CLAIMS"
    CONFLICTS_DISCLOSED = "CONFLICTS_DISCLOSED"
    DOCUMENT_CITATIONS_VALID = "DOCUMENT_CITATIONS_VALID"
    STRUCTURED_LINEAGE_VALID = "STRUCTURED_LINEAGE_VALID"
    TEMPORAL_EVIDENCE_VALID = "TEMPORAL_EVIDENCE_VALID"
    NO_SYNTHETIC_CONTAMINATION = "NO_SYNTHETIC_CONTAMINATION"
    CONTEXT_MATCHES = "CONTEXT_MATCHES"
    NO_FORBIDDEN_ADVICE = "NO_FORBIDDEN_ADVICE"
    DATA_QUALITY_PRESENT = "DATA_QUALITY_PRESENT"
    LIMITATIONS_PRESENT = "LIMITATIONS_PRESENT"
    PACKAGE_ELIGIBLE = "PACKAGE_ELIGIBLE"
    REPORT_TYPE_COMPATIBLE = "REPORT_TYPE_COMPATIBLE"
    PROJECTION_MATCHES = "PROJECTION_MATCHES"


class ReleaseGateRequirementResult(FrozenReportContract):
    requirement: ReleaseGateRequirement
    passed: bool


class ReportReleaseDecisionResult(FrozenReportContract):
    candidate_report_id: UUID
    round_two_reflection_run_id: UUID
    gate_version: Version
    input_manifest_checksum: Checksum
    report_checksum: Checksum
    internal_release_status: ReleaseGateDecision
    requirements: tuple[ReleaseGateRequirementResult, ...] = Field(
        min_length=18,
        max_length=18,
    )
    reason_codes: tuple[Code, ...] = Field(max_length=100)
    sealed_report: ResearchReportAggregate | None = None


class ReportReleaseGateWrite(FrozenReportContract):
    id: UUID
    decision: ReportReleaseDecisionResult
    sealed_report_id: UUID | None = None
    created_at: AwareUtcDateTime


class ReportReleaseGateRecord(ReportReleaseGateWrite):
    pass


_REQUIREMENT_CHECKS = {
    ReleaseGateRequirement.NO_UNSUPPORTED_FACTUAL_BODY_CLAIMS: {
        RuntimeReflectionCheck.FACTUAL_BLOCK_HAS_CLAIM,
        RuntimeReflectionCheck.PRIMARY_CLAIM_HAS_EVIDENCE,
        RuntimeReflectionCheck.UNSUPPORTED_CLAIMS_RESTRICTED,
    },
    ReleaseGateRequirement.CONFLICTS_DISCLOSED: {
        RuntimeReflectionCheck.CONFLICTING_CLAIMS_DISCLOSED,
    },
    ReleaseGateRequirement.DOCUMENT_CITATIONS_VALID: {
        RuntimeReflectionCheck.DOCUMENT_CLAIM_HAS_VALID_CITATION,
        RuntimeReflectionCheck.CITATION_VALID,
    },
    ReleaseGateRequirement.STRUCTURED_LINEAGE_VALID: {
        RuntimeReflectionCheck.STRUCTURED_CLAIM_HAS_LINEAGE,
    },
    ReleaseGateRequirement.TEMPORAL_EVIDENCE_VALID: {
        RuntimeReflectionCheck.NO_FUTURE_EVIDENCE,
        RuntimeReflectionCheck.STRICT_DOCUMENT_PUBLISHED_AT_KNOWN,
    },
    ReleaseGateRequirement.NO_SYNTHETIC_CONTAMINATION: {
        RuntimeReflectionCheck.NO_REAL_RESEARCH_SYNTHETIC_EVIDENCE,
        RuntimeReflectionCheck.SYNTHETIC_NOT_REAL_COMPANY_RESEARCH,
        RuntimeReflectionCheck.FIXTURE_NOT_DESCRIBED_AS_LIVE,
    },
    ReleaseGateRequirement.CONTEXT_MATCHES: {
        RuntimeReflectionCheck.SECURITY_MATCHES,
        RuntimeReflectionCheck.SNAPSHOT_MATCHES,
        RuntimeReflectionCheck.AS_OF_MATCHES,
        RuntimeReflectionCheck.NO_CROSS_SECURITY_RECORDS,
        RuntimeReflectionCheck.NO_CROSS_SNAPSHOT_RECORDS,
        RuntimeReflectionCheck.REPORT_AS_OF_PRESENT,
        RuntimeReflectionCheck.SNAPSHOT_IDENTITY_PRESENT,
        RuntimeReflectionCheck.REPORT_INPUT_MANIFEST_UNCHANGED,
    },
    ReleaseGateRequirement.NO_FORBIDDEN_ADVICE: {
        RuntimeReflectionCheck.NO_RATING_LANGUAGE,
        RuntimeReflectionCheck.NO_TARGET_PRICE,
        RuntimeReflectionCheck.NO_POSITION_ADVICE,
        RuntimeReflectionCheck.NO_TRADING_INSTRUCTION,
        RuntimeReflectionCheck.NO_UNSUPPORTED_OVERSTATEMENT,
    },
    ReleaseGateRequirement.DATA_QUALITY_PRESENT: {
        RuntimeReflectionCheck.DATA_QUALITY_PRESENT,
    },
    ReleaseGateRequirement.LIMITATIONS_PRESENT: {
        RuntimeReflectionCheck.LIMITATIONS_PRESENT,
    },
}


class ReportReleaseGate:
    def evaluate(
        self,
        candidate: ResearchReportAggregate,
        manifest: ReportInputManifest,
        round_two: ReportReflectionResult,
        policy: ReportPolicyRecord,
    ) -> ReportReleaseDecisionResult:
        report = candidate.report
        finding_checks = _finding_checks(round_two)
        report_checksums_valid, projection_matches = _report_integrity(candidate)
        input_checksums_valid = _input_integrity(candidate, manifest)
        round_two_completed = _round_two_completed(candidate, round_two)
        section_keys = {section.section for section in report.structured_content.sections}
        requirement_values = {
            ReleaseGateRequirement.REPORT_CHECKSUMS_VALID: report_checksums_valid,
            ReleaseGateRequirement.PACKAGE_INPUT_CHECKSUMS_VALID: input_checksums_valid,
            ReleaseGateRequirement.ROUND_TWO_COMPLETED: round_two_completed,
            ReleaseGateRequirement.NO_CRITICAL_FINDINGS: (round_two.run.critical_count == 0),
            ReleaseGateRequirement.NO_HIGH_FINDINGS: (round_two.run.high_count == 0),
            ReleaseGateRequirement.NO_UNSUPPORTED_FACTUAL_BODY_CLAIMS: (
                _checks_absent(
                    finding_checks,
                    ReleaseGateRequirement.NO_UNSUPPORTED_FACTUAL_BODY_CLAIMS,
                )
            ),
            ReleaseGateRequirement.CONFLICTS_DISCLOSED: _checks_absent(
                finding_checks,
                ReleaseGateRequirement.CONFLICTS_DISCLOSED,
            ),
            ReleaseGateRequirement.DOCUMENT_CITATIONS_VALID: _checks_absent(
                finding_checks,
                ReleaseGateRequirement.DOCUMENT_CITATIONS_VALID,
            ),
            ReleaseGateRequirement.STRUCTURED_LINEAGE_VALID: _checks_absent(
                finding_checks,
                ReleaseGateRequirement.STRUCTURED_LINEAGE_VALID,
            ),
            ReleaseGateRequirement.TEMPORAL_EVIDENCE_VALID: _checks_absent(
                finding_checks,
                ReleaseGateRequirement.TEMPORAL_EVIDENCE_VALID,
            ),
            ReleaseGateRequirement.NO_SYNTHETIC_CONTAMINATION: (
                (
                    manifest.synthetic_status
                    in {
                        SyntheticStatus.REAL_VERIFIED,
                        SyntheticStatus.FIXTURE_REAL_EXCERPT,
                    }
                    and manifest.research_mode is ResearchMode.REAL_RESEARCH
                )
                or (
                    manifest.synthetic_status is SyntheticStatus.SYNTHETIC_TEST_ONLY
                    and manifest.research_mode is ResearchMode.SYNTHETIC_TEST_ONLY
                )
            )
            and (
                _checks_absent(
                    finding_checks,
                    ReleaseGateRequirement.NO_SYNTHETIC_CONTAMINATION,
                )
            ),
            ReleaseGateRequirement.CONTEXT_MATCHES: (
                _context_matches(candidate, manifest)
                and _checks_absent(
                    finding_checks,
                    ReleaseGateRequirement.CONTEXT_MATCHES,
                )
            ),
            ReleaseGateRequirement.NO_FORBIDDEN_ADVICE: _checks_absent(
                finding_checks,
                ReleaseGateRequirement.NO_FORBIDDEN_ADVICE,
            ),
            ReleaseGateRequirement.DATA_QUALITY_PRESENT: (
                ReportSection.DATA_QUALITY in section_keys
                and _checks_absent(
                    finding_checks,
                    ReleaseGateRequirement.DATA_QUALITY_PRESENT,
                )
            ),
            ReleaseGateRequirement.LIMITATIONS_PRESENT: (
                ReportSection.LIMITATIONS in section_keys
                and _checks_absent(
                    finding_checks,
                    ReleaseGateRequirement.LIMITATIONS_PRESENT,
                )
            ),
            ReleaseGateRequirement.PACKAGE_ELIGIBLE: (
                manifest.package_status is ResearchPackageStatus.COMPLETE
            ),
            ReleaseGateRequirement.REPORT_TYPE_COMPATIBLE: (
                _report_type_compatible(candidate, manifest, policy)
            ),
            ReleaseGateRequirement.PROJECTION_MATCHES: projection_matches,
        }
        requirements = tuple(
            ReleaseGateRequirementResult(
                requirement=requirement,
                passed=requirement_values[requirement],
            )
            for requirement in ReleaseGateRequirement
        )
        decision = _decision(
            manifest=manifest,
            round_two=round_two,
            requirements=requirements,
        )
        failed_requirements = {item.requirement.value for item in requirements if not item.passed}
        finding_reason_codes = {item.value for item in finding_checks}
        reason_codes = tuple(sorted(failed_requirements | finding_reason_codes))
        sealed = (
            _build_sealed_report(candidate) if decision is ReleaseGateDecision.PUBLISHABLE else None
        )
        return ReportReleaseDecisionResult(
            candidate_report_id=report.id,
            round_two_reflection_run_id=round_two.run.id,
            gate_version=RELEASE_GATE_VERSION,
            input_manifest_checksum=manifest.canonical_payload_checksum,
            report_checksum=report.content_checksum,
            internal_release_status=decision,
            requirements=requirements,
            reason_codes=reason_codes,
            sealed_report=sealed,
        )


def _finding_checks(
    result: ReportReflectionResult,
) -> set[RuntimeReflectionCheck]:
    checks: set[RuntimeReflectionCheck] = set()
    for finding in result.findings:
        try:
            checks.add(RuntimeReflectionCheck(finding.finding_code))
        except ValueError:
            continue
    return checks


def _checks_absent(
    findings: set[RuntimeReflectionCheck],
    requirement: ReleaseGateRequirement,
) -> bool:
    return findings.isdisjoint(_REQUIREMENT_CHECKS[requirement])


def _report_integrity(
    candidate: ResearchReportAggregate,
) -> tuple[bool, bool]:
    report = candidate.report
    rendered = DeterministicMarkdownRenderer().render(report.structured_content)
    projection_matches = rendered.markdown_content == report.markdown_content
    try:
        references = ReportReferenceAllocator().allocate(report.structured_content).references
        context = ReportChecksumContext(
            schema_version=report.structured_content.schema_version,
            template_name=report.template_name,
            template_version=report.template_version,
            renderer_version=report.renderer_version,
            markdown_renderer_version=MARKDOWN_RENDERER_VERSION,
            locale=report.report_locale,
            input_manifest_checksum=report.input_manifest_checksum,
            visible_references=references,
        )
        verify_report_projection(
            report.structured_content,
            report.markdown_content,
            context,
            ReportProjectionChecksums(
                structured_checksum=report.structured_checksum,
                markdown_checksum=report.markdown_checksum,
                content_checksum=report.content_checksum,
            ),
        )
    except (TypeError, ValueError):
        return False, projection_matches
    return True, projection_matches


def _input_integrity(
    candidate: ResearchReportAggregate,
    manifest: ReportInputManifest,
) -> bool:
    report = candidate.report
    return (
        report.research_package_id == manifest.research_package_id
        and report.input_manifest_checksum == manifest.canonical_payload_checksum
        and report.package_checksum == manifest.package_checksum
        and report.claim_set_checksum == manifest.claims_checksum
        and report.evidence_set_checksum == manifest.evidence_checksum
        and report.link_set_checksum == manifest.links_checksum
        and report.citation_set_checksum == manifest.citations_checksum
    )


def _context_matches(
    candidate: ResearchReportAggregate,
    manifest: ReportInputManifest,
) -> bool:
    report = candidate.report
    return (
        report.security_id == manifest.security_id
        and report.snapshot_id == manifest.snapshot_id
        and report.research_as_of_time == manifest.research_as_of_time
    )


def _round_two_completed(
    candidate: ResearchReportAggregate,
    result: ReportReflectionResult,
) -> bool:
    run = result.run
    return (
        run.round_number == 2
        and run.status
        in {
            ReportReflectionStatus.PASS,
            ReportReflectionStatus.FINDINGS,
        }
        and run.completed_at is not None
        and run.research_report_id == candidate.report.id
        and run.input_report_checksum == candidate.report.content_checksum
        and len(result.finding_ids) == run.total_finding_count
        and tuple(item.id for item in result.findings) == result.finding_ids
    )


def _report_type_compatible(
    candidate: ResearchReportAggregate,
    manifest: ReportInputManifest,
    policy: ReportPolicyRecord,
) -> bool:
    if candidate.report.report_type not in policy.allowed_report_types:
        return False
    if manifest.package_status is ResearchPackageStatus.BLOCKED:
        return candidate.report.report_type is ReportType.DATA_QUALITY_REPORT
    return manifest.package_status is not ResearchPackageStatus.FAILED


def _decision(
    *,
    manifest: ReportInputManifest,
    round_two: ReportReflectionResult,
    requirements: tuple[ReleaseGateRequirementResult, ...],
) -> ReleaseGateDecision:
    by_code = {item.requirement: item.passed for item in requirements}
    workflow_valid = (
        by_code[ReleaseGateRequirement.REPORT_CHECKSUMS_VALID]
        and by_code[ReleaseGateRequirement.PACKAGE_INPUT_CHECKSUMS_VALID]
        and by_code[ReleaseGateRequirement.ROUND_TWO_COMPLETED]
        and by_code[ReleaseGateRequirement.PROJECTION_MATCHES]
    )
    if not workflow_valid or manifest.package_status is ResearchPackageStatus.FAILED:
        return ReleaseGateDecision.FAILED
    if manifest.package_status is ResearchPackageStatus.BLOCKED:
        return ReleaseGateDecision.BLOCKED
    if (
        not by_code[ReleaseGateRequirement.NO_CRITICAL_FINDINGS]
        or not by_code[ReleaseGateRequirement.NO_HIGH_FINDINGS]
    ):
        return ReleaseGateDecision.BLOCKED
    if manifest.package_status is ResearchPackageStatus.PARTIAL:
        return ReleaseGateDecision.PARTIAL
    if round_two.run.status is ReportReflectionStatus.FINDINGS or not all(
        item.passed for item in requirements
    ):
        return ReleaseGateDecision.PARTIAL
    return ReleaseGateDecision.PUBLISHABLE


def _build_sealed_report(
    candidate: ResearchReportAggregate,
) -> ResearchReportAggregate:
    source = candidate.report
    sealed = source.model_copy(
        update={
            "id": uuid5(
                NAMESPACE_URL,
                f"{source.id}:{RELEASE_GATE_VERSION}:publishable",
            ),
            "report_version": source.report_version + 1,
            "previous_report_id": source.id,
            "status": ResearchReportStatus.PUBLISHABLE,
        }
    )
    validate_report_successor(source, sealed)
    return rebase_report_bindings(candidate, sealed)
