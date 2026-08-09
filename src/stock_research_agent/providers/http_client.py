"""Safe HTTP creation and request boundary for data providers."""

from __future__ import annotations

import hashlib
import http.cookiejar
import ipaddress
import math
import queue
import re
import socket
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial
from typing import TypeVar, cast

import httpx

from stock_research_agent.providers.cache import CachedResponse, ResponseCache
from stock_research_agent.providers.errors import (
    HttpPolicyError,
    HttpTimeoutError,
    InvalidNotModifiedError,
    NetworkDisabledError,
    RedirectError,
    ResponseTooLargeError,
    RetryExhaustedError,
)
from stock_research_agent.providers.rate_limit import RateLimiter

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str], tuple[IPAddress, ...]]
T = TypeVar("T")
_SENSITIVE_QUERY_KEYS = frozenset(
    {
        "token",
        "api_key",
        "apikey",
        "key",
        "access_token",
        "auth",
        "authorization",
        "secret",
        "signature",
    }
)
_SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "api-key",
        "x-api-key",
        "apikey",
        "x-apikey",
    }
)
_PROTECTED_REQUEST_HEADER_NAMES = frozenset(
    {
        "user-agent",
        "accept",
        "accept-encoding",
        "host",
        "if-none-match",
        "if-modified-since",
    }
)
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
_HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_WORKER_STOP = object()


class _RejectAllCookiePolicy(http.cookiejar.DefaultCookiePolicy):
    """Prevent the numeric-IP transport origin from becoming a shared cookie scope."""

    def set_ok(self, cookie: http.cookiejar.Cookie, request: object) -> bool:
        del cookie, request
        return False


@dataclass(frozen=True, slots=True)
class _DeadlineTask[T]:
    operation: Callable[[], T]
    future: Future[T]


class _BoundedDeadlineWorker:
    """Run blocking HTTP boundary work on one daemon and one queued slot."""

    def __init__(self) -> None:
        self._queue: queue.Queue[_DeadlineTask[object] | object] = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._closed = False

    def submit(self, operation: Callable[[], T], timeout: float) -> Future[T]:
        future: Future[T] = Future()
        task = _DeadlineTask(
            operation=cast(Callable[[], object], operation),
            future=cast(Future[object], future),
        )
        with self._lock:
            if self._closed:
                raise RuntimeError("Provider deadline worker is closed")
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run,
                    daemon=True,
                    name=f"stock-provider-http-{id(self):x}",
                )
                self._thread.start()
            self._queue.put(task, timeout=timeout)
        return future

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            while True:
                try:
                    queued = self._queue.get_nowait()
                except queue.Empty:
                    break
                if isinstance(queued, _DeadlineTask):
                    queued.future.cancel()
                self._queue.task_done()
            try:
                self._queue.put_nowait(_WORKER_STOP)
            except queue.Full:
                pass

    def _run(self) -> None:
        while True:
            queued = self._queue.get()
            try:
                if queued is _WORKER_STOP:
                    return
                if not isinstance(queued, _DeadlineTask):
                    continue
                if not queued.future.set_running_or_notify_cancel():
                    continue
                try:
                    result = queued.operation()
                except BaseException as exc:
                    queued.future.set_exception(exc)
                else:
                    queued.future.set_result(result)
            finally:
                self._queue.task_done()


def _is_sensitive_header(name: str) -> bool:
    normalized = name.strip().lower().replace("_", "-")
    if normalized in _SENSITIVE_HEADER_NAMES:
        return True
    parts = normalized.split("-")
    compact = normalized.replace("-", "")
    return any(part in {"token", "secret", "signature"} for part in parts) or compact.endswith(
        ("apikey", "token", "secret", "signature")
    )


def _url_origin(url: str) -> tuple[str, int] | None:
    try:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if host is None:
        return None
    return host.lower(), 443 if port is None else port


def _validate_header(name: object, value: object) -> tuple[str, str]:
    if not isinstance(name, str) or not isinstance(value, str):
        raise HttpPolicyError("Provider request contains an invalid header")
    if _HEADER_NAME_PATTERN.fullmatch(name) is None:
        raise HttpPolicyError("Provider request contains an invalid header")
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        raise HttpPolicyError("Provider request contains an invalid header") from None
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise HttpPolicyError("Provider request contains an invalid header")
    return name, value


