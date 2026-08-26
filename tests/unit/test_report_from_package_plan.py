from __future__ import annotations

from uuid import UUID

from stock_research_agent.domain.live_evidence.offline_pipeline import (
    OfflinePipelineRegistry,
    OfflineReportPlanRequest,
)


def _request(**changes: object) -> OfflineReportPlanRequest:
    values: dict[str, object] = {
        "package_id": UUID(int=1),
        "package_checksum": "a" * 64,
        "package_status": "COMPLETE",
        "run_id": UUID(int=2),
        "snapshot_id": UUID(int=3),
        "security_id": UUID(int=4),
        "policy_version": "controlled-offline-v1",
        "policy_checksum": "b" * 64,
        "template_version": "deterministic-report-v1",
        "template_checksum": "c" * 64,
        "reflection_policy_version": "deterministic-reflection-v1",
        "reflection_policy_checksum": "d" * 64,
        "manifest_checksum": "e" * 64,
        "approved_manifest_checksum": "e" * 64,
    }
    values.update(changes)
    return OfflineReportPlanRequest.model_validate(values)


def _registry() -> OfflinePipelineRegistry:
    return OfflinePipelineRegistry(
        registry_id="OFFLINE_PIPELINE_REGISTRY",
        registry_version="1.0.0",
        registry_checksum="f" * 64,
    )


def test_sealed_package_produces_stable_report_plan() -> None:
    first = _registry().plan_report(_request())
    second = _registry().plan_report(_request())

    assert first.status == "READY"
    assert first.plan_checksum == second.plan_checksum
    assert first.package_id == UUID(int=1)
    assert first.snapshot_id == UUID(int=3)


def test_unsealed_package_and_invalid_manifest_fail_closed() -> None:
    unsealed = _registry().plan_report(_request(package_status="BUILDING"))
    invalid = _registry().plan_report(_request(approved_manifest_checksum="0" * 64))

    assert unsealed.status == "BLOCKED"
    assert unsealed.warning_codes == ("REPORT_PACKAGE_NOT_SEALED",)
    assert invalid.status == "BLOCKED"
    assert invalid.warning_codes == ("REPORT_MANIFEST_INVALID",)
