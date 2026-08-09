"""Fixed-allowlist Provider HTTP telemetry summaries."""

from __future__ import annotations

from collections.abc import Mapping

from stock_research_agent.domain.providers.http import ProviderHttpResponse
from stock_research_agent.providers.http_policy import CanonicalProviderRequest

_SAFE_HEADERS = frozenset(
    {
        "content-length",
        "content-type",
        "date",
        "etag",
        "last-modified",
        "x-request-id",
    }
)


def redact_provider_headers(headers: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in headers.items():
        if key.casefold() not in _SAFE_HEADERS:
            continue
        if (
            not 1 <= len(key) <= 64
            or not 1 <= len(value) <= 256
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            continue
        result[key] = value
    return dict(sorted(result.items(), key=lambda item: item[0].casefold()))


def safe_request_summary(request: CanonicalProviderRequest) -> dict[str, object]:
    return {
        "endpoint_id": request.endpoint_id,
        "method": request.method,
        "scheme": request.scheme,
        "host": request.host,
        "port": request.port,
        "path": request.path,
        "query_keys": tuple(key for key, _value in request.query),
        "max_redirects": request.max_redirects,
    }


def safe_response_summary(response: ProviderHttpResponse) -> dict[str, object]:
    return {
        "status_code": response.status_code,
        "content_type": response.content_type,
        "byte_count": len(response.body),
        "headers": redact_provider_headers(response.safe_headers),
    }
