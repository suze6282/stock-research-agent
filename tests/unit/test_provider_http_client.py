from __future__ import annotations

import importlib
import ipaddress
import math
import threading
import time
import urllib.parse
from collections.abc import Iterator
from concurrent.futures import Future

import httpx
import pytest

import stock_research_agent.providers.http_client as http_client_module
from stock_research_agent.providers.cache import InMemoryResponseCache
from stock_research_agent.providers.http_client import (
    HttpClientPolicy,
    HttpRequest,
    SafeHttpClient,
)


class _RecordingRateLimiter:
    def __init__(self) -> None:
        self.buckets: list[str] = []

    def acquire(self, bucket: str) -> None:
        self.buckets.append(bucket)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class _UnreadableStream(httpx.SyncByteStream):
    def __iter__(self) -> Iterator[bytes]:
        raise AssertionError("redirect response body must not be read")


class _ChunksStream(httpx.SyncByteStream):
    def __init__(self, *chunks: bytes) -> None:
        self._chunks = chunks

    def __iter__(self) -> Iterator[bytes]:
        yield from self._chunks


class _CloseRecordingTransport(httpx.BaseTransport):
    def __init__(self) -> None:
        self.closed = False

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok", request=request)

    def close(self) -> None:
        self.closed = True


class _FailingCloseTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok", request=request)

    def close(self) -> None:
        raise httpx.CloseError("close-secret")


def test_in_memory_response_cache_returns_the_stored_response() -> None:
    module = importlib.import_module("stock_research_agent.providers.cache")
    cache = module.InMemoryResponseCache()
    response = module.CachedResponse(
        body=b"payload",
        content_type="application/json",
        etag='"v1"',
        last_modified="Tue, 14 Jul 2026 08:00:00 GMT",
    )

    assert cache.get("missing") is None
    cache.put("key", response)

    assert cache.get("key") is response


def test_offline_mode_refuses_before_dns_or_network() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    resolver_calls: list[str] = []
    transport_calls: list[httpx.Request] = []
    limiter = _RecordingRateLimiter()

    def resolver(host: str) -> tuple[object, ...]:
        resolver_calls.append(host)
        return ()

    def handler(request: httpx.Request) -> httpx.Response:
        transport_calls.append(request)
        return httpx.Response(200, content=b"unexpected")

    policy = HttpClientPolicy(
        allowed_hosts=frozenset({"data.example"}),
        user_agent="stock-research-agent/test",
    )
    with SafeHttpClient(
        policy,
        cache=InMemoryResponseCache(),
        rate_limiter=limiter,
        transport=httpx.MockTransport(handler),
        resolver=resolver,
    ) as client:
        with pytest.raises(errors.NetworkDisabledError, match="disabled"):
            client.get(HttpRequest(url="https://data.example/file", accept="text/csv"))

    assert resolver_calls == []
    assert transport_calls == []
    assert limiter.buckets == []


def test_http_url_is_rejected_before_dns() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    resolver_calls: list[str] = []

    def resolver(host: str) -> tuple[object, ...]:
        resolver_calls.append(host)
        return ()

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
        resolver=resolver,
    ) as client:
        with pytest.raises(errors.HttpPolicyError, match="HTTPS"):
            client.get(HttpRequest(url="http://data.example/file", accept="text/csv"))

    assert resolver_calls == []


def test_url_user_info_is_rejected_without_exposing_it() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
        resolver=lambda _: (),
    ) as client:
        with pytest.raises(errors.HttpPolicyError) as captured:
            client.get(
                HttpRequest(
                    url="https://analyst:user-secret@data.example/file",
                    accept="text/csv",
                )
            )

    assert "user-secret" not in str(captured.value)
    assert "user-secret" not in repr(captured.value)


def test_url_fragment_is_rejected() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
        resolver=lambda _: (),
    ) as client:
        with pytest.raises(errors.HttpPolicyError, match="fragment"):
            client.get(HttpRequest(url="https://data.example/file#section", accept="text/csv"))


def test_non_standard_https_port_is_rejected() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
        resolver=lambda _: (),
    ) as client:
        with pytest.raises(errors.HttpPolicyError, match="port"):
            client.get(HttpRequest(url="https://data.example:8443/file", accept="text/csv"))


def test_invalid_port_error_discards_sensitive_parser_cause() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
        resolver=lambda _: (),
    ) as client:
        with pytest.raises(errors.HttpPolicyError) as captured:
            client.get(
                HttpRequest(
                    url="https://data.example:port-secret/file?token=query-secret",
                    accept="text/plain",
                )
            )

    assert captured.value.__cause__ is None
    assert "port-secret" not in repr(captured.value)
    assert "query-secret" not in repr(captured.value)


def test_ip_literal_hostname_is_rejected() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"127.0.0.1"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
        resolver=lambda _: (),
    ) as client:
        with pytest.raises(errors.HttpPolicyError, match="IP literal"):
            client.get(HttpRequest(url="https://127.0.0.1/file", accept="text/csv"))


