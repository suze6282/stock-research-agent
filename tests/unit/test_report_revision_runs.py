from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.reports.reflection import (
    ReportReflectionRunRecord,
    ReportReflectionStatus,
)

NOW = datetime(2026, 7, 28, 9, tzinfo=UTC)
SOURCE_REPORT_ID = UUID(int=1001)
REFLECTION_RUN_ID = UUID(int=1002)
REVISION_RUN_ID = UUID(int=1003)
TARGET_REPORT_ID = UUID(int=1004)
FINDING_ID = UUID(int=1005)


def _module() -> object:
    return import_module("stock_research_agent.domain.reports.revision")


def _action() -> object:
    module = _module()
    return module.ReportRevisionAction(
        finding_id=FINDING_ID,
        action_code=module.ReportRevisionActionCode.DOWNGRADE_PARTIAL_LANGUAGE,
        block_key="financial-health.metric",
    )


def _write(**updates: object) -> object:
    module = _module()
    values: dict[str, object] = {
        "id": REVISION_RUN_ID,
        "source_report_id": SOURCE_REPORT_ID,
        "source_reflection_run_id": REFLECTION_RUN_ID,
        "report_policy_version": "report-policy-v1",
        "engine_name": module.REVISION_ENGINE_NAME,
        "engine_version": module.REVISION_ENGINE_VERSION,
        "revision_round": 1,
        "status": module.ReportRevisionStatus.RUNNING,
        "started_at": NOW,
    }
    values.update(updates)
    return module.ReportRevisionRunWrite.model_validate(values)


def _record(**updates: object) -> object:
    module = _module()
    values: dict[str, object] = {
        **_write().model_dump(mode="python"),
        "target_report_id": None,
        "actions": (),
        "applied_finding_ids": (),
        "unresolved_finding_ids": (),
        "blocked_reason_code": None,
        "error_code": None,
        "safe_error_message": None,
        "completed_at": None,
    }
    values.update(updates)
    return module.ReportRevisionRunRecord.model_validate(values)


def _round_one_reflection(**updates: object) -> ReportReflectionRunRecord:
    values: dict[str, object] = {
        "id": REFLECTION_RUN_ID,
        "research_report_id": SOURCE_REPORT_ID,
        "reflection_policy_version": "runtime-report-reflection-v1",
        "engine_name": "deterministic-report-reflection",
        "engine_version": "deterministic-report-reflection-v1",
        "round_number": 1,
        "input_report_checksum": "a" * 64,
        "status": ReportReflectionStatus.FINDINGS,
        "started_at": NOW,
        "total_finding_count": 1,
        "critical_count": 0,
        "high_count": 1,
        "medium_count": 0,
        "low_count": 0,
        "completed_at": NOW,
    }
    values.update(updates)
    return ReportReflectionRunRecord.model_validate(values)


def test_revision_run_binds_round_one_source_policy_and_engine() -> None:
    module = _module()
    run = _write()

    assert run.revision_round == 1
    assert run.source_report_id == SOURCE_REPORT_ID
    assert run.source_reflection_run_id == REFLECTION_RUN_ID
    assert run.report_policy_version == "report-policy-v1"
    assert module.revision_run_uniqueness_key(run) == (SOURCE_REPORT_ID,)
    module.validate_revision_source(
        source_report_id=SOURCE_REPORT_ID,
        reflection=_round_one_reflection(),
    )


@pytest.mark.parametrize("revision_round", (0, 2, 99))
def test_revision_round_is_exactly_one(revision_round: int) -> None:
    with pytest.raises(ValidationError):
        _write(revision_round=revision_round)


@pytest.mark.parametrize(
    "reflection_updates",
    (
        {"round_number": 2},
        {"research_report_id": UUID(int=9999)},
        {"status": ReportReflectionStatus.PASS, "total_finding_count": 0, "high_count": 0},
        {"status": ReportReflectionStatus.BLOCKED, "blocked_reason_code": "INPUT_BLOCKED"},
        {
            "status": ReportReflectionStatus.FAILED,
            "total_finding_count": 0,
            "high_count": 0,
            "error_code": "REFLECTION_FAILED",
            "safe_error_message": "Safe failure.",
        },
    ),
)
def test_revision_requires_completed_round_one_findings(
    reflection_updates: dict[str, object],
) -> None:
    module = _module()
    reflection = _round_one_reflection(**reflection_updates)

    with pytest.raises(module.ReportRevisionTransitionError):
        module.validate_revision_source(
            source_report_id=SOURCE_REPORT_ID,
            reflection=reflection,
        )