def safe_url(url: str) -> str:
    """Return a URL suitable for results and failure messages."""
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return "<invalid-url>"
    host = parsed.hostname
    if host is None:
        return "<invalid-url>"
    try:
        port = parsed.port
    except ValueError:
        return "<invalid-url>"
    display_host = f"[{host.lower()}]" if ":" in host else host.lower()
    netloc = display_host if port is None else f"{display_host}:{port}"
    query = urllib.parse.urlencode(
        [
            (key, "***" if key.lower() in _SENSITIVE_QUERY_KEYS else value)
            for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        ],
        safe="*",
    )
    return urllib.parse.urlunsplit((parsed.scheme.lower(), netloc, parsed.path, query, ""))


def _cache_key(url: str, accept: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        material = f"GET\n{url}\n{accept}".encode()
        return hashlib.sha256(material).hexdigest()
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = host.lower()
    if port not in (None, 443):
        netloc = f"{netloc}:{port}"
    normalized_url = urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            netloc,
            parsed.path or "/",
            parsed.query,
            "",
        )
    )
    material = f"GET\n{normalized_url}\n{accept}".encode()
    return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, slots=True)
class HttpClientPolicy:
    allowed_hosts: frozenset[str]
    user_agent: str
    network_enabled: bool = False
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 15.0
    total_timeout_seconds: float = 30.0
    max_response_bytes: int = 5_242_880
    max_redirects: int = 3
    max_attempts: int = 3
    retry_base_delay_seconds: float = 0.25

    def __post_init__(self) -> None:
        if not self.allowed_hosts:
            raise HttpPolicyError("Provider host allowlist must not be empty")
        for value in (
            self.connect_timeout_seconds,
            self.read_timeout_seconds,
            self.total_timeout_seconds,
            self.retry_base_delay_seconds,
        ):
            if value <= 0 or not math.isfinite(value):
                raise HttpPolicyError("Provider time settings must be positive and finite")
        if not 1 <= self.max_response_bytes <= 52_428_800:
            raise HttpPolicyError("Provider response byte cap is outside its safe range")
        if not 0 <= self.max_redirects <= 5:
            raise HttpPolicyError("Provider redirect limit is outside its safe range")
        if not 1 <= self.max_attempts <= 3:
            raise HttpPolicyError("Provider attempt limit is outside its safe range")
        if not 1 <= len(self.user_agent) <= 256:
            raise HttpPolicyError("Provider User-Agent length is outside its safe range")
        if any(ord(character) < 32 or ord(character) == 127 for character in self.user_agent):
            raise HttpPolicyError("Provider User-Agent contains control characters")


@dataclass(frozen=True, slots=True)
class HttpRequest:
    url: str
    accept: str
    headers: Mapping[str, str] = field(default_factory=dict)
    request_id: str | None = None
    provider_request_id: str | None = None

    def __repr__(self) -> str:
        safe_headers = {
            name: ("***" if _is_sensitive_header(name) else value)
            for name, value in self.headers.items()
        }
        return (
            f"HttpRequest(url={safe_url(self.url)!r}, accept={self.accept!r}, "
            f"headers={safe_headers!r}, request_id={self.request_id!r}, "
            f"provider_request_id={self.provider_request_id!r})"
        )


@dataclass(frozen=True, slots=True)
class HttpResult:
    status_code: int
    body: bytes
    content_type: str | None
    safe_url: str
    attempts: int
    cache_status: str
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True, slots=True)
class _PinnedTarget:
    host: str
    authority: str
    url: str


def _default_resolver(host: str) -> tuple[IPAddress, ...]:
    addresses = {
        ipaddress.ip_address(sockaddr[0])
        for _, _, _, _, sockaddr in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    }
    return tuple(sorted(addresses, key=lambda address: (address.version, int(address))))