def test_hostname_outside_exact_allowlist_is_rejected_before_dns() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    resolver_calls: list[str] = []

    def resolver(host: str) -> tuple[object, ...]:
        resolver_calls.append(host)
        return ()

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
        resolver=resolver,
    ) as client:
        with pytest.raises(errors.HttpPolicyError, match="allowlist"):
            client.get(HttpRequest(url="https://sub.data.example/file", accept="text/csv"))

    assert resolver_calls == []


def test_empty_host_allowlist_is_rejected() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")

    with pytest.raises(errors.HttpPolicyError, match="allowlist"):
        HttpClientPolicy(
            allowed_hosts=frozenset(),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        )


@pytest.mark.parametrize(
    "override",
    [
        {"connect_timeout_seconds": 0.0},
        {"read_timeout_seconds": math.inf},
        {"total_timeout_seconds": -1.0},
        {"max_response_bytes": 0},
        {"max_response_bytes": 52_428_801},
        {"max_redirects": -1},
        {"max_redirects": 6},
        {"max_attempts": 0},
        {"max_attempts": 4},
        {"retry_base_delay_seconds": 0.0},
        {"user_agent": ""},
        {"user_agent": "agent\nvalue"},
    ],
)
def test_http_client_policy_rejects_unsafe_bounds(override: dict[str, object]) -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    values: dict[str, object] = {
        "allowed_hosts": frozenset({"data.example"}),
        "user_agent": "stock-research-agent/test",
    }
    values.update(override)

    with pytest.raises(errors.HttpPolicyError):
        HttpClientPolicy(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.1",
        "127.0.0.1",
        "169.254.1.1",
        "224.0.0.1",
        "240.0.0.1",
        "0.0.0.0",
        "100.64.0.1",
        "::1",
        "fe80::1",
        "ff00::1",
        "::",
        "2001:db8::1",
    ],
)
def test_non_global_resolved_address_is_rejected(address: str) -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    transport_calls: list[httpx.Request] = []
    limiter = _RecordingRateLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        transport_calls.append(request)
        return httpx.Response(200)

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=limiter,
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address(address),),
    ) as client:
        with pytest.raises(errors.HttpPolicyError, match="global"):
            client.get(HttpRequest(url="https://data.example/file", accept="text/csv"))

    assert transport_calls == []
    assert limiter.buckets == []


def test_empty_dns_resolution_is_rejected() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
        resolver=lambda _: (),
    ) as client:
        with pytest.raises(errors.HttpPolicyError, match="resolve"):
            client.get(HttpRequest(url="https://data.example/file", accept="text/csv"))


def test_blocking_resolver_is_cut_off_by_total_deadline() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    release = threading.Event()

    def resolver(_: str) -> tuple[ipaddress.IPv4Address, ...]:
        release.wait(timeout=1.0)
        return (ipaddress.ip_address("93.184.216.34"),)

    started = time.monotonic()
    try:
        with SafeHttpClient(
            HttpClientPolicy(
                allowed_hosts=frozenset({"data.example"}),
                user_agent="stock-research-agent/test",
                network_enabled=True,
                total_timeout_seconds=0.02,
            ),
            cache=InMemoryResponseCache(),
            rate_limiter=_RecordingRateLimiter(),
            transport=httpx.MockTransport(lambda _: httpx.Response(200)),
            resolver=resolver,
        ) as client:
            with pytest.raises(errors.HttpTimeoutError, match="total timeout"):
                client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))
    finally:
        release.set()

    assert time.monotonic() - started < 0.3


def test_repeated_blocking_dns_timeouts_keep_threads_and_queue_bounded() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    release = threading.Event()
    resolver_calls = 0
    baseline_threads = threading.active_count()

    def resolver(_: str) -> tuple[ipaddress.IPv4Address, ...]:
        nonlocal resolver_calls
        resolver_calls += 1
        release.wait(timeout=1.0)
        return (ipaddress.ip_address("93.184.216.34"),)

    client = SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            total_timeout_seconds=0.01,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
        resolver=resolver,
    )
    started = time.monotonic()
    try:
        for _ in range(8):
            with pytest.raises(errors.HttpTimeoutError, match="total timeout"):
                client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))

        assert resolver_calls == 1
        assert threading.active_count() <= baseline_threads + 1
        assert time.monotonic() - started < 0.3
    finally:
        client.close()
        release.set()


def test_valid_get_returns_body_and_response_metadata() -> None:
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                content=b'{"price": 42}',
                headers={
                    "Content-Type": "application/json",
                    "ETag": '"v1"',
                    "Last-Modified": "Tue, 14 Jul 2026 08:00:00 GMT",
                },
            )
        ),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        result = client.get(
            HttpRequest(url="https://data.example/file?symbol=ABC", accept="application/json")
        )

    assert result.status_code == 200
    assert result.body == b'{"price": 42}'
    assert result.content_type == "application/json"
    assert result.safe_url == "https://data.example/file?symbol=ABC"
    assert result.attempts == 1
    assert result.cache_status == "MISS"
    assert result.etag == '"v1"'
    assert result.last_modified == "Tue, 14 Jul 2026 08:00:00 GMT"


