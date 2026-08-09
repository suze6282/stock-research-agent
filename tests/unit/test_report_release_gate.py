from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.reports.checksums import (
    ReportChecksumContext,
    combined_report_checksum,
)
from stock_research_agent.domain.reports.enums import ReportType
from stock_research_agent.domain.reports.markdown import (
    MARKDOWN_RENDERER_VERSION,
)
from stock_research_agent.domain.reports.policies import build_default_report_policy
from stock_research_agent.domain.reports.references import ReportReferenceAllocator
from stock_research_agent.domain.reports.reflection import (
    ReflectionFindingCategory,
    ReflectionSeverity,
    ReportReflectionFindingRecord,
    ReportReflectionResult,
    ReportReflectionRunRecord,
    ReportReflectionStatus,
)
from stock_research_agent.domain.reports.reflection_policy import (
    RuntimeReflectionCheck,
)
from stock_research_agent.domain.reports.release_gate import (
    RELEASE_GATE_VERSION,
    ReleaseGateDecision,
    ReleaseGateRequirement,
    ReportReleaseGate,
)
from stock_research_agent.domain.reports.reporting import (
    ResearchReportAggregate,
    ResearchReportStatus,
)
from stock_research_agent.domain.reports.schemas import ReportInputManifest
from stock_research_agent.domain.research_agent.enums import ResearchPackageStatus
from tests.unit.test_report_reflection_engine import _aggregate

NOW = datetime(2026, 7, 28, 11, tzinfo=UTC)
ROUND_TWO_ID = UUID(int=4001)
FINDING_ID = UUID(int=4002)

EXPECTED_REQUIREMENTS = (
    "REPORT_CHECKSUMS_VALID",
    "PACKAGE_INPUT_CHECKSUMS_VALID",
    "ROUND_TWO_COMPLETED",
    "NO_CRITICAL_FINDINGS",
    "NO_HIGH_FINDINGS",
    "NO_UNSUPPORTED_FACTUAL_BODY_CLAIMS",
    "CONFLICTS_DISCLOSED",
    "DOCUMENT_CITATIONS_VALID",
    "STRUCTURED_LINEAGE_VALID",
    "TEMPORAL_EVIDENCE_VALID",
    "NO_SYNTHETIC_CONTAMINATION",
    "CONTEXT_MATCHES",
    "NO_FORBIDDEN_ADVICE",
    "DATA_QUALITY_PRESENT",
    "LIMITATIONS_PRESENT",
    "PACKAGE_ELIGIBLE",
    "REPORT_TYPE_COMPATIBLE",
    "PROJECTION_MATCHES",
)


def _candidate(
    **updates: object,
) -> tuple[ResearchReportAggregate, ReportInputManifest]:
    candidate, manifest = _aggregate(**updates)
    report = candidate.report
    references = ReportReferenceAllocator().allocate(report.structured_content).references
    checksum = combined_report_checksum(
        report.structured_checksum,
        report.markdown_checksum,
        ReportChecksumContext(
            schema_version=report.structured_content.schema_version,
            template_name=report.template_name,
            template_version=report.template_version,
            renderer_version=report.renderer_version,
            markdown_renderer_version=MARKDOWN_RENDERER_VERSION,
            locale=report.report_locale,
            input_manifest_checksum=report.input_manifest_checksum,
            visible_references=references,
        ),
    )
    return (
        ResearchReportAggregate(report=report.model_copy(update={"content_checksum": checksum})),
        manifest,
    )


