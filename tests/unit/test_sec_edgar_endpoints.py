from __future__ import annotations

import inspect
from importlib import import_module

import pytest


def _endpoints() -> object:
    return import_module("stock_research_agent.providers.sec_edgar.endpoints")


def test_sec_endpoint_policies_are_exact_https_templates() -> None:
    endpoints = _endpoints()
    policies = endpoints.SEC_ENDPOINT_POLICIES  # type: ignore[attr-defined]

    assert tuple(policies) == (
        "SEC_COMPANY_FACTS_JSON",
        "SEC_FILING_DOCUMENT",
        "SEC_SUBMISSIONS_JSON",
    )
    assert policies["SEC_SUBMISSIONS_JSON"].host == "data.sec.gov"
    assert policies["SEC_COMPANY_FACTS_JSON"].host == "data.sec.gov"
    assert policies["SEC_FILING_DOCUMENT"].host == "www.sec.gov"
    assert all(policy.scheme == "https" for policy in policies.values())
    assert all(policy.port == 443 for policy in policies.values())
    assert all(policy.method == "GET" for policy in policies.values())
    assert all(policy.query_keys == () for policy in policies.values())
    assert all(policy.max_redirects == 0 for policy in policies.values())


def test_sec_requests_expand_only_validated_identifiers() -> None:
    endpoints = _endpoints()

    submissions = endpoints.build_sec_request(  # type: ignore[attr-defined]
        "SEC_SUBMISSIONS_JSON",
        cik="723125",
    )
    company_facts = endpoints.build_sec_request(  # type: ignore[attr-defined]
        "SEC_COMPANY_FACTS_JSON",
        cik="0000723125",
    )
    document = endpoints.build_sec_request(  # type: ignore[attr-defined]
        "SEC_FILING_DOCUMENT",
        cik="0000723125",
        accession_number="0000723125-25-000028",
        document_path="mu-20250828.htm",
    )

    assert submissions.url == "https://data.sec.gov/submissions/CIK0000723125.json"
    assert company_facts.url == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000723125.json"
    assert document.url == (
        "https://www.sec.gov/Archives/edgar/data/723125/000072312525000028/mu-20250828.htm"
    )


@pytest.mark.parametrize(
    "document_path",
    (
        "../secret.htm",
        "%2e%2e%2fsecret.htm",
        "folder/document.htm",
        r"folder\document.htm",
        "document.exe",
        "https://evil.example/document.htm",
        "document.htm?download=1",
    ),
)
def test_sec_archive_rejects_traversal_or_unapproved_document_path(
    document_path: str,
) -> None:
    endpoints = _endpoints()

    with pytest.raises(ValueError):
        endpoints.build_sec_request(  # type: ignore[attr-defined]
            "SEC_FILING_DOCUMENT",
            cik="0000723125",
            accession_number="0000723125-25-000028",
            document_path=document_path,
        )


def test_sec_endpoint_api_rejects_widening_and_arbitrary_urls() -> None:
    endpoints = _endpoints()
    signature = inspect.signature(endpoints.build_sec_request)  # type: ignore[attr-defined]

    assert "url" not in signature.parameters
    assert "host" not in signature.parameters
    assert "query" not in signature.parameters
    with pytest.raises(ValueError, match="SEC_ENDPOINT_NOT_ALLOWED"):
        endpoints.build_sec_request("SEC_OTHER", cik="0000723125")  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="SEC_ENDPOINT_ARGUMENTS_INVALID"):
        endpoints.build_sec_request(  # type: ignore[attr-defined]
            "SEC_SUBMISSIONS_JSON",
            cik="0000723125",
            document_path="mu-20250828.htm",
        )


def test_sec_endpoint_policy_map_cannot_be_replaced_at_runtime() -> None:
    endpoints = _endpoints()

    with pytest.raises(TypeError):
        endpoints.SEC_ENDPOINT_POLICIES["SEC_SUBMISSIONS_JSON"] = object()  # type: ignore[attr-defined,index]