def test_each_attempt_connects_to_its_validated_ip_with_original_host_and_sni() -> None:
    resolutions = iter(
        [
            (ipaddress.ip_address("93.184.216.34"),),
            (ipaddress.ip_address("1.1.1.1"),),
        ]
    )
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(500 if len(sent) == 1 else 200, content=b"ok")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_attempts=2,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: next(resolutions),
        sleeper=lambda _: None,
    ) as client:
        result = client.get(
            HttpRequest(url="https://data.example/file?symbol=ABC", accept="text/plain")
        )

    assert [str(request.url) for request in sent] == [
        "https://93.184.216.34/file?symbol=ABC",
        "https://1.1.1.1/file?symbol=ABC",
    ]
    assert [request.headers["Host"] for request in sent] == ["data.example", "data.example"]
    assert [request.extensions["sni_hostname"] for request in sent] == [
        "data.example",
        "data.example",
    ]
    assert result.body == b"ok"


def test_retry_rejects_dns_rebinding_to_a_non_global_address() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    resolutions = iter(
        [
            (ipaddress.ip_address("93.184.216.34"),),
            (ipaddress.ip_address("127.0.0.1"),),
        ]
    )
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(500, content=b"retry")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_attempts=2,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: next(resolutions),
        sleeper=lambda _: None,
    ) as client:
        with pytest.raises(errors.HttpPolicyError, match="global"):
            client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))

    assert [str(request.url) for request in sent] == ["https://93.184.216.34/file"]


def test_lowercase_host_rate_bucket_is_acquired_immediately_before_request() -> None:
    events: list[str] = []

    class _EventLimiter:
        def acquire(self, bucket: str) -> None:
            events.append(f"rate:{bucket}")

    def resolver(host: str) -> tuple[ipaddress.IPv4Address, ...]:
        events.append(f"resolve:{host}")
        return (ipaddress.ip_address("93.184.216.34"),)

    def handler(_: httpx.Request) -> httpx.Response:
        events.append("request")
        return httpx.Response(200, content=b"ok")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_EventLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=resolver,
    ) as client:
        client.get(HttpRequest(url="https://DATA.example/file", accept="text/plain"))

    assert events == ["resolve:data.example", "rate:data.example", "request"]


def test_owned_httpx_client_uses_hardened_tls_redirect_timeout_and_encoding_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.Client
    captured: dict[str, object] = {}

    def client_factory(**kwargs: object) -> httpx.Client:
        captured.update(kwargs)
        kwargs["transport"] = httpx.MockTransport(lambda _: httpx.Response(200))
        return real_client(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(http_client_module.httpx, "Client", client_factory)
    client = SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            connect_timeout_seconds=2.0,
            read_timeout_seconds=7.0,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
    )
    client.close()

    timeout = captured["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 2.0
    assert timeout.read == 7.0
    assert timeout.write == 7.0
    assert timeout.pool == 2.0
    assert captured["verify"] is True
    assert captured["follow_redirects"] is False
    assert captured["trust_env"] is False
    assert captured["headers"] == {"Accept-Encoding": "identity"}
    limits = captured["limits"]
    assert isinstance(limits, httpx.Limits)
    assert limits.max_keepalive_connections == 0


def test_each_attempt_timeout_is_bounded_by_remaining_total_deadline() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, content=b"ok")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            connect_timeout_seconds=5.0,
            read_timeout_seconds=15.0,
            total_timeout_seconds=1.0,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))

    timeout = sent[0].extensions["timeout"]
    assert isinstance(timeout, dict)
    assert set(timeout) == {"connect", "read", "write", "pool"}
    assert all(isinstance(value, float) and 0 < value <= 1.0 for value in timeout.values())


def test_policy_user_agent_accept_and_identity_encoding_cannot_be_overridden() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, content=b"ok")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/provider-test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        client.get(
            HttpRequest(
                url="https://data.example/file",
                accept="application/json",
                headers={
                    "User-Agent": "unsafe-override",
                    "Accept": "*/*",
                    "Accept-Encoding": "gzip",
                    "X-Provider": "kept",
                },
            )
        )

    assert sent[0].headers["User-Agent"] == "stock-research-agent/provider-test"
    assert sent[0].headers["Accept"] == "application/json"
    assert sent[0].headers["Accept-Encoding"] == "identity"
    assert sent[0].headers["X-Provider"] == "kept"


def test_protected_headers_are_replaced_case_insensitively_on_the_wire() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, content=b"ok")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/provider-test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        client.get(
            HttpRequest(
                url="https://data.example/file",
                accept="application/json",
                headers={
                    "user-agent": "unsafe-agent",
                    "aCcEpT": "unsafe-accept",
                    "ACCEPT-encoding": "gzip",
                    "hOsT": "127.0.0.1",
                    "if-none-match": '"attacker"',
                    "IF-modified-SINCE": "attacker-date",
                    "X-Provider": "kept",
                },
            )
        )

    raw_names = [name.decode("ascii").lower() for name, _ in sent[0].headers.raw]
    assert raw_names.count("user-agent") == 1
    assert raw_names.count("accept") == 1
    assert raw_names.count("accept-encoding") == 1
    assert raw_names.count("host") == 1
    assert "if-none-match" not in raw_names
    assert "if-modified-since" not in raw_names
    assert sent[0].headers["User-Agent"] == "stock-research-agent/provider-test"
    assert sent[0].headers["Accept"] == "application/json"
    assert sent[0].headers["Accept-Encoding"] == "identity"
    assert sent[0].headers["Host"] == "data.example"
    assert sent[0].headers["X-Provider"] == "kept"


