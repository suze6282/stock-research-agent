from uuid import uuid4

import pytest

from stock_research_agent.domain.providers.http import (
    ProviderEndpointPolicy,
    ProviderExecutionContext,
    ProviderHttpRequestTemplate,
)


def test_http_template_accepts_only_endpoint_id_and_normalized_parameters() -> None:
    policy = ProviderEndpointPolicy(
        endpoint_id="SEC_SUBMISSIONS",
        policy_version="1.0.0",
        method="GET",
        scheme="https",
        host="data.sec.gov",
        port=443,
        path_template="/submissions/CIK{cik}.json",
        parameter_names=("cik",),
        query_keys=(),
        accepted_content_types=("application/json",),
        max_redirects=0,
    )
    request = ProviderHttpRequestTemplate(
        endpoint_id="SEC_SUBMISSIONS",
        parameters={"cik": "0000723125"},
        query={},
    )
    context = ProviderExecutionContext(
        provider_definition_id=uuid4(),
        provider_capability_id=uuid4(),
        policy_id=uuid4(),
        license_policy_id=uuid4(),
        authorization_id=None,
        sync_run_id=uuid4(),
        max_requests=1,
        max_response_bytes=1024,
        max_total_bytes=1024,
    )

    assert policy.endpoint_id == request.endpoint_id
    assert context.authorization_id is None


@pytest.mark.parametrize(
    "unsafe_key",
    [
        "url",
        "host",
        "path",
        "file",
        "sql",
        "headers",
        "cookie",
        "authorization",
        "credential",
        "provider",
    ],
)
def test_http_template_rejects_caller_controlled_transport_fields(
    unsafe_key: str,
) -> None:
    with pytest.raises(ValueError, match="reserved"):
        ProviderHttpRequestTemplate(
            endpoint_id="SEC_SUBMISSIONS",
            parameters={unsafe_key: "unsafe"},
            query={},
        )


def test_http_template_rejects_unbounded_or_ambiguous_values() -> None:
    with pytest.raises(ValueError):
        ProviderHttpRequestTemplate(
            endpoint_id="SEC_SUBMISSIONS",
            parameters={"cik": ["one", "two"]},
            query={},
        )
    with pytest.raises(ValueError, match="normalized"):
        ProviderHttpRequestTemplate(
            endpoint_id="SEC_SUBMISSIONS",
            parameters={"cik": " 0000723125 "},
            query={},
        )
