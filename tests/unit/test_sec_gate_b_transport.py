from __future__ import annotations

import inspect
import ipaddress
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from importlib import import_module
from uuid import UUID

import httpx
import pytest

from stock_research_agent import cli_live
from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.gate_b_authorization import (
    AuthorizedGateBExecution,
)
from stock_research_agent.domain.providers.credentials import (
    CredentialReferenceRecord,
    CredentialResolverKind,
)
from stock_research_agent.domain.providers.enums import ProviderCredentialStatus
from stock_research_agent.domain.providers.sync import ProviderSyncPlanRecord
from stock_research_agent.providers.cache import InMemoryResponseCache
from stock_research_agent.providers.credentials import EnvironmentCredentialResolver
from stock_research_agent.providers.errors import HttpPolicyError
from stock_research_agent.providers.http_client import HttpRequest, SafeHttpClient


class _RateLimiter:
    def acquire(self, bucket: str) -> None:
        del bucket


class _CountingIdentityResolver(EnvironmentCredentialResolver):
    def __init__(self, environment: dict[str, str]) -> None:
        super().__init__(environment)
        self.calls = 0

    def resolve_request_identity(self, reference: object, request: object) -> object:
        self.calls += 1
        return super().resolve_request_identity(reference, request)  # type: ignore[arg-type]


class _ReservationPort:
    def __init__(self, *, max_reservations: int = 4, wrong_authorization: bool = False) -> None:
        self.max_reservations = max_reservations
        self.wrong_authorization = wrong_authorization
        self.requests: list[object] = []

    def reserve(self, request: object) -> object:
        retry_module = import_module("stock_research_agent.providers.sec_edgar.retry")
        if len(self.requests) >= self.max_reservations:
            raise ValueError("SEC_ATTEMPT_BUDGET_EXHAUSTED")
        self.requests.append(request)
        authorization_id = request.authorization_id  # type: ignore[attr-defined]
        if self.wrong_authorization:
            authorization_id = UUID("60000000-0000-0000-0000-000000000099")
        values = request.model_dump()  # type: ignore[attr-defined]
        values["authorization_id"] = authorization_id
        return retry_module.SecAttemptPermit(
            **values,
            request_attempt_id=UUID(int=len(self.requests)),
        )


class _GlobalRetryReservationPort:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.requests: list[object] = []
        self.retry_reserved = False

    def reserve(self, request: object) -> object:
        retry_module = import_module("stock_research_agent.providers.sec_edgar.retry")
        kind = request.kind  # type: ignore[attr-defined]
        if kind is retry_module.SecAttemptKind.RETRY:
            self.events.append("retry_eligibility_checked")
            if self.retry_reserved:
                raise ValueError("SEC_RETRY_BUDGET_EXHAUSTED")
            self.retry_reserved = True
            self.events.append("retry_reserved")
        self.requests.append(request)
        self.events.append("reservation_commit")
        return retry_module.SecAttemptPermit(
            **request.model_dump(),  # type: ignore[attr-defined]
            request_attempt_id=UUID(int=len(self.requests)),
        )