@pytest.mark.parametrize(
    ("headers", "accept"),
    [
        ({"X-Bad\r\nX-Leak": "header-secret"}, "text/plain"),
        ({"X-Provider": "header-secret\nleak"}, "text/plain"),
        ({"X-Provider": "safe"}, "text/plain\r\nX-Leak: accept-secret"),
    ],
)
def test_invalid_request_headers_are_rejected_without_secret_bearing_cause(
    headers: dict[str, str], accept: str
) -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    transport_calls: list[httpx.Request] = []

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(
            lambda request: (
                transport_calls.append(request),
                httpx.Response(200),
            )[1]
        ),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        with pytest.raises(errors.HttpPolicyError) as captured:
            client.get(
                HttpRequest(
                    url="https://data.example/file",
                    accept=accept,
                    headers=headers,
                )
            )

    assert captured.value.__cause__ is None
    assert "header-secret" not in repr(captured.value)
    assert "accept-secret" not in repr(captured.value)
    assert transport_calls == []


def test_safe_url_and_request_repr_redact_sensitive_query_and_header_values() -> None:
    module = importlib.import_module("stock_research_agent.providers.http_client")
    secrets = {
        "query-secret",
        "auth-secret",
        "proxy-secret",
        "cookie-secret",
        "set-cookie-secret",
        "api-header-secret",
        "rapidapi-header-secret",
        "signature-header-secret",
    }
    request = HttpRequest(
        url="https://DATA.example/file?ToKeN=query-secret&symbol=ABC",
        accept="application/json",
        headers={
            "Authorization": "Bearer auth-secret",
            "Proxy-Authorization": "Bearer proxy-secret",
            "Cookie": "session=cookie-secret",
            "Set-Cookie": "session=set-cookie-secret",
            "X-API-Key": "api-header-secret",
            "x-RapidAPI-key": "rapidapi-header-secret",
            "X-Signature": "signature-header-secret",
            "X-Trace": "safe-trace",
        },
    )

    rendered_url = module.safe_url(request.url)
    rendered_request = repr(request)
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(rendered_url).query)

    assert query == {"ToKeN": ["***"], "symbol": ["ABC"]}
    assert "ToKeN=***" in rendered_url
    assert rendered_url.startswith("https://data.example/file?")
    assert "safe-trace" in rendered_request
    assert all(secret not in rendered_url for secret in secrets)
    assert all(secret not in rendered_request for secret in secrets)


def test_result_safe_url_never_exposes_sensitive_query_values() -> None:
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(404, content=b"not found")),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        result = client.get(
            HttpRequest(
                url="https://data.example/file?api_key=query-secret&symbol=ABC",
                accept="application/json",
            )
        )

    assert "query-secret" not in result.safe_url
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(result.safe_url).query) == {
        "api_key": ["***"],
        "symbol": ["ABC"],
    }


def test_429_is_retried_with_exponential_delay() -> None:
    responses = iter(
        [
            httpx.Response(429, content=b"busy"),
            httpx.Response(200, content=b"ok"),
        ]
    )
    sleeps: list[float] = []
    limiter = _RecordingRateLimiter()

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_attempts=2,
            retry_base_delay_seconds=0.5,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=limiter,
        transport=httpx.MockTransport(lambda _: next(responses)),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
        sleeper=sleeps.append,
    ) as client:
        result = client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))

    assert result.status_code == 200
    assert result.body == b"ok"
    assert result.attempts == 2
    assert sleeps == [0.5]
    assert limiter.buckets == ["data.example", "data.example"]


def test_404_is_returned_without_retry() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, content=b"not found")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
        sleeper=sleeps.append,
    ) as client:
        result = client.get(HttpRequest(url="https://data.example/missing", accept="text/plain"))

    assert result.status_code == 404
    assert result.attempts == 1
    assert attempts == 1
    assert sleeps == []


@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
def test_approved_server_errors_are_retried(status_code: int) -> None:
    responses = iter(
        [
            httpx.Response(status_code, content=b"temporary"),
            httpx.Response(200, content=b"ok"),
        ]
    )
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_attempts=2,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: next(responses)),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
        sleeper=lambda _: None,
    ) as client:
        result = client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))

    assert result.status_code == 200
    assert result.attempts == 2


def test_retryable_status_exhaustion_raises_safe_typed_error() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_attempts=2,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(503, content=b"body-secret")),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
        sleeper=lambda _: None,
    ) as client:
        with pytest.raises(errors.RetryExhaustedError) as captured:
            client.get(
                HttpRequest(
                    url="https://data.example/file?token=query-secret",
                    accept="text/plain",
                )
            )

    rendered = repr(captured.value)
    assert "body-secret" not in rendered
    assert "query-secret" not in rendered


