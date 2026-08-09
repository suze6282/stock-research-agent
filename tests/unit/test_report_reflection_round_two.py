from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.reports.reflection import (
    ReportReflectionResult,
    ReportReflectionRunRecord,
    ReportReflectionStatus,
    ReportReflectionTransitionError,
    validate_reflection_predecessor,
)
from stock_research_agent.domain.reports.reporting import ResearchReportAggregate
from stock_research_agent.domain.reports.revision import (
    REVISION_ENGINE_NAME,
    REVISION_ENGINE_VERSION,
    ReportRevisionAction,
    ReportRevisionActionCode,
    ReportRevisionResult,
    ReportRevisionRunRecord,
    ReportRevisionStatus,
)
from tests.unit.test_report_reflection_engine import _aggregate

NOW = datetime(2026, 7, 28, 10, tzinfo=UTC)
ROUND_ONE_ID = UUID(int=3001)
REVISION_RUN_ID = UUID(int=3002)
FINDING_ID = UUID(int=3003)


def _prior(
    report: ResearchReportAggregate,
    *,
    status: ReportReflectionStatus = ReportReflectionStatus.PASS,
    round_number: int = 1,
) -> ReportReflectionResult:
    has_finding = status is ReportReflectionStatus.FINDINGS
    run = ReportReflectionRunRecord(
        id=ROUND_ONE_ID,
        research_report_id=report.report.id,
        reflection_policy_version="runtime-report-reflection-v1",
        engine_name="deterministic-report-reflection",
        engine_version="deterministic-report-reflection-v1",
        round_number=round_number,
        input_report_checksum=report.report.content_checksum,
        status=status,
        started_at=NOW,
        total_finding_count=int(has_finding),
        critical_count=0,
        high_count=int(has_finding),
        medium_count=0,
        low_count=0,
        blocked_reason_code=(
            "REFLECTION_INPUT_BLOCKED" if status is ReportReflectionStatus.BLOCKED else None
        ),
        error_code=("REFLECTION_FAILED" if status is ReportReflectionStatus.FAILED else None),
        safe_error_message=(
            "Safe reflection failure." if status is ReportReflectionStatus.FAILED else None
        ),
        completed_at=NOW,
    )
    return ReportReflectionResult(
        run=run,
        finding_ids=((FINDING_ID,) if has_finding else ()),
    )


def _revised_target(source: ResearchReportAggregate) -> ResearchReportAggregate:
    report = source.report.model_copy(
        update={
            "id": UUID(int=3100),
            "previous_report_id": source.report.id,
            "report_version": source.report.report_version + 1,
            "status": "REVISED",
        }
    )
    return ResearchReportAggregate(report=report)


def _revision(
    source: ResearchReportAggregate,
    target: ResearchReportAggregate,
    prior: ReportReflectionResult,
    **updates: object,
) -> ReportRevisionResult:
    action = ReportRevisionAction(
        finding_id=FINDING_ID,
        action_code=ReportRevisionActionCode.DOWNGRADE_PARTIAL_LANGUAGE,
        block_key="financial_health.metric",
    )
    values: dict[str, object] = {
        "id": REVISION_RUN_ID,
        "source_report_id": source.report.id,
        "source_reflection_run_id": prior.run.id,
        "report_policy_version": "report-policy-v1",
        "engine_name": REVISION_ENGINE_NAME,
        "engine_version": REVISION_ENGINE_VERSION,
        "revision_round": 1,
        "status": ReportRevisionStatus.COMPLETED,
        "started_at": NOW,
        "target_report_id": target.report.id,
        "actions": (action,),
        "applied_finding_ids": (FINDING_ID,),
        "unresolved_finding_ids": (),
        "completed_at": NOW,
    }
    values.update(updates)
    return ReportRevisionResult(run=ReportRevisionRunRecord.model_validate(values))


