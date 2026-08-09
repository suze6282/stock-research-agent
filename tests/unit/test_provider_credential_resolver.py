from datetime import UTC, datetime
from uuid import uuid4

import pytest

from stock_research_agent.domain.providers.credentials import (
    CredentialReferenceRecord,
    CredentialResolverKind,
)
from stock_research_agent.domain.providers.enums import ProviderCredentialStatus
from stock_research_agent.providers.credentials import (
    CredentialBindingKind,
    EnvironmentCredentialResolver,
    ProviderCredentialExecutionRequest,
)

NOW = datetime(2026, 7, 29, tzinfo=UTC)
SENTINEL = "stage9-test-sentinel-value"


def _reference() -> CredentialReferenceRecord:
    return CredentialReferenceRecord(
        id=uuid4(),
        provider_definition_id=uuid4(),
        reference_version="1.0.0",
        resolver_kind=CredentialResolverKind.ENVIRONMENT,
        declared_name="TEST_PROVIDER_TOKEN",
        status=ProviderCredentialStatus.NOT_READ,
        safe_label="Test Provider token",
        checksum="1" * 64,
        created_at=NOW,
    )


def _request(reference: CredentialReferenceRecord) -> ProviderCredentialExecutionRequest:
    return ProviderCredentialExecutionRequest(
        provider_definition_id=reference.provider_definition_id,
        credential_reference_id=reference.id,
        declared_name="TEST_PROVIDER_TOKEN",
        binding_kind=CredentialBindingKind.HEADER,
        binding_name="X-Test-Token",
        license_allowed=True,
        configuration_allowed=True,
        live_authorized=True,
    )


def test_resolver_requires_explicit_test_environment_and_binds_only_requested_slot() -> None:
    reference = _reference()
    context = EnvironmentCredentialResolver(
        {"TEST_PROVIDER_TOKEN": SENTINEL}
    ).resolve_for_execution(reference, _request(reference))

    assert context.bind_header() == {"X-Test-Token": SENTINEL}
    assert repr(context) == "<ResolvedCredentialContext redacted>"
    assert str(context) == "<ResolvedCredentialContext redacted>"
    assert SENTINEL not in repr(context)
    assert not hasattr(context, "model_dump")
    with pytest.raises(TypeError):
        context.__reduce__()


def test_default_construction_and_metadata_validation_never_read_os_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "os.getenv",
        lambda *_args, **_kwargs: pytest.fail("resolver read global environment"),
    )
    resolver = EnvironmentCredentialResolver({})
    reference = _reference()

    with pytest.raises(ValueError, match="CREDENTIAL_NOT_CONFIGURED"):
        resolver.resolve_for_execution(reference, _request(reference))


@pytest.mark.parametrize(
    ("request_update", "reason"),
    [
        ({"provider_definition_id": uuid4()}, "CREDENTIAL_PROVIDER_MISMATCH"),
        ({"credential_reference_id": uuid4()}, "CREDENTIAL_REFERENCE_MISMATCH"),
        ({"declared_name": "OTHER_TOKEN"}, "CREDENTIAL_NAME_NOT_DECLARED"),
        ({"license_allowed": False}, "CREDENTIAL_LICENSE_GATE_REQUIRED"),
        ({"configuration_allowed": False}, "CREDENTIAL_CONFIGURATION_GATE_REQUIRED"),
        ({"live_authorized": False}, "CREDENTIAL_LIVE_AUTHORIZATION_REQUIRED"),
        ({"binding_name": "Authorization"}, "CREDENTIAL_BINDING_NOT_ALLOWED"),
    ],
)
def test_resolver_rejects_undeclared_or_pregate_execution(
    request_update: dict[str, object],
    reason: str,
) -> None:
    reference = _reference()
    request = _request(reference).model_copy(update=request_update)
    resolver = EnvironmentCredentialResolver({"TEST_PROVIDER_TOKEN": SENTINEL})

    with pytest.raises(ValueError, match=reason):
        resolver.resolve_for_execution(reference, request)
