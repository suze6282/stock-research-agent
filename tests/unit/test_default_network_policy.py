from __future__ import annotations

import socket
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_default_network_policy_blocks_external_dns_and_ip_connections() -> None:
    assert getattr(socket.socket, "_stock_research_offline_guard", False) is True

    with pytest.raises(AssertionError, match="DNS is disabled"):
        socket.getaddrinfo("example.invalid", 443)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        with pytest.raises(AssertionError, match="non-loopback network access is disabled"):
            client.connect(("192.0.2.1", 443))


def test_default_pytest_collection_excludes_live_tests_and_declares_live_marker() -> None:
    configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_options = configuration["tool"]["pytest"]["ini_options"]

    assert pytest_options["testpaths"] == ["tests"]
    assert any(str(marker).startswith("live:") for marker in pytest_options["markers"])


def test_live_smoke_harness_exists_outside_default_testpaths() -> None:
    live_test = PROJECT_ROOT / "live_tests" / "test_provider_smoke.py"

    assert live_test.is_file()
    assert PROJECT_ROOT / "live_tests" not in tuple(
        PROJECT_ROOT / path
        for path in tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
            "tool"
        ]["pytest"]["ini_options"]["testpaths"]
    )


def test_default_ci_forces_offline_provider_policy_and_never_invokes_live_suite() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "backend-ci.yml").read_text(
        encoding="utf-8"
    )

    assert 'PROVIDER_NETWORK_ENABLED: "false"' in workflow
    assert "RUN_LIVE_PROVIDER_TESTS" not in workflow
    assert "live_tests" not in workflow