class _NeverRetry:
    def classify(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        retry_module = import_module("stock_research_agent.providers.retry")
        return retry_module.RetryDecision(
            retry=False,
            reason_code="SEC_RETRY_NOT_ELIGIBLE",
            next_attempt=None,
            delay_seconds=Decimal(0),
            resolve_credential_again=False,
        )


NOW = datetime(2026, 8, 14, tzinfo=UTC)
PLAN_ID = UUID("50000000-0000-0000-0000-000000000001")
PLAN_CHECKSUM = "a" * 64


def _execution() -> AuthorizedGateBExecution:
    return AuthorizedGateBExecution(
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


def _slice(
    slice_id: str,
    ordinal: int,
    endpoint_id: str,
    **parameters: object,
) -> dict[str, object]:
    return {
        "slice_id": slice_id,
        "ordinal": ordinal,
        "range_start": date(2025, 8, 13),
        "range_end": date(2025, 8, 13),
        "depends_on": (),
        "request_parameters": {
            "endpoint_id": endpoint_id,
            "cik": "0000723125",
            "max_response_bytes": 1024,
            **parameters,
        },
    }


def _plan(**updates: object) -> ProviderSyncPlanRecord:
    values: dict[str, object] = {
        "sync_request_id": UUID("50000000-0000-0000-0000-000000000002"),
        "adapter_version": "1.0.0",
        "checkpoint_revision": None,
        "slices": (
            _slice(
                "SEC_SUBMISSIONS",
                0,
                "SEC_SUBMISSIONS_JSON",
                max_response_bytes=2 * 1024 * 1024,
            ),
            _slice(
                "SEC_FILING_INDEX",
                1,
                "SEC_FILING_DOCUMENT",
                accession_number="0000723125-25-000028",
                document_path="index.json",
                form="10-K",
                max_response_bytes=1024 * 1024,
            ),
            _slice(
                "SEC_PRIMARY_DOCUMENT",
                2,
                "SEC_FILING_DOCUMENT",
                accession_number="0000723125-25-000028",
                document_path="mu-20250828.htm",
                form="10-K",
                max_response_bytes=20 * 1024 * 1024,
            ),
        ),
        "plan_checksum": PLAN_CHECKSUM,
        "id": PLAN_ID,
        "slice_count": 3,
        "created_at": NOW,
    }
    values.update(updates)
    slices = list(values["slices"])  # type: ignore[arg-type]
    if len(slices) == 3 and tuple(item["slice_id"] for item in slices) == (
        "SEC_SUBMISSIONS",
        "SEC_FILING_INDEX",
        "SEC_PRIMARY_DOCUMENT",
    ):
        slices[1] = {**slices[1], "depends_on": ("SEC_SUBMISSIONS",)}
        slices[2] = {**slices[2], "depends_on": ("SEC_FILING_INDEX",)}
        values["slices"] = tuple(slices)
    return ProviderSyncPlanRecord(**values)


def _contact_reference(**updates: object) -> CredentialReferenceRecord:
    values: dict[str, object] = {
        "provider_definition_id": UUID("10000000-0000-0000-0000-000000000001"),
        "reference_version": "1.0.0",
        "resolver_kind": CredentialResolverKind.ENVIRONMENT,
        "declared_name": "SEC_EDGAR_CONTACT_IDENTITY",
        "status": ProviderCredentialStatus.CONFIGURED_METADATA_ONLY,
        "safe_label": "SEC EDGAR contact identity",
        "id": _execution().user_agent_reference_id,
        "checksum": "6" * 64,
        "created_at": NOW,
    }
    values.update(updates)
    return CredentialReferenceRecord(**values)


@pytest.mark.parametrize(
    ("endpoint_id", "forged_parameters"),
    (
        ("SEC_SUBMISSIONS_JSON", {"cik": "0000000001"}),
        ("SEC_SUBMISSIONS_JSON", {"host": "www.sec.gov.evil.example"}),
        ("SEC_SUBMISSIONS_JSON", {"path": "/Archives/forged"}),
        ("SEC_UNKNOWN_RESOURCE", {}),
        (
            "SEC_FILING_DOCUMENT",
            {
                "accession_number": "0000723125-25-000028",
                "document_path": "https://evil.example/forged.htm",
            },
        ),
    ),
)
def test_red_039_authorized_plan_rejects_forged_host_path_or_cik_before_sender(
    endpoint_id: str,
    forged_parameters: dict[str, object],
) -> None:
    policy_module = import_module("stock_research_agent.providers.sec_edgar.policy")
    binder = policy_module.bind_sec_authorized_plan
    send_calls: list[str] = []

    authorized = binder(_execution(), _plan())
    assert tuple(resource.request.endpoint_id for resource in authorized.resources) == (
        "SEC_SUBMISSIONS_JSON",
        "SEC_FILING_DOCUMENT",
        "SEC_FILING_DOCUMENT",
    )

    forged_slice = _slice("SEC_FORGED", 0, endpoint_id)
    forged_slice["request_parameters"] = {
        **forged_slice["request_parameters"],  # type: ignore[dict-item]
        **forged_parameters,
    }
    forged = _plan(slices=(forged_slice,), slice_count=1)

    with pytest.raises(ValueError, match="SEC_PLAN_RESOURCE_INVALID"):
        binder(_execution(), forged)

    assert send_calls == []


@pytest.mark.parametrize(
    "value",
    ("", "x" * 257, "contact\rvalue", "contact\nvalue", "contact\x7fvalue"),
)
def test_red_038_invalid_contact_material_fails_without_value_leak(value: str) -> None:
    credentials_module = import_module("stock_research_agent.providers.credentials")
    protected_type = credentials_module.ProtectedRequestIdentity

    with pytest.raises(ValueError, match="SEC_CONTACT_IDENTITY_INVALID") as error:
        protected_type(value)

    if value:
        assert value not in str(error.value)


def test_red_038_sec_identity_requires_authorized_matching_reference() -> None:
    identity_module = import_module("stock_research_agent.providers.sec_edgar.request_identity")
    sentinel = "SECRET_SENTINEL_DO_NOT_LOG"
    resolver = EnvironmentCredentialResolver({"SEC_EDGAR_CONTACT_IDENTITY": sentinel})

    protected = identity_module.resolve_sec_request_identity(
        _execution(),
        _contact_reference(),
        resolver,
    )
    assert repr(protected) == "<ProtectedRequestIdentity redacted>"
    assert sentinel not in repr(protected)

    with pytest.raises(ValueError, match="SEC_CONTACT_REFERENCE_INVALID"):
        identity_module.resolve_sec_request_identity(
            _execution(),
            _contact_reference(id=UUID("10000000-0000-0000-0000-000000000099")),
            resolver,
        )


def test_red_038_protected_identity_unwraps_only_at_final_user_agent_emission() -> None:
    credentials_module = import_module("stock_research_agent.providers.credentials")
    policy_module = import_module("stock_research_agent.providers.sec_edgar.policy")
    sentinel = "SECRET_SENTINEL_DO_NOT_LOG"
    protected = credentials_module.ProtectedRequestIdentity(sentinel)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"offline", request=request)

    with SafeHttpClient(
        policy_module.build_sec_http_client_policy(network_enabled=True),
        cache=InMemoryResponseCache(),
        rate_limiter=_RateLimiter(),
        request_identity=protected,
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        result = client.get(
            HttpRequest(
                url="https://data.sec.gov/submissions/CIK0000723125.json",
                accept="application/json",
                headers={"User-Agent": "operator-override"},
            )
        )

    assert len(requests) == 1
    assert requests[0].headers["User-Agent"] == sentinel
    assert sentinel not in repr(protected)
    assert sentinel not in repr(result)


@pytest.mark.parametrize("status_code", [429, 503])
def test_sec_policy_performs_one_physical_attempt_for_429_and_503(
    status_code: int,
) -> None:
    credentials_module = import_module("stock_research_agent.providers.credentials")
    policy_module = import_module("stock_research_agent.providers.sec_edgar.policy")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status_code, content=b"blocked", request=request)

    with SafeHttpClient(
        policy_module.build_sec_http_client_policy(network_enabled=True),
        cache=InMemoryResponseCache(),
        rate_limiter=_RateLimiter(),
        request_identity=credentials_module.ProtectedRequestIdentity("offline-contact"),
        transport=httpx.MockTransport(handler),
        resolver=lambda _: (ipaddress.ip_address("93.184.216.34"),),
    ) as client:
        result = client.get(
            HttpRequest(
                url="https://data.sec.gov/submissions/CIK0000723125.json",
                accept="application/json",
            )
        )

    assert result.status_code == status_code
    assert result.attempts == 1
    assert len(calls) == 1


def test_sec_policy_without_protected_identity_fails_before_dns_or_send() -> None:
    policy_module = import_module("stock_research_agent.providers.sec_edgar.policy")
    resolver_calls: list[str] = []
    send_calls: list[httpx.Request] = []

    def resolver(host: str) -> tuple[ipaddress.IPv4Address, ...]:
        resolver_calls.append(host)
        return (ipaddress.ip_address("93.184.216.34"),)

    def handler(request: httpx.Request) -> httpx.Response:
        send_calls.append(request)
        return httpx.Response(200, content=b"unexpected", request=request)

    with SafeHttpClient(
        policy_module.build_sec_http_client_policy(network_enabled=True),
        cache=InMemoryResponseCache(),
        rate_limiter=_RateLimiter(),
        transport=httpx.MockTransport(handler),
        resolver=resolver,
    ) as client:
        with pytest.raises(HttpPolicyError, match="request identity is required"):
            client.get(
                HttpRequest(
                    url="https://data.sec.gov/submissions/CIK0000723125.json",
                    accept="application/json",
                )
            )

    assert resolver_calls == []
    assert send_calls == []


def _transport_controller(
    *,
    reservation_port: object,
    handler: object,
    resolver: _CountingIdentityResolver | None = None,
    dns_calls: list[str] | None = None,
    retry_controller: object | None = None,
    clock: Callable[[], datetime] | None = None,
) -> object:
    transport_module = import_module("stock_research_agent.providers.sec_edgar.transport")
    policy_module = import_module("stock_research_agent.providers.sec_edgar.policy")
    identity_resolver = resolver or _CountingIdentityResolver(
        {"SEC_EDGAR_CONTACT_IDENTITY": "offline-contact"}
    )
    observed_dns = dns_calls if dns_calls is not None else []

    def client_factory(identity: object) -> SafeHttpClient:
        def resolve(host: str) -> tuple[ipaddress.IPv4Address, ...]:
            observed_dns.append(host)
            return (ipaddress.ip_address("93.184.216.34"),)

        return SafeHttpClient(
            policy_module.build_sec_http_client_policy(network_enabled=True),
            cache=InMemoryResponseCache(),
            rate_limiter=_RateLimiter(),
            request_identity=identity,  # type: ignore[arg-type]
            transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
            resolver=resolve,
        )

    arguments: dict[str, object] = {
        "credential_resolver": identity_resolver,
        "reservations": reservation_port,
        "retry_controller": retry_controller or _NeverRetry(),
        "http_client_factory": client_factory,
    }
    if clock is not None:
        arguments["clock"] = clock
    return transport_module.SecGateBTransportController(**arguments)


def test_red_034_runtime_attempt_budget_blocks_fifth_send_before_transport() -> None:
    send_calls: list[httpx.Request] = []
    dns_calls: list[str] = []
    identity_resolver = _CountingIdentityResolver({"SEC_EDGAR_CONTACT_IDENTITY": "offline-contact"})
    reservations = _ReservationPort(max_reservations=4)

    def handler(request: httpx.Request) -> httpx.Response:
        send_calls.append(request)
        return httpx.Response(200, content=b"{}", request=request)

    controller = _transport_controller(
        reservation_port=reservations,
        handler=handler,
        resolver=identity_resolver,
        dns_calls=dns_calls,
    )
    for _ in range(4):
        result = controller.execute(  # type: ignore[attr-defined]
            _execution(),
            plan=_plan(),
            slice_id="SEC_SUBMISSIONS",
            contact_reference=_contact_reference(),
        )
        assert result.status.value == "COMPLETED"

    with pytest.raises(ValueError, match="SEC_ATTEMPT_BUDGET_EXHAUSTED"):
        controller.execute(  # type: ignore[attr-defined]
            _execution(),
            plan=_plan(),
            slice_id="SEC_SUBMISSIONS",
            contact_reference=_contact_reference(),
        )

    assert identity_resolver.calls == 4
    assert len(dns_calls) == 4
    assert len(send_calls) == 4


def test_attempt_permit_must_match_authorization_plan_slice_and_attempt() -> None:
    send_calls: list[httpx.Request] = []
    dns_calls: list[str] = []
    identity_resolver = _CountingIdentityResolver({"SEC_EDGAR_CONTACT_IDENTITY": "offline-contact"})

    def handler(request: httpx.Request) -> httpx.Response:
        send_calls.append(request)
        return httpx.Response(200, content=b"{}", request=request)

    controller = _transport_controller(
        reservation_port=_ReservationPort(wrong_authorization=True),
        handler=handler,
        resolver=identity_resolver,
        dns_calls=dns_calls,
    )

    with pytest.raises(ValueError, match="SEC_ATTEMPT_RESERVATION_REQUIRED"):
        controller.execute(  # type: ignore[attr-defined]
            _execution(),
            plan=_plan(),
            slice_id="SEC_SUBMISSIONS",
            contact_reference=_contact_reference(),
        )

    assert identity_resolver.calls == 0
    assert dns_calls == []
    assert send_calls == []


def test_red_032_authorized_sec_controller_sends_only_canonical_plan_resource() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"{}", request=request)

    controller = _transport_controller(
        reservation_port=_ReservationPort(),
        handler=handler,
    )
    result = controller.execute(  # type: ignore[attr-defined]
        _execution(),
        plan=_plan(),
        slice_id="SEC_SUBMISSIONS",
        contact_reference=_contact_reference(),
    )

    assert result.status.value == "COMPLETED"
    assert len(result.attempts) == 1
    assert result.attempts[0].response.status_code == 200
    assert [str(request.url) for request in requests] == [
        "https://93.184.216.34/submissions/CIK0000723125.json"
    ]


