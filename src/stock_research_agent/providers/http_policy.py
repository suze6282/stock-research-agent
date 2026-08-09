"""Deterministic endpoint expansion and transport-address policy."""

from __future__ import annotations

import re
from ipaddress import IPv4Address, IPv6Address, ip_address
from urllib.parse import quote, urlencode

from pydantic import Field

from stock_research_agent.domain.providers.http import (
    ProviderEndpointPolicy,
    ProviderHttpRequestTemplate,
)
from stock_research_agent.domain.providers.schemas import FrozenProviderContract

_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]{0,63})\}")
_DNS_NAME = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)


class CanonicalProviderRequest(FrozenProviderContract):
    endpoint_id: str
    method: str
    scheme: str
    host: str
    port: int
    path: str
    query: tuple[tuple[str, str], ...]
    accepted_content_types: tuple[str, ...]
    max_redirects: int = Field(ge=0, le=5)
    url: str


class ProviderAddressPolicy:
    """Validate and pin one public DNS result set for an execution lifetime."""

    def __init__(self) -> None:
        self._pinned: dict[str, tuple[str, ...]] = {}

    def validate(
        self,
        host: str,
        resolved_addresses: tuple[str, ...],
    ) -> tuple[str, ...]:
        canonical_host = _canonical_host(host)
        if not resolved_addresses:
            raise ValueError("PROVIDER_ADDRESS_SET_EMPTY")
        parsed: list[IPv4Address | IPv6Address] = []
        try:
            parsed = [ip_address(value) for value in resolved_addresses]
        except ValueError as exc:
            raise ValueError("PROVIDER_ADDRESS_INVALID") from exc
        if any(
            not address.is_global
            or address.is_multicast
            or address.is_loopback
            or address.is_link_local
            or address.is_private
            or address.is_reserved
            or address.is_unspecified
            or (isinstance(address, IPv6Address) and address.ipv4_mapped is not None)
            for address in parsed
        ):
            raise ValueError("PROVIDER_ADDRESS_FORBIDDEN")
        normalized = tuple(
            str(address)
            for address in sorted(set(parsed), key=lambda item: (item.version, int(item)))
        )
        pinned = self._pinned.get(canonical_host)
        if pinned is not None and pinned != normalized:
            raise ValueError("PROVIDER_DNS_REBINDING")
        self._pinned[canonical_host] = normalized
        return normalized


class ProviderRedirectDecision(FrozenProviderContract):
    allowed: bool
    reason_code: str
    forward_credentials: bool = False


class ProviderRedirectPolicy:
    """Permit only an explicitly bounded same-origin canonical redirect."""

    @staticmethod
    def evaluate(
        origin: CanonicalProviderRequest,
        target: CanonicalProviderRequest,
        count: int,
    ) -> ProviderRedirectDecision:
        checks = (
            (
                count < 0 or count >= origin.max_redirects,
                "REDIRECT_LIMIT_EXCEEDED",
            ),
            (
                target.scheme != "https" or target.scheme != origin.scheme,
                "REDIRECT_SCHEME_DENIED",
            ),
            (
                target.host != origin.host,
                "REDIRECT_HOST_DENIED",
            ),
            (
                target.port != origin.port or target.port != 443,
                "REDIRECT_PORT_DENIED",
            ),
            (
                _unsafe_redirect_path(target.path),
                "REDIRECT_PATH_DENIED",
            ),
        )
        for failed, reason in checks:
            if failed:
                return ProviderRedirectDecision(
                    allowed=False,
                    reason_code=reason,
                )
        return ProviderRedirectDecision(
            allowed=True,
            reason_code="REDIRECT_SAME_ORIGIN_ALLOWED",
        )


def expand_endpoint(
    policy: ProviderEndpointPolicy,
    template: ProviderHttpRequestTemplate,
) -> CanonicalProviderRequest:
    if policy.endpoint_id != template.endpoint_id:
        raise ValueError("ENDPOINT_ID_MISMATCH")
    expected_parameters = set(policy.parameter_names)
    if set(template.parameters) != expected_parameters:
        raise ValueError("ENDPOINT_PARAMETERS_MISMATCH")
    if not set(template.query) <= set(policy.query_keys):
        raise ValueError("ENDPOINT_QUERY_NOT_ALLOWED")

    host = _canonical_host(policy.host)
    path = policy.path_template
    placeholders = set(_PLACEHOLDER.findall(path))
    if placeholders != expected_parameters:
        raise ValueError("ENDPOINT_POLICY_PLACEHOLDERS_MISMATCH")
    for name in policy.parameter_names:
        value = template.parameters[name]
        if _unsafe_path_parameter(value):
            raise ValueError("ENDPOINT_PARAMETER_UNSAFE")
        path = path.replace(f"{{{name}}}", quote(value, safe=""))
    if not path.startswith("/") or "\\" in path or "/../" in f"{path}/" or "/./" in f"{path}/":
        raise ValueError("ENDPOINT_PATH_UNSAFE")

    query = tuple(sorted(template.query.items()))
    query_string = urlencode(query, doseq=False, safe="")
    authority = host if policy.port == 443 else f"{host}:{policy.port}"
    url = f"{policy.scheme}://{authority}{path}"
    if query_string:
        url = f"{url}?{query_string}"
    return CanonicalProviderRequest(
        endpoint_id=policy.endpoint_id,
        method=policy.method,
        scheme=policy.scheme,
        host=host,
        port=policy.port,
        path=path,
        query=query,
        accepted_content_types=policy.accepted_content_types,
        max_redirects=policy.max_redirects,
        url=url,
    )


def _canonical_host(value: str) -> str:
    try:
        host = value.encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise ValueError("ENDPOINT_HOST_INVALID") from exc
    if len(host) > 253 or _DNS_NAME.fullmatch(host) is None:
        raise ValueError("ENDPOINT_HOST_INVALID")
    return host


def _unsafe_path_parameter(value: str) -> bool:
    lowered = value.casefold()
    return (
        value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "%" in value
        or "%2e" in lowered
        or "%2f" in lowered
        or "%5c" in lowered
    )


def _unsafe_redirect_path(value: str) -> bool:
    lowered = value.casefold()
    segments = value.split("/")
    return (
        not value.startswith("/")
        or "\\" in value
        or any(segment in {".", ".."} for segment in segments)
        or "%2e" in lowered
        or "%2f" in lowered
        or "%5c" in lowered
    )