@pytest.mark.parametrize("failure_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_connect_and_timeout_failures_are_retried(
    failure_type: type[httpx.RequestError],
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise failure_type("temporary failure", request=request)
        return httpx.Response(200, content=b"ok")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_attempts=2,
            retry_base_delay_seconds=0.4,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
        sleeper=sleeps.append,
    ) as client:
        result = client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))

    assert result.status_code == 200
    assert result.attempts == 2
    assert sleeps == [0.4]


@pytest.mark.parametrize("failure_type", [httpx.ReadError, httpx.WriteError, httpx.CloseError])
def test_httpx_network_errors_retry_then_become_safe_typed_errors(
    failure_type: type[httpx.RequestError],
) -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")

    def handler(request: httpx.Request) -> httpx.Response:
        raise failure_type("transport-secret", request=request)

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_attempts=1,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        with pytest.raises(errors.RetryExhaustedError) as captured:
            client.get(
                HttpRequest(
                    url="https://data.example/file?token=query-secret",
                    accept="text/plain",
                )
            )

    assert captured.value.__cause__ is None
    assert "transport-secret" not in repr(captured.value)
    assert "query-secret" not in repr(captured.value)


@pytest.mark.parametrize(
    "failure_type",
    [
        httpx.ProxyError,
        httpx.RemoteProtocolError,
        httpx.LocalProtocolError,
        httpx.UnsupportedProtocol,
        httpx.DecodingError,
    ],
)
def test_httpx_non_network_request_errors_are_safe_and_not_retried(
    failure_type: type[httpx.RequestError],
) -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise failure_type("transport-secret", request=request)

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_attempts=3,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        with pytest.raises(errors.HttpPolicyError) as captured:
            client.get(
                HttpRequest(
                    url="https://data.example/file?token=query-secret",
                    accept="text/plain",
                )
            )

    assert attempts == 1
    assert captured.value.__cause__ is None
    assert "transport-secret" not in repr(captured.value)
    assert "query-secret" not in repr(captured.value)


def test_timeout_exhaustion_raises_safe_typed_timeout() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("transport-secret", request=request)

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_attempts=1,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        with pytest.raises(errors.HttpTimeoutError) as captured:
            client.get(
                HttpRequest(
                    url="https://data.example/file?auth=query-secret",
                    accept="text/plain",
                )
            )

    assert "transport-secret" not in repr(captured.value)
    assert "query-secret" not in repr(captured.value)


def test_numeric_retry_after_within_total_deadline_is_honored() -> None:
    clock = _Clock()
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "2.0"}),
            httpx.Response(200, content=b"ok"),
        ]
    )
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_attempts=2,
            total_timeout_seconds=5.0,
            retry_base_delay_seconds=0.25,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: next(responses)),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
    ) as client:
        result = client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))

    assert result.status_code == 200
    assert clock.sleeps == [2.0]


def test_retry_delay_is_capped_by_remaining_total_deadline() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    clock = _Clock()
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        clock.now += 0.8
        return httpx.Response(429, headers={"Retry-After": "10"})

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_attempts=2,
            total_timeout_seconds=1.0,
            retry_base_delay_seconds=2.0,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
    ) as client:
        with pytest.raises(errors.HttpTimeoutError, match="total timeout"):
            client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))

    assert attempts == 1
    assert clock.sleeps == [pytest.approx(0.2)]


def test_rate_limiter_wait_cannot_send_after_total_deadline() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    clock = _Clock()
    transport_calls = 0

    class _SlowLimiter:
        def acquire(self, bucket: str) -> None:
            assert bucket == "data.example"
            clock.now += 1.0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        return httpx.Response(200, content=b"late")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            total_timeout_seconds=0.5,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_SlowLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
        monotonic=clock.monotonic,
    ) as client:
        with pytest.raises(errors.HttpTimeoutError, match="total timeout"):
            client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))

    assert transport_calls == 0


def test_blocking_rate_limiter_is_cut_off_by_total_deadline() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    release = threading.Event()

    class _BlockingLimiter:
        def acquire(self, _: str) -> None:
            release.wait(timeout=1.0)

    started = time.monotonic()
    try:
        with SafeHttpClient(
            HttpClientPolicy(
                allowed_hosts=frozenset({"data.example"}),
                user_agent="stock-research-agent/test",
                network_enabled=True,
                total_timeout_seconds=0.02,
            ),
            cache=InMemoryResponseCache(),
            rate_limiter=_BlockingLimiter(),
            transport=httpx.MockTransport(lambda _: httpx.Response(200)),
            resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
        ) as client:
            with pytest.raises(errors.HttpTimeoutError, match="total timeout"):
                client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))
    finally:
        release.set()

    assert time.monotonic() - started < 0.3


def test_transport_time_is_enforced_by_total_deadline() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    clock = _Clock()

    def handler(_: httpx.Request) -> httpx.Response:
        clock.now += 1.0
        return httpx.Response(200, content=b"late")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            total_timeout_seconds=0.5,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
        monotonic=clock.monotonic,
    ) as client:
        with pytest.raises(errors.HttpTimeoutError, match="total timeout"):
            client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))