def test_round_two_accepts_same_report_after_clean_round_one() -> None:
    report, _ = _aggregate()
    prior = _prior(report)

    validate_reflection_predecessor(
        report=report,
        round_number=2,
        prior=prior,
        revision=None,
    )


def test_round_two_targets_the_single_revision_result() -> None:
    source, _ = _aggregate()
    prior = _prior(source, status=ReportReflectionStatus.FINDINGS)
    target = _revised_target(source)
    revision = _revision(source, target, prior)

    validate_reflection_predecessor(
        report=target,
        round_number=2,
        prior=prior,
        revision=revision,
    )


def test_round_two_accepts_partial_revision_target_for_independent_recheck() -> None:
    source, _ = _aggregate()
    prior = _prior(source, status=ReportReflectionStatus.FINDINGS)
    target = _revised_target(source)
    revision = _revision(
        source,
        target,
        prior,
        status=ReportRevisionStatus.PARTIAL,
        unresolved_finding_ids=(UUID(int=9994),),
    )

    validate_reflection_predecessor(
        report=target,
        round_number=2,
        prior=prior,
        revision=revision,
    )


@pytest.mark.parametrize("round_number", (1, 3))
def test_round_two_rejects_round_skipping(round_number: int) -> None:
    report, _ = _aggregate()

    with pytest.raises(
        ReportReflectionTransitionError,
        match="REPORT_REFLECTION_PREDECESSOR_INVALID",
    ):
        validate_reflection_predecessor(
            report=report,
            round_number=round_number,
            prior=_prior(report),
            revision=None,
        )


def test_round_two_rejects_reusing_round_two_as_its_predecessor() -> None:
    report, _ = _aggregate()

    with pytest.raises(ReportReflectionTransitionError):
        validate_reflection_predecessor(
            report=report,
            round_number=2,
            prior=_prior(report, round_number=2),
            revision=None,
        )


@pytest.mark.parametrize(
    "status",
    (ReportReflectionStatus.BLOCKED, ReportReflectionStatus.FAILED),
)
def test_round_two_rejects_nonreviewable_round_one_terminal(
    status: ReportReflectionStatus,
) -> None:
    report, _ = _aggregate()

    with pytest.raises(ReportReflectionTransitionError):
        validate_reflection_predecessor(
            report=report,
            round_number=2,
            prior=_prior(report, status=status),
            revision=None,
        )


@pytest.mark.parametrize(
    "revision_updates",
    (
        {"source_report_id": UUID(int=9991)},
        {"source_reflection_run_id": UUID(int=9992)},
        {"target_report_id": UUID(int=9993)},
    ),
)
def test_round_two_rejects_mismatched_revision(
    revision_updates: dict[str, object],
) -> None:
    source, _ = _aggregate()
    prior = _prior(source, status=ReportReflectionStatus.FINDINGS)
    target = _revised_target(source)
    revision = _revision(source, target, prior, **revision_updates)

    with pytest.raises(ReportReflectionTransitionError):
        validate_reflection_predecessor(
            report=target,
            round_number=2,
            prior=prior,
            revision=revision,
        )


def test_round_two_rejects_child_report_bypass_without_revision() -> None:
    source, _ = _aggregate()
    child = _revised_target(source)

    with pytest.raises(ReportReflectionTransitionError):
        validate_reflection_predecessor(
            report=child,
            round_number=2,
            prior=_prior(source),
            revision=None,
        )


def test_round_two_rejects_findings_without_revision_or_revision_after_pass() -> None:
    source, _ = _aggregate()
    findings = _prior(source, status=ReportReflectionStatus.FINDINGS)
    target = _revised_target(source)

    with pytest.raises(ReportReflectionTransitionError):
        validate_reflection_predecessor(
            report=source,
            round_number=2,
            prior=findings,
            revision=None,
        )
    with pytest.raises(ReportReflectionTransitionError):
        validate_reflection_predecessor(
            report=target,
            round_number=2,
            prior=_prior(source),
            revision=_revision(source, target, findings),
        )
