from __future__ import annotations

import socket

import pytest


def _assert_global_guard_is_active() -> None:
    assert getattr(socket.socket, "_stock_research_offline_guard", False) is True


def test_default_suite_blocks_dns_before_resolution() -> None:
    _assert_global_guard_is_active()

    with pytest.raises(AssertionError, match="DNS is disabled"):
        socket.getaddrinfo("example.invalid", 443)


def test_default_suite_blocks_legacy_dns_helpers() -> None:
    _assert_global_guard_is_active()
    assert getattr(socket.gethostbyname, "_stock_research_offline_guard", False) is True

    with pytest.raises(AssertionError, match="DNS is disabled"):
        socket.gethostbyname("example.invalid")


def test_default_suite_blocks_non_loopback_connect_before_network() -> None:
    _assert_global_guard_is_active()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        with pytest.raises(AssertionError, match="non-loopback network access is disabled"):
            client.connect(("192.0.2.1", 443))


def test_default_suite_preserves_ipv4_loopback_sockets() -> None:
    _assert_global_guard_is_active()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect(server.getsockname())
            connection, _address = server.accept()
            connection.close()


def test_default_suite_preserves_ipv6_loopback_resolution() -> None:
    _assert_global_guard_is_active()

    addresses = socket.getaddrinfo("::1", 0, socket.AF_INET6, socket.SOCK_STREAM)

    assert addresses
    assert all(address[-1][0] == "::1" for address in addresses)
