import json

from stock_research_agent.domain.providers.http import ProviderHttpResponse
from stock_research_agent.logging import redact_sensitive_data
from stock_research_agent.providers.http_policy import CanonicalProviderRequest
from stock_research_agent.providers.http_redaction import (
    redact_provider_headers,
    safe_request_summary,
    safe_response_summary,
)

SENTINEL = "stage9-provider-secret-sentinel"


def _request() -> CanonicalProviderRequest:
    return CanonicalProviderRequest(
        endpoint_id="TEST_ENDPOINT",
        method="GET",
        scheme="https",
        host="data.example.com",
        port=443,
        path="/v1/data",
        query=(("api_key", SENTINEL), ("page", "1")),
        accepted_content_types=("application/json",),
        max_redirects=0,
        url=f"https://data.example.com/v1/data?api_key={SENTINEL}&page=1",
    )


def test_safe_request_summary_excludes_query_values_credentials_and_local_paths() -> None:
    summary = safe_request_summary(_request())
    serialized = json.dumps(summary)

    assert SENTINEL not in serialized
    assert "api_key" in serialized
    assert summary["query_keys"] == ("api_key", "page")
    assert "url" not in summary


def test_safe_response_summary_excludes_body_and_sensitive_headers() -> None:
    response = ProviderHttpResponse(
        status_code=200,
        content_type="application/json",
        body=SENTINEL.encode(),
        safe_headers={
            "Content-Type": "application/json",
            "Set-Cookie": SENTINEL,
            "X-Request-ID": "safe-id",
        },
    )
    summary = safe_response_summary(response)
    serialized = json.dumps(summary)

    assert SENTINEL not in serialized
    assert "body" not in summary
    assert summary["headers"] == {
        "Content-Type": "application/json",
        "X-Request-ID": "safe-id",
    }


def test_provider_header_redaction_uses_fixed_allowlist_and_rejects_log_injection() -> None:
    assert redact_provider_headers(
        {
            "Authorization": f"Bearer {SENTINEL}",
            "Cookie": SENTINEL,
            "Set-Cookie": SENTINEL,
            "Content-Length": "42",
            "X-Request-ID": "safe",
        }
    ) == {
        "Content-Length": "42",
        "X-Request-ID": "safe",
    }
    assert redact_provider_headers({"X-Request-ID": "safe\r\ninjected"}) == {}


def test_global_logging_redacts_provider_query_secret_and_http_userinfo() -> None:
    event = {
        "provider_url": (
            f"https://user:{SENTINEL}@data.example.com/v1/data?api_key={SENTINEL}&page=1"
        )
    }
    serialized = json.dumps(redact_sensitive_data(event))
    assert SENTINEL not in serialized
