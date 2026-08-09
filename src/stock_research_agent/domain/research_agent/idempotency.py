"""Semantic idempotency for controlled Research Runs."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.enums import (
    ResearchRunStatus,
    ResearchSection,
    ResearchType,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchAgentRunRecord,
    ResearchPolicyRecord,
)

_REUSABLE = frozenset(
    {
        ResearchRunStatus.CREATED,
        ResearchRunStatus.PLANNING,
        ResearchRunStatus.PLANNED,
        ResearchRunStatus.RUNNING,
        ResearchRunStatus.PAUSED,
        ResearchRunStatus.COMPLETED,
    }
)


def research_run_idempotency_key(
    *,
    normalized_request: str,
    security_id: UUID,
    snapshot_id: UUID,
    research_as_of_time: datetime,
    research_type: ResearchType,
    requested_sections: Sequence[ResearchSection],
    policy_version: str,
    planner_version: str,
    tool_catalog_checksum: str,
) -> str:
    """Hash every semantic input while excluding unique audit metadata."""

    return stable_checksum(
        {
            "normalized_request": normalized_request,
            "security_id": security_id,
            "snapshot_id": snapshot_id,
            "research_as_of_time": research_as_of_time,
            "research_type": research_type,
            "requested_sections": tuple(requested_sections),
            "policy_version": policy_version,
            "planner_version": planner_version,
            "tool_catalog_checksum": tool_catalog_checksum,
        }
    )


def is_reusable_run(
    run: ResearchAgentRunRecord,
    policy: ResearchPolicyRecord,
) -> bool:
    """Apply exact Policy version and explicit terminal reuse rules."""

    if run.policy_version != policy.version:
        return False
    if run.status in _REUSABLE:
        return True
    return run.status is ResearchRunStatus.PARTIAL and policy.reuse_partial_runs is True
