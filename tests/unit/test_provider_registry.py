from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from stock_research_agent.domain.data_access.enums import (
    ProviderCapability,
    ProviderStatus,
)
from stock_research_agent.domain.data_access.schemas import (
    ProviderDescriptor,
    ProviderEnvelope,
    ProviderRequest,
)
from stock_research_agent.providers.base import DataProviderAdapter
from stock_research_agent.providers.errors import (
    DuplicateProviderError,
    MissingProviderCapabilityError,
    ProviderContractError,
    ProviderCredentialsNotConfiguredError,
    ProviderDisabledError,
    ProviderNotAllowedError,
    ProviderNotFoundError,
)
from stock_research_agent.providers.registry import ProviderRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _descriptor(
    code: str,
    *,
    version: str = "1.0.0",
    status: ProviderStatus = ProviderStatus.APPROVED,
    capabilities: frozenset[ProviderCapability] = frozenset({ProviderCapability.DAILY_PRICES}),
    is_enabled: bool = True,
    requires_credentials: bool = False,
    credentials_configured: bool = False,
) -> ProviderDescriptor:
    return ProviderDescriptor(
        code=code,
        name=f"{code} provider",
        version=version,
        status=status,
        capabilities=capabilities,
        is_enabled=is_enabled,
        requires_credentials=requires_credentials,
        credentials_configured=credentials_configured,
    )


@dataclass
class _Adapter:
    descriptor: ProviderDescriptor
    code: str | None = None
    version: str | None = None
    capabilities: frozenset[ProviderCapability] | None = None
    fetch_calls: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.code is None:
            self.code = self.descriptor.code
        if self.version is None:
            self.version = self.descriptor.version
        if self.capabilities is None:
            self.capabilities = self.descriptor.capabilities

    def fetch(self, request: ProviderRequest) -> ProviderEnvelope:
        self.fetch_calls += 1
        raise AssertionError("registry metadata operations must not invoke fetch")


def test_adapter_contract_is_a_protocol_with_the_approved_surface() -> None:
    assert DataProviderAdapter.__dict__["_is_protocol"] is True
    assert DataProviderAdapter.__annotations__ == {
        "code": "str",
        "version": "str",
        "capabilities": "frozenset[ProviderCapability]",
        "descriptor": "ProviderDescriptor",
    }
    assert callable(DataProviderAdapter.__dict__["fetch"])


def test_registry_registers_gets_lists_and_describes_without_fetching() -> None:
    registry = ProviderRegistry()
    adapter = _Adapter(_descriptor("OFFLINE_FIXTURE"))

    registry.register(adapter)  # type: ignore[arg-type]

    assert registry.get("OFFLINE_FIXTURE") is adapter
    assert registry.describe("OFFLINE_FIXTURE") is adapter.descriptor
    assert registry.list() == (adapter.descriptor,)
    assert adapter.fetch_calls == 0


def test_registry_list_is_sorted_and_does_not_enforce_runtime_availability() -> None:
    registry = ProviderRegistry()
    second = _Adapter(
        _descriptor(
            "Z_DISABLED",
            status=ProviderStatus.NOT_ALLOWED,
            is_enabled=False,
            requires_credentials=True,
            credentials_configured=False,
        )
    )
    first = _Adapter(_descriptor("A_READY"))

    registry.register(second)  # type: ignore[arg-type]
    registry.register(first)  # type: ignore[arg-type]

    assert registry.list() == (first.descriptor, second.descriptor)
    assert registry.describe("Z_DISABLED") is second.descriptor
    assert first.fetch_calls == second.fetch_calls == 0


def test_registry_rejects_duplicate_code_before_replacing_adapter() -> None:
    registry = ProviderRegistry()
    first = _Adapter(_descriptor("DUPLICATE"))
    duplicate = _Adapter(_descriptor("DUPLICATE", version="2.0.0"))
    registry.register(first)  # type: ignore[arg-type]

    with pytest.raises(DuplicateProviderError, match="DUPLICATE"):
        registry.register(duplicate)  # type: ignore[arg-type]

    assert registry.get("DUPLICATE") is first
    assert first.fetch_calls == duplicate.fetch_calls == 0


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("code", "DIFFERENT"),
        ("version", "2.0.0"),
        ("capabilities", frozenset({ProviderCapability.FINANCIAL_FACTS})),
    ],
)
def test_registration_rejects_adapter_values_that_disagree_with_descriptor(
    override: str,
    value: object,
) -> None:
    registry = ProviderRegistry()
    adapter = _Adapter(_descriptor("MISMATCH"))
    setattr(adapter, override, value)

    with pytest.raises(ProviderContractError, match=override):
        registry.register(adapter)  # type: ignore[arg-type]

    assert registry.list() == ()
    assert adapter.fetch_calls == 0