def test_blocking_transport_is_cut_off_by_total_deadline() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    release = threading.Event()

    def handler(_: httpx.Request) -> httpx.Response:
        release.wait(timeout=1.0)
        return httpx.Response(200, content=b"late")

    started = time.monotonic()
    try:
        with SafeHttpClient(
            HttpClientPolicy(
                allowed_hosts=frozenset({"data.example"}),
                user_agent="stock-research-agent/test",
                network_enabled=True,
                total_timeout_seconds=0.02,
            ),
            cache=InMemoryResponseCache(),
            rate_limiter=_RecordingRateLimiter(),
            transport=httpx.MockTransport(handler),
            resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
        ) as client:
            with pytest.raises(errors.HttpTimeoutError, match="total timeout"):
                client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))
    finally:
        release.set()

    assert time.monotonic() - started < 0.3


def test_stream_iteration_is_enforced_by_total_deadline() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    clock = _Clock()

    class _SlowStream(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            clock.now += 1.0
            yield b"late"

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            total_timeout_seconds=0.5,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=_SlowStream())),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
        monotonic=clock.monotonic,
    ) as client:
        with pytest.raises(errors.HttpTimeoutError, match="total timeout"):
            client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))


def test_blocking_stream_read_is_cut_off_by_total_deadline() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    release = threading.Event()

    class _BlockingStream(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            release.wait(timeout=1.0)
            yield b"late"

    started = time.monotonic()
    try:
        with SafeHttpClient(
            HttpClientPolicy(
                allowed_hosts=frozenset({"data.example"}),
                user_agent="stock-research-agent/test",
                network_enabled=True,
                total_timeout_seconds=0.02,
            ),
            cache=InMemoryResponseCache(),
            rate_limiter=_RecordingRateLimiter(),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=_BlockingStream())),
            resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
        ) as client:
            with pytest.raises(errors.HttpTimeoutError, match="total timeout"):
                client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))
    finally:
        release.set()

    assert time.monotonic() - started < 0.3


def test_many_small_chunks_reuse_one_bounded_deadline_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread_starts = 0
    original_start = threading.Thread.start

    def record_start(thread: threading.Thread) -> None:
        nonlocal thread_starts
        thread_starts += 1
        original_start(thread)

    class _ManyChunks(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            for _ in range(500):
                yield b"x"

    monkeypatch.setattr(threading.Thread, "start", record_start)
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=_ManyChunks())),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        result = client.get(
            HttpRequest(url="https://data.example/many", accept="application/octet-stream")
        )

    assert result.body == b"x" * 500
    assert thread_starts == 1


def test_late_transport_response_is_closed_after_total_timeout() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    release = threading.Event()
    closed = threading.Event()

    class _CloseSignalStream(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield b"late"

        def close(self) -> None:
            closed.set()

    def handler(_: httpx.Request) -> httpx.Response:
        release.wait(timeout=1.0)
        return httpx.Response(200, stream=_CloseSignalStream())

    client = SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            total_timeout_seconds=0.02,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    )
    try:
        with pytest.raises(errors.HttpTimeoutError, match="total timeout"):
            client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))
        release.set()
        assert closed.wait(timeout=0.3)
    finally:
        release.set()
        client.close()


def test_response_returned_during_future_handoff_is_closed_exactly_once_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    handoff_started = threading.Event()
    release_handoff = threading.Event()
    closed = threading.Event()
    close_calls = 0
    response_futures: list[Future[object]] = []
    original_set_result = Future.set_result

    class _CountingCloseStream(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield b"late"

        def close(self) -> None:
            nonlocal close_calls
            close_calls += 1
            closed.set()

    def pause_response_handoff(future: Future[object], result: object) -> None:
        if isinstance(result, httpx.Response):
            response_futures.append(future)
            handoff_started.set()
            release_handoff.wait(timeout=1.0)
        original_set_result(future, result)

    monkeypatch.setattr(Future, "set_result", pause_response_handoff)
    response = httpx.Response(200, stream=_CountingCloseStream())
    client = SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            total_timeout_seconds=0.02,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
    )
    try:
        with pytest.raises(errors.HttpTimeoutError, match="total timeout"):
            client._call_with_deadline(
                lambda: response,
                time.monotonic() + 0.02,
                late_cleanup=lambda late_response: late_response.close(),
            )
        assert handoff_started.is_set()
        assert close_calls == 0

        client.close()
        assert close_calls == 0

        release_handoff.set()
        assert response_futures
        assert closed.wait(timeout=0.3)
        time.sleep(0.02)
        assert close_calls == 1
    finally:
        release_handoff.set()
        client.close()


def test_relative_redirect_is_revalidated_without_reading_redirect_body() -> None:
    resolver_calls: list[str] = []
    requests: list[httpx.Request] = []

    def resolver(host: str) -> tuple[ipaddress.IPv4Address, ...]:
        resolver_calls.append(host)
        return (ipaddress.ip_address("93.184.216.34"),)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                302,
                headers={"Location": "/next"},
                stream=_UnreadableStream(),
            )
        return httpx.Response(200, content=b"final")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=resolver,
    ) as client:
        result = client.get(HttpRequest(url="https://data.example/start", accept="text/plain"))

    assert [str(request.url) for request in requests] == [
        "https://93.184.216.34/start",
        "https://93.184.216.34/next",
    ]
    assert [request.headers["Host"] for request in requests] == [
        "data.example",
        "data.example",
    ]
    assert resolver_calls == ["data.example", "data.example"]
    assert result.body == b"final"
    assert result.safe_url == "https://data.example/next"
    assert result.attempts == 2


