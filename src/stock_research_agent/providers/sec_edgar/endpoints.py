"""Exact offline SEC EDGAR endpoint policies."""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType

from stock_research_agent.domain.providers.http import (
    ProviderEndpointPolicy,
    ProviderHttpRequestTemplate,
)
from stock_research_agent.providers.http_policy import (
    CanonicalProviderRequest,
    expand_endpoint,
)
from stock_research_agent.providers.sec_edgar.schemas import (
    accession_without_dashes,
    normalize_accession,
    normalize_cik,
)

SEC_ENDPOINT_POLICY_VERSION = "1.0.0"
_DOCUMENT_PATH = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,247}\.(?:htm|html|txt|xml|xsd|json|pdf)$",
    flags=re.IGNORECASE,
)


def _policy(
    *,
    endpoint_id: str,
    host: str,
    path_template: str,
    parameter_names: tuple[str, ...],
    accepted_content_types: tuple[str, ...],
) -> ProviderEndpointPolicy:
    return ProviderEndpointPolicy(
        endpoint_id=endpoint_id,
        policy_version=SEC_ENDPOINT_POLICY_VERSION,
        method="GET",
        scheme="https",
        host=host,
        port=443,
        path_template=path_template,
        parameter_names=parameter_names,
        query_keys=(),
        accepted_content_types=accepted_content_types,
        max_redirects=0,
    )


SEC_ENDPOINT_POLICIES: Mapping[str, ProviderEndpointPolicy] = MappingProxyType(
    {
        "SEC_COMPANY_FACTS_JSON": _policy(
            endpoint_id="SEC_COMPANY_FACTS_JSON",
            host="data.sec.gov",
            path_template="/api/xbrl/companyfacts/CIK{cik}.json",
            parameter_names=("cik",),
            accepted_content_types=("application/json",),
        ),
        "SEC_FILING_DOCUMENT": _policy(
            endpoint_id="SEC_FILING_DOCUMENT",
            host="www.sec.gov",
            path_template=("/Archives/edgar/data/{cik}/{accession}/{document_path}"),
            parameter_names=("accession", "cik", "document_path"),
            accepted_content_types=(
                "application/json",
                "application/pdf",
                "application/xhtml+xml",
                "application/xml",
                "text/html",
                "text/plain",
                "text/xml",
            ),
        ),
        "SEC_SUBMISSIONS_JSON": _policy(
            endpoint_id="SEC_SUBMISSIONS_JSON",
            host="data.sec.gov",
            path_template="/submissions/CIK{cik}.json",
            parameter_names=("cik",),
            accepted_content_types=("application/json",),
        ),
    }
)


def build_sec_request(
    endpoint_id: str,
    *,
    cik: str,
    accession_number: str | None = None,
    document_path: str | None = None,
) -> CanonicalProviderRequest:
    """Expand one approved SEC endpoint without accepting transport fields."""

    policy = SEC_ENDPOINT_POLICIES.get(endpoint_id)
    if policy is None:
        raise ValueError("SEC_ENDPOINT_NOT_ALLOWED")
    normalized_cik = normalize_cik(cik)
    parameters: dict[str, str]
    if endpoint_id in {"SEC_SUBMISSIONS_JSON", "SEC_COMPANY_FACTS_JSON"}:
        if accession_number is not None or document_path is not None:
            raise ValueError("SEC_ENDPOINT_ARGUMENTS_INVALID")
        parameters = {"cik": normalized_cik}
    else:
        if accession_number is None or document_path is None:
            raise ValueError("SEC_ENDPOINT_ARGUMENTS_INVALID")
        normalized_accession = normalize_accession(accession_number)
        _validate_document_path(document_path)
        parameters = {
            "cik": str(int(normalized_cik)),
            "accession": accession_without_dashes(normalized_accession),
            "document_path": document_path,
        }
    return expand_endpoint(
        policy,
        ProviderHttpRequestTemplate(
            endpoint_id=endpoint_id,
            parameters=parameters,
            query={},
        ),
    )


def _validate_document_path(value: str) -> None:
    if (
        _DOCUMENT_PATH.fullmatch(value) is None
        or value in {".", ".."}
        or ".." in value
        or "/" in value
        or "\\" in value
        or "%" in value
    ):
        raise ValueError("SEC_DOCUMENT_PATH_INVALID")
