"""Exact policy and authorized-plan binding for the SEC Gate B pilot."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.live_evidence.gate_b_authorization import (
    AuthorizedGateBExecution,
    GateBAuthorizationValidation,
)
from stock_research_agent.domain.providers.schemas import Checksum, FrozenProviderContract
from stock_research_agent.domain.providers.sync import (
    ProviderSyncPlanRecord,
    ProviderSyncSlice,
)
from stock_research_agent.providers.http_client import HttpClientPolicy
from stock_research_agent.providers.http_policy import CanonicalProviderRequest
from stock_research_agent.providers.sec_edgar.endpoints import (
    SEC_ENDPOINT_POLICIES,
    build_sec_request,
)
from stock_research_agent.providers.sec_edgar.schemas import SecArtifactKind, normalize_cik

_GATE_B_RESOURCE_CONTRACT = (
    (
        "SEC_SUBMISSIONS",
        "SEC_SUBMISSIONS_JSON",
        SecArtifactKind.SUBMISSIONS_METADATA,
        (),
        2 * 1024 * 1024,
    ),
    (
        "SEC_FILING_INDEX",
        "SEC_FILING_DOCUMENT",
        SecArtifactKind.FILING_INDEX,
        ("SEC_SUBMISSIONS",),
        1024 * 1024,
    ),
    (
        "SEC_PRIMARY_DOCUMENT",
        "SEC_FILING_DOCUMENT",
        SecArtifactKind.PRIMARY_FILING_DOCUMENT,
        ("SEC_FILING_INDEX",),
        20 * 1024 * 1024,
    ),
)


class SecAuthorizedResource(FrozenProviderContract):
    plan_id: UUID
    plan_checksum: Checksum
    slice_id: str
    ordinal: int
    request: CanonicalProviderRequest
    artifact_kind: SecArtifactKind
    max_response_bytes: int = Field(ge=1, le=52_428_800)


class SecAuthorizedPlan(FrozenProviderContract):
    plan_id: UUID
    plan_checksum: Checksum
    resources: tuple[SecAuthorizedResource, ...] = Field(min_length=1, max_length=3)

    def require_resource(self, slice_id: str) -> SecAuthorizedResource:
        for resource in self.resources:
            if resource.slice_id == slice_id:
                return resource
        raise ValueError("SEC_PLAN_RESOURCE_NOT_FOUND")


def build_sec_http_client_policy(*, network_enabled: bool) -> HttpClientPolicy:
    """Return the fixed SEC Gate B HTTP boundary without resolved identity material."""

    return HttpClientPolicy(
        allowed_hosts=frozenset(policy.host for policy in SEC_ENDPOINT_POLICIES.values()),
        user_agent=None,
        network_enabled=network_enabled,
        connect_timeout_seconds=10,
        read_timeout_seconds=30,
        total_timeout_seconds=120,
        max_redirects=0,
        max_attempts=1,
        retryable_status_codes=frozenset(),
    )


def describe_sec_gate_b_policy() -> dict[str, object]:
    """Return a non-executable description of the fixed SEC pilot boundary."""

    policies = tuple(SEC_ENDPOINT_POLICIES.values())
    return {
        "status": "NOT_ATTEMPTED",
        "http_method": "GET",
        "allowed_hosts": sorted({policy.host for policy in policies}),
        "planned_resource_count": len(policies),
    }


def bind_sec_authorized_plan(
    execution: AuthorizedGateBExecution | GateBAuthorizationValidation,
    plan: ProviderSyncPlanRecord,
) -> SecAuthorizedPlan:
    """Rebuild exact canonical SEC resources from the authorized persisted plan."""

    if plan.id != execution.plan_id or plan.plan_checksum != execution.plan_checksum:
        raise ValueError("SEC_AUTHORIZED_PLAN_MISMATCH")
    if plan.slice_count != 3 or len(plan.slices) != 3:
        raise ValueError("SEC_PLAN_RESOURCE_INVALID")
    try:
        slices = tuple(ProviderSyncSlice.model_validate(value) for value in plan.slices)
        resources = tuple(
            _bind_resource(execution, plan, item, ordinal, expected)
            for ordinal, (item, expected) in enumerate(
                zip(slices, _GATE_B_RESOURCE_CONTRACT, strict=True)
            )
        )
    except (KeyError, TypeError, ValueError):
        raise ValueError("SEC_PLAN_RESOURCE_INVALID") from None
    return SecAuthorizedPlan(
        plan_id=plan.id,
        plan_checksum=plan.plan_checksum,
        resources=resources,
    )


def _bind_resource(
    execution: AuthorizedGateBExecution | GateBAuthorizationValidation,
    plan: ProviderSyncPlanRecord,
    item: ProviderSyncSlice,
    expected_ordinal: int,
    expected: tuple[str, str, SecArtifactKind, tuple[str, ...], int],
) -> SecAuthorizedResource:
    expected_slice, expected_endpoint, expected_kind, expected_dependencies, expected_bytes = (
        expected
    )
    parameters = item.request_parameters
    endpoint_id = _required_string(parameters, "endpoint_id")
    if (
        item.slice_id != expected_slice
        or item.ordinal != expected_ordinal
        or item.depends_on != expected_dependencies
        or endpoint_id != expected_endpoint
    ):
        raise ValueError("SEC_PLAN_RESOURCE_INVALID")
    cik = normalize_cik(_required_string(parameters, "cik"))
    if cik != execution.provider_security_identifier:
        raise ValueError("SEC_PLAN_RESOURCE_INVALID")
    allowed_keys = {
        "SEC_SUBMISSIONS_JSON": {
            "endpoint_id",
            "cik",
            "form_filters",
            "artifact_kind",
            "max_response_bytes",
        },
        "SEC_FILING_DOCUMENT": {
            "endpoint_id",
            "cik",
            "accession_number",
            "document_path",
            "form",
            "artifact_kind",
            "max_response_bytes",
        },
    }.get(endpoint_id)
    if allowed_keys is None or not set(parameters) <= allowed_keys:
        raise ValueError("SEC_PLAN_RESOURCE_INVALID")
    max_response_bytes = parameters.get("max_response_bytes")
    if (
        isinstance(max_response_bytes, bool)
        or not isinstance(max_response_bytes, int)
        or max_response_bytes != expected_bytes
    ):
        raise ValueError("SEC_PLAN_RESOURCE_INVALID")
    artifact_kind = parameters.get("artifact_kind", expected_kind.value)
    if artifact_kind != expected_kind.value:
        raise ValueError("SEC_PLAN_RESOURCE_INVALID")
    if endpoint_id == "SEC_FILING_DOCUMENT":
        request = build_sec_request(
            endpoint_id,
            cik=cik,
            accession_number=_required_string(parameters, "accession_number"),
            document_path=_required_string(parameters, "document_path"),
        )
    else:
        request = build_sec_request(endpoint_id, cik=cik)
    return SecAuthorizedResource(
        plan_id=plan.id,
        plan_checksum=plan.plan_checksum,
        slice_id=item.slice_id,
        ordinal=item.ordinal,
        request=request,
        artifact_kind=expected_kind,
        max_response_bytes=max_response_bytes,
    )


def _required_string(values: dict[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError("SEC_PLAN_RESOURCE_INVALID")
    return value
