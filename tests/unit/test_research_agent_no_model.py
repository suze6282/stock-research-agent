from __future__ import annotations

import importlib.util

import pytest

from stock_research_agent.domain.research_agent.enums import ProviderHealthStatus
from stock_research_agent.domain.research_agent.policies import (
    build_controlled_offline_policy,
)
from stock_research_agent.domain.research_agent.providers import (
    BlockedModelPlannerProvider,
    BlockedModelReasoningProvider,
    DeterministicPlannerProvider,
    DeterministicReasoningProvider,
    create_production_planner,
    create_production_reasoner,
)


def test_production_factories_ignore_model_environment_and_remain_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "MODEL_PROVIDER",
    ):
        monkeypatch.setenv(name, "must-not-enable")

    planner = create_production_planner()
    reasoner = create_production_reasoner()

    assert isinstance(planner, DeterministicPlannerProvider)
    assert isinstance(reasoner, DeterministicReasoningProvider)
    assert planner.metadata.uses_model is False
    assert reasoner.metadata.uses_model is False
    assert planner.metadata.requires_network is False
    assert reasoner.metadata.requires_network is False
    assert build_controlled_offline_policy().model_token_budget == 0


def test_model_providers_are_explicitly_blocked_and_never_network_ready() -> None:
    planner = BlockedModelPlannerProvider()
    reasoner = BlockedModelReasoningProvider()

    assert planner.validate_configuration().status is ProviderHealthStatus.BLOCKED
    assert reasoner.validate_configuration().status is ProviderHealthStatus.BLOCKED
    assert planner.metadata.requires_network is False
    assert reasoner.metadata.requires_network is False


@pytest.mark.parametrize("package", ("openai", "anthropic", "google.generativeai"))
def test_stage7_installs_no_model_client_package(package: str) -> None:
    try:
        spec = importlib.util.find_spec(package)
    except ModuleNotFoundError:
        spec = None
    assert spec is None