@pytest.mark.parametrize(
    ("target_status", "target_report_id", "actions", "applied", "unresolved"),
    (
        ("COMPLETED", TARGET_REPORT_ID, (_action(),), (FINDING_ID,), ()),
        ("PARTIAL", TARGET_REPORT_ID, (_action(),), (FINDING_ID,), (UUID(int=2001),)),
        ("BLOCKED", None, (), (), (FINDING_ID,)),
    ),
)
def test_running_revision_completes_with_consistent_result(
    target_status: str,
    target_report_id: UUID | None,
    actions: tuple[object, ...],
    applied: tuple[UUID, ...],
    unresolved: tuple[UUID, ...],
) -> None:
    module = _module()
    completion = module.ReportRevisionCompletion(
        target_status=module.ReportRevisionStatus(target_status),
        target_report_id=target_report_id,
        actions=actions,
        applied_finding_ids=applied,
        unresolved_finding_ids=unresolved,
        blocked_reason_code=("REVISION_NOT_SAFE" if target_status == "BLOCKED" else None),
        completed_at=NOW,
    )

    completed = module.complete_revision_run(_record(), completion)
    result = module.ReportRevisionResult(run=completed)

    assert result.run.status.value == target_status
    assert result.run.target_report_id == target_report_id
    assert result.run.completed_at == NOW


def test_failed_revision_has_no_target_or_applied_actions() -> None:
    module = _module()
    completion = module.ReportRevisionCompletion(
        target_status=module.ReportRevisionStatus.FAILED,
        target_report_id=None,
        actions=(),
        applied_finding_ids=(),
        unresolved_finding_ids=(FINDING_ID,),
        error_code="REVISION_FAILED",
        safe_error_message="Safe deterministic revision failure.",
        completed_at=NOW,
    )

    completed = module.complete_revision_run(_record(), completion)

    assert completed.status is module.ReportRevisionStatus.FAILED
    assert completed.target_report_id is None


@pytest.mark.parametrize(
    "updates",
    (
        {
            "target_status": "COMPLETED",
            "target_report_id": None,
            "actions": (),
            "applied_finding_ids": (),
            "unresolved_finding_ids": (),
        },
        {
            "target_status": "COMPLETED",
            "target_report_id": TARGET_REPORT_ID,
            "actions": (),
            "applied_finding_ids": (),
            "unresolved_finding_ids": (FINDING_ID,),
        },
        {
            "target_status": "PARTIAL",
            "target_report_id": TARGET_REPORT_ID,
            "actions": (_action(),),
            "applied_finding_ids": (),
            "unresolved_finding_ids": (FINDING_ID,),
        },
        {
            "target_status": "FAILED",
            "target_report_id": TARGET_REPORT_ID,
            "actions": (),
            "applied_finding_ids": (),
            "unresolved_finding_ids": (),
            "error_code": "REVISION_FAILED",
            "safe_error_message": "Safe failure.",
        },
    ),
)
def test_completion_rejects_inconsistent_target_actions_and_findings(
    updates: dict[str, object],
) -> None:
    module = _module()
    values = {
        "target_status": module.ReportRevisionStatus.BLOCKED,
        "target_report_id": None,
        "actions": (),
        "applied_finding_ids": (),
        "unresolved_finding_ids": (FINDING_ID,),
        "blocked_reason_code": None,
        "error_code": None,
        "safe_error_message": None,
        "completed_at": NOW,
        **updates,
    }

    with pytest.raises(ValidationError):
        module.ReportRevisionCompletion.model_validate(values)


def test_terminal_revision_is_frozen_and_cannot_transition_or_gain_second_target() -> None:
    module = _module()
    terminal = _record(
        status=module.ReportRevisionStatus.COMPLETED,
        target_report_id=TARGET_REPORT_ID,
        actions=(_action(),),
        applied_finding_ids=(FINDING_ID,),
        completed_at=NOW,
    )

    with pytest.raises(module.ReportRevisionTransitionError):
        module.ReportRevisionStateMachine().transition(
            terminal.status,
            module.ReportRevisionStatus.PARTIAL,
        )
    with pytest.raises(ValidationError, match="Instance is frozen"):
        terminal.target_report_id = UUID(int=9999)
    assert module.revision_run_uniqueness_key(terminal) == (SOURCE_REPORT_ID,)
