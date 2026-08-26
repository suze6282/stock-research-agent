from __future__ import annotations

import inspect
import ipaddress
from importlib import import_module
from pathlib import Path
from urllib.parse import urlunsplit
from uuid import UUID

import httpx
import pytest
from typer.testing import CliRunner

from stock_research_agent import cli_live
from stock_research_agent.domain.live_evidence.gate_b_authorization import (
    AuthorizedGateBExecution,
)
from stock_research_agent.providers.cache import InMemoryResponseCache
from stock_research_agent.providers.errors import ProviderHttpError, RedirectError
from stock_research_agent.providers.http_client import (
    HttpClientPolicy,
    HttpRequest,
    SafeHttpClient,
)
from stock_research_agent.providers.http_policy import (
    CanonicalProviderRequest,
    ProviderRedirectPolicy,
)
from stock_research_agent.providers.retry import ProviderRetryOutcome, RetryDecision
from stock_research_agent.providers.sec_edgar import endpoints
from stock_research_agent.providers.sec_edgar.schemas import SecArtifactKind

PLAN_ID = UUID("50000000-0000-0000-0000-000000000001")
PLAN_CHECKSUM = "a" * 64


class _RateLimiter:
    def acquire(self, bucket: str) -> None:
        del bucket


def _canonical_request(**updates: object) -> CanonicalProviderRequest:
    values: dict[str, object] = {
        "endpoint_id": "SEC_FILING_DOCUMENT",
        "method": "GET",
        "scheme": "https",
        "host": "www.sec.gov",
        "port": 443,
        "path": "/Archives/edgar/data/723125/000072312525000028/mu-20250828.htm",
        "query": (),
        "accepted_content_types": ("text/html",),
        "max_redirects": 0,
        "url": (
            "https://www.sec.gov/Archives/edgar/data/723125/000072312525000028/mu-20250828.htm"
        ),
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


def _retry_contract_values() -> tuple[object, object, object]:
    policy_module = import_module("stock_research_agent.providers.sec_edgar.policy")
    retry_module = import_module("stock_research_agent.providers.sec_edgar.retry")
    execution = AuthorizedGateBExecution(
        authorization_id=UUID("60000000-0000-0000-0000-000000000001"),
        authorization_checksum="b" * 64,
        approval_id=UUID("70000000-0000-0000-0000-000000000001"),
        plan_id=PLAN_ID,
        plan_checksum=PLAN_CHECKSUM,
        provider="SEC_EDGAR_PUBLIC_V1",
        security_id=UUID("40000000-0000-0000-0000-000000000002"),
        issuer_id=UUID("30000000-0000-0000-0000-000000000002"),
        provider_security_identifier="0000723125",
        credential_reference_id=UUID("10000000-0000-0000-0000-000000000003"),
        user_agent_reference_id=UUID("10000000-0000-0000-0000-000000000004"),
    )
    resource = policy_module.SecAuthorizedResource(
        plan_id=PLAN_ID,
        plan_checksum=PLAN_CHECKSUM,
        slice_id="SEC_SUBMISSIONS",
        ordinal=0,
        request=endpoints.build_sec_request("SEC_SUBMISSIONS_JSON", cik="0000723125"),
        artifact_kind=SecArtifactKind.SUBMISSIONS_METADATA,
        max_response_bytes=1024,
    )
    permit = retry_module.SecAttemptPermit(
        authorization_id=execution.authorization_id,
        plan_id=PLAN_ID,
        plan_checksum=PLAN_CHECKSUM,
        slice_id=resource.slice_id,
        endpoint_id=resource.request.endpoint_id,
        attempt_number=1,
        kind=retry_module.SecAttemptKind.INITIAL,
        request_attempt_id=UUID(int=1),
    )
    return execution, resource, permit


class _OneGlobalRetryPort:
    def __init__(self) -> None:
        self.retry_reserved = False

    def reserve(self, request: object) -> object:
        retry_module = import_module("stock_research_agent.providers.sec_edgar.retry")
        if self.retry_reserved:
            raise ValueError("SEC_RETRY_BUDGET_EXHAUSTED")
        self.retry_reserved = True
        return retry_module.SecAttemptPermit(
            **request.model_dump(),  # type: ignore[attr-defined]
            request_attempt_id=UUID(int=2),
        )


def test_red_032_production_sec_application_constructs_exact_offline_plan() -> None:
    try:
        application = cli_live.sec_pilot_application_factory()
    except RuntimeError as error:
        pytest.fail(f"RED-032 SEC production composition missing: {error}")

    payload = application.operate("plan", PLAN_ID, PLAN_CHECKSUM)
    assert payload["status"] == "NOT_ATTEMPTED"
    assert payload["http_method"] == "GET"
    assert payload["allowed_hosts"] == ["data.sec.gov", "www.sec.gov"]
    assert payload["planned_resource_count"] == 3


@pytest.mark.parametrize("status_code", [301, 302, 303, 307, 308])
def test_red_033_redirect_response_aborts_after_one_fake_attempt(status_code: int) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status_code,
            headers={"Location": "https://www.sec.gov/other"},
            request=request,
        )

    with SafeHttpClient(
        HttpClientPolicy(
            allowed_hosts=frozenset({"www.sec.gov"}),
            user_agent="offline-gate-b-contract/test",
            network_enabled=True,
            max_redirects=0,
            max_attempts=1,
        ),
        cache=InMemoryResponseCache(),
        rate_limiter=_RateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        with pytest.raises(RedirectError):
            client.get(
                HttpRequest(
                    url="https://www.sec.gov/Archives/edgar/data/file.htm",
                    accept="text/html",
                )
            )

    assert len(calls) == 1


def test_red_035_http_429_is_never_retried_for_gate_b() -> None:
    retry_module = import_module("stock_research_agent.providers.sec_edgar.retry")
    execution, resource, permit = _retry_contract_values()
    port = _OneGlobalRetryPort()
    decision = retry_module.SecGateBRetryController().classify(
        ProviderRetryOutcome(http_status=429, error_code=None),
        execution=execution,
        resource=resource,
        previous_attempt=permit,
        reservations=port,
    )

    assert isinstance(decision, RetryDecision)
    assert decision.retry is False
    assert decision.next_attempt is None
    assert decision.reason_code == "SEC_HTTP_429_ABORT"
    assert port.retry_reserved is False


def test_red_036_retry_budget_is_global_across_the_whole_sec_plan() -> None:
    retry_module = import_module("stock_research_agent.providers.sec_edgar.retry")
    execution, resource, permit = _retry_contract_values()
    port = _OneGlobalRetryPort()
    first = retry_module.SecGateBRetryController().classify(
        ProviderRetryOutcome(http_status=503, error_code=None),
        execution=execution,
        resource=resource,
        previous_attempt=permit,
        reservations=port,
    )
    second_endpoint = retry_module.SecGateBRetryController().classify(
        ProviderRetryOutcome(http_status=None, error_code="READ_TIMEOUT"),
        execution=execution,
        resource=resource.model_copy(update={"slice_id": "SEC_COMPANY_FACTS"}),
        previous_attempt=permit.model_copy(update={"slice_id": "SEC_COMPANY_FACTS"}),
        reservations=port,
    )

    assert isinstance(first, retry_module.SecAttemptPermit)
    assert isinstance(second_endpoint, RetryDecision)
    assert second_endpoint.retry is False
    assert second_endpoint.reason_code == "SEC_RETRY_BUDGET_EXHAUSTED"


def test_red_037_production_sec_timeout_configuration_matches_runbook() -> None:
    generic_policy = HttpClientPolicy(
        allowed_hosts=frozenset({"data.sec.gov", "www.sec.gov"}),
        user_agent="offline-gate-b-contract/test",
    )
    policy_module = import_module("stock_research_agent.providers.sec_edgar.policy")
    policy = policy_module.build_sec_http_client_policy(network_enabled=False)

    assert generic_policy.connect_timeout_seconds == 5
    assert generic_policy.read_timeout_seconds == 15
    assert generic_policy.total_timeout_seconds == 30
    assert policy.connect_timeout_seconds == 10
    assert policy.read_timeout_seconds == 30
    assert policy.total_timeout_seconds == 120
    assert policy.max_redirects == 0
    assert policy.max_attempts == 1


def test_red_038_declared_contact_identity_contract_is_defined_without_secret_output() -> None:
    identity_module = import_module("stock_research_agent.providers.sec_edgar.request_identity")
    credentials_module = import_module("stock_research_agent.providers.credentials")
    protected = credentials_module.ProtectedRequestIdentity("SECRET_SENTINEL_DO_NOT_LOG")

    assert callable(identity_module.resolve_sec_request_identity)
    assert repr(protected) == "<ProtectedRequestIdentity redacted>"
    assert "SECRET_SENTINEL_DO_NOT_LOG" not in repr(protected)
    with pytest.raises(TypeError, match="cannot be serialized"):
        protected.__reduce__()


def test_red_039_production_sec_allowlist_policy_exists_before_send() -> None:
    policy_module = import_module("stock_research_agent.providers.sec_edgar.policy")
    policy_factory = getattr(policy_module, "build_sec_http_client_policy", None)

    assert callable(policy_factory), (
        "RED-039 exact SEC allowlist is not bound into a production transport policy"
    )
    policy = policy_factory(network_enabled=False)
    assert policy.allowed_hosts == frozenset({"data.sec.gov", "www.sec.gov"})


def test_existing_http_boundary_rejects_host_tricks_before_fake_send_or_dns() -> None:
    transport_calls: list[httpx.Request] = []
    resolver_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        transport_calls.append(request)
        return httpx.Response(200, content=b"unexpected", request=request)

    def resolver(host: str) -> tuple[ipaddress.IPv4Address, ...]:
        resolver_calls.append(host)
        return (ipaddress.ip_address("93.184.216.34"),)

    policy = HttpClientPolicy(
        allowed_hosts=frozenset({"data.sec.gov", "www.sec.gov"}),
        user_agent="offline-gate-b-contract/test",
        network_enabled=True,
    )
    invalid_urls = (
        "https://www.sec.gov.evil.example/file",
        "https://data.sec.gov.evil.example/file",
        "https://127.0.0.1/file",
        "https://user@www.sec.gov/file",
        "http://www.sec.gov/file",
        "https://www.sec.gov:444/file",
    )
    with SafeHttpClient(
        policy,
        cache=InMemoryResponseCache(),
        rate_limiter=_RateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=resolver,
    ) as client:
        for url in invalid_urls:
            with pytest.raises(ProviderHttpError):
                client.get(HttpRequest(url=url, accept="text/html"))

    assert resolver_calls == []
    assert transport_calls == []


def test_red_041_sec_public_api_has_no_operator_raw_url_entrypoint() -> None:
    signature = inspect.signature(endpoints.build_sec_request)

    assert "url" not in signature.parameters
    with pytest.raises(ValueError, match="SEC_ENDPOINT_NOT_ALLOWED"):
        endpoints.build_sec_request("ARBITRARY_URL", cik="0000723125")


def test_red_042_default_sec_failure_has_no_live_or_fixture_success_fallback() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli_live.live_app,
        ["sec", "run", str(PLAN_ID), PLAN_CHECKSUM, "--json"],
    )

    assert result.exit_code == 3
    assert "LIVE_TRANSPORT_NOT_CONFIGURED" in result.stdout
    assert "LIVE_VALIDATION_PASS" not in result.stdout
    assert "fixture" not in result.stdout.casefold()
    assert "synthetic" not in result.stdout.casefold()