def _round_two(
    report: ResearchReportAggregate,
    *,
    check: RuntimeReflectionCheck | None = None,
    severity: ReflectionSeverity = ReflectionSeverity.HIGH,
    status: ReportReflectionStatus | None = None,
    round_number: int = 2,
) -> ReportReflectionResult:
    has_finding = check is not None
    actual_status = status or (
        ReportReflectionStatus.FINDINGS if has_finding else ReportReflectionStatus.PASS
    )
    run = ReportReflectionRunRecord.model_construct(
        id=ROUND_TWO_ID,
        research_report_id=report.report.id,
        reflection_policy_version="runtime-report-reflection-v1",
        engine_name="deterministic-report-reflection",
        engine_version="deterministic-report-reflection-v1",
        round_number=round_number,
        input_report_checksum=report.report.content_checksum,
        status=actual_status,
        started_at=NOW,
        total_finding_count=int(has_finding),
        critical_count=int(severity is ReflectionSeverity.CRITICAL and has_finding),
        high_count=int(severity is ReflectionSeverity.HIGH and has_finding),
        medium_count=int(severity is ReflectionSeverity.MEDIUM and has_finding),
        low_count=int(severity is ReflectionSeverity.LOW and has_finding),
        blocked_reason_code=None,
        error_code=None,
        safe_error_message=None,
        completed_at=(None if actual_status is ReportReflectionStatus.RUNNING else NOW),
    )
    findings = (
        (
            ReportReflectionFindingRecord(
                id=FINDING_ID,
                reflection_run_id=run.id,
                research_report_id=report.report.id,
                report_section_id=None,
                report_block_id=None,
                claim_id=None,
                evidence_id=None,
                citation_id=None,
                finding_code=check.value,
                category=ReflectionFindingCategory.CONTENT_SAFETY,
                severity=severity,
                description="A release requirement did not pass.",
                remediation_code=f"REMEDIATE_{check.value}",
                blocking=severity in {ReflectionSeverity.CRITICAL, ReflectionSeverity.HIGH},
                created_at=NOW,
            ),
        )
        if check is not None
        else ()
    )
    return ReportReflectionResult.model_construct(
        run=run,
        finding_ids=tuple(item.id for item in findings),
        findings=findings,
    )


def test_release_gate_requirement_registry_is_closed_and_has_exactly_eighteen() -> None:
    assert tuple(item.value for item in ReleaseGateRequirement) == EXPECTED_REQUIREMENTS


def test_complete_clean_report_becomes_internal_publishable_content_identical_seal() -> None:
    candidate, manifest = _candidate()

    result = ReportReleaseGate().evaluate(
        candidate,
        manifest,
        _round_two(candidate),
        build_default_report_policy(),
    )

    assert result.internal_release_status is ReleaseGateDecision.PUBLISHABLE
    assert result.gate_version == RELEASE_GATE_VERSION
    assert result.reason_codes == ()
    assert len(result.requirements) == 18
    assert all(item.passed for item in result.requirements)
    assert result.sealed_report is not None
    sealed = result.sealed_report.report
    assert sealed.status is ResearchReportStatus.PUBLISHABLE
    assert sealed.previous_report_id == candidate.report.id
    assert sealed.report_version == candidate.report.report_version + 1
    for field in (
        "structured_content",
        "markdown_content",
        "structured_checksum",
        "markdown_checksum",
        "content_checksum",
        "claim_set_checksum",
        "evidence_set_checksum",
        "link_set_checksum",
        "citation_set_checksum",
    ):
        assert getattr(sealed, field) == getattr(candidate.report, field)
    assert "public" not in result.model_dump_json().casefold()


@pytest.mark.parametrize(
    ("package_status", "expected"),
    (
        (ResearchPackageStatus.PARTIAL, ReleaseGateDecision.PARTIAL),
        (ResearchPackageStatus.BLOCKED, ReleaseGateDecision.BLOCKED),
        (ResearchPackageStatus.FAILED, ReleaseGateDecision.FAILED),
    ),
)
def test_package_state_sets_honest_nonpublishable_decision(
    package_status: ResearchPackageStatus,
    expected: ReleaseGateDecision,
) -> None:
    candidate, manifest = _candidate()
    manifest = manifest.model_copy(update={"package_status": package_status})

    result = ReportReleaseGate().evaluate(
        candidate,
        manifest,
        _round_two(candidate),
        build_default_report_policy(),
    )

    assert result.internal_release_status is expected
    assert result.sealed_report is None


