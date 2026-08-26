from __future__ import annotations

import importlib
import socket

import pytest


@pytest.mark.parametrize(
    "module_name",
    (
        "stock_research_agent.cli_live",
        "stock_research_agent.cli_evidence",
        "stock_research_agent.cli_snapshot_ingestion",
        "stock_research_agent.cli_research_pipeline",
        "stock_research_agent.domain.live_evidence.offline_pipeline",
        "stock_research_agent.domain.live_evidence.validation",
        "stock_research_agent.domain.live_evidence.retention",
        "stock_research_agent.domain.live_evidence.incidents",
        "stock_research_agent.api.routes.live_evidence",
    ),
)
def test_stage10_entrypoints_import_without_network_credentials_or_provider_transport(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Stage 10 Gate A attempted network access")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    module = importlib.import_module(module_name)
    importlib.reload(module)
    assert module is not None


def test_gate_a_modules_do_not_name_credential_resolvers_or_model_clients() -> None:
    modules = (
        "stock_research_agent.cli_live",
        "stock_research_agent.domain.live_evidence.offline_pipeline",
    )
    for module_name in modules:
        source = importlib.import_module(module_name).__dict__
        names = {name.casefold() for name in source}
        assert "credential_resolver" not in names
        assert "openai" not in names
        assert "anthropic" not in names