def test_red_043_production_sec_pipeline_validates_before_artifact_persistence() -> None:
    signature = inspect.signature(cli_live.authorized_sec_pilot_application_factory)

    assert "transport" in signature.parameters
    assert "settlement" in signature.parameters
    assert "documents" in signature.parameters
    assert "data_quality" in signature.parameters
    assert (
        cli_live.sec_pilot_application_factory().operate("run", PLAN_ID, PLAN_CHECKSUM)["status"]
        == "BLOCKED"
    )


def test_red_046_production_sec_run_requires_authorization_before_transport() -> None:
    try:
        application = cli_live.sec_pilot_application_factory()
    except RuntimeError as error:
        pytest.fail(f"RED-046 authorization-gated SEC application missing: {error}")

    assert callable(getattr(application, "operate", None))
    assert hasattr(application, "authorization_gate")


def test_production_sec_shell_returns_no_executable_path_without_authorized_context() -> None:
    application = cli_live.sec_pilot_application_factory()

    payload = application.operate("run", PLAN_ID, PLAN_CHECKSUM)

    assert payload["status"] == "BLOCKED"
    assert payload["warning_codes"] == [
        "LIVE_AUTHORIZATION_REQUIRED",
        "LIVE_TRANSPORT_NOT_CONFIGURED",
    ]
    assert "execution_capability" not in payload