@pytest.mark.parametrize(
    "check",
    (
        RuntimeReflectionCheck.SECURITY_MATCHES,
        RuntimeReflectionCheck.NO_FUTURE_EVIDENCE,
        RuntimeReflectionCheck.CITATION_VALID,
        RuntimeReflectionCheck.NO_TRADING_INSTRUCTION,
    ),
)
def test_unresolved_critical_or_high_finding_blocks_release(
    check: RuntimeReflectionCheck,
) -> None:
    candidate, manifest = _candidate()

    result = ReportReleaseGate().evaluate(
        candidate,
        manifest,
        _round_two(candidate, check=check),
        build_default_report_policy(),
    )

    assert result.internal_release_status is ReleaseGateDecision.BLOCKED
    assert check.value in result.reason_codes
    assert result.sealed_report is None


def test_medium_or_low_finding_degrades_complete_package_to_partial() -> None:
    candidate, manifest = _candidate()

    result = ReportReleaseGate().evaluate(
        candidate,
        manifest,
        _round_two(
            candidate,
            check=RuntimeReflectionCheck.NO_ORPHAN_BODY_REFERENCE,
            severity=ReflectionSeverity.MEDIUM,
        ),
        build_default_report_policy(),
    )

    assert result.internal_release_status is ReleaseGateDecision.PARTIAL
    assert result.sealed_report is None


@pytest.mark.parametrize(
    "round_two_updates",
    (
        {"round_number": 1},
        {"status": ReportReflectionStatus.RUNNING},
    ),
)
def test_invalid_or_incomplete_round_two_is_failed_workflow(
    round_two_updates: dict[str, object],
) -> None:
    candidate, manifest = _candidate()
    round_two = _round_two(candidate, **round_two_updates)

    result = ReportReleaseGate().evaluate(
        candidate,
        manifest,
        round_two,
        build_default_report_policy(),
    )

    assert result.internal_release_status is ReleaseGateDecision.FAILED
    assert result.sealed_report is None


def test_gate_rejects_candidate_manifest_context_or_checksum_drift() -> None:
    candidate, manifest = _candidate()
    changed = ResearchReportAggregate(
        report=candidate.report.model_copy(update={"input_manifest_checksum": "9" * 64})
    )

    result = ReportReleaseGate().evaluate(
        changed,
        manifest,
        _round_two(changed),
        build_default_report_policy(),
    )

    assert result.internal_release_status is ReleaseGateDecision.FAILED
    assert "PACKAGE_INPUT_CHECKSUMS_VALID" in result.reason_codes


def test_blocked_package_always_blocked_and_full_report_type_is_incompatible() -> None:
    candidate, manifest = _candidate(report_type=ReportType.FULL_RESEARCH_DRAFT)
    manifest = manifest.model_copy(update={"package_status": ResearchPackageStatus.BLOCKED})

    result = ReportReleaseGate().evaluate(
        candidate,
        manifest,
        _round_two(candidate),
        build_default_report_policy(),
    )

    assert result.internal_release_status is ReleaseGateDecision.BLOCKED
    failed = {item.requirement for item in result.requirements if not item.passed}
    assert ReleaseGateRequirement.PACKAGE_ELIGIBLE in failed
    assert ReleaseGateRequirement.REPORT_TYPE_COMPATIBLE in failed


def test_gate_is_pure_deterministic_and_has_no_external_dependencies() -> None:
    candidate, manifest = _candidate()
    gate = ReportReleaseGate()
    inputs = (
        candidate,
        manifest,
        _round_two(candidate),
        build_default_report_policy(),
    )

    first = gate.evaluate(*inputs)
    second = gate.evaluate(*inputs)

    assert first == second
    assert vars(gate) == {}
    assert not hasattr(gate, "repository")
    assert not hasattr(gate, "tool_registry")
    assert not hasattr(gate, "model_provider")
    assert not hasattr(gate, "http_client")