class SafeHttpClient:
    """Single lifecycle-managed HTTP boundary used by provider adapters."""

    def __init__(
        self,
        policy: HttpClientPolicy,
        *,
        cache: ResponseCache,
        rate_limiter: RateLimiter,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._policy = policy
        self._cache = cache
        self._rate_limiter = rate_limiter
        self._resolver = resolver or _default_resolver
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._deadline_worker = _BoundedDeadlineWorker()
        timeout = httpx.Timeout(
            connect=policy.connect_timeout_seconds,
            read=policy.read_timeout_seconds,
            write=policy.read_timeout_seconds,
            pool=policy.connect_timeout_seconds,
        )
        self._client = httpx.Client(
            verify=True,
            follow_redirects=False,
            trust_env=False,
            timeout=timeout,
            limits=httpx.Limits(max_keepalive_connections=0),
            headers={"Accept-Encoding": "identity"},
            cookies=http.cookiejar.CookieJar(policy=_RejectAllCookiePolicy()),
            transport=transport,
        )

    def __enter__(self) -> SafeHttpClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the owned HTTP client and its transport."""
        try:
            self._client.close()
        except httpx.HTTPError:
            raise HttpPolicyError("Provider HTTP client close failed") from None
        finally:
            self._deadline_worker.close()

    def _call_with_deadline(
        self,
        operation: Callable[[], T],
        deadline: float,
        *,
        late_cleanup: Callable[[T], None] | None = None,
    ) -> T:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise HttpTimeoutError("Provider GET exceeded total timeout")
        state_lock = threading.Lock()
        expired = False
        result_claimed = False
        cleanup_started = False

        def run() -> T:
            return operation()

        def cleanup_expired_result(completed: Future[T]) -> None:
            nonlocal cleanup_started
            if late_cleanup is None:
                return
            with state_lock:
                if (
                    not expired
                    or result_claimed
                    or cleanup_started
                    or not completed.done()
                    or completed.cancelled()
                ):
                    return
                if completed.exception() is not None:
                    cleanup_started = True
                    return
                cleanup_started = True
                result = completed.result()
            try:
                late_cleanup(result)
            except Exception:
                pass

        try:
            future = self._deadline_worker.submit(run, remaining)
        except queue.Full:
            raise HttpTimeoutError("Provider GET exceeded total timeout") from None
        future.add_done_callback(cleanup_expired_result)
        try:
            result = future.result(timeout=max(0.0, deadline - self._monotonic()))
        except FutureTimeoutError:
            with state_lock:
                expired = True
            future.cancel()
            cleanup_expired_result(future)
            raise HttpTimeoutError("Provider GET exceeded total timeout") from None
        with state_lock:
            if self._monotonic() >= deadline:
                expired = True
            else:
                result_claimed = True
        if expired:
            cleanup_expired_result(future)
            raise HttpTimeoutError("Provider GET exceeded total timeout")
        return result

    @contextmanager
    def _stream_response(
        self,
        target: _PinnedTarget,
        headers: Mapping[str, str],
        deadline: float,
    ) -> Iterator[httpx.Response]:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise HttpTimeoutError("Provider GET exceeded total timeout")
        timeout = httpx.Timeout(
            connect=min(self._policy.connect_timeout_seconds, remaining),
            read=min(self._policy.read_timeout_seconds, remaining),
            write=min(self._policy.read_timeout_seconds, remaining),
            pool=min(self._policy.connect_timeout_seconds, remaining),
        )
        response_context = self._client.stream(
            "GET",
            target.url,
            headers=headers,
            timeout=timeout,
            extensions={"sni_hostname": target.host},
        )

        def close_late_response(_: httpx.Response) -> None:
            response_context.__exit__(None, None, None)

        response = self._call_with_deadline(
            response_context.__enter__,
            deadline,
            late_cleanup=close_late_response,
        )
        try:
            yield response
        finally:
            response_context.__exit__(None, None, None)

    def _validate_url(self, url: str, deadline: float) -> _PinnedTarget:
        try:
            parsed = urllib.parse.urlsplit(url)
        except ValueError:
            raise HttpPolicyError("Provider URL is invalid") from None
        if parsed.scheme.lower() != "https":
            raise HttpPolicyError("Provider URL must use HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise HttpPolicyError("Provider URL must not contain user information")
        if parsed.fragment:
            raise HttpPolicyError("Provider URL must not contain a fragment")
        try:
            port = parsed.port
        except ValueError:
            raise HttpPolicyError("Provider URL has an invalid port") from None
        if port not in (None, 443):
            raise HttpPolicyError("Provider URL port must be 443 when present")
        host = parsed.hostname
        if host is None:
            raise HttpPolicyError("Provider URL must contain a hostname")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise HttpPolicyError("Provider URL hostname must not be an IP literal")
        host = host.lower()
        if host not in self._policy.allowed_hosts:
            raise HttpPolicyError("Provider URL hostname is not in the exact allowlist")
        try:
            addresses = self._call_with_deadline(lambda: self._resolver(host), deadline)
        except HttpTimeoutError:
            raise
        except Exception:
            raise HttpPolicyError("Provider hostname resolution failed") from None
        if not addresses:
            raise HttpPolicyError("Provider hostname did not resolve to an address")
        if any(
            not address.is_global
            or address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
            for address in addresses
        ):
            raise HttpPolicyError("Provider hostname must resolve only to global addresses")
        address = min(addresses, key=lambda value: (value.version, int(value)))
        pinned_host = f"[{address}]" if address.version == 6 else str(address)
        authority = f"{host}:443" if port == 443 else host
        pinned_url = urllib.parse.urlunsplit(
            (parsed.scheme.lower(), pinned_host, parsed.path, parsed.query, "")
        )
        return _PinnedTarget(host=host, authority=authority, url=pinned_url)

    def get(self, request: HttpRequest) -> HttpResult:
        """Perform a policy-controlled GET request."""
        if not self._policy.network_enabled:
            raise NetworkDisabledError("Provider network access is disabled")
        deadline = self._monotonic() + self._policy.total_timeout_seconds
        cache_key = _cache_key(request.url, request.accept)
        cached = self._cache.get(cache_key)
        headers: dict[str, str] = {}
        for raw_name, raw_value in request.headers.items():
            name, value = _validate_header(raw_name, raw_value)
            if name.lower() not in _PROTECTED_REQUEST_HEADER_NAMES:
                headers[name] = value
        _validate_header("Accept", request.accept)
        headers.update(
            {
                "Accept": request.accept,
                "Accept-Encoding": "identity",
                "User-Agent": self._policy.user_agent,
            }
        )
        if cached is not None:
            if cached.etag is not None:
                headers["If-None-Match"] = cached.etag
            if cached.last_modified is not None:
                headers["If-Modified-Since"] = cached.last_modified
        for name, value in headers.items():
            _validate_header(name, value)
        current_url = request.url
        attempts = 0
        redirects = 0
        while True:
            target_attempt = 0
            while True:
                if self._monotonic() >= deadline:
                    raise HttpTimeoutError(
                        f"Provider GET exceeded total timeout for {safe_url(current_url)}"
                    )
                target_attempt += 1
                attempts += 1
                try:
                    target = self._validate_url(current_url, deadline)
                except HttpPolicyError:
                    if redirects:
                        raise RedirectError("Provider redirect target was rejected") from None
                    raise
                try:
                    self._call_with_deadline(
                        partial(self._rate_limiter.acquire, target.host), deadline
                    )
                except HttpTimeoutError:
                    raise
                except Exception:
                    raise HttpPolicyError("Provider rate limiter failed") from None
                if self._monotonic() >= deadline:
                    raise HttpTimeoutError(
                        f"Provider GET exceeded total timeout for {safe_url(current_url)}"
                    )
                try:
                    wire_headers = dict(headers)
                    wire_headers["Host"] = target.authority
                    with self._stream_response(target, wire_headers, deadline) as response:
                        if self._monotonic() >= deadline:
                            raise HttpTimeoutError(
                                f"Provider GET exceeded total timeout for {safe_url(current_url)}"
                            )
                        if response.status_code in _REDIRECT_STATUS_CODES:
                            location = response.headers.get("Location")
                            if not location:
                                raise RedirectError(
                                    "Provider redirect is missing a Location header"
                                )
                            if redirects >= self._policy.max_redirects:
                                raise RedirectError("Provider redirect limit was exceeded")
                            try:
                                redirect_url = urllib.parse.urljoin(current_url, location)
                            except ValueError:
                                raise RedirectError(
                                    "Provider redirect Location is invalid"
                                ) from None
                            if _url_origin(redirect_url) != _url_origin(current_url):
                                headers = {
                                    name: value
                                    for name, value in headers.items()
                                    if not _is_sensitive_header(name)
                                }
                            current_url = redirect_url
                            redirects += 1
                            break
                        if response.status_code == 304:
                            if cached is None:
                                raise InvalidNotModifiedError(
                                    "Provider returned 304 without cached content"
                                )
                            return HttpResult(
                                status_code=304,
                                body=cached.body,
                                content_type=cached.content_type,
                                safe_url=safe_url(current_url),
                                attempts=attempts,
                                cache_status="REVALIDATED",
                                etag=cached.etag,
                                last_modified=cached.last_modified,
                            )
                        if response.status_code not in _RETRYABLE_STATUS_CODES:
                            content_length = response.headers.get("Content-Length")
                            if content_length is not None:
                                try:
                                    declared_bytes = int(content_length)
                                except ValueError:
                                    pass
                                else:
                                    if declared_bytes > self._policy.max_response_bytes:
                                        raise ResponseTooLargeError(
                                            "Provider response is too large"
                                        )
                            chunks: list[bytes] = []
                            total_bytes = 0
                            body_iterator = iter(response.iter_bytes())
                            while True:
                                try:
                                    chunk = self._call_with_deadline(
                                        partial(next, body_iterator), deadline
                                    )
                                except StopIteration:
                                    break
                                total_bytes += len(chunk)
                                if total_bytes > self._policy.max_response_bytes:
                                    raise ResponseTooLargeError("Provider response is too large")
                                chunks.append(chunk)
                            body = b"".join(chunks)
                            etag = response.headers.get("ETag")
                            last_modified = response.headers.get("Last-Modified")
                            content_type = response.headers.get("Content-Type")
                            cache_status = "MISS"
                            if 200 <= response.status_code < 300:
                                cache_status = "UPDATED" if cached is not None else "MISS"
                                self._cache.put(
                                    cache_key,
                                    CachedResponse(
                                        body=body,
                                        content_type=content_type,
                                        etag=etag,
                                        last_modified=last_modified,
                                    ),
                                )
                            return HttpResult(
                                status_code=response.status_code,
                                body=body,
                                content_type=content_type,
                                safe_url=safe_url(current_url),
                                attempts=attempts,
                                cache_status=cache_status,
                                etag=etag,
                                last_modified=last_modified,
                            )
                        if target_attempt >= self._policy.max_attempts:
                            raise RetryExhaustedError(
                                f"Provider GET retries exhausted for {safe_url(current_url)}"
                            )
                        retry_after = response.headers.get("Retry-After")
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if target_attempt >= self._policy.max_attempts:
                        if isinstance(exc, httpx.TimeoutException):
                            raise HttpTimeoutError(
                                f"Provider GET timed out for {safe_url(current_url)}"
                            ) from None
                        raise RetryExhaustedError(
                            f"Provider GET retries exhausted for {safe_url(current_url)}"
                        ) from None
                    remaining = max(0.0, deadline - self._monotonic())
                    delay = min(
                        self._policy.retry_base_delay_seconds * 2 ** (target_attempt - 1),
                        remaining,
                    )
                    if delay > 0:
                        self._sleeper(delay)
                    continue
                except httpx.RequestError:
                    raise HttpPolicyError("Provider HTTP request failed") from None
                except (httpx.HTTPError, httpx.InvalidURL):
                    raise HttpPolicyError("Provider HTTP request failed") from None
                remaining = max(0.0, deadline - self._monotonic())
                delay = min(
                    self._policy.retry_base_delay_seconds * 2 ** (target_attempt - 1),
                    remaining,
                )
                if retry_after is not None:
                    try:
                        retry_after_seconds = float(retry_after)
                    except ValueError:
                        pass
                    else:
                        if (
                            math.isfinite(retry_after_seconds)
                            and 0 <= retry_after_seconds <= remaining
                        ):
                            delay = retry_after_seconds
                if delay > 0:
                    self._sleeper(delay)
