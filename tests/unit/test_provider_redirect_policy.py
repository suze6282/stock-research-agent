from urllib.parse import urlunsplit

import pytest

from stock_research_agent.providers.http_policy import (
    CanonicalProviderRequest,
    ProviderRedirectPolicy,
)


def _request(**updates: object) -> CanonicalProviderRequest:
    values: dict[str, object] = {
        "endpoint_id": "TEST_ENDPOINT",
        "method": "GET",
        "scheme": "https",
        "host": "data.example.com",
        "port": 443,
        "path": "/v1/data",
        "query": (),
        "accepted_content_types": ("application/json",),
        "max_redirects": 1,
        "url": "https://data.example.com/v1/data",
    }
    values.update(updates)
    if "url" not in updates:
        scheme = str(values["scheme"])
        host = str(values["host"])
        port = int(values["port"])
        path = str(values["path"])
        authority = host if port == 443 else f"{host}:{port}"
        values["url"] = urlunsplit((scheme, authority, path, "", ""))
    return CanonicalProviderRequest(**values)


def test_same_origin_bounded_redirect_is_allowed_without_credential_forwarding() -> None:
    decision = ProviderRedirectPolicy.evaluate(
        _request(),
        _request(path="/v1/data/next"),
        count=0,
    )
    assert decision.allowed is True
    assert decision.forward_credentials is False


@pytest.mark.parametrize(
    ("target", "count", "reason"),
    [
        (_request(host="other.example.com"), 0, "REDIRECT_HOST_DENIED"),
        (_request(scheme="http"), 0, "REDIRECT_SCHEME_DENIED"),
        (_request(port=444), 0, "REDIRECT_PORT_DENIED"),
        (_request(path="/v1/../secret"), 0, "REDIRECT_PATH_DENIED"),
        (_request(), 1, "REDIRECT_LIMIT_EXCEEDED"),
    ],
)
def test_redirect_policy_rejects_cross_origin_downgrade_traversal_and_limit(
    target: CanonicalProviderRequest,
    count: int,
    reason: str,
) -> None:
    decision = ProviderRedirectPolicy.evaluate(_request(), target, count)
    assert decision.allowed is False
    assert decision.reason_code == reason
    assert decision.forward_credentials is False


def test_zero_redirect_policy_denies_even_same_origin() -> None:
    origin = _request(max_redirects=0)
    decision = ProviderRedirectPolicy.evaluate(origin, _request(), count=0)
    assert decision.allowed is False
    assert decision.reason_code == "REDIRECT_LIMIT_EXCEEDED"
