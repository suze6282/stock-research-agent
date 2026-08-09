"""Explicit versioned Research Policy composition and seed behavior."""

from __future__ import annotations

from dataclasses import dataclass

from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.enums import ResearchSection, ResearchType
from stock_research_agent.domain.research_agent.repositories import ResearchPolicyRepository
from stock_research_agent.domain.research_agent.schemas import (
    AllowedTool,
    ResearchPolicyRecord,
    ResearchPolicyWrite,
)

CONTROLLED_OFFLINE_POLICY_VERSION = "controlled-offline-v1"
CONTROLLED_OFFLINE_TOOL_NAMES = (
    "get_calculation_run",
    "get_citation",
    "get_corporate_actions",
    "get_daily_price_history",
    "get_data_snapshot",
    "get_document_chunk",
    "get_document_metadata",
    "get_evidence_bundle",
    "get_financial_metrics",
    "get_financial_periods",
    "get_latest_close",
    "get_metric_detail",
    "get_metric_lineage",
    "get_normalized_financial_facts",
    "get_reported_financial_facts",
    "get_retrieval_run",
    "get_source_document_metadata",
    "list_document_versions",
    "list_snapshot_items",
    "list_source_documents",
    "search_document_chunks",
    "verify_citation",
)


class ResearchPolicyError(RuntimeError):
    """Fixed-code Policy failure without repository details."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PolicySeedResult:
    policy: ResearchPolicyRecord
    created: bool


def build_controlled_offline_policy() -> ResearchPolicyRecord:
    """Build the exact production-default Policy without consulting the Registry."""

    values = {
        "version": CONTROLLED_OFFLINE_POLICY_VERSION,
        "checksum": "0" * 64,
        "allowed_research_types": tuple(ResearchType),
        "allowed_sections": tuple(ResearchSection),
        "allowed_tools": tuple(
            AllowedTool(tool_name=name, tool_version="1.0.0")
            for name in CONTROLLED_OFFLINE_TOOL_NAMES
        ),
        "denied_tools": (),
        "max_steps": 12,
        "max_tool_calls": 24,
        "max_calls_per_tool": 5,
        "max_retries_per_step": 1,
        "max_duration_seconds": 120,
        "model_token_budget": 0,
        "require_snapshot": True,
        "require_as_of": True,
        "require_evidence_for_claims": True,
        "allow_synthetic_evidence": False,
        "allow_unknown_published_at": False,
        "allow_partial_completion": True,
        "reuse_partial_runs": False,
        "allow_model_planner": False,
        "allow_model_reasoner": False,
    }
    provisional = ResearchPolicyRecord.model_validate(values)
    values["checksum"] = stable_checksum(
        provisional.model_dump(mode="python", exclude={"checksum"})
    )
    return ResearchPolicyRecord.model_validate(values)


class ResearchPolicyService:
    def __init__(self, repository: ResearchPolicyRepository) -> None:
        self._repository = repository

    def require(self, version: str) -> ResearchPolicyRecord:
        policy = self._repository.get_policy(version)
        if policy is None:
            raise ResearchPolicyError("POLICY_NOT_FOUND")
        return policy


class ResearchPolicySeedService:
    def __init__(self, repository: ResearchPolicyRepository) -> None:
        self._repository = repository

    def seed_v1(self) -> PolicySeedResult:
        expected = build_controlled_offline_policy()
        existing = self._repository.get_policy(expected.version)
        if existing is not None:
            if existing.model_dump(mode="python") != expected.model_dump(mode="python"):
                raise ResearchPolicyError("POLICY_VERSION_CONFLICT")
            return PolicySeedResult(policy=existing, created=False)
        created = self._repository.add_policy(
            ResearchPolicyWrite.model_validate(expected.model_dump(mode="python"))
        )
        return PolicySeedResult(policy=created, created=True)
