from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

NOW = datetime(2026, 7, 28, 8, tzinfo=UTC)
REPORT_ID = UUID(int=1)
RUN_ID = UUID(int=2)


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.reflection")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 report Reflection run contracts are missing")


def _write(**updates: object) -> object:
    module = _module()
    values: dict[str, object] = {
        "id": RUN_ID,
        "research_report_id": REPORT_ID,
        "reflection_policy_version": "runtime-report-reflection-v1",
        "engine_name": "deterministic-report-reflection",
        "engine_version": "deterministic-report-reflection-v1",
        "round_number": 1,
        "input_report_checksum": "a" * 64,
        "status": module.ReportReflectionStatus.RUNNING,
        "started_at": NOW,
    }
    values.update(updates)
    return module.ReportReflectionRunWrite.model_validate(values)


def _record(**updates: object) -> object:
    module = _module()
    values = {
        **_write().model_dump(mode="python"),
        "total_finding_count": 0,
        "critical_count": 0,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0,
        "blocked_reason_code": None,
        "error_code": None,
        "safe_error_message": None,
        "completed_at": None,
    }
    values.update(updates)
    return module.ReportReflectionRunRecord.model_validate(values)


def test_reflection_run_binds_exact_report_policy_engine_checksum_and_round() -> None:
    module = _module()
    run = _write()

    assert run.research_report_id == REPORT_ID
    assert run.reflection_policy_version == "runtime-report-reflection-v1"
    assert run.engine_name == "deterministic-report-reflection"
    assert run.engine_version == "deterministic-report-reflection-v1"
    assert run.input_report_checksum == "a" * 64
    assert run.round_number == 1
    assert module.reflection_run_uniqueness_key(run) == (
        REPORT_ID,
        "runtime-report-reflection-v1",
        1,
    )


@pytest.mark.parametrize("round_number", (0, 3))
def test_reflection_run_rejects_rounds_outside_one_and_two(
    round_number: int,
) -> None:
    with pytest.raises(ValidationError):
        _write(round_number=round_number)


@pytest.mark.parametrize(
    (
        "target",
        "counts",
        "blocked_reason",
        "error_code",
        "safe_message",
    ),
    (
        ("PASS", (0, 0, 0, 0), None, None, None),
        ("FINDINGS", (1, 2, 3, 4), None, None, None),
        ("BLOCKED", (0, 1, 0, 0), "INPUT_UNAVAILABLE", None, None),
        (
            "FAILED",
            (0, 0, 0, 0),
            None,
            "REFLECTION_FAILED",
            "Safe deterministic failure.",
        ),
    ),
)
def test_running_can_complete_to_each_valid_terminal_shape(
    target: str,
    counts: tuple[int, int, int, int],
    blocked_reason: str | None,
    error_code: str | None,
    safe_message: str | None,
) -> None:
    module = _module()
    critical, high, medium, low = counts
    completion = module.ReportReflectionCompletion(
        target_status=module.ReportReflectionStatus(target),
        total_finding_count=sum(counts),
        critical_count=critical,
        high_count=high,
        medium_count=medium,
        low_count=low,
        blocked_reason_code=blocked_reason,
        error_code=error_code,
        safe_error_message=safe_message,
        completed_at=NOW,
    )

    completed = module.complete_reflection_run(_record(), completion)

    assert completed.status is module.ReportReflectionStatus(target)
    assert completed.completed_at == NOW
    assert completed.total_finding_count == sum(counts)


def test_completion_rejects_inconsistent_counts_and_result_shape() -> None:
    module = _module()

    for updates in (
        {
            "target_status": module.ReportReflectionStatus.PASS,
            "total_finding_count": 1,
            "high_count": 1,
        },
        {
            "target_status": module.ReportReflectionStatus.FINDINGS,
            "total_finding_count": 0,
        },
        {
            "target_status": module.ReportReflectionStatus.BLOCKED,
            "total_finding_count": 0,
        },
        {
            "target_status": module.ReportReflectionStatus.FAILED,
            "total_finding_count": 0,
        },
    ):
        values = {
            "target_status": module.ReportReflectionStatus.PASS,
            "total_finding_count": 0,
            "critical_count": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
            "completed_at": NOW,
            **updates,
        }
        with pytest.raises(ValidationError):
            module.ReportReflectionCompletion.model_validate(values)


def test_terminal_run_is_frozen_and_cannot_transition_again() -> None:
    module = _module()
    terminal = _record(
        status=module.ReportReflectionStatus.PASS,
        completed_at=NOW,
    )

    with pytest.raises(module.ReportReflectionTransitionError):
        module.ReportReflectionStateMachine().transition(
            terminal.status,
            module.ReportReflectionStatus.FINDINGS,
        )
    with pytest.raises(ValidationError, match="Instance is frozen"):
        terminal.status = module.ReportReflectionStatus.RUNNING


def test_reflection_result_requires_exact_finding_count() -> None:
    module = _module()
    terminal = _record(
        status=module.ReportReflectionStatus.FINDINGS,
        total_finding_count=1,
        high_count=1,
        completed_at=NOW,
    )
    finding_id = UUID(int=99)

    result = module.ReportReflectionResult(
        run=terminal,
        finding_ids=(finding_id,),
    )
    assert result.finding_ids == (finding_id,)
    with pytest.raises(ValidationError):
        module.ReportReflectionResult(run=terminal, finding_ids=())
