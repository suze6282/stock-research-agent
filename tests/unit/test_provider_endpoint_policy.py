import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers.http import (
    ProviderEndpointPolicy,
    ProviderHttpRequestTemplate,
)
from stock_research_agent.providers.http_policy import expand_endpoint


def _policy(**updates: object) -> ProviderEndpointPolicy:
    values: dict[str, object] = {
        "endpoint_id": "SEC_SUBMISSIONS",
        "policy_version": "1.0.0",
        "method": "GET",
        "scheme": "https",
        "host": "data.sec.gov",
        "port": 443,
        "path_template": "/submissions/CIK{cik}.json",
        "parameter_names": ("cik",),
        "query_keys": ("page",),
        "accepted_content_types": ("application/json",),
        "max_redirects": 0,
    }
    values.update(updates)
    return ProviderEndpointPolicy(**values)


def test_expand_endpoint_returns_canonical_https_request() -> None:
    result = expand_endpoint(
        _policy(),
        ProviderHttpRequestTemplate(
            endpoint_id="SEC_SUBMISSIONS",
            parameters={"cik": "0000723125"},
            query={"page": "1"},
        ),
    )

    assert result.scheme == "https"
    assert result.host == "data.sec.gov"
    assert result.port == 443
    assert result.path == "/submissions/CIK0000723125.json"
    assert result.query == (("page", "1"),)
    assert result.url == "https://data.sec.gov/submissions/CIK0000723125.json?page=1"


@pytest.mark.parametrize("value", ["..", "%2e%2e", "../secret", "one/two", "\\secret"])
def test_expand_endpoint_rejects_encoded_or_plain_traversal(value: str) -> None:
    with pytest.raises(ValueError, match="ENDPOINT_PARAMETER_UNSAFE"):
        expand_endpoint(
            _policy(),
            ProviderHttpRequestTemplate(
                endpoint_id="SEC_SUBMISSIONS",
                parameters={"cik": value},
                query={},
            ),
        )


def test_expand_endpoint_rejects_endpoint_and_query_widening() -> None:
    with pytest.raises(ValueError, match="ENDPOINT_ID_MISMATCH"):
        expand_endpoint(
            _policy(),
            ProviderHttpRequestTemplate(
                endpoint_id="OTHER_ENDPOINT",
                parameters={"cik": "0000723125"},
                query={},
            ),
        )
    with pytest.raises(ValueError, match="ENDPOINT_QUERY_NOT_ALLOWED"):
        expand_endpoint(
            _policy(),
            ProviderHttpRequestTemplate(
                endpoint_id="SEC_SUBMISSIONS",
                parameters={"cik": "0000723125"},
                query={"other": "1"},
            ),
        )


def test_endpoint_policy_rejects_scheme_port_userinfo_fragment_and_wildcard() -> None:
    for updates in (
        {"scheme": "http"},
        {"port": 80},
        {"host": "user@data.sec.gov"},
        {"host": "*.sec.gov"},
        {"path_template": "/submissions/{cik}#fragment"},
    ):
        with pytest.raises(ValidationError):
            _policy(**updates)


def test_unicode_host_is_canonicalized_with_idna() -> None:
    result = expand_endpoint(
        _policy(host="例子.公司"),
        ProviderHttpRequestTemplate(
            endpoint_id="SEC_SUBMISSIONS",
            parameters={"cik": "0000723125"},
            query={},
        ),
    )
    assert result.host == "xn--fsqu00a.xn--55qx5d"
