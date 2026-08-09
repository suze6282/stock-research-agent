import socket
from collections.abc import Iterator
from ipaddress import ip_address

import pytest
from pytest import MonkeyPatch


def _is_loopback_host(host: object) -> bool:
    if isinstance(host, bytes):
        try:
            host = host.decode("ascii")
        except UnicodeDecodeError:
            return False
    if not isinstance(host, str):
        return False
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _require_loopback_address(address: object) -> None:
    if isinstance(address, tuple) and address and _is_loopback_host(address[0]):
        return
    raise AssertionError("non-loopback network access is disabled during default pytest")


@pytest.fixture(autouse=True)
def block_non_loopback_network(monkeypatch: MonkeyPatch) -> Iterator[None]:
    """Keep default tests offline while preserving literal loopback for PostgreSQL."""
    original_socket = socket.socket
    original_getaddrinfo = socket.getaddrinfo

    class _OfflineGuardedSocket(original_socket):
        _stock_research_offline_guard = True

        def connect(self, address: object) -> None:
            _require_loopback_address(address)
            return super().connect(address)

        def connect_ex(self, address: object) -> int:
            _require_loopback_address(address)
            return super().connect_ex(address)

        def sendto(self, data: bytes, *args: object) -> int:
            if not args:
                raise AssertionError("network destination is required")
            _require_loopback_address(args[-1])
            return super().sendto(data, *args)

    def guarded_getaddrinfo(
        host: object,
        port: object,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[int, int, int, str, tuple[object, ...]]]:
        if not _is_loopback_host(host):
            raise AssertionError("DNS is disabled during default pytest")
        return original_getaddrinfo(host, port, family, type, proto, flags)

    def blocked_dns(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("DNS is disabled during default pytest")

    blocked_dns._stock_research_offline_guard = True

    monkeypatch.setattr(socket, "socket", _OfflineGuardedSocket)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket, "gethostbyname", blocked_dns)
    monkeypatch.setattr(socket, "gethostbyname_ex", blocked_dns)
    monkeypatch.setattr(socket, "gethostbyaddr", blocked_dns)
    monkeypatch.setattr(socket, "getnameinfo", blocked_dns)
    yield


@pytest.fixture(autouse=True)
def clear_settings_environment(monkeypatch: MonkeyPatch) -> Iterator[None]:
    settings_keys = (
        "APP_NAME",
        "APP_ENV",
        "APP_DEBUG",
        "APP_HOST",
        "APP_PORT",
        "LOG_LEVEL",
        "DATABASE_URL",
        "DATABASE_ECHO",
        "API_PREFIX",
        "PROVIDER_NETWORK_ENABLED",
        "PROVIDER_CONNECT_TIMEOUT_SECONDS",
        "PROVIDER_READ_TIMEOUT_SECONDS",
        "PROVIDER_TOTAL_TIMEOUT_SECONDS",
        "PROVIDER_MAX_RESPONSE_BYTES",
        "PROVIDER_MAX_REDIRECTS",
        "PROVIDER_MAX_ATTEMPTS",
        "PROVIDER_RETRY_BASE_DELAY_SECONDS",
        "PROVIDER_RATE_LIMIT_PER_SECOND",
        "PROVIDER_USER_AGENT",
        "BLOB_STORAGE_ROOT",
        "RUN_LIVE_PROVIDER_TESTS",
        "TUSHARE_TOKEN",
        "TUSHARE_CACHE_PERMISSION_CONFIRMED",
        "US_EOD_API_KEY",
        "US_EOD_LICENSE_CONFIRMED",
        "US_EOD_PROVIDER_CODE",
        "SEC_CONTACT_EMAIL",
        "SEC_USER_AGENT",
    )
    for key in settings_keys:
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.lower(), raising=False)
    yield