def test_sec_transport_result_contains_bounded_response_without_artifact_fields() -> None:
    controller = _transport_controller(
        reservation_port=_ReservationPort(),
        handler=lambda request: httpx.Response(200, content=b"{}", request=request),
    )
    result = controller.execute(  # type: ignore[attr-defined]
        _execution(),
        plan=_plan(),
        slice_id="SEC_SUBMISSIONS",
        contact_reference=_contact_reference(),
    )

    assert result.status.value == "COMPLETED"
    assert not hasattr(result, "artifact_id")
    assert not hasattr(result, "audit_id")
    assert not hasattr(result, "data_quality")


def test_transport_rejects_envelope_or_raw_url_in_place_of_capability_and_resource() -> None:
    transport_module = import_module("stock_research_agent.providers.sec_edgar.transport")
    signature = inspect.signature(transport_module.SecGateBTransportController.execute)

    assert "url" not in signature.parameters
    assert signature.parameters["execution"].annotation in {
        "AuthorizedGateBExecution",
        AuthorizedGateBExecution,
    }


def test_success_attempt_exposes_safe_timing_and_no_contact_material() -> None:
    times = iter(
        (
            datetime(2026, 8, 20, 0, 0, 0, tzinfo=UTC),
            datetime(2026, 8, 20, 0, 0, 1, tzinfo=UTC),
        )
    )
    controller = _transport_controller(
        reservation_port=_ReservationPort(),
        handler=lambda request: httpx.Response(200, content=b"{}", request=request),
        clock=lambda: next(times),
    )

    result = controller.execute(  # type: ignore[attr-defined]
        _execution(),
        plan=_plan(),
        slice_id="SEC_SUBMISSIONS",
        contact_reference=_contact_reference(),
    )

    attempt = result.attempts[0]
    assert attempt.started_at == datetime(2026, 8, 20, 0, 0, 0, tzinfo=UTC)
    assert attempt.completed_at == datetime(2026, 8, 20, 0, 0, 1, tzinfo=UTC)
    assert attempt.socket_opened is True
    assert "offline-contact" not in repr(attempt)