def test_get_rejects_unknown_provider() -> None:
    with pytest.raises(ProviderNotFoundError, match="MISSING"):
        ProviderRegistry().get("MISSING")


def test_get_rejects_disabled_provider_but_describe_remains_available() -> None:
    registry = ProviderRegistry()
    adapter = _Adapter(_descriptor("DISABLED", is_enabled=False))
    registry.register(adapter)  # type: ignore[arg-type]

    with pytest.raises(ProviderDisabledError, match="DISABLED"):
        registry.get("DISABLED")

    assert registry.describe("DISABLED") is adapter.descriptor
    assert adapter.fetch_calls == 0


def test_get_rejects_not_allowed_provider() -> None:
    registry = ProviderRegistry()
    adapter = _Adapter(_descriptor("DENIED", status=ProviderStatus.NOT_ALLOWED))
    registry.register(adapter)  # type: ignore[arg-type]

    with pytest.raises(ProviderNotAllowedError, match="DENIED"):
        registry.get("DENIED")

    assert adapter.fetch_calls == 0


def test_get_rejects_missing_required_capability() -> None:
    registry = ProviderRegistry()
    adapter = _Adapter(_descriptor("PRICE_ONLY"))
    registry.register(adapter)  # type: ignore[arg-type]

    with pytest.raises(MissingProviderCapabilityError, match="FINANCIAL_FACTS"):
        registry.get("PRICE_ONLY", ProviderCapability.FINANCIAL_FACTS)

    assert adapter.fetch_calls == 0


def test_get_accepts_declared_required_capability() -> None:
    registry = ProviderRegistry()
    adapter = _Adapter(_descriptor("PRICE_READY"))
    registry.register(adapter)  # type: ignore[arg-type]

    assert registry.get("PRICE_READY", ProviderCapability.DAILY_PRICES) is adapter
    assert adapter.fetch_calls == 0


def test_get_rejects_provider_with_missing_required_credentials() -> None:
    registry = ProviderRegistry()
    adapter = _Adapter(
        _descriptor(
            "AUTH_REQUIRED",
            status=ProviderStatus.NEEDS_CREDENTIALS,
            requires_credentials=True,
            credentials_configured=False,
        )
    )
    registry.register(adapter)  # type: ignore[arg-type]

    with pytest.raises(ProviderCredentialsNotConfiguredError, match="AUTH_REQUIRED"):
        registry.get("AUTH_REQUIRED")

    assert adapter.fetch_calls == 0


def test_get_allows_provider_when_required_credentials_are_configured() -> None:
    registry = ProviderRegistry()
    adapter = _Adapter(
        _descriptor(
            "AUTH_READY",
            requires_credentials=True,
            credentials_configured=True,
        )
    )
    registry.register(adapter)  # type: ignore[arg-type]

    assert registry.get("AUTH_READY") is adapter
    assert adapter.fetch_calls == 0


def test_data_access_imports_open_no_runtime_resources_or_heavy_boundaries() -> None:
    script = r"""
import builtins
import importlib
import json
import os
import pathlib
import socket
import sys

os.environ["PYDANTIC_DISABLE_PLUGINS"] = "caller-requested-plugin"

def blocked(*args, **kwargs):
    raise AssertionError("runtime I/O attempted during import")

builtins.open = blocked
pathlib.Path.open = blocked
socket.create_connection = blocked
socket.socket.connect = blocked

before = set(sys.modules)
for name in (
    "stock_research_agent.domain.data_access.enums",
    "stock_research_agent.domain.data_access.schemas",
    "stock_research_agent.domain.data_access.repositories",
    "stock_research_agent.providers.base",
    "stock_research_agent.providers.capabilities",
    "stock_research_agent.providers.errors",
    "stock_research_agent.providers.registry",
):
    importlib.import_module(name)

loaded = set(sys.modules) - before
forbidden = sorted(
    name for name in loaded
    if name.split(".", 1)[0] in {
        "alembic", "fastapi", "httpx", "psycopg", "requests", "sqlalchemy", "urllib3"
    }
)
print(json.dumps({
    "forbidden": forbidden,
    "pydantic_disable_plugins": os.environ["PYDANTIC_DISABLE_PLUGINS"],
}))
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "forbidden": [],
        "pydantic_disable_plugins": "__all__",
    }
