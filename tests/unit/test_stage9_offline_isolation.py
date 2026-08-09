from __future__ import annotations

import os
import socket
import tomllib
from pathlib import Path

import pytest

from stock_research_agent.config import Settings
from stock_research_agent.providers.http_executor import OfflineProviderTransport

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROVIDER_CREDENTIAL_ENV_NAMES = (
    "TUSHARE_TOKEN",
    "US_EOD_API_KEY",
    "SEC_CONTACT_EMAIL",
    "SEC_USER_AGENT",
)
PROVIDER_FIXTURE_LF_ATTRIBUTE = "tests/fixtures/providers/**/*.json text eol=lf"


def test_default_pytest_collection_is_tests_only_and_excludes_live_suite() -> None:
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_config = config["tool"]["pytest"]["ini_options"]

    assert pytest_config["testpaths"] == ["tests"]
    assert "tests_live" not in pytest_config["testpaths"]


def test_provider_fixture_json_is_pinned_to_lf_for_cross_platform_checksums() -> None:
    attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()

    assert attributes.count(PROVIDER_FIXTURE_LF_ATTRIBUTE) == 1


def test_default_fixture_removes_provider_credentials_and_live_switches() -> None:
    assert all(name not in os.environ for name in PROVIDER_CREDENTIAL_ENV_NAMES)
    assert "RUN_LIVE_PROVIDER_TESTS" not in os.environ
    assert "PROVIDER_NETWORK_ENABLED" not in os.environ


def test_default_socket_and_dns_guard_block_external_hosts_but_allow_literal_loopback() -> None:
    assert getattr(socket.socket, "_stock_research_offline_guard", False) is True
    with pytest.raises(AssertionError, match="DNS is disabled"):
        socket.getaddrinfo("example.com", 443)
    with socket.socket() as connection:
        with pytest.raises(AssertionError, match="non-loopback network"):
            connection.connect(("203.0.113.1", 443))
    assert socket.getaddrinfo("127.0.0.1", 55432)


def test_production_transport_and_model_capabilities_do_not_auto_enable() -> None:
    settings = Settings(_env_file=None)
    transport = OfflineProviderTransport()

    assert settings.provider_network_enabled is False
    assert transport.__class__.__name__ == "OfflineProviderTransport"
    serialized = repr(settings).casefold()
    assert "openai" not in serialized
    assert "anthropic" not in serialized
    assert "gemini" not in serialized


def test_live_suite_readme_requires_separate_exact_approval_and_finite_disclosure() -> None:
    text = (PROJECT_ROOT / "tests_live" / "providers" / "README.md").read_text(encoding="utf-8")

    assert "批准执行该Provider的有限Live验证" in text
    assert "not run by default pytest" in text.casefold()
    assert "not run by default ci" in text.casefold()
    for term in (
        "provider",
        "official domains",
        "capability",
        "request budget",
        "byte budget",
        "credential reference",
        "license",
        "cost",
        "duration",
        "rollback",
    ):
        assert term in text.casefold()
    assert "SEC approval does not authorize Tushare" in text