def test_committed_permit_contact_failure_returns_terminal_pre_socket_attempt() -> None:
    resolver = _CountingIdentityResolver({})
    dns_calls: list[str] = []
    send_calls: list[httpx.Request] = []
    controller = _transport_controller(
        reservation_port=_ReservationPort(),
        handler=lambda request: send_calls.append(request),
        resolver=resolver,
        dns_calls=dns_calls,
        clock=lambda: NOW,
    )

    result = controller.execute(  # type: ignore[attr-defined]
        _execution(),
        plan=_plan(),
        slice_id="SEC_SUBMISSIONS",
        contact_reference=_contact_reference(),
    )

    assert result.status.value == "BLOCKED"
    assert len(result.attempts) == 1
    assert result.attempts[0].safe_error_code == "SEC_CONTACT_RESOLUTION_FAILED"
    assert result.attempts[0].socket_opened is False
    assert dns_calls == []
    assert send_calls == []


def test_transport_failure_with_uncertain_socket_state_cannot_claim_unstarted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    controller = _transport_controller(
        reservation_port=_ReservationPort(),
        handler=handler,
        clock=lambda: NOW,
    )

    result = controller.execute(  # type: ignore[attr-defined]
        _execution(),
        plan=_plan(),
        slice_id="SEC_SUBMISSIONS",
        contact_reference=_contact_reference(),
    )

    assert result.status.value == "BLOCKED"
    assert result.attempts[0].socket_opened is None