@pytest.mark.parametrize("status_code", [301, 303, 307, 308])
def test_all_approved_redirect_statuses_are_followed_manually(status_code: int) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(status_code, headers={"Location": "/final"})
        return httpx.Response(200, content=b"final")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        result = client.get(HttpRequest(url="https://data.example/start", accept="text/plain"))

    assert result.body == b"final"
    assert result.attempts == 2


def test_cross_origin_redirect_strips_credentials_and_sensitive_headers() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if len(sent) == 1:
            return httpx.Response(302, headers={"Location": "https://mirror.example/final"})
        return httpx.Response(200, content=b"final")

    def resolver(host: str) -> tuple[ipaddress.IPv4Address, ...]:
        address = "93.184.216.34" if host == "data.example" else "1.1.1.1"
        return (ipaddress.ip_address(address),)

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example", "mirror.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=resolver,
    ) as client:
        result = client.get(
            HttpRequest(
                url="https://data.example/start",
                accept="text/plain",
                headers={
                    "Authorization": "Bearer auth-secret",
                    "Proxy-Authorization": "Bearer proxy-secret",
                    "Cookie": "session=cookie-secret",
                    "X-API-Key": "api-secret",
                    "X-RapidAPI-Key": "rapid-secret",
                    "X-Auth-Token": "token-secret",
                    "X-AccessToken": "compact-token-secret",
                    "X-Client-Secret": "client-secret",
                    "X-ClientSecret": "compact-client-secret",
                    "X-Signature": "signature-secret",
                    "Host": "attacker.invalid",
                    "X-Trace": "safe-trace",
                },
            )
        )

    first_names = {name.decode("ascii").lower() for name, _ in sent[0].headers.raw}
    redirected_names = {name.decode("ascii").lower() for name, _ in sent[1].headers.raw}
    sensitive_names = {
        "authorization",
        "proxy-authorization",
        "cookie",
        "x-api-key",
        "x-rapidapi-key",
        "x-auth-token",
        "x-accesstoken",
        "x-client-secret",
        "x-clientsecret",
        "x-signature",
    }
    assert sensitive_names <= first_names
    assert sensitive_names.isdisjoint(redirected_names)
    assert sent[1].headers["Host"] == "mirror.example"
    assert sent[1].headers["X-Trace"] == "safe-trace"
    assert result.body == b"final"


def test_cookie_jar_cannot_reintroduce_cookie_on_cross_origin_redirect() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if len(sent) == 1:
            return httpx.Response(
                302,
                headers={
                    "Location": "https://mirror.example/final",
                    "Set-Cookie": "session=jar-secret; Path=/; Secure",
                },
            )
        return httpx.Response(200, content=b"final")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example", "mirror.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        result = client.get(HttpRequest(url="https://data.example/start", accept="text/plain"))

    assert [request.headers["Host"] for request in sent] == [
        "data.example",
        "mirror.example",
    ]
    assert "Cookie" not in sent[1].headers
    assert "jar-secret" not in repr(sent[1].headers)
    assert result.body == b"final"


def test_cookie_jar_cannot_leak_cookie_to_independent_get_with_same_pinned_ip() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if len(sent) == 1:
            return httpx.Response(
                200,
                content=b"prime",
                headers={"Set-Cookie": "session=jar-secret; Path=/; Secure"},
            )
        return httpx.Response(200, content=b"next")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example", "mirror.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        client.get(HttpRequest(url="https://data.example/prime", accept="text/plain"))
        result = client.get(HttpRequest(url="https://mirror.example/next", accept="text/plain"))

    assert [request.headers["Host"] for request in sent] == [
        "data.example",
        "mirror.example",
    ]
    assert "Cookie" not in sent[1].headers
    assert "jar-secret" not in repr(sent[1].headers)
    assert result.body == b"next"


def test_explicit_cookie_header_is_preserved_across_same_origin_redirect() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if len(sent) == 1:
            return httpx.Response(302, headers={"Location": "/final"})
        return httpx.Response(200, content=b"ok")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        client.get(
            HttpRequest(
                url="https://data.example/file",
                accept="text/plain",
                headers={"Cookie": "session=explicit-cookie"},
            )
        )

    assert [request.headers["Cookie"] for request in sent] == [
        "session=explicit-cookie",
        "session=explicit-cookie",
    ]


def test_redirect_without_location_raises_typed_error() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(302)),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        with pytest.raises(errors.RedirectError, match="Location"):
            client.get(HttpRequest(url="https://data.example/start", accept="text/plain"))


@pytest.mark.parametrize(
    "location",
    [
        "ftp://data.example/file",
        "http://data.example/file",
        "https://other.example/file?token=location-secret",
        "https://data.example:8443/file",
        "https://[invalid",
    ],
)
def test_invalid_redirect_target_raises_safe_typed_error(location: str) -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(302, headers={"Location": location})
        ),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        with pytest.raises(errors.RedirectError) as captured:
            client.get(HttpRequest(url="https://data.example/start", accept="text/plain"))

    assert "location-secret" not in repr(captured.value)


