from __future__ import annotations

import inspect

import pytest

from stock_research_agent.domain.reports.providers import (
    BlockedModelNarrativeProvider,
    BlockedModelReflectionProvider,
    NarrativeProvider,
    ProviderAvailability,
    ProviderClassification,
    ReflectionProvider,
    ReportProviderBlockedError,
    ReportReflectionContext,
    ReportRenderContext,
)


@pytest.mark.parametrize(
    "provider",
    (
        BlockedModelNarrativeProvider(),
        BlockedModelReflectionProvider(),
    ),
)
def test_production_model_report_providers_are_unconditionally_blocked(
    provider: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-enable")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-enable")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-enable")

    metadata = provider.metadata
    health = provider.validate_configuration()
    assert metadata.classification is ProviderClassification.MODEL
    assert metadata.production_default is False
    assert metadata.requires_network is False
    assert metadata.model_token_budget == 0
    assert health.status is ProviderAvailability.BLOCKED
    assert health.consumed_model_tokens == 0


def test_blocked_model_ports_raise_without_inspecting_context() -> None:
    with pytest.raises(ReportProviderBlockedError, match="MODEL_NARRATIVE_PROVIDER_BLOCKED"):
        BlockedModelNarrativeProvider().render_candidate_blocks(
            ReportRenderContext.model_construct()
        )
    with pytest.raises(ReportProviderBlockedError, match="MODEL_REFLECTION_PROVIDER_BLOCKED"):
        BlockedModelReflectionProvider().propose_findings(ReportReflectionContext.model_construct())


def test_provider_module_has_no_model_network_or_environment_runtime() -> None:
    import stock_research_agent.domain.reports.providers as module

    source = inspect.getsource(module).casefold()
    for prohibited in (
        "import openai",
        "import anthropic",
        "import google.generativeai",
        "import requests",
        "import httpx",
        "urlopen(",
        "os.environ",
        "getenv(",
    ):
        assert prohibited not in source
    assert isinstance(BlockedModelNarrativeProvider(), NarrativeProvider)
    assert isinstance(BlockedModelReflectionProvider(), ReflectionProvider)