def test_red_035_429_returns_abort_after_exactly_one_physical_send() -> None:
    retry_module = import_module("stock_research_agent.providers.sec_edgar.retry")
    sends: list[httpx.Request] = []
    reservations = _ReservationPort()

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        return httpx.Response(429, content=b"rate limited", request=request)

    controller = _transport_controller(
        reservation_port=reservations,
        handler=handler,
        retry_controller=retry_module.SecGateBRetryController(),
    )
    result = controller.execute(  # type: ignore[attr-defined]
        _execution(),
        plan=_plan(),
        slice_id="SEC_SUBMISSIONS",
        contact_reference=_contact_reference(),
    )

    assert result.status.value == "BLOCKED"
    assert result.reason_code == "SEC_HTTP_429_ABORT"
    assert len(sends) == 1
    assert len(reservations.requests) == 1


def test_red_036_rejected_second_retry_never_reaches_send_start() -> None:
    retry_module = import_module("stock_research_agent.providers.sec_edgar.retry")
    events: list[str] = []
    reservations = _GlobalRetryReservationPort(events)
    statuses = iter((503, 200, 503))

    def handler(request: httpx.Request) -> httpx.Response:
        events.append("send_start")
        return httpx.Response(next(statuses), content=b"{}", request=request)

    controller = _transport_controller(
        reservation_port=reservations,
        handler=handler,
        retry_controller=retry_module.SecGateBRetryController(),
    )
    first = controller.execute(  # type: ignore[attr-defined]
        _execution(),
        plan=_plan(),
        slice_id="SEC_SUBMISSIONS",
        contact_reference=_contact_reference(),
    )
    second = controller.execute(  # type: ignore[attr-defined]
        _execution(),
        plan=_plan(),
        slice_id="SEC_FILING_INDEX",
        contact_reference=_contact_reference(),
    )

    assert first.status.value == "COMPLETED"
    assert len(first.attempts) == 2
    assert second.status.value == "BLOCKED"
    assert second.reason_code == "SEC_RETRY_BUDGET_EXHAUSTED"
    assert events.count("send_start") == 3


