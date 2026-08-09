from __future__ import annotations

import socket

import pytest

from stock_research_agent.config import ProviderNetworkMode, Settings
from stock_research_agent.providers.http_executor import (
    ControlledExecutionRequest,
    OfflineProviderTransport,
    ProviderTransportStatus,
)


class ExplodingCredential:
    def __getattribute__(self, name: str) -> object:
        raise AssertionError(f"credential was accessed: {name}")


def test_provider_network_mode_is_explicitly_offline_by_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.provider_network_mode is ProviderNetworkMode.OFFLINE
    assert settings.provider_network_enabled is False


def test_offline_transport_returns_structured_block_without_dns_socket_or_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DNS accessed")),
    )
    monkeypatch.setattr(
        socket,
        "socket",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("socket created")),
    )

    result = OfflineProviderTransport().send(
        ControlledExecutionRequest(request_id="REQUEST_001"),
        ExplodingCredential(),
    )
    assert result.status is ProviderTransportStatus.BLOCKED
    assert result.reason_code == "PROVIDER_NETWORK_OFFLINE"
    assert result.body is None


def test_network_enabled_requires_explicit_live_mode() -> None:
    with pytest.raises(ValueError, match="PROVIDER_NETWORK_MODE"):
        Settings(_env_file=None, provider_network_enabled=True)
