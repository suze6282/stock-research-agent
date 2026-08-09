from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

MODULE = "stock_research_agent.domain.research_agent.providers"
SOURCE = Path("src/stock_research_agent/domain/research_agent/providers.py")
SCRIPTED_SOURCE = Path("tests/support/research_agent_providers.py")


def _providers() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def test_production_factories_are_deterministic_offline_and_model_free() -> None:
    providers = _providers()

    planner = providers.create_production_planner()
    reasoner = providers.create_production_reasoner()

    assert planner.metadata.provider_type == "DETERMINISTIC_TEMPLATE"
    assert reasoner.metadata.provider_type == "DETERMINISTIC_RULES"
    for provider in (planner, reasoner):
        assert provider.metadata.test_only is False
        assert provider.metadata.requires_network is False
        assert provider.metadata.uses_model is False
        assert provider.validate_configuration().status == "READY"


def test_model_providers_are_explicitly_blocked_and_never_auto_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _providers()
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-enable")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-enable")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-enable")

    planner = providers.BlockedModelPlannerProvider()
    reasoner = providers.BlockedModelReasoningProvider()

    assert planner.validate_configuration().status == "BLOCKED"
    assert reasoner.validate_configuration().status == "BLOCKED"
    with pytest.raises(providers.ProviderUnavailableError) as planner_error:
        planner.create_plan(None, None, None)
    with pytest.raises(providers.ProviderUnavailableError) as reasoner_error:
        reasoner.propose_claims(None, None)
    assert planner_error.value.code == "MODEL_PROVIDER_NOT_CONFIGURED"
    assert reasoner_error.value.code == "MODEL_PROVIDER_NOT_CONFIGURED"


def test_production_provider_module_has_no_model_sdk_or_test_provider_import() -> None:
    text = SOURCE.read_text(encoding="utf-8").lower()

    for forbidden in (
        "openai",
        "anthropic",
        "gemini",
        "scriptedtest",
        "tests.support",
        "httpx",
        "requests.",
    ):
        assert forbidden not in text


def test_scripted_providers_exist_only_in_test_support_and_are_marked_test_only() -> None:
    assert SCRIPTED_SOURCE.exists()
    spec = importlib.util.spec_from_file_location("scripted_research_providers", SCRIPTED_SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    planner = module.ScriptedTestPlanner(None)
    reasoner = module.ScriptedTestReasoner(())
    assert planner.metadata.provider_type == "SCRIPTED_TEST"
    assert reasoner.metadata.provider_type == "SCRIPTED_TEST"
    assert planner.metadata.test_only is True
    assert reasoner.metadata.test_only is True