def test_red_036_retry_permit_precedes_second_send() -> None:
    retry_module = import_module("stock_research_agent.providers.sec_edgar.retry")
    events: list[str] = []
    reservations = _GlobalRetryReservationPort(events)
    statuses = iter((503, 200))

    def handler(request: httpx.Request) -> httpx.Response:
        events.append("send_start")
        return httpx.Response(next(statuses), content=b"{}", request=request)

    controller = _transport_controller(
        reservation_port=reservations,
        handler=handler,
        retry_controller=retry_module.SecGateBRetryController(),
    )
    result = controller.execute(  # type: ignore[attr-defined]
        _execution(),
        plan=_plan(),
        slice_id="SEC_SUBMISSIONS",
        contact_reference=_contact_reference(),
    )

    assert result.status.value == "COMPLETED"
    assert events == [
        "reservation_commit",
        "send_start",
        "retry_eligibility_checked",
        "retry_reserved",
        "reservation_commit",
        "send_start",
    ]


def test_sec_transient_timeout_uses_one_controller_retry_permit() -> None:
    retry_module = import_module("stock_research_agent.providers.sec_edgar.retry")
    events: list[str] = []
    reservations = _GlobalRetryReservationPort(events)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("offline timeout", request=request)
        return httpx.Response(200, content=b"{}", request=request)

    controller = _transport_controller(
        reservation_port=reservations,
        handler=handler,
        retry_controller=retry_module.SecGateBRetryController(),
    )
    result = controller.execute(  # type: ignore[attr-defined]
        _execution(),
        plan=_plan(),
        slice_id="SEC_SUBMISSIONS",
        contact_reference=_contact_reference(),
    )

    assert result.status.value == "COMPLETED"
    assert len(result.attempts) == 2
    assert calls == 2


def test_default_sec_shell_has_no_send_path_without_production_reservation_port() -> None:
    application = cli_live.sec_pilot_application_factory()
    execute_authorized = getattr(application, "execute_authorized", None)

    assert callable(execute_authorized)
    with pytest.raises(LiveEvidenceValidationError, match="LIVE_TRANSPORT_NOT_CONFIGURED"):
        execute_authorized(
            _execution(),
            plan=_plan(),
            slice_id="SEC_SUBMISSIONS",
            contact_reference=_contact_reference(),
        )
