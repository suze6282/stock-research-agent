from __future__ import annotations

import importlib
import importlib.util

import pytest

MODULE = "stock_research_agent.domain.research_agent.policies"
EXPECTED_ALLOWED_TOOLS = (
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


class MemoryPolicyRepository:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.add_count = 0

    def get_policy(self, version: str) -> object | None:
        return self.values.get(version)

    def add_policy(self, value: object) -> object:
        self.add_count += 1
        version = value.version
        if version in self.values:
            raise AssertionError("seed attempted a duplicate insert")
        self.values[version] = value
        return value


def _policies() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def test_controlled_offline_policy_has_exact_allowlist_and_hard_limits() -> None:
    policies = _policies()

    policy = policies.build_controlled_offline_policy()

    assert policy.version == "controlled-offline-v1"
    assert tuple(item.tool_name for item in policy.allowed_tools) == EXPECTED_ALLOWED_TOOLS
    assert all(item.tool_version == "1.0.0" for item in policy.allowed_tools)
    assert policy.max_steps == 12
    assert policy.max_tool_calls == 24
    assert policy.max_calls_per_tool == 5
    assert policy.max_retries_per_step == 1
    assert policy.max_duration_seconds == 120
    assert policy.model_token_budget == 0
    assert policy.allow_synthetic_evidence is False
    assert policy.allow_model_planner is False
    assert policy.allow_model_reasoner is False
    assert policy.reuse_partial_runs is False
    assert len(policy.checksum) == 64


def test_policy_seed_is_idempotent_and_does_not_overwrite() -> None:
    policies = _policies()
    repository = MemoryPolicyRepository()
    service = policies.ResearchPolicySeedService(repository)

    first = service.seed_v1()
    second = service.seed_v1()

    assert first.created is True
    assert second.created is False
    assert first.policy == second.policy
    assert repository.add_count == 1


def test_policy_seed_rejects_incompatible_existing_version() -> None:
    policies = _policies()
    repository = MemoryPolicyRepository()
    expected = policies.build_controlled_offline_policy()
    repository.values[expected.version] = expected.model_copy(update={"checksum": "f" * 64})

    with pytest.raises(policies.ResearchPolicyError) as raised:
        policies.ResearchPolicySeedService(repository).seed_v1()

    assert raised.value.code == "POLICY_VERSION_CONFLICT"
    assert repository.add_count == 0


def test_policy_service_requires_exact_version() -> None:
    policies = _policies()
    repository = MemoryPolicyRepository()
    service = policies.ResearchPolicyService(repository)

    with pytest.raises(policies.ResearchPolicyError) as raised:
        service.require("unknown-policy-v1")

    assert raised.value.code == "POLICY_NOT_FOUND"
