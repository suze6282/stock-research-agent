import hashlib
import importlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).parents[2]
SCHEMAS_MODULE = ROOT / "src" / "stock_research_agent" / "domain" / "providers" / "schemas.py"


def _load_modules() -> tuple[object, object, object]:
    assert SCHEMAS_MODULE.is_file(), "immutable Provider Definition contracts are absent"
    schemas = importlib.import_module("stock_research_agent.domain.providers.schemas")
    canonical = importlib.import_module("stock_research_agent.domain.providers.canonical")
    enums = importlib.import_module("stock_research_agent.domain.providers.enums")
    return schemas, canonical, enums


def _definition_kwargs(enums: object) -> dict[str, object]:
    return {
        "code": "SEC_EDGAR_PUBLIC_V1",
        "definition_version": "1.0.0",
        "adapter_version": "1.0.0",
        "display_name": "SEC EDGAR public data",
        "data_domain": "US_SEC_FILINGS",
        "definition_status": enums.ProviderDefinitionStatus.ACTIVE,
        "production_status": enums.ProviderProductionStatus.CONDITIONAL,
        "official_domains": ("data.sec.gov", "www.sec.gov"),
        "policy_version": "1.0.0",
        "license_policy_version": "1.0.0",
        "credential_reference_id": None,
        "source_register_version": "1.0.0",
    }


def test_provider_definition_is_strict_frozen_and_versioned() -> None:
    schemas, _, enums = _load_modules()
    value = schemas.ProviderDefinitionWrite(**_definition_kwargs(enums))

    assert value.code == "SEC_EDGAR_PUBLIC_V1"
    assert value.official_domains == ("data.sec.gov", "www.sec.gov")
    with pytest.raises(ValidationError):
        value.code = "OTHER"
    with pytest.raises(ValidationError):
        schemas.ProviderDefinitionWrite(
            **_definition_kwargs(enums),
            unexpected="not allowed",
        )


def test_provider_definition_record_checksum_is_deterministic() -> None:
    schemas, canonical, enums = _load_modules()
    write = schemas.ProviderDefinitionWrite(**_definition_kwargs(enums))
    expected_json = (
        '{"adapter_version":"1.0.0","code":"SEC_EDGAR_PUBLIC_V1",'
        '"credential_reference_id":null,"data_domain":"US_SEC_FILINGS",'
        '"definition_status":"ACTIVE","definition_version":"1.0.0",'
        '"display_name":"SEC EDGAR public data",'
        '"license_policy_version":"1.0.0",'
        '"official_domains":["data.sec.gov","www.sec.gov"],'
        '"policy_version":"1.0.0","production_status":"CONDITIONAL",'
        '"source_register_version":"1.0.0"}'
    )

    assert canonical.canonical_provider_json(write) == expected_json
    assert (
        canonical.provider_checksum(write)
        == hashlib.sha256(expected_json.encode("utf-8")).hexdigest()
    )

    record = schemas.ProviderDefinitionRecord(
        **write.model_dump(),
        id=UUID("11111111-1111-4111-8111-111111111111"),
        checksum=canonical.provider_checksum(write),
        created_at=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
    )
    assert record.checksum == canonical.provider_checksum(write)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    (
        ("code", "sec_edgar"),
        ("definition_version", "latest"),
        ("adapter_version", "v1"),
        ("data_domain", "us filings"),
        ("official_domains", ("https://data.sec.gov",)),
        ("official_domains", ("*.sec.gov",)),
        ("official_domains", ("data.sec.gov:443",)),
    ),
)
def test_provider_definition_rejects_unstable_or_unsafe_identity(
    field: str,
    invalid_value: object,
) -> None:
    schemas, _, enums = _load_modules()
    kwargs = _definition_kwargs(enums)
    kwargs[field] = invalid_value

    with pytest.raises(ValidationError):
        schemas.ProviderDefinitionWrite(**kwargs)
