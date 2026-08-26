from __future__ import annotations

from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.offline_pipeline import (
    OfflinePipelineRegistry,
    OfflineReportExecutionResult,
    OfflineReportPlan,
    OfflineReportPlanRequest,
)


def _registry() -> OfflinePipelineRegistry:
    return OfflinePipelineRegistry(
        registry_id="OFFLINE_PIPELINE_REGISTRY",
        registry_version="1.0.0",
        registry_checksum="f" * 64,
    )


def _plan() -> OfflineReportPlan:
    return _registry().plan_report(
        OfflineReportPlanRequest(
            package_id=UUID(int=1),
            package_checksum="a" * 64,
            package_status="COMPLETE",
            run_id=UUID(int=2),
            snapshot_id=UUID(int=3),
            security_id=UUID(int=4),
            policy_version="controlled-offline-v1",
            policy_checksum="b" * 64,
            template_version="deterministic-report-v1",
            template_checksum="c" * 64,
            reflection_policy_version="deterministic-reflection-v1",
            reflection_policy_checksum="d" * 64,
            manifest_checksum="e" * 64,
            approved_manifest_checksum="e" * 64,
        )
    )


class _ExistingReportPipeline:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def generate(self, plan: OfflineReportPlan) -> OfflineReportExecutionResult:
        self.calls += 1
        if self.fail:
            raise RuntimeError("internal report failure")
        return OfflineReportExecutionResult(
            report_request_id=UUID(int=5),
            generation_run_id=UUID(int=6),
            report_id=UUID(int=7),
            reflection_run_ids=(UUID(int=8), UUID(int=9)),
            release_gate_id=UUID(int=10),
            status="PARTIAL",
            package_id=plan.package_id,
            snapshot_id=plan.snapshot_id,
            security_id=plan.security_id,
        )


def test_sealed_plan_delegates_once_to_existing_deterministic_pipeline() -> None:
    executor = _ExistingReportPipeline()

    result = _registry().generate_report(_plan(), executor=executor)

    assert executor.calls == 1
    assert result.status == "PARTIAL"
    assert result.package_id == UUID(int=1)
    assert result.reflection_run_ids == (UUID(int=8), UUID(int=9))


def test_tamper_or_pipeline_failure_is_blocked_with_safe_code() -> None:
    executor = _ExistingReportPipeline()
    with pytest.raises(LiveEvidenceValidationError) as mismatch:
        _registry().generate_report(
            _plan().model_copy(update={"plan_checksum": "0" * 64}),
            executor=executor,
        )
    assert mismatch.value.code == "REPORT_PLAN_CHECKSUM_MISMATCH"
    assert executor.calls == 0

    with pytest.raises(LiveEvidenceValidationError) as blocked:
        _registry().generate_report(_plan(), executor=_ExistingReportPipeline(fail=True))
    assert blocked.value.code == "REPORT_PIPELINE_BLOCKED"
