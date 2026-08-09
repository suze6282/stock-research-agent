import importlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers.enums import ProviderCredentialStatus

ROOT = Path(__file__).parents[2]
CREDENTIALS_MODULE = (
    ROOT / "src" / "stock_research_agent" / "domain" / "providers" / "credentials.py"
)
PROVIDER_ID = UUID("11111111-1111-4111-8111-111111111111")


def _credentials() -> object:
    assert CREDENTIALS_MODULE.is_file(), "secret-free Credential Reference is absent"
    return importlib.import_module("stock_research_agent.domain.providers.credentials")


def test_environment_credential_reference_contains_metadata_only() -> None:
    credentials = _credentials()
    reference = credentials.CredentialReferenceRecord(
        id=UUID("22222222-2222-4222-8222-222222222222"),
        provider_definition_id=PROVIDER_ID,
        reference_version="1.0.0",
        resolver_kind=credentials.CredentialResolverKind.ENVIRONMENT,
        declared_name="TUSHARE_TOKEN",
        status=ProviderCredentialStatus.NOT_READ,
        safe_label="Tushare production token reference",
        checksum="a" * 64,
        created_at=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
    )

    dumped = reference.model_dump(mode="json")
    assert dumped["declared_name"] == "TUSHARE_TOKEN"
    assert dumped["status"] == "NOT_READ"
    assert set(dumped) == {
        "provider_definition_id",
        "reference_version",
        "resolver_kind",
        "declared_name",
        "status",
        "safe_label",
        "id",
        "checksum",
        "created_at",
    }
    assert "secret-sentinel" not in repr(reference)


@pytest.mark.parametrize(
    "forbidden_field",
    (
        "value",
        "secret",
        "token",
        "api_key",
        "password",
        "prefix",
        "suffix",
        "hash",
        "cookie",
        "authorization",
    ),
)
def test_credential_reference_rejects_secret_shaped_fields(
    forbidden_field: str,
) -> None:
    credentials = _credentials()
    values = {
        "provider_definition_id": PROVIDER_ID,
        "reference_version": "1.0.0",
        "resolver_kind": credentials.CredentialResolverKind.ENVIRONMENT,
        "declared_name": "TUSHARE_TOKEN",
        "status": ProviderCredentialStatus.NOT_READ,
        "safe_label": "Tushare token reference",
        forbidden_field: "secret-sentinel",
    }

    with pytest.raises(ValidationError):
        credentials.CredentialReferenceWrite(**values)
    with pytest.raises(ValueError, match="forbidden credential metadata field"):
        credentials.validate_credential_reference_metadata(values)


def test_credential_reference_rejects_undeclared_or_inconsistent_resolver_slot() -> None:
    credentials = _credentials()
    base = {
        "provider_definition_id": PROVIDER_ID,
        "reference_version": "1.0.0",
        "resolver_kind": credentials.CredentialResolverKind.ENVIRONMENT,
        "declared_name": "TUSHARE_TOKEN",
        "status": ProviderCredentialStatus.NOT_READ,
        "safe_label": "Tushare token reference",
    }

    for update in (
        {"declared_name": "TUSHARE-TOKEN"},
        {"declared_name": "Path"},
        {"declared_name": None},
        {
            "resolver_kind": credentials.CredentialResolverKind.NONE,
            "declared_name": "TUSHARE_TOKEN",
        },
        {
            "resolver_kind": credentials.CredentialResolverKind.NONE,
            "declared_name": None,
            "status": ProviderCredentialStatus.NOT_READ,
        },
    ):
        with pytest.raises(ValidationError):
            credentials.CredentialReferenceWrite(**{**base, **update})


def test_no_credential_reference_requires_no_declared_name() -> None:
    credentials = _credentials()
    value = credentials.CredentialReferenceWrite(
        provider_definition_id=PROVIDER_ID,
        reference_version="1.0.0",
        resolver_kind=credentials.CredentialResolverKind.NONE,
        declared_name=None,
        status=ProviderCredentialStatus.NOT_REQUIRED,
        safe_label="No credential required",
    )

    assert value.declared_name is None
    assert value.status is ProviderCredentialStatus.NOT_REQUIRED