def test_redirect_limit_is_enforced_separately_from_retry_attempts() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    requests = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        if requests > 2:
            raise AssertionError("redirect limit was not enforced")
        return httpx.Response(302, headers={"Location": f"/{requests}"})

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_redirects=1,
            max_attempts=3,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        with pytest.raises(errors.RedirectError, match="limit"):
            client.get(HttpRequest(url="https://data.example/start", accept="text/plain"))

    assert requests == 2


def test_content_length_over_cap_is_rejected_before_stream_iteration() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_response_bytes=5,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                headers={"Content-Length": "6"},
                stream=_UnreadableStream(),
            )
        ),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        with pytest.raises(errors.ResponseTooLargeError, match="large"):
            client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))


def test_stream_is_rejected_when_cumulative_bytes_cross_cap() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
            max_response_bytes=5,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=_ChunksStream(b"abc", b"def"))
        ),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        with pytest.raises(errors.ResponseTooLargeError, match="large"):
            client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))


def test_cached_validators_revalidate_304_with_cached_body() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                content=b"cached-body",
                headers={
                    "Content-Type": "application/json",
                    "ETag": '"v1"',
                    "Last-Modified": "Tue, 14 Jul 2026 08:00:00 GMT",
                },
            )
        assert request.headers["If-None-Match"] == '"v1"'
        assert request.headers["If-Modified-Since"] == "Tue, 14 Jul 2026 08:00:00 GMT"
        return httpx.Response(304)

    cache = InMemoryResponseCache()
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=cache,
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        first = client.get(
            HttpRequest(url="https://data.example/file?symbol=ABC", accept="application/json")
        )
        second = client.get(
            HttpRequest(url="https://data.example/file?symbol=ABC", accept="application/json")
        )

    assert first.cache_status == "MISS"
    assert second.cache_status == "REVALIDATED"
    assert second.body == b"cached-body"
    assert second.content_type == "application/json"
    assert second.etag == '"v1"'
    assert second.last_modified == "Tue, 14 Jul 2026 08:00:00 GMT"


def test_304_without_cached_content_raises_typed_error() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: httpx.Response(304)),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        with pytest.raises(errors.InvalidNotModifiedError, match="304"):
            client.get(HttpRequest(url="https://data.example/file", accept="text/plain"))


def test_successful_revalidation_updates_cached_body_and_status() -> None:
    responses = iter(
        [
            httpx.Response(200, content=b"v1", headers={"ETag": '"v1"'}),
            httpx.Response(200, content=b"v2", headers={"ETag": '"v2"'}),
            httpx.Response(304),
        ]
    )
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(lambda _: next(responses)),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        request = HttpRequest(url="https://data.example/file", accept="text/plain")
        first = client.get(request)
        updated = client.get(request)
        revalidated = client.get(request)

    assert first.cache_status == "MISS"
    assert updated.cache_status == "UPDATED"
    assert revalidated.cache_status == "REVALIDATED"
    assert revalidated.body == b"v2"
    assert revalidated.etag == '"v2"'


def test_cache_key_hashes_normalized_unredacted_url_and_accept() -> None:
    class _KeyCache(InMemoryResponseCache):
        def __init__(self) -> None:
            super().__init__()
            self.keys: list[str] = []

        def get(self, key: str):  # type: ignore[no-untyped-def]
            self.keys.append(key)
            return super().get(key)

    cache = _KeyCache()
    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
            network_enabled=True,
        ),
        cache=cache,
        rate_limiter=_RecordingRateLimiter(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=b"ok", headers={"ETag": '"v"'})
        ),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        client.get(
            HttpRequest(
                url="https://DATA.example:443/file?token=one",
                accept="application/json",
            )
        )
        client.get(
            HttpRequest(
                url="https://data.example/file?token=one",
                accept="application/json",
            )
        )
        client.get(
            HttpRequest(
                url="https://data.example/file?token=two",
                accept="application/json",
            )
        )
        client.get(
            HttpRequest(
                url="https://data.example/file?token=two",
                accept="text/plain",
            )
        )

    assert cache.keys[0] == cache.keys[1]
    assert cache.keys[0] != cache.keys[2]
    assert cache.keys[2] != cache.keys[3]
    assert all(len(key) == 64 for key in cache.keys)
    assert all("one" not in key and "two" not in key for key in cache.keys)


def test_context_manager_closes_owned_httpx_client_and_transport() -> None:
    transport = _CloseRecordingTransport()

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=transport,
    ):
        assert transport.closed is False

    assert transport.closed is True


def test_close_translates_httpx_errors_without_exposing_their_cause() -> None:
    errors = importlib.import_module("stock_research_agent.providers.errors")
    client = SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"data.example"}),
            user_agent="stock-research-agent/test",
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RecordingRateLimiter(),
        transport=_FailingCloseTransport(),
    )

    with pytest.raises(errors.HttpPolicyError) as captured:
        client.close()

    assert captured.value.__cause__ is None
    assert "close-secret" not in repr(captured.value)