def test_red_048_gate_b_modules_have_no_model_runtime_dependency() -> None:
    roots = (
        Path("src/stock_research_agent/cli_live.py"),
        Path("src/stock_research_agent/providers/sec_edgar"),
        Path("src/stock_research_agent/providers/http_executor.py"),
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for root in roots
        for path in ([root] if root.is_file() else sorted(root.glob("*.py")))
    ).casefold()

    assert "openai" not in source
    assert "model_client" not in source
    assert "call_model" not in source


def test_red_049_production_gate_b_stops_at_data_quality() -> None:
    from stock_research_agent.domain.live_evidence.gate_b_pilot import LiveValidationResult

    fields = LiveValidationResult.model_fields
    assert fields["terminal_stage"].default == "DATA_QUALITY"
    for field in (
        "snapshot_created",
        "research_request_created",
        "agent_run_created",
        "claim_created",
        "report_created",
        "stage_11_started",
    ):
        assert fields[field].default is False


def test_existing_sec_endpoint_templates_are_exact_get_only_and_redirect_free() -> None:
    policies = endpoints.SEC_ENDPOINT_POLICIES

    assert {policy.host for policy in policies.values()} == {"data.sec.gov", "www.sec.gov"}
    assert all(policy.method == "GET" for policy in policies.values())
    assert all(policy.scheme == "https" for policy in policies.values())
    assert all(policy.port == 443 for policy in policies.values())
    assert all(policy.max_redirects == 0 for policy in policies.values())


def test_existing_zero_redirect_policy_rejects_even_same_origin() -> None:
    origin = _canonical_request()
    target = _canonical_request(path="/other")

    decision = ProviderRedirectPolicy.evaluate(origin, target, count=0)

    assert decision.allowed is False
    assert decision.reason_code == "REDIRECT_LIMIT_EXCEEDED"
