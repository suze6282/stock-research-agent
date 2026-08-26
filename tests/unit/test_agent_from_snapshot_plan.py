from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from stock_research_agent.domain.live_evidence.offline_pipeline import (
    OfflineAgentPlanRequest,
    OfflinePipelineRegistry,
)
from stock_research_agent.domain.research_agent.enums import ResearchType

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _request(**changes: object) -> OfflineAgentPlanRequest:
    values: dict[str, object] = {
        "snapshot_id": UUID("00000000-0000-0000-0000-000000000001"),
        "snapshot_checksum": "a" * 64,
        "snapshot_status": "COMPLETE",
        "security_id": UUID("00000000-0000-0000-0000-000000000002"),
        "research_as_of_time": NOW,
        "research_type": ResearchType.DATA_QUALITY_REVIEW,
        "policy_version": "research-policy-v1",
        "policy_checksum": "b" * 64,
        "approved_policy_version": "research-policy-v1",
        "approved_policy_checksum": "b" * 64,
        "tool_catalog_version": "tool-catalog-v1:sha256:" + "c" * 57,
        "tool_catalog_checksum": "c" * 64,
        "planner_version": "deterministic-template-v1",
    }
    values.update(changes)
    return OfflineAgentPlanRequest.model_validate(values)


def _registry() -> OfflinePipelineRegistry:
    return OfflinePipelineRegistry(
        registry_id="OFFLINE_PIPELINE_REGISTRY",
        registry_version="1.0.0",
        registry_checksum="f" * 64,
    )


def test_explicit_snapshot_policy_and_catalog_produce_stable_ready_plan() -> None:
    first = _registry().plan_agent(_request())
    second = _registry().plan_agent(_request())

    assert first.status == "READY"
    assert first.plan_checksum == second.plan_checksum
    assert first.snapshot_id == _request().snapshot_id
    assert first.security_id == _request().security_id
    assert first.research_as_of_time == NOW


def test_partial_snapshot_produces_partial_plan_without_latest_shortcut() -> None:
    plan = _registry().plan_agent(_request(snapshot_status="PARTIAL"))

    assert plan.status == "PARTIAL"
    assert plan.warning_codes == ("AGENT_SNAPSHOT_PARTIAL",)
    assert "latest" not in plan.model_dump()


def test_unsealed_snapshot_is_blocked() -> None:
    plan = _registry().plan_agent(_request(snapshot_status="BUILDING"))

    assert plan.status == "BLOCKED"
    assert plan.warning_codes == ("AGENT_SNAPSHOT_NOT_SEALED",)


def test_policy_version_or_checksum_mismatch_is_blocked() -> None:
    version = _registry().plan_agent(_request(approved_policy_version="research-policy-v2"))
    checksum = _registry().plan_agent(_request(approved_policy_checksum="d" * 64))

    assert version.warning_codes == ("AGENT_POLICY_MISMATCH",)
    assert checksum.warning_codes == ("AGENT_POLICY_MISMATCH",)
