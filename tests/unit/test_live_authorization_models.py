from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.live_evidence.enums import EvidenceSourceType
from stock_research_agent.domain.live_evidence.schemas import (
    LiveAuthorizationGrantRecord,
    LiveAuthorizationGrantWrite,
)


def _grant_values() -> dict[str, object]:
    approved_at = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    return {
        "provider_definition_id": UUID("10000000-0000-0000-0000-000000000001"),
        "provider_code": "SEC_EDGAR_PUBLIC_V1",
        "provider_definition_version": "1.0.0",
        "provider_definition_checksum": "1" * 64,
        "provider_capability_id": UUID("10000000-0000-0000-0000-000000000002"),
        "capability_code": "FETCH_SEC_FILING_DOCUMENTS",
        "capability_version": "1.0.0",
        "official_domains": ("data.sec.gov", "www.sec.gov"),
        "security_id": UUID("40000000-0000-0000-0000-000000000002"),
        "issuer_id": UUID("30000000-0000-0000-0000-000000000002"),
        "provider_security_identifier": "0000723125",
        "request_methods": ("GET",),
        "request_limit": 4,
        "byte_limit": 26_214_400,
        "date_from": date(2025, 8, 1),
        "date_to": date(2026, 8, 1),
        "filing_types": ("10-K",),
        "allowed_document_count": 1,
        "credential_reference_id": UUID("10000000-0000-0000-0000-000000000003"),
        "user_agent_reference_id": UUID("10000000-0000-0000-0000-000000000004"),
        "license_policy_id": UUID("10000000-0000-0000-0000-000000000005"),
        "license_policy_version": "1.0.0",
        "license_policy_checksum": "2" * 64,
        "provider_policy_id": UUID("10000000-0000-0000-0000-000000000006"),
        "provider_policy_version": "1.0.0",
        "provider_policy_checksum": "3" * 64,
        "raw_storage_allowed": True,
        "cache_allowed": False,
        "retention_deadline": approved_at + timedelta(days=30),
        "approved_at": approved_at,
        "expires_at": approved_at + timedelta(minutes=30),
        "approved_by": "LOCAL_OPERATOR",
        "canonical_checksum": "4" * 64,
    }


def test_grant_scope_is_frozen_and_secret_free() -> None:
    grant = LiveAuthorizationGrantWrite.model_validate(_grant_values())

    assert grant.provider_code == "SEC_EDGAR_PUBLIC_V1"
    assert grant.request_methods == ("GET",)
    assert grant.request_limit == 4
    assert grant.byte_limit == 26_214_400
    assert grant.model_fields_set == set(_grant_values())
    assert not hasattr(grant, "credential_value")
    assert not hasattr(grant, "user_agent_value")
    with pytest.raises(ValidationError):
        grant.request_limit = 5


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_limit", 0),
        ("request_limit", 101),
        ("byte_limit", 0),
        ("byte_limit", 52_428_801),
        ("allowed_document_count", 0),
        ("request_methods", ("POST",)),
        ("official_domains", ("www.sec.gov", "data.sec.gov")),
        ("official_domains", ("*.sec.gov",)),
        ("filing_types", ("10-Q", "10-K")),
        ("approved_by", "operator@example.com"),
        ("canonical_checksum", "not-a-checksum"),
    ],
)
def test_grant_rejects_invalid_finite_scope(field: str, value: object) -> None:
    values = _grant_values()
    values[field] = value

    with pytest.raises(ValidationError):
        LiveAuthorizationGrantWrite.model_validate(values)


def test_grant_rejects_reversed_dates_and_expiry() -> None:
    values = _grant_values()
    values["date_from"] = date(2026, 8, 2)
    with pytest.raises(ValidationError):
        LiveAuthorizationGrantWrite.model_validate(values)

    values = _grant_values()
    values["expires_at"] = values["approved_at"]
    with pytest.raises(ValidationError):
        LiveAuthorizationGrantWrite.model_validate(values)


def test_grant_rejects_document_count_above_request_limit() -> None:
    values = _grant_values()
    values["request_limit"] = 1
    values["allowed_document_count"] = 2

    with pytest.raises(ValidationError):
        LiveAuthorizationGrantWrite.model_validate(values)


def test_record_adds_database_identity_without_changing_scope() -> None:
    grant = LiveAuthorizationGrantWrite.model_validate(_grant_values())
    record = LiveAuthorizationGrantRecord(
        **grant.model_dump(),
        id=UUID("10000000-0000-0000-0000-000000000099"),
        created_at=datetime(2026, 8, 1, 8, 1, tzinfo=UTC),
    )

    assert record.id == UUID("10000000-0000-0000-0000-000000000099")
    assert record.canonical_checksum == grant.canonical_checksum


def test_evidence_source_type_has_no_implicit_live_alias() -> None:
    assert tuple(EvidenceSourceType) == (
        EvidenceSourceType.PROVIDER_LIVE,
        EvidenceSourceType.MANUAL_IMPORT,
        EvidenceSourceType.SYNTHETIC_TEST,
        EvidenceSourceType.OFFLINE_FIXTURE,
    )
